# MCP ToolServers reference

This reference describes gateway ToolServers, backend sources, authentication,
and tool exposure on `Microsoft.ApiManagement/aigateways`. Use it with the
[administrator workflow](../SKILL.md) and
[native capability inventory](activities-and-cli-coverage.md).

## Resource model

| Object | Configuration responsibility | Relationships and ownership |
| --- | --- | --- |
| ToolServer | Gateway-facing MCP registration, supported versions, source membership, and compatible policies | Gateway-owned host under the default workspace |
| Backend source | One upstream MCP/OpenAPI contract, namespace, required state, and outbound credentials | An entry in the ToolServer's `properties.endpoints` array |
| Upstream service | Actual tools or API operations, availability, and source-side access | External service; registration does not transfer its ownership |
| Published tool | Runtime tool exposed through the federation | Not an independently managed native ARM resource or policy host |

The ToolServer host is
`workspaces/default/toolServers/<server>` under the selected gateway.
Native source commands edit that host's endpoint collection; they do not
provision the upstream service.

### Identifiers

| Identifier | Meaning |
| --- | --- |
| ToolServer ARM name / ID | Selects the gateway registration for `mcp` operations |
| Source `namespace` | Operator-selected unique source identity within the server; selector for native source add/remove operations |
| Persisted endpoint `id` | Server-generated identity returned by `mcp show`; selector for OAuth initiation |
| Upstream URL | Backend MCP endpoint or OpenAPI document location, not the gateway's caller-facing endpoint |
| Runtime tool name | Name discovered through the published MCP surface, not a ToolServer/source management selector |

Display names are descriptive metadata. Runtime endpoints and tool names
come from the actual gateway/service contract and discovery; a management
resource name or source URL is not sufficient to derive them.

## ToolServer configuration

| Setting | Meaning and constraints |
| --- | --- |
| `type` | ToolServer type; the reviewed native interface supports `mcp` |
| `displayName`, `description` | Management metadata |
| `versions` | Finite supported MCP protocol-version list for the server |
| `endpoints` | Nonempty complete collection of backend source objects |
| `policies` | Compatible inline ToolServer controls, separate from source credentials |
| `failureMode` | `failClosed`/`failOpen` accepted at creation only; not returned on reads or supported by update |

The server's MCP protocol versions and a backend MCP source's transport
are separate settings. An OpenAPI source remains an input to an MCP
ToolServer; it does not change the server's type to OpenAPI.

Choose protocol versions from the supported contract rather than a guessed
default. `failureMode` command acceptance does not prove service enforcement;
the reviewed read/update surface cannot establish or modify that behavior.

## Backend source contracts

The writable endpoint shape contains `kind`, `namespace`, `required`,
kind-specific settings, and `credentials`.

| Source kind | Native settings | Contract |
| --- | --- | --- |
| `mcp` | `mcp.url`, `mcp.transport` | Existing MCP endpoint with `streamableHttp` or `sse` backend transport |
| `openApi`, URL document | `openApi.specSource.type: "url"` and `url` | Existing OpenAPI document accessible to the gateway |
| `openApi`, inline document | `openApi.specSource.type: "inline"` and `contentBase64` | Base64-encoded OpenAPI document in the source configuration |
| `http` | Enum exposed, but no verified kind-specific native authoring contract | Capability gap rather than an interchangeable MCP/OpenAPI shape |

`namespace` distinguishes sources within the server. `required` expresses
whether the gateway must reach that source to serve tools; it is not the
server's protocol version or an authentication mode.

The document or endpoint must describe the intended operations and be
reachable with the prepared source access. A valid OpenAPI registration
does not prove generated tools can be called. Base64 encoding is not
encryption; sensitive documents need protected input just like credentials.

Existing Connector Namespace MCP endpoints can be referenced as upstream
MCP services when their actual contract and access are supplied. Source
connections/configurations, stored external credentials, and connector ACLs
remain external. Portal connector-MI grant side effects are not part of
native ToolServer configuration.

## Authentication boundaries

| Connection | Credential purpose | Configuration ownership |
| --- | --- | --- |
| Caller to gateway | Authenticates access to the published MCP server | Gateway caller keys or supported Entra access; see [keys and identities](keys-and-identities.md) |
| Gateway to source | Authenticates outbound calls to one upstream service | That source's `credentials` object plus pre-existing external authorization |

A source using `credentials.type: "none"` does not make the gateway
anonymous. A caller's gateway key does not automatically authenticate the
upstream service. Likewise, attaching a gateway identity does not grant
that identity permission at the source.

### Backend credential types

| Type | Native fields | Prerequisites and semantics |
| --- | --- | --- |
| `none` | No backend credential | Intentionally unauthenticated upstream access |
| `header` | `headers`: header names mapped to string arrays | Exact header values expected by the source, supplied through protected input |
| `managedIdentity` | `managedIdentity.resource`, optional `clientId` | Backend token audience and an existing attached identity with prepared source access |
| `oauth2` | `grantType`, authorization/token URLs, `clientId`, requested scopes, optional `clientSecret` | Existing application configuration and authorization-code flow |

MCP credential header values are **arrays of strings**, unlike OTLP
exporter credential headers. A user-assigned managed identity is selected
by its client UUID; omission selects system identity.

The reviewed OAuth grant enum accepts only `authorizationCode`.
Client-credentials, token exchange, and Entra OBO authoring are not supplied
by those fields. Application registration, external role grants and
provider-side consent administration remain outside the skill's ownership.
Authentication changes follow the common access-change confirmation rules.

## Tool exposure and governance

Backend source configuration, discovered tool availability, and permission
to invoke a tool are different aspects of the system. Control-plane
`mcp show`/`source list` describes registrations, not an observed runtime
tool inventory or a completed backend authorization.

The reviewed endpoint input does not expose exact-tool allow/block lists,
patterns, or selector fields. Native runtime `tools/list`, discovery refresh,
and tool execution commands are also not established. These are capability
gaps; current tool names are not an equivalent substitute for a future
matching pattern.

[Governance policies](policies.md) attach to the ToolServer host, with
compatible workspace defaults also relevant. Sources and individual tools
are not independent policy hosts in this native workflow. Policy selection,
accounting scope and any evaluation-service prerequisites belong to that
policy's contract, not the backend credential object.

## Native operation paths

All commands below are prefixed with `az aigateway` and use the exact
resolved gateway/subscription selectors.

| Configuration unit | Inspection | Native changes |
| --- | --- | --- |
| ToolServer | `mcp list/show` | `mcp create/update/delete`; supplied metadata/protocol fields are distinct from endpoint-array replacement |
| Backend source | `mcp source list`, persisted endpoint metadata from `mcp show` | `mcp source add/remove`; existing source edits use the complete native endpoint-array path |
| Backend authorization initiation | Saved source credentials and persisted endpoint ID | `mcp authorize`; returns sensitive initiation material, not proof of connection |
| ToolServer policies | `mcp show` / `properties.policies` | `mcp update --policies @file`, preserving the complete intended policy array |

Use exact `--ids` where the specific command exposes it. Complete pagination
before absence/dependency claims and match returned IDs to the selected
typed gateway/default workspace.

Native create refuses an existing server, but its best-effort existence
check is not atomic create-if-absent protection. Avoid concurrent creation
of the same ARM name; use an explicit update for intended existing changes.

## Deriving a configuration change

1. Establish the published server contract: intended source services,
   operations, supported MCP versions, availability requirements and governance.
2. Read current server/source configuration and related policies. Identify
   each source's namespace, persisted ID, kind, backend contract and prepared
   authentication without enumerating secrets.
3. Compose supported source objects and independent credential configurations.
   Keep gateway caller access, backend authorization, protocol versions and
   transport choices distinct. Missing external setup is an owner prerequisite.
4. Compare desired membership and settings with current state. Choose granular
   source operations or supplied-field metadata updates where suitable;
   complete replacements require explicit membership/credential preservation.
5. Apply authorized native changes and verify configuration. Source reachability,
   OAuth completion and runtime tool exposure require separate evidence.

Inspection examples use the [resolved variables](../SKILL.md):

```bash
az aigateway mcp list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway mcp show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" -o json
az aigateway mcp source list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" -o json
```

## Configuration examples

Examples illustrate supported shapes and independent operations. Credentials,
URLs and scopes must come from the selected source's actual contract, not
from untrusted tool output or literal placeholders. Secret-bearing files
belong in an approved protected location outside source control; JSON does
not interpolate environment variables.

### Remote MCP source

`endpoints.json` contains the source array itself:

```json
[
  {
    "kind": "mcp",
    "namespace": "documentation",
    "required": true,
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

Supported `--display-name`, `--description`, and `--versions` inputs can be
supplied when requested. A multi-source server uses one array containing
all intended source objects, each with its own namespace and credentials.

### OpenAPI source

```json
[
  {
    "kind": "openApi",
    "namespace": "inventory",
    "required": true,
    "openApi": {
      "specSource": {"type": "url", "url": "https://api.example.com/openapi.json"}
    },
    "credentials": {"type": "none"}
  }
]
```

Inline documents replace `specSource` with
`{"type":"inline","contentBase64":"<base64-document>"}`. This is a document
source, not a raw URL string or a new ToolServer type.

### Header credentials

```json
{"type": "header", "headers": {"X-Api-Key": ["<runtime-secret>"]}}
```

The header names and complete values must match the upstream's requirements.
These are source credentials, not an instruction to retrieve a gateway key.

### Managed identity credentials

```json
{
  "type": "managedIdentity",
  "managedIdentity": {"resource": "<backend-token-audience>"}
}
```

An optional `managedIdentity.clientId` selects an existing attached UAMI.
Identity attachment and source permission grants are separate operations
and ownership decisions.

### OAuth credentials

```json
{
  "type": "oauth2",
  "oauth2": {
    "grantType": "authorizationCode",
    "authorizationUrl": "https://identity.example.com/authorize",
    "tokenUrl": "https://identity.example.com/token",
    "clientId": "<existing-application-client-id>",
    "scopes": ["<requested-scope>"]
  }
}
```

Include `oauth2.clientSecret` in protected input only when the existing
application requires it. Saving this object establishes configuration,
not an authorized backend session.

## Source updates and credential preservation

Granular source addition:

```bash
az aigateway mcp source add --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" \
  --namespace "$SOURCE_NAMESPACE" --kind mcp --mcp @mcp-source.json \
  --credentials @source-credentials.json --required true
```

`mcp-source.json` holds the `mcp` settings object, not the whole endpoint
or array. `source-credentials.json` holds the selected credentials object.
For OpenAPI, use `--kind openApi --open-api @openapi-source.json`, with the
`openApi` settings object. A duplicate namespace fails rather than editing
the existing source.

After confirming the selected removal:

```bash
az aigateway mcp source remove --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" \
  --namespace "$SOURCE_NAMESPACE"
```

Removal fails if it would leave no source. Server deletion is a separate
confirmed lifecycle action, not an automatic fallback.

Metadata/protocol edits use `mcp update` with only the intended
`--display-name`, `--description`, or `--versions`. Editing existing source
settings uses `mcp update --endpoints @file` with **complete intended
membership**: omission removes a source rather than leaving it unchanged.
Namespaces and persisted IDs matter to source identity and credential
preservation; a membership/identity change is not merely descriptive metadata.

Endpoint writes internally read ToolServer secrets, match the read ETags,
preserve credentials for matching persisted sources, and PATCH with
`If-Match`. Explain that implicit secret read and its required permissions.
Supply native writable objects, not a raw redacted `show` response or
server-managed OAuth metadata. Redaction markers are not replacement values.

Conflicts require fresh reads and a new decision, not unconditional retries.
Existing unsupported auth/selector state that cannot round-trip blocks that
endpoint edit; an unrelated supplied-field metadata edit may still be possible.
A remove/add replacement is not a preservation mechanism for unsupported state.

## OAuth lifecycle

| Stage | What is established | What remains separate |
| --- | --- | --- |
| Source saved | OAuth settings exist on a persisted endpoint | Provider sign-in, consent and backend authorization |
| Native initiation | Login link, redirect URI and expiry returned for that endpoint | Operator completion of the interactive provider flow |
| Interactive completion | Provider-side flow completed through the approved private handoff | Evidence that the gateway can discover/use the source |
| Runtime verification | Observed availability through the appropriate portal/runtime venue | Broader tool execution or policy-enforcement claims |

Use the persisted endpoint ID from `mcp show` for
`mcp authorize --endpoint-id`, not a guessed UUID or tool name.
Establish an approved private link handoff before initiating. The login link
is sensitive; native tracing protection does not make ordinary agent/tool
logs a safe output channel.

For example, inside a protected script with shell tracing disabled, capture
the result without printing it:

```bash
OAUTH_INITIATION="$(az aigateway mcp authorize \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" \
  --tool-server-name "$MCP_NAME" --endpoint-id "$ENDPOINT_ID" \
  --output json)" || exit 1
```

Use the result only through the approved private handoff and clear
`OAUTH_INITIATION` afterward. If no safe handoff is available, stop before
initiation. A successful command or issued link is not a connected-state
assertion, and the native CLI has no established runtime tool-listing command
to complete that verification.

## Lifecycle and verification

ToolServer/source updates affect the published gateway configuration.
External Connector Namespace setup, connection authorization and ACL grants
remain outside its lifecycle. Runtime/URL constraints on disabled features,
such as Foundry Toolbox sources, are not removed by using the CLI.

For confirmed ToolServer deletion, use `mcp delete` with the selected
scope/name or exposed exact child `--ids`, then require authoritative absence.
Gateway-owned source configuration is removed with its host; upstream
servers, external connections/credentials, consent and role grants remain
separate resources and responsibilities.

After mutations, compare `mcp show` and `mcp source list` with the intended
server type, versions, membership, source identities, kind-specific settings,
nonsecret authentication metadata and policies. Secret values, backend
reachability, OAuth completion and published tools require separate evidence.
Report partial or unknown outcomes and reconcile before retrying instead
of claiming that a saved registration proves a working federation.
