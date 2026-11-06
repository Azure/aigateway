# Azure AI Gateway

**One gateway for every model and tool.**
[Azure AI Gateway](https://learn.microsoft.com/azure/ai-gateway/overview) is a managed gateway for AI traffic: requests to AI models and
Model Context Protocol (MCP) servers. It gives developers one familiar way to call model APIs and MCP tools, while
platform teams enforce security, policy, networking, and observability.

- **Govern model APIs** — Microsoft Foundry, OpenAI, Anthropic, Google Vertex, and more, while developers keep the SDKs they already use.
- **Federate MCP tools** — combine MCP servers, OpenAPI APIs, and SaaS connectors behind one governed MCP endpoint.
- **Enforce AI policies** — access, content safety, token, and rate controls, globally or per model and tool.
- **Observe AI traffic** — token usage, latency, errors, and policy outcomes in dashboards and logs.
- **Run on a trusted platform** — built on the Azure API Management gateway foundation, with Private Link, virtual network integration, and managed identity.

> See the **[AI Gateway documentation](https://aka.ms/aigateway/docs)** to get started.

---

## Hands-on labs

**[Browse the labs → azure.github.io/aigateway](https://azure.github.io/aigateway/)**

26 step-by-step labs for customers and field teams. They start with the core AI gateway use cases (publishing
models behind aliases, priority and weighted model routing, federating MCP tools, token limits and cost budgets,
content safety, keys and Entra ID, monitoring, and chargeback) and continue to emerging ones (streaming with accurate token counts, agent frameworks, Foundry hosted agents, coding agents,
GitHub Copilot with your own models, Agent 365, private networking, and an enterprise reference architecture). Each lab has portal, Azure CLI, Bicep, or
code tracks, so you can follow it in the way that fits how you work: on the labs site, directly on GitHub, or
in a Jupyter notebook.

**[Start the 5-minute quick start](labs/quickstart/README.md)** · **[Follow the labs on GitHub](labs/README.md)** ·
**[Run the notebooks](labs/README.md#run-the-notebooks)** · **[Use them with a coding agent](labs/README.md#use-the-labs-with-a-coding-agent)** ·
**[What's new](labs/RELEASE-NOTES.md)** · **[Contribute a lab](labs/AUTHORING.md)**

## Azure CLI

Create and manage gateways, model registrations, MCP servers, and policies with
`az aigateway`. See the **[CLI installation and quickstart](cli/README.md)** for
one-line Bash and PowerShell installers, or browse the
[command reference](cli/command-reference.md).

## Coding-agent plugin

This repository hosts the official **plugin** for coding agents. It helps
developers **build applications on top of an existing Azure AI Gateway**: it discovers the
models and MCP tool servers registered in a gateway and integrates them into whatever
you're building — call a model over the OpenAI-compatible passthrough, connect MCP
tools, or scaffold a runnable agent — all from your coding agent.

The plugin follows the [Claude Code plugin spec](https://code.claude.com/docs/en/plugins),
the [GitHub Copilot / awesome-copilot plugin convention](https://github.com/github/awesome-copilot/blob/main/CONTRIBUTING.md#adding-plugins),
the [Cursor plugin format](https://cursor.com/docs/plugins), and the
[Gemini CLI extension format](https://geminicli.com/docs/extensions/), so it installs
in any of those coding agents (and other agents that support the plugin standard).

> **Consumption only.** The plugin is read-only against the gateway — it never
> provisions, updates, or deletes resources. Creating gateways, models, or tools
> is an administrator task done in the [AI Gateway Portal](https://ai.gateway.azure.com).

### What's inside

| Component | Invoked as | Purpose |
| --------- | ---------- | ------- |
| Skill `use-ai-gateway` | `/ai-gateway:use-ai-gateway` | Full discover → select → credential → integrate workflow (call a model, connect MCP tools, or scaffold an agent). |
| Command `discover` | `/ai-gateway:discover` | Read-only: list a gateway's models and MCP tool servers and pick the ones that fit your use case. |
| Command `build` | `/ai-gateway:build` | End-to-end: discover, retrieve a credential, and integrate the models/tools into your app. |

### Install

The plugin is hosted in this repository, so your coding agent can install it
directly from Git — no manual file downloads. Pick the tab for your agent:

**Claude Code / GitHub Copilot CLI** (plugin marketplace protocol):

```
/plugin marketplace add Azure/aigateway
/plugin install ai-gateway@azure
```

**Cursor** — add this repository as a team marketplace from **Dashboard → Plugins →
Add Marketplace → Import from Repo** (`https://github.com/Azure/aigateway`), then
install **ai-gateway** from **Customize**. For local testing, symlink the repo into
`~/.cursor/plugins/local/ai-gateway` and reload the window.

**Gemini CLI**:

```
gemini extensions install https://github.com/Azure/aigateway
```

### Usage

Point the plugin at your gateway's **ARM resource id** (required to list its models and
tools) and describe what you want to build:

```
/ai-gateway:build /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway> a service that summarizes support tickets
```

Or explore first, then integrate:

```
/ai-gateway:discover /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway>
```

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
samples and infrastructure that build on Azure AI Gateway.

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
