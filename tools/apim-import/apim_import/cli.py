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
from .arm import ArmClient, ArmError
from .collect import Collector, CollectOptions, DEFAULT_APIM_API_VERSION, GENERATOR_VERSION

_SERVICE_ID = re.compile(
    r"^/subscriptions/(?P<sub>[^/]+)/resourceGroups/(?P<rg>[^/]+)/providers/"
    r"Microsoft\.ApiManagement/service/(?P<name>[^/]+)/?$",
    re.IGNORECASE,
)

NOT_IMPLEMENTED = {
    "resolve-models": (
        "Fetches the live model catalogue for non-Azure providers (OpenAI /v1/models, "
        "Anthropic /v1/models, and so on) by resolving the backend credential in memory."
    ),
    "assess": (
        "Maps the inventory onto AI Gateway building blocks using a versioned capability "
        "map, and emits assessment.json with per-asset verdicts, gaps, and questions."
    ),
    "plan": (
        "Combines inventory.json, assessment.json, and decisions.json into an ordered, "
        "idempotent migration plan with just-in-time secret resolution."
    ),
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
        "--fast", action="store_true",
        help="Skip operation enumeration for non-MCP APIs (faster, weaker model detection)",
    )

    output = collect.add_argument_group("output")
    output.add_argument("-o", "--output", default="inventory.json", help="Output path, or '-' for stdout")
    output.add_argument("--compact", action="store_true", help="Write minified JSON")
    output.add_argument("--quiet", action="store_true", help="Suppress the progress summary on stderr")

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
        fast=args.fast,
        max_apis=args.max_apis,
    )
    client = ArmClient(subscription=subscription)
    collector = Collector(client, service_id, options)
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


def _validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    errors = validate_inventory(document)
    if errors:
        for error in errors:
            print(f"invalid: {error}", file=sys.stderr)
        return 1
    print(f"{path} is a valid apimAiInventory document")
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
