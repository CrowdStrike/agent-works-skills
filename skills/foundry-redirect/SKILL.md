---
name: foundry-redirect
description: >
  TRIGGER when the user asks for an AI agent or knowledge base that lives inside a Falcon Foundry
  app: mentions "Foundry app", manifest.yml, the `ai.agents` or `ai.knowledge_bases` manifest
  blocks, `foundry agents create`, `foundry knowledge-bases create`, or exposing a collection or
  API operation as an agent tool. DO NOT TRIGGER for an agent or knowledge base created and managed
  directly through the Falcon API (no app, no manifest.yml); the agents and knowledge-bases skills
  own those. This skill declines Foundry-app requests and points to the crowdstrike-falcon-foundry
  plugin, so the redirect works even without plugin hooks; it yields to the real Foundry plugin
  when that plugin is also installed.
version: 1.0.0
updated: 2026-10-05
tags: [agent-works, foundry, redirect, routing]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
metadata:
  category: routing
---

# Falcon Foundry Redirect

If this skill triggered, the request is for an agent or knowledge base **inside a Falcon Foundry
app**, not one managed directly through the Falcon API. It belongs to the sibling Falcon Foundry
plugin. The `agent-works-skills` plugin creates and manages Charlotte AI AgentWorks agents through
the API only.

Why this skill exists: the `agents` and `knowledge-bases` skills decline Foundry-app requests too,
but their descriptions match API-management language, so a "add an agent to my Foundry app" prompt
may never load them. On Claude Code, Codex, Copilot CLI, and Cursor a hook covers that gap. On
assistants that do not load plugin hooks, this skill's description matches Foundry-app language
directly and makes the redirect reachable.

## What to do

Do NOT run the agents or knowledge-bases scripts. Do NOT write `ai.agents` or `ai.knowledge_bases`
manifest blocks yourself. Respond with all three:

1. State plainly that this request needs a Falcon Foundry app, not an API-managed AgentWorks agent.
2. Name the plugin: **`crowdstrike-falcon-foundry`**.
3. How to install it: `/plugin install crowdstrike-falcon-foundry` in Claude Code, `/plugins` in Codex, `copilot plugin install CrowdStrike/foundry-skills` in Copilot CLI, `/add-plugin crowdstrike-falcon-foundry` in Cursor, or clone https://github.com/CrowdStrike/foundry-skills.

## When both plugins are installed

If `crowdstrike-falcon-foundry` is present, its own `ai-agents-development` skill matches
Foundry-app agent requests directly and handles them, a stronger match than this one, so the agent
picks it and this redirect never fires. That is correct: this skill is the safety net for when the
Foundry plugin is absent, not a competitor with it when present.

## Foundry app agent vs. API-managed agent

| Signal in the request | Route |
|---|---|
| "Foundry app", `manifest.yml`, `ai.agents`, `ai.knowledge_bases`, `foundry agents create`, exposing a collection or API operation as an agent tool | **Here** — redirect to foundry-skills |
| "put my agent in Charlotte" from a Foundry app | **Here** — the app owns the agent; Foundry scaffolds and exposes it |
| Create, update, publish, or analyze an agent by ID or name against the Falcon API; manage a knowledge base and its files; invoke, cancel, or trace a run | **`agents`**, **`knowledge-bases`**, **`invocation`** — handle it here |
| Discover models, tools, templates, or spans | **`discovery`** — handle it here |
