#!/usr/bin/env python3
"""
kb_audit.py - Query Charlotte AI AgentWorks knowledge base audit events.

Uses native FalconPy KnowledgeBaseAuditEvents.CombinedKnowledgeBaseAuditEventsV1.

Examples:
    python kb_audit.py --kb-id <uuid> --limit 50
    python kb_audit.py --kb-id <uuid> --filter 'operation_type:"CREATE"' --json
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
from auth import call_native, get_kb_audit_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Query knowledge base audit events")
    parser.add_argument("--kb-id", required=True, help="Knowledge base ID")
    parser.add_argument("--filter", default="", help='FQL filter, e.g. operation_type:"CREATE"')
    parser.add_argument("--limit", type=int, default=100, help="Max results (default 100)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    client = get_kb_audit_client()

    params = {
        "knowledge_base_id": args.kb_id,
        "limit": args.limit,
        "offset": args.offset,
    }
    if args.filter:
        params["filter"] = args.filter

    body = call_native(client.CombinedKnowledgeBaseAuditEventsV1, parameters=params)

    if args.json:
        print(json.dumps(body, indent=2))
        return

    resources = body.get("resources", [])
    total = body.get("meta", {}).get("pagination", {}).get("total", len(resources))

    if not resources:
        print("No audit events found.")
        return

    print(f"Found {len(resources)} audit event(s) (total: {total}):\n")
    for event in resources:
        print(f"Event ID: {event.get('id')}")
        print(f"  Operation: {event.get('operation_type')}")
        print(f"  User: {event.get('user_uuid', 'N/A')}")
        print(f"  Timestamp: {event.get('timestamp')}")
        print(f"  Details: {event.get('details', {})}")
        print()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
