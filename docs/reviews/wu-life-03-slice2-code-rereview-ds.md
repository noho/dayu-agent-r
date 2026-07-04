# Code Re-Review — WU-LIFE-03 Slice 2 Fix (AgentDS)

## Scope

- Mode: current changes (fix re-review)
- Branch: `phase/host-engine-next`
- Base: `main` (Slice 1 commit `ef2d3644`; fix applied on top of uncommitted Slice 2 changes)
- Output file: `docs/reviews/wu-life-03-slice2-code-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-life-03-slice2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-life-03-slice2-code-review-controller-adjudication.md`
- Reviewed scope: controller accepted findings S2-CR-F01 与 S2-CR-F02 的修复，以及修复是否引入新 defect 或违反架构约束。
- Excluded scope: DS F02（Protocol 位置）、DS F03（重叠 check）— controller 已明确 reject/defer，不在本轮 re-review 范围内。
- Parallel review coverage: 无（单 agent 全量走读修复 diff 与相关测试）。

## Findings

### S2-CR-F01 Closure Verification

**结论：CLOSED** — 修复正确且完整。

**修复验证**：

- `dayu/host/recovery.py:676-683` — `_has_accepted_cancel_fact` 新增 `try: ... except HostDurableError: return False`，与 `dispatch.py::_read_linked_cancel_requested_event`（line 4141-4148 附近）的防御模式一致。
- 函数内其他防御路径完整：`cancelling is None → False`（line 673-674）、`cancel_request_event_id` 非 str → False（line 685-686）、链接的 `CANCEL_REQUESTED` 不存在/不匹配 → False（line 691-694）。
- 调用方 `_classify_run`（line 293-308）在 `_has_accepted_cancel_fact` 返回 `False` 时回退到 `_classify_active_or_cancelling`，不会错误 defer 到 watchdog。
- 导入完整：`HostDurableError`（line 20）、`event_payload_object`（line 48）、`Mapping`/`JsonValue`（line 14, 17）。

**测试验证**：

- `test_scan_malformed_cancelling_payload_uses_orphan_policy`（`tests/host/test_recovery_scan.py:717`）：
  - 写入 `payload_json="malformed-cancelling-payload"`（非合法 JSON object）的 `RUN_CANCELLING` event。
  - 以 `defer_accepted_cancel_to_watchdog=True` 运行 scan。
  - 断言 scan 不崩溃（返回 `StartupRecoveryScanResult`）。
  - 断言 Run 分类为 `RUN_LOST` 而非 `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`。
  - 断言产生 1 条 `RUN_LOST` event（正常 orphan closeout 路径）。
- 补充测试 `test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled`（line 687）验证正常 accepted-cancel 路径的 defer 行为（正向用例）。
- 补充测试 `test_scan_watchdog_disabled_keeps_cancelling_orphan_policy`（line 745）验证 `defer_accepted_cancel_to_watchdog=False` 时仍走 orphan 策略（回归防护）。

**测试执行**：3/3 通过（0.31s）。

### S2-CR-F02 Closure Verification

**结论：CLOSED** — 修复正确且完整。

**修复验证**：

- `dayu/host/dispatch.py:_active_cancel_watchdog_loop`（diff 中新增）：
  - Line 2594-2607：per-tick 异常隔离正确。
    ```python
    try:
        result = self.tick_active_cancel_watchdog(datetime.now(UTC))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOGGER.error(...)
        continue
    ```
  - `asyncio.CancelledError` 在 `except Exception` 之前捕获并 re-raise，不会被误吞。
  - 非 cancel 异常记录 `dispatch.active_cancel_watchdog.tick_failed` 日志（含 `host_handle_id` 与 `error_type`），随后 `continue` 进入下一轮 `while not self._closed` 迭代。
  - 外层 `except asyncio.CancelledError`（line 2612-2616）正确处理 scheduler close 取消信号。
  - 外层 `except Exception`（line 2617-2623）作为安全网记录 `fatal_exit` 日志——仅在 queue 本身故障等极端情况下触发，行为与代码库中其他后台 loop 一致。

**测试验证**：

- `test_active_cancel_watchdog_loop_continues_after_transient_tick_failure`（`tests/host/test_dispatch_scheduler.py:2714`）：
  - 使用 `_TransientFailingActiveCancelWatchdogScheduler` 测试子类——第一次 `tick_active_cancel_watchdog` 抛出 `RuntimeError`，第二次成功并置位 `second_tick_seen` event。
  - 测试调用 `wake_active_cancel_watchdog()` 触发第一轮 tick，然后等待 `second_tick_seen`（timeout=0.5s）。
  - 断言 `_active_cancel_watchdog_task.done() is False`（loop 仍在运行，未被异常终止）。
  - 断言 `"dispatch.active_cancel_watchdog.tick_failed"` 与 `"error_type=RuntimeError"` 出现在日志中。
  - 测试子类方式隔离了 `tick_active_cancel_watchdog` 的真实 durable 实现——fix artifact 已明确记录此 tradeoff：核心验证目标是"一次 transient 非 cancel tick 异常不能终止后台 loop"。

**测试执行**：1/1 通过（含于 142 passed）。

### 无新 Material Defect 引入

对修复 diff 做 adversarial failure pass，未发现新 defect：

1. **类型安全**：`_has_accepted_cancel_fact` 返回 `bool`、`payload: Mapping[str, JsonValue]` 类型标注正确；`_active_cancel_watchdog_loop` 的 `except asyncio.CancelledError` 与 `except Exception` 顺序正确（不会误吞 `CancelledError`）。pyright 0 errors。

2. **Docstring**：`_has_accepted_cancel_fact`、`_validate_watchdog_now`、`_read_active_cancel_watchdog_candidates`、`_active_cancel_watchdog_candidate_from_run` 等新增/修改函数均有完整中文 docstring，含参数、返回值、异常说明。

3. **架构边界**：
   - 未引入跨层依赖或反向 import。
   - `recovery.py` 新增 import 均来自 `dayu.host.durable` 或 `dayu.contracts`，不穿透 `dayu.engine` / `dayu.service` / `dayu.ui`。
   - `dispatch.py` 新增 import（`ActiveCancelTimeoutCloseoutInput`、`active_cancel_timeout_closeout_in_transaction`、`read_non_terminal_runs`）均为同层或 durable 子模块导入，无违规。

4. **恢复路径正确性**：
   - `_has_accepted_cancel_fact` 在 `HostDurableError` 时返回 `False` → 回退到 `_classify_active_or_cancelling` → orphan 策略标记 `RUN_LOST`。该路径不会造成 `CANCELLING` Run 静默悬挂。
   - 若 `defer_accepted_cancel_to_watchdog=False`（显式关闭或 `active_cancel_timeout_seconds=None`），即使 payload 正常，`_has_accepted_cancel_fact` 也不会被调用（外层条件先检查 `self.defer_accepted_cancel_to_watchdog`）。正确。

5. **Watchdog loop 异常安全**：
   - `_active_cancel_watchdog_queue.get()` 超时后的 `TimeoutError` 正确处理（pass → 检查 `_closed` → 继续）。
   - `tick_active_cancel_watchdog` 内的 `HostTransactionRetryExhaustedError` 不属于 `asyncio.CancelledError`，会被 `except Exception` 捕获并 `continue`——符合 F02 修复目标。
   - 外层 `except Exception` 仅捕获 queue 自身故障等极端异常，行为与 `_drain_loop` 等其他后台 loop 的安全网模式一致。

6. **非目标 DS F02/F03 无回归**：
   - DS F02（`ActiveCancelWatchdogWakeupPort` 位置）：修复未触碰 `command.py` Protocol 定义，不改变依赖关系。
   - DS F03（overlapping check）：修复未修改 `_read_active_cancel_watchdog_candidates` 筛选逻辑或 `active_cancel_timeout_closeout_in_transaction` precondition，重叠仍然存在但行为一致。

## Open Questions

无。

## Residual Risk

- watchdog loop 测试使用 `_TransientFailingActiveCancelWatchdogScheduler` 子类注入异常，非真实 durable storage 故障。如果 `tick_active_cancel_watchdog` 内部某条路径抛出非 `Exception` 子类的 `BaseException`（理论上不应出现），当前隔离不会捕获。风险极低，属测试覆盖的合理边界。
- `_has_accepted_cancel_fact` 与 `_read_linked_cancel_requested_event` 逻辑重复（均为 RUN_CANCELLING → payload → CANCEL_REQUESTED 链路校验），但分属 recovery 与 dispatch 模块且返回值语义不同（bool vs EventLogRow | None）。当前不强制抽取共享 helper，但若后续出现第三处相同链路校验应考虑抽取。

## Conclusion

**PASS** — 无 BLOCKING FINDINGS。

Closure 状态：

| Finding | Status | 验证依据 |
|---------|--------|---------|
| S2-CR-F01 | **CLOSED** | `_has_accepted_cancel_fact` 捕获 `HostDurableError` 并返回 `False`；`test_scan_malformed_cancelling_payload_uses_orphan_policy` 验证 malformed payload 不 crash 且不 defer 给 watchdog |
| S2-CR-F02 | **CLOSED** | `_active_cancel_watchdog_loop` per-tick `except Exception` + `continue`；`test_active_cancel_watchdog_loop_continues_after_transient_tick_failure` 验证 transient 异常后 loop 继续 |

修复未引入新 material defect，未违反 AGENTS.md 类型/docstring/架构约束，DS F02/F03 未因此次修复变为实际问题。

测试验证：142 passed / pyright 0 errors / 0 warnings / 0 informations。
