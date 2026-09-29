#!/usr/bin/env python3
"""
kb_search.py - Query Charlotte AI AgentWorks knowledge base IDs by FQL filter.

Uses the native FalconPy KnowledgeBases.QueriesKnowledgeBasesV1 method.
Returns a list of KB IDs matching the filter.

IMPORTANT: FQL string values must be single-quoted (`name:'my-kb'`). Double quotes
(`name:"my-kb"`) are NOT valid FQL -- the API accepts the request (200 OK) but silently
returns zero results, with no error to signal the syntax is wrong. For substring/"contains"
matching, use a wildcard: `name:*'*my-kb*'`. See references/fql-filters.md for confirmed
examples. If you don't already know the exact name to search for, use kb_list.py instead,
which does client-side substring filtering across all KBs.

Examples:
    python kb_search.py --filter "name:'my-kb'"
    python kb_search.py --filter "name:*'*my-kb*'"          # substring match
    python kb_search.py --filter "created_at:>'2026-01-01T00:00:00Z'" --limit 50
    python kb_search.py --json  # raw JSON output
"""

import argparse
import json
import sys
import os

# Import shared auth module (3 levels up)
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import call_native, get_kb_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Query knowledge base IDs by FQL filter")
    parser.add_argument("--filter", help="FQL filter, single-quoted values, e.g. name:'my-kb' or name:*'*substring*'", default="")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default 100)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    client = get_kb_client()

    params = {"limit": args.limit, "offset": args.offset}
    if args.filter:
        params["filter"] = args.filter

    body = call_native(client.QueriesKnowledgeBasesV1, parameters=params)

    if args.json:
        print(json.dumps(body, indent=2))
        return

    resources = body.get("resources", [])
    total = body.get("meta", {}).get("pagination", {}).get("total", len(resources))

    if not resources:
        print("No knowledge bases found matching filter.")
        return

    print(f"Found {len(resources)} KB ID(s) (total: {total}):")
    for kb_id in resources:
        print(f"  {kb_id}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
