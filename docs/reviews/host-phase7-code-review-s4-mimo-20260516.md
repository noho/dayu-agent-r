# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-review-s4-mimo-20260516.md
- Included scope: Host Phase 7 P7-S4 WAITING Cancel, Late Result Diagnostic, Poll / Manual Adapter, EngineEvent Confirmation — 当前未提交改动
- Excluded scope: Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 7 个审查焦点的逐项 evidence-based 结论：

### 1. cancel_run / cancel_session_runs WAITING 分支

`cancel_run` 在 `admission.py:968-973` 的 WAITING 分支调用 `_cancel_waiting`，后者委托 `cancel_waiting_run_in_transaction`。该分支位于 `QUEUED`(953) 和 `CANCELLING`(962) 之后、terminal replay(974) 之前，不回归 queued/pre-dispatch/active-worker cancel 路径。

`cancel_session_runs` 在 `admission.py:1436-1437` 的 `target.waiting` 分支调用 `_cancel_waiting_target`，同样委托 `cancel_waiting_run_in_transaction`。`_session_cancel_target_for_run`(2305-2333) 对 WAITING Run 构造 `waiting=True` 的 target，Attempt 非 SUSPENDED 时返回 None（排除不合法状态）。分支顺序：QUEUED(1434) → waiting(1436) → active_worker(1438) → predispatch(1440)。

两条路径共享同一 `cancel_waiting_run_in_transaction` transition。取消后 Run 为 CANCELLED、wait records 为 CANCELLED、不创建 resume Attempt。

### 2. cancel_waiting_run_in_transaction CAS/事务/EventLog 顺序

`run_transition.py:1315-1399`：

1. `_validate_cancel_waiting_input` — 输入校验
2. `read_run_by_id` → 检查 `WAITING` + `current_attempt_id is not None`
3. `read_attempt_by_id` → 检查 `SUSPENDED`
4. `read_active_wait_records_for_run` → 确认有 active waits
5. `append_event(CANCEL_REQUESTED)` — line 1355-1357
6. `cancel_active_wait_records_for_run` (CAS WAITING→CANCELLED) — line 1359-1366
7. `append_event(RUN_CANCELLED)` 含 wait_ids — line 1372-1381
8. `cancel_waiting_run_row` (CAS WAITING→CANCELLED with current_attempt_id) — line 1382-1389

EventLog 顺序正确：CANCEL_REQUESTED → wait records mutation → RUN_CANCELLED → Run row CAS。Run CAS 要求 `status=WAITING AND current_attempt_id=<suspended>` 并检查 `terminal_event_id IS NULL`。`cancel_active_wait_records_for_run`(`state.py:2110-2181`) 使用 `UPDATE WHERE run_id=? AND status=WAITING`，CAS 校验 `rowcount == len(before_rows)`。

### 3. late result diagnostic

`waiting.py:624-677` `_resolve_in_transaction` 条件链：

- terminal wait record (RESOLVED/FAILED/LOST)：先尝试 `_replay_terminal_resolution_or_none`
  - 同 key 同 digest → 重放 ✓
  - 同 key 不同 digest → IDEMPOTENCY_CONFLICT ✓
  - 不同 key（无 idempotency record）→ 返回 None
    - RESOLVED/FAILED：`_replay_terminal_resolution_or_none` 返回 None 后 line 637-645 检查 `status in (RESOLVED, FAILED)` → 抛 `INVALID_STATE`，**不写 diagnostic** ✓
    - LOST：不满足 `(RESOLVED, FAILED)` 检查 → line 646-651 `_reject_late_result` → **写 diagnostic** ✓
- CANCELLED：line 652-658 → `_reject_late_result` → **写 diagnostic** ✓
- 非 WAITING（其它状态）：line 659-665 → `_reject_late_result(rejection_reason=INVALID_WAIT_STATE)` ✓
- WAITING 但 owner Run terminal：line 666-677 → `_reject_late_result(rejection_reason=RUN_TERMINAL)` ✓

`wait_late_rejection` 幂等 scope：`_wait_late_rejection_scope(wait_id, idempotency_key)`，scope_kind=`"wait_late_rejection"`。digest 包含 wait_id、run_id、idempotency_key、source、observed_at、wait_status、rejection_reason、outcome_kind、outcome_digest、outcome。同 key 同 digest → 重放返回 `_LateRejectResult`；同 key 不同 digest → `IDEMPOTENCY_CONFLICT`。幂等有界。

### 4. WaitPoller

`wait_adapter.py:1100-1153` `WaitPoller.poll_once`：

- `run_read` 读取 poll wait 快照（`read_wait_records_for_poll_observation`，只返回 `resume_policy=poll` 且 status IN (WAITING, CANCELLED)）— line 1106-1108
- 遍历 records，adapter 调用在 transaction 外 — line 1114-1145
- CANCELLED → `adapter.abandon_wait(record)`，不调用 `resolve_wait` — line 1119-1125
- WAITING → `adapter.poll_wait(record)`
  - `WaitPollNotReady` → 不调用 `resolve_wait` — line 1131-1133
  - `WaitPollReady` → 构造 `ResolveWaitRequest` 调用 `resolve_wait` — line 1134-1141
  - `WaitPollLost` → 同上，outcome 为 `ResolveWaitLostOutcome` — line 1142-1145
- adapter 异常 (`RuntimeError`) → `adapter_errors += 1`，不崩溃 — line 1123-1124, 1128-1130

### 5. EngineEvent ingest 对 TOOL_AWAITING / RUN_SUSPENDED

`engine_ingest.py:721-773` `_confirm_waiting_engine_event`：

- 不创建 wait state、不 close terminal — line 767-773 只返回 `ACCEPTED` + diagnostic event
- 不把已 WAITING Run 失败收口 — 无 `_close_terminal` 调用
- 幂等确认：event_id 基于 candidate 派生，`_existing_rows` 检查重复 → DUPLICATE — line 747-755
- reason 按 run/attempt 状态区分：`waiting_event_confirmation` vs `waiting_event_without_host_accepted_refs` — line 735-739
- `_late_rejection_reason`(1179-1185)：RUN_SUSPENDED/TOOL_AWAITING + WAITING+SUSPENDED → 返回 None（允许通过）；terminal run → 返回 rejection reason（拒绝）
- `_duplicate_terminal_event_ids` 已移除 RUN_SUSPENDED/TOOL_AWAITING 的 terminal event id 生成 — 不再产生 ATTEMPT_FAILED/RUN_FAILED

### 6. README / tests 一致性

- `dayu/host/README.md`：新增 WAITING cancel、late diagnostic、poller 说明；更新 EngineEvent ingest 描述；更新未实现列表
- `tests/README.md`：新增 `test_wait_cancel_late_result.py` / `test_wait_adapter_polling.py` 运行命令；更新测试覆盖描述
- `tests/host/test_engine_ingest_mapping.py`：RUN_SUSPENDED/TOOL_AWAITING 测试从"diagnostic + FAILED"改为"只 diagnostic、不失败收口"，断言 `RUN_FAILED` 事件数为 0、Run/Attempt 状态不变
- 新增 `tests/host/test_wait_cancel_late_result.py`（4 个测试）：cancel_run WAITING、cancel_session_runs WAITING、late diagnostic 幂等有界、resolved/failed 不同 key 不写 diagnostic
- 新增 `tests/host/test_wait_adapter_polling.py`（3 个测试）：ready resolve、not-ready 不调用 resolve、cancelled abandon

### 7. 边界

变更文件：

- `dayu/host/README.md` — 文档同步
- `dayu/host/_event_payload.py` — `wait_late_result_rejected_payload`
- `dayu/host/admission.py` — cancel_run / cancel_session_runs WAITING 分支
- `dayu/host/durable/run_transition.py` — `cancel_waiting_run_in_transaction`
- `dayu/host/durable/state.py` — `cancel_waiting_run_row`、`cancel_active_wait_records_for_run`、`read_wait_records_for_poll_observation`
- `dayu/host/engine_ingest.py` — `_confirm_waiting_engine_event` 替换 `_diagnostic_then_failed_waiting`
- `dayu/host/wait_adapter.py` — `WaitPoller`、`WaitPollAdapter`、`WaitPollAdapterRegistry`
- `dayu/host/waiting.py` — late result diagnostic path
- `tests/README.md` — 测试手册同步
- `tests/host/test_engine_ingest_mapping.py` — 测试适配新行为
- `tests/host/test_wait_cancel_late_result.py` — 新增
- `tests/host/test_wait_adapter_polling.py` — 新增（存在于 unstaged 但未在 diff stat 中显示，可能已被 staged 或为 untracked）

未修改 Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model。

## Open Questions

无。

## Residual Risk

- Poller 是最小单轮 `poll_once()` 实现，不包含后台调度循环、退避、并发 in-flight fencing 或 adapter 错误重试治理。属于已知非目标。
- Engine contract 当前不携带 Host accepted wait refs，P7-S4 只能实现 diagnostic/idempotent confirmation，无法校验"matching refs"。属于已知架构约束。
