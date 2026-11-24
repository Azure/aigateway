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
import ipaddress
import json
from typing import Any

from . import ids
from . import policy as policy_mod
from .capability import CapabilityMap
from .detect import MCP_PATTERNS, dialect_target
from .dispatch import selector

SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"

# Every place the planner chooses a rule, declared where the choosing happens.
# `migrate_apim.compile` reads these to decide whether a rule in rules.json can
# ever be selected; see migrate_apim/dispatch.py for why they are not a separate
# list somewhere else.
MCP_BY_PATTERN = selector(
    "assets",
    selects="apim.apis[]",
    keys=("type", "pattern"),
    values={"pattern": MCP_PATTERNS},
    site="plan._mcp",
    reads=("verdict", "answer", "capabilityId", "proposal", "rationale", "options"),
)
# The tool list is its own object on the server, and both questions about it are
# asked of that object. `where: {toolDiscovery: "runtimeOnly"}` claimed to read
# `assets.mcpServers[].toolDiscovery`, which is a record and never equal to a
# string; what it compares is the `status` inside it.
MCP_BY_TOOL_DISCOVERY = selector(
    "assets",
    selects="apim.apis[].toolDiscovery",
    keys=("status",),
    values={"status": ("runtimeOnly",)},
    site="plan._mcp tool exposure",
    reads=("verdict", "answer", "proposal", "rationale", "options"),
)
AGENT_RULE = selector(
    "assets", selects="apim.apis[]", keys=("type",), values={"type": ("a2a",)},
    site="plan._agent",
    reads=("verdict", "answer", "proposal", "rationale", "options"),
)

# The decisions that used to be written here rather than in the file. Each names
# the object it judges by where that object lives, and `where` narrows which
# answer applies. One API raises six questions, and they are six paths rather
# than six invented labels: `ARCHITECTURE.md` has described `assets[]` as
# covering models and modelProviders since before any of it existed -- the rules
# it named (`modelsStatus`, `surfaceStatus`) appeared nowhere but the suite's
# example of a rule nothing selects.
#
# Each declares only the fields its own branch takes off the rule. A shared list
# would have excused the ones it does not: `options` on a rule whose site writes
# its own, `rationale` on one whose sentence is always composed from the asset.
# Both were there, and `rule-field-unread` could not see either.
PROVIDER_RULE = selector(
    "assets", selects="assets.modelProviders[]", site="plan._provider",
    reads=("verdict", "answer", "capabilityId"),
)
SURFACE_BY_STATUS = selector(
    "assets", selects="apim.apis[].endpoints.surface", keys=("status",),
    values={"status": ("unbounded",)},
    site="plan._model surface",
    reads=("verdict", "answer", "capabilityId", "proposal", "rationale", "options", "blocking"),
)
SURFACE_PARTIALLY_PUBLISHABLE = selector(
    "assets", selects="apim.apis[].endpoints.surface", keys=("unpublishableCount",),
    site="plan._model surface partial",
    reads=("verdict", "answer", "capabilityId", "proposal", "options", "blocking"),
)
# Two cases, two sites: the indeterminate one proposes nothing, and one selector
# for both would have excused a `proposal` on it that the planner never reads.
DIALECT_TRANSLATING = selector(
    "assets", selects="apim.apis[].endpoints.translation", keys=("status",),
    values={"status": ("translating",)},
    site="plan._model dialect translating",
    reads=("verdict", "answer", "capabilityId", "proposal", "rationale", "options", "blocking"),
)
DIALECT_INDETERMINATE = selector(
    "assets", selects="apim.apis[].endpoints.translation", keys=("status",),
    values={"status": ("indeterminate",)},
    site="plan._model dialect indeterminate",
    reads=("verdict", "answer", "capabilityId", "rationale", "options", "blocking"),
)
SESSION_AFFINITY_RULE = selector(
    "assets", selects="apim.apis[].routing.sessionAffinity", site="plan._pool_affinity",
    reads=("verdict", "answer", "capabilityId", "proposal", "options"),
)
CATALOGUE_RULE = selector(
    "assets", selects="apim.apis[].models", keys=("discoverySource", "catalogue"),
    values={"discoverySource": ("modelsEndpoint",)},
    site="plan._enumerate_models",
    reads=("verdict", "answer", "capabilityId", "proposal", "rationale", "options", "blocking"),
)
MODEL_REGISTRATION_RULE = selector(
    "assets", selects="apim.apis[].models.resolved[]", site="plan._model_registration",
    reads=("verdict", "answer", "capabilityId"),
)
# The API itself, because an alias name is the one thing about it that APIM does
# not hold anywhere: it arrives in the request body, so every model needs one.
ALIAS_NAMES_RULE = selector(
    "assets", selects="apim.apis[]", keys=("role",), values={"role": ("modelApi",)},
    site="plan._alias_naming",
    reads=("verdict", "answer", "capabilityId", "proposal", "rationale", "options"),
)
# `policiesBypassed: true` used to say this, which a reader had to negate: what
# it tested was `policiesApplied is False`, a plain equality on a real field.
TOOL_EXPOSURE_BYPASSED = selector(
    "assets", selects="apim.apis[].toolDiscovery", keys=("policiesApplied",),
    values={"policiesApplied": (False,)},
    site="plan._mcp tool exposure bypassed",
    reads=("verdict", "answer", "proposal", "options"),
)

# `_structural` is six branches, not one. They share a key and nothing else:
# each raises a different item and takes a different set of fields off its rule.
# One selector for all six would have to declare the union of what they read,
# which would excuse a field on the workspace rule because the telemetry branch
# happens to read it. So each branch declares its own.
def _structural_selector(path: str, site: str, *, reads: tuple[str, ...]) -> Any:
    return selector(
        "structural", selects=path, site=f"plan._structural {site}", reads=reads,
    )


_DECIDED = ("verdict", "answer", "proposal", "rationale", "options")
STRUCTURAL_WORKSPACE = _structural_selector("apim.workspaces[]", "workspace", reads=_DECIDED)
STRUCTURAL_SUBSCRIPTIONS = _structural_selector(
    "apim.subscriptions", "subscriptions", reads=_DECIDED,
)
STRUCTURAL_TELEMETRY = _structural_selector(
    "apim.loggers", "telemetry", reads=(*_DECIDED, "capabilityId", "prerequisiteWhen"),
)
STRUCTURAL_CERTIFICATES = _structural_selector(
    "apim.certificates", "certificates",
    reads=("verdict", "answer", "proposal", "rationale"),
)
STRUCTURAL_CREDENTIAL_PROVIDERS = _structural_selector(
    "apim.authorizationProviders", "authorizationProviders",
    reads=("verdict", "answer", "proposal", "rationale"),
)
STRUCTURAL_COVERAGE_GAP = _structural_selector(
    "collection.coverage[]", "coverageGap",
    reads=("verdict", "answer", "rationale", "options", "blocking", "cannotAccept"),
)
IDENTITY_RULE = selector(
    "structural", selects="service.identity", keys=("userAssignedIdentities",),
    site="plan._identity",
    reads=("verdict", "answer", "capabilityId", "proposal", "options"),
)
REACHABILITY_BY_SUBNET = selector(
    "structural", selects="service.networking.targetRequirement", keys=("needsSubnet",),
    values={"needsSubnet": (True, False)},
    site="plan._structural backendReachability", reads=(*_DECIDED, "capabilityId"),
)

# Five cases of one object, so this site dispatches on a second key. The gateway
# has no policy composition at all -- no fragments, no includes, no inheritance
# -- so every fragment has the same fate, dissolved into whatever includes it,
# and what varies is only whether the dissolution can keep what the fragment
# meant. A fragment is a policy document like any other, which is why the path
# is `policies[]`: what makes it one is `scope.level`, and `graph.fragments()`
# is where that filter lives.
FRAGMENT_DISPOSITIONS = ("dissolved", "conditional", "splitSection", "unreferenced", "unresolved")
STRUCTURAL_POLICY_FRAGMENTS = selector(
    "structural", selects="apim.policies[]", keys=("disposition",),
    values={"disposition": FRAGMENT_DISPOSITIONS},
    computed=("disposition",),
    site="plan._policy_fragments",
    reads=(*_DECIDED, "blocking", "cannotAccept"),
)

READY = "ready"
NEEDS_DECISION = "needs-decision"
ADAPTED = "adapted"

# The one item that decides where gateway telemetry reports.
_TELEMETRY_ITEM = "item:telemetry/destination"
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
        # What became of every policy element walked, one bucket each.
        self.policy_coverage: dict[str, int] = {}
        self.unrecognised_policies: list[dict[str, Any]] = []
        self._graph: policy_mod.PolicyGraph | None = None
        self._policy_index: dict[str, dict[str, Any]] = {}
        # `fragment-id`s the selected assets reach and nothing resolves, and
        # what did resolve, by the route it arrived on.
        self._unresolved_fragments: list[str] = []
        self._unreadable_fragments: list[str] = []
        self._fragment_arrivals: dict[str, list[dict[str, Any]]] = {}
        # A model API names the backend it routes to; the provider asset built
        # from that backend is what knows the protocol it speaks.
        self._provider_by_backend: dict[str, dict[str, Any]] = {
            (provider.get("origin") or {}).get("backendId"): provider
            for provider in (inventory.get("assets") or {}).get("modelProviders") or []
            if (provider.get("origin") or {}).get("backendId")
        }

    def _settled(self, item_id: str) -> dict[str, Any] | None:
        """The decision a previous run settled for this item, as a mapping.

        Generation reads settled decisions, not just the merge step, because
        some of them carry the facts the target objects are built from. A
        `list-models` decision names models that exist nowhere in APIM; reading
        it only at merge time preserved the answer and built nothing from it.
        """
        for prior in self.previous.get("items") or []:
            if prior.get("id") != item_id:
                continue
            if prior.get("status") not in {ADAPTED, STALE}:
                return None
            decision = prior.get("decision")
            if decision is None:
                return None
            return decision if isinstance(decision, dict) else {"value": decision}
        return None

    def _settled_value(self, item_id: str) -> Any:
        """The scalar a previous run settled, for an item answered with one."""
        settled = self._settled(item_id)
        return settled.get("value") if settled else None

    # ------------------------------------------------------------- build

    def build(self) -> dict[str, Any]:
        assets = self.inventory.get("assets") or {}
        self._gateway()
        self._identity()
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
        self._check_buildable(merged)
        self._check_produces(merged)
        self._check_supplied(merged)
        self._note_unmapped(merged)
        self._mark_by_hand(merged)
        # Defects in this tool, not decisions for the operator. They are carried
        # on the plan so that whoever reads it sees work that will not happen,
        # rather than discovering it when a phase produces nothing.
        planner_gaps = [
            {"id": item["id"], "gap": item["plannerGap"]}
            for item in merged if item.get("plannerGap")
        ] + [
            {"id": item["id"], "gap": item["unbuildable"]["note"]}
            for item in merged if item.get("unbuildable")
        ]
        service = self.inventory.get("service") or {}
        return {
            "$schema": "https://github.com/Azure/aigateway/tools/migrate-apim/schemas/plan.schema.json",
            "schemaVersion": SCHEMA_VERSION,
            "kind": "apimMigrationPlan",
            "generator": {"name": "migrate-apim", "version": GENERATOR_VERSION, "command": "plan"},
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
            "summary": {
                **_summarize(merged),
                "orphanedDecisions": len(orphaned),
                "plannerGaps": len(planner_gaps),
            },
            "prerequisites": self.prerequisites,
            # What became of every policy element the inventory holds. The
            # dispositions are exclusive and `walked` is their sum, so a reader
            # can check the planner against the inventory instead of trusting
            # that an element which raised no item was one that needed none.
            "policyCoverage": {
                "walked": sum(self.policy_coverage.values()),
                "dispositions": dict(sorted(self.policy_coverage.items())),
                "unrecognised": self.unrecognised_policies,
            },
            "plannerGaps": planner_gaps,
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
            # Three options are written below, so whatever the rule asked for,
            # this one is answered by picking one of them.
            item["kind"] = "choose"
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
                "No options are defined for this item; the generic set is offered instead. "
                "The mapping rule should name the real choices."
            )
        self.items.append(item)
        return item

    def _gateway(self) -> None:
        """The target gateway itself, created by apply when it is not there yet.

        Region follows the source unless the operator says otherwise; a gateway in
        a different region to its backends pays for every call.
        """
        if not self.target:
            return
        service = self.inventory.get("service") or {}
        self._add(
            item_id=ids.item("gateway", "create"),
            source={"assetId": None, "assetKind": "gateway", "aspect": "create"},
            kind=None,
            verdict="native",
            capability_id="gateway.create",
            rationale=(
                f"Creates the target gateway in {service.get('location')}, following the source's "
                "region so model and tool traffic does not cross one."
            ),
            evidence={"targetResourceId": self.target, "sourceLocation": service.get("location")},
            target={
                "capability": "gateway.create",
                "objects": [{"name": self.target.rstrip("/").rsplit("/", 1)[-1],
                             "location": service.get("location")}],
            },
        )

    def _identity(self) -> None:
        """Give the gateway an identity when any provider authenticates as one.

        Every Foundry provider is registered with ``authentication.kind:
        ManagedIdentity``, so without this step the gateway would be configured
        to authenticate as a principal that does not exist, and the RBAC
        prerequisite would have nothing to grant to.

        Which identity is a real decision. A user-assigned identity carried over
        from the source already holds its grants on the backend accounts, so
        reusing it turns the RBAC prerequisite into a no-op; a fresh
        system-assigned identity is a new principal that must be granted access
        before any model call succeeds.
        """
        providers = (self.inventory.get("assets") or {}).get("modelProviders") or []
        needed = [p for p in providers if (p.get("auth") or {}).get("mode") == "managedIdentity"]
        if not needed:
            return
        identity = (self.inventory.get("service") or {}).get("identity") or {}
        assigned = identity.get("userAssignedIdentities") or []
        rule = IDENTITY_RULE.first(
            self.caps.structural_rules(), userAssignedIdentities=assigned
        ) or {}
        # Taking a new principal is the choice that exists either way, so the
        # rule states it; reusing one is an option per identity this source
        # carries, which only the inventory can enumerate.
        options = _options_of(rule)
        for entry in assigned:
            options.append(_opt(
                f"reuse:{entry['resourceId']}",
                "Carries the grants this identity already holds on the backends.",
            ))
        proposal = f"reuse:{assigned[0]['resourceId']}" if assigned else rule.get(
            "proposal", "system-assigned")
        self._add(
            item_id=ids.item("identity", "assign"),
            source={"assetId": None, "assetKind": "identity", "aspect": "gatewayIdentity"},
            kind=rule.get("answer"),
            verdict=rule.get("verdict", "partial" if assigned else "native"),
            capability_id=rule.get("capabilityId", "identity.assign"),
            proposal=proposal,
            rationale=(
                f"{len(needed)} provider(s) authenticate as a managed identity, so the gateway needs "
                "one. " + (
                    "The source uses a user-assigned identity that already holds its backend grants; "
                    "reusing it avoids making them again."
                    if assigned else
                    "The source uses a system-assigned identity, whose principal cannot be carried "
                    "over, so the target gets its own and the backend grants must be made against it."
                )
            ),
            # Nothing is offered without a user-assigned identity to reuse, and
            # that is now the rule for that case saying so rather than a guard
            # here: its verdict is native and it carries no options.
            options=options,
            evidence={
                "sourceIdentity": identity,
                "providers": [p["id"] for p in needed],
                "audiences": sorted({(p.get("auth") or {}).get("identity", {}).get("audience")
                                     for p in needed if (p.get("auth") or {}).get("identity")}),
            },
            target={
                "capability": "identity.assign",
                "objects": [{"systemAssigned": not assigned,
                             "userAssigned": [e["resourceId"] for e in assigned] or None}],
            },
        )

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
        rule = PROVIDER_RULE.first(self.caps.asset_rules()) or {}
        self._add(
            item_id=ids.item("modelProvider", provider["id"]),
            source={"assetId": provider["id"], "assetKind": "modelProvider", "aspect": "registration"},
            kind=rule.get("answer"),
            verdict=rule.get("verdict", "native"),
            capability_id=rule.get("capabilityId", "provider.create"),
            # Named after this provider, so the sentence is built here. The rule
            # states the mapping as a note rather than a rationale: a rationale
            # it carried would never reach an item, which is the kind of dead
            # field `reads` exists to expose.
            rationale=(f"{provider.get('providerLabel') or provider.get('providerKind')} provider "
                       "registers directly."),
            evidence={"endpoint": provider.get("endpoint"), "authMode": auth.get("mode")},
            target={"capability": "provider.create", "objects": [objects]},
        )

    def _model(self, model: dict[str, Any]) -> None:
        asset_id = model["id"]
        endpoints = model.get("endpoints") or {}
        surface = endpoints.get("surface") or {}
        models = model.get("models") or {}
        self._pool_affinity(model)

        # Scope: how much of what this API publishes can move at all.
        if surface.get("status") == "unbounded":
            rule = SURFACE_BY_STATUS.first(self.caps.asset_rules(), status="unbounded") or {}
            self._add(
                item_id=ids.item(asset_id, "surface"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "publishedSurface"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                # The collector's note says which wildcards made it unreadable;
                # the rule's sentence is the one that holds without them.
                rationale=surface.get("note") or rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"surface": surface},
                blocking=rule.get("blocking", True),
            )
        elif surface.get("unpublishableCount"):
            groups = ", ".join(
                f"{entry['group']} x{entry['count']}" for entry in surface.get("unpublishable", [])
            )
            rule = SURFACE_PARTIALLY_PUBLISHABLE.first(
                self.caps.asset_rules(),
                unpublishableCount=surface.get("unpublishableCount"),
            ) or {}
            self._add(
                item_id=ids.item(asset_id, "surface"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "publishedSurface"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                rationale=(
                    f"{surface['publishableCount']} of {surface['operationCount']} operations map to the "
                    f"four publishable routes. No target for: {groups}."
                ),
                # What `split` costs is this API's number of left-behind
                # operations, so that one sentence is built here.
                options=_options_of(rule, {
                    "split": f"Inference moves; {surface['unpublishableCount']} operations stay on APIM.",
                }),
                evidence={"surface": surface},
                blocking=rule.get("blocking", True),
            )

        # Models: a registration needs a model name.
        if models.get("status") in {"unresolved", "empty", "catalogued"}:
            registrations = self._enumerate_models(model, models)
        else:
            registrations = models.get("resolved") or []
        for resolved in registrations:
            self._model_registration(model, resolved)
        if registrations:
            self._alias_naming(model, registrations)

        # Dialect translation.
        translation = endpoints.get("translation") or {}
        if translation.get("status") == "translating":
            rule = DIALECT_TRANSLATING.first(self.caps.asset_rules(), status="translating") or {}
            self._add(
                item_id=ids.item(asset_id, "dialect"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "callerDialect"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                rationale=translation.get("note") or rule.get("rationale", ""),
                # Moving the callers costs them the dialect this backend
                # speaks, which is read off the asset rather than stated once.
                options=_options_of(rule, {
                    "move-callers": f"Callers move to {', '.join(translation.get('backend') or [])}.",
                }),
                evidence={"translation": translation},
                blocking=rule.get("blocking", True),
            )
        elif translation.get("status") == "indeterminate":
            rule = DIALECT_INDETERMINATE.first(
                self.caps.asset_rules(), status="indeterminate") or {}
            self._add(
                item_id=ids.item(asset_id, "dialect"),
                source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "callerDialect"},
                kind=rule.get("answer", "supply"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId"),
                rationale=translation.get("note") or rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"translation": translation},
                blocking=rule.get("blocking", True),
            )

    def _pool_affinity(self, model: dict[str, Any]) -> None:
        """Session affinity on an APIM pool, which this tool cannot reproduce.

        The gateway does have it -- an alias takes a `sessionBackendPreference`
        stage with a CEL key -- but `az aigateway model-alias set` exposes no
        flag for it, so a migration cannot carry it over. That is a gap in the
        tooling rather than in the target, and the difference matters: it is
        work to do by hand afterwards, not a workload that has to stay on APIM.

        Raised only when a pool actually uses it. Pools leave the field null by
        default, and an item per pool would be a question about nothing.
        """
        routing = model.get("routing") or {}
        affinity = routing.get("sessionAffinity")
        if not affinity:
            return
        entry = self.caps.service_only_entry("alias-session-affinity") or {}
        asset_id = model["id"]
        # The catalogue writes its own sentences; this one is a clause inside
        # someone else's.
        gap = (entry.get("cliGap") or "the installed CLI cannot author it").rstrip(". ")
        gap = gap[0].lower() + gap[1:] if gap else gap
        rule = SESSION_AFFINITY_RULE.first(self.caps.asset_rules()) or {}
        self._add(
            item_id=ids.item(asset_id, "sessionAffinity"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "sessionAffinity"},
            kind=rule.get("answer", "choose"),
            verdict=rule.get("verdict", "gap"),
            capability_id=rule.get("capabilityId", "alias.create"),
            proposal=rule.get("proposal", "accept-loss"),
            rationale=(
                "This API's backend pool pins a session to the backend that served it. The gateway "
                "supports the same idea on an alias (a `sessionBackendPreference` stage with a CEL "
                f"key), but {gap}, so this "
                "run cannot configure it. Without it, each request is routed independently and a "
                "session can move between backends mid-conversation."
            ),
            options=_options_of(rule),
            evidence={
                "apimSessionAffinity": affinity,
                "targetProperty": entry.get("property"),
                "authoring": entry.get("authoring"),
                "note": entry.get("evidence"),
                # Said plainly: the target has this, the tool cannot write it.
                "targetSupports": True,
            },
            blocking=True,
        )

    def _enumerate_models(
        self, model: dict[str, Any], models: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Ask which models a passthrough API exposes, and build them once answered.

        APIM does not record the catalogue behind a passthrough backend, so the
        models have to come from the provider's own catalogue endpoint or from
        the operator. Either way the answer lands in this item's decision, and
        generation has to read it back: nothing else in the inventory knows
        those models exist. Raising the question and ignoring the answer left a
        settled item that registered nothing, under a provider that published
        no models at all.
        """
        asset_id = model["id"]
        catalogue = models.get("catalogue") or []
        if catalogue:
            # The catalogue has been read, so nobody has to type names -- but it
            # lists what exists, not what each one can serve, and publishing a
            # model that cannot serve the route is a decision rather than a
            # detail. Confirming is one step; pruning is an edit to the same list.
            sample = ", ".join(str(name) for name in catalogue[:6])
            more = f" and {len(catalogue) - 6} more" if len(catalogue) > 6 else ""
            rule = CATALOGUE_RULE.first(self.caps.asset_rules(), catalogue=catalogue) or {}
            # Listing them costs nothing to say except how many there are, which
            # is this catalogue's count.
            options = _options_of(rule, {
                "list-models":
                    f"Publish the {len(catalogue)} the catalogue returned; drop any that cannot "
                    "serve an inference route by editing `decision.models`.",
            })
            proposal = rule.get("proposal", "list-models")
            rationale = (
                f"The catalogue at {models.get('resolvedFrom')} returned {len(catalogue)} model(s): "
                f"{sample}{more}. It states no modality, so whether each one serves an inference "
                "route is not established -- an image or speech model published here would fail at "
                "the upstream."
            )
        else:
            # A provider with a catalogue endpoint has an actionable default:
            # fetch it rather than ask someone to type model names. Which is
            # which is the rule's to say, so the two cases are two rules.
            rule = CATALOGUE_RULE.first(
                self.caps.asset_rules(), catalogue=catalogue,
                discoverySource=models.get("discoverySource"),
            ) or CATALOGUE_RULE.first(
                # The rule that pins no source, which is the one that answers
                # when this provider's is not one a rule names.
                self.caps.asset_rules(), catalogue=catalogue, discoverySource=None,
            ) or {}
            options = _options_of(rule)
            proposal = rule.get("proposal", "list-models")
            rationale = (" ".join(models.get("notes") or []) or rule.get("rationale", ""))

        item = self._add(
            item_id=ids.item(asset_id, "models"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "modelCatalogue"},
            kind=rule.get("answer", "supply"),
            verdict=rule.get("verdict", "partial"),
            capability_id=rule.get("capabilityId", "model.create"),
            proposal=proposal,
            rationale=rationale,
            options=options,
            evidence={
                "discoverySource": models.get("discoverySource"),
                "catalogue": catalogue,
                "notes": models.get("notes"),
            },
            blocking=rule.get("blocking", True),
        )

        decision = self._settled(item["id"])
        if not decision or decision.get("value") in {"retain-in-apim", "block", None}:
            return []
        names = [str(name).strip() for name in decision.get("models") or [] if str(name).strip()]
        if not names:
            # The decision settled on migrating but named nothing to migrate.
            # Silently registering nothing would read as a completed decision.
            item["plannerGap"] = (
                f"This item is settled as `{decision.get('value')}` but names no models, so "
                "nothing can be registered. Set `decision.models` to the model names, or "
                "choose `retain-in-apim`."
            )
            return []

        # Which routes each model serves is not in the decision, and a catalogue
        # does not carry it either -- the OpenAI `/v1/models` response has no
        # capabilities field. The provider's protocol is readable, and it fixes
        # the inference route; anything beyond that is per-model and left alone.
        provider = self._provider_by_backend.get(_backend_id(model)) or {}
        mapped = dialect_target(provider.get("apiDialect"))
        if not mapped:
            item["plannerGap"] = (
                f"{len(names)} model(s) were named, but the protocol of provider "
                f"`{provider.get('id') or _provider_name(model)}` could not be resolved "
                f"(apiDialect={provider.get('apiDialect')!r}), so neither apiFormat nor a route "
                "can be derived for them. This is a collector gap: the provider's dialect should "
                "be readable from its backend."
            )
            return []

        per_model = decision.get("endpoints") or {}
        item["derived"] = {
            "modelCount": len(names),
            "apiFormat": mapped["apiFormat"],
            "defaultEndpoints": mapped["supportedEndpoints"],
            "basis": (
                f"Protocol of {provider.get('id')} ({provider.get('apiDialect')}). Per-model route "
                "support is not readable from a catalogue; override in `decision.endpoints` "
                "keyed by model name."
            ),
        }
        return [
            {
                "modelName": name,
                "deploymentName": name,
                "enumerated": True,
                "target": {
                    "supportedEndpoints": [
                        str(route) for route in (per_model.get(name) or mapped["supportedEndpoints"])
                    ],
                    "apiFormat": mapped["apiFormat"],
                    # A Custom provider has no backing ARM deployment, so a
                    # registration carries the model name alone. Confirmed against
                    # a live gateway, whose Custom models read back as
                    # `deployment: {modelName: ...}` with no resourceId.
                    "deployment": {"modelName": name},
                },
            }
            for name in names
        ]

    def _model_registration(self, model: dict[str, Any], resolved: dict[str, Any]) -> None:
        asset_id = model["id"]
        name = resolved.get("deploymentName") or resolved.get("modelName") or "model"
        target = resolved.get("target") or {}
        endpoints = target.get("supportedEndpoints") or []
        # A pooled API has one registration per member that serves the model, so
        # the provider is the member this copy lives in -- not the API's first
        # target, which would file every member's models under one account.
        provider_name = (_slug(resolved["backendId"]) if resolved.get("backendId")
                         else _provider_name(model))
        # A gateway model is named within its provider, so two members may both
        # register `gpt-4o`. Only the plan item id has to tell them apart.
        pooled = len({r.get("backendId")
                      for r in (model.get("models") or {}).get("resolved") or []}) > 1
        item_key = f"model/{name}@{provider_name}" if pooled else f"model/{name}"
        registration_rule = MODEL_REGISTRATION_RULE.first(self.caps.asset_rules()) or {}
        self._add(
            item_id=ids.item(asset_id, item_key),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": f"model:{name}"
                    + (f"@{provider_name}" if pooled else "")},
            kind=registration_rule.get("answer"),
            verdict=registration_rule.get("verdict", "native"),
            capability_id=registration_rule.get("capabilityId", "model.create"),
            rationale=(
                f"Registers {resolved.get('modelName')} named in this API's model catalogue decision."
                if resolved.get("enumerated")
                else f"Registers {resolved.get('modelName')} from a resolved deployment."
            ),
            evidence={"modelName": resolved.get("modelName"), "modelVersion": resolved.get("modelVersion")},
            target={
                "capability": "model.create",
                "objects": [{
                    "name": _slug(name),
                    "providerName": provider_name,
                    # A resolved deployment implies its format from the routes it
                    # serves; an enumerated model carries the one its provider's
                    # protocol fixes, which the routes alone cannot distinguish.
                    "apiFormat": target.get("apiFormat") or _api_format(endpoints),
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
        # One alias per callable name, fronting every pool member that serves it.
        # A load-balanced API registers the same model once per account, and an
        # alias per registration would have published the name twice, each
        # pointing at one account -- the second quietly overwriting the first and
        # the pool's traffic split lost with it.
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in registrations:
            grouped.setdefault(
                str(entry.get("deploymentName") or entry.get("modelName")), []
            ).append(entry)

        members = [
            {
                "modelName": copies[0].get("modelName"),
                "proposedAliasName": alias_name,
                "supportedEndpoints": (copies[0].get("target") or {}).get("supportedEndpoints") or [],
                "backends": [
                    {
                        "providerName": (_slug(copy["backendId"]) if copy.get("backendId")
                                         else _provider_name(model)),
                        # APIM pools weight 0-1000 and the target takes 1-100, so
                        # a share is carried across only when it already fits.
                        "priority": copy.get("poolPriority") if copy.get("poolPriority") is not None else 0,
                        "weight": copy.get("poolWeight") if copy.get("poolWeight") is not None else 100,
                    }
                    for copy in copies
                ],
            }
            for alias_name, copies in grouped.items()
        ]
        sample = ", ".join(str(member["proposedAliasName"]) for member in members[:4])
        more = f" and {len(members) - 4} more" if len(members) > 4 else ""

        # A pooled API balances across members, but only a model deployed in
        # every member can actually be balanced. APIM splits traffic blind and
        # fails on the members that lack it; the gateway routes to where the
        # model is. That is better behaviour and a different one, so it is said
        # rather than left for someone to notice in production.
        pooled = max((len(m["backends"]) for m in members), default=1) > 1
        partial = [m["proposedAliasName"] for m in members if len(m["backends"]) == 1] if pooled else []
        balance = ""
        if pooled:
            balance = (
                f" This API load-balances across {max(len(m['backends']) for m in members)} backends; "
                "each alias carries the pool's priority and weight."
            )
            if partial:
                balance += (
                    f" {len(partial)} of them are deployed in only one member "
                    f"({', '.join(str(name) for name in partial[:3])}"
                    f"{'...' if len(partial) > 3 else ''}), so those route to that member alone "
                    "instead of being split."
                )
        rule = ALIAS_NAMES_RULE.first(self.caps.asset_rules(), role="modelApi") or {}
        self._add(
            item_id=ids.item(asset_id, "aliasNames"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "aliasNames"},
            kind=rule.get("answer", "supply"),
            verdict=rule.get("verdict", "partial"),
            capability_id=rule.get("capabilityId", "alias.create"),
            proposal=rule.get("proposal", "use-model-names"),
            # What an alias name is holds for every API, so it is said once in
            # the rule; which names are proposed is this API's models. The two
            # sentences were both written here, and the rule's copy was read by
            # nobody.
            rationale=" ".join(filter(None, [
                rule.get("rationale"),
                f"Proposed for {len(members)} model(s): {sample}{more}." + balance,
            ])),
            options=_options_of(rule),
            evidence={"members": members, "count": len(members),
                      "pooled": pooled, "singleMemberModels": partial},
            target={
                "capability": "alias.create",
                "objects": [
                    {
                        "routingName": member["proposedAliasName"],
                        "backendModels": [{
                            "modelName": _slug(str(member["proposedAliasName"])),
                            # Resolved against the gateway during the aliases
                            # phase: a model's ARM id is a runtime fact.
                            "providerName": backend["providerName"],
                            "resourceId": None,
                            "priority": backend["priority"],
                            "weight": backend["weight"],
                        } for backend in member["backends"]],
                        "supportedEndpoints": member["supportedEndpoints"],
                    }
                    for member in members
                ],
            },
        )

    def _mcp(self, server: dict[str, Any]) -> None:
        asset_id = server["id"]
        pattern = server.get("pattern")
        rule = MCP_BY_PATTERN.first(
            self.caps.asset_rules(), type="mcp", pattern=pattern
        )
        if rule:
            self._add(
                item_id=ids.item(asset_id, "registration"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "registration"},
                kind=rule.get("answer"),
                verdict=rule["verdict"],
                capability_id=rule.get("capabilityId"),
                proposal=rule.get("proposal"),
                rationale=rule.get("rationale")
                or f"A {pattern} MCP server registers as a tool server with its upstream endpoints.",
                options=_options_of(rule),
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
            bypass_rule = TOOL_EXPOSURE_BYPASSED.first(
                self.caps.asset_rules(),
                policiesApplied=discovery_record.get("policiesApplied"),
            ) or {}
            self._add(
                item_id=ids.item(asset_id, "tools"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "toolExposure"},
                kind=bypass_rule.get("answer", "supply"),
                verdict=bypass_rule.get("verdict", "partial"),
                proposal=bypass_rule.get("proposal", "accept-as-listed"),
                rationale=(
                    f"{discovery_record.get('discoveredCount')} tools were listed directly from the "
                    "upstream because the gateway route was unavailable, so the API's policies did "
                    "not run. APIM may be withholding some of these from callers today."
                ),
                options=_options_of(bypass_rule),
                evidence={"toolDiscovery": discovery_record,
                          "tools": [tool.get("name") for tool in server.get("tools") or []]},
                blocking=True,
            )
        if discovery == "runtimeOnly":
            tool_rule = MCP_BY_TOOL_DISCOVERY.first(
                self.caps.asset_rules(), status="runtimeOnly"
            ) or {}
            self._add(
                item_id=ids.item(asset_id, "tools"),
                source={"assetId": asset_id, "assetKind": "mcpServer", "aspect": "toolExposure"},
                kind=tool_rule.get("answer", "supply"),
                verdict=tool_rule.get("verdict", "gap"),
                proposal=tool_rule.get("proposal", "accept-all"),
                rationale=tool_rule.get("rationale", ""),
                options=_options_of(tool_rule),
                evidence={"toolDiscovery": server.get("toolDiscovery")},
            )

    def _agent(self, agent: dict[str, Any]) -> None:
        rule = AGENT_RULE.first(self.caps.asset_rules(), type="a2a") or {}
        self._add(
            item_id=ids.item(agent["id"], "registration"),
            source={"assetId": agent["id"], "assetKind": "agent", "aspect": "registration"},
            kind=rule.get("answer", "choose"),
            verdict=rule.get("verdict", "gap"),
            proposal=rule.get("proposal", "retain-in-apim"),
            rationale=rule.get("rationale", ""),
            options=_options_of(rule),
            evidence={"hosting": agent.get("hosting"), "agent": agent.get("agent")},
        )

    # ----------------------------------------------------------- policies

    def _policies(self) -> None:
        """One item per distinct policy treatment, batched across what it governs.

        Driven by what each asset's policy actually resolves to, rather than by
        walking policy documents as though every scope were one that runs. A
        fragment is not: read as a scope of its own it covered no API, so a
        policy an operator had factored out of four APIs reached none of them.
        Asking `policy.PolicyGraph` instead makes the fragment, the `<base />`
        an API omits, the operation scope and the workspace one question with
        one answer -- the same answer `collect` gets.

        Every element in the inventory still leaves a count behind, in
        `policyCoverage`, walked document by document. That walk is what keeps
        the tally a sum over the inventory rather than over whatever this
        happened to look at.
        """
        graph = self.graph()
        terminal = self.caps.terminal_policy_rule()
        # One entry per element per route it reaches an asset by. The route is
        # part of the key because a fragment included plainly by one API and
        # inside a `choose` by another is two different claims about the same
        # element, and the conditional one is not `handled`.
        governed: dict[tuple[int, bool], list[tuple[dict[str, Any], policy_mod.Occurrence]]] = {}
        for asset, api, workspace in self._policy_assets():
            reached = self._governing(graph, asset=asset, api=api, workspace=workspace)
            self._record_arrivals(asset["id"], reached)
            for occurrence in reached:
                # Keyed on the element itself, not on where it is written: the
                # graph hands back the record the inventory holds, so identity
                # is exact where a document-and-path pair only almost is.
                key = (id(occurrence.element), occurrence.under_conditional)
                governed.setdefault(key, []).append((asset, occurrence))

        batches: dict[str, dict[str, Any]] = {}
        dispositions: dict[int, str] = {}
        for (element_id, conditional), hits in governed.items():
            element = hits[0][1].element
            if not _is_policy_statement(element):
                continue
            has_expression = bool(element.get("expressionIds"))
            rule = self.caps.policy_rule(
                element["name"], family=element.get("family", ""), has_expression=has_expression
            )
            if not rule:
                # Unreachable while rules.json carries a terminal rule, and
                # counted rather than deleted because that is a property of
                # the data, which `compile` enforces and this does not.
                _note(dispositions, element_id, "unresolved")
                continue
            # Analysed before it is excluded, because `handled` is a claim
            # about the element and not every element it covers makes it
            # true. A backend chosen inside a `choose` was excluded on the
            # strength of an alias pool that holds the backends and not the
            # logic that picked among them, and left no trace in the plan.
            rule = _apply_partial_when(rule, element, under_conditional=conditional)
            if rule["verdict"] in {"notApplicable", "handled"}:
                _note(dispositions, element_id, rule["verdict"])
                continue
            # An unrecognised element still becomes an item -- it is counted
            # apart because reaching the terminal rule says the vocabulary
            # has grown, which is not the same as having been mapped.
            _note(dispositions, element_id,
                  "unrecognised" if rule is terminal else "classified")
            signature = _policy_signature(element, rule, has_expression)
            batch = batches.setdefault(signature, {"rule": rule, "element": element,
                                                    "hasExpression": has_expression, "members": []})
            for asset, occurrence in hits:
                batch["members"].append({
                    # Where the element is written, which is where an operator
                    # reads it, and what it governs, which is what carries it.
                    # Both, because a fragment is the first and never the second.
                    "policyId": occurrence.policy_id,
                    "scope": _level_of(self._policy_document(occurrence.policy_id)),
                    "scopeName": _name_of(self._policy_document(occurrence.policy_id)),
                    # The scope whose chain pulled this in, which is the asset's
                    # own or something wider. A fragment is never either, so
                    # asking the document the element is written in made
                    # extracting a policy into a fragment change the answer.
                    "governedAt": occurrence.site_level,
                    "governedBy": occurrence.site_policy_id,
                    # The includes traversed. Part of the member's identity,
                    # because one API can include one fragment twice and those
                    # are two members with everything else in common -- keyed
                    # without it, one overwrote the other's digest and adding a
                    # third include left the decision reading as unchanged.
                    "arrival": list(occurrence.arrival),
                    "path": occurrence.path,
                    "assetId": asset["id"],
                    "section": occurrence.section,
                    "via": list(occurrence.via),
                    "underConditional": occurrence.under_conditional,
                    "element": element["name"],
                    "attributes": element.get("attributes") or {},
                })

        self._count_policy_coverage(dispositions, {key for key, _ in governed})

        for signature, batch in sorted(batches.items()):
            rule = batch["rule"]
            element = batch["element"]
            members = batch["members"]
            self._add(
                item_id=ids.item("policy", signature),
                source={"assetId": None, "assetKind": "policy", "aspect": element["name"]},
                kind=rule.get("answer", "choose"),
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
                options=_options_of(rule) or _loss_options(rule["verdict"]),
                evidence={
                    "element": element["name"],
                    "target": rule.get("target"),
                    "hasExpression": batch["hasExpression"],
                    "occurrences": len(members),
                    "members": members,
                },
                target=self._policy_target(
                    rule, members, item_id=ids.item("policy", signature)),
                blocking=rule["verdict"] == "gap",
            )

    def _policy_fragments(self, structural: list[dict[str, Any]]) -> None:
        """What became of each policy fragment, said once per fragment.

        AI Gateway has no policy composition: not fragments, not includes, not
        inheritance. So a fragment has one fate -- dissolved into every scope
        that includes it -- and the only question is whether the dissolution
        keeps what the fragment meant. An item per fragment is what makes that
        answerable without reading the policies it contributed and working
        backwards.
        """
        graph = self.graph()
        # A fragment that could not be read contributes no elements, so it
        # arrives nowhere and would read as one nothing includes. What says
        # otherwise is the forward walk, which records the name it could not
        # resolve where it tried to resolve it.
        unreadable = set(self._unreadable_fragments)
        for document in graph.fragments():
            name = (document.get("scope") or {}).get("name") or ""
            sites = _unique_arrivals(self._fragment_arrivals.get(document["id"]) or [])
            sections = {site["section"] for site in sites}
            if document["id"] in unreadable:
                # Collected, included, and unreadable. It has no elements to
                # dissolve and nobody can say what it carried, so it is the
                # same unknown as a `fragment-id` naming nothing -- and a
                # dissolution reported as clean would be the stronger claim of
                # the two that is false.
                disposition = "unresolved"
            elif not sites:
                disposition = "unreferenced"
            elif any(site["underConditional"] for site in sites):
                disposition = "conditional"
            elif len(sections) > 1:
                disposition = "splitSection"
            else:
                disposition = "dissolved"
            rule = STRUCTURAL_POLICY_FRAGMENTS.first(
                structural, disposition=disposition
            ) or {}
            self._add(
                item_id=ids.item("fragment", document["id"]),
                source={"assetId": document["id"], "assetKind": "policyFragment", "aspect": name},
                kind=rule.get("answer"),
                verdict=rule.get("verdict", "handled"),
                proposal=rule.get("proposal"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={
                    "fragment": name,
                    "disposition": disposition,
                    "elementCount": len(document.get("elements") or []),
                    "parseError": document.get("parseError"),
                    "sections": sorted(sections),
                    # Whether operation policies were collected decides what
                    # "nothing includes it" is worth: an operation can include a
                    # fragment, and those documents are read only when asked for.
                    "operationPoliciesCollected": self._operation_policies_collected(),
                    "includedBy": sites,
                },
                blocking=rule.get("blocking", False),
                cannot_accept=rule.get("cannotAccept", False),
            )

        # From what the selected assets actually resolve to, not from every
        # include reference in the inventory. An unreferenced fragment naming a
        # missing one governs nothing, and blocking a migration on it would be
        # a decision about a workload nobody is moving.
        # Every reference that resolved to no document at all. A fragment this
        # inventory holds but could not read is reported on its own item,
        # above, and is tracked by document rather than by name so that an `hr`
        # API naming `limits` when only `finance/limits` exists is still
        # reported here -- the two are not the same fragment, and matching them
        # by name left the unknown policy unmentioned.
        for missing in sorted(set(self._unresolved_fragments)):
            rule = STRUCTURAL_POLICY_FRAGMENTS.first(
                structural, disposition="unresolved"
            ) or {}
            self._add(
                item_id=ids.item("fragment", f"unresolved/{missing}"),
                source={"assetId": None, "assetKind": "policyFragment", "aspect": missing},
                kind=rule.get("answer", "supply"),
                verdict=rule.get("verdict", "gap"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"fragment": missing, "disposition": "unresolved"},
                blocking=rule.get("blocking", True),
                cannot_accept=rule.get("cannotAccept", True),
            )

    def _operation_policies_collected(self) -> bool:
        options = (self.inventory.get("collection") or {}).get("options") or {}
        return bool(options.get("operationPolicies"))

    def graph(self) -> policy_mod.PolicyGraph:
        """Which policy governs which API, asked the same way `collect` asks it.

        Built from the inventory alone: inclusion and inheritance are already
        elements in the documents, so this needs no field the collector does
        not write and no second walk to re-derive them.
        """
        if self._graph is None:
            self._graph = policy_mod.PolicyGraph(
                (self.inventory.get("apim") or {}).get("policies") or [],
                products=(self.inventory.get("apim") or {}).get("products") or [],
            )
        return self._graph

    def _record_arrivals(self, asset_id: str, occurrences) -> None:
        """What reached one asset through a fragment, and how.

        Taken from the resolution rather than from the include references in
        the documents, because a reference is not an arrival: one written in a
        policy every migrated API overrides, or on an API this migration
        excludes, names a fragment that governs nothing here. Reading them
        syntactically raised decisions -- and blocking ones -- about workloads
        nobody is moving.
        """
        for occurrence in occurrences:
            for fragment_id in occurrence.via:
                self._fragment_arrivals.setdefault(fragment_id, []).append({
                    "assetId": asset_id,
                    "policyId": occurrence.site_policy_id,
                    "scopeLevel": occurrence.site_level,
                    "section": occurrence.section,
                    "via": list(occurrence.via),
                    "underConditional": occurrence.under_conditional,
                })

    def _governing(self, graph, *, asset, api, workspace):
        """Everything that runs for one API, its own operations included.

        An operation is a scope of its own, and the chain only reaches it when
        asked. Left out, an operation-scoped token limit raised no item at all
        and was counted as governing nothing -- a quieter version of the
        stranding this change exists to end.

        Which resolution answers depends on whether the operations speak for
        all of the API's traffic. When every operation carries a policy of its
        own, each is resolved through the whole chain and the API's own
        resolution is not added: an operation that omits `<base />` overrides
        what is above it, and taking the API's resolution anyway would report a
        limit on traffic nothing applies it to -- and could block a migration
        on a fragment no request reaches. Otherwise some traffic arrives at an
        operation with no policy, which inherits, so the API's resolution is
        what governs it and the operations add only their own elements.
        """
        declared = [
            operation.get("name")
            for operation in ((asset.get("endpoints") or {}).get("operations") or [])
            if operation.get("name")
        ]
        with_policy = graph.operations_of(api=api, workspace=workspace)
        covered = bool(declared) and set(declared) <= set(with_policy)

        occurrences: list[policy_mod.Occurrence] = []

        def take(resolution: policy_mod.Resolution) -> None:
            occurrences.extend(resolution.occurrences)
            self._unresolved_fragments.extend(resolution.unresolved_fragments)
            self._unreadable_fragments.extend(resolution.unreadable_fragments)

        if not covered:
            take(graph.governing(api=api, workspace=workspace))
        for operation in with_policy:
            take(graph.governing(
                api=api, workspace=workspace, operation=operation,
                levels=policy_mod.SCOPE_CHAIN if covered else ("operation",),
            ))
        # Several operations inherit the same scopes above them, and each
        # resolution returns that inheritance in full. Without this the API's
        # own elements would be one member per operation, and the policy would
        # be applied -- and counted -- once for each.
        return policy_mod.unique_occurrences(occurrences)

    def _policy_assets(self):
        """The assets a policy can govern, with the source API each came from."""
        assets = self.inventory.get("assets") or {}
        for kind in ("models", "mcpServers", "agents"):
            for asset in assets.get(kind) or []:
                yield asset, (asset.get("source") or {}).get("name") or "", asset.get("workspace")

    def _policy_document(self, policy_id: str) -> dict[str, Any]:
        if not self._policy_index:
            self._policy_index = {
                document["id"]: document
                for document in (self.inventory.get("apim") or {}).get("policies") or []
            }
        return self._policy_index.get(policy_id) or {}

    def _count_policy_coverage(
        self, dispositions: dict[int, str], reached: set[int]
    ) -> None:
        """Account for every element the inventory holds, under one disposition.

        Walked over the documents rather than over what the asset pass looked
        at, because the elements that reach no asset are the ones most worth
        counting: a policy on an API this migration excludes, or in a fragment
        nothing includes, raises nothing -- and uncounted it would be absent
        from the plan rather than accounted for in it.
        """
        for document in (self.inventory.get("apim") or {}).get("policies") or []:
            for element in document.get("elements") or []:
                key = id(element)
                if not _is_policy_statement(element):
                    # Not a decision of its own: the configuration of the
                    # statement above it, which is classified in its own right.
                    disposition = "configuration"
                elif key in dispositions:
                    disposition = dispositions[key]
                elif key in reached:
                    disposition = "classified"
                else:
                    disposition = "governsNothing"
                self._count_element(disposition, document, element)

    def _count_element(
        self, disposition: str, document: dict[str, Any], element: dict[str, Any]
    ) -> None:
        """Account for one policy element under exactly one disposition.

        The ones nothing can be said about are listed as well as counted,
        because a number alone cannot be acted on: knowing that one element was
        not in the vocabulary is only useful alongside which element, and where
        it is written.
        """
        self.policy_coverage[disposition] = self.policy_coverage.get(disposition, 0) + 1
        if disposition in {"unrecognised", "unresolved"}:
            self.unrecognised_policies.append({
                "element": element["name"],
                "family": element.get("family"),
                "policyId": document["id"],
                "path": element["path"],
            })

    # --------------------------------------------------------- structural

    def _structural(self) -> None:
        apim = self.inventory.get("apim") or {}
        structural = self.caps.structural_rules()
        self._policy_fragments(structural)

        for workspace in apim.get("workspaces") or []:
            if workspace.get("name") == "default" or not workspace.get("collected"):
                continue
            rule = STRUCTURAL_WORKSPACE.first(structural) or {}
            self._add(
                item_id=ids.item("workspace", workspace["name"]),
                source={"assetId": None, "assetKind": "workspace", "aspect": workspace["name"]},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                proposal=rule.get("proposal", "flatten"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"workspace": workspace},
                blocking=True,
            )

        subscriptions = apim.get("subscriptions") or []
        if subscriptions:
            rule = STRUCTURAL_SUBSCRIPTIONS.first(structural) or {}
            scopes = sorted({entry["scope"]["level"] for entry in subscriptions})
            self._add(
                item_id=ids.item("access", "subscriptions"),
                source={"assetId": None, "assetKind": "access", "aspect": "subscriptions"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id="key.create",
                proposal=rule.get("proposal", "entra-rbac"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"count": len(subscriptions), "scopeLevels": scopes},
                # Only one of the options makes keys. Settled on Entra RBAC or on
                # staying in APIM, this item is a decision with nothing to build,
                # and objects shaped for it would be keys nobody asked for.
                target=(
                    {"capability": "key.create", "objects": _key_objects(subscriptions)}
                    if self._settled_value(ids.item("access", "subscriptions"))
                    == "gateway-key-per-consumer" else {}
                ),
                blocking=True,
            )

        if self._reports_telemetry():
            # The options are spelled out in rules.json rather than here, because
            # these four differ in what they *disturb* rather than in what they
            # cost, and that is mapping knowledge: one touches a resource other
            # workloads may be reading, the next leaves every existing dashboard
            # pointing at a gateway that no longer reports to it.
            rule = STRUCTURAL_TELEMETRY.first(structural) or {}
            loggers = [
                logger.get("name") for logger in
                (self.inventory.get("apim") or {}).get("loggers") or []
            ]
            self._add(
                item_id=_TELEMETRY_ITEM,
                source={"assetId": None, "assetKind": "telemetry", "aspect": "destination"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId", "telemetry.create"),
                proposal=rule.get("proposal", "reuse-appinsights"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"apimLoggers": loggers},
                target=_objects_or_none("telemetry.create",
                                        self._telemetry_objects(_TELEMETRY_ITEM)),
                blocking=False,
            )

        # The collection is APIM's name for the resource; the aspect is the item's
        # id, which does not move because the inventory renamed something. An id
        # is what carries an operator's decision across re-runs, so it answers to
        # the decision rather than to the shape of the document.
        for collection, aspect, site in (
            ("certificates", "certificates", STRUCTURAL_CERTIFICATES),
            ("authorizationProviders", "credentialProviders", STRUCTURAL_CREDENTIAL_PROVIDERS),
        ):
            entries = apim.get(collection) or []
            if not entries:
                continue
            rule = site.first(structural) or {}
            verdict = rule.get("verdict", "gap")
            self._add(
                item_id=ids.item("shared", aspect),
                source={"assetId": None, "assetKind": aspect, "aspect": "reprovisioning"},
                kind=rule.get("answer", "choose"),
                verdict=verdict,
                proposal=rule.get("proposal"),
                rationale=rule.get("rationale", ""),
                options=_loss_options(verdict),
                evidence={"count": len(entries), "names": [entry.get("name") for entry in entries]},
            )

        networking = (self.inventory.get("service") or {}).get("networking") or {}
        requirement = networking.get("targetRequirement")
        if requirement:
            rule = REACHABILITY_BY_SUBNET.first(
                structural, needsSubnet=bool(requirement.get("needsSubnet"))
            ) or {}
            self._add(
                item_id=ids.item("network", "reachability"),
                source={"assetId": None, "assetKind": "networking", "aspect": "backendReachability"},
                kind=rule.get("answer", "choose"),
                verdict=rule.get("verdict", "partial"),
                capability_id=rule.get("capabilityId", "network.update"),
                proposal=rule.get("proposal"),
                rationale=requirement.get("note", "") or rule.get("rationale", ""),
                options=_options_of(rule),
                evidence={"networking": networking},
                blocking=True,
            )

        # A failed read is unknown, not absent, and cannot be accepted as a loss.
        failures = [
            entry for entry in (self.inventory.get("collection") or {}).get("coverage") or []
            if entry.get("status") == "failed"
        ]
        for failure in failures:
            rule = STRUCTURAL_COVERAGE_GAP.first(structural) or {}
            self._add(
                item_id=ids.item("coverage", f"{failure['collection']}/{failure['scope']}"),
                source={"assetId": None, "assetKind": "coverageGap", "aspect": failure["collection"]},
                kind=rule.get("answer", "supply"),
                verdict=rule.get("verdict", "gap"),
                rationale=rule.get("rationale", ""),
                options=_options_of(rule) or [
                    _opt("re-collect", "Fix access and collect again."),
                    _opt("supply-facts", "State what is there."),
                ],
                evidence={"coverage": failure},
                blocking=rule.get("blocking", True),
                cannot_accept=rule.get("cannotAccept", True),
            )

    def _reports_telemetry(self) -> bool:
        """Whether anything here was reporting telemetry that has to find a new home.

        Either signal is enough and neither implies the other: a logger is the
        service-wide sink, while an `emit-token-metric` policy is an API asking
        for dimensions on it. An instance can carry one without the other.
        """
        loggers = (self.inventory.get("apim") or {}).get("loggers") or []
        if any(
            str(logger.get("loggerType") or "").lower() in {"applicationinsights", "azuremonitor"}
            for logger in loggers
        ):
            return True
        # Read from the source rather than from the items built so far: the item
        # this answers for is one of them, and asking about itself decided it
        # would not exist.
        return any(
            "emit-token-metric" in (element.get("name") or "")
            for document in (self.inventory.get("apim") or {}).get("policies") or []
            for element in document.get("elements") or []
        )

    def _manual_prerequisites(self) -> None:
        """Steps the tool cannot perform, surfaced before anything is executed."""
        assets = self.inventory.get("assets") or {}
        providers = assets.get("modelProviders") or []
        if any((provider.get("auth") or {}).get("mode") == "managedIdentity" for provider in providers):
            identity = (self.inventory.get("service") or {}).get("identity") or {}
            reusing = bool(identity.get("userAssignedIdentities"))
            accounts = sorted({
                (provider.get("azure") or {}).get("accountResourceId")
                for provider in providers
                if (provider.get("auth") or {}).get("mode") == "managedIdentity"
                and (provider.get("azure") or {}).get("accountResourceId")
            })
            self.prerequisites.append({
                "id": "prereq:foundry-rbac",
                "owner": "azure-administrator",
                # The exact grant, so whoever runs it -- operator or agent -- runs
                # the one the plan specified rather than improvising a role name.
                # The principal only exists once the identity phase has run.
                "commands": [
                    {
                        "command": (
                            "az role assignment create --role 'Foundry User' "
                            "--assignee-object-id <gateway-principal-id> "
                            "--assignee-principal-type ServicePrincipal "
                            f"--scope {account}"
                        ),
                        "roleDefinitionId": "53ca6127-db72-4b80-b1b0-d745d6d5456d",
                        "scope": account,
                        "principalFrom": (
                            "az aigateway show ... --query identity.principalId -o tsv, "
                            "after the identity phase"
                        ),
                    }
                    for account in accounts
                ],
                "summary": "Grant the gateway identity data-plane access on each Foundry account",
                "detail": (
                    "A provider using ManagedIdentity needs a role assignment on the backend account, "
                    "and role assignments are outside the gateway resource provider. "
                    + (
                        "If the plan reuses the source's user-assigned identity, its existing grants "
                        "already cover this and nothing new is needed."
                        if reusing else
                        "The target's system-assigned identity is a new principal, so the source's "
                        "existing grants do not apply to it."
                    )
                ),
            })
        settled = self._settled_value(_TELEMETRY_ITEM)
        # Two of the four destinations create or touch an Application Insights
        # resource, and two do not. Which is which is mapping knowledge, so the
        # rule says it; until the item is settled nothing is ruled out and the
        # administrator still has to know. An unsettled plan asks.
        telemetry_rule = STRUCTURAL_TELEMETRY.first(self.caps.structural_rules()) or {}
        needs_endpoint = telemetry_rule.get("prerequisiteWhen")
        if self._reports_telemetry() and (
            settled is None or not needs_endpoint or settled in needs_endpoint
        ):
            self.prerequisites.append({
                "id": "prereq:appinsights-otlp",
                "owner": "azure-administrator",
                "commands": [],
                "summary": (
                    "Create an Application Insights resource with the OTLP endpoint enabled"
                    if settled == "new-appinsights" else
                    "Enable the OTLP endpoint on the Application Insights resource APIM reports to"
                ),
                # The one fact that makes this mapping possible, and it is in
                # neither product's inventory: APIM emits to Application
                # Insights, the gateway exports OpenTelemetry, and the only
                # surface the two share is App Insights' own OTLP endpoint.
                "detail": (
                    "APIM sends telemetry to Azure Application Insights; AI Gateway sends it "
                    "through an OpenTelemetry exporter. The only surface both support is the OTLP "
                    "endpoint on the Application Insights resource, which is off until someone "
                    "turns it on. Enable it on the existing resource, or create one with it "
                    "enabled, then settle the telemetry item on an OpenTelemetry exporter pointed "
                    "at it. Without that endpoint there is no path at all, and the gateway's own "
                    "metrics are the only telemetry the migration produces."
                ),
            })
        self.prerequisites.append({
            "id": "prereq:caller-rbac",
            "owner": "azure-administrator",
            "commands": [
                {
                    "command": (
                        "az role assignment create --role 'AI Gateway Models User' "
                        "--assignee <caller-principal> --scope <gateway-resource-id>"
                    ),
                    "roleDefinitionId": "a6b68e3d-a1f0-4c60-8678-237c050cf4ea",
                    "note": "Use 'AI Gateway Tools User' for MCP callers, or 'AI Gateway User' for both.",
                },
            ],
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
        if requirement_needed := ((self.inventory.get("service") or {}).get("networking") or {}).get(
            "targetRequirement"
        ):
            self.prerequisites.append({
                "id": "prereq:subnet",
                "owner": "azure-administrator",
                "summary": "Provide a subnet the gateway can integrate with",
                "detail": requirement_needed.get("note", ""),
            })
        self.prerequisites.append({
            "id": "prereq:name-collision",
            "owner": "migrate-apim",
            "summary": "Preflight the target name against Microsoft.ApiManagement/service",
            "detail": "Several CLI commands dispatch by name without --ids, and in a migration the source "
                      "APIM and the target gateway plausibly share a name.",
        })

    # ------------------------------------------------------------- merge

    # ------------------------------------------------------- policy targets

    def _policy_target(
        self, rule: dict[str, Any], members: list[dict[str, Any]], *, item_id: str
    ) -> dict[str, Any]:
        """Shape the objects a policy item is applied from.

        Two shapes, because the gateway holds policy in two places: on a model
        registration, and as one baseline on the default workspace. Telemetry is
        neither -- where it reports is its own decision, on its own item. Nor is
        a target the gateway reaches some other way than by writing a policy:
        `validate-jwt` becomes Entra auth and data-plane RBAC, which is a
        decision about how callers authenticate and not an object this item
        applies. Shaped as a baseline it produced one with no settings on it --
        so it read as an object the plan could not finish configuring, and
        preflight stopped a migration over a policy whose item was only ever a
        decision.
        """
        target_type = rule.get("target")
        if not target_type or rule["verdict"] == "gap":
            return {}
        capability_id = rule.get("capabilityId")
        if capability_id == "model.policy":
            objects = self._per_model_objects(target_type, members)
        elif target_type in _POLICY_FIELDS:
            objects = self._baseline_object(target_type, members)
        else:
            objects = []
        return _objects_or_none(capability_id, objects)

    def _telemetry_objects(self, item_id: str) -> list[dict[str, Any]]:
        """An exporter, once the operator has named the resource and its endpoint.

        Two things have to be settled and only one of them is a choice: which
        Application Insights resource gateway telemetry reports to, and the OTLP
        endpoint it exposes once an administrator has enabled it. Neither is in
        APIM -- its logger records a sink the gateway cannot consume -- so there
        is nothing to build until the decision carries the endpoint itself.
        """
        decision = self._settled(item_id) or {}
        kind = decision.get("kind")
        settings = decision.get("applicationInsights") or decision.get("openTelemetry") or {}
        if kind not in {"ApplicationInsights", "OpenTelemetry"} or not settings:
            return []
        return [{
            "name": decision.get("name") or "appinsights",
            "kind": kind,
            "settings": settings,
            "payloadCapture": decision.get("payloadCapture"),
        }]

    def _per_model_objects(
        self, target_type: str, members: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """One object per model the source policy covers.

        A token limit in APIM sits on an API, a product or the service; in the
        gateway it sits on a model registration. So the scope has to be expanded
        into the registrations this plan creates, and each gets its own object:
        one object is one `model policy set`.

        Batching is by counter key, so a batch can hold two limits with
        different ceilings. Shaping only `members[0]` -- as this did -- applied
        the first API's ceiling and silently dropped the rest.
        """
        objects: list[dict[str, Any]] = []
        carried = any(self._registrations_of(member.get("assetId")) for member in members)
        for member in members:
            settings = _policy_settings(target_type, member)
            registrations = self._registrations_of(member.get("assetId"))
            scope = {"level": member.get("scope"), "name": member.get("scopeName")}
            if not registrations:
                if carried and member.get("governedAt") not in {"api", "operation"}:
                    # Inherited from a wider scope that another member does
                    # carry. A gateway-wide token limit governs the MCP APIs
                    # too, and a tool server registers no model: reporting that
                    # as a policy with nowhere to go would block a migration
                    # over a scope the limit was never going to land on.
                    #
                    # A policy the asset's own API asked for is not that. It
                    # was authored for this one thing, and this one thing
                    # cannot carry it -- a loss, and said below. Asked of where
                    # the element is written, a fragment the API includes
                    # itself read as something wider and the loss went
                    # unreported, so extracting a policy into a fragment hid
                    # what writing it inline would have surfaced.
                    continue
                # Nothing anywhere to attach it to. Recorded as an object that
                # cannot be applied rather than dropped, so the item still says
                # the policy existed and what became of it.
                objects.append({
                    "type": target_type, "settings": settings, "scope": scope,
                    "configurationComplete": False,
                    "incompleteReason": (
                        f"No model registration in this plan falls under {scope['level']} "
                        f"{scope['name']!r}, so there is nothing to carry the policy."
                    ),
                    "fullConfigurationAt": {
                        "policyId": member.get("policyId"), "path": member.get("path")},
                })
                continue
            unmapped = _unmapped_attributes(target_type, member)
            for registration in registrations:
                objects.append({
                    "type": target_type,
                    "modelName": registration["modelName"],
                    "providerName": registration["providerName"],
                    "settings": settings,
                    "scope": scope,
                    "configurationComplete": bool(settings),
                    "unmappedAttributes": unmapped,
                    "fullConfigurationAt": {
                        "policyId": member.get("policyId"), "path": member.get("path")},
                })
        return objects

    def _baseline_object(
        self, target_type: str, members: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The one gateway-wide baseline several source policies have to become.

        `az aigateway policy set-*` writes the default workspace, of which there
        is one. Three APIs rate-limited separately in APIM cannot each keep
        their own, so the strictest is proposed -- never more permissive than
        anything the source enforced -- and every variant is recorded on the
        object. Picking `members[0]` quietly made the first API's limit the
        gateway's, which is as likely to be the loosest as the tightest.
        """
        if not members:
            return []
        shaped = [(member, _policy_settings(target_type, member)) for member in members]
        strictest, settings = min(shaped, key=lambda pair: _strictness(target_type, pair[1]))
        ranges: list[str] = []
        unconvertible: list[str] = []
        if target_type in _POLICY_NEEDS_CHILDREN:
            ranges, unconvertible = self._address_ranges(strictest)
        if ranges:
            settings = {**settings, "ranges": ranges}
        variants = [
            {
                "scope": {"level": member.get("scope"), "name": member.get("scopeName")},
                "settings": member_settings,
                "policyId": member.get("policyId"),
            }
            for member, member_settings in shaped
        ]
        complete = bool(settings) and (target_type not in _POLICY_NEEDS_CHILDREN or bool(ranges))
        obj = {
            "type": target_type,
            "settings": settings,
            "configurationComplete": complete,
            "scope": {"level": "gateway", "name": "default"},
            "unmappedAttributes": _unmapped_attributes(target_type, strictest),
            "fullConfigurationAt": {
                "policyId": strictest.get("policyId"), "path": strictest.get("path")},
        }
        if unconvertible:
            # Named, not dropped: an address the target cannot express is a hole
            # in a filter, and a filter with a hole reads as a filter.
            obj["unconvertibleAddresses"] = unconvertible
            obj["configurationComplete"] = complete = False
            obj["incompleteReason"] = (
                "These addresses are not expressible as CIDR, which is all the target takes: "
                + ", ".join(unconvertible)
            )
        elif not complete and target_type in _POLICY_NEEDS_CHILDREN:
            obj["incompleteReason"] = (
                f"`{strictest.get('element')}` keeps its addresses in child elements and none were "
                "collected, so the baseline would be written with no ranges in it."
            )
        if len({json.dumps(v["settings"], sort_keys=True) for v in variants}) > 1:
            # Said on the object, because this is the one place the collapse is
            # visible: by the time it is a command it looks like one policy.
            obj["collapsedFrom"] = variants
            obj["collapseNote"] = (
                f"{len(variants)} source policies at different scopes become one gateway-wide "
                "baseline. The strictest is proposed; the others are recorded here."
            )
        return [obj]

    def _registrations_of(self, asset_id: str | None) -> list[dict[str, Any]]:
        """The model registrations this plan creates for one source API.

        Matched on the asset, which the member now carries, rather than
        re-derived from a scope level and a bare name. The derivation could not
        answer for a fragment or an operation at all, and answered for an API
        by its unqualified name -- so `finance/shared` and `hr/shared` were one
        API to it, and a limit on either reached the models of both.
        """
        out: list[dict[str, Any]] = []
        for item in self.items:
            if item.get("capabilityId") != "model.create":
                continue
            if (item.get("source") or {}).get("assetId") != asset_id:
                continue
            for obj in (item.get("target") or {}).get("objects") or []:
                if obj.get("name"):
                    out.append({"modelName": obj["name"], "providerName": obj.get("providerName")})
        return out

    def _address_ranges(self, member: dict[str, Any]) -> tuple[list[str], list[str]]:
        """The ip-filter's addresses, as CIDR, and whatever would not convert.

        The walker records children as elements of their own, so the addresses
        are in the inventory under the parent's path rather than on its
        attributes. They need translating as well as finding: APIM writes an
        arbitrary `from`-`to` range and the gateway takes CIDR only, which it
        says by rejecting the write -- *"ipFilter.cidrRanges entries must be
        valid CIDR ranges"*. An arbitrary range is not one CIDR block but a set
        of them, so each is expanded into the exact cover; 192.0.2.1-192.0.2.254
        is fourteen blocks and no addresses more or fewer than the source let
        through.
        """
        document = next(
            (doc for doc in (self.inventory.get("apim") or {}).get("policies") or []
             if doc.get("id") == member.get("policyId")), None
        )
        if not document:
            return [], []
        prefix = f"{member.get('path')}/"
        ranges: list[str] = []
        unconvertible: list[str] = []
        for element in document.get("elements") or []:
            if not (element.get("path") or "").startswith(prefix):
                continue
            attributes = element.get("attributes") or {}
            if element.get("name") == "address-range":
                start, end = attributes.get("from"), attributes.get("to")
                if not start or not end:
                    continue
                blocks = _cidr_cover(start, end)
                (ranges if blocks else unconvertible).extend(blocks or [f"{start}-{end}"])
            elif element.get("name") == "address" and element.get("text"):
                blocks = _cidr_cover(element["text"], element["text"])
                (ranges if blocks else unconvertible).extend(
                    blocks or [str(element["text"])])
        return ranges, unconvertible

    def _mark_by_hand(self, items: list[dict[str, Any]]) -> None:
        """Say which settled work `apply` will leave for the operator.

        The third answer to "can this be migrated", after "the target cannot"
        and "the installed CLI cannot": the gateway can, the CLI can, and this
        tool has no builder. Unsaid, such an item is settled, approved and
        counted as ready to execute, and the only signal is a phase that runs
        no steps -- which reads as a phase with nothing in it.

        Run after the merge, because a decision settled in a previous
        generation is what turns an item into work that would be applied.
        """
        from .apply import AUTHORED_HERE, PHASE_FOR_CAPABILITY, unperformable_phase

        for item in items:
            capability_id = item.get("capabilityId") or ""
            if capability_id not in PHASE_FOR_CAPABILITY or capability_id in AUTHORED_HERE:
                continue
            capability = self.caps.capability(capability_id)
            command = f"az aigateway {' '.join(capability.command)}" if capability else None
            phase = unperformable_phase(item)
            if not phase:
                # Still unsettled. Which way it is settled does not change who
                # applies it, and that belongs in front of the operator while
                # they are choosing between semantics for it.
                if item.get("status") in {NEEDS_DECISION, STALE}:
                    item["rationale"] = (
                        (f"{item['rationale']} " if item.get("rationale") else "")
                        + "However this is settled, `apply` has no builder for "
                        f"`{capability_id}`: the work stays with the operator."
                    )
                continue
            item["appliedByHand"] = {
                "phase": phase,
                "command": command,
                "reason": "migrate-apim has no builder for this capability.",
            }
            item["rationale"] = (
                (f"{item['rationale']} " if item.get("rationale") else "")
                + "This tool cannot author it: the gateway supports the mapping and "
                + (f"`{command}` exists" if command else "the installed CLI exposes it")
                + f", but `apply` has no builder, so the {phase} phase will run no step for it "
                "and the operator applies it themselves."
            )

    def _check_supplied(self, items: list[dict[str, Any]]) -> None:
        """A decision that commits to work the answer does not carry the facts for.

        `compensate` on a metrics policy means "send them somewhere else", and
        nowhere in APIM says where: its own sink is a logger on the service, not
        part of the policy. Settled and left at that, the exporter is simply
        never created and the phase reports nothing amiss.
        """
        for item in items:
            if item["id"] != _TELEMETRY_ITEM:
                continue
            if item.get("status") not in {READY, ADAPTED}:
                continue
            if (item.get("target") or {}).get("objects"):
                continue
            decision = item.get("decision")
            value = decision.get("value") if isinstance(decision, dict) else decision
            if value not in {"reuse-appinsights", "new-appinsights"}:
                continue
            item["needsFact"] = {
                "what": "where the exporter sends",
                # The field names are the service's own, from the validation it
                # answers a wrong one with. A decision shaped to anything else
                # reaches the phase and fails there. The OTLP kind is named
                # first because it is the only one an APIM logger can reach:
                # see prereq:appinsights-otlp.
                "how": (
                    'Set `decision` to {"kind": "OpenTelemetry", "openTelemetry": '
                    '{"metricsEndpoint": "..."}}, with at least one of metricsEndpoint, '
                    "logsEndpoint or tracesEndpoint. To keep reporting into the Application "
                    "Insights resource APIM used, that endpoint is its OTLP endpoint, which has "
                    "to be enabled on the resource first. A direct "
                    '{"kind": "ApplicationInsights", "applicationInsights": {"connectionString": '
                    '"..."}} exporter is accepted by the command but carries nothing across from '
                    "APIM. Any credential is read at apply time, passed as a file, and never "
                    "stored in the plan."
                ),
            }
            item["rationale"] = (
                f"{item['rationale']} Settled as `compensate`, but no destination was given, so "
                "no exporter is created. The decision has to carry one."
            )

    def _note_unmapped(self, items: list[dict[str, Any]]) -> None:
        """Put what will not travel in front of whoever settles the item.

        It is recorded on the object and named again by the step that applies
        it, which is after every decision has been made. An hourly token quota
        that the target has no field for is worth knowing while the item is
        still a question.
        """
        for item in items:
            dropped = sorted({
                name
                for obj in (item.get("target") or {}).get("objects") or []
                for name in (obj.get("unmappedAttributes") or {})
            })
            if not dropped:
                continue
            item["unmappedAttributes"] = dropped
            item["rationale"] = (
                f"{item['rationale']} The source also sets {', '.join(dropped)}, which the target "
                "has no field for: applying this carries the rest and leaves those behind."
            )

    def _check_buildable(self, items: list[dict[str, Any]]) -> None:
        """Flag target objects that no command could be built from.

        A missing required field used to travel all the way to the phase that
        runs it, where the only signal was a refusal to build. The plan is where
        it can still be answered, so it is reported here, on the item that is
        short of it.
        """
        for item in items:
            fields = _REQUIRED_FIELDS.get(item.get("capabilityId") or "")
            objects = (item.get("target") or {}).get("objects") or []
            if not fields or not objects:
                continue
            missing = sorted({
                flag
                for flag, key in fields.items()
                for obj in objects
                if isinstance(obj, dict) and not _supplied(obj.get(key))
            })
            if missing:
                item["unbuildable"] = {
                    "capabilityId": item["capabilityId"],
                    "missing": missing,
                    "note": (
                        f"`az aigateway {item['capabilityId'].split('.')[0]} create` requires "
                        f"{', '.join('--' + flag for flag in missing)}, and the inventory supplied "
                        "no value for it. Re-collect against the source, or settle the item that "
                        "establishes it."
                    ),
                }

    def _check_produces(self, items: list[dict[str, Any]]) -> None:
        """Flag an asset that is settled for migration and yet creates nothing.

        Settling an item reads as disposing of it, so an asset whose every
        decision is made and whose target is empty looks handled while being
        silently dropped. Assets that deliberately create nothing -- retained,
        blocked, or an accepted loss -- are the expected case and are left
        alone.
        """
        by_asset: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            asset_id = (item.get("source") or {}).get("assetId")
            if asset_id:
                by_asset.setdefault(asset_id, []).append(item)

        for asset_id, group in by_asset.items():
            kinds = {(item.get("source") or {}).get("assetKind") for item in group}
            if not kinds & {"modelApi", "mcpServer"}:
                continue
            settled = [item for item in group if item.get("status") in {ADAPTED, READY}]
            if not settled or len(settled) != len(group):
                continue
            if any(_retains(item) for item in group):
                continue
            if any((item.get("target") or {}).get("objects") for item in group):
                continue
            settled[0]["plannerGap"] = (
                f"Every item for {asset_id} is settled on migrating it, but the plan creates no "
                "object for it, so running every phase would leave it unmigrated. Either the "
                "decision carries facts the planner does not build from, or the asset should be "
                "settled as `retain-in-apim`."
            )

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
            # A settled decision that shares no member with the item it was
            # settled against rested on facts none of which are still here, so
            # `changed` finds nothing to compare and the decision would carry
            # forward untouched. It is also what a change to how members are
            # identified looks like -- this one gained the route an element
            # arrives by, and a plan settled before that has keys none of these
            # match -- and in both cases the honest answer is to ask again.
            replaced = bool(before.get("memberDigests")) and not (
                set(before["memberDigests"]) & set(item["memberDigests"])
            )
            item["decision"] = before.get("decision")
            item["decidedAt"] = before.get("decidedAt")
            # Recorded by the generator, not by whoever adapts the item: adapting
            # means setting `status` and `decision`, nothing more.
            item["decidedAgainst"] = {
                "shape": before.get("shapeDigest"),
                "members": before.get("memberDigests") or {},
            }
            if changed or shape_changed or replaced:
                item["status"] = STALE
                item["staleReason"] = (
                    "The options for this item changed." if shape_changed
                    else f"Source facts changed for: {', '.join(sorted(changed))}." if changed
                    else "Nothing this decision was settled against is still here: every source "
                         "it covered has been replaced, or is now identified differently."
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


# Which object field supplies each flag the catalogue marks required. This
# mirrors the builders in apply.py so that an object which cannot be built
# surfaces while the plan is being adapted rather than when the phase runs --
# the difference between a question the operator can still answer and a stalled
# migration. test_plan asserts the two tables stay in step.
_REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "gateway.create": {"location": "location"},
    "provider.create": {"kind": "kind"},
    "model.create": {
        "deployment-config": "deploymentConfig",
        "api-format": "apiFormat",
        "supported-endpoints": "supportedEndpoints",
    },
    "alias.create": {"routing-name": "routingName", "backend-model": "backendModels"},
    "mcp.create": {"endpoints": "endpoints"},
}


def _supplied(value: Any) -> bool:
    """Whether a field carries something a command could actually send."""
    if value is None or isinstance(value, bool):
        return value is True
    if isinstance(value, (str, list, dict)):
        return bool(value)
    return True


# Settling on one of these is settling on building nothing: the workload stays
# where it is, stops here, or the loss is taken. `kind == "accept-loss"` used to
# stand in for the last three, which read the label the rule happened to carry
# rather than the answer somebody gave -- and the label is now `choose`, which
# says nothing about what was chosen.
_CREATES_NOTHING = {"retain-in-apim", "block", "accept", "accept-loss", "compensate"}


def _retains(item: dict[str, Any]) -> bool:
    """Whether this item's outcome is deliberately to create nothing."""
    decision = item.get("decision")
    value = decision.get("value") if isinstance(decision, dict) else decision
    return value in _CREATES_NOTHING


def _backend_id(model: dict[str, Any]) -> str:
    """The backend this API routes to, which identifies its provider asset."""
    for target in (model.get("routing") or {}).get("targets") or []:
        if target.get("backendId"):
            return str(target["backendId"])
    return ""


def _provider_name(model: dict[str, Any]) -> str | None:
    """The CLI name of the provider a model registers under.

    Derived from the backend the API routes to, which is the same slug the
    provider item registers itself under.
    """
    for target in (model.get("routing") or {}).get("targets") or []:
        if target.get("backendId"):
            return _slug(target["backendId"])
    return None


def _api_format(endpoints: list[str]) -> str | None:
    """The target's apiFormat for a set of published routes.

    The enum is AnthropicMessages, OpenAIChatCompletions and ResponsesApi only,
    while a live gateway serves `/openai/v1/embeddings` too. So an embeddings-only
    model takes the OpenAI format with its route carried in supportedEndpoints;
    the routes are declared, the format is the closest the enum allows.
    """
    joined = " ".join(endpoints or [])
    if "/v1/messages" in joined:
        return "AnthropicMessages"
    if "chat/completions" in joined or "embeddings" in joined:
        return "OpenAIChatCompletions"
    if "/responses" in joined:
        return "ResponsesApi"
    return None


def _opt(value: str, consequence: str) -> dict[str, str]:
    return {"value": value, "consequence": consequence}


def _options_of(rule: dict[str, Any],
                composed: dict[str, str] | None = None) -> list[dict[str, str]]:
    """A rule's options, in either of the two shapes rules.json uses.

    A bare string is the choice with nothing said about it; the object form
    carries what choosing it costs. Both reach the plan as {value, consequence},
    so a rule can gain a consequence later without the reader changing.

    `composed` carries the costs that are this asset's own numbers -- how many
    operations stay behind, which dialect the callers move to. Those sites used
    to write the whole list, so the vocabulary in the file was never read and
    editing it changed nothing; the choices are the rule's either way, and only
    the sentence is built where the inventory is.
    """
    options = []
    for option in rule.get("options") or []:
        value = option["value"] if isinstance(option, dict) else option
        if not value:
            continue
        consequence = (composed or {}).get(value)
        if consequence is None:
            consequence = option.get("consequence", "") if isinstance(option, dict) else ""
        options.append(_opt(value, consequence))
    return options


def _loss_options(verdict: str) -> list[dict[str, str]]:
    if verdict != "gap":
        return []
    return [
        _opt("accept", "Migrate without it and accept the reduced posture."),
        _opt("compensate", "Replace it with a different control on the target."),
        _opt("retain-in-apim", "Keep this workload on APIM."),
        _opt("block", "Stop the migration until resolved."),
    ]


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
                # The target wants the absolute URL of the MCP endpoint, which is
                # the backend URL plus the path APIM proxies to -- the same join
                # mcp.upstream_url() makes for tool discovery. Registering the
                # bare backend host points the gateway at the site root.
                "mcp": {
                    "url": upstream["url"].rstrip("/") + (upstream.get("mcpPath") or "/mcp"),
                    "transport": upstream.get("transport") or "streamableHttp",
                },
            })
    for source in server.get("openApiSources") or []:
        endpoints.append({
            "kind": "openApi",
            "required": True,
            "openApi": {"specSource": {"type": "url", "$fromExport": source.get("apiName")}},
        })
    _namespace_endpoints(server, endpoints)
    return endpoints


def _namespace_endpoints(server: dict[str, Any], endpoints: list[dict[str, Any]]) -> None:
    """Give every source the `namespace` the target requires.

    `mcp create` rejects an endpoint without one, and APIM has no equivalent
    field to carry over: a passthrough API proxies one upstream and names
    nothing. The server's own name is the natural identifier for its only
    source; additional sources are suffixed so the set stays unique.
    """
    base = _slug(server["id"])
    for index, endpoint in enumerate(endpoints):
        endpoint["namespace"] = base if index == 0 else f"{base}-{index + 1}"


# Sections, control flow and the fragment root wrap policy statements; anything
# else that wraps an element makes that element its configuration, not a policy
# of its own. `retry` and `wait` are here because they hold real policies: their
# children were read as configuration and never reached rule selection at all,
# and once every element is counted that silence would have been counted as a
# statement being configured.
_STATEMENT_WRAPPERS = {
    "inbound", "backend", "outbound", "on-error", "fragment", "retry", "wait",
    *policy_mod.CONDITIONAL_WRAPPERS,
}


def _is_policy_statement(element: dict[str, Any]) -> bool:
    """True for a policy statement, false for a policy's configuration children.

    ``<set-header><value>…</value></set-header>`` is one decision, not two: the
    ``<value>`` child is how the header is configured. Walking it separately
    produced phantom items named after configuration elements.
    """
    return all(name in _STATEMENT_WRAPPERS for name in policy_mod.ancestors(element))


# Dispositions ranked by how much they claim. An element reached by two routes
# can be excluded on one and raise an item on the other -- a fragment included
# plainly by one API and inside a `choose` by another -- and the stronger claim
# is the one the tally should carry.
_DISPOSITION_RANK = {
    "notApplicable": 0, "handled": 1, "classified": 2, "unrecognised": 3, "unresolved": 4,
}


def _note(dispositions: dict[int, str], key: int, disposition: str) -> None:
    current = dispositions.get(key)
    if current is None or _DISPOSITION_RANK[disposition] > _DISPOSITION_RANK[current]:
        dispositions[key] = disposition


def _unique_arrivals(arrivals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per asset, scope and route, so a fragment reads once per way in."""
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for arrival in arrivals:
        key = (arrival["assetId"], arrival["policyId"], arrival["section"],
               arrival["underConditional"], tuple(arrival["via"]))
        if key not in seen:
            seen.add(key)
            out.append(arrival)
    return out


def _level_of(document: dict[str, Any]) -> str | None:
    return (document.get("scope") or {}).get("level")


def _name_of(document: dict[str, Any]) -> str | None:
    return (document.get("scope") or {}).get("name")


def _apply_partial_when(
    rule: dict[str, Any], element: dict[str, Any], *, under_conditional: bool = False
) -> dict[str, Any]:
    """Demote a mapping to partial when one of the rule's conditions holds.

    A token limit maps natively; it becomes a decision only because its caller
    partition is an expression APIM evaluates and the target cannot. A backend
    selection is carried by the alias pool; it becomes a decision when the
    source picked the backend with an expression or inside a ``choose``,
    because the pool holds the backends and not the rule that chose among them.

    ``under_conditional`` is the caller's, not the element's, because a branch
    can be at the site that included the element rather than around the element
    itself: a fragment pulled in under a ``choose`` runs conditionally however
    unconditionally its own body reads.

    Any one condition demotes. Requiring all of them would let an element that
    trips a single one read as cleanly mapped, which is the reading this exists
    to prevent.
    """
    condition = rule.get("partialWhen")
    if not condition:
        return rule
    attribute = condition.get("attributeIsExpression")
    value = (element.get("attributes") or {}).get(attribute or "")
    holds = (
        (isinstance(value, str) and value.lstrip().startswith("@"))
        or (condition.get("hasExpression") and bool(element.get("expressionIds")))
        or (condition.get("underConditional")
            and (under_conditional or policy_mod.under_conditional(element)))
    )
    if not holds:
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


def _cidr_cover(start: Any, end: Any) -> list[str]:
    """The exact set of CIDR blocks covering an inclusive address range.

    Empty when either end is not an address, or they are of different families,
    so the caller reports what it could not convert rather than writing a filter
    that lets through what the source blocked.
    """
    try:
        first, last = ipaddress.ip_address(str(start).strip()), ipaddress.ip_address(str(end).strip())
        return [str(network) for network in ipaddress.summarize_address_range(first, last)]
    except (ValueError, TypeError):
        return []


def _key_objects(subscriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One gateway key per APIM subscription that was carrying callers.

    The key *value* never crosses: APIM will not hand it over and the gateway
    will not take one. So these are new keys with the old names, and every
    caller is re-keyed from `api-key list-secrets`, which only the operator runs.
    """
    objects = []
    for entry in subscriptions:
        name = _slug(entry.get("name") or "")
        if not name:
            continue
        objects.append({
            "name": name,
            "displayName": entry.get("displayName") or entry.get("name"),
            "replaces": {
                "subscriptionId": entry.get("id"),
                "scope": entry.get("scope"),
                # Said on the object so it reaches the report: a key that is
                # created is not a caller that still works.
                "valueCarriedOver": False,
            },
        })
    return objects


def _objects_or_none(capability_id: str | None, objects: list[dict[str, Any]]) -> dict[str, Any]:
    """A target, or nothing at all when there is no object to apply."""
    return {"capability": capability_id, "objects": objects} if objects else {}


# How strict one policy is against another of the same type, lowest first. Only
# used to choose which of several source policies becomes the one gateway-wide
# baseline, where the conservative choice is the one no source exceeded.
def _strictness(target_type: str, settings: dict[str, Any]) -> tuple[float, float]:
    def number(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    if target_type == "tokenLimit":
        return (number(settings.get("count"), float("inf")), 0.0)
    if target_type == "requestRateLimit":
        calls = number(settings.get("callsPerPeriod"), float("inf"))
        period = number(settings.get("periodSeconds"), 1.0) or 1.0
        # Calls per second, so 60/minute and 1/second rank as the same limit.
        return (calls / period, calls)
    return (0.0, 0.0)


def _policy_settings(target_type: str, member: dict[str, Any]) -> dict[str, Any]:
    mapping = _POLICY_FIELDS.get(target_type, {})
    attributes = member.get("attributes") or {}
    return {
        field: attributes.get(attribute)
        for attribute, field in mapping.items()
        if attributes.get(attribute) is not None
    }


def _unmapped_attributes(target_type: str, member: dict[str, Any]) -> dict[str, Any]:
    """Source attributes the target has no field for.

    `llm-token-limit` on the bugbash instance carried a 5000/Hourly quota and
    `estimate-prompt-tokens` beside the per-minute rate. Only the rate maps, so
    the other two did not travel -- and the step that applied the rate reported
    `verified`, which read as the whole policy having moved.
    """
    mapping = _POLICY_FIELDS.get(target_type, {})
    return {
        name: value for name, value in (member.get("attributes") or {}).items()
        if name not in mapping and value is not None
    }


def _policy_signature(element: dict[str, Any], rule: dict[str, Any], has_expression: bool) -> str:
    """Elements deciding the same thing the same way batch into one item.

    Only attributes the rule says are decision-relevant take part: two token
    limits with different ceilings but the same counter key are one decision
    about partitioning, not two.

    The item id is derived from this, so anything in here is something a
    settled decision is keyed on, and moving it sends every prior answer to
    `orphanedDecisions`. How the item is *answered* is not in here, and was:
    across all 62 elements the collector classifies, times expression true and
    false, times every `partialWhen` either way, no element's answer varies
    while the rest of the signature holds, so it separated nothing. Taking it
    out moved these ids once -- the labels it hashed are gone either way -- and
    is what stops the next change to the rules vocabulary moving them again.
    """
    batch_on = rule.get("batchOn")
    attributes = element.get("attributes") or {}
    relevant = {key: attributes.get(key) for key in batch_on} if batch_on else {}
    return digest({
        "element": element["name"], "verdict": rule["verdict"],
        "expression": has_expression, "attributes": relevant,
    })[7:19]


def _shape_digest(item: dict[str, Any]) -> str:
    """What makes an answer valid: the question and the choices, not the wording."""
    return digest({
        "kind": item["kind"], "verdict": item["verdict"],
        "capabilityId": item["capabilityId"],
        "options": sorted(option["value"] for option in item["options"]),
    })


def _member_key(member: dict[str, Any]) -> str:
    """A stable, readable name for one member of a batched item.

    Batches identify their members differently -- a policy by what it governs
    and where it is written, a model by name -- so the key comes from whichever
    identity the member actually carries. Assuming the policy shape named every
    model member `None#None`: they collapsed onto one key, each digest overwrote
    the last, and a change to any member but the final one went unnoticed.

    A policy member leads with the asset because one element now reaches
    several: a fragment included by four APIs is written once and governs four
    times, and keying on where it is written alone would collapse the four onto
    one digest -- so adding a fifth API would leave a settled decision reading
    as unchanged.
    """
    if member.get("assetId") and member.get("policyId"):
        # The route as well as the destination. One API can include one
        # fragment twice, and those two members agree on everything else.
        route = "+".join(member.get("arrival") or []) or "direct"
        return "#".join([
            str(member["assetId"]), str(member["policyId"]), str(member.get("path") or ""),
            str(member.get("section") or ""), route,
        ])
    for keys in (("policyId", "path"), ("modelName",), ("name",), ("id",)):
        values = [member.get(key) for key in keys]
        if all(value is not None for value in values):
            return "#".join(str(value) for value in values)
    return digest(member)


def _member_digests(item: dict[str, Any]) -> dict[str, str]:
    """Per-member source facts, so one changed member does not unsettle the rest."""
    members = (item.get("evidence") or {}).get("members")
    if isinstance(members, list) and members:
        return {_member_key(member): digest(member) for member in members}
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
