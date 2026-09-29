# Workflow Integration Guide

How Charlotte AI AgentWorks skills connect for end-to-end agent development and optimization.

## Skills Overview

| Skill | Purpose | Key Operations |
|-------|---------|----------------|
| **discovery** | Find resources | Query models, tools, templates, spans |
| **agents** | Agent lifecycle | Create, update, publish, analyze |
| **invocation** | Run & inspect | Invoke agents, trace execution, debug |
| **knowledge-bases** | Manage KBs | Create, upload, query KBs |

---

## Common Workflows

### 1. Create and Deploy an Agent

**Flow:** discovery → agents → invocation → agents

1. **Find prerequisites** (discovery):
   ```bash
   # Find models
   cd skills/discovery
   ../../scripts/python.sh scripts/models_search.py --limit 50
   
   # Find tools
   ../../scripts/python.sh scripts/tools_search.py --filter 'name:"falcon_platform"'
   ```

2. **Create agent** (agents):
   ```bash
   cd skills/agents
   ../../scripts/python.sh scripts/agent_upsert.py \
     --name "Security Analyst" \
     --model "bedrock.claude-4-6-sonnet" \
     --tools "mcp/gce/falcon_platform:search_hosts"
   # Capture: agent_id, version_id
   ```

3. **Test unpublished** (invocation):
   ```bash
   cd ../invocation
   ../../scripts/python.sh scripts/invoke_version.py \
     --agent-id <agent-id> --version-id <version-id> \
     --message "Test query"
   
   ../../scripts/python.sh scripts/get_messages.py --id <invocation-id>
   ```

4. **Publish** (agents):
   ```bash
   cd ../agents
   ../../scripts/python.sh scripts/agent_publish.py \
     --id <agent-id> --version-id <version-id>
   ```

### 2. Test and Debug

**Flow:** invocation → invocation

1. **Invoke** → 2. **Poll for completion** → 3. **Inspect trace**

```bash
cd skills/invocation
../../scripts/python.sh scripts/invoke_agent.py --id <agent-id> --message "Test"
../../scripts/python.sh scripts/get_messages.py --id <invocation-id>
../../scripts/python.sh scripts/inspect_invocation.py --invocation-id <invocation-id>
```

### 3. Optimize an Agent

**Flow:** agents → invocation → agents

1. **Analyze execution patterns** (agents):
   ```bash
   cd skills/agents
   ../../scripts/python.sh scripts/analyze_agent.py \
     --agent-id <agent-id> --days 30 --verbose
   # Review: unused tools, errors, sequences, recommendations
   ```

2. **Deep-dive problem traces** (invocation):
   ```bash
   cd skills/invocation
   ../../scripts/python.sh scripts/inspect_invocation.py \
     --invocation-id <problem-invocation-id>
   ```

3. **Update agent** (agents):
   ```bash
   cd skills/agents
   # Read current config first
   ../../scripts/python.sh scripts/agent_get.py --ids <agent-id>
   
   # Update with improvements
   ../../scripts/python.sh scripts/agent_upsert.py \
     --id <agent-id> \
     --system-prompt "Updated..." \
     --tools <adjusted-list>
   ```

4. **Test & publish** → Repeat from step 1 to verify

### 4. Add Knowledge Base

**Flow:** knowledge-bases → agents

1. **Create and populate KB**:
   ```bash
   cd skills/knowledge-bases
   ../../scripts/python.sh scripts/kb_upsert.py --name "Playbooks"
   ../../scripts/python.sh scripts/kb_file_upload.py --kb-id <kb-id> --file playbooks.pdf
   ```

2. **Attach to agent** (read current config first):
   ```bash
   cd skills/agents
   ../../scripts/python.sh scripts/agent_get.py --ids <agent-id>
   ../../scripts/python.sh scripts/agent_upsert.py \
     --id <agent-id> \
     --knowledge-base-ids <kb-id>
   ```

3. **Test & publish**

---

## Data Flow

### Agent Creation
```
models_search → tools_search → agent_upsert → agent_publish
   ↓               ↓                ↓              ↓
model_id        tool_ids       agent_id      published
```

### Invocation
```
invoke_agent → get_messages → inspect_invocation
    ↓              ↓               ↓
invocation_id  verify done    trace details
```

### Analysis
```
analyze_agent → queries spans → extracts patterns → recommendations
    ↓                                                      ↓
sample invocation_ids ────────> inspect_invocation (deep-dive)
```

---

## Key IDs and Links

| ID | Source | Links To |
|----|--------|----------|
| `model_id` | models_search | agent_upsert (which LLM) |
| `tool_id` | tools_search | agent_upsert (actions) |
| `kb_id` | kb_upsert | agent_upsert (knowledge) |
| `agent_id` | agent_upsert | All agent operations |
| `version_id` | agent_upsert | agent_publish (specific version) |
| `invocation_id` | invoke_agent | Trace operations |
| `trace_id` | From spans | Groups all spans |

---

## Integration Patterns

**Iterative Improvement:**
1. Analyze → 2. Identify issues → 3. Update → 4. Test → 5. Verify → Repeat

**Comprehensive Debugging:**
1. List invocations → 2. Identify problem → 3. Inspect trace → 4. Analyze patterns

**New Agent Development:**
1. Research tools → 2. Create → 3. Test unpublished → 4. Iterate → 5. Publish → 6. Analyze production

---

## Tips

1. **Always analyze before optimizing** - don't guess
2. **Use `--verbose`** when analyzing for detailed patterns
3. **Capture all IDs** - you'll need them for next steps
4. **Filter by span_type** when listing traces (100x faster)
5. **Use `--json`** output when piping between scripts
6. **Read agent config** before updating to avoid conflicts
7. **Verify with small windows** (`--days 1`) after changes
8. **Broaden windows** (`--days 30`) for pattern analysis
