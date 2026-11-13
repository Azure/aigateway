"""Execute a settled plan against the target gateway, one phase at a time.

Migration is additive. Every operation here provisions into the gateway; nothing
is ever written to the source APIM, so a half-finished run leaves a partially
built gateway and a source still serving exactly as before. Retiring anything
from APIM is the operator's decision after validating the new gateway.

Three properties make a partial run recoverable without a transaction:

* **Read before write.** Every step reads its target first and skips the write
  when the desired state is already there, which is both how a re-run resumes
  and how an ambiguous failure recovers.
* **The journal is the history.** The plan stays intent; what happened lives
  beside it, so a failed run resumes instead of restarting.
* **Ambiguity is named.** A write whose outcome could not be established is
  ``mutationUnknown`` and is never blindly retried -- the next run reconciles it
  by reading the target.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .resolve import ResolveError, resolve_secret

SCHEMA_VERSION = "1.0"

# Dependency order. MCP and telemetry do not depend on the model chain, but the
# phases still run in sequence so an operator always knows where they are.
PHASES: tuple[str, ...] = (
    "gateway", "identity", "providers", "models", "aliases", "toolServers", "policies", "keys",
)

_PHASE_FOR_CAPABILITY = {
    "gateway.create": "gateway",
    "identity.assign": "identity",
    "provider.create": "providers",
    "model.create": "models",
    "alias.create": "aliases",
    "mcp.create": "toolServers",
    "policy.update": "policies",
    "model.policy": "policies",
    "key.create": "keys",
    "telemetry.create": "keys",
}

# Injected so tests never shell out.
Runner = Callable[[list[str], dict[str, Any] | None], "CommandResult"]


class ApplyError(RuntimeError):
    pass


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        try:
            return json.loads(self.stdout)
        except (json.JSONDecodeError, TypeError):
            return None


@dataclass
class Target:
    subscription: str
    resource_group: str
    name: str

    @classmethod
    def parse(cls, resource_id: str) -> "Target":
        parts = (resource_id or "").strip("/").split("/")
        lowered = [p.lower() for p in parts]
        try:
            return cls(
                subscription=parts[lowered.index("subscriptions") + 1],
                resource_group=parts[lowered.index("resourcegroups") + 1],
                name=parts[lowered.index("aigateways") + 1],
            )
        except (ValueError, IndexError) as exc:
            raise ApplyError(
                f"the plan's target is not a Microsoft.ApiManagement/aigateways resource id: {resource_id!r}"
            ) from exc

    @property
    def selectors(self) -> list[str]:
        return ["--subscription", self.subscription, "-g", self.resource_group]


@dataclass
class Step:
    item_id: str
    capability_id: str
    phase: str
    objects: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    detail: str = ""
    argv: list[str] = field(default_factory=list)
    # Every command the step would run, not just the first. A rehearsal is the
    # gate an operator approves a phase from, and one item routinely covers
    # many objects -- seven aliases under a single naming decision. Showing one
    # command asked them to approve six they never saw.
    commands: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "capabilityId": self.capability_id,
            "phase": self.phase,
            "status": self.status,
            "detail": self.detail,
            "argv": self.argv,
            "commands": self.commands,
        }


# ------------------------------------------------------------------ preflight


def preflight(plan: dict[str, Any], inventory: dict[str, Any], *, runner: Runner | None = None
              ) -> list[dict[str, Any]]:
    """Everything checkable before the first write.

    There is no transaction across steps, so the cost of discovering a problem
    halfway is a gateway that is half built. Each finding is blocking or not;
    `apply` refuses while any blocking one stands.
    """
    findings: list[dict[str, Any]] = []

    def finding(code: str, blocking: bool, message: str, remedy: str = "") -> None:
        findings.append({"code": code, "blocking": blocking, "message": message, "remedy": remedy})

    target_id = (plan.get("target") or {}).get("resourceId")
    if not target_id:
        finding("noTarget", True, "The plan does not say where it deploys to.",
                "Re-run plan with --target <gateway resource id>.")
    else:
        try:
            Target.parse(target_id)
        except ApplyError as exc:
            finding("badTarget", True, str(exc))

    unsettled = [i for i in plan.get("items") or [] if i.get("status") in {"needs-decision", "stale"}]
    if unsettled:
        finding(
            "unsettled", True,
            f"{len(unsettled)} item(s) still need a decision: "
            + ", ".join(i["id"] for i in unsettled[:5]) + ("..." if len(unsettled) > 5 else ""),
            "Adapt them, then re-run plan.",
        )

    # Work the plan knows it cannot carry out. Stopping here rather than at the
    # phase that hits it means the operator finds out while the plan can still
    # be fixed, instead of part-way through a migration that cannot finish.
    gaps = plan.get("plannerGaps") or []
    if gaps:
        finding(
            "plannerGap", True,
            f"{len(gaps)} item(s) describe work the plan cannot produce: "
            + "; ".join(f"{g['id']}: {g['gap']}" for g in gaps[:3])
            + ("..." if len(gaps) > 3 else ""),
            "Re-collect the inventory and re-run plan, or settle the items named above.",
        )

    orphans = plan.get("orphanedDecisions") or []
    if orphans:
        finding(
            "orphanedDecisions", True,
            f"{len(orphans)} settled decision(s) no longer attach to an item.",
            "Re-apply them to the items that replaced them, or confirm they are not needed.",
        )

    # A secret that cannot be retrieved mechanically stops a step mid-phase.
    secrets_by_id = {entry["id"]: entry for entry in inventory.get("secrets") or []}
    needed = _needed_secret_refs(plan)
    unretrievable = [
        ref for ref in needed
        if ref in secrets_by_id and not secrets_by_id[ref].get("retrievable")
    ]
    missing = [ref for ref in needed if ref not in secrets_by_id]
    if unretrievable:
        finding("secretNotRetrievable", True,
                f"{len(unretrievable)} credential(s) cannot be retrieved automatically: "
                + ", ".join(unretrievable[:3]),
                "Re-provision them on the target, or supply them another way.")
    if missing:
        finding("secretMissing", True,
                f"{len(missing)} referenced credential(s) are not in the inventory: "
                + ", ".join(missing[:3]),
                "Re-collect the inventory.")
    # `retrievable` says a documented retrieval recipe exists for that class of
    # credential, not that this run's identity can execute it. Nothing has
    # fetched anything yet, so a silent pass here would present an untried
    # recipe as a settled one -- and the first attempt happens mid-phase, which
    # is the cost preflight exists to avoid.
    untried = [ref for ref in needed if ref in secrets_by_id and secrets_by_id[ref].get("retrievable")]
    if untried:
        finding("secretRetrievalUntried", False,
                f"{len(untried)} credential(s) have a retrieval recipe that has not been run: "
                + ", ".join(untried[:3]) + ("..." if len(untried) > 3 else ""),
                "Each needs a data-plane read this tool has not attempted -- Key Vault get, or an "
                "APIM listSecrets. A missing grant surfaces when the step runs, not here.")

    created = {
        obj.get("name")
        for item in plan.get("items") or []
        if item.get("capabilityId") == "provider.create"
        for obj in (item.get("target") or {}).get("objects") or []
    }
    dangling = sorted({
        name
        for item in plan.get("items") or []
        if item.get("status") in {"ready", "adapted"}
        for obj in (item.get("target") or {}).get("objects") or []
        for name in [obj.get("providerName")]
                    + [b.get("providerName") for b in obj.get("backendModels") or []]
        if name and name not in created
    })
    if dangling:
        finding(
            "danglingProvider", True,
            "Steps reference providers nothing in the plan creates: " + ", ".join(dangling),
            "Re-plan from a current inventory, or settle the items that register those providers.",
        )

    unbuildable: dict[str, list[str]] = {}
    for item in plan.get("items") or []:
        capability_id = item.get("capabilityId")
        if (item.get("status") in {"ready", "adapted"} and capability_id
                and (item.get("target") or {}).get("objects")
                and capability_id not in _BUILDERS):
            unbuildable.setdefault(capability_id, []).append(item["id"])
    if unbuildable:
        finding(
            "notExecutable", False,
            "The plan contains work this tool cannot perform: "
            + ", ".join(f"{cid} ({len(ids)})" for cid, ids in sorted(unbuildable.items())),
            "Apply these by hand after the run, or they will simply be absent from the gateway.",
        )

    prerequisites = plan.get("prerequisites") or []
    if prerequisites:
        finding("prerequisites", False,
                f"{len(prerequisites)} step(s) only an administrator can do: "
                + ", ".join(p["id"] for p in prerequisites),
                "Acknowledge each with --acknowledge <id> once it is done. Acknowledgement is "
                "recorded, not checked, and does not gate writing: these are external grants this "
                "tool cannot see, and a gateway builds cleanly without them while failing to "
                "serve traffic.")

    if runner and target_id:
        findings.extend(_name_collision_check(Target.parse(target_id), runner))

    return findings


def _needed_secret_refs(plan: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if set(value) == {"$secretRef"}:
                found.append(value["$secretRef"])
                return
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for item in plan.get("items") or []:
        if item.get("status") in {"ready", "adapted"}:
            walk(item.get("target") or {})
    return sorted(set(found))


def _name_collision_check(target: Target, runner: Runner) -> list[dict[str, Any]]:
    """A same-named legacy service is a live hazard, not a hypothetical.

    Several CLI commands dispatch by name without `--ids`, and in a migration the
    source APIM and the target gateway plausibly share a name.
    """
    result = runner([
        "az", "resource", "show", "--subscription", target.subscription,
        "-g", target.resource_group, "-n", target.name,
        "--resource-type", "Microsoft.ApiManagement/service", "-o", "json",
    ], None)
    if result.ok and result.json():
        return [{
            "code": "nameCollision", "blocking": True,
            "message": (
                f"A Microsoft.ApiManagement/service named {target.name!r} exists in the same "
                "resource group. Commands that dispatch by name could resolve to it."
            ),
            "remedy": "Use a different gateway name.",
        }]
    # A read that failed is not a name that is free. `az resource show` exits
    # non-zero for a missing resource and for a missing permission alike, and
    # treating the second as the first reports a check that never ran as a
    # clean one -- on the question of whether commands could hit the source
    # APIM instead of the target.
    noise = f"{result.stderr} {result.stdout}".lower()
    if not result.ok and not any(
        token in noise for token in ("resourcenotfound", "not found", "could not be found")
    ):
        return [{
            "code": "nameCollisionUnknown", "blocking": False,
            "message": (
                f"Whether a Microsoft.ApiManagement/service named {target.name!r} already exists "
                f"could not be established: {(result.stderr or result.stdout).strip()[:200]}"
            ),
            "remedy": (
                "Check by hand with `az resource show --resource-type "
                "Microsoft.ApiManagement/service`, then acknowledge prereq:name-collision."
            ),
        }]
    return []


# ------------------------------------------------------------------- journal


def new_journal(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "apimMigrationJournal",
        "target": (plan.get("target") or {}).get("resourceId"),
        "source": (plan.get("source") or {}).get("resourceId"),
        "startedAt": _now(),
        "updatedAt": _now(),
        "acknowledged": [],
        "phases": {},
        "steps": [],
    }


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def steps_for(plan: dict[str, Any]) -> list[Step]:
    """Executable steps, in dependency order."""
    steps: list[Step] = []
    for item in plan.get("items") or []:
        if item.get("status") not in {"ready", "adapted"}:
            continue
        capability_id = item.get("capabilityId")
        target = item.get("target") or {}
        if not capability_id or not target.get("objects"):
            continue
        phase = _PHASE_FOR_CAPABILITY.get(capability_id)
        if not phase or capability_id not in _BUILDERS:
            # Planned, but this tool cannot perform it. Surfaced by preflight as
            # manual work rather than becoming a step that fails at execution.
            continue
        objects = [dict(obj) for obj in target["objects"]]
        if item.get("decision") is not None:
            # A step may need the decision itself, not just the objects it shaped
            # at planning time -- which identity to assign, for instance.
            for obj in objects:
                obj.setdefault("decision", item["decision"])
        steps.append(Step(item_id=item["id"], capability_id=capability_id, phase=phase,
                          objects=objects))
    return sorted(steps, key=lambda step: PHASES.index(step.phase))


# ------------------------------------------------------------------ executor


class Executor:
    def __init__(
        self,
        plan: dict[str, Any],
        inventory: dict[str, Any],
        journal: dict[str, Any],
        *,
        runner: Runner | None = None,
        arm_client: Any = None,
        execute: bool = False,
        skip_rehearsal: bool = False,
    ) -> None:
        self.plan = plan
        self.inventory = inventory
        self.journal = journal
        self.runner = runner or _run
        self.arm = arm_client
        # Writes are consequential and there is no transaction, so a run is a
        # rehearsal unless asked otherwise.
        self.execute = execute
        self.skip_rehearsal = skip_rehearsal
        # Why a model lookup came back empty, keyed by (provider, model).
        # None means established as absent; a string is the reason the question
        # could not be answered.
        self._lookup_failures: dict[tuple[str | None, str | None], str | None] = {}
        self.target = Target.parse((plan.get("target") or {}).get("resourceId") or "")
        self.secrets = {entry["id"]: entry for entry in inventory.get("secrets") or []}

    # -- phases ---------------------------------------------------------

    def phase_complete(self, phase: str) -> bool:
        """Derived, never stored.

        A phase is complete when every step in it is done. Trusting a stored flag
        let a rehearsal -- which verifies nothing -- mark a phase done, so the
        execute pass skipped it and built on a gateway that was never created.

        "Done" includes a step this tool wrote but cannot read back. Requiring
        verification it is incapable of performing left the run stuck on a step
        that had in fact succeeded.
        """
        steps = [step for step in steps_for(self.plan) if step.phase == phase]
        if not steps:
            return True
        done = self.verified()
        return all(step.item_id in done for step in steps)

    def verified(self) -> set[str]:
        return {entry["itemId"] for entry in self.journal.get("steps") or []
                if entry.get("status") in {"verified", "unverified"}}

    def unverified(self) -> set[str]:
        return {entry["itemId"] for entry in self.journal.get("steps") or []
                if entry.get("status") == "unverified"}

    def rehearsed(self, phase: str) -> bool:
        return phase in (self.journal.get("rehearsals") or {})

    def next_phase(self) -> str | None:
        for phase in PHASES:
            steps = [step for step in steps_for(self.plan) if step.phase == phase]
            if steps and not self.phase_complete(phase):
                return phase
        return None

    def unperformable(self, phase: str) -> list[dict[str, str]]:
        """Work belonging to this phase that this tool cannot carry out.

        A phase reports on the steps it ran, so work it has no builder for is
        absent from that report. Running `policies` and being told only that it
        was rehearsed reads as the phase being covered, when the content-safety
        and token-limit items in it will simply never happen. Named here so the
        phase can say what it is leaving behind.
        """
        out = []
        for item in self.plan.get("items") or []:
            capability_id = item.get("capabilityId")
            if (_PHASE_FOR_CAPABILITY.get(capability_id or "") == phase
                    and item.get("status") in {"ready", "adapted"}
                    and (item.get("target") or {}).get("objects")
                    and capability_id not in _BUILDERS):
                out.append({"itemId": item["id"], "capabilityId": capability_id})
        return out

    def run_phase(self, phase: str) -> list[Step]:
        if phase not in PHASES:
            raise ApplyError(f"unknown phase {phase!r}; expected one of {', '.join(PHASES)}")
        if self.execute and not self.rehearsed(phase) and not self.skip_rehearsal:
            raise ApplyError(
                f"phase {phase!r} has not been rehearsed. Run it without --execute first to see "
                "the commands, or pass --skip-rehearsal to go straight to writing."
            )
        steps = [step for step in steps_for(self.plan) if step.phase == phase]
        for step in steps:
            self.run_step(step)
            if step.status in {"failed", "mutationUnknown"}:
                # Stop this phase rather than building on an unestablished state.
                break

        if not self.execute:
            # A rehearsal made no history. It records only that it happened, so
            # the execute pass can tell it was reviewed.
            self.journal.setdefault("rehearsals", {})[phase] = _now()
        else:
            self.journal.setdefault("phases", {})[phase] = {
                "status": "complete" if self.phase_complete(phase) else "stopped",
                "at": _now(),
                "steps": len(steps),
            }
        self._save()
        return steps

    # -- steps ----------------------------------------------------------

    def run_step(self, step: Step) -> Step:
        """Run every object this item produces, stopping at the first that sticks.

        One item can create several objects -- an API with two models publishes
        two aliases -- so executing only the first would quietly under-provision.
        """
        previous = next((s for s in self.journal["steps"] if s["itemId"] == step.item_id), None)
        digest = _objects_digest(step.objects)
        if previous and previous.get("status") == "verified":
            if previous.get("objectsDigest") in (None, digest):
                step.status, step.detail = "verified", "already recorded as verified"
                return step
            # The item kept its id but now asks for something else, so the old
            # verification was of a different thing and proves nothing about this.
            step.detail = "re-checking: the plan now asks for something different"

        outcomes: list[str] = []
        details: list[str] = []
        for obj in step.objects:
            status, detail, argv = self._run_object(step, obj)
            outcomes.append(status)
            if argv:
                step.commands.append(argv)
                if not step.argv:
                    step.argv = argv
            if detail:
                details.append(detail)
            if status in {"failed", "mutationUnknown"}:
                break

        for bad in ("mutationUnknown", "failed", "unverified"):
            if bad in outcomes:
                step.status = bad
                break
        else:
            step.status = "planned" if "planned" in outcomes else "verified"
        step.detail = "; ".join(dict.fromkeys(details))[:400]
        if len(step.objects) > 1:
            step.detail = f"{len(outcomes)}/{len(step.objects)} objects: {step.detail}"
        if self.execute:
            self._record(step)
        return step

    def _run_object(self, step: Step, obj: dict[str, Any]) -> tuple[str, str, list[str]]:
        desired = _DESIRED.get(step.capability_id, lambda _e, o: o)(self, obj)
        note = "; its credential is write-only and was not read back" if _has_write_only(obj) else ""

        # Verification establishes what a read can carry, and says which fields
        # that excludes rather than quietly narrowing what "verified" covers.
        unreadable = [
            field for field in _NOT_RETURNED.get(step.capability_id, ())
            if isinstance(desired, dict) and field in desired
        ]
        if unreadable:
            desired = {k: v for k, v in desired.items() if k not in unreadable}
            note += f"; {', '.join(unreadable)} is not returned by a read and was not compared"

        # Whatever is left has to constrain something. If dropping the unreadable
        # fields -- or the plan itself -- leaves nothing to check, a read-back
        # proves only that an object is there, and saying "verified" would be a
        # claim about its configuration that nothing established.
        checkable = _comparable(desired)
        if not checkable:
            note += "; nothing in this object can be checked against a read"

        # Read first, and build second. Building resolves credentials, so doing it
        # up front would read a secret for a step that turns out to need no write
        # at all -- the commonest case on a re-run.
        try:
            observed = self._read(step, obj)
        except (ApplyError, ResolveError) as exc:
            return "failed", str(exc), []
        if observed is not None and checkable and _subset(desired, observed):
            return "verified", "already present with the desired state" + note, []

        try:
            argv, files = self._build(step, obj)
        except (ApplyError, ResolveError) as exc:
            return "failed", str(exc), []
        redacted = _redact(argv)
        try:
            if not self.execute:
                return "planned", "dry run; not executed", redacted

            result = self.runner(argv, None)
            if not result.ok:
                return "failed", (result.stderr or result.stdout).strip()[:300], redacted

            observed = self._read(step, obj)
            if observed is None:
                if step.capability_id not in _READERS:
                    # The write succeeded and this tool has no way to read it
                    # back. That is not the same as not knowing whether it
                    # happened, and conflating them blocked the phase forever.
                    return ("unverified",
                            "written, but this tool cannot read it back to confirm it", redacted)
                return ("mutationUnknown",
                        "the write returned success but the object could not be read back",
                        redacted)
            if not checkable:
                return "unverified", "written, and read back; nothing in it could be " \
                                     "compared against the plan" + note, redacted
            if _subset(desired, observed):
                return "verified", "created and read back" + note, redacted
            return "failed", "the object exists but does not match the desired state", redacted
        finally:
            for path in files:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    # -- command construction -------------------------------------------

    def _build(self, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
        builder = _BUILDERS.get(step.capability_id)
        if not builder:
            raise ApplyError(f"no command builder for {step.capability_id}")
        argv, files = builder(self, step, obj)
        # The capability catalogue says which options the command requires. An
        # argv missing one would be rejected by the CLI with a less useful
        # message, after the step had already been counted as attempted.
        required = _REQUIRED_FLAGS.get(step.capability_id) or []
        missing = [flag for flag in required if f"--{flag}" not in argv]
        if missing:
            for path in files:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            raise ApplyError(
                f"{step.item_id} cannot be built: the plan supplies no "
                + ", ".join(f"--{flag}" for flag in missing)
                + ". Re-collect the inventory, or settle the item that provides it."
            )
        return argv, files

    def _read(self, step: Step, obj: dict[str, Any]) -> dict[str, Any] | None:
        reader = _READERS.get(step.capability_id)
        if not reader:
            return None
        argv = reader(self, step, obj)
        result = self.runner(argv, None)
        return result.json() if result.ok else None

    def _model_resource_id(self, provider: str | None, model: str | None) -> str | None:
        """Read a registered model's ARM id from the gateway.

        Records why a lookup came back empty. The caller turns None into "no
        such model, run the models phase first", which is a diagnosis -- and
        the wrong one if the read failed for an access or transport reason,
        sending the operator to re-run a phase that had already worked.
        """
        if not provider or not model:
            return None
        result = self.runner([
            "az", "aigateway", "model", "show", *self.target.selectors,
            "--gateway-name", self.target.name, "--provider-name", provider,
            "-n", model, "--query", "id", "-o", "tsv",
        ], None)
        value = (result.stdout or "").strip()
        if result.ok and value and value != "null":
            return value
        noise = f"{result.stderr} {result.stdout}".lower()
        absent = any(
            token in noise for token in ("notfound", "not found", "could not be found")
        ) or (result.ok and not value)
        self._lookup_failures[(provider, model)] = None if absent else (
            (result.stderr or result.stdout).strip()[:200] or "the read returned no id"
        )
        return None

    def _json_file(self, payload: dict[str, Any]) -> str:
        """Write a structured argument out, resolving any credential just in time.

        Secrets reach `az` only as `@file` with mode 0600, never as scalar flags,
        because scalar flags expose values in process arguments.
        """
        resolved = self._resolve_secrets(payload)
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.chmod(path, 0o600)
        Path(path).write_text(json.dumps(resolved), encoding="utf-8")
        return path

    def _resolve_secrets(self, value: Any) -> Any:
        if isinstance(value, dict):
            if set(value) == {"$secretRef"}:
                ref = self.secrets.get(value["$secretRef"])
                if not ref:
                    raise ApplyError(f"{value['$secretRef']} is not in the inventory")
                if not self.execute:
                    return "<resolved at apply time>"
                if not self.arm:
                    raise ApplyError("no ARM client available to resolve a credential")
                return resolve_secret(self.arm, ref)
            return {key: self._resolve_secrets(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_secrets(item) for item in value]
        return value

    # -- journal --------------------------------------------------------

    def _record(self, step: Step) -> None:
        entry = step.to_dict()
        entry["at"] = _now()
        entry["objectsDigest"] = _objects_digest(step.objects)
        existing = next((s for s in self.journal["steps"] if s["itemId"] == step.item_id), None)
        if existing:
            self.journal["steps"][self.journal["steps"].index(existing)] = entry
        else:
            self.journal["steps"].append(entry)
        self.journal["updatedAt"] = _now()

    def _save(self) -> None:
        path = self.journal.get("_path")
        if path:
            payload = {k: v for k, v in self.journal.items() if not k.startswith("_")}
            Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ builders


def _gateway_create(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    location = spec.get("location") or (executor.inventory.get("service") or {}).get("location")
    if not location:
        raise ApplyError("the gateway needs a location and the inventory records none")
    return ([
        "az", "aigateway", "create", *executor.target.selectors,
        "-n", executor.target.name, "--location", location, "-o", "json",
    ], [])


def _identity_assign(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Assign the identity the providers will authenticate as.

    Reusing the source's user-assigned identity carries its existing backend
    grants; a system-assigned one is a new principal that must be granted.
    """
    argv = [
        "az", "aigateway", "identity", "assign", *executor.target.selectors,
        "-n", executor.target.name,
    ]
    user_assigned = _identity_choice(obj)
    if user_assigned:
        argv += ["--user-assigned", *user_assigned]
    else:
        argv += ["--system-assigned", "true"]
    return argv + ["-o", "json"], []


def _provider_create(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    kind = spec.get("kind") or "Custom"
    settings = spec.get("foundry") if kind == "Foundry" else spec.get("custom")
    path = executor._json_file(settings or {})
    flag = "--foundry" if kind == "Foundry" else "--custom"
    return ([
        "az", "aigateway", "model-provider", "create", *executor.target.selectors,
        "--gateway-name", executor.target.name, "-n", spec["name"],
        "--kind", kind, flag, f"@{path}", "-o", "json",
    ], [path])


def _model_create(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    provider = spec.get("providerName")
    if not provider:
        raise ApplyError(f"{step.item_id} does not say which provider to register under")
    path = executor._json_file(spec.get("deploymentConfig") or {})
    argv = [
        "az", "aigateway", "model", "create", *executor.target.selectors,
        "--gateway-name", executor.target.name, "--provider-name", provider,
        "-n", spec["name"], "--deployment-config", f"@{path}",
    ]
    if spec.get("apiFormat"):
        argv += ["--api-format", spec["apiFormat"]]
    # `--supported-endpoints` takes space-separated values, not a repeatable
    # flag: repeating it keeps only the last, which silently registered a model
    # on one route when the plan asked for several.
    endpoints = spec.get("supportedEndpoints") or []
    if endpoints:
        argv += ["--supported-endpoints", *endpoints]
    return argv + ["-o", "json"], [path]


def _alias_set(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    # `model-alias set` is the one documented create-or-update, which is what
    # makes an alias step safe to repeat.
    argv = [
        "az", "aigateway", "model-alias", "set", *executor.target.selectors,
        "--gateway-name", executor.target.name, "-n", _alias_name(spec),
        "--routing-name", spec["routingName"],
    ]
    for backend in spec.get("backendModels") or []:
        # A model's ARM id only exists once the models phase has created it, so it
        # is read from the gateway here rather than guessed at planning time.
        resource_id = backend.get("resourceId") or executor._model_resource_id(
            backend.get("providerName"), backend.get("modelName")
        )
        if not resource_id and not executor.execute:
            # Nothing has been created in a rehearsal, so an unresolved id is
            # expected rather than a fault. Showing the shape is the useful thing.
            # Space-free: this sits inside a shorthand object, where a space
            # ends the token and would make the rehearsed command unusable if
            # an operator pasted it.
            # Qualified by provider: a pooled alias fronts the same model name in
            # several accounts, and an unqualified placeholder showed the
            # operator what looked like the same backend listed twice.
            resource_id = (f"<resolved-at-apply-time:{backend.get('providerName')}"
                           f"/{backend.get('modelName')}>")
        if not resource_id:
            why = executor._lookup_failures.get(
                (backend.get("providerName"), backend.get("modelName"))
            )
            raise ApplyError(
                f"{step.item_id}: could not resolve a model named {backend.get('modelName')!r} "
                f"under provider {backend.get('providerName')!r}: {why}"
                if why else
                f"{step.item_id}: no registered model named {backend.get('modelName')!r} under "
                f"provider {backend.get('providerName')!r}; run the models phase first"
            )
        # `--backend-model` is an az CLI shorthand *object*: it needs brace form,
        # `{key:value,...}`, in a single token. Both `resource-id=<id> priority=0`
        # and `resource-id=<id>,priority=0` are read as one bare resource id, and
        # the service then rejects a model whose id has the other fields glued on.
        argv += ["--backend-model",
                 "{{resource-id:{id},priority:{p},weight:{w}}}".format(
                     id=resource_id,
                     p=backend.get("priority", 0),
                     w=backend.get("weight", 100),
                 )]
    return argv + ["-o", "json"], []


def _mcp_create(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    path = executor._json_file(spec.get("endpoints") or [])
    return ([
        "az", "aigateway", "mcp", "create", *executor.target.selectors,
        "--gateway-name", executor.target.name, "-n", spec["name"],
        "--endpoints", f"@{path}", "-o", "json",
    ], [path])


def _identity_choice(obj: dict[str, Any]) -> list[str]:
    """Which identity this step assigns, honouring a settled reuse decision."""
    decision = str(obj.get("decision") or "")
    if decision.startswith("reuse:"):
        return [decision.split("reuse:", 1)[1]]
    return list(obj.get("userAssigned") or [])


def _identity_desired(executor: Executor, obj: dict[str, Any]) -> dict[str, Any]:
    """What `identity show` should report once this step has run.

    The planned object says what to assign; verification needs what the read
    returns. Comparing the two directly never matched, so the step could not be
    verified however many times it succeeded.
    """
    return {"type": "UserAssigned" if _identity_choice(obj) else "SystemAssigned"}


def _model_desired(executor: Executor, obj: dict[str, Any]) -> dict[str, Any]:
    """A model registration as `model show` returns it.

    The command takes --deployment-config and --provider-name; the read reports
    the first as `deployment` and the second only in the resource path, which
    the reader already selects on. Comparing the sent shape against the
    returned one failed on both for every model, however correctly created.
    """
    return {
        "name": obj["name"],
        "deployment": obj.get("deploymentConfig") or {},
        "supportedEndpoints": obj.get("supportedEndpoints") or [],
        "apiFormat": obj.get("apiFormat"),
    }


def _alias_desired(executor: Executor, obj: dict[str, Any]) -> dict[str, Any]:
    """An alias as `model-alias show` returns it.

    The read reports `aliasName` for what was sent as --routing-name, and each
    backend model as a bare resourceId -- never the modelName, providerName,
    priority or weight the command carried. The id is what establishes that the
    alias points at the intended model, so an unresolved one is held as a value
    that cannot match rather than dropped: a shorter list would compare clean
    and verify nothing.
    """
    backends = []
    for backend in obj.get("backendModels") or []:
        resource_id = backend.get("resourceId") or executor._model_resource_id(
            backend.get("providerName"), backend.get("modelName")
        )
        backends.append({
            "resourceId": resource_id
            or f"<unresolved model {backend.get('modelName')!r}>"
        })
    desired: dict[str, Any] = {
        "aliasName": obj["routingName"],
        "supportedEndpoints": obj.get("supportedEndpoints") or [],
    }
    if backends:
        desired["backendModels"] = backends
    return desired


def _alias_name(spec: dict[str, Any]) -> str:
    return spec.get("name") or str(spec["routingName"]).replace("/", "-").replace(".", "-")


_BUILDERS: dict[str, Callable[[Executor, Step, dict[str, Any]], tuple[list[str], list[str]]]] = {
    "gateway.create": _gateway_create,
    "identity.assign": _identity_assign,
    "provider.create": _provider_create,
    "model.create": _model_create,
    "alias.create": _alias_set,
    "mcp.create": _mcp_create,
}

# Where the object a step plans and the object its read returns are different
# shapes, this translates one into the other for verification.
_DESIRED: dict[str, Callable[[Executor, dict[str, Any]], dict[str, Any]]] = {
    "identity.assign": _identity_desired,
    "model.create": _model_desired,
    "alias.create": _alias_desired,
}

# Fields the control plane accepts on write and never returns on read. They are
# dropped before comparison for the same reason a credential is: the read cannot
# carry them, so comparing can only fail, and a correctly created object would
# be reported as not matching its plan.
#
# `model show` on a live gateway returns deployment, displayName, endpoints,
# providerKind and supportedEndpoints -- apiFormat is accepted by `model create`
# and absent from every read.
_NOT_RETURNED: dict[str, tuple[str, ...]] = {
    "model.create": ("apiFormat",),
}

# Options the catalogue marks required, checked before a command is run.
_REQUIRED_FLAGS = {
    "model.create": ["deployment-config", "api-format", "supported-endpoints"],
    "provider.create": ["kind"],
    "alias.create": ["routing-name", "backend-model"],
    "mcp.create": ["endpoints"],
    "gateway.create": ["location"],
}

_READERS: dict[str, Callable[[Executor, Step, dict[str, Any]], list[str]]] = {
    "gateway.create": lambda e, s, o: ["az", "aigateway", "show", *e.target.selectors,
                                     "-n", e.target.name, "-o", "json"],
    "provider.create": lambda e, s, o: ["az", "aigateway", "model-provider", "show", *e.target.selectors,
                                      "--gateway-name", e.target.name, "-n", o["name"],
                                      "-o", "json"],
    "model.create": lambda e, s, o: ["az", "aigateway", "model", "show", *e.target.selectors,
                                   "--gateway-name", e.target.name,
                                   "--provider-name", o.get("providerName", ""),
                                   "-n", o["name"], "-o", "json"],
    "alias.create": lambda e, s, o: ["az", "aigateway", "model-alias", "show", *e.target.selectors,
                                   "--gateway-name", e.target.name, "-n", _alias_name(o),
                                   "-o", "json"],
    "identity.assign": lambda e, s, o: ["az", "aigateway", "identity", "show", *e.target.selectors,
                                        "-n", e.target.name, "-o", "json"],
    "mcp.create": lambda e, s, o: ["az", "aigateway", "mcp", "show", *e.target.selectors,
                                 "--gateway-name", e.target.name, "-n", o["name"],
                                 "-o", "json"],
}


# ------------------------------------------------------------------- helpers


def _run(argv: list[str], _payload: dict[str, Any] | None = None) -> CommandResult:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return CommandResult(127, "", "the Azure CLI is not on PATH")
    except subprocess.TimeoutExpired:
        # Unestablished, not failed: the service may have accepted the write.
        return CommandResult(124, "", "the command timed out before reporting an outcome")
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def _objects_digest(objects: list[dict[str, Any]]) -> str:
    """What a step was verified against, so a later plan change re-checks it."""
    canonical = json.dumps(objects, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _redact(argv: list[str]) -> list[str]:
    """Record what was run without recording what it carried."""
    return [part if not part.startswith("@/") else "@<tempfile>" for part in argv]


def _has_write_only(value: Any) -> bool:
    """Whether anything in this object is a field a read can never confirm."""
    if write_only(value):
        return True
    if isinstance(value, dict):
        return any(_has_write_only(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_write_only(item) for item in value)
    return False


def write_only(value: Any) -> bool:
    """A field the control plane accepts but never returns.

    A credential is the obvious case: the API takes `apiKey.value` on write and
    omits it on every read, by design. Comparing it against a read-back can only
    ever fail, so a correctly configured provider reported as mismatched.
    """
    if isinstance(value, dict) and set(value) == {"$secretRef"}:
        return True
    return value == "<resolved at apply time>"


def _comparable(desired: Any) -> bool:
    """Whether this desired shape actually constrains anything.

    `_subset` answers "is every wanted field present with that value", so a
    shape with no wanted fields is satisfied by any object at all. Letting that
    count as verification would pass a step that checked nothing, which is the
    one thing a read-back exists to rule out.
    """
    if write_only(desired):
        return False
    if isinstance(desired, dict):
        return any(_comparable(value) for value in desired.values())
    if isinstance(desired, list):
        return any(_comparable(value) for value in desired)
    return desired is not None


def _subset(desired: Any, observed: Any) -> bool:
    """Whether every field asked for is present with that value.

    Write-only fields are skipped rather than compared: verification establishes
    what can be read, and a secret is deliberately not among it.
    """
    if write_only(desired):
        return True
    if isinstance(desired, dict):
        if not isinstance(observed, dict):
            return False
        lowered = {str(k).lower(): v for k, v in observed.items()}
        properties = lowered.get("properties")
        for key, value in desired.items():
            key_l = str(key).lower()
            if write_only(value):
                # Absent from the read because the API never returns it, which is
                # not the same as missing. Checking for its key would fail every
                # correctly configured credential.
                continue
            if key_l in lowered:
                if not _subset(value, lowered[key_l]):
                    return False
            elif isinstance(properties, dict) and key_l in {str(k).lower() for k in properties}:
                match = next(v for k, v in properties.items() if str(k).lower() == key_l)
                if not _subset(value, match):
                    return False
            else:
                return False
        return True
    if isinstance(desired, list):
        # Every wanted element must be satisfied by a distinct observed one.
        # Comparing lengths made this a check in name only: an alias pointing at
        # a completely different model verified cleanly.
        if not isinstance(observed, list):
            return False
        remaining = list(observed)
        for want in desired:
            if write_only(want):
                continue
            for index, got in enumerate(remaining):
                if _subset(want, got):
                    remaining.pop(index)
                    break
            else:
                return False
        return True
    if isinstance(desired, str) and isinstance(observed, str):
        return desired.lower() == observed.lower()
    return desired == observed
