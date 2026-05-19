# Phase 11 Slice 2 Code Review Controller Adjudication

## Gate

Phase 11 Slice 2 code review adjudication.

## Inputs

- Implementation artifact: `docs/reviews/phase11-slice2-implementation-codex-20260519.md`
- MiMo code review: `docs/reviews/phase11-slice2-code-review-mimo-20260519.md`
- DS code review: `docs/reviews/phase11-slice2-code-review-ds-20260519.md`
- Accepted plan: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- Accepted Slice 1 commit: `235cf7d`

## Review Results

- AgentMiMo: PASS, blocking count = 0, no substantive findings.
- AgentDS: PASS, blocking count = 0, one low observation and three residual risks.

## Controller Decision

Decision: require a narrow Slice 2 fix before accepted slice commit.

基于 design_doc 的设计目标和第一性原理，Slice 2 owns startup classification and CAS closeout. Even non-blocking gaps on CANCELLING orphan and classification no-mutation tests should be closed before implementation moves on, because these are core Phase 11 recovery decisions and cheap to verify at this boundary.

## Finding Decisions

### DS finding: `int()` truncation in stale threshold handoff

Decision: accepted for current Slice 2 fix.

Rationale: classifier and CAS recheck must be logic/data co-sourced. Even if the default threshold is integer seconds, carrying the policy threshold as a lossy int creates avoidable semantic drift. The fix should preserve the exact threshold semantics using `float` seconds or `timedelta` while keeping public/schema unchanged.

Required fix: align `StartupOrphanCloseInput` stale threshold and CAS recheck with `OrphanClassificationPolicy.stale_after` without integer truncation, and add a focused boundary test if practical.

### MiMo / DS residual: CANCELLING orphan scanner-level coverage

Decision: accepted for current Slice 2 fix.

Rationale: `CANCELLING` positive orphan must not recover execution. This is a core Phase 11 design discussion baseline, so scanner-level proof should not rely only on helper-level indirect coverage.

Required fix: add focused scanner-level test proving CANCELLING + positive orphan proof writes `ATTEMPT_LOST` then `RUN_LOST`, uses `cancel_in_flight_attempt_lost` or equivalent structured reason, and never writes `RUN_RECOVERING`.

### DS residual: ACCEPTED / QUEUED classification coverage

Decision: accepted for current Slice 2 fix.

Rationale: accepted / queued paths are simple but define startup non-mutation behavior. Low-cost focused tests protect against future broad conditions accidentally mutating these states.

Required fix: add focused tests proving ACCEPTED and QUEUED startup classification does not mutate Run / Attempt state and does not append recovery facts.

### DS residual: `lose_recovering_run_in_transaction` precondition simplicity

Decision: rejected-current-fix / track in Slice 3 review.

Rationale: DS found the current precondition sufficient for Slice 2 independent behavior. Slice 3 will introduce actual recovery dispatch and new Attempt ownership, so that is the correct gate to re-evaluate RECOVERING source attempt invariants.

Tracking: Slice 3 code review must explicitly check recovering limit / dispatch interaction with source Attempt identity.

## Required Fix Scope

Allowed files:

- `dayu/host/durable/run_transition.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `docs/reviews/phase11-slice2-fix-codex-20260519.md`

The fix may also touch `dayu/host/recovery.py` only if required to preserve exact stale threshold semantics. It must not change schema, public API, Engine, or Slice 3 dispatch behavior.

## Next Gate

Next gate: Phase 11 Slice 2 fix by AgentCodex, then two-way re-review.
