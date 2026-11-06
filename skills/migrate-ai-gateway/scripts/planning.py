"""Deterministic mapping, graph, target, and command validation."""

from __future__ import annotations

import copy
from graphlib import CycleError, TopologicalSorter
import json
from datetime import datetime
from ipaddress import ip_network
from math import isfinite
import re
from urllib.parse import parse_qsl, urlsplit

from core import GATEWAY_TYPE, MigrationError, SECRET, clean, digest, resource_id, semantic, subset, validate_schema
from gateway import catalog, resource_kind
from model_inventory import validate_catalog


def gap_id(coverage):
    return "gap:" + digest([coverage["scope"].lower(), coverage["domain"]])[7:]


def conflict_id(conflict):
    return "conflict:" + digest([conflict["sourceId"].lower(), conflict["evidenceDigest"]])[7:]


def initial_mapping(source):
    items = []
    for item in source["items"]:
        items.append({
            "id": "map:" + digest(item["id"].lower())[7:],
            "sourceIds": [item["id"]],
            "behaviorIds": [behavior["id"] for behavior in source["behaviors"]
                            if behavior["sourceId"].lower() == item["id"].lower()],
            "classification": "needs-input", "capabilityId": None,
            "semanticDecision": None,
            "question": "Confirm destination representation, dependencies, and source behavior.",
            "residual": None,
        })
    for coverage in source["coverage"]:
        if not coverage["establishesCompleteness"]:
            items.append({
                "id": "map:" + gap_id(coverage), "sourceIds": [gap_id(coverage)],
                "behaviorIds": [], "classification": "needs-input", "capabilityId": None,
                "semanticDecision": None, "question": "Resolve incomplete source coverage.",
                "residual": None,
            })
    seen_conflicts = set()
    for conflict in source["conflicts"]:
        if conflict_id(conflict) in seen_conflicts:
            continue
        seen_conflicts.add(conflict_id(conflict))
        items.append({
            "id": "map:" + conflict_id(conflict), "sourceIds": [conflict_id(conflict)],
            "behaviorIds": [], "classification": "needs-input", "capabilityId": None,
            "semanticDecision": None, "question": "Resolve contradictory source authority/provenance.",
            "residual": None,
        })
    return {"schemaVersion": "4.0", "items": items, "selection": None, "nativeSyncPreviews": []}


def plan_digest(bundle):
    mappings = copy.deepcopy(bundle["mapping.json"])
    for item in mappings["items"]:
        item.pop("behaviorResults", None)
        if item["residual"]:
            for key in ("acceptance", "approvedPlanDigest", "decidedAt"):
                item["residual"].pop(key, None)
    for preview in mappings.get("nativeSyncPreviews", []):
        preview.pop("capturedAt", None)
    todos = copy.deepcopy(bundle["todos.json"])
    for item in todos["items"]:
        for key in ("status", "attempts", "approval", "behaviorResults"):
            item.pop(key)
    return digest({
        "source": semantic(bundle["source-inventory.json"]),
        "modelCatalog": semantic(bundle["model-catalog.json"]),
        "destinationId": bundle["context.json"]["destinationId"].lower(),
        "contract": bundle["capability-contract.json"]["contractDigest"],
        "mapping": mappings, "todos": todos,
    })


def contains_secret(value, key=""):
    if isinstance(value, dict) and set(value) == {"$runtimeSecret"}:
        return not isinstance(value["$runtimeSecret"], str) or not re.fullmatch(
            r"[A-Z][A-Z0-9_]*", value["$runtimeSecret"])
    if key.replace("-", "").replace("_", "").lower() == "apikey" and isinstance(value, dict):
        if set(value) <= {"headerName", "value"} and isinstance(value.get("headerName"), str):
            return (not re.fullmatch(r"[A-Za-z0-9-]+", value["headerName"])
                    or ("value" in value and contains_secret(value["value"], "value")))
    if key == "credentials" and isinstance(value, dict):
        if set(value) <= {"type", "headers", "managedIdentity", "oauth2"} and value.get("type") in (
                "none", "header", "managedIdentity", "oauth2"):
            if contains_secret(value.get("headers", {}), "headers"):
                return True
            identity = value.get("managedIdentity", {})
            if not isinstance(identity, dict) or set(identity) - {"clientId", "resource"}:
                return True
            oauth = value.get("oauth2", {})
            if not isinstance(oauth, dict) or set(oauth) - {
                    "authorizationUrl", "clientId", "clientSecret", "grantType", "scopes", "tokenUrl"}:
                return True
            return (contains_secret(identity) or contains_secret(oauth.get("clientSecret", ""), "clientSecret")
                    or any(contains_secret(v, "metadata") for k, v in oauth.items() if k != "clientSecret"))
    if SECRET.search(key.replace("-", "").replace("_", "")) or key.lower() in ("value", "headers"):
        if isinstance(value, dict):
            return any(contains_secret(child, key) for child in value.values())
        if isinstance(value, list):
            return any(contains_secret(child, key) for child in value)
        return value not in (None, "")
    if isinstance(value, dict):
        return any(contains_secret(child, name) for name, child in value.items())
    if isinstance(value, list):
        return any(contains_secret(child, key) for child in value)
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        url = urlsplit(value)
        return bool(url.username or url.password or
                    any(SECRET.search(k) for k, _ in parse_qsl(url.query)))
    return False


def public_projection(value):
    if isinstance(value, dict):
        result = {key: public_projection(child) for key, child in value.items()
                if not SECRET.search(key.replace("-", "").replace("_", ""))
                and key.lower() not in ("value", "headers", "data")
                and not (isinstance(child, dict) and "$runtimeSecret" in child)}
        if isinstance(value.get("apiKey"), dict) and isinstance(value["apiKey"].get("headerName"), str):
            result["apiKey"] = {"headerName": value["apiKey"]["headerName"]}
        if isinstance(value.get("credentials"), dict) and value["credentials"].get("type") in (
                "none", "header", "managedIdentity", "oauth2"):
            result["credentials"] = {"type": value["credentials"]["type"]}
        return result
    if isinstance(value, list):
        return [public_projection(child) for child in value]
    return value


def runtime_references(value):
    if isinstance(value, dict):
        if set(value) == {"$runtimeSecret"}:
            if not isinstance(value["$runtimeSecret"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", value["$runtimeSecret"]):
                raise MigrationError("Invalid caller-owned runtime variable reference.")
            return {value["$runtimeSecret"]}
        return set().union(*(runtime_references(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(runtime_references(child) for child in value)) if value else set()
    return set()


def policy_state(arguments, current=(), workspace=False):
    if not isinstance(current, (list, tuple)) or not all(
            isinstance(policy, dict) and isinstance(policy.get("type"), str) for policy in current):
        raise MigrationError("Existing policy state is malformed.")
    updates = {}

    def counter(option, default):
        value = arguments.get(option, default)
        values = [value] if isinstance(value, str) else value
        allowed = {"Identity": "identity", "IPAddress": "ipAddress",
                   "identity": "identity", "ipAddress": "ipAddress"}
        if (not isinstance(values, list) or not values or
                any(not isinstance(v, str) or v not in allowed for v in values)
                or len(set(values)) != len(values)):
            raise MigrationError("Counters require finite identity/IPAddress dimensions, not expressions or All.")
        normalized = [allowed[v] for v in values]
        if len(set(normalized)) != len(normalized):
            raise MigrationError("Counter dimensions must be unique after normalization.")
        return normalized

    def positive(value):
        return type(value) is int and value > 0

    if {"token-limit", "token-period", "token-counter-key"} & arguments.keys():
        if not positive(arguments.get("token-limit")):
            raise MigrationError("An explicit positive token count is required.")
        period = arguments.get("token-period", "minute")
        if period not in ("minute", "hour", "day"):
            raise MigrationError("Unsupported token period.")
        updates["tokenLimit"] = {"type": "tokenLimit", "count": arguments["token-limit"],
                                "period": period, "counterKey": counter("token-counter-key", ["Identity"])}
    severities = ("Low", "Medium", "High", "None")
    category_options = (("hateSeverity", "hate-severity"), ("selfHarmSeverity", "self-harm-severity"),
                        ("sexualSeverity", "sexual-severity"), ("violenceSeverity", "violence-severity"))
    if "content-safety" in arguments or any(option in arguments for _, option in category_options):
        severity = arguments.get("content-safety")
        if severity not in severities or any(arguments.get(option, severity) not in severities
                                            for _, option in category_options):
            raise MigrationError("Category overrides require an explicit supported content-safety severity.")
        updates["contentSafety"] = {"type": "contentSafety", **{
            field: arguments.get(option, severity) for field, option in category_options}}
    if any(key.startswith("cost-") for key in arguments):
        amount, period = arguments.get("cost-limit"), arguments.get("cost-period")
        finite = ((type(amount) is int and abs(amount) <= 9007199254740991)
                  or (type(amount) is float and isfinite(amount)))
        if (not finite or amount < 0
                or period not in ("hour", "day", "week", "month", "year")):
            raise MigrationError("Cost governance requires a finite non-negative amount and supported period.")
        updates["costLimit"] = {"type": "costLimit", "amount": amount, "period": period,
                               "counterKey": counter("cost-counter-key", ["Identity"])}
        if "cost-id" in arguments:
            identifier = arguments["cost-id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
                raise MigrationError("Cost policy ID must be explicit.")
            updates["costLimit"]["id"] = identifier
    if {"calls-per-period", "period-seconds", "rate-counter-key"} & arguments.keys():
        if not workspace or not positive(arguments.get("calls-per-period")) or not positive(arguments.get("period-seconds")):
            raise MigrationError("Request-rate policies require workspace scope, positive calls and period seconds.")
        updates["requestRateLimit"] = {"type": "requestRateLimit",
                                      "callsPerPeriod": arguments["calls-per-period"],
                                      "periodSeconds": arguments["period-seconds"],
                                      "counterKey": counter("rate-counter-key", ["Identity"])}
    if {"ip-filter-mode", "ip-addresses"} & arguments.keys():
        addresses = arguments.get("ip-addresses")
        action = arguments.get("ip-filter-mode")
        if not workspace or action not in ("allow", "deny") or not isinstance(addresses, list) or not addresses:
            raise MigrationError("An IP policy requires workspace scope, allow/deny and explicit IP ranges.")
        try:
            for address in addresses:
                if not isinstance(address, str):
                    raise ValueError
                ip_network(address, strict=True)
        except ValueError as exc:
            raise MigrationError("Invalid IP address/CIDR range.") from exc
        updates["ipFilter"] = {"type": "ipFilter", "action": action, "cidrRanges": addresses}
    if not updates:
        raise MigrationError("Select an explicit supported policy.")
    merged, remaining = [], dict(updates)
    for existing in current:
        policy = copy.deepcopy(existing)
        kind = policy.get("type")
        if kind in updates:
            if kind not in remaining:
                continue
            policy = {**policy, **remaining.pop(kind)}
        if kind in ("tokenLimit", "costLimit", "requestRateLimit") and "counterKey" in policy:
            values = policy["counterKey"]
            values = [values] if isinstance(values, str) else values
            policy["counterKey"] = [{"Identity": "identity", "IPAddress": "ipAddress"}.get(v, v) if isinstance(v, str) else v
                                    for v in values] if isinstance(values, list) else values
        if workspace and kind in updates and kind in ("tokenLimit", "costLimit", "requestRateLimit"):
            policy["scope"] = "workspace"
        merged.append(policy)
    for kind, policy in remaining.items():
        if kind == "costLimit":
            policy.setdefault("id", "default")
        if workspace and kind in ("tokenLimit", "costLimit", "requestRateLimit"):
            policy["scope"] = "workspace"
        merged.append(policy)
    return merged


def reviewed_arguments(cid, arguments):
    if cid in ("model.policy", "policy.update"):
        policy_state(arguments, workspace=cid == "policy.update")
    if cid in ("gateway.create", "network.update") and "subnet" in arguments:
        if not isinstance(arguments["subnet"], str) or not re.fullmatch(
                r"/subscriptions/[A-Za-z0-9_.-]+/resourceGroups/[A-Za-z0-9_.-]+/providers/"
                r"Microsoft\.Network/virtualNetworks/[A-Za-z0-9_.-]+/subnets/[A-Za-z0-9_.-]+",
                arguments["subnet"], re.I):
            raise MigrationError("Subnet must be a complete existing subnet ARM ID.")
    if cid == "network.update":
        if "subnet" in arguments and arguments.get("disable-vnet-integration"):
            raise MigrationError("Subnet and disable-vnet-integration are mutually exclusive.")
        if "disable-vnet-integration" in arguments and arguments["disable-vnet-integration"] is not True:
            raise MigrationError("Select integration removal explicitly with true.")
    if cid == "key.update":
        if not arguments or set(arguments) - {"state", "expiration-date"}:
            raise MigrationError("Only explicit key state/expiry updates are supported.")
        if arguments.get("state", "active") not in ("active", "suspended"):
            raise MigrationError("Unsupported key state.")
        if "expiration-date" in arguments:
            try:
                parsed = datetime.fromisoformat(arguments["expiration-date"].replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            except (ValueError, TypeError, AttributeError) as exc:
                raise MigrationError("Key expiration requires a timezone-qualified ISO timestamp.") from exc
    if cid in ("telemetry.create", "telemetry.update"):
        if (arguments.get("kind") != "ApplicationInsights"
                or type(arguments.get("payload-capture")) is not bool
                or set(arguments) - {"kind", "application-insights", "payload-capture"}):
            raise MigrationError("Only reviewed ApplicationInsights connection-string writes are enabled; OpenTelemetry fields are unreviewed.")
        config = arguments.get("application-insights")
        if (not isinstance(config, dict) or set(config) != {"connectionString"}
                or not isinstance(config["connectionString"], dict)
                or set(config["connectionString"]) != {"$runtimeSecret"}
                or not runtime_references(config)):
            raise MigrationError("Application Insights requires a runtime-only connection string.")


def meaningful_assertion(todo, cap):
    args, desired = todo["arguments"], todo["desiredState"]
    cid = cap["id"]
    if cap["kind"] == "verify":
        if cid == "network.verify":
            return bool(desired) and not args
        return bool(desired.get("properties")) and not args
    if cid == "gateway.create":
        expected = {"type": GATEWAY_TYPE, "location": args["location"],
                    "properties": {"provisioningState": "Succeeded"}}
        if "subnet" in args:
            expected["properties"]["backend"] = {"subnet": {"id": args["subnet"]}}
        if "sku" in args:
            expected["sku"] = {"name": args["sku"]}
        return subset(expected, desired)
    if cid == "identity.assign":
        dtype = desired.get("type", "")
        return ((not args.get("system-assigned") or "SystemAssigned" in dtype)
                and (not args.get("user-assigned") or "UserAssigned" in dtype)
                and (not args.get("user-assigned") or (
                    isinstance(args["user-assigned"], list) and
                    subset({key: {} for key in args["user-assigned"]},
                           desired.get("userAssignedIdentities", {}))))
                and bool(args.get("system-assigned") or args.get("user-assigned")))
    if cid == "network.update":
        expected = {}
        if "public-network-access" in args:
            expected["publicNetworkAccess"] = args["public-network-access"]
        if "subnet" in args:
            expected.update(virtualNetworkType="External",
                            virtualNetworkConfiguration={"subnetResourceId": args["subnet"]})
        if args.get("disable-vnet-integration"):
            expected.update(virtualNetworkType="None", virtualNetworkConfiguration=None)
        return bool(expected) and subset(expected, desired)
    if cid in ("model.policy", "policy.update"):
        policies = desired.get("properties", {}).get("policies")
        if not isinstance(policies, list):
            return False
        expected = policy_state(args, workspace=cid == "policy.update")
        if "cost-id" not in args:
            for policy in expected:
                if policy["type"] == "costLimit":
                    policy.pop("id", None)
        return bool(expected) and all(any(subset(p, actual) for actual in policies) for p in expected)
    if cid == "connection.update":
        properties = desired.get("properties", {})
        return bool(properties.get("privateEndpoint", {}).get("id")) and subset({"properties": {"privateLinkServiceConnectionState": {
            "status": "Approved", "description": args["description"]},
            "provisioningState": "Succeeded"}}, desired)
    if cid == "mcp.source.add":
        expected = public_projection({key.replace("open-api", "openApi"): value
                                      for key, value in args.items()})
        endpoints = desired.get("properties", {}).get("endpoints")
        return isinstance(endpoints, list) and any(subset(expected, value) for value in endpoints)
    if cid in ("alias.create", "alias.update"):
        expected = {"backendModels": args["backend-models"]}
        if "routing-name" in args:
            expected["aliasName"] = args["routing-name"]
        return subset({"properties": expected}, desired)
    wire = {"display-name": "displayName", "description": "description", "kind": "kind",
            "foundry": "foundry", "custom": "custom", "deployment": "deployment",
            "deployment-config": "deployment", "api-format": "apiFormat",
            "supported-endpoints": "supportedEndpoints", "endpoints": "endpoints",
            "failure-mode": "failureMode", "versions": "versions", "state": "state",
            "expiration-date": "expirationDate", "application-insights": "applicationInsights",
            "payload-capture": "payloadCapture"}
    expected = {wire[key]: public_projection(value) for key, value in args.items() if key in wire}
    return bool(expected) and subset({"properties": expected}, desired)


def validate_plan(bundle):
    errors, warnings = [], []
    def issue(code, path, message):
        errors.append({"code": code, "path": path, "message": message})
    for name in ("context", "mapping", "todos", "source-inventory", "model-catalog", "destination-inventory",
                 "capability-contract"):
        try:
            validate_schema(bundle[name + ".json"], name)
        except MigrationError:
            issue("schema", "/" + name, "Document does not satisfy the current schema.")
    if errors:
        return validation_result(bundle, errors, warnings, None)
    try:
        validate_catalog(bundle["model-catalog.json"])
    except MigrationError:
        issue("model-catalog", "/model-catalog", "Model catalog identities/provenance are invalid.")
    source, destination = bundle["source-inventory.json"], bundle["destination-inventory.json"]
    context = bundle["context.json"]
    mapping = bundle["mapping.json"]["items"]
    if bundle["mapping.json"].get("nativeSyncPreviews") and bundle["mapping.json"].get("selection") is None:
        issue("native-sync-selection", "/mapping", "Native sync evidence requires an explicit selected resource graph.")
    todos = bundle["todos.json"]["items"]
    contract = bundle["capability-contract.json"]
    if source["sourceId"].lower() != context["sourceId"].lower():
        issue("source-identity", "/context", "Source identity differs from inventory.")
    if destination.get("destinationId", "").lower() != context["destinationId"].lower():
        issue("destination-identity", "/context", "Destination identity differs from inventory.")
    if context["sourceId"].lower() == context["destinationId"].lower():
        issue("source-mutation", "/context", "Source and destination must be distinct services.")
    try:
        target = resource_id(context["destinationId"], "aigateways")
        resource_id(context["sourceId"])
    except MigrationError:
        issue("resource-id", "/context", "Expected an APIM service source and an aigateways destination.")
        target = {}
    if source["service"].get("properties", {}).get("provisioningState") != "Succeeded":
        issue("source-health", "/source", "Source provisioning state must be Succeeded.")
    transition = source["service"].get("properties", {}).get("targetProvisioningState")
    if transition not in (None, "Succeeded"):
        issue("source-health", "/source", "Source has a nonterminal target provisioning state.")
    if str(source["service"].get("id", "")).lower() != context["sourceId"].lower():
        issue("source-identity", "/source", "Service snapshot identity differs from the source.")
    if source["sku"] != source["service"].get("sku", {}).get("name"):
        issue("source-profile", "/source", "Profile and observed source service profile disagree.")
    supplied = {key: value for key, value in contract.items() if key != "contractDigest"}
    if digest(supplied) != contract["contractDigest"] or contract["catalogDigest"] != digest(catalog()):
        issue("capability-digest", "/contract", "Capability output is stale or modified.")
    capabilities = {cap["id"]: cap for cap in contract["capabilities"]}
    trusted = {cap["id"]: cap for cap in catalog()["capabilities"]}
    for key, cap in capabilities.items():
        if key not in trusted or any(cap.get(k) != v for k, v in trusted[key].items()):
            issue("capability-catalog", "/contract", "Capability differs from the reviewed catalog.")
    items = {item["id"]: item for item in source["items"]}
    behaviors = {item["id"]: item for item in source["behaviors"]}
    gaps = ({gap_id(coverage) for coverage in source["coverage"]
             if not coverage["establishesCompleteness"]}
            | {conflict_id(conflict) for conflict in source["conflicts"]})
    expected_sources = set(items) | gaps
    observed_sources, observed_behaviors = set(), set()
    mapping_by_id = {item["id"]: item for item in mapping}
    todo_by_id = {item["id"]: item for item in todos}
    if len(mapping_by_id) != len(mapping) or len(todo_by_id) != len(todos):
        issue("duplicate-id", "/", "Mapping and TODO IDs must be unique.")
    if len(items) != len(source["items"]) or len(behaviors) != len(source["behaviors"]):
        issue("duplicate-source", "/source", "Source item and behavior IDs must be unique.")
    for item in mapping:
        path = "/mapping/" + item["id"]
        observed_sources.update(item["sourceIds"])
        for behavior_id in item["behaviorIds"]:
            if behavior_id in observed_behaviors:
                issue("duplicate-behavior", path, "A behavior is mapped more than once.")
            observed_behaviors.add(behavior_id)
            if behavior_id in behaviors and behaviors[behavior_id]["sourceId"] not in item["sourceIds"]:
                issue("behavior-owner", path, "Behavior does not belong to this mapping.")
        classification = item["classification"]
        implementation_ids = item.get("todoIds", [])
        implementations = [todo_by_id[tid] for tid in implementation_ids if tid in todo_by_id]
        graph_mapping = bool(implementation_ids)
        if graph_mapping and (len(implementations) != len(implementation_ids) or any(
                item["id"] not in todo["mappingIds"] for todo in implementations)):
            issue("implementation", path, "Mappings must reference known, reciprocal resource nodes.")
        if graph_mapping and set(item.get("behaviorResults", {})) != set(item["behaviorIds"]):
            issue("verification-coverage", path, "Graph mappings must verify each owned source behavior.")
        if classification == "needs-input" and not item["question"]:
            issue("missing-question", path, "Blocked mappings require an actionable question.")
        if set(item["sourceIds"]) & gaps and classification != "needs-input":
            issue("coverage-gap", path, "Unknown coverage cannot be accepted as a residual.")
        if classification == "cannot-import" and not item["residual"]:
            issue("missing-residual", path, "Unsupported behavior needs an explicit residual.")
        if classification == "ready":
            cap = capabilities.get(item["capabilityId"])
            implementing_caps = ([capabilities.get(t["capabilityId"]) for t in implementations]
                                 if graph_mapping else [cap])
            if (not implementing_caps or any(not c or c["support"] != "conditional" for c in implementing_caps)
                    or not item["semanticDecision"]):
                issue("unsupported-mapping", path, "Ready requires capability and an explicit semantic decision.")
            for sid in item["sourceIds"]:
                if sid not in items:
                    continue
                record = items[sid]
                if record["authority"] != "authoritative":
                    issue("source-authority", path, "Advisory export evidence cannot authorize execution.")
                if implementing_caps:
                    domain = "policies" if record["domain"].endswith("policies") else record["domain"]
                    if not any(c and domain in c["behaviorTypes"] for c in implementing_caps):
                        issue("behavior-capability", path, "Capability does not represent this source domain.")
                    if domain in ("api-operations", "api-schemas", "namedValues") and not bundle["mapping.json"].get("selection"):
                        issue("selection-required", path, "Operation/schema/credential ownership requires explicit selections.")
                    if (domain in ("apis", "service") and any(
                            c and c["id"] in ("model.policy", "model-policy.verify", "policy.update", "policy.verify")
                            for c in implementing_caps) and not bundle["mapping.json"].get("selection")):
                        issue("selection-required", path, "New governance requires an explicit scoped selection.")
                if (record["policyShape"] and '"redacted": true' in json.dumps(record["policyShape"])
                        and not (graph_mapping and bundle["mapping.json"].get("selection")
                                 and record.get("facts", {}).get("routingOnly"))):
                    from selection import policy_translation
                    if not (graph_mapping and bundle["mapping.json"].get("selection")
                            and policy_translation(bundle["mapping.json"]["selection"], sid, item["behaviorIds"])):
                        issue("opaque-policy", path, "Redacted policy inputs require an explicitly approved typed translation.")
                coverage = [c for c in source["coverage"]
                            if c["scope"] == record["scope"] and c["domain"] == record["domain"]]
                if not coverage or not all(c["establishesCompleteness"] and
                                          c["authority"] in ("authoritative", "corroborated")
                                          for c in coverage):
                    issue("source-authority", path, "Ready mapping has incomplete or advisory evidence.")
                if any(conflict["sourceId"].lower() == sid.lower() for conflict in source["conflicts"]):
                    issue("source-conflict", path, "Conflicting source evidence blocks execution.")
            if not any(item["id"] in todo["mappingIds"] for todo in todos):
                issue("missing-todo", path, "Ready mappings require an executable or verified TODO.")
    if observed_sources != expected_sources or observed_behaviors != set(behaviors):
        issue("source-coverage", "/mapping", "Every source item, gap, and behavior must be represented exactly.")
    for todo in todos:
        path = "/todos/" + todo["id"]
        cap = capabilities.get(todo["capabilityId"])
        if not cap or cap["support"] != "conditional":
            issue("unsupported-command", path, "Unavailable destination capability.")
            continue
        if any(str(todo["target"].get(k, "")).lower() != str(v).lower()
               for k, v in target.items()):
            issue("wrong-target", path, "Every mutation must target the exact destination.")
        if any(v is not None and (not isinstance(v, str) or
               not re.fullmatch(r"[A-Za-z0-9_.-]+", v)) for v in todo["target"].values()):
            issue("invalid-selector", path, "Selectors must be unambiguous resource names.")
        if resource_kind(cap["command"]) in ("model-provider", "model", "model-alias", "api-key", "mcp",
                                             "telemetry-exporter", "private-endpoint-connection") and not todo["target"]["name"]:
            issue("missing-child", path, "Child resource name required.")
        if cap["command"][0] == "model" and not todo["target"]["provider"]:
            issue("missing-provider", path, "Model provider name required.")
        if (set(todo["arguments"]) - set(cap["options"])
                or set(cap["required"]) - set(todo["arguments"])):
            issue("invalid-options", path, "Unsupported or missing command options.")
        if cap["id"] == "provider.create":
            kind = todo["arguments"].get("kind")
            if kind not in ("Foundry", "Custom") or kind.lower() not in todo["arguments"]:
                issue("provider-shape", path, "Provider kind needs corresponding low-level settings.")
        if cap["id"] in ("model.create", "model.update"):
            deployment = todo["arguments"].get("deployment-config" if cap["id"] == "model.create" else "deployment")
            if deployment is not None:
                from model_inventory import explicit_id
                if not isinstance(deployment, dict) or not explicit_id(deployment.get("modelName")):
                    issue("model-shape", path, "An explicit runtime model identifier is required.")
            if any(not isinstance(p, str) or "*" in p for p in todo["arguments"].get("supported-endpoints", [])):
                issue("model-shape", path, "Wildcard destination operations are not supported.")
            model_format = todo["arguments"].get("api-format")
            model_paths = todo["arguments"].get("supported-endpoints")
            if (not isinstance(model_format, str) or model_format not in catalog()["modelOperations"] or not isinstance(model_paths, list)
                    or not model_paths or any(p not in catalog()["modelOperations"].get(model_format, [])
                                              for p in model_paths)):
                issue("model-operations", path, "Model mutations require explicit reviewed protocol operation paths.")
        if cap["id"] in ("alias.create", "alias.update"):
            args = todo["arguments"]
            backends = args.get("backend-models")
            root = context["destinationId"] + "/workspaces/default/modelProviders/"
            if (not isinstance(backends, list) or not 1 <= len(backends) <= 30
                    or any(not isinstance(b, dict) or set(b) != {"resourceId", "priority", "weight"}
                           or not isinstance(b["resourceId"], str)
                           or not re.fullmatch(re.escape(root) + r"[A-Za-z0-9_.-]+/models/[A-Za-z0-9_.-]+",
                                               b["resourceId"], re.I)
                           or type(b["priority"]) is not int or not 0 <= b["priority"] <= 100
                           or type(b["weight"]) is not int or not 1 <= b["weight"] <= 100 for b in backends)):
                issue("alias-shape", path, "Aliases require explicit gateway-bound models and valid routing weights.")
            if "routing-name" in args:
                from model_inventory import explicit_id
                if not explicit_id(args["routing-name"]):
                    issue("alias-shape", path, "Callable names must be explicit, not wildcard selectors.")
        if cap["id"] == "model.policy":
            args = todo["arguments"]
            if not ("token-limit" in args or "content-safety" in args or "cost-limit" in args):
                issue("policy-shape", path, "Select token-limit, content-safety or cost-limit explicitly.")
            if {"token-period", "token-counter-key"} & args.keys() and "token-limit" not in args:
                issue("policy-shape", path, "Token period and counter key require token-limit.")
            if any(key.endswith("-severity") for key in args) and "content-safety" not in args:
                issue("policy-shape", path, "Severity overrides require content-safety.")
        if cap["id"] == "mcp.source.add":
            kind = todo["arguments"].get("kind")
            if kind not in ("mcp", "openApi") or (
                    kind == "mcp" and "mcp" not in todo["arguments"]) or (
                    kind == "openApi" and "open-api" not in todo["arguments"]):
                issue("source-shape", path, "A source requires its typed endpoint settings.")
        if contains_secret(todo["arguments"]) or contains_secret(todo["desiredState"]):
            issue("literal-secret", path, "Secret-bearing input requires runtime placeholders.")
        enums = {
            "api-format": tuple(catalog()["modelOperations"]),
            "token-period": ("minute", "hour", "day"),
            "content-safety": ("Low", "Medium", "High", "None"),
            "hate-severity": ("Low", "Medium", "High", "None"),
            "self-harm-severity": ("Low", "Medium", "High", "None"),
            "sexual-severity": ("Low", "Medium", "High", "None"),
            "violence-severity": ("Low", "Medium", "High", "None"),
            "failure-mode": ("failClosed", "failOpen"),
            "public-network-access": ("Enabled", "Disabled"),
            "sku": ("Standard", "Premium", "Consumption"),
        }
        for key, value in todo["arguments"].items():
            json_types = {
                "foundry": dict, "custom": dict, "deployment": dict, "deployment-config": dict,
                "endpoints": list, "supported-endpoints": list, "user-assigned": list,
                "mcp": dict, "open-api": dict, "credentials": dict,
                "backend-models": list,
                "versions": list, "ip-addresses": list, "cost-counter-key": list,
                "rate-counter-key": list, "application-insights": dict,
            }
            if key in json_types and not isinstance(value, json_types[key]):
                issue("option-shape", path, "Structured arguments must be JSON values, not file paths.")
            if isinstance(value, str) and value.startswith(("-", "@")):
                issue("option-value", path, "Scalar arguments must not inject options or file references.")
            if key in enums and value not in enums[key]:
                issue("option-value", path, "Unsupported argument enum value.")
            if key == "token-limit" and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                issue("option-value", path, "Token limits must be positive integers.")
        try:
            reviewed_arguments(cap["id"], todo["arguments"])
            meaningful = meaningful_assertion(todo, cap)
        except (KeyError, TypeError, MigrationError):
            meaningful = False
        if not meaningful:
            issue("desired-state", path, "Read-back must assert the actual requested configuration.")
        if any(v is not None and v.startswith(("-", "@")) for v in todo["target"].values()):
            issue("invalid-selector", path, "Selectors must not be interpreted as CLI options.")
        if not todo["precondition"]["exists"] and cap["kind"] != "create":
            issue("missing-update-target", path, "Updates require an existing target.")
        if cap["kind"] != "verify" and not todo["arguments"]:
            issue("empty-mutation", path, "A mutation must specify its intended configuration.")
        if todo["precondition"]["exists"] != bool(todo["precondition"]["stateDigest"]):
            issue("precondition", path, "Existing targets require a state fingerprint.")
        if cap["kind"] == "create" and todo["precondition"]["exists"]:
            issue("create-overwrite", path, "Create cannot overwrite an existing resource.")
        owners = [mapping_by_id.get(mid) for mid in todo["mappingIds"]]
        if any(owner is None or owner["classification"] != "ready"
               or (todo["id"] not in owner["todoIds"] if owner.get("todoIds") else
                   owner["capabilityId"] != todo["capabilityId"]) for owner in owners):
            issue("invalid-owner", path, "TODO must reference ready matching mappings.")
        behavior_ids = {bid for owner in owners if owner and not owner.get("todoIds")
                        for bid in owner["behaviorIds"]}
        if set(todo["behaviorResults"]) != behavior_ids:
            issue("verification-coverage", path, "TODO must verify every mapped behavior.")
        dependencies = todo["dependsOn"] + todo.get("resourceDependencies", [])
        if any(dep not in todo_by_id or dep == todo["id"] for dep in dependencies):
            issue("dependency", path, "Unknown or self dependency.")
        if todo["status"] == "behavior-verified" and not all(
                result["status"] == "passed" and result["evidenceDigest"]
                for result in todo["behaviorResults"].values()):
            issue("verification", path, "Verified TODO lacks behavior evidence.")
    try:
        TopologicalSorter({tid: item["dependsOn"] + item.get("resourceDependencies", [])
                           for tid, item in todo_by_id.items()}).prepare()
    except CycleError:
        issue("cycle", "/todos", "Dependency graph contains a cycle.")
    def conflicting(left, right):
        if isinstance(left, dict) and isinstance(right, dict):
            return any(conflicting(left[key], right[key]) for key in left.keys() & right.keys())
        return left != right
    for index, left in enumerate(todos):
        for right in todos[index + 1:]:
            left_cap = capabilities.get(left["capabilityId"], {})
            right_cap = capabilities.get(right["capabilityId"], {})
            if (left["target"] == right["target"] and left_cap.get("command", [None])[0] ==
                    right_cap.get("command", [None])[0] and conflicting(left["desiredState"], right["desiredState"])):
                issue("contradictory-state", "/todos",
                      "TODOs assert incompatible final state for the same target; split/re-plan the work.")
    if destination.get("errors"):
        warnings.append({"code": "destination-gaps", "path": "/destination",
                         "message": "Destination collection failures block affected mutations."})
    if bundle["mapping.json"].get("selection") is not None:
        from selection import validate_selection
        try:
            validate_selection(bundle, bundle["mapping.json"]["selection"])
        except MigrationError as exc:
            issue("selection", "/mapping/selection", str(exc))
    return validation_result(bundle, errors, warnings, plan_digest(bundle))


def validation_result(bundle, errors, warnings, pdigest):
    result = {
        "schemaVersion": "2.0", "producer": "skill-local",
        "status": "invalid" if errors else "valid", "planDigest": pdigest,
        "sourceInventoryDigest": digest(semantic(bundle["source-inventory.json"])),
        "capabilityContractDigest": bundle["capability-contract.json"].get("contractDigest"),
        "errors": errors, "warnings": warnings,
    }
    result["resultDigest"] = digest(result)
    return result


def render_plan(bundle, result):
    selection = bundle["mapping.json"].get("selection")
    selected_providers = {p["id"] for p in selection["providers"]} if selection is not None else None
    lines = ["# APIM migration plan", "", f"Validation: {result['status']}",
             f"Plan digest: `{result['planDigest']}`", "",
             "All currently executable mutations require per-item consequential approval.",
             "Unknown source coverage is not an acceptable migration residual.", "",
             f"Source: `{bundle['context.json']['sourceId']}`",
             f"Destination: `{bundle['context.json']['destinationId']}`", "",
             "## Upstream read scope", "",
             "Execution refreshes these approved catalogs; no credential values are displayed.",
             "APIM credentialSource reads additionally require --approved-credential-read after scoped approval.",
             "```json", json.dumps([{
                 "provider": p["id"], "kind": p["kind"], "endpoint": p["endpoint"],
                 "accountId": p["accountId"], "credentialRef": p["credentialRef"],
                 "credentialHeader": p.get("credentialHeader", "Authorization"),
                 "credentialSource": p.get("credentialSource"),
                 "provenance": p["provenance"], "complete": p["complete"], "error": p["error"]}
                 for p in bundle["model-catalog.json"]["providers"]
                 if selected_providers is None or p["id"] in selected_providers], indent=2),
             "```", "",
             "## Classification", ""]
    for item in bundle["mapping.json"]["items"]:
        lines.append(f"- `{item['id']}`: {item['classification']}.")
        if item["question"]:
            lines.append(f"  Input required: {clean(item['question'])}")
        if item["semanticDecision"]:
            lines.append(f"  Decision: {clean(item['semanticDecision'])}")
        if item["residual"]:
            lines.append(f"  Residual: {clean(item['residual']['reason'])}")
            lines.append(f"  Manual action: {clean(item['residual']['manualAction'])}")
        if item.get("todoIds"):
            lines.append("  Required resource nodes: " + ", ".join(item["todoIds"]))
    if bundle["mapping.json"].get("selection"):
        lines.extend(["", "## Explicit models and operations", "", "```json",
                      json.dumps(bundle["mapping.json"]["selection"]["models"], indent=2), "```",
                      "", "## Explicit model routing", "", "```json",
                      json.dumps(bundle["mapping.json"]["selection"].get("aliases", []), indent=2), "```",
                      "Source-pool bindings preserve observed membership, priorities and weights.",
                      "Configuration read-back is not proof of failure triggers, recovery, or runtime failover.",
                      "", "## Separate removal proposals (not executable)", "", "```json",
                      json.dumps(bundle["mapping.json"].get("removalProposals", []), indent=2), "```",
                      "Proposals require complete account/model/alias evidence. An empty list is not proof",
                      "of absence when discovery is incomplete. Normal import/sync never deletes resources."])
    if bundle["mapping.json"].get("nativeSyncPreviews"):
        lines.extend(["", "## Native Foundry sync evidence", "",
                      "Native dry-run owns missing/stale decisions. Only selected registrations become TODOs.",
                      "Matching registrations may receive separately selected metadata updates.", "", "```json",
                      json.dumps(bundle["mapping.json"]["nativeSyncPreviews"], indent=2), "```",
                      "Execution rechecks native decisions; only recorded create-to-unchanged progress is accepted.",
                      "A failed preview blocks this phase; no bulk sync apply or local substitute diff is used."])
    lines.extend(["", "## Executable work", ""])
    for todo in bundle["todos.json"]["items"]:
        lines.append(f"- `{todo['id']}`: {todo['capabilityId']}; "
                     f"depends on {', '.join(todo['dependsOn']) or 'none'}.")
        lines.append("  Resource prerequisites: " + ", ".join(todo.get("resourceDependencies", [])))
        lines.append("  Caller-owned runtime variables: " + ", ".join(sorted(runtime_references(todo["arguments"]))))
        cap = next(cap for cap in bundle["capability-contract.json"]["capabilities"]
                   if cap["id"] == todo["capabilityId"])
        lines.append("  CLI template: `az aigateway " + " ".join(cap["command"]) + "`.")
        lines.append("  " + " ".join(cap["limitations"]))
        lines.extend(["", "```json", json.dumps({
            "target": todo["target"], "arguments": clean(todo["arguments"]),
            "desiredState": clean(todo["desiredState"]), "precondition": todo["precondition"],
            "behaviorIds": sorted(todo["behaviorResults"]),
        }, indent=2), "```", ""])
    return "\n".join(lines) + "\n"
