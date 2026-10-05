#!/usr/bin/env python3
"""
kb_get.py - Get Charlotte AI AgentWorks knowledge base entities by IDs.

Uses the native FalconPy KnowledgeBases.EntitiesKnowledgeBasesV1 method.
Returns full KB details for the given IDs.

Examples:
    python kb_get.py --ids <uuid1> <uuid2>
    python kb_get.py --ids <uuid> --json
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
from auth import call_native, get_kb_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Get knowledge base entities by IDs")
    parser.add_argument("--ids", nargs="+", required=True, help="KB IDs to retrieve")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    client = get_kb_client()

    body = call_native(client.EntitiesKnowledgeBasesV1, ids=args.ids)

    if args.json:
        print(json.dumps(body, indent=2))
        return

    resources = body.get("resources", [])

    if not resources:
        print("No knowledge bases found for given IDs.")
        return

    print(f"Retrieved {len(resources)} knowledge base(s):\n")
    for kb in resources:
        print(f"ID: {kb.get('id')}")
        print(f"  Name: {kb.get('name')}")
        print(f"  Description: {kb.get('description', '(none)')}")
        print(f"  Created: {kb.get('created_at')}")
        print(f"  Updated: {kb.get('updated_at')}")
        print(f"  File count: {kb.get('files_count', 0)}")
        print()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
