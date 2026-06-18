# Code Review (Re-Review)

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-b-rereview-mimo-20260617.md`
- Included scope: Slice B fix - prompt no-detail/detail 输出隔离、watcher-failure-only Outbox fallback
- Excluded scope: Slice A (--log-file)、Slice C (interactive run view)、Host/Engine 变更

## Reviewed Files

- `dayu/cli/commands/prompt.py` - detail 参数传递与 activity renderer 创建逻辑
- `tests/cli/test_prompt_command.py` - watcher failure 模拟、detail 输出隔离测试
- `docs/reviews/wu-cli-output-channels-slice-b-fix-20260617.md` - controller 修复说明

## Findings

未发现实质性问题。

Controller 修复正确解决了旧测试语义与 Host/Service 语义的冲突：

### 1. prompt no-detail/detail 输出隔离

**修复前问题**：`_execute_prompt_on_existing_session` 硬编码 `activity_renderer=new_cli_activity_renderer()`，导致默认 no-detail 时仍创建 TTY policy renderer。

**修复后行为**：
- `_run_prompt_command_async` 传递 `detail=args.detail`（`prompt.py:187`）
- `_execute_prompt_on_existing_session` 接收 `detail: bool = False` 参数（`prompt.py:265`）
- `activity_renderer=_new_detail_activity_renderer() if detail else None`（`prompt.py:286`）
- `_new_detail_activity_renderer()` 创建 `CliActivityRendererOptions(visible=True, enabled=True)`，绕过 TTY gate（`prompt.py:302-314`）

**测试覆盖**：
- `test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout`：默认 no-detail 即使收到 activity event 也不输出 `Activity:`
- `test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout`：显式 `--detail` 在非 TTY 下输出 activity
- `test_prompt_detail_activity_does_not_enter_log_file`：`--detail` activity 不进入 `--log-file`
- `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout`：`--verbose`/`--debug` 不显示 activity

### 2. watcher-failure-only Outbox fallback 语义

**修复前问题**：旧测试 `test_prompt_command_uses_outbox_fallback_when_live_terminal_missing` 构造"watcher 没有 terminal，但 watcher 也没有失败"的场景，却期待 Outbox fallback。这种输入下 Service 持续等待是正确行为，因为：
- `submit_entrypoint_turn_and_wait()` 是在线、已 attach watcher 的路径
- 正常 final answer 必须来自 Host event stream
- Outbox 不是 prompt 在线读取 final answer 的通用接口
- Submit 路径只在 watcher failure 后允许读取 Outbox terminal

**修复后行为**：
- `_FakeHostEventIterator` 新增 `_RaiseSignal` 类和 `fail()` 方法，可模拟 watcher drain 异常
- `_FakeHost` 新增 `submit_watcher_errors` 参数，在 submit 时推入 watcher 错误
- 测试改名为 `test_prompt_command_uses_outbox_fallback_when_watcher_fails`，构造 watcher 断线场景

**测试覆盖**：
- `test_prompt_command_uses_outbox_fallback_when_watcher_fails`：submit 后 watcher 明确抛出 `RuntimeError("watch stream disconnected")`，断言 prompt 经 Outbox fallback 输出 final answer

### 3. AGENTS 约束合规

- 函数提供了完整中文 docstring，包含参数、返回值、异常
- 类与模块提供了中文概览 docstring
- 没有使用 `object`、`Any`、无类型参数、无类型返回值
- `_RaiseSignal` 使用 `@dataclass(frozen=True, slots=True)`，类型安全
- `_FakeHostEventIterator._queue` 类型注解为 `asyncio.Queue[HostEvent | _StopSignal | _RaiseSignal]`，明确

## Open Questions

无。

## Residual Risks

无显著残留风险。

## Validation

### 已运行（由 controller fix artifact 确认）

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py::test_prompt_command_uses_outbox_fallback_when_watcher_fails -q
# 1 passed

source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py -q
# 81 passed, 3 warnings

source .venv/bin/activate && pyright dayu/cli/arg_parsing.py dayu/cli/commands/prompt.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py
# 0 errors

git diff --check
# clean
```

### 未运行

无。本次 re-review 基于静态代码阅读和 controller fix artifact 验证记录，未独立重新运行测试。

---

Review timestamp: 2026-06-17T22:44:58+08:00
Reviewer: AgentMiMo
