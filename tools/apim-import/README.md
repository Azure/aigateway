# apim-import

Inventory the AI assets of an Azure API Management instance, shaped for migration to
[Azure AI Gateway](https://ai.gateway.azure.com) (`Microsoft.ApiManagement/aigateways`).

This is the source-side half of a migration. It answers three questions a coding agent has to
answer before it can move anything:

1. **What AI workload is actually running in this APIM?** Models, MCP servers, and A2A agents —
   and nothing else.
2. **What would it take to reproduce it on AI Gateway?** Every asset is captured decomposed into
   the target's building blocks, so the gap is a comparison rather than an interpretation.
3. **How does an automated migration get the credentials without anyone reading them?** Every
   secret becomes a reference plus the exact command that retrieves it at apply time.

Status: `collect` and `validate` are implemented and verified against live APIM instances.
`resolve-models`, `assess`, and `plan` are specified below and not yet built.

---

## The workflow this is built for

An agent cannot do a migration like this in one pass. It collects, proposes, asks the operator
about the parts that do not translate, records what they decide, and only then emits something
executable. The tool is therefore a **pipeline of pure functions over files**, not one command:

```
          ┌─────────────┐
  APIM ──▶│   collect   │──▶ inventory.json      facts only, no verdicts, no secrets
          └─────────────┘
                 │
          ┌─────────────┐
          │resolve-models│──▶ inventory.json     (optional) third-party model catalogues
          └─────────────┘
                 │
          ┌─────────────┐
          │   assess    │──▶ assessment.json     verdicts, gaps, and questions
          └─────────────┘     ▲
                 │            │
                 │     ┌──────────────┐
                 │     │ decisions.json│         what the operator chose (hand-authored)
                 │     └──────────────┘
          ┌─────────────┐
          │    plan     │──▶ plan.json           ordered, idempotent, secret-resolving
          └─────────────┘
```

The rule that makes the loop converge: **derived files are never hand-edited.** When the operator
says "that rate limit should become a token limit instead" or "merge these three APIs into one
alias", the agent writes that into `decisions.json` and re-runs `assess`. Re-running is cheap,
deterministic, and diffable, so a clarification never destroys earlier work, and the reasoning
behind every deviation stays attached to the artifact instead of living in chat history.

| Artifact | Produced by | Hand-edited | Contains |
| --- | --- | --- | --- |
| `inventory.json` | `collect` | no | What APIM holds, verbatim, plus resolved Azure deployments |
| `assessment.json` | `assess` | no | Per-asset target mapping, feasibility verdict, gaps, questions |
| `decisions.json` | the agent, with the operator | **yes** | Answers, overrides, accepted gaps, chosen names |
| `plan.json` | `plan` | no | The migration asset: ordered operations with secret recipes |

---

## Installation

Python 3.10+ and the Azure CLI, signed in (`az login`). No other dependencies.

```bash
cd tools/apim-import
python3 -m apim_import --help          # run from source
pip install -e .                       # or install the 'apim-import' command
pip install -e '.[dev]'                # adds jsonschema (strict validate) and pytest
```

## Usage

```bash
# Inventory everything AI-related in one APIM instance
apim-import collect --apim apim-gateway-demo -g a365-gateway-governance -o inventory.json

# Narrow the scope
apim-import collect --apim <name> -g <rg> --family mcp --family a2a
apim-import collect --apim <name> -g <rg> --include-api 'aoai-*' --exclude-api 'legacy-*'

# Foundry accounts in other subscriptions
apim-import collect --apim <name> -g <rg> --foundry-subscription <sub-id>

# Check and read
apim-import validate inventory.json
apim-import summary inventory.json --format markdown
```

`collect` is read-only. It issues `GET` requests only, and never calls a `list*` secret action.
Running it needs `Reader` on the APIM instance, plus `Reader` on any Cognitive Services account
you want resolved.

<details>
<summary>All <code>collect</code> options</summary>

| Option | Purpose |
| --- | --- |
| `--apim`, `-g`, `--subscription` | Target, by name plus resource group or by full ARM id |
| `--api-version` | APIM control-plane version (default `2025-09-01-preview`; MCP and A2A fields need this or newer) |
| `--cognitive-api-version` | Cognitive Services version (default: newest stable, discovered at run time) |
| `--workspace` | Repeatable. `all` (default) walks every workspace; `none` restricts the scan to the service scope |
| `--family` | Repeatable: `models`, `mcp`, `a2a` (default: all three) |
| `--include-api` / `--exclude-api` | Glob overrides for the model-API heuristic |
| `--foundry-subscription` | Extra subscription to scan for Cognitive Services accounts |
| `--no-foundry` | Skip ARM deployment resolution |
| `--no-policy-xml` | Keep the normalized element list, drop the raw XML |
| `--fast` | Skip operation enumeration for non-MCP APIs (faster, weaker model detection) |
| `--max-apis` | Stop after N APIs, for a smoke run |

</details>

---

## What gets inventoried

### Asset families

APIM models two of the three families as first-class API types, and the third not at all.

| Family | How APIM represents it | How the tool finds it |
| --- | --- | --- |
| **MCP servers** | `type: "mcp"`, with `mcpProperties`, `backendId`, and `mcpTools`/`apis/{id}/tools` | Deterministic, from the API type |
| **A2A agents** | `type: "a2a"`, with `isAgent`, `a2aProperties`, `agent`, `jsonRpcProperties` | Deterministic, from the API type |
| **Model APIs**, unified | `type: "unifiedModelApi"` over `type: "languageModel"` backends | Deterministic, from the API type |
| **Model APIs**, proxied | Nothing. An Azure OpenAI or Bedrock endpoint is an ordinary `http` API | **Weighted evidence**, see below |

Model APIs come in two forms, and only one of them needs guessing. APIM's **unified model API** is
first-class: one OpenAI-compatible surface fanning out to `languageModel` backends, each declaring
its `apiFormat` and `model` outright. That declaration is authoritative and beats every heuristic —
including the provider host, which can disagree with it. A backend on a `*.services.ai.azure.com`
host speaking `anthropic-messages` is a **Custom** provider on the target, not a Foundry one, which
is exactly how a live AI Gateway models the same upstream.

The older form — an Azure OpenAI or third-party endpoint published as a plain `http` API — has no
marker at all, and is where the scoring below applies.

A fourth family, **model providers**, is derived rather than read: it is the set of upstream model
endpoints referenced by a backend or a service URL. It exists as its own asset because AI Gateway's
first building block is a provider, and because APIM routinely holds a model backend that *no API
publishes* — reached only from a `send-request` policy, or left orphaned. The live instance this was
built against had exactly that: a Foundry backend with an API key and no API in front of it.

### Model-API detection

There is no field to read, so detection is scored, and both the score and the evidence are written
into the output for the agent to show the operator.

| Signal | Weight | Why |
| --- | --- | --- |
| Backend `resourceId` points at `Microsoft.CognitiveServices/accounts` | 60 | Unambiguous |
| Backend or service URL host matches a known provider | 50 | `*.openai.azure.com`, `api.anthropic.com`, `bedrock-runtime.*.amazonaws.com`, and ~15 more |
| An LLM-specific APIM policy is in effect | 40 | `azure-openai-token-limit`, `llm-semantic-cache-lookup`, … |
| Backend name follows APIM's AI import convention | 30 | `*-openai-endpoint`, `*-ai-endpoint` — what the "Import AI API" wizard creates |
| Operations expose inference routes | 25 | `/chat/completions`, `/v1/messages`, `/embeddings`, `:generateContent`, … |
| Backend credential uses the AI import named-value convention | 15 | `*-LLM` |
| Name, path, or title suggests a model API | 10 | Weakest signal; never sufficient alone |

The two naming-convention signals exist because of a real case: an API fronting an unrecognized
provider host (`https://api.meta.ai`) through wildcard `/*` operations, with no LLM policy. Host,
path, and policy all see nothing; only the `-openai-endpoint` backend and the `-LLM` named value
give it away. Together they reach `medium` — enough to raise it, not enough to assume it — and the
provider is reported as `unknown` rather than guessed.

`high` ≥ 50, `medium` ≥ 25, `low` ≥ 10, below that the API is excluded. **Every excluded API is
listed** in `excludedApis` with its reason and whatever signals it did produce, so the agent can
prove nothing was dropped silently — and so a `low`-confidence call is a question for the operator,
not a silent decision. `--include-api` forces an API in with `confidence: "forced"`.

### Model resolution, per provider

The point of resolving models is that AI Gateway registers *models*, not endpoints, and a Foundry
model registration needs the deployment's ARM id, model name, and model version.

| Provider | Resolution | Needs a credential |
| --- | --- | --- |
| **Any `languageModel` backend** | None needed: `languageModel.model` and `.apiFormat` are declared on the backend | No |
| **Microsoft Foundry / Azure OpenAI** | ARM: match the backend host or `resourceId` to a `Microsoft.CognitiveServices/accounts`, then list its `deployments` | No — same cloud, same token |
| OpenAI, Anthropic, Mistral, Groq, Together, DeepSeek, xAI, Perplexity, Google AI | `GET {endpoint}/v1/models` | Yes — `resolve-models` only |
| AWS Bedrock | `aws bedrock list-foundation-models` | Out of band |
| Google Vertex AI | `gcloud ai models list` | Out of band |
| Unrecognized host | Ask the operator | — |

Backend declarations and Foundry resolution both run inside `collect` because neither needs a
secret. Everything that does is deferred to `resolve-models`, which resolves the referenced secret
**in memory only**, calls the catalogue endpoint, and writes back model identifiers — never the
key. That keeps the default path provably secret-free.

`apiFormat` values are mapped to target endpoints from a table of formats verified on a live
service. An unrecognized value is normalized by substring and marked `formatResolution:
"inferred"`, or left `"unknown"` with null endpoints — never silently guessed into a wrong
endpoint.

### Read values versus inferred ones

Paths, names, and URL templates in APIM are operator-configured, so the inventory is careful about
which side of that line a value sits on. Nothing about a path is hard-coded: `source.path` and
`endpoints.basePath` are `properties.path` verbatim, and operation templates are recorded as
returned.

What *is* inferred is the dialect a caller speaks, because APIM does not declare it — it is read
from operation URL templates like `/chat/completions`. An operator can route a model API through a
wildcard `/*` or a custom template, and then no dialect is readable at all. So:

| Value | Basis | Marked as |
| --- | --- | --- |
| `endpoints.basePath`, `operations[].urlTemplate` | Read from APIM | — |
| `backendDialects` | Declared by the backend's `languageModel.apiFormat` | `backendDialectsDeclared: true` |
| `inboundDialects` | Inferred from operation templates | `inboundDialectsInferredFrom: "operationTemplates"` |
| `translation.status` | Comparison of the two | `translating`, `native`, or `indeterminate` |

`indeterminate` is the important one. An earlier version of this tool emitted a translation block
only when it could read both sides, which meant a wildcard route made a real gap *disappear* rather
than surface — the worst kind of wrong answer, because silence reads as "no problem". The block is
now always present when a backend dialect exists, and says plainly when the caller side could not
be determined and needs confirming with the operator.

#### The rule this generalizes to

**A failed inference must not render as an empty list, a null, or a safe-looking default.** Those
are the same shape as a confident negative answer, and a migration agent cannot tell them apart.
Auditing the collector for that one pattern turned up six more instances of it, all now fixed and
regression-tested:

| Where | What it used to say | What was wrong |
| --- | --- | --- |
| Backend auth | `mode: "none"` | Only the API's own policy was searched. An `authentication-managed-identity` inside an included fragment, or in the product or global policy, was missed — reporting a credentialed backend as called unauthenticated. Now resolves fragments and shared scopes, records `basis.policyScopesExamined`, and reports `undetermined` when a fragment could not be resolved |
| `policyRefs.operations` | `[]`, always | Operation policies were captured but never linked, so an asset with operation-level policy looked like it had none |
| Subscription scope | `level: "service"` | An unparseable scope fell back to the *broadest* access level, over-reporting what a key grants. Unrecognized scopes are now `unknown` |
| MCP upstream transport | `transport: null` | Inferred from an endpoint's key name — APIM leaves `transportType` null on every instance seen — and null read as "no transport configured". Now carries `transportBasis.status` of `declared`, `inferred`, or `undetermined` |
| Backend references | `referencedBy: {apis: [], policies: []}` | A whole-value match over attributes only. A backend id built inside a policy expression was invisible, so an empty result looked like proof a backend was orphaned. Now scans text and expressions too, and carries a caveat saying an empty result is weak evidence, not proof |
| Backends not treated as providers | nothing at all | `excludedApis` proved API coverage; backends had no equivalent, so a model backend on an unrecognized host was simply absent. `excludedBackends` now records every skip with its reason and which assets use it |

The same audit removed a dead `policy.controls()` helper that nothing called.

#### Backend roles are declared, not guessed

The sharpest case of the rule. An Azure AI Content Safety endpoint sits on
`*.cognitiveservices.azure.com` and is, by host alone, indistinguishable from a Foundry model host
— so it was being reported as a **model provider** with `models: "empty"`, which reads as "a
Foundry account with no deployments yet" rather than "this is not a model provider at all". A
migration agent would have created a provider for it.

The answer was already in the configuration: `<llm-content-safety backend-id="AI-CS-…">` *declares*
what that backend is for. Policy-declared roles now outrank the host heuristic.

| Policy element | Attribute | Role | Model provider? |
| --- | --- | --- | --- |
| `llm-content-safety`, `azure-openai-content-safety` | `backend-id` | `contentSafety` | No — excluded, with the reason recorded |
| `llm-semantic-cache-lookup`, `azure-openai-semantic-cache-lookup` | `embeddings-backend-id` | `embeddings` | Yes — an embeddings model is still a model |
| `set-backend-service` | `backend-id` | `routing` | Covered by `routing.targets` |

A backend whose declared roles are *only* non-model-serving is skipped and listed in
`excludedBackends` with `reason: "declaredNonModelRole"` and the policy paths that said so. An
attribute holding an expression or a named-value reference is not treated as a backend name.

Each asset also carries `supportingBackends`: the backends it depends on for something other than
serving the model. Content safety is both a dependency and a gap — there is nothing to recreate it
with on a typed AI Gateway — so making the dependency explicit matters more than usual.

That entry is careful about its own completeness, too. `llm-content-safety` keeps its thresholds in
a `<categories>` child element, not in attributes, so the entry exposes `attributes` (never
"settings"), lists `childElements`, sets `configurationComplete: false`, and points at
`fullConfigurationAt` — the policy document and element path where the whole thing can be read.

### Policy capture

Feasibility is decided almost entirely by policy, so `collect` keeps both representations: the raw
XML at every scope it reads (global, product, API, operation, fragment, workspace) and a normalized
element list — one record per element, with its section, path, attributes, named-value references,
and policy expressions.

Deliberately, **no mapping verdict is computed here.** Classification against AI Gateway belongs to
`assess` and its versioned capability map, so that a new AI Gateway release changes a data file
rather than the collector. What `collect` does guarantee:

- `include-fragment` dependencies are resolved and the fragments are captured as their own documents.
- Every `@(…)`/`@{…}` expression gets a stable `expr:<hash>` id, its `context.*` references, and its
  source — the single strongest predictor of a non-portable policy.
- Elements the tool has never heard of get `family: "other"` rather than being dropped.

---

## The secret contract

**No secret value is ever written to an output file, and `collect` never reads one.**

Instead, every credential in APIM becomes a `secretRef` carrying what it is, what consumes it,
whether an automated migration can retrieve it, and the exact call that retrieves it:

```json
{
  "id": "secret:namedValue/openai-api-key-LLM",
  "class": "apimNamedValue",
  "storage": "apimEncrypted",
  "description": "APIM named value 'openai-api-key-LLM'",
  "usedBy": ["backend:openai-openai-endpoint"],
  "retrievable": true,
  "resolution": {
    "method": "armAction",
    "request": { "httpMethod": "POST", "url": "https://management.azure.com/…/namedValues/openai-api-key-LLM/listValue?api-version=2025-09-01-preview" },
    "command": "az rest --method post --url \"…/listValue?api-version=2025-09-01-preview\" --query \"value\" --output tsv",
    "valuePath": "$.value",
    "permissions": ["Microsoft.ApiManagement/service/namedValues/listValue/action"]
  }
}
```

An executing agent resolves these just in time, injects the value into the target's ARM body, and
discards it. The inventory stays safe to commit, diff, and paste into a review.

| Where APIM keeps it | `class` | Retrieval |
| --- | --- | --- |
| Named value, secret | `apimNamedValue` | `POST …/namedValues/{n}/listValue` |
| Named value, Key Vault–backed | `apimNamedValue` | Same, plus an `alternateResolution` reading the vault directly — prefer re-pointing the target at the same secret |
| Literal key on a backend's header/query credentials | `apimBackendInlineCredential` | `GET` the backend and read the field; flagged for rotation |
| Literal key hard-coded in policy XML | `apimPolicyInlineLiteral` | `GET` the policy and XPath to it; flagged for rotation |
| Inbound subscription key | `apimSubscriptionKey` | `POST …/subscriptions/{s}/listSecrets` — but see the gap below |
| Client certificate in the APIM store | `apimCertificate` | **Not retrievable.** APIM does not export private keys; re-upload from source, or move it to Key Vault first |
| Credential-manager connection | `apimCredentialConnection` | **Not retrievable.** Re-authorize interactively against the target |
| Managed identity, from a backend's `credentials.managedIdentity` or an `authentication-managed-identity` policy | `azureManagedIdentity` | Nothing to move; the migration must grant the target gateway's identity the same role on the backend resource |

Two places where the live APIM contract is ahead of the published ARM schema, and where trusting
the docs would have produced a wrong inventory: a backend's `credentials.managedIdentity` (how the
portal wires a Foundry backend — reading only the documented fields reports the most common Azure
model backend as unauthenticated), and `properties.resourceId`, which APIM stores as a *management
URI* rather than a bare ARM id and which the tool normalizes.

Literals are detected by key shape (`sk-…`, `sk-ant-…`, `AKIA…`, JWTs, high-entropy blobs) and by
credential-bearing parameter names, then replaced with `<redacted:N>` before anything is written.
The heuristic errs toward redaction: a false positive costs one question, a false negative leaks a
key. Named-value references (`{{name}}`) and policy expressions are indirections, not values, and
are preserved verbatim because they are what the migration needs to resolve.

---

## How APIM concepts land on AI Gateway

This is the mapping `assess` will encode in a versioned capability map. It is the reason the
inventory is decomposed the way it is.

### Building blocks

| APIM | Azure AI Gateway | Fit |
| --- | --- | --- |
| Backend or service URL pointing at a model host | `modelProviders` (`kind: Foundry` or `Custom`) | Direct |
| Foundry account deployment | `models` (`deployment.resourceId`, `modelName`, `modelVersion`) | Direct, resolved by `collect` |
| Backend pool `services[]` with priority and weight | `aliases.backendModels[]` with priority and weight | Close; see caveats |
| `unifiedModelApi` over N `languageModel` backends | One `alias` over N registered `models` | Close, except the dialect — see gap 7 |
| Backend `languageModel.{model, apiFormat}` | `models.deployment.modelName` and `supportedEndpoints` | Direct |
| Workspace | — | No equivalent. AI Gateway exposes only the implicit `default` workspace, so workspace isolation has to be redesigned |
| The callable name clients send as `model` | `aliases.aliasName` | **No source.** APIM has no alias concept, so a name must be chosen per alias — a decision, not a translation |
| MCP API, passthrough | `toolServers.endpoints[kind: "mcp"]` (`streamable`→`streamableHttp`, `sse`→`sse`) | Direct |
| MCP API, tool projection over a REST API | `toolServers.endpoints[kind: "openApi"]` plus the server's `allowList` | Workable: `collect` emits the OpenAPI export recipe. Per-tool policies do not survive |
| MCP federation router | One `toolServers` with several endpoints | Direct |
| A2A agent API | — | No building block yet; inventoried and parked. See below |
| Products and subscription keys | `apiKeys` (gateway-wide) plus Entra RBAC | **Weak.** See gaps |
| Named values, policy fragments | — | No equivalent; values are inlined into target configuration |
| Loggers and diagnostics | `telemetryExporters` | Partial |

Caveats worth catching before they bite, all from the shipped AI Gateway surface: an alias holds
**1–30** model registrations, so a larger APIM pool does not fit as one alias; alias weights are
**1–100**, so an APIM pool member with `weight: 0` (a drained backend) has no direct expression; and
replacing an alias's backend list replaces the whole pool.

### Policies

AI Gateway's native policy surface is six types — `tokenLimit`, `costLimit`, `requestRateLimit`,
`ipFilter`, `toolThreatProtection`, `agentHooks` — attached to the default workspace, an alias, a
model, or a tool server. APIM has well over a hundred. Most of the migration's real work is here.

| APIM policy | Target | Verdict |
| --- | --- | --- |
| `azure-openai-token-limit`, `llm-token-limit` | `tokenLimit` | **Native** |
| `ip-filter` | `ipFilter` | **Native** |
| `authentication-managed-identity` | Provider `authentication.kind: ManagedIdentity` | **Native** — becomes configuration, not policy |
| Backend header/query key credentials | Provider `authentication.kind: ApiKey` | **Native** |
| `rate-limit-by-key`, `rate-limit` | `requestRateLimit` | **Partial.** `counter-key` is an arbitrary C# expression in APIM; AI Gateway partitions by `identity`, `ipAddress`, both, or nothing. `@(context.Subscription.Id)` is close to `identity` but not identical |
| `azure-openai-emit-token-metric` | `telemetryExporters` | **Partial.** Custom dimensions do not carry over one-for-one |
| `validate-jwt`, `validate-azure-ad-token` | Gateway Entra auth plus data-plane RBAC | **Partial.** Issuer and audience validation is covered; gating on custom claims or app roles is not |
| Per-tool policy on `apis/{id}/tools` | `allowList` / `blocked`, or `agentHooks` | **Partial.** Static allow/deny translates; per-tool logic needs a callback |
| `quota`, `quota-by-key` | — | **Gap.** `costLimit` is a dollar budget, not a call quota |
| `azure-openai-semantic-cache-*`, `llm-semantic-cache-*` | — | **Gap** |
| `azure-openai-content-safety`, `llm-content-safety` | — | **Gap.** Content-safety flags exist in the CLI but are not supported on typed `aigateways`. The policy also pulls in a separate Content Safety backend, surfaced as a `supportingBackends` dependency |
| Transformations: `set-body`, `set-header`, `rewrite-uri`, `json-to-xml` | — | **Gap.** No request/response rewriting |
| `send-request`, `return-response`, custom `@{…}` expressions | — | **Gap.** `agentHooks` is the nearest mechanism, and only for tool traffic |
| `cors`, `trace`, correlation headers | — | **Not applicable** |
| — | `costLimit` | AI Gateway capability with no APIM source; an upgrade, not a gap |

### Known structural gaps

These are not policy details; they change what a migration *means*, and each one should surface as
an explicit question to the operator.

1. **Inbound authorization is scoped differently.** APIM subscription keys are scoped to a product,
   an API, or the whole service. AI Gateway API keys are gateway-wide. There is no import path for
   a key's value either, so every caller is re-keyed. A per-API or per-product authorization model
   has to be redesigned around Entra identities and RBAC.
2. **A passthrough MCP server has no stored tool list.** APIM proxies `tools/list` to the upstream
   server. An AI Gateway `allowList`/`blocked` needs real tool names, so they must be enumerated at
   runtime first. `collect` marks these `toolDiscovery.status: "runtimeOnly"` rather than reporting
   zero tools as if that were the answer.
3. **Aliases have to be named.** The callable model name is a new decision for every alias.
4. **A2A has no target.** Inventoried now so the gap is explicit and the configuration survives.
   An A2A API is unusual in where it keeps things: `backendId` and `serviceUrl` are both null, and
   the upstream lives in `jsonRpcProperties.BackendUrl` — returned with PascalCase keys, unlike the
   rest of the contract, so the collector reads both casings. A Foundry-hosted agent's endpoint
   (`…/api/projects/<project>/agents/<agent>/endpoint/protocols/a2a/`) is decomposed into its
   project, agent id, and the ARM account behind it. The agent card is captured as a *location*:
   APIM stores its URL, never its content, so the card's skills and security schemes are a runtime
   fetch — the same `runtimeOnly` treatment a passthrough MCP server's tool list gets.
5. **Client certificates and credential-manager connections cannot be exported.** They are
   re-provisioning work, not migration work, and the plan must say so up front.
6. **Policy expressions are the real portability boundary.** Any `@(…)` doing more than reading a
   well-known `context` property is almost certainly a gap; the inventory extracts them all.
7. **Format translation has no equivalent.** A unified model API accepts one dialect and calls
   another — OpenAI `/chat/completions` in, `anthropic-messages` out — and APIM translates between
   them. AI Gateway routes protocol-natively: an alias publishes its model at the model's own
   endpoint, so the same Anthropic model is reached at `/v1/messages`. The consequence lands on
   *callers*: they either move to the backend dialect or keep a translating layer in front of the
   gateway. The two sides of that comparison are not equally solid, and the inventory says so —
   see below.
8. **Workspaces do not exist on the target.** AI Gateway configures the implicit `default`
   workspace only. An APIM workspace with `serveOn: workspaceAndDefault` also publishes through the
   service's default hostname, so both the isolation boundary and the routing need a decision.

---

## Output shape

Flat, id-addressed tables with assets referencing them, so nothing is duplicated and a re-collection
of an unchanged service diffs cleanly. Ids are derived from ARM identity and are stable across runs.

```jsonc
{
  "schemaVersion": "1.0",
  "kind": "apimAiInventory",
  "generator":  { "name": "apim-import", "version": "0.1.0", "command": "collect" },
  "collection": { "apiVersions": {...}, "coverage": [...], "warnings": [...] },
  "service":    { "resourceId": "...", "sku": {...}, "identity": {...}, "virtualNetworkType": "..." },
  "workspaces": [ { "name": "finance", "serveOn": "workspaceAndDefault", "collected": true } ],

  "assets": {
    "modelProviders": [ /* upstream endpoints + resolved Foundry deployments + referencedBy */ ],
    "models":         [ /* APIM APIs publishing inference: provider, routing, models, endpoints */ ],
    "mcpServers":     [ /* pattern, upstream, tools, toolDiscovery, openApiSources */ ],
    "agents":         [ /* a2aProperties, agent card, jsonRpcProperties */ ]
  },
  "excludedApis":      [ /* every API not inventoried, with its reason and signals */ ],
  "excludedBackends":  [ /* every backend not treated as a model provider, with its reason */ ],

  "shared": {
    "backends": [...], "namedValues": [...], "policyFragments": [...],
    "products": [...], "subscriptions": [...], "certificates": [...],
    "authorizationServers": [...], "openidConnectProviders": [...],
    "credentialProviders": [...], "telemetry": {...}, "foundryAccounts": [...]
  },

  "policies": [ /* one per scope: raw XML + normalized elements + expressions */ ],
  "secrets":  [ /* every secretRef, referenced by id from the tables above */ ]
}
```

`collection.coverage` records one entry per control-plane read — collection, scope, status, count,
error. Completeness is provable rather than assumed, which matters when a migration decision rests
on "there are no other model APIs".

The schema is [`schemas/inventory.schema.json`](schemas/inventory.schema.json). `apim-import
validate` checks against it with `jsonschema` when installed, and falls back to a structural check
otherwise.

---

## Planned commands

### `resolve-models`

Fills in `models.resolved` for non-Azure providers. Resolves the referenced `secretRef` in memory,
calls the provider's catalogue endpoint, writes back model identifiers, and discards the credential.
Opt-in per provider (`--allow-secret-use <provider>|all`) because it is the one step that touches a
secret, and it should be a deliberate act.

### `assess`

A pure function of `inventory.json` + a versioned capability map + `decisions.json`, emitting
`assessment.json`:

- **Target projection** per asset — the AI Gateway objects it becomes, pre-shaped for `az aigateway`.
- **Verdict** — `ready`, `needsDecision`, or `cannotMigrate`, with the evidence behind it.
- **Gaps** — stable id, severity, whether it blocks, and the nearest compensating control.
- **Questions** — stable id, the exact text to put to the operator, the shape of a valid answer, and
  what it unblocks.

The capability map is a data file keyed by AI Gateway API version, so a new release is a data change.

### `plan`

Emits `plan.json`: ordered, idempotent operations (providers → models → aliases → tool servers →
policies → keys), each with its ARM request and the `secretRef`s it needs. It opens with a secret
preflight listing every credential read and the permission it requires, so an agent can confirm it
*can* finish before it starts. It refuses to emit while any blocking question is unanswered or any
blocking gap is unaccepted — assessment is not execution approval.

---

## Development

```bash
cd tools/apim-import
uv venv .venv && uv pip install --python .venv/bin/python pytest jsonschema
.venv/bin/python -m pytest -q
```

119 tests cover secret classification and recipes, policy normalization, asset detection, and a
full collector run against a canned ARM surface (`tests/fake_arm.py`) that mirrors the shapes that
matter: a passthrough MCP server, a tool projection over REST, a Foundry model API behind a
weighted backend pool with a managed-identity credential, a model API detectable only by naming
convention, a Foundry-hosted A2A agent, a workspace holding a unified model API over a
`languageModel` backend, and a plain REST API that must be excluded.

The suite must stay offline. `tests/test_collect.py` builds options through a local `options()`
helper that pins `cognitive_api_version`, because leaving it unset makes `FoundryResolver` ask
`az provider show` for the newest version — which turns a unit test into a network call.

### Verified against

`collect` was developed and checked against three live instances:

| Instance | What it exercised |
| --- | --- |
| `apim-gateway-demo` (StandardV2) | Passthrough MCP, REST-projected MCP, an orphaned Foundry backend, policy fragments with C# expressions, scoped subscriptions |
| `apim-cowork-mcp-d308bf6a` (Developer) | An MCP API with no upstream configured at all |
| `a365-bugbash-v2` (StandardV2) | Foundry model API with managed-identity auth and 50 inference operations, a third-party model API behind wildcard operations, `llm-token-limit`, a hosted MCP backend, a Foundry-hosted A2A agent, and a workspace serving a unified model API over an Anthropic `languageModel` backend |

The emitted OpenAPI export recipe was executed to confirm it returns a usable document link. The AI
Gateway target shapes were read from live `Microsoft.ApiManagement/aigateways` resources at API
version `2026-09-01-preview`.

Not yet exercised against live configuration, and therefore the first things to re-check:
self-hosted gateways, backend pools in production shapes, workspace-scoped products and
subscriptions, an A2A agent hosted outside Foundry, `apiFormat` values other than
`anthropic-messages`, and non-Azure providers whose model catalogue needs `resolve-models`.
