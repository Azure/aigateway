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
Do not mutate external prerequisites except for the skill's confirmed role-grant
exception. Do not use legacy service destinations or bypass a missing command
with REST.

Use `$ARGUMENTS` to resolve the target and operation. Confirm the active
subscription and inspect current state before proposing commands. Prefer read-only
`list` and `show` operations when the user's intent is diagnostic. Explicit intent
authorizes routine creates and updates. Follow the skill's specific confirmation
gates for destructive/access changes, secret retrieval, OAuth initiation, and
sensitive payload capture. Report unsupported CLI activities explicitly.

Migrating an existing APIM workload is a different job with its own command. If
the request is to assess, plan, or execute such a migration, hand it to
`/aigateway:import` rather than improvising one here: do not read or convert
`Microsoft.ApiManagement/service` configuration, and do not use management
commands as a substitute for the migration workflow.
