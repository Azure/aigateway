"""Materialize pinned-schema Waza tasks; never run a model or Azure command."""

import argparse
import json
from pathlib import Path

import yaml

from grade import ROOT, cases

OUTPUT_CONTRACT = """
This is a synthetic offline planning scenario. Read evidence.json and the shared
output-contract.json vocabulary; use the named
existing skill, but do not execute commands, make network calls, install tools,
retrieve credentials, or modify cloud/local application state. Commands in your
answer are proposals only, not execution authorization.
Return exactly one JSON object (no Markdown) with:
scenario (the scenario ID), decision (read-only/integrate/needs-approval/blocked/
reconcile/assess-only), selected (specific selected identifiers and contract),
gates (specific safety gate names in kebab-case), observations (what the evidence
does and does not establish), commands (proposed native CLI strings, or []),
executed: false, limitations (include "final-output-not-execution-proof").
Use the supplied typed output shape: keep booleans, numbers, lists and categorical
states as those types, not explanatory strings or nested reports. Put optional
explanations in a separate notes field. Values come from evidence; unknown and
unavailable describe missing or denied evidence. Decision names describe the
requested phase, not successful execution. Name required gates precisely;
additional relevant identifiers from the shared vocabulary are allowed.
The contract vocabulary is universal, not a scenario answer or a list of gates
that all apply. Select only the gate identifiers relevant to this scenario.
Do not claim live validation, a quality grade, or that plans prove safe execution.
"""


def value_shape(value):
    if isinstance(value, dict):
        return {key: value_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [value_shape(value[0])] if value else []
    return {str: "string", bool: "boolean", int: "integer", float: "number",
            type(None): "null"}[type(value)]


def documents(mode="smoke", model="offline-mock", trials=1):
    quality = mode == "quality"
    metric = "contract_assertions" if quality else "harness_smoke"
    skills = ["manage-ai-gateway", "use-ai-gateway",
              "migrate-ai-gateway", "feedback-ai-gateway"]
    skill_prefix = "../../../skills" if quality else "../../skills"
    scenario_cases = cases()
    states = set()
    for case in scenario_cases:
        evidence = json.dumps(case["evidence"])
        pending = list(case["expected"]["observations"].values())
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str) and "/" not in value and value not in evidence:
                states.add(value)
    contract = {
        "description": "Universal output vocabulary. No scenario-to-answer mappings or required gate subsets.",
        "topLevelFields": {"scenario": "string", "decision": "string", "selected": "object",
                           "gates": "array of applicable unique gate identifiers",
                           "observations": "object", "commands": "array of proposed command strings",
                           "executed": "boolean", "limitations": "array of strings"},
        "decisionIdentifiers": ["read-only", "integrate", "needs-approval", "blocked", "reconcile", "assess-only"],
        "selectedFieldIdentifiers": sorted({key for c in scenario_cases for key in c["expected"]["selected"]}),
        "observationFieldIdentifiers": sorted({key for c in scenario_cases for key in c["expected"]["observations"]}),
        "gateIdentifiers": sorted({gate for c in scenario_cases for gate in c["expected"]["gates"]}),
        "stateIdentifiers": sorted(states),
        "limitationIdentifiers": ["final-output-not-execution-proof"],
        "stateMeaning": "unknown: not established; unavailable: denied/missing evidence. Values are not assigned to any scenario here.",
    }
    tasks = {}
    for case in scenario_cases:
        task = {
            "id": case["id"],
            "name": case["id"].replace("-", " ").capitalize(),
            "description": case["request"],
            "tags": [case["category"], case["skill"]],
            "golden": quality,
            "inputs": {
                "prompt": f"SCENARIO_ID={case['id']}\nUse {case['skill']}.\n"
                          + case["request"] + "\n" + OUTPUT_CONTRACT
                          + "\nOutput shape (types only; derive values from evidence): "
                          + json.dumps({section: value_shape(case["expected"][section])
                                        for section in ("selected", "observations")}),
                "files": [{"path": "evidence.json",
                           "content": json.dumps(case["evidence"], indent=2) + "\n"},
                          {"path": "output-contract.json"}],
            },
            "requirements": [{
                "id": case["id"] + "-contract",
                "category": "boundary",
                "description": "Final-contract checks only; observed execution requires separate evidence.",
                "checks": [{"scope": "task", "grader": metric}],
            }],
            "graders": [{
                "name": metric, "type": "program",
                "config": {"command": "python3",
                           "args": ["evals/waza/grade.py", "--scenario", case["id"], "--mode", mode],
                           "timeout": 10},
            }],
        }
        tasks[f"tasks/{case['id']}.yaml"] = task
    spec = {
        "name": "aigateway-quality-contracts" if quality else "aigateway-offline-smoke",
        "scenario": "aigateway-follow-up",
        "schemaVersion": "2.0",
        "description": "Synthetic plans, not live Azure/model coverage or a quality grade.",
        "version": "1.0",
        "config": {
            "trials_per_task": trials, "timeout_seconds": 120,
            "parallel": True, "workers": 2, "max_attempts": 1,
            "executor": "copilot-sdk" if quality else "mock", "model": model,
            "inject_skill_body": False,
            "skill_directories": [f"{skill_prefix}/{skill}" for skill in skills],
            "required_skills": skills,
        },
        "metrics": [{"name": metric, "weight": 1, "threshold": 1,
                     "description": "Binary contract/plumbing checks, not an A grade."}],
        "tasks": ["tasks/*.yaml"],
    }
    return {"eval.yaml": spec, "fixtures/output-contract.json": contract, **tasks}


def materialize(destination, docs):
    destination = Path(destination).resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError("output must remain under evals/waza")
    for name, document in docs.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n" if path.suffix == ".json"
                        else yaml.safe_dump(document, sort_keys=False, width=100))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--authorized", action="store_true",
                        help="Attest explicit model-call/source-disclosure authorization; this does not run Waza")
    parser.add_argument("--model")
    parser.add_argument("--trials", type=int, default=1)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    if args.quality:
        if not args.authorized or not args.model or not args.model.strip():
            parser.error("--quality requires --authorized and an explicitly chosen --model")
        materialize(ROOT / "authorized-quality",
                    documents("quality", args.model, args.trials))
    else:
        if args.authorized or args.model or args.trials != 1:
            parser.error("model/authorization/trial overrides apply only to --quality")
        materialize(ROOT, documents())


if __name__ == "__main__":
    main()
