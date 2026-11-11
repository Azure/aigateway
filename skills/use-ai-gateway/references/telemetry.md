# Inspect gateway OpenTelemetry in Application Insights

Traces can explain which backend served an alias, which candidates were
excluded/retried, what policy stage rejected a request, or whether a tool
backend was attempted before a result was withheld. They do not grant access
or guarantee that every span, field or request has been retained.

## Start with the question and incident

For a runtime failure, first capture the minimal redacted time, asset,
operation and error evidence from [diagnostics](diagnostics.md). For latency,
usage or routing analysis, establish the question and a narrow UTC window.
Reuse supplied safe correlation IDs; a request ID is not necessarily a trace ID.
Telemetry access is independent of gateway management and runtime permissions.

## Find the available destination

Use an owner-provided approved monitoring link or destination identity when
available. Exporter discovery below is optional; a user who cannot read gateway
metadata may still have separate read access to that known observability store.
If neither a permitted lookup nor supplied destination is available, retain
client evidence and hand off the missing destination/correlation information.

1. If permitted, GET
   `/workspaces/default/telemetryExporters` below the selected gateway using
   the child-resource API version from [connection](connection.md). Project only exporter
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

## Query existing Application Insights telemetry

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

OpenTelemetry defines signals, trace/span relationships and semantic attributes,
not a universal Azure storage schema. Confirm the destination's actual tables
and columns through its schema view or a read-only schema query, such as
`OTelSpans | getschema` when that table exists. Export mappings may differ;
do not assume classic Application Insights tables have OTel column names.
A missing table is a schema/destination question, not evidence of no traffic.

For the gateway portal's Azure OTel schema, this is a trace-metadata template
to adapt after checking the schema, not a universal query for every destination:

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

If there is no trace ID, first locate candidate traces using the validated UTC
window and known gateway/resource, workspace and asset metadata. For example,
after confirming the OTel schema and adding an available gateway/resource
scope predicate for a shared destination:

```kusto
OTelSpans
| where TimeGenerated between (datetime(<utc-start>) .. datetime(<utc-end>))
| where tostring(Attributes["azure.ai_gateway.workspace"]) == "<workspace>"
| where tostring(Attributes["azure.ai_gateway.alias.name"]) == "<alias>"
| summarize FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by TraceId
| order by FirstSeen desc
| take 20
```

For MCP, use the known server/tool attributes instead of an alias filter.
Do not run an unscoped search if available metadata cannot distinguish the
intended gateway's traffic; request an owner-provided correlation or scoped
view. Inspect the selected trace next rather than exporting all traffic.

For related logs, `OTelLogs` uses `TraceId`, `SpanId`, `TimeGenerated`,
`SeverityText`, `Body` and `Attributes`. Filter to the same trace/time slice;
start with severity and selected diagnostic attributes, not raw `Body` or all
attributes. A destination/table/schema error is not an empty successful trace.
Do not invent a `/traces` API on the gateway runtime.

## Read the trace as an execution tree

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

## Explain what the evidence establishes

Answer the user's question with the observed stage, relevant spans/attributes
and remaining uncertainty. For errors, use the layer-specific diagnosis and
owner handoff in [diagnostics](diagnostics.md). Treat query errors, partial
results and truncation explicitly rather than calling them an empty trace.
If no trace is found, check destination, time range, query permission,
ingestion delay, retention and sampling/export gaps. Absence of telemetry does
not prove absence of execution; do not enable payload capture or replay a
side-effecting request to compensate.
