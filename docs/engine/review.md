# Engine 设计文档 Review

## 1. Review 结论

不通过。设计方向总体符合 NEW 的 Host 强约束思路，但 `docs/engine/design.md` 当前仍存在 tool calling 控制流真源不一致的阻塞问题；在修正该问题前，不适合作为后续 Engine 迁移依据。

## 2. 阅读范围

NEW 文件：

- `AGENTS.md`
- `docs/engine/design.md`

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

### 3.1 Tool calling 控制流真源前后冲突

- 严重级别：阻塞
- 位置：`docs/engine/design.md` 第 5 节“工具调用与结果回填边界”“事件边界”、第 14.4 节“Tool Calling Protocol”；OLD 证据见 `dayu/engine/async_openai_runner.py`、`dayu/engine/async_agent.py`
- 问题说明：文档一方面写明 Agent 调用 Host 注入的 `ToolExecutor.execute(request)`，这是 Engine 唯一调用工具的方式；另一方面又把 `tool_call_requested` 定义为“Host 必须据此调用 Host 侧 ToolExecutor”。这形成两套互斥控制流：一种是 Engine 内部通过注入协议调用 ToolExecutor，Host 只实现协议；另一种是 Engine 产出请求事件后由 Host 外部驱动工具执行并把结果送回 Engine。
- 为什么违反架构或接口原则：Host 是治理真源，但 Engine/Agent 的 tool loop 也必须有单一控制流真源。当前写法会导致实现时出现双执行、事件被当命令、Host 需要理解 Runner/Agent 内部 pending tool-call 状态，或者 Engine 等待一个文档未定义的 Host 回填通道。这会把 `UI -> Service -> Host -> Engine` 边界变成双向协议，且没有明确定义。
- 建议修改方向：二选一并写成唯一稳定协议。结合文档其它章节与 OLD 迁移目标，建议选择“Engine 调用 Host 注入的 `ToolExecutor` 协议，Host ToolRuntime 在协议实现内部完成注册、权限、审计、超时、取消、等待/恢复治理”。此时 `tool_call_requested` 只能是观测事件，不能写“Host 必须据此调用 ToolExecutor”。如果要改成 Host 外部驱动工具执行，则必须补充双向 Engine 协议、pending tool-call 状态、结果回填入口、取消/挂起状态机；当前设计没有这套基础。

## 4. 重要问题

### 4.1 ToolExecutor 协议过宽，重复暴露 ToolRegistry 能力

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 5 节、第 8 节、第 14.1 节、第 14.7 节；OLD 证据见 `dayu/contracts/protocols.py`、`dayu/engine/tool_registry.py`
- 问题说明：文档同时要求 `AgentRunRequest` 携带 `tool_schemas: list[ToolSchema]`，又在 `ToolExecutor` 最小协议中保留 `get_schemas()` 与 `get_tool_display_info()`。这会让 Engine 有两套 schema 真源，并把展示信息这类 Host/UI 可增强事实下泄给 Engine。
- 为什么违反架构或接口原则：设计下层接口时应只考虑 Engine 调用工具所需事实。若 Host 已提供本次 run 的 schema 快照，Engine 不应再从 executor 读取 schema；否则 schema 快照与 executor 内部状态可能漂移。`get_tool_display_info()` 也不是执行工具所必需，容易把 UI 展示策略或 ToolRegistry descriptor 机制泄漏到 Engine。
- 建议修改方向：将 Engine 可见 `ToolExecutor` 收紧到 `execute(request) -> ToolExecutionOutcome`。`tool_schemas` 由 `AgentRunRequest` 单独提供并作为唯一模型可见 schema 真源。展示名、参数摘要等由 Host observer 或 UI 基于 Host ToolRegistry 自行 enrichment；若 EngineEvent 需要可读信息，只放 tool name、tool_call_id、arguments 摘要等中性事实。

### 4.2 ToolExecutionOutcome 扩展位过大，迁移第一阶段风险被放大

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 5 节“扩展 outcome 预留”、第 14.4 节、第 16 节
- 问题说明：文档一次性列出 `progressing`、`approval_required`、`detached`、`retry_after`、`input_required`、`cancelled/timed_out/lost`、`deduplicated`、`delegated`、`artifact_ready` 等 outcome。虽然文档声明这些是 Host 治理语义，不是业务状态，但第 16 节又把“扩展位的封闭联合类型”放进 Engine 迁移计划，容易把第一阶段 contracts 做成过大的抽象面。
- 为什么违反架构或接口原则：Engine 第一阶段需要稳定的是模型 tool call、普通工具结果、失败结果、长事务挂起这条主链路。过早定义大量 outcome，会诱导 Engine 识别 Host 内部 task ledger、审批、通知、artifact store、去重策略等机制，增加下层接口向上泄漏的概率。
- 建议修改方向：第一阶段只落地 `completed | failed | awaiting`，再加一个明确不可注入 LLM 上下文的 `governance_event` 观察事件也可以，但不要把未实现治理分支全部做成 Engine contract。其它分支留在 issue #4 下按独立子 issue 逐一确认，每个分支必须先证明它是 Host 生命周期/取消/等待/审批/artifact 治理语义，而不是 fins/web/doc 业务状态。

### 4.3 EngineEvent / RunnerEvent 仍停留在规则说明，缺少封闭 data 类型清单

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 9 节、第 14 节；OLD 证据见 `dayu/engine/events.py`
- 问题说明：文档正确指出 OLD `StreamEvent(data: Any, metadata: dict[str, Any])` 不能迁移，但 NEW 设计仍主要描述“强类型 data 或 typed metadata”，没有列出封闭事件 data 类型清单。第 7 节还沿用 `content_complete.metadata.reasoning_content` 的表达，和“metadata 不承载显式契约语义”存在张力。
- 为什么违反架构或接口原则：事件是 Host observer、trace、audit、UI 转发的共同边界。如果 data 类型不封闭，后续实现很容易继续使用 `Any`、`object`、开放 metadata 承载显式语义，违反 NEW 编码硬约束，并让 Host 被迫依赖临时字段。
- 建议修改方向：在 design.md 中补一张 EngineEvent/RunnerEvent 类型表，至少覆盖 terminal、iteration、content、reasoning、tool request/result、usage、provider error、context budget、cancel/suspend。每个事件给出独立 dataclass/TypedDict 名称和字段；`reasoning_content` 应成为 `ContentCompleteData` 的显式字段或专门事件字段，而不是 metadata。

### 4.4 ProviderRequestPatch 仍可能退化为新的 extra payload 袋子

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 7 节、第 14.3 节；OLD 证据见 `dayu/engine/protocols.py`、`dayu/engine/async_openai_runner.py`
- 问题说明：文档已经把 `**extra_payloads` 判定为弱类型入口，并把 provider 参数迁到 `RunnerSpec`，方向正确。但 `ProviderRequestPatch(payload: JsonObject)` 如果只要求配置加载时校验 schema，仍可能成为“换了名字的 extra payload”。
- 为什么违反架构或接口原则：显式参数不能放入 extra payload。Provider patch 若允许任意 JSON object，Host/Agent/配置层仍可能临时拼装 provider 私有请求，绕过强类型字段和 runner/provider 契约。
- 建议修改方向：把 `ProviderRequestPatch` 限制为 runner/provider 私有的配置 adapter 输入，禁止公共 Engine contract 直接接受任意 patch。若必须保留，至少要求 `provider`、`schema_id`、`schema_version`、允许 patch 的 JSON pointer 白名单、禁止覆盖的保留字段清单，以及配置解析阶段失败即拒绝启动。

### 4.5 取消协议没有完全收敛到“Host 真源、Engine 观察”的可实现入口

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 6 节、第 9 节、第 14.1 节、第 16 节；OLD 证据见 `dayu/engine/cancellation.py`、`dayu/engine/async_agent.py`
- 问题说明：文档同时写 `AgentRunRequest` 携带 `cancellation_token`，又写 Host -> Engine 稳定协议是 `CancelRun(session_id, run_id, reason, requested_at)`。但函数式 `run_agent_messages(request)` 如何接收后续 `CancelRun`、如何映射到 run-local token、是否需要 Engine supervisor/cancel handle，没有写清楚。
- 为什么违反架构或接口原则：Host 是取消真源，Engine/Runner/Tool 只观察。若取消入口不清，迁移时可能把取消治理下放到 Agent/Runner，或让 Engine 持有跨 run 管理表。
- 建议修改方向：第一阶段只定义一种实现路径。建议 `AgentRunRequest` 接收 Host 创建的 `CancellationToken`，Engine 只观察 token 并产出 `run_cancelled`；`CancelRun` 属于 Host 内部/API 层命令，由 Host 转成 token cancel，不作为 Engine contract。若保留 Engine supervisor，则需要单独定义 `EngineRunHandle.cancel()`、生命周期和资源收口规则。

### 4.6 processors 拆出 Engine 后，Source / DocumentProcessor 类型归属仍未定死

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 10 节、第 11 节、第 16 节；OLD 证据见 `dayu/fins/storage/repository_protocols.py`、`dayu/fins/tools/service.py`、`dayu/engine/processors/base.py`
- 问题说明：文档判断 processors 不应继续作为 NEW core Engine 职责，方向正确。但 OLD `dayu/fins/storage/repository_protocols.py` 直接从 `dayu.engine.processors.source` 导入 `Source`，`FinsToolService` 也依赖 `dayu.engine.processors.base.DocumentProcessor` 与 `ProcessorRegistry`。如果 Engine 阶段拆出 processors，却不先定义 `Source` / processor contract 的新归属，会影响 fins storage 协议。
- 为什么违反架构或接口原则：财报文档存取必须通过 `dayu.fins.storage`，但 storage 协议不应依赖 core Engine 内部 processor 类型。否则 Engine 迁移会把文档解析类型拖回 core Engine，或者让 fins storage 继续反向绑定旧 Engine 目录。
- 建议修改方向：在 design.md 明确：`Source`、`DocumentProcessor`、`ProcessorRegistry` 的稳定归属应迁到 `dayu.fins` 或独立 document capability 的 contract 包；core Engine 不导出、不 re-export、不持有这些类型。Fins storage 协议继续作为财报读取入口，但其 source 类型不应来自 core Engine。

### 4.7 下一阶段迁移计划切片过大

- 严重级别：重要
- 位置：`docs/engine/design.md` 第 16 节
- 问题说明：第 16 节第一步同时迁移 EngineEvent、RunnerEvent、ToolResultEnvelope、ToolAwaitSpec、ToolCallRequest、ToolSchema、ToolExecutionContext、ToolExecutor、AsyncRunner、取消辅助、context budget。后续又把 RunnerSpec、OpenAI Runner、AsyncAgent 重写、tool outcome、context compaction 一起串到 Engine 阶段。
- 为什么违反架构或接口原则：切片过大时，最容易为了让测试先跑通而保留旧 re-export、弱类型 payload、Runner 执工具等兼容包袱，违背 NEW “全新设计，不为旧接口保兼容”的约束。
- 建议修改方向：拆成更小阶段：先做 pure contracts 和 import boundary 测试；再做 RunnerEvent 归一但不执行工具；再做 Agent 最小 loop（无工具 final_answer）；再做 completed/failed tool loop；最后做 awaiting/suspended。每个切片都应有 pyright、架构导入测试和最小行为测试。

## 5. 建议问题

### 5.1 术语需要统一 Engine / Agent 层级

- 严重级别：建议
- 位置：`docs/engine/design.md` 第 3 节、第 4 节、第 5 节
- 问题说明：NEW `AGENTS.md` 使用 `UI -> Service -> Host -> Engine`，任务说明中强调 `UI -> Service -> Host -> Agent`。design.md 采用 `Host -> Engine`，并把 Agent/Runner 作为 Engine 内部原语，这个方向可以接受，但需要显式解释“Engine 是包/能力边界，Agent 是 Engine 内部推理循环实现”，避免后续文档混用 Host -> Agent、Host -> Engine。
- 建议修改方向：在第 4 节增加术语框：架构层级统一写 `UI -> Service -> Host -> Engine`；Engine 内部包含 Agent loop、Runner protocol 和 tool calling contracts；Host 不依赖具体 `AsyncAgent` 类。

### 5.2 ToolTrace schema 归属表述偏早

- 严重级别：建议
- 位置：`docs/engine/design.md` 第 2.9 节、第 9 节
- 问题说明：文档说 trace schema 确认沿用 OLD `tool_trace_v2`，同时又说 trace schema 由 Host/观测层维护，不属于 Engine 稳定接口。OLD 源码确实有 `TRACE_SCHEMA_VERSION = "tool_trace_v2"`，但是否直接沿用应由 Host observer 迁移阶段确认。
- 建议修改方向：改为“OLD `tool_trace_v2` 可作为 Host observer 的默认实现素材；是否作为 NEW trace schema 真源由 Host/观测层迁移阶段确认”。Engine 只承诺事件事实足够重建该 schema。

### 5.3 README 同步规则应落到迁移计划验收项
注：可先不写README，迁移结束后统一写。
- 严重级别：建议
- 位置：`docs/engine/design.md` 第 16 节
- 问题说明：design.md 只写“根据实际落地同步 `dayu/engine/README.md`”，但 NEW `AGENTS.md` 对 README 职责和触发规则有硬约束。
- 建议修改方向：迁移计划验收项增加：修改 `dayu/engine/` 必须检查 `dayu/engine/README.md`；若涉及 Host/Engine 装配边界，还要检查 `dayu/README.md` 与 `dayu/host/README.md` 是否在职责范围内需要更新。

## 6. 可接受风险

- Runner 不执行工具、只归一模型协议：可接受。OLD `AsyncOpenAIRunner` 确实在 `_emit_tool_batch` / `_run_tool_call` 中执行工具，这正是 NEW 需要重设的边界。后续验证点是 Runner 测试必须证明 tool call 只产出 `RunnerEvent`，不依赖 `ToolExecutor`。
- ToolRegistry / ToolRuntime 归 Host：可接受。OLD `ToolRegistry` 同时承担注册、schema 校验、路径白名单、执行、截断、fetch_more 和 middleware，迁到 Host ToolRuntime 符合 Host 治理真源。后续验证点是 Engine 包不能导入 Host ToolRegistry、web/doc/fins tools。
- OLD `_compact_messages` 不作为稳定 Engine 能力：可接受。OLD 实现是确定性应急压缩，不是 conversation memory。后续验证点是 Engine 若保留 emergency fallback，不能写回 memory，也不能调用 LLM 做语义压缩。
- processors/doc/web 不进入 core Engine：可接受。OLD 源码证明这些是文档解析、文件工具和联网工具能力，不是 Agent/Runner 核心原语。后续验证点是 document capability / fins processor contract 的归属必须先定清楚。

## 7. 需要用户/总控确认的问题

- Tool calling 采用哪一种唯一控制流：Engine 内部调用注入的 `ToolExecutor`，还是 Host 消费事件后外部驱动工具执行并回填结果？我建议采用前者。
- 第一阶段 `ToolExecutionOutcome` 是否只允许 `completed | failed | awaiting` 三类落地，其它 outcome 仅保留在 issue #4 讨论，不进入 Engine 初始 contract？
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 的 NEW 归属是 `dayu.fins`、独立 document capability，还是另设跨 capability contract 包？
- `CancelRun` 是 Host 内部命令并转成 `CancellationToken`，还是 Engine 要暴露 run supervisor / cancel handle？

## 8. 总体验收判断

- 是否允许基于当前 design.md 进入迁移计划阶段？不允许直接进入。
- 如果不允许，需要先修哪些章节？至少先修第 5 节工具调用控制流和事件语义，第 8/14 节 ToolExecutor 最小协议，第 9/14 节 EngineEvent/RunnerEvent 强类型清单，第 16 节迁移切片。
- 如果允许，下一阶段最小迁移切片是什么？在修复上述阻塞后，最小切片应是 pure contracts：`EngineEvent` / `RunnerEvent` 封闭类型、`ToolResultEnvelope`、`ToolCallRequest`、`ToolExecutionRequest`、收窄后的 `ToolExecutor` protocol、`AsyncRunner` protocol、取消观察原语，以及 import boundary 测试；不迁 `AsyncAgent`、不迁 `AsyncOpenAIRunner`、不迁 ToolRegistry。
