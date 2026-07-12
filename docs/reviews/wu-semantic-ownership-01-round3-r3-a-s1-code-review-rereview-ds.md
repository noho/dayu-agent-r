# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Code Review Re-Review

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A / S1`
- Gate: S1 code review re-review after accepted fix
- Time: `2026-07-12T14:35:43+0800`
- Branch: `phaseflow/host-issues-control`
- Primary inputs:
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-controller-adjudication.md`
  - Fix report: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-fix-codex.md`
  - Controller fix validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-fix-controller-validation.md`
  - Original failing review: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-codex.md`
- Artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-rereview-ds.md`

## Scope

- Accepted findings under review: Codex-F1 (high), Codex-F2 (medium), Codex-F3 (medium)
- Method: direct code-path inspection of owner modules, consumer paths, tests, and docs; not report-only
- Excluded: S2-S8 behavior, schema DDL/migration, commit/push/PR

## Findings

### Codex-F1：已修复

**入口/函数**: `_accepted_tool_evidence_delta_blocks()` → `event_payload_object()` → `project_accepted_tool_result()`

**直接证据**:

1. `dayu/host/compact_material.py:2556-2560` — compact strict consumer 现在先调用 `event_payload_object(transaction, row, ...)` 完整解析 accepted result payload，再把已验证 object 作为 `resolved_payload` 传给 `project_accepted_tool_result()`。`event_payload_object()` 由 shared durable integrity resolver 拥有，descriptor digest/size、SQLite row digest/size/content、artifact containment/bytes 损坏均抛出 `HostDurableError`，该异常在 `_accepted_tool_evidence_delta_blocks()` 内未被捕获，直接向上传播。

2. `dayu/host/accepted_result_projection.py:170-174,269-270` — `project_accepted_tool_result()` 新增 `resolved_payload` 可选参数。当 `resolved_payload is not None` 时，`_result_event_payload()` 直接返回该已验证 object（行 269-270），完全绕过原有的 try/except `HostDurableError` → `{}` lenient 降级路径（行 271-281）。lenient 路径仅保留给不传 `resolved_payload` 的 read/display 消费者。

3. `tests/host/test_compact_material.py:154-164` — 定义 `_CompactEvidencePayloadTamperKind` 枚举覆盖 8 种篡改分类：`DESCRIPTOR_DIGEST`、`DESCRIPTOR_SIZE`、`SQLITE_ROW_DIGEST`、`SQLITE_ROW_SIZE`、`SQLITE_CONTENT`、`SQLITE_NONCANONICAL`、`ARTIFACT_CONTAINMENT`、`ARTIFACT_BYTES`。

4. `tests/host/test_compact_material.py:1868-1915` — `test_pre_dispatch_evidence_durable_payload_tamper_fails_closed` 对全部 8 种篡改参数化，断言 `build_pre_dispatch_compact_material_view()` 抛出 `HostDurableError`，不产生 material block。

5. `tests/host/test_compact_material.py:3087-3179` — `_tamper_compact_evidence_payload()` 对每种篡改分类执行对应的 SQLite/文件系统级篡改（digest 覆盖、size 偏移、content 替换、non-canonical JSON 注入、artifact 路径逃逸、artifact bytes 覆盖），确保测试在真实 durable integrity atom 层面验证 fail-closed。

**验证结论**: 修复完全符合 adjudication 要求。compact strict consumer 在 lenient projection 前先经 shared integrity owner 校验，损坏不可降级为缺失 evidence；测试覆盖全部 integrity atom 篡改面；无兼容 fallback。

### Codex-F2：已修复

**入口/函数**: `dayu.host._runner_call_manifest.parse_runner_call_manifest()` → Tool Trace `_projector_metadata_summary_from_manifest()` / Engine continuation `_limited_runner_call_manifest_body()`

**直接证据**:

1. `dayu/host/_runner_call_manifest.py:691-746` — `parse_runner_call_manifest()` 新增为 typed full-manifest parser/validator，校验：
   - 顶层字段集合（`_validate_manifest_fields`，行 749-782）；
   - manifest schema version 与 runner-input serializer schema version（行 707-716）；
   - identity closed enum：`runner_call_kind`（5 值）、`runner_call_trigger_reason`（12 值）（行 795-812）；
   - `attempt_id/execution_id` pair、`iteration_id/iteration_index` pair（行 813-823）；
   - message entries 字段集、role closed enum（4 值）、projection ref/digest pair（行 884-949）；
   - projector metadata 六字段 exact contract、`projector_id` closed enum（11 值）、`purpose` closed enum（7 值）、metadata id 唯一性（行 952-1010）；
   - 完整语义图：`message_count` vs entries 长度、连续 indexes、role sequence digest 自洽、message `projector_metadata_id` 引用闭合、compactor identity 与 kind 一致性、compactor parent identity 与 attempt/index 一致性、non-complete diagnostic count/digest 与 manifest 一致（`_validate_manifest_graph`，行 1131-1205）；
   - hot/manifest identity 全字段逐项比对（`_validate_manifest_hot_identity`，行 1208-1281）。

2. `dayu/host/_runner_call_manifest.py:521-536` — `runner_call_hot_payload()` 在构造 hot payload 前同时调用 `_validate_hot_atoms()` 和 `parse_runner_call_manifest()`，确保所有 producer adapter 写入前都经过完整 manifest 校验。

3. `dayu/host/engine_ingest.py:5744-5787` — Engine continuation 的 `_limited_runner_call_projector_metadata()` 现在通过 `runner_call_projector_metadata_descriptor()` 构造六字段 metadata（行 5765-5774），其中 `projector_id` 固定为 closed enum 值 `"engine_observed_runner_input_signal"`（行 5754），`purpose` 为 `_RUNNER_CALL_PROJECTOR_PURPOSE_TOOL_CONTINUATION`。`_limited_runner_call_projector_metadata_id()` 返回 `projector:{iteration_index}:engine-observed`（行 5787），与 message entries 的 `projector_metadata_id` 使用同一公式，引用闭合。

4. `dayu/host/durable/tool_trace.py:1016-1038` — `_validate_runner_call_contract()` 先通过 `parse_runner_call_hot_payload()` 解析 hot payload，再通过 shared durable resolver 读取 manifest bytes，最后调用 `parse_runner_call_manifest()` 做完整 graph 校验。行 1033-1038 返回 `_ValidatedRunnerCallContract` 同时持有 typed hot_payload 和 typed manifest。

5. `dayu/host/durable/tool_trace.py:1042-1061` — `_projector_metadata_summary_from_manifest()` 签名为 `(manifest: RunnerCallInputManifest) -> tuple[ProjectorMetadataSummary, ...]`，只从 typed validated manifest 投影 metadata summary，不再接受 raw JSON 或 metadata item-only 输入。

6. `tests/host/test_tool_trace_queries.py:103-111` — 定义 `_ManifestTamperKind` 枚举覆盖 6 种 full-graph 篡改分类：`INCOMPLETE`、`DANGLING_METADATA_ID`、`UNKNOWN_PROJECTOR_ID`、`UNKNOWN_PURPOSE`、`UNKNOWN_SCHEMA_VERSION`、`HOT_IDENTITY_MISMATCH`。

7. `tests/host/test_tool_trace_queries.py:1364-1448` — `test_runner_call_query_rejects_invalid_full_manifest_graph` 对全部 6 种篡改参数化，构造真实 producer manifest 后针对性破坏，断言 `read_runner_call_reconstruction_signals_by_run()` 抛出 `HostDurableError`。

8. `tests/host/test_tool_trace_queries.py:1302,1352` — 大规模成功测试（300 messages）的 `projector_metadata_summary` 字段从 typed `RunnerCallReconstructionSignal` 读取（这是 output projection type 的字段名，不是 hot payload 字段）。

9. `tests/host/test_engine_ingest_mapping.py` — 确认 continuation message metadata ref 在 manifest 内闭合。

**验证结论**: 修复完全符合 adjudication 要求。manifest 完整语义图由 single owner `_runner_call_manifest` 校验；Tool Trace 只从 typed validated manifest 投影；Engine continuation message metadata ref 闭合；测试覆盖全部 graph 级别 fail-closed 反例；无 metadata-only manifest 成功 fixture。

### Codex-F3：已修复

**入口/函数**: `dayu.host._runner_call_manifest.parse_runner_call_hot_payload()` → Tool Trace `_runner_call_diagnostic()` / Engine ingest `_runner_call_payload_diagnostic()`

**直接证据**:

1. `dayu/host/_runner_call_manifest.py:578-643` — `parse_runner_call_hot_payload()` 是 shared typed hot parser：
   - 要求字段集合精确等于 `_RUNNER_CALL_HOT_FIELDS`（19 字段，行 591-595），拒绝旧 `projector_metadata_summary` 数组及任意未知字段；
   - 要求 `diagnostic` 必须是 JSON object（行 597-598），拒绝 `None`、缺失、非 object 类型；
   - 通过 `runner_call_hot_diagnostic_from_json()` 解析 diagnostic 为 typed `RunnerCallHotDiagnostic`（行 599-601）；
   - `_validate_hot_atoms()` 交叉校验 `diagnostic.status` == `validation_status`（行 1372-1373）；
   - complete 时校验 `diagnostic.observed_count/expected_count` == `message_count`（行 1376-1381）；
   - complete 时校验 `diagnostic.observed_digest/expected_digest` == `role_sequence_digest`（行 1382-1388）。

2. `dayu/host/_runner_call_manifest.py:457-487` — `complete_runner_call_hot_diagnostic()` 构造 complete diagnostic，要求 `observed_count==expected_count==message_count`、`observed_digest==expected_digest==role_sequence_digest`，并通过 `_validate_diagnostic()` 做 complete 专有校验（行 1480-1497）：count/digest 字段必填、observed==expected。

3. `dayu/host/tool_trace.py:729-750` — `_runner_call_diagnostic()` 签名为 `(diagnostic: RunnerCallHotDiagnostic) -> Mapping[str, JsonValue]`，直接从 typed hot diagnostic 投影，不再从 sibling scalar 合成。

4. `dayu/host/engine_ingest.py:6606-6621` — `_runner_call_payload_diagnostic()` 先调用 `parse_runner_call_hot_payload(payload)`（行 6617）做完整 hot contract 校验，再投影 diagnostic atoms；不再自行从 sibling scalar 构造 complete diagnostic。

5. `dayu/host/engine_ingest.py:5997-6017` — `_manifest_hot_diagnostic()` 对 non-complete manifest 通过 `runner_call_hot_diagnostic_from_json()` 读取 manifest 内 diagnostic（行 6009），对 complete 通过 `complete_runner_call_hot_diagnostic()` 构造（行 6012-6017）。两者都产生 typed `RunnerCallHotDiagnostic`，交由 `runner_call_hot_payload()` 统一校验。

6. `tests/host/test_runner_call_hot_payload_contract.py:47-56` — 定义 `_HotPayloadTamperKind` 枚举覆盖 7 种 hot contract 篡改：`MISSING_DIAGNOSTIC`、`NULL_DIAGNOSTIC`、`MALFORMED_DIAGNOSTIC`、`LEGACY_METADATA_ARRAY`、`STATUS_MISMATCH`、`COUNT_MISMATCH`、`DIGEST_MISMATCH`。

7. `tests/host/test_runner_call_hot_payload_contract.py:353-388` — `test_shared_hot_parser_rejects_incomplete_or_conflicting_payload` 对全部 7 种篡改参数化，断言 `parse_runner_call_hot_payload()` 抛出 `HostDurableError`。

8. `tests/host/test_runner_call_hot_payload_contract.py:335-350` — `test_shared_hot_parser_accepts_explicit_complete_diagnostic` 断言 complete hot payload 的 diagnostic status/count/digest 全部显式且与 hot atoms 一致。

9. `docs/host/design.md:1719` — 明确 "`complete` 必须携带与 validation status、message count、role digest 同源的固定 shape diagnostic，不得为 `null`"，原互斥 contract 已统一。

10. 扫描确认：production hot producer/consumer 文件中无 `projector_metadata_summary` 热路径；complete hot success fixture 不含 `diagnostic=None`；无 hot `projector_metadata_summary` producer 成功路径。

**验证结论**: 修复完全符合 adjudication 要求。shared hot parser 要求显式 diagnostic 并交叉校验 status/count/digest；Tool Trace 与 Engine ingest 均消费 typed diagnostic，不合成；测试覆盖全部 hot contract 反例；design.md contract 已统一。

## Open Questions

- 无。

## Residual Risk

- stress suite 的单次 `active_cleanup` 瞬态失败已由 controller 和 AgentCodex 独立复跑确认通过，属于既有 S4 scheduler/worker stress boundary，不在本 S1 fix scope。
- fresh-schema contract 对旧 hot row 或 metadata-only manifest fail closed，这是 design-intended 行为；若部署前存在历史数据，需独立 deployment preflight 处理。
- S2-S8 lifecycle/admin/scheduler 行为未在本次 review 覆盖。

## Conclusion

**PASS**：三项 accepted findings（Codex-F1 高、Codex-F2 中、Codex-F3 中）均已在其语义 owner 边界修复。未发现兼容 fallback、下游修补、测试固化旧行为或新 material regression。docs/README 更新反映已实现 S1 contract。
