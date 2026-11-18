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
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

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


# --------------------------------------------------------------- resolution
#
# Which policy governs which API is one question, and until this it had two
# answers in two modules -- a forward walk in the collector and a backward one
# in the planner -- built from different inputs and already disagreeing about
# workspace scope. A third, reading the de-duplicated `fragmentRefs` name list,
# would have lost the include site's section and its conditional context.
#
# So it is answered once, here, beside the parser whose output it indexes.
# `include-fragment` and `base` are already elements carrying a section and a
# path, which means inclusion and inheritance are facts in the document rather
# than something a caller re-derives: the graph reads them, and the forward and
# backward views come from one index, which is what stops them drifting apart.

# Control flow that decides whether the statement inside it runs at all. The
# element itself records nothing about that; the path is the only place the
# branch survives normalization.
CONDITIONAL_WRAPPERS = frozenset({"choose", "when", "otherwise"})

# The scopes APIM evaluates, outermost first. A fragment is deliberately not one
# of them: it is not a scope anything runs at, it is content spliced into one.
SCOPE_CHAIN = ("global", "workspace", "product", "api", "operation")


def ancestors(element: dict[str, Any]) -> list[str]:
    """The elements enclosing this one, outermost first, occurrence index removed."""
    return [segment.split("[", 1)[0] for segment in (element.get("path") or "").split("/")[:-1]]


def under_conditional(element: dict[str, Any]) -> bool:
    """Whether a branch of the source policy decides if this element runs at all."""
    return any(name in CONDITIONAL_WRAPPERS for name in ancestors(element))


@dataclass(frozen=True)
class Occurrence:
    """One policy element, and the path by which it reaches a scope.

    An element in a fragment has no section of its own -- a fragment has no
    `inbound` wrapper -- so `section` is the include site's, not the one the
    element was parsed under. `under_conditional` is likewise cumulative: a
    fragment included inside a `choose` runs conditionally however
    unconditionally its own body reads.
    """

    element: dict[str, Any]
    policy_id: str
    section: str
    via: tuple[str, ...] = ()
    under_conditional: bool = False

    @property
    def name(self) -> str:
        return self.element.get("name") or ""

    @property
    def path(self) -> str:
        return self.element.get("path") or ""

    def tagged(self) -> dict[str, Any]:
        """The element, carrying where it came from and how it got here."""
        return {
            **self.element,
            "policyId": self.policy_id,
            "section": self.section,
            "via": list(self.via),
            "underConditional": self.under_conditional,
        }


@dataclass(frozen=True)
class Resolution:
    """What governs one scope, and what could not be established about it."""

    occurrences: tuple[Occurrence, ...] = ()
    scopes_examined: tuple[str, ...] = ()
    unresolved_fragments: tuple[str, ...] = ()
    inheritance_breaks: tuple[dict[str, Any], ...] = ()

    @property
    def elements(self) -> list[dict[str, Any]]:
        return [occurrence.tagged() for occurrence in self.occurrences]


class PolicyGraph:
    """Every policy document the inventory holds, and the relations between them.

    Built from the inventory alone -- nothing here reads ARM, and nothing here
    needs a field the collector does not already write. `products` carries the
    product-to-API membership, which is the one relation that is not in a policy
    document.
    """

    def __init__(
        self,
        documents: Iterable[dict[str, Any]],
        *,
        products: Iterable[dict[str, Any]] = (),
    ) -> None:
        self._documents: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._products: list[dict[str, Any]] = []
        # Keyed by workspace and name, both folded: APIM resource names do not
        # distinguish case and a `fragment-id` is authored by hand, so matching
        # exactly would report a fragment that resolves fine in APIM as one
        # naming nothing. Two workspaces may hold a same-named fragment, and
        # they are two fragments.
        self._fragments: dict[tuple[str, str], dict[str, Any]] = {}
        self._includes: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for document in documents:
            self.add(document)
        self.add_products(products)

    def add(self, document: dict[str, Any]) -> None:
        """Index one policy document.

        Incremental so the collector can keep one graph for a whole run and
        index each document as it captures it: the graph is then current when a
        policy is read back, without rebuilding it per API.
        """
        if document["id"] in self._by_id:
            return
        self._documents.append(document)
        self._by_id[document["id"]] = document
        scope = document.get("scope") or {}
        if scope.get("level") == "fragment":
            key = (_fold(_workspace_of(scope)), _fold(scope.get("name") or ""))
            self._fragments.setdefault(key, document)
        for element in document.get("elements") or []:
            if element.get("name") == "include-fragment" and element.get("fragmentId"):
                self._includes.setdefault(_fold(element["fragmentId"]), []).append(
                    (document, element)
                )

    def add_products(self, products: Iterable[dict[str, Any]]) -> None:
        """Product-to-API membership: the one relation not in a policy document."""
        known = {id(product) for product in self._products}
        self._products.extend(product for product in products if id(product) not in known)

    # -------------------------------------------------------------- forward

    def governing(
        self,
        *,
        api: str,
        workspace: str | None = None,
        operation: str | None = None,
        levels: Sequence[str] = SCOPE_CHAIN,
    ) -> Resolution:
        """The elements that actually run for one API, in order.

        Walks the scope chain and splices a parent's section in where the child
        carries `<base />`, because that is the only thing that makes a parent
        run: an API whose `inbound` omits it does not inherit the global policy,
        however globally that policy is written. A scope with no document of its
        own inherits, which is APIM's default template.
        """
        state = _Walk(self, workspace=workspace)
        chain = self._chain(api=api, workspace=workspace, operation=operation, levels=levels)
        occurrences: list[Occurrence] = []
        for section in SECTIONS:
            occurrences.extend(state.expand_scope(chain, len(chain) - 1, section))
        return Resolution(
            occurrences=tuple(_unique(occurrences)),
            scopes_examined=tuple(
                document["id"] for _, document in chain if document is not None
            ),
            unresolved_fragments=tuple(state.unresolved),
            inheritance_breaks=tuple(state.breaks),
        )

    # ------------------------------------------------------------- backward

    def includers(self, fragment: str) -> list[Occurrence]:
        """The scopes whose policy runs a fragment, as the sites that include it.

        The same index read the other way, so a fragment's includers and an
        API's governing elements cannot disagree about what includes what. A
        fragment reached through another fragment resolves to the runnable scope
        at the end of the chain, since a fragment is never a scope itself, and
        `via` names that chain from the include site inwards.
        """
        target = self._fragments_by_id().get(fragment)
        if target is None:
            return []
        found: list[Occurrence] = []
        seen: set[str] = set()
        pending: list[tuple[dict[str, Any], tuple[str, ...]]] = [(target, ())]
        while pending:
            document, via = pending.pop(0)
            if document["id"] in seen:
                # APIM stores a cycle of includes even though it cannot run one.
                continue
            seen.add(document["id"])
            name = _fold((document.get("scope") or {}).get("name") or "")
            for site, element in self._includes.get(name, []):
                site_scope = site.get("scope") or {}
                if self._fragment_for(element["fragmentId"], _workspace_of(site_scope)) is not document:
                    continue
                chain = (document["id"], *via)
                if site_scope.get("level") == "fragment":
                    pending.append((site, chain))
                    continue
                found.append(Occurrence(
                    element=element,
                    policy_id=site["id"],
                    section=element.get("section") or "",
                    via=chain,
                    under_conditional=under_conditional(element),
                ))
        return found

    def unresolved(self) -> list[str]:
        """`fragment-id`s naming no collected fragment: unknown, not absent."""
        return sorted(
            {
                element["fragmentId"]
                for sites in self._includes.values()
                for site, element in sites
                if self._fragment_for(
                    element["fragmentId"], _workspace_of(site.get("scope") or {})
                ) is None
            }
        )

    def fragments(self) -> list[dict[str, Any]]:
        """Every collected fragment document, in inventory order."""
        return [
            document
            for document in self._documents
            if (document.get("scope") or {}).get("level") == "fragment"
        ]

    # --------------------------------------------------------------- scopes

    def _chain(
        self, *, api: str, workspace: str | None, operation: str | None, levels: Sequence[str]
    ) -> list[tuple[str, dict[str, Any] | None]]:
        """The scopes governing one API, outermost first."""
        scoped = ids.scoped(workspace, api)
        chain: list[tuple[str, dict[str, Any] | None]] = []
        if "global" in levels:
            chain.append(("global", self._by_id.get(ids.policy("global"))))
        if "workspace" in levels and workspace and workspace.lower() != "default":
            chain.append(("workspace", self._by_id.get(ids.policy("workspace", workspace))))
        if "product" in levels:
            # Several products can carry the same API, and which one's policy
            # runs depends on the subscription the call arrived on. They stack
            # here rather than one being chosen, because reporting one product's
            # limit and not another's would be a confident negative.
            for product in self._products_of(api, workspace):
                chain.append(("product", self._by_id.get(product)))
        if "api" in levels:
            chain.append(("api", self._by_id.get(ids.policy("api", scoped))))
        if "operation" in levels and operation:
            chain.append(
                ("operation", self._by_id.get(ids.policy("operation", f"{scoped}/{operation}")))
            )
        return chain

    def _products_of(self, api: str, workspace: str | None) -> list[str]:
        api_id = ids.api(api, workspace)
        return [
            product["policyId"]
            for product in self._products
            if product.get("policyId") and api_id in (product.get("apiIds") or [])
        ]

    def _fragments_by_id(self) -> dict[str, dict[str, Any]]:
        return {document["id"]: document for document in self.fragments()}

    def _fragment_for(self, name: str, workspace: str | None) -> dict[str, Any] | None:
        """The fragment a `fragment-id` names, as seen from one workspace.

        A workspace's own fragment wins. The fall back to the service-wide one
        is the lenient reading: resolving to nothing makes the include a
        blocking gap, and reporting that over a fragment APIM resolves happily
        would be a confident negative in the direction that costs most.
        """
        key = _fold(name)
        folded = _fold(workspace or "default")
        return self._fragments.get((folded, key)) or self._fragments.get(("default", key))

    def fragment_document(
        self, name: str, workspace: str | None = None
    ) -> dict[str, Any] | None:
        return self._fragment_for(name, workspace)


@dataclass
class _Walk:
    """One `governing` call: the splices it made and what it could not splice."""

    graph: PolicyGraph
    workspace: str | None = None
    unresolved: list[str] = field(default_factory=list)
    breaks: list[dict[str, Any]] = field(default_factory=list)

    def expand_scope(
        self,
        chain: list[tuple[str, dict[str, Any] | None]],
        index: int,
        section: str,
    ) -> list[Occurrence]:
        """What runs at `section` for chain[index], parents spliced at `<base />`."""
        if index < 0:
            return []
        _, document = chain[index]
        if document is None or not _declares(document, section):
            # No policy of its own at this section is APIM's default template,
            # which is `<base />`: the parent runs.
            return self.expand_scope(chain, index - 1, section)
        out: list[Occurrence] = []
        inherited = False
        for element in document.get("elements") or []:
            if (element.get("section") or "") != section:
                continue
            conditional = under_conditional(element)
            out.append(Occurrence(
                element=element,
                policy_id=document["id"],
                section=section,
                under_conditional=conditional,
            ))
            if element.get("name") == "base":
                inherited = True
                out.extend(self.expand_scope(chain, index - 1, section))
            elif element.get("name") == "include-fragment" and element.get("fragmentId"):
                out.extend(self.expand_fragment(
                    element["fragmentId"], section=section, via=(),
                    under_branch=conditional, seen=frozenset(),
                ))
        if not inherited and index > 0:
            parent_level, parent = chain[index - 1]
            if parent is not None and _declares(parent, section):
                self.breaks.append({
                    "policyId": document["id"], "section": section,
                    "parentLevel": parent_level, "parentPolicyId": parent["id"],
                })
        return out

    def expand_fragment(
        self,
        name: str,
        *,
        section: str,
        via: tuple[str, ...],
        under_branch: bool,
        seen: frozenset[str],
    ) -> list[Occurrence]:
        """A fragment's elements, as they run at the site that included them."""
        document = self.graph.fragment_document(name, self.workspace)
        if document is None:
            if name not in self.unresolved:
                self.unresolved.append(name)
            return []
        key = document["id"]
        if key in seen:
            # APIM accepts a fragment including one that includes it back, and
            # stores it, even though it could never execute it.
            return []
        chain = (*via, key)
        out: list[Occurrence] = []
        for element in document.get("elements") or []:
            conditional = under_branch or under_conditional(element)
            out.append(Occurrence(
                element=element,
                policy_id=document["id"],
                section=section,
                via=chain,
                under_conditional=conditional,
            ))
            if element.get("name") == "include-fragment" and element.get("fragmentId"):
                out.extend(self.expand_fragment(
                    element["fragmentId"], section=section, via=chain,
                    under_branch=conditional, seen=seen | {key},
                ))
        return out


def _declares(document: dict[str, Any], section: str) -> bool:
    """Whether a document says anything about one section.

    Silence is inheritance, so this has to tell an empty `<inbound />` -- which
    stops the parent -- from a document that never mentions inbound at all.
    """
    sections = ((document.get("stats") or {}).get("sections")) or []
    if sections:
        return section in sections
    return any((element.get("section") or "") == section for element in document.get("elements") or [])


def _unique(occurrences: Iterable[Occurrence]) -> list[Occurrence]:
    """One occurrence per element per route, keeping the first.

    Two products carrying the same API each inherit the same global policy, and
    the global elements would otherwise be reported twice.
    """
    seen: set[tuple[int, tuple[str, ...]]] = set()
    out: list[Occurrence] = []
    for occurrence in occurrences:
        # The element itself, not where it is written: a document can hold two
        # elements at one path -- nothing stops it -- and collapsing those would
        # drop a policy rather than a duplicate route.
        key = (id(occurrence.element), occurrence.via)
        if key not in seen:
            seen.add(key)
            out.append(occurrence)
    return out


def _fold(name: str) -> str:
    return (name or "").strip().casefold()


def _workspace_of(scope: dict[str, Any]) -> str:
    """The workspace a policy document belongs to, default when it says none."""
    return scope.get("workspace") or "default"
