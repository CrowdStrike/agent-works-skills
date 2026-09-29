#!/usr/bin/env python3
"""
spans_search.py - Query Charlotte AI AgentWorks trace spans.

Uses the native FalconPy Spans.queries_spans_v1 method.

Examples:
    python spans_search.py --filter 'agent_id:"..."'
    python spans_search.py --limit 50
"""

import sys
import os

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import get_spans_client
from discovery_helpers import run_entity_search


def main() -> None:
    run_entity_search(
        entity_name="span",
        entity_plural="spans",
        # Deferred so get_spans_client() (which resolves credentials) only runs
        # after argparse has had a chance to handle --help / bad args.
        query_fn=lambda **kw: get_spans_client().queries_spans_v1(**kw),
        require_time_filter=True,  # Span queries require time bounds
    )


if __name__ == "__main__":
    main()
