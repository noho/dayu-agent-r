# WU-TOOLS-AWAIT-FANOUT-01 Code Re-review — AgentDS

## Gate

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub Issue #111
- Gate: `code re-review`（fix gate 后）
- Fix artifact: `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`
- Prior review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-code-review-ds.md`
  - `docs/reviews/wu-tools-await-fanout-01-code-review-controller-adjudication.md`

## Scope

- Mode: current changes（dirty workspace on branch `phase/wu-tools-await-fanout-01`）
- Focus: fix 增量相对 controller accepted findings (DS-F01, DS-F03) 的正确性，以及 DS-F02 deferred 边界保持
- Included scope: fix 增量涉及的 `dayu/host/tool_runtime.py`、`tests/host/test_toolruntime_executor.py`、`tests/host/test_toolruntime_duplicate_governance.py`
- Excluded scope: 前序 implementation 已完成的 `dayu/host/tool_duplicate_governance.py` state machine 扩展（非 fix 增量）、`dayu/host/run_input.py` resume material（非 fix 增量）、`dayu/host/README.md`（非 fix 增量）

## Conclusion

**PASS** — 0 unfixed accepted findings，0 new blocking findings。

DS-F01 和 DS-F03 均已正确关闭。DS-F02 仍按 controller 裁决保持 deferred。Fix 保持轻量边界，未触及 `engine_ingest.py`、durable schema/state、public contracts 或 issue-129 activation。验证结果可信：184 passed，pyright 0 errors。

---

## 逐 Finding 复核

### DS-F01: `_record_duplicate_awaiting_accepted` 异常传播修复 ✅ 已关闭

**Pre-fix root cause（确认）**：`_record_duplicate_awaiting_accepted` 原先无 try/except，`record_awaiting_accepted` 抛异常会跳过 `_AwaitingAcceptExecution` 构造，导致 `_execute_one.finally` 使用默认 `GOVERNED_BEFORE_ACCEPT` 执行 durable-missing cleanup，覆盖 owner 的 `ToolAwaitingOutcome` 返回。

**Fix mechanism 逐行走读**：

1. `_record_duplicate_awaiting_accepted`（`tool_runtime.py:2944-3003`）：
   - L2981-3003: `try: await self._duplicate_governance.record_awaiting_accepted(...)` 包裹在 `except Exception` 中
   - 异常路径 L2986-3002：`_LOGGER.warning(...)` + `_emit_duplicate_awaiting_marker_diagnostic_best_effort(...)`
   - L3003: `return True` — 异常不传播，仍返回 terminal 已处理

2. `_accept_awaiting`（`tool_runtime.py:2752-2771`）：
   - L2755-2763: `duplicate_terminal_recorded = await self._record_duplicate_awaiting_accepted(...)` — 即使 marker 失败也得到 `True`
   - L2764-2771: 返回 `_AwaitingAcceptExecution(duplicate_terminal_recorded=True, durable_missing_reason=None)`

3. `_execute_one`（`tool_runtime.py:2391-2398, 2453-2458`）：
   - L2391-2393: `duplicate_terminal_recorded = awaiting_result.duplicate_terminal_recorded` → `True`
   - L2394-2397: `durable_missing_reason` 条件赋值为 None 时保持默认值，但此变量不再使用
   - L2454: `duplicate_owner_needs_terminal and not duplicate_terminal_recorded` → `True and not True` → `False`
   - finally cleanup 被抑制 ✅

**异常类型边界检查**：

- `except Exception` 捕获所有标准 Python 异常（`RuntimeError`, `ValueError`, `AssertionError` 等）
- `asyncio.CancelledError`（`BaseException` 子类）**不被捕获**，会正常传播
- 此设计正确：`CancelledError` 是任务生命周期事件，不是 marker 写入失败；传播后 `finally` 执行 `record_durable_missing(GOVERNED_BEFORE_ACCEPT)` 是取消路径的合理 cleanup（Host durable truth 已成立，attempt-local 清理后 waiter 可重竞争）

**Finally 变量语义完整走读**：

| 场景 | `duplicate_terminal_recorded` | `durable_missing_reason` | finally 行为 | 判定 |
|---|---|---|---|---|
| Accepted ack + marker 成功 | `True` | `None`（不更新，保持默认） | 抑制 | ✅ |
| Accepted ack + marker 失败（Exception） | `True` | `None`（不更新，保持默认） | 抑制 | ✅ |
| Accepted ack + marker 被 CancelledError 中断 | `False`（未到达赋值行） | `GOVERNED_BEFORE_ACCEPT` | 执行 cleanup | ✅ 合理 |
| Rejected ack | `False` | `HOST_ACCEPT_REJECTED`（L2394 更新） | 执行 cleanup | ✅ |
| Timeout ack | `False` | `HOST_ACCEPT_TIMEOUT`（L2394 更新） | 执行 cleanup | ✅ |
| `_accept_awaiting` 整体抛异常 | `False`（未到达赋值行） | `GOVERNED_BEFORE_ACCEPT` | 执行 cleanup | ✅ 保守正确 |

**Monkeypatch 测试可信度**：

测试 `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup`（`test_toolruntime_executor.py`）：
- 用 `monkeypatch.setattr` 替换 `record_awaiting_accepted` 为同步 `raise RuntimeError`
- 这正确触发了 `_record_duplicate_awaiting_accepted` 中的 `except Exception` 分支
- Monkeypatch 替换的是被调用方（`record_awaiting_accepted`），调用方（`_record_duplicate_awaiting_accepted`）的 try/except 逻辑完整执行
- 断言链完整覆盖：owner outcome 仍为 `ToolAwaitingOutcome`、`recorded_reasons == []`、diagnostic reason_code 正确、wait_id 未泄漏到 diagnostic message
- 不掩盖 fix 逻辑；fix 的 try/except 是测试的直接被测路径

### DS-F03: `record_durable_missing` 的 `AWAITING_ACCEPTED` guard 直接单元测试 ✅ 已关闭

**新增测试**：`test_durable_missing_preserves_awaiting_accepted_marker`（`test_toolruntime_duplicate_governance.py`）

**走读验证**：

1. owner `decide_duplicate` → `ALLOW`
2. `record_awaiting_accepted(entry)` → in-flight state = `AWAITING_ACCEPTED`
3. `record_durable_missing(reason=GOVERNED_BEFORE_ACCEPT)` → 触发 guard（`tool_duplicate_governance.py:561-564`）
4. 后续 `decide_duplicate` → `AWAITING_FANOUT`（非 `ALLOW`，未重新竞争 owner）

**Guard 代码路径（`tool_duplicate_governance.py:557-567`）**：
```python
in_flight = self._state.in_flight_by_key.pop(duplicate_key, None)
if in_flight is not None:
    if in_flight.state is _InFlightDuplicateState.AWAITING_ACCEPTED:
        self._state.in_flight_by_key[duplicate_key] = in_flight  # put back
        self._state.condition.notify_all()
        return  # 不覆盖
```

测试覆盖了 pop → 检查 → put back → return 的完整 guard 路径。断言 `decision.kind is AWAITING_FANOUT`、`decision.prior_wait_id == "wait-owner"`、`decision.prior_awaiting_outcome is awaiting_outcome`、`decision.prior_outcome is None` 验证了 owner wait 信息完整保留。

**辅助断言**（同一测试文件中其他测试）：
- `test_record_awaiting_accepted_marks_terminal_without_ordinary_reuse`：验证 `prior_outcome=None` 互斥
- `test_record_awaiting_accepted_fans_out_multiple_waiters`：验证多 waiter 均 fanout
- `test_durable_missing_still_reopens_owner_competition`：验证 `OWNER_RUNNING` → `DURABLE_MISSING` 后 waiter 正常重竞争（非 `AWAITING_ACCEPTED` guard 覆盖场景）

### DS-F02: 诊断 ref 丢弃 ✅ Deferred 保持

- `_awaiting_fanout_record`（`tool_runtime.py:2784-2800`）仍不接收、不存储、不投影 `duplicate_refs`
- 无 record schema、public diagnostics、durable design 扩展
- 按 controller 裁决 `deferred`，fix 未处理 ✅

---

## Fix 边界检查

| 边界约束 | 状态 | 证据 |
|---|---|---|
| 未修改 `engine_ingest.py` | ✅ | `git diff --name-only` 无该文件 |
| 未修改 durable schema/state | ✅ | `git diff --name-only` 无 `dayu/host/durable/` |
| 未修改 public API/contracts | ✅ | `git diff --name-only` 无 `dayu/contracts/` |
| 未修改 wait adapter activation contract | ✅ | 无相关文件变更 |
| 未实现 issue-129 two-phase activation | ✅ | 无相关代码 |
| 未新增 heavy follower ledger 或 wait alias schema | ✅ | 无新增 durable table/column/state |
| 未新增 public await lifecycle contract | ✅ | 无 public contract 变更 |
| Fix 仅触及 controller 允许的生产文件 | ✅ | 仅 `dayu/host/tool_runtime.py` |
| Fix 仅触及 controller 允许的测试文件 | ✅ | `tests/host/test_toolruntime_executor.py`、`tests/host/test_toolruntime_duplicate_governance.py` |

---

## 诊断质量检查

### `_emit_duplicate_awaiting_marker_diagnostic_best_effort`（`tool_runtime.py:3005-3037`）

- diagnostic message 格式：`"duplicate awaiting accepted marker failed: {exc.__class__.__name__}"`
- 不包含 `wait_id`、`tool_call_id`、EventLog ref 或任何 Host 内部标识符
- `wait_id` 参数仅用于 diagnostic 本身失败时的 fallback logging（L3029-3037），不进入 Tool Trace
- 测试断言：`assert awaiting_accept_port.candidates[0].wait_id not in diagnostics.records[0].message` ✅
- reason_code：`"duplicate_awaiting_marker_failed"` — 业务可读，不暴露内部模块名
- 遵循现有 `_emit_duplicate_cleanup_diagnostic_best_effort` 的 best-effort 诊断模式

---

## Validation Checked

| 验证项 | 结果 | 命令/证据 |
|---|---|---|
| Focused pytest | **184 passed in 1.29s** | `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q` |
| pyright | **0 errors, 0 warnings, 0 informations** | `pyright` |
| engine_ingest.py 未修改 | ✅ | `git diff --name-only` 不含该文件 |
| durable schema/state 未修改 | ✅ | `git diff --name-only` 不含 `dayu/host/durable/` |
| public contracts 未修改 | ✅ | `git diff --name-only` 不含 `dayu/contracts/` |

---

## Unfixed Accepted Findings

0 unfixed accepted findings。

---

## New Blocking Findings

0 new blocking findings。

---

## Open Questions

1. `_emit_duplicate_awaiting_marker_diagnostic_best_effort` 的 `wait_id` 参数仅在 diagnostic 自身失败时才写入 fallback log。当前 fallback log 包含 `wait_id`，但其接收方为运维日志系统（非 LLM/Tool Trace），按计划 LLM-facing 约束不涵盖运维日志。是否需要明确此边界？
2. `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` 使用同步 `raise RuntimeError` 模拟异步 `record_awaiting_accepted` 失败。当前测试正确触发了 `except Exception` 路径；若未来 `record_awaiting_accepted` 的失败模式变为仅在 condition lock 内抛特定异常，可能需要补充 condition-context 异常测试。当前 fix 的 `except Exception` 宽捕获对此类场景已有防御。

---

## Residual Risks

| Risk | Severity | Status | 说明 |
|---|---|---|---|
| `asyncio.CancelledError` 在 marker 写入 await 点传播 | Low | Accepted residual | CancelledError 是任务生命周期事件，传播后 finally 执行 `GOVERNED_BEFORE_ACCEPT` cleanup 是正确行为。Host durable truth（wait record, Run WAITING）已在此之前成立。 |
| Monkeypatch 测试用同步 raise 模拟异步异常 | Low | Informational | 当前测试覆盖了 `except Exception` 路径，condition-context 异常由宽捕获覆盖。若需更精确模拟可后续补充。 |
| `AWAITING_FANOUT` 仍为防御性内部状态，batch 截断后不触发 | Low | Deferred | 按 controller 裁决保持，同 DS-F02 状态。 |
| `durable_missing_reason` 默认值 `GOVERNED_BEFORE_ACCEPT` 在 `_accept_awaiting` 整体异常时语义略宽 | Low | Pre-existing | 非 fix 引入，为保守默认值；`_accept_awaiting` 整体异常意味着 Host accept barrier 失败，此默认值合理。 |
| Diagnostic reason_code 新增 `duplicate_awaiting_marker_failed` 可能被下游 Tool Trace 消费方依赖 | Low | Informational | reason_code 遵循现有命名约定，不包含内部实现细节。 |
