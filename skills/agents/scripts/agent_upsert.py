#!/usr/bin/env python3
"""
agent_upsert.py - Create or update a Charlotte AI AgentWorks agent.

Uses the native FalconPy Agents.create_or_update_agent. POST /entities/agents/v3 for both create and update.
Update automatically creates a new version.

Examples:
    # Create with tools
    python agent_upsert.py --name "SecOps Hunter" --model bedrock.claude-5-opus \
        --system-prompt "Hunt for security threats..." \
        --tools <tool-id-1> <tool-id-2>

    # Update (creates new version)
    python agent_upsert.py --id <agent-uuid> --system-prompt "Updated prompt"

    # With knowledge bases
    python agent_upsert.py --name "Docs Assistant" --model bedrock.claude-5-opus \
        --system-prompt "Help with docs..." --knowledge-base-ids <kb-id>
"""

import argparse
import copy
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
from auth import call_native, get_agent_versions_client, get_agents_client

# Distinguishes "flag not passed" from "flag passed with an explicitly empty
# value" for --description/--system-prompt/--tools/--knowledge-base-ids,
# whose argparse defaults used to be "" / [] -- identical to a real empty
# value, so there was no way to intentionally blank a field on update.
_UNSET = object()

# Entity metadata on an agent version that is not part of the editable definition.
# Fields such as cid, is_enabled, is_published and flight_control_config are accepted and
# ignored by the API (verified live), so only the obvious identity/audit fields are stripped.
# Extend this if a 400 ever names another field.
READ_ONLY_VERSION_FIELDS = frozenset({
    "id", "agent_id", "created_at", "created_by", "updated_at", "updated_by",
    "version", "version_number", "status",
})


# Values used for a new agent, and for any field an existing version carries as null/missing.
CREATE_DEFAULTS = {
    "name": "Unnamed Agent",
    "description": "",
    "system_prompt": "",
    "model": "",
    "tools": [],
    "knowledge_base_ids": [],
    "skill_ids": [],
    "parent_version_ids": [],
    "input_format": {"format": "unstructured", "json_schema": "", "usage_instructions": ""},
    "output_format": {"format": "unstructured", "json_schema": "", "usage_instructions": ""},
    "targeting_config": {
        "agent_to_agent": False,
        "apigw": True,
        "charlotte_ai": True,
        "fusion_workflows": False,
    },
    "model_config": {
        "enable_reasoning": False,
        "frequency_penalty": 0.0,
        "max_tokens": 4096,
        "reasoning_effort": "",
        "temperature": 0.7,
        "top_k": 50,
        "top_p": 1.0,
    },
}


def build_tool_objects(tool_ids, existing_tools=()):
    """
    Convert tool ID strings to proper tool objects expected by the API.

    A tool that is already attached keeps its existing object, so its
    parameter_overrides, name_override and description_override survive.

    Args:
        tool_ids: List of tool ID strings (e.g., ["mcp/.../tool_name", ...])
        existing_tools: Tool objects currently on the agent version

    Returns:
        List of tool objects with type, name, id, and override fields
    """
    if not tool_ids:
        return []

    existing_by_id = {tool.get("id"): tool for tool in existing_tools}
    tool_objects = []
    for tool_id in tool_ids:
        if tool_id in existing_by_id:
            tool_objects.append(copy.deepcopy(existing_by_id[tool_id]))
            continue

        # Extract tool name from the ID (last component after final slash)
        tool_name = tool_id.split('/')[-1] if '/' in tool_id else tool_id

        tool_objects.append({
            "type": "action",
            "name": tool_name,
            "id": tool_id,
            "parameter_overrides": {},
            "name_override": "",
            "description_override": ""
        })

    return tool_objects


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or update a Charlotte AI AgentWorks agent",
        epilog="Note: --model is required for create. Get model IDs with models_search.py, tool IDs with tools_get.py/tools_search.py"
    )
    parser.add_argument("--id", help="Agent ID (for update; omit to create new)")
    parser.add_argument("--base-version-id", dest="base_version_id",
                       help="Branch this update from a specific version ID instead of the active "
                            "(published, or latest) version -- e.g. a newer unpublished draft")
    parser.add_argument("--name", help="Agent name (required for create)")
    parser.add_argument("--description", default=_UNSET, help="Agent description (pass \"\" to clear it on update)")
    parser.add_argument("--model", help="Model ID string from models_search.py, e.g. 'bedrock.claude-5-opus' (not a UUID)")
    parser.add_argument("--system-prompt", dest="system_prompt", default=_UNSET,
                       help="Agent system prompt/instructions (pass \"\" to clear it on update)")
    parser.add_argument("--tools", nargs="*", default=_UNSET,
                       help="Tool IDs to attach (space-separated ID strings from tools_get.py/tools_search.py, "
                            "e.g. 'mcp/gce/falcon_platform:...' -- not UUIDs). Pass with no values to clear all tools.")
    parser.add_argument("--knowledge-base-ids", dest="knowledge_base_ids", nargs="*", default=_UNSET,
                       help="Knowledge base IDs (space-separated UUIDs from kb_search.py). Pass with no values to clear all KBs.")
    parser.add_argument("--temperature", type=float, help="Model temperature (0.0-1.0, lower = more deterministic)")
    parser.add_argument("--max-tokens", dest="max_tokens", type=int, help="Maximum tokens in response")
    parser.add_argument("--enable-reasoning", dest="enable_reasoning", action=argparse.BooleanOptionalAction,
                       default=None,
                       help="Enable (--enable-reasoning) or disable (--no-enable-reasoning) extended thinking")
    parser.add_argument("--top-p", dest="top_p", type=float, help="Nucleus sampling threshold (0.0-1.0)")
    parser.add_argument("--top-k", dest="top_k", type=int, help="Top-k sampling limit")
    parser.add_argument("--input-format", dest="input_format",
                       choices=["unstructured", "json_with_schema"],
                       help="Input format type: unstructured (default) or json_with_schema")
    parser.add_argument("--input-schema", dest="input_schema",
                       help="JSON schema for json_with_schema input format")
    parser.add_argument("--output-format", dest="output_format",
                       choices=["unstructured", "html", "markdown", "json", "json_with_schema"],
                       help="Output format type")
    parser.add_argument("--output-schema", dest="output_schema",
                       help="JSON schema for json_with_schema output format")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    # For updates, fetch existing agent to preserve configuration
    existing_version = None
    if args.id:
        print(f"Fetching existing agent configuration...", file=sys.stderr)
        get_response = call_native(get_agents_client().get_studio_agents, ids=[args.id])
        resources = get_response.get("resources", [])
        if not resources:
            print(f"ERROR: agent {args.id} not found", file=sys.stderr)
            sys.exit(1)
        active_version = resources[0].get("active_version")

        if args.base_version_id:
            ver_response = call_native(get_agent_versions_client().get_agent_versions_v1,
                                       ids=[args.base_version_id])
            ver_resources = ver_response.get("resources", [])
            if not ver_resources:
                print(f"ERROR: --base-version-id {args.base_version_id} not found", file=sys.stderr)
                sys.exit(1)
            existing_version = ver_resources[0]
            print(f"Branching from explicit version: {existing_version.get('id')}", file=sys.stderr)
        elif active_version:
            existing_version = active_version
            print(f"Found existing version: {existing_version.get('id')}", file=sys.stderr)

            # Warn if a newer version (an unpublished draft) exists that this
            # update would silently ignore by branching from active_version.
            # Sorted and limited server-side: the default page is 10, so an agent with
            # more versions than that would otherwise pick a stale "newest".
            versions_query = call_native(
                get_agent_versions_client().query_agent_versions_v1,
                parameters={"filter": f"agent_id:'{args.id}'", "sort": "created_at|desc", "limit": 1},
            )
            newest_ids = versions_query.get("resources", [])
            if newest_ids and newest_ids[0] != active_version.get("id"):
                newest_entities = call_native(get_agent_versions_client().get_agent_versions_v1,
                                              ids=newest_ids)
                newest_list = newest_entities.get("resources", [])
                newest = newest_list[0] if newest_list else {"id": newest_ids[0]}
                print(
                    f"WARNING: a newer version exists (id={newest.get('id')}, "
                    f"created_at={newest.get('created_at')}) that is not the active "
                    "version this update will branch from. If that's an unpublished "
                    f"draft you want to keep, re-run with --base-version-id {newest.get('id')}.",
                    file=sys.stderr,
                )

    if args.id and existing_version is None:
        print(f"ERROR: agent {args.id} has no active version to update from. "
              "Re-run with --base-version-id <version-id> (see agent_get.py).", file=sys.stderr)
        sys.exit(1)

    # Validate create requirements
    if not args.id:  # Creating new agent
        if not args.name:
            print("ERROR: --name is required when creating a new agent", file=sys.stderr)
            sys.exit(1)
        if not args.model:
            print("ERROR: --model is required when creating a new agent", file=sys.stderr)
            print("       Get model IDs with: models_search.py --limit 10", file=sys.stderr)
            sys.exit(1)

    # Build version_definition per api.AgentVersionDefinitionRequest.
    # For updates: start from a copy of the existing version so every field we don't
    # model here (e.g. compaction_config, or fields the API adds later) is carried
    # over, then overlay only what the user passed.
    if existing_version:
        version_definition = {
            key: copy.deepcopy(value)
            for key, value in existing_version.items()
            if key not in READ_ONLY_VERSION_FIELDS
        }
    else:
        # Sensible defaults for create
        version_definition = copy.deepcopy(CREATE_DEFAULTS)

    # An existing version can carry null or missing sub-configs; fall back to the create
    # defaults for those so the overrides below never hit a KeyError/TypeError.
    for key, default in CREATE_DEFAULTS.items():
        if version_definition.get(key) is None:
            version_definition[key] = copy.deepcopy(default)

    if args.name:
        version_definition["name"] = args.name
    if args.description is not _UNSET:
        version_definition["description"] = args.description
    if args.system_prompt is not _UNSET:
        version_definition["system_prompt"] = args.system_prompt
    if args.model:
        version_definition["model"] = args.model
    if args.tools is not _UNSET:
        version_definition["tools"] = build_tool_objects(args.tools, version_definition.get("tools") or [])
    if args.knowledge_base_ids is not _UNSET:
        version_definition["knowledge_base_ids"] = args.knowledge_base_ids

    # Override model_config with explicitly passed parameters
    if args.temperature is not None:
        version_definition["model_config"]["temperature"] = args.temperature
    if args.max_tokens is not None:
        version_definition["model_config"]["max_tokens"] = args.max_tokens
    if args.enable_reasoning is not None:
        version_definition["model_config"]["enable_reasoning"] = args.enable_reasoning
    if args.top_p is not None:
        version_definition["model_config"]["top_p"] = args.top_p
    if args.top_k is not None:
        version_definition["model_config"]["top_k"] = args.top_k

    # The 4096 default only applies on create (an update reuses the existing
    # version's max_tokens unless overridden) -- warn since it can silently
    # truncate tool-call arguments or KB-grounded responses for a tool/KB-heavy
    # agent that didn't explicitly set --max-tokens.
    if not args.id and args.max_tokens is None and (
        version_definition["tools"] or version_definition["knowledge_base_ids"]
    ):
        print(
            "WARNING: max_tokens defaults to 4096 and no --max-tokens was given. "
            "This agent has tools/knowledge bases attached, and 4096 tokens can "
            "silently truncate tool-call arguments or KB-grounded responses. "
            "Consider passing --max-tokens explicitly.",
            file=sys.stderr,
        )

    # Override input_format if provided
    if args.input_format is not None or args.input_schema is not None:
        if args.input_format == "json_with_schema":
            version_definition["input_format"]["format"] = "json_with_schema"
            if args.input_schema:
                version_definition["input_format"]["json_schema"] = json.dumps(json.loads(args.input_schema))
        elif args.input_format == "unstructured":
            version_definition["input_format"]["format"] = "unstructured"
            version_definition["input_format"]["json_schema"] = ""
        elif args.input_schema and args.input_format is None:
            # Schema provided without format - keep existing format, update schema
            version_definition["input_format"]["json_schema"] = json.dumps(json.loads(args.input_schema))

    # Override output_format if provided
    if args.output_format is not None or args.output_schema is not None:
        if args.output_format:
            version_definition["output_format"]["format"] = args.output_format
        if args.output_schema:
            version_definition["output_format"]["json_schema"] = json.dumps(json.loads(args.output_schema))
        elif args.output_format and args.output_format != "json_with_schema":
            # Clear schema if format doesn't use it
            version_definition["output_format"]["json_schema"] = ""

    # Build request body per api.CreateOrEditAgentRequest
    body = {"version_definition": version_definition}
    if args.id:
        body["id"] = args.id

    # POST /entities/agents/v3 handles both create and update
    response = call_native(get_agents_client().create_or_update_agent, body=body)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print("Agent operation succeeded but no resource returned.", file=sys.stderr)
        sys.exit(1)

    # API returns {agent, agent_version} not a direct agent object
    resource = resources[0]
    agent = resource.get("agent", {})
    agent_version = resource.get("agent_version", {})
    operation = "updated" if args.id else "created"

    agent_id = agent.get("id")
    version_id = agent_version.get("id")

    print(f"Agent {operation} successfully:")
    print(f"  Agent ID: {agent_id}")

    if version_id:
        print(f"  Version ID: {version_id}")

    # Show version details from agent_version object
    if agent_version:
        print(f"  Name: {agent_version.get('name')}")
        print(f"  Model: {agent_version.get('model')}")
        if agent_version.get('tools'):
            print(f"  Tools: {len(agent_version.get('tools', []))} attached")
        if agent_version.get('knowledge_base_ids'):
            print(f"  Knowledge Bases: {len(agent_version.get('knowledge_base_ids', []))} attached")

    print()
    if version_id and agent_id:
        print(f"To publish this agent:")
        print(f"  python agent_publish.py --id {agent_id} --version-id {version_id}")
    elif agent_id:
        print(f"Note: Use agent_get.py --ids {agent_id} to see version details")


if __name__ == "__main__":
    main()
