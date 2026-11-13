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


def render_plan(document: dict[str, Any], *, fmt: str = "text") -> str:
    """A readable view of the plan, grouped by what still needs deciding."""
    lines: list[str] = []
    summary = document.get("summary") or {}
    source = document.get("source") or {}
    target = document.get("target") or {}
    bullet = "- " if fmt == "markdown" else "  "
    heading = "## " if fmt == "markdown" else ""

    lines.append(f"{heading}Migration plan: {source.get('name')}")
    caps = target.get("capabilities") or {}
    lines.append(
        f"{bullet}{summary.get('total')} items against CLI {caps.get('cliVersion')} "
        f"({'probed' if caps.get('probed') else 'declared, not probed'})"
    )
    by_status = summary.get("byStatus") or {}
    lines.append(
        f"{bullet}" + ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    )
    lines.append("")

    unsettled = [
        item for item in document.get("items") or []
        if item.get("status") in {"needs-decision", "stale"}
    ]
    lines.append(f"{heading}Needs a decision ({len(unsettled)}, {summary.get('blocking')} blocking)")
    for kind, count in (summary.get("byKind") or {}).items():
        lines.append(f"{bullet}{kind}: {count}")
    for item in unsettled:
        flag = "!" if item.get("blocking") else " "
        src = item.get("source") or {}
        asset = src.get("assetId") or f"{src.get('assetKind')}:{src.get('aspect')}"
        options = "/".join(option["value"] for option in item.get("options") or [])
        lines.append(
            f"{'  - ' if fmt == 'markdown' else '    '}{flag} [{item.get('kind')}] {asset}"
            f" -> proposal={item.get('proposal')}"
            + (f" of {options}" if options else "")
        )
        if item.get("status") == "stale":
            lines.append(f"{'      ' if fmt != 'markdown' else '    '}stale: {item.get('staleReason')}")
    lines.append("")

    ready = [item for item in document.get("items") or [] if item.get("status") == "ready"]
    lines.append(f"{heading}Ready to execute ({len(ready)})")
    for item in ready[:12]:
        lines.append(
            f"{'  - ' if fmt == 'markdown' else '    '}{item.get('capabilityId')}: "
            f"{(item.get('source') or {}).get('assetId')}"
            f" [{(item.get('source') or {}).get('aspect')}]"
        )
    if len(ready) > 12:
        lines.append(f"{'  - ' if fmt == 'markdown' else '    '}... and {len(ready) - 12} more")
    lines.append("")

    # Bad news belongs in the summary. Reported only inside the plan file, a gap
    # or an orphaned decision leaves this view reading as a clean bill of health
    # for a plan that will not carry out part of what it was asked to.
    gaps = document.get("plannerGaps") or []
    if gaps:
        lines.append(f"{heading}Will not happen as planned ({len(gaps)})")
        for entry in gaps:
            lines.append(f"{bullet}{entry.get('id')}: {entry.get('gap')}")
        lines.append("")

    orphaned = document.get("orphanedDecisions") or []
    if orphaned:
        lines.append(f"{heading}Settled decisions with no item ({len(orphaned)})")
        for entry in orphaned:
            lines.append(f"{bullet}{entry.get('id')}: {entry.get('decision')}")
        lines.append("")

    prerequisites = document.get("prerequisites") or []
    if prerequisites:
        lines.append(f"{heading}Manual prerequisites ({len(prerequisites)})")
        for entry in prerequisites:
            lines.append(f"{bullet}[{entry.get('owner')}] {entry.get('summary')}")
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


def render_journal(journal: dict[str, Any], steps: list[Any]) -> str:
    """Where the run is: phases done, steps verified, anything stuck."""
    lines = ["Migration run"]
    lines.append(f"  target: {journal.get('target')}")
    by_status: dict[str, int] = {}
    for entry in journal.get("steps") or []:
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
    lines.append(f"  steps: {len(steps)} in the plan, "
                 + (", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
                    or "none executed"))
    phases = journal.get("phases") or {}
    for name in ("gateway", "identity", "providers", "models", "aliases", "toolServers",
                 "policies", "keys"):
        planned = [step for step in steps if getattr(step, "phase", None) == name]
        if not planned:
            continue
        # Derived from verified steps, not from the stored flag. A rehearsal used
        # to write "complete" here, and believing it skipped real work.
        verified = {entry["itemId"] for entry in journal.get("steps") or []
                    if entry.get("status") == "verified"}
        done = all(getattr(step, "item_id", None) in verified for step in planned)
        stuck = any(
            entry["status"] in {"failed", "mutationUnknown"}
            for entry in journal.get("steps") or []
            if entry["itemId"] in {getattr(s, "item_id", None) for s in planned}
        )
        state = "complete" if done else ("stopped" if stuck else "pending")
        rehearsed = " (rehearsed)" if name in (journal.get("rehearsals") or {}) else ""
        lines.append(f"    {name:12} {state:10} ({len(planned)} steps){rehearsed}")
    unverified = [e for e in journal.get("steps") or [] if e["status"] == "unverified"]
    if unverified:
        lines.append("  written but not confirmed by this tool:")
        for entry in unverified:
            lines.append(f"    {entry['itemId']} -- {entry.get('detail', '')[:100]}")
    stuck = [e for e in journal.get("steps") or []
             if e["status"] in {"failed", "mutationUnknown"}]
    if stuck:
        lines.append("  stuck:")
        for entry in stuck:
            lines.append(f"    {entry['status']}: {entry['itemId']} -- {entry.get('detail', '')[:120]}")
    if journal.get("acknowledged"):
        lines.append(f"  acknowledged: {', '.join(journal['acknowledged'])}")
    return "\n".join(lines)
