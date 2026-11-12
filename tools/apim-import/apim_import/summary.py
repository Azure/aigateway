"""Readable summaries of an inventory document."""

from __future__ import annotations

from typing import Any


def render(document: dict[str, Any], *, fmt: str = "text") -> str:
    lines: list[str] = []
    service = document.get("service") or {}
    collection = document.get("collection") or {}
    assets = document.get("assets") or {}

    heading = "## " if fmt == "markdown" else ""
    bullet = "- " if fmt == "markdown" else "  "

    lines.append(f"{heading}APIM AI inventory: {service.get('name')}")
    lines.append(
        f"{bullet}{service.get('resourceId')}"
    )
    sku = (service.get("sku") or {}).get("name")
    lines.append(
        f"{bullet}sku {sku}, region {service.get('location')}, "
        f"vnet {service.get('virtualNetworkType')}, identity {(service.get('identity') or {}).get('type') or 'none'}"
    )
    lines.append(
        f"{bullet}collected {collection.get('completedAt')} in {collection.get('requestCount')} ARM reads"
    )
    lines.append("")

    lines.append(f"{heading}Assets")
    for family, label in (
        ("modelProviders", "model providers"),
        ("models", "model APIs"),
        ("mcpServers", "MCP servers"),
        ("agents", "A2A agents"),
    ):
        items = assets.get(family) or []
        lines.append(f"{bullet}{len(items)} {label}")
        for item in items:
            detection = item.get("detection") or {}
            detail = _asset_detail(family, item)
            name = (item.get("source") or {}).get("name") or item.get("id")
            marker = (
                f"[{item.get('pattern')}, confidence={detection.get('confidence')}]"
                if detection
                else f"[{item.get('providerKind')}]"
            )
            lines.append(
                f"{'  - ' if fmt == 'markdown' else '      '}{name} {marker}"
                + (f" {detail}" if detail else "")
            )
    excluded = document.get("excludedApis") or []
    lines.append(f"{bullet}{len(excluded)} APIs excluded as non-AI")
    lines.append("")

    secrets = document.get("secrets") or []
    retrievable = sum(1 for secret in secrets if secret.get("retrievable"))
    lines.append(f"{heading}Secrets")
    lines.append(
        f"{bullet}{len(secrets)} references, {retrievable} retrievable automatically, "
        f"{len(secrets) - retrievable} needing manual re-provisioning"
    )
    by_class: dict[str, int] = {}
    for secret in secrets:
        by_class[secret.get("class", "unknown")] = by_class.get(secret.get("class", "unknown"), 0) + 1
    for name, count in sorted(by_class.items()):
        lines.append(f"{'  - ' if fmt == 'markdown' else '      '}{name}: {count}")
    lines.append("")

    policies = document.get("policies") or []
    elements = sum((policy.get("stats") or {}).get("elementCount", 0) for policy in policies)
    expressions = sum(len(policy.get("expressions") or []) for policy in policies)
    families: dict[str, int] = {}
    for policy in policies:
        for element in policy.get("elements") or []:
            families[element["family"]] = families.get(element["family"], 0) + 1
    lines.append(f"{heading}Policy surface")
    lines.append(
        f"{bullet}{len(policies)} documents, {elements} elements, {expressions} distinct policy expressions"
    )
    top = sorted(families.items(), key=lambda item: (-item[1], item[0]))[:8]
    if top:
        lines.append(
            f"{bullet}top families: " + ", ".join(f"{name} ({count})" for name, count in top)
        )
    lines.append("")

    warnings = collection.get("warnings") or []
    failures = [entry for entry in (collection.get("coverage") or []) if entry.get("status") == "failed"]
    if warnings or failures:
        lines.append(f"{heading}Gaps in collection")
        for entry in failures:
            lines.append(f"{bullet}{entry['collection']} @ {entry['scope']}: {entry['error']}")
        for warning in warnings:
            lines.append(f"{bullet}{warning.get('code')}: {warning.get('message') or warning.get('error')}")
    return "\n".join(lines)


def _asset_detail(family: str, item: dict[str, Any]) -> str:
    if family == "modelProviders":
        models = item.get("models") or {}
        referenced = item.get("referencedBy") or {}
        resolved = len(models.get("resolved") or [])
        return (
            f"endpoint={item.get('endpoint')} auth={(item.get('auth') or {}).get('mode')} "
            f"models={resolved if resolved else models.get('status')} "
            f"refs={len(referenced.get('apis') or [])} apis/{len(referenced.get('policies') or [])} policies"
        )
    if family == "models":
        provider = item.get("provider") or {}
        models = item.get("models") or {}
        resolved = len(models.get("resolved") or [])
        return (
            f"provider={provider.get('kind')} auth={(provider.get('auth') or {}).get('mode')} "
            f"models={resolved if resolved else models.get('status')}"
        )
    if family == "mcpServers":
        return f"tools={item.get('toolCount')} upstream={len(item.get('upstream') or [])}"
    if family == "agents":
        hosting = item.get("hosting") or {}
        upstream = (item.get("upstream") or [{}])[0]
        return (
            f"agent={(item.get('agent') or {}).get('id')} hosting={hosting.get('kind')}"
            + (f"/{hosting.get('project')}" if hosting.get("project") else "")
            + f" upstream={upstream.get('url') or 'unresolved'}"
        )
    return ""
