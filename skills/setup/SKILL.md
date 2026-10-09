---
name: setup
description: >
  Configure credentials for Charlotte AI AgentWorks API access. Guides users through manual TOML
  configuration or environment variable setup.
  TRIGGER when user explicitly asks to "set up Charlotte AI AgentWorks", "configure credentials", or has auth errors.
  DO NOT TRIGGER for general Charlotte AI AgentWorks usage (orchestrator handles routing).
version: 1.0.0
updated: 2026-08-21
tags: [agentworks, setup, credentials, authentication]
author: CrowdStrike
license: MIT
compatibility: Claude Code >=1.0
metadata:
  category: configuration
---

# Charlotte AI AgentWorks Setup

## Configuration

This plugin requires Falcon API OAuth 2.0 credentials. Configure using one of the methods below.

**Test authentication:**
```bash
scripts/python.sh common/scripts/auth.py
```

Should authenticate 5 FalconPy clients (KnowledgeBases, KnowledgeBaseFiles, KnowledgeBaseAuditEvents, Agents, AgentInvocation), all sharing one token.

## Setup Methods

### Option 1: TOML Profile (Recommended)

Create `~/.cache/crowdstrike-charlotte-ai-agentworks/credentials.toml`:

```toml
default = "us-1"

[us-1]
client_id = "your-client-id-here"
client_secret = "your-client-secret-here"
base_url = "https://api.crowdstrike.com"  # or your cloud URL
```

Set permissions:
```bash
mkdir -p ~/.cache/crowdstrike-charlotte-ai-agentworks
chmod 700 ~/.cache/crowdstrike-charlotte-ai-agentworks
chmod 600 ~/.cache/crowdstrike-charlotte-ai-agentworks/credentials.toml
```

### Option 2: Environment Variables

```bash
export FALCON_CLIENT_ID=<your-id>
export FALCON_CLIENT_SECRET=<your-secret>
export FALCON_BASE_URL=https://api.crowdstrike.com  # optional, defaults to US-1
```

## Required API CSRN Permissions

Charlotte AI AgentWorks uses these CSRN permissions:
- `csrn:charlotte-ai:agent:definition` (read + write)
- `csrn:charlotte-ai:agent:invocation` (assert/execute)
- `csrn:charlotte-ai:agent:knowledge-base` (read + write)
- `csrn:charlotte-ai:agent:template` (read)
- `csrn:charlotte-ai:agent:metrics` (read)

## Verification

After setup, run:
```bash
cd /path/to/agentworks-skills
scripts/python.sh common/scripts/auth.py
```

Should see:
```
✓ Authentication successful (KnowledgeBases client)
✓ Authentication successful (KnowledgeBaseFiles client)
✓ Authentication successful (KnowledgeBaseAuditEvents client)
✓ Authentication successful (Agents client)
✓ Authentication successful (AgentInvocation client)
```

## Troubleshooting

**"No credentials found"**
- Check TOML file exists and has correct profile
- OR set env vars

**"Authentication FAILED"**
- Verify client_id/secret are correct
- Check base_url matches your Falcon cloud (us-1, us-2, eu-1, etc.)
- Ensure API client has required scopes

**"token_expired() returns True"**
- Check network connectivity to Falcon API
- Verify client_id/secret haven't been rotated
- Run `python common/scripts/auth.py` -- as of this version it prints the real API error
  (e.g. bad credentials, missing scope) instead of just "could not obtain token"

**Authentication fails with a certificate/TLS error during login** (e.g.
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`) -- distinct from the
package-install certificate errors below; this happens on the live API call itself, often
behind a TLS-intercepting proxy (e.g. Zscaler) common in corporate environments.
- Check whether your organization requires a custom CA bundle for outbound HTTPS, and that
  Python's trust store (or `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE`) points at it
- Confirm a plain `curl` to your `base_url` succeeds from the same shell/environment first --
  if that also fails, this is a network/proxy config issue outside the plugin, not an
  Charlotte AI AgentWorks credential problem
- These settings must be configured outside the AI coding agent; restart the coding agent
  terminal after configuring so it receives the updated environment

**Package installation reports access, certificate, or registry errors**
- Refer the user to their organization's documentation for setting up a Python environment.
- Their organization may require an approved package registry or specific certificates.
- These settings must be configured outside the AI coding agent.
- After configuration, restart the coding agent terminal so it receives the updated environment.
- Some workstation changes may require signing out and back in before restarting the agent.

## Security

- **Never paste credentials into chat**
- Credentials go only into the TOML file (via your editor) or env vars
- TOML file should be `chmod 600`
- TOML directory should be `chmod 700`
- Never commit credentials to git

## Multi-Cloud Support

Charlotte AI AgentWorks supports all Falcon clouds. `base_url` may be any Falcon cloud URL,
including custom/internal environments; it is not restricted to this list:
- US-1: `https://api.crowdstrike.com` (default)
- US-2: `https://api.us-2.crowdstrike.com`
- EU-1: `https://api.eu-1.crowdstrike.com`
- US-GOV-1: `https://api.laggar.gcw.crowdstrike.com`
