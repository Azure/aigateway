# Model aliases, registrations, and routing

Low-level JSON schemas, update semantics, alias pool routing, and deletion order for `model-provider`, `model`, and `model-alias`.

## Low-level provider JSON schemas

Use `--kind Foundry --foundry @foundry.json` when selecting a user-assigned managed identity, API key authentication, or managing RBAC separately from `--foundry-resource-id`:

```json
{
  "endpoint": "https://<account>.openai.azure.com/",
  "resourceIds": ["/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"],
  "authentication": {
    "kind": "ManagedIdentity",
    "managedIdentity": {
      "resource": "https://cognitiveservices.azure.com/",
      "clientId": "<optional-uami-client-id>"
    }
  }
}
```
- Omit `clientId` to use the gateway's system-assigned identity, or set `"authentication": {"kind": "ApiKey", "apiKey": {"headerName": "api-key", "value": "<secret>"}}`.
- For `--kind Custom --custom @custom.json`, omit `resourceIds` and use `ApiKey` authentication (`Custom` providers do not support `ManagedIdentity` or `model-provider sync`).
- `model-provider update --foundry` / `--custom` merges supplied fields into existing configuration without overwriting omitted credentials.

## Low-level model JSON schema and updates

`deployment.json` (`resourceId` and `modelVersion` are optional for `Custom` providers):

```json
{
  "modelName": "<backend-deployment-or-model-name>",
  "modelVersion": "<optional-version>",
  "resourceId": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/deployments/<deployment>"
}
```

- `model create` takes `--deployment-config @deployment.json`; `model update` takes `--deployment @deployment.json` (replaces the full deployment object).
- `--supported-endpoints` accepts space-separated paths (for example `/openai/v1/chat/completions /openai/v1/responses` or `/anthropic/v1/messages`) and replaces the endpoint list on update.

## Alias pool

Each `--backend-model` target must be a gateway model registration ARM ID (`$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$MODEL`), never a Foundry deployment ID.

| Routing pattern | Target configuration | Behavior |
| --- | --- | --- |
| Single target | `A: priority=0 weight=100` | All traffic routes to `A` |
| Weighted split (active-active / canary) | `A: priority=0 weight=75`, `B: priority=0 weight=25` | 3:1 traffic split across healthy models in priority `0` |
| Primary + fallback | `A: priority=0 weight=100`, `B: priority=1 weight=100` | `A` handles traffic; `B` serves only when priority `0` is unavailable |

- `priority`: integer `0–100` (lower number = higher precedence).
- `weight`: integer `1–100` (relative share within the same priority; does not need to sum to 100; `0` is invalid).
- Passing `--backend-model` (or `--backend-models @pool.json`) **replaces the entire target pool** (1–30 unique models). Read `model-alias show` first to preserve existing targets.

## Safe deletion order

1. Retarget or delete aliases referencing the model (`az aigateway model-alias update` or `delete`).
2. Delete the model registration (`az aigateway model delete --subscription "$SUB" -g "$RG" --gateway-name "$GW" --provider-name "$PROVIDER" -n "$MODEL" --yes`).
3. Delete the provider once it has no remaining models (`az aigateway model-provider delete --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PROVIDER" --yes`).


