# Host P7 实施 Plan：Tool Trace Projection / Sink

## Context

P6 已经把 RunEvent 变成 durable canonical facts，并提供 `ProjectionCoordinator` / `ProjectionStore` / `ObserverSink` 基础设施。当前 Engine `EngineEvent` 与 ToolRuntime canonical facts 已能覆盖工具运行真源，但仍缺少：

1. 一个 Host-owned 的 read-model，能让本地诊断工具按 `run_id` 聚合工具调用、迭代上下文、usage、final response、provider protocol error 等 OLD `tool_trace_v2` 关键诊断语义。
2. `iteration_context_snapshot` 的 durable 真源——P6 EventLog 没有持久化真实 `model_input_messages` 与完整 `tool_schemas`，无法靠 `RunInputBuildTrace` 进程内缓存做 replay。
3. 与 OLD 仓库 `workspace/output/tool_call_traces/` 中 JSONL + raw_payloads 文件布局兼容的导出能力，让现存 `utils/analyze_tool_trace.py` 业务无关诊断（重复调用、truncation→fetch_more、fetch_more 参数质量、context 压力、protocol error、final response presence）能继续工作。

P7 要在不恢复 Engine 私有 recorder/store、不扩大 ToolRegistry 治理、不动 Host public interface 的前提下，落地完整 Host-owned tool trace projection。已通过 plan：`docs/host/phase7-plan.md`；review：`docs/host/phase7-plan-review.md`、`docs/host/phase7-plan-rereview.md`，全部 finding 已关闭。

预期产出：
- 新增 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` Host-owned canonical fact（**作为 P6 EventLog 的 patch，不是 trace 的一部分**）。fact payload 内联完整 model_input_messages 与 tool_schemas raw JSON；harness 在外层 `HostStorage.transaction()` 中以单条 `append_in_transaction(tx, draft)` 提交，不引入新 SQLite 表。
- `ToolTraceObserver` 实现 `ObserverSink`：在 `process(tx, batch)` 中把 EventLog canonical facts 派生为 trace records，**直接写 JSONL 文件**到 `DurableHarnessConfig.tool_trace_path` 下；同时把 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 内联的 raw payload 拆成两个 JSON 文件写到 `raw_payloads/<run_id>_<iteration_id>/`。
- JSONL 每行内嵌 `idempotency_key` 字段（sha256 of source provenance），analyzer / 测试用它去重；crash 重写产生的副本由 key 去重，无 SQLite 索引依赖。
- JSONL 每行写完 flush + fsync（用户决策：每行 fsync）。
- analyzer (`utils/analyze_tool_trace_host.py`) 全新设计，**不兼容 OLD `tool_trace_v2`**；只读 NEW `tool_trace_v2_host` 字段。
- `DurableHarnessConfig.tool_trace_path: str | None`：非空时装配 observer + JSONL 输出根目录；为 None / 空时不装配。
- 完整测试 + smoke + pyright；更新 host / tests / 根 / design README。

---

## 决策固定项（user 已拍板）

| 项 | 决策 |
| --- | --- |
| 新增 SQLite 表 | **0 张**。tool trace 完全走文件系统；P7 唯一动到的 SQLite 写入是 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 作为新 RunEventType 追加到既有 EventLog 表（属于 P6 EventLog 的事实补齐 / patch，不是 trace 的存储）。 |
| context fact raw payload 承载 | fact payload 内联完整 model_input_messages JSON 与 tool_schemas JSON（EventLog row 是 TEXT 列，无大小硬上限；plan §13 已允许 cold layer 大体积）。observer 阶段从 EventLog 读出 fact 后再拆文件。**不新增 raw_payloads 表。** |
| 装配条件 | `DurableHarnessConfig.tool_trace_path: str \| None`；非空（且非空字符串）即装配 `ToolTraceObserver`，路径同时是 JSONL 输出根目录。**不引入 `enable_tool_trace` 布尔。** |
| Trace 存储 | 单一来源 = JSONL 文件。Sink 在 `observer.process` 中实时 append 一行 + flush + fsync（每行 fsync）；checkpoint 推进与文件系统写不在同一原子单元，crash 窗口产生的孤儿副本由 JSONL 行内 `idempotency_key` 字段去重。 |
| Observer 阻塞性 | P6 `coordinator.drain()` 由 `_project_terminal_run` 同步 await（`_run_harness.py:1020`），sink 慢会拖慢**单个 run 的 terminal 完成**，但不阻塞 Engine 事件产生（Engine → EventLog.append 旁路 sink）。本地诊断场景可接受。**P7 不引入异步后台 drain**（属 P9 范畴）。 |
| Schema 字面量 | JSONL `trace_schema_version="tool_trace_v2_host"`。**完全自有 schema，不向 OLD `tool_trace_v2` 提供任何字段映射 / 兼容矩阵 / 适配层。** |
| analyzer 行为 | 仅读 `tool_trace_v2_host`；遇 OLD `tool_trace_v2` 文件直接跳过或报错（按测试结论选）。`utils/analyze_tool_trace.py` 完全无关，不修改。 |
| Pending 配对 | Engine 源头保证 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED` 同 batch；observer 单 batch 内配对，无 pending 表；不变量被破坏时抛 `ProjectionSchemaError` → P6 `BLOCKED_FAILED`。 |
| 交付节奏 | 分 3 个子阶段，每阶段独立通过 pyright + pytest。 |

---

## 子阶段划分

### 子阶段 S1 —— 契约 + Schema + 装配（基础层）

目标：写出 P7 一切上层逻辑都依赖的 RunEvent 契约、SQLite schema、装配配置。本阶段不引入任何 trace 派生逻辑，确保 P6 全量回归通过。

#### 新增

- **`dayu/host/contracts.py`**
  - `RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT = "run_input_context_snapshot_built"`。
  - 强类型 dataclass `RunInputContextSnapshotBuiltData`：
    - `iteration_id: str`
    - `iteration_index: int`
    - `attempt_index: int`
    - `current_user_excerpt: str`（bounded，已在 builder 截断）
    - `current_user_content_hash: str`
    - `current_user_source_cursor: int | None`
    - `message_summaries: tuple[RunInputMessageSummary, ...]`（hot-layer 摘要）
    - `tool_schema_summaries: tuple[RunInputToolSchemaSummary, ...]`（hot-layer 摘要）
    - `context_meta: RunInputContextMeta`
    - `raw_input_messages_json: str`（**完整 model_input_messages JSON 内联**；observer 阶段拆文件）
    - `raw_tool_schemas_json: str`（**完整 tool_schemas JSON 内联**；observer 阶段拆文件）
    - `raw_input_blob_id: str`（observer 写文件时使用的稳定文件名标识）
    - `raw_tool_schemas_blob_id: str`
  - 配套新 dataclass：`RunInputMessageSummary(role, source_kind, excerpt, content_hash, char_size, token_estimate)`、`RunInputToolSchemaSummary(name, schema_hash)`、`RunInputContextMeta(message_count, role_sequence, total_char_size, total_token_estimate, memory_item_count, current_user_run_id)`。
  - 把新 data 加入 `RunEventData` 联合，并 `__all__` 导出。

- **`dayu/host/_run_event_serializer.py`**
  - 在 `_DATA_CLASS_BY_TYPE` 注册 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT -> RunInputContextSnapshotBuiltData`。
  - `_encode_fields` / `_decode_fields` 增加分支；嵌套 summary 结构编码为 JSON object 列表；`raw_input_messages_json` / `raw_tool_schemas_json` 直接以字符串落入 EventLog `data` 列。

- **`dayu/host/_durable_event_store.py`**
  - **不新增任何 SQLite 表**。仅确认 `_append_in_transaction` 既有逻辑足以承载 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`（`run_events` 表 `data` TEXT 列已无大小硬限制）。
  - `DurableRunEventStore` 暴露 `_append_in_transaction` 的 thin 公共包装 `append_in_transaction(tx, draft)`，便于 harness 在外层 `HostStorage.transaction()` 内追加 context fact。

- **`dayu/host/_durable_harness.py`**
  - 新增 `@dataclass(frozen=True, slots=True) class DurableHarnessConfig`：
    - `database_path: str`（必填，复用 P6 EventLog DB）。
    - `tool_trace_path: str | None = None`：JSONL 输出根目录；`None` 或空字符串视为未配置 trace，不装配 observer。**这是 trace observer 的唯一装配开关。**
  - `build_durable_harness(*, config: DurableHarnessConfig, executor=None, memory_store=None, proxy=None)` 接受 config；旧 `database_path` 位置参数删除（CLAUDE.md 禁兼容代码）。
  - `tool_trace_path` 非空时构造 `ToolTraceJsonlSink` + `ToolTraceObserver`（S2 落地）并附加进 coordinator observer 元组；空时不构造、不注册。
  - `DurableHarnessBundle` 增加 `tool_trace_observer: ToolTraceObserver | None` 字段。

#### 测试（新增）

- **`tests/host/test_phase7_contract_serializer.py`**
  - `test_run_input_context_snapshot_built_round_trip`
  - `test_run_input_context_snapshot_built_decode_rejects_unknown_fields`
  - `test_run_input_context_snapshot_built_registered_in_data_class_by_type`

- **`tests/host/test_phase7_schema_bootstrap.py`**
  - `test_no_tool_trace_tables_added_to_sqlite_schema` —— 确认 P7 没有给 SQLite 引入 `host_tool_trace_*` 表，trace 完全走文件系统。
  - `test_run_event_data_column_accepts_inlined_raw_payload` —— `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 内联大体积 raw JSON 可正常 append + decode。

- **`tests/host/test_phase7_durable_harness_config.py`**
  - `test_durable_harness_config_default_tool_trace_path_none_skips_observer`
  - `test_durable_harness_config_empty_tool_trace_path_skips_observer`
  - `test_durable_harness_config_tool_trace_path_set_registers_observer`

#### 验证

```bash
source .venv/bin/activate
pytest tests/host/test_phase7_contract_serializer.py tests/host/test_phase7_schema_bootstrap.py tests/host/test_phase7_durable_harness_config.py -q
pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase6_durable_harness_integration.py -q
python -m pyright
```

S1 完成后向 user 汇报。

---

### 子阶段 S2 —— Sink + Observer + 同事务 Context Fact + 实时 JSONL

目标：把 EventLog canonical facts 实时派生为 JSONL 行（行内自带 `idempotency_key`），observer 写文件 + 每行 fsync；harness 在 RunInputBuilder 完成后、Engine attempt 启动前同事务追加 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact。**不动 SQLite schema**。

#### 新增

- **`dayu/host/_tool_trace_jsonl_sink.py`**
  - `class ToolTraceRecordType(StrEnum)`: `TOOL_CALL`、`ITERATION_CONTEXT_SNAPSHOT`、`ITERATION_USAGE`、`FINAL_RESPONSE`、`PROVIDER_PROTOCOL_ERROR`。
  - `class ToolTraceSchemaVersion(StrEnum)`: `TOOL_TRACE_V2_HOST = "tool_trace_v2_host"`。
  - 强类型 record dataclass（不使用 `Any` / `dict`；序列化 JSON 行时才扁平化）：
    - `ToolCallRecord`、`IterationContextSnapshotRecord`、`IterationUsageRecord`、`FinalResponseRecord`、`ProviderProtocolErrorRecord`。
    - 每条 record 携带 `idempotency_key`、`source_event_position`、`session_id`、`run_id`、`trace_type`、`recorded_at`。
  - `class ToolTraceJsonlSink`：
    - `__init__(*, root_path: Path)`：root_path = `DurableHarnessConfig.tool_trace_path`；首次写入时自动 `mkdir(parents=True, exist_ok=True)`。
    - `append_record(*, record: ToolTraceRecord) -> None`：选择 / 滚动当前 `sessions/<session_id>/tool_calls_<NNNNNN>.jsonl` 文件（按 ~10MB 阈值），写一行 JSON，**每行 flush + fsync**（用户决策）。
    - `write_raw_payload_blob(*, run_id, iteration_id, blob_id, payload_json: str) -> None`：先写 `<blob_id>.json.tmp`，fsync，`os.replace` 原子改名到 `raw_payloads/<run_id>_<iteration_id>/<blob_id>.json`，避免半文件。
    - 行级原子性：用 buffered open + `write` 单次系统调用 + fsync；在严格 OLD-不兼容前提下，行内字段顺序自由，按 NEW schema 设计。
  - 模块级私有 `_PROVIDER_SECRET_KEYS`（仅作用于 provider raw payload）+ `_scrub_provider_secret(payload: JsonValue) -> JsonValue`。
  - `compute_idempotency_key(*, schema_version, trace_type, run_id, iteration_id_or_empty, tool_call_id_or_empty, source_event_position, record_role) -> str`：sha256 模块级公共纯函数，作为 JSONL 行内 `idempotency_key` 字段值。

- **`dayu/host/_run_input_context_fact.py`**
  - `@dataclass class RunInputContextFactBuilder`：
    - `build(*, run_input, build_trace, current_user_event, tool_schemas, attempt_index, iteration_index, iteration_id) -> RunInputContextSnapshotBuiltData`。
    - 用 `RunInputBuildResult` / `RunInputBuildTrace` 直接产出 hot-layer summaries（excerpt 用 `_text.truncate_text`，token 估算用 `_token_estimator.estimate_text_tokens`）；并把完整 `model_input_messages` / `tool_schemas` 序列化为 JSON 字符串内联进 fact data 的 `raw_input_messages_json` / `raw_tool_schemas_json`。
    - blob_id 由 `sha256(run_id|iteration_id|"input")[:16]` 与 `sha256(run_id|iteration_id|"tools")[:16]` 派生（确定性，replay 友好）。
    - 不读 `LocalRunHarness.last_run_input_build_trace_by_run` 等 LRU。
  - 在 `_run_harness.py` 的 `_run_to_store` 路径，每次 `_build_run_input` 完成后、调度 Engine attempt 前：
    1. 在外层 `async with self.storage.transaction() as tx:` 中调用 builder。
    2. `event_store.append_in_transaction(tx, draft)` 追加 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` canonical fact（`RunEventSource.HOST`、`source_engine_event_id=None`）。
    3. 抛错则事务回滚，Engine attempt 不启动；harness 用现有 `host_failure_draft` 写入 `RUN_FAILED`。
    - retry / compact 路径每个 attempt 都跑这条流程，attempt_index 来自现有 `attempt_state_store`。
    - **没有 raw_payload 同事务写入步骤了**（raw payload 内联在 fact 自身），事务边界自然收敛到单条 `append_in_transaction`。
  - 仅当 `tool_trace_path` 非空时执行；为空时该路径 no-op，行为与 P6 完全一致。

- **`dayu/host/_tool_trace_projection.py`**
  - `@dataclass class ToolTraceObserver(ObserverSink)`：
    - `descriptor`：`observer_id="tool_trace"`、`projection_name="tool_trace_v2_host"`、`schema_version=1`、`required=False`。
    - `__init__(*, jsonl_sink: ToolTraceJsonlSink)`。
    - `process(tx, batch)`（**注意：tx 在 P7 不被使用，因为 sink 完全走文件系统；保留参数以满足 ObserverSink 协议**）：
      1. 遍历 envelope，按 `RunEventType` 派发为 `ToolTraceRecord`。
      2. `key = compute_idempotency_key(...)` → 写入 record 的 `idempotency_key` 字段。
      3. `jsonl_sink.append_record(record=record)` 实时写一行 + fsync。
      4. 对 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`：从 fact data 取出内联的 `raw_input_messages_json` / `raw_tool_schemas_json`，调用 `jsonl_sink.write_raw_payload_blob(...)` 写两个文件；JSONL 行内只写 hot-layer 摘要 + raw 文件相对路径。
      5. 对 `PROVIDER_PROTOCOL_ERROR`：`raw_payload`（来自 `ProviderProtocolErrorData.raw_payload`）经 `_scrub_provider_secret` 后写到 `raw_payloads/`。
    - 派发规则：
      - `TOOL_CALL_REQUESTED` + `TOOL_RESULT_ACCEPTED` → 同 batch 配对生成单条 `ToolCallRecord`。若 batch 内 `request` 无对应 `result`，observer 抛 `ProjectionSchemaError`（非 retryable），P6 协调器进入 `BLOCKED_FAILED`。
      - `TOOL_RESULT_TRUNCATED` / `TOOL_FETCH_MORE_*` / `TOOL_CURSOR_*` → 合并到同 batch 的 `ToolCallRecord`（保留 scope_token / cursor 全量）。
      - `RUNNER_USAGE_RECORDED` → `IterationUsageRecord`。
      - `FINAL_ANSWER` → `FinalResponseRecord`。
      - `PROVIDER_PROTOCOL_ERROR` → `ProviderProtocolErrorRecord`。
      - `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` → `IterationContextSnapshotRecord` + 拆 raw 文件。
    - **不维护进程内 dict / 不维护跨 batch pending state / 不写 SQLite 任何新表 / 不读 SQLite raw blob（raw 在 fact 内联）。**
    - **Crash 窗口语义**：JSONL 行写入 + fsync 完成后、`advance_success` 提交前发生 crash → replay 时 observer 会重新生成同一条 record（同 idempotency_key）并 append 到 JSONL，产生孤儿副本。analyzer / 测试按 `idempotency_key` 字段去重消化。窗口大小 = 单 batch 内已 append 的行数。

#### 测试（新增）

- **`tests/host/test_phase7_tool_trace_jsonl_sink.py`**
  - `test_jsonl_sink_writes_one_line_per_record`
  - `test_jsonl_sink_rolls_files_at_byte_threshold`
  - `test_jsonl_sink_fsync_called_per_line`
  - `test_jsonl_sink_raw_payload_uses_atomic_replace`
  - `test_provider_secret_scrub_only_strips_credentials`
  - `test_compute_idempotency_key_is_deterministic_and_collision_free`

- **`tests/host/test_phase7_run_input_context_fact.py`**
  - `test_context_fact_appended_to_eventlog_with_inline_raw_payloads`
  - `test_context_fact_rolled_back_when_eventlog_append_fails`
  - `test_context_fact_per_attempt_after_retry_compact`
  - `test_context_fact_skipped_when_tool_trace_path_is_none`
  - `test_iteration_context_snapshot_does_not_read_run_input_build_trace_lru`
  - `test_blob_id_is_deterministic_across_replays`

- **`tests/host/test_phase7_tool_trace_projection.py`**
  - `test_tool_call_projected_from_eventlog_requested_and_result_in_same_batch`
  - `test_tool_call_request_without_paired_result_blocks_projection`
  - `test_tool_call_projection_repeated_drain_yields_same_idempotency_key`
  - `test_replay_after_partial_drain_produces_orphan_lines_dedupable_by_key`
  - `test_iteration_usage_projected_from_runner_usage_recorded`
  - `test_final_response_projected_from_final_answer`
  - `test_provider_protocol_error_projected_with_bounded_payload`
  - `test_provider_protocol_error_raw_payload_missing_writes_omitted_reason`
  - `test_provider_protocol_error_scrubs_provider_secret_only`
  - `test_truncation_and_fetch_more_projection_preserves_scope_token_and_cursor`
  - `test_fetch_more_duplicate_or_wrong_scope_token_is_diagnosable`
  - `test_iteration_context_snapshot_from_host_owned_context_fact`
  - `test_iteration_context_snapshot_unpacks_inline_raw_to_files`
  - `test_observer_skipped_when_tool_trace_path_is_none`
  - `test_observer_does_not_touch_sqlite_beyond_required_protocol`

- **`tests/host/test_phase7_tool_trace_eventlog_source.py`**
  - `test_trace_does_not_use_engine_recorder_or_manual_store_write`
  - `test_host_import_boundary_engine_has_no_tool_trace_dependency`
  - `test_no_new_sqlite_tables_introduced_for_tool_trace`

#### 验证

```bash
source .venv/bin/activate
pytest tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase7_run_input_context_fact.py tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_eventlog_source.py -q
pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase6_durable_harness_integration.py -q
python -m pyright
```

S2 完成后向 user 汇报。

---

### 子阶段 S3 —— Smoke + Analyzer (NEW only) + README

目标：实跑 smoke 验证端到端 JSONL 输出形态；落地 NEW-only analyzer（**不读 OLD `tool_trace_v2`**）；更新文档。

#### 新增

- **`utils/analyze_tool_trace_host.py`**（独立脚本，**不读 OLD `tool_trace_v2`**）
  - 入参：`<tool_trace_path>`（即 `DurableHarnessConfig.tool_trace_path`）。
  - 递归读 `sessions/*/tool_calls_*.jsonl`，过滤 `trace_schema_version == "tool_trace_v2_host"`；遇 OLD `tool_trace_v2` 文件直接 ERROR 退出（明确语义边界）。
  - **行内 `idempotency_key` 去重**：同 key 多行只保留第一条（消化 crash 窗口的孤儿副本）。
  - 实现 NEW-only 业务无关诊断：重复工具调用、truncation→fetch_more 未续读、fetch_more `scope_token` / `cursor` 重复 / 错值、tool result / raw input bytes 分布、trace 完整性（按 source_event_position 连续性）、provider protocol error 计数、final response presence。
  - 不向 `utils/analyze_tool_trace.py` 引用、不复用其代码；OLD 业务无关诊断的"语义"是参考来源，"代码"全新写。
  - 命令：`python utils/analyze_tool_trace_host.py <tool_trace_path>`。

- **`utils/smoke_host_p7_tool_trace.py`**
  - 用 `DurableHarnessConfig(database_path=tmp.db, tool_trace_path=tmp_jsonl)` 构造 durable harness。
  - 注入 stub WorkerProxy，使其产出 1 次工具请求 + result（带 truncation）+ 1 次 fetch_more + final answer + 1 次 provider protocol error 的事件流。
  - 触发 `coordinator.drain()`；observer 实时写 JSONL（无独立 exporter）。
  - 只打印：`run_id`、`session_id`、observer status、JSONL 文件清单、records counts、tool call summary、fetch_more cursor fingerprint。
  - 不打印完整 prompt / tool result / scope token / raw cursor / provider secret。
  - 末尾自动调用 `analyze_tool_trace_host` 验证 analyzer 可读。

#### 测试（新增）

- **`tests/utils/test_analyze_tool_trace_host.py`**
  - `test_analyzer_dedupes_orphan_lines_by_idempotency_key`
  - `test_analyzer_rejects_old_tool_trace_v2_files`
  - `test_analyzer_detects_repeated_tool_calls`
  - `test_analyzer_detects_truncation_without_fetch_more_followup`
  - `test_analyzer_detects_wrong_scope_token_in_fetch_more`
  - `test_analyzer_counts_provider_protocol_errors`
  - `test_analyzer_reports_final_response_presence`
  - `test_analyzer_validates_trace_completeness_via_source_event_position`

#### 修改

- **`dayu/host/README.md`**：在"当前事实"章节追加 P7：trace 是 P6 projection 派生的实时 JSONL；`DurableHarnessConfig.tool_trace_path` 非空时装配 observer；JSONL 行内自带 `idempotency_key`；**P7 不引入任何新 SQLite 表**；`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 是 P6 EventLog 的事实补齐 patch（fact data 内联 raw payload）；schema 字面量 `tool_trace_v2_host`，**不向后兼容 OLD `tool_trace_v2`**。
- **`tests/README.md`**：在分层说明加入 P7 trace projection / analyzer 测试位置。
- **根 `README.md`**：替换 / 追加 tool trace 入口说明：`DurableHarnessConfig(database_path=..., tool_trace_path=...)`，smoke `utils/smoke_host_p7_tool_trace.py`，分析 `utils/analyze_tool_trace_host.py <tool_trace_path>`；明确说明 NEW schema 与 OLD 不兼容。
- **`docs/host/design.md`**：检查 P7 trace 章节同步事实（JSONL 是真源；SQLite 不增表；context fact 是 EventLog patch；observer 同步阻塞 terminal drain；每行 fsync）。
- **`docs/host/migration-plan.md`**：在 P6/P7 残余风险表追加：observer 同步 sink 阻塞 terminal completion（不阻塞 Engine 事件产生）；JSONL 与 checkpoint 非原子，靠行内 `idempotency_key` 去重消化 crash 窗口。

#### 验证

```bash
source .venv/bin/activate
pytest tests/utils/test_analyze_tool_trace_host.py -q
pytest tests/host/ -q          # 全 host 测试回归
python utils/smoke_host_p7_tool_trace.py
python utils/analyze_tool_trace_host.py <smoke 输出目录>
python -m pyright
```

S3 完成后给出 plan §25 要求的最终汇报：

- 改了什么（按文件分类）。
- OLD 五类 record 的继承 / 有意差异点。
- EventLog provenance 链路。
- Trace payload 边界（provider secret scrub 范围、热/冷分层）。
- async/sync observer 判断（默认保持同步，证据：所有 sink 写入都在 `HostStorageTransaction` 同事务内，无外部 IO）。
- 验证结果。
- README 触发判断结果。
- 残余风险（P8 owner fencing、P15 audit hard-gate、partial tool calls 完整语义）。

---

## 关键复用点（避免重新发明）

- `dayu/host/_event_observer.py:75-105` —— `ObserverSink` 协议；`ToolTraceObserver` 直接实现。
- `dayu/host/_event_observer.py:228-264` —— sink/checkpoint 同事务模板，trace observer 不另起事务。
- `dayu/host/_durable_event_store.py:223-307` —— 现有 `_append_in_transaction` 是同事务 fact 写入的真源；S1 暴露 thin 公共包装。
- `dayu/host/_run_input_builder.py:101-128` —— `RunInputBuildResult` / `RunInputBuildTrace` 直接喂给 context fact builder，禁止经 LRU 兜兜转转。
- `dayu/host/_text.truncate_text`、`dayu/host/_token_estimator.estimate_text_tokens` —— excerpt / token 估算复用，避免在 trace 模块再实现一份。
- `dayu/host/_run_event_serializer.py:1238-1270` —— `_DATA_CLASS_BY_TYPE` 是注册表真源，禁止在 trace 模块自建第二份 type ↔ data 映射。
- `dayu/host/_host_storage_transaction.HostStorage.transaction()` —— 唯一外层事务入口；harness context fact 路径必须用它包住 `write_raw_payload` + `append_in_transaction`。

---

## 关键文件路径汇总

新增：
- `dayu/host/_tool_trace_jsonl_sink.py`（含 `ToolTraceIdempotencyIndex` + `ToolTraceJsonlSink` + record dataclass + 公共 helpers）
- `dayu/host/_tool_trace_projection.py`
- `dayu/host/_run_input_context_fact.py`
- `utils/smoke_host_p7_tool_trace.py`
- `utils/analyze_tool_trace_host.py`
- `tests/host/test_phase7_contract_serializer.py`
- `tests/host/test_phase7_schema_bootstrap.py`
- `tests/host/test_phase7_durable_harness_config.py`
- `tests/host/test_phase7_tool_trace_jsonl_sink.py`
- `tests/host/test_phase7_run_input_context_fact.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase7_tool_trace_eventlog_source.py`
- `tests/utils/test_analyze_tool_trace_host.py`

修改：
- `dayu/host/contracts.py`（新 RunEventType + dataclass，含内联 raw payload 字段）
- `dayu/host/_run_event_serializer.py`（注册 + 编解码分支）
- `dayu/host/_durable_event_store.py`（仅暴露 `append_in_transaction` thin 公共包装；**不新增任何表**）
- `dayu/host/_durable_harness.py`（`DurableHarnessConfig` + `tool_trace_path` 装配开关）
- `dayu/host/_run_harness.py`（每次 attempt 同事务追加 context fact）
- `dayu/host/README.md`、`tests/README.md`、根 `README.md`、`docs/host/design.md`、`docs/host/migration-plan.md`

不修改 / 不新增：
- `dayu/engine/**`（plan §6 硬约束）
- `dayu/contracts/protocols.py`
- `dayu/host/__init__.py` 默认导出
- OLD `utils/analyze_tool_trace.py`（保持原样，与 P7 完全无关）
- ~~`dayu/host/_tool_trace_exporter.py`~~（取消）
- ~~`dayu/host/_tool_trace_store.py`~~（取消）
- ~~SQLite `host_tool_trace_*` 任何表~~（取消，0 张新表）

---

## 验证总览

每个子阶段独立通过：

1. 对应子阶段新增 / 改动测试 + P6 全量回归。
2. `python -m pyright` 无新增 / 扩散错误。
3. README 仅在变更属于该 README 职责时同步。
4. S3 末尾：smoke 实跑 + analyzer 实跑 + plan §25 汇报。

整体 P7 完成的硬验收信号：

- 所有 trace 记录可追溯到 durable EventLog 的 `run_id` / `session_id` / per-run cursor / global event position（行内字段 `source_event_position`）。
- 测试证明 trace 来自 canonical EventLog facts，不是 Engine 私有 recorder 或手动写 trace。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 内联 raw payload，单条 `append_in_transaction` 提交；append 失败回滚，Engine attempt 不启动。
- **P7 不新增任何 SQLite 表**，trace 完全走文件系统。
- JSONL 行内 `idempotency_key` 是去重真源；analyzer 测试证明孤儿副本被去重。
- analyzer 仅读 `tool_trace_v2_host`；遇 OLD `tool_trace_v2` 文件 ERROR 退出（边界明确）。
- provider secret 不入 trace；scope_token / cursor / prompt / 大 tool result 按 NEW schema 完整保留。
- `tool_trace_path=None` / 空字符串时，trace observer 不装配、JSONL 目录不创建、Host 行为与 P6 完全一致。
- Sink 同步阻塞性已记录：`coordinator.drain()` 在 `_project_terminal_run` 同步 await，sink 慢拖慢单 run terminal 完成；Engine 事件产生不被阻塞。每行 fsync 由用户决策固定。
