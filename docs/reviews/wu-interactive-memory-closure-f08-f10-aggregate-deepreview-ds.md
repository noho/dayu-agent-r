# Aggregate Deep Review：Interactive Conversation Memory closure F08–F10 — DS 第二路独立 aggregate deep review

## Scope

- **Mode**: aggregate cross-slice deep review
- **Review range**: `68ba403811fe98835ea93f8c715ca8ed7ba26164..fd15b660`（accepted plan checkpoint 后的全部实现/测试/docs/artifacts）
- **Slices**: F08（session summary null/meaningful）、F09（compactor Tool Trace canonical manifest hot identity）、F10（turn-group atomic selection、feedback binding、budget boundedness）
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-ds.md`
- **Included scope**: 全部 production changed files（`compact_material.py`、`compact_pipeline.py`、`compaction.py`、`compaction_operation.py`、`context_governance.py`、`dispatch.py`）、全部 test changed files、`dayu/config/prompts/scenes/conversation_compaction_user.md`、`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
- **Excluded scope**: MiMo review artifacts（按要求不得参考）；Engine、Memory projector、RunInput consumer 未修改故不纳入 adveresarial consumer trace
- **Parallel review coverage**: 三路 subagent 覆盖 compaction.py/compaction_operation.py（a8e7f21a）、compact_pipeline.py/context_governance.py（a7c1249c）、dispatch.py/memory.py（a2341d45）；主 reviewer 独立复验全量 production diff 与关键 test cases
- **Review date**: 2026-08-04

## Method

本 review 是对 F08–F10 三片 closure 的第二路独立 aggregate deep review。不参考或复述 MiMo 结论；基于直接代码走读、数据流追踪、跨片 adversarial 检查和消费者-生产者 contract 验证。cross-slice 检查重点：

1. **F08 prompt → F10 compact material build → memory projection**：meaningful summary/null/self-contained 规则是否完整传导；hash/manifest 消费者是否看到一致语义
2. **F09 canonical manifest → F10 operation → dispatch**：runner-call manifest/EventLog/hot/public resolver 在所有 success/repair/exhaust/fallback 路径上是否身份同源
3. **F08+F09+F10 集成**：compactor runner-call/trace/dispatch/memory 集成中是否存在 stale/late/double terminal、identity mismatch、LLM 治理字段泄漏、Memory/RunInput/artifact 分叉、下游补偿、compat/schema/public surface 漂移或 God helper

---

## Cross-Slice Adversarial Findings

### 1-NEEDS_FIX-中-`_validate_operation_selected_pack` 的 sorted multiset 比较不覆盖 previous_compacted_view blocks

- **入口/函数**: `_validate_operation_selected_pack`（`compaction_operation.py:1596`）
- **文件(行号)**: `dayu/host/compaction_operation.py:1604-1619`
- **输入场景**: attack 构造一个 root request，其中 `selected_block_provenance` 的 refs/digest 与 previous_compacted_view blocks 的对应项发生交换（即 provenance item A 的 `(canonical_source_refs, packed_content_digest)` 交换为 provenance item B 的值）
- **实际分支**: `_validate_operation_selected_pack` 第 1605-1609 行只遍历 `trace_material`、`evidence_material`、`answer_material` 三个 section，**不包含** `previous_compacted_view` blocks。sorted multiset 比较（`proof_values != pack_values`，第 1619 行）因此不会检测 previous_compacted_view 块的 provenance 与 pack 内容的偏差
- **预期行为**: `_validate_operation_selected_pack` 应对 material pack 中出现的所有 selected blocks（包括 previous_compacted_view）做 provenance 一致性验证
- **实际行为**: previous_compacted_view blocks 的 provenance 不在 proof-vs-pack 验证范围内
- **直接证据**:
  - `compaction_operation.py:1605-1609`：`packed_blocks = (*request.material_pack.trace_material, *request.material_pack.evidence_material, *request.material_pack.answer_material)` — 缺少 `previous_compacted_view`
  - 对比：`_validate_operation_root_request`（`compaction_operation.py:1584-1590`）对 boundary 的验证**包含** `previous_compacted_view` 的 block_labels
  - `CompactSegmentSelection.selected_block_provenance` 可能包含 previous_compacted_view 来源的 provenance items（如果 initial selection 将它们包含在 selected 中）
- **影响**: 中等。DS re-review（F10 code review）的 Finding 1 已识别 sorted multiset 比较在 pipeline 被绕过时无法防御 A↔B 完整交换，但未识别 previous_compacted_view blocks 在 operation 层**完全不参与** proof-vs-pack 比较。当前 `build_compact_material_pack` 的 provenance_map 是从 previous/trace/evidence/answer 全部 blocks 构造的（`compact_material.py:1177-1183`），但 `_validate_operation_selected_pack` 的 pack_values 只覆盖三个 section。如果 future code path 将 previous_compacted_view blocks 纳入 selected_block_provenance（例如 recovery tier 1 的 retained previous blocks），该验证将产生漏报
- **建议改法和验证点**:
  1. 在 `_validate_operation_selected_pack` 的 `packed_blocks` 中显式加入 `request.material_pack.previous_compacted_view`
  2. 或者明确文档化：`_validate_operation_selected_pack` 只覆盖 delta material，previous view 的 provenance 由 `validate_previous_compacted_view_pair` 在构造时独立保证
  3. 添加测试：`test_previous_view_provenance_swap_fails_before_provider`，构造 forged request 使 previous_compacted_view block 的 content_digest 被篡改，断言 `run_compaction_operation` 返回 failure
- **修复风险（低）**: 当前 previous_compacted_view blocks 的 provenance 来自 `_previous_compacted_view_pair_from_candidate` 的机械映射（`compact_material.py:2255-2333`），block_id 使用固定前缀 `"previous:{event_id}:..."` 格式（不与 delta block_id 冲突），加入后不会产生假阳性
- **严重程度（中）**: 当前调用路径安全（tier 1/2/3 的 previous view retention 通过 `retained_previous_compacted_view_labels_for_recovery` 与 `transform_previous_compacted_view_pair_for_recovery` 保证一致性）；但 operation 层缺乏 defense-in-depth，且该 gap 与 DS Finding 1（sorted multiset 比较）不同——它属于**遗漏 section** 而非**比较方式**问题

### 2-NEEDS_FIX-低-`_requires_budget_acceptance` 硬编码为 `True`，与函数签名语义不一致

- **入口/函数**: `_requires_budget_acceptance`（`compaction_operation.py:1663`）
- **文件(行号)**: `dayu/host/compaction_operation.py:1663-1674`
- **输入场景**: 任何调用该函数的路径
- **实际分支**: `del request; return True`（第 1674 行）；函数参数 `request` 被立即删除，无条件返回 `True`
- **预期行为**: 函数签名暗示某些场景下可以跳过 budget acceptance（例如测试路径、dry-run、或 budget policy 未启用时），但实际实现硬编码为始终要求 budget gate
- **实际行为**: 无条件返回 `True`，使 `request` 参数成为死代码
- **直接证据**: `compaction_operation.py:1674` — `del request; return True`
- **影响**: 低。当前行为正确（compaction 后始终需要 budget gate），但函数签名与实现语义不一致，可能导致 future maintainer 误以为可以通过传入特定 `request` 跳过 budget gate，从而引入治理漏洞
- **建议改法和验证点**:
  1. 删除该函数，将 `_requires_budget_acceptance(request)` 的调用点（`_run_compaction_operation:1146`）替换为字面量 `True`
  2. 或在 docstring 中明确标注 "无条件启用，参数保留为 future extension point"
  3. 验证点：确认 `_run_compaction_operation:1150` 的 `if requires_budget and budget > hard_threshold_tokens` 分支仍可达（已有测试覆盖）
- **修复风险（低）**: 纯代码清理
- **严重程度（低）**: 无 correctness impact；属 maintainability 问题

### 3-INFORMATIONAL-`DurableCompactorProposalManifestRecorder` 内部创建 `PayloadStore()` 实例而非依赖注入

- **入口/函数**: `DurableCompactorProposalManifestRecorder.__init__`（`compaction_operation.py:211`）
- **文件(行号)**: `dayu/host/compaction_operation.py:236`
- **输入场景**: 任何创建 `DurableCompactorProposalManifestRecorder` 的调用点
- **实际分支**: `self._payload_store = PayloadStore()`（第 236 行），在 `__init__` 内部创建 PayloadStore 实例，不从外部注入
- **预期行为**: 遵循依赖注入原则，由调用方提供 PayloadStore 实例，确保同一 transaction 范围内的 PayloadStore 一致性
- **直接证据**: `compaction_operation.py:236` — `self._payload_store = PayloadStore()`
- **影响**: 低。当前 `PayloadStore` 是无状态工具类，不持有连接池或共享状态，因此多次创建不会产生资源泄漏或状态分叉。但如果未来 `PayloadStore` 引入有状态能力（如缓存、连接复用），此处将产生隐蔽 bug
- **建议改法和验证点**: 将 `payload_store: PayloadStore | None = None` 加入 `__init__` 参数，仅在 `None` 时创建默认实例
- **严重程度（信息性）**: 非 correctness bug；属架构 hygiene

---

## Cross-Slice Integration Trace

### F08 → F10：Session Summary Null Flow

**完整链路**：LLM prompt（`conversation_compaction_user.md`）→ compactor 输出 candidate → `accept_compact_candidate_v2`（`context_governance.py:59`）→ `CompactAcceptedTruthV2` → `build_compacted_payload_input`（`compact_pipeline.py:705`）→ `CONTEXT_COMPACTED` EventLog → `project_conversation_memory_event`（`memory.py:1229`）→ `ConversationMemorySnapshotVNext` → `SessionSummaryMemoryView`

**验证结论**: ✅ 链路完整，无 semantic drift

- **Prompt 侧**（F08）: `conversation_compaction_user.md:34-37` 明确要求：无法形成完整业务陈述时必须输出 `null`；禁止占位符、孤立字符、截断片段；null 表示清除旧 summary，不影响其它四类语义
- **Accept barrier**（F10/governance）: `_collect_information_issues`（`context_governance.py:457-486`）对 `session_summary=None` 不做 LOW_INFORMATION 判定；只在整个 boundary 非空且 represented 为零时才报告 LOW_INFORMATION
- **Memory projection**: `_session_summary_from_accepted_event`（`memory.py:1242-1245`）正确处理 `accepted_candidate.session_summary is None` → 清空 `session_summary_memory`；其他四类语义（facts/anchors/intents/references）不受影响
- **Digest 一致性**: `CompactCandidateV2.digest()`（`compaction.py:1426-1432`）对 `session_summary=None` 产生稳定 digest；同一 candidate 的 digest 在 accept barrier、EventLog payload、artifact descriptor 三处一致 → 无 fork risk

**未发现**: LLM governance 字段泄漏。`CompactSessionSummaryV2.to_json()` 不含 Host provenance 字段；`CompactMaterialPack.llm_json()` 剥离 provenance_map

### F09 → F10：Manifest Recorder Call Coverage

**验证范围**: `_run_compaction_operation`（`compaction_operation.py:749`）的六条退出路径

| 路径 | Manifest 是否记录 | 证据 |
|------|-------------------|------|
| 成功 accept（第 1207 行） | ✅ 每次 attempt 均记录 | `_prepare_compactor_proposal`（第 865 行）→ `_record_compactor_proposal_manifest`（第 1816 行） |
| QUALITY_CHECK_REJECTED（第 898/1049 行） | ✅ 每次 attempt 均记录 | 同上；manifest_reference 随 rejection 返回 |
| PROPOSAL_FAILED（第 941/1010 行） | ✅ 每次 attempt 均记录（若 proposal 在 manifest recording 之后失败） | `_prepare_compactor_proposal` 的 prepared path 在 `run_prepared_compactor_proposal()` 调用**前**已完成 manifest recording；若 proposal 执行失败，manifest 已记录 |
| CANCELLATION_REQUESTED（第 860/971 行） | ✅ 若已进入 attempt loop | proposal_manifest_reference 初始化为 `None`，仅在 `_prepare_compactor_proposal` 返回后被赋值；若 cancellation 发生在首次 proposal 调用前，manifest 未记录（正确行为——没有 runner call 就没有 manifest） |
| Non-repairable contract failure（第 807 行） | ❌ 未记录 | 此路径在 Phase 0 validation 失败时直接返回 `_non_repairable_contract_failure_result`，未调用 compactor，未产生任何 RUNNER_CALL_INPUT_ASSEMBLED 事件 → **行为正确**，无 runner call 即无 manifest |
| Non-repairable rejection exhaustion（第 1216 行） | ✅ 最后一次 rejection 携带 manifest_reference | `_attempt_rejected` 保存 `proposal_manifest_reference` |

**关键验证**: F09 的修复（`DurableCompactorProposalManifestRecorder`）对所有实际发生 runner call 的 attempt 均写入 manifest + hot payload。contract failure 路径无 runner call，不写入 manifest → 符合 design intent。legacy compactor 路径（`compactor.compact()` 直接调用，无 prepared protocol）**不**记录 manifest → 此为 F09 design 中已接受的限制：只有实现 `CompactorProposalPreparedCompactor` protocol 的 compactor 才享有正式 Tool Trace identity

### F08+F09+F10：Stale/Late/Double Terminal

**检查范围**: dispatch → compaction operation → manifest recording → compact accepted event write → dispatch re-freeze

**验证结论**: ✅ 保护充分，未发现 stale/late/double terminal gap

- **Compaction operation 幂等保护**（`dispatch.py:2345-2412`）：在 accept compact event 写入前，重新验证 Run existence、status match、input_event_sequence match；若 stale → 写入 `compaction_failed`（reason=`stale_compaction_result`），不创建 pending dispatch
- **Late terminal 保护**（`dispatch.py:2134-2154`）：`begin_compaction_terminal_commit_in_transaction` 使用 CAS 模式；`INVALID_MULTIPLE` disposition → `HostDurableError`
- **Double terminal 保护**（`dispatch.py:811-830`）：`_DispatchCandidateOutcome.__post_init__` 强制 `pending_dispatch` 与 `terminal_notice` 互斥
- **Cross-slice race**: compact accepted event 写入与 post-compact candidate re-freeze **在同一次 write transaction 内不连续执行**——compact accepted 在 `_execute_proactive_compaction` 的 write transaction（第 2345 行），post-compact re-freeze 在 `_start_governed_after_compact` 的**独立** write transaction（第 2551 行）。两个 transaction 之间的窗口期：Run 状态可能被其他 dispatcher 修改。`_start_governed_after_compact` 在 re-freeze 前重新读取 Run（第 2555 行），若 status 已漂移 → 返回 `None` → `pending_dispatch=None` → 该 Run 由下次 promotion coalescing 重新处理。**行为正确**，无 orphan compact
- **Durable manifest vs accepted compact fork**: manifest 在 `_record_compactor_proposal_manifest`（proposal attempt 内）写入 EventLog，accepted compact 在 `_append_compacted_event`（dispatch governance 内）写入 EventLog。两者使用不同的 `event_type`（`RUNNER_CALL_INPUT_ASSEMBLED` vs `CONTEXT_COMPACTED`），通过 `compaction_operation_id` 关联 → 不会混用

### Identity Mismatch Checks

**验证结论**: ✅ 保护充分

- **Compact candidate → input binding**: `CompactAcceptedTruthV2.validate_input_binding()`（`compaction.py:1761-1775`）检查 `current_input_ref` identity 和 `source_boundary` identity → 在 `build_compacted_payload_input`（`compact_pipeline.py:728`）调用
- **Repair feedback → request binding**: 三层检查：
  1. `_repair_feedback_matches_request`（`compaction_operation.py:1646-1660`）— operation 层
  2. `_repair_feedback_for_request`（`dispatch.py:5803-5822`）— dispatcher 层
  3. `_run_compaction_operation` 起始（`compaction_operation.py:795-798`）— operation 入口
- **Transient pass identity**: `_operation_pass_requests`（`compaction_operation.py:1496-1553`）验证 pass 与 root 的 trigger_source、session_id、run_id、attempt_id、execution_id 完全一致
- **Manifest identity**: `_validate_prepared_proposal_identity`（`compaction_operation.py:1854-1890`）验证 engine run_id 匹配、不使用 ordinary attempt/execution id、provider/model 一致
- **Worker accept CAS**: `_is_worker_acceptable`（`dispatch.py:5843-5873`）验证 Run status、Attempt status、dispatch record status、worker_accept 和 cancelled event —— 防止 double dispatch

### LLM Governance Field Leaks

**检查范围**: 所有 LLM-facing material（compact prompt、repair feedback、RunInput messages）

**验证结论**: ✅ 未发现治理字段泄漏

- **CompactMaterialPack**: `llm_json()`（`compaction.py:2170-2182`）剥离 `provenance_map`，只保留五个 section 的 LLM-facing 字段
- **CompactInputV2**: `to_json()`（`compaction.py:1090-1100`）只暴露 `readable_text` 和 `source_kind`，不暴露 `source_refs`
- **ContemporaryEvidenceBlock/CurrentInputAnchor**: `llm_json()` 剥离 `canonical_source_refs` 和 `content_digest`
- **Repair feedback**: `_repair_feedback_prompt_json_vnext`（`llm_compaction.py:680-703`）只投影 `required_action`、`issues`（code/json_path/message/source_labels），不含 `request_digest`、`source_boundary_digest` → 已有测试断言（`test_llm_compaction.py:263-264`）
- **RunInput messages**: `_message_from_material_block`（`compact_pipeline.py:1236-1268`）对 raw-tail 投影使用 LLM-facing renderer，不传递 provenance
- **Compactor input projection**: 写入 manifest 的 `runner_call_projection_artifact_ref/digest/size_bytes` 是内部治理标识，不是 LLM-facing 文本

### Memory/RunInput/Artifact Fork

**验证结论**: ✅ 未发现 fork risk

- **Post-compact re-freeze**: `_start_governed_after_compact` 重新创建 `PreparedRunnerCallCandidate`（`dispatch.py:2619-2633`），使用**最新的** memory projection snapshot（在 `_catch_up_memory_projection_before_candidate` 中已更新）—— 不会出现 compact accepted 后 RunInput 仍使用旧 memory 的分叉
- **Compact artifact → Memory consistency**: accepted compact 的 payload 通过 `CONTEXT_COMPACTED` EventLog → memory projector 的单向投影链；memory 不向 compact artifact 反向写入 → 单向真源，无循环依赖
- **Candidate sizing fork protection**: `_commit_dispatch_candidate_in_transaction`（`dispatch.py:2837-2841`）验证 `sizing.candidate_input_digest == candidate.input_snapshot_digest` 和 `candidate_input_cursor` 一致 → 防止 manifest 与 sizing truth 分叉

### Compat/Schema/Public Surface Drift

**验证结论**: ✅ 未发现漂移

- **无 compat re-export**: diff 中无 `__all__` 新增旧名字别名、无 wrapper/facade 透传
- **无 schema 兼容读取**: v2 types 不使用 v1 compat path；旧 `REPAIR_FEEDBACK_SCHEMA` 已被 v2 替代但未删除（属预存清理债务，非新增遗留）
- **Public surface**: `dayu/host/compaction.py` 新增 `CompactSegmentSelectionScope`、`TurnGroupMembership`、`SelectedBlockProvenance` → 均为 Host-internal 类型，不进入 `dayu/__init__` 或 public API
- **Frozen baseline digest**: 三份 baseline SHA-256 保持不变（controller adjudication 已确认）

### God Helper / Dual Ownership

**验证结论**: ✅ 未发现 God helper 或 dual ownership 模式

- **`_dedupe_texts`**（`compact_pipeline.py:1192`）被 4 个 caller 使用 → 属合理共享 helper，不是 God helper
- **`_packed_content_digest`**（`compact_material.py:1674`）被 4 个 caller 使用 → 单一真源，正确
- **MemoryProjectionPolicy 双重用途**: dispatch 将 policy 同时传给 memory projection **和** compaction pipeline → 属合理的单一 policy 多消费者模式，不是 dual ownership（policy 仍是 Memory owner 的真源）
- **`_canonical_text`**（`context_governance.py:733`）被 5 个 caller 使用 → 属共享 canonicalization helper

---

## Single-Slice Test Gap Analysis

### F08：Session Summary Null

- ✅ `test_compact_material.py` 的 owner test 通过 accepted event → production projector → snapshot → canonical JSON round-trip 验证 null 正确处理
- ❌ 未发现: 非空 → null 转换场景的真实 memory projection integration test（即已有旧 summary → compact 输出 null → projector 清空 → 跨进程 reconnect 不再读取旧 summary）——已在 accepted plan 中列为 post-fix scenario obligation `interactive.g06.summary-null`，留待真实 CLI 验证
- 评估: current deterministic validator test 充分；真实 LLM 行为留待 Oracle

### F09：Tool Trace Manifest

- ✅ `test_tool_trace_queries.py` 覆盖 formal resolver 的全部路径（success、invalid→repair→success、exhaustion→fallback）
- ✅ `test_runner_call_hot_payload_contract.py` 验证 compactor-specific hot payload fields
- ✅ `test_compaction_contract.py` 和 `test_public_compact_smoke.py` 更新了 `build_compact_repair_feedback_v2` 的新参数
- ❌ 未发现: legacy compactor 路径（无 `CompactorProposalPreparedCompactor` protocol）的 manifest absence 测试——此 gap 已在 design 中接受（legacy path 不享有正式 Tool Trace identity）
- 评估: owner integration 测试充分；cross-tier fallback 中 manifest 是否被正确记录 → 已有 `test_tool_trace_queries.py` 覆盖

### F10：Turn-Group Atomic Selection

- ✅ `test_turn_group_selection_uses_real_block_count_and_never_splits`（3 blocks，cap=2 items → 整组排除）
- ✅ `test_turn_group_char_cap_accepts_exact_total_and_rejects_one_less`（exact cap 通过，少一字排除）
- ✅ `test_turn_group_budget_preserves_atomic_prefix_after_oversized_middle`（prefix 原子性）
- ✅ `test_turn_group_collective_exclusion_uses_fixed_precedence`（precedence 固定）
- ✅ `test_root_selection_contract_rejects_partial_turn_group_membership`（partial group 被拒绝）
- ✅ `test_root_selected_provenance_mismatch_fails_before_provider_call`（三种 mismatch 参数化）
- ✅ `test_current_input_ref_overlap_fails_before_provider_call`（绕过 pipeline 时的 defense-in-depth）
- ✅ `test_defensive_feedback_mismatch_stops_schedule_with_single_terminal`（feedback binding defense-in-depth）
- ❌ 未发现: **previous_compacted_view blocks 在 `_validate_operation_selected_pack` 中被遗漏**的反例（对应 Finding 1）——无测试证明 forged previous block provenance 会被拦截
- ❌ 未发现: tier 1/2 recovery 中 retained previous blocks 的 provenance 与 root snapshot 一致性的专门测试——当前 `build_tier_recovery_request_plans` 构造的 retained blocks 通过 `transform_previous_compacted_view_pair_for_recovery` 保证一致性，但无 bypass 防御测试
- 评估: core turn-group atomic 测试充分；previous view provenance gap 属 defense-in-depth 缺失

---

## Adversarial Failure Pass

以下各项通过独立 code path 走读验证，**未发现** correctness bug：

### Pre-dispatch → compact material → operation → accept

- Turn-group atomic selection、collective exclusion、strict prefix budget ✅
- SelectedBlockProvenance exact equality verification 在 pipeline（`_validate_segment_against_source_snapshot`）、operation 入口（`_validate_operation_root_request`）、pass queue（`_operation_pass_requests`）三层 ✅
- Same-text/different-ref 保留、same-ref fail-closed 两层验证 ✅
- Excluded mapping sorted copy + MappingProxyType freeze + digest 同源 ✅
- Repair feedback request+source-boundary 双 digest binding 三层 ✅
- Root/transient exact partition 无重叠遗漏 ✅
- Aggregate-root-only durable accept（transient pass 不写 artifact/memory/terminal）✅
- Failed proposal manifest reference 随 rejection 返回（不丢失 audit trail）✅
- Non-repairable contract failure 不调用 compactor（provider count=0）✅

### 异常输入

- 空 material_blocks → `_require_material_block_tuple` fail
- 空 selected_block_ids → `_require_unique_string_tuple` fail（non-empty required）
- 重复 block_id → `_validate_selection_inputs` fail
- turn_group_id 缺失 → `_atomic_material_units` raise
- feedback 不匹配 → operation 层 defense-in-depth raise + dispatcher 层清空
- Transient selection 绑定错误 root digest → `_operation_pass_requests` raise
- provider count=0 仍尝试 compact → `_non_repairable_contract_failure_result` 返回
- budget=None 时 `estimate_post_compact_budget` → 已有 None-safe handler

### 并发

- Compaction CAS（`begin_compaction_terminal_commit_in_transaction`）✅
- Worker accept CAS（`_is_worker_acceptable`）✅
- Post-compact Run status re-read（`_start_governed_after_compact`）✅
- Memory catch-up 在 pre-dispatch 与 post-compact re-freeze 前均执行 ✅

---

## Open Questions

1. **previous_compacted_view provenance gap**（Finding 1）：当前调用路径安全，但 `_validate_operation_selected_pack` 遗漏 previous_compacted_view section。若未来 recovery tier 的 retained previous blocks 被错误标记为 selected_block_provenance 成员（通过 forged request），operation 层防御不完整。是否需要在当前 work unit 修复，还是作为 future defense-in-depth？建议在 closing gate 中裁决为 deferred-with-owner（F10 gate 已有 accepted 裁决，可补充为 minor follow-up）

2. **`_requires_budget_acceptance` 硬编码**（Finding 2）：函数签名暗示 conditional behavior，实际永远返回 `True`。是否计划在 future phase 中根据 request 上下文做 conditional budget gate？

---

## Residual Risk

1. **五条正式 CLI scenarios 未运行**: 按 deepreview skill 禁令未运行。F08（summary null）、F09（formal Tool Trace）、F10（turn-group atomicity）的真实 provider 端到端行为留待后续 Oracle evidence/readiness gate。此风险已在 accepted plan 中明确登记为 post-fix scenario obligations

2. **Previous view provenance gap**（Finding 1）：需 deferred follow-up；当前调用路径安全

3. **Legacy compactor path 无 manifest recording**: F09 design 中已接受的限制；只有 `CompactorProposalPreparedCompactor` protocol 实现才能享有正式 Tool Trace identity。若未来切换 compactor 实现，需确认其实现该 protocol

4. **全树 Ruff lint/format**: F08–F10 pathspec 已 clean；全树既有 debt 不在 scope 内

5. **Single-file coverage**: controller adjudication 报告为 83%–92%（合计 85%）；未独立复验。以上 test gap analysis 为 cross-slice adversarial 检查，非 line-by-line coverage audit

---

## Final Conclusion

**PASS**

本 aggregate cross-slice deep review 对 F08–F10 三片 closure 做了独立 adversarial 检查，重点覆盖：

- F08 prompt → F10 material build → memory 的 semantic null 流 ✅
- F09 manifest → F10 operation 的所有 six 退出路径 manifest coverage ✅
- F08+F09+F10 集成的 stale/late/double terminal、identity mismatch、LLM governance field leak、Memory/RunInput/artifact fork、compat/public surface drift ✅

发现两个 findings：
1. **中 severity**（Finding 1）: `_validate_operation_selected_pack` 遗漏 previous_compacted_view blocks — defense-in-depth gap，当前调用路径安全
2. **低 severity**（Finding 2）: `_requires_budget_acceptance` 硬编码 — maintainability issue

一个 informational observation（Finding 3）：DurableCompactorProposalManifestRecorder 内部创建 PayloadStore。

三个 findings 均不阻塞 ship。core correctness contracts（turn-group atomicity、feedback binding、provenance verification、budget boundedness、LLM governance field isolation）均通过三层或多层 defense 实现，测试覆盖充分。
