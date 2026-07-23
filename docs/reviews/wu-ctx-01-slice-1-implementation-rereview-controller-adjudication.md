# WU-CTX-01 Slice 1 implementation re-review Controller adjudication

## 1. Scope

- Work Unit：`WU-CTX-01`
- Gate：Slice 1 implementation re-review
- Accepted plan base：`ed43bcf2`
- Fix artifact：
  `docs/reviews/wu-ctx-01-slice-1-implementation-review-fix-codex.md`
- AgentMiMo re-review：
  `docs/reviews/code-review-20260724-045325.md`
- AgentDS re-review：
  `docs/reviews/code-review-20260724-044856.md`
- Controller 另行复核了 fix artifact、两路 review artifact、关键 owner 实现、
  测试矩阵、工作区状态与静态边界。

`docs/host/issues-implementation-control.md` 与本 artifact 为 Controller-owned
bookkeeping，不属于 implementation finding scope。

## 2. Decision

**pass**

两路独立 implementation re-review 均判定 `pass`，没有新增 actionable finding。
Controller 接受该共同结论：`CTRL/REVIEW-IMPL-01..09` 已全部关闭，四项途中复核
也已形成 owner-level 代码与反例证据。Slice 1 production/tests 可以进入
accepted slice commit。

## 3. Accepted finding 关闭裁决

| Finding | Controller 裁决 | 关闭证据 |
| --- | --- | --- |
| `CTRL-IMPL-01` | fixed / closed | admission producer、strict parser 与 runtime validator 共用 `EffectiveToolFacts`；dispatch 消费冻结 exact names，`all` 不重选当前全部工具；bundle/schema/source/display drift 在 start 前 fail closed。 |
| `CTRL-IMPL-02` | fixed / closed | `NoBudgetDispatchStart` 显式持有真实 stage；ordinary、post-compact、dispatch-fallback caller 分别传值，commit owner 只消费 `plan.stage`。 |
| `CTRL-IMPL-03` | fixed / closed | strict source owner 产生 typed `TOOL_SCHEMA / POLICY / REQUEST_SEMANTICS`；Engine 只做 closed mapping，顺序固定为 projection → tool → policy → request，不解析异常文本。 |
| `CTRL-IMPL-04` | fixed / closed | source finder 交叉校验 EventLog row、hot payload、source Run 与 caller identity；continuation limited manifest 先校验 identity，再退出 pre-start duplicate 集合。 |
| `REVIEW-IMPL-05` | fixed / closed | 5 stage × 3 pressure 的 15 cells 全部冻结，unknown stage/pressure fail closed。 |
| `REVIEW-IMPL-06` | fixed / closed | manifest parser 拒绝 compactor proposal 的 COMPLETE / UNAVAILABLE sizing，dispatch-relevant kind 拒绝 NOT_APPLICABLE。 |
| `REVIEW-IMPL-07` | fixed / closed | 新增但无 caller 的 source policy loader 及专用 imports/constants 已删除。 |
| `REVIEW-IMPL-08` | fixed / closed | admission direct-running wrapper 及专用 imports 已删除。 |
| `REVIEW-IMPL-09` | fixed / closed | estimator digest docstring 已与真实 contract/input/constants 语义一致。 |

途中四项复核同样关闭：

1. repair replay 使用永久 empty no-tool truth，不读取当前 tooling；
2. continuation limited manifest 不误判为第二个 pre-start，但 row/hot corruption 仍
   fail closed；
3. steer 保留 `SUBSET / ALL / NONE` caller intent，显式 non-empty subset 在 frozen
   policy 禁用工具时继续 fail closed；
4. 同一 source 同时损坏 tool 与 policy 时稳定归为 tool，tool valid 而 policy
   损坏时归为 policy。

## 4. Independent validation

- Focused：`397 passed`。
- Full Host：`2202 passed, 2 skipped, 6 deselected`。
- Full pyright：`0 errors, 0 warnings`。
- 18 个 changed production files 的 branch coverage 均 `>=80%`，合计 `85%`。
- `git diff --check`：通过。
- direct-promotion、dead wrapper/loader stale symbol：零命中。
- Slice 2 `CONTEXT_BUDGET_EVALUATED` / public projection：零新增执行路径。
- Slice 3 usage-anchor producer/consumer：零新增执行路径；已有
  `ContextEstimateMethod.USAGE_ANCHORED` 仅是 accepted closed vocabulary。
- Host/tests README trigger：已按职责同步。

## 5. Re-review observations

AgentDS 在 AgentMiMo 同时运行另一套全量覆盖率测试的并发负载下，首次 full Host
运行出现一次
`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 时序失败；
该用例立即单独重跑通过，随后 full Host 再跑也以 `2202 passed` 通过。目标测试本身
未被本 Slice 修改。Controller 将其记录为非阻断测试时序 residual risk，不把单次
抖动伪装成稳定失败，也没有证据将其归因于本 Slice correctness。

## 6. Residual risk

- optional real compactor smoke 未启用；
- Gemini 等真实 provider quota / endpoint smoke 未执行；
- 默认 pytest 配置排除 6 个 stress tests；
- 并发高负载下 active-cancel watchdog public-watch 用例存在一次未复现的时序抖动。

这些 residual risk 不阻断 Slice 1 accepted commit；不得以 mock 或本地 deterministic
测试冒充外部 provider 验证。

