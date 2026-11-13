"""Policy XML capture and normalization.

APIM expresses most of its AI governance in policy XML at four or five scopes.
Feasibility of a migration is decided almost entirely here, so the collector
keeps the raw document *and* a normalized element list: one record per policy
element, with its section, attributes, named-value references, and policy
expressions. The mapping verdict is deliberately not computed here -- that
belongs to the assessment stage and its versioned capability map.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Callable

from . import ids, secrets

SECTIONS = ("inbound", "backend", "outbound", "on-error")

_EXPRESSION = re.compile(r"@[({]")

# Descriptive grouping only -- what a policy element is about, not whether it
# can migrate. Elements absent from this table are reported with family
# "other", which is a prompt for the assessment stage, not a silent drop.
FAMILIES: dict[str, str] = {
    # inbound auth / identity
    "validate-jwt": "authentication",
    "validate-azure-ad-token": "authentication",
    "authentication-basic": "backendAuthentication",
    "authentication-certificate": "backendAuthentication",
    "authentication-managed-identity": "backendAuthentication",
    "get-authorization-context": "backendAuthentication",
    "check-header": "authentication",
    "validate-client-certificate": "authentication",
    # throttling and quotas
    "rate-limit": "rateLimit",
    "rate-limit-by-key": "rateLimit",
    "quota": "quota",
    "quota-by-key": "quota",
    "limit-concurrency": "concurrency",
    "azure-openai-token-limit": "tokenLimit",
    "llm-token-limit": "tokenLimit",
    # LLM-specific
    "azure-openai-emit-token-metric": "tokenMetrics",
    "llm-emit-token-metric": "tokenMetrics",
    "azure-openai-semantic-cache-lookup": "semanticCache",
    "azure-openai-semantic-cache-store": "semanticCache",
    "llm-semantic-cache-lookup": "semanticCache",
    "llm-semantic-cache-store": "semanticCache",
    "azure-openai-content-safety": "contentSafety",
    "llm-content-safety": "contentSafety",
    # MCP-specific
    "mcp-server": "mcp",
    "validate-mcp-request": "mcp",
    # routing
    "set-backend-service": "routing",
    "forward-request": "routing",
    "retry": "resilience",
    "set-service-url": "routing",
    # network admission
    "ip-filter": "ipFilter",
    "cors": "cors",
    # transformation
    "set-header": "transform",
    "set-query-parameter": "transform",
    "set-body": "transform",
    "set-variable": "transform",
    "rewrite-uri": "transform",
    "json-to-xml": "transform",
    "xml-to-json": "transform",
    "find-and-replace": "transform",
    "redirect-content-urls": "transform",
    # caching
    "cache-lookup": "cache",
    "cache-store": "cache",
    "cache-lookup-value": "cache",
    "cache-store-value": "cache",
    # observability
    "trace": "observability",
    "emit-metric": "observability",
    "log-to-eventhub": "observability",
    # control flow and composition
    "choose": "controlFlow",
    "when": "controlFlow",
    "otherwise": "controlFlow",
    "base": "composition",
    "include-fragment": "composition",
    "return-response": "controlFlow",
    "send-request": "sideEffect",
    "send-one-way-request": "sideEffect",
    "wait": "controlFlow",
    "validate-content": "validation",
    "validate-headers": "validation",
    "validate-status-code": "validation",
    "validate-parameters": "validation",
    "validate-odata-request": "validation",
    "validate-graphql-request": "validation",
}


def family_of(element_name: str) -> str:
    return FAMILIES.get(element_name, "other")


class PolicyParseError(ValueError):
    pass


def parse(
    xml_text: str,
    *,
    policy_id: str,
    scope: dict[str, Any],
    scope_url: str,
    registry: secrets.SecretRegistry | None = None,
) -> dict[str, Any]:
    """Normalize one policy document.

    Returns the record stored under ``policies[]`` in the inventory, including a
    redacted copy of the raw XML.
    """
    cleaned = (xml_text or "").lstrip("﻿").strip()
    document: dict[str, Any] = {
        "id": policy_id,
        "scope": scope,
        "format": "rawxml",
        "elements": [],
        "expressions": [],
        "namedValueRefs": [],
        "fragmentRefs": [],
        "secretRefs": [],
        "stats": {},
        "parseError": None,
        "xml": cleaned,
    }
    if not cleaned:
        document["stats"] = {"elementCount": 0, "expressionCount": 0, "sections": []}
        return document

    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        document["parseError"] = f"{exc}"
        document["stats"] = {"elementCount": 0, "expressionCount": 0, "sections": []}
        return document

    expressions: dict[str, dict[str, Any]] = {}
    named_values: list[str] = []
    fragments: list[str] = []
    secret_refs: list[str] = []
    redactions: list[dict[str, Any]] = []

    def register_literal(path: str, literal_class: str, raw: str) -> str:
        if registry is not None:
            ref_id = registry.policy_inline(
                policy_id=policy_id,
                scope_url=scope_url,
                xpath=path,
                literal_class=literal_class,
                used_by=policy_id,
            )
            if ref_id not in secret_refs:
                secret_refs.append(ref_id)
            redactions.append({"path": path, "class": literal_class, "secretRef": ref_id, "_raw": raw})
            return ref_id
        redactions.append({"path": path, "class": literal_class, "secretRef": None, "_raw": raw})
        return "<redacted>"

    sections_present: list[str] = []
    walk_args = {
        "out": document["elements"],
        "expressions": expressions,
        "named_values": named_values,
        "fragments": fragments,
        "register_literal": register_literal,
    }

    section_children = [child for child in root if _tag(child) in SECTIONS]
    if section_children:
        for child in section_children:
            name = _tag(child)
            sections_present.append(name)
            _walk(child, section=name, path=name, depth=0, **walk_args)
    else:
        # A policy fragment has no inbound/backend/outbound wrapper: its elements
        # are the direct children of <fragment>.
        sections_present.append("fragment")
        _walk(root, section="fragment", path="fragment", depth=0, **walk_args)

    document["expressions"] = list(expressions.values())
    document["namedValueRefs"] = _dedupe(named_values)
    document["fragmentRefs"] = _dedupe(fragments)
    document["secretRefs"] = secret_refs
    document["redactions"] = redactions
    if redactions:
        document["xml"] = _redact_xml(cleaned, redactions)
    document["stats"] = {
        "elementCount": len(document["elements"]),
        "expressionCount": len(document["expressions"]),
        "sections": _dedupe(sections_present),
        "families": sorted({element["family"] for element in document["elements"]}),
    }
    return document


def _tag(node: ET.Element) -> str:
    tag = node.tag
    return tag.split("}", 1)[-1] if isinstance(tag, str) else str(tag)


def _walk(
    node: ET.Element,
    *,
    section: str,
    path: str,
    depth: int,
    out: list[dict[str, Any]],
    expressions: dict[str, dict[str, Any]],
    named_values: list[str],
    fragments: list[str],
    register_literal: Callable[[str, str, str], str],
) -> None:
    counters: dict[str, int] = {}
    for child in node:
        name = _tag(child)
        counters[name] = counters.get(name, 0) + 1
        child_path = f"{path}/{name}[{counters[name]}]"
        record: dict[str, Any] = {
            "section": section,
            "path": child_path,
            "name": name,
            "family": family_of(name),
            "depth": depth + 1,
            "attributes": {},
            "text": None,
            "expressionIds": [],
            "namedValueRefs": [],
            "childNames": sorted({_tag(sub) for sub in child}),
        }

        for attr_name, attr_value in (child.attrib or {}).items():
            value = _capture_value(
                attr_value,
                path=f"{child_path}/@{attr_name}",
                parameter_name=attr_name,
                record=record,
                expressions=expressions,
                named_values=named_values,
                register_literal=register_literal,
            )
            record["attributes"][attr_name] = value

        text = (child.text or "").strip()
        if text:
            record["text"] = _capture_value(
                text,
                path=f"{child_path}/text()",
                parameter_name=child.attrib.get("name") if child.attrib else None,
                record=record,
                expressions=expressions,
                named_values=named_values,
                register_literal=register_literal,
            )

        if name == "include-fragment":
            fragment_id = child.attrib.get("fragment-id")
            if fragment_id:
                fragments.append(fragment_id)
                record["fragmentId"] = fragment_id

        out.append(record)
        _walk(
            child,
            section=section,
            path=child_path,
            depth=depth + 1,
            out=out,
            expressions=expressions,
            named_values=named_values,
            fragments=fragments,
            register_literal=register_literal,
        )


def _capture_value(
    raw: str,
    *,
    path: str,
    parameter_name: str | None,
    record: dict[str, Any],
    expressions: dict[str, dict[str, Any]],
    named_values: list[str],
    register_literal: Callable[[str, str, str], str],
) -> str:
    refs = secrets.named_value_references(raw)
    if refs:
        named_values.extend(refs)
        record["namedValueRefs"].extend(refs)

    if _EXPRESSION.search(raw):
        expression_id = _register_expression(raw, expressions)
        if expression_id not in record["expressionIds"]:
            record["expressionIds"].append(expression_id)
        return raw

    literal_class = secrets.classify_literal(raw, parameter_name=parameter_name)
    if literal_class and literal_class != "declaredCredentialParameter":
        register_literal(path, literal_class, raw)
        return secrets.redact(raw)
    if literal_class == "declaredCredentialParameter" and not refs:
        register_literal(path, literal_class, raw)
        return secrets.redact(raw)
    return raw


def _register_expression(raw: str, expressions: dict[str, dict[str, Any]]) -> str:
    normalized = re.sub(r"\s+", " ", raw).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    expression_id = ids.expression(digest)
    if expression_id in expressions:
        return expression_id
    literal_class = secrets.classify_literal(normalized)
    record = {
        "id": expression_id,
        "sha256": digest,
        "length": len(raw),
        "multiline": "\n" in raw,
        "source": None if literal_class else normalized[:600],
        "truncated": not literal_class and len(normalized) > 600,
        "containsLiteralSecret": bool(literal_class),
        "references": sorted(set(re.findall(r"context\.[A-Za-z0-9_.]+", normalized))),
    }
    expressions[expression_id] = record
    return expression_id


def _redact_xml(xml_text: str, redactions: list[dict[str, Any]]) -> str:
    """Replace detected literals in the raw document.

    Values are matched textually because the parse tree does not retain offsets.
    """
    redacted = xml_text
    for entry in redactions:
        raw = entry.pop("_raw", None)
        if raw:
            redacted = redacted.replace(raw, secrets.redact(raw))
    return redacted


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
