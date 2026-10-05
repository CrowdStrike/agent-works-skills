#!/usr/bin/env python3
"""
kb_file_download.py - Download a file from a Charlotte AI AgentWorks knowledge base.

Calls GET /agentic-studio/entities/knowledge_base_files/download/v1 with the shared FalconPy
token and writes the response bytes as-is (the FalconPy wrapper would parse text/JSON bodies).

Examples:
    python kb_file_download.py --kb-id <uuid> --file-id <uuid> --output data.txt
"""

import argparse
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
from auth import get_raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a file from a knowledge base")
    parser.add_argument("--kb-id", required=True, help="Knowledge base ID")
    parser.add_argument("--file-id", required=True, help="File ID to download")
    parser.add_argument("--output", required=True, help="Output path to save file")
    args = parser.parse_args()

    params = {
        "knowledge_base_id": args.kb_id,
        "id": args.file_id,
    }

    # Not the FalconPy EntitiesKnowledgeBaseFilesDownloadV1 wrapper: it json.loads text/plain
    # bodies (crashing on .txt/.md files) and parses application/json into a dict (.json files).
    content = get_raw("/agentic-studio/entities/knowledge_base_files/download/v1", params)
    if not content:
        print("ERROR: No file content returned", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "wb") as f:
        f.write(content)

    print(f"File downloaded successfully: {args.output} ({len(content)} bytes)")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
