# WU-CM-01 Slice A Re-review — AgentMiMo

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice A re-review |
| slice | Slice A - Compact Contract Closure (fix) |
| design source | `docs/host/design.md` section 24.3 |
| control doc | `docs/host/issues-implementation-control.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-cm-01-slice-a-fix-codex.md` |
| prior code reviews | `docs/reviews/wu-cm-01-slice-a-code-review-mimo.md`; `docs/reviews/wu-cm-01-slice-a-code-review-ds.md` |
| reviewer | AgentMiMo |
| review date | 2026-06-04 |

## Verdict

**pass** — 0 条未关闭 accepted findings，0 条新增 blocking regression。

Slice A accepted findings A1 / A2 / A3 均已正确关闭，fix 范围未超出 controller 裁决边界，未引入新 blocking regression。

## Accepted Findings Closure

### A1: `context_governance.__all__` 导出 — ✅ CLOSED

- **裁决要求**: 将 `check_conversation_compact_output_vnext` 加入 `dayu/host/context_governance.py` 的 `__all__`。
- **直接证据**: `context_governance.py:808`（diff 行）将 `__all__` 从 `["check_compaction_candidate"]` 改为 `["check_compaction_candidate", "check_conversation_compact_output_vnext"]`。
- **结论**: 已正确关闭。模块公共契约完整。

### A2: vNext label-section allowlists 与 stale-label 判定单一真源 — ✅ CLOSED

- **裁决要求**: 将共享 vNext label-section allowlists 和 stale-label helper 集中到 `dayu/host/compaction.py`，`llm_compaction.py` 和 `context_governance.py` 直接 import，不得新增兼容 wrapper / re-export / lazy import / old-new bridge。
- **直接证据**:
  - `compaction.py` 新增公开常量 `CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT`，以及私有常量 `_CONVERSATION_COMPACT_STALE_LABEL_PREFIXES_VNEXT` 和公开 helper `conversation_compact_label_looks_stale_vnext`。
  - `llm_compaction.py` 从 `compaction.py` import 上述常量和 helper（行 49、56、68、89），本地无重复定义。
  - `context_governance.py` 从 `compaction.py` import 上述常量和 helper（行 13、16、27、35），本地无重复定义。
  - 全文 grep 确认：旧 `_SUMMARY_SOURCE_SECTIONS_VNEXT`、`_FACT_SOURCE_SECTIONS_VNEXT`、`_STALE_LABEL_PREFIXES_VNEXT`、`_looks_like_stale_vnext_label` 在 `llm_compaction.py` 和 `context_governance.py` 中均已不存在。
  - 未新增 `hasattr`/`getattr` 探测、lazy import、re-export 或兼容 wrapper。
- **结论**: 已正确关闭。vNext label contract 真源唯一，parser 和 accept barrier 均从 contract owner `compaction.py` 直接 import。

### A3: vNext material mapping 直接边界测试 — ✅ CLOSED

- **裁决要求**: 在 `tests/host/test_compact_material.py` 新增覆盖 user turn → trace、assistant → answer、evidence → evidence_material、previous view fact-only、current_input_anchor not citable 的直接测试。
- **直接证据**: 新增 6 个测试函数：
  - `test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor` — 综合覆盖 user turn → `H1` trace、assistant turn → `H2` answer、evidence → `E1` evidence_material、current anchor not in citable labels。
  - `test_conversation_compact_input_vnext_maps_user_turn_to_trace` — 断言 `RAW_USER_TURN` → `trace_material`，`RAW_ASSISTANT_TURN` 不进入 trace。
  - `test_conversation_compact_input_vnext_maps_assistant_turn_to_answer` — 断言 `RAW_ASSISTANT_TURN` → `answer_material`。
  - `test_conversation_compact_input_vnext_maps_evidence_to_evidence_material` — 断言 accepted evidence → `evidence_material`。
  - `test_conversation_compact_input_vnext_previous_view_only_has_fact_blocks` — 断言 previous view 只含 `EVIDENCE_BACKED_FACT` block，`session_summary`/`answer_anchors`/`forward_intents`/`reference_continuity_items` 均为空或 None。
  - `test_conversation_compact_input_vnext_current_anchor_not_citable` — 断言 `anchor_label == "C1"`、`"C1" not in citable_source_labels`、`source_section("C1").value == "current_input_anchor"`。
- **结论**: 已正确关闭。5 项裁决要求全部有独立直接测试覆盖。

## Deferred Finding Status

### D1: `previous_compacted_view` 仅映射 evidence-backed facts

- **状态**: deferred，非 Slice A defect。
- **本次 fix 未处理**: 正确，不在 A1/A2/A3 范围内。
- **owner**: Slice B/C。

## 新增 Blocking Regression 检查

### 旧路径退化

| 检查项 | 结果 |
|---|---|
| 旧 `CompactionCandidate` / `CompactionRequest` 未修改 | pass — diff 无旧类型改动 |
| 旧 `check_compaction_candidate()` 未修改 | pass — 保留原逻辑 |
| 旧 `LLMContextCompactor.compact()` 未修改 | pass — 仍走旧 request → candidate 路径 |
| 旧 `CompactMaterialPack` 字段未变 | pass — `stable_input`/`history_input`/`evidence_input` 不变 |
| 旧 `build_compact_material_pack()` 未修改 | pass — 无行为变更 |

### 分层约束

| 检查项 | 结果 |
|---|---|
| `compaction.py` 不反向依赖上层 | pass — 无 `llm_compaction`/`context_governance` import |
| `llm_compaction.py` 只从 `compaction.py` import contract 类型 | pass |
| `context_governance.py` 只从 `compaction.py` import contract 类型 | pass |
| `compact_material.py` 只从 `compaction.py` import contract 类型 | pass |
| 未修改 `dayu/service/`、`dayu/ui/`、`dayu/engine/`、`dayu/fins/` | pass — diff 只涉及 `dayu/host/` 和 `tests/host/` |

### 类型 / 编码约束

| 检查项 | 结果 |
|---|---|
| pyright 0 errors | pass — `0 errors, 0 warnings, 0 informations` |
| 无新增 `object`/`Any` 类型 | pass |
| 无 `hasattr`/`getattr` 桥接 | pass |
| 全部 vNext dataclass frozen+slots | pass |
| 完整中文 docstring | pass |

### `compaction.py` `__all__` 完整性

- `compaction.py` 的 `__all__` 已包含新增公开常量和 helper（行 3796、3802、3868），包括 `CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT`、`CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT`、`conversation_compact_label_looks_stale_vnext` 等。
- 结论：contract owner 模块的公共契约导出完整。

## 105 Focused Tests 可信性

```bash
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
# Result: 105 passed in 0.32s
```

- 测试数量从 code review 时的 100 增至 105，增量来自 A3 新增的 5 个 material mapping 直接测试（第 6 个 `test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor` 是原有测试扩展，已在 code review 前存在）。
- 实际新增测试函数：5 个（user turn → trace、assistant → answer、evidence → evidence_material、previous view fact-only、current anchor not citable），与 A3 裁决要求一一对应。
- 测试结果 105 passed，0 failed，0 error。
- 结论：105 focused tests 可信。

## Pyright 0 Errors 可信性

```bash
python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations
```

- fix 只新增了从 `compaction.py` 到 `llm_compaction.py`/`context_governance.py` 的常量 import 和 `compact_material.py` 中的 helper 函数与测试，未引入新的类型边界。
- 结论：pyright 0 errors 可信。

## Residual Risks

| 风险 | 分类 | owner |
|---|---|---|
| `previous_compacted_view` 仅映射 evidence-backed facts，不含 summary/anchor/intent/continuity | deferred D1 | Slice B/C |
| vNext contract 未接入 production operation | Slice A approved boundary | Slice B |
| Memory durable/projection 未切换 vNext | approved later slice | Slice C |
| RunInputBuilder 未切换 vNext | approved later slice | Slice D |

## 结论

Slice A fix 已正确关闭 accepted findings A1 / A2 / A3，未引入新 blocking regression。fix 范围严格限于 controller 裁决边界内：`__all__` 导出、vNext label contract 去重、material mapping 直接测试。105 focused tests 全部通过，pyright 0 errors。Slice A 可进入下一 gate。
