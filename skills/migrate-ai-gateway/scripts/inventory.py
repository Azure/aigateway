"""Read-only collection and provenance. No Azure mutation commands live here."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from core import (
    MigrationError, child_resource_id, clean, digest, now, read_json, resource_id,
    run_az, safe_path, subset, invalid_json, unique_keys,
)
from apiops import contract_shape, read_artifacts


DOMAINS = (
    "apis", "backends", "namedValues", "policyFragments", "products",
    "subscriptions", "groups", "loggers", "diagnostics", "certificates",
    "identityProviders", "authorizationProviders", "authorizationServers", "openidConnectProviders",
    "apiVersionSets", "policies", "tags", "gateways",
)
WORKSPACE_DOMAINS = (
    "apis", "backends", "namedValues", "policyFragments", "products",
    "subscriptions", "groups", "loggers", "diagnostics", "apiVersionSets", "tags",
)
EXPORT_NAMES = {
    "apiInformation.json": "apis", "backendInformation.json": "backends",
    "namedValueInformation.json": "namedValues", "productInformation.json": "products",
    "policyFragmentInformation.json": "policyFragments",
}
API_VERSIONS = ("2024-05-01", "2025-09-01-preview")
COLLECTOR_VERSION = "2.4"


def model_operation(method, template, deployment_id=None):
    """Recognize source protocols independently of destination capabilities."""
    if not isinstance(template, str) or not isinstance(method, str):
        return None
    path = template.split("?", 1)[0]
    if (not path.startswith("/") or any(value in path for value in ("*", "@", "%", "\\", "#", "..", "//"))
            or "{{" in path):
        return None
    deployment = re.match(r"^/(?:openai/)?deployments/([^/]+)(/.*)$", path)
    if deployment:
        name = deployment[1]
        parameter = re.fullmatch(r"\{[^/{}]+\}", name)
        if (not parameter and ("{" in name or "}" in name)
                or deployment_id is not None and not parameter and name != deployment_id):
            return None
        path = deployment[2]
    for prefix in ("/openai/v1", "/openai", "/v1", "/models"):
        if path.startswith(prefix + "/"):
            path = path[len(prefix):]
            break
    if path.startswith("/anthropic/v1/"):
        path = path.removeprefix("/anthropic/v1")
        return path if method == "POST" and path in ("/messages", "/complete") else None
    inference = {
        "/chat/completions", "/completions", "/responses", "/embeddings",
        "/images/generations", "/images/edits", "/images/variations",
        "/audio/speech", "/audio/transcriptions", "/audio/translations",
        "/rerank",
    }
    if (method == "POST" and path in inference) or (method == "GET" and path == "/realtime"):
        return path
    return None


def endpoint_evidence(value):
    if not isinstance(value, str) or any(marker in value for marker in ("@(", "@{", "{{")):
        return []
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if url.scheme != "https" or not host or url.username or url.password or url.port not in (None, 443):
            return []
    except ValueError:
        return []
    if host == "api.openai.com":
        return [{"kind": "provider-endpoint", "provider": "OpenAI"}]
    suffixes = (".openai.azure.com", ".openai.azure.us", ".openai.azure.cn",
                ".services.ai.azure.com", ".services.ai.azure.us", ".services.ai.azure.cn",
                ".models.ai.azure.com", ".inference.ai.azure.com")
    if host.endswith(suffixes):
        return [{"kind": "provider-endpoint", "provider": "Foundry"}]
    operation = model_operation("POST", url.path)
    if operation:
        return [{"kind": "protocol-endpoint", "operation": operation}]
    return []


def resource_model_evidence(properties, domain):
    evidence = []
    for field in (("url", "resourceId") if domain == "backends" else
                  ("serviceUrl",) if domain == "apis" else
                  ("value",) if domain == "namedValues" and properties.get("secret") is False else ()):
        evidence.extend({**entry, "field": field} for entry in endpoint_evidence(properties.get(field)))
    if domain == "backends":
        value = properties.get("resourceId")
        if isinstance(value, str):
            try:
                path = urlsplit(value).path if value.startswith("https://") else value
            except ValueError as exc:
                raise MigrationError("Malformed source backend resource reference.") from exc
            if re.fullmatch(r"/subscriptions/[A-Za-z0-9_.-]+/resourceGroups/[A-Za-z0-9_.-]+/providers/"
                            r"Microsoft\.CognitiveServices/accounts/[A-Za-z0-9_.-]+", path, re.I):
                # Cognitive Services also hosts non-model workloads; this is a discovery lead, not proof.
                evidence.append({"kind": "account-resource", "field": "resourceId", "resourceId": path})
    return evidence


def mcp_configuration(properties):
    """Project MCP API endpoint declarations without depending on endpoint names."""
    config = properties.get("mcpProperties")
    if config is None:
        return None
    issues = []
    if not isinstance(config, dict):
        return {"sourceProperties": clean_mcp_properties(config),
                "transportType": None, "endpoints": [], "issues": ["invalid-properties"]}

    safe_config = clean_mcp_properties(config)
    declared = safe_config.get("endpoints")
    endpoints = []
    if isinstance(declared, list):
        values = declared
    elif isinstance(declared, dict):
        if "uriTemplate" in declared or "name" in declared:
            values = [declared]
        else:
            values = [{"name": name, **value} if isinstance(value, dict) else
                      {"name": name, "uriTemplate": value} if isinstance(value, str) else value
                      for name, value in declared.items()]
    elif declared is None:
        values = []
    else:
        values = []
        issues.append("invalid-endpoints")

    for value in values:
        if not isinstance(value, dict):
            issues.append("invalid-endpoint")
            continue
        name, uri = value.get("name"), value.get("uriTemplate")
        if name is not None and not isinstance(name, str):
            issues.append("invalid-endpoint-name")
            name = None
        if uri is not None and not isinstance(uri, str):
            issues.append("invalid-endpoint-uri-template")
            uri = None
        endpoints.append({key: field for key, field in (("name", name), ("uriTemplate", uri))
                          if field is not None})
    return {
        "sourceProperties": safe_config,
        "transportType": safe_config.get("transportType"),
        "endpoints": sorted(endpoints, key=lambda endpoint: (
            endpoint.get("name", "").lower(), endpoint.get("uriTemplate", ""))),
        "issues": sorted(set(issues)),
    }


def clean_mcp_properties(value, key=""):
    if isinstance(value, dict):
        return {name: clean_mcp_properties(child, name) for name, child in value.items()}
    if isinstance(value, list):
        return [clean_mcp_properties(child, key) for child in value]
    if isinstance(value, str) and key == "uriTemplate":
        try:
            parts = urlsplit(value)
            base = clean(urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), key)
            if not isinstance(base, str):
                return base
            query = urlencode([(name, "[redacted]") for name, _ in parse_qsl(parts.query)])
            return base + ("?" + query if query else "")
        except ValueError:
            path, separator, query = value.partition("?")
            base = clean(path, key)
            if not isinstance(base, str):
                return base
            return base + (separator + urlencode(
                [(pair.partition("=")[0], "[redacted]") for pair in query.split("&") if pair])
                if separator else "")
    return clean(value, key)


def classify_apis(inventory):
    items = inventory["items"]
    by_id = {item["id"].lower(): item for item in items}
    children = {}
    for item in items:
        children.setdefault((item["scope"].lower(), item["domain"]), []).append(item)

    def scoped_reference(item, domain, name):
        match = re.match(r"^(.+?/providers/Microsoft\.ApiManagement/service/[^/]+"
                         r"(?:/workspaces/[^/]+)?)(?:/|$)", item["id"], re.I)
        parent = match[1] + "/" + domain if match else ""
        if re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            if domain == "namedValues" and match:
                matches = [entry for entry in children.get((match[1].lower(), domain), [])
                           if entry["resource"].get("properties", {}).get("displayName") == name]
                if matches:
                    return matches[0] if len(matches) == 1 else None
            target = by_id.get((parent + "/" + name).lower())
            if (domain == "namedValues" and target
                    and target["resource"].get("properties", {}).get("displayName", name) != name):
                return None
            return target
        if parent and child_resource_id(name, parent) and "/" not in name[len(parent) + 1:]:
            return by_id.get(name.lower())
        return None

    def section_nodes(item, section):
        shape = item["policyShape"]
        roots = [node["path"] for node in shape if node["statement"] == section]
        return [node for node in shape if any(
            node["path"] == root or node["path"].startswith(root + "/") for root in roots)]

    def inherit(policies, parent, section):
        nodes = [(item, section_nodes(item, section)) for item in policies]
        present = [(item, node) for item, shape in nodes for node in shape]
        if not present:
            return parent
        if any(node["statement"] == "base" for _, node in present):
            return [*parent, *present]
        return present

    operation_records = [item for item in items if item["domain"] == "api-operations"]
    operation_ids = {item["id"].lower(): item for item in operation_records}

    def resolve_operation(identifier):
        if not isinstance(identifier, str):
            return None
        operation = operation_ids.get(identifier.lower())
        if operation:
            return operation
        matches = [item for item in operation_records
                   if identifier.startswith("/") and item["id"].lower().endswith(identifier.lower())]
        return matches[0] if len(matches) == 1 else None

    for api in (item for item in items if item["domain"] == "apis"):
        api_id = api["id"].lower()
        operations = children.get((api_id, "api-operations"), [])
        api_policies = children.get((api_id, "api-policies"), [])
        products = {item["scope"].lower() for item in items if item["domain"] == "product-apis"
                    and str(item["resource"].get("properties", {}).get("targetResourceId", "")).lower().split(";rev=", 1)[0]
                    == api_id.split(";rev=", 1)[0]}
        product_policies = [item for product in sorted(products)
                            for item in children.get((product, "product-policies"), [])]
        global_policies = children.get((inventory["sourceId"].lower(), "policies"), [])
        pending = [(api, None), *((operation, None) for operation in operations)]
        for section in ("inbound", "backend"):
            global_nodes = [(item, node) for item in global_policies for node in section_nodes(item, section)]
            # Products are alternative admission paths, not a single merged policy chain.
            parents = [global_nodes, *(inherit([policy], global_nodes, section) for policy in product_policies)]
            for parent in parents:
                api_nodes = inherit(api_policies, parent, section)
                if operations:
                    for operation in operations:
                        op_policies = children.get((operation["id"].lower(), "operation-policies"), [])
                        pending.extend(inherit(op_policies, api_nodes, section))
                else:
                    pending.extend(api_nodes)
        evidence, unresolved, seen = [], [], set()
        while pending:
            item, node = pending.pop()
            key = (item["id"].lower(), node["path"] if node else None)
            if key in seen:
                continue
            seen.add(key)
            facts = item.get("facts", {})
            found = (node.get("modelEvidence", []) if node else
                     facts.get("endpointEvidence", [])
                     if item["domain"] == "apis" else facts.get("modelEvidence", []))
            evidence.extend({"sourceId": item["id"], **({"path": node["path"]} if node else {}), **entry}
                            for entry in found)
            if node and node.get("routingUnresolved"):
                unresolved.append({"sourceId": item["id"], "path": node["path"], "reason": "dynamic-routing"})
            if node is None and facts.get("routingUnresolved"):
                unresolved.append({"sourceId": item["id"], "reason": "dynamic-routing"})
            references = ([reference for reference in node["references"]
                           if reference["domain"] != "namedValues"
                           or node["statement"] in ("set-backend-service", "rewrite-uri")]
                          if node else list(facts.get("routingReferences", [])))
            if node is None and item["domain"] == "apis":
                backend = item["resource"].get("properties", {}).get("backendId")
                if isinstance(backend, str):
                    references.append({"domain": "backends", "name": backend})
                elif backend:
                    unresolved.append({"sourceId": item["id"], "reason": "dynamic-backend"})
            if node is None and item["domain"] == "backends":
                pool = item["resource"].get("properties", {}).get("pool") or {}
                references.extend({"domain": "backends", "name": entry["id"]}
                                  for entry in pool.get("services", []) if isinstance(entry, dict)
                                  and isinstance(entry.get("id"), str))
            for reference in references:
                target = scoped_reference(item, reference["domain"], reference["name"])
                if target is None:
                    literal = (re.fullmatch(r"[A-Za-z0-9_.-]+", reference["name"])
                               or child_resource_id(reference["name"], inventory["sourceId"]))
                    unresolved.append({"sourceId": item["id"], "reason": "unresolved-reference",
                                       "domain": reference["domain"],
                                       **({"name": reference["name"]} if literal else {})})
                elif target["domain"] == "policyFragments":
                    pending.extend((target, child) for child in target["policyShape"])
                else:
                    pending.append((target, None))
                    if target["domain"] == "namedValues" and not target.get("facts", {}).get("modelEvidence"):
                        unresolved.append({"sourceId": target["id"], "reason": "opaque-routing-value"})
        properties = api["resource"].get("properties", {})
        paths = {operation["resource"].get("properties", {}).get("urlTemplate", "").split("?", 1)[0]
                 for operation in operations if operation.get("facts", {}).get("modelOperation")
                 and isinstance(operation["resource"].get("properties", {}).get("urlTemplate"), str)}
        observed_type = str(properties.get("type") or properties.get("apiType") or "").lower()
        tool_records = children.get((api_id, "api-tools"), [])
        mcp = mcp_configuration(properties)
        if mcp is None and (observed_type == "mcp" or tool_records):
            mcp = {"sourceProperties": {}, "transportType": None, "endpoints": [], "issues": []}
        if mcp is not None:
            tool_bindings = []
            for tool in tool_records:
                tool_properties = tool["resource"].get("properties", {})
                operation_id = tool_properties.get("operationId")
                operation = resolve_operation(operation_id)
                tool_bindings.append({
                    "toolId": tool["id"],
                    "displayName": tool_properties.get("displayName"),
                    "operationId": operation_id,
                    "resolvedOperationId": operation["id"] if operation else None,
                    "operationResolution": ("resolved" if operation else
                                            "unresolved" if operation_id else "not-bound"),
                })
            backend_id = properties.get("backendId")
            backend = scoped_reference(api, "backends", backend_id) if isinstance(backend_id, str) else None
            backend_properties = backend["resource"].get("properties", {}) if backend else {}
            mcp["backend"] = ({
                "id": backend["id"],
                "url": backend_properties.get("url"),
                "credentialFields": backend.get("facts", {}).get("credentialFields", []),
                "headerNames": backend.get("facts", {}).get("headerNames", []),
                "queryParameterNames": backend.get("facts", {}).get("queryParameterNames", []),
                "certificateReferences": backend.get("facts", {}).get("certificateReferences"),
                "certificateReferenceIds": backend.get("facts", {}).get("certificateReferenceIds", []),
                "certificateReferenceCount": backend.get("facts", {}).get("certificateReferenceCount"),
                "authorizationScheme": backend.get("facts", {}).get("authorizationScheme"),
                "authorizationParameterPresent": backend.get("facts", {}).get(
                    "authorizationParameterPresent"),
                "credentialExpressions": backend.get("facts", {}).get("credentialExpressions"),
            } if backend else ({
                "reference": backend_id, "resolved": False
            } if backend_id is not None else None))
            mcp["serviceUrl"] = properties.get("serviceUrl")
            mcp["tools"] = sorted(tool_bindings, key=lambda tool: tool["toolId"].lower())
            mcp["policySourceIds"] = sorted({
                policy["id"] for policy in items
                if policy["domain"] in ("policies", "product-policies", "api-policies", "operation-policies")
                and (policy["scope"].lower() == inventory["sourceId"].lower()
                     or policy["scope"].lower() == api_id
                     or policy["scope"].lower() in products
                     or policy["scope"].lower() in {operation["id"].lower() for operation in operations})
            }, key=str.lower)
            policy_records = [by_id[identifier.lower()] for identifier in mcp["policySourceIds"]]
            policy_backends, visited_fragments = {}, set()

            def index_policy_backends(policy):
                for node in policy["policyShape"]:
                    for reference in node["references"]:
                        target = scoped_reference(policy, reference["domain"], reference["name"])
                        if target is None:
                            continue
                        if target["domain"] == "backends":
                            key = (policy["id"].lower(), node["path"], target["id"].lower())
                            backend_properties = target["resource"].get("properties", {})
                            policy_backends[key] = {
                                "policyId": policy["id"],
                                "policyPath": node["path"],
                                "backendId": target["id"],
                                "url": backend_properties.get("url"),
                                "credentialFields": target.get("facts", {}).get("credentialFields", []),
                                "headerNames": target.get("facts", {}).get("headerNames", []),
                                "queryParameterNames": target.get("facts", {}).get("queryParameterNames", []),
                                "certificateReferences": target.get("facts", {}).get("certificateReferences"),
                                "certificateReferenceIds": target.get("facts", {}).get(
                                    "certificateReferenceIds", []),
                                "certificateReferenceCount": target.get("facts", {}).get(
                                    "certificateReferenceCount"),
                                "authorizationScheme": target.get("facts", {}).get("authorizationScheme"),
                                "authorizationParameterPresent": target.get("facts", {}).get(
                                    "authorizationParameterPresent"),
                                "credentialExpressions": target.get("facts", {}).get("credentialExpressions"),
                            }
                        elif target["domain"] == "policyFragments" and target["id"].lower() not in visited_fragments:
                            visited_fragments.add(target["id"].lower())
                            index_policy_backends(target)

            for policy in policy_records:
                index_policy_backends(policy)
            mcp["policyBackends"] = [policy_backends[key] for key in sorted(policy_backends)]
            api.setdefault("facts", {})["mcpConfiguration"] = mcp
        established = any(entry["kind"] != "account-resource" for entry in evidence)
        wildcard = any("*" in str(operation["resource"].get("properties", {}).get("urlTemplate", ""))
                       for operation in operations)
        role = ("mcp" if observed_type == "mcp" or mcp is not None or children.get((api_id, "api-tools")) else
                "model-protocol" if established else
                observed_type if observed_type and observed_type != "http" else
                "model-candidate" if evidence else
                "wildcard-proxy" if wildcard else "rest" if operations else "unclassified")
        api["facts"] = {**api.get("facts", {}), "role": role, "operationCount": len(operations),
                        "modelProtocolPaths": sorted(paths),
                        "roleEstablished": role not in ("model-candidate", "wildcard-proxy", "unclassified"),
                        "modelEvidence": sorted(evidence, key=lambda entry: json.dumps(entry, sort_keys=True)),
                        "unresolvedModelRouting": sorted(unresolved, key=lambda entry: json.dumps(entry, sort_keys=True))}
    return inventory


def inventory_item(raw, scope, domain, authority="authoritative", evidence="live"):
    properties = raw.get("properties", {})
    if not isinstance(properties, dict):
        raise MigrationError("Malformed source resource properties.")
    policy = domain.endswith("policies") or domain == "policyFragments"
    if policy and not isinstance(properties.get("value"), str):
        raise MigrationError("Policy body is missing; behavior inventory is incomplete.")
    shape = policy_shape(properties["value"]) if policy else []
    resource = clean(raw)
    if domain == "apis" and "mcpProperties" in properties:
        resource["properties"]["mcpProperties"] = clean_mcp_properties(properties["mcpProperties"])
    if domain == "api-contracts" and "structure" in properties:
        # This allowlisted projection contains schemas, not raw payload/content values.
        resource["properties"]["structure"] = properties["structure"]
    if domain == "api-schemas":
        document = properties.get("document")
        if "json" in str(properties.get("contentType", "")).lower():
            if not isinstance(document, dict):
                raise MigrationError("JSON API schema document is not an object.")
            value = document["value"] if "value" in document else document
            try:
                parsed = (json.loads(value, parse_constant=lambda _: invalid_json(),
                                     object_pairs_hook=unique_keys)
                          if isinstance(value, str) else value)
            except (ValueError, RecursionError) as exc:
                raise MigrationError("Malformed JSON API schema.") from exc
            if not isinstance(parsed, dict):
                raise MigrationError("JSON API schema is not an object.")
            structure = contract_shape(parsed)
            digest(structure)
            resource["properties"]["document"] = {"structure": structure}
        elif isinstance(document, dict):
            resource["properties"]["document"]["analysis"] = "opaque-schema; inspect separately"
    item = {"id": raw["id"], "scope": scope, "domain": domain, "resource": resource,
            "policyShape": shape, "authority": authority, "evidence": evidence}
    model_evidence = resource_model_evidence(properties, domain)
    if model_evidence:
        item["facts"] = {"endpointEvidence" if domain == "apis" else "modelEvidence": model_evidence}
    if domain in ("apis", "backends"):
        fields = ("serviceUrl",) if domain == "apis" else ("url", "resourceId")
        values = [properties[field] for field in fields if isinstance(properties.get(field), str)]
        references = sorted({name for value in values for name in re.findall(r"\{\{([A-Za-z0-9_.-]+)\}\}", value)})
        if references or any(marker in value for value in values for marker in ("@(", "@{", "{{")):
            item.setdefault("facts", {}).update(routingUnresolved=True, routingReferences=[
                {"domain": "namedValues", "name": name} for name in references])
    if domain == "backends":
        credentials = properties.get("credentials") or {}
        if not isinstance(credentials, dict) or any(
                credentials.get(field) is not None and not isinstance(credentials[field], dict)
                for field in ("header", "query")):
            raise MigrationError("Malformed source backend credential metadata.")
        authorization = credentials.get("authorization")
        certificate_ids = credentials.get("certificateIds")
        certificate_thumbprints = credentials.get("certificate")
        if authorization is None:
            authorization = {}
        if certificate_ids is None:
            certificate_ids = []
        if certificate_thumbprints is None:
            certificate_thumbprints = []
        if (not isinstance(authorization, dict) or not isinstance(certificate_ids, list)
                or not all(isinstance(value, str) for value in certificate_ids)
                or not isinstance(certificate_thumbprints, list)
                or not all(isinstance(value, str) for value in certificate_thumbprints)
                or any(authorization.get(field) is not None and not isinstance(authorization[field], str)
                       for field in ("scheme", "parameter"))):
            raise MigrationError("Malformed source backend authorization metadata.")
        pool = properties.get("pool")
        if pool is not None and (
                not isinstance(pool, dict) or not isinstance(pool.get("services", []), list)
                or any(not isinstance(member, dict) or not isinstance(member.get("id"), str)
                       for member in pool.get("services", []))):
            raise MigrationError("Malformed source backend pool metadata.")
        item["facts"] = {**item.get("facts", {}),
                "credentialFields": sorted(credentials),
                "headerNames": sorted(credentials.get("header") or {}),
                "queryParameterNames": sorted(credentials.get("query") or {}),
                "certificateReferences": bool(certificate_ids or certificate_thumbprints),
                "certificateReferenceIds": sorted(set(certificate_ids)),
                "certificateReferenceCount": len(set(certificate_ids)) + len(set(certificate_thumbprints)),
                "authorizationScheme": authorization.get("scheme"),
                "authorizationParameterPresent": authorization.get("parameter") is not None,
                "credentialExpressions": "@(" in json.dumps(credentials) or "@{" in json.dumps(credentials),
                "namedValueReferences": sorted(set(re.findall(
                    r"\{\{([A-Za-z0-9_.-]+)\}\}", json.dumps(credentials)))),
        }
    if policy:
        allowed = {"policies", "fragment", "inbound", "backend", "outbound", "on-error",
                   "base", "forward-request", "set-backend-service"}
        routing_only = all(
            node["statement"] in allowed and not node["hasText"]
            and set(node["attributes"]) <= (
                {"id", "backend-id"} if node["statement"] == "set-backend-service" else {"id"})
            and (node["statement"] != "set-backend-service" or
                 any(r["domain"] == "backends" for r in node["references"]))
            for node in shape)
        item["facts"] = {"routingOnly": routing_only}
    if domain == "api-operations":
        request = properties.get("request") or {}
        if not isinstance(request, dict):
            raise MigrationError("Malformed source operation request.")
        responses = properties.get("responses") or []
        if (not isinstance(responses, list) or any(
                not isinstance(response, dict) or not isinstance(response.get("representations") or [], list)
                or not all(isinstance(rep, dict) for rep in response.get("representations") or [])
                for response in responses)):
            raise MigrationError("Malformed source response contract metadata.")
        def parameters(values):
            if not isinstance(values, list) or not all(isinstance(p, dict) for p in values):
                raise MigrationError("Malformed source operation parameters.")
            return [{**{key: p.get(key) for key in ("name", "type", "required")},
                     "opaqueConstraints": [key for key in ("defaultValue", "values", "schemaId", "typeName")
                                           if p.get(key) not in (None, "", [])]}
                    for p in values]
        item["facts"] = {
            "templateParameters": parameters(properties.get("templateParameters") or []),
            "queryParameters": parameters(request.get("queryParameters") or []),
            "requestHeaders": parameters(request.get("headers") or []),
            "responseContracts": [
                {"status": response.get("statusCode"),
                 "representations": [{key: rep.get(key) for key in ("contentType", "schemaId", "typeName")}
                                     for rep in response.get("representations") or []]}
                for response in responses],
        }
        operation = model_operation(properties.get("method"), properties.get("urlTemplate"))
        if operation:
            item["facts"].update(modelOperation=operation, modelEvidence=[
                {"kind": "protocol-operation", "method": properties["method"], "operation": operation}])
    if domain == "api-tools":
        item["facts"] = {
            "displayName": properties.get("displayName"),
            "operationId": properties.get("operationId"),
        }
    return item


def item_behaviors(item, raw=None):
    item_id, scope, domain = item["id"], item["scope"], item["domain"]
    behaviors = [{"id": "behavior:" + digest(item_id.lower())[7:],
                  "sourceId": item_id, "type": domain, "scope": scope}]
    if domain == "service":
        raw = raw if raw is not None else item["resource"]
        properties = {**raw.get("properties", {}),
                      "identity": raw.get("identity"), "zones": raw.get("zones")}
        for key, value in sorted(properties.items()):
            if value is not None and key not in ("provisioningState", "targetProvisioningState"):
                behaviors.append({
                    "id": "behavior:" + digest([item_id.lower(), key])[7:],
                    "sourceId": item_id, "type": "service", "scope": scope, "property": key})
    for node in item["policyShape"]:
        behaviors.append({
            "id": "behavior:" + digest([item_id.lower(), node["path"]])[7:],
            "sourceId": item_id, "type": "policies", "scope": scope,
            "statement": node["statement"], "path": node["path"]})
    return behaviors


class Reader:
    def __init__(self, source_id, runner=run_az, endpoint=None):
        self.source_id = source_id
        self.target = resource_id(source_id)
        self.run = runner
        endpoint = endpoint or runner(
            ["az", "cloud", "show", "--query", "endpoints.resourceManager", "-o", "json"]
        )
        if not isinstance(endpoint, str):
            raise MigrationError("Invalid Azure cloud resource-manager endpoint.")
        parts = urlsplit(endpoint)
        if (parts.scheme != "https" or not parts.netloc or parts.username or parts.password
                or parts.query or parts.fragment):
            raise MigrationError("Invalid Azure cloud resource-manager endpoint.")
        self.endpoint = endpoint.rstrip("/")

    def url(self, path, version="2024-05-01"):
        return self.endpoint + path + "?api-version=" + version

    def get(self, url):
        return self.run(["az", "rest", "--method", "get", "--url", url,
                         "--headers", "Accept=application/json",
                         "--subscription", self.target["subscription"], "-o", "json"])

    def revision_item(self, item, path):
        parent = path.removesuffix("/revisions")
        relative_parent = parent[len(self.source_id):]
        if (not child_resource_id(parent, self.source_id) or not re.fullmatch(
                r"/(?:workspaces/[A-Za-z0-9_.-]+/)?apis/[A-Za-z0-9_.-]+",
                relative_parent, re.I)):
            raise MigrationError("Revision collection does not belong to an exact source API.")
        properties = item.get("properties", {})
        if not isinstance(properties, dict):
            raise MigrationError("Malformed revision properties.")
        number = item.get("apiRevision") or properties.get("apiRevision")
        if not isinstance(number, str) or not re.fullmatch(r"[0-9]+", number):
            raise MigrationError("Revision has no usable revision number.")
        relative_api = relative_parent + ";rev=" + number
        absolute_api = self.source_id + relative_api
        api_id = item.get("apiId")
        if "apiId" in item and (
                not isinstance(api_id, str)
                or api_id.lower() not in (relative_api.lower(), absolute_api.lower())):
            raise MigrationError("Revision API identity differs from its selected parent.")
        identifier = item.get("id")
        if identifier:
            name = parent.rsplit("/", 1)[1] + ";rev=" + number
            relative_id = relative_api + "/revisions/" + name
            known_relative = (isinstance(identifier, str) and identifier.lower() in (
                relative_id.lower(), (self.source_id + relative_id).lower()) and api_id is not None)
            known_absolute = (child_resource_id(identifier, path)
                              and identifier[len(path) + 1:].lower() in (number, name.lower()))
            if not known_relative and not known_absolute:
                raise MigrationError("Unrecognized or out-of-scope revision identity.")
        elif identifier is not None and identifier != "":
            raise MigrationError("Malformed revision identity.")
        result = {**item, "id": path + "/observed-" + digest(number)[7:],
                  "apiId": absolute_api, "syntheticId": True}
        if identifier:
            result["observedId"] = identifier
        if api_id is not None:
            result["observedApiId"] = api_id
        return result

    def detail(self, item, version, policy=False):
        url = self.url(item["id"], version) + ("&format=rawxml" if policy else "")
        result = self.get(url)
        if (not isinstance(result, dict)
                or str(result.get("id", "")).lower() != item["id"].lower()
                or not isinstance(result.get("properties"), dict)):
            raise MigrationError("Source detail is malformed or has a different identity.")
        return result

    def collection(self, path, version="2024-05-01"):
        original = self.url(path, version)
        url, seen, items = original, set(), []
        while url:
            current, first = urlsplit(url), urlsplit(original)
            if (current.scheme != "https" or current.netloc != first.netloc
                    or current.path.lower() != first.path.lower()
                    or "%" in current.path or "\\" in current.path or ".." in current.path
                    or current.username or current.password or current.fragment
                    or parse_qs(current.query).get("api-version") != [version]
                    or url in seen or len(seen) >= 10000):
                raise MigrationError("Unsafe or cyclic ARM collection continuation.")
            seen.add(url)
            result = self.get(url)
            if not isinstance(result, dict) or not isinstance(result.get("value"), list):
                raise MigrationError("ARM collection did not return a value array.")
            for item in result["value"]:
                if not isinstance(item, dict):
                    raise MigrationError("Malformed collection item.")
                if path.endswith("/revisions"):
                    item = self.revision_item(item, path)
                if not child_resource_id(item.get("id"), self.source_id):
                    raise MigrationError("Collection contains a resource outside its scope.")
                items.append(item)
            next_link = result.get("nextLink")
            if next_link and not isinstance(next_link, str):
                raise MigrationError("Invalid ARM continuation.")
            url = urljoin(original, next_link) if next_link else None
        if len({item["id"].lower() for item in items}) != len(items):
            raise MigrationError("Duplicate resource IDs in collection.")
        return sorted(items, key=lambda item: item["id"].lower())


def policy_shape(raw):
    if not isinstance(raw, str) or "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise MigrationError("Unrecognized or unsafe policy XML.")
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise MigrationError("Malformed policy XML.") from exc
    nodes = []
    pending = [(tree, "0")]
    while pending:
        element, path = pending.pop()
        public = {"calls", "renewal-period", "tokens-per-minute", "token-limit",
                  "estimate-prompt-tokens"}
        references = []
        reference_attribute = {
            "include-fragment": ("fragment-id", "policyFragments"),
            "set-backend-service": ("backend-id", "backends"),
        }.get(element.tag)
        if reference_attribute:
            attribute, domain = reference_attribute
            name = element.attrib.get(attribute, "")
            if re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                references.append({"domain": domain, "name": name})
        for value in [*element.attrib.values(), element.text or ""]:
            for name in re.findall(r"\{\{([A-Za-z0-9_.-]+)\}\}", value):
                reference = {"domain": "namedValues", "name": name}
                if reference not in references:
                    references.append(reference)
        nodes.append({"path": path, "statement": element.tag,
                      "attributes": {key: value if key in public and re.fullmatch(
                          r"[0-9]+|true|false", value) else {"redacted": True}
                          for key, value in element.attrib.items()},
                      "hasText": bool((element.text or "").strip()),
                      "references": references})
        node = nodes[-1]
        if element.tag.startswith(("azure-openai-", "llm-")):
            node["modelEvidence"] = [{"kind": "ai-policy", "statement": element.tag}]
        if element.tag == "set-backend-service":
            value = element.attrib.get("base-url", "")
            hints = endpoint_evidence(value)
            if hints:
                node["modelEvidence"] = hints
            if any(marker in value or marker in element.attrib.get("backend-id", "")
                   for marker in ("@(", "@{", "{{")):
                node["routingUnresolved"] = True
            elif value:
                safe_url = clean(value, "baseUrl")
                if isinstance(safe_url, str):
                    node["routing"] = {"baseUrl": safe_url}
        if element.tag == "rewrite-uri":
            template = element.attrib.get("template", "")
            operation = model_operation("POST", template)
            if operation:
                node["modelEvidence"] = [{"kind": "protocol-rewrite", "operation": operation}]
            if any(marker in template for marker in ("@(", "@{", "{{")):
                node["routingUnresolved"] = True
            elif template:
                node["routing"] = {"uriTemplate": clean_mcp_properties(template, "uriTemplate")}
        pending.extend((child, f"{path}/{index}") for index, child in reversed(
            list(enumerate(element))))
    return nodes


def source_inventory(source_id, runner=run_az, endpoint=None):
    reader = Reader(source_id, runner, endpoint)
    service = reader.get(reader.url(source_id))
    if not isinstance(service, dict) or str(service.get("id", "")).lower() != source_id.lower():
        raise MigrationError("Source service identity mismatch.")
    sku = service["sku"].get("name") if isinstance(service.get("sku"), dict) else None
    if not isinstance(sku, str) or not sku or not isinstance(service.get("properties"), dict):
        raise MigrationError("Malformed source service properties or service profile.")
    result = {"schemaVersion": "5.0", "producer": "skill-local",
              "collectorVersion": COLLECTOR_VERSION, "sourceId": source_id,
              "sku": sku, "service": clean(service), "capturedAt": now(),
              "items": [], "behaviors": [], "coverage": [], "provenance": [],
              "conflicts": []}

    def add_item(raw, scope, domain):
        item_id = str(raw["id"])
        if any(item["id"].lower() == item_id.lower() for item in result["items"]):
            return
        item = inventory_item(raw, scope, domain)
        result["items"].append(item)
        result["behaviors"].extend(item_behaviors(item, raw))

    def collect(scope, domain, path, version="2024-05-01", link=None):
        coverage = {"scope": scope, "domain": domain, "status": "failed",
                    "authority": "insufficient", "establishesCompleteness": False,
                    "evidence": "live", "error": None}
        try:
            items = reader.collection(path, version)
            collected = []
            for item in items:
                try:
                    policy = domain.endswith("policies") or domain == "policyFragments"
                    if policy or domain in ("apis", "backends", "api-operations", "api-schemas") or (
                            "/workspaces/" in scope.lower() and domain in WORKSPACE_DOMAINS):
                        item = reader.detail(item, version, policy)
                    if domain in ("product-apis", "product-groups", "product-tags",
                                  "api-tags", "gateway-apis", "tag-apis", "tag-products"):
                        if link:
                            target = item.get("properties", {}).get(link)
                            target_domain = {"apiId": "apis", "groupId": "groups",
                                             "productId": "products"}[link]
                            base, workspace_child = re.split("/workspaces/", scope, maxsplit=1, flags=re.I)
                            workspace = base + "/workspaces/" + workspace_child.split("/")[0]
                            target_collection = workspace + "/" + target_domain
                            if (not child_resource_id(target, target_collection)
                                    or "/" in target[len(target_collection) + 1:]):
                                raise MigrationError("Workspace link target escaped its resource scope.")
                            if domain in ("tag-apis", "tag-products"):
                                item_scope = target
                                item_domain = "api-tags" if domain == "tag-apis" else "product-tags"
                                item = association(target + "/tags", scope)
                                add_item(item, item_scope, item_domain)
                            else:
                                item = association(scope + "/" + target_domain, target)
                                add_item(item, scope, domain)
                        else:
                            item = association(path, item["id"])
                            add_item(item, scope, domain)
                    else:
                        add_item(item, scope, domain)
                    collected.append(item)
                except MigrationError:
                    coverage["error"] = "Resource detail failed or malformed; inspect securely and resume."
                    coverage.setdefault("failedResourceIds", []).append(item["id"])
            if coverage["error"]:
                coverage["status"] = "partial" if collected else "failed"
            else:
                coverage.update(status="complete" if items else "empty",
                                authority="authoritative", establishesCompleteness=True)
        except MigrationError as exc:
            # Failure details can contain secrets. A gap is explicit and never absence,
            # except when the service states that the tier does not offer the collection.
            if exc.code == "MethodNotAllowedInPricingTier":
                coverage.update(status="notApplicable", authority="authoritative",
                                establishesCompleteness=True,
                                evidence=f"live:{sku}-pricing-tier-restriction")
            else:
                coverage["error"] = "Collection failed or malformed; inspect securely and resume."
            collected = []
        result["coverage"].append(coverage)
        return collected

    visited_apis = set()

    def collect_api(item, scope, version):
        api_id = item["id"]
        if api_id.lower() in visited_apis:
            return
        visited_apis.add(api_id.lower())
        api_type = item.get("properties", {}).get("type") or item.get("properties", {}).get("apiType")
        if scope == source_id:
            collect(api_id, "api-tools", api_id + "/tools", "2025-09-01-preview")
        else:
            result["coverage"].append({
                "scope": api_id, "domain": "api-tools",
                "status": "notApplicable", "authority": "authoritative",
                "establishesCompleteness": True,
                "evidence": "not-in-service-level-tools-resource-contract",
                "error": None})
        for child in ("operations", "policies", "schemas", "diagnostics", "releases", "tags"):
            if child == "tags" and scope != source_id:
                continue
            nested = collect(api_id, "api-" + child, api_id + "/" + child, version)
            if child == "operations":
                for operation in nested:
                    collect(operation["id"], "operation-policies",
                            operation["id"] + "/policies", version)
        if ";rev=" not in api_id.lower():
            revisions = collect(api_id, "api-revisions", api_id + "/revisions", version)
            for revision in revisions:
                number = revision.get("apiRevision") or revision.get("properties", {}).get("apiRevision")
                if not isinstance(number, str) or not re.fullmatch(r"[0-9]+", number):
                    # The revisions collection is retained, but its configurations are unknown.
                    result["coverage"].append({
                        "scope": api_id, "domain": "api-revision-configurations", "status": "failed",
                        "authority": "insufficient", "establishesCompleteness": False,
                        "evidence": "live", "error": "Revision has no usable revision number."})
                    break
                revision_id = api_id + ";rev=" + number
                if revision_id.lower() in visited_apis:
                    continue
                entry = {"scope": revision_id, "domain": "api-revision-configurations",
                         "status": "failed", "authority": "insufficient",
                         "establishesCompleteness": False, "evidence": "live", "error": None}
                try:
                    current = item.get("properties", {})
                    if (revision.get("isCurrent") is True and current.get("isCurrent") is True
                            and current.get("apiRevision") == number):
                        entry.update(status="complete", authority="authoritative",
                                     establishesCompleteness=True, evidence="live:current-api")
                    else:
                        detail = reader.detail({"id": revision_id}, version)
                        add_item(detail, scope, "apis")
                        entry.update(status="complete", authority="authoritative",
                                     establishesCompleteness=True)
                        collect_api(detail, scope, version)
                except MigrationError:
                    entry["error"] = "Revision configuration failed or malformed; inspect securely."
                result["coverage"].append(entry)

    add_item(service, source_id, "service")
    result["coverage"].append({"scope": source_id, "domain": "service", "status": "complete",
                              "authority": "authoritative", "establishesCompleteness": True,
                              "evidence": "live", "error": None})
    workspaces = collect(source_id, "workspaces", source_id + "/workspaces")
    for scope in [source_id] + [workspace["id"] for workspace in workspaces]:
        domains = DOMAINS if scope == source_id else WORKSPACE_DOMAINS
        for domain in domains:
            version = "2025-09-01-preview" if scope == source_id and domain == "apis" else "2024-05-01"
            items = collect(scope, domain, scope + "/" + domain, version)
            for item in items:
                if domain == "apis":
                    collect_api(item, scope, version)
                elif domain == "products":
                    for child in ("apis", "policies", "groups", "tags"):
                        if scope != source_id and child == "tags":
                            continue
                        link = ({"apis": "apiId", "groups": "groupId"}.get(child)
                                if scope != source_id else None)
                        segment = {"apis": "apiLinks", "groups": "groupLinks"}[child] if link else child
                        collect(item["id"], "product-" + child, item["id"] + "/" + segment, link=link)
                elif domain == "gateways":
                    collect(item["id"], "gateway-apis", item["id"] + "/apis")
                elif domain == "tags" and scope != source_id:
                    for child, link in (("apis", "apiId"), ("products", "productId")):
                        segment = "apiLinks" if child == "apis" else "productLinks"
                        collect(item["id"], "tag-" + child, item["id"] + "/" + segment, link=link)
                elif domain == "authorizationProviders":
                    for authorization in collect(item["id"], "provider-authorizations",
                                                 item["id"] + "/authorizations"):
                        collect(authorization["id"], "authorization-accessPolicies",
                                authorization["id"] + "/accessPolicies")
        if scope != source_id:
            for parent_domain, link_domain, target_domain in (
                    ("apis", "tag-apis", "api-tags"), ("products", "tag-products", "product-tags")):
                tag_coverage = [entry for entry in result["coverage"] if
                                (entry["scope"] == scope and entry["domain"] == "tags") or
                                (entry["scope"].lower().startswith(scope.lower() + "/tags/")
                                 and entry["domain"] == link_domain)]
                complete = bool(tag_coverage) and all(c["establishesCompleteness"] for c in tag_coverage)
                for parent in [i for i in result["items"] if i["scope"] == scope and i["domain"] == parent_domain]:
                    present = any(i["scope"] == parent["id"] and i["domain"] == target_domain
                                  for i in result["items"])
                    result["coverage"].append({
                        "scope": parent["id"], "domain": target_domain,
                        "status": ("complete" if present else "empty") if complete else "failed",
                        "authority": "authoritative" if complete else "insufficient",
                        "establishesCompleteness": complete, "evidence": "live",
                        "error": None if complete else "Workspace tag/link enumeration is incomplete."})
    result["provenance"].append({"kind": "live", "sourceId": source_id,
                                 "apiVersions": list(API_VERSIONS)})
    return classify_apis(result)


def association(path, target):
    return {"id": path + "/association-" + digest(target.lower())[7:],
            "properties": {"targetResourceId": target, "association": True}}


def apply_export(inventory, path, kind, approved_digest):
    """Approved exports corroborate facts; incomplete exports never establish absence."""
    path = safe_path(path)
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    content_digest = export_digest(path)
    if approved_digest != content_digest:
        raise MigrationError("Local export requires explicit approval of its current content digest.")
    found, metadata = read_artifacts(path, inventory["sourceId"]) if kind == "apiops" else ([], None)

    for file in files if kind == "arm" else ():
        if not file.is_file() or file.suffix != ".json":
            continue
        document = read_json(file)
        if kind == "arm":
            def resources(document, parent=None):
                if not isinstance(document, dict):
                    return
                entries = document.get("resources", [])
                if not isinstance(entries, list):
                    raise MigrationError("ARM resources must be an array.")
                for resource in entries:
                    if not isinstance(resource, dict):
                        raise MigrationError("Malformed ARM resource entry.")
                    rtype, name = resource.get("type", ""), resource.get("name", "")
                    if not isinstance(rtype, str):
                        raise MigrationError("ARM resource type must be a literal string.")
                    rid = resource.get("id")
                    if not rid and isinstance(name, str) and "[" not in name:
                        if rtype.lower() == "microsoft.apimanagement/service" and name.lower() == resource_id(inventory["sourceId"])["gateway"].lower():
                            rid = inventory["sourceId"]
                        elif parent and "/" not in rtype:
                            rid = parent + "/" + rtype + "/" + name
                        elif rtype.lower().startswith("microsoft.apimanagement/service/"):
                            segments = name.split("/")
                            types = rtype.split("/")[2:]
                            if (len(segments) == len(types) + 1 and segments[0].lower()
                                    == resource_id(inventory["sourceId"])["gateway"].lower()):
                                rid = inventory["sourceId"] + "".join(
                                    "/" + t + "/" + n for t, n in zip(types, segments[1:]))
                    if rid:
                        yield {**resource, "id": rid}
                    yield from resources(resource, rid)
            for raw in resources(document):
                domain = raw.get("type", "").split("/")[-1]
                canonical = next((name for name in DOMAINS if name.lower() == domain.lower()), None)
                if canonical:
                    rid = raw["id"]
                    suffix = rid[len(inventory["sourceId"]):].split("/")
                    scope = (inventory["sourceId"] + "/workspaces/" + suffix[2]
                             if len(suffix) > 3 and suffix[1] == "workspaces" else inventory["sourceId"])
                    found.append((canonical, scope, raw))
    if not found and metadata is None:
        raise MigrationError("Export contains no recognized resources with explicit ARM identities.")
    observed = {}
    for domain, scope, raw in found:
        rid = raw["id"]
        if not child_resource_id(rid, inventory["sourceId"]) or "[" in rid:
            raise MigrationError("Export resource does not belong to the selected source.")
        observed.setdefault((scope, domain), set()).add(rid.lower())
        candidate = inventory_item(raw, scope, domain, "advisory", kind + ":" + content_digest)
        existing = next((item for item in inventory["items"]
                         if item["id"].lower() == rid.lower()), None)
        if existing:
            expected = candidate["resource"].get("properties", {})
            actual = existing["resource"].get("properties", {})
            if kind == "apiops":
                expected = {key: value for key, value in expected.items()
                            if key not in ("format", "value") and value is not None}
                equivalent = subset(expected, actual) and candidate["policyShape"] == existing["policyShape"]
            else:
                equivalent = expected == actual
            if not equivalent:
                inventory["conflicts"].append({"sourceId": rid, "evidenceDigest": content_digest,
                                               "reason": "Live and local evidence differ."})
            continue
        live_coverage = next((entry for entry in inventory["coverage"]
                              if (entry["scope"], entry["domain"]) == (scope, domain)), None)
        if live_coverage and live_coverage["establishesCompleteness"]:
            inventory["conflicts"].append({
                "sourceId": rid, "evidenceDigest": content_digest,
                "reason": "Local resource is absent from complete higher-authority discovery."})
        inventory["items"].append(candidate)
        inventory["behaviors"].extend(item_behaviors(candidate))
        if live_coverage is None:
            inventory["coverage"].append({
                "scope": scope, "domain": domain, "status": "partial", "authority": "advisory",
                "establishesCompleteness": False, "evidence": kind + ":" + content_digest,
                "error": "Local artifacts do not establish collection completeness."})
        children = (("api-operations", "api-policies", "api-schemas", "api-diagnostics",
                     "api-revisions", "api-releases", "api-tags", "api-tools") if domain == "apis" else
                    ("product-apis", "product-groups", "product-policies", "product-tags") if domain == "products"
                    else ())
        for child in children:
            if not any(c["scope"] == rid and c["domain"] == child for c in inventory["coverage"]):
                inventory["coverage"].append({
                    "scope": rid, "domain": child, "status": "failed", "authority": "insufficient",
                    "establishesCompleteness": False, "evidence": kind + ":" + content_digest,
                    "error": "Export recovered a parent resource, not its child behavior inventory."})
    if metadata is not None:
        if (not isinstance(metadata, dict) or metadata.get("schemaVersion") != "1.0"
                or str(metadata.get("sourceResourceId", "")).lower() != inventory["sourceId"].lower()
                or not isinstance(metadata.get("collections"), list)):
            raise MigrationError("Invalid APIOps completeness metadata.")
        for claim in metadata["collections"]:
            if not isinstance(claim, dict) or set(claim) != {"scope", "domain", "resourceIds", "complete"}:
                raise MigrationError("Invalid APIOps collection claim.")
            if (not isinstance(claim["scope"], str) or not isinstance(claim["domain"], str)
                    or claim["domain"] not in EXPORT_NAMES.values()):
                raise MigrationError("Unsupported APIOps completeness scope/domain.")
            key = (claim["scope"], claim["domain"])
            ids = claim["resourceIds"]
            if (not isinstance(ids, list) or not all(isinstance(rid, str) for rid in ids)
                    or len(set(rid.lower() for rid in ids)) != len(ids)
                    or set(rid.lower() for rid in ids) != observed.get(key, set())
                    or claim["complete"] is not True):
                raise MigrationError("APIOps completeness claim does not match recognized resources.")
            coverage = next((entry for entry in inventory["coverage"]
                             if (entry["scope"], entry["domain"]) == key), None)
            conflicted = any(conflict["sourceId"].lower() in set(rid.lower() for rid in ids)
                             for conflict in inventory["conflicts"])
            for item in inventory["items"]:
                if ((item["scope"], item["domain"]) == key and item["evidence"] == "live"
                        and item["id"].lower() not in {rid.lower() for rid in ids}):
                    inventory["conflicts"].append({
                        "sourceId": item["id"], "evidenceDigest": content_digest,
                        "reason": "Observed live resource omitted by local completeness claim."})
                    conflicted = True
            if coverage is None:
                raise MigrationError("APIOps claim references an undiscovered scope/domain.")
            if not coverage["establishesCompleteness"] and not conflicted:
                # Explicitly approved completeness is required; ordinary export omission is advisory.
                coverage.update(status="complete" if ids else "empty",
                                authority="authoritative", establishesCompleteness=True,
                                evidence="apiops:" + content_digest, error=None)
                for item in inventory["items"]:
                    if ((item["scope"], item["domain"]) == key and
                            item["id"].lower() in {rid.lower() for rid in ids}):
                        item["authority"] = "authoritative"
    inventory["provenance"].append({"kind": kind, "path": path.name,
                                     "contentDigest": content_digest,
                                     "authority": "advisory", "approved": True})
    return classify_apis(inventory)


def collect_with_exports(source_id, exports=(), runner=run_az):
    result = source_inventory(source_id, runner)
    # Explicitly order fallbacks; caller order must not change authority.
    for kind in ("apiops", "arm"):
        for supplied_kind, path, approved_digest in exports:
            if supplied_kind == kind:
                result = apply_export(result, path, kind, approved_digest)
    return result


def export_digest(path):
    path = safe_path(path)
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    evidence = {}
    for file in files:
        safe_path(file)
        if file.is_file():
            if file.stat().st_size > 32 * 1024 * 1024:
                raise MigrationError("Export file exceeds 32 MiB.")
            evidence[file.relative_to(path).as_posix() if path.is_dir() else file.name] = digest(
                file.read_bytes().hex()
            )
    return digest(evidence)
