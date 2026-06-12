# WU-OBS-SIGNALS-01 Aggregate Deepreview (AgentDS)

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main`
- Output file: `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-ds.md`
- Included scope: `dayu/host/engine_ingest.py`, `dayu/host/tool_runtime.py`, `dayu/host/tool_trace.py`, 6 test files, README updates, control document updates
- Excluded scope: `docs/reviews/` review artifacts（只读参考，不做重复审查）；`docs/host/wu-obs-signals-p01-p04-plan.md` plan gate（已通过 controller adjudication）；WU-OBS-00 analyzer（明确 non-goal）
- Parallel review coverage: 无（本 review 为单一 aggregate 审查，未分派 subagent）
- Design truth sources: `docs/host/design.md`，`docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`

## Findings

### 1-未修复-低-三模块中常量与 bounded text 验证逻辑重复定义

- **入口/函数**: `_bounded_failure_text`（`tool_runtime.py`）、`_validate_bounded_text_field`（`tool_trace.py`）、`_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 常量引用
- **文件(行号)**:
  - `dayu/host/tool_trace.py:173` — `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`
  - `dayu/host/tool_runtime.py:240` — `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`
  - `dayu/host/tool_trace.py:174-176` — `_FAILURE_KIND_TOOL_FAILED / _TOOL_CANCELLED / _POLICY_BLOCKED`
  - `dayu/host/tool_runtime.py:241-243` — 同三个常量
  - `dayu/host/engine_ingest.py:263` — `_FAILURE_KIND_PROVIDER_PROTOCOL_ERROR`
- **输入场景**: 后续修改 bounded text 上限（如 512→1024）或增加新 failure kind 时
- **实际分支**: 三个模块各自维护相同的常量值和相似的 bounded text 校验逻辑
- **预期行为**: 跨模块共享的 contract 级常量应定义在公共契约或单一 owner 模块
- **实际行为**: tool_trace.py（projection 层）、tool_runtime.py（accept 层）、engine_ingest.py（ingest 层）各自定义了一份 `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS`；`tool_runtime.py` 和 `tool_trace.py` 各有一份 `_FAILURE_KIND_TOOL_FAILED / _TOOL_CANCELLED / _POLICY_BLOCKED`
- **直接证据**:
  - `tool_trace.py:173` vs `tool_runtime.py:240`：同一字面量 512 在两层独立定义
  - `tool_trace.py:182-189` 定义了完整闭集 `_FAILURE_METADATA_ALLOWED_KINDS` frozenset，但 `tool_runtime.py:4462-4473` 的 `_validate_failure_metadata_signal` 只校验了三个 kind（tool_failed / tool_cancelled / policy_blocked），provider_protocol_error 和 compaction 变体由 tool_trace.py 独立校验——两套校验闭集不一致
  - bounded text 校验逻辑在 `tool_runtime.py:4524-4548`（`_validate_bounded_text_fields` raise ValueError）和 `tool_trace.py:1695-1721`（`_validate_bounded_text_field` raise HostDurableError）实质相同但维护两份
- **影响**: 中度 maintainability 风险——bounded text 上限修改、新增 failure kind 或校验规则变更时容易漏改造成 producer-consumer contract drift。当前行为正确，两份代码未出现逻辑分歧，但缺少编译期或测试期强制同步机制
- **建议改法和验证点**: 将 `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 和 signal schema version / failure kind / event type 等 contract 级常量抽取到 `dayu.host.durable.tool_trace`（或 `dayu.host.tool_trace_contracts`）单一模块，供 tool_runtime、engine_ingest、tool_trace 三模块引用。bounded text 校验也可考虑抽取公共 `_validate_bounded_text_signal(signal, field_name, error_factory)` 辅助函数。此改法非紧急，适合后续 WU 随 analyzer 落地时重构
- **修复风险（低）**: 抽取常量不改变运行时行为；bounded text 校验抽取需要确保 tool_runtime 仍 raise ValueError 而 tool_trace 仍 raise HostDurableError
- **严重程度（低）**: 当前无行为 bug，纯 maintainability 风险

### 2-未修复-低-`_context_compaction_request_payload` 在 projection 内做跨 event read

- **入口/函数**: `_context_compaction_request_payload` → `_context_compaction_failed_pressure` → `_canonical_trace_summary_signals` → `_extract_canonical_trace`
- **文件(行号)**: `dayu/host/tool_trace.py:1359-1377`
- **输入场景**: Tool Trace projection 处理 `CONTEXT_COMPACTION_FAILED` canonical fact 时，需要读取对应的 compaction request fact 的 payload 字段（如 policy_ref、estimator_digest）
- **实际分支**: `_context_compaction_request_payload` 调用 `read_event_by_id(transaction, operation_id)` 从同一 Host SQLite durable store 读取引用事件
- **预期行为**: Projection 通常只消费当前 event 的 payload，跨 event read 应在设计上明确标记为 bounded 且不引入 N+1 风险
- **实际行为**: 当前实现正确——通过 `operation_id` 读取 request fact payload，不存在则返回 None 并将下游字段置为 None；无 N+1 问题（每次 compaction failed 事件最多一次额外 read）
- **直接证据**:
  - `tool_trace.py:1370`: `row = read_event_by_id(transaction, operation_id)`
  - `tool_trace.py:1372`: `if row is None: return None` — 正确处理缺失
  - `tool_trace.py:1283-1298`: 调用方在 `request_payload is None` 时所有派生字段置为 None — 正确降级
- **影响**: 当前行为正确。长期风险：大规模 catch-up 时每个 compaction failed 事件产生一次额外 SQLite read；当前 batch size 约束下此开销可忽略，但未来若 trace 行量极大，可能需要在 catch-up 的 batch 级做 prefetch
- **建议改法和验证点**: 当前无需修复。若未来 trace 行量达到数万级别且有性能问题时，可在 `_canonical_trace_summary_signals` 添加 batch-level request fact prefetch。当前实现中 `read_event_by_id` 通过 SQLite primary key 查询，性能可接受
- **修复风险（低）**: 暂不修复
- **严重程度（低）**: 正确性不受影响，性能风险当前不成立

## Open Questions

- 无。所有 review items 均有充分证据支撑判断。

## Coverage Notes

### P01 context_pressure 来源审查

- **入口**: `EngineEventIngestor._append_usage_projection_signal`（`engine_ingest.py:2661-2715`）
- **信号构造**: `_usage_context_pressure_signal`（`engine_ingest.py:4112-4171`）
- **来源验证**:
  - `BudgetEstimate` 字段（`input_budget_tokens`, `soft_threshold_tokens`, `hard_threshold_tokens`）→ 来自 Host context_budget owner
  - `decide_context_budget(estimate)` → 来自 `dayu.host.context_budget`
  - `UsageReportedData`（`prompt_tokens`, `completion_tokens`, `total_tokens`）→ 来自 Engine usage report
  - `UsageObservationDiagnostic`（`status`, `policy_ref`, `estimator_digest`, `estimated_input_tokens`）→ Host 计算的使用量诊断
  - 阈值比较 `estimate.estimated_input_tokens >= estimate.soft_threshold_tokens` 使用 `>=`，at-threshold 算 exceeded → 正确
  - `estimate is None` 时所有 budget 字段为 `None`，`budget_decision` 为 `"unknown"` → 正确降级
- **compact 派生路径**: `_context_compaction_failed_pressure`（`tool_trace.py:1233-1299`）和 `_context_compaction_attempt_rejected_pressure`（`tool_trace.py:1302-1325`）从现有 compact canonical payload 派生，不引入新 Engine 或治理事实
- **副作用检查**: `context_pressure` 写入 projection_signal payload → Tool Trace projection 只读复制到 `trace_summary` → 不进入 Run/Attempt 状态机、ToolRuntime governance、memory projection 或 recovery 路径
- **结论**: PASS。context_pressure 信号来源稳定且只来自 Host budget/usage 和现有 compact payload，无治理副作用

### P02 tool_timing 来源审查

- **入口**: `_tool_fact_accept_candidate` → `_tool_timing_from_meta`（`tool_runtime.py:6083-6110`）
- **meta 提取**: `_tool_result_meta`（`tool_runtime.py:6064-6080`）按 typed outcome 分支：
  - `ToolCompletedOutcome` → `outcome.result.meta`
  - `ToolFailedOutcome` → `outcome.result.meta`
  - `ToolCancelledOutcome` → `outcome.meta`
  - `ToolAwaitingOutcome` → raise TypeError（不参与 accept 流程）
- **duration 计算**: `int((meta.finished_at - meta.started_at) // _ONE_MILLISECOND)` — 只来自 `ToolResultMeta` 的两个 datetime 字段
- **缺失降级**: `meta is None` 时返回 `status="missing_tool_result_meta"`，所有时间字段为 null → 正确
- **副作用检查**: `tool_timing` 写入 `TOOL_RESULT_ACCEPTED` canonical fact payload → Tool Trace projection 只读复制 → ToolRuntime 执行/accep/governance 语义不受此字段影响
- **结论**: PASS。tool_timing 信号只来自 `ToolResultMeta.duration`，不污染 ToolRuntime 治理语义

### P03 failure_metadata 闭集审查

- **闭集定义**: `tool_trace.py:182-189` `_FAILURE_METADATA_ALLOWED_KINDS = frozenset({tool_failed, tool_cancelled, policy_blocked, provider_protocol_error, context_compaction_attempt_rejected, context_compaction_failed})` — 6 个变体
- **来源映射**:
  | failure_kind | signal_source | 生产位置 |
  |---|---|---|
  | `tool_failed` | `TOOL_RESULT_ACCEPTED` | `tool_runtime.py:6140-6151` `_failure_metadata_from_outcome` from `ToolFailedOutcome` |
  | `tool_cancelled` | `TOOL_RESULT_ACCEPTED` | `tool_runtime.py:6152-6167` from `ToolCancelledOutcome` |
  | `policy_blocked` | `TOOL_RESULT_ACCEPTED` | `tool_runtime.py:6129-6137` from `ToolPolicyDecision` |
  | `provider_protocol_error` | `PROVIDER_PROTOCOL_ERROR` | `engine_ingest.py:5950-5973` from `ProviderProtocolErrorData` |
  | `context_compaction_attempt_rejected` | `CONTEXT_COMPACTION_ATTEMPT_REJECTED` | `tool_trace.py:1304-1323` from compact event payload |
  | `context_compaction_failed` | `CONTEXT_COMPACTION_FAILED` | `tool_trace.py:1330-1356` from compact event payload |
- **变体验证**: `_validate_failure_metadata_variant`（`tool_trace.py:1472-1532`）对全部 6 个变体做了 signal_source 匹配和变体字段校验，default 分支 raise HostDurableError → 闭集完备
- **bounded text 规则**: 执行路径覆盖 null、exact-512 边界、over-512 截断，digest 为 `sha256:<hex>` 前缀格式：
  - `_bounded_failure_text`（`tool_runtime.py:6188-6206`）→ 生产端
  - `_validate_bounded_text_field`（`tool_trace.py:1695-1721`）→ 投影端校验
  - 两端规则一致：null → (null, null, false)；non-null → (bounded[0:512], digest over full original, truncated=len>512)
- **completed 互斥**: `_validate_candidate_failure_metadata`（`tool_runtime.py:4481-4503`）在 `ToolFactKind.COMPLETED` 时要求 `failure_metadata=None` → 正确
- **结论**: PASS。failure_metadata 是闭集 union，来源只限 typed outcome / Engine data / context payload，bounded text 规则正确

### P04 partial_tool_call_signal 有界性审查

- **入口**: `_provider_protocol_partial_tool_call_signal`（`engine_ingest.py:5978-6007`）
- **Engine 契约**: 参数类型 `tuple[PartialToolCallSummary, ...]` — Engine 已裁剪和脱敏的有界摘要
- **序列化字段**: `_partial_tool_call_summary_payload`（`engine_ingest.py:6010-6028`）只暴露:
  - `tool_call_index`（int）
  - `tool_call_id`（str | None）
  - `name_fragment`（str | None）— 工具名片段，非完整调用
  - `arguments_byte_size`（int）
  - `arguments_sha256`（str | None）— bare 64-char hex digest
  - `arguments_present`（bool）
- **raw args 检查**: 无 `arguments` 字段，无 `raw_payload` 字段，无 `stream` 字段。`arguments_sha256` 是 Engine 预计算的裸 sha256 hex（不带 `sha256:` 前缀），由 `_is_bare_sha256_hex`（`tool_trace.py:1647-1655`）校验为 64 位小写十六进制
- **投影层校验**: `_optional_partial_tool_call_signal`（`tool_trace.py:1535-1579`）校验 `partial_tool_call_count` 与 `partial_tool_calls` 数组长度一致、summary_status 与 count 一致、每个 summary 的 arguments_present 与 arguments_sha256 一致
- **redaction 边界**: `raw_payload_present` 仅指示 Host raw payload descriptor 是否存在，不泄漏 payload 内容
- **结论**: PASS。partial_tool_call_signal 只来自 Engine bounded PartialToolCallSummary，无 raw args/raw stream 泄漏

### OBS-SIG-05 query helper 集成路径审查

- **测试入口**: `test_query_helpers_return_rows_ordered_by_event_sequence`（`test_tool_trace_queries.py`）与 `test_provider_request_id_terminal_diagnostic_query`
- **验证路径**:
  - Hot row 中 `trace_summary` 包含四类 signal → `_assert_trace_summary_signals`
  - `run` query helper: `query_tool_trace_rows_by_run` 返回的 `trace_summary` 保留 `context_pressure`, `tool_timing`, `failure_metadata`
  - `tool_call` query helper: `query_tool_trace_hot_rows_by_tool_call_id_prefix` 同样保留
  - `diagnostic` query helper: `query_tool_trace_rows_by_diagnostic_ref` 同样保留
  - `provider` query helper: `query_tool_trace_rows_by_provider_request_id` 保留 `partial_tool_call_signal`
  - `run_next` query helper: cursor-based pagination 保留 signal
  - 所有 query helper 返回的 `trace_summary` 通过 cold JSONL 等价验证（`_cold_trace_summary` 比较 hot row 与 cold line）
- **结论**: PASS。四类信号在 run/tool-call/diagnostic/provider 查询路径中保持

### Engine contract/schema、ToolRuntime、analyzer 层级依赖审查

- **Engine contract 消费**: `engine_ingest.py:52` import `PartialToolCallSummary` from `dayu.engine.contracts.partial_tool_call` — 正确的 Host→Engine 单向依赖，只消费 Engine 公开契约
- **ToolRuntime 扩展**: `tool_runtime.py` 新增 `ToolAcceptResult.tool_timing` 和 `.failure_metadata` 字段，新增 `_tool_timing_from_meta`、`_failure_metadata_from_outcome` 等辅助函数 — 都是 Host 层内部 paylaod 序列化，未修改 ToolRuntime accept/governance/execution 核心语义
- **ToolTrace analyzer 未实现**: WU-OBS-00 analyzer 为明确 non-goal，当前无 analyzer 代码
- **反向依赖检查**: 无 Host→Engine 反向 import，无 ToolRuntime→ToolTrace 反向 import，无 ToolTrace→Engine 反向 import
- **scheam 未修改**: SQLite `host_tool_trace_hot` 表 schema 未变，signal 全部存储在现有 `trace_summary_json` TEXT 列
- **结论**: PASS。无过度扩展，无层级反向依赖

### hot/cold summary 等价与状态转移副作用审查

- **hot/cold 等价**: `_trace_summary`（`tool_trace.py:1102-1191`）统一构造 hot summary JSON；`_write_cold_trace` 将同一 summary 写入 cold JSONL；测试 `test_tool_trace_copies_optional_summary_signal_objects` 和 `test_tool_trace_projects_tool_timing_available_and_missing_signals` 等均断言 `_cold_trace_summary(cold_lines, i) == row.trace_summary`
- **状态转移**: 本 WU 不修改任何 Run/Attempt 状态机。projection_signal 和 diagnostic 事件保持 non-governing 地位
- **治理语义**: `tool_timing`、`failure_metadata`、`context_pressure`、`partial_tool_call_signal` 均为 additive payload 字段，现有 consumer（recovery、resume、memory、audit、outbox、lifecycle state indexes）不读取这些新字段，行为不受影响
- **结论**: PASS

### README 更新触发合规

- `dayu/host/README.md` 第 353 行：将 tool trace 描述从"记录工具执行 hot rows 与诊断"扩展为"记录工具执行 hot rows 与诊断，并投影 context pressure、tool timing、failure metadata 等只读结构化 signal"——准确反映本次变更范围，不泄漏内部实现细节
- `tests/README.md` 第 164 行：Tool Trace 测试覆盖描述增加"context pressure / tool timing / failure metadata 结构化 signal"——与新增测试覆盖一致
- `docs/host/issues-implementation-control.md`：正确记录 WU-OBS-SIGNALS-01 的 gate 状态（deepreview）、slice commit 列表、WU-PROJ-01 合并状态更新、P01-P04 合并进 WU-OBS-SIGNALS-01
- 未触发 `dayu/engine/`、`dayu/fins/`、`dayu/config/` README 更新
- **结论**: PASS

### pyright/tests 充分性审查

- **pyright**: 0 errors, 0 warnings, 0 informations（全项目检查通过）
- **测试执行**: 全部受影响测试通过
  - `tests/host/test_tool_trace_projection.py`: 33 passed — 覆盖 signal 复制、timing signal、failure metadata（6 变体 + malformed rejection）、partial tool-call signal（状态 + malformed rejection）、context compaction pressure 派生、bounded text malformed 校验
  - `tests/host/test_tool_trace_queries.py`: 33 passed — 覆盖 query helper 四路径 signal 保持 + provider_request_id diagnostic query
  - `tests/host/test_toolruntime_executor.py`: 33 passed — 覆盖 failed/cancelled/policy_blocked failure metadata 生产 + bounded text parametrize (null / 512 / 513)
  - `tests/host/test_engine_ingest_mapping.py`: 61 passed — 覆盖 engine_ingest context_pressure signal 映射
  - `tests/host/test_toolruntime_accept_barrier.py`: 30 passed — 覆盖 accept barrier 中 ToolAcceptResult signal 字段
  - `tests/host/test_phase6_toolruntime_integration.py`: 3 passed — 集成
  - 合计: 193 passed, 0 failed
- **边界覆盖**: bounded text 测试覆盖 null、exact-512（不截断）、513（截断 + digest）；failure metadata 测试覆盖全部 6 个变体；partial tool-call signal 测试覆盖 none/present 状态 + 内部一致性校验 + malformed rejection
- **Fail-closed 覆盖**: malformed timing signal（非法 duration、非法 status、缺失字段）→ HostDurableError；malformed failure metadata（非法 kind、非法 source、非法 bounded text）→ HostDurableError；malformed partial tool-call signal（count mismatch、非法 arguments_sha256、非法 status）→ HostDurableError
- **结论**: PASS

## Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 三地重复定义导致未来 drift | Low | WU-OBS-SIGNALS-01 maintainer | 见 Finding 1；建议后续 WU 将常量收敛到 `dayu.host.durable.tool_trace` 共享模块 |
| WU-OBS-00 analyzer 未落地 | Medium | WU-OBS-00 | 明确 non-goal；analyzer 是 signal 的唯一消费方，缺失则 signal 无法产生可观测价值；在 control document 中已登记为 `pending-prerequisite` |
| `_context_compaction_request_payload` 跨 event read 在大规模 catch-up 时的性能 | Low | WU-OBS-SIGNALS-01 maintainer | 见 Finding 2；当前 batch size 下不构成实际问题 |
| tool_runtime.py `_validate_failure_metadata_signal` 只校验 3 个 kind 而非完整 6 个闭集 | Note | WU-OBS-SIGNALS-01 maintainer | 这是正确的——tool_runtime 只生产 tool_failed / tool_cancelled / policy_blocked，其它 3 个 kind 由 engine_ingest 和 tool_trace 生产。不需要在 tool_runtime 校验 engine_ingest/tool_trace 的 kind。当前 tool_runtime.py `_validate_failure_metadata_signal` 的 `raise ValueError("failure_metadata.failure_kind is unsupported")` 对于 tool_runtime 生产的信号是完备的 |

## Validation

### 运行验证

```text
pyright (full project): 0 errors, 0 warnings, 0 informations
Test run summary:
  tests/host/test_tool_trace_projection.py:       33 passed
  tests/host/test_tool_trace_queries.py:           33 passed
  tests/host/test_toolruntime_executor.py:         33 passed
  tests/host/test_engine_ingest_mapping.py:         61 passed
  tests/host/test_toolruntime_accept_barrier.py:   30 passed
  tests/host/test_phase6_toolruntime_integration.py: 3 passed
  Total:                                           193 passed, 0 failed
```

### 采信验证

- pyright 全项目 clean（0 errors）
- 所有 193 个受影响 Host 测试通过
- Controller adjudication 链完整（OBS-SIG-00 至 OBS-SIG-05 各 gate 均已 adjudicated）
- plan review / code review / fix / re-review 各阶段 artifact 均在 `docs/reviews/` 下可追溯
- README / control document 更新与实现一致

## Verdict

**PASS**

四类 signal (P01 context_pressure, P02 tool_timing, P03 failure_metadata, P04 partial_tool_call_signal) 的来源均受控于规划范围：P01 只来自 Host budget/usage 和 context compact payload，P02 只来自 ToolResultMeta duration_ms，P03 是正确闭集 union（6 种 failure_kind），P04 只来自 Engine bounded PartialToolCallSummary 无 raw args 泄漏。signals 均为 additive payload 字段，不影响 Run/Attempt 状态机、ToolRuntime governance/execution 语义或其它 consumer。hot/cold summary 等价性已通过测试断言验证。pyright 0 errors，193 tests pass。无层级反向依赖，无 schema 变更。两个低严重度 finding（常量重复定义、跨 event read）为 maintainability 关注点，不影响 ship 决策。WU-OBS-00 analyzer 是 OBS-SIGNALS-01 的预期消费方，当前 `pending-prerequisite` 状态已在 control document 登记，因而是已知的 residual risk 而非未识别缺陷。
