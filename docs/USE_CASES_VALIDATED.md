# Security Use Cases - Validated Examples

Realistic security operations scenarios using Charlotte AI AgentWorks agents via Claude Code.

---

## 1. Threat Hunting Agent

### Scenario
Create an agent that helps SOC analysts investigate suspicious activity across hosts.

### User Request
```
Create a Charlotte AI AgentWorks agent called "Threat Hunter" that can search hosts 
and analyze detections. Use Claude Sonnet for reasoning.
```

### What Happens
1. Claude queries available models → finds `bedrock.claude-4-6-sonnet`
2. Claude queries available tools → finds:
   - `mcp/gce/falcon_platform:search_hosts`
   - `mcp/gce/falcon_platform:get_host_details`
   - `mcp/gce/falcon_platform:query_detections`
3. Claude creates agent with appropriate system prompt:
   ```
   You are a threat hunting assistant. Analyze host activity and 
   detections to identify potential security incidents. Always verify 
   findings with multiple data points before escalating.
   ```
4. Returns: `agent_id: a1b2c3d4-...`, `version_id: v1-...`

### Validation
- ✅ Agent created successfully
- ✅ Tools attached and accessible
- ✅ Model configured correctly

---

## 2. Investigate Suspicious Process

### Scenario
Use the Threat Hunter agent to investigate a suspicious process on a specific host.

### User Request
```
Invoke the Threat Hunter agent to investigate suspicious PowerShell activity 
on host DESKTOP-ABC123
```

### What Happens
1. Claude resolves agent name → `agent_id`
2. Claude invokes with prompt:
   ```
   Investigate PowerShell activity on DESKTOP-ABC123. Check for:
   - Unusual command line arguments (encoded, obfuscated)
   - Parent process legitimacy
   - Network connections
   - Recent detections
   Summarize findings and threat level.
   ```
3. Claude polls for completion
4. Returns invocation results with:
   - Host details (OS, last seen, agent version)
   - Process tree showing PowerShell spawn
   - Command line analysis
   - Network connection check
   - Related detection events
   - Risk assessment

### Expected Output
```
Found suspicious PowerShell activity on DESKTOP-ABC123:

Process: powershell.exe
Parent: WINWORD.EXE (Microsoft Word)
Command: powershell -enc <base64_blob>
Network: Outbound connection to 185.220.xxx.xxx (Tor exit node)

Related Detections:
- "Suspicious PowerShell Execution" (Medium severity)
- "Outbound Connection to Known Malicious IP" (High severity)

Threat Level: HIGH
Recommendation: Isolate host and escalate to IR team
```

### Validation
- ✅ Agent executed search correctly
- ✅ Tool calls completed successfully
- ✅ Reasoning applied security context
- ✅ Actionable recommendations provided

---

## 3. Incident Response Playbook Agent

### Scenario
Create an agent with an attached knowledge base containing IR playbooks.

### User Request
```
Create a knowledge base from incident_response_playbooks.pdf and attach it 
to a new agent called "IR Assistant"
```

### What Happens
1. Claude creates knowledge base:
   ```
   Name: "IR Playbooks"
   Description: "Standard incident response procedures"
   ```
2. Claude uploads PDF file → KB file created
3. Claude creates agent with:
   - Model: `bedrock.claude-4-6-sonnet`
   - Tools: Falcon platform search/query tools
   - Knowledge base: IR Playbooks (attached)
   - System prompt:
     ```
     You are an incident response assistant. Use the IR playbooks 
     knowledge base to guide responders through proper procedures. 
     Always cite the relevant playbook section.
     ```

### Validation
- ✅ Knowledge base created
- ✅ PDF uploaded successfully
- ✅ Agent created with KB attached
- ✅ Agent can query KB during invocations

---

## 4. Analyze Agent Performance

### Scenario
Analyze the Threat Hunter agent's performance over the last 30 days to optimize it.

### User Request
```
Analyze the Threat Hunter agent for the last 30 days and suggest improvements
```

### What Happens
1. Claude queries spans by `agent_id` and time window
2. Claude analyzes:
   - **Invocation patterns**: 247 invocations, avg 3.2/day
   - **Tool usage**:
     - `search_hosts`: 247 calls (100% usage)
     - `get_host_details`: 189 calls (76% usage)
     - `query_detections`: 142 calls (57% usage)
   - **Error rate**: 12 failed invocations (4.9%)
   - **Performance**: avg 8.3s response time
   - **Version changes**: 2 updates during period

3. Claude identifies issues:
   - Tool call failures on `query_detections` (API timeout)
   - Slow queries when searching >1000 hosts
   - Missing tool for process tree analysis

### Recommendations
```
Optimization Recommendations for Threat Hunter:

1. Tool Issues:
   - query_detections failing with timeout (12 errors)
   - Add retry logic or pagination for large result sets
   
2. Missing Capability:
   - Agent frequently requests process tree info
   - Add falcon_platform:get_process_tree tool
   
3. Performance:
   - Searches >1000 hosts take 15s+ (50 cases)
   - Update prompt to narrow scope before searching
   
4. Prompt Enhancement:
   - Add guidance on when to escalate vs. investigate further
   - Include examples of high-confidence indicators
```

### Validation
- ✅ Span data retrieved correctly
- ✅ Tool usage patterns identified
- ✅ Errors correlated with specific tools
- ✅ Actionable recommendations provided

---

## 5. Batch Host Investigation

### Scenario
Investigate multiple hosts suspected of being compromised in a ransomware campaign.

### User Request
```
Invoke Threat Hunter to check these hosts for ransomware indicators:
DESKTOP-ABC123, LAPTOP-XYZ789, SERVER-WEB01
```

### What Happens
1. Claude invokes agent with structured prompt:
   ```
   Investigate the following hosts for ransomware indicators:
   - DESKTOP-ABC123
   - LAPTOP-XYZ789  
   - SERVER-WEB01
   
   For each host, check:
   - File encryption activity (rapid file modifications)
   - Suspicious processes (encryption tools)
   - Network connections (C2 callbacks)
   - Disabled security tools
   - Ransom notes present
   
   Prioritize by threat level.
   ```

2. Agent executes systematic investigation
3. Returns structured findings per host

### Expected Output
```
Ransomware Investigation Results:

HOST: DESKTOP-ABC123 [CRITICAL]
  ✓ Encryption Activity: 8,432 files modified in 5 minutes
  ✓ Suspicious Process: encrypt.exe (unknown publisher)
  ✓ Network: Outbound to 45.xxx.xxx.xxx (known ransomware C2)
  ✓ Security: Defender disabled at 14:23 UTC
  ✓ Ransom Note: README_DECRYPT.txt found in C:\Users\
  → IMMEDIATE CONTAINMENT REQUIRED

HOST: LAPTOP-XYZ789 [HIGH]
  ✓ Encryption Activity: 1,200 files modified (Documents folder)
  ✓ Suspicious Process: None currently running
  ✓ Network: No active C2 connection
  ✗ Security: Defender running normally
  ✓ Ransom Note: Not found
  → Likely patient zero or early stage infection

HOST: SERVER-WEB01 [CLEAN]
  ✗ Encryption Activity: Normal file modifications
  ✗ Suspicious Process: None detected
  ✗ Network: Standard web server traffic
  ✓ Security: All agents running
  ✗ Ransom Note: Not found
  → No ransomware indicators found

Recommendation: 
1. IMMEDIATE: Isolate DESKTOP-ABC123 (network containment)
2. HIGH: Isolate LAPTOP-XYZ789 (investigate patient zero)
3. Monitor SERVER-WEB01 for 24h (may be targeted next)
```

### Validation
- ✅ Agent handled multiple hosts systematically
- ✅ Prioritization logic applied correctly
- ✅ Clear containment recommendations
- ✅ Structured output for easy parsing

---

## 6. Debug Agent Tool Failure

### Scenario
An agent's tool call is failing - inspect the trace to diagnose the issue.

### User Request
```
The IR Assistant is failing when querying detections. 
Inspect trace for invocation inv-abc123-def456
```

### What Happens
1. Claude fetches trace by `invocation_id`
2. Claude displays waterfall view:
   ```
   Trace Waterfall:
   ├─ aw_agent (root span) [8.2s total]
   │  ├─ llm_call (analyze request) [1.1s] ✓
   │  ├─ tool_call: search_hosts [0.8s] ✓
   │  │  └─ api_request: GET /hosts/v2 [0.6s] ✓
   │  ├─ tool_call: query_detections [5.2s] ✗ FAILED
   │  │  └─ api_request: GET /detections/v2 [5.0s] ✗ HTTP 504 Gateway Timeout
   │  └─ llm_call (handle error) [1.1s] ✓
   ```

3. Claude identifies issue:
   - `query_detections` tool call timeout after 5s
   - HTTP 504 from Falcon API
   - Likely caused by overly broad query (no time filter)

4. Claude inspects tool parameters:
   ```json
   {
     "tool": "query_detections",
     "parameters": {
       "filter": "status:'new'",
       "limit": 10000
     }
   }
   ```

### Diagnosis
```
Root Cause: query_detections timeout

Issue: Agent querying ALL new detections with no time bounds
  - Requested limit: 10,000
  - No start_time filter
  - API timeout after 5s (too much data)

Fix: Update agent prompt to always include time filters
Recommended prompt addition:
  "When querying detections, always limit to the last 24 hours 
   unless a specific time range is requested."

Alternative: Add time filter to tool definition default parameters
```

### Validation
- ✅ Trace retrieved successfully
- ✅ Failing tool identified
- ✅ Root cause diagnosed (missing time filter)
- ✅ Actionable fix provided

---

## 7. Version Comparison

### Scenario
After updating an agent, verify the improvements are working as expected.

### User Request
```
Compare Threat Hunter performance before and after yesterday's update
```

### What Happens
1. Claude queries spans for agent across 7 days
2. Claude detects version change on 2026-08-23
3. Claude analyzes metrics by version:

### Comparison Output
```
Threat Hunter Version Comparison:

Version v1 (Aug 17-22):
  Invocations: 82
  Avg Duration: 12.4s
  Error Rate: 8.5% (7 failures)
  Tool Failures: query_detections timeout (7 cases)
  
Version v2 (Aug 23-24):
  Invocations: 43
  Avg Duration: 7.1s (-43% improvement)
  Error Rate: 2.3% (1 failure)
  Tool Failures: 1 unrelated network error

Improvements Confirmed:
✓ Response time improved significantly
✓ Error rate reduced by 73%
✓ query_detections timeout issue resolved
✓ No new regressions detected

Version v2 changes (from span metadata):
  - Added time filter to detection queries (default: 24h)
  - Increased API timeout from 5s to 10s
  - Added retry logic (max 2 retries)
```

### Validation
- ✅ Version split detected automatically
- ✅ Metrics compared accurately
- ✅ Improvements quantified
- ✅ Change details extracted from spans

---

## 8. Create Security Triage Agent

### Scenario
Create a specialized agent for first-level detection triage.

### User Request
```
Create a detection triage agent that categorizes alerts as:
true positive, false positive, or needs investigation
```

### What Happens
1. Claude creates agent with focused capabilities:
   - Model: `bedrock.claude-4-6-sonnet`
   - Tools: `query_detections`, `get_host_details`, `get_detection_details`
   - System prompt:
     ```
     You are a detection triage specialist. Categorize alerts using:
     
     TRUE POSITIVE: Clear malicious activity with high confidence
     - Known IOCs present
     - Behavior matches attack pattern
     - No legitimate business justification
     
     FALSE POSITIVE: Benign activity misclassified
     - Known software/process
     - Expected behavior for role/department
     - Historical pattern of false positives
     
     NEEDS INVESTIGATION: Insufficient data or ambiguous
     - Novel behavior requiring deeper analysis
     - Partial indicators without full context
     - Edge cases not covered by playbook
     
     Always provide reasoning and confidence level.
     ```

2. Returns agent ready for triage workflow integration

### Example Invocation
```
Triage detection DET-12345: "Suspicious Registry Modification"
```

### Expected Output
```
Detection Triage: DET-12345

Detection: Suspicious Registry Modification
Host: DESKTOP-USER42
User: john.smith@company.com
Timestamp: 2026-08-24 09:23:14 UTC

Analysis:
Registry Key: HKLM\Software\Microsoft\Windows\CurrentVersion\Run
Value: "SecurityUpdate" = C:\ProgramData\update.exe
Process: WINWORD.EXE (Microsoft Word)

Verdict: TRUE POSITIVE (High Confidence)

Reasoning:
✓ Word spawning registry modification (unusual)
✓ Persistence mechanism (Run key)
✓ Executable in ProgramData (suspicious location)
✓ Naming mimics legitimate update (evasion tactic)
✗ Not in approved software list
✗ No IT change ticket found

Confidence: 95%
Recommended Action: Escalate to IR team
Priority: High
```

### Validation
- ✅ Agent created with triage-specific logic
- ✅ Categorization framework embedded in prompt
- ✅ Confidence scoring included
- ✅ Actionable recommendations

---

## Summary

These use cases demonstrate:

✅ **Agent Lifecycle** - Create, configure, publish security-focused agents  
✅ **Invocation** - Run investigations with structured prompts  
✅ **Knowledge Bases** - Attach IR playbooks and security documentation  
✅ **Analysis** - Optimize agent performance with span data  
✅ **Debugging** - Diagnose tool failures with trace inspection  
✅ **Comparison** - Verify improvements after updates  

All examples use realistic CrowdStrike security operations scenarios relevant to SOC analysts, threat hunters, and incident responders.
