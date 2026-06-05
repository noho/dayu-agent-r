# WU-CM-01 Slice B Fix Re-Review (MiMo)

- **日期**: 2026-06-04
- **审查范围**: accepted findings A1/A2 fix closure，新增 blocking regression 扫描
- **设计真源**: `docs/host/design.md`
- **控制文档**: `docs/host/issues-implementation-control.md`
- **Code review artifacts**: `docs/reviews/wu-cm-01-slice-b-code-review-mimo.md`、`docs/reviews/wu-cm-01-slice-b-code-review-ds.md`
- **Controller 裁决**: `docs/reviews/wu-cm-01-slice-b-code-review-controller-adjudication.md`
- **Fix artifact**: `docs/reviews/wu-cm-01-slice-b-fix-codex.md`

---

## Verdict: PASS -- All accepted findings closed, no new blocking regressions

---

## A1: context_events.py -- 旧 compact payload dead helper / old imports 删除 + vNext fail-closed 保留

**状态: CLOSED**

### 证据 -- 旧 dead helper / old imports 已删除

`context_events.py` 仅导入 vNext 类型（lines 14-17）:

```python
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    ConversationCompactOutputVNext,
)
```

MiMo NB-1 原始报告的旧类型（`CompactionCandidate`, `CompactQualityCheckResult`, `EvidenceBackedFactCandidate`, `EvidenceBackedFactKind`, `MinimumPreserveItemCandidate`, `MinimumPreserveReason`, `PinnedPatchOperation`, `PreservationEvidence`）均不存在。`canonical_json_dumps` 亦不存在。

fix-codex 列出的 17 个 dead helper 函数（`_evidence_list_json`, `_fact_candidate_list_json`, `_minimum_preserve_candidate_list_json`, `_validate_patch_evidence`, `_validate_fact_candidates`, `_validate_minimum_preserve_items`, `_validate_quality_check_result`（旧版）, `_reject_old_quality_result_fields`, `_range_list_json`, `_evidence_ids`, `_validate_confirmed_subject_patch`, `_validate_replace_patch_value`, `_validate_confirmed_subject_item`, `_reject_old_preserved_fact_ref_fields`, `_validate_opaque_ref_text`, `_validate_opaque_ref_kind`, `_allowed_opaque_ref_kinds`）全部不存在。仅保留 vNext validator `_validate_quality_check_result_vnext`（lines 498-511）。

### 证据 -- vNext fail-closed reject-list 保留

- `_COMPACTED_OLD_FIELDS` frozenset（lines 113-125）完整，包含全部 9 个旧字段名。
- `_reject_old_compacted_fields()`（lines 451-461）遍历 `_COMPACTED_OLD_FIELDS`，命中旧字段时 raise `ValueError`。
- `validate_context_compacted_payload()` 第一步（line 316）调用该 reject 函数，先于 required-field 校验。
- 旧字段字符串常量（lines 55-63）在文件中各出现恰好 2 次：一次定义，一次放入 frozenset。无其它引用。干净。

---

## A2: test_compaction_operation.py -- 旧 preserved refs merge 测试名/断言改为 vNext whole-candidate 语义

**状态: CLOSED**

### 证据

- 测试 `test_reactive_multi_pass_uses_last_whole_vnext_fact_tuple` 存在于 line 675。docstring: "reactive multi-pass accepts last complete vNext fact tuple"（line 676）。
- 使用 `_DistinctFactPassCompactor`（lines 306-340），每次 pass 返回不同 `evidence_backed_facts`，claim_text 为 `f"whole vNext fact tuple from pass {self.calls}"`。
- 断言（lines 690-693）验证 `len(result.accepted_candidate.evidence_backed_facts) == 1` 且 claim_text == `"whole vNext fact tuple from pass 2"`，确认 last-pass whole-candidate replacement 语义（非旧 preserved-refs merge）。
- 伴随测试 `test_reactive_multi_pass_uses_last_whole_vnext_candidate`（line 697）验证 last whole candidate summary（line 714: `summary_text == "whole vNext candidate from pass 2"`）。
- 测试文件中残留的 `preserved_fact_refs` 引用（lines 1275-1284, 1483）属于无关测试：`test_compaction_request_evidence_inputs_reject_malformed_compacted_payload` 和 `test_compaction_request_evidence_inputs_use_stable_derived_fact_refs`，测试的是读取已有 EventLog payload 数据用于 evidence input 收集，非 A2 所针对的 "preserved refs merge" 行为。

---

## 新增 Blocking Regression 扫描

**结果: 无新增 blocking regression**

| 模块 | 检查结果 |
|------|---------|
| `compact_payload.py` | 仅使用 vNext 类型。两个 old-bridge helper（`preserved_canonical_evidence_refs`, `preserved_fact_refs_summary`，lines 54-95）有明确 docstring 标注仅服务未迁移的 RunInputBuilder（Slice D），不被 production operation/dispatch/engine_ingest 路径调用。 |
| `compaction_operation.py` | `CompactionOperationResult` 字段类型为 `ConversationCompactOutputVNext \| None` 和 `CompactQualityCheckResultVNext \| None`（lines 85-86）。`_compact_vnext()` 强制 `ContextCompactorVNext` 协议（lines 323-325）。无旧 candidate 类型。 |
| `dispatch.py` | `_append_compacted_event()`（lines 1533-1635）使用 `compact_artifact_json_vnext`、`compact_artifact_payload_ref`、`compact_artifact_descriptor_metadata_vnext`、`build_context_compacted_payload`、`COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT`。无 `CompactArtifactWriteRequest` 导入。 |
| `engine_ingest.py` | `_append_reactive_compacted_event()`（lines 1713-1814）使用相同 vNext helper。无 `CompactArtifactWriteRequest` 导入。 |
| `llm_compaction.py` | 保留旧 `compact()` 和新 `compact_request_vnext()` 两个方法，属预期设计——旧方法服务旧 contract 路径，`compact_request_vnext` 是 vNext operation 入口。 |

---

## 测试与类型检查验证

| 项目 | 结果 | 备注 |
|------|------|------|
| pytest | **272 passed**, 1 failed, 5 deselected | 失败测试 `test_call_signature_no_kwargs`（`tests/engine/runners/openai/test_protocol_surface.py:32`）为**预先存在**的失败，与 Slice B 无关——验证方式：`git stash` 后在同一 clean state 复现相同失败。该测试检查 `AsyncOpenAIRunner.call` 签名不含 `request_identity` 参数，属于 Engine Phase 1 OpenAI runner（commit 8393ea80）引入的变更，不在 host/compaction 范围内。 |
| pyright | **0 errors**, 0 warnings, 0 informations | 无类型错误。 |

> 注：测试计数 272 passed 与预期 270 focused tests 略有差异（+2），原因是当前 branch 包含部分非 Slice B 相关测试。Slice B 范围内测试全部通过。

---

## 结论

| 项目 | 判定 |
|------|------|
| A1 | **CLOSED** -- 17 个 dead helper 删除，旧类型导入删除，`_COMPACTED_OLD_FIELDS` / `_reject_old_compacted_fields` fail-closed 保留 |
| A2 | **CLOSED** -- 测试重命名为 vNext whole-candidate 语义，断言验证 last-pass replacement |
| 新增 blocking finding | **无** |
| Residual risk | 低。`compact_payload.py` 中两个 old-bridge helper 将在 Slice D RunInputBuilder 迁移时删除；`llm_compaction.py` 旧 `compact()` 方法将在旧 contract 路径废弃时清理。两者均不影响 Slice B vNext 生产路径。 |
