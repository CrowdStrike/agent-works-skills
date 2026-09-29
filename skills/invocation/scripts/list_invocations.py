#!/usr/bin/env python3
"""
list_invocations.py - List recent invocations for an agent.

Finds an agent's invocations from its root spans (matched by aw_agent.id, and by
aw_agent.definition.name for inline/programmatic runs that carry no agent ID), then reads
each selected invocation's full trace for its status, span count and duration.

Examples:
    # List last 10 invocations
    python list_invocations.py --agent-id <uuid>

    # List last 50 invocations from past 7 days
    python list_invocations.py --agent-id <uuid> --limit 50 --days 7

    # JSON output for piping to other tools
    python list_invocations.py --agent-id <uuid> --json
"""

import argparse
import json
import sys
import os
from collections import defaultdict
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
from discovery_helpers import hydrate_spans, query_span_ids
from formatting import format_timestamp, humanize_duration

# ISO-style layout for the per-invocation listing (tables elsewhere use formatting's default).
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# Root (agent-level) spans carry the invocation metadata; child spans (LLM, tool, KB) do not.
ROOT_SPAN_TYPES = "span_type:['aw_agent','aw_eval_run_started']"

# Traces whose full span set is fetched per query when computing per-invocation stats.
TRACE_BATCH = 20

# Cap on spans read back per batch of traces; a batch that hits it is re-fetched trace by trace.
MAX_SPANS_PER_BATCH = 5000

# Cap on spans read back for a single trace.
MAX_SPANS_PER_TRACE = 5000


def _fq(value: str) -> str:
    """Escape a value for use inside a single-quoted FQL string."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def query_agent_root_spans(agent_id: str, agent_name: str | None, days: int, limit: int) -> list[str]:
    """Query root-span IDs for an agent within the time window (FQL syntax).

    Two queries, merged: by aw_agent.id (UI-triggered runs), and by aw_agent.definition.name
    (inline/programmatic runs, which carry no aw_agent.id). Same-named spans that belong to a
    different agent ID are dropped after hydration by extract_invocations. Results are newest
    first and capped near `limit` invocations (an invocation has one or two root spans).
    """
    window = f"start_time:>='now-{days}d'"
    max_results = min(1000, max(50, limit * 4))

    filters = [f"(attributes.aw_agent.id:'{_fq(agent_id)}'+{window})+{ROOT_SPAN_TYPES}"]
    if agent_name:
        filters.append(
            f"(attributes.aw_agent.definition.name:'{_fq(agent_name)}'+{window})+{ROOT_SPAN_TYPES}"
        )

    span_ids: list[str] = []
    for filter_expr in filters:
        print(f"Querying: {filter_expr}", file=sys.stderr)
        span_ids.extend(query_span_ids(filter_expr, max_results=max_results))
    return list(dict.fromkeys(span_ids))  # dedupe, keep order


def _trace_stats(trace_spans: list[dict]) -> dict:
    """Start/end/duration, error status and span count for one trace's spans."""
    starts = [s.get("start_time") for s in trace_spans if s.get("start_time")]
    ends = [s.get("end_time") for s in trace_spans if s.get("end_time")]

    start_time = end_time = duration_ms = None
    if starts and ends:
        try:
            start_ms = min(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000
                           for t in starts)
            end_ms = max(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000
                         for t in ends)
            duration_ms = end_ms - start_ms
            start_time, end_time = min(starts), max(ends)
        except ValueError:
            pass

    has_error = any(
        s.get("status") == "error" or (s.get("attributes") or {}).get("tool.result_is_error") is True
        for s in trace_spans
    )
    return {
        "start_time": start_time,
        "end_time": end_time,
        "duration_ms": duration_ms,
        "status": "error" if has_error else "success",
        "span_count": len(trace_spans),
    }


def extract_invocations(
    spans: list[dict],
    target_agent_id: str | None = None,
    target_agent_name: str | None = None,
) -> list[dict]:
    """Extract invocation metadata from root spans grouped by trace_id.

    Args:
        spans: Hydrated root spans
        target_agent_id: If provided, keep only this agent's invocations
        target_agent_name: Agent name, used to match inline invocations, which carry no
            aw_agent.id but do carry aw_agent.definition.name
    """
    by_trace = defaultdict(list)
    for span in spans:
        trace_id = span.get("trace_id")
        if trace_id:
            by_trace[trace_id].append(span)

    invocations = []
    for trace_id, trace_spans in by_trace.items():
        invocation_id = agent_id = agent_name = None
        inline = False
        for span in trace_spans:
            attrs = span.get("attributes") or {}
            # Attributes are FLAT with dotted keys, not nested dicts:
            # - aw_agent.id (only on UI-triggered invocations)
            # - aw_agent.inline_invocation (boolean, true for inline/programmatic runs)
            # - aw_agent.definition.name (present on inline runs too)
            # - aw_agent.invocation_id
            invocation_id = invocation_id or attrs.get("aw_agent.invocation_id")
            agent_id = agent_id or attrs.get("aw_agent.id")
            agent_name = agent_name or attrs.get("aw_agent.definition.name")
            inline = inline or attrs.get("aw_agent.inline_invocation") is True

        if not invocation_id:
            continue
        if target_agent_id and agent_id != target_agent_id:
            # Inline invocations have no aw_agent.id; match them by definition name.
            if agent_id or not target_agent_name or agent_name != target_agent_name:
                continue

        invocations.append({
            "invocation_id": invocation_id,
            "agent_id": agent_id or target_agent_id,
            "inline": inline,
            "trace_id": trace_id,
            **_trace_stats(trace_spans),
        })

    invocations.sort(key=lambda x: x.get("start_time") or "", reverse=True)  # newest first
    return invocations


def enrich_from_full_traces(invocations: list[dict]) -> None:
    """Recompute status, span count and duration from each invocation's full trace, in place.

    The root spans alone miss failed tool/LLM child spans, so an invocation whose tools all
    errored would otherwise be reported as a success.
    """
    for i in range(0, len(invocations), TRACE_BATCH):
        batch = invocations[i:i + TRACE_BATCH]
        trace_list = ",".join(f"'{_fq(inv['trace_id'])}'" for inv in batch)
        span_ids = query_span_ids(
            f"(trace_id:[{trace_list}]+start_time:>='now-90d')", max_results=MAX_SPANS_PER_BATCH
        )
        if len(span_ids) >= MAX_SPANS_PER_BATCH:
            # Possibly truncated (newest spans win, so the oldest traces would lose their child
            # spans and look like successes): fetch these traces one by one instead.
            span_ids = []
            for inv in batch:
                trace_span_ids = query_span_ids(
                    f"(trace_id:'{_fq(inv['trace_id'])}'+start_time:>='now-90d')",
                    max_results=MAX_SPANS_PER_TRACE,
                )
                if len(trace_span_ids) >= MAX_SPANS_PER_TRACE:
                    print(f"WARNING: trace {inv['trace_id']} has at least {MAX_SPANS_PER_TRACE} "
                          f"spans; status, span count and duration cover only the newest "
                          f"{MAX_SPANS_PER_TRACE}.", file=sys.stderr)
                span_ids += trace_span_ids
        by_trace = defaultdict(list)
        for span in hydrate_spans(span_ids):
            by_trace[span.get("trace_id")].append(span)
        for inv in batch:
            if by_trace.get(inv["trace_id"]):
                inv.update(_trace_stats(by_trace[inv["trace_id"]]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List recent invocations for an agent",
        epilog="Finds invocations from root spans, then reads each full trace for status and duration"
    )
    parser.add_argument("--agent-id", required=True,
                       help="Agent ID to list invocations for")
    parser.add_argument("--limit", type=int, default=10,
                       help="Maximum number of invocations to show (default: 10)")
    parser.add_argument("--days", type=int, default=1,
                       help="Number of days to search (default: 1, max: 90)")
    parser.add_argument("--json", action="store_true",
                       help="Output raw JSON")
    args = parser.parse_args()

    if args.days < 1 or args.days > 90:
        print("ERROR: --days must be between 1 and 90", file=sys.stderr)
        sys.exit(1)

    if args.limit < 1:
        print("ERROR: --limit must be >= 1", file=sys.stderr)
        sys.exit(1)

    print(f"Querying invocations for agent {args.agent_id} (last {args.days} day(s))...\n",
          file=sys.stderr)

    # Resolve the agent's name so inline invocations (no aw_agent.id) can be matched.
    agent_name = None
    try:
        agent_response = call_native(get_agents_client().get_studio_agents, ids=args.agent_id)
        resources = agent_response.get("resources") or [{}]
        # The display name lives under active_version, not on the agent entity itself.
        agent_name = (resources[0].get("active_version") or {}).get("name")
    except RuntimeError as e:
        print(f"WARNING: could not look up agent name ({e}); inline invocations "
              "will not be matched.", file=sys.stderr)

    span_ids = query_agent_root_spans(args.agent_id, agent_name, args.days, args.limit)
    invocations = []
    if span_ids:
        spans = hydrate_spans(span_ids)
        invocations = extract_invocations(
            spans, target_agent_id=args.agent_id, target_agent_name=agent_name
        )[:args.limit]
        enrich_from_full_traces(invocations)

    if not invocations:
        print(f"No invocations found for agent {args.agent_id} in the last {args.days} day(s).",
              file=sys.stderr)
        if args.json:
            print(json.dumps({"agent_id": args.agent_id, "invocations": []}, indent=2))
        return

    if args.json:
        print(json.dumps({
            "agent_id": args.agent_id,
            "invocations": invocations
        }, indent=2))
        return

    print(f"Found {len(invocations)} invocation(s):\n")

    for i, inv in enumerate(invocations, 1):
        status_icon = "❌" if inv["status"] == "error" else "✅"
        inline_tag = " (inline, matched by agent name)" if inv["inline"] else ""
        start = format_timestamp(inv["start_time"], fmt=TIMESTAMP_FORMAT, empty="—")
        print(f"{i}. {status_icon} Invocation: {inv['invocation_id']}{inline_tag}")
        print(f"   Trace ID: {inv['trace_id'][:16]}...")
        print(f"   Started: {start}")
        print(f"   Duration: {humanize_duration(inv['duration_ms'])}")
        print(f"   Spans: {inv['span_count']}")
        print()

    print("To inspect a specific invocation:")
    print("  cd ../invocation")
    print("  ../../scripts/python.sh scripts/inspect_invocation.py \\")
    print("    --invocation-id <invocation-id>")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native/hydrate_spans raise RuntimeError on HTTP errors and failed batches.
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
