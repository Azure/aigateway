"""Offline config binding, plus optional redacted post-run policy evidence check."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from author import documents
from grade import ROOT


def verify(path):
    path = Path(path).resolve()
    if path.parent not in (ROOT / "authorized-quality", ROOT / "authorized-holdouts"):
        raise ValueError("expected generated quality/holdout evaluation under evals/waza")
    spec = yaml.safe_load(path.read_text())
    policy = yaml.safe_load((ROOT / "planning.agent.md").read_text().split("---")[1])
    if policy["name"] != "aigateway-planning" or policy.get("tools") != []:
        raise ValueError("planning agent must explicitly declare tools: []")
    if (ROOT / "SKILL.md").exists() or (ROOT.parents[1] / "SKILL.md").exists():
        raise ValueError("SKILL.md can shadow the selected .agent.md policy")
    for candidate in ROOT.glob("*.agent.md"):
        header = yaml.safe_load(candidate.read_text().split("---")[1])
        if header.get("name") == policy["name"] and candidate.name != "planning.agent.md":
            raise ValueError("duplicate evaluation agent can shadow the selected policy")
    for candidate in ROOT.parents[1].glob("*.agent.md"):
        header = yaml.safe_load(candidate.read_text().split("---")[1])
        if header.get("name") == policy["name"]:
            raise ValueError("repository-root agent shadows evaluation policy")
    config = spec["config"]
    expected = documents("quality", config["model"], config["trials_per_task"],
                         holdouts=path.parent.name == "authorized-holdouts")
    for name, document in expected.items():
        actual = path.parent / name
        content = json.loads(actual.read_text()) if actual.suffix == ".json" else yaml.safe_load(actual.read_text())
        if content != document:
            raise ValueError("stale or modified generated planning configuration: " + name)
    if {str(p.relative_to(path.parent)) for p in (path.parent / "tasks").glob("*.yaml")} != {
            name for name in expected if name.startswith("tasks/")}:
        raise ValueError("unexpected extra tasks would expand the selected run")
    return {"configuredToolPolicy": "deny_all", "model": config["model"],
            "trialsPerTask": config["trials_per_task"],
            "tasks": sum(name.startswith("tasks/") for name in expected),
            "runtimePolicyVerified": False}


def verify_result(path):
    artifact = json.loads(Path(path).read_text())
    runs = [run for task in artifact["tasks"] for run in task["runs"]]
    counts = {"runs": len(runs), "denyAll": 0, "missingOrDifferentPolicy": 0,
              "denials": 0, "toolEvents": 0, "toolCalls": 0, "missingToolCounts": 0}
    for run in runs:
        digest = run.get("session_digest") or {}
        mode = digest.get("tool_policy_mode") if isinstance(digest, dict) else None
        counts["denyAll" if mode == "deny_all" else "missingOrDifferentPolicy"] += 1
        counts["denials"] += len(digest.get("tool_policy_denials") or []) if isinstance(digest, dict) else 0
        counts["toolEvents"] += len(run.get("tool_events") or [])
        calls = digest.get("tool_call_count") if isinstance(digest, dict) else None
        if type(calls) is not int or calls < 0:
            counts["missingToolCounts"] += 1
        else:
            counts["toolCalls"] += calls
    counts["policyEvidencePassed"] = bool(runs) and not any(
        counts[key] for key in ("missingOrDifferentPolicy", "denials", "toolEvents",
                               "toolCalls", "missingToolCounts"))
    return counts


def verify_preflight(report, eval_path):
    """Accept only the reviewed offline limitations, never other prerequisites."""
    spec = yaml.safe_load(Path(eval_path).read_text())
    expected = documents("quality", spec["config"]["model"],
                         spec["config"]["trials_per_task"],
                         holdouts=Path(eval_path).parent.name == "authorized-holdouts")
    ids = {task["id"] for name, task in expected.items() if name.startswith("tasks/")}
    if (report.get("kind") != "waza.preflight" or report.get("schemaVersion") != "1.0"
            or report.get("complete") is not True or report.get("executor") != "copilot-sdk"
            or Path(report.get("source", "")).resolve() != Path(eval_path).resolve()):
        raise ValueError("preflight report identity/inventory is incomplete or mismatched")
    tasks = report.get("tasks", [])
    if (len(tasks) != len(ids) or {task.get("id") for task in tasks} != ids
            or any(task.get("enabled") is not True for task in tasks)):
        raise ValueError("preflight task inventory differs from the generated suite")
    allowed = {"boundary.requested_policy", "grader.subprocess",
               "boundary.post_run", "runtime.availability"}
    warnings = Counter()
    scoped = Counter()
    policy_tasks = set()
    for diagnostic in report.get("diagnostics", []):
        state, code = diagnostic.get("state"), diagnostic.get("code")
        if state == "verified":
            continue
        if (state != "unresolved" or code not in allowed
                or diagnostic.get("severity") != "warning"):
            raise ValueError("blocked preflight diagnostic: " + str(code))
        task = diagnostic.get("task_id", "")
        if (code == "runtime.availability" and task) or (
                code != "runtime.availability" and task not in ids):
            raise ValueError("preflight warning has unexpected task scope")
        warnings[code] += 1
        scoped[(code, task)] += 1
        if code == "boundary.requested_policy":
            policy_tasks.add(task)
    dependencies = report.get("dependencies", [])
    bound = set()
    for dependency in dependencies:
        if dependency.get("kind") == "boundary":
            if (dependency.get("mode") != "requested-deny-all"
                    or dependency.get("state") != "unresolved"
                    or Path(dependency.get("name", "")).resolve() != ROOT / "planning.agent.md"):
                raise ValueError("preflight did not resolve the expected deny-all policy")
            bound.add(dependency.get("task_id"))
        elif (dependency.get("kind") != "grader" or dependency.get("mode") != "subprocess"
              or dependency.get("state") != "unresolved"
              or dependency.get("task_id") not in ids
              or dependency.get("name") not in ("behavior", "syntax")):
            raise ValueError("unexpected preflight dependency")
    if policy_tasks != ids or bound != ids or warnings["runtime.availability"] != 1:
        raise ValueError("preflight policy/runtime warning inventory is missing")
    if any(scoped[(code, task)] != count for task in ids for code, count in (
            ("boundary.requested_policy", 1), ("boundary.post_run", 1),
            ("grader.subprocess", 2))):
        raise ValueError("preflight per-task warning inventory is missing or duplicated")
    return {"offlinePrerequisitesAccepted": True, "unresolvedWarnings": dict(warnings),
            "runtimePolicyVerified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("eval", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--preflight", type=Path,
                        help="Review Waza --format json report; use - for stdin")
    args = parser.parse_args()
    try:
        report = verify(args.eval)
        if args.preflight:
            content = sys.stdin.read() if str(args.preflight) == "-" else args.preflight.read_text()
            report["preflight"] = verify_preflight(json.loads(content), args.eval)
        if args.result:
            report["postRun"] = verify_result(args.result)
        print(json.dumps(report, indent=2))
        if args.result and not report["postRun"]["policyEvidencePassed"]:
            raise SystemExit(1)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
