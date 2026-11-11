# MCP ToolServers reference

Federate existing backends with native `az aigateway mcp` commands.
Scope, confirmations, grants and protected inputs follow the
[administrator workflow](../SKILL.md); versioned support evidence lives in the
[capability inventory](activities-and-cli-coverage.md).

## Choose the task

| Intended outcome | Native route and effect |
| --- | --- |
| Inspect or diagnose | [Read configuration](#inspect-a-server), then [identify runtime gaps](#identify-remaining-runtime-uncertainty) |
| Federate existing backends | [Create a ToolServer](#create-a-toolserver) with an endpoint array |
| Add/remove a backend | [Source add/remove](#add-or-remove-one-source); preserves siblings, implicitly reads secrets |
| Change metadata/versions | [Update supplied fields](#edit-a-server-or-existing-backend), not endpoints |
| Edit backend settings/authentication | [Replace endpoints](#edit-a-server-or-existing-backend); complete membership, implicit secret read |
| Configure governance | [Replace policies](#attach-or-configure-policies), not endpoints |
| Connect shared OAuth | [Inspect OAuth](#diagnose-backend-oauth-without-initiating-it), then authorize initiation |
| Restrict tools, suspend access or use caller delegation | Check [native limits](#product-controls-and-native-limits) first |
| Delete a registration | [Confirm and delete](#delete-a-toolserver); upstream services remain |

## Understand the effects

| Configuration owner | Settings and responsibility |
| --- | --- |
| ToolServer | `type: "mcp"`, `displayName`, `description`, protocol `versions`, source membership (`properties.endpoints`), and inline `policies` |
| Backend source | An endpoint-array entry: unique `namespace`, `kind`, `required`, `mcp` or `openApi` settings, and outbound `credentials` |
| External service | Actual operations, availability, application/connection configuration and source-side access; registration does not provision it |
| Published tool | Runtime discovery result, not an independent native ARM resource or policy host |

The ARM host is `$GATEWAY_ID/workspaces/default/toolServers/<server>`.
Clients use the gateway runtime URL plus
`/default/toolservers/<server>/mcp`, not the upstream URL. The gateway combines
backend tools for `tools/list` and routes `tools/call` to the supplying backend.

Use the ToolServer ARM name/ID to select a registration, source `namespace`
for add/remove, and the server-generated endpoint `id` for OAuth initiation.
Display names and discovered tool names are not management selectors.
The server's protocol-version list is separate from each backend's transport;
an OpenAPI backend still belongs to a server of type `mcp`.

A namespace prefixes exposed names as `<namespace>_<toolname>`. Changing it
changes client references and matching tool rules. Namespaces must be unique;
without one, tool names must already be unique across backends. The product
permits omitted namespaces, but native `source add` requires one.

`required` controls federation tool discovery: failure to retrieve a required
backend's tools fails the listing; an unavailable optional backend is skipped.
It does not provide tool-call failover or prove later calls will succeed.
Set it per backend: top-level `--failure-mode` is create-only, absent on native
read-back and therefore unverifiable through this surface.

### Product controls and native limits

These product controls and OAuth client credentials have no established
[native authoring path](activities-and-cli-coverage.md); portal controls and
free-form JSON do not establish one.

| Product control | Effect |
| --- | --- |
| `allowList` | Exact names or `*`/`?` patterns match final names, including namespaces, and control discovery and invocation; omitted allows all, empty exposes none. |
| `blocked` | Allowed tools remain discoverable but matching invocations are rejected; blocking wins over an allow match. |
| `accessState` | `blocked` suspends discovery and invocation without deleting configuration. |
| OAuth token exchange / Entra OBO | Uses the caller's delegated user permissions; gateway keys and app-only tokens cannot substitute. |
| Foundry Toolbox import | Disabled in the portal; no verified native source contract. |

Preserve configuration authored elsewhere; do not substitute deletion,
changed credentials or different policy semantics for these controls.

## Execute the smallest native change

### Inspect a server

Use the [resolved variables](../SKILL.md#prerequisites-and-target-resolution)
and set `MCP_NAME` to the registration's ARM name. Use `list` to resolve an
unknown name, `show` for full configuration or `source list` for just endpoints:

```bash
MCP_NAME="<server-name>"
MCP_ID="$GATEWAY_ID/workspaces/default/toolServers/$MCP_NAME"

az aigateway mcp list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway mcp show --ids "$MCP_ID" \
  --subscription "$SUBSCRIPTION" -o json
az aigateway mcp source list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" -o json
```

These reads redact secrets. Record membership, persisted IDs, backend settings,
authentication and policies before changing them.

### Prepare backend sources

Choose each source's contract, `required` state and prepared authentication:

| Kind | Source settings object |
| --- | --- |
| Remote `mcp` | `mcp: {"url":"<backend-url>","transport":"streamableHttp"}`; `sse` is also exposed |
| OpenAPI URL | `openApi: {"specSource":{"type":"url","url":"<document-url>"}}` |
| OpenAPI inline | `openApi: {"specSource":{"type":"inline","contentBase64":"<base64-document>"}}` |
| `http` | Exposed enum only; no verified kind-specific native authoring contract |

Base64 is not encryption: protect sensitive inline documents like credentials.
An existing Connector Namespace MCP endpoint can be a remote source when its
actual contract and access are supplied. Connector connection/configuration
and ACL administration remain external; portal connector-MI grant side effects
are not native ToolServer configuration.

#### Prepare an OpenAPI document

Use an OpenAPI document, not an HTML documentation page. For URL sources,
supply gateway-readable JSON; convert YAML to JSON for inline input, then
base64-encode its UTF-8 bytes. The portal's YAML-URL conversion is not a native
CLI preparation step. Before inlining, resolve relative `servers[].url`
against the document URL so backend URLs remain absolute HTTP(S). For a
document without `servers`, establish the intended backend URL explicitly.
The document's location is not the API's callable base URL.

#### Select outbound authentication

Caller-to-gateway authentication is configured separately under
[keys and identities](keys-and-identities.md). Backend `none` does not make the
gateway anonymous, and a caller's gateway key does not authenticate a backend.

| `credentials.type` | Configuration and prerequisites |
| --- | --- |
| `none` | `{"type":"none"}` for intentionally unauthenticated backend access |
| `header` | `{"type":"header","headers":{"X-Api-Key":["<secret>"]}}`; header values are **string arrays**, unlike OTLP exporter headers |
| `managedIdentity` | `{"type":"managedIdentity","managedIdentity":{"resource":"<token-audience>"}}`; optional `managedIdentity.clientId` is the UUID of an existing attached UAMI; omission selects system identity |
| `oauth2` | Shared authorization-code connection: `oauth2` object with `grantType: "authorizationCode"`, `authorizationUrl`, `tokenUrl`, `clientId`, requested `scopes`, and optional `clientSecret` |

An attached identity still needs backend access; plan any required grant using
the shared role-assignment workflow. Entra application registration and
provider/connector consent administration remain owner prerequisites.

### Create a ToolServer

For a two-backend federation, `endpoints.json` is the array itself. Replace
the example upstream with a prepared backend before running:

```json
[
  {
    "kind": "mcp",
    "namespace": "documentation",
    "required": true,
    "mcp": {"transport": "streamableHttp", "url": "https://learn.microsoft.com/api/mcp"},
    "credentials": {"type": "none"}
  },
  {
    "kind": "mcp",
    "namespace": "reference",
    "required": false,
    "mcp": {"transport": "streamableHttp", "url": "https://tools.example.com/mcp"},
    "credentials": {"type": "none"}
  }
]
```

```bash
az aigateway mcp create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" \
  --endpoints @endpoints.json
```

Choose authentication and `required` values for the actual backends.
Protect secret-bearing input; JSON files do not expand environment variables.

Supply `--display-name`, `--description` or `--versions` when needed. Choose
versions from the supported client/backend contract, not a guessed default.
Create refuses an existing registration; avoid concurrent creation of the same
name.

### Add or remove one source

Prefer source-local commands over rebuilding the collection. Both use
[secret-preserving conditional writes](#credential-preservation-and-implicit-secret-reads).
For a new remote source, `mcp-source.json` contains just its settings object:
`{"url":"https://learn.microsoft.com/api/mcp","transport":"streamableHttp"}`.
The credentials file contains only the selected credentials object.
Set `SOURCE_NAMESPACE` to a new unique namespace for addition:

```bash
az aigateway mcp source add --subscription "$SUBSCRIPTION" \
  --ids "$MCP_ID" \
  --namespace "$SOURCE_NAMESPACE" --kind mcp --mcp @mcp-source.json \
  --credentials @source-credentials.json --required true
```

For OpenAPI, substitute `--kind openApi --open-api @openapi-source.json`;
that file holds the `openApi` settings object from the contract table.
For confirmed removal, select the exact existing `SOURCE_NAMESPACE`:

```bash
az aigateway mcp source remove --subscription "$SUBSCRIPTION" \
  --ids "$MCP_ID" --namespace "$SOURCE_NAMESPACE"
```

Addition preserves siblings and fails on duplicate namespace; it is not a
source update. Removal fails for a missing namespace or the last source.
Neither failure authorizes remove/add replacement or server deletion.

### Edit a server or existing backend

Metadata/protocol edits PATCH only supplied fields. For example:

```bash
az aigateway mcp update --ids "$MCP_ID" --subscription "$SUBSCRIPTION" \
  --display-name "Documentation tools"
```

There is no `source update`. To change a backend URL, transport, availability
requirement or authentication, use `mcp update --endpoints`:

1. Read the current server and prepare **complete intended membership** in
   `endpoints-edit.json`. Include each retained source's writable `kind`,
   `namespace`, `required` and `mcp`/`openApi` settings.
2. Keep existing namespaces stable so the native adapter matches persisted
   source identities. Omit unchanged credentials and inline OpenAPI
   `contentBase64`; the native secret merge preserves them. Do not copy
   redaction markers, returned `id` or server-managed OAuth status into input.
3. Confirm the collection replacement and its implicit secret read, then apply:

```bash
az aigateway mcp update --ids "$MCP_ID" --subscription "$SUBSCRIPTION" \
  --endpoints @endpoints-edit.json
```

Omitting a source removes it; omitting an unchanged credential is not a request
to remove that credential. A namespace change is not a metadata rename.
Ambiguous namespaces or unsupported authentication/selector state that cannot
round-trip block the endpoint edit, not an unrelated metadata-only edit.

#### Credential preservation and implicit secret reads

On an existing ToolServer, **source add/remove and update with `--endpoints`**
internally call ToolServer `listSecrets`, including for unchanged siblings.
Obtain explicit consent for this retrieval and establish the required permission;
do not retrieve or print secrets separately to reconstruct input.
Ordinary list/show/source-list reads, create, and metadata/protocol/policy-only
updates do not trigger this preservation read.

The native adapter merges secret fragments for matching persisted sources,
checks that GET and secret-read ETags agree, strips server-managed OAuth
metadata, and PATCHes with `If-Match`. Supply protected secret values only for
intended credential changes; a redaction marker can overwrite a preserved
value. A conflict requires a fresh read and decision, not a blind retry.
Remove/add is not a credential-preservation workaround.

### Attach or configure policies

Compatible policies attach to the ToolServer's `properties.policies`, not a
backend source or individual tool. Applicable workspace defaults also matter.
Use [policy configuration](policies.md) for `requestRateLimit`, `ipFilter`,
`toolThreatProtection`, and `agentHooks`, including resource scope, caller
partitions and external evaluation prerequisites.

Merge the requested configuration into the **complete intended policy array**,
preserving other instances and their IDs:

```bash
az aigateway mcp update --ids "$MCP_ID" --subscription "$SUBSCRIPTION" \
  --policies @tool-server-policies.json
```

This replaces policies, not endpoints; do not include `--endpoints` for a
policy-only change.

### Diagnose backend OAuth without initiating it

Use saved nonsecret fields, not `authorize`, as diagnostic evidence:

```bash
az aigateway mcp show --ids "$MCP_ID" --subscription "$SUBSCRIPTION" \
  --query 'properties.endpoints[].{id:id,namespace:namespace,auth:credentials.type,grant:credentials.oauth2.grantType,status:credentials.oauth2.status,expires:credentials.oauth2.tokenExpiresUtc}' \
  -o json
```

Compare the selected source's client ID, authorization/token URLs and scopes
with its application contract. Missing status or timestamps prove neither
success nor failure. Saved settings, sign-in/consent and observed backend
usability are separate evidence; diagnostics authorize no initiation or changes.

#### Initiate only when explicitly authorized

Use the persisted endpoint `id`, not a namespace, tool name or guessed UUID.
Establish a private login-link handoff before initiation. Capture without
printing in an approved protected script with tracing disabled:

```bash
OAUTH_INITIATION="$(az aigateway mcp authorize \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" \
  --tool-server-name "$MCP_NAME" --endpoint-id "$ENDPOINT_ID" \
  --output json)" || exit 1
```

The result contains a sensitive login link, redirect URI and expiry. Use only
the approved handoff and clear `OAUTH_INITIATION` afterwards. Built-in tracing
suppression does not protect ordinary agent output. An issued link is
initiation, not completed authorization or proof of a connected backend.

### Delete a ToolServer

After confirming deletion of this registration and its gateway-facing endpoint:

```bash
az aigateway mcp delete --ids "$MCP_ID" --subscription "$SUBSCRIPTION" --yes
```

Require authoritative absence. The host and its source registrations are
removed; upstream services, external connections, consent and grants remain.

## Verify configuration

After create/update/source/policy changes, repeat `mcp show` on the exact
`$MCP_ID`. Compare intended fields and preserved source membership/IDs,
namespaces, `required` flags, versions, nonsecret authentication settings and
policy IDs/configuration. Check existing `allowList`, `blocked` and
`accessState` when returned.
For policy changes, also inspect applicable workspace defaults. A mismatch or
failed read-back is an explicit verification gap, not permission to retry a write.

## Identify remaining runtime uncertainty

Use native reads to narrow a diagnosis without treating them as runtime tests:

| Symptom | Configuration evidence and remaining question |
| --- | --- |
| Tools are missing | Check membership, URL, namespace, `required`, auth type and returned tool rules/access state. Optional backends may be skipped; actual discovery remains unverified. |
| Tool names changed | Compare namespaces and final-name rules; reconcile client references rather than assuming backend operations were removed. |
| Discovery fails | Check required sources, versions, authentication and returned server access state. Reachability and compatibility still need runtime evidence. |
| Tools list but invocation fails | Check returned blocked selectors, policies and backend authentication. Listing does not establish execution permission; obtain runtime denial details. |
| OAuth link was issued or backend was saved | Use the OAuth diagnostic above. Initiation and saved credentials do not establish completed consent or backend access. |

The native surface has no established runtime `tools/list`, discovery refresh
or tool-execution command. Report verified configuration separately from
unverified tool exposure, OAuth completion, OpenAPI behavior and policy
enforcement. If runtime evidence is needed, identify the separately authorized
portal/client venue; do not invoke a tool without authorization.
