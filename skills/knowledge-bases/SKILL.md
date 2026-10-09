---
name: knowledge-bases
description: >
  Manage Charlotte AI AgentWorks knowledge bases.
  Create/update/query KBs, upload/download files, and view audit events using native FalconPy classes.
  TRIGGER when user asks to create/query/update a knowledge base, upload files to a KB,
  download KB files, or view KB audit events.
  DO NOT TRIGGER for agent creation, agent invocation, or model/tool discovery —
  use agents, invocation, or discovery skills.
  DO NOT TRIGGER for knowledge bases defined in a Falcon Foundry app (manifest.yml `ai.knowledge_bases`,
  `foundry knowledge-bases create`); foundry-redirect handles those.
version: 1.0.0
updated: 2026-08-21
tags: [agentworks, charlotte, knowledge-base, files, audit, falcon]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
allowed-tools: Bash(cd *), Bash(../../scripts/python.sh:*)
metadata:
  category: data-management
---

# Knowledge Bases

> **Read this first.**
>
> You are an AI assistant with expertise in Charlotte AI AgentWorks knowledge base operations.
> Your role is to help users create, query, update, upload files to, download from, and audit
> knowledge bases using native FalconPy
> service classes (`KnowledgeBases`, `KnowledgeBaseFiles`, `KnowledgeBaseAuditEvents`).
>
> **IMMEDIATE ACTIONS REQUIRED:**
> 1. Read this entire skill file before taking any action
> 2. Verify credentials are configured (TOML profile or env vars)
> 3. Only use the scripts documented below — never guess API parameters
> 4. Run scripts via `cd ${CLAUDE_PLUGIN_ROOT}/skills/knowledge-bases && ../../scripts/python.sh scripts/<script>.py`
> 5. Parse script output and present results clearly to the user
>
> **MUST NOT:**
> - Delete KBs or files (delete operations excluded from v1 scope)
> - Guess knowledge_base_id or file IDs — always query first

## Running the scripts

All scripts must be invoked through the managed venv wrapper so dependencies (FalconPy) are available:

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/knowledge-bases
../../scripts/python.sh scripts/<script_name>.py [args]
```

- **Claude Code**: `${CLAUDE_PLUGIN_ROOT}` is substituted with the plugin's install path before this text reaches the model. Use the braced form; a bare `$CLAUDE_PLUGIN_ROOT` is never exported into the Bash tool's shell.
- **Other hosts (Codex, Copilot CLI, Cursor, Antigravity)**: these don't set `CLAUDE_PLUGIN_ROOT`. `cd` to the folder you loaded this SKILL.md from (e.g. `~/.agents/skills/knowledge-bases`) and run `../../scripts/python.sh scripts/<script_name>.py [args]` from there.

The wrapper auto-builds the venv on first use if the SessionStart hook didn't run.

## Prerequisites

- **Credentials**: Charlotte AI AgentWorks TOML (`~/.cache/crowdstrike-charlotte-ai-agentworks/credentials.toml`) OR env vars (`FALCON_CLIENT_ID`, `FALCON_CLIENT_SECRET`, optional `FALCON_BASE_URL`). Run `/crowdstrike-charlotte-ai-agentworks:setup` if needed.
- **API scopes**: `csrn:charlotte-ai:agent:knowledge-base` (read + write)
- **Python 3.14+**: Auto-managed by the venv setup
- **FalconPy 1.6.6+**: Provides the native `KnowledgeBases`, `KnowledgeBaseFiles`, `KnowledgeBaseAuditEvents` classes (`common/scripts/auth.py` enforces a shared 1.6.6+ floor across all skills)

## Core Workflow

1. **Search/browse KBs by name or description substring** → `kb_list.py --contains "topic"` → table of matches, no exact-syntax guessing needed
2. **Query KB IDs by exact/known filter** → `kb_search.py --filter "name:'my-kb'"` (single-quoted FQL values only — see `references/fql-filters.md`) → returns KB IDs
3. **Get KB details** → `kb_get.py --ids <id1> <id2>` → full KB entities
4. **Create or update KB** → `kb_upsert.py --name "..." --description "..."` (optional `--id` for update)
5. **Upload file** → `kb_file_upload.py --kb-id <id> --file <path> --description "..."`
6. **List/browse files in a KB** → `kb_files_list.py --kb-id <id>` → table of files with size, type, status
7. **Download file** → `kb_file_download.py --kb-id <id> --file-id <id> --output <path>`
8. **View audit events** → `kb_audit.py --kb-id <id> --limit 50`

Stop after each script; confirm with user before proceeding to the next step.

## Script Reference

| Script | Purpose | Key Flags |
|--------|---------|-----------|
| `kb_list.py` | Browse/search KBs by name+description substring (table output) | `--name-contains`, `--contains` (name OR description), `--modified-since`, `--sort`, `--limit` |
| `kb_search.py` | Query KB IDs by exact/known FQL filter | `--filter "name:'...'"` (single-quoted!), `--limit 100` |
| `kb_get.py` | Get KB entities by IDs | `--ids <id> [id...]` |
| `kb_upsert.py` | Create or update a KB | `--name`, `--description`, optional `--id` (update) |
| `kb_file_upload.py` | Upload file to a KB | `--kb-id`, `--file <path>`, `--description` |
| `kb_files_list.py` | List files in a KB (table output) | `--kb-id`, `--name-contains` |
| `kb_file_download.py` | Download file from KB | `--kb-id`, `--file-id`, `--output <path>` |
| `kb_audit.py` | Query KB audit events | `--kb-id`, `--limit 100` |

All scripts support `--help` for full arg lists and `--json` for raw JSON output.

**When the user asks to find/list/browse KBs by topic** (not an exact known name), use
`kb_list.py --contains "topic"`, not `kb_search.py`. `kb_search.py`'s `name` filter only works
for exact or wildcard-substring matches you already know how to spell, and there's no
server-side full-text search across name+description.

## Usage Examples

### Search/browse KBs by topic
```bash
../../scripts/python.sh scripts/kb_list.py --contains "root access"
# Table of matches across name AND description, paginated; use this when you don't
# already know the exact KB name.
```

### Query KBs by exact name
```bash
../../scripts/python.sh scripts/kb_search.py --filter "name:'Insurance'" --limit 10
# Returns KB IDs. Values MUST be single-quoted -- name:"Insurance" silently matches nothing.
```

### Get KB details
```bash
../../scripts/python.sh scripts/kb_get.py --ids abc123-kb-id
```

### Create a new KB
```bash
../../scripts/python.sh scripts/kb_upsert.py \
  --name "Insurance Terms & Conditions" \
  --description "Romanian insurance policy documentation"
# Returns KB ID
```

### Update existing KB
```bash
../../scripts/python.sh scripts/kb_upsert.py \
  --id abc123-kb-id \
  --description "Updated description..."
```

### Upload file to KB
```bash
../../scripts/python.sh scripts/kb_file_upload.py \
  --kb-id abc123-kb-id \
  --file /path/to/document.pdf \
  --description "Insurance policy terms"
# Returns file ID
```

### List files in a KB
```bash
../../scripts/python.sh scripts/kb_files_list.py --kb-id abc123-kb-id
# Table: name, description, size, content type, status, last modified, modified by, file ID
```

### Download file from KB
```bash
../../scripts/python.sh scripts/kb_file_download.py \
  --kb-id abc123-kb-id \
  --file-id file123 \
  --output ./downloaded-policy.pdf
```

### View KB audit events
```bash
../../scripts/python.sh scripts/kb_audit.py \
  --kb-id abc123-kb-id \
  --limit 50
# Shows file uploads, KB updates, etc.
```

### Attach KB to agent (see agents skill)
```bash
cd ../agents
../../scripts/python.sh scripts/agent_upsert.py \
  --id <agent-id> \
  --knowledge-base-ids abc123-kb-id
```

## Common Pitfalls / Counter-Rationalizations

| Thought | Reality |
|---------|---------|
| "I'll guess the KB ID" | **Query first.** KB IDs are UUIDs; guessing fails 100%. Use `kb_search.py` or `kb_list.py`. |
| "I'll skip the filter and list all KBs" | **Always filter.** Unfiltered queries on large CIDs can time out or return truncated results. Use `--filter "name:'...'"` or a date range, or use `kb_list.py` which paginates for you. |
| "`--filter 'name:\"my-kb\"'` with double quotes should work" | **Silently wrong.** FQL string values must be single-quoted (`name:'my-kb'`). Double quotes return 200 OK with zero results — no error — which looks identical to "no such KB exists." See `references/fql-filters.md`. |
| "I searched by name and got nothing, so no matching KB exists" | **Rule out syntax first.** `name` filtering does work on this endpoint (unlike agents), but only exact/wildcard matches with correct quoting. Before concluding nothing exists, either fix the quoting or use `kb_list.py --contains "..."` for substring search across name+description. |
| "File upload is just POST + JSON body" | **Multipart/form-data required.** `kb_file_upload.py` uses FalconPy's multipart handling; manual curl won't work without exact boundary formatting. |
| "I can delete a KB by setting is_deleted:true" | **Delete out of scope.** Per v1 plan, no delete operations. KBs persist once created. |
| "I'll list a KB's files with `kb_search.py --kb-id`" | **That flag doesn't exist.** Use `kb_files_list.py --kb-id <id>` instead. |
| "I'll pass just `ids` to get file entities" | **`knowledge_base_id` is also required.** `EntitiesKnowledgeBaseFilesV1(ids=[...])` alone fails with "knowledge_base_id parameter is required" — pass both, e.g. `EntitiesKnowledgeBaseFilesV1(knowledge_base_id=kb_id, ids=[...])`. Matches what the Falcon UI itself sends. |
| "The native FalconPy class means I don't need auth.py" | **Auth.py is required.** It builds the clients with credential resolution. Never instantiate `KnowledgeBases()` directly in scripts. |

## Reading Guide

For deep dives, see `references/`:

| Task | Reference Doc |
|------|---------------|
| Full endpoint table (methods, paths, params) | `references/api-reference.md` |
| FQL filter syntax + confirmed examples (the double-quote trap, substring matching) | `references/fql-filters.md` |
| OAuth 2.0 flow + scope requirements | `../setup/SKILL.md` |

Load these on demand — don't read upfront.

## FalconPy Native Support

This skill uses **native typed FalconPy service classes**. Benefits:
- Typed methods: `client.EntitiesKnowledgeBasesCreateV1(body={...})`
- Auto-parameter validation
- Built-in pagination + error handling


