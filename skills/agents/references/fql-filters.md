# FQL Filters for Charlotte AI AgentWorks Agent Queries

Applies to `GET /agentic-studio/queries/agents/v2` (used by `agent_search.py`).

## What actually works (confirmed 2026-09-22, live tenant)

Three matching modes, on two nested fields:

```
id:'756e80ab-a906-4d5f-89ad-7e89b93acf36'                       # exact ID match
active_version.name:'CV1 Root Access Hunter'                    # exact name match (case-sensitive)
active_version.name:~'root access'                              # FUZZY/CONTAINS match — case-insensitive substring, matches anywhere in the string
active_version.description:~'privilege escalation'              # same fuzzy operator works on description too
```

**The `:~` operator is the real server-side "contains" search** for this endpoint — it is NOT
the same as the wildcard `*'...'` syntax used elsewhere in this repo (e.g. the knowledge-bases
skill's `name:*'*term*'`, which is a different endpoint with a different, working wildcard
implementation). On the agents endpoint, `*'...'` wildcards on `active_version.name` return
**zero** results (confirmed below); `:~` is the one that actually does substring matching here.

**Use `:~` for name/topic search going forward** — this is the primary/first tool now, not
`agent_list.py`. It's a single API call regardless of tenant size, works case-insensitively, and
matches substrings anywhere in the field (prefix, middle, or suffix):

```bash
python agent_search.py --filter "active_version.name:~'root access'"
python agent_search.py --filter "active_version.description:~'privilege escalation'"
```

`agent_list.py` is still useful when you need **combined criteria** in one pass (name substring +
date range + publish status), sorted/paginated table output, or a substring match on a field `:~`
doesn't cover — but for a plain "find agents matching this term," reach for `agent_search.py`
with `:~` first.

## History of this doc being wrong twice — read this before trusting your own new finding either

1. **First version (2026-09-21):** concluded "only `id` works," after testing `name:'...'`,
   `name:'*...*'`, `name.raw:'*...*'` — but never tried the correct nested path
   `active_version.name` at all. Wrong by omission.
2. **Second version (2026-09-22, same day, still wrong):** corrected the field to
   `active_version.name`, confirmed exact match works, tested wildcard forms
   (`active_version.name:*'*term*'`, prefix, suffix) and found they all return zero, and
   concluded "no substring support on this endpoint, use `agent_list.py`." That conclusion was
   *also* wrong — it tested the wrong *operator* for substring matching (`*'...'` wildcard syntax)
   instead of the `:~` fuzzy operator, which does exactly that and was only discovered by capturing
   the real Falcon UI's own network request (`filter=active_version.name%3A~%27CV%27` — url-decoded:
   `active_version.name:~'CV'`).

**Lesson: when a filter "doesn't support substring matching," that usually means you haven't
found the right operator yet, not that the capability doesn't exist.** Before writing a negative
conclusion into this file, check what the actual product UI sends over the wire (network tab) for
the equivalent search, rather than only trying variations of syntax you already know from other
endpoints.

## What does NOT work

```
name:'my-agent'                              # top-level `name` (not active_version.name) -- any form
name:~'my-agent'                             # top-level `name` -- fuzzy doesn't help, field isn't there
active_version.name:*'*my-agent*'            # wildcard *'...' syntax -- NOT the substring operator on this endpoint
active_version.name:'my-agent*'              # prefix wildcard -- same, doesn't work
active_version.name:'*my-agent'              # suffix wildcard -- same, doesn't work
active_version.name:'cv1 root access hunter' # exact match is case-SENSITIVE -- wrong case returns zero
```

A `q` query param (hoping for full-text search) is also silently ignored — same unfiltered result
set as no filter at all.

**Why:** `name`/`description` are properties of `active_version`, not top-level indexed fields on
the agent entity. Once you use the correct nested path, exact match (`:`) and fuzzy/contains match
(`:~`) both work; wildcard glob syntax (`*'...'`) does not — this endpoint's fuzzy operator
replaces the need for it.

## How to find an agent by name or topic

**One-shot substring/topic search (recommended default):**
```bash
python agent_search.py --filter "active_version.name:~'search term'"
# or across description too:
python agent_search.py --filter "active_version.description:~'search term'"
```

**If you already know the exact, full, correctly-cased name** (marginally faster, but `:~` works
fine for this case too):
```bash
python agent_search.py --filter "active_version.name:'Exact Full Name'"
```

**If you need combined criteria, sorting, or a table** (date range + status + name substring all
at once, paginated output):
```bash
python agent_list.py --name-contains "topic" --status published --modified-since 2026-09-01
```
This pages through the list endpoint for all IDs, batch-fetches entities, and filters/sorts/
paginates client-side — on a ~1700-agent tenant that's ~17 list calls + ~17 batch-get calls.
Reach for `agent_search.py` with `:~` first; only fall back to this for multi-criteria queries.

## Other confirmed filter syntax (general FQL, not agent-specific)

See `references/fql-syntax.md` at the repo root for span/trace query syntax (operators, quoting,
AND/OR, arrays, date math). That reference is for the tracing/spans API, not this agents endpoint —
the syntax rules are similar, but which *fields* and *operators* are supported differs per
endpoint and isn't documented by CrowdStrike; verify empirically before relying on a new
field/operator, and check the product UI's actual network requests when in doubt — that's how the
`:~` operator in this doc was actually discovered.
