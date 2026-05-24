# P12.6 Aggregate Fix Re-Review — AgentDS

日期：2026-05-25
Gate：aggregate fix re-review
范围：AgentCodex fix artifact `docs/reviews/p12-6-aggregate-fix-codex-20260524.md` 对应的 diff
审查基准：MiMo review `p12-6-aggregate-deepreview-mimo-20260524.md`、DS review `p12-6-aggregate-deepreview-ds-20260524.md`

---

## Verdict: PASS

DS Finding 1 和 DS Finding 2 均已修复。无 new findings。341 passed, 1 skipped, pyright 0 errors。原始 P12.6 success signals 全部保持。

---

## DS Finding 1 — open_questions / working_assumptions normalized 去重：FIXED

**open_questions:**

- `PinnedStateView.__post_init__()` (memory.py:383-387) 调用 `_dedupe_text_tuple_by_normalized_text(self.open_questions)`。
- `_dedupe_text_tuple_by_normalized_text()` (memory.py:2606-2623) 使用 `_normalized_text()`（casefold + whitespace collapse），逆序遍历保留较新元素，维持原始相对顺序。deterministic。
- 去重发生在 `__post_init__` 内，早于任何 budget limit。

**working_assumptions:**

- `_limit_working_assumptions()` (memory.py:2371) 在 policy limit 前调用 `_dedupe_working_assumptions_by_normalized_summary(items)`。
- `_dedupe_working_assumptions_by_normalized_summary()` (memory.py:2626-2649) 对 `assumption_summary` 做 normalized text 去重，相同 normalized summary 保留 `(event_sequence, item_id)` 更大的 view，最后按 `(event_sequence, item_id)` 排序输出。deterministic。
- 去重发生在 budget limit 之前。

**测试覆盖:**

- `test_open_questions_deduplicate_normalized_text_before_pinned_limit` (test_memory_projection.py:1092)：3 个 question 中 2 个为 normalized 重复，max_pinned_items=2 约束下断言去重后保留较新 raw text 且数量先于 limit 裁剪。PASS。
- `test_working_assumptions_deduplicate_normalized_summary_before_limit` (test_memory_projection.py:1029)：3 个 assumption 中 2 个 normalized summary 重复，max_working_assumptions=2 约束下断言去重后保留较新 view 且原始 raw text 不丢失。PASS。

---

## DS Finding 2 — 旧 range collector 删除：FIXED

- `collect_compaction_request_evidence_inputs` 在 `dayu/host/` 中：**零匹配**。
- `collect_compaction_request_evidence_inputs` 在 `tests/` 中：**零匹配**。
- `__all__` (compaction_evidence.py:524-528)：仅含 `CompactionRequestEvidenceInputs`、`SelectedEvidenceBlockRef`、`collect_selected_compaction_request_evidence_inputs`。旧函数已移除。
- 无兼容 wrapper、re-export、deprecated alias。
- `test_compaction_operation.py` 全线使用 `collect_selected_compaction_request_evidence_inputs`（line 34）。

---

## New Findings

无 new findings。

逐项检查：

| 检查项 | 状态 |
|--------|------|
| 类型约束（无 `Any`/`object`/无类型参数） | PASS — pyright 0 errors |
| `hasattr`/`getattr` 使用 | PASS — 变更代码中零使用 |
| 中文 docstring（新函数全覆盖） | PASS — `_dedupe_text_tuple_by_normalized_text`、`_dedupe_working_assumptions_by_normalized_summary`、`_working_assumption_dedupe_key` 均有完整中文 docstring |
| 反向依赖 | PASS — 无 `dayu.service`/`dayu.ui`/`dayu.fins` 导入 |
| 兼容 wrapper | PASS — 无旧字段 re-export 或兼容别名 |
| README 同步 | PASS — `dayu/host/README.md` 新增 normalized open_questions/working_assumptions 去重说明；`tests/README.md` 同步更新 |

---

## 原始 P12.6 Success Signals 复核

| # | 信号 | 状态 |
|---|------|------|
| 1 | EventLog ledger dump 不进入 compactor prompt | 保持 PASS |
| 2 | `result_preview` 不读取/生成/作为 evidence input | 保持 PASS |
| 3 | event id/digest/cursor 不作为 LLM semantic input | 保持 PASS |
| 4 | prompt-local labels + Host provenance map | 保持 PASS |
| 5 | Context Governance lifecycle/cancellation/commit barrier | 保持 PASS |
| 6 | memory projection bounded deterministic working set | **增强** — open_questions/working_assumptions 增加 normalized dedup |
| 7 | public compact smoke 覆盖 success signals | 保持 PASS |
| 8 | 分层/类型/docstring/README/无兼容 wrapper | 保持 PASS |

---

## Residual Risks

DS Finding 3-10 及 MiMo INFO 按 Controller 裁决保留，不在本次 fix scope：

| 风险 | 来源 |
|------|------|
| `CompactSegmentSelection.policy_digest` 命名误导 | DS F3 |
| `build_initial_material_pack()` builder dedupe guard 不对称 | DS F4 |
| Proactive/reactive stale 路径缺 diagnostic | DS F5/F6 |
| Reactive smoke 缺失 | DS F7 |
| `CONTEXT_COMPACTED` EventLog 断言分散 | DS F8 |
| `build_compact_material_pack` 全 section 测试缺失 | DS F9 |
| `EpisodeSummaryCandidate.source_event_refs` ref 策略不一致 | DS F10 |
| `_reject_result_preview()` migration guard 保留 | MiMo F1 |

---

## 验证记录

```bash
# 全量测试
pytest tests/host/test_memory_projection.py tests/host/test_compaction_operation.py \
  tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py \
  tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py \
  tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py \
  tests/host/test_compact_artifact_store.py tests/host/test_context_budget.py \
  tests/host/test_toolruntime_accept_barrier.py -q
# → 341 passed, 1 skipped in 6.51s

# 类型检查
python -m pyright dayu/host/ tests/host/
# → 0 errors, 0 warnings, 0 informations
```
