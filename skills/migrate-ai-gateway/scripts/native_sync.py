"""Read-only public CLI sync previews; no local Foundry missing/stale algorithm."""

from __future__ import annotations

import copy
import re

from core import MigrationError, clean, digest, now, resource_id, run_az, semantic, subset, validate_schema
from gateway import inspect_cli
from model_inventory import validate_catalog


NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}")


def provider_path(root, name):
    resource_id(root, "aigateways")
    if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name or name.startswith("-"):
        raise MigrationError("Native preview requires an explicit destination provider name.")
    return root + "/workspaces/default/modelProviders/" + name


def model_rows(preview):
    return {row["resourceId"].lower(): row for row in preview["plan"]["models"]}


def check_cli(cli):
    required = {"--dry-run", "--subscription", "--resource-group", "--gateway-name", "--name"}
    if ("model-provider sync" not in cli.get("resourceCommands", {}).get("aigateways", [])
            or not required <= set(cli.get("commands", {}).get("model-provider sync") or [])):
        raise MigrationError("The reviewed current CLI does not expose a routed read-only sync preview contract.")


def validate_preview(preview, catalogs, destination, cli, check_snapshot=False):
    validate_schema(preview, "native-sync-preview")
    validate_catalog(catalogs)
    check_cli(cli)
    if (preview["catalogDigest"] != digest(semantic(catalogs))
            or preview["cliFingerprint"] != cli["fingerprint"]
            or preview["destinationId"].lower() != destination["destinationId"].lower()):
        raise MigrationError("Native sync preview evidence is stale or belongs to a different target/contract.")
    provider = next((p for p in catalogs["providers"] if p["id"] == preview["providerKey"]), None)
    if not provider or provider["kind"] != "Foundry" or provider["accountId"].lower() != preview["accountId"].lower():
        raise MigrationError("Native sync preview does not belong to the selected Foundry account.")
    if check_snapshot and preview["destinationDigest"] != digest(semantic(destination)):
        raise MigrationError("Destination evidence changed since the native preview; recollect it.")
    if preview["status"] == "blocked":
        return preview
    plan = preview["plan"]
    path = provider_path(destination["destinationId"], preview["providerName"])
    if (plan["providerId"].lower() != path.lower()
            or plan["providerName"].lower() != preview["providerName"].lower()
            or plan["foundryResourceId"].lower() != preview["accountId"].lower()):
        raise MigrationError("Native sync output escaped the approved provider/account scope.")
    seen = set()
    for row in plan["models"]:
        prefix = preview["accountId"] + "/deployments/"
        deployment = row["deploymentResourceId"]
        if (row["resourceId"].lower() != (path + "/models/" + row["name"]).lower()
                or not deployment.lower().startswith(prefix.lower())
                or not re.fullmatch(r"[A-Za-z0-9_.()-]{1,80}", deployment[len(prefix):])
                or deployment[len(prefix):] == "." or ".." in deployment[len(prefix):]
                or row["resourceId"].lower() in seen):
            raise MigrationError("Native sync model identity is duplicated or outside the selected scope.")
        if row["action"] == "create" and row["name"] != deployment[len(prefix):]:
            raise MigrationError("Native create naming differs from its reviewed deployment-name contract.")
        seen.add(row["resourceId"].lower())
    return preview


def _check_provider(value, path, provider):
    properties = value.get("properties") if isinstance(value, dict) else None
    if (not isinstance(properties, dict) or str(value.get("id", "")).lower() != path.lower()
            or str(properties.get("kind", "")).lower() != "foundry"):
        raise MigrationError("Native preview requires the existing selected Foundry provider.")
    config = properties.get("foundry")
    if (not isinstance(config, dict) or not isinstance(config.get("resourceIds"), list)
            or len(config["resourceIds"]) != 1
            or str(config["resourceIds"][0]).lower() != provider["accountId"].lower()
            or str(config.get("endpoint", "")).rstrip("/") != provider["endpoint"].rstrip("/")):
        raise MigrationError("Destination provider account/endpoint does not match the approved catalog.")
    for container in (properties, config):
        for field in ("accountResourceId", "resourceId"):
            if container.get(field) is not None and str(container[field]).lower() != provider["accountId"].lower():
                raise MigrationError("Provider has an unapproved alternate account reference.")


def collect_preview(catalogs, destination, provider_key, provider_name, approved=False,
                    runner=run_az, inspector=inspect_cli, cli=None):
    if not approved:
        raise MigrationError("Approve native preview reads of the gateway workspace, aliases and provider's Foundry account.")
    validate_catalog(catalogs)
    validate_schema(destination, "destination-inventory")
    provider = next((p for p in catalogs["providers"] if p["id"] == provider_key), None)
    if not provider or provider["kind"] != "Foundry" or provider["error"]:
        raise MigrationError("Native sync previews support available Foundry catalogs only, not Custom providers.")
    root = destination["destinationId"]
    path = provider_path(root, provider_name)
    if not destination["exists"] or any(
            e["domain"] in ("model-provider", "model", "model-alias") for e in destination["errors"]):
        raise MigrationError("Native preview requires an existing destination and complete model/provider/alias reads.")
    for group in ("model-provider", "model", "model-alias"):
        if group not in destination["collections"]:
            raise MigrationError("Recollect complete destination evidence before requesting native preview.")
    if not any(str(p.get("id", "")).lower() == path.lower()
               for p in destination["collections"]["model-provider"]):
        raise MigrationError("Create/verify the selected provider first, then collect a native sync preview.")
    cli = cli if cli is not None else inspector()
    check_cli(cli)
    result = {
        "schemaVersion": "1.0", "providerKey": provider_key, "providerName": provider_name,
        "destinationId": root, "accountId": provider["accountId"], "capturedAt": now(),
        "cliFingerprint": cli["fingerprint"], "catalogDigest": digest(semantic(catalogs)),
        "destinationDigest": digest(semantic(destination)), "status": "blocked", "error": None, "plan": None,
    }
    target = resource_id(root, "aigateways")
    selectors = ["--subscription", target["subscription"], "--resource-group", target["resourceGroup"],
                 "--gateway-name", target["gateway"], "--name", provider_name]
    try:
        before = runner(["az", "aigateway", "model-provider", "show", *selectors, "-o", "json"])
        _check_provider(before, path, provider)
        baseline = next(p for p in destination["collections"]["model-provider"]
                        if str(p.get("id", "")).lower() == path.lower())
        if digest(semantic(clean(before))) != digest(semantic(baseline)):
            raise MigrationError("Provider differs from the destination snapshot; recollect.")
        plan = runner(["az", "aigateway", "model-provider", "sync", *selectors, "--dry-run", "-o", "json"])
        after = runner(["az", "aigateway", "model-provider", "show", *selectors, "-o", "json"])
        _check_provider(after, path, provider)
        if digest(semantic(clean(before))) != digest(semantic(clean(after))):
            raise MigrationError("Provider changed during native planning; recollect rather than mixing evidence.")
        result.update(status="ready", plan=plan)
        validate_preview(result, catalogs, destination, cli, check_snapshot=True)
        models = [m for m in destination["collections"]["model"]
                  if str(m.get("id", "")).lower().startswith(path.lower() + "/models/")]
        existing = {str(m.get("id", "")).lower(): m for m in models}
        if len(existing) != len(models):
            raise MigrationError("Destination model evidence has duplicate identities; recollect.")
        planned_existing = {r["resourceId"].lower() for r in plan["models"] if r["action"] != "create"}
        creates = {r["resourceId"].lower() for r in plan["models"] if r["action"] == "create"}
        if set(existing) != planned_existing or set(existing) & creates:
            raise MigrationError("Native preview and destination model evidence disagree; recollect.")
        for row in plan["models"]:
            if row["action"] == "create":
                continue
            properties = existing[row["resourceId"].lower()].get("properties")
            deployment = properties.get("deployment") if isinstance(properties, dict) else None
            if (not isinstance(deployment, dict)
                    or str(deployment.get("resourceId", "")).lower() != row["deploymentResourceId"].lower()):
                raise MigrationError("Native registration deployment differs from destination evidence; recollect.")
        aliases = set()
        for alias in destination["collections"]["model-alias"]:
            properties = alias.get("properties")
            backends = properties.get("backendModels") if isinstance(properties, dict) else None
            if (not isinstance(backends, list)
                    or not all(isinstance(b, dict) and isinstance(b.get("resourceId"), str) for b in backends)):
                raise MigrationError("Destination alias references are malformed; recollect.")
            aliases.update(b["resourceId"].lower() for b in backends)
        if any(r["action"] == "delete" and r["resourceId"].lower() in aliases for r in plan["models"]):
            raise MigrationError("Native preview disagrees with alias references in the snapshot; recollect.")
    except MigrationError as exc:
        error = ("Native sync preview is blocked by an alias-bound stale registration; keep all models/aliases unchanged."
                 if exc.code == "SyncAliasBoundStale" else str(exc))
        result.update(status="blocked", error=error, plan=None)
    validate_schema(result, "native-sync-preview")
    return result


def selected_action(bundle, provider_key, target_provider, model):
    previews = [p for p in bundle["mapping.json"].get("nativeSyncPreviews", []) if p["providerKey"] == provider_key]
    if len(previews) != 1:
        raise MigrationError("Foundry model planning requires one current native sync preview; set up the provider first.")
    preview = previews[0]
    validate_preview(preview, bundle["model-catalog.json"], bundle["destination-inventory.json"],
                     bundle["capability-contract.json"]["cli"])
    if preview["status"] != "ready":
        raise MigrationError(preview["error"])
    if preview["providerName"].lower() != target_provider.lower():
        raise MigrationError("Selected provider name differs from the native preview.")
    rid = provider_path(bundle["context.json"]["destinationId"], target_provider) + "/models/" + model["name"]
    row = model_rows(preview).get(rid.lower())
    provider = next(p for p in bundle["model-catalog.json"]["providers"] if p["id"] == provider_key)
    catalog_model = next(m for m in provider["models"] if m["id"] == model["id"])
    if (not row or row["action"] == "delete"
            or row["deploymentResourceId"].lower() != catalog_model["deploymentId"].lower()):
        raise MigrationError("Select an explicit native preview create/unchanged registration; do not rename or select delete actions.")
    return row


def removal_proposals(bundle):
    proposals = []
    selected = {p["id"] for p in (bundle["mapping.json"].get("selection") or {}).get("providers", [])}
    for preview in bundle["mapping.json"].get("nativeSyncPreviews", []):
        if preview["providerKey"] in selected and preview["status"] == "ready":
            proposals.extend({"resourceId": row["resourceId"], "action": "propose-separate-removal",
                              "source": "native-cli-preview", "blockedByAlias": False, "executionApproved": False}
                             for row in preview["plan"]["models"] if row["action"] == "delete")
    return proposals


def refresh_previews(bundle, destination, runner, cli):
    """Recheck native decisions, allowing only recorded create->unchanged progress."""
    for preview in bundle["mapping.json"].get("nativeSyncPreviews", []):
        validate_preview(preview, bundle["model-catalog.json"], destination, cli)
        if preview["status"] != "ready":
            raise MigrationError(preview["error"])
        fresh = collect_preview(bundle["model-catalog.json"], destination,
                                preview["providerKey"], preview["providerName"],
                                approved=True, runner=runner, cli=cli)
        if fresh["status"] != "ready":
            raise MigrationError(fresh["error"])
        expected = copy.deepcopy(preview["plan"])
        for row in expected["models"]:
            if row["action"] != "create":
                continue
            todo = next((t for t in bundle["todos.json"]["items"] if
                         t["capabilityId"] == "model.create" and
                         (provider_path(preview["destinationId"], t["target"]["provider"])
                          + "/models/" + str(t["target"]["name"])).lower() == row["resourceId"].lower()), None)
            current = next((m for m in destination["collections"]["model"]
                            if str(m.get("id", "")).lower() == row["resourceId"].lower()), None)
            if (todo and todo["attempts"] and
                    todo["status"] in ("resource-verified", "behavior-verified", "in-progress", "mutation-unknown")
                    and current is not None and subset(todo["desiredState"], clean(current))):
                row["action"] = "unchanged"
        def normalized(plan):
            result = copy.deepcopy(plan)
            result["providerName"] = result["providerName"].lower()
            for key in ("providerId", "foundryResourceId"):
                result[key] = result[key].lower()
            for row in result["models"]:
                for key in ("name", "resourceId", "deploymentResourceId"):
                    row[key] = row[key].lower()
            result["models"].sort(key=lambda row: row["resourceId"])
            return result
        if normalized(expected) != normalized(fresh["plan"]):
            raise MigrationError("Native sync decisions changed beyond recorded progress; refresh evidence and re-plan.")
