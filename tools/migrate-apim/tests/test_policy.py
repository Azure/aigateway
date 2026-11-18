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


# --------------------------------------------------------------- resolution


def document(policy_id, scope, xml):
    return policy.parse(xml, policy_id=policy_id, scope=scope, scope_url=SCOPE_URL)


def api_policy(name, xml, *, workspace="default"):
    scoped = name if workspace == "default" else f"{workspace}/{name}"
    return document(
        f"policy:api/{scoped}",
        {"level": "api", "name": name, "workspace": workspace},
        xml,
    )


def fragment(name, xml, *, workspace="default"):
    scoped = name if workspace == "default" else f"{workspace}/{name}"
    return document(
        f"policy:fragment/{scoped}",
        {"level": "fragment", "name": name, "workspace": workspace},
        f"<fragment>{xml}</fragment>",
    )


def inbound(*statements):
    """A policy with statements inbound, and APIM's default `<base />` elsewhere.

    The other three sections matter: an empty `<backend />` is an override, not
    a silence, so leaving `<base />` out of them would make every document in
    these tests break inheritance in three sections nobody is testing.
    """
    body = "".join(statements)
    return (f"<policies><inbound>{body}</inbound>"
            "<backend><base /></backend><outbound><base /></outbound>"
            "<on-error><base /></on-error></policies>")


def names(resolution):
    return [occurrence.name for occurrence in resolution.occurrences]


class TestAFragmentReachesTheScopesThatIncludeIt:
    """A fragment is not a scope anything runs at: it is content spliced into
    one. Resolved as a scope of its own it covered no API at all."""

    def test_its_elements_run_at_the_including_api(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<base />", "<include-fragment fragment-id='limits' />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_it_runs_in_the_section_it_was_included_into(self):
        # A fragment has no section of its own -- its elements parse under
        # `fragment` -- so the only section that means anything is the one at
        # the site that pulled it in.
        graph = policy.PolicyGraph([
            api_policy("aoai", "<policies><inbound /><backend />"
                               "<outbound><include-fragment fragment-id='limits' /></outbound>"
                               "<on-error /></policies>"),
            fragment("limits", "<set-header name='x' exists-action='override' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "set-header"]
        assert occurrence.section == "outbound"

    def test_a_fragment_included_through_a_fragment_still_arrives(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='outer' />")),
            fragment("outer", "<include-fragment fragment-id='inner' />"),
            fragment("inner", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "llm-token-limit"]
        assert occurrence.via == ("policy:fragment/outer", "policy:fragment/inner")

    def test_a_cycle_of_includes_terminates(self):
        """APIM stores a fragment that includes one including it back, and
        cannot execute it. Resolving it must still answer."""
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='a' />")),
            fragment("a", "<llm-token-limit tokens-per-minute='1' />"
                          "<include-fragment fragment-id='b' />"),
            fragment("b", "<include-fragment fragment-id='a' />"),
        ])
        assert names(graph.governing(api="aoai")).count("llm-token-limit") == 1

    def test_a_conditional_include_makes_its_contents_conditional(self):
        # Nothing in the fragment's own body says so: the branch is at the site.
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound(
                "<choose><when condition='@(true)'>"
                "<include-fragment fragment-id='routing' />"
                "</when></choose>")),
            fragment("routing", "<set-backend-service backend-id='east' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "set-backend-service"]
        assert occurrence.under_conditional is True

    def test_an_unconditional_include_does_not(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='routing' />")),
            fragment("routing", "<set-backend-service backend-id='east' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "set-backend-service"]
        assert occurrence.under_conditional is False

    def test_a_fragment_id_is_matched_without_regard_to_case(self):
        # APIM resource names do not distinguish case and a `fragment-id` is
        # typed by hand. Matching exactly reports a fragment that resolves
        # perfectly well as one naming nothing.
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='KillSwitch' />")),
            fragment("killswitch", "<set-variable name='k' value='1' />"),
        ])
        assert "set-variable" in names(graph.governing(api="aoai"))
        assert graph.unresolved() == []

    def test_a_fragment_id_naming_nothing_is_reported_rather_than_skipped(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='gone' />")),
        ])
        assert graph.unresolved() == ["gone"]
        assert graph.governing(api="aoai").unresolved_fragments == ("gone",)

    def test_same_named_fragments_in_two_workspaces_are_two_fragments(self):
        graph = policy.PolicyGraph([
            api_policy("one", inbound("<include-fragment fragment-id='shared' />"),
                       workspace="finance"),
            api_policy("two", inbound("<include-fragment fragment-id='shared' />"),
                       workspace="hr"),
            fragment("shared", "<llm-token-limit tokens-per-minute='100' />",
                     workspace="finance"),
            fragment("shared", "<llm-token-limit tokens-per-minute='999' />", workspace="hr"),
        ])
        for workspace, ceiling in (("finance", "100"), ("hr", "999")):
            api = "one" if workspace == "finance" else "two"
            [occurrence] = [o for o in graph.governing(api=api, workspace=workspace).occurrences
                            if o.name == "llm-token-limit"]
            assert occurrence.element["attributes"]["tokens-per-minute"] == ceiling


class TestIncludersReadTheSameIndexBackwards:
    """A fragment's includers and an API's governing elements come off one
    index, so they cannot disagree about what includes what."""

    def test_every_scope_that_includes_it_is_named(self):
        graph = policy.PolicyGraph([
            api_policy("one", inbound("<include-fragment fragment-id='limits' />")),
            api_policy("two", inbound("<include-fragment fragment-id='limits' />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        sites = graph.includers("policy:fragment/limits")
        assert {site.policy_id for site in sites} == {"policy:api/one", "policy:api/two"}

    def test_a_fragment_nothing_includes_has_none(self):
        graph = policy.PolicyGraph([fragment("orphan", "<set-variable name='x' value='1' />")])
        assert graph.includers("policy:fragment/orphan") == []

    def test_an_include_through_a_fragment_resolves_to_the_scope_that_runs(self):
        # A fragment is never a scope itself, so the chain has to be followed
        # to whatever does run.
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='outer' />")),
            fragment("outer", "<include-fragment fragment-id='inner' />"),
            fragment("inner", "<llm-token-limit tokens-per-minute='1' />"),
        ])
        [site] = graph.includers("policy:fragment/inner")
        assert site.policy_id == "policy:api/aoai"
        assert site.via == ("policy:fragment/outer", "policy:fragment/inner")


class TestInheritanceIsWhatTheChildAsksFor:
    """APIM runs a parent's section only where the child carries `<base />`."""

    def _global(self, xml):
        return document("policy:global", {"level": "global", "name": None,
                                          "workspace": "default"}, xml)

    def test_a_section_with_base_inherits(self):
        graph = policy.PolicyGraph([
            self._global(inbound("<llm-token-limit tokens-per-minute='7000' />")),
            api_policy("aoai", inbound("<base />")),
        ])
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_a_section_that_omits_base_does_not(self):
        graph = policy.PolicyGraph([
            self._global(inbound("<llm-token-limit tokens-per-minute='7000' />")),
            api_policy("aoai", inbound("<ip-filter action='allow' />")),
        ])
        resolution = graph.governing(api="aoai")
        assert "llm-token-limit" not in names(resolution)
        assert "ip-filter" in names(resolution)

    def test_the_omission_is_reported_rather_than_merely_acted_on(self):
        graph = policy.PolicyGraph([
            self._global(inbound("<llm-token-limit tokens-per-minute='7000' />")),
            api_policy("aoai", inbound("<ip-filter action='allow' />")),
        ])
        [broken] = graph.governing(api="aoai").inheritance_breaks
        assert broken["policyId"] == "policy:api/aoai"
        assert broken["section"] == "inbound"
        assert broken["parentPolicyId"] == "policy:global"

    def test_an_api_with_no_policy_at_all_inherits(self):
        # APIM's default template is `<base />` in every section, so silence is
        # inheritance -- reading it as an override would drop a global policy
        # from every API that never needed one of its own.
        graph = policy.PolicyGraph([
            self._global(inbound("<llm-token-limit tokens-per-minute='7000' />")),
        ])
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_a_fragment_the_global_policy_includes_reaches_an_inheriting_api(self):
        graph = policy.PolicyGraph([
            self._global(inbound("<include-fragment fragment-id='limits' />")),
            api_policy("aoai", inbound("<base />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_and_not_an_api_that_overrides_its_section(self):
        graph = policy.PolicyGraph([
            self._global(inbound("<include-fragment fragment-id='limits' />")),
            api_policy("aoai", inbound("<ip-filter action='allow' />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        assert "llm-token-limit" not in names(graph.governing(api="aoai"))


class TestScopesOutsideTheApi:
    def test_a_product_policy_governs_the_apis_it_carries(self):
        graph = policy.PolicyGraph(
            [
                document("policy:product/ai", {"level": "product", "name": "ai",
                                               "workspace": "default"},
                         inbound("<llm-token-limit tokens-per-minute='7000' />")),
                api_policy("aoai", inbound("<base />")),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_and_not_an_api_it_does_not(self):
        graph = policy.PolicyGraph(
            [
                document("policy:product/ai", {"level": "product", "name": "ai",
                                               "workspace": "default"},
                         inbound("<llm-token-limit tokens-per-minute='7000' />")),
                api_policy("other", inbound("<base />")),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )
        assert "llm-token-limit" not in names(graph.governing(api="other"))

    def test_an_operation_policy_governs_its_own_operation(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<ip-filter action='allow' />")),
            document("policy:operation/aoai/chat",
                     {"level": "operation", "name": "chat", "apiName": "aoai",
                      "workspace": "default"},
                     inbound("<base />", "<llm-token-limit tokens-per-minute='7000' />")),
        ])
        resolution = graph.governing(api="aoai", operation="chat")
        assert "llm-token-limit" in names(resolution)
        assert "ip-filter" in names(resolution), "the operation asked for `<base />`"

    def test_a_workspace_policy_governs_its_own_apis(self):
        graph = policy.PolicyGraph([
            document("policy:workspace/finance",
                     {"level": "workspace", "name": "finance", "workspace": "finance"},
                     inbound("<llm-token-limit tokens-per-minute='7000' />")),
            api_policy("model-api", inbound("<base />"), workspace="finance"),
        ])
        assert "llm-token-limit" in names(
            graph.governing(api="model-api", workspace="finance")
        )

    def test_levels_can_be_narrowed_to_the_apis_own_policy(self):
        # Detection reads API-scoped evidence only: a global token limit applies
        # to every API and would make all of them look like model APIs.
        graph = policy.PolicyGraph([
            document("policy:global", {"level": "global", "name": None, "workspace": "default"},
                     inbound("<llm-token-limit tokens-per-minute='7000' />")),
            api_policy("aoai", inbound("<base />", "<ip-filter action='allow' />")),
        ])
        resolution = graph.governing(api="aoai", levels=("api",))
        assert "ip-filter" in names(resolution)
        assert "llm-token-limit" not in names(resolution)
