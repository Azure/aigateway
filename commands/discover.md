---
description: Discover authorized Azure AI Gateway model and MCP endpoints, or identify the exact details an asset owner must provide.
argument-hint: [gateway resource ID, runtime endpoint, or connection details]
---

# /aigateway:discover

List the requested gateway's model aliases, MCP servers and key metadata, or
explain how to use supplied runtime details. Follow
`skills/use-ai-gateway/SKILL.md` and its
[connection reference](../skills/use-ai-gateway/references/connection.md).

Use the current Azure CLI identity for relevant read-only discovery when
needed. Do not sign in, switch identity, request broader access, retrieve key
values, call models/tools, or change gateway configuration. A denied or failed
read is not an empty inventory.

Return the exact task-relevant endpoint, callable name, operation/protocol and
authentication requirement. If discovery is unavailable, ask only for missing
published details. Stop after discovery; use `/aigateway:build` to integrate
or make runtime requests.
