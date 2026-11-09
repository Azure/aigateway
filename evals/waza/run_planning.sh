#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:?Pass the verified generated eval.yaml}"
RESULT="${2:?Pass a fresh result JSON path}"
: "${PLANNING_HOME:?Set the SDK-verified isolated profile}"
case "$RESULT" in *.json) ;; *) printf 'Result must end in .json\n' >&2; exit 1 ;; esac
test ! -e "$RESULT"
test -w "$(dirname "$RESULT")"
test -f "${RESULT%.json}.identity.json"
export CONFIG RESULT PLANNING_HOME

uv run --no-project --with pyyaml --with jsonschema python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import yaml

root = Path.cwd().resolve()
result = Path(os.environ["RESULT"])
record = json.loads(Path(str(result)[:-5] + ".identity.json").read_text())
assert result.resolve().is_relative_to(root / "evals/waza/results")
assert record["result"] == str(result) and record["config"] == os.environ["CONFIG"]
assert record["model"] == "gpt-6.1-sol" and record["trialsPerTask"] == 1
spec = yaml.safe_load(Path(os.environ["CONFIG"]).read_text())
assert spec["config"]["model"] == record["model"]
assert spec["config"]["trials_per_task"] == record["trialsPerTask"]
assert record["sourceDigests"] and Path(record["configSnapshot"]).is_dir()
assert json.loads((Path(os.environ["PLANNING_HOME"]) / "settings.json").read_text()) == {"disableAllHooks": True}
assert record["profileEvidence"] == {
    "hooksDisabled": True, "installedPlugins": 0, "userMcpServers": 0,
    "managedStartupKeys": 0, "existingAuthentication": True,
}
for items in (record["sourceDigests"], record["originalDigests"]):
    for name, expected in items.items():
        path = Path(name)
        assert path.resolve().is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, "Prepared inputs changed"
PY
uv run --no-project --with pyyaml --with jsonschema python evals/waza/verify_planning.py "$CONFIG"
if COPILOT_HOME="$PLANNING_HOME" TMPDIR="$PWD/evals/waza/workspaces" \
  COPILOT_AUTO_UPDATE=false WAZA_NO_UPDATE_CHECK=1 \
  uv run --no-project --with pyyaml --with jsonschema \
  waza run "$CONFIG" --no-cache --output "$RESULT" > "${RESULT%.json}.local.log" 2>&1; then
  WAZA_STATUS=0
else
  WAZA_STATUS=$?
fi
if test -f "$RESULT"; then
  if uv run --no-project --with pyyaml --with jsonschema \
    python evals/waza/verify_planning.py "$CONFIG" --result "$RESULT"; then
    POLICY_STATUS=0
  else
    POLICY_STATUS=$?
  fi
else
  POLICY_STATUS=99
fi
export WAZA_STATUS POLICY_STATUS
uv run --no-project --with pyyaml --with jsonschema python - <<'PY'
import hashlib
import json
import os
from pathlib import Path

p = Path(os.environ["RESULT"])
r = json.loads(Path(str(p)[:-5] + ".identity.json").read_text())
def changed(items):
    return [name for name, old in items.items() if not Path(name).is_file()
            or hashlib.sha256(Path(name).read_bytes()).hexdigest() != old]
status = {"wazaExit": int(os.environ["WAZA_STATUS"]), "policyExit": int(os.environ["POLICY_STATUS"]),
          "changedSource": changed(r["sourceDigests"]), "changedOriginalArtifacts": changed(r["originalDigests"]),
          "sourceCommit": r["sourceCommit"],
          "resultSha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
with Path(str(p)[:-5] + ".status.json").open("x") as f:
    json.dump(status, f, indent=2)
print(json.dumps({"result": str(p), **status}))
assert not status["changedSource"] and not status["changedOriginalArtifacts"], "Freeze or original immutability violated"
PY
if test "$WAZA_STATUS" -ne 0; then exit "$WAZA_STATUS"; fi
exit "$POLICY_STATUS"
