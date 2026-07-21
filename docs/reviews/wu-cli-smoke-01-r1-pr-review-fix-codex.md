# WU-CLI-SMOKE-01-R1 Draft PR #180 Review Fix

## Scope / Owner

- Finding：唯一 accepted finding `PR180-F01`。
- Risk：Low Risk / PR-metadata-only。
- Semantic owner：GitHub PR #180 的 `body` metadata。
- Repository scope：仅新增本 artifact；未修改 production、test、design、README、control 或既有 review artifact。

## Root Cause

修复前直接读取 `gh pr view 180 --json body,...`，body 的实际值由字面量反斜杠加 `n` 连接，例如“## 摘要”后连续出现两个字面量换行转义序列。创建 PR 时传入的 shell 参数没有把 JSON escape 转换为实际换行，导致 GitHub 将反斜杠与 `n` 两个普通字符持久化为 body 正文，Markdown 因而无法形成标题、空行和列表。该问题不属于仓库代码、Host / Service / CLI contract 或测试 owner。

## External Modification

1. 使用 `apply_patch` 创建静态真实多行文件 `workspace/tmp/wu-cli-smoke-01-r1-pr-180-body.md`，正文逐行照录修复前内容，仅把分隔用的字面量反斜杠加 `n` 改为真实换行；未使用动态替换。
2. 执行 `gh pr edit 180 --repo noho/dayu-agent-r --body-file workspace/tmp/wu-cli-smoke-01-r1-pr-180-body.md`。
3. 使用 `apply_patch` 删除该临时文件。

唯一外部修改是 PR #180 body 的换行格式。未修改 title、Draft 状态、base/head、review requests、PR state 或 code head；未新增 closing footer，未 comment，未操作 issue。

## Validation

- 修复前 code head：`ff5d515a50d538415c0906b80ebdef594601c5c8`。
- `gh pr view 180 --repo noho/dayu-agent-r --json body,isDraft,reviewRequests,baseRefName,headRefName,headRefOid,title`：
  - `body` 以真实多行 `## 摘要`、`## 验证`、`## 已接受边界` 标题及 `- ` 列表返回；正文文字保持不变。
  - `isDraft=true`。
  - `reviewRequests=[]`。
  - `baseRefName=main`。
  - `headRefName=phaseflow/wu-cli-smoke-01-r1`。
  - `headRefOid=ff5d515a50d538415c0906b80ebdef594601c5c8`，与修复前一致，证明 PR code head 未变。
  - `title=WU-CLI-SMOKE-01-R1: move engine deltas to Host transient live stream`，与修复前一致。
- `gh pr view 180 --repo noho/dayu-agent-r --json body --jq <结构断言>`：`lineCount=26`、`hasSummaryHeadingAndList=true`、`hasValidationHeadingAndList=true`、`hasBoundaryHeadingAndList=true`、`hasLiteralBackslashN=false`、`hasClosesDirective=false`。
- closing footer 检查：body 不含 `Closes #...` 指令；正文原有“不添加 Closes footer”说明句保持不变。
- 临时 body 文件已删除。
- 最终 `git status --short` 仅包含 controller 预先存在的两份 control 修改、两份 PR review artifact、controller adjudication，以及本 fix artifact。
- 未运行 pytest / pyright：本次没有代码、测试、schema、契约或运行时文件改动，且 handoff 明确限定为外部 PR metadata 与本 review artifact；已执行本 gate 指定的 metadata、head 与工作树验证。
- README decision：无触发项，且本 handoff 明确禁止修改 README。

## Residual Risk / Stop Status

- Residual risk：本修复未改变 aggregate 阶段已接受的 live-only、容量 256、cross-domain ordering 与可控 worker 边界。
- Stop status：`completed-and-stopped`。`PR180-F01` 已修复并完成直接验证；按 handoff 在此停止，等待 AgentMiMo / AgentDS 双路 PR re-review。
