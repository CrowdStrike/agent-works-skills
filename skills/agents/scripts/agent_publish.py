#!/usr/bin/env python3
"""
agent_publish.py - Publish a Charlotte AI AgentWorks agent version (make invocable).

Uses the native FalconPy Agents.update_agent. PATCH /entities/agents/v3?id=<agent-id>
with body {version_id, is_published:true}.

Examples:
    python agent_publish.py --id <agent-uuid> --version-id <version-uuid>

Get the version ID from agent_upsert.py output or agent_get.py.
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
    parser = argparse.ArgumentParser(
        description="Publish a Charlotte AI AgentWorks agent version",
        epilog="Note: Both --id (agent ID) and --version-id are required. Get version ID from agent_upsert.py or agent_get.py"
    )
    parser.add_argument("--id", required=True, help="Agent ID")
    parser.add_argument("--version-id", dest="version_id", required=True,
                       help="Version ID to publish (from agent_upsert.py or agent_get.py)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    response = call_native(
        get_agents_client().update_agent,
        id=args.id,
        version_id=args.version_id,
        is_published=True,
    )

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print("Publish succeeded but no resource returned.", file=sys.stderr)
        sys.exit(1)

    agent = resources[0]

    print("Agent version published successfully:")
    print(f"  Agent ID: {agent.get('id')}")

    # Extract published version details
    if "active_version" in agent and isinstance(agent["active_version"], dict):
        av = agent["active_version"]
        print(f"  Version ID: {av.get('id')}")
        print(f"  Name: {av.get('name')}")
        print(f"  Is Published: {av.get('is_published', False)}")
        print(f"  Is Enabled: {av.get('is_enabled', True)}")
    elif "published_version_ids" in agent:
        print(f"  Published Versions: {len(agent.get('published_version_ids', []))}")

    print()
    print("Agent is now invocable:")
    print(f"  python invoke_agent.py --id {agent.get('id')} --message \"Your prompt\"")


if __name__ == "__main__":
    main()
