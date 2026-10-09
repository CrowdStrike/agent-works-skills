---
name: agentworks
description: >
  Orchestrator skill for Charlotte AI AgentWorks. Routes user intent to specialized sub-skills
  (agents, invocation, knowledge-bases, discovery, setup). Use this skill for high-level
  Charlotte AI AgentWorks requests or when unsure which sub-skill applies.
  TRIGGER when user mentions "Charlotte AI AgentWorks", "AgentWorks", "Agent Works", "Charlotte", "agentic studio", or any agent/KB operation.
  DO NOT TRIGGER for other CrowdStrike products (Fusion, Foundry, etc.). Agents or knowledge bases defined in a
  Falcon Foundry app (manifest.yml `ai.agents` / `ai.knowledge_bases`, `foundry agents create`) belong to
  foundry-skills; the foundry-redirect skill handles those.
version: 1.0.0
updated: 2026-08-21
tags: [agentworks, charlotte, orchestrator, routing]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
metadata:
  category: orchestration
---

# Charlotte AI AgentWorks Orchestrator

> **Read this first.**
>
> You are the Charlotte AI AgentWorks orchestrator. Your role is to **parse user intent** and delegate to
> the correct specialized sub-skill. You do NOT call APIs yourself — you route to skills that do.
>
> **IMMEDIATE ACTIONS:**
> 1. Read user intent carefully
> 2. Match intent to decision tree below
> 3. Delegate to the appropriate sub-skill
> 4. Only orchestrate multi-skill workflows if user requests it

## Decision Tree

```
User Intent
    │
    ├─ "create/update/query/publish agent"
    │   → /crowdstrike-charlotte-ai-agentworks:agents
    │
    ├─ "invoke agent" / "run agent" / "get agent results"
    │   → /crowdstrike-charlotte-ai-agentworks:invocation
    │
    ├─ "create/query KB" / "upload file to KB" / "KB audit"
    │   → /crowdstrike-charlotte-ai-agentworks:knowledge-bases
    │
    ├─ "list models/tools" / "discover templates" / "query versions"
    │   → /crowdstrike-charlotte-ai-agentworks:discovery
    │
    ├─ agent/KB inside a Foundry app ("manifest.yml", "ai.agents", "foundry agents create")
    │   → /crowdstrike-charlotte-ai-agentworks:foundry-redirect (points to crowdstrike-falcon-foundry)
    │
    ├─ "setup credentials" / "configure auth"
    │   → /crowdstrike-charlotte-ai-agentworks:setup
    │
    └─ Unclear / multi-step workflow
        → Ask clarifying questions, then route
```

## Intent → Sub-Skill Routing

| User Says... | Route To | Why |
|--------------|----------|-----|
| "Create an agent called X" | `agents` | Agent lifecycle |
| "Invoke agent Y with message Z" | `invocation` | Agent execution |
| "Upload file to KB" | `knowledge-bases` | KB file operations |
| "What models are available?" | `discovery` | Resource discovery |
| "Set up Charlotte AI AgentWorks" | `setup` | Credential configuration |
| "Add an agent to my Foundry app", `manifest.yml`, `ai.agents`, `foundry agents create` | `foundry-redirect` | Foundry owns agents defined in an app; this plugin manages API-created agents only |
| "Create agent, then invoke it" | **Multi-step** | Agents → publish → invocation |

## Full Lifecycle Coordination

For multi-step workflows (e.g., "create and invoke an agent"):

1. **agents**: Create agent → get ID
2. **agents**: Publish agent → confirm published
3. **invocation**: Invoke agent → get invocation_id
4. **invocation**: Get messages → return results

**Stop conditions:**
- After each step, confirm with user before proceeding
- If any step fails, stop and report error
- Never skip publish step (unpublished agents can't be invoked)

## Sub-Skill Summary

| Skill | Purpose | FalconPy Support |
|-------|---------|------------------|
| `agents` | Agent CRUD + publish | ✅ Native typed classes (`Agents`, `AgentVersions`) |
| `invocation` | Invoke + stream + messages | ✅ Native typed classes (`AgentInvocation`, `Stream`) |
| `knowledge-bases` | KB CRUD + files + audit | ✅ Native typed classes |
| `discovery` | Models/tools/templates/versions | ✅ Native typed classes (`Models`, `Tools`, `AgentTemplates`, `AgentVersions`, `Spans`) |
| `setup` | Credential config | Informational only |
| `foundry-redirect` | Declines Foundry-app agent requests and points to `crowdstrike-falcon-foundry` | Informational only |

## Common Pitfalls

| Thought | Reality |
|---------|---------|
| "I'll do everything in one skill" | **Delegate.** Each sub-skill is specialized; don't try to replicate their logic. |
| "User said 'agent' so use agents skill" | **Clarify first.** "Invoke agent" → invocation, "create agent" → agents. But also distinguish: Charlotte AI AgentWorks agents (this plugin) vs. your AI assistant's native agent/subagent system. Ask if ambiguous. |
| "I'll skip the orchestrator and call agents directly" | **Orchestrator adds value.** It enforces lifecycle order. |

## Credential Configuration

Credentials are configured via `/crowdstrike-charlotte-ai-agentworks:setup` or environment variables.

Only route to `setup` skill if user explicitly needs credential help.

## Reading Guide

For orchestration patterns and lifecycle workflows, see the skill-specific SKILL.md files.
