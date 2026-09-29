"""
Shared helpers for Charlotte AI AgentWorks invocation scripts.

This module provides constants shared by the scripts that poll an invocation's status.
"""

# Invocation statuses that mean the run is done. Anything else (processing, queued, cancelling,
# an unrecognized value, ...) is treated as still in flight, so pollers keep waiting on it.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
