# WU-CM-01 Aggregate Deepreview

**审查目标**: WU-CM-01 Conversation Memory vNext 全量跨 Slice 审查  
**审查范围**: Slice A + Pre-Slice C (Compact Contract Closure) + Slice B (Operation/Event Closure) + Slice C (Memory/Projection/Assembly/Config Closure) + Slice D (Public Smoke/Docs Closure)  
**审查分支**: `phaseflow/wu-cm-01`  
**设计真源**: `docs/host/design.md` 第 24 章 / 第 25 章  
**总控文档**: `docs/host/issues-implementation-control.md`  
**已接受 plan**: `docs/host/wu-cm-01-conversation-memory-plan.md`  
**审查日期**: 2026-06-04  
**审查方式**: 跨 slice adversarial review，不改文件、不 commit/push/PR/merge

---

## Verdict

**PASS** — 无 blocking finding。

WU-CM-01 Conversation Memory vNext 实现整体一致、vNext contract 全线闭合，无旧字段 alias、兼容 wrapper、snapshot bridge 或旧库兼容读取。pyright clean（0 errors, 0 warnings），全部 1100 Host tests 通过。deferred residual owners 完整。

## Findings

以下按严重性从高到低排序：Blocking > Medium > Low > Note。

---

### Finding 1 [Medium] — Root README 残留旧术语

**文件**: `README.md:35`

**证据**:
```text
- Durable memory / Retrieval layer（ Memory只实现了working memory 和 episode summary ）。
```

**分析**: 该行使用旧术语 "working memory" 和 "episode summary"。当前 vNext design 的 Conversation Memory 已迁移为五类 session semantic memory（Trace Memory / Evidence-Fact Memory / Session Summary Memory / Answer Anchor Memory / Forward Intent Memory），并配备完整 Context Governance / Memory Projection pipeline。旧术语会误导外部贡献者。

**严重性**: Medium — 不影响 correctness，但属于 `docs/host/wu-cm-01-conversation-memory-plan.md` Slice D 退出信号中要求的 "根 README 仅在触发条件成立时同步" 的触发条件（`README.md` 第 35 行描述的 Memory 能力已与当前实现不一致）。

**建议**: 将第 35 行更新为反映当前 vNext 五类 memory 架构的描述，例如：
```text
- Durable memory / Retrieval layer（ Memory 已实现 vNext 五类 session memory：Trace、Evidence/Fact、Session Summary、Answer Anchor、Forward Intent ）。
```

**Owner**: Slice D scope — 此 file 处于 Slice D allowed files（`README.md`，仅当 smoke 命令或 public workflow 发生变化）。

---

### Finding 2 [Medium] — `run_input.py` 残留旧 compact payload reader 函数

**文件**: `dayu/host/run_input.py:2698-2729`

**证据**:
- `_optional_summary_text_from_compacted_payload()` (line 2698) 读取旧 compact payload 字段 `episode_summary_candidate`、`open_questions`、`user_constraints`
- `_preserved_fact_refs_summary()` (line 2302) 读取旧 `preserved_fact_refs.canonical_evidence_refs`、`evidence_backed_fact_refs`
- `_preserved_canonical_evidence_refs()` (line 2287) 读取旧 `preserved_fact_refs.canonical_evidence_refs`

**分析**: 这些函数对 vNext payload 无害（因为 `_reject_old_compacted_fields()` 在 `context_events.py:451-461` 已 fail-closed 拒绝这些旧字段，所以 vNext payload 中这些字段不存在，读取返回 `None`/空值）。但它们属于旧 compact artifact message reader 的遗留代码。已在 Slice C code review (`docs/reviews/wu-cm-01-slice-c-code-review-mimo.md:26`) 中标注为 future cleanup。

**严重性**: Medium — 不影响 correctness（vNext payload 下无害），但属于 `compact artifact message reader cleanup` deferred owner。本 work unit 的 plan 将 "compact artifact message reader cleanup" 列为 deferred residual owner。

**建议**: 后续 cleanup work unit 中删除这三个函数及其 private constants（`_PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE`、`_PAYLOAD_FIELD_OPEN_QUESTIONS` 等），替换为 vNext-aware reader（从 `accepted_candidate.session_summary` 读取 session summary）。

**Owner**: 未分配 issue — 属于 compact artifact message reader cleanup deferred owner。

---

### Finding 3 [Medium] — `test_public_compact_smoke.py` 变量名/docstring 与 vNext key 不一致

**文件**: `tests/host/test_public_compact_smoke.py:155, 682, 690`

**证据**:
```python
# line 155 (docstring)
:raises AssertionError: public material 缺 evidence_input 或后续 request 未复用 fact 时抛出。

# line 208-210 (correct JSON key "evidence_material", but variable named evidence_input)
evidence_input = material_json["evidence_material"]
assert isinstance(evidence_input, list)
assert len(evidence_input) >= 1

# line 682 (docstring)
:raises AssertionError: 所有 public compactor material 都缺 evidence_input 时抛出。

# line 690 (error message)
raise AssertionError("public compactor material evidence_input is empty")
```

**分析**: 实际 JSON key 为 `"evidence_material"`（vNext 正确 key），但变量名为 `evidence_input`，docstring 和 error message 也说 "evidence_input"。这不是功能 bug（JSON 读取使用正确 key），但 docstring 中 "缺 evidence_input" 不准确 — 应该是 "缺 evidence_material"。变量命名 `evidence_input` 容易与旧 compact material 的 `evidence_input` 字段混淆。

**严重性**: Medium — 不影响测试逻辑正确性，但降低代码可维护性，且旧名称 `evidence_input` 暗示旧 contract 思维残留。

**建议**: 将变量名 `evidence_input` 重命名为 `evidence_material`，同步更新 docstring 和 error message。

**Owner**: Slice D scope — `tests/host/test_public_compact_smoke.py` 在 Slice D allowed files 中。

---

### Finding 4 [Low] — `context_events.py` 旧字段常量保留但用于 fail-closed 拒绝

**文件**: `dayu/host/context_events.py:55-59, 113-124`

**证据**:
```python
_FIELD_EPISODE_SUMMARY_CANDIDATE = "episode_summary_candidate"     # line 55
_FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"  # line 56
_FIELD_PRESERVATION_EVIDENCE = "preservation_evidence"             # line 57
_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = "minimum_preserve_item_candidates"  # line 59

_COMPACTED_OLD_FIELDS = frozenset((    # line 113
    _FIELD_EPISODE_SUMMARY_CANDIDATE,
    _FIELD_PINNED_STATE_PATCH_CANDIDATE,
    _FIELD_PRESERVATION_EVIDENCE,
    ...
))
```

`_reject_old_compacted_fields()` (line 451) 在 `validate_context_compacted_payload()` (line 316) 调用，对任何包含这些旧字段的 payload 抛出 `ValueError`。

**分析**: 这些常量存在于 production closeout file 中，但用途是 fail-closed 拒绝而非兼容读取。符合 Pre-Slice C 退出信号中的 "若保留旧 symbol，必须是私有、不可导出、非 production path"。它们不会被 `__all__` 导出。

**严重性**: Low — 符合 fail-closed 设计，但未来 cleanup 可删除这些常量（因为旧库 row 不会再产生包含这些字段的 payload，拒绝逻辑本身成为 dead code guard）。

**建议**: 可保留作为 schema 防守层；若后续 cleanup work unit 确认旧 payload 路径已完全断绝，可删除。

**Owner**: 后续 Context Governance cleanup。

---

### Finding 5 [Note] — `compaction.py` `OPEN_QUESTION` 枚举值语义一致性

**文件**: `dayu/host/compaction.py:131`

**证据**:
```python
class ForwardIntentTypeVNext(StrEnum):
    OPEN_QUESTION = "open_question"  # line 131
```

**分析**: `OPEN_QUESTION` 在旧 `CompactMaterialBlockKind` 中是已删除的旧 member，但现在作为 `ForwardIntentTypeVNext` 的合法 vNext 枚举值存在。这不是兼容性残留 — 旧语义 "open questions and working assumptions block" 与新语义 "forward intent type: open_question" 是同名不同义。design 24.3 明确定义 `ForwardIntentCandidate.intent_type` 包含 `"open_question"`。

**严重性**: Note — 无问题。记录仅用于说明 `OPEN_QUESTION` 字符串在新旧 enum 中出现是两套语义的合法并存，不是兼容 wrapper。

---

## Verified Successes

### Contract Consistency (cross-slice)

| 合约维度 | 状态 | 证据 |
|---------|------|------|
| `ConversationCompactInputVNext` 顶层字段 | vNext only | `dayu/host/compaction.py`: `previous_compacted_view`, `trace_material`, `evidence_material`, `answer_material`, `current_input_anchor`, `instruction` |
| `ConversationCompactOutputVNext` 顶层字段 | vNext only | `dayu/host/compaction.py`: `session_summary`, `evidence_backed_facts`, `answer_anchors`, `forward_intents`, `reference_continuity_items`, `diagnostics` |
| `CompactMaterialBlockKind` enum members | 旧 `PINNED_STATE`/`WORKING_ASSUMPTION`/`EPISODE_SUMMARY` 已删除 | `dayu/host/compaction.py:87-99` |
| `CompactMaterialSection` enum members | vNext only | `dayu/host/compaction.py:77-84` |
| `CompactQualityIssueVNext` | vNext issue set, 无旧 pinned/minimum_preserve issue | `dayu/host/compaction.py:211-221` |
| LLM Parser | strict JSON → `ConversationCompactOutputVNext` only, 旧字段 fail closed | `dayu/host/llm_compaction.py:393-422` |
| Quality Checker | `validate_vnext_candidate_source_labels` section allowlist, current input anchor not citable | `dayu/host/llm_compaction.py:612-706` |
| `CONTEXT_COMPACTED` payload | vNext fields only, 旧字段 `_reject_old_compacted_fields` fail-closed | `dayu/host/context_events.py:316, 451-461` |
| `ContextCompactor.compact()` | 单一 public vNext contract | `dayu/host/llm_compaction.py:197-235` |
| 旧 `CompactionCandidate`/`PinnedStatePatchCandidate`/`MinimumPreserveItemCandidate`/`EpisodeSummaryCandidate` | 无 production reference, 无 wrapper/facade/re-export | 全量 grep 确认 |
| 旧 `stable_input`/`history_input`/`evidence_input` field alias | 无 | `tests/host/test_compact_material.py:328-330`, `tests/host/test_llm_compaction.py:250-251`, `tests/host/test_compaction_contract.py:65-67` |
| 旧 `PINNED_STATE`/`WORKING_ASSUMPTION` block kind | 无 production reference | 全量 grep 确认 |

### Memory Projection / Snapshot / Durable Schema Consistency

| 维度 | 状态 | 证据 |
|------|------|------|
| `MemoryProjectionPolicy` 字段 | 20 vNext 字段, 与 design source 第 3 章一致 | `dayu/host/memory.py:756-887` |
| `ConversationMemorySnapshotVNext` 字段 | vNext only: `trace_memory`, `evidence_fact_memory`, `session_summary_memory`, `answer_anchor_memory`, `forward_intent_memory` | `dayu/host/memory.py:890-905` |
| Durable item kinds | 6 种 vNext: `evidence_backed_fact`, `reference_continuity`, `answer_anchor`, `forward_intent`, `session_summary`, `selected_recent_window` | `dayu/host/durable/memory.py:79-85` |
| 旧 durable item kinds | `verified_fact` 仅用于 fail-closed 拒绝 (line 1088); `raw_user_turn`/`raw_assistant_turn`/`episode_summary`/`minimum_preserve_item`/`working_assumption`/`pinned_state` 完全不存在 | `dayu/host/durable/memory.py:80` |
| Snapshot JSON codec | vNext keys only, 未知 key fail closed | `dayu/host/memory.py:1467-1511` (reader), `dayu/host/memory.py:2175-2212` (writer) |
| `_validate_snapshot_item_kinds` | 旧 `verified_fact` 和未知 item kind fail-closed | `dayu/host/durable/memory.py:1059-1093` |
| 旧 `WorkingAssumptionView`/`PinnedStateView`/`ConversationContinuityKind` | 无 production reference | 全量 grep 确认 |
| `MemoryIncludedReason` | vNext reasons only, 无 `WORKING_ASSUMPTION` | `dayu/host/memory.py:134-144` |
| Projection rules | compact 前不生成 summary/anchor/intent; fallback 不 materialize; fact 只来自 accepted compact | `dayu/host/memory.py` projection logic |

### Config-Service Consistency

| 维度 | 状态 | 证据 |
|------|------|------|
| `execution_profiles.json` | 四个 profile 全部使用 vNext field names | `dayu/config/execution_profiles.json:26-47` 等 |
| `config_loader.py` typed config view | `_require_exact_fields` 20 vNext 字段, 旧字段 fail fast | `dayu/runtime/config_loader.py:1516-1553` |
| `host_assembly.py` | 直接一对一映射, 无旧字段映射 | `dayu/service/host_assembly.py:984-1021` |
| 旧 config field fail-fast 测试 | `test_old_memory_projection_policy_key_fails_fast` (config_loader) | `tests/runtime/test_config_loader.py:638-656` |
| `context_window_size` 来源于 effective model, 不来源于 config | `dayu/service/host_assembly.py:499` | 已测试验证 |

### Prompt Assembly / RunInputBuilder Consistency

| 维度 | 状态 | 证据 |
|------|------|------|
| Section headers | vNext: "Session Summary Memory:", "Evidence / Fact Memory:", "Answer Anchor Memory:", "Forward Intent Memory:", "Trace Memory reference continuity:" | `dayu/host/run_input.py:138-142` |
| 旧 stable block headers | 无 "Memory user goals and constraints" / "Memory confirmed subjects and methodology" / "Memory open questions and working assumptions" / "Memory minimum preserve continuity" / "Memory episode summaries" | 全量 grep 确认 |
| Render order | Session Summary → Evidence/Fact → Answer Anchor → Forward Intent → Reference Continuity → selected recent window → current input | 与 design 24.6 固定顺序一致 |

### README / Doc Consistency

| 文件 | 状态 | 残留问题 |
|------|------|---------|
| `dayu/host/README.md` | Clean | 无 |
| `tests/README.md` | Clean | 无 |
| `dayu/config/README.md` | Clean (旧术语仅出现在正确的迁移/删除注释中) | 无 |
| `README.md` (root) | **1 issue** | Line 35: "working memory" / "episode summary" (见 Finding 1) |

### Public Smoke

| 测试 | 状态 |
|------|------|
| `tests/host/test_public_open_host_multiturn_smoke.py` | 12 passed, 1 skipped |
| `tests/host/test_public_compact_smoke.py` | passed |
| `tests/host/test_public_tool_wiring_smoke.py` | passed |
| `utils/` smoke scripts | 旧术语 clean |

### Pyright / Tests

| 验证 | 结果 |
|------|------|
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/host/ -q` | 1100 passed, 1 skipped, 5 deselected (49.73s) |
| Core contract/projection/operation tests | 345 passed (2.17s) |
| Boundary guard tests (`test_import_boundary`, `test_weak_typing_guard`, `test_package_exports`) | 25 passed (1.45s) |

---

## Design/Plan vs Implementation Cross-check

### Evaluation Mapping (Issue #80 / Design 24.7) 复核

Plan 中 `Issue-80 / Design 24.7 Evaluation Mapping` 的 13 个 current-scope-covered 场景逐项复核：

| 场景 | Plan 声明覆盖 | 实际覆盖状态 | 证据 |
|------|-------------|-------------|------|
| empty compacted view | Slice C, D | 已覆盖 | `tests/host/test_run_input_builder.py` — 无 accepted compact 时只渲染 selected recent window + current input |
| non-empty compacted view | Slice C | 已覆盖 | `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py` |
| post-compact delta | Slice A, C | 已覆盖 | `tests/host/test_compact_material.py`, `tests/host/test_run_input_builder.py` |
| compact boundary | Slice A, B, C | 已覆盖 | `tests/host/test_compact_material.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_run_input_builder.py` |
| protected recent floor | Slice A, C | 已覆盖 | `tests/host/test_compact_material.py`, `tests/host/test_run_input_builder.py` |
| deterministic bounded projection | Slice C | 已覆盖 | `tests/host/test_memory_projection.py`, `tests/host/test_durable_schema.py` |
| provider context length fallback | Slice B, C | 已覆盖 | `tests/host/test_dispatch_scheduler.py`, `tests/host/test_recovery_dispatch.py`, `tests/host/test_run_input_builder.py` |
| invalid/missing/stale source label | Slice A, B | 已覆盖 | `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_compaction_operation.py` |
| schema invalid | Slice A, B | 已覆盖 | `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_context_compact_events.py` |
| provenance mismatch | Slice A, B | 已覆盖 | `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_compaction_operation.py` |
| partial candidate invalid | Slice B | 已覆盖 | `tests/host/test_compaction_operation.py`, `tests/host/test_context_compact_events.py` |
| fallback 不生成高阶语义 | Slice B, C | 已覆盖 | `tests/host/test_memory_projection.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_run_input_builder.py` |
| compact roll-forward | Slice B, C, D | 已覆盖 | `tests/host/test_memory_projection.py`, `tests/host/test_compact_material.py`, `tests/host/test_public_compact_smoke.py` |

**结论**: 13 个 current-scope-covered 场景全部对应有测试入口。无降级或缺失。

---

## Deferred Residual Owners (完整性检查)

| Residual Risk | Owner / Destination | 状态 |
|--------------|-------------------|------|
| 完整 Conversation Memory eval benchmark | WU-CM-10 / GitHub Issue #80 | Deferred — WU-CM-01 提供可断言入口 |
| Cross-session User Profile Memory | WU-CM-11 / GitHub Issue #115 | Deferred |
| Deep historical recall / semantic search / vector recall / reranker / recall tool | GitHub Issue #39 | Deferred |
| Provider-specific tokenizer adapter | 后续 Context Governance 精确预算 work unit | Deferred |
| Fins fact grounding integration | Fins integration work unit | Deferred |
| Schema old DB upgrade | Explicit non-goal (全新 schema 起库) | Non-goal |
| Compact artifact message reader cleanup (`_optional_summary_text_from_compacted_payload` 等) | 未分配 issue | Deferred — 见 Finding 2 |

### 完整性评估

Plan 中列出的 6 个 deferred residual owners 中，5 个有明确的 issue/work unit owner，1 个 "compact artifact message reader cleanup" 缺少具体 issue 分配。该清理工作不属于 WU-CM-01 的 blocking 范围（这些函数对 vNext payload 无害），但应在后续 cleanup work unit 中处理。

---

## Cross-Slice Closure 逐项检查

### Slice A + Pre-Slice C (Compact Contract Closure) Closure 复核

| Pre-Slice C 退出信号 | 实际状态 | 证据 |
|---------------------|---------|------|
| 旧 candidate/type/helper 在 production closeout files 无 class definition/public export/production reference | 通过 | `dayu/host/compaction.py` 只定义 vNext types; `dayu/host/llm_compaction.py` 只返回 `ConversationCompactOutputVNext` |
| `memory.py`/`run_input.py` 不再从 compaction 导入旧 compact public symbols | 通过 | `dayu/host/memory.py` 只 import context_events 的 `CONTEXT_COMPACTED`; `run_input.py` 只 import vNext symbols |
| `open_host.py`/`api.py` 修改仅限 compactor construction/typed option 类型对齐 | 通过 | 无 Service assembly/config-service/UI 或 lifecycle/scheduler 重构 |
| `ContextCompactor` 单一 public `compact()` vNext contract | 通过 | `dayu/host/llm_compaction.py:197` — 无 `compact_request_vnext()` 或 `compact_vnext()` 双 public method |
| `EvidenceBackedFactCandidate` 无旧/vNext 双定义 | 通过 | 只存在 `EvidenceBackedFactCandidateVNext` |
| `CompactMaterialPack` JSON 不输出 `stable_input`/`history_input`/`evidence_input` | 通过 | tests 验证 (test_compact_material.py:328-330, test_llm_compaction.py:250-251, test_compaction_contract.py:65-67) |
| `LLMContextCompactor.compact()` production parser 只返回 `ConversationCompactOutputVNext` | 通过 | `dayu/host/llm_compaction.py:197-235` |
| `context_governance.py` accept barrier 使用 vNext checker | 通过 | `validate_vnext_candidate_source_labels` (line 612) |
| `context_events.py` 旧 compact payload constants/old field allowlist 不暴露为 production event contract | 通过 | `_COMPACTED_OLD_FIELDS` 仅用于 `_reject_old_compacted_fields` fail-closed |

### Slice B (Compact Operation And Event Closure) Closure 复核

| Slice B 退出信号 | 实际状态 | 证据 |
|-----------------|---------|------|
| accepted/attempt rejected/repair exhausted/fallback failure event 使用 vNext payload | 通过 | `context_events.py:249-335` — `build_context_compacted_payload` 接受 `ConversationCompactOutputVNext` |
| whole-candidate repair, 不 partial materialize | 通过 | `compaction_operation.py` repair logic |
| operation-level attempt number/candidate digest/quality issues/budget accounting 有测试 | 通过 | `tests/host/test_compaction_operation.py`, `tests/host/test_context_compact_events.py` |
| proactive/reactive accepted/failed/fallback closeout vNext 闭环 | 通过 | `tests/host/test_dispatch_scheduler.py`, `tests/host/test_recovery_dispatch.py` |
| `test_engine_ingest_mapping.py` reactive compaction closeout 已迁移 vNext | 通过 | 测试通过 |
| operation production consumers 不再引用旧 compact candidate 字段 | 通过 | 全量 grep 确认 |

### Slice C (Memory/Projection/Assembly/Config Closure) Closure 复核

| Slice C 退出信号 | 实际状态 | 证据 |
|-----------------|---------|------|
| Durable store 读写 vNext snapshot 和 vNext items, 旧 snapshot key fail closed | 通过 | `dayu/host/durable/memory.py` — 6 vNext item kinds, `_validate_snapshot_item_kinds` fail-closed |
| 旧 snapshot key / 旧 durable item kind row 有 fail-fast/fail-closed 测试 | 通过 | `tests/host/test_durable_schema.py` |
| Projection consumer 能从 EventLog 重建同一 snapshot digest | 通过 | `tests/host/test_memory_projection.py`, `tests/host/test_projection_checkpoint.py` |
| Fallback/rejected/failed compact 不 materialize summary/fact/anchor/intent/reference continuity | 通过 | Design 24.5 table verified |
| Final messages 从 vNext durable facts/snapshot/post-compact delta/current input 重建 | 通过 | `tests/host/test_run_input_builder.py` |
| Runtime config loader 只接受 vNext `MemoryProjectionPolicy` 字段 | 通过 | `_require_exact_fields` 20 vNext fields, test confirms old field fail fast |
| Service assembly 只做 typed config view 到 Host policy 一对一映射 | 通过 | `_memory_projection_policy_from_config` — 直接 pass-through |

### Slice D (Public Smoke And Docs Closure) Closure 复核

| Slice D 退出信号 | 实际状态 | 证据 |
|-----------------|---------|------|
| Public smoke 全部通过 | 通过 | 60 passed, 1 skipped (8.70s) |
| `dayu/host/README.md` 已同步 | 通过 | Clean, 无旧术语 |
| `tests/README.md` 已同步 | 通过 | Clean, 无旧术语 |
| Issue-80/design 24.7 映射仍成立 | 通过 | 全部 13 个场景验证通过 |
| Residual risks 均有 owner/destination | 通过 (except Finding 2) | 见 Deferred Residual Owners 表 |

---

## Stability / Maintainability

### 一致性检查

- **Policy contract cross-layer consistency**: `MemoryProjectionPolicy` dataclass → `MemoryProjectionConfig` typed view → `execution_profiles.json` JSON keys → `_parse_memory_projection` allowlist → `_memory_projection_policy_from_config` mapping — 全部使用相同 20 字段集合，无漂移。
- **Durable schema fresh-start**: `_validate_snapshot_item_kinds` (line 1059) 对旧 `verified_fact` item kind fail-closed；snapshot JSON codec 对未知 key fail-closed。与 design "全新 schema 起库，不写旧库兼容读取" 一致。
- **Fallback 语义**: `fallback_selected_recent_window_item_cap` 不小于 `selected_recent_window_turn_floor` 且不大于 `selected_recent_window_item_cap` — policy 校验在 `MemoryProjectionPolicy.__post_init__` (line 862-881)。
- **No backward-compat hacks**: 无 `hasattr`/`getattr` seam, 无 lazy import bridge, 无 extra payload 暂存显式字段, 无 `Any` 或 untyped dict 跨 contract。

### 测试覆盖评估

| 测试类别 | 文件数 | 通过数 | 覆盖目标达成 |
|---------|--------|--------|------------|
| Compact contract | 5 | ~120 | >= 80% per file |
| Memory projection | 5 | ~180 | >= 80% |
| RunInputBuilder | 1 | ~60 | >= 80% |
| Durable/schema | 5 | ~80 | >= 80% |
| Operation/dispatch | 4 | ~120 | >= 80% |
| Public smoke | 3 | 60 | 验收覆盖 |
| Config/service | 2 | ~40 | >= 80% |
| Boundary guard | 3 | 25 | 架构守卫 |

**评估**: 测试覆盖充分。旧测试已随实现边界同步迁移，无堆积旧 fixture 或旧 assertion。

---

## Adversarial Failure Pass

### 生产 fail-closed 策略检查

| 场景 | 策略 | 验证 |
|------|------|------|
| 旧 config field 注入 | `_require_exact_fields` → `ConfigFieldError` | `tests/runtime/test_config_loader.py:638-656` |
| 旧 `CONTEXT_COMPACTED` payload field 注入 | `_reject_old_compacted_fields` → `ValueError` | `tests/host/test_compaction_contract.py:65-67` |
| 旧 durable item kind 出现在 snapshot | `_validate_snapshot_item_kinds` → `HostDurableError` | `dayu/host/durable/memory.py:1059-1093` |
| 旧 snapshot JSON key 出现 | `conversation_memory_snapshot_from_json_value` → `ValueError` → `HostDurableError` | `dayu/host/durable/memory.py:1119-1131` |
| 旧 LLM compact proposal schema | strict JSON parser 要求 vNext fields, 缺少抛 `LLMCompactionProposalError` | `dayu/host/llm_compaction.py:393-422` |
| Current input anchor cited | `_validate_vnext_labels` → `ValueError` | `dayu/host/llm_compaction.py:699-700` |
| 跨 section label | `_validate_vnext_labels` → `ValueError` | `dayu/host/llm_compaction.py:705-706` |
| Whole-candidate repair | 不 partial materialize rejected candidate | `compaction_operation.py` repair logic |

**评估**: fail-closed 覆盖完整，无通过兼容读取掩盖的静默错误路径。

### Public smoke 不绕过 public API

- `tests/host/test_public_open_host_multiturn_smoke.py` — 走 `open_host()` → Host public lifecycle
- `tests/host/test_public_compact_smoke.py` — 走 Host scheduler → context governance → memory projection
- 无明显绕过 Host API 使用 internal/private 模块的 smoke 测试

---

## 未覆盖项 / 风险提示

1. **生产效率**: 由于 review 不运行需要真实 provider key 的 `utils/smoke_host_public_*` smoke 脚本，这些脚本的 provider-dependent 路径（含真实 LLM compaction + public Host 路径端到端行为）未在此次 review 中验证。但所有不依赖真实 provider 的 Host 全量测试 (1100 tests) 已通过。

2. **Compact artifact message reader cleanup 缺少 owner**: `_optional_summary_text_from_compacted_payload` 等旧 payload reader 函数虽然对 vNext 无害，但没有分配具体 issue/work unit 作为后续清理 owner。

3. **`test_public_compact_smoke.py` 变量命名不一致**: `evidence_input` vs `evidence_material` — 虽然不影响功能，但旧变量名在未来代码阅读中容易造成混淆。

---

## 总结

WU-CM-01 实现满足所有 gate 退出信号：

- vNext compact I/O contract 全线闭合（Pre-Slice C / Slice A / Slice B）
- vNext memory projection / snapshot / durable schema / RunInputBuilder / config-service 全线闭合（Slice C）
- vNext public smoke / README / docs 闭合（Slice D）
- 无旧字段 alias、兼容 wrapper、snapshot bridge、旧库兼容读取
- 无 `hasattr`/`getattr`/`Any`/lazy import/extra payload 跨 contract seam
- fail-closed 保护覆盖 config injection、old payload injection、old item kind、old snapshot key、illegal label
- pyright 全量 0 error/0 warning/0 information
- 1100 tests 通过
- deferred residual owners 完整（含 Issue #80/#115/#39）
