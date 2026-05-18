# Phase 10 Slice 5 Code Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Verdict: ACCEPTED_WITH_RESIDUAL**

## Scope

Review of Phase 10 Slice 5 reactive overflow recovery implementation:
- `dayu/host/engine_ingest.py` (reactive compact orchestration)
- `dayu/host/durable/run_transition.py` (recovery close/start/fail transitions)
- `dayu/host/durable/state.py` (running→recovering→running/failed CAS)
- `dayu/host/dispatch.py` (stop_worker_stream + governance wiring)
- `tests/host/test_engine_ingest_mapping.py` (reactive recovery tests)
- `tests/host/test_dispatch_scheduler.py` (end-to-end integration tests)
- `dayu/host/README.md` / `tests/README.md`

## Verification

- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py -q` — 104 passed
- `pyright` — 0 errors
- `git diff --check` — 通过

---

## Adversarial Vectors

### V1. terminal_closeout / stop_worker_stream 语义正确性

**Attack:** recovery accepted 错误地触发 terminal closeout side effects（queue promotion、duplicate governance registry clear），或错误地未停止旧 worker stream。

**Defense (dispatch.py `_consume_worker_events` :1809-1828):**

Recovery accepted 返回 `terminal_closeout=False, stop_worker_stream=True`。在 worker event loop 中：

1. **Stream stop**: `result.terminal_closeout or result.stop_worker_stream` → `True` → `terminal_seen = True`, break loop。旧 worker 不再被消费。
2. **Registry**: `run_terminal_closed = _ingest_closed_run(result)` (:1817)。`_ingest_closed_run` (:1831-1841) 要求 `result.terminal_closeout` **且** status ACCEPTED/DUPLICATE 才返回 `True`。Recovery accepted 的 `terminal_closeout=False` → `run_terminal_closed=False`。不清理 duplicate governance registry。
3. **Promotion**: `_with_terminal_promotion_retry` (`ingest()` :299-303) 只在 `result.terminal_closeout AND status ACCEPTED/DUPLICATE` 时触发 `wake_queue_promotion`。Recovery accepted 不触发。
4. **Handle cleanup**: `finally` (:1819-1828) 无论何种情况都关闭旧 handle、释放旧 lane token、unregister 旧 attempt_id/execution_id — 但新 recovery attempt 有新的 attempt_id/execution_id，不冲突。

**真正 Run terminal 路径不变:**
- `_close_terminal` (:777-871) 始终返回 `terminal_closeout=True`
- 正常 run_failed(recoverable=False) / final_answer 走 `_close_terminal` → `_ingest_closed_run` → `True` → clear registry + promotion

**结论: BLOCKED**。stop_worker_stream 只停止旧 stream 不清理 registry，terminal_closeout 仍负责 registry + promotion。语义分离正确。

**评级:** 无 finding。

---

### V2. CONTEXT_COMPACTION_REQUESTED duplicate replay + 旧 Attempt late events

**Attack 1:** 同一个 reactive CONTEXT_COMPACTION_REQUESTED 被重复发送，导致第二次 recovery Attempt。

**Defense:**
- `_duplicate_terminal_result` (engine_ingest.py:541-568) 检查 `_duplicate_terminal_event_ids` — 对 CONTEXT_COMPACTION_REQUESTED，检查三事件: `CONTEXT_COMPACTION_REQUESTED(:0)`, `ATTEMPT_FAILED(:1)`, `RUN_RECOVERING(:2)`
- 若三者均已有 event row → 返回 DUPLICATE，`stop_worker_stream=True`
- 不会再次调用 `_start_reactive_context_recovery`

**Attack 2:** 旧 Attempt 在 recovery start 后发送 `run_failed(context_compaction_required, recoverable=True)`，创建第二个 recovery Attempt。

**Defense (两层):**

1. `_duplicate_terminal_event_ids` 不再为 RUN_FAILED 生成 event IDs（从原实现的 DIAGNOSTIC+ATTEMPT_FAILED+RUN_FAILED 三元组改为空元组 `()` (:2796 return ())），所以 `_duplicate_terminal_result` 不拦截此 case。

2. **但** `_late_rejection_reason` (:2078-2097) 拦截：recovery closeout 已将 old Attempt 的 `terminal_event_id` 设为非空。`_late_rejection_reason` 检测到 `context.attempt.terminal_event_id is not None` → 返回 `"terminal_already_closed"` → `_append_rejected_diagnostic` → REJECTED。不进入 `_ingest_validated`，不创建第二个 Attempt。

3. 即使绕过了 `_late_rejection_reason`（理论上不可能，因为 old attempt.terminal_event_id 已被 recovery closeout 设置），`_close_terminal` → `terminal_closeout_in_transaction` → `_invalid_terminal_precondition` 也会检查 `run.current_attempt_id != attempt_id`（old attempt_id != new attempt_id after recovery）→ INVALID_STATE。

**结论: BLOCKED**。三层防御：duplicate check（针对 CONTEXT_COMPACTION_REQUESTED）、late rejection（针对任意后续事件）、CAS precondition（针对 terminal closeout）。

**评级:** 无 finding。

---

### V3. Durable identity guard 校验完整性

**Attack:** 旧 Attempt 事件使用已失效的 attempt_id/execution_id/dispatch_record_id，但仍然通过 identity guard 校验。

**Defense:**
`_validate_durable_context` (:743-775) 校验:
- `run.session_id == envelope.session_id`
- `run.run_id == envelope.run_id`
- `attempt.run_id == envelope.run_id`
- `attempt.execution_id == envelope.execution_id`
- `dispatch_record.dispatch_record_id == envelope.dispatch_record_id`
- `dispatch_record.execution_id == envelope.execution_id`

**注意:** 此校验**不检查** `run.current_attempt_id == envelope.attempt_id`。这意味着 recovery 后旧 attempt_id 的 event（attempt 行仍存在，状态 FAILED）可以通过此校验。

但这**不是漏洞**，因为后续的 `_late_rejection_reason` (:2092-2096) 会检测到旧 attempt 已有 `terminal_event_id`，直接 REJECTED。`_validate_durable_context` 的职责是校验"candidate 引用的 durable entities 是否存在且自洽"，而非"是否为当前 active entity"。"是否为 stale"的语义由 `_late_rejection_reason` 承担。

**结论: BLOCKED**。校验覆盖完整，职责分离正确。

**评级:** 无 finding。

---

### V4. CAS 正确性：RUNNING → RECOVERING → RUNNING(new Attempt) 与 RECOVERING → FAILED

**Attack:** 并发操作导致状态竞争，例如 recovery start 和 recovery failure 同时触发。

**Defense:**

**`mark_running_run_recovering_row`** (state.py:2844-2888):
- CAS: `status = 'running' AND current_attempt_id = ? AND terminal_event_id IS NULL`
- 只检查 current_attempt_id，不检查 active unique index（RUNNING 已在 index 中，RECOVERING 是行内状态变更）

**`start_recovering_run_row`** (state.py:2892-2960):
- CAS: `status = 'recovering' AND current_attempt_id = ? AND terminal_event_id IS NULL`
- **额外**: `NOT EXISTS` 子查询检查同 Session 是否有 `accepted/running/waiting/cancelling/recovering` 其他 Run
- 这是一个 application-level active unique guard

**`terminal_recovering_run_row`** (state.py:2963-3010):
- CAS: `status = 'recovering' AND current_attempt_id = ? AND terminal_event_id IS NULL`

**并发场景分析:**
1. 两个 recovery start 同时到达: 第一个更新 status recovering→running，第二个 CAS 检查 status='recovering' 失败 → INVALID_STATE
2. recovery start 与 fail 同时到达: 一个更新 recovering→running，另一个 CAS recovering 失败
3. recovery start 与 admission 新 Run 创建: `NOT EXISTS` 子查询阻止在其他 active run 存在时 start

**RECOVERING 不在 active index 中的影响:**
- `host_runs_one_active_per_session` WHERE 包含 `'recovering'` (:814)，所以 RECOVERING Run 占用 active slot
- 在 recovery 期间不能创建新的 ACCEPTED/RUNNING/WAITING/CANCELLING Run

**结论: BLOCKED**。CAS 条件完整，NOT EXISTS 提供额外保护。

**评级:** 无 finding。

---

### V5. CONTEXT_COMPACTION_REQUESTED reactive event payload 校验

**Attack:** reactive event payload 缺少 attempt_id/execution_id 非空，或错误使用 Engine budget_state 作为预算真源。

**Defense:**

`_append_reactive_compaction_requested_event` (:643-705) 构造 payload 时：
- `attempt_id=context.attempt.attempt_id` (:680) — 来自 durable Attempt 行，非空
- `execution_id=context.attempt.execution_id` (:681) — 来自 durable Attempt 行，非空
- `budget_snapshot_ref=estimate.estimator_digest` (:693) — **Host estimator digest**，不是 Engine budget_state
- `estimator_digest=estimate.estimator_digest` (:695)
- `policy_ref=policy_ref` (:696) — Host policy ref
- `provider_request_id=data.provider_request_id` (:697) — 可选，Engine 可能传 null
- `provider_error_ref=_engine_event_ref(candidate)` (:698)

`build_context_compaction_requested_payload` (context_events.py) 的 validator 要求 `attempt_id`/`execution_id` 为非空文本。reactive trigger_source 的 `attempt_id`/`execution_id` 非空已在 Slice 3 M1 fix 中验证。

**Engine budget_state 处理:**
- `_start_reactive_context_recovery` (:361-485) 使用 Host `estimate_context_budget(policy, BudgetEstimateInput(...))` 作为预算真源
- 从不读取 `data.budget_state`
- 测试 `test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers` 已验证 `budget_state=None` 时使用 Host estimator

**结论: BLOCKED**。reactive payload 满足 validator 约束，Host estimator 为预算唯一真源。

**评级:** 无 finding。

---

### V6. Reactive compact count 读取/损坏 fail-closed

**Attack 1:** committed reactive count 读取抛异常，绕过 count limit 限制。

**Defense:**
- `_committed_reactive_compact_count` (:619-641) 使用 `count_committed_events_by_run_and_type` + `EventPayloadTextEqualsFilter` 过滤 `trigger_source=reactive`
- 调用方 (:412-424) 用 try/except 包裹 → 异常时走 `_fail_reactive_recovery_without_request`，不追加新 request fact，直接 close old attempt + fail run
- `_fail_reactive_recovery_without_request` (:487-536) 不调用 `_append_reactive_compaction_requested_event`，所以不增加 request count

**Attack 2:** committed count 已达上限，仍 append 新 request fact。

**Defense:**
- 上限检查 (:425-433) **在** `_append_reactive_compaction_requested_event` (:434-440) **之前**
- 达到上限时直接走 `_fail_reactive_recovery_without_request`，不 append REQUESTED

**测试验证:**
- `test_reactive_compact_count_limit_fails_closed_without_second_attempt`: 验证上限时 `CONTEXT_COMPACTION_REQUESTED not in event_types`，Attempt count = 1
- `test_reactive_compact_corrupt_count_fact_fails_closed`: 验证损坏时 fail closed，Attempt count = 1

**结论: BLOCKED**。count check 先于 request append，异常保守失败，不绕过配额。

**评级:** 无 finding。

---

### V7. Compact accepted event ordering + memory catch-up

**Attack:** CONTEXT_COMPACTED 的 event_sequence 在 memory projection catch-up cursor 之后，导致 projection 不包含 compacted 事实。

**Defense:**

事件在 `_start_reactive_context_recovery` transaction 内的 append 顺序：
1. `_append_reactive_compaction_requested_event` (:434-440) — CONTEXT_COMPACTION_REQUESTED, sub_index=0
2. `_close_attempt_for_context_recovery` (:441-446) — ATTEMPT_FAILED (sub_index=1), RUN_RECOVERING (sub_index=2)
3. `_compact_reactive_recovery` (:449-455) — CONTEXT_COMPACTED (sub_index=3) 或 CONTEXT_COMPACTION_FAILED

三者在同一 write transaction 内，event_sequence 递增。

在 `_complete_reactive_recovery_after_compact` (:971-993)：
1. `catch_up_conversation_memory_projection(max_event_sequence=accepted.compacted_event_sequence)` — catch-up 到 COMPACTED 的 sequence（包含 COMPACTED）
2. `_StartReactiveRecoveryOperation` 在**新** write transaction 中写入 RUN_STARTED + ATTEMPT_STARTED

事件序列: REQUESTED < ATTEMPT_FAILED < RUN_RECOVERING < COMPACTED < (memory catch-up) < RUN_STARTED < ATTEMPT_STARTED

Memory projection 在 new Attempt STARTED event 之前 catch-up，保证新 Attempt 的 RunInputBuilder 能读到 compacted 后的 memory 状态。

**结论: BLOCKED**。事件 append 顺序正确，catch-up 在 start 之前，projection cursor 覆盖 COMPACTED。

**评级:** 无 finding。

---

### V8. Compact failure 总在 old Attempt 关闭后 Run FAILED，不写 RUN_LOST

**Attack:** compact failure 路径不关闭 old Attempt 就写 RUN_FAILED，或错误地写 RUN_LOST。

**Defense:**

所有 failure 路径都遵循: `_close_attempt_for_context_recovery` 先于 `_fail_recovering_run`：

1. `_fail_reactive_recovery_without_request` (:487-536):
   - `_close_attempt_for_context_recovery` (先) → 写 ATTEMPT_FAILED + RUN_RECOVERING
   - `_append_reactive_compaction_failed_event` → CONTEXT_COMPACTION_FAILED
   - `_fail_recovering_run` → RUN_FAILED (从 RECOVERING → FAILED)

2. `_compact_reactive_recovery` 的 4 个失败分支 (:726-797):
   - compactor/artifact missing: `_append_reactive_compaction_failed_event` → `_fail_recovering_run`
   - quality rejected: `_append_reactive_compaction_failed_event` → `_fail_recovering_run`
   - hard after compact: `_append_reactive_compaction_failed_event` → `_fail_recovering_run`

在这些路径之前，`_close_attempt_for_context_recovery` 已在 `_start_reactive_context_recovery` (:441-448) 中调用。

`_fail_recovering_run` (:909-969) 调用 `fail_recovering_run_in_transaction`:
- CAS: `status = 'recovering' AND current_attempt_id = ?` → RUN_FAILED
- 不修改已关闭的 old Attempt（source_attempt_id 只用于 CAS 校验）
- 不写 RUN_LOST

**结论: BLOCKED**。所有 failure 路径确保 old Attempt 先关闭、Run FAILED、不写 RUN_LOST。

**评级:** 无 finding。

---

### V9. Scheduler `_consume_worker_events` — lane/handle 释放正确性

**Attack:** recovery accepted 停止旧 worker stream 后，lane token 未正确释放，导致新 recovery dispatch 无法获取 lane。

**Defense:**

Recovery accepted 时 `stop_worker_stream=True`:
1. `terminal_seen = True` + break loop (:1815-1818)
2. `run_terminal_closed = _ingest_closed_run(result)` → `False` (terminal_closeout=False) (:1817)
3. `finally` (:1819-1828):
   - **不** clear duplicate governance registry (run_terminal_closed=False)
   - discard handle → close handle
   - **unregister old attempt_id/execution_id** from active_registry
   - **release old lane token** → lane slot 变为可用

新 recovery dispatch 随后通过 `wake_dispatch` (:992) 入队 → `_drain_loop` → acquire new lane token → dispatch new worker。新 worker 使用 new attempt_id/execution_id 注册。

**结论: BLOCKED**。lane release + handle close + active registry unregister 正确，不与新 recovery worker 冲突。

**评级:** 无 finding。

---

### V10. Tests 是否真实覆盖 production path

**Attack:** test helper (`_seed_active_run` / `_seed_current_run`) 绕过 production path（admission → governance → start），掩盖 production bug。

**Defense 分析:**

`_seed_current_run` (test_dispatch_scheduler.py:2303-2362) 使用 `create_running_run_with_starting_attempt_in_transaction` 直接创建 RUNNING Run + STARTING Attempt + PENDING dispatch。

`_seed_active_run` (test_engine_ingest_mapping.py:1170+) 创建 RUNNING Run + RUNNING Attempt（通过 `_accept_worker_transition`）。

**这些 helpers 对 reactive recovery 路径的适用性:**
- Reactive recovery 的起点是 RUNNING Run + RUNNING/STARTING Attempt + dispatch record
- `close_attempt_for_context_recovery_in_transaction` 的 `_invalid_terminal_precondition` 接受 `attempt.status in (STARTING, RUNNING)` → STARTING 可通过
- 其他 precondition: `run.status == RUNNING`, `run.current_attempt_id == attempt_id` → 满足

两个 helpers 产出的状态满足 recovery closeout 的所有 precondition，测试覆盖的路径与 production 路径（governance start → dispatch → worker accepted → RUNNING attempt → overflow → recovery）的后续段一致。

**但是:** 没有测试覆盖 "RUNNING attempt 是通过 worker accept transition 从 STARTING 转变为 RUNNING 后到达 recovery" 的完整链。现有测试跳过 worker accept transition，直接创建 RUNNING attempt。这不掩盖 bug，但缺失 worker accept → context_compaction_requested 的边界测试。

**结论: RESIDUAL**。当前 helper 不掩盖 production bug（precondition 路径一致），但缺少 worker accept transition → recovery 的完整链测试。

**评级:** R1 (residual，测试覆盖边界)。

---

### V11. Engine ingest 是否承担过度 Context Governance orchestration

**Attack:** `EngineEventIngestor._start_reactive_context_recovery` 承担过多 governance 逻辑（budget estimate、compact count、compactor call、artifact write、memory projection catch-up），违反单一职责，变成 God method。

**Code evidence:**

`_start_reactive_context_recovery` (:361-485) 包含：
- Policy 读取 (:376-384)
- Input event 读取 (:385-395)
- Display text 提取 (:396)
- Budget estimate + decision (:397-411)
- Compact count 读取 + 异常处理 (:412-424)
- Count limit 检查 (:425-433)
- CONTEXT_COMPACTION_REQUESTED append (:434-440)
- Attempt closeout (:441-448)
- Compactor LLM 调用 + quality check + artifact write (:449-455, delegated to `_compact_reactive_recovery` :707-849)
- 结果聚合 (:456-485)

`_complete_reactive_recovery_after_compact` (:971-993) 额外承担：
- Memory projection catch-up
- Recovery start transaction
- Dispatch wakeup

**评估:**
- 这确实是一段复杂的编排逻辑，但 `EngineEventIngestor` 的定位是 **Host-owned EngineEvent 处理中枢**
- Slice 4 proactive governance 的对应逻辑在 `HostDispatchScheduler._run_pre_start_governance` 中，Slice 5 reactive 逻辑在 `EngineEventIngestor` 中 — 这是合理的，因为 reactive overflow 的触发点是 Engine event ingestion，不是 scheduler wakeup
- 但 `_start_reactive_context_recovery` 方法体 ~120 行，确实偏长；`_compact_reactive_recovery` 也被抽成独立方法 (:707-849)

**结论: RESIDUAL**。职责在可接受范围内——EngineEventIngestor 作为 ingest 中枢承担 reactive recovery orchestration 是合理的，但建议后续将 budget estimation + compact 决策逻辑抽取为独立 governance helper 以减少 `_start_reactive_context_recovery` 的方法体长度。

**评级:** R2 (residual，代码组织建议)。

---

### V12. Slice 4 residuals 延续状态

**Attack:** S4 residuals 在 S5 中未被记录或恶化。

**Defense:**
- R1 (compactor/artifact write 在 DB transaction 内): **延续**。`_compact_reactive_recovery` (:764: `compactor.compact(request)`) + (:798-817: `write_compact_artifact`) 仍在 write transaction 内执行。实现 artifact 已记录。
- R2 (budget estimate 只用 display_text): **延续**。`_start_reactive_context_recovery` (:396-410) 与 S4 同一模式。
- R3 (promote_next_queued_run 旧 API): **无变化**。S5 不引入新调用。

**结论: RESIDUAL**。S4 三个 residuals 在 S5 中延续，均已知并记录。

**评级:** 无新增 finding。

---

## Findings Summary

| ID | Severity | Category | Description | Verdict |
|----|----------|----------|-------------|---------|
| — | — | V1 stop_worker_stream | 语义分离正确，不触发 promotion/registry clear | BLOCKED |
| — | — | V2 duplicate replay + late events | 三层防御：dup check + late rejection + CAS | BLOCKED |
| — | — | V3 identity guard | 校验完整，late rejection 兜底 | BLOCKED |
| — | — | V4 CAS 正确性 | running→recovering→running/failed CAS + NOT EXISTS guard | BLOCKED |
| — | — | V5 reactive payload | attempt_id/execution_id 非空，Host estimator 真源 | BLOCKED |
| — | — | V6 count fail-closed | count check 先于 request append，异常保守失败 | BLOCKED |
| — | — | V7 event ordering | REQUESTED < FAILED < RECOVERING < COMPACTED < (projection) < STARTED | BLOCKED |
| — | — | V8 failure paths | 所有路径 old Attempt 先关闭、不写 RUN_LOST | BLOCKED |
| — | — | V9 lane release | lane + handle + registry unregister 正确，新 worker 不冲突 | BLOCKED |
| R1 | RESIDUAL | V10 test coverage | 缺少 worker accept → recovery 完整链测试 | RESIDUAL |
| R2 | RESIDUAL | V11 orchestration size | _start_reactive_context_recovery ~120 行，建议抽 governance helper | RESIDUAL |
| — | — | V12 S4 residuals | R1/R2/R3 延续，已知并记录 | 无新增 |

**Verdict: ACCEPTED_WITH_RESIDUAL** — 12 vectors, 9 blocked, 2 new residual (R1 test boundary, R2 code organization), 3 S4 residuals延续。无 blocking/high/medium finding。

## 未覆盖风险

1. **R1 — Worker accept → recovery 完整链测试缺失**: 现有 helpers 从 STARTING/RUNNING 开始，未覆盖 worker_accept transition 使 attempt 变为 RUNNING 后再收到 CONTEXT_COMPACTION_REQUESTED 的路径。当前 test 使用 `_seed_active_run`/`_seed_current_run` 跳过 accept transition，但所有后续 precondition 与 production 路径一致，不构成实际正确性风险。

2. **R2 — `_start_reactive_context_recovery` 方法体偏长**: ~120 行 orchestration 逻辑，建议后续将 budget estimation + compact decision 抽取为独立模块级 helper。

3. **S4 Residual 延续**:
   - R1: Compactor LLM + 文件 I/O 在 SQLite write transaction 内
   - R2: Budget estimate 仅覆盖 display_text
   - R3: `promote_next_queued_run` 旧 API 表面

4. **RECOVERING cancel 未实现** (已知): 当前实现不处理 RECOVERING 状态的 cancel。如果 cancel 在 recovery 期间到达，会走 `_CancelRunOperation` 的 INVALID_STATE 分支 (recovering 不在 accepted/queued/running/cancelling/waiting/terminal 任一分支中)。

5. **Phase 11 startup recovery** (已知): 不实现 orphan recovery、positive orphan proof 或通用 recovery scan。
