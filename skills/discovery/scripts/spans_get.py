#!/usr/bin/env python3
"""
spans_get.py - Fetch full trace span entities by their IDs.

Uses the native FalconPy Spans.entities_spans_v1 method via hydrate_spans().

Examples:
    python spans_get.py --ids <span-id-1> <span-id-2>
    python spans_get.py --ids $(python spans_search.py --filter 'trace_id:"..."' | grep -oE '[0-9a-f-]{36}' | head -5 | tr '\\n' ' ')
"""

import argparse
import json
import sys
import os

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from discovery_helpers import hydrate_spans


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch full span entities by IDs",
        epilog="Get span IDs from spans_search.py. Uses automatic batching for large ID lists."
    )
    parser.add_argument("--ids", nargs="+", required=True,
                       help="Span IDs (space-separated UUIDs)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--batch-size", type=int, default=50,
                       help="Batch size for hydration (default: 50)")
    args = parser.parse_args()

    # Hydrate spans with automatic batching
    print(f"Hydrating {len(args.ids)} span(s) in batches of {args.batch_size}...", file=sys.stderr)
    spans = hydrate_spans(args.ids, batch_size=args.batch_size)

    if args.json:
        print(json.dumps({"resources": spans}, indent=2))
        return

    if not spans:
        print(f"No spans found for {len(args.ids)} ID(s).", file=sys.stderr)
        return

    print(f"Found {len(spans)} span(s):\n")

    for span in spans:
        span_id = span.get("span_id", span.get("id", ""))
        name = span.get("name", "(unnamed)")
        span_type = span.get("span_type", "")
        duration_ms = span.get("duration_ms")
        status = span.get("status", "")
        trace_id = span.get("trace_id", "")

        # Humanize duration
        if duration_ms is not None:
            if duration_ms >= 60000:
                m = duration_ms // 60000
                s = (duration_ms % 60000) // 1000
                dur_str = f"{m}m{s:02d}s"
            elif duration_ms >= 1000:
                dur_str = f"{duration_ms / 1000:.1f}s"
            else:
                dur_str = f"{duration_ms}ms"
        else:
            dur_str = "—"

        error_mark = "  ⚠ error" if status == "error" else ""

        print(f"Span: {name}")
        print(f"  ID: {span_id}")
        print(f"  Type: {span_type}")
        print(f"  Duration: {dur_str}{error_mark}")
        print(f"  Status: {status}")
        print(f"  Trace ID: {trace_id[:8]}...")

        # Show cost if available
        attrs = span.get("attributes", {})
        if "cost.raw_credit_cents" in attrs:
            cents = attrs["cost.raw_credit_cents"]
            credits = cents / 100 if isinstance(cents, (int, float)) else 0
            print(f"  Credits: {credits:.2f}")

        print()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native/hydrate_spans raise RuntimeError on HTTP errors and failed batches.
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
