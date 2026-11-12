---
name: use-ai-gateway
version: 3.2.0
description: Discover callable Azure AI Gateway model and MCP endpoints, then connect them to an existing app or developer workflow.
---

# Use Azure AI Gateway assets

Help developers consume existing gateway assets. Route from the requested
outcome; use supplied connection details before attempting discovery.

| User wants to | Read |
| --- | --- |
| Find gateway URLs, model aliases, MCP servers, or key metadata | [Connection and discovery](references/connection.md) |
| Call or integrate a model | [Models](references/models.md), then [authentication](references/authentication.md) |
| Connect to an MCP server, list tools, or call a tool | [MCP](references/mcp.md), then [authentication](references/authentication.md) |
| Diagnose a failed or unexpected request | [Diagnostics](references/diagnostics.md) |

## Resolve only what the task needs

1. Reuse the supplied endpoint, alias/tool name, protocol, project and credential
   binding. If they form a complete callable contract, skip Azure inventory.
2. If endpoint or asset details are missing, try the relevant read-only Azure
   discovery under the current signed-in identity and selected subscription;
   see [connection](references/connection.md). Do not sign in, switch identity,
   scan other subscriptions, or request broader access to make optional
   discovery work.
3. If discovery is unavailable, ask for only the missing published contract:
   model operation URL, callable alias and API format; or MCP endpoint,
   protocol/version and connection instructions. Ask for a secure credential
   binding, never a secret pasted into chat. If the user wants Azure inventory,
   explain the management-read access and scope needed; it is not required to
   use supplied runtime details.
4. If there are multiple viable assets, shortlist only those that meet the
   user's stated needs and explain the material tradeoff. Preserve explicit
   choices; do not audit routing or policies unless they affect the task.

## Connect and verify

- For models, use the published operation URL, exact callable alias and
  advertised API format. The alias is the request's `model`, not a backend
  deployment name.
- For MCP, use the gateway server endpoint and compatible MCP client. List
  tools before selecting them; preserve each exact name and schema.
- Integrate into the user's existing project and workflow. Follow its language,
  framework and dependency conventions; do not scaffold a standalone agent
  unless requested.
- Use one approved runtime credential as `Authorization: Bearer`. Keep it in
  the existing secret store or environment binding. Never expose it in code,
  logs, prompts, URLs or browser bundles.
- Before a live request, verify its destination and whether cost or side effects
  are covered by the user's request. Treat explicit authorization for a named
  operation and arguments as approval; ask only when material impact or scope is
  unclear. Tool listing is not tool invocation.
- Verify the actual HTTP and application/protocol result. HTTP 200 alone does
  not prove model completion or successful tool execution. Do not retry an
  operation that may have side effects until its outcome is known.

This is a consumer workflow: do not create or change gateways, assets, policies,
roles, keys or backend connections. Do not bypass gateway checks with provider
URLs or broader credentials. Finish with the endpoint/operation used, what was
actually verified, and the precise missing detail or owner action, if any.
