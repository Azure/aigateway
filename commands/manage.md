---
description: Configure and operate an Azure AI Gateway, including assets, model policies, identities, networking, and secret rotation.
argument-hint: <gateway-name> <resource-group> <operation>
---

# /aigateway:manage

Configure and operate an existing Azure AI Gateway for an authorized administrator or
platform engineer. Follow the complete workflow in
`skills/manage-ai-gateway/SKILL.md`, especially **Configure gateway assets** and
**Operate**. Use the current native `az aigateway` command group, scoped to
`Microsoft.ApiManagement/aigateways` and its own default-workspace children.
Do not mutate external prerequisites, use legacy service destinations, run
Foundry convenience onboarding with external role-grant side effects, or
bypass a missing command with REST.

Use `$ARGUMENTS` to resolve the target and operation. Confirm the active
subscription and inspect current state before proposing commands. Prefer read-only
`list` and `show` operations when the user's intent is diagnostic. Explicit intent
authorizes routine creates and updates. Follow the skill's specific confirmation
gates for destructive/access changes, secret retrieval, OAuth initiation, and
sensitive payload capture. Report unsupported CLI activities explicitly.

If the request is to assess, plan, execute, or resume an APIM migration, stop
this workflow and use `skills/migrate-ai-gateway/SKILL.md` (or direct the user to
`/aigateway:migrate`). Use its local inventory/validation helpers and do not
use management commands to bypass its capability or approval gates.
After any mutation, verify from the command result and, where supported, the
corresponding `show` or `list` command. Report the outcome without exposing
secrets.
