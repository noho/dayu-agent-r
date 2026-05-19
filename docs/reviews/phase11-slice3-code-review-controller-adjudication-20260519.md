# Phase 11 Slice 3 Code Review Controller Adjudication

## Gate

Phase 11 Slice 3 code review adjudication.

## Inputs

- Implementation artifact: `docs/reviews/phase11-slice3-implementation-codex-20260519.md`
- MiMo code review: `docs/reviews/phase11-slice3-code-review-mimo-20260519.md`
- DS code review: `docs/reviews/phase11-slice3-code-review-ds-20260519.md`
- Accepted plan: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- Accepted Slice 2 commit: `2e89558`

## Review Results

- AgentMiMo: PASS, blocking count = 0, one low finding.
- AgentDS: PASS, blocking count = 0, two low findings and residual risks.

## Controller Decision

Decision: require a narrow Slice 3 fix before accepted slice commit.

基于 design_doc 的设计目标和第一性原理，Slice 3 correctly implements recovery dispatch without crossing the WorkerProxy boundary. The remaining issues are not blockers, but they affect durable diagnostic clarity and developer-facing module truth. Both are cheap to fix before committing the slice.

## Finding Decisions

### MiMo 001: `dayu.host.recovery` module docstring stale

Decision: accepted for current Slice 3 fix.

Rationale: the module now owns startup orphan closeout plus recovery dispatch record creation. A docstring claiming it does not create recovery Attempt misstates the Host module ownership boundary and can mislead later implementation/review.

Required fix: update `dayu/host/recovery.py` module docstring to describe current Slice 3 responsibilities: startup scan, orphan closeout, recovery dispatch Attempt / execution / dispatch creation, and post-commit scheduler wake; also state it still does not call WorkerProxy directly.

### DS 1: orphan closeout succeeds but recovery dispatch CAS returns `INVALID_STATE`

Decision: accepted for current Slice 3 fix.

Rationale: durable state is safe, but the scanner decision should reflect the durable fact that the old Attempt was closed and the Run is now `RECOVERING`. Returning plain `INVALID_STATE` after successful closeout weakens observability and can mislead diagnostics. The fix should not change durable mutation semantics; it should only make the returned action/decision express the successful closeout plus pending retry/follow-up.

Required fix: if `_close_positive_orphan` successfully writes orphan closeout and subsequent recovery dispatch creation returns `INVALID_STATE`, return a decision such as `RECOVERING_READY` or equivalent existing non-terminal recovery decision instead of plain `INVALID_STATE`, and add a focused test for this partial-success path if practical.

### DS 2: `lose_recovering_run_in_transaction` precondition sufficient

Decision: accepted as no-action / close tracking item.

Rationale: DS verified the Slice 2 tracked item under actual Slice 3 dispatch ownership. The CAS precondition matches the function contract for terminalizing a `RECOVERING` Run and does not need current modification.

Tracking: no further action unless later slices change RECOVERING ownership semantics.

## Required Fix Scope

Allowed files:

- `dayu/host/recovery.py`
- `tests/host/test_recovery_dispatch.py`
- `docs/reviews/phase11-slice3-fix-codex-20260519.md`

The fix must not change Engine, public API, schema, WorkerProxy behavior, RECOVERING cancel, or multi-process behavior.

## Next Gate

Next gate: Phase 11 Slice 3 fix by AgentCodex, then two-way re-review.
