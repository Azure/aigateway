#!/usr/bin/env python3
"""Run the minimum approved Azure AI Gateway model and MCP smoke checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core import (
    MigrationError, digest, read_json, resource_id, safe_path, validate_schema,
    write_new, run_az,
)


MODEL_ROUTES = ("v1/chat/completions", "v1/responses", "v1/messages")
MCP_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MCP_DEFAULT_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_RESPONSE_BYTES = 1_048_576


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SmokeCheckError(MigrationError):
    pass


def _destination_args(target):
    return [
        "--subscription", target["subscription"],
        "--resource-group", target["resourceGroup"],
        "--gateway-name", target["gateway"],
    ]


def _get_gateway(target):
    gateway = run_az([
        "az", "aigateway", "show",
        "--subscription", target["subscription"],
        "--resource-group", target["resourceGroup"],
        "--name", target["gateway"], "-o", "json",
    ])
    if (not isinstance(gateway, dict) or not isinstance(gateway.get("id"), str)
            or gateway["id"].lower() != target["id"].lower()):
        raise MigrationError("Gateway identity could not be verified.")
    properties = gateway.get("properties")
    gateway_url = properties.get("gatewayUrl") if isinstance(properties, dict) else None
    if isinstance(gateway_url, str):
        parsed = urlsplit(gateway_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise MigrationError("Published gateway runtime URL is malformed.")
        return gateway, parsed.hostname.lower().rstrip(".")
    frontend = properties.get("frontend") if isinstance(properties, dict) else None
    hostname = frontend.get("defaultHostname") if isinstance(frontend, dict) else None
    if not isinstance(hostname, str) or not hostname:
        raise MigrationError("Gateway runtime hostname is not published.")
    return gateway, hostname.lower().rstrip(".")


def _list_resources(target, group):
    return run_az([
        "az", "aigateway", *group.split(),
        *_destination_args(target), "-o", "json",
    ])


def _endpoint_url(endpoint, hostname):
    if not isinstance(endpoint, dict) or not isinstance(endpoint.get("url"), str):
        raise MigrationError("Runtime endpoint URL is missing from resource read-back.")
    parsed = urlsplit(endpoint["url"])
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.hostname.lower().rstrip(".") != hostname):
        raise MigrationError("Runtime endpoint does not match the verified gateway hostname.")
    return endpoint["url"]


def _model_request(alias, endpoints, hostname, approved_api):
    properties = alias.get("properties")
    if not isinstance(properties, dict):
        raise MigrationError("Alias configuration is malformed.")
    if not isinstance(endpoints, list):
        raise MigrationError("Alias runtime endpoints are malformed.")
    for endpoint in endpoints:
        api = endpoint.get("api") if isinstance(endpoint, dict) else None
        if api == approved_api:
            route = next((known for known in MODEL_ROUTES if api.rstrip("/").lower().endswith(known)), None)
            if route:
                url = _endpoint_url(endpoint, hostname)
                break
    else:
        raise MigrationError("Approved inference API is not advertised by the alias.")
    name = properties.get("aliasName") or alias.get("name")
    if not isinstance(name, str) or not name:
        raise MigrationError("Callable model alias name is missing.")
    headers = {"Content-Type": "application/json"}
    if route == "v1/chat/completions":
        body = {"model": name, "messages": [{"role": "user", "content": "Reply OK."}],
                "max_completion_tokens": 1}
    elif route == "v1/responses":
        body = {"model": name, "input": "Reply OK.", "max_output_tokens": 1}
    elif route == "v1/messages":
        headers["anthropic-version"] = "2023-06-01"
        body = {"model": name, "max_tokens": 1,
                "messages": [{"role": "user", "content": "Reply OK."}]}
    else:
        raise MigrationError("Image-generation and unknown model output routes are not smoke-testable.")
    return url, headers, body, route


def _http(method, url, headers, body=None, timeout=30):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = Request(url, data=data, headers=headers, method=method)
    opener = build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SmokeCheckError("Runtime response exceeded the smoke-test size limit.")
            return response.status, dict(response.headers.items()), raw
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), b""
    except (URLError, TimeoutError, OSError) as exc:
        raise MigrationError("Runtime request failed before a conclusive response.") from exc


def _header(headers, name):
    return next((value for key, value in headers.items() if key.lower() == name.lower()), "")


def _json_or_sse(headers, raw):
    try:
        text = raw.decode("utf-8", errors="strict")
        if "text/event-stream" not in _header(headers, "Content-Type").lower():
            return json.loads(text)
        data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        for item in reversed(data):
            if item and item != "[DONE]":
                return json.loads(item)
    except (UnicodeError, ValueError) as exc:
        raise SmokeCheckError("Runtime returned a malformed JSON response.") from exc
    raise SmokeCheckError("MCP event stream contained no JSON-RPC result.")


def _mcp_supported_versions(properties):
    if "versions" not in properties:
        return MCP_DEFAULT_VERSIONS
    versions = properties["versions"]
    return tuple(version for version in MCP_VERSIONS
                 if isinstance(versions, list) and version in versions)


def _validate_model_response(response, route):
    if not isinstance(response, dict) or response.get("error"):
        raise SmokeCheckError("Inference returned a malformed or error response.")
    expected = {
        "v1/chat/completions": "choices",
        "v1/responses": "output",
        "v1/messages": "content",
    }[route]
    if not isinstance(response.get(expected), list):
        raise SmokeCheckError("Inference response did not contain the expected result.")


def _mcp_request(url, token, body, session_id=None, version=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if version:
        headers["MCP-Protocol-Version"] = version
    status, response_headers, raw = _http("POST", url, headers, body)
    parsed = None
    if raw:
        parsed = _json_or_sse(response_headers, raw)
    return status, response_headers, parsed


def _mcp_check(server, hostname, token, approved_version):
    properties = server.get("properties")
    if not isinstance(properties, dict):
        raise MigrationError("Tool server configuration is malformed.")
    if approved_version not in _mcp_supported_versions(properties):
        raise MigrationError("Approved MCP version is not supported by the tool server.")
    endpoints = properties.get("gatewayEndpoints")
    endpoints = [entry for entry in endpoints or [] if isinstance(entry, dict)
                 and entry.get("api") == "mcp"]
    if len(endpoints) != 1:
        raise MigrationError("Tool server must publish exactly one MCP runtime endpoint.")
    url = _endpoint_url(endpoints[0], hostname)

    status, headers, response = _mcp_request(
        url, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": approved_version,
                                "capabilities": {}, "clientInfo": {"name": "aigateway-migration-smoke",
                                                                   "version": "1"}}})
    if (not 200 <= status < 300 or not isinstance(response, dict)
            or response.get("id") != 1 or response.get("error")):
        raise SmokeCheckError(f"MCP initialize failed with HTTP {status}.")
    result = response.get("result")
    if not isinstance(result, dict) or result.get("protocolVersion") != approved_version:
        raise SmokeCheckError("MCP initialize did not negotiate the requested version.")
    session_id = _header(headers, "Mcp-Session-Id") or None

    status, _, notification_response = _mcp_request(
        url, token, {"jsonrpc": "2.0", "method": "notifications/initialized"},
        session_id, approved_version)
    if status not in (200, 202, 204):
        raise SmokeCheckError(f"MCP initialized notification failed with HTTP {status}.")
    if notification_response is not None and (
            not isinstance(notification_response, dict) or notification_response.get("error")):
        raise SmokeCheckError("MCP initialized notification returned an error.")

    status, _, response = _mcp_request(
        url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                     "params": {}}, session_id, approved_version)
    if (not 200 <= status < 300 or not isinstance(response, dict)
            or response.get("id") != 2 or response.get("error")):
        raise SmokeCheckError(f"MCP tools/list failed with HTTP {status}.")
    result = response.get("result")
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list) or not all(isinstance(t, dict) and isinstance(t.get("name"), str)
                                               for t in tools):
        raise SmokeCheckError("MCP tools/list returned a malformed tool collection.")
    return {"protocolVersion": approved_version, "toolCount": len(tools),
            "tools": [tool["name"] for tool in tools],
            "partial": bool(result.get("nextCursor"))}


def _approved_checks(inventory):
    checks = []
    for asset in inventory["assets"]:
        if asset["kind"] not in ("alias", "mcp") or asset["action"] == "manual":
            continue
        tests = asset["smokeTests"]
        if len(tests) != 1 or not tests[0]["required"]:
            raise MigrationError(f"{asset['id']} must have exactly one required minimum smoke test.")
        smoke = tests[0]
        request = smoke["request"]
        mode = "minimal-inference" if asset["kind"] == "alias" else "mcp-initialize-tools-list"
        expected_keys = {"mode", "api"} if asset["kind"] == "alias" else {"mode", "protocolVersion"}
        if (set(request) != expected_keys or request.get("mode") != mode
                or smoke["credentialInputs"]):
            raise MigrationError(f"{asset['id']} must declare the standard {mode} check without key inputs.")
        if asset["kind"] == "alias" and request["api"] not in MODEL_ROUTES:
            raise MigrationError(
                f"{asset['id']} must name a supported text inference API; image-generation routes are not supported."
            )
        if asset["kind"] == "mcp" and request["protocolVersion"] not in MCP_VERSIONS:
            raise MigrationError(f"{asset['id']} must name one supported session-based MCP version.")
        maximum = 1 if asset["kind"] == "alias" else 3
        if smoke["bounds"]["maxRequests"] != maximum:
            raise MigrationError(f"{asset['id']} smoke-test request bound must be {maximum}.")
        if asset["kind"] == "alias" and smoke["bounds"].get("maxTokens") not in (None, 1):
            raise MigrationError(f"{asset['id']} must limit text inference output to one token.")
        checks.append(asset)
    return checks


def _validate_confirmation(results_path, approved_digest):
    results = read_json(results_path)
    validate_schema(results, "migration-results")
    if results["inventoryDigest"] != approved_digest:
        raise MigrationError("Confirmation receipt does not match the approved inventory digest.")
    if not results["confirmation"]["evidence"].strip():
        raise MigrationError("Confirmation receipt has no approval evidence.")
    return results


def _pending_checks(assets, receipt_by_id):
    if not assets:
        raise MigrationError("Inventory has no approved alias or MCP smoke tests.")
    if (len({asset["id"] for asset in assets}) != len(assets)
            or len({asset["targetId"].lower() for asset in assets}) != len(assets)):
        raise MigrationError("Approved smoke asset IDs or targets are duplicated.")
    pending = []
    prior_checks = []
    for asset in assets:
        smoke_id = f"smoke-{asset['smokeTests'][0]['id']}"
        previous = receipt_by_id.get(asset["id"])
        checks = [check for check in previous["checks"] if check["id"] == smoke_id] if previous else []
        if len(checks) > 1:
            raise MigrationError(f"{asset['id']} has duplicate smoke receipts.")
        if checks:
            prior_checks.append(checks[0])
        else:
            pending.append(asset)
    if not pending:
        raise MigrationError("All approved assets already have smoke receipts; inspect them before any new request.")
    return pending, all(check["status"] == "passed" for check in prior_checks)


def _replace_results(path, results):
    path = safe_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".smoke-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(results, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def run_smoke_tests(inventory_path, confirmation_path, approved_digest, output_path):
    inventory = read_json(inventory_path)
    validate_schema(inventory, "migration-inventory")
    if digest(inventory) != approved_digest:
        raise MigrationError("Approved inventory digest does not match.")
    receipts = _validate_confirmation(confirmation_path, approved_digest)
    assets = _approved_checks(inventory)
    if len({asset["assetId"] for asset in receipts["assets"]}) != len(receipts["assets"]):
        raise MigrationError("Confirmation receipt contains duplicate asset IDs.")
    output_path = safe_path(output_path)
    if output_path.exists():
        raise MigrationError("Smoke results output must be a new file.")
    receipt_by_id = {asset["assetId"]: asset for asset in receipts["assets"]}
    assets, all_passed = _pending_checks(assets, receipt_by_id)
    target = resource_id(inventory["destinationId"], "aigateways")
    target["id"] = inventory["destinationId"]
    _, hostname = _get_gateway(target)
    aliases = _list_resources(target, "model-alias list")
    servers = _list_resources(target, "mcp list")
    if (not isinstance(aliases, list) or not isinstance(servers, list)
            or not all(isinstance(item, dict) and isinstance(item.get("id"), str)
                       for item in aliases + servers)):
        raise MigrationError("Gateway callable resource read-back is malformed.")
    alias_by_id = {item["id"].lower(): item for item in aliases}
    server_by_id = {item["id"].lower(): item for item in servers}
    if len(alias_by_id) != len(aliases) or len(server_by_id) != len(servers):
        raise MigrationError("Gateway callable resource identities are malformed or duplicated.")
    for asset in assets:
        child_type = "aliases" if asset["kind"] == "alias" else "toolServers"
        prefix = f"{target['id']}/workspaces/default/{child_type}/"
        if not asset["targetId"].lower().startswith(prefix.lower()):
            raise MigrationError(f"{asset['id']} target is outside the selected gateway workspace.")

    # Use Entra ID for inbound calls so identity-based gateway policies are honored.
    token_result = run_az([
        "az", "account", "get-access-token", "--subscription", target["subscription"],
        "--resource", "https://ai.gateway.azure.com", "-o", "json",
    ])
    token = token_result.get("accessToken") if isinstance(token_result, dict) else None
    if not isinstance(token, str) or not token:
        raise MigrationError("Azure CLI did not return an Entra runtime token.")

    write_new(output_path, receipts)
    for asset in assets:
        resource = (alias_by_id if asset["kind"] == "alias" else server_by_id).get(
            asset["targetId"].lower())
        smoke_id = f"smoke-{asset['smokeTests'][0]['id']}"
        receipt = receipt_by_id.get(asset["id"])
        if receipt is None:
            receipt = {"assetId": asset["id"], "provisioning": "unknown",
                       "checks": [], "notes": ""}
            receipts["assets"].append(receipt)
            receipt_by_id[asset["id"]] = receipt
        check = {"id": smoke_id, "status": "blocked",
                 "evidence": "Smoke request may be in progress; inspect this receipt before retrying."}
        receipt["checks"].append(check)
        validate_schema(receipts, "migration-results")
        _replace_results(output_path, receipts)

        result = {"assetId": asset["id"], "targetId": asset["targetId"],
                  "kind": asset["kind"], "status": "blocked"}
        try:
            if resource is None:
                raise MigrationError("Registered resource was not found in gateway read-back.")
            started = time.monotonic()
            if asset["kind"] == "alias":
                properties = resource.get("properties")
                endpoints = properties.get("gatewayEndpoints") if isinstance(properties, dict) else None
                url, headers, body, route = _model_request(
                    resource, endpoints, hostname, asset["smokeTests"][0]["request"]["api"])
                headers["Authorization"] = f"Bearer {token}"
                status, response_headers, raw = _http("POST", url, headers, body)
                if not 200 <= status < 300:
                    raise SmokeCheckError(f"Inference returned HTTP {status}.")
                if not raw:
                    raise SmokeCheckError("Inference returned an empty response.")
                _validate_model_response(_json_or_sse(response_headers, raw), route)
                result.update(status="passed", route=route, httpStatus=status)
            else:
                details = _mcp_check(
                    resource, hostname, token,
                    asset["smokeTests"][0]["request"]["protocolVersion"])
                result.update(status="passed", **details)
            result["elapsedMs"] = round((time.monotonic() - started) * 1000)
        except MigrationError as exc:
            result["evidence"] = str(exc)
            if isinstance(exc, SmokeCheckError):
                result["status"] = "failed"
        evidence = result.get("evidence")
        if evidence is None:
            evidence = json.dumps(
                {key: value for key, value in result.items()
                 if key not in ("assetId", "targetId", "kind", "status")},
                sort_keys=True, separators=(",", ":"))
        check.update(status=result["status"], evidence=evidence)
        validate_schema(receipts, "migration-results")
        _replace_results(output_path, receipts)
        all_passed = all_passed and result["status"] == "passed"
    return all_passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-file", required=True)
    parser.add_argument("--confirmation-file", required=True)
    parser.add_argument("--approved-digest", required=True)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args(argv)
    try:
        return 0 if run_smoke_tests(
            args.inventory_file, args.confirmation_file, args.approved_digest, args.output_file
        ) else 1
    except (MigrationError, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(str(exc) if isinstance(exc, MigrationError) else
              "Smoke-test preparation failed; inspect the inventory and protected environment.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
