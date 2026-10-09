#!/usr/bin/env bash
set -euo pipefail

# python.sh
# Runs an agentworks Python script using the managed venv so the correct Python
# and dependencies (crowdstrike-falconpy) are ALWAYS used — never a stale
# or dependency-free system Python.
#
# Usage: python.sh <script.py> [args...]

CACHE_DIR="${HOME}/.cache/crowdstrike-charlotte-ai-agentworks"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./python-detect.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/python-detect.sh"
_pd_set_venv_bins "${CACHE_DIR}/venv"

# Always run the setup script: it is a no-op when requirements.txt and the venv's Python are
# unchanged, and it repairs a half-built venv (e.g. an interrupted first pip install) or
# installs requirements changed by a plugin update. Skipping it whenever bin/python3 exists
# would leave such a venv broken until deleted by hand.
if ! "${SCRIPT_DIR}/setup-python-venv.sh" >&2; then
    echo "ERROR: failed to set up the agentworks Python venv." >&2
    exit 1
fi
_pd_set_venv_bins "${CACHE_DIR}/venv"
if [[ ! -x "$VENV_PYTHON_BIN" ]]; then
    echo "ERROR: venv setup reported success but ${VENV_PYTHON_BIN} is missing." >&2
    exit 1
fi

if [[ -z "${1:-}" ]]; then
    echo "ERROR: no script specified. Usage: python.sh <script.py> [args...]" >&2
    exit 1
fi

# Windows default codepage (cp1252) can't encode all API-response characters.
if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    export PYTHONIOENCODING=utf-8
fi

exec "$VENV_PYTHON_BIN" "$@"
