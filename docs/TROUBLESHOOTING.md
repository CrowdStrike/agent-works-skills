# Troubleshooting Guide

Quick fixes for common issues. For detailed technical references, see `references/` directory.

## Common Issues and Solutions

### Hydration Failures

#### Issue: "Failed to retrieve trace spans" with 400 error

**Symptom:**
```
Warning: Failed to hydrate batch 1: HTTP 400: {'code': 400, 'message': 'Failed to retrieve trace spans'}
```

**Root Cause:** Batch size too large or incorrect parameter format.

**Solutions:**

1. **Use repeated `ids=` parameters** (NOT comma-separated):
   ```python
   # ✅ CORRECT: pass a real list; FalconPy sends repeated ids= parameters
   call_native(get_spans_client().entities_spans_v1, ids=batch)

   # ❌ WRONG
   call_native(get_spans_client().entities_spans_v1, ids=",".join(batch))
   ```

2. **Reduce batch size** to 50 or lower:
   ```python
   from discovery_helpers import hydrate_spans
   spans = hydrate_spans(span_ids, batch_size=50)  # Default is 50
   ```

3. **Use the shared helper** - it handles batching automatically:
   ```python
   from discovery_helpers import hydrate_spans
   spans = hydrate_spans(span_ids)  # Automatically batches in chunks of 50
   ```

### FQL Filter Syntax Errors

#### Issue: "invalid filter" 400 errors

**Symptom:**
```
ERROR: HTTP 400: {'code': 400, 'message': 'invalid filter'}
```

**Root Cause:** Using SQL-like syntax instead of FQL (Falcon Query Language).

**Common Mistakes:**

| Wrong (SQL-like) | Correct (FQL) |
|------------------|---------------|
| `field>=value` | `field:>='value'` |
| `field="value"` | `field:'value'` |
| `a AND b` | `a+b` |
| `a OR b` | `a,b` |
| `field IN (a,b)` | `field:['a','b']` |
| `start_time>=now-24h` | `start_time:>='now-24h'` |

**Solution:** Let Claude handle the syntax - just describe what you want to find.

If you need to write queries manually, see `references/fql-syntax.md`.

### Span Filter Rejection

#### Issue: Span query filters rejected even with basic time syntax

**Symptom:** Time-based filters fail with 400 errors even when syntax appears correct.

**Diagnostic Steps:**

1. **Test what actually works** - Run the filter syntax tester:
   ```bash
   cd skills/discovery
   ../../scripts/python.sh scripts/probe_span_filters.py
   ```
   
   This tests: empty filters, date math (`now-24h`), RFC3339 timestamps, alternative operators, field name variations.

2. **Use invocation-ID-driven approach** if time filtering doesn't work:
   ```bash
   # Inspect specific invocation
   cd skills/invocation
   ../../scripts/python.sh scripts/inspect_invocation.py --invocation-id <invocation-id>
   ```

3. **Check field structure** with diagnostics:
   ```bash
   cd skills/discovery
   ../../scripts/python.sh scripts/diagnose_spans.py --sample 10
   ```
   
   Shows available fields, attribute structure, and recommended filter patterns.

### Missing Invocation ID

#### Issue: Cannot find invocation_id in span attributes

**Symptom:**
```
ERROR: Could not resolve trace_id for invocation
No invocation_id found in span attributes
```

**Root Causes:**

1. **Looking at wrong span type** - Child spans (tool calls, LLM) don't have `aw_agent.*` attributes
2. **Wrong attribute path** - Attributes are FLAT with dot notation, not nested

**Solutions:**

1. **Query for root spans** first:
   ```python
   filter_expr = "span_type:['aw_agent','aw_eval_run_started']"
   ```

2. **Use flat attribute path**:
   ```python
   # ✅ CORRECT
   invocation_id = attrs.get("aw_agent.invocation_id")
   agent_id = attrs.get("aw_agent.id")
   
   # ❌ WRONG (nested)
   invocation_id = attrs.get("aw_agent", {}).get("invocation_id")
   ```

3. **Understand span types**:
   - **Root spans** (`aw_agent`, `aw_eval_run_started`): Have `aw_agent.*` attributes
   - **Child spans** (tools, LLM, KB): NO `aw_agent.*` attributes, only linked by `trace_id`

### Missing Agent ID

#### Issue: Filter by agent_id returns no results

**Symptom:**
```
Found 0 span IDs
No spans found for agent <uuid>
```

**Root Causes:**

1. **Agent has no UI invocations** - `aw_agent.id` only exists in UI-triggered invocations
2. **Wrong time window** - Spans older than 90 days are not available
3. **Wrong field name** - Looking for `aw_agent.agent_id` instead of `aw_agent.id`
4. **Field not indexed** - The nested attribute field isn't indexed by the API

**Solutions:**

1. **Use correct field name**:
   ```python
   filter_expr = f"attributes.aw_agent.id:'{agent_id}'"  # NOT agent_id
   ```

2. **Check invocation source**:
   - **UI invocations**: Have `aw_agent.id`
   - **Inline/programmatic invocations**: NO `aw_agent.id`

3. **Use fallback strategy** if agent_id filter fails:
   ```python
   # Try agent_id first
   filter_expr = f"(attributes.aw_agent.id:'{agent_id}'+start_time:>='now-{days}d')"
   
   # Fallback: query all, filter client-side
   if not span_ids:
       filter_expr = f"start_time:>='now-{days}d'+span_type:['aw_agent','aw_eval_run_started']"
       # Then filter by agent_id in extracted spans
   ```

4. **Check field structure**:
   ```bash
   cd skills/discovery
   ../../scripts/python.sh scripts/diagnose_spans.py --sample 10
   ```
   
   Output shows whether the field uses nested or flat structure:
   - **Nested**: `attributes.aw_agent.id:'<uuid>'` (the correct field -- see Root Cause 3 above)
   - **Flat**: `attributes.agent_id:'<uuid>'`
   - **Missing**: Use fallback (query by time, filter client-side)

### Span Time Constraint Errors

#### Issue: Query fails with time-related errors

**Root Cause:** Span queries REQUIRE time bounds (90-day max).

**Solution:** Always include time filter:
```python
# ✅ CORRECT
filter_expr = "(your_filter)+start_time:>='now-7d'"

# Use helper that auto-adds time bounds
from discovery_helpers import _ensure_span_time_filter
filter_expr = _ensure_span_time_filter(user_filter)
```

See `references/span-constraints.md` for technical details.

## Diagnostic Tools

### Check Span Structure

When you're not sure about span field structure:

```bash
cd skills/discovery
../../scripts/python.sh scripts/diagnose_spans.py --sample 5
```

Shows:
- Available top-level fields
- Available attribute fields (for filtering)
- Sample span with all fields
- Detected agent/invocation IDs
- Recommended filter patterns

### Test Filter Syntax

When a filter isn't working:

```bash
cd skills/discovery
../../scripts/python.sh scripts/probe_span_filters.py
```

Tests different filter syntaxes systematically.

## Understanding Error Messages

### "400 Bad Request" errors

Usually means:
- Wrong FQL syntax (use `:>=` not `>=`)
- Missing time bounds on span query
- Invalid field name
- Wrong parameter format (comma-separated vs repeated)

**Solution:** Use diagnostic tools or see `references/fql-syntax.md` for manual query syntax.

### "403 Forbidden" errors

Usually means:
- Missing OAuth 2.0 scopes
- Incorrect credentials
- API token expired

**Solution:** Check `common/scripts/auth.py` configuration and scopes.

### "Empty results" (not errors)

Usually means:
- Wrong time window (spans too old or too new)
- Filter doesn't match any data
- Looking at wrong span type
- Agent has no invocations yet
- Field structure differs from expected

**Solution:** Broaden time window, check span types, verify agent has been invoked, run diagnostics to check field structure.

## Performance Issues

### Slow Hydration

**Symptom:** Hydrating 1000+ spans takes very long or fails.

**Solution:**
1. Filter by span_type to reduce result set:
   ```python
   "+span_type:['aw_agent','aw_eval_run_started']"  # 100x fewer spans
   ```

2. Use smaller batch size:
   ```python
   hydrate_spans(span_ids, batch_size=25)
   ```

3. Reduce query limit:
   ```python
   params = {"filter": filter_expr, "limit": "100"}  # Not 1000
   ```

### Slow Analysis

**Symptom:** `analyze_agent.py` takes very long.

**Solutions:**
1. Reduce time window: `--days 7` instead of `--days 90`
2. Let it run - analyzing 1000+ spans with version detection takes time
3. Use `--json` output and parse programmatically if running repeatedly

## Fallback Strategies

### Server-Side vs Client-Side Filtering

**Server-side filtering (preferred):**
- ✅ Fast (fewer spans returned)
- ✅ Low bandwidth
- ❌ Requires indexed fields

**Client-side filtering (fallback):**
- ✅ Always works
- ✅ Handles any field structure
- ❌ Slower (more data transferred)
- ❌ Capped at 1000 spans per query

Scripts with automatic fallback: `list_invocations.py`, `analyze_agent.py`

### Alternative: Use Known Invocation IDs

If span queries continue to fail:

1. **Get invocation ID from invoke response:**
   ```bash
   ../../scripts/python.sh scripts/invoke_agent.py --id <agent-id> --message "test"
   # Output: invocation_id
   ```

2. **Directly inspect that invocation:**
   ```bash
   ../../scripts/python.sh scripts/inspect_invocation.py --invocation-id <invocation-id>
   ```

3. **Or query by trace_id if you know it:**
   ```bash
   ../../scripts/python.sh scripts/spans_search.py \
     --filter "trace_id:'<trace-id>'+start_time:>='now-24h'"
   ```

## Getting Help

1. **Run diagnostics** (most useful):
   - `diagnose_spans.py` - Check span structure
   - `probe_span_filters.py` - Test filter syntax

2. **Ask Claude to try a different approach**:
   - "Try broader time window"
   - "Query without filters first"
   - "Use client-side filtering"

3. **Check credentials**:
   - `python3 common/scripts/auth.py`
   - Verify OAuth 2.0 scopes in Falcon Console

4. **Read documentation**:
   - Root `README.md` - Setup and credentials
   - `docs/USE_CASES_VALIDATED.md` - What's possible

## Quick Reference: Common Patterns

### Query spans for an agent
```python
filter_expr = (
    f"(attributes.aw_agent.id:'{agent_id}'"
    f"+start_time:>='now-7d')"
    f"+span_type:['aw_agent','aw_eval_run_started']"
)
```

### Resolve invocation to trace
```python
# Step 1: Find root span with invocation_id
filter_expr = f"attributes.aw_agent.invocation_id:'{invocation_id}'"
span_ids = query_span_ids(filter_expr, max_results=5)

# Step 2: Hydrate to get trace_id
spans = hydrate_spans(span_ids[:3])
trace_id = spans[0]["trace_id"]

# Step 3: Get full trace
filter_expr = f"trace_id:'{trace_id}'"
all_span_ids = query_span_ids(filter_expr, max_results=5000)  # paginates past 500 per page
all_spans = hydrate_spans(all_span_ids)
```

### Extract metadata from spans
```python
for span in spans:
    attrs = span.get("attributes", {})
    
    # Flat access (not nested)
    invocation_id = attrs.get("aw_agent.invocation_id")
    agent_id = attrs.get("aw_agent.id")  # Only in UI invocations
    model = attrs.get("aw_agent.definition.model")
    tools = attrs.get("aw_agent.definition.tools", [])
```
