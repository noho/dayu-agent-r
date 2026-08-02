# Code Review — S3B Real-evidence Regression (第二路独立审查)

## Scope

- **Mode:** working-tree changes (未提交)
- **Branch:** `codex/interactive-oracle`
- **Base:** `eae09be9` (HEAD)
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-ds.md`
- **Included scope (production):**
  - `dayu/cli/agent_entrypoint.py` — `CliSigintMonitor.install()` 幂等 guard
  - `dayu/cli/commands/prompt.py` — invocation 起点提前安装 SIGINT + key monitor
  - `dayu/cli/run_keys.py` — `TCSANOW` 替代默认 `TCSAFLUSH`
  - `dayu/cli/composer.py` — `has_pending_submit_intent()` contract 与 `_record_submit_intent` 实现
  - `dayu/cli/session_execution.py` — prompt observed_sigint_count=0、interactive pending_submit_sigint_count drain
- **Included scope (test):**
  - `tests/cli/test_interactive_command.py`
  - `tests/cli/test_interactive_composer.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_run_keys.py`
- **Excluded scope:**
  - 四份 S8 README（`README.md`、`dayu/config/README.md`、`dayu/host/README.md`、`tests/README.md`）— 仅核对不在 S3B 范围
  - `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md` — 不在本次 scope
  - PR 190 已提交历史中的 Host/Engine/Service 变更 — 不在 working-tree diff
  - `docs/reviews/wu-cli-conformance-f01-f07-s3b-real-evidence-regression-implementation-codex.md` — 作为只读参考，不纳入 finding 证据链
- **Parallel review coverage:** 无（单路独立审查）

## Findings

### 1-未修复-高-TCSANOW 安装与 reader thread 启动之间的 prestart 输入窗口无 owner

- **入口/函数:** `TtyRunningKeyMonitor.start()` → `_read_loop` background thread
- **文件(行号):** `dayu/cli/run_keys.py:171` (TCSANOW setcbreak) — `dayu/cli/run_keys.py:187` (thread.start)
- **输入场景:** `tty.setcbreak(fd, when=termios.TCSANOW)` 在行 171 执行成功后，终端已切换至 cbreak 模式（单字节、无 echo、无 line buffering）。但 background reader thread 要等到行 187 `thread.start()` 才真正开始 `os.read(fd)` 消费字节。如果 OS 在这 16 行同步 Python 代码窗口内 deliver 新输入字节到 slave PTY，它们会进入 kernel tty buffer，在 cbreak 模式下排队，但无人读取。
- **实际分支:** 行 171 `setcbreak` 成功 → 行 166-186 同步创建 Thread 对象并赋值 `self._thread` / `self._loop` / `self._started` → 行 187 `thread.start()` → 读者线程进入 `_read_loop`。窗口内到达的字节在 `thread.start()` 之后才会被 `_read_loop` 的第一个 `select` + `os.read` 消费。
- **预期行为:** 输入字节应被保留并随后由 reader thread 消费；当前实现依赖 kernel tty buffer 在 cbreak 模式下缓存这些字节，这在 Darwin/Linux 的典型 PTY 实现中成立（kernel 维护上限至少 4096 字节的 input queue）。
- **实际行为:** 当前实现在此窗口内不会丢字节——`TCSANOW` 不清空队列，且 reader thread 启动后会立即 `select` 读取已在队列中的字节。但在极端场景（PTY slave kernel buffer 满 + 窗口内有大量 burst 输入），超出 kernel buffer 上限的字节会被丢弃。此窗口的实际持续时间取决于 Python 线程创建开销，通常在 μs~低 ms 级别。
- **直接证据:** diff 只改了一行（`tty.setcbreak(fd, when=termios.TCSANOW)`），窗口始终存在（`setcbreak` 必须先于 `thread.start()`，否则 reader 会在 cooked mode 下读到行缓冲数据）。行 188-195 的 `except RuntimeError` 正确处理了 thread start 失败，但没有缩短窗口本身。
- **影响:** 仅在极端 burst + 慢线程创建场景下可能丢 prestart 字节。对典型 CLI 交互（单次 Escape、单次 Ctrl+C、少量 type-ahead）无实际影响。Severity 定为"高"是因为这是 correctness 边界——不能在 review 中证明"绝对不会丢"，只能说明"在典型条件下不会丢"。
- **建议改法和验证点:** 无明显无副作用缩短方案（不能在 `setcbreak` 前启动 thread，因为 cooked mode read 会行缓冲；不能把 `setcbreak` 推迟到 thread start 之后，因为 cooked→cbreak 切换本身也有竞态）。建议在 docstring 或模块注释中明确记录此窗口的存在与 kernel buffer 假设，并将此作为已知设计边界。验证：用极高 burst rate（>4096 bytes/μs）的 PTY master 写入做 stress test。
- **修复风险（低）:** 仅增加文档说明，不改变行为。
- **严重程度（高）:** correctness 边界——无法从代码逻辑证明零丢字节，只能从 kernel buffer 容量论证。

### 2-未修复-高-`_drive_interactive_tty_repl` 在 terminal 已观察但 `current = None` 提交前收到 SIGINT 创建孤儿 cancel task

- **入口/函数:** `_drive_interactive_tty_repl` → `_request_interactive_cancel` → `_ActiveTurnCloseout.request_cancel`
- **文件(行号):** `dayu/cli/session_execution.py:1942` (`wait_closeout`) → `dayu/cli/session_execution.py:1956` (`current = None`) → `dayu/cli/session_execution.py:288-293` (`request_cancel`)
- **输入场景:** Turn 正常完成（`submit_task` terminal 到达，无用户取消），`wait_closeout()` 返回 terminal 后 `closeout.intent` 仍为 `NONE`。在行 1942 `wait_closeout()` 返回与行 1956 `current = None` 之间（中间有 `terminal_exit_code` 赋值、`EXIT_AFTER_CANCEL` 检查、`submit_task` 回收），如果 SIGINT 到达，`sigint_task` handler 会检查 `current is not None`（仍为 True），调用 `_request_interactive_cancel`，后者在 `closeout.intent is NONE` 时创建新 `cancel_task`。
- **实际分支:** 行 1942 `terminal = await completed.closeout.wait_closeout()` → 行 1943-1955 处理 terminal_exit_code/exit_after_closeout/submit_task 回收 → 在此期间如果 sigint_task 在 done set 中且被先处理（行 1868），进入 active turn 路径（行 1883-1893），调用 `_request_interactive_cancel` → `request_cancel` 创建 `asyncio.create_task(self.wait_accepted_then_cancel())`。
- **预期行为:** Terminal 已观察后不应再创建 cancel task；cancel task 应只在 terminal 尚未到达时创建。
- **实际行为:** `wait_accepted_then_cancel` 内部通过 `terminal_task = asyncio.create_task(self._terminal_observed.wait())` 自愈——因为 `_terminal_observed` 已被 `wait_closeout()` 内的 `observe_terminal` 设置，`terminal_task` 会立即完成，`asyncio.wait` 返回后走行 321-322 的 early return，不会真正向 Host 发送 cancel。**因此这个孤儿 task 不会产生外部可见副作用**——它会快速自愈并返回已有 terminal。
- **直接证据:** 行 1942 `wait_closeout()` 内调用 `_require_terminal()` 确认 terminal 已设置、`_terminal_observed` 已 set。行 288-293 只在 `intent is NONE` 时创建 task，不检查 terminal 是否已观察。行 299-331 的 `wait_accepted_then_cancel` 通过 `terminal_task` 自愈。
- **影响:** 短暂创建一个立即自愈的 asyncio task（约 1-2 个事件循环 tick），不产生 Host cancel 请求、不改变退出码、不泄漏资源。仅在 `current = None` 前的极窄窗口（相邻 Python 语句间）可能触发。Severity 定为"高"是因为状态机推进权问题——cancel task 的创建决策应由 terminal 已观察这一事实驱动，而非事后自愈。
- **建议改法和验证点:** 在 `_request_interactive_cancel` 或 `request_cancel` 中，增加 terminal 已观察的 early return：检查 `closeout._terminal_observed.is_set()`，若已设置则跳过 cancel task 创建。或在行 1942 之后立即设置 `current = None`，缩窄窗口。
- **修复风险（低）:** 增加 terminal guard 是纯约束收紧，不改变已有正确路径行为。
- **严重程度（高）:** 状态机推进权依赖事后自愈而非事前 guard；窗口极窄但有理论可达路径。

### 3-未修复-中-`sigint_monitor.close()` 未被 cancellation shield 保护

- **入口/函数:** `execute_interactive_on_session` → `sigint_monitor.close()`
- **文件(行号):** `dayu/cli/session_execution.py:838`
- **输入场景:** `execute_interactive_on_session` 在 `except BaseException` 捕获 primary_error 后进入 cleanup 阶段。如果 primary_error 触发时外层 task 已被 cancel（例如 `asyncio.wait_for` 超时），cleanup 阶段运行的 coroutine 仍可能收到 `CancelledError`。行 838 `sigint_monitor.close()` 未被 `asyncio.shield` 包裹。
- **实际分支:** 行 834-835 捕获 primary_error → 行 837-840 try/except 调用 `sigint_monitor.close()` → 如果此时 `CancelledError` 被抛出（外层 task cancel），`close()` 被中断，`_installation_mode` 可能仍为非 `NONE`，OS SIGINT handler 未恢复为进程原 handler。
- **预期行为:** Cleanup 阶段的 signal handler 恢复应与 attachment close 一样（行 848 `asyncio.shield(attachment_controller.close())`），不受 task cancellation 影响。
- **实际行为:** 关闭中的 `CancelledError` 会被行 839 的 `except BaseException` 捕获并赋值给 `cleanup_error`，所以不会向上传播导致 handler 永久泄漏。但 `close()` 内部的 `remove_signal_handler` + `signal.signal(restore)` 是两步操作——如果 `CancelledError` 在两者之间抛出，第一步可能已执行但第二步未执行。实际上 Python 的 `CancelledError` 只在 `await` 点抛出，而 `close()` 方法是同步的（`remove_signal_handler` 和 `signal.signal` 都是同步调用），所以 `CancelledError` 不会在 `close()` 内部抛出，只会在 `close()` 返回后的下一个 `await` 点抛出。因此这个 finding 的严重程度需要降级。
- **直接证据:** 行 838 `sigint_monitor.close()` — 同步方法，无 `await`。行 848 `await asyncio.shield(attachment_controller.close())` — 异步方法，有 `await`。行 841 `display_error = await _close_runtime_display(runtime_display)` — 异步方法，无 shield。
- **影响:** `close()` 是同步方法，内部无 `await` 点，`CancelledError` 不会在其中抛出。`_close_runtime_display` 是异步的且未被 shield——如果在 display close 期间被 cancel，display executor 可能未被正确关闭。但 display 关闭失败已被行 841-845 的 error 合并逻辑处理。
- **建议改法和验证点:** 为 `_close_runtime_display` 增加 `asyncio.shield`，与 `attachment_controller.close()` 保持一致。`sigint_monitor.close()` 同步方法不需要 shield。验证：构造 display close 期间的 cancel 场景。
- **修复风险（低）:** shield 是纯保护性增强。
- **严重程度（中）:** `sigint_monitor.close()` 本身无实际风险（同步方法），但 `_close_runtime_display` 有同等 gap。

### 4-未修复-中-`_pending_submit_intent` 的空白 draft 边界：纯空白 Enter 被视为"无 intent"

- **入口/函数:** `PromptToolkitInteractiveComposer._record_submit_intent`
- **文件(行号):** `dayu/cli/composer.py:459`
- **输入场景:** 用户输入纯空白（空格、制表符）后按 Enter。`_record_submit_intent` 计算 `draft.strip() != ""` → `False`，所以 `_pending_submit_intent = False`。此时如果紧随 Enter 的 SIGINT 到达，`has_pending_submit_intent()` 返回 `False`，driver 进入 idle exit 路径而非绑定到随后创建的 turn。
- **实际分支:** 行 459 `self._pending_submit_intent = draft.strip() != ""` — 空白 draft → `False`。行 1874-1877 sigint handler → `has_pending_submit_intent()` → `False` → 走 `exit_intent = IDLE_EXIT_PENDING`。随后 composer_task 交付 SUBMIT（`draft.strip() == ""` → `user_prompt == ""`），行 1749-1751 执行 `pending_mutation = None; composer.accept_submit(record_history=False)`，行 1744 重置 `exit_intent = CONTINUE`。所以 SIGINT 被"浪费"在 idle exit pending 上，随后被 Enter 覆盖。
- **预期行为:** 对于空白 Enter + 紧随 SIGINT，直觉上 SIGINT 应触发 idle exit（因为用户没有提交有效内容），当前行为符合预期。
- **实际行为:** 空白 Enter 没有业务语义（不会创建 Run），SIGINT 走 idle exit 路径是正确的。此 finding 更多是语义澄清而非缺陷。
- **直接证据:** 行 459 `draft.strip() != ""` → 空白 draft → `False`。行 1874 的 `has_pending_submit_intent()` 检查。行 1744 `exit_intent = CONTINUE` 覆盖 idle exit pending。
- **影响:** 无实际用户可观测的异常行为。空白 Enter + SIGINT 的交互符合直觉。
- **建议改法和验证点:** 无需修改。建议在 `_record_submit_intent` 的 docstring 中明确"纯空白不被视为 submit intent"的语义。
- **修复风险（低）:** 仅文档说明。
- **严重程度（中）:** 语义边界——非缺陷但值得显式化。

### 5-未修复-低-`TtyRunningKeyMonitor.close()` 的 thread join 超时后线程可能继续访问已恢复的 terminal fd

- **入口/函数:** `TtyRunningKeyMonitor.close()` → `_read_loop` daemon thread
- **文件(行号):** `dayu/cli/run_keys.py:218-225`
- **输入场景:** `close()` 调用 `_stop_event.set()` 后 join reader thread，超时 0.2 秒。如果 reader thread 正阻塞在 `os.read(fd, ...)` 中（等待用户输入），`select` 已返回 readable 但 `os.read` 尚未返回，join 超时后行 220-221 恢复 termios 原属性。此时 reader thread 可能仍在 `os.read` 中（使用已恢复的 cooked mode），读到的数据可能不完整或语义不同。
- **实际分支:** 行 216 `_stop_event.set()` → 行 218-219 `thread.join(timeout=0.2)` → 超时 → 行 220-221 `_restore_terminal_attrs(fd, original_attrs)` → 返回。Reader thread 在下一次循环迭代的行 253 `select(...)` 会检查行 261 `self._stop_event.is_set()` 并退出。
- **预期行为:** Thread 在 terminal 恢复后不再读取新数据，或读到的数据被安全丢弃。
- **实际行为:** Reader thread 在 terminal 恢复与 `_stop_event` 检查之间最多执行一次 `select` + 可能的 `os.read`。`os.read` 最多读 1024 bytes，这些 bytes 会被 `_publish_actions` 投递到 `_queue`，但 `_queue` 已无消费者（`wait_next` 不会再被调用）。这是安全的——数据被丢弃但不会导致 crash 或状态污染。Thread 是 daemon，进程退出时自动清理。
- **直接证据:** 行 218-219 `thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)` — 0.2 秒超时。行 264-269 `os.read(fd, _READ_SIZE_BYTES)` — 每次最多 1024 bytes。
- **影响:** 极低。仅在 prompt one-shot 正常退出 + 用户恰好在退出时刻敲击键盘时可能读取并丢弃一些字节。不影响正确性。
- **建议改法和验证点:** 可考虑在 terminal restore 后增加一次 `_stop_event.wait(0.05)` 或轮询 `thread.is_alive()`，但投入产出比不高。当前实现已足够健壮。
- **修复风险（低）:** 增加额外等待可能略微延长 close 时间。
- **严重程度（低）:** daemon thread 安全丢弃，无资源泄漏，无状态污染。

### 6-未修复-低-`_drive_interactive_tty_repl` 的 `pending_submit_sigint_count` drain 与 sigint_task handler 之间存在重复消费窗口

- **入口/函数:** `_drive_interactive_tty_repl` → `pending_submit_sigint_count` drain → sigint handler
- **文件(行号):** `dayu/cli/session_execution.py:1833-1849` (drain) → `dayu/cli/session_execution.py:1868-1896` (sigint handler)
- **输入场景:** drain 在行 1833-1849 消耗 `pending_submit_sigint_count` 并重置为 0。在 drain 完成到下一次 `asyncio.wait` 之间，如果新 SIGINT 到达且 `has_pending_submit_intent()` 仍然为 True（因为 `accept_submit` 尚未被调用），新的 `pending_submit_sigint_count` 会在行 1874-1877 再次递增。下一次迭代的 drain（行 1833）会再次将其绑定到仍为 `current` 的同一 turn。
- **实际分支:** 第一次 drain 将 pending count 绑定到刚创建的 current → reset 为 0。新 SIGINT → `has_pending_submit_intent()` 仍 True → `pending_submit_sigint_count += 1`。下一次迭代 drain 再次绑定同一 turn。
- **预期行为:** 第二次 drain 对同一 turn 再次调用 `_request_interactive_cancel`。此时 `closeout.intent` 已非 `NONE`（第一次 drain 已设置），所以 `request_cancel` 只更新 `exit_after` 标志（行 295-297），不创建新 cancel task。这是正确的。
- **实际行为:** 行为正确，但同一信号被处理两次——第一次通过 drain，第二次通过 sigint handler → drain。由于 `request_cancel` 的幂等设计，第二次是安全 no-op。但仍浪费了一个 `asyncio.wait` 迭代。
- **直接证据:** 行 1834-1849 drain 创建 cancel 并 reset count → 行 1874-1877 可能再次递增 → 下一轮循环行 1833 再次 drain。行 295-297 幂等 guard 防止重复 cancel task。
- **影响:** 极低。至多多一次 `asyncio.wait` 循环和一次安全 no-op `request_cancel` 调用。
- **建议改法和验证点:** 无需修改。当前幂等设计已正确处理。
- **修复风险（低）:** N/A。
- **严重程度（低）:** 无外部可见错误，仅理论效率边界。

## Open Questions

1. **`_restore_terminal_attrs` 使用 `TCSANOW` 恢复原始终端属性是否正确？** 使用 `TCSANOW` 意味着恢复时不清空队列，保留了 Dayu 退出后可能残留的已到达但未消费字节。这对用户（shell 会读取它们）是正确的行为。但如果这些字节是 Dayu 内部协议的一部分（如 ESC 序列），可能会污染 shell 的输入。当前场景下（prompt one-shot 退出），这种情况不太可能发生，但值得确认。

2. **`CliSigintMonitor.install()` 幂等 guard 是否应考虑 loop 变化？** 当前 guard 检查 `_installation_mode is not NONE` 就返回。如果 `install()` 在 loop A 中调用，然后事件循环被销毁并创建 loop B（在 asyncio 3.11 中可能但罕见），`install()` 会错误地认为 handler 已安装而跳过。当前 prompt/interactive 的 usage pattern 都在同一事件循环中，但 guard 的语义是"已安装"而非"已在当前 loop 安装"。

## Residual Risk

1. **测试未覆盖真实 OS 信号竞态。** `_ManualSigintMonitor.notify()` 和 `_PendingSubmitBarrierComposer` 在受控 asyncio 调度点注入信号，而非真实 OS 级别的异步信号投递。真实 OS SIGINT 可能在 Python 字节码解释器的任意点触发（包括 `_record_submit_intent` 内部的 `draft.strip()` 调用期间、`_exit_with_composer_event` 内部的 buffer 读取期间等）。这些点的行为取决于 CPython 的信号处理实现（信号在"安全点"被处理，通常在下一条 Python 字节码之前），但测试未覆盖。Mimo PTY 手动验证提供了两个场景的证据（prompt pre-accept Escape、interactive pre-accept double SIGINT），但未覆盖全部 F01-F07 矩阵组合。

2. **PTY prestart 测试仅覆盖 POSIX。** `test_tty_running_key_monitor_preserves_prestart_standalone_escape` 和 `test_tty_running_key_monitor_preserves_prestart_complete_sequences` 均标记 `@pytest.mark.skipif(os.name != "posix", ...)`。Windows/non-POSIX 平台的 prestart 输入行为完全未测试——在 Windows 上 `TtyRunningKeyMonitor.start()` 会因 `_POSIX_TERMINAL_CONTROL_AVAILABLE = False` 直接返回 no-op，此时 prestart 输入由 `NoopRunningKeyMonitor` 处理（永不产生 cancel 动作）。这是设计决定的平台差异，但 residual risk 是：如果未来在 Windows 上需要 prestart Escape 支持，需要完全不同的实现路径。

3. **`_pending_submit_intent` 和 `_pending_submit` 两个 flag 之间的不一致窗口。** 在 `read_event` 的行 388-392（处理 stale pending submit）中，`_pending_submit_intent` 与 `_pending_submit` 同步清除。但在 `_exit_with_composer_event` 的 SUBMIT 路径（行 406-409）中，只设置 `_pending_submit = True`，不设置 `_pending_submit_intent`——后者依赖 Enter callback 已调用 `_record_submit_intent`。如果通过其他路径（如非 Enter 的某种 prompt_toolkit 内部机制）产生 SUBMIT，`_pending_submit_intent` 可能为 False 而 `_pending_submit` 为 True。当前所有 SUBMIT 路径都经过 `_submit_or_insert_xterm_shift_enter`（Enter 回调），所以不存在此问题。但这是隐式假设，值得在代码中显式化。

4. **`key_monitor` 在 prompt 路径中被 `execute_prompt_on_session` 的默认参数覆盖。** 行 678（diff 中的 line 295）`key_monitor=(new_running_key_monitor() if key_monitor is None else key_monitor)` 在 `key_monitor` 为 `None` 时创建新 monitor。但如果调用方传入的 `key_monitor` 是已 close 的实例，这里不会检测。当前 prompt 路径保证调用方传入的 monitor 在 `execute_prompt_on_session` 生命周期内始终存活（由外层的 `finally: key_monitor.close()` 保证），所以不存在此问题。但如果未来有新的调用方，这是一个潜在 footgun。
