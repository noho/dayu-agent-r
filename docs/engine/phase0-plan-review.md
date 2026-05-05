# Engine Phase 0 实施计划 Review

## 1. Review 结论

通过。

本轮复审对象为 `docs/engine/phase0-plan.md`。上一版 review 提出的三项重要问题与三项建议问题均已在计划中收口：Engine/Runner 的 `runner_done` data 命名已统一，所有 StrEnum 已补明确成员名/值表，`ToolResultMeta` / `ToolAwaitSpec` / `ToolAwaitSnapshot` / `RunResumeHint` 的开放 `attributes` 字段已移除，`await_kind` 已收窄为 `ToolAwaitKind`，`AgentMessage` union 测试不再依赖运行时 TypeAlias 行为，`JsonValue` 也明确只做类型别名、不提前承担 runtime validator 或序列化职责。当前计划可作为 Phase 0 实施依据；仍需总控/用户确认的事项属于实施前决策点，不再是计划阻塞。

## 2. 阅读范围

实际阅读的 NEW 文档：

- `docs/engine/phase0-plan.md`
- `docs/engine/phase0-plan-review.md`
- `docs/engine/design.md`
- `docs/engine/review.md`
- `docs/engine/migration-plan.md`
- `docs/engine/migration-plan-review.md`
- `AGENTS.md`
- `pyrightconfig.json`

实际核查的 OLD 源码：

- `~/workspace/dayu-agent/dayu/engine/tool_result.py`
- `~/workspace/dayu-agent/dayu/contracts/protocols.py`
- `~/workspace/dayu-agent/dayu/engine/events.py`

额外本地验证：

- 用 Python 3.11 验证过 PEP 604 union 形式可运行。
- 用 Python 3.11 验证过函数式 `StrEnum("system","user",...)` 不是可执行写法；当前计划已改为显式 class 成员表。

## 3. 阻塞问题

无。

复核要点：

- Phase 0 范围仍严格限定为 pure contracts、包根导出策略、import boundary tests 与 weak typing 防线。
- 未偷跑 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools、processors 或 tool calling 闭环。
- 未导出未实现的 `run_agent_messages` / `run_agent_and_wait`。
- `ToolExecutor` 仍只包含 `execute(request) -> ToolExecutionOutcome`。
- `AsyncRunner` 仍只是协议，不执行工具，不依赖 `ToolExecutor`。
- Engine contracts 仍全面禁止导入 `dayu.fins`。
- README 默认不创建，且明确不写未来路线图或 “待 Phase 1+” 内容。

## 4. 重要问题

无。

上一版重要问题复核结果：

- EngineEvent data 命名：第 1 节和第 6.4 节已统一为 Engine 侧 `RunnerDoneEngineData`、Runner 侧 `RunnerDoneData`。
- StrEnum 成员表：第 6.6 节已列出 `AgentMessageRole`、`FinishReason`、`OpenAIReasoningEffort`、`ToolAwaitKind`、`EngineEventType`、`RunnerEventType` 的成员名和值。
- attributes 弱类型语义袋：`ToolResultMeta`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`RunResumeHint` 已全部移除开放 `attributes` 字段。

## 5. 建议问题

无必须修改项。

上一版建议问题复核结果：

- `ToolAwaitSpec.await_kind` 已从 `str` 收窄为 `ToolAwaitKind`，Phase 0 只落地 `EXTERNAL_JOB = "external_job"`。
- `test_agent_message_union.py` 已明确针对四个具体 dataclass 做运行时 `isinstance`，不依赖 `AgentMessage` TypeAlias 的运行时行为。
- `JsonValue` 已明确 Phase 0 只落地类型别名，不实现 runtime validator 或序列化 helper，避免把后续 adapter 职责提前塞进 contracts。

## 6. 可接受风险

- `RunnerDoneEngineData` 命名仍需总控/用户最终接受。该命名已在计划内统一，不影响实施 Agent 按当前真源落地。
- `ToolAwaitKind.EXTERNAL_JOB` 是 Phase 0 保守初始集合。后续若需要更多等待类型，应由消费 Phase 单独评审扩展。
- `AgentMessage` 四元封闭联合是 Phase 0 最小形态。Phase 1 Runner 若发现不足，应按计划停止并回到总控确认，而不是在实现中自行扩字段。
- `correlation_id` 作为 `ToolExecutionContext` 中性关联字段可接受；后续不得变成 ToolTraceRecorder 私有入口。
- Phase 0 不创建 README 可接受；实施汇报需要说明原因。

## 7. 需要总控 / 用户确认的问题

- 是否接受 Engine 侧 runner done data 固定命名为 `RunnerDoneEngineData`。
- 是否接受 `ToolAwaitKind` Phase 0 仅落地 `EXTERNAL_JOB`。
- 是否接受 `AgentMessage` 四元封闭联合为 Phase 0 稳定最小形态。
- 是否接受 `correlation_id: str | None` 进入 `ToolExecutionContext`，且仅作为中性关联字段。
- 是否确认 Phase 0 全面禁止 Engine contracts 导入 `dayu.fins` 任意子模块。
- 是否确认 Phase 0 默认不创建 `dayu/engine/README.md`。

## 8. 总体验收判断

- 是否允许基于当前 Phase 0 计划开始实施？允许。
- 如果不允许，需要先修哪些部分？不适用；当前无阻塞和重要问题。
- 如果允许，Phase 0 的最小实施范围是什么？严格按 `docs/engine/phase0-plan.md` 第 1 / 2 / 5 / 6 / 7 节：只新建 `dayu/engine/contracts/` contract 类型、`dayu.engine.__all__` contract 导出白名单，以及 `tests/engine/` 架构与类型边界测试；不实现 Agent loop、Runner 实现、ToolRegistry、doc/web/fins tools、processors，不导出未实现函数式入口。
