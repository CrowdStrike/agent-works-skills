---
name: agents
description: >
  Manage Charlotte AI AgentWorks agent lifecycle.
  Create/update agents, query by filter, get agent details, publish agents, and ANALYZE execution patterns.
  **Analysis provides actionable prompt improvements based on actual execution traces, not just statistics.**
  Uses the native FalconPy `Agents` and `AgentVersions` classes.
  TRIGGER when user asks to create/update/query/publish/analyze/improve an agent.
  DO NOT TRIGGER for agent invocation (use invocation skill), knowledge bases (use knowledge-bases skill),
  or discovery (use discovery skill).
  DO NOT TRIGGER for enable/disable agent (publish-only per v1 scope) or delete operations.
  DO NOT TRIGGER for agents defined in a Falcon Foundry app (manifest.yml `ai.agents`, `foundry agents create`);
  foundry-redirect handles those.
version: 1.0.0
updated: 2026-08-21
tags: [agentworks, charlotte, agents, lifecycle, falcon, analysis, optimization]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
allowed-tools: Bash(cd *), Bash(../../scripts/python.sh:*)
metadata:
  category: agent-management
---

# Agents Lifecycle & Analysis

> **Read this first.**
>
> You are an AI assistant with expertise in Charlotte AI AgentWorks agent lifecycle management
> and **execution trace analysis for prompt optimization**.
> Your role is to help users create, update, query, get, publish, and **ANALYZE** agents
> using the native FalconPy `Agents` and `AgentVersions` service classes.
>
> **IMMEDIATE ACTIONS REQUIRED:**
> 1. Read this entire skill file before taking any action
> 2. Verify credentials are configured (TOML profile or env vars)
> 3. Only use the scripts documented below — never guess agent IDs or parameters
> 4. Run scripts via `cd ${CLAUDE_PLUGIN_ROOT}/skills/agents && ../../scripts/python.sh scripts/<script>.py`
> 5. Parse script output and present results clearly to the user
> 6. **When user asks to improve/optimize an agent, ALWAYS run analyze_agent.py first**
>
> **MUST NOT:**
> - Enable or disable agents (publish-only per v1 scope)
> - Delete agents (delete operations excluded)
> - Guess agent IDs — always query first
> - Give generic advice — always analyze actual execution traces first

## Running the scripts

All scripts must be invoked through the managed venv wrapper:

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/agents
../../scripts/python.sh scripts/<script_name>.py [args]
```

- **Claude Code**: `${CLAUDE_PLUGIN_ROOT}` is substituted with the plugin's install path before this text reaches the model. Use the braced form; a bare `$CLAUDE_PLUGIN_ROOT` is never exported into the Bash tool's shell.
- **Other hosts (Codex, Copilot CLI, Cursor, Antigravity)**: these don't set `CLAUDE_PLUGIN_ROOT`. `cd` to the folder you loaded this SKILL.md from (e.g. `~/.agents/skills/agents`) and run `../../scripts/python.sh scripts/<script_name>.py [args]` from there.

Uses the native FalconPy `Agents` and `AgentVersions` service classes.

## Prerequisites

- **Credentials**: Same as knowledge-bases skill (TOML profile or env vars)
- **API scopes**: `csrn:charlotte-ai:agent:definition` (read + write)
- **Python 3.14+**: Auto-managed
- **FalconPy 1.6.6+**: Provides the `Agents` service class (shared version floor enforced by `common/scripts/auth.py` across all skills, not just this one)

## Core Workflows

### 📋 Inspecting Agent Definitions Before Recommending

**CRITICAL:** When evaluating agents from Claude Code's available agent types list (visible in system reminders) or from tool metadata, you MUST inspect the full agent definition before recommending or using it.

#### ID Disambiguation - CRITICAL

**Use `version_group_id`, NOT `agent_id` (or just `id`):**

- **`version_group_id`** → The stable identifier across all versions of an agent → **USE THIS**
- **`agent_id` or `id`** → A specific version instance → Using this will fail with "failed to retrieve agent"

**Where to find `version_group_id`:**
- In agent types list metadata: Look for `version_group_id` field
- In tool discovery output: Listed as "Version group:" or `version_group_id`
- In agent metadata: Extract from `version_group` or `version_group_id` field

#### What Version You'll See - CRITICAL

When you inspect an agent using `version_group_id`, `agent_get.py` returns:

1. **Latest PUBLISHED version** (if one exists) ← Most common case
2. **Latest version** (if no published version exists) ← Draft only

**Important implications:**

- **Modifying a published agent creates a DRAFT version** → The draft is NOT returned by `agent_get.py`
- **Inspection shows production behavior** → You see what's actually running, not work-in-progress
- **Draft changes are invisible until published** → If an agent was recently modified but not published, you won't see those changes

**Example:**
```
Published agent: v1 (system prompt: "You are a security analyst...")
↓ User modifies agent
Draft version: v2 (system prompt: "You are an expert security analyst...")
↓ Inspect with agent_get.py
Result: Shows v1 (published), NOT v2 (draft)
↓ Publish v2
↓ Inspect with agent_get.py
Result: Shows v2 (now published)
```

**Example from tool discovery:**
```
• Vulnerability Response Agent
  - ID: agents/0ad0ec8a-c49a-4784-9541-8c931aa0a365/...  ← DON'T USE THIS
  - Version group: 4ff1fc7a-2181-405d-a6d7-95b549eb7a10    ← USE THIS
```

#### Workflow for Agent Inspection:

1. **Extract `version_group_id`** (NOT `agent_id` or `id`) from the metadata
2. **Get the complete definition**:
   ```bash
   cd ${CLAUDE_PLUGIN_ROOT}/skills/agents
   ../../scripts/python.sh scripts/agent_get.py --ids <version_group_id>
   ```
3. **Inspect the full definition**:
   - System prompt - does it match the task's needs?
   - Tools - does it have the right capabilities?
   - Model - is it appropriate for the complexity?
   - Knowledge base IDs - does it have relevant context?
4. **Only recommend/use** if the actual definition is a strong fit for the task

**Why:** Agent names and brief descriptions can be misleading. A "security-agent" might be configured for compliance checks, not threat hunting. The system prompt and tool configuration reveal the true capabilities.

**Example - Correct ID Usage:**
```bash
# Tool metadata shows:
#   ID: agents/0ad0ec8a-c49a-4784-9541-8c931aa0a365/vulnerability_response_agent
#   Version group: 4ff1fc7a-2181-405d-a6d7-95b549eb7a10

# ❌ WRONG - Using agent_id:
../../scripts/python.sh scripts/agent_get.py --ids 0ad0ec8a-c49a-4784-9541-8c931aa0a365
# Result: "failed to retrieve agent"

# ✅ CORRECT - Using version_group_id:
cd ${CLAUDE_PLUGIN_ROOT}/skills/agents
../../scripts/python.sh scripts/agent_get.py --ids 4ff1fc7a-2181-405d-a6d7-95b549eb7a10
# Result: Full agent definition with system prompt, tools, model

# Review output to confirm it has:
# - System prompt mentioning the specific security domain (e.g., "vulnerability triage")
# - Relevant tools (e.g., falcon_platform:get_vulnerabilities, not just generic tools)
# - Appropriate model for the task complexity
```

### 🔍 Analyze Agent Execution (START HERE for optimization)

**When to use:** User asks to "improve", "optimize", "debug", or "analyze" an agent.

1. **Analyze execution patterns** → `analyze_agent.py --agent-id <uuid> --days 7 --verbose`
   - Examines actual execution traces (not just statistics)
   - Identifies tool usage patterns, error contexts, version changes
   - Provides **actionable prompt improvements** with specific guidance
   - Shows performance anomalies and root causes

2. **Review recommendations** → Parse output for:
   - 🔧 **Unused tools** → Remove or add usage guidance to prompt
   - ⚠️ **Error-prone tools** → Add validation/error handling guidance
   - ⏱️ **Slow tools** → Add timeout warnings or optimization hints
   - 📊 **Common tool sequences** → Optimize prompt to guide workflows
   - 💭 **Excessive LLM calls** → Make prompt more decisive
   - 🔄 **Version changes** → Compare definitions to understand performance shifts

3. **Deep-dive specific traces** → Use invocation IDs from analysis with `inspect_invocation.py` (invocation skill)

4. **Apply improvements** → Update agent with `agent_upsert.py` using recommended prompt changes

**Example output:**
```
💡 Recommendations
1. 🔧 Unused tools: falcon_platform:get_host_details
   Either remove OR add: 'When user asks about host details, use falcon_platform:get_host_details to...'

2. ⚠️ Tool 'falcon_platform:search_hosts' has high error rate: 45%
   Add validation: 'Before calling search_hosts, verify filter syntax...'

3. 📊 Common tool patterns:
    - search_hosts → get_host_details → format_response (12x)
   Consider optimizing prompt to guide this workflow explicitly.
```

### Create/Update Agent

**CRITICAL FOR UPDATES:** When updating an existing agent, preserve existing configuration unless explicitly instructed otherwise:
1. **Get current agent details** → `agent_get.py --ids <agent-id>` → read current model, tools, model_config
2. **Only modify what's requested** → Keep existing model, tools, model_config unless user specifically asks to change them or you have strong reasoning
3. **Pass all fields to upsert** → Even unchanged fields must be included in the upsert call

**Workflow:**

1. **For updates: Read existing agent first** → `agent_get.py --ids <id>` → capture current config
2. **Discover prerequisites only if changing tools/model**:
   - `models_search.py --limit 50` (discovery skill) → capture a model ID if changing model
   - `tools_get.py --search "specific capability"` (discovery skill) → capture tool IDs if changing tools
   - If the tool family is known, filter it first with
     `tools_get.py --category <category> --search "specific capability"`; see the discovery
     skill's category guide. This avoids similarly named tools from unrelated providers.
     - ⚠️ **Use specific search terms**: "host search", "detection query", "vulnerability scan", "logscale"
     - ❌ **Avoid generic terms**: "falcon", "crowdstrike" (matches everything in Falcon platform, useless results)
3. **Query agents by filter** (if you don't have agent ID) → `agent_search.py --filter "active_version.name:~'topic'"` (substring, case-insensitive) → returns agent IDs
4. **Create or update agent** → `agent_upsert.py`:
   - Create: omit `--id`, specify all required fields (returns agent ID + version ID)
   - Update: include `--id <uuid>`, pass existing values for unchanged fields (creates new version, returns version ID)
5. **PROPOSE test invocation before publishing** → Offer to test the new version:
   - Use invocation skill: `invoke_version.py --agent-id <agent-id> --version-id <version-id> --message "Test prompt"`
   - Note: Draft versions CAN be invoked via `invoke_version.py` (no publish required for testing)
   - Poll for completion: `get_messages.py --id <invocation-id>`
   - If issues found, return to step 4 to adjust
6. **Publish agent** → `agent_publish.py --id <agent-uuid> --version-id <version-uuid>` → makes version the published default

Stop after each script; confirm with user before proceeding.

## Script Reference

| Script | Purpose | Key Flags |
|--------|---------|-----------|
| `agent_search.py` | Query agent IDs by FQL filter | `--filter "active_version.name:~'term'"` (substring), `--limit 100` |
| `agent_get.py` | Get agent entities by IDs | `--ids <id> [id...]` |
| `agent_list.py` | List agents as a table (Name/Description/Last modified/Last modified by/Created by/Status) | `--name-contains`, `--created-by`, `--modified-since`, `--modified-before`, `--status {published,unpublished}`, `--sort {name,updated_at}` (default `updated_at`), `--order {asc,desc}` (default `desc`), `--limit` |
| `agent_upsert.py` | Create or update an agent | `--name`, `--model`, `--system-prompt`, `--tools`, `--knowledge-base-ids`, optional `--id` |
| `agent_publish.py` | Publish agent (make invocable) | `--id <uuid>`, `--version-id <uuid>` |
| `analyze_agent.py` | Analyze execution patterns & suggest improvements | `--agent-id <uuid>`, `--days 7`, `--verbose` |

All scripts support `--help` and `--json`.

### Finding/listing agents by topic, name, date, or status

**For a plain topic/name substring search**, use `agent_search.py` with the `:~` fuzzy operator —
one API call, works at any tenant size:

```bash
../../scripts/python.sh scripts/agent_search.py --filter "active_version.name:~'root access'"
../../scripts/python.sh scripts/agent_search.py --filter "active_version.description:~'privilege escalation'"
```

**For combined criteria** (name substring + date range + publish status all at once), sorted
table output, or pagination — use `agent_list.py` instead, which pages through all agents and
filters/sorts client-side (slower on large tenants, but supports multiple simultaneous filters
that `agent_search.py`'s single `--filter` string doesn't conveniently combine):

```bash
../../scripts/python.sh scripts/agent_list.py --name-contains "root access"
../../scripts/python.sh scripts/agent_list.py --modified-since 2026-09-01 --status published
../../scripts/python.sh scripts/agent_list.py --limit 5  # most recently modified first (default sort)
```

See `references/fql-filters.md` for the full confirmed filter/operator behavior — it has a
"History" section on how the wrong conclusion got written into this doc twice before the `:~`
operator was found; read it before trusting a new negative finding of your own.

`--sort` only accepts `name` or `updated_at` — there is no `modified` value, even though the
flag is about modification date; the sortable field is named `updated_at`. Since `updated_at desc`
is already the default, "most recent N agents" needs only `--limit N`, no `--sort`/`--order`.

**Always paste the resulting table directly into your chat response — do not just point at the
tool output.** Script stdout is plain text to the harness; it is not markdown-rendered. Only text
you write directly in your own reply renders as an actual table for the user.

**Pagination:** `agent_list.py` defaults to `--limit 20` and prints a trailer line after the table:
`Showing 1-20 of 47 matching agent(s).` and, if more remain, `MORE_RESULTS_AVAILABLE
next_offset=20 remaining=27`. When you see that trailer, do NOT silently fetch/dump everything or
silently truncate — tell the user how many more there are and ask if they want the next page (e.g.
via AskUserQuestion or a plain question). If they say yes, re-run with `--offset <next_offset>`
(same filters/sort) to get the next page.

**Always paste the resulting table directly into your chat response — do not just point at the
tool output.** Script stdout is plain text to the harness; it is not markdown-rendered. Only text
you write directly in your own reply renders as an actual table for the user.

## Input/Output Format Types

Agents support structured input validation and output formatting:

### Input Formats
- **`unstructured`** (default): Free-form text or JSON input, no schema validation
- **`json_with_schema`**: JSON input validated against a JSON Schema

### Output Formats
- **`unstructured`** (default): Free-form text response
- **`html`**: HTML-formatted response
- **`markdown`**: Markdown-formatted response
- **`json`**: JSON-formatted response (no schema enforcement)
- **`json_with_schema`**: JSON response validated against a JSON Schema

### Usage Examples

**Add input validation:**
```bash
../../scripts/python.sh scripts/agent_upsert.py \
  --id <agent-id> \
  --input-format json_with_schema \
  --input-schema '{
    "type": "object",
    "properties": {
      "prompt": {"type": "string", "description": "User question"},
      "severity": {"type": "string", "enum": ["low", "medium", "high"]}
    },
    "required": ["prompt"]
  }'
```

**Request structured JSON output:**
```bash
../../scripts/python.sh scripts/agent_upsert.py \
  --id <agent-id> \
  --output-format json_with_schema \
  --output-schema '{
    "type": "object",
    "properties": {
      "risk_score": {"type": "number"},
      "recommendations": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["risk_score"]
  }'
```

## Usage Examples

### Query agents by name
```bash
../../scripts/python.sh scripts/agent_search.py --filter "active_version.name:~'Security'" --limit 10
```

### Get agent details
```bash
../../scripts/python.sh scripts/agent_get.py --ids <agent-id>
```

### Create a new agent
```bash
../../scripts/python.sh scripts/agent_upsert.py \
  --name "Root Access Hunter" \
  --description "Detects unauthorized root access" \
  --model bedrock.claude-4-6-sonnet \
  --system-prompt "You are a security agent that analyzes root access patterns..." \
  --tools <tool-id-1> <tool-id-2> \
  --knowledge-base-ids <kb-id>
```

### Update existing agent (creates new version)
```bash
# CRITICAL: Read current agent first to preserve existing config
../../scripts/python.sh scripts/agent_get.py --ids <agent-id>
# Note current: model, tools, model_config, knowledge_base_ids

# Update ONLY the system prompt, keep everything else the same
../../scripts/python.sh scripts/agent_upsert.py \
  --id <agent-id> \
  --system-prompt "Updated prompt with better instructions..." \
  --model <same-model-from-get> \
  --tools <same-tools-from-get> \
  --knowledge-base-ids <same-kbs-from-get>
# Pass ALL fields even if unchanged - API requires complete definition
```

### Publish agent
```bash
../../scripts/python.sh scripts/agent_publish.py \
  --id <agent-id> \
  --version-id <version-id>
```

### Analyze agent performance (last 7 days)
```bash
../../scripts/python.sh scripts/analyze_agent.py \
  --agent-id <agent-id> \
  --days 7 \
  --verbose
```

**What the analysis provides:**

1. **Version Detection** - Shows if agent definition changed
2. **Tool Usage Patterns** - Actual execution sequences (e.g., "search → get → format (12x)")
3. **Actionable Prompt Improvements** - Specific guidance with examples
4. **Error Context** - Which tools fail and why
5. **Performance Anomalies** - Version comparison with root cause
6. **Missing Capabilities** - Suggests additional tools based on patterns

See "Core Workflows → Analyze Agent Execution" above for detailed examples.

## Common Pitfalls / Counter-Rationalizations

| Thought | Reality |
|---------|---------|
| "The agent name tells me what it does" | **Inspect first.** Names can be misleading. Get the full definition with `agent_get.py --ids <version_group_id>` to see the actual system prompt, tools, and capabilities before recommending. |
| "I'll use the agent ID from the tool metadata" | **Use version_group_id instead.** The `agent_id` or `id` field refers to a specific version instance. Use `version_group_id` to retrieve the current definition. Using `agent_id` returns "failed to retrieve agent". |
| "I just modified the agent, so inspection will show my changes" | **Modifications create drafts.** `agent_get.py` returns the latest **published** version, not draft versions. Your changes are invisible until you publish them with `agent_publish.py`. |
| "I'll guess the agent ID" | **Query first.** Agent IDs are UUIDs; guessing fails. Use `agent_search.py`. |
| "I can update just the prompt" | **Read agent first, pass all fields.** When updating, get current config with `agent_get.py`, then pass ALL fields (model, tools, model_config, etc) even if unchanged. Omitted fields may be lost. |
| "I'll give generic optimization advice" | **Analyze first.** Run `analyze_agent.py` to get actionable insights from actual traces. Generic advice doesn't account for version changes, tool patterns, or error contexts. |
| "The agent is slow because of the model" | **Check execution patterns.** Could be tool sequences, excessive LLM calls, or unused/misconfigured tools. Analysis shows root cause. |
| "I'll enable the agent after publishing" | **Publish-only scope.** No enable/disable in v1. Publish = make invocable. |
| "I can delete an agent" | **Delete excluded.** No DELETE operations per v1 design. Agents persist. |
| "Model ID is just the model name" | **Model ID is a UUID.** Query models first with discovery skill, or user provides the UUID. |
| "agent_upsert returns only the agent ID" | **It also returns the version ID.** The version ID is required for `agent_publish.py --version-id`. |
| "Publish just needs the agent ID" | **Publish needs BOTH agent ID and version ID.** Use `PATCH` with `params={id}` and `body={version_id, is_published:true}`. |
| "I need to list invocations to analyze an agent" | **Use spans APIs instead.** Query spans by `agent_id`, hydrate them, extract `invocation_id` from attributes. Use `analyze_agent.py`. |
| "I'll filter agent_search by name" | **Top-level `name` doesn't work; `active_version.name:~'term'` does — use that.** `name:'...'` on `queries/agents/v2` silently matches nothing regardless of quoting/wildcard. The correct nested field is `active_version.name`, and the correct substring operator is `:~` (fuzzy, case-insensitive, matches anywhere) — NOT wildcard `*'...'` syntax, which also silently returns zero on this endpoint. `active_version.description:~'term'` works too. See `references/fql-filters.md` (which itself was wrong twice before this was nailed down — read the "History" section there before trusting a new negative finding). |
| "I'll pass multiple ids to agent_get as a comma-joined string" | **Must be a real list param.** `params={"ids": ",".join(ids)}` gets treated as one literal id and fails with "failed to retrieve agent". Use `params={"ids": ids}` (a list). See `references/api-reference.md`. |
| "I'll show the user a table by printing it from the script" | **Tool stdout isn't markdown-rendered.** Paste the table into your own chat response text, or the user just sees raw pipe-delimited text. |
| "I'll pass `--sort modified` since the flag is about modification date" | **`--sort` only accepts `name` or `updated_at`.** The sortable field is named `updated_at`, not `modified`, even though `--modified-since`/`--modified-before` exist as separate filter flags. Run `agent_list.py --help` if unsure, don't infer flag values from naming patterns. |
| "I'll write a severity/status/category enum from what sounds right" | **Query the tenant's actual values first.** A rewritten system prompt or `--input-schema`/`--output-schema` that hardcodes an assumed enum (e.g. `"enum": ["low", "medium", "high"]`) can silently mismatch the tenant's real configured values, breaking the workflow it was meant to automate. Check real invocation inputs/outputs (e.g. via `analyze_agent.py`, or `inspect_invocation.py` on a known trace) or whatever source of truth the workflow already uses before encoding an enum. |

## Reading Guide

| Task | Reference Doc |
|------|---------------|
| API endpoints and parameters | `references/api-reference.md` |
| FQL filter syntax | `references/fql-filters.md` |
| OAuth 2.0 + scopes | `../setup/SKILL.md` |

## FalconPy classes

This skill uses the native typed `Agents` class (`query_studio_agents`, `get_studio_agents`,
`create_or_update_agent`, `update_agent`) and `AgentVersions`, via `auth.get_agents_client()` and
`auth.call_native()`.

