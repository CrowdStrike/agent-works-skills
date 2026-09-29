#!/usr/bin/env python3
"""
tools_get.py - Get full tool entities with smart search across name and description.

Unlike tools_search.py (which hits /queries endpoint), this directly fetches
tool entities and provides client-side filtering across multiple fields.

Examples:
    # Search by keyword in name OR description
    python tools_get.py --search "security vulnerability"

    # Discover tools in an exact category
    python tools_get.py --category falcon_platform

    # Get specific tool IDs
    python tools_get.py --ids <id1> <id2>

    # List all tools
    python tools_get.py --limit 100

    # See tool counts per category before deciding where to search
    python tools_get.py --list-categories
"""

import argparse
import json
import sys
import os
import re

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "..", "..", "..", "common", "scripts",
    ),
)
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import call_native, get_tools_client

# Known tool categories (tenant-specific availability -- a zero count is not an
# error). Keep this in sync with discovery/SKILL.md's category table.
KNOWN_CATEGORIES = [
    "charlotte-mcp",
    "agents",
    "gce",
    "fusion_workflows",
    "falcon_platform",
    "integrations",
    "Collections",
    "action_requests",
    "foundry-user-mcp",
]


def normalize_search_term(term: str) -> str:
    """Normalize search terms for better matching."""
    # Remove common overly-broad terms
    stop_words = {'falcon', 'crowdstrike', 'cs', 'cspm', 'the', 'a', 'an'}
    words = term.lower().split()
    filtered = [w for w in words if w not in stop_words]
    return ' '.join(filtered) if filtered else term.lower()


def search_in_text(text: str, search_terms: str) -> bool:
    """
    Check if search terms appear in text.
    Returns True if ANY search term matches.
    """
    if not text or not search_terms:
        return False

    text_lower = text.lower()
    normalized_search = normalize_search_term(search_terms)

    # Split on whitespace and search for each term
    for term in normalized_search.split():
        if term in text_lower:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get Charlotte AI AgentWorks tools with smart search"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--ids",
        nargs="+",
        help="Specific tool IDs to fetch"
    )
    group.add_argument(
        "--search",
        help="Search keyword(s) in tool name, description, and category (space-separated for OR logic)"
    )
    parser.add_argument(
        "--category",
        help="Filter by exact, case-sensitive tool category"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max results to return (default: 100); with --search, applies to the matches"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show search match details"
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="Print tool counts per known category and exit (cheap: no hydration). "
             "Use this before --search to decide which --category to scope to."
    )

    args = parser.parse_args()

    if args.list_categories:
        tools_client = get_tools_client()
        print(f"{'Category':<20} Count")
        print(f"{'-' * 20} -----")
        for category in KNOWN_CATEGORIES:
            response = call_native(
                tools_client.queries_tools_v1,
                parameters={"limit": 1, "filter": f"category:'{category}'"},
            )
            total = (response.get("meta") or {}).get("pagination", {}).get("total", 0)
            print(f"{category:<20} {total}")
        print(
            "\nA zero count is not an error -- category availability is tenant-specific.",
            file=sys.stderr,
        )
        return


    # Step 1: Query for tool IDs
    if args.ids:
        tool_ids = args.ids
    else:
        # Query tool IDs first. --search filters client-side, so it must see every
        # tool (paginated); otherwise it would only search the first --limit IDs.
        page_size = 100
        wanted = None if args.search else args.limit
        tool_ids = []
        while wanted is None or len(tool_ids) < wanted:
            query_params = {"limit": page_size, "offset": len(tool_ids)}
            if args.category:
                query_params["filter"] = f"category:'{args.category}'"
            query_response = call_native(get_tools_client().queries_tools_v1, parameters=query_params)
            page = query_response.get("resources", [])
            tool_ids.extend(page)
            total = (query_response.get("meta") or {}).get("pagination", {}).get("total")
            if not page or len(page) < page_size or (total is not None and len(tool_ids) >= total):
                break
        if wanted is not None:
            tool_ids = tool_ids[:wanted]

    if not tool_ids:
        print("No tools found.")
        return

    # Step 2: Hydrate tool entities (batch if needed)
    tools_client = get_tools_client()
    if len(tool_ids) <= 50:
        # Single request for small batches
        response = call_native(tools_client.entities_tools_v1, ids=tool_ids)
        tools = response.get("resources", [])
    else:
        # Batch requests for large sets
        tools = []
        for i in range(0, len(tool_ids), 50):
            batch = tool_ids[i:i+50]
            response = call_native(tools_client.entities_tools_v1, ids=batch)
            tools.extend(response.get("resources", []))

    if not tools:
        print("No tools found.")
        return

    # Defensively enforce exact category matching after hydration as well.
    if args.category:
        tools = [tool for tool in tools if tool.get("category") == args.category]

    # Client-side filtering if search specified
    if args.search:
        if args.verbose:
            print(f"Searching for: {args.search}", file=sys.stderr)
            print(f"Normalized: {normalize_search_term(args.search)}", file=sys.stderr)
            print("", file=sys.stderr)

        filtered_tools = []
        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            category = tool.get("category", "")

            # Search across name, description, and category
            if (search_in_text(name, args.search) or
                search_in_text(description, args.search) or
                search_in_text(category, args.search)):

                if args.verbose:
                    matches = []
                    if search_in_text(name, args.search):
                        matches.append(f"name: '{name}'")
                    if search_in_text(description, args.search):
                        desc_preview = description[:60] + "..." if len(description) > 60 else description
                        matches.append(f"description: '{desc_preview}'")
                    if search_in_text(category, args.search):
                        matches.append(f"category: '{category}'")
                    print(f"✓ {tool.get('id')}: {' | '.join(matches)}", file=sys.stderr)

                filtered_tools.append(tool)

        tools = filtered_tools[:args.limit]

        if args.verbose:
            print(f"\nMatched {len(tools)} tool(s)\n", file=sys.stderr)

    # Output results
    if args.json:
        print(json.dumps({"resources": tools, "count": len(tools)}, indent=2))
        return

    print(f"Found {len(tools)} tool(s):\n")

    for tool in tools:
        tool_id = tool.get("id", "N/A")
        name = tool.get("name", "N/A")
        category = tool.get("category", "N/A")
        description = tool.get("description", "")

        print(f"ID: {tool_id}")
        print(f"  Name: {name}")
        print(f"  Category: {category}")
        if description:
            # Truncate long descriptions
            desc_display = description[:100] + "..." if len(description) > 100 else description
            print(f"  Description: {desc_display}")
        print()


if __name__ == "__main__":
    main()
