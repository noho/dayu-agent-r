# P12.6 Aggregate Fix Re-Review — AgentMiMo

日期：2026-05-24
Gate：aggregate deepreview targeted fix re-review
Fix artifact：`docs/reviews/p12-6-aggregate-fix-codex-20260524.md`
Fix diff 范围：`dayu/host/memory.py`、`dayu/host/compaction_evidence.py`、`tests/host/test_memory_projection.py`、`tests/host/test_compaction_operation.py`、`dayu/host/README.md`、`tests/README.md`

---

## Verdict: PASS

DS Finding 1 与 DS Finding 2 均已正确修复，未引入新 blocking findings。原 P12.6 success signals 全部仍然成立。

---

## DS Finding 1 Fix 状态：FIXED

### 审查项：open_questions 与 working_assumptions 是否按 normalized text 去重，去重发生在 budget limit 前，且 deterministic

**PASS — 全部满足。**

1. **open_questions normalized 去重**：`PinnedStateView.__post_init__()` (`memory.py:383-387`) 在原精确去重校验处替换为 `_dedupe_text_tuple_by_normalized_text()`，使用 `_normalized_text()` (casefold + whitespace collapse) 去重，保留 tuple 中较新的原始文本。去重发生在任何下游消费之前，deterministic（输入相同则输出相同）。

2. **working_assumptions normalized 去重**：`_limit_working_assumptions()` (`memory.py:2371`) 先调用 `_dedupe_working_assumptions_by_normalized_summary()` 按 normalized `assumption_summary` 去重，再执行 `policy.max_working_assumptions` limit。去重函数 (`memory.py:2626-2649`) 使用 dict 按 normalized summary 选择 `(event_sequence, item_id)` 最大的 view 保留，然后按 `(event_sequence, item_id)` 排序输出，deterministic。

3. **去重早于 budget limit**：open_questions 去重在 `__post_init__` 中完成，早于任何 pinned limit。working_assumptions 去重在 `_limit_working_assumptions` 内部、policy limit 检查之前执行。

4. **测试覆盖**：
   - `test_pinned_state_open_questions_are_not_duplicated` 验证 normalized 重复项被去重，保留较新原始文本。
   - `test_open_questions_deduplicate_normalized_text_before_pinned_limit` 验证去重先于 pinned limit。
   - `test_working_assumptions_deduplicate_normalized_summary_before_limit` 验证 normalized summary 去重先于 budget limit。

5. **无遗漏**：`_normalized_text()` 已存在于 `memory.py:2598`，去重函数复用该函数，无重复实现。

---

## DS Finding 2 Fix 状态：FIXED

### 审查项：旧 `collect_compaction_request_evidence_inputs` range collector 定义、__all__ 导出、生产/测试引用是否已删除，无兼容 wrapper

**PASS — 全部满足。**

1. **函数定义删除**：`compaction_evidence.py` 中旧 `collect_compaction_request_evidence_inputs` 函数（原 line 152-205）已完整删除，无残留。

2. **`__all__` 清理**：`__all__` (`compaction_evidence.py:524-528`) 只包含 `CompactionRequestEvidenceInputs`、`SelectedEvidenceBlockRef`、`collect_selected_compaction_request_evidence_inputs`，旧函数已移除。

3. **生产代码引用**：`dayu/host/` 中 `rg "collect_compaction_request_evidence_inputs"` 零匹配。

4. **测试代码引用**：`tests/host/` 中 `rg "collect_compaction_request_evidence_inputs"` 零匹配。旧测试 helper `_collect_evidence_ids`、`_collect_fact_refs` 也已删除，替换为 `_collect_selected_evidence_ids`、`_collect_selected_fact_refs`。

5. **无兼容 wrapper**：未引入任何兼容性 re-export、wrapper 或 facade。旧 range-based 测试全部迁移到 selected refs 路径。

6. **模块 docstring 更新**：`compaction_evidence.py` 模块 docstring 已从 "从 bounded EventLog range 中读取" 改为 "按 compact material selection 中的 canonical refs 读取"，语义一致。

7. **`CompactionRequestEvidenceInputs` docstring 更新**：字段 docstring 从 "compact input range 内" 改为 "selected"，语义准确。

---

## 新 Findings 审查

### 无 blocking 或 needs-fix findings。

#### NF1 — INFO：`_working_assumption_dedupe_key` 使用 `(event_sequence, item_id)` 排序

`item_id` 为 string 类型，tiebreaker 使用 lexicographic ordering。当两个不同 `item_id` 的 assumption 具有相同 `event_sequence` 时，保留 lexicographically 较大的 `item_id`。这是 deterministic 的，且实践中同一 `event_sequence` 下出现不同 normalized summary 的 duplicate 概率极低（通常同一 compact 事件内的 assumptions 来源相同）。无运行时影响，仅记录。

#### NF2 — INFO：`_limit_working_assumptions` 中 `first_dropped` 使用线性扫描

`memory.py:2376-2378` 使用 `next(item for item in deduped_items if item.item_id not in kept_ids)` 查找第一个被丢弃的 item。当 `deduped_items` 数量较大时存在线性扫描开销。但 `max_working_assumptions` 通常很小（设计文档中为常数级），实际开销可忽略。

---

## 原 P12.6 Success Signals 验证

| Signal | 状态 |
|--------|------|
| no-compaction recent raw turns continuity | PASS (`test_public_compact_smoke.py`) |
| post-compaction evidence-backed fact reuse | PASS (`test_public_compact_smoke.py`) |
| long user input + minimum preserve resolution | PASS (`test_public_compact_smoke.py`) |
| long tool result from raw evidence (not preview) | PASS (`test_public_compact_smoke.py`) |
| long session multiple compact + bounded memory | PASS (`test_public_compact_smoke.py`) |
| proactive compact with duplicate prompt | PASS (`test_public_compact_smoke.py`) |

全部 6 个 success signal 测试通过，未受影响。

---

## 分层/类型/docstring/README/兼容性约束

**PASS — 无新违规。**

- **类型**：`memory.py`、`compaction_evidence.py` 中无新增 `Any`、`object`、无类型参数或返回值。pyright `0 errors, 0 warnings, 0 informations`。
- **中文 docstring**：新增的 `_dedupe_text_tuple_by_normalized_text`、`_dedupe_working_assumptions_by_normalized_summary`、`_working_assumption_dedupe_key` 均有完整中文 docstring（参数、返回值）。测试 helper `_working_assumption` 亦有完整中文 docstring。
- **README 同步**：`dayu/host/README.md` 更新 Memory 段新增 open_questions / working_assumptions normalized 去重说明，Context Compaction 段将 "range 内" 改为 "selection 没有"，语义准确。`tests/README.md` 新增 "normalized open_questions / working_assumptions 去重" 覆盖说明。无越界写法。
- **兼容性**：零兼容 wrapper、re-export、旧字段残留。

---

## Residual Risks

与原 aggregate review 一致，本次 fix 不引入新 residual：

| 风险 | Owner | 说明 |
|------|-------|------|
| `CompactSegmentSelection.policy_digest` 命名误导 | 后续 phase | 非本次 fix 范围 |
| `build_initial_material_pack()` builder 层 dedupe guard 路径不对称 | 后续 phase | 非本次 fix 范围 |
| proactive / reactive 少数 stale 或状态漂移场景缺 diagnostic | 后续 phase | 非本次 fix 范围 |
| public compact reactive 路径 smoke 测试缺失 | 后续 phase | 非本次 fix 范围 |
| `build_compact_material_pack()` 含 memory snapshot stable input 的显式测试缺失 | 后续 phase | 非本次 fix 范围 |
| `EpisodeSummaryCandidate.source_event_refs` ref 策略不一致 | 后续 phase | 非本次 fix 范围 |
| `_reject_result_preview()` migration guard 可后续清理 | 后续确认后清理 | 非本次 fix 范围 |

---

## 验证命令

```bash
source .venv/bin/activate

# 修复范围测试
pytest tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_compaction_contract.py -q
# 109 passed in 1.39s

# broader 测试（含 success signals）
pytest tests/host/test_public_compact_smoke.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_run_input_builder.py -q
# 126 passed, 1 skipped in 2.96s

# 类型检查
python -m pyright dayu/host/memory.py dayu/host/compaction_evidence.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py
# 0 errors, 0 warnings, 0 informations

# 旧函数残留检查
rg "collect_compaction_request_evidence_inputs" dayu/host/ tests/host/
# 零匹配（仅 review docs 中存在）
```
