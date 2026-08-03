# Code Re-Review — S3D Fast-closeout + C01 Chord-lifetime Fix (MiMo)

## Scope

- Mode: Current Changes (S3D review-fix gate, uncommitted)
- Branch: `codex/interactive-oracle`
- Base: `63fca270cc29d300c86e2ad0c9fddd9399913372`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-rereview-mimo.md`
- Included scope:
  - `dayu/cli/composer.py` (Protocol + implementation: `current_input_revision()`)
  - `dayu/cli/session_execution.py` (`_InteractiveSigintChordState` + driver wiring)
  - `tests/cli/test_interactive_composer.py` (revision tracking test)
  - `tests/cli/test_interactive_command.py` (6 new tests + helpers + `_AcceptedThenReadOnlyControlledHost` + `_ReadOnlyChordBarrierComposer`)
  - `tests/service/test_entrypoint_runtime_interactive_path.py` (`_FreshQueuedLifecycleComposer.current_input_revision()`)
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-fast-closeout-corrective-implementation-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-fix-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md` (trailing whitespace)
  - `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md` (EOF blank line)
- Excluded scope: four dirty README, S8 artifact, excluded self-review artifacts, frozen docs, `code-review-20260803-075748.md`, `plan-review-20260803-064525.md`
- Parallel review coverage: 无
- Controller input: `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-controller-adjudication.md`
- Original MiMo review: `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-mimo.md`

## Findings

未发现实质性问题。

## Controller C01 逐项验证

### C01 定义

controller 裁定：typed post-cancel chord lifetime 必须在下一次 user-input mutation boundary 结束，
不只在 `SUBMIT` / `EOF` event 结束。composer 的单调 input revision 是唯一 mutation 检测 owner。

### C01 反例 1：idle 输入再删除后 Ctrl+C 不得 exit 130

**修复机制**：`_InteractiveSigintChordState.reconcile_input_revision()`（`session_execution.py:411-427`）。
在每次 signal 消费前调用，比较 composer 当前 revision 与冻结的 `self.input_revision`。若 revision
变化（输入/删除/粘贴），先 `clear_for_user_input_mutation()` 再把当前 revision 冻结为新 chord identity。

**代码路径**：
1. 首击 active SIGINT → `consume_active_signal` 冻结 `input_revision=R0`，`active_signal_count=1`
2. Host cancelled closeout → `finish_active_closeout`（`session_execution.py:455-481`）：
   `terminal_status=CANCELLED`，`active_signal_count==1` → `exit_intent=SIGINT_CHORD_PENDING`
3. 用户键入 "x" 再删除 → composer revision 变为 `R0+2`
4. 第二次 SIGINT（idle）→ `consume_idle_signal(R0+2)`（`session_execution.py:441-453`）：
   - `reconcile_input_revision(R0+2)`：`R0+2 != R0` → `clear_for_user_input_mutation()` + 冻结 `R0+2`
   - `exit_intent` 已被清除为 `CONTINUE` → 不返回 `True` → 设 `SIGINT_CHORD_PENDING` 为首击
   - 不 exit 130 ✓

**测试**：`test_interactive_idle_type_and_delete_end_cancelled_closeout_sigint_chord` 使用真实
`PromptToolkitInteractiveComposer` + `create_pipe_input`，发送 `"x"` + `"\x7f"` (backdelete)，
断言 `edited_revision > frozen_revision`、`exit_code == EXIT_SUCCESS`、`cancel_requests == 1`。✓

### C01 反例 2：首击后 queued SUBMIT 不得让旧 closeout 重 arm chord

**修复机制**：`finish_active_closeout`（`session_execution.py:469-473`）在 closeout arm 前比较
`input_revision` 参数（closeout 完成时 composer 的当前 revision）与 `self.input_revision`（首击冻结的
revision）。若不一致，`clear_for_user_input_mutation()` 后直接返回。

**代码路径**：
1. 首击 active SIGINT → `input_revision=R0`，`active_signal_count=1`
2. 用户提交 queued SUBMIT → `clear_for_user_input_mutation()`（`session_execution.py:1842`）：
   `input_revision=None`，`active_signal_count=0`，`exit_intent=CONTINUE`
3. composer revision 现在是 `R1`（SUBMIT 作为 mutation 推进了 revision）
4. 旧 closeout 完成 → `finish_active_closeout(terminal_status=CANCELLED, input_revision=R1)`：
   - `self.input_revision`（`None`）`!= R1` → `clear_for_user_input_mutation()` + 返回
   - chord 不被重 arm ✓
5. queued run 晋升 → 第二次 SIGINT → `reconcile_input_revision(R1)`：`None != R1` → 冻结 `R1`
   为首击 → `consume_active_signal` → `active_signal_count=1` → 不 exit ✓

**测试**：`test_interactive_queued_submit_before_closeout_prevents_old_sigint_rearm` 使用
`_BarrierScriptedComposer(("current", "queued"), blocked_call_index=2)`，在首击后释放 queued
SUBMIT，等待 closeout 完成和 run-2 promotion，再发第二次 SIGINT。断言 `exit_code == EXIT_SUCCESS`、
`cancel:run-1 == 1`、`cancel:run-2 == 1`、`cancel_requests == 2`。✓

### C01 反例 3：READ_ONLY rejection 不得复活旧 chord

**修复机制**：READ_ONLY rejection 路径（`session_execution.py:2043-2047`）调用
`sigint_chord.clear_for_user_input_mutation()`。该 SUBMIT 已是 user-input mutation，即使 Host
以 typed READ_ONLY 拒绝，chord 也必须被清除。

**代码路径**：
1. 首击 active SIGINT → `input_revision=R0`，closeout → `SIGINT_CHORD_PENDING`
2. 用户提交新 SUBMIT → `clear_for_user_input_mutation()`（行 1842）：清除 chord
3. Host typed READ_ONLY rejection → 行 2046 `clear_for_user_input_mutation()`：再次清除
4. 第二次 SIGINT（idle）→ `consume_idle_signal(current_revision)`：`reconcile` 冻结新 revision，
   `exit_intent=CONTINUE` → 设为首击 → 不 exit 130 ✓

**测试**：`test_interactive_read_only_rejection_does_not_revive_old_sigint_chord` 使用
`_AcceptedThenReadOnlyControlledHost`（首次 accept、后续 READ_ONLY rejection）+
`_ReadOnlyChordBarrierComposer`。断言 `exit_code == EXIT_SUCCESS`、`cancel_requests == 1`。✓

### C01 验证：无 mutation frozen +0.05s 仍 exit 130

**修复机制**：`reconcile_input_revision` 在 revision 未变化时直接 return（`session_execution.py:424-425`）。
`finish_active_closeout` 在 `input_revision == self.input_revision` 时保留 chord（行 471-478）。

**代码路径**：
1. 首击 → `input_revision=R0`
2. 无用户输入 → revision 仍为 `R0`
3. closeout → `finish_active_closeout(CANCELLED, R0)`：`R0 == R0` ✓，`active_signal_count==1` ✓
   → `SIGINT_CHORD_PENDING`
4. 第二次 SIGINT → `consume_idle_signal(R0)`：`reconcile` 不变，`exit_intent=SIGINT_CHORD_PENDING`
   → `return True` → exit 130 ✓

**测试**：`test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 参数化 3 条 frozen
lane，使用真实 PTY + `os.kill(SIGINT)` + `call_later(0.05s)`。断言 `exit_code == EXIT_KEYBOARD_INTERRUPT`。✓

## 原 MiMo Review Findings 逐项 Re-Review

### 1. Fast cancelled closeout 跨 closeout exit 130

原 review 结论：PASS。Re-review：`finish_active_closeout` 替换了原 `elif` 分支，逻辑等价但增加了
revision 校验。revision 未变化时行为与原 S3D 一致。✓

### 2. Single canonical cancel/terminal

原 review 结论：PASS。Re-review：`_ActiveTurnCloseout.request_cancel` 不变，单 turn 单 cancel task。
`_consume_interactive_active_sigints` 仍通过 `sigint_chord.consume_active_signal` 管理阈值。✓

### 3. Queued current 不被误取消

原 review 结论：PASS。Re-review：`SIGINT_CHORD_PENDING` + `current is not None` 路径
（`session_execution.py:1989-1996`）只设 `exit_after_closeout`，不发额外 cancel。新增
`test_interactive_queued_submit_before_closeout_prevents_old_sigint_rearm` 直接覆盖。✓

### 4. Submit/编辑 mutation 清除旧 chord

原 review 结论：PASS（仅基于 SUBMIT event）。Re-review：C01 修复后，revision-based reconciliation
覆盖所有 user-input mutation（输入、删除、粘贴、SUBMIT、EOF、READ_ONLY rejection）。SUBMIT/EOF
仍显式调用 `clear_for_user_input_mutation()`；普通编辑由下次 signal/closeout 的 `reconcile_input_revision`
隐式生效。覆盖范围扩大且语义正确。✓

### 5. Escape cancel 不武装

原 review 结论：PASS。Re-review：Escape 不经过 SIGINT 消费路径，`active_signal_count` 保持 0。
`finish_active_closeout` 中 `active_signal_count == 1` 条件不满足。✓

### 6. Active closeout 原语义不回归

原 review 结论：PASS。Re-review：`EXIT_AFTER_CANCEL` 升级路径（行 2086-2087）在
`finish_active_closeout` 调用前执行，不受影响。`exit_after_closeout` 标志仍由
`_consume_interactive_active_sigints` 设置。既有 236 tests 全通过。✓

### 7. 真实 PTY/os.kill 三 lane

原 review 结论：PASS（行为正确性，非毫秒精确性）。Re-review：不变。✓

### 8. Typed owner、无时间窗/强杀/第二 cancel source

原 review 结论：PASS。Re-review：`_InteractiveSigintChordState` 是窄 typed dataclass，只在
`_drive_interactive_tty_repl` 内实例化和消费。`current_input_revision()` 是 Protocol 上的只读
projection。无时间窗、无 `os.kill`、无新 cancel 通道。✓

## Adversarial 检查

### 多 signal batch

`_consume_interactive_active_sigints` 循环处理 `interrupt_count` 个 signal。每次调用
`consume_active_signal` 时 `reconcile_input_revision` 只在 revision 变化时清除一次；后续 signal
在同一新 revision 下继续累加。`consume_idle_signal` 同理。正确。✓

### Revision 变化时当前 signal 应为新首击

`reconcile_input_revision` 先 `clear_for_user_input_mutation()`（重置 count/intent/revision），
再 `self.input_revision = input_revision`（冻结新 revision）。后续 `active_signal_count += 1` 从 0
开始，当前 signal 成为新 chord 首击。✓

### Successful vs cancelled terminal

`finish_active_closeout` 只在 `terminal_status is CANCELLED` 且 `active_signal_count == 1` 时
arm chord。successful terminal 不满足 `CANCELLED` 条件 → `exit_intent` 保持 `CONTINUE` →
`input_revision` 被清除（行 480-481）。✓

### SUBMIT 在 closeout arm 前后

- **前**：SUBMIT 先 `clear_for_user_input_mutation()`，closeout 时 `input_revision` 已变化 → 不 arm。
- **后**：closeout 先 arm `SIGINT_CHORD_PENDING`，SUBMIT 后 `clear_for_user_input_mutation()` 清除。
  两种顺序都正确。✓

### State invariant

- `input_revision`：`None` ↔ 非负 int。`None` 表示无 chord；非负表示首击冻结的 revision。
- `active_signal_count`：非负。`finish_active_closeout` 和 `clear_for_user_input_mutation` 均重置为 0。
- `exit_intent`：`CONTINUE` ↔ `SIGINT_CHORD_PENDING`。`clear_for_user_input_mutation` 重置为
  `CONTINUE`；`consume_idle_signal` 和 `finish_active_closeout` 设为 `SIGINT_CHORD_PENDING`。
- 无循环引用、无泄漏、无孤儿状态。✓

### God object / ownership drift

`_InteractiveSigintChordState` 职责单一：管理 chord 的 revision identity、signal count 和 exit intent。
`current_input_revision()` 是 Protocol 上的只读 projection，不暴露 composer 内部状态。revision 仍由
composer 唯一拥有（`_record_text_change` 递增），chord state 由 driver 唯一拥有。无 ownership drift。✓

## Residual Risk

| 项目 | 说明 |
|---|---|
| Full-real F01-F07 immutable evidence refresh | 尚未在新 target 重跑。由后续 S8 controller 覆盖。 |
| 第三方 deprecation warnings | 3 个非本 slice 回归。 |
| `finish_active_closeout` 中 `input_revision` 时序 | 当前 `composer.current_input_revision()` 在 closeout 完成时读取。若 closeout 期间用户快速输入再删除使 revision 变化又回到相同文本，revision 仍单调递增，chord 会被清除——这是正确行为（revision 变化 = mutation 发生过）。无风险。 |

## Open Questions

无。

## Gate Verdict

**PASS**

C01 的 4 项阻塞验证全部通过：idle 输入再删除清除旧 chord（revision reconciliation）、首击后
queued SUBMIT 不让旧 closeout 重 arm（`finish_active_closeout` revision 比较）、READ_ONLY
rejection 不复活旧 chord（显式 `clear_for_user_input_mutation`）、无 mutation frozen +0.05s 仍
exit 130（revision 不变 → chord 保留）。composer `current_input_revision()` 是窄 typed protocol
projection，`_InteractiveSigintChordState` 职责单一无 ownership drift。6 项新 owner tests +
既有 236 tests 全通过，pyright 0 errors。原 MiMo 8 项 findings 全部 re-confirm PASS。
