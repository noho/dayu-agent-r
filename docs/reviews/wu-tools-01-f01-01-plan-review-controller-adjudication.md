# WU-TOOLS-01-F01-01 Plan Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: plan review
- Plan artifact: `docs/host/wu-tools-01-f01-01-filelock-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-01-plan-review-ds.md`

## Verdict

Plan review passed with non-blocking findings. The plan is directionally code-generation-ready, but two clarification findings should be fixed in the plan artifact before accepted-plan commit.

Next gate: `fix`.

## Finding Adjudication

### A1. `_release_ticker_lock` token parameter and dict cleanup

- Source findings: MiMo F1; DS F2.
- Decision: accepted.
- Reason: Slice 2 changes `_release_ticker_lock` from stream lifecycle to token lifecycle. The implementation plan should explicitly require `stream` to become `token: RuntimeFileLockToken | None = None`, and explicit-token release should still remove the ticker entry from `_ticker_lock_tokens` to avoid preserving the existing stale-reference edge case.
- Required fix: update the plan artifact Slice 2 exact changes / implementation decisions with this rule.

### A2. `_StoreFileLock` fd-close test deletion rationale

- Source findings: MiMo F2; DS F3.
- Decision: accepted.
- Reason: Removing `_StoreFileLock` makes the old Fins-specific file-descriptor close test obsolete, but the plan should state why this is not a coverage loss: Fins no longer opens the lock stream, and fd lifecycle is owned by `dayu.runtime.filelock` / third-party `filelock`.
- Required fix: update the plan artifact Slice 1 tests or completion/report guidance with this rationale.

### R1. Blocking flock versus non-blocking retry implementation detail

- Source finding: DS F1.
- Decision: rejected-with-reason.
- Reason: This is useful implementation evidence, but it is not a plan defect. The plan already defines `RuntimeFileLock` blocking acquire as the public contract, includes a stop condition if runtime filelock cannot replace cross-process mutual exclusion, and requires affected Fins/runtime validation. The third-party implementation detail should not become a Fins-specific plan requirement.

### R2. `_fs_storage_infra` single-file coverage may be below 80 percent

- Source finding: MiMo F3.
- Decision: rejected-with-reason.
- Reason: The plan already requires coverage commands where practical and requires implementation report classification if broad shared infra coverage cannot reach the single-file target. There is no missing plan action.

## Residual Risks

- `RuntimeFileLockError` docstring / error surface changes remain implementation-owned and are already tracked in the plan residual risks.
- Release failure type changes remain implementation-owned and must be reported in Slice 2 validation.
- Stale lock, lease, fencing, crash recovery ownership and distributed lock semantics remain out of scope by design.

No unclassified residual risk remains for plan review.

## Validation

- Read both review artifacts.
- Cross-checked accepted findings against the plan artifact and current Fins lock call paths.
- Controller whitespace check for the untracked plan artifact used `git diff --no-index --check /dev/null docs/host/wu-tools-01-f01-01-filelock-plan.md`; it produced no whitespace diagnostics.
