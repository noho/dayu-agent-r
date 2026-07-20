# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview Re-review Controller Authorization

## Authorization

`AUTHORIZED / AGENTMIMO_AND_AGENTDS_CONCURRENT_COMPLETE_AGGREGATE_REREVIEW_ONLY`

两路使用`/deepreview`，独立对完整不变range和全部initial review/Controller adjudication/zero-change disposition evidence执行re-review；不得只审zero-change artifact，不得互读另一路final re-review，不得spawn subagents。

Immutable target：

- HEAD：`85aa7184a694448a5b27da7cca52f753f84d6e20`
- tree：`0db1c91f92dca594cf77c74bbde8f5b4fc42710d`
- range：`b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- initial MiMo SHA：`9bb5168bfd4eb9bbb8ae5a74ded5d8c6eba0ceb77c948ce45164af0308e66107`
- initial DS SHA：`3afb417dcc8dee839a98d69099615b4fd5091fde6e8b97a1b639244cdbb74ffc`
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md`
- zero-change disposition SHA：`ac8193fbdb103f9fb9400f530abca81cbe796e4780982ad60612ffffbbef3a31`
- Controller fix validation：`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-validation.md`

MiMo唯一可写：

`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-mimo.md`

DS唯一可写：

`docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-ds.md`

必须确认：

1. initial review完整范围仍成立，Topic 1—7组合与安全/deferred/no-code/residual ledger无漂移；
2. DS-01/02/03 Controller裁决有直接代码证据且zero-change未错误实施；
3. 没有新material finding/needs-evidence；若有，只写artifact交Controller，不修改代码；
4. Config/Host internal trusted-local、projection plaintext-zero、Gemini no-code、AR-F06/AR-F07、Issues 142/151/175/177/178与Topic8/9状态准确；
5. HEAD/tree/staged和全部protected dirty hashes不变。

本gate不授权产品/测试/README/design/control/workflow修改、stage/commit/push/PR/Windows/final closeout。artifact不自嵌自身SHA；final SHA由Controller外部计算。
