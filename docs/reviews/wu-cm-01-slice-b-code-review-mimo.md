# WU-CM-01 Slice B Code Review - AgentMiMo

## Verdict

**pass-with-findings**

实现正确完成了 Slice B 的全部目标：production compaction operation/event/artifact 切到 vNext，proactive dispatch 与 reactive engine_ingest accepted closeout 都写 vNext artifact 和 vNext `CONTEXT_COMPACTED` payload，无旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload 或 untyped payload。270 focused tests passed，pyright 0 errors。发现 0 条 blocking finding、3 条 non-blocking finding。

## 验证

| 检查项 | 结果 |
|---|---|
| 270 focused tests passed | 已验证，1.78s |
| pyright 0 errors | 已验证，0 errors / 0 warnings / 0 informations |

## Blocking Findings

无。

## Non-Blocking Findings

### NB-1: `context_events.py` 残留旧类型 import 和未调用旧 helper 函数

**位置**: `dayu/host/context_events.py:16-31, 658-698, 965-992, 1059-1092, 1109-1136, 1169-1203`

**描述**: `context_events.py` 仍然 import 旧类型 `CompactionCandidate`、`CompactQualityCheckResult`、`EvidenceBackedFactCandidate`、`EvidenceBackedFactKind`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PinnedPatchOperation`、`PreservationEvidence`。这些类型仅被以下未调用的私有 helper 函数引用：

- `_evidence_list_json()` (line 658)
- `_fact_candidate_list_json()` (line 671)
- `_minimum_preserve_candidate_list_json()` (line 686)
- `_validate_patch_evidence()` (line 965)
- `_validate_fact_candidates()` (line 1059)
- `_validate_minimum_preserve_items()` (line 1109)
- `_validate_quality_check_result()` (line 1169)

这些函数在 `context_events.py` 内部和整个 `dayu/host/` 包中均无调用点。它们是旧 compact payload validator 的残留，属于 dead code。

**风险**: 低。pyright 通过说明这些 import 被 dead code 消费，不影响类型安全。但违反编码硬约束中"禁止兼容性代码"和"不得引入旧字段 re-export"的精神。

**建议**: 在 Slice C/D 清理阶段删除这些 dead helper 和对应旧 import。不在本 slice 强制要求。

**证据**: `grep -n` 确认这些函数在 `context_events.py` 中只有定义行，无调用行；在 `dayu/host/` 其它模块中无 import。

### NB-2: `engine_ingest.py` reactive closeout 内联计算 accepted_attempt_number

**位置**: `dayu/host/engine_ingest.py:1682`

**描述**: reactive accepted closeout 使用 `len(operation_result.rejected_attempts) + 1` 内联计算 `accepted_attempt_number`，而 `dispatch.py` 已将同一逻辑抽取为 `_accepted_attempt_number()` helper (line 3678)。两处逻辑一致但未共享。

**风险**: 极低。逻辑简单且稳定，未来修改时需同步两处。

**建议**: 可在 Slice C/D 将 `_accepted_attempt_number()` 移到 `compaction_operation.py` 作为 `CompactionOperationResult` 的方法或模块级 helper，供 `dispatch.py` 和 `engine_ingest.py` 复用。

### NB-3: `context_events.py` 旧 `_COMPACTED_OLD_FIELDS` 仍引用旧字段常量

**位置**: `dayu/host/context_events.py:168-180`

**描述**: `_COMPACTED_OLD_FIELDS` frozenset 引用了 `_FIELD_EPISODE_SUMMARY_CANDIDATE`、`_FIELD_PINNED_STATE_PATCH_CANDIDATE`、`_FIELD_PRESERVATION_EVIDENCE`、`_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES`、`_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES`、`_FIELD_PRESERVED_FACT_REFS`、`_FIELD_DROPPED_RANGES`、`_FIELD_SUMMARIZED_RFS`、`_FIELD_EVIDENCE_ANCHORS_RETAINED` 等旧字段常量。这些常量和 `_reject_old_compacted_fields()` 一起用于 vNext payload 校验中拒绝旧字段。

**风险**: 无。这是 intentional 的防御性校验——vNext validator 主动拒绝旧字段，防止旧 payload 误入 vNext 路径。旧字段常量在此处是"拒绝列表"的一部分，不是旧 payload 兼容入口。

**说明**: 此为设计意图确认，不需要修改。

## Review Checklist 逐项验证

### 1. production compaction operation/event/artifact 是否切到 ConversationCompactOutputVNext / CompactQualityCheckResultVNext

**通过**。

- `compaction_operation.py:85-86`: `CompactionOperationResult` 类型字段为 `ConversationCompactOutputVNext | None` 和 `CompactQualityCheckResultVNext | None`。
- `compaction_operation.py:309-325`: `_compact_vnext()` 检查 `ContextCompactorVNext` protocol 并调用 `compact_request_vnext()`。
- `context_events.py:313-368`: `build_context_compacted_payload()` 参数类型为 `ConversationCompactOutputVNext` 和 `CompactQualityCheckResultVNext`，内部 `isinstance` 校验拒绝旧类型。
- `context_events.py:528-576`: `_validate_vnext_candidate_payload()` 和 `_validate_quality_check_result_vnext()` 校验 vNext candidate shape 和 accepted quality result。

### 2. proactive dispatch 与 reactive engine_ingest accepted closeout 是否都写 vNext artifact 和 vNext CONTEXT_COMPACTED payload

**通过**。

- **Proactive** (`dispatch.py:1533-1632`): `_append_compacted_event()` 使用 `compact_artifact_json_vnext()`、`compact_artifact_payload_ref()`、`compact_artifact_descriptor_metadata_vnext()` 和 `build_context_compacted_payload()`。
- **Reactive** (`engine_ingest.py:1713-1814`): `_append_reactive_compacted_event()` 使用完全相同的 vNext helper 集合。
- 两条路径都通过 `COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT` 写 artifact descriptor。

### 3. engine_ingest.py 修改是否仅限 reactive accepted closeout

**通过**。

- 新增 import 仅限 vNext compact payload helper (`compact_payload.py`) 和 vNext compaction types。
- `_append_reactive_compacted_event()` 方法签名从旧 `CompactionCandidate` + `CompactQualityCheckResult` 切到 `ConversationCompactOutputVNext` + `CompactQualityCheckResultVNext`。
- 不再 import `CompactArtifactWriteRequest`。
- 非 closeout 路径（status transition、projection catch-up、RunInputBuilder）未修改。

### 4. compact_payload.py 旧 preserved refs helper 是否只是未迁移 consumer 暂留

**通过**。

- `preserved_canonical_evidence_refs()` (line 54-69): docstring 明确标注"仅保留到 RunInputBuilder 所属 Slice D 切换前"、"vNext operation / dispatch 不调用该函数"。
- `preserved_fact_refs_summary()` (line 72-95): docstring 明确标注"只服务尚未迁移的 RunInputBuilder artifact message"。
- 生产 operation path (`dispatch.py`、`engine_ingest.py`) 不调用这两个函数。

### 5. 是否无旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped payload

**通过**。

- `CONTEXT_COMPACTED` payload 不含 `evidence_backed_fact_candidates`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preserved_*` 或其它旧字段。
- `_reject_old_compacted_fields()` (context_events.py:515-525) 主动拒绝旧字段。
- 无 lazy import seam、字符串字段探测、`extra` payload 字段或 untyped event payload。
- 无旧 candidate 到 vNext / vNext 到旧 candidate 的 adapter。

### 6. tests 是否覆盖 operation/event/proactive/reactive closeout

**通过**。

- `test_compaction_operation.py`: 运行 compaction operation 循环、quality reject、hard threshold、cancellation。
- `test_context_compact_events.py`: vNext payload builder/validator、旧字段拒绝。
- `test_dispatch_scheduler.py`: proactive compact accepted/failed closeout。
- `test_engine_ingest_mapping.py`: reactive accepted closeout 断言 vNext payload schema、无旧 `preserved_fact_refs` 字段、payload descriptor、artifact media type、artifact JSON schema 和 candidate digest。fake compactor 已迁移到 `compact_request_vnext`。

### 7. README 更新是否符合职责

**通过**。

- `dayu/host/README.md`: Context Compaction 段落更新，同步 vNext candidate/artifact/`CONTEXT_COMPACTED` closeout 事实。符合 Host README 职责。
- `tests/README.md`: 测试覆盖说明更新，移除旧 compact 消费描述，同步为 vNext closeout 覆盖。符合 tests README 职责。

## Residual Risks

1. **vNext compact event 已提交但 memory durable/projection 尚未消费**: 分类为 covered by later approved slice，owner 是 Slice C。
2. **ordinary prompt assembly 与 public smoke 尚未完成**: 分类为 covered by later approved slice，owner 是 Slice D / E。
3. **`context_events.py` dead code 清理**: 旧 helper 函数和旧 import 可在 Slice C/D 清理，owner 是 Slice D cleanup。
