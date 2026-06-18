# Code Review

## Scope

- Mode: current changes
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/code-review-wu-cm-12-s5-mimo-20260618.md
- Included scope: WU-CM-12 S5。文件：`dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/memory.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_memory_projection.py`、`tests/host/test_public_compact_smoke.py`、`docs/reviews/wu-cm-12-s5-implementation-codex-20260618.md`。
- Excluded scope: S1-S4 已接受变更；reactive recovery（S4 明确 deferred）；Engine message dataclasses；EventLog/durable schema；public API。
- Parallel review coverage: 无。单一 reviewer 逐链路走读全部 S5 变更。

## Findings

未发现实质性问题。

## Review Checklist 逐项结论

### 1) Proactive fallback selected-id 同源修复 — PASS

**检查项**: `EventLogContextFallbackProvider` 重建 EventLog-backed frozen material view，`RunInputBuilder` fallback 渲染优先用 `fallback.material_blocks`；是否保持 tier4 recent-window/floor/caps 语义，没有退化为 current-only。

**直接证据**:

- `context_fallback.py:379-406`：Provider 读取 `trigger_source`，当 `PROACTIVE` 时调用 `_proactive_material_blocks_for_window` 重建 material view，挂到 `ActiveRecentWindowFallback.material_blocks`。
- `context_fallback.py:410-454`：`_proactive_material_blocks_for_window` 调用 `build_pre_dispatch_compact_material_view`（与 dispatch.py proactive compaction 同源 builder）获取 delta material blocks，再追加 `_current_input_material_block_for_fallback` 构造 current input block。block_id 格式 `current:{current_input_ref}` 与 `build_run_input_material_blocks` 一致。
- `run_input.py:1901-1915`：`RunInputBuilder` 优先使用 `fallback.material_blocks`（provider 提供的 frozen view），fallback 为 `None` 时才使用 `build_run_input_material_blocks` 构造 ordinary view。
- `test_pre_start_governance_compact_failure_is_attempt_free`：断言 `selected_block_ids` 包含 `"eventlog:user:event-input-run-compact-failure-old"`（historical floor block）和 `f"current:event-input-{seeded.run_id}"`（current input），证明 fallback 仍选择 recent-window floor block，未退化为 current-only。断言 `"older fallback floor material that must render" in rendered` 证明 floor block 被实际渲染到 Engine messages。
- `ActiveRecentWindowFallback.material_blocks` 字段（行 252）：`tuple[RunInputMaterialBlock, ...] | None = None`，`__post_init__` 中 `_require_block_tuple` 校验（行 284-285）。
- Reactive path 不触发重建（`trigger_source != PROACTIVE` 时 `material_blocks` 保持 `None`），fallback 到 ordinary view，行为不变。

### 2) Provenance guards 仍 fail closed — PASS

**检查项**: selected source refs / selected material view digest / protected group guards 是否仍 fail closed。

**直接证据**:

- `run_input.py:2751-2763`：`_fallback_context_messages` 调用 `_selected_material_render_view`，传入 `fallback_material_blocks`（优先 provider frozen view）。
- `run_input.py:2776-2818`：`_selected_material_render_view` 执行全部 S3 guards：
  - duplicate selected ids（行 2782-2783）
  - missing selected id（行 2787-2788）
  - current_input_ref mismatch（行 2790-2791）
  - source_refs mismatch（行 2793-2794）
  - fallback_input_digest mismatch（行 2796-2800）
  - selected_material_view_digest mismatch（行 2802-2806）
  - protected group consistency（行 2808-2812）
- S5 改动不影响 guard 逻辑，只改变 `material_blocks` 来源（provider frozen view vs ordinary view）。Guard 校验对象不变：selected ids、source refs、digest、protected groups。

### 3) `_facts_from_accepted_event` 修复 — PASS

**检查项**: 是否只 whole-drop invalid empty evidence_labels item，不丢此前 valid facts，不改 public/durable/EventLog contract。

**直接证据**:

- `memory.py:1823-1832`：原逻辑 `return ((), tuple(diagnostics) + (...))` 改为 `diagnostics.append(...)` + `continue`。
- 修复行为：遇到 `evidence_labels` 为空的 fact candidate 时，记录 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` diagnostic，跳过该 candidate，继续处理后续 facts。此前已 append 的 valid facts 保留在 `facts` list 中。
- 不改变返回值类型 `tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]`。
- 不改变 public API、durable schema 或 EventLog 语义。`_fact_candidate_invalid_diagnostic` 是既有 diagnostic helper。
- `test_accepted_compact_keeps_valid_fact_before_empty_evidence_labels`：构造 valid fact 在前、empty evidence_labels fact 在后的 payload，断言 `evidence_backed_facts` 只包含 valid fact 的 `claim_text`，断言 diagnostic 包含 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`。

### 4) Public compact smoke 超长 current input 预期 — PASS

**检查项**: 超长 current input smoke 是否符合 `docs/host/design.md` no truncation/no preview：不调用 compactor、不写 compact artifact、走 dispatch fallback。

**直接证据**:

- `compaction.py:680`：`CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200`。`CurrentInputAnchorVNext.text` 有 `_require_bounded_non_empty_text` 校验（行 665-668）。
- `design.md:2966`："candidate 文本必须非空且受 policy char cap 限制"。
- `design.md:3263`："禁止截断 semantic item text"。
- `test_proactive_compact_duplicate_prompt_falls_back_without_lossy_anchor`：原断言 `len(fake_compactor.prompt_lengths) == 1` 改为 `fake_compactor.prompt_lengths == []`（不调用 compactor）。原断言 compact artifact 存在改为 `_compact_artifact_files(...) == ()`（不写 compact artifact）。Run 仍然 `SUCCEEDED`（走 dispatch fallback）。
- `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 和 `test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` 改用 `_soft_threshold_prompt()`（短 current input），确保需要 compact 的 smoke 能正常进入 compactor。
- 最终结果：`11 passed, 1 skipped`。

### 5) README decision 和 residual reconciliation — PASS

**检查项**: README decision 和 residual reconciliation 是否充分。

**直接证据**:

- README decision（implementation artifact 行 42-46）：已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md`。Host 改动是内部 proactive fallback selected-id 同源修正和 memory projection invalid candidate 处理，不改变 public Host API、装配方式、稳定开发手册入口或用户工作流。Test 改动不改变测试目录结构、运行方式或维护规则。不更新 README。
- Residual reconciliation（implementation artifact 行 31-38）：
  - `WU-CM-12-S1-R1`：已修复（`_facts_from_accepted_event` empty evidence_labels 丢弃问题）。
  - `WU-CM-12-S4-R1`：deferred follow-up / intentional non-goal（reactive tier1-3 recovery 超出 S5 scope）。
- Residual risk（implementation artifact 行 62-64）：reactive tier1-3 recovery deferred；current `ConversationCompactInputVNext` 无法表示超 1200 字符 current input。

## Open Questions

- 无。

## Residual Risk

- Reactive tier1-3 compact recovery remains intentionally deferred（S4 已知 scope boundary）。
- `_proactive_material_blocks_for_window` 在 provider read transaction 内重建 material view。如果 EventLog 在 fallback 写入后、provider 读取前新增了 compact event，material view 可能与 fallback payload 不一致。但 S3 guards（source refs、digest）会检测到漂移并 fail closed，不会静默渲染错误 context。
- `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200` 是硬编码 schema 约束。如果 future slices 需要支持更长 current input，需要 schema 变更。

## Conclusion

**PASS** — S5 实现的 proactive fallback selected-id 同源修复、`_facts_from_accepted_event` 修复、public compact smoke 调整均正确：
1. Provider 重建 EventLog-backed frozen material view，RunInputBuilder 优先使用，保持 tier4 recent-window/floor/caps 语义。
2. Provenance guards 仍 fail closed，不受 material_blocks 来源变更影响。
3. `_facts_from_accepted_event` 只 whole-drop invalid candidate，不丢此前 valid facts。
4. 超长 current input 不调用 compactor、不写 compact artifact、走 dispatch fallback，符合 design.md no truncation/no preview。
5. README decision 和 residual reconciliation 充分。

312 tests passed / pyright 0 errors / git diff --check clean。无新 blocker。
