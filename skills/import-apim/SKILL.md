---
name: import-apim
description: Migrate AI workloads from Azure API Management to Azure AI Gateway. Use when asked to inventory, assess, plan, or execute a move of model APIs, MCP servers, or A2A agents from an APIM instance to Microsoft.ApiManagement/aigateways.
---

# Migrate APIM AI workloads to Azure AI Gateway

The tool is `tools/apim-import`. It does two jobs: inventory an APIM instance, and propose a
migration plan. Your job is the third: work with the operator to adapt that plan, then execute it
one object at a time.

```
apim-import collect  --apim <name> -g <rg> -o inventory.json
apim-import plan     --inventory inventory.json -o plan.json
# ... run resolve-models / discover-tools where the plan proposes them ...
# ... adapt plan.json with the operator ...
apim-import plan     --inventory inventory.json -o plan.json   # re-run; adaptations survive
```

`plan.json` is the one living artifact. It is proposed by the tool, adapted in place, and executed.
Do not keep decisions in the conversation — the plan is the record.

## Assessment is not execution approval

Collecting an inventory and proposing a plan are read-only. Neither authorises creating anything.
Do not provision a gateway because someone asked whether a migration is possible.

## 1. Collect

`collect` is read-only and never reads a secret. If the operator has already named a subset, honour
it; do not open by asking "the whole instance or just AI?".

Check `collection.coverage` for `failed` entries before trusting the result. A failed read is an
unknown, not an absence.

## 2. Adapt the plan

Every item arrives **proposed**, with a rationale and the options spelled out. `needs-decision`
means "confirm or change this", not "the tool has no opinion". Read `plan.json`, then work through
the unsettled items with `AskUserQuestion`.

**Group by kind, ask one dependency-ready question at a time.** The plan already batches identical
things — three identical rate limits are one item. Do not unbatch them.

| Kind | What you are asking |
| --- | --- |
| `reduce-surface` | AI Gateway publishes four inference routes. Which part of this API moves, and what happens to the rest? |
| `translate` | It maps, but the semantics differ. Which target semantics? |
| `accept-loss` | No equivalent. Accept, compensate, retain in APIM, or block? |
| `enumerate` | A fact that only exists at runtime or in the operator's head. |

An `enumerate` item about an MCP server's tools is **not** a question either: run
`discover-tools`, which calls `tools/list` for you. Prefer the gateway route -- that is the list
callers actually see. If it falls back to the upstream, the API's policies did not run, so say so
when you put the list to the operator rather than presenting it as what the gateway exposes.

An `enumerate` item proposing `resolve-models` is **not** a question. Run it — the tool fetches the
catalogue using the credential the inventory already knows how to retrieve, and re-planning closes
the item. Asking the operator to type model names the tool can fetch is the governing rule being
broken in the other direction.
| `name` | What clients send as `model`. A default is proposed; confirm or replace. |
| `scope` | How gateway-wide keys and Entra RBAC replace per-product subscription keys. |
| `collapse` | Only the `default` workspace exists on the target. |

Lead with `blocking: true` items, and put the consequence in the question — "assistants, threads and
vector-store callers stop working" is the decision, not "44 operations are unpublishable".

To record an answer, set **only** `status: "adapted"` and `decision: "<chosen value>"` on the item.
The generator handles the rest. Then re-run `plan`: adapted items are preserved, and an item is
re-opened only when the APIM facts *it* rested on changed, with `staleReason` saying what moved.

### What is not a question

> An item needs a human only when the target cannot do something, or when the answer exists only in
> a caller's head. **If the answer is derivable from APIM configuration, it is a collector bug.**

So: a provider you cannot identify, a dialect you cannot read, a tool list you did not fetch — these
are engineering work on `apim-import`, not questions for the operator. An item carrying `rulesGap`
means the mapping rules are incomplete; fix `capabilities/rules.json` rather than asking with the
generic options. Likewise an unrun verification is "not run", not "unknown".

An item with `cannotAccept: true` is an unknown — a control-plane read that failed. It cannot be
closed by accepting a loss; re-collect with the right access, or have the operator state what is
there.

## 3. Execute

**Migration is additive.** Everything is provisioned into the gateway; nothing is removed from
APIM. A failed run leaves a partially built gateway and a source still serving as before. Retiring
anything from APIM is the operator's decision after they have validated the new gateway — do not
do it, and do not offer to.

Keep a visible TODO of the phases and say which one you are in. Work one phase at a time, report
what it produced, and stop for the operator before starting the next.

Only once nothing is `needs-decision` or `stale`. Work the plan one object at a time and narrate
each one. Dependency order is fixed: gateway → identity → provider → model → alias, with MCP and
telemetry as parallel branches and policies last.

Before the first write, put the `prerequisites` list to the operator. Those are steps the tool
cannot perform — Foundry RBAC grants, caller `AI Gateway Models User` / `Tools User` roles, Entra
consent, `mcp authorize` completion, private endpoint approvals. A plan that executes without them
produces a gateway that reads as configured and does not serve traffic.

Never pass a secret as a scalar CLI flag; process arguments are visible. A `{"$secretRef": "..."}`
placeholder is resolved from the inventory's retrieval recipe at apply time and written to a
mode-`0600` file passed as `@path`.

## 4. Report honestly

A management read-back proves saved configuration. It does not prove inference works, tools are
exposed, policies are enforced, or telemetry is arriving. Keep **configured** and **working**
separate, and say which you have.

The migration is not finished when objects exist. Every caller changes host, path and auth header,
and for a `split` decision some routes moved while others stayed on APIM. The cutover guide is part
of the deliverable, not a follow-up.

## Boundaries

- Target resource type is `Microsoft.ApiManagement/aigateways`, implicit `default` workspace only.
- Use `az aigateway`. Do not substitute `az rest`, generic resource writes, or an SDK.
- Confirm before: deletion, whole-collection replacement, policy removal or weakening, key creation
  or rotation, identity changes, network access changes, private endpoint decisions, secret
  retrieval, OAuth initiation, and payload capture.
- The source APIM and the target gateway may share a name, and several commands dispatch by name
  without `--ids`. Check the resolved resource type before every write.
