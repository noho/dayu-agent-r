# Code Review — WU-OBS-P00 Slice 4

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice4-code-review-ds.md`
- Review date: 2026-06-05
- Included scope: `dayu/host/tool_trace.py`, `dayu/host/durable/tool_trace.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_tool_trace_queries.py`, `dayu/host/README.md`, `tests/README.md`
- Excluded scope: `docs/reviews/wu-dur-obs-cm-closeout-slice4-implementation-codex.md`（implementation artifact 本身不 review，只读入作为上下文参考）；`docs/host/design.md`（per Slice 4 non-goal，未编辑也不 review）；`docs/host/issues-implementation-control.md`（仅参考 WU-DUR-P01-S2-R1 状态）
- Parallel review coverage: 无 — 本次 review scope 集中在一个 subsystem（Tool Trace），由单一 reviewer 主链路走读

## Findings

未发现实质性问题。

## 逐条 Review Point 裁决

### 1. RUNNER_CALL_INPUT_ASSEMBLED 投影

**状态：pass**

证据：

- `_runner_call_trace_summary()` (`dayu/host/tool_trace.py:586–616`) 正确复制 `runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`、`iteration_id`、`manifest_ref`、`manifest_digest`、`message_count`、`role_sequence_digest`、`input_projection_digest`、`projector_metadata_summary` 与 typed `diagnostic`。
- `_extract_runner_call_trace()` (`dayu/host/tool_trace.py:555–583`) 将 `manifest_digest` 放入 `result_digest`，`manifest_ref` 放入 `payload_ref`/`diagnostic_ref`，与 Tool Trace 现有字段语义一致。
- `_runner_call_projector_metadata_summary()` (`dayu/host/tool_trace.py:690–729`) 裁剪 projector metadata 只保留 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose` 五个字段，不内联完整 manifest body。
- Read-model 侧 `_runner_call_signal_from_hot_row()` (`dayu/host/durable/tool_trace.py:644–696`) 正确从 hot row trace_summary 重建 typed `RunnerCallReconstructionSignal`。
- 测试 `test_tool_trace_projects_runner_call_manifest_signal` 逐字段验证 complete signal 所有字段正确投影。

### 2. 非 complete runner-call signal 缺 typed diagnostic fail closed

**状态：pass**

证据：

- `_runner_call_diagnostic()` (`dayu/host/tool_trace.py:649–650`)：当 `status is not COMPLETE` 且 `diagnostic is not Mapping` 时抛出 `HostDurableError("runner-call diagnostic must be object")`。
- 测试 `test_tool_trace_rejects_non_complete_runner_call_without_diagnostic` (`tests/host/test_tool_trace_projection.py:609–652`) 以 `validation_status="limited_signal"` + `diagnostic=None` 触发 fail-closed，断言 `HostDurableError` 且 match `"runner-call diagnostic"`。
- 该 failure 会被 `ProjectionRunner` 记录到 `host_projection_failures`，event sequence checkpoint 不推进，重试时重新 fail — 符合 fail-closed 不静默丢失语义。

### 3. Diagnostic enum 校验封闭

**状态：pass**

证据（投影侧）：

- `_runner_call_status()` (`dayu/host/tool_trace.py:732–746`)：通过 `RunnerCallReconstructionStatus(value)` 构造，非法值由 `StrEnum.__new__` 抛 `ValueError`，统一转为 `HostDurableError`。
- `_runner_call_reason()` (`dayu/host/tool_trace.py:749–763`)：同模式。
- `_optional_runner_call_missing_atom_kind()` (`dayu/host/tool_trace.py:766–783`)：同模式。
- `_optional_runner_call_missing_ref_kind()` (`dayu/host/tool_trace.py:786–806`)：同模式，且先做 producer-boundary 归一化。

证据（查询侧）：

- `_runner_call_status_from_text()` (`dayu/host/durable/tool_trace.py:853–867`)
- `_runner_call_consumer_boundary_from_text()` (`dayu/host/durable/tool_trace.py:870–884`)
- `_optional_runner_call_reason_from_text()` (`dayu/host/durable/tool_trace.py:887–905`)
- `_optional_runner_call_missing_atom_kind_from_text()` (`dayu/host/durable/tool_trace.py:908–925`)
- `_optional_runner_call_missing_ref_kind_from_text()` (`dayu/host/durable/tool_trace.py:929–947`)

所有 enum 均为 `StrEnum`，5 个校验函数均通过 try/except ValueError 转 `HostDurableError`，不存在字符串 passthrough 路径。

### 4. Query helper `read_runner_call_reconstruction_signals_by_run`

**状态：pass**

证据：

- `read_runner_call_reconstruction_signals_by_run()` (`dayu/host/durable/tool_trace.py:544–572`)：只通过 `_query_page()` 查询 `host_tool_trace_hot` 表，WHERE 条件 `run_id = ? AND event_type = 'RUNNER_CALL_INPUT_ASSEMBLED'`，不读取 EventLog payload body、manifest body 或任何 Engine/Host 状态表。
- 返回 typed `RunnerCallReconstructionSignalPage`，每个 signal 含 typed `RunnerCallReconstructionDiagnostic`。
- 分页使用 `event_sequence ASC` + `limit + 1` fetch 判断 `has_more` (`dayu/host/durable/tool_trace.py:595–641`)。
- 测试 `test_runner_call_reconstruction_signal_query_classifies_statuses` 覆盖 complete / limited_signal / mismatch 三类 signal 的完整 round-trip：从 EventLog append -> Tool Trace projection -> query helper -> typed enum 断言。

### 5. Producer-boundary missing ref kind 归一化

**状态：pass**

证据：

- `_optional_runner_call_missing_ref_kind()` (`dayu/host/tool_trace.py:800–802`)：对 producer 标签 `"runner_call_projection_artifact"` 归一为 `RunnerCallReconstructionMissingRefKind.ARTIFACT_REF.value`（即 `"artifact_ref"`）。
- 测试 `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` 中 diagnostic 输入 `missing_ref_kind: "runner_call_projection_artifact"`（`tests/host/test_tool_trace_projection.py:549`），投影后断言 `"artifact_ref"`（line 598）。
- 查询侧测试 `test_runner_call_reconstruction_signal_query_classifies_statuses` 断言 `limited.diagnostic.missing_ref_kind is RunnerCallReconstructionMissingRefKind.ARTIFACT_REF`（line 398）。
- Tool Trace query contract 不会泄漏内部 producer 标签给 LLM-facing consumer（Tool Trace 查询结果只暴露稳定 enum 值）。

### 6. Tests 覆盖

**状态：pass**

运行结果：`pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` — 15 passed。

覆盖矩阵：

| 测试 | 覆盖场景 |
|---|---|
| `test_tool_call_chain_projects_hot_rows_and_cold_lines` | 完整 tool call chain 投影 + cold JSONL 字段验证 |
| `test_tool_trace_does_not_inline_large_tool_call_arguments` | 大参数不展开进 cold JSONL |
| `test_tool_trace_projects_runner_call_manifest_signal` | complete signal 全字段投影 |
| `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` | limited_signal + ref kind 归一 + consumer_boundary 收敛 |
| `test_tool_trace_rejects_non_complete_runner_call_without_diagnostic` | fail-closed 缺 diagnostic |
| `test_tool_trace_projects_mismatch_runner_call_diagnostic` | mismatch + observed/expected count/digest |
| `test_tool_trace_projection_includes_client_correlation_id` | hot/cold 均暴露 correlation |
| `test_tool_trace_projection_rejects_non_text_client_correlation_id` | 类型校验 fail-closed |
| `test_cold_writer_failure_records_projection_failure_without_checkpoint` | cold 写失败 checkpoint 不推进 |
| `test_projection_rebuild_from_event_log_restores_hot_rows` | rebuild 恢复 hot rows |
| `test_cold_jsonl_source_key_digest_conflict_records_failure_without_hot_row` | source key 冲突 detection |
| `test_default_tool_trace_path_is_derived_from_artifact_root` | 默认路径派生 |
| `test_query_helpers_return_rows_ordered_by_event_sequence` | 四个 query helper 分页 + 排序 |
| `test_provider_request_id_terminal_diagnostic_query` | provider request id 关联 terminal + protocol diagnostic |
| `test_runner_call_reconstruction_signal_query_classifies_statuses` | complete / limited_signal / mismatch typed query |

pyright: `0 errors, 0 warnings, 0 informations`。

### 7. README 更新

**状态：pass**

- `dayu/host/README.md`（line 202）：新增 RunInputBuilder `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact 描述与 manifest 契约说明，描述当前行为，不含未来计划。
- `tests/README.md`（line 129）：更新 Host 测试覆盖描述，新增 "runner-call manifest read-model signal"、"non-complete typed diagnostic fail closed"、"mismatch diagnostic" 和 "按 Run 查询 complete/limited_signal/mismatch typed reconstruction signal" — 均为当前已存在测试行为。
- 根 `README.md` 和 `dayu/README.md` 未更新，理由合理：无 CLI/config entry 或 layer relationship 变化。
- `docs/host/design.md` 未编辑，per Slice 4 non-goal。

## WU-DUR-P01-S2-R1 关闭状态

**状态：已关闭**

控制文档 `docs/host/issues-implementation-control.md:251` 记录 WU-DUR-P01-S2-R1 为 `deferred-with-owner`，destination 为 `WU-OBS-P00 / Slice 4 Tool Trace signal hardening`，要求 "Add direct test for Tool Trace fail-closed behavior when a non-complete runner-call diagnostic payload lacks a diagnostic object."

实现提供了：
- `dayu/host/tool_trace.py:649–650`：非 complete signal 缺 diagnostic object 时 `raise HostDurableError`
- `tests/host/test_tool_trace_projection.py:609–652`：`test_tool_trace_rejects_non_complete_runner_call_without_diagnostic` 直接验证该 fail-closed 行为

WU-DUR-P01-S2-R1 可在控制文档中标记为 closed。

## Tool Trace 边界验证

逐条确认 Tool Trace 不作为 EventLog / recovery / memory / dispatch / Run 状态真源：

1. **模块级声明显式**：`dayu/host/tool_trace.py:3–6` 与 `dayu/host/durable/tool_trace.py:3–7` 均声明 Tool Trace 是 committed EventLog 的派生 projection，不参与恢复/resume/memory/Run 状态迁移。
2. **Import 边界干净**：`tool_trace.py` 不 import recovery、memory、dispatch、Run state machine 模块。`durable/tool_trace.py` 只 import `_validation`、`codec`、`errors`、`schema`、`transaction` — 均为 durable foundation 层。
3. **只读路径**：所有 query helper（`read_runner_call_reconstruction_signals_by_run`、`read_tool_trace_by_run` 等）只执行 SELECT，不写任何表。
4. **写入路径隔离**：`ToolTraceProjectionConsumer.apply_event()` 只写 `host_tool_trace_hot` 表与 cold JSONL 文件，不写 EventLog、Run、Attempt、dispatch、memory snapshot 表。
5. **ProjectionRunner 契约约束**：Tool Trace consumer 通过 `ProjectionRunner` 注册，由 projection framework 管理 catch-up / checkpoint，不直接参与 command 路径或 state transition。

## Hot/Cold Trace 内容边界验证

1. **不内联长 prompt**：`_runner_call_trace_summary()` 只存 `manifest_ref`/`manifest_digest`，不存 message content。
2. **不内联完整 messages**：`_build_cold_line()` 只存 digests、refs、summary — 无 message text 字段。
3. **不内联 provider raw payload**：`_extract_canonical_trace()` 从 payload 抽取 bounded digest/ref 字段，不拷贝 `raw_result` 等非结构化内容（测试 `test_tool_call_chain_projects_hot_rows_and_cold_lines:376` 断言 `"raw_result" not in cold line`）。
4. **不内联完整 tool results**：Tool Trace 只存 `outcome_digest`、`payload_ref`、`payload_digest`。
5. **不内联 manifest body**：`_runner_call_projector_metadata_summary()` 只裁剪到 5 个 bounded 字段。
6. **不内联大参数**：`test_tool_trace_does_not_inline_large_tool_call_arguments` 验证 1024 字符参数不进入 cold JSONL。

## Residual Risk

- analyzer fixture / WU-OBS-00 实际消费该 query contract 时，可能发现 signal field 粒度不足（例如需要更细粒度的 projector 版本差异信息）；这是 WU-OBS-00 的 scope，当前 Slice 4 的 contract surface 按 plan 提供。
- `_runner_call_diagnostic_from_trace()` 对 "complete signal 带 reason" 的 fail-closed（durable/tool_trace.py:766）虽然没有独立测试，但受 triple-layer 防护：producer 写入正确值 -> projection 对 complete 直接 return -> query 侧校验作为最后防线。不构成当前风险。
- cold JSONL `_jsonl_contains_line()` 对 corrupted 行按 skip 处理（return None），在极端磁盘损坏场景下可能让实际存在冲突的行被重写；但 cold JSONL 是 append-only diagnostic artifact，且 hot row dedup 由 SQLite unique constraint 独立保护，不会导致 hot truth 不一致。
- 项目级 pyright 全量检查（`dayu/` + `tests/` + `utils/`）未在本次 review 中重新运行；但受影响的 `dayu/host/tool_trace.py` 与 `dayu/host/durable/tool_trace.py` 及其测试文件的 pyright 结果已确认 0 errors。

## Verdict

**pass**

## Ready for Controller Adjudication

yes
