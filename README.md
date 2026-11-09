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
`az aigateway`. Install the published Azure CLI extension using the
**[installation guide and quickstart](cli/README.md)** for Bash or PowerShell,
or browse the [searchable command reference](cli/command-reference.md).
Use the latest published CLI, including preview releases, rather than a local
source build or an installer copied from an older release.

## Coding-agent plugin

This repository hosts the official **plugin** for coding agents. It supports two
personas:

- **Administrators and platform engineers** can create and operate gateways
  and configure their assets with the current `az aigateway` CLI.
- **Developers** can discover the models and MCP tool servers in an existing
  gateway and integrate them into an application.

### What's inside

| Component | Invoked as | Purpose |
| --------- | ---------- | ------- |
| Command `discover` | `/aigateway:discover` | Read-only: list a gateway's models and MCP tool servers and pick the ones that fit your use case. |
| Command `build` | `/aigateway:build` | End-to-end: discover, retrieve a credential, and integrate the models/tools into your app. |
| Command `create` | `/aigateway:create` | Create a gateway and verify that it is ready for configuration. |
| Command `manage` | `/aigateway:manage` | Configure and operate a gateway and its assets. |
| Command `migrate` | `/aigateway:migrate` | Run the assisted, capability-gated APIM V2 migration workflow or resume its verified state. |
| Command `feedback` | `/aigateway:feedback` | Package one selected agent session into a local ZIP for user-controlled sharing; anonymization and review are mandatory for GitHub issues. |
| Skill `use-ai-gateway` | `/aigateway:use-ai-gateway` | Use AI assets from Azure AI Gateway to build intelligent applications. |
| Skill `manage-ai-gateway` | `/aigateway:manage-ai-gateway` | Full administrator workflow for creating, configuring, and operating a gateway. |
| Skill `migrate-ai-gateway` | `/aigateway:migrate-ai-gateway` | Inventory, assess, validate, and reconcile supported APIM V2 configuration to move the workload to Azure AI Gateway. |

### Install

The plugin is hosted in this repository, so your coding agent can install it
directly from Git — no manual file downloads. Pick the tab for your agent:

**Claude Code / GitHub Copilot CLI** (plugin marketplace protocol):

```
/plugin marketplace add Azure/aigateway
/plugin install aigateway@azure
```

**Cursor** — add this repository as a team marketplace from **Dashboard → Plugins →
Add Marketplace → Import from Repo** (`https://github.com/Azure/aigateway`), then
install **aigateway** from **Customize**. For local testing, symlink the repo into
`~/.cursor/plugins/local/aigateway` and reload the window.

**Gemini CLI**:

```
gemini extensions install https://github.com/Azure/aigateway
```

### Usage

Point the plugin at your gateway's **ARM resource id** (required to list its models and
tools) and describe what you want to build:

```
/aigateway:build /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway> a service that summarizes support tickets
```

Or explore first, then integrate:

```
/aigateway:discover /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ApiManagement/aigateways/<gateway>
```

#### Manage

Administrators can create a gateway or manage an existing one:

```
/aigateway:create my-gateway my-resource-group eastus2
/aigateway:manage my-gateway my-resource-group add a Foundry model provider
```

The [administrator skill](skills/manage-ai-gateway/SKILL.md) provides native CLI
runbooks for gateway lifecycle, models and aliases, MCP sources, policies, keys,
identities, networking, and telemetry. It manages only
`Microsoft.ApiManagement/aigateways` and its own children; external resources and
role grants must already be prepared. Routine create/update intent authorizes the
requested work; destructive, access-sensitive, and secret-related operations have
specific confirmation gates. [Portal activity coverage and CLI gaps](skills/manage-ai-gateway/references/activities-and-cli-coverage.md)
are explicit rather than bypassed with REST or legacy resource types.

#### Migrate workloads to Azure AI Gateway

Administrators can assess and migrate supported APIM V2 configuration to Azure AI Gateway:

```
/aigateway:migrate /subscriptions/.../Microsoft.ApiManagement/aigateways/<source-apim>
```

The assessment inventories AI assets first, then assesses
migrating all discovered AI APIs or a feasible subset.

#### Share feedback

Send a coding-agent session for feedback to the product team:

```
/aigateway:feedback
```

The [feedback skill](skills/feedback-ai-gateway/SKILL.md) packages your selected
session and approved diagnostics into a **local ZIP**. Nothing is uploaded
automatically; you choose how to share it. Anonymization is optional for private
sharing. Sharing through a [GitHub issue](https://github.com/Azure/aigateway/issues/new)
requires anonymization, review of the ZIP and issue text, and your explicit approval.

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
