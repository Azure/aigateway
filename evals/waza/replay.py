"""Read immutable final outputs; print field-only historical/contract assessments."""

import argparse
import hashlib
import json
import subprocess
import types
from collections import Counter
from pathlib import Path

import yaml

from grade import ROOT, cases, evaluate

SNAPSHOTS = {
    "original": "90dc1c2941945dee6484c3db52a3189292f385a6",
    "previous-correction": "4e3e7db97f37e1e52effe5b25e739f867672ad13",
}


def snapshot(commit):
    def text(path):
        return subprocess.run(
            ["git", "show", f"{commit}:evals/waza/{path}"], cwd=ROOT,
            check=True, capture_output=True, text=True).stdout
    inventory = yaml.safe_load(text("cases.yaml"))["cases"]
    module = types.ModuleType("historical_grader")
    module.__file__ = str(ROOT / "grade.py")
    # Only the two explicit, previously published repository revisions above.
    exec(compile(text("grade.py"), "historical_grader", "exec"), module.__dict__)
    module.cases = lambda: inventory
    return inventory, module.check


def replay(path):
    raw = Path(path).read_bytes()
    artifact = json.loads(raw)
    history = {name: snapshot(commit) for name, commit in SNAPSHOTS.items()}
    current = {case["id"]: case for case in cases()}
    original = {case["id"]: case for case in history["original"][0]}
    previous = {case["id"]: case for case in history["previous-correction"][0]}
    report = {"sourceSha256": hashlib.sha256(raw).hexdigest(),
              "kind": "offline-replay-not-a-new-trial", "historical": {},
              "currentContractOriginalEvidence": [], "unknownTasks": 0}
    counters = {name: Counter() for name in history}
    for task in artifact["tasks"]:
        identifier = task["test_id"]
        if identifier not in current:
            report["unknownTasks"] += 1
            continue
        for run in task["runs"]:
            output = run["final_output"]
            for name, (inventory, checker) in history.items():
                case = next(c for c in inventory if c["id"] == identifier)
                try:
                    checker(case, output)
                    counters[name]["pass"] += 1
                except ValueError:
                    counters[name]["fail"] += 1
            # Preserve the original inputs. Do not score old answers against
            # changed URLs or treat an offline replay as a new prompt execution.
            case = json.loads(json.dumps(current[identifier]))
            case["evidence"] = original[identifier]["evidence"]
            # Retain the reviewed current alias oracle; runtime URLs are derived
            # from the original evidence by behavior_expected.
            if identifier == "runtime-only-known-endpoint":
                case["expected"]["observations"] = original[identifier]["expected"]["observations"]
            item = {"task": identifier}
            for component in ("behavior", "syntax"):
                item[component] = evaluate(case, output, component)
            try:
                history["previous-correction"][1](previous[identifier], output)
                item["previouslyFailed"] = False
            except ValueError:
                item["previouslyFailed"] = True
            report["currentContractOriginalEvidence"].append(item)
    report["historical"] = {
        name: {"rubricCommit": SNAPSHOTS[name], **dict(counts)}
        for name, counts in counters.items()}
    for component in ("behavior", "syntax"):
        report[component] = dict(Counter(
            item[component]["status"] for item in report["currentContractOriginalEvidence"]))
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != report["sourceSha256"]:
        raise ValueError("source artifact changed during read-only replay")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.result), indent=2))
