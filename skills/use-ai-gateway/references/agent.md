# Scaffold a standalone agent

Use only when the user requests a standalone agent, not for an ordinary request
or existing-project integration. First establish the selected callable contract
with [models](models.md), [MCP](mcp.md) and [authentication](authentication.md).

Default to Python unless the user selected another language. Use the
[GitHub Copilot SDK](https://github.com/github/copilot-sdk) and the published
release's matching documentation and runtime, not a stale copied example.
Use Python `github-copilot-sdk>=1.0.1` with Python 3.11+, or TypeScript
`@github/copilot-sdk>=1.0.1`. Follow that release's runtime setup instructions
(current Python releases provide `python -m copilot download-runtime`).
Do not assume the runtime is installed or silently install/upgrade tools.

Configure the selected model as BYOK, keeping inference on the gateway:

| Protocol | Provider configuration |
| --- | --- |
| Chat Completions | `type: "openai"`, derived base URL, `wire_api: "completions"` (TypeScript `wireApi`). |
| Responses | `type: "openai"`, derived base URL, `wire_api: "responses"`. |
| Messages | `type: "anthropic"` with a verified Messages-compatible base URL. |

Use the exact callable alias/model name. Supply the selected credential through
the release's supported bearer token/provider callback or Authorization-header
configuration; ensure Entra tokens refresh during long-lived sessions.
Never use an upstream Foundry URL or `type: "azure"` just because the gateway
is hosted in Azure. Non-chat models cannot back a conversational agent.

Configure only the selected remote servers through Python `mcp_servers` or
TypeScript `mcpServers`, with their HTTP URLs and the endpoint-appropriate
[runtime auth headers](authentication.md). Send a gateway key or Entra token
as an `Authorization: Bearer` credential for each MCP connection.
Set each server's `tools` to the exact selected names, never `["*"]`.
Restrict session tools with `available_tools`/`availableTools` using the
source-qualified `mcp:<server-key>-<tool-name>` form; use an empty list when no
tools are selected. Start from an isolated client configuration (current Python
SDK: `CopilotClient(mode="empty")`) and add only selected server definitions.
Do not implicitly expose built-in shell/filesystem tools or start unrelated
user/plugin MCP servers; if the chosen release cannot isolate configuration,
report that constraint. Check client/runtime protocol compatibility before
promising a modern-only server will work.

Implement a permission callback that requires an explicit user decision for
ordinary permission requests. Leave managed approvals to the managing client
using the SDK's no-result decision; deny in noninteractive mode rather than
auto-approving. Never copy `PermissionHandler.approve_all` or equivalent
approval-all callbacks from quickstarts.

Use the current SDK's typed session APIs, bounded waits, and async cleanup.
Print the model's response or an actionable, redacted failure, and propagate
errors as failures. A timeout or missing response is not success. Do not log
request headers, credentials, or raw exception objects containing secrets.

Create a complete project: entry point, dependency manifest/start command,
`.env.example`, `.gitignore`, and README explaining authentication, model
protocol, selected tool allowlists, permission decisions, setup, run command,
and expected output. Include the relevant callable-asset/routing constraints
and how to collect safe diagnostic IDs without logging secrets or payloads.
Load `.env` explicitly if using dotenv. Do not generate a second project when
the user asked to integrate into an existing one.
