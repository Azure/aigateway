import copy
import json

import pytest

from apim_import.apply import (
    ApplyError,
    CommandResult,
    Executor,
    PHASES,
    Target,
    new_journal,
    preflight,
    steps_for,
)
from apim_import.capability import CapabilityMap
from apim_import.collect import Collector, CollectOptions
from apim_import.plan import build_plan
from fake_arm import SERVICE, FakeArmClient

TARGET = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo/providers/Microsoft.ApiManagement/aigateways/gw"


def options(**overrides):
    overrides.setdefault("cognitive_api_version", "2025-06-01")
    return CollectOptions(**overrides)


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE, options()).run()


@pytest.fixture
def settled(inventory):
    plan = build_plan(copy.deepcopy(inventory), CapabilityMap.load(), target=TARGET)
    for item in plan["items"]:
        if item["status"] == "needs-decision":
            item["status"] = "adapted"
            item["decision"] = item["proposal"] or "accept"
    return plan


class _Runner:
    """A canned az. Records every argv and serves scripted replies."""

    def __init__(self, reads=None, writes_ok=True):
        self.calls: list[list[str]] = []
        self.reads = reads if reads is not None else {}
        self.writes_ok = writes_ok

    def __call__(self, argv, _payload=None):
        self.calls.append(argv)
        verb = argv[2] if len(argv) > 2 else ""
        is_read = "show" in argv
        if is_read:
            key = argv[argv.index("-n") + 1] if "-n" in argv else verb
            value = self.reads.get(key)
            return CommandResult(0 if value else 1, json.dumps(value) if value else "")
        if "resource" in argv[:2]:
            return CommandResult(1, "")  # no name collision
        return CommandResult(0 if self.writes_ok else 1, "{}", "" if self.writes_ok else "boom")


class TestTarget:
    def test_a_gateway_id_parses(self):
        target = Target.parse(TARGET)
        assert (target.resource_group, target.name) == ("rg-demo", "gw")

    def test_a_legacy_service_id_is_refused(self):
        with pytest.raises(ApplyError, match="aigateways"):
            Target.parse("/subscriptions/s/resourceGroups/rg/providers/Microsoft.ApiManagement/service/x")


class TestPreflight:
    def test_a_plan_with_no_target_cannot_be_applied(self, inventory):
        plan = build_plan(inventory, CapabilityMap.load())
        codes = {f["code"] for f in preflight(plan, inventory) if f["blocking"]}
        assert "noTarget" in codes

    def test_unsettled_items_block(self, inventory):
        plan = build_plan(inventory, CapabilityMap.load(), target=TARGET)
        codes = {f["code"] for f in preflight(plan, inventory) if f["blocking"]}
        assert "unsettled" in codes

    def test_orphaned_decisions_block(self, inventory, settled):
        plan = copy.deepcopy(settled)
        plan["orphanedDecisions"] = [{"id": "item:x", "decision": "v", "note": "n"}]
        codes = {f["code"] for f in preflight(plan, inventory) if f["blocking"]}
        assert "orphanedDecisions" in codes

    def test_a_settled_plan_has_no_blocking_findings(self, inventory, settled):
        assert [f for f in preflight(settled, inventory) if f["blocking"]] == []

    def test_manual_prerequisites_are_raised_but_do_not_block(self, inventory, settled):
        notes = [f for f in preflight(settled, inventory) if not f["blocking"]]
        assert any(f["code"] == "prerequisites" for f in notes)

    def test_a_same_named_legacy_service_blocks(self, inventory, settled):
        def runner(argv, _payload=None):
            return CommandResult(0, json.dumps({"id": "/x", "type": "Microsoft.ApiManagement/service"}))

        codes = {f["code"] for f in preflight(settled, inventory, runner=runner) if f["blocking"]}
        assert "nameCollision" in codes

    def test_an_unretrievable_credential_blocks(self, inventory, settled):
        broken = copy.deepcopy(inventory)
        for entry in broken["secrets"]:
            entry["retrievable"] = False
        codes = {f["code"] for f in preflight(settled, broken) if f["blocking"]}
        assert "secretNotRetrievable" in codes


class TestPhases:
    def test_steps_come_out_in_dependency_order(self, settled):
        phases = [step.phase for step in steps_for(settled)]
        assert phases == sorted(phases, key=PHASES.index)

    def test_the_gateway_comes_before_everything(self, settled):
        steps = steps_for(settled)
        assert steps[0].phase == "gateway"

    def test_only_settled_items_become_steps(self, inventory):
        plan = build_plan(inventory, CapabilityMap.load(), target=TARGET)
        assert all(
            next(i for i in plan["items"] if i["id"] == step.item_id)["status"] in {"ready", "adapted"}
            for step in steps_for(plan)
        )

    def test_next_phase_skips_completed_ones(self, inventory, settled):
        journal = new_journal(settled)
        journal["phases"] = {"gateway": {"status": "complete"}}
        executor = Executor(settled, inventory, journal, runner=_Runner())
        assert executor.next_phase() == "identity"

    def test_a_gateway_whose_providers_use_an_identity_gets_one(self, settled):
        # Regression: nothing emitted identity.assign, so the identity phase was
        # always empty and Foundry providers were configured against a principal
        # that did not exist.
        identity = [s for s in steps_for(settled) if s.capability_id == "identity.assign"]
        assert identity, "no identity step for providers that authenticate as one"
        assert identity[0].phase == "identity"

    def test_the_identity_is_assigned_before_any_provider(self, settled):
        phases = [step.phase for step in steps_for(settled)]
        assert phases.index("identity") < phases.index("providers")


class TestRehearsal:
    def test_a_rehearsal_writes_nothing(self, inventory, settled):
        runner = _Runner()
        executor = Executor(settled, inventory, new_journal(settled), runner=runner)
        executor.run_phase("providers")
        assert all("create" not in argv or "show" in argv for argv in runner.calls)

    def test_a_rehearsal_reports_the_command_it_would_run(self, inventory, settled):
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner())
        [step] = [s for s in executor.run_phase("gateway") if s.capability_id == "gateway.create"]
        assert step.status == "planned"
        assert "aigateway" in step.argv and "create" in step.argv

    def test_a_credential_never_appears_in_a_recorded_argv(self, inventory, settled):
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner())
        for phase in ("providers", "toolServers"):
            for step in executor.run_phase(phase):
                assert not any(part.startswith("@/tmp") for part in step.argv)
                assert "@<tempfile>" in step.argv or all("@" not in p for p in step.argv)


class TestExecution:
    def test_an_object_already_in_the_desired_state_is_not_written(self, inventory, settled):
        # Read before write is what makes a re-run safe after an ambiguous failure.
        runner = _Runner(reads={"gw": {"name": "gw", "location": "West US 2"}})
        executor = Executor(settled, inventory, new_journal(settled), runner=runner, execute=True)
        [step] = [s for s in executor.run_phase("gateway") if s.capability_id == "gateway.create"]
        assert step.status == "verified"
        assert not any("create" in argv for argv in runner.calls)

    def test_a_write_that_cannot_be_read_back_is_unknown_not_successful(self, inventory, settled):
        runner = _Runner(reads={})  # every read fails
        executor = Executor(settled, inventory, new_journal(settled), runner=runner, execute=True)
        [step] = [s for s in executor.run_phase("gateway") if s.capability_id == "gateway.create"]
        assert step.status == "mutationUnknown"
        assert "could not be read back" in step.detail

    def test_a_failed_write_stops_the_phase(self, inventory, settled):
        runner = _Runner(writes_ok=False)
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=runner, execute=True)
        executor.run_phase("providers")
        assert journal["phases"]["providers"]["status"] == "stopped"

    def test_an_item_with_several_objects_runs_all_of_them(self, inventory, settled):
        # An API with two models publishes two aliases; running only the first
        # would quietly under-provision.
        multi = [s for s in steps_for(settled) if len(s.objects) > 1]
        assert multi, "fixture no longer has a multi-object item"
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner())
        step = executor.run_step(multi[0])
        assert step.detail.startswith(f"{len(multi[0].objects)}/{len(multi[0].objects)} objects")


class TestJournal:
    def test_a_verified_step_is_not_repeated(self, inventory, settled):
        journal = new_journal(settled)
        steps = steps_for(settled)
        journal["steps"].append({"itemId": steps[0].item_id, "status": "verified", "detail": ""})
        runner = _Runner()
        executor = Executor(settled, inventory, journal, runner=runner, execute=True)
        step = executor.run_step(steps[0])
        assert step.status == "verified"
        assert runner.calls == []

    def test_the_journal_records_every_attempt(self, inventory, settled):
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=_Runner())
        executor.run_phase("providers")
        assert journal["steps"]
        assert all("at" in entry for entry in journal["steps"])

    def test_the_journal_names_the_source_it_came_from(self, settled):
        journal = new_journal(settled)
        assert journal["source"] == settled["source"]["resourceId"]
        assert journal["target"] == TARGET
