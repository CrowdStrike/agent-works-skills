#!/usr/bin/env python3
"""
analyze_agent.py - Analyze agent execution patterns from traces and suggest improvements.

Queries spans by agent_id, analyzes tool usage, errors, and performance patterns,
then suggests improvements to system prompt and tool configuration.

Examples:
    # Analyze last 24 hours
    python analyze_agent.py --agent-id <uuid>

    # Analyze last 7 days
    python analyze_agent.py --agent-id <uuid> --days 7

    # Verbose output with per-trace details
    python analyze_agent.py --agent-id <uuid> --verbose

    # Scope to a specific set of invocations instead of a whole agent_id window --
    # use this for a before/after comparison so re-analyzing after publishing a new
    # version doesn't merge the old version's traces back in.
    python analyze_agent.py --agent-id <uuid> --invocation-ids <uuid1> <uuid2>
"""

import argparse
import hashlib
import json
import sys
import os
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import call_native, get_agents_client
from discovery_helpers import TOOL_RESPONSE_SPAN_TYPE, hydrate_spans, query_span_ids
from formatting import humanize_duration

# Upper bounds on span IDs collected per query; pagination (500 per page) fills them.
MAX_ROOT_SPANS = 2000
MAX_SPANS_PER_TRACE = 5000


# Traces whose spans are fetched in one query, and the span cap for such a batch. A batch that
# hits the cap is re-fetched trace by trace so nothing is silently cut off.
TRACE_BATCH = 10
MAX_SPANS_PER_BATCH = 5000


def _fq(value: str) -> str:
    """Escape a value for use inside a single-quoted FQL string."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def query_agent_spans(
    agent_id: str, days: int = 1, agent_name: str | None = None
) -> tuple[list[str], list[dict]]:
    """Query span IDs for every trace belonging to this agent within the time window.

    Two-stage, matching inspect_invocation.py's resolve_trace_id/fetch_full_trace pattern:
    `attributes.aw_agent.id` is present ONLY on root spans (aw_agent, aw_agent_response) --
    child spans (tool, tool_response, llm) carry no aw_agent.* attributes at all, only
    trace_id (see references/fql-syntax.md's "Span Relationships" section). A single-stage
    query on aw_agent.id therefore returns only the 1-2 root spans per trace and silently
    drops every tool/LLM child span an analysis actually needs.

    Inline/programmatic invocations have no aw_agent.id but carry aw_agent.definition.name, so
    when the agent's name is known those are queried too and kept when the name matches and no
    other agent ID is present.

    Returns:
        (all span IDs, the already-hydrated root spans), so callers don't hydrate roots twice.
    """
    window = f"start_time:>='now-{days}d'"
    filters = [f"(attributes.aw_agent.id:'{_fq(agent_id)}'+{window})"]
    if agent_name:
        filters.append(f"(attributes.aw_agent.definition.name:'{_fq(agent_name)}'+{window})")

    root_ids: list[str] = []
    for root_filter in filters:
        found = query_span_ids(root_filter, max_results=MAX_ROOT_SPANS)
        if len(found) >= MAX_ROOT_SPANS:
            print(f"WARNING: hit the {MAX_ROOT_SPANS}-root-span cap; the analysis covers only the "
                  f"newest traces, not the full {days}-day window. Use a smaller --days.",
                  file=sys.stderr)
        root_ids += found
    root_ids = list(dict.fromkeys(root_ids))

    def belongs_to_agent(span: dict) -> bool:
        attrs = span.get("attributes") or {}
        span_agent_id = attrs.get("aw_agent.id")
        if span_agent_id:
            return span_agent_id == agent_id
        return bool(agent_name) and attrs.get("aw_agent.definition.name") == agent_name

    return _expand_to_full_traces(root_ids, keep=belongs_to_agent)


def query_invocation_spans(invocation_ids: list[str], days: int = 90) -> tuple[list[str], list[dict]]:
    """Query span IDs for a specific, known set of invocations (before/after comparisons).

    Same two-stage shape as query_agent_spans, but scoped by aw_agent.invocation_id
    instead of aw_agent.id -- lets a re-analysis after publishing a new version compare
    only the invocations that actually exercised it, instead of merging every version's
    traces together under one agent_id (see inspect_invocation.py's resolve_trace_id, which
    does the single-invocation version of this same query).
    """
    root_ids: list[str] = []
    for inv_id in invocation_ids:
        root_filter = (
            f"(attributes.aw_agent.invocation_id:'{_fq(inv_id)}'"
            f"+start_time:>='now-{days}d')"
        )
        root_ids += query_span_ids(root_filter, max_results=10)
    return _expand_to_full_traces(root_ids)


def _expand_to_full_traces(root_ids: list[str], keep=None) -> tuple[list[str], list[dict]]:
    """Given root-span IDs, hydrate them, collect their trace_ids, and fetch each trace's full
    span set (root + tool/tool_response/llm children), several traces per query.

    Args:
        root_ids: Root-span IDs from the stage-1 query
        keep: Optional predicate on a hydrated root span; traces with no kept root are dropped

    Returns:
        (all span IDs for the kept traces, the kept hydrated root spans)
    """
    if not root_ids:
        return [], []
    root_spans = hydrate_spans(root_ids)
    if keep is not None:
        root_spans = [s for s in root_spans if keep(s)]
    kept_root_ids = {s.get("id") for s in root_spans}
    root_ids = [i for i in root_ids if i in kept_root_ids]
    trace_ids = list(dict.fromkeys(s["trace_id"] for s in root_spans if s.get("trace_id")))

    all_ids = list(root_ids)
    for i in range(0, len(trace_ids), TRACE_BATCH):
        chunk = trace_ids[i:i + TRACE_BATCH]
        trace_list = ",".join(f"'{_fq(t)}'" for t in chunk)
        batch_ids = query_span_ids(f"trace_id:[{trace_list}]", max_results=MAX_SPANS_PER_BATCH)
        if len(batch_ids) >= MAX_SPANS_PER_BATCH:
            # Possibly truncated: fetch these traces one by one instead.
            batch_ids = []
            for trace_id in chunk:
                trace_span_ids = query_span_ids(f"trace_id:'{_fq(trace_id)}'",
                                                max_results=MAX_SPANS_PER_TRACE)
                if len(trace_span_ids) >= MAX_SPANS_PER_TRACE:
                    print(f"WARNING: trace {trace_id} has at least {MAX_SPANS_PER_TRACE} spans; "
                          f"only the newest {MAX_SPANS_PER_TRACE} are analyzed.", file=sys.stderr)
                batch_ids += trace_span_ids
        all_ids += batch_ids
    # dict.fromkeys dedupes while preserving order (a span_id can appear in both
    # the root query and its trace re-query).
    return list(dict.fromkeys(all_ids)), root_spans


def _ts_ms(ts: str | None) -> float:
    """ISO8601 timestamp to epoch ms, with missing/unparseable values sorting last.

    Compared numerically because 'Z' and '+00:00' denote the same instant but sort differently
    as strings.
    """
    if not ts:
        return float("inf")
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return float("inf")


def extract_agent_version(span: dict) -> dict:
    """Extract agent version/definition from span attributes."""
    attrs = span.get("attributes", {})

    # Build version signature from definition fields. The tool list is reduced to sorted IDs so
    # an API that returns tools in a different order does not split one version into two.
    tools = attrs.get("aw_agent.definition.tools") or []
    version = {
        "model": attrs.get("aw_agent.definition.model"),
        "system_prompt": attrs.get("aw_agent.definition.system_prompt") or "",
        "tools": sorted(
            (t.get("id") or t.get("name") or "") if isinstance(t, dict) else str(t) for t in tools
        ),
        "model_config": {
            "temperature": attrs.get("aw_agent.definition.model_config.temperature"),
            "max_tokens": attrs.get("aw_agent.definition.model_config.max_tokens"),
            "reasoning": attrs.get("aw_agent.definition.model_config.enable_reasoning"),
        }
    }

    # Full definition for comparison
    definition = {
        "name": attrs.get("aw_agent.definition.name"),
        "description": attrs.get("aw_agent.definition.description"),
        "model": attrs.get("aw_agent.definition.model"),
        "system_prompt": attrs.get("aw_agent.definition.system_prompt"),
        "tools": attrs.get("aw_agent.definition.tools", []),
        "model_config": {
            k.replace("aw_agent.definition.model_config.", ""): v
            for k, v in attrs.items()
            if k.startswith("aw_agent.definition.model_config.")
        },
        "input_format": attrs.get("aw_agent.definition.input_format"),
        "output_format": attrs.get("aw_agent.definition.output_format"),
    }

    return {
        # Stable across processes (unlike hash(), which is randomized per run by PYTHONHASHSEED).
        "version_signature": hashlib.sha256(
            json.dumps(version, sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
        "definition": definition
    }


def analyze_spans(spans: list[dict]) -> dict:
    """Analyze spans to extract patterns and metrics."""
    # Group by trace_id (invocation)
    by_trace = defaultdict(list)
    for span in spans:
        trace_id = span.get("trace_id")
        if trace_id:
            by_trace[trace_id].append(span)

    # Get execution patterns first (needs by_trace)
    execution_patterns = analyze_execution_patterns(spans, by_trace)

    # Extract metrics
    total_traces = len(by_trace)
    tool_usage = Counter()
    tool_errors = Counter()
    tool_durations = defaultdict(list)
    trace_durations = []
    trace_statuses = Counter()
    invocation_ids = set()

    # Version tracking
    by_version = defaultdict(lambda: {
        "traces": [],
        "durations": [],
        "errors": 0,
        "cost_cents": [],
        "definition": None
    })

    total_cost_cents = 0.0
    empty_result_traces = 0

    for trace_id, trace_spans in by_trace.items():
        # Extract invocation_id and version from agent-level span
        trace_version = None
        # Only the aw_agent_response span carries these -- confirmed live
        # (2026-09-25): cost.agg_credit_cents (total credits spent for the
        # invocation) and aw_agent.output (the final response). Deferred to
        # after has_error is known below, same reason trace duration is
        # deferred: trace_version may not be set yet on the span that carries
        # cost/output if aw_agent_response happens to precede aw_agent.
        trace_cost_cents = None
        trace_output_empty = False

        for span in trace_spans:
            attrs = span.get("attributes", {})
            # Attributes are flat: aw_agent.invocation_id, aw_agent.id
            inv_id = attrs.get("aw_agent.invocation_id")
            if inv_id:
                invocation_ids.add(inv_id)

                # Only treat this as the version-defining span if it actually
                # carries a model -- aw_agent_response spans also carry
                # aw_agent.invocation_id but have no aw_agent.definition.* at
                # all, so extracting a "version" from them produces a phantom
                # Model: None, Tools: 0 entry distinct from the real version.
                if attrs.get("aw_agent.definition.model") is not None:
                    version_info = extract_agent_version(span)
                    trace_version = version_info["version_signature"]

                    # Store definition for this version
                    if not by_version[trace_version]["definition"]:
                        by_version[trace_version]["definition"] = version_info["definition"]

            cost_cents = attrs.get("cost.agg_credit_cents")
            if cost_cents is not None:
                trace_cost_cents = cost_cents

            # "aw_agent.output" is only present on the aw_agent_response span --
            # a trace that completes without error but with a blank output is a
            # distinct failure mode from an errored trace (e.g. the agent
            # decided it had nothing to say), invisible until now.
            if "aw_agent.output" in attrs and not attrs.get("aw_agent.output"):
                trace_output_empty = True

        # Trace-level metrics
        starts = [s.get("start_time") for s in trace_spans if s.get("start_time")]
        ends = [s.get("end_time") for s in trace_spans if s.get("end_time")]
        if starts and ends:
            # Parse timestamps
            try:
                start_ms = min([datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp() * 1000
                               for t in starts])
                end_ms = max([datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp() * 1000
                             for t in ends])
                duration = end_ms - start_ms
                trace_durations.append(duration)

                # Track by version
                if trace_version:
                    by_version[trace_version]["traces"].append({
                        "trace_id": trace_id,
                        # Earliest span start, not whichever span happened to be seen last.
                        "start_time": min(starts, key=_ts_ms),
                        "duration_ms": duration
                    })
                    by_version[trace_version]["durations"].append(duration)
            except (ValueError, TypeError):
                pass

        # Check trace status. tool_response spans carry tool.result_is_error
        # as well as status -- checked live against a real tenant (2026-09-23):
        # a failed tool call's span had status:"error" AND
        # attributes.tool.result_is_error:true together in every sample, so
        # this is a belt-and-suspenders addition, not a replacement for status.
        has_error = any(
            s.get("status") == "error"
            or s.get("attributes", {}).get("tool.result_is_error") is True
            for s in trace_spans
        )
        trace_statuses["error" if has_error else "success"] += 1

        if has_error and trace_version:
            by_version[trace_version]["errors"] += 1

        if trace_cost_cents is not None:
            total_cost_cents += trace_cost_cents
            if trace_version:
                by_version[trace_version]["cost_cents"].append(trace_cost_cents)

        # A blank aw_agent.output only counts as "empty result" when the trace
        # otherwise succeeded -- an errored trace legitimately has no output.
        if trace_output_empty and not has_error:
            empty_result_traces += 1

        # Tool-level metrics -- see TOOL_RESPONSE_SPAN_TYPE for why only this
        # one span_type is counted (avoids double-counting each tool call).
        for span in trace_spans:
            span_type = span.get("span_type", "")
            attrs = span.get("attributes", {})
            # span.get("name") is a generic display label ("Tool Response" for
            # EVERY tool_response span, regardless of which tool ran) -- the
            # real tool identifier is attributes.tool.id/tool.name, confirmed
            # live (2026-09-23) to match the agent definition's tool.id exactly.
            name = attrs.get("tool.id") or attrs.get("tool.name") or span.get("name", "")
            status = span.get("status", "")
            duration_ms = span.get("duration_ms")
            result_is_error = attrs.get("tool.result_is_error")

            if span_type == TOOL_RESPONSE_SPAN_TYPE:
                tool_usage[name] += 1
                if status == "error" or result_is_error is True:
                    tool_errors[name] += 1
                if duration_ms:
                    tool_durations[name].append(duration_ms)

    return {
        "total_traces": total_traces,
        "total_spans": len(spans),
        "invocation_ids": list(invocation_ids),
        "trace_statuses": dict(trace_statuses),
        "tool_usage": dict(tool_usage),
        "tool_errors": dict(tool_errors),
        "tool_durations": {tool: {
            "count": len(durs),
            "avg_ms": sum(durs) / len(durs) if durs else 0,
            "max_ms": max(durs) if durs else 0
        } for tool, durs in tool_durations.items()},
        "trace_durations": {
            "count": len(trace_durations),
            "avg_ms": sum(trace_durations) / len(trace_durations) if trace_durations else 0,
            "max_ms": max(trace_durations) if trace_durations else 0
        },
        "by_version": dict(by_version),
        "execution_patterns": execution_patterns,
        # Distinct from "tool_usage is empty" (which is also true if every
        # configured tool genuinely went unused) -- this tells the difference
        # between "no tool telemetry was fetched at all" (the bug this script
        # used to have) and "telemetry was fetched but nothing used a tool".
        "saw_tool_telemetry": any(s.get("span_type") == TOOL_RESPONSE_SPAN_TYPE for s in spans),
        "total_cost_cents": total_cost_cents,
        "avg_cost_cents": total_cost_cents / total_traces if total_traces else 0,
        "empty_result_traces": empty_result_traces,
    }


def analyze_execution_patterns(spans: list[dict], by_trace: dict) -> dict:
    """Analyze actual execution patterns from spans to understand agent behavior."""
    patterns = {
        "tool_sequences": [],
        "error_contexts": [],
        "llm_calls": [],
        "unused_tools": set(),
        "configured_tools": set(),
        "tool_call_patterns": defaultdict(int),
        "input_patterns": [],
    }

    for trace_id, trace_spans in by_trace.items():
        # Get root span for this trace
        root_span = None
        for span in trace_spans:
            if span.get("span_type") in ["aw_agent", "aw_eval_run_started"]:
                root_span = span
                break

        if not root_span:
            continue

        attrs = root_span.get("attributes", {})

        # Collect configured tools. tool.get("id") is preferred over "name" --
        # the agent definition's "name" field is frequently an empty string
        # (confirmed live 2026-09-23: e.g. {"name": "", "id": "mcp/charlotte-mcp/logscale"}),
        # so tool.get("name", tool.get("id", "")) never actually falls back to
        # id (the "name" key exists, just empty) and silently collects "" as a
        # "configured tool". "id" is the value that also shows up verbatim in
        # a tool_response span's attributes.tool.id/tool.name.
        configured_tools = attrs.get("aw_agent.definition.tools", [])
        for tool in configured_tools:
            if isinstance(tool, dict):
                identifier = tool.get("id") or tool.get("name") or ""
                if identifier:
                    patterns["configured_tools"].add(identifier)

        # Collect input for pattern analysis
        agent_input = attrs.get("aw_agent.input", [])
        if agent_input:
            patterns["input_patterns"].append({
                "trace_id": trace_id,
                "input": agent_input,
                "duration_ms": root_span.get("duration_ms", 0),
                "status": root_span.get("status", "unset")
            })

        # Build tool sequence for this trace
        tool_sequence = []
        llm_count = 0

        # Sort by start_time to get execution order
        sorted_spans = sorted(
            [s for s in trace_spans if s.get("start_time")],
            key=lambda s: s.get("start_time", "")
        )

        for span in sorted_spans:
            span_type = span.get("span_type", "")
            name = span.get("name", "")
            status = span.get("status", "")
            span_attrs = span.get("attributes", {})

            # Track LLM calls
            if "llm" in span_type.lower() or "model" in span_type.lower():
                llm_count += 1
                patterns["llm_calls"].append({
                    "trace_id": trace_id,
                    "name": name,
                    "duration_ms": span.get("duration_ms", 0)
                })

            # Track tool calls -- exact match, see TOOL_RESPONSE_SPAN_TYPE.
            if span_type == TOOL_RESPONSE_SPAN_TYPE:
                # See the identical fix in analyze_spans() for why this reads
                # attributes.tool.id/tool.name instead of the generic span name.
                tool_name = span_attrs.get("tool.id") or span_attrs.get("tool.name") or name
                tool_sequence.append({
                    "name": tool_name,
                    "status": status,
                    "duration_ms": span.get("duration_ms", 0)
                })

                # Collect error context
                result_is_error = span_attrs.get("tool.result_is_error")
                if status == "error" or result_is_error is True:
                    patterns["error_contexts"].append({
                        "trace_id": trace_id,
                        "tool": tool_name,
                        "input": agent_input,
                        "attributes": span_attrs
                    })

        if tool_sequence:
            patterns["tool_sequences"].append({
                "trace_id": trace_id,
                "sequence": tool_sequence,
                "llm_calls": llm_count
            })

            # Track common tool combinations
            if len(tool_sequence) > 1:
                tool_names = [t["name"] for t in tool_sequence]
                combo = " → ".join(tool_names)
                patterns["tool_call_patterns"][combo] += 1

    # Identify unused tools
    used_tools = set()
    for seq in patterns["tool_sequences"]:
        for tool_call in seq["sequence"]:
            used_tools.add(tool_call["name"])

    patterns["unused_tools"] = patterns["configured_tools"] - used_tools

    # Sets aren't JSON-serializable -- convert before returning (--json mode
    # crashed with "Object of type set is not JSON serializable" until this
    # fix, confirmed live 2026-09-23; pre-existing, unrelated to the span-fetch
    # fix above but caught while verifying it end-to-end).
    patterns["configured_tools"] = sorted(patterns["configured_tools"])
    patterns["unused_tools"] = sorted(patterns["unused_tools"])
    patterns["tool_call_patterns"] = dict(patterns["tool_call_patterns"])

    return patterns


def generate_recommendations(analysis: dict, agent_details: dict | None, execution_patterns: dict) -> list[str]:
    """Generate improvement recommendations based on analysis."""
    recommendations = []

    # Error rate analysis
    total_traces = analysis["total_traces"]
    error_traces = analysis["trace_statuses"].get("error", 0)
    if total_traces > 0:
        error_rate = error_traces / total_traces
        if error_rate > 0.2:
            recommendations.append(
                f"⚠️ High error rate: {error_rate:.1%} of traces failed. "
                "Review tool configurations and error handling in system prompt."
            )

    # Tool usage analysis
    tool_usage = analysis["tool_usage"]
    tool_errors = analysis["tool_errors"]

    # Unused tools (if we have agent details)
    if agent_details:
        active_version = agent_details.get("active_version") or {}
        # t["id"] is preferred over t["name"] -- confirmed live (2026-09-23) that
        # "name" is frequently an empty string (e.g. {"name": "", "id":
        # "mcp/charlotte-mcp/logscale"}), while "id" is the value that shows up
        # verbatim in a tool_response span's attributes.tool.id/tool.name, which
        # is what tool_usage's keys are now built from (see analyze_spans()).
        configured_tools = {
            t.get("id") or t.get("name") or "" for t in (active_version.get("tools") or [])
        } - {""}
        used_tools = set(tool_usage.keys())
        unused_tools = configured_tools - used_tools

        if not analysis.get("saw_tool_telemetry") and configured_tools:
            # Zero tool_response spans were fetched at all -- do NOT claim every
            # configured tool is unused, since that's indistinguishable from
            # "the span query returned no tool telemetry in this window" and
            # acting on it would strip working tool config from a healthy agent.
            recommendations.append(
                "❓ No tool telemetry in scope for this window -- can't tell which "
                "configured tools were actually used. Try a larger --days, or "
                "confirm this agent's traces actually include tool calls."
            )
        elif unused_tools:
            recommendations.append(
                f"📋 Unused tools detected: {', '.join(sorted(unused_tools))}. "
                "Consider removing or clarifying their usage in the system prompt."
            )

    # Error-prone tools
    for tool, error_count in tool_errors.items():
        usage_count = tool_usage.get(tool, 0)
        if usage_count > 0:
            error_rate = error_count / usage_count
            if error_rate > 0.3:
                recommendations.append(
                    f"⚠️ Tool '{tool}' has high error rate: {error_rate:.1%}. "
                    "Check parameter passing or add error handling guidance to prompt."
                )

    # Performance analysis
    tool_durs = analysis["tool_durations"]
    for tool, dur_stats in tool_durs.items():
        if dur_stats["avg_ms"] > 30000:  # > 30 seconds
            recommendations.append(
                f"⏱️ Tool '{tool}' is slow (avg {dur_stats['avg_ms']/1000:.1f}s). "
                "Consider optimizing queries or setting timeouts."
            )

    # Trace duration
    trace_dur = analysis["trace_durations"]
    if trace_dur["avg_ms"] > 60000:  # > 1 minute
        recommendations.append(
            f"⏱️ Average invocation duration is {trace_dur['avg_ms']/1000:.1f}s. "
            "Consider simplifying the workflow or parallelizing tool calls where possible."
        )

    # Common tool-call patterns (sequences repeated across 3+ traces) -- this was
    # previously computed into execution_patterns["tool_call_patterns"] but never
    # actually read here, so the recommendation never printed.
    tool_call_patterns = execution_patterns.get("tool_call_patterns", {})
    for combo, count in sorted(tool_call_patterns.items(), key=lambda x: x[1], reverse=True)[:3]:
        if count >= 3:
            recommendations.append(
                f"📊 Common tool pattern: {combo} (seen {count}x). "
                "Consider guiding this workflow explicitly in the system prompt."
            )

    # Empty results -- a trace that completes without error but returns a
    # blank aw_agent.output is invisible to error-rate analysis above.
    empty_result_traces = analysis.get("empty_result_traces", 0)
    if empty_result_traces > 0:
        recommendations.append(
            f"{empty_result_traces} trace(s) completed successfully but returned "
            "an empty result. Review the system prompt for cases where the agent "
            "has nothing to say, or check for a tool result the agent isn't using."
        )

    # Cost -- surfaced per-invocation since a single expensive trace can hide
    # inside a low average across many cheap ones.
    avg_cost_cents = analysis.get("avg_cost_cents", 0)
    if avg_cost_cents > 0:
        recommendations.append(
            f"Average cost per invocation: {avg_cost_cents / 100:.2f} credits "
            f"(total: {analysis.get('total_cost_cents', 0) / 100:.2f} credits across "
            f"{total_traces} traces)."
        )

    if not recommendations:
        recommendations.append("✅ No major issues detected. Agent is performing well.")

    return recommendations


# Longest prompt/input text kept per entry in --json output.
JSON_TEXT_LIMIT = 500


def _slim_for_json(analysis: dict) -> dict:
    """Copy of the analysis without the raw span payloads the text report never shows.

    error_contexts keeps the trace, tool and input but drops the full span attributes, and
    long input text is truncated, so --json stays small and doesn't dump prompts and tool
    payloads wholesale.
    """
    slim = dict(analysis)
    patterns = dict(analysis.get("execution_patterns") or {})

    def clip(value):
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        return text if len(text) <= JSON_TEXT_LIMIT else text[:JSON_TEXT_LIMIT] + "...(truncated)"

    patterns["error_contexts"] = [
        {**{k: v for k, v in ctx.items() if k != "attributes"}, "input": clip(ctx.get("input"))}
        for ctx in patterns.get("error_contexts", [])
    ]
    patterns["input_patterns"] = [
        {**item, "input": clip(item.get("input"))} for item in patterns.get("input_patterns", [])
    ]
    slim["execution_patterns"] = patterns
    return slim


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze agent execution patterns and suggest improvements",
        epilog="Queries spans by agent_id, analyzes tool usage and errors, generates recommendations"
    )
    parser.add_argument("--agent-id", required=True,
                       help="Agent ID to analyze")
    parser.add_argument("--days", type=int, default=1,
                       help="Number of days to analyze (default: 1, max: 90). Ignored "
                            "when --invocation-ids is given (that scopes by invocation, "
                            "not by window).")
    parser.add_argument("--invocation-ids", nargs="+", default=None,
                       help="Scope analysis to these specific invocation IDs instead of "
                            "every trace under --agent-id in the --days window. Use this "
                            "for a before/after comparison across agent versions -- "
                            "re-analyzing by --agent-id alone always merges every "
                            "version's traces back together.")
    parser.add_argument("--verbose", action="store_true",
                       help="Show detailed per-tool metrics")
    parser.add_argument("--json", action="store_true",
                       help="Output raw JSON analysis")
    args = parser.parse_args()

    # Validate days
    if args.days < 1 or args.days > 90:
        print("ERROR: --days must be between 1 and 90", file=sys.stderr)
        sys.exit(1)

    # Step 1: Get agent details
    try:
        agent_response = call_native(get_agents_client().get_studio_agents, ids=args.agent_id)
        agent_details = agent_response.get("resources", [{}])[0] if agent_response.get("resources") else None
    except RuntimeError as exc:
        # Keep going without the agent's configured-tools context, but say so: a 401/403
        # (expired token, missing scope) would otherwise make the recommendations look complete.
        print(f"WARNING: could not fetch agent details ({exc}); recommendations that depend on "
              "the configured tools will be skipped.", file=sys.stderr)
        agent_details = None

    # Step 2: Query spans
    if args.invocation_ids:
        print(f"Analyzing {len(args.invocation_ids)} invocation(s) for agent "
              f"{args.agent_id}...\n", file=sys.stderr)
        print("Querying spans...", file=sys.stderr)
        span_ids, known_spans = query_invocation_spans(args.invocation_ids)
    else:
        print(f"Analyzing agent {args.agent_id} (last {args.days} day(s))...\n", file=sys.stderr)
        print("Querying spans...", file=sys.stderr)
        agent_name = ((agent_details or {}).get("active_version") or {}).get("name")
        span_ids, known_spans = query_agent_spans(args.agent_id, args.days, agent_name)

    if not span_ids:
        if args.invocation_ids:
            print("No spans found for the given invocation ID(s).", file=sys.stderr)
        else:
            print(f"No spans found for agent {args.agent_id} in the last {args.days} day(s).", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(span_ids)} spans\n", file=sys.stderr)

    # Step 3: Hydrate spans
    print("Hydrating spans...", file=sys.stderr)
    known_ids = {s.get("id") for s in known_spans}
    spans = known_spans + hydrate_spans([i for i in span_ids if i not in known_ids])

    if not spans:
        print("ERROR: Could not hydrate spans", file=sys.stderr)
        sys.exit(1)

    print(f"Hydrated {len(spans)} spans\n", file=sys.stderr)

    # Step 4: Analyze
    analysis = analyze_spans(spans)

    # JSON output
    if args.json:
        print(json.dumps({
            "agent_id": args.agent_id,
            "analysis_window_days": args.days,
            "analysis": _slim_for_json(analysis)
        }, indent=2))
        return

    # Human-readable output
    print("=" * 60)
    print(f"Agent Analysis: {args.agent_id}")
    if agent_details:
        active_version = agent_details.get("active_version") or {}
        print(f"Name: {active_version.get('name', '(unnamed)')}")
    print("=" * 60)
    print()

    print(f"📊 Summary")
    print(f"  Traces analyzed: {analysis['total_traces']}")
    print(f"  Total spans: {analysis['total_spans']}")
    print(f"  Unique invocations: {len(analysis['invocation_ids'])}")
    print()

    print(f"✅ Trace Status")
    for status, count in analysis["trace_statuses"].items():
        pct = count / analysis["total_traces"] * 100 if analysis["total_traces"] > 0 else 0
        print(f"  {status}: {count} ({pct:.1f}%)")
    empty_result_traces = analysis.get("empty_result_traces", 0)
    if empty_result_traces > 0:
        print(f"  empty result: {empty_result_traces}")
    print()

    print("Cost")
    print(f"  Total: {analysis.get('total_cost_cents', 0) / 100:.2f} credits")
    print(f"  Average per invocation: {analysis.get('avg_cost_cents', 0) / 100:.2f} credits")
    print()

    # Version analysis
    by_version = analysis.get("by_version", {})
    if len(by_version) > 1:
        print(f"🔄 Multiple Versions Detected ({len(by_version)} versions)")
        print()

        # Order versions by when each was first seen (oldest first). Traces arrive
        # newest-first, so traces[0] is a version's LAST trace, not its first.
        versions = sorted(
            by_version.items(),
            key=lambda x: min((_ts_ms(t["start_time"]) for t in x[1]["traces"]), default=float("inf")),
        )
        for i, (version_sig, version_data) in enumerate(versions, 1):
            definition = version_data["definition"]
            traces = version_data["traces"]
            durations = version_data["durations"]
            errors = version_data["errors"]

            avg_duration = sum(durations) / len(durations) if durations else 0
            min_duration = min(durations) if durations else 0
            max_duration = max(durations) if durations else 0

            print(f"  Version {i}:")
            print(f"    Model: {definition.get('model', 'N/A')}")
            print(f"    Tools: {len(definition.get('tools') or [])} tool(s)")
            print(f"    Temperature: {definition.get('model_config', {}).get('temperature', 'N/A')}")
            print(f"    Max tokens: {definition.get('model_config', {}).get('max_tokens', 'N/A')}")
            print(f"    Traces: {len(traces)} ({errors} errors)")
            print(f"    Avg duration: {humanize_duration(avg_duration)} (min: {humanize_duration(min_duration)}, max: {humanize_duration(max_duration)})")

            if traces:
                trace_starts = [t["start_time"] for t in traces if t["start_time"]]
                first_seen = min(trace_starts, key=_ts_ms) if trace_starts else None
                last_seen = max(trace_starts, key=_ts_ms) if trace_starts else None
                print(f"    First seen: {first_seen}")
                if len(traces) > 1:
                    print(f"    Last seen: {last_seen}")
            print()

        # Performance comparison
        if len(by_version) == 2:
            v1_durations = versions[0][1]["durations"]
            v2_durations = versions[1][1]["durations"]

            if v1_durations and v2_durations:
                v1_avg = sum(v1_durations) / len(v1_durations)
                v2_avg = sum(v2_durations) / len(v2_durations)
                ratio = v2_avg / v1_avg if v1_avg > 0 else 0

                if ratio > 2 or ratio < 0.5:
                    factor = ratio if ratio > 1 else (1 / ratio if ratio > 0 else 0)
                    print(f"  ⚠️ Performance Changed: Version 2 is {factor:.1f}x {'slower' if ratio > 1 else 'faster'} than Version 1")
                    print(f"     Version 1 avg: {humanize_duration(v1_avg)}")
                    print(f"     Version 2 avg: {humanize_duration(v2_avg)}")
                    print()

                    # Show what changed
                    def1 = versions[0][1]["definition"]
                    def2 = versions[1][1]["definition"]

                    changes = []
                    if def1.get("model") != def2.get("model"):
                        changes.append(f"Model: {def1.get('model')} → {def2.get('model')}")
                    if len(def1.get("tools") or []) != len(def2.get("tools") or []):
                        changes.append(f"Tools: {len(def1.get('tools') or [])} → {len(def2.get('tools') or [])}")
                    if def1.get("model_config", {}).get("temperature") != def2.get("model_config", {}).get("temperature"):
                        changes.append(f"Temperature: {def1.get('model_config', {}).get('temperature')} → {def2.get('model_config', {}).get('temperature')}")

                    if changes:
                        print("     Changes detected:")
                        for change in changes:
                            print(f"       - {change}")
                        print()

    elif len(by_version) == 1:
        print(f"✅ Single Version (consistent configuration)")
        print()

    print(f"⏱️ Invocation Duration")
    avg = humanize_duration(analysis["trace_durations"]["avg_ms"])
    max_d = humanize_duration(analysis["trace_durations"]["max_ms"])
    print(f"  Average: {avg}")
    print(f"  Max: {max_d}")
    print()

    if analysis["tool_usage"]:
        print(f"🔧 Tool Usage (top 10)")
        for tool, count in sorted(analysis["tool_usage"].items(),
                                   key=lambda x: x[1], reverse=True)[:10]:
            error_count = analysis["tool_errors"].get(tool, 0)
            error_str = f" ({error_count} errors)" if error_count > 0 else ""
            print(f"  {tool}: {count}{error_str}")

            if args.verbose and tool in analysis["tool_durations"]:
                dur = analysis["tool_durations"][tool]
                avg = humanize_duration(dur["avg_ms"])
                max_d = humanize_duration(dur["max_ms"])
                print(f"    Duration: avg {avg}, max {max_d}")
        print()

    # Generate recommendations
    recommendations = generate_recommendations(analysis, agent_details, analysis["execution_patterns"])

    print("💡 Recommendations")
    for i, rec in enumerate(recommendations, 1):
        # Multi-line recommendations should be indented properly
        lines = rec.split('\n')
        print(f"{i}. {lines[0]}")
        for line in lines[1:]:
            print(f"   {line}")
    print()

    # Show sample invocation IDs
    if analysis["invocation_ids"] and not args.json:
        print("📋 Sample Invocation IDs (for deep-dive with inspect_invocation.py):")
        for inv_id in list(analysis["invocation_ids"])[:5]:
            print(f"  {inv_id}")
        if len(analysis["invocation_ids"]) > 5:
            print(f"  ... and {len(analysis['invocation_ids']) - 5} more")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native/hydrate_spans raise RuntimeError on HTTP errors and failed batches.
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
