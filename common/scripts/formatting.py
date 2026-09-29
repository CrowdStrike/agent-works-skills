"""
Shared display-formatting helpers for Charlotte AI AgentWorks scripts.

Durations, timestamps and "modified by" labels are rendered the same way by every
list/inspect/analyze script, so they live here instead of being copied per script.
"""

from datetime import datetime
from typing import Any

# Default timestamp layout for table output, e.g. "Oct. 05, 2026 14:03:09".
TABLE_TIMESTAMP_FORMAT = "%b. %d, %Y %H:%M:%S"


def humanize_duration(ms: float | None) -> str:
    """Convert milliseconds to a human-readable duration (ms, s, or m/s).

    Returns "—" for a missing, NaN, or negative value.
    """
    if ms is None or ms != ms or ms < 0:  # ms != ms is the NaN check
        return "—"
    if ms >= 60000:
        minutes = int(ms // 60000)
        seconds = int((ms % 60000) // 1000)
        return f"{minutes}m{seconds:02d}s"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{int(ms)}ms"


def format_timestamp(
    ts: str | None,
    fmt: str = TABLE_TIMESTAMP_FORMAT,
    empty: str = "(unknown)",
) -> str:
    """Format an ISO8601 timestamp for display.

    Args:
        ts: ISO8601 timestamp (a trailing "Z" is accepted).
        fmt: strftime layout for the output.
        empty: Text returned when ts is missing.

    Returns:
        The formatted timestamp, `empty` if ts is falsy, or ts unchanged if it can't be parsed.
    """
    if not ts:
        return empty
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime(fmt)
    except (ValueError, AttributeError):
        return ts


def format_modified_by(updated_by: dict[str, Any] | None) -> str:
    """Render an `updated_by` / `created_by` actor as a display name."""
    if not updated_by:
        return "(unknown)"
    name = updated_by.get("name")
    if name:
        return name
    api_client_id = updated_by.get("api_client_id")
    if api_client_id:
        return f"{api_client_id} (API client)"
    return updated_by.get("uuid") or updated_by.get("cid") or "(unknown)"
