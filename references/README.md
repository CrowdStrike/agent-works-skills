# Technical References

This directory contains technical references for Claude Code skills and plugin maintainers.

## For Skills (Claude's Reference Material)

These files are loaded by SKILL.md files to provide technical context:

- **[fql-syntax.md](fql-syntax.md)** - FQL query language syntax
- **[span-constraints.md](span-constraints.md)** - Span time filter requirements
- **[invocation-patterns.md](invocation-patterns.md)** - Agent invocation workflows
- **[workflow-integration.md](workflow-integration.md)** - How skills connect

## For Maintainers/Contributors

These files document the plugin architecture and validation:

- **[developer-guide.md](developer-guide.md)** - Development patterns, testing
- **[mcp-compatibility.md](mcp-compatibility.md)** - MCP server integration

## Usage in Skills

Skills reference these files like:

```markdown
---
name: discovery
description: Query Charlotte AI AgentWorks resources
---

## Prerequisites

**CRITICAL:** Read FQL syntax reference first:
- See `references/fql-syntax.md` for complete syntax
- See `references/span-constraints.md` for time requirements
```

## Not for End Users

End users should read:
- Root `README.md` - Installation and setup
- `docs/USE_CASES_VALIDATED.md` - Examples and use cases
- `docs/TROUBLESHOOTING.md` - Common issues

These technical references are for Claude's internal use when executing skills.
