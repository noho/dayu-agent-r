# S3B Code Re-review 总控裁决

## Gate 与输入

- **Gate:** S3B code re-review
- **实现基线:** `eae09be97963382c49fbf71195820637a4baa948`
- **输入档案:** S3B 首轮双路 review、Controller 首轮裁决、Codex fix artifact、Mimo/DeepSeek re-review artifacts。
- **验证事实:** S3B focused matrix `206 passed`；full pyright `0 errors, 0 warnings, 0 informations`；changed Ruff 与 `git diff --check` 通过；staged diff 为空。

## Re-review 逐项裁决

| 来源 | 结论或 finding | 裁决 | 直接理由 |
|---|---|---|---|
| Mimo | accepted READ_ONLY pending-submit-intent finding 已闭环，无新 finding | **接受** | `reject_submit_delivery()` 位于 composer typed owner，只将 `_pending_submit_intent` 置为 false；owner test 证明 draft、cursor、revision、pending editable draft 与 history 原样保留。唯一生产调用位于 typed READ_ONLY、未跨 acceptance barrier 的 rejection 分支。integration test 证明 rejection 后 idle SIGINT 不产生 cancel，fresh attachment 重提复用同一 `client_request_id` 且 Host 只接受一个 Run。 |
| DeepSeek | `reject_submit_delivery()` 重复调用安全幂等，但 guard 不区分首次与重复 rejection，标低 | **拒绝为 finding** | 审查自身确认无外部可见缺陷、当前路径不存在重复进入且重复赋值安全。typed contract 并未承诺暴露 rejection 次数；新增第二个“已拒绝”状态反而会复制无业务消费者的状态并扩大 owner surface。当前 `_pending_submit` 表达可恢复的 pending editable draft，`_pending_submit_intent` 表达是否仍应跨 delivery barrier 绑定输入，二者分离正是 frozen F03/F04 所需。 |

## Residual 逐项裁决

- rejection 与下一次 `read_event()` 之间 `_pending_submit` 仍为真：这是保存 exact editable draft 的 owner contract，不是时序泄漏。READ_ONLY 分支在下一轮读取前取消同一 turn acceptance task；不存在额外 `accept_submit` 调用点。
- integration test 使用 typed scripted composer：owner state 由真实 `PromptToolkitInteractiveComposer` pipe-input test 覆盖；driver/Host attachment、idempotency 和 signal 归属由 deterministic integration test 覆盖。最终 S8 immutable bundle 必须再提供真实 PTY/Host 证据，测试不冒充 full-real evidence。
- `_wait_for_sigint_rearm` 的有界 event-loop polling 只用于测试同步，1000 次 cooperative yield 有明确 failure；不进入生产语义。
- CLI display cleanup 与 Authorization 持久化继续作为独立 work-unit residual，不在本 slice 扩张修复。

## Gate 结论

**ACCEPTED-SLICE-COMMIT**。首轮唯一 accepted finding 已在正确 owner 闭环；两路 durable re-review 均验证核心修复，DeepSeek 新列低项不构成产品、correctness 或 contract 缺陷。允许只 stage S3B production/tests 与本 gate artifacts 并提交；四份 S8 README 和 S8 implementation artifact 必须继续留在 working tree，等待新的 post-fix conformance refresh gate。
