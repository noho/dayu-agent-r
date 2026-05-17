# P9.5 S4 Host Durable Helper API Tightening Implementation

## 范围

- Gate：P9.5 S4 Host Durable Helper API Tightening implementation。
- 分支：`p9.5-pre-p10-hardening`。
- 计划来源：`docs/host/p9-5-pre-p10-hardening-plan.md` 的 S4。

## 动机判断

S4 动机成立。直接证据是 `mark_dispatching_after_lane_row` 允许 `PENDING` dispatch record 在拿到 lane 后直跳 `DISPATCHING`，绕过了生产 scheduler 的 `WAITING_FOR_LANE` 诊断阶段；`accept_worker_running_in_transaction` 的 `ATTEMPT_RUNNING` payload 也少于 scheduler 生产路径中的 worker/lane accept 诊断字段。

## 变更文件

- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_run_input_builder.py`
- `docs/reviews/p9-5-s4-host-durable-helper-tightening-implementation-20260517.md`

## 实现内容

- 收紧 `mark_dispatching_after_lane_row`：只接受已经处于 `WAITING_FOR_LANE` 的 dispatch record，不再允许 `PENDING` 直跳 `DISPATCHING`。
- 在 dispatching helper 内增加同事务 fail-closed 前置检查：Run 必须 `RUNNING`、Run current Attempt 必须匹配、Attempt 必须 `STARTING`、Attempt 与 dispatch record 的 execution id 必须一致、dispatch owner/lane waiting 诊断必须存在且匹配、claim/dispatching/worker/cancel refs 必须尚未写入。
- 调整 scheduler durable recheck：只把 `WAITING_FOR_LANE` 视为可 dispatch，避免生产 caller 继续依赖 direct pending path。
- 收紧 `accept_worker_running_in_transaction`：worker accept 前校验 run/attempt/dispatch/execution/lane/owner/worker/cancel 前置完整一致。
- 让 `accept_worker_running_in_transaction` 的 `ATTEMPT_RUNNING` payload 补齐 scheduler production path 对齐的 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id` 诊断字段。
- 更新白盒测试：移除 pending direct dispatching 期望，改为验证 pending bypass 被拒绝；scheduler 测试改为先进入 `WAITING_FOR_LANE` 再 dispatching，并新增未 waiting 时被跳过的行为测试；相关 ToolRuntime / resolve / cancel / RunInputBuilder fixture 补齐 production-like lane waiting / dispatching 诊断输入。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_resolve_wait_command.py tests/host/test_public_cancel_session_runs.py`
  - 结果：67 passed。
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py`
  - 结果：26 passed。
- `source .venv/bin/activate && pytest tests/host`
  - 结果：500 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无输出。
- 额外受影响测试：`source .venv/bin/activate && pytest tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py`
  - 结果：10 passed。

## 文档决策

已检查 `dayu/host/README.md` 与 `tests/README.md`。现有文档已经描述 scheduler 路径为 `pending -> waiting_for_lane -> dispatching`，未保留 pending direct dispatching 语义；测试手册的分层说明仍匹配当前覆盖范围。本次不需要修改 README。

## 残余风险

- `AcceptWorkerRunningInput.local_worker_id` 保持内部字段，未导出 public facade；非本地或旧白盒调用可为 `None`，但生产等价测试已按 scheduler payload 补齐该字段。
- 未新增状态、schema、public facade、compat wrapper 或 P11 `RECOVERING` 语义。
- 未触碰允许范围外的生产模块；未 commit、未 push、未创建 PR，未进入 review gate。

## 停止状态

S4 implementation 完成。
