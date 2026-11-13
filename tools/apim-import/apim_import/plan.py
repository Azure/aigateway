"""Propose a migration plan, and preserve it across regeneration.

The plan is the one living artifact: proposed by the tool, adapted in place by
the agent and the user, then executed. Every item arrives with a recommended
value and the reasoning behind it -- ``needs-decision`` means "confirm or change
this", not "the tool has no opinion".

Regeneration is safe. An adapted item is preserved, and re-opened only when the
APIM facts *it* was decided against actually changed. An unrelated change never
disturbs settled work.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from . import ids
from .capability import CapabilityMap

SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"

READY = "ready"
NEEDS_DECISION = "needs-decision"
ADAPTED = "adapted"
EXCLUDED = "excluded"
STALE = "stale"


def digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def secret_ref(ref_id: str) -> dict[str, str]:
    """A placeholder resolved at apply time from the inventory's recipe.

    The value never enters the plan; only the reference does.
    """
    return {"$secretRef": ref_id}


class PlanBuilder:
    def __init__(
        self,
        inventory: dict[str, Any],
        capabilities: CapabilityMap,
        *,
        previous: dict[str, Any] | None = None,
        target: str | None = None,
    ) -> None:
        # Where this plan deploys to. Recorded on the plan so a resumed session
        # knows the destination without being told again.
        self.target = target or ((previous or {}).get("target") or {}).get("resourceId")
        self.inventory = inventory
        self.caps = capabilities
        self.previous = previous or {}
        self.items: list[dict[str, Any]] = []
        self.prerequisites: list[dict[str, Any]] = []

    # ------------------------------------------------------------- build

    def build(self) -> dict[str, Any]:
        assets = self.inventory.get("assets") or {}
        for provider in assets.get("modelProviders") or []:
            self._provider(provider)
        for model in assets.get("models") or []:
            self._model(model)
        for server in assets.get("mcpServers") or []:
            self._mcp(server)
        for agent in assets.get("agents") or []:
            self._agent(agent)
        self._policies()
        self._structural()
        self._manual_prerequisites()

        merged, orphaned = self._merge_with_previous(self.items)
        service = self.inventory.get("service") or {}
        return {
            "$schema": "https://github.com/Azure/aigateway/tools/apim-import/schemas/plan.schema.json",
            "schemaVersion": SCHEMA_VERSION,
            "kind": "apimMigrationPlan",
            "generator": {"name": "apim-import", "version": GENERATOR_VERSION, "command": "plan"},
            "generatedAt": _now(),
            "source": {
                "resourceId": service.get("resourceId"),
                "name": service.get("name"),
                "inventoryCapturedAt": (self.inventory.get("collection") or {}).get("completedAt"),
            },
            "target": {
                "resourceId": self.target,
                "capabilities": self.caps.to_dict(),
                "publishableRoutes": self.caps.publishable_routes(),
            },
            "summary": {**_summarize(merged), "orphanedDecisions": len(orphaned)},
            "prerequisites": self.prerequisites,
            # Settled decisions whose item no longer exists. Dropping them quietly
            # would lose work across a tool change and re-ask as if never asked.
            "orphanedDecisions": orphaned,
            "items": merged,
        }

    # ------------------------------------------------------------- assets

    def _add(
        self,
        *,
        item_id: str,
        source: dict[str, Any],
        kind: str | None,
        verdict: str,
        rationale: str,
        capability_id: str | None = None,
        proposal: Any = None,
        options: list[dict[str, str]] | None = None,
        evidence: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        blocking: bool = False,
        cannot_accept: bool = False,
    ) -> dict[str, Any]:
        capability = self.caps.capability(capability_id)
        status = READY if verdict in {"native", "handled", "notApplicable"} else NEEDS_DECISION
        if verdict in {"handled", "notApplicable"}:
            status = EXCLUDED
        item: dict[str, Any] = {
            "id": item_id,
            "source": source,
            "status": status,
            "kind": kind,
            "verdict": verdict,
            "capabilityId": capability_id,
            "proposal": proposal,
            "decision": None,
            "rationale": rationale,
            "options": options or [],
            "evidence": evidence or {},
            "target": target or {},
            "blocking": blocking,
            "cannotAccept": cannot_accept,
            "decidedAgainst": None,
        }
        if capability and not capability.usable:
            # The catalog declares it; the installed CLI does not expose it. That
            # is a limit of the local tooling, not of the target, and the item has
            # to say so -- otherwise it reads as a missing target capability and
            # the generic loss options send the reader to fix the wrong thing.
            missing = (
                f" (missing {', '.join(capability.missing_options)})"
                if capability.missing_options else ""
            )
            item["status"] = NEEDS_DECISION
            item["kind"] = item["kind"] or "accept-loss"
            item["blocking"] = True
            item["capabilityUnavailable"] = {
                "support": capability.support,
                "missingOptions": capability.missing_options,
            }
            item["rationale"] = (
                f"The installed az extension does not expose `az aigateway "
                f"{' '.join(capability.command)}`{missing}. This is a limit of the local CLI, "
                "not of the target."
                + (f" Mapping: {item['rationale']}" if item["rationale"] else "")
            )
            item["options"] = [
                _opt("upgrade-cli", "Install or upgrade the aigateway extension, then re-plan."),
                _opt("retain-in-apim", "Keep this workload on APIM for now."),
                _opt("block", "Stop until the CLI can perform it."),
            ]
        if capability and capability.limitations:
            item["capabilityLimitations"] = capability.limitations
        if item["status"] == NEEDS_DECISION and not item["options"]:
            # An item that asks for a decision without offering one is useless to
            # whoever has to make it. Fall back to the generic set, and say that
            # the rule was incomplete rather than hiding it.
            item["options"] = _loss_options("gap")
            item["rulesGap"] = (
                f"No options are defined for this {item['kind'] or 'item'}; the generic set is "
                "offered instead. The mapping rule should name the real choices."
            )
        self.items.append(item)
        return item

    def _provider(self, provider: dict[str, Any]) -> None:
        kind = provider.get("targetProviderKind") or "Custom"
        auth = provider.get("auth") or {}
        objects: dict[str, Any] = {"name": _slug(provider["id"]), "kind": kind}
        if kind == "Foundry":
            azure = provider.get("azure") or {}
            objects["foundry"] = {
                "endpoint": provider.get("endpoint"),
                "resourceIds": [azure["accountResourceId"]] if azure.get("accountResourceId") else [],
                "authentication": {
                    "kind": "ManagedIdentity",
                    "managedIdentity": {"resource": "https://cognitiveservices.azure.com/"},
                },
            }
        else:
            objects["custom"] = {
                "endpoint": provider.get("endpoint"),
                "authentication": _custom_auth(auth),
            }
        self._add(
            item_id=ids.item("modelProvider", provider["id"]),
            source={"assetId": provider["id"], "assetKind": "modelProvider", "aspect": "registration"},
            kind=None,
            verdict="native",
            capability_id="provider.create",
            rationale=f"{provider.get('providerLabel') or provider.get('providerKind')} provider registers directly.",
            evidence={"endpoint": provider.get("endpoint"), "authMode": auth.get("mode")},
            target={"capability": "provider.create", "objects": [objects]},
        )

    def _model(self, model: dict[str, Any]) -> None:
        asset_id = model["id"]
        endpoints = model.get("endpoints") or {}
        surface = endpoints.get("surface") or {}
        models = model.get("models") or {}

        # Scope: how much of what this API publishes can move at all.
        if surface.get("status") == "unbounded":
            self._add(
                item_id=ids.item(asset_id, "surface"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "publishedSurface"},
                kind="reduce-surface",
                verdict="partial",
                capability_id="alias.create",
                proposal="inference-only",
                rationale=surface.get("note") or "The exposed surface cannot be read from configuration.",
                options=[
                    _opt("inference-only", "Publish the four inference routes; any other path callers use breaks."),
                    _opt("retain-in-apim", "Nothing moves for this API."),
                    _opt("block", "Stop the migration until the used routes are established."),
                ],
                evidence={"surface": surface},
                blocking=True,
            )
        elif surface.get("unpublishableCount"):
            groups = ", ".join(
                f"{entry['group']} x{entry['count']}" for entry in surface.get("unpublishable", [])
            )
            self._add(
                item_id=ids.item(asset_id, "surface"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "publishedSurface"},
                kind="reduce-surface",
                verdict="partial",
                capability_id="alias.create",
                proposal="split",
                rationale=(
                    f"{surface['publishableCount']} of {surface['operationCount']} operations map to the "
                    f"four publishable routes. No target for: {groups}."
                ),
                options=[
                    _opt("split", f"Inference moves; {surface['unpublishableCount']} operations stay on APIM."),
                    _opt("inference-only", "Inference moves and the rest is dropped; those callers break."),
                    _opt("retain-in-apim", "Nothing moves for this API."),
                    _opt("block", "Stop the migration until resolved."),
                ],
                evidence={"surface": surface},
                blocking=True,
            )

        # Models: a registration needs a model name.
        if models.get("status") in {"unresolved", "empty"}:
            self._add(
                item_id=ids.item(asset_id, "models"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "modelCatalogue"},
                kind="enumerate",
                verdict="partial",
                capability_id="model.create",
                # A provider with a catalogue endpoint has an actionable default:
                # fetch it rather than ask someone to type model names.
                proposal="resolve-models" if models.get("discoverySource") == "modelsEndpoint"
                else "list-models",
                rationale=" ".join(models.get("notes") or []) or "The model catalogue could not be resolved.",
                options=[
                    _opt("resolve-models", "Read the provider's catalogue with its credential."),
                    _opt("list-models", "Name the models to register."),
                    _opt("retain-in-apim", "Do not migrate this API."),
                ],
                evidence={"discoverySource": models.get("discoverySource"), "notes": models.get("notes")},
                blocking=True,
            )
        else:
            registrations = models.get("resolved") or []
            for resolved in registrations:
                self._model_registration(model, resolved)
            if registrations:
                self._alias_naming(model, registrations)

        # Dialect translation.
        translation = endpoints.get("translation") or {}
        if translation.get("status") == "translating":
            self._add(
                item_id=ids.item(asset_id, "dialect"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "callerDialect"},
                kind="translate",
                verdict="partial",
                capability_id="alias.create",
                proposal="move-callers",
                rationale=translation.get("note") or "",
                options=[
                    _opt("move-callers", f"Callers move to {', '.join(translation.get('backend') or [])}."),
                    _opt("retain-in-apim", "Keep APIM in front so callers are unchanged."),
                    _opt("block", "Stop until the caller impact is agreed."),
                ],
                evidence={"translation": translation},
                blocking=True,
            )
        elif translation.get("status") == "indeterminate":
            self._add(
                item_id=ids.item(asset_id, "dialect"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "callerDialect"},
                kind="enumerate",
                verdict="partial",
                capability_id="alias.create",
                rationale=translation.get("note") or "",
                options=[
                    _opt("confirm-dialect", "State the dialect callers use."),
                    _opt("retain-in-apim", "Do not migrate this API."),
                ],
                evidence={"translation": translation},
                blocking=True,
            )

    def _model_registration(self, model: dict[str, Any], resolved: dict[str, Any]) -> None:
        asset_id = model["id"]
        name = resolved.get("deploymentName") or resolved.get("modelName") or "model"
        target = resolved.get("target") or {}
        endpoints = target.get("supportedEndpoints") or []
        self._add(
            item_id=ids.item(asset_id, f"model/{name}"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": f"model:{name}"},
            kind=None,
            verdict="native",
            capability_id="model.create",
            rationale=f"Registers {resolved.get('modelName')} from a resolved deployment.",
            evidence={"modelName": resolved.get("modelName"), "modelVersion": resolved.get("modelVersion")},
            target={
                "capability": "model.create",
                "objects": [{
                    "name": _slug(name),
                    "deploymentConfig": target.get("deployment") or {},
                    "supportedEndpoints": endpoints,
                }],
            },
        )

    def _alias_naming(self, model: dict[str, Any], registrations: list[dict[str, Any]]) -> None:
        """One naming decision per API, not one per model.

        The callable name is not in APIM -- it arrives in the request body -- so
        every model needs one. Asked per model, a provider exposing a catalogue of
        fifty turns into fifty questions whose answer is "the model's own name".
        It is one decision with a per-model default that can be overridden.
        """
        asset_id = model["id"]
        members = [
            {
                "modelName": entry.get("modelName"),
                "proposedAliasName": entry.get("deploymentName") or entry.get("modelName"),
                "supportedEndpoints": (entry.get("target") or {}).get("supportedEndpoints") or [],
            }
            for entry in registrations
        ]
        sample = ", ".join(str(member["proposedAliasName"]) for member in members[:4])
        more = f" and {len(members) - 4} more" if len(members) > 4 else ""
        self._add(
            item_id=ids.item(asset_id, "aliasNames"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "aliasNames"},
            kind="name",
            verdict="partial",
            capability_id="alias.create",
            proposal="use-model-names",
            rationale=(
                f"An alias publishes the route, and its routingName is what clients send as `model`. "
                f"APIM does not store it. Proposed for {len(members)} model(s): {sample}{more}."
            ),
            options=[
                _opt("use-model-names", "Publish each model under its own name."),
                _opt("override", "Supply names per model; set them in this item's members."),
            ],
            evidence={"members": members, "count": len(members)},
            target={
                "capability": "alias.create",
                "objects": [
                    {
                        "routingName": member["proposedAliasName"],
                        "backendModels": [{"modelName": _slug(str(member["proposedAliasName"])),
                                            "priority": 0, "weight": 100}],
                        "supportedEndpoints": member["supportedEndpoints"],
                    }
                    for member in members
                ],
            },
        )

    def _mcp(self, server: dict[str, Any]) -> None:
        asset_id = server["id"]
        pattern = server.get("pattern")
        rule = _first(
            self.caps.asset_rules(),
            lambda r: (r.get("match") or {}).get("family") == "mcpServers"
            and (r.get("match") or {}).get("pattern") == pattern,
        )
        if rule:
            self._add(
                item_id=ids.item(asset_id, "registration"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "registration"},
                kind=rule.get("itemKind"),
                verdict=rule["verdict"],
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                rationale=rule.get("rationale")
                or f"A {pattern} MCP server registers as a tool server with its upstream endpoints.",
                options=[_opt(value, "") for value in rule.get("options") or []],
                evidence={"pattern": pattern, "upstream": server.get("upstream")},
                target={
                    "capability": "mcp.create",
                    "objects": [{"name": _slug(asset_id), "endpoints": _mcp_endpoints(server)}],
                } if rule["verdict"] in {"native", "partial"} else {},
                blocking=rule["verdict"] == "gap",
            )
        discovery_record = server.get("toolDiscovery") or {}
        discovery = discovery_record.get("status")
        if discovery == "complete" and discovery_record.get("policiesApplied") is False:
            # The list came from the upstream with the API's policies bypassed, so
            # it can be broader than what callers reach through the gateway.
            # Treating it as settled would publish tools APIM currently withholds.
            self._add(
                item_id=ids.item(asset_id, "tools"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "toolExposure"},
                kind="enumerate",
                verdict="partial",
                proposal="accept-as-listed",
                rationale=(
                    f"{discovery_record.get('discoveredCount')} tools were listed directly from the "
                    "upstream because the gateway route was unavailable, so the API's policies did "
                    "not run. APIM may be withholding some of these from callers today."
                ),
                options=[
                    _opt("accept-as-listed", "Federate every tool the upstream exposes."),
                    _opt("verify-through-gateway", "Re-list through APIM before deciding."),
                    _opt("retain-in-apim", "Do not migrate this server."),
                ],
                evidence={"toolDiscovery": discovery_record,
                          "tools": [tool.get("name") for tool in server.get("tools") or []]},
                blocking=True,
            )
        if discovery == "runtimeOnly":
            tool_rule = _first(
                self.caps.asset_rules(),
                lambda r: (r.get("match") or {}).get("toolDiscovery") == "runtimeOnly",
            ) or {}
            self._add(
                item_id=ids.item(asset_id, "tools"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "toolExposure"},
                kind="enumerate",
                verdict="gap",
                proposal=tool_rule.get("proposal", "accept-all"),
                rationale=tool_rule.get("rationale", ""),
                options=[_opt(value, "") for value in tool_rule.get("options") or []],
                evidence={"toolDiscovery": server.get("toolDiscovery")},
            )

    def _agent(self, agent: dict[str, Any]) -> None:
        rule = _first(
            self.caps.asset_rules(), lambda r: (r.get("match") or {}).get("family") == "agents"
        ) or {}
        self._add(
            item_id=ids.item(agent["id"], "registration"),
            source={"assetId": agent["id"], "assetKind": "agent", "aspect": "registration"},
            kind="accept-loss",
            verdict="gap",
            proposal=rule.get("proposal", "retain-in-apim"),
            rationale=rule.get("rationale", ""),
            options=[_opt(value, "") for value in rule.get("options") or []],
            evidence={"hosting": agent.get("hosting"), "agent": agent.get("agent")},
        )

    # ----------------------------------------------------------- policies

    def _policies(self) -> None:
        """One item per distinct policy treatment, batched across assets."""
        batches: dict[str, dict[str, Any]] = {}
        for document in self.inventory.get("policies") or []:
            for element in document.get("elements") or []:
                if not _is_policy_statement(element):
                    continue
                has_expression = bool(element.get("expressionIds"))
                rule = self.caps.policy_rule(
                    element["name"], family=element.get("family", ""), has_expression=has_expression
                )
                if not rule or rule["verdict"] in {"notApplicable", "handled"}:
                    continue
                rule = _apply_partial_when(rule, element)
                signature = _policy_signature(element, rule, has_expression)
                batch = batches.setdefault(signature, {"rule": rule, "element": element,
                                                        "hasExpression": has_expression, "members": []})
                batch["members"].append({
                    "policyId": document["id"],
                    "scope": document.get("scope", {}).get("level"),
                    "path": element["path"],
                    "element": element["name"],
                    "attributes": element.get("attributes") or {},
                })

        for signature, batch in sorted(batches.items()):
            rule = batch["rule"]
            element = batch["element"]
            members = batch["members"]
            label = element["name"] + (" with expression" if batch["hasExpression"] else "")
            self._add(
                item_id=ids.item("policy", signature),
                source={"assetId": None, "assetKind": "policy", "aspect": element["name"]},
                kind=rule.get("itemKind", "accept-loss"),
                verdict=rule["verdict"],
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                # A native mapping needs no argument, but it still has to say what
                # it does -- an item with a blank rationale is unreviewable.
                rationale=rule.get("rationale")
                or (
                    f"`{element['name']}` maps to the target's `{rule['target']}` policy."
                    if rule.get("target")
                    else f"`{element['name']}` is carried by another object."
                ),
                options=[_opt(value, "") for value in rule.get("options") or []]
                or _loss_options(rule["verdict"]),
                evidence={
                    "element": element["name"],
                    "target": rule.get("target"),
                    "hasExpression": batch["hasExpression"],
                    "occurrences": len(members),
                    "members": members,
                },
                target=_policy_target(rule, members),
                blocking=rule["verdict"] == "gap",
            )

    # --------------------------------------------------------- structural

    def _structural(self) -> None:
        shared = self.inventory.get("shared") or {}
        rules = {(_match_kind(rule)): rule for rule in self.caps.structural_rules()}

        for workspace in self.inventory.get("workspaces") or []:
            if workspace.get("name") == "default" or not workspace.get("collected"):
                continue
            rule = rules.get("workspace") or {}
            self._add(
                item_id=ids.item("workspace", workspace["name"]),
                source={"assetId": None, "assetKind": "workspace", "aspect": workspace["name"]},
                kind="collapse",
                verdict="partial",
                proposal=rule.get("proposal", "flatten"),
                rationale=rule.get("rationale", ""),
                options=[_opt(value, "") for value in rule.get("options") or []],
                evidence={"workspace": workspace},
                blocking=True,
            )

        subscriptions = shared.get("subscriptions") or []
        if subscriptions:
            rule = rules.get("subscriptions") or {}
            scopes = sorted({entry["scope"]["level"] for entry in subscriptions})
            self._add(
                item_id=ids.item("access", "subscriptions"),
                source={"assetId": None, "assetKind": "access", "aspect": "subscriptions"},
                kind="scope",
                verdict="partial",
                capability_id="key.create",
                proposal=rule.get("proposal", "entra-rbac"),
                rationale=rule.get("rationale", ""),
                options=[_opt(value, "") for value in rule.get("options") or []],
                evidence={"count": len(subscriptions), "scopeLevels": scopes},
                blocking=True,
            )

        for name, kind in (("certificates", "certificates"), ("credentialProviders", "credentialProviders")):
            entries = shared.get(name) or []
            if not entries:
                continue
            rule = rules.get(kind) or {}
            self._add(
                item_id=ids.item("shared", kind),
                source={"assetId": None, "assetKind": kind, "aspect": "reprovisioning"},
                kind="accept-loss",
                verdict="gap",
                rationale=rule.get("rationale", ""),
                options=_loss_options("gap"),
                evidence={"count": len(entries), "names": [entry.get("name") for entry in entries]},
            )

        # A failed read is unknown, not absent, and cannot be accepted as a loss.
        failures = [
            entry for entry in (self.inventory.get("collection") or {}).get("coverage") or []
            if entry.get("status") == "failed"
        ]
        for failure in failures:
            rule = rules.get("coverageGap") or {}
            self._add(
                item_id=ids.item("coverage", f"{failure['collection']}/{failure['scope']}"),
                source={"assetId": None, "assetKind": "coverageGap", "aspect": failure["collection"]},
                kind="enumerate",
                verdict="gap",
                rationale=rule.get("rationale", ""),
                options=[_opt("re-collect", "Fix access and collect again."),
                         _opt("supply-facts", "State what is there.")],
                evidence={"coverage": failure},
                blocking=True,
                cannot_accept=True,
            )

    def _manual_prerequisites(self) -> None:
        """Steps the tool cannot perform, surfaced before anything is executed."""
        assets = self.inventory.get("assets") or {}
        providers = assets.get("modelProviders") or []
        if any((provider.get("auth") or {}).get("mode") == "managedIdentity" for provider in providers):
            self.prerequisites.append({
                "id": "prereq:foundry-rbac",
                "owner": "azure-administrator",
                "summary": "Grant the gateway identity data-plane access on each Foundry account",
                "detail": "A provider using ManagedIdentity needs a role assignment on the backend account. "
                          "Role assignments are outside the gateway resource provider.",
            })
        self.prerequisites.append({
            "id": "prereq:caller-rbac",
            "owner": "azure-administrator",
            "summary": "Assign callers AI Gateway Models User / Tools User at the right scope",
            "detail": "A management role such as Contributor does not imply runtime invocation access.",
        })
        if assets.get("mcpServers"):
            if any(
                ((endpoint.get("credentials") or {}) or {}) for server in assets["mcpServers"]
                for endpoint in (server.get("upstream") or [])
            ):
                self.prerequisites.append({
                    "id": "prereq:mcp-oauth",
                    "owner": "operator",
                    "summary": "Complete OAuth authorization for tool-server sources interactively",
                    "detail": "`mcp authorize` returns a login link; completion is interactive and the "
                              "command's success does not prove the connection works.",
                })
        self.prerequisites.append({
            "id": "prereq:name-collision",
            "owner": "apim-import",
            "summary": "Preflight the target name against Microsoft.ApiManagement/service",
            "detail": "Several CLI commands dispatch by name without --ids, and in a migration the source "
                      "APIM and the target gateway plausibly share a name.",
        })

    # ------------------------------------------------------------- merge

    def _merge_with_previous(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        prior = {item["id"]: item for item in (self.previous.get("items") or [])}
        merged: list[dict[str, Any]] = []
        current_ids = {item["id"] for item in items}
        for item in items:
            item["shapeDigest"] = _shape_digest(item)
            item["memberDigests"] = _member_digests(item)
            before = prior.get(item["id"])
            if not before or before.get("status") not in {ADAPTED, STALE}:
                merged.append(item)
                continue
            # Preserve a settled decision unless the facts it rested on moved.
            changed = [
                key for key, value in (before.get("memberDigests") or {}).items()
                if key in item["memberDigests"] and item["memberDigests"][key] != value
            ]
            shape_changed = before.get("shapeDigest") != item["shapeDigest"]
            item["decision"] = before.get("decision")
            item["decidedAt"] = before.get("decidedAt")
            # Recorded by the generator, not by whoever adapts the item: adapting
            # means setting `status` and `decision`, nothing more.
            item["decidedAgainst"] = {
                "shape": before.get("shapeDigest"),
                "members": before.get("memberDigests") or {},
            }
            if changed or shape_changed:
                item["status"] = STALE
                item["staleReason"] = (
                    "The options for this item changed." if shape_changed
                    else f"Source facts changed for: {', '.join(sorted(changed))}."
                )
            else:
                item["status"] = ADAPTED
                new_members = sorted(set(item["memberDigests"]) - set(before.get("memberDigests") or {}))
                if new_members:
                    # Joining a settled batch inherits its decision; flag, do not re-open.
                    item["newMembers"] = new_members
            merged.append(item)

        orphaned = [
            {
                "id": item["id"],
                "kind": item.get("kind"),
                "assetId": (item.get("source") or {}).get("assetId"),
                "aspect": (item.get("source") or {}).get("aspect"),
                "decision": item.get("decision"),
                "note": (
                    "This decision was settled against an item that no longer exists -- usually "
                    "because the mapping rules changed its shape. Re-apply it to the item that "
                    "replaced it, or confirm it is no longer needed."
                ),
            }
            for item in (self.previous.get("items") or [])
            if item.get("status") in {ADAPTED, STALE} and item["id"] not in current_ids
        ]
        # Carry forward anything a previous run already flagged and nobody resolved.
        for entry in self.previous.get("orphanedDecisions") or []:
            if entry["id"] not in current_ids and entry["id"] not in {o["id"] for o in orphaned}:
                orphaned.append(entry)
        return merged, orphaned


# ---------------------------------------------------------------- helpers


def _opt(value: str, consequence: str) -> dict[str, str]:
    return {"value": value, "consequence": consequence}


def _loss_options(verdict: str) -> list[dict[str, str]]:
    if verdict != "gap":
        return []
    return [
        _opt("accept", "Migrate without it and accept the reduced posture."),
        _opt("compensate", "Replace it with a different control on the target."),
        _opt("retain-in-apim", "Keep this workload on APIM."),
        _opt("block", "Stop the migration until resolved."),
    ]


def _first(items: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    for item in items:
        if predicate(item):
            return item
    return None


def _match_kind(rule: dict[str, Any]) -> str:
    return (rule.get("match") or {}).get("kind") or ""


def _slug(value: str) -> str:
    return value.split(":", 1)[-1].replace("/", "-")


def _custom_auth(auth: dict[str, Any]) -> dict[str, Any]:
    """Custom provider authentication. The enum is ApiKey only in this baseline."""
    refs = auth.get("secretRefs") or []
    header = ((auth.get("parameters") or {}).get("header") or ["api-key"])[0]
    return {
        "kind": "ApiKey",
        "apiKey": {"headerName": header, "value": secret_ref(refs[0]) if refs else None},
    }


def _mcp_endpoints(server: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints = []
    for upstream in server.get("upstream") or []:
        if upstream.get("url"):
            endpoints.append({
                "kind": "mcp",
                "required": True,
                "mcp": {"url": upstream["url"], "transport": upstream.get("transport") or "streamableHttp"},
            })
    for source in server.get("openApiSources") or []:
        endpoints.append({
            "kind": "openApi",
            "required": True,
            "openApi": {"specSource": {"type": "url", "$fromExport": source.get("apiName")}},
        })
    return endpoints


# Sections and control flow wrap policy statements; anything else that wraps an
# element makes that element its configuration, not a policy of its own.
_STATEMENT_WRAPPERS = {"inbound", "backend", "outbound", "on-error", "fragment", "choose", "when", "otherwise"}


def _is_policy_statement(element: dict[str, Any]) -> bool:
    """True for a policy statement, false for a policy's configuration children.

    ``<set-header><value>…</value></set-header>`` is one decision, not two: the
    ``<value>`` child is how the header is configured. Walking it separately
    produced phantom items named after configuration elements.
    """
    ancestors = [segment.split("[", 1)[0] for segment in (element.get("path") or "").split("/")[:-1]]
    return all(name in _STATEMENT_WRAPPERS for name in ancestors)


def _apply_partial_when(rule: dict[str, Any], element: dict[str, Any]) -> dict[str, Any]:
    """Demote a native mapping to partial only when the rule's condition holds.

    A token limit maps natively; it becomes a decision only because its caller
    partition is an expression APIM evaluates and the target cannot.
    """
    condition = rule.get("partialWhen")
    if not condition:
        return rule
    attribute = condition.get("attributeIsExpression")
    value = (element.get("attributes") or {}).get(attribute or "")
    if not (isinstance(value, str) and value.lstrip().startswith("@")):
        return rule
    return {**rule, "verdict": "partial", **(rule.get("partial") or {})}


# APIM attribute -> target policy field, for the mappings that are direct.
_POLICY_FIELDS: dict[str, dict[str, str]] = {
    "tokenLimit": {"tokens-per-minute": "count", "counter-key": "counterKey"},
    "requestRateLimit": {"calls": "callsPerPeriod", "renewal-period": "periodSeconds",
                         "counter-key": "counterKey"},
    "ipFilter": {"action": "action"},
}

# Target policies whose configuration lives in child elements, so attributes
# alone cannot complete the object.
_POLICY_NEEDS_CHILDREN = {"ipFilter"}


def _policy_target(rule: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape the target policy object, and say when it is not complete.

    ipFilter keeps its CIDR ranges in ``<address-range>`` children, so the
    attributes alone do not finish the object. Saying so beats emitting a
    plausible-looking policy with no ranges in it.
    """
    target_type = rule.get("target")
    if not target_type or rule["verdict"] == "gap":
        return {}
    mapping = _POLICY_FIELDS.get(target_type, {})
    first = members[0] if members else {}
    settings = {
        field: first.get("attributes", {}).get(attribute)
        for attribute, field in mapping.items()
        if first.get("attributes", {}).get(attribute) is not None
    }
    complete = bool(settings) and target_type not in _POLICY_NEEDS_CHILDREN
    return {
        "capability": rule.get("capabilityId"),
        "objects": [{
            "type": target_type,
            "settings": settings,
            "configurationComplete": complete,
            "fullConfigurationAt": {"policyId": first.get("policyId"), "path": first.get("path")},
        }],
    }


def _policy_signature(element: dict[str, Any], rule: dict[str, Any], has_expression: bool) -> str:
    """Items of the same kind and shape batch into one.

    Only attributes the rule says are decision-relevant take part: two token
    limits with different ceilings but the same counter key are one decision
    about partitioning, not two.
    """
    batch_on = rule.get("batchOn")
    attributes = element.get("attributes") or {}
    relevant = {key: attributes.get(key) for key in batch_on} if batch_on else {}
    return digest({
        "element": element["name"], "verdict": rule["verdict"],
        "kind": rule.get("itemKind"), "expression": has_expression, "attributes": relevant,
    })[7:19]


def _shape_digest(item: dict[str, Any]) -> str:
    """What makes an answer valid: the question and the choices, not the wording."""
    return digest({
        "kind": item["kind"], "verdict": item["verdict"],
        "capabilityId": item["capabilityId"],
        "options": sorted(option["value"] for option in item["options"]),
    })


def _member_digests(item: dict[str, Any]) -> dict[str, str]:
    """Per-member source facts, so one changed member does not unsettle the rest."""
    members = (item.get("evidence") or {}).get("members")
    if isinstance(members, list) and members:
        return {
            f"{member.get('policyId')}#{member.get('path')}": digest(member)
            for member in members
        }
    return {item["source"].get("assetId") or item["id"]: digest(item.get("evidence") or {})}


def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    unsettled = [item for item in items if item["status"] in {NEEDS_DECISION, STALE}]
    return {
        "total": len(items),
        "byStatus": counts,
        "unsettled": len(unsettled),
        "blocking": sum(1 for item in unsettled if item.get("blocking")),
        "byKind": _tally(unsettled, "kind"),
    }


def _tally(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = item.get(field) or "none"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_plan(
    inventory: dict[str, Any],
    capabilities: CapabilityMap,
    *,
    previous: dict[str, Any] | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    return PlanBuilder(inventory, capabilities, previous=previous, target=target).build()
