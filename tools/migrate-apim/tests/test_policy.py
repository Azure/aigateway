from migrate_apim import policy, secrets

SCOPE_URL = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim/apis/a"

POLICY_XML = """<policies>
  <inbound>
    <base />
    <include-fragment fragment-id="mcp-killswitch" />
    <rate-limit-by-key calls="60" renewal-period="60" counter-key="@(context.Subscription.Id)" />
    <validate-azure-ad-token tenant-id="{{FLEET-TENANT}}" output-token-variable-name="jwt">
      <audiences>
        <audience>{{FLEET-AUDIENCE}}</audience>
      </audiences>
    </validate-azure-ad-token>
    <set-header name="api-key" exists-action="override">
      <value>sk-abcdefghijklmnopqrstuvwxyz0123</value>
    </set-header>
    <choose>
      <when condition="@(context.Request.Method == &quot;POST&quot;)">
        <set-status code="403" />
      </when>
    </choose>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>"""


def parse(xml=POLICY_XML, registry=None):
    return policy.parse(
        xml,
        policy_id="policy:api/a",
        scope={"level": "api", "name": "a", "resourceId": SCOPE_URL},
        scope_url=SCOPE_URL,
        registry=registry,
    )


class TestParse:
    def test_elements_are_flattened_with_section_and_path(self):
        document = parse()
        paths = {element["path"] for element in document["elements"]}
        assert "inbound/rate-limit-by-key[1]" in paths
        assert "inbound/choose[1]/when[1]/set-status[1]" in paths
        sections = {element["section"] for element in document["elements"]}
        assert sections == {"inbound", "backend", "outbound", "on-error"}

    def test_families_are_assigned(self):
        document = parse()
        by_name = {element["name"]: element["family"] for element in document["elements"]}
        assert by_name["rate-limit-by-key"] == "rateLimit"
        assert by_name["validate-azure-ad-token"] == "authentication"
        assert by_name["include-fragment"] == "composition"

    def test_unknown_elements_become_other_rather_than_disappearing(self):
        document = policy.parse(
            "<policies><inbound><some-future-policy x='1' /></inbound></policies>",
            policy_id="p",
            scope={"level": "api"},
            scope_url=SCOPE_URL,
        )
        [element] = [e for e in document["elements"] if e["name"] == "some-future-policy"]
        assert element["family"] == "other"

    def test_named_value_references_are_collected(self):
        document = parse()
        assert document["namedValueRefs"] == ["FLEET-TENANT", "FLEET-AUDIENCE"]

    def test_fragment_references_are_collected(self):
        document = parse()
        assert document["fragmentRefs"] == ["mcp-killswitch"]

    def test_expressions_get_stable_ids_and_keep_their_source(self):
        document = parse()
        assert len(document["expressions"]) == 2
        expression = next(e for e in document["expressions"] if "Subscription" in (e["source"] or ""))
        assert expression["id"].startswith("expr:")
        assert expression["references"] == ["context.Subscription.Id"]
        # Re-parsing the same document yields the same ids.
        assert {e["id"] for e in parse()["expressions"]} == {e["id"] for e in document["expressions"]}

    def test_status_code_is_not_redacted(self):
        document = parse()
        element = next(e for e in document["elements"] if e["name"] == "set-status")
        assert element["attributes"]["code"] == "403"

    def test_literal_secret_is_replaced_and_registered(self):
        registry = secrets.SecretRegistry(service_id="/s", api_version="2025-09-01-preview")
        document = parse(registry=registry)
        assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in document["xml"]
        assert "<redacted:33>" in document["xml"]
        assert document["secretRefs"]
        [ref] = [item for item in registry.items() if item["class"] == "apimPolicyInlineLiteral"]
        assert ref["retrievable"] is True
        assert ref["resolution"]["method"] == "armReadXml"

    def test_malformed_xml_is_reported_not_raised(self):
        document = policy.parse("<policies><inbound>", policy_id="p", scope={}, scope_url=SCOPE_URL)
        assert document["parseError"]
        assert document["elements"] == []

    def test_empty_policy_is_handled(self):
        document = policy.parse("", policy_id="p", scope={}, scope_url=SCOPE_URL)
        assert document["stats"]["elementCount"] == 0

    def test_fragment_document_without_sections_is_parsed(self):
        document = policy.parse(
            "<fragment><set-variable name='x' value='1' /></fragment>",
            policy_id="policy:fragment/f",
            scope={"level": "fragment"},
            scope_url=SCOPE_URL,
        )
        assert [element["name"] for element in document["elements"]] == ["set-variable"]
        assert document["stats"]["sections"] == ["fragment"]
