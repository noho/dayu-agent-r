# WU-PROJ-01 Slice 2 Code Review - AgentMiMo

## Review Scope

- diff: uncommitted changes on `wu-proj-01`
- files: `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py`, `tests/host/test_compact_material.py`, `tests/host/test_dispatch_scheduler.py`, `docs/host/issues-implementation-control.md`
- design sources: `docs/host/design.md` (Ch.24–25), `docs/engine/design.md` (Ch.15)
- plan: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- implementation report: `docs/reviews/wu-proj-01-slice2-implementation-codex.md`

## Verdict

**APPROVE** — 无 blocking findings。实现与 plan 和 design 对齐，dead code 清理完整，测试覆盖充分。

## Findings by Severity

### PASS — Plan Checklist 全部通过

| 检查项 | 结果 | 证据 |
|---|---|---|
| proactive budget 使用 `material_view.budget_fragments` | ✅ | `dispatch.py:1023` — `message_fragments=material_view.budget_fragments` |
| `_prepare_compact_before_dispatch` / `select_compact_segment` / `build_compact_material_pack` 使用同一冻结 view | ✅ | `dispatch.py:1157` 传 `material_view`；`dispatch.py:1570–1580` 用 `material_view.material_blocks` |
| `build_compact_material_pack` 传 `previous_compacted_view=material_view.previous_compacted_view` | ✅ | `dispatch.py:1579` |
| `CompactionRequest` refs 从 material view / selection 派生 | ✅ | `_selected_evidence_refs` / `_selected_raw_turn_refs` 从 `material_view.material_blocks` + `selected_block_ids` 派生；`older_raw_turn_refs` 使用 `selected_material_source_refs` |
| 旧 `_proactive_material_blocks` / memory snapshot evidence 去重职责已删除 | ✅ | `grep` 确认 `_proactive_material_blocks`、`_proactive_represented_evidence_refs`、`_latest_session_compacted_event_before_input`、`read_latest_memory_snapshot_at_or_before`、`CONVERSATION_MEMORY_CONSUMER_ID`、`digest_memory_projection_policy`、`accepted_evidence_mapping_refs`（非 `_for_candidate` 变体）均从 dispatch.py 移除 |
| material source failure fail unstarted Run，不创建 Attempt，不 fallback | ✅ | `dispatch.py:967–1017` — catch Exception → `_append_compaction_failed_event` + `_fail_unstarted_in_transaction`，直接 return |
| compactor/config failure fallback 只在已有可信 material view 时使用 | ✅ | `_append_compaction_failed_with_proactive_fallback` 签名要求 `material_view: PreDispatchCompactMaterialView`；hard-threshold path (`dispatch.py:1052–1085`) 直接 fail closed 不进 fallback |
| reactive path 只做 previous view 最小适配 | ✅ | `engine_ingest.py:1327–1332` 只取 `.previous_compacted_view`，不改 multi-pass / overflow freeze |
| `_readable_query_text_from_envelope` full query atom path 已测试 | ✅ | `test_compact_material.py:test_pre_dispatch_evidence_uses_full_tool_call_query_atom` 覆盖 `TOOL_CALL_REQUESTED` → `semantic_query_text` 完整路径 |
| pyright / test validation 可信 | ✅ | pyright 0 errors；32 + 18 + 6 tests passed |

### INFO — 非 Blocking 观察

#### INFO-1: reactive 路径 budget estimate 仍只用单 fragment

`engine_ingest.py:1284–1296` 的 reactive budget estimate 仍用单一 `BudgetTextFragment(text=display_text)`，未使用 `build_pre_dispatch_compact_material_view` 返回的 `budget_fragments`。

这是 accepted plan 的 scope 内行为（implementation report 已声明 residual risk），不阻塞本次 review。但需注意：如果 reactive overflow 发生在已有大量 delta material 的 Session 上，budget estimate 会低估实际 input token，可能导致 compactor 被触发后发现 budget 不够用而 rejection。后续 owner 应考虑将 reactive budget 也升级到同源 material view。

#### INFO-2: `_MinimalSummaryCompactor` 测试 fixture 假设 trace_material 非空

`test_dispatch_scheduler.py:609` — `_MinimalSummaryCompactor.run_prepared_compactor_proposal` 取 `trace_material[0]`。如果某个测试场景的 material pack 恰好 trace_material 为空，会抛 `IndexError`。当前所有使用该 fixture 的测试均确保 trace material 非空（因为有 old + current 两个 user input），但若未来新增边界测试场景需注意。

#### INFO-3: `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 调整了 budget 阈值

该测试将 `context_window_size` 从默认值改为 200，`soft_threshold_tokens` 改为 60，`hard_threshold_tokens` 改为 160。这是合理的：新的 `budget_fragments` 包含了 previous view + delta + current input 全量 token，比旧的单 fragment estimate 更大，需要更宽松的阈值以确保 compact 能正常触发。改动本身正确，但建议在测试注释中说明调参原因。

## Blocking Open Questions

无。

## Residual Risks

1. **reactive path budget estimate 未使用同源 material view** — 本次 scope 外，已记录为后续 owner 事项（INFO-1）。
2. **reactive multi-pass / overflow material freeze / evidence-block 分段** — 按 accepted plan 留给后续 owner，implementation report 已声明。
3. **`_readable_query_text_from_envelope` limited-signal 分支** — 当 `requested_event_ref` 为 None、request row 不存在、session mismatch、event type mismatch、或 `tool_call_request_atoms` 抛异常时，返回 limited-signal 文本。这些降级路径在 `test_compact_material.py` 中通过 Slice 1 的既有测试覆盖，本次 Slice 2 不引入新的 limited-signal 场景。

## Gate Bookkeeping Review

`docs/host/issues-implementation-control.md` 的 gate 状态更新正确：

- gate: `implementation` → `code review` ✅
- implementation status: 更新为 Slice 2 completed + awaiting two-lane review ✅
- next entry point: 更新为 code review gate via AgentMiMo and AgentDS ✅
- Slice 2 section: status 更新、implementation artifact 记录、changed files 记录、validation 结果记录均完整 ✅
- review artifacts expected: 列出了 `mimo` 和 `ds` 两个 artifact ✅
