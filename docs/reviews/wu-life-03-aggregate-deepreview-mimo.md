# WU-LIFE-03 Aggregate Deepreview — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phase/host-engine-next`
- Base: `main`
- Output file: `docs/reviews/wu-life-03-aggregate-deepreview-mimo.md`
- Included scope: WU-LIFE-03 全部本地变更——plan artifacts、Slice 1 durable timeout closeout / ingest late terminal handling、Slice 2 Host watchdog runtime integration / recovery defer / open_host startup ordering / public watch behavior、README/design/control docs、全部 tests 和 review/fix artifacts。
- Excluded scope: 无。
- Parallel review coverage: 无 subagent；单 reviewer 全量走读。

## WU-LIFE-03 目标完整性评估

### 目标 1：active cancel accepted 后 Host durable truth 不依赖 worker/provider/tool cooperation

**结论：满足。**

`active_cancel_timeout_closeout_in_transaction()` (`run_transition.py:2248-2352`) 独立于 worker event stream，通过 durable SQL 扫描 `CANCELLING` Run + `RUNNING` Attempt + worker accepted dispatch record + 链接 `CANCEL_REQUESTED` fact，写入 `ATTEMPT_CANCELLED` + `RUN_CANCELLED` terminal facts。不依赖 Engine `run_cancelled` event、provider 返回或 tool cooperation。

### 目标 2：timeout 后有 CANCELLED terminal closeout

**结论：满足。**

`HostDispatchScheduler.tick_active_cancel_watchdog()` (`dispatch.py:1071-1152`) 执行 deterministic tick：SQL scan → timeout 判断 → `active_cancel_timeout_closeout_in_transaction()` → projection catchup → queue promotion wakeup。payload 包含 `timeout_seconds`、`cancel_requested_at`、`timed_out_at`、`watchdog_owner`、`worker_lifecycle_signal`，符合 plan 要求。

### 目标 3：first-committer-wins / late terminal / replay 一致性

**结论：满足。**

- **first-committer-wins**: `_active_cancel_timeout_replay_result()` (`run_transition.py:5030-5060`) 识别同终态 replay 返回 `UPDATED`；`_invalid_active_cancel_timeout_closeout_precondition()` (`run_transition.py:5063-5120`) 要求 Run 为 `CANCELLING`、Attempt 为 `RUNNING`、dispatch 已 worker accepted 且未 cancelled。cooperative cancel 或其它 terminal 先到时，timeout closeout 前置不满足。
- **late terminal after RUN_CANCELLING**: `_late_rejection_reason()` (`engine_ingest.py:3299-3305`) 在 Run 为 `CANCELLING` 且 engine event 为 `FINAL_ANSWER` / `RUN_FAILED` 时返回 `_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL`，拒绝写入 success/failure terminal。
- **late terminal after timeout closeout**: Attempt 已 terminal 时，`_late_rejection_reason()` 返回 `_REASON_TERMINAL_ALREADY_CLOSED`。
- **awaiting/suspend after cancel**: `RUN_CANCELLING` 下的 `run_suspended` / `tool_awaiting` 仍被 ingest 接受为 diagnostic，但 `_validate_waiting_confirmation()` 不会将 Run 推入 `WAITING`（现有逻辑已覆盖）。
- **cancel replay**: `cancel_run` / `cancel_session_runs` 不重复追加 `CANCEL_REQUESTED` / `RUN_CANCELLING`，但仍传播 active cancel 到 registry；cancel commit 唤醒 watchdog。

### 目标 4：startup recovery ordering

**结论：满足。**

`open_host.py:892-901` startup 顺序为：
1. `scheduler.tick_active_cancel_watchdog(datetime.now(UTC))` — 已超时的 `CANCELLING` Run 关闭为 `CANCELLED`
2. `StartupRecoveryScanner(..., defer_accepted_cancel_to_watchdog=True).scan()` — 剩余 accepted-cancel `CANCELLING` Run defer 给 watchdog，不转为 `LOST`

`_has_accepted_cancel_fact()` (`recovery.py:654-695`) 校验 `RUN_CANCELLING` 存在且链接到同 Run 的 `CANCEL_REQUESTED`；malformed payload 时 fallback 到 orphan policy（已有测试覆盖）。

### 目标 5：scheduler close 不写 timeout terminal

**结论：满足。**

`HostDispatchScheduler.close()` 取消 watchdog task、调用 `cancel_all("scheduler_close")` 传播本地 cancel、清空 registry，但不调用 `tick_active_cancel_watchdog()`，不写任何 terminal fact。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **timeout CANCELLED 不物理停止 provider/tool work**: 属于 WU-TOOLS-CANCEL-01 scope。当前 Host terminal truth 已正确收敛，但 provider 侧可能继续产出 side effects。Plan 已明确记录该 residual risk owner。
- **cross-instance UTC clock skew**: reopen 后 watchdog 比较 durable UTC event timestamp 与当前 Host UTC time，clock skew 可能导致 timeout detection 略早或略晚。属 Host lifecycle watchdog runtime tuning scope under #87。
- **`active_cancel_timeout_seconds` 默认 300 秒**: 生产调优需验证是否适合所有 provider/worker backend。属 Host runtime config follow-up。

## Review Coverage Matrix

| 区域 | 覆盖状态 | 审查结论 |
|---|---|---|
| `dayu/host/durable/run_transition.py` — timeout closeout helper + payload + validation + replay | ✅ 完整走读 | 正确：独立 helper、CAS 前置、replay 同终态、malformed cancelling 拒绝 |
| `dayu/host/dispatch.py` — watchdog tick/loop/candidate scan/wakeup | ✅ 完整走读 | 正确：SQL scan、timeout 判断、projection catchup、queue promotion |
| `dayu/host/engine_ingest.py` — late terminal rejection | ✅ 完整走读 | 正确：FINAL_ANSWER/RUN_FAILED after CANCELLING rejected |
| `dayu/host/recovery.py` — defer accepted cancel to watchdog | ✅ 完整走读 | 正确：malformed payload fallback、disabled watchdog 保持原 behavior |
| `dayu/host/open_host.py` — startup ordering + watchdog wakeup port | ✅ 完整走读 | 正确：tick → scan → admission → command handle |
| `dayu/host/api.py` — `active_cancel_timeout_seconds` option | ✅ 完整走读 | 正确：optional positive finite float validation |
| `dayu/host/command.py` — watchdog wakeup after cancel commit | ✅ 完整走读 | 正确：best-effort wakeup port protocol |
| `dayu/host/README.md` — cancel/runtime/recovery 文档 | ✅ 完整走读 | 准确反映已实现行为 |
| `docs/host/design.md` — cancel/startup 文档 | ✅ 完整走读 | 准确反映已实现行为 |
| `docs/host/issues-implementation-control.md` — WU-LIFE-03 状态 | ✅ 完整走读 | 状态正确 |
| `tests/host/test_run_attempt_transitions.py` — timeout closeout tests | ✅ 完整走读 | 覆盖：正常 closeout、requires cancelling、malformed payload、first-committer-wins (cooperative/succeeded) |
| `tests/host/test_engine_ingest_mapping.py` — late terminal tests | ✅ 完整走读 | 覆盖：late terminal after timeout、late final_answer/run_failed after CANCELLING、late awaiting |
| `tests/host/test_active_cancel_dispatch.py` — watchdog integration tests | ✅ 完整走读 | 覆盖：timeout、noop before timeout、zero/multiple cancelling、reopen close/reopen defer |
| `tests/host/test_recovery_scan.py` — recovery defer tests | ✅ 完整走读 | 覆盖：defer enabled、malformed payload、disabled watchdog |
| `tests/host/test_open_host_runtime.py` — public watch/reopen tests | ✅ 完整走读 | 覆盖：public watch observes cancelled、reopen closes as CANCELLED、reopen defers |
| `docs/host/wu-life-03-active-cancel-watchdog-plan.md` — plan artifact | ✅ 完整走读 | code-generation-ready，实现与 plan 一致 |
| review/fix artifacts | ✅ 抽查 | gate 流程完整 |

## Architecture Boundary Assessment

- **Host/Engine 分层**: timeout closeout 完全在 Host 层（`run_transition.py` + `dispatch.py`），不修改 Engine public contract。✅
- **dayu.runtime**: 无新增依赖。✅
- **Service/public API**: `OpenHostOptions.active_cancel_timeout_seconds` 为 construction-time option，不新增 public command method。✅
- **EventLog schema**: 使用现有 `ATTEMPT_CANCELLED` / `RUN_CANCELLED` event types，无 schema 变更。✅
- **LLM-facing text**: 无变更。✅

## Conclusion

**PASS**

WU-LIFE-03 实现完整满足全部 5 个目标。first-committer-wins、late terminal rejection、replay、queue promotion、projection、startup recovery ordering 跨 Slice 1+2 一致。无架构边界问题。测试矩阵覆盖关键行为，无为旧测试添加兼容或表面修复的情况。README/design docs 准确反映已实现行为。
