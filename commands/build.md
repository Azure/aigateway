---
description: Discover an AI Gateway's models and MCP tools, retrieve a credential, and integrate them into your app — call a model, connect MCP tools, or scaffold a runnable agent.
argument-hint: [gateway resource id or host] [optional use case]
---

# /ai-gateway:build

Take the user all the way from discovery to working code that uses an existing
AI Gateway's models and/or MCP tools — in whatever they're building. This command runs
the **full** workflow in the bundled skill `skills/use-ai-gateway/SKILL.md` end to end:

1. **Discover & select** the models and MCP tool servers in the gateway
   (Part 1 of the skill). Use `$ARGUMENTS` for the target gateway (ARM
   `gatewayResourceId` — required to list assets; a host alone is not enough, so resolve
   or ask for the id if only a host is given) and, if present, the desired use case. Ask
   the user to
   confirm the selected assets before continuing.
2. **Retrieve a credential** — list the gateway API keys and read the secret of the
   chosen key. The **same** gateway key authenticates both the model passthrough and the
   MCP tool servers, passed as `Authorization: Bearer <key>`.
3. **Integrate** (Part 2 of the skill). Ask what the user is building and pick the path:
   - **Call a model** over the gateway's OpenAI-compatible passthrough (any language or
     raw HTTP).
   - **Connect MCP tools** from an MCP-capable client/app.
   - **Scaffold a standalone agent** with the **GitHub Copilot SDK**
     (`github-copilot-sdk >= 1.0.0`) if the user wants a ready-to-run agent project —
     default to Python unless they ask for TypeScript. Produce a complete, self-contained
     project: agent code, `.env` / `.env.example`, `.gitignore` (must ignore `.env`),
     `requirements.txt` (or `package.json`), and a `README.md`.
   Integrate into the user's existing project when they have one, respecting its language
   and conventions.
4. **Run and verify** the integration once and report the outcome, distinguishing genuine
   wiring bugs (`unknown_model`, `401`/`403`, missing env var) from benign backend
   conditions (`429`/quota).

### Guardrails

- **Consumption only.** This is strictly read-only against the gateway. Never issue ARM
  `PUT`/`PATCH`/`DELETE` calls and never create, provision, or delete gateways, models,
  tools, connections, or products. If the user asks to provision anything, tell them
  that is an administrator task done in the [AI Gateway Portal](https://ai.gateway.azure.com).
- **Never hardcode secrets.** Read the gateway key from an environment variable and keep
  `.env` out of source control. Warn the user that the written `.env` holds a live key
  and to rotate it in the portal if it is ever exposed.
- Use `properties.deployment.modelName` (exact dots/casing) as the model identifier —
  prefer it over the ARM `name` or `displayName` (which some gateways reject with
  `unknown_model`). Runtime calls use the gateway's `properties.gatewayUrl` host and the
  `/default/` workspace segment: `<host>/default/models/openai/v1/...` and
  `<host>/default/toolservers/<name>/mcp` (omitting `/default/` returns `404`).
- Authenticate models and MCP tool servers with the gateway key as
  `Authorization: Bearer <key>`, in one header only (adding an `Api-Key` header as well
  returns `400`).
