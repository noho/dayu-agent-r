# P8.5 Slice 5b Fix Report

- **work gate name**: fix
- **work unit**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **assigned slice**: Slice 5b — Attempt Lease / Recovery Adversarial Hardening
- **source review artifact**: `docs/host/phase8.5-s5b-code-review.md`
- **implementation artifact**: `docs/host/phase8.5-s5b-implementation-report.md`
- **artifact path**: `docs/host/phase8.5-s5b-fix-report.md`

## Controller-Accepted Finding

- **accepted residual / finding id**: `renew/terminal race targeted supervisor coverage`
- **controller decision**: accepted residual risk; requires targeted supervisor coverage for `_renew_loop` receiving terminal / attempt-terminal style fencing after terminal close or terminal race.
- **fix status**: fixed.

## Fix Summary

新增一个窄 supervisor-level adversarial test，直接覆盖真实 `AttemptSupervisor._renew_loop` 在 attempt 已经通过 terminal close 收口后继续 renew，并由真实 `AttemptLeaseStore.renew()` 诊断为 `AttemptLeaseDecision.TERMINAL` / `AttemptFencingReason.ATTEMPT_TERMINAL` 的路径。

测试断言：

- `wait_owner_lost()` 返回 typed `AttemptOwnerLossReason.FENCED`。
- session 记录的 `fence_reason` 为 `AttemptFencingReason.ATTEMPT_TERMINAL`。
- renew background task 已退出，且 `exception()` 为 `None`，没有泄漏后台 task 异常。

未修改生产代码；该测试未暴露新的生产缺陷。

## Changed Files

- `tests/host/test_phase8_attempt_supervisor.py`
  - 新增 `_host_run_failed_draft()` 测试 helper。
  - 新增 `test_renew_terminal_fence_after_terminal_close_marks_owner_lost()`。
- `tests/README.md`
  - 同步 P8-S3 attempt supervisor 测试覆盖点。
- `docs/host/phase8.5-s5b-fix-report.md`
  - 本 fix gate durable artifact。

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_tool_runtime_fencing.py -q`
  - 结果：通过，`56 passed in 0.51s`
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - 结果：通过，`4 passed in 1.62s`

## Documentation Decision

已更新 `tests/README.md`。原因：本 fix 修改了 `tests/host/test_phase8_attempt_supervisor.py` 的覆盖面，且该 README 当前职责包含测试分层、运行方式与维护规则；同步只记录当前已存在的测试覆盖点，不引入未来设计。

未更新 Host README 或其它 README。原因：本 fix 只补 supervisor 内部 adversarial 测试与测试手册，不改变 Host 对外接口、架构边界、运行命令、配置入口或用户可见行为。

## New Risks / Open Questions

- 未引入新的 open question。
- 未引入生产代码变更风险。

## Residual Risks

- `renew/terminal race targeted supervisor coverage`: fixed in this fix pass.
- `production process supervisor`: remains deferred to later phase / work unit; outside accepted fix scope.
- `P9 lifecycle admission`: remains deferred to later phase / work unit; outside accepted fix scope.
- `special cursor facts`: remains non-goal; no cursor / truncation / fetch_more special RunEvents were restored.

## Stop Condition Status

- 未处理 rejected / deferred findings。
- 未启动 Slice 6。
- 未 commit、未 PR、未 closeout。
