#!/usr/bin/env python3
"""Portable entry point. No collect or validate subcommand performs Azure writes."""

from __future__ import annotations

import argparse
import json
import sys

from core import MigrationError, State, digest, now, read_json, semantic, validate_schema, write_new
from execution import (
    approve, execute, initialize, invalidate, record_behavior, refresh, report, validated,
    verify_final_resources,
)
from gateway import capabilities, destination_inventory, inspect_cli
from inventory import collect_with_exports, export_digest
from planning import render_plan, validate_plan
from model_inventory import collect_models, import_models, validate_catalog
from selection import compile_selection
from native_sync import collect_preview


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("inspect-cli", "capabilities"):
        sub.add_parser(name).add_argument("--output-file", required=True)
    evidence = sub.add_parser("export-digest")
    evidence.add_argument("--path", required=True)
    model_digest = sub.add_parser("model-catalog-digest")
    model_digest.add_argument("--path", required=True)
    model_digest.add_argument("--selection", action="store_true")
    sub.add_parser("translation-digest").add_argument("--path", required=True)
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
    preview = sub.add_parser("collect-sync-preview")
    preview.add_argument("--model-catalog-file", required=True)
    preview.add_argument("--destination-file", required=True)
    preview.add_argument("--provider-id", required=True)
    preview.add_argument("--provider-name", required=True)
    preview.add_argument("--approved-read", action="store_true")
    preview.add_argument("--output-file", required=True)
    source = sub.add_parser("collect-source")
    source.add_argument("--source-id", required=True)
    source.add_argument("--output-file", required=True)
    export_options(source)
    destination = sub.add_parser("collect-destination")
    destination.add_argument("--destination-id", required=True)
    destination.add_argument("--output-file", required=True)
    init = sub.add_parser("init")
    init.add_argument("--state-dir", required=True)
    init.add_argument("--model-catalog-file")
    for name in ("source", "destination", "capabilities"):
        init.add_argument("--" + name + "-file", required=True)
    for name in ("check-state", "validate-plan", "compile-plan", "approve", "execute", "record-verification",
                 "accept-residual", "report", "cancel"):
        command = sub.add_parser(name)
        command.add_argument("--state-dir", required=True)
        if name in ("execute", "report"):
            export_options(command)
            command.add_argument("--approved-credential-read", action="store_true")
        if name == "validate-plan":
            command.add_argument("--mapping-file")
            command.add_argument("--todos-file")
        if name == "compile-plan":
            command.add_argument("--selection-file", required=True)
            command.add_argument("--sync-preview-file", action="append")
            for artifact in ("source", "model-catalog", "destination", "capabilities"):
                command.add_argument("--" + artifact + "-file")
        if name in ("approve", "execute"):
            command.add_argument("--todo-id", required=True)
        if name in ("approve", "execute", "record-verification", "accept-residual"):
            command.add_argument("--plan-digest", required=True)
        if name == "record-verification":
            owner = command.add_mutually_exclusive_group(required=True)
            owner.add_argument("--todo-id")
            owner.add_argument("--mapping-id")
            command.add_argument("--behavior-id", required=True)
            command.add_argument("--method", required=True,
                                 choices=("control-plane", "data-plane", "administrator-attestation"))
            command.add_argument("--evidence-digest", required=True)
            command.add_argument("--status", choices=("passed", "failed", "inconclusive"),
                                 default="passed")
        if name == "accept-residual":
            command.add_argument("--mapping-id", required=True)
    return root


def export_options(command):
    command.add_argument("--apiops-artifact")
    command.add_argument("--apiops-approved-digest")
    command.add_argument("--arm-template-file")
    command.add_argument("--arm-approved-digest")


def exports(args):
    return [(kind, path, approval) for kind, path, approval in (
        ("apiops", args.apiops_artifact, args.apiops_approved_digest),
        ("arm", args.arm_template_file, args.arm_approved_digest),
    ) if path]


def main(argv=None):
    args = parser().parse_args(argv)
    command = args.command
    if command == "export-digest":
        print(export_digest(args.path))
        return 0
    if command == "translation-digest":
        entry = read_json(args.path)
        fields = ("sourceIds", "behaviorIds", "settings", "scopeDecision")
        if not isinstance(entry, dict) or any(field not in entry for field in fields):
            raise MigrationError("Translation intent requires source/behavior IDs, settings and a scope decision.")
        print(digest({field: entry[field] for field in fields}))
        return 0
    if command == "model-catalog-digest":
        document = read_json(args.path)
        print(digest(semantic(document) if args.selection else document))
        return 0
    if command == "collect-models":
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
    if command == "import-models":
        write_new(args.output_file, import_models(args.manifest_file, args.approved_digest))
        return 0
    if command == "merge-model-catalogs":
        providers = []
        for path in args.catalog_file:
            providers.extend(validate_catalog(read_json(path))["providers"])
        write_new(args.output_file, validate_catalog({"schemaVersion": "1.0", "providers": providers}))
        return 0
    if command == "collect-sync-preview":
        result = collect_preview(read_json(args.model_catalog_file), read_json(args.destination_file),
                                 args.provider_id, args.provider_name, args.approved_read)
        write_new(args.output_file, result)
        if result["status"] == "blocked":
            print(result["error"], file=sys.stderr)
            return 1
        return 0
    if command in ("inspect-cli", "capabilities"):
        result = inspect_cli()
        if command == "capabilities":
            result = capabilities(result)
        write_new(args.output_file, result)
        return 0
    if command == "collect-source":
        result = collect_with_exports(args.source_id, exports(args))
        validate_schema(result, "source-inventory")
        write_new(args.output_file, result)
        return 0
    if command == "collect-destination":
        result = destination_inventory(args.destination_id)
        validate_schema(result, "destination-inventory")
        write_new(args.output_file, result)
        return 0
    state = State(args.state_dir)
    if command == "init":
        bundle = initialize(read_json(args.source_file), read_json(args.destination_file),
                            read_json(args.capabilities_file),
                            read_json(args.model_catalog_file) if args.model_catalog_file else None)
        with state.locked(create=True):
            state.save(bundle)
        print(json.dumps({"status": "initialized", "generationId": bundle["context.json"]["generationId"]}))
        return 0
    with state.locked():
        bundle = state.load()
        if command == "check-state":
            result = validate_plan(bundle)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "valid" else 1
        if command == "compile-plan":
            inputs = dict(bundle)
            inputs["mapping.json"] = {**bundle["mapping.json"], "nativeSyncPreviews": [
                read_json(path) for path in args.sync_preview_file or []]}
            for option, artifact, schema in (
                    ("source", "source-inventory.json", "source-inventory"),
                    ("model_catalog", "model-catalog.json", "model-catalog"),
                    ("destination", "destination-inventory.json", "destination-inventory"),
                    ("capabilities", "capability-contract.json", "capability-contract")):
                path = getattr(args, option + "_file")
                if path:
                    inputs[artifact] = read_json(path)
                    validate_schema(inputs[artifact], schema)
            candidate = compile_selection(inputs, read_json(args.selection_file))
            result = validate_plan(candidate)
            print(json.dumps(result, indent=2))
            if result["status"] != "valid":
                return 1
            bundle = candidate
            bundle["plan-validation.json"] = result
            bundle["migration-plan.md"] = render_plan(bundle, result)
            invalidate(bundle, "Explicit selection compiled; fresh per-item approvals are required.")
        elif command == "validate-plan":
            if args.mapping_file:
                bundle["mapping.json"] = read_json(args.mapping_file)
            if args.todos_file:
                bundle["todos.json"] = read_json(args.todos_file)
            result = validate_plan(bundle)
            print(json.dumps(result, indent=2))
            if result["status"] != "valid":
                return 1
            bundle["plan-validation.json"] = result
            bundle["migration-plan.md"] = render_plan(bundle, result)
            invalidate(bundle, "Plan updated; fresh approvals are required.")
        elif command == "approve":
            approve(bundle, args.todo_id, args.plan_digest)
        elif command == "execute":
            execute(bundle, args.todo_id, args.plan_digest, state.save, exports=exports(args),
                    credential_read_approved=args.approved_credential_read)
            return 0
        elif command == "record-verification":
            record_behavior(bundle, args.mapping_id or args.todo_id, args.behavior_id, args.method,
                            args.evidence_digest, args.plan_digest, args.status)
        elif command == "accept-residual":
            result = validated(bundle)
            if result["planDigest"] != args.plan_digest:
                raise MigrationError("Residual acceptance requires the displayed current digest.")
            matches = [item for item in bundle["mapping.json"]["items"]
                       if item["id"] == args.mapping_id and item["classification"] == "cannot-import"]
            if len(matches) != 1:
                raise MigrationError("Expected one explicit unsupported-behavior residual.")
            matches[0]["residual"].update(acceptance="accepted",
                                         approvedPlanDigest=args.plan_digest, decidedAt=now())
        elif command == "report":
            try:
                snapshot = refresh(bundle, exports=exports(args),
                                   credential_read_approved=args.approved_credential_read)
                if digest(semantic(snapshot)) != digest(semantic(bundle["destination-inventory.json"])):
                    raise MigrationError("Destination drift blocks completion.")
                verify_final_resources(bundle, snapshot)
            except MigrationError:
                invalidate(bundle, "Fresh evidence is unavailable or changed.")
                state.save(bundle)
                raise
            report(bundle, fresh=True)
        elif command == "cancel":
            invalidate(bundle, "Cancelled; new approval is required to resume.")
            bundle["context.json"]["completionStatus"] = "cancelled"
            report(bundle)
        state.save(bundle)
        print(json.dumps({"status": bundle["context.json"]["completionStatus"],
                          "generationId": bundle["context.json"]["generationId"]}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MigrationError, OSError, UnicodeError) as exc:
        # OS exceptions can include sensitive absolute paths; keep them out of reports.
        print(str(exc) if isinstance(exc, MigrationError) else
              "Local file operation failed; inspect storage, ownership, and paths.",
              file=sys.stderr)
        sys.exit(2)
