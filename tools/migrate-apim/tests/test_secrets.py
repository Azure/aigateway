from migrate_apim import secrets


def registry() -> secrets.SecretRegistry:
    return secrets.SecretRegistry(
        service_id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.ApiManagement/service/apim",
        api_version="2025-09-01-preview",
    )


class TestClassifyLiteral:
    def test_named_value_reference_is_an_indirection_not_a_secret(self):
        assert secrets.classify_literal("{{openai-api-key}}", parameter_name="api-key") is None

    def test_policy_expression_is_an_indirection_not_a_secret(self):
        assert secrets.classify_literal("@(context.Variables[\"key\"])", parameter_name="api-key") is None

    def test_openai_key_shape_is_detected_regardless_of_parameter(self):
        assert secrets.classify_literal("sk-abcdefghijklmnopqrstuvwxyz0123") == "openaiApiKey"

    def test_credential_parameter_name_flags_a_literal_value(self):
        assert (
            secrets.classify_literal("hunter2-hunter2", parameter_name="api-key")
            == "declaredCredentialParameter"
        )

    def test_status_code_is_not_a_credential(self):
        # Regression: <set-status code="403"> tripped the parameter-name heuristic.
        assert secrets.classify_literal("403", parameter_name="code") is None

    def test_short_values_under_a_credential_name_are_ignored(self):
        assert secrets.classify_literal("none", parameter_name="authorization") is None

    def test_auth_scheme_word_is_not_a_credential(self):
        assert secrets.classify_literal("Bearer", parameter_name="authorization") is None

    def test_resource_id_is_not_a_high_entropy_token(self):
        resource_id = (
            "/subscriptions/8fb15cdc-e03d-4014-842e-c241971e853d/resourceGroups/rg"
            "/providers/Microsoft.CognitiveServices/accounts/account"
        )
        assert secrets.classify_literal(resource_id) is None

    def test_aws_access_key_is_detected(self):
        assert secrets.classify_literal("AKIAIOSFODNN7EXAMPLE") == "awsAccessKeyId"


class TestRegistry:
    def test_secret_named_value_gets_a_list_value_recipe(self):
        reg = registry()
        ref_id = reg.named_value(
            {"name": "openai-key", "properties": {"displayName": "openai-key", "secret": True}},
            used_by="backend:x",
        )
        [ref] = reg.items()
        assert ref["id"] == ref_id == "secret:namedValue/openai-key"
        assert ref["retrievable"] is True
        assert ref["storage"] == "apimEncrypted"
        assert ref["resolution"]["method"] == "armAction"
        assert ref["resolution"]["request"]["url"].endswith(
            "/namedValues/openai-key/listValue?api-version=2025-09-01-preview"
        )
        assert ref["usedBy"] == ["backend:x"]

    def test_key_vault_named_value_prefers_the_vault(self):
        reg = registry()
        reg.named_value(
            {
                "name": "kv-key",
                "properties": {
                    "secret": True,
                    "keyVault": {"secretIdentifier": "https://v.vault.azure.net/secrets/k"},
                },
            },
            used_by=None,
        )
        [ref] = reg.items()
        assert ref["storage"] == "keyVault"
        assert ref["alternateResolution"]["method"] == "keyVault"

    def test_non_secret_named_value_is_marked_plaintext(self):
        reg = registry()
        reg.named_value({"name": "tenant", "properties": {"secret": False}}, used_by=None)
        [ref] = reg.items()
        assert ref["storage"] == "apimPlaintext"

    def test_certificate_without_key_vault_is_not_retrievable(self):
        reg = registry()
        reg.certificate({"name": "client-cert", "properties": {"thumbprint": "AA"}})
        [ref] = reg.items()
        assert ref["retrievable"] is False
        assert ref["resolution"] is None

    def test_credential_manager_connection_cannot_be_exported(self):
        reg = registry()
        reg.credential_connection("github", "conn1")
        [ref] = reg.items()
        assert ref["retrievable"] is False
        assert "re-authorized" in " ".join(ref["notes"])

    def test_managed_identity_has_nothing_to_fetch(self):
        reg = registry()
        reg.managed_identity(
            identity_type="systemAssigned", client_id=None, audience="https://cognitiveservices.azure.com/"
        )
        [ref] = reg.items()
        assert ref["storage"] == "none"
        assert ref["resolution"]["method"] == "none"
        assert ref["retrievable"] is True

    def test_duplicate_references_merge_and_accumulate_consumers(self):
        reg = registry()
        payload = {"name": "shared", "properties": {"secret": True}}
        reg.named_value(payload, used_by="backend:a")
        reg.named_value(payload, used_by="backend:b")
        assert len(reg.items()) == 1
        assert reg.items()[0]["usedBy"] == ["backend:a", "backend:b"]


class TestHelpers:
    def test_named_value_references_are_found_in_nested_structures(self):
        payload = {"header": {"api-key": ["{{key-one}}"]}, "query": {"k": ["{{key-two}}", "literal"]}}
        assert secrets.named_value_references(payload) == ["key-one", "key-two"]

    def test_sanitize_structure_replaces_only_the_literal(self):
        seen = []

        def on_literal(path, literal_class, raw):
            seen.append((path, literal_class))
            return "<ref>"

        payload = {"header": {"api-key": ["sk-abcdefghijklmnopqrstuvwxyz0123"], "accept": ["application/json"]}}
        cleaned = secrets.sanitize_structure(payload, path="", on_literal=on_literal)
        assert cleaned["header"]["api-key"] == ["<ref>"]
        assert cleaned["header"]["accept"] == ["application/json"]
        assert seen == [("header.api-key[0]", "openaiApiKey")]

    def test_redact_preserves_length_only(self):
        assert secrets.redact("abcdef") == "<redacted:6>"
