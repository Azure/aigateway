"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import summary as summary_mod
from . import apply as apply_mod
from .arm import ArmClient, ArmError
from .collect import Collector, CollectOptions, DEFAULT_APIM_API_VERSION, GENERATOR_VERSION

_SERVICE_ID = re.compile(
    r"^/subscriptions/(?P<sub>[^/]+)/resourceGroups/(?P<rg>[^/]+)/providers/"
    r"Microsoft\.ApiManagement/service/(?P<name>[^/]+)/?$",
    re.IGNORECASE,
)

NOT_IMPLEMENTED = {
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apim-import",
        description=(
            "Inventory the AI assets (models, MCP servers, A2A agents) of an Azure API "
            "Management instance, shaped for migration to Azure AI Gateway."
        ),
    )
    parser.add_argument("--version", action="version", version=f"apim-import {GENERATOR_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Read an APIM instance and write inventory.json")
    target = collect.add_argument_group("target")
    target.add_argument("--apim", required=True, help="APIM name, or its full ARM resource id")
    target.add_argument("-g", "--resource-group", help="Resource group (required when --apim is a name)")
    target.add_argument("--subscription", help="Subscription id or name (defaults to the active one)")
    target.add_argument(
        "--api-version", default=DEFAULT_APIM_API_VERSION,
        help=f"APIM control-plane API version (default: {DEFAULT_APIM_API_VERSION})",
    )
    target.add_argument("--cognitive-api-version", help="Cognitive Services API version (default: newest stable)")

    scope = collect.add_argument_group("scope")
    scope.add_argument(
        "--workspace", action="append", default=None,
        help=(
            "Workspace to include; repeatable. 'all' (default) walks every workspace, "
            "'none' restricts the scan to the service scope"
        ),
    )
    scope.add_argument(
        "--family", action="append", choices=["models", "mcp", "a2a"], default=None,
        help="Asset family to inventory; repeatable (default: all three)",
    )
    scope.add_argument("--include-api", action="append", default=[], help="Glob of API names to force-include")
    scope.add_argument("--exclude-api", action="append", default=[], help="Glob of API names to skip")
    scope.add_argument("--max-apis", type=int, help="Stop after this many APIs (useful for a smoke run)")

    behaviour = collect.add_argument_group("behaviour")
    behaviour.add_argument(
        "--no-foundry", dest="resolve_foundry", action="store_false",
        help="Skip resolving Azure AI Foundry accounts and deployments",
    )
    behaviour.add_argument(
        "--foundry-subscription", action="append", default=[],
        help="Extra subscription to scan for Cognitive Services accounts; repeatable",
    )
    behaviour.add_argument(
        "--no-policy-xml", dest="include_policy_xml", action="store_false",
        help="Omit raw policy XML and keep only the normalized element list",
    )
    behaviour.add_argument(
        "--operation-policies", action="store_true",
        help=(
            "Also read a policy for every operation. One round trip each and no bulk read exists, "
            "so this is off by default and the skip is recorded in coverage"
        ),
    )
    behaviour.add_argument(
        "--fast", action="store_true",
        help="Skip operation enumeration for non-MCP APIs (faster, weaker model detection)",
    )

    output = collect.add_argument_group("output")
    output.add_argument("-o", "--output", default="inventory.json", help="Output path, or '-' for stdout")
    output.add_argument("--compact", action="store_true", help="Write minified JSON")
    output.add_argument("--quiet", action="store_true", help="Suppress the progress summary on stderr")

    plan_cmd = subparsers.add_parser(
        "plan", help="Propose a migration plan from an inventory, or regenerate one in place"
    )
    plan_cmd.add_argument("--inventory", required=True, help="Path to inventory.json")
    plan_cmd.add_argument(
        "-o", "--output", default="plan.json",
        help="Plan path. An existing plan at this path is read first and its adapted items preserved",
    )
    plan_cmd.add_argument(
        "--target", metavar="GATEWAY_RESOURCE_ID",
        help=(
            "The Microsoft.ApiManagement/aigateways resource this plan deploys to. Recorded on the "
            "plan, so a resumed session knows the destination; sticky once set"
        ),
    )
    plan_cmd.add_argument("--capabilities", help="Capability catalogue path (default: the bundled one)")
    plan_cmd.add_argument("--rules", help="Mapping rules path (default: the bundled one)")
    plan_cmd.add_argument(
        "--probe-cli", action="store_true",
        help="Reconcile the capability catalogue against the installed az extension",
    )
    plan_cmd.add_argument("--compact", action="store_true", help="Write minified JSON")
    plan_cmd.add_argument("--quiet", action="store_true", help="Suppress the summary on stderr")

    resolve = subparsers.add_parser(
        "resolve-models",
        help="Read a provider's live model catalogue and write it back into the inventory",
    )
    resolve.add_argument("--inventory", required=True, help="Path to inventory.json")
    resolve.add_argument(
        "-o", "--output", help="Where to write the updated inventory (default: in place)"
    )
    resolve.add_argument(
        "--allow-secret-use", action="append", default=[], metavar="PROVIDER_ID|all",
        help=(
            "Authorize using a provider's credential to read its catalogue; repeatable. "
            "Without it nothing is read and the command reports what it would do"
        ),
    )
    resolve.add_argument("--subscription", help="Subscription for the control-plane reads")

    tools_cmd = subparsers.add_parser(
        "discover-tools",
        help="Ask a passthrough MCP server which tools it exposes and record them",
    )
    tools_cmd.add_argument("--inventory", required=True, help="Path to inventory.json")
    tools_cmd.add_argument("-o", "--output", help="Where to write the updated inventory (default: in place)")
    tools_cmd.add_argument(
        "--allow-secret-use", action="append", default=[], metavar="ASSET_ID|all",
        help="Authorize calling a server; repeatable. Without it nothing is called",
    )
    tools_cmd.add_argument(
        "--route", choices=["auto", "gateway", "upstream"], default="auto",
        help=(
            "auto (default) prefers the gateway, which is what callers see, and falls back to the "
            "upstream; upstream bypasses APIM policies and can list more tools than the gateway exposes"
        ),
    )
    tools_cmd.add_argument("--subscription", help="Subscription for the control-plane reads")

    apply_cmd = subparsers.add_parser(
        "apply", help="Provision a settled plan into the target gateway, one phase at a time"
    )
    apply_cmd.add_argument("--plan", required=True, help="Path to plan.json")
    apply_cmd.add_argument("--inventory", required=True, help="Path to inventory.json")
    apply_cmd.add_argument("--journal", default="journal.json", help="Execution state (default: journal.json)")
    apply_cmd.add_argument("--preflight", action="store_true", help="Run the checks and stop")
    apply_cmd.add_argument("--status", action="store_true", help="Report where the run is and stop")
    apply_cmd.add_argument("--phase", help=f"Run one phase ({', '.join(apply_mod.PHASES)})")
    apply_cmd.add_argument("--next-phase", action="store_true", help="Run the next incomplete phase")
    apply_cmd.add_argument(
        "--execute", action="store_true",
        help="Actually write. Without it the run is a rehearsal that prints the commands",
    )
    apply_cmd.add_argument(
        "--skip-rehearsal", action="store_true",
        help="Execute a phase that has not been rehearsed (refused by default)",
    )
    apply_cmd.add_argument(
        "--acknowledge", action="append", default=[], metavar="PREREQ_ID",
        help="Record that a manual prerequisite is done; repeatable",
    )
    apply_cmd.add_argument("--subscription", help="Subscription for credential reads")

    validate = subparsers.add_parser("validate", help="Check an artifact against its JSON Schema")
    validate.add_argument("file", help="Path to inventory.json")

    summarize = subparsers.add_parser("summary", help="Print a readable summary of an inventory")
    summarize.add_argument("file", help="Path to inventory.json")
    summarize.add_argument("--format", choices=["text", "markdown"], default="text")

    for name, description in NOT_IMPLEMENTED.items():
        stub = subparsers.add_parser(name, help=f"(planned) {description.split('.')[0]}")
        stub.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in NOT_IMPLEMENTED:
        print(
            f"'{args.command}' is not implemented yet.\n\n{NOT_IMPLEMENTED[args.command]}\n\n"
            "See tools/apim-import/README.md for the contract this command will honour.",
            file=sys.stderr,
        )
        return 2
    if args.command == "collect":
        return _collect(args)
    if args.command == "plan":
        return _plan(args)
    if args.command == "resolve-models":
        return _resolve_models(args)
    if args.command == "discover-tools":
        return _discover_tools(args)
    if args.command == "apply":
        return _apply(args)
    if args.command == "validate":
        return _validate(args)
    if args.command == "summary":
        return _summary(args)
    parser.error(f"unknown command {args.command}")
    return 2


# ----------------------------------------------------------------- commands


def _collect(args: argparse.Namespace) -> int:
    try:
        service_id, subscription = _resolve_service_id(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    options = CollectOptions(
        workspaces=args.workspace or ["all"],
        include_api=args.include_api,
        exclude_api=args.exclude_api,
        families=set(args.family or ["models", "mcp", "a2a"]),
        resolve_foundry=args.resolve_foundry,
        foundry_subscriptions=args.foundry_subscription,
        apim_api_version=args.api_version,
        cognitive_api_version=args.cognitive_api_version,
        include_policy_xml=args.include_policy_xml,
        operation_policies=args.operation_policies,
        fast=args.fast,
        max_apis=args.max_apis,
    )
    client = ArmClient(subscription=subscription)

    def progress(message: str) -> None:
        if not args.quiet:
            print(f"  ... {message}", file=sys.stderr, flush=True)

    collector = Collector(client, service_id, options, progress=progress)
    try:
        document = collector.run()
    except ArmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(document, indent=None if args.compact else 2, ensure_ascii=False)
    if args.output == "-":
        print(payload)
    else:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    if not args.quiet:
        print(summary_mod.render(document, fmt="text"), file=sys.stderr)
        if args.output != "-":
            print(f"\nWrote {args.output} ({len(payload):,} bytes)", file=sys.stderr)
    return 0


def _plan(args: argparse.Namespace) -> int:
    from .capability import CapabilityError, CapabilityMap
    from .plan import build_plan

    try:
        inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if inventory.get("kind") != "apimAiInventory":
        print("error: --inventory is not an apimAiInventory document", file=sys.stderr)
        return 2

    try:
        capabilities = CapabilityMap.load(
            catalog_path=Path(args.capabilities) if args.capabilities else None,
            rules_path=Path(args.rules) if args.rules else None,
        )
    except CapabilityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.probe_cli:
        try:
            capabilities.probe()
        except CapabilityError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    # An existing plan at the output path is the previous generation: its adapted
    # items are preserved rather than overwritten.
    previous = None
    output = Path(args.output)
    if args.output != "-" and output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: existing plan at {args.output} is not valid JSON: {exc}", file=sys.stderr)
            return 1

    document = build_plan(inventory, capabilities, previous=previous, target=args.target)
    orphans = document.get("orphanedDecisions") or []
    payload = json.dumps(document, indent=None if args.compact else 2, ensure_ascii=False)
    if args.output == "-":
        print(payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    if not args.quiet:
        print(summary_mod.render_plan(document), file=sys.stderr)
        if orphans:
            print(
                f"\n{len(orphans)} settled decision(s) no longer have an item to attach to:",
                file=sys.stderr,
            )
            for entry in orphans:
                print(f"  {entry['id']} = {json.dumps(entry['decision'])[:60]}", file=sys.stderr)
            print("  Re-apply them to the items that replaced them, or confirm they are not needed.",
                  file=sys.stderr)
        if args.output != "-":
            print(f"\nWrote {args.output} ({len(payload):,} bytes)", file=sys.stderr)
    return 0


def _resolve_models(args: argparse.Namespace) -> int:
    from .resolve import resolve_models, resolvable

    path = Path(args.inventory)
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if inventory.get("kind") != "apimAiInventory":
        print("error: --inventory is not an apimAiInventory document", file=sys.stderr)
        return 2

    candidates = resolvable(inventory)
    if not candidates:
        print("No provider has an unresolved catalogue reachable over its endpoint.", file=sys.stderr)
        return 0

    allow = {value for value in args.allow_secret_use}
    client = ArmClient(subscription=args.subscription) if allow else None
    results = resolve_models(inventory, client=client, allow=allow)

    for result in results:
        print(f"  {result.status:18} {result.provider_id} -> {result.catalogue_url}", file=sys.stderr)
        if result.models:
            print(f"                     {', '.join(result.models[:8])}"
                  + (" ..." if len(result.models) > 8 else ""), file=sys.stderr)
        elif result.detail:
            print(f"                     {result.detail}", file=sys.stderr)

    if not allow:
        print(
            "\nNothing was read. Reading a catalogue uses the provider's credential, so it needs "
            "explicit authorization:\n  --allow-secret-use <providerId>   (or 'all')",
            file=sys.stderr,
        )
        return 0

    resolved = [result for result in results if result.status == "resolved"]
    if resolved:
        output = Path(args.output) if args.output else path
        output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nUpdated {output} ({len(resolved)} provider(s) resolved)", file=sys.stderr)
    return 0 if all(r.status in {"resolved", "needsAuthorization"} for r in results) else 1


def _discover_tools(args: argparse.Namespace) -> int:
    from .mcp import discover_tools, discoverable

    path = Path(args.inventory)
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if inventory.get("kind") != "apimAiInventory":
        print("error: --inventory is not an apimAiInventory document", file=sys.stderr)
        return 2
    if not discoverable(inventory):
        print("No MCP server has a runtime-only tool list.", file=sys.stderr)
        return 0

    allow = {value for value in args.allow_secret_use}
    client = ArmClient(subscription=args.subscription) if allow else None
    results = discover_tools(inventory, client=client, allow=allow, route=args.route)

    for result in results:
        print(f"  {result.status:18} {result.asset_id} via {result.route}", file=sys.stderr)
        if result.tools:
            print(f"                     {', '.join(t['name'] for t in result.tools[:10])}"
                  + (" ..." if len(result.tools) > 10 else ""), file=sys.stderr)
        if result.detail:
            print(f"                     {result.detail}", file=sys.stderr)

    if not allow:
        print(
            "\nNothing was called. Listing tools calls the server and may use a subscription key, "
            "so it needs explicit authorization:\n  --allow-secret-use <assetId>   (or 'all')",
            file=sys.stderr,
        )
        return 0

    found = [result for result in results if result.status == "discovered"]
    if found:
        output = Path(args.output) if args.output else path
        output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nUpdated {output} ({len(found)} server(s) discovered)", file=sys.stderr)
    return 0 if all(r.status in {"discovered", "needsAuthorization"} for r in results) else 1


def _apply(args: argparse.Namespace) -> int:
    from .apply import ApplyError, Executor, new_journal, preflight, steps_for

    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if plan.get("kind") != "apimMigrationPlan":
        print("error: --plan is not an apimMigrationPlan document", file=sys.stderr)
        return 2

    journal_path = Path(args.journal)
    journal = (
        json.loads(journal_path.read_text(encoding="utf-8"))
        if journal_path.exists() else new_journal(plan)
    )
    journal["_path"] = str(journal_path)
    for entry in args.acknowledge:
        if entry not in journal["acknowledged"]:
            journal["acknowledged"].append(entry)

    from .apply import _run as _az

    findings = preflight(plan, inventory, runner=_az)
    outstanding = [
        f for f in findings
        if f["blocking"] or f["code"] not in {"prerequisites"}
        or not all(p["id"] in journal["acknowledged"] for p in plan.get("prerequisites") or [])
    ]
    if args.preflight or outstanding:
        print("Preflight:", file=sys.stderr)
        for finding in findings or [{"code": "ok", "blocking": False,
                                     "message": "nothing outstanding", "remedy": ""}]:
            mark = "BLOCK" if finding["blocking"] else " note"
            print(f"  [{mark}] {finding['code']}: {finding['message']}", file=sys.stderr)
            if finding.get("remedy"):
                print(f"          {finding['remedy']}", file=sys.stderr)
    blocking = [f for f in findings if f["blocking"]]
    if args.preflight:
        _write_journal(journal, journal_path)
        return 1 if blocking else 0
    if blocking:
        print("\nRefusing to apply while a blocking finding stands.", file=sys.stderr)
        return 1

    try:
        executor = Executor(
            plan, inventory, journal,
            arm_client=ArmClient(subscription=args.subscription) if args.execute else None,
            execute=args.execute,
            skip_rehearsal=args.skip_rehearsal,
        )
    except ApplyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.status:
        print(summary_mod.render_journal(journal, steps_for(plan)), file=sys.stderr)
        return 0

    phase = args.phase or (executor.next_phase() if args.next_phase else None)
    if not phase:
        print(summary_mod.render_journal(journal, steps_for(plan)), file=sys.stderr)
        if not args.phase and not args.next_phase:
            print("\nPass --next-phase to run the next one, or --phase <name>.", file=sys.stderr)
        return 0

    mode = "EXECUTING" if args.execute else "rehearsal (pass --execute to write)"
    print(f"Phase {phase} -- {mode}", file=sys.stderr)
    try:
        steps = executor.run_phase(phase)
    except ApplyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        _write_journal(journal, journal_path)
        return 1
    for step in steps:
        print(f"  {step.status:16} {step.item_id}", file=sys.stderr)
        if step.detail:
            print(f"                   {step.detail}", file=sys.stderr)
        if not args.execute:
            # Every command, because this is the gate the phase is approved from.
            for argv in step.commands or ([step.argv] if step.argv else []):
                print(f"                   $ {' '.join(argv)}", file=sys.stderr)
    _write_journal(journal, journal_path)

    stuck = [s for s in steps if s.status in {"failed", "mutationUnknown"}]
    if stuck:
        print(f"\nStopped in {phase}. The source APIM is untouched; the gateway is partially built.",
              file=sys.stderr)
        return 1
    if not args.execute:
        # A rehearsal changed nothing, so saying "complete" would overstate it.
        print(f"\nRehearsed {phase}. Nothing was written. Run the same phase with --execute "
              "to apply it.", file=sys.stderr)
        return 0
    remaining = executor.next_phase()
    print(f"\nPhase {phase} complete."
          + (f" Next: {remaining}." if remaining else " No phases remain."), file=sys.stderr)
    return 0


def _write_journal(journal: dict, path: Path) -> None:
    payload = {k: v for k, v in journal.items() if not k.startswith("_")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    errors = validate_document(document)
    if errors:
        for error in errors:
            print(f"invalid: {error}", file=sys.stderr)
        return 1
    print(f"{path} is a valid {document.get('kind')} document")
    return 0


def _summary(args: argparse.Namespace) -> int:
    try:
        document = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(summary_mod.render(document, fmt=args.format))
    return 0


# ------------------------------------------------------------------ helpers


def _resolve_service_id(args: argparse.Namespace) -> tuple[str, str | None]:
    value = (args.apim or "").strip().rstrip("/")
    if value.startswith("/subscriptions/"):
        match = _SERVICE_ID.match(value)
        if not match:
            raise ValueError(
                "--apim looks like a resource id but is not a Microsoft.ApiManagement/service id. "
                "The AI Gateway resource type (Microsoft.ApiManagement/aigateways) is the migration "
                "target, not a source."
            )
        return value, args.subscription or match.group("sub")
    if not args.resource_group:
        raise ValueError("--resource-group is required when --apim is a name rather than a resource id")
    subscription = args.subscription or _active_subscription()
    if not subscription:
        raise ValueError("could not determine the subscription; pass --subscription")
    return (
        f"/subscriptions/{subscription}/resourceGroups/{args.resource_group}"
        f"/providers/Microsoft.ApiManagement/service/{value}"
    ), subscription


def _active_subscription() -> str | None:
    try:
        proc = subprocess.run(
            ["az", "account", "show", "--query", "id", "--output", "tsv", "--only-show-errors"],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


_SCHEMA_FOR_KIND = {
    "apimAiInventory": "inventory.schema.json",
    "apimMigrationPlan": "plan.schema.json",
    "apimMigrationJournal": "journal.schema.json",
}


def validate_document(document: Any) -> list[str]:
    """Validate an artifact against the schema for its own `kind`."""
    kind = document.get("kind") if isinstance(document, dict) else None
    if kind not in _SCHEMA_FOR_KIND:
        return [f"<root>: unknown artifact kind {kind!r}; expected one of {sorted(_SCHEMA_FOR_KIND)}"]
    return _validate_against(document, _SCHEMA_FOR_KIND[kind])


def validate_inventory(document: Any) -> list[str]:
    """Validate against the bundled schema, or structurally when jsonschema is absent."""
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "inventory.schema.json"
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_errors(document)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover
        return [f"schema unavailable: {exc}"]
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda err: list(err.path))
    ][:50]


def _validate_against(document: Any, schema_name: str) -> list[str]:
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / schema_name
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_errors(document) if schema_name == "inventory.schema.json" else []
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover
        return [f"schema unavailable: {exc}"]
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda err: list(err.path))
    ][:50]


def _structural_errors(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["<root>: expected an object"]
    for key in ("schemaVersion", "kind", "generator", "collection", "service", "assets", "secrets", "policies"):
        if key not in document:
            errors.append(f"<root>: missing required property '{key}'")
    if document.get("kind") != "apimAiInventory":
        errors.append("kind: expected 'apimAiInventory'")
    assets = document.get("assets")
    if isinstance(assets, dict):
        for family in ("models", "mcpServers", "agents"):
            if not isinstance(assets.get(family), list):
                errors.append(f"assets/{family}: expected an array")
    else:
        errors.append("assets: expected an object")
    for index, secret in enumerate(document.get("secrets") or []):
        if not isinstance(secret, dict):
            errors.append(f"secrets/{index}: expected an object")
            continue
        for key in ("id", "class", "storage", "retrievable"):
            if key not in secret:
                errors.append(f"secrets/{index}: missing required property '{key}'")
    return errors


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
