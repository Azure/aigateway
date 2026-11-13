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
from .capability import CapabilityMap
from .detect import dialect_target

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
        options = [
            _opt("system-assigned",
                 "A new principal; every backend grant has to be made against it."),
        ]
        for entry in assigned:
            options.append(_opt(
                f"reuse:{entry['resourceId']}",
                "Carries the grants this identity already holds on the backends.",
            ))
        proposal = f"reuse:{assigned[0]['resourceId']}" if assigned else "system-assigned"
        self._add(
            item_id=ids.item("identity", "assign"),
            source={"assetId": None, "assetKind": "identity", "aspect": "gatewayIdentity"},
            kind="translate" if assigned else None,
            verdict="partial" if assigned else "native",
            capability_id="identity.assign",
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
            options=options if assigned else [],
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
        self._pool_affinity(model)

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
        self._add(
            item_id=ids.item(asset_id, "sessionAffinity"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "sessionAffinity"},
            kind="accept-loss",
            verdict="gap",
            capability_id="alias.create",
            proposal="accept-loss",
            rationale=(
                "This API's backend pool pins a session to the backend that served it. The gateway "
                "supports the same idea on an alias (a `sessionBackendPreference` stage with a CEL "
                f"key), but {gap}, so this "
                "run cannot configure it. Without it, each request is routed independently and a "
                "session can move between backends mid-conversation."
            ),
            options=[
                _opt("accept-loss", "Migrate without affinity, and configure it afterwards by hand."),
                _opt("retain-in-apim", "Keep this API on APIM until affinity can be authored."),
                _opt("block", "Stop the migration until it can be carried over."),
            ],
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
            options = [
                _opt("list-models",
                     f"Publish the {len(catalogue)} the catalogue returned; drop any that cannot "
                     "serve an inference route by editing `decision.models`."),
                _opt("retain-in-apim", "Do not migrate this API."),
            ]
            proposal = "list-models"
            rationale = (
                f"The catalogue at {models.get('resolvedFrom')} returned {len(catalogue)} model(s): "
                f"{sample}{more}. It states no modality, so whether each one serves an inference "
                "route is not established -- an image or speech model published here would fail at "
                "the upstream."
            )
        else:
            options = [
                _opt("resolve-models", "Read the provider's catalogue with its credential."),
                _opt("list-models", "Name the models to register."),
                _opt("retain-in-apim", "Do not migrate this API."),
            ]
            # A provider with a catalogue endpoint has an actionable default:
            # fetch it rather than ask someone to type model names.
            proposal = ("resolve-models"
                        if models.get("discoverySource") == "modelsEndpoint" else "list-models")
            rationale = (" ".join(models.get("notes") or [])
                         or "The model catalogue could not be resolved.")

        item = self._add(
            item_id=ids.item(asset_id, "models"),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": "modelCatalogue"},
            kind="enumerate",
            verdict="partial",
            capability_id="model.create",
            proposal=proposal,
            rationale=rationale,
            options=options,
            evidence={
                "discoverySource": models.get("discoverySource"),
                "catalogue": catalogue,
                "notes": models.get("notes"),
            },
            blocking=True,
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
        self._add(
            item_id=ids.item(asset_id, item_key),
            source={"assetId": asset_id, "assetKind": "modelApi", "aspect": f"model:{name}"
                    + (f"@{provider_name}" if pooled else "")},
            kind=None,
            verdict="native",
            capability_id="model.create",
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
                + balance
            ),
            options=[
                _opt("use-model-names", "Publish each model under its own name."),
                _opt("override", "Supply names per model; set them in this item's members."),
            ],
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
                    # The level alone cannot say which models a policy covers:
                    # an api-scoped limit on one API is not a limit on the rest.
                    "scopeName": document.get("scope", {}).get("name"),
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
                target=self._policy_target(
                    rule, members, item_id=ids.item("policy", signature)),
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

        networking = (self.inventory.get("service") or {}).get("networking") or {}
        requirement = networking.get("targetRequirement")
        if requirement:
            self._add(
                item_id=ids.item("network", "reachability"),
                source={"assetId": None, "assetKind": "networking", "aspect": "backendReachability"},
                kind="translate",
                verdict="partial",
                capability_id="network.update",
                proposal="new-delegated-subnet" if requirement.get("needsSubnet") else "private-ingress",
                rationale=requirement.get("note", ""),
                options=[
                    _opt("new-delegated-subnet",
                         "Provision a subnet delegated to Microsoft.App/environments and integrate the gateway."),
                    _opt("public-egress",
                         "Reach backends over public networking; only viable if they accept it."),
                    _opt("retain-in-apim", "Keep workloads that need private backends on APIM."),
                    _opt("block", "Stop until the network design is agreed."),
                ],
                evidence={"networking": networking},
                blocking=True,
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

        Three target shapes, because the gateway has three: a per-model policy,
        one gateway-wide baseline on the default workspace, and a telemetry
        exporter whose destination is in neither the policy nor the gateway.
        """
        target_type = rule.get("target")
        if not target_type or rule["verdict"] == "gap":
            return {}
        capability_id = rule.get("capabilityId")
        if capability_id == "model.policy":
            objects = self._per_model_objects(target_type, members)
        elif capability_id == "telemetry.create":
            objects = self._telemetry_objects(item_id)
        else:
            objects = self._baseline_object(target_type, members)
        return {"capability": capability_id, "objects": objects} if objects else {}

    def _telemetry_objects(self, item_id: str) -> list[dict[str, Any]]:
        """An exporter, once the operator has said where it sends.

        `emit-token-metric` names dimensions, not a destination -- APIM's own
        sink is a logger on the service, which does not come with the policy.
        So there is nothing to build until the decision carries one, and
        `accept` means the gateway's own telemetry is enough: no exporter at all.
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
        for member in members:
            settings = _policy_settings(target_type, member)
            registrations = self._registrations_in_scope(member)
            scope = {"level": member.get("scope"), "name": member.get("scopeName")}
            if not registrations:
                # Nothing to attach it to. Recorded as an object that cannot be
                # applied rather than dropped, so the item still says the policy
                # existed and what became of it.
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

    def _registrations_in_scope(self, member: dict[str, Any]) -> list[dict[str, Any]]:
        """The model registrations this plan creates under a policy's scope."""
        level, name = member.get("scope"), member.get("scopeName")
        apis = self._apis_in_scope(level, name)
        out: list[dict[str, Any]] = []
        for item in self.items:
            if item.get("capabilityId") != "model.create":
                continue
            asset_id = (item.get("source") or {}).get("assetId") or ""
            if apis is not None and _api_of(asset_id) not in apis:
                continue
            for obj in (item.get("target") or {}).get("objects") or []:
                if obj.get("name"):
                    out.append({"modelName": obj["name"], "providerName": obj.get("providerName")})
        return out

    def _apis_in_scope(self, level: str | None, name: str | None) -> set[str] | None:
        """Which source APIs a policy scope covers, or None for all of them."""
        if level in {"global", "service", None}:
            return None
        if level == "api":
            return {name or ""}
        if level == "workspace":
            return {
                _api_of((item.get("source") or {}).get("assetId") or "")
                for item in self.items
                if item.get("capabilityId") == "model.create"
                and ((item.get("source") or {}).get("assetId") or "").split(":", 1)[-1]
                .startswith(f"{name}/")
            }
        if level == "product":
            for product in (self.inventory.get("shared") or {}).get("products") or []:
                if product.get("name") == name or product.get("id") == name:
                    return {ids.arm_name(api_id) for api_id in product.get("apiIds") or []}
            return set()
        return set()

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
            (doc for doc in self.inventory.get("policies") or []
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
            if item.get("capabilityId") != "telemetry.create":
                continue
            if item.get("status") not in {READY, ADAPTED}:
                continue
            if (item.get("target") or {}).get("objects"):
                continue
            decision = item.get("decision")
            value = decision.get("value") if isinstance(decision, dict) else decision
            if value != "compensate":
                continue
            item["needsFact"] = {
                "what": "where the exporter sends",
                # The field names are the service's own, from the validation it
                # answers a wrong one with. A decision shaped to anything else
                # reaches the phase and fails there.
                "how": (
                    'Set `decision` to {"kind": "ApplicationInsights", "applicationInsights": '
                    '{"connectionString": "..."}}, or {"kind": "OpenTelemetry", "openTelemetry": '
                    '{"metricsEndpoint": "..."}} with at least one of metricsEndpoint, '
                    "logsEndpoint or tracesEndpoint. A connection string is read at apply time, "
                    "passed as a file, and never stored in the plan."
                ),
            }
            item["rationale"] = (
                f"{item['rationale']} Settled as `compensate`, but no destination was given, so "
                "no exporter is created. The decision has to carry one."
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


def _retains(item: dict[str, Any]) -> bool:
    """Whether this item's outcome is deliberately to create nothing."""
    if item.get("kind") == "accept-loss":
        return True
    decision = item.get("decision")
    value = decision.get("value") if isinstance(decision, dict) else decision
    return value in {"retain-in-apim", "block"}


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


def _api_of(asset_id: str) -> str:
    """The source API name in a model asset id, workspace prefix removed."""
    return (asset_id.split(":", 1)[-1]).rsplit("/", 1)[-1]


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


def _member_key(member: dict[str, Any]) -> str:
    """A stable, readable name for one member of a batched item.

    Batches identify their members differently -- a policy by id and path, a
    model by name -- so the key comes from whichever identity the member
    actually carries. Assuming the policy shape named every model member
    `None#None`: they collapsed onto one key, each digest overwrote the last,
    and a change to any member but the final one went unnoticed.
    """
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
