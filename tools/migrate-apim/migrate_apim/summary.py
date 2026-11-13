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

    # Separated, because "ready to execute" is a promise about what `apply` will
    # do. An item this tool has no builder for is ready in every other sense and
    # will still be sitting there, unapplied, when the last phase reports done.
    # Settled items count here whether they arrived ready or were adapted into it.
    by_hand = [item for item in document.get("items") or [] if item.get("appliedByHand")]
    ready = [item for item in document.get("items") or []
             if item.get("status") == "ready" and not item.get("appliedByHand")]
    lines.append(f"{heading}Ready to execute ({len(ready)})")
    for item in ready[:12]:
        lines.append(
            f"{'  - ' if fmt == 'markdown' else '    '}{item.get('capabilityId')}: "
            f"{_item_source(item)}"
        )
    if len(ready) > 12:
        lines.append(f"{'  - ' if fmt == 'markdown' else '    '}... and {len(ready) - 12} more")
    lines.append("")

    if by_hand:
        lines.append(f"{heading}Applied by hand ({len(by_hand)})")
        lines.append(
            f"{bullet}The gateway and the installed CLI support these; `apply` has no builder for "
            "them, so it will run no step and report the phase as `by hand`."
        )
        for item in by_hand:
            command = (item.get("appliedByHand") or {}).get("command") or "no command recorded"
            lines.append(
                f"{'  - ' if fmt == 'markdown' else '    '}{item.get('capabilityId')}: "
                f"{_item_source(item)} -> {command}"
            )
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


def _item_source(item: dict[str, Any]) -> str:
    """What this item is about, in one phrase.

    A policy or an identity item has no asset id -- printing the `None` it holds
    said less than the kind of thing it is.
    """
    source = item.get("source") or {}
    return f"{source.get('assetId') or source.get('assetKind')} [{source.get('aspect')}]"


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


def phases_remaining(journal: dict[str, Any], steps: list[Any]) -> list[str]:
    """Phases with steps still to run -- the question `--next-phase` asks.

    Written-but-unconfirmed counts as run, matching `Executor.phase_complete`:
    the tool will not hand that phase back, so calling it remaining would name
    work nobody can do.
    """
    from .apply import PHASES

    done_ids = {e["itemId"] for e in journal.get("steps") or []
                if e.get("status") in {"verified", "unverified"}}
    out = []
    for name in PHASES:
        ids = {getattr(step, "item_id", None) for step in steps
               if getattr(step, "phase", None) == name}
        if ids and not ids <= done_ids:
            out.append(name)
    return out


def render_verify(journal: dict[str, Any], plan: dict[str, Any] | None = None) -> list[str]:
    """What to do when the phases are done: go and look at it.

    Every check this tool makes is a management read-back, so the end of a run
    is the point where somebody has to open the gateway and see it. Printed
    with the link already built, because the one thing an operator will not do
    is assemble a URL out of a resource id by hand.

    "No phases remain" is not "everything in the plan happened". A phase whose
    content has no builder here has no steps, so the run passes over it and
    ends -- with that work never applied by anyone. It is named here, above the
    link, or the closing lines of a run read as a migration that finished.
    """
    from .apply import unperformable_for
    from .ids import PORTAL, portal_url

    lines: list[str] = []
    manual = unperformable_for(plan) if plan else []
    if manual:
        by_phase: dict[str, int] = {}
        for entry in manual:
            by_phase[entry["phase"]] = by_phase.get(entry["phase"], 0) + 1
        where = ", ".join(f"{phase} ({count})" for phase, count in by_phase.items())
        lines += [
            f"{len(manual)} item(s) in this plan have no builder here and were not applied: "
            f"{where}.",
            "They are absent from the gateway until someone configures them by hand.",
            "",
        ]
    url = portal_url(journal.get("target"))
    return lines + [
        "These objects exist. Whether the gateway serves traffic is a separate question:",
        "every check above is a management read-back, not a call through the gateway.",
        "Open it and see what the run provisioned:",
        f"  {url}" if url else f"  {PORTAL}   (then select the gateway in the top bar)",
    ]


def render_phases(
    journal: dict[str, Any],
    steps: list[Any],
    *,
    plan: dict[str, Any] | None = None,
    current: str | None = None,
    indent: str = "",
) -> list[str]:
    """The phase checklist: what is done, what is left, where the run is.

    Every `apply` run prints this, not just `--status`, so the list exists in
    the transcript whether or not whoever is driving the tool keeps one. It is
    derived from the journal on each call, so it cannot drift from the run the
    way a hand-kept list does.

    "Done" matches `Executor.phase_complete` -- written-but-unconfirmed counts,
    because `--next-phase` will not return that phase again. Saying `pending`
    for a phase the tool refuses to re-run would point the reader at work they
    cannot do. The unconfirmed part is marked rather than hidden.

    Pass `plan` to count the work this tool has no builder for. Without it a
    phase of nothing but manual items reads as absent from the migration, when
    in fact it is the part nobody will run.
    """
    from .apply import PHASES, unperformable_for

    by_hand: dict[str, int] = {}
    for entry in unperformable_for(plan) if plan else []:
        by_hand[entry["phase"]] = by_hand.get(entry["phase"], 0) + 1

    entries = journal.get("steps") or []
    remaining = set(phases_remaining(journal, steps))
    unconfirmed_ids = {e["itemId"] for e in entries if e.get("status") == "unverified"}
    stuck_ids = {e["itemId"] for e in entries
                 if e.get("status") in {"failed", "mutationUnknown"}}

    lines: list[str] = []
    for name in PHASES:
        planned = [step for step in steps if getattr(step, "phase", None) == name]
        manual = by_hand.get(name, 0)
        mark = "> " if name == current else "  "
        count = f"({len(planned)} steps" + (f", {manual} by hand)" if manual else ")")
        if not planned:
            # A phase with nothing planned is not part of this migration, so it
            # stays off the list -- unless it holds manual work, or is the one
            # being run, where its emptiness is the outcome and "complete" would
            # misread as work done.
            if manual:
                lines.append(f"{indent}{mark}{name:12} {'by hand':10} {count}")
            elif name == current:
                lines.append(f"{indent}{mark}{name:12} {'no steps':10} {count}")
            continue
        ids = {getattr(step, "item_id", None) for step in planned}
        done = name not in remaining
        state = "complete" if done else ("stopped" if ids & stuck_ids else "pending")
        if done and ids & unconfirmed_ids:
            suffix = " (unconfirmed)"
        elif not done and name in (journal.get("rehearsals") or {}):
            suffix = " (rehearsed)"
        else:
            suffix = ""
        lines.append(f"{indent}{mark}{name:12} {state:10} {count}{suffix}")
    return lines


def render_journal(journal: dict[str, Any], steps: list[Any],
                   plan: dict[str, Any] | None = None) -> str:
    """Where the run is: phases done, steps verified, anything stuck."""
    lines = ["Migration run"]
    lines.append(f"  target: {journal.get('target')}")
    by_status: dict[str, int] = {}
    for entry in journal.get("steps") or []:
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
    lines.append(f"  steps: {len(steps)} in the plan, "
                 + (", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
                    or "none executed"))
    lines.extend(render_phases(journal, steps, plan=plan, indent="  "))
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
    if journal.get("steps") and not phases_remaining(journal, steps):
        lines.append("")
        lines.extend(render_verify(journal, plan))
    return "\n".join(lines)
