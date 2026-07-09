# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Controller Validation

## Inputs

- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- Agent delivery: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-codex.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`

## Verdict

The P2-A plan is ready for independent plan review.

The plan performs fresh current-code confirmation rather than mechanically copying the old full-repo findings. The controller independently verified the core evidence and agrees with the finding judgments:

- DS 03 remains accepted: `session.py` still imports prompt/interactive private helpers.
- DS 10 should be treated as partially accepted / updated: Service owns normal missing RESULT fallback, while CLI still has a downstream fake business RESULT fallback that should become hard contract violation.
- DS 11 remains accepted: session has structured `HostApiError` formatting/exit policy, prompt and interactive use generic exception formatting.

## Direct Evidence Checked

- `dayu/cli/commands/session.py:36-45`: imports `_execute_*` and `_prepare_*` private helpers from prompt / interactive command modules.
- `dayu/cli/commands/session.py:251-267` and `dayu/cli/commands/session.py:275-289`: session resume calls those private helpers for prompt / interactive modes.
- `dayu/service/fins_direct.py:207-213`, `:355-361`, `:423-429`, `:468-474`: all Fins direct Service streams are wrapped by `_ensure_result_event`.
- `dayu/service/fins_direct.py:477-510`: Service `_ensure_result_event` guarantees a single RESULT on normal stream close and fail-fast on duplicate RESULT.
- `dayu/cli/commands/fins.py:703-731` and `:899-923`: CLI still synthesizes `_missing_result_event()` after stream exhaustion.
- `dayu/cli/commands/session.py:150-154`, `:621-647`: session command owns structured HostApiError presentation and exit code.
- `dayu/cli/commands/prompt.py:150-162` and `dayu/cli/commands/interactive.py:194-210`: prompt / interactive do not catch `HostApiError` separately and fall through generic `Exception`.

## Plan Quality Notes

- The plan has three implementation slices, matching the control doc's small cross-module cleanup guideline.
- Slice ownership is coherent:
  - S1 moves shared existing-session command execution to a public CLI helper, not a compatibility wrapper around old private functions.
  - S2 leaves normal Fins missing-result fallback in Service and makes CLI treat absence of RESULT as broken Service contract.
  - S3 makes HostApiError presentation / exit policy a CLI-owned shared helper instead of moving process exit code concerns into Service.
- Stop conditions are explicit and useful.
- README trigger decisions are present and appropriately deferred to implementation, because this gate only creates planning artifacts.
- The validation matrix covers affected CLI and Service tests, pyright, and `git diff --check`.

## Required Plan Review Focus

Reviewers should specifically challenge:

- Whether the proposed `dayu.cli.session_execution` helper risks becoming a glue facade rather than a real owner of shared CLI execution semantics.
- Whether S2 should change CLI missing-result behavior to `RuntimeError` or a more specific CLI contract error type.
- Whether HostApiError exit-code policy is conservative enough, especially NOT_FOUND after label resolution versus explicit id selector.
- Whether README update triggers are sufficiently concrete for user-visible CLI stderr / exit-code changes.

## Validation

This gate only changed planning artifacts and the control doc. The controller ran:

```bash
git diff --check
```

Result: passed.
