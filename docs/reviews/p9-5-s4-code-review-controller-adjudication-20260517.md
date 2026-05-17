# P9.5 S4 Code Review Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Slice: S4 Host Durable Helper API Tightening.
- Implementation artifact: `docs/reviews/p9-5-s4-host-durable-helper-tightening-implementation-20260517.md`.
- Review artifacts:
  - `docs/reviews/p9-5-s4-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s4-code-review-ds-20260517.md`
- Fix artifact: `docs/reviews/p9-5-s4-fix-20260517.md`.

## Controller Decision

S4 is accepted.

The motivation is valid. Production dispatch must go through the Host-controlled lane wait and durable recheck path; a low-level helper that can jump directly from `PENDING` to `DISPATCHING` is broader than the scheduler path and weakens the Host-as-truth boundary. S4 correctly narrows the helper without adding states, schema, public facade behavior, or Phase 11 recovery semantics.

## Findings Adjudication

### MiMo Review

- Blocking findings: 0.
- Info observations:
  - F1 Python precondition plus SQL CAS check.
  - F2 scheduler recheck and durable helper precondition overlap.
  - F3 `AcceptWorkerRunningInput.local_worker_id` defaulting to `None`.
- Decision: All accepted as non-blocking. F1 overlaps with DS F1 and was fixed with a docstring note. F2 is intentional separation between fast scheduler filtering and transaction-local durable fail-closed checks. F3 is acceptable because `AcceptWorkerRunningInput` is internal and production scheduler paths pass `local_worker_id`; non-local or white-box paths may record `null` as internal diagnostic payload.

### DS F1 — Python precondition and SQL CAS double checks need intent documentation

- Severity: Low.
- Decision: Accepted and fixed.
- Rationale: The dual checks are a correct CAS pattern, but the intent should be explicit because the Python precondition provides structured `NOT_FOUND` / `INVALID_STATE` diagnostics while SQL `WHERE` is the final atomic guard. `docs/reviews/p9-5-s4-fix-20260517.md` records the comment-only fix.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_resolve_wait_command.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_input_builder.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py`
  - Result: 103 passed.
- `source .venv/bin/activate && pytest tests/host`
  - Result: 500 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: clean.

## Accepted State

- Blocking findings: 0.
- Required behavior fixes after review: 0.
- Accepted low documentation fix: 1, completed.
- README decision: `dayu/host/README.md` and `tests/README.md` remain accurate. The current docs already describe the production dispatch path as `pending -> waiting_for_lane -> dispatching`, and no testing convention changed.
- S4 may proceed to accepted slice commit.
