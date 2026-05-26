# P12.6 Slice 6 Code Review — AgentDS

- **Review role**: AgentDS adversarial code review
- **Base checkpoint**: `851a2e7 gateflow: accept P12.6 slice 5`
- **Artifact date**: 2026-05-24
- **Reviewed diff**: `dayu/host/memory.py`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`

## Verdict: PASS

无 blocking findings。

---

## Findings

### 1. Dedupe key 验证 — PASS

**文件**: `dayu/host/memory.py:1578-1591`

`_evidence_backed_fact_dedupe_key` 的 dedupe key 为 `(normalized claim_text, sorted evidence_refs, evidence_kind)`。`_normalized_text` (line 2595) 执行 casefold + 空白压缩，去重口径合理。`tuple(sorted(fact.evidence_refs))` 确保 evidence refs 顺序无关。`EvidenceBackedFactKind` 为 `StrEnum`，成员为 `OBSERVED_VALUE / QUOTED_STATEMENT / TABLE_VALUE / DERIVED_FROM_EVIDENCE`，覆盖了 compact output 的四种 fact kind。

`_is_newer_or_equal_extraction` (line 1594-1606) 在 event_sequence 相同时以 item_id 作为 tiebreaker，确保同时提取的同 dedupe key 候选能稳定决出胜负。`_superseded_fact_diagnostic` (line 1609-1638) 记录 superseded → superseding 的 item_id 关联，diagnostic message 可解释。

**唯一注意点**: 同一 compact event 内若产出两个完全相同 dedupe key 的 fact candidate，第二个 candidate 会 supersede 第一个（item_id tiebreaker），两个 candidate 都会产生 superseded diagnostic。这是正确行为，只是需要在 trace 中注意解读。

### 2. Bounded fact working set 确定性 — PASS

**文件**: `dayu/host/memory.py:2297-2351`

`_select_evidence_backed_fact_working_set` 的排序 key 由五个分量组成，每个分量都来自输入快照的确定性子集：

1. `-_token_overlap_count(fact_tokens, subject_tokens)` — pinned subjects token 重叠（降序）
2. `-_token_overlap_count(fact_tokens, goal_tokens)` — current goal token 重叠（降序）
3. `-_token_overlap_count(fact_tokens, recent_tokens)` — recent user turns token 重叠（降序）
4. `-item.provenance.event_sequence` — 较新 event 优先（降序）
5. `item.item_id` — 最终稳定 tiebreaker

排序 key 的所有输入都来自同一 snapshot 的 committed 数据，对同样的输入完全确定性。最后一步 `tuple(item for item in items if item.item_id in selected_ids)` 保持原始 EventLog 排序，不引入 sorted items 的顺序扰动。

Token 化使用 `_text_tokens` (line 2598-2616)：casefold → 非 alnum 替换为空格 → split。`_token_overlap_count` 使用 frozenset intersection，复杂度 O(min(|left|, |right|))。

`_pinned_subject_tokens` (line 2535-2546) 将 `ref_kind.value` 和 `ref_id` 都纳入 token 集合；`_recent_user_reference_tokens` (line 2549-2567) 只取最近 `DEFAULT_MEMORY_RECENT_RAW_TURNS_FLOOR=2` 个 user turn 的 summary_text 做 token 化。两者都纯文本、无业务字段依赖，符合 Host-neutral 约束。

### 3. Episode summaries bounded rendering — PASS

**文件**: `dayu/host/memory.py:2441-2457`

`_policy_bounded_recent_episode_summaries` 使用 `max(DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR, policy.recent_raw_turns_floor)` 作为上限。按设计文档 §24 (line 2590)："episode summaries 进入 history pool 后仍需 bounded rendering；较旧 summaries 应 roll up 或只保留 artifact / EventLog refs"。实现满足需求：被排除的 summaries 通过 `_limit_continuity_items` 的统一 budget diagnostic (line 2431-2438) 给出解释，不渲染被裁剪的全文。

### 4. Minimum preserve coverage expiry — PASS

**文件**: `dayu/host/memory.py:2460-2573`

`_expire_covered_minimum_preserve_items` 对每个 `MINIMUM_PRESERVE_ITEM` 调用 `_minimum_preserve_is_covered` 检查：

- Stable facts: `source_refs.issubset(_evidence_backed_fact_cover_refs(fact))` 且 fact 的 event_sequence > item 的 event_sequence（必须是"后来"的 stable fact）
- Episode summaries: 同理，summary 的 source_refs 必须覆盖 preserve 的 source_refs 且 summary 更晚

`_evidence_backed_fact_cover_refs` (line 2528-2545) 的覆盖范围包括 fact 自己的 `evidence_refs + item_id + candidate_id + event_id + compact_artifact_ref + payload_ref`。覆盖面充分，既包括 evidence 引用也包括 provenance 标识。

被覆盖的 preserve item 产生 `MINIMUM_PRESERVE_ITEM_COVERED` diagnostic (line 2548-2573)，可解释。

**设计对齐**: 设计文档 (line 2596-2597)："minimum_preserve_items 与 conversation continuity 是短寿命导航层；如果已被 stable layer 或 episode summary 覆盖，应从可见 working set 中移除。"

### 5. Compaction-gated fact extraction 保护 — PASS

**文件**: `dayu/host/memory.py:1196-1235`

`project_conversation_memory_event` 的事件处理路径：

- `TOOL_RESULT_ACCEPTED` → pass（只记录 accepted evidence envelope，不直接物化 fact）：符合设计 (line 2624-2626)
- `USER_INPUT_ACCEPTED` → continuity raw turn + pinned state 更新：不进入 fact
- `RUN_SUCCEEDED` → assistant conclusion continuity：不进入 fact
- `CONTEXT_COMPACTED` → `_evidence_backed_facts_from_compacted_event` → `_merge_evidence_backed_facts_by_dedupe_key`：唯一 fact 物化入口

`_evidence_backed_facts_from_compacted_event` (line 1437-1516) 为每个 fact 构造 `EvidenceBackedFactView.provenance` 指向 `CONTEXT_COMPACTED` event 的 id / event_sequence / payload_ref / payload_digest / run_id / attempt_id / execution_id。`extraction_operation_ref` 为 `f"event:{event.event_id}"`。item_id 为 `f"evidence_backed_fact:{candidate_id}"`，provider 为 `HOST_PROJECTION`。所有字段都来自 committed EventLog event，不由 LLM 或 Context Governance 直接写入。

### 6. RunInputBuilder rendering — PASS

**文件**: `dayu/host/run_input.py:1777-1802`

`_memory_evidence_backed_fact_message` 为每个 fact 渲染：
```
fact=claim_text={...}; evidence_refs={...}; evidence_kind={...}; extraction_operation_ref={...}; event_id={...}; event_sequence={...}
```

包含 design doc (line 2622-2623) 要求的 `claim_text` 和 `evidence_refs`，同时附加 `evidence_kind`、`extraction_operation_ref` 和 provenance。测试 `test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only` 验证了渲染内容不包含 `digest_ref=` 或 `fact_summary=`，确认不退化为 digest-only。

`_memory_minimum_preserve_message` (line 1870-1901) 渲染 label、text、source_refs、preserve_reason。`_memory_episode_summary_message` (line 1904-1929) 渲染 episode_summary 文本。均不进入稳定 facts block。

### 7. 分层与类型约束 — PASS

- `memory.py` import 仅来自 `dayu.host.*` (compaction, context_events, durable/codec, terminal_summary_payload) 和 `dayu.contracts.json_value`。无 `dayu.engine / fins / service / ui / config` 导入。
- 类型注解中零处 `object`、`Any` 使用。docstring 中的 "JSON object" 为文档用语，非类型注解。
- 所有新增公开函数和模块级函数提供中文 docstring 及 `params/returns/raises`。
- 无兼容性 wrapper、兼容性 re-export、或旧 key fallback。

### 8. Pinned state 只暴露 materialized state — PASS

**文件**: `dayu/host/memory.py:1190,1245-1249,1258`

`_apply_pinned_state_patch_candidate` 将 patch candidate 合并到 materialized `pinned_state`，每次 compact 产出的是当前物化值（如 `current_goal` 的最终值），不是 patch 累积日志。`_limit_pinned_state` (line 1258) 施加 bounds。测试 `test_memory_projection_materializes_pinned_state_current_value_not_patch_log` 验证：两次 compact（goal "analyze revenue" → "analyze margin"）后 snapshot.pinned_state.current_goal == "analyze margin"。

### 9. 抗幻觉保护 — PASS

**文件**: `dayu/host/memory.py:1196-1249` + test

- USER_INPUT_ACCEPTED → 不进入 evidence_backed_facts
- RUN_SUCCEEDED → 不进入 evidence_backed_facts
- CONTEXT_COMPACTED episode_summary_candidate → 不进入 evidence_backed_facts

测试 `test_final_answer_user_input_summary_do_not_become_evidence_backed_fact` 覆盖：user input "revenue was 100"、assistant final answer "assistant says revenue was 100"、episode summary "summary says revenue was 100" 都不会进入 evidence_backed_facts。三者分别进入 RAW_USER_TURN、ASSISTANT_CONCLUSION、EPISODE_SUMMARY continuity。

### 10. Episode summary source_refs 实现 — PASS

**文件**: `dayu/host/memory.py:1833-1849`

`_compact_episode_summary_source_refs` 从 episode_summary_candidate 读取 `source_event_refs + evidence_refs + confirmed_fact_refs` 并去重。用在 `_compact_episode_summary_from_projection_event` (line 1823) 和 `_minimum_preserve_is_covered` (line 2523) 的覆盖判断中。

### 11. 无兼容性退化 — PASS

`_replace_item_by_id` 保留给 continuity_items / pinned_state 的 idempotent 替换逻辑，仍然在使用中。`_evidence_backed_facts_from_compacted_event` 不再调用 `_replace_item_by_id`，改为经 `_merge_evidence_backed_facts_by_dedupe_key` 合并。没有为保留 `_replace_item_by_id` 的旧语义而添加条件分支。

---

## Tests Reviewed

### 新增 tests（@memory_projection）

| Test | 覆盖点 |
|------|--------|
| `test_final_answer_user_input_summary_do_not_become_evidence_backed_fact` | 抗幻觉：user input / final answer / episode summary 不升级为 fact |
| `test_memory_projection_materializes_pinned_state_current_value_not_patch_log` | Pinned state 暴露物化值，非 patch log |
| `test_evidence_backed_fact_working_set_is_bounded_and_deterministic` | Duplicate claim text（不同空白）被正确 dedupe；bounded working set 按 event sequence 输出 |
| `test_episode_summaries_are_policy_bounded_not_append_only_rendered` | 4 summaries → 只保留后 2 个；旧 summary 产生 BUDGET_LIMIT_REACHED diagnostic |
| `test_minimum_preserve_expires_when_covered_by_stable_or_summary` | Minimum preserve 被后续 summary 覆盖后从 working set 移除；产生 MINIMUM_PRESERVE_ITEM_COVERED diagnostic |

### 新增 tests（@run_input_builder）

| Test | 覆盖点 |
|------|--------|
| `test_run_input_builder_renders_claim_text_and_evidence_refs_not_digest_only` | 渲染包含 claim_text / evidence_refs，不包含 digest_ref= / fact_summary= |
| `test_no_compaction_recent_raw_turns_continuity_still_works` | 无 compact 链路：recent raw turns 仍然提供连续性 |

### 现有 tests 仍 passing

91 passed (test_memory_projection.py + test_run_input_builder.py)，无 regression。

---

## Recommended Additions

以下为质量加固建议，均非 blocking：

1. **Dedupe key coverage edge**: 考虑增加同 event 内两个 candidate 有相同 dedupe key 但不同 candidate_id 的边界测试。当前 `_is_newer_or_equal_extraction` 在同 event_sequence 下以 item_id 决胜负，两个 candidate 各产出一条 superseded diagnostic。这个行为是正确的，但应明确覆盖。

2. **Fact working set on empty pinned_state / empty goal**: `_evidence_backed_fact_selection_key` 在 `pinned_state` 空、`current_goal` 空、`recent_tokens` 空时，退化为纯 (event_sequence, item_id) 排序。这是合理回退，但可加一条 smoke test 确认空 context 下仍保持确定性。

3. **Minimum preserve source_refs 为空时不判定为 covered** — 当前实现已正确处理此边界（line 2511-2512），可加一条单测锁定此行为。

---

## Residual Risks

1. **Fact working set relevance 排序是 Host-neutral token overlap**。当前不包含财报业务语义排序（如 metric / period / subject 的语义距离）。若未来需要业务语义排序，应在独立的 Host policy / retrieval owner 中设计。此风险已在 implementation artifact 中标注为 stop condition，不属于本 slice scope。

2. **Durable historical facts 全量存储仍受当前 snapshot table 物理模型约束**。本 slice 保证 ordinary RunInputBuilder / compactor input 只消费 bounded snapshot working set。大 session 下的历史 fact 全量 query 不在本 slice 范围。

3. **Episode summary source_refs 覆盖面已足够**（source_event_refs + evidence_refs + confirmed_fact_refs），但若 compact output 未来新增其他 ref 类型，需同步更新 `_compact_episode_summary_source_refs`。

4. **`_is_newer_or_equal_extraction` 在同 event_sequence + 同 item_id 时判定为 "newer or equal"**。这在正常流程中不会触发（同 event 的同 candidate 不会产生两个不同 fact view），但若出现因 codec bug 产生的重复 candidate，会生成一条多余的 superseded diagnostic。影响仅为 noise，不破坏 correctness。
