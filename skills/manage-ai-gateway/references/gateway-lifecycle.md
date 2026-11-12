# Gateway lifecycle

Supplementary details for `az aigateway` root operations (`create`, `show`, `list`, `update`, `delete`, `wait`).

## Async waits (`--no-wait`)

When `--no-wait` is passed to `create`, `update`, or `delete`, poll the exact resource ID:

```bash
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUB" --created --timeout 1800 --interval 20
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUB" --updated --timeout 1800 --interval 20
az aigateway wait --ids "$GATEWAY_ID" --subscription "$SUB" --deleted --timeout 1800 --interval 20
```

- `wait --created` / `--updated` completes when `properties.provisioningState` reaches `Active` or `Succeeded`.
