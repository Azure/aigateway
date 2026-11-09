# Azure AI Gateway evaluations

The [Waza suite](waza/README.md) covers 18 synthetic management, discovery,
integration, and negative scenarios, plus three separately selected development
variants. Their historical `holdout` names remain for compatibility; they have
been repeatedly inspected and do not provide genuine held-out validation.
It checks selected subscriptions and gateways, exact callable/auth contracts,
least-privilege reads, explicit approvals, and evidence-aware recovery.

## What is ready

- **Authored:** `waza/eval.yaml`, 18 tasks, synthetic evidence, contract graders,
  and an explicit authorized `copilot-sdk` configuration preparation command.
  New quality tasks supply selected skill text and evidence inline, without
  grader files or expected answers, plus one matching synthetic evidence resource
  to satisfy Waza's relative-path/empty-sandbox guard. A development-only `tools: []` agent denies
  all model tools; it does not change installed runtime skills.
  Native command comparisons allow equivalent flag ordering while retaining
  exact scopes, values and operation order.
- **Static/offline:** deterministic fixture, pinned-schema, grader-negative,
  response-shape, MCP-sequence and budget-formula checks. Run from the repository root:

  ```bash
  uv run --no-project --with pyyaml --with jsonschema \
    python -m unittest discover -s evals/waza -p 'test_*.py' -q
  ```

  These use uv-managed Python, PyYAML and jsonschema without credentials,
  model calls or Azure calls. Missing Python/dependencies may require uv downloads.
- **Harness:** checked-in Waza executor is `mock`, with two parallel workers.
  A supplied local smoke artifact reports 18 passes and no errors. Mock echoes
  inputs; its grader checks synthetic positive/missing-gate answers. These
  exercise wiring and assertions, not an assistant's behavior or safety.
- **Real evaluation:** a supplied Copilot SDK / GPT-6.1 Sol artifact reports
  one run per task, 0 original passes, 18 contract failures and no harness errors.
  The [redacted PR journal](https://github.com/Azure/aigateway/pull/38#issuecomment-6730494888)
  distinguishes rubric defects from behavior findings. Corrected graders can be
  replayed offline against those outputs; that is not a new model trial.
  The original run established neither enforced tool isolation nor a paired CLI
  baseline. A newer operator planning artifact reports 18 failed tasks, but 17
  stopped before the model at a shared empty-sandbox path guard. The one executed
  task passes syntax and fails residual-fact behavior; it records deny-all and zero
  tool calls. Whole-suite policy evidence fails because 17 policies are missing.
  This is not 18 skill regressions. The corrected input resources require
  configuration regeneration, not a rubric change. Reported usage was one premium
  request and 3.36635 AI credits in that operator-owned run.
  Subsequent explicitly authorized assistant-owned runs are recorded separately
  in the suite guide and PR journal. The corrected candidate passed 21/21 in one
  fresh trial, then 19/21 in the next unchanged trial. Both have complete
  deny-all/zero-tool-activity evidence and 21/21 syntax. This is not three-trial
  repeatability. Offline corrections now accept the correctly scoped alias list
  and equivalent composite-counter representation while independently requiring
  the management skill's same-name family preflight before the alias update.
  Foreign targets, late/missing preflight and independent counters remain
  rejected. The existing skill precaution was moved next to execution to make
  the required ordering harder to omit. A separate replay passes 21/21 and
  20/21 behavior, with the second still failing its missing family check;
  syntax passes throughout. These are unchanged old outputs, not fresh scores
  or validation of the repositioned guidance. The
  bootstrap request is now explicitly single-deployment; case-only identity
  normalization does not broaden approval or import scope. These offline
  corrections change the candidate and reset repeatability, not the saved scores.
  A subsequently authorized frozen trial passed 19/21 again, but alias routing
  and composite accounting passed. Its bootstrap model-inventory and stale-sync
  parent-family reads were rejected by incomplete evaluator read coverage.
  Offline correction now consistently accepts exact management parent preflight
  and explicitly scopes the bootstrap model list, retaining required writes,
  approvals and runtime-only isolation. A separate unchanged-output replay is
  21/21, not a fresh score; the 60-test suite passes. No request/evidence/skill
  change occurred in that correction, but repeatability resets.
  Paid runs stopped after that first invocation, with two unused; they cannot establish three
  consecutive green trials. The user subsequently chose **Stop paid trials**;
  no further paid invocation is scheduled. Session-local startup isolation and deny-all are
  not an OS filesystem/credential/network sandbox and do not test plugin
  discovery or progressive loading. Further execution needs sufficient explicit
  spending approval for the unchanged-candidate validation target.

**Stopped-spending offline audit:** safe parent reads are consistently compared,
but bootstrap and approved Foundry create plans could still omit the management
recipe's family preflight. The shared plan checker now requires it before the
tested name-selected writes. Scope/identity/role/negation and required child-read,
mutation and read-back ordering remain strict. All 21 inputs retain their user
intent and supplied evidence; no skill text or approval boundary changed.
Repeated exact required child reads are accepted without replacing later
read-back or missing writes; unrelated reads remain excluded.
All 63 offline evaluation and 10 plugin regressions pass. The audit inspected
12 immutable results and kept its diagnostics separate from saved fresh scores.
The latest output still replays at 21/21; its fresh score remains 19/21.
Repeatability is reset, not established, and paid trials remain stopped.

This is fixed-input instruction-following evidence, not a test of actual skill
discovery, selection or progressive loading. Genuine held-out evaluation,
live CLI/data-plane behavior and matched CLI performance remain absent.

The suite guide defines per-task behavior boundaries, separate representation/
syntax checks, approval-pending plans, quality dimensions, proposed
latency/tool budgets against matched CLI baselines, and grade-A prerequisites.
No measured baseline, live coverage, or letter grade is claimed. Final-output
checks cannot prove that an assistant avoided transient mutations or tool-side
secret disclosure.

## Authoring provenance

The complete [eval](https://raw.githubusercontent.com/microsoft/waza/v0.40.1/schemas/eval.schema.json)
and [task](https://raw.githubusercontent.com/microsoft/waza/v0.40.1/schemas/task.schema.json)
schemas were read from public raw **Waza `v0.40.1`**, with tag commit
`e0c251df896bee4e0f9b38a693a6105bf7eadd19`.
They are preserved unmodified, checked against that immutable commit, with SHA-256 digests in
[`waza/sources.json`](waza/sources.json) and an upstream MIT notice.

Pinned [CLI runner](https://raw.githubusercontent.com/microsoft/waza/v0.40.1/cmd/waza/cmd_run.go),
[mock executor](https://raw.githubusercontent.com/microsoft/waza/v0.40.1/internal/execution/mock.go)
and [program grader](https://raw.githubusercontent.com/microsoft/waza/v0.40.1/internal/graders/program_grader.go)
establish `waza run`, scenario schema 2.0, parallel configuration, eval-relative
skill directories, mock echo behavior, and stdin/exit-status grading.
Exact commands, authorization switch, source caveats and limitations are in the
[suite guide](waza/README.md). The tag README retains an older `v0.39.1`
release-boundary paragraph; tag schema provenance is not binary verification.

Actual installed native CLI **1.0.0b22** version/help evidence is recorded in
[`waza/native-help.json`](waza/native-help.json). Offline checks verify fixture
options against that surface, including Foundry single-deployment onboarding
and alias priority/weight updates. Help reads do not establish live behavior,
installed-wheel provenance, or new-RP dispatch.
