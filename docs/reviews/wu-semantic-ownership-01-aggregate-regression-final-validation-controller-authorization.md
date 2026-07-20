# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Final Validation Controller Authorization

## Authorization

`AUTHORIZED / AGENTCODEX_FRESH_AGGREGATE_REGRESSION_ONLY`

Slice 1 accepted commit `ba44bf877138235d53606d082341a7f7280af488`、Slice 2 accepted commit `9e7a4e9d4796b9c382d44494bb10efa64787b199` 和 Slice 3 accepted commit `85aa7184a694448a5b27da7cca52f753f84d6e20` 均已完成其 plan/review/fix/re-review/local-commit gate。现在授权 AgentCodex 按 accepted plan `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` §7，从最终整合树 fresh 执行 aggregate regression，并写唯一 artifact：

`docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md`

## Immutable baseline

- branch：`phaseflow/host-issues-control`
- HEAD：`85aa7184a694448a5b27da7cca52f753f84d6e20`
- tree：`0db1c91f92dca594cf77c74bbde8f5b4fc42710d`
- aggregate parent：`3410d7422655c56bdf13c643f77c27f40b9d4550`
- review range：`b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- expected changed production Python set：exact `219`
- coverage exclusion：只允许 AR-F06 exact scheduler node；该 node 必须另行 collect 为唯一 node 并真实运行通过。

除上述新 artifact 外，当前 tracked/untracked tree 全部 immutable。若验证揭示真实 product/test/README defect，不得自行修改；保存最小直接证据并停止交 Controller 裁决。

## Required fresh validation

完整执行 plan §7，至少覆盖：

1. canonical non-coverage full suite 0 failed，AR-F06 node真实执行；
2. exact single-node exclusion coverage 0 failed，`219/219 >=80.00%`逐文件 ledger；
3. full pyright、full Ruff exact baseline delta、diff-check、immutable HEAD/tree/staged/worktree；
4. wheel/sdist build与artifact hashes；
5. 六组 source/propagation scans、direct-stream/awaiting owner/stale scans、README、安全、configured-secret semantic classification、deferred/no-code ledger；
6. accepted real Web/public awaiting/R03/compactor/Fins/live-browser/POSIX generated script/CLI/init smokes，以及 immutable HKEX evidence复核；
7. AR-F01—AR-F05逐项 `CLOSED`，AR-F06与AR-F07保留其既有 owner/status。

## Fixed decisions

- Config 与 Host internal SQLite/EventLog 属于 trusted local domain；API key/header 可在该内部真源出现。Tool Trace、audit、public、LLM-facing、logs/outputs/diff/reviews必须明文为零。不得据此设计 secret infrastructure或统一authorization framework。
- Gemini 是低预算测试账号；quota/provider adherence 证据是 non-blocking/no-code。不得新增真实 provider 请求或修改 config/model/key/retry/quota/budget。
- 不实施 Issues 142、151、175、177、178 或 Web/WeChat/render tracker能力；Topic 8/9维持 no-code decisions。
- 本 gate 不授权任何代码修改、stage、commit、push、PR、workflow trigger 或 deepreview。
