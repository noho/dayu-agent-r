# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Code Review Re-Review

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A / S1`
- Gate: S1 code review re-review after accepted fix
- Time: `2026-07-12T14:36:08+0800`（本机系统时钟）
- Branch: `phaseflow/host-issues-control`
- Baseline: control-doc plan acceptance `41bd6ca9`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-rereview-mimo.md`

## Scope

- Review only whether the three accepted code-review findings (Codex-F1, Codex-F2, Codex-F3) are fixed.
- Do not modify code, tests, docs, control doc, commit, push, PR, or enter next gate.
- Primary inputs: controller adjudication, fix report, controller fix validation, original failing review, plan, design source.

## Findings

### Codex-F1: strict compact path must fail closed on accepted result payload corruption

- **入口/函数**: `_accepted_tool_evidence_delta_blocks()` → `event_payload_object()` → `project_accepted_tool_result(resolved_payload=...)`
- **文件(行号)**: `dayu/host/compact_material.py:2556-2565`；`dayu/host/accepted_result_projection.py:269-270`
- **验证路径**: `_accepted_tool_evidence_delta_blocks()` 先调用 `event_payload_object()` 解析 accepted result payload；descriptor digest/size、SQLite row digest/size/content、artifact containment/bytes 或 canonical JSON 损坏时，shared integrity owner 抛出 `HostDurableError`。该异常在 `event_payload_object()` 层抛出，**不进入** `project_accepted_tool_result()` 的 lenient `_result_event_payload()` 降级路径。
- **`project_accepted_tool_result()` 确认**: `resolved_payload` 参数非 `None` 时，`_result_event_payload()` 直接返回已校验 payload（`accepted_result_projection.py:269-270`），不捕获 `HostDurableError`。
- **测试覆盖**: `tests/host/test_compact_material.py` 的 `_CompactEvidencePayloadTamperKind` 枚举覆盖 `DESCRIPTOR_DIGEST`、`DESCRIPTOR_SIZE`、`ROW_DIGEST`、`ROW_SIZE`、`ROW_CONTENT`、`ARTIFACT_CONTAINMENT`、`ARTIFACT_BYTES`、`CANONICAL_BYTES` 八类篡改；`test_pre_dispatch_evidence_durable_payload_tamper_fails_closed()` 断言 material 构造抛 `HostDurableError`。另有 `test_pre_dispatch_evidence_missing_request_atom_fails_closed()`、`test_pre_dispatch_evidence_request_ref_to_result_event_fails_closed()`、`test_pre_dispatch_evidence_request_identity_mismatch_fails_closed()`、`test_pre_dispatch_evidence_payload_damage_fails_closed()`、`test_pre_dispatch_payload_damage_fails_closed_without_recovery_request()` 覆盖 request provenance 与 raw evidence 边界。
- **兼容 fallback 检查**: `AcceptedToolResultProjection` 的 lenient `_result_event_payload()` catch `HostDurableError` 降级路径（`accepted_result_projection.py:280-281`）仅在 `resolved_payload is None`（即 read/display 路径）时生效。compact strict path 已通过预解析绕过该降级。
- **结论**: Codex-F1 已修复。durable corruption 在 compact material 构造时 fail closed，不会被 lenient projection 降级为 missing evidence。

### Codex-F2: full runner-call manifest semantic graph must be owned and validated by `_runner_call_manifest`

- **入口/函数**: `parse_runner_call_manifest()` → `_validate_manifest_fields()` / `_parse_manifest_identity()` / `_parse_manifest_message_entries()` / `_parse_manifest_projector_metadata()` / `_validate_manifest_graph()` / `_validate_manifest_hot_identity()`
- **文件(行号)**: `dayu/host/_runner_call_manifest.py:691-746,749-783,785-840,884-949,952-1010,1131-1205,1208-1281`
- **验证路径**:
  - **Schema & fields**: `_validate_manifest_fields()` 校验 required fields、unknown fields、projection descriptor trio 聚散。
  - **Identity & closed enums**: `_parse_manifest_identity()` 校验 `schema_version`、`runner_call_kind`、`runner_call_trigger_reason` closed enum，`attempt_id/execution_id` 和 `iteration_id/iteration_index` 必须成对。
  - **Message entries**: `_parse_manifest_message_entries()` 校验 exact fields、role closed enum、projection ref/digest pairing。
  - **Projector metadata**: `_parse_manifest_projector_metadata()` 校验 exact fields、`projector_id` closed enum、`purpose` closed enum、id 唯一性。
  - **Graph closure**: `_validate_manifest_graph()` 校验 `message_count` 匹配 `len(entries)`、contiguous indexes、role sequence digest、每个 message 的 `projector_metadata_id` 引用闭合到 manifest metadata、compactor identity 一致性。
  - **Hot/manifest identity**: `_validate_manifest_hot_identity()` 校验 identity fields、validation_status、message_count、role_sequence_digest、input_projection_digest、projection descriptor、manifest_digest 全部一致。
- **Engine continuation**: `run_input.py`、`engine_ingest.py`、`compaction_operation.py` 在 append 前调用同一 owner 校验完整 manifest。
- **Tool Trace**: `durable/tool_trace.py:1033-1038` 通过 `parse_runner_call_manifest()` 获取 typed validated manifest；`_projector_metadata_summary_from_manifest()` 只从 typed manifest 投影 summary（`durable/tool_trace.py:1042-1061`）。旧 metadata-item-only 成功路径已删除。
- **测试覆盖**: `tests/host/test_tool_trace_queries.py` 使用真实 `DurableRunnerCallManifestRecorder` 产物构造成功 fixture。`_ManifestTamperKind` 枚举覆盖 `INCOMPLETE`、`DANGLING_METADATA_ID`、`UNKNOWN_PROJECTOR_ID`、`UNKNOWN_PURPOSE`、`UNKNOWN_SCHEMA_VERSION`、`HOT_IDENTITY_MISMATCH` 六类篡改；`test_runner_call_manifest_graph_validation_fails_closed()` 断言 `HostDurableError`。
- **兼容 fallback 检查**: 无 metadata-only manifest 成功 fixture。无旧 schema fallback。
- **结论**: Codex-F2 已修复。full manifest semantic graph 由 `_runner_call_manifest` 唯一 owning、parsing 和 validating。Tool Trace 只消费 typed validated manifest。

### Codex-F3: shared hot payload parser must require explicit diagnostic and reject malformed

- **入口/函数**: `parse_runner_call_hot_payload()` → `runner_call_hot_diagnostic_from_json()` → `_validate_hot_atoms()` → `_validate_diagnostic()`
- **文件(行号)**: `dayu/host/_runner_call_manifest.py:578-643,490-518,1284-1399,1402-1439`
- **验证路径**:
  - **Exact fields**: `_require_exact_fields()` 拒绝未知字段、缺失字段。
  - **Diagnostic required**: `parse_runner_call_hot_payload()` 要求 `diagnostic` 必须是 `Mapping`（`:597-598`）。
  - **Diagnostic shape**: `runner_call_hot_diagnostic_from_json()` 校验 exact diagnostic fields。
  - **Cross-field validation**: `_validate_hot_atoms()` 校验 `diagnostic.status == validation_status`（`:1372-1373`）；complete 时 `observed_count == expected_count == message_count` 且 `observed_digest == expected_digest == role_sequence_digest`（`:1374-1388`）。
  - **Diagnostic internal**: `_validate_diagnostic()` 校验 status closed enum、consumer_boundary 非空、complete 时 reason/missing_* 字段必须为 `None`（`:1427-1439`）。
- **Consumer alignment**: `tool_trace._runner_call_diagnostic()` 和 `engine_ingest._runner_call_payload_diagnostic()` 均通过 `parse_runner_call_hot_payload()` 获取 typed atoms，然后投影 `diagnostic` 字段。不从 sibling scalars 合成 complete diagnostic。
- **Design doc alignment**: `design.md:2676` 明确要求 complete hot diagnostic 必须显式，不得为 `null`。`design.md:1719` 中的 diagnostic 表格要求 `always explicit`。manifest body 的 `diagnostic=null` 仅适用于 complete manifest body（`_parse_manifest_diagnostic()` `:1064-1065`），hot payload 始终携带显式 diagnostic。
- **测试覆盖**: `tests/host/test_runner_call_hot_payload_contract.py` 的 `_HotPayloadTamperKind` 枚举覆盖 `MISSING_DIAGNOSTIC`、`NULL_DIAGNOSTIC`、`MALFORMED_DIAGNOSTIC`、`LEGACY_METADATA_ARRAY`、`STATUS_MISMATCH`、`COUNT_MISMATCH`、`DIGEST_MISMATCH` 七类篡改；`test_runner_call_hot_payload_tamper_fails_closed()` 断言 `HostDurableError`。Engine ingest 的 `_EngineHotTamperKind` 同类矩阵在 `test_engine_ingest_mapping.py` 中覆盖。
- **兼容 fallback 检查**: `diagnostic=None` 在测试中的出现仅为 complete manifest body shape（`test_tool_trace_queries.py:335`），由 `_hot_payload_for_manifest()` 将其转换为显式 `complete_runner_call_hot_diagnostic()`（`:458-465`）。无 complete hot payload success fixture 使用 `diagnostic=None`。无旧 `projector_metadata_summary` 数组成功 fixture。
- **结论**: Codex-F3 已修复。shared hot parser 要求显式 diagnostic，complete 时交叉校验 status/count/digest。消费者不再合成 complete diagnostic。

## Open Questions

- 无。

## Residual Risk

- stress suite 存在一次 active-cancel 传播时序波动，已被 controller 确认为既有 S4 scheduler stress timing residual，不与本次 semantic owner 改动同源。
- fresh-schema contract 会对旧 hot row、metadata-only manifest 或不闭合 graph fail closed。这是 gate 明确要求的行为，不提供兼容 shim；历史数据需由独立 deployment preflight 处理。
- S2-S8 lifecycle/admin/scheduler 行为不在本次 re-review scope。

## Conclusion

`PASS`：三项 accepted findings（Codex-F1、Codex-F2、Codex-F3）均已直接在 owner 边界修复，无兼容 fallback 或下游 repair 引入。测试断言 owner-level fail-closed 行为，不保留旧 broken behavior。docs/README 变更仅反映已实现的 S1 contract。未发现新 material regression。
