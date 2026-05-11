# P8.5 Slice 5b Re-review

- **review gate name**: re-review
- **work unit**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **assigned slice**: Slice 5b — Attempt Lease / Recovery Adversarial Hardening
- **source review artifact**: `docs/host/phase8.5-s5b-code-review.md`
- **fix artifact**: `docs/host/phase8.5-s5b-fix-report.md`
- **reviewed target**: accepted residual `renew/terminal race targeted supervisor coverage`
- **artifact path**: `docs/host/phase8.5-s5b-rereview.md`

## Reviewer Conclusion

**pass**

accepted residual 已修复。新增 supervisor-level 测试直接驱动真实 `AttemptSupervisor._renew_loop`，在 attempt 已通过 terminal close 收口后，由真实 `AttemptLeaseStore.renew()` 返回 `AttemptLeaseDecision.TERMINAL` / `AttemptFencingReason.ATTEMPT_TERMINAL` 风格诊断，并断言 owner-lost signal、fence reason 与后台 renew task 无异常退出。

本 residual 的修复不需要生产行为变更；fix pass 只需要补 targeted 测试与测试文档同步。此次 re-review 未修改生产代码。

## Re-reviewed Finding

### renew/terminal race targeted supervisor coverage

- **source status**: accepted residual risk
- **fix status**: fixed
- **re-review status**: passed
- **直接证据**:
  - `tests/host/test_phase8_attempt_supervisor.py:1100` 新增 `test_renew_terminal_fence_after_terminal_close_marks_owner_lost`。
  - 测试使用 `_build_supervisor(...)` 构造真实 supervisor，并进入 `supervisor.lease_context(...)`，因此 renew loop 由 supervisor 自身启动。
  - `tests/host/test_phase8_attempt_supervisor.py:1121` 先调用 `supervisor.append_terminal_and_close(...)`，把当前 attempt 写入 terminal close。
  - `tests/host/test_phase8_attempt_supervisor.py:1127` 等待 `session.stopped_event`，确认 `_renew_loop` 已自然退出。
  - `tests/host/test_phase8_attempt_supervisor.py:1128` 调用 `supervisor.wait_owner_lost(owner_context)`，断言 owner-lost signal 可读。
  - `tests/host/test_phase8_attempt_supervisor.py:1134` 到 `tests/host/test_phase8_attempt_supervisor.py:1142` 断言 loss reason 是 `AttemptOwnerLossReason.FENCED`、`session.fence_reason` 是 `AttemptFencingReason.ATTEMPT_TERMINAL`、`renew_task.done()` 且 `renew_task.exception() is None`。
  - `dayu/host/_attempt_supervisor.py:1044` 到 `dayu/host/_attempt_supervisor.py:1050` 显示 `_renew_loop` 在事务内调用 `self.lease_store.renew(...)`。
  - `dayu/host/_attempt_supervisor.py:1090` 到 `dayu/host/_attempt_supervisor.py:1110` 显示非 `ACQUIRED` 结果被映射为 owner-lost `FENCED`，并保留 store 返回的 `reason`。
  - `dayu/host/_run_state_store.py:561` 到 `dayu/host/_run_state_store.py:624` 显示真实 `AttemptLeaseStore.renew()` 在 CAS miss 时进入 `_diagnose_fence(...)`。
  - `dayu/host/_run_state_store.py:1144` 到 `dayu/host/_run_state_store.py:1152` 显示 terminal attempt 状态被诊断为 `AttemptLeaseDecision.TERMINAL`，reason 为 `AttemptFencingReason.ATTEMPT_TERMINAL`。

## Production Behavior Change Check

未发现该 accepted residual 需要新的生产行为修改。测试覆盖的生产路径已经存在：`_renew_loop` 对 store 非 `ACQUIRED` 结果统一标记 owner-lost，真实 store 对 terminal attempt 返回 typed terminal fencing 诊断。fix artifact 记录的 changed files 也不包含生产代码。

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_tool_runtime_fencing.py -q`
  - 结果：通过，`56 passed in 0.51s`
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - 结果：通过，`4 passed in 1.62s`

## Findings

No findings.

## Open Questions And Residual Risk

- `renew/terminal race targeted supervisor coverage`: fixed in this fix pass.
- 未发现该 fix 引入新的 blocker。
- `production process supervisor`、`P9 lifecycle admission`、`special cursor facts` 仍按 fix artifact 记录保持在原 scope 外；本 re-review 未重新裁决这些非目标项。

## Stop Condition Status

- 未启动 `$gateflow` / `/gateflow`。
- 未重新做 plan。
- 未修改生产代码或测试代码。
- 未 commit、未 PR、未 closeout。
