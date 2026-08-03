# Code Review — S3D Fast-closeout Corrective Slice (MiMo)

## Scope

- Mode: Current Changes (uncommitted S3D corrective slice)
- Branch: `codex/interactive-oracle`
- Base: `63fca270cc29d300c86e2ad0c9fddd9399913372`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-mimo.md`
- Included scope:
  - `dayu/cli/session_execution.py` (production, 4 hunks)
  - `tests/cli/test_interactive_command.py` (3 new tests + 3 helper functions)
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-fast-closeout-corrective-implementation-codex.md` (new artifact)
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md` (trailing whitespace removal, 3 lines)
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md` (EOF blank line removal)
- Excluded scope: four dirty README, S8 artifact, `code-review-20260803-075748.md`, `plan-review-20260803-064525.md`, frozen docs, S8 bundle evidence
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 覆盖证据与 adversarial 逐项分析

以下按用户指定的 adversarial 检查点逐一说明覆盖证据与结论。

#### 1. Host fast cancelled closeout 早于 frozen second action +0.05s 时同一 Ctrl+C chord 跨 closeout，下一击 exit130

**生产代码路径**：`session_execution.py:1990-1996`。

closeout 完成后检查 `terminal.terminal_status is HostTerminalStatus.CANCELLED and active_sigint_count == _INTERACTIVE_SINGLE_SIGINT_COUNT`（即 1），满足时把 `exit_intent` 设为 `SIGINT_CHORD_PENDING`。下一击在 `session_execution.py:1878-1885` 被消费：`exit_intent is SIGINT_CHORD_PENDING` 且 `current is None` 时直接 `return EXIT_KEYBOARD_INTERRUPT`。

**无论第二击在 closeout 完成前还是完成后到达，exit 130 都能触发**：

- 若第二击在 closeout 前到达（`current` 仍非 None）：走 `_consume_interactive_active_sigints`（`session_execution.py:1895-1910`），`active_sigint_count` 升至 2，`exit_after_closeout = True`，closeout 后 `session_execution.py:2014-2018` 返回 130。
- 若第二击在 closeout 后到达（`current` 已 None）：`exit_intent` 已被设为 `SIGINT_CHORD_PENDING`，走 `session_execution.py:1878-1881` 直接返回 130。

**测试覆盖**：`test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 参数化覆盖 `PROVIDER_WAIT`、`TOOL_EXECUTION`、`CLOSEOUT` 三条 frozen lane，使用真实 PTY + `os.kill(SIGINT)` + `call_later` 精确 0.05s 延迟。测试断言 `exit_code == EXIT_KEYBOARD_INTERRUPT` 和 `monitor.count == 2`。3/3 通过。

#### 2. Single canonical cancel/terminal

**生产代码路径**：`session_execution.py:1990-1996` 新分支只在 `intent is not EXIT_AFTER_CANCEL` 时执行（`elif`），不覆盖已有 `EXIT_AFTER_CANCEL` 升级路径。`_ActiveTurnCloseout.request_cancel`（`session_execution.py:291-300`）保证单 turn 只创建一个 cancel task。

**测试覆盖**：所有新测试断言 `host.calls.count("cancel:run-1") == 1` 和 `len(host.cancel_requests) == 1`。

#### 3. Queued current 不被误取消

**生产代码路径**：`session_execution.py:1878-1885` 的 `SIGINT_CHORD_PENDING` 路径中，若 `current is None` 则立即退出；若 `current is not None`（queued run 已晋升），只设 `exit_after_closeout = True` 并取消 composer task，不向已晋升的 current 发送额外 cancel。后续 `session_execution.py:2014-2018` 等待其既有 terminal 后退出。

**语义正确**：第二击到达时若已有 active run（不论来源），走 `_consume_interactive_active_sigints` 正常取消路径，不区分 run 来源。

#### 4. 正常新用户 submit/编辑 mutation 清除旧 chord

**生产代码路径**：`session_execution.py:1746-1747`，SUBMIT event 到达时无条件执行 `exit_intent = _InteractiveExitIntent.CONTINUE`，精确清除 `SIGINT_CHORD_PENDING`。此清除发生在新 turn 的 `_InteractiveActiveTurn` 创建之前。

**测试覆盖**：`test_interactive_submit_clears_cancelled_closeout_sigint_chord` 验证第一轮单 SIGINT cancelled closeout 后的新 submit，第二轮单次 SIGINT 产生 `cancel:run-2` 并最终 exit 0，证明 chord state 已被清除。

#### 5. Escape cancel 不武装

**生产代码路径**：Escape cancel 由 composer `RUNNING_KEY_ACTION` 事件驱动，不经过 `_consume_interactive_active_sigints`，因此 `active_sigint_count` 保持为 0。`session_execution.py:1990-1996` 的 `active_sigint_count == _INTERACTIVE_SINGLE_SIGINT_COUNT` 条件（1）不满足，不设置 `SIGINT_CHORD_PENDING`。

**测试覆盖**：`test_interactive_escape_cancel_does_not_arm_sigint_chord` 验证 Escape cancel 后单次 idle SIGINT 不直接 exit 130，而是等待 composer EOF 正常 exit 0。

#### 6. Active closeout 原语义不回归

**生产代码路径**：`session_execution.py:1988-1996` 新分支是 `elif`，只在 `EXIT_AFTER_CANCEL` 不满足时执行。已有 `_LocalCancelIntent.EXIT_AFTER_CANCEL` 升级路径（行 1988-1989）不受影响。既有 active double-SIGINT → `exit_after_closeout` 路径（通过 `_consume_interactive_active_sigints`）不变。

**测试覆盖**：既有 `test_interactive_os_sigint_first_second_and_third_follow_same_lifecycle`、`test_real_posix_double_sigint_exits_after_single_canonical_closeout` 全部通过（S3D artifact 验证：232 passed）。

#### 7. 真实 PTY/os.kill 测试能否证明三 lane exact timing、handler 和 terminal restoration

**handler 恢复**：测试断言 `signal.getsignal(signal.SIGINT) == previous_handler`。✓

**terminal restoration**：测试断言 `_terminal_lflag_controls(restored_lflag) == _terminal_lflag_controls(original_lflag)`，比较 ECHO/ICANON/ISIG/IEXTEN 四项 flags。✓

**三 lane timing**：测试使用 `first_sigint_delay`（provider/tool 0.01s，closeout 0.10s）+ `call_later(0.05s)` 精确重现 frozen scenario 的 +0.05s 第二击时序。但由于 asyncio event loop 调度抖动，测试无法证明 0.05s 精确到微秒级的 timing——它证明的是"第二击在 closeout 前后两种路径都正确处理"的行为正确性，而非毫秒级时序精确性。这是 PTY/os.kill 测试的固有限制，非本 slice 缺陷。

#### 8. Typed owner、无时间窗/强杀/第二 cancel source

- **Typed owner**：`exit_intent` 是 `_InteractiveExitIntent(StrEnum)`，只在 `session_execution.py` 的 `_drive_interactive_tty_repl` 函数内赋值和消费。`SIGINT_CHORD_PENDING` 只表达"下一击 SIGINT 应退出"的跨轮事实，不引入新 owner。
- **无时间窗**：生产代码无 `time.time()`、`asyncio.sleep()`、deadline 或 TTL 判断。`_INTERACTIVE_SINGLE_SIGINT_COUNT` 和 `_INTERACTIVE_EXIT_SIGINT_COUNT` 是 typed count 常量，不是时间阈值。
- **无强杀**：不调用 `os.kill`、`process.terminate()`、`task.cancel()`（除 composer task 取消，这是既有行为）。
- **无第二 cancel source**：只扩展 `_InteractiveExitIntent` 的合法来源和消费规则，不新增 cancel 通道。

#### 9. S3C 纯 whitespace 变更

`docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md`：3 处行尾 trailing space 删除（行 100、126、155）。`docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md`：EOF 多余空行删除。两者均无语义变更，与 S8 bundle `target_diff_check.findings` 一致。

### Residual Risk

| 项目 | 说明 |
|---|---|
| Queued run 在 SIGINT_CHORD_PENDING 状态下晋升 | 当前无专门测试覆盖"第一轮 SIGINT → closeout 设 SIGINT_CHORD_PENDING → queued run 晋升 → 第二轮 SIGINT 取消晋升 run 而非 exit 130"的完整路径。既有 S3C `test_interactive_accepted_sole_queue_followup_survives_double_sigint` 部分覆盖，但该测试的 closeout intent 是 `EXIT_AFTER_CANCEL` 而非 `CANCELLED`，不触发新分支。不阻塞 S3D gate。 |
| Full-real F01-F07 immutable evidence refresh | 尚未在新 target 上重跑。S3D artifact 明确声明由后续 S8 controller 覆盖。 |
| 第三方 deprecation warnings | 3 个非本 slice 回归，由 dependency maintenance 跟踪。 |

## Open Questions

无。

## Gate Verdict

**PASS**

S3D corrective slice 的生产代码变更（4 个 diff hunk）精确扩展既有 typed `_InteractiveExitIntent` 的合法来源，在 fast cancelled closeout 后保留已消费的第一击 chord state，并在下一次 SIGINT 正确 exit 130。实现不引入时间窗、强杀、第二 cancel source 或新 coordinator。三类 owner tests（frozen fast-closeout matrix、mutation chord 清除、Escape 不武装）覆盖核心行为，既有 232 个 CLI tests 全部通过，pyright 0 errors。S3C artifacts 的 whitespace 变更已确认纯格式修正。未发现实质性 defect。
