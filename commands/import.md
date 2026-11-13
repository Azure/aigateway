---
description: Migrate AI workloads from an Azure API Management instance to Azure AI Gateway: inventory the source, propose a migration plan, adapt it with the operator, then provision it phase by phase.
argument-hint: <apim-name> <resource-group> [target-gateway]
---

# /aigateway:import

Move model APIs, MCP servers, and A2A agents from `Microsoft.ApiManagement/service` to
`Microsoft.ApiManagement/aigateways`. Follow the complete workflow in
`skills/import-apim/SKILL.md`. Use `$ARGUMENTS` to resolve the source instance and, when
given, the target gateway.

The work has four steps and they do not collapse into one another:

1. **Inventory** the APIM instance with `apim-import collect`. Facts only, no verdicts.
2. **Plan** with `apim-import plan`, which matches that inventory against what the
   installed `az aigateway` can actually do.
3. **Adapt** the plan with the operator. Everything that does not map one-to-one is an
   item to settle; record a decision by setting only `status` and `decision`, then
   re-run `plan`.
4. **Provision** with `apim-import apply`, one phase at a time.

Before step 1, make the tool runnable and say which way you did it. In order: `apim-import`
already on `PATH`; otherwise the copy shipped with this plugin at
`${CLAUDE_PLUGIN_ROOT}/tools/apim-import`; otherwise `tools/apim-import` in a clone of
`github.com/Azure/aigateway`. It is a dependency-free Python package needing 3.10 or later —
`pip install -e <path>` installs the `apim-import` command, and `python -m apim_import.cli`
runs it from the directory without installing. If none of those resolve, say so and stop
rather than approximating the tool with `az` commands.

**Migration is additive.** Everything is provisioned into the gateway and nothing is removed
from APIM. A failed run leaves a partially built gateway and a source still serving as
before. Retiring anything from APIM is the operator's decision after they have validated the
new gateway — do not do it, and do not offer to.

Ask the operator only what APIM cannot answer. A provider you cannot identify, a dialect you
cannot read, or a tool list you did not fetch is a bug in the tool, not a question: the
governing rule and the question kinds are in the skill. Items carrying `plannerGaps`,
`rulesGap`, or `cannotAccept` are defects or unknowns and cannot be settled by accepting a
loss. An item whose `evidence.targetSupports` is true means the gateway can do it and the
installed CLI cannot author it — put that distinction to the operator rather than reporting a
capability the target lacks.

Run `apply --preflight` first and resolve everything blocking. Rehearse each phase before
executing it, show the operator the actual commands, and get explicit agreement before
`--execute` creates real Azure resources. Work one phase per turn, keep a visible TODO of
where you are, and report what each phase produced before starting the next. Put the manual
prerequisites — Foundry RBAC, caller role assignments, Entra consent, private endpoint
approvals — to the operator before the first write, and never acknowledge one on their
behalf.

Never pass a secret as a scalar CLI flag, write one to a file the tool did not create, or
print one. The inventory carries retrieval recipes, not values.

Report honestly. A management read-back proves configured, not working: do not claim the
migration works, distinguish `unverified` from `verified`, name the work a phase could not
perform, and separate what you provisioned from what still needs the operator.
