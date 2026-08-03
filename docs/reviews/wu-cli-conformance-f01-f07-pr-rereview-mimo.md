# PR Re-Review: wu-cli-conformance-f01-f07

## Scope

- Mode: PR fix re-review
- PR: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- Branch: `codex/interactive-oracle`
- Base: `main`
- Accepted deepreview HEAD: `c69445c2d22febf056bf54e331912f62b3d5ddcb`
- Re-review date: 2026-08-03
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-pr-rereview-mimo.md`
- Input artifacts:
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-fix-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-ds.md`

## PR-M01: canonical drop order — 已修复

### Verification

**入口**: `_canonical_candidate` → `accept_compact_candidate_v2` → `build_context_compacted_payload` → `parse_context_compacted_semantic_payload`

**Fix diff** (`context_governance.py` L669):
```python
# Before:
explicitly_dropped_sources=candidate.explicitly_dropped_sources,

# After:
explicitly_dropped_sources=tuple(
    sorted(
        candidate.explicitly_dropped_sources,
        key=lambda drop: boundary_order[drop.source_label],
    )
),
```

**Test**: `test_accept_owner_canonicalizes_reverse_drops_for_committed_round_trip`
- 构造 candidate drops 为逆序 `(T1, E1)`
- accept 后验证 `candidate.explicitly_dropped_sources` 为 root order `(E1, T1)`
- 验证 `explicitly_dropped_coverage.source_labels` 为 `(E1, T1)`
- 验证 `build_context_compacted_payload` → `parse_context_compacted_semantic_payload` round-trip 后 candidate 与 coverage 仍精确同源

**Regression check**: 453 affected tests passed, pyright 0 errors.

**Scope drift**: 无。修改仅限 `_canonical_candidate` 的 `explicitly_dropped_sources` 排序，与同函数中其它 6 个字段的 `_ordered_labels` 处理一致。

### Verdict: 已修复

---

## PR-M02: attachment cleanup — 已修复

### Verification

**入口**: `_PublicHostHandle._close_managed_attachment`

**Fix diff** (`open_host.py` L1372-1383):
```python
# Before:
await self._cancel_and_join_delayed_attachment_recovery(attachment.session_id)
await attachment.aclose()

# After:
try:
    await self._cancel_and_join_delayed_attachment_recovery(
        attachment.session_id
    )
finally:
    await attachment.aclose()
```

**Test**: `test_managed_attachment_close_releases_resource_when_recovery_join_fails`
- monkeypatch `_cancel_and_join_delayed_attachment_recovery` 抛出 `RuntimeError`
- 断言 `_close_managed_attachment` 仍抛出同一个 `RuntimeError`
- 断言 `attachment.close_calls == 1`（底层 close 被调用恰好一次）

**Regression check**: 453 affected tests passed, pyright 0 errors.

**Scope drift**: 无。修改仅限 `_close_managed_attachment` 方法体，docstring 更新为说明 join 或 close 失败时均传播异常。

**异常传播验证**: finally 块中的 `attachment.aclose()` 若成功，原 join 异常正常传播。若 `aclose()` 也抛异常，Python 3 会用 finally 异常替换原异常（PEP 3134 `__context__` 链保留）。这是可接受行为——attachment 清洗失败比 join 失败更严重。

### Verdict: 已修复

---

## PR-D01: compact input single owner — 已修复

### Verification

**删除的符号**:
- `compact_material.conversation_compact_input_vnext_from_material_pack`
- `compact_material._source_boundary_v2`
- `compact_material._previous_source_kind_v2`

**迁移的 consumers** (6 处):
| File | Before | After |
|---|---|---|
| `compaction_operation.py` L1062 | `conversation_compact_input_vnext_from_material_pack(request.material_pack)` | `request.compact_input` |
| `compaction_operation.py` L1401 | 同上 | 同上 |
| `compaction_operation.py` L1413 | 同上 | 同上 |
| `compaction_operation.py` L1521 | 同上 | 同上 |
| `dispatch.py` L3008 | 同上 | 同上 |
| `engine_ingest.py` L2791 | 同上 | 同上 |
| `llm_compaction.py` L309 | 同上 | 同上 |
| `compact_pipeline.py` L619 | 同上 | 同上 |
| `compact_pipeline.py` L641 | 同上 | 同上 |
| `smoke_host_public_r03_semantic_ownership.py` | 同上 | 构造 `CompactionRequest` 后用 `compact_input` |

**Diagnostic projector identity**: `_DIAGNOSTIC_PARSER_COMPACT_INPUT_PROJECTOR` 从 `"conversation_compact_input_vnext_from_material_pack"` 改为 `"CompactionRequest.compact_input"`。

**Active source inventory**: `grep -rn "conversation_compact_input_vnext_from_material_pack\|_source_boundary_v2\|_previous_source_kind_v2" dayu/ tests/ utils/` 返回零结果。

**Import cleanup**: `compact_material.py` 不再导入 `CompactInputV2`、`COMPACT_INPUT_SCHEMA_V2`、`CompactCurrentInputV2`、`CompactSourceBoundaryEntryV2`、`CompactSourceKindV2`。

**Regression check**: 453 affected tests passed, pyright 0 errors。

**Scope drift**: 无。删除的函数是 `CompactionRequest.compact_input` property 的重复实现。所有 consumers 机械迁移到同一 owner。未修改 frozen schema、candidate 解析、validation 或 persistence 逻辑。

### Verdict: 已修复

---

## New Findings

无。三项 fix 均为最小化、owner-boundary 修复，未引入 correctness、semantic ownership、resource cleanup 或 scope drift 回归。

## Residual Risks

- 本 re-review 仅验证三项 accepted finding 的 closure 和 fix 自身回归。PR 190 的完整 residual risks（G01-G07、GitHub zero checks、Phase 5 races、renderer target pin）不变，参见 Controller adjudication。
- PR-M02 的 finally 异常替换行为（Python PEP 3134 `__context__` 链）是语言标准行为，不构成本 fix 的 residual risk。

## Gate Verdict

`READY-FOR-CONTROLLER-PR-REREVIEW-ADJUDICATION`
