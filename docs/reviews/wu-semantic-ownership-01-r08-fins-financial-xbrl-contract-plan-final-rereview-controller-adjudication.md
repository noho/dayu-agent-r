# WU-SEMANTIC-OWNERSHIP-01 / R08 final plan re-review Controller adjudication

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella 的 overdesign remediation continuation |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | second dual complete plan re-review adjudication |
| timestamp | `2026-07-17 04:38:51 +0800` |
| accepted plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| accepted plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| AgentMiMo final review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-final-rereview-mimo.md` / `1c1e8898cd3e905c7206077714d1327cce0dd953a8aa21370eb53ac5e5230d1a` |
| AgentDS final review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-final-rereview-ds.md` / `5c4a99d92bc253ec60cee46ebd1821e3186a3064f8d67464d198486d1e702647` |
| result | **PASS / PLAN ACCEPTED / READY FOR EXACT-SCOPE LOCAL COMMIT** |

## 2. Review evidence integrity

两路均审查同一 final plan SHA，并完整复核整份计划，而非只看最后两处 diff。Controller 在接收前退回并纠正三类 artifact evidence 问题：

1. AgentCodex 初次 probe 用 `.get("fact_count")` 得到 `None`，无法区分字段缺失与 Host 删除；同一任务重跑完整 public shapes，证明当前 pre/post 旧 contract 都尚无 `fact_count`，Host 只替换 `facts` 并保留全部 siblings。Final plan 已改为 membership、direct index、key-set 与 non-facts sibling equality。
2. AgentMiMo 初稿把原 `R08-PF-01..07` ID 与裁决内容错配；同一 artifact 已按 Controller 真源纠正并重算 hash。
3. AgentDS 初稿同样错配原七项，并有 `SEC_EDAR` 拼写及五项矩阵计数错误；同一 artifact 已全部纠正并重算 hash。

最终两份 artifact 均与 Controller accepted ID ledger、plan 内容和当前代码证据一致；`git diff --check` 通过。

## 3. Final closure ledger

| ID | 最终状态 | 两路结论 |
|---|---|---|
| `R08-PF-01` S1 immutable hash/full-pyright ledger + shared fiscal boundary | closed | PASS / PASS |
| `R08-PF-02` 七值 financial reason 的业务含义与 LLM-safe next action | closed | PASS / PASS |
| `R08-PF-03` citation `Mapping[str, JsonValue]` → independent dict，R07 no-touch | closed | PASS / PASS |
| `R08-PF-04` `SEC_EDGAR` example | closed | PASS / PASS |
| `R08-PF-05` `fiscal_period.enum` 消费 `FISCAL_PERIODS` | closed | PASS / PASS |
| `R08-PF-06` min/max bool reject + True/False/int/float/missing matrix | closed | PASS / PASS |
| `R08-PF-07` explicit `Public*` names，old tools names no compat | closed | PASS / PASS |
| `R08-RR-PF-01` S1 formal/coverage exact-node selection | closed | PASS / PASS |
| `R08-RR-PF-02` real ToolRuntime forced-truncation public-seam test | closed | PASS / PASS |

汇总：`9/9 closed`，`0 deferred accepted finding`，`0 new material finding`，`0 open question`，`0 product blocker`。

## 4. Rejected opinions and residual routing

- Optional-reason 私有 helper 指令：保持 rejected；状态机、terminal validator owner 与 owner tests 已足够，implementation 自行选择 owner 内私有 helper 形态。
- Reason frozenset 额外 checklist：no-fix；七值闭集与测试已多处精确指定。
- R09 truncation routing：rejected；R09 是 wait poller。Generic Doc/TruncationManager 完整接通继续由 Issue 177 跟踪，本 R08 不实施。
- Host truncation envelope 是独立治理层；R08 不改 Host、不私造 cursor/fetch_more、不把 envelope 解释为第二个 Fins business result。

## 5. Scope and authorization

R08 plan 现在 code-generation-ready，切分保持：

1. R08-S1：producer contracts + actual processors；无中间 commit，使用 immutable tree/hash + exact full-pyright propagation ledger 完成双路 review。
2. R08-S2：read/tool/LLM single projection + README + real composition validation；full pyright 必须归零，完成双路 code review/fix/re-review 与 aggregate deepreview 后才接受实现。

本 adjudication 只授权 exact-scope local accepted-plan commit。该 commit 之后必须用单独的 control transition commit 进入 R08-S1 implementation；不得把 transition、implementation、R09-R12、Issue 177、统一 authorization、push 或 PR 混入 accepted-plan commit。
