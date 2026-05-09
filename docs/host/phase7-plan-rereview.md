# Host P7 Plan Re-review：Tool Trace Projection / Sink

结论：通过。

调整后的 P7 plan 已经对齐用户最新决策：`iteration_context_snapshot` 不再采用降级 snapshot，而是新增 Host-owned `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` durable fact；provider secret / Authorization / API key / cookie 不进 trace；scope token、cursor、prompt、tool result 按 OLD 热 / 冷分层保留；OLD `analyze_tool_trace.py` 的业务无关诊断能力被纳入 P7 主线。Host / Engine 架构边界也基本一致：Engine 不恢复 recorder/store，ToolRuntime 不直接写 trace，trace 由 ProjectionCoordinator 从 durable EventLog 派生。

本轮没有发现阻断 plan gate 的问题。下面 findings 均已由总控回写关闭；实现时仍需按 plan 中的不变量补测试。

总控处理状态：以下三项已回写到 `docs/host/phase7-plan.md` 与 `docs/host/design.md`：

- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` raw payload refs 与 EventLog fact 必须同一个 Host durable transaction 提交。
- analyzer / schema 路径固定为 `tool_trace_v2_host` + Host read API + JSONL exporter / analyzer adapter。
- durable harness 在配置 `ToolTraceStore` / trace storage path 时默认注册 `tool_trace_observer`，未配置时不注册。

## Findings

### [已修复] Medium - `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 的 raw payload 侧写事务边界仍需在实现前固定

证据：

- `docs/host/phase7-plan.md` 已要求 P7 在 RunInputBuilder 完成后写入 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact，并为完整 model input / tool schemas 写 raw payload ref。
- 同一 plan 建议新增 `host_tool_trace_raw_payloads`，但 raw payload 写入、EventLog append、context fact serializer 之间的事务边界仍主要以“写入失败不能静默继续”表达。
- `docs/host/design.md` 已把 P7 后目标路径写成 “Host writes RUN_INPUT_CONTEXT_SNAPSHOT_BUILT fact -> cold refs -> ProjectionCoordinator drains EventLog -> tool_trace_observer writes ToolTraceStore”。

影响：

如果 raw payload ref 与 EventLog fact 不在同一个 durable unit of work 中，崩溃窗口可能留下“fact 已落库但 raw ref 缺失”或“raw payload 已落库但 fact append 失败”的不一致。后者只是孤儿冷存，影响较小；前者会破坏 `iteration_context_snapshot` 可回放语义，让 analyzer 看到看似完整但无法读取 raw input 的记录。

建议：

- 实现前固定一种策略：
  - 首选：raw payload 写入与 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` append 使用同一个 Host durable transaction，fact 只引用已同事务提交的 raw payload。
  - 可接受备选：如果无法同事务，fact payload 必须显式携带 `raw_payload_write_failed` / `raw_ref_missing` 状态，tool trace 不得把它伪装成完整 snapshot。
- 增加测试覆盖：fact 已写但 raw payload ref 缺失时，projection 必须 blocked 或生成明确 degraded / omitted reason，不能生成完整 `iteration_context_snapshot`。

是否阻断 plan gate：否。当前 plan 已抓住正确方向，但实现 prompt / code review 必须把事务不变量列为重点。

### [已修复] Medium - analyzer / schema 输出路径仍是进入实现前的用户确认项

原始证据：

- `docs/host/phase7-plan.md` 曾要求实现前在 `tool_trace_v2_host + read API / analyzer adapter` 与 `tool_trace_v2 + 逐字段兼容矩阵` 之间二选一。
- OLD `utils/analyze_tool_trace.py` 只读取 JSONL，并按 `trace_schema_version == "tool_trace_v2"` 与五类 record 字段解析。
- 用户最新决策是“迁移 OLD analyze_tool_trace 中业务无关部分”，但尚未指定 NEW 直接输出 OLD-compatible JSONL，还是提供 Host SQLite read model 的 adapter/exporter。

修复后证据：

- `docs/host/phase7-plan.md` 已固定采用 `tool_trace_v2_host` + Host read API + JSONL exporter / analyzer adapter。
- `docs/host/design.md` 已同步写明 Host 内部 read model 不伪装成完全 OLD-compatible schema。

影响：

如果实现阶段不先固定路径，容易出现两类偏差：SQLite trace projection 正确但 analyzer 不可用；或者为了复用 OLD analyzer，把 NEW 语义伪装成完全 OLD-compatible，掩盖 `provider_protocol_error` / Host-owned context fact 等有意差异。

建议：

- 实现前必须由总控固定一个选项并写入 plan 或 implementation prompt。
- 若选 `tool_trace_v2_host`，P7 必须交付 analyzer adapter 或 exporter，并用 fixture 验证业务无关分析项可用。
- 若选 `tool_trace_v2`，P7 必须提供 OLD compatible / degraded / missing 字段矩阵，避免 analyzer 把有意差异误判为完整 OLD 语义。

是否阻断 plan gate：否。短复核确认该项已关闭，不再阻断代码实施入口。

### [已记录-实现复核] Low - `provider_protocol_error` / `sse_protocol_error` 命名需要在实现中避免双重事实

证据：

- OLD trace record 使用 `sse_protocol_error`。
- NEW Engine / Host 事件语义是 `PROVIDER_PROTOCOL_ERROR`。
- `docs/host/phase7-plan.md` 已允许 internal record type 使用 `PROVIDER_PROTOCOL_ERROR`，OLD-compatible 文件输出可映射为 `sse_protocol_error`。

影响：

如果实现同时写 internal `provider_protocol_error` 和 exported `sse_protocol_error` 两条 hot records，而不是同一事实的两种投影名称，analyzer 可能重复计数协议错误。

建议：

- ToolTraceStore 内部只保留一个 canonical record type。
- exporter / adapter 负责把它映射为 OLD `sse_protocol_error` 字面量。
- 增加 fixture 确认同一 provider protocol error 在 analyzer 聚合中只计一次。

是否阻断 plan gate：否。

## 通过项

- Host-owned fact 决策已落地：`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 是 durable EventLog / projection 真源，不依赖 `LocalRunHarness` LRU、`RunInputBuildTrace` 内存缓存、Engine 私有对象或日志文本。
- trace payload 边界已与用户决策一致：provider secret 类能力凭据不进 trace；scope token / cursor / prompt / tool result 默认保留在 trace 冷层，用于真实故障定位。
- P7 仍遵守分层边界：Engine 只产出强类型事件；ToolRuntime 只产出工具运行事实；ProjectionCoordinator / observer / sink 负责派生 trace read model。
- OLD 业务无关诊断语义覆盖充分：重复调用、truncation -> fetch_more、fetch_more 参数 / 质量、trace 完整性、context pressure、provider protocol error、final response presence 都进入 plan / 测试 / review gate。
- schema 与 replay 风险已被计划约束：确定性非空 idempotency key、sink/checkpoint 同事务、cross-batch pending durable state、重复 drain 与 crash replay 测试均有安排。
- P8/P9/P10 边界清晰：不引入 lease/fencing，不固定 public lifecycle，不扩大 ToolRegistry governance，不迁移 web/business tools。

## 短复核

结论：通过。

- 条件 1 已关闭：`docs/host/phase7-plan.md` 已固定 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` raw payload refs 与 EventLog fact 在同一个 Host durable transaction 中提交；raw payload 写入或 context fact append 任一失败时整笔 transaction 回滚，Engine attempt 不启动。`docs/host/design.md` 也同步写明该 durable unit of work。
- 条件 2 已关闭：`docs/host/phase7-plan.md` 已固定 analyzer / schema 路径为 `tool_trace_v2_host` + Host read API + JSONL exporter / analyzer adapter，不再保留 `tool_trace_v2` 兼容矩阵二选一。
- 条件 3 已关闭：`docs/host/phase7-plan.md` 已固定 durable harness observer 注册策略：配置 `ToolTraceStore` / trace storage path 时默认注册 `tool_trace_observer`，未配置 trace store 时不注册。
- 条件 4 已关闭：本文件的 finding 标题已标注状态；两个 Medium finding 标为 `[已修复]`，Low finding 标为 `[已记录-实现复核]`。
