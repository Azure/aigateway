---
name: use-ai-gateway
description: Choose, consume and troubleshoot existing Azure AI Gateway models and MCP tools. Integrate a known runtime endpoint without ARM access, discover permitted assets with native CLI reads, or scaffold a least-privilege agent. Never provision gateway resources, change policies or grant access.
license: MIT
metadata:
  author: Microsoft
  version: "3.1.0"
---

# Use an Azure AI Gateway

Help developers use an existing gateway through `/aigateway:discover`,
`/aigateway:build`, or this skill. Start with the supplied connection contract
and the user's task, not a gateway audit. Gateway changes belong to
[manage-ai-gateway](../manage-ai-gateway/SKILL.md); APIM migration belongs to
[migrate-ai-gateway](../migrate-ai-gateway/SKILL.md).

## Choose the shortest path

| User intent | Required cues and acceptance | Read when needed |
| --- | --- | --- |
| Integrate a known model endpoint | Exact URL, callable name, operation, existing secure credential binding; client produces the operation's expected result | [Runtime integration](references/runtime-integration.md), Path A |
| Discover suitable models/tools | Authorized metadata or owner-supplied connection details; finite shortlist, tradeoff and unknowns, no code or new credentials | [Runtime integration](references/runtime-integration.md), Part 1 |
| Connect a known MCP server | Published gateway URL, compatible protocol and existing credential; paginated descriptors with exact tool names, not tool execution | [Runtime integration](references/runtime-integration.md), Path B |
| Scaffold an agent | Explicit project/language, conversational model and selected tools; complete project with isolation and permission decisions | [Runtime integration](references/runtime-integration.md), Path C |
| Explain routing, policy, cost or tool exposure | Relevant supplied or permitted metadata; configured behavior distinguished from observed request behavior | [Asset selection](references/asset-selection.md) |
| Diagnose 401/403/429, wrong model, missing tools or latency | Sanitized error and client contract first; narrow existing traces only if separately authorized | [Diagnostics](references/diagnostics.md) |

Explicit choices do not need to be selected again. Ask only for missing details
that change the result. An endpoint host alone cannot reveal a model/server
catalog; request its published contract instead of guessing names or paths.

## Access and scope

**Runtime-only:** a complete endpoint/name/protocol/auth contract needs no ARM
ID, `az login`, CLI installation/version check, subscription inventory, provider
enrichment, key listing or release lookup. Validate the local request and use
the existing approved secret binding. An explicitly requested Entra sign-in
is separate from management discovery. Missing management/telemetry access
limits explanations, not otherwise-authorized client integration.

**Management-enriched:** prefer task-scoped `az aigateway show`,
`model-alias list/show`, `model list/show`, `mcp list/show`, and relevant policy
or exporter reads. Use explicit subscription and gateway selectors; validate
returned identity/family and default workspace. Inspect installed task-specific
help only for commands needed now.
If a gateway-root read is needed, prefer its fully typed
`Microsoft.ApiManagement/aigateways` ID with `show --ids` where help exposes it;
do not replace that binding with a name-only read or re-anchor a foreign ID.
Use scoped ARM GETs only for fields not
exposed by the CLI or a verified legacy contract, as described in the runtime
reference. Failed reads and incomplete pagination are unknown, not empty.
Do not retry under another identity.

This skill is read-only **against gateway configuration**, not against the
user's requested application files. Discovery stops at a selection brief.
Build integrates into the existing project, or scaffolds only when requested.
Secret retrieval, runtime invocation, tool side effects and telemetry queries
need their own appropriate authorization; a metadata read grants none of them.

## Preserve the callable contract

- Use `properties.aliasName` for a published alias, not its backend deployment
  or ARM ID. Resolve `supportedEndpoints` for the chosen operation; join
  `<origin>/default/models<supportedEndpoint>` once, preserving the provider
  prefix. Keep an explicitly supplied, verified direct-model contract.
- Published examples differ: the older CLI quickstart uses `Api-Key` and
  `properties.deployment.modelName`; the hosted quickstart uses
  `Authorization: Bearer` and aliases. Resolve the **selected gateway's**
  contract from its published connection details, metadata and applicable
  documentation, not CLI version alone. Missing alias permission does not
  prove legacy support. Never automatically switch headers, credentials or
  identities after an error. The runtime reference explains compatibility.
- Keep gateway runtime credentials separate from ARM and backend credentials.
  Prefer existing Entra runtime access for scoped production use. Existing keys
  are gateway-wide; never select the first/master key or create/rotate one here.
  Name secret bindings, never values; redaction markers are not credentials.
- Use the gateway's MCP endpoint, never an upstream `endpoints[].mcp.url`.
  Follow the verified protocol's handshake/session/pagination rules. Validate
  JSON-RPC errors and tool `isError` even on HTTP 200. `tools/list` is discovery;
  `tools/call` needs authorization for the exact operation and arguments.
- Keep routing and governance server-side. Do not bypass an alias/provider,
  change policy/networking, broaden roles, auto-connect backends, expose
  unselected tools or generate approval-all permission callbacks.

## Integrate and verify

Use the existing language, package manager and secret-store pattern. Read only
the selected runtime recipe; SDK setup is unnecessary for an endpoint question.
Use exact-URL HTTP when the SDK cannot represent the verified path or header.
Keep shared keys on trusted backends, never in browser bundles or committed
config. Generate empty placeholders only; live secret files need explicit
approval, ignore rules and restrictive permissions.

Validate URL/body/protocol locally before a live check. Confirm the destination,
synthetic input, credential identity, cost and any tool side effects. Use one
bounded model request with timeout and no automatic retries, or authorized
read-only MCP listing. Check the operation's actual output: nonempty chat
choices/text, completed Responses output, Messages content, or embeddings
vectors; streams must complete without error. A tool result, empty reply,
timeout, 429 or HTTP-success error envelope is not success.

Finish with the selected contract/tradeoff, integrated files and observed
outcome, or the concrete blocker. Metadata persistence does not prove runtime
behavior, policy enforcement, backend authorization or telemetry ingestion.
