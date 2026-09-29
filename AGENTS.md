# AGENTS.md

A tool-agnostic guide to the `agent-works-skills` plugin for AI coding assistants that are **not** Claude Code (Codex, GitHub Copilot, Cursor, Antigravity, and others). Claude Code users get the same content via the plugin system and [CLAUDE.md](./CLAUDE.md); this file lets any agent use the skills directly.

## What This Is

`agent-works-skills` lets an assistant create, configure, invoke, and analyze **Charlotte AI AgentWorks** agents through the Falcon API, manage their knowledge bases, and discover the models, tools, templates, and trace spans available to them.

Agents created and managed directly through the API belong to this plugin. Agents defined inside a Falcon Foundry app's `manifest.yml` (`ai.agents`) are part of that app — use the `foundry-skills` plugin for those.

## Prerequisites

- **Python** 3.14+
- **crowdstrike-falconpy** 1.6.6+ (`pip install crowdstrike-falconpy`)
- **Falcon API OAuth 2.0 client credentials** with the `charlotte-ai-agent-definition:read` and `charlotte-ai-agent-definition:write` scopes

Configure credentials with the setup command (writes the TOML profile at `~/.cache/crowdstrike-agent-works/credentials.toml`):

```
/crowdstrike-agent-works:setup
```

For CI or a one-off override, set environment variables instead:

```bash
export FALCON_CLIENT_ID=your_client_id_here
export FALCON_CLIENT_SECRET=your_client_secret_here
# export FALCON_BASE_URL=https://api.crowdstrike.com  # US-1 (default)
```

Verify credentials:

```bash
python common/scripts/auth.py
```

## Repository Structure

```
skills/
  agent-works/      Orchestrator skill — SKILL.md decision tree, routes to the skills below
  agents/           agent_upsert/get/list/search/publish, analyze_agent, compare_versions
  invocation/       invoke_agent/version, get_messages, stream_invocation, cancel_invocation, list_invocations, inspect_invocation
  knowledge-bases/  kb_upsert/get/list/search, kb_files_list, kb_file_upload/download, kb_audit
  discovery/        models/tools/templates/versions/spans search and get
  setup/            SKILL.md — interactive credential setup
  foundry-redirect/ SKILL.md — points Foundry-app agent requests to foundry-skills
common/scripts/     auth.py (shared API auth), discovery_helpers.py, invocation_helpers.py, formatting.py, waterfall.py, _bootstrap.py
hooks/              Plugin hooks (venv bootstrap, intent routing)
references/         Cross-skill reference docs
```

Each skill's `SKILL.md` is plain markdown with YAML frontmatter — read it directly for the workflow, script reference, and pitfalls. Reference docs live under each skill's `references/` directory.

## Skills Ecosystem

| Skill | Use it to |
|-------|-----------|
| `agent-works` | Understand routing between the skills (read this first) |
| `agents` | Create, update, query, publish, and analyze agents |
| `invocation` | Invoke agents (published or a specific version), read messages, cancel, inspect traces |
| `knowledge-bases` | Manage knowledge bases, their files, and audit events |
| `discovery` | Find models, tools, templates, agent versions, and trace spans |
| `setup` | Configure credentials |
| `foundry-redirect` | Decline agent/KB requests for a Foundry app and point to `foundry-skills` |

## Using Without the Claude Code Plugin System

The skills are markdown instructions plus Python scripts — no plugin runtime is required.

1. **Read the SKILL.md** for the task you are doing (e.g., `skills/agents/SKILL.md` to create an agent).
2. **Run the scripts** from the skill's folder through the managed-venv wrapper:
   `cd skills/<skill> && ../../scripts/python.sh scripts/<script>.py --help`. `${CLAUDE_PLUGIN_ROOT}` (set only by Claude Code) is not required. A script started with a bare `python` that lacks FalconPy re-executes itself through the wrapper, which builds the venv on first use.
3. **Follow the discipline rules**, which are not optional:
   - Never guess agent, version, knowledge base, file, or invocation IDs — query first (`agent_search.py`, `kb_search.py`, …).
   - Tool IDs come from `tools_get.py`/`tools_search.py`, and model IDs from `models_search.py`; they are opaque strings, not UUIDs.
   - A draft version cannot be invoked with `invoke_agent.py`; use `invoke_version.py` with the version ID. Publish with `agent_publish.py` before using `invoke_agent.py`.
   - Delete operations and agent enable/disable are out of scope for v1.
   - Look at real traces (`analyze_agent.py`, `inspect_invocation.py`) before suggesting prompt changes.

## Lifecycle at a Glance

```
discover models/tools  →  upsert agent  →  invoke a version  →  inspect / analyze  →  refine  →  publish
      (discovery)           (agents)          (invocation)          (invocation, agents)  (agents)   (agents)
```

Carry the artifacts forward: `agent_upsert.py` returns an agent ID and a version ID, invocation returns an invocation ID, and `inspect_invocation.py` resolves the trace from that invocation ID.
