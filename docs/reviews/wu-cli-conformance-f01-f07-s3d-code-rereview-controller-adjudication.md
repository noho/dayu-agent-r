# WU CLI Conformance F01-F07 — S3D Re-review Controller Adjudication

## 1. Gate 与结论

- Work unit：PR 190 F03 fast-closeout corrective slice。
- 基线：`63fca270cc29d300c86e2ad0c9fddd9399913372`。
- MiMo re-review：`docs/reviews/wu-cli-conformance-f01-f07-s3d-code-rereview-mimo.md`。
- DeepSeek re-review：`docs/reviews/wu-cli-conformance-f01-f07-s3d-code-rereview-ds.md`。
- 结论：`ACCEPTED-S3D`。

Controller 逐项核对 C01、两路 re-review 和修复后代码/测试；两路 PASS 仅作输入，不替代以下
证据裁决。

## 2. C01 逐项裁决

### Composer revision owner 与 protocol

接受。`InteractiveComposer.current_input_revision()` 是无参数、只读、严格返回 `int` 的窄协议；
真实实现直接投影 composer 已有单调 `_input_revision`，key binding revision provider 复用同一
方法。driver 不产生、递增或从 draft 重算 revision，没有第二真源。

### 普通编辑/删除 mutation

接受。`_InteractiveSigintChordState.reconcile_input_revision()` 在每次 signal 消费前比较首击冻结
revision；发生输入再删除时，即使最终 draft 再次为空，revision 仍已单调变化，旧 chord/count 先
被清除，当前 SIGINT 成为新首击。真实 composer pipe test 与 driver test直接覆盖该反例。

### 首击后的 queued SUBMIT

接受。SUBMIT 先清空 chord state；旧 Run closeout arm 前再次比较 composer revision，不能以旧
active count 重建 chord。新增测试等待 run-2 实际 promotion 后发送单次 SIGINT，并证明只对 run-2
产生其唯一 graceful cancel、两个 Run watcher 均完成清理、进程不误 exit130。

### READ_ONLY rejection

接受。新 SUBMIT 在 Host acceptance 前已是 user-input mutation，SUBMIT handler 和 typed
READ_ONLY rejection 路径都显式清除 chord。无论 rejection 与旧 closeout 的调度顺序如何，旧
chord都不能在 rejection 后复活；新增测试证明后续单次 idle SIGINT只是新首击。

### 无 mutation frozen +0.05s

接受。revision 未变化时 closeout 仅在 canonical `CANCELLED` 且 active signal count 恰好为一时
arm pending chord；第二击仍跨快速 closeout exit130。真实 PTY/os.kill 三 lane test保持 single
cancel、唯一 terminal、handler/terminal flags 与 watcher cleanup 断言。

### Ownership 与结构

接受。`_InteractiveSigintChordState` 只有 revision identity、per-chord count 和 local exit intent
三个同属 chord owner 的字段，不持有 Host/composer/display/attachment 对象；Host lifecycle 继续
由 `_ActiveTurnCloseout` 拥有。未引入时间窗、轮询、强杀、第二 cancel source、fallback、兼容
shim 或 God object。

## 3. Re-review findings 逐项裁决

### MiMo：无实质 finding

接受其代码与测试证据。MiMo 原 review 遗漏的普通编辑、queued SUBMIT、READ_ONLY 三类反例已在
C01 fix 与 re-review 中直接覆盖，不再残留。

### DeepSeek defensive note：READ_ONLY 与 closeout 时序

驳回为 finding，保留为非阻塞维护说明。DeepSeek 自身的两种顺序展开均证明当前实现正确：
closeout 先 arm 时后续 SUBMIT/rejection 清除；SUBMIT/rejection 先发生时 revision mismatch 阻止
arm。没有失败输入、错误分支或可观察影响，不能分类为未修复 defect。

### DeepSeek residual：Escape 与既有 pending chord 组合

裁决为非阻塞、未扩张 oracle。当前 frozen truth 明确要求 Escape cancel 不武装 SIGINT chord，
实现以 active signal count 为零保证这一点并有直接测试。是否把 Escape 控制动作定义为“普通编辑
mutation”不是当前 accepted oracle；本 work unit 不重新裁决产品语义。若未来 oracle 对“旧 chord
pending + queued Run + Escape”给出新语义，应由 Oracle 总控建立独立 work unit，不在此擅自扩张。

### DeepSeek residual：closeout 后 active count 清零

驳回为风险。active count 是单个 active closeout 内的派生计数；closeout 完成后无条件归零、仅以
typed pending intent跨边界，是本修复要建立的所有权分离，不是信息丢失。

### DeepSeek residual：Service fake 只按 submit 推进 revision

接受为测试分层说明，不是 production risk。该 fake 的场景只产生 typed SUBMIT mutation，不模拟
字符级输入；字符级 revision owner 已由真实 PromptToolkit composer tests 覆盖。禁止为 fake 扩大
production protocol。

### Full-real refresh 与第三方 warnings

接受为后续 gate 输入。新 target 尚未执行完整 F01-F07 full-real refresh，必须在 S8 重新创建
immutable bundle；三个第三方 deprecation warnings不是本 slice 回归。

## 4. Validation accepted

- C01 聚焦矩阵：`12 passed`。
- 受影响 owner/integration 矩阵：`236 passed`。
- coverage：composer `89%`，session execution `85%`，合计 `86%`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- changed Ruff：PASS。
- `git diff --check`：PASS。

## 5. Gate decision

`ACCEPTED-S3D — READY-FOR-S3D-COMMIT-AND-S8-REFRESH`

S3D 没有 blocking open question。下一入口是在当前 branch 精确 stage/commit S3D intended files 与
durable artifacts，不带入四份 README、S8 artifact或两份 excluded self-review；随后从新 commit
执行完整、全新的 immutable S8 F01-F07 full-real evidence refresh。
