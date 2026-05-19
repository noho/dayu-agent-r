# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-11-recovery
- Base: 235cf7d (accepted Phase 11 Slice 1 commit)
- Output file: docs/reviews/phase11-slice2-code-review-mimo-20260519.md
- Included scope: Phase 11 Slice 2 uncommitted diff against 235cf7d, untracked files `dayu/host/recovery.py` and `tests/host/test_recovery_scan.py`
- Excluded scope: `docs/reviews/phase11-slice2-implementation-codex-20260519.md` (implementation artifact, not production code), `docs/host/implementation-control.md` (control doc, not production code)
- Parallel review coverage: 无

## Review Checklist

### Plan Conformance

- [x] Allowed files only: `recovery.py`, `state.py`, `run_transition.py`, `event_log.py` (narrow typed helper), `test_recovery_scan.py`, `test_run_attempt_transitions.py`, `README.md`
- [x] No Engine/public API/schema changes
- [x] No dispatch implementation (Slice 3 scope)
- [x] Startup scanner classifies ACCEPTED/QUEUED/WAITING/RUNNING/CANCELLING/RECOVERING
- [x] WAITING diagnostic-only fallback: no Attempt creation, no state mutation
- [x] Positive orphan CAS recheck over Run/Attempt/dispatch/owner/heartbeat stale
- [x] Same-transaction ATTEMPT_LOST then RUN_RECOVERING/RUN_LOST ordering
- [x] CANCELLING orphan not recovered (recoverable guard at line 348-349)
- [x] Recovery dispatch count typed EventLog helper
- [x] Projection lag not truth
- [x] Tests pass (38 passed), pyright clean (0 errors), git diff --check clean

### Verification Results

```bash
pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q  # 38 passed in 0.45s
python -m pyright dayu/host tests/host  # 0 errors, 0 warnings, 0 informations
git diff --check 235cf7d  # clean
```

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `CANCELLING` positive orphan closeout 路径没有 scanner-level 集成测试覆盖（`test_recovery_scan.py` 中无 CANCELLING seed）。单元测试 `test_startup_orphan_closeout_marks_attempt_lost_then_run_recovering` 验证了 `close_startup_orphan_attempt_in_transaction` 的 recoverable 路径，但 CANCELLING 专属 reason (`cancel_in_flight_attempt_lost`) 和 LOST 收口仅由 transition-level 代码路径保证，无 scanner 端到端断言。风险低：CANCELLING 与 RUNNING 共享 `_classify_active_or_cancelling` 入口，`recoverable` 由 `run.status is RunStatus.RUNNING` 守护，`_startup_closeout_reason` 对 CANCELLING 返回 `_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST`。
