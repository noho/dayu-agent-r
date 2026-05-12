# Gateflow Implementation Artifact: Engine Design Doc Sync

- **work gate name**: implementation
- **work-unit name**: 将 Engine 文档对齐到当前代码，以代码为准
- **assigned slice id**: engine-design-doc-sync
- **artifact path**: `docs/reviews/gateflow-implementation-engine-design-doc-sync-20260512.md`

## Assigned Scope

- **允许修改文件**: `docs/engine/design.md`
- **允许 artifact 文件**: `docs/reviews/gateflow-implementation-engine-design-doc-sync-20260512.md`
- **显式非目标**: 不修改 `dayu/engine/README.md`、不修改代码、不新增未来设计、不写过程状态、不越过 Engine 文档职责，不改 Host/runtime/Fins 文档。

## Motivation And Direct Evidence

动机成立。`docs/engine/design.md` 的主体已经描述当前 Engine，但存在几处与代码真源不够精确或遗漏的文档事实，属于 Engine 设计说明职责范围。

直接证据：

- `tests/engine/test_package_exports.py:11` 与 `tests/engine/test_package_exports.py:106` 锁定 `dayu.engine.__all__`：包根导出 Engine 契约和调用 Engine 需要的共享工具/取消契约，同时禁止 `_AsyncAgent`、`AsyncOpenAIRunner`、取消异常等实现细节泄漏。
- `dayu/engine/contracts/runner_spec.py:237`、`dayu/engine/contracts/runner_spec.py:260`、`dayu/engine/contracts/runner_spec.py:264` 与 `dayu/engine/contracts/runner_spec.py:268` 表明 `supports_stream_usage`、`stream_idle_timeout_seconds`、`stream_idle_heartbeat_seconds` 是当前 RunnerSpec 契约，并有正数与 heartbeat 不超过 timeout 的校验。
- `tests/engine/test_runner_event_contract.py:54` 与 `dayu/engine/contracts/runner_events.py:220` 表明 `RunnerEvent` 是可测试的 Runner 契约，字段不含 `session_id` / `run_id`；`run_agent_messages` 的对外事件流仍是 `EngineEvent`。
- `dayu/engine/agent.py:1445`、`dayu/engine/agent.py:1479`、`dayu/engine/agent.py:1491` 和 `tests/engine/test_agent_phase3_tool_call.py:1339` 表明 ToolExecutor 普通异常会归一为 `ToolFailedOutcome(error="tool_executor_exception")`；`asyncio.CancelledError` 只有在 run cancellation token 已取消时才进入取消终态。
- `dayu/contracts/tool_schema.py:75`、`dayu/contracts/tool_schema.py:85` 与 `dayu/engine/__init__.py:188` 表明 `ToolTruncationStrategy` / `ToolTruncateSpec` 的真源在 `dayu.contracts`，且不属于 `dayu.engine` 包根导出的稳定调用面。

## Changed Files

- `docs/engine/design.md`
- `docs/reviews/gateflow-implementation-engine-design-doc-sync-20260512.md`

注意：工作树中存在 `dayu/engine/README.md` 的未提交差异，但该文件不在本 handoff 允许范围内，本次未修改、未纳入 changed files。

## Implemented Items

- 补充 `dayu.engine` 包根导出边界：导出函数式入口、Engine 契约和必要共享契约，但不导出 `_AsyncAgent`、`AsyncOpenAIRunner` 等实现类。
- 补充 `RunnerSpec.supports_stream_usage` 的 provider 字段门控语义。
- 补充 `stream_idle_timeout_seconds` 与 `stream_idle_heartbeat_seconds` 的当前契约与校验规则。
- 将 `RunnerEvent` 从“完全不跨 Engine 外部调用边界”的过强表述改为“Runner 到 Agent 的协议归一事件契约”：可供 Runner 实现和契约测试使用，但不是 `run_agent_messages` 的输出事件流。
- 补充 `ToolExecutor.execute` 普通异常与 `asyncio.CancelledError` 的当前归一规则。
- 澄清 `ToolTruncateSpec` / `ToolTruncationStrategy` 属于 `dayu.contracts`，不是 Engine 包根稳定导出；Engine 不执行工具结果截断。

## Not Implemented

- 未修改 `dayu/engine/README.md`：该文件是显式非目标，且可能由另一个 slice/Agent 负责。
- 未修改代码或测试：本 slice 是文档对齐，代码真源无需变更。
- 未新增未来设计或计划性内容：所有修改均来自当前代码与测试事实。

## Validation

- `source .venv/bin/activate && python -m pytest tests/engine -q`
  - 结果：通过，`303 passed in 1.07s`。
- `source .venv/bin/activate && pyright dayu/engine tests/engine`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。

## Documentation Decision

已更新 `docs/engine/design.md`，因为本 slice 的目标就是 Engine 设计文档对齐。未更新 README：`dayu/engine/README.md` 不在本 assigned scope 内，且用户明确禁止本 handoff 修改它。

## Plan Gaps Or Controller Decisions

无阻塞缺口。本 handoff 是用户指定的直接 implementation，没有 approved plan artifact；本次按用户最新指令只执行目标文档同步。

## Residual Risks And Uncovered Areas

- `accepted as covered by a later slice in the approved plan`: `dayu/engine/README.md` 当前工作树存在差异，但属于另一个目标文档/Agent 范围，本 slice 不处理。
- `requiring a new issue or explicit user decision`: 无。
- `fixed in the current slice before review`: 已修正 `docs/engine/design.md` 中与当前代码不够精确的 RunnerEvent、RunnerSpec、ToolExecutor 与 ToolTruncateSpec 表述。

## Completion Signal

- `docs/engine/design.md` 已按当前 Engine 代码和测试事实完成窄范围对齐。
- 指定测试与 pyright 均通过。
- 未修改非目标文件，未提交、未 push、未创建 PR。

## Stop Condition Status

当前 assigned slice 已完成，可以交回 controller 进入 review gate。不阻止另一个 slice 启动。
