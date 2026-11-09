"""Offline config binding, plus optional redacted post-run policy evidence check."""

import argparse
import json
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("eval", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.eval)
        if args.result:
            report["postRun"] = verify_result(args.result)
        print(json.dumps(report, indent=2))
        if args.result and not report["postRun"]["policyEvidencePassed"]:
            raise SystemExit(1)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
