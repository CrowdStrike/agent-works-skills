"""Cold-start dependency bootstrap for the agent-works entry-point scripts.

The scripts depend on `crowdstrike-falconpy`, which lives in a managed virtualenv built by
the plugin's SessionStart hook and used by ``scripts/python.sh``. A script may still be
launched with a bare ``python script.py`` -- for example from a cloned repo, where the
plugin hook never fired -- using an interpreter that has no falconpy, which fails with a
``ModuleNotFoundError`` at the first API call.

``ensure_deps()`` makes the scripts resilient to how they are launched: if falconpy is
missing from the current interpreter, it re-executes the script through
``scripts/python.sh``, which runs (and, on demand, builds) the managed venv. If falconpy
is already importable -- the normal case, including when already running inside the venv --
it does nothing.

A guard environment variable prevents an infinite re-exec loop: if the managed venv itself
lacks falconpy, the second run lets the import fail with its natural, clear error.
"""

import os
import sys
from importlib.util import find_spec

# Set in the child environment before re-exec so a venv that is somehow still missing
# falconpy fails naturally instead of looping.
_GUARD_ENV = "AGENT_WORKS_BOOTSTRAPPED"

# Marker dependency: the package a bare interpreter is most likely to lack.
_MARKER_PACKAGE = "falconpy"


def _python_sh_path() -> str:
    """Absolute path to scripts/python.sh, resolved relative to this file.

    This module lives at ``<repo>/common/scripts/_bootstrap.py``; the wrapper is at
    ``<repo>/scripts/python.sh``.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(here, "..", "..", "scripts", "python.sh")


def ensure_deps(script_path: str) -> None:
    """Re-exec through the managed venv if the marker dependency is missing.

    Call this at the top of an entry-point script, after the ``sys.path`` insert that makes
    ``common/scripts`` importable and before importing ``auth``::

        import _bootstrap
        _bootstrap.ensure_deps(__file__)
        from auth import get_kb_client

    Args:
        script_path: The calling script's ``__file__``, re-run verbatim in the managed venv
            (with its original command-line arguments).

    Returns:
        None. Either the current interpreter already has the dependency (returns normally)
        or the process is replaced via ``os.execv`` and does not return.
    """
    if find_spec(_MARKER_PACKAGE) is not None:
        return  # Dependency present -- nothing to do.

    if os.environ.get(_GUARD_ENV):
        # Already re-exec'd once and falconpy is still missing. Let the import fail
        # naturally with a clear error rather than looping.
        return

    wrapper = _python_sh_path()
    if not os.path.exists(wrapper):
        # No wrapper to hand off to; let the natural import error surface.
        return

    os.environ[_GUARD_ENV] = "1"
    # Re-run this exact script with its original args through the venv wrapper.
    os.execv(wrapper, [wrapper, os.path.realpath(script_path), *sys.argv[1:]])
