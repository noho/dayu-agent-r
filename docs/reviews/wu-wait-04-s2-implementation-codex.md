# WU-WAIT-04 S2 Implementation Report - AgentCodex

## Artifact

- `docs/reviews/wu-wait-04-s2-implementation-codex.md`

## Changed Files

- `tests/service/test_entrypoint_runtime_awaiting_smoke.py`
- `tests/README.md`
- `docs/reviews/wu-wait-04-s2-implementation-codex.md`

未修改 `docs/host/issues-implementation-control.md`；该文件在本 slice 开始前已有 controller dirty update。

## Behavior Implemented

- 新增 production-grade Service entrypoint awaiting smoke。
- 测试直接构造 public `OpenHostOptions`，包含 deterministic worker factory、等待型业务工具 bundle、wait binding registry、wait poll adapter registry，以及显式启用的短间隔 `WaitPollerRuntimePolicy`；未改变生产默认值。
- 第一轮 worker 通过 public `AgentRunRequest.tool_executor.execute(BatchToolExecutionRequest(...))` 发起工具执行握手；Host 工具治理真实执行等待型业务工具并接受 awaiting outcome，使 Run 进入 `WAITING`。
- 第一轮 worker 只用 public `LocalWorkerHandle.events() -> AsyncIterator[EngineEvent]` 协议把 public `TOOL_AWAITING` / `RUN_SUSPENDED` 事件载荷交回 Host；未导入或调用 private Engine agent implementation。
- 恢复后的第二轮 worker 通过同一 public worker event 协议返回 public final answer event。
- poll adapter 通过 production `WaitPollAdapterRegistry` 注册，并由实例内 `asyncio.Event` gate 控制：
  - gate 打开前返回 `WaitPollNotReady`；
  - Service activity 与 public `host.get_run(...)` 均观察到等待态后才打开 gate；
  - gate 打开后返回 `WaitPollReady(ResolveWaitCompletedOutcome(...))`，由 background poller 进入 Host common wait recovery pipeline。
- `submit_entrypoint_turn_and_wait` 使用 `on_run_accepted` 记录 accepted run id，使用 `on_activity` 观察 `EntrypointActivityStatus.WAITING`。
- smoke 断言：
  - public Run snapshot 曾为 `RunStatus.WAITING`；
  - Service submit 返回 `EntrypointTerminalSource.LIVE_EVENT`；
  - terminal run id 与 accepted run id 相同；
  - terminal status 为 succeeded；
  - final answer 非空；
  - deterministic worker 接受两次运行，poll adapter ready 一次；
  - terminal 后通过 public `host.read_outbox_terminal_items(session_id, ReadOutboxTerminalItemsRequest(...))` 补读到同一 run 的 terminal item。

## Validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: passed, `1 passed, 3 warnings`.
  - Warnings: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: passed, `55 passed, 3 warnings`.
  - Warnings: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- Forbidden-path grep:
  - Command: `rg -n "from dayu\.host\.durable|import dayu\.host\.durable|from dayu\.host\.tool_runtime|import dayu\.host\.tool_runtime|open_host_durable_store|read_active_wait_records_for_run|read_wait_record_by_id|ResolveWaitRequest|WaitResolutionSource\.MANUAL|resolve_wait\(|ToolRuntime|dispatch row|scheduler|dayu\.engine\.agent|_AsyncAgent" tests/service/test_entrypoint_runtime_awaiting_smoke.py`
  - Result: no matches.
- `git diff --check`
  - Result: passed.

## README Decision

已读取 `tests/README.md` 的 Agent 更新约束。新增 `tests/service/test_entrypoint_runtime_awaiting_smoke.py` 改变了 `tests/service/` entrypoint runtime 覆盖事实，因此已在 `tests/README.md` 的 Service 分层条目中最小追加 production awaiting smoke 覆盖说明。

未更新其它 README。S2 未修改生产代码、用户可见 CLI/Web/WeChat workflow、命令参数、默认输出通道、分层关系或 durable schema。

## Public-contract-only Enforcement

- 测试主体只使用 public `open_host(options)`、`ensure_session`、Service `submit_entrypoint_turn_and_wait`、`on_run_accepted`、`on_activity`、`host.get_run(...)` 与 `host.read_outbox_terminal_items(...)`。
- 等待恢复只通过 production wait poller policy 与 public wait poll adapter registry 触发。
- 未导入 `dayu.engine.agent`，未使用 `_AsyncAgent` 或其它 private Engine agent path。
- `EngineEvent` 只用于 public `LocalWorkerHandle.events` 协议的返回类型和载荷，以便 Host public opener 消费 worker output；测试不对 Engine events 做行为断言，所有行为断言仍在 Host / Service public API 层完成。
- 未读取 durable wait rows、dispatch rows、scheduler internals、ToolRuntime internals。
- 未使用测试私有 wait id bridge。
- 未调用 manual resolve。
- 新测试文件通过 forbidden-path grep，无命中。

## Residual Risks / Uncovered Areas

- S2 使用 deterministic business tool 与 deterministic poll adapter，验证 UI / Service public workflow 与 production poller runtime，不覆盖真实 Fins ingestion provider 的外部系统状态转换；真实 Fins poll adapter assembly 已由 S1 / existing service assembly tests 覆盖。
- 当前 smoke 不覆盖 callback endpoint path；accepted plan 明确选择 poller path，因为 ordinary UI / Service path 没有 public wait id discovery contract。
- 测试依赖短 poll interval 和 bounded timeout；gate 在 public WAITING 观察后才打开，降低提前恢复造成的 flake 风险。

## Blocker

未发现 public contract blocker。S2 可在不读取内部 wait storage、不调用 manual resolve、不修改生产代码的前提下完成。
