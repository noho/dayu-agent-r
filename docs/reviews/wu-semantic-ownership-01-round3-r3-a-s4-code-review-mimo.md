# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S4 Code Review

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `815432ea` (S3 acceptance commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-code-review-mimo.md`
- Included scope: S4 production changes (`dayu/host/durable/state.py`, `dayu/host/recovery.py`, `dayu/host/open_host.py`) and test changes (`tests/host/test_recovery_scan.py`, `tests/host/test_open_host_runtime.py`), plus doc updates (`docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`)
- Excluded scope: S3 health state machine, S5 watchdog/cancel, Service/CLI/Fins/Engine, S2 actor implementation
- Parallel review coverage: 无 (scope 集中, 单 reviewer 可完成)

## Findings

未发现实质性问题。

## Evidence-Based Analysis

### 1. Cursor/watermark 来自 durable governance truth, tie-break 正确

`read_non_terminal_run_upper_watermark()` (state.py) 使用 `ORDER BY accepted_event_sequence DESC, run_id DESC LIMIT 1` 从 durable `host_runs` 表读取固定上界。`read_non_terminal_runs_keyset_page()` (state.py) 使用 keyset 分页:

- 上界: `(accepted_event_sequence < ?) OR (accepted_event_sequence = ? AND run_id <= ?)`
- 游标: `(accepted_event_sequence > ?) OR (accepted_event_sequence = ? AND run_id > ?)`
- 排序: `ORDER BY accepted_event_sequence ASC, run_id ASC`
- 限制: `LIMIT ?` (typed `batch_size` 参数)

Python 端 `_non_terminal_run_keyset_order()` 返回 `(sequence, run_id)` tuple, 利用 Python tuple 比较确保全序一致性。`_validate_non_terminal_run_keyset()` 校验 sequence > 0 且 run_id 非空。

### 2. Batch transaction, commit-after-wake, READY handoff 明确

`_StartupRecoveryBatchOperation.__call__()` 在单个 write transaction 内读取 keyset page 并分类/迁移。`_wake_after_committed_batch()` 只在 `run_write()` 成功返回后调用, 投递 dispatch/queue-promotion wake。rollback 的 batch 不投递 wake。

READY handoff 在 `open_host.py` 中: recovery 通过 `durable_actor.call(_StartupRecoveryActorOperation(...))` 在 actor thread 执行, 完成后才执行 `health_gate.mark_ready()`。异常路径不会 READY (test `test_open_host_startup_failure_flushes_projection_before_close` 验证 `ready_calls == 0`)。

失败重跑不依赖内存 offset: cursor 只从已提交 page 最后一行派生, 完整重跑从 `cursor=None` 开始, 依赖 durable CAS/idempotency 收敛。

### 3. 全量 reader, OFFSET, unbounded transaction 已消除

`recovery.py` 不再 import `read_non_terminal_runs`, source scan 确认 `rg -n 'read_non_terminal_runs\(|OFFSET|fetchall\(' dayu/host/recovery.py` 无命中。recovery call graph 仅通过 `read_non_terminal_run_upper_watermark()` + `read_non_terminal_runs_keyset_page()` 走 bounded path。

### 4. fetchall() 全部 bounded page, 新增 reader 带 LIMIT

`read_non_terminal_runs_keyset_page()` 的 SQL 明确使用 `LIMIT ?`, 参数来自 typed `batch_size` (默认 64)。`fetchall()` 只消费该 bounded page。其它 `fetchall()` 命中属于既有非 S4 readers, 不在 recovery call graph。

### 5. 未改写业务分类

`_classify_run()` 实现未修改。测试 `test_paginated_scan_preserves_accepted_queued_waiting_and_cancel_owners` 验证分页后 `ACCEPTED_WAKE`, `QUEUE_PROMOTION_CHECK`, `WAITING_DIAGNOSTIC_ONLY`, `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG` 分类不变。

### 6. 未越界修改

- S3 health gate: `open_host.py` 仅消费 `mark_ready()`, 未修改 `_execution_health.py`
- S5 watchdog/cancel: 未修改 `dispatch.py` 的 `wake_active_cancel_watchdog` 或 cancel command
- Service/CLI/Fins/Engine: 未 import 或修改
- S2 actor: `_StartupRecoveryActorOperation` 通过 `handle._transaction_runner()` 使用 actor connection, 符合 S2 boundary

### 7. Cursor advancement invariant

`recovery.py` 中 `if batch.next_cursor is None or batch.next_cursor == cursor: raise RuntimeError("startup recovery keyset cursor did not advance")` 防止无限循环。`while cursor != upper_watermark` + `if batch.page_size == 0: break` 提供双重退出条件。

### 8. Fixed policy_now 跨 batch invariant

`_StartupRecoveryBatchOperation.__call__()` 检查 `if self.policy.now != self.policy_now: raise RuntimeError` 确保所有 batch 使用同一冻结时间。测试 `test_policy_now_is_fixed_across_all_batches` 验证 monkeypatched advancing default 只调用一次, 所有 5 行观察到同一 `_NOW`。

## Open Questions

无。

## Residual Risk

1. Legacy `read_non_terminal_runs()` 仍存在于 `state.py`, 非 S4 recovery call graph 消费者仍可使用。删除超出当前 slice。
2. Batch commit 后多个 wake callback 之间非原子事务; 先前 callback 已执行时后续 bridge 失败会导致 opener fail closed, durable pending truth 允许下一 healthy opener 幂等重放。
3. 未运行全仓 pytest; 只验证了 required focused matrix (60 passed)。
