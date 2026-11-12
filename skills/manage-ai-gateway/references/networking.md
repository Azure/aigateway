# Gateway networking and private connections

Subnet requirements and private endpoint connection subcommands for `az aigateway network`.

## Outbound VNet subnet requirements

- Same subscription and region as the gateway.
- Dedicated subnet `/27` or larger (`/24` recommended), delegated to `Microsoft.App/environments`.
- Outbound TCP 443 allowed to `Storage` and `AzureKeyVault`; do not place private endpoints inside the delegated subnet.
- `network show` returns `properties.backend.subnet.id` under `virtualNetworkConfiguration.subnetResourceId`.
- If `--no-wait` is passed to `network update`, poll with `az aigateway network wait --ids "$GATEWAY_ID" --subscription "$SUB" --updated --timeout 600 --interval 15`.

## Gateway-side private endpoint connections

Private endpoints is in preview and it requires to request access to this feature. To request access, see [Request access to private endpoints](https://aka.ms/aigateway/privateEndpoints).

Targets `$GATEWAY_ID/privateEndpointConnections/<connection-name>` (not the backing `Microsoft.Network/privateEndpoints` resource):

```bash
az aigateway network private-endpoint-connection show --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" -o json
az aigateway network private-endpoint-connection approve --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" --description "$REASON"
az aigateway network private-endpoint-connection reject --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" --description "$REASON"
az aigateway network private-endpoint-connection delete --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" --yes
az aigateway network private-endpoint-connection wait --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$PEC_NAME" --updated --timeout 600 --interval 15
```


