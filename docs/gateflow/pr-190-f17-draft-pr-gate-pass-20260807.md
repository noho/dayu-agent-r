# PR 190 F17 Draft PR Gate Pass

## Result

Gate：`Draft PR Gate`，结果 `pass-with-explicit-gaps`。

这只表示 F17 work unit 已按 Gateflow 复用并更新既有 draft PR 190；不表示 PR ready、GitHub CI
PASS、formal scenario accepted、Oracle readiness 或 merge authorization。

## Remote facts

- PR：190
- URL：`https://github.com/noho/dayu-agent-r/pull/190`
- State：`OPEN`
- Draft：`true`
- Mergeable / state：`true` / `clean`
- Base：`main`
- Head ref：`codex/interactive-oracle`
- Head SHA：`386da1fd6aea0b9b36b5cada50efce2969462cfa`
- Requested reviewers：无
- Submitted reviews：无
- Checks：no checks reported

远端 branch `refs/heads/codex/interactive-oracle` 与 PR API head 均精确为上述 SHA。push 使用普通
fast-forward push；没有 force-push、rebase、merge、mark ready、approve、request reviewers、
GitHub review/comment 或新 PR 创建。

## Accepted evidence

- Plan：`0d215296`
- Implementation：`305c1012`
- Aggregate review：`33f6c16d`
- Aggregate formatting fix：`dcc08399`
- PR review acceptance：`386da1fd`
- PR review acceptance artifact：
  `docs/gateflow/pr-190-f17-pr-review-acceptance-20260807.md`

## Explicit gaps

- GitHub 没有 status checks；本地验证不能伪装成远端 CI PASS。
- 三条 formal replacement scenarios 仍为 `unadjudicated`，不得生成 readiness proof 或改变
  registry status。
- F17 是 deterministic init publication truth 修复，没有执行新的真实 provider/PTY/Oracle 场景；
  这与前序 F14/F15/F16 real observation evidence 分开报告。

下一 gate 为 final closeout；只允许提交/推送 closeout evidence，不改变 PR readiness 或外部 review 状态。
