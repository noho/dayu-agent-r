# WU-CM-01 Slice A Re-Review — AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | fix re-review |
| slice | Slice A - Compact Contract Closure |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| original review | `docs/reviews/wu-cm-01-slice-a-code-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-cm-01-slice-a-fix-codex.md` |
| reviewer | AgentDS |
| review date | 2026-06-04 |

## Verdict

**fix-accepted** — 3/3 accepted findings (A1/A2/A3) 已完全关闭，0 条新增 blocking finding，0 条部分关闭。

## Accepted Finding Closure Evidence

### A1: `context_governance.__all__` 导出 — CLOSED

- **证据**: `dayu/host/context_governance.py:811` 现在为 `__all__ = ["check_compaction_candidate", "check_conversation_compact_output_vnext"]`。
- **判定**: 完全关闭。函数已声明为模块公共 API，可被 `import *` 与 IDE 自动补全发现。

### A2: vNext label-section allowlists 与 stale-label 判定单一直源 — CLOSED

- **真源位置**: `dayu/host/compaction.py:211-265`
  - `CONVERSATION_COMPACT_SUMMARY_SOURCE_SECTIONS_VNEXT` (line 211)
  - `CONVERSATION_COMPACT_FACT_SOURCE_SECTIONS_VNEXT` (line 219)
  - `CONVERSATION_COMPACT_ANSWER_SOURCE_SECTIONS_VNEXT` (line 224)
  - `CONVERSATION_COMPACT_FORWARD_SOURCE_SECTIONS_VNEXT` (line 229)
  - `CONVERSATION_COMPACT_REFERENCE_SOURCE_SECTIONS_VNEXT` (line 236)
  - `CONVERSATION_COMPACT_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT` (line 243)
  - `_CONVERSATION_COMPACT_STALE_LABEL_PREFIXES_VNEXT` (line 251, module-private)
  - `conversation_compact_label_looks_stale_vnext()` (line 255, public)
- **Consumer 导入证据**:
  - `llm_compaction.py:47-56,89` — 所有常量与函数从 `compaction` 直接 import。
  - `context_governance.py:11-16,35` — 所有常量与函数从 `compaction` 直接 import。
- **旧重复定义已删除**: `llm_compaction.py` 与 `context_governance.py` 中不再包含 `_STALE_LABEL_PREFIXES_VNEXT`、`_looks_like_stale_vnext_label`、`_SUMMARY_SOURCE_SECTIONS_VNEXT` 等旧本地定义。
- **无 compatibility wrapper / re-export / lazy import / old-new bridge**: 全文搜索确认 consumer 模块只有直接 `from dayu.host.compaction import ...` 顶层 import，无 `hasattr`/`getattr` 探测，无兼容性 re-export，无 lazy import seam。
- **`__all__` 导出完整**: `compaction.py:3794-3802` 导出所有 6 个 section allowlist 常量，`compaction.py:3868` 导出 `conversation_compact_label_looks_stale_vnext`。
- **判定**: 完全关闭。contract owner 单一真源约束已满足。

### A3: vNext material mapping 直接边界测试 — CLOSED

`tests/host/test_compact_material.py` 新增 6 个直接边界测试：

| 测试 | 行号 | 覆盖边界 |
|---|---|---|
| `test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor` | 227 | user turn→trace, assistant→answer, evidence→evidence_material, anchor not citable, 旧 section key 不泄漏到 JSON |
| `test_conversation_compact_input_vnext_maps_user_turn_to_trace` | 275 | RAW_USER_TURN 只映射到 trace_material，不混入 answer |
| `test_conversation_compact_input_vnext_maps_assistant_turn_to_answer` | 302 | RAW_ASSISTANT_TURN 只映射到 answer_material，不混入 trace |
| `test_conversation_compact_input_vnext_maps_evidence_to_evidence_material` | 331 | accepted evidence 的正确 tool_name/response_text mapping |
| `test_conversation_compact_input_vnext_previous_view_only_has_fact_blocks` | 364 | previous view 只收 EVIDENCE_BACKED_FACT block；goal 等非 fact stable block 不收入；session_summary/answer_anchors/forward_intents/reference_continuity_items 为 None 或空 tuple |
| `test_conversation_compact_input_vnext_current_anchor_not_citable` | 406 | anchor_label=C1 可读但不在 citable_source_labels；source_section 返回 current_input_anchor |

- **判定**: 完全关闭。所有 5 个 NF-03 要求的边界均已独立覆盖。

## Regression Check

| 检查项 | 结果 | 证据 |
|---|---|---|
| 未引入新 compatibility wrapper | PASS | 全文搜索 `compat\|bridge\|re_export\|re-export\|lazy.import\|old.new\|wrapper\|_DEPRECATED\|_LEGACY\|_OLD` 在 `dayu/host/compaction.py`/`llm_compaction.py`/`context_governance.py`/`compact_material.py` 无新增命中 |
| 未引入新 re-export | PASS | consumer 模块无 `from X import Y as Z` 重命名再导出 |
| 未引入新 lazy import | PASS | 所有 import 均为模块顶层 import |
| 未破坏旧 contract path | PASS | 旧 `check_compaction_candidate` 仍在 `__all__`，旧 `CompactionCandidate`/`CompactionRequest` 类型未修改 |
| 未切换 production operation | PASS | `LLMContextCompactor.compact` 保持旧路径；`compact_vnext` 仍是独立入口 |
| 未修改 design 24.3 contract 语义 | PASS | 所有常量值与原始重复定义一致 |
| 测试 helper 质量 | PASS | `_snapshot_with_goal_and_fact` 有完整中文 docstring、类型注解、利用已有 `_snapshot_with_goal` helper，无 God builder |

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
# Result: 105 passed in 0.32s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations
```

- 105 focused tests 全部通过，含新增 6 个 A3 直接边界测试与之前 99 个已有测试（原 review 时 100 tests，A2 常量收敛后 `llm_compaction.py` 少了一个模块级常量定义相关 import 但测试数不变——新增 5 测试后从 100 → 105）。
- pyright 0 errors: 可信。

## Residual Risks

| 风险 | 状态 | Owner |
|---|---|---|
| D1: `previous_compacted_view` 只映射 evidence-backed facts | 仍 deferred | Slice B/C — 非 Slice A scope |
| Production operation 未切换到 vNext | 仍 intentional | Slice B |
| Memory durable/projection 未切换到 vNext | 仍 intentional | Slice C |
| RunInputBuilder 未切换到 vNext | 仍 intentional | Slice D |
| `_CONVERSATION_COMPACT_STALE_LABEL_PREFIXES_VNEXT` 是 module-private（下划线前缀）— consumer 通过 public `conversation_compact_label_looks_stale_vnext()` 访问，不直接依赖该常量 | 设计正确，非风险 | — |

## Recommendation

Slice A fix 可以推进到下一 gate。A1/A2/A3 全部关闭，无新增 blocking findings，105 focused tests 全部通过，pyright 0 errors。
