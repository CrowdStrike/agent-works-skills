#!/usr/bin/env python3
"""
kb_upsert.py - Create or update a Charlotte AI AgentWorks knowledge base.

Uses native FalconPy KnowledgeBases.EntitiesKnowledgeBasesCreateV1 (create)
or EntitiesKnowledgeBasesUpdateV1 (update if --id provided).

Examples:
    python kb_upsert.py --name "My KB" --description "Test KB"  # create
    python kb_upsert.py --id <uuid> --description "Updated desc"  # update
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
    parser = argparse.ArgumentParser(description="Create or update a knowledge base")
    parser.add_argument("--id", help="KB ID (for update; omit to create new)")
    parser.add_argument("--name", help="KB name (required for create)")
    parser.add_argument("--description", help="KB description")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not args.id and not args.name:
        print("ERROR: --name is required when creating a new KB", file=sys.stderr)
        sys.exit(1)

    client = get_kb_client()

    body = {}
    if args.id:
        body["id"] = args.id
    if args.name:
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description

    if args.id:
        # Update. The API replaces the KB, and requires a name on every update, so carry over
        # whichever of name/description the user didn't pass instead of blanking or failing.
        if not args.name or args.description is None:
            existing = call_native(client.EntitiesKnowledgeBasesV1, ids=[args.id]).get("resources", [])
            if not existing:
                print(f"ERROR: knowledge base {args.id} not found", file=sys.stderr)
                sys.exit(1)
            if not args.name:
                body["name"] = existing[0].get("name", "")
            if args.description is None:
                body["description"] = existing[0].get("description", "")
        response = call_native(client.EntitiesKnowledgeBasesUpdateV1, body=body)
        operation = "update"
    else:
        # Create
        response = call_native(client.EntitiesKnowledgeBasesCreateV1, body=body)
        operation = "create"

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print(f"KB {operation} succeeded but no resource returned.", file=sys.stderr)
        sys.exit(1)

    kb = resources[0]
    print(f"Knowledge base {operation}d successfully:")
    print(f"  ID: {kb.get('id')}")
    print(f"  Name: {kb.get('name')}")
    print(f"  Description: {kb.get('description', '(none)')}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
