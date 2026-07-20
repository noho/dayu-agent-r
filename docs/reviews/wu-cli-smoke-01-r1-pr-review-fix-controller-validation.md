# WU-CLI-SMOKE-01-R1 Draft PR #180 Fix Controller Validation

## Scope

- Accepted finding: PR180-F01。
- Fix artifact: `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-codex.md`。
- External owner: Draft PR #180 body metadata。
- Repository implementation change: none。

## Direct Validation

- `gh pr view 180 --json body,isDraft,reviewRequests,baseRefName,headRefName,headRefOid,title`：
  - body 以真实 `## 摘要`、`## 验证`、`## 已接受边界` 多行标题与 Markdown 列表返回。
  - `isDraft=true`。
  - `reviewRequests=[]`。
  - base=`main`。
  - head=`phaseflow/wu-cli-smoke-01-r1`。
  - head OID=`ff5d515a50d538415c0906b80ebdef594601c5c8`，与 fix 前一致。
  - title 未变。
- `gh pr view 180 --json body --jq .body | sed -n '1,40l'`：每个标题、空行与列表项均以真实行终止符显示，不再由字面量反斜杠-n 连接。
- body 不含行首 closing directive；仅保留说明“没有独立 Issue owner，因此不添加 Closes footer”。
- `gh pr checks 180`：
  - `windows-init-transaction` pass。
  - `windows-upload-script` pass。
- `git diff --check`：pass。
- `git status --short`：仅有两份 controller-owned control doc、两份 PR review artifact、PR review controller adjudication、本 fix artifact 与本 validation artifact；无 production/test/design/README 修改。

## Decision

`ready-for-PR-rereview`。PR180-F01 已由直接 GitHub metadata 证据关闭；代码 head 未变，CI 两项均通过。按用户指定路由进入 AgentMiMo / AgentDS 双路 PR re-review。
