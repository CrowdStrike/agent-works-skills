#!/usr/bin/env python3
"""
compare_versions.py - Invoke two versions of the same agent with the same message and
compare their results side by side (status, duration, cost, tool calls, errors).

Built for the "improve, re-measure" loop: publish/update a new version, then compare it
against the previous one on an identical input instead of eyeballing two separate
analyze_agent.py/inspect_invocation.py runs by hand.

Examples:
    python compare_versions.py --agent-id <uuid> \
        --version-id-a <old-version-uuid> --version-id-b <new-version-uuid> \
        --message "Hello"

    python compare_versions.py --agent-id <uuid> \
        --version-id-a <old-version-uuid> --version-id-b <new-version-uuid> \
        --message "Analyze this ticket..." --timeout 600
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
from discovery_helpers import hydrate_spans
from invocation_helpers import TERMINAL_STATUSES

from analyze_agent import query_invocation_spans, analyze_spans


def invoke_version(agent_id: str, version_id: str, message: str) -> str:
    """Start an invocation of a specific version, returning its invocation_id."""
    body = {
        "id": agent_id,
        "version_id": version_id,
        "messages": [{"role": "user", "content": message}],
    }
    response = call_native(get_agent_invocation_client().invoke_agent_version_external_v1, body=body)
    resources = response.get("resources", [])
    if not resources:
        print(f"ERROR: invocation of version {version_id} started but returned no resource", file=sys.stderr)
        sys.exit(1)
    return resources[0]["id"]


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


def wait_for_terminal(invocation_id: str, timeout: int) -> dict:
    """Poll with backoff (5s -> 20s cap) until status reaches TERMINAL_STATUSES or
    timeout elapses. Mirrors get_messages.py's _wait_for_terminal."""
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
            print(f"WARNING: transient error while polling {invocation_id} ({exc}); retrying...", file=sys.stderr)
            status = "unknown"
        if status in TERMINAL_STATUSES or time.monotonic() >= deadline:
            break
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
        interval = min(interval * 2, 20)
    if status not in TERMINAL_STATUSES:
        print(
            f"WARNING: invocation {invocation_id} still '{status}' after {timeout}s -- "
            "comparing against its latest partial state. Re-run with a larger --timeout.",
            file=sys.stderr,
        )
    return response


def summarize(invocation_id: str, response: dict) -> dict:
    resources = response.get("resources", [])
    invocation = resources[0] if resources else {}
    status = invocation.get("status", "unknown")

    # query_invocation_spans returns (all span IDs, root spans it already hydrated).
    span_ids, known_spans = query_invocation_spans([invocation_id])
    known_ids = {s.get("id") for s in known_spans}
    spans = known_spans + hydrate_spans([i for i in span_ids if i not in known_ids])
    analysis = analyze_spans(spans)

    return {
        "invocation_id": invocation_id,
        "status": status,
        "duration_ms": analysis["trace_durations"]["avg_ms"],
        "total_cost_cents": analysis["total_cost_cents"],
        "tool_usage": analysis["tool_usage"],
        "tool_errors": analysis["tool_errors"],
        "empty_result_traces": analysis["empty_result_traces"],
        "saw_tool_telemetry": analysis["saw_tool_telemetry"],
    }


def print_side_by_side(label_a: str, label_b: str, summary_a: dict, summary_b: dict) -> None:
    def fmt_cost(cents):
        return f"{cents / 100:.2f} credits"

    def fmt_tools(usage, errors):
        if not usage:
            return "(none)"
        return ", ".join(f"{name}: {count} ({errors.get(name, 0)} errors)" for name, count in sorted(usage.items()))

    rows = [
        ("Invocation ID", summary_a["invocation_id"], summary_b["invocation_id"]),
        ("Status", summary_a["status"], summary_b["status"]),
        ("Duration", f"{summary_a['duration_ms']:.0f}ms", f"{summary_b['duration_ms']:.0f}ms"),
        ("Cost", fmt_cost(summary_a["total_cost_cents"]), fmt_cost(summary_b["total_cost_cents"])),
        ("Empty result", str(summary_a["empty_result_traces"]), str(summary_b["empty_result_traces"])),
        ("Tool calls", fmt_tools(summary_a["tool_usage"], summary_a["tool_errors"]),
         fmt_tools(summary_b["tool_usage"], summary_b["tool_errors"])),
    ]

    print(f"{'':16} | {label_a:<40} | {label_b:<40}")
    print("-" * 16 + "-+-" + "-" * 40 + "-+-" + "-" * 40)
    for name, val_a, val_b in rows:
        print(f"{name:16} | {str(val_a):<40} | {str(val_b):<40}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoke two versions of an agent with the same message and compare results"
    )
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--version-id-a", required=True, help="First version ID (UUID)")
    parser.add_argument("--version-id-b", required=True, help="Second version ID (UUID)")
    parser.add_argument("--message", required=True, help="Message to send to both versions")
    parser.add_argument("--timeout", type=int, default=300, help="Max seconds to wait per invocation (default: 300)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON summary instead of a table")
    args = parser.parse_args()

    print(f"Invoking version A ({args.version_id_a})...", file=sys.stderr)
    invocation_id_a = invoke_version(args.agent_id, args.version_id_a, args.message)
    print(f"Invoking version B ({args.version_id_b})...", file=sys.stderr)
    invocation_id_b = invoke_version(args.agent_id, args.version_id_b, args.message)

    print(f"Waiting for version A invocation {invocation_id_a}...", file=sys.stderr)
    response_a = wait_for_terminal(invocation_id_a, args.timeout)
    print(f"Waiting for version B invocation {invocation_id_b}...", file=sys.stderr)
    response_b = wait_for_terminal(invocation_id_b, args.timeout)

    summary_a = summarize(invocation_id_a, response_a)
    summary_b = summarize(invocation_id_b, response_b)

    if args.json:
        print(json.dumps({"version_a": summary_a, "version_b": summary_b}, indent=2))
        return

    print()
    print_side_by_side(f"A ({args.version_id_a[:8]}...)", f"B ({args.version_id_b[:8]}...)", summary_a, summary_b)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 404 bad ID, 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
