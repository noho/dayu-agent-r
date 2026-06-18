# Code Review

## Scope

- Mode: current changes (aggregate)
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/deepreview-wu-cm-12-mimo-20260618.md
- Included scope: WU-CM-12 S1-S5 累计变更。生产代码：`dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`。测试：`tests/host/test_compact_material.py`、`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_tool_wiring_smoke.py`。设计/控制文档：`docs/host/design.md`、`docs/host/issues-implementation-control.md`、`docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`。S1-S5 implementation/control/review artifacts。
- Excluded scope: S1-S5 各 slice 已在独立 review 中通过的单项；reactive recovery（S4 deferred）；Engine message dataclasses；EventLog/durable schema；public API。
- Parallel review coverage: 无。单一 reviewer 逐维度走读累计变更。

## Findings

未发现实质性问题。

## Review Checklist 逐项结论

### 1) design.md 作为设计真源 — PASS

**检查项**: `docs/host/design.md` 是否已作为设计真源，讨论稿不再替代真源；实现是否偏离 design.md no silent truncation/no preview/assemble/fallback tiers/five semantic memories。

**直接证据**:

- `issues-implementation-control.md` 设计源声明（当前状态）："Current active WU: updated `docs/host/design.md`; `docs/engine/design.md` only if Engine contracts are touched. `docs/host/conversation-memory-material-budget-discussion.md` remains rationale / handoff reference and no longer replaces design truth after completed write-back."
- `design.md` diff 包含：expanded `assemble(...)`（行 2787、2829、2870、3104、3193-3255）、五类 Session Semantic Memory 映射（行 2796）、tier 0-5 fallback 状态机（行 3193-3263）、no silent truncation/preview/summary 化约束（行 1596、2966、3263）、`memory_projection_policy` owner 边界（行 2817）、section-aware degrade 禁止动作（行 3263）。
- 实现与 design.md 一致性：
  - `_bounded_text`（silent truncation）已从 `memory.py` 删除。`CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` 和 `_CURRENT_INPUT_TRUNCATED_MARKER` 已从 `compact_material.py` 删除。`_COMPACT_SUMMARY_MAX_CHARS` 已从 `run_input.py` 删除。
  - 超长 current input（>1200 chars）不调用 compactor、不写 compact artifact、走 dispatch fallback（`test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`），符合 design.md no truncation。
  - Session summary 超 char cap 时 whole-item drop 并记录 diagnostic（`memory.py:1730-1740`），不截断。
  - Evidence fact 超 char cap 时 whole-item drop 并记录 diagnostic（`memory.py:1812-1821`），不截断。

### 2) MemoryProjectionPolicy 作为 LLM-facing material 产量单一 owner — PASS

**检查项**: `MemoryProjectionPolicy` 是否成为 LLM-facing material 产量单一 owner；是否仍存在私有 cap/截断进入 LLM-facing material。

**直接证据**:

- `MemoryProjectionPolicy`（`memory.py:767-885`）定义所有 LLM-facing material 产量参数：`selected_recent_window_turn_floor`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`session_summary_char_cap`、`evidence_fact_char_cap` 等。
- 生产代码中无残留私有 cap/截断常量进入 LLM-facing material：
  - `_bounded_text` 已删除（`memory.py` diff 行 3013-3026）。
  - `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` 已删除（`compact_material.py` diff）。
  - `_COMPACT_SUMMARY_MAX_CHARS` 已删除（`run_input.py` diff）。
  - `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096`（`compact_material.py:89`）是 evidence chunk 确定性分块上限，不是截断——超出时分为多个 chunk 并保留 provenance，符合 design.md "chunking with provenance"。
  - `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200`（`compaction.py:680`）是 compact schema 约束，不是 Host 截断——超长时 Host 不 compact 而非截断。
  - `_validate_bounded_text_field`（`tool_trace.py`、`tool_runtime.py`）是 tool signal schema 校验，不进入 LLM-facing material。

### 3) turn_group_id/floor/fallback caps 保护 Host run group — PASS

**检查项**: turn_group_id/floor/fallback caps 是否正确保护 Host run group，不打散 floor，不用后续小块绕 cap。

**直接证据**:

- S1：`RunInputMaterialBlock.turn_group_id` 字段（`compact_material.py:238`）；`is_turn_group_material_block` 和 `protected_recent_turn_group_ids_for_material_blocks` 共享 helper（`compact_material.py:1530-1582`）。
- S2：`_protected_recent_run_ids`（`memory.py:1997-2048`）按 turn group floor 保护 recent run groups；`_protected_recent_turn_group_block_ids`（`compact_material.py:1498-1528`）保护 compact segment floor；`build_recent_window_fallback_selection`（`context_fallback.py:481`）保护 fallback floor。
- S4：`select_compact_segment` 新增 `max_selected_item_count`（`compact_material.py:893`）和 `budget_blocked` flag（`compact_material.py:927`）。`budget_blocked` 一旦触发，后续所有 block 被 whole-drop（行 929-931），不用更晚小块绕 cap。`max_selected_item_count=None` 时 `budget_blocked` 永远 `False`，normal path 不受影响。
- S4：`degrade_previous_compacted_view_for_recovery`（`compact_material.py:984-1017`）只 whole-drop section，不截断/改写/合成。
- 测试覆盖：`test_recovery_segment_selection_enforces_fallback_item_cap`、`test_recovery_segment_selection_does_not_use_later_block_to_evade_char_cap`、`test_degrade_previous_compacted_view_keeps_highest_priority_section_exact`。

### 4) Provenance guards fail closed 且同源 — PASS

**检查项**: compact input / ordinary RunInput / fallback RunInput selected-id/source-ref/provenance guard 是否 fail closed 且同源。

**直接证据**:

- S3：`_selected_material_render_view`（`run_input.py:2776-2818`）实现全部 guards：duplicate selected ids、missing selected id、current_input_ref mismatch、source_refs mismatch、fallback_input_digest mismatch、selected_material_view_digest mismatch、protected group consistency。全部 raise `HostDurableError`。
- S3：`EventLogContextFallbackProvider`（`context_fallback.py:356-406`）使用 required reader 读取 always-present provenance 字段，缺失/坏类型 → `HostDurableError`。
- S5：Provider 重建 EventLog-backed frozen material view（`context_fallback.py:410-454`），与 dispatch.py proactive compaction 同源 builder `build_pre_dispatch_compact_material_view`。`RunInputBuilder` 优先使用 frozen view（`run_input.py:1901-1915`），fallback 为 `None` 时使用 ordinary view。Guard 校验对象不变。
- 三个路径（compact / ordinary / fallback）共享同一套 material selection/rendering 语义（design.md 行 2870），差异只在 renderer、source label 和 accept barrier。

### 5) Tier1-3 proactive recovery、tier4/5 fallback state machine — PASS

**检查项**: tier1-3 proactive recovery、tier4/5 fallback state machine 是否正确；S4 reactive recovery deferred 是否在 control doc 中有 owner 且不阻断本 WU。

**直接证据**:

- S4：`_proactive_compaction_recovery_attempts`（`dispatch.py:1479-1545`）按顺序构造 tier 1/2/3。Recovery loop（`dispatch.py:1341-1374`）对每个 tier 调用 `run_compaction_operation(max_attempts=1)`，accepted 后 break。Stale check 三层覆盖：token 前（行 1343）、token 后（行 1353）、commit 前 Session recheck（行 1396-1411）。`_completed_compaction_proposal_attempt_count`（`dispatch.py:4121-4141`）排除 cancellation-before-attempt。
- S4：全部失败后走 `_append_compaction_failed_with_proactive_fallback`（行 1422-1438）→ tier 4/5 dispatch fallback。
- Control doc residual table：`WU-CM-12-S4-R1` 标记为 `deferred-with-owner`，owner 为 "Future reactive compact recovery follow-up; owner must be assigned by user or GitHub Issue before implementation"。不阻断本 WU。
- 测试覆盖：tier 1/2/3 accepted、stale-before、stale-during、all-tier-fail。

### 6) S5 public smoke reconciliation — PASS

**检查项**: 超长 current input 不截断、不调用 compactor、不写 compact artifact 且 fallback 成功。

**直接证据**:

- `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200`（`compaction.py:680`）。`CurrentInputAnchorVNext.text` 有 `_require_bounded_non_empty_text` 校验。
- `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`：`fake_compactor.prompt_lengths == []`（不调用 compactor）、`_compact_artifact_files(...) == ()`（不写 compact artifact）、`terminal.kind is HostEventKind.SUCCEEDED`（fallback 成功）。
- 需要 compact 的 smoke 改用 `_soft_threshold_prompt()`（短 current input），确保正常进入 compactor。
- 最终结果：`11 passed, 1 skipped`。

### 7) Active residual table — PASS

**检查项**: active residual table 是否只保留真正 deferred-with-owner 项，已关闭 residual 是否有 artifact 依据。

**直接证据**:

- `WU-CLI-ACTIVITY-01-PR-R1`：已关闭。依据：S5 public continuity smokes 通过（`2 passed`），control doc 记录 "closed by passing public continuity smokes"。
- `WU-CM-12-S1-R1`：已关闭。依据：`_facts_from_accepted_event` root-cause fix（`memory.py:1823-1832`），`test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels` 覆盖。
- `WU-CM-12-S4-R1`：保留为 `deferred-with-owner`。依据：S4/S5 adjudication 结论 reactive tier1-3 recovery 需要 separate Engine ingest recovery sequencing，超出本 WU scope。Owner 为 "Future reactive compact recovery follow-up; owner must be assigned by user or GitHub Issue before implementation"。
- 其他 residual（`WU-TOOLS-01-F01-02-R1`、`WU-TOOLS-01-F01-02-R2`、`WU-TOOLS-01-F03-R4`）均为 pre-existing deferred 项，与 WU-CM-12 无关。

### 8) README decision — PASS

**检查项**: README decision 是否符合 AGENTS.md。

**直接证据**:

- `git diff main...HEAD -- dayu/host/README.md tests/README.md README.md` 无变更。
- S5 implementation artifact README decision："Host 改动是内部 proactive fallback selected-id 同源修正和 memory projection invalid candidate 处理，不改变 public Host API、装配方式、稳定开发手册入口或用户工作流。Test 改动不改变测试目录结构、运行方式或维护规则。"
- 符合 AGENTS.md 触发规则：Host 内部 selector/projection 修复不触发 README 更新。

## Open Questions

- 无。

## Residual Risk

- **Reactive tier1-3 compact recovery deferred**：`WU-CM-12-S4-R1` 保留为 deferred-with-owner。Owner 需要由用户或 GitHub Issue 分配。不阻断本 WU。
- **`CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200` 硬编码 schema 约束**：如果 future slices 需要支持更长 current input，需要 schema 变更。当前行为（不 compact、走 fallback）是正确的 fail-closed 设计。
- **`EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096` evidence chunk 分块**：是确定性分块而非截断，chunk 带 provenance。符合 design.md "chunking with provenance"。
- **Control doc 常量审计清单**：control doc 要求 "final closeout 必须输出一份代码常量审计清单"。当前 WU 尚未完成 final closeout，该清单为 final closeout 输出物。

## Validation

- `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_public_compact_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py -q`：**330 passed, 1 skipped**。
- `pyright dayu/ tests/ utils/`：**0 errors, 0 warnings, 0 informations**。
- `git diff --check`：**无 whitespace 错误**。

## Conclusion

**PASS** — WU-CM-12 S1-S5 累计变更通过 aggregate deepreview：
1. `docs/host/design.md` 已作为设计真源，讨论稿不再替代真源。实现与 design.md no silent truncation/no preview/assemble/fallback tiers/five semantic memories 一致。
2. `MemoryProjectionPolicy` 已成为 LLM-facing material 产量单一 owner。私有 cap/截断常量已删除或明确标记为非 LLM-facing。
3. turn_group_id/floor/fallback caps 正确保护 Host run group，不打散 floor，不用后续小块绕 cap。
4. compact input / ordinary RunInput / fallback RunInput 的 selected-id/source-ref/provenance guard fail closed 且同源。
5. Tier1-3 proactive recovery 和 tier4/5 fallback state machine 正确。S4 reactive recovery deferred 有 owner 且不阻断本 WU。
6. S5 public smoke reconciliation 正确：超长 current input 不截断、不调用 compactor、不写 compact artifact、fallback 成功。
7. Active residual table 只保留真正 deferred-with-owner 项，已关闭 residual 有 artifact 依据。
8. README decision 符合 AGENTS.md。

330 tests passed, 1 skipped / pyright 0 errors / git diff --check clean。无 blocker。仅剩 final closeout 常量审计清单待输出。
