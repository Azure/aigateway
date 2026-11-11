"""Destination capability inspection and discovery, independent of APIM inventory."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess

from core import (
    ROOT, TOOL_VERSION, MigrationError, child_resource_id, clean, digest, now,
    read_json, resource_id, run_az, safe_path,
)
from cli_release import latest_release, require_current_cli, verify_installed_release


def catalog():
    return read_json(ROOT / "capabilities.json")


def exposed_options(text):
    return sorted({option for line in text.splitlines()
                   if re.match(r"^    --", line)
                   for option in re.findall(r"--[a-z][a-z-]+", line.split(":")[0])})


def command_selectors(command):
    common = {"--subscription", "--resource-group"}
    if command[0] == "policy":
        return common | {"--gateway-name"}
    if command[:2] == ["network", "private-endpoint-connection"]:
        return common | {"--gateway-name", "--name"}
    if command[0] in ("create", "show", "identity", "network"):
        return common | {"--name"}
    return common | {"--gateway-name", "--name"} | (
        {"--provider-name"} if command[0] == "model" else set())


def resource_kind(command):
    if command[:2] == ["network", "private-endpoint-connection"]:
        return "private-endpoint-connection"
    return "gateway" if command[0] in ("create", "show") else command[0]


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
            "review its adapter before destination execution."
        ) from exc


def inspect_cli():
    version = run_az(["az", "aigateway", "version", "--output", "json"])
    if not isinstance(version, dict) or version.get("extensionName") != "aigateway":
        raise MigrationError("Unexpected CLI extension producer.")
    release = latest_release()
    require_current_cli(version.get("extensionVersion"), release)
    evidence = catalog()["cliEvidence"]
    if (release["version"] != evidence["documentedVersion"]
            or release["wheelSha256"] != evidence["wheelSha256"]):
        raise MigrationError("The latest CLI needs a reviewed capability profile before destination operations; do not fall back to an older CLI.")
    installation = run_az(["az", "extension", "show", "--name", "aigateway",
                           "--query", "path", "-o", "json"])
    if not isinstance(installation, str):
        raise MigrationError("CLI extension installation path is unavailable.")
    package = safe_path(Path(installation) / "azext_aigateway")
    released_digest = verify_installed_release(package, release)
    files = sorted(package.rglob("*.py"))
    if not files:
        raise MigrationError("Cannot fingerprint installed CLI code; adapter compatibility is unknown.")
    code_digest = digest({file.relative_to(package).as_posix(): digest(
        safe_path(file).read_bytes().hex()) for file in files})
    helper_digest = digest({
        file.relative_to(ROOT).as_posix(): digest(file.read_bytes().hex())
        for folder in ("scripts", "schemas") for file in sorted((ROOT / folder).glob("*"))
        if file.is_file() and file.suffix in (".py", ".json")
    })
    commands = {tuple(cap["command"]) for cap in catalog()["capabilities"]}
    commands |= {tuple(cap["read"]) for cap in catalog()["capabilities"]}
    commands |= {(group, "list") for group in (
        "model", "model-provider", "model-alias", "mcp", "api-key", "policy", "telemetry-exporter")}
    commands.add(("network", "private-endpoint-connection", "list"))
    commands |= {("list",), ("model-provider", "sync")}
    shapes = {}
    for command in sorted(commands):
        try:
            result = subprocess.run(["az", "aigateway", *command, "--help"],
                                    capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MigrationError("Unable to inspect local CLI help.") from exc
        options = exposed_options(result.stdout)
        shapes[" ".join(command)] = options if result.returncode == 0 else None
    identity = {"extension": version, "commands": shapes,
                "release": release, "releasedWheelSha256": released_digest,
                "resourceCommands": {"aigateways": gateway_commands(package)},
                "extensionCodeDigest": code_digest,
                "helperDigest": helper_digest}
    return {"schemaVersion": "1.0", "producer": "skill-local", "toolVersion": TOOL_VERSION,
            **identity, "fingerprint": digest(identity)}


def capabilities(cli):
    cat = catalog()
    entries = []
    routed = cli.get("resourceCommands", {}).get("aigateways", [])
    for cap in cat["capabilities"]:
        options = cli["commands"].get(" ".join(cap["command"]))
        reads = cli["commands"].get(" ".join(cap["read"]))
        selectors = command_selectors(cap["command"])
        required_options = {"--" + name for name in cap["options"]} | selectors
        available = (options is not None and reads is not None
                     and required_options.issubset(options)
                     and command_selectors(cap["read"]).issubset(reads)
                     and " ".join(cap["command"]) in routed and " ".join(cap["read"]) in routed
                     and cli["commands"].get("list") is not None
                     and cli["extension"].get("apiVersion") == cat["apiVersion"])
        entries.append({**cap, "support": "conditional" if available else "unavailable"})
    result = {"schemaVersion": "1.0", "producer": "skill-local",
              "catalogVersion": cat["catalogVersion"], "catalogDigest": digest(cat),
              "cli": cli, "capabilities": entries, "unsupported": cat["unsupported"]}
    result["contractDigest"] = digest(result)
    return result


def destination_inventory(destination_id, runner=run_az):
    target = resource_id(destination_id, "aigateways")
    selectors = ["--subscription", target["subscription"],
                 "--resource-group", target["resourceGroup"]]
    result = {"schemaVersion": "1.0", "destinationId": destination_id,
              "capturedAt": now(), "collections": {}, "errors": []}
    gateways = runner(["az", "aigateway", "list", *selectors, "-o", "json"])
    if isinstance(gateways, dict):
        if incomplete_page(gateways):
            raise MigrationError("Incomplete destination enumeration cannot establish absence.")
        gateways = gateways.get("value")
    if not isinstance(gateways, list):
        raise MigrationError("Unexpected destination list shape.")
    for item in gateways:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise MigrationError("Malformed gateway enumeration cannot establish absence.")
        observed = resource_id(item["id"], None)
        if any(observed[key].lower() != target[key].lower()
               for key in ("subscription", "resourceGroup")):
            raise MigrationError("Gateway enumeration escaped its selected scope.")
    matches = [item for item in gateways
               if str(item.get("id", "")).lower() == destination_id.lower()]
    if len(matches) > 1:
        raise MigrationError("Duplicate gateway identities make destination evidence ambiguous.")
    result["exists"] = bool(matches)
    if not matches:
        result["collections"]["gateway"] = []
        return result
    gateway = runner(["az", "aigateway", "show", *selectors, "--name", target["gateway"],
                      "-o", "json"])
    if not isinstance(gateway, dict) or str(gateway.get("id", "")).lower() != destination_id.lower():
        raise MigrationError("Destination identity mismatch.")
    result["collections"]["gateway"] = [clean(gateway)]
    for group in ("model-provider", "model", "model-alias", "mcp", "api-key",
                  "telemetry-exporter", "private-endpoint-connection"):
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
    try:
        network = runner(["az", "aigateway", "network", "show", *selectors,
                          "--name", target["gateway"], "-o", "json"])
        if not isinstance(network, dict):
            raise MigrationError("Malformed network snapshot.")
        result["collections"]["network"] = clean(network)
    except MigrationError:
        result["errors"].append({"domain": "network", "code": "inconclusive"})
    try:
        policies = runner(["az", "aigateway", "policy", "list", *selectors,
                           "--gateway-name", target["gateway"], "-o", "json"])
        result["collections"]["policy"] = policy_resource(policies, destination_id)
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
