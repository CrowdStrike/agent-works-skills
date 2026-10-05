# Charlotte AI AgentWorks Agents API Reference

Endpoints under `/agentic-studio/...`, called through the native FalconPy `Agents` and `AgentVersions`
classes via `common/scripts/auth.py` (`get_agents_client()`, `call_native()`).

## GET /agentic-studio/queries/agents/v2 — list agent IDs

Params: `limit`, `offset`, `filter` (FQL).

**`id` (exact) and `active_version.name`/`active_version.description` (exact match with `:`, or
substring/fuzzy match with `:~`) are working filter fields** — confirmed empirically
(2026-09-22, live tenant, corrected from an earlier wrong "only `id` works" conclusion; see
`fql-filters.md`'s "History of this doc being wrong twice" section). Top-level `name` (not
nested under `active_version`) never works, in any form:

```
name:'my-agent'
name:'*my-agent*'
name:'My Agent*'
name.raw:'*my-agent*'
```

The correct nested field + the `:~` fuzzy operator (found by capturing the Falcon UI's own
network request, not by guessing) IS the working substring search:

```
active_version.name:~'my-agent'                   # substring, case-insensitive -- works
active_version.description:~'search term'         # same operator works on description
active_version.name:'Exact Case-Sensitive Name'    # exact match -- also works
active_version.name:*'*my-agent*'                  # wildcard glob syntax -- does NOT work (zero results)
```

There is also no `q` / full-text param; passing one is silently ignored (same result set as no
filter).

**To find agents by name/topic**, prefer `agent_search.py --filter "active_version.name:~'term'"`
— one API call. Only fall back to paging through all IDs (via `agent_list.py`) when you need
multiple combined criteria (name + date range + status) or table/pagination output:
1. Page through `queries/agents/v2` with `limit`/`offset` to collect all agent IDs (`meta.pagination.total` gives the count; this tenant has ~1700).
2. Batch-fetch entities via `entities/agents/v2` (see below) and filter on `active_version.name` client-side.

## GET /agentic-studio/entities/agents/v2 — get agent entities by ID

**Critical: `ids` must be passed as a real list/array param, not a comma-joined string.**

```python
# ❌ WRONG — API treats the whole comma-joined string as one literal id and returns
# {"errors": [{"message": "failed to retrieve agent", "id": "<id1>,<id2>"}], "resources": null}
call_native(get_agents_client().get_studio_agents, ids=",".join([id1, id2]))

# ✅ CORRECT
call_native(get_agents_client().get_studio_agents, ids=[id1, id2])
```

This works for both a single id and a batch (tested up to 100 ids per call). `agent_get.py` was
fixed to use the list form on 2026-09-21 — if you see this comma-join pattern reappear (e.g. after
a revert), it's the bug, not a new API restriction.

### Response shape

Top-level entity fields: `id`, `cid`, `is_deleted`, `is_in_sync`, `published_version_ids` (list,
empty if never published), `tags`.

Everything version-specific — `name`, `description`, `system_prompt`, `model`, `tools`,
`knowledge_base_ids`, `input_format`, `output_format`, `model_config`, `targeting_config`,
`skill_ids`, `parent_version_ids` — lives under `active_version` (the latest **published** version,
or latest version if never published — see SKILL.md's "What Version You'll See" section). There is
no top-level `name`/`model_id`/`status`/`created_at`/`versions` on the entity itself; scripts that
print those directly are buggy (this was the case for `agent_get.py`'s non-JSON branch until fixed
2026-09-21).

## POST /agentic-studio/entities/agents/v3 — create/update

Body: `{"version_definition": {...}, "id": "<uuid>"}` (omit `id` to create). See `agent_upsert.py`
for the full `version_definition` shape.

`--json` output mode: `agent_upsert.py` had a `json`-shadowing bug (conditional `import json`
inside `main()` made the module-level `json` import local for the whole function, per Python's
static scoping rules) — fixed 2026-09-21. If `--json` throws `UnboundLocalError: json`, check for
a stray `import json` reintroduced inside `main()`.

## PATCH /agentic-studio/entities/agents/v3 — publish

Body: `{"id": "<agent-uuid>", "version_id": "<version-uuid>", "is_published": true}`. Needs both
IDs — the agent ID alone is not enough.
