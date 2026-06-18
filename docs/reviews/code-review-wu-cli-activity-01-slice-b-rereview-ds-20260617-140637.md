# WU-CLI-ACTIVITY-01 Slice B 修复后复审

## Scope

- Mode: current changes (unstaged diff)
- Branch: wu-cli-activity-01
- Base: main
- Review focus: Service activity callback — 已接受 DS F-1 / F-3 修复验证；F-2 裁决延期，不作为阻断
- Output file: docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-ds-20260617-140637.md
- Included scope:
  - dayu/service/entrypoint_runtime.py (unstaged diff)
  - tests/service/test_entrypoint_runtime.py (unstaged diff)
- Excluded scope:
  - docs/host/issues-implementation-control.md（仅控制文档状态更新，非本次 review 对象）
  - cancel_entrypoint_run_and_wait on_activity（F-2，已裁决延期到 Slice E）
- Source adjudication: docs/reviews/code-review-wu-cli-activity-01-slice-b-adjudication-20260617-135835.md
- Fix artifact: docs/reviews/wu-cli-activity-01-slice-b-fix-codex.md

## Findings

### DS F-1：非终态 dedupe key 抑制终态 — 已修复

- **入口/函数**: `_terminal_result_from_live_event`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:1008-1034`
- **输入场景**: 非终态 progress/activity 事件（`terminal_status is None`）与后续终态事件使用相同 `dedupe_key`
- **实际分支**: 修复后，`if event.terminal_status is None: return None`（行 1012-1013）在 dedupe 状态变更前执行 early return
- **预期行为**: 非终态事件不应污染 `seen_dedupe_keys` / `seen_event_ids`，后续终态事件应正常返回
- **实际行为**: 非终态事件提前返回 `None`，不写入 `seen_dedupe_keys`、`seen_event_ids`、`seen_terminal_event_ids`；后续终态事件可正常通过 dedupe 检查
- **直接证据**:
  - 行 1012-1013: `if event.terminal_status is None: return None` 在所有 dedupe 状态写入之前执行
  - 行 1014-1019: dedupe 检查与 `seen_dedupe_keys` 写入仅在 `terminal_status is not None` 时执行
  - 行 1011: `last_observed_event_sequence` 仍在 early return 之前更新，非终态事件的 sequence tracking 不受影响
- **Activity 侧隔离**: `_emit_entrypoint_activity_from_host_event`（行 793-817）使用独立的 `state.seen_activity_dedupe_keys` 做 activity 去重，与 `_terminal_result_from_live_event` 的 `seen_dedupe_keys` 完全分离
- **测试覆盖**:
  - `test_submit_entrypoint_turn_non_terminal_dedupe_key_does_not_hide_terminal`（行 633-666）：共享 dedupe key 的非终态+终态事件序列，验证终态正常返回
  - `test_submit_entrypoint_turn_deduplicates_activity_by_dedupe_key`（行 597-630）：验证 activity 自身去重仍生效
- **影响**: 已消除 — 非终态 event 不再能抑制终态 terminal
- **严重程度**: 无（已修复）

### DS F-3：activity callback 异常传播测试 — 已修复

- **入口/函数**: `test_submit_entrypoint_turn_activity_callback_exception_propagates`
- **文件(行号)**: `tests/service/test_entrypoint_runtime.py:669-706`
- **输入场景**: `on_activity` callback 抛出 `RuntimeError`
- **实际分支**: callback 异常从 `_emit_entrypoint_activity_from_host_event` → `_drain_available_watcher_items` → `_wait_for_terminal` → `submit_entrypoint_turn_and_wait` 自然透传，不被任何 try/except 吞掉
- **预期行为**: 异常向调用方传播，且 watcher 资源在 `finally` 块中正确关闭
- **实际行为**: `pytest.raises(RuntimeError)` 捕获到 callback 异常；`fake_host.watchers[0].closed_count == 1` 确认 watcher 已关闭
- **直接证据**:
  - 行 817: `on_activity(_entrypoint_activity_from_host_event(event))` 无 try/except 包裹
  - 行 575-576: `submit_entrypoint_turn_and_wait` 的 `finally` 块执行 `await _close_watcher(...)`
  - 行 697-706: 测试用 `pytest.raises` 断言异常传播 + 断言 watcher 关闭
- **影响**: 已消除 — callback 异常传播行为有测试覆盖且行为合理
- **严重程度**: 无（已修复）

### 非阻断：`_drain_available_watcher_items` docstring 与行为不一致

- **入口/函数**: `_drain_available_watcher_items`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:762`
- **输入场景**: callback 抛异常时，函数会向上透传异常
- **实际分支**: docstring 写 `:raises Exception: 不主动抛出异常。`，但 callback 异常可透传
- **预期行为**: docstring 应说明 callback 异常会透传
- **实际行为**: docstring 声明"不主动抛出异常"，技术上正确（函数自身不 raise），但可能误导读者认为所有异常路径都被内部吸收
- **直接证据**: 行 762 的 docstring；行 785-790 的 callback 调用无 try/except
- **影响**: 仅文档可读性，不影响运行时行为
- **建议改法和验证点**: 将 docstring 改为 `:raises Exception: 不主动抛出异常；callback 异常会向调用方透传。` 或类似表述
- **修复风险**: 无（仅文档修改）
- **严重程度**: 低

## Open Questions

无。

## Residual Risk

- `cancel_entrypoint_run_and_wait` 的 `on_activity` 回调已裁决延期到 Slice E，当前 cancel 路径无 activity 通知 — 这是已知的已裁决延期，不是新风险。
- CLI renderer/composer 尚未接入 activity callback，`EntrypointActivity` 及相关 enum/dataclass 的端到端验证需等到 Slice C/D 完成。
- 新增 activity 相关 enum (`EntrypointActivityKind`, `EntrypointActivityStatus`, `EntrypointActivitySeverity`) 与 `EntrypointActivity` dataclass 的序列化/反序列化未测试；若未来需要跨进程传递需补充。

## 验证结果

- `pytest tests/service/test_entrypoint_runtime.py -q`: 26 passed, 3 warnings（第三方 edgar deprecation）
- `pyright dayu/service/entrypoint_runtime.py tests/service/test_entrypoint_runtime.py`: 0 errors, 0 warnings, 0 informations

## 复审结论

**非阻断**。DS F-1 和 DS F-3 均已正确修复，有直接证据和测试覆盖。F-2 按裁决延期到 Slice E，不作为本次阻断。`_drain_available_watcher_items` docstring 存在轻微不一致，不影响 correctness，建议在后续修改中顺手修正。
