# Authenticate to the runtime

Use this reference for an actual connection/integration, not to acquire
credentials for discovery-only work. Keep live-use approval separate from
credential setup. Management reads, if needed, follow [connection](connection.md).

Management, runtime, and backend credentials are different. An ARM token is
not a gateway runtime token. A gateway's managed identity authenticating to an
upstream is not the application's identity or credential.

For model and MCP requests, send either the gateway API key or a Microsoft Entra
runtime token as `Authorization: Bearer <credential>`. Choose one method
explicitly and configure the client to send only that credential; do not fall
back between identities. If supplied connection instructions disagree, report
the contract as unverified and ask the asset owner rather than silently trying
other headers or credentials.

**Microsoft Entra ID:** prefer this for production and asset-scoped access.
The gateway runtime audience is `https://azure-api.net/aigateway`; this is an
Entra resource identifier, not the gateway runtime URL. For a signed-in Azure
CLI user, request a token for that resource:

```bash
AI_GATEWAY_TOKEN="$(az account get-access-token \
  --resource 'https://azure-api.net/aigateway' --query accessToken -o tsv)"
export AI_GATEWAY_TOKEN
```

Use the gateway's tenant and the intended caller. Custom delegated applications
request `https://azure-api.net/aigateway/Data.All` and need the `Data.All`
permission and consent; do not create registrations or grant consent in this
skill. Managed identities and app-only clients use
`https://azure-api.net/aigateway/.default` with an identity SDK. Use the
identity library to cache and refresh tokens rather than persisting static tokens.

The caller also needs **AI Gateway Models User**, **AI Gateway Tools User**,
or **AI Gateway User** at the appropriate workspace, model-alias, or MCP-server
scope. Management roles such as Contributor or AI Gateway Developer do not
imply invocation access, and invocation roles do not imply management reads.
Report missing consent/access to the administrator; never assign roles here.

Runtime-only users can follow these sign-in/credential instructions without
ARM access. Use an existing approved key binding or runtime identity; do not
list keys, call `listSecrets`, or request management access to establish runtime
authentication. A missing runtime credential needs a secure owner-provided
binding or approved sign-in, not a pasted secret.

**Existing gateway key:** prefer the application's already-authorized
`AI_GATEWAY_API_KEY` binding or secret store. Keys grant broad gateway runtime
access; explain that tradeoff. Only with management secret-read permission
and explicit approval, list key metadata at `/apiKeys` if retrieval is needed
and select the intended existing resource
name. Do not choose the first/master key automatically or invent key names.
Then POST `{}` to that selected `/apiKeys/{keyName}/listSecrets`, using the
child-resource API version from [connection](connection.md).

Capture the response directly in process memory, never terminal/chat output.
Read nonempty string `primaryKey`/`secondaryKey` fields at the top level or under
`properties`; tolerate `primaryValue`/`secondaryValue` variants. A `value` field
is a key only with an explicit `target` of `Primary` or `Secondary`. Preserve an
explicit primary/secondary choice; do not silently substitute another key.
Missing values or denied access are blockers, not permission to create/rotate
a key. Never enumerate provider or backend secrets.

## Store credentials safely

Use environment variables or the project's secret store. Generate only empty
credential placeholders in `.env.example`. Do not persist a runtime token.
Write a live API key to `.env` only with explicit approval; first ensure
`.env` is ignored, preserve existing entries, use BOM-free UTF-8 and restrictive
permissions, and warn that the file contains a live secret. Never put secrets
in committed examples, transcripts, screenshots, traces, or shell history.
