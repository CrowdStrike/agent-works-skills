#!/usr/bin/env python3
"""
get_messages.py - Get messages from a Charlotte AI AgentWorks invocation.

Uses the native FalconPy AgentInvocation.get_agent_invocation_v3 method.

Examples:
    python get_messages.py --id <invocation-uuid>

    # Block until the invocation reaches a terminal status instead of
    # polling manually with repeated calls + sleep
    python get_messages.py --id <invocation-uuid> --wait
    python get_messages.py --id <invocation-uuid> --wait --timeout 600
"""

import argparse
import json
import sys
import os
import time

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import call_native, get_agent_invocation_client, is_transient_error
from invocation_helpers import TERMINAL_STATUSES


def _fetch(invocation_id: str) -> dict:
    params = {"id": invocation_id}
    return call_native(get_agent_invocation_client().get_agent_invocation_v3, parameters=params)


def _status_of(response: dict, invocation_id: str) -> str:
    """Return the invocation's status.

    Raises:
        RuntimeError (no HTTP status, so is_transient_error treats it as permanent) if the
        response carries no resources.
    """
    resources = response.get("resources", [])
    if not resources:
        raise RuntimeError(f"No invocation found for ID {invocation_id}")
    return resources[0].get("status", "unknown")


def _wait_for_terminal(invocation_id: str, timeout: int) -> dict:
    """Poll with backoff (5s -> 20s cap) until status reaches TERMINAL_STATUSES
    or timeout elapses. Returns the last response fetched either way.

    A transient fetch error (e.g. a momentary 429/503, or a network-level
    connection/timeout error) is treated the same as an in-flight status --
    logged and retried -- rather than raising and losing all prior wait
    progress; the invocation is very likely still running server-side.
    Permanent errors (other 4xx, e.g. a bad ID or missing scope) are re-raised
    immediately instead of polling until the timeout.
    """
    deadline = time.monotonic() + timeout
    interval = 5
    response = {"resources": []}
    status = "unknown"
    while True:
        try:
            response = _fetch(invocation_id)
            status = _status_of(response, invocation_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if not is_transient_error(exc):
                raise
            # Broad on purpose: call_native only raises RuntimeError for
            # HTTP-level errors: a connection drop/timeout from the
            # underlying request surfaces as some other exception type, and
            # --wait should retry through that too rather than crash.
            print(f"WARNING: transient error while polling ({exc}); retrying...", file=sys.stderr)
            status = "unknown"
        if status in TERMINAL_STATUSES or time.monotonic() >= deadline:
            break
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
        interval = min(interval * 2, 20)  # backoff, capped at 20s
    if status not in TERMINAL_STATUSES:
        print(
            f"WARNING: still '{status}' after {timeout}s -- showing latest "
            "partial state. Re-run with a larger --timeout to keep waiting.",
            file=sys.stderr,
        )
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Get messages from invocation")
    parser.add_argument("--id", required=True, help="Invocation ID")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll (with backoff) until the invocation reaches a terminal status, "
             "instead of returning immediately. Replaces manual sleep+poll loops.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to poll when --wait is set (default: 300)",
    )
    args = parser.parse_args()

    response = _wait_for_terminal(args.id, args.timeout) if args.wait else _fetch(args.id)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print("No invocation found for given ID.")
        return

    invocation = resources[0]
    # API returns 'conversation' field, not 'messages'
    conversation = invocation.get("conversation", [])
    status = invocation.get("status", "unknown")

    print(f"Invocation: {invocation.get('id')}")
    print(f"Status: {status}")
    print(f"Agent ID: {invocation.get('agent_id')}")
    print()

    if not conversation:
        print("No messages yet. Invocation may still be running.")
        return

    print(f"Conversation ({len(conversation)} messages):\n")
    for i, msg in enumerate(conversation, 1):
        role = msg.get("role") or "unknown"
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content)
        print(f"{i}. [{role.upper()}]")
        print(f"   {content[:200]}{'...' if len(content) > 200 else ''}")
        print()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 404 bad ID, 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
