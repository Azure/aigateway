"""Resolve Azure AI Foundry (Cognitive Services) backends to real deployments.

APIM and Foundry live in the same cloud, so for Azure model backends the tool
does not have to guess which models sit behind an endpoint: it resolves the
backend URL to an ARM account and lists that account's deployments. The result
carries exactly what an AI Gateway ``model`` registration needs -- the
deployment's ARM id, model name, and model version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .arm import ArmClient, ArmError, newest_api_version
from .ids import normalize_arm_id

DEFAULT_API_VERSION = "2025-06-01"


@dataclass
class FoundryAccount:
    resource_id: str
    name: str
    resource_group: str
    subscription_id: str
    location: str
    kind: str
    sku: str | None
    hosts: set[str] = field(default_factory=set)
    custom_subdomain: str | None = None
    public_network_access: str | None = None
    disable_local_auth: bool | None = None
    deployments: list[dict[str, Any]] | None = None
    deployments_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resourceId": self.resource_id,
            "name": self.name,
            "resourceGroup": self.resource_group,
            "subscriptionId": self.subscription_id,
            "location": self.location,
            "kind": self.kind,
            "sku": self.sku,
            "customSubDomainName": self.custom_subdomain,
            "publicNetworkAccess": self.public_network_access,
            "disableLocalAuth": self.disable_local_auth,
            "hosts": sorted(self.hosts),
            "deployments": self.deployments,
            "deploymentsError": self.deployments_error,
        }


class FoundryResolver:
    """Index of Cognitive Services accounts, keyed by endpoint hostname."""

    def __init__(self, client: ArmClient, *, api_version: str | None = None) -> None:
        self.client = client
        self.api_version = api_version or newest_api_version(
            "Microsoft.CognitiveServices", "accounts"
        ) or DEFAULT_API_VERSION
        self._by_host: dict[str, FoundryAccount] = {}
        self._by_id: dict[str, FoundryAccount] = {}
        self._scanned: set[str] = set()
        self.errors: list[dict[str, str]] = []

    # -- indexing -----------------------------------------------------------

    def scan_subscription(self, subscription_id: str) -> int:
        if subscription_id in self._scanned:
            return 0
        self._scanned.add(subscription_id)
        url = f"/subscriptions/{subscription_id}/providers/Microsoft.CognitiveServices/accounts"
        try:
            accounts = self.client.list(url, self.api_version)
        except ArmError as exc:
            self.errors.append({"subscriptionId": subscription_id, "error": str(exc)})
            return 0
        for raw in accounts:
            self._index(raw)
        return len(accounts)

    def _index(self, raw: dict[str, Any]) -> FoundryAccount:
        resource_id = raw.get("id") or ""
        existing = self._by_id.get(resource_id.lower())
        if existing:
            return existing
        props = raw.get("properties") or {}
        hosts: set[str] = set()
        for url in [props.get("endpoint")] + list((props.get("endpoints") or {}).values()):
            host = (urlsplit(url or "").hostname or "").lower()
            if host:
                hosts.add(host)
        parts = resource_id.strip("/").split("/")
        account = FoundryAccount(
            resource_id=resource_id,
            name=raw.get("name") or "",
            resource_group=parts[3] if len(parts) > 3 else "",
            subscription_id=parts[1] if len(parts) > 1 else "",
            location=raw.get("location") or "",
            kind=raw.get("kind") or "",
            sku=(raw.get("sku") or {}).get("name"),
            hosts=hosts,
            custom_subdomain=props.get("customSubDomainName"),
            public_network_access=props.get("publicNetworkAccess"),
            disable_local_auth=props.get("disableLocalAuth"),
        )
        self._by_id[resource_id.lower()] = account
        for host in hosts:
            self._by_host.setdefault(host, account)
        return account

    # -- lookup -------------------------------------------------------------

    def by_url(self, url: str | None) -> FoundryAccount | None:
        host = (urlsplit(url or "").hostname or "").lower()
        if not host:
            return None
        return self._by_host.get(host)

    def by_resource_id(self, resource_id: str | None) -> FoundryAccount | None:
        resource_id = normalize_arm_id(resource_id)
        if not resource_id:
            return None
        account = self._by_id.get(resource_id.strip("/").lower()) or self._by_id.get(resource_id.lower())
        if account:
            return account
        # The account may live in a subscription we have not scanned; fetch it directly.
        raw = None
        try:
            raw = self.client.get_json(resource_id, self.api_version)
        except ArmError as exc:
            self.errors.append({"resourceId": resource_id, "error": str(exc)})
            return None
        return self._index(raw) if raw else None

    def load_deployments(self, account: FoundryAccount) -> list[dict[str, Any]]:
        if account.deployments is not None:
            return account.deployments
        try:
            raw = self.client.list(f"{account.resource_id}/deployments", self.api_version)
        except ArmError as exc:
            account.deployments = []
            account.deployments_error = str(exc)
            self.errors.append({"resourceId": account.resource_id, "error": str(exc)})
            return account.deployments
        account.deployments = [_deployment(entry) for entry in raw]
        return account.deployments

    def accounts(self) -> list[FoundryAccount]:
        return list(self._by_id.values())


def _deployment(raw: dict[str, Any]) -> dict[str, Any]:
    props = raw.get("properties") or {}
    model = props.get("model") or {}
    sku = raw.get("sku") or {}
    return {
        "name": raw.get("name"),
        "resourceId": raw.get("id"),
        "modelName": model.get("name"),
        "modelVersion": model.get("version"),
        "modelFormat": model.get("format"),
        "modelSource": model.get("source"),
        "sku": {"name": sku.get("name"), "capacity": sku.get("capacity")},
        "provisioningState": props.get("provisioningState"),
        "raiPolicyName": props.get("raiPolicyName"),
        "versionUpgradeOption": props.get("versionUpgradeOption"),
        "capabilities": props.get("capabilities"),
    }


def target_model_registration(account: FoundryAccount, deployment: dict[str, Any]) -> dict[str, Any]:
    """Shape a resolved deployment the way an AI Gateway model registration wants it."""
    return {
        "providerKind": "Foundry",
        "deployment": {
            "modelName": deployment.get("modelName"),
            "modelVersion": deployment.get("modelVersion"),
            "resourceId": deployment.get("resourceId"),
        },
        "providerEndpoint": f"https://{sorted(account.hosts)[0]}/" if account.hosts else None,
        "providerResourceIds": [account.resource_id],
    }
