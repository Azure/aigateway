---
description: Integrate existing Azure AI Gateway models and MCP tools into an app or a requested standalone agent.
argument-hint: [gateway resource id or runtime connection details] [use case]
---

# /aigateway:build

Read and follow `skills/use-ai-gateway/SKILL.md` in **Build** mode.
Use `$ARGUMENTS` and the existing project to choose the shortest path.
Preserve supplied endpoint, callable name, protocol and secure credential binding;
a complete runtime contract needs no ARM discovery or management sign-in.
Load only the relevant integration recipe. Gateway configuration stays unchanged.

Integrate into the existing app; scaffold a complete isolated agent only when
requested. Verify the exact operation with a separately authorized bounded
request and validate its response shape, not just HTTP status. Missing access,
credentials or approval remains an explicit unperformed check. Never expose
secrets, bypass policies, switch identities/headers automatically or invoke
unselected MCP tools.
