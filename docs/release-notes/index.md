# Labs release notes

What changed in the Azure AI Gateway labs for each [product release](https://ai.gateway.azure.com/docs/), and
where to practice every new feature. Newest first. 🆕 marks a new lab, ✏️ an updated lab, ✅ a lab that already
covered the feature, and ➖ a feature that no lab covers yet.

## October 16, 2026

### Priority and weighted model routing, MCP 2026-07-28

Keep a stable alias while you prefer purchased capacity, balance traffic across deployments, or test a new
model version, and manage MCP servers that use the 2026-07-28 MCP specification.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-16).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Route an alias's traffic across backend models by priority and weight | [22 · Route an alias across models by priority and weight](22-model-routing/README.md) | 🆕 New lab |
| Canary a new model version or run an A/B test with a controlled split | [22 · Split traffic 80/20 between two models](22-model-routing/README.md#split-traffic-8020-between-two-models) | 🆕 New lab |
| Prefer purchased capacity with priorities | [22 · Prefer one model by priority](22-model-routing/README.md#prefer-one-model-by-priority) | 🆕 New lab |
| Create and edit aliases with the **Create alias** wizard | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md#give-one-backend-model-two-aliases) | ✏️ Updated |
| Choose the MCP protocol versions a server supports, including 2026-07-28 | [04 · Choose supported MCP versions](04-federate-mcp-tools/README.md#choose-supported-mcp-versions) | ✏️ Updated |
| See supported MCP versions on the server page and in **Catalog** | [04 · Check the negotiated version](04-federate-mcp-tools/README.md#check-the-negotiated-version) | ✏️ Updated |

#### Labs changes

- **November 5.** The labs repo is now [Azure/aigateway](https://github.com/Azure/aigateway), and the labs site is
  [azure.github.io/aigateway](https://azure.github.io/aigateway/). The [Setup guide](SETUP.md#clone-the-labs-repo)
  clones it into `~/aigateway`, and every lab runs from `~/aigateway/labs/<lab>`. If you cloned `Azure/ai-gateway`
  before, `git pull` still works, and `mv ~/ai-gateway ~/aigateway` moves it to the folder that the labs expect.
- **November 4.** The Azure CLI tracks need `aigateway` extension 1.0.0b22 or later, which the
  [Setup guide](SETUP.md#install-the-aigateway-extension) installs, and use its new commands instead of `az rest`.
  Labs [07](07-cost-budgets/README.md#set-the-cost-limit), [09](09-gateway-baselines/README.md#set-the-baseline), and
  [14](14-otel-chargeback/README.md#choose-the-claims-to-export) replace their REST API tracks with Azure CLI tracks
  that run `az aigateway model policy set-cost-limit`, `az aigateway policy set`, and
  `az aigateway telemetry-exporter update`. [Lab 13](13-monitoring/README.md#create-the-telemetry-exporter) gets an
  Azure CLI track that connects Application Insights with `az aigateway telemetry-exporter create`. Labs
  [10](10-api-keys/README.md#suspend-a-key-instead) and
  [24](24-github-copilot-byok/README.md#cut-copilot-off-by-suspending-the-key) suspend and reactivate keys with
  `az aigateway api-key update --state`, [lab 04](04-federate-mcp-tools/README.md#choose-supported-mcp-versions)
  sets the supported MCP versions with `az aigateway mcp update --versions`, and `az aigateway api-key create` no
  longer passes `--display-name`. The labs still call `az rest` for the connector gateway, MCP tool rules, and
  policy files, which the extension doesn't cover yet.
- **November 4.** The gateways use the `Standard` SKU, the only one that AI Gateway accepts. It's the default in
  the portal and in `az aigateway create`, so [lab 01](01-provision-gateway/README.md#create-the-ai-gateway) no
  longer passes `--sku`, and the Bicep templates set `Standard`. Lab 01 also explains the runtime host name: the
  gateway name's first 10 characters, a hyphen, a 13-character hash, and `.<region>-01.ai.gateway.azure.com`, so
  always read it from the gateway instead of building it from the name.
- **November 4.** On the site, **Your values** has a **Runtime URL** field, and the code blocks fill
  `<gateway-url>` in with it, like the gateway name. The code blocks use `<model-name>` for the alias that apps
  call, so **Model alias** fills it in too.
- **November 4.** [Lab 18](18-private-networking/README.md#how-it-works) no longer says that private routing can only
  be chosen at creation: add, change, or remove it under **Networking**, or with `az aigateway network update`.
  [Lab 02](02-first-model-call/README.md#register-the-deployment)'s tip imports every deployment of a Foundry account with
  `az aigateway model-provider create --foundry-resource-id`. The [lab 15](15-agent-frameworks/README.md) samples
  call the Responses API, because some reasoning models accept function tools only there.
  [Lab 16](16-foundry-hosted-agent/README.md#create-an-azd-environment) creates the azd environment in the
  subscription that the Azure CLI uses, so azd doesn't stop to ask for one, and the
  [lab 11](11-entra-rbac/README.md#clean-up) cleanup skips the role assignment when **Verify** already removed it.
- **October 28.** A new [Setup guide](SETUP.md) collects the tasks that every lab shares: checking your subscription
  and permissions, choosing between Cloud Shell and a local shell, signing in, installing the `aigateway` extension,
  registering the resource providers, finding the available regions, cloning the labs repo, and deploying and
  deleting a lab with azd. Each lab page links to it from the right rail, between **Your values** and
  **Open the portal**, and the labs link to its sections instead of repeating the steps, so they're shorter. Labs
  that run scripts or samples from `infra/` now say to clone the repo first.
- **October 28.** On the site, the [Setup guide](SETUP.md) now opens in a panel next to the lab, like
  **Your values**, from the right rail, the lab's header, or any link to one of its tasks. Mark a task **Done** in
  the panel or on the guide's page, and the labs stop listing it. Each lab's **Before you begin** starts with a
  **One-time setup** card that lists only the tasks it needs and that you haven't done yet, so the labs no longer
  repeat tool lists, sign-in, or a **Clone the lab** step: the **Bicep + azd** tracks start by moving into the lab's
  folder. The [quick start](quickstart/README.md) uses the card too, so its tracks no longer install the extension,
  register the providers, or clone the repo, and every later lab reuses that setup.
- **October 28.** A new [Troubleshooting](TROUBLESHOOTING.md) page collects the errors from every lab, with their
  likely causes and fixes, in one section per lab, plus
  [Setup and deployment](TROUBLESHOOTING.md#setup-and-deployment).
  On the site, you can filter it by an error code or a word from the message, and site search finds each lab's
  section. Each lab's right rail links to its section on the page.
- **October 28.** On the site, [Troubleshooting](TROUBLESHOOTING.md) now opens in a panel next to the lab, like
  the Setup guide, from the right rail or any other link to it. The lab's own errors come first, open, as cards that
  label the likely cause and the fix, and the filter works in the panel too. **Open as a page** keeps the filter.
- **October 28.** Each error on the [Troubleshooting](TROUBLESHOOTING.md) page now names the steps where it shows
  up, and the labs no longer have a **Troubleshooting** section. On the site, those steps get a **Troubleshoot**
  button next to **Done**, with the number of known errors. It opens the panel with only that step's errors, for the
  track you're on, and **Show all errors** shows the rest of the lab. On GitHub, each lab's footer links to its
  section.
- **October 28.** Every Azure CLI, azd, and REST command in the labs, the [quick start](quickstart/README.md), and
  the [Setup guide](SETUP.md) now has a comment that explains what it does, in both Bash and PowerShell. After it
  runs, it prints a short status line with an emoji, such as `🚀 Gateway aigw-1a2b3c is ready` or
  `🤖 <the model's reply>`. Status lines print only when the command succeeds, and keys and tokens are never
  printed: only their length is. [Authoring](AUTHORING.md#cli-comments-and-status-lines) lists the conventions.
- **October 28.** The [quick start](quickstart/README.md)'s Azure CLI track no longer creates a connector gateway
  (`Microsoft.Web/connectorGateways`) with `az rest`, or registers `Microsoft.Web`. Only connector-based MCP tools
  use the connector gateway, and the portal creates it when you first add a connector backend. A live run of the
  track without it published the model and got a reply.
- **October 28.** The [quick start](quickstart/README.md) now names Azure RBAC as the keyless alternative to the
  runtime API key, in every track and in **How it works**, and links to
  [Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md) from its next steps.
- **October 28.** The [quick start](quickstart/README.md#publish-the-model)'s Azure CLI track now publishes the model
  with one import: `az aigateway model-provider create --foundry-resource-id` grants the gateway's managed identity
  the **Foundry User** role on the Foundry account, adds a model provider that signs in with that identity, and adds
  a model for each deployment. It replaces the role assignment, the provider JSON, and `az aigateway model create`.
  The track still adds the alias, because the import doesn't. Labs
  [02](02-first-model-call/README.md#create-the-foundry-provider) and
  [18](18-private-networking/README.md#publish-the-deployment-and-an-alias) now pass the provider's Foundry settings
  in the Azure CLI shorthand instead of building JSON with `jq` or a file.
- **October 28.** The Bash snippets now paste cleanly into zsh on macOS. Their status lines use only emoji that zsh
  draws, such as 🔐 instead of 🛡️ and 🔖 instead of 🏷️, and JSON values that contain a URL stay on one line, so
  oh-my-zsh's URL quoting can't escape them. The [Setup guide](SETUP.md#choose-where-to-run-commands) turns on
  `interactive_comments`, so zsh accepts the pasted comments, and
  [Troubleshooting](TROUBLESHOOTING.md#setup-and-deployment) lists the paste errors. `npm run check` flags other
  emoji, and URL lines that zsh could change. [Authoring](AUTHORING.md#cli-comments-and-status-lines) lists the
  emoji.
- **October 28.** The labs no longer describe AI Gateway as a preview service or say that the gateway is free
  during the preview. [Lab 00](00-how-ai-gateway-works/README.md) and the
  [Setup guide](SETUP.md#check-your-subscription-and-permissions) point to the
  [AI Gateway documentation](https://ai.gateway.azure.com/docs) for pricing, and the lab 01 video narrates the
  region step without the preview. Labs [19](19-tool-threat-protection/README.md) and
  [20](20-agent-365-governance/README.md) still mark Agent 365 as an emerging capability.
- **October 28.** AI Gateway now runs in more regions, and the list keeps growing, so the labs no longer name fixed
  regions. The [Setup guide](SETUP.md#find-the-available-regions) shows how to list the current ones with the Azure
  CLI, and how to check that a Foundry model is available in a region. The Bicep templates accept any region, the
  other labs link to that list, and the notebooks check `AIGW_LOCATION` against it. The portal can offer fewer regions
  than the Azure CLI and Bicep + azd tracks.
- **October 28.** On the site, Safari no longer offers saved credit cards or contacts in **Your values**, such as on
  **Subscription ID**. The panel now focuses its close button when it opens instead of the first field, and
  password managers skip its fields too. Your saved values carry over.
- **October 28.** The Azure CLI tracks need `aigateway` extension 1.0.0b15 or later, which the
  [Setup guide](SETUP.md#install-the-aigateway-extension) installs. They publish aliases with
  `az aigateway model-alias set`, which creates the alias or updates it, so you can run the step again (the
  [quick start](quickstart/README.md#publish-the-model), labs [02](02-first-model-call/README.md#publish-an-alias),
  [03](03-multi-provider-aliases/README.md#create-the-aliases), [18](18-private-networking/README.md),
  [22](22-model-routing/README.md), [23](23-streaming-responses/README.md), and
  [24](24-github-copilot-byok/README.md)). [Lab 01](01-provision-gateway/README.md#create-the-ai-gateway) passes
  `--sku Consumption` and shows the SKU, [lab 06](06-token-limits/README.md#set-the-token-limit) shows that
  `--token-counter-key` takes `Identity`, `IPAddress`, or both, like the portal's **Counter dimensions**, and
  [lab 12](12-backend-identity/README.md#update-the-providers-authentication) changes only the provider's identity
  with a partial `az aigateway model-provider update --foundry`, without reading and rewriting the whole provider.
- **October 27.** Every Bicep + azd track is now a self-contained azd template, like the quick start's: clone the
  repo, run `azd up` in the lab's folder to create a new gateway with everything the lab needs, change its settings
  with `azd env set` and `azd provision`, and remove it all with `azd down --purge --force`
  ([lab 06](06-token-limits/README.md#deploy-with-azd-up) shows the pattern). Labs
  [01](01-provision-gateway/README.md), [02](02-first-model-call/README.md), [04](04-federate-mcp-tools/README.md),
  [06](06-token-limits/README.md), [11](11-entra-rbac/README.md), [12](12-backend-identity/README.md), [13](13-monitoring/README.md),
  [18](18-private-networking/README.md), [22](22-model-routing/README.md), [23](23-streaming-responses/README.md),
  and [24](24-github-copilot-byok/README.md) move to it, and labs [03](03-multi-provider-aliases/README.md),
  [05](05-mcp-tool-controls/README.md), [07](07-cost-budgets/README.md), [08](08-content-safety/README.md),
  [10](10-api-keys/README.md), [14](14-otel-chargeback/README.md), and [19](19-tool-threat-protection/README.md) gain a
  Bicep + azd track. The reusable modules have descriptive names, such as lab 01's `gateway.bicep`, lab 02's
  `publish-model.bicep`, lab 04's `tool-server.bicep`, and lab 06's `limited-alias.bicep`, so other labs can
  compose them. Lab 05 now shows that a blocked MCP server answers `200` with the JSON-RPC error
  `AccessBlockedByGateway`.
- **October 27.** The Azure CLI tracks need `aigateway` extension 1.0.0b14 or later, which the
  [Setup guide](SETUP.md#install-the-aigateway-extension) installs. They now register models with
  `az aigateway model create`, set and remove token limits and content safety with `az aigateway model policy`
  ([lab 06](06-token-limits/README.md), [lab 08](08-content-safety/README.md),
  [lab 09](09-gateway-baselines/README.md), [lab 24](24-github-copilot-byok/README.md)), and rotate the secondary
  key value with `az aigateway api-key regenerate --key-type secondary` ([lab 10](10-api-keys/README.md)).
  [Lab 02](02-first-model-call/README.md#register-the-deployment) also shows the one-step
  `az aigateway model create --foundry-resource-id`. The labs keep `az rest` for gateway policies, cost limits,
  telemetry exporters, MCP versions, API key state, and the connector gateway.
- **October 27.** The [quick start](quickstart/README.md#review-the-template)'s Bicep + azd track now gets its
  template by cloning the repo and moving into `labs/quickstart`, instead of downloading each file. The clone also
  gets the other labs, and the track no longer lists the template's files.
- **October 26.** The Bicep templates now follow the AI Gateway [reference sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/ai-gateway/main.bicep): they
  create the gateway in the `Consumption` SKU, the same one that `az aigateway create` uses, and then its connector
  gateway. A template that omits `sku` creates a `Premium` gateway, so set it in your own templates too. Every
  template now silences the `BCP081` warnings for the preview resource types, so `az bicep build` runs clean, and
  the quick start template's model and alias set `displayName`, `modelVersion`, and `aliasName`, as the sample does.
  [Lab 01](01-provision-gateway/README.md#review-the-template) explains the template, and its troubleshooting now
  covers `InvalidSkuName` and the limit of five gateways per subscription in each region.
- **October 23.** The Azure CLI tracks, the **Verify** and **Clean up** steps, and the lab scripts now use the
  `aigateway` CLI extension for gateways, model providers, aliases, API keys, and MCP servers.
  The [Setup guide](SETUP.md#install-the-aigateway-extension) shows how to install it. The labs keep `az rest` only
  for what the extension can't do yet, such as registering models and setting policies, and say why each time.
- **October 23.** [Lab 18](18-private-networking/README.md#prepare-the-virtual-network) now delegates the integration
  subnet to `Microsoft.App/environments`, which the service requires. A subnet delegated to
  `Microsoft.Web/serverFarms` fails with `AIGatewaySubnetNotDelegated`. The portal's subnet check still expects
  `Microsoft.Web/serverFarms` and shows a warning, which you can ignore.
- **October 23.** [Lab 24](24-github-copilot-byok/README.md#publish-microsoft-learn-tools-for-copilot) now
  publishes the Microsoft Learn MCP server on the gateway, with portal, Azure CLI, and Bicep tracks, and adds its
  tools to GitHub Copilot in VS Code, the Copilot CLI, the Copilot SDK, and the GitHub Copilot app with the same
  runtime key. It shows the token cost of tool results and how one suspended key cuts off both models and tools.
- **October 22.** New lab [24 · Use your gateway's models and tools in GitHub Copilot](24-github-copilot-byok/README.md):
  publish `gpt-6-astra` with a per-caller token limit and a key for Copilot, then connect GitHub Copilot in VS Code,
  the Copilot CLI, the Copilot SDK (Python and TypeScript), and the GitHub Copilot app with bring your own key
  (BYOK). It includes portal, Azure CLI, and Bicep tracks, and shows how one suspended key cuts off every Copilot
  surface.
- **October 22.** New [5-minute quick start](quickstart/README.md): learn the building blocks, create a gateway
  with a Foundry `gpt-6-luna` model, an alias, and a runtime key, and make your first call. Follow it in the AI
  Gateway portal, with a screenshot for every step; paste its Azure CLI commands (Bash or PowerShell) into Cloud
  Shell; or download its Bicep template and deploy it with one `azd up`. There's nothing to clone. The
  home page now starts with it, and the former 30-minute quickstart path is now **30-minute essentials**.
- **October 22.** New lab [23 · Stream responses and count every token](23-streaming-responses/README.md), which
  covers usage for streamed Chat Completions responses from the [September 24](#september-24-2026) release. It
  streams with curl, PowerShell, Python, and TypeScript, shows each chunk and where usage arrives, proves that a
  token limit counts streams with or without `include_usage`, and has a notebook and an interactive streaming
  usage simulator on the site.
- **October 22.** New lab [22 · Route an alias across models by priority and weight](22-model-routing/README.md),
  with portal, Azure CLI, and Bicep tracks, a script that counts which model served each request, and an
  interactive priority and weight simulator on the site.
- **October 22.** [Lab 04](04-federate-mcp-tools/README.md) adds **Supported MCP versions**: the version list,
  the legacy defaults, the rule that every backend must support every listed version, and a `supportedVersions`
  Bicep parameter. [Lab 03](03-multi-provider-aliases/README.md) follows the new alias wizard and links to lab 22.
- **October 22.** The labs use the latest models: `gpt-6-luna` and `gpt-6.1-sol` from Microsoft Foundry, and
  `claude-haiku-5-5` and `claude-sonnet-5-5` from Anthropic. Portal steps say **Catalog** where the portal used
  to say **Discover**.
- **October 22.** [Lab 00](00-how-ai-gateway-works/README.md) has a narrated three-minute video tour of the
  portal.
- **October 19.** Every lab creates the dedicated `Microsoft.ApiManagement/aigateways` resource type.
- **October 19.** Each lab's `README.md` is the source of truth for both the site and GitHub, with navigation
  that works on GitHub. Jupyter notebooks run five labs end to end by deploying the labs' own Bicep files
  through a shared [`utils.py`](shared/utils.py).
- **October 19.** [Lab 01](01-provision-gateway/README.md) has a narrated video, and the
  [`azure-ai-gateway-labs`](skills/azure-ai-gateway-labs/SKILL.md) agent skill teaches coding agents how to use
  the labs.

## October 8, 2026

### Agent 365 integration and tool threat protection

Discover and govern AI Gateway MCP servers and tools from Microsoft Agent 365, and protect tool calls with
Microsoft Defender and Microsoft Purview.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-08).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Discover AI Gateway MCP servers in the Agent 365 inventory | [20 · Connect Agent 365 to your gateways](20-agent-365-governance/README.md#connect-agent-365-to-your-gateways) | ✅ Covered |
| Block or unblock MCP servers and individual tools from Agent 365 | [20 · Block a tool](20-agent-365-governance/README.md#block-a-tool) | ✅ Covered |
| Evaluate tool calls before and after invocation with Defender and Purview | [19 · Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md) | ✅ Covered |

#### Labs changes

- **October 14.** The labs launch with 22 labs that cover every product release through October 8, each with
  portal steps and, where the product supports them, Azure CLI, REST, Bicep, and code tracks.

## October 1, 2026

### Cost limit overrides for Microsoft Entra identities

Set different cost limit amounts for Microsoft Entra callers by identity or by an exact combination of
validated token claims.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-10-01).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A higher or lower budget for a selected identity or matching token claims | [07 · Give a Microsoft Entra identity its own budget](07-cost-budgets/README.md#give-a-microsoft-entra-identity-its-own-budget) | ✅ Covered |
| Separate budgets per caller by tenant ID and object ID | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| The first matching override wins | [07 · How it works](07-cost-budgets/README.md#how-it-works) | ✅ Covered |

## September 24, 2026

### Model aliases, Entra access, and Chat Completions streaming usage

Aliases become the stable model contract, with Microsoft Entra authentication, gateway-scoped policies, and
complete usage for streamed Chat Completions responses.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-24).

| In the product | Practice it in the labs | Status |
|---|---|---|
| Callable aliases, several aliases for one backend model, and retargeting | [03 · Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md) | ✅ Covered |
| Grant model and MCP access to Microsoft Entra users, groups, apps, and managed identities | [11 · Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md) | ✅ Covered |
| Export selected JWT claims to OTLP logs, traces, and metrics | [14 · Choose the claims to export](14-otel-chargeback/README.md#choose-the-claims-to-export) | ✅ Covered |
| Apply one policy to every current and future asset, including a gateway-wide cost limit | [09 · Set gateway-wide policy baselines](09-gateway-baselines/README.md) | ✅ Covered |
| Usage for streamed Chat Completions responses without `include_usage` | [23 · Stream a burst without asking for usage](23-streaming-responses/README.md#stream-a-burst-without-asking-for-usage) | 🆕 New lab |

## September 10, 2026

### Per-key budget overrides and MCP tool filtering and blocking

Assign higher or lower model budgets to selected API keys, and control which MCP tools agents can discover and
invoke.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-09-10).

| In the product | Practice it in the labs | Status |
|---|---|---|
| A different budget for selected API keys | [07 · Give an API key a bigger budget](07-cost-budgets/README.md#give-an-api-key-a-bigger-budget) | ✅ Covered |
| Expose all, selected, or pattern-matched tools | [05 · Publish only approved tools](05-mcp-tool-controls/README.md#publish-only-approved-tools) | ✅ Covered |
| Block individual tools or a whole MCP server | [05 · Take the whole server offline](05-mcp-tool-controls/README.md#take-the-whole-server-offline) | ✅ Covered |
| Redesigned Home and first-run gateway setup | [01 · Provision your AI Gateway](01-provision-gateway/README.md) | ✅ Covered |

## August 28, 2026

### OpenTelemetry observability and model budgets

Export logs, traces, token metrics, and estimated cost metrics through OTLP, and enforce model spend with cost
limits.
[Read the product release notes](https://ai.gateway.azure.com/docs/releases/2026-08-28).

| In the product | Practice it in the labs | Status |
|---|---|---|
| The built-in Application Insights dashboard and request traces | [13 · Monitor usage, cost, and traces](13-monitoring/README.md) | ✅ Covered |
| OTLP export of logs, traces, and token and cost metrics | [14 · Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md) | ✅ Covered |
| Cost limits with hourly to yearly budget windows | [07 · Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md) | ✅ Covered |
| Import Microsoft Foundry models and onboard custom providers | [02 · Publish a Foundry model](02-first-model-call/README.md) and [03 · Add Anthropic as a custom provider](03-multi-provider-aliases/README.md#add-anthropic-as-a-custom-provider) | ✅ Covered |

## How these notes work

Each section matches one entry in the [product release notes](https://ai.gateway.azure.com/docs/), with the same
date and title, and maps every product change to the lab where you can practice it. Changes to the labs that
don't come from a product release are listed under **Labs changes** in the release they followed.

This file, [`labs/RELEASE-NOTES.md`](RELEASE-NOTES.md), is the source of truth: the labs site renders it at
[/release-notes/](https://azure.github.io/aigateway/release-notes/). To check for product releases that the
notes don't cover yet, run `npm run releases` in `labs/`. See [Authoring](AUTHORING.md#release-notes).
