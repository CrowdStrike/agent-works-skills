#!/usr/bin/env python3
"""
stream_invocation.py - Stream Charlotte AI AgentWorks invocation results.

Uses the native FalconPy Stream.stream_invocation_response_v1 method.

NOTE: This uses the same non-streaming request mechanism as every other FalconPy
call, so it does not provide true SSE token-by-token streaming. This script returns
the current/accumulated invocation payload as best-effort support.

Examples:
    python stream_invocation.py --id <invocation-uuid>
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
from auth import call_native, get_stream_client


def parse_sse(raw: bytes | str) -> list[dict]:
    """Parse a server-sent-event payload into a list of {"event", "data"} dicts.

    Each event's `data:` lines are joined and decoded as JSON when possible, otherwise kept as
    text. The terminal `[DONE]` sentinel is dropped.
    """
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event_name = "message"
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip())
        if not data_lines:
            continue
        data = "\n".join(data_lines)
        if data == "[DONE]":
            continue
        try:
            data = json.loads(data)
        except ValueError:
            pass
        events.append({"event": event_name, "data": data})
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream invocation results")
    parser.add_argument("--id", required=True, help="Invocation ID")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    # Swagger documents this query param as singular 'id', not 'ids'.
    params = {"id": args.id}

    # The stream endpoint returns the raw server-sent-event text, not a JSON object.
    response = call_native(get_stream_client().stream_invocation_response_v1, parameters=params)
    events = parse_sse(response) if isinstance(response, (bytes, str)) else []

    if args.json:
        print(json.dumps(events if events else response, indent=2, default=str))
        return

    if not events:
        print("No streamed messages for given ID (it may not exist or has produced no output yet).")
        return

    print(f"Invocation: {args.id}")
    print(f"Events ({len(events)}):\n")
    for i, event in enumerate(events, 1):
        data = event["data"]
        if isinstance(data, dict):
            role = (data.get("role") or event["event"]).upper()
            content = data.get("content") or ""
            if not isinstance(content, str):
                content = json.dumps(content)
        else:
            role, content = event["event"].upper(), str(data)
        print(f"{i}. [{role}]")
        print(f"   {content[:200]}{'...' if len(content) > 200 else ''}")
        print()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 404 bad ID, 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
