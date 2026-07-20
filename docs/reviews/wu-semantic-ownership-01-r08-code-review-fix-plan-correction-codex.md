# WU-SEMANTIC-OWNERSHIP-01 R08 Code-Review Fix Plan Correction — AgentCodex

## 1. Gate 结果

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：既有 `R08`；不是新 WU
- gate：code-review fix plan-only correction
- finding：`R08-CR-PCF01`
- HEAD：`9a90212bcf2f14652ff59f220a5a7a850f6e4096`
- branch：`phaseflow/host-issues-control`
- 结果：`COMPLETE — RETURN TO CONTROLLER FOR COMPLETE CORRECTED-PLAN REVIEW`

本 turn 只修改 R08 计划并新增本 artifact；没有运行 implementation，没有修改 product、
tests、README、control、design、prior artifacts，没有 stage、commit、push 或创建 PR。

## 2. 修正动机与 root owner

`R08-CR-CF01` 的四节点/九 imports 删除是正确修复，不能回滚。删除后累计 coverage 直接
证明：15 个 changed production 文件中 14 个达到 whole-file exact-key `>=80.00%`，唯一失败
`read_runtime_helpers.py` 为 `320/494 = 64.78%`；R08 normalize/dedup changed-owner 完整调用
闭包的理论上限仅 `351/494 = 71.05%`。因此缺口来自 accepted plan 对同一 changed module
稳定 owner 测试授权不完整，不是 product contract、coverage threshold 或共享测试文件 symbol
boundary 错误。

正确 owner boundary 是：

- `test_fins_read_runtime.py` 继续只拥有一个 S1 fiscal node、六个 S2 normalize/dedup nodes 与
  两个未改 generic nodes；四个越界节点与九个专用 imports 不恢复；
- 既有 S2 allowlisted `test_read_runtime_semantic_ownership_guards.py` 承载最小、按 stable owner
  family 拆分的 coverage evidence；
- `read_runtime_helpers.py` production 语义不为 coverage 改写；whole-file exact-key 80% 与完整
  §6.6/§6.7 保持不变。

## 3. Plan 修改段落

Plan before SHA-256：
`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。

Plan final SHA-256：
`86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`。

本次只修改下列段落：

1. §0：切换到当前 plan-only correction gate，固定 23-path protected hash 与本 turn 两条文档
   allowlist。
2. §1 / §2.1 / §3.4：记录 coverage 自冲突的直接数据、完成定义与 guards 文件的新 owner
   职责，不改变 product contract。
3. §5.1：原样保留共享文件 symbol boundary，并精确列出不得恢复的四个节点与九个 imports。
4. §6.1：不扩 test path allowlist；按固定顺序授权 document-type/filter、section、table、
   XBRL taxonomy/default-concept、search next-step 五个候选 owner families。每个 family 都有建议
   exact node、public seam、业务输入/输出/failure signal；前四项必须走 public
   `FinsReadRuntime`，`build_search_next_section_fields` 是唯一 module-helper 例外。
5. §6.1 / §6.5：禁止 compatibility inputs（`availability`、
   `has_structured_financial_statements`、`has_financial_statement_sections`、
   `has_financial_statement`、`has_xbrl`）、omnibus 改名搬运、private cache/processor/Host state、
   偶然顺序、fake-only、空执行、skip/xfail/pragma/omit/阈值豁免。
6. §6.2 / §6.6：定义 correction-entry hashes、逐 node 增量 coverage ledger 与“首次
   `>=80.00%` 立即停止”；之后清空 coverage 并完整重跑保留的 §6.6/§6.7。五个候选全部耗尽
   仍不过线时 stop 回 Controller。
7. §6.7F：加入共享文件删除边界、compatibility/private-helper、AST/import、连续最短前缀与
   exact protected-path scans。
8. §6.9 / §7 / §8 / §9：明确旧 hash/validation/reviews 失效，更新 corrected-plan → test-only
   continuation → full revalidation → cumulative code re-review → aggregate deepreview handoff、
   checklist 与 stop conditions。
9. §10：更新本 gate 的 artifact、hash、diff、staged 与 no-product/test-change 自检要求。

§4 financial/XBRL product contracts、S1/S2 production/test/README path allowlists、R07/Host
边界、retained security、Topic 8-9 no-code、R09-R12 与 Issues 142/151/175/177/178 deferred
decisions均未改变。

## 4. `R08-CR-PCF01` closure

| 要求 | 计划落点 | 状态 |
|---|---|---|
| 保留共享文件固定 symbol boundary 与删除结果 | §2.1、§5.1、§6.7F、§9 | CLOSED |
| 保留 15-file whole-file exact-key 80% 与完整 §6.6/§6.7 | §6.6、§6.7、§7、§9 | CLOSED |
| 只在既有 guards path 授权 split stable-owner tests | §3.4、§6.1、§6.5 | CLOSED |
| 每 family 给出 exact node、business I/O/failure 与 seam | §6.1 | CLOSED |
| public seam 优先、唯一 module-helper 例外 | §6.1 | CLOSED |
| 禁止 compatibility/omnibus/private/fake/empty/skip/coverage bypass | §6.1、§6.6、§6.7F、§8、§9 | CLOSED |
| 增量 ledger 首次过线即停，再完整重验证 | §6.2、§6.6、§8、§9 | CLOSED |
| 旧 hash/validation/reviews 失效并更新 aggregate handoff | §6.7F、§6.9、§7、§9 | CLOSED |

## 5. Protected diff、路径与 staged 证据

Protected scope command：

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

- 修改前：`7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`
- 修改后：`7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`
- protected changed paths：`23`
- protected product/test/README drift caused by this turn：`0`
- staged paths：空

本 turn authored paths 精确为：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md
```

进入本 turn 前已存在的 23 个 tracked product/test/README changes 与两个 untracked S1/S2
implementation artifacts 保持原样；它们不是本 turn authored delta。control、design、prior
review/fix/controller artifacts均无本 turn diff。

## 6. Validation

- `git diff --check`：PASS。
- 两条 authored doc paths whitespace check：PASS。
- protected 23-path binary diff hash before/after：PASS，均为 `7a7ebf...1d6d`。
- `git diff --cached --name-only`：PASS，空。
- product/tests/README/control/design/prior-artifact no-touch：PASS。
- tests / pyright / Ruff / implementation validation：未运行；本 gate 明确是 plan-only correction，
  后续只有 corrected plan accepted 后才允许恢复 test implementation。

## 7. Handoff

停止回 Controller。下一 gate 只能是 Controller 对 corrected plan 与 protected tree 的验证，
随后 AgentMiMo / AgentDS 两路完整 corrected-plan review；不得进入 test implementation、code
re-review、aggregate deepreview、commit、R09-R12、push 或 PR。
