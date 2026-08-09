# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Code Review（MiMo）

## Scope

- Mode: current changes（uncommitted workspace changes relative to `fc1b4946`）
- Branch: `codex/interactive-oracle`
- Base: `fc1b4946`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-mimo.md`
- Included scope: 7 files — `dayu/cli/run_keys.py`, `dayu/cli/session_execution.py`, `dayu/cli/composer.py`, `tests/cli/test_run_keys.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_composer.py`, `tests/cli/test_interactive_command.py`
- Excluded scope: frozen registry files, plan/oracle/scenario docs（只读参考，不修改）
- Parallel review coverage: 无

## Adversarial Review Checklist

以下按用户指定的 adversarial 检查点逐项展开。

### 1. 单 Vt100Parser/decoder 和 0.1s conservative deadline 的真实 select/EOF/close/readable race

**结论：无实质问题。**

`run_keys.py:225-298` 的 `_read_loop` 实现了完整的竞态防护：

- **单一 parser/decoder owner**：`Vt100Parser`、`codecs.getincrementaldecoder("utf-8")` 和 `callback_collector` 都在 reader thread 内创建（行 237-240），全部留在该线程。测试 `test_reader_constructs_single_parser_and_decoder_on_owner_thread` 验证了构造和 resolution 都在同一线程。
- **readable 优先于 deadline**：行 260 `if readable:` 分支在 deadline 检查（行 285）之前执行。readable 时 `continue` 跳过本轮 deadline 检查，避免同轮既 read 又 flush。
- **deadline refresh**：行 269 `if _ESC in data or escape_deadline is not None:` — 新 ESC 刷新 deadline，已有 deadline 也刷新（保持 0.1s 窗口）。
- **close/EOF 不合成 flush**：行 263 `if not data: return` — EOF 时直接退出，不 flush，不产生 action。测试 `test_reader_close_wins_over_pending_escape_deadline` 验证了 close 与 deadline 同轮时不产生 cancel。
- **escape_deadline 清除**：行 291 `escape_deadline = None` — flush 后无条件清除，下次循环用默认 `_POLL_INTERVAL_SECONDS`。

**直接证据**：`run_keys.py:242-298`，测试 `test_reader_uses_conservative_deadline_and_readable_priority`（5 个参数化 case）、`test_reader_close_wins_over_pending_escape_deadline`。

### 2. feed/flush batch 分类、known meta、Alt/CSI/paste/CtrlT

**结论：无实质问题。**

`_classify_running_key_batch`（行 385-412）实现了精确的 batch 分类：

- **standalone Escape 四条件**：`is_ambiguity_flush=True` AND `len(batch)==1` AND `key is Keys.Escape` AND `data == "\x1b"`。测试 `test_running_key_batch_classifier_requires_flush_key_and_data` 验证了每个条件的独立性。
- **Ctrl+T 不被 Escape 吞掉**：行 402-406 先收集所有 `Keys.ControlT`，再检查 Escape 条件。即使 batch 包含 Escape + Ctrl+T，Ctrl+T 仍然产生 `TOGGLE_ACTIVITY`。测试 `test_running_key_batch_suppresses_escape_without_swallowing_ctrl_t` 覆盖了 `is_ambiguity_flush` 的两种值。
- **CSI/Alt/paste 不产生 cancel**：测试 `test_complete_sequences_and_ctrl_c_do_not_create_cancel` 覆盖了 8 种序列：CSI arrows、SS3、Home/Delete、CSI+modifier、bracketed paste（含 Ctrl+T payload）、Alt Unicode、Ctrl+C byte。
- **paste payload 内的 Ctrl+T**：`\x1b[200~paste\x14\x1b[201~` 被 Vt100Parser 解析为 `Keys.BracketedPaste`，`Keys.ControlT` 不会独立出现。

**直接证据**：`run_keys.py:385-412`，测试 `test_running_key_batch_classifier_requires_flush_key_and_data`、`test_running_key_batch_suppresses_escape_without_swallowing_ctrl_t`、`test_complete_sequences_and_ctrl_c_do_not_create_cancel`。

### 3. Ctrl+C 是否仍有第二 input owner

**结论：无实质问题。**

- **prompt**：Ctrl+C 由 `CliSigintMonitor` 独占。`run_keys.py` 的 `_classify_running_key_batch` 不识别 `Keys.ControlC`（行 402-406 只检查 `Keys.ControlT`），Ctrl+C byte 不产生任何 action。测试 `test_complete_sequences_and_ctrl_c_do_not_create_cancel` 验证了 `\x03` 不产生 cancel。
- **interactive**：Ctrl+C binding 只调用 `_raise_sigint()`（`composer.py:533`），由 invocation 已安装的唯一 SIGINT monitor 消费。composer 不产生 Ctrl+C cancel enum。测试 `test_ctrl_c_phase_matrix_uses_sigint_owner` 验证了 Ctrl+C 只通过唯一 SIGINT seam 通知 driver。

**直接证据**：`run_keys.py:402-406`、`composer.py:519-533`、测试 `test_complete_sequences_and_ctrl_c_do_not_create_cancel`、`test_ctrl_c_phase_matrix_uses_sigint_owner`。

### 4. pre-accept submit/accepted race

**结论：无实质问题。**

`_AcceptedRunBarrier`（`session_execution.py:166-205`）实现了幂等 acceptance：

- **同 id 幂等**：行 187-189 `if self.accepted_run_id == run_id: return` — 重复 publish 不报错。
- **冲突 id fail fast**：行 191-192 `if self.accepted_run_id != run_id: raise ValueError` — 不同 run_id 冲突立即报错。
- **pre-accept cancel 跨 barrier**：`_ActiveTurnCloseout.wait_accepted_then_cancel`（行 286-318）用 `asyncio.wait` 并发等待 acceptance 和 terminal。cancel intent 可在 acceptance 前登记，`wait_accepted_then_cancel` 会先等 acceptance 再发 Host cancel。

测试 `test_active_turn_closeout_freezes_identity_and_cancels_exactly_once` 验证了 reason 冲突 id 检测、幂等 publish 和 exactly-once cancel。

**直接证据**：`session_execution.py:166-205`、`session_execution.py:286-318`、测试 `test_active_turn_closeout_freezes_identity_and_cancels_exactly_once`。

### 5. terminal-first、cancel-task lifecycle、重复 signal、queued followup identity

**结论：无实质问题。**

- **terminal-first**：`wait_accepted_then_cancel` 行 308-309 — terminal 先到时保留真值且不发迟到 cancel。测试 `test_active_turn_closeout_terminal_first_skips_late_cancel` 验证了此行为。
- **cancel-task lifecycle**：`request_cancel` 行 275-284 — 首次创建 task，后续只更新 intent。task 最多一个。`wait_closeout` 行 338-350 — 等待 cancel_task（如果存在）和 terminal_observed。
- **重复 signal**：`_submit_prompt_turn_handling_sigint` 行 1148-1168 — 每次 SIGINT 增加 `observed_turn_sigint_count`，第二次设置 `exit_after=True`，但不创建新 cancel task。测试 `test_prompt_repeated_sigint_waits_for_cancel_terminal` 验证了连续 Ctrl+C 等待 Host canonical cancel terminal。
- **queued followup identity**：`_InteractiveQueuedFollowup`（行 389-400）携带自己的 `turn_index`、`submit_task` 和 `closeout`。promotion 时（行 1897-1915）保持原 submit/terminal waiter，只更新 generation。测试 `test_interactive_command.py` 中的 queued accepted follow-up 测试覆盖了此路径。

**直接证据**：`session_execution.py:275-350`、`session_execution.py:1148-1168`、`session_execution.py:1897-1915`、测试 `test_active_turn_closeout_terminal_first_skips_late_cancel`、`test_prompt_repeated_sigint_waits_for_cancel_terminal`。

### 6. second Ctrl+C 是否只在 canonical Host terminal 及全部 outer cleanup 后 130

**结论：无实质问题。**

- **prompt**：`_submit_prompt_turn_handling_sigint` 行 1206-1211 — `exit_after_cancel` 只在 `closeout.wait_closeout()` 返回后检查。outer cleanup（行 1183-1205）在返回前完成。`execute_prompt_on_session`（行 517-564）在 `outcome.exit_after_cancel` 检查前完成了 `render_prompt_terminal_result` 和 `advance_cli_terminal_cursor`。
- **interactive**：`_drive_interactive_tty_repl` 行 1665-1671 — `exit_after_closeout` 只在 `current is None` 且 closeout 完成后检查。`_finish_interactive_terminal`（行 2019-2055）在返回前完成了 display、render 和 cursor。

测试 `test_prompt_repeated_sigint_waits_for_cancel_terminal` 验证了：第二次 Ctrl+C 后，execution task 未立即完成；release cancel terminal 后，exit_code 为 130；cursor 在 terminal 后正确推进。

**直接证据**：`session_execution.py:1183-1211`、`session_execution.py:1665-1671`、测试 `test_prompt_repeated_sigint_waits_for_cancel_terminal`。

### 7. composer phase/display/cursor/attachment cleanup 偏序

**结论：无实质问题。**

- **prompt cleanup 偏序**：`_close_prompt_lifecycle`（行 921-974）按 `display.begin_closing` → `submit_task.cancel` → `display.close` → `monitor.close` → `sigint_monitor.close` → `sigint_task.cancel` → `key_task.cancel` 顺序执行。
- **interactive cleanup 偏序**：`execute_interactive_on_session`（行 567-724）在 finally 中按 `sigint_monitor.close` → `display.close` → `attachment.aclose` 顺序执行。primary_error 优先于 cleanup_error。
- **composer phase**：`set_phase` 在 submit 后设为 `RUNNING`，cancel 时设为 `CANCELLING`，完成后设为 `IDLE`。`_drive_interactive_tty_repl` 在 turn 完成后正确切换 phase（行 1655-1663）。
- **cursor 推进**：`_finish_interactive_terminal` 行 2049-2054 — cursor 在 render 后推进。prompt 的 `execute_prompt_on_session` 行 554-559 — cursor 在 render 后推进。

**直接证据**：`session_execution.py:921-974`、`session_execution.py:567-724`、`session_execution.py:2019-2055`。

### 8. 异常清理是否覆盖/掩盖 primary error

**结论：无实质问题。**

- **primary_error 优先**：`_raise_lifecycle_primary`（行 1018-1032）保持 primary_error identity，cleanup_error 作为 cause 链追加。
- **cleanup error 链接**：`_combine_lifecycle_cleanup_errors`（行 977-992）保留首错，后续 cleanup 错误追加到 cause 链尾部。`_append_lifecycle_cleanup_cause`（行 995-1015）检测 cause 环。
- **closeout cleanup**：行 1183-1205 — closeout_task 取消失败作为 closeout_cleanup_error，与 lifecycle cleanup_error 合并后附加到 primary_error。

测试 `test_session_execution_appends_later_cleanup_error_to_existing_cause_chain` 验证了 cause 链追加顺序。测试 `test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle` 验证了 display close failure 作为 primary error 传播。

**直接证据**：`session_execution.py:977-1032`、`session_execution.py:1183-1205`、测试 `test_session_execution_appends_later_cleanup_error_to_existing_cause_chain`。

### 9. 删除/重写测试是否丢失有效旧 contract 或只用 fixture 自证

**结论：无实质问题。**

- **测试覆盖范围**：四个测试文件共 182 个测试，覆盖了 public feed/flush seam、classifier key+data 双条件、Alt ASCII/Unicode、CSI arrows、SS3、Home/Delete、bracketed paste、paste payload Ctrl+T、同 batch Ctrl+T、Ctrl+C no-op、0.1s deadline、readable priority、refresh、空 flush、尾随 ESC、close-wins、不重复 cancel、记录构造和线程 id、PTY action 投递、termios 恢复和幂等 close。
- **prompt closeout 测试**：覆盖了 closeout identity/reason/exactly-once/terminal-first、pre-accept Escape 与 durable pre-accept SIGINT 跨 barrier、Ctrl+T、standalone Escape、repeated SIGINT 及 canonical terminal/cleanup 后返回。
- **interactive composer 测试**：覆盖了 typed Escape/Ctrl+T event 与 Ctrl+C 仅 raise SIGINT、Ctrl+J、Shift+Enter、bracketed paste、editor 矩阵。
- **interactive command 测试**：覆盖了 TTY/non-TTY pre-accept cancel、first/second/third SIGINT、Escape 幂等、queued accepted follow-up、terminal race、Ctrl+T 独立、canonical terminal 与 outer cleanup 偏序。
- **fixture 质量**：测试使用的 fake Host、fake watcher、fake monitor 等 fixture 都是按 production contract 设计的，不是自证式 fixture。例如 `_FakeHost` 的 `submit_followup` 按 production 顺序推入 events 和 terminal，`_ControlledCancelHost` 用 barrier 控制 cancel terminal 时序。

**直接证据**：182 passed 测试运行结果、四个测试文件的内容。

## Gate Verdict

**未发现实质性问题。**

S3/F03 implementation 在以下关键维度通过了 adversarial review：

1. **VT100 parser 单一所有权**：parser、decoder、collector 都在 reader thread 内，无跨线程竞态。
2. **0.1s deadline 正确性**：readable 优先、close 优先、deadline refresh 和清除逻辑完整。
3. **batch 分类完整性**：Escape 四条件、Ctrl+T 不被吞、CSI/Alt/paste 不产生 cancel、Ctrl+C no-op。
4. **acceptance barrier 幂等性**：同 id 幂等、冲突 id fail fast、pre-accept cancel 跨 barrier。
5. **cancel closeout 单调性**：reason 冻结、exactly-once Host cancel、terminal-first、second Ctrl+C 只升级 intent。
6. **exit 130 偏序**：canonical terminal → outer cleanup → exit 130，无提前退出。
7. **cleanup error 链**：primary error 优先、cause 链追加、环检测。
8. **测试覆盖**：182 passed，覆盖 happy path、failure path、boundary conditions 和竞态场景。

## Residual Risk

- **MEDIUM / covered by later S8 evidence**：真实终端分块、ESC/Alt 固有的 0.1s ambiguity、不同 provider/tool/closeout timing 与完整 live PTY scenario evidence。当前实现按 frozen oracle 抑制 ambiguity batch 的 Escape cancel，不把不可区分输入扩展为新产品承诺。
- **LOW / inherent design**：`_read_loop` 的 `select` 超时粒度为 `_POLL_INTERVAL_SECONDS`（0.05s），在极端负载下可能导致 Escape 解析延迟最多 0.05s。这是 polling 设计的固有 trade-off，不影响正确性。
- **LOW / test-only**：测试使用的 `_ScriptedSelectClock` 和 `_ScriptedRead` 是可控 seam，不覆盖真实 `select`/`os.read` 的 OS 级竞态。真实 PTY 测试（`test_real_posix_pty_exact_sequences_and_terminal_mode_restore`、`test_tty_running_key_monitor_reads_action_and_restores_terminal`）覆盖了 POSIX PTY contract。

## Open Questions

无。
