# 测试手册

本文件只记录当前 `tests/` 下已经存在的测试分层、运行方式与维护约定。测试事实以当前代码和测试目录为准；新增测试层级后，应同步更新本文件。

## 默认环境

项目默认测试环境为 Python 3.11。运行测试或类型检查前，先激活仓库内虚拟环境：

```bash
source .venv/bin/activate
```

当前类型检查配置覆盖 `dayu/`、`tests/`、`utils/`，并排除 `workspace/`、缓存目录、隐藏目录与 `.venv/`。

## 常用命令

运行当前契约与 Engine 相关测试：

```bash
pytest tests/contracts tests/engine -q
```

运行类型检查：

```bash
pyright
```

也可以按目录或文件收窄测试范围：

```bash
pytest tests/contracts -q
pytest tests/host -q
pytest tests/host/test_phase2_tool_runtime_truncation.py -q
pytest tests/host/test_phase2_tool_runtime_eventlog.py -q
pytest tests/host/test_phase2_tool_runtime_boundary.py -q
pytest tests/host/test_phase3_conversation_memory_projection.py -q
pytest tests/host/test_phase3_run_input_builder.py -q
pytest tests/host/test_phase3_multiturn_smoke.py -q
pytest tests/host/test_phase3_boundary.py -q
pytest tests/contracts/test_tool_declaration.py -q
pytest tests/host/test_phase5_multiturn_no_governance_smoke.py -q
pytest tests/host/test_phase8_attempt_supervisor.py -q
pytest tests/engine/contracts -q
pytest tests/engine/runners/openai/test_event_flow_ordering.py -q
```

## 当前测试分层

### `tests/runtime/`

运行时基础设施测试，覆盖 `dayu.runtime` 的层中立边界、取消 helper 与日志装配：

- import boundary：阻止 runtime 反向依赖 Engine、Host、Service、UI、fins 或引入运行期 HTTP 客户端。
- cancellation：覆盖取消等待 helper 的完成、取消与异常传播语义。
- logging：验证 `dayu.runtime.log` 的 logger 装配、CLI 风格级别解析、`VERBOSE` / `CRITICAL` 级别契约，
  并验证 `dayu.runtime.log_levels` 只提供公共日志级别常量、不注册 stdlib logging level。

### `tests/contracts/`

公共协作契约测试，覆盖 `dayu.contracts` 的稳定边界：

- package exports：锁定包根 `__all__` 白名单，阻止未承诺符号泄漏。
- import boundary：阻止公共契约层反向依赖 Engine、Host、Service、UI、fins 或运行期 HTTP 客户端。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入公共契约源码。
- ToolExecutionOutcome / ToolResult / ToolCall 等契约测试：覆盖工具调用 provider state、工具结果信封、工具执行 outcome 封闭联合与穷尽匹配。
- tool declaration：覆盖 P5 最小 `@tool(..., truncate=ToolTruncateSpec(...))` 声明能力，确认
  `ToolDefinition` / `ToolBundle` 只投影 `ToolSchema` 给 Engine，`ToolTruncateSpec`、`ToolDisplayInfo`
  展示 metadata、tags 与 executor binding 不进入 LLM-facing schema，并拒绝工具名与 schema 名错位或
  bundle 内重复工具名。

### `tests/engine/`

Engine 契约、包根导出、事件契约与架构边界测试，覆盖 `dayu.engine` 的稳定边界：

- package exports：锁定 `dayu.engine.__all__`，阻止未承诺入口、实现类或取消异常出现在包根。
- import boundary：阻止 Engine 反向依赖 Host、Service、UI、fins、工具执行实现、处理器或 trace 私有模块；OpenAI runner 子树内允许当前实现所需的 `aiohttp`。
- weak typing guard：扫描 `dayu.engine` 源码，守住强类型签名、封闭联合与 metadata 类型边界。
- 事件契约与消息契约：覆盖 EngineEvent、RunnerEvent、AgentMessage、metadata、终态事件集合等结构约束。
- Agent 状态机：覆盖无工具 final / failed / cancelled、普通 completed / failed tool calling、工具结果投影、max iteration force-answer、连续失败工具批次保护、awaiting 拒绝与取消优先级。
- smoke 脚本轻量测试：覆盖 provider smoke 与 tool-call smoke 的参数解析、缺 key 跳过、安全输出和 fake 工具行为，不做真实联网。

### `tests/host/`

Host 当前 Run harness、RunEventStore、ToolRuntime、Conversation Memory / RunInputBuilder、P4 context compact
与 P5 no-full-governance integration guard 测试，覆盖 `dayu.host` 当前已落地的边界：

- run harness：验证 public `start_run` 可经 Host 调用 Engine 函数式入口，并把 `EngineEvent` 翻译为已 append 的 `RunEvent`。
- event store：验证 append-only、per-run cursor、exclusive replay、replay-then-follow 订阅和 terminal 后订阅结束。
- host logging：验证 `VERBOSE` 可串起已落地 Host 主路径，且不泄漏用户输入、final answer、工具参数 / 结果、
  raw cursor 或 `scope_token`；验证 EventStore 在 DEBUG 下不刷 preview append、subscribe wait / batch。
- run harness eventlog：验证 `USER_INPUT_ACCEPTED` append-before-engine / append-before-stream、preview 不污染
  terminal result、结果只从已 append terminal event 推导，worker / proxy 异常和 Engine stream 无终态正常结束
  会落 Host-owned canonical failure 事件，并验证 RunInput trace 调试缓存与更小的消息诊断缓存分别按容量淘汰。
- tool-call smoke：通过内部 `LocalRunHarness` 注入 fake ToolExecutor，覆盖 Runner tool call -> Engine 工具闭环 -> Host RunEvent stream。
- ToolRuntime truncation：覆盖 text chars、text lines、list items、binary bytes、no-spec no-truncate、
  explicit target only、field_path 优先级、路径不匹配不截断、execute-time cursor facts、非成功 outcome 不创建
  cursor、single-use、并发 single-use、TTL expired、opportunistic cleanup、limit clamp 与策略 / data 类型不匹配。
- ToolRuntime eventlog：覆盖截断 / cursor issued / fetch_more requested / completed / failed / denied / expired
  均通过 canonical RunEvent 表达，handle 阶段 denied / expired 写入可信 owner run，terminal 后不追加事实，
  非权限失败不标记 denied，且 EventLog 不保存明文 scope token 或完整大结果。
- ToolRuntime boundary：覆盖 Host 包根只导出 Run 级补读入口与契约类型，Engine 不 import Host / ToolRuntime，
  Host public scope token 只能通过受控 handle 交付，跨 run 补读不污染请求伪造的 run，Engine LLM-facing
  projection 会为截断结果生成 `fetch_more_args`。
- Conversation Memory projection：覆盖 `USER_INPUT_ACCEPTED`、canonical final answer、ToolRuntime / Engine tool fact
  从 EventLog 投影，preview / reasoning / delta 不进入 memory，assistant final answer 不自动成为 verified claim，
  memory item 携带 provenance / trust / scope 元数据，`USER_INPUT_ACCEPTED` scope 使用封闭枚举并非法 fail fast，
  非 SESSION scope clear patch fail fast，不同 session 不串 memory。
- RunInputBuilder：覆盖 memory block 顺序、tool facts / evidence anchors 与 assistant history 分离、
  tool facts 独立 section、source event cursor 输出、recent raw turns 单 section header、pinned state 预算外全量注入、
  older pool 新到旧消费预算后按时间顺序渲染、internal-only `RunInputBuildTrace`、预算裁剪原因、
  超大旧轮语义降级与 current user 末尾注入。
- multiturn smoke：覆盖单进程顺序第二个 Run 通过真实 `LocalRunHarness -> RunInputBuilder` 路径看到 previous run
  canonical final answer 与 tool summary。
- P4 context compaction：覆盖 Host 内部 token estimator、deterministic compact 保留当前用户问题 /
  pinned state / evidence anchors / source cursor / tool facts、compact block 多 item section 单 header、
  当前 deterministic compact 的 `degraded_item_count=0` 语义、no-op compact 不 retry、Engine overflow 后同一
  Run 内 internal attempt retry、不重复追加 `USER_INPUT_ACCEPTED`、retry 上限耗尽后的 Host-owned terminal
  failure、负数 retry 上限 fail fast、非 terminal compact trigger 也写入 `context_overflow_observed`、
  同一 Run overflow 前已 append 的工具事实进入 compacted attempt、trace 缓存缺失失败收口、caller system
  prompt 顺序、非法入口消息拒绝、final answer 内部字段回显过滤，以及 Host public API 不导出 compact
  coordinator。
- P5 no-full-governance smoke：覆盖公共 `huge_echo` 工具通过 `ToolDefinition` / `ToolBundle` 声明、
  fake provider 只模拟 LLM tool call output、真实 Engine Agent tool loop 调用 `ToolExecutor.execute`、
  `ToolRuntimeToolExecutor -> InMemoryToolRuntime -> huge_echo executor` 产生 truncate / cursor facts、
  截断 ToolMessage 包含 LLM-readable `truncation.next_action="fetch_more"` 与 `fetch_more_args`、模型在同一 run
  内通过 Engine tool loop 发起 framework `fetch_more`、Host ToolRuntime 路由 framework 补读并在 terminal 前追加
  fetch_more facts、terminal 后 Host public `fetch_more_tool_result` typed failure 不追加 EventLog、
  后续 Run 的 RunInputBuilder 看到 previous run user / final / tool / fetch_more facts 与 source cursor、
  compact retry 不重复 `USER_INPUT_ACCEPTED`，真实 provider smoke 按 `utils/` smoke 既有范式写死
  `mimo-v2.5-pro-plan` `ProviderCase` 且不读取配置层级，并显式锁定
  `MimoThinkingExtension(enabled=True)` 属于 hardcoded ProviderCase，`--thinking` 只在 real-provider 路径回显
  provider reasoning delta、无 delta 时回退聚合 reasoning、final answer 前缀，覆盖 reasoning delta 在 final
  event 到达前随 RunEvent 流即时输出，以及 preview / reasoning 不进入下一轮运行态输入。
- P3 boundary：覆盖 Host 包根不导出 internal memory store / builder / trace，Engine 不 import Host memory，
  `USER_INPUT_ACCEPTED` append 失败不启动 Engine，入口历史 transcript 形态 fail fast 且不污染 EventLog / memory，
  Host-owned failure terminal 会触发 memory projection，reasoning / display completed 不进入 RunInput replay。
- P6 durable EventLog / projection（`tests/host/test_phase6_*.py`）：
  - `host_storage_transaction`：post-commit hook 仅在 COMMIT 后触发，事务体异常时回滚不触发，
    并发写者通过 `asyncio.Lock` 串行化。
  - `durable_event_store`：per-run cursor 单调、跨 run global position 单调，terminal 之后
    append fail-fast，subscribe 先 replay 已有事件再阻塞并在 terminal 后结束，按 global position
    分页消费，engine 来源缺 `source_engine_event_id` 时拒绝，`latest_event_position` 跟踪最大值。
  - `run_event_serializer`：常见 RunEventData round trip，`RUN_FAILED` 在 Engine `RunFailedData`
    与 Host `HostRunFailedData` 之间靠 `exception_type` 区分，type↔data 不匹配 fail-fast，
    `schema_version` 不匹配 fail-fast，`type_name` 与 `event_type` 不匹配 fail-fast。
  - `run_state_store`：FINAL_ANSWER append 后 run state 自动转 SUCCEEDED 并记录 terminal cursor，
    terminal `RunResult` JSON encode/decode round trip，attempt 创建 + 状态推进 + 终态字段写入。
  - `projection_checkpoint`：observer drain 后 checkpoint 推进到最新 position，
    `RetryableProjectionError` 标 RETRYABLE_FAILED 不前进 success position，普通异常进入
    BLOCKED_FAILED 并记录错误码，`ProjectionStore.advance_success` 拒绝倒退，`lag_events`
    等于 MAX(position) - last_success_position。
  - `memory_rebuild`：required memory projection 满足 USER_INPUT_ACCEPTED 永不丢失、成功终态
    写 assistant final、Engine `RUN_FAILED` 与 Host-owned `RUN_FAILED` 写中性 terminal summary、
    cancelled / suspended 仅保留用户输入。
  - `timeline_audit_projection`：timeline observer 仅累积 canonical 事件且按 cursor sequence
    升序，audit observer 按 global position 升序累积元数据并对 preview kind 跳过。
  - `review_fixes`：覆盖本轮 P6 review 修复 —— 四种终态 RunResult 快照与 terminal event
    同事务持久化、`source_engine_event_id` 唯一约束违反映射为 `ValueError`、
    `ProjectionStore.advance_success` 同 position 重放幂等且严格拒绝倒退、
    `ProjectionCoordinator._drain_lock` 防并发 drain 重入、多 run 并发 append global
    position 单调、post-commit hook 抛异常不污染事务、事务体异常 ROLLBACK。
  - `durable_harness_integration`：通过 `build_durable_harness` 注入 stub `WorkerProxy`,
    覆盖 `harness.start_run` -> Engine event stream -> append -> terminal -> coordinator.drain
    端到端路径,守护 attempt 终态写入、observer caught_up、共享 memory store 无 split-brain、
    RunResult 快照可读。
- P7 tool trace projection（`tests/host/test_phase7_*.py`）：覆盖
  `RunInputContextFactBuilder` 派生 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`` canonical
  fact、`ToolTraceJsonlSink` JSONL + raw payload blob 落盘、provider secret
  scrub、`ToolTraceObserver` 5 类 record 派发、``DurableHarnessConfig.tool_trace_path``
  装配开关与 ``tool_trace_v2_host`` schema 字面量边界。
- P8-S3 attempt supervisor（`tests/host/test_phase8_attempt_supervisor.py`）：覆盖
  `AttemptSupervisor.lease_context` 正常 acquire / yield / 退出清理；renew loop 在 fake
  clock 下 renew 成功保持 fencing token 不变、刷新 `lease_expires_at`；renew 命中
  `FENCED` 后 session 失活并通过 `wait_owner_lost` 暴露 typed `FENCED`；renew 抛 storage
  异常时映射为 typed `STORAGE_ERROR`，masked 日志覆盖且 owner secret 明文不泄漏；
  `DurableHarnessConfig.attempt_lease_config` 装配入口可覆盖默认 TTL / interval / prefix；
  `LocalRunHarness` 仅薄委托 supervisor，并在 `_finish_attempt_if_durable` 通过
  `close_attempt_with_diagnostic_state` 完成 owner-aware 收口；owner CAS 命中失败时
  diagnostic close 返回 `False` 且不覆盖未来状态；harness 在 owner-lost 后停止从 Engine
  拉取 / append late event。
- public boundary：锁定 `dayu.host.__all__`，允许 Run 级 `start_run`、`stream_run_events`、`get_run_result`，
  以及 P2 Run 级 `get_tool_fetch_more_handle`、`fetch_more_tool_result`，阻止 `EngineWorker`、`LocalProxy`、
  `ToolExecutor`、`InMemoryToolRuntime`、`ToolRuntimeToolExecutor`、`InMemoryConversationMemoryStore`、
  `DefaultRunInputBuilder`、`RunInputBuildTrace`、`run_agent_messages` 泄漏为包根 API。
- import boundary：阻止 Host 导入 `dayu.fins`、`dayu.service`、`dayu.ui`。
- weak typing guard：扫描 `dayu.host` 源码，阻止 `Any`、`object`、无类型签名与裸容器注解。

### `tests/utils/`

`utils/` 下分析脚本的单元测试，覆盖：

- `test_analyze_tool_trace_host.py`：验证 P7 trace analyzer
  (`utils/analyze_tool_trace_host.py`) 按 ``idempotency_key`` 去重、严格拒绝
  OLD ``tool_trace_v2`` schema、检测重复 tool_call、truncation 后未续读
  fetch_more、fetch_more 引用未知 cursor、provider_protocol_error 计数、
  final_response 是否存在与同 run 内 ``source_event_position`` 单调性。

### `tests/engine/contracts/`

Engine contract 的细粒度测试，当前覆盖：

- `messages`：AssistantMessage / AssistantToolCall 与 provider state roundtrip 契约。
- `runner_events`：RunnerEventData 联合、RunnerHTTPErrorCode、RunnerHTTPErrorData、HTTP error 与
  context overflow 错误枚举、HTTP error 到 Done(ERROR) 的收口契约。
- `runner_spec`：RunnerSpec 字段集合、provider reasoning / thinking extension、stream usage 能力字段与构造路径。
- import boundary：Engine contract 子包不得越过自身契约边界引入上层依赖。

### `tests/engine/runners/openai/`

OpenAI-compatible Runner 的 provider 协议测试，覆盖从 payload 构建、provider 响应解析到 RunnerEvent 事件流的行为：

- payload：消息、工具 schema、reasoning content、provider 扩展、stream usage gating、禁止额外 payload 袋。
- SSE：content delta、reasoning delta、tool call delta、tool call 聚合、usage、`[DONE]`、多行 data、跨 chunk UTF-8、非法 UTF-8、尾部无换行、空 choices + usage。
- non-stream：非流式响应、thought 标签处理、stream / non-stream 终态语义一致性。
- 错误与重试：协议错误、HTTP error 分类、context overflow classifier、未知状态码、retry backoff、
  重试耗尽后的事件收口；context overflow 覆盖 `context_length_exceeded` 结构化 code、OLD 多 provider
  message 信号矩阵、结构化非 overflow code 优先级与普通 client error 负例。
- 取消与资源：取消边界、取消后不补 done 事件、close 释放资源。
- 架构边界与协议表面：Runner 只产出 RunnerEvent，不依赖 ToolExecutor，不暴露任意 `**kwargs` 或 `set_tools`，事件流顺序保持单调并以唯一终态收口。

本目录内已有 `_fakes.py`、`_factories.py`、`_sse_helpers.py` 作为局部测试 helper。

## 维护约定

- 新增公共契约必须补 package export、import boundary、weak typing guard 相关测试。
- 新增 Runner 行为必须优先补协议事件流测试，确保下游 Engine loop 能无歧义消费。
- 状态机测试必须覆盖输入事实、状态分支、事件顺序、终态收口。
- 架构边界测试必须阻止反向依赖，尤其是下层导入上层实现或私有治理概念。
- 测试不得为了旧接口在生产代码中保留兼容逻辑；测试应跟随当前实现边界迁移。
- 测试 helper 可以放在对应测试子目录内，例如 `_fakes.py`、`_factories.py`、`_sse_helpers.py`。
- helper 不应成为生产代码替代品，也不应隐藏关键断言；协议事实和终态断言应保留在测试用例中。

## 类型与弱类型守护

测试必须配合 `pyright` 使用。公共契约和 Engine 契约的测试已经通过 AST 扫描守护弱类型边界，新增契约时应保持同等严格度。

- 禁止通过测试 helper 引入 `Any` / `object` / 裸 `dict` 的公共契约逃逸。
- 如果测试需要构造 JSON，应使用当前项目已有 `JsonValue` 类型或局部私有 helper，不得把弱类型 JSON 袋扩散到生产接口。
- 对封闭联合新增成员时，应同步更新穷尽匹配测试，避免新分支在类型检查中静默漏处理。

## README 更新边界

本文件只描述当前 `tests/` 已存在的事实，不写用户手册、Engine 设计文档、完整 review prompt、未落地测试体系或时间敏感记录。

如果之后新增测试层级、测试运行方式或测试维护规则发生变化，应在对应变更中同步更新本文件。
