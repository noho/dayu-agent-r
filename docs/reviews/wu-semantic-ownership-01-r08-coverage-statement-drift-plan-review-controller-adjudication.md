# WU-SEMANTIC-OWNERSHIP-01 / R08 coverage-statement drift plan review Controller adjudication

## 1. 结论

`PASS / NO_ACCEPTED_PLAN_FINDING / READY_FOR_ACCEPTED_PLAN_COMMIT`。

审查目标是完整最终计划：

- path：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- SHA-256：`115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401`

两路 reviewer 均独立匹配最终 plan 与 stopped tree locks：

- AgentMiMo：`PASS`，artifact `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-review-mimo.md`，SHA-256 `4db054fabf721ee05508dff4ad25b49d6c1c224f0276244bf8d81f93685d2e00`；
- AgentDS：`PASS-WITH-RISKS`，artifact `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-review-ds.md`，SHA-256 `55f79640da5541e73ec25bca23d7c610b90bbf1231c970c659cb048c0fa4dbcd`。

Reviewer verdict 不独立授权实现。Controller 对全部 candidate findings 作如下最终裁决。

## 2. Findings adjudication

### DS-R08-PR-01：拒绝作为 finding

提议：在 text negative scan 中重复加入 private `_resolve_document_type`，否则实现可能直接 import/private-test。

裁决：`REJECTED_AS_FINDING / ALREADY_COVERED_BY_STRONGER_EXACT_ALLOWLIST`。

直接证据：完整计划 §6.7.F 已要求 AST import assertion 证明，相对 guards entry hash 唯一新增 production symbol import 精确等于 `{resolve_document_type_for_source}`，并明确不得加入 `_resolve_document_type`、mapping constant 或其它 helper；AST node assertion还要求 candidate 6 直接调用无下划线 production owner。任何额外 private import 都会使 exact allowlist 失败。再在 regex negative scan 中复制同一规则不会增加可检测状态，只会形成重复 governance owner。

因此不存在未覆盖的 owner-boundary 缺口，不修改计划。实现与 Controller validation 仍必须执行该 AST exact allowlist，并人工核对三条 direct public-owner assertions。

### DS-R08-PR-02：拒绝作为 finding

提议：coverage.py 版本可能影响 `387/485`、`390/485`，建议增加版本声明或 data-file hash。

裁决：`REJECTED_AS_FINDING / INTENTIONAL_FAIL_CLOSED_PROOF`。

直接证据：

- 当前 repository、Python 3.11 virtual environment、dependency environment、source/test tree 与命令集合全部受锁；
- Controller 已在同一环境独立测得 all-five `387/485=79.79381443%`；
- 计划要求 implementation gate 自己 fresh erase 后复现，而不是复用 Controller JSON；
- numerator、denominator 或 threshold 任何 drift 都必须停止回 Controller，正是用来发现环境/source/test/coverage drift 的设计，不是 portability defect；
- 将 checker 弱化为 inequality、绑定旧 data-file，或把环境差异隐藏为 permissive acceptance，都会破坏 first/shortest threshold-crossing proof。

该提议与此前 candidate-exhaustion plan review 中已拒绝的 exact-coverage portability 提议同类；没有新代码证据推翻既有裁决。不修改计划。若未来 fresh proof 真实 drift，保留现场并回 Controller 重新诊断，不能预先兼容。

### DS residual RR-3 / RR-4：记录但不接受为当前 finding

- Forced-truncation 路径是已有累计 R08 mandatory smoke，非本 correction 新增；计划已有真实 fixture、exact node、stop condition 和从零全量验证，不得用 skip 降级。
- 测试非确定性是假设性风险；当前同一锁定测试集合已有可重复 Controller/Agent 证据。若 fresh run 出现不一致，fail-closed 并按真实证据诊断，不预先设计 fallback。

## 3. Final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current plan findings | 0 | 无 |
| rejected reviewer candidates | 2 | `DS-R08-PR-01..02` |
| retained non-blocking residual groups | 2 | exact-proof drift 与 mandatory smoke/non-determinism，仅在真实触发时由 Controller 诊断 |
| blockers / open questions | 0 | 无 |

无需 AgentCodex plan fix，也无需 dual re-review。

## 4. Accepted plan boundary

最终计划保持：

- dead-helper deletion 与 actual typed/sorted owner；
- candidate 6 唯一 exact node/import及三条 public owner assertions；
- prefix-five `387/485<80`、prefix-six `390/485>=80` exact fail-closed proofs；
- 达标后从零完整 §6.6/§6.7 validation；
- production、shared/其它 tests、README、S1/S2 artifacts no-touch；
- R09-R12、Issues 142/151/175/177/178、统一 authorization、Topic 8-9 code out-of-scope。

Stopped `dayu/fins + tests` diff 仍为 `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0`，staged tree 在 adjudication 前为空，`git diff --check` 通过。

## 5. Next gate

只允许 exact-scope accepted local plan commit。该 commit 不得包含 product code、tests、README、S1/S2 implementation artifacts 或 deferred scope。Commit 后必须由 Controller 单独生成 implementation authorization，再派发 AgentCodex；未完成 authorization 前不得修改 guards 或运行 implementation gate。
