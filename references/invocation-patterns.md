# Agent Invocation Patterns

## Overview

This document explains the different patterns for invoking agents and retrieving results, including the differences between the Python plugin and MCP server approaches.

## Fire-and-Forget Pattern (Python Plugin Default)

The Python scripts use a **non-blocking, fire-and-forget** approach:

### 1. Invoke Agent

```bash
python invoke_agent.py --id <agent-uuid> --message "Your question here"
```

**Returns immediately** with:
- `invocation_id` - Use this to retrieve results
- `status` - Initial status (typically "processing")
- `agent_id` - The agent being invoked

**Does NOT wait** for the agent to complete.

### 2. Retrieve Results

Two options for getting results:

#### Option A: Poll for completion

```bash
python get_messages.py --id <invocation-id>
```

Check the `status` field:
- `"completed"` - Agent finished successfully, see `conversation` for output
- `"failed"` - Agent encountered an error, see `error` field
- `"processing"` - Still running, poll again
- `"waiting_for_tool_approval"` - Human approval required
- `"waiting_for_external_tools"` - External action needed

**Polling loop example:**

```bash
#!/bin/bash
INVOCATION_ID="<your-invocation-id>"

while true; do
    STATUS=$(python get_messages.py --id "$INVOCATION_ID" --json | jq -r '.status')
    echo "Status: $STATUS"
    
    if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
        python get_messages.py --id "$INVOCATION_ID"
        break
    fi
    
    sleep 2
done
```

#### Option B: Stream results

```bash
python stream_invocation.py --id <invocation-id>
```

**Note:** Despite the name, this does NOT provide true token-by-token streaming — the native FalconPy `Stream` class uses the same non-streaming request/response mechanism as every other FalconPy call, it's just typed access to the same endpoint. It polls internally and returns the full conversation once complete.

## Blocking Pattern (MCP Server)

The MCP server's `invoke_agent` tool uses a **blocking approach**:

```typescript
// MCP automatically polls every 1.5s with 60s timeout
const result = await invoke_agent({
  agent_id: "...",
  messages: [{role: "user", content: "..."}],
});
// Returns only when completed, failed, or timed out
```

**Differences:**
- ✅ Simpler - single call gets results
- ⚠️ Blocks for up to 60s (configurable via `FALCON_INVOKE_TIMEOUT_MS`)
- ⚠️ Returns fallback object if timeout: `{invocation_id: "...", status: "running", hint: "..."}`

## Comparison Table

| Feature | Python Plugin | MCP Server |
|---------|---------------|------------|
| **Invocation** | Fire-and-forget | Blocking with poll |
| **Returns** | Immediately | After completion or timeout |
| **Timeout** | None (user polls) | 60s default (configurable) |
| **Polling** | Manual (user script) | Automatic (internal) |
| **Use Case** | Long-running agents, async workflows | Quick responses, synchronous calls |
| **Flexibility** | Full control over polling | Simplified, one-shot |

## When to Use Each Pattern

### Use Fire-and-Forget (Python Plugin)

✅ **Good for:**
- Long-running agents (>60s)
- Batch processing multiple agents in parallel
- Workflows where you need the invocation ID immediately
- When you want control over polling frequency
- Asynchronous job queues

❌ **Not ideal for:**
- Quick question-answer interactions
- When you need results in a single blocking call

### Use Blocking Poll (MCP Server)

✅ **Good for:**
- Interactive sessions with Claude Code
- Quick agent responses (<60s)
- Simplified scripts where you just want the answer
- When you don't want to manage polling logic

❌ **Not ideal for:**
- Long-running agents that exceed timeout
- High-concurrency parallel invocations
- When you need granular control over polling

## Building a Blocking Wrapper

If you want MCP-like behavior in Python, create a polling wrapper:

```python
#!/usr/bin/env python3
"""invoke_and_wait.py - Blocking agent invocation with polling"""

import argparse
import json
import sys
import time
from auth import call_native, get_agent_invocation_client

def invoke_and_wait(agent_id, message, timeout_seconds=60):
    """Invoke agent and poll until completion or timeout."""
    
    # Start invocation
    body = {
        "id": agent_id,
        "messages": [{"role": "user", "content": message}],
    }
    client = get_agent_invocation_client()
    response = call_native(client.invoke_published_agent_external_v1, body=body)
    invocation_id = response["resources"][0]["id"]
    
    # Poll until done or timeout
    deadline = time.time() + timeout_seconds
    poll_interval = 1.5  # seconds
    
    terminal_statuses = {"completed", "failed", "waiting_for_tool_approval", "waiting_for_external_tools"}
    
    while time.time() < deadline:
        # Fetch current state
        result = call_native(client.get_agent_invocation_v3, parameters={"id": invocation_id})
        invocation = result["resources"][0]
        status = invocation.get("status", "unknown")
        
        if status in terminal_statuses:
            return invocation
        
        time.sleep(poll_interval)
    
    # Timeout fallback
    return {
        "invocation_id": invocation_id,
        "status": "running",
        "hint": "still running; call get_messages.py with this invocation_id"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Invoke agent and wait for result")
    parser.add_argument("--id", required=True, help="Agent ID")
    parser.add_argument("--message", required=True, help="Message")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()
    
    result = invoke_and_wait(args.id, args.message, args.timeout)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result.get("status")
        if status == "completed":
            conversation = result.get("conversation", [])
            last_assistant = next((m for m in reversed(conversation) if m["role"] == "assistant"), None)
            print(last_assistant.get("content", "No response"))
        elif status == "failed":
            print(f"ERROR: {result.get('error')}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Status: {status}")
            print(f"Invocation ID: {result.get('invocation_id')}")
```

## Real-World Examples

### Example 1: Quick Question (Use Blocking)

```bash
# MCP Server approach (blocking)
python invoke_and_wait.py --id <agent-id> --message "What's the weather today?"
# Waits and returns answer
```

### Example 2: Long Analysis (Use Fire-and-Forget)

```bash
# Start agent
INVOCATION_ID=$(python invoke_agent.py --id <agent-id> \
  --message "Analyze this 1000-page document" --json | jq -r '.resources[0].id')

# Do other work...
echo "Agent running in background: $INVOCATION_ID"

# Check back later
python get_messages.py --id "$INVOCATION_ID"
```

### Example 3: Parallel Batch Processing

```bash
# Start 10 agents in parallel (fire-and-forget)
for i in {1..10}; do
  python invoke_agent.py --id <agent-id> --message "Task $i" --json > /tmp/inv_$i.json &
done
wait

# Poll all of them
for i in {1..10}; do
  INVOCATION_ID=$(jq -r '.resources[0].id' /tmp/inv_$i.json)
  python get_messages.py --id "$INVOCATION_ID" > /tmp/result_$i.txt &
done
wait
```

## Streaming Limitation

Both Python plugin and MCP server have the **same streaming limitation**:

> The native FalconPy `Stream` class does not expose true SSE token-by-token streaming — it uses the same underlying request/response mechanism as every other call. All "streaming" scripts poll internally and return the full conversation once complete.

This is a FalconPy SDK limitation, not specific to this plugin or MCP server.

## Summary

- **Python Plugin Default**: Fire-and-forget (non-blocking)
  - `invoke_agent.py` → returns immediately
  - `get_messages.py` → poll manually
  - `stream_invocation.py` → polls internally

- **MCP Server**: Blocking with automatic polling
  - `invoke_agent` → waits up to 60s
  - Polls internally at 1.5s intervals
  - Returns result or timeout fallback

Choose the pattern that fits your use case!
