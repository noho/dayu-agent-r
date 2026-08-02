# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `b8f87e3b` (PR 190 HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-ds.md`
- Review date: 2026-08-03T03:36:39+08:00
- Included scope: 37 files (15 production, 2 config/prompts, 1 design, 15 tests, 2 utils/smoke, 2 durable)
- Excluded scope: Engine production, CLI/Service production, Fins, frozen registry (`docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`), `README.md` (S8 scope), `dayu/host/README.md` (S8 scope, confirmed stale reference at line 735)
- Parallel review coverage:
  - Subagent A: strict JSON boundary (`llm_compaction.py`) — covered
  - Subagent B: caps alignment (`context_governance.py` ↔ `memory.py`) — covered
  - Subagent C: repair/terminal flow (`compaction_operation.py`, `compact_pipeline.py`) — covered
  - Subagent D: event chain consistency (`context_events.py`, `memory.py`, `compact_payload.py`, `compact_artifact.py`, `run_input.py`) — covered
  - Subagent E: old symbol scan, reactive queue, test coverage, hasattr/getattr — covered
  - Main reviewer: contract types (`compaction.py`), governance (`context_governance.py`), prompts, `design.md`, `durable/memory.py`, synthesis — covered

## Findings

### 1-未修复-中-test_compaction_operation 测试覆盖回归

- **入口/函数**: `tests/host/test_compaction_operation.py`（整个文件从 1615+ 行重写为 456 行）
- **文件(行号)**: `tests/host/test_compaction_operation.py:1-456`
- **输入场景**: 以下场景的 fake compactor 类和对应测试函数被完全删除且无等价替换
- **实际分支**: 新测试文件仅覆盖 6 个场景：semantic reject→feedback、parser reject→semantic repair、execution failure 无伪造 feedback、all-invalid exhaust、root budget reject route、cancelled operation
- **直接证据**:

  删除的 fake compactor 类（16 个）：
  - `_FailOnceCompactor` — 第一次 RuntimeError、第二次成功
  - `_AlwaysFailingCompactor` — 始终 RuntimeError
  - `_SensitiveFailingCompactor` — 抛出含 `api_key=plain-secret`、`token=token-secret`、`Bearer bearer-secret`、`password=password-secret` 的异常（**敏感字段脱敏测试**）
  - `_EmptyMessageFailingCompactor` — 无消息的 RuntimeError
  - `_CancelAfterFailureCompactor` — 尝试间取消（**mid-retry cancellation**）
  - `_QualityRejectOnceCompactor` — 第一次 quality reject、第二次通过
  - `_HardThresholdOnceCompactor` — 第一次超 hard threshold、第二次通过
  - `_DiagnosticsOnlyLargeCompactor` — 诊断字段特大但业务文本小
  - `_RecordingCompactor` — 跨 pass 记录 CompactionRequest
  - `_DistinctFactPassCompactor` — 不同 pass 返回不同 evidence facts
  - `_SecondPassFailingCompactor` — 仅第二 pass 失败
  - `_DistinctPassCompactor` — 不同 pass 返回不同 summary/patch
  - `_RejectingToolExecutor` — 工具执行拒绝
  - `_RecordingProposalManifestRecorder` — manifest 记录
  - `_PreparedManifestCompactor` — prepared manifest
  - `_PreparedCancelledCompactor` — prepared manifest + 取消

  删除的测试函数（3 个）：
  - `test_compactor_proposal_manifest_uses_initial_trigger_for_first_attempt`
  - `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed`
  - `test_accepted_compaction_missing_successful_response_identity_guard_fails_closed`

  具体缺口：
  1. **敏感字段脱敏**：`_SensitiveFailingCompactor` 验证了 `api_key`、`token`、`Bearer`、`password` 等敏感字符串在异常消息中的脱敏行为。该场景无等价覆盖。
  2. **mid-retry cancellation**：`_CancelAfterFailureCompactor` 测试了 attempt 1 失败后、attempt 2 开始前取消的场景。新测试 `test_cancelled_operation_never_calls_compactor` 仅覆盖了操作启动前取消（pre-operation cancellation），不是 mid-retry 取消。
  3. **proposal manifest 生命周期**：3 个删除的测试函数覆盖了 manifest 的 trigger source、缺失 guard、response identity 缺失 guard。新测试不覆盖 manifest 路径。
  4. **diagnostics-only 大 payload**：`_DiagnosticsOnlyLargeCompactor` 测试了业务文本小但诊断字段超大的边界。无等价覆盖。
  5. **multi-pass 内容分化**：`_DistinctPassCompactor` 和 `_DistinctFactPassCompactor` 测试了不同 pass 产生真正不同内容（而非同一输出的 repaired 版本）。无等价覆盖。
  6. **第二 pass 独立失败**：`_SecondPassFailingCompactor` 测试了仅第二 pass 失败（非第一 pass），与 generic retry-after-execution-failure 的场景不同。

- **预期行为**: 这些场景应被等价或更精确的 owner-level 测试覆盖。
- **实际行为**: 新测试文件聚焦于 whole-candidate repair 的 happy path 和 exhaust path，但敏感字段脱敏、mid-retry 取消、manifest guard、diagnostics-only 大 payload 和 pass-specific 失败等防御性场景缺少覆盖。
- **影响**: 这些场景如有回归，可能静默通过测试但生产行为错误（如敏感信息泄漏到异常消息、mid-retry 取消被忽略、manifest 缺失不 fail-closed）。
- **建议改法和验证点**:
  1. 恢复 `_SensitiveFailingCompactor` 等价测试，验证异常消息中敏感字段被脱敏。
  2. 增加 mid-retry cancellation 测试：attempt 1 失败后、attempt 2 prepare 前设置取消，验证操作返回取消终态且不调用 compactor。
  3. 恢复 proposal manifest guard 测试（缺失 manifest 或缺失 response identity 时 fail-closed）。
  4. 增加 diagnostics-only 大 payload 场景（候选业务文本小、diagnostics 超大），验证仍被正确拒绝或接受。
  5. 增加第二个 pass 独立失败的 multi-pass 场景。
- **修复风险（低）**: 仅新增测试，不改变生产代码。
- **严重程度（中）**: 防御性场景覆盖缺失，虽然核心 happy path 已验证，但敏感信息泄漏和 mid-retry cancel 是安全/稳定性相关的边界。

### 2-未修复-低-durable/memory.py 变更以格式化为主，业务变更需确认

- **入口/函数**: `dayu/host/durable/memory.py`（多个函数）
- **文件(行号)**: `dayu/host/durable/memory.py:164-1434`（diff 范围）
- **输入场景**: durable memory 的 snapshot/item/diagnostic 读写路径
- **实际分支**: diff 显示 +23/-73 行，但大部分是行长度格式化（将原本多行参数折叠为单行）。实际业务变更集中在：
  - `_memory_projection_payload_view`（~line 366-370）：`parse_context_compacted_semantic_payload(event.payload)` 替代旧的业务枚举 `.value` 读取 — 这是正确的 v2 迁移
  - 删除了 `_CanonicalMemoryBusinessText` 类
- **直接证据**: 实现报告 §8 记录了该变更：`durable forward-intent/reference serializer 仍调用业务文本 .value；这里是正确持久化 owner`。但实际 diff 中大部分是格式化变更，真正的业务变更（删除 `_CanonicalMemoryBusinessText` 和改用 `parse_context_compacted_semantic_payload`）占比很小。
- **预期行为**: 格式化变更与业务变更应在独立 commit 中分离，或至少在实现报告中说明格式化占比。
- **实际行为**: 23 insertions、73 deletions 的数字中大部分是格式化，实际业务变更更小。这不影响正确性，但降低了 diff 可审查性。
- **影响**: 仅影响代码审查可读性，不影响运行时行为。
- **建议改法和验证点**: 无需修改。说明格式化变更的原因（如 ruff format 或手动折叠长行）并确认 `parse_context_compacted_semantic_payload` 路径有 roundtrip 测试覆盖（`test_memory_projection.py` 已有覆盖）。
- **修复风险（低）**: 无需修复。
- **严重程度（低）**: 可读性问题，不影响正确性。

### 3-未修复-低-intent_type 与 reason 从闭集枚举改为自由文本

- **入口/函数**: `CompactForwardIntentV2.intent_type: str`、`CompactReferenceContinuityV2.reason: str`
- **文件(行号)**: `dayu/host/compaction.py:1224`（intent_type）、`dayu/host/compaction.py:1270`（reason）
- **输入场景**: LLM 返回 candidate 时填写 `intent_type` 和 `reason` 字段
- **实际分支**: v1 contract 中 `intent_type` 是闭集枚举（`next_step_note|open_question|pending_clarification|pending_user_visible_task`），`reason` 也是闭集（`local_reference|ordinal_reference|ellipsis_recovery|recent_state`）。v2 contract 中两者均改为 `str`（自由文本）。
- **直接证据**:
  - `CompactForwardIntentV2.intent_type: str`（compaction.py:1224），只校验非空
  - `CompactReferenceContinuityV2.reason: str`（compaction.py:1270），只校验非空
  - prompt 中也不再列出闭集允许值（`conversation_compaction_user.md` 仅写 "非空字符串"）
  - `CompactForwardIntentStatusV2` 仍然是闭集枚举（`open|blocked|superseded`），但 `intent_type` 和 `reason` 不再是
- **预期行为**: 如果设计意图是允许模型自由选择 intent_type/reason，这是合理的简化。如果设计意图是约束为闭集以保证 Memory 下游可解释性，则需要重新评估。
- **影响**: 模型可能返回非标准 `intent_type` 或 `reason`，下游 Memory projection 和 RunInput reader 需要能处理任意字符串。当前 Memory 的 `ConversationMemorySnapshotVNext` 中对应字段也是 `str`，因此一致性成立。
- **建议改法和验证点**: 确认这是有意的设计决定。若有意，无需修改。若无意（可能是迁移遗漏），恢复为 v2 闭集 StrEnum 并更新 prompt 中的允许值列表。
- **修复风险（低）**: 如恢复闭集，需同步更新 `compaction.py` 类型定义、`llm_compaction.py` 解析逻辑（增加 `_required_enum` 调用）和 prompt。
- **严重程度（低）**: 这是 contract 设计选择，当前不造成不一致，但如果后续需要按 intent_type 做分类决策，自由文本会增加复杂度。

### 4-未修复-低-AnswerAnchor 从 items 列表改为 detail 单字段

- **入口/函数**: `CompactAnswerAnchorV2` 类型定义
- **文件(行号)**: `dayu/host/compaction.py:1174-1211`
- **输入场景**: LLM 返回 answer anchor candidate
- **实际分支**: v1 contract 中 answer anchor 有 `anchor_items: list[AnswerAnchorChild]`，每个 child 有 `display_text` 和可选 `ordinal`。v2 contract 改为 `title: str` + `detail: str` 两个平字段。
- **直接证据**:
  - `CompactAnswerAnchorV2` 字段：`title: str`、`detail: str`、`source_labels: tuple[str, ...]`（compaction.py:1182-1184）
  - prompt 中说明：`title`（非空字符串）、`detail`（非空字符串）
  - 不再有 `anchor_items` 列表或 `ordinal` 字段
- **预期行为**: 如果设计意图是简化 answer anchor 结构（用单段 detail 文本替代列表），这是合理的。但 flattened detail 丢失了 item 级结构和序号信息。
- **影响**: Memory 中 answer anchor 的粒度从"多个带序号的子项"变为"一个标题+一段细节文本"。后续如果模型引用"刚才的结论第 3 点"，Host 无法在 Memory 中定位到具体子项。当前 Memory 的投影逻辑需要与此简化一致（`memory.py` 中 answer memory 的 `item_text` 字段）。
- **建议改法和验证点**: 确认这是有意的设计简化。检查 `memory.py` 中 answer anchor projection 是否与 v2 `title+detail` 结构一致（从 `_facts_from_accepted_event` 和相关函数验证）。
- **修复风险（低）**: 如需要恢复子项结构，需改动类型定义、parser、prompt 和 Memory projection。
- **严重程度（低）**: contract 设计选择，当前不影响正确性。

---

## 逐项证实/挑战（无 finding 项）

以下检查项均有直接证据支撑，**未发现实质性问题**：

### strict duplicate/unknown JSON boundary

**证实通过。** `llm_compaction.py:965-978` 的 `_strict_object_pairs` 通过 `json.loads(object_pairs_hook=...)` 在 Python 默认"后值覆盖前值"发生前检测重复 key。`_require_exact_keys`（line 1054-1075）在顶层和每个嵌套对象层执行 exact-key 检查（顶层 8 字段、summary 2 字段、fact 3 字段、anchor 3 字段、intent 4 字段、reference 3 字段、diagnostic 3 字段、drop 2 字段）。unknown/missing key 通过 `ValueError` 前缀精确路由到 `_parser_validation_report`（line 1014-1051），映射为 `DUPLICATE_JSON_KEY`、`UNKNOWN_JSON_KEY`、`MISSING_REQUIRED_KEY`。v1 schema 在 line 757-758 被 `!= COMPACT_OUTPUT_SCHEMA_V2` 严格拒绝。各层 exact-key frozenset 直接来自 field 常量（`_TOP_LEVEL_FIELDS` 等），不存在 loose parser 路径。

### source boundary/represented/dropped exact coverage

**证实通过。** `context_governance.py:261-327` 的 `_collect_coverage_issues` 强制执行精确 partition：`boundary_labels == represented_labels ∪ explicitly_dropped_labels` 且交集为空（line 276-327）。未知 label（不在 boundary 中）在 line 280-288 被拒绝。重复 drop 在 line 289-306 被拒绝。represented/drop overlap 在 line 308-316 被拒绝。uncovered source 在 line 318-327 被逐 label 检测。Host 派生的 `_represented_sections`（line 544-565）从 5 个业务区的 source_labels 引用关系唯一计算 represented map，不存在 candidate 自身报告的第二份 represented list。`CompactAcceptedTruthV2.__post_init__`（compaction.py:1716-1719）再次硬编码 partition 等式。

### section count/char/total caps 与 Memory 同源

**证实通过。** `context_governance.py:41` 直接 import `MemoryProjectionPolicy` 和 `estimate_memory_size_units`。`accept_compact_candidate_v2` 接收 `memory_policy: MemoryProjectionPolicy` 参数（line 52），不做 copy 或重新实例化。`_collect_policy_issues`（line 454-505）和 `_section_caps`（line 508-541）读取 `policy.session_summary_char_cap`、`policy.evidence_fact_item_cap`、`policy.evidence_fact_char_cap` 等字段，使用同一个 `estimate_memory_size_units`。context_governance.py 中 **零** 个硬编码 cap 常量。Memory 侧 `_validate_committed_candidate_policy`（memory.py line 1652）也使用相同 policy 字段和 estimator，在读时二次验证。

### diagnostics-only/low-info/duplicate/contradiction

**证实通过。** `_collect_information_issues`（context_governance.py:422-451）检测：全空（五个业务区 0 item + diagnostics 空 → `EMPTY_SEMANTIC_OUTPUT`）、diagnostics-only（0 semantic + diagnostics 非空 → `DIAGNOSTICS_ONLY_OUTPUT`）、低信息（非空 boundary 但 represented 为 0 → `LOW_INFORMATION_OUTPUT`）。`_collect_duplicate_and_contradiction_issues`（line 330-393）按 plan §9.4 的确定性 identity 规则检测：fact=`claim`（`_canonical_text` 处理后）、anchor=`title+detail`、intent=`intent_type+text`、reference=`text`、diagnostic=`code+message`。contradiction 只判 schema 可证明冲突：同一 intent 不同 status、同一 reference 不同 reason、同一 drop label 不同 reason。不引入自然语言模糊相似度判断。

### bounded redacted whole-candidate repair

**证实通过。** `build_compact_repair_feedback_v2`（context_governance.py:107-141）实现 32/240/8192 三重边界：issues 截取前 32（line 125）、单条 message 截断到 240 字符（`_bounded_issue_message` line 734-750）、总 feedback JSON 字符不超过 8192（line 133-141 的 while 循环逐步减少 issue 数）。feedback 不含 raw candidate 片段、input readable text、canonical refs、event/tool-call id、digest、cursor。`required_action` 固定为完整 replacement（`COMPACT_REPAIR_REQUIRED_ACTION` line 1622-1624）。`repair_feedback` 作为 typed `CompactRepairFeedbackV2 | None` 参数传递（compaction_operation.py:707），首次为 `None`（line 693），不进入 extra payload。

### immutable input、global budget、root revalidation、cross-pass label collision

**证实通过。** `CompactPipelinePassQueuePlan`（compact_pipeline.py:251）在构造时冻结 root input 和 pass queue。`build_reactive_pass_queue_plan`（line 576-626）按 material block 确定性切分，各 pass boundary 通过 `_bind_reactive_pass_to_root_labels`（line 629-699）绑定到 root labels，验证 `rebound_input.source_boundary == expected_entries`（line 697-698）。`_operation_pass_requests`（compaction_operation.py:1390-1425）验证 pass boundaries 是 root 的互斥 partition。root revalidation 在全部 pass accepted 后执行（line 1064-1166）：`_aggregate_pass_candidates` 机械合并、`accept_compact_candidate_v2` 对 root input 重新执行全部 semantic/budget validation、失败按 `_route_root_validation_report`（line 1241-1257）路由到贡献该 issue 的最后一个 pass。全局 budget 通过 `attempt_number <= max_attempt_number`（line 805）和 `repairable = attempt_number < max_attempt_number`（line 834）控制。cross-pass label collision 因各 pass boundary 是 root 的互斥子集且绑定到 root labels 而自然避免。

### invalid/intermediate 无 artifact/event/Memory/RunInput/trace

**证实通过。** 中间 pass accepted truth 仅存储在 operation-local `accepted_pass_truths: list[CompactAcceptedTruthV2 | None]`（compaction_operation.py:790），root revalidation 失败时清除（line 1110）。`_failed_operation_result`（line 1362-1387）始终返回 `accepted_truth=None`。rejected attempt 仅记录 manifest 引用（line 870），不写 artifact/event。Memory 只从 committed `CONTEXT_COMPACTED` event 的 `compacted_semantics` 消费（memory.py:1229-1255），不从 operation 内存对象直接读取。RunInput 从 committed EventLog row 解析（run_input.py:1949-1984、4214-4262），不解析 raw LLM JSON。

### 单一 terminal、late/stale/cancel race

**证实通过。** `_run_compaction_operation` 的所有 return 路径中，仅一条产生 `accepted_truth is not None`（line 1158-1166），其余全部返回 `accepted_truth=None`。`_CompactionAttemptCancellationToken`（compaction_operation.py:577-652）为每次 attempt 创建新实例（line 836），单次 timeout 不污染后续 attempt。`_ensure_compactor_proposal_active`（line 1557-1578）在 manifest 写入后、实际 LLM 调用前二次检查取消状态。`asyncio.CancelledError` 在 `_prepare_compactor_proposal` 中与 `cancellation_token.is_cancelled()` 联动（line 1487-1492），未确认的 CancelledError 透传。

### rolling replacement 与 committed-event-only Memory

**证实通过。** Memory 的 `project_conversation_memory_event`（memory.py:1229-1255）对 `CONTEXT_COMPACTED` 事件执行：session summary 全量替换（line 1242-1244）、evidence facts 全量替换（line 1246-1248）、answer anchors 全量替换（line 1250）、forward intents 全量替换（line 1251）、reference continuity 全量替换（line 1252-1254）。selected recent window 中 items 通过 `source_set.isdisjoint(covered)` 删除被 compact 覆盖的 raw material（line 1957），`current_input_ref` 始终保护。第二次 compact 时，前次 accepted candidate 被 material builder 投影为 previous-* boundary entries，新 candidate 必须逐项 represented 或 drop。commit 后 Memory 只含第二次 accepted truth。

### artifact/EventLog/Memory/RunInput/trace 同源

**证实通过。** 全链使用同一个 `CompactAcceptedTruthV2` 对象：
- `build_context_compacted_payload`（context_events.py:1136）从 `accepted_truth` 提取 candidate/boundary/coverage 写入 event payload
- `compact_artifact_json_vnext`（compact_payload.py:742）从同一 `accepted_truth` 提取相同字段写入 artifact JSON
- Memory 从 committed event 的 `parse_context_compacted_semantic_payload` 恢复后，重新验证 coverage 等式（`_validate_committed_coverage`，compact_payload.py:350-378）和 candidate digest（line 136-137）
- RunInput 从 committed EventLog row 调用同一 `parse_context_compacted_semantic_payload`（run_input.py:1973、4248、5465）

### fresh schema 无 alias/old reader

**证实通过。** 全局 `rg` 扫描结果：在 `dayu/host`、`dayu/config`、`tests/host`、`tests/runtime/test_scene_prepare.py`、`tests/service/test_entrypoint_runtime_interactive_path.py`、`docs/host/design.md` 中，所有 v1 符号（`CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT`、`CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`、`ConversationCompactInputVNext`、`ConversationCompactOutputVNext`、`ConversationCompactLabelSectionVNext`、`CompactReadableViewVNext`、`CompactCandidateDiagnosticVNext`、`CompactQualityIssueVNext`、`CompactQualityCheckResultVNext`）**零命中**。仅 `dayu/host/README.md:735` 有一个文档残留 `conversation_compact_output_v1` 引用，已列入 S8 scope。v1 相关 `schema_version` 字段名和旧 field name 全部替换为 v2 `schema` + v2 field names。

### 空 boundary proactive/reactive

**证实通过。** `CompactInputV2.source_boundary` 可为空 tuple。当 `build_reactive_pass_queue_plan` 的 selected blocks ≤ 1 时返回空 pass queue（compact_pipeline.py:588-593）。空 boundary 在 material builder/selection 边界结束，不调用 compactor。`context_governance.py:444` 的 `len(compact_input.source_boundary) > 0 and len(represented) == 0` 分支只在 boundary 非空时才检测 `LOW_INFORMATION_OUTPUT`，空 boundary 不触发该 issue。

### allowlist expansions、utils churn

**证实通过。** 实现报告 §8 记录了 7 个 allowlist 例外，每个都有 entry/current SHA-256 和 numstat。`utils/smoke_host_public_conversation_memory_scenarios.py` 的 `+103/-164`（`-w` 后 `+99/-160`）和 `utils/smoke_host_public_r03_semantic_ownership.py` 的 `+6/-4` 均是最小 patch（删除旧 section/alias reader、改写 strict v2 fake candidate）。没有使用 checkout/reset。两个 utils 是 AGENTS 定义的 smoke/分析脚本，不纳入 production coverage 要求。

### 设计真源、中文 docstring、分层/owner

**证实通过。** `docs/host/design.md` 的 §24.3 从 v1 I/O contract 完整机械更新到 v2（`ConversationCompactInputVNext` → `CompactInputV2`、`ConversationCompactOutputVNext` → `CompactCandidateV2`、field names 全量映射），不保留迁移叙事。所有修改的生产文件均提供中文 docstring（类级、函数级、参数/返回值/异常）。分层清晰：`compaction.py` 只拥有类型契约，`context_governance.py` 只拥有 accept 判定，`llm_compaction.py` 只拥有 LLM 调用和 strict parse，`compact_pipeline.py` 只拥有 pass queue 构造，`compaction_operation.py` 只拥有 attempt/repair/terminal 编排，`memory.py` 只拥有 Memory projection。无 God object（无跨层 God dataclass、无上帝函数）。

### 过度设计检查

**证实通过。** 没有引入通用 JSON Schema 框架、多阶段 DAG、新数据库、语义 embedding 去重。没有改变 Engine outcome owner。`CompactAcceptedTruthV2` 的 `_permit` 模式是必要的构造来源控制，不属于过度设计。

### 无 hasattr/getattr/loose parsing

**证实通过。** 在 `dayu/host/`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_pipeline.py` 中 `hasattr`/`getattr` 零命中。所有属性访问均为直接 dot notation。

### Reactive queue 保留

**证实通过。** `CompactPipelinePassQueuePlan` 在 `compact_pipeline.py:251` 定义并在 line 1192 导出；`build_reactive_pass_queue_plan` 在 line 576 定义并在 line 1201 导出。`engine_ingest.py:107` import 并在 line 2788 调用。两个 owner tests（`test_compact_pipeline.py` lines 289、326、363、399）覆盖该路径。系统保留了 reactive queue 而不删除。

### v1 兼容性代码无残留

**证实通过。** 没有兼容性 re-export、兼容性常量 re-export、兼容性 wrapper/facade。旧 symbols/literals 全部删除，无 alias。`_CanonicalMemoryBusinessText` 已完全删除。

---

## Open Questions

1. **intent_type/reason 自由文本化是否为有意的设计决定？** v1 中两者均为闭集枚举，v2 改为自由文本 `str`。如果后续需要按 intent_type 做 Memory 分类或按 reason 做 compaction 策略决策，自由文本会增加复杂度。建议确认此变更是否为有意的简化。

2. **AnswerAnchor 从 items 列表改为 detail 单字段是否丢失了结构化信息？** v1 的 `anchor_items: list[{display_text, ordinal}]` 能保留"第 3 点"这样的序号引用，v2 的 flat `detail: str` 丢失了 item 级粒度。当前 Memory 投影中 answer anchor 的存储粒度是否与此简化一致？

3. **utils churn 的 `-w` diff 是否完全排除格式化？** 实现报告 §8 说首次迁移误对整个文件运行 `ruff format` 后纠正。最终 `+99/-160`（`-w`）与 `+103/-164` 的差值（4 行）是仅空格差异还是有未说明的内容变更？

---

## Residual Risk

1. **LLM 自然语言质量风险（已知，非实现缺陷）**：deterministic validator 能证明 schema、coverage、caps、duplicate/contradiction 边界，但不能证明自然语言 claim 是否真实蕴含于 evidence 或 summary 是否忠实。这属于模型评估风险，不属于 S7 实现缺陷。

2. **测试覆盖密度**：`test_compaction_operation.py` 从 1615+ 行重写为 456 行后，每测试行覆盖的代码路径密度显著降低。虽然新测试覆盖了核心 whole-candidate repair 流程，但防御性边界（敏感字段脱敏、mid-retry cancel、manifest guard）的覆盖空缺意味着这些路径的回归只能依赖 integration/CLI evidence 而非 focused unit tests。

3. **multi-pass root revalidation 的实际触发路径**：reactive multi-pass 的 root revalidation（line 1064-1166）包含复杂的 issue 路由逻辑（`_route_root_validation_report` line 1241-1257，从最后一个 pass 向前扫描贡献者）。当前测试覆盖了 root budget reject 的 route 路径（`test_root_hard_budget_reject_routes_whole_candidate_repair`），但 coverage/duplicate/contradiction 等其他 root reject reason 的 route 路径是否有覆盖需要确认。

4. **`dayu/host/README.md:735` 的文档残留**：`conversation_compact_output_v1` 引用仍在 README 中。按 plan S8 scope 由 S8 负责更新，不属于 S7 缺陷，但若 S8 遗漏则成为文档与代码不一致。

---

## 结论

**ACCEPT** — 有建议。

S7/F07 实现完成了 fresh v2 contract 的原子 closure。strict JSON boundary（duplicate key 检测、exact-key parsing、v1 reject）、source coverage exact partition、policy caps 同源、diagnostics-only/low-info/duplicate/contradiction 判定、bounded redacted whole-candidate repair、immutable input/global budget/root revalidation、中间 pass 隔离、单一 terminal、committed-event-only Memory、artifact/EventLog/Memory/RunInput/trace 同源、fresh schema 零旧 symbol、空 boundary 处理、reactive queue 保留等关键不变量均有逐项直接证据支撑。

主要建议：
1. 补充 `test_compaction_operation.py` 的防御性测试覆盖（敏感字段脱敏、mid-retry cancellation、manifest guard）。
2. 确认 `intent_type`/`reason` 自由文本化和 AnswerAnchor 结构简化是否为有意的设计决定。
3. 确认 S8 将处理 `README.md:735` 的文档残留。
