# Phase 10 Slice 5 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: Phase 10 Slice 5 — Reactive Engine Overflow Recovery to RECOVERING to New Attempt

## Verdict

**PASS**

## Summary

Slice 5 实现了 Engine `context_compaction_requested` reactive overflow recovery 路径：`EngineEventIngestor` 在 durable identity guard 通过后，使用 Host estimator（不信任 Engine `budget_state`）写 `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`，关闭旧 Attempt 为 `FAILED` 并写 `RUN_RECOVERING`；compact accepted 后追平 memory projection，创建新 Attempt / execution / dispatch 并写 `RUN_STARTED(start_reason=recovery)` / `ATTEMPT_STARTED`，唤醒 scheduler dispatch。compact failure、compactor 缺失、count 损坏、count 上限、quality rejected、hard after compact 均从 `RECOVERING` 收口 `FAILED`，不写 `LOST`。recovery accepted 返回 `terminal_closeout=False, stop_worker_stream=True`，scheduler 停止旧 worker stream 但不清理 duplicate governance registry。全部 104 个测试通过，pyright 零错误。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py -q` | 104 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

注：implementation artifact 记录 103 passed，实际验证为 104 passed。差异可能来自 artifact 编写时的测试计数快照，不影响结论。

## Adversarial Check Matrix

### 1. `terminal_closeout` / `stop_worker_stream` 语义

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| recovery accepted 是否触发 queue promotion | `engine_ingest.py` `_with_terminal_promotion_retry` 检查 `result.terminal_closeout`；recovery accepted 返回 `terminal_closeout=False` → 不触发 promotion | **BLOCKED** |
| recovery accepted 是否停止旧 worker stream | `dispatch.py:1815` `if result.terminal_closeout or result.stop_worker_stream:` → `terminal_seen=True` → break | **BLOCKED** |
| recovery accepted 是否清理 duplicate governance registry | `dispatch.py:1820-1821` `if run_terminal_closed:` → `_ingest_closed_run` 检查 `result.terminal_closeout` which is `False` → `run_terminal_closed=False` → 不清理 | **BLOCKED** |
| recovery accepted 是否释放旧 handle / lane | `dispatch.py:1822-1828` finally 块总是执行：`_active_handles.discard(handle)` + `_active_registry.unregister()` + `_safe_close_worker_handle` + `_safe_release_lane_token` | **BLOCKED** |
| 真正 Run terminal 是否仍清理 registry | `_ingest_closed_run` 检查 `result.terminal_closeout and result.status in (ACCEPTED, DUPLICATE)` → 真正 terminal 时 `terminal_closeout=True` → `run_terminal_closed=True` → 清理 | **BLOCKED** |
| duplicate CONTEXT_COMPACTION_REQUESTED replay 的 `stop_worker_stream` | `engine_ingest.py:557-568` duplicate 检测返回 `terminal_closeout=False, stop_worker_stream=True` → 停止旧 worker，不触发 terminal promotion | **BLOCKED** |

### 2. Duplicate replay 与 stale old Attempt 事件

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| 同一 `context_compaction_requested` 重复到达 | `_duplicate_terminal_event_ids` 检查 (REQUESTED, ATTEMPT_FAILED, RUN_RECOVERING) 三个 event_id；全部存在时返回 DUPLICATE + `stop_worker_stream=True`，不重复 compact | **BLOCKED** |
| 旧 Attempt 后续 `run_failed(context_compaction_required)` | durable identity guard 校验 `execution_id`；recovery 后 current Attempt 已变，旧 execution_id 不匹配 → REJECTED (`stale_execution_id`) | **BLOCKED** |
| 旧 Attempt 其他 late events | 同上：execution_id 不匹配 → REJECTED | **BLOCKED** |
| recovery 后是否创建第二个 recovery Attempt | recovery accepted 后 Run 从 RECOVERING → RUNNING；旧 Attempt 事件因 execution_id 不匹配被拒绝；无法触发第二次 recovery | **BLOCKED** |

### 3. Durable identity guard

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| attempt_id 不匹配 | `_validate_durable_context` 校验 `context.attempt.attempt_id == envelope.attempt_id` | **BLOCKED** |
| execution_id 不匹配 | `_validate_durable_context` 校验 `context.attempt.execution_id == envelope.execution_id` | **BLOCKED** |
| dispatch_record_id 不匹配 | `_validate_durable_context` 校验 `context.dispatch_record.dispatch_record_id == envelope.dispatch_record_id` | **BLOCKED** |
| Run 不在 RUNNING 状态 | `_validate_durable_context` 读取 active run；非 RUNNING 状态的 Run 不返回 valid context | **BLOCKED** |

### 4. State machine CAS 正确性

| 转换 | CAS 条件 | 结论 |
| --- | --- | --- |
| RUNNING → RECOVERING | `mark_running_run_recovering_row`: `WHERE status='running' AND current_attempt_id=? AND terminal IS NULL` | **PASS** |
| RECOVERING → RUNNING (recovery start) | `start_recovering_run_row`: `WHERE status='recovering' AND current_attempt_id=? AND terminal IS NULL AND NOT EXISTS (other active run in session)` | **PASS** |
| RECOVERING → FAILED (recovery failure) | `terminal_recovering_run_row`: `WHERE status='recovering' AND current_attempt_id=? AND terminal IS NULL` | **PASS** |
| 同 Session active/accepted/queued 互斥 | `start_recovering_run_row` 包含 `NOT EXISTS` 子查询检查 accepted/running/waiting/cancelling/recovering | **PASS** |

### 5. Reactive compact count 与 fail-closed

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| count 上限阻止第二轮 compact | `_committed_reactive_compact_count` 统计 committed reactive REQUESTED facts；`count >= max_reactive_compactions_per_run` → fail without writing new request | **BLOCKED** |
| count fact payload 损坏 | `_committed_reactive_compact_count` 使用 `EventPayloadTextEqualsFilter`；非文本 `trigger_source` → `count_committed_events_by_run_and_type` 抛异常 → `except Exception` catch → fail closed (`reactive_compact_count_unreadable`) | **BLOCKED** |
| count 上限时不 append 新 request fact | `_start_reactive_context_recovery` 在 count 检查后才 append REQUESTED；上限检查先于 append → 不写新 fact | **BLOCKED** |
| compactor / artifact root 缺失 | `_compact_reactive_recovery` 检查 `compactor is None or artifact_root is None` → fail without creating recovery Attempt | **BLOCKED** |
| quality check 拒绝 | `check_compaction_candidate` 返回 `accepted=False` → fail | **BLOCKED** |
| compact 后仍越过 hard threshold | `candidate.budget_after_compact >= estimate.hard_threshold_tokens` → fail | **BLOCKED** |

### 6. Event ordering

| 顺序要求 | 防御路径 | 结论 |
| --- | --- | --- |
| REQUESTED < ATTEMPT_FAILED < RUN_RECOVERING | `_start_reactive_context_recovery` 中 `_append_reactive_compaction_requested_event` (sub_index=0) → `_close_attempt_for_context_recovery` (sub_index=1 ATTEMPT_FAILED, sub_index=2 RUN_RECOVERING)，同事务内 sequence 递增 | **PASS** |
| RUN_RECOVERING < CONTEXT_COMPACTED | 第一事务 commit 后，`_compact_reactive_recovery` 在同一事务内写 COMPACTED (sub_index=3) | **PASS** |
| CONTEXT_COMPACTED < RUN_STARTED < ATTEMPT_STARTED | `_complete_reactive_recovery_after_compact` 先 catch-up memory projection 到 COMPACTED sequence，再 `_StartReactiveRecoveryOperation` 写 RUN_STARTED + ATTEMPT_STARTED | **PASS** |
| memory catch-up 覆盖 COMPACTED sequence | `catch_up_conversation_memory_projection(max_event_sequence=accepted.compacted_event_sequence)` | **PASS** |

### 7. Failure path 不写 RUN_LOST

| 失败场景 | 防御路径 | 结论 |
| --- | --- | --- |
| policy 缺失 | `_fail_reactive_recovery_without_request` → close Attempt + CONTEXT_COMPACTION_FAILED + RUN_FAILED | **BLOCKED** |
| input event 缺失 | 同上 | **BLOCKED** |
| count 损坏 | 同上 | **BLOCKED** |
| count 上限 | 同上 | **BLOCKED** |
| compactor 缺失 | `_compact_reactive_recovery` → fail + RUN_FAILED | **BLOCKED** |
| quality rejected | 同上 | **BLOCKED** |
| hard after compact | 同上 | **BLOCKED** |

所有 failure 路径写 `RUN_FAILED`，不写 `RUN_LOST`。`_fail_recovering_run` 调用 `fail_recovering_run_in_transaction` → `terminal_recovering_run_row` CAS `RECOVERING → FAILED`。

### 8. Scheduler `_consume_worker_events` 资源清理

| 资源 | recovery accepted | 真正 terminal |
| --- | --- | --- |
| `_active_handles.discard(handle)` | finally 块总是执行 | finally 块总是执行 |
| `_active_registry.unregister(...)` | finally 块总是执行 | finally �块总是执行 |
| `_safe_close_worker_handle(handle)` | finally 块总是执行 | finally 块总是执行 |
| `_safe_release_lane_token(token)` | finally 块总是执行 | finally 块总是执行 |
| `_duplicate_governance_registry.clear_run(...)` | 不清理（`run_terminal_closed=False`） | 清理（`run_terminal_closed=True`） |

### 9. Tests 是否覆盖 production path

| 测试 | 生产路径覆盖 | 结论 |
| --- | --- | --- |
| `test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers` | 完整 recovery 路径：REQUESTED → ATTEMPT_FAILED → RUN_RECOVERING → COMPACTED → new Attempt → wake_dispatch | **PASS** |
| `test_context_compaction_requested_stale_identity_is_rejected` | durable identity guard 拒绝 mismatched execution_id | **PASS** |
| `test_reactive_compact_failure_fails_run_without_lost` | 无 compactor → REQUESTED → ATTEMPT_FAILED → RUN_RECOVERING → CONTEXT_COMPACTION_FAILED → RUN_FAILED，无 RUN_LOST | **PASS** |
| `test_old_attempt_run_failed_after_recovery_is_stale_diagnostic` | recovery 后旧 Attempt run_failed 被拒绝 | **PASS** |
| `test_reactive_compact_count_limit_fails_closed_without_second_attempt` | count 上限 → fail，无新 REQUESTED fact，无 recovery Attempt | **PASS** |
| `test_reactive_compact_corrupt_count_fact_fails_closed` | 损坏 count → fail closed，无 recovery Attempt | **PASS** |
| `test_reactive_overflow_recovers_and_dispatches_new_attempt` | 完整 scheduler 集成：worker 产出 reactive → Host recovery → 新 Attempt dispatch → final answer → SUCCEEDED | **PASS** |
| `test_reactive_recovery_does_not_clear_duplicate_registry` | recovery 后 duplicate registry 保持 active（`final_blocks=True` 阻塞新 Attempt） | **PASS** |

测试使用 `_seed_current_run` 创建初始 Run，reactive overflow 通过 `_ReactiveRecoveryWorkerFactory` 注入。测试 helper 如 `_reactive_policy()` 使用明确的 `context_window_size=100, reserved_output_tokens=10` 等参数，不掩盖 production budget 逻辑。`FakeContextCompactor` 仅在测试中显式注入。

## Findings

**无 blocking / high / medium defect。**

### Low

**L1. Implementation artifact 测试计数与实际不符**

- 文件: `docs/reviews/phase10-s5-reactive-overflow-recovery-implementation-20260518.md:40`
- 状态: artifact 记录 "103 passed"，实际验证为 "104 passed"。
- 影响: 不影响代码正确性。可能是 artifact 编写时的测试计数快照与最终提交有差异。
- 优先级极低，不阻塞。

**L2. `_fail_reactive_recovery_without_request` 中 closeout result 未使用**

- 文件: `dayu/host/engine_ingest.py`
- 状态: `_fail_reactive_recovery_without_request` 调用 `_close_attempt_for_context_recovery` 后检查 `closeout.status`，但只使用其 `events` 字段构造最终结果。closeout 的 `terminal_closeout` 标记被丢弃（最终结果自己设置 `terminal_closeout=True`）。
- 影响: 功能正确。closeout 返回的 `terminal_closeout=True` 在此处无额外语义，因为 failure 路径本身就是 terminal。
- 优先级极低，不阻塞。

**L3. `_duplicate_terminal_event_ids` 对 CONTEXT_COMPACTION_REQUESTED 使用 CANONICAL_FACT event class**

- 文件: `dayu/host/engine_ingest.py` (diff line 1065-1084)
- 状态: 旧代码使用 `EventClass.DIAGNOSTIC` + `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`，新代码使用 `EventClass.CANONICAL_FACT` + `CONTEXT_COMPACTION_REQUESTED`。这与实际 `_append_reactive_compaction_requested_event` 使用的 event class 一致。
- 影响: duplicate 检测正确对齐。旧代码的 DIAGNOSTIC event class 是因为旧路径写的是 diagnostic event。
- 无功能影响。

## Plan Compliance

| 计划要求 | 状态 | 证据 |
| --- | --- | --- |
| Replace unsupported recovery with P10 reactive path | PASS | `engine_ingest.py:700-705` CONTEXT_COMPACTION_REQUESTED 走 `_start_reactive_context_recovery`，旧 `_unsupported_recovery_plan` 路径已移除 |
| Durable identity guard 校验 attempt_id + execution_id | PASS | `_validate_durable_context` 校验 attempt/execution/dispatch 三重 identity |
| Append CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive) | PASS | `_append_reactive_compaction_requested_event` 使用 `ContextCompactionTriggerSource.REACTIVE` |
| Use Host estimator even when Engine budget_state=None | PASS | `estimate_context_budget(policy, BudgetEstimateInput(...))` 不读取 `data.budget_state` |
| Close current Attempt + RUN_RECOVERING | PASS | `_close_attempt_for_context_recovery` → `close_attempt_for_context_recovery_in_transaction` |
| Run ContextGovernance reactive compact at most once | PASS | `_committed_reactive_compact_count` 统计 committed reactive facts；count ≥ max → fail |
| On accepted: CONTEXT_COMPACTED + artifact + memory catch-up + RUN_STARTED(recovery) + new Attempt | PASS | `_compact_reactive_recovery` → `_complete_reactive_recovery_after_compact` → `_StartReactiveRecoveryOperation` |
| On compact failure: CONTEXT_COMPACTION_FAILED + RUN_FAILED | PASS | `_fail_reactive_recovery_without_request` / `_compact_reactive_recovery` failure paths |
| No RUN_LOST in compact failure | PASS | 所有 failure 路径调用 `_fail_recovering_run` → `terminal_recovering_run_row` CAS RECOVERING→FAILED |
| Old Attempt subsequent events are stale | PASS | `test_old_attempt_run_failed_after_recovery_is_stale_diagnostic` 验证 execution_id 不匹配 → REJECTED |
| Corrupted compact count fails closed | PASS | `test_reactive_compact_corrupt_count_fact_fails_closed` 验证异常 catch → fail |
| Count limit does not append new request fact | PASS | count 检查先于 `_append_reactive_compaction_requested_event` |
| Recovery accepted: terminal_closeout=False, stop_worker_stream=True | PASS | `_StartReactiveRecoveryOperation.__call__` 返回 `terminal_closeout=False, stop_worker_stream=True` |
| Scheduler stops old worker stream but preserves duplicate registry | PASS | `dispatch.py:1815` break + `dispatch.py:1820` registry 保留 |
| Engine budget_state not used as budget truth | PASS | `_start_reactive_context_recovery` 不访问 `data.budget_state` |
| EngineIngestResult.stop_worker_stream default False | PASS | `stop_worker_stream: bool = False` dataclass 默认值 |
| Scheduler wiring injects context governance config | PASS | `dispatch.py` 注入 context_budget_policy/context_compactor/compact_artifact_root/memory_projection_policy |
| README 同步 | PASS | `dayu/host/README.md` 补充 reactive overflow recovery 描述；`tests/README.md` 更新覆盖说明 |

## Residual Risks

1. **Compactor / artifact write 在 Host write transaction 内执行**：沿用 Slice 4 residual。后续接入慢速生产 compactor 时需增加 in-progress / fencing 设计。
2. **Reactive estimator 只使用 durable current user input 片段**：沿用 Slice 4 residual。provider-specific tokenizer / retrieval 归后续 owner。
3. **不实现 Phase 11 startup recovery / positive orphan proof / RECOVERING cancel / 通用 recovery scan**：本 slice 只覆盖 Engine overflow reactive recovery。若 scheduler 在 RECOVERING 状态 crash，Run 将留在 RECOVERING 状态直到 Phase 11 实现。
4. **`_duplicate_terminal_event_ids` 对 failure path（不写 REQUESTED）不产生 duplicate match**：failure path 不写 REQUESTED event，因此 (REQUESTED, ATTEMPT_FAILED, RUN_RECOVERING) 三个 event_id 不全存在。后续相同 Engine event 到达时不会被识别为 duplicate，但会因 Run 已进入 FAILED terminal 状态被 `_late_rejection_reason` 拒绝。行为正确但路径不同于 success duplicate。
