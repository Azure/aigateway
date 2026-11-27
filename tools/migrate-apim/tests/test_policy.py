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

    def test_the_omission_is_reported_against_the_nearest_scope_that_speaks(self):
        # A scope with no policy of its own is transparent, so an API dropping
        # `<base />` under a silent product still overrides the global policy.
        graph = policy.PolicyGraph(
            [
                self._global(inbound("<llm-token-limit tokens-per-minute='7000' />")),
                api_policy("aoai", inbound("<ip-filter action='allow' />")),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )
        [broken] = graph.governing(api="aoai").inheritance_breaks
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


class TestARouteIsMoreThanTheFragmentAtTheEndOfIt:
    """Two includes of one fragment are two arrivals, and the weaker of them
    must not be the one that survives."""

    def test_a_plain_include_and_a_conditional_one_both_reach_rule_selection(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound(
                "<include-fragment fragment-id='routing' />",
                "<choose><when condition='@(true)'>"
                "<include-fragment fragment-id='routing' />"
                "</when></choose>")),
            fragment("routing", "<set-backend-service backend-id='east' />"),
        ])
        arrivals = [o for o in graph.governing(api="aoai").occurrences
                    if o.name == "set-backend-service"]
        assert {o.under_conditional for o in arrivals} == {True, False}

    def test_the_same_fragment_in_two_sections_arrives_in_both(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", "<policies>"
                               "<inbound><include-fragment fragment-id='shared' /></inbound>"
                               "<backend><base /></backend>"
                               "<outbound><include-fragment fragment-id='shared' /></outbound>"
                               "<on-error><base /></on-error></policies>"),
            fragment("shared", "<set-header name='x' exists-action='override' />"),
        ])
        arrivals = [o for o in graph.governing(api="aoai").occurrences if o.name == "set-header"]
        assert {o.section for o in arrivals} == {"inbound", "outbound"}

    def test_a_branch_anywhere_on_the_chain_makes_the_arrival_conditional(self):
        """Reading only the outermost include site reported a fragment pulled
        in under a `choose` two hops down as plainly dissolved."""
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='outer' />")),
            fragment("outer", "<choose><when condition='@(true)'>"
                              "<include-fragment fragment-id='inner' />"
                              "</when></choose>"),
            fragment("inner", "<set-backend-service backend-id='east' />"),
        ])
        [forward] = [o for o in graph.governing(api="aoai").occurrences
                     if o.name == "set-backend-service"]
        assert forward.under_conditional is True


class TestAProductIsAnAlternativeAndNotALink:
    """Which product's policy runs depends on the subscription a call arrived
    on. Chained, the order they were collected in decided the answer."""

    def _two_products(self, second_inherits):
        return policy.PolicyGraph(
            [
                document("policy:global", {"level": "global", "name": None,
                                           "workspace": "default"},
                         inbound("<llm-token-limit tokens-per-minute='7000' />")),
                document("policy:product/a", {"level": "product", "name": "a",
                                              "workspace": "default"},
                         inbound("<base />", "<ip-filter action='allow' />")),
                document("policy:product/b", {"level": "product", "name": "b",
                                              "workspace": "default"},
                         inbound(*(["<base />"] if second_inherits else []),
                                 "<rate-limit calls='10' renewal-period='60' />")),
                api_policy("aoai", inbound("<base />")),
            ],
            products=[{"policyId": "policy:product/a", "apiIds": ["api:aoai"]},
                      {"policyId": "policy:product/b", "apiIds": ["api:aoai"]}],
        )

    def test_both_products_policies_reach_the_api(self):
        resolved = names(self._two_products(second_inherits=True).governing(api="aoai"))
        assert "ip-filter" in resolved and "rate-limit" in resolved

    def test_one_product_omitting_base_does_not_suppress_the_other(self):
        # Chained, `b` without `<base />` cut off `a` and the global policy
        # with it, so reordering the products changed what reached the plan.
        resolved = names(self._two_products(second_inherits=False).governing(api="aoai"))
        assert "ip-filter" in resolved, "product a still carries its own filter"
        assert "llm-token-limit" in resolved, "and still inherits the global limit"
        assert "rate-limit" in resolved


class TestAnIncludeIsResolvedWhereItIsWritten:
    def test_a_global_include_names_the_service_fragment_not_the_readers(self):
        """Resolved against the consuming API's workspace, a finance API got
        the finance fragment out of the service's own global policy."""
        graph = policy.PolicyGraph([
            document("policy:global", {"level": "global", "name": None, "workspace": "default"},
                     inbound("<include-fragment fragment-id='shared' />")),
            api_policy("model-api", inbound("<base />"), workspace="finance"),
            fragment("shared", "<llm-token-limit tokens-per-minute='100' />"),
            fragment("shared", "<llm-token-limit tokens-per-minute='999' />", workspace="finance"),
        ])
        [occurrence] = [o for o in graph.governing(api="model-api", workspace="finance").occurrences
                        if o.name == "llm-token-limit"]
        assert occurrence.policy_id == "policy:fragment/shared"
        assert occurrence.element["attributes"]["tokens-per-minute"] == "100"

    def test_a_workspace_include_still_names_the_workspace_fragment(self):
        graph = policy.PolicyGraph([
            api_policy("model-api", inbound("<include-fragment fragment-id='shared' />"),
                       workspace="finance"),
            fragment("shared", "<llm-token-limit tokens-per-minute='100' />"),
            fragment("shared", "<llm-token-limit tokens-per-minute='999' />", workspace="finance"),
        ])
        [occurrence] = [o for o in graph.governing(api="model-api", workspace="finance").occurrences
                        if o.name == "llm-token-limit"]
        assert occurrence.policy_id == "policy:fragment/finance/shared"


class TestAnUnreadableFragmentIsNotAnEmptyOne:
    def _graph(self):
        unreadable = fragment("broken", "")
        unreadable["parseError"] = "the body could not be read"
        return policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='broken' />")),
            unreadable,
        ])

    def test_its_include_contributes_nothing_and_says_so(self):
        resolution = self._graph().governing(api="aoai")
        assert resolution.unreadable_fragments == ("policy:fragment/broken",)

    def test_it_is_reported_by_document_and_not_by_name(self):
        """A name is not an identity. Reported by name, an `hr` API naming
        `limits` when only `finance/limits` exists looked like a reference to
        the finance fragment, and the unknown policy went unmentioned."""
        resolution = self._graph().governing(api="aoai")
        assert resolution.unresolved_fragments == (), "it resolved -- it just could not be read"

    def test_a_name_nothing_answers_to_is_unresolved_rather_than_unreadable(self):
        graph = policy.PolicyGraph([
            api_policy("one", inbound("<include-fragment fragment-id='limits' />"),
                       workspace="hr"),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />",
                     workspace="finance"),
        ])
        resolution = graph.governing(api="one", workspace="hr")
        assert resolution.unresolved_fragments == ("limits",)
        assert resolution.unreadable_fragments == ()


class TestOperationsAreScopesOfTheirOwn:
    def test_the_api_names_the_operations_that_carry_a_policy(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<base />")),
            document("policy:operation/aoai/chat",
                     {"level": "operation", "name": "chat", "apiName": "aoai",
                      "workspace": "default"},
                     inbound("<llm-token-limit tokens-per-minute='500' />")),
        ])
        assert graph.operations_of(api="aoai") == ["chat"]

    def test_an_operation_of_another_api_is_not_one_of_these(self):
        graph = policy.PolicyGraph([
            document("policy:operation/other/chat",
                     {"level": "operation", "name": "chat", "apiName": "other",
                      "workspace": "default"},
                     inbound("<llm-token-limit tokens-per-minute='500' />")),
        ])
        assert graph.operations_of(api="aoai") == []

    def test_an_operation_in_a_workspace_belongs_to_that_workspaces_api(self):
        graph = policy.PolicyGraph([
            document("policy:operation/finance/model-api/chat",
                     {"level": "operation", "name": "chat", "apiName": "model-api",
                      "workspace": "finance"},
                     inbound("<llm-token-limit tokens-per-minute='500' />")),
        ])
        assert graph.operations_of(api="model-api", workspace="finance") == ["chat"]
        assert graph.operations_of(api="model-api") == []


class TestEveryWayInIsItsOwnArrival:
    """One fragment reached twice is two executions; the same fragment reached
    down two product chains is one seen twice. The route tells them apart."""

    def test_a_fragment_included_twice_in_one_document_runs_twice(self):
        # `_backend_auth` reads the last managed identity in the list, so
        # collapsing the second arrival changed which credential an API was
        # recorded as using.
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound(
                "<include-fragment fragment-id='creds' />",
                "<authentication-managed-identity resource='https://b' />",
                "<include-fragment fragment-id='creds' />")),
            fragment("creds", "<authentication-managed-identity resource='https://c' />"),
        ])
        resources = [o.element["attributes"].get("resource")
                     for o in graph.governing(api="aoai").occurrences
                     if o.name == "authentication-managed-identity"]
        assert resources == ["https://c", "https://b", "https://c"]

    def test_the_same_include_reached_by_two_products_is_one_arrival(self):
        graph = policy.PolicyGraph(
            [
                document("policy:global", {"level": "global", "name": None,
                                           "workspace": "default"},
                         inbound("<include-fragment fragment-id='limits' />")),
                document("policy:product/a", {"level": "product", "name": "a",
                                              "workspace": "default"}, inbound("<base />")),
                document("policy:product/b", {"level": "product", "name": "b",
                                              "workspace": "default"}, inbound("<base />")),
                api_policy("aoai", inbound("<base />")),
                fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
            ],
            products=[{"policyId": "policy:product/a", "apiIds": ["api:aoai"]},
                      {"policyId": "policy:product/b", "apiIds": ["api:aoai"]}],
        )
        assert names(graph.governing(api="aoai")).count("llm-token-limit") == 1

    def test_two_routes_into_one_intermediate_fragment_both_survive(self):
        """`outer` includes `inner` plainly and again under a `choose`."""
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='outer' />")),
            fragment("outer", "<include-fragment fragment-id='inner' />"
                              "<choose><when condition='@(true)'>"
                              "<include-fragment fragment-id='inner' />"
                              "</when></choose>"),
            fragment("inner", "<set-backend-service backend-id='east' />"),
        ])
        arrivals = [o for o in graph.governing(api="aoai").occurrences
                    if o.name == "set-backend-service"]
        assert {o.under_conditional for o in arrivals} == {True, False}


class TestAnElementKnowsWhichScopePulledItIn:
    def test_a_fragment_the_api_includes_is_governed_at_the_api(self):
        graph = policy.PolicyGraph([
            api_policy("aoai", inbound("<include-fragment fragment-id='limits' />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "llm-token-limit"]
        assert occurrence.policy_id == "policy:fragment/limits", "written in the fragment"
        assert occurrence.site_level == "api", "but the API is what asked for it"
        assert occurrence.site_policy_id == "policy:api/aoai"

    def test_a_fragment_the_global_policy_includes_is_governed_globally(self):
        graph = policy.PolicyGraph([
            document("policy:global", {"level": "global", "name": None, "workspace": "default"},
                     inbound("<include-fragment fragment-id='limits' />")),
            api_policy("aoai", inbound("<base />")),
            fragment("limits", "<llm-token-limit tokens-per-minute='7000' />"),
        ])
        [occurrence] = [o for o in graph.governing(api="aoai").occurrences
                        if o.name == "llm-token-limit"]
        assert occurrence.site_level == "global"


class TestAChainWithNoProductIsAlwaysOneOfThem:
    """A subscription scoped to the API, or service-wide, passes through no
    product at all."""

    def test_a_product_that_omits_base_does_not_cut_off_the_global_policy(self):
        graph = policy.PolicyGraph(
            [
                document("policy:global", {"level": "global", "name": None,
                                           "workspace": "default"},
                         inbound("<llm-token-limit tokens-per-minute='7000' />")),
                document("policy:product/a", {"level": "product", "name": "a",
                                              "workspace": "default"},
                         inbound("<ip-filter action='allow' />")),
                api_policy("aoai", inbound("<base />")),
            ],
            products=[{"policyId": "policy:product/a", "apiIds": ["api:aoai"]}],
        )
        assert "llm-token-limit" in names(graph.governing(api="aoai"))

    def test_a_linked_product_with_no_policy_of_its_own_inherits_transparently(self):
        # It is filtered out of the product chains for having no document, and
        # without the plain chain its requests lost the global policy with it.
        graph = policy.PolicyGraph(
            [
                document("policy:global", {"level": "global", "name": None,
                                           "workspace": "default"},
                         inbound("<llm-token-limit tokens-per-minute='7000' />")),
                api_policy("aoai", inbound("<base />")),
            ],
            products=[{"policyId": None, "apiIds": ["api:aoai"]}],
        )
        assert "llm-token-limit" in names(graph.governing(api="aoai"))


class TestEachRequestContextKeepsItsOrder:
    """A union of alternatives is not an execution sequence. Anything reading
    one element as overriding another has to read a chain."""

    def _api_over_product(self):
        return policy.PolicyGraph(
            [
                document("policy:product/ai", {"level": "product", "name": "ai",
                                               "workspace": "default"},
                         inbound("<include-fragment fragment-id='creds' />")),
                api_policy("aoai", inbound(
                    "<base />",
                    "<authentication-managed-identity resource='https://a' />")),
                fragment("creds", "<authentication-managed-identity resource='https://b' />"),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )

    def test_the_api_identity_is_last_in_every_chain(self):
        # Flattened first-seen, the API's identity was emitted once from the
        # no-product chain and then dropped from the product chain as a
        # duplicate, leaving the product's reading as the later of the two.
        for chain in self._api_over_product().governing(api="aoai").chains:
            resources = [o.element["attributes"].get("resource") for o in chain
                         if o.name == "authentication-managed-identity"]
            assert resources[-1] == "https://a", resources

    def test_the_union_still_holds_everything_both_chains_run(self):
        resolved = names(self._api_over_product().governing(api="aoai"))
        assert resolved.count("authentication-managed-identity") >= 2

    def test_one_chain_per_alternative_request_context(self):
        assert len(self._api_over_product().governing(api="aoai").chains) == 2

    def _product_includes_a_fragment(self):
        return policy.PolicyGraph(
            [
                document("policy:product/ai", {"level": "product", "name": "ai",
                                               "workspace": "default"},
                         inbound("<include-fragment fragment-id='creds' />")),
                api_policy("aoai", inbound(
                    "<base />",
                    "<authentication-managed-identity resource='https://a' />")),
                fragment("creds", "<authentication-managed-identity resource='https://b' />"),
            ],
            products=[{"policyId": "policy:product/ai", "apiIds": ["api:aoai"]}],
        )

    def test_the_union_is_not_an_order_and_the_chains_are(self):
        """The union emits the API's identity first, because the chain with no
        product in it is resolved first. That is why nothing may read it as a
        sequence -- and why the chains exist."""
        resolution = self._product_includes_a_fragment().governing(api="aoai")
        union = [o.element["attributes"].get("resource") for o in resolution.occurrences
                 if o.name == "authentication-managed-identity"]
        assert union == ["https://a", "https://b"], "the union looks like b wins"
        for chain in resolution.chains:
            last = [o.element["attributes"].get("resource") for o in chain
                    if o.name == "authentication-managed-identity"][-1]
            assert last == "https://a", "and in every chain it does not"


CREDENTIAL_XML = """<policies>
  <inbound>
    <base />
    <set-header name="api-key" exists-action="override"><value>{{aoai-key}}</value></set-header>
    <set-header name="x-api-key" exists-action="override"><value>sk-abcdefghijklmnopqrstuvwxyz01</value></set-header>
    <set-query-parameter name="api-key" exists-action="override"><value>{{aoai-key}}</value></set-query-parameter>
    <set-header name="x-mcp-caller" exists-action="override"><value>gateway</value></set-header>
    <set-header name="x-trace" exists-action="override"><value>{{MCP-KILLSWITCH}}</value></set-header>
    <set-header name="Authorization" exists-action="override">
      <value>@(context.Request.Headers.GetValueOrDefault("Authorization"))</value>
    </set-header>
  </inbound>
  <backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error>
</policies>"""


class TestTheUpstreamCredentialIsRecognised:
    """APIM has no backend-key object: an upstream key is a `set-header`.

    Unmarked it reads as request rewriting -- which has no target -- so the
    credential reaches no provider and the backend reports as called
    unauthenticated. Both conditions are pinned here because either alone
    misfires, and a false positive publishes a header as a credential.
    """

    def _marked(self, xml=CREDENTIAL_XML):
        return {
            (element["name"], (element["attributes"] or {}).get("name")):
                element.get("credentialParameter")
            for element in parse(xml)["elements"]
            if element["name"] in {"set-header", "set-query-parameter"}
        }

    def test_a_credential_name_holding_a_named_value_is_the_upstream_key(self):
        marked = self._marked()
        assert marked[("set-header", "api-key")] == "api-key"
        assert marked[("set-query-parameter", "api-key")] == "api-key"

    def test_a_redacted_literal_counts_as_the_value(self):
        """The inventory keeps no literal secret, so the placeholder is the
        only evidence left that one was there."""
        assert self._marked()[("set-header", "x-api-key")] == "x-api-key"

    def test_an_ordinary_header_is_not_a_credential(self):
        assert self._marked()[("set-header", "x-mcp-caller")] is None

    def test_a_named_value_in_a_non_credential_header_is_not_one_either(self):
        """`{{MCP-KILLSWITCH}}` is configuration. The name is what says what a
        header is for, so the value alone must not promote it."""
        assert self._marked()[("set-header", "x-trace")] is None

    def test_forwarding_the_callers_own_key_is_not_a_backend_credential(self):
        """An expression reading the inbound request sets no stored secret:
        there is nothing for a provider to be registered with."""
        assert self._marked()[("set-header", "Authorization")] is None
