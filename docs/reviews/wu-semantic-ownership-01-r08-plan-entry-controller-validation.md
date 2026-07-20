# WU-SEMANTIC-OWNERSHIP-01 / R08 plan-entry Controller validation

## 1. Gate verdict

| 项 | 结论 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 overdesign remediation continuation |
| internal sub-WU | `R08` Financial/XBRL 最小 contract 与单一 projection；不是新 WU |
| input plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| transition HEAD | `8d9bf63b3ab56f9ba3d5355d75af4ee002548c9c` |
| R07 completion | `28b6fc1956bd3832489a471fa29bfe354b319860` |
| final plan SHA-256 | `9ddc11b6dbfc9559561ae619f47e2d237a7e999b88798eb861eae7483b0e2385` |
| verdict | **PASS / READY FOR DUAL COMPLETE PLAN REVIEW** |

本结论只授权 AgentMiMo 与 AgentDS 对同一份 R08 plan 做并发完整 plan review。它不接受计划、不授权 implementation、stage/commit、R09-R12、deferred Issues、统一 authorization、push 或 PR。

## 2. Controller independent checks

Controller 完整阅读了 698 行初稿和定点修正后的最终计划，并重新核对：

- `AGENTS.md` 的 semantic owner、LLM-facing、分层、类型、测试与 README 约束；
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.4 final user adjudication；
- `docs/fins/design.md` §5-§6；
- umbrella accepted remediation plan §15；
- R06 transaction/publication 与 R07 identity/revision/snapshot/citation 已接受边界；
- 当前 domain contracts、actual SEC/BS/6-K/HTML processor、read/tool projection、SEC fiscal consumer 与 Host truncation 实现；
- worktree、lineage、untracked artifact whitespace 与 final SHA-256。

当前 worktree 只有 R08 plan 为 untracked；`git diff --no-index --check /dev/null <plan>` 无 whitespace error。计划未改 product、test、README、design、control 或既有 review artifact。

## 3. Entry findings and closure

| ID | 直接证据 | Controller disposition | 最终状态 |
|---|---|---|---|
| `R08-PE-F01` | 当前 `FinancialScale` 唯一值是 `units|thousands|millions|billions`，初稿误写 `ones` | 改回既有真源值，禁止借 R08 引入新 enum | closed |
| `R08-PE-F02` | 仓库没有 `JsonNumber` 定义 | query 数值使用可实现的 `int | float`，validator 显式拒绝 `bool`；不无必要新增 alias | closed |
| `R08-PE-F03` | R07 当前 `Citation` 要求 `source_type/document_id/ticker` | 最小示例补齐同源 identity；不得建立第二个 citation owner | closed |
| `R08-PE-F04` | 初稿同时要求 S1 full pyright 零、又允许尚未迁移 S2 consumer error | S1 modified-owner scoped type gate 必须零；full pyright 必跑且只允许预声明 S2 direct-consumer 的精确破坏性传播证据；S2 后 full pyright 必须零 | closed |
| `R08-PE-F05` | 既有 public result 使用 `dict[str, Any]`，但本轮会重建 financial/XBRL public contract | 新 projection 不得复制 `Any` 签名；机械消费 R07 citation 的 strict JsonValue-compatible mapping，不改 R07 owner、不 cast/shim | closed |

无 finding 被推迟为“后续优化”，也没有重新打开已裁决产品问题。

## 4. Accepted owner and slice boundary for review

### 4.1 S1 owner boundary

- `dayu.fins.domain.financial_result_contract` 独占 financial producer result、reason 闭集与 terminal validation。
- actual SEC/BS/6-K/HTML/OCR producers 直接产生最小 contract；method absent、`None`、空表、空 rows 在 producer terminal 统一为 `statement_not_found`。
- `statement_locator`、`statement_method_missing`、`statement_empty` 与无 production caller 的 alternate financial reason owner 删除，不在 read/test/adapter 保留。
- `dayu.fins.domain.xbrl_result_contract` 独占 raw XBRL query contract；producer result 删除本地 `len(facts)` 派生的 `total`，query params 形成一个 flat typed shape。
- 若实施发现真实 provider raw total，只能进入明确 internal typed validation/diagnostic owner并提供 provider input、校验动作、owner test 与 no-public-propagation 五联证据；当前 inventory 预期为零。

### 4.2 S2 owner boundary

- `dayu.fins.tools.result_types` 邻接拥有严格 typed public result、small projection builders 与同源 description metadata/helper；不得再建 generic schema framework。
- read 只做 raw copy、normalize、stable dedupe 与 mechanical projection；不能写回 processor payload，也不能补 producer default/reason。
- public XBRL 只有一个 `fact_count`，唯一赋值为 builder 对最终独立 `returned_facts_copy` 的 `len(...)`。
- tool description、serializer/example 从同一 projection owner 派生并满足 `AGENTS.md` 的自足 LLM-facing contract。
- R07 snapshot/borrow/revision/citation/source-changed owner保持 no-touch，只机械提供当前 borrowed snapshot context。

S1 是未提交的严格 review checkpoint；S1 双路 review/fix/re-review 完成后才能进入 S2。S1/S2 均不做中间 accepted commit；R08 complete tree 通过 S2 review、aggregate validation 与 aggregate deepreview 后才允许一个 exact-scope implementation commit。

## 5. Host truncation composition adjudication

当前 `query_xbrl_facts` 的 `ToolTruncateSpec` 以 `facts` 为 target。Host 超限时把该字段替换为：

```text
{truncated: true, value: <visible facts>, fetch_more: {cursor, scope_token}}
```

并保留 sibling `fact_count`；`fetch_more` 返回 remainder value，不返回第二个 Fins result。Controller 对既有裁决作如下 owner-level解释：

1. `fact_count == len(facts)` 是 Fins public typed business result 在交给 Host governance 前必须成立的不变量；这里 `facts` 是完整、已去重、独立 public list。
2. Host 替换 target field 后，替换值是 Host-owned truncation envelope，不再是另一个 Fins typed `facts` list；`fetch_more` remainder 也不是 Fins serializer 的第二次业务投影。
3. R08 不得删除现有 ToolTruncateSpec、修改 Host、私造 cursor/fetch_more、把限制搬进 read、静默 drop，或让 Fins 根据 envelope 重写 sibling count。
4. S2 必须同时验证 under-limit 完整业务结果、forced-truncation envelope、fetch_more owner 与 Fins pre-Host invariant，并确保 LLM 不把 envelope/count解释为 raw provider total或 dedupe diagnostic。
5. 若实际实现证据表明 Fins serializer、tool description 或 Engine projection把 Host envelope重新承诺为普通 Fins `facts` list，必须 stop 回 Controller；不得用 union/fallback/shim遮蔽 owner 冲突。

这一解释保留 Topic 1 的 ToolTruncateSpec/fetch_more，也保留 Topic 6 的唯一 Fins count；不实施 Issue 177。

## 6. Mandatory dual-review challenges

两路 reviewer 必须至少独立检查：

- 七值 financial reason 闭集是否每个都有当前业务恢复动作，是否仍残留内部 diagnostic；
- actual producer inventory 是否覆盖 generic SEC、BS report forms、BS 6-K、HTML/OCR 与继承/registry传播；
- `_build_financials_payload` 删除是否确有无 production caller 证据，且没有误删 SEC fiscal 业务 consumer；
- flat XBRL query params 是否把“实际执行参数”作为 producer truth，并拒绝 read 重拼/default `None`；
- public citation typing是否能在不改 R07 owner、不用 `Any/cast/shim` 的前提下实现；
- S1 internal checkpoint 的 bounded propagation evidence 是否足够审查，是否会形成未登记红树或半成品 acceptance；
- Host truncation组合裁决与 forced-truncation/fetch_more tests 是否可执行且不越界；
- exact allowlists、逐文件 coverage、scoped Ruff、full pyright、真实 AAPL/HTML/no-statement smoke、双向 scans 是否完整；
- 是否偷带 R09-R12、Issues 142/151/175/177/178、unified authorization 或 R07 owner change。

## 7. Next gate

下一 gate 是同一 final-plan SHA 的 AgentMiMo / AgentDS 并发完整 plan review。任一路 accepted finding 都必须由 Controller 裁决后交 AgentCodex plan-only fix，再做双路完整 re-review。只有最终两路通过、全部 finding 有最终状态并完成 accepted-plan local commit，才可另行进入 R08-S1 implementation。
