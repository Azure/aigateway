"""Read approved APIOps artifacts as source evidence, never as deployment instructions."""

from __future__ import annotations

import re

from core import MigrationError, child_resource_id, clean, digest, read_json, safe_path


INFORMATION = {
    "apiInformation.json": ("apis", "apis"),
    "backendInformation.json": ("backends", "backends"),
    "namedValueInformation.json": ("named values", "namedValues"),
    "productInformation.json": ("products", "products"),
    "policyFragmentInformation.json": ("policy fragments", "policyFragments"),
    "loggerInformation.json": ("loggers", "loggers"),
    "diagnosticInformation.json": ("diagnostics", "diagnostics"),
    "versionSetInformation.json": ("version sets", "apiVersionSets"),
    "groupInformation.json": ("groups", "groups"),
    "subscriptionInformation.json": ("subscriptions", "subscriptions"),
    "tagInformation.json": ("tags", "tags"),
    "gatewayInformation.json": ("gateways", "gateways"),
    "workspaceInformation.json": ("workspaces", "workspaces"),
    "apiReleaseInformation.json": ("releases", "api-releases"),
}
ASSOCIATIONS = {
    "productApiInformation.json": ("products", "apis", "product-apis"),
    "productGroupInformation.json": ("products", "groups", "product-groups"),
    "productTagInformation.json": ("products", "tags", "product-tags"),
    "gatewayApiInformation.json": ("gateways", "apis", "gateway-apis"),
    "tagApiInformation.json": ("tags", "apis", "tag-apis"),
    "tagProductInformation.json": ("tags", "products", "tag-products"),
}
FOLDERS = {"named values": "namedValues", "policy fragments": "policyFragments",
           "version sets": "apiVersionSets"}


def artifact_identity(parts, source):
    if len(parts) % 2:
        raise MigrationError("Unrecognized APIOps resource path.")
    pairs = list(zip(parts[::2], parts[1::2]))
    if any(not re.fullmatch(r"[A-Za-z0-9_.;-]+", name) for _, name in pairs):
        raise MigrationError("Invalid APIOps resource name.")
    return source + "".join("/" + FOLDERS.get(folder, folder) + "/" + name
                            for folder, name in pairs)


def normalize_references(value, source, scope):
    if isinstance(value, dict):
        return {key: normalize_references(child, source, scope) if key not in (
            "apiVersionSetId", "apiId", "scope", "loggerId") else normalize_reference(child, source, scope)
                for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_references(child, source, scope) for child in value]
    return value


def normalize_reference(value, source, scope):
    if not isinstance(value, str):
        return value
    for domain in ("apiVersionSets", "products", "apis", "loggers"):
        prefix = "/" + domain + "/"
        if value.lower().startswith(prefix.lower()):
            identifier = scope + value
            if not child_resource_id(identifier, source):
                raise MigrationError("Unsafe APIOps resource reference.")
            return identifier
    return value


def contract_shape(value, depth=0, context=""):
    if depth > 80:
        raise MigrationError("API contract nesting exceeds the supported depth.")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise MigrationError("API contract keys must be strings.")
        maps = {"paths", "properties", "schemas", "definitions", "responses", "content",
                "headers", "securitySchemes", "securityDefinitions", "requestBodies"}
        structural = {
            "openapi", "swagger", "components", "schema", "items", "allOf", "oneOf", "anyOf",
            "not", "$ref", "type", "format", "required", "nullable", "additionalProperties",
            "readOnly", "writeOnly", "deprecated", "minimum", "maximum", "minLength", "maxLength",
            "minItems", "maxItems", "uniqueItems", "exclusiveMinimum", "exclusiveMaximum",
            "operationId", "parameters", "requestBody", "name", "in", "style", "explode",
            "allowEmptyValue", "collectionFormat", "consumes", "produces",
            "get", "post", "put", "patch", "delete", "head", "options", "trace",
            "scheme", "bearerFormat",
        } | maps
        return {key: contract_shape(child, depth + 1, "" if context in maps else key)
                if context in maps or key in structural else {"redacted": True}
                for key, child in value.items()}
    if isinstance(value, list):
        return [contract_shape(child, depth + 1, context) for child in value]
    if value is not None and not isinstance(value, (str, bool, int, float)):
        raise MigrationError("API contract contains a non-JSON value.")
    return clean(value)


def read_contract(file):
    if file.suffix == ".json":
        value = read_json(file)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise MigrationError("Install the helper requirements to read YAML API contracts.") from exc

        class ContractLoader(yaml.SafeLoader):
            node_depth = 0
            node_count = 0

            def compose_node(self, parent, index):
                if self.check_event(yaml.AliasEvent):
                    raise MigrationError("YAML aliases are not supported in API contracts.")
                self.node_count += 1
                self.node_depth += 1
                if self.node_count > 100000 or self.node_depth > 80:
                    raise MigrationError("API contract is too complex.")
                try:
                    return super().compose_node(parent, index)
                finally:
                    self.node_depth -= 1

            def construct_mapping(self, node, deep=False):
                result = {}
                for key_node, value_node in node.value:
                    key = self.construct_object(key_node, deep=deep)
                    if not isinstance(key, str) or key in result:
                        raise MigrationError("API contract has duplicate or non-string keys.")
                    result[key] = self.construct_object(value_node, deep=deep)
                return result

        try:
            value = yaml.load(file.read_text(encoding="utf-8"), Loader=ContractLoader)
        except (yaml.YAMLError, RecursionError, UnicodeError) as exc:
            raise MigrationError("Malformed YAML API contract.") from exc
    if (not isinstance(value, dict) or not (
            isinstance(value.get("openapi"), str) or value.get("swagger") == "2.0")
            or not isinstance(value.get("paths"), dict)):
        raise MigrationError("Unrecognized OpenAPI contract.")
    structure = contract_shape(value)
    digest(structure)
    return structure


def read_artifacts(path, source):
    path = safe_path(path)
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    found, metadata, fragments, fragment_files = [], None, {}, set()
    for file in files:
        if not file.is_file():
            continue
        parts = file.relative_to(path).parts if path.is_dir() else file.parts[-3:]
        name, parents = parts[-1], parts[:-1]
        if path.is_file() and name in INFORMATION:
            document = read_json(file)
            rid = document.get("id") if isinstance(document, dict) else None
            if not child_resource_id(rid, source):
                raise MigrationError("A standalone APIOps document needs an explicit source identity.")
            parents = tuple(rid[len(source) + 1:].split("/"))
        scope = source
        if len(parents) >= 2 and parents[0] == "workspaces":
            scope = artifact_identity(parents[:2], source)
        resource_parents = parents[2:] if scope != source else parents
        if name == "inventory-metadata.json":
            if parents:
                raise MigrationError("APIOps completeness metadata must be at the artifact root.")
            metadata = read_json(file)
        elif name in INFORMATION:
            folder, domain = INFORMATION[name]
            canonical_folder = FOLDERS.get(folder, folder)
            if (len(resource_parents) < 2 or
                    FOLDERS.get(parents[-2], parents[-2]) != canonical_folder):
                # The workspace information file describes the workspace itself.
                if name != "workspaceInformation.json" or len(parents) != 2:
                    raise MigrationError("Unrecognized APIOps information path.")
            allowed = (len(resource_parents) == 2 or
                       len(resource_parents) == 4 and resource_parents[0] == "apis"
                       and folder in ("diagnostics", "releases") or
                       name == "workspaceInformation.json" and len(parents) == 2)
            if not allowed:
                raise MigrationError("Unrecognized APIOps information scope.")
            if domain == "api-releases" and len(resource_parents) != 4:
                raise MigrationError("API releases must belong to an API.")
            raw = read_json(file)
            if not isinstance(raw, dict) or not isinstance(raw.get("properties"), dict):
                raise MigrationError("Unrecognized APIOps resource document.")
            rid = artifact_identity(parents, source)
            if not isinstance(raw.get("id", rid), str) or raw.get("id", rid).lower() != rid.lower():
                raise MigrationError("APIOps document identity differs from its artifact path.")
            parent = (artifact_identity(parents[:-2], source) if len(resource_parents) == 4
                      or domain == "workspaces" else scope)
            item_domain = "api-diagnostics" if domain == "diagnostics" and parent != scope else domain
            raw = normalize_references({**raw, "id": rid}, source, scope)
            if domain == "policyFragments":
                if (rid, "metadata") in fragment_files:
                    raise MigrationError("Duplicate APIOps fragment metadata.")
                fragment_files.add((rid, "metadata"))
                previous = fragments.get(rid)
                if previous:
                    if "value" in raw["properties"] and raw["properties"]["value"] != previous[2]["properties"]["value"]:
                        raise MigrationError("APIOps fragment metadata and policy body disagree.")
                    raw["properties"] = {**raw["properties"], **previous[2]["properties"]}
                fragments[rid] = (item_domain, parent, raw)
            else:
                found.append((item_domain, parent, raw))
        elif name in ASSOCIATIONS:
            primary, secondary, domain = ASSOCIATIONS[name]
            if len(resource_parents) != 4 or resource_parents[0::2] != (primary, secondary):
                raise MigrationError("Unrecognized APIOps association path.")
            document = read_json(file)
            if not isinstance(document, dict) or not isinstance(document.get("properties", {}), dict):
                raise MigrationError("Malformed APIOps association.")
            parent = artifact_identity(parents[:-2], source)
            target = artifact_identity((*parents[:len(parents) - 4], secondary, parents[-1]), source)
            reference = document.get("properties", {}).get({
                "apis": "apiId", "products": "productId", "groups": "groupId",
                "tags": "tagId"}[secondary])
            if reference is not None and normalize_reference(reference, source, scope) != target:
                raise MigrationError("APIOps link target differs from its artifact path.")
            if primary == "tags":
                parent, target = target, parent
                secondary = "tags"
                domain = "api-tags" if domain == "tag-apis" else "product-tags"
            found.append((domain, parent, {
                "id": parent + "/" + secondary + "/association-" + digest(target.lower())[7:],
                "properties": {"targetResourceId": target, "association": True}}))
        elif name == "policy.xml":
            rid = artifact_identity(parents, source)
            raw = {"id": rid, "properties": {"value": file.read_text(encoding="utf-8")}}
            if len(resource_parents) == 2 and resource_parents[0] in (
                    "policy fragments", "policyFragments"):
                if (rid, "policy") in fragment_files:
                    raise MigrationError("Duplicate APIOps fragment policy.")
                fragment_files.add((rid, "policy"))
                domain, parent, previous = fragments.get(rid, ("policyFragments", scope, raw))
                if previous["properties"].get("value", raw["properties"]["value"]) != raw["properties"]["value"]:
                    raise MigrationError("APIOps fragment metadata and policy body disagree.")
                raw["properties"] = {**previous["properties"], **raw["properties"]}
                fragments[rid] = (domain, parent, raw)
            else:
                domains = {(): "policies", ("apis",): "api-policies",
                           ("products",): "product-policies",
                           ("apis", "operations"): "operation-policies"}
                domain = domains.get(resource_parents[::2])
                if domain is None or (scope != source and not resource_parents):
                    raise MigrationError("Unrecognized APIOps policy scope.")
                found.append((domain, rid, {**raw, "id": rid + "/policies/policy"}))
        elif name in ("specification.json", "specification.yaml", "specification.yml",
                      "specification.graphql", "specification.wsdl", "specification.wadl"):
            if len(resource_parents) != 2 or resource_parents[0] != "apis":
                raise MigrationError("Unrecognized APIOps specification scope.")
            api_id = artifact_identity(parents, source)
            properties = {"format": file.suffix[1:],
                          "contentDigest": digest(file.read_bytes().hex())}
            if file.suffix in (".json", ".yaml", ".yml"):
                properties["structure"] = read_contract(file)
            else:
                properties["analysis"] = "opaque-contract; inspect separately"
            found.append(("api-contracts", api_id, {
                "id": api_id + "/contracts/" + file.suffix[1:], "properties": properties}))
        elif name.endswith("Information.json") or file.suffix == ".xml":
            raise MigrationError("Unsupported APIOps artifact; extend the source reader before use.")
    found.extend(fragments.values())
    if len({raw["id"].lower() for _, _, raw in found}) != len(found):
        raise MigrationError("APIOps artifacts contain duplicate resource identities.")
    return found, metadata
