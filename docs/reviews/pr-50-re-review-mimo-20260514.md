# PR 50 Fix Re-Review (AgentMiMo)

- **PR**: #50 Host Phase 3 admission state machine
- **fix commit**: `16668ac fix host phase3 pr review findings`
- **re-review date**: 2026-05-14
- **scope**: fix commit diff + controller adjudication verification
- **reviewer**: AgentMiMo

## Verification Results

| check | result |
|---|---|
| `pytest tests/host -q` | 160 passed in 2.09s |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed (exit 0) |
| `git diff --check main...HEAD` | passed (exit 0) |

## Accepted Findings Verification

### PR50-C-001: Post-commit wakeup must not block durable queue promotion — FIXED

**Fix summary**: `_promote_after_release` 调换执行顺序，先执行 durable promotion，再在 try/except 中执行 queue wakeup；dispatch wakeup 通过 `suppress_runtime_error=True` 参数实现 best-effort。

**代码验证**:

1. `_promote_after_release` (`admission.py:1612-1627`): 先调用 `service.promote_next_queued_run(session_id)` 拿到 `promotion` 结果，再在 `try/except RuntimeError: pass` 中调用 `service.wakeup_port.wake_queue_promotion(session_id)`。durable promotion 异常正常传播，queue wakeup 异常被吞掉。返回值始终是 promotion 结果。**正确。**

2. `_wake_dispatch_if_needed` (`admission.py:1590-1609`): 新增 `suppress_runtime_error: bool = False` keyword-only 参数。`wake_dispatch` 调用包裹在 `try/except RuntimeError` 中，仅当 `suppress_runtime_error=False` 时 re-raise。**正确。**

3. `promote_next_queued_run` (`admission.py:529-533`): 调用 `_wake_dispatch_if_needed(self.wakeup_port, result.pending_dispatch, suppress_runtime_error=True)`。promotion 已提交后的 dispatch wakeup RuntimeError 被 best-effort 处理，不掩盖 promotion 结果。**正确。**

4. 测试覆盖（3 个新测试）:
   - `test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure`: active cancel 后 queue wakeup 失败，断言 Run 已 CANCELLED、queued Run 已 promoted RUNNING、wakeup spy 记录了调用。**覆盖 cancel 路径。**
   - `test_terminal_closeout_promotion_survives_queue_wakeup_failure`: terminal closeout 后 queue wakeup 失败，断言 Run 已 SUCCEEDED、queued Run 已 promoted RUNNING。**覆盖 closeout 路径。**
   - `test_promote_next_queued_run_returns_result_when_dispatch_wakeup_fails`: promotion 提交后 dispatch wakeup 失败，断言 promotion 结果正确返回、queued Run 已 RUNNING。**覆盖 dispatch wakeup 路径。**

**结论**: 三个子场景全部 fixed 且有回归测试。durable promotion 异常不被吞掉（符合 controller "not accepted" 约束）。

### PR50-C-002: PR diff trailing whitespace — FIXED

**Fix summary**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md:133-150` 尾随空白已清理。

**验证**: `git diff --check` 和 `git diff --check main...HEAD` 均 exit 0。**正确。**

### PR50-C-003: `_require_event_sequence` should use `EventLogStore` — FIXED

**Fix summary**: 函数签名改为 `_require_event_sequence(transaction, event_log_store, event_id)`，内部通过 `event_log_store.read_event_by_id(transaction, event_id)` 读取。`TABLE_EVENT_LOG` import 已从 `admission.py` 移除。

**代码验证**:

1. `admission.py:1666-1692`: 函数签名包含 `event_log_store: EventLogStore`，内部调用 `event = event_log_store.read_event_by_id(transaction, event_id)`，通过 `event.event_sequence` 获取值。错误处理逻辑不变。**正确。**

2. `admission.py` import 区域（line 30-60）: `TABLE_EVENT_LOG` 不再出现。grep 确认全文件无 `TABLE_EVENT_LOG` 引用。**正确。**

3. `EventLogStore.read_event_by_id` (`event_log.py:181-190`): 签名 `(self, transaction: HostTransaction, event_id: str) -> EventLogRow | None`，`EventLogRow` 有 `event_sequence` 属性。**接口匹配。**

4. 两个调用点（`admission.py:910-914` 和 `admission.py:973-977`）均已更新为传入 `self.event_log_store`。**正确。**

**结论**: FIXED，import boundary 清洁。

## Controller Rejected Findings Verification

### Followup digest excludes `resolved_execution_target` — rejected, plan/test backed

- Controller 判定依据: Phase 3 plan 明确要求 follow-up queue digest 排除 `resolved_execution_target`。
- 测试锁定: `test_followup_idempotency_excludes_later_resolved_execution_target` 断言同 key 不同 target 的请求返回幂等重放而非 SEMANTIC_CONFLICT。
- **判定合理**: 行为由 plan 和测试双重锁定，非遗漏。

### ATTACH_ACTIVE does not append EventLog — rejected, plan/test backed

- Controller 判定依据: Phase 3 plan 明确 `attach_active` 不写 EventLog、幂等记录 event ref 为 null。
- 测试锁定: `test_reject_and_attach_active_have_expected_event_and_idempotency_effects` 断言无 EventLog 副作用。
- **判定合理**: 行为由 plan 和测试双重锁定，非遗漏。

### Broad failure-path test coverage — rejected as PR-blocking scope

- Controller 判定依据: Phase 3 已有 state/admission/multiprocess 核心不变量覆盖；列表中无当前行为缺陷。
- **判定合理**: 测试缺口属于 hardening 范畴，不阻塞 PR 合并。Phase 4/5/11 各有归属。

### `closeout_attempt_terminal` no idempotency replay — rejected, deferred to Phase 5

- Controller 判定依据: Phase 3 plan 明确 `internal_terminal_closeout` 非 public command，不需要幂等重放。
- **判定合理**: CAS 保证重复调用不产生副作用，调用方收到 INVALID_STATE 而非幂等重放是设计决策。

### Cancel CAS status code inconsistency — rejected

- Controller 判定依据: `cancel_running_run_row` 有额外 `current_attempt_id` CAS 谓词，rowcount=0 语义不同于另外两个 cancel 函数。
- **判定合理**: CAS 语义确实不同，统一反而降低精确度。

### REJECT policy no idempotency record — rejected

- Controller 判定依据: Phase 3 plan 明确 reject + active Run 不写幂等记录。测试已覆盖。
- **判定合理**: 行为由 plan 和测试锁定。

### ATTACH_ACTIVE replay returns non-active Run — rejected

- Controller 判定依据: Phase 3 plan 明确同 digest attach_active 重放返回原始 Run，不论其当前状态。
- **判定合理**: 幂等语义正确，不创建重复工作。Phase 4 可调整 API 命名。

### Attempt DDL includes future statuses — rejected

- Controller 判定依据: Phase 3 schema 编码 Host 设计完整状态集，transition helpers 只实现 Phase 3 子集。
- **判定合理**: DDL 与 `docs/host/design.md` 对齐，移除反而偏离设计。

## Fix Introduced Issues Check

### 状态机行为: 无新问题

- `_promote_after_release` 仅改变 wakeup/promotion 执行顺序和异常处理，不改变状态转换逻辑。
- durable promotion 异常仍正常传播，符合 controller 约束。

### EventLog / CAS 事务一致性: 无新问题

- promotion 在独立事务中执行，与 cancel/closeout 事务分离。
- queue wakeup 在 promotion 事务提交后执行，不影响事务一致性。
- dispatch wakeup 在 `promote_next_queued_run` 事务提交后执行，`suppress_runtime_error=True` 仅吞掉 wakeup 异常。

### import boundary: 无新问题

- `TABLE_EVENT_LOG` 已完全移除，admission 通过 `EventLogStore` 接口访问 EventLog。
- 无新增跨层 import。

### 弱类型: 无新问题

- `_wake_dispatch_if_needed` 新增 `suppress_runtime_error: bool` keyword-only 参数，类型明确。
- `_require_event_sequence` 新增 `event_log_store: EventLogStore` 参数，类型明确。
- pyright 0 errors 确认。

### README 同步: 已更新

- `dayu/host/README.md` 新增一行: "post-commit wakeup 边界：active slot 释放后的 durable promotion 先于 queue promotion wakeup；promotion 已提交后的 dispatch / queue wakeup `RuntimeError` 只按 best-effort 处理，不回滚或掩盖 durable promotion 结果。"
- 与代码实现一致。

### 测试质量: 良好

- 3 个新测试覆盖 PR50-C-001 的全部子场景。
- `_ToggleFailingWakeupSpy` 继承 `_WakeupSpy`，通过 `fail_dispatch` / `fail_queue_promotion` 开关控制异常注入，设计清晰。
- 测试断言覆盖: 主操作结果状态、promotion 结果、queued Run 最终状态、wakeup spy 调用记录。

## Conclusion

**Accepted / No blocking findings.**

三个 controller accepted findings 全部 fixed，验证命令全部通过，fix 未引入新问题。Controller rejected findings 均有 plan/test 依据，判定合理。
