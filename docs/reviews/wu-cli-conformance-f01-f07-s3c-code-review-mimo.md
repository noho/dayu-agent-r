# Code Review — S3C Corrective Slice (PR 190)

## Scope

- **Mode:** PR 190 uncommitted S3C corrective slice
- **PR:** 190 (`fix(cli): close interactive conformance gaps`)
- **Branch:** `codex/interactive-oracle` vs `main`
- **Base:** `main`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-mimo.md`
- **Included scope:** production `dayu/cli/composer.py`, `dayu/cli/run_keys.py`, `dayu/cli/session_execution.py`；tests `tests/cli/test_interactive_composer.py`, `tests/cli/test_interactive_command.py`；docs `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md`
- **Excluded scope:** README dirty changes (S8)；`docs/reviews/code-review-20260803-075748.md`、`plan-review-20260803-064525.md`、`wu-cli-conformance-f01-f07-s8-implementation-codex.md`
- **Parallel review coverage:** 无

## Frozen F03 Target

1. Enter 后 0/10/20ms standalone Escape 跨 acceptance barrier 绑定同一 Run
2. Alt+X/CSI/Home/Delete/bracketed paste 完整 sequence 不误取消，仅无 continuation 才按 Escape
3. provider wait/tool/closeout double SIGINT single graceful closeout 后 exit 130

## Findings

未发现实质性问题。

### Detailed Evidence Walk

#### F03-1: Enter → standalone Escape 跨 acceptance barrier

**`SUBMITTING` phase 正确性**

- `composer.py:158` — `SUBMITTING` 枚举值加入 `InteractiveComposerPhase`。
- `composer.py:561-565` — `_record_submit_intent` 在 Enter chord 的同步按键回调中设置 `_pending_submit_intent = True` 并立即 `self._phase = InteractiveComposerPhase.SUBMITTING`。该赋值发生在 `prompt_async` task 向 REPL 返回 typed `SUBMIT` 之前，不依赖调度时序。
- `session_execution.py:1779` — driver 创建 turn task 后立即 `composer.set_phase(InteractiveComposerPhase.SUBMITTING)`，再创建 acceptance barrier task。两个 phase 设置时序一致，driver 的显式 set 不会覆盖 Enter chord 已设置的值。

**`_submit_or_insert_xterm_shift_enter` SUBMITTING 守卫**

- `composer.py:700-701` — `if phase_provider() is InteractiveComposerPhase.SUBMITTING: return`。Enter 在 SUBMITTING phase 被静默吸收，不产生第二份 SUBMIT。这是正确的：acceptance 前的第二个 Enter 没有业务语义。

**`_PendingSubmitDocument` 精确保留**

- `composer.py:298-306` — `_PendingSubmitDocument` 冻结 exact text 和 cursor_position。
- `composer.py:599-612` — `_record_pending_submit_document` 在 `_ComposerEventSignal` 或正常返回时冻结文档。
- `composer.py:438-460` — `read_event` 中，submit_handoff 路径把 `_draft` 设为空、`_submit_handoff_started = True`；非 handoff 的 rejected 路径调用 `_restore_pending_submit_document`。
- `composer.py:383-409` — `accept_submit` 在 `record_history=True` 时写入 pending document 的 text，否则保留。
- `composer.py:420-436` — `reject_submit_delivery` 调用 `_restore_pending_submit_document` 恢复 exact draft/cursor。

**PromptToolkit app handoff flush**

- `composer.py:531-548` — `_flush_submit_handoff_input` 在 `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 后调用 `application.input.flush_keys()` + `key_processor.feed_multiple` + `process_keys`。`is_done` 守卫防止 app 已退出后执行。
- `composer.py:478-480` — `pre_run=partial(self._begin_tracking_user_edits, flush_submit_handoff=submit_handoff)` 把 flush 注册为 PromptToolkit 的 background task。flush 与 PromptToolkit 自身的 `ttimeoutlen` 共用同一个 `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 常量。

**Test coverage:**

- `test_interactive_composer.py:542-574` — `test_exact_alt_x_is_resolved_before_standalone_escape` 覆盖同 chunk 和跨 chunk Alt+X。
- `test_interactive_composer.py:577-604` — `test_standalone_escape_waits_for_sequence_resolution_and_restores_draft` 覆盖 ambiguity timeout 后 standalone Escape 保留 draft/cursor。
- `test_interactive_command.py:3522-3574` — `test_real_pipe_early_escape_binds_submit_across_application_handoff` 参数化覆盖 0ms/10ms/20ms Enter → Escape，验证真实 PromptToolkit pipe 下 single cancel、history 记录、REPL 延续。
- `test_interactive_command.py:3479-3518` — `test_interactive_escape_crosses_pre_acceptance_barrier_once` 覆盖 pre-accept Escape 等待 Run id 后单次 cancel。
- `test_interactive_command.py:3582-3646` — `test_interactive_very_early_sigint_binds_pending_submit_to_accepted_run` 覆盖 typed SUBMIT 交付前 SIGINT 绑定同一 Run。

#### F03-2: Alt+X/CSI/Home/Delete/bracketed paste 不误取消

**PromptToolkit VT100 parser ambiguity 共用常量**

- `run_keys.py:32` — `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`，public 导出。
- `composer.py:37` — `from dayu.cli.run_keys import ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`。
- `composer.py:370-371` — `self._session.app.timeoutlen = ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 和 `ttimeoutlen` 相同值。PromptToolkit 的 VT100 parser 在此窗口内等待 ESC-prefixed continuation；超时后 flush 为 standalone `Keys.Escape`。
- `run_keys.py:273-274` — `TtyRunningKeyMonitor._read_loop` 中的 `escape_deadline = feed_time + ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`。

**`_is_exact_standalone_escape` 三重校验**

- `composer.py:1286-1298` — `len(event.key_sequence) == 1 and event.key_sequence[0].key is Keys.Escape and event.key_sequence[0].data == "\x1b"`。必须三者同时满足。Alt+X 解析为 `[Keys.Escape, Keys.Any]`（len=2），CSI 解析为多键序列，bracketed paste 产生多键序列，均不满足 `len == 1`。

**`_handle_complete_escape_prefixed_chord` 安全消费**

- `composer.py:746-762` — `@bindings.add(Keys.Escape, Keys.Any, filter=active_phase)`。完整双键 chord 只执行 continuation 自身语义（当前只有 Ctrl+T → TOGGLE_ACTIVITY），不发 cancel。

**run_keys.py VT100 parser 独立路径**

- `run_keys.py:389-416` — `_classify_running_key_batch` 只在 `is_ambiguity_flush=True and len(batch) == 1 and standalone.key is Keys.Escape and standalone.data == _ESC_TEXT` 时产生 `CANCEL_RUN`。非 flush batch 中的 Escape 不产生 cancel。

**Test coverage:**

- `test_interactive_composer.py:510-539` — `test_complete_csi_alt_and_bracketed_paste_do_not_emit_cancel` 参数化覆盖 `\x1b[A`、`\x1b[H`、`\x1b[3~`、`\x1bx`、`\x1b[200~粘贴\n内容\x1b[201~`，断言不产生 cancel。
- `test_interactive_composer.py:542-574` — `test_exact_alt_x_is_resolved_before_standalone_escape(split_chunks=True/False)` 覆盖同 chunk 和歧义期内跨 chunk 的 Alt+X。
- `test_interactive_composer.py:1213-1274` — `test_real_posix_pty_exact_sequences_and_terminal_mode_restore` 使用真实 PTY 验证完整序列解析、普通 Enter、standalone Escape 和 terminal mode 恢复。

#### F03-3: Double SIGINT → single graceful closeout → exit 130

**closeout SIGINT reconciliation**

- `session_execution.py:1957-1974` — terminal render/cursor cleanup 的 `await` 返回后、`current = None` 前，再次 `sigint_monitor.count - observed_sigint_count` 计算 closeout 期间到达的 SIGINT 增量。若有增量，调用 `_consume_interactive_active_sigints` 单调升级同一 closeout 的 exit intent。这确保 `_finish_interactive_terminal` 的 display/cursor I/O 期间到达的真实第二个 SIGINT 不会落入下一轮 idle 语义。

**`_consume_interactive_active_sigints` 单调升级**

- `session_execution.py:2294-2331` — 循环 `interrupt_count` 次，每次 `active_sigint_count += 1`，`exit_after = active_sigint_count >= 2`。第二次及以后调用 `request_cancel(exit_after=True)`，closeout 内部 `request_cancel` 在 `intent != NONE` 时只单调升级 intent，不创建第二个 cancel task。

**`_ActiveTurnCloseout.request_cancel` 幂等性**

- `session_execution.py:287-297` — `intent is NONE` 时创建唯一 cancel task；`exit_after=True` 时单调升级到 `EXIT_AFTER_CANCEL`。`_cancel_reason` 只在首次冻结。

**Test coverage:**

- `test_interactive_command.py:3823-3892` — `test_real_posix_double_sigint_exits_after_single_canonical_closeout` 参数化覆盖 `PROVIDER_WAIT`、`TOOL_EXECUTION`、`CLOSEOUT` 三阶段，使用真实 `os.kill(os.getpid(), signal.SIGINT)` 两次。断言 `monitor.count == 2`、`len(host.cancel_requests) == 1`、`exit_code == EXIT_KEYBOARD_INTERRUPT`、watcher 均关闭、signal handler 恢复。
- `test_interactive_command.py:3730-3766` — `test_interactive_ctrl_c_first_cancels_second_exits_and_third_is_noop` 覆盖 1st/2nd/3rd Ctrl+C 矩阵。
- `test_interactive_command.py:3769-3820` — `test_interactive_os_sigint_first_second_and_third_follow_same_lifecycle` 覆盖同步 fallback 的 OS SIGINT 三次复用统一 active 生命周期。
- `test_interactive_command.py:1955-2004` — `test_interactive_non_tty_second_sigint_waits_terminal_then_returns_130_and_third_is_noop` 覆盖 non-TTY 路径。

#### 类型/owner 边界

**`ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 共享**

- `run_keys.py:32-33` — public export，docstring 明确说明为 CLI input owner 共用常量。composer 和 run_keys 使用同一值，避免漂移。public 可见性是合理的设计决策——该常量描述两个模块的共享协议。

**`InteractiveComposerPhase.SUBMITTING` 语义**

- `composer.py:154-160` — `IDLE → SUBMITTING → RUNNING → CANCELLING`。SUBMITTING 是 Enter chord 后、Host acceptance 前的中间态。composer owner 同步设置，driver 显式确认。不存在多真源。
- `composer.py:407-409` — `accept_submit` 在 `record_history=True` 时设置 `_phase = RUNNING`。driver 也调用 `composer.set_phase(RUNNING)`。两者时序一致（accept_submit 在 acceptance barrier 之后）。

**`_PendingSubmitDocument` vs `_draft`**

- `_PendingSubmitDocument` 是 Enter chord 提交时的不可变快照，用于 history 记录和 rejection 恢复。
- `_draft` 是当前可编辑状态，submit handoff 期间被设为空（第二个 app 接管 stdin）。
- 两者不构成多真源：`_PendingSubmitDocument` 是 acceptance 前的冻结事实，`_draft` 是当前编辑状态。

**`has_pending_submit_intent` SIGINT 绑定**

- `session_execution.py:1876-1879` — idle SIGINT 检查 `composer.has_pending_submit_intent()`，若为 True 则 `pending_submit_sigint_count += 1`。该计数在 turn 创建后被消费（`session_execution.py:1838-1850`），绑定同一 Run。这是正确的：Enter chord 已同步设置 intent，SIGINT 不需要等 task 调度。

#### 补充验证

**`_cancel_active_with_escape` SUBMITTING + `is_done` 路径**

- `composer.py:774-777` — `phase_provider() is InteractiveComposerPhase.SUBMITTING and event.app.is_done` 时，不调用 `_exit_with_composer_event`（app 已退出），改为 `running_action_recorder(RunningKeyAction.CANCEL_RUN)`。action 进入 `_pending_running_actions`，下次 `read_event` 时消费。

**`read_event` SUBMITTING 检查**

- `composer.py:1190-1199` — `_ScriptedComposer.read_event` 中，`_phase is SUBMITTING` 时等待 phase 变更。这确保 scripted composer 在 acceptance 前不投递新 SUBMIT。

**`_InteractiveComposerCompletion.generation` stale control**

- `session_execution.py:1736-1741` — `RUNNING_KEY_ACTION` 在 `completion.generation != generation` 时视为 stale control 并丢弃。这防止已 turn 的 Escape 泄漏到新 turn。

## Open Questions

无。

## Residual Risk

1. **S8 full-real provider bundle 尚未重跑** — 当前 S3C 只修正了 S8 暴露的三项 F03 偏差。F01-F07 完整覆盖需要在 S3C review 通过后重跑 immutable evidence bundle。owner 为后续 S8 controller。
2. **Authorization durable projection residual** — 本轮未修，已分配到独立 work unit。
3. **第三方 deprecation warnings** — 非本 slice 回归，由 dependency maintenance 跟踪。

## Conclusion

**PASS**

S3C corrective slice 的三项 F03 修复均有直接代码证据支撑，实现路径清晰，类型/owner 边界正确，测试覆盖完整（含真实 PTY、真实 POSIX SIGINT、参数化 timing 矩阵）。未发现实质性问题。
