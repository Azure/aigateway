# Azure AI Gateway

**One gateway for every model and tool.**
[Azure AI Gateway](https://aka.ms/aigateway/docs) gives developers one familiar way
to call model APIs and MCP tools, while
platform teams enforce security, policy, networking, and observability.

- **Govern model APIs** — Microsoft Foundry, OpenAI, Anthropic, Google Vertex, and more, while developers keep the SDKs they already use.
- **Federate MCP tools** — combine MCP servers, OpenAPI APIs, and SaaS connectors behind one governed MCP endpoint.
- **Enforce AI policies** — access, content safety, token, and rate controls, globally or per model and tool.
- **Observe AI traffic** — token usage, latency, errors, and policy outcomes in dashboards and logs.
- **Run on a trusted platform** — the Azure API Management platform, with Private Link, virtual network integration, and managed identity.

> Azure AI Gateway is in **public preview**, available free of charge. See the **[documentation](https://aka.ms/aigateway/docs)** to get started.

---

## Azure CLI

Create and manage gateways, model registrations, MCP servers, and policies with
`az aigateway`. The CLI is an external dependency published in **[Azure/aigateway](https://github.com/Azure/aigateway)**.
See the **[hosted CLI quickstart](https://ai.gateway-df.azure.com/docs/quickstarts/cli)** for
one-line Bash and PowerShell installers, or browse the
[current command reference](https://github.com/Azure/aigateway/blob/main/cli/command-reference.md).
Use the official published CLI, including reviewed preview releases, rather than
a local source build. Ordinary tasks reuse the installed version and task-specific
help; installation/upgrade is separate approved work, not a prerequisite to every
question. Migration retains its stricter release/provenance validation.

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
| Command `build` | `/aigateway:build` | Integrate supplied or discovered assets using an existing secure credential; selected secret retrieval and live checks require authorization. |
| Command `create` | `/aigateway:create` | Create a gateway; include selected RG/Foundry bootstrap only when explicitly requested and approved. |
| Command `manage` | `/aigateway:manage` | Configure and operate a gateway and its assets. |
| Command `migrate` | `/aigateway:migrate` | Run the assisted, capability-gated APIM V2 migration workflow or resume its verified state. |
| Command `feedback` | `/aigateway:feedback` | Package one selected agent session into a local ZIP for user-controlled sharing; anonymization and review are mandatory for GitHub issues. |
| Skill `use-ai-gateway` | `/aigateway:use-ai-gateway` | Use AI assets from Azure AI Gateway to build intelligent applications. |
| Skill `manage-ai-gateway` | `/aigateway:manage-ai-gateway` | Full administrator workflow for creating, configuring, and operating a gateway. |
| Skill `migrate-ai-gateway` | `/aigateway:migrate-ai-gateway` | Inventory, assess, validate, and reconcile supported APIM V2 configuration to move the workload to Azure AI Gateway. |

### Install

The root `plugin.json` uses **Agent Plugins 1.0**: the four skills are portable
`skills/<name>/SKILL.md` components. Copilot CLI shortcuts are thin wrappers in
`com.github.copilot/commands/`; Claude/Cursor manifests and Gemini TOML commands
remain available. Shortcut support varies by host; the skills are the shared
workflow, not separate implementations.

**GitHub Copilot CLI** — install directly, without registering a marketplace:

```bash
copilot plugin install Azure/aigateway
```

Or use this repository's **azure** marketplace:

```bash
copilot plugin marketplace add Azure/aigateway
copilot plugin install aigateway@azure
```

**VS Code / compatible Copilot products** — use the host's Agent Plugins
installation UI and add this repository's marketplace when supported. In VS
Code, use **Chat: Plugins**; availability depends on the installed version and
organization policy. Do not assume CLI-specific shortcuts load in every product.

**Claude Code**:

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

This layout follows the public awesome-copilot plugin conventions. It does
**not** claim that `aigateway@awesome-copilot` has been accepted or published.
Use the direct repository or `aigateway@azure` installation above.

### Usage

For management-enriched discovery, provide the gateway's ARM resource ID and
your use case; listing requires authorized management reads:

```
/aigateway:build /subscriptions/.../aigateways/<gateway> a service that summarizes support tickets
```

Or explore first, then integrate:

```
/aigateway:discover /subscriptions/.../aigateways/<gateway>
```

For a known endpoint, no ARM ID, subscription inventory or management sign-in
is needed. Supply the exact URL, callable name, operation and existing secure
credential **binding**, never a secret value:

```text
/aigateway:build Integrate https://<published-host>/default/models/openai/v1/chat/completions
using the published alias support/assistant and the existing AI_GATEWAY_API_KEY
binding. The owner verified bearer authentication. Modify my existing Python app;
do not make a live call yet.
```

Published runtime examples differ: the older CLI quickstart uses `Api-Key` and
direct model names, while the hosted quickstart uses bearer authentication and
aliases. The skill preserves the **selected gateway's verified contract**,
not an assumed universal header/model shape or an automatic fallback after 401.

#### Manage

Administrators can create a gateway or manage an existing one:

```
/aigateway:create my-gateway my-resource-group eastus2
/aigateway:manage my-gateway my-resource-group register one selected existing Foundry deployment
```

The [administrator skill](skills/manage-ai-gateway/SKILL.md) provides native CLI
runbooks for gateway lifecycle, models and aliases, MCP sources, policies, keys,
identities, networking, and telemetry. It manages only
`Microsoft.ApiManagement/aigateways` and its own children. Explicit bootstrap
can create a selected RG and use selected Foundry onboarding after disclosure
and approval of gateway identity and account-level Foundry User grants. Provider
onboarding imports every current deployment; "add one model" is not bulk-import
permission. Other external infrastructure and grants remain prerequisites.
Routine create/update intent authorizes the requested work; destructive,
access-sensitive, and secret-related operations have
specific confirmation gates. [Portal activity coverage and CLI gaps](skills/manage-ai-gateway/references/activities-and-cli-coverage.md)
are explicit rather than bypassed with REST or legacy resource types.

#### Migrate workloads to Azure AI Gateway

Administrators can assess and migrate supported APIM V2 configuration to Azure AI Gateway:

```
/aigateway:migrate /subscriptions/.../Microsoft.ApiManagement/aigateways/<source-apim>
```

Use the source's actual verified ARM ID and family; do not rewrite a legacy
`Microsoft.ApiManagement/service` ID to `aigateways`.

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

### Scenario coverage and evaluation

The existing skills cover gateway lifecycle, model registration and alias
routing, MCP federation, policy/finops controls, access, networking/private
connections, observability and data-plane integration. They load only the
reference needed for the current task. IaC, backend provisioning and unsupported
native fields remain explicit separate work, not invented CLI operations.

Run deterministic packaging/link/entry-point checks with
`python3 -m unittest discover -s tests`. The [evaluation suite](evals/README.md)
defines Waza scenarios and quality/safety criteria for further improvement.
Offline checks do not establish live model quality, cloud behavior or a grade A;
authenticated trials and separately authorized Azure validation are distinct.

### Format references

- [Copilot CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
  and [shared plugin formats](https://docs.github.com/en/copilot/reference/plugin-and-marketplace-reference).
- [awesome-copilot plugin guide](https://github.com/github/awesome-copilot/blob/main/docs/README.plugins.md)
  and [portable Azure exemplar](https://github.com/github/awesome-copilot/blob/main/plugins/azure-cloud-development/plugin.json).
- [CLI b22 release](https://github.com/Azure/aigateway/releases/tag/cli-v1.0.0b22)
  and [hosted documentation](https://ai.gateway-df.azure.com/docs/quickstarts/cli).

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
