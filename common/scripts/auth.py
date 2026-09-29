"""
Shared CrowdStrike authentication for Charlotte AI AgentWorks using the FalconPy SDK.

This module exposes FalconPy service clients for the Charlotte AI AgentWorks external API surface:

    get_kb_client()               -> KnowledgeBases (native typed class)
    get_kb_files_client()         -> KnowledgeBaseFiles (native typed class)
    get_kb_audit_client()         -> KnowledgeBaseAuditEvents (native typed class)
    get_agent_invocation_client() -> AgentInvocation (native typed class)
    get_stream_client()           -> Stream (native typed class)
    get_models_client()           -> Models (native typed class)
    get_tools_client()            -> Tools (native typed class)
    get_agent_templates_client()  -> AgentTemplates (native typed class)
    get_agent_versions_client()   -> AgentVersions (native typed class)
    get_spans_client()            -> Spans (native typed class)
    get_agents_client()           -> Agents (native typed class)

All clients share one OAuth2 auth object, so a session makes a single token request.

Credentials are never hardcoded. Run directly to verify them:

    python auth.py

Credential resolution order (first source that supplies both an ID and a
secret wins)
-----------------------------------------------------------------------------
1. Environment variables: FALCON_CLIENT_ID, FALCON_CLIENT_SECRET, and the
   optional FALCON_BASE_URL. Use these for CI and one-off overrides. If
   FALCON_BASE_URL is unset, DEFAULT_BASE_URL is used.
2. TOML profile file at ~/.cache/crowdstrike-agent-works/credentials.toml.
   The profile used is the one named by the FALCON_PROFILE environment
   variable, or the file's top-level `default` key when FALCON_PROFILE is
   unset. Example:

       default = "us-1"

       [us-1]
       client_id = "abc123..."
       client_secret = "xyz789..."
       base_url = "https://api.crowdstrike.com"

   Parsed with the standard-library `tomllib`. A missing or unparsable file is
   skipped silently.

Run `/crowdstrike-agent-works:setup` to configure credentials interactively.

Import contract for sibling scripts
-----------------------------------
Each skill's scripts/ directory is three levels below the repo root
(e.g. skills/agents/scripts/), so the shared module lives at
../../../common/scripts relative to the importing script. Add that directory to
sys.path anchored to the importing file's own location, then import normally:

    import sys, os
    sys.path.insert(
        0,
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..", "..", "..", "common", "scripts",
        ),
    )
    from auth import get_kb_client        # for KB scripts
    from auth import get_spans_client     # for discovery/invocation scripts (native FalconPy classes)
    from auth import get_agents_client    # for agent CRUD (agents skill)

Anchoring to __file__ (not the current working directory) makes the import
work no matter where the script is launched from. No package install or
symlink is required.

Note: the FalconPy version is intentionally left unpinned in requirements so
installs automatically receive the latest SDK updates. This module imports the
classes lazily inside the client factories so a missing dependency surfaces
only when a client is actually requested, not at import time.
"""

import os
import re
import sys
import tomllib
from typing import Any

# Fix Windows console encoding so the Unicode box characters below render.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_URL = "https://api.crowdstrike.com"

# Minimum supported FalconPy version. The Agents service class (agent CRUD) and
# AgentInvocation.update_agent_invocation (cancel) were added in 1.6.6. The dependency
# itself stays unpinned per CrowdStrike guidance -- this is a runtime floor, not a
# requirements pin, so an older install fails with a clear RuntimeError instead of an
# AttributeError the first time one of those classes is requested.
MIN_FALCONPY = (1, 6, 6)

# TOML credentials file path.
TOML_CREDENTIALS_PATH_AGENT_WORKS = os.path.expanduser(
    "~/.cache/crowdstrike-agent-works/credentials.toml"
)


# ── TOML profile loader ───────────────────────────────────────────────────────


def _load_toml(path: str) -> dict[str, Any] | None:
    """
    Parse a TOML file into a dict with the stdlib `tomllib`.

    Returns None if the file is missing or cannot be parsed -- never raises.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        # ValueError covers tomllib.TOMLDecodeError (a subclass).
        return None


def _creds_from_toml(path: str) -> tuple[str, str, str] | None:
    """
    Return (client_id, client_secret, base_url) from the TOML profile file,
    or None if unavailable/incomplete.

    The profile is chosen by FALCON_PROFILE, falling back to the file's
    top-level `default` key.
    """
    data = _load_toml(path)
    if not isinstance(data, dict):
        return None

    profile = os.environ.get("FALCON_PROFILE") or data.get("default")
    if isinstance(profile, dict):
        # A `[default]` table rather than `default = "<profile>"`: treat it as the profile itself.
        section = profile
    elif isinstance(profile, str) and profile:
        section = data.get(profile)
    else:
        return None
    if not isinstance(section, dict):
        return None

    client_id = section.get("client_id", "")
    client_secret = section.get("client_secret", "")
    if not client_id or not client_secret:
        return None

    base_url = section.get("base_url", DEFAULT_BASE_URL)
    return client_id, client_secret, base_url


# ── Credentials ─────────────────────────────────────────────────────────────


def get_credentials() -> tuple[str, str, str]:
    """
    Return (client_id, client_secret, base_url) using the documented
    resolution order: environment variables, then the agent-works TOML file.
    The first source supplying both an ID and a secret wins.

    Exits with a clear error if no source provides credentials.
    """
    # 1. Environment variables (for CI and overrides). These outrank the TOML
    #    file so a run can be redirected without editing the profile.
    client_id = os.environ.get("FALCON_CLIENT_ID", "")
    client_secret = os.environ.get("FALCON_CLIENT_SECRET", "")
    if client_id and client_secret:
        base_url = os.environ.get("FALCON_BASE_URL", "") or DEFAULT_BASE_URL
        return client_id, client_secret, base_url.rstrip("/")

    # 2. Agent-works TOML profile file.
    toml_creds = _creds_from_toml(TOML_CREDENTIALS_PATH_AGENT_WORKS)
    if toml_creds:
        client_id, client_secret, base_url = toml_creds
        return client_id, client_secret, base_url.rstrip("/")

    print(
        "ERROR: FALCON_CLIENT_ID and FALCON_CLIENT_SECRET must be set via "
        "environment variables or the TOML credentials file "
        "(~/.cache/crowdstrike-agent-works/credentials.toml). "
        "Run /crowdstrike-agent-works:setup to configure credentials.",
        file=sys.stderr,
    )
    sys.exit(1)


# ── FalconPy version guard ────────────────────────────────────────────────────


def _falconpy_version(falconpy: Any) -> tuple[int, int, int]:
    """Return the installed FalconPy version as a (major, minor, patch) tuple.

    Reads `falconpy.version()` (a string like "1.6.3"), falling back to the
    `__version__` attribute. Parses defensively: only the leading numeric
    dotted components are used, and anything unparseable yields (0, 0, 0) so the
    guard fails closed (treats an unknown version as too old).
    """
    raw = ""
    version_fn = getattr(falconpy, "version", None)
    if callable(version_fn):
        try:
            raw = version_fn() or ""
        except Exception:  # pylint: disable=broad-exception-caught
            raw = ""
    if not raw:
        raw = getattr(falconpy, "__version__", "") or ""

    match = re.match(r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(raw))
    if not match:
        return (0, 0, 0)
    return tuple(int(part) if part else 0 for part in match.groups())


def _check_falconpy_version(falconpy: Any) -> None:
    """Raise RuntimeError if the installed FalconPy is older than MIN_FALCONPY."""
    found = _falconpy_version(falconpy)
    if found < MIN_FALCONPY:
        floor = ".".join(str(n) for n in MIN_FALCONPY)
        found_str = ".".join(str(n) for n in found)
        raise RuntimeError(
            f"FalconPy >= {floor} required (found {found_str}). "
            "Upgrade with `pip install -U crowdstrike-falconpy`, or run this "
            "script via the project virtualenv: .venv/bin/python"
        )


# ── FalconPy clients ─────────────────────────────────────────────────────────
#
# Every service client is built lazily, cached by class name, and shares a single
# OAuth2 auth object so requesting several clients costs one token request. Requesting
# one client never forces construction of the others.

_auth_object = None  # pylint: disable=invalid-name
_clients: dict[str, Any] = {}


def _get_auth_object() -> Any:
    """Return the shared FalconPy OAuth2 object, creating it on first use."""
    global _auth_object  # pylint: disable=global-statement
    if _auth_object is None:
        import falconpy  # pylint: disable=import-outside-toplevel

        _check_falconpy_version(falconpy)
        client_id, client_secret, base_url = get_credentials()
        _auth_object = falconpy.OAuth2(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
        )
    return _auth_object


def _get_client(class_name: str) -> Any:
    """Return the shared FalconPy service class `class_name`, creating it on first use."""
    if class_name not in _clients:
        import falconpy  # pylint: disable=import-outside-toplevel

        _clients[class_name] = getattr(falconpy, class_name)(auth_object=_get_auth_object())
    return _clients[class_name]


def get_raw(path: str, parameters: dict[str, str]) -> bytes:
    """GET `path` with the shared OAuth2 token and return the response bytes untouched.

    FalconPy service classes parse text/plain and application/json responses (json.loads), which
    breaks endpoints that stream file content. Use this for file downloads.

    Raises:
        RuntimeError on an HTTP error status.
    """
    import requests  # pylint: disable=import-outside-toplevel

    auth = _get_auth_object()
    response = requests.get(
        f"{auth.base_url}{path}",
        params=parameters,
        headers=auth.auth_headers,
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    return response.content


def get_kb_client() -> Any:
    """Return the shared FalconPy KnowledgeBases client (/agentic-studio/.../knowledge_bases...)."""
    return _get_client("KnowledgeBases")


def get_kb_files_client() -> Any:
    """Return the shared FalconPy KnowledgeBaseFiles client."""
    return _get_client("KnowledgeBaseFiles")


def get_kb_audit_client() -> Any:
    """Return the shared FalconPy KnowledgeBaseAuditEvents client."""
    return _get_client("KnowledgeBaseAuditEvents")


def get_agents_client() -> Any:
    """
    Return the shared FalconPy Agents client.

    Covers query_studio_agents, get_studio_agents, create_or_update_agent (create/update)
    and update_agent (publish).
    """
    return _get_client("Agents")


def get_agent_invocation_client() -> Any:
    """
    Return the shared FalconPy AgentInvocation client.

    Covers invoke_published_agent_external_v1, invoke_agent_version_external_v1,
    get_agent_invocation_v3 and update_agent_invocation (cancel).
    """
    return _get_client("AgentInvocation")


def get_stream_client() -> Any:
    """
    Return the shared FalconPy Stream client (stream_invocation_response_v1).

    Note: this uses the same non-streaming request mechanism as every other FalconPy
    call, so it does not provide true SSE token-by-token streaming, only typed access
    to the same endpoint.
    """
    return _get_client("Stream")


def get_models_client() -> Any:
    """Return the shared FalconPy Models client."""
    return _get_client("Models")


def get_tools_client() -> Any:
    """Return the shared FalconPy Tools client."""
    return _get_client("Tools")


def get_agent_templates_client() -> Any:
    """Return the shared FalconPy AgentTemplates client."""
    return _get_client("AgentTemplates")


def get_agent_versions_client() -> Any:
    """Return the shared FalconPy AgentVersions client."""
    return _get_client("AgentVersions")


def get_spans_client() -> Any:
    """Return the shared FalconPy Spans client."""
    return _get_client("Spans")


def reset_clients() -> None:
    """Reset all shared clients and the shared auth object (useful for testing)."""
    global _auth_object  # pylint: disable=global-statement
    _auth_object = None
    _clients.clear()


# ── Helper for service-class calls ───────────────────────────────────────────


def call_native(method: Any, **kwargs: Any) -> dict[str, Any] | Any:
    """
    Helper for calling a FalconPy service class method (e.g.
    get_spans_client().queries_spans_v1). Returns the parsed response body and raises on
    HTTP errors, so callers can use response.get("resources", ...) directly.

    Args:
        method: A bound method on one of the get_*_client() singletons, e.g.
            get_models_client().queries_models_v1
        **kwargs: Forwarded to the method as-is (e.g. parameters=..., body=..., ids=...)

    Returns:
        The response dict (parsed body if available, else the raw response object).

    Raises:
        RuntimeError on HTTP error or auth failure.
    """
    response = method(**kwargs)

    # FalconPy service class methods return a {'status_code', 'body', ...} dict.
    if isinstance(response, dict):
        raw_body = response.get("body")
        response_body = raw_body if isinstance(raw_body, dict) else {}
        status = response.get("status_code") or 0
        if status >= 400:
            errors = response_body.get("errors", [])
            # Fall back to the raw body so a non-dict error (e.g. a gateway's plain-text 502) isn't lost.
            error_msg = "; ".join(str(e) for e in errors) if errors else (response_body or raw_body)
            raise RuntimeError(f"HTTP {status}: {error_msg}")
        # A 204 No Content carries body=None (the key exists), so .get("body", response) would
        # return None and break callers that chain .get(...) on the result.
        body = response.get("body")
        return body if body is not None else response

    # If response is not a dict, return as-is (edge case, shouldn't happen normally)
    return response


def is_transient_error(exc: Exception) -> bool:
    """
    True if a call_native() failure is worth retrying: HTTP 429/5xx, or a network-level error
    (connection reset, timeout, DNS). Everything else is permanent: other HTTP 4xx (bad ID,
    missing scope), RuntimeErrors without an HTTP status (auth failure), and programming or
    parsing errors such as KeyError and TypeError.
    """
    if isinstance(exc, RuntimeError):
        match = re.match(r"HTTP (\d{3})", str(exc))
        if not match:
            return False
        status = int(match.group(1))
        return status == 429 or status >= 500
    try:
        import requests  # pylint: disable=import-outside-toplevel

        if isinstance(exc, requests.RequestException):
            return True
    except ImportError:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


# ── Self-test ───────────────────────────────────────────────────────────────

def _fail_reason_suffix(client) -> str:
    """Format the real API error FalconPy captured on a failed login, if any.

    A straightforward bad-credentials failure doesn't raise -- FalconPy's
    _login_handler catches it, calls bearer_token.fail_token(status, message),
    and token_expired() just returns True. Without this, the self-test only
    ever printed a generic "could not obtain token", discarding the actual
    reason (e.g. invalid client_id/secret, missing scope) that FalconPy
    already captured. (A connection-level failure like a bad TLS cert is NOT
    affected by this -- that raises and is already shown by the outer broad
    `except Exception` below.)

    Service classes wrap an auth_object and expose it as client.auth_object, which
    carries token_fail_reason.
    """
    auth_obj = getattr(client, "auth_object", client)
    reason = getattr(auth_obj, "token_fail_reason", None)
    return f": {reason}" if reason else ""


if __name__ == "__main__":
    print("CrowdStrike Auth — Charlotte AI AgentWorks self-test (FalconPy)")
    print("─" * 60)
    cid, csec, burl = get_credentials()
    print(f"  Base URL  : {burl}")
    print(f"  Client ID : {cid[:8]}...{cid[-4:]}")
    print(f"  Secret    : {'*' * 12} ({len(csec)} chars)")
    print()
    try:
        # All clients share one OAuth2 object, so checking each class verifies its import
        # and construction, and the first call verifies the shared token.
        for label, factory in (
            ("KnowledgeBases", get_kb_client),
            ("KnowledgeBaseFiles", get_kb_files_client),
            ("KnowledgeBaseAuditEvents", get_kb_audit_client),
            ("Agents", get_agents_client),
            ("AgentInvocation", get_agent_invocation_client),
        ):
            client = factory()
            if client.token_expired():
                print(
                    f"  Authentication FAILED: could not obtain token ({label})"
                    f"{_fail_reason_suffix(client)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"  ✓ Authentication successful ({label} client)")

        print()
        print("All clients authenticated successfully. Ready to use Charlotte AI AgentWorks APIs.")

    # Self-test reports any auth failure cause to the user, so a broad catch is
    # intentional here — narrowing would drop useful diagnostics.
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"\n  Authentication FAILED: {e}", file=sys.stderr)
        sys.exit(1)
