# Engine 设计文档 Review

## 1. Review 结论

通过。

当前 `docs/engine/design.md` 已能作为后续 Engine 最小迁移切片的设计依据。上一轮要求修正的 tool calling 控制流、事件命名、metadata 边界、`ToolAwaitSpec` 归属和 `ToolExecutionContext.trace_identity` 残留问题均已收口。

## 2. 阅读范围

NEW 文件：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/engine/review.md`

OLD Engine 文件：

- `dayu/engine/protocols.py`
- `dayu/engine/events.py`
- `dayu/engine/async_agent.py`
- `dayu/engine/async_openai_runner.py`
- `dayu/engine/tool_registry.py`
- `dayu/engine/tool_result.py`
- `dayu/engine/tool_trace.py`
- `dayu/engine/truncation_manager.py`
- `dayu/engine/context_budget.py`
- `dayu/engine/cancellation.py`
- `dayu/engine/__init__.py`
- `dayu/engine/tools/doc_tools.py`
- `dayu/engine/tools/web_tools.py`
- `dayu/engine/processors/base.py`

OLD Fins / contracts 文件：

- `dayu/contracts/protocols.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/tools/service.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/toolset_registrars.py`

## 3. 阻塞问题

本轮未发现阻塞问题。

已确认上一轮阻塞项和重要项的处理结果：

- Tool calling 控制流已统一：`tool_call_requested` 是观测事件，Engine/Agent 通过 Host 注入的 `ToolExecutor.execute(request)` 调用工具，Host 不因该事件另行触发工具执行。
- `ToolExecutor` 已收窄为最小协议：Engine 只依赖 `execute(request) -> ToolExecutionOutcome`，`tool_schemas` 由 `AgentRunRequest` 单独提供。
- 第一阶段 `ToolExecutionOutcome` 已收敛为 `completed | failed | awaiting`，其它治理分支进入 issue #4 子 issue。
- EngineEvent / RunnerEvent 已统一事件命名，并列出封闭 data 类型草案。
- 显式契约事实已要求进入强类型 data；metadata 只允许承载非契约 debug / sampling / observer hint，并要求严格 JSON value union。
- `ToolAwaitSpec` 已明确只能作为 `ToolAwaitingOutcome` 显式字段返回，不进入普通 `ToolResultEnvelope.meta`。
- `trace_identity` 已从工具执行上下文中移除，改为可选中性 `correlation_id`，且声明不是 ToolTraceRecorder 依赖。

## 4. 重要问题

本轮未发现必须阻止迁移计划进入下一阶段的重要问题。

## 5. 建议问题

### 5.1 contracts 落地时继续收紧“草案”到代码真源

- 严重级别：建议
- 位置：`docs/engine/design.md` 第 9 节、第 14 节、第 16 节
- 问题说明：文档已经给出事件表和协议草案。下一阶段实现时，应避免出现“文档一套、代码一套”的二次漂移。
- 建议修改方向：在 pure contracts 切片中先落地事件枚举、data 类型、outcome 联合类型和 import boundary 测试；后续 `AsyncAgent` / `AsyncOpenAIRunner` 迁移只能依赖这些 contract 真源。

### 5.2 `correlation_id` 保持可选且中性

- 严重级别：建议
- 位置：`docs/engine/design.md` 第 8 节
- 问题说明：`correlation_id` 的表述已比 `trace_identity` 更符合边界，但实现时仍要防止它被重新用作 trace recorder 私有入口。
- 建议修改方向：类型上保持 `str | None`，语义只用于跨 Host observer / ToolRuntime 的中性关联；trace、审计、UI 展示需要的事实优先通过 `session_id`、`run_id`、`iteration_id`、`tool_call_id`、EngineEvent sequence 建立关联。

### 5.3 README 同步放到实际迁移切片验收

- 严重级别：建议
- 位置：`docs/engine/design.md` 第 16 节
- 问题说明：当前仍是设计文档阶段，不需要为 review 本身同步 README。但后续修改 `dayu/engine/`、Host/Engine 装配边界或公共入口时，必须按 `AGENTS.md` 的 README 触发规则更新对应文档。
- 建议修改方向：在每个实现切片验收 checklist 中加入 README 检查项，尤其是 `dayu/engine/README.md` 和涉及分层边界时的 `dayu/README.md` / `dayu/host/README.md`。

## 6. 可接受风险

- Runner 不执行工具、只归一模型协议：可接受。OLD `AsyncOpenAIRunner` 确实在 `_emit_tool_batch` / `_run_tool_call` 中执行工具，这是 NEW 必须重设的边界。后续验证点是 Runner 测试必须证明 tool call 只产出 `RunnerEvent`，不依赖 `ToolExecutor`。
- ToolRegistry / ToolRuntime 归 Host：可接受。OLD `ToolRegistry` 同时承担注册、schema 校验、路径白名单、执行、截断、fetch_more 和 middleware，迁到 Host ToolRuntime 符合 Host 治理真源。后续验证点是 Engine 包不能导入 Host ToolRegistry、web/doc/fins tools。
- 第一阶段只落地 `completed | failed | awaiting`：可接受。其它治理分支转入 #4 子 issue 后，可以避免 Engine 初始 contract 过早绑定 Host task ledger、审批、artifact、去重等机制。
- processors/doc/web 不进入 core Engine：可接受。OLD 源码证明这些是文档解析、文件工具和联网工具能力，不是 Agent/Runner 核心原语。后续验证点是 `Source`、`DocumentProcessor`、`ProcessorRegistry` 不出现在 Engine / Host 公共边界。
- OLD `_compact_messages` 不作为稳定 Engine 能力：可接受。OLD 实现是确定性应急压缩，不是 conversation memory。后续验证点是 Engine 若保留 emergency fallback，不能写回 memory，也不能调用 LLM 做语义压缩。
- OLD `tool_trace_v2` 仅作为 Host observer 实现素材：可接受。NEW Engine 只承诺产出足够重建 trace 的强类型事件事实，不把 trace schema 纳入 Engine 稳定接口。

## 7. 需要用户/总控确认的问题

- 下一阶段是否按 `docs/engine/design.md` 第 16 节的顺序进入 pure contracts 切片。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 最终归属是 Fins capability 内部、通用 document capability 内部，还是单独 contract 包。当前 Engine 设计只要求它们不进入 Engine / Host 公共边界。

## 8. 总体验收判断

- 是否允许基于当前 design.md 进入迁移计划阶段？允许。
- 如果不允许，需要先修哪些章节？无。
- 如果允许，下一阶段最小迁移切片是什么？先做 pure contracts 与 import boundary 测试：封闭 `EngineEvent` / `RunnerEvent` 类型、`ToolResultEnvelope`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCallRequest`、`ToolExecutionRequest`、收窄后的 `ToolExecutor` protocol、`AsyncRunner` protocol、取消观察原语，以及 Engine 包根导出约束；暂不迁 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools。
