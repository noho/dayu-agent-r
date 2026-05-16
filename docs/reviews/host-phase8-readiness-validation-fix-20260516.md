# Host Phase 8 Readiness Validation Fix - 2026-05-16

## Gate

当前 gate：Phase 8 ready-to-open-draft-PR 前最终验证。

输入：

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/host/phase8-projection-core-event-stream-plan.md`
- Phase 8 aggregate fix / re-review artifacts

## Failure

最终完整 Host 测试复现失败：

```bash
pytest tests/host -q
```

失败用例：

- `tests/host/test_dispatch_scheduler.py::test_scheduler_uses_toolruntime_when_tooling_is_configured`

现象：

- 测试在 `scheduler.drain_once()` 后手工调用 `request.tool_executor.execute(...)`。
- `ToolRuntime` 业务 callable 已被调用一次。
- Host accept barrier 返回 `tool_accept_rejected`，hint 为 `accept_rejected:invalid_attempt`。

## Root Cause

该测试使用默认 `_FakeHandle`，其 `events()` 是空异步事件流。调度器在 worker accept 后会立即启动 active task 消费
EngineEvent stream；空事件流会被 production scheduler 映射为 clean EOF terminal closeout。此时 Run / Attempt 不再满足
ToolRuntime accept precondition，accept barrier 拒绝工具事实是正确行为。

因此失败根因不是 ToolRuntime accept barrier 或 Phase 8 projection 逻辑错误，而是测试夹具在断言 tool-enabled wiring 时没有保持
Attempt 处于 `RUNNING`。测试应模拟 live worker 在执行工具调用期间仍未 terminal，而不是在 worker stream 已 EOF 后再执行工具。

## Fix

修复范围：

- `tests/host/test_dispatch_scheduler.py`

修复内容：

- 为 `_FakeWorkerFactory` 增加 `accepted_handle` 测试注入能力。
- `_AcceptingWorker` 在记录 snapshot / request 后可返回指定 handle。
- `test_pending_waiting_dispatching_worker_accept_marks_running` 与
  `test_scheduler_uses_toolruntime_when_tooling_is_configured` 使用 `_CloseCountingHandle`，让 worker stream 在 scheduler close
  前保持打开，避免与 clean EOF terminal closeout 竞争。

## Validation

```bash
source .venv/bin/activate
pytest tests/host/test_dispatch_scheduler.py::test_scheduler_uses_toolruntime_when_tooling_is_configured tests/host/test_dispatch_scheduler.py::test_pending_waiting_dispatching_worker_accept_marks_running -q
pytest tests/host -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

结果：

- targeted dispatch tests：2 passed
- Host tests：435 passed
- pyright：0 errors, 0 warnings, 0 informations
- diff check：clean

## Residual Risk

无新增生产风险。该修复只调整测试夹具，不改变 Host runtime、ToolRuntime、dispatch、projection 或 public API 行为。
