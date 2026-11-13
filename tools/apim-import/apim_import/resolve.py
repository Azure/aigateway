"""Fetch a provider's live model catalogue, without persisting its credential.

`collect` never reads a secret, so a provider that only exposes its models over
an authenticated endpoint comes back `unresolved`. This is the one step that
touches a credential, which is why it is a separate opt-in command: the secret
is resolved into memory from the recipe the inventory already recorded, used for
one GET, and dropped. It is never written to the inventory, a file, a command
line, or a log.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .arm import ArmClient, ArmError

# Injected so tests never make a network call.
Fetcher = Callable[[str, dict], list[str]]


class ResolveError(RuntimeError):
    pass


@dataclass
class Resolution:
    provider_id: str
    endpoint: str | None
    catalogue_url: str | None = None
    models: list[str] = field(default_factory=list)
    status: str = "pending"  # resolved | skipped | failed | needsAuthorization
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "endpoint": self.endpoint,
            "catalogueUrl": self.catalogue_url,
            "models": self.models,
            "status": self.status,
            "detail": self.detail,
        }


def catalogue_url(endpoint: str | None) -> str | None:
    """Where the model list lives for an OpenAI-protocol endpoint.

    A backend URL may already carry the version prefix -- APIM's AI import
    writes `.../openai/v1` for an Azure OpenAI-compatible surface -- so appending
    `/v1/models` blindly produces `/openai/v1/v1/models`.
    """
    if not endpoint:
        return None
    split = urlsplit(endpoint)
    path = (split.path or "").rstrip("/")
    if path.endswith("/models"):
        suffix = path
    elif path.endswith("/v1"):
        suffix = f"{path}/models"
    else:
        suffix = f"{path}/v1/models"
    return urlunsplit((split.scheme, split.netloc, suffix, "", ""))


def auth_headers(provider: dict[str, Any], secret: str) -> dict[str, str]:
    """Send the credential the way this provider's backend sends it.

    The header name comes from the APIM backend, not from a guess: a provider
    reached with `Authorization` must not be probed with `api-key`.
    """
    auth = provider.get("auth") or {}
    names = ((auth.get("parameters") or {}).get("header") or [])
    header = names[0] if names else "Authorization"
    headers = {header: secret, "Accept": "application/json"}
    if (provider.get("apiDialect") or "").startswith("anthropic"):
        # Anthropic's catalogue requires a version header.
        headers.setdefault("anthropic-version", "2023-06-01")
    return headers


def resolve_secret(client: ArmClient, secret_ref: dict[str, Any]) -> str:
    """Run the inventory's own retrieval recipe, in process.

    Reconstructed from the recorded request rather than shelling out the recorded
    command, so the value never reaches a command line where process arguments
    would expose it.
    """
    resolution = secret_ref.get("resolution") or {}
    request = resolution.get("request") or {}
    url = request.get("url")
    method = request.get("httpMethod") or "GET"
    if resolution.get("method") not in {"armAction", "armRead"} or not url:
        raise ResolveError(
            f"{secret_ref['id']} is not retrievable in process ({resolution.get('method')}). "
            "Supply it another way or resolve it manually."
        )
    response = client.request(method, url)
    if not response.ok or not isinstance(response.body, dict):
        raise ResolveError(f"{secret_ref['id']} could not be read: {response.status}")
    value = response.body
    for part in (resolution.get("valuePath") or "$.value").lstrip("$.").split("."):
        if not isinstance(value, dict) or part not in value:
            raise ResolveError(f"{secret_ref['id']} returned no value at {resolution.get('valuePath')}")
        value = value[part]
    if not isinstance(value, str) or not value:
        raise ResolveError(f"{secret_ref['id']} returned an empty value")
    return value


def fetch_models(url: str, headers: dict[str, str], *, timeout: int = 30) -> list[str]:
    """GET an OpenAI-shaped catalogue and return the model identifiers."""
    request = urllib.request.Request(url, method="GET")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise ResolveError(f"{url} returned {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        raise ResolveError(f"{url} could not be read: {exc}") from exc
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ResolveError(f"{url} did not return a model list")
    found = []
    for entry in entries:
        name = entry.get("id") or entry.get("name") if isinstance(entry, dict) else entry
        if isinstance(name, str) and name:
            found.append(name)
    return found


def resolvable(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Providers whose catalogue is one authenticated GET away."""
    return [
        provider
        for provider in (inventory.get("assets") or {}).get("modelProviders") or []
        if (provider.get("models") or {}).get("discoverySource") == "modelsEndpoint"
        and (provider.get("models") or {}).get("status") != "resolved"
    ]


def resolve_models(
    inventory: dict[str, Any],
    *,
    client: ArmClient | None = None,
    allow: set[str] | None = None,
    fetcher: Fetcher | None = None,
) -> list[Resolution]:
    """Resolve catalogues for the authorized providers and update the inventory.

    ``allow`` is the explicit authorization to use a credential; a provider not
    named in it (or in ``{"all"}``) is reported as needing authorization and left
    untouched. Nothing is read without being asked for.
    """
    allow = allow or set()
    fetcher = fetcher or (lambda url, headers: fetch_models(url, headers))
    secrets_by_id = {entry["id"]: entry for entry in inventory.get("secrets") or []}
    results: list[Resolution] = []

    for provider in resolvable(inventory):
        result = Resolution(provider_id=provider["id"], endpoint=provider.get("endpoint"))
        result.catalogue_url = catalogue_url(provider.get("endpoint"))
        authorized = "all" in allow or provider["id"] in allow
        if not authorized:
            result.status = "needsAuthorization"
            result.detail = "Reading this provider's catalogue needs its credential; not authorized."
            results.append(result)
            continue
        if not result.catalogue_url:
            result.status = "failed"
            result.detail = "The provider has no endpoint to query."
            results.append(result)
            continue

        refs = [secrets_by_id[r] for r in (provider.get("auth") or {}).get("secretRefs") or []
                if r in secrets_by_id]
        usable = [ref for ref in refs if (ref.get("resolution") or {}).get("method") in
                  {"armAction", "armRead"}]
        if not usable:
            result.status = "failed"
            result.detail = (
                "No in-process retrieval recipe for this provider's credential."
                if refs else "The provider records no credential to use."
            )
            results.append(result)
            continue

        try:
            secret = resolve_secret(client, usable[0]) if client else ""
            if not secret:
                raise ResolveError("no ARM client available to resolve the credential")
            result.models = fetcher(result.catalogue_url, auth_headers(provider, secret))
        except (ResolveError, ArmError) as exc:
            result.status = "failed"
            result.detail = str(exc)
            results.append(result)
            continue
        finally:
            secret = ""  # noqa: F841 - do not keep the credential alive

        result.status = "resolved"
        result.detail = f"{len(result.models)} models"
        _apply(inventory, provider, result)
        results.append(result)

    return results


def _apply(inventory: dict[str, Any], provider: dict[str, Any], result: Resolution) -> None:
    """Write the catalogue back onto the provider and the APIs that use it."""
    models = provider.setdefault("models", {})
    # A catalogue answers "which models exist", never "what can each one serve".
    # The OpenAI /v1/models response carries no modality, so the reply is a
    # proposal to confirm, not a resolved set: writing it out as resolved
    # published an image model and a speech-to-text model as chat-completions
    # endpoints that would have failed at the upstream.
    models["status"] = "catalogued" if result.models else "empty"
    models["discoverySource"] = "modelsEndpoint"
    models["resolvedFrom"] = result.catalogue_url
    models["catalogue"] = list(result.models)
    models["notes"] = [
        f"Catalogue read from {result.catalogue_url}. The credential was resolved in memory "
        "and not persisted.",
        f"{len(result.models)} model(s) offered. The catalogue states no modality, so which of "
        "them can serve an inference route is not established by this read.",
    ]
    for asset in (inventory.get("assets") or {}).get("models") or []:
        if provider["id"] in (asset.get("providerIds") or []):
            asset_models = asset.setdefault("models", {})
            asset_models.update({
                "status": models["status"],
                "discoverySource": "modelsEndpoint",
                "catalogue": models["catalogue"],
                "resolvedFrom": models["resolvedFrom"],
                "notes": models["notes"],
            })
