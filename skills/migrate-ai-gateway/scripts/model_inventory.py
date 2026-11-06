"""Source-only model catalogs. Discovery never changes accounts or gateways."""

from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core import (
    MigrationError, child_resource_id, digest, invalid_json, now, read_json,
    resource_id, run_az, unique_keys, validate_schema,
)


FOUNDRY_VERSION = "2025-04-01-preview"
APIM_VERSION = "2024-05-01"
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


def checked_credential_source(source):
    if not isinstance(source, dict) or set(source) != {"sourceId", "resourceId", "field", "scheme"}:
        raise MigrationError("APIM credential reads require an exact source, resource, field, and scheme.")
    if not isinstance(source["sourceId"], str):
        raise MigrationError("APIM credential reads require the selected source service ARM ID.")
    target = resource_id(source["sourceId"])
    rid = source["resourceId"]
    if not child_resource_id(rid, source["sourceId"]):
        raise MigrationError("Credential resource must belong to the exact selected APIM source.")
    match = re.fullmatch(r"/(namedValues|subscriptions)/([A-Za-z0-9_.-]{1,256})",
                         rid[len(source["sourceId"]):], re.I)
    if not match:
        raise MigrationError("Select one service-level APIM named value or subscription, not a collection.")
    kind = match[1].lower()
    fields = ("value",) if kind == "namedvalues" else ("primaryKey", "secondaryKey")
    if source["field"] not in fields or source["scheme"] not in (None, "Bearer", "Basic"):
        raise MigrationError("Invalid APIM credential field or authentication scheme.")
    if kind == "subscriptions" and source["scheme"] is not None:
        raise MigrationError("APIM subscription keys must not use an upstream authentication scheme.")
    return target, kind


def read_apim_credential(source, endpoint, runner):
    target, kind = checked_credential_source(source)
    try:
        origin = runner(["az", "cloud", "show", "--query", "endpoints.resourceManager", "-o", "json"])
        parts = checked_url(origin)
        if parts.path not in ("", "/"):
            raise MigrationError("The Azure cloud ARM endpoint must not contain a resource path.")
        origin = origin.rstrip("/")
        options = ["--headers", "Accept=application/json", "--subscription", target["subscription"],
                   "--only-show-errors", "-o", "json"]
        if kind == "subscriptions":
            service = runner(["az", "rest", "--method", "get", "--url",
                              origin + source["sourceId"] + "?api-version=" + APIM_VERSION, *options])
            if (not isinstance(service, dict)
                    or str(service.get("id", "")).lower() != source["sourceId"].lower()
                    or not isinstance(service.get("properties"), dict)):
                raise MigrationError("Cannot verify the selected APIM gateway origin.")
            properties = service["properties"]
            advertised = [properties.get("gatewayUrl")]
            bindings = properties.get("hostnameConfigurations") or []
            if not isinstance(bindings, list):
                raise MigrationError("Malformed APIM hostname bindings.")
            for binding in bindings:
                if not isinstance(binding, dict):
                    raise MigrationError("Malformed APIM hostname binding.")
                if str(binding.get("type", "")).lower() == "proxy":
                    hostname = binding.get("hostName")
                    if not isinstance(hostname, str) or not re.fullmatch(r"[A-Za-z0-9.-]+", hostname):
                        raise MigrationError("Malformed APIM gateway hostname.")
                    advertised.append("https://" + hostname)
            selected = checked_url(endpoint)
            origins = set()
            for url in advertised:
                if url is not None:
                    advertised_parts = checked_url(url)
                    origins.add((advertised_parts.hostname, advertised_parts.port or 443))
            if (selected.hostname, selected.port or 443) not in origins:
                raise MigrationError("APIM subscription keys may only authenticate the selected source's gateway origin.")
        action = "listValue" if kind == "namedvalues" else "listSecrets"
        response = runner(["az", "rest", "--method", "post", "--url",
                           origin + source["resourceId"] + "/" + action + "?api-version=" + APIM_VERSION,
                           *options])
    except MigrationError as exc:
        raise MigrationError("Scoped APIM credential read failed; verify source, gateway origin, "
                             "and secret-read permission.", code=exc.code) from None
    secret = response.get(source["field"]) if isinstance(response, dict) else None
    if not isinstance(secret, str) or not secret:
        raise MigrationError("APIM credential response lacks the selected secret value; no catalog request was sent.")
    fields = ("value",) if kind == "namedvalues" else ("primaryKey", "secondaryKey")
    sensitive = [response[field] for field in fields
                 if isinstance(response.get(field), str) and response[field]]
    return secret, sensitive


def credential_header_value(secret, scheme=None):
    if (not isinstance(secret, str) or not secret
            or any(ord(char) < 32 or ord(char) == 127 for char in secret)):
        raise MigrationError("The approved runtime credential is missing or malformed.")
    return (scheme + " " if scheme else "") + secret


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
        if "credentialSource" in provider:
            if provider["kind"] != "Custom" or provider["credentialRef"] is not None:
                raise MigrationError("APIM credential sources are Custom-only and cannot also use an environment credential.")
            checked_credential_source(provider["credentialSource"])
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
    except HTTPError as exc:
        exc.close()
        raise MigrationError(f"Custom /models discovery failed (HTTP {exc.code}); "
                             "the catalog read is inconclusive.") from None
    except (URLError, TimeoutError, ValueError, UnicodeError) as exc:
        raise MigrationError(
            "Custom /models discovery failed or was malformed; supply an explicit operator model manifest."
        ) from exc


def collect_models(provider_id, kind, endpoint, account_id=None, credential_ref=None,
                   credential_header="Authorization", approved=False, runner=run_az, fetch=http_json,
                   *, credential_source=None, credential_read_approved=False):
    if not approved:
        raise MigrationError("Explicit approval of provider model reads and credential use is required.")
    if kind == "Foundry" and (credential_ref is not None or credential_source is not None):
        raise MigrationError("Foundry discovery uses scoped Azure login, not an upstream credential.")
    if credential_source is not None and not credential_read_approved:
        raise MigrationError("Separately approve the exact APIM secret read and its use at the selected catalog endpoint.")
    if credential_read_approved and credential_source is None:
        raise MigrationError("Secret-read approval requires an explicit APIM credential resource.")
    checked_url(endpoint)
    provider = {
        "id": provider_id, "kind": kind, "accountId": account_id, "endpoint": endpoint,
        "credentialRef": credential_ref, "capturedAt": now(),
        "credentialHeader": credential_header,
        "provenance": "foundry-deployments" if kind == "Foundry" else "custom-models",
        "complete": False, "error": None, "models": [],
    }
    if credential_source is not None:
        provider["credentialSource"] = credential_source
    catalog = {"schemaVersion": "1.0", "providers": [provider]}
    validate_catalog(catalog)
    headers = {"Accept": "application/json"}
    sensitive = []
    secret = None
    if credential_ref is not None or credential_source is not None:
        if (not re.fullmatch(r"[A-Za-z0-9-]+", credential_header)
                or credential_header.lower() in ("host", "content-length", "connection",
                                                  "transfer-encoding", "proxy-authorization", "proxy-connection")):
            raise MigrationError("Invalid runtime credential reference/header.")
    if credential_ref and kind == "Custom":
        secret = os.environ.get(credential_ref)
        headers[credential_header] = credential_header_value(secret)
        sensitive.append(secret)
        if secret.lower().startswith(("bearer ", "basic ")):
            sensitive.append(secret.split(" ", 1)[1])
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
        if credential_source is not None:
            secret, sensitive = read_apim_credential(credential_source, endpoint, runner)
            headers[credential_header] = credential_header_value(secret, credential_source["scheme"])
            sensitive.append(headers[credential_header])
            if secret.lower().startswith(("bearer ", "basic ")):
                sensitive.append(secret.split(" ", 1)[1])
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
                    if sensitive and isinstance(row["id"], str):
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
            if next_link and any(value and value in next_link for value in sensitive):
                raise MigrationError("Provider returned credential-bearing pagination; no continuation was followed.")
            if kind == "Custom" and page.get("has_more") and not next_link:
                raise MigrationError("Custom catalog pagination requires a reviewed continuation.")
            url = urljoin(original, next_link) if next_link else None
        provider["complete"] = True
        return validate_catalog(catalog)
    except MigrationError as exc:
        error = str(exc)
        if any(value and value in error for value in sensitive):
            error = "Model discovery failed; credential-bearing diagnostics were withheld."
        provider.update(complete=False, error=error, models=[])
        return validate_catalog(catalog)
    finally:
        headers.clear()
        sensitive.clear()
        secret = None


def import_models(path, approved_digest):
    document = read_json(path)
    if digest(document) != approved_digest:
        raise MigrationError("Model manifest approval does not match its current content digest.")
    result = validate_catalog(document)
    if any(p["provenance"] != "operator-manifest" for p in result["providers"]):
        raise MigrationError("Manual import must declare operator-manifest provenance, not live authority.")
    return result
