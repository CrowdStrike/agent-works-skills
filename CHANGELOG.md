# Changelog

All notable changes to the Charlotte AI AgentWorks Skills plugin.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-06

### Added
- Initial release of the agentworks-skills plugin
- **Knowledge Bases** skill with full CRUD operations
  - Create, query, get, and update knowledge bases via native FalconPy classes
  - File upload/download with multipart support
  - Audit event querying
  - 8 Python scripts: kb_search, kb_list, kb_get, kb_upsert, kb_file_upload, kb_file_download, kb_files_list, kb_audit
- **Agent lifecycle** skill
  - Create/update agents via native `Agents` class
  - Query and get agent details
  - Publish agents (no enable/disable per v1 scope)
  - Analyze execution patterns and suggest prompt improvements
- **Agent invocation** skill
  - Invoke published agents and specific versions via native `AgentInvocation`/`Stream` classes
  - Stream invocation results (the `Stream` class polls and returns the full conversation; no token-by-token SSE)
  - Get messages and cancel in-flight invocations via `AgentInvocation.update_agent_invocation`
- **Discovery** skill
  - Query models, tools, templates, agent versions, and trace spans via native FalconPy classes
    (`Models`, `Tools`, `AgentTemplates`, `AgentVersions`, `Spans`)
- **Setup** skill - credential configuration guide
- **Orchestrator** skill - intent routing and decision tree
- Credential resolution from environment variables or TOML profile
  - TOML file at `~/.cache/crowdstrike-charlotte-ai-agentworks/credentials.toml`
  - Environment variable support: `FALCON_CLIENT_ID`, `FALCON_CLIENT_SECRET`, `FALCON_BASE_URL`
- Managed Python venv (Python 3.14+) with auto-bootstrap
  - SessionStart hook builds venv at `~/.cache/crowdstrike-charlotte-ai-agentworks/venv`
  - Lazy fallback if hook doesn't fire
  - FalconPy 1.6.6+ from PyPI
- Multi-assistant support
  - Claude Code (primary)
  - Codex, Copilot CLI, Cursor, Antigravity (via Agent Plugins format)
- Advisory skill routing hooks (UserPromptSubmit + PreToolUse), with Claude Code and Cursor output shapes
- **Foundry redirect** skill and `agentworks-foundry-bridge.sh` hook: agents and knowledge bases defined in a
  Falcon Foundry app are pointed to `crowdstrike-falcon-foundry`; API-managed ones stay here
- Scripts re-exec through the managed venv when launched with an interpreter that lacks FalconPy
- Shared display helpers in `common/scripts/formatting.py`
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and a Cursor plugin manifest and hooks file

### Documentation
- README with install instructions, architecture diagram
- Inline skill docs (SKILL.md per skill)
- Implementation guide for replicating KB skill pattern

### FalconPy Support
- Native typed classes for every API surface: `Agents`, `AgentVersions` (agents); `AgentInvocation`,
  `Stream` (invocation); `KnowledgeBases`, `KnowledgeBaseFiles`, `KnowledgeBaseAuditEvents`
  (knowledge-bases); `Models`, `Tools`, `AgentTemplates`, `Spans` (discovery). No uber-class.
- All clients share one OAuth2 auth object (one token request per session)

### Excluded from v1.0 (Per Design)
- DELETE operations for any resource
- Agent enable/disable actions (publish-only)
- Soft-delete for KBs

[1.0.0]: https://github.com/CrowdStrike/agentworks-skills/releases/tag/v1.0.0
