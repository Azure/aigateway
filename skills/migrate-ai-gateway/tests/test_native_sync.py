"""Published native preview orchestration, using fixed fake CLI responses only."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import MigrationError, State, cli_failure_code, digest, now, semantic
from execution import approve, execute
from gateway import destination_inventory
import migration
from native_sync import collect_preview, refresh_previews, validate_preview
from planning import plan_digest, validate_plan
from selection import compile_selection
from test_migration import TARGET, cli
from test_model_inventory import ACCOUNT, GraphAzure, catalog, graph_fixture


PROVIDER = TARGET + "/workspaces/default/modelProviders/destination-provider"
MODEL = PROVIDER + "/models/deployment-a"


def action(kind, name, deployment=None):
    return {"action": kind, "name": name, "resourceId": PROVIDER + "/models/" + name,
            "deploymentResourceId": ACCOUNT + "/deployments/" + (deployment or name)}


class NativeAzure(GraphAzure):
    def __init__(self):
        super().__init__()
        self.plan = {"dryRun": True, "providerName": "destination-provider", "providerId": PROVIDER,
                     "foundryResourceId": ACCOUNT, "aliases": [],
                     "models": [action("create", "deployment-a"), action("create", "unselected-b")]}
        self.native_error = None

    def __call__(self, argv):
        if argv[:4] == ["az", "aigateway", "model-provider", "sync"]:
            self.calls.append(argv)
            if self.native_error:
                raise self.native_error
            return copy.deepcopy(self.plan)
        return super().__call__(argv)


def fixture():
    bundle, selected, original = graph_fixture()
    azure = NativeAzure()
    azure.collections = original.collections
    azure.gateway = {"id": TARGET, "type": "Microsoft.ApiManagement/aigateways",
                     "location": "eastus2", "properties": {"provisioningState": "Succeeded"}}
    models = catalog("Foundry")
    models["providers"][0]["provenance"] = "operator-manifest"
    bundle["model-catalog.json"] = models
    selected["catalogDigest"] = digest(semantic(models))
    provider = selected["providers"][0]
    provider.update(name="destination-provider", reuseExisting=True)
    auth = provider["settings"]["custom"]["authentication"]
    provider["settings"] = {"kind": "Foundry", "foundry": {
        "endpoint": "https://provider.example", "resourceIds": [ACCOUNT], "authentication": auth}}
    selected["models"][0].update(id="deployment-a", name="deployment-a")
    azure.resources["model-provider"][PROVIDER] = {
        "id": PROVIDER, "name": "destination-provider", "properties": copy.deepcopy(provider["settings"])}
    bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
    azure.calls.clear()
    return bundle, selected, azure


def preview(bundle, azure):
    return collect_preview(bundle["model-catalog.json"], bundle["destination-inventory.json"],
                           "provider-one", "destination-provider", approved=True, runner=azure, inspector=cli)


def attach(bundle, azure):
    proof = preview(bundle, azure)
    if proof["status"] != "ready":
        raise AssertionError(proof)
    bundle["mapping.json"]["nativeSyncPreviews"] = [proof]
    return proof


class NativePreviewTests(unittest.TestCase):
    def test_scoped_read_only_command_and_explicit_authorization(self):
        bundle, _, azure = fixture()
        with self.assertRaises(MigrationError):
            collect_preview(bundle["model-catalog.json"], bundle["destination-inventory.json"],
                            "provider-one", "destination-provider", runner=azure, inspector=cli)
        self.assertEqual(azure.calls, [])
        self.assertEqual(preview(bundle, azure)["status"], "ready")
        command = next(c for c in azure.calls if "sync" in c)
        self.assertEqual(command, [
            "az", "aigateway", "model-provider", "sync", "--subscription", "sub",
            "--resource-group", "target-rg", "--gateway-name", "target",
            "--name", "destination-provider", "--dry-run", "-o", "json"])
        self.assertFalse(any("--yes" in c or "--create-default-aliases" in c for c in azure.calls))

    def test_custom_absent_provider_and_unreviewed_sync_contract_block_before_reads(self):
        for variant in ("custom", "absent", "unrouted", "missing-dry-run"):
            with self.subTest(variant=variant):
                bundle, _, azure = fixture()
                contract = cli()
                if variant == "custom":
                    bundle["model-catalog.json"] = catalog()
                elif variant == "absent":
                    bundle["destination-inventory.json"]["collections"]["model-provider"] = []
                elif variant == "unrouted":
                    contract["resourceCommands"]["aigateways"].remove("model-provider sync")
                else:
                    contract["commands"]["model-provider sync"].remove("--dry-run")
                with self.assertRaises(MigrationError):
                    collect_preview(bundle["model-catalog.json"], bundle["destination-inventory.json"],
                                    "provider-one", "destination-provider", True, runner=azure, cli=contract)
                self.assertEqual(azure.calls, [])

    def test_wrong_live_provider_account_endpoint_or_kind_never_reaches_native_sync(self):
        for field in ("id", "account", "endpoint", "kind", "alternate-account"):
            with self.subTest(field=field):
                bundle, _, azure = fixture()
                live = azure.resources["model-provider"][PROVIDER]
                if field == "id":
                    live["id"] = PROVIDER + "-other"
                elif field == "kind":
                    live["properties"]["kind"] = "Custom"
                else:
                    foundry = live["properties"]["foundry"]
                    foundry[{"account": "resourceIds", "endpoint": "endpoint",
                             "alternate-account": "accountResourceId"}[field]] = (
                        [ACCOUNT + "-other"] if field == "account" else ACCOUNT + "-other"
                        if field == "alternate-account" else "https://wrong.example")
                result = preview(bundle, azure)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["plan"])
                self.assertFalse(any("sync" in c for c in azure.calls))

    def test_native_malformed_or_cross_scope_output_is_not_empty_success(self):
        for variant in ("not-dry-run", "gateway", "account", "duplicate", "unknown-action",
                        "cross-provider", "cross-account", "renamed-create", "aliases", "missing-field"):
            with self.subTest(variant=variant):
                bundle, _, azure = fixture()
                plan = azure.plan
                if variant == "not-dry-run":
                    plan["dryRun"] = False
                elif variant == "gateway":
                    plan["providerId"] = PROVIDER.replace("/aigateways/target", "/aigateways/other")
                elif variant == "account":
                    plan["foundryResourceId"] += "-other"
                elif variant == "duplicate":
                    plan["models"].append(copy.deepcopy(plan["models"][0]))
                elif variant == "unknown-action":
                    plan["models"][0]["action"] = "update"
                elif variant == "cross-provider":
                    plan["models"][0]["resourceId"] = MODEL.replace("destination-provider", "other")
                elif variant == "cross-account":
                    plan["models"][0]["deploymentResourceId"] = ACCOUNT + "-other/deployments/deployment-a"
                elif variant == "renamed-create":
                    plan["models"][0]["deploymentResourceId"] = ACCOUNT + "/deployments/other"
                elif variant == "aliases":
                    plan["aliases"] = [{"action": "create"}]
                else:
                    del plan["models"][0]["deploymentResourceId"]
                result = preview(bundle, azure)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["plan"])

    def test_snapshot_catalog_and_cli_binding_rejects_stale_evidence(self):
        bundle, _, azure = fixture()
        proof = preview(bundle, azure)
        for field in ("catalog", "cli", "destination", "target"):
            with self.subTest(field=field):
                current = copy.deepcopy(bundle)
                contract = cli()
                if field == "catalog":
                    current["model-catalog.json"]["providers"][0]["models"][0]["version"] = "3"
                elif field == "cli":
                    contract["fingerprint"] = digest("different")
                elif field == "destination":
                    current["destination-inventory.json"]["collections"]["gateway"][0]["location"] = "westus"
                else:
                    current["destination-inventory.json"]["destinationId"] = TARGET + "-other"
                with self.assertRaises(MigrationError):
                    validate_preview(proof, current["model-catalog.json"],
                                     current["destination-inventory.json"], contract, check_snapshot=True)

    def test_snapshot_and_native_registration_or_alias_conflicts_block_collection(self):
        for variant in ("deployment", "duplicate-model", "alias", "malformed-alias", "provider-changed"):
            with self.subTest(variant=variant):
                bundle, _, azure = fixture()
                row = action("delete", "retained-stale", "removed-deployment")
                azure.plan["models"].append(row)
                azure.resources["model"][row["resourceId"]] = {
                    "id": row["resourceId"], "name": row["name"],
                    "properties": {"deployment": {"resourceId": row["deploymentResourceId"]}}}
                bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
                snapshot = bundle["destination-inventory.json"]["collections"]
                if variant == "deployment":
                    snapshot["model"][0]["properties"]["deployment"]["resourceId"] = ACCOUNT + "/deployments/other"
                elif variant == "duplicate-model":
                    snapshot["model"].append(copy.deepcopy(snapshot["model"][0]))
                elif variant == "alias":
                    snapshot["model-alias"] = [{"properties": {"backendModels": [{"resourceId": row["resourceId"]}]}}]
                elif variant == "malformed-alias":
                    snapshot["model-alias"] = [{"properties": None}]
                else:
                    azure.resources["model-provider"][PROVIDER]["properties"]["displayName"] = "Changed"
                self.assertEqual(preview(bundle, azure)["status"], "blocked")

    def test_alias_bound_stale_failure_is_a_blocker_not_a_local_substitute_diff(self):
        bundle, selected, azure = fixture()
        azure.native_error = MigrationError("Azure CLI failed (exit 1).", code="SyncAliasBoundStale")
        proof = preview(bundle, azure)
        self.assertEqual(proof["status"], "blocked")
        self.assertIn("alias-bound stale", proof["error"])
        self.assertIsNone(proof["plan"])
        bundle["mapping.json"]["nativeSyncPreviews"] = [proof]
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        self.assertFalse(any("delete" in c or "update" in c for c in azure.calls))
        message = "A stale model is still targeted by an alias."
        self.assertEqual(cli_failure_code("ERROR: " + message), "SyncAliasBoundStale")
        self.assertIsNone(cli_failure_code("ERROR: 403 Forbidden " + message))
        self.assertIsNone(cli_failure_code("ERROR: resource name contains " + message))

    def test_selected_creates_only_and_native_deletes_are_unapproved_proposals(self):
        bundle, selected, azure = fixture()
        stale = action("delete", "retained-stale", "removed-deployment")
        azure.plan["models"].append(stale)
        azure.resources["model"][stale["resourceId"]] = {
            "id": stale["resourceId"], "name": stale["name"],
            "properties": {"deployment": {"resourceId": stale["deploymentResourceId"]}}}
        bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
        attach(bundle, azure)
        compiled = compile_selection(bundle, selected)
        self.assertEqual(validate_plan(compiled)["status"], "valid")
        model_todos = [t for t in compiled["todos.json"]["items"] if t["capabilityId"].startswith("model.")]
        self.assertEqual([t["target"]["name"] for t in model_todos], ["deployment-a"])
        self.assertEqual(compiled["mapping.json"]["removalProposals"], [{
            "resourceId": stale["resourceId"], "action": "propose-separate-removal",
            "source": "native-cli-preview", "blockedByAlias": False, "executionApproved": False}])
        self.assertFalse(any("delete" in t["capabilityId"] for t in compiled["todos.json"]["items"]))
        self.assertIn(stale["resourceId"], azure.resources["model"])
        selected["models"][0]["name"] = "invented-registration"
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)

    def test_new_provider_foundation_can_be_planned_but_models_require_preview(self):
        bundle, selected, azure = fixture()
        with self.assertRaises(MigrationError):
            compile_selection(bundle, selected)
        azure.gateway = None
        azure.resources["model-provider"].clear()
        bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
        selected["models"] = []
        selected["keys"] = []
        selected["providers"][0].pop("reuseExisting")
        result = compile_selection(bundle, selected)
        self.assertEqual(validate_plan(result)["status"], "valid")
        self.assertIn("provider.create", {t["capabilityId"] for t in result["todos.json"]["items"]})
        self.assertFalse(any(t["capabilityId"].startswith("model.") for t in result["todos.json"]["items"]))

    def test_unchanged_native_membership_still_allows_explicit_metadata_update(self):
        bundle, selected, azure = fixture()
        selected["models"][0]["name"] = "registered-name"
        row = action("unchanged", "registered-name", "deployment-a")
        azure.plan["models"][0] = row
        azure.resources["model"][row["resourceId"]] = {
            "id": row["resourceId"], "name": row["name"], "properties": {
                "deployment": {"resourceId": row["deploymentResourceId"], "modelName": "deployment-a",
                               "modelVersion": "1"}, "apiFormat": "OpenAIChatCompletions",
                "supportedEndpoints": ["/openai/v1/chat/completions"], "policies": [{"type": "preserve"}]}}
        bundle["destination-inventory.json"] = destination_inventory(TARGET, azure)
        attach(bundle, azure)
        result = compile_selection(bundle, selected)
        result["plan-validation.json"] = validate_plan(result)
        pdigest = result["plan-validation.json"]["planDigest"]
        self.assertIn("model.update", {t["capabilityId"] for t in result["todos.json"]["items"]})
        for todo in result["todos.json"]["items"]:
            approve(result, todo["id"], pdigest)
            execute(result, todo["id"], pdigest, lambda b: None, azure, cli)
        model = azure.resources["model"][row["resourceId"]]["properties"]
        self.assertEqual(model["deployment"]["modelVersion"], "2")
        self.assertEqual(model["policies"], [{"type": "preserve"}])

    def test_execution_rechecks_native_plan_and_accepts_only_own_recorded_progress(self):
        bundle, selected, azure = fixture()
        attach(bundle, azure)
        result = compile_selection(bundle, selected)
        result["plan-validation.json"] = validate_plan(result)
        pdigest = result["plan-validation.json"]["planDigest"]
        for todo in result["todos.json"]["items"]:
            approve(result, todo["id"], pdigest)
            execute(result, todo["id"], pdigest, lambda b: None, azure, cli)
            if todo["capabilityId"] == "model.create":
                azure.plan["models"][0]["action"] = "unchanged"
                azure.plan["models"].reverse()  # Native order can change when a create becomes an existing model.
        refresh_previews(result, destination_inventory(TARGET, azure), azure, cli())
        self.assertEqual(set(azure.resources["model"]), {MODEL})
        self.assertEqual(plan_digest(result), pdigest)
        self.assertTrue(all("--dry-run" in c for c in azure.calls if "sync" in c))

    def test_external_matching_creation_and_unselected_action_drift_block(self):
        for variant in ("external-create", "new-action", "failure"):
            with self.subTest(variant=variant):
                bundle, selected, azure = fixture()
                attach(bundle, azure)
                result = compile_selection(bundle, selected)
                if variant == "external-create":
                    todo = next(t for t in result["todos.json"]["items"] if t["capabilityId"] == "model.create")
                    azure.resources["model"][MODEL] = {"id": MODEL, "name": "deployment-a",
                                                       **copy.deepcopy(todo["desiredState"])}
                    azure.plan["models"][0]["action"] = "unchanged"
                elif variant == "new-action":
                    azure.plan["models"].append(action("create", "unapproved-c"))
                else:
                    azure.native_error = MigrationError("Native planning unavailable.")
                with self.assertRaises(MigrationError):
                    refresh_previews(result, destination_inventory(TARGET, azure), azure, cli())
                result["plan-validation.json"] = validate_plan(result)
                todo = result["todos.json"]["items"][0]
                pdigest = result["plan-validation.json"]["planDigest"]
                approve(result, todo["id"], pdigest)
                with self.assertRaises(MigrationError):
                    execute(result, todo["id"], pdigest, lambda b: None, azure, cli)
                self.assertEqual(todo["approval"]["status"], "invalidated")
                self.assertFalse(any(c[2:4] in (["model", "create"], ["model", "update"]) for c in azure.calls))

    def test_unknown_outcome_can_reconcile_without_replaying_create(self):
        bundle, selected, azure = fixture()
        attach(bundle, azure)
        result = compile_selection(bundle, selected)
        result["plan-validation.json"] = validate_plan(result)
        pdigest = result["plan-validation.json"]["planDigest"]
        for todo in result["todos.json"]["items"][:2]:
            approve(result, todo["id"], pdigest)
            execute(result, todo["id"], pdigest, lambda b: None, azure, cli)
        todo = next(t for t in result["todos.json"]["items"] if t["capabilityId"] == "model.create")
        todo["status"] = "mutation-unknown"
        todo["attempts"].append({"startedAt": now(), "outcome": "unknown"})
        azure.resources["model"][MODEL] = {"id": MODEL, "name": "deployment-a", **copy.deepcopy(todo["desiredState"])}
        azure.plan["models"][0]["action"] = "unchanged"
        approve(result, todo["id"], pdigest)
        execute(result, todo["id"], pdigest, lambda b: None, azure, cli)
        self.assertEqual(todo["status"], "resource-verified")
        self.assertFalse(any(c[2:4] == ["model", "create"] for c in azure.calls))

    def test_cli_files_are_protected_and_failed_compile_preserves_committed_generation(self):
        bundle, selected, azure = fixture()
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            root = Path(temporary)
            for name in ("model-catalog", "destination-inventory"):
                (root / (name + ".json")).write_text(json.dumps(bundle[name + ".json"]))
            (root / "selection.json").write_text(json.dumps(selected))
            output = root / "preview.json"
            args = ["collect-sync-preview", "--model-catalog-file", str(root / "model-catalog.json"),
                    "--destination-file", str(root / "destination-inventory.json"), "--provider-id", "provider-one",
                    "--provider-name", "destination-provider", "--approved-read", "--output-file", str(output)]
            with patch("migration.collect_preview", side_effect=lambda *a: collect_preview(*a, runner=azure, inspector=cli)):
                self.assertEqual(migration.main(args), 0)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            state = State(root / "state")
            with state.locked(create=True):
                state.save(bundle)
            compile_args = ["compile-plan", "--state-dir", str(state.path),
                            "--selection-file", str(root / "selection.json"), "--sync-preview-file", str(output)]
            self.assertEqual(migration.main(compile_args), 0)
            loaded = state.load()
            self.assertEqual(len(loaded["mapping.json"]["nativeSyncPreviews"]), 1)
            proof = json.loads(output.read_text())
            before = plan_digest(loaded)
            loaded["mapping.json"]["nativeSyncPreviews"][0]["capturedAt"] = now()
            self.assertEqual(plan_digest(loaded), before)
            loaded["mapping.json"]["nativeSyncPreviews"][0]["plan"]["models"].pop()
            self.assertNotEqual(plan_digest(loaded), before)
            proof["cliFingerprint"] = digest("different-cli")
            (root / "stale.json").write_text(json.dumps(proof))
            with self.assertRaises(MigrationError):
                migration.main(compile_args[:-1] + [str(root / "stale.json")])
            self.assertEqual(state.load()["context.json"]["generationId"], loaded["context.json"]["generationId"])
            foundation = copy.deepcopy(selected)
            foundation.update(models=[], keys=[])
            (root / "foundation.json").write_text(json.dumps(foundation))
            self.assertEqual(migration.main(["compile-plan", "--state-dir", str(state.path),
                                            "--selection-file", str(root / "foundation.json")]), 0)
            self.assertEqual(state.load()["mapping.json"]["nativeSyncPreviews"], [])
            azure.native_error = MigrationError("Read inconclusive.")
            args[-1] = str(root / "blocked.json")
            with patch("migration.collect_preview", side_effect=lambda *a: collect_preview(*a, runner=azure, inspector=cli)):
                self.assertEqual(migration.main(args), 1)
            self.assertEqual(json.loads((root / "blocked.json").read_text())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
