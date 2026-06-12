# WU-OBS-SIGNALS-01 Aggregate Deepreview Controller Adjudication

## Verdict

修复后进入 re-review。

## 输入

- AgentMiMo aggregate deepreview: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-mimo.md`
- AgentDS aggregate deepreview: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-ds.md`
- Work unit: `WU-OBS-SIGNALS-01`
- 设计真源: `docs/host/design.md`, `docs/engine/design.md`
- 总控: `docs/host/issues-implementation-control.md`

## 裁决

### Finding A: 三模块中常量与 bounded text 规则重复定义

- 来源: AgentDS finding 1
- 严重度: 低
- 裁决: accepted
- 原因: 该 finding 有直接代码证据，`tool_runtime.py`、`engine_ingest.py`、`tool_trace.py` 分别维护 Tool Trace signal schema version、failure kind、status 与 bounded text 上限。当前行为正确，但该重复命中项目约束中“重复逻辑必须抽取”，且后续新增 failure kind 或调整 bounded text 上限时容易形成 producer / consumer drift。
- 处理: 在当前 aggregate deepreview fix gate 内修复。新增 Host 内部共享模块 `dayu.host.tool_trace_signals`，集中 signal schema version、status、failure kind、closed union 与 bounded text 裁剪 helper；三个生产/消费模块只引用该单一真源。

### Finding B: `_context_compaction_request_payload` 在 projection 内做跨 event read

- 来源: AgentDS finding 2
- 严重度: 低
- 裁决: not accepted as current fix
- 原因: 当前实现只在 `CONTEXT_COMPACTION_FAILED` 投影时按 `operation_id` 做一次 SQLite primary-key read，缺失时降级为 `None`，不影响正确性，不引入治理副作用，也没有当前规模下的性能证据。该读取是为了从同一 durable EventLog 追溯 compaction request payload，仍属于 Host 事实范围内的只读派生。
- 后续: 若后续 Tool Trace catch-up 行量达到导致可测性能问题，再由 Tool Trace / retention 相关 WU 评估 batch-level prefetch。当前不新增 active residual risk。

## Re-review 入口

Aggregate deepreview fix artifact: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-fix-codex.md`

Re-review 需重点确认：

- `dayu.host.tool_trace_signals` 不引入反向依赖，不进入 `dayu.runtime`，不暴露给 LLM-facing 文本。
- `tool_runtime.py`、`engine_ingest.py`、`tool_trace.py` 的 JSON signal 形状、schema version、status、failure kind、bounded text digest 与截断规则保持不变。
- ToolRuntime 校验仍抛 `ValueError`，ToolTrace projection 校验仍抛 `HostDurableError`。
- P01/P02/P03/P04 signal 的来源约束不变。

