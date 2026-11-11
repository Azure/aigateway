# Caller authentication and outbound gateway identity

## Choose the task

| Task | Inspect → change |
| --- | --- |
| Authorize callers | Principal, token flow, grants and scope → least-privileged role |
| Manage keys | Metadata, consumers and primary/secondary usage → one `api-key` operation |
| Authenticate outbound | Identity, auth/audience and grants → change each separately |
| Diagnose denial | Locate ARM/runtime/backend failure → read only, not credential substitution |

Use the [shared safeguards](../SKILL.md) and resolved variables.
Examples are independent, not a batch.

## Understand the effects

**ARM management access is not runtime access.**
Contributor implies neither invocation nor role-assignment authority.
Prefer **AI Gateway Models User** on selected aliases,
**AI Gateway Tools User** on selected ToolServers, or **AI Gateway User** for both.
Default-workspace/gateway grants include future assets. Inspect direct,
inherited and relevant group-derived grants and role DataActions before adding.

Entra tokens target the gateway runtime, not ARM/backend. Check tenant/audience
and delegated permission/consent separately from caller roles; token issuance
does not prove gateway acceptance. Use the
[Entra/RBAC lab](../../../labs/11-entra-rbac/README.md) for flow examples, verifying
the intended audience. Keys do not repair missing caller roles.

**Keys are gateway-wide, not per-asset grants.** Primary/secondary share state,
expiry and caller identity for usage and [caller-partitioned policies](policies.md).
Suspension/expiry affects both; reactivation does not clear expiry. Rotation
invalidates only the selected value, preserves caller identity and does not
extend expiry. A new key changes caller identity: review accounting continuity
and per-caller overrides before replacing rather than rotating.

**Outbound identity is separate from callers.** Enable system identity or attach
an **existing** user-assigned managed identity (UAMI); select asset auth and grant
destination access separately. UAMI **resource ID** attaches it,
**client ID** selects it, and **principal/object ID** receives grants. For managed-identity
authentication, an optional `clientId` selects an attached UAMI; omission
selects the enabled system identity. Each asset reference owns its JSON shape.
The token audience identifies a destination service, not an identity or authorization.

Inspect dependent [providers](models-and-routing.md#provider-configuration),
[MCP sources](mcp.md) and [exporters](telemetry-and-troubleshooting.md).
Attachment does not switch their auth; removal can break them. Re-enabling
system identity creates a new principal without old grants. UAMI detachment
deletes neither identity nor grants, which other gateways may use.

Use the [grant procedure](#grant-caller-or-destination-access) for caller and
destination access, not an asset registration as an implicit permission change.

## Execute the smallest native change

Key create and identity show/assign/remove use names: apply the
[shared dispatch guard](../SKILL.md#prerequisites-and-target-resolution).
Coordinate concurrent admins: key/identity writes lack confirmed conditional
guards; absence checks are not atomic create guards.

### Inspect or change caller keys

```bash
az aigateway api-key list --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway api-key show --subscription "$SUBSCRIPTION" \
  --ids "$KEY_ID" -o json
```

Select by identity/purpose/state/expiry, not `default`/`master` or first result.
Set `KEY_ID` from validated metadata; complete pagination before absence claims.
Metadata does not establish usage.

| Task | `az aigateway api-key` operation |
| --- | --- |
| Issue | `create`; confirm gateway-wide access and name absence |
| Suspend | `update --ids "$KEY_ID" --state suspended` |
| Reactivate | `update --ids "$KEY_ID" --state active`; check expiry |
| Set expiry | `update --ids "$KEY_ID" --expiration-date "$EXPIRY"`; ISO 8601 |
| Delete | `delete --ids "$KEY_ID"`; confirm affected consumers |

Confirm key changes. Add `--subscription "$SUBSCRIPTION"` throughout:

```bash
az aigateway api-key create --subscription "$SUBSCRIPTION" \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" -o json
```

Create returns redacted metadata. State/expiry require a separate update, not
atomic creation. Renaming is service-rejected despite `--display-name`;
no expiry-clearing syntax is established.

### Retrieve or replace a value

`list-secrets` reads both values; `--query` filters output, not server access.
Authorize separately from creation/rotation. In an approved protected script,
with tracing/debug/verbose disabled, retain only the needed value:

```bash
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets \
  --subscription "$SUBSCRIPTION" --ids "$KEY_ID" \
  --query secondaryKey -o tsv)" || exit 1
if [ -z "$AI_GATEWAY_API_KEY" ] || [ "$AI_GATEWAY_API_KEY" = "null" ]; then
  printf '%s\n' 'No usable key returned.' >&2
  exit 1
fi
```

Follow [protected secret handling](../SKILL.md#authorization-and-preservation)
and `unset AI_GATEWAY_API_KEY` after use. Prefer regeneration over
`update --primary-key`/`--secondary-key`. Supplied scalar values can leak through
process listings: require an established protected input path or report the
limitation, not invented file/STDIN support.

### Stage rotation

1. Establish primary/secondary usage; rotate the unused value first. If both
   are used or usage is unknown, obtain a cutover plan.
2. Confirm key/value, invalidation impact, expiry and overlap window.
3. Execute once; secondary must be safe to invalidate for this example:

```bash
az aigateway api-key regenerate --subscription "$SUBSCRIPTION" \
  --ids "$KEY_ID" --key-type secondary -o none
```

4. Retrieve only when authorized; owners cut over clients/secret stores.
5. Require cutover evidence and separate confirmation before rotating the other
   value, never both in one batch. For leaks, consider confirmed suspension.

### Enable, attach, or remove outbound identity

Inspect, then confirm the identity change:

```bash
az aigateway identity show --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" -o json
az aigateway identity assign --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" --system-assigned true -o json
```

Use `--user-assigned "$IDENTITY_ID"` instead for a UAMI; other identities are
preserved absent races. After dependency review and removal confirmation:

```bash
az aigateway identity remove --subscription "$SUBSCRIPTION" \
  -g "$RG" -n "$GATEWAY" --user-assigned "$IDENTITY_ID" -o json
```

Use `--system-assigned true` instead to disable system identity. Resolve its
principal after enablement; select asset auth via its reference.
For Foundry onboarding, use the [low-level registration workflow](models-and-routing.md#foundry-provider)
to keep identity and grant decisions separate.

### Grant caller or destination access

Plan principal, required operations, least-privileged role and narrowest scope;
reuse sufficient existing/custom-role access. Foundry's documented role is
**Foundry User** (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) at the existing account;
other destinations use their task reference's requirements.
Check assignment authority, conditions and activation before requesting exact
confirmation under the [role-assignment rule](../SKILL.md#operating-boundary).
If authority or confirmation is missing, provide the owner these same details
and command instead. Unreadable permissions/grants are gaps, not absence.

Resolve `PRINCIPAL_ID` (caller/selected identity's object ID), `ROLE_ID`,
`GRANT_SCOPE`, `GRANT_SUBSCRIPTION` and `PRINCIPAL_TYPE` (`User`, `Group`, or
`ServicePrincipal`; MI uses the latter). Use a validated alias/ToolServer ID for
caller scope or destination ID for outbound access. Inspect before confirming:

```bash
az role assignment list --subscription "$GRANT_SUBSCRIPTION" \
  --assignee-object-id "$PRINCIPAL_ID" --scope "$GRANT_SCOPE" \
  --include-inherited --fill-principal-name false -o json
```

Resolve group-derived access separately; this list omits it.
After authority and exact confirmation:

```bash
az role assignment create --subscription "$GRANT_SUBSCRIPTION" \
  --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "$ROLE_ID" --scope "$GRANT_SCOPE" -o json
```

Entra app/consent and connector ACL changes remain outside the
[operating boundary](../SKILL.md#operating-boundary), not native JSON features.

## Verify configuration

- **Keys:** show metadata; verify ID, state/expiry and preserved fields. Create
  labels may not persist: re-read. Verify deletion by authoritative absence.
- **Identity:** read the exact typed root; verify principal/client IDs, retained
  identities and selected asset auth. Identity-show not-found can mean unassigned,
  not a missing gateway. Bounded `identity wait --updated` waits for gateway
  provisioning, not a specific identity/principal field.
- **Grants:** re-read principal, role definition, scope and conditions. Conflict
  does not prove the intended grant exists. Leave residual grants after
  detachment/partial failure for explicit owner review.

Reconcile uncertain delivery before retrying. Rotation metadata cannot prove
which value clients received; repetition may invalidate replacements.
Stop until cutover evidence resolves this.

## Identify remaining runtime uncertainty

Not every backend supports MI. Use the [shared verification boundary](../SKILL.md#operate)
to separate configuration/grants from token issuance, propagation or invocation.

Locate denials before remediation: ARM → operator permissions; runtime → caller
role/scope, tenant/audience/consent or key state/expiry; backend → selected
identity, audience and destination grants. Check error codes: quotas/IP controls
can also deny traffic. "Subscription not found" may mean the key resource.
Use [troubleshooting](telemetry-and-troubleshooting.md) for nonsecret evidence.
