# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview Controller Authorization

## Authorization

`AUTHORIZED / AGENTMIMO_AND_AGENTDS_CONCURRENT_COMPLETE_AGGREGATE_DEEPREVIEW_ONLY`

这是既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation的 aggregate deepreview gate，不是新 WU。两路必须使用 `/deepreview`，独立审查完整组合树；不得互读或复用另一路review结论，不得spawn subagents。

## Immutable review target

- branch：`phaseflow/host-issues-control`
- accepted HEAD：`85aa7184a694448a5b27da7cca52f753f84d6e20`
- accepted tree：`0db1c91f92dca594cf77c74bbde8f5b4fc42710d`
- aggregate parent：`3410d7422655c56bdf13c643f77c27f40b9d4550`
- required review range：`b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- changed production Python：exact 219；fresh aggregate validation已达219/219 line coverage >=80%。

AgentMiMo唯一可写：

`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md`

AgentDS唯一可写：

`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md`

除各自artifact外，当前全部tracked/untracked paths immutable；staged必须保持为空。不得修改产品、测试、README、design、control、workflow或其它review artifact。

## Required truth sources

完整读取并按优先级使用：

1. `AGENTS.md`
2. `docs/host/issues-implementation-control.md`
3. `docs/phaseflow-umbrella-optimization-control.md`
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
5. `docs/host/design.md`
6. `docs/engine/design.md`
7. `docs/tool/design.md`
8. `docs/fins/design.md`
9. `docs/ui/design.md`
10. accepted umbrella/sub-WU/aggregate fix plans与Controller adjudications。

三路原始 overdesign review只作代码证据；冲突时Controller discussion优先。最终aggregate validation及Controller validation是测试证据，不替代code/design review。

## Required review coverage

必须覆盖全部 Topic 1—7 的组合行为、LLM-facing传播、owner边界、跨slice交互、correctness/stability/maintainability/security/over-coupling、测试真实性、README一致性与residual ownership，特别挑战：

- Doc完整输入与ToolTruncateSpec/fetch_more边界，不能偷带Issue 177；
- Web private/custom-port/proxy/DNS-peer/browser/budget/diagnostics/storage-state删除组合，不能偷带Issue 178或删防御安全；
- Host LLM-safe源头投影与内部canonicalization分离；
- opaque evidence refs不能进入RunInput/Memory/Compact/LLM trace冒充业务来源；
- wait provider/runtime config ownership、observation timeout late-publication撤销、claim/backoff和LOST authoritative rule；
- Fins transaction/provenance/staging/XBRL/terminal validator/HKEX/filesystem/storage key owner组合；
- CLI upload script/init/reset与placeholder package删除组合，不能偷带Issues 142/151/175或tracker能力；
- S3 Docling caption与Fins atomic virtual/base publication组合；
- Config/Host internal SQLite/EventLog trusted-local与Tool Trace/audit/public/LLM/log zero-required边界；
- Topic 8 240字符Engine语义保持、Topic 9不实现统一authorization framework；
- AR-F06/AR-F07、Gemini quota/provider adherence与其它residual必须有明确owner/status，不得误报为已修复或当前代码finding。

## Finding rules

- finding必须有当前代码/测试/设计真源的直接证据、可复现影响、唯一semantic owner、精确路径与最小修复边界。
- 不把风格偏好、未来优化、已裁决no-code/deferred项、测试账号quota、trusted-internal SQLite/EventLog命中、Darwin Windows skip本身包装成current code finding。
- 发现material finding时只写artifact并交Controller；不得修改代码。
- 必须列出material/needs-evidence/rejected-observation候选、residual risks与最终verdict，并报告artifact SHA、HEAD/tree/staged/worktree锁。

本 gate 不授权fix、stage、commit、push、PR、workflow trigger或final closeout。
