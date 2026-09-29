#!/usr/bin/env python3
"""
agent_search.py - Query Charlotte AI AgentWorks agent IDs by FQL filter.

Uses the native FalconPy Agents.query_studio_agents.

IMPORTANT: the agent's display name/description live under `active_version.name` /
`active_version.description`, NOT top-level `name`/`description` fields -- those silently
match zero agents, even against an agent known to exist.

For substring/topic search, use the `:~` fuzzy operator (case-insensitive, matches
anywhere in the string) -- NOT wildcard `*'...'` syntax, which returns zero results on
this endpoint. See references/fql-filters.md for the full confirmed behavior and how
this was found (captured from the Falcon UI's own network requests).

Examples:
    python agent_search.py --filter "active_version.name:~'root access'"          # substring/topic search (recommended)
    python agent_search.py --filter "active_version.description:~'privilege escalation'"
    python agent_search.py --filter "active_version.name:'My Exact Agent Name'"    # exact match, case-sensitive
    python agent_search.py --filter "id:'756e80ab-a906-4d5f-89ad-7e89b93acf36'"
    python agent_search.py --filter 'created_at:>"2026-01-01T00:00:00Z"' --limit 50
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
from auth import call_native, get_agents_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Query agent IDs by FQL filter")
    parser.add_argument("--filter", help="FQL filter, e.g. active_version.name:~'term' (substring, case-insensitive) or active_version.name:'exact' or id:'uuid'", default="")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default 100)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    params = {"limit": args.limit, "offset": args.offset}
    if args.filter:
        params["filter"] = args.filter

    response = call_native(get_agents_client().query_studio_agents, parameters=params)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    pagination = response.get("meta", {}).get("pagination", {})
    total = pagination.get("total", len(resources))

    if not resources:
        print("No agents found matching filter.")
        return

    print(f"Found {len(resources)} agent ID(s) (total: {total}):")
    for agent_id in resources:
        print(f"  {agent_id}")


if __name__ == "__main__":
    main()
