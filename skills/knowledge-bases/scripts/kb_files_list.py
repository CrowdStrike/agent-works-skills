#!/usr/bin/env python3
"""
kb_files_list.py - List files in a Charlotte AI AgentWorks knowledge base as a table.

Uses the native FalconPy KnowledgeBaseFiles.QueriesKnowledgeBaseFilesV1 (list file IDs)
and EntitiesKnowledgeBaseFilesV1 (hydrate) methods.

IMPORTANT: EntitiesKnowledgeBaseFilesV1 requires `knowledge_base_id` as a parameter
alongside `ids` -- passing `ids` alone fails with "knowledge_base_id parameter is
required" (confirmed 2026-09-21, live tenant; matches what the Falcon UI itself sends,
per its network requests to GET .../entities/knowledge_base_files/v1?ids=...&knowledge_base_id=...
and GET .../queries/knowledge_base_files/v1?limit=...&offset=...&knowledge_base_id=...).

There was previously no script for this at all -- kb_search.py has no --kb-id flag
despite SKILL.md's Core Workflow claiming `kb_search.py --kb-id <id>` lists files in a
KB. This script is the actual implementation of that workflow step.

Examples:
    python kb_files_list.py --kb-id <uuid>
    python kb_files_list.py --kb-id <uuid> --name-contains "email"
    python kb_files_list.py --kb-id <uuid> --json
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
from auth import call_native, get_kb_files_client
from formatting import format_modified_by, format_timestamp


def fetch_all_file_ids(client, kb_id):
    all_ids = []
    offset, limit = 0, 100
    while True:
        body = call_native(client.QueriesKnowledgeBaseFilesV1, parameters={
            "knowledge_base_id": kb_id, "limit": limit, "offset": offset,
        })
        ids = body.get("resources") or []
        if not ids:
            break
        all_ids.extend(ids)
        total = body.get("meta", {}).get("pagination", {}).get("total", 0)
        offset += limit
        if offset >= total:
            break
    return all_ids


def fetch_file_entities(client, kb_id, ids):
    entities = []
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        # knowledge_base_id is required here, not just ids -- see module docstring
        body = call_native(client.EntitiesKnowledgeBaseFilesV1, knowledge_base_id=kb_id, ids=batch)
        entities.extend(body.get("resources") or [])
    return entities


def main() -> None:
    parser = argparse.ArgumentParser(description="List files in a knowledge base as a table")
    parser.add_argument("--kb-id", required=True, help="Knowledge base ID")
    parser.add_argument("--name-contains", help="Case-insensitive substring filter on file name")
    parser.add_argument("--json", action="store_true", help="Output raw JSON rows instead of a table")
    args = parser.parse_args()

    client = get_kb_files_client()
    ids = fetch_all_file_ids(client, args.kb_id)

    if not ids:
        if args.json:
            print(json.dumps({"total_matched": 0, "rows": []}, indent=2))
        else:
            print("No files found in this knowledge base.")
        return

    entities = fetch_file_entities(client, args.kb_id, ids)

    rows = []
    for f in entities:
        name = f.get("name", "")
        if args.name_contains and args.name_contains.lower() not in name.lower():
            continue
        rows.append({
            "id": f.get("id"),
            "name": name,
            "description": (f.get("metadata") or {}).get("description", ""),
            "size": f.get("size", 0),
            "content_type": f.get("content_type", ""),
            "status": f.get("status", ""),
            "updated_at": f.get("updated_at", ""),
            "updated_by": format_modified_by(f.get("updated_by")),
        })

    rows.sort(key=lambda r: r["updated_at"] or "", reverse=True)

    if args.json:
        print(json.dumps({"total_matched": len(rows), "rows": rows}, indent=2))
        return

    if not rows:
        print("No files found matching filters.")
        return

    print("| Name | Description | Size | Type | Status | Last modified | Modified by | ID |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        desc = r["description"] or ""
        if len(desc) > 60:
            desc = desc[:60] + "..."
        print(f"| {r['name']} | {desc} | {r['size']} | {r['content_type']} | {r['status']} | "
              f"{format_timestamp(r['updated_at'])} | {r['updated_by']} | {r['id']} |")

    print()
    print(f"{len(rows)} file(s) in KB {args.kb_id}.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
