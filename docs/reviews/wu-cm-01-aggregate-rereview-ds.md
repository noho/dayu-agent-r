# WU-CM-01 Aggregate DeepReview Re-Review

**审查目标**: Controller Adjudication accepted findings 修复完成度复核  
**审查范围**: F-1 (README), F-2 (run_input.py), F-3 (test_public_compact_smoke.py) — 仅 accepted findings  
**审查分支**: `phaseflow/wu-cm-01`  
**审查日期**: 2026-06-04  
**前序 artifact**: `docs/reviews/wu-cm-01-aggregate-deepreview-controller-adjudication.md`  
**修复 artifact**: `docs/reviews/wu-cm-01-aggregate-deepreview-fix-codex.md`

---

## Verdict

**PASS** — 全部 3 个 accepted findings 修复完成，无新问题引入。

---

## Findings

### F-1 [ACCEPTED → VERIFIED] — README.md 旧术语已清除

**文件**: `README.md:35`  
**裁决**: PASS

**变更** (git diff 确认):
```diff
- Durable memory / Retrieval layer（ Memory只实现了working memory 和 episode summary ）。
+ Durable memory / Retrieval layer（Memory 已落地五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent）。
```

**验证**:
- `working memory` 全文搜索：README.md 无匹配
- `episode summary` 全文搜索：README.md 无匹配
- 五类 session memory 术语与 design.md / vNext contract 一致

**违规检查**: 无。新旧术语未并存，仅替换为当前落地事实。

---

### F-2 [ACCEPTED → VERIFIED] — run_input.py 旧 compact payload reader 已完全替换

**文件**: `dayu/host/run_input.py`  
**裁决**: PASS

**已删除**:
- `_optional_summary_text_from_compacted_payload()` 函数体
- `_preserved_fact_refs_summary()` 函数体
- `_preserved_canonical_evidence_refs()` 函数体
- `_optional_text_list_field()` 宽容读取辅助函数
- 旧字段常量: `_PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE`, `_PAYLOAD_FIELD_CANDIDATE_ID`, `_PAYLOAD_FIELD_GOAL`, `_PAYLOAD_FIELD_OPEN_QUESTIONS`, `_PAYLOAD_FIELD_USER_CONSTRAINTS`, `_PAYLOAD_FIELD_PRESERVED_FACT_REFS`, `_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS`, `_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS`

**已新增** (vNext-aware reader):
- `_accepted_evidence_mapping_refs()` (line 2643) — 只读 `accepted_evidence_mapping_refs`，缺失或非法类型抛 `HostDurableError`
- `_vnext_compact_candidate_summary()` (line 2658) — 从 `accepted_candidate` 渲染 bounded 摘要
- `_optional_session_summary_text()` (line 2697) — 只读 vNext `session_summary.summary_text`
- `_required_mapping_field()`, `_required_mapping_list_field()`, `_required_text_list_field()` — fail-closed 辅助函数
- vNext 字段常量: `_PAYLOAD_FIELD_ACCEPTED_CANDIDATE`, `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS`, `_PAYLOAD_FIELD_SCHEMA_VERSION`, `_PAYLOAD_FIELD_SESSION_SUMMARY`, `_PAYLOAD_FIELD_SUMMARY_TEXT`, `_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS`, `_PAYLOAD_FIELD_ANSWER_ANCHORS`, `_PAYLOAD_FIELD_FORWARD_INTENTS`, `_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS`

**消费点更新**:
- `DurableCompactArtifactProvider.__init__` docstring: `episode summary` → `compact candidate` (line 1228, 1240)
- `CompactArtifactView.represented_evidence_refs` (line 1308): `_preserved_canonical_evidence_refs(payload)` → `_accepted_evidence_mapping_refs(payload)`
- `_compact_artifact_message_content()` (lines 2628-2640): SystemMessage 文案从旧 `preserved_fact_refs=/episode_summary=` 改为 vNext `accepted_evidence_mapping_refs=/accepted_candidate=`

**违规检查**:
- 无兼容读取旧 payload 路径: ✅ (`_optional_text_list_field` 已删除，`_required_text_list_field` 对非法元素 fail-closed)
- 无旧 field alias 保留: ✅ (全部旧常量已删除)
- 无 `extra payload`: ✅
- 无 `hasattr`/`getattr` seam: ✅
- 无 god function/builder: ✅ (新增函数均为模块级私有单职责函数)

---

### F-3 [ACCEPTED → VERIFIED] — test_public_compact_smoke.py 命名已统一

**文件**: `tests/host/test_public_compact_smoke.py`  
**裁决**: PASS

**变更** (git diff 确认):
| 位置 | 旧 | 新 |
|------|----|----|
| Line 155 docstring | `缺 evidence_input` | `缺 evidence_material` |
| Line 208 变量名 | `evidence_input` | `evidence_material` |
| Line 682 docstring | `evidence_input` | `evidence_material` |
| Line 683 returns | `evidence_input` | `evidence_material` |
| Line 684 raises | `evidence_input` | `evidence_material` |
| Line 690 error message | `evidence_input is empty` | `evidence_material is empty` |

**验证**:
- `evidence_input` 全文搜索 test_public_compact_smoke.py: 无匹配
- JSON key 保持 `evidence_material` (已是 vNext 正确 key，未改动)
- 测试逻辑仍读取 vNext `evidence_material`: ✅

---

### test_run_input_builder.py [F-2 伴随验证] — vNext reader 测试覆盖完整

**文件**: `tests/host/test_run_input_builder.py`  
**裁决**: PASS

**变更**:
- 旧测试 `test_compact_artifact_preserved_fact_refs_reads_canonical_evidence_key` → 新测试 `test_compact_artifact_reader_uses_vnext_evidence_mapping_refs` (line 1398)
- import 更新: `_preserved_fact_refs_summary` → `_accepted_evidence_mapping_refs` + `_vnext_compact_candidate_summary`
- 测试 payload 使用纯 vNext 字段: `accepted_candidate` (含 `schema_version`, `session_summary`, `evidence_backed_facts`, etc.) + `accepted_evidence_mapping_refs`
- `_compact_payload` helper docstring: `episode summary` → `session summary` (line 3526)

**违规检查**:
- 无保留旧测试兼容旧 payload: ✅ (旧测试完全替换)
- 无兼容性测试逻辑: ✅

---

## 验证命令与结果

### 测试

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q
```

结果: `47 passed, 1 skipped in 1.03s`

### 类型检查

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果: `0 errors, 0 warnings, 0 informations`

### 空白检查

```bash
git diff --check
```

结果: 无输出 (无空白问题)

---

## 范围外确认

以下 rejected findings 未被修改 (scope respect verified):

- **F-4** `context_events.py` 旧字段 fail-closed 常量: git diff 无变更
- **F-5** `ForwardIntentTypeVNext.OPEN_QUESTION`: git diff 无变更

---

## Residual Risks

1. **非本次 re-review scope 的改动**: `run_input.py` diff 中额外看到的 `_optional_text_list_field` → `_required_text_list_field` 替换，以及新增 `_required_mapping_field` / `_required_mapping_list_field` / `_required_text_list_field` 辅助函数，均为 F-2 修复的自然衍生。这些辅助函数只被新增 vNext reader 使用，无扩散到其他模块的风险。

2. **旧 compact payload 注入到 vNext reader**: 新 reader 对 `accepted_candidate` 和 `accepted_evidence_mapping_refs` 字段使用 fail-closed 语义（缺失或类型非法直接抛 `HostDurableError`）。这与 controller adjudication 中 F-4 的 reject reason（fail-closed 防守层）一致，不构成静默错误路径。

3. **`_compact_artifact_message_content` 文案变更**: SystemMessage 从 "Accepted compact artifact" 改为 "Accepted vNext compact artifact"，同时删除旧 `preserved_fact_refs=` 和 `episode_summary=` 行。这属于符合预期的文案更新，与 vNext contract 对齐。

---

## 总结

Controller adjudication 中全部 3 个 accepted findings 的修复已完成并通过验证：
- F-1: README.md 旧术语已清除，vNext 五类 memory 表述已落地
- F-2: run_input.py 旧 compact payload reader 已完全替换为 vNext-aware reader，无兼容残留
- F-3: test_public_compact_smoke.py 命名已统一为 `evidence_material`

全部测试通过，pyright clean，无 whitespace 问题。无新增违反 design source / AGENTS.md / vNext contract 的问题。
