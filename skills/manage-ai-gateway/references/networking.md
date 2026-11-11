# Gateway networking and private connections

[Apply the administrator workflow](../SKILL.md). Gateway
settings and connections only; existing subnets, private endpoints and DNS
remain externally owned.

## Choose the traffic path

| Task / portal control | Native control and boundary |
| --- | --- |
| Private backends: **Networking > Outbound**, VNet integration | `--subnet`: outbound backend routing, not ingress isolation or backend authorization |
| Private-only clients: **Networking > Inbound** | `--public-network-access`, approved gateway endpoint and client DNS/reachability; unsupported isolation below |
| Connection: **Inbound** row | `approve`/`reject`/`delete`: gateway-side decision, not endpoint/DNS provisioning or public access |

[Service evidence](activities-and-cli-coverage.md#operation-gaps-and-applicability)
and [Lab 18](../../../labs/18-private-networking/README.md#how-it-works) record
unavailable typed-gateway private ingress and ineffective public disablement.
Portal gates/help do not supersede service evidence: do not offer `Disabled`
as isolation or bypass the gap with legacy resources/feature registration.

## Read and confirm

```bash
az aigateway network show --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" -o json
```

Compare public access, subnet and provisioning with the requested traffic
path. `network show` projects `properties.backend.subnet.id` as
`virtualNetworkConfiguration.subnetResourceId`, not a legacy wire contract.
Skip no-ops; identify client/backend impact and specifically confirm the change.

For outbound integration, record exact subnet, backend endpoint, DNS zone/link
IDs and owners. Require the gateway's subscription/region, a dedicated subnet
of at least `/27` (`/24` recommended), `Microsoft.App/environments` delegation,
and the lab's outbound TCP 443 allowances to `Storage` and `AzureKeyVault`.
Keep private endpoints outside the integration subnet. Check capacity,
effective NSGs/firewalls, routes/return paths and DNS links/forwarding/resolver
reachability with the owner; attachment does not establish these.

Keep backend hostnames for HTTPS validation. Subnet updates neither enable an
identity nor grant [backend access](keys-and-identities.md); authentication
and reachability are independent. Missing infrastructure goes to its owner.

## Apply the smallest native change

Refresh before writing: network/connection paths send no `If-Match`, so reads
are not concurrency protection. `network update` sends only supplied settings:

```bash
az aigateway network update --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" --subnet "$SUBNET_ID"
```

`$SUBNET_ID` is the existing subnet ARM ID. To detach, substitute
`--disable-vnet-integration true`; it is mutually exclusive with `--subnet`.
Either change can interrupt private backends. Public access uses
`--public-network-access Enabled|Disabled`; never reopen automatically.
If stronger service evidence enables disablement, first verify private
client/DNS access and confirm a lockout/recovery plan.

Prefer default operation tracking. With `--no-wait`, bound the parent wait:

```bash
az aigateway network wait --ids "$GATEWAY_ID" \
  --subscription "$SUBSCRIPTION" --updated --timeout 600 --interval 15
az aigateway show --ids "$GATEWAY_ID" --subscription "$SUBSCRIPTION" -o json
```

`--updated` checks parent provisioning (`Active`/`Succeeded`), not the changed
subnet or operation result; stale success can precede operation failure.
After either mode compare `properties.publicNetworkAccess`,
`properties.backend.subnet.id`, provisioning and preserved siblings. Retain
operation outcomes; reconcile failures/timeouts before retrying.

## Existing private endpoint connections

```bash
az aigateway network private-endpoint-connection list \
  --subscription "$SUBSCRIPTION" -g "$RG" --gateway-name "$GATEWAY" -o json
az aigateway network private-endpoint-connection show \
  --ids "$CONNECTION_ID" --subscription "$SUBSCRIPTION" -o json
```

Select `$CONNECTION_ID` under `$GATEWAY_ID/privateEndpointConnections/`, not
the backing `privateEndpoint.id`. Match peer ID, owner, clients and current
state; never bulk-approve or trust display names. For the confirmed `Pending`
request:

```bash
az aigateway network private-endpoint-connection approve \
  --ids "$CONNECTION_ID" --subscription "$SUBSCRIPTION" \
  --description "$DECISION_REASON"
```

Use `reject` with the same selectors/reason for a confirmed denial, or
`delete` with those selectors but no `--description` for a confirmed disconnect.
Rejection/deletion can cut off clients; neither removes the backing
`Microsoft.Network/privateEndpoints` resource or DNS.

Repeat `show`: require intended `properties.privateLinkServiceConnectionState.status`
(`Approved`/`Rejected`) and completed provisioning, or authoritative absence for deletion.
With `--no-wait`, use connection `wait` with the same selectors,
`--updated` (or `--deleted`), `--timeout 600 --interval 15`. Here `--updated`
checks child provisioning (`Active`/`Succeeded`), not approval. Reconcile
unknown outcomes before retrying.

## Separate configuration from connectivity

Report persisted fields/operation outcomes separately from runtime evidence.
Native reads do not test DNS, NSGs or traffic. Obtain separately authorized
evidence from the intended client/gateway path; another VM's DNS is preliminary.
Any future private-only claim needs private client success and public-path
rejection, not an authentication, DNS or backend error. Otherwise mark it
unverified. Use [telemetry troubleshooting](telemetry-and-troubleshooting.md)
for export failures, not public-access changes. Missing telemetry does not
authorize network changes.
