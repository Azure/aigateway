---
description: Select authorized Azure AI Gateway models and MCP tools, or explain supplied runtime assets.
argument-hint: [gateway resource id or runtime connection details] [use case]
---

# /aigateway:discover

Read and follow `skills/use-ai-gateway/SKILL.md` in **Discover** mode.
Use `$ARGUMENTS` to select a small task-relevant shortlist. Prefer scoped native
CLI metadata reads when authorized; otherwise use published connection details
without ARM discovery, management sign-in or guessed assets.

Explain callable names/operations, tools, constraints, tradeoffs and unknowns.
Only an already-authorized credential permits read-only MCP listing; follow
the verified protocol and pagination. Do not acquire credentials, retrieve
secrets, generate code, mutate configuration or execute tools. Stop at selection;
integration belongs to `/aigateway:build`.
