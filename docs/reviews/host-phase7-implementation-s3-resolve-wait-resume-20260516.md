# Host Phase 7 P7-S3 Implementation - resolve_wait Command And Resume Attempt

日期：2026-05-16

## 完成状态

已完成 P7-S3 implementation。

## 变更摘要

- `dayu/host/command.py`：`resolve_wait` 从 stable unsupported 改为打开 handle 校验后调用 durable wait resolution service；completed / tool-cancelled resume commit 后唤醒 dispatch scheduler。
- `dayu/host/waiting.py`：新增 `DefaultHostResolveWaitService`，实现 `(wait_id, idempotency_key)` 幂等、同 key digest 冲突检测、resolved/failed/lost 终态重放、waiting 状态下 completed/cancelled/failed/lost 四类 outcome 分流。
- `dayu/host/durable/run_transition.py`：新增 `resume_run_from_waiting_in_transaction`、`fail_run_from_waiting_in_transaction`、`mark_run_lost_from_waiting_in_transaction`，确保 wait record CAS、EventLog facts、Run/Attempt/dispatch mutation 在同一 transaction 内完成。
- `dayu/host/durable/state.py`：新增 `resume_waiting_run_row`，以 `WAITING + suspended_attempt_id` 为 CAS 前置恢复 Run 到 `RUNNING` 并切换 current Attempt。
- `dayu/host/_event_payload.py`：新增 `resume_requested_payload` 与 `tool_result_wait_resolution_payload`。
- `dayu/host/run_input.py`：resume Attempt 构造输入时从当前 `RUN_STARTED(start_reason=resume)` 引用的 `TOOL_RESULT_ACCEPTED` 重建 accepted wait/tool fact system message。
- `tests/host/test_resolve_wait_command.py`：覆盖 completed resume、幂等重放、幂等冲突、failed/lost closeout、lost 终态重放、tool-cancelled resume。
- `tests/host/test_resolve_wait_command.py`：补充 resume dispatch 到 Engine request 的 RunInputBuilder continuity 断言。
- `tests/host/test_phase7_waiting_integration.py`：补齐 P7-S3 指定集成测试入口。
- `tests/host/test_public_run_api.py`：移除 `resolve_wait` 旧 stable unsupported 断言，保留 retry / replay / purge deferred unsupported 覆盖。
- `dayu/host/README.md`、`tests/README.md`：同步当前 resolve wait / resume 行为与测试覆盖事实。

## 非目标确认

- 未修改 Engine、contracts、fins/service/ui、remote transport、projection/memory/context/recovery/outbox/audit/tool trace read-model。
- 未实现 poller、callback endpoint、WAITING cancel、late diagnostic、Engine ingest 行为变更。
- 未提交、未 push、未创建 PR。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q`
  - 结果：`64 passed`
- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py -q`
  - 结果：`6 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`381 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## 风险与未覆盖

- P7-S4 范围的 late result diagnostic、cancel-vs-resolve race 与 CAS_LOST 并发压力测试未实现。
