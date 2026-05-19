# Code Review — Phase 11 Slice 2 Re-review

## Scope

- Mode: current changes
- Branch: feat/host-phase-11-recovery
- Base: 235cf7d (accepted Phase 11 Slice 1 commit)
- Output file: docs/reviews/phase11-slice2-rereview-mimo-20260519.md
- Included scope: uncommitted diff against 235cf7d after fix artifact `docs/reviews/phase11-slice2-fix-codex-20260519.md`
- Excluded scope: `docs/reviews/` artifacts, `docs/host/implementation-control.md` (control doc)
- Parallel review coverage: 无

## Verification Targets

Controller adjudication (`docs/reviews/phase11-slice2-code-review-controller-adjudication-20260519.md`) accepted three items for current fix:

1. Stale threshold `int()` truncation — align CAS recheck with classifier `timedelta` semantics
2. CANCELLING positive orphan scanner-level coverage — ATTEMPT_LOST then RUN_LOST, no RUN_RECOVERING
3. ACCEPTED / QUEUED classification coverage — no mutation, no recovery facts, no Attempt creation

Controller rejected `lose_recovering_run_in_transaction` precondition simplicity as current fix (deferred to Slice 3).

## Verification Results

### 1. Stale threshold `int()` truncation — FIXED

**Evidence chain:**

- `StartupOrphanCloseInput.stale_after` is typed `timedelta` (`run_transition.py` dataclass, diff line 163).
- `recovery.py:370` passes `stale_after=policy.stale_after` directly — no `int()` truncation.
- `_validate_startup_orphan_close_input` validates `request.stale_after <= timedelta(0)` (`run_transition.py` diff line 641).
- CAS recheck at `_invalid_startup_orphan_precondition` uses `request.occurred_at - heartbeat_at > request.stale_after` (`run_transition.py` diff line 573) — pure `timedelta` comparison, no integer conversion.
- Classifier boundary at `recovery_process.py` uses `policy.now - heartbeat_at <= policy.stale_after` — same `timedelta` semantics.

**Boundary test:**

- `test_startup_orphan_closeout_preserves_fractional_stale_threshold` (`test_run_attempt_transitions.py:1629-1668`): heartbeat at `01:01:32.750Z`, occurred_at at `01:02:03Z` (diff = 30.25s), stale_after = `timedelta(seconds=30, milliseconds=500)` (30.5s). `30.25 > 30.5` is False → CAS correctly returns `INVALID_STATE` with 0 ATTEMPT_LOST events. With old `int()` truncation to 30, `30.25 > 30` would be True → CAS would incorrectly proceed. Test passes.

**Conclusion:** Fix is semantically correct. The boundary test directly proves the truncation edge case.

### 2. CANCELLING scanner-level positive orphan test — FIXED

**Evidence chain:**

- `test_scan_cancelling_positive_orphan_loses_attempt_then_run` (`test_recovery_scan.py:153-202`): seeds a CANCELLING Run with stale owner dispatch record, runs scanner, verifies:
  - `decision == StartupRecoveryDecision.RUN_LOST`
  - `reason == "cancel_in_flight_attempt_lost"`
  - Run status after scan is `LOST`
  - `event_types[-2:] == (ATTEMPT_LOST, RUN_LOST)`
  - `RUN_RECOVERING not in event_types`
  - `run_lost_reason == "cancel_in_flight_attempt_lost"`

**Code path verification:**

- `_classify_run` at `recovery.py:199`: `run.status in (RunStatus.RUNNING, RunStatus.CANCELLING)` → `_classify_active_or_cancelling`.
- `_close_positive_orphan` at `recovery.py:348-349`: `recoverable = run.status is RunStatus.RUNNING and ...` — CANCELLING fails first condition → `recoverable = False`.
- `_startup_closeout_reason` at `recovery.py:478`: `status is RunStatus.CANCELLING` → `_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST`.
- `_validate_startup_orphan_close_input` at `run_transition.py` diff line 661: `request.recoverable and request.expected_run_status != RunStatus.RUNNING` raises — but `recoverable=False` so this guard is not triggered.
- `close_startup_orphan_attempt_in_transaction` takes `else` branch → `terminal_orphaned_run_lost_row`.

**Conclusion:** Fix is correct. Scanner-level test covers the full CANCELLING → RUN_LOST path with no RUN_RECOVERING.

### 3. ACCEPTED / QUEUED classification tests — FIXED

**Evidence chain:**

- `test_scan_accepted_does_not_mutate_or_create_attempt` (`test_recovery_scan.py:205-222`): seeds ACCEPTED Run, captures before-state via `_unstarted_scan_observation` (status, updated_at, Attempt count, EventLog types), runs scanner, verifies `decision == ACCEPTED_WAKE`, asserts `after == before`.
- `test_scan_queued_does_not_mutate_or_create_attempt` (`test_recovery_scan.py:225-242`): same pattern for QUEUED → `decision == QUEUE_PROMOTION_CHECK`, `after == before`.

**Code path verification:**

- `_classify_run` at `recovery.py:183-190`: `run.status is RunStatus.ACCEPTED` → `_action(run, ACCEPTED_WAKE, "accepted")` — pure return, no side effects.
- `run.status is RunStatus.QUEUED` → `_action(run, QUEUE_PROMOTION_CHECK, "queued")` — pure return, no side effects.
- No EventLog append, no state mutation, no Attempt creation in either path.

**Conclusion:** Fix is correct. Before/after observation pattern provides strong no-mutation proof.

### 4. `lose_recovering_run_in_transaction` precondition — NOT CHANGED

Controller rejected this as current fix. No code change observed. Deferred to Slice 3 review per adjudication.

## Verification Summary

```bash
pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q
# 42 passed in 0.46s

python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations
```

42 tests (up from 38 pre-fix) — 4 new tests added by fix.

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `test_startup_orphan_closeout_preserves_fractional_stale_threshold` 的时间差为 30.25 秒，stale_after 为 30.5 秒。差值 0.25 秒远大于浮点精度误差，但严格来说边界分辨能力仅在 `int()` 截断场景下有效（30.25 > 30 为 True，30.25 > 30.5 为 False）。若未来 `timedelta` 比较语义变更，该测试仍能提供回归保护，但非极端边界测试。风险极低。

## Conclusion

PASS。Blocking count = 0。Controller adjudication 要求的三项 fix 均已通过逐行走读验证：(1) stale threshold 从 `int()` 改为 `timedelta` 直传，CAS recheck 与 classifier 语义一致，边界测试覆盖亚秒截断场景；(2) CANCELLING scanner-level 测试覆盖 ATTEMPT_LOST → RUN_LOST 路径，无 RUN_RECOVERING；(3) ACCEPTED/QUEUED 测试覆盖无 mutation / 无 recovery fact / 无 Attempt 创建。未引入新 blocker。
