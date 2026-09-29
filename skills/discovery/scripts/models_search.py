#!/usr/bin/env python3
"""
models_search.py - Query available Charlotte AI AgentWorks models.

Uses the native FalconPy Models.queries_models_v1 method.

NOTE: The models query API filter only works by ID, not by name or other fields.
      To find models, query all and filter client-side, or use specific model IDs.

Examples:
    python models_search.py --limit 50
    python models_search.py --filter 'id:"bedrock.claude-4-6-sonnet"'
"""

import argparse
import json
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
from auth import call_native, get_models_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Query available models")
    parser.add_argument("--filter", help='FQL filter', default="")
    parser.add_argument("--limit", type=int, default=100, help="Max results")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    params = {"limit": args.limit, "offset": args.offset}
    if args.filter:
        params["filter"] = args.filter

    response = call_native(get_models_client().queries_models_v1, parameters=params)

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    total = response.get("meta", {}).get("pagination", {}).get("total", len(resources))

    if not resources:
        print("No models found.")
        return

    print(f"Found {len(resources)} model ID(s) (total: {total}):")
    for model_id in resources:
        print(f"  {model_id}")


if __name__ == "__main__":
    main()
