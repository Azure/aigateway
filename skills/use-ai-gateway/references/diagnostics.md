# Diagnose the request, not just the HTTP status

Use this reference for an unexpected model choice, missing or blocked tools,
latency, usage surprises, authentication failures or other runtime errors.
It supplements normal discovery/integration; do not query monitoring or replay
requests automatically for an ordinary catalog request.

## Runtime-only diagnosis remains useful

Gateway management access is not required to check a supplied endpoint,
callable name, request format, credential method or sanitized runtime error.
First inspect the local client configuration: HTTPS origin, `/default/`, exact
operation path, one correct SDK suffix, body model name, chosen runtime
credential binding, protocol and completion/error handling.

If the user cannot read ARM resources, skip alias/server/key/policy enumeration.
Continue with these checks, the returned code and behavior, safe correlation
metadata, and the published connection contract. State which routing, policy or
upstream explanations remain hypotheses. Do not request elevated management
access as a prerequisite or guess hidden configuration from a status alone.

A supplied monitoring link/resource can be used if the user separately has
query permission, even without gateway management permission. Without telemetry
access too, finish with a precise redacted client-side diagnosis or owner
handoff; do not pretend trace retrieval or configuration inspection occurred.

## 1. Capture the smallest useful incident

Record a redacted diagnostic envelope:

- UTC time/window, supplied runtime endpoint and gateway/workspace identity when
  known, callable alias or MCP server/tool, operation/protocol, and client/SDK version.
- Authentication method and intended caller context, never the token/key.
- HTTP status and parsed, sanitized provider/gateway or JSON-RPC error code.
  For streams, include whether the failure occurred after HTTP acceptance.
- Available safe request/correlation/trace identifiers and any Retry-After
  value. Use only allowlisted response metadata; do not dump all headers,
  raw exception objects or request/response bodies.
- MCP negotiated version and whether a session was established, without
  retaining a session credential. For model calls, retain any reported model
  identity separately from the requested alias.

An SDK request ID, a provider response ID and a distributed trace ID are not
interchangeable. Do not promise that every gateway returns a trace ID. If none
is available, use time, asset and authorized caller filters to locate an
existing trace. Do not collect prompts, tool arguments, JWTs, full user claims,
backend credentials or unredacted payloads merely for correlation.

Inspect HTTP, protocol and application outcomes separately. HTTP 200 can contain
an OpenAI Responses `response.failed`/`error` event, an Anthropic stream error,
a Chat Completions error payload, an MCP JSON-RPC error, or a tool result with
`isError: true`. A connection closing without the expected result is not proof
that the operation succeeded or never executed.

## 2. Establish the failed access/processing layer

| Layer | Appropriate identity and evidence |
| --- | --- |
| Management metadata | The caller's ARM read permissions on the selected resources; use Azure CLI/ARM authentication, not a runtime key. |
| Gateway runtime | The explicitly selected gateway key or Entra runtime token. Delegated users request `https://ai.gateway.azure.com/Data.All`; workload identities use resource `https://ai.gateway.azure.com` / scope `https://ai.gateway.azure.com/.default`. Check tenant, expiry, consent and runtime role/scope separately. |
| Gateway to backend | Existing configured backend key, managed identity or user connection/token exchange. Management access or the caller's gateway key does not establish upstream authorization. |
| Observability store | Independent read/query permission on the existing Azure Monitor workspace or custom destination. Gateway control-plane access does not automatically grant it. |

Keep the chosen credential identity fixed while diagnosing. A new key, broader
token, role grant or provider-direct call would change the security context
rather than explain the failing request. Do not carry out those changes.

Classify the failure using actual response/error and configuration evidence:

| Symptom | Evidence to inspect and safe next step |
| --- | --- |
| `unknown_model` or unsupported operation | Exact callable alias versus management/backend names; endpoint suffix and SDK joining; aliases and capability support. Do not "fix" a working alias by substituting a deployment. |
| 400 / input rejection | Protocol/schema, model-specific parameters, no eligible router model, condition/session expression errors, prohibited overrides, auto-selection text/state restrictions, and content-safety details. Not every 400 is a client serialization bug. |
| 401 | Selected runtime host/header, token audience/tenant/expiry or current key. Keep ARM, runtime and backend tokens separate. |
| 403 | Error code and stage: runtime role/scope, IP restrictions, blocked server/tool, cost budget, policy or backend denial. `LlmCostQuotaExceeded` is not fixed by granting an invocation role. |
| 404 | Correct management/root API version or runtime route, `/default/`, provider prefix, resource identity, session handling and duplicated/missing SDK suffixes. |
| 429 | Gateway policy versus backend quota, counter dimension and safe Retry-After. Only retry with bounded backoff when appropriate; do not rotate identity to evade limits. |
| Missing tools | Server allowlist/blocked state, per-backend namespace, actual paginated inventory, compatible MCP version, caller access and upstream connection. A block can deny invocation while leaving discovery visible. |
| Slow/empty reply, timeout, 5xx or partial stream | Correlate routing attempts, policy evaluation, provider latency and protocol completion. Determine whether any backend/tool action happened before considering a retry. |

Do not infer the layer from status alone. Use the smallest relevant permitted
configuration reads from the asset-selection reference. A client with no
management permission can still use its supplied runtime contract and client
evidence; request only the missing owner confirmation.

## 3. Inspect existing traces when authorized

Traces can explain which backend served an alias, which candidates were
excluded/retried, what policy stage rejected a request, or whether a tool
backend was attempted before a result was withheld. They do not grant access
or guarantee that every span, field or request has been retained.

### Find the available destination

Use an owner-provided approved monitoring link or destination identity when
available. Exporter discovery below is optional; a user who cannot read gateway
metadata may still have separate read access to that known observability store.
If neither a permitted lookup nor supplied destination is available, retain
client evidence and hand off the missing destination/correlation information.

1. If permitted, GET
   `/workspaces/default/telemetryExporters` below the selected gateway using
   the child-resource API version from the main skill. Project only exporter
   kind, linked `applicationInsights.resourceId`, configured signal endpoints,
   and payload-capture state. Do not display connection strings, credentials,
   headers or managed-identity secrets.
2. Establish whether the traces/logs signal is configured and whether the
   current caller can query that destination. Publishing and querying are
   separate permissions. Do not enable signals, create exporters, grant roles,
   or request a more privileged credential as a debugging shortcut.
3. For an Application Insights-linked exporter, use the portal's
   **Monitoring > Traces** and a narrow time range, gateway/workspace, asset and
   available caller/request filters. Open the request details.
4. For a custom OTLP destination, use that existing platform's authorized
   query/viewer and schema. The gateway portal does not query arbitrary custom
   collectors. Do not assume Azure table names there or reconfigure its export.

Request/response payload capture is off by default and has no built-in PII
redaction. Do not enable it or fetch captured bodies as the first diagnostic
step. Even existing traces can contain sensitive URLs, claims, policy data or
payloads: project only necessary non-secret metadata and sanitize before sharing.

### Optional read-only Azure Monitor query

When the user authorizes programmatic inspection and the current identity has
access, follow the existing configured resource links:

- Read the linked or explicitly supplied authorized Application Insights component using ARM API
  `2020-02-02`; its `properties.WorkspaceResourceId` identifies the Log
  Analytics workspace for request spans/logs. Do not confuse this with an
  `AzureMonitorWorkspaceResourceId` used for Prometheus metrics.
- The portal queries that Log Analytics ARM resource's
  `/query?api-version=2017-10-01` with POST body `{"query": "<KQL>"}`.
  This is a read-only query action, not an inference call or configuration
  write. Use existing ARM authentication and independently authorized query
  scope; a gateway key cannot query telemetry.
- Validate the linked resource, time window and trace ID before constructing
  a query. Use escaped literals, bounded rows and projections. Do not paste
  arbitrary user text into KQL or search all tenant traffic.

For the portal's current Azure OTel schema, this is a trace-metadata template,
not a universal query for every destination:

```kusto
OTelSpans
| where TimeGenerated between (datetime(<utc-start>) .. datetime(<utc-end>))
| where TraceId == "<validated-trace-id>"
| project TimeGenerated, TraceId, SpanId, ParentSpanId, Name, Kind,
    DurationMs, StatusCode, ResultCode,
    Workspace=tostring(Attributes["azure.ai_gateway.workspace"]),
    Alias=tostring(Attributes["azure.ai_gateway.alias.name"]),
    RequestedModel=tostring(Attributes["gen_ai.request.model"]),
    ResolvedModel=tostring(Attributes["azure.ai_gateway.resolved_model.name"]),
    RespondingModel=tostring(Attributes["gen_ai.response.model"]),
    Tool=tostring(Attributes["gen_ai.tool.name"]),
    PolicyType=tostring(Attributes["azure.apim.policy.type"]),
    ErrorType=tostring(Attributes["error.type"]),
    RoutingAttempt=tostring(Attributes["azure.ai_gateway.routing.attempt"])
| order by TimeGenerated asc
| take 200
```

Replace placeholders only after validating their types. Confirm attribution
to the intended gateway/workspace/asset using available resource and span
metadata, especially when a workspace is shared. Report truncation/partial
results explicitly; request only the next necessary bounded slice.

For related logs, `OTelLogs` uses `TraceId`, `SpanId`, `TimeGenerated`,
`SeverityText`, `Body` and `Attributes`. Filter to the same trace/time slice;
start with severity and selected diagnostic attributes, not raw `Body` or all
attributes. A destination/table/schema error is not an empty successful trace.
Do not invent a `/traces` API on the gateway runtime.

### Read the trace as an execution tree

| Evidence | Interpretation and limits |
| --- | --- |
| `TraceId` | Correlates spans/logs for a trace; preserve other request IDs separately. |
| `SpanId`, `ParentSpanId` | Establish parent/child relationships. Reconstruct the tree instead of assuming time order alone identifies the failed stage. |
| Timestamp, `DurationMs`, span `Kind` | Separate gateway request, policy/selection work and backend attempts. Parallel child durations must not simply be summed into end-to-end latency. |
| `StatusCode`, `ResultCode`, HTTP/error/RPC attributes | Span status can be Error even with HTTP 200. Preserve protocol/tool failure evidence, not just transport status. |
| Alias/requested/resolved/responding-model attributes | Distinguish the published contract, chosen registration and provider-reported identity. If resolved-backend fields are absent, do not fill them from the alias or a guessed provider. |
| Routing attributes | `azure.ai_gateway.routing.backend`, `.backend_url`, `.attempt`, `.priority`, `.weight`, `.exclusion.reason`, `.failure.type`, `.failure.provider_code`, `.affinity.kind`, `.affinity.hit` can explain selection and retries where emitted. Sanitize URLs before sharing. |
| Policy attributes | `azure.apim.policy.type` and available policy metadata identify enforcement stages; correlate them with exact host/scope configuration where possible, not a global policy name alone. |
| Tool attributes | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `azure.ai_gateway.mcp.tool_server.name`, `rpc.response.status_code` and `azure.ai_gateway.tool.error.type` identify tool operations/failures where emitted. |

The inference log event is
`azure.ai_gateway.client.inference.operation.details`; the tool invocation
event is `azure.ai_gateway.client.tool.invocation.details`. Logs can enrich
the span they reference, not replace missing evidence with a success claim.
Fields vary with operation, backend support, export mapping and capture limits.

Compare configured candidate routes with observed attempts and outcome:
pre-dispatch denial, attempted backend failure, partial federation, or successful
execution followed by post-processing rejection are different diagnoses.
An observed tool attempt is not automatically proof of completed side effects;
missing/withheld output is not proof of no side effects either.

## 4. Close the evidence loop

Explain the observed failure boundary, the supporting evidence, confidence
and any remaining unknown. Recommend the smallest client fix consistent with
the chosen asset contract. Separate client fixes from owner actions such as
changing filters/policies, granting access or correcting backend connectivity.
Do not carry out the latter through this skill.

When no trace is found, check the selected destination, time range, ingestion
delay, retention/sampling/export gaps and query permission. Trace absence does
not prove that no request or tool execution occurred. Do not turn on payload
logging or repeatedly replay a potentially side-effecting call to compensate.

Provide a concise escalation packet if blocked: runtime endpoint, gateway/workspace
identity when known, asset and
operation, UTC window, safe correlation IDs, auth method, sanitized error/stage,
relevant configured constraints, permitted read coverage, and the precise
missing read or owner decision. Keep keys, tokens, payloads and private tool
results out of the packet.
