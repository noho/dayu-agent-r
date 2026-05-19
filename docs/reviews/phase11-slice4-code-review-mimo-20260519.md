# Phase 11 Slice 4 Code Review — AgentMiMo — 2026-05-19

## Verdict

**PASS** — blocking count = 0。

## 审查范围

工作区：`/Users/leo/workspace/dayu-agent-r`，分支 `feat/host-phase-11-recovery`。

未提交 diff（`git diff HEAD`）涉及 8 个文件、+518 / -58 行：

| 文件 | 变更性质 |
|------|----------|
| `dayu/host/durable/run_transition.py` | +219：新增 `CancelRecoveringRunInput`、`cancel_recovering_run_in_transaction`、`_cancel_recovering_run_row`、`_validate_cancel_recovering_input`、`_read_current_attempt_if_present`、`_read_current_dispatch_record_if_present`；扩展 `_cancel_requested_event_request` 与 `_run_cancelled_event_request` union |
| `dayu/host/admission.py` | +130：新增 `_CancelRunOperation._cancel_recovering`、`_CancelSessionRunsOperation._cancel_recovering_target`、`_SupportedSessionCancelTarget.recovering` 字段；修改 `_session_cancel_target_for_run` RECOVERING 分支从 `return None` 改为返回 supported target |
| `dayu/host/command.py` | +9/-6：`_IsDeferredCancelStateOperation` 移除 RECOVERING 分类；docstring 更新 |
| `tests/host/test_public_cancel_session_runs.py` | +148/-58：新增 `test_cancel_run_recovering_appends_no_attempt_terminal`、`test_cancel_session_runs_includes_recovering_without_fail_closed`；删除旧 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation`；新增 `_cancel_run_request`、`_event_types_for_run`、`_attempt_status` helper |
| `tests/host/test_public_cancel_smoke.py` | +52：新增 `test_recovering_cancel_does_not_propagate_worker_cancel`、`_mark_run_recovering` helper |
| `dayu/host/README.md` | +6/-6：更新 cancel_run / cancel_session_runs 覆盖范围描述；RECOVERING 状态描述增加 cancel 语义 |
| `tests/README.md` | +4/-4：更新 cancel 覆盖范围描述 |
| `docs/host/implementation-control.md` | +8：更新 gate 状态与 Slice 4 事实 |

设计真源：`docs/host/design.md` §22 Cancel 表 `cancel_run on recovering before dispatch` 行。

## 验证命令结果

```bash
# focused tests
pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
# 结果：19 passed in 0.65s

# pyright
python -m pyright dayu/host tests/host
# 结果：0 errors, 0 warnings, 0 informations

# trailing whitespace
git diff --check
# 结果：clean
```

## Findings

### Blocking

无。

### High

无。

### Medium

无。

### Low

#### L1: `_cancel_recovering` 设置 `released_active_slot=True` 但 RECOVERING 不持有 active slot

`dayu/host/admission.py:1755` — `_cancel_recovering` 返回 `released_active_slot=True`。RECOVERING Run 的旧 Attempt 已关闭，不持有 active execution slot。与 `_cancel_waiting`（`True`）一致，语义是"Run 进入终态 CANCELLED 后应触发 queued Run promotion"，而非"释放了一个物理 active slot"。这是当前代码库的既有约定（`True` = terminal + 可 promotion），不是 bug，但值得在后续统一清理时显式区分"释放 active slot"与"进入终态可 promotion"。

#### L2: `_mark_run_recovering` 测试 helper 直接写 DB 不追加 EventLog

`tests/host/test_public_cancel_session_runs.py:390-403` 与 `tests/host/test_public_cancel_smoke.py:246-258` — 两个 `_mark_run_status` / `_mark_run_recovering` helper 通过 raw SQL 直接把 Run status 改为 RECOVERING，不追加 `RUN_RECOVERING` EventLog。这在 focused test 场景下是合理的（测试目标是 cancel 路径，不是 recovery 创建路径），但意味着测试不验证 EventLog 一致性。implementation artifact 已声明此为 residual risk，归 Slice 2/3 与后续 multiprocess coverage。

## 逐项审查

### 1. 设计对齐

`docs/host/design.md` §22 Cancel 表明确定义：

> `cancel_run on recovering before dispatch`：Run `RECOVERING` 且无新 Attempt dispatch committed → Run `CANCELLED` → `CANCEL_REQUESTED`、`RUN_CANCELLED` → 不创建新 Attempt；不进入 `CANCELLING`

实现完全对齐：
- `cancel_recovering_run_in_transaction`（`run_transition.py:2356-2419`）只追加 `CANCEL_REQUESTED` + `RUN_CANCELLED`，不追加 `ATTEMPT_CANCELLED`。
- `_cancel_recovering_run_row`（`run_transition.py:2754-2809`）CAS 更新 `host_runs` status 从 RECOVERING 到 CANCELLED，不修改 Attempt 或 dispatch record。
- `_cancel_recovering`（`admission.py:1695-1756`）不产生 `active_cancel_target`，不触碰 WorkerProxy。

### 2. RECOVERING cancel 只追加 Run-level facts、不关闭旧 Attempt

- `cancel_recovering_run_in_transaction` 传入 `terminal_attempt_id=None`、`terminal_attempt_event_id=None` 给 `_run_cancelled_event_request`。
- 测试 `test_cancel_run_recovering_appends_no_attempt_terminal`（`test_public_cancel_session_runs.py:458-491`）断言 `event_types[-2:] == (CANCEL_REQUESTED, RUN_CANCELLED)` 且 `ATTEMPT_CANCELLED not in event_types`，同时验证旧 Attempt 状态保持 `STARTING` 不变。

### 3. session-scope cancel 包含 RECOVERING 且幂等 scope 未漂移

- `_session_cancel_target_for_run`（`admission.py:4288-4306`）RECOVERING 分支从 `return None` 改为返回 `_SupportedSessionCancelTarget(recovering=True)`。
- `_cancel_target`（`admission.py:2066-2085`）dispatch 优先级：`queued → waiting → recovering → active_worker → predispatch`。RECOVERING 在 active_worker 之前，正确。
- `_CancelSessionRunsOperation.__call__`（`admission.py:1953`）幂等 scope 仍为 `(session_id, client_request_id)`，未漂移。
- 测试 `test_cancel_session_runs_includes_recovering_without_fail_closed`（`test_public_cancel_session_runs.py:495-517`）验证 RECOVERING + queued 同批取消，session snapshot 正确。

### 4. closed/shutdown/watcher 行为未被意外改变

- `command.py` 的 `_IsDeferredCancelStateOperation` 移除了 RECOVERING 分类（`command.py:1232-1233`），RECOVERING 不再走 deferred cancel 路径，而是直接走 `_cancel_recovering` 闭环。这是正确的，因为 RECOVERING cancel 现在是完整实现。
- graceful shutdown 代码路径无修改。implementation artifact 声明"现有 close ordering 已正确设置 closed gate first、close scheduler、flush projection、close command handle，不追加用户 cancel 或 synthetic terminal facts"。
- `test_public_lifecycle_smoke.py` 与 `test_watch_session_events.py` 仍在 focused test 集合中且通过，确认 watcher 行为未被影响。

### 5. CAS 安全性

`_cancel_recovering_run_row`（`run_transition.py:2779-2803`）CAS 条件：

```sql
WHERE run_id = ?
  AND status = ?                           -- RECOVERING
  AND terminal_event_id IS NULL
  AND terminal_event_sequence IS NULL
  AND terminal_at IS NULL
```

- `terminal_event_id IS NULL` / `terminal_event_sequence IS NULL` / `terminal_at IS NULL` 防止重复 terminal 化。
- `status = RECOVERING` 防止与 recovery dispatch 竞争（recovery dispatch 会先 CAS RECOVERING → RUNNING）。
- 在单个 HostTransaction 内执行，SQLite WAL 保证原子性。

### 6. 状态机 / EventLog / 分层 / 类型 / docstring

- 所有新增函数/类均有完整中文 docstring，包含参数、返回值、异常。
- 类型签名无 `Any`、`object`、无类型参数。
- `CancelRecoveringRunInput` 是 frozen slots dataclass，字段与 `CancelWaitingRunInput` 对齐。
- `_cancel_requested_event_request` 与 `_run_cancelled_event_request` 的 union 类型已扩展包含 `CancelRecoveringRunInput`。
- `_SupportedSessionCancelTarget` 新增 `recovering: bool` 字段，所有构造点均已补全。

### 7. 测试覆盖

| 测试 | 覆盖点 |
|------|--------|
| `test_cancel_run_recovering_appends_no_attempt_terminal` | cancel_run 单个 RECOVERING Run：Run → CANCELLED，Attempt 不变，只有 Run-level events |
| `test_cancel_session_runs_includes_recovering_without_fail_closed` | session-scope cancel：RECOVERING + queued 同批取消，无 fail-closed |
| `test_recovering_cancel_does_not_propagate_worker_cancel` | public path：RECOVERING cancel 不触碰 active WorkerProxy |
| 既有 `test_cancel_session_runs_cancels_queued_and_predispatch_subset` | 确认非 RECOVERING 子集未被回归 |
| 既有 `test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run` | 确认幂等 scope 未漂移 |

### 8. README 同步

- `dayu/host/README.md`：cancel_run / cancel_session_runs 覆盖范围描述已更新包含 recovering；RECOVERING 状态描述已增加 cancel 语义。
- `tests/README.md`：cancel 覆盖范围描述已更新包含 RECOVERING。
- 无根 README 更新需求（无用户 CLI / 配置 / workflow 变更）。

## 总结

Slice 4 实现与 `docs/host/design.md` §22 Cancel 的 RECOVERING cancel 设计语义完全对齐。durable transition 只追加 `CANCEL_REQUESTED` + `RUN_CANCELLED`，不修改旧 Attempt 或 dispatch record，CAS 条件正确防御多进程竞争。session-scope cancel 现在包含 RECOVERING，幂等 scope 未漂移，dispatch 优先级正确。deferred-cancel 分类变更合理。graceful shutdown / watcher 行为未被影响。代码符合分层、类型、docstring 约束。测试覆盖核心路径，focused tests 与 pyright 均通过。
