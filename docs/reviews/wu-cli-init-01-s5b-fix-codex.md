# WU-CLI-INIT-01 S5-B Oracle Correction Fix

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- slice：`S5-B live provider matrix`
- gate：code-review finding adjudication / fix / re-review
- 日期：2026-07-30
- 状态：**已修复；PASS**
- artifact path：`docs/reviews/wu-cli-init-01-s5b-fix-codex.md`

## Finding adjudication

| Finding | 裁决 | 最终状态 |
| --- | --- | --- |
| terminal preview 含已知绝对 CI root | accepted | 已修复；精确 root 脱敏保留 |
| Host SQLite 持久化 resolved credential 属于 violation | rejected-with-reason | 证据失效；用户裁决该 durable fact 允许 |
| 非 Host SQLite durable artifact 出现 exact credential 应失败 | accepted | 已修复 |
| secret canary 在任何位置出现应失败 | accepted | 已修复 |
| DS F01 non-requestable reconciliation 未复用完整脱敏 owner | accepted | 已修复；credential/canary/request-id/Authorization/Bearer/roots 走同一 owner |
| DS F02 live expected/effective identity 同源自引用 | accepted | 已修复；expected 来自 choice + frozen package truth，effective 只来自 assembly |
| Controller F02 retained report 仍信任旧 no-fallback bool | accepted | 已修复；reconciliation 从 expected/effective/Host canonical evidence 重算并覆盖 |
| DS F03 legacy canary prefix 误报风险 | rejected-with-reason | intentional fail-closed；不知道旧 exact canary 时必须保留前缀探针 |
| DS F04 typed bool 冗余读回 | accepted（non-blocking） | 已用局部 typed bool 清理 |

错误 finding 的根因不是 Host 行为，而是 S5-B scanner 把“发生匹配”与“违反 policy”
混为一个 `findings` 集合，再让所有匹配统一污染 internal contract 与 overall verdict。
正确 owner boundary 是 scanner classification/report projection。

## Fix

- 以 typed `PersistedCredentialObservation` 和 `PersistedSecretViolation` 分离两种语义。
- Host SQLite/WAL exact credential 只进入 `accepted_observations`。
- config/report/log/trace/其它 durable artifact exact credential 进入 `violations`。
- canary 不享受 Host 例外，在任何 artifact class 中都进入 `violations`。
- fail-closed traversal errors 继续作为 violation。
- matrix exit 只消费 persistence `passed/violations`，不消费 accepted observation。
- reconciliation 从非 persistence owner evidence 重算 internal/availability，清除旧
  oracle 的派生误判。
- 保留绝对路径与 request-id value 脱敏；报告只含稳定 code/class/count。
- non-requestable reconciliation preview 复用 `_redact_sensitive_text`；完整脱敏
  owner 同时移除 credential、known legacy canary placeholder、Authorization/Bearer、
  request-id value 与显式 roots。未知旧 canary 继续由 prefix scan 阻止写入。
- live no-fallback expected identity 的 provider family 来自 `InitModelChoice`，
  静态 provider model 来自冻结 package `models.json`，动态 provider model 来自
  init-owned workspace publication，均经 `ConfigLoader` 解析；effective identity
  只从 production assembly 产生。无 assembly 时不构造 effective，已请求却缺
  identity 时 fail closed。
- reconciliation 不再读取旧 `row.no_fallback` verdict。requestable 从 package/
  init-owned expected、row assembly effective、只读 Host runner calls/run binding
  与 request/response facts 重新 `evaluate_no_fallback`；non-requestable 必须同时
  无 request、identity、trace/run binding 与 response。
- reconciliation 使用局部 typed internal-contract bool，不再写入 JSON 后立即读回。

没有修改 Host，没有删除 raw evidence，没有 provider 调用，没有 backup。

## Re-review evidence

指定 run 的正式 report 已原位重签：

`workspace/tmp/wu-cli-init-01/20260730T112936Z-a86f5ccdeab5/matrix-report.json`

re-review assertions：

- 15 rows；
- 10 个 Host SQLite 聚合 observation records，分布于 10 rows；
- observation `count` 汇总为 20 次 exact-byte matches；`count` 仅表示 bounded
  scanner 的 bytes 匹配次数，不推断 20 个业务事件；
- 0 persistence violation；
- 15 rows internal contract valid；
- 15 rows canonical no-fallback valid；
- overall exit 0；
- report 自身不含 credential value、canary、Authorization/Bearer value、
  request-id value或 project/run/workspace 已知绝对 root；
- run 根仅含 `rows/` 与正式 `matrix-report.json`。

验证：

- focused pytest + coverage：`71 passed`；
- source/test coverage：81% / 99%；
- full pyright：0 errors / 0 warnings；
- scoped ruff：pass；
- `git diff --check`：pass。

## Docs decision

`docs/cli_ci.md` 已同步最终 policy。`tests/README.md` 不承担具体 oracle policy，
测试层级与执行方式也未改变，因此不更新。

## Residual risks

- Host SQLite retained credential 是 accepted observation，不是 deferred finding。
- legacy canary 只可扫描稳定 marker；新 run 仍扫描完整 exact canary。
- provider 状态未重试，继续由 retained raw evidence 证明。

没有 blocking finding、未分类 residual risk 或 uncovered owner。按用户要求不 commit。
