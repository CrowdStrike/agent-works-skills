---
name: discovery
description: >
  Discover available models, tools, templates, agent versions, and trace spans in Charlotte AI AgentWorks.
  Read-only queries using native FalconPy classes (`Models`, `Tools`, `AgentTemplates`, `AgentVersions`, `Spans`).
  TRIGGER when user asks to list/query/discover models, tools, templates, versions, or spans.
  DO NOT TRIGGER for agent creation/invocation (use agents/invocation skills) or knowledge bases.
version: 1.0.0
updated: 2026-08-21
tags: [agentworks, charlotte, discovery, models, tools, templates, falcon]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
allowed-tools: Bash(cd *), Bash(../../scripts/python.sh:*)
metadata:
  category: discovery
---

# Discovery

> **Read this first.**
>
> You are an AI assistant helping users discover Charlotte AI AgentWorks resources (models, tools, templates,
> versions, spans). All operations are **read-only queries** using native FalconPy classes (`Models`, `Tools`, `AgentTemplates`, `AgentVersions`, `Spans`).
>
> **IMMEDIATE ACTIONS REQUIRED:**
> 1. Read this entire skill file
> 2. Verify credentials configured
> 3. Run scripts via `cd ${CLAUDE_PLUGIN_ROOT}/skills/discovery && ../../scripts/python.sh scripts/<script>.py`
>
> **MUST NOT:**
> - 
> - Modify discovered resources (read-only skill)

## Running the scripts

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/discovery
../../scripts/python.sh scripts/<script_name>.py [args]
```

- **Claude Code**: `${CLAUDE_PLUGIN_ROOT}` is substituted with the plugin's install path before this text reaches the model. Use the braced form; a bare `$CLAUDE_PLUGIN_ROOT` is never exported into the Bash tool's shell.
- **Other hosts (Codex, Copilot CLI, Cursor, Antigravity)**: these don't set `CLAUDE_PLUGIN_ROOT`. `cd` to the folder you loaded this SKILL.md from (e.g. `~/.agents/skills/discovery`) and run `../../scripts/python.sh scripts/<script_name>.py [args]` from there.

## Prerequisites

- **Credentials**: Same as other skills
- **API scopes**: `csrn:charlotte-ai:agent:definition` (read), `:template`, `:metrics`
- **FQL Knowledge**: Span queries use Falcon Query Language (FQL) syntax - see `docs/FQL_SYNTAX_REFERENCE.md`

## Core Workflow

All discovery scripts follow a two-step pattern:

### Step 1: Query for IDs
- **Query models** → `models_search.py --limit 50` → returns model IDs (filter by ID only, not name)
- **Query tools** → `tools_search.py --filter 'name:"..."'` → returns tool IDs
- **Query templates** → `templates_search.py --filter 'category:"..."'` → returns template IDs
- **Query versions** → `versions_search.py --filter 'agent_id:"..."'` → returns version IDs
- **Query spans** → `spans_search.py --filter 'trace_id:"..."'` → returns span IDs

### Step 2: Hydrate entities (for full details)
- **Get agent entities** → `agent_get.py --ids <id1> <id2>` (agents skill)
- **Get span entities** → `spans_get.py --ids <id1> <id2>` (discovery skill)

Query endpoints return opaque IDs; entity endpoints return full details.

## Inspecting Agent Definitions Before Recommending

**CRITICAL:** When evaluating agents from Claude Code's available agent types list (visible in system reminders) or from tool discovery output, you MUST inspect the full agent definition before recommending or using it.

### ID Disambiguation - CRITICAL

**Use `version_group_id`, NOT `agent_id` (or just `id`):**

- **`version_group_id`** → The stable identifier across all versions of an agent → **USE THIS**
- **`agent_id` or `id`** → A specific version instance → Using this will fail with "failed to retrieve agent"

**Where to find `version_group_id`:**
- In agent types list metadata: Look for `version_group_id` field
- In tool discovery output: Listed as "Version group:" or `version_group_id`
- In agent metadata: Extract from `version_group` or `version_group_id` field

### What Version You'll See - CRITICAL

When you inspect an agent using `version_group_id`, the agents skill's `agent_get.py` returns:

1. **Latest PUBLISHED version** (if one exists) ← Most common case
2. **Latest version** (if no published version exists) ← Draft only

**Important implications:**

- **Modifying a published agent creates a DRAFT version** → The draft is NOT returned
- **Inspection shows production behavior** → You see what's actually running, not work-in-progress
- **Draft changes are invisible until published** → Recent modifications won't appear until published

### Workflow for Agent Inspection:

1. **Extract `version_group_id`** (NOT `agent_id` or `id`) from the metadata
2. **Use the agents skill** to get the complete definition:
   ```bash
   cd ${CLAUDE_PLUGIN_ROOT}/skills/agents
   ../../scripts/python.sh scripts/agent_get.py --ids <version_group_id>
   ```
3. **Inspect the full definition** - review system prompt, tools, model, capabilities
4. **Only recommend/use** if the actual definition is a strong fit for the task

**Why:** Agent names and brief descriptions in the types list can be misleading. The actual system prompt, tool configuration, and capabilities determine if an agent is suitable. Don't guess based on names alone.

**Example - Correct vs Incorrect ID:**
```
Tool metadata shows:
  ID: agents/0ad0ec8a-c49a-4784-9541-8c931aa0a365/...  ← DON'T USE
  Version group: 4ff1fc7a-2181-405d-a6d7-95b549eb7a10    ← USE THIS

# ❌ WRONG:
agent_get.py --ids 0ad0ec8a-c49a-4784-9541-8c931aa0a365
# Returns: "failed to retrieve agent"

# ✅ CORRECT:
agent_get.py --ids 4ff1fc7a-2181-405d-a6d7-95b549eb7a10
# Returns: Full agent definition
```

## Script Reference

All scripts are nearly identical (just different paths):

| Script | Purpose | Endpoint |
|--------|---------|----------|
| `models_search.py` | Query available models | `/queries/models/v1` |
| `tools_search.py` | Query available tools | `/queries/tools/v1` |
| `templates_search.py` | Query agent templates | `/queries/agent-templates/v1` |
| `versions_search.py` | Query agent versions | `/queries/agent-versions/v1` |
| `spans_search.py` | Query trace spans (IDs only) | `/queries/spans/v1` |
| `spans_get.py` | Get full span entities | `/entities/spans/v1` |

## Usage Examples

### Query available models
```bash
../../scripts/python.sh scripts/models_search.py --limit 10
# Returns model IDs (UUIDs)
# NOTE: Filter only works by ID, not by name. Query all and filter client-side.
```

### Query tools by name or description
```bash
# DEPRECATED: tools_search.py uses /queries endpoint which may be unstable
# Use tools_get.py instead for client-side filtering

../../scripts/python.sh scripts/tools_get.py --search "logscale query" --verbose
# Searches across name, description, and category
# Automatically filters out overly-broad terms like "falcon", "crowdstrike"
# Returns full tool entities with descriptions

# Legacy approach (may return 500 errors):
../../scripts/python.sh scripts/tools_search.py --filter 'name:"logscale"' --limit 20
```

### Query tools by category

Use `tools_get.py --category` for an exact, case-sensitive category match. Prefer category
filtering when the requested capability maps to one of the families below; add `--search`
to narrow by name or description within that family.

```bash
../../scripts/python.sh scripts/tools_get.py \
  --category falcon_platform \
  --search "device query" \
  --limit 100
```

| Category | Use it to discover |
|----------|--------------------|
| `charlotte-mcp` | Curated Charlotte AI assistants for security tasks such as LogScale queries, detection triage, threat intelligence, malware analysis, documentation, and remediation guidance. |
| `agents` | Published Charlotte AI AgentWorks agents exposed as callable tools. Filter here when one agent should delegate a specialized task to another agent. |
| `gce` | Generic GCE tools, if present. This category currently returns no tools; do not confuse it with tool IDs prefixed `mcp/gce/`, whose actual categories are more specific. |
| `fusion_workflows` | On-demand Fusion workflow tools that execute a configured workflow and return its execution ID and declared outputs. |
| `falcon_platform` | First-party Falcon platform operations for hosts, detections, incidents, cases, identity, intelligence, LogScale, workflows, and response actions. |
| `integrations` | Operations supplied by configured third-party Fusion integrations; these commonly require an integration credential/configuration ID. |
| `Collections` | Create, get, list, search, and delete objects in agent-managed collections. The category name is case-sensitive. |
| `action_requests` | Human-in-the-loop actions that pause execution to request clarification. |
| `foundry-user-mcp` | Tools from user-configured MCP servers connected through Foundry, such as Jira, Confluence, Slack, or Microsoft documentation tools. Availability is tenant-specific. |

Category availability is tenant-specific. A zero-result category is not an error; report it
and only broaden the search after explaining that exact category matching found nothing.

**⚠️ IMPORTANT - Avoid Overly-Broad Search Terms:**
- ❌ DON'T search for: "falcon", "crowdstrike", "cs" (too generic, matches everything)
- ✅ DO search for: specific capabilities like "host search", "detections", "vulnerability", "logscale query"
- Think: "What unique capability am I looking for?" not "What product is this in?"

### Query agent templates
```bash
../../scripts/python.sh scripts/templates_search.py --filter 'category:"security"'
```

### Query agent versions
```bash
../../scripts/python.sh scripts/versions_search.py \
  --filter 'agent_id:"<agent-id>"' \
  --limit 10
```

### Query spans by trace ID
```bash
../../scripts/python.sh scripts/spans_search.py \
  --filter "trace_id:'abc123'+start_time:>='now-24h'" \
  --limit 100
# Note: Time filter required (start_time or end_time)
# Note: Use FQL syntax - operators are :>=, :<=, :<, :>, values in single quotes
```

### Query spans by agent ID
```bash
../../scripts/python.sh scripts/spans_search.py \
  --filter "(attributes.aw_agent.id:'<agent-id>'+start_time:>='now-7d')+span_type:['aw_agent','aw_eval_run_started']" \
  --limit 500
# Note: FQL uses + for AND, , for OR
# Note: Wrap complex filters in parentheses
# Note: Filter by span_type for efficiency (agent-level spans only)
```

### Hydrate span IDs to full entities
```bash
# First get span IDs from query (--json: the default output is a header plus an indented list)
SPAN_IDS=$(../../scripts/python.sh scripts/spans_search.py \
  --filter "trace_id:'abc123'+start_time:>='now-24h'" --json | jq -r '.resources[]')

# Then hydrate to full entities (SPAN_IDS is intentionally unquoted so each ID is its own argument)
../../scripts/python.sh scripts/spans_get.py --ids $SPAN_IDS
# Shows full span details: name, type, duration, status, credits, attributes
```

## Common Pitfalls

| Thought | Reality |
|---------|---------|
| "I'll use the agent ID from tool metadata to inspect it" | **Use version_group_id instead.** The `agent_id` field refers to a specific version. Use `version_group_id` to retrieve the current published definition. |
| "I just saw someone modify an agent, so inspection will show those changes" | **Modifications create drafts.** Agent inspection returns the latest **published** version, not draft versions. Changes are invisible until published. |
| "A tool ID beginning with `mcp/gce/` has category `gce`" | **ID namespace and category differ.** Filter the entity's exact category, such as `falcon_platform`, `fusion_workflows`, or `integrations`. |
| "Category matching ignores case" | **Treat categories as case-sensitive.** In particular, use `Collections` with a capital `C`. |
| "Discovery = get entities" | **Query IDs only (except `spans_get.py`).** Most scripts return IDs; use `GET /entities/...` to hydrate. |
| "Model name = model ID" | **Model ID is UUID.** Discovery returns IDs; filter only works by ID, not name. Query all models and grep client-side. |
| "I can filter models by name" | **Models filter only works by ID.** Query all (`--limit 100`) and filter client-side or use known model IDs. |
| "Span queries don't need time filters" | **Time filter REQUIRED.** The API enforces 90-day max age and adds default `start_time>=<90d-ago>` if missing. See `docs/SPAN_TIME_CONSTRAINTS.md` for full rules. |
| "I can query spans from 6 months ago" | **90-day hard limit.** Spans older than 90 days cannot be queried. Use `start_time:>=now-90d` for maximum history. |

## Reading Guide

| Task | Reference Doc |
|------|---------------|
| **FQL filter syntax (REQUIRED)** | `docs/FQL_SYNTAX_REFERENCE.md` |
| API endpoints and parameters | `references/api-reference.md` |
| FQL filter syntax | `references/fql-filters.md` |
| OAuth 2.0 + scopes | `../setup/SKILL.md` |
| **Span time constraints (CRITICAL)** | `docs/SPAN_TIME_CONSTRAINTS.md` |
| Span filter debugging | `docs/SPAN_FILTER_DEBUGGING.md` |

**Allowed (all read-only):**
- `GET /agentic-studio/queries/models/v1`
- `GET /agentic-studio/queries/tools/v1`
- `GET /agentic-studio/queries/agent-templates/v1`
- `GET /agentic-studio/queries/agent-versions/v1`
- `GET /agentic-studio/queries/spans/v1` (requires time filter)
- `GET /agentic-studio/entities/spans/v1` (hydrate span IDs)
