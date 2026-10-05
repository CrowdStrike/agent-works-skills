#!/usr/bin/env python3
"""
tools_search.py - Query available Charlotte AI AgentWorks tools.

Uses the native FalconPy Tools.queries_tools_v1 method.

Examples:
    python tools_search.py --filter 'type:"..."'
    python tools_search.py --limit 50
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
from auth import get_tools_client
from discovery_helpers import run_entity_search


def main() -> None:
    run_entity_search(
        entity_name="tool",
        entity_plural="tools",
        # Deferred so get_tools_client() (which resolves credentials) only runs
        # after argparse has had a chance to handle --help / bad args.
        query_fn=lambda **kw: get_tools_client().queries_tools_v1(**kw),
    )


if __name__ == "__main__":
    main()
