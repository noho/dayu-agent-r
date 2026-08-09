# Code Review — Gateflow S4 (F11/F12) MiMo Independent Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `HEAD` (`eadee40932cff2113e944620dcbac1bf187ab799`)
- Output file: `docs/reviews/code-review-wu-cli-interactive-02-s4-mimo-20260801-210345.md`
- Included scope: 全部 workspace unstaged/staged changes (5 文件), 新增 `dayu/host/compaction_terminal.py`, 新增 `tests/host/test_compaction_terminal.py`, AGENTS.md, plan §8, implementation artifact
- Excluded scope: 无
- Parallel review coverage: 无

## Review Method

独立阅读以下全部材料后执行 adversarial review：

1. `git diff HEAD` — 全部 5 文件 1665 行 diff
2. `dayu/host/compaction_terminal.py` — 新增 292 行 production
3. `tests/host/test_compaction_terminal.py` — 新增 756 行 owner tests
4. `AGENTS.md` — 架构/编码/语义所有权约束
5. `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` §8 — F11/F12 设计规范
6. `docs/reviews/gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md` — implementation artifact
7. 现有 production: `dispatch.py`, `engine_ingest.py`, `proactive_compaction.py` 关键 call chains

## Findings

未发现实质性问题。

以下记录验证过程与每个 adversarial 验证维度的结论。

## Verification Record

### V1: transaction-local shared terminal owner 覆盖所有 request-backed proactive/reactive writer

**验证方法**: 逐行走读 `begin_compaction_terminal_commit_in_transaction` 入口 → `dispatch.py` 4 个调用点 → `engine_ingest.py` 1 个调用点 → `proactive_compaction.py` 1 个调用点（只读判定） → AST inventory test 固定调用数。

**结论**: 覆盖完整。

- `dispatch.py` 的 `_prepare_compact_before_dispatch` (2 处: invalid/exhausted + missing compactor), `_execute_proactive_compaction` (1 处: late outcome), `_run_pre_start_governance` (1 处: resume snapshot invalid fallback) — 共 4 处，全部在同一 write transaction 内首先调用 shared owner。
- `engine_ingest.py` 的 `_execute_reactive_compaction` (1 处: outcome commit) — 同一 write transaction 内首先调用。
- `proactive_compaction.py` 的 `read_proactive_compaction_projection` (1 处: 只读 terminal disposition 判定) — 不写 terminal，只读取 owner 判定并传入 `_project_state` 交叉验证。
- AST inventory test (`test_compaction_terminal_writer_inventory_uses_only_shared_owner`) 固定 dispatch=4, engine=1, proactive=1, 且 proactive_source/dispatch_source/engine_source 均不含 `terminal_count`。
- hard-threshold-before-dispatch、material-source precondition、reactive precondition diagnostic 没有 `CONTEXT_COMPACTION_REQUESTED`，不是 request-backed terminal writer，不需覆盖。

### V2: first truth / late loser / INVALID_MULTIPLE 在 artifact/descriptor/rejected/terminal/fallback/start 前收口

**验证方法**: 逐行走读每个调用点的 `CompactionTerminalClosed` 处理分支，确认 late loser 在任何 durable 写入前返回 no-op。

**结论**: 收口正确。

- `dispatch.py` proactive outcome: `isinstance(terminal_commit, CompactionTerminalClosed)` → warning log + return `_GovernanceStageResult(pending_dispatch=None, compact_accepted=None)`。不写 artifact、descriptor、rejected event、terminal event、fallback、recovery start。
- `dispatch.py` resume/missing compactor fallback: 同模式，return no-op。
- `engine_ingest.py` reactive outcome: 同模式，return `pending.result_prefix`（已写 request 的 ingest result）。不写 artifact、descriptor、rejected event、terminal event、recovery start/fail-close。
- `INVALID_MULTIPLE` 在所有 proactive/reactive caller 中显式 `raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)`，保留已有 truth，不追加第三 terminal。

**反例验证**:
- `test_proactive_late_accepted_result_preserves_first_failed_truth`: compactor 在 await 期间先写 failed terminal，late accepted 零 artifact/descriptor/event/fallback/start。
- `test_proactive_same_operation_terminal_contenders_preserve_first_truth` (2 parametrized): barrier 两个相反 outcome，winner 先提交后 loser 零 durable 写入。
- `test_reactive_same_pending_terminal_race_preserves_first_truth` (2 parametrized): 同模式。
- `test_proactive_invalid_multiple_terminals_fail_closed_without_third_or_start`: 注入 2 terminal，`HostDurableError` 抛出，不追加第三。
- `test_reactive_invalid_multiple_terminals_fail_closed_without_third_or_start`: 同模式。

### V3: projection 是否产生第二 owner

**验证方法**: 逐行走读 `proactive_compaction.py` 的 `read_proactive_compaction_projection` → `_project_state`，确认 terminal disposition 只从 shared owner 派生。

**结论**: 不产生第二 owner。

- `read_proactive_compaction_projection` 在 `_project_state` 前调用 `begin_compaction_terminal_commit_in_transaction`，把 `terminal_state` 传入 `_project_state`。
- `_project_state` 用 `terminal_sequence`（来自 `terminal_state.first_terminal_event_sequence`）替代旧 `terminal_count`。
- manifest/rejection 的 "after terminal" 检查从 `terminal_count > 0` 改为 `terminal_sequence is not None and row.event_sequence > terminal_sequence` — 语义等价但精确绑定到 owner 投影的 first terminal sequence。
- compacted/failed terminal 行的交叉验证：`not isinstance(terminal_state, CompactionTerminalClosed) or terminal_state.disposition is not <expected> or terminal_state.first_terminal_event_sequence != row.event_sequence` — 要求 projection 看到的 terminal 行与 owner 投影完全一致。
- 旧 `terminal_count > 1` 检查已删除（由 owner 的 `INVALID_MULTIPLE` disposition 替代）。
- 旧 `terminal_count` 变量已删除。AST inventory test 固定 `terminal_count` 不在 proactive/dispatch/engine source 中。

### V4: per-Session flight 正确 coalesce、无 exit race

**验证方法**: 逐行走读 `_signal_pre_start_governance` → `_run_pre_start_governance_flight` → `wake_queue_promotion` → `_enqueue_requeued_promotion` → `_promotion_drain_loop` → `close`。

**结论**: coalesce 正确，无 exit race。

**信号合并**:
- `wake_queue_promotion`: 已有 flight → `rerun_requested=True`，不入队。已在 pending set → 不重复入队。否则加入 pending set + promotion queue。
- `_signal_pre_start_governance`: 已有 flight → `rerun_requested=True` + `await shield(task)`。否则创建新 task/flight。
- `_enqueue_requeued_promotion` (transient backoff callback): 同 `wake_queue_promotion` 的 flight/pending 检查。
- 三个入口（wake/periodic/direct）都收敛到同一 flight 机制。

**Exit race 分析**:
- `_run_pre_start_governance_flight` 的 "check bit → delete entry" 区间无 `await`，event loop 原子。
- 信号只能在两个时机到达：(a) check 前 — bit 被置位，loop 继续；(b) delete 后 — flight entry 已不存在，`wake_queue_promotion`/`_enqueue_requeued_promotion` 创建新 flight。
- `call_soon` 边界测试 (`test_pre_start_flight_exit_boundary_signal_starts_fresh_flight`): pass 返回后 `call_soon(wake_queue_promotion)` 在 flight 删除后创建新 flight，`pass_count==2` 且 `_pre_start_flights == {}`。

**Caller cancel**:
- `asyncio.shield(flight.task)` 阻止 caller cancel 传播到 flight task。
- `test_pre_start_flight_is_parallel_per_session_and_close_owned`: caller cancel 后 flight task 未完成 (`done() is False`)。

**Scheduler close**:
- `close()` 取消所有 `_active_tasks`（含 flight tasks），`_suppress_task_cancel` 等待完成。
- flight task 被 cancel → `CancelledError` → finally block 清理 flight entry。
- `test_pre_start_flight_is_parallel_per_session_and_close_owned`: close 后 `_pre_start_flights == {}`。

**Fresh owner recovery**:
- live compactor await 期间重复 signal 只置 bit；flight 完成后 fresh pass 看到 terminal/dispatch 后 no-op。
- 只有 fresh owner 重启后从 durable `CONTEXT_COMPACTION_REQUESTED` 恢复同 operation/snapshot/budget/next-attempt。
- `test_live_compactor_flight_coalesces_wake_and_periodic_without_recovery`: barrier 期间 `provider_calls == 1`, `prepared_requests == 1`, release 后 `terminal_count == 1`, `prepared_attempt_numbers == (1,)`。

### V5: 测试有无弱化、race 假证明、scope 越界

**验证方法**: 逐个阅读新增/修改测试，检查断言强度、barrier 设计、scope 边界。

**结论**: 无弱化、无 race 假证明、无 scope 越界。

**断言强度**:
- terminal race tests 断言 `_event_log_types_after_cursor(cursor_after_winner) == ()`（精确到游标后零新增）、`_compact_artifact_files` 不变、`_payload_descriptor_count` 不变、`RUN_STARTED`/attempt count 不变。这是对 late loser 零副作用的最强可用断言。
- F12 tests 断言 `pass_count == 2`（精确合并次数）、`_pre_start_flights == {}`（无泄漏）、`provider_calls == 1`（无重复 provider）、`prepared_requests == 1`（无重复 request）、`CONTEXT_COMPACTION_REQUESTED == 1`（无重复 request event）。

**Barrier 设计**:
- `_TerminalWinningProactiveCompactor`: 在 compactor await 内用独立 write transaction 写 first terminal，返回 late accepted — 精确模拟 I0543 时序。
- `_contending_attempt`: 两个 barrier event 控制两个 contender 的释放顺序 — 精确模拟 A-first/B-late 和 B-first/A-late。
- `_BlockingAfterManifestCompactor`: manifest 后 provider await 阻塞 — 精确模拟 live compactor 期间的重复 signal。

**Existing test adjustments**:
- `test_second_proactive_compact_uses_previous_view_without_old_raw_replacement`: `drain_once()` → `_wait_for_final_request_count` — 适配 F12 signal 机制，不弱化断言。
- `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback`: `drain_once()` → `_wait_for_event_count("ATTEMPT_RUNNING", 1)` — 等待真实 durable 证据而非调度计数。
- `test_pre_start_governance_compact_failure_is_attempt_free`: factory 加 `accepted_handle=_CloseCountingHandle()` — 恢复 HEAD 原值（implementation artifact §3.1 已记录）。
- `test_wake_queue_promotion_requeues_after_transient_exception`: 取消 reconciliation task 防止干扰，monkeypatch 目标从 `run_queue_promotion` 改为 `_signal_pre_start_governance` — 适配新入口。

**Scope 边界**:
- 所有测试只在 plan §8.1 允许的文件范围内。
- `test_compaction_terminal.py` 只测试 `compaction_terminal.py` 的 owner contract。
- `test_dispatch_scheduler.py` 的 F12 tests 使用 `_run_queue_promotion_with_lease` monkeypatch 隔离 flight 逻辑。
- `test_engine_ingest_mapping.py` 的 F11 tests 使用 `run_compaction_operation` monkeypatch 隔离 reactive outcome。

## Open Questions

无。

## Residual Risk

1. **periodic reconciliation 与 flight 的交互**: `reconcile_owned_sessions_once` 现在通过 `_signal_pre_start_governance` 间接执行，其 `OwnedSessionReconciliationResult.dispatched` 计数来自 flight 的 `bool` 返回值。flight 的 `dispatched` 是 "任一 pass 创建 stable dispatch" 的 OR 归约。如果多个 periodic one-shot 入射同一 Session，每次都 `await shield(task)`，返回值一致。这符合语义但与旧 "每轮独立计数" 行为不同。非 correctness 风险，仅是 observability 差异。

2. **`_promotion_pending_session_ids` 生命周期**: set 在 `wake_queue_promotion` / `_enqueue_requeued_promotion` 中增长，在 `_promotion_drain_loop` dequeue 时收缩。如果 drain task 因未捕获异常退出，set 中的条目不会被清理；但下次 `wake_queue_promotion` 会重启 drain task。实际风险极低，因为 drain loop 已捕获 `RuntimeError`、`HostTransactionRetryExhaustedError` 和 `CancelledError`。

3. **proactive_compaction.py `_project_state` 交叉验证的 store corruption 假设**: 如果 durable store 在同一 transaction 内出现 terminal owner 说 OPEN 但 projection 看到 terminal row 的不一致，代码会 raise `HostDurableError`。这是正确的 fail-closed 行为，但该假设在正常 SQLite transaction isolation 下不可能发生。记录为理论防御，非实际风险。

## Conclusion

S4 F11/F12 实现与 plan §8 设计规范一致。terminal owner 覆盖完整，late loser/INVALID_MULTIPLE 收口正确，projection 不产生第二 owner，per-Session flight coalesce/exit-race/close/cancel 生命周期正确，测试无弱化或 race 假证明。未发现实质性问题。Next gate: S4 controller adjudication。
