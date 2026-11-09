[AI Gateway labs](README.md) › Troubleshooting <!-- gh -->

# Troubleshooting

The errors you might hit in the labs, with their likely causes and fixes. Errors from setting up and deploying, such
as a missing extension or an unavailable region, are under [Setup and deployment](#setup-and-deployment), and the
others are under their lab, with the steps where they show up. Look for the error code or the message, for example
`429` or `ValidationError`. On the site, the **Troubleshoot** button of a lab step shows only that step's errors.

**Jump to:** [Setup and deployment](#setup-and-deployment) · [Quick start](#quick-start) · [00](#lab-00-how-ai-gateway-works) · [01](#lab-01-provision-a-gateway) · [02](#lab-02-first-model-call) · [03](#lab-03-multi-provider-aliases) · [04](#lab-04-federate-mcp-tools) · [05](#lab-05-tool-allow-and-block-lists) · [06](#lab-06-token-limits) · [07](#lab-07-cost-budgets) · [08](#lab-08-content-safety) · [09](#lab-09-gateway-wide-baselines) · [10](#lab-10-runtime-api-keys) · [11](#lab-11-entra-id-and-rbac) · [12](#lab-12-backend-identities) · [13](#lab-13-monitoring) · [14](#lab-14-opentelemetry-chargeback) · [15](#lab-15-agent-frameworks) · [16](#lab-16-foundry-hosted-agent) · [17](#lab-17-coding-agent-plugin) · [18](#lab-18-private-networking) · [19](#lab-19-tool-threat-protection) · [20](#lab-20-agent-365-governance) · [21](#lab-21-enterprise-reference) · [22](#lab-22-priority-and-weighted-routing) · [23](#lab-23-streaming-responses) · [24](#lab-24-github-copilot-byok) <!-- gh -->

## Setup and deployment

Setup guide: [The one-time tasks that every lab builds on](SETUP.md)

| Symptom | Likely cause | Fix |
|---|---|---|
| `'aigateway' is misspelled or not recognized by the system` | The `aigateway` extension isn't installed | [Install the extension](SETUP.md#install-the-aigateway-extension), then run `az aigateway version`. |
| `MissingSubscriptionRegistration`, or `The subscription is not registered to use namespace` | A resource provider isn't registered in the subscription | [Register the resource providers](SETUP.md#register-the-resource-providers), or ask your subscription administrator. |
| `LocationNotAvailableForResourceType` | The location isn't a region where AI Gateway is available | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). |
| `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| `InvalidResourceGroupLocation` from `azd up` | The resource group `rg-<environment name>` already exists in another region | Run `azd env new` with a new environment name, or delete the old resource group. |
| Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |
| `zsh: command not found: #`, or a pasted block stops after a comment | zsh on macOS reads pasted `#` lines as commands | Turn on `interactive_comments`, as in [Choose where to run commands](SETUP.md#choose-where-to-run-commands), and paste the block again. |
| `jq: error: syntax error, unexpected INVALID_CHARACTER`, and the pasted command shows `\{` or `\}` after a URL | The block was pasted while a command still ran, and oh-my-zsh's URL quoting escaped the characters after the URL | Wait for the prompt, then paste the block again. |
| Pasted text shows codes such as `<0001f9e0>` | The snippet is an older copy with an emoji that zsh can't draw. The command still runs. | Reload the lab page to copy the current snippets. |

## Quick start

Quick start: [Your first model call in 5 minutes](quickstart/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Create the gateway | A subscription is disabled in **Create AI gateway** | You can't write API Management or connector gateway resources in it | Pick another subscription, or ask for **Contributor** on it. |
| Import the model from Foundry<br>Publish the model<br>Deploy with azd up | `AuthorizationFailed` on `Microsoft.Authorization/roleAssignments` | You can create resources but not role assignments | Ask for **Owner**, or **Role Based Access Control Administrator**, on the resource group. |
| Start creating the gateway<br>Deploy with azd up | `LocationNotAvailableForResourceType` | AI Gateway isn't available in the region | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). |
| Create the gateway<br>Start creating the gateway<br>Deploy with azd up | `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| Deploy the model in Foundry<br>Deploy with azd up | `InvalidResourceProperties`: `The specified SKU 'GlobalStandard' for model 'gpt-5-mini 2025-08-07' is not supported in this region` | `gpt-5-mini` isn't available in the region | Pick a region where the model check in [Find the available regions](SETUP.md#find-the-available-regions) prints `GlobalStandard`. |
| Deploy the model in Foundry<br>Deploy with azd up | `InsufficientQuota` on the model deployment | The subscription has no `gpt-5-mini` capacity left in the region | Start again in another region: set `LOCATION` in the Azure CLI track, or run `azd env new` with a new name and another `--location` in the Bicep + azd track. Or free capacity in [Foundry](https://ai.azure.com). |
| Deploy with azd up | `InvalidResourceGroupLocation` from `azd up` | The resource group `rg-<environment name>` already exists in another region | Run `azd env new` with a new environment name, or delete the old resource group. |
| Make your first call | `403` or `404` from the gateway in the first minute | The gateway's role on the Foundry account, or the new alias, is still taking effect | Wait a minute and call again. |
| Make your first call | `403` from the backend that doesn't go away | The gateway's managed identity has no role on the Foundry account | Run the import in the Azure CLI track's **Publish the model** step again, which grants the role, or assign the gateway **Foundry User** on the account. Then wait a few minutes. |
| Make your first call | `401`: `Missing or invalid Entra ID token, or missing Data.All scope` | The key is missing, wrong, or in the wrong header. The message mentions Entra ID even when you use a key | Send it in the `api-key` header, or as `Authorization: Bearer <key>`. In the portal, copy it again from **Access** › **API keys**. |
| Make your first call | The playground shows `You don't have permission to invoke this model with Entra ID` and you can't type a prompt | **Method** is **Microsoft Entra ID**, and you have no AI Gateway role on the gateway | Set **Method** to **API key** and choose `app-first-call`. To call with Entra ID instead, grant yourself **AI Gateway Models User** in **Access** › **Entra ID**, as [Lab 11](11-entra-rbac/README.md) shows. |
| Make your first call | `400` that mentions authentication | The request has both an `api-key` and an `Authorization` header | Send only one of them. |
| Start creating the gateway<br>Deploy the model in Foundry<br>Deploy with azd up | `The subscription is not registered to use namespace` | A resource provider isn't registered yet | [Register the resource providers](SETUP.md#register-the-resource-providers), then try again. |
| Make your first call (Azure CLI, Bicep + azd) | `404` with `Resource not found` from the gateway | The alias is missing, or the URL path is wrong | Run the alias command in **Publish the model**: the import adds models but no aliases. Call `<runtime URL>/default/models/openai/v1/chat/completions`. |

## Lab 00: How AI Gateway works

Lab 00: [How Azure AI Gateway works](00-how-ai-gateway-works/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Browse models and aliases | A model call says the model can't be found | The `model` field doesn't match an alias | Copy the alias from **Models**, or from the code sample in **Catalog** |
| Browse models and aliases | An Anthropic call fails on the OpenAI endpoint | The gateway doesn't translate between protocols | Call `/default/models/anthropic/v1/messages` with `anthropic-version: 2023-06-01` |
| Open your gateway | You can't create a gateway in your region | AI Gateway isn't available there yet | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions) |
| Open Monitoring | Monitoring is empty | No telemetry destination | Connect Application Insights in **Monitoring** › **Settings** |

## Lab 01: Provision a gateway

Lab 01: [Provision your AI Gateway](01-provision-gateway/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Enter the gateway details | Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |
| Create the AI gateway<br>Deploy with azd up | `LocationNotAvailableForResourceType` | `$LOCATION` or the template's `location` isn't a region where AI Gateway is available | Pick a region from [Find the available regions](SETUP.md#find-the-available-regions). The template defaults to `eastus2`. |
| Watch it provision<br>Create the AI gateway<br>Deploy with azd up | `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| Enter the gateway details<br>Create the AI gateway | The name is rejected | Gateway names are globally unique and limited to 24 characters: letters, digits, and hyphens, starting with a letter | Pick another name that follows the rules. |
| Watch it provision<br>Create the AI gateway<br>Deploy with azd up | `AIGatewaySubscriptionGatewayLimitExceeded`: `…has reached the maximum of 5 AI Gateway resources allowed in this region.` | The subscription already has five gateways in `$LOCATION` | Delete a gateway you no longer need, or create this one in another available region. |
| Deploy with azd up | `InvalidSkuName`: `The supported AI Gateway SKU name is 'Standard'.` | Your template or command sets another SKU, such as `Consumption`, `Premium`, or `AIGateway` from older samples | Set `sku: { name: 'Standard' }`, as [`infra/gateway.bicep`](01-provision-gateway/infra/gateway.bicep) does, or omit `--sku` in `az aigateway create`. |
| Create the AI gateway<br>Deploy with azd up | `MissingSubscriptionRegistration` | A resource provider isn't registered in the subscription | [Register the resource providers](SETUP.md#register-the-resource-providers), or ask your subscription administrator. |
| Call the runtime URL | `Could not resolve host` when you call the URL | Provisioning or DNS isn't finished | Run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` and retry. |
| Create the AI gateway<br>Call the runtime URL | `'aigateway' is misspelled or not recognized by the system` | The `aigateway` extension isn't installed | [Install the `aigateway` extension](SETUP.md#install-the-aigateway-extension), then run `az aigateway version`. |

## Lab 02: First model call

Lab 02: [Publish a Foundry model and make your first call](02-first-model-call/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Call Chat Completions<br>Run the sample<br>Get a 200 with the key | `401` from the gateway | The key is missing, misspelled, or deleted | Send an active runtime key in the `api-key` header or as the SDK API key. Create a new key if you lost the value. |
| Run the sample | `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header, such as an SDK placeholder key | Pass the runtime key as the SDK API key and remove the `api-key` default header. |
| Try the model in Catalog<br>Call Chat Completions<br>Run the sample<br>Get a 200 with the key | `403` mentioning permissions on the Foundry account | The gateway's identity lacks **Foundry User**, or the assignment hasn't propagated yet | Wait a few minutes. If it persists, assign the role as shown in the portal track. |
| Call Chat Completions<br>Run the sample<br>Get a 200 with the key | `404` with `model_not_found` | `model` doesn't match an alias exactly | Copy the alias from the model's **Aliases** tab or from **Catalog**. |
| Call Chat Completions<br>Run the sample | `400` `unsupported_parameter` for `max_tokens`, or `unsupported_value` for `temperature` | `gpt-5-mini` is a reasoning model | Send `max_completion_tokens` instead of `max_tokens`. Leave `temperature` out: the model accepts only the default, `1`. |
| Call Chat Completions<br>Run the sample | `200` with empty `content` and `finish_reason` `length` | Reasoning used the whole `max_completion_tokens` budget | Raise the budget, or send `reasoning_effort: "none"` for short, direct replies. |
| Call the Responses API<br>Run both calls with a script<br>Run the sample | The Responses API call fails while Chat Completions works | The model doesn't advertise the Responses interface | Check the supported interfaces on the model details page and call only those. |
| Import the deployment from Foundry | The import wizard doesn't list your account | It's already imported into this gateway, or you can't read it in that subscription | Check **Models** for an existing provider, or ask for read access to the account. |
| Grant the gateway access to the account<br>Deploy with azd up | `AuthorizationFailed` on `roleAssignments` during deployment | You can't create role assignments on the Foundry account | Ask for **Role Based Access Control Administrator** on the account, or have an owner grant the role. |

## Lab 03: Multi-provider aliases

Lab 03: [Publish models from any provider behind stable aliases](03-multi-provider-aliases/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Choose the models and their aliases | The wizard discovers no models, or times out | The base endpoint URL includes `/v1`, the header name is wrong, or the provider doesn't serve `/v1/models` | Use `https://api.anthropic.com` and `x-api-key`. If the provider can't list models, add them with **Individual model**. |
| Call both aliases | `401` from the gateway | The `api-key` header is missing or holds the Anthropic key instead of a gateway runtime key | Send a runtime key from **Access** › **API keys** in the `api-key` header. |
| Call both aliases | An authentication error from Anthropic in the response body | The stored provider key is wrong or expired, or **Include Bearer** is selected for Anthropic | Update the provider's API key and clear **Authentication scheme**. |
| Call both aliases | `400` that mentions `anthropic-version` | The request doesn't send the `anthropic-version` header | Add `anthropic-version: 2023-06-01`. |
| Call both aliases | `404` or a "model not found" error | The `model` value doesn't exactly match an alias, or you called the OpenAI route for an Anthropic model | Copy the alias from **Models**, and call `/default/models/anthropic/v1/messages`. |
| Call both aliases | `404` with an empty body from both Anthropic aliases, while `gpt-5-mini` works | A service issue in the current preview: the gateway adds its `/anthropic` route segment to the provider's endpoint path, so Anthropic gets `/anthropic/v1/messages` and answers `404` | Your setup is right, and no endpoint value works around it. Finish the other steps with `gpt-5-mini`, and check the [AI Gateway changelog](https://ai.gateway.azure.com/docs/) for the fix. |
| Choose the models and their aliases<br>Add the batch-chat alias | "Callable aliases must be unique" | Another alias in the gateway already uses that name | Pick a different alias, or retarget the existing one. |

## Lab 04: Federate MCP tools

Lab 04: [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Add the server to VS Code<br>Call the tools from Python<br>List the published tools<br>Send a raw JSON-RPC request | `401` from the MCP endpoint | The key is missing, revoked, or sent in the wrong header | Send a runtime key from **Access** › **API keys** in the `api-key` header. |
| Add the server to VS Code<br>Call the tools from Python<br>List the published tools<br>Send a raw JSON-RPC request | `404` from the MCP endpoint | Wrong server name in the URL, or the server is still provisioning | List the servers with `az aigateway mcp list -g "$RG" --gateway-name "$GATEWAY" -o table` and use the exact name in `/default/toolservers/<server-name>/mcp`. |
| Send a raw JSON-RPC request | `406` or an error about the `Accept` header | The client doesn't accept both JSON and SSE | Send `Accept: application/json, text/event-stream`, or use an MCP SDK. |
| Call the tools from Python<br>List the published tools<br>Send a raw JSON-RPC request | `tools/list` returns an empty `tools` array | The registration is reachable but no backend returned tools | Check each backend's URL with `az aigateway mcp source list -g "$RG" --gateway-name "$GATEWAY" -n <server-name> -o table`, and check its authentication. |
| Call the tools from Python<br>List the published tools<br>Call a tool through the gateway | The whole server fails when one backend is down | That backend is **Required** | Turn **Required** off for backends that are nice-to-have, or fix the backend. |
| Add the second namespace<br>Pin the versions | Backends or policies disappeared after a Bicep deployment | A Bicep deployment sends a `PUT`, which replaces an existing registration with the same name | Change existing servers with `az aigateway mcp update` or `az aigateway mcp source add` and `remove`, as in the CLI track, or deploy to a new name. |
| Create the registration | `mcp create` fails with "This MCP registration already exists; use mcp update." | A server with that name already exists | Change it with `az aigateway mcp update` or the `mcp source` commands, or choose another name. |
| Remove the second source or the server | `mcp source remove` fails with "Cannot remove the last source." | An MCP server needs at least one backend | Keep at least one backend, or delete the server with `az aigateway mcp delete`. |
| Add the server to VS Code<br>Call the tools from Python | `400` with `Unsupported MCP-Protocol-Version` | The client sent an `MCP-Protocol-Version` header that isn't in **Supported MCP versions** | Add the version to the list if every backend supports it, or let the client negotiate a listed version. |
| Add the server to VS Code<br>Call the tools from Python<br>List the published tools | `404` with "Federation tools/list failed: required endpoint '…' returned error: Backend selected protocol version '…' instead of '…'" | **Supported MCP versions** includes a version that this backend doesn't support, and the client negotiated it | Keep only versions that every backend supports. In the portal, edit and save each backend to recheck it. |
| Add the server to VS Code<br>Call the tools from Python | `400` with JSON-RPC error `-32603`, "The request cannot be completed using the requested protocol version." | A `2026-07-28` request reached a backend that doesn't support `2026-07-28` | Remove `2026-07-28` from **Supported MCP versions** until every backend supports it. |
| List the published tools<br>Send a raw JSON-RPC request | `400` with JSON-RPC error `-32602`, "Required MCP request metadata is missing or malformed." | A `2026-07-28` request lacks the `Mcp-Method` or `Mcp-Name` header, or `params._meta` | Use an MCP SDK that implements `2026-07-28` instead of hand-written requests. |
| Pin the version | The portal shows "Backend isn't compatible with all configured MCP versions." | The backend doesn't report support for every selected version | Return to **Basic info** and change **Supported MCP versions**, or update the backend. |
| Publish all tools<br>Create the registration<br>Deploy with azd up | Creating a server fails with `502 Bad Gateway`, or a Bicep deployment keeps running | Another MCP server in the gateway already uses the same display name | Choose a unique display name, for example with the Bicep `displayName` parameter. |

## Lab 05: Tool allow and block lists

Lab 05: [Control which tools agents can call](05-mcp-tool-controls/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Check the catalog<br>Call a blocked tool | A tool you blocked still appears in `tools/list` | Expected. Blocked tools remain visible, but the gateway blocks their execution | Call the tool to confirm that it's blocked. To hide a tool, leave it out of the allow list instead. |
| Check the catalog | `tools/list` returns no tools | The allow list matches nothing | Check the patterns against the exact tool names. |
| Turn the server back on<br>Call a blocked tool<br>Run the burst | `initialize` returns `AccessBlockedByGateway` | The server access is **Blocked** | Set **MCP server access** to **Active**, or run `azd env set MCP_SERVER_ACCESS active` and `azd provision`. |
| Check the catalog | An allowed tool is blocked | A blocked pattern also matches it. Blocked patterns take precedence | Make the blocked pattern narrower, for example `*code_sample*` instead of `*sample*`. |
| Call a blocked tool<br>Run the burst | `429` on the first request of a run | The previous step used up the window, or a **Gateway** scope rate limit also applies | Wait for `Retry-After`, and review **Policies** for every limit that covers the MCP server. |
| Run the burst | Never `429` | The policy is on another asset, it was saved moments ago, or the burst spans two windows | Check the policy's scope, wait a minute after you save it, and run a longer burst, for example `./infra/trigger-request-rate.sh learn 12`. |
| Replace the request rate limit and keep everything else | Other policies vanished after `mcp update` | `--policies` replaces the whole `policies` array | Always read the current array, merge, then update, as shown in the Azure CLI track. |
| Block the server (Bicep + azd)<br>Turn the server back on (Bicep + azd)<br>Change the limit | Tool rules or policies set in the portal vanished after `azd provision` | A Bicep deployment sends a `PUT`, which replaces the whole MCP server | Change the azd environment values and run `azd provision` instead of editing the server in the portal. |

## Lab 06: Token limits

Lab 06: [Throttle tokens per caller with token limits](06-token-limits/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Run the burst<br>Inspect one throttled response | Every request returns `200`, never `429` | The limit is on a different model or alias than the one you call, or the window reset between requests | Check that the request `model` matches an alias of the limited model. Run the burst without pauses. |
| Run the burst<br>Prove the counter is per caller | `429` on the very first request | Another token limit with a lower allowance applies, for example a **Gateway** scope policy, or the counter is shared because **Counter dimensions** is empty | Review **Policies** for every limit that covers the model. Pick **Caller identity** for per-caller counters. |
| Run the burst<br>Inspect one throttled response | `403` with `LlmCostQuotaExceeded` | A **Cost limit** blocked the call, not the token limit | See [Enforce cost budgets](07-cost-budgets/README.md). |
| Run the burst | `429` without a gateway token limit | The backend deployment ran out of TPM | Raise the deployment's capacity in Foundry, or lower per-caller gateway limits so their sum fits. |
| Replace the token limit and keep everything else<br>Remove the policy (REST API) | Other policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track. |
| Replace the token limit and keep everything else | `ValidationError` with target `counterKey` | `counterKey` is a string such as `"Identity"`, uses another value, or is missing | Send an array with `identity`, `ipAddress`, or both, for example `"counterKey": ["identity"]`. |

## Lab 07: Cost budgets

Lab 07: [Enforce cost budgets with per-caller overrides](07-cost-budgets/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Run the requests<br>Inspect one blocked response | Every request returns `200`, never `403` | The cost limit is on a different model than the alias you call, your key has an override, or the model is so cheap that the calls haven't reached the budget | Check **Applies to** on the policy details page, use a key without an override, and lower the budget to `0.001` or send more requests. |
| Run the requests | `403` with `LLM cost quota is exceeded` on the first request | The key already spent more than the new amount in this period (spend is kept when you edit), or a **Gateway** scope cost limit is exhausted | Review every **Cost limit** in **Policies**. Raise the amount, or wait for the next renewal period. |
| Prove the override and the per-caller counters | An Entra override doesn't apply | An earlier override matched first, the caller used an API key, or you entered a service principal's application ID | Remove the earlier override and add them again in the order you want. Call with an Entra token. Use the service principal's **object ID**. |
| Set the default budget | **Caller IP address** can't be selected in **Counter dimensions** | The policy has overrides | Remove all overrides, or keep **Caller identity**. |
| Run the requests | `429` instead of `403` | A **Token rate limit** or **Request rate limit** blocked the call, or the backend ran out of capacity | See [Throttle tokens per caller with token limits](06-token-limits/README.md). |
| Set the cost limit<br>Remove the cost limit | `'set-cost-limit' is misspelled or not recognized by the system` | The `aigateway` extension is older than `1.0.0b22`, the first version these labs use for `az aigateway model policy` | Run `az extension update --name aigateway`, as described in the [Setup guide](SETUP.md#install-the-aigateway-extension). |
| Add overrides in the portal | `--overrides` fails with `has no field apiKeyResourceId` or a similar schema error | In `1.0.0b22`, `--overrides` doesn't accept override objects | Add the overrides in the portal, or use the Bicep + azd track, which declares them. `set-cost-limit` keeps them when you change the amount later. |
| Lower the budget for the test<br>Run the requests | Every request returns `200` right after you lowered the budget | A policy change takes up to a minute to reach the gateway | Wait a minute and run the script again. The spend so far still counts. |

## Lab 08: Content safety

Lab 08: [Screen prompts and responses with content safety](08-content-safety/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Run the test prompts<br>Relax one category | Ordinary prompts return `400` | A threshold is too strict for your traffic, or another content safety policy, such as a **Gateway** scope policy, also applies | Review **Policies** for every content safety policy that covers the model. Move categories from **Strict** to **Balanced** and retest with representative prompts. |
| Run the test prompts | Nothing is ever blocked | The policy is on a different model or alias than the one you call, or a category is **Off** | Check the policy's scope and that the request `model` matches an alias of that model. |
| Run the test prompts<br>Relax one category | `400` that mentions `content_filter`, or `finish_reason` is `content_filter` | The Foundry deployment's **Content filter** acted, not the gateway | Review the deployment's content filter in Foundry. The gateway policy is managed separately. |
| Run the test prompts | `400` that isn't about content | The request itself is invalid, for example an unknown model alias | Read the error message, and check the request body and the alias. |
| Replace the content safety policy and keep everything else | `ValidationError` such as `contentSafety.violenceSeverity must be one of: Low, Medium, High, None.` | A severity uses a portal label such as `Strict` or `Balanced` | Use the API values from the table in [How it works](08-content-safety/README.md#how-it-works): `Low`, `Medium`, `High`, or `None`. |
| Replace the content safety policy and keep everything else<br>Remove the policy (REST API) | Other policies vanished after the `PATCH` | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the CLI and REST tracks. |

## Lab 09: Gateway-wide baselines

Lab 09: [Set gateway-wide policy baselines](09-gateway-baselines/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Call the model from your IP address<br>Layer a stricter model policy | Every call returns `403` | Your public IP address changed (new network, VPN, or hotspot), or your traffic to Azure leaves from a different address than the one `api.ipify.org` reported. A VPN, a corporate proxy, or a client such as Global Secure Access can do that | Check `curl -s https://api.ipify.org` again and update the IP filter. If you use a proxy, a VPN, or Global Secure Access, ask your network team for the egress ranges, or run the lab from Azure Cloud Shell. Management calls still work, so you can always fix the list. |
| See the IP filter block a call (optional) | `check-call` still returns `200` after you set `203.0.113.10/32`, or still `403` after you restore your range | Policy changes take up to a minute to reach the gateway | Wait a minute and run `check-call` again. |
| Watch outcomes in Monitoring | Teammates, pipelines, or hosted agents get `403` | Their egress addresses aren't on the allow list | Add their CIDR ranges, or remove the IP filter until you know them. |
| Call the model from your IP address<br>Layer a stricter model policy | Ordinary prompts return `400` | Content safety blocked them, from the baseline or from a stricter asset policy | Review every **Content safety** policy that covers the asset in **Policies**, and retest with representative prompts. |
| Layer a stricter model policy | `429` much earlier than the baseline allows | A tighter token or request rate limit on the model, alias, or MCP server applies | Review **Policies** for every limit that covers the asset. The lowest applicable limit wins. |
| Set the baseline<br>See the IP filter block a call (optional) | `ipFilter.cidrRanges entries must be valid CIDR ranges` | An entry has no prefix length, such as `198.51.100.7` instead of `198.51.100.7/32`, or `--allowed-ips` contains a space | Use CIDR notation for every entry, and pass the list without spaces, for example `--allowed-ips "[198.51.100.7/32,203.0.113.0/24]"`. |
| Set the baseline<br>Remove the baseline | `'policy' is misspelled or not recognized by the system` | The `aigateway` extension is older than `1.0.0b22`, the first version these labs use for the Gateway scope `policy` commands | Run `az extension update --name aigateway`, as described in the [Setup guide](SETUP.md#install-the-aigateway-extension). |
| Apply it | The `PATCH` returns a validation error about `counterKey` or `scope` | `counterKey` is a string such as `"Identity"` instead of an array, or the shape differs from what the API version expects | Use `"counterKey": ["identity"]`. If it still fails, create that policy once in the portal at **Gateway** scope, read the shape with the `GET`, and use it in your script or policy file. |
| Preview the change<br>Apply it<br>See the IP filter block a call (optional) | `Set ALLOWED_CIDRS ...` or `Use CIDR notation ...` from the script | `ALLOWED_CIDRS` is empty, or an entry has no prefix length | Set it to comma-separated CIDR ranges, for example `"$MY_IP/32"`. |
| Apply it<br>Remove the baseline | Other Gateway scope policies vanished after you called the management API yourself | `PATCH` replaces the whole `policies` array | Use the `az aigateway policy` commands, which keep the other policies, or always `GET`, merge, then `PATCH`, as the script does. |
| Preview the change<br>Apply it | `jq: command not found` | `jq` isn't installed | Install `jq`, or use the PowerShell commands. |

## Lab 10: Runtime API keys

Lab 10: [Issue and rotate runtime API keys](10-api-keys/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Run the checks<br>Check that the rotated key still works | A new key gets `401` | The value has a space or line break, or an MCP client sends it in `Authorization` instead of `api-key` | Copy the value again and send it as `api-key: <value>`. |
| Any step | `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header | Send one of them. With an OpenAI SDK, pass the key as the SDK's API key and remove the extra header. |
| Rotate the key<br>Check that the rotated key still works | `401` right after **Rotate key** in the portal | Portal rotation replaces the primary value immediately | Give the client the value from **API key rotated successfully**. Next time, use the CLI secondary-value flow. |
| Create the first key<br>Create the other two keys | "The key was created, but its value couldn't be retrieved." | You don't have `Microsoft.ApiManagement/aigateways/apiKeys/listSecrets/action` | Use **Rotate key** to get a new value, or ask someone with that permission, such as a Contributor, to read it. |
| Move the client to the secondary value<br>Run the checks<br>Check that the rotated key still works | `check-key` prints `not checked` with `HTTP 404` | The gateway doesn't know the alias in `AI_GATEWAY_MODEL`, so it never checked the key | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| Check that the rotated key still works | A key that worked gets `401`, and nobody rotated it | The key is `suspended` | Check `state` with the list command, and set it back to `active` if the suspension is over. |
| Move the client to the secondary value<br>Run the checks<br>Check that the rotated key still works | `check-key` prints `key accepted, but the call failed` | The key works, but `AI_GATEWAY_MODEL` isn't an alias you can call, or a policy blocked the request | Set `AI_GATEWAY_MODEL` to an alias from **Models**, for example the one from lab 02. |
| Save the current value<br>Regenerate the unused secondary value<br>Regenerate the primary value | `Forbidden`, `ForbiddenByConnection`: "Public network access is disabled and request is not from a trusted service nor via an approved private link." | An Azure Policy in your organization turns off public network access on new key vaults, and keeps it off even after `az keyvault update --public-network-access Enabled` | Ask your Azure administrator for a policy exemption for the lab's resource group, or run the Key Vault commands from a network that reaches the vault through a private endpoint. |
| Regenerate the unused secondary value<br>Regenerate the primary value<br>Load the app-dev key | `Forbidden` from `az keyvault secret set` or `secret show` | You have no data-plane role on the vault, or the role assignment hasn't applied yet | Assign **Key Vault Secrets Officer** on the vault and wait a few minutes. |
| Any step | Monitoring shows no caller identities | Monitoring isn't configured, or the time range has no traffic | Complete [Monitor usage, cost, and traces](13-monitoring/README.md), send requests with each key, and widen the time range. |

## Lab 11: Entra ID and RBAC

Lab 11: [Go keyless with Microsoft Entra ID and RBAC](11-entra-rbac/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Call the model with the bearer token<br>Confirm the keyless call succeeds<br>Restore access | `401` on every Entra call | The token is expired, or it was issued for another audience, such as Azure Resource Manager | Request a new token for `https://azure-api.net/aigateway` (`.default` for app-only callers). Check `aud` in the decoded token. |
| Send a prompt<br>Call the model with the bearer token<br>Run it<br>Restore access | `403` right after you assigned the role | Role assignments take several minutes to apply | Wait and retry with a fresh token. In the playground, use **Back to playground** after reviewing access. |
| Send a prompt<br>Call the model with the bearer token<br>Run it | `403` for one model or MCP server only | The role is scoped to a different alias or MCP server, or the role doesn't cover it (Models User on an MCP server, Tools User on a model) | Assign a compatible role at the gateway or at that alias or MCP server. |
| Send a prompt<br>Call the model with the bearer token<br>Run it | `403` even though the role is correct | A gateway policy (for example a cost limit), the request proxy, or the backend rejected the call | Read the error code in the response body before changing permissions. `LlmCostQuotaExceeded` comes from a cost limit. |
| Review and assign<br>Create the role assignment<br>Use the helper for other roles and scopes<br>Deploy with azd up | `AuthorizationFailed` when you create the assignment | You have **Contributor**, which can't write role assignments | Ask an **Owner**, **User Access Administrator**, or **Role Based Access Control Administrator** to assign the role. |
| Run it | `DefaultAzureCredential failed to retrieve a token` | No sign-in is available to the credential chain | Run `az login`, or sign in to the Azure extension in your IDE, then rerun the sample. |
| Select identities | Your name doesn't appear when you search for it | Name search in the directory is off | Turn on **Allow directory search**, or paste your object ID (`MY_OBJECT_ID`), which works without it. |
| Confirm the assignment<br>Read the outputs<br>Remove the role and try again | `az role assignment list --scope "$GATEWAY_ID"` doesn't show a role that you assigned in the portal | The portal assigns roles at the gateway's `/workspaces/default` scope, and the list doesn't include child scopes | List with `--all --assignee "$MY_OBJECT_ID"` and the `starts_with(scope, '$GATEWAY_ID')` filter, as the lab does. |

## Lab 12: Backend identities

Lab 12: [Call backends with managed identities](12-backend-identity/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Call the model through the gateway | `403` mentioning permissions on the Foundry account right after the switch | The role assignment hasn't propagated, or it's at a different scope than the Foundry account | Wait a few minutes. Check `az role assignment list --assignee "$IDENTITY_PRINCIPAL_ID" --scope "$FOUNDRY_ID" -o table`. |
| Call the model through the gateway | Calls fail after the switch and the role is in place | `clientId` holds the principal (object) ID, or the identity isn't attached to the gateway | Use the identity's **Client ID**, and check that `az aigateway identity show -g "$RG" -n "$GATEWAY" --query userAssignedIdentities` lists the identity. |
| Attach it to the gateway | `az aigateway identity assign` fails with an authorization error | You can't assign that identity to resources | Ask for **Managed Identity Operator** on the identity. |
| Check it with the CLI | `az aigateway identity show` reports that no identity is assigned to the gateway | The gateway has no managed identity | Enable it with `az aigateway identity assign` in [Check the system-assigned identity](12-backend-identity/README.md#check-the-system-assigned-identity), then grant it **Foundry User**. |
| Detach the identity from the gateway<br>Remove the role assignment and delete the identity | Calls fail after you detach an identity or disable the system identity | An asset still uses that identity | Check **View access** › **Backend access** before you remove an identity, and switch those assets first. |
| Check it with the CLI<br>Grant Foundry User on the Foundry account<br>Deploy with azd up | `AuthorizationFailed` on `roleAssignments` | You can't create role assignments on the Foundry account | Ask for **Role Based Access Control Administrator** on the account, or have an owner grant the role. |

## Lab 13: Monitoring

Lab 13: [Monitor usage, cost, and traces](13-monitoring/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Overview: is the gateway healthy, and what does it cost?<br>Confirm all signals are flowing | "Enable all telemetry signals" on the dashboard | Metrics, logs, or traces is turned off | Select **Open Monitoring settings** and set all three endpoints, or disable monitoring and configure it again with Application Insights. |
| Start the setup<br>Confirm all signals are flowing | "This legacy exporter no longer activates OTLP signals" in **Settings** | The exporter has kind `applicationInsights`, for example from the reference sample's Bicep or a setup before 2026-08-28 | Select **Settings** › **General** › **Disable monitoring**, then **Configure telemetry** again with the same Application Insights resource. |
| Apply the configuration<br>Let the gateway publish<br>Deploy with azd up | **Assign Monitoring Metrics Publisher role** fails, or `az role assignment create` returns `AuthorizationFailed` | You can't create role assignments on the destination | Ask an **Owner** to grant the role on the Data Collection Rule, or to run the setup. |
| Apply the configuration | **Discover OTLP endpoints** fails with "Could not resolve the Data Collection Rule" | OTLP support was just enabled and Azure is still provisioning it | Wait a few minutes, then select **Retry**. |
| Deploy with azd up | The `postprovision` hook fails with "has no OTLP endpoints after 10 minutes" or "The telemetry exporter deployment failed" | Azure is still creating the OTLP endpoints, or the new role assignment hasn't propagated yet | Wait a few minutes, then run `azd hooks run postprovision`. Running `azd provision` again doesn't help: when the templates haven't changed, azd skips the deployment and its hooks. |
| Overview: is the gateway healthy, and what does it cost?<br>Models: who uses which model, and how many tokens? | "Model token and estimated cost data are incomplete until you add a Prometheus access token" | The portal can't read the metrics workspace with your session | Paste a token from `az account get-access-token --resource https://prometheus.monitor.azure.com --query accessToken -o tsv` into **Prometheus access token**. |
| Overview: is the gateway healthy, and what does it cost?<br>Run the starter queries<br>Match the dashboard to your traffic | Dashboard and queries are empty | No traffic in the selected range, or ingestion is still catching up | Widen the time range, wait a few minutes, and run the traffic script again. |

## Lab 14: OpenTelemetry chargeback

Lab 14: [Attribute tokens and cost with OpenTelemetry](14-otel-chargeback/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Open the token claim attributes<br>Add metrics for the client app (Portal) | No **Token claim attributes** section in **Settings** | The exporter is the legacy `applicationInsights` kind | Disable monitoring and configure it again, as in [Monitor usage, cost, and traces](13-monitoring/README.md). |
| Change the claims | The claims don't change after `azd provision` | The templates haven't changed, so azd skipped the deployment and the `postprovision` hook that deploys the exporter | Run `azd hooks run postprovision`. |
| Deploy with azd up | The `postprovision` hook fails with "has no OTLP endpoints after 10 minutes" or "The telemetry exporter deployment failed" | Azure is still creating the OTLP endpoints, or the new role assignment hasn't propagated yet | Wait a few minutes, then run `azd hooks run postprovision`. |
| Call the gateway as two callers | The `entra` rows return `401` or `403` | Wrong token audience, or no **AI Gateway Models User** role yet | Get the token for `https://azure-api.net/aigateway`, check the role assignment, wait a few minutes, and get a new token. |
| Find your callers in Monitoring<br>Compare the report with the dashboard | Entra callers show as **Unattributed** on **Models** | `tid` or `oid` isn't exported to **Metrics** | Select **Metrics** for both and send new traffic. Earlier requests stay unattributed. |
| Run the query | The chargeback query returns no rows | Telemetry hasn't arrived, the **Logs** signal is off, or your API reports usage under other names | Wait a few minutes, then run `OTelLogs \| where TimeGenerated > ago(1h) \| take 5` and compare the `Attributes` with the query. |
| Run the query<br>Price it | `Tenant` or `ClientApp` is empty for Entra rows | The claim wasn't exported to **Logs** when the request ran | Enable **Logs** for the claim and send new traffic. |
| Query token usage for the last day<br>Query estimated cost | The Prometheus query returns `401` or `403` | Your account can't read the Azure Monitor workspace | Ask for a data read role on the Azure Monitor workspace, such as **Monitoring Data Reader**, then get a new token. |

## Lab 15: Agent frameworks

Lab 15: [Connect agent frameworks to models and tools](15-agent-frameworks/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Run each sample | `401` from the model or MCP endpoint | The key is missing, wrong, or revoked, or the header isn't sent | Check `AI_GATEWAY_API_KEY` in `.env` and that the key exists under **Access** › **API keys**. A value set in your shell overrides `.env`. |
| Run each sample | `404` from the MCP endpoint | `AI_GATEWAY_MCP_SERVER` doesn't match an MCP server name | Copy the name from **MCP servers**, or the endpoint from the server's page. |
| Run each sample | A `4xx` error that mentions the model | `AI_GATEWAY_MODEL` isn't a callable alias | Copy the alias exactly from the model's **Aliases** tab. |
| Run each sample | The agent answers without citing any URL | The MCP server publishes no tools, or tool controls block them | Run `list_tools.py` from [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md) and check the server's tool controls. |
| Run each sample | `429` responses | A token limit or rate limit on the alias, MCP server, or gateway | Expected when a policy applies. Wait for `Retry-After`, or raise the limit. |
| Run each sample | `400`: `Function tools with reasoning_effort are not supported for <model> in /v1/chat/completions` | An older copy of a sample calls Chat Completions with tools on a reasoning model that takes function tools only on Responses | Pull the latest samples, which call the Responses API. Or send `reasoning_effort: "none"` with Chat Completions. |
| Run each sample<br>Prove the gateway is in the path | `ModuleNotFoundError` | The virtual environment isn't active | Activate `.venv` and run `pip install -r requirements.txt` again. |

## Lab 16: Foundry hosted agent

Lab 16: [Deploy a Foundry hosted agent behind AI Gateway](16-foundry-hosted-agent/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Ask the hosted agent<br>Trigger the limit | `ERROR: agent failed (server_error): An internal server error occurred.` | A model or tool call failed inside the agent, and Foundry hides the details | Run `azd ai agent monitor gateway-agent --tail 300` and look for `Error code`, then use the rows below. |
| Ask a question<br>Ask the hosted agent | `403` "Access denied. You do not have permission to access the requested resource. Ask an administrator to grant the required Azure role." | The caller has no AI Gateway role, or the assignment hasn't applied yet. Locally, the caller is you; in Foundry, it's the agent's identity. | Assign **AI Gateway User**, as in **Give the project and yourself access** and **Give the agent access**, then wait about two minutes. |
| Ask a question<br>Ask the hosted agent | `404` from the model endpoint | `AI_GATEWAY_MODEL` doesn't match an alias | Copy the alias exactly from the model's **Aliases** tab, run `azd env set AI_GATEWAY_MODEL`, then `azd deploy --all`. |
| Ask the hosted agent<br>Trigger the limit | `429` "Token limit is exceeded" in the agent's logs, while local runs still work | A token limit counted per caller identity, such as the one from this lab: the agent's identity spent its tokens, and you have your own counter | Wait for the time in the message, or remove the policy. |
| Ask a question<br>Ask the hosted agent | `429` "Your requests to … have exceeded token rate limit" | The Foundry deployment behind the alias ran out of tokens per minute, not the gateway's limit. A fetch of a whole Microsoft Learn article can spend most of a 10,000-tokens-per-minute quota in one call. | Wait a minute, or raise the deployment's capacity. Keep the instruction in `main.py` that answers from the search results. |
| Ask a question<br>Ask the hosted agent | The agent answers that it can't reach Microsoft Learn, and its log shows "Access denied when connecting to the MCP server at …/toolservers/learn/mcp while calling tool … (HTTP 403 Forbidden)" | The agent's MCP client negotiated version `2026-07-28` with the toolbox, which then sends `server/discover` to the gateway's `learn` server. That server supports only the versions of its backend, and answers with `403`. | Keep `HandshakeClient` in `main.py`, which opens the toolbox connection with the `initialize` handshake. Your roles are fine when a direct call to the MCP server works. |
| Ask a question<br>Ask the hosted agent | `429` from tool calls | A request rate limit on the `learn` server, for example from [Control which tools agents can call](05-mcp-tool-controls/README.md) | Wait for the `Retry-After` time, or remove the policy from the MCP server. |
| Create an azd environment<br>Provision the Foundry project | `AZURE_SUBSCRIPTION_ID is required` or `no default response for prompt 'Select an Azure Subscription to use'` | azd runs without prompts in a script, a CI job, or a coding agent, so it can't ask for the subscription | Run `azd env new` with `--subscription "$(az account show --query id -o tsv)"`, as the lab does, or `azd env set AZURE_SUBSCRIPTION_ID` before `azd provision`. |
| Start the agent<br>Ask the hosted agent | `RuntimeError: Set AI_GATEWAY_URL` | An azd environment value is missing | Run `azd env set` for the missing value, then `azd ai agent run` or `azd deploy --all`. |
| Find the agent's identity | `AGENT_GATEWAY_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID` is empty | The agent's identity exists only after the first deployment | Run **Deploy the connection, the toolbox, and the agent** first. |
| Ask the hosted agent | The hosted agent still uses an old value | Foundry reads environment variables when the agent version is created | Run `azd deploy --all` after every `azd env set`. |
| Deploy the connection, the toolbox, and the agent | `[CodeError] [tool.poetry] section not found` during deployment | A `pyproject.toml` without a lock file was added to `src/gateway-agent` | Keep `requirements.txt` as the dependency file, or commit a `uv.lock` next to `pyproject.toml`. |
| Deploy the connection, the toolbox, and the agent | `WARNING: gateway-agent (predeploy): AZURE_CONTAINER_REGISTRY_ENDPOINT not set; skipping ACR role check.` | The agent builds from code on Foundry, so there's no container registry | Expected on the first deployment. Ignore it. |
| Start the agent | `azd ai agent run` can't download packages, with a certificate error | A proxy on your network inspects TLS traffic | Set `UV_SYSTEM_CERTS=true` (`UV_NATIVE_TLS=true` in older uv versions) so uv trusts your system certificates, then run it again. |

## Lab 17: Coding-agent plugin

Lab 17: [Build on your gateway with coding agents](17-coding-agent-plugin/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Check that the commands are available | `/ai-gateway:discover` isn't recognized | The plugin isn't installed or the client hasn't reloaded it | Repeat the install for your agent, then restart it. Check with `copilot plugin list` in GitHub Copilot CLI or `gemini extensions list` in Gemini CLI. |
| Run discover with your resource ID<br>Read the summary | The plugin can't list models, or Azure returns `401` or `403` | `az` is signed in to another tenant or subscription, or your account can't read the gateway | Run `az account show`, then `az account set --subscription <subscription-id>`. Ask for read access to the gateway. |
| Answer the plugin's questions | The plugin stops at the credential step | Your account can't list key secrets on the gateway | Create or get a key as in **Before you begin**, and tell the agent to read it from `AI_GATEWAY_API_KEY`. |
| Run the app | `404 Resource not found` from the gateway | The URL is missing the `/default/` segment | Use `<gateway URL>/default/models/openai/v1` or `<gateway URL>/default/toolservers/<name>/mcp`. |
| Run the app | `unknown_model` | The model name isn't one the gateway publishes, the client uses another protocol than the model supports, or a GitHub Copilot SDK older than 1.0.0 drops the key header | Use the name that discover reported or your alias. Pin `github-copilot-sdk>=1.0.0`. |
| Run the app<br>Confirm the key and model outside the generated code | `401` from the gateway | The key is missing or deleted, or an MCP call sends it as a bearer token. The MCP endpoint reads keys only from the `api-key` header. | Send the key in the `api-key` header. Create a new key if you deleted it. |
| Run the app | `400` "Specify either an API key or an Authorization header, not both" | The client sends the key in `api-key` and also an `Authorization` header, as SDKs do when you pass a placeholder key | Send only one. For the model endpoint, pass the runtime key as the SDK's API key and drop the extra `api-key` header. |
| Run the app | `KeyError: 'AI_GATEWAY_API_KEY'` | `.env` wasn't loaded, often because PowerShell saved it with a byte order mark | Export the variable in your shell, or save `.env` as UTF-8 without a byte order mark. |
| Run the app<br>Confirm the key and model outside the generated code | `429` | A token limit or the backend's quota | The wiring works. See [Throttle tokens per caller with token limits](06-token-limits/README.md). |
| Read the summary | A tool server shows `0` tools | The server exposes no tools, or tool availability hides them | Check the server's tools in the portal, or see [Federate MCP tools behind one endpoint](04-federate-mcp-tools/README.md). |

## Lab 18: Private networking

Lab 18: [Lock down backend traffic with private networking](18-private-networking/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Choose private routing<br>Create the gateway in the integration subnet<br>Deploy with azd up | The create dialog flags the subnet, or the create request fails with a subnet error | The subnet is in another subscription or region, smaller than `/27`, not delegated to `Microsoft.App/environments`, used by another gateway or resource, or its NSG lacks the 443 rules | Fix each item. The NSG needs outbound TCP 443 allow rules to the `Storage` and `AzureKeyVault` service tags. |
| Choose private routing<br>Create the gateway in the integration subnet<br>Deploy with azd up | The create request fails with `AIGatewaySubnetNotDelegated`: "Virtual network integration with subnet ID '…' requires the subnet to be delegated to 'Microsoft.App/environments'." | The subnet isn't delegated, or it's delegated to another service, such as `Microsoft.Web/serverFarms` | Delegate the subnet to `Microsoft.App/environments`, then create the gateway again. |
| Choose private routing | The portal's subnet check shows a warning: "Subnet delegated to Microsoft.Web/serverFarms" | The portal check still expects the old delegation | Expected. Keep `Microsoft.App/environments` and continue. |
| Create the gateway in the integration subnet<br>Disable public network access on Foundry (Bicep + azd) | "Virtual network integration for Azure AI Gateway can only be configured during creation." | An older service version, or an older Azure CLI extension, that couldn't change private routing on an existing gateway | Update the extension with `az extension update --name aigateway`, then use **Networking** › **Outbound** in the portal or `az aigateway network update --subnet` (or `--disable-vnet-integration`). The change takes a minute or two. |
| Call the model through the gateway | Model calls through the new gateway fail after you turn off Foundry public access | The gateway resolves Foundry to its public IP: the zones aren't linked to the integrated virtual network, the private endpoint has no DNS zone group, or the gateway was created without private routing | Check the `A` records and zone links, and confirm that `properties.backend.subnet.id` points to the integration subnet. |
| Disable public network access on Foundry | The gateway from the earlier labs, or another app, now gets `403` from Foundry | It reaches Foundry over the internet, and Foundry's public access is disabled | Expected. Use a dedicated Foundry resource for this lab, or re-enable public access when you finish. |
| Create a runtime API key<br>Check the model and the key<br>Call the model through the gateway | The first call after the import returns `401` or `403` from the backend | The **Foundry User** role assignment hasn't propagated yet | Wait a few minutes, and confirm that the role is assigned to the new gateway's principal ID on the Foundry resource. |
| Enter the gateway details | **Public network access** › **Disabled** is greyed out, or `az aigateway network update --public-network-access Disabled` (or a `PATCH`) succeeds but `publicNetworkAccess` stays empty and the endpoint stays public | Private frontend access isn't available for AI Gateway yet | Expected. Protect the public endpoint with keys or Microsoft Entra ID and an `ipFilter` policy. |
| Delete the lab's resources<br>Delete everything azd created | Deleting the resource group or the virtual network fails because the subnet is in use | The service is still releasing the gateway's integration subnet | Wait a few minutes after the gateway is gone, then delete again. |

## Lab 19: Tool threat protection

Lab 19: [Protect tool calls with Agent 365 threat protection](19-tool-threat-protection/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Call the protected tool with your user token | Every protected call returns `ToolEvaluationIdentityRequired` | The call has no bearer token, or the token isn't a delegated user token. App-only tokens and runtime keys can't be used for OBO. | Sign in with `az login` as a user, get a token for `https://azure-api.net/aigateway`, and send it as `Authorization: Bearer`. Check that the token has an `scp` claim. |
| Call a tool with your user token<br>Call the protected tool with your user token | `tools/call` returns HTTP `401` or `403` with a bearer token | The user has no data-plane role on the MCP server, or the assignment hasn't applied yet | Assign **AI Gateway Tools User** at the MCP server or gateway scope and wait a few minutes |
| Call the protected tool with your user token | Calls return `ToolEvaluationUnavailable` | The token exchange or the evaluation failed, timed out, returned an invalid verdict, or the evaluator was unavailable | Retry later. If it persists, confirm the Microsoft Defender or Microsoft Purview license and the Defender policy mode with your security team, and share the `correlationId`. |
| Call the protected tool with your user token | A benign call returns `ToolEvaluationDenied` | Defender or Purview flagged the request or the result | Review the call with your security team using the `correlationId`. If the tool already ran (after-invocation stage), don't retry it automatically. |
| Select the MCP server<br>Choose the evaluation stages | You can't add a second tool threat protection policy to the server | Each MCP server can have only one tool threat protection policy | Keep the existing policy, or delete it and add a new one with the stages you want |
| Call the protected tool with your user token | Tool calls got noticeably slower | Each enabled stage adds an evaluation round trip | Keep both stages where you need them, and use only **Before tool invocation** where results are trusted |
| Call a tool with your user token<br>Call the protected tool with your user token | A script stops with HTTP `503` and `{"error":"App port is not ready"}` | The gateway is still starting after `azd up` or `azd provision` | Wait 30 seconds and run the script again. |
| Turn on both stages<br>Confirm the policy | A policy you added in the portal vanished after `azd provision` | A Bicep deployment sends a `PUT`, which replaces the whole MCP server | Change the azd environment values and run `azd provision` instead of editing the server in the portal. |

## Lab 20: Agent 365 governance

Lab 20: [Govern MCP servers with Agent 365](20-agent-365-governance/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Find your MCP server | The gateway's MCP servers don't appear under **Agents** › **Tools** | Consent isn't granted, or the instance is on an API Management v1 tier | Have a tenant administrator turn on **Azure API Management service and AI Gateway** under **Agents** › **Settings** › **Gateways**. Use a v2 tier or the AI Gateway tier. |
| Turn off the tool in Agent 365 | The server's **Tools** tab can't list its tools | The server doesn't have a static list of allowed tools, for example it uses **Allow all tools** | In the AI Gateway portal, choose **Select exact tools** on the server's **Tools** step. Otherwise, block tools in the AI Gateway portal. |
| Turn off the tool in Agent 365 | You can't block individual tools | The instance is on an API Management v2 tier | Tool-level blocking needs Azure AI Gateway. Block the whole server instead. |
| Call the blocked tool | A blocked tool still runs for some agents | Those agents call the MCP server directly, not through the gateway | Point every agent at the gateway's MCP endpoint and restrict direct access to the backend |
| Call the blocked tool | An agent keeps retrying a blocked tool | The agent ignores `isError` | Check `result.isError` and the `ToolNotAvailable` denial code, and stop retrying that tool |
| Unblock the server<br>Confirm the server works end to end | Calls still fail after you unblock | Another control blocks them, such as the gateway's **Blocked tools**, **MCP server access**, or a policy | Check the server's **Basic info** and **Tools** steps and its policies in the AI Gateway portal |

## Lab 21: Enterprise reference

Lab 21: [Deploy an enterprise reference architecture](21-enterprise-reference/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Deploy<br>Run it | The deployment fails with `InsufficientQuota`, or the model or version isn't available | The region has no `GlobalStandard` quota for `gpt-5-mini`, or doesn't offer that version | Lower `modelCapacity`, request quota, or change `modelName`, `modelVersion`, or `--location` in your parameter file and command. |
| Deploy<br>Run it | The gateway's `provisioningState` ends in `Failed` | Azure hit an activation or managed identity conflict, often after a gateway with the same name was deleted moments before | Delete the failed gateway, wait about three minutes for the identity to be cleaned up, and deploy again. |
| Run it<br>Run the smoke test | The smoke test prints `Waiting for the model route` until it fails with `401`, `403`, or `404` | The new Foundry User role assignment or the model route hasn't propagated yet | Wait a few minutes and run the smoke test again. If it still fails, run the backend identity checks in [Verify](21-enterprise-reference/README.md#verify). |
| Connect telemetry<br>Run it | The telemetry script stops with "has no OTLP endpoints after 10 minutes" | Azure hasn't finished creating the component's OTLP endpoints | Wait a few minutes and run the script again. If it still fails, check that the component's `AzureMonitorWorkspaceIngestionMode` is `Enabled`. |
| Connect telemetry<br>Run it | The telemetry script fails with `AuthorizationFailed` on `roleAssignments` | The identity that runs it can't create role assignments on the Data Collection Rule | Use the same rights as the deployment: **Owner**, or **Role Based Access Control Administrator**, on the subscription. |
| Connect telemetry<br>Run it | `aigw-telemetry` fails with "Telemetry exporter kind cannot be changed after creation." | An exporter with the same name has another kind, and the script couldn't read it to replace it, for example because the `aigateway` extension isn't installed | [Install the `aigateway` extension](SETUP.md#install-the-aigateway-extension), then run the script again. It replaces the exporter. |
| Apply the gateway baseline<br>Run it | `apply-baselines` fails with a validation error from the `PATCH` | A field in `baselines.json` doesn't match the current API contract, for example `counterKey` as a string instead of an array such as `["identity"]` | Create the policy once in the portal at **Gateway** scope, read the workspace with `az rest`, and copy that shape into `baselines.json`. |
| Run it | `azure/login` fails with `AADSTS70021: No matching federated identity record found` | The token subject doesn't match a federated credential | Check that the subject is exactly `repo:<github-org>/<github-repo>:environment:<name>` and that the GitHub environment name matches the job's `environment:`. |

## Lab 22: Priority and weighted routing

Lab 22: [Route an alias across models by priority and weight](22-model-routing/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Create the chat alias (Portal) | "Select models with at least one common API format." | The selected backend models don't share an interface, for example an Anthropic Messages model and an OpenAI Chat Completions model | Put models that share an interface in the same alias. |
| Create the chat alias<br>Edit the alias<br>Update the priorities | "Weight must be a whole number from 1 to 100.", `Each target's weight must be a whole number from 1 to 100.`, or `weight must be between 1 and 100.` | A weight is `0`, negative, or above `100` | To stop traffic to a model, raise its priority number or remove it. |
| Create the chat alias<br>Edit the alias<br>Update the priorities<br>Promote the new model | "Priority must be a whole number from 0 to 100.", `Each target's priority must be a whole number from 0 to 100.`, or `priority must be between 0 and 100.` | A priority is outside `0` to `100` | Use `0` for the preferred tier and higher numbers for the others. |
| Create the chat alias<br>Update the priorities<br>Promote the new model | "Each backend model can appear only once." or `backendModels must not contain duplicate model identities.` | The same backend model is listed twice | Combine the entries and adjust the weight. |
| Create the chat alias<br>Read the outputs and the key | All requests go to one model | The models have different priorities, so only the lowest number receives traffic | Give the models the same priority to split by weight. |
| Create the chat alias<br>Read the outputs and the key<br>Promote the new model | `404` with `DeploymentNotFound` | The candidate backend model points to a Foundry deployment that doesn't exist | Create the deployment, or fix `deployment.resourceId` on the backend model. |
| Create the chat alias<br>Read the outputs and the key | The first requests of the count return `HTTP 404 model_not_found` | The new alias takes a few seconds to reach the gateway | Wait a few seconds and run the count again. |
| Count the requests again | One of the first requests shows `gpt-6.1-sol-…` | The priority change takes a few seconds to reach the gateway | Run the count again. Every request then shows `gpt-5-mini-…`. |
| Count the requests again<br>Promote the new model | `429` from the preferred model | The preferred deployment is out of capacity, and the gateway returns the error | Retry in the client, add capacity, or spread traffic with weights at the same priority. |

## Lab 23: Streaming responses

Lab 23: [Stream responses and count every token](23-streaming-responses/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Stream from code<br>Run the sample | `IndexError: list index out of range` in Python, or `Cannot read properties of undefined` in TypeScript | The code reads `choices[0]` on the prompt filter chunk or the usage chunk, which have no choices | Skip chunks whose `choices` array is empty, as the samples do. |
| Watch the raw events<br>Stream with the script | The whole reply appears at once | curl runs without `-N`, PowerShell uses `Invoke-RestMethod`, or a proxy buffers the response | Use `curl -N`, read the stream with `HttpClient` as `stream-chat.ps1` does, and turn off response buffering in your proxy. |
| Ask for usage at the end of the stream<br>Run the sample<br>Stream a burst with usage | No usage chunk at the end of the stream | The client didn't set `stream_options.include_usage` | Set it when your app needs the numbers. The gateway counts the tokens for its limits either way. |
| Ask for usage at the end of the stream | `400` with `The 'stream_options' parameter is only allowed when 'stream' is enabled.` | The request sets `stream_options` without `"stream": true` | Send both, or neither. |
| Stream a burst without asking for usage<br>Stream a burst with usage<br>Inspect a throttled streaming request | `429` JSON response instead of a stream | A token limit on the alias, the model, or the gateway is exhausted | Wait for `Retry-After` seconds. The limit is checked before the stream starts, so no partial reply is lost. |
| Run the sample | The SDK sample never shows a `429` | The OpenAI SDKs retry `429` responses automatically and honor `Retry-After` | That's the behavior you want in an app. To see each `429`, create the client with `max_retries=0` (Python) or `maxRetries: 0` (TypeScript). |
| Stream a burst without asking for usage<br>Stream a burst with usage | Every request in the burst returns `200` | The policy isn't active yet, or the burst used another alias | Check that `STREAM_ALIAS` matches the alias with the limit, wait a minute, and run the burst again. |

## Lab 24: GitHub Copilot BYOK

Lab 24: [Use your gateway's models and tools in GitHub Copilot](24-github-copilot-byok/README.md)

| Step | Symptom | Likely cause | Fix |
|---|---|---|---|
| Deploy the model in Foundry<br>Deploy with azd up | `InsufficientQuota`: `The deployment requires 100 quota units, but only 0 quota units are available` | The subscription's Global Standard capacity for `gpt-6.1-sol` in the region is used up | In the Azure CLI track, deploy with `--sku-name DataZoneStandard`. With azd, run `azd env set BYOK_MODEL_SKU DataZoneStandard` and `azd up` again. Or deploy in another region. |
| Pick the model and run an agent task<br>Ask a quick question<br>Run a sample<br>Start a session on gpt-6.1-sol<br>Turn Copilot back on | `HTTP 401` or "Authentication failed with provider" | The key is wrong, suspended, or deleted, or the new key isn't active yet | Check the key's state in **Access** › **API keys**, wait a minute after you create it, and paste it again. |
| Run a sample | `400` on every request from a custom client | The request sends both `Authorization` and `api-key` | Send one of them. Copilot sends `Authorization: Bearer` only. |
| Pick the model and run an agent task<br>Ask a quick question<br>Run a sample<br>Start a session on gpt-6.1-sol | `404`, or a "model not found" error | The model name isn't an alias on the gateway, for example the portal import's `<foundry-account-name>/gpt-6.1-sol` | Publish the `gpt-6.1-sol` alias, or set the model ID to the alias that exists. |
| Pick the model and run an agent task<br>Start a session on gpt-6.1-sol | The model doesn't appear in VS Code or the app | The gateway has no `/models` list to discover, or VS Code hasn't reloaded the file | Add `gpt-6.1-sol` by hand, then run **Developer: Reload Window** in VS Code. |
| Pick the model and run an agent task | The model is missing from the picker in Agent mode | `toolCalling` is missing or `false` | Set `"toolCalling": true` on the model. |
| Add the gateway as a custom endpoint<br>Add the gateway as a model provider | VS Code or the app doesn't offer your own models at all | Your Copilot Business or Enterprise organization hasn't allowed custom models | Ask an administrator to enable them. |
| Pick the model and run an agent task<br>Ask a quick question<br>Run a sample<br>Start a session on gpt-6.1-sol | Replies are empty or cut off, or tool calls fail | The surface uses Chat Completions with a reasoning model | Set the API to Responses: `apiType` in VS Code, `COPILOT_PROVIDER_WIRE_API=responses` for the CLI, `wireApi` in the SDK. |
| Pick the model and run an agent task<br>Run an agent task | `429 Too Many Requests` | Copilot used the key's 100,000 tokens for this minute | Wait for the `Retry-After` interval, or raise the token limit. |
| Run an agent task | The CLI's first interactive prompt doesn't respond | A slow first connection | Press <kbd>Ctrl</kbd>+<kbd>C</kbd> and send the prompt again. |
| Pick the model and run an agent task | Two **GPT-6.1 Sol** entries in VS Code's model picker | Copilot's built-in model and yours share a name | Give yours a distinct `name`, such as `GPT-6.1 Sol (AI Gateway)`. |
| Start the server<br>Check the tools in a session<br>Run a sample with the tools<br>Check the server | The MCP server doesn't start, or returns `401` | The key is sent as a bearer token, or `${AI_GATEWAY_API_KEY}` is empty where the CLI or the app runs | Send the key in the `api-key` header. Export `AI_GATEWAY_API_KEY` in the terminal, or make it available to the app and reopen it. |
| Test the MCP endpoint | `jq: error … Cannot iterate over null` right after you create the server | The new `learn` server is still taking effect, so the reply has no `result` | Wait a minute and run the step again. |
| Use the tools in one-shot mode | `copilot -p` doesn't use the Learn tools, or says they were denied | One-shot mode can't ask for approval | Add `--allow-tool='ai-gateway-learn'`. |
| Run a task with the tools<br>Use the tools in one-shot mode<br>Run a sample with the tools | A task with the Learn tools hits `429` or uses many tokens | Each Learn result is 25 to 50 KB | Ask for fewer lookups, publish fewer tools, or raise the token limit. |
| Check the tools | VS Code lists MCP servers that you didn't add | VS Code discovers servers configured in other apps | Set `chat.mcp.discovery.enabled` to `false`. |
