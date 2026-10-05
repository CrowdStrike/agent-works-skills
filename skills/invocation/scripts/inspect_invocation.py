#!/usr/bin/env python3
"""
inspect_invocation.py - Inspect invocation traces with waterfall visualization and tool outputs.

Resolves invocation_id → trace_id → full span tree, renders waterfall, and shows tool outputs.

Examples:
    # Full trace inspection (waterfall + duration + tool outputs)
    python inspect_invocation.py --invocation-id <uuid>

    # Just show tool outputs
    python inspect_invocation.py --invocation-id <uuid> --tool-output-only

    # Only show tool spans that errored
    python inspect_invocation.py --invocation-id <uuid> --errors-only

    # Raw JSON
    python inspect_invocation.py --invocation-id <uuid> --json
"""

import argparse
import json
import sys
import os
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
from waterfall import parse_ms, render_waterfall
from discovery_helpers import TOOL_RESPONSE_SPAN_TYPE, hydrate_spans, query_span_ids
from formatting import humanize_duration


# Look-back window for span queries, matching the 90-day retention the other scripts assume.
SPAN_WINDOW = "now-90d"

# Upper bound on spans fetched for one trace (paginated 500 at a time).
MAX_TRACE_SPANS = 5000


def resolve_trace_id(invocation_id: str) -> str | None:
    """Resolve invocation_id to trace_id by querying agent-level spans.

    The aw_agent/aw_agent_response spans carry attributes.aw_agent.invocation_id;
    granular child spans (LLM, tool, KB) only share the trace_id. API errors propagate
    (RuntimeError) instead of being reported as "not found".
    """
    # Attributes are flat: aw_agent.invocation_id (not nested)
    # Escape single quotes in FQL filter value
    safe_id = invocation_id.replace("'", "\\'")
    filter_expr = f"(attributes.aw_agent.invocation_id:'{safe_id}'+start_time:>='{SPAN_WINDOW}')"
    span_ids = query_span_ids(filter_expr, max_results=5)
    if not span_ids:
        return None

    # Hydrate the first few spans to read trace_id
    for span in hydrate_spans(span_ids[:3]):
        trace_id = span.get("trace_id")
        if trace_id:
            return trace_id
    return None


def fetch_full_trace(trace_id: str) -> list[dict]:
    """Fetch all spans for a trace_id (FQL syntax), paginating past the 500-per-page limit.

    API errors propagate (RuntimeError); a trace longer than MAX_TRACE_SPANS is reported on
    stderr rather than silently truncated.
    """
    # Escape single quotes in FQL filter value
    safe_trace = trace_id.replace("'", "\\'")
    filter_expr = f"(trace_id:'{safe_trace}'+start_time:>='{SPAN_WINDOW}')"
    span_ids = query_span_ids(filter_expr, max_results=MAX_TRACE_SPANS, sort="start_time|asc")
    if len(span_ids) >= MAX_TRACE_SPANS:
        print(f"WARNING: trace has at least {MAX_TRACE_SPANS} spans; showing the first "
              f"{MAX_TRACE_SPANS}.", file=sys.stderr)
    return hydrate_spans(span_ids)


def extract_tool_outputs(spans: list[dict]) -> list[dict]:
    """Extract tool call spans with their outputs."""
    tool_spans = []
    for span in spans:
        span_type = span.get("span_type", "")
        # Exact match: a substring check would also match the paired "tool" request
        # span and count every call twice -- see TOOL_RESPONSE_SPAN_TYPE.
        if span_type == TOOL_RESPONSE_SPAN_TYPE:
            tool_spans.append(span)
    return tool_spans


def calculate_total_duration(spans: list[dict]) -> float:
    """Calculate total invocation duration from span timestamps."""
    if not spans:
        return 0.0

    starts = [parse_ms(s.get("start_time")) for s in spans]
    ends = [parse_ms(s.get("end_time")) for s in spans]

    starts_valid = [s for s in starts if s == s]  # Filter NaN
    ends_valid = [e for e in ends if e == e]

    if not starts_valid or not ends_valid:
        return 0.0

    return max(ends_valid) - min(starts_valid)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect invocation traces with waterfall visualization",
        epilog="Shows waterfall tree, total/per-span durations, and raw tool outputs"
    )
    parser.add_argument("--invocation-id", required=True,
                       help="Invocation ID (from invoke_agent.py)")
    parser.add_argument("--tool-output-only", action="store_true",
                       help="Only show tool outputs, skip waterfall")
    parser.add_argument("--errors-only", action="store_true",
                       help="Only show tool spans that errored (status:error or tool.result_is_error)")
    parser.add_argument("--json", action="store_true",
                       help="Output raw JSON spans")
    args = parser.parse_args()

    # Step 1: Resolve invocation_id → trace_id
    print(f"Resolving trace for invocation {args.invocation_id}...", file=sys.stderr)
    trace_id = resolve_trace_id(args.invocation_id)

    if not trace_id:
        print(f"ERROR: Could not resolve trace_id for invocation {args.invocation_id}", file=sys.stderr)
        print("The invocation may be too old (>90 days) or invalid.", file=sys.stderr)
        sys.exit(1)

    print(f"Trace ID: {trace_id[:8]}...\n", file=sys.stderr)

    # Step 2: Fetch full trace
    print("Fetching full trace...", file=sys.stderr)
    spans = fetch_full_trace(trace_id)

    if not spans:
        print(f"ERROR: No spans found for trace {trace_id}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(spans)} spans\n", file=sys.stderr)

    # JSON output
    if args.json:
        print(json.dumps({
            "invocation_id": args.invocation_id,
            "trace_id": trace_id,
            "spans": spans
        }, indent=2))
        return

    # Step 3: Calculate and show duration
    total_ms = calculate_total_duration(spans)
    print(f"Total Invocation Duration: {humanize_duration(total_ms)}\n")

    # Step 4: Show waterfall (unless tool-output-only)
    if not args.tool_output_only:
        print("=== Trace Waterfall ===\n")
        waterfall = render_waterfall(spans)
        print(waterfall)
        print()

    # Step 5: Extract and show tool outputs
    tool_spans = extract_tool_outputs(spans)
    total_tool_spans = len(tool_spans)
    if args.errors_only:
        tool_spans = [
            s for s in tool_spans
            if s.get("status") == "error" or s.get("attributes", {}).get("tool.result_is_error") is True
        ]

    if tool_spans:
        header_suffix = "error tool span(s)" if args.errors_only else "tool spans"
        print(f"=== Tool Outputs ({len(tool_spans)} {header_suffix}) ===\n")
        for i, span in enumerate(tool_spans, 1):
            name = span.get("name", "(unnamed)")
            span_type = span.get("span_type", "")
            duration_ms = span.get("duration_ms")
            attrs = span.get("attributes", {})

            print(f"Tool #{i}: {name}")
            print(f"  Type: {span_type}")
            if duration_ms:
                print(f"  Duration: {humanize_duration(duration_ms)}")

            # Show relevant attributes (raw output, input, etc.)
            if attrs:
                print(f"  Attributes:")
                # Pretty-print JSON attributes
                for key, value in sorted(attrs.items()):
                    # Skip cost/internal attrs, show tool-relevant ones
                    if not key.startswith("cost.") and not key.startswith("_"):
                        val_str = json.dumps(value, indent=4) if isinstance(value, (dict, list)) else str(value)
                        # Limit output length
                        if len(val_str) > 500:
                            val_str = val_str[:500] + "...(truncated)"
                        print(f"    {key}: {val_str}")
            print()
    else:
        if args.errors_only:
            print("=== Tool Outputs (0 error tool span(s)) ===\n")
        else:
            print("No tool spans found in this trace.")
            print("(Tool calls are spans with span_type 'tool_response')\n")

    # Summary
    print("=== Summary ===")
    print(f"Invocation ID: {args.invocation_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Total Spans: {len(spans)}")
    if args.errors_only:
        print(f"Tool Spans: {total_tool_spans} ({len(tool_spans)} errored)")
    else:
        print(f"Tool Spans: {len(tool_spans)}")
    print(f"Total Duration: {humanize_duration(total_ms)}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native/hydrate_spans raise RuntimeError on HTTP errors and failed batches.
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
