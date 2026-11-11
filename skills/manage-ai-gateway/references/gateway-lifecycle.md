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

## Tag updates

`--tags` replaces the entire tag object. Merge existing tags before updating:

```bash
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUB" --query tags -o json > tags.json
# Merge requested changes into tags.json, then:
az aigateway update --ids "$GATEWAY_ID" --subscription "$SUB" --tags @tags.json
```

## Soft-delete purge

`az aigateway delete` removes the active gateway and leaves a recoverable APIM soft-delete record. Purge only when permanent deletion is explicitly requested:

```bash
az apim deletedservice purge --subscription "$SUB" --service-name "$GW" --location "$LOCATION"
```


