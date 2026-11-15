# Migration Tool Architecture

The tool maps APIM assets to Azure AI Gateway capabilities. It does this through two data files that describe the target platform, paired with a planner that reads them.

## Two-File Contract

### `capabilities/aigateway-<version>.json`

Declares what the `az aigateway` CLI extension can do. Paired to a specific CLI release (e.g., `cli-v1.0.0b31`). Contains:

- **`capabilities[]`** — CLI commands that exist (`model create`, `model-provider create`, `policy set`, etc.), with their options, required fields, and known limitations.
- **`unsupported[]`** — Things the gateway cannot do at all (`arbitrary-policy-xml`, `workspace-creation`, etc.).
- **`serviceOnly[]`** — Things the gateway can do but the CLI cannot author yet (`alias-session-affinity`, `alias-auto-model-selection`). Separate from `unsupported` because one means "cannot migrate", the other means "migrate by hand".
- **`cliEvidence`** — The CLI revision this catalog was written against. Used to verify the installed extension matches.
- **`sourceProfiles`** — Which APIM SKUs are supported as migration sources.

### `capabilities/rules.json`

Declares how APIM shapes map to target capabilities. Never versioned separately; versioned with the catalog it references. Contains:

- **`assets[]`** — How to map each APIM asset family (models, mcpServers, agents, modelProviders). Each rule matches on asset properties (`family`, `modelsStatus`, `surfaceStatus`, etc.) and declares:
  - `verdict` — `native` (direct map), `partial` (decision needed), `gap` (no target), `handled` (carried elsewhere), `notApplicable` (skip it)
  - `capabilityId` — Which capability in the catalog handles this
  - `itemKind` — What type of plan item to raise (`reduce-surface`, `translate`, `accept-loss`, `enumerate`, `name`, `scope`, `collapse`)
  - `options` — If `partial`, the choices the operator can make
  - `proposal` — If `partial`, the recommended choice

- **`structural[]`** — Rules for cross-asset things (workspaces, subscriptions, telemetry, coverage gaps).

- **`policies[]`** — How APIM policies map to AI Gateway policies. Matched by element name, then by family, with fallbacks for expressions and unknowns.

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
│ Match on        │          │ Match on element     │
│ family,         │          │    ↓                 │
│ modelsStatus,   │          │ Get capability id    │
│ surfaceStatus   │          │    ↓                 │
│    ↓            │          │ Build plan item      │
│ Get capability  │          │                      │
│ from catalog    │          │                      │
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

## The Version Contract

When the Azure CLI extension gains a new capability:

1. **Update the CLI** — `az aigateway` gains the command and options.
2. **Update `capabilities/aigateway-<version>.json`** — Add the capability, update `cliEvidence.documentedVersion` and `.wheelSha256`. If a capability became unavailable, move it to `unsupported` or `serviceOnly`.
3. **Update `capabilities/rules.json`** — Add or modify asset/policy rules to use the new capability id.
4. **No code change needed** — The planner reads the data files; it does not care what they contain. A new gateway release is a data change.

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
