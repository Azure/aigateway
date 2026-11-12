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
from typing import Any
from urllib.parse import urlsplit

from . import detect, ids, policy as policy_mod, secrets
from .arm import ArmClient, ArmError
from .foundry import FoundryResolver, target_model_registration

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
    fast: bool = False
    max_apis: int | None = None


class Collector:
    def __init__(self, client: ArmClient, service_id: str, options: CollectOptions) -> None:
        self.client = client
        self.service_id = service_id.rstrip("/")
        self.options = options
        self.api_version = options.apim_api_version
        self.registry = secrets.SecretRegistry(service_id=self.service_id, api_version=self.api_version)
        self.coverage: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self._policy_index: dict[str, dict[str, Any]] = {}
        self.foundry: FoundryResolver | None = None
        self.subscription_id = ids.arm_segment(self.service_id, "subscriptions") or ""
        self._products_by_scope: dict[str, list[dict[str, Any]]] = {}
        self.excluded_backends: list[dict[str, Any]] = []

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
            "$schema": "https://github.com/Azure/aigateway/tools/apim-import/schemas/inventory.schema.json",
            "schemaVersion": SCHEMA_VERSION,
            "kind": "apimAiInventory",
            "generator": {
                "name": "apim-import",
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
                    "fast": self.options.fast,
                },
                "requestCount": self.client.call_count,
                "coverage": self.coverage,
                "warnings": self.warnings,
            },
            "service": service,
            "workspaces": [
                {**entry, "collected": entry["name"] in scopes} for entry in workspaces
            ],
            "assets": assets,
            "excludedApis": excluded,
            "excludedBackends": self.excluded_backends,
            "shared": shared,
            "policies": self.policies,
            "secrets": self.registry.items(),
        }
        if self.foundry:
            document["shared"]["foundryAccounts"] = [
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
            raise ArmError(f"API Management service not found: {self.service_id}")
        props = raw.get("properties") or {}
        identity = raw.get("identity") or {}
        user_assigned = identity.get("userAssignedIdentities") or {}
        hostnames = [
            {
                "type": entry.get("type"),
                "hostName": entry.get("hostName"),
                "certificateSource": entry.get("certificateSource"),
                "keyVaultId": entry.get("keyVaultId"),
                "identityClientId": entry.get("identityClientId"),
            }
            for entry in (props.get("hostnameConfigurations") or [])
        ]
        return {
            "resourceId": raw.get("id"),
            "name": raw.get("name"),
            "location": raw.get("location"),
            "subscriptionId": self.subscription_id,
            "resourceGroup": ids.arm_segment(self.service_id, "resourceGroups"),
            "sku": raw.get("sku"),
            "provisioningState": props.get("provisioningState"),
            "gatewayUrl": props.get("gatewayUrl"),
            "managementApiUrl": props.get("managementApiUrl"),
            "developerPortalUrl": props.get("developerPortalUrl"),
            "virtualNetworkType": props.get("virtualNetworkType"),
            "publicNetworkAccess": props.get("publicNetworkAccess"),
            "publicIPAddresses": props.get("publicIPAddresses"),
            "privateIPAddresses": props.get("privateIPAddresses"),
            "hostnameConfigurations": hostnames,
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
            scope={"level": "global", "name": None, "resourceId": self.service_id},
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
        fragments = self._collect_fragments(base, scope_label)
        products = self._collect_products(base, workspace, scope_label)
        self._products_by_scope[workspace or "default"] = products
        subscriptions = self._collect_subscriptions(base, workspace, scope_label)
        certificates = self._collect_certificates(base, scope_label) if not workspace else []
        auth_servers = self._collect_auth_servers(base, scope_label) if not workspace else []
        openid = self._collect_openid(base, scope_label) if not workspace else []
        credential_providers = self._collect_credential_providers(base, scope_label) if not workspace else []
        telemetry = self._collect_telemetry(base, scope_label) if not workspace else {}

        if workspace and workspace != "default":
            self._capture_policy(
                scope={"level": "workspace", "name": workspace, "resourceId": base},
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
            "credentialProviders": credential_providers,
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
            else:
                # Non-secret named values are plain configuration and are part of
                # the migration payload, so keep their value.
                record["value"] = props.get("value")
            results.append(record)
        return results

    def _collect_fragments(self, base: str, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{base}/policyFragments", "policyFragments", scope)
        results = []
        for entry in raw:
            name = entry.get("name") or ""
            props = entry.get("properties") or {}
            value = props.get("value")
            if value is None:
                detail = self._get(
                    f"{base}/policyFragments/{name}", "policyFragment", scope, params={"format": "rawxml"}
                )
                value = ((detail or {}).get("properties") or {}).get("value")
            policy_id = ids.policy("fragment", name)
            document = policy_mod.parse(
                value or "",
                policy_id=policy_id,
                scope={"level": "fragment", "name": name, "resourceId": entry.get("id")},
                scope_url=f"{base}/policyFragments/{name}",
                registry=self.registry,
            )
            self._add_policy(document)
            results.append(
                {
                    "id": ids.fragment(name),
                    "name": name,
                    "description": props.get("description"),
                    "policyId": policy_id,
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
                scope={"level": "product", "name": name, "resourceId": entry.get("id")},
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
                continue
            if self.options.exclude_api and detect.matches_any(name, self.options.exclude_api):
                excluded.append(_excluded(raw, workspace, "excludedByOption", []))
                continue
            forced = bool(self.options.include_api and detect.matches_any(name, self.options.include_api))

            api_url = f"{base}/apis/{name}"
            policy_id = ids.policy("api", ids.scoped(workspace, name))
            document = self._capture_policy(
                scope={"level": "api", "name": name, "resourceId": raw.get("id")},
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
            api_scoped = self._effective_elements(document, include_shared=False, api_name=name, workspace=workspace)
            effective = self._effective_elements(document, include_shared=True, api_name=name, workspace=workspace)
            element_names = {element["name"] for element in api_scoped["elements"]}
            families = {element["family"] for element in api_scoped["elements"]}

            backend_record = _resolve_backend(props, backends_by_name, backends_by_id, workspace)
            backend_urls = _backend_urls(backend_record, backends_by_id)

            api_type = (props.get("type") or "http").lower()
            operations: list[dict[str, Any]] = []
            # MCP and A2A APIs expose no REST operations; skip the round trip.
            if api_type not in {"mcp", "a2a"} and not self.options.fast:
                operations = self._collect_operations(api_url, name, workspace, scope_label)

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
                "policyRefs": _policy_refs(policy_id, document, workspace, shared, name, operations),
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
                assets["mcpServers"].append(self._mcp_asset(common, raw, api_url, backend_record, backends_by_id, workspace, scope_label, classification))
            elif classification.kind == "agent" and "a2a" in self.options.families:
                assets["agents"].append(self._agent_asset(common, raw, api_url, backend_record, workspace))
            elif classification.kind == "modelApi" and "models" in self.options.families:
                assets["models"].append(
                    self._model_asset(
                        common, raw, operations, backend_record, backends_by_id, classification, effective
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
            name = candidate["origin"].get("backendName") or (urlsplit(candidate["endpoint"] or "").hostname or key)
            record: dict[str, Any] = {
                "id": ids.asset("modelProvider", name, workspace),
                "kind": "modelProvider",
                "workspace": workspace or "default",
                "providerKind": rule.kind if rule else "unknown",
                "providerLabel": rule.label if rule else None,
                "targetProviderKind": rule.target_provider_kind if rule else "Custom",
                "apiDialect": rule.api_dialect if rule else None,
                "endpoint": candidate["endpoint"],
                "origin": candidate["origin"],
                "auth": _provider_auth(candidate, self.registry),
                "tls": candidate["tls"],
                "circuitBreaker": candidate["circuitBreaker"],
                "azure": None,
                "models": {
                    "status": "unresolved",
                    "discoverySource": rule.catalog if rule else "unknown",
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
                            {
                                "deploymentName": deployment["name"],
                                "modelName": deployment["modelName"],
                                "modelVersion": deployment["modelVersion"],
                                "modelFormat": deployment["modelFormat"],
                                "sku": deployment["sku"],
                                "raiPolicyName": deployment["raiPolicyName"],
                                "target": target_model_registration(account, deployment),
                            }
                            for deployment in deployments
                        ],
                        "notes": [account.deployments_error] if account.deployments_error else [],
                    }
                else:
                    record["models"]["notes"].append(
                        "Endpoint resolves to no Cognitive Services account in the scanned subscriptions. "
                        "Pass --foundry-subscription for cross-subscription backends."
                    )
            elif rule and rule.catalog == "modelsEndpoint":
                record["models"]["notes"].append(
                    f"Run 'apim-import resolve-models' to list models from {record['endpoint']}/v1/models "
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
            asset["providerIds"] = [
                provider["id"]
                for provider in providers
                if provider["origin"].get("backendId")
                in {target.get("backendId") for target in (asset.get("routing") or {}).get("targets", [])}
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
                record = _resolve_backend(source_props, backends_by_name, backends_by_id, workspace)
                for target in _routing_targets(record, backends_by_id, source_props.get("serviceUrl")):
                    upstream.append({**target, "viaApi": ids.api(source_name, workspace), "transport": "http"})
            asset["upstream"] = upstream
            asset["sourceApiIds"] = [ids.api(name, workspace) for name in source_names]

    def _collect_operations(self, api_url: str, name: str, workspace: str | None, scope: str) -> list[dict[str, Any]]:
        raw = self._list(f"{api_url}/operations", "operations", f"{scope}/api:{name}", quiet=True)
        operations = []
        for entry in raw:
            props = entry.get("properties") or {}
            operation_name = entry.get("name") or ""
            policy_id = ids.policy("operation", f"{ids.scoped(workspace, name)}/{operation_name}")
            document = self._capture_policy(
                scope={
                    "level": "operation",
                    "name": operation_name,
                    "apiName": name,
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
        effective: dict[str, Any],
    ) -> dict[str, Any]:
        props = raw.get("properties") or {}
        targets = _routing_targets(backend_record, backends_by_id, props.get("serviceUrl"))
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
            "auth": _backend_auth(backend_record, effective, self.registry),
            "azure": None,
        }

        models: dict[str, Any] = {
            "status": "unresolved",
            "discoverySource": provider_rule.catalog if provider_rule else "unknown",
            "resolved": [],
            "declared": sorted(_declared_models(operations, effective.get("elements") or [])),
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
            account = None
            for target in targets:
                account = self.foundry.by_resource_id(target.get("resourceIdRef")) or self.foundry.by_url(target.get("url"))
                if account:
                    break
            if account:
                deployments = self.foundry.load_deployments(account)
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
                models["status"] = "resolved" if deployments else "empty"
                models["discoverySource"] = "armDeployments"
                models["resolved"] = [
                    {
                        "deploymentName": deployment["name"],
                        "modelName": deployment["modelName"],
                        "modelVersion": deployment["modelVersion"],
                        "modelFormat": deployment["modelFormat"],
                        "sku": deployment["sku"],
                        "raiPolicyName": deployment["raiPolicyName"],
                        "target": target_model_registration(account, deployment),
                    }
                    for deployment in deployments
                ]
                if account.deployments_error:
                    models["notes"].append(account.deployments_error)
            else:
                models["notes"].append(
                    "Backend looks like an Azure AI Foundry endpoint but no matching Cognitive Services "
                    "account was found in the scanned subscriptions. Pass --foundry-subscription."
                )
        elif provider_rule and provider_rule.catalog == "modelsEndpoint":
            models["notes"].append(
                f"Model list is discoverable from {provider_rule.label} at {endpoint or '<endpoint>'}/v1/models, "
                "which requires the backend credential. Run 'apim-import resolve-models' to fetch it "
                "just-in-time without persisting the key."
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
                "mode": "pool" if (backend_record or {}).get("type") == "Pool" else ("single" if targets else "policy"),
                "targets": targets,
                "circuitBreaker": (backend_record or {}).get("circuitBreaker"),
                "evidence": (backend_record or {}).get("id") or "serviceUrl",
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
        for target in _routing_targets(backend_record, backends_by_id, props.get("serviceUrl")):
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

    def _effective_elements(
        self,
        document: dict[str, Any] | None,
        *,
        include_shared: bool,
        api_name: str,
        workspace: str | None,
    ) -> dict[str, Any]:
        """Flatten the policy elements that actually govern one API.

        Resolves ``include-fragment`` references (guarding against cycles) and,
        when ``include_shared``, folds in the product and global documents. The
        scopes consulted are returned so a reader can tell "found nothing" apart
        from "did not look".
        """
        elements: list[dict[str, Any]] = []
        scopes: list[str] = []
        unresolved: list[str] = []

        def add(doc: dict[str, Any] | None) -> None:
            if doc:
                # Tag each element with the document it came from, so anything built
                # from this flattened view can point back at the full configuration.
                elements.extend({**element, "policyId": doc["id"]} for element in doc.get("elements") or [])
                if doc["id"] not in scopes:
                    scopes.append(doc["id"])

        add(document)
        pending = list((document or {}).get("fragmentRefs") or [])
        seen: set[str] = set()
        while pending:
            fragment_name = pending.pop(0)
            if fragment_name in seen:
                continue
            seen.add(fragment_name)
            fragment_doc = self._policy_index.get(ids.policy("fragment", fragment_name))
            if fragment_doc is None:
                unresolved.append(fragment_name)
                continue
            add(fragment_doc)
            pending.extend(fragment_doc.get("fragmentRefs") or [])

        if include_shared:
            api_id = ids.api(api_name, workspace)
            for product in self._products_by_scope.get(workspace or "default", []):
                if api_id in product["apiIds"] and product.get("policyId"):
                    add(self._policy_index.get(product["policyId"]))
            add(self._policy_index.get(ids.policy("global")))

        return {"elements": elements, "scopesExamined": scopes, "unresolvedFragments": unresolved}

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

    def _get(
        self, url: str, collection: str, scope: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        try:
            resp = self.client.request("GET", url, api_version=self.api_version, params=params)
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

    def _list(self, url: str, collection: str, scope: str, *, quiet: bool = False) -> list[dict[str, Any]]:
        try:
            items = self.client.list(url, self.api_version)
        except ArmError as exc:
            self.coverage.append(_coverage(collection, scope, "failed", 0, str(exc)))
            if not quiet:
                self.warnings.append({"code": "collectionRead", "collection": collection, "scope": scope, "message": str(exc)})
            return []
        self.coverage.append(_coverage(collection, scope, "complete" if items else "empty", len(items), None))
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


def _resolve_backend(
    props: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    workspace: str | None,
) -> dict[str, Any] | None:
    backend_id = props.get("backendId")
    if not backend_id:
        return None
    record = by_name.get(backend_id) or by_id.get(ids.backend(backend_id, workspace))
    return record


def _raw_backend(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {"properties": {"url": record.get("url"), "resourceId": record.get("resourceIdRef")}}


def _backend_urls(record: dict[str, Any] | None, by_id: dict[str, dict[str, Any]]) -> list[str]:
    if not record:
        return []
    urls = [record.get("url")] if record.get("url") else []
    for item in ((record.get("pool") or {}).get("services") or []):
        member = by_id.get(item["backendId"])
        if member and member.get("url"):
            urls.append(member["url"])
    return [url for url in urls if url]


def _routing_targets(
    record: dict[str, Any] | None, by_id: dict[str, dict[str, Any]], service_url: str | None
) -> list[dict[str, Any]]:
    if record is None:
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
    return [
        {
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
    ]


# A backend can carry several credentials at once. The reported mode is the one
# that governs how the target provider must be configured, strongest first.
_AUTH_PRECEDENCE = (
    "managedIdentity", "credentialManager", "clientCertificate",
    "authorizationHeader", "apiKey", "none",
)


def _backend_auth(
    record: dict[str, Any] | None, effective: dict[str, Any] | None, registry: secrets.SecretRegistry
) -> dict[str, Any]:
    auth: dict[str, Any] = {"mode": "none", "modes": [], "secretRefs": [], "evidence": []}
    credentials = (record or {}).get("credentials") or {}
    owner = (record or {}).get("id")

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

    for element in (effective or {}).get("elements", []):
        if element["name"] == "authentication-managed-identity":
            add_identity(
                element["attributes"].get("client-id"),
                element["attributes"].get("resource"),
                "policy:authentication-managed-identity",
            )
        elif element["name"] == "authentication-certificate":
            note("clientCertificate", "policy:authentication-certificate")
        elif element["name"] == "get-authorization-context":
            note("credentialManager", "policy:get-authorization-context")

    for mode in _AUTH_PRECEDENCE:
        if mode in auth["modes"]:
            auth["mode"] = mode
            break

    # "none" is a claim that the backend is called unauthenticated. Record what was
    # searched so a reader can tell it apart from "nothing was searched", and say so
    # outright when a fragment could not be resolved.
    auth["basis"] = {
        "backendCredentials": bool(credentials),
        "policyScopesExamined": (effective or {}).get("scopesExamined") or [],
        "unresolvedFragments": (effective or {}).get("unresolvedFragments") or [],
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


def _supporting_backends(effective: dict[str, Any], *, workspace: str) -> list[dict[str, Any]]:
    """Backends this API depends on for something other than serving the model.

    A content-safety or embeddings backend is a migration dependency in its own
    right -- and content safety has no equivalent on a typed AI Gateway, so the
    dependency is also a gap rather than a thing to recreate.
    """
    found: dict[str, dict[str, Any]] = {}
    for element in effective.get("elements") or []:
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


def _provider_auth(candidate: dict[str, Any], registry: secrets.SecretRegistry) -> dict[str, Any]:
    record = {"credentials": candidate.get("credentials"), "secretRefs": candidate.get("secretRefs")}
    return _backend_auth(record, None, registry)


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


def _policy_refs(
    policy_id: str,
    document: dict[str, Any] | None,
    workspace: str | None,
    shared: dict[str, Any],
    api_name: str,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "global": ids.policy("global"),
        "api": policy_id if document else None,
        "fragments": [ids.policy("fragment", name) for name in (document or {}).get("fragmentRefs", [])],
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
