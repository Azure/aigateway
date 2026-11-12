---
description: Connect an existing application or workflow to Azure AI Gateway models and MCP tools.
argument-hint: [gateway resource ID, runtime endpoint, or connection details] [use case]
---

# /aigateway:build

Connect the requested existing gateway model or MCP tools to the user's
application or workflow. Follow `skills/use-ai-gateway/SKILL.md`; skip
discovery when the supplied callable contract is complete.

1. Reuse supplied details. If needed, make relevant read-only discovery with
   the current Azure CLI identity. Do not require management access for a known
   runtime endpoint. Preserve explicit asset choices; ask only for missing
   published details.
2. Use an existing approved Entra or gateway-key binding as
   `Authorization: Bearer`. Never retrieve, create or rotate keys here.
3. Integrate the exact model operation or selected MCP tools into the existing
   project using its conventions. List MCP tools before configuring or calling
   them; get approval for the specific call and arguments.
4. Verify one bounded request after confirming any cost or side effect. Report
   the actual result; errors and timeouts are not success.

Do not change gateways, assets, roles, keys, policies or backend connections.
Preserve the callable alias, published endpoint and `/default/` workspace.
Never use an upstream endpoint, substitute a backend model name or expose a
credential.
