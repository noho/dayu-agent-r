# 测试手册

本文件只记录当前 `tests/` 下已经存在的测试分层、运行方式与维护约定。测试事实以当前代码和测试目录为准；新增测试层级后，应同步更新本文件。

## 默认环境

项目默认测试环境为 Python 3.11。运行测试或类型检查前，先激活仓库内虚拟环境：

```bash
source .venv/bin/activate
```

当前类型检查配置覆盖 `dayu/`、`tests/`、`utils/`，并排除 `workspace/`、缓存目录、隐藏目录与 `.venv/`。

## 常用命令

运行当前契约、Host、Runtime 与 Engine 测试：

```bash
pytest tests/contracts tests/host tests/runtime tests/engine -q
```

运行类型检查：

```bash
python -m pyright dayu/ tests/ utils/
```

也可以按目录或文件收窄测试范围：

```bash
pytest tests/contracts -q
pytest tests/host -q
pytest tests/host/test_tooling_options.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py tests/host/test_event_log_store.py tests/host/test_event_log_multiprocess.py tests/host/test_idempotency_store.py -q
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q
pytest tests/host/test_session_lifecycle.py tests/host/test_run_attempt_transitions.py -q
pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
pytest tests/host/test_admission_multiprocess.py tests/host -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q
pytest tests/host/test_phase5_local_execution_integration.py -q
pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q
pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q
pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py -q
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q
pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
pytest tests/runtime -q
pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q
pytest tests/engine -q
pytest tests/engine/contracts -q
pytest tests/engine/runners/openai/test_event_flow_ordering.py -q
pytest tests/engine/test_smoke_async_agent_providers.py -q
```

## 当前测试分层

### `tests/runtime/`

运行时基础设施测试，覆盖 `dayu.runtime` 的层中立边界、取消 helper 与日志装配：

- import boundary：阻止 runtime 反向依赖 Engine、Host、Service、UI、Fins 或引入运行期 HTTP 客户端。
- cancellation：覆盖取消等待 helper 的完成、取消与异常传播语义。
- lane：覆盖 cross-process named semaphore / capacity guard 的配置校验、独立 SQLite runtime lane DB schema、acquire /
  heartbeat / release、timeout、协作式 cancellation、`Task.cancel()` 透传、controller close、跨进程 capacity invariant、
  shielded claim / release 遇到外层取消时的收口一致性、release 后其它进程 acquire，以及 crash 后 TTL stale cleanup
  eventual acquire；测试不断言 FIFO、公平性或 Host dispatch 集成。
- filelock：覆盖同步 file lock wrapper 的 parent directory 创建策略、禁用创建时的结构化错误、context manager 正常与异常路径 release、release 幂等、non-blocking timeout 包装，以及第三方 `filelock` import 只能出现在 `dayu.runtime.filelock` 的边界。
- logging：验证 `dayu.runtime.log` 的 logger 装配、CLI 风格级别解析、`VERBOSE` / `CRITICAL` 级别契约，并验证 `dayu.runtime.log_levels` 只提供公共日志级别常量、不注册 stdlib logging level。

### `tests/contracts/`

公共协作契约测试，覆盖 `dayu.contracts` 的稳定边界：

- package exports：锁定包根 `__all__` 白名单，阻止未承诺符号泄漏。
- import boundary：阻止公共契约层反向依赖 Engine、Host、runtime implementation、Service、UI、Fins 或运行期 HTTP 客户端。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入公共契约源码。
- ToolExecutionOutcome / ToolResult / ToolCall 等契约测试：覆盖工具调用 provider state、工具结果信封、工具执行 outcome 封闭联合与穷尽匹配。
- tool declaration：覆盖最小 `@tool(..., truncate=ToolTruncateSpec(...))` 声明能力，确认 `ToolDefinition` / `ToolBundle` 只投影 `ToolSchema` 给 Engine。

### `tests/host/`

Host 公共 API 类型、Session / Run public command facade、construction tooling options 与内部 durable foundation 测试，覆盖 `dayu.host` 的稳定边界：

- package exports：锁定 `dayu.host.__all__` 与 `dayu.host.api.__all__` 白名单，确认 command facade / tooling 类型可从包根导入但不进入 `dayu.host.api`。
- public contracts：验证 status / error 枚举字符串值、frozen slots dataclass、结构化 `HostApiError` 与 request validation failure paths。
- command handle / public session API：覆盖 Host command handle factory fresh DB、稳定 public handle id、默认 active registry 不跨 handle 共享、内部依赖不暴露、close 幂等、关闭后 facade 稳定失败，以及 `ensure_session` / `create_session` / `get_session` / `close_session` 的 snapshot、幂等、冲突、NOT_FOUND 与保留 durable truth 语义。
- public run / wait API：覆盖 `start_run` direct running / attach active / 幂等重放 / 幂等冲突、`submit_followup(queue)` active 与 no-active 分支、`submit_followup(steer)` stable unsupported 且不追加 EventLog、`cancel_run` queued / pre-dispatch STARTING / injected active worker registry / WAITING、`cancel_session_runs` 的 queued / pre-dispatch STARTING / injected active worker registry / WAITING 子集、幂等重放、不影响其它 Session、unsupported non-terminal 无 partial mutation，以及 `resolve_wait` completed resume / tool-cancelled resume / failed closeout / lost closeout / late diagnostic / 同 outcome 不受 `observed_at` 变化影响的幂等重放 / 不同 outcome 幂等冲突。
- tooling options：验证 `ToolBundleSourceKind` / `FrameworkToolName` 为 `StrEnum`、默认 reserved framework tool policy、source refs 非空、业务 `ToolBundle` 不得占用 `fetch_more` 等 reserved framework tool name，以及 default policy view 不共享可变状态。
- durable foundation / projection core / Conversation Memory / RunInputBuilder / dispatch scheduler / ToolRuntime accept barrier / executor / truncation / fetch_more / duplicate governance / diagnostics / EngineEvent ingest / internal admission：覆盖 SQLite fresh bootstrap、schema version / table constraint、transaction runner commit / rollback / after-commit / busy retry、EventLog append / read / duplicate / conflict、canonical fact inline payload size guard、idempotency record / conflict、payload descriptor、local artifact helper、host instance liveness、多进程 EventLog `event_sequence` 唯一递增 smoke、projection checkpoint / failure schema 与 row codec、ProjectionRunner filter / typed payload / 同事务 checkpoint advance / failure 不推进 checkpoint、minimal RunResult / Session timeline read model 投影、terminal 冲突失败、display_text 缺失 fallback、repair reset / replay / resume、Conversation Memory typed contract 校验、Host-neutral ref 边界、tool-verified / assumption claim status 边界、deterministic snapshot digest、memory table / CHECK / FK / index、memory snapshot 与 projection checkpoint 同事务 rollback、memory diagnostic durable round-trip、ConversationMemoryProjectionConsumer committed EventLog projection、memory projection consumer-scoped reset / rebuild / catch-up failure、tool fact provenance、final answer / user input anti-hallucination matrix、history pool budget / stable layer budget / recent raw turn floor / episode summary 降级顺序、RunInputBuilder memory snapshot covered / inline delta / repair-required 路径、Session lifecycle、Run / Attempt transition primitive、dispatch record 四状态 schema、wait record schema / row codec / DDL CHECK / CAS helper、awaiting accept 三事实原子写入 / wait record 创建 / WAITING 和 SUSPENDED 状态推进 / replay / conflict / stale execution reject、resolve_wait 原子 resume / terminal closeout / resume RunInputBuilder continuity / late diagnostic / after-commit catch-up failure tolerance、WAITING cancel、wait poller ready / not-ready / cancelled abandon / adapter error warning、waiting / dispatching / worker accept refs、active cancel durable primitive、RunInputBuilder durable prompt / canonical continuity / no-tool request / 非可派发状态拒绝、scheduler pending / waiting / dispatching / worker accept / durable retry requeue / promotion catch-up failure tolerance、scheduler 默认 active registry 不跨实例共享、真实 scheduler tool-enabled ToolRuntime wiring、真实 scheduler awaiting production wiring、drain loop empty / sleep wakeup 窗口、pre-accept cancel race、lane acquire timeout、worker startup timeout、active task 资源释放、LocalProxy single-use events / close race / Engine entry boundary、ToolRuntime effective bundle 同源 schema / callable、ToolRuntime accept key 幂等重放 / conflict / invalid Attempt / stale execution reject / reuse canonical governance / accepted tool fact catch-up failure tolerance、ToolRuntimeExecutor accepted ack barrier、oversized tool result governed diagnostic outcome、rejected ack 不泄漏 raw result、accept timeout bounded retry、side-effect / paid missing idempotency key guard、awaiting accepted / rejected / timeout / missing adapter / missing external job / batch stop、no-tool scope defense、mixed batch、`text_chars` / `text_lines` / `list_items` / `binary_bytes` truncation、run-scoped truncation cursor / scope token、fetch_more 普通工具注入、oversized fetch_more continuation guard、single-use / TTL / scope / token / missing cursor / invalid limit / remainder digest 错误路径、duplicate key 规范化并排除 `index_in_iteration`、同 iteration 重复调用治理、`allow` / `reuse` / `hint` / `require_justification` / `hard_stop` matrix、duplicate governed candidate 字段一致性、Run-scoped duplicate registry 的同 Run 共享 / 跨 Run 隔离 / scheduler 生命周期清理、diagnostic emitter refs，以及 Engine 经 ToolRuntime durable accepted 后继续第二轮、fetch_more 经同一 ToolRuntime accept EventLog path、final answer / failed / cancelled / usage / preview data 校验 / unsupported recovery EngineEvent mapping / Engine awaiting confirmation diagnostic 与 accepted wait refs 匹配、Engine 工具事件 preview 边界、clean EOF / worker lost closeout、terminal duplicate promotion retry、start / follow-up admission、queue policy、idempotency、FIFO promotion、queued / pre-dispatch cancel、terminal closeout，以及 admission 多进程 durable invariant，包括同 slot ensure、同 Session active Run 唯一性、跨进程幂等、FIFO promotion、queued cancel / promotion 竞争和 EventLog sequence 全局顺序。
- runtime：覆盖取消 / 超时 race helper、日志装配、file lock、lane controller 与 runtime import / weak typing guard。
- Phase 5 本地执行集成：`test_phase5_local_execution_integration.py` 使用 public `start_run`、真实 `HostDispatchScheduler`、runtime lane 与 fake local worker 覆盖 no-tool Engine 闭环。fake worker 必须只通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 Engine public `EngineEvent` 或模拟 clean EOF / stream crash；测试断言 Host durable Run / Attempt 终态、active cancel 传播、terminal / cancel 后 queue promotion 继续唤醒 dispatch，不绕过 scheduler 直接改生产状态。
- import boundary：允许 Host 在 LocalProxy 边界沿依赖方向调用 Engine public entry，阻止 Host 导入 Config、Fins、Service 或 UI，阻止 Host 使用动态模块扫描能力扫描业务工具模块，确认 business `ToolBundle` 不进入 per-run request dataclass 字段，并确认 `fetch_more` 只留在 ToolRuntime / tooling owner。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入 Host 公共类型源码。

### `tests/engine/`

Engine 契约、包根导出、事件契约与架构边界测试，覆盖 `dayu.engine` 的稳定边界：

- package exports：锁定 `dayu.engine.__all__`，阻止未承诺入口、实现类或取消异常出现在包根。
- import boundary：阻止 Engine 反向依赖 Host（含 memory）、Service、UI、Fins、工具声明 owner、工具执行实现、处理器或 trace 私有模块；OpenAI runner 子树内允许当前实现所需的 `aiohttp`。
- weak typing guard：扫描 `dayu.engine` 源码，守住强类型签名、封闭联合与 metadata 类型边界。
- 事件契约与消息契约：覆盖 EngineEvent、RunnerEvent、AgentMessage、metadata、provider protocol error `partial_tool_calls` 有界摘要、Engine message inline size guard、终态事件集合等结构约束。
- Agent 状态机：覆盖无工具 final / failed / cancelled、普通 completed / failed tool calling、工具结果投影、max iteration force-answer、连续失败工具批次保护、awaiting 拒绝与取消优先级。
- provider smoke 轻量测试：覆盖 `utils/smoke_async_agent_providers.py` 的参数解析、缺 key 跳过、安全输出与 provider case 配置，不做真实联网。

### `tests/engine/contracts/`

Engine contract 的细粒度测试，当前覆盖：

- `messages`：AssistantMessage / AssistantToolCall 与 provider state roundtrip 契约。
- `runner_events`：RunnerEventData 联合、RunnerHTTPErrorCode、RunnerHTTPErrorData、HTTP error 与 context overflow 错误枚举、HTTP error 到 Done(ERROR) 的收口契约。
- `runner_spec`：RunnerSpec 字段集合、provider reasoning / thinking extension、stream usage 能力字段、timeout / retry 校验与构造路径。
- import boundary：Engine contract 子包不得越过自身契约边界引入上层依赖。

### `tests/engine/runners/openai/`

OpenAI-compatible Runner 的 provider 协议测试，覆盖从 payload 构建、provider 响应解析到 RunnerEvent 事件流的行为：

- payload：消息、工具 schema、reasoning content、provider 扩展、stream usage gating、禁止额外 payload 袋。
- SSE：content delta、reasoning delta、tool call delta、tool call 聚合、usage、malformed usage 非终止诊断、`[DONE]`、多行 data、跨 chunk UTF-8、非法 UTF-8、尾部无换行、空 choices + usage。
- non-stream：非流式响应、thought 标签处理、stream / non-stream 终态语义一致性。
- 错误与重试：协议错误、HTTP error 分类、context overflow classifier、未知状态码、retry backoff、重试耗尽后的事件收口。
- 取消与资源：取消边界、取消后不补 done 事件、close 释放资源。
- 架构边界与协议表面：Runner 只产出 RunnerEvent，不依赖 ToolExecutor，不暴露任意 `**kwargs` 或 `set_tools`，事件流顺序保持单调并以唯一终态收口。

本目录内已有 `_fakes.py`、`_factories.py`、`_sse_helpers.py` 作为局部测试 helper。

## 维护约定

- 新增公共契约必须补 package export、import boundary、weak typing guard 相关测试。
- 新增 Host 公共类型必须同步更新 `tests/host/test_package_exports.py`，并为新增 request / snapshot 或 construction options 校验补充对应测试。
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
