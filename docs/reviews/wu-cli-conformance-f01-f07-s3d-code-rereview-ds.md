# WU CLI Conformance F01-F07 — S3D Code Re-Review (DeepSeek, Post-C01-Fix)

## Scope

- **Mode:** current changes (uncommitted S3D corrective slice, post C01 fix)
- **Branch:** `codex/interactive-oracle`
- **Base:** `63fca270cc29d300c86e2ad0c9fddd9399913372`
- **Output file:** `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-rereview-ds.md`
- **Included scope:**
  - `dayu/cli/composer.py` — `current_input_revision()` protocol + implementation
  - `dayu/cli/session_execution.py` — `_InteractiveSigintChordState` + driver integration
  - `tests/cli/test_interactive_composer.py` — revision tracking test
  - `tests/cli/test_interactive_command.py` — 5 new C01 tests + 3 original S3D tests
  - `tests/service/test_entrypoint_runtime_interactive_path.py` — Service fake composer revision
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-fast-closeout-corrective-implementation-codex.md` — S3D implementation artifact
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-fix-codex.md` — C01 fix artifact
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-controller-adjudication.md` — controller C01 adjudication
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-mimo.md` — MiMo original review
  - `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-ds.md` — DS original review
  - S3C whitespace-only artifacts（2 files）
- **Excluded scope:** 四份既有 dirty README、S8 artifact、`code-review-20260803-075748.md`、`plan-review-20260803-064525.md`、frozen docs
- **Parallel review coverage:** 无（单一 reviewer 完整走读）

## Controller C01 逐项验证

以下逐项对照 controller adjudication (`docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-controller-adjudication.md`) 的 C01 finding，给出直接 `file:line` 证据与反例覆盖。

### C01-1: composer revision 是唯一输入 mutation owner 且 protocol 足够窄

**Protocol 定义** — `dayu/cli/composer.py:246-254`:
```python
def current_input_revision(self) -> int:
    """返回 composer 已观察到的单调用户输入版本。
    :returns: 非负且只在真实用户输入 mutation 后递增的版本。
    """
```

协议足够窄：一个无参数方法，只读投影当前 int，不暴露内部 `_input_revision` 字段、不提供 setter、不要求调用方了解 buffer/text/intent 内部状态。

**真实实现** — `dayu/cli/composer.py:517-525`:
```python
def current_input_revision(self) -> int:
    return self._input_revision
```
`_input_revision` 由 `_record_text_change`（composer 内部 key binding handler）在每次真实 buffer 文本变化时单调递增。唯一 owner 不变。

**Scripted composer** — `tests/cli/test_interactive_command.py:1224-1231`:
```python
def current_input_revision(self) -> int:
    return self._revision
```
`_revision` 在每次 SUBMIT event 或 `input_revision` 字段更新时推进。与真实 composer 的差别仅限于测试简化（scripted composer 没有逐字符编辑语义，只有每轮 SUBMIT 的 revision 跳变），不影响 revision-as-mutation-detector 的正确性。

**Service fake** — `tests/service/test_entrypoint_runtime_interactive_path.py:564-570`:
```python
def current_input_revision(self) -> int:
    return self._input_revision
```
Service 集成 fake 在每次 SUBMIT 前递增 `_input_revision`。满足协议 contract。

**Revision provider 一致性** — `dayu/cli/composer.py:368`:
```python
revision_provider=self.current_input_revision,
```
key binding 中的 revision provider 与新 public protocol 复用同一方法，不创建第二计数器。✓

### C01-2: 首击 revision 冻结与 signal/closeout reconcile 正确

**`_InteractiveSigintChordState`** — `dayu/cli/session_execution.py:386-479`:

冻结发生在第一次 signal 消费时：

- **Active signal**: `consume_active_signal(input_revision)`（行 434-445）→ 先 `reconcile_input_revision`（冻结当前 revision）→ 递增 `active_signal_count` → 返回是否达到 exit 阈值
- **Idle signal**: `consume_idle_signal(input_revision)`（行 447-458）→ 先 `reconcile_input_revision` → 若已有 chord pending 则返回 True（应退出）→ 否则设 `exit_intent = SIGINT_CHORD_PENDING`
- **Closeout arm**: `finish_active_closeout(terminal_status, input_revision)`（行 460-479）→ 若 revision 不匹配则 `clear_for_user_input_mutation()` → 否则仅在 CANCELLED + count==1 时 arm chord

**`reconcile_input_revision`** — 行 408-422:
```python
def reconcile_input_revision(self, input_revision: int) -> None:
    if self.input_revision == input_revision:
        return                    # 同 revision，保持既有 chord
    self.clear_for_user_input_mutation()  # revision 变化，清除旧 chord
    self.input_revision = input_revision  # 冻结新 revision
```

这是 C01 的核心机制：每次 signal 消费前都采样当前 composer revision；若 revision 已变（说明 signal 间发生过编辑/submit mutation），旧 chord 被清除，当前 signal 自动成为新 chord 首击。

### C01-3: idle 输入再删除结束旧 chord（反例 1）

**测试:** `test_interactive_idle_type_and_delete_end_cancelled_closeout_sigint_chord` — `tests/cli/test_interactive_command.py:4091-4145`

测试步骤:
1. Submit "current" → SIGINT → cancelled closeout → chord armed
2. 真实 PTY 输入 "x" + backspace `\x7f` → composer revision 前进 2 次
3. 断言 `edited_revision > frozen_revision`
4. 发送 SIGINT → 断言 `not driver.done()`（不 exit 130）
5. 断言 `len(host.cancel_requests) == 1`（无新 cancel）
6. EOF → exit 0

**生产路径:** idle SIGINT → `consume_idle_signal(composer.current_input_revision())` → `reconcile_input_revision(revision)` → revision 不匹配 → `clear_for_user_input_mutation()` → 当前 signal 成为新 chord 首击 → `exit_intent = SIGINT_CHORD_PENDING` → 返回 False（不退出）→ 等待下一击或 mutation。

### C01-4: 首击后 queued SUBMIT 不让旧 closeout 重新 arm（反例 2）

**测试:** `test_interactive_queued_submit_before_closeout_prevents_old_sigint_rearm` — `tests/cli/test_interactive_command.py:4149-4197`

测试步骤:
1. Submit "current" → SIGINT → cancel started（closeout 尚未完成）
2. Release composer → submit "queued" → `SUBMIT` handler 调用 `clear_for_user_input_mutation()`（行 1843）
3. Release cancel terminal → old closeout completes → `finish_active_closeout` 比较 revision
4. Revision 已不匹配（queued SUBMIT 的 `clear_for_user_input_mutation` 将 `input_revision` 设为 None，`finish_active_closeout` 收到新 composer revision）→ 不 arm chord
5. Run-2 promoted → single SIGINT → `cancel:run-2`（独立 cancel，非旧 chord 第二击）
6. Exit 0

**生产路径:**
- `SUBMIT` handler 行 1843: `sigint_chord.clear_for_user_input_mutation()` — revision 设为 None
- `finish_active_closeout` 行 470: `self.input_revision != input_revision` → True（None != composer revision）→ 清除并 return，不 arm chord

### C01-5: READ_ONLY rejection 不复活旧 chord（反例 3）

**测试:** `test_interactive_read_only_rejection_does_not_revive_old_sigint_chord` — `tests/cli/test_interactive_command.py:4201-4248`

测试步骤:
1. Submit "current" → SIGINT → cancelled closeout → chord armed
2. Submit "rejected" → Host typed READ_ONLY rejection → `sigint_chord.clear_for_user_input_mutation()`（行 2046）
3. Idle SIGINT → `consume_idle_signal` → revision 为首击后的新 revision → 设为新 chord 首击 → 不 exit 130
4. EOF → exit 0
5. `host.calls.count("cancel:run-1") == 1`、`len(host.cancel_requests) == 1`

**生产路径:** READ_ONLY rejection 后行 2046:
```python
sigint_chord.clear_for_user_input_mutation()
```
新 mutation（即使被 Host 拒绝）发生在 `exit_intent = SIGINT_CHORD_PENDING` 之后（行 1849 SUBMIT handler 已清除过一次），但因 closeout 随后调用了 `finish_active_closeout`（行 2088-2091），可能重新 arm chord。行 2046 的显式清除确保 READ_ONLY rejection 后的 idle SIGINT 不会命中旧 chord。

关键：`finish_active_closeout`（行 2088-2091）在 `clear_for_user_input_mutation`（行 2046）之后调用，但 submission 的 `clear_for_user_input_mutation` 已清除 `input_revision = None`，`finish_active_closeout` 收到的 composer revision 是 submission 后的值，与 None 不匹配 → 不 arm。

**验证:** 这不是"rejection 复活 chord"的时序问题。行 2046 的清除发生在 `current = None` 的同分支（行 2042），而 `finish_active_closeout` 在更外层（行 2088-2091），但 `current is None` 检查（行 2047）通过 `continue` 跳过了 `finish_interactive_terminal` → `finish_active_closeout` 的路径。Wait — 让我重新追踪代码路径。

实际路径（从 session_execution.py 当前代码追踪）:
1. READ_ONLY rejection 在行 1926-1946 处理：`current = None`（行 1945）、`sigint_chord.clear_for_user_input_mutation()`（行 2046 等效位置）→ `composer.set_phase(IDLE)` → `continue`（行 1958 后）
2. 因为是 `continue`，**不会**进入 `finish_active_closeout`

等等，我需要重新读取当前代码确认行号。在 C01 fix 后的代码中：

查看 diff 中的 READ_ONLY 处理（session_execution.py diff 行 1926-1946 区域）:
```python
current = None
sigint_chord.clear_for_user_input_mutation()  # 新增 C01 fix
composer.set_phase(InteractiveComposerPhase.IDLE)
```

这是 `current = None` 路径内的逻辑 —— 因为 `current is None`（行 1938），走 `continue`（行 1958），跳过 `finish_active_closeout`。

所以 READ_ONLY rejection 的 `clear_for_user_input_mutation()` 是防御性的：即使 closeout 尚未完成（submit_task 失败在 Host 层），chord state 已被清除。后续 idle SIGINT 走 `consume_idle_signal`，revision 是新值 → 成为新 chord 首击。

实际上让我再读一次当前代码，验证 READ_ONLY 路径确实有 `clear_for_user_input_mutation`。从 diff 中看到：
```
+                        sigint_chord.clear_for_user_input_mutation()
```
在行 2046（final state）。这个调用替换了原来的 `active_sigint_count = 0`。

好，确认 READ_ONLY rejection 路径确实清除了 chord state。回过来看 `finish_active_closeout` — 在这个路径中不会到达，因为 `current is None` → `continue` 跳过了终端处理。所以 `finish_active_closeout` 不会在 READ_ONLY 场景中重新 arm chord。✓

### C01-6: 无 mutation frozen +0.05s 仍 exit 130

**测试:** `test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` — 三 lane 参数化，与原始 S3D 完全一致。

C01 fix 后的行为：无 mutation 意味着 composer revision 不变。`finish_active_closeout` 比较 revision 匹配 → CANCELLED + count==1 → arm chord。第二击到达时 `consume_idle_signal` 检查 `exit_intent is SIGINT_CHORD_PENDING` → 返回 True → exit 130。

与原始 S3D 的行为完全一致，因为无 mutation 场景下 revision 比较总是匹配的。

### C01-7: queued promotion 不误取消/不残留 Run

**验证:** chord pending + `current is not None`（queued promoted）路径 — `session_execution.py` 行 1977-1988:
```python
if (sigint_chord.exit_intent is _InteractiveExitIntent.SIGINT_CHORD_PENDING):
    exit_after_closeout = True
    if composer_task is not None:
        await cancel_and_await_task(composer_task)
        composer_task = None
```
只设置 `exit_after_closeout`，不调用 `_request_interactive_cancel`，不经过 `_ActiveTurnCloseout.request_cancel`。queued run 的既有 `submit_task` 继续运行至终端。既有的 `test_interactive_exit_after_cancel_waits_accepted_sole_queue_terminal` 覆盖等价路径（共享 `exit_after_closeout` 下游）。

### C01-8: Escape/active double/single terminal/cleanup 不回归

**既有测试全部通过（6/6 regression batch）:**

| 测试 | 验证点 | 状态 |
|---|---|---|
| `test_interactive_os_sigint_first_second_and_third_follow_same_lifecycle` | OS SIGINT 三次统一生命周期（同步 fallback） | PASS |
| `test_real_posix_double_sigint_exits_after_single_canonical_closeout` | 真实 POSIX 双 SIGINT → exit 130，single cancel | PASS |
| `test_interactive_accepted_sole_queue_followup_survives_double_sigint` | accepted sole queue + double SIGINT | PASS |
| `test_interactive_ctrl_c_first_cancels_second_exits_and_third_is_noop` | 三次 Ctrl+C 矩阵 | PASS |
| `test_interactive_escape_cancel_does_not_arm_sigint_chord` | Escape 不武装 chord（C01 fix 后仍 PASS） | PASS |
| `test_interactive_submit_clears_cancelled_closeout_sigint_chord` | Submit 清除 chord（C01 fix 后仍 PASS） | PASS |

**Escape cancel 不武装分析（C01 fix 后）:**
Escape → `_request_interactive_cancel` → `closeout.request_cancel(reason, exit_after=False)` → 不经过 `_InteractiveSigintChordState` 的任何方法（因为 Escape 不是 SIGINT 路径）。closeout 完成后 `finish_active_closeout` 检查 `self.active_signal_count == _INTERACTIVE_SINGLE_SIGINT_COUNT` → `0 == 1` → False → 不 arm chord。✓

## Findings

### 编号-未修复-中-READ_ONLY rejection 的 `clear_for_user_input_mutation` 与 `finish_active_closeout` 的时序依赖

- **入口/函数:** `_drive_interactive_tty_repl` → READ_ONLY rejection 处理
- **文件(行号):** `dayu/cli/session_execution.py:2046`（`clear_for_user_input_mutation`）、`:2088-2091`（`finish_active_closeout`）
- **输入场景:** 首击 SIGINT → Host cancelled closeout 在 READ_ONLY rejection 之前完成
- **实际分支:** 如果 READ_ONLY rejection 发生在 `finish_active_closeout` 被调用之前（即 submission 很快在 Host 层失败，而 cancel/closeout 还没走到 `finish_active_closeout`），则：
  1. `clear_for_user_input_mutation()` 清除 chord（行 2046）
  2. `continue` 跳回主循环
  3. 后续 idle SIGINT 调用 `consume_idle_signal` → 当前 revision → 冻结为新首击
  4. 旧 closeout 的 `finish_active_closeout` 尚未被调用（因为 `current = None` + `continue`）

  但如果 cancel terminal 很快到达（行 2085 `terminal = await completed.closeout.wait_closeout()` 在 READ_ONLY 的 `continue` 之前已完成），`finish_active_closeout` 会在 READ_ONLY 的 `current = None` 之前被调用，此时 revision 还未被清除。

  实际上，`HostApiError`（READ_ONLY）发生在 `await completed.submit_task`（行 1926），这是 `submit_task` 的结果。此时 `cancel_task` 可能已经完成也可能还在运行。如果 cancel_task 在 submit_task 之前/同时完成，closeout 路径会先被处理（行 1918-1922 的 `cancel_task in done` 分支），然后再处理 submit_task 的异常。

- **预期行为:** 无论 cancel/closeout 和 READ_ONLY rejection 的完成顺序如何，chord 都不应在 READ_ONLY rejection 后被 arm。
- **实际行为:** 当前实现正确，因为：
  - 若 closeout 先完成 → `finish_active_closeout` 先 arm chord → READ_ONLY 的 `clear_for_user_input_mutation` 后清除 → 后续 SIGINT 不命中旧 chord ✓
  - 若 READ_ONLY 先到达 → `clear_for_user_input_mutation` 先清除 → `finish_active_closeout` 看到 revision 不匹配 → 不 arm ✓

  两种顺序都安全。时序分析确认无误。
- **直接证据:** 行 2046 `sigint_chord.clear_for_user_input_mutation()` 在 `current = None` 后立即执行；行 2088-2091 `finish_active_closeout` 只在正常 terminal 路径（非 READ_ONLY `continue`）被调用。
- **影响:** 无实际 bug。时序分析确认两种顺序都安全。
- **建议改法和验证点:** 保持现状。若未来有人重构 READ_ONLY 路径，需保留 `clear_for_user_input_mutation()` 调用。可在 `_InteractiveSigintChordState` 的 docstring 注明这一点。
- **修复风险（低）:** 无需修改。
- **严重程度（低）:** 当前实现正确，无实际缺陷。作为 defensive note 记录，防止未来重构引入时序问题。

评审员注：本 finding 源自 adversarial 时序探索，最终确认没有 bug。按 review 纪律保留为"无实际缺陷"的低严重度 finding，供后续重构参考。

## Controller C01 Rereview Summary

| C01 检查项 | Verdict | 直接证据 |
|---|---|---|
| composer revision 是唯一 input mutation owner | PASS | `composer.py:246-254` protocol, `:517-525` 真实实现, `test_interactive_composer.py:468-499` revision tracking test |
| protocol 足够窄 | PASS | 单一 `current_input_revision() -> int` 方法，无参数，只读投影 |
| 首击 revision 冻结正确 | PASS | `session_execution.py:408-422` `reconcile_input_revision`, `:434-445` `consume_active_signal` |
| signal/closeout reconcile 正确 | PASS | `session_execution.py:460-479` `finish_active_closeout` 比较 revision 后决定 arm |
| idle 输入再删除结束旧 chord | PASS | `test_interactive_command.py:4091-4145` 真实 PTY 输入/删除 → SIGINT 不 exit 130 |
| queued SUBMIT 结束旧 chord | PASS | `test_interactive_command.py:4149-4197` queued submit → old closeout 不 re-arm → independent cancel on run-2 |
| READ_ONLY rejection 结束旧 chord | PASS | `test_interactive_command.py:4201-4248` rejection 后 idle SIGINT 不 exit 130 |
| 无 mutation frozen +0.05s 仍 exit 130 | PASS | 三 lane frozen PTY test unchanged, 8/8 pass |
| queued promotion 不误取消 | PASS | `session_execution.py:1977-1988` chord pending+current→`exit_after_closeout` only |
| Escape 不武装 chord | PASS | `finish_active_closeout` 中 `active_signal_count==0`，`0 != 1` → 不 arm |
| Active double SIGINT 不回归 | PASS | Existing `test_interactive_ctrl_c_first_cancels_second_exits_and_third_is_noop` PASS |
| Single canonical terminal/cleanup 不回归 | PASS | Existing regression batch 6/6 PASS |

## State Machine Verification

### `_InteractiveSigintChordState` 状态转换

```
                    ┌──────────────────────────────────────┐
                    │         clear_for_user_input()        │
                    │  (SUBMIT / EOF / READ_ONLY / revise)  │
                    ▼                                      │
              ┌──────────┐                                 │
              │ NO CHORD │◄────────────────────────────────┤
              │ rev=None │                                  │
              │ cnt=0    │                                  │
              │ intent=  │                                  │
              │ CONTINUE │                                  │
              └────┬─────┘                                  │
                   │ idle SIGINT                            │
                   │ consume_idle_signal(rev)               │
                   ▼                                        │
         ┌─────────────────────┐                            │
         │ IDLE CHORD PENDING  │                            │
         │ rev=frozen          │                            │
         │ cnt=0               │                            │
         │ intent=CHORD_PEND   │                            │
         └────────┬────────────┘                            │
                  │ next SIGINT                             │
                  │ (current=None → exit 130)               │
                  │ (current≠None → exit_after_closeout)    │
                  │                                         │
   active SIGINT   │                                         │
   consume_active  │                                         │
   _signal(rev)    ▼                                         │
         ┌─────────────────────┐                            │
         │ ACTIVE FIRST HIT    │────────────────────────────│
         │ rev=frozen          │                            │
         │ cnt=1               │                            │
         │ intent=CONTINUE     │                            │
         └────────┬────────────┘                            │
                  │                                         │
          ┌───────┴────────┐                                │
          │                │                                │
    finish_active_   finish_active_                         │
    closeout:        closeout:                              │
    CANCELLED        !CANCELLED or                          │
    cnt==1           cnt≠1                                  │
    rev matches      or rev≠match                           │
          │                │                                │
          ▼                ▼                                │
   ┌────────────┐   ┌──────────┐                            │
   │ CHORD PEND │   │ NO CHORD │ (back to start)           │
   └────────────┘   └──────────┘                            │
```

**Terminal/absorbing states:**
- `_LocalCancelIntent.EXIT_AFTER_CANCEL`（在 `_ActiveTurnCloseout` 中，不在 chord state 中）是 absorbing
- Chord state 本身没有 terminal state — 它的语义是"下一次 SIGINT 应该退出"，实际退出由 `exit_after_closeout` 或 idle `return EXIT_KEYBOARD_INTERRUPT` 完成

**幂等性:**
- `reconcile_input_revision` 对同 revision 重复调用是 no-op（行 418-419）
- `clear_for_user_input_mutation` 重复调用是幂等的（所有字段重置为默认值）
- `consume_active_signal` 重复调用（同 revision）递增 count，多 signal batch 走 `for` loop
- `finish_active_closeout` 只能调用一次（每次 closeout 只触发一次）

### `_ActiveTurnCloseout` 与 `_InteractiveSigintChordState` 的关系

两个 typed state machine 职责分离：
- `_ActiveTurnCloseout`: 拥有 per-turn cancel/acceptance/terminal 协调（`_LocalCancelIntent`、`_cancel_task`、`_terminal`）
- `_InteractiveSigintChordState`: 拥有跨轮 Ctrl+C chord 语义（`input_revision`、`active_signal_count`、`exit_intent`）

它们在 `finish_active_closeout` 中交汇：`_ActiveTurnCloseout.intent`（`_LocalCancelIntent.EXIT_AFTER_CANCEL`）优先于 chord arm（行 2088-2089 先检查 `EXIT_AFTER_CANCEL`，再调用 `finish_active_closeout`）。这是正确的分层：per-turn 语义（第二击在本 turn 内）强于跨轮语义（第一击在已完成的 turn）。

## Semantic Ownership Drift Check

| 语义 | Owner | 有无漂移 |
|---|---|---|
| input mutation revision | `InteractiveComposer`（唯一） | 无 — `current_input_revision()` 是窄只读投影 |
| active turn cancel intent | `_ActiveTurnCloseout._LocalCancelIntent`（唯一） | 无 |
| cross-turn chord intent | `_InteractiveSigintChordState.exit_intent`（唯一） | 无 |
| SIGINT signal count | `CliSigintMonitor.count`（durable）→ `_InteractiveSigintChordState.active_signal_count`（per-chord 派生） | 无 — count 是 monotic source of truth，chord state 只做 per-revision 本地消费 |
| composer phase | `InteractiveComposer`（唯一） | 无 |
| Host cancel | `_ActiveTurnCloseout.cancel_task`（唯一 canonical cancel path per turn） | 无 |
| canonical terminal | `_ActiveTurnCloseout._terminal`（唯一） | 无 |
| attachment lifecycle | `_InteractiveSessionAttachmentController`（唯一） | 无 |

没有发现多真源、下游 fallback、`hasattr`/`getattr`、loose parsing 或兼容 shim 导致的 semantic ownership drift。

## God Object / Structural Clarity Check

`_InteractiveSigintChordState`:
- 3 个字段（`input_revision`、`active_signal_count`、`exit_intent`）→ 不是 God object
- 5 个窄方法，每个方法单一职责
- 不持有 composer、Host、display、attachment 引用
- 只在 `_drive_interactive_tty_repl` 内创建和使用 → 局部状态，不泄漏到其他 driver

`_drive_interactive_tty_repl`:
- C01 fix 将 3 个分散的局部变量（`exit_intent`、`active_sigint_count` + revision tracking）合并为 1 个 typed dataclass
- 变量数从 3 减到 1 → 结构改善
- 原 DS review F02（常量一致性）在 refactor 后自动解决 — `consume_active_signal` 内部使用 `_INTERACTIVE_EXIT_SIGINT_COUNT`

## Adversarial Checks

### 多 signal batch
`for _interrupt_index in range(pending_interrupts)` 循环内 `consume_active_signal` 首次调用 `reconcile_input_revision` 冻结 revision，后续调用跳过 reconcile（同 revision）→ 所有 signal 归属同一 chord。✓

### Revision 变化时当前 signal 应为新首击
`reconcile_input_revision` → `clear_for_user_input_mutation()` → 当前 revision 冻结 → 随后 `active_signal_count += 1` 成为新首击计数。若 `exit_after = (count >= 2)` → count 刚被清零再递增为 1 → `exit_after` 为 False。✓

### Successful terminal 不 arm chord
`finish_active_closeout` 只检查 `HostTerminalStatus.CANCELLED` → SUCCEEDED/FAILED/LOST 不 arm。同时 `active_signal_count` 被清零但 `input_revision` 在 `exit_intent == CONTINUE` 时也清除。✓

### Cancelled terminal with different revision
`finish_active_closeout` 先检查 `self.input_revision != input_revision` → 不匹配则 `clear_for_user_input_mutation()` 并 return → 不 arm。✓

### SUBMIT timing variants
- **SUBMIT before closeout**: `clear_for_user_input_mutation()` 清除 → `finish_active_closeout` 比较 revision 不匹配 → 不 arm ✓
- **SUBMIT after closeout arm**: `clear_for_user_input_mutation()` 清除 chord → 下一击不命中旧 chord ✓
- **SUBMIT between first SIGINT and closeout**: controller C01-4 (queued SUBMIT) 覆盖 ✓

### Idle 空 prompt SIGINT（chord 不应在此误触）
S3C 既有 test `test_interactive_first_idle_keyboard_interrupt_redisplays_prompt_without_exit`：空 prompt 首次 Ctrl+C 不 exit。C01 fix 后路径：idle → `consume_idle_signal` → revision frozen → `exit_intent = SIGINT_CHORD_PENDING` → 返回 False → 不退出。第二次 Ctrl+C：`consume_idle_signal` → revision 匹配（无 mutation）→ `exit_intent is SIGINT_CHORD_PENDING` → 返回 True → exit 130。与既有行为一致。✓

## Open Questions

无。

## Residual Risk

1. **Escape cancel 在 chord pending 时的交互无独立测试:** 如果 chord pending 后用户通过 Escape（而非 SIGINT）取消一个新 active turn，`active_signal_count` 不会被消费（Escape 不走 chord state），但 closeout 的 `finish_active_closeout` 会检查 `active_signal_count == 1` → 若不等于一（因 Escape 未递增）则不重新 arm chord。这是正确的（Escape 不等于 SIGINT），但无显式测试覆盖该组合。

2. **`_InteractiveSigintChordState` 的 `active_signal_count` 在 `finish_active_closeout` 后无条件清零（行 476）:** 如果两次 active SIGINT 都是同一 revision 的首击（极端不可能的场景：两个独立的单 SIGINT turn，之间没有 mutation），第二次 turn 的 `active_signal_count` 也会从零开始递增。这是正确行为，但值得在 state machine doc 中显式说明。

3. **Full-real F01-F07 immutable evidence 未重跑:** 仍属后续 S8 work unit。C01 fix 的 owner-level 和 integration 测试矩阵（146 passed）覆盖了所有新增和回归路径。

4. **Service integration composer fake 的 revision 以 submit 计数而非编辑计数:** `_FreshQueuedLifecycleComposer.current_input_revision()` 返回已提交次数而非逐字符编辑版本。这在 Service 测试场景中是充分的（Service 测试不覆盖字符级编辑 mutation），但若未来 Service 测试覆盖 CHAR-level chord，需要更新 fake。

## Gate Verdict

**PASS**

C01 fix 以 typed `_InteractiveSigintChordState` 将 input revision 冻结、signal reconcile 和 closeout arm 统一为单一 owner，完全满足 controller adjudication 的全部要求。8 项 C01 检查点均有直接 `file:line` 代码证据与 owner-level 测试覆盖。新增 5 个 C01 反例测试 + 1 个 composer protocol 测试均通过，既有回归矩阵无退化。pyright 0 errors。没有发现新的实质性缺陷。一个低严重度 defensive note（READ_ONLY 时序分析）供未来重构参考，不阻塞 merge。

下一入口：MiMo re-review 与 controller final adjudication。
