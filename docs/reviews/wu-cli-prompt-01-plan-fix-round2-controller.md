# WU-CLI-PROMPT-01 Plan Review Fix Round 2

## Gate

- Work Unit：`WU-CLI-PROMPT-01`
- gate：`plan re-review -> fix`
- reviewed artifact：`docs/reviews/plan-review-20260731-181839.md`
- fixed target：`docs/reviews/wu-cli-prompt-01-plan-controller.md`
- decision：`ready-for-plan-re-review`
- next entry point：`re-review`

## Finding Adjudication

### PR-001 — accepted / 已修复

第二轮最小实验确认 subparser action 收到独立 namespace，无法访问顶层 per-parse list；因此第一轮
custom action 修复无效。计划现已改为：

- root、command、二级 action 各自拥有不同 typed selector occurrence dest；
- 三套 parent 由同一个 option-to-canonical spec 注册，不复制 selector 语义；
- `session`/`tool_trace` action parser 显式使用 action-scope parent；
- parse 后 finalizer 合并三份 list 并校验总 occurrence；
- 每次 parse 使用 fresh lists，不在 parser/action/global state 保存 collector；
- tests 覆盖 root/command/action 任意两层及同一 parser 连续 invocation 隔离。

该设计不依赖跨 namespace mutation、不扫描 raw argv，也不引入 prompt-only shim。

### PR-002 / PR-003 / PR-004 — 已修复，证据保持有效

本轮没有改动已通过的 startup complete-main boundary、logger+handler 双 gate 或 S6 docs slice；
其上一轮 re-review 证据继续有效。

## Validation

- 修订计划已明确 parent assembly、dest ownership、finalizer data flow 与连续调用测试。
- 本 fix 只修改 plan artifact；未修改生产代码、测试或冻结 registry。
- `git diff --check` 在下一次 re-review 前运行。

## Residual Risks

- scope parent 重构可能意外改变非 selector 全局参数位置；S5 必须保留现有 root/command/action
  参数位置 tests，并用全 command parser smoke 覆盖，分类为 fixed in S5。
- 其余 residual risk 保持由 S3、S5 与 final validation 覆盖。

不存在未分类 residual risk 或 blocking open question。

## Completion

第二轮 plan fix 完成，重新进入 `re-review`；pass 前不得进入 implementation。
