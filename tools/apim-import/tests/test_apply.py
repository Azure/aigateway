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

    def test_next_phase_skips_phases_whose_steps_are_verified(self, inventory, settled):
        journal = new_journal(settled)
        gateway_steps = [s for s in steps_for(settled) if s.phase == "gateway"]
        journal["steps"] = [{"itemId": s.item_id, "status": "verified"} for s in gateway_steps]
        executor = Executor(settled, inventory, journal, runner=_Runner())
        assert executor.next_phase() == "identity"

    def test_a_phase_marked_complete_without_verified_steps_is_not_believed(self, inventory, settled):
        # Regression: a rehearsal wrote status complete, and the execute pass then
        # skipped the phase and built on a gateway that was never created.
        journal = new_journal(settled)
        journal["phases"] = {"gateway": {"status": "complete"}}
        executor = Executor(settled, inventory, journal, runner=_Runner())
        assert executor.next_phase() == "gateway"

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
        executor = Executor(settled, inventory, new_journal(settled), runner=runner, execute=True,
                            skip_rehearsal=True)
        [step] = [s for s in executor.run_phase("gateway") if s.capability_id == "gateway.create"]
        assert step.status == "verified"
        assert not any("create" in argv for argv in runner.calls)

    def test_a_write_that_cannot_be_read_back_is_unknown_not_successful(self, inventory, settled):
        runner = _Runner(reads={})  # every read fails
        executor = Executor(settled, inventory, new_journal(settled), runner=runner, execute=True,
                            skip_rehearsal=True)
        [step] = [s for s in executor.run_phase("gateway") if s.capability_id == "gateway.create"]
        assert step.status == "mutationUnknown"
        assert "could not be read back" in step.detail

    def test_a_failed_write_stops_the_phase(self, inventory, settled):
        runner = _Runner(writes_ok=False)
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=runner, execute=True,
                            skip_rehearsal=True)
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
        executor = Executor(settled, inventory, journal, runner=_Runner(), execute=True,
                            skip_rehearsal=True)
        executor.run_phase("providers")
        assert journal["steps"]
        assert all("at" in entry for entry in journal["steps"])

    def test_the_journal_names_the_source_it_came_from(self, settled):
        journal = new_journal(settled)
        assert journal["source"] == settled["source"]["resourceId"]
        assert journal["target"] == TARGET


class TestRehearsalLeavesNoState:
    """A rehearsal makes no history, so it cannot be mistaken for work done."""

    def test_a_rehearsal_records_no_phase_status(self, inventory, settled):
        journal = new_journal(settled)
        Executor(settled, inventory, journal, runner=_Runner()).run_phase("gateway")
        assert journal.get("phases") in (None, {})

    def test_a_rehearsal_records_no_steps(self, inventory, settled):
        journal = new_journal(settled)
        Executor(settled, inventory, journal, runner=_Runner()).run_phase("gateway")
        assert journal["steps"] == []

    def test_a_rehearsal_does_not_advance_the_next_phase(self, inventory, settled):
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=_Runner())
        first = executor.next_phase()
        executor.run_phase(first)
        assert executor.next_phase() == first

    def test_a_rehearsal_is_recorded_as_having_happened(self, inventory, settled):
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=_Runner())
        executor.run_phase("gateway")
        assert "gateway" in journal["rehearsals"]
        assert executor.rehearsed("gateway")

    def test_executing_an_unrehearsed_phase_is_refused(self, inventory, settled):
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner(), execute=True)
        with pytest.raises(ApplyError, match="has not been rehearsed"):
            executor.run_phase("gateway")

    def test_rehearsing_first_allows_the_execute_pass(self, inventory, settled):
        journal = new_journal(settled)
        Executor(settled, inventory, journal, runner=_Runner()).run_phase("gateway")
        runner = _Runner(reads={"gw": {"name": "gw", "location": "West US 2"}})
        executor = Executor(settled, inventory, journal, runner=runner, execute=True)
        [step] = executor.run_phase("gateway")
        assert step.status == "verified"


class TestEveryWriteCanBeChecked:
    """A capability the tool can write but not read back blocks a phase forever,
    because completeness is derived from what has been confirmed."""

    def test_every_builder_has_a_reader(self):
        from apim_import.apply import _BUILDERS, _READERS

        missing = sorted(set(_BUILDERS) - set(_READERS))
        assert missing == [], f"no read-back for: {', '.join(missing)}"

    def test_the_identity_read_shape_matches_what_is_planned(self):
        from apim_import.apply import _DESIRED, _subset

        desired = _DESIRED["identity.assign"]({"systemAssigned": True, "userAssigned": None})
        observed = {"principalId": "p", "tenantId": "t", "type": "SystemAssigned"}
        # The planned object and the read are different shapes; comparing them
        # directly never matched, so the step could never be verified.
        assert _subset(desired, observed)

    def test_reusing_a_user_assigned_identity_expects_that_type(self):
        from apim_import.apply import _DESIRED, _subset

        desired = _DESIRED["identity.assign"]({"decision": "reuse:/subscriptions/s/uami/one"})
        assert _subset(desired, {"type": "UserAssigned"})
        assert not _subset(desired, {"type": "SystemAssigned"})

    def test_an_unreadable_capability_does_not_block_the_run(self, inventory, settled):
        import apim_import.apply as mod

        reader = mod._READERS.pop("identity.assign")
        try:
            journal = new_journal(settled)
            Executor(settled, inventory, journal, runner=_Runner()).run_phase("identity")
            executor = Executor(settled, inventory, journal, runner=_Runner(), execute=True)
            [step] = executor.run_phase("identity")
            assert step.status == "unverified"
            assert "cannot read it back" in step.detail
            # It still counts as done, or the run would never move past it.
            assert executor.phase_complete("identity")
        finally:
            mod._READERS["identity.assign"] = reader


class TestWriteOnlyFields:
    """The control plane takes a credential on write and never returns it, so
    comparing one against a read-back can only ever fail."""

    def test_a_secret_placeholder_is_not_compared(self):
        from apim_import.apply import _subset

        desired = {"authentication": {"kind": "ApiKey", "apiKey": {
            "headerName": "Authorization", "value": {"$secretRef": "secret:namedValue/k"}}}}
        observed = {"authentication": {"kind": "ApiKey", "apiKey": {"headerName": "Authorization"}}}
        assert _subset(desired, observed)

    def test_the_fields_around_it_are_still_compared(self):
        from apim_import.apply import _subset

        desired = {"apiKey": {"headerName": "Authorization", "value": {"$secretRef": "x"}}}
        assert not _subset(desired, {"apiKey": {"headerName": "api-key"}})

    def test_a_rehearsal_placeholder_is_also_write_only(self):
        from apim_import.apply import write_only

        assert write_only("<resolved at apply time>")
        assert write_only({"$secretRef": "secret:namedValue/k"})
        assert not write_only({"headerName": "Authorization"})

    def test_an_api_key_provider_verifies_against_a_real_read_back(self, inventory, settled):
        observed = {
            "name": "meta-ai-openai-endpoint",
            "properties": {"kind": "Custom", "custom": {
                "endpoint": "https://api.meta.ai",
                "authentication": {"kind": "ApiKey", "apiKey": {"headerName": "Authorization"}}}},
        }
        runner = _Runner(reads={"meta-ai-openai-endpoint": observed})
        executor = Executor(settled, inventory, new_journal(settled), runner=runner,
                            execute=True, skip_rehearsal=True)
        # No ARM client: a step satisfied by the read must never need a credential.
        step = executor.run_step(
            next(s for s in steps_for(settled) if "meta-ai" in s.item_id
                 and s.capability_id == "provider.create")
        )
        # Every readable field matched; the credential is simply not readable.
        assert step.status == "verified"
        assert "write-only" in step.detail


class TestCredentialsAreReadLate:
    def test_a_step_already_in_the_desired_state_reads_no_credential(self, inventory, settled):
        # Building resolves credentials, so building before reading would fetch a
        # secret for a step that needs no write -- the commonest case on a re-run.
        observed = {
            "name": "meta-ai-openai-endpoint",
            "properties": {"kind": "Custom", "custom": {
                "endpoint": "https://api.meta.ai",
                "authentication": {"kind": "ApiKey", "apiKey": {"headerName": "Authorization"}}}},
        }
        executor = Executor(settled, inventory, new_journal(settled),
                            runner=_Runner(reads={"meta-ai-openai-endpoint": observed}),
                            execute=True, skip_rehearsal=True, arm_client=None)
        step = executor.run_step(
            next(s for s in steps_for(settled)
                 if "meta-ai" in s.item_id and s.capability_id == "provider.create")
        )
        assert step.status == "verified"


class TestVerificationIsRealNotNominal:
    """Audit of one defect family: the tool asserting or demanding something it
    cannot substantiate. These are the occurrences a review turned up."""

    def test_lists_compare_contents_not_lengths(self):
        from apim_import.apply import _subset

        # An alias pointing at a different model used to verify cleanly, because
        # list comparison only checked length.
        assert not _subset(
            {"backendModels": [{"resourceId": "/correct"}]},
            {"backendModels": [{"resourceId": "/different"}]},
        )
        assert _subset(
            {"backendModels": [{"resourceId": "/correct"}]},
            {"backendModels": [{"resourceId": "/correct", "weight": 100}]},
        )

    def test_a_wanted_element_may_match_any_observed_one(self):
        from apim_import.apply import _subset

        assert _subset({"endpoints": [{"kind": "mcp"}]},
                       {"endpoints": [{"kind": "openApi"}, {"kind": "mcp"}]})

    def test_two_wanted_elements_need_two_distinct_matches(self):
        from apim_import.apply import _subset

        assert not _subset({"e": [{"k": "a"}, {"k": "a"}]}, {"e": [{"k": "a"}]})

    def test_a_recorded_verification_belongs_to_what_it_verified(self, inventory, settled):
        journal = new_journal(settled)
        step = steps_for(settled)[0]
        journal["steps"].append({
            "itemId": step.item_id, "status": "verified", "detail": "",
            "objectsDigest": "sha256:somethingelse",
        })
        runner = _Runner()
        executor = Executor(settled, inventory, journal, runner=runner, execute=True,
                            skip_rehearsal=True)
        again = executor.run_step(step)
        # The item kept its id but asks for something else now, so the old
        # verification proves nothing about it.
        assert again.status != "verified" or runner.calls

    def test_work_the_tool_cannot_perform_is_reported_not_silently_dropped(self, inventory, settled):
        import apim_import.apply as mod

        builder = mod._BUILDERS.pop("provider.create")
        try:
            codes = {f["code"] for f in preflight(settled, inventory)}
            assert "notExecutable" in codes
            # And it does not become a step that fails later.
            assert not [s for s in steps_for(settled) if s.capability_id == "provider.create"]
        finally:
            mod._BUILDERS["provider.create"] = builder

    def test_a_step_referencing_an_uncreated_provider_blocks(self, inventory, settled):
        import copy

        broken = copy.deepcopy(settled)
        for item in broken["items"]:
            for obj in (item.get("target") or {}).get("objects") or []:
                if obj.get("providerName"):
                    obj["providerName"] = "a-provider-nothing-creates"
        codes = {f["code"] for f in preflight(broken, inventory) if f["blocking"]}
        assert "danglingProvider" in codes

    def test_the_name_collision_check_actually_runs_from_the_cli(self):
        import inspect

        from apim_import import cli

        # It is gated on a runner being supplied; the CLI once called preflight
        # without one, so a documented blocking check silently never happened.
        source = inspect.getsource(cli._apply)
        assert "preflight(plan, inventory, runner=" in source
