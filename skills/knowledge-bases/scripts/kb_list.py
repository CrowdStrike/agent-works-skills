#!/usr/bin/env python3
"""
kb_list.py - List Charlotte AI AgentWorks knowledge bases as a table (Name, Description, Last
modified, File count) -- for browsing/searching by name, not exact-ID lookup.

kb_search.py's `name` filter DOES work server-side, but only with single-quoted FQL
values (`name:'my-kb'`) and only for exact/wildcard matches you already know how to
spell (`name:*'*term*'` for substring). When you don't know the exact name -- e.g.
"find any KB related to X" -- there's no server-side full-text search, so this script
pages through ALL KB IDs, batch-fetches their entities, then filters/sorts/paginates
client-side on name+description substrings. See references/fql-filters.md for the
confirmed-working filter syntax if you already know what to search for.

On a ~350-KB tenant this is ~4 list calls + ~18 batch-get calls; the heavy per-KB JSON
stays inside this script and never hits stdout -- only the compact table rows are printed.

Examples:
    python kb_list.py
    python kb_list.py --name-contains "root access"
    python kb_list.py --contains "privilege escalation"  # matches name OR description
    python kb_list.py --modified-since 2026-09-01
    python kb_list.py --sort name --order asc
    python kb_list.py --limit 50 --json
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
from auth import call_native, get_kb_client
from formatting import format_modified_by, format_timestamp


def fetch_all_ids(client):
    all_ids = []
    offset, limit = 0, 100
    while True:
        body = call_native(client.QueriesKnowledgeBasesV1, parameters={"limit": limit, "offset": offset})
        ids = body.get("resources") or []
        if not ids:
            break
        all_ids.extend(ids)
        total = body.get("meta", {}).get("pagination", {}).get("total", 0)
        offset += limit
        if offset >= total:
            break
    return all_ids


def fetch_entities(client, ids):
    entities = []
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        body = call_native(client.EntitiesKnowledgeBasesV1, ids=batch)
        entities.extend(body.get("resources") or [])
    return entities


def main() -> None:
    parser = argparse.ArgumentParser(description="List Charlotte AI AgentWorks knowledge bases as a table")
    parser.add_argument("--name-contains", help="Case-insensitive substring filter on KB name")
    parser.add_argument("--contains", help="Case-insensitive substring filter on name OR description")
    parser.add_argument("--modified-since", help="ISO date/datetime; only KBs modified on/after this")
    parser.add_argument("--modified-before", help="ISO date/datetime; only KBs modified before this")
    parser.add_argument("--sort", choices=["name", "updated_at"], default="updated_at", help="Sort field (default: updated_at)")
    parser.add_argument("--order", choices=["asc", "desc"], default="desc", help="Sort order (default: desc)")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many matching KBs before paging (default 0)")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to display (default 20)")
    parser.add_argument("--min-files", type=int, help="Only show KBs with at least this many files")
    parser.add_argument("--modified-by", help="Case-insensitive substring filter on the name of who last modified the KB")
    parser.add_argument("--json", action="store_true", help="Output raw JSON rows instead of a table")
    args = parser.parse_args()

    client = get_kb_client()
    ids = fetch_all_ids(client)
    entities = fetch_entities(client, ids)

    rows = []
    for kb in entities:
        name = kb.get("name", "")
        description = kb.get("description", "")
        if args.name_contains and args.name_contains.lower() not in name.lower():
            continue
        if args.contains and args.contains.lower() not in (name + " " + description).lower():
            continue
        updated_at = kb.get("updated_at", "")
        if args.modified_since and updated_at < args.modified_since:
            continue
        if args.modified_before and updated_at >= args.modified_before:
            continue
        files_count = kb.get("files_count", 0)
        if args.min_files is not None and files_count < args.min_files:
            continue
        updated_by = format_modified_by(kb.get("updated_by"))
        if args.modified_by and args.modified_by.lower() not in updated_by.lower():
            continue
        rows.append({
            "id": kb.get("id"),
            "name": name,
            "description": description,
            "updated_at": updated_at,
            "updated_by": updated_by,
            "files_count": files_count,
        })

    rows.sort(key=lambda r: r[args.sort] or "", reverse=(args.order == "desc"))
    total_matched = len(rows)
    page = rows[args.offset: args.offset + args.limit]
    has_more = args.offset + args.limit < total_matched

    if args.json:
        print(json.dumps({
            "total_matched": total_matched,
            "offset": args.offset,
            "limit": args.limit,
            "has_more": has_more,
            "next_offset": args.offset + args.limit if has_more else None,
            "rows": page,
        }, indent=2))
        return

    if not page:
        print("No knowledge bases found matching filters.")
        return

    print("| Name | Description | Last modified | Modified by | Files | ID |")
    print("|---|---|---|---|---|---|")
    for r in page:
        desc = r["description"] or ""
        if len(desc) > 80:
            desc = desc[:80] + "..."
        print(f"| {r['name']} | {desc} | {format_timestamp(r['updated_at'])} | {r['updated_by']} | {r['files_count']} | {r['id']} |")

    shown_start = args.offset + 1
    shown_end = args.offset + len(page)
    print()
    print(f"Showing {shown_start}-{shown_end} of {total_matched} matching KB(s).")
    if has_more:
        print(f"MORE_RESULTS_AVAILABLE next_offset={args.offset + args.limit} remaining={total_matched - shown_end}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
