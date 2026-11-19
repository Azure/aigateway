# Migration Tool Architecture

The tool maps APIM assets to Azure AI Gateway capabilities. It does this through two data files that describe the target platform, paired with a planner that reads them.

## Two-File Contract

### `capabilities/aigateway-<version>.json`

Declares what the `az aigateway` CLI extension can do. Paired to one CLI release, named in its own `cliEvidence.documentedVersion` and in its filename. Contains:

- **`capabilities[]`** — CLI commands that exist (`model create`, `model-provider create`, `policy set`, etc.), with their options, required fields, and known limitations.
- **`unsupported[]`** — Things the gateway cannot do at all (`arbitrary-policy-xml`, `workspace-creation`, etc.).
- **`serviceOnly[]`** — Things the gateway can do but the CLI cannot author yet (`alias-session-affinity`, `alias-auto-model-selection`). Separate from `unsupported` because one means "cannot migrate", the other means "migrate by hand".
- **`cliEvidence`** — The CLI revision this catalog was written against. Used to verify the installed extension matches.
- **`sourceProfiles`** — Which APIM SKUs are supported as migration sources.

### `capabilities/rules.json`

Declares how APIM shapes map to target capabilities. Never versioned separately; versioned with the catalog it references. Contains:

Every rule says what it decides about in `selects`, narrows with `where` (field predicates), `derived` (predicates computed from a record rather than read off it) or `fallback` (the rule that answers when nothing above it did), and then declares the decision. A subject is a *question*, not an asset type: one model API raises six, and they are decided separately.

- **`assets[]`** — The questions asked about one asset. `modelProvider` and `modelRegistration`, `publishedSurface`, `callerDialect`, `sessionAffinity`, `modelCatalogue` and `aliasNames` for a model API, `mcpServer`, `toolExposure` and `agent` for the rest. Each declares:
  - `verdict` — `native` (direct map), `partial` (decision needed), `gap` (no target), `handled` (carried elsewhere), `notApplicable` (skip it)
  - `capabilityId` — Which capability in the catalog handles this
  - `itemKind` — What type of plan item to raise (`reduce-surface`, `translate`, `accept-loss`, `enumerate`, `name`, `scope`, `collapse`)
  - `options` — If `partial`, the choices the operator can make
  - `proposal` — If `partial`, the recommended choice

- **`structural[]`** — The questions asked about the service rather than one asset: `workspace`, `subscriptions`, `telemetry`, `certificates`, `credentialProviders`, `coverageGap`, `policyFragment`, plus `gatewayIdentity` and `backendReachability`. A rule may narrow with `where` where one subject resolves to several cases: `policyFragment` pins a `disposition`, because a fragment the target must dissolve is not a fragment nothing includes, and neither is an `include-fragment` naming one the inventory does not hold.

- **`policies[]`** — How APIM policies map to AI Gateway policies. Every rule here `selects: policyElement`. Four passes in order: by element name (`where.name`), then by family (`where.family`), then a fallback for anything carrying a policy expression (`derived.hasExpression`), then one terminal rule (`fallback: true`) that answers for everything else.

  The last pass is what makes an unmapped element impossible rather than unlikely: before it, an element matching no rule was dropped where it was classified, and the ones that vanished were those carrying *no* expression, since an expression at least reached the pass above. It is a net and not a mapping, so `compile` holds every element in `policy.FAMILIES` to a rule of its own or a family rule and fails if one is left to it. The planner counts what reaches it into `policyCoverage.unrecognised` on the plan.

- **`publishableRoutes[]`** — The four routes AI Gateway publishes (`/openai/v1/chat/completions`, `/v1/messages`, etc.). Used to decide what part of a model API surface can move.

## How the Planner Uses Both

```
┌─────────────────────┐
│ capabilities.json   │ (CLI commands that exist)
│   + rules.json      │ (How APIM shapes map to those commands)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  CapabilityMap      │ (loads both files)
│ .capabilities{}     │ (lookup by id)
│ .asset_rules()      │ (get all asset rules)
│ .policy_rule()      │ (lookup one policy rule)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  PlanBuilder        │
│  (reads inventory)  │
└──────────┬──────────┘
           │
     ┌─────┴──────────────────────────────┐
     │                                    │
     ▼                                    ▼
┌─────────────────┐          ┌──────────────────────┐
│ For each asset: │          │ For each policy:     │
│ .asset_rules()  │          │ .policy_rule()       │
│    ↓            │          │    ↓                 │
│ selects: the    │          │ selects:             │
│ question asked  │          │ policyElement        │
│    ↓            │          │    ↓                 │
│ where/derived:  │          │ where: name, family  │
│ which answer    │          │    ↓                 │
│    ↓            │          │ Get capability id    │
│ Get capability  │          │    ↓                 │
│ from catalog    │          │ Build plan item      │
│    ↓            │          │                      │
│ Build plan item │          │                      │
│ with verdict    │          │                      │
└─────────────────┘          └──────────────────────┘
     │                                    │
     └─────────────────┬──────────────────┘
                       │
                       ▼
             ┌──────────────────┐
             │  plan.json       │
             │ (items ready or  │
             │  needing choice) │
             └──────────────────┘
```

### `capabilities/cli-surface-<version>.json`

What one released wheel actually offers: every `az aigateway` command and the options it exposes, exported by `scripts/azcli_aigw_export.py` from an installed extension. It carries the wheel's SHA-256, which is the same digest `cliEvidence.wheelSha256` names — that pairing is what stops a snapshot being checked against a release it did not come from.

The catalog says what the tool intends to call; the snapshot says what exists. `compile` compares them.

## The Version Contract

When the Azure CLI extension gains a new capability:

1. **Update the CLI** — `az aigateway` gains the command and options.
2. **Re-export the surface** — `scripts/azcli_aigw_export.py --wheel <wheel> --out capabilities/cli-surface-<version>.json`, against the extension installed into its own `AZURE_EXTENSION_DIR`.
3. **Update `capabilities/aigateway-<version>.json`** — Add the capability, update `cliEvidence.documentedVersion` and `.wheelSha256`. Rename the file to match the version it documents. If a capability became unavailable, move it to `unsupported` or `serviceOnly`.
4. **Update `capabilities/rules.json`** — Add or modify asset/policy rules to use the new capability id, and point `targetCapabilities` at the catalog.
5. **Point `DEFAULT_CATALOG` at the new file** — every entry point that is not given `--capabilities` falls back to it.
6. **Compile** — `migrate-apim compile` must pass. It is the step that makes the rest of this list checkable rather than advisory.
7. **No code change needed** — The planner reads the data files; it does not care what they contain. A new gateway release is a data change.

## Compilation

A data-driven contract is only as good as the checking of it. Two claims used to go unverified, and both were wrong in shipped releases: the catalog declared `az aigateway mcp import`, which exists in no release, and `model-provider import --foundry`, where the flag is `--foundry-resource-id`; `rules.json` carried thirteen rules no selection site could ever choose, five of them matching on keys no collector emits. Neither could fail a test — the suite injects a probe, so a fabricated command answers whatever the fake says, and a rule nobody selects is a rule nobody notices.

`migrate-apim compile` settles both, offline:

| Claim | How it is checked |
|---|---|
| The commands exist | Each capability's `command` and `read` path is in the surface snapshot |
| The options exist | Each declared and each required option is in that command's options |
| Nothing the CLI insists on is missing | Every option the snapshot marks `[Required]`, other than the identity arguments `apply` supplies from the plan's target, is one the catalog marks required |
| The snapshot is of this release | Its `wheelSha256` and version equal the catalog's `cliEvidence` |
| One release, named consistently | Catalog filename and `targetCapabilities` agree with the `cliEvidence` version |
| A newer release exists | With `--newest-release`, whether anything newer than the documented version is published — a suggestion, see below |
| The shapes are well formed | Both files against `schemas/capabilities.schema.json` and `schemas/rules.schema.json`, `additionalProperties` closed |
| Every rule can be selected | Each rule is governed by a registered selector (below) |
| Every rule field has a reader | Each field is one that some site able to select the rule declares it `reads` |
| No rule is ambiguous | In every section, no two rules look identical to the site that selects them — including the policy passes keyed on `family` and `hasExpression` |

Three severities. **Errors** fail the command. **Warnings** — a field no site reads, a version that cannot be compared — are advisory, and `--strict` promotes them; `--strict` passes on the committed data, which is the only state in which it is worth having, since a mode that cannot pass is a mode nobody runs. **Suggestions** are never fatal, not even under `--strict`, and are counted apart from the tally so a clean compile still reads as clean.

A newer release existing is a suggestion. The catalog is a claim about one release, checked against that release, and another one shipping does not make it false — there is nothing wrong to report. Calling it a warning put a problem in CI that was not there, and under `--strict` would have failed this tool's build on somebody else's release. What it is, is the moment to consider adopting, said to whoever is already editing the table.

The catalog says which release to install; nothing here reads `cli/` to find out. `cli/install.sh` is the CLI's own artifact and moves when the CLI releases, so checking the catalog against it would have made the newest release the only one the catalog could ever pin — and then every run would validate against latest, which is the opposite of pinning. the export job in `migrate-apim.yml` takes the version and digest from `cliEvidence` and installs exactly that wheel. The installers keep their own pin honest through `cli/tests/test_installers.py`.

### The selector registry

One question is answered in one place for the same reason. `migrate_apim/policy.py` owns which policy governs which API: the scope chain, `<base />` inheritance, fragment splicing and the workspace qualification of every name. `collect` asks it to decide what authenticates a backend and `plan` asks it to decide what a policy item covers, so the two cannot drift — which they had, the collector folding in the product and global policy but never the workspace, and the planner answering for neither a fragment nor an operation. Nothing is re-derived to answer it: `include-fragment` and `base` are already elements in the inventory, each with its section and path.

`compile` holds two invariants that keep this true rather than aspirational: every subject a site selects on has at least one rule, so a question the planner asks cannot be answered in code instead of in the file; and every `where` key names a field `inventory.schema.json` declares, so a rule cannot match on something no record carries and simply never fire. Both are checked against the registry the planner itself uses.

Reachability is checkable only because selection happens in one place. `migrate_apim/dispatch.py` defines `Selector`, which both performs a match and states what the match looks at; `plan.py` and `capability.py` declare one per selection site. `compile` imports those modules and reads `dispatch.REGISTRY`, so the contract it checks is the one the planner runs — not a second declaration that can drift from it.

A selector *governs* a rule when the rule decides the subject that site selects, its `where` and `derived` keys are a subset of the ones that site examines, and every value it pins is one that site accepts. Subset, not equality: a rule may pin fewer keys, but pinning more means the surplus is silently ignored and the rule matches more broadly than it reads.

A selector also declares what it `reads`: the rule fields it consumes once it has chosen one. A field outside that union is a field somebody wrote expecting an effect it does not have — the same defect as an unreadable `where` key, one layer in — and it is found the same way, by asking the sites rather than by keeping a list in the checker. A list in the checker is a second declaration, and it drifted: `constraints` and `toolDiscoveryGuidance` sat unread for releases because nobody thought to add them to it.

This is why the six `plan._structural` branches declare six selectors rather than one, and why `callerDialect` declares two: branches that share a subject and nothing else each raise a different item and take a different set of fields, and a single selector would have to declare the union — excusing a field on the workspace rule because the telemetry branch happens to read it, or a `proposal` on the indeterminate-dialect rule that nothing reads. The declaration is only worth having while it is the narrowest true one.

Adding a selection site means declaring a selector there. A rule that no selector governs is an error, with the reason given — an unread key is a different mistake from an unknown value, and they have different fixes.

## The Probe

When the planner runs with `--probe-cli`, it reconciles the declared catalog against the installed extension:

```python
CapabilityMap.probe()
  for each capability:
    if command not in installed CLI:
      support = "unavailable"
    elif required_options not in installed options:
      support = "unavailable"
    else:
      support = "conditional"
```

A capability `declared` in the catalog but `unavailable` in the installed CLI becomes a plan item with `capabilityUnavailable`, pointing the operator to upgrade the extension.

## What Stays Out

- **AI Gateway internals** — The tool describes what the CLI can do, not how the gateway implements it.
- **Source code assumptions about the target** — No hardcoded knowledge of "aliases are limited to 30 models" or "AI Gateway publishes four routes". Read it from the data files instead.
- **LLM instructions with platform details** — Agents derive capability facts from the codebase, schemas, and data files.

## Testing

The test suite provides a fake probe (`tests/test_collect.py`, `tests/test_capability.py`) so tests are offline. A new capability is tested by:

1. Adding it to `aigateway-<version>.json`.
2. Adding a rule to `rules.json`.
3. Adding a test case that verifies the planner produces the right item.
4. Running the plan and apply builders against the test case.

No code change required in the builder itself — if the capability and rule are correct, the planner works.

The fake probe is also the reason `compile` exists. It answers whatever a test tells it to, so it can confirm that the planner handles an unavailable capability correctly, but it can say nothing about whether the capability is real. `tests/test_compile.py` covers the other half, by reconstructing each defect that shipped and asserting the compiler names it.

## CI

`.github/workflows/migrate-apim.yml` runs on every pull request and push touching the tool, with one job per link in the chain:

| Job | What it proves | Needs |
|---|---|---|
| `compile` | the catalog and rules compile against the committed snapshot, the suite passes, and a newer `cli-v*` release is reported | nothing — offline, no `az`, no credentials |
| `export` | the committed snapshot is what the pinned wheel really offers | the Azure CLI and the network |

Together they give catalog ⊆ reality, and neither covers the other: `compile` can gate every change only because it trusts the snapshot, and a snapshot is a file somebody could hand-edit.

They are one workflow because they were never independent. The snapshot cannot change without `capabilities/` changing, so `export` never had a reason to run that `compile` did not also have — two files meant two statuses to read for one answer.

Neither is wired to `cli-v*` tags. A CLI release is not this tool's build to redden, so the "a newer release exists" signal is raised offline, where the person it is addressed to is already standing. The cost is that it is only asked when somebody touches this tool: a pin can sit stale between visits, but it cannot be stale while being worked on.

The drift check compares what two snapshots *claim* — version, digest, commands, options — rather than their bytes. The file also records the azure-cli-core that produced it, and that runner installs whatever is current; a byte comparison would report the next core release as drift in the wheel, which is both wrong and the kind of wrong that teaches people to ignore the check. `azcli_aigw_export.py --compare` is that comparison, and it names the command and flag that moved, so the log says what to re-pin rather than only that something did.
