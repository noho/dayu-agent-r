# WU CLI Conformance F01-F07 — S3D Code Review Fix

## 1. Gate 与结论

- **Work unit：** PR 190 F03 fast-closeout corrective slice
- **Gate：** 同一 S3D review-fix gate
- **基线 target：** `63fca270cc29d300c86e2ad0c9fddd9399913372`
- **Controller 输入：** `docs/reviews/wu-cli-conformance-f01-f07-s3d-code-review-controller-adjudication.md`
- **修复范围：** 只修 accepted controller C01
- **状态：** `READY-FOR-DUAL-S3D-REREVIEW`
- **下一入口：** MiMo 与 DeepSeek 双路 S3D code re-review
- **Git 操作：** 未 stage、未 commit、未 push

两路 reviewer 的共同 PASS 没有覆盖 direct owner truth：typed post-cancel chord lifetime 必须在
下一次 user-input mutation boundary 结束，而不是只在 `SUBMIT` / `EOF` event 结束。controller
C01 动机成立且为阻塞 correctness finding；本 gate 未接受或顺带修复其他 reviewer finding。

## 2. Root cause 与 semantic owner

直接代码证据：

1. `InteractiveComposerEvent.input_revision` 已声明它用于识别两次 Ctrl+C 之间的普通编辑；
2. `PromptToolkitInteractiveComposer._record_text_change` 在 composer 实际观察到 buffer 文本变化时
   单调递增 `_input_revision`；输入、删除、粘贴和编辑都从这一 owner 产生事实；
3. 原 S3D driver 只在 typed `SUBMIT` / `EOF` event 清除 `_InteractiveExitIntent`，无法观察 closeout
   后输入再删除这种“draft 最终相同、revision 已变化”的 mutation；
4. 首击后 queued SUBMIT 虽先清除 intent，旧 closeout 仍会按遗留 active count 重 arm，说明 exit
   intent 与 count 必须共享同一 frozen revision identity。

因此最佳 owner 设计不是给 composer 增加 chord callback/event，也不是在 driver 比较 draft 或计时；
而是由 composer 继续唯一拥有单调 revision，通过 `InteractiveComposer.current_input_revision()` 窄
typed protocol 只读投影。driver 的 chord owner 冻结首击 revision，在每次 signal 消费与 closeout
arm 前比较。revision 变化时清除旧 intent/count；若当前正在消费 signal，再把它作为新 chord 首击。

## 3. Production 修复

### Composer owner projection

- `dayu/cli/composer.py` 为 `InteractiveComposer` 增加
  `current_input_revision() -> int`。
- 真实 composer 直接返回既有 `_input_revision`，不新增第二计数器；key binding revision provider
  同样复用该 projection。
- Service integration fake 与 scripted composer 只按各自真实 scripted mutation 推进 revision，
  没有 loose parsing、默认值、`getattr` 或 `hasattr`。

### Driver chord owner

- `dayu/cli/session_execution.py` 用窄 `_InteractiveSigintChordState` 同地持有首击 revision、active
  signal count 与既有 typed `_InteractiveExitIntent`。
- active/idle signal 消费前均 reconcile 当前 composer revision；revision 变化会同时清除旧 chord
  与 active count，当前 signal 随后按新首击处理。
- closeout arm 前再次比较 revision；只有 terminal 为 canonical `CANCELLED`、revision 未变化且
  active SIGINT 恰为一次时，才保留 `SIGINT_CHORD_PENDING`。
- `SUBMIT`、`EOF` 和 typed READ_ONLY rejection 仍是显式清除边界；普通编辑/删除无需新 event，
  由下一个 signal 或 closeout arm 的 revision 比较生效。
- Host graceful cancel、canonical terminal、attachment 和 cleanup 生命周期未改；未增加时间窗、
  轮询、强杀、第二 cancel source、fallback 或通用 coordinator。

## 4. Owner-level tests

- 真实 composer protocol test：普通输入和删除分别单调推进 public revision，EOF event 投影相同值。
- idle 输入再删除反例：首次 active SIGINT 快速完成 cancelled closeout；真实输入/删除后下一次
  SIGINT 不 exit 130、不增加 cancel，EOF 正常退出。
- queued-before-closeout 反例：首击后、旧 closeout 前产生 queued SUBMIT；旧 closeout 不得重 arm，
  run-2 promotion 后的单次 SIGINT 对 run-2 发出其唯一 graceful cancel 并正常退出。
- typed READ_ONLY 反例：新 mutation 被 Host typed 拒绝后，单次 idle SIGINT 不直接 exit 130，旧
  chord 不复活。
- frozen `+0.05s` provider wait/tool/closeout 三 lane 仍真实 `os.kill(SIGINT)` exit 130，并保持
  single cancel、唯一 canonical CANCELLED、handler/terminal 恢复。
- standalone Escape 不武装 chord、active double SIGINT、submit mutation、sole queue、terminal 与
  watcher cleanup 既有回归继续通过。

## 5. Validation

| 检查 | 结果 |
|---|---|
| C01 聚焦 owner/regression matrix | `12 passed` |
| 受影响完整 CLI owner/integration matrix | `236 passed`，3 个第三方 deprecation warnings |
| coverage | composer `89%`；session execution `85%`；合计 `86%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed-file Ruff | `PASS` |
| `git diff --check` | `PASS` |

## 6. Scope preservation 与 residual risk

- 未修改 controller、MiMo、DeepSeek review artifacts。
- 未修改四份 README、S8 implementation artifact、两份 excluded self-review artifacts 或 frozen docs。
- 没有 schema、LLM-facing 文本、Service/Host/Engine lifecycle 或用户工作流变化，因此无需 README 更新。
- 新 target 的 full-real F01-F07 immutable evidence 仍属于后续已批准 S8 evidence refresh，不在本
  review-fix gate 执行。
- 第三方 deprecation warnings 属于 dependency maintenance，不是本 slice 回归。

没有未分类 residual risk，没有 blocking open question。

## 7. Gate marker

`READY-FOR-DUAL-S3D-REREVIEW`
