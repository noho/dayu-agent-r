# Code Review — Slice C: interactive run view / activity sink boundary

## Scope

- Mode: current changes (Slice C)
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-c-code-review-ds-20260617.md`
- Included scope:
  - `dayu/cli/run_view.py`（新）— `ActivitySink` / `InteractiveRunView` Protocol、`TerminalInteractiveRunView`、`new_interactive_run_view`
  - `dayu/cli/activity.py` — 新增 `format_cli_activity_line` 公共 helper
  - `dayu/cli/commands/interactive.py` — `activity_renderer` → `run_view` 迁移、`render_interactive_terminal_result` → `view.render_terminal_result`、Ctrl+T / Esc / cancel 路径
  - `tests/cli/test_interactive_run_view.py`（新）— run view 单元测试
  - `tests/cli/test_interactive_command.py` — 旧 TTY activity 测试迁移、新增 Ctrl+T 集成测试
  - `tests/README.md` — 测试覆盖事实同步
  - `docs/reviews/wu-cli-output-channels-slice-c-implementation-20260617.md` — 实现报告
- Excluded scope: Slice A（`--log-file`）、Slice B（`prompt --detail`）、Host/Engine/Service 内部实现。
- Reference docs:
  - `CLAUDE.md` — 项目约束。
  - `docs/reviews/wu-cli-output-channels-plan-20260617.md` — 已接受 plan（Slice C 定义于行 291-355）。

## Review method summary

沿 6 条主链路逐行走读：
1. `_run_interactive_repl` → `_submit_interactive_turn_handling_sigint` → `view.activity_sink().record_activity` → `TerminalInteractiveRunView.record_activity`
2. `RunningKeyAction.TOGGLE_ACTIVITY` → `view.toggle_view()` → `_render_view_snapshot`
3. `_submit_interactive_turn_handling_sigint` → Esc/SIGINT → `_cancel_interactive_turn_after_first_sigint` → `view.render_cancel_requested()` → `_cancel_run_waiting_for_terminal_or_second_sigint` → `view.render_local_exit_after_cancel()`
4. `view.render_terminal_result` → `render_interactive_terminal_result` + transcript buffer + stdout/stderr 输出分支
5. `new_interactive_run_view()` → `TerminalInteractiveRunView.__init__` → TTY `enabled` 决策
6. View lifecycle：创建 → finally close

## Findings

### 1-未修复-低-`TerminalInteractiveRunView.record_activity` 缺少 dedupe 防护

- **入口/函数**: `TerminalInteractiveRunView.record_activity` (`run_view.py:204-217`)
- **文件(行号)**: `dayu/cli/run_view.py:204-217`
- **输入场景**: Service helper 的 watcher 对同一 activity 多次回调 `on_activity`（例如 watch replay、重连重放、或 Service 内部未去重）。
- **实际分支**: `record_activity` 无条件追加 `format_cli_activity_line(activity)` 到 `_activity_lines` 并在 ACTIVITY mode 下实时 print。
- **预期行为**: 与 `CliActivityRenderer.record` (`activity.py:92-116`) 对齐，按 `dedupe_key` 去重、按 `event_sequence` 拒绝乱序事件。
- **实际行为**: 无去重、无乱序拒绝。同一 `dedupe_key` 的 activity 会被重复追加到 buffer，ACTIVITY mode 下会重复输出到 stderr。
- **直接证据**:
  - `CliActivityRenderer.record` 维护 `_seen_dedupe_keys: set[str]` 并在 `activity.py:102` 做 `activity.dedupe_key in self._seen_dedupe_keys` 检查。
  - `TerminalInteractiveRunView.record_activity` 无任何 `dedupe_key` 或 `event_sequence` 检查，直接 `self._activity_lines.append(line)` (`run_view.py:215`)。
- **影响**: 在当前 interactive 单 turn 流程中（每 turn 独立 run、Service watcher 不重放），实际不会触发。但如果未来 Service watcher 产生重复 activity（如 startup reconnect 期间推入 activity event），activity buffer 会出现重复条目，ACTIVITY mode 实时输出也会重复。影响面小，仅视觉重复。
- **建议改法和验证点**: 在 `TerminalInteractiveRunView` 中增加 `_seen_dedupe_keys: set[str]` 和 `_last_event_sequence: int | None`，在 `record_activity` 入口做与 `CliActivityRenderer.record` 相同的去重与乱序检查。验证：构造相同 `dedupe_key` 的两次 `record_activity` 调用，断言 buffer 中仅一条记录。
- **修复风险（低）**: 改动局限在 `run_view.py` 单文件内，不涉及 Protocol 变更。
- **严重程度（低）**: 当前交互流程不会触发，但缺少防御性去重使代码对 Service 行为变更更脆弱。

## Plan Adherence Check

逐条对照 plan Slice C (`docs/reviews/wu-cli-output-channels-plan-20260617.md` 行 291-355)：

| Plan requirement | Implementation | Status |
|---|---|---|
| 定义 `ActivitySink.record_activity` Protocol | `run_view.py:35-44` | ✅ |
| 定义 `InteractiveRunView` Protocol | `run_view.py:47-94`，含 `activity_sink`、`render_terminal_result`、`toggle_view`、`render_cancel_requested`、`render_local_exit_after_cancel`、`close` | ✅ |
| 非 full-screen TTY implementation 持有 transcript/activity buffers | `TerminalInteractiveRunView` (`run_view.py:123-302`) 持有 `_transcript_lines`、`_activity_lines` | ✅ |
| 默认 view 为 transcript | `self._mode = InteractiveRunViewMode.TRANSCRIPT` (`run_view.py:160`) | ✅ |
| Ctrl+T 复用 `RunningKeyAction.TOGGLE_ACTIVITY`，调 `view.toggle_view()` | `interactive.py:614` 调用 `view.toggle_view()` | ✅ |
| Ctrl+T 新语义不输出 `Activity hidden` | `toggle_view()` 无 `Activity hidden` 输出；测试断言 `"Activity hidden" not in stderr_text` (`test_interactive_run_view.py:87`) | ✅ |
| Esc 继续 cancel | `interactive.py:619-629` 保持 Esc → `_cancel_interactive_turn_after_first_sigint` | ✅ |
| 非 TTY implementation 保持原 stdout/stderr 输出 | `TerminalInteractiveRunView` 在 `not self._enabled` 时 `render_terminal_result` 直接写 stdout/stderr (`run_view.py:244-246`) | ✅ |
| interactive command 不直接创建 `CliActivityRenderer` | `interactive.py` 移除了 `from dayu.cli.activity import CliActivityRenderer, new_cli_activity_renderer` | ✅ |
| 不引入 full-screen `prompt_toolkit Application.run_async()` | 无 `prompt_toolkit` 新依赖 | ✅ |
| activity 复用 `dayu.cli.activity` 的有界格式化 | `run_view.py:17` `from dayu.cli.activity import format_cli_activity_line` | ✅ |
| cancel 提示通过 UI 方法输出，不写 logging | `render_cancel_requested` / `render_local_exit_after_cancel` 通过 `print(..., file=self._stderr)` 输出，不经 logging | ✅ |

## Key Path Walkthrough

### Path 1: Normal interactive turn (TTY, transcript mode)

```
_run_interactive_repl
  → new_interactive_run_view() → TerminalInteractiveRunView(enabled=True, mode=TRANSCRIPT)
  → _submit_interactive_turn_handling_sigint(run_view=view)
    → on_activity=view.activity_sink().record_activity
    → submit_entrypoint_turn_and_wait(...)
      → [Service watcher 推送 activity event]
      → on_activity(activity)
        → _InteractiveRunViewActivitySink.record_activity(activity)
          → view.record_activity(activity)
            → format_cli_activity_line(activity) → line
            → _activity_lines.append(line)       # 写入 buffer
            → mode=TRANSCRIPT → 不实时 print     # 无 stderr 输出
    → [Service watcher 推送 terminal event]
    → return EntrypointRunTerminalResult
  → view.render_terminal_result(terminal)
    → render_interactive_terminal_result(terminal, stdout=buffer, stderr=buffer)
      → successful → print(answer, file=buffer_stdout)
    → _transcript_lines.extend(["answer"])
    → enabled=True, mode=TRANSCRIPT → _write_lines(["answer"], sys.stdout)  # 写真实 stdout
    → return EXIT_SUCCESS
  → advance_cli_terminal_cursor(...)
  → turn_index += 1 → 下一轮循环
```

Output contract: activity 进入 buffer 但不写 stderr；final answer 写 stdout 并进入 transcript buffer。✅

### Path 2: Ctrl+T toggle (transcript → activity → transcript)

```
[运行态，mode=TRANSCRIPT]
  → RunningKeyAction.TOGGLE_ACTIVITY
  → view.toggle_view()
    → mode=TRANSCRIPT → mode=ACTIVITY
    → _render_view_snapshot("[Interactive activity]", activity_lines, stderr)
      → print("[Interactive activity]", file=stderr)
      → _write_lines(activity_lines, stderr)  # 输出 buffer 快照

[运行态继续，mode=ACTIVITY]
  → activity 到达 → record_activity → 写入 buffer + 实时 print(line, file=stderr)

[再次 Ctrl+T]
  → mode=ACTIVITY → mode=TRANSCRIPT
  → _render_view_snapshot("[Interactive transcript]", transcript_lines, stderr)
```

Output contract: 切换时渲染目标 buffer 快照；无 `Activity hidden` 旧文本。✅

### Path 3: Esc cancel (TTY, run accepted)

```
[运行态]
  → RunningKeyAction.CANCEL_RUN
  → _cancel_interactive_turn_after_first_sigint(run_view=view)
    → submit_task.cancel(); await submit_task  # 等待 submit 取消
    → run_id 已记录 → view.render_cancel_requested()
      → print("Interactive: cancel requested", file=stderr)  # 仅 enabled 时输出
    → _cancel_run_waiting_for_terminal_or_second_sigint(run_view=view)
      → host.cancel_run(run_id, ...)
      → cancel_terminal 到达 → return EntrypointRunTerminalResult
```

Output contract: "Interactive: cancel requested" 写 stderr（仅 enabled 时）；Host cancel 正常发起。✅

### Path 4: Non-TTY fallback

```
[非 TTY stderr]
  → new_interactive_run_view() → TerminalInteractiveRunView(enabled=False)
    # isatty() = False → options=None → enabled=False
  → _submit_interactive_turn_handling_sigint(run_view=view)
    → on_activity=view.activity_sink().record_activity
    → record_activity: 写入 buffer 但 mode=TRANSCRIPT 时不实时 print
  → view.render_terminal_result(terminal)
    → enabled=False → _write_lines(stdout_lines, sys.stdout)  # 直接写 stdout
```

Output contract: 非 TTY 保持原 stdout/stderr 输出行为；activity 仍进入 buffer 但无实时输出。✅

## stdout/stderr/logging 隔离检查

| 输出内容 | 通道 | 是否受 `--log-file` 影响 | 是否受 TTY 影响 |
|---|---|---|---|
| transcript terminal result (SUCCEEDED) | stdout (`self._stdout`) | 否 | 否（始终写 stdout） |
| transcript terminal result (FAILED/CANCELLED) | stderr (`self._stderr`) | 否 | 否（始终写 stderr） |
| activity buffer 记录 | 内存 `_activity_lines` | 否 | 否（始终入 buffer） |
| activity 实时输出 | stderr (`self._stderr`)，仅 ACTIVITY mode | 否 | 是（仅 enabled 时输出） |
| Ctrl+T view snapshot | stderr (`self._stderr`) | 否 | 是（仅 enabled 时切换） |
| cancel 提示 | stderr (`self._stderr`) | 否 | 是（仅 enabled 时输出） |
| `--verbose`/`--debug` 诊断 | stderr，经 `runtime_log` | 是（Slice A） | 否 |

所有 UI 输出（transcript、activity snapshot、cancel 提示）均不经 Python logging 体系，不被 `--log-file` 捕获。与 plan `--log-file` 只迁移诊断日志的决策一致。✅

## AGENTS 约束检查

| 约束 | 状态 |
|---|---|
| 函数完整中文 docstring | ✅ 所有新增函数/方法均有中文 docstring |
| 禁止 `Any`/`object`/无类型签名 | ✅ `run_view.py` 中无违规；Protocol 参数类型明确 |
| 禁止胶水 seam | ✅ 无 |
| 禁止魔法值 | ⚠️ 见下方 minor note |
| 模块间依赖最小化 | ✅ `run_view.py` 仅依赖 `dayu.cli.activity`、`dayu.cli.output`、`dayu.service.entrypoint_runtime`（DTO） |
| 禁止兼容性代码 | ✅ 无兼容 re-export；`interactive.py` 移除了旧 `CliActivityRenderer` 导入 |
| 分层架构 | ✅ CLI 层变更，未触及 Host/Engine/Service |
| 测试跟随实现边界迁移 | ✅ 旧 TTY activity 测试迁移为 run view buffer 测试 |

Minor note: `run_view.py` 模块级常量未使用 `Final`（如 `_TRANSCRIPT_HEADER: str = "Interactive transcript"`），而 `activity.py` 中同类常量使用 `Final`（如 `_ACTIVITY_PREFIX: Final[str] = "Activity"`）。这是风格不一致，不影响 correctness。无 `Final` 不会导致类型收窄失败或运行期行为差异。

## Open Questions

- 无。

## Residual Risk

- **Activity buffer 无界增长**：`_activity_lines` 和 `_transcript_lines` 在整个 interactive session 中持续追加，无上限。对于数百轮的长时间 session，内存占用可能显著。非 full-screen 实现按 plan 接受此限制；若后续需要，可加有界裁剪（如保留最近 N 行）。
- **`TerminalInteractiveRunView` 非 full-screen 限制**：当前 `_render_view_snapshot` 在切换 view 时全量输出 buffer 到 stderr，buffer 很大时输出量也大。按 plan "若必须迁入 full prompt_toolkit `Application`，拆为后续独立 work unit"，当前实现符合 stop condition。
- **`session resume --mode interactive` 路径的 view 生命周期**：`_execute_interactive_on_existing_session` 传入 `run_view=None`（默认），`_run_interactive_repl` 内部创建并 close。但若调用方显式传入 `run_view`，调用方负责 close。当前测试中 `test_interactive_esc_requests_cancel_after_run_id` 显式创建 `TerminalInteractiveRunView` 但未显式 close（依赖 `StringIO` GC）。测试无资源泄漏，但生产调用方契约隐含"传入的 run_view 由调用方管理生命周期"。当前仅 `_run_interactive_repl` 创建 view，无外部传入场景，风险极低。

## Verification

```
source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q
→ 36 passed, 3 warnings (third-party edgar deprecation)

source .venv/bin/activate && pytest tests/cli/ -q
→ 195 passed, 3 warnings (no regressions)

source .venv/bin/activate && python -m pyright dayu/cli/run_view.py dayu/cli/activity.py dayu/cli/commands/interactive.py tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py
→ 0 errors, 0 warnings, 0 informations
```
