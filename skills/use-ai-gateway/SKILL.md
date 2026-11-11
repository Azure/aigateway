---
name: use-ai-gateway
version: 2.2.0
updated: 2026-07-21
description: Discover the models and MCP tool servers registered in an AI Gateway, retrieve a credential, and integrate them into any application — call a model over its exact runtime protocol (OpenAI Chat Completions, OpenAI Responses, or Anthropic Messages), connect to MCP tool servers, or scaffold a standalone agent. Use this whenever a developer wants to use an AI Gateway's models and/or tools from the app they are building.
---

# Use an AI Gateway (models & MCP tools)

<!-- Skill version 2.2.0 (2026-07-21). Canonical copy shipped by the `ai-gateway` plugin. Works with any coding agent that can read this file. -->
<!-- 2.2.0: select the model's exact runtime protocol from properties.supportedEndpoints (Chat Completions / Responses / Anthropic Messages) instead of assuming OpenAI chat; robust listSecrets key parsing; skip non-agent (embeddings/image) models; native Claude Code / Codex MCP config; managed-identity vs runtime-key clarification. -->

> Invoked as `/ai-gateway:use-ai-gateway` when installed via the plugin. It is also invoked automatically by the `/ai-gateway:discover` and `/ai-gateway:build` commands.

> This skill is coding-agent–agnostic: any assistant that can read this file and run shell commands can follow it.

Use this skill when a developer wants to **use the models and/or MCP tools registered in an existing AI Gateway from their application** — whatever they are building (a web app, backend service, script, notebook, data pipeline, or a standalone agent). This single skill takes the user all the way from discovery to working, integrated code:

1. **Discover** the models and MCP tools registered in the gateway.
2. **Select** the ones that match the user's intent (and confirm with them).
3. **Retrieve** the credential needed to call them.
4. **Integrate** them into the user's application, choosing the path that fits what they're building:
   - **Call a model** over the gateway's OpenAI-compatible passthrough (any language, framework, or raw HTTP).
   - **Connect MCP tools** from an MCP-capable client/app.
   - **Scaffold a standalone agent** (GitHub Copilot SDK) if the user wants a ready-to-run agent project.

## Scope (consumption only)

This skill is **strictly for developers consuming an existing AI Gateway**. It is **read-only** against the gateway and only generates client code that calls already-registered models and tools.

- ✅ Allowed: list models, list tools/MCP servers, read an existing API key, generate integration/client/agent code.
- ❌ Not allowed: creating, provisioning, updating, or deleting gateways, models, tools, connections, products, or any other resource. Never issue ARM `PUT`/`PATCH`/`DELETE` calls. If a user asks to create or provision a gateway or model, tell them that is an administrator task done in the [AI Gateway Portal](https://ai.gateway.azure.com) and is out of scope for this skill.

---

## Part 1 — Discover & select assets

### Parameters

Ask the user for (or confirm) these before calling the API:

- **gatewayResourceId** — the ARM resource ID of the user's gateway. It is one of two APIM resource types:
  `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/service/<gateway-name>` **or** `.../Microsoft.ApiManagement/aigateways/<gateway-name>`. Both expose the same sub-resources (`workspaces/default/models`, `workspaces/default/toolServers`, and `apiKeys` at the resource root), so every template below works for either type. Keep the **leading `/`** exactly as ARM returns the `id`. The URL templates append it directly to `https://management.azure.com` (no slash in between), so the full URL resolves to `https://management.azure.com/subscriptions/...`. Don't add a slash before a leading-slash id — that produces a doubled `//subscriptions/...` and the call fails.
  > **Discovery needs the resource id, not just a host.** Listing models/tools/keys goes through the ARM control plane, which is keyed by `gatewayResourceId`. If the user gives you only a runtime host, resolve the id first (e.g. `az resource list --name <name>` or the Azure Portal) or ask for it — you cannot list assets from a host alone.
- **apiVersion** — `2025-09-01-preview`

Every ARM call must be authenticated with an Azure Resource Manager bearer token:

```
Authorization: Bearer <token>
```

Retrieve the token with:

```
az account get-access-token --query accessToken -o tsv
```

### 0. Resolve the runtime host

Discovery uses the ARM control plane (keyed by `gatewayResourceId`), but the model passthrough and MCP endpoints are called on the gateway's **runtime host**. Read the host from the resource itself rather than guessing it from the name:

```
GET https://management.azure.com{gatewayResourceId}?api-version={apiVersion}
```

Use `properties.gatewayUrl` (e.g. `https://<name>.<region>.ai.gateway-current.azure.com`) as `<ai-gateway-host>` for every runtime URL below. If `properties.gatewayUrl` is empty, fall back to `https://<properties.frontend.defaultHostname>`; never fabricate `<name>.azure-api.net` from the resource name. **All runtime paths are served under the workspace segment `/default/`** (the Default workspace — the only one today). So the model runtime base is `<ai-gateway-host>/default/models` and each MCP endpoint is `<ai-gateway-host>/default/toolservers/<tool-server-name>/mcp`. Omitting the `/default/` segment returns `404 Resource not found`.

The exact suffix after `/default/models` depends on the **model's protocol**, which you read from each model's `properties.supportedEndpoints` (see §1) — most commonly the OpenAI-compatible `/openai/v1/chat/completions`, but a model may instead expose `/openai/v1/responses` (OpenAI Responses) or `/anthropic/v1/messages` (Anthropic Messages). Build the runtime URL as `<ai-gateway-host>/default/models{supportedEndpoint}` — don't assume every model is OpenAI Chat Completions.

### One-shot discovery (copy-paste)

This performs the whole of Part 1 in one block. Set `RID` to the `gatewayResourceId` (keep its leading `/`); requires `az` and `jq`:

```bash
RID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/service/<name>"
VER="2025-09-01-preview"
TOKEN=$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)
B="https://management.azure.com$RID"
AUTH=(-H "Authorization: Bearer $TOKEN")

# Runtime host (used for every model/MCP call below)
HOST=$(curl -s "${AUTH[@]}" "$B?api-version=$VER" | jq -r '.properties.gatewayUrl')

# Models -> use .properties.deployment.modelName as the model id (exact dots/casing)
curl -s "${AUTH[@]}" "$B/workspaces/default/models?api-version=$VER" \
  | jq -r '.value[] | "\(.properties.deployment.modelName)\t\(.properties.supportedEndpoints | join(","))"'

# MCP tool servers
curl -s "${AUTH[@]}" "$B/workspaces/default/toolServers?api-version=$VER" | jq -r '.value[].name'

# API key: list keys, then read the first active key's secret (name is commonly "master" or "default")
KEYNAME=$(curl -s "${AUTH[@]}" "$B/apiKeys?api-version=$VER" | jq -r '.value[0].name')
KEY=$(curl -s -X POST "${AUTH[@]}" -H "Content-Length: 0" \
  "$B/apiKeys/$KEYNAME/listSecrets?api-version=$VER" \
  | jq -r '.primaryKey // .properties.primaryKey // .primaryValue // .properties.primaryValue // .value')

# Smoke-test a model over the passthrough — note the /default/ workspace segment and the bearer key
curl -s "$HOST/default/models/openai/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"<modelName>","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
```

The individual steps and their gotchas are documented below.

### 1. Discover models

List the models registered in the gateway workspace:

```
GET https://management.azure.com{gatewayResourceId}/workspaces/default/models?api-version={apiVersion}
```

**Use `properties.deployment.modelName` as the model identifier** in every gateway call — **not** the ARM resource `name` and **not** `properties.displayName`. This is the single most common cause of failures, so get it right:

- `properties.deployment.modelName` is the exact string the OpenAI passthrough accepts in the request body, e.g. `gpt-5.4-nano` or `DeepSeek-V3.2`. It preserves dots and original casing.
- The ARM resource `name` is a **sanitized** version of that value with dots and other characters replaced by dashes (e.g. `gpt-5-4-nano`). Some gateways accept the sanitized `name` too, but others reject it with a misleading **`unknown_model`** error — so always send `properties.deployment.modelName` to be safe, and don't "correct" a working call back to the ARM `name`.
- `properties.displayName` is a human-friendly label and is also rejected by the passthrough.

For each model, read `properties.deployment.modelName` and carry that exact string (same dots, same casing, same punctuation) through to the agent's `model=` parameter. If `properties.deployment.modelName` is missing for some reason, fall back to confirming the accepted ID by probing `POST {gateway-host}/default/models/openai/v1/chat/completions` with a tiny payload rather than guessing from the ARM `name`.

Match models to the user's use case based on the model name/description (e.g. a GPT-class model for chat, an embedding model for RAG). Suggest the best match as the default but let the user pick another.

**Read each model's protocol from `properties.supportedEndpoints`** — don't assume every model is OpenAI Chat Completions. This array holds the exact runtime operation path(s) the model accepts; select the one matching your integration and build the runtime URL as `<ai-gateway-host>/default/models{supportedEndpoint}` (preserve the returned value exactly, including any provider prefix like `/openai/v1` or `/anthropic/v1`). The recognized agent/chat protocols are:

| Endpoint suffix     | Protocol                | Client                                            |
| ------------------- | ----------------------- | ------------------------------------------------- |
| `/chat/completions` | OpenAI Chat Completions | OpenAI-compatible client (Chat Completions mode)  |
| `/responses`        | OpenAI Responses        | OpenAI-compatible client (Responses mode)         |
| `/messages`         | Anthropic Messages      | Anthropic-compatible client (Messages mode)       |

Most gateways today expose `/openai/v1/chat/completions`, which is why the examples below default to it — but if the selected model's `supportedEndpoints` shows `/responses` or `/messages` instead, use that protocol's client and request shape (see _Path A_). If a model exposes **only** non-agent endpoints (embeddings, images, audio, etc.), don't scaffold a chat agent against it — explain the mismatch and let the user pick a different model.

### 2. Discover tools (MCP tool servers)

Tools are registered as **tool servers** in the gateway workspace. Each tool server is a federated MCP host exposed at a single MCP endpoint on the gateway. List them:

```
GET https://management.azure.com{gatewayResourceId}/workspaces/default/toolServers?api-version={apiVersion}
```

Each item's `name` is the tool server name. Build its MCP endpoint URL as `https://{gateway-host}/default/toolservers/{toolServerName}/mcp` (note the `/default/` workspace segment — without it the gateway returns `404`). **`properties.mcpEndpointUrl` is frequently empty** in the ARM response, so do not rely on it — construct the URL from the host and tool server name, and only use `properties.mcpEndpointUrl` if it is non-empty. Filter to the tools relevant to the user's request (examine names and descriptions for keywords — e.g. for shipping, look for a "calculator" tool). Then **stop and ask the user**: "I found these tools for your use case. Which would you like to use?" List them clearly with brief descriptions and endpoints, and allow selecting all, some, or none.

> **Verify the tool server actually exposes tools before wiring it in.** A tool server can be registered but expose **zero** tools (e.g. a federated OpenAPI/MCP source that failed to sync). Confirm with an MCP handshake against the constructed URL, using the `Authorization: Bearer <gateway key>` header and `Accept: application/json, text/event-stream` on every request: `POST` an `initialize` request, capture the **`Mcp-Session-Id`** response header, `POST` a `notifications/initialized` message with that session id, then `POST` a `tools/list` request (also carrying the session id). If `tools/list` returns an empty array, tell the user that server has no usable tools right now (a gateway-side configuration issue, not a client bug) and let them pick a different one rather than scaffolding an agent that can't call anything.

### 3. Retrieve a credential

The model passthrough and MCP tool servers are called with a gateway **API key** — the **same key works for both**.

1. List the available keys (keys live at the gateway level, not the workspace):
   ```
   GET https://management.azure.com{gatewayResourceId}/apiKeys?api-version={apiVersion}
   ```
2. Pick a key — use the first key whose `properties.state` is `active`. The name is commonly `master` or `default`; don't hardcode it, read it from the list response.
3. Retrieve the secret:
   ```
   POST https://management.azure.com{gatewayResourceId}/apiKeys/{keyName}/listSecrets?api-version={apiVersion}
   ```
   The key is normally in `primaryKey`:
   ```json
   { "primaryKey": "2e41...", "secondaryKey": "365..." }
   ```
   Backend versions have returned a few response shapes, so read the first non-empty value from, in order: `primaryKey`, `properties.primaryKey`, `primaryValue`, `properties.primaryValue`, then `value` (when `target == "Primary"`), falling back to the equivalent `secondary*` fields. If none is present, the caller likely isn't authorized to `listSecrets` — stop and direct them to an administrator rather than creating or rotating a key.

The credential is passed as **`Authorization: Bearer <gateway key>`** for both the model passthrough and the MCP tool servers. It's still a gateway key, not an Entra token.

> **Discovery-only path:** If the user only wants to explore and select assets (models/tools) and does **not** want to integrate them yet, you can stop here. Present the discovered assets and selected credential, and skip Part 2. Code generation is optional.

---

## Part 2 — Integrate into your application

By now you have (a) the selected model(s) and/or MCP tool server(s) and (b) the gateway API key. Now wire them into whatever the user is building.

**First, pick the integration path** — ask the user what they're building if it isn't already clear, then follow the matching path (they can combine A and B):

- **Path A — Call a model.** The user wants their app/script/service to send prompts to a model. Works from any language or raw HTTP via the gateway's OpenAI-compatible passthrough. _Most common for existing apps._
- **Path B — Connect MCP tools.** The user wants their app or MCP-capable client to call the gateway's registered MCP tool servers.
- **Path C — Scaffold a standalone agent.** The user wants a ready-to-run agent project (GitHub Copilot SDK) that combines models and tools.

Whichever path you take, integrate into the user's **existing** project when they have one (respect its language, framework, and conventions) rather than forcing a new scaffold. Path C's scaffold is only for users who explicitly want a fresh standalone agent.

**Shared rules (all paths):**

- Read every credential from environment variables (e.g. `AI_GATEWAY_API_KEY`) — never hardcode secrets. See _Shared: credentials & project hygiene_ below.
- The gateway authenticates **both** models and MCP tool servers with the same key, passed as **`Authorization: Bearer <gateway key>`**. Send it in one header only: a request that also carries an `Api-Key` header gets `400` ("Specify either an API key or an Authorization header, not both").
- **Client key vs. backend managed identity are different things.** A model provider or tool server may use the gateway's managed identity to authenticate to *its* upstream (that's gateway-to-backend auth, transparent to your app). Don't try to fetch or supply that upstream credential, and don't replace the gateway key with a provider key or the provider's own auth header (such as Anthropic's `x-api-key`) — your app authenticates to the gateway runtime with the gateway key as a bearer token.

---

### Path A — Call a model

Most AI Gateway models expose an **OpenAI-compatible** endpoint, so the examples below default to it. First confirm the selected model's protocol from its `properties.supportedEndpoints` (see §1) and derive the client **base URL** from the exact endpoint by stripping the operation suffix:

| Protocol (endpoint suffix)         | Client base URL = `<ai-gateway-host>/default/models` + …          | Client appends       |
| ---------------------------------- | ----------------------------------------------------------------- | -------------------- |
| OpenAI Chat Completions (`/chat/completions`) | `/openai/v1` (drop `/chat/completions`)                | `/chat/completions`  |
| OpenAI Responses (`/responses`)    | `/openai/v1` (drop `/responses`)                                  | `/responses`         |
| Anthropic Messages (`/v1/messages`)| the endpoint with `/v1/messages` removed (Anthropic SDK re-adds it) | `/v1/messages`     |

Common case — OpenAI-compatible. Point any OpenAI-style client (or plain HTTP) at it:

- **Base URL:** `<ai-gateway-host>/default/models/openai/v1` — e.g. `https://my-gateway.westus2-01.ai.gateway-current.azure.com/default/models/openai/v1`. This is the same endpoint the [AI Gateway Portal](https://ai.gateway.azure.com) advertises to consumers; clients append `/chat/completions` (or `/responses` for a Responses model). The `/default/` segment (the workspace) is required — dropping it returns `404`.
- **Auth header:** `Authorization: Bearer <gateway key>`. OpenAI-compatible SDKs send their `api_key` this way, so pass the gateway key as the SDK's `api_key` and don't add another auth header.
- **Model identifier:** use the selected model's **`properties.deployment.modelName`** (e.g. `gpt-5.4-nano`) exactly — same dots, casing, and punctuation. Prefer it over the ARM resource `name` (e.g. `gpt-5-4-nano`) or `displayName`, which may be rejected with `unknown_model` on some gateways.

#### curl

```bash
curl "$AI_GATEWAY_HOST/default/models/openai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  -d '{
    "model": "<properties.deployment.modelName>",
    "messages": [{ "role": "user", "content": "Hello!" }]
  }'
```

#### Python (openai SDK)

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=f"{os.environ['AI_GATEWAY_HOST']}/default/models/openai/v1",
    # The SDK sends api_key as Authorization: Bearer, which is how the gateway reads its key.
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)

resp = client.chat.completions.create(
    model="<properties.deployment.modelName>",  # e.g. "gpt-5.4-nano"
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)
```

#### TypeScript / JavaScript (openai SDK)

```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: `${process.env.AI_GATEWAY_HOST}/default/models/openai/v1`,
  // The SDK sends apiKey as Authorization: Bearer, which is how the gateway reads its key.
  apiKey: process.env.AI_GATEWAY_API_KEY!,
});

const resp = await client.chat.completions.create({
  model: "<properties.deployment.modelName>", // e.g. "gpt-5.4-nano"
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(resp.choices[0].message.content);
```

> The passthrough is OpenAI-compatible, so streaming, tools/function-calling, and other OpenAI request fields work as usual — just keep the gateway key as the SDK's API key and the exact `modelName`.

#### Other protocols (only when the model's `supportedEndpoints` says so)

If the selected model exposes `/responses` or `/anthropic/v1/messages` instead of `/chat/completions`, use that protocol's request shape (same bearer key, same exact `modelName`, same `/default/models` prefix):

```bash
# OpenAI Responses model (supportedEndpoints contains /openai/v1/responses)
curl "$AI_GATEWAY_HOST/default/models/openai/v1/responses" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  -d '{"model":"<properties.deployment.modelName>","input":"Hello!"}'

# Anthropic Messages model (supportedEndpoints contains /anthropic/v1/messages)
curl "$AI_GATEWAY_HOST/default/models/anthropic/v1/messages" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"<properties.deployment.modelName>","max_tokens":16,"messages":[{"role":"user","content":"Hello!"}]}'
```

For SDKs, set the base URL per the derivation table above and pass the gateway key as a bearer token: the OpenAI SDK's `responses.create(...)` (key in `api_key`) targets a Responses model, and the Anthropic SDK with `base_url = <messages endpoint minus /v1/messages>` plus `auth_token=<gateway key>` (`authToken` in TypeScript) targets a Messages model. Don't pass the gateway key as the Anthropic SDK's `api_key`: that sends `x-api-key`, which the gateway rejects with `401`. Don't point an OpenAI Chat Completions client at a `/responses`- or `/messages`-only model (and vice versa) — the protocol must match the endpoint.

---

### Path B — Connect to MCP tool servers

Each registered MCP tool server is reachable at its own MCP endpoint (captured during discovery), authenticated with the same gateway key as **`Authorization: Bearer <gateway key>`**. Use it from any MCP client:

- **Endpoint:** the tool server's MCP URL from discovery (e.g. `<ai-gateway-host>/default/toolservers/<name>/mcp`).
- **Transport:** streamable HTTP (`type: "http"`).
- **Auth header:** `Authorization: Bearer <gateway key>`.

To sanity-check a tool server manually, run the full MCP handshake — `initialize`, then `notifications/initialized`, then `tools/list` — carrying the `Mcp-Session-Id` returned by `initialize` on the follow-up calls:

```bash
# 1. initialize — capture the Mcp-Session-Id response header
SID=$(curl -s -D - -o /dev/null "$TOOL_ENDPOINT" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1.0"}}}' \
  | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')

# 2. notifications/initialized
curl -s "$TOOL_ENDPOINT" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  ${SID:+-H "Mcp-Session-Id: $SID"} \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null

# 3. tools/list — an empty "tools" array means the server exposes no usable tools
curl -s "$TOOL_ENDPOINT" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  ${SID:+-H "Mcp-Session-Id: $SID"} \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

To wire it into an application, configure your MCP client with the endpoint URL, `http` transport, and the `Authorization` header — for example, in a client that reads an `mcp.json`/`mcpServers` map:

```json
{
  "mcpServers": {
    "<tool-name>": {
      "type": "http",
      "url": "<tool-endpoint>",
      "headers": { "Authorization": "Bearer ${AI_GATEWAY_API_KEY}" }
    }
  }
}
```

Adapt the exact shape to whatever MCP client/library the user's app uses (the essentials are always: endpoint URL, HTTP transport, and the `Authorization: Bearer` header). Native config locations for common coding agents:

- **Claude Code** — the `mcpServers` JSON above is exactly the shape of a project-scoped `.mcp.json`. Claude Code expands `${AI_GATEWAY_API_KEY}` from the environment in HTTP `headers`. Run `claude mcp list` (or `/mcp`) and approve the project server when prompted.
- **OpenAI Codex** — add to `~/.codex/config.toml` (or a trusted project `.codex/config.toml`), passing the key by env-var reference so the secret isn't written into config:
  ```toml
  [mcp_servers.<tool-server-name>]
  url = "<ai-gateway-host>/default/toolservers/<tool-server-name>/mcp"
  bearer_token_env_var = "AI_GATEWAY_API_KEY"
  ```
  Verify with `codex mcp list` or `/mcp`.
- **Other MCP-capable agents** — consult the agent's current CLI help or config schema for its remote/HTTP MCP entry rather than guessing field names; the essentials are the same three: endpoint URL, HTTP transport, `Authorization: Bearer` header.

If the user is building an agent that needs these tools, prefer **Path C**, which wires models and MCP tools together.

---

### Path C — Scaffold a standalone agent (GitHub Copilot SDK)

Use this path when the user explicitly wants a runnable standalone **agent** project that combines the selected model and MCP tools.

#### C.1 Choose language

Ask the user which language they prefer. **Default to Python** if not specified. Supported:

- Python (default)
- TypeScript/JavaScript

#### C.2 Generate agent code

Generate the agent code using the **GitHub Copilot SDK** (code, docs, examples: https://github.com/github/copilot-sdk).

> **Required SDK version: `github-copilot-sdk >= 1.0.0`.** The agent authenticates the BYOK model with the provider's `api_key`, which the SDK sends as `Authorization: Bearer`, and the MCP tool servers with a custom `Authorization` header. SDK versions older than 1.0.0 silently drop custom headers. Always pin `>= 1.0.0` in `requirements.txt` / `package.json` and in any install command.

The generated code must:

- Use the GitHub Copilot SDK correctly for the chosen language (default to Python, unless the user specifies otherwise). Require **`github-copilot-sdk >= 1.0.0`** — older versions drop the custom headers used to authenticate the gateway tools
- Configure MCP tool connections to the selected AI Gateway tool servers via `mcp_servers` in the session config, using `type: "http"` with the tool server's MCP endpoint URL
- Authenticate tool servers with the gateway API key passed as **`Authorization: Bearer <key>`** via the `headers` config
- Configure model access through a BYOK `provider` in the session config
- Authenticate models with the **same** gateway API key in the provider's `api_key` field. The SDK sends it as `Authorization: Bearer`, which is how the gateway reads its key. Don't add an `Api-Key` header to the provider as well: a request with both headers gets `400`
- Use model provider `type: "openai"` (the AI Gateway exposes an OpenAI-compatible passthrough, where the model is selected by name in the request body)
- Construct the model `base_url` as the AI Gateway's unified model passthrough: `<ai-gateway-host>/default/models/openai/v1` — for example `https://my-gateway.westus2-01.ai.gateway-current.azure.com/default/models/openai/v1`. This is the same endpoint the [AI Gateway Portal](https://ai.gateway.azure.com) advertises to consumers (the SDK appends `/chat/completions`). The `/default/` workspace segment is required — dropping it returns `404`
- Precisely specify the model parameter and match it exactly to the selected model's **`properties.deployment.modelName`** (e.g. `gpt-5.4-nano`) — same dots, same casing, same punctuation. Prefer it over the ARM resource `name` (e.g. `gpt-5-4-nano`) or `displayName`, which may be rejected with `unknown_model` on some gateways
- Generate a custom `on_permission_request` handler that requires an explicit user decision for ordinary permission requests and leaves managed approval requests unresolved for the managing client. Never use `PermissionHandler.approve_all` in generated applications
- Restrict each MCP server's `tools` list to the individually selected tool names. Never generate `"tools": ["*"]`
- Set `available_tools` to the selected MCP tools using the Copilot SDK's source-qualified `mcp:<server-key>-<tool-name>` format. This prevents unrelated built-in, custom, or newly added MCP tools from becoming available implicitly
- Pass the session config to `create_session` as keyword arguments (e.g. `create_session(model=..., provider=..., mcp_servers=...)`), like in the example below
- Read all credentials from environment variables — never hardcode secrets
- Load environment variables from a `.env` file using `python-dotenv` (Python) or `dotenv` (TypeScript)
- Use `send_and_wait()` with the prompt as a positional string to get the agent's response, then **always print the response content or the error** — the user must see output
- Handle errors gracefully with full tracebacks for debugging
- Include a clear main entry point and example usage
- Match the code example below as closely as possible

##### Python Example Structure

```python
import asyncio
import os
from dotenv import load_dotenv
from copilot import (
    CopilotClient,
    PermissionNoResult,
    PermissionRequest,
    PermissionRequestResult,
)
from copilot.rpc import PermissionDecisionApproveOnce, PermissionDecisionReject

load_dotenv()

async def confirm_permission(
    request: PermissionRequest,
    invocation: dict,
) -> PermissionRequestResult:
    if getattr(request, "managed_approval_required", False) is True:
        return PermissionNoResult()

    request_type = type(request).__name__
    details = []
    for attribute in ("tool_name", "full_command_text", "path", "url", "server_name"):
        value = getattr(request, attribute, None)
        if value:
            details.append(f"{attribute}={value}")

    description = f"{request_type}: {', '.join(details)}" if details else request_type
    answer = await asyncio.to_thread(
        input,
        f"Approve tool permission request ({description})? [y/N] ",
    )
    if answer.strip().lower() in {"y", "yes"}:
        return PermissionDecisionApproveOnce()

    return PermissionDecisionReject(feedback="The user denied this tool operation.")

async def main():
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            on_permission_request=confirm_permission,
            model="<selected-model>",  # e.g. "gpt-4o"
            # BYOK provider — points to the AI Gateway unified model passthrough.
            # The SDK sends api_key as Authorization: Bearer, which is how the
            # gateway reads its key.
            provider={
                "type": "openai",
                "base_url": "<ai-gateway-host>/default/models/openai/v1",
                "api_key": os.environ["AI_GATEWAY_API_KEY"],
            },
            # MCP tool servers from AI Gateway
            mcp_servers={
                "<tool-server-name>": {
                    "type": "http",
                    "url": "<tool-endpoint>",
                    "headers": {
                        "Authorization": f"Bearer {os.environ['AI_GATEWAY_API_KEY']}",
                    },
                    "tools": ["<selected-tool-name>"],
                },
                # Add more tools as needed
            },
            # MCP tools are registered as <server-key>-<tool-name>. The
            # source-qualified form keeps built-in and unselected tools out.
            available_tools=[
                "mcp:<tool-server-name>-<selected-tool-name>",
            ],
        )

        def on_event(event):
            event_type = event.type.value
            if event_type == "tool.execution_start":
                print(f"  [tool call: {event.data.tool_name}]")
            elif event_type == "error":
                msg = getattr(event.data, "message", str(event))
                print(f"  [error: {msg}]")

        session.on(on_event)

        reply = await session.send_and_wait("<user prompt>")

        if reply:
            print("\n=== Agent Response ===")
            print(reply.data.content if reply.data.content else "(empty response)")
        else:
            print("\n=== No response received from agent ===")

        await session.disconnect()

    except Exception as e:
        print(f"\nFailed to run agent: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

#### C.3 Create project files

After generating the agent code, create a complete, self-contained project the user can download and run as-is. See _Shared: credentials & project hygiene_ below for `.env`, `.env.example`, and `.gitignore`, plus:

4. **`requirements.txt`** (Python) — pin the agent's dependencies so the project installs in one command:

   ```
   github-copilot-sdk>=1.0.0
   python-dotenv
   ```

   (For TypeScript, generate a `package.json` with the equivalent dependencies — `github-copilot-sdk` at `>=1.0.0` — and a `start` script.)

5. **`README.md`** — a short, self-contained guide so the downloaded project runs without this chat. Include:
   - what the agent does and which gateway model + tool servers it uses (by name)
   - that tool permission requests require explicit confirmation and should be approved only when the displayed operation is expected
   - which individual MCP tools are allowlisted and how to update the allowlist intentionally
   - prerequisites (Python 3.10+, the Copilot CLI, `github-copilot-sdk >= 1.0.0`)
   - install steps (`pip install -r requirements.txt`)
   - how to set credentials (copy `.env.example` to `.env`, or use the pre-filled `.env`)
   - the run command and the expected output

#### C.4 Provide setup instructions

After generating the code, provide:

- Required package installation commands: `pip install "github-copilot-sdk>=1.0.0" python-dotenv` (the `>= 1.0.0` pin is mandatory — older SDKs drop the custom `Authorization` header that the MCP tool servers need)
- Copilot CLI must be installed separately (the SDK communicates with it via JSON-RPC)
- Environment variable setup:
  - `AI_GATEWAY_API_KEY` — the gateway API key from discovery (passed as `Authorization: Bearer` in the `headers` of each tool server, and as the BYOK provider `api_key` for the model)
- How to run the agent

#### C.5 Run and verify

Don't stop at "here's the code." Run the agent once and confirm the wiring actually works, then report the outcome to the user:

- **Run it** (e.g. `python agent.py`) and read the output.
- If the agent requests tool permission, verify the displayed operation and approve only the tool call expected for the test. An unexpected shell, file, URL, or unselected MCP operation must be denied and treated as a generated-code or prompt-safety defect.
- **Distinguish config failures from benign backend conditions.** Treat these as a **healthy** end-to-end wiring (the gateway accepted the request) — report success and move on:
  - `429 ... exceeded rate limit` or quota errors from the model
  - empty/slow responses caused by the upstream model, not the client
- **Treat these as real bugs to fix before handing off:**
  - `unknown_model` → wrong model identifier (used ARM `name`/`displayName` instead of `properties.deployment.modelName`), a protocol mismatch (e.g. a Chat Completions client pointed at a `/responses`- or `/messages`-only model)
  - `KeyError: 'AI_GATEWAY_API_KEY'` → `.env` not loaded, usually a BOM (see the `.env` note below)
  - `401`/`403` → wrong or missing `Authorization: Bearer <gateway key>` header
  - `400` "Specify either an API key or an Authorization header, not both" → remove the extra `Api-Key` header
- If you can't get a clean model response because of a backend `429`/quota, say so explicitly and note that everything up to the model was validated, rather than implying the full round-trip succeeded.

---

### Shared: credentials & project hygiene

Whenever you write credentials or scaffold files into the user's project (any path), keep secrets safe:

1. **`.env`** — populated with the actual key retrieved during discovery:

   ```
   AI_GATEWAY_API_KEY=<actual gateway API key from discovery>
   ```

   > **Security note:** this writes a **live gateway secret in cleartext** to disk. The `.gitignore` (below) keeps it out of source control, but warn the user that the file holds a real key and to **rotate it in the [AI Gateway Portal](https://ai.gateway.azure.com) if it is ever exposed or shared**.

   > **Write `.env` as UTF-8 _without_ a BOM.** `python-dotenv` (and `dotenv` for Node) does **not** strip a leading byte-order mark, so a BOM makes the first variable load as `\ufeffAI_GATEWAY_API_KEY` and the app crashes with `KeyError: 'AI_GATEWAY_API_KEY'`. This bites on Windows specifically: PowerShell's `Set-Content -Encoding utf8` and `Out-File` **add a BOM**. Write the file with a BOM-free encoder instead, e.g.:
   >
   > ```powershell
   > [System.IO.File]::WriteAllText("$PWD\.env", "AI_GATEWAY_API_KEY=$key`n", (New-Object System.Text.UTF8Encoding($false)))
   > ```
   >
   > or simply create the file through your editor/agent file-write tool, which does not add a BOM. After writing, sanity-check that the first byte is not `0xEF`.

2. **`.env.example`** — a template with a placeholder value for documentation:

   ```
   AI_GATEWAY_API_KEY=your-gateway-api-key-here
   ```

3. **`.gitignore`** — must include `.env` to prevent committing secrets:

   ```
   .env
   __pycache__/
   *.pyc
   .venv/
   ```
