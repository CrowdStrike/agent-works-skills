#!/usr/bin/env python3
"""
invoke_agent.py - Invoke a published Charlotte AI AgentWorks agent.

Uses the native FalconPy AgentInvocation.invoke_published_agent_external_v1 method.

Examples:
    python invoke_agent.py --id <agent-uuid> --message "Hello, how can you help?"
    python invoke_agent.py --id <agent-uuid> --message "Analyze..." --deadline-seconds 300
    python invoke_agent.py --id <agent-uuid> --message "Investigate..." --max-cost 100
    python invoke_agent.py --id <agent-uuid> --message "Audit..." --deadline-seconds 900 --max-cost 500
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
from auth import call_native, get_agent_invocation_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke a published agent")
    parser.add_argument("--id", required=True, help="Published agent ID")
    parser.add_argument("--message", required=True, help="Message to send to agent")
    parser.add_argument(
        "--deadline-seconds",
        type=int,
        help="Optional deadline in seconds (minimum: 90). Invocation terminates after this duration.",
    )
    parser.add_argument(
        "--max-cost",
        type=int,
        help="Optional max cost in credit cents (100 = 1 Charlotte credit; max: 10000). Invocation terminates when limit is reached.",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    # Validate deadline_seconds minimum
    if args.deadline_seconds is not None and args.deadline_seconds < 90:
        print("Error: --deadline-seconds must be at least 90 seconds", file=sys.stderr)
        sys.exit(1)

    # Validate max_cost bound. The API requires an integer and rejects values
    # above 10000 credit cents (100 Charlotte credits) with a 400.
    if args.max_cost is not None and args.max_cost > 10000:
        print("Error: --max-cost must not exceed 10000 credit cents (100 Charlotte credits)", file=sys.stderr)
        sys.exit(1)

    # InvokePublishedAgentExternalRequest body
    # API expects "messages" array format per MCP server specification
    body = {
        "id": args.id,
        "messages": [
            {
                "role": "user",
                "content": args.message,
            }
        ],
    }

    # Add optional execution controls if specified
    if args.deadline_seconds is not None:
        body["deadline_seconds"] = args.deadline_seconds
    if args.max_cost is not None:
        body["credit_cents_limit"] = args.max_cost

    response = call_native(get_agent_invocation_client().invoke_published_agent_external_v1, body=body)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print("Invocation started but no resource returned.", file=sys.stderr)
        sys.exit(1)

    invocation = resources[0]
    invocation_id = invocation.get("id")
    status = invocation.get("status", "unknown")

    print(f"Agent invocation started successfully:")
    print(f"  Invocation ID: {invocation_id}")
    print(f"  Agent ID: {invocation.get('agent_id')}")
    print(f"  AI TraceID: {invocation.get('ai_trace_id')}")
    print(f"  Status: {status}")

    # Show execution controls if they were specified
    if args.deadline_seconds is not None:
        print(f"  Deadline: {args.deadline_seconds} seconds")
    if args.max_cost is not None:
        charlotte_credits = args.max_cost / 100
        print(f"  Max cost: {args.max_cost} credit cents ({charlotte_credits:.2f} Charlotte credits)")

    print()
    print(f"Use get_messages.py --id {invocation_id} to retrieve results.")
    print(f"Or use stream_invocation.py --id {invocation_id} for real-time streaming.")


if __name__ == "__main__":
    main()
