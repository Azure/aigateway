#!/usr/bin/env python3
"""Read-only evidence collection and local document utilities; no deployment commands."""

from __future__ import annotations

import argparse
import sys

from core import MigrationError, digest, read_json, validate_schema, write_new
from gateway import destination_inventory, inspect_cli
from inventory import collect_with_exports, export_digest
from model_inventory import collect_models, import_models, validate_catalog


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    cli = sub.add_parser("inspect-cli")
    cli.add_argument("--command", dest="command_list", action="append", required=True,
                     help="Selected aigateway command, e.g. 'model create'; repeat as needed.")
    cli.add_argument("--output-file", required=True)
    sub.add_parser("export-digest").add_argument("--path", required=True)
    sub.add_parser("document-digest").add_argument("--path", required=True)
    check = sub.add_parser("validate-document")
    check.add_argument("--path", required=True)
    check.add_argument("--schema", required=True, choices=(
        "source-inventory", "model-catalog", "destination-inventory",
        "migration-inventory", "migration-results"))
    models = sub.add_parser("collect-models")
    models.add_argument("--provider-id", required=True)
    models.add_argument("--kind", choices=("Foundry", "Custom"), required=True)
    models.add_argument("--endpoint", required=True)
    models.add_argument("--account-id")
    credentials = models.add_mutually_exclusive_group()
    credentials.add_argument("--credential-env")
    credentials.add_argument("--credential-resource-id")
    models.add_argument("--source-id")
    models.add_argument("--credential-field", choices=("value", "primaryKey", "secondaryKey"), default="value")
    models.add_argument("--credential-scheme", choices=("Bearer", "Basic"))
    models.add_argument("--credential-header", default="Authorization")
    models.add_argument("--approved-read", action="store_true")
    models.add_argument("--approved-credential-read", action="store_true")
    models.add_argument("--output-file", required=True)
    manual = sub.add_parser("import-models")
    manual.add_argument("--manifest-file", required=True)
    manual.add_argument("--approved-digest", required=True)
    manual.add_argument("--output-file", required=True)
    merge = sub.add_parser("merge-model-catalogs")
    merge.add_argument("--catalog-file", required=True, action="append")
    merge.add_argument("--output-file", required=True)
    source = sub.add_parser("collect-source")
    source.add_argument("--source-id", required=True)
    source.add_argument("--output-file", required=True)
    for kind in ("apiops", "arm"):
        source.add_argument("--" + kind + ("-artifact" if kind == "apiops" else "-template-file"))
        source.add_argument("--" + kind + "-approved-digest")
    destination = sub.add_parser("collect-destination")
    destination.add_argument("--destination-id", required=True)
    destination.add_argument("--group", action="append", choices=(
        "model-provider", "model", "model-alias", "mcp", "api-key",
        "telemetry-exporter", "private-endpoint-connection", "network", "policy"))
    destination.add_argument("--output-file", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "export-digest":
        print(export_digest(args.path))
    elif args.command == "document-digest":
        print(digest(read_json(args.path)))
    elif args.command == "validate-document":
        validate_schema(read_json(args.path), args.schema)
        print("Document structure is valid; review scope, references and CLI support separately.")
    elif args.command == "inspect-cli":
        write_new(args.output_file, inspect_cli(args.command_list))
    elif args.command == "collect-source":
        exports = [(kind, path, approval) for kind, path, approval in (
            ("apiops", args.apiops_artifact, args.apiops_approved_digest),
            ("arm", args.arm_template_file, args.arm_approved_digest),
        ) if path]
        result = collect_with_exports(args.source_id, exports)
        validate_schema(result, "source-inventory")
        write_new(args.output_file, result)
    elif args.command == "collect-destination":
        result = destination_inventory(args.destination_id, groups=args.group)
        validate_schema(result, "destination-inventory")
        write_new(args.output_file, result)
    elif args.command == "collect-models":
        credential_source = None
        if args.credential_resource_id:
            credential_source = {
                "sourceId": args.source_id, "resourceId": args.credential_resource_id,
                "field": args.credential_field, "scheme": args.credential_scheme,
            }
        elif args.source_id or args.credential_scheme or args.credential_field != "value":
            raise MigrationError("Control-plane credential options require --credential-resource-id.")
        result = collect_models(
            args.provider_id, args.kind, args.endpoint, args.account_id,
            args.credential_env, args.credential_header, args.approved_read,
            credential_source=credential_source, credential_read_approved=args.approved_credential_read)
        write_new(args.output_file, result)
        return 0 if all(p["error"] is None for p in result["providers"]) else 1
    elif args.command == "import-models":
        write_new(args.output_file, import_models(args.manifest_file, args.approved_digest))
    elif args.command == "merge-model-catalogs":
        providers = []
        for path in args.catalog_file:
            providers.extend(validate_catalog(read_json(path))["providers"])
        write_new(args.output_file, validate_catalog({"schemaVersion": "1.0", "providers": providers}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MigrationError, OSError, UnicodeError) as exc:
        print(str(exc) if isinstance(exc, MigrationError) else
              "Local file operation failed; inspect storage, ownership, and paths.",
              file=sys.stderr)
        sys.exit(2)
