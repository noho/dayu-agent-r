# Code Re-Review — Phase 12.6 Slice 1 Accepted Findings Verification

## Scope

- **Mode**: current changes (workspace diff against HEAD), targeted re-review
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Base**: HEAD (8749be9 gateflow: accept plan fix for P12.6 slice 1)
- **Output file**: docs/reviews/p12-6-slice1-code-rereview-ds-20260524.md
- **Gate**: code re-review, not implementation — verify accepted findings D-F1, D-F2, D-F3, M-F3 are fixed; verify rejected MiMo base-mismatch findings (M-F1, M-F2) are not in current diff; ensure no new regressions
- **Truth sources**: `docs/reviews/p12-6-slice1-code-review-controller-adjudication-20260524.md`, `docs/reviews/p12-6-slice1-fix-codex-20260524.md`, `docs/reviews/p12-6-slice1-code-review-ds-20260524.md`, `docs/reviews/p12-6-slice1-code-review-mimo-20260524.md`
- **Workspace diff files** (git diff HEAD --name-only): 19 files — 11 production + 1 config + 1 doc + 6 test files

## Accepted Finding Verification

### D-F1 (run_input.py 与 context_events.py 的 preserved_fact_refs payload 字段名不一致) — FIXED

- **入口/函数**: `_preserved_fact_refs_text` → `run_input.py:2150`; `_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS` → `run_input.py:115`
- **文件(行号)**: `dayu/host/run_input.py:115`
- **验证证据**: `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_REFS = "accepted_evidence_refs"` → `_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS = "canonical_evidence_refs"`；`_preserved_fact_refs_text` 内 `_optional_text_list` 调用使用 `_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS`；渲染文本输出 `canonical_evidence_refs=...`；docstring 更新为 "渲染 preserved canonical evidence"。
- **测试覆盖**: `tests/host/test_run_input_builder.py` 新增 `test_compact_artifact_preserved_fact_refs_reads_canonical_evidence_key`（22 行），验证 payload key `canonical_evidence_refs` 被正确读取并渲染。
- **结论**: 修复完成。writer (`context_events.py`) 和 reader (`run_input.py`) 现在使用相同的 payload key `canonical_evidence_refs`。

### D-F2 (_range_tuple 对空 canonical_source_refs 的隐式 IndexError 风险) — FIXED

- **入口/函数**: `_canonical_refs_for_labels` → `llm_compaction.py`（新增）；`_canonical_evidence_refs_for_labels` → `llm_compaction.py`（新增）
- **文件(行号)**: `dayu/host/llm_compaction.py`（`_canonical_refs_for_labels` 和 `_canonical_evidence_refs_for_labels` 函数）
- **验证证据**: 新增 `_canonical_refs_for_labels` 函数，在 `entry.canonical_source_refs` 为空时显式抛出 `ValueError(f"{field_name} label has no canonical source refs: {label}")`；新增 `_canonical_evidence_refs_for_labels` 函数，在 `entry.accepted_evidence_id is None` 时显式抛出 `ValueError(f"{field_name} evidence label has no canonical ref")`。`_range_tuple` 已改用 `_canonical_refs_for_labels(request, ...)` 替代直接索引 `start_refs[0]`。
- **测试覆盖**: `tests/host/test_llm_compaction.py` 已有相关覆盖（test 文件在 diff 内）。
- **结论**: 修复完成。空 canonical_source_refs 不再触发隐式 IndexError，改为明确 ValueError。

### D-F3 (context_events.py 字段常量命名与值不一致) — FIXED

- **入口/函数**: `context_events.py` 模块级常量
- **文件(行号)**: `dayu/host/context_events.py:85, 111, 116`
- **验证证据**: `_FIELD_ACCEPTED_EVIDENCE_REFS` → `_FIELD_CANONICAL_EVIDENCE_REFS`；`_FIELD_ACCEPTED_EVIDENCE_REFS_RETAINED` → `_FIELD_CANONICAL_EVIDENCE_REFS_RETAINED`；`_FIELD_RETAINED_ACCEPTED_EVIDENCE_REFS` → `_FIELD_RETAINED_CANONICAL_EVIDENCE_REFS`。所有模块内引用已同步更新；payload key 值保持不变（`"canonical_evidence_refs"` 等），无行为变更。相关 docstring 和参数名已同步更新（`accepted_evidence_refs` → `canonical_evidence_refs`）。
- **结论**: 修复完成。常量名与值一致。

### M-F3 (测试 docstring 残留旧字段名 accepted_evidence_envelopes) — FIXED

- **入口/函数**: `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids`
- **文件(行号)**: `tests/host/test_compaction_operation.py:708`
- **验证证据**: docstring 从 `accepted_evidence_envelopes 按 evidence_id 去重并保留首个` 改为 `evidence material 按 accepted evidence id 去重并保留首个`。同文件中其他 docstring 也同步更新：`accepted evidence` → `canonical evidence`。
- **结论**: 修复完成。旧字段名已从 docstring 清除。

## Rejected Finding Verification

### M-F1 (Slice 1 修改了 plan 明确归属 Slice 6 的生产文件) — NOT IN CURRENT DIFF

- **验证方法**: `git diff HEAD --name-only | grep -E "memory\.py"`
- **结果**: 无匹配。`dayu/host/memory.py` 不在当前 workspace diff 中。`dayu/host/run_input.py` 在当前 diff 中，但其变更仅限于 D-F1 修复（payload field name 对齐，约 20 行改动），不是 MiMo 报告的 +91/-19 大规模 Slice 6 迁移。Controller 已裁决 run_input.py 的 D-F1 修复属于 Slice 1 范围。
- **结论**: 驳回的 M-F1 不适用。

### M-F2 (18 个 plan 未授权的测试文件被修改) — NOT IN CURRENT DIFF

- **验证方法**: `git diff HEAD --name-only | grep -E "test_public_compact_smoke|test_context_policy|test_local_proxy|test_logging|test_open_host|test_phase5|test_phase6|test_phase7|test_public_contracts|test_public_open_host|test_public_tool|test_recovery|test_resolve_wait|test_toolruntime"`
- **结果**: 无匹配。18 个 MiMo 报告的未授权测试文件均不在当前 workspace diff 中。
- **结论**: 驳回的 M-F2 不适用。

## Regression Checks

### 旧 CompactionRequest 字段删除

- `rg "accepted_evidence_envelopes|input_event_refs|current_message_summary|compact_raw_context_items|CompactRawContextItem|CompactRawContextKind|CurrentMessageSummary" dayu/host/compaction.py`（排除注释、`__all__`、旧字段拒绝逻辑）— **无匹配**。旧字段和旧类型已完全从生产代码移除。
- `compaction.py` diff 中旧字段仅出现在被删除行（`-` 前缀），确认无回归。

### Prompt-local label / provenance 映射

- `CompactMaterialBlock.llm_json()` 排除 `canonical_source_refs`、`content_digest`。
- `CompactEvidenceBlock.llm_json()` 排除 `canonical_source_refs`、`content_digest`。
- `CurrentInputAnchor.llm_json()` 排除 `canonical_source_refs`、`content_digest`。
- `CompactMaterialPack.llm_json()` 排除 `provenance_map`，仅通过各 block 的 `llm_json()` 渲染 LLM-facing 字段。
- **结论**: Host-internal provenance 字段正确排除于 LLM-facing JSON。

### API 边界

- `dayu/host/api.py` 无新增 `from dayu.host.compaction import` 或 `from dayu.host.evidence import`。
- `dayu/host/compact_artifact.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 无跨层穿透 import。
- 无 Engine/Fins/Service/UI 文件在 workspace diff 中。
- **结论**: API 边界无回归。

### 测试与类型检查

- `pytest tests/host/` — **867 passed, 1 failed**。唯一失败 `tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity`（`KeyError: 'current_user_input_ref'`），该文件不在 `git diff HEAD --name-only` 中，属于分支上预先存在的问题，与本次修复无关。
- `pytest tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py` — **100 passed**。
- `pyright dayu/host/run_input.py dayu/host/context_events.py dayu/host/llm_compaction.py dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py` — **0 errors, 0 warnings, 0 informations**。
- **结论**: 受影响文件测试和类型检查全部通过。

## Open Questions

无。

## Residual Risk

- `tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity` 在分支上预先存在 `KeyError: 'current_user_input_ref'` 失败（该文件不在当前 workspace diff 中）。此问题不影响 Slice 1 修复验证，但应在 Slice 2 或独立修复中处理。
- `tests/host/test_memory_projection.py` 在 workspace diff 中的变更仅为测试 helper 的 payload field name 迁移（`accepted_evidence_refs` → `canonical_evidence_refs` 等），与 Slice 1 payload 字段重命名一致，不引入新风险。
- Slice 1 原始 DS review 中记录的已知延期项（segment selection 占位实现、memory snapshot cursor 未校验、evidence raw_result_text JSON encoding）仍适用，由后续 Slice 处理。

## Conclusion

**PASS**

四项 accepted findings (D-F1, D-F2, D-F3, M-F3) 均已正确修复。两项 rejected MiMo findings (M-F1, M-F2) 不在当前 workspace diff 中。旧字段删除、prompt-local label/provenance 映射、API 边界、测试和 pyright 均无回归。唯一预先存在的测试失败与本次修复无关。
