---
description: Discover authorized Azure AI Gateway assets, or explain supplied runtime endpoints when control-plane discovery is unavailable.
argument-hint: [gateway resource id, runtime endpoint, or connection details]
---

# /aigateway:discover

Discover — and only discover — the AI assets registered in an Azure AI Gateway. This is a
**read-only** exploration command: it lists models and MCP tool servers when authorized,
or helps the user understand supplied runtime assets. It never provisions, updates, or deletes
anything, and it does **not** scaffold code (use `/aigateway:build` for that).

Follow the discovery workflow defined in the bundled skill
`skills/use-ai-gateway/SKILL.md` — specifically **Part 1 — Discover & select assets**:

1. Use `$ARGUMENTS` and choose the skill's access path. Gateway-wide enumeration
   needs an ARM resource ID and authorized control-plane reads. Without those
   permissions, do not require an ARM ID, enumerate resources, or request elevated
   access. Use supplied published model names/protocols and known MCP URLs instead.
   If only a host is known, explain authentication and URL shapes and ask only for
   the missing published connection details. A host alone cannot identify assets.
   For authorized ARM reads, follow the skill's resource-type/API-version rules.
2. When permitted, list published **model aliases** and their supported operations. Use
   `properties.aliasName` (or the alias resource name when absent) as the callable
   model name. Only fall back to backend-model discovery when alias support is
   explicitly unsupported; for that legacy path use `properties.deployment.modelName`.
   Otherwise preserve the supplied callable name and operation; mark backend,
   routing and capability details unknown rather than assuming a chat endpoint.
3. When permitted, list **MCP tool servers** and their advertised protocol versions.
   Without management access, work with known MCP endpoints only. Use the
   verified published gateway MCP endpoint or construct
   `<gateway-host>/default/toolservers/<toolServerName>/mcp`, never an upstream URL.
   Probe `tools/list` only with an already-authorized runtime credential, using
   the skill's version-aware procedure or published/runtime-negotiated connection
   contract. Unread version metadata is not an omitted setting. Listing tools at a
   known endpoint does not enumerate gateway servers. Otherwise report tools as
   unverified. Do not retrieve secrets or execute tools for discovery.
4. Give a task-focused selection brief: callable models/protocols, known MCP tools,
   relevant routing/policy constraints when readable, and explicit unknowns. Explain
   the recommendation's tradeoff and confirm finite selections. Do not claim a
   complete catalog or successful runtime verification without evidence.

Stop after presenting the assets. Do not acquire credentials or generate code unless
the user explicitly asks to continue (or runs `/aigateway:build`).
