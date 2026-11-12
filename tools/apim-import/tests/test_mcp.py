import copy
import json

import pytest

from apim_import.capability import CapabilityMap
from apim_import.collect import Collector, CollectOptions
from apim_import.mcp import _parse, discover_tools, discoverable, gateway_url, upstream_url
from apim_import.plan import build_plan
from apim_import.resolve import ResolveError
from fake_arm import SERVICE, FakeArmClient


def options(**overrides):
    overrides.setdefault("cognitive_api_version", "2025-06-01")
    return CollectOptions(**overrides)


@pytest.fixture(scope="module")
def inventory():
    return Collector(FakeArmClient(), SERVICE, options()).run()


class _SecretClient:
    def request(self, method, url, **_kwargs):
        from apim_import.arm import ArmResponse

        return ArmResponse(200, {"primaryKey": "sub-key-value", "value": "sub-key-value"}, "")


class TestWireFormat:
    def test_an_sse_reply_is_read(self):
        body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
        assert _parse(body, "text/event-stream")["id"] == 1

    def test_a_plain_json_reply_is_read(self):
        assert _parse('{"jsonrpc":"2.0","id":2}', "application/json")["id"] == 2

    def test_an_event_stream_with_no_data_is_an_error_not_an_empty_result(self):
        with pytest.raises(ResolveError, match="no data frame"):
            _parse("event: ping\n\n", "text/event-stream")


class TestRouteSelection:
    def test_the_gateway_url_is_what_callers_use_today(self, inventory):
        server = next(s for s in inventory["assets"]["mcpServers"] if s["pattern"] == "passthrough")
        url = gateway_url(inventory, server)
        assert url.startswith(inventory["service"]["gatewayUrl"])
        assert url.endswith("/mcp")

    def test_the_upstream_url_appends_the_mcp_path(self, inventory):
        server = next(s for s in inventory["assets"]["mcpServers"] if s["pattern"] == "passthrough")
        assert upstream_url(server).endswith("/mcp")

    def test_only_runtime_only_servers_are_candidates(self, inventory):
        ids = {server["id"] for server in discoverable(inventory)}
        # A tool projection already has its list from the control plane.
        assert "mcp:orders-mcp" not in ids
        assert "mcp:support-mcp" in ids


class TestAuthorization:
    def test_nothing_is_called_without_authorization(self, inventory):
        document = copy.deepcopy(inventory)
        calls = []
        results = discover_tools(document, caller=lambda u, h, s: calls.append(u) or {"tools": []})
        assert results and all(r.status == "needsAuthorization" for r in results)
        assert calls == []


class TestDiscovery:
    def test_the_gateway_route_is_preferred(self, inventory):
        document = copy.deepcopy(inventory)
        seen = []

        def caller(url, headers, server):
            seen.append(url)
            return {"tools": [{"name": "alpha", "description": "a"}]}

        [result] = [r for r in discover_tools(document, client=_SecretClient(), allow={"all"},
                                              caller=caller) if r.status == "discovered"]
        assert result.route == "gateway"
        assert result.bypassedPolicy is False
        assert seen[0].startswith(document["service"]["gatewayUrl"])

    def test_the_subscription_key_is_sent_under_the_apim_header(self, inventory):
        document = copy.deepcopy(inventory)
        captured = {}

        def caller(url, headers, server):
            captured.update(headers)
            return {"tools": []}

        discover_tools(document, client=_SecretClient(), allow={"all"}, caller=caller)
        assert captured.get("Ocp-Apim-Subscription-Key") == "sub-key-value"

    def test_falling_back_to_the_upstream_records_that_policies_were_bypassed(self, inventory):
        document = copy.deepcopy(inventory)

        def caller(url, headers, server):
            if url.startswith(document["service"]["gatewayUrl"]):
                raise ResolveError("401")
            return {"tools": [{"name": "alpha", "description": "a"}]}

        [result] = [r for r in discover_tools(document, client=_SecretClient(), allow={"all"},
                                              caller=caller) if r.status == "discovered"]
        assert result.route == "upstream"
        assert result.bypassedPolicy is True
        assert "policies did not run" in result.detail

    def test_the_route_is_recorded_on_the_asset(self, inventory):
        document = copy.deepcopy(inventory)
        discover_tools(document, client=_SecretClient(), allow={"all"},
                       caller=lambda u, h, s: {"tools": [{"name": "alpha"}]})
        server = next(s for s in document["assets"]["mcpServers"] if s["id"] == "mcp:support-mcp")
        assert server["toolDiscovery"]["status"] == "complete"
        assert server["toolDiscovery"]["policiesApplied"] is True
        assert [tool["name"] for tool in server["tools"]] == ["alpha"]

    def test_both_routes_failing_is_reported_with_both_reasons(self, inventory):
        document = copy.deepcopy(inventory)

        def caller(url, headers, server):
            raise ResolveError("401")

        [result] = [r for r in discover_tools(document, client=_SecretClient(), allow={"all"},
                                              caller=caller) if r.status == "failed"]
        assert "gateway" in result.detail and "upstream" in result.detail
        # Not recorded as zero tools.
        server = next(s for s in document["assets"]["mcpServers"] if s["id"] == "mcp:support-mcp")
        assert server["toolDiscovery"]["status"] == "runtimeOnly"

    def test_an_explicit_route_is_honoured(self, inventory):
        document = copy.deepcopy(inventory)
        seen = []
        discover_tools(document, client=_SecretClient(), allow={"all"}, route="upstream",
                       caller=lambda u, h, s: seen.append(u) or {"tools": []})
        assert all(not url.startswith(document["service"]["gatewayUrl"]) for url in seen)


class TestPlanAfterDiscovery:
    def test_discovery_through_the_gateway_settles_the_question(self, inventory):
        document = copy.deepcopy(inventory)
        discover_tools(document, client=_SecretClient(), allow={"all"},
                       caller=lambda u, h, s: {"tools": [{"name": "alpha"}]})
        plan = build_plan(document, CapabilityMap.load())
        assert not [
            i for i in plan["items"]
            if i["source"]["aspect"] == "toolExposure" and i["source"]["assetId"] == "mcp:support-mcp"
        ]

    def test_a_list_obtained_by_bypassing_policy_still_needs_a_decision(self, inventory):
        document = copy.deepcopy(inventory)

        def caller(url, headers, server):
            if url.startswith(document["service"]["gatewayUrl"]):
                raise ResolveError("401")
            return {"tools": [{"name": "alpha"}, {"name": "beta"}]}

        discover_tools(document, client=_SecretClient(), allow={"all"}, caller=caller)
        plan = build_plan(document, CapabilityMap.load())
        item = next(
            i for i in plan["items"]
            if i["source"]["aspect"] == "toolExposure" and i["source"]["assetId"] == "mcp:support-mcp"
        )
        # APIM may be withholding tools the upstream exposes; publishing them all
        # without saying so would widen what callers can reach.
        assert item["status"] == "needs-decision"
        assert item["proposal"] == "accept-as-listed"
        assert "policies did not run" in item["rationale"]
        assert "verify-through-gateway" in {option["value"] for option in item["options"]}

    def test_no_credential_reaches_the_inventory(self, inventory):
        document = copy.deepcopy(inventory)
        discover_tools(document, client=_SecretClient(), allow={"all"},
                       caller=lambda u, h, s: {"tools": []})
        assert "sub-key-value" not in json.dumps(document)
