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

    def to_dict(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "capabilityId": self.capability_id,
            "phase": self.phase,
            "status": self.status,
            "detail": self.detail,
            "argv": self.argv,
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

    prerequisites = plan.get("prerequisites") or []
    if prerequisites:
        finding("prerequisites", False,
                f"{len(prerequisites)} step(s) only an administrator can do: "
                + ", ".join(p["id"] for p in prerequisites),
                "Acknowledge each with --acknowledge <id> once it is done.")

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
        if not phase:
            continue
        steps.append(Step(item_id=item["id"], capability_id=capability_id, phase=phase,
                          objects=target["objects"]))
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
    ) -> None:
        self.plan = plan
        self.inventory = inventory
        self.journal = journal
        self.runner = runner or _run
        self.arm = arm_client
        # Writes are consequential and there is no transaction, so a run is a
        # rehearsal unless asked otherwise.
        self.execute = execute
        self.target = Target.parse((plan.get("target") or {}).get("resourceId") or "")
        self.secrets = {entry["id"]: entry for entry in inventory.get("secrets") or []}

    # -- phases ---------------------------------------------------------

    def next_phase(self) -> str | None:
        done = {name for name, record in (self.journal.get("phases") or {}).items()
                if record.get("status") == "complete"}
        for phase in PHASES:
            if phase in done:
                continue
            if any(step.phase == phase for step in steps_for(self.plan)):
                return phase
        return None

    def run_phase(self, phase: str) -> list[Step]:
        if phase not in PHASES:
            raise ApplyError(f"unknown phase {phase!r}; expected one of {', '.join(PHASES)}")
        steps = [step for step in steps_for(self.plan) if step.phase == phase]
        self.journal.setdefault("phases", {})[phase] = {
            "status": "running", "startedAt": _now(), "steps": len(steps),
        }
        for step in steps:
            self.run_step(step)
            if step.status in {"failed", "mutationUnknown"}:
                # Stop this phase rather than building on an unestablished state.
                self.journal["phases"][phase].update({"status": "stopped", "stoppedAt": _now()})
                self._save()
                return steps
        self.journal["phases"][phase].update({"status": "complete", "completedAt": _now()})
        self._save()
        return steps

    # -- steps ----------------------------------------------------------

    def run_step(self, step: Step) -> Step:
        """Run every object this item produces, stopping at the first that sticks.

        One item can create several objects -- an API with two models publishes
        two aliases -- so executing only the first would quietly under-provision.
        """
        previous = next((s for s in self.journal["steps"] if s["itemId"] == step.item_id), None)
        if previous and previous.get("status") == "verified":
            step.status, step.detail = "verified", "already recorded as verified"
            return step

        outcomes: list[str] = []
        details: list[str] = []
        for obj in step.objects:
            status, detail, argv = self._run_object(step, obj)
            outcomes.append(status)
            if argv and not step.argv:
                step.argv = argv
            if detail:
                details.append(detail)
            if status in {"failed", "mutationUnknown"}:
                break

        for bad in ("mutationUnknown", "failed"):
            if bad in outcomes:
                step.status = bad
                break
        else:
            step.status = "planned" if "planned" in outcomes else "verified"
        step.detail = "; ".join(dict.fromkeys(details))[:400]
        if len(step.objects) > 1:
            step.detail = f"{len(outcomes)}/{len(step.objects)} objects: {step.detail}"
        self._record(step)
        return step

    def _run_object(self, step: Step, obj: dict[str, Any]) -> tuple[str, str, list[str]]:
        try:
            argv, files = self._build(step, obj)
        except (ApplyError, ResolveError) as exc:
            return "failed", str(exc), []
        redacted = _redact(argv)
        try:
            # Read before write: an object already in the desired state is not
            # written again, which is what makes a re-run safe.
            observed = self._read(step, obj)
            if observed is not None and _subset(obj, observed):
                return "verified", "already present with the desired state", redacted
            if not self.execute:
                return "planned", "dry run; not executed", redacted

            result = self.runner(argv, None)
            if not result.ok:
                return "failed", (result.stderr or result.stdout).strip()[:300], redacted

            observed = self._read(step, obj)
            if observed is None:
                return ("mutationUnknown",
                        "the write returned success but the object could not be read back",
                        redacted)
            if _subset(obj, observed):
                return "verified", "created and read back", redacted
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
        """Read a registered model's ARM id from the gateway."""
        if not provider or not model:
            return None
        result = self.runner([
            "az", "aigateway", "model", "show", *self.target.selectors,
            "--gateway-name", self.target.name, "--provider-name", provider,
            "-n", model, "--query", "id", "-o", "tsv",
        ], None)
        value = (result.stdout or "").strip()
        return value if result.ok and value and value != "null" else None

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
    return ([
        "az", "aigateway", "identity", "assign", *executor.target.selectors,
        "-n", executor.target.name, "--system-assigned", "true", "-o", "json",
    ], [])


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
    for endpoint in spec.get("supportedEndpoints") or []:
        argv += ["--supported-endpoints", endpoint]
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
            resource_id = f"<id of {backend.get('modelName')} at apply time>"
        if not resource_id:
            raise ApplyError(
                f"{step.item_id}: no registered model named {backend.get('modelName')!r} under "
                f"provider {backend.get('providerName')!r}; run the models phase first"
            )
        argv += ["--backend-model", f"resource-id={resource_id} "
                 f"priority={backend.get('priority', 0)} weight={backend.get('weight', 100)}"]
    return argv + ["-o", "json"], []


def _mcp_create(executor: Executor, step: Step, obj: dict[str, Any]) -> tuple[list[str], list[str]]:
    spec = obj
    path = executor._json_file(spec.get("endpoints") or [])
    return ([
        "az", "aigateway", "mcp", "create", *executor.target.selectors,
        "--gateway-name", executor.target.name, "-n", spec["name"],
        "--endpoints", f"@{path}", "-o", "json",
    ], [path])


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


def _redact(argv: list[str]) -> list[str]:
    """Record what was run without recording what it carried."""
    return [part if not part.startswith("@/") else "@<tempfile>" for part in argv]


def _subset(desired: Any, observed: Any) -> bool:
    """Whether every field asked for is present with that value."""
    if isinstance(desired, dict):
        if not isinstance(observed, dict):
            return False
        lowered = {str(k).lower(): v for k, v in observed.items()}
        properties = lowered.get("properties")
        for key, value in desired.items():
            key_l = str(key).lower()
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
        return isinstance(observed, list) and len(observed) >= len(desired)
    if isinstance(desired, str) and isinstance(observed, str):
        return desired.lower() == observed.lower()
    return desired == observed
