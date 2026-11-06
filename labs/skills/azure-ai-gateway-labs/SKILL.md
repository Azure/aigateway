---
name: azure-ai-gateway-labs
description: Guide to the Azure AI Gateway hands-on labs, a set of step-by-step labs, learning paths, and Jupyter notebooks published at azure.github.io/aigateway from the labs folder of github.com/Azure/aigateway. Use this skill whenever a user wants to learn, try, demo, teach, or automate Azure AI Gateway (resource type Microsoft.ApiManagement/aigateways), even if they don't mention labs. Topics include provisioning a gateway, publishing Foundry, OpenAI, or Anthropic models behind aliases, federating MCP tools, token limits, cost budgets, content safety, runtime API keys, Entra ID and RBAC, managed identities, monitoring and OpenTelemetry chargeback, agent frameworks, Foundry hosted agents, coding-agent plugins, private networking, Agent 365, and an enterprise reference architecture. The skill picks the right lab or learning path, follows one track (portal, Azure CLI, REST, Bicep, code, or notebook) step by step, verifies the result, and cleans up.
license: MIT
---

# Azure AI Gateway labs

Hands-on labs for Azure AI Gateway. Each lab is one Markdown file with a scenario, a diagram, step-by-step tasks
with checkpoints, a **Verify** section, and clean-up, and the Troubleshooting page maps its errors to its steps. Most
labs offer several tracks (Portal, Azure CLI, REST, Bicep, Code), and some also ship a Jupyter notebook.

- Labs site: https://azure.github.io/aigateway/
- Source: https://github.com/Azure/aigateway/tree/main/labs
- Product docs: https://ai.gateway.azure.com/docs
- AI Gateway portal: https://ai.gateway.azure.com
- Overview on Microsoft Learn: https://learn.microsoft.com/azure/ai-gateway/overview

Portal labels and API shapes can change as AI Gateway evolves. When a step fails, look up the error in the lab's
section of the Troubleshooting page (its **Step** column names the steps where each error shows up), and compare the
step with the product docs that the lab links to, before you improvise a fix.

## Where to find things

| You need | Get it from |
| :-- | :-- |
| A lab as clean Markdown, with its metadata as YAML front matter | `https://azure.github.io/aigateway/labs/<slug>/index.md` |
| The same lab on GitHub, with navigation and inline code | `https://github.com/Azure/aigateway/blob/main/labs/<slug>/README.md` |
| The lab page to share with a person | `https://azure.github.io/aigateway/labs/<slug>/` |
| Files the lab uses (`infra/`, the notebook) | `labs/<slug>/` in a clone, or `https://raw.githubusercontent.com/Azure/aigateway/main/labs/<slug>/<path>` |
| Shared setup: sign-in, the `aigateway` extension, resource providers, regions, the clone, and azd | The Setup guide: `https://azure.github.io/aigateway/setup/index.md`, or `labs/SETUP.md` in a clone |
| Errors, likely causes, and fixes, for setup and deployment and for each lab | The Troubleshooting page: `https://azure.github.io/aigateway/troubleshooting/index.md`, or `labs/TROUBLESHOOTING.md` in a clone. Each lab has a `## Lab NN: <short title>` section |
| Every lab in one file | `https://azure.github.io/aigateway/llms-full.txt` |
| Which lab covers a product release or a new feature | `https://azure.github.io/aigateway/release-notes/index.md`, or `labs/RELEASE-NOTES.md` in a clone |

When the workspace is a clone of `Azure/aigateway`, read `labs/<slug>/README.md` from disk instead.

## Run a lab with the user

1. **Pick the lab.** Match the user's goal to the [use-case map](#use-case-map) or the [catalog](#lab-catalog). Check
   what the lab needs first: the portal, CLI, and REST tracks of most labs reuse the gateway from lab 01 and the
   model from lab 02, while a lab's Bicep + azd track creates its own. For newcomers,
   suggest the 5-minute quick start, `quickstart`: in the portal, with Azure CLI commands in Cloud Shell, or with one
   `azd up` of a Bicep template that it clones from the repo, it creates a gateway, a Foundry
   model, an alias, and a runtime key with lab 02's names, so labs 03 onward work on it. Then suggest the 30-minute
   essentials path.
2. **Read the whole lab** before you run anything. **Before you begin** lists the tools, Azure roles, regions, and
   billable resources. Its first line, `<!-- setup: <keys> -->`, lists the one-time tasks of the Setup guide that the
   lab needs (`permissions`, `tools`, `sign-in`, `extension`, `providers`, `regions`, `clone`), and the region below
   it links to each one (`../SETUP.md#<section>`). The lab doesn't repeat them, so read each linked section and run
   it when the user hasn't done it yet. Bicep + azd tracks expect the repo cloned to `~/aigateway`.
3. **Choose one track.** A track starts at `<!-- track: <id> | <label> -->`, and the group of tracks ends at
   `<!-- /tracks -->`. On GitHub, each track is a collapsible `<details>` section. Follow only the chosen track.
   Sections outside the track markers, such as **Verify** and **Clean up**, apply to every track. A track can end
   with its own **Clean up** step instead, as in the quick start.
4. **Fill in the placeholders:** `<subscription-id>`, `<resource-group>`, `<gateway>`, `<location>`,
   `<model-name>`, `<provider-name>`, `<foundry-account-name>`, and `<tenant-id>`. Get the values from the user or
   from `az account show`. Keep secrets in environment variables such as `$AI_GATEWAY_API_KEY`, and never write
   them to files, code, or chat.
5. **Go one step at a time.** Each `###` heading in a track is a step. Run it, then compare the result with the
   **Checkpoint** that follows. `<!-- include: infra/<file> -->` means the step uses that file from the lab folder.
   `<!-- widget: … -->` marks an interactive simulator on the site, which you can skip.
   `<!-- video: … -->` marks an optional narrated walkthrough; the steps in the text are complete without it.
   Every command has a `#` comment that says what it does. In the Bash and PowerShell tabs, it prints an emoji
   status line, such as `🚀 Gateway aigw-1a2b3c is ready`, only when it succeeds, so a missing status line means
   that the command failed: read the error above it. 🚦 marks a failure that the lab causes on purpose, such as a
   `429` from a token limit. Keys and tokens print only their length.
6. **Verify** with the lab's **Verify** section, and tell the user what you checked.
7. **Clean up.** Labs create billable resources. Offer the lab's **Clean up** section, or the chosen track's
   **Clean up** step, and delete only what this lab created, because later labs reuse the gateway and the model.

Before you create, change, or delete Azure resources, confirm the subscription and resource group with the user.

| Track | Marker id | How to use it |
| :-- | :-- | :-- |
| Portal | `portal` | Click-by-click steps in the AI Gateway portal. You can't run them from a shell, so guide the user through them one screen at a time. |
| Azure CLI | `cli` | `az aigateway` commands (extension 1.0.0b22 or later), plus `az rest` calls to Azure Resource Manager for what the extension can't do yet, in Bash and PowerShell variants. This is the easiest track for an agent to run. |
| REST API | `rest` | Raw Azure Resource Manager requests, for users who script against the API themselves. |
| Bicep + azd | `iac` | A self-contained azd template in the lab folder (`azure.yaml` and `infra/main.bicep`): clone the repo, run `azd up` in the lab folder to create a new resource group with its own gateway, model, and the lab's feature, read the outputs with `azd env get-value`, change settings with `azd env set` and `azd provision`, and delete everything with `azd down --purge --force`. Lab 09 labels its track **Policy as code** (JSON policies applied by a script), and lab 21 **Bicep** (`az deployment sub create` with parameter files). |
| Code | `code` | Python, TypeScript, and .NET clients, and agent frameworks, calling the gateway at runtime. |
| Notebook | none | `labs/<slug>/<slug>.ipynb` deploys the lab's resource-group-scoped `infra/` Bicep modules onto the notebook's gateway from Python with helpers in `labs/shared/utils.py`, then checks each step with `assert`. |

## Facts to rely on

- The gateway is the `Microsoft.ApiManagement/aigateways` resource, API version `2025-09-01-preview`. Never use
  `Microsoft.ApiManagement/service`. In Bicep, omit `sku`, so the service default `Standard` applies (as with
  `az aigateway create`), and set no publisher properties. Don't declare a `Microsoft.Web/connectorGateways`
  resource. Put `#disable-next-line BCP081` before each `aigateways` resource declaration, because Bicep has no
  types for it. Gateway names are at most 24 characters, and a subscription
  can have at most five gateways in each region.
- AI Gateway runs in a growing list of regions. List them with
  `az provider show --namespace Microsoft.ApiManagement --query "resourceTypes[?resourceType=='aigateways'].locations | [0]"`
  (display names; `az account list-locations` maps them to `--location` names), as in the Setup guide's
  **Find the available regions**. The portal can offer fewer regions than the CLI and Bicep. Templates that deploy
  Foundry models need a region where those models are available too.
- The CLI track uses the `az aigateway` extension 1.0.0b22 or later (the Setup guide installs it) for gateways
  (including `network update`), providers, models (`model create --deployment-config "{resourceId:…,modelName:…}"`),
  aliases, model policies (`model policy set-token-limit`, `set-content-safety`, `set-cost-limit`, `remove`),
  Gateway scope policies (`az aigateway policy`), telemetry exporters (`az aigateway telemetry-exporter`), API keys,
  and MCP servers. `az aigateway create` takes no `--sku`, secrets come from `api-key list-secrets`, rotation uses
  `api-key regenerate --key-type primary|secondary`, `api-key update --state suspended|active` pauses a key, and
  `model-alias set` creates an alias or updates the existing one. `--token-counter-key` takes one or more values,
  such as `Identity IPAddress`. `model-provider update --foundry` and `--custom` merge a partial JSON value into the
  provider's settings, and `mcp update --versions` and `--endpoints` change only what you pass. Don't use
  `model create --foundry-resource-id --deployment`: it crashes in 1.0.0b22. The track keeps `az rest` for what the
  extension can't do yet: MCP tool rules (`allowList`, `blocked`, `accessState`) and writing a whole policy array
  from a file. Tool servers have no top-level `failureMode`: the service drops it, and only an endpoint's
  `required` setting persists. Only connector-based MCP tools use a `Microsoft.Web/connectorGateways` resource: the
  portal creates one with the gateway's name when it creates the gateway, and deletes it with the gateway. The CLI
  and Bicep tracks don't create it.
  Tracks that call `az rest` set `GATEWAY_ID` (from `az aigateway show`),
  `WS` (`https://management.azure.com$GATEWAY_ID/workspaces/default`), and `API`
  (`api-version=2025-09-01-preview`) once. A `PATCH` replaces whole arrays such as `properties.policies`, so read,
  edit, then write.
- The runtime URL is `https://` plus `properties.frontend.defaultHostname`: the name's first 10 characters
  (without a trailing hyphen), a hyphen, a 13-character hash, and `.<region>-01.ai.gateway.azure.com`, for example
  `https://aigw-labs-k3v7qz2m9xw4p.eastus2-01.ai.gateway.azure.com` for `aigw-labs-001`. Always read it from the
  gateway, never build it from the name, and the labs write it as `<gateway-url>`. A new gateway with no models answers `404`.
- Models: `<runtime URL>/default/models/openai/v1` serves OpenAI Chat Completions and Responses.
  `<runtime URL>/default/models/anthropic/v1/messages` serves Anthropic Messages.
- The labs use `gpt-5-mini` (version `2025-08-07`, `GlobalStandard`) from Foundry, and `gpt-6.1-sol` (version
  `2026-09-29`) where a lab needs a second or stronger model. `gpt-5-mini` is a reasoning model: Chat Completions
  rejects `max_tokens` (send `max_completion_tokens`) and any `temperature` other than the default, `1`, so leave
  it out. Chat Completions reports the model as `gpt-5-mini-2025-08-07`, and Responses as `gpt-5-mini`. At the
  default effort, reasoning can use the whole token budget and leave the reply empty, so the scripts send
  `reasoning_effort: "none"` when they cap tokens. Claude Sonnet 5.5 and Haiku 5.5
  think by default, so read the `text` blocks in `content` and leave headroom in `max_tokens`.
- MCP tools: `<runtime URL>/default/toolservers/<name>/mcp`. Federated tools are named `<namespace>_<tool>`, for
  example `learn_microsoft_docs_search`.
- Runtime auth for models: a runtime API key in the `api-key` header, or `Authorization: Bearer` with the key or a
  Microsoft Entra token. Never send both, or the gateway answers `400`. With an OpenAI SDK, pass the key as the
  client's API key. MCP endpoints read keys only from `api-key`.
- Entra tokens use the audience `https://azure-api.net/aigateway`. The data-plane roles are **AI Gateway User**
  (models and tools), **AI Gateway Models User**, and **AI Gateway Tools User**.
- Policy changes take 20 to 60 seconds to apply. A token or request rate limit answers `429` with `Retry-After`, a
  cost budget answers `403` `LlmCostQuotaExceeded`, and content safety blocks with `400`.
- Streaming (`"stream": true`) returns `text/event-stream` chunks and ends with `data: [DONE]`. Chat Completions
  sends a usage chunk with empty `choices` only when the client sets `stream_options.include_usage`, and
  `stream_options` without `stream` answers `400`. The gateway counts the tokens of every stream for limits,
  budgets, and Monitoring either way. A limited caller gets a JSON `429` before the stream starts, and a stream that
  already started finishes.
- GitHub Copilot (VS Code, CLI, SDK, and the GitHub Copilot app) can use a gateway model with bring your own key: base
  URL `<runtime URL>/default/models/openai/v1`, the Responses API, a runtime key sent as a bearer token, and the alias
  as the model ID. The gateway doesn't serve `GET /models` (it answers `400`), so add models by hand. Name the alias
  after a well-known model, such as `gpt-6.1-sol`, so Copilot applies that model's prompts and token sizes. Agent
  requests carry 14,000 to 38,000 input tokens each, so give Copilot keys a generous token limit.
- The same Copilot clients can use a gateway MCP server, such as `learn`, at `<runtime URL>/default/toolservers/<name>/mcp`
  with the same runtime key in the `api-key` header (a bearer token answers `401`). Add it with
  `copilot mcp add --transport http --header 'api-key: ${AI_GATEWAY_API_KEY}' <name> <url>` (the CLI and the GitHub
  Copilot app share `~/.copilot/mcp-config.json`), a `.vscode/mcp.json` `http` server with a password input, or
  `mcpServers` in an SDK session. Tool results add tokens: a Learn search returns 26 to 52 KB, so one question with
  a search can send about 50,000 input tokens. Suspending the key returns `401` for both models and tools.

## Lab catalog

Each entry shows the level, time, tracks, and the labs it needs.

<!-- gh:begin catalog: generated by "npm run sync" from the metadata, do not edit -->
### Foundations

- **⚡** [Your first model call in 5 minutes](https://azure.github.io/aigateway/labs/quickstart/index.md) `quickstart` (Beginner, 5 min · Portal, CLI, Bicep): Learn the building blocks of Azure AI Gateway, create a gateway with a Microsoft Foundry model in the portal, the Azure CLI, or Bicep with azd, and make your first model call, all in about five minutes.
- **00** [How Azure AI Gateway works](https://azure.github.io/aigateway/labs/00-how-ai-gateway-works/index.md) `00-how-ai-gateway-works` (Beginner, 20 min · Portal): A 20-minute visual tour of Azure AI Gateway. Follow one request through the gateway, meet models, aliases, MCP servers, policies, and identities, and pick the learning path that fits your role.
- **01** [Provision your AI Gateway](https://azure.github.io/aigateway/labs/01-provision-gateway/index.md) `01-provision-gateway` (Beginner, 15 min · Portal, CLI, Bicep, Notebook): Create the shared Azure AI Gateway that your apps and agents will call, from the AI Gateway portal, the Azure CLI, or Bicep and azd, then take a guided tour of the portal.
- **02** [Publish a Foundry model and make your first call](https://azure.github.io/aigateway/labs/02-first-model-call/index.md) `02-first-model-call` (Beginner, 25 min · Portal, CLI, Bicep, Code, Notebook · needs 01): Publish a Microsoft Foundry model deployment through your gateway with its managed identity, create a runtime API key, try the model in the Catalog playground, and call it from curl, PowerShell, Python, TypeScript, and C#.

### Models & routing

- **03** [Publish models from any provider behind stable aliases](https://azure.github.io/aigateway/labs/03-multi-provider-aliases/index.md) `03-multi-provider-aliases` (Intermediate, 30 min · Portal, CLI, Bicep · needs 02): Connect Anthropic or another non-Azure provider with a credential that stays in the gateway, publish its models behind callable aliases, call Claude with the native Messages API, and retarget an alias to a different backend model without changing a single client.
- **22** [Route an alias across models by priority and weight](https://azure.github.io/aigateway/labs/22-model-routing/index.md) `22-model-routing` (Intermediate, 25 min · Portal, CLI, Bicep · needs 02): Put two Foundry models behind one alias, canary a new model version with an 80/20 weighted split, then prefer one model by priority, all without changing the model name that clients send.
- **23** [Stream responses and count every token](https://azure.github.io/aigateway/labs/23-streaming-responses/index.md) `23-streaming-responses` (Intermediate, 20 min · CLI, Code, Portal, Bicep, Notebook · needs 02): Stream Chat Completions and Responses API replies through the gateway, read the server-sent events that your client receives, and prove that a token limit counts streamed tokens even when the client never asks for usage.

### MCP & tools

- **04** [Federate MCP tools behind one endpoint](https://azure.github.io/aigateway/labs/04-federate-mcp-tools/index.md) `04-federate-mcp-tools` (Beginner, 30 min · Portal, CLI, Bicep, Code, Notebook · needs 01): Register a remote MCP server in Azure AI Gateway, add a second backend under its own namespace, and connect curl, VS Code, and Python to one governed MCP endpoint.
- **05** [Control which tools agents can call](https://azure.github.io/aigateway/labs/05-mcp-tool-controls/index.md) `05-mcp-tool-controls` (Intermediate, 20 min · Portal, CLI, Bicep · needs 04): Publish only approved MCP tools with name patterns, block risky tools, take a whole MCP server offline, and cap tool traffic per caller with a request rate limit.

### Governance & cost

- **06** [Throttle tokens per caller with token limits](https://azure.github.io/aigateway/labs/06-token-limits/index.md) `06-token-limits` (Beginner, 25 min · Portal, CLI, REST, Bicep, Notebook · needs 02): Cap how many tokens each app, agent, or user can consume per minute, hour, or day, and watch the gateway answer with 429 and Retry-After before your backend capacity runs out.
- **07** [Enforce cost budgets with per-caller overrides](https://azure.github.io/aigateway/labs/07-cost-budgets/index.md) `07-cost-budgets` (Intermediate, 30 min · Portal, CLI, Bicep, Notebook · needs 06, 10): Give every app, agent, and user a dollar budget per hour, day, or month, raise or lower it for specific API keys and Microsoft Entra identities, and watch the gateway answer 403 LlmCostQuotaExceeded once a caller's estimated spend runs out.
- **08** [Screen prompts and responses with content safety](https://azure.github.io/aigateway/labs/08-content-safety/index.md) `08-content-safety` (Beginner, 20 min · Portal, CLI, REST, Bicep · needs 02): Add a content safety policy that screens prompts, tool inputs, and responses for hate, self-harm, sexual, and violent content, tune each category's threshold, and see how blocked calls return 400.
- **09** [Set gateway-wide policy baselines](https://azure.github.io/aigateway/labs/09-gateway-baselines/index.md) `09-gateway-baselines` (Intermediate, 25 min · Portal, CLI, Bicep · needs 06, 08): Apply a baseline of token limit, request rate limit, content safety, and IP filter policies at Gateway scope so every model and MCP server, including the ones you add later, starts with the same guardrails, then layer stricter asset policies on top.

### Security & identity

- **10** [Issue and rotate runtime API keys](https://azure.github.io/aigateway/labs/10-api-keys/index.md) `10-api-keys` (Beginner, 15 min · Portal, CLI, Bicep · needs 01): Give every app its own runtime API key, keep the value out of your code, rotate it without downtime with the primary and secondary values, revoke a leaked key, and see usage and cost per key in Monitoring.
- **11** [Go keyless with Microsoft Entra ID and RBAC](https://azure.github.io/aigateway/labs/11-entra-rbac/index.md) `11-entra-rbac` (Intermediate, 35 min · Portal, CLI, Bicep, Code, Notebook · needs 02): Replace shared gateway API keys with Microsoft Entra ID tokens. Grant users, groups, apps, and managed identities an AI Gateway data-plane role at the gateway, a model alias, or an MCP server, then call models from the playground, curl, Python, TypeScript, and C# with no secret in code.
- **12** [Call backends with managed identities](https://azure.github.io/aigateway/labs/12-backend-identity/index.md) `12-backend-identity` (Intermediate, 20 min · Portal, CLI, Bicep · needs 02): Let the gateway reach Microsoft Foundry with a managed identity instead of stored keys. Check the system-assigned identity, then create a user-assigned identity you can share across gateways, grant it Foundry User, attach it, and point a model provider at it from the portal, the Azure CLI, or Bicep.

### Observability & FinOps

- **13** [Monitor usage, cost, and traces](https://azure.github.io/aigateway/labs/13-monitoring/index.md) `13-monitoring` (Beginner, 25 min · Portal, CLI, Bicep · needs 02): Send the gateway's OpenTelemetry metrics, logs, and traces to Application Insights, then use the built-in Monitoring dashboard to see usage, estimated cost per model and API key, policy impact, and gateway-aware traces.
- **14** [Attribute tokens and cost with OpenTelemetry](https://azure.github.io/aigateway/labs/14-otel-chargeback/index.md) `14-otel-chargeback` (Advanced, 35 min · Portal, CLI, Bicep · needs 13, 11): Export Microsoft Entra token claims with the gateway's logs, traces, and token metrics, then turn observed tokens into a per-tenant, per-app, and per-key chargeback report with KQL, PromQL, and a small Python script.

### Agents

- **15** [Connect agent frameworks to models and tools](https://azure.github.io/aigateway/labs/15-agent-frameworks/index.md) `15-agent-frameworks` (Intermediate, 30 min · Code, Notebook · needs 02, 04): Point Microsoft Agent Framework, the OpenAI Agents SDK, and LangChain with LangGraph at the gateway's OpenAI-compatible model endpoint and its MCP endpoint, so every model and tool call an agent makes passes through gateway policies and shows up in Monitoring.
- **16** [Deploy a Foundry hosted agent behind AI Gateway](https://azure.github.io/aigateway/labs/16-foundry-hosted-agent/index.md) `16-foundry-hosted-agent` (Intermediate, 45 min · Portal, CLI, Code, Notebook · needs 02, 04): Deploy your own Microsoft Agent Framework agent to Foundry Hosted Agents with azd. The agent has no model deployment, no direct tool access, and no keys. It calls its model through AI Gateway with its own Microsoft Entra Agent ID, and reaches the Microsoft Learn MCP server through a Foundry toolbox that signs in with the project's managed identity. Run it locally, invoke it in Foundry, and cap its tokens without changing its code.
- **17** [Build on your gateway with coding agents](https://azure.github.io/aigateway/labs/17-coding-agent-plugin/index.md) `17-coding-agent-plugin` (Beginner, 15 min · Code, Notebook · needs 02): Install the AI Gateway plugin in GitHub Copilot CLI, Claude Code, Cursor, or Gemini CLI, then let your coding agent discover the gateway's models and MCP tools and generate working client code.
- **24** [Use your gateway's models and tools in GitHub Copilot](https://azure.github.io/aigateway/labs/24-github-copilot-byok/index.md) `24-github-copilot-byok` (Intermediate, 40 min · Portal, CLI, Bicep, Code, Notebook · needs 02): Point GitHub Copilot in VS Code, the Copilot CLI, the Copilot SDK, and the GitHub Copilot app at gpt-6.1-sol published by your gateway, then give them Microsoft Learn tools from an MCP server on the same gateway, so every model and tool call uses your key, your limits, and your monitoring.

### Production & emerging

- **18** [Lock down backend traffic with private networking](https://azure.github.io/aigateway/labs/18-private-networking/index.md) `18-private-networking` (Advanced, 45 min · Portal, CLI, Bicep · needs 01, 12): Create an Azure AI Gateway with private routing through your virtual network, reach a Foundry backend over a private endpoint with its public access turned off, and learn which inbound options aren't available yet.
- **19** [Protect tool calls with Agent 365 threat protection](https://azure.github.io/aigateway/labs/19-tool-threat-protection/index.md) `19-tool-threat-protection` (Advanced, 30 min · Portal, Bicep · needs 04, 11): Have Microsoft Defender and Microsoft Purview evaluate every tool call on an MCP server, before the tool runs, after it returns, or both, and see how a fail-closed denial reaches the caller.
- **20** [Govern MCP servers with Agent 365](https://azure.github.io/aigateway/labs/20-agent-365-governance/index.md) `20-agent-365-governance` (Intermediate, 20 min · Portal · needs 04, 05): Connect Microsoft Agent 365 to your gateways, find their MCP servers in one inventory, block a single tool or a whole server from the Microsoft 365 admin center, and see exactly what agents get back.
- **21** [Deploy an enterprise reference architecture](https://azure.github.io/aigateway/labs/21-enterprise-reference/index.md) `21-enterprise-reference` (Advanced, 60 min · Bicep · needs 09, 13, 12): Deploy a production-shaped Azure AI Gateway environment from modular Bicep, with a keyless Foundry backend, models and MCP tools behind RBAC, a key per app, layered policies, and monitoring. Then promote it from dev to prod with a GitHub Actions workflow that signs in with OpenID Connect and smoke-tests every deployment.
<!-- gh:end -->

## Learning paths

<!-- gh:begin paths: generated by "npm run sync" from the metadata, do not edit -->
| Path | For | Labs, in order |
| :-- | :-- | :-- |
| 30-minute essentials | Everyone | 00 → 01 → 02 → 04 |
| Platform engineer | Build the shared AI platform | 01 → 02 → 03 → 22 → 04 → 09 → 12 → 18 → 21 |
| App & agent developer | Ship apps and agents on governed endpoints | 02 → 03 → 22 → 23 → 04 → 15 → 16 → 17 → 24 |
| Security & compliance | Protect data, identities, and tools | 10 → 11 → 08 → 05 → 09 → 19 → 20 |
| FinOps & operations | Control spend and run the gateway | 06 → 23 → 07 → 13 → 14 |
<!-- gh:end -->

## Use-case map

<!-- gh:begin usecases: generated by "npm run sync" from the metadata, do not edit -->
| Use case | Start with |
| :-- | :-- |
| One endpoint for every model: Foundry, Azure OpenAI, OpenAI, Anthropic, Bedrock, and Vertex AI behind stable aliases | 03 Multi-provider aliases |
| Priority & weighted routing: Canary a new model, run A/B tests, or prefer purchased capacity behind one alias | 22 Priority & weighted routing |
| Token limits & quotas: Cap tokens per minute, hour, or day for each caller | 06 Token limits |
| Budgets & cost control: Dollar budgets per key, per Entra identity, or across the gateway | 07 Cost budgets |
| Federated MCP tools: One governed MCP endpoint for remote servers, APIs, and connectors | 04 Federate MCP tools |
| Keyless access with Entra ID: RBAC for users, apps, and managed identities down to a single alias | 11 Entra ID & RBAC |
| Observability & tracing: Tokens, cost, outcomes, and policy spans in one dashboard | 13 Monitoring |
| Content safety: Screen prompts, tool inputs, and responses before they reach a backend | 08 Content safety |
| Agent frameworks & hosted agents: Route every model and tool call an agent makes through one control point | 16 Foundry hosted agent |
| Tool allow and block lists: Expose only approved tools with exact lists and patterns | 05 Tool allow & block lists |
| Chargeback with token claims: Attribute tokens and cost to tenants, apps, and cost centers | 14 OpenTelemetry chargeback |
| Tool threat protection: Defender and Purview evaluate tool calls for injection and data risk | 19 Tool threat protection |
| Agent 365 governance: Inventory and block MCP servers and tools from the Microsoft 365 admin center | 20 Agent 365 governance |
| Coding-agent plugin: Let Copilot, Claude Code, Cursor, or Gemini build on your gateway | 17 Coding-agent plugin |
| GitHub Copilot on your models and tools: Run Copilot in VS Code, the CLI, the SDK, and the app on models and MCP tools your gateway governs | 24 GitHub Copilot BYOK |
| Streaming with accurate usage: Stream replies token by token while limits, budgets, and monitoring count every token | 23 Streaming responses |
<!-- gh:end -->

## Notebooks

The notebooks share one gateway, so run lab 01, then lab 02, then any other notebook. Each one deploys its lab's
Bicep files (`labs/<slug>/infra/*.bicep`) with `az deployment group create`, through the shared helpers in
`labs/shared/utils.py`, so run it from its lab folder in a clone. They need Python 3.10 or later and `az login`, and
the first cell installs the packages they use. These defaults can be overridden with environment variables before
the kernel starts:

| Setting | Default | Environment variable |
| :-- | :-- | :-- |
| Resource group | `rg-ai-gateway-labs` | `AIGW_RESOURCE_GROUP` |
| Gateway name | `aigw-labs-` plus 6 characters of the SHA-1 of the subscription ID | `AIGW_GATEWAY_NAME` |
| Region | `eastus2` | `AIGW_LOCATION` |
| Foundry account for lab 02 | `aigwlabs` plus 8 characters of the same hash, created by the notebook | `AIGW_FOUNDRY_ACCOUNT` |
| Foundry account's resource group | the labs resource group | `AIGW_FOUNDRY_RESOURCE_GROUP` |

To run a notebook headless, `cd labs/<slug>` and use
`jupyter nbconvert --to notebook --execute <slug>.ipynb --output <copy>.ipynb`. Each notebook ends with a
**Clean up** step.

## Change or add a lab

In a clone of `Azure/aigateway`, edit only `labs/<slug>/README.md`, following `labs/AUTHORING.md`. Then run
`npm run sync` and `npm run check` in `labs/`. Never edit `docs/` or the generated `<!-- gh:begin -->` regions by
hand. `npm run sync` also regenerates the catalog, paths, and use-case map in this skill.

When the user asks to update the labs for new product releases, follow the "Update the labs" workflow in the
repository's `AGENTS.md`: `npm run releases` lists the product releases that `labs/RELEASE-NOTES.md` doesn't cover
yet.

## Related skill

For a developer who only wants to call the models and MCP tools of an existing gateway from an app, use the
`use-ai-gateway` skill in `skills/use-ai-gateway` of the same repository.
