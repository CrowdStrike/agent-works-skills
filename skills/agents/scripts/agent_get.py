#!/usr/bin/env python3
"""
agent_get.py - Get Charlotte AI AgentWorks agent entities by IDs.

Uses the native FalconPy Agents.get_studio_agents.

Examples:
    python agent_get.py --ids <uuid1> <uuid2>
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
    parser = argparse.ArgumentParser(description="Get agent entities by IDs")
    parser.add_argument("--ids", nargs="+", required=True, help="Agent IDs to retrieve")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    response = call_native(get_agents_client().get_studio_agents, ids=args.ids)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])

    if not resources:
        print("No agents found for given IDs.")
        return

    print(f"Retrieved {len(resources)} agent(s):\n")
    for agent in resources:
        active_version = agent.get("active_version") or {}
        print(f"ID: {agent.get('id')}")
        print(f"  Name: {active_version.get('name')}")
        print(f"  Description: {active_version.get('description') or '(none)'}")
        print(f"  Model: {active_version.get('model')}")
        print(f"  Is deleted: {agent.get('is_deleted')}")
        published_version_ids = agent.get("published_version_ids") or []
        print(f"  Published version IDs: {', '.join(published_version_ids) or '(none - draft only)'}")
        tools = active_version.get("tools") or []
        print(f"  Tools: {len(tools)} attached")
        kb_ids = active_version.get("knowledge_base_ids") or []
        print(f"  Knowledge Bases: {len(kb_ids)} attached")
        print()

    print(
        "(Modification timestamps aren't in this entity payload -- use "
        "agent_list.py for last-modified date/by, or --json for the raw "
        "active_version.)"
    )


if __name__ == "__main__":
    main()
