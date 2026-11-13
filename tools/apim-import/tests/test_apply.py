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

def _alias_key(obj):
    from apim_import.apply import _alias_name
    return _alias_name(obj)


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

        desired = _DESIRED["identity.assign"](None, {"systemAssigned": True, "userAssigned": None})
        observed = {"principalId": "p", "tenantId": "t", "type": "SystemAssigned"}
        # The planned object and the read are different shapes; comparing them
        # directly never matched, so the step could never be verified.
        assert _subset(desired, observed)

    def test_reusing_a_user_assigned_identity_expects_that_type(self):
        from apim_import.apply import _DESIRED, _subset

        desired = _DESIRED["identity.assign"](None, {"decision": "reuse:/subscriptions/s/uami/one"})
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


class TestFieldsAReadCannotCarry:
    """Verification establishes what a read returns, and says what it skipped.

    `model create` accepts --api-format and `model show` never returns it. Held
    against the read-back, a correctly created model fails to match its own
    plan, and the phase reports a migration that in fact worked as broken.
    """

    def _model_step(self, settled, inventory, reads):
        runner = _Runner(reads=reads)
        executor = Executor(settled, inventory, new_journal(settled), runner=runner,
                            execute=True, skip_rehearsal=True)
        steps = [s for s in executor.run_phase("models") if s.capability_id == "model.create"]
        assert steps, "the fixture should plan at least one model"
        return steps

    def test_a_model_verifies_without_its_api_format_coming_back(self, settled, inventory):
        obj = next(
            o
            for item in settled["items"] if item.get("capabilityId") == "model.create"
            for o in (item.get("target") or {}).get("objects") or []
        )
        # Exactly what a live gateway returns: no apiFormat anywhere in it.
        read_back = {
            "name": obj["name"],
            "properties": {
                "deployment": obj["deploymentConfig"],
                "supportedEndpoints": obj["supportedEndpoints"],
                "providerKind": "Custom",
            },
        }
        steps = self._model_step(settled, inventory, {obj["name"]: read_back})
        step = next(s for s in steps if s.objects and s.objects[0]["name"] == obj["name"])
        assert step.status == "verified", step.detail
        assert "apiFormat is not returned by a read" in step.detail

    def test_a_field_the_read_does_carry_is_still_compared(self, settled, inventory):
        obj = next(
            o
            for item in settled["items"] if item.get("capabilityId") == "model.create"
            for o in (item.get("target") or {}).get("objects") or []
        )
        wrong = {
            "name": obj["name"],
            "properties": {
                "deployment": obj["deploymentConfig"],
                "supportedEndpoints": ["/openai/v1/completely-different"],
                "providerKind": "Custom",
            },
        }
        steps = self._model_step(settled, inventory, {obj["name"]: wrong})
        step = next(s for s in steps if s.objects and s.objects[0]["name"] == obj["name"])
        assert step.status == "failed"


class TestPlannerGapsStopPreflight:
    def test_a_gap_blocks_before_anything_is_written(self, settled, inventory):
        settled["plannerGaps"] = [{"id": "item:model/x/models", "gap": "names no models"}]
        findings = preflight(settled, inventory, runner=_Runner())
        gap = next(f for f in findings if f["code"] == "plannerGap")
        assert gap["blocking"] is True


class TestAliasVerification:
    """An alias read back reports a different shape from the one it was sent."""

    def _alias_objs(self, settled):
        return [
            o
            for item in settled["items"] if item.get("capabilityId") == "alias.create"
            for o in (item.get("target") or {}).get("objects") or []
            if o.get("routingName")
        ]

    def _alias_obj(self, settled):
        return self._alias_objs(settled)[0]

    def _reads(self, settled, resource_id):
        """A read-back for every alias the phase will touch."""
        return {
            _alias_key(o): {
                "name": _alias_key(o),
                "properties": {
                    "aliasName": o["routingName"],
                    "backendModels": [{"resourceId": resource_id}],
                    "supportedEndpoints": o.get("supportedEndpoints") or [],
                    "gatewayEndpoints": [{"api": "v1/messages"}],
                    "selectionOrder": ["priority"],
                },
            }
            for o in self._alias_objs(settled)
        }

    def test_an_alias_verifies_against_the_shape_a_read_returns(self, settled, inventory):
        obj = self._alias_obj(settled)
        # Exactly what a live gateway returns: an id and nothing else.
        model_id = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.ApiManagement/aigateways/gw/workspaces/default/modelProviders/p/models/m"
        runner = _Runner(reads=self._reads(settled, model_id))
        executor = Executor(settled, inventory, new_journal(settled), runner=runner,
                            execute=True, skip_rehearsal=True)
        executor._model_resource_id = lambda *_a, **_k: model_id

        steps = [s for s in executor.run_phase("aliases") if s.capability_id == "alias.create"]
        step = next(s for s in steps if s.objects and s.objects[0].get("routingName") == obj["routingName"])
        assert step.status == "verified", step.detail

    def test_an_alias_pointing_at_another_model_does_not_verify(self, settled, inventory):
        obj = self._alias_obj(settled)
        runner = _Runner(reads=self._reads(settled, "/subscriptions/s/.../models/somebody-else"))
        executor = Executor(settled, inventory, new_journal(settled), runner=runner,
                            execute=True, skip_rehearsal=True)
        executor._model_resource_id = lambda *_a, **_k: "/subscriptions/s/.../models/the-right-one"

        steps = [s for s in executor.run_phase("aliases") if s.capability_id == "alias.create"]
        step = next(s for s in steps if s.objects and s.objects[0].get("routingName") == obj["routingName"])
        assert step.status == "failed"

    def test_an_unresolvable_backend_cannot_verify_silently(self, settled, inventory):
        # A shorter desired list would compare clean against anything.
        from apim_import.apply import _alias_desired

        class _NoModels:
            def _model_resource_id(self, *_a, **_k):
                return None

        desired = _alias_desired(_NoModels(), self._alias_obj(settled))
        assert desired["backendModels"]
        assert "unresolved" in desired["backendModels"][0]["resourceId"]


class TestRehearsalShowsEveryCommand:
    """The rehearsal is the gate a phase is approved from, so it hides nothing."""

    def test_a_multi_object_step_shows_one_command_per_object(self, settled, inventory):
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner())
        multi = [
            s for s in executor.run_phase("aliases")
            if len(s.objects) > 1 and s.capability_id == "alias.create"
        ]
        assert multi, "the fixture should batch several aliases under one item"
        for step in multi:
            assert len(step.commands) == len(step.objects), step.item_id

    def test_the_journal_records_them_all(self, settled, inventory):
        journal = new_journal(settled)
        executor = Executor(settled, inventory, journal, runner=_Runner(), execute=True,
                            skip_rehearsal=True)
        steps = executor.run_phase("models")
        recorded = {s["itemId"]: s for s in journal["steps"]}
        for step in steps:
            if step.item_id in recorded and step.commands:
                assert len(recorded[step.item_id]["commands"]) == len(step.commands)


class TestAFailedCheckIsNotACleanCheck:
    """A check that could not run must not read as one that found nothing."""

    def _collision_runner(self, returncode, stderr):
        class _R:
            calls = []

            def __call__(self, argv, _payload=None):
                if "resource" in argv[:2]:
                    return CommandResult(returncode, "", stderr)
                return CommandResult(1, "")
        return _R()

    def test_a_missing_resource_is_a_clean_check(self, settled, inventory):
        runner = self._collision_runner(1, "ResourceNotFound: ...was not found")
        codes = {f["code"] for f in preflight(settled, inventory, runner=runner)}
        assert "nameCollision" not in codes
        assert "nameCollisionUnknown" not in codes

    def test_a_denied_read_is_reported_as_unestablished(self, settled, inventory):
        runner = self._collision_runner(1, "AuthorizationFailed: does not have permission")
        finding = next(f for f in preflight(settled, inventory, runner=runner)
                       if f["code"] == "nameCollisionUnknown")
        assert "AuthorizationFailed" in finding["message"]

    def test_an_untried_secret_recipe_is_declared(self, settled, inventory):
        codes = {f["code"] for f in preflight(settled, inventory, runner=_Runner())}
        # The fixture's providers authenticate with a key, so something is needed.
        if codes & {"secretNotRetrievable", "secretMissing"}:
            pytest.skip("fixture has no retrievable secrets to report")
        assert "secretRetrievalUntried" in codes

    def test_acknowledgement_does_not_claim_to_gate_writing(self, settled, inventory):
        finding = next(f for f in preflight(settled, inventory, runner=_Runner())
                       if f["code"] == "prerequisites")
        assert "does not gate writing" in finding["remedy"]


class TestVerificationThatChecksNothing:
    def test_an_empty_desired_shape_is_not_comparable(self):
        from apim_import.apply import _comparable

        assert _comparable({"a": 1}) is True
        assert _comparable({}) is False
        assert _comparable({"a": {}, "b": []}) is False
        assert _comparable([None, None]) is False
        assert _comparable({"a": {"b": "x"}}) is True

    def test_a_write_with_nothing_checkable_is_unverified_not_verified(self, settled, inventory):
        # _subset is satisfied by anything here, so "verified" would be a claim
        # about configuration that no read established.
        from apim_import.apply import _DESIRED

        obj = next(
            o
            for item in settled["items"] if item.get("capabilityId") == "model.create"
            for o in (item.get("target") or {}).get("objects") or []
        )
        reads = {obj["name"]: {"name": obj["name"], "properties": {"anything": "at all"}}}
        _DESIRED["model.create"] = lambda _e, o: {}
        try:
            executor = Executor(settled, inventory, new_journal(settled), runner=_Runner(reads=reads),
                                execute=True, skip_rehearsal=True)
            steps = [s for s in executor.run_phase("models") if s.capability_id == "model.create"]
            # The one with a stubbed read-back: present, but nothing comparable.
            assert steps[0].status == "unverified", steps[0].detail
            assert "nothing in it could be compared" in steps[0].detail
            assert not any(s.status == "verified" for s in steps)
        finally:
            from apim_import.apply import _model_desired
            _DESIRED["model.create"] = _model_desired


class TestAPhaseDeclaresWhatItLeavesBehind:
    def test_work_with_no_builder_is_named_by_its_phase(self, settled, inventory):
        executor = Executor(settled, inventory, new_journal(settled), runner=_Runner())
        named = {e["capabilityId"] for phase in PHASES for e in executor.unperformable(phase)}
        planned = {
            i["capabilityId"] for i in settled["items"]
            if i.get("status") in {"ready", "adapted"} and i.get("capabilityId")
            and (i.get("target") or {}).get("objects")
        }
        from apim_import.apply import _BUILDERS
        assert named == {c for c in planned if c not in _BUILDERS}

    def test_a_model_lookup_failure_is_not_reported_as_an_absent_model(self, settled, inventory):
        class _Denied:
            def __call__(self, argv, _payload=None):
                if "model" in argv and "show" in argv:
                    return CommandResult(1, "", "AuthorizationFailed: no access")
                return CommandResult(1, "")

        executor = Executor(settled, inventory, new_journal(settled), runner=_Denied(),
                            execute=True, skip_rehearsal=True)
        steps = [s for s in executor.run_phase("aliases") if s.capability_id == "alias.create"]
        detail = " ".join(s.detail for s in steps)
        assert "AuthorizationFailed" in detail
        assert "run the models phase first" not in detail
