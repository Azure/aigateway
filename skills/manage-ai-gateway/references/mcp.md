# MCP ToolServers reference

Source schemas, authentication formats, full-array endpoint edits, and OAuth flows for `az aigateway mcp`.

## Source and credential JSON schemas

Each element in `--endpoints @endpoints.json` (or passed to `mcp source add` via `--mcp` / `--open-api` and `--credentials`) uses:

| `kind` | Source settings property |
| --- | --- |
| `mcp` | `"mcp": {"url": "https://example.com/mcp", "transport": "streamableHttp"}` (or `"sse"`) |
| `openApi` (URL) | `"openApi": {"specSource": {"type": "url", "url": "https://example.com/openapi.json"}}` |
| `openApi` (inline) | `"openApi": {"specSource": {"type": "inline", "contentBase64": "<base64-utf8-openapi-json>"}}` (convert YAML to JSON and resolve `servers[].url` to absolute HTTP/HTTPS before encoding) |

| `credentials.type` | `credentials` object |
| --- | --- |
| `none` | `{"type": "none"}` |
| `header` | `{"type": "header", "headers": {"X-Api-Key": ["<secret>"]}}` (values must be **string arrays**) |
| `managedIdentity` | `{"type": "managedIdentity", "managedIdentity": {"resource": "<audience>", "clientId": "<optional-uami-client-id>"}}` |
| `oauth2` | `{"type": "oauth2", "oauth2": {"grantType": "authorizationCode", "authorizationUrl": "...", "tokenUrl": "...", "clientId": "...", "scopes": ["..."], "clientSecret": "<optional>"}}` |

## Editing existing sources (`mcp update --endpoints`)

There is no `mcp source update`. To modify an existing source's URL, transport, `required` flag, or credentials:

1. Read `az aigateway mcp show --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$MCP_NAME" -o json`.
2. Build the **complete `endpoints` array** in `endpoints-edit.json` with each kept source's `kind`, `namespace`, `required`, and `mcp`/`openApi` settings.
3. Keep `namespace` values unchanged and **omit unchanged `credentials` and `contentBase64`**—the CLI internally invokes `listSecrets` and merges stored secrets for matching namespaces. Never include redacted markers, server-generated `id`, or OAuth `status`.
4. Run `az aigateway mcp update --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$MCP_NAME" --endpoints @endpoints-edit.json`.

For display-name, version, or `--policies` updates, omit `--endpoints` so `listSecrets` is not called.

## Backend OAuth (`oauth2`)

- **Inspect OAuth status**:
  ```bash
  az aigateway mcp show --subscription "$SUB" -g "$RG" --gateway-name "$GW" -n "$MCP_NAME" \
    --query 'properties.endpoints[].{id:id,namespace:namespace,auth:credentials.type,status:credentials.oauth2.status,expires:credentials.oauth2.tokenExpiresUtc}' -o json
  ```
- **Initiate authorization flow** (only when requested; pass the server-generated endpoint `id` from `mcp show`, not `namespace`):
  ```bash
  az aigateway mcp authorize --subscription "$SUB" -g "$RG" --gateway-name "$GW" \
    --tool-server-name "$MCP_NAME" --endpoint-id "$ENDPOINT_ID" -o json
  ```

## Filter and block tools

Use property `allowList` to control which tools are available through the federation. If endpoints have a namespace, tools should be `<namespace>_<tool_name>`. Only tools in `allowList` are returned in `tools/list`.

Use property `blocked` to temporarily block tool execution. Tools are returned in `tools/list`.
