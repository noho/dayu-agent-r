# WU-SEMANTIC-OWNERSHIP-01 R08 Code-Review Fix Plan Correction — Controller 裁决

## 1. 触发证据

R08 cumulative code-review fix artifact：
`docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-fix-codex.md`
（SHA-256 `4583e02d3c2947db1e4dc2320898b683e15787dadcfecaf1bf296cc291b497f4`）。

AgentCodex 已完成 `R08-CR-CF01` 的机械部分：

- 删除 `tests/fins/test_fins_read_runtime.py` 中四个 plan 外节点；
- 删除九个只服务这些节点的 imports；
- 证明 generic LRU/form-matching common nodes AST 未变；
- 没有把 assertions 搬到其它文件；
- 没有修改 production、README、design、plan、control 或旧 artifacts。

新 tracked implementation diff SHA-256 为
`7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`，
staged tree 为空。

在该精确 tree 上，accepted plan §6.6 coverage 集通过 `386 passed`，15 个 changed
production files 中 14 个达到 exact-key `>=80.00%`；唯一失败为：

```text
dayu/fins/tools/read_runtime_helpers.py
320 / 494 statements = 64.78%
```

达到阈值至少需要 `396 / 494`，还差 76 条语句。AgentCodex 用 AST 从
`_normalize_xbrl_query_payload` 机械计算 R08 changed-owner 的完整模块内调用闭包：
该闭包所有尚未覆盖 executable statements 只有 31 条，即使全部覆盖，理论上限也仅为
`351 / 494 = 71.05%`。

Controller 独立读取 coverage JSON，确认 `320/494`、174 条 missing lines 与阈值计算
成立；当前 R08 XBRL normalize/dedup 区域本身不足以把 whole-file coverage 提升到
80%。这是 accepted plan 的验证边界自冲突，不是产品设计真源冲突。

## 2. Root cause

accepted plan 同时要求：

1. 每个实际 changed production Python file 的 whole-file exact-key coverage
   `>=80.00%`；
2. `test_fins_read_runtime.py` 只能修改一个 fiscal node 与六个 normalize/dedup nodes；
3. coverage 不得通过无关功能、compatibility fixture、fake-only path 或空执行 padding
   补齐。

第 1 项计算整个 `read_runtime_helpers.py`，而第 2/3 项把新增证据限定到只占该文件一小部
分的本轮 changed symbols。原始四个 omnibus nodes 通过直接覆盖 document/search/table/
navigation/default-rule branches 把文件推到 85.83%，但放错了固定 symbol boundary 的
共享文件，其中还包含 compatibility-field assertions。Controller 删除裁决正确；错误在于
Controller adjudication 随后把“不得搬运相同 omnibus/compatibility assertions”过度解释为
“不得为同一 changed module 的其它稳定 owner 建立真实 owner-level tests”，使 whole-file
coverage gate 数学上不可满足。

## 3. Plan-correction finding

### R08-CR-PCF01（HIGH）— coverage owner-test authorization 不完整

#### 必须保留

- `test_fins_read_runtime.py` 的 accepted final plan §5.1 symbol boundary 原样保留；四个
  删除节点和九个专用 imports 不得恢复。
- 15 个 actual changed production files 仍逐文件 exact-key `>=80.00%`；不得改成
  aggregate、changed-line、阈值豁免、omit 或 loose path matching。
- production/README/design、S1/S2 product contracts、R07 no-touch、Host truncation、
  security 与 deferred boundaries 不变。
- 不得实施 MiMo/DS 已拒绝 findings、R09-R12、Issues 142/151/175/177/178 或统一 tool
  authorization。

#### 必须补充到 plan

在既有 S2 test path allowlist 的
`tests/fins/test_read_runtime_semantic_ownership_guards.py` 中，授权最小、拆分清晰的
`read_runtime_helpers.py` stable-owner coverage closure tests。该授权不扩大 test path
allowlist，也不允许恢复原四个 omnibus nodes。

每个新增 node 必须满足全部条件：

1. 只验证一个清晰 owner family，例如 document-type/filter projection、section/table
   public payload projection、search next-step projection 或 XBRL taxonomy/default-concept
   selection；不得把多个无依赖 owner 拼成一个 coverage omnibus。
2. 断言业务可观察的精确输入/输出或 fail-closed 行为；不得只调用函数、只断言非空或锁定
   偶然执行顺序。
3. 优先经 public `FinsReadRuntime` / result projection seam；若该规则没有独立 public seam，
   允许直接调用其唯一模块级 helper owner。该例外不适用于 private cache、snapshot internals、
   processor private method 或 Host private truncation state。
4. 禁止断言 `resolve_has_financial_data` 的 legacy/compatibility inputs，包括
   `availability`、`has_structured_financial_statements`、
   `has_financial_statement_sections`、`has_financial_statement`、`has_xbrl`；不得用字段
   黑名单、fallback 或兼容 fixture 固化旧语义。
5. 禁止复制原四个测试的 omnibus 结构或仅改名搬运；新增 tests 必须按 owner family 重写，
   docstring 说明 owner、业务 contract 和 failure signal。
6. 只增加达到 `>=80.00%` 所需的最小 owner evidence；达到阈值后停止，不追求 100% 或补未
   观察到的边缘分支。
7. coverage closure 后必须重新执行 accepted plan §6.6/§6.7 全部命令；旧 validation、hash
   与 reviews 均不得复用。

#### 为什么这不是“测试驱动 shim”或无关 feature

`read_runtime_helpers.py` 是本轮实际 changed production file，whole-file 80% 是用户与
AGENTS.md 指定的修改后验证目标。新增证据只验证该文件已有稳定 semantic owners，不改变
production，不新增 public schema，不保留旧 contract，不为测试加 fallback。将这些 owner tests
放到 semantic-ownership guards 文件，既避免共享迁移文件 symbol drift，也让 whole-file
coverage 的证据具有真实业务断言，而不是四个 omnibus padding nodes。

## 4. Corrected gate sequence

1. AgentCodex 仅修改 R08 accepted final plan，加入 `R08-CR-PCF01` 的精确授权、边界、测试
   结构与完整再验证要求；不得在 plan-fix turn 继续修改 tests/product。
2. Controller 验证 plan diff 与当前 protected implementation/test deletion tree。
3. AgentMiMo / AgentDS 对完整 corrected plan 并发 plan review；所有 accepted findings 必须
   由 AgentCodex 修复并完成并发 re-review。
4. corrected plan accepted commit 后，AgentCodex 回到同一 cumulative code-review fix，在
   `test_read_runtime_semantic_ownership_guards.py` 实现最小 stable-owner tests，完成
   §6.6/§6.7。
5. Controller 独立验证新 immutable tree；AgentMiMo / AgentDS 对完整 S1+S2+fix tree 并发
   code re-review。
6. code re-review 关闭后才可进入 aggregate deepreview。

## 5. 裁决

**PLAN CORRECTION REQUIRED / NO USER RECONFIRMATION REQUIRED**。

这是同一 R08、同一 umbrella WU 内由实测 coverage 触发的验证计划修正，不修改 controller
discussion、`docs/fins/design.md` 或用户 Topic 6 产品裁决。没有设计真源矛盾，也不需要创建新
WU/Issue。当前机械删除保持在未提交 protected implementation tree；不得回滚，也不得在 corrected
plan accepted 前继续添加 tests。
