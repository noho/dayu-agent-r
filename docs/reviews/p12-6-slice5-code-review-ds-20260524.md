# P12.6 Slice 5 Code Review — AgentDS

## 基本信息

- **Reviewer**: AgentDS
- **Gate**: P12.6 Slice 5 implementation
- **Base**: 410a620 gateflow: accept P12.6 slice 4
- **Scope**: Proactive / Reactive Context Governance 接线与 reactive multi-pass single-operation durable semantics
- **Reviewed files**: `dispatch.py`, `engine_ingest.py`, `compaction_operation.py`, `context_events.py`, `compact_artifact.py`, `context_budget.py`, `README.md`, `test_dispatch_scheduler.py`, `test_engine_ingest_mapping.py`, `test_compaction_operation.py`, `test_context_budget.py`
- **Excluded**: `docs/host/implementation-control.md`（controller-only）
- **References**: AGENTS.md, `docs/host/design.md` §24/§25, implementation plan Slice 5, Codex completion report

## Verdict: PASS

8/8 plan-specified tests 存在且可防御回归。核心语义（proactive 不再使用 Session 起点 range collector、reactive 冻结 overflow material list、multi-pass 共享 budget 单 operation 提交、reactive 不以估算阻断 recovery dispatch、stale/failure fail closed）均已正确落地。无停止条件触发。发现 2 个 HIGH 问题需要关注，但均不阻塞接受。

---

## Findings

### P1-HIGH

#### D1. `_selected_material_source_refs` 重复定义

- **文件/行号**: `dispatch.py:3252-3259`, `engine_ingest.py:3316-3348`
- **证据**: 两个完全相同的函数体，参数、逻辑、返回值一致，分别位于 `dispatch.py` 与 `engine_ingest.py` 模块级私有函数。
- **影响**: DRY 违规。后续任一修改路径必须同步两处，否则出现语义漂移。两个调用方（proactive `_maybe_start_compaction` 与 reactive `_reactive_compaction_request` / `_reactive_compaction_pass_queue`）均需该逻辑。
- **建议**: 将 `_selected_material_source_refs` 提取到 `compact_material.py` 或 `run_input.py` 作为模块级公共 helper，`dispatch.py` 与 `engine_ingest.py` 统一导入。若仅在 Host internal 使用，放入 `compact_material.py` 与 `RunInputMaterialBlock` 相邻最自然。

---

#### D2. `_merge_pass_candidates` 摘要/补丁只取最后 pass

- **文件/行号**: `compaction_operation.py:282-293`（`_merge_pass_candidates`），`compaction_operation.py:319-320`
- **证据**:
  ```python
  episode_summary_candidate=last.episode_summary_candidate,
  pinned_state_patch_candidate=last.pinned_state_patch_candidate,
  ```
  当 `len(candidates) > 1` 时，只保留最后一个 pass 的 `episode_summary_candidate` 与 `pinned_state_patch_candidate`，前序 pass 的 summary/patch 被静默丢弃。相比之下，`evidence_backed_fact_candidates`、`minimum_preserve_item_candidates`、`preservation_evidence`、`dropped_ranges`、`summarized_ranges` 均正确拼接并去重保留所有 pass 的结果。
- **影响**: 当前 `_reactive_compaction_pass_queue` 每个 pass 只看到单个 material block（+ current input anchor）。pass 1 产出的 summary（覆盖 block A）在 merge 时被丢弃，只剩下 pass N 对 block N 的 summary。merge 后的 `episode_summary_candidate` 不能完整反映本次 compaction operation 覆盖的所有 material block 语义。
- **分析**: 这个行为在 plan §6.7 未明确指定 merge 策略，且 Codex completion report 承认"中间产物当前只在 operation 内存中合并"。但最终提交的 `CONTEXT_COMPACTED` payload 会包含所有 pass 的 facts/minimum_preserve/ranges → 后续 memory projection 仍可从中恢复完整信息。因此实际危害有限（summary 本身只是导航层，不替代 facts），但也说明当前 summary text 在多 pass 场景下是不完整的。
- **建议**: 明确 merge 策略并写回 design/plan。可选方案：(a) 要求最后一个 pass 的 compactor 同时看到所有前序 pass 的 summary 进行最终整合（增加一次 LLM 调用）；(b) 拼接所有 pass summary（可能导致重复）；(c) 当前行为保持不变但文档显式说明 `episode_summary_candidate` 在多 pass 场景下的局限性。

---

### P2-MEDIUM

#### D3. `budget_after_compact` 在 merge 时取 min 而非重新计算

- **文件/行号**: `compaction_operation.py:342`
- **证据**:
  ```python
  budget_after_compact=min(candidate.budget_after_compact for candidate in candidates),
  ```
  merge 后 candidate 的内容（deduped ranges/facts/items）与原 pass candidate 不同，但 `budget_after_compact` 直接取所有 pass 中的最小值，不基于 merged content 重新估算。
- **影响**: 保守估计（取 min）在数值上不会高估 budget savings，不会导致 hard threshold 误判为 pass。但可能低估实际 savings（dedup 后内容更少），使后续决策偏保守。对 reactive path 不构成功能问题（reactive 不用 hard threshold gate），对 proactive path（单 pass 不触发 merge）也无实际影响。纯 code quality 观察。
- **建议**: 若后续 multi-pass 扩展到 proactive 路径或引入更多 consumer，应在 merge 后按 merged content 重新估算 budget。当前可接受但建议加 comment 说明 `min()` 的选择理由。

---

#### D4. `_reactive_compaction_pass_queue` 的 pass segment selection 存在间接 fallback 路径

- **文件/行号**: `engine_ingest.py:2888-2904`
- **证据**:
  ```python
  selection = select_compact_segment(
      ...,
      policy_digest=f"{pending.frozen_material_list_digest}:{block_id}",
      material_blocks=pending.frozen_material_blocks,
      max_selected_size_units=0,
  )
  if block_id not in selection.selected_block_ids:
      selection = _single_block_segment_selection(...)
  ```
  先尝试通过 `max_selected_size_units=0` 让 `select_compact_segment` 决定是否选择该 block（利用 size 限制迫使 selection 为空），若 block 未被选中再手动构造 `_single_block_segment_selection`。逻辑等价于"如果 budget 允许就通过标准 selection 选单个 block，否则强制单选"，但 `max_selected_size_units=0` 作为 trick parameter 不够显式。
- **影响**: 功能正确，无 bug。但 `max_selected_size_units=0` 的语义是"最多选 0 size units"，用于测试单个 block 是否在 budget 内，读者需推断才能理解。若 `select_compact_segment` 的行为在未来变更中对 `max_selected_size_units=0` 的处理方式改变，可能产生边缘行为差异。
- **建议**: 考虑抽取 `_select_single_block_segment()` helper 直接实现"为单个 block 构造 reactive pass selection"，消除对 `max_selected_size_units=0` trick 的依赖。

---

#### D5. `collect_compaction_request_evidence_inputs` 仍有导出声明

- **文件/行号**: `compaction_evidence.py:152`, `compaction_evidence.py:582`（`__all__`）
- **证据**: `dispatch.py` 与 `engine_ingest.py` 均已移除对该函数的 import 和调用，但函数体与导出声明仍在 `compaction_evidence.py` 中保留。
- **影响**: dead export。不影响 Slice 5 功能，但若被其他模块意外 import 使用，会绕过 material-pack-based 的新 contract。
- **建议**: Slice 7 最终清理时应删除该函数及其 `__all__` 条目，确保没有遗漏的外部调用方。

---

### P3-LOW

#### D6. README 变更只涵盖 multi-pass 语义，未记录 frozen material list

- **文件/行号**: `dayu/host/README.md:258`
- **证据**: README diff 只新增一句："同一 reactive operation 内的 material pass 共享 proposal attempt 预算，只有所有 pass 成功后才提交一个 merged `CONTEXT_COMPACTED`，任一 pass 最终失败只提交一个 `CONTEXT_COMPACTION_FAILED`。"
- **影响**: reactive 路径的 frozen overflow material list 语义（冻结 digest/refs 写入 `CONTEXT_COMPACTION_REQUESTED` payload）未被 README 记录。对于 Host 的使用者/维护者来说，这是理解 reactive compact durable record 的关键信息。
- **建议**: 在 Context Governance README 段补充一句 reactive 冻结 material list 的 durable 语义，不写实现细节，只写稳定行为。

---

## Review Focus 逐项验证

### 1. Proactive 是否不再使用 Session 起点 range collector ✓

- `dispatch.py:1366-1377`: `_proactive_material_blocks` 只使用 `run.input_event_id` 与 `display_text` 构造当前 input anchor material block，不再调用 `collect_compaction_request_evidence_inputs(... start_event_sequence=1 ...)`。
- 旧 import `from dayu.host.compaction_evidence import collect_compaction_request_evidence_inputs` 已删除。
- 无 `start_event_sequence=1` 出现在 dispatch.py 中。

### 2. Reactive 是否冻结 overflow material list ✓

- `engine_ingest.py:1177-1180`: `_frozen_reactive_material_blocks` 通过 `build_run_input_material_blocks` 从当前 Run 状态构造 frozen material blocks。
- `engine_ingest.py:1191-1192`: `_ReactiveCompactPending` 存储 `frozen_material_blocks`, `frozen_material_list_digest`, `frozen_material_refs`。
- `engine_ingest.py:3023-3055`: `_reactive_compaction_request` 使用 `pending.frozen_material_blocks` 构造 segment selection 与 material pack。
- `context_events.py:188-189`: `build_context_compaction_requested_payload` 新增 `frozen_material_list_digest` 与 `frozen_material_refs` 字段写入 EventLog payload。
- 验证通过测试: `test_reactive_freezes_overflow_material_list_before_compaction`

### 3. `run_compaction_operation` multi-pass 语义 ✓

- `compaction_operation.py:326-351`: `_operation_pass_requests` 校验 pass_queue 元素类型与 identity（session_id/run_id/attempt_id/execution_id/trigger_source 必须匹配 root request）。
- `compaction_operation.py:73-322`: 外层 `for pass_request in requests`  + 内层 `while attempt_number <= max_attempts`，`attempt_number` 跨 pass 共享，正确实现 budget 共享。
- `compaction_operation.py:288`: 所有 pass 成功后调用 `_merge_pass_candidates`。
- `compaction_operation.py:289-312`: merge 后再次 quality check + budget acceptance gate。
- 失败时直接 return `CompactionOperationResult(accepted_candidate=None, failure_reason=...)`，不写 partial compacted。
- 验证通过测试: `test_reactive_multi_pass_commits_single_merged_context_compacted`, `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event`, `test_reactive_passes_share_operation_attempt_budget`

### 4. Reactive compact 后不以估算阻断 recovery dispatch ✓

- `compaction_operation.py:423-434`: `_requires_budget_acceptance` 只在 `trigger_source is PROACTIVE` 时返回 `True`。
- `engine_ingest.py`: 无 hard threshold 检查。
- Reactive `_execute_reactive_compact` 成功返回 `_ReactiveRecoveryAccepted` 后由 dispatch 继续 recovery，不再二次校验 budget。
- Proactive hard threshold gate 保留在 `_requires_budget_acceptance` → `run_compaction_operation` 对 PROACTIVE request 的 merged quality check 路径。

### 5. stale/cancel/cursor mismatch fail closed ✓

- `engine_ingest.py:1492-1513`: `sequence_stale` 检测后写入 `stale_compaction_result` failed event，不写 `CONTEXT_COMPACTED`，不返回 `_ReactiveRecoveryAccepted`。
- `engine_ingest.py:1529-1563`: `accepted_candidate is None` 或 `failure_reason is not None` 时写入 `CONTEXT_COMPACTION_FAILED` 并 `_fail_recovering_run`。
- `compaction_operation.py:77-98`: cancellation token 检测后 fail closed，不写 partial compacted。
- 无 `partial` compacted 写入路径。

### 6. Architecture: 无 Engine runner retry / 无新 Run/Attempt state / 无 durable schema change ✓

- 无 `dayu/engine/` 修改。
- 无新增 RunStatus / AttemptStatus 枚举值。
- `context_events.py` 仅在 `CONTEXT_COMPACTION_REQUESTED` payload 新增两个 optional 字段（`frozen_material_list_digest` + `frozen_material_refs`），不改变 event type 或 schema version。
- 无 `Any`、`object`、`hasattr`、`getattr` 出现在新增代码中。
- 无 lazy import / seam。

### 7. Tests 覆盖 ✓

全部 8 项 plan-specified 测试均已实现：

| # | 测试 | 文件 | 真实防回归 |
|---|------|------|-----------|
| 1 | `test_proactive_compaction_uses_selected_material_not_session_start_range` | `test_dispatch_scheduler.py:2456` | 断言 `input_cursor` 等于 run input sequence，无 Session 起点 range |
| 2 | `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` | `test_dispatch_scheduler.py:2497` | 断言 pack 字符数 ≤ ordinary + 512 |
| 3 | `test_reactive_freezes_overflow_material_list_before_compaction` | `test_engine_ingest_mapping.py:4520` | 断言 payload 中有 frozen_material_refs 与 frozen_material_list_digest |
| 4 | `test_reactive_multi_pass_commits_single_merged_context_compacted` | `test_compaction_operation.py:435` | 断言 merged candidate_id 以 "merged:" 开头 |
| 5 | `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event` | `test_compaction_operation.py:451` | 断言 failure_reason="proposal_failed"，无 partial candidate |
| 6 | `test_reactive_passes_share_operation_attempt_budget` | `test_compaction_operation.py:474` | max_attempts=1, 2 passes → 第二个 pass 耗尽 budget |
| 7 | `test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run` | `test_engine_ingest_mapping.py:4750` | 断言 0 COMPACTED, 1 RUN_FAILED, 0 RUN_LOST |
| 8 | `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering` | `test_dispatch_scheduler.py:1278` | 断言 RUN_RECOVERING=0, RunStatus.RUNNING |

测试设计质量：
- 前 3 项（dispatch/ingest 级）通过 fake compactor + durable store 真实触发 scheduler/ingestor 路径，非纯单元 mock。
- 后 5 项（operation/ingest 级）通过 recording/failing fake compactor 验证 multi-pass 行为，含边界条件（budget 耗尽、中间失败）。

### 8. README 只写稳定语义 ✓

- `dayu/host/README.md:258`: 新增一句 multi-pass / merged event 语义。语句是稳定行为描述，不写实现细节或未来计划。
- 无新旧术语并存，无过程状态。
- 建议补 frozen material list durable 语义（见 D6）。

---

## Validation Summary

| 检查项 | 状态 |
|--------|------|
| 无 Session 起点 range collector | PASS |
| Reactive frozen material list + digest | PASS |
| Multi-pass single operation + shared budget | PASS |
| Reactive 无 hard threshold gate | PASS |
| Proactive hard threshold gate 保留 | PASS |
| stale/cancel fail closed，无 partial compacted | PASS |
| 无 Engine runner retry 修改 | PASS |
| 无 Run/Attempt 新状态 | PASS |
| 无 durable schema change | PASS |
| 无 Any/object/hasattr/getattr | PASS |
| 8/8 plan 测试覆盖 | PASS |
| pyright: 0 errors | PASS (per Codex report) |
| pytest: 139 passed | PASS (per Codex report) |
| README 稳定语义 | PASS (建议补 frozen material 语义) |

---

## Residual Risks

1. **Multi-pass merge 策略未写回 design** (D2): `episode_summary_candidate` / `pinned_state_patch_candidate` 的 last-pass-only 行为未在 `docs/host/design.md` §25 或 plan §6.7 中明确。当前行为在功能上不阻塞（facts/preserve/ranges 完整保留），但如果未来 design 要求 multi-pass summary 覆盖全部 compacted material blocks，当前实现不完全满足。建议 Controller 裁决并写回 design。

2. **`_selected_material_source_refs` 重复** (D1): 两处相同实现可能在后续独立演化中漂移，但当前两处逻辑完全一致，不构成功能 bug。

3. **Proactive 路径仅构造 current input anchor material block**: `_proactive_material_blocks` 当前只返回 current input anchor 一个 block。在 pre-start 阶段没有 `AttemptDispatchSnapshot`，无法通过 `build_run_input_material_blocks` 获取完整 memory/history/evidence blocks。这意味着当前 proactive path 的 `select_compact_segment` 只能看到 current input，`selected_block_ids` 必然为空。这是 plan 明确说明的已知限制（见 Codex 报告 §风险与未覆盖项），非 Slice 5 bug，但需 Slice 6 补齐 memory projection 后 proactive material view 才能完整。

4. **`_frozen_reactive_material_blocks` 当 `started_event_id is None` 时退化为 current-only**: 与 proactive 相同的限制——没有 RUN_STARTED 就没有完整 material view。这在 reactive 场景中理论上不应发生（reactive 只出现在 Engine 报告 overflow 时，必然已经 RUN_STARTED），但 defensive fallback 已经就位。

5. **No test for `_merge_pass_candidates` summary loss**: 当前测试 `test_reactive_multi_pass_commits_single_merged_context_compacted` 使用 `FakeContextCompactor`（两次 pass 返回相同 candidate），未覆盖两个 pass 产生不同 summary/patch 时 merge 丢弃前序 pass 数据的行为。建议补充差异化 candidate 的 merge 测试。
