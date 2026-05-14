# Controller Aggregate Re-review Adjudication: Host Phase 3 Session / Run / Attempt Admission

- **gate**: aggregate re-review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **date**: 2026-05-14
- **base accepted slice HEAD**: `49fc1d5`
- **aggregate review artifacts**:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p3-session-run-attempt-admission-ds-20260514.md`
- **aggregate fix artifact**: `docs/reviews/gateflow-aggregate-fix-host-p3-session-run-attempt-admission-20260514.md`
- **aggregate re-review artifacts**:
  - `docs/reviews/gateflow-aggregate-re-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-re-review-host-p3-session-run-attempt-admission-ds-20260514.md`

## Decision

Phase 3 aggregate deepreview is accepted. No blocking findings remain.

AgentMiMo reported no blocking finding. AgentDS reported two non-blocking findings:

- N-1: `_require_event_sequence` used the literal `event_log` table name.
- N-2: `terminal_run_row` allowed `WAITING` as a forward-looking source state without documenting the Phase 3 boundary.

Controller accepted both as small aggregate fixes because they reduce maintenance ambiguity without changing runtime behavior, schema, EventLog semantics, CAS conditions or Phase 3 scope.

## Fix Verification

Both aggregate re-review agents confirmed the fixes:

- N-1 fixed: `dayu/host/admission.py` now uses `TABLE_EVENT_LOG`.
- N-2 fixed: `dayu/host/durable/state.py` documents that `WAITING` is reserved for a later wait resolve path and Phase 3 callers only pass `RUNNING`.

AgentMiMo aggregate re-review result:

- `pytest tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: clean
- conclusion: accepted / no blocking findings

AgentDS aggregate re-review result:

- `pytest tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: clean
- conclusion: accepted / no blocking findings

Controller also reran:

- `pytest tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: passed

## Residual Risk Ownership

- Phase 4 Host Public API Command Path owner must add API-level coverage for queued cancel versus promotion once public command facade wiring exists.
- Phase 5 RunInputBuilder 与本地执行 Dispatch owner owns scheduler, lane acquire, dispatch record `dispatching`, `ATTEMPT_RUNNING`, Engine dispatch and active worker cancel propagation.
- Phase 5 scheduler / wakeup owner must define the retry or scan path for queued Runs if after-commit promotion fails in its separate transaction.
- Phase 7 Tool Awaiting / resolve_wait owner owns `WAITING` Run closeout semantics and public wait resolution behavior.
- Phase 11 Host Lifecycle / Recovery / Multi-process Hardening owner owns recovery scan, positive orphan proof, SQLite multiprocess hardening and long-running busy/retry tuning.

## Gate Result

Phase 3 is completed and ready-to-create-PR after the accepted aggregate deepreview commit is created. All tracked residual items have explicit owners.
