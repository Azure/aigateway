"""Collect an AI-asset inventory from an Azure API Management instance.

The collector is read-only and secret-free: it issues ``GET`` requests against
the APIM and Cognitive Services control planes, and never calls a ``list*``
secret action. Everywhere APIM holds a credential, the output carries a
reference and the command that retrieves it at apply time.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Sequence
from urllib.parse import urlsplit

from . import detect, ids, policy as policy_mod, secrets
from .arm import ArmAuthError, ArmClient, ArmError
from .foundry import FoundryResolver, resolved_model, target_model_registration

SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"
DEFAULT_APIM_API_VERSION = "2025-09-01-preview"

# https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent>/...
_FOUNDRY_AGENT_PATH = re.compile(r"/api/projects/(?P<project>[^/]+)/agents/(?P<agent>[^/]+)")


def _ci_get(mapping: dict[str, Any], key: str) -> Any:
    """Case-insensitive lookup.

    ``jsonRpcProperties`` is returned with PascalCase keys (``BackendUrl``,
    ``Path``) while the rest of the contract is camelCase. Read both, so a
    future normalization of the preview surface does not silently drop the
    agent's upstream.
    """
    if not mapping:
        return None
    if key in mapping:
        return mapping[key]
    lowered = key.lower()
    for name, value in mapping.items():
        if name.lower() == lowered:
            return value
    return None


@dataclass
class CollectOptions:
    # Every workspace by default: a workspace can hold model APIs and backends of
    # its own, so skipping them would silently under-report the migration.
    workspaces: list[str] = field(default_factory=lambda: ["all"])
    include_api: list[str] = field(default_factory=list)
    exclude_api: list[str] = field(default_factory=list)
    families: set[str] = field(default_factory=lambda: {"models", "mcp", "a2a"})
    resolve_foundry: bool = True
    foundry_subscriptions: list[str] = field(default_factory=list)
    apim_api_version: str = DEFAULT_APIM_API_VERSION
    cognitive_api_version: str | None = None
    include_policy_xml: bool = True
    operation_policies: bool = False
    fast: bool = False
    max_apis: int | None = None


class Collector:
    def __init__(
        self,
        client: ArmClient,
        service_id: str,
        options: CollectOptions,
        *,
        progress: Any = None,
    ) -> None:
        # A collection is dozens of serial round trips with nothing to show for
        # minutes. Without a heartbeat a slow network is indistinguishable from a
        # hang, which is exactly how the first trial run read.
        self.progress = progress or (lambda message: None)
        self.client = client
        self.service_id = service_id.rstrip("/")
        self.options = options
        self.api_version = options.apim_api_version
        self.registry = secrets.SecretRegistry(service_id=self.service_id, api_version=self.api_version)
        self.coverage: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self._policy_index: dict[str, dict[str, Any]] = {}
        # One graph for the run, kept current by `_add_policy`. Which policy
        # governs which API is asked here and in the planner, and asking it two
        # ways is how the two answers drift.
        self._graph = policy_mod.PolicyGraph([])
        self.foundry: FoundryResolver | None = None
        self.subscription_id = ids.arm_segment(self.service_id, "subscriptions") or ""
        self.excluded_backends: list[dict[str, Any]] = []
        # Every API seen, in every scope walked. Accumulated here rather than
        # returned, because it is one flat answer to "what APIs are there" and
        # the scope loop is an implementation detail of finding them.
        self.apim_apis: list[dict[str, Any]] = []
        self._operations_by_api: dict[str, list[dict[str, Any]]] = {}
        # What governs each API, kept so the model providers behind it can be
        # asked the same question. A provider's credential is set by the policy
        # of whatever publishes it just as often as by the backend record, and
        # `_model_providers` runs after the API loop has thrown the resolution
        # away. Resolving a second time there would be the two-ways drift the
        # graph comment above exists to prevent.
        self._effective_by_api: dict[str, policy_mod.Resolution] = {}
        # Named value name -> the secret ref already registered for it. A policy
        # references a named value by bare name, so that is the key; a workspace
        # redefining a service-scope name would collide, which no instance seen
        # so far does and which the registry would surface as one ref used twice.
        self._secret_by_named_value: dict[str, str] = {}

    # ------------------------------------------------------------------ run

    def run(self) -> dict[str, Any]:
        started = _now()
        service = self._service()
        workspaces = self._workspaces()

        shared: dict[str, Any] = {}
        assets: dict[str, list[dict[str, Any]]] = {
            "modelProviders": [], "models": [], "mcpServers": [], "agents": []
        }
        excluded: list[dict[str, Any]] = []

        if self.options.resolve_foundry:
            self.foundry = FoundryResolver(self.client, api_version=self.options.cognitive_api_version)
            for subscription in [self.subscription_id, *self.options.foundry_subscriptions]:
                if subscription:
                    self.foundry.scan_subscription(subscription)

        scopes = self._scopes(workspaces)

        # Before the scope loop: the global policy can reference a backend, and the
        # backend cross-reference scan reads whatever policies have been captured.
        self._collect_service_wide()

        for workspace in scopes:
            scope_shared = self._collect_shared(workspace)
            _merge_shared(shared, scope_shared)
            scope_assets, scope_excluded = self._collect_apis(workspace, scope_shared)
            for key, values in scope_assets.items():
                assets[key].extend(values)
            excluded.extend(scope_excluded)

        document = {
            "$schema": "https://github.com/Azure/aigateway/tools/migrate-apim/schemas/inventory.schema.json",
            "schemaVersion": SCHEMA_VERSION,
            "kind": "apimAiInventory",
            "generator": {
                "name": "migrate-apim",
                "version": GENERATOR_VERSION,
                "command": "collect",
            },
            "collection": {
                "startedAt": started,
                "completedAt": _now(),
                "apiVersions": {
                    "apiManagement": self.api_version,
                    "cognitiveServices": self.foundry.api_version if self.foundry else None,
                },
                "options": {
                    "workspaces": self.options.workspaces,
                    "families": sorted(self.options.families),
                    "includeApi": self.options.include_api,
                    "excludeApi": self.options.exclude_api,
                    "resolveFoundry": self.options.resolve_foundry,
                    "operationPolicies": self.options.operation_policies,
                    "fast": self.options.fast,
                },
                "requestCount": self.client.call_count,
                "coverage": self.coverage,
                "warnings": self.warnings,
            },
            "service": service,
            # What APIM has, under the names APIM gives it. A rule selects from
            # here, so the path a rule names is a path through the service's own
            # object graph rather than through this tool's decomposition of it.
            # `authorizationProviders` is the one that had drifted: we called it
            # `credentialProviders`, which is a name APIM does not use for a
            # resource it does have.
            "apim": {
                "workspaces": [
                    {**entry, "collected": entry["name"] in scopes} for entry in workspaces
                ],
                "apis": self.apim_apis,
                "backends": shared.get("backends") or [],
                "namedValues": shared.get("namedValues") or [],
                "products": shared.get("products") or [],
                "subscriptions": shared.get("subscriptions") or [],
                "certificates": shared.get("certificates") or [],
                "authorizationServers": shared.get("authorizationServers") or [],
                "openidConnectProviders": shared.get("openidConnectProviders") or [],
                "authorizationProviders": shared.get("authorizationProviders") or [],
                "policyFragments": shared.get("policyFragments") or [],
                # APIM has loggers and diagnostics; "telemetry" was a box we put
                # them in, and a rule had to select the box to reach either.
                "loggers": (shared.get("telemetry") or {}).get("loggers") or [],
                "diagnostics": (shared.get("telemetry") or {}).get("diagnostics") or [],
                "policies": self.policies,
            },
            "assets": assets,
            "excludedApis": excluded,
            "excludedBackends": self.excluded_backends,
            # Not APIM: a Microsoft.CognitiveServices account, read to resolve
            # what a Foundry backend actually serves. It stays outside `apim`
            # because putting it in would make the one claim that region makes
            # -- these are APIM's objects -- false.
            "foundryAccounts": [],
            "secrets": self.registry.items(),
        }
        if self.foundry:
            document["foundryAccounts"] = [
                account.to_dict() for account in self.foundry.accounts() if account.deployments is not None
            ]
            if self.foundry.errors:
                for error in self.foundry.errors:
                    self.warnings.append({"code": "foundryResolution", **error})
        if not self.options.include_policy_xml:
            for document_policy in self.policies:
                document_policy.pop("xml", None)
        return document

    # -------------------------------------------------------------- service

    def _service(self) -> dict[str, Any]:
        raw = self._get(self.service_id, "service", "service")
        if raw is None:
            # Why the read failed is the whole message here: reporting every
            # failure as "not found" sent an operator hunting for a service
            # that was there all along.
            entry = self.coverage[-1]
            if entry.get("status") == "notFound":
                raise ArmError(
                    f"API Management service not found: {self.service_id}. Check the name, the "
                    "resource group, and that --subscription is the one that holds it."
                )
            raise ArmError(
                f"Could not read the API Management service {self.service_id}: {entry.get('error')}"
            )
        networking = self._networking(raw.get("properties") or {})
        return {
            **_service_source(
                raw,
                subscription_id=self.subscription_id,
                resource_group=ids.arm_segment(self.service_id, "resourceGroups"),
            ),
            # Reaching a backend depends on how the source reaches it today, so the
            # target needs the same reachability -- not the same subnet, because the
            # two resource types require different delegations.
            "networking": networking,
            # A reading of the service, for a rule to narrow on. How it was worked
            # out is ours -- from `virtualNetworkType` and `publicNetworkAccess` --
            # but what it is about is the service, which is APIM's.
            "needsSubnet": (networking.get("targetRequirement") or {}).get("needsSubnet"),
        }

    def _networking(self, props: dict[str, Any]) -> dict[str, Any]:
        """How the source reaches its backends, and what the target would need.

        A VNet-integrated APIM reaches private backends through its own injected
        subnet. The gateway cannot reuse that subnet: typed gateways require a
        delegation to `Microsoft.App/environments`, where APIM uses its own. So
        this records the requirement, never a subnet to copy.
        """
        vnet = props.get("virtualNetworkConfiguration") or {}
        connections = self._list(
            f"{self.service_id}/privateEndpointConnections", "privateEndpointConnections", "service",
            quiet=True,
        )
        integrated = (props.get("virtualNetworkType") or "None") != "None"
        record: dict[str, Any] = {
            "virtualNetworkType": props.get("virtualNetworkType"),
            "publicNetworkAccess": props.get("publicNetworkAccess"),
            "vnetIntegrated": integrated,
            "subnetResourceId": vnet.get("subnetResourceId"),
            "vnetId": vnet.get("vnetid"),
            "outboundPublicIPAddresses": props.get("outboundPublicIPAddresses"),
            "natGatewayState": props.get("natGatewayState"),
            "privateEndpointConnections": [
                {
                    "name": entry.get("name"),
                    "state": ((entry.get("properties") or {}).get("privateLinkServiceConnectionState")
                              or {}).get("status"),
                }
                for entry in connections
            ],
            "targetRequirement": None,
        }
        if integrated:
            record["targetRequirement"] = {
                "needsSubnet": True,
                "delegation": "Microsoft.App/environments",
                "note": (
                    "The source reaches backends through an injected subnet. The gateway needs its "
                    "own subnet in the same region delegated to Microsoft.App/environments -- APIM's "
                    "subnet uses a different delegation and cannot be reused."
                ),
            }
        elif (props.get("publicNetworkAccess") or "Enabled") == "Disabled":
            record["targetRequirement"] = {
                "needsSubnet": False,
                "note": "Public ingress is disabled on the source; the target needs an equivalent private path.",
            }
        return record

    def _workspaces(self) -> list[dict[str, Any]]:
        raw = self._list(f"{self.service_id}/workspaces", "workspaces", "service")
        return [
            {
                "name": entry.get("name"),
                "displayName": (entry.get("properties") or {}).get("displayName"),
                "description": (entry.get("properties") or {}).get("description"),
                # workspaceAndDefault means the workspace's APIs are also served on
                # the service's default gateway hostname.
                "serveOn": (entry.get("properties") or {}).get("serveOn"),
            }
            for entry in raw
            if entry.get("name")
        ]

    def _scopes(self, workspaces: list[dict[str, Any]]) -> list[str | None]:
        """Scopes to walk: ``None`` is the service itself, then named workspaces."""
        names = [entry["name"] for entry in workspaces]
        requested = [value.lower() for value in self.options.workspaces]
        if "none" in requested:
            return [None]
        if "all" in requested:
            return [None, *names]
        selected = [name for name in names if name.lower() in requested]
        for value in self.options.workspaces:
            if value.lower() not in {"all", "none"} and value not in names:
                self.warnings.append(
                    {"code": "workspaceNotFound", "message": f"No workspace named '{value}' on this service."}
                )
        return [None, *selected]

    def _collect_service_wide(self) -> None:
        """Scopes that exist only on the service, never inside a workspace."""
        self._capture_policy(
            scope={"level": "global", "name": None, "workspace": "default",
                   "resourceId": self.service_id},
            scope_url=self.service_id,
            policy_id=ids.policy("global"),
        )

    # --------------------------------------------------------------- shared

    def _scope_url(self, workspace: str | None) -> str:
        if workspace and workspace != "default":
            return f"{self.service_id}/workspaces/{workspace}"
        return self.service_id

    def _collect_shared(self, workspace: str | None) -> dict[str, Any]:
        base = self._scope_url(workspace)
        scope_label = workspace or "service"

        backends = self._collect_backends(base, workspace, scope_label)
        named_values = self._collect_named_values(base, workspace, scope_label)
        fragments = self._collect_fragments(base, workspace, scope_label)
        products = self._collect_products(base, workspace, scope_label)
        self._graph.add_products(products)
        subscriptions = self._collect_subscriptions(base, workspace, scope_label)
        certificates = self._collect_certificates(base, scope_label) if not workspace else []
        auth_servers = self._collect_auth_servers(base, scope_label) if not workspace else []
        openid = self._collect_openid(base, scope_label) if not workspace else []
        credential_providers = self._collect_credential_providers(base, scope_label) if not workspace else []
        telemetry = self._collect_telemetry(base, scope_label) if not workspace else {}

        if workspace and workspace != "default":
            self._capture_policy(
                scope={"level": "workspace", "name": workspace, "workspace": workspace,
                       "resourceId": base},
                scope_url=base,
                policy_id=ids.policy("workspace", workspace),
            )

        return {
            "backends": backends,
            "namedValues": named_values,
            "policyFragments": fragments,
            "products": products,
            "subscriptions": subscriptions,
            "certificates": certificates,
            "authorizationServers": auth_servers,
            "openidConnectProviders": openid,
            "authorizationProviders": credential_providers,
            "telemetry": telemetry,
        }

    def _collect_backends(self, base: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/backends", "backends", scope)
        results: list[dict[str, Any]] = []
        for entry in raw:
            name = entry.get("name") or ""
            props = dict(entry.get("properties") or {})
            backend_id = ids.backend(name, workspace)
            secret_refs: list[str] = []

            credentials = props.get("credentials")
            if credentials:
                def on_literal(path: str, literal_class: str, _raw: str, _name: str = name) -> str:
                    ref = self.registry.backend_inline(
                        backend_name=_name,
                        field_path=f"credentials.{path}" if path else "credentials",
                        literal_class=literal_class,
                        workspace=workspace,
                        used_by=backend_id,
                    )
                    secret_refs.append(ref)
                    return f"${{{ref}}}"

                credentials = secrets.sanitize_structure(credentials, path="", on_literal=on_literal)
                for nv_name in secrets.named_value_references(props.get("credentials")):
                    secret_refs.append(ids.secret("namedValue", ids.scoped(workspace, nv_name)))
                for certificate_id in (props.get("credentials") or {}).get("certificateIds") or []:
                    secret_refs.append(ids.secret("certificate", ids.arm_name(certificate_id)))

            pool = props.get("pool") or {}
            record = {
                "id": backend_id,
                "name": name,
                "workspace": workspace or "default",
                "resourceId": entry.get("id"),
                "title": props.get("title"),
                "description": props.get("description"),
                "type": props.get("type") or ("Pool" if pool else "Single"),
                "protocol": props.get("protocol"),
                "url": props.get("url"),
                "host": (urlsplit(props.get("url") or "").hostname or None),
                "resourceIdRef": ids.normalize_arm_id(props.get("resourceId")),
                "azureRegion": props.get("azureRegion"),
                "credentials": credentials,
                "tls": props.get("tls"),
                "proxy": _redact_proxy(props.get("proxy")),
                "circuitBreaker": (props.get("circuitBreaker") or {}).get("rules"),
                "pool": {
                    "services": [
                        {
                            "backendId": ids.backend(ids.arm_name(item.get("id") or ""), workspace),
                            "resourceId": item.get("id"),
                            "priority": item.get("priority"),
                            "weight": item.get("weight"),
                            "preferredCarbonEmission": item.get("preferredCarbonEmission"),
                        }
                        for item in (pool.get("services") or [])
                    ],
                    "failureResponse": pool.get("failureResponse"),
                    "sessionAffinity": pool.get("sessionAffinity"),
                } if pool else None,
                "secretRefs": _dedupe(secret_refs),
                "provider": None,
            }
            # Host identifies the vendor; APIM's import naming declares the protocol.
            # They are orthogonal -- a Foundry account reached at /openai/v1 is a
            # Foundry provider speaking the OpenAI protocol -- and between them they
            # usually answer "what provider is this?" without asking anyone.
            rule = detect.provider_for_url(props.get("url"))
            convention = detect.protocol_from_backend_name(name)
            if rule or convention:
                record["provider"] = {
                    "kind": rule.kind if rule else convention["providerKind"],
                    "label": rule.label if rule else None,
                    "apiDialect": (convention or {}).get("apiDialect") or (rule.api_dialect if rule else None),
                    "targetProviderKind": (
                        rule.target_provider_kind if rule else convention["targetProviderKind"]
                    ),
                    "catalog": (convention or {}).get("catalog") or (rule.catalog if rule else None),
                    "basis": "backendHost" if rule else convention["basis"],
                    "protocolBasis": "importConvention" if convention else (
                        "backendHost" if rule else None
                    ),
                }

            # A languageModel backend states its dialect and model outright. That
            # declaration beats the host heuristic: a Foundry host serving the
            # Anthropic protocol is a Custom provider on the target, not a Foundry one.
            language_model = props.get("languageModel")
            if language_model:
                fmt = detect.language_model_format(language_model.get("apiFormat"))
                record["languageModel"] = {
                    "model": language_model.get("model"),
                    "apiFormat": language_model.get("apiFormat"),
                    "dialect": fmt["dialect"],
                    "supportedEndpoints": fmt["supportedEndpoints"],
                    "targetProviderKind": fmt["targetProviderKind"],
                    "providerKind": fmt["providerKind"],
                    "formatResolution": fmt["resolution"],
                }
                record["provider"] = {
                    "kind": rule.kind if rule else "custom",
                    "label": rule.label if rule else None,
                    "apiDialect": fmt["dialect"],
                    "declaredByBackend": True,
                }
            results.append(record)
        return results

    def _collect_named_values(self, base: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/namedValues", "namedValues", scope)
        results = []
        for entry in raw:
            props = entry.get("properties") or {}
            name = entry.get("name") or ""
            record: dict[str, Any] = {
                "id": ids.named_value(name, workspace),
                "name": name,
                "workspace": workspace or "default",
                "displayName": props.get("displayName"),
                "secret": bool(props.get("secret")),
                "tags": props.get("tags"),
                "keyVault": props.get("keyVault"),
                "value": None,
                "secretRef": None,
            }
            if props.get("secret") or props.get("keyVault"):
                record["secretRef"] = self.registry.named_value(entry, workspace=workspace, used_by=record["id"])
                self._secret_by_named_value[name] = record["secretRef"]
            else:
                # Non-secret named values are plain configuration and are part of
                # the migration payload, so keep their value.
                record["value"] = props.get("value")
            results.append(record)
        return results

    def _collect_fragments(
        self, base: str, workspace: str | None, scope: str
    ) -> list[dict[str, Any]]:
        # `format=rawxml` on the list, not only on the per-fragment fallback:
        # every other policy read goes through `get_policy`, which forces it so
        # expression text is kept as authored. Without it a fragment's
        # expressions come back XML-encoded and hash to different `expr:` ids
        # than the same expression captured at API scope.
        raw = self._list(
            f"{base}/policyFragments", "policyFragments", scope, params={"format": "rawxml"}
        )
        results = []
        for entry in raw:
            name = entry.get("name") or ""
            props = entry.get("properties") or {}
            value = props.get("value")
            unreadable = False
            if value is None:
                detail = self._get(
                    f"{base}/policyFragments/{name}", "policyFragment", scope, params={"format": "rawxml"}
                )
                value = ((detail or {}).get("properties") or {}).get("value")
                unreadable = value is None
            policy_id = ids.policy("fragment", ids.scoped(workspace, name))
            document = policy_mod.parse(
                value or "",
                policy_id=policy_id,
                scope={
                    "level": "fragment", "name": name,
                    "workspace": workspace or "default", "resourceId": entry.get("id"),
                },
                scope_url=f"{base}/policyFragments/{name}",
                registry=self.registry,
            )
            if unreadable:
                # An empty parse is a fragment that says nothing; a fragment
                # whose body could not be read says nothing about what is in
                # it. Left alike, the second reads as the first, and whatever
                # the fragment carried migrates as though it were not there.
                document["parseError"] = (
                    "The body could not be read, so what this fragment contains is unknown. "
                    "It is not evidence that the fragment is empty."
                )
            self._add_policy(document)
            results.append(
                {
                    "id": ids.fragment(name, workspace),
                    "name": name,
                    "workspace": workspace or "default",
                    "description": props.get("description"),
                    "policyId": policy_id,
                    "elementCount": len(document.get("elements") or []),
                    "parseError": document.get("parseError"),
                }
            )
        return results

    def _collect_products(self, base: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/products", "products", scope)
        results = []
        for entry in raw:
            name = entry.get("name") or ""
            props = entry.get("properties") or {}
            policy_id = ids.policy("product", ids.scoped(workspace, name))
            self._capture_policy(
                scope={"level": "product", "name": name, "workspace": workspace or "default",
                       "resourceId": entry.get("id")},
                scope_url=f"{base}/products/{name}",
                policy_id=policy_id,
            )
            linked = self._list(f"{base}/products/{name}/apis", "productApis", scope, quiet=True)
            results.append(
                {
                    "id": ids.product(name, workspace),
                    "name": name,
                    "workspace": workspace or "default",
                    "displayName": props.get("displayName"),
                    "state": props.get("state"),
                    "subscriptionRequired": props.get("subscriptionRequired"),
                    "approvalRequired": props.get("approvalRequired"),
                    "subscriptionsLimit": props.get("subscriptionsLimit"),
                    "apiIds": [ids.api(item.get("name") or "", workspace) for item in linked],
                    "policyId": policy_id if policy_id in self._policy_index else None,
                }
            )
        return results

    def _collect_subscriptions(self, base: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/subscriptions", "subscriptions", scope)
        results = []
        for entry in raw:
            name = entry.get("name") or ""
            props = entry.get("properties") or {}
            scope_id = props.get("scope") or ""
            results.append(
                {
                    "id": ids.subscription(name, workspace),
                    "name": name,
                    "workspace": workspace or "default",
                    "displayName": props.get("displayName"),
                    "state": props.get("state"),
                    "allowTracing": props.get("allowTracing"),
                    "scope": _subscription_scope(scope_id),
                    "ownerId": props.get("ownerId"),
                    "secretRef": self.registry.subscription_key(
                        name, workspace=workspace, used_by=ids.subscription(name, workspace)
                    ),
                }
            )
        return results

    def _collect_certificates(self, base: str, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/certificates", "certificates", scope)
        results = []
        for entry in raw:
            props = entry.get("properties") or {}
            name = entry.get("name") or ""
            results.append(
                {
                    "id": ids.certificate(name),
                    "name": name,
                    "subject": props.get("subject"),
                    "thumbprint": props.get("thumbprint"),
                    "expirationDate": props.get("expirationDate"),
                    "keyVault": props.get("keyVault"),
                    "secretRef": self.registry.certificate(entry, used_by=ids.certificate(name)),
                }
            )
        return results

    def _collect_auth_servers(self, base: str, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/authorizationServers", "authorizationServers", scope)
        results = []
        for entry in raw:
            props = entry.get("properties") or {}
            name = entry.get("name") or ""
            results.append(
                {
                    "id": ids.authorization_server(name),
                    "name": name,
                    "displayName": props.get("displayName"),
                    "clientId": props.get("clientId"),
                    "clientRegistrationEndpoint": props.get("clientRegistrationEndpoint"),
                    "authorizationEndpoint": props.get("authorizationEndpoint"),
                    "tokenEndpoint": props.get("tokenEndpoint"),
                    "grantTypes": props.get("grantTypes"),
                    "defaultScope": props.get("defaultScope"),
                    "bearerTokenSendingMethods": props.get("bearerTokenSendingMethods"),
                    "secretRef": self.registry.authorization_server(
                        name, used_by=ids.authorization_server(name)
                    ),
                }
            )
        return results

    def _collect_openid(self, base: str, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/openidConnectProviders", "openidConnectProviders", scope)
        results = []
        for entry in raw:
            props = entry.get("properties") or {}
            name = entry.get("name") or ""
            results.append(
                {
                    "id": ids.openid_provider(name),
                    "name": name,
                    "displayName": props.get("displayName"),
                    "metadataEndpoint": props.get("metadataEndpoint"),
                    "clientId": props.get("clientId"),
                    "useInApiDocumentation": props.get("useInApiDocumentation"),
                    "secretRef": self.registry.authorization_server(
                        name, kind="openidConnectProvider", used_by=ids.openid_provider(name)
                    ),
                }
            )
        return results

    def _collect_credential_providers(self, base: str, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/authorizationProviders", "authorizationProviders", scope)
        results = []
        for entry in raw:
            props = entry.get("properties") or {}
            name = entry.get("name") or ""
            connections = self._list(
                f"{base}/authorizationProviders/{name}/authorizations", "credentialConnections", scope, quiet=True
            )
            results.append(
                {
                    "id": ids.credential_provider(name),
                    "name": name,
                    "displayName": props.get("displayName"),
                    "identityProvider": props.get("identityProvider"),
                    "oauth2GrantType": ((props.get("oauth2") or {}).get("grantTypes") or {}) and list(
                        (props.get("oauth2") or {}).get("grantTypes", {}).keys()
                    ),
                    "connections": [
                        {
                            "name": connection.get("name"),
                            "status": (connection.get("properties") or {}).get("status"),
                            "error": (connection.get("properties") or {}).get("error"),
                            "secretRef": self.registry.credential_connection(
                                name, connection.get("name") or "", used_by=ids.credential_provider(name)
                            ),
                        }
                        for connection in connections
                    ],
                }
            )
        return results

    def _collect_telemetry(self, base: str, scope: str) -> dict[str, Any]:
        loggers = self._list(f"{base}/loggers", "loggers", scope, quiet=True)
        diagnostics = self._list(f"{base}/diagnostics", "diagnostics", scope, quiet=True)
        return {
            "loggers": [
                {
                    "name": entry.get("name"),
                    "loggerType": (entry.get("properties") or {}).get("loggerType"),
                    "resourceId": (entry.get("properties") or {}).get("resourceId"),
                    "isBuffered": (entry.get("properties") or {}).get("isBuffered"),
                    "credentialsReferenced": sorted(
                        set(secrets.named_value_references((entry.get("properties") or {}).get("credentials")))
                    ),
                }
                for entry in loggers
            ],
            "diagnostics": [
                {
                    "name": entry.get("name"),
                    "loggerId": (entry.get("properties") or {}).get("loggerId"),
                    "samplingPercentage": (
                        ((entry.get("properties") or {}).get("sampling") or {}).get("percentage")
                    ),
                    "verbosity": (entry.get("properties") or {}).get("verbosity"),
                    "logClientIp": (entry.get("properties") or {}).get("logClientIp"),
                }
                for entry in diagnostics
            ],
        }

    # ----------------------------------------------------------------- apis

    def _collect_apis(
        self, workspace: str | None, shared: dict[str, Any]
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        base = self._scope_url(workspace)
        scope_label = workspace or "service"
        raw_apis = self._list(f"{base}/apis", "apis", scope_label)
        if self.options.max_apis:
            raw_apis = raw_apis[: self.options.max_apis]

        backends_by_id = {entry["id"]: entry for entry in shared.get("backends", [])}
        backends_by_name = {entry["name"]: entry for entry in shared.get("backends", [])}

        assets: dict[str, list[dict[str, Any]]] = {
            "modelProviders": [], "models": [], "mcpServers": [], "agents": []
        }
        excluded: list[dict[str, Any]] = []
        api_index = {entry.get("name"): entry for entry in raw_apis}

        for raw in raw_apis:
            name = raw.get("name") or ""
            props = raw.get("properties") or {}
            if not props.get("isCurrent", True):
                # A superseded revision is not what callers reach, so it is not
                # inventoried -- but it was leaving by a bare `continue`, with no
                # excludedApis entry and no coverage record. That made it the one
                # thing this collector dropped without saying so, in a file whose
                # premise is that `excludedApis` proves nothing was. An operator
                # auditing what moved could not tell a revision that was
                # considered and set aside from one that was never seen.
                excluded.append(_excluded(raw, workspace, "notCurrentRevision", []))
                continue
            if self.options.exclude_api and detect.matches_any(name, self.options.exclude_api):
                excluded.append(_excluded(raw, workspace, "excludedByOption", []))
                continue
            forced = bool(self.options.include_api and detect.matches_any(name, self.options.include_api))

            api_url = f"{base}/apis/{name}"
            policy_id = ids.policy("api", ids.scoped(workspace, name))
            document = self._capture_policy(
                scope={"level": "api", "name": name, "workspace": workspace or "default",
                       "resourceId": raw.get("id")},
                scope_url=api_url,
                policy_id=policy_id,
            )
            # Policy evidence must not stop at the API's own document. An
            # authentication-managed-identity inside an included fragment, or in the
            # product or global policy, governs this API just as much -- and missing
            # it reports a credentialed backend as unauthenticated.
            #
            # The two scopes differ on purpose. Detection uses API-scoped evidence
            # only: a global llm-token-limit applies to every API and would make all
            # of them look like model APIs. Backend auth uses every scope, because
            # any of them can set it.
            api_scoped = self._graph.governing(
                api=name, workspace=workspace, levels=("api",)
            )
            effective = self._graph.governing(api=name, workspace=workspace)
            self._effective_by_api[ids.api(name, workspace)] = effective
            element_names = {element["name"] for element in api_scoped.elements}
            families = {element["family"] for element in api_scoped.elements}

            backend_record, routing_candidates = _resolve_backend(
                props, backends_by_name, backends_by_id, workspace, api_scoped.elements
            )
            candidate_records = _candidate_records(
                routing_candidates, backends_by_name, backends_by_id, workspace
            )
            backend_urls = _backend_urls(
                backend_record, backends_by_id, candidates=candidate_records
            )

            api_type = (props.get("type") or "http").lower()
            operations: list[dict[str, Any]] = []
            # MCP and A2A APIs expose no REST operations; skip the round trip.
            if api_type not in {"mcp", "a2a"} and not self.options.fast:
                operations = self._collect_operations(api_url, name, workspace, scope_label)

            self._operations_by_api[ids.api(name, workspace)] = operations

            classification = detect.classify_api(
                raw,
                backend=_raw_backend(backend_record),
                backend_urls=backend_urls,
                operation_paths=[operation["urlTemplate"] for operation in operations],
                policy_element_names=element_names,
                policy_families=families,
                backend_name=(backend_record or {}).get("name") or props.get("backendId"),
                credential_named_values=secrets.named_value_references(
                    (backend_record or {}).get("credentials")
                ),
            )
            if forced and classification.kind == "excluded":
                classification.kind = "modelApi"
                classification.confidence = "forced"
                classification.reason = "Included by --include-api"

            common = {
                "id": ids.asset(_asset_prefix(classification.kind), name, workspace),
                "workspace": workspace or "default",
                "source": _api_source(raw, workspace),
                "detection": classification.to_dict(),
                "policyRefs": _policy_refs(
                    policy_id, document, workspace, shared, name, operations,
                    operation_policies_collected=self.options.operation_policies,
                    effective=effective,
                ),
                "access": self._access(raw, name, workspace, shared),
            }

            if classification.pattern == "unconfigured":
                self.warnings.append({
                    "code": "mcpApiUnconfigured",
                    "asset": common["id"],
                    "message": (
                        f"MCP API '{name}' declares no backend, service URL, MCP properties, or tools. "
                        "There is nothing to migrate until the operator confirms its intended upstream."
                    ),
                })

            if classification.kind == "mcpServer" and "mcp" in self.options.families:
                assets["mcpServers"].append(self._mcp_asset(
                    common, raw, api_url, backend_record, backends_by_id, workspace,
                    scope_label, classification, candidate_records,
                ))
            elif classification.kind == "agent" and "a2a" in self.options.families:
                assets["agents"].append(self._agent_asset(common, raw, api_url, backend_record, workspace))
            elif classification.kind == "modelApi" and "models" in self.options.families:
                assets["models"].append(
                    self._model_asset(
                        common, raw, operations, backend_record, backends_by_id, classification,
                        effective, routing_candidates, candidate_records,
                    )
                )
            else:
                excluded.append(
                    _excluded(raw, workspace, classification.reason or "notInRequestedFamilies", classification.signals)
                )

        self._link_tool_projections(assets["mcpServers"], api_index, backends_by_name, backends_by_id, workspace)
        if "models" in self.options.families:
            assets["modelProviders"] = self._model_providers(workspace, shared, assets, api_index)
        _mark_referenced(excluded, assets)
        self.apim_apis.extend(
            _apim_apis(raw_apis, workspace, assets, excluded, self._operations_by_api))
        return assets, excluded

    # ------------------------------------------------------- model providers

    def _model_providers(
        self,
        workspace: str | None,
        shared: dict[str, Any],
        assets: dict[str, list[dict[str, Any]]],
        api_index: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Backends and service URLs that look like an upstream model provider.

        This is the AI Gateway's first building block, and it exists in APIM even
        when no API publishes it -- a backend reached only from a ``send-request``
        or ``set-backend-service`` policy is still a provider that has to move.
        """
        candidates: dict[str, dict[str, Any]] = {}
        roles = self._backend_roles()

        for backend in shared.get("backends", []):
            backend["roles"] = sorted(roles.get(backend["name"], {}))

        for backend in shared.get("backends", []):
            declared_roles = set(backend.get("roles") or [])
            if declared_roles & detect.NON_MODEL_ROLES and not (declared_roles - detect.NON_MODEL_ROLES):
                # A policy says what this backend is for, and it is not serving models.
                self.excluded_backends.append(
                    {
                        "backendId": backend["id"],
                        "name": backend["name"],
                        "url": backend.get("url"),
                        "host": backend.get("host"),
                        "reason": "declaredNonModelRole",
                        "roles": sorted(declared_roles),
                        "declaredBy": roles.get(backend["name"], {}),
                        "usedByAssets": [],
                    }
                )
                continue

            rule = detect.provider_for_url(backend.get("url"))
            is_foundry_ref = "/microsoft.cognitiveservices/accounts/" in (backend.get("resourceIdRef") or "").lower()
            ai_named = detect.is_ai_named_backend(backend.get("name"))
            if not rule and not is_foundry_ref and not ai_named and not backend.get("languageModel"):
                # Record the skip. Without this, a model backend on an unrecognized
                # host with no naming convention would simply be absent, and absence
                # is indistinguishable from "there are no other model providers".
                self.excluded_backends.append(
                    {
                        "backendId": backend["id"],
                        "name": backend["name"],
                        "url": backend.get("url"),
                        "host": backend.get("host"),
                        "reason": "noProviderHostResourceIdNamingOrLanguageModelDeclaration",
                        "usedByAssets": sorted(
                            asset["id"]
                            for asset in assets.get("mcpServers", []) + assets.get("models", [])
                            for target in (asset.get("upstream") or (asset.get("routing") or {}).get("targets") or [])
                            if target.get("backendId") == backend["id"]
                        ),
                    }
                )
                continue
            candidates[backend["id"]] = {
                "origin": {"type": "backend", "backendId": backend["id"], "backendName": backend["name"]},
                "endpoint": backend.get("url"),
                "resourceIdRef": backend.get("resourceIdRef"),
                "rule": rule,
                "foundryRef": is_foundry_ref,
                "declaredProvider": backend.get("provider") or {},
                "languageModel": backend.get("languageModel"),
                "secretRefs": backend.get("secretRefs") or [],
                "credentials": backend.get("credentials"),
                "tls": backend.get("tls"),
                "circuitBreaker": backend.get("circuitBreaker"),
            }

        for asset in assets.get("models", []):
            for target in (asset.get("routing") or {}).get("targets", []):
                key = target.get("backendId") or f"serviceUrl:{target.get('url')}"
                if key in candidates:
                    continue
                rule = detect.provider_for_url(target.get("url"))
                if not rule:
                    continue
                candidates[key] = {
                    "origin": {"type": "serviceUrl", "apiId": asset["source"]["apiId"]},
                    "endpoint": target.get("url"),
                    "resourceIdRef": target.get("resourceIdRef"),
                    "rule": rule,
                    "foundryRef": False,
                    "secretRefs": target.get("secretRefs") or [],
                    "credentials": None,
                    "tls": None,
                    "circuitBreaker": target.get("circuitBreaker"),
                }

        foundry_rule = next(rule for rule in detect.PROVIDERS if rule.kind == "foundry")
        providers: list[dict[str, Any]] = []
        for key, candidate in candidates.items():
            # A candidate reaches here by host match, by a Cognitive Services resource
            # id, or by APIM's AI import naming alone. Only the first two identify the
            # provider; the third says "this is a model backend" and nothing more.
            rule = candidate["rule"] or (foundry_rule if candidate.get("foundryRef") else None)
            # The backend already resolved protocol and catalogue from the import
            # naming; the provider asset must not contradict it.
            declared = candidate.get("declaredProvider") or {}
            name = candidate["origin"].get("backendName") or (urlsplit(candidate["endpoint"] or "").hostname or key)
            record: dict[str, Any] = {
                "id": ids.asset("modelProvider", name, workspace),
                "kind": "modelProvider",
                "workspace": workspace or "default",
                "providerKind": (rule.kind if rule else None) or declared.get("kind") or "unknown",
                "providerLabel": rule.label if rule else declared.get("label"),
                "targetProviderKind": (
                    rule.target_provider_kind if rule else declared.get("targetProviderKind") or "Custom"
                ),
                "apiDialect": declared.get("apiDialect") or (rule.api_dialect if rule else None),
                "endpoint": candidate["endpoint"],
                "origin": candidate["origin"],
                "auth": _provider_auth(
                    candidate, self._provider_resolutions(candidate["origin"], assets), self.registry,
                    secret_by_named_value=self._secret_by_named_value,
                ),
                "tls": candidate["tls"],
                "circuitBreaker": candidate["circuitBreaker"],
                "azure": None,
                "models": {
                    "status": "unresolved",
                    "discoverySource": (rule.catalog if rule else None) or declared.get("catalog") or "unknown",
                    "resolved": [],
                    "notes": [],
                },
                "referencedBy": self._references_to_backend(candidate["origin"].get("backendName"), api_index, workspace),
                "secretRefs": candidate["secretRefs"],
            }
            declaration = candidate.get("languageModel")
            if declaration:
                # The backend states its dialect and model. That declaration wins over
                # the host heuristic and removes any need for catalogue discovery.
                record["providerKind"] = declaration.get("providerKind") or record["providerKind"]
                record["targetProviderKind"] = declaration.get("targetProviderKind") or "Custom"
                record["apiDialect"] = declaration.get("dialect")
                record["declaredByBackend"] = True
                record["models"] = {
                    "status": "declared",
                    "discoverySource": "backendLanguageModel",
                    "resolved": [
                        {
                            "modelName": declaration.get("model"),
                            "apiFormat": declaration.get("apiFormat"),
                            "formatResolution": declaration.get("formatResolution"),
                            "inferenceRoutes": declaration.get("supportedEndpoints"),
                            "target": {
                                "providerKind": declaration.get("targetProviderKind"),
                                "deployment": {"modelName": declaration.get("model")},
                                "supportedEndpoints": declaration.get("supportedEndpoints"),
                            },
                        }
                    ],
                    "notes": [],
                }
                if declaration.get("formatResolution") != "verified":
                    record["models"]["notes"].append(
                        f"apiFormat '{declaration.get('apiFormat')}' was normalized by name rather than "
                        "from a verified mapping. Confirm the target endpoints before registering."
                    )
            elif self.foundry and (detect.is_foundry(rule) or candidate.get("resourceIdRef")):
                account = self.foundry.by_resource_id(candidate.get("resourceIdRef")) or self.foundry.by_url(
                    candidate["endpoint"]
                )
                if account:
                    deployments = self.foundry.load_deployments(account)
                    record["azure"] = {
                        "accountResourceId": account.resource_id,
                        "accountName": account.name,
                        "resourceGroup": account.resource_group,
                        "subscriptionId": account.subscription_id,
                        "location": account.location,
                        "kind": account.kind,
                        "disableLocalAuth": account.disable_local_auth,
                        "publicNetworkAccess": account.public_network_access,
                    }
                    record["models"] = {
                        "status": "resolved" if deployments else "empty",
                        "discoverySource": "armDeployments",
                        "resolved": [
                            resolved_model(account, deployment)
                            for deployment in deployments
                        ],
                        "notes": [account.deployments_error] if account.deployments_error else [],
                    }
                else:
                    record["models"]["notes"].append(
                        "Endpoint resolves to no Cognitive Services account in the scanned subscriptions. "
                        "Pass --foundry-subscription for cross-subscription backends."
                    )
            elif record["models"]["discoverySource"] == "modelsEndpoint":
                record["models"]["notes"].append(
                    f"Run 'migrate-apim resolve-models' to list models from {record['endpoint']}/v1/models "
                    "using the referenced credential, resolved in memory only."
                )
            elif rule:
                record["models"]["notes"].append(
                    f"{rule.label} has no OpenAI-style catalogue endpoint; resolve with '{rule.catalog}' "
                    "or confirm the model set with the operator."
                )
            else:
                record["models"]["notes"].append(
                    f"Host '{record['endpoint']}' matches no known provider. It was treated as a model "
                    "backend because of APIM's AI import naming convention. Confirm the provider and its "
                    "API dialect with the operator before mapping it to a model provider."
                )
            providers.append(record)

        for asset in assets.get("models", []):
            reachable = _api_backend_ids(asset)
            asset["providerIds"] = [
                provider["id"]
                for provider in providers
                if provider["origin"].get("backendId") in reachable
                or provider["origin"].get("apiId") == asset["source"]["apiId"]
            ]
        return providers

    def _backend_roles(self) -> dict[str, dict[str, list[str]]]:
        """What every policy-referenced backend is used for, and where that was declared.

        Maps backend name -> role -> the policy paths asserting it. A role is a
        declaration rather than a guess, so it outranks host-based inference.
        """
        roles: dict[str, dict[str, list[str]]] = {}
        for document in self.policies:
            for element in document.get("elements", []):
                found = detect.backend_roles_from_element(element)
                if not found:
                    continue
                backend_name, role = found
                where = f"{document['id']}#{element['path']}"
                roles.setdefault(backend_name, {}).setdefault(role, [])
                if where not in roles[backend_name][role]:
                    roles[backend_name][role].append(where)
        return roles

    def _provider_resolutions(
        self, origin: dict[str, Any], assets: dict[str, list[dict[str, Any]]]
    ) -> list[policy_mod.Resolution]:
        """What governs every model API that routes to this provider.

        A provider's upstream credential is as often set by the policy of the
        API publishing it as by the backend record -- `authentication-managed-identity`
        on the API is how a hand-built Foundry backend is credentialed, and the
        portal's AI import is the case that writes `credentials.managedIdentity`
        instead. Reading only the backend reported the first shape as having no
        credential at all.

        The reverse of the `providerIds` link above, and deliberately the same
        test: a provider is behind an API when the API can route to its backend,
        or when the provider *is* that API's service URL. Two statements of
        "which provider does this API use" would be free to disagree, so both
        ask `_api_backend_ids` rather than each spelling the test out.
        """
        backend_id = origin.get("backendId")
        api_id = origin.get("apiId")
        resolutions = []
        for asset in assets.get("models") or []:
            reachable = _api_backend_ids(asset)
            asset_api = asset["source"]["apiId"]
            if not ((backend_id is not None and backend_id in reachable)
                    or (api_id is not None and api_id == asset_api)):
                continue
            resolution = self._effective_by_api.get(asset_api)
            if resolution is not None:
                resolutions.append(resolution)
        return resolutions

    def _references_to_backend(
        self, backend_name: str | None, api_index: dict[str, dict[str, Any]], workspace: str | None
    ) -> dict[str, Any]:
        """Who points at this backend: APIs by ``backendId``, and policies by attribute."""
        references: dict[str, Any] = {"apis": [], "policies": [], "expressions": []}
        if not backend_name:
            return references
        for name, raw in api_index.items():
            if ((raw.get("properties") or {}).get("backendId")) == backend_name:
                references["apis"].append(ids.api(name or "", workspace))
        for document in self.policies:
            for element in document.get("elements", []):
                haystack = [value for value in element.get("attributes", {}).values() if isinstance(value, str)]
                if isinstance(element.get("text"), str):
                    haystack.append(element["text"])
                if any(backend_name in value for value in haystack):
                    references["policies"].append(
                        {"policyId": document["id"], "path": element["path"], "element": element["name"]}
                    )
            # A backend id assembled inside a policy expression is invisible to a
            # textual scan, so expressions are searched too and flagged separately.
            for expression in document.get("expressions", []):
                if backend_name in (expression.get("source") or ""):
                    references["expressions"].append(
                        {"policyId": document["id"], "expressionId": expression["id"]}
                    )
        references["basis"] = {
            "method": "substringScanOfPolicyAttributesTextAndExpressions",
            "caveat": (
                "A backend referenced only through a value computed at runtime cannot be "
                "found by this scan. No references found is weak evidence of an unused "
                "backend, not proof of one."
            ),
        }
        return references

    def _link_tool_projections(
        self,
        mcp_assets: list[dict[str, Any]],
        api_index: dict[str, dict[str, Any]],
        backends_by_name: dict[str, dict[str, Any]],
        backends_by_id: dict[str, dict[str, Any]],
        workspace: str | None,
    ) -> None:
        """Resolve a tool-projected MCP server's real upstream through its source API."""
        for asset in mcp_assets:
            if asset.get("pattern") != "toolProjection" or asset.get("upstream"):
                continue
            source_names = sorted({tool["sourceApi"] for tool in asset.get("tools", []) if tool.get("sourceApi")})
            upstream: list[dict[str, Any]] = []
            for source_name in source_names:
                source = api_index.get(source_name)
                if not source:
                    asset.setdefault("notes", []).append(
                        f"Tools project from API '{source_name}', which was not returned by this collection."
                    )
                    continue
                source_props = source.get("properties") or {}
                # The source API routes the tool calls, so a runtime choice in
                # *its* policy is this server's upstream just as much as a
                # declared backend is. Dropping the candidates here reported a
                # projected server as having no upstream at all.
                resolution = self._effective_by_api.get(ids.api(source_name, workspace))
                record, source_candidates = _resolve_backend(
                    source_props, backends_by_name, backends_by_id, workspace,
                    resolution.elements if resolution else None,
                )
                for target in _routing_targets(
                    record, backends_by_id, source_props.get("serviceUrl"),
                    candidates=_candidate_records(
                        source_candidates, backends_by_name, backends_by_id, workspace
                    ),
                ):
                    upstream.append({**target, "viaApi": ids.api(source_name, workspace), "transport": "http"})
            asset["upstream"] = upstream
            asset["sourceApiIds"] = [ids.api(name, workspace) for name in source_names]

    def _collect_operations(self, api_url: str, name: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{api_url}/operations", "operations", f"{scope}/api:{name}", quiet=True)
        operations = []
        # APIM exposes no bulk read for operation policies, so collecting them
        # costs one round trip per operation -- 110 of 171 reads on a single real
        # instance, nearly all returning 404. It is off by default and the skip is
        # recorded, because "not collected" must not read as "none exist".
        collect_policies = self.options.operation_policies
        if not collect_policies and raw:
            self.coverage.append(
                _coverage("operationPolicies", f"{scope}/api:{name}", "notCollected", len(raw), None)
            )
        for entry in raw:
            props = entry.get("properties") or {}
            operation_name = entry.get("name") or ""
            policy_id = ids.policy("operation", f"{ids.scoped(workspace, name)}/{operation_name}")
            document = None
            if collect_policies:
                document = self._capture_policy(
                    scope={
                        "level": "operation",
                        "name": operation_name,
                        "apiName": name,
                        "workspace": workspace or "default",
                        "resourceId": entry.get("id"),
                    },
                    scope_url=f"{api_url}/operations/{operation_name}",
                    policy_id=policy_id,
                    quiet=True,
                )
            operations.append(
                {
                    "name": operation_name,
                    "displayName": props.get("displayName"),
                    "method": props.get("method"),
                    "urlTemplate": props.get("urlTemplate") or "",
                    "description": props.get("description"),
                    "policyId": policy_id if document else None,
                }
            )
        return operations

    # -------------------------------------------------------------- assets

    def _model_asset(
        self,
        common: dict[str, Any],
        raw: dict[str, Any],
        operations: list[dict[str, Any]],
        backend_record: dict[str, Any] | None,
        backends_by_id: dict[str, dict[str, Any]],
        classification: detect.Classification,
        effective: policy_mod.Resolution,
        routing_candidates: list[str] | None = None,
        candidate_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        props = raw.get("properties") or {}
        targets = _routing_targets(
            backend_record, backends_by_id, props.get("serviceUrl"),
            candidates=candidate_records,
        )
        provider_rule = classification.provider
        endpoint = targets[0]["url"] if targets else props.get("serviceUrl")

        # The backend record already resolved the provider from host and import
        # naming; prefer it over the classifier's host-only view so an API whose
        # host matches nothing still reports its protocol instead of "unknown".
        resolved = (backend_record or {}).get("provider") or {}
        provider: dict[str, Any] = {
            "kind": (provider_rule.kind if provider_rule else None) or resolved.get("kind") or "unknown",
            "label": (provider_rule.label if provider_rule else None) or resolved.get("label"),
            "apiDialect": resolved.get("apiDialect") or (provider_rule.api_dialect if provider_rule else None),
            "targetProviderKind": (
                provider_rule.target_provider_kind if provider_rule
                else resolved.get("targetProviderKind") or "Custom"
            ),
            "basis": resolved.get("basis") or ("backendHost" if provider_rule else None),
            "protocolBasis": resolved.get("protocolBasis"),
            "endpoint": endpoint,
            "auth": _backend_auth(
                backend_record, effective, self.registry,
                secret_by_named_value=self._secret_by_named_value,
            ),
            "azure": None,
        }

        catalog = (provider_rule.catalog if provider_rule else None) or resolved.get("catalog")
        models: dict[str, Any] = {
            "status": "unresolved",
            "discoverySource": catalog or "unknown",
            "resolved": [],
            "declared": sorted(_declared_models(operations, effective.elements)),
            "notes": [],
        }

        # A languageModel backend names its model and dialect, so there is nothing
        # to discover and nothing to ask the operator.
        declarations = [target["languageModel"] for target in targets if target.get("languageModel")]
        if declarations:
            models["status"] = "declared"
            models["discoverySource"] = "backendLanguageModel"
            models["resolved"] = [
                {
                    "modelName": declaration.get("model"),
                    "apiFormat": declaration.get("apiFormat"),
                    "formatResolution": declaration.get("formatResolution"),
                    "inferenceRoutes": declaration.get("supportedEndpoints"),
                    "target": {
                        "providerKind": declaration.get("targetProviderKind"),
                        "deployment": {"modelName": declaration.get("model")},
                        "supportedEndpoints": declaration.get("supportedEndpoints"),
                    },
                }
                for declaration in declarations
            ]
            inferred = [d for d in declarations if d.get("formatResolution") != "verified"]
            if inferred:
                models["notes"].append(
                    "Backend apiFormat values "
                    + ", ".join(sorted({str(d.get("apiFormat")) for d in inferred}))
                    + " were normalized by name rather than from a verified mapping. Confirm the "
                    "target endpoints before registering these models."
                )
            provider["targetProviderKind"] = declarations[0].get("targetProviderKind") or "Custom"
            provider["apiDialect"] = declarations[0].get("dialect")
            provider["kind"] = declarations[0].get("providerKind") or provider["kind"]
            provider["declaredByBackend"] = True
        elif self.foundry and detect.is_foundry(provider_rule):
            # Every target, not just the first. A load-balanced API routes to a
            # pool of accounts, and stopping at one reported its models as the
            # API's whole catalogue while the other members -- and the weights
            # that split traffic between them -- went missing entirely.
            resolved: list[dict[str, Any]] = []
            account = None
            for target in targets:
                member = (self.foundry.by_resource_id(target.get("resourceIdRef"))
                          or self.foundry.by_url(target.get("url")))
                if not member:
                    continue
                account = account or member
                deployments = self.foundry.load_deployments(member)
                for deployment in deployments:
                    resolved.append(resolved_model(
                        member, deployment,
                        # Which member serves it, and on what share of traffic.
                        # One alias fronts the same model across members, so the
                        # registration has to say where each copy lives.
                        backendId=target.get("backendId"),
                        poolPriority=target.get("priority"),
                        poolWeight=target.get("weight"),
                    ))
                if member.deployments_error:
                    models["notes"].append(member.deployments_error)
            if account:
                provider["azure"] = {
                    "accountResourceId": account.resource_id,
                    "accountName": account.name,
                    "resourceGroup": account.resource_group,
                    "subscriptionId": account.subscription_id,
                    "location": account.location,
                    "kind": account.kind,
                    "disableLocalAuth": account.disable_local_auth,
                    "publicNetworkAccess": account.public_network_access,
                }
                models["status"] = "resolved" if resolved else "empty"
                models["discoverySource"] = "armDeployments"
                models["resolved"] = resolved
            else:
                models["notes"].append(
                    "Backend looks like an Azure AI Foundry endpoint but no matching Cognitive Services "
                    "account was found in the scanned subscriptions. Pass --foundry-subscription."
                )
        elif catalog == "modelsEndpoint":
            models["discoverySource"] = "modelsEndpoint"
            models["notes"].append(
                f"{provider.get('label') or provider.get('kind')} speaks the OpenAI protocol, so its "
                f"model list is one GET away at {endpoint or '<endpoint>'}/v1/models with the backend "
                "credential. Run 'migrate-apim resolve-models' to fetch it without persisting the key."
            )
        elif provider_rule:
            models["notes"].append(
                f"{provider_rule.label} does not expose an OpenAI-style model list. Resolve it with "
                f"'{provider_rule.catalog}' out of band, or confirm the model set with the operator."
            )
        else:
            models["notes"].append(
                "Provider could not be inferred from the backend URL. Confirm the upstream with the operator."
            )

        dialects = detect.api_dialect_for_paths([operation["urlTemplate"] for operation in operations])
        backend_dialects = sorted({d["dialect"] for d in declarations if d.get("dialect")})
        translation = _translation(dialects, backend_dialects, operations)
        return {
            **common,
            "kind": "modelApi",
            "pattern": classification.pattern,
            "provider": provider,
            "routing": {
                "mode": (
                    "pool" if (backend_record or {}).get("type") == "Pool"
                    else "conditional" if routing_candidates
                    else "single" if targets else "policy"
                ),
                "targets": targets,
                "circuitBreaker": (backend_record or {}).get("circuitBreaker"),
                "evidence": (backend_record or {}).get("id") or "serviceUrl",
                # Pool behaviour the plan has to account for. Held only on the
                # raw backend before, where nothing downstream could see it, so
                # a pool pinning sessions to a backend migrated as if it did not.
                "sessionAffinity": ((backend_record or {}).get("pool") or {}).get("sessionAffinity"),
                "failureResponse": ((backend_record or {}).get("pool") or {}).get("failureResponse"),
                # Several set-backend-service elements mean the upstream is
                # picked at runtime. Naming them beats reporting no backend,
                # which is what an unread policy used to look like.
                "candidates": routing_candidates or [],
            },
            "models": models,
            "supportingBackends": _supporting_backends(effective, workspace=common["workspace"]),
            "endpoints": {
                # Inferred from operation URL templates, which operators configure
                # freely; the backend side is declared by the backend itself.
                "inboundDialects": dialects,
                "inboundDialectsInferredFrom": "operationTemplates",
                "backendDialects": backend_dialects,
                "backendDialectsDeclared": bool(backend_dialects),
                "translation": translation,
                # How much of what this API publishes the target can publish at
                # all. AI Gateway exposes four inference routes; everything else
                # an APIM API fronts has no target, so this is the input to the
                # scope decision rather than a detail.
                "surface": detect.summarize_surface(
                    [operation["urlTemplate"] for operation in operations]
                ),
                "operations": operations,
                "basePath": props.get("path"),
            },
        }

    def _mcp_asset(
        self,
        common: dict[str, Any],
        raw: dict[str, Any],
        api_url: str,
        backend_record: dict[str, Any] | None,
        backends_by_id: dict[str, dict[str, Any]],
        workspace: str | None,
        scope: str,
        classification: detect.Classification,
        candidate_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        props = raw.get("properties") or {}
        mcp_props = props.get("mcpProperties") or {}
        pattern = classification.pattern

        tools: list[dict[str, Any]] = []
        for entry in self._list(f"{api_url}/tools", "tools", f"{scope}/api:{raw.get('name')}", quiet=True):
            tool_props = entry.get("properties") or {}
            tools.append(
                {
                    "name": tool_props.get("displayName"),
                    "description": tool_props.get("description"),
                    "origin": "operation",
                    "operationId": tool_props.get("operationId"),
                    "sourceApi": ids.arm_segment(tool_props.get("operationId") or "", "apis"),
                    "sourceOperation": ids.arm_name(tool_props.get("operationId") or ""),
                    "hasToolPolicy": bool(tool_props.get("policies")),
                }
            )
        for entry in props.get("mcpTools") or []:
            name = entry.get("name")
            if any(tool["name"] == name for tool in tools):
                continue
            tools.append(
                {
                    "name": name,
                    "description": entry.get("description"),
                    "origin": "operation",
                    "operationId": entry.get("operationId"),
                    "sourceApi": ids.arm_segment(entry.get("operationId") or "", "apis"),
                    "sourceOperation": ids.arm_name(entry.get("operationId") or ""),
                    "hasToolPolicy": False,
                }
            )

        transport = _mcp_transport(mcp_props)
        upstream = []
        for target in _routing_targets(
            backend_record, backends_by_id, props.get("serviceUrl"),
            candidates=candidate_records,
        ):
            upstream.append(
                {
                    **target,
                    "transport": transport["value"],
                    "transportBasis": {k: v for k, v in transport.items() if k != "value"},
                    "mcpPath": _mcp_path(mcp_props),
                }
            )

        source_api_names = sorted({tool["sourceApi"] for tool in tools if tool.get("sourceApi")})
        openapi = None
        if pattern == "toolProjection" and source_api_names:
            openapi = [
                {
                    "apiName": api_name,
                    "exportRecipe": {
                        "method": "armRead",
                        "request": {
                            "httpMethod": "GET",
                            "url": (
                                f"https://management.azure.com{self._scope_url(workspace)}/apis/{api_name}"
                                f"?api-version={self.api_version}&export=true&format=openapi%2Bjson-link"
                            ),
                        },
                        "command": (
                            f'az rest --method get --url "https://management.azure.com{self._scope_url(workspace)}'
                            f'/apis/{api_name}?api-version={self.api_version}&export=true&format=openapi%2Bjson-link"'
                            " --query link --output tsv"
                        ),
                        "valuePath": "$.link",
                        "note": (
                            "Returns a short-lived SAS link to the OpenAPI document; the link itself is a "
                            "credential, so fetch and use it immediately and never persist it. An AI Gateway "
                            "tool server consumes the document as an 'openApi' source, inline or by URL."
                        ),
                    },
                }
                for api_name in source_api_names
            ]

        return {
            **common,
            "kind": "mcpServer",
            "pattern": pattern,
            "mcp": {
                "transportType": mcp_props.get("transportType"),
                "endpoints": mcp_props.get("endpoints"),
                "isFederationRouter": mcp_props.get("isFederationRouter"),
                "federation": mcp_props.get("federation"),
            },
            "upstream": upstream,
            "tools": tools,
            "toolCount": len(tools),
            "toolDiscovery": _tool_discovery(pattern, tools, props),
            "openApiSources": openapi,
        }

    def _agent_asset(
        self,
        common: dict[str, Any],
        raw: dict[str, Any],
        api_url: str,
        backend_record: dict[str, Any] | None,
        workspace: str | None,
    ) -> dict[str, Any]:
        props = raw.get("properties") or {}
        a2a_props = props.get("a2aProperties") or {}
        json_rpc = props.get("jsonRpcProperties") or {}

        # An A2A API carries its upstream in jsonRpcProperties rather than in a
        # backend or serviceUrl, so the usual backend resolution finds nothing.
        upstream: list[dict[str, Any]] = []
        rpc_url = _ci_get(json_rpc, "BackendUrl")
        if rpc_url:
            upstream.append(
                {
                    "backendId": None,
                    "url": rpc_url,
                    "transport": "jsonRpc",
                    "path": _ci_get(json_rpc, "Path"),
                    "source": "jsonRpcProperties",
                }
            )
        backend_url = (backend_record or {}).get("url") or props.get("serviceUrl")
        if backend_url:
            upstream.append(
                {
                    "backendId": (backend_record or {}).get("id"),
                    "url": backend_url,
                    "transport": "http",
                    "source": "backend" if backend_record else "serviceUrl",
                }
            )

        card_url = a2a_props.get("agentCardBackendUrl")
        hosting = self._agent_hosting(rpc_url or card_url)
        return {
            **common,
            "kind": "agent",
            "pattern": "a2a",
            "agent": {
                "id": (props.get("agent") or {}).get("id"),
                "name": (props.get("agent") or {}).get("name"),
                "providerName": (props.get("agent") or {}).get("providerName"),
                "managementPortalUrl": (props.get("agent") or {}).get("managementPortalUrl"),
            },
            "agentCard": {
                "backendUrl": card_url,
                "exposedPath": a2a_props.get("agentCardPath"),
                "discovery": {
                    "status": "runtimeOnly",
                    "note": (
                        "APIM stores the agent card's URL, not its content. The card's skills, "
                        "capabilities, and security schemes need a runtime fetch of this URL with "
                        "credentials the collector deliberately does not use."
                    ),
                },
            },
            "hosting": hosting,
            "upstream": upstream,
            "a2a": {
                "a2aProperties": props.get("a2aProperties"),
                "agent": props.get("agent"),
                "jsonRpcProperties": props.get("jsonRpcProperties"),
                "isAgent": props.get("isAgent"),
            },
            "note": (
                "Azure AI Gateway does not yet expose an A2A building block. This asset is inventoried "
                "so the gap is explicit and the configuration survives until support ships."
            ),
        }

    def _agent_hosting(self, url: str | None) -> dict[str, Any]:
        """Identify a Foundry-hosted agent and resolve its account.

        A Foundry agent endpoint looks like
        ``https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent>/…``,
        so the hosting project and the ARM account behind it are recoverable.
        """
        hosting: dict[str, Any] = {"kind": "unknown", "endpoint": url}
        if not url:
            return hosting
        rule = detect.provider_for_url(url)
        match = _FOUNDRY_AGENT_PATH.search(url)
        if match:
            hosting["project"] = match.group("project")
            hosting["agentId"] = match.group("agent")
        if not detect.is_foundry(rule):
            hosting["kind"] = rule.kind if rule else "external"
            return hosting
        hosting["kind"] = "foundry"
        account = self.foundry.by_url(url) if self.foundry else None
        if account:
            hosting["azure"] = {
                "accountResourceId": account.resource_id,
                "accountName": account.name,
                "resourceGroup": account.resource_group,
                "subscriptionId": account.subscription_id,
                "location": account.location,
                "kind": account.kind,
            }
        else:
            hosting["note"] = (
                "Host looks like Azure AI Foundry but no matching Cognitive Services account was "
                "found in the scanned subscriptions. Pass --foundry-subscription."
            )
        return hosting

    # ------------------------------------------------------------- helpers

    def _access(
        self, raw: dict[str, Any], name: str, workspace: str | None, shared: dict[str, Any]
    ) -> dict[str, Any]:
        props = raw.get("properties") or {}
        api_id = ids.api(name, workspace)
        products = [product["id"] for product in shared.get("products", []) if api_id in product["apiIds"]]
        api_resource_id = (raw.get("id") or "").lower()
        subscriptions = []
        for entry in shared.get("subscriptions", []):
            scope = entry["scope"]
            if scope["level"] == "service":
                subscriptions.append({"id": entry["id"], "via": "service"})
            elif scope["level"] == "allApis":
                subscriptions.append({"id": entry["id"], "via": "allApis"})
            elif scope["level"] == "api" and (scope.get("resourceId") or "").lower() == api_resource_id:
                subscriptions.append({"id": entry["id"], "via": "api"})
            elif scope["level"] == "product" and ids.product(scope.get("name") or "", workspace) in products:
                subscriptions.append({"id": entry["id"], "via": "product"})
        return {
            "subscriptionRequired": props.get("subscriptionRequired"),
            "subscriptionKeyParameterNames": props.get("subscriptionKeyParameterNames"),
            "authenticationSettings": props.get("authenticationSettings"),
            "productIds": products,
            "subscriptions": subscriptions,
        }


    def _capture_policy(
        self,
        *,
        scope: dict[str, Any],
        scope_url: str,
        policy_id: str,
        quiet: bool = False,
    ) -> dict[str, Any] | None:
        try:
            raw = self.client.get_policy(scope_url, self.api_version)
        except ArmAuthError:
            raise
        except ArmError as exc:
            if not quiet:
                self.warnings.append({"code": "policyRead", "scope": policy_id, "message": str(exc)})
            return None
        if not raw or not raw.get("value"):
            return None
        document = policy_mod.parse(
            raw.get("value") or "",
            policy_id=policy_id,
            scope=scope,
            scope_url=scope_url,
            registry=self.registry,
        )
        self._add_policy(document)
        return document

    def _add_policy(self, document: dict[str, Any]) -> None:
        if document["id"] in self._policy_index:
            return
        self._policy_index[document["id"]] = document
        self.policies.append(document)
        self._graph.add(document)

    def _get(
        self, url: str, collection: str, scope: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        try:
            resp = self.client.request("GET", url, api_version=self.api_version, params=params)
        except ArmAuthError:
            raise
        except ArmError as exc:
            self.coverage.append(_coverage(collection, scope, "failed", 0, str(exc)))
            return None
        if resp.status == 404:
            self.coverage.append(_coverage(collection, scope, "notFound", 0, None))
            return None
        if not resp.ok:
            self.coverage.append(_coverage(collection, scope, "failed", 0, f"{resp.status}: {resp.text[:200]}"))
            return None
        self.coverage.append(_coverage(collection, scope, "complete", 1, None))
        return resp.body if isinstance(resp.body, dict) else None

    def _list(
        self, url: str, collection: str, scope: str, *, quiet: bool = False,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            items = self.client.list(url, self.api_version, **(params or {}))
        except ArmAuthError:
            raise
        except ArmError as exc:
            self.coverage.append(_coverage(collection, scope, "failed", 0, str(exc)))
            if not quiet:
                self.warnings.append({"code": "collectionRead", "collection": collection, "scope": scope, "message": str(exc)})
            return []
        self.coverage.append(_coverage(collection, scope, "complete" if items else "empty", len(items), None))
        self.progress(f"{collection}@{scope}: {len(items)} ({self.client.call_count} reads)")
        return items


# ---------------------------------------------------------------- utilities


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _coverage(collection: str, scope: str, status: str, count: int, error: str | None) -> dict[str, Any]:
    return {"collection": collection, "scope": scope, "status": status, "count": count, "error": error}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _merge_shared(target: dict[str, Any], scope: dict[str, Any]) -> None:
    for key, value in scope.items():
        if isinstance(value, list):
            target.setdefault(key, []).extend(value)
        elif isinstance(value, dict):
            existing = target.setdefault(key, {})
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, list):
                    existing.setdefault(sub_key, []).extend(sub_value)
                else:
                    existing[sub_key] = sub_value
        else:
            target[key] = value


def _service_source(raw: dict[str, Any], *, subscription_id: str = "",
                    resource_group: str = "") -> dict[str, Any]:
    """The APIM service as ARM returns it.

    Split out for the reason `_api_source` is: it is the one place the service's
    own fields are written down, so `compile` can ask it what APIM returns
    rather than ask a schema we wrote and could have widened by hand.
    """
    props = raw.get("properties") or {}
    identity = raw.get("identity") or {}
    user_assigned = identity.get("userAssignedIdentities") or {}
    return {
        "resourceId": raw.get("id"),
        "name": raw.get("name"),
        "location": raw.get("location"),
        "subscriptionId": subscription_id,
        "resourceGroup": resource_group,
        "sku": raw.get("sku"),
        "provisioningState": props.get("provisioningState"),
        "gatewayUrl": props.get("gatewayUrl"),
        "managementApiUrl": props.get("managementApiUrl"),
        "developerPortalUrl": props.get("developerPortalUrl"),
        "virtualNetworkType": props.get("virtualNetworkType"),
        "publicNetworkAccess": props.get("publicNetworkAccess"),
        "publicIPAddresses": props.get("publicIPAddresses"),
        "privateIPAddresses": props.get("privateIPAddresses"),
        "hostnameConfigurations": [
            {
                "type": entry.get("type"),
                "hostName": entry.get("hostName"),
                "certificateSource": entry.get("certificateSource"),
                "keyVaultId": entry.get("keyVaultId"),
                "identityClientId": entry.get("identityClientId"),
            }
            for entry in (props.get("hostnameConfigurations") or [])
        ],
        "identity": {
            "type": identity.get("type"),
            "principalId": identity.get("principalId"),
            "tenantId": identity.get("tenantId"),
            "userAssignedIdentities": [
                {"resourceId": key, "clientId": (value or {}).get("clientId")}
                for key, value in user_assigned.items()
            ],
        },
        "tags": raw.get("tags") or {},
    }


def api_readings(asset: dict[str, Any]) -> dict[str, Any]:
    """The scalar readings of an API that a rule narrows on.

    The evidence each summarises is this tool's -- a catalogue resolved from
    CognitiveServices deployments, a dialect comparison, a tool list fetched at
    runtime -- but what each is *about* is the API, which is APIM's.

    Rendered here rather than inline because the asset they read can be
    rewritten after collection: see `refresh_api_readings`.
    """
    catalogue = asset.get("models") or {}
    translation = (asset.get("endpoints") or {}).get("translation") or {}
    discovery = asset.get("toolDiscovery") or {}
    return {
        "catalogueFetched": bool(catalogue.get("catalogue")),
        "discoverySource": catalogue.get("discoverySource"),
        "translation": translation.get("status"),
        "toolDiscovery": discovery.get("status"),
        "toolsFromGateway": discovery.get("policiesApplied"),
    }


def refresh_api_readings(inventory: dict[str, Any]) -> dict[str, Any]:
    """Re-render `apim.apis[]`'s readings from the assets they summarise.

    "One reading, rendered once, so there is nothing to drift" held only until
    something rewrote an asset after collection -- and `resolve-models` and
    `discover-tools`, the two commands the skill requires, do exactly that.
    They updated the asset and left the copy saying what was true before they
    ran: a provider whose catalogue had just been fetched still read
    `catalogueFetched: false`, and a server whose tools had just been listed
    still read `toolDiscovery: runtimeOnly`.

    Nothing selected on the stale value yet, because the planner reads the
    asset. That is the whole danger: the vocabulary those commits introduced
    for rules to narrow on was wrong, and the first rule to use it would have
    been wrong with it, silently.
    """
    assets = (inventory.get("assets") or {})
    by_id = {
        asset["id"]: asset
        for family in assets.values() if isinstance(family, list)
        for asset in family if isinstance(asset, dict) and asset.get("id")
    }
    for row in (inventory.get("apim") or {}).get("apis") or []:
        asset = by_id.get(row.get("assetId"))
        if asset:
            row.update(api_readings(asset))
    return inventory


def _apim_apis(
    raw_apis: list[dict[str, Any]],
    workspace: str | None,
    assets: dict[str, list[dict[str, Any]]],
    excluded: list[dict[str, Any]],
    operations_by_api: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Every API APIM has in this scope, and what this tool made of each.

    Answering "which APIs are on this service" took a union of five lists --
    three asset families plus `excludedApis`, with model providers in a fourth
    that has no API behind it at all. That is a question APIM can answer in one
    call, so the inventory should answer it in one place.

    The fields are `_api_source`'s, called here rather than copied: both this
    and the `source` block on each asset come out of the one function, so there
    is no second description of an API to drift from the first. What is added is
    only the pair that cannot be read off APIM -- which asset the API became, or
    why it became none. Exactly one of the two is set.
    """
    became = {
        (asset.get("source") or {}).get("apiId"): asset
        for family in assets.values()
        for asset in family
        if (asset.get("source") or {}).get("apiId")
    }
    # Read after `_mark_referenced`, so an API kept as a dependency carries the
    # reason it was kept rather than the one it was first set aside for.
    reasons = {entry["apiId"]: entry["reason"] for entry in excluded}
    rows = []
    for raw in raw_apis:
        source = _api_source(raw, workspace)
        asset = became.get(source["apiId"])
        row = {
            **source,
            "workspace": workspace or "default",
            "subscriptionRequired": (raw.get("properties") or {}).get("subscriptionRequired"),
            "assetId": asset["id"] if asset else None,
            "role": _ROLE_OF.get((asset or {}).get("kind"), "excluded"),
            "pattern": (asset or {}).get("pattern"),
            "excludedReason": reasons.get(source["apiId"]),
        }
        # APIM returns operations, so the spine carries them. Each is APIM's
        # record plus two readings of its `urlTemplate`, named as readings:
        # `group` is which inference route it looks like, `publishable` whether
        # the target has that route at all.
        # Scalar readings of the API, for a rule to narrow on. The evidence they
        # summarise is this tool's -- a catalogue resolved from CognitiveServices
        # deployments, a dialect comparison, a tool list fetched at runtime --
        # but what each is *about* is the API, which is APIM's. So the subject of
        # the rule is the APIM object and the reading is a `where` key, which is
        # the same shape `type` and `pattern` already have.
        if asset:
            row.update(api_readings(asset))
        row["operations"] = [
            {**operation, **_operation_reading(operation.get("urlTemplate") or "")}
            for operation in operations_by_api.get(source["apiId"]) or []
        ]
        rows.append(row)
    return rows


# APIM's `properties.type` says what kind of API it is; `role` is this tool's
# word for the same thing after classification, because an http-typed API can
# still be a model API and APIM has no field that says so.
_ROLE_OF = {"modelApi": "modelApi", "mcpServer": "mcpServer", "agent": "agent"}

# Which keys on an `apim.*` object this tool worked out rather than read from
# ARM. Declared here, beside the code that produces them, because the checker
# that uses it must not be a second list that can drift.
#
# The rule it encodes: a reading may be a `where` key, never a path segment.
# `apim.apis[]` narrowed on `pattern` is honest -- an APIM object, this tool's
# reading of it, and a reader can tell which is which. `apim.apis[].endpoints`
# was not: `endpoints` is a decomposition of ours, and putting it in the path
# made a whole structure of this tool's read as though APIM returned it.
APIM_READINGS = {
    "service": ("networking", "needsSubnet"),
    "apim.apis[]": ("role", "pattern", "catalogueFetched", "discoverySource", "translation",
                    "toolDiscovery", "toolsFromGateway"),
    "apim.apis[].operations[]": ("group", "publishable", "route", "subresource", "template"),
}


def _operation_reading(url_template: str) -> dict[str, Any]:
    """This tool's reading of an operation's template, on APIM's own record.

    A reading is allowed to sit on an APIM object as long as it is named as one
    -- `type` is APIM's, `group` and `publishable` are ours, and a rule can
    narrow on either. What is not allowed is a whole decomposition of ours
    hanging off an APIM path: `apim.apis[].endpoints.surface` read as though
    APIM had an `endpoints` property, which it does not.
    """
    classified = detect.classify_operation(url_template)
    return {"group": classified["group"], "publishable": classified["publishable"]}


def _api_source(raw: dict[str, Any], workspace: str | None) -> dict[str, Any]:
    props = raw.get("properties") or {}
    return {
        "apiId": ids.api(raw.get("name") or "", workspace),
        "name": raw.get("name"),
        "resourceId": raw.get("id"),
        "displayName": props.get("displayName"),
        "description": props.get("description"),
        "type": props.get("type") or "http",
        "path": props.get("path"),
        "effectivePath": props.get("effectivePath"),
        "protocols": props.get("protocols"),
        "serviceUrl": props.get("serviceUrl"),
        "backendId": props.get("backendId"),
        "apiRevision": props.get("apiRevision"),
        "apiVersion": props.get("apiVersion"),
        "apiVersionSetId": props.get("apiVersionSetId"),
        "isCurrent": props.get("isCurrent"),
        "accessState": props.get("accessState"),
    }


def _excluded(
    raw: dict[str, Any], workspace: str | None, reason: str, signals: list[detect.Signal]
) -> dict[str, Any]:
    props = raw.get("properties") or {}
    return {
        "apiId": ids.api(raw.get("name") or "", workspace),
        "name": raw.get("name"),
        "displayName": props.get("displayName"),
        "type": props.get("type") or "http",
        "path": props.get("path"),
        "reason": reason,
        "signals": [signal.to_dict() for signal in signals],
    }


def _asset_prefix(kind: str) -> str:
    return {"modelApi": "model", "mcpServer": "mcp", "agent": "agent"}.get(kind, "api")


def policy_routed_backends(elements: list[dict[str, Any]] | None) -> list[str]:
    """Backends a ``set-backend-service`` policy routes this API to.

    An API can name its backend in ``properties.backendId`` or leave it to
    policy. The import wizard writes both for a single upstream, so reading only
    the property worked until an API load-balanced across accounts: its backend
    is a pool, which ``properties.backendId`` never carries. Those APIs resolved
    to no backend at all, so a pool of Foundry accounts read as an API with no
    provider and no targets.
    """
    names: list[str] = []
    for element in elements or []:
        named = detect.backend_roles_from_element(element)
        if named and named[1] == "routing" and named[0] not in names:
            names.append(named[0])
    return names


def _resolve_backend(
    props: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    workspace: str | None,
    elements: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """The backend this API routes to, and any candidates left unresolved.

    Several ``set-backend-service`` elements mean the backend is chosen at
    runtime -- inside a ``choose``, typically. Picking the first would state a
    route nobody configured, so none is returned and all the candidates are
    reported instead.
    """
    backend_id = props.get("backendId")
    if backend_id:
        return by_name.get(backend_id) or by_id.get(ids.backend(backend_id, workspace)), []

    candidates = policy_routed_backends(elements)
    if len(candidates) != 1:
        return None, candidates
    name = candidates[0]
    return by_name.get(name) or by_id.get(ids.backend(name, workspace)), []


def _candidate_records(
    names: list[str] | None,
    by_name: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    workspace: str | None,
) -> list[dict[str, Any]]:
    """The backend records behind the names `_resolve_backend` reported.

    An API that picks its upstream at runtime reports candidates instead of a
    route, and those are what it reaches. Everything that reads a backend has
    to see them -- the provider classification, the model catalogue, the alias
    members, an MCP server's upstream -- or a conditionally routed API is
    analysed as one with no backend at all.

    A name that resolves to no record is dropped rather than carried as None:
    `set-backend-service` names a backend by id, and one APIM does not have is
    a dangling reference in the source, not an upstream to report.
    """
    return [
        record for record in (
            by_name.get(name) or by_id.get(ids.backend(name, workspace))
            for name in names or ()
        ) if record
    ]


def _raw_backend(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {"properties": {"url": record.get("url"), "resourceId": record.get("resourceIdRef")}}


def _backend_urls(
    record: dict[str, Any] | None,
    by_id: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]] | None = None,
) -> list[str]:
    if not record:
        # What the API reaches when it picks at runtime. `classify_api` reads
        # these to recognise a model provider by host, so without them a
        # conditionally routed API was classified with no backend evidence and
        # its provider came back "unknown".
        return [member["url"] for member in (candidates or []) if member.get("url")]
    urls = [record.get("url")] if record.get("url") else []
    for item in ((record.get("pool") or {}).get("services") or []):
        member = by_id.get(item["backendId"])
        if member and member.get("url"):
            urls.append(member["url"])
    return [url for url in urls if url]


def _api_backend_ids(asset: dict[str, Any]) -> set[str]:
    """Every backend this API can send a request to, however it chooses.

    Both halves of the provider link ask this -- `providerIds` forward and
    `_provider_resolutions` back -- because the two are only trustworthy while
    they are the same test, and two copies of a comprehension are not.

    `targets` is the backend the API resolves to. `candidates` is the set it
    picks from at runtime, which `_resolve_backend` reports instead of a target
    whenever the `set-backend-service` count is not exactly one. Reading only
    `targets` left a conditionally routed API linked to no provider at all, so
    the policy carrying its upstream credential was never consulted for the
    backends that policy itself names.

    A candidate is an alternative rather than a confirmed route, and it stays
    one: this returns what the API *can* reach, and `_backend_auth` is where
    several alternatives become `identityCandidates` rather than a silent pick.
    Candidates are recorded as bare backend names, so they are scoped to the
    asset's workspace to match the ids `targets` carries.
    """
    routing = asset.get("routing") or {}
    workspace = asset.get("workspace")
    reachable = {
        target.get("backendId")
        for target in routing.get("targets") or []
        if target.get("backendId")
    }
    reachable |= {
        ids.backend(name, workspace) for name in routing.get("candidates") or [] if name
    }
    return reachable


def _member_target(record: dict[str, Any]) -> dict[str, Any]:
    """One backend as a routing target, however the API arrived at it.

    Priority and weight are a pool's declaration, so they are absent here: the
    API that names this backend directly reaches only it, and the one that
    picks between candidates declares no share either.
    """
    return {
        "backendId": record.get("id"),
        "url": record.get("url"),
        "resourceIdRef": record.get("resourceIdRef"),
        "priority": None,
        "weight": None,
        "circuitBreaker": record.get("circuitBreaker"),
        "secretRefs": record.get("secretRefs") or [],
        "provider": record.get("provider"),
        "languageModel": record.get("languageModel"),
    }


def _routing_targets(
    record: dict[str, Any] | None,
    by_id: dict[str, dict[str, Any]],
    service_url: str | None,
    candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if record is None:
        # A `set-backend-service` count that is not exactly one resolves to no
        # single backend, but the API still reaches every candidate. Reporting
        # no target at all made the model catalogue unresolvable and left the
        # alias with no members -- so the plan proposed carrying the routing
        # condition into alias priority and weight while building no alias to
        # carry it. They are targets without a priority or a weight because a
        # `choose` declares neither; what the condition meant is the separate
        # decision the `set-backend-service` rule already raises.
        if candidates:
            return [_member_target(member) for member in candidates]
        return [{"backendId": None, "url": service_url, "priority": None, "weight": None}] if service_url else []
    pool = record.get("pool") or {}
    if pool.get("services"):
        targets = []
        for item in pool["services"]:
            member = by_id.get(item["backendId"]) or {}
            targets.append(
                {
                    "backendId": item["backendId"],
                    "url": member.get("url"),
                    "resourceIdRef": member.get("resourceIdRef"),
                    "priority": item.get("priority"),
                    "weight": item.get("weight"),
                    "circuitBreaker": member.get("circuitBreaker"),
                    "secretRefs": member.get("secretRefs") or [],
                    "provider": member.get("provider"),
                    "languageModel": member.get("languageModel"),
                }
            )
        return targets
    return [_member_target(record)]


# A backend can carry several credentials at once. The reported mode is the one
# that governs how the target provider must be configured, strongest first.
#
# The three in the middle have no target field at all, so they rank above the
# two that do: a backend carrying both a client certificate and an api-key
# header is not migrated by registering the key and calling it done. `basic` is
# last of those three because it is the only one a person can reproduce by hand
# -- `Authorization: Basic base64(user:pass)` is a Custom provider's ApiKey
# header -- whereas an OAuth connection and mTLS can be reproduced by nothing.
_AUTH_PRECEDENCE = (
    "managedIdentity", "credentialManager", "clientCertificate", "basic",
    "authorizationHeader", "apiKey", "none",
)


def _backend_auth(
    record: dict[str, Any] | None, effective: policy_mod.Resolution | None,
    registry: secrets.SecretRegistry, *, alternatives: str = "product",
    secret_by_named_value: dict[str, str] | None = None,
) -> dict[str, Any]:
    auth: dict[str, Any] = {"mode": "none", "modes": [], "secretRefs": [], "evidence": []}
    credentials = (record or {}).get("credentials") or {}
    owner = (record or {}).get("id")
    # A parameter setter names the credential; its `<value>` child holds it.
    # Both are elements, so the pair has to be put back together here.
    children_of: dict[str, list[dict[str, Any]]] = {}
    for element in (effective.elements if effective else []):
        parent, _, tail = (element.get("path") or "").rpartition("/")
        if parent and tail.startswith("value["):
            children_of.setdefault(parent, []).append(element)

    def note(mode: str, evidence: str) -> None:
        if mode not in auth["modes"]:
            auth["modes"].append(mode)
        if evidence not in auth["evidence"]:
            auth["evidence"].append(evidence)

    def add_secret(ref: str) -> None:
        if ref not in auth["secretRefs"]:
            auth["secretRefs"].append(ref)

    def add_identity(client_id: str | None, audience: str | None, evidence: str) -> None:
        identity_type = "userAssigned" if client_id else "systemAssigned"
        note("managedIdentity", evidence)
        auth["identity"] = {"type": identity_type, "clientId": client_id, "audience": audience}
        add_secret(
            registry.managed_identity(
                identity_type=identity_type, client_id=client_id, audience=audience, used_by=owner
            )
        )

    # The live APIM contract exposes credentials.managedIdentity, which the published
    # ARM schema does not document. It is how the portal's AI API import wires a
    # Foundry backend, and it maps onto an AI Gateway provider's
    # authentication.kind: ManagedIdentity -- so missing it would misreport the most
    # common Azure model backend as unauthenticated.
    identity = credentials.get("managedIdentity")
    if identity:
        add_identity(identity.get("clientId"), identity.get("resource"), "backend.credentials.managedIdentity")

    if credentials.get("header") or credentials.get("query"):
        note("apiKey", "backend.credentials")
        auth["parameters"] = {
            "header": list((credentials.get("header") or {}).keys()),
            "query": list((credentials.get("query") or {}).keys()),
        }
    if credentials.get("authorization"):
        note("authorizationHeader", "backend.credentials.authorization")
        auth["scheme"] = (credentials.get("authorization") or {}).get("scheme")
    if credentials.get("certificateIds") or credentials.get("certificate"):
        note("clientCertificate", "backend.credentials.certificate")

    for ref in (record or {}).get("secretRefs") or []:
        add_secret(ref)

    for element in (effective.elements if effective else []):
        if element["name"] == "authentication-certificate":
            note("clientCertificate", "policy:authentication-certificate")
        elif element["name"] == "authentication-basic":
            # No secret ref, deliberately, and the same way the two branches
            # around it carry none. `secretRefs` is what `_custom_auth` reads
            # to fill a provider's ApiKey value, so claiming the password here
            # would publish a basic credential as a working api key -- a
            # stronger falsehood than the one this branch exists to remove. The
            # password is still registered on the policy document, so it is
            # recorded; it is just not this provider's credential.
            note("basic", "policy:authentication-basic")
        elif element["name"] == "get-authorization-context":
            note("credentialManager", "policy:get-authorization-context")
        elif element.get("credentialParameter"):
            # The upstream key, written as the header or query parameter the
            # provider reads it from. `credentials.header` above is the same
            # credential declared on the backend record instead; a backend can
            # carry it either way and the target field is the same, so this
            # records the parameter in the shape that branch already uses.
            parameter = element["credentialParameter"]
            note("apiKey", f"policy:{element['name']}")
            parameters = auth.setdefault("parameters", {"header": [], "query": []})
            side = "query" if element["name"] == "set-query-parameter" else "header"
            if parameter not in parameters.setdefault(side, []):
                parameters[side].append(parameter)
            # The value is on the `<value>` child, which is an element of its
            # own: the setter names the parameter and the child carries what
            # goes in it. The secret ref is the one `_collect_named_values`
            # already registered -- minting a second here would describe the
            # same APIM secret twice, under two ids.
            for child in children_of.get(element.get("path") or "", ()):
                for nv_name in child.get("namedValueRefs") or []:
                    ref = (secret_by_named_value or {}).get(nv_name)
                    if ref:
                        add_secret(ref)

    # Per request context, because the last `authentication-managed-identity`
    # to run is the one that applies and a union of alternatives is not an
    # order. A product is one alternative and no product is another: flattened
    # together, an identity set on the API after `<base />` could be dropped as
    # a duplicate and a product's identity read as the later of the two, when
    # the API's overrides it in both contexts.
    candidates: list[tuple[str | None, str | None]] = []
    for chain in (effective.chains if effective else ()):
        last = None
        for occurrence in chain:
            if occurrence.name == "authentication-managed-identity":
                last = occurrence.element
        if last is not None:
            attributes = last.get("attributes") or {}
            candidate = (attributes.get("client-id"), attributes.get("resource"))
            if candidate not in candidates:
                candidates.append(candidate)
    if candidates:
        client_id, audience = candidates[0]
        add_identity(client_id, audience, "policy:authentication-managed-identity")
        if len(candidates) > 1:
            # Which one applies depends on the route a call arrives by, and one
            # provider cannot authenticate two ways. Named rather than resolved:
            # picking silently would be a guess reported as a fact.
            auth["identityCandidates"] = [
                {"clientId": cid, "audience": aud} for cid, aud in candidates
            ]
            auth["identityNote"] = (
                f"{len(candidates)} managed identities apply, depending on which {alternatives} a "
                "call arrives through. The first is proposed; the alternatives are recorded here."
            )

    for mode in _AUTH_PRECEDENCE:
        if mode in auth["modes"]:
            auth["mode"] = mode
            break

    # "none" is a claim that the backend is called unauthenticated. Record what was
    # searched so a reader can tell it apart from "nothing was searched", and say so
    # outright when a fragment could not be resolved.
    auth["basis"] = {
        "backendCredentials": bool(credentials),
        "policyScopesExamined": list(effective.scopes_examined) if effective else [],
        # Both kinds of "could not be read", because for this question they
        # cost the same: a fragment naming nothing and one whose body would not
        # load are each a place the credential could have been set.
        "unresolvedFragments": sorted(
            {*(effective.unresolved_fragments if effective else ()),
             *(effective.unreadable_fragments if effective else ())}
        ),
    }
    if auth["mode"] == "none":
        if auth["basis"]["unresolvedFragments"]:
            auth["mode"] = "undetermined"
            auth["note"] = (
                "No credential found, but policy fragments "
                + ", ".join(auth["basis"]["unresolvedFragments"])
                + " could not be resolved, so one may be set there."
            )
        elif not auth["basis"]["policyScopesExamined"] and not credentials:
            auth["mode"] = "undetermined"
            auth["note"] = (
                "No backend credentials and no policy was read for this asset, so how it "
                "authenticates upstream could not be determined."
            )
        else:
            auth["note"] = (
                "No credential on the backend and none set by the policies examined; the "
                "upstream appears to be called unauthenticated."
            )
    return auth


def _supporting_backends(effective: policy_mod.Resolution, *, workspace: str) -> list[dict[str, Any]]:
    """Backends this API depends on for something other than serving the model.

    A content-safety or embeddings backend is a migration dependency in its own
    right -- and content safety has no equivalent on a typed AI Gateway, so the
    dependency is also a gap rather than a thing to recreate.
    """
    found: dict[str, dict[str, Any]] = {}
    for element in effective.elements:
        mapping = detect.backend_roles_from_element(element)
        if not mapping:
            continue
        backend_name, role = mapping
        if role == "routing":
            continue  # that is the model backend itself, covered by routing.targets
        key = f"{backend_name}:{role}"
        if key in found:
            continue
        child_names = element.get("childNames") or []
        found[key] = {
            "backendId": ids.backend(backend_name, workspace if workspace != "default" else None),
            "name": backend_name,
            "role": role,
            "policyElement": element["name"],
            # Attributes only. Policies like llm-content-safety keep most of their
            # configuration in child elements (<categories>, thresholds), so naming
            # this "settings" would imply a completeness it does not have.
            "attributes": element.get("attributes") or {},
            "childElements": child_names,
            "configurationComplete": not child_names,
            "fullConfigurationAt": {"policyId": element.get("policyId"), "path": element["path"]},
        }
    return list(found.values())


def _translation(
    inbound: list[str], backend: list[str], operations: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Compare the dialect callers speak with the one the backend speaks.

    The inbound side is inferred from operation URL templates, which an operator
    configures freely -- a wildcard ``/*`` route carries no dialect at all. So the
    comparison reports an explicit status, including "indeterminate", rather than
    going quiet and turning a real gap into a silent omission.
    """
    if not backend:
        return None
    basis = {
        "inboundFrom": "operationTemplates",
        "operationCount": len(operations),
        "caveat": (
            "Inbound dialect is inferred from operation URL templates, which are "
            "operator-configured. It is evidence, not a declaration."
        ),
    }
    if not inbound:
        return {
            "status": "indeterminate",
            "inbound": [],
            "backend": backend,
            "basis": basis,
            "note": (
                "The operations expose no recognizable inference route (a wildcard or custom "
                "template), so the dialect callers use cannot be read from configuration. Confirm "
                "it with the operator: if it differs from the backend dialect, APIM is translating "
                "formats and AI Gateway has no equivalent."
            ),
        }
    if set(inbound) & set(backend):
        return {
            "status": "native",
            "inbound": inbound,
            "backend": backend,
            "basis": basis,
            "note": "Callers already use the backend's dialect, so no translation is in play.",
        }
    return {
        "status": "translating",
        "inbound": inbound,
        "backend": backend,
        "basis": basis,
        "note": (
            "This API accepts one dialect and calls another, so APIM is translating formats. "
            "AI Gateway publishes a model at its native endpoint instead, so callers would have "
            "to move to the backend dialect or keep a translation layer in front of the gateway."
        ),
    }


def _tool_discovery(pattern: str, tools: list[dict[str, Any]], props: dict[str, Any]) -> dict[str, Any]:
    """Where the authoritative tool list for this server comes from.

    It matters for migration because an AI Gateway tool server's ``allowList``
    and ``blocked`` arrays need real tool names, and a passthrough APIM MCP API
    does not store them: APIM proxies ``tools/list`` to the upstream server.
    """
    if pattern == "toolProjection":
        return {
            "status": "complete",
            "source": "apimControlPlane",
            "note": "Tools are APIM operations, so the control plane holds the authoritative list.",
        }
    return {
        "status": "runtimeOnly",
        "source": "upstreamMcpServer",
        "note": (
            "APIM proxies tools/list to the upstream server and stores no tool names. Call "
            "tools/list against the gateway or the upstream to enumerate them before writing an "
            "AI Gateway allowList or blocked list."
        ),
        "discoveredCount": len(tools),
    }


def _merge_resolutions(
    resolutions: Sequence[policy_mod.Resolution],
) -> policy_mod.Resolution | None:
    """One resolution covering every API that reaches the same provider.

    `chains` concatenates rather than unions, because a chain is one alternative
    request context and `_backend_auth` reads the *last* identity in each. Two
    APIs are two more alternatives in exactly the sense a product already is, so
    an identity they disagree on surfaces as `identityCandidates` instead of
    whichever API happened to be collected second.

    Everything else unions: what a policy covers, which scopes were read, and
    which fragments would not resolve are all set questions.
    """
    if not resolutions:
        return None
    if len(resolutions) == 1:
        return resolutions[0]
    scopes: list[str] = []
    unresolved: list[str] = []
    unreadable: list[str] = []
    breaks: list[dict[str, Any]] = []
    occurrences: list[policy_mod.Occurrence] = []
    chains: list[tuple[policy_mod.Occurrence, ...]] = []
    for resolution in resolutions:
        occurrences.extend(resolution.occurrences)
        chains.extend(resolution.chains)
        for source, sink in (
            (resolution.scopes_examined, scopes),
            (resolution.unresolved_fragments, unresolved),
            (resolution.unreadable_fragments, unreadable),
            (resolution.inheritance_breaks, breaks),
        ):
            for value in source:
                if value not in sink:
                    sink.append(value)
    return policy_mod.Resolution(
        occurrences=tuple(policy_mod.unique_occurrences(occurrences)),
        scopes_examined=tuple(scopes),
        unresolved_fragments=tuple(unresolved),
        unreadable_fragments=tuple(unreadable),
        inheritance_breaks=tuple(breaks),
        chains=tuple(chains),
    )


def _provider_auth(
    candidate: dict[str, Any],
    resolutions: Sequence[policy_mod.Resolution],
    registry: secrets.SecretRegistry,
    *,
    secret_by_named_value: dict[str, str] | None = None,
) -> dict[str, Any]:
    record = {"credentials": candidate.get("credentials"), "secretRefs": candidate.get("secretRefs")}
    # "API or product", because a provider sits behind every API that routes to
    # it: the alternatives it has to choose between are one per API per product,
    # where an API has only the products.
    return _backend_auth(
        record, _merge_resolutions(resolutions), registry, alternatives="API or product",
        secret_by_named_value=secret_by_named_value,
    )


def _mark_referenced(excluded: list[dict[str, Any]], assets: dict[str, list[dict[str, Any]]]) -> None:
    """Annotate skipped APIs that an inventoried asset still depends on."""
    referenced: dict[str, list[str]] = {}
    for asset in assets.get("mcpServers", []):
        for api_id in asset.get("sourceApiIds") or []:
            referenced.setdefault(api_id, []).append(asset["id"])
    for provider in assets.get("modelProviders", []):
        for api_id in (provider.get("referencedBy") or {}).get("apis", []):
            referenced.setdefault(api_id, []).append(provider["id"])
    for entry in excluded:
        owners = referenced.get(entry["apiId"])
        if owners:
            entry["referencedBy"] = sorted(set(owners))
            entry["reason"] = "notAnAiAssetButReferencedByOne"


def _declared_models(operations: list[dict[str, Any]], elements: list[dict[str, Any]]) -> set[str]:
    """Model names that appear literally in operation templates or policy."""
    found: set[str] = set()
    for operation in operations:
        for match in re.finditer(r"/deployments/([A-Za-z0-9._\-]+)", operation.get("urlTemplate") or ""):
            candidate = match.group(1)
            if not candidate.startswith("{"):
                found.add(candidate)
    for element in elements:
        # set-backend-service carries backend ids and base URLs, never model names.
        if element["name"] in {"set-variable", "set-header"}:
            for value in element["attributes"].values():
                if isinstance(value, str) and re.fullmatch(r"(gpt|o\d|claude|llama|mistral|phi|gemini)[A-Za-z0-9._\-]*", value or "", re.IGNORECASE):
                    found.add(value)
    return found


def _mcp_transport(mcp_props: dict[str, Any]) -> dict[str, Any]:
    """Resolve the upstream MCP transport, and record how.

    An AI Gateway tool-server endpoint requires streamableHttp or sse. APIM leaves
    transportType null on every instance seen so far, so the value usually has to
    be read from the endpoint collection's key names -- an inference. When neither
    is readable the result says "undetermined" rather than returning null, which
    would read as "no transport configured".
    """
    declared = mcp_props.get("transportType")
    if declared:
        return {
            "value": {"streamable": "streamableHttp", "sse": "sse"}.get(declared, declared),
            "basis": "transportType",
            "status": "declared",
        }
    endpoints = mcp_props.get("endpoints")
    names: set[str] = set()
    if isinstance(endpoints, dict):
        names = {str(key) for key in endpoints}
    elif isinstance(endpoints, list):
        names = {str(entry.get("name")) for entry in endpoints if entry.get("name")}
    if "sse" in names:
        return {"value": "sse", "basis": "endpointName", "status": "inferred"}
    if names:
        return {"value": "streamableHttp", "basis": "endpointName", "status": "inferred"}
    return {
        "value": None,
        "basis": None,
        "status": "undetermined",
        "note": (
            "APIM declares no transportType and exposes no MCP endpoint names, so the "
            "upstream transport could not be read. Confirm it before registering a tool "
            "server endpoint, which requires streamableHttp or sse."
        ),
    }


def _mcp_path(mcp_props: dict[str, Any]) -> str | None:
    endpoints = mcp_props.get("endpoints")
    if isinstance(endpoints, dict):
        for key in ("mcp", "message", "messages", "sse"):
            entry = endpoints.get(key)
            if isinstance(entry, dict) and entry.get("uriTemplate"):
                return entry["uriTemplate"]
    if isinstance(endpoints, list):
        for entry in endpoints:
            if entry.get("uriTemplate"):
                return entry["uriTemplate"]
    return None



def _fragments_reaching(
    effective: policy_mod.Resolution | None, workspace: str | None
) -> list[str]:
    """Every fragment an API's policy reaches, resolved or not.

    A reference naming no collected fragment is listed too, under the id it
    would have had, and so is one whose body would not load -- that one
    contributes no elements, so it is in no occurrence's route, and dropping it
    would cut the asset's only link to the document explaining the failure.
    `auth.basis.unresolvedFragments` says which of these could not be read.
    """
    seen: list[str] = []
    for occurrence in (effective.occurrences if effective else ()):
        for policy_id in occurrence.via:
            if policy_id not in seen:
                seen.append(policy_id)
    for policy_id in (effective.unreadable_fragments if effective else ()):
        if policy_id not in seen:
            seen.append(policy_id)
    for name in (effective.unresolved_fragments if effective else ()):
        missing = ids.policy("fragment", ids.scoped(workspace, name))
        if missing not in seen:
            seen.append(missing)
    return seen


def _policy_refs(
    policy_id: str,
    document: dict[str, Any] | None,
    workspace: str | None,
    shared: dict[str, Any],
    api_name: str,
    operations: list[dict[str, Any]] | None = None,
    operation_policies_collected: bool = False,
    effective: policy_mod.Resolution | None = None,
) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "global": ids.policy("global"),
        "api": policy_id if document else None,
        "operationPoliciesCollected": operation_policies_collected,
        # Every fragment that reaches this API, not only the ones its own
        # document names: a fragment included by another fragment, or by the
        # product or global policy, governs it just as much. Taken from the
        # resolution rather than re-walked, so this cannot disagree with it.
        "fragments": _fragments_reaching(effective, workspace),
        "products": [],
        "operations": [
            operation["policyId"] for operation in (operations or []) if operation.get("policyId")
        ],
    }
    api_id = ids.api(api_name, workspace)
    for product in shared.get("products", []):
        if api_id in product["apiIds"] and product.get("policyId"):
            refs["products"].append(product["policyId"])
    return refs


def _subscription_scope(scope_id: str) -> dict[str, Any]:
    """Classify what an APIM subscription key grants access to.

    AI Gateway API keys are gateway-wide, so this distinction is exactly the
    authorization gap a migration has to resolve.
    """
    lowered = (scope_id or "").lower().rstrip("/")
    if not lowered:
        return {"level": "unknown", "resourceId": scope_id}
    if lowered.endswith("/apis"):
        return {"level": "allApis", "resourceId": scope_id}
    if "/apis/" in lowered:
        return {"level": "api", "name": ids.arm_name(scope_id), "resourceId": scope_id}
    if "/products/" in lowered:
        return {"level": "product", "name": ids.arm_name(scope_id), "resourceId": scope_id}
    # Only the service id itself is service-wide. Anything unrecognized is reported
    # as unknown rather than silently widened to the broadest access level.
    if re.search(r"/providers/microsoft\.apimanagement/service/[^/]+$", lowered):
        return {"level": "service", "resourceId": scope_id}
    return {"level": "unknown", "resourceId": scope_id}


def _redact_proxy(proxy: dict[str, Any] | None) -> dict[str, Any] | None:
    if not proxy:
        return None
    cleaned = dict(proxy)
    if cleaned.get("password"):
        cleaned["password"] = secrets.redact(cleaned["password"])
    return cleaned
