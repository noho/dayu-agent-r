# Code Review — Slice B Re-review (Controller Fix)

## Scope

- Mode: current changes (Slice B fix + original implementation)
- Branch: `wu-cli-activity-01`
- Base: `main` (HEAD at `7e22e7a8`)
- Output file: `docs/reviews/wu-cli-output-channels-slice-b-rereview-ds-20260617.md`
- Included scope:
  - `dayu/cli/arg_parsing.py` — `ParsedCliArgs.detail`、namespace default、`--detail`/`--no-detail` 互斥组。
  - `dayu/cli/commands/prompt.py` — `detail` 参数全链路（parse → `_execute_prompt_on_existing_session` → `_new_detail_activity_renderer` → `on_activity`）、cancel 提示门禁。
  - `tests/cli/test_arg_parsing.py` — parser 正交性/互斥/默认值测试。
  - `tests/cli/test_prompt_command.py` — 集成测试含修复后的 Outbox fallback watcher-failure 语义。
  - `tests/README.md` — 测试覆盖事实更新。
  - `docs/reviews/wu-cli-output-channels-slice-b-fix-20260617.md` — Controller fix 说明。
- Excluded scope: Slice A/C/D、Host/Engine/Service 内部实现。
- Reference docs:
  - `CLAUDE.md` — 项目约束。
  - `docs/reviews/wu-cli-output-channels-plan-20260617.md` — 已接受 plan。
  - `docs/reviews/wu-cli-output-channels-slice-b-code-review-ds-20260617.md` — 前次 review。
  - `docs/reviews/wu-cli-output-channels-slice-b-fix-20260617.md` — Controller 发现的 stale test 修复。

## Fix summary

Controller 复跑测试时 `test_prompt_command_uses_outbox_fallback_when_live_terminal_missing` 发生无限等待。Root cause 不是 `--detail/--no-detail` 运行时缺陷，而是旧测试语义与当前 Service 契约冲突：`submit_entrypoint_turn_and_wait` 的 Outbox fallback 只在 watcher 明确失败后触发，不是"watcher 没有 terminal event"的通用兜底路径。旧测试构造的是"watcher 健康但无 terminal"场景，Service 持续等待是正确行为。

修复内容：

| 变更 | 文件:行号 | 说明 |
|---|---|---|
| `_RaiseSignal` dataclass | test_prompt_command.py:75-78 | 测试 watcher 异常信号，携带 `error: Exception` |
| `_FakeHostEventIterator` 支持 `fail()` | test_prompt_command.py:131-138 | 推入异常信号到队列 |
| `_FakeHostEventIterator.__anext__` 处理异常 | test_prompt_command.py:117-118 | `isinstance(item, _RaiseSignal)` → `raise item.error` |
| `_FakeHost` 增加 `_submit_watcher_errors` | test_prompt_command.py:164,176,205 | 构造参数；submit 时注入 watcher 异常 |
| `_FakeHost.submit_followup` 注入异常 | test_prompt_command.py:268-269 | 在 terminal push 前调用 `watcher.fail(error)` |
| 用例改名+语义修正 | test_prompt_command.py:902-929 | `_when_watcher_fails` + `submit_watcher_errors=(RuntimeError(...),)` |
| 多测试补充 activity event 注入 | test_prompt_command.py:多处 | `submit_events=(_activity_event(),)` 确保 no-detail 下 activity 到达但不渲染 |

## Findings

未发现实质性问题。Controller 修复精确解决了 stale test 语义问题，未引入新缺陷。

逐项验证：

### 1. prompt no-detail/detail 输出隔离 — 正确

**全链路**：
```
parse_cli_args → args.detail (默认 False)
  → _run_prompt_command_async(detail=args.detail)           [prompt.py:187]
    → _execute_prompt_on_existing_session(detail=args.detail) [prompt.py:265]
      → activity_renderer = _new_detail_activity_renderer() if detail else None [prompt.py:286]
        → _submit_prompt_turn_handling_sigint(activity_renderer=...)  [prompt.py:286]
          → renderer = activity_renderer                      [prompt.py:391]
          → on_activity = None if renderer is None else renderer.record [prompt.py:418]
```

- **no-detail**: `activity_renderer=None` → `on_activity=None` → Service helper 不注册 activity callback → 无 activity 格式化/去重/输出开销。
- **detail**: `_new_detail_activity_renderer()` 创建 `CliActivityRendererOptions(visible=True, enabled=True)` → 绕过 `isatty()` 自动检测 → 非 TTY 也输出 activity → `on_activity=renderer.record`。

测试覆盖：
- `test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout` (test_prompt_command.py:905-931)：_FakeHost 推送 activity event，默认 no-detail 下 stderr 不含 `Activity:`。
- `test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout` (test_prompt_command.py:934-964)：`--detail` 下非 TTY 捕获流输出 activity，且无 `[VERBOSE]`/`[DEBUG]` 污染。
- `test_prompt_detail_activity_does_not_enter_log_file` (test_prompt_command.py:967-1005)：`--detail --log-file` 下 activity 只写 stderr、不进入日志文件。

### 2. watcher-failure-only Outbox fallback 语义 — 正确

**修复前问题**：`test_prompt_command_uses_outbox_fallback_when_live_terminal_missing` 构造 `submit_terminal=None` 且无 watcher 异常 → Service 持续等待 → 无限 hang。这是正确的 Service 行为（watcher 健康就应该等 terminal），但旧测试误把它当 Outbox fallback 场景。

**修复后**：`test_prompt_command_uses_outbox_fallback_when_watcher_fails` 构造 `submit_watcher_errors=(RuntimeError("watch stream disconnected"),)` → watcher 在 drain 阶段抛异常 → Service 捕获后走 Outbox fallback。

**异常注入路径**：
```
_FakeHost.submit_followup
  → self.watchers[-1].fail(RuntimeError("watch stream disconnected"))  [prompt.py:269]
    → self._queue.put(_RaiseSignal(error=error))                        [prompt.py:140]
  → await asyncio.sleep(0)  # 让出 event loop
  → return FollowupSnapshot(accepted_run_id="run-1", ...)

Service submit_entrypoint_turn_and_wait:
  → host.submit_followup(...) → FollowupSnapshot  # submit 已完成
  → iterate watcher → __anext__ → _RaiseSignal → raise RuntimeError(...)
  → catch watcher error → Outbox fallback
```

这个语义与生产一致：watcher 异常（网络断线、连接断开）才触发 Outbox fallback，不是"没有 terminal"就 fallback。

类型安全检查：`_FakeHostEventIterator._queue` 类型为 `asyncio.Queue[HostEvent | _StopSignal | _RaiseSignal]`，`__anext__` 对三类 item 做穷尽分支处理（`_StopSignal` → `StopAsyncIteration`；`_RaiseSignal` → `raise item.error`；`HostEvent` → return），返回类型仍为 `HostEvent`（因为前两类都 raise 了）。✅

### 3. AGENTS 约束检查

| 约束 | 状态 |
|---|---|
| 函数完整中文 docstring | ✅ 所有新增函数（`_new_detail_activity_renderer`、`fail`）均有中文 docstring |
| 禁止 `Any`/`object`/无类型签名 | ✅ diff 中无违规；`_RaiseSignal.error: Exception` 类型明确 |
| 禁止魔法值 | ✅ `"watch stream disconnected"` 是测试字面量，属可接受范围 |
| 禁止胶水 seam | ✅ 无 |
| 模块间依赖最小化 | ✅ 无新增跨层依赖 |
| 禁止兼容性代码 | ✅ 无；旧 `new_cli_activity_renderer` 导入已移除，未保留兼容 re-export |
| 分层架构 | ✅ CLI 层变更，未触及 Host/Engine/Service |
| 测试跟随实现边界迁移 | ✅ 旧 `test_prompt_tty_activity_writes_stderr_and_final_answer_stays_stdout` 已重命名为 `test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout`，旧 monkeypatch `new_cli_activity_renderer` 已移除 |

### 4. 测试增强细节验证

**多测试补充 `submit_events=(_activity_event(),)`**：修复在以下测试的 `_FakeHost` 构造中增加了 activity event 注入，确保 no-detail 路径下 activity 到达但不渲染：

| 测试 | 增加内容 | 验证点 |
|---|---|---|
| `test_prompt_command_outputs_fast_live_terminal_and_converts_requests` | `submit_events=(_activity_event(),)` | 默认 no-detail，`captured.err == ""` |
| `test_prompt_existing_session_execution_does_not_create_or_ensure` | `submit_events=(_activity_event(),)` | existing-session 路径，无 activity 输出 |
| `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` | `submit_events=(_activity_event(),)` + `assert "Activity:" not in captured.err` | `--verbose`/`--debug` 不触发 activity |

这些补充将 activity-event-arrives-but-no-render 的断言从仅一条测试扩散到多条路径，提高了回归防护面。

### 5. 前次 review 未覆盖项的检查

前次 review 标记了两个非实质性缺口：

- **Ctrl+T 在 no-detail 模式下静默 no-op**：未变化，仍是 UX 偏好问题。
- **`session resume` 永远不显示 activity**：未变化，与 plan 一致——`--detail` 只属于 `prompt` 命令。

本次修复未触及这两个区域。

## Open Questions

- 无。

## Residual Risk

- **watcher 异常注入时序**：测试 fake 中 `submit_followup` 在返回前将 `_RaiseSignal` 推入 watcher 队列，Service 在 submit 后迭代 watcher 时立即遇到异常。生产环境中 watcher 异常是真正异步的（在 drain 过程中随时发生）。当前 fake 的同步注入能覆盖"watcher 在 drain 开始时失败"路径，但无法覆盖"watcher drain 到一半时失败"的中间状态。这是 fake 的固有限制——要覆盖更细粒度的 drain 中间异常，需要更复杂的 fake watcher（如在 push N 个 event 后自动 fail）。当前测试目标（验证 Outbox fallback 入口可达且参数正确）已充分覆盖。
- **`tests/README.md` 更新**：已将 `prompt` 测试覆盖描述从"TTY activity stderr 渲染"更新为"默认 no-detail 不注册 activity 输出、显式 `--detail` 在非 TTY 下输出 activity、activity 不进入 `--log-file`"。与当前实现一致。✅

## Verification

```
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py -q
→ 81 passed, 3 warnings (third-party edgar deprecation)

source .venv/bin/activate && python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/prompt.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py
→ 0 errors, 0 warnings, 0 informations
```
