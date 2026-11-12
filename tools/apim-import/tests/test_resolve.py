import copy
import json

import pytest

from apim_import.arm import ArmResponse
from apim_import.capability import CapabilityMap
from apim_import.collect import Collector, CollectOptions
from apim_import.plan import build_plan
from apim_import.resolve import (
    ResolveError,
    auth_headers,
    catalogue_url,
    resolvable,
    resolve_models,
    resolve_secret,
)
from fake_arm import SERVICE, FakeArmClient


def options(**overrides):
    overrides.setdefault("cognitive_api_version", "2025-06-01")
    return CollectOptions(**overrides)


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE, options()).run()


class _SecretClient:
    """Serves the recorded retrieval recipe and nothing else."""

    def __init__(self, value="Bearer s3cret-value-not-in-any-file"):
        self.value = value
        self.calls: list[str] = []

    def request(self, method, url, **_kwargs):
        self.calls.append(f"{method} {url}")
        return ArmResponse(200, {"value": self.value}, "")


class TestCatalogueUrl:
    def test_a_bare_host_gets_the_version_prefix(self):
        assert catalogue_url("https://api.meta.ai") == "https://api.meta.ai/v1/models"

    def test_an_endpoint_that_already_has_v1_is_not_doubled(self):
        # APIM's AI import writes .../openai/v1 for an OpenAI-compatible surface;
        # appending /v1/models blindly produces /openai/v1/v1/models.
        assert catalogue_url("https://acct.services.ai.azure.com/openai/v1") == (
            "https://acct.services.ai.azure.com/openai/v1/models"
        )

    def test_an_endpoint_already_pointing_at_models_is_left_alone(self):
        assert catalogue_url("https://x/v1/models") == "https://x/v1/models"

    def test_a_trailing_slash_does_not_change_the_result(self):
        assert catalogue_url("https://api.meta.ai/") == "https://api.meta.ai/v1/models"

    def test_no_endpoint_yields_nothing(self):
        assert catalogue_url(None) is None


class TestAuthHeaders:
    def test_the_header_name_comes_from_the_backend_not_a_guess(self):
        provider = {"auth": {"parameters": {"header": ["Authorization"]}}}
        assert auth_headers(provider, "tok")["Authorization"] == "tok"

    def test_a_provider_using_api_key_is_not_probed_with_authorization(self):
        provider = {"auth": {"parameters": {"header": ["api-key"]}}}
        headers = auth_headers(provider, "tok")
        assert headers["api-key"] == "tok"
        assert "Authorization" not in headers

    def test_anthropic_gets_its_required_version_header(self):
        provider = {"apiDialect": "anthropicMessages", "auth": {"parameters": {"header": ["x-api-key"]}}}
        assert auth_headers(provider, "tok")["anthropic-version"]


class TestSecretResolution:
    def test_the_recorded_recipe_is_replayed_in_process(self):
        client = _SecretClient()
        ref = {
            "id": "secret:namedValue/k",
            "resolution": {
                "method": "armAction",
                "request": {"httpMethod": "POST", "url": "https://management.azure.com/x/listValue"},
                "valuePath": "$.value",
            },
        }
        assert resolve_secret(client, ref) == "Bearer s3cret-value-not-in-any-file"
        # Replayed as a request, not as the recorded shell command, so the value
        # never reaches a command line.
        assert client.calls == ["POST https://management.azure.com/x/listValue"]

    def test_a_recipe_that_cannot_run_in_process_is_refused(self):
        ref = {"id": "secret:certificate/c", "resolution": {"method": "keyVault", "request": {}}}
        with pytest.raises(ResolveError, match="not retrievable in process"):
            resolve_secret(_SecretClient(), ref)

    def test_an_unretrievable_secret_is_refused(self):
        ref = {"id": "secret:x/y", "resolution": None}
        with pytest.raises(ResolveError):
            resolve_secret(_SecretClient(), ref)


class TestAuthorization:
    """Reading a catalogue uses a credential, so it is never done unasked."""

    def test_nothing_is_read_without_authorization(self, inventory):
        document = copy.deepcopy(inventory)
        calls = []
        results = resolve_models(document, client=_SecretClient(),
                                 fetcher=lambda url, headers: calls.append(url) or [])
        assert results
        assert all(result.status == "needsAuthorization" for result in results)
        assert calls == []

    def test_authorizing_one_provider_does_not_authorize_another(self, inventory):
        document = copy.deepcopy(inventory)
        target = resolvable(document)[0]["id"]
        results = resolve_models(document, client=_SecretClient(), allow={target},
                                 fetcher=lambda url, headers: ["m1"])
        by_id = {result.provider_id: result.status for result in results}
        assert by_id[target] == "resolved"
        assert all(status == "needsAuthorization" for pid, status in by_id.items() if pid != target)


class TestResolution:
    def test_the_catalogue_is_written_back_onto_the_provider(self, inventory):
        document = copy.deepcopy(inventory)
        provider_id = resolvable(document)[0]["id"]
        resolve_models(document, client=_SecretClient(), allow={"all"},
                       fetcher=lambda url, headers: ["model-a", "model-b"])
        provider = next(p for p in document["assets"]["modelProviders"] if p["id"] == provider_id)
        assert provider["models"]["status"] == "resolved"
        assert [m["modelName"] for m in provider["models"]["resolved"]] == ["model-a", "model-b"]
        assert provider["models"]["resolvedFrom"]

    def test_the_apis_using_that_provider_are_updated_too(self, inventory):
        document = copy.deepcopy(inventory)
        resolve_models(document, client=_SecretClient(), allow={"all"},
                       fetcher=lambda url, headers: ["model-a"])
        asset = next(m for m in document["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert asset["models"]["status"] == "resolved"
        assert asset["models"]["discoverySource"] == "modelsEndpoint"

    def test_the_credential_never_reaches_the_inventory(self, inventory):
        document = copy.deepcopy(inventory)
        secret = "Bearer s3cret-value-not-in-any-file"
        resolve_models(document, client=_SecretClient(secret), allow={"all"},
                       fetcher=lambda url, headers: ["model-a"])
        assert secret not in json.dumps(document)

    def test_a_fetch_failure_is_reported_not_raised(self, inventory):
        document = copy.deepcopy(inventory)

        def boom(url, headers):
            raise ResolveError("403")

        [result] = [r for r in resolve_models(document, client=_SecretClient(), allow={"all"},
                                              fetcher=boom)
                    if r.status != "needsAuthorization"]
        assert result.status == "failed"
        assert "403" in result.detail
        # The inventory is left as it was rather than half-written.
        asset = next(m for m in document["assets"]["models"] if m["source"]["name"] == "meta-ai")
        assert asset["models"]["status"] == "unresolved"

    def test_an_empty_catalogue_is_empty_not_resolved(self, inventory):
        document = copy.deepcopy(inventory)
        resolve_models(document, client=_SecretClient(), allow={"all"}, fetcher=lambda u, h: [])
        provider = next(p for p in document["assets"]["modelProviders"]
                        if p["origin"].get("backendName") == "meta-ai-openai-endpoint")
        assert provider["models"]["status"] == "empty"


class TestPlanAfterResolving:
    """Resolving must close a question, not open ten new ones."""

    def test_the_catalogue_question_disappears(self, inventory):
        caps = CapabilityMap.load()
        before = build_plan(copy.deepcopy(inventory), caps)
        assert [i for i in before["items"] if i["source"]["aspect"] == "modelCatalogue"]

        resolved = copy.deepcopy(inventory)
        resolve_models(resolved, client=_SecretClient(), allow={"all"},
                       fetcher=lambda u, h: [f"m{n}" for n in range(10)])
        after = build_plan(resolved, caps)
        assert not [i for i in after["items"] if i["source"]["aspect"] == "modelCatalogue"]

    def test_ten_models_cost_one_naming_decision_not_ten(self, inventory):
        caps = CapabilityMap.load()
        resolved = copy.deepcopy(inventory)
        resolve_models(resolved, client=_SecretClient(), allow={"all"},
                       fetcher=lambda u, h: [f"m{n}" for n in range(10)])
        plan = build_plan(resolved, caps)
        naming = [
            i for i in plan["items"]
            if i["kind"] == "name" and i["source"]["assetId"] == "model:meta-ai"
        ]
        assert len(naming) == 1
        assert naming[0]["evidence"]["count"] == 10
        assert naming[0]["proposal"] == "use-model-names"

    def test_resolving_does_not_increase_the_decision_count(self, inventory):
        caps = CapabilityMap.load()
        before = build_plan(copy.deepcopy(inventory), caps)["summary"]["unsettled"]
        resolved = copy.deepcopy(inventory)
        resolve_models(resolved, client=_SecretClient(), allow={"all"},
                       fetcher=lambda u, h: [f"m{n}" for n in range(10)])
        after = build_plan(resolved, caps)["summary"]["unsettled"]
        assert after <= before
