# WU-CLI-01 CLI-01-S4 Implementation Review — AgentMiMo

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S4, Interactive command using the same Service session semantics
- Gate: implementation review
- Agent: AgentMiMo
- Date: 2026-06-14
- Review target: 未提交改动（`git diff HEAD` + untracked files）

## Review Criteria

本轮裁决标准：迁移旧 `interactive` 的业务逻辑/用户可见语义，适配新 Host public contracts/API；不以旧 `interactive_ui.py` 或旧 label registry 一致性作为正确性。

---

## Findings

### F-01 [PASS] EntrypointRuntimeRequest / Service helper / Host public API 边界

`dayu/cli/commands/interactive.py` 全文只通过以下路径与 Host/Service 交互：

- `prepare_entrypoint_runtime(EntrypointRuntimeRequest(scene_id="interactive"))` — runtime 准备。
- `open_host(runtime.host_assembly.options)` — Host 生命周期。
- `ensure_or_create_entrypoint_session(...)` — session ensure/create。
- `submit_entrypoint_turn_and_wait(...)` — 单轮 submit + terminal wait。
- `cancel_entrypoint_run_and_wait(...)` — cancel + terminal wait。

未发现直接构造 Engine request、访问 Host durable/internal、读取 Fins storage 的路径。import 列表只引用 `dayu.host.api`（public DTO）、`dayu.host.open_host`（public opener）、`dayu.service.entrypoint_runtime`（Service helper）、`dayu.service.host_assembly`（Service DTO）。**Pass。**

### F-02 [PASS] CLI / Service 边界清晰度

CLI adapter（`interactive.py`）职责边界：

- REPL 输入（`_read_user_input` → `input()`）。
- stdout/stderr 终态输出（委托 `render_interactive_terminal_result`）。
- SIGINT → Host cancel 转换（`_InteractiveSigintMonitor` + `_cancel_run_waiting_for_terminal_or_second_sigint`）。
- HostCallContext / client_request_id 构造（委托 `host_context.py`）。
- exit code 映射。

Session、turn、terminal observation 与 cancel 语义全部复用 `dayu.service.entrypoint_runtime`。`output.py` 的 `render_interactive_terminal_result` 是纯 UI 输出函数，不持有 Host 状态。Service helper 仍可供未来 WeChat/GUI 复用。**Pass。**

### F-03 [PASS] 参数映射

| 参数 | 映射 | 证据 |
|---|---|---|
| `--label` | `interactive_slot_key(args.label)` → `cli.interactive.<label>` slot | `interactive.py:334-347` |
| `--new-session` | `ensure_or_create_entrypoint_session(create_new=True, bind_slot=True)` | `interactive.py:348-364` |
| `--ticker` | `context_slot_values["fins_default_subject"] = ticker.strip()` | `interactive.py:772-785` |
| 无 ticker | `context_slot_values["fins_default_subject"] = "未指定具体公司"` | `interactive.py:59, 782` |
| `base_user` | 固定 `"本地 CLI 用户"` | `interactive.py:60, 785` |
| `--model-name` | `ServiceAssemblyOverrides(model_id=...)` | `interactive.py:292-296` |
| execution overrides | `ServiceRunOverrides(temperature, tool_timeout_seconds, max_iterations, ...)` | `interactive.py:743-769` |
| unsupported legacy flags | `_raise_for_unsupported_execution_options` → `EXIT_USAGE_ERROR` | `interactive.py:692-704` |
| `--label` / `--new-session` 互斥 | argparse `add_mutually_exclusive_group` | `arg_parsing.py:340-346` |

`arg_parsing.py:101` 补齐 `new_session: bool` 类型声明。`--label` / `--new-session` 互斥由 argparse 在解析层保证。**Pass。**

### F-04 [PASS] 多轮状态机

`_run_interactive_repl`（`interactive.py:383-430`）实现 while-True REPL：

- 每轮调用 `_submit_interactive_turn_handling_sigint`，内部创建新的 `submit_task`（含新的 `HostCallContext.request_id` 和 `client_request_id`）。
- 每轮创建新的 `_InteractiveSigintMonitor` 实例（通过 `sigint_monitor_factory`）。
- `submit_entrypoint_turn_and_wait` 内部每轮 attach 新 watcher、drain events、close watcher。
- 测试 `test_interactive_two_turns_use_same_session_and_independent_watchers` 验证：
  - 同一 session_id。
  - 每轮独立 watcher attach/close（`watchers[0].closed_count == 1, watchers[1].closed_count == 1`）。
  - 每轮独立 client_request_id（`turn-1:submit`, `turn-2:submit`）。
  - 每轮独立 `HostCallContext.request_id`。

`test_entrypoint_runtime_interactive_path.py::test_interactive_two_turns_have_independent_terminal_wait_state` 进一步验证真实 runtime 下两轮独立 terminal wait state。**Pass。**

### F-05 [PASS] SIGINT cancel 语义

**运行态第一次 Ctrl-C：**

1. `sigint_monitor.wait_next` 返回 → 进入 `_cancel_interactive_turn_after_first_sigint`。
2. 若已有 run_id（`accepted_run.run_id is not None`）：cancel submit_task → 发 `cancel_entrypoint_run_and_wait(EntrypointCancelRequest(..., reason=CLI_SIGINT_REASON, mode=CancelMode.GRACEFUL))`。
3. 若尚无 run_id：进入 `_wait_for_run_id_or_local_exit`，等待 run_id / submit 完成 / 第二次 SIGINT。

**等待 run id 阶段 submit 先完成/失败的处理（controller pre-review blocker fix）：**

`_wait_for_run_id_or_local_exit`（`interactive.py:584-626`）用 `asyncio.wait` 同时等待 `submit_task`、`run_id_task`、`second_sigint_task`：

- `submit_task in done` → 取消 run_id_task 和 second_sigint_task → 返回 `_SubmitCompletedWhileWaitingForRunId(terminal=await submit_task)`。若 submit_task 抛异常，`await submit_task` 会向上透传，不误映射为 130。
- `second_sigint_task in done` → cancel submit_task → 返回 `_LocalExitRequested()`。
- `run_id_task in done` → 返回 `_RunIdAccepted(run_id=...)`。

测试覆盖：
- `test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first` — submit 先成功。
- `test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first` — submit 先失败，RuntimeError 向上透传。
- `test_wait_for_run_id_returns_none_when_second_sigint_wins` — 第二次 SIGINT 先到。

**同一轮 cancel id 稳定：**

`interactive_cancel_client_request_id(invocation, turn_index=turn_index, run_id=run_id)` 基于 `invocation_id + turn_index + run_id + CLI_SIGINT_REASON` 构造。测试验证 `cancel_request.client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")`。

**第二次 SIGINT 本地 130：**

`_cancel_run_waiting_for_terminal_or_second_sigint`（`interactive.py:629-689`）在等待 cancel terminal 时同时监听第二次 SIGINT；第二次 SIGINT 先到时返回 `None`，REPL 层映射为 `EXIT_KEYBOARD_INTERRUPT`（130）。

测试覆盖：`test_interactive_second_sigint_exits_after_cancel_request`、`test_interactive_repl_returns_130_on_second_sigint`。**Pass。**

### F-06 [PASS] Terminal policy

`render_interactive_terminal_result`（`output.py:62-95`）：

| Terminal Status | 输出位置 | 返回值 | 行为 |
|---|---|---|---|
| `SUCCEEDED` | stdout（final_answer.content） | `EXIT_SUCCESS`（0） | 继续输入态 |
| `SUCCEEDED` 但 `final_answer is None` | stderr（fallback 消息） | `EXIT_FAILURE`（1） | 继续输入态 |
| `FAILED` | stderr（error_message 或 fallback） | `EXIT_SUCCESS`（0） | 继续输入态 |
| `CANCELLED` | stderr（cancel_reason 或 fallback） | `EXIT_SUCCESS`（0） | 继续输入态 |
| `LOST` | stderr（error_message 或 fallback） | `EXIT_FAILURE`（1） | fatal 退出 |

与 accepted plan 的 terminal policy 完全一致。`SUCCEEDED` 无 final_answer 的 case 返回 `EXIT_FAILURE`（1）是合理的 fail-safe。

REPL 层（`interactive.py:427-429`）检查 `render_exit_code != EXIT_SUCCESS` 时退出循环，即 `LOST` 和 `SUCCEEDED` 无 final_answer 时退出。**Pass。**

### F-07 [PASS] 测试 / README / pyright / AGENTS 合规

- **中文 docstring**：所有新增函数、类、模块均有完整中文 docstring，含参数、返回值、异常说明。
- **无 Any/object/hasattr/getattr 逃逸**：grep 确认新增代码无 `Any`、`object`、`hasattr`、`getattr`。
- **无兼容 wrapper**：未发现仅为保持旧导入路径的 re-export 或 facade。
- **无魔法字符串**：所有常量使用 `Final[str]` 声明；schema 内字符串按 AGENTS.md 例外允许。
- **tests/README.md**：已同步更新 interactive 测试覆盖说明。
- **pyright**：0 errors, 0 warnings。
- **测试**：63 passed（coverage 88-100%），82 passed（regression）。
- **git diff --check**：clean。

**Pass。**

### F-08 [INFO] `_accepted_run._event` 初始化时机

`_AcceptedRunState.__init__` 中 `self._event = asyncio.Event()`。在 Python 3.10+ 中，`asyncio.Event()` 的创建不应在非运行的事件循环上调用（已弃用行为），但本模块中 `_AcceptedRunState` 总是在 async 上下文（`_submit_interactive_turn_handling_sigint`）中创建，所以实际无问题。与 prompt.py 的 `_AcceptedRunState` 对比，prompt 版本不使用 Event（因为 prompt 是单轮，不需要等待 run_id 的异步机制），interactive 版本增加了 Event 用于 `_wait_for_run_id`。设计合理。**Info only，不阻塞。**

### F-09 [INFO] `_InteractiveSigintMonitor.notify` 参数兼容性

`notify` 方法签名接受 `_signal_number` 和 `_frame` 参数以兼容 `signal.signal` 风格 handler。但 `loop.add_signal_handler` 的回调签名是 `callback()` 无参数。实际运行中 `add_signal_handler` 会以无参数方式调用 `notify()`，由于参数有默认值 `None`，所以兼容。**Info only，不阻塞。**

### F-10 [PASS] `_cancel_interactive_turn_after_first_sigint` 中 submit_task 已完成的竞争

`interactive.py:569-570`：获取 run_id 后先检查 `submit_task.done()`，若已完成直接 `await submit_task` 返回。这防止了对已完成 task 发 cancel 的无意义操作。**Pass。**

### F-11 [PASS] `--new-session` 的 slot key 使用 invocation_id

`interactive_process_slot_key(invocation)` 生成 `cli.interactive.<invocation_id>`，确保每次 `--new-session` 使用唯一的进程本地 slot key，不会复用旧 session。测试验证 `create_requests[0].slot_key.startswith("cli.interactive.")`。**Pass。**

### F-12 [PASS] `open_host` 使用 `async with` 确保 Host 生命周期

`interactive.py:301`：`async with open_host(runtime.host_assembly.options) as host`。Host handle 在 REPL 循环结束后自动关闭。SIGINT cancel 和 terminal wait 都在 `async with` 块内完成。**Pass。**

---

## Verdict

**Pass — 无 blocker，无 major，无 minor。**

本轮实现严格通过 `EntrypointRuntimeRequest(scene_id="interactive")`、Service helper、`open_host` 与 Host public API 完成所有 Host 交互；CLI / Service 边界清晰；参数映射符合 accepted plan；多轮状态机正确；SIGINT cancel 语义完整覆盖了 controller pre-review blocker（等待 run id 阶段 submit 先完成/失败不误映射为 130）；terminal policy 与 plan 一致；测试覆盖率达标；pyright 0 errors；代码风格符合 AGENTS.md 约束。

## Verified Commands

1. `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q` — **63 passed**，覆盖率 interactive.py 88%、host_context.py 99%、output.py 83%、arg_parsing.py 100%、main.py 94%。
2. `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q` — **82 passed**（回归）。
3. `source .venv/bin/activate && python -m pyright dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py dayu/cli/arg_parsing.py dayu/cli/main.py tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py` — **0 errors, 0 warnings**。
4. `git diff --check HEAD` — **clean**。
5. 手动 grep 检查 `hasattr`/`getattr`/`Any`/`object`/Engine import/Fins storage import — **无命中**。
