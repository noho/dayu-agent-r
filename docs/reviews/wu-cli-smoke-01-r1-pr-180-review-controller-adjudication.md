# WU-CLI-SMOKE-01-R1 Draft PR #180 Review Controller Adjudication

## Scope

- Gate: Draft PR #180 strict PR review。
- Reviewed head: `ff5d515a`。
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-mimo.md`（AgentMiMo，PASS，1 个 non-blocking low note）。
  - `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-ds.md`（AgentDS，PASS，0 finding）。
- Controller direct metadata checks:
  - `gh pr view 180 --json ...`。
  - `gh pr checks 180`。
  - `gh pr view 180 --json body --jq .body | sed -n '1,8l'`。

## Motivation / Owner Check

两路 reviewer 均确认远端代码 diff 与 accepted aggregate 状态一致：三类 delta owner、zero-row、after-commit publish、terminal fence、multi-watcher、bounded slow-consumer、Host→Service→CLI public union、测试、设计与控制文档均无 merge 前代码缺陷。

但 controller 的直接 GitHub metadata 读取证明 PR body 不是 reviewer 所述的正常 Markdown 多行文本：其值包含字面量反斜杠加 `n`，例如首段以 `## 摘要\n\n- 将 ...` 形式存在。该问题来自创建 PR 时 shell 参数没有把 JSON escape 还原为实际换行，不涉及仓库实现 owner；GitHub PR metadata/body 是本 gate 的直接 owner。

## Decisions

### MiMo low note：`api.py` 格式化 diff 噪声

- `accepted-as-non-blocking-note`，不形成 current fix 或 residual risk。
- 格式化由本 WU 同一文件的 typed contract 修改触发，pyright、全量测试与两轮 code/aggregate review 均通过；没有语义变化、merge conflict 或错误定位成本的直接反例。
- 现在反向拆分/重写已 accepted commits 只会扩大 PR churn。后续大规模格式化应独立提交，但本 PR 无需修复。

### DS PASS 与代码/架构结论

- `accepted`。
- 0 个 production/test current-fix finding。远端 head/base、Draft 状态、无 reviewer request、无错误 `Closes` footer、diff 完整性及架构/测试证据均成立。

### PR180-F01：PR body 使用字面量 `\n` 而非真实换行

- `accepted`，严重度 low，blocking for draft-PR-pass。
- 直接证据：`gh pr view 180 --json body --jq .body | sed -n '1,8l'` 显示整个 body 由 `\n` 字面量连接；GitHub API JSON 亦返回双重转义。内容文字本身正确，但 Markdown 结构没有按标题、段落和列表渲染。
- Root owner: GitHub PR #180 body metadata，不是 Host/Service/CLI 生产代码或仓库 Markdown 文档。
- Fix：使用真实多行 body file 调用 `gh pr edit 180 --body-file ...`；不得改变标题、Draft 状态、base/head、review requests 或添加 `Closes` footer。
- Validation：重新读取 body，确认真实换行存在且无字面量 `\n`；确认 `isDraft=true`、`reviewRequests=[]`、head 仍为 `ff5d515a` 或仅因后续 fix artifact/control commit按流程推进，代码 diff 不变。

## Fix Handoff

- Agent: AgentCodex。
- Risk: Low Risk / PR-metadata-only。
- Allowed external change: 仅 PR #180 body 的换行格式；文字内容保持与 controller accepted body 相同。
- Allowed repository change: 仅 `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-codex.md`；可在 `workspace/tmp/` 创建并删除 body 临时文件。
- Forbidden: production/test/design/README/control 修改、commit、push、PR state change、review request、comment、issue 操作。
- Required validation:
  - `gh pr view 180 --json body,isDraft,reviewRequests,baseRefName,headRefName,headRefOid`。
  - body 中没有字面量反斜杠-n，且包含真实 Markdown 标题/列表换行。
  - `git status --short` 只新增 fix artifact 与 controller/reviewer artifacts/control 预期变更。
- Stop status: fix 与 artifact 完成后停止，等待 AgentMiMo / AgentDS 双路 PR re-review。

## Decision

`fix-required`。唯一 accepted finding 为 controller direct PR metadata finding PR180-F01；仓库代码无需修改。按用户指定路由，fix 后执行 MiMo / DS 双路 PR re-review。
