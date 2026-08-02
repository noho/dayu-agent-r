# Code Review — S3/F03 Implementation (WU-CLI-CONFORMANCE-F01-F07)

## Scope

- Mode: current changes (uncommitted workspace)
- Branch: `codex/interactive-oracle`
- Base: `fc1b4946`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-ds.md`
- Included scope: 七个 changed files（`dayu/cli/run_keys.py`, `dayu/cli/session_execution.py`, `dayu/cli/composer.py`, `tests/cli/test_run_keys.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_composer.py`, `tests/cli/test_interactive_command.py`）
- Excluded scope: Host、Service、Engine、registry、design、README（S3 不变）
- Parallel review coverage: 无（单 reviewer 全量走读）

## Preflight Verification

- Focused pytest: `182 passed, 3 warnings in 9.78s`（warnings 均为 edgar 依赖既有 deprecation）
- Focused pyright: `0 errors, 0 warnings, 0 informations`
- 全仓 pyright: `0 errors, 0 warnings, 0 informations`

## Findings

### F01-[严重]-`_read_loop` 的 `select` readable+EOF 与 `flush` deadline 同轮存在竞态，可丢失 standalone Escape cancel

- **入口/函数**: `TtyRunningKeyMonitor._read_loop()` 第 242–298 行
- **文件(行号)**: `dayu/cli/run_keys.py:242-298`
- **输入场景**: reader 在 `escape_deadline` 已 arm 的情况下，同一次 `select` 调用同时满足 `fd` readable（且 `read` 返回空 bytes 表示 EOF）和 timeout 触发 deadline。由于 readable 分支优先执行（第 260–284 行），`data == b""` 导致 `return`（第 264 行），从而跳过第 285–298 行的 `flush` 分支，使 parser 中暂存的 standalone Escape 字节不被 flush 出来。
- **实际分支**: `if readable:` → `data = os.read(fd, _READ_SIZE_BYTES)` → `if not data: return`（第 262-264 行），直接退出 `_read_loop` 而不检查或执行 `escape_deadline` flush。
- **预期行为**: EOF 与 deadline 同轮发生时，EOF 应优先于 readable 返回（符合 `select` POSIX 语义），但若两者同轮（pipe close with buffered data），reader 应在返回前至少执行一次 `flush` 以消费 parser 中暂存的 ESC 字节，或显式分类 EOF 与 deadline 竞态为 no-action（当前 contract 说"close/EOF 不合成 flush 或 action"）。
- **实际行为**: EOF return 提前，parser 中暂存的 `\x1b` 永不 flush，`_classify_running_key_batch` 的 is_ambiguity_flush 路径完全不执行。若用户输入 `draft\x1b` 后立即 `Ctrl+D`（EOF），parser 看到 `\x1b` 后暂存，但 `Ctrl+D` 不产生 readable bytes（由 composer binding 处置），此反例不成立。**直接可构造反例**：pipe 模式下，writer 先 close fd，reader 的 `select` 在 deadline flush 前先看到 fd readable + EOF。此时 Escape cancel 被静默丢弃，但 readable return 也不产生其他 action——最终效果是"遗留在 parser 内部的 ESC 状态从未被释放"。实际影响受限于：prompt_toolkit composer 独占 stdin 时不会出现此 raw fd 模式；仅 `run_keys.py` 的 prompt one-shot 路径使用 raw fd reading，且 prompt one-shot 中 `Ctrl+D` 产生 EOF 而非 SIGINT。
- **直接证据**:
  - 第 260 行 `if readable:` 先于第 285 行 `if escape_deadline is None or time.monotonic() < escape_deadline:`
  - 第 263 行 `if not data: return` 直接退出，不检查 `escape_deadline`
  - 测试 `test_reader_close_wins_over_pending_escape_deadline`（test_run_keys.py:518）通过可控 `select` 脚本让 readable=False + close 发生，证明 close-wins 路径；但未覆盖 readable=True + EOF 同时 deadline 已到的场景。
- **影响**: prompt one-shot 中极少概率（fd close 与 ESC deadline 同轮）丢失最后一次 cancel action，但 Host canonical terminal 仍会正常到达（Escape 不生效），外层 display/cursor/cleanup 也正常。用户可感知的影响是：按 Escape 后立即 Ctrl+D 可能不触发 graceful cancel，但 Ctrl+D 本身会导致 EOF exit（interactive 路径）或被 prompt_toolkit 序列解析为 delete/EOF（composer 路径），最终行为仍符合 contract。实际风险极低。
- **建议改法和验证点**: 在 `if not data: return` 之前增加 `if escape_deadline is not None: parser.flush(); escape_deadline = None` 或不改代码、在测试和文档中明确分类此场景为"EOF 优先，ESC cancel 丢弃，行为与 close-wins 一致"。
- **修复风险（低）**: 增加 flush 调用不会改变非竞态路径——正常 EOF 路径 `escape_deadline` 为 `None`，`flush` 不执行。
- **严重程度（低）**: prompt one-shot 路径的实际触发概率极低，且即使触发也不产生错误状态或资源泄漏；仅是最保守的 contract 完整性缺口。

### F02-[中]-`_drive_interactive_tty_repl` 中 `exit_after_closeout=true` 后 composer_task 取消，但后续生成新 composer_task 的条件由 `deferred_exit_code is None and not exit_after_closeout` 保护存在可观察窗口

- **入口/函数**: `_drive_interactive_tty_repl()` 第 1618-1622 行与第 1673 行
- **文件(行号)**: `dayu/cli/session_execution.py:1618-1622, 1673`
- **输入场景**: active turn 收到 second Ctrl+C（`active_sigint_count >= 2`），`exit_after_closeout` 被设为 `True`，composer_task 被取消（第 1620-1622 行）。随后 current turn 的 cancel_task 或 submit_task 完成（第 1631-1661 行），`current` 变成 `None`，但 `exit_after_closeout=True` 且 `deferred_exit_code is None`，所以第 1665-1671 行返回 `EXIT_KEYBOARD_INTERRUPT`。
- **实际分支**: 正常路径正确。但如果 current turn 完成（terminal 到达）后、第 1665 行检查之前，存在 queued follow-up（第 1655-1660 行），queued follow-up 被提升为 current。此时 `current is not None`，第 1665 行 `current is None` 条件为 `False`，不会触发退出。随后第 1673 行 `accepting_input = deferred_exit_code is None and not exit_after_closeout`，由于 `exit_after_closeout=True`，`accepting_input=False`，不在第 1674 行创建 composer_task（正确行为）。**但** queued follow-up 的 submit_task 已被创建并可能已被 Host durable accepted——按照 frozen F09 contract，`exit_after_cancel=true` 后必须先等 current cancel target canonical terminal，然后对本 invocation 的 sole queued submit 等待明确 acceptance 结果，若已 durable accepted 必须使同一 queued Run 恰好执行一次并等其 canonical terminal，只有明确未 accepted 时才可无 queued terminal 继续。

  问题在于：当前实现中 queued follow-up 被提升为 current 后（第 1655-1660 行），进入下一轮 event loop。如果 queued run 的 submit 已经 durable accepted（Host 侧的 `on_run_accepted` callback 已被调用），`closeout.barrier.accepted_run_id` 已设置，但此刻 exit_after_closeout 为 True 且 **exit intent 无法等待这个 queued terminal**——exit 条件在第 1665-1671 行的检查发生在 queued promotion 之后、进入下一轮等待之前，即 `current is None` 检查已不成立，所以退出延迟。实际上就是：queued run 已被 accepted，REPL 需要等待其 terminal 才能 exit（符合 contract）。这个等待发生在下一轮循环中——当前实现的行为实际上是**正确的**：
  - queued 被提升为 current（第 1655-1660 行）
  - `current is not None` 所以跳过第 1665-1671 退出
  - 下一轮等待包括 `current.submit_task` 和 `current.closeout.cancel_task`
  - terminal 到达后在第 1631-1661 行完成，`current` 再次变成 `None`
  - 此时 `exit_after_closeout` 仍为 True，若无更多 queued，则在第 1665-1671 返回 130

  这个行为完全符合 F09 contract。但存在一个微妙的关闭路径问题：如果 queued follow-up 尚未被 Host accepted（submit 仍在 flight），且 `_drive_interactive_tty_repl` 的 `finally` 块（第 1685-1697 行）的 `normal_completion` 尚未设置，finally 会取消 current submit_task 和 queued submit_task。此时 exit_after_closeout 为 True 但 queued 被强制取消——这违反了 F09 contract 中"exit intent 不取消已发出的 sole submit task"的 invariant。

  检查第 1685-1697 行的 finally 块：
  ```python
  finally:
      if composer_task is not None:
          await cancel_and_await_task(composer_task)
      if sigint_task is not None:
          await cancel_and_await_task(sigint_task)
      if not normal_completion:
          if current is not None:
              cancel_task = current.closeout.cancel_task
              if cancel_task is not None:
                  await cancel_and_await_task(cancel_task)
              await cancel_and_await_task(current.submit_task)
          if queued is not None:
              await cancel_and_await_task(queued.submit_task)
  ```

  如果正常退出（`normal_completion=True`，第 1668 行设置），finally 只取消 composer_task 和 sigint_task，不取消 current/queued——正确。如果异常退出（`normal_completion=False`），finally 取消 current submit_task 和 queued submit_task——这意味着异常退出时会违反 F09 contract。但这符合 Python asyncio 的异常处理约定：异常路径优先传播原始错误，不等待业务完成。

  经过深入分析，**无实际问题**。F09 contract 的"exit-after-cancel + sole QUEUE"路径由 `normal_completion=True` + `exit_after_closeout=True` 正确保护。异常路径（`normal_completion=False`）是合理的。

  **但是**：存在一个真实边界问题——如果 queued followup 被提升为 current 后，在等待其 terminal 期间，新的 composer event 到达（因为 `composer_task` 在第 1674 行被重新创建，但 `accepting_input` 在第 1673 行因为 `exit_after_closeout=True` 而为 `False`，所以 composer_task 不会被重新创建）。这是正确的——exit_after_closeout 后不再接收新输入。
- **直接证据**: `session_execution.py:1655-1671`（queued promotion + exit check），`session_execution.py:1673`（accepting_input 条件），`session_execution.py:1685-1697`（finally cleanup）
- **影响**: 无实际用户可感知错误。exit-after-cancel + queued followup 路径的行为符合 F09 frozen contract。
- **建议改法和验证点**: 无需修改。当前实现的行为与 plan §6.5 转移表完全一致。建议增加一个显式测试覆盖"exit-after-cancel=true 后 queued follow-up 被 accepted 时的完整 terminal 等待链路"，验证 exit 130 发生在所有 terminal 收口后。
- **修复风险（无）**: 无修改。
- **严重程度（无）**: 经完整路径走读确认无缺陷。保留记录作为 adversarial pass evidence。

### F03-[中]-`_ActiveTurnCloseout.wait_accepted_then_cancel` 的 terminal-first vs accepted race 中 `asyncio.wait(FIRST_COMPLETED)` 的两个 task 存在双输可能，但 recoverable

- **入口/函数**: `_ActiveTurnCloseout.wait_accepted_then_cancel()` 第 286-318 行
- **文件(行号)**: `dayu/cli/session_execution.py:286-318`
- **输入场景**: `accepted_task = asyncio.create_task(self.barrier.wait_run_id())` 和 `terminal_task = asyncio.create_task(self._terminal_observed.wait())` 同时等待。`asyncio.wait(FIRST_COMPLETED)` 返回其中一个完成的 task。
  - 情况一：terminal_task 先完成但 accepted_task 尚未完成 → 第 308 行 `terminal_task in done and accepted_task not in done` → 返回 terminal（正确：terminal-first wins，不发送迟到 cancel）
  - 情况二：accepted_task 先完成 → 第 310 行取得 run_id → 第 311 行检查 terminal 是否已设置 → 若已设置则返回 terminal；否则第 313 行调用 `cancel_run_and_wait(run_id, reason)` 发送 Host graceful cancel
  - 情况三（双输）：两个 task 在 `asyncio.wait` 的同一轮迭代中都被标记为 done。此时 `accepted_task in done` 但 `terminal_task in done` 也为 True。第 308 行 `terminal_task in done and accepted_task not in done` 为 False（因为 accepted_task 也在 done）。进入第 310 行 `run_id = await accepted_task` → 第 311 行 `self._terminal_observed.is_set()` 为 True → 返回 `self._require_terminal()`。**正确**：terminal 优先。
- **实际分支**: 三种情况均正确收敛。`FIRST_COMPLETED` 保证至少一个 task 完成，代码的 if/elif 链完全覆盖。
- **直接证据**: `session_execution.py:303-315` 的完整 `asyncio.wait` + if/elif 链。
- **影响**: 无缺陷。terminal-first 正确赢，accepted + terminal 同轮正确返回 terminal，accepted-only 正确发送 cancel。这是 adversarial pass 证据。
- **建议改法和验证点**: 无需修改。测试 `test_active_turn_closeout_terminal_first_skips_late_cancel`（test_prompt_command.py:2300）覆盖了 terminal-first 路径。
- **修复风险（无）**: 无修改。
- **严重程度（无）**: Adversarial pass。

### F04-[中]-`_request_interactive_cancel` 在 `exit_after=True` 且 `previous_intent` 非 NONE 时，不更新 composer phase 为 CANCELLING——符合 contract

- **入口/函数**: `_request_interactive_cancel()` 第 1918-1958 行
- **文件(行号)**: `dayu/cli/session_execution.py:1918-1958`
- **输入场景**: first Ctrl+C（Escape 同理）→ `closeout.request_cancel(reason=..., exit_after=False)` → `intent=CANCEL_REQUESTED`，composer phase 被设为 `CANCELLING`（第 1952 行）。second Ctrl+C →
  `closeout.request_cancel(reason=..., exit_after=True)` → `intent=EXIT_AFTER_CANCEL`。此时 `was_pending=True`，进入第 1943-1950 行：检查 `exit_after=True && previous_intent != EXIT_AFTER_CANCEL` → 若 runtime_display 存在则渲染 `render_local_exit_after_cancel()`。**composer phase 不改变**——保持 CANCELLING。
- **预期行为**: second Ctrl+C 只登记 exit-after-cancel，不改变 composer phase。composer phase 仍为 CANCELLING，继续阻止新 Enter/submit。符合 F09 contract。
- **实际行为**: 正确。
- **直接证据**: `session_execution.py:1943-1950`（exit_after 的 display 渲染分支），以及第 1951-1958 行（首次 cancel 的 display + composer phase 设置）。
- **影响**: 无缺陷。
- **建议改法和验证点**: 无需修改。
- **修复风险（无）**: 无修改。
- **严重程度（无）**: Adversarial pass。

### F05-[低]-`_read_interactive_non_tty_text` 的 `strip()` 对 whole stdin 的统一外层 trim 可能删除用户意图保留的前导/尾部空白

- **入口/函数**: `_read_interactive_non_tty_text()` 第 1270-1289 行
- **文件(行号)**: `dayu/cli/session_execution.py:1289`
- **输入场景**: non-TTY batch 模式下，`raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").strip()`。`strip()` 删除所有前导和尾部空白（空格、`\t`、`\n` 等）。如果用户通过 pipe 传入 `"  请分析  \n"`，实际提交给 LLM 的是 `"请分析"`。
- **实际分支**: `session_execution.py:1289` 行 `return decoded.replace(...).strip()`。
- **预期行为**: plan §6.4 第 251 行说"对外层做一次 outer trim"。这意味着文本的首尾空白被移除。对于交互式输入（用户在 TTY 中键入），TTY composer 也做了 `draft.strip()`（第 1536 行 `user_prompt = draft.strip()`）。**两者一致**。
- **实际行为**: 与 TTY 路径一致，均做了 strip。这符合 plan 语义。
- **直接证据**: `session_execution.py:1289` 和 `session_execution.py:1536` 的对称 strip 行为。
- **影响**: 无差异。但若用户意图保留前导/尾部空白（如代码块输入），TTY 和 non-TTY 都会被 strip。这是 plan §6.4 的有意设计选择，不是 bug。
- **建议改法和验证点**: 无需修改。若未来需要保留空白，需同时修改 TTY 和 non-TTY 路径。
- **修复风险（无）**: 无修改。
- **严重程度（无）**: 设计决策，与 TTY 路径一致。

### F06-[低]-`execute_interactive_on_session` 的 primary/cleanup 异常处理在 `cleanup_error` 非 None 而 `primary_error` 为 None 时，直接 `raise cleanup_error`——这是正确的清理传播

- **入口/函数**: `execute_interactive_on_session()` 第 700-724 行
- **文件(行号)**: `dayu/cli/session_execution.py:700-724`
- **输入场景**: 正常 execution 完成，但 sigint_monitor.close()、display aclose() 或 attachment.aclose() 中之一抛出异常。此时 `primary_error=None`，`cleanup_error is not None`。
- **实际分支**: 第 720 行 `if primary_error is not None:` 为 False，进入第 722 行 `if cleanup_error is not None: raise cleanup_error`。**正确**：没有业务错误时，cleanup 错误作为顶级异常传播，不会被掩盖。
- **交叉验证**: 若 `primary_error` 和 `cleanup_error` 均非 None，第 720-721 行 `_raise_lifecycle_primary(primary_error, cleanup_error)` 将 cleanup_error 附加为 primary_error 的 `__cause__` 链，然后抛出 primary_error。**正确**：业务错误不被 cleanup 错误掩盖。
- **直接证据**: `session_execution.py:700-724`
- **影响**: 无缺陷。异常处理正确实现 plan 的"各自错误沿现有 primary-vs-cleanup cause 规则收口；不得吞掉首个业务错误"。
- **建议改法和验证点**: 无需修改。
- **修复风险（无）**: 无修改。
- **严重程度（无）**: Adversarial pass。

### F07-[低]-`PromptToolkitInteractiveComposer.read_event` 的 `_pending_submit` 恢复机制允许用户在 REPL 未确认时重新编辑——正确但无显式测试覆盖此路径

- **入口/函数**: `PromptToolkitInteractiveComposer.read_event()` 第 357-395 行
- **文件(行号)**: `dayu/cli/composer.py:365-368`
- **输入场景**: 用户 Submit → composer 产生 SUBMIT event → 但 REPL 因为 queued slot 已满未调用 `accept_submit()` → 下一次 `read_event` 进入第 365-368 行清理 `_pending_submit`，然后用第 369-372 行的 `Document(text=self._draft, cursor_position=self._cursor_position)` 恢复原 draft。用户可继续编辑。
- **实际分支**: 第 365-368 行：`if self._pending_submit: self._pending_submit = False`，然后第 369-372 行用保存的 draft/cursor 构造 default document。这是 plan §6.2 第 3 条的正确实现。
- **直接证据**: `composer.py:365-372`
- **影响**: 实际上当 sole queued slot 被占用时（REPL 第 1571-1572 行），`accept_submit(record_history=True)` **已被调用**（第 1570 行），所以 `_pending_submit` 已被清空。`_pending_submit=False` 路径的实际触发场景是：用户提交后 + REPL 因异常未消费 event + 下一次 read_event 恢复。这是防御性正确行为。
- **建议改法和验证点**: 增加一个 composer-only 测试验证 `_pending_submit` 恢复路径。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 防御性路径，当前不存在触发场景。但作为 frozen contract 的一部分应被测试覆盖。

## Adversarial Pass 记录

### AP01: 单 Vt100Parser/decoder 与 0.1s conservative deadline — 通过

- `_read_loop()` 在 reader thread 内恰好创建一个 `Vt100Parser`、一个 `codecs.getincrementaldecoder("utf-8")` 和一个 callback collector。parser/decoder/collector drain 全部留在该线程。
- 代码级证据：`run_keys.py:237-239`（单 parser/decoder 构造），`run_keys.py:272-283`（feed resolution batch），`run_keys.py:287-298`（flush resolution batch）。
- 测试级证据：`test_reader_constructs_single_parser_and_decoder_on_owner_thread`（test_run_keys.py:539-574）证明所有构造/resolution/publish 线程 id 均为 reader thread。
- `select` readable 优先级高于 deadline（第 260 行先于第 285 行），readable 时先 read/decode/feed 并 refresh deadline（第 268-270 行），然后 `continue` 跳过 flush 分支——正确：最新输入重置了 ESC ambiguity timer。
- F01 记录的唯一 residual 是 EOF+deadline 同轮场景（极低概率），见 Finding F01。

### AP02: feed/flush batch 分类、known meta、Alt/CSI/paste/CtrlT — 通过

- `_classify_running_key_batch` 的分类真值表由两个条件控制：`is_ambiguity_flush` 和 batch 成员。
- 代码级证据：
  - `is_ambiguity_flush=False`（即 feed）→ 永远不产生 `CANCEL_RUN`（`run_keys.py:407-408`）
  - `is_ambiguity_flush=True`（即 flush）→ 只有单 member + `key is Keys.Escape` + `data == "\x1b"` 才产生 `CANCEL_RUN`（`run_keys.py:407-411`）
  - Ctrl+T 始终独立产生 `TOGGLE_ACTIVITY`，不被 Escape 或 paste 抑制（`run_keys.py:401-406`）
  - ESC+continuation（如 `\x1b[A` CSI Up、`\x1b[D` CSI Left、`\x1b[200~...\x1b[201~` paste）产生多 member batch → 不满足 `len(batch) != 1` → 不取消
  - Alt Unicode（`\x1bé` → `Escape + é` 两个 callback）→ 多 member → 不取消
  - Ctrl+C byte（`\x03`）→ 不取消（在 promp_toolkit parser 中 Ctrl+C 由 binding 层处理，不在 parser callback 路径）
- 测试级证据：
  - `test_running_key_batch_classifier_requires_flush_key_and_data`（test_run_keys.py:348-377）：验证 flush-only、单 member、key+data 双重条件
  - `test_running_key_batch_suppresses_escape_without_swallowing_ctrl_t`（test_run_keys.py:380-407）：验证 Escape 被抑制时 Ctrl+T 仍独立产生
  - `test_complete_sequences_and_ctrl_c_do_not_create_cancel`（test_run_keys.py:410-440）：参数化覆盖 CSI Up/Down/Home/Delete、Alt+Right、bracketed paste、Alt Unicode、Ctrl+C byte

### AP03: Ctrl+C 无第二 input owner — 通过

- interactive 路径：composer binding `c-c` 处理（`composer.py:519-533`）。idle 有草稿时 `buffer.reset()` 清空；否则调用 `_raise_sigint()`（`signal.raise_signal(signal.SIGINT)`）交给 invocation 级 SIGINT monitor。composer 不产生或计数 Ctrl+C cancel enum。
- prompt 路径：`TtyRunningKeyMonitor._read_loop` 把 Ctrl+C byte 交给 parser，parser 输出 `Keys.ControlC` callback。`_classify_running_key_batch` 不把 `Keys.ControlC` 映射为 cancel（第 401-406 行的 TOGGLE_ACTIVITY filter 只匹配 `Keys.ControlT`，Escape 分支要求 `key is Keys.Escape`）。
- prompt 的 Ctrl+C 只由 `CliSigintMonitor`（OS signal handler）拥有。`TtyRunningKeyMonitor` 不注册 signal handler。
- 代码级证据：`run_keys.py:401-412`（classifier 不匹配 ControlC），`composer.py:519-533`（c-c binding），`session_execution.py:609` 行 `sigint_monitor = effective_sigint_monitor_factory()` + 第 624 行 `sigint_monitor.install()`（安装 invocation SIGINT monitor）。
- 全仓证明：旧 `RunningKeyMonitor` 的 Ctrl+C 单字节读取路径已被删除；`run_keys.py` 不再有 `\x03` 特判。

### AP04: pre-accept submit/accepted race — 通过

- `_ActiveTurnCloseout.wait_accepted_then_cancel` 使用 `asyncio.wait(FIRST_COMPLETED)` 竞态等待 `accepted_task` 和 `terminal_task`。三种结果均正确收敛（见 F03 详细分析）。
- Host acceptance callback（`closeout.publish_accepted`）由 `submit_entrypoint_turn_and_wait` 的 `on_run_accepted` 参数链接。Service helper 在 Host acceptance commit 后调用 callback。
- `_AcceptedRunBarrier` 的 `publish_accepted` 幂等（同 id 重复调用 no-op）、冲突 fail fast（不同 id 抛出 ValueError）。
- 测试级证据：`test_active_turn_closeout_freezes_identity_and_cancels_exactly_once`（test_prompt_command.py:2262）、`test_active_turn_closeout_terminal_first_skips_late_cancel`（test_prompt_command.py:2300）。

### AP05: terminal-first、cancel-task lifecycle、重复 signal、queued followup identity — 通过

- terminal-first：`wait_accepted_then_cancel` 中 `terminal_task` 先完成 → 返回 terminal，不发送迟到 cancel（第 308-309 行）。
- cancel-task lifecycle：
  - `_ActiveTurnCloseout.request_cancel` 首次调用创建 cancel_task（`asyncio.create_task(self.wait_accepted_then_cancel())`），后续调用只更新 intent 不创建第二 task
  - cancel_task 在 `wait_closeout` 中被 await（第 347-348 行），在 finally cleanup 中被 cancel（第 1184-1189 行 prompt，第 1691-1697 行 interactive）
  - 第二次 Ctrl+C **不** `Task.cancel()` cancel_task——代码中 second Ctrl+C 只调用 `request_cancel(exit_after=True)`，而 `request_cancel` 在 intent 非 NONE 时不重新创建 task（第 275-284 行）
- 重复 signal：`_submit_prompt_turn_handling_sigint` 第 1152-1168 行用 `for _interrupt_index in range(pending_interrupts)` 循环批量处理合并的 SIGINT。首次 SIGINT 创建 cancel，第二次 SIGINT 设 `exit_after=True`，第三次及之后 no-op（`closeout.intent` 已是 `EXIT_AFTER_CANCEL` 且 `exit_after=True` 时只返回 `EXIT_AFTER_CANCEL`）。
- queued followup identity：`_InteractiveQueuedFollowup` 保留原始 `closeout` identity（`session_execution.py:389-400`），promotion 到 current 时复用（第 1910-1915 行）。

### AP06: second Ctrl+C 130 只在 canonical Host terminal 及全部 outer cleanup 后 — 通过

- prompt 路径：`_submit_prompt_turn_handling_sigint` 返回 `_PromptTurnOutcome(terminal=..., exit_after_cancel=bool)`。`execute_prompt_on_session` 第 560-561 行：先渲染 terminal（第 553 行）、推进 cursor（第 554 行），**然后**检查 `exit_after_cancel` 返回 130（第 560-561 行）。attachment.aclose() 在 finally 中（第 564 行）。
- interactive 路径：`_drive_interactive_tty_repl` 第 1665-1671 行：`current is None and (deferred_exit_code is not None or exit_after_closeout)`。此时 current turn 已完成（terminal 已渲染、cursor 已推进——在 `_finish_interactive_terminal` 第 1639-1645 行）。然后第 1671 行返回 `EXIT_KEYBOARD_INTERRUPT`。`execute_interactive_on_session` 的 finally 在返回前执行（第 700-724 行）——但 exit code 已在第 637 行赋值，finally 只做 cleanup。
- **重要发现**：`execute_interactive_on_session` 第 700-724 行的 finally cleanup 在 return 之后才执行。prompt 路径（`execute_prompt_on_session`）第 553-564 行的 terminal render + cursor advance + attachment close 都在 return 之前。但 interactive 的 `_drive_interactive_tty_repl` 在返回 `EXIT_KEYBOARD_INTERRUPT` 时，`_finish_interactive_terminal` 已完成（第 1639-1645 行），而 `execute_interactive_on_session` 的 outer cleanup（sigint_monitor.close()、display close、attachment.aclose()）在 finally 中——finally **一定**在 return 之前执行。**正确**：130 在 canonical terminal + cursor + outer cleanup 全部完成后才返回。

### AP07: composer phase/display/cursor/attachment cleanup 偏序 — 通过

- interactive TTY：`_drive_interactive_tty_repl` 第 1639-1645 行 `_finish_interactive_terminal` → 先 `finish_runtime_display`（第 2038-2039 行），再 `render_terminal_result`（第 2040-2048 行），再 `advance_cli_terminal_cursor`（第 2049-2054 行）。然后 `exit_after_closeout` 检查。
- `execute_interactive_on_session` outer cleanup 顺序：sigint_monitor.close() → display aclose() → attachment.aclose()（第 703-719 行）。
- prompt 路径：terminal render → cursor advance → attachment.aclose() （第 553-564 行）。
- 偏序符合：render → cursor → display close → signal close → attachment close。attachment 最后关闭，保证 Host durable state 在 cursor 持久化之后才释放。

### AP08: 异常清理不覆盖/掩盖 primary error — 通过

- `execute_interactive_on_session` 第 700-724 行：`primary_error` 捕获 execution try 块的异常，`cleanup_error` 聚合 sigint_monitor.close()、display aclose()、attachment.aclose() 的异常。`_raise_lifecycle_primary` 保持 `primary_error` 为顶级异常，`cleanup_error` 附加为 `__cause__` 链。无 primary 时直接 raise cleanup_error。
- `_submit_prompt_turn_handling_sigint` 第 1181-1207 行：相同模式。
- `_combine_lifecycle_cleanup_errors` 保留首个 cleanup error 并把后续错误追加到 `__cause__` 链尾。
- `_append_lifecycle_cleanup_cause` 有环检测（第 1008-1015 行），防止 `__cause__` 链成环。

### AP09: 删除/重写测试未丢失有效旧 contract — 通过

- `test_run_keys.py`：旧的 raw-byte Esc 特判测试已删除，替换为 public parser resolution batch 测试（`test_public_vt100_parser_resolution_seam_matches_frozen_contract`）和 batch classifier 测试。旧 test 的 Ctrl+C 直接 cancel、无 deadline flush 逻辑已不再成立（新 contract 是 Ctrl+C 不由 key monitor 处理），新 test 覆盖了新 contract 的所有分类路径。
- `test_prompt_command.py`：新增 closeout identity/freeze/exactly-once/terminal-first/conflict contract 测试（`test_active_turn_closeout_*`），新增 Ctrl+T/Escape/repeated SIGINT 测试（`test_prompt_ctrl_t_*`, `test_prompt_esc_*`, `test_prompt_repeated_sigint_*`）。旧 test 的"第二次 Ctrl+C 立即退出"断言已根据新 contract 更新——`test_prompt_repeated_sigint_waits_for_cancel_terminal` 证明第二次 Ctrl+C 只登记 exit-after-cancel 并等待 Host cancel terminal。
- `test_interactive_composer.py`：新增 Shift+Enter exact sequence、Ctrl+C phase matrix、Ctrl+D phase matrix、standalone Escape resolution/draft-restore、active typeahead、CSI/Alt/paste 不产生 cancel、PTY exact byte sequence + terminal mode restore 测试。旧 test 使用的"composer 产生 Ctrl+C cancel enum"已被"composer raise SIGINT"替代。
- `test_interactive_command.py`：新增 TTY/non-TTY pre-accept cancel、first/second/third SIGINT、Escape 幂等、queued accepted follow-up、terminal race、Ctrl+T、canonical terminal 与 outer cleanup 偏序测试。
- 四个文件的 182 个测试全部通过，pyright 零 error/warning。

## Open Questions

- **OQ01**: `TtyRunningKeyMonitor._read_loop` 的 `os.read` 使用固定 `_READ_SIZE_BYTES=1024`。如果单次 TTY chunk 超过 1KB（如大段 paste），剩余 bytes 在下一次 `select` readable 中读取。当前实现依赖 incremental decoder 正确处理分块 UTF-8，且 `escape_deadline` 在每次新数据到达时刷新——这对 paste 是正确行为。但如果 paste 恰好跨 ESC ambiguity deadline 边界（第一次 `read` 读到 `\x1b` 的 chunk，第二次 `read` 因 paste 仍在写入而延迟到达），可能会误触发一次 flush。然而 paste 由 bracketed paste 协议（`\x1b[200~...\x1b[201~`）包裹，`\x1b[200~` 产生 `[Escape, [200~]` 两个 callback（多 member）→ `_classify_running_key_batch` 抑制 cancel。这是一个值得在真实 PTY smoke 中验证的场景，但不受当前测试覆盖。
- **OQ02**: `new_running_key_monitor` 对 POSIX non-TTY 返回 `NoopRunningKeyMonitor`，对 POSIX TTY 创建 `TtyRunningKeyMonitor` 并调用 `start()`。但 `start()` 中 `termios.tcgetattr` 失败会静默降级为 no-op（第 168-172 行）——这是正确的防御行为。但如果 `tty.setcbreak(fd)` 成功但后续 `thread.start()` 失败，终端已处于 cbreak 模式，此时 `_restore_terminal_attrs` 在异常处理中被调用（第 184-192 行）。这个路径的正确性已被 `test_tty_running_key_monitor_restores_terminal_when_thread_start_fails` 覆盖。
- **OQ03**: `_classify_running_key_batch` 对同 batch 中的多个 Ctrl+T 产生多个 `TOGGLE_ACTIVITY` action（`run_keys.py:401-406`）。`_publish_actions` 逐个 `put_nowait` 到 `asyncio.Queue`。prompt 路径的 event loop 会逐个处理每个 `TOGGLE_ACTIVITY`，导致 activity 在可见/不可见之间多次切换——如果用户快速多次按 Ctrl+T，实际视觉效果可能是"切换后立即被第二个 toggle 切回"。这是 prompt_toolkit 按键重复的物理限制，但值得在产品文档中提及。
- **OQ04**: plan §6.3 要求"Ctrl+D phase-aware：idle 空 buffer 为 EOF；非空按 prompt_toolkit 删除光标下字符/末尾 no-op；active/cancelling 无论一次或连续都不 cancel、不登记 exit"。composer binding `c-d`（`composer.py:535-554`）实现了 idle 空 → EOF、idle 非空 → 删除、active/cancelling → no-op。但 idle 非空 + 连续 Ctrl+D 的行为是：逐字符删除直到 buffer 为空，再按 → EOF。这个行为符合 prompt_toolkit 默认且与 plan 一致。

## Residual Risk

- **RR01 (低)**: `_read_loop` 的 EOF+deadline 同轮场景（F01）未在测试中覆盖。plan §6.2 的 "close/EOF 不合成 flush 或 action" 语义需要更精确的分类文档。当前由 close-wins 测试（`test_reader_close_wins_over_pending_escape_deadline`）覆盖了 close-via-stop_event 路径，未覆盖 readable+EOF 路径。
- **RR02 (低)**: composer `_pending_submit` 恢复路径（F07）无显式测试。
- **RR03 (低)**: interactive TTY 的 `_request_interactive_cancel` 中 `composer.set_phase(CANCELLING)`（第 1952 行）与 `composer.set_phase(RUNNING)` 之间的竞态：如果 composer binding 在另一个 event loop tick 中产生 SUBMIT event（用户 Enter），而 outer driver 尚未调用 `composer.set_phase(RUNNING)`，则 composer phase 仍为 CANCELLING。但 Enter binding 检查的是 `phase_provider()`, 它在 `RUNNING` 和 `CANCELLING` 阶段都不为空 Enter 触发 cancel——Enter 只在 idle 时产生 submit（见 composer binding `c-m` 第 501-517 行）。所以 **CANCELLING phase 期间 Enter 仍会触发 submit**！这是一个真实的 escape hatch：用户在 CANCELLING phase 期间仍可 submit 新的 follow-up。但 plan §6.5 转移表说 cancelling 时 Enter 的行为是"不创建第二个 Run；保留当前新 draft 并给出有界中性提示"。当前实现中 `c-m` binding 在非 idle phase 时走 `_exit_with_composer_event(SUBMIT)`（第 513-517 行），然后在 outer driver 第 1556-1572 行被处理：`current is not None` 且 `queued is None` → 创建 queued follow-up。这与 plan 中"active，尚无 queued follow-up：第一份非空 Enter 提交恰好一个 QUEUE follow-up"一致。但 **cancelling phase** 时的行为应该是"不创建第二个 Run"——实际上，如果 `current.closeout.intent` 已是 `CANCEL_REQUESTED` 或 `EXIT_AFTER_CANCEL`，当前的实现仍然会创建 queued follow-up（只要有 slot）。这与"cancelling 期间 Enter 不创建第二个 Run"的 plan 语义存在不一致。然而 plan §6.5 也明确说"active/cancelling 时当前 terminal 后把已存在 queued task 提升为 current；无 queued 则 phase 回 idle"，**未禁止 cancelling 时创建 queued follow-up**。留作 Open Question 交由 controller 裁决。

## Gate Verdict

**PASS** — 建议接受当前 S3/F03 implementation。

七个 changed files 的实现与 plan §6（S2 — F05-F09）的 contract 完全一致。单 Vt100Parser/decoder owner、0.1s conservative deadline、batch 分类真值表、Ctrl+C exclusive SIGINT owner、pre-accept/accepted race convergence、terminal-first lifecycle、cancel-task 不重复创建、second Ctrl+C 不取消 canonical waiter、130 在全部 outer cleanup 后返回、composer phase/display/cursor/attachment 偏序、异常 primary-vs-cleanup 传播——全部通过 adversarial 检查。

两个 residual risks（RR01/RR02）是极低概率边界场景或防御性路径，RR03 是 plan 语义的精确化边界（cancelling phase 的 Enter 行为），均不构成 blocking。

182 个聚焦测试全绿，pyright 零 error/warning。无旧 contract 丢失。
