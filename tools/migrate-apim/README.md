# migrate-apim

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

Status: `collect`, `resolve-models`, `discover-tools`, `plan`, `apply` and `validate` are
implemented and verified against live APIM instances.

---

## The workflow this is built for

An agent cannot do a migration like this in one pass. It collects, proposes, asks the operator
about the parts that do not translate, records what they decide, and only then emits something
executable. The tool is therefore a **pipeline of pure functions over files**, not one command:

```
          ┌─────────────┐
  APIM ──▶│   collect   │──▶ inventory.json    facts only, no verdicts, no secrets
          └─────────────┘
                 │
          ┌─────────────┐
          │    plan     │──▶ plan.json         proposed, then adapted in place
          └─────────────┘         ▲
                 │                │  agent + operator settle what does not map
                 │                └────────────── re-run; adaptations survive
          ┌─────────────┐
          │    apply    │──▶ one object at a time, journalled and resumable
          └─────────────┘
```

**`plan.json` is the one living artifact.** Every item arrives proposed, with a rationale and its
options spelled out; `needs-decision` means "confirm or change this", not "the tool has no opinion".
Adapting an item means setting `status` and `decision` on it — nothing else.

Re-running `plan` is safe and is the normal way to work. Adapted items are preserved, and an item is
re-opened only when the APIM facts **it** rested on changed, with `staleReason` saying what moved.
An unrelated change never disturbs settled work.

| Artifact | Produced by | Adapted | Contains |
| --- | --- | --- | --- |
| `inventory.json` | `collect` | no | What APIM holds, verbatim, plus resolved Azure deployments |
| `plan.json` | `plan` | **yes, in place** | One item per source aspect: proposal, options, evidence, and pre-shaped target objects |
| `journal.json` | `apply` | no | Attempts and resume state |

---

## Running it

Python 3.10+ and the Azure CLI, signed in (`az login`). No other dependencies, so there is
nothing to install — the package runs from wherever it already is:

```bash
PYTHONPATH=<tool-dir> python3 -m migrate_apim.cli --help
```

`<tool-dir>` is this directory. The [coding-agent plugin](../../README.md#coding-agent-plugin)
ships it, so installing the plugin already put a copy on disk — under
`${CLAUDE_PLUGIN_ROOT}/tools/migrate-apim` in Claude Code. A clone of the repository works the
same way.

Installing the `migrate-apim` command is a convenience for working from a clone:

```bash
cd tools/migrate-apim
pip install -e .                       # installs the 'migrate-apim' command
pip install -e '.[dev]'                # adds jsonschema (strict validate) and pytest
```

Do not point `pip install -e` at the plugin's copy. That path is pinned to one commit, so the
editable install breaks the next time the plugin updates.

Every example below writes `migrate-apim`. Without the installed command, that is
`PYTHONPATH=<tool-dir> python3 -m migrate_apim.cli`.

## Usage

```bash
# Inventory everything AI-related in one APIM instance
migrate-apim collect --apim apim-gateway-demo -g a365-gateway-governance -o inventory.json

# Propose a migration plan, then re-run it after adapting items in place
migrate-apim plan --inventory inventory.json -o plan.json
migrate-apim plan --inventory inventory.json -o plan.json --probe-cli   # check the installed az extension too

# Fill in a provider's model list where it needs the backend credential
migrate-apim resolve-models --inventory inventory.json --allow-secret-use all

# Narrow the scope
migrate-apim collect --apim <name> -g <rg> --family mcp --family a2a
migrate-apim collect --apim <name> -g <rg> --include-api 'aoai-*' --exclude-api 'legacy-*'

# Foundry accounts in other subscriptions
migrate-apim collect --apim <name> -g <rg> --foundry-subscription <sub-id>

# Check and read
migrate-apim validate inventory.json
migrate-apim summary inventory.json --format markdown
```

`collect` is read-only. It issues `GET` requests only, and never calls a `list*` secret action.
Running it needs `Reader` on the APIM instance, plus `Reader` on any Cognitive Services account
you want resolved. It prints a heartbeat per collection to stderr, because a run is dozens of
serial round trips and a slow network is otherwise indistinguishable from a hang.

**Operation policies are opt-in.** APIM exposes no bulk read for them, so collecting them costs one
round trip per operation — on one real instance that was 110 of 171 reads, nearly all returning 404,
and it took the run from 37 seconds to over eight minutes. Skipping them is recorded twice, because
"not collected" must never read as "none exist": a `notCollected` entry in `collection.coverage`
with the number skipped, and `policyRefs.operationPoliciesCollected: false` on each asset.

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
| `--operation-policies` | Also read a policy for every operation. Off by default: APIM has no bulk read, so it costs one round trip each |
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
  "generator":  { "name": "migrate-apim", "version": "0.1.0", "command": "collect" },
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

The schema is [`schemas/inventory.schema.json`](schemas/inventory.schema.json). `migrate-apim
validate` checks against it with `jsonschema` when installed, and falls back to a structural check
otherwise.

---

## Resolving a model catalogue

`collect` never reads a secret, so a provider that only exposes its models over an authenticated
endpoint comes back `unresolved`. `resolve-models` is the one step that touches a credential, which
is why it is separate and opt-in:

```bash
migrate-apim resolve-models --inventory inventory.json                       # reports what it would do
migrate-apim resolve-models --inventory inventory.json --allow-secret-use all
```

The credential is resolved in memory by replaying the retrieval recipe the inventory already
recorded — as a request, not as the recorded shell command, so the value never reaches a command
line where process arguments would expose it. It is used for one GET and dropped. It is never
written to the inventory, a file, or a log.

Knowing an upstream speaks the OpenAI protocol is also knowing its model list is one GET away, so
APIM's import naming (`*-openai-endpoint`) sets `discoverySource: "modelsEndpoint"` and the plan
proposes `resolve-models` rather than asking an operator to type model names the tool can fetch.
An endpoint that already carries its version prefix is not doubled: `.../openai/v1` becomes
`.../openai/v1/models`, not `.../openai/v1/v1/models`.

Resolving closes a question without opening new ones. A catalogue of fifty models produces fifty
model registrations and **one** naming decision, because the alias names batch with a per-model
default.

## Networking

Reaching a backend depends on how the source reaches it today, so the inventory records the
source's reachability: VNet type, public network access, the injected subnet, NAT gateway state,
and private endpoint connections.

What it deliberately does **not** do is offer that subnet for reuse. A typed gateway requires a
subnet delegated to `Microsoft.App/environments`; APIM injects into a subnet with its own
delegation, so the two cannot share one. A VNet-integrated source therefore produces a blocking
`translate` item and a `prereq:subnet` entry asking an administrator for a new delegated subnet in
the same region, rather than a plan that looks executable and fails at the first private backend.

## Saving and resuming

The plan file **is** the saved state. There is nothing else to persist: every decision lives on the
item it settles, so a later session picks up by pointing at the same file.

```bash
migrate-apim plan --inventory inventory.json -o plan.json --target <gateway-resource-id>
# ... days later, possibly a different session or machine ...
migrate-apim plan --inventory inventory.json -o plan.json     # adaptations preserved, target remembered
```

`--target` records where the plan deploys to and is sticky, so a resumed session does not have to be
told the destination again.

Two things a resume must never do quietly, both of which it now reports:

- **An item whose source facts changed** comes back as `stale`, keeping its prior decision and
  saying what moved.
- **A decision whose item no longer exists** — usually because a tool change altered an item's shape
  — is listed under `orphanedDecisions` with its value, rather than disappearing and being re-asked
  as though it had never been settled. This is not hypothetical: batching alias naming orphaned five
  real decisions from a trial run, and the first version of the merge dropped them without a word.

## Listing an MCP server's tools

APIM stores no tool names for a passthrough server -- it proxies `tools/list` to the upstream -- so
the only way to know them is to ask at runtime. `discover-tools` is the MCP counterpart of
`resolve-models`: opt-in, credential-aware, and explicit about which route it took.

```bash
migrate-apim discover-tools --inventory inventory.json                        # reports what it would do
migrate-apim discover-tools --inventory inventory.json --allow-secret-use all
```

**The route changes the answer**, so it is recorded rather than assumed:

| Route | What the list means | Recorded as |
| --- | --- | --- |
| Through the APIM gateway | What callers actually see, because the API's policies ran | `policiesApplied: true` |
| Directly at the upstream | Policies were bypassed, so it can be broader than the gateway exposes | `policiesApplied: false` |

`auto` prefers the gateway and falls back. A list obtained by bypassing policy does **not** settle
the question: the plan raises a decision saying APIM may be withholding some of those tools today,
because federating them all would widen what callers can reach.

Observed across the live instances, all three outcomes occur: a public server listed cleanly through
the gateway; an Entra-claim-gated API that refused at the gateway and listed from the upstream with
the caveat recorded; and one that refused on both routes and is reported as failed with both
reasons, never as zero tools.

The client speaks streamable HTTP, reads replies as either JSON or SSE, follows 307/308 with the
method and body intact (a missing trailing slash is the common cause), and carries the
`Mcp-Session-Id` from `initialize` with the `notifications/initialized` acknowledgement -- a
stateful server rejects everything after the handshake without them.

## The plan

`plan` matches the inventory against a **capability inventory** — `capabilities/aigateway-1.0.0b26.json`,
a curated table of what `az aigateway` can actually do, pinned to a CLI revision, plus
`capabilities/rules.json` mapping source shapes to target capabilities. A new AI Gateway release is
a data change, not a code change. With `--probe-cli`, the declared table is reconciled against the
installed extension, so a capability the docs promise but the local CLI does not expose is reported
`unavailable` instead of being planned against.

Each item is one source aspect and what becomes of it:

```jsonc
{
  "id": "item:model/a2a-intent-fdry-9a73/surface",
  "source": {"assetId": "model:a2a-intent-fdry-9a73", "aspect": "publishedSurface"},
  "status": "needs-decision",     // ready | needs-decision | adapted | excluded | stale
  "kind": "reduce-surface",
  "proposal": "split",
  "rationale": "7 of 50 operations map to the four publishable routes. No target for: threads x17, …",
  "options": [
    {"value": "split", "consequence": "Inference moves; 43 operations stay on APIM."},
    {"value": "inference-only", "consequence": "Inference moves and the rest is dropped; those callers break."}
  ],
  "target": {"capability": "alias.create", "objects": [ /* pre-shaped az inputs */ ]},
  "blocking": true
}
```

**Decision kinds.** `reduce-surface` (what part of an API can move), `translate` (maps with different
semantics), `accept-loss` (no equivalent), `enumerate` (a fact only runtime or the operator has),
`name` (what clients send as `model`), `scope` (access model), `collapse` (workspaces).

There is deliberately no `identify` kind. If a provider or protocol cannot be identified, that is a
collector gap to fix — see the governing rule below.

**Batching.** Items of the same kind and shape merge into one, so three identical `rate-limit-by-key`
policies are one decision about partitioning, not three. Which attributes make two policies
different is declared per rule (`batchOn`), so two token limits with different ceilings but the same
counter key stay one item.

### What counts as a question

> **An item needs a human only when the target cannot do something, or when the answer exists only
> in a caller's head. If the answer is derivable from APIM configuration, it is a collector bug, not
> a question.**

The same discipline as the inference rule above, one level up, and easy to violate by accident.
Asking "which provider is `meta-ai`?" looks like diligence, but APIM already answered: its backend
is named `meta-ai-openai-endpoint`, and the import wizard writes `-openai-endpoint` for
OpenAI-protocol upstreams and `-ai-endpoint` for Foundry. The collector reads that now.

Two consequences in the output: an item carrying `rulesGap` means the mapping rules were incomplete
and offered generic options — fix the rules rather than asking. And an item with `cannotAccept: true`
is an unknown from a failed read; it cannot be closed by accepting a loss, and the schema rejects
the attempt.

### The dominant decision

A live AI Gateway publishes exactly four inference routes:

```
/openai/v1/chat/completions   /openai/v1/responses
/openai/v1/embeddings         /v1/messages
```

A real Azure OpenAI import publishes far more. On `a2a-intent-fdry-9a73`, 50 operations reduce to 7:
17 thread operations, 16 vector-store, 5 assistants, 3 audio, 1 images and 1 legacy completions have
no target at all. So the first question about a model API is not how to map it but **how much of it
can move** — and `split` keeps the rest on APIM rather than dropping it.

## Applying the plan

```bash
migrate-apim apply --plan plan.json --inventory inventory.json --preflight
migrate-apim apply --plan plan.json --inventory inventory.json --next-phase            # rehearsal
migrate-apim apply --plan plan.json --inventory inventory.json --next-phase --execute  # writes
migrate-apim apply --plan plan.json --inventory inventory.json --status
```

**Migration is additive. Nothing is ever removed from APIM.** Every operation provisions into the
gateway, so a half-finished run leaves a partially built gateway and a source still serving exactly
as before. Retiring anything from APIM is the operator's decision after validating the new gateway;
this tool does not do it and will not offer to.

**A run is a rehearsal unless you pass `--execute`.** The rehearsal prints the exact command each
step would run, with `@file` arguments redacted, so the whole sequence can be reviewed before
anything is written.

A rehearsal **makes no history**. It records only that it happened, and `--execute` refuses a phase
that has not been rehearsed (`--skip-rehearsal` overrides). An earlier version recorded a rehearsed
phase as `complete`, so the documented rehearse-then-execute workflow skipped the gateway phase and
built on a gateway that was never created.

Phase completeness is **derived from verified steps, never stored**. A claim that can be checked is
checked, so a journal carrying a stale or wrong phase status repairs itself on the next read.

### Preflight

There is no transaction across steps, so the cost of finding a problem halfway is a half-built
gateway. `--preflight` refuses while any of these stands: the plan names no target; an item still
needs a decision; a settled decision has been orphaned; a referenced credential is missing or not
mechanically retrievable; or a `Microsoft.ApiManagement/service` shares the target's name, which
matters because several CLI commands dispatch by name without `--ids`. Manual prerequisites are
raised as notes and acknowledged with `--acknowledge <id>`.

### Phases

`gateway → identity → providers → models → aliases → toolServers → policies → keys`, one phase per
invocation so an operator always knows where the run is. A failed step stops its phase rather than
building on an unestablished state.

Three properties make a partial run recoverable without a transaction:

| Property | Why |
| --- | --- |
| **Read before write** | A step reads its target first and skips the write when the desired state is already there — which is both how a re-run resumes and how an ambiguous failure recovers |
| **The journal is the history** | `journal.json` records every attempt beside the plan, so the plan stays intent and a failed run resumes rather than restarts |
| **Ambiguity is named** | A write accepted but not readable back is `mutationUnknown`, never blindly retried — the next run reconciles it by reading the target |

`mutationUnknown` and `unverified` are different things and were once conflated. The first means the
write was accepted but its result could not be established; the second means the write succeeded and
this tool has no way to read it back at all. Only the first is an ambiguity to reconcile. The second
counts as done — requiring verification the tool is incapable of performing left a run stuck on a
step that had in fact succeeded — and is reported separately as "written but not confirmed by this
tool". Every capability that can be written now has a read-back, enforced by a test, so the second
case should not arise.

An item can produce several objects — an API with two models publishes two aliases — and every one
is executed; running only the first would quietly under-provision. A model's ARM id does not exist
until the models phase has created it, so aliases bind it at run time rather than guessing it at
planning time. `model-alias set` is used because it is the one documented create-or-update.

Secrets reach `az` only as `@file` with mode `0600`, never as scalar flags, because scalar flags
expose values in process arguments. The recorded `argv` redacts those paths. A step reads its target
*before* building the command, so a step already in the desired state — the commonest case on a
re-run — resolves no credential at all.

**A write-only field is skipped, not compared.** The control plane accepts `apiKey.value` on write
and omits it from every read, by design. Comparing the two can only ever fail, so an API-key
provider reported as mismatched however correctly it was configured. Verification now establishes
what can be read and says what it could not: a step whose object carries a credential is verified
with "its credential is write-only and was not read back".

## One defect family, and the audit for it

Four bugs found while driving a real deployment were all the same mistake: **the tool asserting or
demanding something it cannot substantiate.** Providers configured against an identity nothing
created; a rehearsal recorded as work done; a write with no read-back, blocking forever on
verification the tool could not perform; a comparison against a field the API never returns.

That is the rule this project already enforces on the inventory — *a failed inference must not read
as a confident negative* — applied one level down and, at first, not applied at all. So the executor
was reviewed for the whole family. Five more:

| Occurrence | What it claimed | Why it was wrong |
| --- | --- | --- |
| List comparison checked length only | "verified" | An alias pointing at a **completely different model** verified cleanly. Verification in name only is worse than none, because it produces confidence |
| The name-collision check was gated on a runner the CLI never passed | "preflight clean" | A documented blocking check silently never ran |
| Four capabilities were mapped to phases with no command builder | a step that fails at execution | Work the tool cannot do, discovered after everything else was provisioned. Now reported by preflight as manual work |
| A recorded `verified` was trusted across a changed plan | "already verified" | The item kept its id but asked for something else; the old verification proved nothing about the new ask. Steps now carry a digest of what they were verified against |
| Nothing checked that a step's provider is one the plan creates | an executable plan | A model step naming a provider nothing registers fails mid-phase. Now a blocking preflight finding |

The structural guards matter more than the individual fixes: completeness is derived rather than
stored, every capability with a builder must have a reader (enforced by a test), write-only fields
are skipped by construction, and work the tool cannot perform is surfaced before the first write
rather than failing after the last.

## Development

```bash
cd tools/migrate-apim
uv venv .venv && uv pip install --python .venv/bin/python pytest jsonschema
.venv/bin/python -m pytest -q
```

187 tests cover secret classification and recipes, policy normalization, asset detection, and a
full collector run against a canned ARM surface (`tests/fake_arm.py`) that mirrors the shapes that
matter: a passthrough MCP server, a tool projection over REST, a Foundry model API behind a
weighted backend pool with a managed-identity credential, a model API detectable only by naming
convention, a Foundry-hosted A2A agent, a workspace holding a unified model API over a
`languageModel` backend, an Azure OpenAI import whose assistants and vector-store surface cannot
move, and a plain REST API that must be excluded.

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
