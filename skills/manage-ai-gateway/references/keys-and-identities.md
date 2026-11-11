# Caller authentication and outbound gateway identity

RBAC role assignments, managed identity identifier rules, and API key rotation/secret handling.

## Managed identity identifiers

| Identifier | Where to use it |
| --- | --- |
| UAMI ARM `id` | `az aigateway identity assign/remove --user-assigned "$UAMI_RESOURCE_ID"` |
| UAMI `clientId` | `managedIdentity.clientId` in provider, MCP, hook, or exporter JSON (omit `clientId` to select the system-assigned identity) |
| System or UAMI `principalId` | `az role assignment list/create --assignee-object-id "$PRINCIPAL_ID"` |

## Grant caller or destination access

| Direction | Role name / ID | Scope |
| --- | --- | --- |
| Inbound caller → models | `AI Gateway Models User` | Model alias ID or gateway/workspace ID |
| Inbound caller → tools | `AI Gateway Tools User` | MCP ToolServer ID or gateway/workspace ID |
| Inbound caller → models + tools | `AI Gateway User` | Gateway or workspace ID |
| Outbound gateway MI → Foundry | `Foundry User` (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) | Foundry account ARM ID |
| Outbound gateway MI → App Insights OTLP | `Monitoring Metrics Publisher` | Data Collection Rule (DCR) ARM ID |

Check existing assignments first, then confirm `PRINCIPAL_ID`, `ROLE`, and `SCOPE` with the user before creating the grant:

```bash
az role assignment list --subscription "$TARGET_SUB" \
  --assignee-object-id "$PRINCIPAL_ID" --scope "$SCOPE" \
  --include-inherited --fill-principal-name false -o json

az role assignment create --subscription "$TARGET_SUB" \
  --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "$ROLE" --scope "$SCOPE" -o json
```
(`PRINCIPAL_TYPE`: `ServicePrincipal` for managed identities/apps, `User`, or `Group`.)

## API key secrets, expiry, and staged rotation

`primaryKey` and `secondaryKey` on an API key share state, expiration, and caller identity for rate/cost/token counters.

```bash
# Set expiration (ISO 8601) or reactivate
az aigateway api-key update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --expiration-date "2027-01-01T00:00:00Z"
az aigateway api-key update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --state active

# Retrieve secret value (only when explicitly authorized; never echo in logs/output)
az aigateway api-key list-secrets --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --query secondaryKey -o tsv
```

- **Zero-downtime rotation**:
  1. Confirm which slot (`primary` or `secondary`) is unused, then regenerate only that slot:
     ```bash
     az aigateway api-key regenerate --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$KEY_NAME" --key-type secondary
     ```
  2. Cut clients over to the new key and confirm before regenerating the other slot.


