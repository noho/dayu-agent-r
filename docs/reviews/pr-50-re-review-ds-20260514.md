# PR 50 Fix Re-Review — AgentDS

- **PR**: #50 Host Phase 3 admission state machine
- **fix commit**: 16668ac fix host phase3 pr review findings
- **date**: 2026-05-14
- **reviewer**: AgentDS
- **controller adjudication**: `docs/reviews/pr-50-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/pr-50-fix-20260514.md`

## Verification Gates

| Gate | Result |
|------|--------|
| `pytest tests/host -q` | 160 passed in 1.89s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | pass (no output) |
| `git diff --check main...HEAD` | pass (no output) |

## Accepted Findings — Fix Verification

### PR50-C-001: Post-commit wakeup 不阻断 durable queue promotion — FIXED

**`_promote_after_release` (admission.py:1612-1627)**:
- Durable promotion `service.promote_next_queued_run(session_id)` 先于 queue wakeup 执行。
- `wake_queue_promotion` 包裹在 `try/except RuntimeError: pass` 中，失败不传播。
- 返回的 `PromotionResult` 不受 wakeup 影响。

**`promote_next_queued_run` (admission.py:511-534)**:
- Promotion transaction 提交后调用 `_wake_dispatch_if_needed(..., suppress_runtime_error=True)`。
- dispatch wakeup `RuntimeError` 不掩盖已提交的 promotion 结果。

**`_wake_dispatch_if_needed` (admission.py:1590-1609)**:
- 新增 `suppress_runtime_error` 参数，控制 `RuntimeError` 是传播还是 best-effort 吞掉。
- `start_run` / `submit_followup_queue` 路径使用默认 `suppress_runtime_error=False`，保持 dispatch wakeup 失败传播语义。

**回归测试**:
- `test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure` (line 734): active cancel → queue wakeup 失败 → promotion 已完成且结果不掩盖。
- `test_promote_next_queued_run_returns_result_when_dispatch_wakeup_fails` (line 775): promotion → dispatch wakeup 失败 → promotion 结果不掩盖。
- `test_terminal_closeout_promotion_survives_queue_wakeup_failure` (line 868): terminal closeout → queue wakeup 失败 → promotion 已完成且结果不掩盖。
- `test_rollback_before_cancel_commit_does_not_wake_or_promote` (line 987): cancel transaction rollback 时不触发 wakeup/promotion。

**边界确认**:
- Durable promotion 事务失败仍传播异常（符合 controller 裁决：Phase 5 scheduler retry/scan 之前不做 promotion failure swallow）。
- `cancel_run` 幂等重放路径 `_idempotent_cancel_result` 固定返回 `released_active_slot=False, promotion=None`，wakeup 修复后首次 cancel 的 promotion 不会因 wakeup 失败而丢失，因此幂等重放不需要补做 promotion。

### PR50-C-002: git diff --check main...HEAD — FIXED

- `git diff --check` 通过。
- `git diff --check main...HEAD` 通过。
- 原始 trailing whitespace（`docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md:133-150`）已清理。

### PR50-C-003: `_require_event_sequence` 使用 EventLogStore — FIXED

- `TABLE_EVENT_LOG` 不再从 `dayu.host.admission` import（grep 确认 0 matches）。
- `_require_event_sequence` 签名改为 `(transaction: HostTransaction, event_log_store: EventLogStore, event_id: str) -> int`。
- 实现通过 `event_log_store.read_event_by_id(transaction, event_id)` 读取 EventLog row。
- 包含 null check（event 缺失 → `INTERNAL_ERROR`）和 type guard（`isinstance(value, int)` → `INTERNAL_ERROR`）。
- `EventLogRow` 仍被 import（用于 `read_event_by_id` 返回类型的属性访问），这是合理的。

## Rejected Findings — Plan/Test Basis Verification

### followup digest 不含 `resolved_execution_target` — CONFIRMED REJECTED

- **Plan evidence**: `docs/host/phase3-session-run-attempt-admission-plan.md` 明确要求 follow-up queue digest 排除 `resolved_execution_target`；同 key 同 digest 重试返回首次持久化 Run。
- **Test evidence**: `test_followup_idempotency_excludes_later_resolved_execution_target` (test_admission_queue.py:399) 锁定此行为。
- **结论**: 控制器裁决有效，不在本 PR 修。

### ATTACH_ACTIVE 不写 EventLog — CONFIRMED REJECTED

- **Plan evidence**: Phase 3 plan 明确 attach-active 创建 null event ref 的幂等记录，不追加 EventLog fact。
- **Test evidence**: `test_reject_and_attach_active_have_expected_event_and_idempotency_effects` (test_admission_queue.py:480) 断言无 EventLog side effect 行为。
- **结论**: 控制器裁决有效，不在本 PR 修。

### 其余 rejected findings — CONFIRMED REJECTED

| Finding | Rejection basis | Valid? |
|---------|----------------|--------|
| closeout 无幂等保护 | Plan 明确 internal closeout 不是 public command，Phase 5 owner | Yes |
| cancel CAS status code 不一致 | Controller 解释不同 CAS predicate 导致不同 reachable condition，统一会降低精度 | Yes |
| REJECT policy 不写幂等记录 | Plan 明确 reject 不写 EventLog/幂等记录，有 test 锁定 | Yes |
| ATTACH_ACTIVE 幂等重放可能返回已终态 Run | Plan 规定 idempotency result ref 是权威引用，不创建重复 work | Yes |
| Attempt DDL 含 Phase 3 不可达状态 | 设计上有意 forward-compatible，与 `docs/host/design.md` 对齐 | Yes |
| 广泛 failure-path 测试覆盖 | 已覆盖 plan 规定 invariant，其余归 Phase 4/5/11 | Yes |

## New Issues Check

### 状态机行为 — 无问题

- `_promote_after_release` 仅改变 promotion 与 wakeup 的调用顺序及异常处理，不改变任何 state transition 逻辑。
- `_require_event_sequence` 仅改变 EventLog 读取路径（直接 SQL → EventLogStore.read_event_by_id），行为等价。

### EventLog / CAS 事务一致性 — 无问题

- `_require_event_sequence` 的 `read_event_by_id` 在同一 `HostTransaction` 内执行，与原有直接 SQL 处于相同事务边界。
- `_promote_after_release` 的 promotion 仍在独立事务中执行（closeout 事务已 commit 后），与原有事务模型一致。

### Import boundary — 无问题

- `TABLE_EVENT_LOG` 已从 admission.py 完全移除。
- `EventLogRow` 保留 import（用于 `read_event_by_id` 返回值属性访问），这是对 EventLogStore 公共 contract 的合法依赖。
- 无新增跨层 import 或反向依赖。

### 弱类型 — 无问题

- `_require_event_sequence` 签名: `(HostTransaction, EventLogStore, str) -> int`，完整类型标注。
- `_wake_dispatch_if_needed` 签名: `(AdmissionWakeupPort, PendingDispatchRecord \| None, *, bool) -> None`，完整类型标注。
- `_ToggleFailingWakeupSpy` 继承 `_WakeupSpy(AdmissionWakeupPort)`，符合 Protocol 契约。
- pyright 0 errors 确认无类型问题。

### README 同步 — 已同步

- `dayu/host/README.md` 新增 Internal Admission 章节，文档化：
  - post-commit wakeup 边界（"active slot 释放后的 durable promotion 先于 queue promotion wakeup"）
  - follow-up queue digest 不含 `resolved_execution_target`
  - promotion dispatch/queue wakeup RuntimeError 按 best-effort 处理
  - 测试覆盖范围更新

### 测试质量 — 无问题

新增 3 个回归测试（配合已有的 rollback 测试共 4 个相关测试）：
- 每个测试建立完整的 active + queued 状态，执行 cancel/closeout/promotion，断言 promotion 结果正确且 wakeup 失败不掩盖。
- `_ToggleFailingWakeupSpy` 通过 boolean 开关精确控制 `RuntimeError` 抛出时机，同时保留 spy 记录能力。
- 测试覆盖 cancel 路径（pre-dispatch STARTING）、closeout 路径（terminal closeout）和 promotion 路径（dispatch wakeup）三个关键场景。

## Conclusion

**3/3 accepted findings fixed. No new issues found. No blocking findings.**

- PR50-C-001: FIXED — promotion ordering + wakeup best-effort + 回归测试。
- PR50-C-002: FIXED — trailing whitespace 清理，diff check 通过。
- PR50-C-003: FIXED — EventLogStore.read_event_by_id 替代直接 SQL，TABLE_EVENT_LOG import 移除。

Rejected findings 均有 plan/test 依据，控制器裁决有效。

Verification gates 全部通过：160 tests passed, pyright 0 errors, git diff --check 通过。

**Verdict: ACCEPTED — no blocking findings.**
