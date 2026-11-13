# Azure AI Gateway

**One gateway for every model and tool.**

[![Docs](https://img.shields.io/badge/docs-aka.ms%2Faigateway%2Fdocs-0078D4)](https://aka.ms/aigateway/docs)
[![az aigateway](https://img.shields.io/badge/az_aigateway-public_preview-5C2D91)](cli/README.md)
[![Labs](https://img.shields.io/badge/labs-26-107C10)](https://azure.github.io/aigateway/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[Azure AI Gateway](https://learn.microsoft.com/azure/ai-gateway/overview) is a managed gateway for AI traffic:
requests to AI models and Model Context Protocol (MCP) servers. Developers keep the SDKs they already use, while
platform teams enforce security, policy, networking, and observability in one place.

- **Govern model APIs** from Microsoft Foundry, OpenAI, Anthropic, Google Vertex, and more.
- **Federate MCP tools** — MCP servers, OpenAPI APIs, and SaaS connectors behind one governed MCP endpoint.
- **Enforce AI policies** for access, content safety, tokens, and rate limits, globally or per model and tool.
- **Observe AI traffic**: token usage, latency, errors, and policy outcomes in dashboards and logs.
- **Run on a trusted platform** — the Azure API Management gateway foundation, with Private Link, virtual
  network integration, and managed identity.

> [!TIP]
> New to the service? Start with the **[AI Gateway documentation](https://aka.ms/aigateway/docs)**.

This repository holds the tooling around it:

| Component | What it is |
| --------- | ---------- |
| **[Azure CLI extension](#azure-cli)** | `az aigateway`: create and operate gateways from your shell. |
| **[Coding-agent plugin](#coding-agent-plugin)** | `/aigateway:*` commands and skills for Claude Code, GitHub Copilot CLI, Cursor, and Gemini CLI. |
| **[Hands-on labs](#labs-samples-and-support)** | 26 step-by-step labs, published as a site, on GitHub, and as notebooks. |
| **[Samples catalog](samples/README.md)** | End-to-end samples and infrastructure built on AI Gateway. |

## Azure CLI

`az aigateway` (shorthand `az aig`) creates gateways and manages model providers, models and aliases, MCP
servers, policies, identities, networking, and client keys. It ships as a published Azure CLI extension and is
in **public preview**.

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75.0 or later, then:

**Bash**

```bash
curl -fsSL https://aka.ms/aigateway-cli-install -o install.sh
sh install.sh
az aigateway version
```

**PowerShell**

```powershell
Invoke-WebRequest https://aka.ms/aigateway-cli-install-ps -OutFile install.ps1
./install.ps1
az aigateway version
```

The installers download a pinned wheel and verify its SHA-256 before installing. To install a newer preview
release, or to download and check the wheel yourself, follow the
**[installation guide](cli/README.md)** — and never substitute a source build or an installer copied from an
older release.

Create a gateway and confirm it provisioned:

```bash
az aigateway create --subscription "$SUBSCRIPTION" -g "$RG" -n "$GATEWAY" --location "$LOCATION"
az aigateway show --subscription "$SUBSCRIPTION" -g "$RG" -n "$GATEWAY" -o json
```

Register providers and models, publish aliases, and add MCP servers: every command group has an example in the **[searchable command reference](cli/command-reference.md)**.

## Coding-agent plugin

The official plugin for coding agents, for two personas:

- **Developers** discover the models and MCP tool servers in an existing gateway and integrate them into an app.
- **Administrators and platform engineers** create, configure, and operate gateways, and migrate AI workloads onto them.

### Install

**Claude Code / GitHub Copilot CLI**

```
/plugin marketplace add Azure/aigateway
/plugin install aigateway@azure
```

**Gemini CLI**

```
gemini extensions install https://github.com/Azure/aigateway
```

**Cursor** — add this repository as a team marketplace from **Dashboard → Plugins → Add Marketplace → Import
from Repo** (`https://github.com/Azure/aigateway`), then install **aigateway** from **Customize**.

### Commands

| Command | What it does | Skill |
| ------- | ------------ | ----- |
| `/aigateway:discover <gateway-resource-id>` | Read-only: list a gateway's model aliases and MCP tool servers. | [`use-ai-gateway`](skills/use-ai-gateway/SKILL.md) |
| `/aigateway:build <gateway-resource-id> <use case>` | Discover, retrieve a credential, and wire the models and tools into your app. | [`use-ai-gateway`](skills/use-ai-gateway/SKILL.md) |
| `/aigateway:create <gateway> <resource-group> <region>` | Create a gateway and verify that it is ready to configure. | [`manage-ai-gateway`](skills/manage-ai-gateway/SKILL.md) |
| `/aigateway:manage <gateway> <resource-group> <operation>` | Configure and operate a gateway and its assets. | [`manage-ai-gateway`](skills/manage-ai-gateway/SKILL.md) |
| `/aigateway:migrate <apim-name> <resource-group>` | Inventory an API Management instance, plan the move, settle it with you, then provision phase by phase. | [`migrate-apim`](skills/migrate-apim/SKILL.md) |
| `/aigateway:feedback` | Package one agent session into a local ZIP that you choose how to share. | [`feedback-ai-gateway`](skills/feedback-ai-gateway/SKILL.md) |

A gateway's **ARM resource id** is what the developer commands need to list its models and tools:

```
/aigateway:discover /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway>
/aigateway:build    /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway> a service that summarizes support tickets
/aigateway:create   my-gateway my-resource-group eastus2
/aigateway:manage   my-gateway my-resource-group add a Foundry model provider
/aigateway:migrate  my-apim-instance my-resource-group
```

## Labs, samples, and support

- **[Hands-on labs](labs/README.md)** — 26 step-by-step labs for customers and field teams, from the core use
  cases (aliases, priority and weighted routing, federated MCP tools, token limits and budgets, content safety,
  keys and Entra ID, monitoring, chargeback) to emerging ones (streaming token counts, agent frameworks, coding
  agents, Agent 365, private networking, an enterprise reference architecture). Each has portal, CLI, REST,
  Bicep, or code tracks. Follow them on the **[labs site](https://azure.github.io/aigateway/)**, here on GitHub,
  or as [Jupyter notebooks](labs/README.md#run-the-notebooks) — or
  [with a coding agent](labs/README.md#use-the-labs-with-a-coding-agent).
  Shortcuts: [5-minute quick start](labs/quickstart/README.md) ·
  [what's new](labs/RELEASE-NOTES.md) · [contribute a lab](labs/AUTHORING.md).
- **[Samples catalog](samples/README.md)** — end-to-end samples and infrastructure that build on AI Gateway.
- **[Product documentation](https://aka.ms/aigateway/docs)** — concepts, how-to guides, and the release changelog.
- **[Support](SUPPORT.md)** for questions and bugs. Report vulnerabilities through
  [Security](SECURITY.md), never a public issue.

## Contributing

Contributions and suggestions are welcome. Most require you to agree to a
[Contributor License Agreement](https://cla.opensource.microsoft.com); a CLA bot decorates your pull request
with what to do, and you only do it once across all repositories that use it. Labs have their own
[authoring guide](labs/AUTHORING.md), and coding agents working here should read [AGENTS.md](AGENTS.md).

This project has adopted the [Microsoft Open Source Code of Conduct](CODE_OF_CONDUCT.md). See the
[FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact
[opencode@microsoft.com](mailto:opencode@microsoft.com) with any questions.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply
Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.
