# WU-CTX-01 Ready-to-open-draft-PR Preflight

## 1. Scope

- Work Unit：`WU-CTX-01`
- branch：`feat/wu-ctx-01`
- base：`main`
- remote：`github`
- base commit：`5afe71fefa2486ff0e0d9b2026fee23685d48c2e`
- accepted aggregate deepreview commit：
  `798ba977cce9426e003b9ba18726e7cca336375c`
- linked Issue：
  [#20 Host Context Governance：Usage-Anchored Adaptive Context Sizing](https://github.com/noho/dayu-agent-r/issues/20)
- decision：`pass`
- blocking questions：None

## 2. Branch / remote preflight

- `git branch --show-current`：`feat/wu-ctx-01`
- local `main`、`github/main` 与 fresh `FETCH_HEAD`：
  `5afe71fefa2486ff0e0d9b2026fee23685d48c2e`
- `git merge-base HEAD github/main`：
  `5afe71fefa2486ff0e0d9b2026fee23685d48c2e`
- `git rev-list --left-right --count github/main...HEAD`：
  `0 8`
- branch 未落后 remote base；8 个受保护 WU commits 全部位于 base 之后。
- `gh pr list --state all --head feat/wu-ctx-01`：空；不存在同 head 重复 PR。
- Issue #20：`OPEN`，title/body 与 design §25 和 goal confirmation 一致。

## 3. Commit range

```text
06c143f2 gateflow: accept plan for WU-CTX-01
ff28cbc4 gateflow: accept plan amendment for WU-CTX-01
3f4190ed gateflow: accept reactive plan amendment for WU-CTX-01
ed43bcf2 gateflow: accept first-call producer plan for WU-CTX-01
b6f297b4 gateflow: accept WU-CTX-01 slice 1
126e67ca gateflow: accept WU-CTX-01 slice 2
fad15d39 gateflow: accept WU-CTX-01 slice 3
798ba977 gateflow: pass WU-CTX-01 aggregate deepreview
```

没有 merge commit、临时 implementation commit 或未裁决 code checkpoint。

## 4. Publish diff preflight

首次对 committed range 执行 `git diff --check github/main...HEAD` 时，发现两份早期
Controller adjudication artifact 的 EOF 各有一个多余空行：

- `docs/reviews/wu-ctx-01-plan-amendment-rereview-controller-adjudication.md`
- `docs/reviews/wu-ctx-01-slice-1-implementation-rereview-controller-adjudication.md`

这是发布格式阻断，不影响 production semantics。Controller 在当前 readiness gate 删除了
两个多余 EOF 空行；没有改动正文、裁决、production 或 tests。包含该最小修复的最终
working range 执行：

```bash
git diff --check github/main
git diff --check
```

均通过，无输出。该修复随 readiness/control artifact 创建独立 protected commit，不改写
已保护的 aggregate commit。

## 5. Validation evidence

accepted aggregate gate 的最终证据：

- focused owner/integration：`209 passed`
- clean full Host：`2259 passed, 2 skipped, 6 deselected`
- project standard suite：
  `5704 passed, 11 skipped, 6 deselected, 3 third-party deprecation warnings`
- full pyright：`0 errors, 0 warnings, 0 informations`
- WU base 到最终 aggregate working tree 的 25 个 production Python 文件 branch
  coverage：全部 `>=80%`，最低 `82%`，union `86%`
- AgentMiMo/AgentDS aggregate re-review：均 `pass`，0 新 actionable findings

readiness gate 只修改 Markdown EOF/control/artifact，不要求重跑 production tests；
最终 range whitespace、base sync、duplicate PR、Issue scope 与 commit allowlist 已重新核对。

## 6. Intended draft PR

- title：`feat(host): add usage-anchored adaptive context sizing`
- base：`main`
- head：`feat/wu-ctx-01`
- mode：draft
- body 必须包含：
  - canonical `CONTEXT_BUDGET_EVALUATED` 与 adaptive estimator 是独立 contract；
  - compatible usage anchor 使用 signed delta；
  - provider 不返回 usage 时回退现有 complete-input conservative estimator，Run 不失败；
  - five-stage producer / recovery / continuation 与 public context-usage projection；
  - full Host、standard suite、pyright、25-file coverage 与双路 deepreview evidence；
  - `Closes #20`。

不得把 PR 标记 ready、请求外部 reviewer、merge、评论或关闭 Issue。

## 7. Decision

**`pass`**

允许创建 readiness protected commit、push `feat/wu-ctx-01` 到 `github`，并创建 draft
PR。PR 创建成功后进入双路 PR deepreview；在 PR review gate 完成前保持 draft。
