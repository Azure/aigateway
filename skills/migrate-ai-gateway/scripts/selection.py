"""Finite source selections and deterministic, non-destructive resource graphs."""

from __future__ import annotations

import base64
import copy
import json
import re

from core import MigrationError, SECRET, child_resource_id, clean, digest, invalid_json, resource_id, semantic, subset, unique_keys, validate_schema
from model_inventory import explicit_id, validate_catalog
from gateway import catalog
from native_sync import selected_action, validate_preview, removal_proposals


NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}")


def pending_results(behaviors):
    return {bid: {"status": "pending", "method": "control-plane",
                  "evidenceDigest": None, "recordedAt": None} for bid in behaviors}


def source_service_id(bundle):
    records = [item["id"] for item in bundle["source-inventory.json"]["items"] if item["domain"] == "service"]
    if len(records) != 1:
        raise MigrationError("Source evidence must contain one authoritative service record.")
    return records[0]


def check_inline_contract(value, context=""):
    if isinstance(value, dict):
        if context in ("properties", "schemas", "responses", "headers", "parameters", "requestBodies", "securitySchemes"):
            for child in value.values():
                if not isinstance(child, dict):
                    raise MigrationError("Inline contract maps require schema/response objects, not literal payloads.")
                check_inline_contract(child)
            return
        for key, child in value.items():
            if key == "$ref" and (not isinstance(child, str) or not child.startswith("#/components/schemas/")):
                raise MigrationError("Inline references must be local schemas; external fetches are not authorized.")
            if key.lower() in ("default", "example", "examples", "value", "$runtimesecret") and not isinstance(child, dict):
                raise MigrationError("Inline contracts must not carry payload/default/credential values.")
            if key.lower() in ("default", "example", "examples", "$runtimesecret") or key.lower().startswith("x-"):
                raise MigrationError("Opaque inline payloads/extensions need a separately reviewed public contract.")
            if SECRET.search(key) and isinstance(child, (str, int, float)):
                raise MigrationError("Credential-bearing inline fields must use source credentials, not embedded values.")
            check_inline_contract(child, key)
    elif isinstance(value, list):
        for child in value:
            check_inline_contract(child)
    elif isinstance(value, str) and clean(value) != value:
        raise MigrationError("Sensitive literal content cannot be published inside an inline specification.")


def schema_projection(value, property_map=False):
    """Compare public structural constraints without publishing redacted literals."""
    if isinstance(value, list):
        return [schema_projection(child) for child in value]
    if not isinstance(value, dict):
        if isinstance(value, str) and value.startswith("#/definitions/"):
            return "#/components/schemas/" + value.removeprefix("#/definitions/")
        return value
    if value == {"redacted": True}:
        raise MigrationError("An opaque schema constraint needs reviewed source evidence.")
    if property_map:
        return {key: schema_projection(child) for key, child in value.items()}
    return {key: schema_projection(child, key == "properties") for key, child in value.items()
            if key not in ("title", "description", "summary", "example", "examples")}


def current_resource(destination, group, name=None, provider=None):
    collection = {"model-policy": "model", "connection": "private-endpoint-connection"}.get(group, group)
    if not destination["exists"]:
        return None
    if collection not in destination["collections"] or any(
            error["domain"] == collection for error in destination["errors"]):
        raise MigrationError("Recollect complete destination evidence for " + collection + ".")
    values = destination["collections"][collection]
    if group in ("network", "policy"):
        return values
    suffix = {
        "model-policy": f"/workspaces/default/modelProviders/{provider}/models/{name}",
        "connection": f"/privateEndpointConnections/{name}",
        "telemetry-exporter": f"/workspaces/default/telemetryExporters/{name}",
        "api-key": f"/apiKeys/{name}",
        "mcp": f"/workspaces/default/toolServers/{name}",
    }[group]
    matches = [item for item in values if str(item.get("id", "")).lower()
               == (destination["destinationId"] + suffix).lower()]
    if len(matches) > 1:
        raise MigrationError("Duplicate destination identities.")
    return matches[0] if matches else None


def scoped_nodes(bundle, selection):
    from planning import policy_state, public_projection, reviewed_arguments, runtime_references

    destination = bundle["destination-inventory.json"]
    behaviors = {b["id"]: b for b in bundle["source-inventory.json"]["behaviors"]}
    source = {item["id"]: item for item in bundle["source-inventory.json"]["items"]}
    nodes, owned = [], set()
    allowed_policy = {"policies", "inbound", "backend", "outbound", "on-error", "base",
                      "rate-limit", "rate-limit-by-key", "llm-token-limit", "azure-openai-token-limit",
                      "ip-filter", "address", "address-range", "llm-content-safety"}

    def add(entry, group, arguments, desired, dependencies, name=None, provider=None):
        ids = entry["behaviorIds"]
        if (set(ids) & owned or any(bid not in behaviors or behaviors[bid]["sourceId"] not in entry["sourceIds"]
                                   for bid in ids) or set(entry["sourceIds"]) != {behaviors[bid]["sourceId"] for bid in ids}):
            raise MigrationError("Scoped selections require disjoint exact source behavior ownership.")
        for bid in ids:
            behavior = behaviors[bid]
            item = source[behavior["sourceId"]]
            if group in ("policy", "model-policy") and not item["policyShape"]:
                selected_apis = {sid for selected in selection["models"] for sid in selected["sourceIds"]}
                if (not entry.get("newGovernance") or not arguments
                        or any(not key.startswith("cost-") for key in arguments)
                        or item["domain"] not in ("apis", "service") or "property" in behavior
                        or (item["domain"] == "apis" and item["id"] not in selected_apis)):
                    raise MigrationError("Non-policy bindings support only explicit new cost governance for selected model traffic or its gateway.")
            if group in ("policy", "model-policy") and item["policyShape"]:
                if behavior.get("statement") not in allowed_policy and "statement" in behavior:
                    raise MigrationError("Unreviewed policy statements cannot become supported mappings.")
                if any(node["hasText"] or any(isinstance(v, dict) for k, v in node["attributes"].items() if k != "id")
                       for node in item["policyShape"]) and entry.get("translationDigest") != digest({
                           "sourceIds": entry["sourceIds"], "behaviorIds": ids,
                           "settings": entry["settings"], "scopeDecision": entry["scopeDecision"]}):
                    raise MigrationError("Opaque policy inputs need an explicitly approved typed translation digest.")
            if group in ("network", "connection"):
                properties = ({"privateEndpointConnections"} if group == "connection" else
                              {"publicNetworkAccess", "virtualNetworkType", "virtualNetworkConfiguration"})
                if behavior.get("property") not in properties:
                    raise MigrationError("A network selection cannot own unrelated service behavior.")
            if (group == "telemetry-exporter" and item["domain"] == "service"
                    and behavior.get("property") not in ("loggers", "diagnostics", "telemetry")):
                raise MigrationError("Exporter selection cannot own unrelated service behavior.")
        owned.update(ids)
        prefix = {"model-policy": "model-policy", "policy": "policy", "network": "network",
                  "connection": "connection", "telemetry-exporter": "telemetry"}[group]
        identifier = prefix + ":" + (name or "default") + (":" + provider if provider else "")
        current = current_resource(destination, group, name, provider)
        if current is None and group != "telemetry-exporter":
            raise MigrationError("Create/verify the destination prerequisite first, then recollect and re-plan.")
        verify = current is not None and subset(desired, current)
        if group == "telemetry-exporter":
            own_progress = any(
                todo["id"] == identifier and todo["arguments"] == arguments
                and todo["status"] in ("resource-verified", "behavior-verified", "in-progress", "mutation-unknown")
                for todo in bundle["todos.json"]["items"])
            if current is not None and not own_progress and not entry.get("reuseExisting") and not entry.get("updateExisting"):
                raise MigrationError("Exporter reuse or update must be explicit.")
            if not verify and current is not None and not entry.get("updateExisting"):
                raise MigrationError("Existing exporter differs; explicit update is required.")
            if not verify:
                reviewed_arguments("telemetry.create" if current is None else "telemetry.update", arguments)
            elif runtime_references(arguments) and not own_progress:
                raise MigrationError("Exporter secret-only changes cannot be inferred from redacted state.")
        cap = ("model-policy.verify" if verify else "model.policy") if group == "model-policy" else (
            prefix + (".verify" if verify else ".create" if current is None else ".update"))
        nodes.append({"id": identifier, "group": group, "capabilityId": cap, "name": name,
                      "provider": provider, "arguments": {} if verify else arguments,
                      "intent": arguments,
                      "desired": desired, "dependencies": dependencies, "entry": entry,
                      "current": current})

    gateway = "gateway:" + resource_id(destination["destinationId"], "aigateways")["gateway"]
    for entry in selection.get("policies", []):
        group = "policy" if entry["scope"] == "workspace" else "model-policy"
        name, provider = entry.get("model"), entry.get("provider")
        if group == "model-policy" and (not NAME.fullmatch(name or "") or not NAME.fullmatch(provider or "")):
            raise MigrationError("Model policy requires exact existing model/provider names.")
        if group == "policy" and (name is not None or provider is not None):
            raise MigrationError("Workspace policies do not take model/provider selectors.")
        args = copy.deepcopy(entry["settings"])
        cap = "policy.update" if group == "policy" else "model.policy"
        allowed = next(c["options"] for c in catalog()["capabilities"] if c["id"] == cap)
        if set(args) - set(allowed):
            raise MigrationError("Unreviewed policy settings.")
        reviewed_arguments(cap, args)
        current = current_resource(destination, group, name, provider)
        if current is None:
            raise MigrationError("Policy targets need a verified foundation and fresh destination evidence.")
        existing = current["properties"].get("policies", [])
        for key, default in (("token-period", "minute"), ("token-counter-key", ["Identity"]),
                             ("cost-counter-key", ["Identity"])):
            parent = "cost-limit" if key.startswith("cost") else "token-limit"
            if parent in args:
                args.setdefault(key, default)
        desired = semantic(copy.deepcopy(current))
        desired["properties"]["policies"] = policy_state(args, existing, group == "policy")
        add(entry, group, args, desired, [gateway], name, provider)
    if "network" in selection:
        entry = selection["network"]
        args = entry["settings"]
        if not args or set(args) - {"subnet", "public-network-access", "disable-vnet-integration"}:
            raise MigrationError("Select explicit reviewed network settings.")
        reviewed_arguments("network.update", args)
        desired = semantic(copy.deepcopy(current_resource(destination, "network")))
        if desired is None:
            raise MigrationError("Network updates require an existing verified gateway.")
        if "public-network-access" in args:
            desired["publicNetworkAccess"] = args["public-network-access"]
        if "subnet" in args:
            desired.update(virtualNetworkType="External", virtualNetworkConfiguration={"subnetResourceId": args["subnet"]})
        if args.get("disable-vnet-integration"):
            desired.update(virtualNetworkType="None", virtualNetworkConfiguration=None)
        dependencies = [gateway]
        if args.get("public-network-access") == "Disabled":
            dependencies.extend("connection:" + c["name"] for c in selection.get("connections", []))
        add(entry, "network", args, desired, dependencies)
    for entry in selection.get("connections", []):
        current = current_resource(destination, "connection", entry["name"])
        if current is None or current.get("properties", {}).get("privateEndpoint", {}).get("id") != entry["peerId"]:
            raise MigrationError("Select the exact existing destination private-endpoint peer.")
        desired = semantic(copy.deepcopy(current))
        desired["properties"].update(provisioningState="Succeeded",
                                     privateLinkServiceConnectionState={"status": "Approved", "description": entry["description"]})
        add(entry, "connection", {"description": entry["description"]}, desired, [gateway], entry["name"])
    for entry in selection.get("telemetry", []):
        if not isinstance(entry["name"], str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,78}[A-Za-z0-9])?", entry["name"]):
            raise MigrationError("Exporter names must be 1-80 alphanumeric/hyphen characters.")
        args = entry["settings"]
        wire = {"kind": "kind", "application-insights": "applicationInsights", "payload-capture": "payloadCapture"}
        if set(args) - set(wire) or type(args.get("payload-capture")) is not bool:
            raise MigrationError("Unreviewed telemetry settings or missing payload-capture decision.")
        desired = {"properties": {wire[k]: public_projection(v) for k, v in args.items()}}
        add(entry, "telemetry-exporter", args, desired, [gateway], entry["name"])
    return nodes


def policy_translation(selection, source_id, behavior_ids):
    entries = [entry for entry in selection.get("policies", []) if source_id in entry["sourceIds"]]
    covered = set()
    for entry in entries:
        if entry.get("translationDigest") == digest({
                "sourceIds": entry["sourceIds"], "behaviorIds": entry["behaviorIds"],
                "settings": entry["settings"], "scopeDecision": entry["scopeDecision"]}):
            covered.update(entry["behaviorIds"])
    return set(behavior_ids) <= covered


def check_routing_failures(item):
    if item["domain"] == "backends" and item["resource"].get("properties", {}).get("circuitBreaker") is not None:
        raise MigrationError("Source circuit-breaker failure conditions and recovery have no reviewed model-routing "
                             "translation; retain that source behavior instead of claiming failover equivalence.")
    shape = item["policyShape"]
    if any(node["statement"] == "retry" or (
            node["statement"] == "on-error" and any(
                child["path"].startswith(node["path"] + "/") for child in shape)) for node in shape):
        raise MigrationError("Source retries and nonempty error handlers have no reviewed model-routing translation.")


def backend_ids(item):
    scope = re.match(
        r"^(/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.ApiManagement/service/"
        r"[^/]+(?:/workspaces/[^/]+)?)(?:/|$)", item["id"], re.I)
    if scope is None:
        raise MigrationError("Model routing requires an exact source service/workspace resource identity.")
    parent = scope[1] + "/backends"
    ids = {(parent + "/" + reference["name"]).lower() for node in item["policyShape"]
           for reference in node["references"] if reference["domain"] == "backends"}
    backend = item["resource"].get("properties", {}).get("backendId")
    if item["domain"] == "apis" and backend:
        if not isinstance(backend, str):
            raise MigrationError("Source backend routing is unresolved; do not infer a pool from an expression.")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", backend):
            ids.add((parent + "/" + backend).lower())
        elif child_resource_id(backend, parent) and "/" not in backend[len(parent) + 1:]:
            ids.add(backend.lower())
        else:
            raise MigrationError("Source backend routing is unresolved or outside its exact APIM scope.")
    return ids


def source_pool_routes(bundle, selection):
    source = {item["id"].lower(): item for item in bundle["source-inventory.json"]["items"]}
    providers = {provider.get("name", provider["id"]): provider for provider in selection["providers"]}
    routes = {}
    for alias in selection.get("aliases", []):
        pool_id = alias.get("sourcePoolId")
        observed_pools = {
            sid.lower() for sid in alias["sourceIds"] if sid.lower() in source
            and source[sid.lower()]["domain"] == "backends"
            and (source[sid.lower()]["resource"].get("properties", {}).get("type") == "Pool"
                 or source[sid.lower()]["resource"].get("properties", {}).get("pool") is not None)}
        if pool_id is None:
            if observed_pools or any("sourceBackendId" in backend for backend in alias["backends"]):
                raise MigrationError("Source pool translation requires sourcePoolId and exact sourceBackendId bindings.")
            continue
        pool = source.get(pool_id.lower())
        if (not pool or pool["domain"] != "backends" or pool["authority"] != "authoritative"
                or observed_pools != {pool_id.lower()}):
            raise MigrationError("Select exactly one authoritative source pool in the alias sourceIds.")
        check_routing_failures(pool)
        properties = pool["resource"].get("properties", {})
        config = properties.get("pool")
        if (properties.get("type") != "Pool" or not isinstance(config, dict)
                or set(config) != {"services"} or not isinstance(config["services"], list)
                or not config["services"] or len(config["services"]) != len(alias["backends"])):
            raise MigrationError("Source pool translation requires explicit, complete reviewed pool membership.")
        if not any(pool_id.lower() in backend_ids(source[sid.lower()])
                   for sid in alias["sourceIds"] if sid.lower() in source and sid.lower() != pool_id.lower()):
            raise MigrationError("Alias source evidence must route to the selected source pool.")
        members = {}
        for member in config["services"]:
            if (not isinstance(member, dict) or set(member) != {"id", "priority", "weight"}
                    or not isinstance(member["id"], str)):
                raise MigrationError("Source pool members require exact backend IDs, priorities and weights.")
            sid = member["id"].lower()
            backend = source.get(sid)
            if (sid in members or not backend or backend["domain"] != "backends"
                    or backend["scope"].lower() != pool["scope"].lower()
                    or backend["authority"] != "authoritative"):
                raise MigrationError("Source pool members must be distinct authoritative backends in the same scope.")
            settings = backend["resource"].get("properties", {})
            if settings.get("type") == "Pool" or settings.get("pool") is not None:
                raise MigrationError("Nested source pools need a separately supported routing translation.")
            check_routing_failures(backend)
            if (type(member["priority"]) is not int or not 0 <= member["priority"] <= 100
                    or type(member["weight"]) is not int or not 1 <= member["weight"] <= 100):
                raise MigrationError("Source pool priorities/weights must be explicit and in reviewed ranges; "
                                     "null/default values and zero weights need a separate routing decision.")
            members[sid] = member
        selected_members = set()
        for backend in alias["backends"]:
            sid = backend.get("sourceBackendId", "").lower()
            provider = providers.get(backend["provider"])
            if (sid not in members or sid in selected_members or not provider
                    or sid not in {identifier.lower() for identifier in provider["sourceIds"]}):
                raise MigrationError("Every source pool member must bind exactly once to its selected provider/backend.")
            if any(backend[key] != members[sid][key] for key in ("priority", "weight")):
                raise MigrationError("Source pool translation must preserve observed priorities and weights.")
            selected_members.add(sid)
            routes.setdefault((backend["provider"], backend["model"]), set()).add(pool_id.lower())
    return routes


def validate_selection(bundle, selection, verify_graph=True):
    validate_schema(selection, "selection")
    catalogs = validate_catalog(bundle["model-catalog.json"])
    operations = catalog()["modelOperations"]
    if (selection["models"] or selection["mcp"]) and not selection["keys"]:
        raise MigrationError("Select explicit gateway-key admission; anonymous client equivalence is not a reviewed CLI capability.")
    if selection["catalogDigest"] != digest(semantic(catalogs)):
        raise MigrationError("Selection is bound to a different model catalog; review and reselect.")
    providers = {p["id"]: p for p in catalogs["providers"]}
    source = {i["id"]: i for i in bundle["source-inventory.json"]["items"]}
    pool_routes = source_pool_routes(bundle, selection)
    selected_providers, provider_names, selected_models, aliases, routing_names = set(), set(), set(), set(), set()
    previews = bundle["mapping.json"].get("nativeSyncPreviews", [])
    if not isinstance(previews, list):
        raise MigrationError("Native sync evidence must be a list of preview documents.")
    for preview in previews:
        validate_preview(preview, catalogs, bundle["destination-inventory.json"],
                         bundle["capability-contract.json"]["cli"])
        if preview["status"] != "ready":
            raise MigrationError(preview["error"])
        if not any(p["id"] == preview["providerKey"]
                   and p.get("name", p["id"]).lower() == preview["providerName"].lower()
                   for p in selection["providers"]):
            raise MigrationError("Native preview belongs to an unselected destination provider.")
    if len({p["providerKey"] for p in previews}) != len(previews):
        raise MigrationError("Native sync previews must have unique provider identities.")

    def bindings(record):
        if any(identifier not in source for identifier in record["sourceIds"]):
            raise MigrationError("Selection references an unknown source resource.")

    def name(value):
        if not isinstance(value, str) or not NAME.fullmatch(value) or ".." in value:
            raise MigrationError("Gateway resource names must be explicit, unambiguous identifiers.")

    for selected in selection["providers"]:
        bindings(selected)
        target_name = selected.get("name", selected["id"])
        name(target_name)
        if target_name.lower() in provider_names:
            raise MigrationError("Distinct provider/catalog boundaries cannot share a target registration.")
        provider_names.add(target_name.lower())
        if selected["id"] not in providers or selected["id"] in selected_providers:
            raise MigrationError("Select each known provider at most once.")
        selected_providers.add(selected["id"])
        provider, settings = providers[selected["id"]], selected["settings"]
        if provider["error"] or settings.get("kind") != provider["kind"]:
            raise MigrationError("Provider evidence is unavailable or its kind differs.")
        config = settings.get(provider["kind"].lower())
        if not isinstance(config, dict) or config.get("endpoint") != provider["endpoint"]:
            raise MigrationError("Provider settings must preserve the selected upstream endpoint.")
        observed_endpoints = {source[sid]["resource"].get("properties", {}).get("url", "").rstrip("/")
                              for sid in selected["sourceIds"] if source[sid]["domain"] == "backends"}
        if observed_endpoints and observed_endpoints != {provider["endpoint"].rstrip("/")}:
            raise MigrationError("Provider endpoint differs from the selected source backend boundary.")
        backend_records = [source[sid] for sid in selected["sourceIds"] if source[sid]["domain"] == "backends"]
        if len(backend_records) > 1:
            raise MigrationError("Separate source backend/credential boundaries need separate provider selections.")
        for backend_record in backend_records:
            check_routing_failures(backend_record)
            properties = backend_record["resource"].get("properties", {})
            if properties.get("type") == "Pool" or properties.get("pool") is not None:
                raise MigrationError("Source pools map to explicit aliases, not provider credential boundaries.")
            facts = backend_record.get("facts", {})
            if not all(key in facts for key in ("headerNames", "queryParameterNames", "credentialExpressions", "certificateReferences")):
                raise MigrationError("Recollect non-secret upstream authentication metadata before provider mapping.")
            if (not isinstance(facts["headerNames"], list) or not all(isinstance(h, str) for h in facts["headerNames"])
                    or not isinstance(facts["queryParameterNames"], list)
                    or type(facts["credentialExpressions"]) is not bool
                    or type(facts["certificateReferences"]) is not bool):
                raise MigrationError("Malformed source credential metadata; recollect instead of guessing its mechanism.")
            if facts["credentialExpressions"] or facts["queryParameterNames"] or facts["certificateReferences"]:
                raise MigrationError("Dynamic, query or certificate credentials need a supported separate identity mapping.")
            if len(facts["headerNames"]) > 1:
                raise MigrationError("A single provider API-key header cannot represent multiple source credential headers.")
        auth = config.get("authentication", {})
        if not isinstance(auth, dict) or auth.get("kind") not in (
                ("ApiKey", "ManagedIdentity") if provider["kind"] == "Foundry" else ("ApiKey",)):
            raise MigrationError("Provider authentication needs a reviewed explicit mechanism.")
        if auth["kind"] == "ApiKey":
            settings_key = auth.get("apiKey")
            secret_input = settings_key.get("value") if isinstance(settings_key, dict) else None
            runtime_input = (isinstance(secret_input, dict) and set(secret_input) == {"$runtimeSecret"}
                             and isinstance(secret_input["$runtimeSecret"], str)
                             and re.fullmatch(r"[A-Z][A-Z0-9_]*", secret_input["$runtimeSecret"]))
            if (not isinstance(settings_key, dict) or not isinstance(settings_key.get("headerName"), str)
                    or not re.fullmatch(r"[A-Za-z0-9-]+", settings_key["headerName"])
                    or (not selected.get("reuseExisting") and not runtime_input)):
                raise MigrationError("Provider API-key authentication requires a header and runtime-only secret input.")
        for backend_record in backend_records:
            header_names = backend_record["facts"]["headerNames"]
            if header_names and (auth["kind"] != "ApiKey" or
                          auth["apiKey"]["headerName"].lower() != header_names[0].lower()):
                raise MigrationError("Provider authentication must preserve the observed source header mechanism.")
        if provider["kind"] == "Foundry" and config.get("resourceIds") != [provider["accountId"]]:
            raise MigrationError("Foundry import/sync requires exactly the selected account boundary.")
    for selected in selection["models"]:
        bindings(selected)
        for value in ([selected["name"]] if selected.get("explicitAlias") else [selected["name"], selected["alias"]]):
            name(value)
        provider_id = selected["provider"]
        if provider_id not in selected_providers:
            raise MigrationError("Model provider must be selected explicitly.")
        provider = providers[provider_id]
        model = next((m for m in provider["models"] if m["id"] == selected["id"]), None)
        key = (provider_id, selected["name"].lower())
        if not model or key in selected_models or (
                not selected.get("explicitAlias") and not explicit_id(selected["routingName"])):
            raise MigrationError("Select a concrete catalog model and unique registration.")
        if provider["kind"] == "Foundry":
            target_provider = next(p.get("name", p["id"]) for p in selection["providers"] if p["id"] == provider_id)
            selected_action(bundle, provider_id, target_provider, selected)
        selected_models.add(key)
        if not selected.get("explicitAlias") and (
                selected["alias"].lower() in aliases or selected["routingName"].casefold() in routing_names):
            raise MigrationError("Alias ARM/callable names collide; choose explicit distinct names.")
        if not selected.get("explicitAlias"):
            aliases.add(selected["alias"].lower())
            routing_names.add(selected["routingName"].casefold())
        if selected["apiFormat"] not in operations or any(
                path not in operations[selected["apiFormat"]] for path in selected["endpoints"]):
            raise MigrationError("Only finite reviewed model protocol operations can be selected.")
        known_paths = set(model["endpoints"])
        if known_paths and any(path.removeprefix("/openai/v1").removeprefix("/anthropic/v1")
                               not in {p.removeprefix("/anthropic/v1") for p in known_paths}
                               for path in selected["endpoints"]):
            raise MigrationError("Selected operations exceed the upstream catalog's observed capabilities.")
        target_provider = next(p.get("name", p["id"]) for p in selection["providers"] if p["id"] == provider_id)
        routed_pools = pool_routes.get((target_provider, selected["name"]), set())
        for sid in selected["sourceIds"]:
            item = source[sid]
            check_routing_failures(item)
            properties = item["resource"].get("properties", {})
            if (item["domain"] == "backends" and (
                    properties.get("type") == "Pool" or properties.get("pool") is not None)
                    and sid.lower() not in routed_pools):
                raise MigrationError("Source pool behavior requires its explicitly bound shared alias, not a model-only mapping.")
            if item["domain"] == "apis" and item.get("facts", {}).get("role") in ("rest", "mcp"):
                raise MigrationError("Ordinary REST/MCP APIs are not model registrations.")
            policy_behaviors = [b["id"] for b in bundle["source-inventory.json"]["behaviors"]
                                if b["sourceId"] == sid and "statement" in b]
            if (item["policyShape"] and not item.get("facts", {}).get("routingOnly")
                    and not policy_translation(selection, sid, policy_behaviors)):
                raise MigrationError("Untranslated policy behavior cannot be represented by a model selection.")
            expected_backends = backend_ids(item)
            provider_sources = next(p["sourceIds"] for p in selection["providers"] if p["id"] == provider_id)
            actual_backends = {identifier.lower() for identifier in provider_sources
                               if source[identifier]["domain"] == "backends"}
            if expected_backends and expected_backends != actual_backends and not (
                    len(expected_backends) == 1 and expected_backends <= routed_pools):
                raise MigrationError("Model provider selection crosses the observed backend boundary.")
            if item["domain"] == "api-operations":
                if item["scope"] not in selected["sourceIds"]:
                    raise MigrationError("Operation bindings must include their source API context.")
                properties = item["resource"].get("properties", {})
                path = properties.get("urlTemplate", "").split("?")[0]
                if properties.get("method") != "POST" or path not in {
                        p.removeprefix("/openai/v1").removeprefix("/anthropic/v1")
                        for p in selected["endpoints"]}:
                    raise MigrationError("A model mapping cannot own wildcard or unrelated source operations.")
    for selected in selection["mcp"]:
        bindings(selected)
        name(selected["name"])
        namespaces = set()
        for endpoint in selected["endpoints"]:
            if not isinstance(endpoint, dict) or not explicit_id(endpoint.get("namespace")):
                raise MigrationError("MCP sources require explicit namespaces.")
            if endpoint["namespace"].casefold() in namespaces:
                raise MigrationError("MCP source namespaces must be distinct.")
            namespaces.add(endpoint["namespace"].casefold())
            if endpoint.get("kind") == "mcp":
                from model_inventory import checked_url
                settings = endpoint.get("mcp")
                if not isinstance(settings, dict) or settings.get("transport", "streamableHttp") not in ("streamableHttp", "sse"):
                    raise MigrationError("Remote MCP settings require a reviewed transport.")
                checked_url(settings.get("url"))
                allowed_urls = set()
                matched_apis = set()
                for sid in selected["sourceIds"]:
                    api_record = source[sid]
                    if api_record["domain"] != "apis" or api_record.get("facts", {}).get("role") != "mcp":
                        continue
                    properties = api_record["resource"]["properties"]
                    service_url = properties.get("serviceUrl")
                    message = (((properties.get("mcpProperties") or {}).get("endpoints") or {}).get("message") or {}).get("uriTemplate")
                    if isinstance(service_url, str):
                        if isinstance(message, str) and message.startswith("/") and not message.startswith("//"):
                            candidate_url = service_url.rstrip("/") + message
                        else:
                            candidate_url = service_url
                        allowed_urls.add(candidate_url)
                        if settings["url"] == candidate_url:
                            matched_apis.add(sid)
                    gateway_url = bundle["source-inventory.json"]["service"]["properties"].get("gatewayUrl")
                    if isinstance(gateway_url, str) and isinstance(properties.get("path"), str):
                        candidate_url = gateway_url.rstrip("/") + "/" + properties["path"].strip("/") + "/mcp"
                        allowed_urls.add(candidate_url)
                        if settings["url"] == candidate_url:
                            matched_apis.add(sid)
                if settings["url"] not in allowed_urls:
                    raise MigrationError("Remote MCP URL must match an observed upstream or the selected APIM MCP bridge.")
                tool_operations = {item["resource"]["properties"].get("operationId") for item in source.values()
                                   if item["domain"] == "api-tools" and item["scope"] in matched_apis}
                dependency_apis = {source[oid]["scope"] for oid in tool_operations if oid in source}
                for sid in selected["sourceIds"]:
                    item = source[sid]
                    if ((item["domain"] == "apis" and sid not in matched_apis | dependency_apis)
                            or (item["domain"] == "api-operations" and sid not in tool_operations)
                            or (item["domain"] == "api-tools" and item["scope"] not in matched_apis)
                            or (item["domain"] == "api-schemas" and item["scope"] not in dependency_apis)):
                        raise MigrationError("A remote MCP source cannot own unrelated API/model behaviors.")
            elif endpoint.get("kind") == "openApi":
                spec = endpoint.get("openApi", {}).get("specSource", {})
                if spec.get("type") != "inline" or not isinstance(spec.get("contentBase64"), str):
                    raise MigrationError("Compiled OpenAPI mappings need an approved inline contract, not an unchecked URL.")
                try:
                    contract = json.loads(base64.b64decode(spec["contentBase64"], validate=True),
                                          parse_constant=lambda _: invalid_json(), object_pairs_hook=unique_keys)
                except (ValueError, UnicodeError) as exc:
                    raise MigrationError("Malformed inline OpenAPI contract.") from exc
                if (not isinstance(contract, dict) or not isinstance(contract.get("openapi"), str)
                        or not isinstance(contract.get("paths"), dict)
                        or any(not isinstance(path, str) or not path.startswith("/") or path.startswith("//")
                               or "*" in path or "\\" in path or ".." in path or not isinstance(methods, dict)
                               or "servers" in methods
                               for path, methods in contract["paths"].items())):
                    raise MigrationError("OpenAPI MCP operations must be finite explicit paths.")
                check_inline_contract(contract)
                if any(isinstance(operation, dict) and ("servers" in operation or "callbacks" in operation)
                       for methods in contract["paths"].values() for operation in methods.values()):
                    raise MigrationError("Operation-level servers/callbacks need a separately reviewed source contract.")
                servers = contract.get("servers")
                if (not isinstance(servers, list) or len(servers) != 1
                        or not isinstance(servers[0], dict) or not isinstance(servers[0].get("url"), str)):
                    raise MigrationError("Inline MCP contracts require one explicit source-bound server.")
                from model_inventory import checked_url
                checked_url(servers[0]["url"])
                for sid in selected["sourceIds"]:
                    item = source[sid]
                    if item["domain"] != "api-operations":
                        continue
                    if item["scope"] not in selected["sourceIds"]:
                        raise MigrationError("MCP operations require their selected API context.")
                    api = source[item["scope"]]["resource"]["properties"]
                    endpoints = {api["serviceUrl"].rstrip("/")} if isinstance(api.get("serviceUrl"), str) else set()
                    backend = api.get("backendId")
                    for candidate in source.values():
                        if candidate["domain"] == "backends" and candidate["id"].rsplit("/", 1)[-1] == backend:
                            endpoints.add(candidate["resource"]["properties"].get("url", "").rstrip("/"))
                    if servers[0]["url"].rstrip("/") not in endpoints:
                        raise MigrationError("MCP contract server differs from the observed source backend.")
                expected = {(source[sid]["resource"]["properties"]["method"].lower(),
                             source[sid]["resource"]["properties"]["urlTemplate"].split("?")[0])
                            for sid in selected["sourceIds"] if source[sid]["domain"] == "api-operations"}
                observed = {(method, path) for path, methods in contract["paths"].items()
                            for method in methods if method in ("get", "post", "put", "patch", "delete", "head", "options")}
                if not expected or expected != observed:
                    raise MigrationError("Inline MCP operations must exactly match selected source operation bindings.")
                if any(not isinstance(source[sid]["resource"]["properties"].get("operationId"), str)
                       for sid in selected["sourceIds"] if source[sid]["domain"] == "api-tools"):
                    raise MigrationError("REST-backed MCP translation requires established operation references.")
                tool_operations = {source[sid]["resource"]["properties"]["operationId"]:
                                   source[sid]["resource"]["properties"]["displayName"]
                                   for sid in selected["sourceIds"] if source[sid]["domain"] == "api-tools"}
                if any(source[sid]["resource"].get("properties", {}).get("policies") not in (None, "", [], {})
                       for sid in selected["sourceIds"] if source[sid]["domain"] == "api-tools"):
                    raise MigrationError("Tool-specific policies cannot be dropped during OpenAPI translation; retain the MCP source or map them explicitly.")
                for sid in selected["sourceIds"]:
                    item = source[sid]
                    if item["domain"] != "api-operations":
                        continue
                    properties = item["resource"]["properties"]
                    operation = contract["paths"][properties["urlTemplate"].split("?")[0]][properties["method"].lower()]
                    if not isinstance(operation, dict) or not isinstance(operation.get("responses"), dict):
                        raise MigrationError("Inline OpenAPI operation/response contract is malformed.")
                    if sid in tool_operations and operation.get("operationId") != tool_operations[sid]:
                        raise MigrationError("OpenAPI operation IDs must preserve the selected MCP tool names.")
                    facts = item.get("facts", {})
                    if not all(key in facts for key in ("templateParameters", "queryParameters", "requestHeaders")):
                        raise MigrationError("Recollect operation parameter metadata before compiling OpenAPI tools.")
                    if any(p.get("opaqueConstraints") for field in ("templateParameters", "queryParameters", "requestHeaders")
                           for p in facts[field]):
                        raise MigrationError("Opaque source parameter constraints need reviewed evidence; they cannot be silently dropped.")
                    parameters = operation.get("parameters", [])
                    if not isinstance(parameters, list):
                        raise MigrationError("Inline OpenAPI parameters must be explicit.")
                    actual = {(p.get("in"), p.get("name")): (p.get("schema", {}).get("type"), p.get("required", False))
                              for p in parameters if isinstance(p, dict)}
                    required = {(location, p["name"]): (p["type"], bool(p["required"]))
                                for field, location in (("templateParameters", "path"), ("queryParameters", "query"),
                                                        ("requestHeaders", "header")) for p in facts[field]}
                    if actual != required:
                        raise MigrationError("Inline MCP parameter shapes differ from selected source operations.")
                    response_facts = facts.get("responseContracts")
                    if response_facts is None:
                        raise MigrationError("Recollect source response-contract metadata before compiling OpenAPI tools.")
                    expected_statuses = {str(r["status"]) for r in response_facts}
                    if set(operation["responses"]) != (expected_statuses or {"default"}):
                        raise MigrationError("Inline MCP response statuses differ from the source contract.")
                    schema_pairs = {}
                    for response in response_facts:
                        actual_response = operation["responses"][str(response["status"])]
                        if not isinstance(actual_response, dict):
                            raise MigrationError("Malformed OpenAPI response.")
                        for representation in response["representations"]:
                            media = (actual_response.get("content") or {}).get(representation["contentType"])
                            if not isinstance(media, dict):
                                raise MigrationError("Inline MCP response media types must preserve the source contract.")
                            if representation["schemaId"] or representation["typeName"]:
                                schema_item = next((candidate for candidate in source.values()
                                    if candidate["domain"] == "api-schemas" and candidate["scope"] == item["scope"]
                                    and candidate["id"].rsplit("/", 1)[-1] == representation["schemaId"]), None)
                                if schema_item is None or schema_item["id"] not in selected["sourceIds"]:
                                    raise MigrationError("Referenced response schemas require explicit source bindings.")
                                structure = schema_item["resource"]["properties"]["document"].get("structure", {})
                                definitions = structure.get("components", {}).get("schemas") or structure.get("definitions", {})
                                type_name = representation["typeName"]
                                if not isinstance(definitions, dict) or type_name not in definitions:
                                    raise MigrationError("Response type is not established by its selected source schema.")
                                if media.get("schema") != {"$ref": "#/components/schemas/" + type_name}:
                                    raise MigrationError("Response schema references differ from the selected source type.")
                                schema_pairs[type_name] = definitions
                    checked, pending = set(), list(schema_pairs)
                    while pending:
                        type_name = pending.pop()
                        if type_name in checked:
                            continue
                        checked.add(type_name)
                        definitions = schema_pairs[type_name]
                        expected_schema = schema_projection(definitions[type_name])
                        actual_schema = (contract.get("components") or {}).get("schemas", {}).get(type_name)
                        if not isinstance(actual_schema, dict) or schema_projection(actual_schema) != expected_schema:
                            raise MigrationError("MCP output schema constraints differ from authoritative source structure.")
                        def references(value):
                            if isinstance(value, dict):
                                ref = value.get("$ref")
                                found = {ref.removeprefix("#/components/schemas/")} if isinstance(ref, str) else set()
                                return found | set().union(*(references(child) for child in value.values()))
                            if isinstance(value, list):
                                return set().union(*(references(child) for child in value)) if value else set()
                            return set()
                        for reference in references(expected_schema):
                            if reference not in definitions:
                                raise MigrationError("Unresolved source schema reference; no external lookup was attempted.")
                            schema_pairs[reference] = definitions
                            pending.append(reference)
            else:
                raise MigrationError("Unreviewed MCP source kind.")
    for selected in selection["keys"]:
        bindings(selected)
        name(selected["name"])
        if selected.get("state") == "suspended" and (selection["models"] or selection["mcp"]):
            if not any(key.get("state", "active") == "active" for key in selection["keys"]):
                raise MigrationError("Selected traffic needs an explicitly active admission key.")
    for selected in selection.get("aliases", []):
        bindings(selected)
        for sid in selected["sourceIds"]:
            item = source[sid]
            check_routing_failures(item)
            policy_behaviors = [b["id"] for b in bundle["source-inventory.json"]["behaviors"]
                                if b["sourceId"] == sid and "statement" in b]
            if (item["policyShape"] and not item.get("facts", {}).get("routingOnly")
                    and not policy_translation(selection, sid, policy_behaviors)):
                raise MigrationError("Untranslated policy behavior cannot be represented by an alias selection.")
        name(selected["name"])
        if (selected["name"].lower() in aliases or not explicit_id(selected["routingName"])
                or selected["routingName"].casefold() in routing_names):
            raise MigrationError("Explicit aliases need unique resource/callable names.")
        aliases.add(selected["name"].lower())
        routing_names.add(selected["routingName"].casefold())
        if len({(b["provider"].lower(), b["model"].lower()) for b in selected["backends"]}) != len(selected["backends"]):
            raise MigrationError("A routing pool cannot duplicate the same model registration.")
        protocols, endpoint_sets = set(), set()
        for backend in selected["backends"]:
            model = next((model for model in selection["models"] if model["name"] == backend["model"]
                          and next(p.get("name", p["id"]) for p in selection["providers"] if p["id"] == model["provider"])
                          == backend["provider"]), None)
            if model is None:
                raise MigrationError("Every routing backend needs an explicitly selected model registration.")
            if selected.get("sourcePoolId") and not model.get("explicitAlias"):
                raise MigrationError("Source pool models require explicitAlias so the shared alias owns their callable route.")
            protocols.add(model["apiFormat"])
            endpoint_sets.add(frozenset(model["endpoints"]))
        if len(protocols) != 1 or len(endpoint_sets) != 1:
            raise MigrationError("Routed models must share the selected API format and operation surface.")
    for model in selection["models"]:
        if model.get("explicitAlias") and not any(
                backend["model"] == model["name"] and backend["provider"] == next(
                    p.get("name", p["id"]) for p in selection["providers"] if p["id"] == model["provider"])
                for alias in selection.get("aliases", []) for backend in alias["backends"]):
            raise MigrationError("An explicit callable alias is required for every selected model.")
    scoped_nodes(bundle, selection)
    handler_sources = {sid for entry in selection["models"] + selection["mcp"] for sid in entry["sourceIds"]}
    if any(source[sid]["domain"] == "apis" and sid not in handler_sources
           for entry in selection["keys"] for sid in entry["sourceIds"]):
        raise MigrationError("API admission needs its explicit model/MCP implementation, not a key-only API mapping.")
    if selection["models"] or selection["mcp"]:
        coverage = {(c["scope"], c["domain"]): c for c in bundle["source-inventory.json"]["coverage"]}
        required_policy_scopes = {(bundle["source-inventory.json"]["sourceId"], "policies")}
        for sid in handler_sources:
            item = source[sid]
            if item["domain"] == "apis":
                required_policy_scopes.add((sid, "api-policies"))
            if item["domain"] == "api-operations":
                required_policy_scopes.add((sid, "operation-policies"))
        if any(not coverage.get(key, {}).get("establishesCompleteness") for key in required_policy_scopes):
            raise MigrationError("Selected traffic has incomplete inherited/API/operation policy evidence; recollect before mapping.")
    if len({r["sourceId"] for r in selection["retained"]}) != len(selection["retained"]):
        raise MigrationError("Duplicate retained source records.")
    for retained in selection["retained"]:
        if retained["sourceId"] not in source:
            raise MigrationError("Unknown coverage cannot be accepted as a retained source record.")
    if verify_graph and bundle["mapping.json"].get("selection") is not None:
        verify_selected_graph(bundle, selection, providers)
    return selection


def verify_selected_graph(bundle, selection, providers):
    from planning import public_projection

    nodes = {t["id"]: t for t in bundle["todos.json"]["items"]}
    required = {}

    def check(identifier, group, name, provider, properties, args, source_ids, deps):
        todo = nodes.get(identifier)
        if (not todo or todo["target"]["name"] != name or todo["target"]["provider"] != provider
                or not todo["capabilityId"].startswith(group + ".")
                or not subset({"properties": public_projection(properties)}, todo["desiredState"])
                or not set(deps) <= set(todo["dependsOn"] + todo.get("resourceDependencies", []))):
            raise MigrationError("Resource graph does not implement its approved explicit selection.")
        if not todo["capabilityId"].endswith(".verify"):
            actual = {("deployment-config" if k == "deployment" else k): v
                      for k, v in todo["arguments"].items()}
            if actual != args:
                raise MigrationError("Resource arguments differ from the explicit selection.")
        for sid in source_ids:
            required.setdefault(sid, set()).add(identifier)

    gateway = "gateway:" + resource_id(bundle["context.json"]["destinationId"], "aigateways")["gateway"]
    check(gateway, "gateway", None, None, {"provisioningState": "Succeeded"},
          selection["gateway"], [source_service_id(bundle)], [])
    if "sku" in selection["gateway"] and nodes[gateway]["desiredState"].get("sku") != {
            "name": selection["gateway"]["sku"]}:
        raise MigrationError("Gateway assertions must preserve the selected destination SKU.")
    for selected in selection["providers"]:
        target_name = selected.get("name", selected["id"])
        if (nodes.get("provider:" + target_name, {}).get("precondition", {}).get("exists")
                and not selected.get("reuseExisting")):
            raise MigrationError("Existing provider reuse must be explicit, not inferred from redacted credentials.")
        if nodes.get("provider:" + target_name, {}).get("capabilityId") == "provider.update":
            raise MigrationError("Compiled model synchronization does not implicitly modify provider authentication/configuration.")
        check("provider:" + target_name, "provider", target_name, None,
              {("displayName" if key == "display-name" else key): value
               for key, value in selected["settings"].items()},
              selected["settings"], selected["sourceIds"], [gateway])
    for selected in selection["models"]:
        target_provider = next(p.get("name", p["id"]) for p in selection["providers"] if p["id"] == selected["provider"])
        model = next(m for m in providers[selected["provider"]]["models"] if m["id"] == selected["id"])
        deployment = {"modelName": model["id"]}
        if model["deploymentId"]:
            deployment["resourceId"] = model["deploymentId"]
        if model["version"]:
            deployment["modelVersion"] = model["version"]
        mid = "model:" + selected["name"] + ":" + target_provider
        check(mid, "model", selected["name"], target_provider,
              {"deployment": deployment, "apiFormat": selected["apiFormat"], "supportedEndpoints": selected["endpoints"]},
              {"deployment-config": deployment, "api-format": selected["apiFormat"], "supported-endpoints": selected["endpoints"]},
              selected["sourceIds"], ["provider:" + target_provider])
        if selected.get("explicitAlias"):
            continue
        model_id = (bundle["context.json"]["destinationId"] + "/workspaces/default/modelProviders/"
                    + target_provider + "/models/" + selected["name"])
        backends = [{"resourceId": model_id, "priority": 0, "weight": 100}]
        if (nodes.get("alias:" + selected["alias"], {}).get("capabilityId") == "alias.update"
                and not selected.get("updateAlias")):
            raise MigrationError("Replacing an existing alias requires an explicit selection decision.")
        check("alias:" + selected["alias"], "alias", selected["alias"], None,
              {"aliasName": selected["routingName"], "backendModels": backends},
              {"routing-name": selected["routingName"], "backend-models": backends},
              selected["sourceIds"], [mid])
    for selected in selection["mcp"]:
        if (nodes.get("mcp:" + selected["name"], {}).get("precondition", {}).get("exists")
                and not (selected.get("reuseExisting") or selected.get("replaceEndpoints"))):
            raise MigrationError("Existing MCP authentication reuse/replacement must be explicit.")
        properties, settings = mcp_settings(bundle, selected)
        if (nodes.get("mcp:" + selected["name"], {}).get("capabilityId") == "mcp.update"
                and not selected.get("replaceEndpoints") and "endpoints" in settings):
            raise MigrationError("Replacing an existing MCP endpoint collection requires an explicit selection decision.")
        check("mcp:" + selected["name"], "mcp", selected["name"], None,
              properties, settings,
              selected["sourceIds"], [gateway])
    for selected in selection["keys"]:
        properties, arguments = key_settings(bundle, selected)
        check("key:" + selected["name"], "key", selected["name"], None,
              properties, arguments, selected["sourceIds"], [gateway])
    for selected in selection.get("aliases", []):
        backends = alias_backends(bundle, selected)
        check("alias:" + selected["name"], "alias", selected["name"], None,
              {"aliasName": selected["routingName"], "backendModels": backends},
              {"routing-name": selected["routingName"], "backend-models": backends}, selected["sourceIds"],
              ["model:" + b["model"] + ":" + b["provider"] for b in selected["backends"]])
    scoped_required = {}
    extensions = scoped_nodes(bundle, selection)
    for extension in extensions:
        todo = nodes.get(extension["id"])
        choices = {
            "policy": ("policy.update", "policy.verify"), "model-policy": ("model.policy", "model-policy.verify"),
            "network": ("network.update", "network.verify"),
            "connection": ("connection.update", "connection.verify"),
            "telemetry-exporter": ("telemetry.create", "telemetry.update", "telemetry.verify"),
        }[extension["group"]]
        if (not todo or todo["target"]["name"] != extension["name"]
                or todo["target"]["provider"] != extension["provider"]
                or todo["capabilityId"] not in choices
                or todo["arguments"] != ({} if todo["capabilityId"].endswith(".verify") else extension["intent"])
                or todo["desiredState"] != extension["desired"]
                or not set(extension["dependencies"]) <= set(todo.get("resourceDependencies", []))):
            raise MigrationError("Scoped resource graph differs from its explicit selection.")
        for bid in extension["entry"]["behaviorIds"]:
            behavior = next(b for b in bundle["source-inventory.json"]["behaviors"] if b["id"] == bid)
            scoped_required[bid] = {extension["id"]} | (
                required.get(behavior["sourceId"], set()) if "property" not in behavior else set())
    expected_nodes = (set().union(*required.values()) if required else set()) | {e["id"] for e in extensions}
    if set(nodes) != expected_nodes:
        raise MigrationError("The selected graph contains missing or unselected resource nodes.")
    for mapping in bundle["mapping.json"]["items"]:
        expected = (set().union(*(scoped_required.get(bid, required.get(
            next(b["sourceId"] for b in bundle["source-inventory.json"]["behaviors"] if b["id"] == bid), set()))
                                 for bid in mapping["behaviorIds"]))
                    if mapping["classification"] == "ready" else set())
        if set(mapping.get("todoIds", [])) != expected:
            raise MigrationError("Mapping ownership differs from its selected resource graph.")


def alias_backends(bundle, selected):
    root = bundle["context.json"]["destinationId"] + "/workspaces/default/modelProviders/"
    return [{"resourceId": root + b["provider"] + "/models/" + b["model"],
             "priority": b["priority"], "weight": b["weight"]} for b in selected["backends"]]


def key_settings(bundle, selected):
    properties = {"displayName": selected["displayName"]}
    arguments = {"display-name": selected["displayName"]}
    lifecycle = {flag: selected[field] for field, flag in (
        ("state", "state"), ("expirationDate", "expiration-date")) if field in selected}
    if lifecycle:
        current = current_resource(bundle["destination-inventory.json"], "api-key", selected["name"])
        if current is None:
            raise MigrationError("Create/verify key metadata first, then re-plan its lifecycle.")
        if current.get("properties", {}).get("displayName") != selected["displayName"]:
            raise MigrationError("The service rejects key renames; select its existing display name.")
        if not selected.get("updateExisting") and any(
                current["properties"].get("state" if flag == "state" else "expirationDate") != value
                for flag, value in lifecycle.items()):
            raise MigrationError("Key lifecycle updates require an explicit updateExisting decision.")
        properties.update({("expirationDate" if k == "expiration-date" else k): v for k, v in lifecycle.items()})
        arguments = lifecycle
    return properties, arguments


def mcp_settings(bundle, selected):
    from planning import public_projection, runtime_references

    properties = {"endpoints": selected["endpoints"]}
    if "versions" in selected:
        properties["versions"] = selected["versions"]
    arguments = dict(properties)
    if any(todo["id"] == "mcp:" + selected["name"] and todo["arguments"] == properties
           and todo["status"] in ("resource-verified", "behavior-verified", "in-progress", "mutation-unknown")
           for todo in bundle["todos.json"]["items"]):
        return properties, arguments
    current = current_resource(bundle["destination-inventory.json"], "mcp", selected["name"])
    if (current is not None and public_projection(current["properties"].get("endpoints"))
            == public_projection(selected["endpoints"])
            and (selected.get("reuseExisting") or not runtime_references(selected["endpoints"]))):
        arguments.pop("endpoints")
    return properties, arguments


def compile_selection(bundle, selection):
    from planning import initial_mapping, public_projection, runtime_references

    validate_selection(bundle, selection, verify_graph=False)
    for preview in bundle["mapping.json"].get("nativeSyncPreviews", []):
        validate_preview(preview, bundle["model-catalog.json"], bundle["destination-inventory.json"],
                         bundle["capability-contract.json"]["cli"], check_snapshot=True)
    result = copy.deepcopy(bundle)
    result["mapping.json"] = initial_mapping(result["source-inventory.json"])
    result["mapping.json"]["selection"] = copy.deepcopy(selection)
    result["mapping.json"]["nativeSyncPreviews"] = copy.deepcopy(bundle["mapping.json"].get("nativeSyncPreviews", []))
    result["todos.json"] = {"schemaVersion": "4.0", "items": []}
    destination = result["destination-inventory.json"]
    root = result["context.json"]["destinationId"]
    scope = resource_id(root, "aigateways")
    mappings = {sid: m for m in result["mapping.json"]["items"] for sid in m["sourceIds"]}
    catalogs = {p["id"]: p for p in result["model-catalog.json"]["providers"]}
    selected_ids, nodes, retained = set(), [], {r["sourceId"]: r["reason"] for r in selection["retained"]}

    def node(group, name, provider, arguments, properties, dependencies, source_ids, evidence,
             allow_update=True, extension=None):
        if extension is not None:
            todo = {
                "id": extension["id"], "mappingIds": [], "capabilityId": extension["capabilityId"],
                "target": {**scope, "workspace": "default", "name": name, "provider": provider},
                "arguments": extension["arguments"], "desiredState": extension["desired"],
                "dependsOn": [], "resourceDependencies": dependencies,
                "precondition": {"exists": extension["current"] is not None,
                                 "stateDigest": digest(semantic(extension["current"]))
                                 if extension["current"] is not None else None},
                "approval": {"status": "pending", "planDigest": None, "approvedAt": None},
                "status": "pending", "attempts": [], "behaviorResults": {},
            }
            bids = set(extension["entry"]["behaviorIds"])
            inherited = set()
            mapping = {
                "id": "map:" + extension["id"], "sourceIds": source_ids,
                "behaviorIds": extension["entry"]["behaviorIds"], "classification": "ready",
                "capabilityId": None, "semanticDecision": evidence, "question": None, "residual": None,
                "todoIds": [todo["id"]], "behaviorResults": pending_results(bids), "disposition": "selected",
            }
            for existing in list(result["mapping.json"]["items"]):
                if bids.intersection(existing["behaviorIds"]):
                    inherited.update(existing.get("todoIds", []))
                    existing["behaviorIds"] = [bid for bid in existing["behaviorIds"] if bid not in bids]
                    if "behaviorResults" in existing:
                        existing["behaviorResults"] = pending_results(existing["behaviorIds"])
                    if not existing["behaviorIds"]:
                        result["mapping.json"]["items"].remove(existing)
                        for resource in nodes:
                            if existing["id"] in resource["mappingIds"]:
                                resource["mappingIds"].remove(existing["id"])
            mapping["todoIds"].extend(sorted(inherited))
            for resource in nodes:
                if resource["id"] in inherited:
                    resource["mappingIds"].append(mapping["id"])
            result["mapping.json"]["items"].append(mapping)
            todo["mappingIds"] = [mapping["id"]]
            if todo["id"] in {t["id"] for t in nodes}:
                raise MigrationError("Duplicate scoped target; combine policies for each target in one selection.")
            nodes.append(todo)
            return todo["id"]
        suffix = {
            "model-provider": f"/workspaces/default/modelProviders/{name}",
            "model": f"/workspaces/default/modelProviders/{provider}/models/{name}",
            "model-alias": f"/workspaces/default/aliases/{name}", "api-key": f"/apiKeys/{name}",
            "mcp": f"/workspaces/default/toolServers/{name}", "gateway": "",
        }[group]
        if destination["exists"] and (any(e["domain"] == group for e in destination["errors"])
                                     or group not in destination["collections"]):
            raise MigrationError("Destination coverage is incomplete for a required resource.")
        current = next((item for item in destination["collections"].get(group, [])
                        if str(item.get("id", "")).lower() == (root + suffix).lower()), None)
        prefix = {"model-provider": "provider", "model": "model", "model-alias": "alias",
                  "api-key": "key", "mcp": "mcp", "gateway": "gateway"}[group]
        desired = {"properties": public_projection(properties)}
        if group == "gateway":
            desired.update(type="Microsoft.ApiManagement/aigateways")
            if "location" in arguments:
                desired["location"] = arguments["location"]
            if "sku" in arguments:
                desired["sku"] = {"name": arguments["sku"]}
        action = "verify" if current is not None and subset(desired, current) else "update" if current else "create"
        if group == "gateway" and action == "update":
            raise MigrationError("Existing gateway metadata differs; choose an appropriate destination instead of an implicit gateway update.")
        if action == "update" and (not allow_update or group == "model-provider"):
            raise MigrationError("Existing provider/alias configuration differs; review replacement separately instead of implicit sync changes.")
        if group == "mcp" and current is not None and action == "verify" and allow_update and runtime_references(arguments):
            raise MigrationError("Secret-only endpoint changes need a separately verifiable credential workflow; no replacement was inferred.")
        if prefix == "key" and action == "update" and not set(arguments) <= {"state", "expiration-date"}:
            raise MigrationError("Existing key metadata differs; explicitly choose a new key or reuse its current metadata.")
        if action == "update" and "deployment-config" in arguments:
            arguments = {("deployment" if k == "deployment-config" else k): v for k, v in arguments.items()}
        identifier = prefix + ":" + (name or scope["gateway"])
        if provider:
            identifier += ":" + provider
        todo = {
            "id": identifier, "mappingIds": [], "capabilityId": prefix + "." + action,
            "target": {**scope, "workspace": "default", "name": name, "provider": provider},
            "arguments": {} if action == "verify" else arguments, "desiredState": desired,
            "dependsOn": [], "resourceDependencies": dependencies,
            "precondition": {"exists": current is not None,
                             "stateDigest": digest(semantic(current)) if current is not None else None},
            "approval": {"status": "pending", "planDigest": None, "approvedAt": None},
            "status": "pending", "attempts": [], "behaviorResults": {},
        }
        if identifier in {t["id"] for t in nodes}:
            raise MigrationError("Duplicate destination resource selection.")
        for sid in source_ids:
            if sid in retained:
                raise MigrationError("A source behavior cannot be both selected and retained.")
            mapping = mappings[sid]
            previous = mapping.get("semanticDecision") if mapping["classification"] == "ready" else None
            source_item = next(i for i in result["source-inventory.json"]["items"] if i["id"] == sid)
            dependency = (source_item["domain"] in ("backends", "namedValues", "api-schemas")
                          or source_item.get("facts", {}).get("role") == "rest")
            mapping.update(classification="ready", capabilityId=None, question=None, residual=None,
                           disposition="dependency" if dependency else "selected", semanticDecision=(
                               previous if previous and evidence in previous else
                               previous + "\n" + evidence if previous else evidence))
            mapping.setdefault("todoIds", []).append(identifier)
            mapping["behaviorResults"] = pending_results(mapping["behaviorIds"])
            todo["mappingIds"].append(mapping["id"])
            selected_ids.add(sid)
        if not todo["mappingIds"]:
            raise MigrationError("Every resource node requires source behavior provenance.")
        nodes.append(todo)
        return identifier

    service = source_service_id(result)
    service_mapping = mappings[service]
    service_behaviors = {b["id"]: b for b in result["source-inventory.json"]["behaviors"]
                         if b["sourceId"] == service}
    property_ids = [bid for bid in service_mapping["behaviorIds"] if "property" in service_behaviors[bid]]
    if property_ids:
        retained_service = copy.deepcopy(service_mapping)
        retained_service.update(
            id=service_mapping["id"] + ":service-properties", behaviorIds=property_ids,
            classification="cannot-import", disposition="retained-source", question=None,
            semanticDecision="Service properties are not implicitly converted by gateway creation.",
            residual={"reason": "Source service properties need separate identity/network/telemetry decisions.",
                      "manualAction": "Retain on APIM or explicitly map required service properties before cutover.",
                      "acceptance": "pending", "approvedPlanDigest": None, "decidedAt": None})
        result["mapping.json"]["items"].append(retained_service)
        service_mapping["behaviorIds"] = [bid for bid in service_mapping["behaviorIds"] if bid not in property_ids]
    gateway_args = selection["gateway"]
    if not destination["exists"] and not gateway_args.get("location"):
        raise MigrationError("A new destination requires an explicitly selected location.")
    gateway_properties = {"provisioningState": "Succeeded"}
    if gateway_args.get("subnet"):
        gateway_properties["backend"] = {"subnet": {"id": gateway_args["subnet"]}}
    gateway = node("gateway", None, None, gateway_args, gateway_properties,
                   [], [service], "Explicit destination resource and verified provisioning.")
    provider_nodes = {}
    for provider in selection["providers"]:
        settings = provider["settings"]
        target_name = provider.get("name", provider["id"])
        existing = any(i.get("name", "").lower() == target_name.lower()
                       for i in destination["collections"].get("model-provider", []))
        if existing and not provider.get("reuseExisting"):
            raise MigrationError("Existing provider credentials require an explicit reuse decision; no secret rotation is inferred.")
        provider_nodes[provider["id"]] = node(
            "model-provider", target_name, None, settings,
            {("displayName" if key == "display-name" else key): value for key, value in settings.items()}, [gateway],
            provider["sourceIds"], provider["evidence"])
    for selected in selection["models"]:
        target_provider = next(p.get("name", p["id"]) for p in selection["providers"] if p["id"] == selected["provider"])
        provider = catalogs[selected["provider"]]
        model = next(m for m in provider["models"] if m["id"] == selected["id"])
        deployment = {"modelName": model["id"]}
        if model["deploymentId"]:
            deployment["resourceId"] = model["deploymentId"]
        if model["version"]:
            deployment["modelVersion"] = model["version"]
        arguments = {"deployment-config": deployment, "api-format": selected["apiFormat"],
                     "supported-endpoints": selected["endpoints"]}
        properties = {"deployment": deployment, "apiFormat": selected["apiFormat"],
                      "supportedEndpoints": selected["endpoints"]}
        model_node = node("model", selected["name"], target_provider, arguments, properties,
                          [provider_nodes[selected["provider"]]], selected["sourceIds"], selected["evidence"])
        if provider["kind"] == "Foundry":
            action = selected_action(bundle, selected["provider"], target_provider, selected)["action"]
            generated = nodes[-1]["capabilityId"]
            if (action == "create") != (generated == "model.create"):
                raise MigrationError("Native model action and destination preconditions disagree; recollect.")
        if selected.get("explicitAlias"):
            continue
        model_id = (root + "/workspaces/default/modelProviders/" + target_provider
                    + "/models/" + selected["name"])
        backends = [{"resourceId": model_id, "priority": 0, "weight": 100}]
        node("model-alias", selected["alias"], None,
             {"routing-name": selected["routingName"], "backend-models": backends},
             {"aliasName": selected["routingName"], "backendModels": backends},
             [model_node], selected["sourceIds"], selected["evidence"], allow_update=selected.get("updateAlias", False))
    for selected in selection["mcp"]:
        existing = any(i.get("name", "").lower() == selected["name"].lower()
                       for i in destination["collections"].get("mcp", []))
        if existing and not (selected.get("reuseExisting") or selected.get("replaceEndpoints")):
            raise MigrationError("Existing MCP authentication needs an explicit reuse or replacement decision.")
        properties, settings = mcp_settings(result, selected)
        if existing and "endpoints" in settings and selected.get("replaceEndpoints") and not selected.get("credentialUseApproved"):
            raise MigrationError("Approve the CLI's destination credential reads before endpoint updates.")
        node("mcp", selected["name"], None, settings,
             properties, [gateway],
             selected["sourceIds"], selected["evidence"] + " Access: " + selected["accessDecision"],
             allow_update=selected.get("replaceEndpoints", False) or (
                 "versions" in selected and "endpoints" not in settings))
    for selected in selection["keys"]:
        properties, arguments = key_settings(result, selected)
        node("api-key", selected["name"], None, arguments,
             properties, [gateway],
             selected["sourceIds"], selected["accessDecision"])
    for selected in selection.get("aliases", []):
        backends = alias_backends(result, selected)
        node("model-alias", selected["name"], None,
             {"routing-name": selected["routingName"], "backend-models": backends},
             {"aliasName": selected["routingName"], "backendModels": backends},
             ["model:" + b["model"] + ":" + b["provider"] for b in selected["backends"]],
             selected["sourceIds"], selected["evidence"] + " Scope: " + selected["scopeDecision"],
             allow_update=selected.get("updateExisting", False))
    for extension in scoped_nodes(result, selection):
        entry = extension["entry"]
        node(extension["group"], extension["name"], extension["provider"], extension["arguments"], {},
             extension["dependencies"], entry["sourceIds"], entry["evidence"] + " Scope: " + entry["scopeDecision"],
             extension=extension)
    for sid, reason in retained.items():
        mapping = mappings[sid]
        mapping.update(classification="cannot-import", disposition="retained-source", question=None,
                       semanticDecision=reason, residual={
                           "reason": reason, "manualAction": "Retain the observed behavior on APIM.",
                           "acceptance": "pending", "approvedPlanDigest": None, "decidedAt": None})
    result["todos.json"]["items"] = nodes
    result["mapping.json"]["removalProposals"] = removal_proposals(result)
    return result
