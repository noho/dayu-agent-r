# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-mimo-20260617-140637.md`
- Included scope: `dayu/service/entrypoint_runtime.py`、`tests/service/test_entrypoint_runtime.py` 的未提交改动
- Excluded scope: F-2 `cancel_entrypoint_run_and_wait` `on_activity` 已裁决延期至 Slice E，不在本次复审范围
- Parallel review coverage: 无

## 复审任务

复审 WU-CLI-ACTIVITY-01 Slice B 修复后的当前未提交改动。聚焦两项已接受 finding：

1. **F-1**: 非终态 HostEvent 的 dedupe key 不得抑制后续终态 HostEvent
2. **F-3**: callback exception propagation 测试与行为合理性

## Findings

未发现实质性问题。

### F-1 修复验证：非终态 dedupe key 不再抑制终态

**修复位置**: `dayu/service/entrypoint_runtime.py:1012-1019`（`_terminal_result_from_live_event`）

**修复前行为（旧代码）**：

```python
duplicate = event.event_id in state.seen_event_ids or event.dedupe_key in state.seen_dedupe_keys
state.seen_event_ids.add(event.event_id)
if event.terminal_status is not None:
    state.seen_terminal_event_ids.add(event.event_id)
if duplicate:
    return None
state.seen_dedupe_keys.add(event.dedupe_key)
```

非终态事件（`terminal_status is None`）到达时，`state.seen_dedupe_keys.add(event.dedupe_key)` 会在函数末尾执行。若后续终态事件携带相同 dedupe key，`duplicate` 判断为 `True`，终态被错误抑制。

**修复后行为（新代码）**：

```python
if event.terminal_status is None:
    return None
duplicate = event.event_id in state.seen_event_ids or event.dedupe_key in state.seen_dedupe_keys
state.seen_event_ids.add(event.event_id)
state.seen_terminal_event_ids.add(event.event_id)
if duplicate:
    return None
state.seen_dedupe_keys.add(event.dedupe_key)
```

关键改动：**early return for non-terminal**（行 1012-1013）。非终态事件在任何去重逻辑之前返回 `None`，不会向 `seen_dedupe_keys` 或 `seen_event_ids` 写入任何内容。

**Activity 投影路径独立化**：新增 `seen_activity_dedupe_keys`（行 391）专用于 activity 去重，与 terminal dedupe 完全隔离。`_emit_entrypoint_activity_from_host_event` 使用独立的 `seen_activity_dedupe_keys`，不触碰 terminal 去重集合。

**证据链**：
- `state.seen_dedupe_keys` 现在只被 `_terminal_result_from_live_event` 写入（行 1019），而该函数已通过 early return 过滤掉所有非终态事件
- `_emit_entrypoint_activity_from_host_event`（行 808-809）使用 `state.seen_activity_dedupe_keys`，与 `seen_dedupe_keys` 无交集
- `_WatcherFailure` activity 使用常量 dedupe key `entrypoint_watcher_failure`（行 65），同样只写入 `seen_activity_dedupe_keys`

**测试覆盖**: `test_submit_entrypoint_turn_non_terminal_dedupe_key_does_not_hide_terminal`（行 586-615）精确构造了非终态与终态共用 dedupe key 的场景，断言终态仍被正确返回。

**结论**: F-1 修复正确。terminal 去重与 activity 去重完全隔离，非终态事件不再污染 terminal dedupe 路径。

### F-3 修复验证：callback exception propagation 测试与行为合理性

**测试**: `test_submit_entrypoint_turn_activity_callback_exception_propagates`（行 618-649）

**行为走读**：

1. `_FakeHost` 推入 activity event（seq=2）和 terminal event（seq=3）
2. `_drain_available_watcher_items` 先处理 activity event
3. `_terminal_result_from_live_event` 返回 `None`（非终态）
4. `_emit_entrypoint_activity_from_host_event` 调用 `on_activity(raise_from_activity)`
5. `raise_from_activity` 抛出 `RuntimeError("activity callback failed: activity-callback-error")`
6. 异常无 try/except 包裹，直接沿 `_drain_available_watcher_items` → `_wait_for_terminal` → `submit_entrypoint_turn_and_wait` 传播
7. `submit_entrypoint_turn_and_wait` 的 `finally` 块（行 575-576）确保 `_close_watcher` 被调用
8. `_FakeHostEventIterator.aclose()` 递增 `closed_count`

**异常传播路径确认**：
- `_emit_entrypoint_activity_from_host_event`（行 814）：`on_activity(...)` 无 try/except 保护，异常直接传播
- `_drain_available_watcher_items`（行 785-790）：`_emit_entrypoint_activity_from_host_event` 调用不在 try/except 内
- `_wait_for_terminal`（行 728-730）：`_drain_available_watcher_items` 调用不在 try/except 内
- `submit_entrypoint_turn_and_wait`（行 575-576）：`finally: await _close_watcher(watcher=watcher, drain_task=drain_task)` 保证资源释放

**测试断言**：
- `pytest.raises(RuntimeError, match="activity callback failed: activity-callback-error")` — 验证异常精确传播
- `assert fake_host.watchers[0].closed_count == 1` — 验证 watcher 资源正确释放

**结论**: F-3 测试覆盖合理。异常传播路径清晰，无吞没风险；`finally` 块保证资源释放；测试同时验证了异常内容和 watcher cleanup。

### F-2 延期确认

`cancel_entrypoint_run_and_wait` 的 `on_activity` 参数集成已裁决延期至 Slice E，本次不阻断。

## Open Questions

- 无。

## Residual Risk

- `_emit_entrypoint_activity_from_host_event` 和 `_emit_watcher_failure_activity` 均直接透传 callback 异常。若未来 UI adapter 的 callback 实现不够健壮（如未捕获外部渲染库异常），可能导致整个 terminal 等待中断。当前设计是正确的——不应吞没 caller 的异常——但上层集成时需确保 callback 异常处理策略明确。
- `_close_watcher` 若 `aclose()` 也抛异常，原始 activity callback 异常会被 watcher close 异常覆盖（Python `finally` 行为）。当前测试未覆盖此组合场景。风险低，因为 `_FakeHostEventIterator.aclose()` 默认不抛异常，且真实 Host watcher 的 close 异常应极罕见。

## 结论

**非阻断**。F-1 和 F-3 两项已接受 finding 的修复均正确、测试充分、行为合理。
