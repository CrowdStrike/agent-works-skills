#!/usr/bin/env python3
"""
versions_search.py - Query Charlotte AI AgentWorks agent versions.

Uses the native FalconPy AgentVersions.query_agent_versions_v1 method.

Examples:
    python versions_search.py --filter 'agent_id:"..."'
    python versions_search.py --limit 50
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
from auth import get_agent_versions_client
from discovery_helpers import run_entity_search


def main() -> None:
    run_entity_search(
        entity_name="version",
        entity_plural="agent versions",
        # Deferred so get_agent_versions_client() (which resolves credentials) only
        # runs after argparse has had a chance to handle --help / bad args.
        query_fn=lambda **kw: get_agent_versions_client().query_agent_versions_v1(**kw),
    )


if __name__ == "__main__":
    main()
