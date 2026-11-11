# Telemetry export and diagnosis

A gateway/default-workspace exporter owns signal endpoints, authentication,
claim attributes, and payload capture.
Destinations, DCRs, workspaces, registration, retention, and query access remain
externally owned; grants follow the [confirmed role workflow](../SKILL.md#operating-boundary).
The [capability inventory](activities-and-cli-coverage.md), not portal controls
or free-form JSON, records native applicability.

## Choose the task and inspect its exporter

Read the selected exporter and task dependencies. Diagnose missing data below,
not with a full gateway inventory.

```bash
az aigateway telemetry-exporter list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway telemetry-exporter show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" -o json
```

Select by name and purpose; the portal selects one destination. Inspect kind,
component link, signal URLs, auth mode/client ID, attributes, capture, and any
provisioning state. Exporter commands have no `--ids`; apply the main
workflow's name-selector guard.

Native reads mask secrets, including the whole headers map, and can omit
write-only fields. Compare `show/list` if needed; masks or omission are neither
proof of absent credentials nor values safe to replay.

Choose an existing **OTLP/HTTP Protobuf** destination. For a custom receiver,
obtain full signal URLs, supported auth/audience, access, and reachability.

For Application Insights, read `OTLPMetricsEndpoint`, `OTLPLogsEndpoint`,
`OTLPTracesEndpoint`, and `DataCollectionRuleResourceId` from the existing
component with authorized core CLI reads. The
[monitoring recipe](../../../labs/13-monitoring/README.md#let-the-gateway-publish)
uses **Monitoring Metrics Publisher** on that exact DCR for the selected
gateway identity's **principal object ID**. Check grants and assignment authority;
confirm that exact assignment before `az role assignment create` and verification,
or hand it to the owner. Missing OTLP enablement, resources, or registration
remains an owner prerequisite.

## Create an OTLP exporter

Use complete URLs including paths; the gateway does not append `/v1/...`.
Enable only needed signals: metrics (usage/cost), logs (requests), traces
(request/policy spans); retain at least one. Example `otlp.json`:

```json
{
  "metricsEndpoint": "https://collector.example.com/v1/metrics",
  "logsEndpoint": "https://collector.example.com/v1/logs",
  "tracesEndpoint": "https://collector.example.com/v1/traces",
  "credentials": {
    "managedIdentity": {"resource": "<receiver-token-audience>"}
  }
}
```

Replace URLs/audience; omit unneeded signals on creation.
`credentials.managedIdentity.clientId` selects an attached UAMI; omission
selects the enabled system identity. Alternatives are
`credentials.headers`, a **string-to-string** map in a protected file, or
deliberately unauthenticated export. Do not combine MI with an Authorization
header. [Identity selection](keys-and-identities.md) grants no ingestion access.

```bash
az aigateway telemetry-exporter create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" \
  --kind OpenTelemetry --open-telemetry @otlp.json --payload-capture false
```

For Application Insights-linked OTLP, also pass
`--application-insights @appinsights-link.json`, containing:

```json
{"resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Insights/components/<component>"}
```

Use Azure Monitor's actual OTLP endpoints and audience
(`https://monitor.azure.com` in the sourced recipe). The component link selects
the portal's query destination; it provisions nothing and grants no access.
Legacy `ApplicationInsights`/connection-string and singular `endpoint` help
examples are not current per-signal OTLP/dashboard recipes.

Use bounded `show/list` read-back before retrying uncertain writes.
Verify exporter ID, changed/preserved fields, and any provisioning state. No
`telemetry-exporter wait`; saved configuration does not prove ingestion.

## Edit endpoints, auth, claims, or capture

Use `telemetry-exporter update` with fresh state and only changed
`--open-telemetry`, `--application-insights`, `--telemetry`, or
`--payload-capture` fields. Native updates forward supplied objects; do not
reconstruct secret-bearing settings from redacted reads. For a kind change,
plan confirmed disable/reconfigure rather than assume in-place conversion.

For endpoint-only changes, omit credentials. Endpoint omission leaves a field
unrequested; explicit `null` requests disabling that signal. Retain one signal,
or all three for portal dashboard eligibility. Attribute `signals` below
selects claim attachment, not signal export.

When switching auth, clear the inactive branch: `credentials.headers: null`
for MI, `credentials.managedIdentity: null` for headers. Send the selected
branch's configuration. Disabling auth requires confirmation and both cleared;
never resend masks.

For attributes-only edits, merge desired rows with the existing array in
`telemetry.json`. This row illustrates shape, not complete membership:

```json
{
  "attributes": [
    {"source": {"kind": "claims", "value": "cost_center"}, "signals": ["logs", "traces"]}
  ]
}
```

```bash
az aigateway telemetry-exporter update --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" \
  --telemetry @telemetry.json
```

`attributes` replaces the array; leave auth/capture flags unrequested.
An empty array removes mappings. Select validated claims and at least one of
`logs`, `traces`, `metrics` per row. API-key callers have no Entra claims.
Review readership, PII, and metric cardinality rather than exporting broad
identity defaults.

Keep capture off unless authorized. `--payload-capture true` needs informed consent:
prompts/completions and tool input/output may be exported without built-in PII
redaction, increasing data volume and potential ingestion/retention costs.
Review readership/retention, use authorized synthetic traffic, and disable
capture when the investigation ends. Disabling it does not erase exported data.

No exporter ETag/conditional-write input is exposed. Avoid concurrent edits;
fresh reads and verification do not prevent races or prove write-only secrets.

## Disable

Confirm telemetry/dashboard loss before `telemetry-exporter delete`;
verify authoritative absence. Leave the external component, DCR, workspaces,
collected data, and shared grants intact.

## Diagnose without speculative remediation

Inspect the exporter fields above, then choose relevant read-only checks:

1. **Establish traffic.** Read the exact gateway; correlate the incident window,
   route, and supplied request/error evidence. If calls never reached the
   gateway, follow [networking](networking.md) first. For [routing failures](models-and-routing.md),
   follow `model-alias show` → selected `model show` → `model-provider show`.
   Check [MCP sources/auth](mcp.md) for tool failures, [policies](policies.md) for rejections.
2. **Check destination access.** Use `az aigateway identity show` for the
   scoped gateway; resolve the selected principal, audience, and grants.
   Recreated identities can leave stale grants. An unassigned identity can
   produce not-found even when the gateway exists. Check header validity
   through the credential owner, not secret retrieval/rotation.
3. **Separate ingress from export egress.** Use
   `az aigateway network show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION"`.
   Read `network private-endpoint-connection list` only if ingress is implicated.
   Inbound approval does not prove outbound delivery. Have the network/receiver
   owner verify DNS, TLS, routing, and firewall/private-access rules from the
   gateway's outbound path.
4. **Separate queries from ingestion.** Portal metrics query the linked Azure
   Monitor workspace's Prometheus endpoint with query credentials; logs/traces
   use Application Insights/Log Analytics queries. Check component/workspace
   linkage and operator query permissions or expired query credentials before
   changing export auth. Publisher access does not grant operator query access.
   Correlate authorized evidence by signal, gateway, and time window, allowing
   ingestion delay. No native metrics/trace/KQL query or inference/MCP test
   subgroup is established; queries or synthetic traffic need separate
   authorization. Without delivery evidence, report ingestion as unverified.

| Symptom | Evidence that narrows the cause |
| --- | --- |
| One signal missing | Full endpoint/path, receiver support, relevant traffic; another signal arriving does not validate this one |
| Dashboard unavailable | Requires linked OTLP and all signal endpoints; custom/legacy destinations are ineligible |
| Claims absent | Caller authentication/claim availability, retained mappings, selected signals; mapping is not claim issuance |
| 401/403 | Locate the boundary: ARM management, gateway caller, backend, or exporter destination; each uses different credentials/grants |
