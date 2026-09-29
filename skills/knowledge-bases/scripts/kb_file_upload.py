#!/usr/bin/env python3
"""
kb_file_upload.py - Upload a file to a Charlotte AI AgentWorks knowledge base.

Uses native FalconPy KnowledgeBaseFiles.EntitiesKnowledgeBaseFilesCreateV1
with multipart/form-data.

Examples:
    python kb_file_upload.py --kb-id <uuid> --file data.txt --description "Test file"
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
from auth import call_native, get_kb_files_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a file to a knowledge base")
    parser.add_argument("--kb-id", required=True, help="Knowledge base ID")
    parser.add_argument("--file", required=True, help="Path to file to upload")
    parser.add_argument("--description", default="", help="File description")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    client = get_kb_files_client()

    # FalconPy's EntitiesKnowledgeBaseFilesCreateV1 only reads flat kwargs
    # (knowledge_base_id, file, file_name, file_description) via its own
    # params_to_keywords -- it never looks inside a data=/files= wrapper, so
    # passing those silently drops `file` and every call fails with
    # "You must provide a file to upload." (confirmed against the installed
    # crowdstrike-falconpy==1.6.5 source, 2026-09-23).
    with open(args.file, "rb") as f:
        response = call_native(
            client.EntitiesKnowledgeBaseFilesCreateV1,
            knowledge_base_id=args.kb_id,
            file_name=os.path.basename(args.file),
            file_description=args.description,
            file=f,
        )

    if args.json:
        print(json.dumps(response, indent=2))
        return

    resources = response.get("resources", [])
    if not resources:
        print("File upload succeeded but no resource returned.", file=sys.stderr)
        sys.exit(1)

    file_entity = resources[0]
    print("File uploaded successfully:")
    print(f"  File ID: {file_entity.get('id')}")
    print(f"  KB ID: {file_entity.get('knowledge_base_id')}")
    print(f"  Name: {file_entity.get('name')}")
    print(f"  Status: {file_entity.get('status', 'processing')}")
    print("\nNote: File may take a few moments to process. Poll with kb_get.py to check status.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # call_native raises RuntimeError on HTTP errors (e.g. 403 missing scope).
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
