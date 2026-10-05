# shellcheck shell=bash
# host-output.sh - JSON shape the current host actually injects.
#
# Sourced by the hook scripts. Cursor sets CURSOR_PLUGIN_ROOT and injects top-level
# additional_context; it does not inject Claude's nested hookSpecificOutput.additionalContext.
# Claude Code also reads additional_context, so emitting both would duplicate the advisory
# there. Codex and Copilot keep the Claude shape.

cursor_hooks() {
  [ -n "${CURSOR_PLUGIN_ROOT:-}" ]
}

# emit_advisory <hook event name> <text>
emit_advisory() {
  local event="$1"
  local text="$2"
  if cursor_hooks; then
    jq -n --arg text "$text" '{additional_context: $text}'
  else
    jq -n --arg event "$event" --arg text "$text" '{
      hookSpecificOutput: {
        hookEventName: $event,
        additionalContext: $text
      }
    }'
  fi
}
