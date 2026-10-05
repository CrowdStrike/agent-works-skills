"""
Shared helpers for Charlotte AI AgentWorks discovery scripts.

This module provides common functionality for querying discovery endpoints
(spans, templates, tools, versions) which all share the same interface.
"""

import argparse
import json
import re
import sys
import time
from typing import Any, Callable

from auth import call_native, get_spans_client, is_transient_error


# Attempts per span batch (1 try + retries on transient errors).
HYDRATE_ATTEMPTS = 3


def hydrate_spans(span_ids: list[str], batch_size: int = 50) -> list[dict]:
    """Hydrate span IDs into full entities with automatic batching.

    Uses the native FalconPy Spans.entities_spans_v1 method, which serializes the
    `ids` array-type query parameter correctly on its own (repeated `ids=` params),
    so no manual query-string construction is needed here.

    Transient failures (429/5xx, connection errors) are retried per batch; a permanent
    failure, or a batch that still fails after the retries, raises. Returning a partial
    list would let callers compute error rates, costs and durations from a subset of spans
    and present them as complete.

    Args:
        span_ids: List of span IDs to hydrate
        batch_size: Number of IDs per request (default: 50, tested up to 50)

    Returns:
        List of hydrated span entities

    Raises:
        RuntimeError: a batch could not be hydrated.
    """
    if not span_ids:
        return []

    all_spans = []
    spans_client = get_spans_client()

    for i in range(0, len(span_ids), batch_size):
        batch = span_ids[i:i + batch_size]
        for attempt in range(1, HYDRATE_ATTEMPTS + 1):
            try:
                response = call_native(spans_client.entities_spans_v1, ids=batch)
            except Exception as e:  # pylint: disable=broad-exception-caught
                if attempt == HYDRATE_ATTEMPTS or not is_transient_error(e):
                    raise RuntimeError(
                        f"Failed to hydrate span batch {i // batch_size + 1} "
                        f"({len(batch)} of {len(span_ids)} spans): {e}"
                    ) from e
                print(f"Warning: span batch {i // batch_size + 1} failed ({e}); "
                      f"retry {attempt}/{HYDRATE_ATTEMPTS - 1}...", file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            all_spans.extend(response.get("resources", []))
            break

    return all_spans


# QueriesSpansV1 rejects (or clamps) any limit above this.
SPAN_QUERY_PAGE_SIZE = 500

# The tool_response span_type is the single canonical signal for "a tool call
# completed": it carries the call's name, status, tool.result_is_error, and
# duration_ms for the full round trip. The paired "tool" span_type (the request)
# is intentionally NOT counted here -- matching both via a "tool" in span_type
# substring check (as this script used to) double-counts every single tool call,
# since "tool_response" also contains the substring "tool" (confirmed live:
# every tool invocation emits exactly one "tool" span + one "tool_response" span).
TOOL_RESPONSE_SPAN_TYPE = "tool_response"


def query_span_ids(filter_expr: str, max_results: int, sort: str = "start_time|desc") -> list[str]:
    """Query span IDs (FQL syntax), paginating with offset in pages of SPAN_QUERY_PAGE_SIZE.

    Stops at max_results IDs, or earlier once the API reports no more results. Errors
    propagate to the caller rather than being reported as an empty result.

    Args:
        filter_expr: FQL filter for QueriesSpansV1
        max_results: Maximum number of span IDs to return
        sort: Sort expression (default: newest first)

    Returns:
        List of span IDs, at most max_results long
    """
    ids: list[str] = []
    offset = 0
    while len(ids) < max_results:
        page_size = min(SPAN_QUERY_PAGE_SIZE, max_results - len(ids))
        params = {
            "filter": filter_expr,
            "limit": str(page_size),
            "offset": str(offset),
            "sort": sort,
        }
        response = call_native(get_spans_client().queries_spans_v1, parameters=params)
        page = response.get("resources", [])
        ids.extend(page)
        offset += len(page)
        total = response.get("meta", {}).get("pagination", {}).get("total")
        # Stop on an empty page or when the API's total is reached. A short page only ends the
        # loop when no total is reported: the API may clamp a page below the requested limit.
        if not page or (total is not None and offset >= total) or (
            total is None and len(page) < page_size
        ):
            break
    return ids


def _ensure_span_time_filter(filter_str: str) -> str:
    """
    Ensure span queries have time bounds per API requirements.

    The span query API requires time-bounded filters using start_time/end_time.
    If the filter doesn't contain these, default to last 24 hours.
    Uses FQL (Falcon Query Language) syntax.

    Args:
        filter_str: FQL filter string

    Returns:
        Filter string with time bounds guaranteed (FQL syntax)
    """
    # Check if filter already has start_time or end_time
    if re.search(r'\b(start_time|end_time)\s*:', filter_str, re.IGNORECASE):
        return filter_str

    # Add default 24h time window (FQL syntax: field:operator'value')
    default_time = "start_time:>='now-24h'"

    if filter_str.strip():
        # FQL uses + for AND
        return f"({filter_str})+{default_time}"
    return default_time


def run_entity_search(
    entity_name: str,
    entity_plural: str,
    query_fn: Callable[..., dict],
    require_time_filter: bool = False,
) -> None:
    """
    Generic search helper for discovery endpoints.

    Args:
        entity_name: Singular entity name for display (e.g., "span", "template")
        entity_plural: Plural entity name for display (e.g., "spans", "templates")
        query_fn: Callable forwarding its kwargs to a native FalconPy query method, e.g.
            `lambda **kw: get_models_client().queries_models_v1(**kw)`. Must be a lambda
            (not a bound method fetched eagerly by the caller) so that get_*_client()
            — which resolves credentials and can exit(1) if they're missing — only runs
            after argparse below has had a chance to handle --help / bad args. Called as
            call_native(query_fn, parameters=params).
        require_time_filter: If True, ensure time bounds in filter (for span queries)
    """
    parser = argparse.ArgumentParser(
        description=f"Query {entity_plural}"
    )
    parser.add_argument("--filter", help="FQL filter", default="")
    parser.add_argument("--limit", type=int, default=100, help="Max results")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    filter_str = args.filter

    # Span queries require time bounds per API documentation
    if require_time_filter:
        filter_str = _ensure_span_time_filter(filter_str)
        if filter_str != args.filter:
            print("INFO: Added default time filter (last 24h) to span query", file=sys.stderr)

    params: dict[str, Any] = {"limit": args.limit, "offset": args.offset}
    if filter_str:
        params["filter"] = filter_str

    response = call_native(query_fn, parameters=params)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    total = response.get("meta", {}).get("pagination", {}).get("total", len(resources))

    if not resources:
        print(f"No {entity_plural} found.")
        return

    print(f"Found {len(resources)} {entity_name} ID(s) (total: {total}):")
    for entity_id in resources:
        print(f"  {entity_id}")
