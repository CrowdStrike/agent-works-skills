# FQL Filters for Charlotte AI AgentWorks Knowledge Base Queries

Applies to `GET /agentic-studio/queries/knowledge_bases/v1` (used by `kb_search.py`).

## What actually works (confirmed 2026-09-21, live tenant)

Unlike the agents `queries/agents/v2` endpoint (see `../../agents/references/fql-filters.md`,
where `name` is not filterable at all), `name` **does** work here — but only with
single-quoted FQL string values:

```
name:'KB 2 for Duplication'          # exact match
name:*'*Duplication*'                # substring / "contains" match
created_at:>'2026-01-01T00:00:00Z'   # date comparison
```

## The trap: double quotes silently return zero results

```
name:"my-kb"     # ❌ WRONG — not FQL. Returns 200 OK with 0 matches, no error.
name:'my-kb'     # ✅ CORRECT
```

This repo's general FQL rules (`references/fql-syntax.md`, `references/developer-guide.md`
at the repo root) already state values must be single-quoted — this file exists specifically
because `kb_search.py`'s own docstring/`--help` text used to show the double-quoted form as
its example, which meant following the tool's own usage example produced a silent false
negative (looks like "no matching KB exists" when it's actually a syntax error). The script's
help text has since been corrected; this doc is here so the failure mode doesn't get
reintroduced.

## Finding a KB when you don't know the exact name

`name:*'*term*'` substring matching works, but only for a term you already suspect is in the
name. For open-ended "find any KB related to X" searches, there's no full-text search across
`name` + `description` server-side — use `kb_list.py` instead, which pages through all KB IDs,
hydrates them, and filters client-side on name **and** description substrings:

```bash
python kb_list.py --contains "root access"
```

## ids parameter for kb_get.py

`EntitiesKnowledgeBasesV1(ids=[...])` takes a real list, not a comma-joined string — same
gotcha documented for agents in `../../agents/references/api-reference.md`. This already works
correctly in `kb_get.py`/`kb_list.py`; don't reintroduce a comma-joined string if refactoring.
