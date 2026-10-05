# Span Time Constraints

**⚠️ CRITICAL:** All span queries MUST include time bounds (90-day maximum)

See `references/fql-syntax.md` for complete FQL syntax.

---

## Critical Rules

### 1. Maximum Age: 90 Days (Hard Limit)

**Rule:** Spans older than 90 days cannot be queried.

```python
# ❌ FAILS - Too old
filter = "start_time:>='2025-01-01T00:00:00Z'"

# ✅ WORKS - Within 90 days
filter = "start_time:>='now-89d'"
```

### 2. Automatic 90-Day Floor

**Rule:** API automatically adds 90-day floor if missing.

```python
# You send:
filter = "status:'error'"

# API transforms to:
filter = "(status:'error')+(start_time:>='<90-days-ago>')"
```

### 3. Time Operators

**Allowed operators:**
- `start_time:>=<value>` - Greater than or equal (recommended)
- `start_time:><value>` - Greater than
- `end_time:<=<value>` - Less than or equal
- `end_time:<<value>` - Less than

**Only ONE lower bound and ONE upper bound allowed per query.**

### 4. Time Value Formats

**RFC3339:**
```python
"start_time:>='2026-08-21T10:30:00Z'"
```

**Date Math:**
```python
"start_time:>='now-24h'"    # 24 hours ago
"start_time:>='now-7d'"     # 7 days ago
"start_time:>='now-90d'"    # Maximum
"start_time:>='now-7d/d'"   # Rounded to start of day
```

### 5. Time Range Validation

**Rule:** `end_time` must be AFTER `start_time`

```python
# ❌ FAILS
filter = "start_time:>='2026-08-21T10:00:00Z'+end_time:<='2026-08-20T10:00:00Z'"

# ✅ WORKS
filter = "start_time:>='2026-08-20T10:00:00Z'+end_time:<='2026-08-21T10:00:00Z'"
```

---

## Common Patterns

### Default (Let API Apply 90-Day Floor)
```python
filter = "attributes.aw_agent.id:'<uuid>'"
```

### Explicit Time Window (Recommended)
```python
# Last 24 hours
filter = "attributes.aw_agent.id:'<uuid>'+start_time:>='now-24h'"

# Last 7 days
filter = "trace_id:'<uuid>'+start_time:>='now-7d'"

# Maximum history
filter = "attributes.aw_agent.id:'<uuid>'+start_time:>='now-90d'"
```

### Specific Date Range
```python
filter = "start_time:>='2026-08-15T00:00:00Z'+end_time:<='2026-08-21T23:59:59Z'"
```

---

## Python Implementation

### Helper Function

```python
def ensure_time_filter(filter_expr: str, default_window: str = "24h") -> str:
    """Ensure span query has time bounds."""
    if not filter_expr:
        return f"start_time:>='now-{default_window}'"
    
    if "start_time" not in filter_expr.lower():
        return f"{filter_expr}+start_time:>='now-{default_window}'"
    
    return filter_expr
```

### Error Handling

```python
try:
    response = call_native(get_spans_client().queries_spans_v1, parameters={"filter": filter_expr})
except Exception as e:
    if "time must be within the last 90 days" in str(e):
        print("ERROR: Query exceeds 90-day limit", file=sys.stderr)
    elif "time value must be RFC3339 or a date math expression" in str(e):
        print("ERROR: Invalid time format", file=sys.stderr)
    raise
```

### Script Arguments

```python
parser.add_argument("--days", type=int, default=1,
                   help="Days to query (default: 1, max: 90)")

if args.days > 90:
    print("WARNING: Capping at 90 days (API limit)", file=sys.stderr)
    args.days = 90
```

---

## Quick Reference

| Constraint | Value |
|------------|-------|
| Max age | 90 days |
| Formats | RFC3339 or date math (`now-24h`) |
| Rule | end_time > start_time |
| Bounds | One start_time, one end_time max |
| Default | API adds 90-day floor if missing |

**Recommended defaults:**
- General: `start_time:>='now-24h'`
- Analysis: `start_time:>='now-7d'`
- Maximum: `start_time:>='now-90d'`

**Always valid:**
```python
"start_time:>='now-90d'"  # Maximum
"start_time:>='now-24h'"  # Default
"start_time:>='now-1h'"   # Recent
```

**Never valid:**
```python
"start_time:>='now-91d'"  # Too old
""  # Empty (be explicit)
```

---

## Diagnostic Tools

**Test filter syntax:**
```bash
cd skills/discovery
../../scripts/python.sh scripts/probe_span_filters.py
```

**Check field structure:**
```bash
../../scripts/python.sh scripts/diagnose_spans.py --sample 5
```

See `docs/TROUBLESHOOTING.md` for more help.
