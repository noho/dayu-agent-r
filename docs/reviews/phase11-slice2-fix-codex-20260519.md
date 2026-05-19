# Phase 11 Slice 2 Fix — AgentCodex

## Scope

- Role: Phase 11 Slice 2 fix specialist
- Fix target: controller-accepted findings only
- Source adjudication: `docs/reviews/phase11-slice2-code-review-controller-adjudication-20260519.md`
- Excluded: rejected/deferred `lose_recovering_run_in_transaction` precondition review item
- GitHub actions: no commit, no push, no PR

## Per-Finding Status

### 1. stale threshold `int()` truncation

Status: fixed.

`StartupOrphanCloseInput` now carries the stale threshold as `timedelta` instead of lossy integer seconds. Startup recovery passes `policy.stale_after` directly, and CAS recheck uses the same `occurred_at - heartbeat_at > stale_after` semantics as the classifier boundary. A focused fractional-threshold test covers the previous truncation edge.

### 2. CANCELLING positive orphan scanner-level coverage

Status: fixed.

Added scanner-level coverage for `CANCELLING` plus positive orphan proof. The test verifies the scanner returns `RUN_LOST`, records reason `cancel_in_flight_attempt_lost`, appends `ATTEMPT_LOST` then `RUN_LOST`, and does not append `RUN_RECOVERING`.

### 3. ACCEPTED / QUEUED startup classification coverage

Status: fixed.

Added focused scanner tests for `ACCEPTED` and `QUEUED`. Both tests verify classification only: no recovery facts are appended, Run status and `updated_at` remain unchanged, and no Attempt row is created.

### 4. `lose_recovering_run_in_transaction` precondition simplicity

Status: not changed by design.

Controller rejected this as a current Slice 2 fix and deferred it to Slice 3 review.

## Changed Files

- `dayu/host/durable/run_transition.py`
- `dayu/host/recovery.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `docs/reviews/phase11-slice2-fix-codex-20260519.md`

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q
# 42 passed in 0.51s

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

## New Risks / Open Questions

- No new known risks from this fix.
- README was not changed because the requested allowed-file scope did not include README files and this fix does not change user-facing commands, schema, or public API.

## Conclusion

FIX_COMPLETE
