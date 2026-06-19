# Code Review

## Scope

- Mode: current changes
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/code-review-wu-cm-12-s4-mimo-20260618-164733.md
- Included scope: WU-CM-12 S4 Tier 1-3 Compact Recovery Fallback。文件：`dayu/host/dispatch.py`、`dayu/host/compact_material.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_compact_material.py`、`docs/reviews/wu-cm-12-s4-implementation-codex-20260618.md`。
- Excluded scope: S1/S2/S3 已接受变更；reactive recovery（S4 明确 out of scope）；Engine message dataclasses；EventLog/durable schema；public API。
- Parallel review coverage: 无。单一 reviewer 逐链路走读全部 S4 变更。

## Findings

### 1-未修复-中-Recovery tier accepted 后 `accepted_attempt_number` 只计 recovery tier 内部 rejected attempts，遗漏 normal compaction 和前置 recovery tier 的 rejected attempts

- **入口/函数**: `HostDispatchScheduler._governance_compact_pending` / `_accepted_attempt_number`
- **文件(行号)**: `dispatch.py:1336-1364`（recovery loop）、`dispatch.py:1450-1459`（`_append_compacted_event` 调用）、`dispatch.py:4101-4108`（`_accepted_attempt_number`）
- **输入场景**: normal compaction 有 N 个 rejected attempts，recovery tier 1 失败（1 rejected attempt），recovery tier 2 accepted（0 rejected attempts）。
- **实际分支**: `accepted_result = tier_result`（`dispatch.py:1363`）→ `_accepted_attempt_number(accepted_result)` 返回 `len(tier2_result.rejected_attempts) + 1 = 1`。
- **预期行为**: `accepted_attempt_number` 应反映从 normal compaction 到 accepted recovery tier 的总 attempt 序号（例如 normal 2 rejected + tier 1 1 rejected + tier 2 accepted = attempt 4）。
- **实际行为**: `accepted_attempt_number` 只反映 accepted recovery tier 内部的 attempt 序号（总是 1，因为 recovery tier `max_attempts=1` 且 accepted 时 `rejected_attempts` 为空）。
- **直接证据**:
  - `_accepted_attempt_number`（`dispatch.py:4108`）：`return len(result.rejected_attempts) + 1`。
  - Recovery tier 调用（`dispatch.py:1342-1348`）：`max_attempts=1`，accepted 时 `rejected_attempts` 为空 tuple。
  - `_append_compacted_event`（`dispatch.py:1459`）：`accepted_attempt_number=_accepted_attempt_number(accepted_result)` — 传入的是 recovery tier 的 result。
- **影响**: `CONTEXT_COMPACTED` payload 中 `accepted_attempt_number` 诊断字段不准确。不影响 compacted event 的语义正确性（accepted candidate、quality、manifest 均正确），但 observability 降级。
- **建议改法和验证点**:
  1. 在 recovery loop 中累计 rejected attempts：`total_rejected = len(result.rejected_attempts)`，每 tier 失败后 `total_rejected += len(tier_result.rejected_attempts)`。
  2. 用累计值构造 `accepted_attempt_number`：`total_rejected + 1`。
  3. 验证：补充测试断言 recovery accepted 后 `CONTEXT_COMPACTED` payload 的 `accepted_attempt_number` 等于 normal rejected + tier rejected + 1。
- **修复风险（低）**: 只影响诊断字段，不改变 compaction 语义。
- **严重程度（中）**: 不影响正确性，但 `CONTEXT_COMPACTED` payload 的 `accepted_attempt_number` 诊断不准确，影响问题排查。

### 2-未修复-低-`test_proactive_compaction_recovery_stale_after_tier_proposal_discards` 实际测试的是 stale-after-normal-compaction，不是 stale-after-recovery-tier-proposal

- **入口/函数**: `_RecoveryScenarioCompactor.run_prepared_compactor_proposal`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py:3232-3267`
- **输入场景**: `_RecoveryScenarioCompactor(accept_call=2, stale_after_call=2)` — normal compaction call 1 失败，recovery tier 1 call 2 触发 stale。
- **实际分支**: Call 2（recovery tier 1）→ `_fail_unstarted_for_stale_test` 先于 `accept_call` 检查执行 → Run 被置为 failed → compactor raise RuntimeError → `run_compaction_operation` 返回 failure result → cancellation token 检测到 stale → break。
- **预期行为**: 测试名暗示测试 "tier proposal 返回后 stale 不写 CONTEXT_COMPACTED"。应有一个场景：tier proposal 成功返回 accepted candidate，但 commit 前 Run 变 stale。
- **实际行为**: 测试场景是 recovery tier proposal 本身因 Run 已 failed 而失败（compactor raise RuntimeError），不是 proposal 成功后 commit 前变 stale。行为正确（stale detected, no CONTEXT_COMPACTED written），但测试覆盖的场景与名称不符。
- **直接证据**:
  - `_RecoveryScenarioCompactor.run_prepared_compactor_proposal`（`dispatch.py` 测试 helper）：`_fail_unstarted_for_stale_test` 在 `accept_call` 检查前执行。
  - 断言：`compactor.calls == 2`（call 1 = normal fail, call 2 = recovery stale），`CONTEXT_COMPACTED == 0`，`CONTEXT_COMPACTION_FAILED == 1`。
- **影响**: 测试名与实际覆盖场景不一致，可能误导后续维护者认为 stale-after-accepted-recovery-proposal 已被覆盖。
- **建议改法和验证点**:
  1. 重命名测试为 `test_proactive_compaction_recovery_stale_during_tier_proposal_discards` 以反映实际场景。
  2. 可选：补充一个测试，用 `stale_after_call` 在 `accept_call` 之后制造 stale（例如 `accept_call=2, stale_after_call=3`），验证 accepted recovery proposal 在 commit 前被正确丢弃。但这需要 `_fail_unstarted_for_stale_test` 在 compactor 返回后、token check 前执行，当前 helper 设计不支持此时序。
- **修复风险（低）**: 纯测试修正。
- **严重程度（低）**: 测试行为正确，只是名称不精确。

## Open Questions

- 无。

## Residual Risk

- **Reactive recovery 未实现**: S4 实现 artifact 明确声明 "本 slice 只闭环 proactive recovery"。Reactive path（`engine_ingest.py`）的 `run_compaction_operation` 未插入 recovery loop。这是 plan 内已知的 scope boundary，不是遗漏。
- **Recovery tier failure 未写入 tier 专属 durable metadata**: 实现 artifact 声明 "Tier failure proposal 未写入 tier 专属 durable metadata"。`CONTEXT_COMPACTION_FAILED` payload 的 schema 与 tier 4/5 fallback 保持既有形状，不区分 normal failure 和 recovery failure。这是有意的 schema stability 设计。
- **`_sort_recovery_previous_blocks` 的 `eventlog-seq:` 前缀解析**: 依赖 `canonical_source_refs` 中的 `eventlog-seq:<n>` 格式。如果 future slices 改变 compact block 的 source ref 格式，排序逻辑可能需要同步更新。当前 `_max_recovery_source_event_sequence` 对不匹配的 ref 返回 `None`，触发 material-order fallback，是正确的防御性设计。

## Review Checklist 逐项结论

### 1) proactive-only 是否可接受

**结论: PASS。** S4 plan 要求 "在 normal compaction 无 accepted 后、写 CONTEXT_COMPACTION_FAILED / tier 4 fallback 前插入 bounded tier 1-3 recovery"。Reactive path（`engine_ingest.py`）有独立的 compaction flow、cancellation token 和 compact count limit。Plan 未显式要求 S4 recovery 覆盖 reactive path。实现 artifact 和 residual risk 均明确声明 proactive-only。Reactive recovery 是 future scope。

### 2) tier 1/2/3 按顺序执行，每 tier 至多一次 run_compaction_operation

**结论: PASS。** `_proactive_compaction_recovery_attempts`（`dispatch.py:1479-1545`）按顺序构造 tier 1/2/3：
- Tier 1: `bounded_selection`（fallback caps）+ `previous_compacted_view`。
- Tier 2: `pending.request.segment_selection`（original selection）+ `degraded_previous_view`（只在 degrade 有效时添加）。
- Tier 3: `bounded_selection` + empty `previous_compacted_view`。

Recovery loop（`dispatch.py:1338-1364`）对每个 tier 调用 `run_compaction_operation(max_attempts=1)`，accepted 后 break。`_compaction_result_accepted` 检查 `accepted_candidate`、`quality_result`、`failure_reason`。全部失败后进入 `_operation` transaction，走既有 `_append_compaction_failed_with_proactive_fallback` 路径。

### 3) stale checks 覆盖 tier attempt 前、proposal 返回后、commit 前

**结论: PASS（有注意事项）。** Stale check 三层覆盖：
1. **Tier attempt 前**: `cancellation_token.is_cancelled()`（`dispatch.py:1340`）在每个 tier 前检查。Token 检查 Run status、input cursor、Session missing/closed。
2. **Proposal 返回后**: `cancellation_token.is_cancelled()`（`dispatch.py:1350`）在 tier `run_compaction_operation` 返回后检查。
3. **Commit 前**: `_operation` transaction 内（`dispatch.py:1366-1411`）重新读取 Run 和 Session 状态。`_run_session_allows_proactive_compaction`（`dispatch.py:3854-3869`）检查 Session open 且未 closed。

注意事项：stale-after 测试（Finding 2）实际测试的是 stale-during-proposal，不是 stale-after-accepted-proposal。但 commit 前的 recheck（第 3 层）覆盖了 accepted proposal 的 stale 场景。

### 4) select_compact_segment 新参数不破坏 normal compact/reaction selection

**结论: PASS。** `max_selected_item_count` 默认 `None`。当 `None` 时：
- `budget_blocked` 始终 `False`（`dispatch.py:927`，不会被设为 `True`）。
- `if budget_blocked:` 分支（`dispatch.py:929`）永远不进入。
- `len(selected) > 0 or max_selected_item_count is not None` 等价于 `len(selected) > 0`（原行为）。
- `if max_selected_item_count is not None and ...`（`dispatch.py:945`）永远不进入。

Normal compact 和 reactive selection 不传 `max_selected_item_count`，行为不变。

### 5) section-aware degrade 是否只 whole-drop

**结论: PASS。** `degrade_previous_compacted_view_for_recovery`（`compact_material.py:984-1017`）按 `_RECOVERY_PREVIOUS_VIEW_KIND_PRIORITY` 遍历 kind，只保留最高优先级非空 section 的原始 blocks。不截断、不改写、不合成新 summary。`_sort_recovery_previous_blocks` 在所有候选有 `eventlog-seq:` source ref 时按最大 sequence 降序，否则回退到 material order。

### 6) tests 覆盖

**结论: PASS（有缺口）。** 已覆盖：
- Tier 1 accepted（`test_proactive_compaction_recovery_tier1_uses_fallback_caps`）：断言 `compactor.calls == 2`、`CONTEXT_COMPACTED == 1`、`CONTEXT_COMPACTION_FAILED == 0`、tier 1 request 的 segment 和 trace material 内容。
- Tier 2 accepted（`test_proactive_compaction_recovery_tier2_degrades_previous_view`）：断言 `compactor.calls == 3`、previous view 只保留 EVIDENCE_BACKED_FACT、文本 byte-exact。
- Tier 3 accepted（`test_proactive_compaction_recovery_tier3_uses_delta_only`）：断言 `compactor.calls == 4`、previous view 为空、delta material 保留。
- Stale before（`test_proactive_compaction_recovery_stale_before_tier_attempt_discards`）：断言 `CONTEXT_COMPACTED == 0`、`CONTEXT_COMPACTION_FAILED == 1`。
- Stale after（`test_proactive_compaction_recovery_stale_after_tier_proposal_discards`）：断言同上（实际测试 stale-during-proposal）。
- All tiers fail（`test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback`）：断言 `compactor.calls == 4`、`CONTEXT_COMPACTED == 0`、`CONTEXT_COMPACTION_FAILED == 1`、dispatch fallback 生效。
- Compact material helpers：strict fallback item cap、char cap 不绕序、section-aware degrade deterministic keep/drop、source sequence 降序。

缺口：`accepted_attempt_number` 在 recovery accepted 后不准确（Finding 1）；stale-after-accepted-recovery-proposal 未被显式测试（Finding 2）。

### 7) implementation artifact residual risk 是否充分

**结论: PASS。** Residual risk 声明：
- "本 slice 只闭环 proactive recovery" — 与代码一致。
- "Reactive recovery 未扩展" — 与代码一致。
- "execution replacement guard 对 proactive 无 execution id 可比对" — 正确，proactive path 的 `CompactionRequest` 的 `attempt_id` 和 `execution_id` 均为 `None`。
- "Tier failure proposal 未写入 tier 专属 durable metadata" — 与代码一致，`CONTEXT_COMPACTION_FAILED` payload schema 不变。

## Conclusion

**PASS（有 1 个中 severity finding）** — S4 实现的 tier 1-3 recovery loop 设计正确：按顺序执行、每 tier 至多一次 `run_compaction_operation`、accepted 走既有 `_append_compacted_event`、stale check 三层覆盖（token 前、token 后、commit 前）、`select_compact_segment` 新参数不影响 normal path、section-aware degrade 只 whole-drop。1 个中 severity finding：recovery accepted 后 `accepted_attempt_number` 诊断不准确（不影响 compaction 语义正确性）。118 tests passed / pyright 0 errors / git diff --check clean。
