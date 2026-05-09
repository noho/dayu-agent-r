# P8-S4 Fix Re-Review

- **Review gate**: P8-S4 code re-review
- **Reviewed target**: 当前未提交 diff（F1/F2 accepted findings 修复）
- **原 code review artifact**: `docs/host/phase8-s4-code-review.md`
- **复审范围**: F1 duplicate terminal event type -> AttemptState mapping; F2 `_append_terminal_and_close` extra DB round-trip

## Conclusion

**通过 (PASSED)**

F1 和 F2 修复均到位，符合 code review 建议和 controller decision。修复未引入新 blocker。review artifact 中 F1/F2 的 controller decision 标注已更新为 `accepted — 已修复`；checklist 第 10 项的过期 "待 controller decision" 表述已清理。

## F1 复审：duplicate terminal event type -> AttemptState mapping

**结论: fixed**

逐项验证：

1. **`_attempt_state_mapping.py` 是 single source of truth** — 确认。`attempt_state_from_terminal_event_type` 定义在 [_attempt_state_mapping.py:22-53](dayu/host/_attempt_state_mapping.py#L22-L53)，包含完整 match 分支（FINAL_ANSWER -> SUCCEEDED, RUN_FAILED -> FAILED, RUN_CANCELLED -> CANCELLED, RUN_SUSPENDED -> SUSPENDED），非 terminal 入参抛 `ValueError`。

2. **`_attempt_supervisor.py` 与 `_run_harness.py` 不再各自保留重复 match 分支** — 确认。`_attempt_supervisor.py:61` 和 `_run_harness.py:39` 均 `from dayu.host._attempt_state_mapping import attempt_state_from_terminal_event_type`。两文件中不再存在 `match event_type` / `match draft.type` / `case RunEventType.FINAL_ANSWER` 等独立 match 分支。

3. **无循环依赖** — 确认。`_attempt_state_mapping.py` 只 import `_internal_contracts.AttemptState` 和 `contracts.RunEventType`，均为更低层模块；不 import `_attempt_supervisor` 或 `_run_harness`。

4. **helper 未放入 `dayu.runtime`** — 确认。模块位于 `dayu/host/_attempt_state_mapping.py`，模块 docstring 明确写 "属于 Host attempt 语义, 不进入 `dayu.runtime` 公共运行时基础设施"。

5. **未改变 public API** — 确认。模块不在 `dayu/host/__init__.py` 的 public exports 中，`__all__` 仅控制模块级导出。

6. **中文 docstring** — 确认。模块有完整中文概览 docstring（10 行），函数有完整中文 docstring 含参数、返回值、异常说明。

## F2 复审：`_append_terminal_and_close` extra DB round-trip

**结论: fixed**

逐项验证：

1. **`AttemptTerminalLink` 携带 `RunEvent`** — 确认。[_attempt_lease.py:312-335](dayu/host/_attempt_lease.py#L312-L335) 定义 `AttemptTerminalLink` dataclass，包含 `event: RunEvent` 字段，docstring 说明 "本类型同时承载事务内 append 出的 terminal RunEvent 实例, 供调用方在事务提交后无需再次访问 EventLog 即可拿到完整事件"。

2. **`AttemptSupervisor.append_terminal_and_close(...)` 在事务内直接返回 append 得到的 RunEvent** — 确认。[_attempt_supervisor.py:475-484](dayu/host/_attempt_supervisor.py#L475-L484) 构造 `AttemptTerminalLink` 时传入 `event=appended.event`，其中 `appended` 来自同事务内 `append_with_position_in_transaction` 的返回值。

3. **`LocalRunHarness._append_terminal_and_close(...)` 直接 `return link.event`** — 确认。[_run_harness.py:1597](dayu/host/_run_harness.py#L1597) `return link.event`，注释明确写 "不再做事务提交后的 list_events round-trip, 也不依赖 'append 后立即可查' 的隐含不变量"。

4. **事务提交后的 `event_store.list_events(...)` 查询和 `atomic close invariant broken` 兜底分支已删除** — 确认。`_append_terminal_and_close` 方法（1526-1597 行）内无 `list_events` 调用，无 "atomic close invariant broken" 字符串。

5. **terminal_event_position / event_cursor / event_position 语义未变** — 确认。`AttemptTerminalLink` 仍包含 `event_cursor: RunEventCursor` 和 `event_position: GlobalEventPosition`，与原设计一致；新增的 `event: RunEvent` 是纯增量字段，不改变既有语义。

## Review Artifact 状态

1. **F1 controller decision** — 已标 `accepted` + `已修复`（第 39 行）。
2. **F2 controller decision** — 已标 `accepted` + `已修复`（第 53 行）。
3. **F3** — `deferred-with-owner — P16 / issue #28`（第 67 行）。
4. **F4** — `rejected-with-reason`（第 81 行）。
5. **过期表述** — checklist 第 10 项已改为 "F1（duplicate mapping）和 F2（extra DB round-trip）已修复并经 re-review 通过（见 `docs/host/phase8-s4-fix-rereview.md`）。F3（`_sessions` 访问）deferred 到后续 slice。"，确认不再残留 "待 controller decision"。

## 新 Blocker 检查

**未发现新 blocker。**

- 类型错误：pyright 0 errors, 0 warnings。
- 循环依赖：`_attempt_state_mapping.py` 仅依赖更低层 `_internal_contracts` 和 `contracts`，无环。
- public contract 漂移：`AttemptTerminalLink` 新增 `event` 字段为 frozen dataclass 增量扩展，不破坏现有消费方（现有代码只读 `event_cursor` / `event_position`，不因新增字段而报错）。
- 提前实现 P8-S5/S6/S7：diff 中无 ToolRuntime attempt-scoped append、recovery scan、multiprocessing 相关代码。

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py -q` | 15 passed |
| `python -m pyright dayu/host/_attempt_state_mapping.py dayu/host/_attempt_supervisor.py dayu/host/_run_harness.py dayu/host/_attempt_lease.py` | 0 errors, 0 warnings |

## Re-Review 清理要求

- [x] 更新 `docs/host/phase8-s4-code-review.md` 第 123 行，将 "待 controller decision" 改为 "已修复" 或等价准确表述。

## Residual Risks 与 Owner

| 风险 | 分类 | Owner |
|------|------|-------|
| F3: test `_sessions` access | deferred-with-owner | P16 / issue #28 |
| P8-S5 ToolRuntime attempt-scoped CAS append | 未实现 | P8-S5 |
| P8-S6 recovery scan | 未实现 | P8-S6 |
| P8-S7 multiprocessing | 未实现 | P8-S7 |
