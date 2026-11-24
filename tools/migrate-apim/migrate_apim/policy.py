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
    site_policy_id: str = ""
    """The runnable document whose chain pulled this in. Its own, unless it
    came from a fragment: a fragment is never a scope, so the question "is this
    the asset's own policy or something wider" has to be asked of the include
    site. Asked of `policy_id`, extracting a policy into a fragment changed the
    answer."""
    site_level: str = ""
    """That document's scope level: global, workspace, product, api, operation."""
    arrival: tuple[str, ...] = ()
    """The include sites traversed, outermost first, as `<policyId>#<path>`.

    Identifies the route rather than its destination. Two includes of one
    fragment in one document are two executions and both run; the same include
    reached down two product chains is one execution seen twice."""

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
            "sitePolicyId": self.site_policy_id,
            "siteLevel": self.site_level,
        }


@dataclass(frozen=True)
class Resolution:
    """What governs one scope, and what could not be established about it."""

    occurrences: tuple[Occurrence, ...] = ()
    """Everything that governs the scope, once each.

    A set, in document order per chain, and **not an execution sequence**. The
    chains are alternatives -- one per product plus the one with no product --
    so an element that runs last in every chain can appear before one that runs
    last in none. Read `chains` for anything where one element overrides
    another; read this for what covers the scope at all.
    """
    scopes_examined: tuple[str, ...] = ()
    unresolved_fragments: tuple[str, ...] = ()
    inheritance_breaks: tuple[dict[str, Any], ...] = ()
    chains: tuple[tuple[Occurrence, ...], ...] = ()
    """Each alternative request context in order, before they were unioned.

    `occurrences` is the union, which is the right shape for asking what a
    policy covers and the wrong one for asking what runs last: a product is an
    alternative, so a flattened union of several is not an execution sequence.
    Anything that reads one element as overriding another has to read a chain.
    """
    unreadable_fragments: tuple[str, ...] = ()
    """Fragment documents reached and not readable, by id.

    Apart from `unresolved_fragments`, which names what resolved to no document
    at all. The two look alike and are not: one has an item of its own to carry
    the parse error, the other has nothing anywhere."""

    @property
    def elements(self) -> list[dict[str, Any]]:
        return [occurrence.tagged() for occurrence in self.occurrences]


class PolicyGraph:
    """Every policy document the inventory holds, and the relations between them.

    Built from the inventory alone -- nothing here reads ARM, and nothing here
    needs a field the collector does not already write. `products` carries the
    product-to-API membership, which is the one relation that is not in a policy
    document.

    One direction only, deliberately: everything is asked of what a scope
    resolves to. A reverse query -- which scopes include this fragment -- was
    the obvious companion and had to go, because it answered from the
    references written in the documents rather than from the routes requests
    actually take. It called a fragment included by an API nobody is migrating
    "included", and it missed a branch partway down a chain that the forward
    walk saw. Two views of one index still disagreed, which is the thing this
    module exists to stop.
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
        state = _Walk(self)
        occurrences: list[Occurrence] = []
        chains: list[tuple[Occurrence, ...]] = []
        examined: list[str] = []
        # One chain per product, not one chain through all of them. A product is
        # an alternative context -- which one applies depends on the
        # subscription the call arrived on -- so stacking them made the order
        # they were collected in decide the answer, and let one product's
        # section without `<base />` suppress another product's policy and the
        # global policy with it. Resolved apart and unioned, every product's
        # policy reaches the plan and none of them cuts off a sibling.
        for chain in self._chains(
            api=api, workspace=workspace, operation=operation, levels=levels
        ):
            resolved: list[Occurrence] = []
            for section in SECTIONS:
                resolved.extend(state.expand_scope(chain, len(chain) - 1, section))
            # Deduplicated within the chain, where a repeated include is a
            # repeated execution and survives, but never across chains: that is
            # what makes this an order you can read.
            chains.append(tuple(unique_occurrences(resolved)))
            occurrences.extend(resolved)
            for _, document in chain:
                if document is not None and document["id"] not in examined:
                    examined.append(document["id"])
        return Resolution(
            occurrences=tuple(unique_occurrences(occurrences)),
            scopes_examined=tuple(examined),
            unresolved_fragments=tuple(state.unresolved),
            unreadable_fragments=tuple(state.unreadable),
            inheritance_breaks=tuple(_unique_breaks(state.breaks)),
            chains=tuple(chains),
        )

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

    def operations_of(self, *, api: str, workspace: str | None = None) -> list[str]:
        """The operations of one API that have a policy document of their own.

        Operation policies are collected only when asked for, so this is empty
        on an ordinary run -- and an operation-scoped policy that nothing
        resolved would otherwise raise no item at all.
        """
        scoped = _fold(ids.scoped(workspace, api))
        names: list[str] = []
        for document in self._documents:
            scope = document.get("scope") or {}
            if scope.get("level") != "operation":
                continue
            parent = _fold(ids.scoped(_workspace_of(scope), scope.get("apiName") or ""))
            if parent == scoped and scope.get("name"):
                names.append(scope["name"])
        return names

    def fragments(self) -> list[dict[str, Any]]:
        """Every collected fragment document, in inventory order."""
        return [
            document
            for document in self._documents
            if (document.get("scope") or {}).get("level") == "fragment"
        ]

    # --------------------------------------------------------------- scopes

    def _chains(
        self, *, api: str, workspace: str | None, operation: str | None, levels: Sequence[str]
    ) -> list[list[tuple[str, dict[str, Any] | None]]]:
        """The scopes governing one API, outermost first -- one chain per product.

        Several products can carry the same API, and which one's policy runs
        depends on the subscription the call arrived on. Each is therefore its
        own chain rather than a link in one: reporting a product's limit only
        when it happens to be collected last would be a confident negative.
        """
        scoped = ids.scoped(workspace, api)
        head: list[tuple[str, dict[str, Any] | None]] = []
        if "global" in levels:
            head.append(("global", self._by_id.get(ids.policy("global"))))
        if "workspace" in levels and workspace and workspace.lower() != "default":
            head.append(("workspace", self._by_id.get(ids.policy("workspace", workspace))))
        tail: list[tuple[str, dict[str, Any] | None]] = []
        if "api" in levels:
            tail.append(("api", self._by_id.get(ids.policy("api", scoped))))
        if "operation" in levels and operation:
            tail.append(
                ("operation", self._by_id.get(ids.policy("operation", f"{scoped}/{operation}")))
            )
        # The chain with no product in it is always one of them. A
        # subscription scoped to the API, or service-wide, carries no product,
        # so dropping it let a product that omits `<base />` cut the global
        # policy out of request contexts that never passed through a product at
        # all -- and a linked product with no policy document of its own, which
        # inherits transparently, is not in `_products_of` to put it back.
        chains = [head + tail]
        if "product" in levels:
            chains.extend(
                head + [("product", self._by_id.get(product))] + tail
                for product in self._products_of(api, workspace)
            )
        return chains

    def _products_of(self, api: str, workspace: str | None) -> list[str]:
        api_id = ids.api(api, workspace)
        return [
            product["policyId"]
            for product in self._products
            if product.get("policyId") and api_id in (product.get("apiIds") or [])
        ]

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
    unresolved: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
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
        level = chain[index][0]
        for element in document.get("elements") or []:
            if (element.get("section") or "") != section:
                continue
            conditional = under_conditional(element)
            out.append(Occurrence(
                element=element,
                policy_id=document["id"],
                section=section,
                under_conditional=conditional,
                site_policy_id=document["id"],
                site_level=level,
            ))
            if element.get("name") == "base":
                inherited = True
                out.extend(self.expand_scope(chain, index - 1, section))
            elif element.get("name") == "include-fragment" and element.get("fragmentId"):
                out.extend(self.expand_fragment(
                    element["fragmentId"], section=section, via=(),
                    under_branch=conditional, seen=frozenset(),
                    site_policy_id=document["id"], site_level=level,
                    arrival=(_site(document, element),),
                    # The workspace of the document that authored the include,
                    # not of the API consuming it. An `include-fragment` in the
                    # global policy names a service fragment wherever it is
                    # inherited, and resolving it against the reader's
                    # workspace handed a finance API the finance fragment --
                    # a different policy, and one the reverse lookup disagreed
                    # with.
                    workspace=_workspace_of(document.get("scope") or {}),
                ))
        if not inherited:
            # The nearest ancestor that says anything, not the immediate one:
            # a scope with no policy of its own is transparent, so an API that
            # drops `<base />` while its product is silent is still overriding
            # the global policy, and reporting only against the product would
            # have found nothing to report.
            for above in range(index - 1, -1, -1):
                parent_level, parent = chain[above]
                if parent is not None and _declares(parent, section):
                    self.breaks.append({
                        "policyId": document["id"], "section": section,
                        "parentLevel": parent_level, "parentPolicyId": parent["id"],
                    })
                    break
        return out

    def expand_fragment(
        self,
        name: str,
        *,
        section: str,
        via: tuple[str, ...],
        under_branch: bool,
        seen: frozenset[str],
        workspace: str | None,
        site_policy_id: str,
        site_level: str,
        arrival: tuple[str, ...],
    ) -> list[Occurrence]:
        """A fragment's elements, as they run at the site that included them."""
        document = self.graph.fragment_document(name, workspace)
        if document is None:
            # Nothing of this name anywhere the include could see it.
            if name not in self.unresolved:
                self.unresolved.append(name)
            return []
        if document.get("parseError"):
            # Found and not readable, which is as unknown as never collected --
            # splicing its empty element list would say the include contributed
            # nothing, the one thing nobody can know about it. Recorded by
            # document rather than by name, because the document has an item of
            # its own to carry the parse error, and a name is not an identity:
            # an `hr` API naming `limits` when only `finance/limits` exists
            # resolves to nothing, and matching those two by name hid it.
            if document["id"] not in self.unreadable:
                self.unreadable.append(document["id"])
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
                site_policy_id=site_policy_id,
                site_level=site_level,
                arrival=arrival,
            ))
            if element.get("name") == "include-fragment" and element.get("fragmentId"):
                out.extend(self.expand_fragment(
                    element["fragmentId"], section=section, via=chain,
                    under_branch=conditional, seen=seen | {key},
                    site_policy_id=site_policy_id, site_level=site_level,
                    arrival=(*arrival, _site(document, element)),
                    # A nested include is authored in the fragment, so the
                    # fragment's own workspace is what resolves it.
                    workspace=_workspace_of(document.get("scope") or {}),
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


def unique_occurrences(occurrences: Iterable[Occurrence]) -> list[Occurrence]:
    """One occurrence per element per route, keeping the first.

    Two products carrying the same API each inherit the same global policy, and
    the global elements would otherwise be reported twice.
    """
    seen: set[tuple[int, tuple[str, ...], str, bool]] = set()
    out: list[Occurrence] = []
    for occurrence in occurrences:
        # The element itself, not where it is written: a document can hold two
        # elements at one path -- nothing stops it -- and collapsing those would
        # drop a policy rather than a duplicate route.
        #
        # Keyed on the route and not on its destination. A document that
        # includes one fragment twice runs it twice, and whether that matters
        # is not this function's to decide: `_backend_auth` reads the last
        # managed identity in the list, so dropping the second arrival changed
        # which credential an API was recorded as using. What is genuinely one
        # execution seen twice is the same include reached down two product
        # chains, and that collapses because the route is identical.
        key = (id(occurrence.element), occurrence.arrival,
               occurrence.section, occurrence.under_conditional)
        if key not in seen:
            seen.add(key)
            out.append(occurrence)
    return out


def _site(document: dict[str, Any], element: dict[str, Any]) -> str:
    """One include, identified by where it is written rather than what it names."""
    return f"{document['id']}#{element.get('path') or ''}"


def _unique_breaks(breaks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One break per scope and section, however many product chains found it."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for entry in breaks:
        key = (entry["policyId"], entry["section"])
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return out


def _fold(name: str) -> str:
    return (name or "").strip().casefold()


def _workspace_of(scope: dict[str, Any]) -> str:
    """The workspace a policy document belongs to, default when it says none."""
    return scope.get("workspace") or "default"
