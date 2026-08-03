# WU CLI Conformance F01-F07 — S3D Code Review Controller Adjudication

## 1. Gate 与输入

- Work unit：PR 190 F03 fast-closeout corrective slice。
- 基线：`63fca270cc29d300c86e2ad0c9fddd9399913372`。
- MiMo artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-mimo.md`。
- DeepSeek artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-ds.md`。
- 判定：`NEEDS-FIX`。

本裁决不以两路 review 的共同 PASS 代替证据。逐项核对 reviewer finding、residual risk、
frozen scenario 和 immutable root-cause owner evidence 后，controller 新增一项阻塞 finding。

## 2. Reviewer findings 逐项裁决

### MiMo：无正式 finding

裁决：不直接接受 PASS。MiMo 对 fast-closeout、single cancel、Escape、active closeout 与
真实 PTY 证据的代码走读成立；但其“正常新用户 submit/编辑 mutation 清除旧 chord”只引用
`SUBMIT` event 和 submit test，没有证明 application 运行期间的普通文本编辑会清除 chord。
该遗漏由 controller finding C01 收口。

### MiMo residual：queued current 缺少独立组合测试

裁决：接受其“存在 coverage gap”的事实，但不接受“不阻塞”的分类。新 production 分支在
`SIGINT_CHORD_PENDING` 且 `current is not None` 时只设置 `exit_after_closeout`，这是本 slice
新增的独立行为，现有 `EXIT_AFTER_CANCEL` queued test 不能证明该来源。更关键的是，queued
submit 与文本编辑都可能是结束旧 chord 的 user-input mutation；必须随 C01 一并补直接测试。

### DeepSeek F01：PTY `monitor.count == 1` 可能因负载误失败

裁决：驳回为 non-finding。该断言的目的就是证明本次测试确实进入“Host closeout 早于 frozen
第二击”的目标分支；如果环境负载使第二击先发生，测试没有证明该分支，失败比放宽为
`count <= 2` 更正确。`TimerHandle.when()` 或额外 `sleep(0)` 也不能建立更强保证。保留当前
精确断言，后续 full-real frozen scenario 才是最终 conformance 证据。

### DeepSeek F02：计数递增未复用 single-count 常量

裁决：驳回为 style non-finding。`active_sigint_count += 1` 表达一次 loop iteration 消费一次
signal，不是业务阈值；把递增单位替换为 threshold 常量会混淆语义，并不能提升 correctness。

### DeepSeek open question：chord pending + queued promotion 缺少测试

裁决：接受并升级到 C01 的验证要求。该分支是生产新增路径，必须有 owner-level 反例，而不能
只依赖共享的 `exit_after_closeout` 下游变量。

### DeepSeek open question：READ_ONLY rejection 后 chord 行为未测试

裁决：部分接受、语义说明驳回。DeepSeek 将 READ_ONLY rejection 解释为“不是 successful
mutation”，但 immutable owner truth 是“下一次 user-input mutation boundary”，并不要求 Host
接受 mutation。一次新的 SUBMIT 在进入 Host 前就已是用户输入 mutation，因此必须清除旧
chord；READ_ONLY rejection 不得复活它。应补 direct test 或由已有 submit-before-host test 明确
覆盖该顺序。

### DeepSeek residual：terminal finisher seam 未覆盖真实 render/cursor

裁决：接受为非阻塞的测试分层说明。S3D owner test隔离 chord ownership，既有 terminal
render/cursor tests 与后续 full-real S8 覆盖真实投影；不得因此把 UI/render 变成 chord owner。

## 3. Controller finding

### C01 — 阻塞 — chord lifetime 没有在下一次普通编辑 mutation 结束

- 直接真源：immutable `root-cause-owner-evidence.json` 明确规定 typed post-cancel chord state
  的 lifetime “ends at the next user-input mutation boundary, never at a business-time window”；
  S8 blocker artifact 同样写明“下一次用户输入 mutation boundary”。
- 直接代码：`InteractiveComposerEvent.input_revision` 的 contract 已声明该 revision 用于判定两次
  Ctrl+C 之间的正常编辑，`PromptToolkitInteractiveComposer._record_text_change` 会在每次真实
  buffer 文本变化时单调递增 revision；但 `InteractiveComposer` protocol 没有向 driver 暴露当前
  revision，S3D driver 也只在收到 `SUBMIT` / `EOF` event 时清除 `exit_intent`。
- 反例 1：第一次 active SIGINT 后 Host 快速 cancelled closeout，composer 回到 idle；用户键入再
  删除文本（revision 已变化、draft 再次为空）后按 Ctrl+C。当前代码仍命中
  `SIGINT_CHORD_PENDING` 并直接 exit 130，把 mutation 后的首次 Ctrl+C 误判成旧 chord 第二击。
- 反例 2：第一次 active SIGINT 后、closeout 前用户提交 queued follow-up。该 `SUBMIT` 当时清除
  的是尚未 arm 的 `CONTINUE`，随后旧 Run closeout 又无条件按 `active_sigint_count == 1` arm
  chord；因此发生在首击后的新 mutation 没有结束旧 chord。
- 反例 3：新 SUBMIT 遭 READ_ONLY rejection 仍然是 user-input mutation；不得因 Host 未接受而
  恢复或保留旧 chord。
- Owner-level fix：由 composer 继续唯一拥有单调 input revision，并通过窄 typed protocol
  投影当前 revision；CLI chord owner 在首击时冻结 revision，在每次 signal 消费及 closeout arm
  前与当前 revision 比较。revision 已变化时先清除旧 chord/active count，再把该 signal 作为新
  chord 首击。不要引入毫秒窗口、轮询、`getattr`、下游 fallback 或第二 cancel source。
- 验证：至少补真实或 owner-level反例，覆盖 idle 文本编辑后首次 Ctrl+C 不 exit130、首击后
  queued SUBMIT 不让旧 closeout 重新 arm、READ_ONLY rejection 不复活旧 chord，以及无 mutation
  的 frozen +0.05s 三 lane 仍 exit130。现有 Escape、active double-SIGINT、single canonical
  terminal/cleanup tests 必须继续通过。

严重度：阻塞。当前实现修复 frozen happy path，但没有满足其自身采用的 typed chord lifetime
contract，若直接进入 S8 会把普通输入 mutation 后的 SIGINT 错投影为退出意图。

## 4. Gate decision

`NEEDS-FIX-S3D`

下一入口：同一 S3D slice 由 AgentCodex 修复 C01、更新 implementation artifact、运行 owner
tests/coverage/full pyright/Ruff/diff-check；随后 MiMo 与 DeepSeek 在同一 review gate re-review，
controller 再逐项裁决。不得 commit 或进入 S8。
