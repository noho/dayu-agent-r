# WU-CLI-INIT-01 S4 Code Review Adjudication

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- Gate：`code review adjudication`
- 唯一目标边界：
  `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Accepted scope：
  `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- Implementation：
  `docs/reviews/wu-cli-init-01-s4-implementation-codex.md`
- Independent reviews：
  - `docs/reviews/wu-cli-init-01-s4-code-review-mimo.md`
  - `docs/reviews/wu-cli-init-01-s4-code-review-ds.md`
- Decision：`PASS`
- 下一入口：Controller validation / S4 commit

## Review verdicts

- AgentMiMo：`PASS`，未发现 material finding。
- AgentDS：`PASS`，未发现 material finding。

两路均独立确认：

1. tracked diff 只包含五个 accepted code/test files；
2. ConfigLoader 两个 revert-only 文件对 S1–S3 基线零 diff；
3. PRESERVE 只补真正缺失项，已有用户 bytes 保留；
4. OVERWRITE 只接管 ordinary-file `config`，保留 `.dayu`；
5. RESET 接管 ordinary-file `config` / `.dayu`，保留 portfolio、assets 与其它
   non-init-owned roots；
6. cleanup 以既有 `PathIdentity.mode` 为真源分派 `unlink` / `rmtree`；
7. `backup_records` 保持 3-tuple，`_rollback_or_raise(...)` 无净 diff；
8. fd reader、snapshot loader、typed filename、`_PrivatePathShape`、
   ctime/nlink 和 race/fault matrix 均无残留；
9. 测试断言真实 tree、bytes、identity 与真实 ConfigLoader/Service 加载结果，
   不依赖 CLI 自报 mode。

## Non-blocking notes

- Windows ordinary-file publication 的真实平台 smoke 未在当前 Darwin 主机执行，
  沿用既有跨平台 CI / Issue `#184` 跟踪。
- 外部并发文件系统 mutation 明确不属于本 work unit。
- 根 README 的最终用户文案同步由 accepted S6 承接。
- DeepSeek 关于 staging destination symlink check 的维护性备注不影响当前流程：
  public config tree 已先由 `_validate_ordinary_tree(...)` 拒绝 symlink；不据此扩大
  当前修改。

## Controller decision

没有需要返回 AgentCodex 修复的 finding。S4 实现通过 code review，可以进入
Controller 最终验证与 slice commit。
