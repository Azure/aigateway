# Choose assets by the job they can do

Use this reference when discovery must explain a choice, not just return URLs.
Inspect only the assets and constraints relevant to the task. Management reads
can enrich the decision; they are not a prerequisite for consuming an already
published endpoint with runtime authorization.

## Choose the depth the user's access allows

Without control-plane access, do not attempt to enumerate model aliases or MCP
server resources. Use supplied published model names/operation URLs and known
MCP endpoints. Explain authentication and route shapes, preserve the existing
caller identity, and use runtime responses as evidence. At a known MCP endpoint,
authorized `tools/list` can reveal tools without granting gateway-wide server
discovery or visibility into routing, filters and policy configuration.

If only the gateway host is known, help with authentication and URL structure
while requesting the missing callable model/protocol or MCP URL from the asset
owner. Do not guess asset names or make an ARM ID/elevated read permission the
next required step. Runtime rights and control-plane visibility are separate.

Management reads enrich the same decision when permitted; they are not a
different prerequisite workflow. Never present unread metadata as an empty
catalog, an omitted setting, or proof that policies are absent.

## Build a small, evidence-qualified selection brief

Start with the intended outcome and constraints already supplied: operation
and modality, quality/cost/latency preferences, state requirements, permitted
data locations, and tool actions and side effects. Ask only about missing facts
that would change the recommendation. Do not make the user learn every gateway
concept before completing a simple task.

For each plausible choice, explain:

| Choice | What the developer needs to know |
| --- | --- |
| Callable model | Exact request `model`, operation/protocol, candidate backend models, and routing behavior relevant to the task. |
| MCP server and tools | Gateway endpoint, exact selected exposed tools and their input schemas, source namespaces, and known restrictions/readiness. |
| Access and governance | Caller authentication, relevant policy limits, backend connection requirements, and unread scopes. |
| Evidence | What is configured, what was observed for this caller/request, and what is unknown. |

End with a recommendation and its concrete tradeoff, plus the finite model,
operation and tool selection to confirm. Do not confuse a long asset inventory
with an informed decision or create a persistent inventory file by default.

## Understand the callable-model contract

An application normally calls an **alias**, not a provider or deployment.
Keep these identities separate:

| Identity | Meaning and evidence |
| --- | --- |
| Alias callable name | `properties.aliasName`, or the alias resource `name` when absent; this is the request's `model`. |
| Alias management identity | Full ARM alias ID; used for reads, policy/access scope and attribution, not as the request model. |
| Candidate backend | Each `backendModels[].resourceId`, resolved to a model registration under the same gateway/workspace. |
| Deployment/model identity | The registration's `properties.deployment`, including exact model name/version when available; not a replacement for an alias name. |
| Provider | Parent model provider: provider kind, non-secret endpoint/region evidence and connectivity. Credentials belong to the gateway. |
| Observed backend/responding model | A particular request's resolved backend and provider-reported model, established by response metadata and traces where emitted. |

When permitted, read the selected alias, resolve only its backend registrations,
and read relevant provider metadata. Existing discovery collections are
`/workspaces/default/aliases`, `/workspaces/default/models`, and
`/workspaces/default/modelProviders`; an exact alias is under `/aliases/{name}`
and a provider-backed model under `/modelProviders/{provider}/models/{model}`.
Use actual returned, validated IDs rather than assuming a provider named
`default`. Project non-secret fields and do not request provider secrets.
With runtime-only access, explain the alias/registration/provider distinction
but label its actual mapping as unknown unless the owner supplies it. Do not
substitute a guessed deployment or promise a backend/region from a URL alone.

Read capability evidence, `backendModels` conditions/priorities/weights,
`selectionOrder`, `autoModelSelection`, `sessionBackendPreference`, and relevant
policies. A caller may see aliases without permission to see backend/provider
details. Preserve that boundary and identify which details an asset owner can
confirm. Do not require those details for an otherwise valid published runtime
contract. An empty successful alias list is not permission to bypass publishing.

Present the configured **candidate set**, not a claim that every candidate can
serve every request or that one was actually selected. Compatible API paths do
not prove identical context windows, tool calling, modalities, data residency,
quality, latency or cost. Use documented capability evidence for requirements;
do not infer them from an alias name or a provider hostname.

### Translate routing into application choices

Explain the routing stages actually configured, not every possible setting:

| Mechanism | Consumer implication |
| --- | --- |
| Backend `when` conditions | Conditions filter eligible backends before routing. Missing required request data, evaluation errors, or all-false conditions can reject a request before any provider call. Caller-controlled headers are not an authorization boundary. |
| Priority | The available group with the lowest priority number is preferred at that stage. An advertised model in a lower-priority group might not be eligible for the current choice. |
| Weight | Relative request share among remaining backends, not a guarantee of which backend serves a request or a percentage of tokens, capacity or cost. |
| Auto model selection | Prompt-aware choice among configured selector models using Balanced, Cost or Quality, followed by deployment routing. A selector name can differ from a deployment name. |
| Session backend preference | A configured session-key expression prefers a backend when possible. A successful affinity stage skips later selection stages/weights; it can improve cache locality but does not guarantee cache hits or permanent placement. |
| Routing order and fallback | `selectionOrder` determines precedence. Priority-first favors preferred capacity; selection-first can favor model fit; affinity-first can avoid another selector call. Failover or fallback can change the responding backend. |

For example, `support/assistant` may route to several deployments and even
several model families. The developer still sends `model="support/assistant"`.
If the workload requires one exact model or location, show whether the existing
alias contract meets it; do not silently call a backend directly or reconfigure
the alias. Recommend an owner-provided suitable alias if needed.

Check request/state compatibility before generating code:

- Auto selection supports self-contained text requests, not embeddings or
  image inputs. These restrictions remain even when affinity can run first.
- Provider-stored state such as Responses `previous_response_id` belongs to
  the backend that created it; auto selection must be off for those requests.
  Affinity for complete conversation requests is not portable provider state.
  If the state-owning backend cannot be used, do not assume another backend can
  resume the conversation.
- If an alias expects a session header, read the actual expression/contract
  before adding one. Stable, non-secret application session IDs are appropriate;
  keys, tokens and conversation text are not.
- Request overrides are off unless granted by
  `autoModelSelection.allowedRequestOverrides`. Supported requests may narrow
  `auto_model_selection.models` to existing selector names or override the
  objective. The top-level `model` still names the alias. Do not add a model
  outside the pool, broaden shared settings, or silently drop a rejected
  override. Required request parameters can leave no eligible candidate.

If exact runtime selection matters, use the diagnostic reference to compare
the alias, resolved backend and responding model for a particular request.
Neither configured weights nor a successful response alone prove that mapping.

## Understand the exposed-tool contract

A gateway MCP server is a **published federation**, not necessarily one source
service. It can combine remote MCP backends, selected OpenAPI operations, and
references to Azure-hosted sources. The client calls the gateway endpoint;
each source can have different schemas, connection/authentication requirements,
availability and side effects.

### Names identify tools, not permissions

An endpoint's optional namespace disambiguates source tools such as two backends
both exposing `search`. A runtime name might be `catalog_search` or
`support_search`; use the exact returned name and schema, not a guessed prefix
or separator. Keep any known mapping from final name to source namespace so
the user can distinguish similar actions.

Three different names can appear:

1. The gateway MCP server resource name identifies the published endpoint.
2. The endpoint/tool namespace identifies a federated source's exposed tools.
3. The app's MCP server key identifies that connection in its client or SDK.

A tool namespace is not an Azure Connector Namespace resource, an authorization
scope or a token-saving mechanism. Do not strip it from calls. Do not confuse
the final runtime tool name with an SDK's additional source-qualified
`mcp:<client-server-key>-<runtime-tool-name>` identifier.

### Discovery, invocation and client exposure are separate

Read non-secret `versions`, `accessState`, `allowList`, `blocked`, endpoint
namespaces and per-endpoint `required` where permitted. Then compare them with
the actual authorized `tools/list` result, preserving pagination and failures.
Without those reads, select from the known server's returned descriptors and
published instructions, while marking the unknown controls explicitly.

| Layer | What it means |
| --- | --- |
| `allowList` omitted or `["*"]` | No restriction from this selector: all otherwise available tools can be discovered/invoked. Other access, policies and backend requirements still apply. |
| `allowList: []` | No tools are exposed. A healthy server can intentionally return an empty list. |
| Finite `allowList` names/patterns | Server-side filtering of both discovery and invocation against final exposed names, including namespaces. Use the gateway's documented glob semantics, not an invented substring match. |
| `blocked` names/patterns | Matching invocations are denied even if allowed, but descriptors are not removed from discovery. Listed does not mean invocable. |
| `accessState: "blocked"` | The whole server is blocked for consumers; a key or broader local tool filter is not a bypass. |
| Backend `required` | A required backend failure can fail federation; an optional failed backend can be omitted while others work. The top-level failure label alone is not proof of the effective per-backend behavior. |
| App/client tool allowlist | Further narrows what the agent sees and can select. It cannot grant permissions or undo gateway filters, policies or source access requirements. |

For example, if `catalog_*` is allowed but `catalog_delete` is blocked,
`catalog_delete` may still be listed. An app needing search should expose
`catalog_search` only, not the wildcard or the blocked operation.

Select tools from the intersection of observed descriptors, known permitted
operations and the user's task. Preserve uncertainty when permissions prevent
reading selectors: discovery is evidence of visibility, not proof of
invocation authorization. Do not test a questionable tool by calling it.
Describe omitted namespaces as unavailable/unverified, not nonexistent.

### Budget model context, not just connections

One MCP connection can expose hundreds of tool schemas. Model context and
selection quality depend on the descriptors actually presented to the model,
not the number of endpoints.

- Keep full discovery metadata local to the selection process; avoid pasting
  the entire catalog into a prompt. Choose tools by action, schema, source,
  side effects and overlap, not by namespace or name alone.
- Expose a finite set of necessary tools through the client's supported
  filtering mechanism. Preserve their exact callable names and schemas.
  Revisit the selection deliberately when the task or catalog changes.
- A server-side allowlist can reduce returned discovery descriptors. Blocking
  invocations alone does not hide descriptors or guarantee fewer input tokens.
  A client filter may reduce model exposure without reducing MCP discovery
  network traffic; inspect the client's behavior before promising savings.
- Prefer supported pagination/result limits and bounded relevant outputs.
  Do not silently drop requested records, rewrite schemas or treat local
  filtering as a security boundary.

Keep server-curation changes as recommendations to the owner, not actions in
this skill. Quantify context/cost effects only from actual provider/client
usage measurements. Fewer descriptors can help, but no fixed savings are implied.

## Explain relevant governance before use

When authorized, inspect `properties.policies` on the default workspace and
the exact selected alias, backend model or MCP server. Policies are inline on
their declaring host; do not invent a `/policies/{id}` resource API. Keep host
ID, policy identity/type, scope, configuration and read coverage associated.
Use non-secret projections and ordinary GETs, never secret-preserving admin
merge/replacement helpers.

Interpret only applicable supported policies. Workspace, alias and selected
backend/server constraints may all matter; a direct policy is not proof that
inherited constraints were replaced. Unknown/disabled policy types, an unread
host, partial inventory, or missing scope evidence are limitations, not "none."
Without management permission, use the error code/behavior and supplied policy
documentation to explain possible constraints; do not claim a complete policy
audit or block authentication/URL/client-error guidance on that missing read.

| Constraint | What changes for the application |
| --- | --- |
| Request/token limits | Calls can receive 429 and a reset/Retry-After indication. Include tool descriptors and conversation/output size in the request budget; distinguish gateway from upstream throttling. |
| Cost limits | A model request can receive 403 `LlmCostQuotaExceeded`. Identity/IP counter dimensions and shared keys can mean the limit is shared, not a private per-process allowance. |
| Content safety | Input/output can be rejected, commonly with 400; valid authentication and schemas do not guarantee content acceptance. |
| Fallback | Availability can improve while backend identity, latency, output and cost change; correlate an actual attempt before attributing behavior. |
| IP/CORS | Reachability and browser-origin rules can reject requests before inference/tool execution. A successful server-side test does not prove a browser preflight is allowed. |
| Tool threat protection/agent hooks | Pre-checks can prevent execution; post-checks can withhold an already-executed tool's result. Missing output is not permission to repeat a side effect. |

Translate applicable settings into one or two practical client decisions
(for example, narrower tool exposure, compatible state handling, a session
header, bounded request size, or an actionable access request). Configuration
shows intended constraints; request diagnostics/traces establish what happened.
Never disable a policy, change a counter identity, switch credentials, or call
an upstream directly to evade a denial.
