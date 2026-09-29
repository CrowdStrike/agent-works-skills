#!/usr/bin/env python3
"""
cancel_invocation.py - Cancel a Charlotte AI AgentWorks invocation.

Uses the native FalconPy AgentInvocation.update_agent_invocation (PATCH /entities/agent-invocations/v3,
which only accepts status="cancelled").

Examples:
    python cancel_invocation.py --id <invocation-uuid>
"""

import argparse
import json
import sys
import time
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
from invocation_helpers import TERMINAL_STATUSES


# Seconds to wait for the invocation to leave an in-flight status after the cancel is accepted.
STATUS_WAIT_SECONDS = 10


def main() -> None:
    parser = argparse.ArgumentParser(description="Cancel an invocation")
    parser.add_argument("--id", required=True, help="Invocation ID to cancel")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    call_native(
        get_agent_invocation_client().update_agent_invocation,
        id=args.id,
        status="cancelled",
    )

    # The PATCH returns an empty body and call_native already raised on any HTTP error, so the
    # cancel was accepted. Cancellation can take a moment, so read the status back briefly.
    status = "unknown"
    deadline = time.monotonic() + STATUS_WAIT_SECONDS
    while True:
        current = call_native(get_agent_invocation_client().get_agent_invocation_v3,
                              parameters={"id": args.id})
        resources = current.get("resources", [])
        status = resources[0].get("status", "unknown") if resources else "unknown"
        if status in TERMINAL_STATUSES or time.monotonic() >= deadline:
            break
        time.sleep(2)

    if args.json:
        print(json.dumps({"id": args.id, "cancel_requested": True, "status": status}, indent=2))
        return

    print(f"Cancel requested for invocation {args.id}")
    print(f"  Status: {status}")
    if status not in TERMINAL_STATUSES:
        print(f"NOTE: still '{status}' after {STATUS_WAIT_SECONDS}s; the cancel was accepted. "
              "Check again with get_messages.py.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 404 bad ID, 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
