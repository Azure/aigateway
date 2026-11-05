# AI Gateway tier in Azure API Management

**One gateway for every model and tool.**
[AI Gateway tier in Azure API Management](https://aka.ms/aigateway/docs) is the AI-focused tier of Azure API
Management. It gives developers one familiar way to call model APIs and MCP tools, while
platform teams enforce security, policy, networking, and observability.

- **Govern model APIs** — Microsoft Foundry, OpenAI, Anthropic, Google Vertex, and more, while developers keep the SDKs they already use.
- **Federate MCP tools** — combine MCP servers, OpenAPI APIs, and SaaS connectors behind one governed MCP endpoint.
- **Enforce AI policies** — access, content safety, token, and rate controls, globally or per model and tool.
- **Observe AI traffic** — token usage, latency, errors, and policy outcomes in dashboards and logs.
- **Run on a trusted platform** — the Azure API Management platform, with Private Link, virtual network integration, and managed identity.

> AI Gateway is in **public preview**, available free of charge. See the **[documentation](https://aka.ms/aigateway/docs)** to get started.

---

## Azure CLI

Create and manage gateways, model registrations, MCP servers, and policies with
`az aigateway`. The CLI is an external dependency published in **[Azure/aigateway](https://github.com/Azure/aigateway)**.
See its **[current installation and quickstart](https://github.com/Azure/aigateway/tree/main/cli)** for
one-line Bash and PowerShell installers, or browse the
[current command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md).
Use the latest published CLI, including preview releases, rather than a local
source build or an installer copied from an older release.

## Coding-agent plugin

This repository hosts the official **plugin** for coding agents. It supports two
personas:

- **Administrators and platform engineers** can create and operate gateways
  and configure their assets with the current `az aigateway` CLI.
- **Developers** can discover the models and MCP tool servers in an existing
  gateway and integrate them into an application.

The plugin follows the [Claude Code plugin spec](https://code.claude.com/docs/en/plugins),
the [GitHub Copilot / awesome-copilot plugin convention](https://github.com/github/awesome-copilot/blob/main/CONTRIBUTING.md#adding-plugins),
the [Cursor plugin format](https://cursor.com/docs/plugins), and the
[Gemini CLI extension format](https://geminicli.com/docs/extensions/), so it installs
in any of those coding agents (and other agents that support the plugin standard).

> **Separate administrator and developer workflows.** Discover and build remain
> read-only against the gateway. Create and manage require an authorized
> administrator and approval before mutations. APIM migration uses additional
> local helpers, capability checks, and explicit per-item approval.

### What's inside

| Component | Invoked as | Purpose |
| --------- | ---------- | ------- |
| Skill `use-ai-gateway` | `/ai-gateway:use-ai-gateway` | Full discover → select → credential → integrate workflow (call a model, connect MCP tools, or scaffold an agent). |
| Skill `manage-ai-gateway` | `/ai-gateway:manage-ai-gateway` | Full administrator workflow for creating, configuring, and operating a gateway. |
| Skill `migrate-ai-gateway` | `/ai-gateway:migrate-ai-gateway` | Inventory, assess, validate, and reconcile supported APIM V2 configuration with explicit approval. |
| Command `discover` | `/ai-gateway:discover` | Read-only: list a gateway's models and MCP tool servers and pick the ones that fit your use case. |
| Command `build` | `/ai-gateway:build` | End-to-end: discover, retrieve a credential, and integrate the models/tools into your app. |
| Command `create` | `/ai-gateway:create` | Create a gateway and verify that it is ready for configuration. |
| Command `manage` | `/ai-gateway:manage` | Configure and operate a gateway, rotate keys, or maintain assets. |
| Command `migrate` | `/ai-gateway:migrate` | Run the assisted, capability-gated APIM V2 migration workflow or resume its verified state. |

### Install

The plugin is hosted in this repository, so your coding agent can install it
directly from Git — no manual file downloads. Pick the tab for your agent:

**Claude Code / GitHub Copilot CLI** (plugin marketplace protocol):

```
/plugin marketplace add Azure/ai-gateway
/plugin install ai-gateway@azure
```

**Cursor** — add this repository as a team marketplace from **Dashboard → Plugins →
Add Marketplace → Import from Repo** (`https://github.com/Azure/ai-gateway`), then
install **ai-gateway** from **Customize**. For local testing, symlink the repo into
`~/.cursor/plugins/local/ai-gateway` and reload the window.

**Gemini CLI**:

```
gemini extensions install https://github.com/Azure/ai-gateway
```

### Usage

Point the plugin at your gateway's **ARM resource id** (required to list its models and
tools) and describe what you want to build:

```
/ai-gateway:build /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/service/<gateway> a service that summarizes support tickets
```

Or explore first, then integrate:

```
/ai-gateway:discover /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/service/<gateway>
```

Administrators can create a gateway or manage an existing one:

```
/ai-gateway:create my-gateway my-resource-group eastus2
/ai-gateway:manage my-gateway my-resource-group add a Foundry model provider
```

Administrators can assess and migrate supported APIM V2 configuration:

```
/ai-gateway:migrate /subscriptions/<sub>/resourceGroups/<source-rg>/providers/Microsoft.ApiManagement/service/<source-apim>
```

A source-only invocation assesses feasibility without requiring a destination.
The assessment gives evidence-based per-component conclusions and asks specific
questions when missing facts affect the verdict, rather than leaving generic
"confirmation needed" items. It inventories AI traffic first, then assesses
migrating all discovered AI APIs or a feasible subset. Any scope question comes
after inventory when needed; an already-specified subset is preserved.
Traditional APIs remain on APIM except where their behavior is needed by AI
traffic. This is not an assessment of replacing the entire APIM instance, and
no feasibility conclusion authorizes deployment.

For destination-bound planning, supply a target:

```
/ai-gateway:migrate /subscriptions/<sub>/resourceGroups/<source-rg>/providers/Microsoft.ApiManagement/service/<source-apim> my-ai-gateway my-target-rg eastus2
```

The [migration skill](skills/migrate-ai-gateway/SKILL.md) bundles Python helpers
for read-only source inventory, redaction, capability evidence, deterministic plan
validation, approved reconciliation, verification, and resume. The native
`az aigateway` CLI performs supported destination operations; it is not an APIM
bulk-import tool. Install the helper's isolated dependencies as described in the
skill. BasicV2, StandardV2, and PremiumV2 sources are initially enabled; classic
V1 and AIGateway source profiles are reserved for later expansion.

Approved local APIOps and conservative ARM-template evidence can supplement
incomplete discovery. Unsupported behavior remains an explicit question or
residual, never an implicit approximation. Each mutation needs current-plan
approval; resource read-back and source-behavior verification are separate.
Version-3 state uses protected immutable generations under
`.ai-gateway-migration/`. Legacy checkpoints are preserved read-only, not
automatically resumed. See the [state schemas](skills/migrate-ai-gateway/schemas/).

### Security

The generated code authenticates the model passthrough and the MCP tool servers
with a gateway **API key**, read from an environment variable
(`AI_GATEWAY_API_KEY`) and never hardcoded. Scaffolded projects keep `.env` out of
source control. If a key is ever exposed, rotate it in the [AI Gateway Portal](https://ai.gateway.azure.com).

Standalone agent scaffolds use least-privilege tool configuration: only explicitly
selected MCP tools are made available, and permission-requiring operations require
an explicit user decision. Generated applications do not automatically approve
tool requests. Review each requested operation and grant the application and its
gateway credentials only the permissions it needs.

To report a security issue, see [SECURITY.md](SECURITY.md).

## Samples

Looking for working examples? The [samples catalog](samples/README.md) curates end-to-end
samples and infrastructure that build on the AI Gateway tier in Azure API Management.

## Contributing

This project welcomes contributions and suggestions. Most contributions require you
to agree to a Contributor License Agreement (CLA) declaring that you have the right
to, and actually do, grant us the rights to use your contribution. For details,
visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you
need to provide a CLA and decorate the PR appropriately (e.g., status check,
comment). Simply follow the instructions provided by the bot. You will only need to
do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any
additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services.
Authorized use of Microsoft trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not
cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or
logos are subject to those third-party's policies.
