"""Materialize pinned-schema Waza tasks; never run a model or Azure command."""

import argparse
import json
import re
from pathlib import Path

import yaml

from grade import ROOT, behavior_expected, cases

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

PLANNING_CONTRACT = """
This is a fixed-input planning task. All tools are denied. The selected skill text,
task references, recorded local CLI help and evidence are supplied below, so do
not try to read files or invoke a skill.
The sandbox also receives evidence.json containing exactly the inline synthetic
evidence. Relative links in the quoted skill are context, not requests to load
more files; file and skill tools remain denied.
Return one JSON object with scenario, selected, observations, commands (array of
native CLI proposals whose changes already have the required approval),
pendingCommands (array of {command, approvals} for optional work requiring further
approval), and executed: false. No proposal may be executed in this evaluation.
Each pending approval is {action, scope}, with an exact resource ID for scope.
The action is a typed operation, not an explanatory sentence. Identity operations
use {operation, identityType}; role operations use {operation, role, principal},
where principal is {identityType, resourceId}. Operation names are identity.assign,
identity.remove, role.assign, or role.remove. Derive the operation, identity type,
role, principal resource and scope from the supplied skill and evidence.
Disclose each exact external side effect; put explanations in notes, not action.
Keep approved work and pending work separate. Omit unsupported command recipes;
report missing information rather than guessing. A read-back is not verification.
Use the typed fact shape below; explanations belong in notes. Facts come from
evidence. Missing evidence stays unknown/unavailable, not an invented success.
String facts describe a category or identifier, not a sentence: units name the
unit, uncertainty uses unknown/unavailable, and residuals identify unsupported
source behaviors present in evidence. Put counts, explanations and evidence
gaps in notes rather than merging them into these atomic facts.
Import lists describe the proposed import, not deployments already imported.
The commands array contains native CLI proposals only; application code and
non-native runtime request examples belong in notes, with their selected runtime
parameters retained in selected. Use the supplied task context to prepare the
requested plan; optional local help/version proposals do not replace it.
No decision label, gate identifier or special limitation phrase is required.
"""


def skill_text(case):
    path = ROOT.parents[1] / "skills" / case["skill"] / "SKILL.md"
    text = path.read_text()
    if case["skill"] == "migrate-ai-gateway":
        # This suite assesses only; execution/mapping recipes are not in scope.
        text = text.split("## 2. Initialize and map")[0]
    return text


def task_context(case):
    base = ROOT.parents[1] / "skills" / case["skill"]
    sections = []
    for reference in case.get("context_sections", []):
        filename, heading = reference.split("#", 1)
        path = (base / filename).resolve()
        if not path.is_relative_to((base / "references").resolve()):
            raise ValueError("task context must come from the selected skill's references")
        text = path.read_text()
        matches = list(re.finditer(r"^(#{1,6}) " + re.escape(heading) + r"$", text, re.M))
        if len(matches) != 1:
            raise ValueError("missing or ambiguous task-reference heading: " + reference)
        match = matches[0]
        following = re.search(r"^#{1," + str(len(match[1])) + r"} ", text[match.end():], re.M)
        end = match.end() + following.start() if following else len(text)
        sections.append(reference + "\n" + text[match.start():end].strip())
    if case["skill"] == "manage-ai-gateway" or case["id"] == "native-task-scoped-discovery":
        help_data = json.loads((ROOT / "native-help.json").read_text())
        sections.append("Recorded local CLI help (not live resource evidence):\n"
                        + json.dumps({"extensionVersion": help_data["extensionVersion"],
                                      "semantics": help_data["semantics"],
                                      "commands": [{"command": row["command"],
                                                    "options": row["verifiedFixtureOptions"]}
                                                   for row in help_data["commands"]]}, indent=2))
    return "\n\n".join(sections)


def value_shape(value):
    if isinstance(value, dict):
        return {key: value_shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [value_shape(value[0])] if value else []
    return {str: "string", bool: "boolean", int: "integer", float: "number",
            type(None): "null"}[type(value)]


def documents(mode="smoke", model="offline-mock", trials=1, holdouts=False, combined=False):
    if holdouts and combined:
        raise ValueError("select separate or combined holdouts, not both")
    quality = mode == "quality"
    metric = "contract_assertions" if quality else "harness_smoke"
    skills = ["manage-ai-gateway", "use-ai-gateway",
              "migrate-ai-gateway", "feedback-ai-gateway"]
    skill_prefix = "../../../skills" if quality else "../../skills"
    holdout_cases = yaml.safe_load((ROOT / "holdouts.yaml").read_text())["cases"]
    holdout_ids = {case["id"] for case in holdout_cases}
    scenario_cases = holdout_cases if holdouts else cases() + (holdout_cases if combined else [])
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
        "gateIdentifiers": sorted({gate for c in scenario_cases for gate in c["expected"].get("gates", [])}),
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
        if quality:
            task["inputs"]["prompt"] = (
                f"SCENARIO_ID={case['id']}\n{case['request']}\n{PLANNING_CONTRACT}"
                + "\nFact shape (types only): " + json.dumps(value_shape(behavior_expected(case)))
                + "\nSelected skill text:\n" + skill_text(case)
                + "\nSelected task context:\n" + task_context(case)
                + "\nSynthetic evidence:\n" + json.dumps(case["evidence"], indent=2))
            # A real evidence resource satisfies Waza's empty-sandbox path guard.
            task["inputs"]["files"] = [
                {"path": "evidence.json",
                 "content": json.dumps(case["evidence"], indent=2) + "\n"}]
            task["graders"] = [
                {"name": name, "type": "program",
                 "config": {"command": "python3",
                            "args": ["evals/waza/grade.py", "--scenario", case["id"],
                                     "--mode", name, *(["--holdouts"] if case["id"] in holdout_ids else [])],
                            "timeout": 10}}
                for name in ("behavior", "syntax")]
            task["requirements"][0]["checks"] = [
                {"scope": "task", "grader": "behavior"},
                {"scope": "task", "grader": "syntax"}]
            task["requirements"][0]["description"] = (
                "Typed representation and scenario behavior are separate checks; no execution evidence.")
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
    if quality:
        spec["skill"] = "aigateway-planning"
        spec["config"].update(
            skill_directories=[".."], required_skills=["aigateway-planning"],
            inject_skill_body=True)
        spec["metrics"] = [
            {"name": name, "weight": 1, "threshold": 1,
             "description": ("Scenario facts, scoped approved/pending actions; not observed execution."
                             if name == "behavior" else "Output types and CLI syntax, not skill quality.")}
            for name in ("behavior", "syntax")]
        spec["name"] = ("aigateway-planning-combined" if combined else
                        "aigateway-planning-holdouts" if holdouts else "aigateway-planning-quality")
        contract = {"description": "Fixed-input planning: no gate vocabulary or scenario answers."}
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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--holdouts", action="store_true",
                        help="Prepare the separate three-task development-variant suite, not the 18-task baseline")
    selection.add_argument("--include-holdouts", action="store_true",
                           help="Prepare original 18 plus the three development variants")
    parser.add_argument("--trials", type=int, default=1)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    if args.quality:
        if not args.authorized or not args.model or not args.model.strip():
            parser.error("--quality requires --authorized and an explicitly chosen --model")
        materialize(ROOT / ("authorized-combined" if args.include_holdouts else
                            "authorized-holdouts" if args.holdouts else "authorized-quality"),
                    documents("quality", args.model, args.trials, args.holdouts,
                              combined=args.include_holdouts))
    else:
        if args.authorized or args.model or args.trials != 1 or args.holdouts or args.include_holdouts:
            parser.error("model/authorization/trial overrides apply only to --quality")
        materialize(ROOT, documents())


if __name__ == "__main__":
    main()
