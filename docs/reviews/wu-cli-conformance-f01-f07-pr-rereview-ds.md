# PR Re-Review: wu-cli-conformance-f01-f07 — Fix Verification

## Scope

- **Mode**: PR fix re-review (同一 PR review gate 的第二轮)
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- **Branch**: `codex/interactive-oracle`
- **Accepted deepreview HEAD**: `c69445c2d22febf056bf54e331912f62b3d5ddcb`
- **Current working tree**: uncommitted fix changes (23 files, +388/-176)
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-pr-rereview-ds.md`
- **Reviewed artifacts**:
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-fix-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-ds.md`

本 re-review 仅复审 Controller 已接受的 3 项 finding 的 uncommitted working-tree fix，不重新打开已被 Controller rejected/deferred 的 finding，也不重复第一轮 full review 的完整 surface。

## Controller Accepted Findings Under Re-Review

| Fix ID | Source | Summary |
|--------|--------|---------|
| PR-M01 | MiMo-01 | `_canonical_candidate` 必须按 immutable root `source_boundary` 顺序 canonicalize `explicitly_dropped_sources` |
| PR-M02 | MiMo-02 | `_close_managed_attachment` 在 delayed recovery join 抛异常时仍必须关闭底层 attachment |
| PR-D01 | DS-D-001 | `CompactionRequest.compact_input` 成为 strict v2 input 唯一 owner；删除 `compact_material` 的重复 projector |

---

## PR-M01: Canonical Drop Order

### 修复内容

**文件**: `dayu/host/context_governance.py` (+5/-2)

`_canonical_candidate` 中 `explicitly_dropped_sources` 从直接传递 `candidate.explicitly_dropped_sources` 改为按 `boundary_order` 排序：

```python
explicitly_dropped_sources=tuple(
    sorted(
        candidate.explicitly_dropped_sources,
        key=lambda drop: boundary_order[drop.source_label],
    )
),
```

### 验证

1. **语义正确性**: `boundary_order` 是由 `accept_compact_candidate_v2` 在调用 `_canonical_candidate` 前从 immutable root `source_boundary` 构造的 `{source_label: index}` 映射。所有 drop labels 已在此前的 `_collect_coverage_issues` 中验证存在于 boundary 中，因此 `boundary_order[drop.source_label]` 的 `KeyError` 风险为零。`sorted()` 的稳定性保证了相同 label（不可能出现，已被 `_collect_coverage_issues` 的 `DUPLICATE_DROP_LABEL` 检查拦截）的确定行为。

2. **完整 round-trip 验证**: 新增测试 `test_accept_owner_canonicalizes_reverse_drops_for_committed_round_trip` (`tests/host/test_compaction_contract.py`) 构造了逆序 multi-drop (T1, E1)：
   - accepted candidate drops 按 root order 变为 (E1, T1)
   - accepted explicitly-dropped coverage 同为 (E1, T1)
   - `build_context_compacted_payload(...)` 通过 strict payload validation
   - `parse_context_compacted_semantic_payload(...)` round-trip 后 candidate 与 coverage 仍精确同源

3. **无 scope drift**: 修复仅触及 `_canonical_candidate` 中的 drops 排序，未修改 frozen candidate schema、drop reason、coverage 定义、persisted parser 规则，也未更改 `session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`、`diagnostics` 的已有排序逻辑。

4. **符号一致性**: 与其他 6 个字段使用相同的 `boundary_order` 机制（`_ordered_labels` 内部使用 `sorted(labels, key=boundary_order.__getitem__)`，drops 使用 `sorted(drops, key=lambda drop: boundary_order[drop.source_label])`），语义等价。

### 状态: **已修复**

---

## PR-M02: Attachment Cleanup

### 修复内容

**文件**: `dayu/host/open_host.py` (+8/-2)

`_close_managed_attachment` 使用 `try/finally` 包裹 delayed recovery join：

```python
try:
    await self._cancel_and_join_delayed_attachment_recovery(
        attachment.session_id
    )
finally:
    await attachment.aclose()
```

### 验证

1. **语义正确性**: `finally` 块保证无论 `_cancel_and_join_delayed_attachment_recovery` 是否抛出异常（包括非 `CancelledError` 的异常），`attachment.aclose()` 都会被调用。原异常通过 `finally` 的正常传播机制继续向 caller 抛出。若 `aclose()` 自身也失败，Python 的 `finally` 语义保证 join 异常优先传播（`aclose()` 异常作为 secondary 附加到 `__context__`）。

2. **资源释放验证**: 新增测试 `test_managed_attachment_close_releases_resource_when_recovery_join_fails` (`tests/host/test_open_host_runtime.py`)：
   - 通过 monkeypatch 注入 `_cancel_and_join_delayed_attachment_recovery` → `RuntimeError("forced delayed recovery join failure")`
   - 使用 `_CloseRecordingAttachment` 记录 `aclose()` 调用次数
   - 断言 `RuntimeError` 正确传播且 `attachment.close_calls == 1`

3. **无 scope drift**: 修复仅添加 `try/finally` 包装。未修改 `_cancel_and_join_delayed_attachment_recovery` 的取消/shield/report_fatal 逻辑，未修改 delayed fatal reporting、health transition、recovery policy，也未处理 Controller 已拒绝的 MiMo-04（double shield、原始异常丢失）。

4. **docstring 更新**: `_close_managed_attachment` 的 `:raises` 从仅描述 `attachment close 失败时透传` 更新为 `delayed recovery join 或底层 attachment close 失败时透传`，准确反映新的异常传播契约。

### 状态: **已修复**

---

## PR-D01: Compact Input Single Owner

### 修复内容

**文件**: `dayu/host/compact_material.py` (-106 lines) + 6 个 consumer 文件

1. **删除重复 projector**:
   - 删除 `conversation_compact_input_vnext_from_material_pack()` 函数（~20 行）
   - 删除 `_source_boundary_v2()` 函数（~55 行）
   - 删除 `_previous_source_kind_v2()` 函数（~20 行）
   - 从 `__all__` 移除 `"conversation_compact_input_vnext_from_material_pack"`
   - 移除了不再需要的 imports（`CompactInputV2`, `COMPACT_INPUT_SCHEMA_V2`, `CompactCurrentInputV2`, `CompactSourceBoundaryEntryV2`, `CompactSourceKindV2`）

2. **迁移所有 active Python consumers** (7 个文件):
   - `dayu/host/compact_artifact.py`: `conversation_compact_input_vnext_from_material_pack(self.compaction_request.material_pack)` → `self.compaction_request.compact_input`
   - `dayu/host/compact_pipeline.py`: 5 处迁移（root_input、pass_input、rebound_input、validate_input_binding）
   - `dayu/host/compaction_operation.py`: 5 处迁移 + diagnostic projector identity 更新
   - `dayu/host/dispatch.py`: 1 处迁移
   - `dayu/host/engine_ingest.py`: 1 处迁移
   - `dayu/host/llm_compaction.py`: 1 处迁移
   - `utils/smoke_host_public_r03_semantic_ownership.py`: 1 处迁移

3. **测试迁移** (7 个测试文件):
   - `tests/host/test_compact_material.py`: 引入 `_compaction_request_for_material_pack()` helper，所有测试改为 `request.compact_input`
   - `tests/host/test_accepted_result_projection.py`: 引入 `_compaction_request_for_material_pack()` helper
   - `tests/host/fake_compaction.py`、`test_compact_pipeline.py`、`test_compaction_cancellation_scope.py`、`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_proactive_compaction_operation.py`: import 清理

### 验证

1. **零残留引用**: 全仓扫描确认三个旧符号在任何 Python 文件中均无引用：
   ```text
   rg 'conversation_compact_input_vnext_from_material_pack|_source_boundary_v2|_previous_source_kind_v2' → 零匹配
   ```

2. **无 wrapper/facade/re-export**: 确认未保留任何兼容性入口。旧符号被完全删除，不是重导出或转发。

3. **语义一致性**: `CompactionRequest.compact_input` (property, `compaction.py:2129-2180`) 是唯一 owner。它从 `CompactMaterialPack` 的冻结四个 material section（previous_compacted_view、trace_material、evidence_material、answer_material）机械投影出 `CompactInputV2`。已删除的 `_source_boundary_v2` 和 `_previous_source_kind_v2` 的映射逻辑与此 property 完全相同。迁移后所有消费者从同一真源读取。

4. **Diagnostic projector identity 更新**: `compaction_operation.py` 中的 `_DIAGNOSTIC_PARSER_COMPACT_INPUT_PROJECTOR` 从 `"conversation_compact_input_vnext_from_material_pack"` 更新为 `"CompactionRequest.compact_input"`，准确反映新 owner。

5. **`__all__` 同步**: `compact_material.py` 的 `__all__` 已移除 `"conversation_compact_input_vnext_from_material_pack"`。

6. **无 scope drift**: 仅删除重复代码和迁移消费者。未修改 `CompactionRequest.compact_input` 的 property 实现、未新增函数、未修改变更范围外的模块行为。

### 状态: **已修复**

---

## New Findings

逐项检查三个 fix 是否引入 correctness、semantic ownership、resource cleanup 或 scope drift 回归：

### PR-M01: 无新 finding

- `boundary_order[drop.source_label]` 的安全性由 `_collect_coverage_issues` 的前置 `UNKNOWN_SOURCE_LABEL` 检查保证。在 `_canonical_candidate` 被调用前，所有 drop labels 已通过 boundary 存在性验证。
- `sorted()` 的 key 函数在 duplicate label 场景下不会抛出（duplicate 已被 `_collect_coverage_issues` 的 `DUPLICATE_DROP_LABEL` 拦截）。
- 修复与同函数中其他 6 个字段的 canonicalization 模式一致。

### PR-M02: 无新 finding

- `finally` 中的 `await attachment.aclose()` 如果自身失败，Python 的 `finally` 语义保证原始 join 异常优先传播，`aclose()` 异常被附加到 `__context__`。这符合 Controller 的修复要求："正确传播失败"。
- `_CloseRecordingAttachment` 的 `aclose()` 不会抛出，因此测试中不存在双重异常场景。生产环境中 `aclose()` 的实现是 durable attachment 的 `aclose()`，其异常处理由 durable 层负责。

### PR-D01: 无新 finding

- `_compaction_request_for_material_pack()` helper 在 `test_compact_material.py` 和 `test_accepted_result_projection.py` 中各定义一次（模块级私有函数）。这不构成语义重复——两者服务于不同测试模块的不同 fixture 需求，且各自只在其模块内使用。
- `compact_input` property 在 `compaction.py` 中每次访问时重新计算（Controller 已在 DS-D-007 中 rejected 此项为 non-issue）。迁移后的消费者调用模式与迁移前完全一致（每次需要 `CompactInputV2` 时读取一次），没有引入额外的重复计算。
- 所有 consumer 迁移均为机械替换（`conversation_compact_input_vnext_from_material_pack(request.material_pack)` → `request.compact_input`），无逻辑变更。

### 整体: 无新 finding

三个 fix 均精确限定在 accepted finding 的修复范围内，未引入回归、scope drift 或新的 correctness/semantic ownership/resource cleanup 问题。

---

## Residual Risks

1. **既有 cancel-watchdog test-order timing flake**: Fix artifact 报告首轮 affected suite 为 452 passed / 1 failed（`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`），隔离与完整复跑通过。此次 timing flake 的 root cause 未被 PR-M02 fix 触及（也不应由 PR-M02 触及），归属既有 Host test-runtime owner。

2. **既有 phase5 scheduler/test races**: 6 个 race 已在 clean base 复现，非本次 fix 引入。

3. **未重新运行 full-real provider matrix**: 本轮三项修复均为 deterministic Host owner 修复，不改变 provider/tool/frozen scenario 行为。full-real evidence 已在 PR 190 前序 gate 中留存。

4. **GitHub zero checks**: 没有 CI 配置，无法声称 CI pass。本地验证证据（453 passed affected suite、0 pyright errors、active Python inventory clean）是独立证据。

---

## Gate Verdict

三项 Controller accepted findings 均已完整修复，无新 finding，无 scope drift：

| Fix ID | 最终状态 | 关键证据 |
|--------|---------|---------|
| PR-M01 | **已修复** | `_canonical_candidate` drops 按 root boundary 排序；round-trip 测试覆盖逆序 multi-drop → accept → payload → parse 全链路 |
| PR-M02 | **已修复** | `_close_managed_attachment` 使用 try/finally；测试验证 join 失败时 `aclose()` 仍被调用一次且原异常传播 |
| PR-D01 | **已修复** | 全仓零残留引用；7 个 production consumer + 7 个 test/smoke 全部迁移到 `request.compact_input` |

## READY-FOR-CONTROLLER-PR-REREVIEW-ADJUDICATION
