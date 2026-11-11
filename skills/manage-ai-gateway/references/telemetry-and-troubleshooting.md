# Telemetry export and diagnosis

JSON schemas, updates, and diagnostics for `az aigateway telemetry-exporter` (uses `-g "$RG" --gateway-name "$GW" -n "$EXPORTER"`; no `--ids` or `wait`).

## Discover Application Insights OTLP endpoints and DCR

```bash
az resource show --ids "$APPINSIGHTS_ID" --api-version 2020-02-02-preview \
  --query '{dcr:properties.DataCollectionRuleResourceId,metrics:properties.OTLPMetricsEndpoint,logs:properties.OTLPLogsEndpoint,traces:properties.OTLPTracesEndpoint}' -o json
```

Grant the gateway's outbound managed identity **Monitoring Metrics Publisher** on `DataCollectionRuleResourceId` ([keys-and-identities.md](keys-and-identities.md)).

## `otlp.json` schema (`--open-telemetry @otlp.json`)

Include complete signal URLs with paths (for Azure Monitor OTLP, audience is `"https://monitor.azure.com"`; enable all three signals by default unless the user requests a subset):

```json
{
  "metricsEndpoint": "<OTLPMetricsEndpoint>",
  "logsEndpoint": "<OTLPLogsEndpoint>",
  "tracesEndpoint": "<OTLPTracesEndpoint>",
  "credentials": {
    "managedIdentity": {
      "resource": "https://monitor.azure.com",
      "clientId": "<optional-uami-client-id>"
    }
  }
}
```
- For header-authenticated custom OTLP collectors, use `"credentials": {"headers": {"Authorization": "Bearer <secret>"}}` (**string-to-string** map).

## Updates and claim attributes

- **Disable one signal**: Set that endpoint to `null` in `--open-telemetry` (at least one signal must remain active).
- **Switch authentication**: Set the unused credential branch to `null` (`"headers": null` or `"managedIdentity": null`). Never resend redacted header masks.
- **Export Entra token claims** (`--telemetry` replaces the `attributes` array—merge with existing entries from `show` first):
  ```bash
  az aigateway telemetry-exporter update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$EXPORTER" \
    --telemetry '{"attributes":[{"source":{"kind":"claims","value":"cost_center"},"signals":["logs","traces"]}]}'
  ```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing metrics/logs/traces | Verify signal URLs in `telemetry-exporter show`, gateway identity (`identity show`), and `Monitoring Metrics Publisher` role on the DCR. |
| Missing claim attributes | API-key callers have no Entra JWT claims; verify `attributes` mappings and target `signals`. |
| 401/403 on model/tool calls | Separate inbound caller auth (`AI Gateway Models/Tools User` or active `api-key`) from outbound backend auth (`Foundry User` or backend credential). |


