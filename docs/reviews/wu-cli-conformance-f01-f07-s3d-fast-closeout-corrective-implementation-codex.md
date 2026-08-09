# WU CLI Conformance F01-F07 — S3D Fast-closeout Corrective Implementation

## 1. Gate 与结论

- **Gate：** S3D corrective implementation / accepted C01 review-fix
- **Work unit：** PR 190 F03 exact-timeline blocker
- **基线 target：** `63fca270cc29d300c86e2ad0c9fddd9399913372`
- **状态：** `READY-FOR-DUAL-S3D-REREVIEW`
- **下一入口：** 双路 S3D code re-review
- **Artifact：** `docs/reviews/wu-cli-conformance-f01-f07-s3d-fast-closeout-corrective-implementation-codex.md`
- **Git 操作：** 未 stage、未 commit、未 push

本 slice 先修复新 immutable partial bundle 暴露的 frozen `+0.05s` fast-closeout
blocker，随后在同一 S3D review-fix gate 只修复 controller accepted C01，并为已提交 S3C
artifacts 做用户点名的纯 whitespace 修正。未修改 frozen
oracle/scenario/docs、四份既有 dirty README、S8 implementation artifact 或两份 excluded
self-review artifacts。

## 2. 输入证据与 first-principles 判断

实现前读取并交叉核对：

- frozen 三条 interactive double POSIX SIGINT scenarios；
- `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`；
- S3C implementation、两份 code review 与 controller adjudication artifacts；
- `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T005803Z-63fca270cc29/bundle`；
- `dayu/cli/session_execution.py`、`tests/cli/test_interactive_command.py` 及相关 composer/run-key/Service tests。

immutable bundle 的直接事实是：provider wait、tool execution、closeout 三条 frozen lane
都在第一次 signal 的 `after-action +0.05s` 发出第二个 SIGINT；Host 均只产生一次
`CANCEL_REQUESTED` 与一次 canonical `RUN_CANCELLED`，但 CLI 均超时并被 harness SIGTERM，
未自行 exit 130。bundle `SHA256SUMS` digest 为
`1baee636b99db8aec60d8af66ce86b81c7cce609e3851dbfd63f1e7146e1e050`，逐项校验通过。

问题动机成立，且 root cause 与失败数据同源：

1. active turn 第一次 SIGINT 已由 `_ActiveTurnCloseout` 请求唯一 graceful cancel；
2. Host terminal 若在第二击前完成，driver 在 closeout 后把 `current` 清空并把
   `active_sigint_count` 归零；
3. 第二击只能落入 `_InteractiveExitIntent` 的 idle 首击分支，因此进程继续等待第三击或用户输入；
4. Host 已正确完成唯一 cancel/terminal，改变 Host 生命周期、增加 cancel source 或强杀都不是根因修复。

初版修复确认 CLI driver 已有 typed `_InteractiveExitIntent` 是“本地下一击 SIGINT 是否退出”的
owner，但 controller C01 的直接反例进一步证明：只在 `SUBMIT` / `EOF` event 清除 intent，不足以
满足“下一次 user-input mutation boundary”契约。composer 已有单调 `input_revision`，并在真实
buffer 文本变化时递增，因此编辑事实必须继续由 composer 唯一拥有；driver 只能通过窄 typed
protocol 读取当前 revision，不得从 draft、事件顺序或时间反推 mutation。

## 3. Approved S3D contract

### 目标与成功信号

- 第一次 active SIGINT 请求 graceful cancel 后，如果 Host cancelled closeout 在 frozen 第二击前完成，
  已消费的第一击继续由 typed chord intent 持有。
- 下一次 SIGINT 视为同一 chord 的第二击并 exit 130；同一已完成 closeout 不再发送 cancel。
- 如果 closeout 后已有此前 accepted queued Run，第二击只登记退出并等待其既有 terminal，不增加 cancel source。
- 下一次普通编辑、删除、`SUBMIT`、`EOF` 或 READ_ONLY rejected submit 等 user-input mutation
  boundary 都结束旧 chord；下一次 SIGINT 必须成为新 chord 首击。
- standalone Escape cancel 的 active SIGINT count 为零，不得武装 chord intent。

### 非目标

- 不增加毫秒或业务时间窗；`0.05s` 只存在于 frozen owner test 输入。
- 不强杀、不增加第二 cancel source、不修改 Service / Host / Engine 生命周期。
- 不修改 schema、frozen docs、README 或 S8 evidence bundle。
- 不在本 slice 执行 dual review、commit、push 或新 full-real provider refresh。

该方案只给既有 composer protocol 增加当前 revision 的只读 typed projection，并用一个窄
`_InteractiveSigintChordState` 聚合 revision、active count 与既有 exit intent；没有新增事件、
coordinator、跨层协议、轮询或通用状态框架，因此是满足 fast-closeout 与 C01 的最小 owner-level 修复。

## 4. Production 实现

### `dayu/cli/composer.py`

- `InteractiveComposer` 新增 `current_input_revision() -> int` 窄 typed projection。
- `PromptToolkitInteractiveComposer` 直接返回既有 `_input_revision`；该值仍只由 composer 的真实
  text-change owner 单调递增，driver 不产生、修改或重算 revision。
- key binding 的 revision provider 复用同一 public projection，保持单一真源。

### `dayu/cli/session_execution.py`

- 将 `_InteractiveExitIntent.IDLE_EXIT_PENDING` 精确改名为
  `SIGINT_CHORD_PENDING`，使该 typed state 能表达 idle 首击和 cancelled closeout 后保留的
  active 首击，而不是错误绑定到某个 driver phase。
- 新增窄 `_InteractiveSigintChordState`，只持有首击 revision、active signal count 与既有 typed
  exit intent；没有吸收 Host lifecycle、cancel、terminal 或 composer 职责。
- 每次消费 active/idle SIGINT 前读取 composer 当前 revision；若与首击冻结值不同，先清除旧
  chord/count，再把当前 signal 作为新 chord 首击。
- cancelled terminal closeout arm 前再次比较 revision；仅在 revision 未变且只消费一次 active
  SIGINT 时把 chord intent 置为 pending。queued SUBMIT 若发生在旧 closeout 前，其 revision 变化
  因而阻止旧 closeout 重 arm。
- cancelled terminal 完成时，仅在 active signal count 为一时把 chord intent 置为 pending；
  Escape cancel 的计数为零，重复 SIGINT 已由 `_LocalCancelIntent.EXIT_AFTER_CANCEL` 持有，均不会误入该分支。
- pending chord 收到下一次 SIGINT 时：无 active Run 立即返回 130；若此前 queued Run 已晋升，
  只设置既有 `exit_after_closeout` 并等待其 terminal，不向它发送额外 cancel。
- 保留 `SUBMIT` / `EOF` typed 清除，并在 READ_ONLY rejection closeout 明确清除；普通编辑/删除则
  由下一次 signal 或 closeout arm 的 revision 比较同步终结旧 chord。
- 用两个私有 typed count constants 取代本 slice 触及的裸一击/二击阈值；没有引入时间判断。

## 5. Owner-level tests

### Frozen fast-closeout matrix

`test_real_posix_frozen_double_sigint_survives_fast_cancelled_closeout` 参数化覆盖 provider wait、
tool execution 与 closeout 三条等价路径：

- 使用真实 PTY、真实 `PromptToolkitInteractiveComposer` 和真实 `os.kill(SIGINT)`；
- provider/tool 首击按 frozen `+0.01s`，closeout 首击按 frozen `+0.10s` 调度；
- 第二击由 event loop 在第一次 action 后精确 `+0.05s` 调度；
- Host cancel terminal barrier 预先放行，并在第二击前断言 composer 已回到 `IDLE` 且 monitor count 仍为一；
- 断言 exit 130、single graceful cancel、唯一 CANCELLED terminal、两个 watcher 各关闭一次、
  SIGINT handler 恢复，以及 PTY ECHO/ICANON/ISIG/IEXTEN flags 恢复。

该测试在 production 修复前稳定复现 driver timeout，修复后 3/3 通过，因此不是只验证 fake
内部字段的自证测试。

### Mutation 与 Escape 反例

- `test_current_input_revision_tracks_type_and_delete_mutations`：真实 prompt-toolkit pipe 输入逐次执行
  普通输入与删除，断言 public revision 由 composer owner 单调推进，EOF event 投影同一 revision。
- `test_interactive_idle_type_and_delete_end_cancelled_closeout_sigint_chord`：快速 closeout 后真实输入再
  删除使 draft 恢复为空；下一次 SIGINT 只能成为新首击，driver 不 exit 130 且不产生额外 cancel。
- `test_interactive_queued_submit_before_closeout_prevents_old_sigint_rearm`：第一次 active SIGINT 后、旧
  closeout 前投递 queued SUBMIT；run-2 promotion 后的单次 SIGINT 必须 cancel run-2，而非被旧 closeout
  chord 直接解释为 exit 130。
- `test_interactive_read_only_rejection_does_not_revive_old_sigint_chord`：首轮快速 cancel 后的新 SUBMIT
  收到 typed READ_ONLY rejection；随后单次 idle SIGINT不得直接退出，证明 rejected mutation 不会
  复活旧 chord。
- `test_interactive_submit_clears_cancelled_closeout_sigint_chord`：第一轮单 SIGINT cancelled closeout
  后提交第二轮；第二轮的单次 SIGINT 必须产生 `cancel:run-2` 并最终 exit 0，证明新 mutation
  清除了旧 chord state。
- `test_interactive_escape_cancel_does_not_arm_sigint_chord`：standalone Escape 完成 cancelled closeout
  后，单次 idle SIGINT 不得直接 exit 130；随后 EOF 清理并 exit 0。
- 既有 active double-SIGINT、third no-op、accepted sole queue、READ_ONLY、early submit、composer
  sequence 与真实 Service/Host integration tests 全部继续通过。

## 6. Validation

| 检查 | 结果 |
|---|---|
| S3D C01 聚焦回归矩阵 | `12 passed` |
| 受影响 CLI owner/integration matrix | `236 passed`，3 个第三方 deprecation warnings |
| coverage | `dayu/cli/composer.py = 89%`；`dayu/cli/session_execution.py = 85%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-file Ruff | `PASS` |
| immutable bundle `SHA256SUMS` | 全部 `OK`；digest 与 S8 artifact 一致 |
| frozen oracle/scenario/docs hashes | 与 S8 artifact 一致 |
| `git diff --check` | `PASS` |

## 7. Docs 与 workspace decision

- 本 slice 只让 production 符合既有 frozen 用户契约，没有新增用户操作、测试层级或架构边界；
  按 README 自身职责与用户明确边界，不修改四份既有 dirty README。
- `docs/reviews/wu-cli-conformance-f01-f07-s3c-code-review-ds.md` 仅删除行 100、126、155
  的 trailing spaces。
- `docs/reviews/wu-cli-conformance-f01-f07-s3c-real-evidence-corrective-implementation-codex.md`
  仅删除 EOF extra blank line。
- 保留且未修改 `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`、
  `docs/reviews/code-review-20260803-075748.md`、`docs/reviews/plan-review-20260803-064525.md`。

## 8. Findings 与 residual risks

| 项目 | 状态 | 分类 / owner |
|---|---|---|
| F03 frozen fast-closeout exact timeline blocker | `已修复`，等待双路 S3D re-review | fixed in current slice |
| C01 chord lifetime 普通编辑/queued/READ_ONLY 反例 | `已修复`，等待双路 S3D re-review | fixed in current slice |
| 新 target 的 full-real F01-F07 immutable evidence | 尚未重跑 | covered by later approved S8 evidence refresh；owner 为后续 S8 controller |
| resolved Authorization durable persistence | 本轮未修 | assigned to later independent work unit；owner 为 effective-execution durable projection |
| 第三方 deprecation warnings | 非本 slice 回归 | tracked by dependency maintenance，不阻塞 S3D review |

没有 unclassified residual risk，没有 blocking open question。

## 9. Gate marker

`READY-FOR-DUAL-S3D-REREVIEW`
