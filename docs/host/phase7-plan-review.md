# Host P7 Plan Review：Tool Trace Projection / Sink

结论：不通过。

P7 的总体动机成立：`docs/host/migration-plan.md` 明确 P7 应在 P6 observer / sink 基础上落地 tool trace，且不得恢复 Engine 私有 recorder / store；`docs/host/design.md` 与 `docs/engine/design.md` 也一致要求 Engine 只产出强类型事件，Host observer 从 EventLog 派生 trace。`docs/host/phase7-plan.md` 在这一点上方向正确，也基本守住了 P8/P9/P10/P15 phase 边界。

但当前 plan 仍有阻断级缺口：它要求覆盖 OLD `iteration_context_snapshot` 语义，却没有把 P6 EventLog 不足以重建真实 model input / tool schemas 的事实转化为明确的新增 RunEvent 或 durable projection input；同时建议的 trace records 唯一约束包含 nullable 字段，在 SQLite 下无法保证 P7 要求的 replay/idempotency。实现 Agent 若按当前 plan 直接落地，容易在“看似通过测试”的情况下实际依赖进程内缓存或产生重复 trace。

## Findings

### [已修复] 严重级别：High - `iteration_context_snapshot` 的 canonical 事实源未被明确补齐

修复状态：`docs/host/phase7-plan.md` 已按用户决策改为 P7 新增 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` durable fact，不再采用降级 snapshot 作为最终策略。该 fact 在 RunInputBuilder 完成、Engine attempt 启动前写入 EventLog，热层保存 message summary / source cursor / context meta / tool schema hash，冷层保存完整 model input 与 tool schemas raw payload ref。计划同时禁止 P7 observer 读取 `LocalRunHarness.last_run_input_build_trace_by_run`、`last_run_input_messages_by_run`、进程内 LRU、未持久化 `RunInputBuildTrace` 或 Engine 私有对象作为 replay 真源。

证据：

- P7 plan 要求 OLD 五类语义对齐，包含 `iteration_context_snapshot`，并列出 `current_user_message`、`context_meta`、`model_input_messages_summary`、`raw_input_ref`、`tool_schema_names`、`raw_tool_schemas_ref` 等字段（`docs/host/phase7-plan.md:51-70`）。
- OLD recorder 的 `start_iteration` 直接接收真实 `model_input_messages` 与 `tool_schemas`，`finish_iteration` 再写 `raw_input_ref`、`model_input_messages_summary`、`tool_schema_names` 和 `raw_tool_schemas_ref`（旧仓库 `dayu/engine/tool_trace.py:893-929`、`1198-1254`）。
- NEW `IterationStartedData` 只有 `iteration_id`、`iteration_index`、`message_count`（`dayu/engine/contracts/engine_events.py:50-62`），不能重建消息内容、source tags 或工具 schema 名称。
- 当前 `RunInputBuildTrace` 是 internal-only 诊断对象，不写入 EventLog；设计文档明确它“不写入 EventLog，不进入模型上下文，也不作为下一轮事实真源”（`docs/host/design.md` 的 `RunInputBuildTrace` 章节被 `rg` 命中，当前实现也只把它保存在 `LocalRunHarness.last_run_input_build_trace_by_run` LRU 缓存中，见 `dayu/host/_run_harness.py:260-271`、`319-326`）。
- P7 plan 原先虽然写了“若 P7 无法从 EventLog 重建真实 model input，则不得伪造完整 snapshot”，也承认 EventLog 未持久化 `RunInputBuildTrace` 时无法完整重建，但文件级改动清单没有明确新增哪个 RunEvent 或 durable projection input 来承载真实摘要和 raw refs。

影响：

P7 observer 若严格只消费 durable EventLog，就无法生成 OLD analyzer 依赖的高价值上下文字段；若实现为了补齐字段去读 `LocalRunHarness` 的 LRU 缓存或 `RunInputBuildTrace` 内存对象，则违反 P7 “trace 来自 durable EventLog / projection，而不是进程内 recorder 状态”的验收信号，并且崩溃 replay 后无法重建。

建议修复：

- 在 plan 中明确新增 Host-owned、强类型 canonical RunEvent / durable projection input，例如 “run input context snapshot built” 事实。
- 该 fact 必须保留热/冷分层：热层可检索摘要，冷层 raw ref 保存完整 model input / raw tool schemas，以继承 OLD `iteration_context_snapshot` 的诊断价值。
- 明确禁止 P7 observer 读取 `LocalRunHarness.last_run_input_build_trace_by_run`、`last_run_input_messages_by_run` 这类内存缓存作为 replay 真源。

是否阻断 plan gate：是。

### [已修复] 严重级别：High - trace records 幂等 schema 使用 nullable 唯一键，不能证明 replay 不重复

修复状态：`docs/host/phase7-plan.md` 已要求确定性非空 `trace_record_id` / `idempotency_key` 作为幂等真源，禁止使用包含 nullable 字段的 SQLite UNIQUE 约束证明 replay 幂等，并补充 `final_response`、`iteration_usage`、`provider_protocol_error` 的 checkpoint 未推进 replay 测试要求。

证据：

- P7 plan 建议 `host_tool_trace_records` 表包含 nullable 的 `iteration_id`、`tool_call_id`，并用 `UNIQUE(trace_schema_version, trace_type, run_id, iteration_id, tool_call_id, source_event_position)` 作为唯一约束（`docs/host/phase7-plan.md:199-214`）。
- 同一 plan 又要求重复 drain、sink 写入后 checkpoint 未前进再 replay、跨 batch 重放都不能重复写 trace（`docs/host/phase7-plan.md:232-245`）。
- SQLite 的 `UNIQUE` 约束允许多行 `NULL` 不相等；因此 `final_response`、部分 `iteration_usage`、`provider_protocol_error` 或任何 `tool_call_id` 为空的记录，即使其他字段完全相同，也可能重复插入。plan 虽然有 `trace_record_id TEXT PRIMARY KEY`，但没有规定它必须由 idempotency key 确定性生成，也没有把它列为 replay 的主约束。
- P6 `ProjectionCoordinator` 的成功路径是在同一事务中先 `observer.process()` 再 `advance_success()`（`dayu/host/_event_observer.py:254-264`），这给 P7 提供了正确事务边界；但 sink 自身必须有可靠幂等键才能承受事务前失败后的重放。

影响：

实现即使遵守 P6 同事务 checkpoint，也可能在 crash/replay 或重复 drain 中写出重复 trace records，尤其是没有 `tool_call_id` 的记录类型。这样会破坏 OLD analyzer 的 run 聚合、计数、large payload / protocol error 统计，也会让 smoke 输出不稳定。

建议修复：

- 在 plan 中要求 `trace_record_id` 由稳定 source provenance 确定性生成，例如 `sha256(schema_version|trace_type|run_id|iteration_id_or_empty|tool_call_id_or_empty|source_event_position|record_role)`。
- 或为不同 record type 设计非 nullable 的独立幂等列，例如 `idempotency_key TEXT NOT NULL UNIQUE`。
- 保留业务查询索引即可，不要依赖包含 nullable 字段的 SQLite `UNIQUE` 约束证明幂等。
- 增加测试：对 `final_response`、`iteration_usage`、`provider_protocol_error` 分别模拟 “sink 已写入但 checkpoint 未推进” 后 replay，断言记录数不增加。

是否阻断 plan gate：是。

### [已修复] 严重级别：Medium - OLD analyzer 兼容路径仍是待确认项，验收口径不够收敛

修复状态：`docs/host/phase7-plan.md` 已把该项收口为实现前必须固定的用户确认项：若选 `tool_trace_v2_host`，必须提供 Host read API / smoke 摘要 / analyzer adapter；若选 `tool_trace_v2`，必须提供 OLD compatible / degraded / missing 字段矩阵并用 fixture 测 analyzer 解析。该项仍需要用户在实现前二选一，但不再允许实现完成后才补验收口径。

证据：

- P7 验收信号允许 “OLD analyzer 可理解核心字段，或新增/调整 analyzer 适配层明确读取”（`docs/host/phase7-plan.md:17-21`）。
- 但 plan 的待确认项仍未决定使用 `tool_trace_v2` 还是 `tool_trace_v2_host`，也未决定是否提供 JSONL exporter（`docs/host/phase7-plan.md:498-506`）。
- OLD analyzer 当前只按 JSONL 文件读取，并过滤 `trace_schema_version == "tool_trace_v2"`；解析 `tool_call`、`iteration_usage`、`iteration_context_snapshot`、`final_response`、`sse_protocol_error` 都依赖该字面量与字段形状（旧仓库 `utils/analyze_tool_trace.py:33-39`、`472-637`）。
- P7 plan 的持久化真源是 SQLite read model（`docs/host/phase7-plan.md:195-230`），这与 OLD analyzer 的文件输入形态不一致。

影响：

实现完成后可能出现 “SQLite trace 正确但 analyzer 不可读” 或 “为了让 analyzer 可读而把 NEW schema 伪装成 OLD `tool_trace_v2`” 的偏差。前者验收口径不清，后者会误导消费侧，以为字段语义与 OLD 完全一致，尤其是 `iteration_context_snapshot` 和 `sse_protocol_error`。

建议修复：

- 在进入实现前固定一条路径：
  - 若使用 `tool_trace_v2_host`，必须定义 smoke/read API 或 analyzer adapter 的最小字段映射。
  - 若继续写 `tool_trace_v2`，必须逐字段列出 OLD 兼容、降级、缺失三类，并用 fixture 测 analyzer 解析结果。
- 不要把 `utils/analyze_tool_trace.py` 变成 Host runtime 依赖；这一点当前 plan 已写明，应保留。

是否阻断 plan gate：否，但应作为进入实现前的用户确认项。

### [已修复] 严重级别：Medium - protocol error 语义差距已识别，但字段映射需更可测试

修复状态：`docs/host/phase7-plan.md` 已补 `PROVIDER_PROTOCOL_ERROR -> provider_protocol_error / sse_protocol_error` 字段级映射：`error_type = error_code`、`request_id = provider_request_id or ""`、`partial_tool_name = None`、`attempt = None`、`partial_arguments_ref` 仅允许 bounded / provider-secret-scrubbed raw payload ref，缺失或超限写 omitted reason；同时补 raw payload present / missing / provider-secret scrub 测试要求。

证据：

- OLD `record_sse_protocol_error` 写 `error_type`、`partial_tool_name`、`partial_arguments_ref`、`request_id`、`attempt`，并冷存 `partial_tool_calls`（旧仓库 `dayu/engine/tool_trace.py:1136-1191`；测试见旧仓库 `tests/engine/test_tool_trace.py:251-301`）。
- NEW `ProviderProtocolErrorData` 只有 `iteration_id`、`error_code`、`message`、`provider_request_id`、`raw_payload`（`dayu/engine/contracts/engine_events.py:187-204`）。
- P7 plan 已正确承认缺少 OLD partial tool calls 时不能从 raw stream 旁路补造（`docs/host/phase7-plan.md:76`、`487`），并要求 bounded payload（`docs/host/phase7-plan.md:373`）。

影响：

如果实现只把 `error_code` 粗略映射成 `error_type`，但没有明确 `request_id = provider_request_id`、`partial_tool_name = None`、`attempt = None`、`partial_arguments_ref` 是否存在及 omitted reason，消费侧会难以区分 “确实无 partial arguments” 与 “projection 漏字段”。

建议修复：

- 在 plan 的映射表中增加 `PROVIDER_PROTOCOL_ERROR -> sse_protocol_error/provider_protocol_error` 字段级规则：
  - `error_type = data.error_code`
  - `request_id = data.provider_request_id or ""`
  - `partial_tool_name = None`
  - `attempt = None`
  - `partial_arguments_ref` 只允许 bounded / provider-secret-scrubbed `raw_payload` 引用，缺失时写 `omitted_reason`
- 增加 fixture 覆盖 raw payload 存在、raw payload 缺失、raw payload 超限或 provider secret 被 scrub 三种路径。

是否阻断 plan gate：否。

## 通过项

- 动机成立：P7 从 P6 durable EventLog / ProjectionCoordinator 派生 trace，而不是恢复 Engine `V2ToolTraceRecorder` / `JsonlToolTraceStore`，与总控计划和 Engine/Host 设计一致。
- 分层边界总体正确：plan 明确 Engine 不 import Host trace schema、不写 trace、不恢复 `ToolTraceRecorder`；ToolRuntime 只产出 canonical facts；Service/UI/public Host API 不在 P7 偷改。
- Observer 协议默认保持同步是合理选择：P6 `ObserverSink.process` 已在 `HostStorageTransaction` 内同步执行，并与 checkpoint 前进同事务提交；P7 若使用 SQLite 同事务写入，无需为 tool trace 单独 async 化。
- phase 边界基本清楚：plan 明确不做 P8 lease/fencing、P9 lifecycle、P10 ToolRegistry governance、P10.5 web tools、P11 validation、P15 audit hard-gate。
- trace payload 边界已按用户决策调整：provider secret 不进 trace；scope token、raw cursor、完整 prompt、大 tool result 不做过滤，按 OLD 热/冷分层保留，用于定位 `fetch_more` 重复调用、错 token / 错 cursor 和上下文问题。

## Residual Risk / Open Questions

- P7 是否默认注册进 durable harness：plan 把它列为待确认项。默认注册会让所有 durable smoke 多一个 observer 状态面；显式注册则更符合 P7 internal projection 的渐进落地。
- `tool_call` 的 `latency_ms` 在 NEW 中可从 `ToolResultMeta.started_at/finished_at` 派生，但 plan 未明确字段级规则；实现时应补测试。
- `ToolTraceRawPayloadRef.storage_uri` 若直接指 SQLite blob key，不应被误当成本地文件路径；若要兼容 OLD analyzer，需要 exporter/adapter 明确转换。
- P6 schema bootstrap 是 `CREATE TABLE IF NOT EXISTS`，但迁移约束要求全新起库。P7 继续扩 schema 时应避免写旧库兼容读取和兼容测试。
