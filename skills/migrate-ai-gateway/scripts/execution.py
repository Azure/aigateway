"""Approved reconciliation; writes use only reviewed aigateway argv templates."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from core import (
    MigrationError, clean, digest, now, resource_id, run_az, semantic, subset,
    validate_schema,
)
from gateway import capabilities, destination_inventory, inspect_cli
from inventory import collect_with_exports
from planning import initial_mapping, runtime_references, validate_plan
from model_inventory import collect_models, validate_catalog
from native_sync import refresh_previews


def initialize(source, destination, contract, model_catalog=None):
    validate_schema(source, "source-inventory")
    validate_schema(contract, "capability-contract")
    validate_schema(destination, "destination-inventory")
    model_catalog = validate_catalog(model_catalog or {"schemaVersion": "1.0", "providers": []})
    context = {"schemaVersion": "4.0", "generationId": str(uuid.uuid4()),
               "sourceId": source["sourceId"], "destinationId": destination["destinationId"],
               "phase": "mapping", "completionStatus": "blocked",
               "manifestDigest": "sha256:" + "0" * 64}
    resource_id(context["destinationId"], "aigateways")
    if context["sourceId"].lower() == context["destinationId"].lower():
        raise MigrationError("Source and destination must be distinct services.")
    bundle = {"context.json": context, "source-inventory.json": source, "model-catalog.json": model_catalog,
              "destination-inventory.json": destination, "capability-contract.json": contract,
              "mapping.json": initial_mapping(source), "todos.json": {"schemaVersion": "4.0", "items": []},
              "migration-plan.md": "# Migration plan\n\nMapping input is required.\n",
              "migration-report.md": "# Migration report\n\nBlocked: mapping input is required.\n"}
    bundle["plan-validation.json"] = validate_plan(bundle)
    return bundle


def validated(bundle):
    result = validate_plan(bundle)
    saved = bundle["plan-validation.json"]
    if result["status"] != "valid" or saved != result:
        raise MigrationError("Plan validation is invalid or stale; validate the current inputs.")
    return result


def select_todo(bundle, tid):
    matches = [item for item in bundle["todos.json"]["items"] if item["id"] == tid]
    if len(matches) != 1:
        raise MigrationError("Expected one known TODO ID.")
    return matches[0]


def invalidate(bundle, reason):
    for todo in bundle["todos.json"]["items"]:
        todo["approval"]["status"] = "invalidated"
    for mapping in bundle["mapping.json"]["items"]:
        for result in mapping.get("behaviorResults", {}).values():
            result.update(status="pending", evidenceDigest=None, recordedAt=None)
    bundle["context.json"].update(phase="blocked", completionStatus="blocked")
    bundle["migration-report.md"] = f"# Migration report\n\nBlocked: {reason}\n"


def refresh(bundle, runner=run_az, inspector=inspect_cli, exports=()):
    source = collect_with_exports(bundle["context.json"]["sourceId"], exports, runner)
    old_source = bundle["source-inventory.json"]
    contract = capabilities(inspector())
    destination = destination_inventory(bundle["context.json"]["destinationId"], runner)
    if digest(semantic(source)) != digest(semantic(old_source)):
        raise MigrationError("Source content, coverage, or behavior drift; collect a new plan.")
    if contract != bundle["capability-contract.json"]:
        raise MigrationError("CLI or capability contract drift; collect a new plan.")
    selection = bundle["mapping.json"].get("selection")
    selected_providers = {p["id"] for p in selection["providers"]} if selection is not None else None
    for provider in bundle["model-catalog.json"]["providers"]:
        if selected_providers is not None and provider["id"] not in selected_providers:
            continue
        if provider["provenance"] == "operator-manifest":
            continue
        fresh = collect_models(
            provider["id"], provider["kind"], provider["endpoint"], provider["accountId"],
            provider["credentialRef"], provider.get("credentialHeader", "Authorization"),
            approved=True, runner=runner)["providers"][0]
        if digest(semantic(fresh)) != digest(semantic(provider)):
            raise MigrationError("Upstream model catalog changed or is unavailable; reselect and re-plan.")
    refresh_previews(bundle, destination, runner, contract["cli"])
    return destination


def capability(bundle, todo):
    return next(cap for cap in bundle["capability-contract.json"]["capabilities"]
                if cap["id"] == todo["capabilityId"])


def selectors(todo, cap):
    target = todo["target"]
    args = ["--subscription", target["subscription"], "--resource-group", target["resourceGroup"]]
    if cap["command"][0] in ("create", "show", "identity", "network"):
        return args + ["--name", target["gateway"]]
    args += ["--gateway-name", target["gateway"], "--name", target["name"]]
    if cap["command"][0] == "model":
        args += ["--provider-name", target["provider"]]
    return args


def read_current(bundle, todo, snapshot, runner):
    cap = capability(bundle, todo)
    if not snapshot["exists"]:
        return None
    group = cap["command"][0]
    if any(error["domain"] == group for error in snapshot["errors"]):
        raise MigrationError("Target collection is incomplete; preconditions are unknown.")
    root = bundle["context.json"]["destinationId"]
    expected_id = root
    if group == "model-provider":
        expected_id += "/workspaces/default/modelProviders/" + todo["target"]["name"]
    elif group == "model":
        expected_id += ("/workspaces/default/modelProviders/" + todo["target"]["provider"]
                        + "/models/" + todo["target"]["name"])
    elif group == "mcp":
        expected_id += "/workspaces/default/toolServers/" + todo["target"]["name"]
    elif group == "model-alias":
        expected_id += "/workspaces/default/aliases/" + todo["target"]["name"]
    elif group == "api-key":
        expected_id += "/apiKeys/" + todo["target"]["name"]
    if group not in ("create", "show", "identity", "network"):
        matches = [item for item in snapshot["collections"].get(group, [])
                   if str(item.get("id", "")).lower() == expected_id.lower()]
        if not matches:
            return None
    result = runner(["az", "aigateway", *cap["read"], *selectors(todo, cap), "-o", "json"])
    if not isinstance(result, dict):
        raise MigrationError("Resource read-back must be an object.")
    if group == "identity":
        if not isinstance(result, dict) or str(result.get("id", "")).lower() != expected_id.lower():
            raise MigrationError("Identity parent read-back has the wrong resource identity.")
        identity = result.get("identity")
        if identity is not None and not isinstance(identity, dict):
            raise MigrationError("Malformed identity read-back.")
        return clean(identity or {})
    if group not in ("identity", "network"):
        rid = str(result.get("id", ""))
        if rid.lower() != expected_id.lower():
            raise MigrationError("Read-back resource is not the exact expected destination resource.")
    return clean(result)


def verify_final_resources(bundle, snapshot, runner=run_az):
    for todo in bundle["todos.json"]["items"]:
        if todo["status"] not in ("resource-verified", "behavior-verified"):
            continue
        current = read_current(bundle, todo, snapshot, runner)
        if current is None or not subset(todo["desiredState"], current):
            todo["status"] = "blocked"
            for behavior in todo["behaviorResults"].values():
                behavior.update(status="pending", evidenceDigest=None, recordedAt=None)
            raise MigrationError("Final resource state no longer meets a verified TODO; re-plan and verify.")


def resolve_runtime(value):
    if isinstance(value, dict) and set(value) == {"$runtimeSecret"}:
        secret = os.environ.get(value["$runtimeSecret"])
        if not secret:
            raise MigrationError("Required runtime secret environment variable is not set.")
        return secret
    if isinstance(value, dict):
        return {key: resolve_runtime(child) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_runtime(child) for child in value]
    return value


def mutation_argv(bundle, todo, directory):
    cap = capability(bundle, todo)
    argv = ["az", "aigateway", *cap["command"], *selectors(todo, cap)]
    for key, value in sorted(todo["arguments"].items()):
        if isinstance(value, (dict, list)):
            path = Path(directory) / (key + ".json")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(resolve_runtime(value), output)
            argv.extend(["--" + key, "@" + str(path)])
        elif isinstance(value, (str, bool, int)):
            argv.extend(["--" + key, str(value).lower() if isinstance(value, bool) else str(value)])
        else:
            raise MigrationError("Unsupported scalar command input.")
    return argv + ["-o", "json"]


def execute(bundle, tid, approved_digest, save, runner=run_az, inspector=inspect_cli, exports=()):
    result = validated(bundle)
    todo = select_todo(bundle, tid)
    if approved_digest != result["planDigest"]:
        raise MigrationError("Execution approval is not bound to the current plan.")
    approval = todo["approval"]
    if approval["status"] != "approved" or approval["planDigest"] != approved_digest:
        raise MigrationError("TODO lacks current explicit per-item approval.")
    graph = {item["id"]: item for item in bundle["todos.json"]["items"]}
    if any(graph[dep]["status"] != "behavior-verified" for dep in todo["dependsOn"]):
        raise MigrationError("Dependencies are not behavior-verified.")
    if any(graph[dep]["status"] not in ("resource-verified", "behavior-verified")
           for dep in todo.get("resourceDependencies", [])):
        raise MigrationError("Structural resource dependencies are not verified.")
    prerequisite_ids, pending = {tid}, [tid]
    while pending:
        node = graph[pending.pop()]
        for dependency in node["dependsOn"] + node.get("resourceDependencies", []):
            if dependency not in prerequisite_ids:
                prerequisite_ids.add(dependency)
                pending.append(dependency)
    for mapping in bundle["mapping.json"]["items"]:
        if prerequisite_ids.intersection(mapping.get("todoIds", [])) and any(
                result["status"] in ("failed", "inconclusive")
                for result in mapping.get("behaviorResults", {}).values()):
            raise MigrationError("Failed or inconclusive mapping behavior blocks dependent work.")
    try:
        snapshot = refresh(bundle, runner, inspector, exports)
    except MigrationError:
        invalidate(bundle, "Fresh source/catalog/CLI/native-sync evidence is unavailable or changed.")
        save(bundle)
        raise
    current = read_current(bundle, todo, snapshot, runner)
    changed = digest(semantic(snapshot)) != digest(semantic(bundle["destination-inventory.json"]))
    if current is not None and subset(todo["desiredState"], current):
        # This also recovers unknown outcomes without replaying a mutation.
        if changed and todo["status"] not in ("in-progress", "mutation-unknown"):
            invalidate(bundle, "Destination drift requires a new plan, even when desired fields match.")
            save(bundle)
            raise MigrationError("Destination drift blocks reuse of earlier verification.")
        if changed:
            for other in bundle["todos.json"]["items"]:
                if other["id"] != tid:
                    other["approval"]["status"] = "invalidated"
            for behavior in todo["behaviorResults"].values():
                behavior.update(status="pending", evidenceDigest=None, recordedAt=None)
            bundle["migration-report.md"] = (
                "# Migration report\n\nUnknown mutation reconciled by resource read-back. "
                "Other approvals were invalidated; fresh behavior verification is required.\n")
        todo["status"] = "resource-verified"
        bundle["destination-inventory.json"] = snapshot
        bundle["context.json"].update(phase="verification", completionStatus="in-progress")
        if todo["behaviorResults"] and all(v["status"] == "passed" and v["evidenceDigest"]
               for v in todo["behaviorResults"].values()):
            todo["status"] = "behavior-verified"
        save(bundle)
        return
    if changed:
        invalidate(bundle, "Destination drift; re-inventory and re-plan before mutation.")
        save(bundle)
        raise MigrationError("Destination drift blocks execution.")
    if capability(bundle, todo)["kind"] == "verify":
        raise MigrationError("Read-only verification did not match the approved desired state.")
    if todo["status"] in ("in-progress", "mutation-unknown"):
        invalidate(bundle, "Prior mutation outcome is unknown and desired state is not established.")
        save(bundle)
        raise MigrationError("Reconcile the prior attempt manually before retrying.")
    precondition = todo["precondition"]
    actual_digest = digest(semantic(current)) if current is not None else None
    if precondition["exists"] != (current is not None) or precondition["stateDigest"] != actual_digest:
        invalidate(bundle, "Target precondition changed.")
        save(bundle)
        raise MigrationError("Target precondition changed.")
    if any(not os.environ.get(name) for name in runtime_references(todo["arguments"])):
        raise MigrationError("A required caller-owned runtime variable is missing; no mutation was attempted.")
    todo["status"] = "in-progress"
    attempt = {"startedAt": now(), "outcome": "unknown"}
    todo["attempts"].append(attempt)
    bundle["context.json"].update(phase="execution", completionStatus="in-progress")
    save(bundle)
    try:
        with tempfile.TemporaryDirectory(prefix="aigateway-runtime-") as directory:
            runner(mutation_argv(bundle, todo, directory))
        observed_snapshot = destination_inventory(bundle["context.json"]["destinationId"], runner)
        observed = read_current(bundle, todo, observed_snapshot, runner)
    except MigrationError:
        todo["status"] = "mutation-unknown"
        bundle["context.json"].update(phase="blocked", completionStatus="blocked")
        save(bundle)
        raise
    if observed is None or not subset(todo["desiredState"], observed):
        todo["status"] = "failed"
        attempt["outcome"] = "unverified"
        bundle["context.json"].update(phase="blocked", completionStatus="failed")
        save(bundle)
        raise MigrationError("Mutation returned, but resource read-back did not match desired state.")
    attempt.update(outcome="resource-verified", finishedAt=now())
    todo["status"] = "resource-verified"
    bundle["destination-inventory.json"] = observed_snapshot
    bundle["context.json"]["phase"] = "verification"
    # Earlier approvals were made against earlier destination evidence.
    for other in bundle["todos.json"]["items"]:
        if other["id"] != tid:
            other["approval"]["status"] = "invalidated"
    save(bundle)


def approve(bundle, tid, approved_digest):
    result = validated(bundle)
    if result["planDigest"] != approved_digest:
        raise MigrationError("Approval must identify the displayed current plan digest.")
    todo = select_todo(bundle, tid)
    todo["approval"] = {"status": "approved", "planDigest": approved_digest, "approvedAt": now()}
    bundle["context.json"].update(phase="approval", completionStatus="in-progress")


def record_behavior(bundle, tid, bid, method, evidence_digest, approved_digest, status="passed"):
    result = validated(bundle)
    if result["planDigest"] != approved_digest:
        raise MigrationError("Verification must be bound to the current plan.")
    graph_mappings = [m for m in bundle["mapping.json"]["items"] if m["id"] == tid and m.get("todoIds")]
    if graph_mappings:
        mapping = graph_mappings[0]
        nodes = {t["id"]: t for t in bundle["todos.json"]["items"]}
        if any(nodes[identifier]["status"] not in ("resource-verified", "behavior-verified")
               for identifier in mapping["todoIds"]):
            raise MigrationError("All implementation resources must be verified before source behavior.")
        if (bid not in mapping.get("behaviorResults", {}) or method not in (
                "control-plane", "data-plane", "administrator-attestation")
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", evidence_digest)
                or status not in ("passed", "failed", "inconclusive")):
            raise MigrationError("Invalid mapping behavior verification.")
        mapping["behaviorResults"][bid] = {
            "status": status, "method": method, "evidenceDigest": evidence_digest, "recordedAt": now()}
        return
    todo = select_todo(bundle, tid)
    if todo["status"] not in ("resource-verified", "behavior-verified"):
        raise MigrationError("Read-back verification must precede behavior verification.")
    if bid not in todo["behaviorResults"] or not re.fullmatch(r"sha256:[0-9a-f]{64}", evidence_digest):
        raise MigrationError("Unknown behavior or invalid evidence digest.")
    if method not in ("control-plane", "data-plane", "administrator-attestation"):
        raise MigrationError("Unsupported verification method.")
    if status not in ("passed", "failed", "inconclusive"):
        raise MigrationError("Unsupported verification outcome.")
    todo["behaviorResults"][bid] = {"status": status, "method": method,
                                   "evidenceDigest": evidence_digest, "recordedAt": now()}
    if status == "failed":
        todo["status"] = "failed"
    if all(value["status"] == "passed" for value in todo["behaviorResults"].values()):
        todo["status"] = "behavior-verified"


def report(bundle, fresh=False):
    result = validate_plan(bundle)
    mappings = bundle["mapping.json"]["items"]
    todos = bundle["todos.json"]["items"]
    residuals = [item for item in mappings if item["classification"] == "cannot-import"]
    unresolved = [item for item in mappings if item["classification"] == "needs-input"]
    mapping_results = [value for mapping in mappings for value in mapping.get("behaviorResults", {}).values()]
    graph_nodes = {identifier for mapping in mappings for identifier in mapping.get("todoIds", [])}
    accepted = all(item["residual"] and item["residual"]["acceptance"] == "accepted"
                   and item["residual"]["approvedPlanDigest"] == result["planDigest"]
                   for item in residuals)
    if bundle["context.json"]["completionStatus"] == "cancelled":
        status = "cancelled"
    elif any(todo["status"] == "failed" for todo in todos) or any(v["status"] == "failed" for v in mapping_results):
        status = "failed"
    elif (result["status"] != "valid" or unresolved or not fresh
          or any(todo["status"] in ("blocked", "in-progress", "mutation-unknown") or
                 any(result["status"] == "inconclusive" for result in todo["behaviorResults"].values())
                 for todo in todos)
          or any(v["status"] == "inconclusive" for v in mapping_results)
          or not bundle["destination-inventory.json"].get("exists")
          or bundle["destination-inventory.json"].get("errors")):
        status = "blocked"
    elif any(gateway.get("properties", {}).get("provisioningState") != "Succeeded"
             for gateway in bundle["destination-inventory.json"]["collections"].get("gateway", [])):
        status = "blocked"
    elif (not accepted or any(
            todo["status"] not in (("resource-verified", "behavior-verified")
                                   if todo["id"] in graph_nodes else ("behavior-verified",)) for todo in todos)
          or any(v["status"] != "passed" or not v["evidenceDigest"] for v in mapping_results)):
        status = "incomplete"
    else:
        status = "complete-with-accepted-residuals" if residuals else "complete"
    bundle["context.json"].update(
        completionStatus=status, phase="complete" if status.startswith("complete") else "blocked")
    lines = ["# APIM migration report", "", f"Status: **{status}**", "",
             f"Source: `{bundle['context.json']['sourceId']}`",
             f"Destination: `{bundle['context.json']['destinationId']}`", "",
             f"Plan digest: `{result['planDigest']}`", "",
             f"Unresolved mappings: {len(unresolved)}",
             f"Explicit residuals: {len(residuals)}",
             f"Behavior-verified TODOs: {sum(t['status'] == 'behavior-verified' for t in todos)}/{len(todos)}",
             f"Resource-verified TODOs: {sum(t['status'] in ('resource-verified', 'behavior-verified') for t in todos)}/{len(todos)}",
             f"Source behavior checks: {sum(v['status'] == 'passed' for v in mapping_results)}/{len(mapping_results)}",
             "", "## Work", ""]
    for todo in todos:
        lines.append(f"- `{todo['id']}`: {todo['status']}.")
    lines.extend(["", "## Follow-up", ""])
    for mapping in unresolved:
        lines.append(f"- `{mapping['id']}`: {clean(mapping['question'])}")
    for mapping in residuals:
        residual = mapping["residual"]
        accepted_here = (residual["acceptance"] == "accepted"
                         and residual["approvedPlanDigest"] == result["planDigest"])
        lines.append(f"- `{mapping['id']}`: {clean(residual['reason'])} "
                     f"Acceptance: {'accepted for this plan' if accepted_here else 'required'}. "
                     f"Manual action: {clean(residual['manualAction'])}")
    lines.append("\nInventory and reports are redacted; secret inputs are runtime-only.\n")
    bundle["migration-report.md"] = "\n".join(lines)
    return status
