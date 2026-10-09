#!/usr/bin/env bash
#
# agentworks-foundry-bridge.sh
#
# PreToolUse hook on the Skill tool. Provides advisory cross-plugin routing between
# crowdstrike-charlotte-ai-agentworks (agents and knowledge bases managed directly through the API) and
# crowdstrike-falcon-foundry (agents and knowledge bases defined in a Foundry app's
# manifest.yml). Advisory only -- never blocks a skill invocation.
#
# Two directions:
# 1. A Foundry skill is invoked while AgentWorks (API-managed) intent is active
#    -> remind that API-managed agents belong to this plugin.
# 2. An AgentWorks skill is invoked but the work needs Foundry app capabilities
#    (manifest.yml, ai.agents, foundry CLI) -> point at foundry-skills.
#
# Receives JSON on stdin with tool_input.skill (the skill being invoked).
# Outputs JSON with additionalContext. Always exits 0.

set +e  # Advisory hook -- never fail

# Needs jq to read the hook payload and emit JSON; without it, stay silent.
command -v jq >/dev/null 2>&1 || exit 0

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/host-output.sh"

INPUT=$(cat)

SKILL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_input.skill // empty')
# Same session-scoped marker paths as agentworks-router.sh: MARKER means this prompt was about an
# API-managed agent or knowledge base; FOUNDRY_MARKER means it was about one inside a Foundry app.
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // .conversation_id // "nosession"' | tr -cd 'A-Za-z0-9_-')
MARKER="${TMPDIR:-/tmp}/agentworks-router-${SESSION_ID:-nosession}"
FOUNDRY_MARKER="$MARKER.foundry"

# Detect whether the sibling Foundry plugin is installed on the host running this hook.
# Claude Code records installed plugins in JSON; Codex records enabled marketplace plugins in
# TOML; Antigravity in config.json; Cursor in its plugin cache. Cursor sets CURSOR_PLUGIN_ROOT.
# Codex sends turn_id. All checks are best-effort.
codex_foundry_enabled() {
  [ -f "$HOME/.codex/config.toml" ] || return 1
  # Only the plugin's own table counts, not a nested one such as
  # [plugins."<id>@<marketplace>".mcp_servers.x].
  awk -v prefix='[plugins."crowdstrike-falcon-foundry@' '
    /^\[/ { in_plugin = (index($0, prefix) == 1 && substr($0, length(prefix) + 1) ~ /^[^".]*"\][[:space:]]*(#.*)?$/); next }
    in_plugin && /^enabled[[:space:]]*=[[:space:]]*true[[:space:]]*(#.*)?$/ { found = 1 }
    END { exit found ? 0 : 1 }
  ' "$HOME/.codex/config.toml" 2>/dev/null
}

FOUNDRY_INSTALLED=false
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  [ -d "$HOME/.cursor/plugins/cache/cursor-public/crowdstrike-falcon-foundry" ] && FOUNDRY_INSTALLED=true
elif printf '%s' "$INPUT" | jq -e 'has("turn_id")' >/dev/null 2>&1; then
  codex_foundry_enabled && FOUNDRY_INSTALLED=true
elif [ -f "$HOME/.claude/plugins/installed_plugins.json" ] &&
     grep -q "crowdstrike-falcon-foundry" "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null; then
  FOUNDRY_INSTALLED=true
elif codex_foundry_enabled; then
  FOUNDRY_INSTALLED=true
elif [ -d "$HOME/.gemini/config/plugins/crowdstrike-falcon-foundry" ]; then
  FOUNDRY_INSTALLED=true
elif [ -d "$HOME/.cursor/plugins/cache/cursor-public/crowdstrike-falcon-foundry" ]; then
  FOUNDRY_INSTALLED=true
fi

case "$SKILL_NAME" in
  # A Foundry skill is being invoked. If this turn's intent was an API-managed agent
  # (marker present), say which plugin owns that.
  crowdstrike-falcon-foundry:*)
    if [ -f "$MARKER" ]; then
      emit_advisory "PreToolUse" "Cross-plugin note: For an agent or knowledge base managed directly through the Falcon API (no Foundry app, no manifest.yml), use the crowdstrike-charlotte-ai-agentworks skills (agentworks, agents, knowledge-bases) instead. Only route to Foundry if the agent must live in an app's ai.agents manifest block."
      exit 0
    fi
    ;;

  # An AgentWorks skill is being invoked although the prompt was about a Foundry app. Advise the
  # Foundry path; stay silent otherwise so ordinary AgentWorks use gets no cross-plugin noise.
  crowdstrike-charlotte-ai-agentworks:*|agentworks|knowledge-bases)
    [ -f "$FOUNDRY_MARKER" ] || exit 0
    if [ "$FOUNDRY_INSTALLED" = true ]; then
      MSG="Cross-plugin note: If this agent or knowledge base must be defined in a Foundry app (manifest.yml ai.agents / ai.knowledge_bases, foundry CLI), the foundry-skills plugin is installed -- route to crowdstrike-falcon-foundry:ai-agents-development for the app lifecycle. API-managed agents stay here."
    else
      MSG="Cross-plugin note: This plugin manages agents and knowledge bases directly through the Falcon API. If the user needs them inside a Foundry app (manifest.yml ai.agents / ai.knowledge_bases, foundry CLI), install crowdstrike-falcon-foundry from the plugin browser (/plugins in Codex; /plugin install crowdstrike-falcon-foundry in Claude Code; /add-plugin crowdstrike-falcon-foundry in Cursor; agy plugin install https://github.com/CrowdStrike/foundry-skills in Antigravity)."
    fi
    emit_advisory "PreToolUse" "$MSG"
    exit 0
    ;;
esac

exit 0
