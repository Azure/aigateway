# Authenticate to the gateway runtime

Model and MCP requests use one gateway credential in
`Authorization: Bearer <credential>`. Use the application's existing approved
binding; do not send an ARM token or provider credential.

## Microsoft Entra ID

The runtime resource identifier is `https://ai.gateway.azure.com`. For an
existing Azure CLI sign-in in the intended tenant:

```bash
AI_GATEWAY_TOKEN="$(az account get-access-token \
  --resource 'https://ai.gateway.azure.com' --query accessToken -o tsv)"
export AI_GATEWAY_TOKEN
```

Pass the token as a bearer credential and let the identity library refresh
tokens in long-running applications. Delegated applications request
`https://ai.gateway.azure.com/Data.All`; workload identities request
`https://ai.gateway.azure.com/.default`. The caller also needs **AI Gateway
Models User**, **AI Gateway Tools User**, or **AI Gateway User** at the
applicable workspace or asset scope. Report missing consent or access to the
owner; do not grant roles here.

## Existing gateway key

Use the application's existing `AI_GATEWAY_API_KEY` secret binding when
approved. Keys are runtime credentials; do not print, retrieve, create, rotate
or paste one into chat as part of endpoint discovery. If no approved binding
exists, ask the owner to provision one through the approved secret-delivery
process.

Keep tokens and keys out of source, committed examples, shell history, URLs,
browser bundles and logs. An `.env.example` may name an empty placeholder only.
