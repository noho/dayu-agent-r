# Code Review — Phase 11 Slice 2

## Scope

- Mode: current changes
- Branch: feat/host-phase-11-recovery
- Base: 235cf7d (Phase 11 Slice 1 accepted commit)
- Output file: docs/reviews/phase11-slice2-code-review-ds-20260519.md
- Included scope: `dayu/host/recovery.py`, `dayu/host/durable/run_transition.py`, `dayu/host/durable/state.py`, `dayu/host/durable/event_log.py`, `tests/host/test_recovery_scan.py`, `tests/host/test_run_attempt_transitions.py`, `dayu/host/README.md`, `docs/host/implementation-control.md`
- Excluded scope: Engine, public API, schema migration, dispatch implementation, Slice 3/4/5 code
- Parallel review coverage: 无

## Findings

### 1. 未修复-低-`int()` 截断导致 CAS recheck 的 stale 判断与 classifier 的 timedelta 精度不一致

- **入口/函数**: `_close_positive_orphan` → `close_startup_orphan_attempt_in_transaction` → `_invalid_startup_orphan_precondition`
- **文件(行号)**: `dayu/host/recovery.py:369-370` 传入 `stale_after_seconds=int(policy.stale_after.total_seconds())`；`dayu/host/durable/run_transition.py:4563-4566` 使用该值做比较
- **输入场景**: `policy.stale_after` 为非整数秒 timedelta（如 `timedelta(seconds=30, microseconds=500000)`）
- **实际分支**: `int()` 向下取整为 30，CAS recheck 的 `(occurred_at - heartbeat_at).total_seconds() > 30` 判断边界比 `timedelta(seconds=30.5)` 宽松 0.5 秒
- **预期行为**: CAS recheck 的 stale 阈值应与 classifier 使用的阈值（`policy.now - heartbeat_at <= policy.stale_after`）语义一致
- **实际行为**: 在默认 `timedelta(seconds=30)` 整数秒阈值下无实际差异；仅在非整数阈值时 CAS recheck 比 classifier 更早判定 stale，但此时 classifier 已返回 `OwnerStillLive`，不会进入 CAS 路径，故不存在实际误判路径
- **直接证据**: `recovery.py:369` `stale_after_seconds=int(policy.stale_after.total_seconds())` → `run_transition.py:4566` `(request.occurred_at - heartbeat_at).total_seconds() > request.stale_after_seconds`
- **影响**: 当前默认策略无影响；未来若调整为非整数 stale threshold 且在 positive proof 边界附近，可能出现 classifier 判定 not-stale 但 CAS 判定 stale 的理论不一致，但该场景下 CAS 路径不会被触发，故无实际风险
- **建议改法和验证点**: 可选将 `stale_after_seconds` 改为 `float` 或在 `StartupOrphanCloseInput` 中直接传递 `timedelta`；当前默认配置下无害，无需立即修复
- **修复风险（低）**:
- **严重程度（低）**:

---

以下逐项确认用户指定的 correctness 检查点，均未发现实质性问题。

#### 1. startup scan 分类 ACCEPTED/QUEUED/WAITING/RUNNING/CANCELLING/RECOVERING

`_classify_run`（`recovery.py:169-201`）使用 `is` 身份比较精确命中各状态，fallthrough 返回 `INVALID_STATE`。分支顺序：ACCEPTED → QUEUED → WAITING → RECOVERING → (RUNNING|CANCELLING) → fallthrough，无宽条件抢先命中覆盖更具体分支的问题。

`read_non_terminal_runs`（`state.py:693-740`）以 `ORDER BY accepted_event_sequence ASC, run_id ASC` 保证确定性扫描顺序；SQL `WHERE status IN` 覆盖全部六个非终态。

#### 2. WAITING diagnostic-only fallback

`recovery.py:192-196`：WAITING 直接返回 `WAITING_DIAGNOSTIC_ONLY`，不写 EventLog、不创建 Attempt、不修改 Run/Attempt 状态。测试 `test_scan_waiting_uses_diagnostic_only_fallback`（`test_recovery_scan.py:123-140`）验证 Attempt 数量不变（仍为 1）、Run 状态保持 WAITING。符合 plan 要求。

#### 3. positive orphan CAS recheck 覆盖 Run/Attempt/dispatch/owner/heartbeat stale

`_invalid_startup_orphan_precondition`（`run_transition.py:4508-4597`）在同一 write transaction 内重新读取四行的最新快照，逐字段验证 20+ 条件：

- Run: `status`、`current_attempt_id`、terminal 三字段 IS NULL
- Attempt: `run_id`、`status`、`execution_id`、terminal 三字段 IS NULL
- Dispatch: `dispatch_record_id`、`run_id`、`attempt_id`、`execution_id`、`status`、`owner_host_instance_id`、cancel 两字段 IS NULL
- Owner: `status == RUNNING`、`heartbeat_at` 未变、heartbeat 仍 stale

关键保护：`owner.heartbeat_at != request.owner_heartbeat_at` 捕获 classifier 读取到 CAS recheck 之间的任何 heartbeat 变更；`not heartbeat_stale` 防止 heartbeat parse 结果恰好落在阈值内。测试 `test_startup_orphan_closeout_cas_rechecks_owner_heartbeat` 用最新 heartbeat 触发 `INVALID_STATE`，0 个 ATTEMPT_LOST 事件，验证 CAS 不误写。

#### 4. 同事务 ATTEMPT_LOST 再 RUN_RECOVERING/RUN_LOST 顺序

`close_startup_orphan_attempt_in_transaction`（`run_transition.py:1285-1298`）严格按序：
1. validate input
2. CAS recheck
3. `append_event(ATTEMPT_LOST)`
4. `append_event(RUN_RECOVERING)` 或 `append_event(RUN_LOST)`
5. `terminal_attempt_row(LOST)`
6. `terminal_orphaned_run_lost_row` 或 `mark_running_run_recovering_row`

步骤 5/6 均经过 `_require_attempt_mutation_updated` / `_require_run_mutation_updated` 强制断言；若 state mutation 失败，`HostDurableError` 触发事务回滚，保护已 append 的 EventLog row 不与错误 state 并存。测试 `test_startup_orphan_closeout_marks_attempt_lost_then_run_recovering` 验证 event_types 最后两个为 `(ATTEMPT_LOST, RUN_RECOVERING)`。

#### 5. CANCELLING orphan 不恢复

`_close_positive_orphan`（`recovery.py:348-354`）：`recoverable` 的第一个条件是 `run.status is RunStatus.RUNNING`，CANCELLING 直接为 False。进入 `RUN_LOST` 路径，reason 取 `_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST`。`_validate_startup_orphan_close_input`（`run_transition.py:5125`）额外校验 `recoverable=True` 时 `expected_run_status` 必须为 RUNNING，防止调用方误用。

#### 6. recovery dispatch count 使用 typed EventLog helper

`count_recovery_dispatches_for_run`（`event_log.py:598-634`）：SQL 查询 `run_id + event_type='RUN_STARTED' + event_class='canonical_fact'`，不在 SQL 层做 payload 文字匹配。对每条返回的 payload_json 解析后取 `start_reason` 字段，要求值必须在 `allowed_values`（`initial`, `queue_promotion`, `resume`, `steer`, `recovery`）内，否则 fail-closed 抛 `HostDurableError`。只计数 `start_reason == "recovery"`。不读取 projection/read-model/diagnostic event。

#### 7. projection lag 不影响分类

测试 `test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag`（`test_recovery_scan.py:143-163`）写入 `host_projection_checkpoints` 中 event_sequence=0 的 lag marker，在 EventLog 已有 1 条 recovery RUN_STARTED 的情况下，验证 scanner 基于 EventLog 计数（1 ≥ limit=1）得出 RUN_LOST，Run 状态变为 LOST。测试 `test_scan_running_positive_orphan_moves_to_recovering_without_projection`（`test_recovery_scan.py:90-120`）同样在 projection lag 存在时验证 scanner 正确走向 RECOVERING。

#### 8. 无 dispatch 实现

`_classify_recovering`（`recovery.py:220-224`）：count < limit 时返回 `RECOVERING_READY`，reason 为 `"recovery_dispatch_not_implemented_in_slice2"`，不创建 Attempt，不调用 dispatch scheduler。符合 Slice 2 范围。

#### 9. 无 Engine/public API/schema 变更

diff 仅触及 `dayu/host/` 和 `tests/host/`。未修改 Engine、Service、UI 文件。未新增 public API 方法、`OpenHostOptions` 字段或 schema DDL。新增 `read_non_terminal_runs` 使用既有 `host_runs` 表和既有列；新增 `terminal_orphaned_run_lost_row`、`terminal_recovering_run_lost_row` 更新既有列。

#### 10. tests / docs / pyright

- `pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q`：38 passed
- `pyright dayu/host tests/host`：0 errors, 0 warnings
- `dayu/host/README.md`：在 dispatch scheduler 段落后新增 1 句 recovery scanner 语义描述，与代码一致

## Open Questions

无。

## Residual Risk

- `CANCELLING` orphan → `RUN_LOST` 路径仅有参数校验与 CAS SQL 层保护，缺乏独立 focused test 直接验证 CANCELLING Run 进入 positive orphan closeout 时走 `RUN_LOST`（非 `RUN_RECOVERING`）且 reason 为 `cancel_in_flight_attempt_lost`。当前以 `_startup_closeout_reason` 的纯函数分支 + `_validate_startup_orphan_close_input` 的 recoverable 约束 + CAS SQL 的 expected_status 校验间接保证正确性。
- `ACCEPTED` / `QUEUED` 分类路径无独立 focused test；它们的行为极其简单（直接返回 action，无 mutation），风险低。
- `lose_recovering_run_in_transaction` 的 precondition check 较 `_invalid_startup_orphan_precondition` 更简洁（不检查 source_attempt 的 terminal 状态、execution_id 一致性等），其正确性最终依赖 `terminal_recovering_run_lost_row` 的 SQL CAS。当前路径下 source_attempt 可能已被较早的 `close_startup_orphan_attempt_in_transaction` 设为 LOST 或由 Slice 3 dispatch 设为新 STARTING/RUNNING Attempt；两种场景下将 RECOVERING Run 收口为 LOST 均为正确行为。对 Slice 2 独立使用（非 Slice 3 dispatch 组合）该路径在 `_classify_recovering` 中 `count >= limit` 时仅调用一次，precondition 的简洁性不构成当前正确性问题。

## Conclusion

PASS。Blocking count = 0。所有用户指定 correctness 检查点均通过逐行走读验证，无实质性缺陷。一个低严重度 observation（int 截断）已有分析证明当前默认策略下无害。三个 residual risk 条目记录边界覆盖缺口，均非 blocking。
