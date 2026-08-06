# Code Review — AgentDS

## Verdict

**PASS** — 无 blocking defect。实现正确对应 accepted plan 的全部 owner contract、算法结构与生命周期规则。发现 2 项 medium findings 与 1 项低严重度 finding，均可在后续 iteration 中处理，不阻塞 merge。

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `b222b8b064f096d899a9de708e45cd1fb6e732e6` (accepted plan commit)
- Output file: `docs/reviews/pr-190-f14-code-review-ds-20260806.md`
- Included scope:
  - `dayu/host/compact_material.py` (production owner)
  - `tests/host/test_compact_material.py` (owner tests)
  - `tests/host/test_run_input_builder.py` (integration fixture update)
  - `tests/host/test_dispatch_scheduler.py` (integration fixture update)
  - `docs/host/design.md` (design truth update)
  - `dayu/host/README.md` (developer overview update)
- Excluded scope: Engine、prompt、provider、UI、Service、CLI、财报工具、Oracle（均不在 plan scope）
- Parallel review coverage: 无（全部由 AgentDS 单路走读）

## Reference Documents

- Accepted plan: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`
- Goal confirmation: `docs/reviews/f14-goal-confirmation-20260806-221301.md`
- S1 implementation record: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`
- Project instructions: `AGENTS.md`

## Findings

### 1-NEEDS_FIX-Medium-`_conservative_unconsumed_row_start_sequence` 的 `group[0].event_sequence` 缺少显式 minimum-sequence 断言

- **入口/函数**: `_conservative_unconsumed_row_start_sequence` → for 循环内 unconsumed group 分支
- **文件(行号)**: `dayu/host/compact_material.py:2762`
- **输入场景**: 当 `grouped[run_id]` 内 rows 的 EventLog sequence 不严格单调递增时（即组内首行不是最小 sequence），`group[0].event_sequence` 会取到偏大的值，导致保守扫描起点晚于该组内其他更早 row，使部分 rows 在 `row.event_sequence >= conservative_start` 过滤时被丢弃。
- **实际分支**: `if not seen_unconsumed: first_unconsumed_sequence = group[0].event_sequence`
- **预期行为**: 应以 `min(row.event_sequence for row in group)` 作为该组的最早 sequence。
- **实际行为**: 取 `group[0].event_sequence`，隐式依赖两个不变量：(a) `grouped` dict 的 list 按 rows 遍历顺序（EventLog sequence ASC）构建，因此 `group[0]` 是 rows 中该 run_id 的首次出现 row；(b) EventLog 中同一 Run 的事件严格按 USER_INPUT_ACCEPTED → RUN_SUCCEEDED → TOOL_RESULT_ACCEPTED 连续写入，因此首次出现 row 即最小 sequence row。
- **直接证据**:
  - L2731-2734: `grouped` 由遍历 `rows` 构建，rows 来自 `SELECT ... ORDER BY event_sequence ASC`（L2698）。`grouped[run_id][0]` 是该 run_id 在全局 ordered rows 中的最小 event_sequence row。
  - L2762: `first_unconsumed_sequence = group[0].event_sequence` — 使用 `group[0]` 而非 `min(...)`。
  - plan L116: "若未来引入任意位置的显式保护，必须先修改本 owner contract 与 proof，不能静默复用本算法" — plan 自身已预见到此不变量可能被打破。
- **影响**: 当前生产环境下两个不变量均成立，此代码在当前行为上正确。但若未来引入非连续 Run 事件（如 attachment recovery 事件插入 Run 中间）或 `explicit protected_recent_raw_turn` 标记使组内顺序变化，`group[0]` 可能不再是最小 sequence，导致部分 rows 被错误丢弃且不触发任何 fail-closed 检查。此时 stage 2 atomic proof 会看到不完整的 unit（缺少被丢弃的 row 对应的 block），触发 `ValueError` → `HostDurableError` 或 partial unit corruption 检测，因此不是静默数据丢失。但错误信号（"atomic grouping is invalid"）不如"group ordering assumption violated"直指根因。
- **建议改法和验证点**:
  1. 将 `first_unconsumed_sequence = group[0].event_sequence` 改为 `first_unconsumed_sequence = min(item.event_sequence for item in group)`，消除对 group 内顺序的隐式依赖。不需要额外 SQL 查询。
  2. 或在 `_conservative_unconsumed_row_start_sequence` 开头显式断言 `rows` 按 `event_sequence` 单调递增（防御），并在 docstring 中明确 `group[0]` 是最小 sequence 的前提。
  3. 验证点：构造 group 内 row 顺序非 USER_INPUT_ACCEPTED-first 的 fixture（如 RUN_SUCCEEDED at seq 5, USER_INPUT_ACCEPTED at seq 7），断言 conservative_start 正确取 min(5, 7) = 5。
- **修复风险（低）**: `min()` 调用为 O(n) per group，但 group 内 rows 数量极有限（通常 1-4 条），对整体性能无影响。
- **严重程度（中）**: 当前行为正确，但隐式不变量缺少显式防护。plan 已明确预见该不变量可能在未来被打破，应在此修复中一并加固。

### 2-NEEDS_FIX-Medium-`_conservative_unconsumed_row_start_sequence` 跳过整组后 row 可能因 conservative_start 偏差被投影

- **入口/函数**: `build_pre_dispatch_compact_material_view` → `_conservative_unconsumed_row_start_sequence` → filter `row.event_sequence >= conservative_start`
- **文件(行号)**: `dayu/host/compact_material.py:538-540` 与 `L2762`
- **输入场景**: 当 Run group A 被 label 为 consumed（user anchor 在 consumed 集合中），但其 answer/evidence rows 的 `event_sequence` 值 ≥ conservative_start（即后面某个 unconsumed group 的起点 sequence），这些 rows 会被送入 typed projector 并被 `_unconsumed_atomic_material_blocks` 处理。
- **实际分支**: L2760 `continue`（跳过 consumed group），L538-540 `row.event_sequence >= conservative_start` 过滤（consumed group 的后续 rows 若 sequence ≥ conservative_start 仍进入投影）。
- **预期行为**: consumed group 的所有 rows 不进入 typed projector（更高效），且 atomic proof 判定为 consumed。
- **实际行为**: 当前实现对 "consumed group 的 user anchor event_id 在 consumed_set 中，但同组 answer/evidence block 的 canonical_source_refs 也在 consumed_set 中" 的前提成立——因为 accepted compact boundary 的 selector 是 atomic 的（整组入选或整组排除），`compacted_source_refs` 必然包含同组所有已入选 blocks 的 source_refs。因此 atomic proof 也会判定这些 blocks 为 consumed，最终从 `material_blocks` 中正确删除。行为正确。
- **直接证据**:
  - `_user_input_delta_block` L2872: `canonical_source_refs=(row.event_id,)`
  - `_assistant_answer_delta_block` L2907: `canonical_source_refs=(row.event_id,)`
  - `_accepted_tool_evidence_delta_blocks` L2955: `canonical_source_refs=(projection.evidence_id,)`
  - `_accepted_compacted_source_refs` L2384-2390: consumed 集合来自 `compacted_source_refs`，该值由 `CompactAcceptedTruthV4` 的 boundary entries 的 represented/omitted coverage source_refs 并集构成（compact_payload.py L163-182）。由于 selector 的 atomicity 保证整组入选时所有 block 的 source_refs 均在其中，user anchor consumed ↔ group consumed 是对的。
- **影响**: 当且仅当 selector atomicity 不变量被打破时（例如 future work 允许 partial group selection），consumed group 的非 user rows 会被投影，atomic proof 会发现它们的 canonical_source_refs 不在 consumed 中，标记为 unconsumed 并保留。此时 `first_unconsumed_sequence` 和 `material_blocks` 可能不一致（consumed user block 缺失，但同组 answer/evidence blocks 仍在 suffix）。`_atomic_material_units` 会因为缺少 user block（非 turn_group 成员）或 membership 不完整而抛 `ValueError` → `HostDurableError("unconsumed material atomic grouping is invalid")`，fail-closed。因此当前行为在当前不变量下正确，在不变量被打破时 fail-closed。
- **建议改法和验证点**:
  1. 在 `_conservative_unconsumed_row_start_sequence` 或 `_unconsumed_atomic_material_blocks` 的 docstring 中显式声明"user anchor consumed ⇔ all group blocks consumed"依赖 selector atomicity 担保，并交叉引用 selector 的 `turn_group_memberships_for_material_blocks` / `_atomic_material_units` 作为该不变量的 owner-level proof。
  2. 可选（不强制）：在 `_conservative_unconsumed_row_start_sequence` 返回的 `conservative_start` 上，额外插入一层轻量校验——验证所有 `event_sequence < conservative_start` 的 rows 的 `run_id` 组确实全部被 consumed group 覆盖，无遗漏。这只需检查 row metadata 而不解析 payload。但当前 stage 2 atomic proof 已提供等价的 fail-closed 保护，新增校验会重复覆盖。
  3. 验证点：构造 fixture 其中 user anchor consumed 但 answer block's canonical_source_ref NOT in consumed（模拟 selector atomicity 被打破），断言 `HostDurableError` 而非静默通过。当前 `test_pre_dispatch_partial_atomic_coverage_fails_closed` 已覆盖 partial unit consumption，但未覆盖"user anchor consumed 但同组 block 不在 consumed"的特定场景。
- **修复风险（低）**: 建议仅为文档增强，不影响运行时行为。
- **严重程度（中）**: 正确性当前无缺陷，但关键不变量缺少跨函数显式文档与 owner reference。这在 future work 引入 partial group selection 或 protected marker 时可能被忽略。

### 3-NEEDS_FIX-Low-`_accepted_compacted_source_refs` docstring raises 格式不规范

- **入口/函数**: `_accepted_compacted_source_refs`
- **文件(行号)**: `dayu/host/compact_material.py:2381`
- **输入场景**: 静态代码审查。
- **实际分支**: `:raises Exception: 不主动抛出异常。` — `Exception` 不是实际可能抛出的类型，且该声明不符合 Python docstring 规范（raises 应列出具体异常类型；如果函数不抛出异常，不应写 raises）。
- **预期行为**: 将 `:raises Exception: 不主动抛出异常。` 删去，或在 Returns 行后补充说明"本函数不主动抛出异常，仅做纯数据转换"。
- **实际行为**: 误导读者认为可能抛出 `Exception`。
- **直接证据**: L2381。
- **影响**: 文档误导，无运行时影响。
- **建议改法和验证点**: 删去 `:raises Exception: 不主动抛出异常。` 行。
- **修复风险（低）**: 纯文档修改。
- **严重程度（低）**: 不影响代码行为，仅影响可维护性。

## Correctness Verification — 无 Finding 的正确性确认项

以下各项经逐行走读确认正确，不构成 finding，但记录审查轨迹：

### A. accepted chain 完整性

- `_accepted_compact_chain_before_current_input` 从 SQL 只读取 `CONTEXT_COMPACTED` + `CANONICAL_FACT` 行（L2247-2262），`CONTEXT_COMPACTION_ATTEMPT_REJECTED` / `CONTEXT_COMPACTION_FAILED` 不会匹配 `CONTEXT_COMPACTED`，正确排除非 accepted 事件。
- 每条 row 经过 `read_event_by_id` → `_require_canonical_session_event` → `_validated_compacted_payload` → `parse_context_compacted_semantic_payload` → `_validate_accepted_compact_entry_references` 五层校验，任一层失败抛 `HostDurableError`。
- `event_sequence` 双重校验（SQL 返回的 sequence 与 `read_event_by_id` 返回 row 的 sequence 比对，L2279），防止 concurrent write 导致的 phantom change。

### B. current input 与 previous compact 引用严格校验

- `_require_prior_canonical_event_ref` 要求 ref exact 指向同 Session (`_require_canonical_session_event` 检查 session_id)、更早 (`referenced.event_sequence >= owner_event.event_sequence` 抛错) 的指定 type 的 canonical event。
- `current_input_ref` 必须指向 `USER_INPUT_ACCEPTED`（L2323）。
- 所有 `PREVIOUS_*` source_kind 的 source_refs 必须指向 `CONTEXT_COMPACTED`（L2335）。
- `test_pre_dispatch_accepted_chain_rejects_invalid_current_input_reference` 覆盖 missing/cross-session/forward 三种非法场景。
- `test_pre_dispatch_accepted_chain_rejects_invalid_previous_compact_reference` 覆盖 missing/self/cross-session/forward 四种非法场景。

### C. atomic Run group 与 prefix proof

- `_unconsumed_atomic_material_blocks` 的 block-level check（L2826-2830）：`canonical_source_refs` 中任一 ref 部分匹配 → `HostDurableError`。由于 evidence block 的 `canonical_source_refs` 只包含 `projection.evidence_id`（L2955），user/answer block 只包含 `row.event_id`（L2872, L2907），block 内 refs 数极少（通常 1 个），此检查足够精确。
- unit-level check（L2836-2839）：同一 unit 内 blocks 必须同为 consumed 或同为 unconsumed。
- prefix check（L2841-2846）：consumed → unconsumed transition 只能发生一次，之后不能再出现 consumed unit。
- `test_pre_dispatch_partial_atomic_coverage_fails_closed` 覆盖 unit 内混合消费场景。
- 三项检查互补，形成 fail-closed 闭环。

### D. protected suffix 保护

- `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix` 证明 accepted terminal（seq 10）位于 protected group（seq 5-9）之后，但 protected group 因不在 boundary 中而保持未消费。`post_compact_delta_start_sequence` 正确返回 5（protected group 最早 sequence），而非旧实现的 11（terminal+1）。
- 同一测试的 restart 段（L911-928）证明关闭/reopen durable store 后重建的 view 与原始 view exact 相等。

### E. evidence ownership 与 opaque ID 区分

- `_accepted_tool_evidence_delta_blocks` 的 `canonical_source_refs` 使用 `projection.evidence_id`（格式 `evidence:event-tool-result-*`），而非 `row.event_id`（producer EventLog id）。
- `_compacted_payload` fixture 中 `accepted_evidence_refs` 使用 evidence ID 格式（如 `evidence:event-tool-result-before-compact`），而 `source_refs_by_label` 中 evidence 的 source_refs 也使用相同格式。
- `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix` 中使用 `evidence:event-tool-result-consumed-prefix` 作为 evidence ref，而非 `event-tool-result-consumed-prefix`，明确测试 evidence ID 与 producer EventLog ID 不相等。

### F. 失败 / cancelled / stale 生命周期

- 只有 `CONTEXT_COMPACTED`（`event_type='CONTEXT_COMPACTED'`）进入 `_accepted_compact_chain_before_current_input` 的 SQL 查询。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED`、`CONTEXT_COMPACTION_FAILED` 等非 accepted event type 不进入查询 → 不推进 frontier。
- `test_pre_dispatch_non_accepted_compaction_events_do_not_advance_frontier`（L1226-1330）覆盖 rejected + failed 不推进。

### G. 同源投影

- `represented_evidence_refs` 继续只从 latest entry 的 `accepted_evidence_mapping_refs` 获取（L512-513），语义不变（latest replacement 逐 fact refs union）。
- `previous_compacted_view` 只从 latest entry 的 `accepted_replacement` 构造（L518-522）。
- `latest_compacted_event_id/sequence` 只从 latest entry 的 event 获取（L549-555），只作为 provenance 暴露，不作为 consumption cursor。
- Material frontier 独立从 `consumed_source_refs` + `_unconsumed_atomic_material_blocks` 派生，不与 terminal sequence 互相推导。

### H. 性能 fail-closed

- Partial block/unit coverage → `HostDurableError`（L2829-2831, L2836-2839）。
- Non-prefix coverage → `HostDurableError`（L2841-2846）。
- `_atomic_material_units` 的 `ValueError` → 转为 `HostDurableError`（L2819-2820）。
- `_post_compact_delta_start_sequence` 中 material_block 的 `event_sequence=None` → `HostDurableError`（L2650-2652）。
- 无静默 truncation、fallback、兼容分支或默认值处理 corruption。

### I. 测试真实性

- 所有 coverage-sensitive fixtures 现在显式提供真实 `current_input_ref` 与 per-label `source_refs_by_label`（如 `_append_compacted_event`、`_compacted_payload`、`_compact_payload`），而非 synthetic `source:T1` 标签。
- `test_pre_dispatch_second_compact_rolls_from_latest_accepted_proposal` 等旧测试已更新为使用真实 refs，消除 fixture 与生产 behavior 的语义 gap。
- `_append_retained_previous_compacted_event`（L2142-2200）正确构造只 retain 一个 previous EvidenceFact 的 compact candidate，通过 `build_context_compacted_payload` + `accepted_truth_for_test_candidate` 生成与生产代码同源的 compact payload。
- `test_pre_dispatch_previous_compact_ref_preserves_uncovered_raw_material`（L1441-1543）证明 previous compact ref 只提供 rolling provenance 而不消费未覆盖 raw groups。

## Open Questions

- 无。

## Residual Risk

- **Selector atomicity 不变量未跨模块显式担保**: `_conservative_unconsumed_row_start_sequence` 的 user-anchor proof 依赖 `turn_group_memberships_for_material_blocks` 的 selector atomicity + `compacted_source_refs` 的完整 boundary coverage 两个不变量。它们在当前生产中均成立（同一 `_atomic_material_units` helper），但未被显式交叉引用。已在 Finding 2 中建议文档增强。
- **Production CLI observation 未在本 gate 执行**: real provider behavior validation 留给 Controller 后续 formal observation 流程。deterministic owner tests 已独立证明 frontier correctness，provider 非确定性不应混入 owner correctness judgement。此风险已由 S1 implementation record 明确记录。
- **全仓 frozen publication manifest 4 failures**: 范围外既有 baseline inconsistency，与 F14 代码变更无交集（manifest files 未被修改）。
- **全仓 Ruff 89 errors**: 全部位于本轮未修改文件，changed files focused Ruff 通过。

---

**Reviewer**: AgentDS
**Timestamp**: 2026-08-06T23:33:56+08:00
**Base**: b222b8b064f096d899a9de708e45cd1fb6e732e6
**Files reviewed**: 6 changed files (3 production, 3 test), full adversarial pass with state machine, atomic proof, ownership, 同源投影, and fail-closed verification.
