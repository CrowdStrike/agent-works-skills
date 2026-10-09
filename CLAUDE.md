# CLAUDE.md

Project-level instructions for Claude Code when working in the `agentworks-skills` plugin. For the tool-agnostic guide (repo structure, skills ecosystem, usage without the plugin system), see [AGENTS.md](./AGENTS.md).

## Plugin Hook Behavior

This plugin includes two hooks that run automatically:

- **SessionStart**: `bootstrap.sh` builds or refreshes the managed Python venv. It is a no-op when `requirements.txt` and the venv's Python are unchanged, and it never blocks the session.
- **UserPromptSubmit + PreToolUse (`Bash|Skill`)**: `agentworks-router.sh` classifies only the user's prompt. On a match it writes a session-scoped marker and injects advisory context pointing at the `agentworks` orchestrator skill. On the next `Bash` call it nudges once for that prompt; loading any skill clears the marker.

- **PreToolUse (Skill)**: `agentworks-foundry-bridge.sh` gives advisory cross-plugin routing between this plugin (API-managed agents and knowledge bases) and `crowdstrike-falcon-foundry` (agents defined in a Foundry app's `manifest.yml`). It stays silent unless the prompt was about one of the two.

Both hooks are **advisory only** — they always exit 0 and never block a user action or a tool call. They need `jq` and stay silent without it.

## Counter-Rationalizations

Each thought on the left has led to a wrong result; the right column says what to do instead:

| Thought | Reality |
|---------|---------|
| "I'll invoke the draft with `invoke_agent.py`" | `invoke_agent.py` only runs the published version. Use `invoke_version.py --version-id` for drafts |
| "I know the agent ID" | Query first (`agent_search.py`); never guess IDs |
| "I'll suggest prompt changes from the description" | Analyze real traces first (`analyze_agent.py`, `inspect_invocation.py`) |
| "I'll delete or disable the agent" | Delete and enable/disable are out of scope for v1 |
| "I'll call the API directly" | Use the scripts; they handle auth, pagination, and HTTP errors |

## Skills Integration

- **Orchestration**: The `agentworks` skill is the entry point. It routes to `agents`, `invocation`, `knowledge-bases`, `discovery`, and `setup`.
- **Direct invocation**: Each sub-skill can be used directly for a focused task.
- **Shared auth**: All Python scripts import credentials and FalconPy clients from `common/scripts/auth.py` (`get_agents_client()`, `get_agent_invocation_client()`, `get_kb_client()`, …), which share one OAuth2 token.
- **Shared helpers**: `common/scripts/formatting.py` (durations, timestamps), `discovery_helpers.py` (span queries, hydration), `invocation_helpers.py` (invocation status constants), and `_bootstrap.py` (re-exec through the managed venv).
- **Superpowers**: If installed, superpowers planning/TDD skills MAY supplement the workflow but should not replace the orchestrator's routing.
