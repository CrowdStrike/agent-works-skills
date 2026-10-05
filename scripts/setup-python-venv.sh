#!/usr/bin/env bash
set -euo pipefail

# setup-python-venv.sh
# Creates/updates the agent-works managed venv at ~/.cache/crowdstrike-agent-works/venv.
# uv-first (fast, can provision Python 3.14+) with a `python -m venv` fallback.
# Idempotent: skips reinstall when requirements.txt is unchanged; rebuilds if the
# venv's Python drifts out of the supported range.

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

# shellcheck source=./python-detect.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/python-detect.sh"

VENV_DIR="${HOME}/.cache/crowdstrike-agent-works/venv"
_pd_set_venv_bins "$VENV_DIR"
REQUIREMENTS_FILE="${PLUGIN_ROOT}/requirements.txt"
REQUIREMENTS_HASH_FILE="${VENV_DIR}/.requirements.sha256"
PYTHON_VERSION_FILE="${VENV_DIR}/.python.version"

_calc_hash() {
    local file="$1"
    if command -v sha256sum &>/dev/null; then
        sha256sum "$file" | awk '{print $1}'
    else
        shasum -a 256 "$file" | awk '{print $1}'
    fi
}

_has_uv() { command -v uv &>/dev/null; }

_print_package_access_guidance() {
    cat >&2 <<'EOF'
If the install failed with an access, certificate, or package registry error,
refer to your organization's documentation for setting up a Python environment.
You may need to configure an approved package registry or install required
certificates outside the AI coding agent. Afterward, restart the coding agent
terminal so it inherits the updated environment. Some workstation changes may
require signing out and back in before restarting the agent.
EOF
}

# Is the existing venv's Python still supported?
_check_venv_python_version() {
    [[ -x "$VENV_PYTHON_BIN" ]] || return 1
    local version
    version=$(_pd_get_python_version "$VENV_PYTHON_BIN" 2>/dev/null) || return 1
    _pd_is_version_supported "$version"
}

# Fast path: is the venv already built from the current requirements with a supported Python?
# Cheap on purpose (one `python --version` and one hash), and runs before any Python discovery.
_venv_is_current() {
    [[ -f "$REQUIREMENTS_HASH_FILE" ]] || return 1
    _check_venv_python_version || return 1
    [[ "$(_calc_hash "$REQUIREMENTS_FILE")" == "$(cat "$REQUIREMENTS_HASH_FILE")" ]]
}

# Serialize setup runs (the SessionStart hook and the first script, or parallel scripts) so one
# cannot delete or rebuild the venv while another is installing into it. mkdir is atomic and
# portable (macOS has no flock); a lock whose owner PID is gone is treated as stale.
LOCK_DIR="${VENV_DIR}.lock"
_acquire_lock() {
    mkdir -p "$(dirname "$LOCK_DIR")"
    local waited=0
    until mkdir "$LOCK_DIR" 2>/dev/null; do
        local owner
        owner=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
        if [[ -n "$owner" ]] && ! kill -0 "$owner" 2>/dev/null; then
            # Stale: owner exited without releasing. Rename (atomic, so only one contender wins)
            # instead of rm -rf, so a contender that already re-created the lock is not deleted
            # out from under its new owner; if we grabbed a live lock, put it back.
            local reaped="$LOCK_DIR.stale.$$"
            if mv "$LOCK_DIR" "$reaped" 2>/dev/null; then
                if [[ "$(cat "$reaped/pid" 2>/dev/null || true)" == "$owner" ]]; then
                    rm -rf "$reaped"
                else
                    mv -n "$reaped" "$LOCK_DIR" 2>/dev/null || rm -rf "$reaped"
                fi
            fi
            continue
        fi
        if (( waited >= 300 )); then
            echo -e "${RED}ERROR: timed out waiting for another venv setup (lock: $LOCK_DIR)${NC}" >&2
            exit 2
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo $$ > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR"' EXIT
}

_create_venv_with_uv() {
    local python_bin="$1" version
    version=$(_pd_get_python_version "$python_bin")
    echo -e "${GREEN}[uv]${NC} Creating venv with Python $version: $VENV_DIR"
    if ! uv venv "$VENV_DIR" --python "$python_bin" --quiet 2>/dev/null; then
        echo -e "${YELLOW}[uv] venv creation failed, falling back to standard venv${NC}" >&2
        return 1
    fi
    echo "$version" > "$PYTHON_VERSION_FILE"
}

_create_venv() {
    local python_bin="$1" version
    version=$(_pd_get_python_version "$python_bin")
    echo "Creating venv with Python $version: $VENV_DIR"
    "$python_bin" -m venv "$VENV_DIR" || {
        echo -e "${RED}ERROR: Failed to create Python venv${NC}" >&2
        local platform
        platform=$(_pd_detect_platform)
        [[ "$platform" == "debian" ]] && echo "Try: sudo apt install python3.14-venv" >&2
        exit 2
    }
    echo "$version" > "$PYTHON_VERSION_FILE"
}

main() {
    _venv_is_current && exit 0

    _acquire_lock
    # Another process may have finished the setup while we waited for the lock.
    _venv_is_current && exit 0

    local python_bin
    python_bin=$(find_compatible_python) || { print_install_instructions; exit 2; }
    local python_version
    python_version=$(_pd_get_python_version "$python_bin")

    if [[ -d "$VENV_DIR" ]]; then
        # Rebuild if the venv's Python drifted out of range.
        if ! _check_venv_python_version; then
            local old_version="unknown"
            [[ -f "$PYTHON_VERSION_FILE" ]] && old_version=$(cat "$PYTHON_VERSION_FILE")
            echo -e "${YELLOW}Rebuilding venv: Python $old_version -> $python_version${NC}"
            rm -rf "$VENV_DIR"
            if _has_uv; then _create_venv_with_uv "$python_bin" || _create_venv "$python_bin"
            else _create_venv "$python_bin"; fi
        fi

        # Fast path: requirements unchanged -> nothing to do.
        if [[ -f "$REQUIREMENTS_HASH_FILE" ]] && _check_venv_python_version; then
            local current_hash cached_hash
            current_hash=$(_calc_hash "$REQUIREMENTS_FILE")
            cached_hash=$(cat "$REQUIREMENTS_HASH_FILE")
            [[ "$current_hash" == "$cached_hash" ]] && exit 0
        fi
    else
        echo -e "${YELLOW}Setting up the agent-works Python environment...${NC}"
        if _has_uv; then _create_venv_with_uv "$python_bin" || _create_venv "$python_bin"
        else _create_venv "$python_bin"; fi
    fi

    echo "Installing dependencies from requirements.txt"
    local install_success=false

    # uv install (fast).
    if _has_uv; then
        echo -e "${GREEN}[uv]${NC} Attempting fast install..."
        if uv pip install --quiet --upgrade -r "$REQUIREMENTS_FILE" --python "$VENV_PYTHON_BIN" 2>/dev/null; then
            install_success=true
        else
            echo -e "${YELLOW}[uv] install failed, falling back to pip${NC}" >&2
        fi
    fi

    # pip fallback (works everywhere).
    if [[ "$install_success" != "true" ]]; then
        echo "Installing with pip..."
        if [[ ! -x "$VENV_PIP_BIN" ]]; then
            "$VENV_PYTHON_BIN" -m ensurepip --quiet 2>/dev/null || {
                echo -e "${YELLOW}ensurepip failed, recreating venv with standard python${NC}" >&2
                rm -rf "$VENV_DIR"; _create_venv "$python_bin"
            }
        fi
        "$VENV_PIP_BIN" install --quiet --upgrade pip || {
            echo -e "${RED}ERROR: Failed to upgrade pip${NC}" >&2
            _print_package_access_guidance
            exit 2
        }
        "$VENV_PIP_BIN" install --quiet --upgrade -r "$REQUIREMENTS_FILE" || {
            echo -e "${RED}ERROR: Failed to install dependencies from $REQUIREMENTS_FILE${NC}" >&2
            _print_package_access_guidance
            exit 2
        }
    fi

    _calc_hash "$REQUIREMENTS_FILE" > "$REQUIREMENTS_HASH_FILE"
    echo -e "${GREEN}[OK] agent-works venv ready: ${VENV_DIR} (Python $python_version)${NC}"
    exit 0
}

main "$@"
