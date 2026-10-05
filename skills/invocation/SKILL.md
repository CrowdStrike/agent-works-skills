---
name: invocation
description: >
  Invoke Charlotte AI AgentWorks agents and manage invocations.
  Invoke published agents or specific versions, stream results, get messages, and cancel runs.
  Uses native FalconPy classes (`AgentInvocation`, `Stream`).
  TRIGGER when user asks to invoke an agent, run an agent, get agent results/messages, or cancel an invocation.
  DO NOT TRIGGER for agent creation (use agents skill), knowledge bases (use knowledge-bases skill),
  or discovery (use discovery skill).
version: 1.0.0
updated: 2026-08-21
tags: [agent-works, charlotte, invocation, streaming, falcon]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
allowed-tools: Bash(cd *), Bash(../../scripts/python.sh:*)
metadata:
  category: agent-execution
---

# Agent Invocation

> **Read this first.**
>
> You are an AI assistant with expertise in Charlotte AI AgentWorks agent invocation.
> Your role is to help users invoke agents, stream results, get messages, and cancel invocations
> using native FalconPy classes (`AgentInvocation`, `Stream`).
>
> **IMMEDIATE ACTIONS REQUIRED:**
> 1. Read this entire skill file before taking any action
> 2. Verify credentials are configured
> 3. Invoke **published agents** via `invoke_agent.py` OR **specific versions** (including drafts) via `invoke_version.py`
> 4. Run scripts via `cd ${CLAUDE_PLUGIN_ROOT}/skills/invocation && ../../scripts/python.sh scripts/<script>.py`
> 5. Parse script output and present results clearly
>
> **MUST NOT:**
> - Invoke unpublished agents using `invoke_agent.py` (will fail with 400) — use `invoke_version.py` instead
> - Guess invocation IDs — save from invoke response
> - Poll messages in tight loop (use reasonable intervals)

## Running the scripts

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/invocation
../../scripts/python.sh scripts/<script_name>.py [args]
```

- **Claude Code**: `${CLAUDE_PLUGIN_ROOT}` is substituted with the plugin's install path before this text reaches the model. Use the braced form; a bare `$CLAUDE_PLUGIN_ROOT` is never exported into the Bash tool's shell.
- **Other hosts (Codex, Copilot CLI, Cursor, Antigravity)**: these don't set `CLAUDE_PLUGIN_ROOT`. `cd` to the folder you loaded this SKILL.md from (e.g. `~/.agents/skills/invocation`) and run `../../scripts/python.sh scripts/<script_name>.py [args]` from there.

## Prerequisites

- **Credentials**: Same as other skills
- **API scopes**: `csrn:charlotte-ai:agent:invocation` (assert/execute)
- **Agent publishing**:
  - `invoke_agent.py` requires **published agents** (invokes latest published version)
  - `invoke_version.py` can invoke **any version** (published or draft) by specifying version_id

## Core Workflow

1. **List recent invocations** → `list_invocations.py --agent-id <agent-id> --limit 10` → shows recent invocation IDs
2. **Invoke agent** → `invoke_agent.py --id <agent-id> --message "Hello"` → returns invocation_id and trace_id
   - **Optional controls**: `--deadline-seconds <seconds>` (min: 90), `--max-cost <credit-cents>` (100 = 1 credit; max: 10000, integer only) → constrain execution
3. **Get messages** → `get_messages.py --id <invocation-id> --wait` → blocks (backoff 5s→20s, default 300s timeout) until the invocation reaches a terminal status, then returns conversation messages. Add `--timeout <seconds>` to change the max wait. Omit `--wait` to just fetch the current state once, e.g. for a quick status check without blocking.
4. **Inspect trace** → `inspect_invocation.py --invocation-id <invocation-id>` → waterfall tree, duration, tool outputs
5. **Inspect cost** → Fetch the trace (discovery skill) and read `cost.agg_credit_cents`/`cost.raw_credit_cents` off its spans → actual cost in credit cents (no separate `cost` span_type -- see "Monitoring Invocation Costs" below)
6. **Stream invocation** → `stream_invocation.py --id <invocation-id>` → full conversation once complete (polls; not token-by-token SSE)
7. **Cancel invocation** → `cancel_invocation.py --id <invocation-id>` → stops in-flight run

## Invocation Controls

When invoking agents, you can optionally specify execution constraints:

### Deadline

Set a hard deadline (in seconds) after which the invocation will be terminated:

```bash
# Stop execution after 5 minutes (300 seconds)
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Your task..." \
  --deadline-seconds 300
```

**Constraints:**
- **Minimum value: 90 seconds** - Values below 90 are rejected with HTTP 400
- **Recommended minimum: 120 seconds** for agents with tool calls
- **Typical values**: 300-600 seconds for standard tasks, 900-1800 for complex operations

**Use cases:**
- Time-sensitive operations with hard cutoffs
- Preventing runaway agents from consuming excessive time
- Integration with external systems that have timeout constraints

### Max Cost

Set a maximum cost in Charlotte credit cents (100 = 1 Charlotte credit) to prevent expensive invocations:

```bash
# Limit invocation to 10,000 credit cents (100 Charlotte credits — the max allowed)
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Your task..." \
  --max-cost 10000
```

**Constraints:**
- **Maximum value: 10000 credit cents (100 Charlotte credits)** - Values above 10000 are rejected with HTTP 400
- **Must be an integer** - The API rejects non-integer values (e.g. `10000.0`) with a generic 400

**Credit Conversion:**
- **1 Charlotte credit = 100 credit cents**
- Example values:
  - `--max-cost 100` = 1 Charlotte credit
  - `--max-cost 1000` = 10 Charlotte credits
  - `--max-cost 10000` = 100 Charlotte credits (the maximum allowed)

**Use cases:**
- Budget control for exploratory or experimental agents
- Cost caps for user-facing agents in multi-tenant environments
- Preventing unexpectedly expensive tool calls or excessive LLM usage

### Combined Controls

Both parameters can be used together:

```bash
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Analyze recent detections" \
  --deadline-seconds 600 \
  --max-cost 10000
```

**Behavior when limits are reached:**
- The invocation is terminated gracefully
- Partial results (if any) are available via `get_messages.py`
- Trace shows termination reason in span attributes

**Note:** `max_cost` is expressed in **credit cents** where 100 = 1 Charlotte credit, capped at 10000 (100 Charlotte credits).

### Monitoring Invocation Costs

After an invocation completes, you can inspect the actual cost incurred by fetching the
trace and reading its `cost.*` attributes -- there is no separate `cost` span_type; cost
lives directly on the spans a normal trace query already returns (confirmed against a live
tenant, 2026-09-23):

```bash
# Get the trace_id from the invocation response, then fetch the full trace.
cd ${CLAUDE_PLUGIN_ROOT}/skills/discovery
../../scripts/python.sh scripts/spans_search.py \
  --filter "trace_id:'<trace-id>'+start_time:>='now-24h'" \
  --limit 500
# Hydrate the returned span IDs with spans_get.py, then read cost.* off the
# aw_agent_response / llm spans (see below) -- no additional filter needed.
```

**Cost attributes (on `aw_agent_response`/`llm` spans):**
- `cost.agg_credit_cents` — total cost for the whole invocation (on the `aw_agent_response` span)
- `cost.raw_credit_cents` — per-LLM-call cost (on individual `llm` spans)
- `cost.reserved_credit_cents` — the budget that was *reserved* for the invocation, not what
  was actually spent (confirmed live: on a failed/timed-out invocation, `agg_credit_cents`
  was `0` while `reserved_credit_cents` still showed the reserved amount) -- don't mistake it
  for actual cost.
- `cost.was_quota_consumed` — whether the invocation was charged against quota vs. credits

**Use cases:**
- Verify actual cost vs. budget after invocation completes
- Analyze cost trends across multiple invocations
- Identify expensive agents or operations for optimization
- Generate cost reports for billing/accounting

## Script Reference

| Script | Purpose | Key Flags |
|--------|---------|-----------|
| `list_invocations.py` | List recent invocations for an agent | `--agent-id <uuid>`, `--limit 10`, `--days 7` |
| `invoke_agent.py` | Invoke latest **published** version of an agent | `--id <agent-id>`, `--message "..."`, `--deadline-seconds <seconds>` (min: 90), `--max-cost <credit-cents>` (100 = 1 credit; max: 10000, integer only) |
| `invoke_version.py` | Invoke **specific version** (published or draft) | `--agent-id`, `--version-id <uuid>`, `--message`, `--deadline-seconds`, `--max-cost` — returns `invocation_id`; feed that straight into `inspect_invocation.py --invocation-id` (it resolves its own `trace_id`) |
| `get_messages.py` | Get conversation from invocation | `--id <invocation-id>`, `--wait` (block until terminal status, backoff 5s→20s), `--timeout <seconds>` (default 300, only with `--wait`) |
| `inspect_invocation.py` | Inspect invocation trace (waterfall + tool outputs) | `--invocation-id` (required), `--tool-output-only`, `--errors-only` (only show tool spans that errored), `--json` |
| `cancel_invocation.py` | Cancel in-flight invocation | `--id <invocation-id>` |
| `stream_invocation.py` | Stream invocation results (polls; returns full conversation) | `--id <invocation-id>` |

## Usage Examples

### List recent invocations for an agent
```bash
../../scripts/python.sh scripts/list_invocations.py \
  --agent-id <agent-id> \
  --limit 10

# Shows:
# - Invocation IDs
# - Timestamps
# - Duration
# - Status (✅ success / ❌ error)
# - Span count
```

### Invoke a published agent
```bash
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Investigate detection XYZ for unauthorized access"
# Returns: invocation_id and trace_id
# Use invocation_id with inspect_invocation.py to view execution details
```

**With execution controls:**
```bash
# With deadline (minimum 90 seconds)
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Investigate detection XYZ" \
  --deadline-seconds 300

# With max cost (credit cents: 100 = 1 Charlotte credit)
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Analyze vulnerabilities" \
  --max-cost 10000

# With both
../../scripts/python.sh scripts/invoke_agent.py \
  --id <agent-id> \
  --message "Comprehensive security audit" \
  --deadline-seconds 900 \
  --max-cost 10000
```

### Invoke a specific version (draft or published), then inspect its trace
```bash
../../scripts/python.sh scripts/invoke_version.py \
  --agent-id <agent-id> \
  --version-id <version-id> \
  --message "Investigate detection XYZ"
# Returns: invocation_id (no trace_id printed directly -- inspect_invocation.py
# resolves its own trace_id from the invocation_id, so this is enough)

../../scripts/python.sh scripts/get_messages.py --id <invocation-id> --wait
# Blocks until the invocation reaches a terminal status

../../scripts/python.sh scripts/inspect_invocation.py --invocation-id <invocation-id>
# Waterfall + tool outputs for this specific version's run
```

### Get invocation messages
```bash
../../scripts/python.sh scripts/get_messages.py \
  --id abc123-invocation-id
```

### Inspect full trace (waterfall + tool outputs)
```bash
../../scripts/python.sh scripts/inspect_invocation.py \
  --invocation-id abc123-invocation-id

# Shows:
# - Waterfall tree visualization
# - Total invocation duration
# - Per-span durations
# - Tool outputs with attributes
```

### Inspect invocation cost
```bash
# First, get the trace_id from the invocation (returned by invoke_agent.py)
TRACE_ID="<trace-id-from-invocation>"

# Fetch the full trace using the discovery skill -- cost lives in attributes
# on the spans this already returns, there is no separate "cost" span_type.
cd ${CLAUDE_PLUGIN_ROOT}/skills/discovery
../../scripts/python.sh scripts/spans_search.py \
  --filter "trace_id:'${TRACE_ID}'+start_time:>='now-24h'" \
  --limit 500

# Hydrate the returned span IDs, then read cost.agg_credit_cents off the
# aw_agent_response span (total) or cost.raw_credit_cents off individual
# llm spans (per-call):
../../scripts/python.sh scripts/spans_get.py --ids <span-id>

# Shows:
# - Total cost in credit cents
# - Cost breakdown by resource type
# - Model-specific costs
# - Token usage metrics
```

### Inspect only tool outputs
```bash
../../scripts/python.sh scripts/inspect_invocation.py \
  --invocation-id abc123-invocation-id \
  --tool-output-only
```

### Cancel running invocation
```bash
../../scripts/python.sh scripts/cancel_invocation.py \
  --id abc123-invocation-id
```

### Stream invocation results
```bash
../../scripts/python.sh scripts/stream_invocation.py \
  --id abc123-invocation-id
# Note: FalconPy limitation - returns full conversation after completion, not true SSE
```

## Common Pitfalls / Counter-Rationalizations

| Thought | Reality |
|---------|---------|
| "I'll invoke the draft agent with invoke_agent.py" | **Use invoke_version.py for drafts.** `invoke_agent.py` only invokes the latest **published** version. To test draft/unpublished versions, use `invoke_version.py --agent-id <id> --version-id <version-uuid>`. |
| "I need a :draft-invocation scope to invoke drafts" | **No special scope needed.** The base `:invocation` scope covers both published and draft version invocations. Use `invoke_version.py` with the draft's version_id. |
| "I'll set a deadline 30 seconds from now for a complex task" | **Minimum 90 seconds required.** The API rejects `deadline_seconds` values below 90 with HTTP 400. Set realistic deadlines: 120+ for simple tasks, 300-600 for standard operations, 900+ for complex workflows. |
| "Max cost is just a suggestion" | **Max cost is a hard limit.** The invocation terminates when the limit (in credit cents: 100 = 1 Charlotte credit) is reached. Set appropriate budgets or omit the parameter for unbounded execution. |
| "I can pass any value for --max-cost" | **Capped at 10000 and integer-only.** The API rejects values above 10000 credit cents (100 Charlotte credits) with a 400, and rejects non-integer values (e.g. `10000.0`) with a generic "invalid ... invocation request" error. |
| "Cost is in the invocation response" | **Cost is in trace span attributes.** Fetch the trace (discovery skill) and read `cost.agg_credit_cents`/`cost.raw_credit_cents` off its spans -- there's no separate `cost` span_type. The invocation response doesn't include cost data. |
| "I can see costs in get_messages output" | **Cost is on the trace's spans.** Use the discovery skill to fetch the trace_id's spans and read `cost.*` attributes. Messages don't contain cost information. |
| "Invocation ID = agent ID" | **Different UUIDs.** Invocation ID is returned from invoke call; don't reuse agent ID. |
| "I'll poll messages every 100ms" | **Rate limit risk.** Use reasonable intervals (1-5s) or use streaming. |
| "Streaming uses /agentic-studio base" | **Wrong base.** Streaming uses `/agentic-studio-streaming/` base path. |
| "Tool outputs are in messages" | **Tool outputs are in trace spans.** Use `inspect_invocation.py` to see invocation waterfall, duration, and raw tool outputs. |
| "I need a dedicated endpoint to list invocations" | **Use spans APIs.** Query spans by `agent_id`, extract `invocation_id` from attributes. Use `list_invocations.py`. |

