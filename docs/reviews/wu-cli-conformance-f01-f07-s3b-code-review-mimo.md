# S3B Real-evidence Regression Code Review — Mimo

## Scope

- **Mode:** PR 190 S3B real-evidence regression slice (working-tree changes vs eae09be97963382c49fbf71195820637a4baa948)
- **Branch:** `codex/interactive-oracle`
- **Base:** `eae09be97963382c49fbf71195820637a4baa948`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3b-code-review-mimo.md`
- **Included scope:**
  - `dayu/cli/agent_entrypoint.py`
  - `dayu/cli/commands/prompt.py`
  - `dayu/cli/composer.py`
  - `dayu/cli/run_keys.py`
  - `dayu/cli/session_execution.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/cli/test_interactive_composer.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_run_keys.py`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3b-real-evidence-regression-implementation-codex.md`
- **Excluded scope:** 四份 README 与 S8 artifact 是既有保留基线，不在本次 S3B diff 范围内。
- **Parallel review coverage:** 无。

## Verification

- **pyright:** `0 errors, 0 warnings, 0 informations` ✅
- **pytest:** `204 passed, 3 warnings` (warnings 均为第三方 deprecation) ✅
- **git diff --check:** pass ✅
- **staged diff:** empty ✅

## Findings

### 1-未修复-中-READ_ONLY rejection 后 `_pending_submit_intent` 未清除，导致后续 SIGINT 错误绑定下一次 Run

- **入口/函数:** `_drive_interactive_tty_repl` @ `session_execution.py:1912-1928`
- **文件(行号):** `composer.py:458-459` (`_record_submit_intent`), `session_execution.py:1912-1928` (READ_ONLY rejection path), `session_execution.py:1875-1877` (SIGINT binding)
- **输入场景:** 用户在 interactive TTY 模式下提交非空 prompt，Host 返回 READ_ONLY attachment rejection；随后用户再次提交并触发 SIGINT。
- **实际分支:** `_is_read_only_mutation_rejection(error)` 为 `True`，代码进入 `session_execution.py:1914-1928` 的 READ_ONLY 处理路径。`current` 设为 `None`，`set_phase(IDLE)`，但 `_pending_submit_intent` 保持 `True`。
- **预期行为:** READ_ONLY rejection 后 submit 语义已终结，composer 的 `_pending_submit_intent` 应重置为 `False`。后续 idle SIGINT 应走 `IDLE_EXIT_PENDING` 分支（double Ctrl+C 退出），不应绑定到尚未创建的下一次 Run。
- **实际行为:** READ_ONLY path 不重置 `_pending_submit_intent`。用户再次提交非空 prompt 后、Run accepted 前到达的 SIGINT 走 `session_execution.py:1875` 的 `has_pending_submit_intent()` 分支，被缓冲到 `pending_submit_sigint_count`。新 SUBMIT 创建 turn 后 drain 该 SIGINT 并请求 Host cancel（`session_execution.py:1840-1846`），可能取消用户主动发起的下一次 Run。
- **直接证据:**
  - `composer.py:458-459`: `_record_submit_intent` 设置 `_pending_submit_intent = draft.strip() != ""`
  - `composer.py:362-369`: `accept_submit` 是唯一清除 `_pending_submit_intent = False` 的路径
  - `session_execution.py:1912-1928`: READ_ONLY path 调用 `set_phase(IDLE)` 但不重置 `_pending_submit_intent`
  - `session_execution.py:1875-1877`: `if composer.has_pending_submit_intent(): pending_submit_sigint_count += 1; continue`——stale intent 导致 SIGINT 被错误缓冲
  - `session_execution.py:1837-1849`: drain 循环对新 turn 发起 `_request_interactive_cancel`
- **影响:** correctness 风险。READ_ONLY rejection 残留的 stale `_pending_submit_intent` 会使用户下一次提交后的 SIGINT（可能是前一个 turn 的残留或用户有意中断新 turn 前的操作）被错误绑定到新 turn 并请求 Host cancel，取消用户主动发起的 Run。这不是"多走一个 SIGINT 周期"的偏差，而是 SIGINT 语义被错误归属到错误 turn 的 correctness 缺陷。
- **建议改法和验证点:** 在 composer owner 中新增 typed 方法（如 `clear_pending_submit_intent()`），只结束 pending-delivery intent 状态，不触碰 `_draft`、`_cursor_position`、`_input_revision` 或 `_pending_submit`。READ_ONLY rejection path 在 `set_phase(IDLE)` 前调用该方法。禁止调用 `accept_submit(record_history=False)`，因为它会清空 `_draft` 和 `_cursor_position`（`composer.py:365-368`），违反 frozen F04 保留 exact draft/cursor/revision 的 contract。验证：补充测试覆盖 READ_ONLY rejection → 用户再次提交 → accepted 前 SIGINT 不应取消新 Run。
- **修复风险（低/中/高）:** 低
- **严重程度（低/中/高/严重）:** 中

## 按审查维度逐项结论

### 1. Prompt monitor 在 runtime/Host 前 install/start

**结论: ✅ 无问题**

`prompt.py:105-110` 在 `_run_prompt_command_async` 入口处：
```
sigint_monitor = CliSigintMonitor()
key_monitor = new_running_key_monitor()
sigint_monitor.install()
try:
    key_monitor.start()
    ...
```
SIGINT monitor.install() 在 line 107，key_monitor.start() 在 line 110，均在 `prepare_prompt_session_execution`（line 112）和 `open_host`（line 124）之前。异常路径（`key_monitor.start()` 失败）的 finally 块正确恢复两个 monitor。

### 2. prepare/open/attach/start/normal/exception 各路径唯一 close/handler/termios 恢复

**结论: ✅ 无问题**

- **prompt 命令:** `prompt.py:139-142` 嵌套 finally 确保 `key_monitor.close()` 和 `sigint_monitor.close()` 在所有路径执行。
- **interactive 命令:** `session_execution.py:836-858` 在 `BaseException` 后执行 `sigint_monitor.close()` → `_close_runtime_display` → `attachment_controller.close()`，顺序正确。
- **TtyRunningKeyMonitor:** `run_keys.py:206-226` 的 `close()` 恢复 `termios.tcsetattr(fd, TCSANOW, attrs)`，且 `_started` flag 防止重复 close。
- **TtyRunningKeyMonitor.start() 失败:** `run_keys.py:166-195` 在 `OSError/ValueError/termios.error` 时立即 `_restore_terminal_attrs`，在线程启动失败时同样恢复。

### 3. 把 observed SIGINT 从 0 消费是否会重放非本 turn 信号

**结论: ✅ 无问题**

- `_submit_prompt_turn_handling_sigint` (`session_execution.py:1224`) 从 `observed_sigint_count = 0` 开始。这是正确的：monitor 属于当前 invocation，从 0 消费确保 durable count 只作用于同一 accepted Run。
- `_drive_interactive_tty_repl` (`session_execution.py:1705`) 从 `observed_sigint_count = sigint_monitor.count` 开始，跨 turn 累积。turn 完成后 `active_sigint_count` 重置为 0，`observed_sigint_count` 不重置。`wait_next(observed_sigint_count)` 只在 `count > observed_count` 时返回，不会重放已消费信号。

### 4. TCSANOW 保留 prestart ESC 且不误分类 Alt+X、CSI/Home/Delete、bracketed paste

**结论: ✅ 无问题**

- `run_keys.py:171`: `tty.setcbreak(fd, when=termios.TCSANOW)` 替代默认 `TCSAFLUSH`，保留 prestart input。
- `run_keys.py:388-415`: `_classify_running_key_batch` 只在 `is_ambiguity_flush=True` 且 `len(batch)==1` 且 `standalone.key is Keys.Escape` 且 `standalone.data == "\x1b"` 时产生 `CANCEL_RUN`。Alt+X（`"\x1bx"` 同 batch）、CSI（`"\x1b[A"`）、Home/Delete、bracketed paste 均为完整序列，不满足 flush+单 member 条件。
- 测试覆盖：`test_run_keys.py:413-444` 参数化覆盖 CSI、Alt、Home/Delete、bracketed paste、Ctrl+C；`test_run_keys.py:676-741` 真实 PTY 测试覆盖 prestart standalone Escape 和完整序列。

### 5. InteractiveComposer.has_pending_submit_intent typed contract 与所有实现

**结论: ✅ 无问题**

- **Protocol 定义:** `composer.py:236-243`，返回 `bool`，docstring 说明"普通 Enter 已提交非空草稿且 REPL 尚未确认时返回 True"。
- **PromptToolkitInteractiveComposer 实现:** `composer.py:371-378` 返回 `self._pending_submit_intent`。
- **_record_submit_intent:** `composer.py:458-459` 设置 `self._pending_submit_intent = draft.strip() != ""`，只对非空白草稿返回 True。
- **accept_submit:** `composer.py:369` 清除 `self._pending_submit_intent = False`。
- **消费方:** `session_execution.py:1875-1877` 用 `has_pending_submit_intent()` 判断是否缓冲 early SIGINT。

### 6. Submit event 未交付时 single/double SIGINT 绑定同一 turn

**结论: ✅ 无问题**

`session_execution.py:1833-1849`: Enter chord 同步设置 `_pending_submit_intent`（`composer.py:458`），但 `prompt_async` 的 typed SUBMIT 可能晚于 SIGINT 被调度。REPL 在 `current is None` 且 `has_pending_submit_intent()` 时缓冲 SIGINT 到 `pending_submit_sigint_count`。SUBMIT 到达创建 turn 后，`session_execution.py:1837-1849` drain 缓冲的 SIGINT 并绑定到该 turn。`_record_submit_intent` 在 prompt_toolkit 的 `c-m` key handler 内同步执行（`composer.py:553`），`signal.raise_signal(signal.SIGINT)` 同步触发（`composer.py:1061`），因此 intent 设置先于 SUBMIT 事件投递。

### 7. Idle double Ctrl+C 不变

**结论: ✅ 无问题**

`session_execution.py:1874-1882`:
- 第一次 idle SIGINT: `current is None` 且 `has_pending_submit_intent()` 为 False → `exit_intent = IDLE_EXIT_PENDING`
- 第二次 idle SIGINT: `exit_intent is IDLE_EXIT_PENDING` → `return EXIT_KEYBOARD_INTERRUPT`

与旧行为一致。新 turn 创建时 `exit_intent = CONTINUE` 重置。

### 8. 空 submit / read-only / submit failure / queued / closeout 不残留 pending count

**结论: ⚠️ READ_ONLY 路径残留 `_pending_submit_intent`（见 Finding #1）**

- **空 submit:** `session_execution.py:1749-1751` → `accept_submit(record_history=False)` 清除 pending ✅
- **READ_ONLY:** `session_execution.py:1912-1928` → `current = None`, `active_sigint_count = 0` ✅；`pending_submit_sigint_count` 由 drain 循环清零 ✅；但 **`_pending_submit_intent` 未重置** ❌ → 后续 SIGINT 错误绑定下一次 Run（Finding #1）
- **Submit failure（非 READ_ONLY）:** 异常传播到 `session_execution.py:834` 的 `BaseException` handler ✅
- **Queued followup:** `session_execution.py:1860-1866` → `accept_submit(record_history=True)` 清除 pending ✅
- **Closeout:** `session_execution.py:1956` → `current = None`, `generation += 1`, `active_sigint_count = 0` ✅

### 9. 第二次不强杀

**结论: ✅ 无问题**

- **prompt:** `session_execution.py:1289` 设置 `exit_after = observed_turn_sigint_count >= 2`，closeout 升级为 `EXIT_AFTER_CANCEL`，但仍等待 Host canonical terminal（`session_execution.py:1301-1312`）。不调用 `task.cancel()` 强杀。
- **interactive:** `session_execution.py:1883-1896` 同样设置 `exit_after_closeout = True` 并取消 composer task，但仍等待 `closeout.wait_closeout()` 获取 Host terminal。

### 10. Host terminal 唯一

**结论: ✅ 无问题**

- `_ActiveTurnCloseout.observe_terminal` (`session_execution.py:333-349`): 首次设置 `_terminal` 并 `_terminal_observed.set()`；重复调用若结果冲突则 `raise ValueError("terminal result conflicts with canonical terminal")`。
- `_ActiveTurnCloseout.wait_closeout` (`session_execution.py:351-363`): 等待 `_terminal_observed` 然后 `_require_terminal()` 确保 terminal 唯一。

### 11. PENDIN 判定不掩盖真实模式泄漏

**结论: ✅ 无问题**

- `run_keys.py:418-432`: `_restore_terminal_attrs` 使用 `TCSANOW` 恢复原始属性。
- 真实 PTY 测试（`test_run_keys.py:651-671`, `test_interactive_composer.py:1136-1194`）断言 `_terminal_lflag_controls` 四项 flags（ECHO/ICANON/ISIG/IEXTEN）完全恢复。
- S3B artifact 指出 full lflag XOR `0x20000000 == termios.PENDIN`，是 kernel pending-input 状态，非 Dayu 安装的 terminal mode。修改它会把 harness/audit 队列状态错误归给产品 owner。

### 12. 真实 Mimo 证据与 204 tests/coverage/artifact 准确性

**结论: ✅ 准确**

- pytest: `204 passed, 3 warnings` ✅
- pyright: `0 errors, 0 warnings, 0 informations` ✅
- S3B artifact 描述的 prompt pre-accept Escape 与 interactive pre-accept double SIGINT 两条 lane 证据与代码实现一致。
- S3B artifact 的 `READY-FOR-DUAL-S3B-CODE-REVIEW` 状态准确：实现已完成，待双路 code review。

### 13. 无 God helper / semantic ownership drift / compat shim

**结论: ✅ 无问题**

- `CliSigintMonitor` 是 SIGINT 观察器，不持有 business state。
- `PromptToolkitInteractiveComposer` 是 interactive TTY 输入唯一 owner，不泄漏 prompt_toolkit 类型。
- `_ActiveTurnCloseout` 是 acceptance/cancel/terminal coordinator，不持有 composer/display/cursor。
- `_InteractiveSessionAttachmentController` 是 attachment 生命周期 controller，不推断 mode。
- `TtyRunningKeyMonitor` 是 TTY 按键监听器，不访问 Host/Service。
- 无 `hasattr/getattr` 滥用，无兼容 shim，无 fallback 分支。

## Open Questions

无。

## Residual Risk

- Coverage 工具在当前环境下无法正确报告单文件覆盖率（namespace package 导入问题），但 204 测试全部通过且 pyright 0 errors。
- 独立 Authorization 持久化 residual 未处理，仍由原 owner/work unit 承担。
- READ_ONLY rejection 后 `_pending_submit_intent` 未清除（Finding #1）是 correctness 缺陷：stale intent 会使后续 SIGINT 错误取消用户主动发起的 Run。修复在 composer owner 层新增只清除 intent 的 typed 方法，不触碰 draft/cursor/revision。

## Conclusion

S3B real-evidence regression 实现的 12 个审查维度中 11 个通过，1 个（维度 8 READ_ONLY 路径）存在 correctness 缺陷（Finding #1）。核心修复（prompt monitor 前置、TCSANOW 保留 prestart input、interactive pending submit intent、SIGINT 从 0 消费）实现正确，测试覆盖充分，无 semantic ownership drift 或 compat shim。Finding #1 需在 composer owner 层新增只清除 pending-delivery intent 的 typed 方法修复，不得调用 `accept_submit` 以避免违反 F04 draft 保留 contract。
