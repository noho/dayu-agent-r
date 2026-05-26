# P12.6 Aggregate Deep Review — AgentDS

日期：2026-05-24
范围：`8749be9` → `69ca9ce` (slice 1-7 全部实现与测试)
设计真源：`docs/host/design.md` §24 / §25
总控文档：`docs/host/implementation-control.md`
计划文档：`docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`

## Verdict: PASS

72 文件，+13356 / -1118 行。所有 8 个 aggregate check 类别通过。1 个 MEDIUM finding (working_assumptions / open_questions dedup)，9 个 LOW observations。

---

## Findings

### Finding 1 [MEDIUM] — open_questions 仅精确匹配去重，working_assumptions 完全无去重

**文件:** `dayu/host/memory.py`
**行号:** 382-384 (open_questions), 2354-2378 (working_assumptions)

**证据:**
```python
# memory.py:382-384 — open_questions 仅用 frozenset 做精确去重
if len(frozenset(self.open_questions)) != len(self.open_questions):
    raise ValueError("open_questions must not contain duplicates")

# memory.py:2354-2378 — working_assumptions 只按 count 裁剪，无去重步骤
if len(items) <= policy.max_working_assumptions:
    return items, ()
kept = items[-policy.max_working_assumptions :]
```

`_normalized_text()` (casefold + whitespace collapse) 在 memory.py:2588 已存在，但既未对 open_questions 执行归一化去重，也未对 working_assumptions 执行任何去重。

**影响:** 设计文档 §24 要求 `working_assumptions` 与 `open_questions` 按 normalized text 去重。跨多次 compact 累积时，语义重复项会挤占预算，导致真正的 distinct assumptions 被过早裁剪。

**建议修复:**
1. `PinnedStateView.__post_init__()` 中对 open_questions 应用 `_normalized_text()` 去重。
2. 新增 `_dedupe_working_assumptions()` 函数，在 `_limit_working_assumptions()` 前调用 `_normalized_text()` 对 `assumption_summary` 去重。

---

### Finding 2 [LOW] — 旧 `collect_compaction_request_evidence_inputs` 函数仍存在并公开导出

**文件:** `dayu/host/compaction_evidence.py`
**行号:** 152-205 (定义), 582 (__all__)

**证据:** 接受 `start_event_sequence` / `end_event_sequence` 的 Session 起点 EventLog range 读取函数仍存在于代码中并公开导出。但无生产代码路径调用（dispatch.py / engine_ingest.py 中零引用），仅 test_compaction_operation.py 的隔离测试调用。

**严重程度:** LOW — 无生产影响，已知延迟清理项（Slice 7 控制器裁决）。

**建议:** Slice 7 cleanup 中移除。

---

### Finding 3 [LOW] — `CompactSegmentSelection.policy_digest` 字段名误导

**文件:** `dayu/host/compaction.py:597`, `dayu/host/dispatch.py:1393`, `dayu/host/engine_ingest.py:3028`

**证据:** 字段名为 `policy_digest` 但实际存储 budget estimator digest (proactive) 或 frozen material list digest (reactive)，而非 policy digest。该字段仅用于 Host 内部诊断，不暴露给 LLM。

**建议:** 重命名为 `selection_context_digest` 或补充 docstring 说明。

---

### Finding 4 [LOW] — `build_initial_material_pack()` 跳过 builder 层 dedupe guard

**文件:** `dayu/host/compact_material.py:801-840`

**证据:** `_raise_on_duplicate_section_owner()` 仅在 `build_compact_material_pack()` (line 661) 内调用。`build_initial_material_pack()` 依赖 `CompactMaterialPack.__post_init__()` 中的构造器级 guard (`_require_one_section_per_canonical_content`)，功能等效但路径不对称。

**建议:** 统一两条 builder 路径的 dedupe 调用，或显式文档化 post-init guard 覆盖所有路径。

---

### Finding 5 [LOW] — Proactive path 冗余 None 检查可能静默丢弃失败

**文件:** `dayu/host/dispatch.py`
**行号:** 1084-1086, 1106-1109

**证据:**
- Line 1084-1086: `_execute_proactive_compaction` 中 `compactor is None` 返回 None，但 `_prepare_compact_before_dispatch` 已守卫此条件。
- Line 1106-1109: `run is None` (Run 被删除) 返回 None，不写 `CONTEXT_COMPACTION_FAILED`。

**影响:** 极端边界情况下静默丢弃 compact 结果而不留下 canonical 记录。不导致数据损坏。

**建议:** 两条路径都写入 `CONTEXT_COMPACTION_FAILED` 以改善可调试性。

---

### Finding 6 [LOW] — Reactive path 非 RECOVERING 丢弃不记录 diagnostic

**文件:** `dayu/host/engine_ingest.py`
**行号:** 1516-1519

**证据:** compact operation 完成后若 Run 已不再是 RECOVERING (被并发进程修改)，结果被静默丢弃，无 `CONTEXT_COMPACTION_FAILED` 写入。

**建议:** 添加 `failure_reason="run_not_recovering_after_compact"` 的 diagnostic 事件。

---

### Finding 7 [LOW] — Public compact smoke 缺少 reactive 路径端到端触发

**文件:** `tests/host/test_public_compact_smoke.py`

**证据:** 6 个 smoke 测试覆盖 proactive 路径和 material pack 验证，但无 smoke 级别的 reactive 路径触发。Reactive compact 仅在 `test_compaction_operation.py` 单元测试中覆盖。

**建议:** 若 reactive 在 public API 边界可达，增加一个触发 reactive compact 的 smoke 测试。

---

### Finding 8 [LOW] — Public compact smoke 未独立断言 CONTEXT_COMPACTED EventLog 写入

**文件:** `tests/host/test_public_compact_smoke.py`

**证据:** Smoke 测试验证 memory projection 输出但不独立断言 CONTEXT_COMPACTED EventLog 行存在。该断言分散在 test_context_compact_events.py 和 test_memory_projection.py。

**建议:** 在 smoke watcher 循环中添加 `HostEventKind.PROGRESS` 事件断言。

---

### Finding 9 [LOW] — `build_compact_material_pack` 缺少含 memory snapshot stable_input 的显式测试

**文件:** `tests/host/test_compact_material.py`

**证据:** `select_compact_segment` 被彻底测试，但 `build_compact_material_pack` 仅在 4 个测试中间接调用，无覆盖全部 4 个 section (含 memory snapshot stable_input) 的显式测试。

**建议:** 增加包含 memory snapshot 的完整 pack builder 测试。

---

### Finding 10 [LOW] — EpisodeSummaryCandidate.source_event_refs 使用 raw event ID

**文件:** `dayu/host/llm_compaction.py:512`

**证据:** `_episode_summary_candidate` 将 `source_event_refs` 设为 `request.material_source_refs` (canonical event ID)，而其他 candidate 使用 prompt-local / opaque ref 策略。这不暴露给 LLM (仅在 `to_json()` 中用于 durable 序列化)，但 ref 策略不一致。

**建议:** 考虑统一 ref 策略或添加注释说明此处有意使用 event ID。

---

## 逐项检查结果

### 1. EventLog ledger dump / Session 起点 range — PASS

- 无 `start_event_sequence=1` 硬编码进入 compactor prompt。
- Proactive dispatch path 使用 `build_accepted_tool_evidence_material_blocks` (event_id + session_id 校验)。
- Reactive engine_ingest path 使用 in-memory views (MemorySnapshotView, CompactArtifactView, SessionContinuityView)。
- 旧 `collect_compaction_request_evidence_inputs` 函数保留但无生产调用 (Finding 2)。

### 2. result_preview — PASS

- `compaction_evidence.py:253` 在每次 TOOL_RESULT_ACCEPTED payload 处理时调用 `_reject_result_preview()`。
- `compaction_evidence.py:302-311` — 若 payload 含 `result_preview` 抛出 `HostDurableError`，fail closed。
- Smoke 测试断言 `result_preview` 不在 material text 中 (line 212)。

### 3. Event id / payload ref / digest / cursor 作为 LLM semantic input — PASS

- 所有 LLM-facing JSON (`llm_json()` / `llm_material_json()`) 系统性地排除 canonical provenance key。
- `CompactMaterialBlock.llm_json()` 只返回 `{label, kind, text, source_labels}`。
- `CompactEvidenceBlock.llm_json()` 只返回 `{label, kind, tool_name, query_text, result_text, source_text}`。
- `CompactMaterialPack.llm_json()` 不包含 `provenance_map`。

### 4. Material pack prompt-local labels + Host provenance map — PASS

- Prompt-local label 生成集中在 `compact_material.py` 的 `material_label()`, `evidence_chunk_label()`, `current_input_anchor_label()`。
- Section prefix 映射使用共享 `_SECTION_PREFIXES` 常量。
- LLM output 解析通过 `_canonical_refs_for_labels()` / `_canonical_evidence_refs_for_labels()` 映射 prompt-local labels → canonical refs。
- Evidence 内容来自 digest-checked raw payload / raw result descriptor，非 accepted evidence envelope preview。
- 双层 dedupe 防线：builder 层 (`_raise_on_duplicate_section_owner`) + 构造器层 (`_require_one_section_per_canonical_content`)。

### 5. Proactive/reactive Context Governance lifecycle — PASS

- Proactive path: dispatch 前执行 compact，不创建 Attempt；失败 Run → FAILED。
- Reactive path: 校验 attempt_id + execution_id → 关闭 Attempt → Run → RECOVERING → compact → 新 Attempt。
- Multi-pass: 中间产物仅 transient in-memory，最终提交一个 merged `CONTEXT_COMPACTED` 或一个 `CONTEXT_COMPACTION_FAILED`。
- Stale/cancelled/cursor-mismatch 正确丢弃 stale proposal，不写 `CONTEXT_COMPACTED`。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 作为 `EventClass.CANONICAL_FACT` 写入。
- 所有 compact 事件通过 `EventLog.append_event()` 写入，不绕过 EventLog。
- Memory projection 不消费中间 pass output。

### 6. Memory projection / RunInputBuilder bounded working set — PASS (1 MEDIUM)

- Memory projection 只消费 committed canonical EventLog facts。
- Pinned state 渲染当前值非 patch log；tri-state patch (`MISSING`/`CLEAR`/`REPLACE`) 应用后丢弃。
- Evidence-backed facts 只来自 CONTEXT_COMPACTED payload 的 fact candidates，引用 accepted evidence。
- Fact dedup: `(normalized claim_text, sorted evidence_refs, evidence_kind)` key。
- Episode summary 只做导航 (ConversationContinuityKind.EPISODE_SUMMARY)，不创建新 fact。
- Stable layer bounded: ratio/floor/cap；history pool bounded: ratio/floor/cap + recent raw turns floor。
- Minimum preserve items: text ≤ 1200 chars, label ≤ 120 chars, count ≤ 32, 三种 narrow preserve reason。
- Snapshot cursor 校验: lag ≤ threshold → inline delta repair; lag > threshold → MemoryProjectionRepairRequired → catch-up/rebuild。
- **MEDIUM: open_questions 精确去重 + working_assumptions 无去重** (Finding 1)。

### 7. Tests / public compact smoke — PASS (3 LOW observations)

- 6 个 public smoke tests 覆盖: proactive 触发, material pack 无 ledger dump, result_preview 拒绝, prompt-local label, fact reuse。
- 22 个 compaction contract tests, 18 个 llm_compaction tests, 21 个 compaction_operation tests, 34 个 memory projection tests。
- Fake compactor (`fake_compaction.py`) 完整覆盖 proposal → candidate → quality check 路径。
- LOW: reactive smoke 缺失, CONTEXT_COMPACTED EventLog 断言分散, pack builder 全 section 测试缺失。

### 8. 分层/类型/docstring/兼容性约束 — PASS

- 零 `Any` / `object` 类型注解。全部函数完整类型签名。
- 零 `hasattr` / `getattr` 在 P12.6 变更代码中。
- 全部新增函数完整中文 docstring (参数、返回值、异常)。
- 零 `dayu.host` import `dayu.service` / `dayu.ui` / `dayu.fins`。
- 零兼容 wrapper / deprecated alias / 旧字段 re-export。旧 `proposed_verified_fact_refs` 字段被正确拒绝。

---

## Residual Risks

| Risk | Owner | Mitigation |
|---|---|---|
| working_assumptions 语义重复累积导致预算浪费 | P12.7 / 后续 phase | Finding 1 修复或 P12.7 中补齐 normalized dedup |
| 旧 `collect_compaction_request_evidence_inputs` 保留可能被未来代码误用 | P12.7 cleanup | Slice 7 cleanup 移除 |
| Reactive path 无 smoke-level 端到端覆盖 | P12.7 测试补充 | 增加 reactive smoke test |
| Proactive/reactive stale 路径中少数静默丢弃场景 | P12.7 robustness | 添加 diagnostic CONTEXT_COMPACTION_FAILED |

---

## Tests Reviewed

- `tests/host/test_public_compact_smoke.py` — 6 tests (proactive end-to-end)
- `tests/host/test_compact_material.py` — 11 tests (segment selection, dedup, section mapping)
- `tests/host/test_compaction_contract.py` — 22 tests (quality check, candidate validation, candidate builder)
- `tests/host/test_compaction_operation.py` — 21 tests (operation lifecycle, multi-pass merge, evidence read, retry)
- `tests/host/test_llm_compaction.py` — 18 tests (prompt rendering, label parsing, candidate construction)
- `tests/host/test_context_compact_events.py` — 17 tests (event payload validation)
- `tests/host/test_memory_projection.py` — 34 tests (CONTEXT_COMPACTED projection, fact dedup, expiration)
- `tests/host/test_run_input_builder.py` — memory provider / material block 相关测试
- `tests/host/test_dispatch_scheduler.py` — proactive dispatch 路径
- `tests/host/test_engine_ingest_mapping.py` — reactive ingest 路径
- `tests/host/test_compact_artifact_store.py` — artifact 读写
- `tests/host/test_import_boundary.py` — 分层约束

## Tests Recommended

1. `test_compact_material.py`: 增加含 memory snapshot stable_input 的 `build_compact_material_pack` 全 section 测试。
2. `test_public_compact_smoke.py`: 增加 reactive 路径端到端 smoke test (若 public API 边界可达)。
3. `test_public_compact_smoke.py`: 增加 watcher 中 CONTEXT_COMPACTED HostEvent 独立断言。
4. `test_memory_projection.py`: 增加 open_questions normalized dedup 测试 + working_assumptions dedup 测试。
