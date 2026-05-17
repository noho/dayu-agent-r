# P9.5 S4 Host Durable Helper API Tightening — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S4 Host Durable Helper API Tightening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S4.
- Implementation artifact: `docs/reviews/p9-5-s4-host-durable-helper-tightening-implementation-20260517.md`.
- Reviewed files: `dayu/host/durable/run_transition.py`, `dayu/host/durable/state.py`, `dayu/host/dispatch.py`, `tests/host/test_run_attempt_transitions.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_phase6_toolruntime_integration.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_public_cancel_session_runs.py`.
- No code, tests, or artifacts were modified.

## Scope Adherence Verification

- All changes within S4 allowed files: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/dispatch.py`, and tests.
- No new states, schema, public facade, compat wrapper, or RECOVERING semantics.
- No P10+ semantics introduced.
- Plan boundaries honored.

## Findings

### F1 [Low] `_invalid_dispatching_after_lane_precondition` duplicate row reads with `mark_dispatching_after_lane_row`

- **入口/函数**: `mark_dispatching_after_lane_row` → `_invalid_dispatching_after_lane_precondition`
- **文件(行号)**: `dayu/host/durable/state.py:3147-3166` (precondition check), `state.py:4147-4200` (precondition function body)
- **输入场景**: production scheduler 在 lane acquired 后调用 `mark_dispatching_after_lane_row`
- **实际分支**: `_invalid_dispatching_after_lane_precondition` 执行 `read_dispatch_record_by_attempt_id`、`read_attempt_by_id`、`read_run_by_id` 做前置检查；随后 `mark_dispatching_after_lane_row` 的同事务 SQL UPDATE 的 WHERE clause 又做了一遍等效 status/owner/refs 检查。
- **预期行为**: 前置检查应消除 SQL-level 重复检查，或明确注释说明双重防御的意图。
- **实际行为**: Python-level precondition 和 SQL WHERE clause 做了双重等效检查。行为正确——SQL WHERE 是 CAS 防线，Python 检查提供结构化 `INVALID_STATE` / `NOT_FOUND` 诊断。但二者检查粒度不完全一致：Python 检查了 `run.status` / `attempt.status` / `execution_id` 一致性，SQL WHERE 未覆盖这些；SQL WHERE 检查了 `worker_accept_event_id IS NULL` / `cancelled_event_id IS NULL` / `cancelled_event_sequence IS NULL`，Python 也已覆盖。不存在遗漏，但缺少注释说明二者为何并存。
- **直接证据**: `state.py:4147-4200` (Python 前置) vs `state.py:3170-3190` (SQL WHERE)。
- **影响**: 维护者可能不确定是否应统一到一侧。当前行为正确，不会产生错误。
- **建议改法和验证点**: 在 `_invalid_dispatching_after_lane_precondition` 或 `mark_dispatching_after_lane_row` 的 docstring 中说明：Python 前置提供结构化诊断，SQL WHERE 提供 final CAS；二者互补而非冗余。
- **修复风险（低）**: 仅注释。
- **严重程度（低）**:

## Open Questions

无。

## Residual Risk

- `_invalid_dispatching_after_lane_precondition` 的 Python 前置与 SQL WHERE 的 CAS 双重检查粒度不一致：SQL 不检查 `run.status` / `attempt.status`（但 CAS lost 后置检查会判定 INVALID_STATE）；Python 前置若与 SQL 不同步则可能出现诊断不准确。当前实现正确，但后续修改 `mark_dispatching_after_lane_row` 的 SQL WHERE 时需同步更新 Python 前置。
- `AcceptWorkerRunningInput.local_worker_id` 为 optional；非本地 worker 路径为 `None` 时 `_attempt_running_event_request` 会写入 `"local_worker_id": null` 到 payload JSON。这与 `worker_accept_reason` 必填不同——后者有强制性校验。当前 behavior 正确，但需注意 JSON payload 中的 `null` 对下游消费者的影响。

## Review Point Checklist

| # | 审查点 | 状态 |
|---|--------|------|
| 1 | `mark_dispatching_after_lane_row` 收窄为 WAITING_FOR_LANE → DISPATCHING，前置覆盖 run/attempt/dispatch/execution/owner/lane/cancel/worker refs | **通过** — SQL WHERE 从 `IN (PENDING, WAITING_FOR_LANE)` 收窄为 `= WAITING_FOR_LANE`；新增 `_invalid_dispatching_after_lane_precondition` 在事务内验证 run RUNNING、attempt STARTING、execution_id 一致、owner/lane 诊断字段完整、claim/dispatching/worker/cancel refs 未写入。 |
| 2 | `accept_worker_running_in_transaction` fail-closed 且 ATTEMPT_RUNNING payload 补齐诊断但不变 public contract | **通过** — `_invalid_accept_worker_precondition` 新增 execution_id 一致、dispatch run/attempt 一致、owner/lane/claim/acquired/dispatching 存在、worker_accepted/cancelled 未写入等 15 项检查；`_attempt_running_event_request` 补齐 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id`。`local_worker_id` 为 optional，不破坏既有调用方。 |
| 3 | dispatch scheduler recheck 不再依赖 pending direct path | **通过** — `_is_dispatchable_recheck` 从 `IN (PENDING, WAITING_FOR_LANE)` 收窄为 `== WAITING_FOR_LANE`，新增 `owner_host_instance_id IS NOT NULL`、`waiting_for_lane_at IS NOT NULL`、`lane_name IS NOT NULL`。新测试 `test_pending_dispatch_recheck_without_waiting_is_skipped` 证明 pending bypass 被拒绝。 |
| 4 | 白盒 fixture 迁移为 production-like 状态 | **通过** — `_seed_current_run`（test_run_input_builder）先 `mark_dispatch_waiting_for_lane_row` 再 `mark_dispatching_after_lane_row`；`_force_dispatch_snapshot_state` 的 PENDING/WAITING_FOR_LANE/DISPATCHING 分支均补齐全部 lane/dispatch/worker/cancel 诊断字段；旧测试 `test_dispatching_supports_pending_direct_lane_recheck` 改为 `test_dispatching_rejects_pending_direct_lane_bypass` 并断言 `INVALID_STATE`。 |
| 5 | 不违反 design.md/S4 plan/AGENTS 硬约束 | **通过** — 未新增状态、schema、public facade、compat wrapper、反向依赖、`Any`/`object` 签名、god object/function。中文 docstring 完整。 |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 1 (F1 — Python/SQL 双重前置缺少注释说明)
- **S4 五项审查点**: 全部通过
- **类型检查**: pyright 0 errors / 0 warnings（已由 implementation artifact 验证 `python -m pyright dayu/host tests/host`）
- **测试**: 500 passed, 0 failed（已由 implementation artifact 验证 `pytest tests/host`）
