# Charlotte AI AgentWorks Knowledge Bases API Reference

Native FalconPy `KnowledgeBases`/`KnowledgeBaseFiles`/`KnowledgeBaseAuditEvents` classes, called
via `common/scripts/auth.py`'s `get_kb_client()`.

## GET /agentic-studio/queries/knowledge_bases/v1 — list KB IDs (`KnowledgeBases.QueriesKnowledgeBasesV1`)

Params: `limit`, `offset`, `filter` (FQL).

**Unlike the agents list endpoint, `name` IS a working filter field here** — confirmed
2026-09-21, live tenant — but only with single-quoted FQL values. See `fql-filters.md` for the
full syntax breakdown (the double-quote trap, wildcard substring matching).

There is no full-text search across `name` + `description` server-side. For an open-ended "find
any KB about X" search where you don't know the exact name, use `kb_list.py`, which pages through
all IDs and filters client-side.

## GET /agentic-studio/entities/knowledge_bases/v1 — get KB entities by ID (`KnowledgeBases.EntitiesKnowledgeBasesV1`)

`ids` is passed as `ids=[...]` (a real list) to the native method — this already works correctly
in `kb_get.py`/`kb_list.py`.

### Response shape

KB entity fields are flat/top-level — `id`, `name`, `description`, `created_at`, `updated_at`,
`file_count` — unlike agents, where most fields live nested under `active_version`. No
version/publish concept applies to KBs.

## POST /agentic-studio/entities/knowledge_bases/v1 — create/update (`KnowledgeBases.EntitiesKnowledgeBasesCreateV1` / update variant)

Used by `kb_upsert.py`. Omit `--id` to create, pass `--id` to update.

## GET /agentic-studio/queries/knowledge_base_files/v1 — list file IDs in a KB (`KnowledgeBaseFiles.QueriesKnowledgeBaseFilesV1`)

Params: `knowledge_base_id` (required), `limit`, `offset`. Used by `kb_files_list.py`. Confirmed to
match the exact request the Falcon UI itself sends (network tab, 2026-09-21, live tenant).

## GET /agentic-studio/entities/knowledge_base_files/v1 — get file entities by ID (`KnowledgeBaseFiles.EntitiesKnowledgeBaseFilesV1`)

**`knowledge_base_id` is required alongside `ids`** — confirmed 2026-09-21, live tenant. Passing
`ids` alone fails with `{"code": 400, "message": "knowledge_base_id parameter is required"}`. This
matches the Falcon UI's own request shape (`?ids=...&knowledge_base_id=...`).

```python
# ❌ WRONG — fails with 400
client.EntitiesKnowledgeBaseFilesV1(ids=[file_id])

# ✅ CORRECT
client.EntitiesKnowledgeBaseFilesV1(knowledge_base_id=kb_id, ids=[file_id])
```

### Response shape

File entity fields: `id`, `knowledge_base_id`, `name`, `size`, `content_type`, `status`
(`PROCESSED` once ready), `metadata.description`, `created_at`/`updated_at`,
`created_by`/`updated_by` (same shape as KB entities).

## PUT+POST /agentic-studio/entities/knowledge_base_files/v1 — upload file (`KnowledgeBaseFiles`)

Multipart/form-data, handled by FalconPy's native class — do not attempt manual `curl` without
exact boundary formatting (see `kb_file_upload.py`).

## GET /agentic-studio/entities/knowledge_base_audit_events/v1 and queries/... — audit events (`KnowledgeBaseAuditEvents`)

Used by `kb_audit.py` for file uploads, KB updates, etc.
