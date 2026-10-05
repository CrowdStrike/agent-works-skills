#!/usr/bin/env python3
"""
agent_list.py - List Charlotte AI AgentWorks agents as a table (Name, Description, Last modified,
Last modified by, Status) -- mirrors the Charlotte AI AgentWorks UI's agent list view.

For a plain name/description substring search, prefer agent_search.py's
`active_version.name:~'term'` / `active_version.description:~'term'` fuzzy filter instead --
it's a single API call regardless of tenant size (see references/fql-filters.md). Use this
script when you need MULTIPLE criteria combined at once (name substring + date range +
publish status), sorted/paginated table output -- things a single `--filter` string doesn't
conveniently express. This script pages through ALL agent IDs, batch-fetches their entities,
then filters/sorts/paginates client-side. On a ~1700-agent tenant this is ~17 list calls +
~17 batch-get calls; the heavy per-agent JSON (system prompts, tool configs) stays inside
this script and never hits stdout -- only the compact table rows are printed.

Examples:
    python agent_list.py
    python agent_list.py --name-contains "root access"
    python agent_list.py --modified-since 2026-09-01
    python agent_list.py --status published --sort name --order asc
    python agent_list.py --limit 50 --json
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone

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
from formatting import format_modified_by, format_timestamp


def fetch_all_ids():
    all_ids = []
    offset, limit = 0, 100
    while True:
        r = call_native(get_agents_client().query_studio_agents, parameters={"limit": limit, "offset": offset})
        ids = r.get("resources") or []
        if not ids:
            break
        all_ids.extend(ids)
        total = r.get("meta", {}).get("pagination", {}).get("total", 0)
        offset += limit
        if offset >= total:
            break
    return all_ids


def parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO8601 date/datetime (trailing "Z" accepted; naive values are UTC).

    Returns None if value is empty or unparseable.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch_entities(ids):
    entities = []
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        r = call_native(get_agents_client().get_studio_agents, ids=batch)
        entities.extend(r.get("resources") or [])
    return entities


def main() -> None:
    parser = argparse.ArgumentParser(description="List Charlotte AI AgentWorks agents as a table")
    parser.add_argument("--name-contains", help="Case-insensitive substring filter on agent name")
    parser.add_argument("--created-by", help="Case-insensitive substring filter on the creator's name/id (client-side; active_version.created_by is not a confirmed FQL field)")
    parser.add_argument("--modified-since", help="ISO date/datetime; only agents modified on/after this")
    parser.add_argument("--modified-before", help="ISO date/datetime; only agents modified before this")
    parser.add_argument("--status", choices=["published", "unpublished"], help="Filter by publish status")
    parser.add_argument("--sort", choices=["name", "updated_at"], default="updated_at", help="Sort field (default: updated_at)")
    parser.add_argument("--order", choices=["asc", "desc"], default="desc", help="Sort order (default: desc)")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many matching agents before paging (default 0)")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to display (default 20)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON rows instead of a table")
    args = parser.parse_args()

    bounds = {}
    for flag in ("modified_since", "modified_before"):
        raw = getattr(args, flag)
        if raw:
            bounds[flag] = parse_timestamp(raw)
            if bounds[flag] is None:
                parser.error(f"--{flag.replace('_', '-')}: not an ISO date/datetime: {raw!r}")

    ids = fetch_all_ids()
    entities = fetch_entities(ids)

    rows = []
    for agent in entities:
        av = agent.get("active_version") or {}
        name = av.get("name", "")
        if args.name_contains and args.name_contains.lower() not in name.lower():
            continue
        created_by = format_modified_by(av.get("created_by"))
        if args.created_by and args.created_by.lower() not in created_by.lower():
            continue
        updated_at = av.get("updated_at", "")
        if bounds:
            updated_dt = parse_timestamp(updated_at)
            if updated_dt is None:
                continue
            if "modified_since" in bounds and updated_dt < bounds["modified_since"]:
                continue
            if "modified_before" in bounds and updated_dt >= bounds["modified_before"]:
                continue
        is_published = bool(av.get("is_published"))
        if args.status == "published" and not is_published:
            continue
        if args.status == "unpublished" and is_published:
            continue
        rows.append({
            "id": agent.get("id"),
            "name": name,
            "description": av.get("description", ""),
            "updated_at": updated_at,
            "updated_by": format_modified_by(av.get("updated_by")),
            "created_by": created_by,
            "status": "Published" if is_published else "Unpublished",
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
        print("No agents found matching filters.")
        return

    print("| Name | Description | Last modified | Last modified by | Created by | Status |")
    print("|---|---|---|---|---|---|")
    for r in page:
        desc = r["description"] or ""
        if len(desc) > 80:
            desc = desc[:80] + "..."
        print(f"| {r['name']} | {desc} | {format_timestamp(r['updated_at'])} | {r['updated_by']} | {r['created_by']} | {r['status']} |")

    shown_start = args.offset + 1
    shown_end = args.offset + len(page)
    print()
    print(f"Showing {shown_start}-{shown_end} of {total_matched} matching agent(s).")
    if has_more:
        print(f"MORE_RESULTS_AVAILABLE next_offset={args.offset + args.limit} remaining={total_matched - shown_end}")


if __name__ == "__main__":
    main()
