# Host P7 Handoff Plan：Tool Trace Projection / Sink

## 1. 目标

P7 目标是在 P6 durable EventLog / ProjectionCoordinator / observer / sink 基础上，落地 Host-owned Tool Trace Projection / Sink。动机成立：P6 已经把 RunEvent 变成 durable canonical facts，并提供 projection checkpoint；若 P7 仍恢复 OLD Engine 私有 `V2ToolTraceRecorder` / `JsonlToolTraceStore`，会形成第二事实源，破坏“Host 从 EventLog 派生诊断视图”的迁移方向。

本阶段必须产出：

- `tool_trace` observer：只消费 P6 durable EventLog 的 canonical facts 与 global event position，不直接订阅 EngineEvent iterator，不在 Engine / EngineWorker 内写 trace。
- tool trace sink / store：以 Host projection read model 保存 trace 记录、raw payload 引用、schema version、source event cursor / position 与 observer checkpoint。
- OLD `tool_trace_v2` 关键语义对齐：覆盖 `tool_call`、`iteration_context_snapshot`、`iteration_usage`、`final_response`、`sse_protocol_error` 五类诊断记录的可消费语义；其中 `iteration_context_snapshot` 在 P7 新增 Host-owned durable fact 作为事实源，记录“这一轮模型到底看到了什么上下文”的热层摘要与冷层 raw payload 引用。
- tool call / result / truncation / fetch_more / iteration usage / final response / provider protocol error 投影测试。
- 幂等与 replay 测试：重复 drain、崩溃后 checkpoint 未推进重放、跨 batch 重放不能重复写 trace。
- trace payload 边界：provider secret 不进 trace；其它诊断字段默认不做过滤，按 OLD 热/冷分层保存，尤其必须保留 `fetch_more` 的 `scope_token` / `cursor` 以支持重复调用、错 token、错 cursor 等真实故障定位。
- 迁移 OLD `utils/analyze_tool_trace.py` 中业务无关的诊断能力：重复工具调用、截断后未续读、`fetch_more` 参数 / 质量、trace 完整性、context 压力、provider protocol error 等；财报 / web 业务专项分析不进入 P7 主线。
- 手工 smoke：新增 `utils/smoke_host_p7_tool_trace.py`，可观察真实 Host durable EventLog -> projection -> trace sink 链路。

验收信号：

- trace 记录可由 P7 固定的读取路径理解：P7 固定使用 `tool_trace_v2_host` + Host read API + JSONL exporter / analyzer adapter，不把 NEW hot schema 伪装成完全 OLD `tool_trace_v2`。
- 所有 trace 记录都能追溯到 durable EventLog 的 `run_id`、`session_id`、per-run cursor 和 internal global position。
- 测试证明 trace 来自 canonical EventLog facts，而不是手写 trace、进程内 recorder 状态或 Engine 私有 recorder。
- analyzer adapter 必须迁移 OLD `utils/analyze_tool_trace.py` 的业务无关诊断能力，并用 fixture 证明可读。

## 2. 非目标

P7 不实现以下能力：

- 不恢复 Engine 私有 recorder / store，不新增 `dayu.engine.tool_trace`，不让 Engine import Host trace schema。
- 不把 trace 写回 Engine，不把 trace schema 变成 Engine 稳定契约。
- 不扩大 ToolRegistry 权限治理；权限、middleware、tool catalog、display metadata 仍留到 P10。
- 不实现 audit hard-gate；trace 默认 best-effort，不阻塞 Run terminal。
- 不实现 P8 attempt lease / recovery / fencing、observer claim / lease / owner token。
- 不实现 P9 Session / Run lifecycle、`client_request_id` 幂等、active run admission、public interface 固定。
- 不迁移 web/business tools，不迁移 fins/doc/web 全量工具。
- 不改变 Host public interface；P7 只新增 Host internal projection 与 smoke/test 入口。
- 不做旧 trace 文件兼容迁移；schema 变更按全新起库处理。
- 不把 `utils/analyze_tool_trace.py` 扩展成生产依赖。若需要临时适配，只作为工具脚本更新，不进入 Host runtime。

## 3. 前置条件

进入 P7 实施前必须确认：

- P6 durable branch 已包含 `DurableRunEventStore`、`ProjectionCoordinator`、`ProjectionStore`、timeline / audit / memory observer 示例与 `utils/smoke_host_p6_durable_eventlog.py`。
- `docs/host/migration-plan.md` 中 P6 残余风险已登记，尤其是 `ObserverSink.process` sync 协议与 `_run_async` 桥接风险。
- `RunEventType` 已覆盖工具请求、工具结果、usage、final answer、provider protocol error、ToolRuntime truncation / cursor / fetch_more facts。
- `dayu/engine` import boundary 测试仍禁止 `tool_trace`、`ToolTraceRecorder`、`JsonlToolTraceStore` 回流 Engine。
- 旧仓库直接证据已对照：
  - `/Users/leo/workspace/dayu-agent/dayu/engine/tool_trace.py`
  - `/Users/leo/workspace/dayu-agent/tests/engine/test_tool_trace.py`
  - `/Users/leo/workspace/dayu-agent/utils/analyze_tool_trace.py`

## 4. OLD Tool Trace 关键语义证据

OLD `tool_trace_v2` 的关键价值不是 recorder 所在位置，而是诊断语义：

- 记录类型：
  - `tool_call`
  - `iteration_context_snapshot`
  - `iteration_usage`
  - `final_response`
  - `sse_protocol_error`
- 所有热层记录包含 `trace_schema_version="tool_trace_v2"`、`trace_type`、`recorded_at`、`run_id`、`session_id`、`iteration_id`。
- `tool_call` 记录包含 `tool_call_id`、`index_in_iteration`、`tool_name`、`arguments`、`result_fact`、`result_summary`、可选 `result_data`。
- `result_fact` 关键字段是 `status`、`error_code`、`truncated`、`latency_ms`、`result_hash`、`raw_result_ref`；OLD 明确不写 `success` 字段，而用 `status` 表达成功/失败。
- 请求与返回可乱序到达：OLD recorder 能缓存 pending request / result 并配对；close 时会把未配对请求写成 `RESULT_MISSING`，未配对结果写成 `REQUEST_MISSING`。
- `iteration_context_snapshot` 包含 `iteration_index`、`current_user_message`、`context_meta`、`model_input_messages_summary`、`raw_input_ref`、`tool_schema_names`、`raw_tool_schemas_ref`、`tool_calls`、`termination_reason`。
- 上下文热层只写摘要：按 `policy`、`memory`、`summary`、`tool_context`、`recent_history`、`current_iteration` 标记来源，并写 excerpt + content hash；完整输入走 raw payload ref。
- `iteration_usage` 写 `usage` 与可选 `budget_snapshot`。
- `final_response` 写 `content`、`degraded`、`filtered`、`finish_reason`。
- `sse_protocol_error` 写 `error_type`、`partial_tool_name`、`partial_arguments_ref`、`request_id`、`attempt`，partial tool calls 放 raw payload 冷存。
- OLD store 按 session 分区 JSONL、支持 raw payload 冷存、分片 rollover、过期清理与 best-effort 失败隔离。

P7 继承这些语义，但必须重设所有权：

- `V2ToolTraceRecorder` 的 per-run 内存聚合不能照搬到 Engine；P7 应由 Host observer 从 durable EventLog 聚合。
- JSONL 可以作为 smoke / 本地诊断 sink 的实现素材，但 durable Host schema 才是 NEW projection 真源。
- `sse_protocol_error` 在 NEW 中对应 `RunEventType.PROVIDER_PROTOCOL_ERROR`；如果缺少 OLD `partial_tool_calls` 级事实，P7 只能记录当前强类型事件已有字段，并在 plan/code review 中标注语义差距，不得用 metadata 或 prompt/raw stream 旁路补造。
- `iteration_context_snapshot` 在 NEW P7 必须新增 Host-owned durable fact 作为事实源。当前 P6 EventLog 没有持久化真实 `model_input_messages`、source tags 全量和 raw tool schemas；P7 不能降级占位，而要在 RunInput 构建完成后写入 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 一类 Host-owned fact，热层保存摘要，冷层保存完整 model input / tool schemas raw payload 引用。

## 5. 架构边界

P7 的边界固定为：

```text
Engine -> EngineEvent
Host event translation -> canonical RunEvent
DurableRunEventStore -> EventLog facts
ProjectionCoordinator -> tool_trace_observer
ToolTraceSink/Store -> trace read model / raw payload refs
```

原则：

- Host 是 trace projection owner，Engine 只提供强类型事件事实。
- ToolRuntime 只产生工具运行事实，例如 truncation、cursor issued、fetch_more requested/completed/failed；它不是 trace writer。
- observer 默认 best-effort，失败只更新 projection checkpoint 状态，不改变 Run terminal。
- trace projection 不反向影响 RunInputBuilder、ConversationMemory、ToolRuntime 决策。
- `LocalRunHarness` 只做装配和 terminal 后 `coordinator.drain()`，不能继续膨胀为 trace builder / schema owner。
- 若发现 EventLog facts 不足以派生 OLD 关键语义，实施 Agent 必须停下来列出缺口，优先评估是否需要新增强类型 RunEvent / EngineEvent；禁止从 Engine 私有对象、日志文本、metadata、prompt 原文或 trace-only side channel 取数。
- P7 observer 禁止读取 `LocalRunHarness.last_run_input_build_trace_by_run`、`LocalRunHarness.last_run_input_messages_by_run`、进程内 LRU、Engine 私有对象或未进入 durable EventLog 的 `RunInputBuildTrace` 作为 replay 真源。
- P7 新增的 RunInput context fact 归 Host 所有，由 Host 在 RunInputBuilder 产物确定后、Engine attempt 启动前写入 durable EventLog；该 fact 不是 Engine 契约，也不进入 ConversationMemory 下一轮事实池。

## 6. 文件级改动清单

计划新增：

- `dayu/host/_run_input_context_fact.py`
  - 定义 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 的构造逻辑。
  - 输入为当前 run 的 `RunInput`、tool schema projection、RunInputBuilder trace / memory source 信息和 context budget snapshot。
  - 输出热层摘要与冷层 raw payload 引用；禁止只写进程内 LRU 后让 P7 observer 读取。

- `dayu/host/_tool_trace_projection.py`
  - 定义 `ToolTraceObserver` / projection 聚合逻辑。
  - 从 `ProjectionEventEnvelope` 批量消费 canonical RunEvent。
  - 按确定性非空 `trace_record_id` / `idempotency_key` 幂等写入 sink，不依赖 nullable 业务字段唯一约束。
  - 只保留 batch 内必要聚合状态；跨 batch 需要状态时必须落 durable projection 表，不能靠进程内 pending dict。

- `dayu/host/_tool_trace_store.py`
  - 定义 Host internal tool trace store / sink 协议与 SQLite 实现。
  - 写入 trace records、raw payload refs、source positions、schema version。
  - 提供测试 / smoke 读取 API，例如按 `run_id` 列出 trace 摘要。

- `utils/smoke_host_p7_tool_trace.py`
  - 手工 smoke，基于 durable harness 真实写 EventLog、drain projection、输出小摘要。
  - 不打印大 prompt、大 tool result、完整 scope token、完整 raw cursor、provider secret。

- `tests/host/test_phase7_tool_trace_projection.py`
  - 覆盖 EventLog -> observer -> trace sink 的核心派生语义。

- `tests/host/test_phase7_tool_trace_store.py`
  - 覆盖 schema、幂等键、raw payload ref、provider secret scrub、retention / cleanup 的最小实现。

- `tests/host/test_phase7_tool_trace_eventlog_source.py`
  - 专门证明 trace 从 durable EventLog canonical facts 派生，不依赖 Engine recorder 或手动写 trace。

- `tests/host/test_phase7_run_input_context_fact.py`
  - 覆盖 Host-owned context fact 的 append 时机、payload 热/冷分层、replay 后可派生 `iteration_context_snapshot`。

可能修改：

- `dayu/host/_durable_event_store.py`
  - 仅当需要追加 tool trace projection 表时扩展 P6 schema bootstrap。
  - 不修改 RunEvent public cursor 语义。

- `dayu/host/contracts.py` / `dayu/host/_run_event_serializer.py`
  - 增加 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 对应的强类型 payload 与 serializer。
  - 该事件是 Host-owned diagnostic fact，不属于 EngineEvent。

- `dayu/host/_durable_harness.py`
  - 将 `ToolTraceObserver` 注册进 durable harness 默认 observer 列表，或提供显式构造选项。
  - 不能把 trace 写入逻辑放到 harness。

- `dayu/host/_run_harness.py`
  - 在 RunInputBuilder 完成、Engine attempt 启动前 append Host-owned context fact。
  - 只能负责调用 fact builder 与 EventLog append，不能把 `_run_harness.py` 继续膨胀为 trace builder。

- `dayu/host/_event_observer.py`
  - 仅在 P7 async/sync 协议评估成立时做最小协议调整；见第 16 节。

- `dayu/host/README.md`
  - 若 P7 代码落地，需要更新 Host 当前事实：tool trace 是 P6 projection 派生能力。

- `tests/README.md`
  - 若新增 P7 测试分层说明，需要同步测试手册。

不应修改：

- `dayu/engine/**` 不新增 trace recorder/store，不新增 trace schema ownership。
- `dayu/contracts/protocols.py` 不恢复 `ToolTraceRecorder` 协议。
- `dayu/host/__init__.py` 默认不导出 P7 internal trace store，除非用户确认 Host public 需要查询 trace。
- `utils/analyze_tool_trace.py` 只有在 P7 输出路径/字段需要脚本读取时才可更新，并必须保持工具脚本属性。

## 7. 新增 / 修改契约

新增 Host internal 契约：

- `ToolTraceRecordType`：封闭枚举，至少包含 `TOOL_CALL`、`ITERATION_CONTEXT_SNAPSHOT`、`ITERATION_USAGE`、`FINAL_RESPONSE`、`PROVIDER_PROTOCOL_ERROR`。对外文件兼容可继续写字面量 `sse_protocol_error`，但 internal 命名应与 NEW provider protocol error 事实一致；若保留 OLD 名称必须在 docstring 写明映射。
- `ToolTraceSchemaVersion`：P7 固定为 `tool_trace_v2_host`。Host 内部 read model 不伪装成 OLD `tool_trace_v2`；如需给脚本消费，提供 JSONL exporter / analyzer adapter，把业务无关诊断能力迁移到 NEW schema 上。
- `ToolTraceRecord`：强类型 dataclass union，不允许 `dict[str, Any]` 作为核心签名。
- `ToolTraceSink` / `ToolTraceStore`：只作为 Host internal protocol，方法签名使用强类型，不使用 `Any` / `object`。
- `ToolTraceRawPayloadRef`：包含 `blob_id`、`content_hash`、`storage_uri` 或 SQLite blob key、`bytes`。P7 本地 trace 不默认过滤业务内容、prompt、tool result、scope token 或 cursor；provider secret / API key / Authorization / Cookie 仍不得写入。
- `RunInputContextSnapshotBuiltData`：Host-owned canonical fact payload，承载 `iteration_id`、`iteration_index`、message summary、tool schema summary、context budget snapshot、memory source summary、current user source cursor、raw model input ref、raw tool schemas ref、content hashes 与 byte sizes。

契约要求：

- 每条 trace record 必须包含 source provenance：`run_id`、`session_id`、`iteration_id | None`、`source_event_cursor`、`source_event_position`、`recorded_at`、`trace_schema_version`、`trace_type`。
- 每条 trace record 必须有确定性非空幂等真源，二选一：
  - `trace_record_id TEXT PRIMARY KEY` 由稳定 source provenance 确定性生成。
  - `idempotency_key TEXT NOT NULL UNIQUE` 由稳定 source provenance 确定性生成，`trace_record_id` 可作为普通主键。
- 幂等键输入必须全部非空且稳定。推荐格式为 `sha256(schema_version|trace_type|run_id|iteration_id_or_empty|tool_call_id_or_empty|source_event_position|record_role)`；`record_role` 用于区分同一 source event 派生出的不同记录，例如 `tool_call`、`final_response`、`provider_protocol_error_raw_payload`。
- 业务查询索引可继续包含 nullable 的 `iteration_id`、`tool_call_id`，但这些索引不得作为 replay 幂等证明。
- record type 的 source provenance 规则：
  - `tool_call`: `run_id + iteration_id + tool_call_id + request/result source positions + record_role`。
  - `iteration_usage`: `run_id + iteration_id_or_empty + source_event_position + record_role`。
  - `final_response`: `run_id + source_event_position + record_role`。
  - `provider_protocol_error`: `run_id + iteration_id_or_empty + source_event_position + record_role`。
  - `iteration_context_snapshot`: `run_id + iteration_id + source_event_position + record_role`，source event 必须是 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact。
- provider secret scrubbing helper 必须是模块级私有函数，不能用 `hasattr/getattr` 逃避类型边界。

### 7.1 `iteration_context_snapshot` Host-owned Fact 策略

P7 固定新增 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact，不采用降级 snapshot 作为最终策略。该 fact 的目标是让 tool trace 能回答“这一轮模型到底看到了什么上下文”，且崩溃 replay 后仍可重建。

写入时机：

- Host RunInputBuilder 完成当前 run / attempt 的 model input 与 tool schema projection。
- Host 在同一个 Host durable transaction 中将 raw model input / raw tool schemas 写入 P7 冷层 raw payload store，并 append `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` canonical fact。
- fact 只引用同事务提交的 raw payload refs。
- Engine attempt 启动。

热层字段：

- `iteration_id` / `iteration_index`。
- `current_user_message` 的 bounded excerpt、content hash、source cursor。
- `context_meta`：message count、role sequence、context budget snapshot、compact count、memory item counts、source positions。
- `model_input_messages_summary`：每条 message 的 role、kind/source tag、bounded excerpt、content hash、estimated token / char count。
- `tool_schema_names` 与 schema hash。
- `raw_input_ref` 与 `raw_tool_schemas_ref`。
- `tool_calls`：该 context 构造时已知的 tool schema / framework tool 摘要；真实 tool call 仍由后续 tool call facts 派生。

冷层字段：

- 完整 model input messages。
- 完整 tool schemas。
- 必要的 raw context builder trace payload。

禁止字段行为：

- P7 observer 不得从 `RunInputBuildTrace`、`LocalRunHarness` 内存缓存、prompt 原文、Engine 私有对象或日志文本补造 `iteration_context_snapshot`。
- 若 raw payload 写入或 context fact append 任一失败，整笔 transaction 必须回滚；Engine attempt 不得启动。禁止产生“fact 已落库但 raw ref 缺失”的状态。
- 该 fact 不进入 ConversationMemory 下一轮事实池，不影响模型输入，只服务 trace / audit / replay 诊断。

### 7.2 Provider Protocol Error 字段映射

`RunEventType.PROVIDER_PROTOCOL_ERROR` 在 trace 中映射为 internal `PROVIDER_PROTOCOL_ERROR`；若选择 OLD-compatible 文件输出，可投影为 `sse_protocol_error` 字面量，但字段语义必须按下列规则固定：

- `error_type = data.error_code`。
- `request_id = data.provider_request_id or ""`。
- `partial_tool_name = None`，并在 payload 中写 `partial_tool_name_omitted_reason="not_in_provider_protocol_error_event"`。
- `attempt = None`，并写 `attempt_omitted_reason="not_in_provider_protocol_error_event"`。
- `partial_arguments_ref` 只允许指向 bounded / provider-secret-scrubbed `raw_payload` 的 raw payload ref；当 `raw_payload` 缺失时为 `None` 并写 `partial_arguments_omitted_reason="raw_payload_missing"`。
- raw payload 超限或含 provider secret 时，必须先 bounded / scrubbed 后再生成 ref；无法保存时 `partial_arguments_ref=None`，并写清原因。
- 不得从 provider raw stream、metadata、prompt 或日志旁路解析 partial tool calls 来补 `partial_tool_name` / `attempt` / `partial_arguments_ref`。

## 8. 状态机变化

Run / Attempt 状态机不变。

Projection 状态机沿用 P6：

- `IDLE`
- `RUNNING`
- `CAUGHT_UP`
- `RETRYABLE_FAILED`
- `BLOCKED_FAILED`

P7 只新增一个 observer 的状态推进，不新增 Run terminal gate。

处理策略：

- trace sink 写入成功后 checkpoint 前进。
- trace sink 抛可重试异常时 checkpoint 不前进，状态为 `RETRYABLE_FAILED`。
- trace schema / contract violation 属于 blocked failure，状态为 `BLOCKED_FAILED`，不得跳过事件继续前进。
- malformed but nonessential trace field 不能静默吞掉；必须要么按 provider-secret scrub / 缺省规则稳定降级，要么 blocked，并由测试覆盖。

## 9. 数据持久化 / Schema 变化

P7 涉及 Host durable schema 变更，按全新 schema 起库处理，不做旧库兼容读取。

建议新增表：

- `host_tool_trace_records`
  - `trace_record_id TEXT PRIMARY KEY`
  - `idempotency_key TEXT NOT NULL UNIQUE`
  - `trace_schema_version TEXT NOT NULL`
  - `trace_type TEXT NOT NULL`
  - `run_id TEXT NOT NULL`
  - `session_id TEXT NOT NULL`
  - `iteration_id TEXT`
  - `tool_call_id TEXT`
  - `source_event_position INTEGER NOT NULL`
  - `source_event_sequence INTEGER NOT NULL`
  - `recorded_at TEXT NOT NULL`
  - `payload TEXT NOT NULL`

- `host_tool_trace_raw_payloads`
  - `blob_id TEXT PRIMARY KEY`
  - `run_id TEXT NOT NULL`
  - `iteration_id TEXT`
  - `payload_type TEXT NOT NULL`
  - `content_hash TEXT NOT NULL`
  - `byte_size INTEGER NOT NULL`
  - `created_at TEXT NOT NULL`
  - `payload TEXT NOT NULL`

注意：

- `trace_record_id` 与 `idempotency_key` 必须至少一个承担确定性幂等主约束；若两者同时存在，推荐二者值一致或同源派生，避免主键随机而唯一键才是真源。
- 禁止使用包含 nullable 字段的 SQLite `UNIQUE(trace_schema_version, trace_type, run_id, iteration_id, tool_call_id, source_event_position)` 作为幂等证明；SQLite 允许多个 `NULL` 通过唯一约束，会导致 `final_response`、`iteration_usage`、`provider_protocol_error` replay 重复。
- 可另建普通查询索引，例如 `(run_id, iteration_id)`、`(run_id, trace_type)`、`(tool_call_id)`；这些索引只服务读取，不承担 replay 幂等。
- SQLite payload 仍必须由封闭 serializer 写入，不能让生产代码到处拼开放 JSON。
- raw payload 冷存按 OLD 热/冷分层保存完整诊断材料，默认不对 prompt、model input、大 tool result、scope token、cursor 做过滤；provider secret、Authorization header、API key、cookie 不得进入 raw payload 表。
- cursor / scope token 必须完整记录在 tool call arguments / raw payload 中，用于定位 `fetch_more` 重复调用、错 cursor、错 scope token；可额外记录 fingerprint 方便热层聚合。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 的 raw payload refs 与 EventLog fact 必须同事务提交；其它 tool result raw payload 与对应 trace record 的一致性由 ToolTraceStore 的幂等写入和 checkpoint 同事务保证。
- 是否需要 workspace migration 插件：P7 默认不需要旧库迁移；若当前 `dayu-cli init` 已管理 Host SQLite schema，则实施 Agent 必须在计划执行前停下确认是否接入初始化流程。

## 10. 多进程并发影响

P7 不实现 P8 observer claim / lease / fencing，但必须在 P6 能力内保证：

- 同一 observer 重复 drain 不重复 trace：靠确定性非空 `trace_record_id` / `idempotency_key` 与 upsert / insert-or-ignore / compare-and-set 实现。
- sink 写入与 checkpoint 前进同事务提交；禁止出现 trace 未写但 checkpoint 已前进。
- 多进程同时 drain 同一 observer 时，结果必须幂等；允许一个进程因唯一约束发现已写入而继续推进 checkpoint。
- 不宣称生产级 observer worker fleet；真实多进程 stress 与 owner fencing 后移 P8。

测试至少覆盖：

- 两次 drain 同一事件集只生成一组 trace。
- 人为在 sink 写入后、checkpoint 前进前抛错，重放后 trace 不重复且 checkpoint 可前进。
- 对 `final_response`、`iteration_usage`、`provider_protocol_error` 分别模拟 sink 已写入但 checkpoint 未推进后的 replay，断言记录数不增加，并证明不依赖 nullable 业务字段唯一约束。
- batch 边界拆分后，tool request 与 result 分属不同 batch 时仍能生成正确 tool_call，或明确记录 P7 不支持该场景并停止。优先方案是 durable pending state，不接受进程内 pending dict 作为跨 batch 真源。

## 11. ToolRuntime / EngineWorker / Engine 边界影响

Engine 边界：

- Engine 不新增 trace API。
- Engine 不 import `dayu.host` / `tool_trace`。
- Engine 只通过现有 `EngineEvent` 输出 tool call、tool result、usage、final answer、provider protocol error。

EngineWorker 边界：

- EngineWorker 不写 trace，不持有 trace sink。
- EngineWorker 只继续把 EngineEvent 交给 Host run harness / event translation。

ToolRuntime 边界：

- ToolRuntime 继续 append canonical ToolRuntime facts：`tool_result_truncated`、`tool_cursor_issued`、`tool_fetch_more_requested`、`tool_fetch_more_completed`、`tool_fetch_more_failed`、`tool_cursor_expired`、`tool_cursor_denied`。
- ToolRuntime 不直接调用 ToolTraceStore。
- P7 observer 从 ToolRuntime facts 派生 truncation/fetch_more trace 摘要。
- scope token、raw cursor、完整 fetched chunk 必须可进入 trace 冷层；provider secret 仍不得进入 trace。

## 12. EventLog / RunEventStore / Projection 影响

P7 observer 只消费：

- `RunEventKind.CANONICAL`
- `RunEventType.ITERATION_STARTED`
- `RunEventType.TOOL_CALL_REQUESTED`
- `RunEventType.TOOL_RESULT_ACCEPTED`
- `RunEventType.TOOL_RESULT_TRUNCATED`
- `RunEventType.TOOL_CURSOR_ISSUED`
- `RunEventType.TOOL_FETCH_MORE_REQUESTED`
- `RunEventType.TOOL_FETCH_MORE_COMPLETED`
- `RunEventType.TOOL_FETCH_MORE_FAILED`
- `RunEventType.TOOL_CURSOR_EXPIRED`
- `RunEventType.TOOL_CURSOR_DENIED`
- `RunEventType.RUNNER_USAGE_RECORDED`
- `RunEventType.PROVIDER_PROTOCOL_ERROR`
- `RunEventType.FINAL_ANSWER`
- `RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`
- 必要时读取 Host-owned failure terminal 作为 close / missing result 补偿信号。

P7 不消费 preview delta、reasoning delta、content delta 全量，避免 trace 变成大内容仓库。

需要特别测试：

- `TOOL_CALL_REQUESTED -> TOOL_RESULT_ACCEPTED` 生成 `tool_call`。
- `TOOL_RESULT_ACCEPTED` 先于 `TOOL_CALL_REQUESTED` 的 durable replay 顺序如果理论上不可能，应用直接证据说明；如果可能，必须支持配对。
- `TOOL_RESULT_TRUNCATED + TOOL_CURSOR_ISSUED` 让 `result_fact.truncated=True`，同时保留 cursor / scope token 以诊断补读链路。
- `fetch_more` requested/completed/failed 派生为 tool trace 里可诊断的补读链路，必须能看出重复调用、错 cursor、错 scope token。
- `PROVIDER_PROTOCOL_ERROR` 派生 `sse_protocol_error` / `provider_protocol_error` 记录，并按第 7.2 节字段级映射写 omitted reason。
- `FINAL_ANSWER` 派生 `final_response`。
- `RUNNER_USAGE_RECORDED` 派生 `iteration_usage`。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 派生 `iteration_context_snapshot`，不能从进程内缓存派生。

## 13. Trace Payload 边界

P7 的部署形态是本地财报分析 Agent，trace 的首要目标是可回放、可定位、可诊断。默认原则是沿用 OLD 热/冷分层，而不是做业务内容过滤：

- 热层 trace record 保存可检索摘要、统计字段、content hash、source cursor / position、大小、状态。
- 冷层 raw payload 保存完整 model input、完整 tool schema、完整 tool result、scope token、cursor、provider protocol raw payload，用于定位真实故障。
- `fetch_more` 的 `scope_token` / `cursor` 必须保留；OLD analyzer 会优先展示它们，历史上也真实发生过重复调用、错 token、错 cursor。
- provider secret、Authorization header、API key、cookie 不进 trace。
- 日志、smoke stdout、README 示例不打印完整 prompt、大 tool result、provider secret；scope token / cursor 在 smoke 中可按需打印摘要或 fingerprint，完整值留在 trace store。

若 provider raw payload 中包含 provider secret，必须 scrub 后再写入；scrub 行为只针对 provider secret 类能力凭据，不扩大到业务 prompt / tool result。

## 14. 可接受临时实现 / 不可接受临时实现

可接受：

- trace 默认 best-effort，不阻塞 Run terminal。
- JSONL exporter / analyzer adapter 作为 P7 必交付的诊断入口，用于迁移 OLD `analyze_tool_trace.py` 的业务无关能力；SQLite / Host projection schema 是 P7 真源。
- `iteration_context_snapshot` 只从 durable `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 生成；该 fact 必须包含热层摘要与冷层 raw refs。
- provider protocol error 暂只保留 NEW 强类型事件已有字段；OLD partial tool calls 缺失时登记语义差距。

不可接受：

- 在 Engine / Agent / Runner 中恢复 `V2ToolTraceRecorder`。
- observer 直接读进程内 EngineEvent iterator 或 ToolRuntime 内存状态。
- observer 读取 `LocalRunHarness.last_run_input_build_trace_by_run`、`last_run_input_messages_by_run`、进程内 LRU、未持久化 `RunInputBuildTrace` 或 Engine 私有对象作为 replay 真源。
- 手动在测试里直接调用 ToolTraceStore 写 trace 后声称 projection 通过。
- checkpoint 先前进再写 sink。
- 用开放 `dict[str, Any]`、`Any`、`object` 作为新增生产契约签名。
- 把 provider secret、Authorization header、API key、cookie 写入 trace。
- 为兼容 OLD 导入路径新增 re-export / facade。

## 15. Runtime Dependency

P7 不需要新增 `dayu.runtime` 能力，也不涉及 lane。

允许复用：

- `dayu.runtime.log_levels` 既有日志等级。
- P6 `HostStorage` / transaction / projection 基础设施。

禁止：

- 把 Host trace schema 或业务诊断语义放进 `dayu.runtime`。
- 引入消息队列、后台 worker 框架或新数据库依赖来绕过 P6 projection 基础。

## 16. P6 残余风险重评估：ObserverSink 是否升级 async

P7 必须重新评估 P6 残余风险，但不能默认大改。

判断标准：

- 若 `ToolTraceSink` 写入完全基于 P6 synchronous `HostStorageTransaction`，且不需要 await 外部 IO，则 P7 继续使用同步 `ObserverSink.process`。
- 若 P7 需要调用 async store、异步文件 IO、异步 remote sink，或需要与 caller event loop 共享 async 状态，则必须提出 async observer 协议变更方案。
- 若只因 memory projection 的 `_run_async` 桥接存在开销，不应在 P7 为 tool trace 单独大改；应记录为 P8/P15 综合处理。
- 若改 async 协议会触碰 memory/timeline/audit observer，大于 P7 trace 范围，则必须先写专项设计/plan review，不可在代码实施中顺手改。

选择策略：

- 默认选择：保持同步 sink，ToolTraceStore 使用同事务同步写入，删除 P7 自己引入 async sink 的需要。
- 升级条件：实现过程中出现直接证据证明同步协议无法保证 sink/checkpoint 同事务、无法支持 durable pending state，或会长期复制 `_run_async` 桥接。
- 无论选择哪条路，实施报告必须说明判断依据，并把未解决风险回写到 `docs/host/migration-plan.md` P6/P7 残余风险追踪。

## 17. 测试清单

新增单元测试：

- `test_tool_call_projected_from_eventlog_requested_and_result`
- `test_tool_call_projection_is_idempotent_across_repeated_drain`
- `test_tool_call_projection_replays_after_sink_written_before_checkpoint`
- `test_final_response_replay_uses_non_null_idempotency_key`
- `test_iteration_usage_replay_uses_non_null_idempotency_key`
- `test_provider_protocol_error_replay_uses_non_null_idempotency_key`
- `test_trace_does_not_use_engine_recorder_or_manual_store_write`
- `test_iteration_usage_projected_from_runner_usage_recorded`
- `test_final_response_projected_from_final_answer`
- `test_provider_protocol_error_projected_with_bounded_payload`
- `test_provider_protocol_error_raw_payload_missing_writes_omitted_reason`
- `test_provider_protocol_error_scrubs_provider_secret_only`
- `test_truncation_and_fetch_more_projection_preserves_scope_token_and_cursor`
- `test_fetch_more_duplicate_or_wrong_scope_token_is_diagnosable`
- `test_iteration_context_snapshot_from_host_owned_context_fact`
- `test_iteration_context_snapshot_has_raw_input_and_tool_schema_refs`
- `test_iteration_context_snapshot_does_not_read_run_input_build_trace_lru`
- `test_missing_result_or_missing_request_behavior_matches_or_intentionally_deviates_from_old`
- `test_projection_blocks_on_schema_violation_without_checkpoint_advance`
- `test_tool_trace_store_round_trip_all_record_variants`
- `test_host_import_boundary_engine_has_no_tool_trace_dependency`

OLD / NEW 对齐测试要求：

- 对照 OLD `tests/engine/test_tool_trace.py` 中配对、business error、context/final、SSE protocol error、result-before-request、close flush、write error swallowed 的语义逐项判断：
  - 可继承的必须测。
  - 因 NEW EventLog 事实不同而不继承的必须在测试名或注释写明原因。
- 对照 OLD `utils/analyze_tool_trace.py` 中业务无关分析能力逐项迁移或标注有意差异，至少覆盖：
  - 同一 run 内相同工具 + 相同参数重复调用。
  - 截断后 `truncation.next_action=fetch_more` 但模型未继续 `fetch_more`。
  - `fetch_more` 的 `scope_token` / `cursor` 参数摘要、重复调用、错 token / 错 cursor 诊断。
  - tool result bytes / raw input bytes 大小分布。
  - trace 完整性、provider protocol error、final response presence。
- analyzer 依赖字段如 `status`、`truncated`、`error_code`、`raw_result_ref`、`final_response`、`sse_protocol_error` 必须有 fixture 覆盖。
- P7 实现前必须固定 analyzer 路径并落对应测试：
  - 固定采用 `tool_trace_v2_host`。
  - 必须覆盖 Host read API 与 JSONL exporter / analyzer adapter 能读取 `tool_call`、`iteration_context_snapshot`、`iteration_usage`、`final_response`、`provider_protocol_error`。
  - 必须覆盖重复调用、truncation/fetch_more、fetch_more 参数质量、trace 完整性等业务无关分析。

覆盖率：

- 新增生产模块单文件覆盖率目标 >= 80%。
- `utils/smoke_host_p7_tool_trace.py` 无覆盖率要求，但必须能手工运行。

## 18. Smoke 计划

新增 `utils/smoke_host_p7_tool_trace.py`。

Smoke 目标：

- 构造 durable harness，运行包含工具调用、截断或 fetch_more、final answer 的最小 run。
- 触发 `ProjectionCoordinator.drain()`。
- 从 ToolTraceStore 读取 trace 摘要。
- 输出 observer checkpoint、trace record counts、tool call summary、truncation/fetch_more summary、final response presence、provider protocol error count。

输出限制：

- 只打印 run_id、session_id、trace record count、observer status、source event positions、tool_name、tool_call_id、status、truncated、cursor fingerprint。
- 不打印完整 prompt。
- 不打印大 tool result。
- 不打印完整 scope token。
- 不打印完整 raw cursor。
- 不打印 provider secret。

推荐输出示例：

```text
P7 tool trace smoke ok
run_id=...
observer=tool_trace status=caught_up last_success_position=...
records: tool_call=1 iteration_usage=1 final_response=1 provider_protocol_error=0
tool_call: name=huge_echo id=... status=success truncated=true source_position=...
fetch_more: requested=1 completed=1 cursor_fingerprint=sha256:...
```

## 19. 验证命令

实施完成后必须运行：

```bash
source .venv/bin/activate
pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_store.py tests/host/test_phase7_tool_trace_eventlog_source.py -q
pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase6_durable_harness_integration.py -q
python utils/smoke_host_p7_tool_trace.py
python -m pyright
```

若修改或迁移 `utils/analyze_tool_trace.py`，还必须运行该脚本 / adapter 的最小 fixture / smoke 命令；若当前没有测试，实施 Agent 必须新增脚本级测试或在最终报告中明确无法自动验证的原因。

## 20. README / Docs 触发判断

本阶段只写 plan 时不更新 README。

代码实施时触发：

- 修改 `dayu/host/`：检查并按当前事实更新 `dayu/host/README.md`。
- 新增 `tests/host/test_phase7_*`：检查 `tests/README.md` 是否需要加入 P7 trace projection 测试分层。
- 新增 `utils/smoke_host_p7_tool_trace.py` 或修改项目级 tool trace 使用方式：检查根目录 `README.md` 的 tool trace / smoke / trace analyzer 说明是否仍对应当前接口。
- 若涉及分层关系或 observer 归属表述变化：检查 `dayu/README.md` 与 `docs/host/design.md` 是否需要同步当前事实。
- 不把未来 P8/P9/P10 能力写成已落地事实。

## 21. Review Gate

Plan review gate：

- 常规 plan review：检查必填模板、P7/P8/P9/P10 边界、文件级清单与测试是否可交接。
- OLD / NEW 专项 review：对照 OLD `tool_trace.py`、`test_tool_trace.py`、`analyze_tool_trace.py`，确认关键语义继承/有意差异都有证据。
- 架构边界 review：确认 Engine 不恢复 recorder/store，ToolRuntime 不直接写 trace，ProjectionCoordinator 是唯一派生路径。
- trace payload review：专查 provider secret 不入 trace，同时确认 prompt、scope token、cursor、tool result 按 OLD 热/冷分层保留，足以定位 `fetch_more` 和上下文问题。

Code review gate：

- 常规 code review：优先找正确性、幂等、事务、schema、类型与测试缺口。
- OLD / NEW code review：逐项核对 OLD 五类 record 与 analyzer 依赖字段。
- Projection / concurrency review：检查 sink/checkpoint 同事务、重复 drain、多进程幂等、cross-batch pending state。
- Import boundary review：扫描 Engine 不含 `tool_trace` / `ToolTraceRecorder` / `JsonlToolTraceStore`。
- Smoke review：确认 `utils/smoke_host_p7_tool_trace.py` 真实走 EventLog projection，不打印敏感/大结果。

所有 review finding 修复后，必须在对应 review 文档标题标注修复状态。

## 22. 停止条件

遇到以下情况必须停止并回报用户，不得继续实现：

- 当前 RunEvent facts 无法派生 OLD 关键 trace 语义，且需要新增 EngineEvent / RunEvent 契约。
- 需要改变 Host public interface。
- 需要恢复 Engine recorder/store 或 Engine trace import。
- 需要引入 P8 lease/fencing 才能保证 P7 最小正确性。
- 需要迁移 web/business tools 才能完成 P7。
- 无法在保留 scope token / cursor / prompt / 大结果冷层诊断材料的同时排除 provider secret。
- 需要把 `ObserverSink.process` 改成 async 且影响 P6 既有 observers。

## 23. 风险与回滚

主要风险：

- OLD `iteration_context_snapshot` 依赖真实 model input；NEW P7 必须用 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 持久化热层摘要与冷层 raw refs，不能再依赖进程内缓存或降级占位。
- OLD `sse_protocol_error` 有 partial tool calls；NEW `ProviderProtocolErrorData` 可能缺少 partial arguments。应记录语义差距，不能从 raw stream 旁路读取。
- cross-batch tool request/result 配对如果只靠内存，会在 replay 后丢失。必须用 durable pending/projection state 或证明 EventLog 顺序使其不需要。
- provider raw payload 可能混入 provider secret。必须只 scrub provider secret 类能力凭据，不扩大到业务 prompt / tool result / scope token / cursor。
- JSONL 旧 analyzer 不能直接读取 NEW SQLite trace。P7 已固定采用 `tool_trace_v2_host` + Host read API + JSONL exporter / analyzer adapter；不得在实现完成后再补验收口径。

回滚策略：

- P7 schema 独立于 EventLog facts；回滚可移除 tool trace observer 注册与新增 trace 表，不影响 RunEventStore 主事实。
- 若 observer 失败，可从 durable harness 默认 observers 中暂时移除 tool trace observer，EventLog facts 仍可后续 replay 重建。
- 不允许通过删除 EventLog facts 回滚 trace 错误；trace 是派生视图，修复应重建 projection。

## 24. 已固定口径与残余确认项

已固定口径：

- `iteration_context_snapshot` P7 固定新增 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact，不再采用降级 snapshot 作为最终策略。
- P7 observer 注册策略：durable harness 在配置了 `ToolTraceStore` / trace storage path 时默认注册 `tool_trace_observer`；未配置 trace store 时不注册，避免无意义 observer 状态面。

残余确认项：

- `provider_protocol_error` P7 首版默认接受 NEW 字段子集，并按第 7.2 节写字段级 omitted reason；若用户要求 partial tool calls 完整语义，必须先确认扩展 Engine/RunEvent 契约。

## 25. 实施完成汇报格式

迁移 Agent 完成代码后，最终汇报必须包含：

- 改了什么：按文件列出生产代码、测试、smoke、README/docs。
- OLD 语义对齐：五类 record 哪些已继承，哪些有意差异，差异依据是什么。
- EventLog provenance：说明 trace 如何从 durable canonical facts 派生，source cursor/position 如何记录。
- Trace payload：说明 provider secret 如何排除；说明 scope token、cursor、完整 prompt、大 tool result 如何按热/冷分层保留并用于诊断。
- async/sync observer 判断：说明 P7 选择继续同步 sink 还是升级协议，以及依据。
- 验证了什么：列出 pytest、smoke、pyright 命令和结果。
- README/docs 触发判断：哪些更新了，哪些检查后无需更新。
- 风险或未覆盖项：列出仍需 P8/P9/P15/P16 承接的问题。
