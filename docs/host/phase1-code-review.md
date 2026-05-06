# Host P1 Code Review

## Review 范围

本轮审查 P1 代码实施 diff：

- `dayu/host/__init__.py`
- `dayu/host/contracts.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_worker.py`
- `dayu/host/_proxy.py`
- `dayu/host/_run_harness.py`
- `tests/host/`
- `dayu/host/README.md`
- `tests/README.md`
- `utils/smoke_engine_worker.py`

设计与计划依据：

- `docs/host/design.md`
- `docs/host/migration-plan.md`
- `docs/host/phase1-plan.md`

## 结论

P1 代码实现通过 code review gate。

当前实现满足 P1 目标：Host public `start_run` 可以通过内部
`LocalRunHarness -> LocalProxy -> EngineWorker -> dayu.engine.run_agent_messages`
调用 Engine 函数式入口，并将 EngineEvent 薄翻译为 RunEvent。`start_run` 会立即创建 P1 内存后台
任务，避免 lazy stream 造成后创建 run 先启动。普通 tool-call fake executor smoke 已通过内部
harness 覆盖，未把 ToolExecutor 暴露为 Host public API。P1 还新增
`utils/smoke_engine_worker.py` 作为人工 smoke，直接验证 EngineWorker 装配边界。

阻塞问题：无。

## Gate 检查

### 1. EngineWorker / ToolExecutor public boundary

结论：通过。

证据：

- `dayu.host.__all__` 只导出 Run 契约与 `start_run`。
- `tests/host/test_phase1_public_boundary.py` 明确断言 `EngineWorker`、`LocalProxy`、`ToolExecutor`、
  `run_agent_messages` 不在包根 `__all__` 中，也不能作为包根属性访问。
- `ToolExecutor` 只出现在 `dayu.host._worker.EngineWorker` 与 `dayu.host._run_harness` 内部装配中。

### 2. Host -> Engine 调用链路

结论：通过。

证据：

- `dayu.host._worker.EngineWorker` 将 `StartRunRequest` 强类型装配为 `AgentRunRequest`，调用
  `dayu.engine.run_agent_messages`。
- `tests/host/test_phase1_run_harness.py` 通过 monkeypatch Engine runner 构造，验证 public
  `start_run` 可以消费 Engine 事件并产出 Host `RunEvent`。

### 3. 普通 tool-call fake executor smoke

结论：通过。

证据：

- `tests/host/test_phase1_run_harness.py::test_local_harness_supports_tool_call_fake_executor_smoke`
  使用内部 `LocalRunHarness` 注入 fake ToolExecutor，覆盖 Runner tool call、工具执行、
  `TOOL_RESULT_ACCEPTED`、final answer 与 Host RunEvent stream。
- 该测试没有把 fake ToolExecutor 注入路径提升到 `dayu.host` public API。
- `utils/smoke_engine_worker.py` 复用真实 provider case 与 fake `add_numbers` ToolExecutor，供人工
  验证 EngineWorker wrapper；README 已明确该脚本不代表 public API。

### 4. EventLog / RunEventStore 边界

结论：通过。

证据：

- P1 只新增 `RunEventCursor(sequence)`，README 明确 cursor 只映射 Engine sequence，不具备持久补读语义。
- 代码没有新增 EventLog、RunEventStore、projection、memory、timeline 或 transcript 真源。

### 5. P7 governance 边界

结论：通过。

证据：

- `StartRunRequest` 暂不包含 `client_request_id`。
- README 明确未落地创建幂等、Session governance、同 Session active Run 仲裁、多进程治理。
- P1 只返回内存态 `RUNNING` handle，并由 Engine 终态事件映射终态结果。

### 6. Import boundary 与类型边界

结论：通过。

证据：

- `tests/host/test_import_boundary.py` 扫描 `dayu.host`，阻止 Host import `dayu.fins`、
  `dayu.service`、`dayu.ui`。
- 现有 `tests/engine/test_import_boundary.py` 继续阻止 Engine 反向 import Host。
- `tests/host/test_weak_typing_guard.py` 扫描 `dayu.host`，阻止 `Any`、`object`、无类型签名与裸容器注解。
- `python -m pyright` 通过。

### 7. README / tests 文档同步

结论：通过。

证据：

- `dayu/host/README.md` 已更新为 P1 当前事实，不写 EventLog、memory、production governance 等未落地能力。
- `tests/README.md` 已新增 `tests/host/` 分层、运行方式与维护边界。

## Findings

阻塞 finding 已修复。

### 1-已修复-高-`start_run` 返回 lazy async generator 会破坏排队 / 启动顺序语义

- 位置：`dayu/host/_run_harness.py`
- 问题：原实现中 `LocalRunHarness.start_run()` 只返回 `RunStream(events=self._stream_events(request))`。
  `_stream_events` 是 async generator，创建 generator 对象时不会执行函数体；只有调用方开始
  `async for` 消费时才会调用 `LocalProxy -> EngineWorker -> run_agent_messages`。
- 影响：如果多个 run 已被创建但事件流消费顺序不同，后创建的 run 可能先启动，破坏 Host
  `start_run` 的接纳 / 排队直觉，也不符合设计中“start_run 负责创建并启动或排队 Run”的语义。
- 修复：`LocalRunHarness.start_run()` 现在立即创建后台 task，后台 task 调用 worker 并把翻译后的
  `RunEvent` 写入内存队列；`RunStream.events` 只从队列消费。
- 验证：新增 `test_start_run_eagerly_starts_before_event_stream_is_consumed`，断言未消费
  `stream.events` 前 Runner 已被后台执行触发。

### 建议 1-低-P1 `RunEvent.data` 直接携带 Engine data 是临时契约，P1.5 需重新审查

用户已确认 P1 允许 `RunEvent.data` 直接携带 Engine event data 联合。当前 README 与 contracts
docstring 已说明这是 P1 最小翻译策略，不代表 Host timeline / EventLog 的最终 data contract。

修复状态：已在 `dayu/host/contracts.py` 与 `dayu/host/README.md` 标注边界。P1.5 继续审查。

## 验证结果

已运行：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts -q
python -m utils.smoke_engine_worker --help
python -m pyright
```

结果：

- pytest：32 passed。
- smoke help：命令行参数可解析。
- pyright：0 errors, 0 warnings, 0 informations。

## 用户人工 review 停止点

按 `docs/host/migration-plan.md`，P1 code review 通过后应停止，等待用户人工 review。
用户确认后，才能 commit P1 代码、测试与 README 更新。
