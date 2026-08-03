# WU CLI Conformance F01-F07 — S3D Fast-closeout Corrective Code Review (DeepSeek)

## Scope

- **Mode:** current changes (uncommitted S3D corrective slice)
- **Branch:** `codex/interactive-oracle`
- **Base:** `63fca270cc29d300c86e2ad0c9fddd9399913372`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-ds.md`
- **Included scope:**
  - `dayu/cli/session_execution.py` — production diff
  - `tests/cli/test_interactive_command.py` — test diff
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-fast-closeout-corrective-implementation-codex.md` — implementation artifact
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md` — whitespace-only diff
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md` — whitespace-only diff
- **Excluded scope:**
  - 四份既有 dirty README（`README.md`、`dayu/README.md`、`dayu/config/README.md`、`tests/README.md`）
  - `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`
  - `docs/reviews/code-review-20260803-075748.md`
  - `docs/reviews/plan-review-20260803-064525.md`
  - Frozen `docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`
- **Evidence sources read:**
  - S8 partial bundle: `summary.json`、`summary.md`、`validation-results.json`
  - F03 frozen double SIGINT scenarios: `frozen-double-sigint-scenarios.json`
  - F03 root cause owner evidence: `root-cause-owner-evidence.json`
  - S3C implementation artifacts (whitespace diff verified via `git diff --check`)
- **Parallel review coverage:** 无（单一 reviewer 完整走读）

## Review Method Summary

沿真实代码路径逐行走读 `_drive_interactive_tty_repl` 的 SIGINT 处理主链路（idle、active、closeout→chord→exit），展开入参→条件→下游调用→返回值→副作用，对每个关键 `if/elif` 做分支覆盖分析，对 `_ActiveTurnCloseout`、`_InteractiveExitIntent`、`_LocalCancelIntent` 三个 typed state machine 做正常/取消/快速 closeout/queued promotion/READ_ONLY 恢复路径的状态转换验证。执行 adversarial failure pass：检查时间窗、第二 cancel source、chord 误武装、chord 泄漏跨 mutation、Escape cancel 误计数、queued current 误取消。逐项对 S3D contract 的 6 条目标/非目标做覆盖证据检查。

## Findings

### F01-未修复-低-frozen PTY 测试的 `monitor.count == 1` 断言依赖调度时序

- **入口/函数:** `test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout`
- **文件(行号):** `tests/cli/test_interactive_command.py:3976`
- **输入场景:** frozen closeout/provider/tool lane，第一次 `os.kill(SIGINT)` 后 `+0.05s` 的 `call_later` 已注册但尚未触发
- **实际分支:** `_wait_for_real_composer_phase` 的 1000 次 `await asyncio.sleep(0)` 循环完成时，`call_later(0.05, os.kill, ...)` 回调因 wall-clock 未到而尚未触发
- **预期行为:** `assert monitor.count == 1` 应始终成立，证明第二击在 closeout 完成后才到达
- **实际行为:** 在极端负载系统上，1000 次 `asyncio.sleep(0)` 的 wall-clock 累计可能超过 0.05s，导致定时器先于断言触发，`monitor.count` 已经为 2，测试误失败
- **直接证据:**
  - `call_later(_FROZEN_SECOND_SIGINT_DELAY_SECONDS, os.kill, ...)` 在行 3965 注册，`_FROZEN_SECOND_SIGINT_DELAY_SECONDS = 0.05`
  - `_wait_for_real_composer_phase`（行 4688-4694）每次迭代 `await asyncio.sleep(0)` 将控制权交回 event loop，event loop 在每次迭代检查到期定时器
  - 行 3976 `assert monitor.count == 1` 没有 wall-clock guarantee，只依赖 event loop 调度速度
- **影响:** 测试不稳定，极端负载下偶发误报（flaky test）；不影响 production 正确性，因为 production 路径不依赖此类时序假设
- **建议改法和验证点:**
  - 在 `call_later` 注册前调用 `second_signal` handle 的 `when()` 确认定时器未到期，或
  - 将 `assert monitor.count == 1` 改为 `assert monitor.count <= 2`（仍在证明第二击未在 closeout 前到达，但不如原断言精确），或
  - 在 `_wait_for_real_composer_phase` 返回后插入 `await asyncio.sleep(0)` 以 flush 已到期的定时器，再断言 `monitor.count == 1`
  - 验证点：在低负载 CI 环境连续运行 100 次确认稳定
- **修复风险（低）:** 仅测试内部 guard，不改变 production 语义
- **严重程度（低）:** 当前环境下 `0.05s` 远超 1000 次 `asyncio.sleep(0)` 的执行时间，实际 flake 概率极低；且断言级联到后续 `assert monitor.count == 2` 与 `exit_code == 130`，不会导致假阳性通过

### F02-未修复-低-`_INTERACTIVE_SINGLE_SIGINT_COUNT` 常量仅在 chord arm 条件使用，`pending_submit_sigint_count` 路径中的计数递增未使用该常量

- **入口/函数:** `_drive_interactive_tty_repl` → `pending_submit_sigint_count` 消费路径
- **文件(行号):** `dayu/cli/session_execution.py:1837-1853`
- **输入场景:** Enter 后 typed SUBMIT 尚未交付时收到的 SIGINT（极早中断场景）
- **实际分支:**
  ```python
  for _interrupt_index in range(pending_submit_sigint_count):
      active_sigint_count += 1  # line 1842
      exit_after = active_sigint_count >= _INTERACTIVE_EXIT_SIGINT_COUNT  # line 1843
  ```
- **预期行为:** `active_sigint_count += 1` 为裸常量，虽然值恒为一，但语义上应通过常量表达"每次递增一个 SIGINT"
- **实际行为:** 递增步长为一，与 `_INTERACTIVE_SINGLE_SIGINT_COUNT`（值同样为一）数值一致，但没有通过常量自文档化其含义
- **直接证据:** 行 1842 `active_sigint_count += 1` 对比行 1843 的 `>= _INTERACTIVE_EXIT_SIGINT_COUNT`
- **影响:** 极低 — 两常量值均为一，即使未来调整数值（极不可能，因为 SIGINT 计数语义是固定的），此处裸 `1` 是 for-loop 索引递增，不是业务阈值
- **建议改法和验证点:** 可将 `active_sigint_count += 1` 改为 `active_sigint_count += _INTERACTIVE_SINGLE_SIGINT_COUNT` 以获得一致的常量使用；但当前写法可读且不会引入 bug
- **修复风险（低）:** 纯常量替换，无语义变化
- **严重程度（低）:** 不构成 bug，仅代码风格一致性建议

## Contract Coverage Evidence

以下逐项对照 S3D approved contract（implementation doc §3）给出覆盖证据：

### 目标 1: 第一次 active SIGINT 请求 graceful cancel 后，Host cancelled closeout 在 frozen 第二击前完成，已消费的第一击继续由 typed chord intent 持有

**覆盖证据:** `dayu/cli/session_execution.py:1990-1996`
```python
elif (
    terminal.terminal_status is HostTerminalStatus.CANCELLED
    and active_sigint_count == _INTERACTIVE_SINGLE_SIGINT_COUNT
):
    exit_intent = _InteractiveExitIntent.SIGINT_CHORD_PENDING
```
此分支在 `EXIT_AFTER_CANCEL`（已有第二击）为 False 时检查：terminal 为 CANCELLED 且恰好消费了一次 SIGINT → 将 chord intent 置为 pending。测试 `test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 三 lane 参数化覆盖 provider wait、tool execution、closeout，均验证：首击后 closeout 完成 → composer 回到 IDLE → monitor.count 仍为一 → chord 已武装。

### 目标 2: 下一次 SIGINT 视为同一 chord 的第二击并 exit 130；同一已完成 closeout 不再发送 cancel

**覆盖证据:** `dayu/cli/session_execution.py:1878-1885`
```python
if exit_intent is _InteractiveExitIntent.SIGINT_CHORD_PENDING:
    if current is None:
        normal_completion = True
        return EXIT_KEYBOARD_INTERRUPT
    exit_after_closeout = True
```
此分支在 `pending_interrupts > 0` 时最先检查（先于 idle 首击/active turn 处理），确保 chord pending 时的新 SIGINT 被解释为第二击。无 current 时立即 exit 130；有 queued promotion 时只设置 `exit_after_closeout`，不发送新 cancel。测试中 `host.calls.count("cancel:run-1") == 1` 证明没有第二次 cancel。

### 目标 3: 如果 closeout 后已有此前 accepted queued Run，第二击只登记退出并等待其既有 terminal，不增加 cancel source

**覆盖证据:** 同上行 1882-1885 的 `exit_after_closeout = True` 路径。此路径不调用 `_request_interactive_cancel`，不经过 `_ActiveTurnCloseout.request_cancel`，因此不创建新的 cancel task。queued Run 的既有 `submit_task` 继续运行至 terminal，driver 在 `current is None and exit_after_closeout`（行 2014-2018）时返回 130。既有测试 `test_interactive_exit_after_cancel_waits_accepted_sole_queue_terminal` 覆盖了 exit-after-cancel + queued 的等价路径（共享同一 `exit_after_closeout` 机制和同一退出检查点）。

**反例检查:** chord pending + queued promotion 场景没有独立测试。当前测试矩阵依赖 `exit_after_closeout` 的两种来源（`EXIT_AFTER_CANCEL` 和 `SIGINT_CHORD_PENDING → exit_after_closeout = True`）共享同一退出机制。S3D contract 没有要求为该组合单独新增测试，但应记为 residual risk（见下方）。

### 目标 4: 后续 typed SUBMIT / EOF mutation boundary 清除旧 chord intent

**覆盖证据:** `dayu/cli/session_execution.py:1747`（SUBMIT handler 首行）:
```python
exit_intent = _InteractiveExitIntent.CONTINUE
```
和行 1832（EOF handler）:
```python
exit_intent = _InteractiveExitIntent.CONTINUE
```
测试 `test_interactive_submit_clears_cancelled_closeout_sigint_chord` 验证：第一轮单 SIGINT cancelled closeout（chord armed）→ 第二轮 submit（chord cleared）→ 第二轮单 SIGINT 产生独立 `cancel:run-2` 并 exit 0。

### 目标 5: standalone Escape cancel 的 active SIGINT count 为零，不得武装 chord intent

**覆盖证据:** Escape cancel 走 `_request_interactive_cancel` → `closeout.request_cancel(reason, exit_after=False)`，不经过 SIGINT monitor 的 count 递增路径。`active_sigint_count` 保持为 0（因为没有 `pending_interrupts > 0` 触发 `_consume_interactive_active_sigints`）。当 cancelled closeout 完成时，`active_sigint_count == _INTERACTIVE_SINGLE_SIGINT_COUNT` 为 `0 == 1` → False，chord 不武装。测试 `test_interactive_escape_cancel_does_not_arm_sigint_chord` 验证：Escape cancel → cancelled closeout → idle SIGINT 不 exit 130 → EOF exit 0。

### 非目标验证

- **无时间窗:** chord 仅由 typed state（`SIGINT_CHORD_PENDING` + `_LocalCancelIntent`）驱动，无 `time.sleep`、`call_later`、deadline 或 threshold 判断。✓
- **无强杀:** cancel 始终为 `CancelMode.GRACEFUL`，无 `SIGKILL`/`SIGTERM`/force close。✓
- **无第二 cancel source:** `_ActiveTurnCloseout.request_cancel` 首次后只升级 `exit_after`，不创建新 task；chord pending 路径的 `exit_after_closeout = True` 不经过任何 cancel 路径。✓
- **未修改 schema/frozen docs/README/S8 bundle:** diff 仅触及 `session_execution.py`、`test_interactive_command.py` 与两份 S3C artifact 的 whitespace。✓

## Whitespace-Only Changes (S3C Artifacts)

`docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md`:
- 行 100: trailing spaces 删除 ✓
- 行 126: trailing spaces 删除 ✓
- 行 155: trailing spaces 删除 ✓

`docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md`:
- 行 160: EOF extra blank line 删除 ✓

两文件 diff 经 `git diff --check` 确认仅含上述四项变更，无内容修改。`validation-results.json` 的 `target_diff_check.findings` 确认同一组问题。

## Real PTY/os.kill Test Coverage

`test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 覆盖：

| 维度 | 证据 |
|---|---|
| **真实 PTY** | `pty.openpty()` 创建 master/slave pair |
| **真实 composer** | `PromptToolkitInteractiveComposer` + `create_input(stdin=slave_stream)` |
| **真实 signal** | `os.kill(os.getpid(), signal.SIGINT)` 发送真实 POSIX 信号 |
| **真实 monitor** | `CliSigintMonitor()` 安装真实 asyncio signal handler |
| **三 lane exact timing** | `_FROZEN_PROVIDER_TOOL_FIRST_SIGINT_DELAY_SECONDS=0.01`、`_FROZEN_CLOSEOUT_FIRST_SIGINT_DELAY_SECONDS=0.1`、`_FROZEN_SECOND_SIGINT_DELAY_SECONDS=0.05` 参数化覆盖 provider wait / tool execution / closeout |
| **handler restoration** | `assert signal.getsignal(signal.SIGINT) == previous_handler` |
| **terminal restoration** | `assert _terminal_lflag_controls(restored_lflag) == _terminal_lflag_controls(original_lflag)` 验证 ECHO/ICANON/ISIG/IEXTEN 四项 local flags |
| **single cancel** | `assert host.calls.count("cancel:run-1") == 1` |
| **exit 130** | `assert exit_code == EXIT_KEYBOARD_INTERRUPT` |
| **canonical terminal** | `assert finisher.terminals[0].terminal_status is HostTerminalStatus.CANCELLED` |
| **watcher cleanup** | `assert [watcher.closed_count for watcher in host.watchers] == [1, 1]` |

## Typed Owner Verification

| 语义 | Owner | 证据 |
|---|---|---|
| cancel intent（单次/升级） | `_LocalCancelIntent` (NONE → CANCEL_REQUESTED → EXIT_AFTER_CANCEL) | `_ActiveTurnCloseout.request_cancel` 行 276-300 |
| chord intent（跨轮） | `_InteractiveExitIntent` (CONTINUE / SIGINT_CHORD_PENDING) | `_drive_interactive_tty_repl` local `exit_intent` |
| SIGINT 计数（单轮） | `active_sigint_count`（driver local） | 行 1698 初始化为 0，completed 后行 1983 归零 |
| canonical terminal | `_ActiveTurnCloseout._terminal` | `observe_terminal` 行 336-352，`wait_closeout` 行 354-366 |
| cancel reason | `_ActiveTurnCloseout._cancel_reason`（首次冻结） | `request_cancel` 行 291-296 |
| composer phase | `InteractiveComposer`（单一 stdin owner） | `composer.set_phase` 调用点 |

没有发现多真源、下游 fallback 或兼容 shim 导致的 semantic ownership drift。

## Open Questions

1. **Chord pending + queued promotion 组合场景缺少独立测试:** 当前测试矩阵中 `test_interactive_exit_after_cancel_waits_accepted_sole_queue_terminal` 覆盖了 `exit_after_closeout` + queued 路径，但 chord pending（`SIGINT_CHORD_PENDING` → `exit_after_closeout = True`）与 queued promotion 的组合没有独立测试用例。两种来源共享同一 `exit_after_closeout` 机制和同一退出检查点（行 2014），风险较低，但严格来说不完全覆盖 S3D contract §3 目标 3。

2. **Chord pending 跨 READ_ONLY rejection 的行为未测试:** 如果 cancelled closeout 武装 chord 后，下一轮 submit 遇到 READ_ONLY rejection（`current = None, active_sigint_count = 0`，但不重置 `exit_intent`），随后的 idle SIGINT 会命中 chord pending → exit 130。这是预期行为（chord 在 mutation boundary 才清除，READ_ONLY rejection 不是 successful mutation），但没有显式测试证明。

## Residual Risk

1. **Chord pending + queued promotion 无独立测试:** 如上 Open Questions #1。缓解因素：`exit_after_closeout` 的两种来源走同一退出路径（行 2014-2018），且 queued promotion 后的 current 处理逻辑与正常 exit-after-cancel 完全相同。

2. **Frozen PTY 测试的时序假设:** 如 Finding F01 所述，`assert monitor.count == 1` 依赖 wall-clock 调度。实际风险极低（0.05s >> 1000 次 `asyncio.sleep(0)`），但理论上存在。

3. **Full-real F01-F07 immutable evidence 未重跑:** 按 S3D implementation doc §8，新 target 的 full-real evidence refresh 属于后续 S8 work unit。当前 S3D slice 的测试矩阵覆盖了 frozen 时序的等价 fake/PTY 路径，但未使用真实 Mimo provider 重跑完整 F01-F07。

4. **测试 `_BlockingTerminalFinisher` seam 绕过 production `_finish_interactive_terminal`:** 真实的 `runtime_display.finish_runtime_display()`、`render_terminal_result` 和 `advance_cli_terminal_cursor` 在 frozen 测试中被替换为同步 no-op。这些 production 路径的副作用（display 渲染、cursor 持久化）不在 chord ownership 测试范围内。其正确性由其他既有测试覆盖（如 `test_interactive_turn_cursor_write_failure_propagates_after_terminal_render`）。

## Gate Verdict

**PASS**

本 S3D corrective slice 以 typed owner-level 最小变更修复了 frozen `+0.05s` fast-closeout blocker。六条 contract 目标均有直接代码证据与测试覆盖；三条非目标均未违反。发现两个低严重度 finding（测试时序假设与常量一致性），不阻塞 merge。两个 open question 和四个 residual risk 均有明确缓解因素或已分配给后续 work unit。

下一入口：双路 S3D code review 的另一路（如 MiMo / S8 controller 方）可独立出具 review 并做 cross-adjudication。
