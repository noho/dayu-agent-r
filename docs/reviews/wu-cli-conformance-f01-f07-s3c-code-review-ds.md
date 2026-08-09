# Code Review — WU CLI Conformance F01-F07 S3C Corrective Slice (DS)

## Scope

- **Mode**: current changes (uncommitted S3C corrective slice)
- **Branch**: `codex/interactive-oracle`
- **Base**: `016d834adba509fbf7d1dc8749d474ed9f09ade4` (S8 immutable evidence baseline)
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md`
- **Review date**: 2026-08-03
- **PR**: PR 190

### Included scope

| 文件 | 角色 |
|---|---|
| `dayu/cli/composer.py` | Production: PromptToolkit composer, SUBMITTING phase, ESC handoff flush, key bindings |
| `dayu/cli/run_keys.py` | Production: `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 常量公开 |
| `dayu/cli/session_execution.py` | Production: driver REPL loop, SIGINT consumption, closeout reconciliation |
| `tests/cli/test_interactive_composer.py` | Test: Alt+X/CSI/Home/Delete/bracketed paste, standalone Escape, PTY mode restore |
| `tests/cli/test_interactive_command.py` | Test: real-pipe 0/10/20ms handoff, POSIX double SIGINT per-phase, scripted composer SUBMITTING |
| `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md` | Reference: implementation document (read-only, not reviewed for correctness) |

### Excluded scope

- `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md` — S8 controller 既有 dirty changes，非本 slice
- `docs/reviews/code-review-20260803-075748.md` — S8 review artifact
- `docs/reviews/plan-review-20260803-064525.md` — S8 plan review artifact
- `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md` — S8 implementation artifact
- 所有 `dayu/host/`、`dayu/engine/`、`dayu/service/` 等其他文件 — 不在 S3C scope

### Review target (F03 frozen requirements)

1. **Enter 后 0/10/20ms standalone Escape 跨 acceptance barrier 绑定同一 Run**
2. **Alt+X/CSI/Home/Delete/bracketed paste 完整 sequence 不误取消，仅无 continuation 才按 Escape**
3. **provider wait/tool/closeout double SIGINT single graceful closeout 后 exit130**
4. **PromptToolkit parser/app handoff**
5. **pending draft/history/read-only rejection**
6. **SIGINT durable count snapshot/race**
7. **single cancel/canonical terminal**
8. **类型/owner 边界**

### Review method

逐行走读 production 与 test diff，沿真实调用链追踪 Enter→SUBMITTING→handoff→Escape/Ctrl+T→cancel/acceptance/closeout 完整路径，以及 SIGINT monitor count→wait_next→pending_interrupts→_consume_interactive_active_sigints→closeout reconciliation 完整路径。adversarial failure pass 覆盖 TOCTOU race、state machine ordering、phase inconsistency、draft restoration、history 写入、exit code 正确性、type narrowing 与 semantic ownership。

## Findings

### 1-未修复-低-`_flush_submit_handoff_input` 在 application 快速退出时 ESC prefix 可能未被 flush

- **入口/函数**: `PromptToolkitInteractiveComposer._begin_tracking_user_edits` → `_flush_submit_handoff_input`
- **文件(行号)**: `dayu/cli/composer.py` 行 526-548
- **输入场景**: 用户在第二个 application（handoff 后空 buffer app）启动后 < `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`（0.1s）内键入 Enter 或其他导致 application 退出的输入
- **实际分支**: `_begin_tracking_user_edits` 在 `pre_run` 中通过 `create_background_task` 启动 `_flush_submit_handoff_input`，该 task 在 `asyncio.sleep(0.1)` 期间 application 退出，PromptToolkit 在 application exit 时取消所有 background tasks，task 被取消且不执行 flush
- **预期行为**: 残留 ESC prefix 要么被 flush 为 standalone Escape（取消），要么因 application 已退出而无害丢弃
- **实际行为**: task 被静默取消，VT parser 中残留 ESC prefix 未被显式 flush。但由于用户的新输入（Enter）已使 application 退出并提交了新 SUBMIT 事件，旧 ESC prefix 对功能无影响
- **直接证据**: 行 527 `self._session.app.create_background_task(self._flush_submit_handoff_input())` — 返回值未保存，task 无外部引用；PromptToolkit application exit 时 cancel 所有 background tasks（PromptToolkit 内部行为）
- **影响**: 无功能影响。ESC prefix 唯一有意义的消费路径是"用户未在歧义期内键入任何 continuation"→ standalone Escape → cancel。若用户在歧义期内键入 Enter，cancel 已无意义。当前行为等价于用户主动放弃了 ESC prefix。
- **建议改法和验证点**: 可保留现状。若追求形式完备性，可在 `_flush_submit_handoff_input` 中捕获 `asyncio.CancelledError` 并在被取消前尝试 flush（但此时 application 已退出，flush 无实际意义）。
- **修复风险（低）**: 非功能性改进，无需修复。
- **严重程度（低）**: 无功能影响，无用户可感知缺陷。

### 2-未修复-低-`reject_submit_delivery` 与 `read_event` 对 `_restore_pending_submit_document` 的重复调用

- **入口/函数**: `PromptToolkitInteractiveComposer.reject_submit_delivery` → `read_event`
- **文件(行号)**: `dayu/cli/composer.py` 行 432 与行 456
- **输入场景**: READ_ONLY rejection 路径 — Host 拒绝 mutation 后，driver 调用 `reject_submit_delivery()` 再重新创建 composer_task 进入 `read_event`
- **实际分支**: `reject_submit_delivery` (行 432) 调用 `_restore_pending_submit_document()` 将 draft/cursor 从 `_pending_submit_document` 快照恢复到实例字段。随后 `read_event` 的 `elif self._pending_submit` 分支 (行 456) 再次调用 `_restore_pending_submit_document()`，将同一快照值再次写入 `_draft` 与 `_cursor_position`
- **预期行为**: draft/cursor 只恢复一次
- **实际行为**: 同一快照被写入两次，值相同（`_pending_submit_document` 为 frozen dataclass），因此 idempotent 且无副作用
- **直接证据**: 行 432 `self._restore_pending_submit_document()`；行 456 `self._restore_pending_submit_document()` — 两个调用路径在 rejection 后连续执行
- **影响**: 无功能影响。代码阅读者可能疑惑为何需要两次恢复。实际原因是 `reject_submit_delivery` 的语义是"终结 delivery intent 并让 draft 可再次编辑"，而 `read_event` 的 elif 分支语义是"上一份 SUBMIT 未被 REPL 确认，恢复 draft 并清除 pending 标记"。两条路径在 rejection 场景中恰好叠加。
- **建议改法和验证点**: 可保留现状——两个调用的语义不同（一个是 delivery 终结，一个是 pending 清除），叠加 idempotent。若要在代码层面消除冗余，可将 `reject_submit_delivery` 中的 `_restore_pending_submit_document` 移除，仅靠 `read_event` 恢复；但需验证 `reject_submit_delivery` 调用后、下一次 `read_event` 前无人读取 `_draft`/`_cursor_position`。当前 `InteractiveComposer` Protocol 未暴露 `_draft`，该路径安全。
- **修复风险（低）**: 仅涉及内部状态管理，测试覆盖充分。
- **严重程度（低）**: 无功能影响。

### 3-未修复-低-`active_sigint_count` 在 closeout reconciliation 后被无条件重置为 0，覆盖 reconciliation 更新值

- **入口/函数**: `_drive_interactive_tty_repl` outer driver loop
- **文件(行号)**: `dayu/cli/session_execution.py` 行 1960-1974 与行 1983
- **输入场景**: closeout rendering 期间第三个 SIGINT 到达，被 reconciliation block 消费
- **实际分支**: 行 1960-1974 的 reconciliation block 通过 `_consume_interactive_active_sigints` 更新 `active_sigint_count`（可能变为 3）。行 1983 `active_sigint_count = 0` 将其无条件重置。由于 `active_sigint_count` 是 per-turn 计数，turn 清理后重置为 0 是正确的语义——下一个 turn 从 0 开始计数。
- **预期行为**: per-turn 计数器在 turn 清理后归零
- **实际行为**: 正确归零
- **直接证据**: 行 1983 `active_sigint_count = 0` 与行 1981 `current = None` 在同一代码块中顺序执行
- **影响**: 无功能影响。`active_sigint_count` 是 turn-local 变量，`current = None` 表示 turn 已结束。若 reconciliation 块将其更新为 3 后归零，下一个 turn 从 0 开始——这正是预期行为。此处列为 finding 仅因代码阅读时可能误以为 reconciliation 更新的值被"丢弃"。
- **建议改法和验证点**: 无需修改。可在行 1983 上方添加注释说明"per-turn 计数器；新 turn 从 0 开始"。
- **修复风险（低）**: 无。
- **严重程度（低）**: 无功能影响，仅为代码可读性提示。

## F03 Frozen Requirements — 逐项验证

### F03-1: Enter 后 0/10/20ms standalone Escape 跨 acceptance barrier 绑定同一 Run

**验证结果: PASS**

- **实现路径**: Enter binding (行 700-707) → `_record_submit_intent` 同步设置 `phase=SUBMITTING` → `_exit_with_composer_event` 退出第一个 application → `read_event` 冻结 `_pending_submit_document` → driver 创建 current turn (行 1764-1778) 并调用 `composer.set_phase(SUBMITTING)` → `read_event` 检测 `submit_handoff` 条件 (行 446)，启动第二个 application，draft 归零 → Escape 到达第二个 application → `_cancel_active_with_escape` 检测 `event.app.is_done`（若 Escape 与 Enter 在同 batch 则为 True；若 Escape 在第二 app 存活期间到达则为 False）→ True 时通过 `running_action_recorder` 记录 CANCEL_RUN 到 `_pending_running_actions`，由下一次 `read_event` 返回；False 时直接退出第二 app 返回 CANCEL_RUN → driver 收到 CANCEL_RUN，调用 `_request_interactive_cancel` 对同一 `current` turn 发起 graceful cancel

- **测试覆盖**: `test_real_pipe_early_escape_binds_submit_across_application_handoff` 参数化 0ms/10ms/20ms 三种间隔，使用真实 `PromptToolkitInteractiveComposer` + `create_pipe_input` + `_DelayedAcceptanceControlledHost`，验证：1 个 submit、1 个 `cancel:run-1`、1 个 GRACEFUL cancel、history 写入一次、exit 0。✓

- **边界确认**:
  - Escape 在 Enter 之前到达（pre-submit）→ 由 driver 在 `pending_submit_sigint_count` 路径处理（行 1834-1850），绑定随即创建的同一 turn ✓
  - Escape 在 acceptance 完成后到达 → 此时 phase 已变更为 RUNNING，Escape 走正常 `_exit_with_composer_event` 路径 ✓
  - Enter + Escape 同 batch → `event.app.is_done` 为 True，通过 `running_action_recorder` 延迟投递 ✓

### F03-2: Alt+X/CSI/Home/Delete/bracketed paste 完整 sequence 不误取消

**验证结果: PASS**

- **实现路径**: 两阶段 binding：
  1. `@bindings.add(Keys.Escape, Keys.Any, filter=active_phase)` (行 746) — 捕获所有 `ESC + continuation` 双键 chord。PromptToolkit 按 specificity 优先匹配（双键 > 单键），因此 `ESC + x`、`ESC + [` 等完整 chord 命中此 binding，不进入 standalone Escape binding。仅 `ESC + Ctrl+T` 有特殊处理（TOGGLE_ACTIVITY），其余 continuation 为 no-op（不取消、不退出 application）。
  2. `@bindings.add(Keys.Escape, filter=active_phase)` (行 764) — 仅在 PromptToolkit 经过 `timeoutlen=ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 超时后确认无 continuation 时才命中。`_is_exact_standalone_escape` 三重校验：`len(key_sequence)==1 AND key is Keys.Escape AND data=="\x1b"`。

- **测试覆盖**:
  - `test_complete_csi_alt_and_bracketed_paste_do_not_emit_cancel` — 参数化覆盖 `\x1b[A`（CSI up）、`\x1b[H`（CSI home）、`\x1b[3~`（CSI delete）、`\x1bx`（Alt+X）、`\x1b[200~...\x1b[201~`（bracketed paste），全部验证 SUBMIT 事件、无 cancel。✓
  - `test_exact_alt_x_is_resolved_before_standalone_escape` — 新增同 chunk 与跨 chunk（ESC 和 x 分两次写入，间隔 ESCAPE_SEQUENCE_AMBIGUITY_SECONDS/2）两种模式，验证 exact Alt+X 不误发 cancel。✓

- **边界确认**:
  - `ESC + ESC`（用户快速按两次 Escape）→ 命中 `Escape+Any` binding（continuation 为 Escape），非 ControlT → no-op。无副作用。✓
  - `ESC` 后等待 > 0.1s 无 continuation → PromptToolkit timeout → standalone Escape binding → cancel。✓
  - `ESC` 后 < 0.1s 内到达非按键字节（如终端控制序列的中间字节）→ PromptToolkit 内部 parser 继续等待完整序列，不触发 standalone binding。✓

### F03-3: provider wait/tool/closeout double SIGINT single graceful closeout 后 exit130

**验证结果: PASS**

- **实现路径**:
  1. `sigint_monitor.wait_next(observed_sigint_count)` → 返回新 count
  2. `pending_interrupts = sigint_monitor.count - observed_sigint_count` → 批量捕获所有未消费 interrupt
  3. `observed_sigint_count = sigint_monitor.count` → 快照更新
  4. `_consume_interactive_active_sigints(interrupt_count=pending_interrupts, active_sigint_count=current_count)` → 逐 interrupt 调用 `_request_interactive_cancel`：
     - 第一个 interrupt: `active_sigint_count=1`, `exit_after=False` → 创建 cancel task
     - 第二个 interrupt: `active_sigint_count=2`, `exit_after=True` → 升级 intent 为 EXIT_AFTER_CANCEL
  5. closeout rendering/cleanup 后 (行 1960-1974): `closeout_interrupts = sigint_monitor.count - observed_sigint_count` → 捕获 rendering 期间到达的迟到 SIGINT → 再次通过 `_consume_interactive_active_sigints` 单调升级

- **测试覆盖**: `test_real_posix_double_sigint_exits_after_single_canonical_closeout` 参数化三个 phase (`provider_wait`, `tool_execution`, `closeout`)，使用真实 `os.kill(os.getpid(), SIGINT)` × 2，验证：
  - `monitor.count == 2` ✓
  - `host.calls.count("cancel:run-1") == 1`（single cancel） ✓
  - `len(host.cancel_requests) == 1` ✓
  - 两个 watcher 均关闭 ✓
  - `exit_code == EXIT_KEYBOARD_INTERRUPT` (130) ✓
  - closeout phase: `len(finisher.terminals) == 1`，`terminal_status is CANCELLED` ✓
  - SIGINT handler 恢复为 `previous_handler` ✓

- **边界确认**:
  - 第三个 SIGINT 在 closeout 后 → `current = None`，进入 idle 处理（行 1875-1883），两次 idle Ctrl+C 后 exit ✓
  - closeout rendering 期间第二个 SIGINT（`_BlockingTerminalFinisher` barrier 注入）→ reconciliation block (行 1960) 捕获 ✓
  - `CliSigintMonitor.wait_next` 的 event clearing 与 count 递增非原子 → 但 `while self.count <= observed_count` 循环 + `pending_interrupts = count - observed` 的 delta 计算保证不丢失 interrupt ✓

### F03-4: PromptToolkit parser/app handoff

**验证结果: PASS**

- **实现路径**: 第一个 application 因 Enter 退出 → `read_event` 冻结 `_pending_submit_document` 快照 → 下一次 `read_event` 检测 `submit_handoff` 条件 → 第二个 application 以空 buffer 启动并接管 stdin → `pre_run` 中 `_begin_tracking_user_edits(flush_submit_handoff=True)` 创建 `_flush_submit_handoff_input` background task → task 在 `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 后调用 `application.input.flush_keys()` + `key_processor.feed_multiple()` + `key_processor.process_keys()` 将上一 app 的 VT parser 残留 ESC prefix 注入当前 key processor → 若有完整 continuation 已在歧义期内到达 pipe，由当前 parser 先解析完整 chord

- **关键设计决策**:
  - `_submit_handoff_started` flag (行 450) 确保 `accept_submit` 不清空已在第二 app 中编辑的 draft
  - `_pending_submit_document` frozen snapshot (行 297-306) 使 acceptance 时仍可拿到原始 Enter 时刻的 exact draft 写入 history，即使第二 app 的 buffer 已被修改
  - `application.input.flush_keys()` + `key_processor.feed_multiple()` + `key_processor.process_keys()` 的显式 flush seam（行 546-548）确保 PromptToolkit 内部 input buffer 与 key processor 之间无隐式 typeahead 丢失

### F03-5: pending draft/history/read-only rejection

**验证结果: PASS**

- **history 写入**: `accept_submit(record_history=True)` (行 399-400) 从 `_pending_submit_document.text` 写入 history（而非当前 `_draft`），确保写入的是原始 Enter 时刻的 exact draft。✓
- **draft 保留**: `_submit_handoff_started` flag (行 401) 使 draft 在 handoff 场景不清空（第二 app 可能已有新编辑）。✓
- **READ_ONLY rejection**: `reject_submit_delivery()` (行 420-436) 从 `_pending_submit_document` 快照恢复 draft/cursor → 清 `_pending_submit_intent`、清 `_pending_running_actions`、phase=IDLE → 下一次 `read_event` 的 elif 分支恢复 draft 并启动新 application。测试 `test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft` 验证 draft 精确恢复。✓
- **READ_ONLY + SIGINT 交互**: `test_interactive_idle_sigint_after_read_only_does_not_cancel_retry_run` 验证 rejection 后 idle SIGINT 不误取消。✓

### F03-6: SIGINT durable count snapshot/race

**验证结果: PASS**

- **快照机制**: `observed_sigint_count = sigint_monitor.count` (行 1874) 在每次消费后更新；`pending_interrupts = sigint_monitor.count - observed_sigint_count` (行 1872) 总是计算增量
- **batch 处理**: `interrupt_count` 直接传入 `_consume_interactive_active_sigints`，for 循环逐 interrupt 处理，不遗漏
- **closeout reconciliation**: 行 1960 `closeout_interrupts = sigint_monitor.count - observed_sigint_count` 在 `await _finish_interactive_terminal(...)` (可能 yield event loop) 之后执行，捕获 rendering 期间的迟到 SIGINT
- **`current` 清空前 reconciliation**: reconciliation 在 `current = None` (行 1981) 之前执行，确保第三次 SIGINT 仍绑定同一 turn
- **`CliSigintMonitor.wait_next` race**: `while self.count <= observed_count: await event.wait(); event.clear()` 的 event clearing 与 count increment 不原子——但 while 循环 + count 比较保证不丢失。若两个 SIGINT 在 event.wait() 与 event.clear() 之间到达，count 已 = 2，while 循环退出，返回 count=2，caller 计算 `pending_interrupts=2`。✓

### F03-7: single cancel/canonical terminal

**验证结果: PASS**

- **single cancel**: `_ActiveTurnCloseout.request_cancel` (行 273-297)：`intent is NONE` 时创建 cancel task；后续调用仅升级 intent（`CANCEL_REQUESTED` → `EXIT_AFTER_CANCEL`），不创建第二个 cancel task。✓
- **canonical terminal**: `_ActiveTurnCloseout.observe_terminal` (行 333-349)：首个 terminal 写入 `_terminal` 并 set `_terminal_observed`；后续 terminal 若与既有冲突则 raise ValueError。`_require_terminal` 在 `_terminal is None` 时 raise RuntimeError。✓
- **acceptance barrier**: `_AcceptedRunBarrier.publish_accepted` (行 190-205)：首个 run_id 写入并 set event；后续 run_id 冲突则 raise ValueError。`wait_run_id` (行 207-218) 等待 event 后返回 run_id。✓

### F03-8: 类型/owner 边界

**验证结果: PASS**

- `_RunningActionRecorder`: `Callable[[RunningKeyAction], None]` — 类型精确，仅接受 `RunningKeyAction` enum。✓
- `_PendingSubmitDocument`: `@dataclass(frozen=True, slots=True)` — 不可变快照，字段 `text: str`、`cursor_position: int`。✓
- `_start_tty_driver` 签名变更 (行 4522): `composer: _ScriptedComposer` → `composer: InteractiveComposer` — protocol 类型更宽，正确接收 `PromptToolkitInteractiveComposer` 与 `_ScriptedComposer` 两种实现。✓
- `_ScriptedComposer` protocol compliance: 完整实现 `set_phase`、`accept_submit`、`has_pending_submit_intent`、`reject_submit_delivery`、`read_event`。✓
- `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 常量公开化 (run_keys.py 行 32-33): 移除 `_` 前缀，添加 docstring，composer 与 prompt monitor 共用同一常量，消除 dual ownership。✓
- composer 的 `timeoutlen`/`ttimeoutlen` 设置 (行 370-371): 使用同一公共常量，语义一致。✓
- PrompToolkit 类型不泄露到 CLI REPL 层：`InteractiveComposer` Protocol 不暴露任何 `prompt_toolkit` 类型。✓

## Open Questions

- **OQ-1**: `_flush_submit_handoff_input` 的 `asyncio.sleep(ESCAPE_SEQUENCE_AMBIGUITY_SECONDS)` 是否足以覆盖所有终端类型的 ESC sequence 歧义期？PromptToolkit 文档中 `timeoutlen` 默认值为 1.0s；当前设置 0.1s 与 `run_keys.py` 的 ESC sequence ambiguity 常量一致，对现代终端足够。若未来有超慢连接（如 300 baud serial terminal），0.1s 可能不足——但此类终端不在支持范围内。
- **OQ-2**: `CliSigintMonitor._event.clear()` 与 `self.count` 递增之间的非原子性是否可能导致 missed wakeup？经逐行验证，while 循环 + count 比较保证不漏；但如果 `wait_next` 并发调用（当前 production 中只有一个 caller——outer driver），不会有问题。并发调用场景超出当前 scope。

## Residual Risk

- **RR-1**: 新的 target full-real F01-F07 immutable evidence bundle 尚未重跑。S3C slice 只修复了 S8 evidence 暴露的三项 F03 偏差，但未用新的 production 代码重新生成 evidence bundle。该动作属于本 slice 双路 review 接受后的 target evidence refresh（owner: 后续 S8 controller）。风险：可能存在未被 S8 frozen evidence 覆盖的回归，但 S3C 的 focused tests 覆盖了所有三项偏差的直接路径。
- **RR-2**: `_ScriptedComposer` 的 SUBMITTING phase blocking 逻辑 (行 1190-1199) 只在 `not self._remaining` 或下一步为 str/SUBMIT event 时阻塞。若 script 中下一步为 RUNNING_KEY_ACTION，SUBMITTING 不阻塞——这正确地模拟了 production 行为。但若 script 中下一步为 EOF，SUBMITTING 会阻塞直到 phase 变化——这在特定测试场景下可能导致 hang。当前测试用例均不触发此路径。
- **RR-3**: Authorization durable projection residual (DR-S8-01) 未修复，属独立 work unit。不影响本 slice 的 F03 validation。

## Conclusion

**PASS** — 无阻塞性缺陷。实现准确覆盖三项 F03 frozen requirements 的所有正向路径与边界条件。

三项 low-severity findings 均为代码可读性/冗余性问题，不影响功能正确性。所有 F03 子项（handoff、Escape resolution、SIGINT consumption、single cancel、canonical terminal、类型边界）的逐项验证均 PASS。测试覆盖充分：真实 pipe PTY、真实 POSIX SIGINT × 2 per-phase、真实 PromptToolkit key binding resolution（Alt+X 同 chunk/跨 chunk）、0/10/20ms handoff delay、READ_ONLY rejection + draft restoration、SIGINT handler 恢复。

建议后续 S8 controller 在双路 review 接受后执行 full-real F01-F07 evidence bundle refresh，以端到端确认 no regression。
