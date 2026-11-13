---
name: migrate-apim
description: Migrate AI workloads from Azure API Management to Azure AI Gateway. Use when asked to inventory, assess, plan, or execute a move of model APIs, MCP servers, or A2A agents from an APIM instance to Microsoft.ApiManagement/aigateways.
---

# Migrate APIM AI workloads to Azure AI Gateway

The tool does two jobs: inventory an APIM instance, and propose a migration plan. Your job is the
third: work with the operator to adapt that plan, then execute it one object at a time.

## Make the tool runnable first

Nothing separate to install: the tool ships inside this plugin. Resolve it in this order, and say
which one you used:

1. The copy shipped with this plugin, under its root at `tools/migrate-apim`. In Claude Code that
   root is `${CLAUDE_PLUGIN_ROOT}`.
2. `tools/migrate-apim` in a clone of `github.com/Azure/aigateway`.
3. `migrate-apim` already on `PATH` — check with `migrate-apim --version`. This holds only if
   someone installed it earlier; nothing publishes the command.

It is a Python package with no runtime dependencies, needing 3.10 or later, so it runs from wherever
it already sits:

```
PYTHONPATH=<tool-dir> python3 -m migrate_apim.cli --version
```

The examples below write `migrate-apim` for brevity — read that as whichever invocation you
resolved. `pip install -e <path>` installs the real command, but only ever from a clone: the plugin
copy lives under a path pinned to one commit, so an editable install against it breaks the next time
the plugin updates. Ask before installing anything into the operator's environment.

If none of those resolve, say so and stop. Do not approximate the tool with `az` commands: the
inventory's value is that it is complete and says where it is not, which a hand-rolled read is not.

Every command reads ARM with the operator's Azure CLI login, so `az login` has to have happened.
The tool resolves `az` on `PATH` itself, Windows included; if it is missing or logged out, that is
the first line of the error. Ask the operator to log in rather than wrapping or patching the tool.

```
migrate-apim collect  --apim <name> -g <rg> -o inventory.json
migrate-apim plan     --inventory inventory.json -o plan.json
# ... run resolve-models / discover-tools where the plan proposes them ...
# ... adapt plan.json with the operator ...
migrate-apim plan     --inventory inventory.json -o plan.json   # re-run; adaptations survive
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

The tool writes progress to stderr and results to stdout. Do not read stderr output as failure —
some shells, PowerShell among them, present it as an error. Use the exit code. If a command does
fail, report its message as written rather than working around it: it names the cause.

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
are engineering work on `migrate-apim`, not questions for the operator. An item carrying `rulesGap`
means the mapping rules are incomplete; fix `capabilities/rules.json` rather than asking with the
generic options. Likewise an unrun verification is "not run", not "unknown".

An item with `cannotAccept: true` is an unknown — a control-plane read that failed. It cannot be
closed by accepting a loss; re-collect with the right access, or have the operator state what is
there.

The plan's `plannerGaps` is the same category and blocks `apply`. Each entry names work an item
commits to that the plan does not produce — a required field nothing supplied, or a settled
decision that yields no target object. Read it as a bug report against `migrate-apim`, not as a
question: re-collect if the inventory is older than the tool, otherwise fix the planner. Never
settle the named item some other way just to clear the gap; that discards the work rather than
doing it.

An item carrying `evidence.targetSupports: true` is a third thing again: the gateway *can* do this
and the installed CLI cannot author it. Say so when you put it to the operator — "the gateway
supports this, we cannot configure it from here" is a different decision from "the target cannot do
this". These come from the catalogue's `serviceOnly` list, and the honest outcome is usually
`accept-loss` plus a line in the final report telling the operator what to set by hand.

## 3. Execute

**Migration is additive.** Everything is provisioned into the gateway; nothing is removed from
APIM. A failed run leaves a partially built gateway and a source still serving as before. Retiring
anything from APIM is the operator's decision after they have validated the new gateway — do not
do it, and do not offer to.

**Make the TODO list before the first write.** `apply --preflight` prints the eight phases and
asks for it: create one entry per phase, in that order, with whatever task tool your host gives
you — `TodoWrite` in Claude Code. If you have none, say so once and print the checklist in every
reply instead. A migration runs one phase per turn over many turns; the list is what holds it
together, and the phase nobody is tracking is the phase that goes missing.

Every later `apply` run reprints the checklist with `>` on the phase being run. Tick your entries
from what the tool printed, never from memory: its list is rebuilt from the journal, yours is not.
Work one phase at a time, report what it produced, and stop for the operator before the next.

A phase listed as `by hand` has work this tool has no builder for and no steps to run, so
`--next-phase` passes over it. It is not done — carry it into the final report as configuration the
operator applies themselves.

Only once nothing is `needs-decision`, `stale`, or orphaned.

```bash
migrate-apim apply --plan plan.json --inventory inventory.json --preflight
migrate-apim apply --plan plan.json --inventory inventory.json --next-phase              # rehearsal
migrate-apim apply --plan plan.json --inventory inventory.json --next-phase --execute
```

Start with `--preflight` and resolve everything blocking. Then **rehearse each phase before
executing it** — a run without `--execute` prints the exact commands, which is what you show the
operator. A rehearsal writes nothing and advances nothing, so rehearse the same phase you are about
to execute; `--execute` refuses a phase you have not. Phases are `gateway → identity → providers → models → aliases → toolServers → policies →
keys`; run one per turn, report what it produced, and stop before the next.

If a step comes back `mutationUnknown`, the write was accepted but its outcome could not be
established. Do not retry it. Re-running the phase reconciles it by reading the target.

Read what a phase prints, not just whether it failed. `unverified` means the write happened and
could not be confirmed — report it as written, never as verified. A line marked `not performed`
names work in that phase this tool has no implementation for: it will be absent from the gateway
until someone applies it by hand, so carry it into the final report rather than letting a phase
that printed no errors read as a phase that did everything. `no steps in this phase` is a real
outcome too, and worth saying out loud.

Before the first write, put the `prerequisites` list to the operator. These are outside the
gateway's resource provider — Foundry RBAC grants, caller `AI Gateway Models User` / `Tools User`
roles, Entra consent, `mcp authorize` completion, private endpoint approvals. A plan that executes
without them produces a gateway that reads as configured and does not serve traffic.

**You may offer to run the ones that are commands, and you should.** A prerequisite carrying a
`commands` array has the exact invocation the plan specified; run that, not one you compose
yourself — the role name, its definition id and the scope are all decided there. The rules:

- Show the command and say what it changes: which principal gets which role on which scope.
- Get explicit agreement first. A role assignment is a privilege change, not a step in a checklist.
- Never acknowledge a prerequisite to get past preflight. `--acknowledge` records that the work is
  *done*, so acknowledging it yourself asserts something you have not established.
- Say when it failed and why. Lacking the permission to grant a role is a normal outcome and the
  operator needs to hear it, not a retry.
- A grant made is part of the migration record: report it alongside what `apply` provisioned.

Some prerequisites are not commands at all — Entra consent and private endpoint approval are
decisions someone makes in a portal. Do not simulate those.

Never pass a secret as a scalar CLI flag; process arguments are visible. A `{"$secretRef": "..."}`
placeholder is resolved from the inventory's retrieval recipe at apply time and written to a
mode-`0600` file passed as `@path`.

## 4. Report honestly

A management read-back proves saved configuration. It does not prove inference works, tools are
exposed, policies are enforced, or telemetry is arriving. Keep **configured** and **working**
separate, and say which you have.

So end by sending the operator to look at the gateway themselves. When no phases remain, `apply`
prints the link — `https://ai.gateway.azure.com<resourceId>/overview` — and it belongs in the final
report alongside what to check there: the models, tool servers and policies the run provisioned,
anything a phase left `unverified`, and anything listed as `by hand`. Suggest the check; their
eyes on the portal is not something you can do for them or report as done.

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
