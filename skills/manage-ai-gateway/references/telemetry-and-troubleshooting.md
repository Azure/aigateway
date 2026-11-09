# Telemetry configuration and operational diagnosis

Apply [the skill's scope, authorization, and secret rules](../SKILL.md).
Exporter configuration is gateway-owned; destination resources, DCRs,
workspaces, publisher role assignments, and provider registration are not.

## Inspect exporters and select a destination

```bash
az aigateway telemetry-exporter list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway telemetry-exporter show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" -o json
```

Resolve the selected exporter's kind, destination, enabled signals,
authentication, attributes, and payload capture. Do not silently select the
first exporter or create an additional exporter to evade a service limit.
The portal currently configures one destination. Name-only native writes
need the typed-parent/collision guard; current exporter commands do not all
expose exact `--ids`.

Choose an existing destination and its actual **OTLP/HTTP Protobuf** signal
URLs. Each is a full URL including the destination's required path; the
gateway does not append `/v1/...`. At least one signal is required.
Application Insights portal dashboards require the linked component and
all three signals. Its connection string alone is not the current OTLP
setup.

For existing Application Insights, obtain authorized read-only evidence of
its OTLP endpoints/DCR and pre-existing publisher access. Missing OTLP
enablement, a DCR role grant, resource creation, or registration is an
external owner prerequisite. Do not reproduce the portal's automatic
resource/role provisioning side effects.

## Create an OTLP exporter

Example `otlp.json` for a preconfigured custom receiver:

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

Use the selected destination's exact URLs/audience. An optional
`credentials.managedIdentity.clientId` selects an existing attached UAMI;
otherwise system identity is used. Alternatively use
`credentials.headers` as a **string-to-string** map in a protected file,
or intentionally unauthenticated configuration. Do not combine MI with an
Authorization header. Backend access must already exist.

```bash
az aigateway telemetry-exporter create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$EXPORTER" \
  --kind OpenTelemetry --open-telemetry @otlp.json --payload-capture false
```

For current Application Insights-linked OTLP, also pass
`--application-insights @appinsights-link.json`, containing:

```json
{"resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Insights/components/<component>"}
```

The OTLP endpoints and managed identity audience must be the existing Azure
Monitor destination's actual values (normally `https://monitor.azure.com`),
with publisher access already granted. Do not assume a shorter legacy
`--kind ApplicationInsights --application-insights` connection-string recipe
establishes current portal dashboard compatibility. Legacy-kind operations
remain visible but require their own explicit existing contract/intent.

Verify via exporter `list/show`: kind, destination link, URLs, credential
mode/client ID, retained attributes, and capture state. Direct reads can
omit sensitive/write-only fields; use authorized list metadata when needed,
never automatic credential enumeration.

## Edit endpoints, auth, claims, or capture

Read fresh state, then use `telemetry-exporter update` with only the intended
`--open-telemetry`, `--application-insights`, `--telemetry`, or
`--payload-capture` fields. Preserve credentials and unrequested settings;
do not reconstruct them from redacted output or replace the kind implicitly.
Current exporter kind switches should be treated as confirmed
disable/reconfigure, not assumed in-place conversion.

Endpoint-only partial object:

```json
{"metricsEndpoint": "https://collector.example.com/v1/metrics", "logsEndpoint": null}
```

`null` explicitly disables that signal under the reviewed contract.
Omission leaves it unrequested. Check that the resulting exporter still
has at least one enabled signal; disabling a required Application Insights
signal makes the built-in dashboard unavailable.

When switching auth modes, explicitly clear the inactive credential branch.
For example, MI selection:

```json
{
  "credentials": {
    "headers": null,
    "managedIdentity": {"resource": "<receiver-token-audience>"}
  }
}
```

For custom headers set `managedIdentity: null`; intentionally disabling auth
requires confirmation and both branches cleared. Do not resend masked values.
These are access-sensitive changes and do not grant destination permissions.

Claim attributes use `--telemetry @telemetry.json`:

```json
{
  "attributes": [
    {"source": {"kind": "claims", "value": "cost_center"}, "signals": ["logs", "traces"]}
  ]
}
```

Merge the desired claim rows with retained mappings before replacing the
array; an empty `attributes` array removes mappings. Use exact validated
token claim names and explicitly selected `logs`, `traces`, and/or `metrics`.
Mappings do not issue claims, and API-key callers have no Entra claims.
Review destination readership and cardinality before adding metric dimensions.
Do not enable broad identity/PII exports by default.

Capture defaults off. Enabling `--payload-capture true` requires explicit
informed authorization: prompts/completions and tool input/output may be
exported, with no built-in PII redaction. Review readership/retention, use
synthetic test traffic, and disable capture when the authorized investigation
ends. Turning capture off does not erase previously exported data.

Exporter updates do not provide a blanket atomic concurrency guarantee.
Avoid concurrent editing; verify both changed and preserved settings.
There is **no `telemetry-exporter wait`** in the reviewed installed CLI,
despite the reference table. Use bounded `show/list` reconciliation, not a
fabricated wait command.

## Disable

After confirming loss of future telemetry and its dashboard impact, use
`telemetry-exporter delete` with the selected name/scope. Verify authoritative
absence using exporter reads. Do not delete the Application Insights
component, DCR, workspaces, collected data, or shared access grants.

## Diagnose without speculative remediation

| Question or symptom | Smallest useful native evidence and next owner action |
| --- | --- |
| Resource did not provision, command timed out | Exact root/child `show`, matching advertised `wait`, terminal state; keep unknown outcome distinct from failure |
| Model unreachable or wrong protocol | Provider/model metadata, endpoints, deployment identity, alias routing and policy arrays; verify existing backend access separately |
| Wrong backend or traffic split | Alias callable name, complete target pool, priorities/weights, compatible operations; configuration is not observed runtime selection |
| MCP auth/empty tools | Registration/source URL, transport, versions, supported credential metadata; saved OAuth link is not connection proof |
| 401/403 | Distinguish management authentication/RBAC from gateway caller key/Entra access and backend outbound credentials; do not retrieve/rotate keys reflexively |
| 404 | Verify exact resource family, subscription, child names, alias/callable route, and authoritative deletion evidence |
| 429 | Inspect configured token/request/cost limits; backend quota is a different possibility, not proven by a policy read |
| Private access fails | Public setting, outbound subnet and existing private connection state; external DNS/reachability remains an owner check |
| Telemetry absent | Enabled signal URLs, linked destination, auth mode/identity, prerequisite publisher access, ingestion delay; saved exporter is not delivery proof |
| Dashboard empty but export is configured | Custom destinations are not queried by the portal; Application Insights needs all signals plus viewer query permissions |
| Permissions/discovery failed | Report the precise collection/operation and missing permission; retain successful partial evidence rather than showing zero assets |

No native gateway metric/trace/KQL query or inference/MCP runtime test
subgroup was established. Do not invent one, run tools automatically, or
claim policy enforcement/ingestion from management reads. Identify the
appropriate portal/configured-destination verification and its separate
authorization/cost implications. Export access for the gateway and query
access for the operator are distinct.
