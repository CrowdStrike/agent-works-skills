#!/usr/bin/env python3
"""
diagnose_spans.py - Diagnose span field structure and available filters.

Queries a small sample of spans to understand field structure and help debug
filter issues.

Examples:
    # Sample recent spans
    python diagnose_spans.py --sample 5

    # Check specific trace
    python diagnose_spans.py --trace-id <trace-id>

    # Check specific invocation (requires knowing a span ID)
    python diagnose_spans.py --span-id <span-id>
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
from auth import call_native, get_spans_client


def sample_recent_spans(count: int = 5) -> list[dict]:
    """Get a sample of recent spans with minimal filter."""
    # Query with just time filter (FQL syntax)
    filter_expr = "start_time:>='now-24h'"
    params = {"filter": filter_expr, "limit": str(count), "sort": "start_time|desc"}

    try:
        print(f"Querying spans with filter: {filter_expr}", file=sys.stderr)
        response = call_native(get_spans_client().queries_spans_v1, parameters=params)
        span_ids = response.get("resources", [])

        if not span_ids:
            print("No span IDs returned", file=sys.stderr)
            return []

        print(f"Got {len(span_ids)} span IDs, hydrating...", file=sys.stderr)

        # Hydrate using the shared helper
        from discovery_helpers import hydrate_spans
        return hydrate_spans(span_ids[:count])
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return []


def get_span_by_id(span_id: str) -> dict | None:
    """Get a specific span by ID."""
    try:
        from discovery_helpers import hydrate_spans
        spans = hydrate_spans([span_id])
        return spans[0] if spans else None
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return None


def get_spans_by_trace(trace_id: str) -> list[dict]:
    """Get spans for a specific trace."""
    filter_expr = f"trace_id:'{trace_id}'"
    params = {"filter": filter_expr, "limit": "100"}

    try:
        print(f"Querying spans with filter: {filter_expr}", file=sys.stderr)
        response = call_native(get_spans_client().queries_spans_v1, parameters=params)
        span_ids = response.get("resources", [])

        if not span_ids:
            return []

        from discovery_helpers import hydrate_spans
        return hydrate_spans(span_ids)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return []


def analyze_span_structure(spans: list[dict]) -> dict:
    """Analyze span structure to identify available fields."""
    if not spans:
        return {}

    # Get field paths
    all_fields = set()
    attribute_fields = set()

    for span in spans:
        # Top-level fields
        for key in span.keys():
            all_fields.add(key)

        # Attribute fields
        attrs = span.get("attributes", {})
        if attrs:
            for key, value in attrs.items():
                attribute_fields.add(key)
                # Check nested structures
                if isinstance(value, dict):
                    for nested_key in value.keys():
                        attribute_fields.add(f"{key}.{nested_key}")

    return {
        "top_level_fields": sorted(all_fields),
        "attribute_fields": sorted(attribute_fields),
        "sample_span_keys": list(spans[0].keys()) if spans else [],
        "sample_attributes": list(spans[0].get("attributes", {}).keys()) if spans else []
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose span field structure",
        epilog="Helps debug filter issues by showing actual span structure"
    )
    parser.add_argument("--sample", type=int, default=5,
                       help="Number of recent spans to sample (default: 5)")
    parser.add_argument("--trace-id", help="Get spans for specific trace")
    parser.add_argument("--span-id", help="Get specific span by ID")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    spans = []

    if args.span_id:
        print(f"Fetching span {args.span_id}...", file=sys.stderr)
        span = get_span_by_id(args.span_id)
        if span:
            spans = [span]
    elif args.trace_id:
        print(f"Fetching spans for trace {args.trace_id}...", file=sys.stderr)
        spans = get_spans_by_trace(args.trace_id)
    else:
        print(f"Sampling {args.sample} recent spans...", file=sys.stderr)
        spans = sample_recent_spans(args.sample)

    if not spans:
        print("ERROR: No spans retrieved", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Retrieved {len(spans)} span(s)\n", file=sys.stderr)

    if args.json:
        print(json.dumps(spans, indent=2))
        return

    # Analyze structure
    structure = analyze_span_structure(spans)

    print("=" * 60)
    print("SPAN FIELD STRUCTURE")
    print("=" * 60)
    print()

    print("Top-level fields:")
    for field in structure["top_level_fields"]:
        print(f"  - {field}")
    print()

    print("Attribute fields (for filtering):")
    for field in structure["attribute_fields"]:
        print(f"  - attributes.{field}")
    print()

    # Show sample span
    print("=" * 60)
    print("SAMPLE SPAN")
    print("=" * 60)
    print()

    sample = spans[0]
    print(f"Span ID: {sample.get('span_id', 'N/A')}")
    print(f"Name: {sample.get('name', 'N/A')}")
    print(f"Type: {sample.get('span_type', 'N/A')}")
    print(f"Trace ID: {sample.get('trace_id', 'N/A')}")
    print(f"Status: {sample.get('status', 'N/A')}")
    print()

    if sample.get("attributes"):
        print("Attributes:")
        attrs = sample["attributes"]

        # Pretty print nested structure
        def print_dict(d, indent=2):
            for key, value in sorted(d.items()):
                if isinstance(value, dict):
                    print(f"{' ' * indent}{key}:")
                    print_dict(value, indent + 2)
                else:
                    val_str = str(value)
                    if len(val_str) > 60:
                        val_str = val_str[:60] + "..."
                    print(f"{' ' * indent}{key}: {val_str}")

        print_dict(attrs)
        print()

    # Check for agent/invocation fields
    print("=" * 60)
    print("AGENT/INVOCATION DETECTION")
    print("=" * 60)
    print()

    for i, span in enumerate(spans, 1):
        attrs = span.get("attributes", {})

        # Check various possible paths
        agent_id = None
        invocation_id = None

        # Span attributes are FLAT with dotted keys (aw_agent.id, aw_agent.invocation_id), not
        # nested dicts. aw_agent.id is present only on UI-triggered invocations.
        agent_id = attrs.get("aw_agent.id")
        invocation_id = attrs.get("aw_agent.invocation_id")

        # Fall back to a nested aw_agent dict and bare keys, in case the shape ever changes.
        if isinstance(attrs.get("aw_agent"), dict):
            agent_id = agent_id or attrs["aw_agent"].get("id") or attrs["aw_agent"].get("agent_id")
            invocation_id = invocation_id or attrs["aw_agent"].get("invocation_id")
        agent_id = agent_id or attrs.get("agent_id")
        invocation_id = invocation_id or attrs.get("invocation_id")

        if agent_id or invocation_id:
            print(f"Span {i}:")
            if agent_id:
                print(f"  Agent ID: {agent_id}")
            if invocation_id:
                print(f"  Invocation ID: {invocation_id}")
            print()

    print("=" * 60)
    print("RECOMMENDED FILTER PATTERNS")
    print("=" * 60)
    print()

    # Based on what we found, suggest filters
    if any(
        "aw_agent.id" in s.get("attributes", {}) or "aw_agent.invocation_id" in s.get("attributes", {})
        for s in spans
    ):
        print("✓ aw_agent attributes detected (flat dotted keys)")
        print("  Filter by agent id:")
        print("    attributes.aw_agent.id:'<uuid>'")
        print("  Filter by invocation_id:")
        print("    attributes.aw_agent.invocation_id:'<uuid>'")
    else:
        print("⚠ No aw_agent.* attributes found in sample")
        print("  Try broader time-based queries and filter client-side")
        print("  Example: start_time:>='now-24h'")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native/hydrate_spans raise RuntimeError on HTTP errors and failed batches.
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
