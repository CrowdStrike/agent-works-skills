"""
Waterfall renderer for Charlotte AI AgentWorks trace spans.

Renders a monospace tree visualization of spans with duration, credits, and timeline bars.
"""

from datetime import datetime
from typing import Any

from formatting import humanize_duration


# Display constants
BAR_WIDTH = 20
NAME_WIDTH = 32
TYPE_WIDTH = 18


class Node:
    """Tree node for span hierarchy."""
    def __init__(self, span: dict[str, Any]):
        self.span = span
        self.children: list[Node] = []


def parse_ms(iso_time: str | None) -> float:
    """Parse RFC3339 timestamp to milliseconds since epoch."""
    if not iso_time:
        return float('nan')
    try:
        # Handle trailing Z
        if iso_time.endswith('Z'):
            iso_time = iso_time[:-1] + '+00:00'
        dt = datetime.fromisoformat(iso_time)
        return dt.timestamp() * 1000
    except (ValueError, AttributeError):
        return float('nan')


def _humanize_duration(duration_ms: float | int | None) -> str:
    """Human-readable duration; a missing or negative value renders as 0ms in the waterfall."""
    return humanize_duration(max(float(duration_ms or 0), 0.0))


def _credits(span: dict[str, Any]) -> str:
    """Extract credit cost from span attributes."""
    attrs = span.get("attributes", {})
    cents = attrs.get("cost.raw_credit_cents")
    if isinstance(cents, (int, float)):
        return f"{cents / 100:.2f}"
    return "—"


def _truncate(s: str, width: int) -> str:
    """Truncate string to width, adding ellipsis if needed."""
    if len(s) > width:
        return s[:width - 1] + "…"
    return s


def _pad_right(s: str, width: int) -> str:
    """Pad string to width with trailing spaces."""
    if len(s) >= width:
        return s
    return s + " " * (width - len(s))


def _pad_left(s: str, width: int) -> str:
    """Pad string to width with leading spaces."""
    if len(s) >= width:
        return s
    return " " * (width - len(s)) + s


def _timeline_bar(start_ms: float, dur_ms: float, trace_start: float, trace_total: float) -> str:
    """Render a scaled timeline bar for this span within the trace window.

    Format: │░░░████░░░│  (20 chars wide)
    """
    denom = trace_total if trace_total > 0 else 1
    offset = max(0, start_ms - trace_start) if start_ms == start_ms else 0  # NaN check
    dur = float(dur_ms) if dur_ms and dur_ms > 0 else 0

    lead = round((offset / denom) * BAR_WIDTH)
    fill = max(1, round((dur / denom) * BAR_WIDTH))

    # Ensure fit within BAR_WIDTH
    if lead + fill > BAR_WIDTH:
        lead = max(0, BAR_WIDTH - fill)
    if fill > BAR_WIDTH:
        fill = BAR_WIDTH

    trail = max(0, BAR_WIDTH - lead - fill)

    return f"│{'░' * lead}{'█' * fill}{'░' * trail}│"


def _start_key(span: dict[str, Any]) -> float:
    """Sort key: span start in ms, with spans that have no valid start sorted last."""
    start = parse_ms(span.get("start_time"))
    return start if start == start else float("inf")  # NaN check


def _build_forest(spans: list[dict[str, Any]]) -> list[Node]:
    """Build parent-child tree from flat span list.

    Every span gets its own node (a duplicated span_id must not attach one node twice), and
    spans caught in a parent cycle are promoted to roots instead of being dropped.
    """
    nodes = [Node(span) for span in spans]
    by_id: dict[str, Node] = {}
    for node in nodes:
        span_id = node.span.get("span_id")
        if span_id and span_id not in by_id:
            by_id[span_id] = node

    roots: list[Node] = []
    parent_of: dict[int, Node] = {}
    for node in nodes:
        parent_id = node.span.get("parent_span_id")
        parent = by_id.get(parent_id) if parent_id else None
        if parent is not None and parent is not node:
            parent.children.append(node)
            parent_of[id(node)] = parent
        else:
            roots.append(node)

    # Anything not reachable from a root sits in a parent cycle: detach it from its parent and
    # promote it to a root so it is still rendered.
    reachable: set[int] = set()

    def mark(start: Node) -> None:
        # Iterative: a long parent chain would exceed Python's recursion limit.
        stack = [start]
        while stack:
            node = stack.pop()
            if id(node) in reachable:
                continue
            reachable.add(id(node))
            stack.extend(node.children)

    for root in roots:
        mark(root)
    for node in sorted(nodes, key=lambda n: _start_key(n.span)):
        if id(node) not in reachable:
            parent = parent_of.pop(id(node), None)
            if parent is not None and node in parent.children:
                parent.children.remove(node)
            roots.append(node)
            mark(node)

    # Iterative: a long parent chain would exceed Python's recursion limit.
    roots.sort(key=lambda n: _start_key(n.span))
    pending = list(roots)
    while pending:
        node = pending.pop()
        node.children.sort(key=lambda n: _start_key(n.span))
        pending.extend(node.children)
    return roots


def _render_trace(trace_id: str, spans: list[dict[str, Any]]) -> str:
    """Render a single trace as a waterfall tree."""
    # Calculate trace time window
    starts = [parse_ms(s.get("start_time")) for s in spans]
    ends = [parse_ms(s.get("end_time")) for s in spans]
    starts_valid = [s for s in starts if s == s]  # Filter NaN
    ends_valid = [e for e in ends if e == e]

    trace_start = min(starts_valid) if starts_valid else 0
    trace_end = max(ends_valid) if ends_valid else trace_start
    total = trace_end - trace_start

    lines: list[str] = []

    # Header
    header = f"{_pad_right('NAME', NAME_WIDTH)}  {_pad_right('TYPE', TYPE_WIDTH)}  {_pad_left('CREDITS', 7)}  {_pad_left('DURATION', 8)}  TIMELINE"
    lines.append(f"Trace {str(trace_id or 'unknown')[:8]}   {len(spans)} spans   total {_humanize_duration(total)}")
    lines.append(header)

    # Render tree (iterative: a long parent chain would exceed Python's recursion limit)
    def render_node(node: Node, prefix: str, is_last: bool, is_root: bool) -> None:
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        label = _truncate(f"{prefix}{connector}{node.span.get('name') or '(unnamed)'}", NAME_WIDTH)

        span_type = _truncate(node.span.get("span_type") or "", TYPE_WIDTH)
        credits_str = _credits(node.span)
        duration_str = _humanize_duration(node.span.get("duration_ms"))
        bar = _timeline_bar(
            parse_ms(node.span.get("start_time")),
            node.span.get("duration_ms") or 0,
            trace_start,
            total
        )
        error_mark = "  ⚠ error" if node.span.get("status") == "error" else ""

        lines.append(f"{_pad_right(label, NAME_WIDTH)}  "
                     f"{_pad_right(span_type, TYPE_WIDTH)}  "
                     f"{_pad_left(credits_str, 7)}  "
                     f"{_pad_left(duration_str, 8)}  "
                     f"{bar}{error_mark}")

    def walk(root: Node, is_last_root: bool) -> None:
        # Explicit stack of (node, prefix, is_last, is_root); children are pushed in reverse so
        # they pop in order.
        stack = [(root, "", is_last_root, True)]
        while stack:
            node, prefix, is_last, is_root = stack.pop()
            render_node(node, prefix, is_last, is_root)
            child_prefix = "" if is_root else (prefix + ("   " if is_last else "│  "))
            count = len(node.children)
            for i in range(count - 1, -1, -1):
                stack.append((node.children[i], child_prefix, i == count - 1, False))

    roots = _build_forest(spans)
    for i, root in enumerate(roots):
        walk(root, i == len(roots) - 1)

    return "\n".join(lines)


def render_waterfall(spans: list[dict[str, Any]]) -> str:
    """Render spans as a waterfall tree, grouped by trace_id.

    Args:
        spans: List of span dictionaries from /entities/spans/v1

    Returns:
        Monospace waterfall visualization ready to print
    """
    if not spans:
        return ""

    # Group by trace_id
    by_trace: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        trace_id = span.get("trace_id") or "unknown"
        if trace_id not in by_trace:
            by_trace[trace_id] = []
        by_trace[trace_id].append(span)

    # Render each trace
    traces = [_render_trace(tid, group) for tid, group in by_trace.items()]
    return "\n\n".join(traces)
