#!/usr/bin/env bash
# bootstrap.sh - SessionStart hook: builds the agent-works managed venv.
# Runs idempotently at session start (or on first script use). Advisory-only;
# always exits 0 so setup issues never block the session.

set +e  # Allow non-zero exit (advisory hook)

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$HOOK_DIR")"

# Always run the setup script: its requirements-hash and Python-version checks make it a
# no-op when the venv is healthy, and it repairs half-built venvs or picks up requirements
# changes from plugin updates.
if ! "${PLUGIN_ROOT}/scripts/setup-python-venv.sh" >&2; then
    # Setup failed — don't block the session. Scripts will retry lazily.
    echo "WARNING: Charlotte AI AgentWorks Python environment setup failed; setup is incomplete and skill commands may fail." >&2
    exit 0
fi

exit 0
