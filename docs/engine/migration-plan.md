# Engine 迁移总控计划

## 1. 计划状态

本计划是 Engine 迁移讨论稿，用于指导后续多个迁移 Agent 分阶段实施。它不是实现文档，不包含生产代码，也不代表可以立即进入迁移。

实施顺序必须是：

1. 本计划提交 review。
2. review Agent 审查通过。
3. 总控 Agent 检查阶段成果。
4. 用户确认。
5. 才能进入对应 Phase 的实现、测试、README 同步和 GitHub PR 流程。

任何 Phase 在实现中发现设计边界不成立、需要新增公共契约、需要触碰 Host / capability / fins 具体实现，必须停止当前实现，回到设计讨论或拆分新 issue。

## 2. 依据

本计划依据以下材料：

- `docs/engine/design.md`
- `docs/engine/review.md`
- GitHub issue #2：`https://github.com/noho/dayu-agent-r/issues/2`
- `AGENTS.md`

其中 `docs/engine/design.md` 是 Engine 接口设计依据，`docs/engine/review.md` 已确认该设计可进入迁移计划阶段。OLD 仓库只作为源码证据来源和有价值 implementation 片段来源，不作为 NEW 架构、目录边界或公共接口的真源。

## 3. 总体原则

- NEW 是全新架构，不为 OLD 路径、OLD 接口、OLD 测试保留兼容 wrapper / facade / re-export。
- OLD 只能提供直接源码证据和可复用 implementation 片段；禁止机械搬迁 OLD 架构、旧接口、旧目录边界或历史包袱。
- Dayu 是宿主强约束下的 `LLM in the loop`，不是 `LLM on the loop`。
- 分层固定为 `UI -> Service -> Host -> Engine`。
- Host 是 Engine 生命周期、取消、治理的强约束真源；具体覆盖 Engine 内部 Agent / AsyncAgent / AsyncOpenAIRunner 的创建、关闭、取消观察与运行治理，以及 Host 侧 ToolRegistry / ToolRuntime、长事务等待与恢复。
- Engine 只消费 Host 通过 EngineWorker capability 提供的 run 输入、RunnerSpec、tool schema 快照、ToolExecutor protocol 和 cancellation token。
- Engine 不反向依赖 Host / Service / UI 的具体实现。
- Engine 不注册工具、不持有 ToolRegistry、不执行权限审计、不写 transcript、不写 trace store、不实现 conversation memory。
- Runner 只负责 provider 请求、响应流归一、usage、错误分类、资源关闭和取消观察；Runner 不执行工具。
- Agent 是 Engine 内部推理循环实现；Host 稳定依赖函数式入口和 contracts，不依赖具体 `AsyncAgent` 类。
- EngineEvent 是 Engine -> Host 的唯一观测边界；显式契约事实必须进入强类型 data，不得塞进 metadata。
- ToolExecutor 是 Host / EngineWorker 与 Engine 围绕 tool calling 的最小协议，只暴露 `execute(request) -> ToolExecutionOutcome`；EngineWorker 只是替 Host 在选定执行环境中代持 ToolExecutor，不拥有工具治理真源。
- 第一阶段 ToolExecutionOutcome 只落地 `completed | failed | awaiting`。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 在 Engine / Host 公共边界不可见。
- 财报文档存取必须且只能通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成。
- 禁止使用 `Any`、`object`、无类型参数、无类型返回值逃避严格类型设计。
- 每个实现切片都必须先有接口测试和架构测试，再迁实现。

## 4. 阶段总览

| Phase | 名称 | 目标 | 输入 | 输出 | 禁止事项 | 验收信号 |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 0 | pure contracts 与 import boundary tests | 先落地 Engine 最小稳定 contract 和包边界测试 | `design.md` 第 9、14、16 节，`review.md` 通过结论 | 强类型 contracts、包根导出约束、import boundary tests | 不迁 `AsyncAgent`、`AsyncOpenAIRunner`、ToolRegistry、doc/web/fins tools | contracts 可被测试导入；架构测试能阻止旧 re-export 和反向依赖 |
| Phase 1 | Runner protocol 与 OpenAI-compatible Runner | 迁移 provider 协议归一能力，Runner 只产出 RunnerEvent | Phase 0 contracts，OLD `async_openai_runner.py` 可复用片段 | `AsyncRunner` protocol 当前实现、RunnerEvent 流、RunnerSpec provider extension | 不迁 `AsyncCliRunner`，不迁 Runner 工具执行，不保留 `call(**extra_payloads)` | Runner 测试证明 tool call 只产生 RunnerEvent，不调用 ToolExecutor |
| Phase 1.5 | Log / Runner diagnostics 与 SSE idle | 引入 `dayu.runtime` 公共运行时基础设施（log 装配 + cancellation race helper），给 Phase 1 Runner 补齐运行时边界日志，落地 chunk 级 SSE idle heartbeat / hard timeout（issue #6） | Phase 1 Runner、`dayu/contracts/cancellation.py`、OLD `dayu/log.py` / `sse_parser.py` 证据 | `dayu/runtime/log.py`、`dayu/runtime/cancellation.py`、Runner 边界 logger、`RunnerSpec.stream_idle_*` 字段、idle 控制流 | 不污染 RunnerEvent / EngineEvent；不新增 Engine / Runner 公共终态异常；Engine 不 import `dayu.runtime.log`；不迁 OLD `Log` 单例 wrapper；不写 README（统一推迟到 Phase 5 文档收口） | 诊断字段在 caplog 中可见；idle 测试集（disabled / heartbeat / timeout / timeout-only / cancel wins / retry / aclose / outer cancel）全绿；事件契约无 log/idle 字段污染；issue #6 可关闭 |
| Phase 2 | Agent run loop 骨架 | 建立 run-scoped Agent 和函数式入口 | Phase 0 contracts，Phase 1 Runner，Phase 1.5 logger / cancellation runtime | `run_agent_messages` / `run_agent_and_wait` 骨架、RunnerEvent -> EngineEvent 提升、terminal 收口、`dayu/engine/README.md` 当前事实手册 | 不接入 ToolRegistry，不实现 long-running tool waiting，不迁 doc/web/fins 工具 | 无工具 run 可完成 final_answer / run_failed / run_cancelled，并关闭 Runner；Engine README 只写 Phase 2 已落地事实 |
| Phase 3 | EngineWorker 代持 ToolExecutor 的 tool calling 闭环 | 建立普通工具调用闭环，并按 Host capability 口径固定 EngineWorker / ToolExecutor 边界；同步落地 max_iterations force-answer 与连续失败工具批次保护 | Phase 2 Agent loop，Phase 0 ToolExecutor contract，`docs/host/design.md` | 模型 tool call -> ToolExecutionRequest -> ToolExecutionOutcome -> LLM-facing tool message 注入下一轮；默认 max_iterations force-answer；连续失败工具批次按 fallback mode 收口；测试用 fake ToolExecutor 表示 EngineWorker 替 Host 代持的执行能力 | Engine 不注册工具，不执行权限、审计、路径白名单、长事务治理；不实现 EngineWorker / RPC 生产代码；Runner 不执行工具 | completed / failed 工具结果可进入下一轮；内部 ToolResultEnvelope 不直接进入 LLM-facing content；max_iterations 默认 force-answer；连续失败批次保护可观测；无双执行、无事件驱动工具执行；计划和 review 均确认 EngineWorker 是 Host capability 且不拥有治理权 |
| Phase 3 后置 patch | provider_state / reasoning roundtrip | 在普通工具闭环落地后，把 Phase 3 过渡性的 reasoning_content 无脑写回改为 provider-specific 策略 | Phase 3 tool loop，真实 provider smoke / NEW-OLD 对照证据 | 明确 `ToolCallProviderState` 扩展策略，判断哪些 provider 需要把 reasoning_content 纳入 provider_state 或请求投影策略 | 不把 Phase 3 的无条件写回固化为跨 provider 稳定规则 | provider_state 可避免多轮工具调用协议断链；reasoning_content 写回策略按 provider 明确 |
| Phase 4 | 已取消：awaiting / suspend 后移 issue #4 | 不再作为独立 Engine 迁移阶段实施 | Phase 3 tool loop，issue #4 后续子 issue | 历史草案保留；`suspend` / `run_suspended` / `ToolAwaitingOutcome` 由 issue #4 重新计划 | 不把 awaiting 作为 Phase 5 前置；不实现 Host wait record / monitor / resume | migration plan 与历史草案均明确 Phase 4 已取消，后续由 issue #4 拆子 issue |
| Phase 5 | continuation、取消收口回归 + Phase 6 文档收口 | 合并原 Phase 5/6；迁移 Engine 层剩余 Agent 自洽能力并在同一 PR 做 README / docs 验收收口 | Phase 3 普通 tool calling 主链路，Phase 1 Runner，OLD AsyncAgent / Runner 强参考源 | `finish_reason=length` 禁工具续写拼接、continuation 次数限制、content_filter 不续写、取消优先回归、README / issue 收口 | 不实现 Phase 4 suspend；不实现 context overflow / `context_compaction_requested` / trigger ratio；不实现 Engine 内 compact/retry；不迁 OLD TruncationManager / fetch_more / cursor / TTL / scope token；不实现 conversation memory / transcript / trace store / Host wait record | OLD/NEW 专项 review 与日常 review 通过；Phase 3 force-answer 与连续失败批次不回退；README 只写已落地事实；context overflow 明确后移 Host 实施时作为独立 issue 完善 |

## 5. Phase 0 详细计划

### 目标

落地 Engine pure contracts 与 import boundary tests。该阶段只建立公共契约和架构护栏，不迁移 Agent loop、Runner 实现、ToolRegistry 或任何工具。

### 前置条件

- `docs/engine/design.md` 已通过 review。
- 用户确认可以从计划阶段进入 Phase 0 实现。
- 当前仓库不存在必须保留的 OLD Engine 兼容入口要求。

### 迁移 Agent 任务

- 新建 Engine contract 模块，定义封闭强类型 `EngineEvent`、`RunnerEvent`、事件 data 类型、terminal event 类型。
- 定义 `ToolResultEnvelope`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`ToolCallRequest`、`ToolExecutionRequest`、`ToolExecutionContext`、`ToolExecutionOutcome`。
- 定义收窄后的 `ToolExecutor` protocol，仅包含 `execute(request) -> ToolExecutionOutcome`。
- 定义 `AsyncRunner` protocol，只包含 `call(messages, options, tools)`、`is_supports_tool_calling()`、`close()`。
- 定义 `AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、cancellation 观察原语。
- 建立 Engine 包根导出策略与测试；Phase 0 只允许导出 contract 类型，不导出未实现的 `run_agent_messages` / `run_agent_and_wait` 占位函数。
- 建立 import boundary tests，阻止 Engine 导入 Host 具体实现、ToolRegistry、web/doc/fins tools、ToolTraceRecorder、`dayu.fins.storage` 具体实现。
- 建立 weak typing tests 或 pyright 覆盖，阻止公共 contract 中出现 `Any`、`object`、无类型参数、无类型返回值。

### 允许复用的 OLD implementation 片段

- `dayu/engine/events.py` 的事件语义作为命名和场景证据。
- `dayu/engine/tool_result.py` 的工具结果信封字段语义。
- `dayu/contracts/protocols.py` 中 `ToolExecutionContext` 的 run / iteration / tool_call / timeout / cancellation 字段语义。
- `dayu/engine/cancellation.py` 的协作式取消思想。

### 禁止迁移项

- `AsyncAgent` 实现。
- `AsyncOpenAIRunner` 实现。
- `AsyncCliRunner`。
- ToolRegistry / ToolRuntime 具体实现。
- doc/web/fins tools。
- processors。
- ToolTraceRecorder / JsonlToolTraceStore。
- `dayu.engine.__init__` 旧 re-export。
- `StreamEvent(data: Any, metadata: dict)` 弱类型接口。

### 测试要求

- contract 类型导入测试。
- Engine 包根导出测试：Phase 0 若导出超出 contract 类型则测试失败；`run_agent_messages` / `run_agent_and_wait` 到 Phase 2 具备真实最小实现后才加入包根导出。
- import boundary 测试：Engine 不得导入 Host、Service、UI、Host ToolRegistry、web/doc/fins tools、ToolTraceRecorder、`dayu.fins.storage` 具体实现。
- 事件 data 封闭联合测试：新增 event type 必须有强类型 data。
- `ToolExecutionOutcome` 穷尽匹配测试：只允许 `completed | failed | awaiting`。
- metadata 边界测试：显式契约事实不得进入 metadata。

### pyright 要求

- Phase 0 完成后必须运行 pyright。
- 不允许新增、扩散、掩盖类型错误。
- 公共 contract 禁止 `Any`、`object`、无类型参数、无类型返回值。

### README / docs 同步要求

- 若新增 `dayu/engine/` contract 代码，应检查 `dayu/engine/README.md` 是否需要记录当前公共契约。
- README 命中触发条件时先检查职责范围；只有当前可用契约确实落地且属于 `dayu/engine/README.md` 职责范围时才更新，不做机械同步。
- 若仅添加测试和内部 contract 草案，可在 PR 说明中解释 README 不更新的原因。
- 不更新根 README 的用户手册内容，除非实际公共命令或用户入口变化。

### review Agent 审查重点

- contract 是否严格对应 `design.md` 的事件表和 outcome 设计。
- 是否出现旧 `StreamEvent`、`EventType` 兼容 re-export。
- ToolExecutor 是否只暴露 `execute`。
- Engine 包根是否过宽。
- 是否存在 Engine -> Host / tool / fins 的反向导入。
- 是否有 `Any`、`object`、裸 dict 等弱类型逃逸。

### 总控验收标准

- Phase 0 可独立形成 PR。
- PR 只包含 contracts、架构测试、必要 README/docs 同步。
- 测试和 pyright 通过。
- review Agent 未发现边界回退。

### 用户确认点

- 是否确认 Engine 包根导出集合。
- 是否确认 `correlation_id` 作为可选中性字段保留。
- 是否确认 Phase 1 可基于该 contract 真源继续。

## 6. Phase 1 详细计划

### 目标

迁移 OpenAI-compatible Runner 的模型协议归一能力。Runner 只负责 provider 请求、SSE/JSON 响应解析、usage、错误分类、资源关闭和取消观察，并只产出 RunnerEvent。

### 前置条件

- Phase 0 contracts 与 import boundary tests 已合并。
- `RunnerSpec`、`RunnerCallOptions`、`ToolSchema`、`RunnerEvent` 已成为代码真源。
- 用户确认进入 Runner 实现阶段。

### 迁移 Agent 任务

- 基于 `AsyncRunner` protocol 实现 OpenAI-compatible Runner。
- 将 OLD `call(**extra_payloads)` 重设为 `call(messages, options, tools)`。
- 将 provider、model、endpoint、headers、thinking/reasoning provider 参数放入 `RunnerSpec`。
- 将 temperature、max tokens、top_p、response format 等请求级参数放入 `RunnerCallOptions`。
- 迁移 SSE / non-stream JSON 解析、usage 采集、HTTP 错误分类、重试与 backoff 的有价值实现。
- 迁移 provider reasoning 内容归一逻辑，但输出必须是 `runner_reasoning_delta` 或 `runner_content_completed.reasoning_content`。
- Runner 在 HTTP 建连、响应读取、SSE chunk 等待、重试 sleep 边界观察 cancellation token。
- Runner 关闭时释放 HTTP session / stream / parser 资源。

### 允许复用的 OLD implementation 片段

- `async_openai_runner.py` 中 payload 构建、SSE / JSON 响应解析、usage 采集、HTTP 错误分类、重试策略。
- `sse_parser.py`、`reasoning_protocol.py`、`xml_extractor.py` 中 provider 协议归一片段。
- cancellation helper 的 await / cancel 竞争思想。

### 禁止迁移项

- `_emit_tool_batch`、`_run_tool_call` 等 Runner 执行工具职责。
- `set_tools`。
- `call(**extra_payloads)`。
- `AsyncCliRunner`。
- ToolExecutor 依赖。
- ToolRegistry 依赖。
- trace recorder 依赖。
- 直接读取 `llm_models.json`。

### 测试要求

- Runner protocol 实现测试。
- SSE content delta / reasoning delta / tool call delta / usage / runner_done 测试。
- non-stream JSON 响应测试。
- HTTP 错误分类和重试测试。
- cancellation 阻塞边界测试。
- close 资源释放测试。
- tool call 输出测试必须证明 Runner 只产出 RunnerEvent，不执行工具、不依赖 ToolExecutor。
- provider request extension 测试必须证明显式字段不进入 extra payload 袋子。

### pyright 要求

- Runner 公共签名和 provider extension 类型必须通过 pyright。
- 禁止用 `Any`、`object` 或裸 dict 表达 provider 公共 contract。
- 若内部必须处理 JSON，应使用严格 JSON value union 或私有 adapter 类型。

### README / docs 同步要求

- 若 `dayu/engine/` 新增当前 Runner 实现，应检查 `dayu/engine/README.md` 的 Runner 协议说明。
- 若涉及 Engine / Host 装配边界变化，应检查 `dayu/README.md` 是否属于职责范围。
- 不写尚未落地的 tool calling 或 Host 实现细节。

### review Agent 审查重点

- Runner 是否仍然只产出 RunnerEvent。
- 是否删除 `set_tools` 和 `call(**extra_payloads)` 弱入口。
- provider 私有参数是否只在 RunnerSpec / provider adapter 内部受控流动。
- 取消观察和资源关闭是否覆盖阻塞边界。
- 是否误迁 `AsyncCliRunner` 或工具执行代码。

### 总控验收标准

- Phase 1 可独立形成 PR。
- Runner tests、架构测试、pyright 通过。
- Runner 不导入 ToolExecutor、ToolRegistry、tools、Host、trace recorder。
- RunnerEvent 与 Phase 0 contract 完全一致。

### 用户确认点

- 是否接受首个 OpenAI-compatible Runner 的 provider extension 范围。
- 是否确认暂不迁 `AsyncCliRunner`。

## 6.5 Phase 1.5 详细计划

### 目标

在进入 Phase 2 Agent loop 之前，引入 `dayu.runtime` 公共运行时基础设施包，给 Phase 1 OpenAI-compatible Runner 补齐运行时边界日志，并落地 chunk 级 SSE idle heartbeat / hard timeout（GitHub issue #6）。

### 前置条件

- Phase 1 Runner 已合并，RunnerEvent 流稳定。
- 用户确认进入 Phase 1.5 实施。
- 详细任务、字段语义、测试清单等真源在 `docs/engine/phase1_5-plan.md`，本节只承担总控接入说明。

### 迁移 Agent 任务

- 落地 `dayu/runtime/__init__.py`、`dayu/runtime/log.py`（`LogLevel` + `configure` + `set_level_from_flags`）、`dayu/runtime/cancellation.py`（`await_or_cancel` + `wait_for_or_cancel` + 封闭联合结果类型）。
- 把 `dayu/engine/runners/openai/cancellation_helpers.py` 收缩为只持有 `_RunnerInterrupted` 私有信号；公共 race / poll 能力迁出到 `dayu.runtime.cancellation`，原文件不保留兼容 wrapper。
- 给 OpenAI-compatible Runner / `SSEParser` / `non_stream_parser` 在运行时边界挂上 `_LOGGER = logging.getLogger(__name__)` 并按 `phase1_5-plan.md` §5 边界表挂日志。
- `RunnerSpec` 新增 `stream_idle_timeout_seconds` / `stream_idle_heartbeat_seconds` 两个可选字段，附 `__post_init__` 校验。
- Runner byte iterator 拆出 idle disabled / idle enabled 两条路径；idle 路径以 `wait_for_or_cancel` 实现 pending vs cancellation vs timeout 三方 race。

### 允许复用的 OLD implementation 片段

- OLD `dayu/log.py` 的 LogLevel 设计与 `set_level_from_flags` 入口形态。
- OLD `async_openai_runner.py` Runner 边界日志位置与字段（按 `phase1_5-plan.md` §2 边界表筛选）。
- OLD `sse_parser.py` 中跨循环复用 `pending = create_task(__anext__())` + `asyncio.wait` 三方 race + finally 清理的 idle 实现思路。
- OLD `tests/engine/test_sse_parser.py` 中 `test_parse_stream_cancels_pending_task_on_early_close` / `test_parse_stream_outer_task_cancel_cleans_inflight_next_chunk_task` 的回归场景。

### 禁止迁移项

- OLD `Log` 单例与 `Log.debug/info/warn/error` 兼容 wrapper / 别名。
- Tool execution、`default_extra_payloads`、Runner 层 `request_id`、模型降级路径等不在 Runner 边界的日志。
- provider response body preview、完整 exception text、messages、payload、headers、tool arguments 等敏感字段写入 log。
- Engine import `dayu.runtime.log`（只允许 import `dayu.runtime.cancellation` 与 stdlib `logging`）。
- `dayu.runtime.*` 反向 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- 新增 Engine / Runner 公共终态异常表达 cancel 或 idle timeout（idle timeout 复用 `RunnerHTTPErrorCode.TIMEOUT` 与 `_AttemptFailedRetriable`）。
- 新增 `RunnerEventType` / `EngineEventType`、向 RunnerEvent / EngineEvent / metadata 写入 log 字段。

### 测试要求

- 测试清单以 `phase1_5-plan.md` §8 为真源；至少必须覆盖：
  - `tests/runtime/*`：runtime 不反向 import 上层、`configure()` 幂等与 root 不污染、`await_or_cancel` / `wait_for_or_cancel` 行为与封闭结果类型、watcher / pending task 在 timeout / cancel / outer cancel 各路径不泄漏、cancellation 与 timeout 同时满足时 cancellation 优先。
  - `tests/engine/test_logger_import_boundary.py`：禁止 import `dayu.runtime.log`、允许 import `dayu.runtime.cancellation`。
  - Runner diagnostics：HTTP error / retry / protocol error / cancellation / close / 无 body preview。
  - `tests/engine/runners/openai/test_sse_idle_*.py`：disabled / heartbeat / timeout / timeout-only / cancel wins / retry / aclose / outer cancel cleanup。
  - `RunnerSpec` 字段 contract 测试与 `RunnerEventData` 不含 `log_*` / `idle_*` / `heartbeat_*` 字段防回流测试。

### pyright 要求

- `dayu/runtime/**` 与 Runner 修改面 pyright 全绿，无新增 / 扩散类型错误。
- 公共 helper（`wait_for_or_cancel` 返回值、`RunnerSpec` 字段）必须封闭强类型，禁止 `Any` / 裸 dict。

### README / docs 同步要求

- 按用户决策，Phase 1.5 不修改、不新建任何 README；统一推迟到 Phase 5 文档收口阶段一次性同步。
- 仅修改本计划与 `docs/engine/phase1_5-plan.md`。
- PR 描述中显式说明：本期未修改 README，全部以代码 + 测试 + `docs/engine/phase1_5-plan.md` 为事实真源。

### review Agent 审查重点

- `dayu.runtime` 是否保持层中立、不反向 import 上层。
- Engine Runner 是否仅 import stdlib `logging` 与 `dayu.runtime.cancellation`，不 import `dayu.runtime.log`。
- 日志是否未污染 RunnerEvent / EngineEvent / metadata。
- idle 是否放在 Runner byte iterator 层，`SSEParser` 是否保持纯 parser、未 import Runner 私有异常或 token。
- 是否未新增 Engine / Runner 公共终态异常；cancel 与 idle timeout 是否仍走既有私有异常路径。
- `RunnerSpec` idle 字段非法值是否构造期拒绝。
- 是否未引入 OLD `Log` 单例 wrapper、未保留 `await_or_cancel` 转发 wrapper。

### 总控验收标准

- Phase 1.5 可独立形成 PR。
- `tests/runtime` / `tests/engine` 受影响子集与 pyright 全绿。
- review Agent 与总控验收通过；GitHub issue #6 可在合并后关闭。
- README 按 §9 决策保持不变。

### 用户确认点

- `LogLevel` 是否保留 `VERBOSE=15`（推荐暂不保留）。
- `dayu.runtime.cancellation` 公共结果类型采用封闭联合 / 单一判别枚举（推荐封闭联合，由 review I1 锁定）。

## 7. Phase 2 详细计划

### 目标

建立 run-scoped Agent run loop 骨架与函数式入口。该阶段只实现无工具主链路：iteration、RunnerEvent -> EngineEvent 提升、terminal event 收口和资源关闭。

### 前置条件

- Phase 0 contracts 已合并。
- Phase 1 Runner 可被函数式入口创建或注入。
- Engine 包根导出规则已由测试保护。

### 迁移 Agent 任务

- 实现 `run_agent_messages(request)`，返回 `AsyncIterator[EngineEvent]`。
- 实现 `run_agent_and_wait(request)`，聚合事件流得到 `AgentRunResult`。
- 建立 run-scoped Agent 内部类或私有实现函数。
- 每次 run 创建新的 Agent 与 Runner，run 终态后关闭 Runner。
- 实现 iteration_started、runner_* event 提升、runner_usage_recorded、runner_done、final_answer、run_failed、run_cancelled。
- 实现 Agent 实例 fail-fast 并发保护。
- 实现 final_answer 前取消检查。
- 实现 basic max iteration / basic fallback / provider error 收口的最小骨架。
- 新增 `utils/` 下的手动 smoke 脚本，用简单 prompt 真实调用多个 OpenAI-compatible provider，开启 DEBUG 日志，验证 Phase 2 AsyncAgent 主链路与 Phase 1.5 Runner diagnostics 可以协同工作。
- smoke 脚本的 provider case 可以参考 OLD `llm_models.json` 后在脚本内写死少量非敏感配置；脚本运行时不得依赖 OLD 仓库。
- smoke 脚本只能从环境变量读取 API key，不得把 key、headers、完整 payload、完整 prompt 或财报内容写入日志。

### 允许复用的 OLD implementation 片段

- `AsyncAgent.run_messages` 的 run-scoped finally 关闭 Runner 思路。
- `_acquire_run_slot` 的并发 fail-fast 思路。
- `_run_loop` 中 iteration 与 final_answer 收敛的场景判断，但必须拆分，不能照搬 God function。
- content_filter / length finish_reason 的场景证据。
- OLD `llm_models.json` 中少量 OpenAI-compatible provider 的 endpoint / model / provider extension 形态可作为 smoke 脚本配置证据，但不得运行时读取 OLD 文件。

### 禁止迁移项

- ToolRegistry。
- ToolExecutor tool calling 闭环。
- awaiting / long-running tool waiting。
- doc/web/fins tools。
- ToolTraceRecorder。
- transcript 持久化。
- conversation memory。
- 语义压缩。
- smoke 脚本不得进入 `dayu/` 生产包，不得作为 pytest 常规用例，不得成为 provider 行为的单元测试真源。
- smoke 脚本不得引入 OLD 运行时依赖或读取 OLD 仓库文件。

### 测试要求

- 函数式入口导出测试。
- 无工具成功 run：RunnerEvent 提升为 EngineEvent 并产出 final_answer。
- provider error -> run_failed。
- cancellation token 已取消 -> run_cancelled，且不产出 final_answer。
- final_answer 前取消命中 -> run_cancelled 优先。
- Runner close 在 success / failure / cancellation 中都执行。
- event_id 幂等、sequence 单调、terminal event 唯一性测试。
- Agent 实例并发 fail-fast 测试。
- smoke 脚本必须可通过命令行手动运行，并在缺少必要 API key 时明确跳过 / 友好报错；该脚本不纳入常规 pytest。

### pyright 要求

- Agent loop 内部状态和事件提升必须有完整类型。
- 不允许用裸 dict 传递 EngineEvent data。
- 不允许为了简化聚合使用 `Any`。
- smoke 脚本若纳入 pyright 检查范围，也必须保持完整类型；若因手动工具属性需要例外，必须在计划中说明边界，不得影响生产包类型质量。

### README / docs 同步要求

- Phase 2 必须新建 `dayu/engine/README.md`，这是用户明确要求的 README 例外。
- `dayu/engine/README.md` 只写 Phase 2 已经落地的当前事实：Engine 职责边界、`UI -> Service -> Host -> Engine`、Host 与 Engine 的稳定依赖表面、`run_agent_messages` / `run_agent_and_wait`、run-scoped Agent 生命周期、RunnerEvent -> EngineEvent 提升、无工具主链路状态机、`final_answer` / `run_failed` / `run_cancelled` 终态、取消优先级、Runner close、Phase 1 OpenAI-compatible Runner 与 Phase 1.5 diagnostics / SSE idle 的当前位置。
- `dayu/engine/README.md` 不得把 ToolExecutor tool calling 闭环、awaiting / long-running tool waiting、Host ToolRegistry、trace store、transcript 持久化、conversation memory、context budget / continuation 写成可用能力。
- 如果新增或调整测试分层且属于 `tests/README.md` 职责范围，可以更新 `tests/README.md`。
- 除 `dayu/engine/README.md` 与必要的 `tests/README.md` 外，Phase 2 不新建、不修改其它 README；其它 README 仍统一推迟到 Phase 5 文档收口阶段。

### review Agent 审查重点

- Host 是否只依赖函数式入口和 contracts。
- Agent 是否 run-scoped，不跨 run 持有状态。
- Runner 是否在所有终态关闭。
- 取消是否优先于 final_answer。
- 是否提前接入工具、trace、memory 或 Host 具体实现。
- 常规 code review 通过后，必须再执行一轮 NEW / OLD AsyncAgent 无工具核心状态机与 Runner 消费边界的实现代码严格对照 review，确认 Phase 2 未让 OLD 高可靠 Agent run loop 语义或 OpenAI-compatible Runner 协议、事件流、状态机在 Agent 提升过程中漂移。

### 总控验收标准

- Phase 2 可独立形成 PR。
- 无工具 Agent loop 可运行、可测试、可取消、可失败收口。
- `utils/` smoke 脚本可手动验证多个 OpenAI-compatible provider 的简单 prompt，并输出 DEBUG 级别 Runner / Agent 诊断日志；缺 key 时安全跳过。
- import boundary tests 继续通过。
- README 策略与用户决策一致：必须新建 `dayu/engine/README.md`，只写当前已落地事实；除该文件与必要的 `tests/README.md` 外不改其它 README。
- 总控必须提醒并确认已完成 NEW / OLD AsyncAgent 无工具核心状态机与 Runner 消费边界严格对照 review；该 review 通过后，Phase 2 才能进入提交 / PR 流程。

### 用户确认点

- 是否接受函数式入口作为 Host 首选依赖表面。
- 是否确认 Phase 3 开始接入 EngineWorker 替 Host 代持并提供的 ToolExecutor。

## 8. Phase 3 详细计划

### 目标

建立 EngineWorker 替 Host 代持 ToolExecutor 的普通 tool calling 闭环：模型 tool call -> ToolExecutionRequest -> ToolExecutionOutcome -> LLM-facing tool message 注入下一轮 Runner。同时在 Phase 3 内完成 max_iterations force-answer 与连续失败工具批次保护，避免把 OLD 可靠主链路拆到 Phase 5。

Phase 3 不插入独立 Phase 2.5；`docs/host/design.md` 中关于 EngineWorker 的决策作为本阶段前置设计输入一并吸收：

- EngineWorker 是 Host 的 capability，不是新的顶层业务层。
- Host 仍是治理真源。
- EngineWorker 代表 Host 持有执行环境，并替 Host 代持、提供 ToolExecutor。
- Local Agent 表示 Engine + tools 在本地 worker 侧执行。
- Remote Agent 表示 Engine + tools 在远程 worker 侧执行。
- Engine 不知道 Local / Remote / RPC，只消费 ToolExecutor protocol。
- Phase 3 测试中的 fake ToolExecutor 只表示 EngineWorker 替 Host 代持 ToolExecutor 的测试替身，不代表生产 Host 实现。

### 前置条件

- Phase 2 Agent loop 已合并。
- Phase 0 ToolExecutor、ToolExecutionRequest、ToolExecutionOutcome 已稳定。
- Runner 已能输出 runner_tool_call_delta / runner_tool_calls_completed 或等价 RunnerEvent。
- `docs/host/design.md` 已记录 EngineWorker 是 Host capability、ToolExecutor 由 EngineWorker 替 Host 代持并提供给 Engine 的决策。

### 迁移 Agent 任务

- Agent 将 Runner tool call 归一为 ToolCallRequest。
- Agent 发出 `tool_call_requested` EngineEvent，该事件只用于观测。
- Agent 构造 ToolExecutionRequest，补齐 `session_id`、`run_id`、`iteration_id`、`tool_call_id`、`index_in_iteration`、`cancellation_token`、可选 `correlation_id`。
- Agent 调用 EngineWorker 替 Host 代持并提供的 `tool_executor.execute(request)`。
- completed / failed outcome 返回后，Agent 发出 `tool_result_accepted`，并通过 Engine 内部专用 LLM-facing projection helper 把 tool message 注入下一轮 Runner；禁止把内部 `ToolResultEnvelope` 直接作为 `ToolMessage.content`。
- 工具执行失败作为普通工具失败结果进入上下文，由模型继续恢复或解释。
- 补齐 `FinalAnswerData.degraded`；force-answer 产出 `degraded=True`，content_filter 产出 `filtered=True, degraded=True`，普通 final answer 为 `degraded=False`。
- 补齐 `AgentPolicy.fallback_mode` / `fallback_prompt` / `max_consecutive_failed_tool_batches`；默认 fallback mode 为 force-answer，连续失败工具批次阈值参考 OLD 为 2。
- `max_iterations` 耗尽时，最后一轮允许的 tool call 照常执行并注入结果；默认追加 `UserMessage` fallback prompt、调用 Runner 时 `tools=()`、不调用 ToolExecutor，生成 `final_answer(degraded=True)`；`RAISE_ERROR` 时才 `run_failed("max_iterations_exceeded")`。
- 连续失败工具批次达到阈值后按 fallback mode 收口：force-answer 路径追加 `UserMessage` fallback prompt、Runner 调用 `tools=()`、不调用 ToolExecutor；raise-error 路径产出明确错误码。
- 保持 ToolSchema 快照来自 AgentRunRequest，不从 ToolExecutor 再读取 schema。
- 新增测试用极小 fake tool（例如 `add_numbers(a, b) -> a + b`），作为 EngineWorker 替 Host 代持 ToolExecutor 的状态机护栏，证明工具只执行一次、事件只观测不触发执行、completed / failed outcome 能进入下一轮 Runner。
- 可新增 `utils/` 下 Phase 3 手动 smoke 脚本，用真实 provider + 极小 fake tool 验证 tool calling 闭环；该脚本不进入生产包、不纳入真实联网 pytest。

### 允许复用的 OLD implementation 片段

- OLD tool call ID、index、arguments 归一场景。
- OLD `project_for_llm()` 的 LLM-facing projection 语义：成功 dict 展开、成功非 dict 包 `content`、失败只暴露 `error/message/hint`、空结果保持 tool message 配对、truncation 只保留 LLM 可执行字段；内部契约必须保持 NEW 强类型。
- OLD max_iterations -> force-answer 默认收口语义。
- OLD content_filter `filtered=True, degraded=True` 语义。
- OLD 连续失败工具批次保护语义。
- duplicate call guard 的场景证据，可作为后续 AgentPolicy 的实现素材。

### 禁止迁移项

- Engine 内 ToolRegistry。
- Engine 内工具注册、参数校验、权限、审计、路径白名单。
- EngineWorker / LocalEngineWorker / RemoteEngineWorkerProxy / RemoteEngineWorkerStub 生产实现。
- 远程 RPC 协议。
- Runner 执行工具。
- Host 根据 `tool_call_requested` 事件另行执行工具。
- `get_schemas()` / `get_tool_display_info()` 回到 ToolExecutor。
- long-running awaiting outcome 的完整治理。
- doc/web/fins 工具实现。

### 测试要求

- tool_schemas 只从 AgentRunRequest 进入 Runner。
- 模型 tool call 后只调用一次 `ToolExecutor.execute`。
- `tool_call_requested` 事件不触发第二套执行路径。
- completed outcome 注入下一轮 tool message。
- failed outcome 注入下一轮失败工具消息。
- LLM-facing projection 测试：成功 object 展开、成功 scalar/string 包 `content`、失败不带 `ok`、`hint=None` 省略、空结果注入非空占位、truncation 不泄漏内部治理对象。
- max_iterations 默认 force-answer：最后一轮 tool call 照常执行并注入结果，fallback prompt 追加为 `UserMessage`，Runner 调用 `tools=()`，force-answer 不调用 ToolExecutor，final answer `degraded=True`。
- `fallback_mode=RAISE_ERROR` 才 `run_failed("max_iterations_exceeded")`；force-answer 空内容 `run_failed("force_answer_empty")`。
- content_filter 产出 `filtered=True, degraded=True`。
- 连续失败工具批次达到阈值后分别覆盖 force-answer / raise-error；成功批次会清零连续失败计数。
- max_iterations、连续失败工具批次、force-answer、content_filter 路径都必须断言 terminal event 唯一与 cancellation 优先。
- ToolExecutionRequest 字段完整性测试。
- ToolExecutor 异常边界测试：若 Host executor 违反契约，应进入 run_failed 或协议错误，而不是裸异常泄漏。
- Runner 不依赖 ToolExecutor 的架构测试继续通过。
- fake `add_numbers` 工具护栏测试：completed outcome 注入下一轮 tool message，failed outcome 注入下一轮失败工具消息，ToolExecutor 只调用一次，Engine 不持有 ToolRegistry。
- Phase 3 smoke 脚本轻量测试：缺 key 友好跳过、参数解析、安全输出、fake tool 行为，不真实联网。

### pyright 要求

- ToolExecutionRequest、ToolResultEnvelope、ToolExecutionOutcome 必须为封闭强类型。
- tool arguments 若为 JSON，应使用严格 JSON value union，不得用 `Any`。

### README / docs 同步要求

- 更新 `dayu/engine/README.md` 的 tool calling 状态机时，只能明确 ToolExecutor 由 EngineWorker 替 Host 代持并提供、EngineWorker 是 Host capability。
- 不写 Host ToolRegistry 具体实现细节。
- 不写 EngineWorker / RPC 生产实现细节。
- 不写 doc/web/fins 工具使用手册。

### review Agent 审查重点

- 是否存在双执行风险。
- 是否按 `docs/host/design.md` 采用 EngineWorker 口径，而不是把 ToolExecutor 写死为 Host 本进程直接执行。
- ToolExecutor 是否保持最小协议。
- Engine 是否仍不接触 ToolRegistry。
- tool_result_accepted 事件与 ToolResultEnvelope 是否强类型。
- LLM-facing projection 是否与内部 ToolResultEnvelope 分离，且没有把 `ok/value` envelope 直接塞给 LLM。
- max_iterations 是否默认 force-answer，且 fallback prompt 是 `UserMessage`、Runner 调用 `tools=()`、不调用 ToolExecutor。
- content_filter 是否 `filtered=True, degraded=True`。
- 连续失败工具批次保护是否在 Agent loop 内实现，且没有误写成 Host ToolRegistry / ToolRuntime 治理。
- 工具失败是否被误当 run_failed。
- 常规 code review 通过后，必须再执行一轮 NEW / OLD Agent tool calling 状态机严格对照 review。该 review 以 OLD AsyncAgent / Runner 中高度可靠的普通工具调用语义为强参考源，但必须确认 NEW 已将工具执行职责重设到 EngineWorker 替 Host 代持并提供的 ToolExecutor，不能把 OLD Runner 执行工具的职责迁回 Engine / Runner。

### 总控验收标准

- Phase 3 可独立形成 PR。
- completed / failed 普通工具闭环可运行。
- LLM-facing projection、max_iterations force-answer、content_filter degraded、连续失败工具批次保护均按 `docs/engine/phase3-plan.md` 覆盖。
- 架构测试继续阻止 ToolRegistry / tools 导入。
- review Agent 确认工具调用控制流单一。
- review Agent 确认 EngineWorker 是 Host capability 的边界未被破坏；Phase 3 未实现 EngineWorker / RPC 生产代码。
- 总控必须提醒并确认已完成 NEW / OLD Agent tool calling 状态机严格对照 review；该 review 通过后，Phase 3 才能进入提交 / PR 流程。

### 用户确认点

- 是否确认普通工具失败进入 LLM 上下文，由模型恢复或解释。
- 是否确认 awaiting / suspend 不在 Phase 3 提前实现，后续由 issue #4 拆子 issue 处理。

## 8.5 Phase 3 后置 patch：provider_state / reasoning roundtrip

### 动机

`provider_state` 来自模型 provider 的 tool call 响应。Agent 在下一轮把 assistant tool_calls 注入给 Runner 时，需要按 provider 协议把必要状态原样带回 provider，避免某些 provider 的多轮工具调用协议断链。

当前 `ToolCallProviderState` 只有一个已确认形态：`GeminiToolCallState`。Phase 3 先确保 `provider_state` 有强类型通道，并能随 tool roundtrip 保留；Phase 3 后再用专门 patch 判断是否扩展更多 provider-specific state。

Phase 3 为了先落地普通工具闭环，可以按 OLD 已证明可行的行为，把 `reasoning_content` 无条件写回后续请求。这个行为的依据来自部分模型 API 文档：思考模式下多轮工具调用时，模型可能在返回 tool_calls 的同时返回 `reasoning_content`，后续请求保留历史 `reasoning_content` 可能获得更好表现。

但这只是 Phase 3 过渡实现，不能直接变成 NEW 的跨 provider 稳定契约：

- 有些 provider 可能要求写回 `reasoning_content`。
- 有些 provider 可能不要求写回。
- 有些 provider 可能拒绝带回不支持的 reasoning 字段。

因此，Phase 3 后置 patch 要把 `reasoning_content` 无脑写回改为 provider-specific 非无脑写回：哪些 provider 需要写回、写到哪里、由 Agent message 承载还是由 provider_state / provider adapter 投影，都必须按 provider 明确建模。

### patch 目标

- 复核 Phase 3 实现中 `ToolCallProviderState` 的数据流：provider 响应 -> RunnerEvent / ToolCallRequest -> EngineEvent -> assistant tool_calls -> 下一轮 Runner 请求。
- 基于真实 provider smoke、API 文档和 NEW / OLD 对照结果，判断哪些 provider 需要写回 `reasoning_content`，以及是否需要把它纳入 provider-specific state。
- 如需支持 reasoning roundtrip，优先通过 `ToolCallProviderState` 的封闭联合扩展或 provider adapter 的显式请求投影表达，而不是把 `reasoning_content` 塞进 `metadata` 或长期在所有 provider 的 `AssistantMessage` 中无条件保留。
- 明确 provider adapter 负责把 provider-specific state 投影回最终请求 payload；Agent 只传递强类型 state，不拼 provider 私有字段。

### 禁止事项

- 禁止把 Phase 3 的无条件写回 `reasoning_content` 过渡实现固化为 NEW 默认行为。
- 禁止用 `metadata`、裸 dict、`Any` 或 provider 字符串分支承载 roundtrip state。
- 禁止让 Runner 重新执行工具或依赖 ToolExecutor。
- 禁止让 Host / EngineWorker 的治理所有权进入 provider_state。

### 验收信号

- 每个 provider 的 reasoning roundtrip 策略有明确证据来源：API 文档、真实 smoke 或可复现 provider 行为。
- `ToolCallProviderState` 仍是封闭强类型联合；当前仅有 `GeminiToolCallState` 时，不提前伪造其它 provider state。
- 不需要 reasoning roundtrip 的 provider 不会被写入多余 reasoning 字段。
- 需要 reasoning roundtrip 的 provider 能在多轮 tool calling 中保持协议不断链。

## 9. Phase 4 状态：已取消独立实施

### 当前决策

Phase 4 不再作为独立 Engine 迁移阶段实施。

`suspend` / `run_suspended` / `ToolAwaitingOutcome` 已转入 GitHub issue #4 跟踪，后续必须在 issue #4 下拆分子 issue 后重新计划。`docs/engine/phase4-plan.md` 与 `docs/engine/phase4-plan-review.md` 仅作为历史草案与历史 review 记录保留，不再作为当前实施 handoff 或放行 gate。

### 原因

awaiting / suspend 不是单纯 Engine 事件问题。若只在 Engine 侧产出 `tool_awaiting` / `run_suspended`，但 Host wait record、monitor、resume 输入、恢复治理、取消 / 超时 / 丢失治理尚未落地，会形成半截能力。当前架构下应由 Host 后续统一设计长事务等待与恢复闭环。

### 对后续 Phase 的影响

- Phase 5 不得把 Phase 4 作为前置条件。
- Phase 5 不得实现 `ToolAwaitingOutcome`、`tool_awaiting`、`run_suspended` 或 resume API。
- Phase 5 若遇到需要 Host 后续接管的状态，必须以当前已存在的 EngineEvent 事实和保守 terminal 收口表达，不得借用 `run_suspended`。
- issue #4 继续作为 approval、detached、retry_after、artifact_ready、awaiting / suspend / resume 等扩展 outcome 和 Host 长事务治理的总跟踪入口。

## 10. Phase 5 详细计划：Phase 5 with Phase 6 doc closeout

### 目标

合并原 Phase 5 和 Phase 6。Phase 5 是最后一个 Engine 实现收口阶段；原 Phase 6 不再作为第二个实现阶段，只作为同一 PR 中的 README / docs / issue 验收收口部分。

Phase 5 目标是补齐 Engine 层剩余自洽 Agent 能力：`finish_reason=length` 受次数限制续写并拼接最终内容、continuation 轮固定 `tools=()`、`content_filter` 不续写、取消优先和 Phase 3 既有收口回归。

Phase 5 完成后，NEW Engine 可以在 Engine 层进一步接近 OLD Agent / AsyncAgent 主能力对齐，但必须明确排除 Host / Service / issue #4 能力：context overflow / context compaction 协作、Host wait record、monitor、resume、ToolRuntime、ToolRegistry、conversation memory、transcript、trace store、OLD `TruncationManager` / fetch_more / cursor / TTL / scope token 等均不属于本阶段。

### 前置条件

- Phase 3 普通 completed / failed tool calling 主链路已合并。
- Phase 4 已取消独立实施，`suspend` / `run_suspended` / `ToolAwaitingOutcome` 不作为 Phase 5 前置。
- Phase 0 / Phase 3 既有 contracts 已稳定；若 Phase 5 需要扩展 `AgentPolicy`，必须按强类型契约演进并补测试。
- 用户确认本轮 Engine 迁移不把 context overflow / `context_compaction_requested` 纳入范围；后续在实施 Host 上下文治理时，再作为独立 issue 完善 Engine 协作事件与状态机。
- 用户确认 OLD `TruncationManager` / fetch_more / cursor / TTL / scope token / tool-level truncation manager 后移 Host / ToolRuntime，不进入 Phase 5。

### 迁移 Agent 任务

- 扩展 `AgentPolicy` 的必要 continuation 策略入口；不得加入 `max_context_tokens`、`context_compaction_trigger_ratio` 或其它 context compaction 字段。
- 实现 `finish_reason=length` continuation：追加 continuation prompt、下一轮 Runner 调用固定 `tools=()`、不进入普通 tool loop、不消耗连续失败工具批次保护、受 `continuation_max_attempts` 限制、拼接多次 partial content，最终产出完整 final answer；`content_filter` 不 continuation。
- 普通 provider error、HTTP retry exhausted、Runner protocol error 仍按 Phase 2/3 既有 `run_failed` 路径收口；Phase 5 不新增开放式 provider fallback 或降级策略。
- Agent 每轮 iteration 起点检查取消。
- Runner 阻塞边界观察取消。
- Agent 在提交 final_answer 前再次检查取消。
- 取消命中后产出 run_cancelled，不产出 final_answer。
- 在同一 PR 末尾执行原 Phase 6 文档收口：根据已落地代码更新必要 README、计划状态和 issue 汇总；README 只写当前事实，不写未来设计。

### 允许复用的 OLD implementation 片段

- `AsyncAgent._run_loop` 中 `finish_reason=length` continuation、partial content 累积、取消优先、既有收口场景判断；必须拆分为 NEW 小函数，不能照搬 God function。
- `cancellation.py` 的 await_or_cancel 思路。
- OLD context budget、context overflow 与 `TruncationManager` 代码只作为“哪些能力不迁入本轮 Engine”的边界证据，不作为 Phase 5 implementation 来源。

### 禁止迁移项

- conversation memory。
- 语义压缩。
- Engine 写 transcript。
- Engine 调用 LLM 做压缩摘要。
- Engine 内 compact / retry。
- provider context overflow 强类型识别。
- `context_compaction_requested` 事件生产路径。
- `context_compaction_required` recoverable failure 状态机。
- `max_context_tokens`、`context_compaction_trigger_ratio` 或 projected context trigger。
- `run_suspended` / `ToolAwaitingOutcome` / resume API。
- Host wait record、monitor、resume、approval、detached、retry_after、artifact_ready。
- Engine 理解 fins/doc/web 业务语义。
- ToolRegistry / ToolRuntime、权限、审计、路径白名单、工具超时治理。
- OLD `TruncationManager` / fetch_more cursor / TTL / scope token / tool-level truncation manager。
- DuplicateCallGuard 语义级重复调用策略；如需推进必须单独开 issue。
- provider-specific reasoning roundtrip patch；继续按 Phase 3 后置 patch / issue #10 跟踪。
- Runner response cleanup hardening；只可记录风险，不进入 Phase 5 实现。
- watchdog、取消超时升级、lost 判定等取消治理增强；这些由 issue #3 跟踪。

### 测试要求

- AgentPolicy continuation 字段构造和非法值测试。
- continuation 次数限制、prompt 注入、partial content 拼接、最终回答完整性测试。
- `content_filter` 不 continuation，继续产出 `filtered=True, degraded=True`。
- continuation 达到上限 terminal、普通 provider error 既有 `run_failed` 回归测试；max_iterations force-answer 与连续失败工具批次保护只做回归确认，不作为 Phase 5 新能力。
- 取消优先级测试：取消与 final_answer 竞争时产出 run_cancelled。
- Runner 阻塞取消测试。
- Agent terminal 前取消检查测试。
- Engine 不写 transcript / memory 的架构测试。
- Host-only 能力防回流测试：Engine 不导入 ToolRegistry / ToolRuntime / TruncationManager / trace store / transcript / conversation memory。

### pyright 要求

- continuation policy 和既有收口策略必须严格类型化。
- 不允许用字符串魔法值表达终态或 budget 状态；使用 enum / 封闭类型。

### README / docs 同步要求

- Phase 5 计划阶段不更新 README。
- Phase 5 代码实现、code review、OLD/NEW 专项 review 通过后，作为同一 PR 的文档收口部分更新必要 README。
- `dayu/engine/README.md` 只写当前已落地事实：continuation、取消优先和 Phase 3 既有回归状态。
- `dayu/engine/README.md` 不得写 context overflow / `context_compaction_requested` 已落地。
- README 不得写 Host wait record / monitor / resume、conversation memory、语义压缩、trace store、OLD `TruncationManager` / fetch_more / cursor 已可用。
- 若涉及测试分层变化，只更新 `tests/README.md`；若涉及整体分层事实变化，才检查 `dayu/README.md`。

### review Agent 审查重点

- 取消是否绝对优先于 final_answer。
- continuation 是否受 AgentPolicy 控制，且没有覆盖 Phase 3 的 max_iterations force-answer / 连续失败工具批次语义。
- 是否把 OLD `TruncationManager`、fetch_more、cursor、TTL、scope token 或工具级截断误迁回 Engine。
- continuation 是否真正拼接最终内容，且 `content_filter` 不 continuation。
- Phase 5 plan review、Phase 5 code review、日常 `docs/code_review.md` review 必须通过。
- 常规 code review 通过后，必须再执行一轮 NEW / OLD continuation / 既有收口策略 / 取消优先级严格对照 review。该 review 以 OLD AsyncAgent / Runner 高可靠实现为强参考源，但必须确认 NEW 只对齐“final answer text continuation”的可靠性目标，不机械迁 OLD context budget / context overflow / soft / hard / capping / compact，也不迁 transcript、conversation memory、trace store、Host 治理职责或 OLD `TruncationManager`。

### 总控验收标准

- Phase 5 形成一个 PR，命名口径建议为 `Phase 5 with Phase 6 doc closeout`。
- 取消、continuation 和 Phase 3 既有 fallback 回归测试通过。
- pyright 通过。
- Phase 3 max_iterations force-answer、连续失败工具批次、普通 tool calling 回归测试通过。
- 总控必须提醒并确认已完成 NEW / OLD continuation / 既有收口策略对照 review；该 review 通过后，Phase 5 才能进入提交 / PR 流程。
- 原 Phase 6 文档收口已经在同一 PR 完成，README 与当前代码一致，issue #2 / issue #4 状态清楚。
- README 与当前实现一致。

### 用户确认点

- 是否需要将 DuplicateCallGuard、provider-specific reasoning roundtrip、Runner response cleanup hardening 分别开后续 issue。
- 是否需要为 context overflow / Host context compaction 协作创建后续独立 issue。
- 是否确认 Phase 5 合并原 Phase 6 文档收口后，下一步进入 Host / ToolRuntime / capability 后续迁移。

## 12. 跨阶段架构测试

以下测试必须长期保留，不得只在 Phase 0 临时存在：

- Engine 包根导出测试：Phase 0 只允许导出 contract 类型；Phase 2 之后只允许导出 `run_agent_messages`、`run_agent_and_wait` 和 contract 类型；额外导出实现类、兼容 wrapper、旧 re-export 时测试失败。
- import boundary 测试：Engine 不得导入 Host / Service / UI 具体实现。
- Tool boundary 测试：Engine 不得导入 Host ToolRegistry、ToolRuntime 具体实现、doc/web/fins tools。
- Fins boundary 测试：Engine 不得导入 `dayu.fins.storage` 具体实现；财报文档读取不能经 Engine 直连文件路径。
- Runner boundary 测试：Runner 不得依赖 ToolExecutor，不得执行工具。
- Trace boundary 测试：Engine 不得依赖 ToolTraceRecorder、JsonlToolTraceStore 或 trace schema 真源。
- Weak typing 测试：Engine 公共 contract 不得出现 `Any`、`object`、无类型参数、无类型返回值、开放 metadata 承载显式契约事实。
- Event contract 测试：EngineEvent / RunnerEvent 事件名和 data 类型必须封闭；新增事件必须新增强类型 data 和测试。
- Outcome 穷尽测试：`ToolExecutionOutcome` 新增分支必须触发穷尽匹配测试失败，直到实现明确处理。
- Terminal 唯一性测试：每个 run 只能有一个 terminal event，`final_answer`、`run_failed`、`run_cancelled`、`run_suspended` 互斥。
- Cancellation priority 测试：取消命中后不得继续产出 final_answer。
- Metadata 测试：usage、provider_request_id、raw_payload、protocol error 等显式事实必须在 data 中，不得进入 metadata。
- README 触发检查：修改 `dayu/engine/`、分层边界或测试约定时必须检查对应 README。

## 13. GitHub issue / PR 策略

- issue #2 作为 Engine 迁移总控 issue，记录设计、计划、review、总控验收和阶段进展。
- 每个 Phase 建议单独开子 issue，issue 标题格式建议为：`Engine Phase N: <名称>`。
- 每个 Phase 原则上单独 PR。当前已确认原 Phase 6 合并为 Phase 5 的文档 / 验收收口部分；后续若再合并多个 Phase，必须由总控和用户确认。
- 扩展 outcome 使用 issue #4 作为总跟踪，并为每个扩展分支单独开子 issue。
- 取消治理增强使用 issue #3 跟踪，不塞进 Engine 初始迁移。
- Host ToolRuntime / ToolRegistry 具体实现必须另开 Host 迁移 issue。
- web tools capability、doc tools capability、fins tools / fins storage 实现、processors 归属与迁移、trace observer / audit / metrics / alerting、conversation memory 与语义压缩都必须另开 issue。

每个 PR 合并前的验收顺序：

1. 迁移 Agent 完成实现、测试、pyright、README/docs 同步。
2. 迁移 Agent 在 PR / issue 中列出改动、验证、未覆盖风险。
3. review Agent 审查代码、测试和边界。
4. 总控 Agent 检查是否符合本计划和 issue 范围。
5. 用户确认。
6. 才能合并或进入下一 Phase。

## 14. 风险与停止条件

必须停止实现、回到设计讨论的情况：

- 需要新增或修改 Engine 公共 contract，但 design / migration-plan 未覆盖。
- 实现要求 Engine 导入 Host、Service、UI、ToolRegistry、doc/web/fins tools 或 trace recorder。
- Runner 需要执行工具或依赖 ToolExecutor。
- ToolExecutor 需要恢复 `get_schemas()`、`get_tool_display_info()` 或其它 Registry 能力。
- `ToolExecutionOutcome` 需要新增 `approval_required`、`detached`、`retry_after`、`artifact_ready` 等分支。
- awaiting / suspend 需要 Engine sleep、轮询、创建后台任务、写 wait record 或新增 resume API。
- context budget 需要 Engine 内 compact / retry、语义压缩、conversation memory 或业务语义。
- 财报工具需要绕过 `dayu.fins.storage` 直接读文件。
- 为了让旧测试通过而需要兼容 wrapper / facade / re-export。
- 为了快速实现而出现 `Any`、`object`、裸 dict、开放 metadata 承载契约事实。
- README 要写“未来会支持”才能解释当前接口。

必须拆分新 issue 的情况：

- Host ToolRuntime / ToolRegistry 具体实现。
- web tools capability。
- doc tools capability。
- fins tools / fins storage 实现。
- processors 归属与迁移。
- approval / detached / retry_after / input_required / artifact_ready / delegated 等扩展 outcome。
- conversation memory 和语义压缩。
- trace observer / audit / metrics / alerting 的 Host 实现。
- watchdog、取消超时升级、lost 判定、强制终止等取消治理增强。

必须由用户或总控确认的情况：

- Phase 范围需要合并、拆分或跨层。
- Engine 包根导出集合需要变化。
- `Source`、`DocumentProcessor`、`ProcessorRegistry` 的最终归属需要定为 Fins capability、document capability 或独立 contract 包。
- `correlation_id` 语义需要从可选中性关联 ID 扩展。
- README 触发范围存在争议。
- 实现无法同时满足设计文档、review 结论和 `AGENTS.md`。

## 15. 下一步

下一步不是实现，而是 review 本计划。

建议 review Agent 重点审查：

- Phase 切片是否足够小，是否能独立 PR。
- 每个 Phase 的“不迁什么”是否明确。
- review 与总控验收标准是否能防止边界回退。
- 是否遗漏长期架构测试。
- 是否把 Host / capability / fins / trace / memory 的后续工作误塞进 Engine core。

本计划 review 通过、总控检查通过并经用户确认后，才能从 Phase 0 开始实施。
