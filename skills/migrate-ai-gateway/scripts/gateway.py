"""Read-only inspection of selected CLI commands and destination configuration."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess

from core import (
    MigrationError, child_resource_id, clean, now,
    resource_id, run_az, safe_path,
)
from cli_release import latest_release, require_current_cli, verify_installed_release


def inspect_cli(commands):
    """Verify release provenance once and inspect only the selected native commands."""
    if not commands or len(set(commands)) != len(commands) or any(
            not isinstance(command, str) or not re.fullmatch(r"[a-z]+(?:[ -][a-z]+)*", command)
            for command in commands):
        raise MigrationError("Name unique selected aigateway commands to inspect.")
    version = run_az(["az", "aigateway", "version", "--output", "json"])
    if not isinstance(version, dict) or version.get("extensionName") != "aigateway":
        raise MigrationError("Unexpected CLI extension producer.")
    release = latest_release()
    require_current_cli(version.get("extensionVersion"), release)
    installation = run_az(["az", "extension", "show", "--name", "aigateway",
                           "--query", "path", "-o", "json"])
    if not isinstance(installation, str):
        raise MigrationError("CLI extension installation path is unavailable.")
    package = safe_path(Path(installation) / "azext_aigateway")
    released_digest = verify_installed_release(package, release)
    routed = set(gateway_commands(package))
    shapes = {}
    for command in commands:
        if command not in routed:
            raise MigrationError("A selected command has no established aigateways dispatch; review its current official implementation.")
        try:
            result = subprocess.run(["az", "aigateway", *command.split(), "--help"],
                                    capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MigrationError("Unable to inspect selected CLI help.") from exc
        if result.returncode:
            raise MigrationError("Selected CLI help failed; do not infer command support.")
        shapes[command] = exposed_options(result.stdout)
    return {"schemaVersion": "1.0", "extension": version, "release": release,
            "releasedWheelSha256": released_digest, "commands": shapes,
            "resourceCommands": {"aigateways": sorted(set(commands))}, "capturedAt": now()}


def exposed_options(text):
    return sorted({option for line in text.splitlines()
                   if re.match(r"^    --", line)
                   for option in re.findall(r"--[a-z][a-z-]+", line.split(":")[0])})


def gateway_commands(package):
    """Inspect the reviewed new-RP dispatch allowlist without importing CLI code."""
    path = safe_path(package / "_rp.py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        groups = {}
        names = {"SUPPORTED_NEW_COMMANDS", "CHILD_READS", "CHILD_WRITES"}
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names):
                value = ast.literal_eval(node.value)
                if not isinstance(value, set) or not all(
                        isinstance(command, str) and command.startswith("aigateway ")
                        for command in value):
                    raise ValueError
                groups[node.targets[0].id] = value
            if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == "SUPPORTED_NEW_COMMANDS"):
                call = node.value
                if (call.func.attr != "update" or len(call.args) != 1 or call.keywords
                        or not isinstance(call.args[0], ast.Name) or call.args[0].id not in groups):
                    raise ValueError
                groups["SUPPORTED_NEW_COMMANDS"].update(groups[call.args[0].id])
        return sorted(command.removeprefix("aigateway ")
                      for command in groups["SUPPORTED_NEW_COMMANDS"])
    except (OSError, UnicodeError, SyntaxError, ValueError, TypeError, KeyError) as exc:
        raise MigrationError(
            "Cannot establish the installed CLI's aigateways routing contract; "
            "review the selected command's official implementation before destination execution."
        ) from exc


def destination_inventory(destination_id, runner=run_az, groups=None):
    target = resource_id(destination_id, "aigateways")
    selectors = ["--subscription", target["subscription"],
                 "--resource-group", target["resourceGroup"]]
    result = {"schemaVersion": "1.0", "destinationId": destination_id,
              "capturedAt": now(), "collections": {}, "errors": []}
    try:
        gateway = runner(["az", "aigateway", "show", *selectors,
                          "--name", target["gateway"], "-o", "json"])
    except MigrationError as exc:
        if exc.code != "ResourceNotFound":
            raise
        group_id = (f"/subscriptions/{target['subscription']}/resourceGroups/"
                    f"{target['resourceGroup']}")
        group = runner(["az", "group", "show", "--subscription", target["subscription"],
                        "--name", target["resourceGroup"], "-o", "json"])
        if not isinstance(group, dict) or str(group.get("id", "")).lower() != group_id.lower():
            raise MigrationError("Destination resource-group identity could not be established.")
        result["exists"] = False
        result["collections"]["gateway"] = []
        return result
    result["exists"] = True
    if not isinstance(gateway, dict) or str(gateway.get("id", "")).lower() != destination_id.lower():
        raise MigrationError("Destination identity mismatch.")
    result["collections"]["gateway"] = [clean(gateway)]
    for group in ("model-provider", "model", "model-alias", "mcp", "api-key",
                  "telemetry-exporter", "private-endpoint-connection"):
        if groups is not None and group not in groups:
            continue
        try:
            command = ["network", group, "list"] if group == "private-endpoint-connection" else [group, "list"]
            values = runner(["az", "aigateway", *command, *selectors,
                             "--gateway-name", target["gateway"], "-o", "json"])
            if isinstance(values, dict):
                if incomplete_page(values):
                    raise MigrationError("Incomplete destination collection.")
                values = values.get("value")
            if not isinstance(values, list):
                raise MigrationError("Unexpected destination collection shape.")
            if not all(isinstance(item, dict) and child_resource_id(item.get("id"), destination_id)
                       for item in values):
                raise MigrationError("Destination collection contains malformed or out-of-scope resources.")
            if group in ("telemetry-exporter", "private-endpoint-connection"):
                suffix = "/workspaces/default/telemetryExporters/" if group == "telemetry-exporter" else "/privateEndpointConnections/"
                if (any(not re.fullmatch(re.escape(destination_id + suffix) + r"[A-Za-z0-9_.-]+",
                                         item["id"], re.I) for item in values)
                        or len({item["id"].lower() for item in values}) != len(values)):
                    raise MigrationError("Malformed or duplicate child-resource identities.")
            if group == "model-alias" and any(
                    not isinstance(item.get("properties"), dict)
                    or not isinstance(item["properties"].get("backendModels"), list)
                    or not all(isinstance(b, dict) and isinstance(b.get("resourceId"), str)
                               and child_resource_id(b["resourceId"], destination_id)
                               for b in item["properties"]["backendModels"])
                    for item in values):
                raise MigrationError("Alias references are incomplete or escape the selected gateway.")
            result["collections"][group] = clean(values)
        except MigrationError:
            result["errors"].append({"domain": group, "code": "inconclusive"})
    identity = gateway.get("identity")
    if identity is not None and not isinstance(identity, dict):
        result["errors"].append({"domain": "identity", "code": "malformed"})
    else:
        result["collections"]["identity"] = clean(identity or {})
    if groups is None or "network" in groups:
        try:
            network = runner(["az", "aigateway", "network", "show", *selectors,
                              "--name", target["gateway"], "-o", "json"])
            if not isinstance(network, dict):
                raise MigrationError("Malformed network snapshot.")
            result["collections"]["network"] = clean(network)
        except MigrationError:
            result["errors"].append({"domain": "network", "code": "inconclusive"})
    if groups is None or "policy" in groups:
        return _collect_policies(result, target, selectors, runner)
    return result


def _collect_policies(result, target, selectors, runner):
    try:
        policies = runner(["az", "aigateway", "policy", "list", *selectors,
                           "--gateway-name", target["gateway"], "-o", "json"])
        result["collections"]["policy"] = policy_resource(policies, result["destinationId"])
    except MigrationError:
        result["errors"].append({"domain": "policy", "code": "inconclusive"})
    return result


def policy_resource(policies, root):
    if not isinstance(policies, list) or not all(
            isinstance(policy, dict) and isinstance(policy.get("type"), str) for policy in policies):
        raise MigrationError("Malformed default-workspace policy array.")
    return {"id": root + "/workspaces/default", "properties": {"policies": clean(policies)}}


def incomplete_page(value):
    return any(child for key, child in value.items() if key.replace("_", "").replace(
        ".", "").replace("@", "").lower() in ("nextlink", "nexttoken", "skiptoken", "odatanextlink"))
