# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cli-activity-01-cli-mimo-20260617-145226.md`
- Included scope:
  - `dayu/cli/run_keys.py` — TTY 运行态按键监听
  - `dayu/cli/activity.py` — CLI activity renderer
  - `dayu/cli/composer.py` — interactive 输入态 composer
  - `dayu/cli/commands/prompt.py` — prompt 命令 activity / cancel 集成
  - `dayu/cli/commands/interactive.py` — interactive 命令 composer / activity / cancel 集成
  - `dayu/cli/output.py` — stdout/stderr 输出 helper（未修改，只读参照）
  - `tests/cli/test_prompt_command.py` — prompt 命令测试
  - `tests/cli/test_interactive_command.py` — interactive 命令测试
  - `tests/cli/test_activity_renderer.py` — activity renderer 独立测试
  - `tests/cli/test_interactive_composer.py` — composer 独立测试
  - `tests/service/test_entrypoint_runtime.py` — entrypoint runtime 测试（含 activity callback 测试）
  - `tests/README.md` — 测试手册更新
- Excluded scope: F-2 `cancel_entrypoint_run_and_wait` `on_activity` 已裁决延期至 Slice E；Host / Service / Engine 层改动不在本次 CLI review 范围
- Parallel review coverage: 无

## Findings

### 1-未修复-低-interactive terminal-before-cancel 竞争未在 REPL 层覆盖

- **入口/函数**: `_run_interactive_repl` → `_submit_interactive_turn_handling_sigint` → `_cancel_run_waiting_for_terminal_or_second_sigint`
- **文件(行号)**: `dayu/cli/commands/interactive.py:663-720`
- **输入场景**: 用户按 Esc 触发 cancel，Host cancel task 和 second SIGINT task 同时竞争
- **实际分支**: `_cancel_run_waiting_for_terminal_or_second_sigint` 内 `asyncio.wait(FIRST_COMPLETED)` 竞争
- **预期行为**: cancel task 先完成时返回 terminal result；second SIGINT 先到时本地退出
- **实际行为**: 函数级测试 `test_interactive_second_sigint_exits_after_cancel_request` 覆盖了 second SIGINT 胜出路径；`test_interactive_esc_requests_cancel_after_run_id` 覆盖了 Esc → cancel → terminal 路径。但 REPL 层 `_run_interactive_repl` 未直接测试"cancel terminal 先到达"的竞争场景
- **直接证据**: `test_interactive_repl_returns_130_on_second_sigint`（行 1136）测的是 second SIGINT 胜出；prompt 侧 `_cancel_prompt_turn_after_local_request`（行 429）也有类似函数级覆盖但无 REPL 级竞争测试
- **影响**: 若 `_run_interactive_repl` 的 `_submit_interactive_turn_handling_sigint` 返回值映射逻辑引入回归，现有测试可能无法捕获
- **建议改法和验证点**: 补充 REPL 级测试，用 `_FakeHost(cancel_status=SUCCEEDED)` + `_FakeRunningKeyMonitor(CANCEL_RUN)` 验证 cancel terminal 先到达时 REPL 正确输出并回到输入态
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-TtyRunningKeyMonitor 终端恢复依赖 close() 调用

- **入口/函数**: `TtyRunningKeyMonitor.close()`
- **文件(行号)**: `dayu/cli/run_keys.py:181-201`
- **输入场景**: `start()` 成功启用 cbreak 模式后，`close()` 未被调用（进程异常退出、上层遗漏 cleanup）
- **实际分支**: `close()` 内 `termios.tcsetattr(fd, TCSANOW, attrs)` 恢复原始终端属性
- **预期行为**: cbreak 模式必须在 monitor 生命周期结束时恢复
- **实际行为**: `close()` 正确恢复终端属性。prompt/interactive 的 `_submit_*_handling_sigint` 在 `finally` 块中调用 `monitor.close()`（prompt 行 423、interactive 行 548），确保正常和异常路径均恢复。但如果进程被 SIGKILL 或上层未进入 try/finally，终端将留在 cbreak 模式
- **直接证据**: `finally: ... monitor.close()` 在 prompt 行 423 和 interactive 行 548；`_restore_terminal_attrs`（行 261）用 `TCSANOW` 立即恢复
- **影响**: 用户终端在异常退出后可能需要手动 `stty sane` 恢复。属于 Unix TTY 编程的固有限制
- **建议改法和验证点**: 当前设计已是最小化方案。可考虑在模块 docstring 中记录"进程异常退出时终端可能留在 cbreak 模式"的已知行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **prompt 侧 second SIGINT REPL 级竞争测试缺失**: `test_prompt_sigint_after_run_id_cancels_host_run` 覆盖了 Esc → cancel → terminal 路径，`test_prompt_sigint_before_run_id_returns_local_interrupt` 覆盖了 Run accepted 前 SIGINT。但 prompt 侧没有类似 interactive 的 `_SecondSigintAfterCancelMonitor` REPL 级竞争测试。风险低，因为 prompt 和 interactive 共享相同的 `_cancel_prompt_turn_after_local_request` / `_cancel_run_waiting_for_terminal_or_second_sigint` 实现模式。
- **PromptToolkitInteractiveComposer 集成测试**: composer 独立测试（`test_interactive_composer.py`）验证了 key binding 注册和 handler 行为。但 `PromptToolkitInteractiveComposer.read()` 的端到端 prompt_toolkit 集成（真实终端交互）未在 CI 中覆盖。风险低，因为 prompt_toolkit 是成熟库且 key binding 已通过 fake 验证。
- **activity renderer `_last_event_sequence` 排序逻辑**: `test_activity_renderer_deduplicates_and_ignores_older_sequences` 验证了旧 sequence 被忽略。但未测试"同一 sequence 不同 dedupe key"的边界。风险低，因为 Host event stream 是严格有序的。

## 结论

**非阻断**。两项 low-severity findings 均不阻断 merge：

1. interactive terminal-before-cancel 竞争的 REPL 级测试可作为 follow-up 补充
2. TTY 终端恢复是 Unix TTY 编程的固有限制，当前 cleanup 路径已正确覆盖

关键验证结果：
- 72 项 CLI + service 测试全部通过
- pyright 零错误
- tests/README.md 已按触发规则更新
- `run_keys.py` cbreak/thread/close/termios restore 路径正确
- prompt/interactive Ctrl+T toggle、Esc cancel、Ctrl+C cancel/二次退出、terminal-first-wins 均满足 plan
- stdout/stderr 分离正确，non-TTY 不输出 live activity
- composer Ctrl+J/Ctrl+R/Ctrl+X Ctrl+E 通过独立单元测试验证
- 类型/docstring 符合 AGENTS 约束
