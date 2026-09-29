# FQL (Falcon Query Language) Syntax Reference

**Official Documentation:** https://developer.crowdstrike.com/api-reference/falcon-query-language/

## Critical Syntax Rules

### Operators (Colon-Prefixed)

```python
# ✅ CORRECT
"start_time:>='now-24h'"      # Greater than or equal
"end_time:<'now'"              # Less than
"status:'success'"             # Equals

# ❌ WRONG
"start_time>=now-24h"          # Missing colon and quotes
```

### Values (Single-Quoted)

```python
# ✅ CORRECT
"start_time:>='now-45d'"
"agent_id:'<agent-id>'"

# ❌ WRONG
"start_time:>=now-45d"         # Missing quotes
```

### Logical Operators

- **AND:** Use `+`
- **OR:** Use `,`

```python
# ✅ CORRECT
"start_time:>='now-45d'+status:'error'"      # AND
"status:'error',status:'warning'"            # OR
"(start_time:>='now-7d'+status:'error'),priority:'high'"  # Complex

# ❌ WRONG
"start_time:>='now-45d' AND status:'error'"  # Wrong operator
```

### Arrays (Square Brackets)

```python
# ✅ CORRECT
"span_type:['aw_agent','aw_eval_run_started']"
"status:['error','warning','fatal']"

# ❌ WRONG
"span_type:('aw_agent','aw_eval_run_started')"  # Wrong brackets
```

### Grouping (Parentheses)

```python
# ✅ CORRECT
"(start_time:>='now-45d'+start_time:<'now')+span_type:['aw_agent']"
"((status:'error'+severity:'high'),(status:'fatal'))"

# Use parentheses for precedence clarity
```

---

## Common Span Query Patterns

### Time Window
```python
"start_time:>='now-24h'"                    # Last 24 hours
"start_time:>='now-7d'"                     # Last 7 days
"(start_time:>='now-45d'+start_time:<'now')" # Last 45 days with explicit end
```

### Agent Filter (Efficient)
```python
# Root spans only (contains invocation metadata)
"(attributes.aw_agent.id:'<uuid>'+start_time:>='now-7d')+span_type:['aw_agent','aw_eval_run_started']"
```

### Invocation Filter
```python
"attributes.aw_agent.invocation_id:'abc123'"
```

### Trace Filter
```python
"trace_id:'def456'"  # Unique, usually doesn't need time
```

### Combined Filters (Recommended)
```python
# Agent + time + types (RECOMMENDED for listing invocations)
"(attributes.aw_agent.id:'<uuid>'+start_time:>='now-7d')+span_type:['aw_agent','aw_eval_run_started']"

# Agent + time + status (error analysis)
"(attributes.aw_agent.id:'<uuid>'+start_time:>='now-7d'+status:'error')"
```

---

## Understanding Traces and Spans

### Span Tree Structure

A **trace** is a collection of spans forming a tree:
- Root span: `aw_agent` or `aw_eval_run_started` (has agent metadata)
- Child spans: tool calls, LLM, KB lookups (operation-specific)
- All share same `trace_id`, linked by `parent_span_id`

```
Trace (trace_id: abc123)
├─ aw_agent (root) - has agent_id, invocation_id, definition
│  ├─ llm_call (thinking)
│  ├─ tool_call (falcon_platform:search_hosts)
│  └─ kb_lookup (knowledge base query)
```

### Span Relationships

**Root spans** (`aw_agent`, `aw_eval_run_started`):
- Have `attributes.aw_agent.invocation_id`, `attributes.aw_agent.id`, `attributes.aw_agent.definition.*`
- Only 1-2 per trace

**Child spans** (tools, LLM, KB):
- NO `aw_agent.*` attributes
- Linked via shared `trace_id`
- 10-100x more numerous

**For listing invocations:**
```python
"+span_type:['aw_agent','aw_eval_run_started']"
```

**For inspecting a trace:**
```python
"trace_id:'<id>'"  # Gets entire tree
```

---

## Date Math Expressions

```python
'now'          # Current time
'now-1h'       # 1 hour ago
'now-24h'      # 24 hours ago
'now-7d'       # 7 days ago
'now-90d'      # Maximum for spans
'now-7d/d'     # 7 days ago, rounded to start of day
```

---

## Nested Attributes

Access with dot notation:

```python
"attributes.aw_agent.id:'...'"
"attributes.aw_agent.invocation_id:'...'"
"attributes.cost.raw_credit_cents:>100"
```

---

## Common Mistakes

| Wrong | Right |
|-------|-------|
| `start_time>='now-24h'` | `start_time:>='now-24h'` |
| `start_time:>=now-24h` | `start_time:>='now-24h'` |
| `field1 AND field2` | `field1+field2` |
| `field1 OR field2` | `field1,field2` |
| `field:('val1','val2')` | `field:['val1','val2']` |
| `agent_id:<uuid>` | `agent_id:'<uuid>'` |

---

## Python Helper Function

```python
def build_fql_filter(
    agent_id: str | None = None,
    invocation_id: str | None = None,
    start_time: str = "now-24h",
    span_types: list[str] | None = None
) -> str:
    """Build FQL filter with correct syntax."""
    parts = []
    
    if agent_id:
        parts.append(f"attributes.aw_agent.id:'{agent_id}'")
    if invocation_id:
        parts.append(f"attributes.aw_agent.invocation_id:'{invocation_id}'")
    if start_time:
        parts.append(f"start_time:>='{start_time}'")
    if span_types:
        types = "','".join(span_types)
        parts.append(f"span_type:['{types}']")
    
    return f"({'+'.join(parts)})" if len(parts) > 1 else parts[0] if parts else "start_time:>='now-24h'"
```

---

## Testing Filters

```bash
# Test syntax
cd skills/discovery
../../scripts/python.sh scripts/probe_span_filters.py

# Check field structure
../../scripts/python.sh scripts/diagnose_spans.py --sample 5
```

---

## Reference

**Official FQL:** https://developer.crowdstrike.com/api-reference/falcon-query-language/  
**Date Math:** https://github.com/timberio/go-datemath

See also: `references/span-constraints.md`, `docs/TROUBLESHOOTING.md`
