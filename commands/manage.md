---
description: Configure and operate an Azure AI Gateway, including assets, model policies, identities, networking, and secret rotation.
argument-hint: <gateway-name> <resource-group> <operation>
---

# /ai-gateway:manage

Configure and operate an existing Azure AI Gateway for an authorized administrator or
platform engineer. Follow the complete workflow in
`skills/manage-ai-gateway/SKILL.md`, especially **Configure gateway assets** and
**Operate**. Use the current `az aigateway` command group.

Use `$ARGUMENTS` to resolve the target and operation. Confirm the active
subscription and inspect current state before proposing commands. Prefer read-only
`list` and `show` operations when the user's intent is diagnostic. Explain the
impact and obtain explicit confirmation immediately before deletes, API-key
regeneration, identity removal, overwrites, or network access changes.

If the request is to assess, plan, execute, or resume an APIM migration, stop
this workflow and use `skills/migrate-ai-gateway/SKILL.md` (or direct the user to
`/ai-gateway:migrate`). Use its local inventory/validation helpers and do not
use management commands to bypass its capability or approval gates.
After any mutation, verify from the command result and, where supported, the
corresponding `show` or `list` command. Report the outcome without exposing
secrets.
