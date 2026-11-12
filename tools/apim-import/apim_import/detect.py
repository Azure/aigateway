"""Classify APIM APIs into the three asset families a migration cares about.

MCP servers and A2A agents are first-class APIM API types, so classifying them
is a lookup. Model APIs are not: APIM publishes an Azure OpenAI, Bedrock, or
Anthropic endpoint as an ordinary ``http`` API. Detection is therefore
evidence-based and reports both a confidence and the signals behind it, so the
agent can confirm the borderline cases with the operator instead of guessing.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Provider recognition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderRule:
    kind: str
    label: str
    host_patterns: tuple[str, ...]
    api_dialect: str
    catalog: str  # how the model list can be discovered
    target_provider_kind: str  # the AI Gateway modelProvider kind this maps to


PROVIDERS: tuple[ProviderRule, ...] = (
    ProviderRule(
        "foundry", "Microsoft Foundry / Azure OpenAI",
        ("*.openai.azure.com", "*.services.ai.azure.com", "*.cognitiveservices.azure.com",
         "*.inference.ai.azure.com", "*.models.ai.azure.com", "*.api.cognitive.microsoft.com"),
        "azureOpenAI", "armDeployments", "Foundry",
    ),
    ProviderRule("openai", "OpenAI", ("api.openai.com",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("anthropic", "Anthropic", ("api.anthropic.com",), "anthropicMessages", "modelsEndpoint", "Custom"),
    ProviderRule(
        "bedrock", "AWS Bedrock",
        ("bedrock-runtime.*.amazonaws.com", "bedrock.*.amazonaws.com", "bedrock-agent-runtime.*.amazonaws.com"),
        "bedrock", "awsCli", "Custom",
    ),
    ProviderRule(
        "vertex", "Google Vertex AI",
        ("*-aiplatform.googleapis.com", "aiplatform.googleapis.com"),
        "vertex", "gcloudCli", "Custom",
    ),
    ProviderRule(
        "googleAi", "Google AI (Gemini)", ("generativelanguage.googleapis.com",),
        "gemini", "modelsEndpoint", "Custom",
    ),
    ProviderRule("mistral", "Mistral", ("api.mistral.ai",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("cohere", "Cohere", ("api.cohere.ai", "api.cohere.com"), "cohere", "modelsEndpoint", "Custom"),
    ProviderRule("groq", "Groq", ("api.groq.com",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("together", "Together AI", ("api.together.xyz", "api.together.ai"), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("deepseek", "DeepSeek", ("api.deepseek.com",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("xai", "xAI", ("api.x.ai",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule("perplexity", "Perplexity", ("api.perplexity.ai",), "openAI", "modelsEndpoint", "Custom"),
    ProviderRule(
        "huggingface", "Hugging Face",
        ("*.endpoints.huggingface.cloud", "api-inference.huggingface.co"),
        "openAI", "manual", "Custom",
    ),
    ProviderRule("databricks", "Databricks", ("*.databricks.com", "*.azuredatabricks.net"), "openAI", "manual", "Custom"),
)

_FOUNDRY_KINDS = {"foundry"}

# A backend with type "languageModel" declares its dialect and model outright, so
# nothing has to be inferred. Only formats observed on a live service are mapped
# exactly; anything else is normalized by substring and marked as inferred, with
# the raw value always preserved.
_VERIFIED_MODEL_FORMATS: dict[str, dict[str, Any]] = {
    "anthropic-messages": {
        "dialect": "anthropicMessages",
        "supportedEndpoints": ["/v1/messages"],
        "targetProviderKind": "Custom",
        "providerKind": "anthropic",
    },
}

_FORMAT_HINTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("anthropic", {"dialect": "anthropicMessages", "supportedEndpoints": ["/v1/messages"],
                   "targetProviderKind": "Custom", "providerKind": "anthropic"}),
    ("azure-openai", {"dialect": "azureOpenAI", "supportedEndpoints": ["/openai/v1/chat/completions"],
                      "targetProviderKind": "Foundry", "providerKind": "foundry"}),
    ("openai", {"dialect": "openAIChatCompletions", "supportedEndpoints": ["/openai/v1/chat/completions"],
                "targetProviderKind": "Custom", "providerKind": "openai"}),
)


def language_model_format(api_format: str | None) -> dict[str, Any]:
    """Resolve a backend's declared apiFormat to a dialect and target endpoints."""
    record: dict[str, Any] = {
        "apiFormat": api_format,
        "dialect": None,
        "supportedEndpoints": None,
        "targetProviderKind": "Custom",
        "providerKind": None,
        "resolution": "unknown",
    }
    if not api_format:
        return record
    key = api_format.strip().lower()
    verified = _VERIFIED_MODEL_FORMATS.get(key)
    if verified:
        return {**record, **verified, "resolution": "verified"}
    for hint, mapping in _FORMAT_HINTS:
        if hint in key:
            return {**record, **mapping, "resolution": "inferred"}
    return record

# Inference-shaped request paths, strongest first.
_INFERENCE_PATHS: tuple[tuple[str, str], ...] = (
    (r"/chat/completions", "openAIChatCompletions"),
    (r"/v1/responses|/responses\b", "openAIResponses"),
    (r"/v1/messages|/messages\b", "anthropicMessages"),
    (r"/embeddings", "openAIEmbeddings"),
    # Not /chat/completions, which the first rule already claimed.
    (r"(?<!chat)/completions\b", "openAICompletions"),
    (r"/images/(generations|edits)", "openAIImages"),
    (r"/audio/(speech|transcriptions|translations)", "openAIAudio"),
    (r"/converse(-stream)?\b", "bedrockConverse"),
    (r"/model/[^/]+/invoke(-with-response-stream)?", "bedrockInvoke"),
    (r":generateContent|:streamGenerateContent", "geminiGenerateContent"),
    (r"/rerank", "rerank"),
    (r"/deployments/\{?[A-Za-z0-9_\-]*deployment", "azureOpenAIDeploymentRoute"),
)

_NAME_HINTS = re.compile(
    r"(?i)\b(openai|azure[-_ ]?openai|foundry|llm|gpt|claude|anthropic|bedrock|gemini|vertex|"
    r"mistral|cohere|embedding|inference|completion|chat|model)\b"
)

# APIM's "Import AI API" wizard names the objects it creates. These conventions are
# the only trace left when a model API fronts an unrecognized provider host behind a
# wildcard operation -- which is exactly the case the host and path signals miss.
_AI_BACKEND_SUFFIX = re.compile(r"(?i)-(?:openai|ai)-endpoint$")
_AI_NAMED_VALUE_SUFFIX = re.compile(r"(?i)-LLM$")

# The suffix does not just say "this is an AI backend" -- it says which protocol
# the wizard imported. Observed consistently across two live instances:
#   *-openai-endpoint -> an OpenAI-protocol upstream  (api.meta.ai, .../openai/v1)
#   *-ai-endpoint     -> an Azure AI Foundry upstream (*.services.ai.azure.com)
# Provider identity (who) and protocol (how) are orthogonal: a Foundry host
# reached at /openai/v1 is a Foundry provider speaking the OpenAI protocol.
_IMPORT_PROTOCOL = (
    (re.compile(r"(?i)-openai-endpoint$"), "openAiCompatible", "openAIChatCompletions"),
    (re.compile(r"(?i)-ai-endpoint$"), "foundry", "azureOpenAI"),
)


def protocol_from_backend_name(name: str | None) -> dict[str, Any] | None:
    """Protocol declared by APIM's AI import naming convention, if any."""
    for pattern, provider_kind, dialect in _IMPORT_PROTOCOL:
        if name and pattern.search(name):
            return {
                "providerKind": provider_kind,
                "apiDialect": dialect,
                "targetProviderKind": "Foundry" if provider_kind == "foundry" else "Custom",
                "basis": "importConvention",
            }
    return None


# ---------------------------------------------------------------------------
# Publishable surface
#
# A live AI Gateway publishes exactly four inference routes (verified against
# a365-aigw-rp-demo at API version 2026-09-01-preview). Every operation a source
# API exposes either maps onto one of these or has no target at all, so this
# table is what decides how much of an API can actually move.
# ---------------------------------------------------------------------------

TARGET_ROUTES: dict[str, str] = {
    "chatCompletions": "/openai/v1/chat/completions",
    "responses": "/openai/v1/responses",
    "embeddings": "/openai/v1/embeddings",
    "messages": "/v1/messages",
}

# Ordered. Container resources are matched before the generic verbs they contain,
# so /openai/threads/{id}/messages is a thread operation and not the Anthropic
# messages route.
_SURFACE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/assistants\b"), "assistants"),
    (re.compile(r"/threads\b"), "threads"),
    (re.compile(r"/vector_stores\b"), "vectorStores"),
    (re.compile(r"/files\b"), "files"),
    (re.compile(r"/batches\b"), "batches"),
    (re.compile(r"/fine_tuning\b"), "fineTuning"),
    (re.compile(r"/moderations\b"), "moderations"),
    (re.compile(r"/audio/"), "audio"),
    (re.compile(r"/images/"), "images"),
    (re.compile(r"/chat/completions\b"), "chatCompletions"),
    (re.compile(r"/v1/messages\b"), "messages"),
    (re.compile(r"/responses\b"), "responses"),
    (re.compile(r"/embeddings\b"), "embeddings"),
    (re.compile(r"/completions\b"), "legacyCompletions"),
    (re.compile(r"/models\b"), "modelCatalogue"),
    (re.compile(r"/realtime\b"), "realtime"),
)

_WILDCARD = re.compile(r"/\*\s*$|^/\*")


def classify_operation(url_template: str) -> dict[str, Any]:
    """Place one operation template against the target's publishable routes."""
    path = (url_template or "").split("?", 1)[0]
    if _WILDCARD.search(path):
        return {"template": url_template, "group": "wildcard", "publishable": None, "route": None}
    for pattern, group in _SURFACE_RULES:
        if pattern.search(path):
            route = TARGET_ROUTES.get(group)
            # The plain route is directly publishable. A sub-resource of a
            # publishable group (GET /responses/{id}) is in scope for the same
            # API but its support is not established, so it is not claimed.
            exact = bool(route) and path.rstrip("/").endswith(_GROUP_TAIL[group])
            return {
                "template": url_template,
                "group": group,
                "publishable": bool(route),
                "route": route if route and exact else None,
                "subresource": bool(route) and not exact,
            }
    return {"template": url_template, "group": "other", "publishable": False, "route": None}


_GROUP_TAIL = {
    "chatCompletions": "chat/completions",
    "responses": "responses",
    "embeddings": "embeddings",
    "messages": "messages",
}


def summarize_surface(url_templates: list[str]) -> dict[str, Any]:
    """Per-asset breakdown of what can and cannot be published on the target."""
    operations = [classify_operation(template) for template in url_templates]
    wildcard = [op for op in operations if op["group"] == "wildcard"]
    groups: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if operation["group"] == "wildcard":
            continue
        entry = groups.setdefault(
            operation["group"],
            {"group": operation["group"], "publishable": operation["publishable"],
             "route": TARGET_ROUTES.get(operation["group"]), "count": 0, "subresources": 0,
             "samples": []},
        )
        entry["count"] += 1
        if operation.get("subresource"):
            entry["subresources"] += 1
        if len(entry["samples"]) < 3:
            entry["samples"].append(operation["template"])

    publishable = sorted(
        (entry for entry in groups.values() if entry["publishable"]), key=lambda e: e["group"]
    )
    unpublishable = sorted(
        (entry for entry in groups.values() if not entry["publishable"]),
        key=lambda e: (-e["count"], e["group"]),
    )
    summary: dict[str, Any] = {
        "status": "bounded",
        "basis": "operationTemplates",
        "operationCount": len(operations),
        "publishable": publishable,
        "unpublishable": unpublishable,
        "publishableCount": sum(entry["count"] for entry in publishable),
        "unpublishableCount": sum(entry["count"] for entry in unpublishable),
        "targetRoutes": sorted(TARGET_ROUTES.values()),
    }
    if wildcard:
        # A wildcard forwards whatever the upstream offers. Reporting zero
        # inference routes here would read as "nothing to migrate" when the truth
        # is that configuration cannot answer the question at all.
        summary["status"] = "unbounded"
        summary["note"] = (
            f"{len(wildcard)} wildcard operation(s) forward every upstream path, so the exposed "
            "surface cannot be read from configuration. The routes callers actually use have to be "
            "established with the operator or from traffic."
        )
    elif not operations:
        summary["status"] = "unknown"
        summary["note"] = (
            "No operations were enumerated for this API, so its published surface is undetermined "
            "rather than empty."
        )
    return summary

_LLM_POLICY_FAMILIES = {"tokenLimit", "tokenMetrics", "semanticCache", "contentSafety"}
_LLM_POLICY_ELEMENTS = {
    "azure-openai-token-limit", "llm-token-limit",
    "azure-openai-emit-token-metric", "llm-emit-token-metric",
    "azure-openai-semantic-cache-lookup", "azure-openai-semantic-cache-store",
    "llm-semantic-cache-lookup", "llm-semantic-cache-store",
    "azure-openai-content-safety", "llm-content-safety",
}


@dataclass
class Signal:
    type: str
    value: str
    weight: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        record = {"type": self.type, "value": self.value, "weight": self.weight}
        if self.detail:
            record["detail"] = self.detail
        return record


@dataclass
class Classification:
    kind: str  # modelApi | mcpServer | agent | excluded
    score: int = 0
    confidence: str = "none"
    signals: list[Signal] = field(default_factory=list)
    provider: ProviderRule | None = None
    reason: str = ""
    pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "confidence": self.confidence,
            "score": self.score,
            "signals": [signal.to_dict() for signal in self.signals],
        }
        if self.provider:
            record["providerGuess"] = self.provider.kind
        if self.reason:
            record["reason"] = self.reason
        return record


def provider_for_url(url: str | None) -> ProviderRule | None:
    host = (urlsplit(url or "").hostname or "").lower()
    if not host:
        return None
    for rule in PROVIDERS:
        for pattern in rule.host_patterns:
            if fnmatch.fnmatch(host, pattern):
                return rule
    return None


def is_foundry(rule: ProviderRule | None) -> bool:
    return bool(rule and rule.kind in _FOUNDRY_KINDS)


def is_ai_named_backend(name: str | None) -> bool:
    """True when a backend name follows APIM's AI API import convention."""
    return bool(name and _AI_BACKEND_SUFFIX.search(name))


# Policies that point at a backend declare what that backend is for. The
# declaration is authoritative and outranks the host heuristic: an Azure AI
# Content Safety endpoint sits on *.cognitiveservices.azure.com and so looks
# exactly like a Foundry model host, but it serves no models and never will.
BACKEND_ROLE_ATTRIBUTES: dict[str, tuple[str, str]] = {
    "llm-content-safety": ("backend-id", "contentSafety"),
    "azure-openai-content-safety": ("backend-id", "contentSafety"),
    "llm-semantic-cache-lookup": ("embeddings-backend-id", "embeddings"),
    "azure-openai-semantic-cache-lookup": ("embeddings-backend-id", "embeddings"),
    "set-backend-service": ("backend-id", "routing"),
}

# Roles whose backend serves no model, so it must not become a model provider.
NON_MODEL_ROLES = frozenset({"contentSafety"})


def backend_roles_from_element(element: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(backendName, role)`` when a policy element names a backend."""
    mapping = BACKEND_ROLE_ATTRIBUTES.get(element.get("name") or "")
    if not mapping:
        return None
    attribute, role = mapping
    value = (element.get("attributes") or {}).get(attribute)
    if not isinstance(value, str) or not value or value.startswith("@") or "{{" in value:
        return None
    return value, role


def api_dialect_for_paths(paths: list[str]) -> list[str]:
    """Map operation URL templates to recognizable inference dialects."""
    found: list[str] = []
    for path in paths:
        for pattern, dialect in _INFERENCE_PATHS:
            if re.search(pattern, path or "", re.IGNORECASE) and dialect not in found:
                found.append(dialect)
    return found


def classify_api(
    api: dict[str, Any],
    *,
    backend: dict[str, Any] | None,
    backend_urls: list[str],
    operation_paths: list[str],
    policy_element_names: set[str],
    policy_families: set[str],
    backend_name: str | None = None,
    credential_named_values: list[str] | None = None,
) -> Classification:
    """Decide what an APIM API is, and how sure we are."""
    props = api.get("properties") or {}
    api_type = (props.get("type") or props.get("apiType") or "http").lower()

    if api_type == "a2a" or props.get("isAgent") or props.get("a2aProperties") or props.get("agent"):
        return Classification(
            kind="agent",
            confidence="high",
            score=100,
            signals=[Signal("apiType", api_type, 100, "API declares the a2a type or agent properties")],
            pattern="a2a",
        )

    if api_type == "mcp":
        pattern = _mcp_pattern(props, api)
        return Classification(
            kind="mcpServer",
            confidence="high",
            score=100,
            signals=[Signal("apiType", "mcp", 100, "APIM first-class MCP API type")],
            pattern=pattern,
        )

    # APIM's unified model API is a first-class model type: one OpenAI-compatible
    # surface that fans out to language-model backends, translating formats. No
    # heuristic needed, and no heuristic should override it.
    if api_type == "unifiedmodelapi":
        return Classification(
            kind="modelApi",
            confidence="high",
            score=100,
            signals=[Signal("apiType", "unifiedModelApi", 100, "APIM first-class unified model API type")],
            provider=None,
            pattern="unifiedModelApi",
        )

    signals: list[Signal] = []
    provider: ProviderRule | None = None

    backend_props = (backend or {}).get("properties") or {}
    resource_id = backend_props.get("resourceId") or ""
    if "/microsoft.cognitiveservices/accounts/" in resource_id.lower():
        signals.append(Signal("backendResourceId", resource_id, 60, "Backend links an Azure AI Foundry account"))
        provider = next(rule for rule in PROVIDERS if rule.kind == "foundry")

    for url in [props.get("serviceUrl")] + backend_urls:
        if not url:
            continue
        rule = provider_for_url(url)
        if rule:
            provider = provider or rule
            signals.append(Signal("backendUrl", url, 50, f"Host matches {rule.label}"))
            break

    llm_elements = policy_element_names & _LLM_POLICY_ELEMENTS
    if llm_elements:
        signals.append(
            Signal("policyElement", ",".join(sorted(llm_elements)), 40, "LLM-specific APIM policy in effect")
        )
    elif policy_families & _LLM_POLICY_FAMILIES:
        signals.append(
            Signal("policyFamily", ",".join(sorted(policy_families & _LLM_POLICY_FAMILIES)), 25, "LLM policy family in effect")
        )

    dialects = api_dialect_for_paths(operation_paths)
    if dialects:
        signals.append(Signal("operationPath", ",".join(dialects), 25, "Operations expose inference routes"))

    if backend_name and _AI_BACKEND_SUFFIX.search(backend_name):
        signals.append(
            Signal(
                "backendNaming", backend_name, 30,
                "Backend follows APIM's AI API import naming convention (-openai-endpoint / -ai-endpoint)",
            )
        )
    ai_named_values = [name for name in (credential_named_values or []) if _AI_NAMED_VALUE_SUFFIX.search(name)]
    if ai_named_values:
        signals.append(
            Signal(
                "namedValueNaming", ",".join(ai_named_values), 15,
                "Backend credential uses APIM's AI API import named-value convention (-LLM)",
            )
        )

    name_blob = " ".join(
        str(value) for value in (api.get("name"), props.get("displayName"), props.get("path")) if value
    )
    if _NAME_HINTS.search(name_blob):
        signals.append(Signal("naming", name_blob[:120], 10, "Name, path, or title suggests a model API"))

    score = sum(signal.weight for signal in signals)
    if score >= 50:
        confidence = "high"
    elif score >= 25:
        confidence = "medium"
    elif score >= 10:
        confidence = "low"
    else:
        return Classification(
            kind="excluded",
            score=score,
            confidence="none",
            signals=signals,
            reason=f"No model, MCP, or agent signal (apiType={api_type})",
        )

    return Classification(
        kind="modelApi",
        score=score,
        confidence=confidence,
        signals=signals,
        provider=provider,
        pattern="inferenceProxy",
    )


def _mcp_pattern(props: dict[str, Any], api: dict[str, Any]) -> str:
    mcp_props = props.get("mcpProperties") or {}
    if mcp_props.get("isFederationRouter") or mcp_props.get("federation"):
        return "federationRouter"
    if props.get("mcpTools") or api.get("_tools"):
        return "toolProjection"
    if props.get("backendId") or props.get("serviceUrl"):
        return "passthrough"
    # An MCP-typed API with no upstream, no tools, and no MCP properties has
    # nothing to route to. It is reported rather than dropped, because it is
    # usually a half-finished import that the operator needs to confirm.
    return "unconfigured"


def matches_any(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(value or "", pattern) for pattern in patterns)
