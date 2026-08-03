# WU CLI Conformance F01-F07 — S3C Real-evidence Corrective Implementation

## 1. Gate 与结论

- **Gate：** S3C corrective implementation slice
- **Work unit：** PR 190 F03 immutable-evidence corrective
- **基线 target：** `016d834adba509fbf7d1dc8749d474ed9f09ade4`
- **状态：** `READY-FOR-DUAL-S3C-CODE-REVIEW`
- **下一入口：** 双路 S3C code review
- **Git 操作：** 未 stage、未 commit、未 push

本 slice 只修复 S8 immutable evidence 暴露的三项 F03 真实偏差。没有修改 frozen oracle/scenario，
没有修改或暂存既有四份 README 与三份 S8/自审 artifact，也没有处理 Authorization durable
residual。

## 2. 输入证据与 first-principles 判断

实现前读取并交叉核对：

- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md`；
- `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`；
- `docs/reviews/code-review-20260803-075748.md`；
- `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T000310Z-016d834adba5-r2/bundle`。

冻结输入 hash 与 S8 记录一致：

| 输入 | SHA-256 |
|---|---|
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` |
| `docs/cli_ci.md` | `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82` |

最终 r2 bundle 的 `shasum -a 256 -c SHA256SUMS` 全部通过，说明本轮判断使用的失败证据未被改写。

问题动机成立，且三项偏差都位于 CLI input/composer owner 或其直接 driver handoff：

1. Enter 退出第一段 PromptToolkit application 后，driver 在 Host acceptance 前禁止重新 arm
   composer；standalone Escape 因此没有 live input owner，并且 composer 只有 Ctrl+C 的 pending
   submit bridge。
2. interactive Escape binding 对 provisional Escape callback 立即退出 application，未先证明是否有
   同一个 ESC-prefixed continuation，因此 exact Alt+X 存在误 cancel 路径。
3. terminal closeout 可以在下一次 SIGINT waiter 消费 durable count 前清空 `current` 与
   `active_sigint_count`；第二次真实 SIGINT 随后落入 idle 语义，不能升级同一 turn 的
   exit-after-closeout。

Host 已经是 accepted Run、graceful cancel 与 canonical terminal 的唯一 owner；把默认 cancel、第二
cancel source 或强杀逻辑下沉到 Host 不能修复输入丢失，反而会产生多真源。因此修复边界保持在 CLI。

## 3. Approved slice contract

### 目标与成功信号

- Enter 后 0/10/20ms standalone Escape 均穿越两个 PromptToolkit application 的 handoff，绑定
  随后 accepted 的同一个 Run，只请求一次 graceful cancel；唯一 cancelled terminal 完成后返回 REPL。
- ESC prefix 必须先等待 continuation；exact Alt+X、CSI、Home、Delete 与 bracketed paste 完整
  sequence 不得取消。只有 ambiguity timeout 后仍无 continuation，且 key/data 都精确为单一 Escape，
  才产生 `CANCEL_RUN`。
- provider wait、tool execution 与 terminal closeout 的第二个真实 POSIX SIGINT 在 `current` 清空前
  单调升级同一个 closeout；唯一 `RUN_CANCELLED` 与 watcher/attempt cleanup 完成后 exit 130，不需要
  第三个 signal。

### 非目标

- 不改 Service / Host / Engine cancel contract，不增加 cancel source 或 downstream fallback。
- 不使用业务 sleep/time-window 推断 Run identity；唯一 timeout 是终端 ESC sequence 的输入歧义解析。
- 不修 Authorization durable projection residual，不修改 schema，不做兼容 shim。
- 不重跑 S8 full-real provider bundle；该动作属于本 slice 双路 review 接受后的新 target evidence refresh。

该设计只增加一个精确 `SUBMITTING` phase、pending submit document、PromptToolkit handoff flush 和一个
active SIGINT count consumer；没有创建通用 terminal framework、God helper 或跨层协议，因此未过度设计。

## 4. 实现

### `dayu/cli/composer.py`

- 新增 `SUBMITTING` phase。Enter chord 在 input owner 内同步进入该 phase，driver 无需靠调度时间猜测
  submit 是否存在。
- pending submit 使用独立 typed document snapshot；第二个 PromptToolkit application 可以立即以空
  buffer 接管 stdin，而 acceptance 仍能把原 exact draft 写入 history，READ_ONLY rejection 仍能恢复原
  draft/cursor。
- 第二个 application 在统一输入歧义期后，通过 PromptToolkit input/key processor seam flush 上一个 app
  遗留、尚未形成 `KeyPress` 的 ESC prefix；完整 continuation 若已到达，会先由同一 parser 解析。
- `Escape + Any` 是完整 chord binding；Alt/meta continuation 不发 cancel，`Escape + Ctrl+T` 只保留
  continuation 自身动作。standalone binding 同时校验单 member、`Keys.Escape` 与原始 `"\x1b"` data。
- PromptToolkit 的 VT parser flush 与 key-binding ambiguity timeout 共用一个明确常量；没有依据 Run/Host
  时间做判断。

### `dayu/cli/run_keys.py`

- 将既有 0.1 秒 ESC sequence ambiguity 常量提升为 CLI input owner 共用的 typed 常量，prompt monitor 与
  interactive composer 不再各自定义漂移值。

### `dayu/cli/session_execution.py`

- current turn 创建后立即把 composer 置为 `SUBMITTING` 并允许第二个 app 在 acceptance barrier 期间读取；
  queued acceptance 仍阻塞第三份 mutation，保持 sole queue contract。
- READ_ONLY 分支先关闭 handoff app，再恢复 pending submit document。
- `_consume_interactive_active_sigints` 只把 durable count 增量投影到当前 `_ActiveTurnCloseout`；首次创建
  single graceful cancel task，第二次及以后只单调升级/保持 exit intent。
- terminal render/cursor cleanup 的 await 返回后、`current` 清空前再次 reconcile monitor count，避免真实
  第二个 signal 在 closeout ordering 中被重置。退出仍发生在 canonical terminal 与 outer cleanup 之后。

## 5. 测试变更与 owner assertions

### PromptToolkit pipe / PTY

- exact Alt+X 同 chunk 与歧义期内跨 chunk 均不 cancel；CSI、Home、Delete、bracketed paste 完整序列不
  cancel。
- standalone Escape 等 parser/key ambiguity resolution 后才产生一次 cancel。
- 真实 POSIX PTY 继续断言完整序列解析、普通 Enter、standalone Escape，以及 echo/canonical terminal
  flags 恢复。
- Enter 后 0/10/20ms 使用真实 PromptToolkit pipe，经 delayed public acceptance barrier 验证：一个
  submit、一个 exact `run-1` graceful cancel、一个 cancelled terminal、history 写入一次、取消后继续
  REPL 并 exit 0。

### POSIX SIGINT / durable Host owner

- provider wait、tool activity 与 closeout 三个阶段均用真实 `os.kill(os.getpid(), SIGINT)` 两次；断言
  durable monitor count=2、single cancel、唯一 canonical cancelled terminal、两个 watcher 均关闭、
  exit 130、SIGINT handler 恢复，且不发送第三个 signal。
- 既有真实 CLI → Service → Host integration 继续断言取消路径最终没有 non-terminal Run，current
  `RunStatus.CANCELLED / AttemptStatus.CANCELLED`，sole queued Run/Attempt 成功终态。本轮把该测试纳入
  focused validation，避免 fake Host 代替 durable Run/Attempt truth。
- scripted composer fake 迁移到 `SUBMITTING` contract：pre-accept 只允许 control event 穿越，后续 submit
  等 acceptance；测试不再用旧调度行为倒逼 production 保留 gap。

## 6. Validation

| 检查 | 结果 |
|---|---|
| F03 focused：run_keys + composer + interactive + prompt + real durable Host integration | `217 passed`，3 个第三方 deprecation warnings |
| 同一 CLI owner coverage run | `216 passed`；composer 89%、run_keys 93%、session_execution 85%，合计 87% |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-file Ruff | `PASS` |
| r2 immutable bundle `SHA256SUMS` | 全部 `OK` |
| frozen oracle/scenario/docs hashes | 与 S8 frozen record 一致 |

最终 `git diff --check` 在 artifact 写入后执行并记录于交付说明。

## 7. Docs decision

本 slice 没有改变已冻结的用户可见 contract，只把 production 行为修正到 oracle 与现有 README 已描述的
语义。四份 README 的当前 diff 属于 S8 controller 既有改动，按用户要求原样保留，未修改、未暂存。
本轮只新增本 artifact。

## 8. Findings 与 residual risks

| 项目 | 状态 | 分类 / owner |
|---|---|---|
| DR-S8-01 / F03 三项真实偏差 | `已修复`，等待双路 code review | fixed in current slice |
| 新 target 的 full-real F01-F07 immutable evidence | 尚未重跑 | covered by later approved S8 evidence refresh；owner 为后续 S8 controller |
| resolved Authorization durable persistence | 本轮未修 | assigned to later independent work unit；owner 为 effective-execution durable projection |
| 第三方 deprecation warnings | 非本 slice 回归 | tracked by dependency maintenance，不阻塞 S3C review |

没有 unclassified residual risk，没有 blocking open question。

## 9. Gate marker

`READY-FOR-DUAL-S3C-CODE-REVIEW`

