# Phase 11 Slice 2 Re-Review Controller Adjudication

## Gate

Phase 11 Slice 2 re-review adjudication.

## Inputs

- Slice 2 implementation artifact: `docs/reviews/phase11-slice2-implementation-codex-20260519.md`
- Slice 2 fix artifact: `docs/reviews/phase11-slice2-fix-codex-20260519.md`
- MiMo re-review: `docs/reviews/phase11-slice2-rereview-mimo-20260519.md`
- DS re-review: `docs/reviews/phase11-slice2-rereview-ds-20260519.md`
- Controller code review adjudication: `docs/reviews/phase11-slice2-code-review-controller-adjudication-20260519.md`

## Review Results

- AgentMiMo: PASS, blocking count = 0.
- AgentDS: PASS, blocking count = 0. DS corrected one factual typo in its artifact; conclusion unchanged.

Both re-reviewers confirmed the accepted fixes are complete:

- stale threshold is carried as `timedelta`, eliminating integer truncation between classifier and CAS recheck;
- CANCELLING scanner-level positive orphan coverage proves `ATTEMPT_LOST` then `RUN_LOST` and no `RUN_RECOVERING`;
- ACCEPTED and QUEUED classification tests prove no mutation, no recovery facts, and no Attempt creation;
- `lose_recovering_run_in_transaction` precondition simplicity remains deferred to Slice 3 review per Controller decision.

## Controller Decision

Decision: accept Slice 2.

基于 design_doc 的设计目标和第一性原理，Slice 2 now satisfies the core startup recovery scan contract: non-mutating states remain non-mutating, active orphan closeout performs durable CAS recheck, EventLog and state-index updates are ordered in the same transaction, CANCELLING does not recover execution, and recovery dispatch count is derived from canonical EventLog facts rather than projection or read model state.

## Validation Evidence

Controller locally reran:

- `pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q`: 42 passed.
- `python -m pyright dayu/host tests/host`: 0 errors.
- `git diff --check`: clean.

## Residual Tracking

- `lose_recovering_run_in_transaction` source Attempt precondition simplicity: track explicitly in Slice 3 code review, because Slice 3 introduces actual recovery dispatch and new Attempt ownership.
- Actual RECOVERING dispatch, scheduler wake integration, and `open_host(...)` startup hook remain Slice 3 owner.
- RECOVERING public cancel behavior remains Slice 4 owner.

## Next Gate

Next gate: accepted Slice 2 local commit, then Phase 11 Slice 3 implementation.
