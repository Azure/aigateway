"""Source-only model catalogs. Discovery never changes accounts or gateways."""

from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core import MigrationError, digest, invalid_json, now, read_json, run_az, unique_keys, validate_schema


FOUNDRY_VERSION = "2025-04-01-preview"
MAX_MODELS = 10000
ACCOUNT = re.compile(
    r"^/subscriptions/([A-Za-z0-9_.-]+)/resourceGroups/([A-Za-z0-9_.-]+)/"
    r"providers/Microsoft\.CognitiveServices/accounts/([A-Za-z0-9_.-]+)$", re.I)
CAPABILITIES = {
    "chatCompletion": "/chat/completions", "responses": "/responses",
    "completion": "/completions", "embeddings": "/embeddings",
    "imageGenerations": "/images/generations",
}


def explicit_id(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 512
            and not any(c in value for c in ("*", "?", "\n", "\r", "\0")))


def checked_url(value):
    if not isinstance(value, str):
        raise MigrationError("Model discovery requires an HTTPS URL.")
    try:
        parts = urlsplit(value)
        parts.port
    except ValueError as exc:
        raise MigrationError("Malformed model-discovery URL.") from exc
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.fragment or parts.query or "%" in parts.path or "\\" in parts.path
            or ".." in parts.path):
        raise MigrationError("Model discovery requires a scoped HTTPS URL without credentials or query values.")
    return parts


def validate_catalog(catalog):
    validate_schema(catalog, "model-catalog")
    seen = set()
    for provider in catalog["providers"]:
        if provider["id"].lower() in seen:
            raise MigrationError("Duplicate provider catalog identity.")
        seen.add(provider["id"].lower())
        checked_url(provider["endpoint"])
        if provider["kind"] == "Foundry" and (
                not ACCOUNT.fullmatch(provider["accountId"] or "") or ".." in provider["accountId"]):
            raise MigrationError("Foundry catalogs require an exact account ARM ID.")
        if provider["kind"] == "Custom" and provider["accountId"] is not None:
            raise MigrationError("Custom catalogs must not claim a Foundry account.")
        if provider["credentialRef"] is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]*", provider["credentialRef"]):
            raise MigrationError("Catalog credential references must be environment variable names.")
        if provider["provenance"] == "operator-manifest" and provider["complete"]:
            raise MigrationError("An operator list cannot establish exhaustive provider completeness.")
        ids = set()
        for model in provider["models"]:
            if not explicit_id(model["id"]) or model["id"] in ids:
                raise MigrationError("Model IDs must be explicit, unique and case-preserving.")
            ids.add(model["id"])
            if any(not explicit_id(path) or not path.startswith("/") for path in model["endpoints"]):
                raise MigrationError("Catalog operation facts must be explicit paths, not wildcard claims.")
            if provider["kind"] == "Foundry":
                expected = provider["accountId"] + "/deployments/" + model["id"]
                if "/" in model["id"] or str(model["deploymentId"]).lower() != expected.lower():
                    raise MigrationError("Foundry deployment identity escaped its selected account.")
            elif model["deploymentId"] is not None:
                raise MigrationError("Custom catalogs cannot invent Foundry deployments.")
    digest(catalog)
    return catalog


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MigrationError("Model discovery redirects are not authorized; use a reviewed endpoint.")


def http_json(url, headers):
    request = Request(url, headers=headers, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            content = response.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            raise MigrationError("Model discovery response exceeds 2 MiB.")
        return json.loads(content, parse_constant=lambda _: invalid_json(), object_pairs_hook=unique_keys)
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError) as exc:
        raise MigrationError(
            "Custom /models discovery failed or was malformed; supply an explicit operator model manifest."
        ) from exc


def collect_models(provider_id, kind, endpoint, account_id=None, credential_ref=None,
                   credential_header="Authorization", approved=False, runner=run_az, fetch=http_json):
    if not approved:
        raise MigrationError("Explicit approval of provider model reads and credential use is required.")
    if kind == "Foundry" and credential_ref is not None:
        raise MigrationError("Foundry discovery uses scoped Azure login, not upstream credential environment variables.")
    checked_url(endpoint)
    provider = {
        "id": provider_id, "kind": kind, "accountId": account_id, "endpoint": endpoint,
        "credentialRef": credential_ref, "capturedAt": now(),
        "credentialHeader": credential_header,
        "provenance": "foundry-deployments" if kind == "Foundry" else "custom-models",
        "complete": False, "error": None, "models": [],
    }
    catalog = {"schemaVersion": "1.0", "providers": [provider]}
    validate_catalog(catalog)
    headers = {"Accept": "application/json"}
    if credential_ref and kind == "Custom":
        if (not re.fullmatch(r"[A-Z][A-Z0-9_]*", credential_ref)
                or not re.fullmatch(r"[A-Za-z0-9-]+", credential_header)
                or credential_header.lower() in ("host", "content-length", "connection")):
            raise MigrationError("Invalid runtime credential reference/header.")
        secret = os.environ.get(credential_ref)
        if not secret or "\r" in secret or "\n" in secret:
            raise MigrationError("The approved runtime credential is missing or malformed.")
        headers[credential_header] = secret
    if kind == "Foundry":
        match = ACCOUNT.fullmatch(account_id or "")
        if not match:
            raise MigrationError("Select an exact Foundry account ARM ID.")
        origin = runner(["az", "cloud", "show", "--query", "endpoints.resourceManager", "-o", "json"])
        if not isinstance(origin, str):
            raise MigrationError("The selected Azure cloud has no usable ARM endpoint.")
        checked_url(origin.rstrip("/"))
        original = origin.rstrip("/") + account_id + "/deployments?api-version=" + FOUNDRY_VERSION
    else:
        original = endpoint.rstrip("/") + "/models"
    first = urlsplit(original)
    url, seen, model_ids = original, set(), set()
    try:
        if kind == "Foundry":
            account = runner(["az", "rest", "--method", "get", "--url",
                              origin.rstrip("/") + account_id + "?api-version=" + FOUNDRY_VERSION,
                              "--headers", "Accept=application/json", "--subscription", match[1], "-o", "json"])
            if (not isinstance(account, dict) or str(account.get("id", "")).lower() != account_id.lower()
                    or str(account.get("kind", "")).lower() not in ("aiservices", "openai")
                    or not isinstance(account.get("properties"), dict)):
                raise MigrationError("Foundry discovery requires an existing AIServices/OpenAI account.")
            properties = account["properties"]
            advertised = [properties.get("endpoint")]
            if isinstance(properties.get("endpoints"), dict):
                advertised.extend(properties["endpoints"].values())
            if endpoint.rstrip("/") not in {v.rstrip("/") for v in advertised if isinstance(v, str)}:
                raise MigrationError("Selected Foundry endpoint is not advertised by the selected account.")
        while url:
            try:
                parts = urlsplit(url)
                same_origin = (parts.hostname, parts.port or 443) == (first.hostname, first.port or 443)
            except ValueError as exc:
                raise MigrationError("Malformed model-catalog continuation.") from exc
            same_path = parts.path.lower() == first.path.lower() if kind == "Foundry" else parts.path == first.path
            if (parts.scheme != "https" or not same_origin or not same_path
                    or parts.username or parts.password or parts.fragment or url in seen or len(seen) >= 1000
                    or (kind == "Foundry" and parse_qs(parts.query).get("api-version") != [FOUNDRY_VERSION])):
                raise MigrationError("Unsafe, repeated or unreviewed model-catalog continuation.")
            seen.add(url)
            if kind == "Foundry":
                page = runner(["az", "rest", "--method", "get", "--url", url,
                               "--headers", "Accept=application/json", "--subscription", match[1], "-o", "json"])
            else:
                page = fetch(url, headers)
            values = page.get("value" if kind == "Foundry" else "data") if isinstance(page, dict) else None
            if not isinstance(values, list):
                raise MigrationError("Model catalog requires its reviewed array envelope.")
            for entry in values:
                if not isinstance(entry, dict):
                    raise MigrationError("Malformed model entry.")
                if kind == "Foundry":
                    rid = entry.get("id")
                    prefix = account_id + "/deployments/"
                    if not isinstance(rid, str) or not rid.lower().startswith(prefix.lower()):
                        raise MigrationError("Deployment escaped the selected account.")
                    model_id = rid[len(prefix):]
                    properties = entry.get("properties") or {}
                    if not isinstance(properties, dict) or not isinstance(properties.get("model") or {}, dict):
                        raise MigrationError("Malformed Foundry deployment metadata.")
                    model = properties.get("model") or {}
                    if not isinstance(properties.get("capabilities") or {}, dict):
                        raise MigrationError("Malformed Foundry model capabilities.")
                    protocol = model.get("format")
                    endpoints = [
                        path for capability, path in CAPABILITIES.items()
                        if str((properties.get("capabilities") or {}).get(capability, "")).lower() == "true"]
                    row = {"id": model_id, "deploymentId": rid, "family": model.get("name"),
                           "version": model.get("version"), "apiFormat": protocol, "endpoints": endpoints}
                else:
                    row = {"id": entry.get("id"), "deploymentId": None, "family": None,
                           "version": None, "apiFormat": None, "endpoints": []}
                    if credential_ref and isinstance(row["id"], str):
                        sensitive = [headers[credential_header]]
                        if sensitive[0].lower().startswith("bearer "):
                            sensitive.append(sensitive[0][7:])
                        if any(value and value in row["id"] for value in sensitive):
                            raise MigrationError("Provider returned credential-bearing model metadata; use manual input.")
                if (not explicit_id(row["id"]) or row["id"] in model_ids
                        or len(model_ids) >= MAX_MODELS):
                    raise MigrationError("Model discovery returned duplicate/wildcard IDs or exceeded the 10,000-entry processing limit.")
                model_ids.add(row["id"])
                provider["models"].append(row)
            next_link = page.get("nextLink") if kind == "Foundry" else page.get("next")
            for key, value in page.items():
                marker = key.replace("_", "").replace("@", "").replace(".", "").lower()
                if value and marker in ("nextlink", "nexttoken", "continuationtoken", "odatanextlink"):
                    if key != ("nextLink" if kind == "Foundry" else "next"):
                        raise MigrationError("Unreviewed pagination cannot establish catalog completeness.")
            if next_link is not None and (not isinstance(next_link, str) or not next_link):
                raise MigrationError("Unrecognized model-catalog pagination.")
            if kind == "Custom" and page.get("has_more") and not next_link:
                raise MigrationError("Custom catalog pagination requires a reviewed continuation.")
            url = urljoin(original, next_link) if next_link else None
        provider["complete"] = True
        return validate_catalog(catalog)
    except MigrationError as exc:
        provider.update(complete=False, error=str(exc), models=[])
        return validate_catalog(catalog)


def import_models(path, approved_digest):
    document = read_json(path)
    if digest(document) != approved_digest:
        raise MigrationError("Model manifest approval does not match its current content digest.")
    result = validate_catalog(document)
    if any(p["provenance"] != "operator-manifest" for p in result["providers"]):
        raise MigrationError("Manual import must declare operator-manifest provenance, not live authority.")
    return result
