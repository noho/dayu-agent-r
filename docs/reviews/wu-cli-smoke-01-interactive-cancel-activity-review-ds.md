# Code Review — interactive cancel/activity 修复 (AgentDS)

## Scope

- Mode: current changes（未提交 diff review）
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-interactive-cancel-activity-review-ds.md`
- Included scope: 8 files, 134 insertions, 29 deletions
- Excluded scope: 无（全量走读）
- Parallel review coverage: 无（单 reviewer 逐链路走读）

### Changed files

| File | Change |
|------|--------|
| `dayu/cli/output.py` | cancel_reason 用户可见文案映射 |
| `dayu/cli/run_view.py` | terminal result 后 mode 重置到 default_mode |
| `dayu/host/durable/run_transition.py` | WaitingRunTerminalInput 新增 message 字段；RUN_FAILED/RUN_LOST payload 条件写入 |
| `dayu/host/read_api.py` | ATTEMPT_STARTED、RUN_WAITING 移出 activity projection allowlist |
| `dayu/host/waiting.py` | _resolve_failed/_resolve_lost 新增 type guard + message 填充 |
| `tests/cli/test_interactive_run_view.py` | 新增 default_mode 保持测试；重命名旧测试 |
| `tests/host/test_host_activity_event_projection.py` | ATTEMPT_STARTED 断言 activity=None；RUN_WAITING 断言 activity=None |
| `tests/host/test_resolve_wait_command.py` | RUN_FAILED/RUN_LOST payload 断言 message 字段 |

## 按检查点逐项验证

### 1. Public projection 边界

**ATTEMPT_STARTED 移出 activity projection（`read_api.py:1078-1086`）**

- 旧行为：ATTEMPT_STARTED 与 RUN_STARTED 共用 `_run_lifecycle_activity`，投影 "运行已开始" / IN_PROGRESS → **重复 activity**。
- 新行为：ATTEMPT_STARTED 不再进入 `_activity_from_row` 任何 allowlist 分支，返回 `None`。
- ATTEMPT_STARTED 是 internal governance event（记录 attempt 生命周期），不是用户可见事实。RUN_STARTED 已经投影了同一语义。
- 验证：`test_non_terminal_run_lifecycle_activity_projection` 新增 `attempt_started.activity is None` 断言。✓

**RUN_WAITING 移出 activity projection（`read_api.py:1091`）**

- 旧行为：RUN_WAITING 投影 "等待工具完成"（无 tool_name，无 tool_display_name）→ 与 TOOL_AWAITING 投影重复（TOOL_AWAITING 带 tool name）。
- 新行为：只有 TOOL_AWAITING 投影 tool_awaiting activity。
- 证据：`waiting.py:1741`（TOOL_AWAITING）与 `waiting.py:1795`（RUN_WAITING）在同一 transaction 中成对发射；`engine_ingest.py:3448-3453` 也是成对读取。不存在 RUN_WAITING 独立发射的路径。
- 验证：`test_tool_awaiting_projects_activity_and_run_waiting_stays_silent` 断言 `run_waiting.activity is None`。✓

**结论：public projection 边界正确，无信息丢失。每个用户可见事实仍有唯一 activity 来源。**

### 2. Host canonical EventLog 不被破坏

**RUN_FAILED / RUN_LOST payload 新增 `message` 字段（`run_transition.py:3803-3813`）**

- `_waiting_run_terminal_event_request` 在 payload 中条件写入 `"message"` 键（仅当 `request.message is not None`）。
- payload 存量字段（`run_id`、`attempt_id`、`wait_id`、`terminal_status`、`reason`、`tool_result_event_ref`）保持不变。
- `_validate_waiting_terminal_input` 新增 `_require_optional_non_empty_text(request.message, field_name="message")` — `None` 通过，非空字符串校验非空白。
- EventLog 是 append-only，存量事件不受影响。新事件 payload 多一个 key，旧 reader 忽略未知 key 不报错。

**现有 read_api 已经读取 `message` 字段**：

- `_failed_host_event`（`read_api.py:973-975`）：`error_message = _optional_payload_text(payload, field_name=_PAYLOAD_FIELD_MESSAGE, row=row)` — 其中 `_PAYLOAD_FIELD_MESSAGE = "message"`。
- `_lost_host_event`（`read_api.py:1058-1060`）：同上。
- 旧行为：payload 中无 `message` key → `_optional_payload_text` 返回 `None` → `error_message=None` → CLI fallback 到 `_FAILED_FALLBACK_MESSAGE` / `_LOST_FALLBACK_MESSAGE`。
- 新行为：payload 中有 `message` key → `error_message` 有值 → CLI 显示真实错误信息。

**结论：EventLog schema 向后兼容，只增不减。read_api 已有消费路径，无需新增 reader。**

### 3. RUN_FAILED/RUN_LOST payload message 符合 read_api terminal policy

**read_api terminal policy**（`_failed_host_event` / `_lost_host_event`）：

- `error_message` 从 payload `"message"` 字段读取（`_optional_payload_text`）。
- `HostEvent.error_message` → `EntrypointRunTerminalResult.error_message` → CLI `render_*_terminal_result` 打印到 stderr。

**message 来源**：

- **FAILED**：`_failed_wait_terminal_message(outcome)` → `outcome.result.message` + 可选 `outcome.result.hint`（来自 `ToolResultFailure.message: str` + `ToolResultFailure.hint: str | None`，均在 `__post_init__` 中 validated non-empty）。
- **LOST**：`outcome.message`（来自 `ResolveWaitLostOutcome.message: str`，`__post_init__` 中 validated non-empty）。

**CLI 展示**（`output.py:101-104`）：

- `render_prompt_terminal_result`：LOST → `result.error_message or _LOST_FALLBACK_MESSAGE`；FAILED → `result.error_message or _FAILED_FALLBACK_MESSAGE`。
- `render_interactive_terminal_result`：同上顺序。

**结论：message 从 tool/lost outcome → EventLog payload → read_api error_message → CLI stderr 的链路完整、自洽，符合 read_api terminal policy。**

### 4. CLI cancel reason 映射仅影响用户输出

**`_public_cancel_message`（`output.py:144-153`）**：

```python
def _public_cancel_message(cancel_reason: str | None) -> str:
    if cancel_reason == CLI_SIGINT_REASON:   # "cli_sigint" == "cli_sigint"
        return _USER_CANCELLED_MESSAGE        # "Cancelled."
    return cancel_reason or _CANCELLED_FALLBACK_MESSAGE
```

**数据流**：

1. CLI cancel 路径（`prompt.py:578` / `interactive.py:832`）：`reason=CLI_SIGINT_REASON` → `"cli_sigint"`
2. Host `cancel_run` → RUN_CANCELLED EventLog payload `"reason": "cli_sigint"`
3. `_cancelled_host_event`（`read_api.py:1029-1031`）：`cancel_reason=_optional_payload_text(payload, field_name="reason", ...)` → `"cli_sigint"`
4. `EntrypointRunTerminalResult.cancel_reason` = `"cli_sigint"`
5. `_public_cancel_message("cli_sigint")` → `"Cancelled."`

**不影响的层**：
- `EntrypointRunTerminalResult.cancel_reason` 仍保留原始值 `"cli_sigint"`（不做变换）
- Host EventLog 仍写入原始 `reason`（不受 CLI 文案影响）
- Host durable state 完全不受 CLI presentation 层影响

**非 SIGINT 取消**：`cancel_reason` 不是 `"cli_sigint"` → 走 `cancel_reason or _CANCELLED_FALLBACK_MESSAGE` → 行为与旧代码相同。

**结论：CLI cancel reason 映射是纯 presentation 层变换，不向上游泄漏。Host canonical state 与 EventLog 不受影响。**

### 5. Interactive run view mode reset 符合 prompt/interactive 对齐

**`render_terminal_result`（`run_view.py:323`）**：

```python
# 旧：self._mode = InteractiveRunViewMode.TRANSCRIPT  （硬编码）
# 新：self._mode = self._default_mode                   （使用配置默认值）
```

**行为变化**：

| initial_mode | 旧行为（terminal 后） | 新行为（terminal 后） |
|-------------|---------------------|---------------------|
| 未指定（默认 TRANSCRIPT） | TRANSCRIPT | TRANSCRIPT（不变） |
| ACTIVITY | TRANSCRIPT（**静默降级**） | ACTIVITY（**保持**） |
| TRANSCRIPT（显式） | TRANSCRIPT | TRANSCRIPT（不变） |

**prompt/interactive 对齐**：

- prompt 模式：单次 run，terminal 后进程退出 → mode reset 不适用。
- interactive 模式：多轮交互，每轮 terminal 后应回到用户配置的初始 mode。旧代码始终重置到 TRANSCRIPT，违背用户显式选择 ACTIVITY 的意图。

**测试覆盖**：
- `test_run_view_activity_mode_outputs_terminal_and_returns_to_default_mode`：默认 TRANSCRIPT → terminal 后 TRANSCRIPT。✓
- `test_run_view_detail_mode_keeps_activity_after_terminal_result`：ACTIVITY → terminal 后 ACTIVITY。✓

**toggle_view 不受影响**：toggle 是二元翻转（TRANSCRIPT ↔ ACTIVITY），与 `_default_mode` 独立。

**结论：mode reset 行为正确，新行为符合 "尊重用户配置" 的交互原则。测试覆盖两种路径。**

## Findings

未发现实质性问题。

逐检查点结论：

| # | 检查点 | 结论 |
|---|--------|------|
| 1 | public projection 边界 | ATTEMPT_STARTED 和 RUN_WAITING 移除正确，消除重复，无信息丢失 |
| 2 | Host canonical EventLog | payload 只增不减，存量字段不变，向后兼容 |
| 3 | RUN_FAILED/RUN_LOST message vs read_api terminal policy | message → payload → error_message → CLI 链路完整，符合 policy |
| 4 | CLI cancel reason 映射影响范围 | 纯 presentation 层；内部状态/EventLog 不受影响 |
| 5 | interactive run view mode reset | 正确重置到 default_mode；prompt/interactive 对齐 |
| — | schema change | WaitingRunTerminalInput.message 两个 call site 均已更新，无遗漏 |
| — | 测试覆盖 | 36 passed, 3 处行为变更均有对应测试 |
| — | pyright | 0 errors, 0 warnings, 0 informations |
| — | README | 不触发更新（无 CLI 入口/workflow/架构边界变化） |

## Open Questions

无。

## Residual Risk

- **非 `_resolve_failed`/`_resolve_lost` 路径的 RUN_FAILED/RUN_LOST event 不含 `message`**：如 Engine 直接返回 failure/lost（非 wait resolution 路径）的 terminal event 不受本轮修改影响，其 payload 中无 `message` 字段。`_failed_host_event` / `_lost_host_event` 已通过 `_optional_payload_text` 容错处理（返回 None → fallback 到通用消息）。classified as accepted — 这些路径可后续独立增强。
- **`_public_cancel_message` 无独立单元测试**：函数仅 2 分支，被 `render_prompt_terminal_result` 和 `render_interactive_terminal_result` 间接覆盖。classified as accepted — 集成路径已覆盖主分支。
- **`_failed_wait_terminal_message` 无独立单元测试**：被 `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 通过 RUN_FAILED payload `message` 断言间接覆盖。classified as accepted — 端到端断言已覆盖正确性。

## 结论

**PASS.**

8 个文件、134 insertions、29 deletions 全部验证通过。无新增 finding。5 个指定检查点逐一符合预期，pyright 0 errors，受影响测试 36 passed。
