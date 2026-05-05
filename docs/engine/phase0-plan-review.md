# Engine Phase 0 实施计划 Review

## 1. Review 结论

通过。

本轮复审对象为 `docs/engine/phase0-plan.md`。计划已按最新契约归属范式收口：层间协作协议迁入 `dayu.contracts`，Engine 语义真源仍保留在 `dayu.engine.contracts`，并明确 `dayu.contracts` 禁止反向依赖 Engine / Host / Service / UI / fins。取消边界也已修正为只公开 `CancellationToken`，不导出 `CancelledError`，公共取消终态仍由 `RunCancelledData` / `EngineRunOutcomeCancelled` 表达。当前未发现阻塞或重要问题，可作为 Phase 0 实施依据。

## 2. 阅读范围

实际阅读文件：

- `docs/engine/phase0-plan.md`
- `docs/engine/phase0-plan-review.md`
- `docs/engine/migration-plan.md`
- `docs/engine/migration-plan-review.md`
- `docs/engine/design.md`
- `AGENTS.md`

重点补读范围：

- `docs/engine/design.md` 第 9 节取消 / 事件边界
- `docs/engine/design.md` 第 14 节接口草案
- `docs/engine/design.md` 第 16 节迁移计划草案

## 3. 阻塞问题

无。

## 4. 重要问题

无。

## 5. 建议问题

无必须修改项。

可选建议：后续实现时建议在 `dayu/engine/__init__.py` 的模块 docstring 中继续写清楚 `dayu.contracts` 是共享协议的 canonical home，`dayu.engine` 对其 re-export 是 Engine API surface 的结构导出，不是兼容旧路径的 facade。

## 6. 契约归属专项结论

- `dayu.contracts` 收纳范围是否合理？
  - 合理。计划把 `CancellationToken`、`ToolExecutor`、`ToolCallRequest`、`ToolExecutionRequest`、`ToolExecutionContext`、`ToolSchema`、`ToolResultEnvelope`、`ToolExecutionOutcome`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`JsonValue` 放入 `dayu.contracts`。这些类型不是 Engine 单方调用参数，而是 Host 与 Engine 都需要独立产生、解释或持久化的协作协议。

- `dayu.engine.contracts` 保留范围是否合理？
  - 合理。`RunnerSpec`、`RunnerCallOptions`、`AgentRunRequest`、`AgentPolicy`、`AgentMessage`、`EngineEvent`、`RunnerEvent`、`AgentRunResult`、`FinishReason` 等仍留在 `dayu.engine.contracts`，符合 Engine 语义真源原则。Host 会 import 这些类型不构成把它们下沉到 `dayu.contracts` 的理由。

- `RunnerSpec` 是否正确保留在 Engine 契约？
  - 是。`RunnerSpec` / `RunnerCallOptions` 描述 Engine 内 Runner 规约与调用选项，语义真源在 Engine；Host 只是装配并传入，不独立解释为 Host 协作协议。

- `CancellationToken` 是否正确迁入公共契约？
  - 是。`CancellationToken` 是 Host 产生 / 激活、Engine 观察的层间协作协议，迁入 `dayu.contracts` 合理。同时计划明确不导出取消异常，取消公共终态由 `RunCancelledData` / `EngineRunOutcomeCancelled` 表达，符合 `design.md` 的结构化取消边界。

- 是否仍存在会诱导 Agent 误判共享契约的表述？
  - 当前计划已把判断依据写成“语义真源归属”和“是否为真正层间协作协议”，没有再用“被多个层 import”作为归属依据。`dayu.engine.__init__` re-export `dayu.contracts` 符号有轻微误读风险，但计划 §1.3 已说明这是结构契约导出，不是兼容 wrapper；可接受。

## 7. 可接受风险

- `dayu.engine.__init__` re-export `dayu.contracts` 全部符号：可接受。它让 Engine 调用方有单一 API surface，但需保持 `dayu.contracts` 为 canonical home，并通过测试保证 `dayu.contracts` 不 import `dayu.engine`。
- `ToolAwaitKind.EXTERNAL_JOB` 是 Phase 0 保守初始集合：可接受。后续新增等待类型必须由消费 Phase 单独评审。
- `AgentMessage` 四元封闭联合是 Phase 0 最小形态：可接受。Phase 1 Runner 若发现不足，应按计划停止并回到总控确认。
- `ToolExecutionContext.correlation_id` 进入公共契约：可接受，但后续不得演变成 ToolTraceRecorder 私有入口。
- README 默认不创建：可接受。Phase 0 仍是 contract 与边界测试切片，无用户向能力变化。

## 8. 需要总控 / 用户确认的问题

- 是否接受 §0 / §1.1 / §1.2 的契约分层范式与具体落点。
- 是否接受 `dayu.engine.__init__` 对 `dayu.contracts` 符号做结构导出。
- 是否接受 Engine 侧 runner done data 固定命名为 `RunnerDoneEngineData`。
- 是否接受 `ToolAwaitKind` Phase 0 仅落地 `EXTERNAL_JOB`。
- 是否接受 `AgentMessage` 四元封闭联合为 Phase 0 稳定最小形态。
- 是否接受 `ToolExecutionContext.correlation_id: str | None` 作为中性关联字段。
- 是否确认 Phase 0 全面禁止 `dayu.fins` 任意子模块导入。
- 是否确认 Phase 0 默认不创建 `dayu/contracts/README.md` / `dayu/engine/README.md`。

## 9. 总体验收判断

- 是否允许基于当前 `docs/engine/phase0-plan.md` 开始 / 继续 Phase 0 实施？允许。
- 如果不允许，需要先修哪些章节？不适用；当前无阻塞和重要问题。
- 如果允许，Phase 0 最小实施范围是什么？按当前计划只落地 `dayu.contracts` 与 `dayu.engine.contracts` 的 pure contracts、`dayu.contracts.__all__` / `dayu.engine.__all__` 导出白名单、`tests/contracts/` 与 `tests/engine/` 的 import boundary / weak typing / protocol surface / event-outcome 封闭测试；不实现 Runner、Agent loop、ToolRegistry、doc/web/fins tools、processors，不导出 `run_agent_messages` / `run_agent_and_wait` / `AsyncAgent` / `AsyncOpenAIRunner`，不导出任何取消异常。
