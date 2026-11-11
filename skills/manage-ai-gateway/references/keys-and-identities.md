# Caller authentication and outbound gateway identity

There are two separate authentication connections:

| Connection | Preferred authentication | Required authorization |
| --- | --- | --- |
| Inbound: application or user to gateway | Microsoft Entra ID OAuth access token for the caller | A gateway data-plane role at the intended gateway/workspace or asset scope |
| Outbound: gateway to model provider or tool backend | Gateway managed identity, where the backend and native configuration support it | Backend roles or access grants for that gateway identity |

Neither connection grants access to the other. A caller's token or gateway
API key is not a backend credential. A gateway's managed identity does not
give the caller permission to invoke the gateway.
Apply the [scope, credential, and confirmation rules](../SKILL.md).

## Inbound: prefer Microsoft Entra ID

Use the application's existing supported OAuth flow. Delegated users request
`https://ai.gateway.azure.com/Data.All`; workload identities request resource
`https://ai.gateway.azure.com`, or scope
`https://ai.gateway.azure.com/.default` with an identity SDK. Send the runtime
token in the `Authorization: Bearer <token>` header, not an ARM management
token or a provider token. Use an identity library to refresh tokens; do not
save access tokens in source files or replay scripts.

The caller also needs **AI Gateway Models User**, **AI Gateway Tools User**,
or **AI Gateway User** at the appropriate scope. A management role such as
Contributor does not imply runtime invocation access. Delegated applications
also need the gateway data-plane permission and tenant consent. See the
[developer authentication workflow](../../use-ai-gateway/SKILL.md#establish-runtime-authentication)
for token acquisition, and the
[Entra ID and RBAC lab](https://github.com/Azure/aigateway/tree/main/labs/11-entra-rbac)
for caller-role examples.

Role assignments and Entra application/consent changes are external
prerequisites, not writes performed by this skill. Report the missing
principal, role, and scope to the owner rather than substituting a shared key.

## Outbound: prefer gateway managed identity

Enable the gateway's system-assigned identity or attach an existing
user-assigned managed identity, then select that identity in the supported
provider or MCP source authentication configuration. Identity attachment
alone does not configure backend authentication or grant access.

Before calling a backend, have its owner grant the selected gateway
principal the required role at that backend's scope. For example, the
Foundry onboarding path grants **Foundry User** on the existing account.
For another model or tool target, verify its own required audience,
role/access policy, and supported identity flow; do not reuse a Foundry
grant or assume every MCP source supports managed identity.
See [provider authentication](models-and-routing.md#provider-configuration),
[MCP credentials](mcp.md), and the
[backend identity lab](https://github.com/Azure/aigateway/tree/main/labs/12-backend-identity).

Use the [identity commands below](#manage-outbound-gateway-identity) only
after confirmation. External role grants remain the backend owner's work.
Verify both gateway configuration and backend access; a saved identity
setting alone does not prove a successful model or tool call.

## Inbound alternative: gateway API keys

Use keys only when the chosen client cannot use the supported identity flow
or the user explicitly requires them. They grant gateway-wide runtime access,
not per-model/tool permissions. Keep values in an approved secret store and
retrieve them only for the authorized use, in protected memory or protected
files outside source control. Never put them in chat, logs, shell history,
browser code, or replay scripts. The following operations manage these
**inbound caller keys**, not provider or MCP backend credentials.

### Inventory keys without retrieving values

```bash
az aigateway api-key list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway api-key show --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" -o json
```

These return metadata, not key values. Select the key by resource identity,
state, purpose, and expiry; there is no assumed `default` key and no silent
first-key selection. The keys are gateway-wide, not per-model/tool grants.
Creating one gives broad runtime access; explain and confirm that impact.

### Create, suspend, expire, or remove a key

After confirming the intended identity/access:

```bash
az aigateway api-key create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" \
  --display-name "$KEY_DISPLAY_NAME"
```

Inspect existence before create and refuse an accidental overwrite.
Create returns redacted metadata and may not preserve the requested
friendly label; verify through `show`. Do not retrieve values automatically.
If state/expiry is required, explain that a subsequent update is a separate
write, not an atomic create-with-expiry.

For selected state or expiry changes:

```bash
az aigateway api-key update --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" --state suspended
```

Use `--state active` to reactivate or `--expiration-date "$EXPIRY"` with an
explicit ISO 8601 timestamp to change expiry. Confirm each access change,
then verify actual metadata. Do not invent expiry-clearing syntax.
Although `--display-name` is visible on update, the reviewed service rejects
renaming; do not claim it succeeded.

Confirmed `api-key delete` removes the selected key and breaks its clients.
Read before deletion, explain consumers affected, execute with exact
selectors/ID where supported, and require authoritative absence afterward.
Do not delete keys merely because they appear unused; metadata is not
traffic evidence.

### Retrieve or replace a value

Retrieve only one deliberately selected key after explicit authorization.
Use a private execution path with tracing disabled and capture the value
without exposing command output. For example, inside a protected script:

```bash
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" \
  -n "$KEY_NAME" --query primaryKey -o tsv)" || exit 1
if [ -z "$AI_GATEWAY_API_KEY" ] || [ "$AI_GATEWAY_API_KEY" = "null" ]; then
  printf '%s\n' 'No usable key value returned; verify key identity and permissions.' >&2
  exit 1
fi
```

Do not echo, log, dump the environment, or write this value into the replay
script. Clear it with `unset AI_GATEWAY_API_KEY` after the approved use.
A "Subscription not found" error can refer to the named key/subscription
resource; inspect key metadata rather than switching Azure subscriptions
blindly.

`api-key update --primary-key` or `--secondary-key` replaces a selected value.
Prefer regeneration unless a supplied replacement is specifically required.
Use runtime secret input, never a literal in history. Scalar CLI flags can
expose expanded secrets in process arguments even when shell history is safe;
if the execution environment cannot protect that exposure, report the input
channel limitation instead of passing the secret. Never invent file/STDIN
support for scalar options.

### Stage rotation

1. Identify which value clients currently use and choose the other value
   for the first rotation. Do not assume primary is unused.
2. Obtain confirmation for the selected key/value and invalidation impact.
3. Execute one rotation:

```bash
az aigateway api-key regenerate --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" --key-type secondary
```

4. Retrieve the replacement only when authorized, through the protected
   path; migrate clients through their owners. No app/secret-store writes
   are included in this skill.
5. Obtain client cutover evidence before separately confirming/rotating the
   other value. Never rotate both in one batch.

A successful rotation command does not prove clients work or that retrieval
succeeded. If the command times out, reconcile before another rotation;
repeating it may invalidate a replacement already in use.

## Manage outbound gateway identity

```bash
az aigateway identity show --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" -o json
```

Inspect system identity type/principal, attached UAMIs/client IDs, and gateway
provider/MCP/exporter auth dependencies. The parent must be an unambiguous
typed gateway; identity assign/remove lack exposed exact `--ids` selectors
in the reviewed CLI, so apply the skill's name-only dispatch guard.

After identity/access confirmation, enable system identity or attach an
existing UAMI:

```bash
az aigateway identity assign --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" --system-assigned true
```

Use `--user-assigned "$IDENTITY_ID"` for an existing UAMI instead.
Other identities are preserved. Verify through `identity show` and the
exact root `show`; wait with bounded `identity wait --updated` if the
selected asynchronous operation requires it.

After dependency review and immediate confirmation:

```bash
az aigateway identity remove --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" --user-assigned "$IDENTITY_ID"
```

Use `--system-assigned true` instead to disable system identity. Removing
system identity recycles its service principal; re-enabling is not a
restoration of its old principal/grants. Detaching a UAMI does not delete
the identity resource. Verify selected removals and retained identities.

No identity operation grants Foundry/telemetry/source access or cleans up
external role assignments. Azure invocation roles under
`Microsoft.Authorization/roleAssignments`, even when scoped to a gateway
or alias/ToolServer, are outside this skill's own-RP resource boundary.
Explain the exact missing role/scope/principal for the appropriate owner;
do not use a gateway key or governance policy as a substitute.
