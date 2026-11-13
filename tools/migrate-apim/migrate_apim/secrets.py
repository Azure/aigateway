"""Secret references and their retrieval recipes.

The inventory never carries a secret value. Wherever APIM holds one, the
inventory carries a *reference*: what the secret is, what consumes it, whether
an automated migration can retrieve it, and the exact control-plane call that
retrieves it at apply time. The collector itself never issues those calls.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from . import ids

# ---------------------------------------------------------------------------
# Literal-secret detection
#
# Used only on values that APIM returns in clear (inline backend credentials and
# policy attributes). Anything matched is replaced by a reference before it can
# reach the output file. Over-matching costs an extra question; under-matching
# leaks a credential, so the patterns err toward redaction.
# ---------------------------------------------------------------------------

_NAMED_VALUE_REF = re.compile(r"^\s*\{\{[^}]+\}\}\s*$")
_EXPRESSION = re.compile(r"^\s*@[({]")

_KEY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openaiApiKey", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("anthropicApiKey", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("googleApiKey", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("awsAccessKeyId", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("githubToken", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("jsonWebToken", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.")),
    ("connectionString", re.compile(r"(?i)\b(?:AccountKey|SharedAccessKey|Password)\s*=\s*[^;\s]{8,}")),
    # Long opaque blobs, but only when they mix cases and digits: plain identifiers,
    # URLs, and resource ids must not trip this.
    ("highEntropyToken", re.compile(r"(?=[A-Za-z0-9+=]*[0-9])(?=[A-Za-z0-9+=]*[A-Z])\b[A-Za-z0-9+]{40,}={0,2}\b")),
)

# Parameter names whose value is a credential by construction.
_SECRET_PARAM_NAMES = {
    "api-key", "apikey", "x-api-key", "authorization", "ocp-apim-subscription-key",
    "subscription-key", "x-goog-api-key", "anthropic-api-key", "password", "secret",
    "client-secret", "clientsecret", "access-token", "x-functions-key",
}

# Values that are structurally incapable of being a credential. Without this
# guard, attributes such as <set-status code="403"> trip the name heuristic.
_NOT_A_SECRET = re.compile(r"^(?:\d+|true|false|null|none|bearer|basic|negotiate)$", re.IGNORECASE)
_MIN_SECRET_LENGTH = 8


def is_named_value_reference(value: str) -> bool:
    return bool(_NAMED_VALUE_REF.match(value or ""))


def is_expression(value: str) -> bool:
    return bool(_EXPRESSION.match(value or ""))


def classify_literal(value: str, *, parameter_name: str | None = None) -> str | None:
    """Return a literal-secret class name, or ``None`` when the value is safe.

    Named-value references and policy expressions are indirections, not values,
    and stay in the inventory verbatim because they are what the migration needs
    to resolve.
    """
    if not value or not isinstance(value, str):
        return None
    if is_named_value_reference(value) or is_expression(value):
        return None
    # A recognizable key shape is more specific than the parameter name, so it wins.
    for name, pattern in _KEY_PATTERNS:
        if pattern.search(value):
            return name
    stripped = value.strip()
    if (
        parameter_name
        and parameter_name.strip().lower() in _SECRET_PARAM_NAMES
        and len(stripped) >= _MIN_SECRET_LENGTH
        and not _NOT_A_SECRET.match(stripped)
    ):
        return "declaredCredentialParameter"
    return None


def redact(value: str) -> str:
    """A non-reversible placeholder that preserves shape but no content."""
    length = len(value or "")
    return f"<redacted:{length}>"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SecretRegistry:
    """Collects deduplicated secret references in first-seen order."""

    def __init__(self, *, service_id: str, api_version: str) -> None:
        self.service_id = service_id.rstrip("/")
        self.api_version = api_version
        self._by_id: dict[str, dict[str, Any]] = {}

    # -- construction -------------------------------------------------------

    def _add(self, ref: dict[str, Any], used_by: str | None) -> str:
        existing = self._by_id.get(ref["id"])
        if existing is None:
            ref.setdefault("usedBy", [])
            self._by_id[ref["id"]] = ref
            existing = ref
        if used_by and used_by not in existing["usedBy"]:
            existing["usedBy"].append(used_by)
        return ref["id"]

    def items(self) -> list[dict[str, Any]]:
        return list(self._by_id.values())

    def _arm_action(self, path: str, value_path: str, permission: str) -> dict[str, Any]:
        url = f"https://management.azure.com{self.service_id}/{path.lstrip('/')}?api-version={self.api_version}"
        return {
            "method": "armAction",
            "request": {"httpMethod": "POST", "url": url, "body": None},
            "command": f'az rest --method post --url "{url}" --query "{value_path}" --output tsv',
            "valuePath": f"$.{value_path}",
            "permissions": [permission],
        }

    def _arm_read(self, path: str, value_path: str, permission: str, *, query: str = "") -> dict[str, Any]:
        suffix = f"&{query}" if query else ""
        url = f"https://management.azure.com{self.service_id}/{path.lstrip('/')}?api-version={self.api_version}{suffix}"
        return {
            "method": "armRead",
            "request": {"httpMethod": "GET", "url": url, "body": None},
            "command": f'az rest --method get --url "{url}" --query "{value_path}" --output tsv',
            "valuePath": f"$.{value_path}",
            "permissions": [permission],
        }

    # -- secret classes -----------------------------------------------------

    def named_value(self, nv: dict[str, Any], *, workspace: str | None = None, used_by: str | None = None) -> str:
        name = nv.get("name") or ""
        props = nv.get("properties") or {}
        key_vault = props.get("keyVault") or {}
        secret_identifier = key_vault.get("secretIdentifier")
        path_prefix = f"workspaces/{workspace}/" if workspace and workspace != "default" else ""
        ref: dict[str, Any] = {
            "id": ids.secret("namedValue", ids.scoped(workspace, name)),
            "class": "apimNamedValue",
            "storage": "keyVault" if secret_identifier else "apimEncrypted",
            "description": f"APIM named value '{props.get('displayName') or name}'",
            "owner": ids.named_value(name, workspace),
            "retrievable": True,
            "resolution": self._arm_action(
                f"{path_prefix}namedValues/{name}/listValue",
                "value",
                "Microsoft.ApiManagement/service/namedValues/listValue/action",
            ),
            "notes": [],
        }
        if secret_identifier:
            ref["keyVault"] = {
                "secretIdentifier": secret_identifier,
                "identityClientId": key_vault.get("identityClientId"),
            }
            ref["alternateResolution"] = {
                "method": "keyVault",
                "request": {"httpMethod": "GET", "url": f"{secret_identifier.rstrip('/')}?api-version=7.4"},
                "command": f'az keyvault secret show --id "{secret_identifier}" --query value --output tsv',
                "valuePath": "$.value",
                "permissions": ["Microsoft.KeyVault/vaults/secrets/getSecret/action"],
            }
            ref["notes"].append(
                "Key Vault is the system of record. Prefer re-pointing the target at the same "
                "secret over copying its value."
            )
        if not props.get("secret"):
            ref["notes"].append(
                "APIM does not mark this named value as secret; its value is readable from the "
                "control plane and may be configuration rather than a credential."
            )
            ref["storage"] = "apimPlaintext"
        return self._add(ref, used_by)

    def backend_inline(
        self,
        *,
        backend_name: str,
        field_path: str,
        literal_class: str,
        workspace: str | None = None,
        used_by: str | None = None,
    ) -> str:
        path_prefix = f"workspaces/{workspace}/" if workspace and workspace != "default" else ""
        json_path = field_path.replace("[", "[").replace("'", "")
        ref = {
            "id": ids.secret("backendInline", f"{ids.scoped(workspace, backend_name)}/{field_path}"),
            "class": "apimBackendInlineCredential",
            "storage": "inlineLiteral",
            "description": (
                f"Literal credential stored directly on backend '{backend_name}' at "
                f"properties.{field_path} (detected as {literal_class})"
            ),
            "owner": ids.backend(backend_name, workspace),
            "retrievable": True,
            "resolution": self._arm_read(
                f"{path_prefix}backends/{backend_name}",
                f"properties.{json_path}",
                "Microsoft.ApiManagement/service/backends/read",
            ),
            "notes": [
                "The value is stored in clear on the APIM backend. Read it at apply time and "
                "write it to the target as a secret; do not persist it.",
                "Consider replacing it with a Key Vault-backed named value before migrating.",
            ],
        }
        return self._add(ref, used_by)

    def policy_inline(
        self,
        *,
        policy_id: str,
        scope_url: str,
        xpath: str,
        literal_class: str,
        used_by: str | None = None,
    ) -> str:
        url = f"https://management.azure.com{scope_url}/policies/policy?api-version={self.api_version}&format=rawxml"
        ref = {
            "id": ids.secret("policyInline", f"{policy_id}/{xpath}"),
            "class": "apimPolicyInlineLiteral",
            "storage": "inlineLiteral",
            "description": f"Literal credential embedded in policy XML at {xpath} (detected as {literal_class})",
            "owner": policy_id,
            "retrievable": True,
            "resolution": {
                "method": "armReadXml",
                "request": {"httpMethod": "GET", "url": url, "body": None},
                "command": f'az rest --method get --url "{url}" --headers "Accept=application/json" --query properties.value --output tsv',
                "valuePath": f"$.properties.value :: xpath({xpath})",
                "permissions": ["Microsoft.ApiManagement/service/apis/policies/read"],
            },
            "notes": [
                "A credential hard-coded in policy XML. It is readable by anyone with policy read "
                "access; treat rotating it as part of the migration.",
            ],
        }
        return self._add(ref, used_by)

    def subscription_key(self, sub_name: str, *, workspace: str | None = None, used_by: str | None = None) -> str:
        path_prefix = f"workspaces/{workspace}/" if workspace and workspace != "default" else ""
        ref = {
            "id": ids.secret("subscriptionKey", ids.scoped(workspace, sub_name)),
            "class": "apimSubscriptionKey",
            "storage": "apimEncrypted",
            "description": f"Inbound subscription key pair for APIM subscription '{sub_name}'",
            "owner": ids.subscription(sub_name, workspace),
            "retrievable": True,
            "resolution": self._arm_action(
                f"{path_prefix}subscriptions/{sub_name}/listSecrets",
                "primaryKey",
                "Microsoft.ApiManagement/service/subscriptions/listSecrets/action",
            ),
            "notes": [
                "Inbound caller credential. AI Gateway API keys are gateway-wide and are issued "
                "fresh; an existing APIM key value cannot be imported, so callers must be re-keyed.",
            ],
        }
        ref["resolution"]["alsoReturns"] = ["$.secondaryKey"]
        return self._add(ref, used_by)

    def certificate(self, cert: dict[str, Any], *, used_by: str | None = None) -> str:
        name = cert.get("name") or ""
        props = cert.get("properties") or {}
        key_vault = props.get("keyVault") or {}
        secret_identifier = key_vault.get("secretIdentifier")
        ref: dict[str, Any] = {
            "id": ids.secret("certificate", name),
            "class": "apimCertificate",
            "storage": "keyVault" if secret_identifier else "apimCertificateStore",
            "description": f"Client certificate '{name}' (thumbprint {props.get('thumbprint')})",
            "owner": ids.certificate(name),
            "retrievable": bool(secret_identifier),
            "notes": [],
        }
        if secret_identifier:
            ref["keyVault"] = {"secretIdentifier": secret_identifier}
            ref["resolution"] = {
                "method": "keyVault",
                "request": {"httpMethod": "GET", "url": f"{secret_identifier.rstrip('/')}?api-version=7.4"},
                "command": f'az keyvault secret download --id "{secret_identifier}" --file cert.pfx --encoding base64',
                "valuePath": "$.value",
                "permissions": ["Microsoft.KeyVault/vaults/secrets/getSecret/action"],
            }
        else:
            ref["resolution"] = None
            ref["notes"].append(
                "APIM does not export a certificate private key. Re-upload the certificate to the "
                "target from its original source, or move it to Key Vault first."
            )
        return self._add(ref, used_by)

    def authorization_server(self, name: str, *, kind: str = "authorizationServer", used_by: str | None = None) -> str:
        path = "authorizationServers" if kind == "authorizationServer" else "openidConnectProviders"
        permission = f"Microsoft.ApiManagement/service/{path}/listSecrets/action"
        ref = {
            "id": ids.secret(kind, name),
            "class": f"apim{kind[0].upper()}{kind[1:]}Secret",
            "storage": "apimEncrypted",
            "description": f"OAuth client secret for {kind} '{name}'",
            "owner": ids.authorization_server(name) if kind == "authorizationServer" else ids.openid_provider(name),
            "retrievable": True,
            "resolution": self._arm_action(f"{path}/{name}/listSecrets", "clientSecret", permission),
            "notes": [],
        }
        return self._add(ref, used_by)

    def credential_connection(self, provider: str, connection: str, *, used_by: str | None = None) -> str:
        ref = {
            "id": ids.secret("credentialConnection", f"{provider}/{connection}"),
            "class": "apimCredentialConnection",
            "storage": "apimManagedToken",
            "description": f"Credential-manager connection '{connection}' on provider '{provider}'",
            "owner": ids.credential_provider(provider),
            "retrievable": False,
            "resolution": None,
            "notes": [
                "APIM credential-manager access tokens are never exported. The equivalent AI "
                "Gateway tool-server OAuth connection must be re-authorized interactively with "
                "'az aigateway mcp authorize'.",
            ],
        }
        return self._add(ref, used_by)

    def managed_identity(
        self,
        *,
        identity_type: str,
        client_id: str | None,
        audience: str | None,
        used_by: str | None = None,
    ) -> str:
        # Identify the grant by who acts and on what: a system-assigned identity has
        # no client id, so the audience is what distinguishes one grant from another.
        label = client_id or (urlsplit(audience or "").hostname or audience) or "default"
        ref = {
            "id": ids.secret("managedIdentity", f"{identity_type}/{label}"),
            "class": "azureManagedIdentity",
            "storage": "none",
            "description": (
                f"{identity_type} managed identity"
                + (f" (clientId {client_id})" if client_id else "")
                + (f" for audience {audience}" if audience else "")
            ),
            "owner": None,
            "retrievable": True,
            "resolution": {
                "method": "none",
                "request": None,
                "command": None,
                "valuePath": None,
                "permissions": [],
            },
            "notes": [
                "No secret to move. The migration must instead assign the target gateway's "
                "identity the same data-plane role on the backend resource.",
            ],
        }
        if audience:
            ref["audience"] = audience
        return self._add(ref, used_by)


def named_value_references(value: Any) -> list[str]:
    """Extract ``{{name}}`` references from a string or nested structure."""
    found: list[str] = []
    _walk_named_values(value, found)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


_NV_INLINE = re.compile(r"\{\{([^{}]+)\}\}")


def _walk_named_values(value: Any, found: list[str]) -> None:
    if isinstance(value, str):
        found.extend(match.group(1).strip() for match in _NV_INLINE.finditer(value))
    elif isinstance(value, dict):
        for item in value.values():
            _walk_named_values(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_named_values(item, found)


def sanitize_structure(
    value: Any,
    *,
    path: str,
    on_literal: Any,
    parameter_name: str | None = None,
) -> Any:
    """Deep-copy a structure, replacing detected literal secrets.

    ``on_literal(path, literal_class, raw_value)`` returns the replacement, and is
    where the caller registers a secret reference.
    """
    if isinstance(value, str):
        literal_class = classify_literal(value, parameter_name=parameter_name)
        if literal_class:
            return on_literal(path, literal_class, value)
        return value
    if isinstance(value, dict):
        return {
            key: sanitize_structure(
                item, path=f"{path}.{key}" if path else str(key), on_literal=on_literal, parameter_name=str(key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            sanitize_structure(
                item, path=f"{path}[{index}]", on_literal=on_literal, parameter_name=parameter_name
            )
            for index, item in enumerate(value)
        ]
    return value


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_strings(item)
