# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Plan Review Controller Adjudication

## 1. Gate 与结论

**ACCEPTED / NO PLAN FIX OR RE-REVIEW REQUIRED。**

本轮审查对象是最终计划
`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`，SHA-256 为
`0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9`。AgentMiMo 与
AgentDS 均独立匹配 stopped product/test locks 并审查完整累计计划。两路没有产生 Controller
accepted finding；因此不进入无实质内容的 plan-fix/re-review gate，下一步是 exact-scope accepted
local plan commit。

| Reviewer | Artifact | Verdict |
|---|---|---|
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-mimo.md` | PASS；0 accepted finding |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-ds.md` | Reviewer 标为 NEEDS FIX；两项 LOW 经 Controller 逐项拒绝 |

## 2. Review locks

| 项目 | 最终值 |
|---|---|
| plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| stopped cumulative diff SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| staged tree during review | empty |
| `git diff --check` | PASS |

## 3. AgentMiMo observations

AgentMiMo 的 `F01..F16` 全部由其本人判定 PASS/PASS-with-note，没有 required current plan fix。
其中 coverage 精确值、actual-owner SHA/AST 双锁、candidate-5 下界、changed-manifest、S1/S2
boundary、LLM-facing reason、Host truncation、完整 validation、旧证据失效、stop conditions、
statement count、owner 声明、禁止 compatibility/deferred scope、依赖顺序和 failure recovery 均已
由当前计划覆盖。

MiMo 将 Host truncation 组合验证复杂度标记为 implementation flag，但该三段公开链路 test 已存在，
历史累计 validation 与 Controller 本轮复跑均通过；复杂度不是遗漏的步骤、owner 或 failure signal，
不构成 plan fix。

## 4. AgentDS findings 裁决

### R08-CE-PR-DS-F01 — REJECTED

**Reviewer claim：** candidate-4/candidate-5 proof 不应精确断言 `382/482` 与 denominator `482`，
应只比较阈值，以免 coverage.py/Python 版本变化造成 false failure。

**Controller evidence / decision：**

1. 本 continuation 的 baseline、五步 incremental ledger 与后续 deletion proof 在同一 repo、Python
   3.11 `.venv` 和当前 coverage toolchain 下执行；没有计划内 dependency/toolchain upgrade。
2. `382/494` 与 `388/494` 是当前 stopped tree 的真实测量；被删 definition 对应 12 个全未覆盖
   statements。`382/482` 与至少 `388/482` 因而既验证阈值，也验证本 gate 确实只删除了预期分母。
3. Controller 对 `R08-CR-PCF02` 的明确 acceptance requirement 就是 fresh
   `382/482 < 80` 与 all-five `>=388/482 >=80`。若 denominator 或 numerator 漂移，正确行为是
   fail closed 并回 Controller 查明 source/test/tool drift，而不是用 `480..490` 范围或 inequality
   吞掉未审查变化。
4. Reviewer 自己也确认当前确定性 tree 可精确复现，并允许降级为 INFO/PASS。

因此精确断言是 review lock，不是脆弱业务语义。修改为 inequality-only 会削弱唯一 deletion 与
first/shortest prefix 的机械证据，finding 不接受、不实施。

### R08-CE-PR-DS-F02 — REJECTED

**Reviewer claim：** forced-truncation real-fixture test 应在 AAPL facts 不足时 skip，或把不足记录为
blocked-by-fixture residual risk。

**Controller evidence / decision：**

1. AAPL fixture 位于 repo 内，是版本控制的确定性测试资产，不是会在运行中漂移的远端输入。
2. Exact node
   `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` 已存在；R08 历史完整
   Fins validation 为 `857 passed, 1 existing skip`，Controller 本轮又直接复跑该 node，结果
   `1 passed, 3 existing edgartools warnings`。
3. 该断言的职责正是证明真实 fixture 能产生大于强制上限的 facts，从而使 pre-Host value、Host
   cursor envelope 与公开 `fetch_more` remainder 三段链路都真实可观测。若 fixture 被修改到不足，
   必需 smoke 已失去验收能力，测试应明确失败并阻止 gate；skip 会把缺失的真实 smoke 伪装成绿色。
4. 最终计划 §6.5 明确禁止 skip/xfail，§6.4 与 §8 要求任一公开 seam 无法观测时 stop 回 Controller；
   这已覆盖 fixture 无法驱动三段链路的情况。AGENTS.md 与用户要求也都要求适当真实 smoke，不能将
   mandatory evidence 改成可跳过项。

因此不增加 skip guard、不降低为 residual risk、不构造 synthetic fake 替代 real fixture。

### R08-CE-PR-DS-F03 — NOT ACCEPTED / NON-BLOCKING

S1 blocked intermediate tree 的累计 cutover blast radius 是历史计划风险，已经由累计 S1+S2 full
pyright、完整 Fins/aggregate tests、15-file coverage 和双路 code review 控制。当前 continuation
还要求 deletion 后从零完整重跑 §6.6/§6.7；它没有重新引入 S1 独立 commit/review。该 INFO 不需要
新计划文字或当前实现动作。

DS `F04..F12` 均为 PASS。

## 5. Final accepted plan scope

计划最终接受以下闭环：

1. 只删除零 caller/import 的重复 private helper
   `read_runtime_helpers.py::_collect_available_document_types`。
2. 保留 actual typed/sorted owner、shared resolver、全部五个 tests、guards/shared locks 与 README。
3. deletion 后先完成 old-helper zero + actual-owner invariant source/AST proof。
4. fresh candidate-4 `382/482<80` 与 all-five `>=388/482>=80` proof 通过后，再从零完成原
   §6.6/§6.7 全量 acceptance validation。
5. 不增加第六 node、compatibility/fake/private-helper direct test、skip/xfail/coverage bypass、
   无关 dead-code cleanup、deferred issue 或统一 tool authorization 实现。

## 6. 下一 gate

Controller 只允许 exact-scope accepted local plan commit，范围为：最终计划、Codex correction
artifact、Controller validation、MiMo/DS 两路 review、本 adjudication 和 control 状态。不得把
product/tests/README、S1/S2 implementation artifacts 或其它 workspace changes stage 进该 commit。
Accepted plan commit 完成并重新建立 implementation authorization 前，不得删除 helper 或运行
implementation gate。
