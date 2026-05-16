# PR 56 Deep Review — Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter

日期：2026-05-16

## Scope

- Mode: PR
- PR: #56 — Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter
- Repository: noho/dayu-agent-r
- Head branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base branch: main
- Output file: docs/reviews/pr-56-deepreview-mimo-20260516.md
- Included scope: PR #56 全部 74 文件变更（203.4KB diff），含 S1~S5 全量实现
- Excluded scope: Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 4 subagent 全部因 model 不可用失败（API Error 400: Not supported model claude-haiku-4-5-20251001），主 reviewer 直接读取全部关键文件完成审查
- CI: 无 checks 配置

## PR Facts

- Author: noho
- Title: Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter
- State: OPEN (draft)
- Claimed validation: 389 tests passed, pyright 0 errors, git diff --check clean

## Findings

未发现实质性问题。

以下为 7 个审查焦点的逐项 evidence-based 结论：

### 1. ToolRuntime awaiting accept path

`tool_runtime.py:2314-2327`：`_execute_one` 在 dispatch tool call 后、进入 normal accept path 前拦截 `ToolAwaitingOutcome`，路由到 `_accept_awaiting`。这是正确的 — awaiting outcome 跳过 truncation 和 normal fact accept，走专用 awaiting accept path。

`tool_runtime.py:2420-2502` `_accept_awaiting`：

1. 检查 `_awaiting_accept_port` 和 `_wait_adapter_registry` 是否存在（line 2449-2452）
2. 解析 binding（line 2457-2460）；binding 为 None 时返回 governed failure（line 2461-2465）
3. 解析 external_job_ref（line 2466）；POLL policy 且无 ref 时返回 governed failure（line 2467-2474）
4. 构造 `ToolAwaitingAcceptCandidate`（line 2476-2489）
5. 调用 `_accept_awaiting_with_retry`（line 2490）
6. AcceptedAck → 返回原始 `ToolAwaitingOutcome`（line 2491-2498）；不写入 duplicate accepted index，因为 awaiting 是中间态

`tool_runtime.py:2544-2579` `_accept_awaiting_with_retry`：与 fact accept retry 相同模式 — `HostTransactionRetryExhaustedError` 和 `TimeoutError` 归一为 `ToolAwaitingAcceptTimedOut`，rejected ack 不重试。

`tool_runtime.py:2229-2254` batch 执行：`run_suspended_by_awaiting` 标记在首个 awaiting 后设为 True，后续 calls 获得 governed error（`run_suspended_by_tool_awaiting`）。正确 — Run 已 SUSPENDED，不应继续执行后续工具。

### 2. EngineEvent ingest — TOOL_AWAITING / RUN_SUSPENDED diagnostic confirmation

`engine_ingest.py:721-773` `_confirm_waiting_engine_event`：

- 只写 diagnostic event，不创建 wait state，不 close terminal（line 767-773: `terminal_closeout=False`）
- reason 按 run/attempt 状态区分：WAITING+SUSPENDED → `waiting_event_confirmation`；其它 → `waiting_event_without_host_accepted_refs`（line 735-739）
- 幂等确认：event_id 基于 candidate 派生，`_existing_rows` 检查重复 → DUPLICATE（line 747-755）

`engine_ingest.py:1172-1191` `_late_rejection_reason`：

- `RUN_SUSPENDED`/`TOOL_AWAITING` + WAITING+SUSPENDED → 返回 None（允许通过，line 1179-1185）
- terminal run（`terminal_event_id is not None`）→ 返回 rejection reason（拒绝，line 1186-1190）
- 其它 → 返回 None（允许，line 1191）

`engine_ingest.py:1283-1397` `_duplicate_terminal_event_ids`：只处理 `FINAL_ANSWER`、`RUN_FAILED`、`RUN_CANCELLED`、`CONTEXT_COMPACTION_REQUESTED`，末尾 `return ()`（line 1397）。`RUN_SUSPENDED`/`TOOL_AWAITING` 不生成 terminal event id — 正确。

### 3. resolve_wait condition chain — late diagnostic scoping

`waiting.py:624-688` `_resolve_in_transaction` 条件链：

1. terminal wait (RESOLVED/FAILED/LOST)：`_replay_terminal_resolution_or_none`
   - 同 key 同 digest → 重放 ✓
   - 同 key 不同 digest → IDEMPOTENCY_CONFLICT ✓
   - 不同 key → 返回 None
     - RESOLVED/FAILED：line 637-645 检查 `status in (RESOLVED, FAILED)` → 抛 `INVALID_STATE`，**不写 diagnostic** ✓
     - LOST：不满足 `(RESOLVED, FAILED)` 检查 → line 646-651 `_reject_late_result` → **写 diagnostic** ✓
2. CANCELLED：line 652-658 → `_reject_late_result` → **写 diagnostic** ✓
3. 非 WAITING（其它状态）：line 659-665 → `_reject_late_result(rejection_reason=INVALID_WAIT_STATE)` ✓
4. WAITING 但 owner Run terminal：line 666-677 → `_reject_late_result(rejection_reason=RUN_TERMINAL)` ✓

`wait_late_rejection` 幂等 scope：`_wait_late_rejection_scope(wait_id, idempotency_key)`，scope_kind=`"wait_late_rejection"`。同 key 同 digest → 重放返回 `_LateRejectResult`；同 key 不同 digest → `IDEMPOTENCY_CONFLICT`。幂等有界。

### 4. WaitPoller

`wait_adapter.py:1100-1153` `WaitPoller.poll_once`：

- `run_read` 读取 poll wait 快照（`read_wait_records_for_poll_observation`，只返回 `resume_policy=poll` 且 status IN (WAITING, CANCELLED)）— line 1106-1108
- adapter 调用在 transaction 外 — line 1114-1145
- CANCELLED → `adapter.abandon_wait(record)`，不调用 `resolve_wait` — line 1119-1125
- WAITING → `adapter.poll_wait(record)`
  - `WaitPollNotReady` → 不调用 `resolve_wait` — line 1131-1133
  - `WaitPollReady` → 构造 `ResolveWaitRequest` 调用 `resolve_wait` — line 1134-1141
  - `WaitPollLost` → 同上，outcome 为 `ResolveWaitLostOutcome` — line 1142-1145
- adapter 异常 (`RuntimeError`) → `adapter_errors += 1`，不崩溃 — line 1123-1124, 1128-1130

### 5. RunInputBuilder resume continuity

`run_input.py:1072-1115` `_resume_wait_message_from_current_start`：

- 读取 `RUN_STARTED.start_reason`（line 1084-1087）；非 resume → 返回 None
- 读取 `tool_result_event_ref`（line 1089-1091）
- 读取 `TOOL_RESULT_ACCEPTED` event（line 1092-1098）
- 构造 system message 含 wait_id、tool_call_id、tool_name、resolution_kind、tool_fact_kind、result（line 1100-1115）

resume Attempt 的 RunInputBuilder 从 EventLog 重建 accepted wait/tool fact — 正确。

### 6. Schema DDL

`schema.py:459-577` `host_wait_records` DDL：

- CHECK 约束：status enum（`waiting/resolved/failed/cancelled/lost`），terminal_at 与 terminal status 配对，resolve_idempotency_key 与 resolve_semantic_digest 配对
- 索引：`one_active_per_run`（unique partial WHERE status='waiting'），`active_poll`（resume_policy, status, deadline_at, expires_at），`external_job`（adapter_key, external_job_id WHERE NOT NULL）
- 外键：session_id、run_id、attempt_id、execution_id、created/updated event refs
- Schema version 3→4，fresh schema（无 migration）

CHECK 约束覆盖完整。snapshot 字段三元组约束（ref IS NULL AND captured_at IS NULL AND digest IS NULL）OR（ref IS NOT NULL AND captured_at IS NOT NULL）允许 digest 为 NULL — 这是有意设计，digest 是可选完整性校验。

### 7. cancel_run / cancel_session_runs WAITING 分支

`admission.py:968-973` `cancel_run` WAITING 分支调用 `_cancel_waiting`，委托 `cancel_waiting_run_in_transaction`。

`admission.py:1436-1437` `cancel_session_runs` 的 `target.waiting` 分支调用 `_cancel_waiting_target`，同样委托 `cancel_waiting_run_in_transaction`。

两条路径共享同一 transition。取消后 Run 为 CANCELLED、wait records 为 CANCELLED、不创建 resume Attempt。分支顺序正确：QUEUED → waiting → active_worker → predispatch，不回归 queued/pre-dispatch/active-worker cancel 路径。

`run_transition.py:1315-1399` `cancel_waiting_run_in_transaction` CAS/事务/EventLog 顺序：

1. `_validate_cancel_waiting_input` — 输入校验
2. `read_run_by_id` → 检查 `WAITING` + `current_attempt_id is not None`
3. `read_attempt_by_id` → 检查 `SUSPENDED`
4. `read_active_wait_records_for_run` → 确认有 active waits
5. `append_event(CANCEL_REQUESTED)` — line 1355-1357
6. `cancel_active_wait_records_for_run` (CAS WAITING→CANCELLED) — line 1359-1366
7. `append_event(RUN_CANCELLED)` 含 wait_ids — line 1372-1381
8. `cancel_waiting_run_row` (CAS WAITING→CANCELLED with current_attempt_id) — line 1382-1389

EventLog 顺序正确：CANCEL_REQUESTED → wait records mutation → RUN_CANCELLED → Run row CAS。

### 8. resume_run_from_waiting_in_transaction

`run_transition.py` resume path：RESUME_REQUESTED → TOOL_RESULT_ACCEPTED → wait record RESOLVED → RUN_STARTED(resume) → ATTEMPT_STARTED → dispatch record。dispatch wakeup 在 `command.py:508-511` 的事务提交后执行（`wake_dispatch` 在 `service.resolve_wait` 返回后调用）。

### 9. Design Alignment

`docs/host/design.md` §20 要求与实现对照：

| 设计要求 | 实现位置 | 状态 |
|----------|----------|------|
| ToolRuntime Host accept path 是 awaiting canonical owner | `waiting.py` `DefaultHostToolAwaitingAcceptPort` | ✅ |
| Engine tool_awaiting/run_suspended 不能创建 wait state | `engine_ingest.py` `_confirm_waiting_engine_event` — 只 diagnostic | ✅ |
| wait record 是 Host durable state index | `durable/state.py` host_wait_records schema + CAS helper | ✅ |
| resolve_wait 是短事务 command | `waiting.py` `resolve_wait` — single write transaction | ✅ |
| 幂等范围 (wait_id, idempotency_key) | `waiting.py` `_wait_resolution_scope` | ✅ |
| 同 key 同 outcome 重放，不同 outcome 冲突 | `waiting.py` `_resolve_in_transaction` + `_replay_terminal_resolution_or_none` | ✅ |
| cancelled/lost late result → WAIT_LATE_RESULT_REJECTED diagnostic | `waiting.py` `_reject_late_result` | ✅ |
| WAITING cancel → cancelled wait records + CANCELLED Run | `run_transition.py` `cancel_waiting_run_in_transaction` | ✅ |
| resume 是同一 Run 内新 Attempt | `run_transition.py` `resume_run_from_waiting_in_transaction` | ✅ |
| RunInputBuilder 从 EventLog canonical facts 重建 messages | `run_input.py` `_resume_wait_message_from_current_start` | ✅ |
| poll/callback/manual 都走同一 resolve_wait pipeline | `wait_adapter.py` `WaitPoller.poll_once` → `resolve_wait` | ✅ |

### 10. Exit Criteria 验证

Phase 7 退出条件（`implementation-control.md:900-903`）：

| 条件 | 状态 | 证据 |
|------|------|------|
| 长事务工具可以让 Run 进入 WAITING | ✅ | S2: `ToolAwaitingOutcome` → wait record → WAITING/SUSPENDED |
| 由统一 `resolve_wait` 创建新 Attempt 继续 | ✅ | S3: completed/cancelled → resume Attempt + dispatch; S5 集成测试验证 |
| `ResolveWaitRequest.outcome_ref` 已被 typed envelope 替代 | ✅ | S1: `ResolveWaitCompletedOutcome` / `FailedOutcome` / `CancelledOutcome` / `LostOutcome` |
| `observed_at` 类型明确 | ✅ | S1: `datetime`，UTC-aware，`__post_init__` 校验 |
| lost outcome 与 wait record lost 状态区别 | ✅ | S1: `ResolveWaitLostOutcome` vs `WaitRecordStatus.LOST` |
| `adapter_key` 来源明确 | ✅ | S1: `WaitAdapterKey` typed ref，来自 `WaitAdapterRegistry` binding |
| `snapshot_ref` / `external_job_id` typed ref 约束 | ✅ | S1: `HostPayloadRef` / `ExternalJobRef` typed dataclass |

### 11. 验证要求验证

Phase 7 验证要求（`implementation-control.md:893-898`）：

| 要求 | 测试覆盖 |
|------|----------|
| wait record state machine | `test_wait_record_state.py` — 8 tests: schema/row codec/DDL CHECK/CAS helper |
| resolve_wait idempotency | `test_resolve_wait_command.py` — 6 tests: completed resume, same key replay, same key different outcome conflict, failed/lost closeout, lost same key replay, tool-cancelled resume |
| late result rejection | `test_wait_cancel_late_result.py` — 4 tests: cancel_run WAITING, cancel_session_runs WAITING, late diagnostic bounded idempotency, RESOLVED/FAILED different key no diagnostic |
| cancel-vs-resolve first-committer-wins | `test_wait_cancel_late_result.py` — cancel 后 resolve 写 late diagnostic |
| poll adapter observes cancelled wait and stops | `test_wait_adapter_polling.py` — 3 tests: ready resolve, not-ready no resolve, cancelled abandon |
| late result writes diagnostic EventLog event | `test_wait_cancel_late_result.py` — WAIT_LATE_RESULT_REJECTED 事件验证 |
| integration: awaiting -> resumed local run | `test_phase7_waiting_integration.py` — 端到端 manual resolve |
| pyright: wait adapter modules | 0 errors（claimed） |
| docs: Host README wait/resume 语义同步 | README 已更新 WAITING cancel、resolve_wait、late diagnostic、poller、Engine diagnostic |

### 12. 边界验证

变更文件（生产代码）：

- `dayu/host/README.md` — 文档同步
- `dayu/host/__init__.py` — 新 exports
- `dayu/host/_event_payload.py` — 6 new payload helpers
- `dayu/host/admission.py` — WAITING cancel paths
- `dayu/host/api.py` — 新 contracts
- `dayu/host/command.py` — resolve_wait 实现
- `dayu/host/durable/run_transition.py` — 4 new transitions
- `dayu/host/durable/schema.py` — schema v4 + wait records DDL
- `dayu/host/durable/state.py` — wait record CRUD + CAS
- `dayu/host/engine_ingest.py` — `_confirm_waiting_engine_event`
- `dayu/host/run_input.py` — resume continuity
- `dayu/host/tool_runtime.py` — awaiting accept path
- `dayu/host/wait_adapter.py` — WaitPoller + registry
- `dayu/host/waiting.py` — awaiting accept port + resolve_wait service

未修改 Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model。

### 13. Non-goals 验证

Phase 7 non-goals（`implementation-control.md:865-868`）：

| Non-goal | 状态 |
|----------|------|
| 不保证外部 job physical cancel | ✅ 未实现 |
| 不实现 callback 认证入口完整产品化 | ✅ 未实现 |
| 不实现远端 worker 自治 resume | ✅ 未实现 |
| 不实现 HTTP callback endpoint | ✅ 未实现 |
| 不修改 Engine contract | ✅ 未修改 |
| 不把 adapter object / callable 放进 durable wait record | ✅ 只存 typed refs |
| 不做旧库兼容 | ✅ 全新 schema |

## Open Questions

无。

## Residual Risk

以下为 Phase 7 已知非目标，有明确 owner 或属于后续 phase：

1. **callback endpoint / auth / replay**：Phase 7 只预留 `callback` source 和 `resolve_wait` pipeline contract。Owner: 后续 phase。
2. **外部 job physical cancel / revoke**：adapter 只能 best-effort。Owner: 后续 adapter hardening。
3. **Engine contract 不携带 Host accepted wait refs**：P7 只能做 diagnostic confirmation，不能做强 matching-ref 校验。Owner: 后续 Engine contract 扩展。
4. **poller 后台调度循环 / 退避 / in-flight fencing**：当前只有 `poll_once()` 单轮。Owner: 后续 runtime hardening。
5. **recovery scan 对 WAITING Run 处理**：design §20 明确 "Host recovery scan 遇到 WAITING Run 时不得创建新 Attempt"。Owner: Phase 11。
6. **tool trace projection / late diagnostic 可观测性**：WAIT_LATE_RESULT_REJECTED diagnostic 已写入 EventLog，但无 read model 投影。Owner: Phase 8+ projection。

所有 residual risk 均有明确 owner 或属于已确认 non-goal，无无主风险。

## 结论

**PR 56 PASS。**

Phase 7 全部退出条件、验证要求和 design alignment 均已满足。awaiting accept path、resolve_wait condition chain、late diagnostic scoping、WaitPoller、EngineEvent diagnostic confirmation、cancel/resume transitions、RunInputBuilder resume continuity、schema DDL 均经逐行走读验证正确。测试覆盖完整（6 个新测试文件 + 集成测试）。未发现 blocking finding。Residual risks 均有明确 owner。
