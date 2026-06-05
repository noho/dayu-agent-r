# WU-CM-01 Slice B Fix Re-Review (DeepSeek)

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B fix re-review |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| prior artifacts | `docs/reviews/wu-cm-01-slice-b-code-review-mimo.md`、`docs/reviews/wu-cm-01-slice-b-code-review-ds.md`、`docs/reviews/wu-cm-01-slice-b-code-review-controller-adjudication.md`、`docs/reviews/wu-cm-01-slice-b-fix-codex.md` |
| reviewer | DeepSeek (via Claude Code) |
| review date | 2026-06-04 |

## Verdict

**A1/A2 均已关闭，无新增 blocking regression。** Fix 严格按照 Controller adjudication 要求执行：A1 删除了 `context_events.py` 中全部 dead helper 与旧 import，同时保留 vNext fail-closed 拒绝逻辑；A2 将 stale preserved refs merge 测试改为 vNext whole-candidate 语义。270 focused tests 与 pyright 0 errors 独立复现通过，结果可信。

---

## A1 逐项验证: context_events.py 旧 compact payload dead helper / old imports 清理

### 已删除的 dead helper（全部确认不存在）

以下 16 个函数在 `dayu/host/context_events.py` 中已无定义：

- `_range_list_json`
- `_evidence_list_json`
- `_fact_candidate_list_json`
- `_minimum_preserve_candidate_list_json`
- `_evidence_ids`
- `_validate_patch_evidence`
- `_validate_confirmed_subject_patch`
- `_validate_replace_patch_value`
- `_validate_confirmed_subject_item`
- `_validate_fact_candidates`
- `_reject_old_preserved_fact_ref_fields`
- `_validate_minimum_preserve_items`
- `_validate_opaque_ref_text`
- `_validate_opaque_ref_kind`
- `_allowed_opaque_ref_kinds`
- `_validate_quality_check_result`
- `_reject_old_quality_result_fields`

**证据**: `grep` 对上述全部函数名在 `context_events.py` 中命中 0 次。

### 已删除的旧 import（全部确认不存在）

以下旧类型/工具 import 已从 `context_events.py` 移除：

- `CompactionCandidate`
- `EvidenceBackedFactKind`
- `MinimumPreserveItemCandidate`
- `MinimumPreserveReason`
- `canonical_json_dumps`

**证据**: `grep` 对上述符号在 `context_events.py` 中命中 0 次。

当前 `context_events.py:14-17` 仅 import vNext 类型：

```python
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    ConversationCompactOutputVNext,
)
```

### 保留的 vNext fail-closed 逻辑（确认完整保留）

| 符号 | 位置 | 状态 |
|---|---|---|
| `_COMPACTED_OLD_FIELDS` frozenset | `context_events.py:113-124` | 保留，含 9 个旧字段常量 |
| `_reject_old_compacted_fields()` | `context_events.py:451-461` | 保留，遍历 `_COMPACTED_OLD_FIELDS` 拒绝旧字段 |
| 调用点 | `context_events.py:316` | `validate_context_compacted_payload()` 入口首行调用 |
| 旧字段名常量 (`_FIELD_EPISODE_SUMMARY_CANDIDATE` 等) | `context_events.py:55-63` | 保留，被 `_COMPACTED_OLD_FIELDS` 引用 |

**结论**: A1 已完全关闭。旧 dead code 全部删除，vNext fail-closed 防御逻辑完整保留，无过度删除。

---

## A2 逐项验证: stale preserved refs 测试语义修正

### 旧测试名已删除

`test_reactive_multi_pass_merges_only_candidate_preserved_refs` 在 `tests/host/test_compaction_operation.py` 中已不存在。

**证据**: `grep` 对 `merges_only_candidate` 和 `preserved.refs.merge` 在测试文件中命中 0 次。

### 新测试: `test_reactive_multi_pass_uses_last_whole_vnext_fact_tuple`

**位置**: `tests/host/test_compaction_operation.py:675-694`

**Fake compactor**: `_DistinctFactPassCompactor` (lines 306-340)
- 每个 pass 返回不同的 `evidence_backed_facts` tuple
- pass 1: `claim_text="whole vNext fact tuple from pass 1"`
- pass 2: `claim_text="whole vNext fact tuple from pass 2"`

**断言语义**:
```python
assert len(result.accepted_candidate.evidence_backed_facts) == 1
assert result.accepted_candidate.evidence_backed_facts[0].claim_text == (
    "whole vNext fact tuple from pass 2"
)
```
- 验证最终 candidate 只有 pass 2 的 fact tuple，不包含 pass 1 的 fact
- 语义明确是"最后完整 vNext fact tuple 替换"，不是"合并 preserved refs"
- 无旧 `preserved_evidence_backed_fact_refs` 字段引用

**结论**: A2 已完全关闭。测试名、fake compactor、断言三者一致描述 vNext whole-candidate 替换语义，不再残留旧 preserved refs merge 描述。

---

## 独立验证复现

### 270 focused tests

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py \
  tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py \
  tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py \
  tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q
```

**结果**: `270 passed in 1.82s` — 与 fix artifact 声称一致，0 失败。

### pyright

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

**结果**: `0 errors, 0 warnings, 0 informations` — 与 fix artifact 声称一致。

---

## 新增 Blocking Finding

无。

## 未关闭/部分关闭 Finding

无。A1 和 A2 均已完全关闭。

## Observation（非 blocking）

### O1: `test_compaction_operation.py` 残留未使用的旧 compact 类型 import

**位置**: `tests/host/test_compaction_operation.py:20-35`

`CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedPatchOperation`、`PinnedStatePatchCandidate`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`PreservationEvidence` 等旧类型在 import 块中存在，但经全文检查未在当前测试文件中被引用。这些 import 是 Slice B 迁移 fake compactor 到 vNext 后的残留。

**严重性**: 低。仅影响测试文件 import 整洁度，不影响类型安全（pyright 0 errors），不阻塞 Slice B 合入。

**建议**: 可在后续 Slice C/D 或独立清理 PR 中移除。

---

## 综合结论

1. **A1 关闭**: `context_events.py` 旧 dead helper 与旧 import 已全部删除，`_COMPACTED_OLD_FIELDS` / `_reject_old_compacted_fields()` vNext fail-closed 逻辑完整保留。
2. **A2 关闭**: stale preserved refs merge 测试已改为 `test_reactive_multi_pass_uses_last_whole_vnext_fact_tuple`，fake compactor 与断言一致描述 vNext whole-candidate 替换语义。
3. **无新增 blocking regression**: 270 focused tests 全部通过，pyright 0 errors。
4. **270 tests 和 pyright 0 errors 可信**: 独立复现结果与 fix artifact 完全一致。

## Residual Risks（与 fix artifact 一致，无新增）

- vNext `CONTEXT_COMPACTED` 后续 memory durable / projection 消费仍属于 Slice C。
- ordinary RunInputBuilder 对 vNext compacted view 的消费仍属于 Slice D。
- 本次未处理 Controller 明确标为 non-fix 的 `_NO_CONTEXT_BUDGET_POLICY_REF` 观察项。
