# Gateway networking and private connections

Apply [typed target resolution and confirmation](../SKILL.md). Manage gateway
network properties and existing gateway-side connections only, not the VNet,
subnet, backing endpoint, DNS, role grants, or feature registration.

## Inspect prerequisites and current state

```bash
az aigateway network show --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" -o json
az aigateway network private-endpoint-connection list \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" -o json
```

Inspect public access, outbound subnet, provisioning, exact private endpoint
peer IDs, and connection/provisioning states. A failed connection read is not
an empty inventory. Public ingress and outbound integration are separate
controls. CLI network output can project the typed `backend.subnet` contract
into a networking view; do not infer legacy wire properties from that view.

For an existing integration subnet, use authorized read-only Azure CLI
inspection to establish the exact ID, region, delegation, address capacity,
occupancy, NSG/routes/DNS, and operator ownership. Typed-gateway integration
requires same-region delegation to `Microsoft.App/environments`; the CLI
does not validate all prerequisites. Do not use the old service delegation
or silently modify the subnet. Report missing prerequisite evidence.

The portal's inbound UI rollout and feature enrollment can restrict portal
editing. They are not universal ARM availability guarantees. Use current
published CLI/service evidence and permissions; do not bypass a service
denial by changing feature registration or resource families.

## Public access

Before disabling public ingress, identify a working approved private path
and its client/DNS dependencies, explain lockout risk, and confirm the exact
change. Native configuration cannot prove private reachability.

```bash
az aigateway network update --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" --public-network-access Disabled
az aigateway network show --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" -o json
```

Use `Enabled` only for an explicitly confirmed opening. Do not couple the
change to an outbound update or automatically reopen public access after
failure.

## Outbound subnet integration

After prerequisite review and networking confirmation:

```bash
az aigateway network update --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" --subnet "$SUBNET_ID"
```

To clear integration, use `--disable-vnet-integration true` instead.
It cannot be combined with `--subnet`. Removing/changing integration can
break private backends. Send ingress and outbound changes separately so
their outcomes and recovery decisions remain clear.

Prefer the native update's default LRO tracking. If explicitly using
`--no-wait`, inspect advertised `network wait` conditions with bounded
`--timeout`/`--interval`, retain tracking evidence, and read the desired
network fields. A root's old healthy provisioning state or persisted subnet
alone does not establish the underlying asynchronous operation succeeded.
On timeout/failure, reconcile rather than repeat a disruptive update.
No blanket ETag/atomic concurrency guarantee is implied.

## Existing private endpoint connections

Read the exact selected connection first:

```bash
az aigateway network private-endpoint-connection show \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" \
  -n "$CONNECTION_NAME" -o json
```

Confirm the backing peer resource/subscription and whether the requested
decision is appropriate for its current state. Never approve every pending
connection automatically or trust only its display name.

After immediate approval confirmation:

```bash
az aigateway network private-endpoint-connection approve \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" \
  -n "$CONNECTION_NAME" --description "$DECISION_REASON"
```

For a confirmed rejection use `reject` with the same selectors/reason.
For a confirmed gateway-side disconnect use `delete`; explain connection
loss before deletion. Use the exposed exact connection `--ids` if chosen
instead of the separate selectors.

Use default operation tracking or the exposed
`network private-endpoint-connection wait` with the selected condition and
bounds when necessary. Re-read `privateLinkServiceConnectionState.status`
and provisioning for approve/reject; require authoritative absence for
delete. An operation still in progress is not a completed decision.
Unknown outcomes need reads, not blind duplicate decisions.

These actions do not delete or create a `Microsoft.Network/privateEndpoints`
resource, modify DNS/VNet configuration, or enroll a subscription. If the
backing resource needs work, report its ID and the owner prerequisite.
