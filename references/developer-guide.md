# Developer Guide - Charlotte AI AgentWorks Skills

## Critical Information for Developers

### 1. Falcon Query Language (FQL) is REQUIRED

**IMPORTANT:** All filter-based queries use **Falcon Query Language (FQL)** syntax, NOT standard SQL-like syntax.

**Official Docs:** https://developer.crowdstrike.com/api-reference/falcon-query-language/

**Complete Reference:** See `references/fql-syntax.md`

### Quick FQL Rules

```python
# ✅ CORRECT FQL
filter = "start_time:>='now-24h'"                           # Colon before operator, quoted value
filter = "(field1:'value'+field2:'value')"                  # + for AND
filter = "(status:'error',status:'warning')"                # , for OR
filter = "span_type:['aw_agent','aw_eval_run_started']"    # Arrays with []

# ❌ WRONG - Not FQL
filter = "start_time>=now-24h"                              # Missing colon, missing quotes
filter = "field1:'value' AND field2:'value'"                # Wrong operator
filter = "status IN ('error','warning')"                    # SQL syntax
```

### 2. Span Query Requirements

**Time bounds are MANDATORY** for span queries:
- Maximum age: 90 days
- API automatically adds 90-day floor
- Always include explicit time window for clarity

```python
# Use the helper
from discovery_helpers import _ensure_span_time_filter

filter_expr = _ensure_span_time_filter(user_filter)
# Ensures FQL-compliant time bounds
```

**See:** `references/span-constraints.md` for complete rules

### 3. Adding New Filter-Based Scripts

When creating new scripts that query APIs with filters:

#### Step 1: Import the helper
```python
from discovery_helpers import _ensure_span_time_filter  # For span queries
```

#### Step 2: Use FQL syntax builders
```python
def build_filter(agent_id: str, days: int = 7) -> str:
    """Build FQL filter for agent spans.
    
    Filters to agent-level spans only for efficiency.
    """
    # Filter to agent-level spans: aw_agent, aw_eval_run_started
    # These contain invocation metadata; child spans (tool calls, LLM) don't
    return (
        f"(attributes.aw_agent.id:'{agent_id}'"
        f"+start_time:>='now-{days}d')"
        f"+span_type:['aw_agent','aw_eval_run_started']"
    )
```

#### Step 3: Validate filter format
- Use `:>=`, `:<`, `:>`, `:<=` for operators (colon prefix)
- Always quote values with single quotes: `'value'`
- Use `+` for AND, `,` for OR
- Wrap complex conditions in parentheses

#### Step 4: Test with diagnostic tool
```bash
cd skills/discovery
../../scripts/python.sh scripts/probe_span_filters.py
```

### 4. Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| `field>=value` | `field:>='value'` |
| `field:"value"` | `field:'value'` |
| `a AND b` | `a+b` |
| `a OR b` | `a,b` |
| `field IN (a,b)` | `field:['a','b']` |
| Unquoted dates: `now-24h` | Quoted: `'now-24h'` |

### 5. Date Math Format

```python
'now'          # Current time
'now-1h'       # 1 hour ago
'now-24h'      # 24 hours ago
'now-7d'       # 7 days ago
'now-90d'      # 90 days ago (max for spans)
'now-7d/d'     # 7 days ago, rounded to start of day
```

### 6. Nested Attributes

Access with dot notation:
```python
"attributes.aw_agent.id:'uuid'"           # Agent ID
"attributes.aw_agent.invocation_id:'uuid'"  # Invocation ID
"attributes.cost.raw_credit_cents:>100"
```

### 7. Script Template

When creating new discovery/query scripts:

```python
#!/usr/bin/env python3
"""
script_name.py - Brief description.

Uses FQL (Falcon Query Language) for filters.
See references/fql-syntax.md for syntax details.
"""

import argparse
import sys
import os

# A skill's scripts/ folder is three levels below the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "common", "scripts"))
import _bootstrap

_bootstrap.ensure_deps(__file__)
from auth import call_native, get_spans_client

def build_filter(user_input: str, time_window: str = "now-24h") -> str:
    """Build FQL-compliant filter.
    
    Args:
        user_input: User's filter expression
        time_window: Time window (default: 'now-24h')
    
    Returns:
        FQL-compliant filter string
    """
    # For span queries, ensure time bounds
    if not user_input:
        return f"start_time:>='{time_window}'"
    
    # Check if user provided time bounds
    if "start_time" in user_input.lower() or "end_time" in user_input.lower():
        return user_input
    
    # Add default time bounds using FQL syntax
    return f"({user_input})+start_time:>='{time_window}'"

def main():
    parser = argparse.ArgumentParser(
        description="Query description",
        epilog="Uses FQL syntax. Examples: field:'value', field:>='now-24h', (a+b),c"
    )
    parser.add_argument("--filter", default="", 
                       help="FQL filter (see references/fql-syntax.md)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    # Build FQL filter
    filter_expr = build_filter(args.filter)
    
    # Query API
    params = {"filter": filter_expr, "limit": "100"}
    response = call_native(get_spans_client().queries_spans_v1, parameters=params)
    
    # Process results...

if __name__ == "__main__":
    main()
```

### 8. Testing Your Filters

#### Quick Test
```python
from auth import call_native, get_spans_client

# Test your filter
filter_expr = "(your+filter+here)"
try:
    response = call_native(get_spans_client().queries_spans_v1,
                           parameters={"filter": filter_expr, "limit": "5"})
    print(f"✅ Filter works: {len(response.get('resources', []))} results")
except Exception as e:
    print(f"❌ Filter failed: {e}")
```

#### Comprehensive Test
```bash
cd skills/discovery
../../scripts/python.sh scripts/probe_span_filters.py
```

### 9. Documentation Standards

When documenting filters in help text or examples:

```python
# ✅ GOOD - Shows FQL syntax explicitly
parser.add_argument("--filter", 
    help="FQL filter. Examples: status:'error', (field1:'a'+field2:'b')")

# ✅ GOOD - Links to reference
"""
Filters use FQL syntax. See references/fql-syntax.md

Examples:
  --filter "start_time:>='now-24h'"
  --filter "(agent_id:'uuid'+status:'error')"
"""

# ❌ BAD - Shows wrong syntax
parser.add_argument("--filter", 
    help="Filter. Examples: status='error', field1='a' AND field2='b'")
```

### 10. Key Files

| File | Purpose |
|------|---------|
| `references/fql-syntax.md` | Complete FQL syntax guide (READ THIS FIRST) |
| `references/span-constraints.md` | Span query time rules |
| `common/scripts/discovery_helpers.py` | Reusable filter helpers |
| `skills/discovery/scripts/probe_span_filters.py` | Filter syntax tester |

### 11. Pull Request Checklist

Before submitting code that adds/modifies filters:

- [ ] Uses correct FQL syntax (`:>=`, `'quotes'`, `+` for AND, `,` for OR)
- [ ] Span queries include time bounds
- [ ] Tested with `probe_span_filters.py` or manual API call
- [ ] Help text shows correct FQL syntax examples
- [ ] Complex filters wrapped in parentheses for clarity
- [ ] Documentation updated if adding new filter patterns

### 12. Common Debug Steps

If filters fail:

1. **Check FQL syntax:**
   - Operators: `:>=`, `:<`, not `>=`, `<`
   - Values quoted: `'value'`, not `value` or `"value"`
   - Logic: `+` and `,`, not `AND` and `OR`

2. **Test in isolation:**
   ```bash
   ../../scripts/python.sh scripts/probe_span_filters.py
   ```

3. **Check time bounds (for spans):**
   - Maximum: 90 days (`'now-90d'`)
   - start_time must be before end_time

4. **Verify field names:**
   - Use `diagnose_spans.py` to see actual span structure
   - Nested: `attributes.field.subfield`

### 13. Resources

- **FQL Official Docs:** https://developer.crowdstrike.com/api-reference/falcon-query-language/
- **Date Math Library:** https://github.com/timberio/go-datemath

## Quick Start for New Contributors

1. Read `references/fql-syntax.md` (5 minutes)
2. Look at existing scripts as examples (e.g., `list_invocations.py`)
3. Use the template above for new scripts
4. Test filters with `probe_span_filters.py`
5. Reference this guide when in doubt

**Remember:** FQL syntax is non-negotiable. All filters MUST use it.
