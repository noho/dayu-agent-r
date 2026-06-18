# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-c-code-review-mimo-20260617.md`
- Included scope: Slice C - interactive run view / activity sink boundary
- Excluded scope: Slice A (--log-file)、Slice B (prompt --detail/--no-detail)、Host/Engine 变更

## Reviewed Files

- `dayu/cli/activity.py` - 新增 `format_cli_activity_line()` 供 run view 复用
- `dayu/cli/run_view.py` - 新增 `ActivitySink`、`InteractiveRunView` Protocol 与 `TerminalInteractiveRunView` 实现
- `dayu/cli/commands/interactive.py` - interactive command 使用 run view 替代旧 activity renderer
- `tests/cli/test_interactive_run_view.py` - run view 独立单元测试
- `tests/cli/test_interactive_command.py` - interactive command 集成测试
- `tests/README.md` - 测试覆盖事实更新

## Findings

未发现实质性问题。

实现与已接受 plan 的 Slice C 要求一致：

### 1. interactive run_view boundary

**Protocol 设计**：
- `ActivitySink` Protocol 定义 `record_activity(activity: EntrypointActivity) -> None`
- `InteractiveRunView` Protocol 定义 `activity_sink()`、`render_terminal_result()`、`toggle_view()`、`render_cancel_requested()`、`render_local_exit_after_cancel()`、`close()`
- `TerminalInteractiveRunView` 实现非 full-screen 的 transcript/activity view

**行为正确性**：
- 默认 transcript mode（`run_view.py:160`）
- activity 到达时总是进入 activity buffer（`run_view.py:215`）
- 只有在 activity view 已打开时才实时写 UI stderr（`run_view.py:216-217`）
- terminal result 始终进入 transcript buffer（`run_view.py:242-243`）
- 在 transcript view 下保持原 stdout/stderr 用户通道输出（`run_view.py:244-246`）

**边界清晰**：
- run view 不读取 Host durable internals
- 不参与 logging handler 装配
- 只消费 Service entrypoint DTO

### 2. Ctrl+T transcript/activity switch

**语义正确**：
- `toggle_view()` 切换 transcript/activity view（`run_view.py:258-266`）
- 渲染当前 buffer 快照（`run_view.py:260-271`）
- 不输出旧 `Activity hidden` 文本

**测试覆盖**：
- `test_run_view_toggle_switches_activity_and_transcript_snapshots`：确认 Ctrl+T 在 activity/transcript 间切换，不输出旧 hidden 文本
- `test_interactive_ctrl_t_switches_run_view_without_cancel`：确认 Ctrl+T 只切 view，不触发 Host cancel

### 3. Esc cancel

**实现正确**：
- cancel path 使用 `view.render_cancel_requested()`（`interactive.py:705-706`）
- 二次 SIGINT 使用 `view.render_local_exit_after_cancel()`
- cancel 提示通过 view 方法输出，不进入 logging

**测试覆盖**：
- `test_interactive_esc_requests_cancel_after_run_id`：确认 Esc 请求 Host cancel，输出 `Interactive: cancel requested`
- `test_interactive_second_sigint_exits_after_cancel_request`：确认二次 SIGINT 本地退出

### 4. stdout/stderr/logging isolation

**隔离正确**：
- activity 写入 buffer，不作为普通 stderr activity 行实时输出
- activity view 下实时写 UI stderr（`run_view.py:216-217`）
- terminal result 在 transcript view 下保持原 stdout/stderr 用户通道输出（`run_view.py:244-246`）
- activity view 下 terminal result 进入 transcript buffer，不直接写 stdout（`run_view.py:233-240`）

**测试覆盖**：
- `test_run_view_records_activity_without_transcript_output`：transcript view 下 activity 只进入 buffer
- `test_run_view_renders_terminal_result_to_transcript`：terminal success 写 stdout 并进入 transcript buffer
- `test_run_view_activity_mode_buffers_terminal_until_transcript_toggle`：activity view 下 terminal 进入 buffer，不直接写 stdout

### 5. AGENTS 约束合规

- 函数提供了完整中文 docstring，包含参数、返回值、异常
- 类与模块提供了中文概览 docstring
- 没有使用 `object`、`Any`、无类型参数、无类型返回值
- Protocol 定义清晰，使用 `...` 表示抽象方法
- `InteractiveRunViewMode` 使用 `StrEnum`，类型安全
- `InteractiveRunViewOptions` 使用 `@dataclass(frozen=True, slots=True)`

### 6. 复用与避免重复

- `format_cli_activity_line()` 从 `activity.py` 导出，run view 复用同一格式化逻辑
- `_InteractiveRunViewActivitySink` 内部实现 `ActivitySink` Protocol，转发给 view
- `_split_buffer_lines()` 和 `_write_lines()` 私有辅助函数职责单一

## Open Questions

无。

## Residual Risks

无显著残留风险。

**已确认的 stop condition**：
- 本 slice 没有引入 full-screen prompt_toolkit `Application.run_async()`
- 当前实现是非 full-screen run view，符合已接受 plan 的 stop condition
- 若需要 full-screen prompt_toolkit `Application`，应拆为后续独立 work unit

## Validation

### 已运行（由 implementation artifact 确认）

```bash
source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py -q
# 30 passed, 3 warnings

source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q
# 36 passed, 3 warnings

source .venv/bin/activate && pyright dayu/cli/activity.py dayu/cli/run_view.py dayu/cli/commands/interactive.py tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py
# 0 errors

git diff --check
# clean
```

### 未运行

无。本次 review 基于静态代码阅读和 implementation artifact 验证记录，未独立重新运行测试。

---

Review timestamp: 2026-06-17T22:57:11+08:00
Reviewer: AgentMiMo
