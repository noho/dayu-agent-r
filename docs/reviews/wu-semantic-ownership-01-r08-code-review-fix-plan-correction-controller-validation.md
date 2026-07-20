# WU-SEMANTIC-OWNERSHIP-01 R08 Code-Review Fix Plan Correction — Controller Validation

## 1. Verdict

**PASS / READY FOR DUAL COMPLETE CORRECTED-PLAN REVIEW**。

- umbrella / sub-WU：既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`
- gate：code-review fix plan-only correction validation
- corrected plan：
  `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- corrected plan SHA-256：
  `86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`
- AgentCodex artifact：
  `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md`
- AgentCodex artifact SHA-256：
  `b38d9decbb4ff3f970a1f499cd87cf3fae9ca35e37299902cf1fc4d937ab7410`
- protected 23-path `dayu/fins + tests` binary diff SHA-256：
  `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`
- staged paths：空

## 2. `R08-CR-PCF01` closure

Controller 完整读取 corrected plan 与 Codex artifact，并核对当前代码、测试、coverage JSON
与 protected tree。修正已 code-generation-ready：

1. `test_fins_read_runtime.py` 的固定 symbol boundary 保留；四个删除节点、九个 imports、
   generic LRU/form-matching AST no-touch 均被精确锁定。
2. 15 个 actual changed production Python files 的 whole-file exact-key coverage
   `>=80.00%` 保留；没有 changed-line、aggregate、omit、pragma、阈值豁免或 loose path
   fallback。
3. test path allowlist 未扩大。新增 evidence 只可进入既有
   `test_read_runtime_semantic_ownership_guards.py`。
4. 五个候选 owner families 顺序固定：document type/filter、section payload、table payload、
   XBRL taxonomy/default concepts、search next-step；前四个强制走 public
   `FinsReadRuntime`，第五个是唯一 module-helper 例外。
5. 每个候选都有 exact node、repository-backed/typed fixture、业务输入/输出/failure signal；
   node 必须是连续最短前缀，逐 node 运行 coverage ledger，首次达到 80% 立即停止。
6. `availability`、`has_structured_financial_statements`、
   `has_financial_statement_sections`、`has_financial_statement`、`has_xbrl` 与
   `resolve_has_financial_data` compatibility evidence 明确禁止；omnibus 改名搬运、private
   cache/processor/Host state、偶然顺序、fake-only、空执行、skip/xfail/pragma/omit 均有
   source/AST stop gate。
7. 新增 test 后必须清空 coverage 并从零完整重跑 §6.6/§6.7；旧 plan SHA、review lock、
   validation、review verdict 和 `7a7ebf...1d6d` coverage 均明确失效。

## 3. Product / security / deferred no-drift

- §4 financial/XBRL producer/public product contracts零变化。
- R07 snapshot acquire/borrow/release、cache/revision、citation、source-changed owners零授权。
- Host truncation/fetch-more composition owner零变化。
- filesystem containment、symlink、snapshot/revision、atomic publication 与其它 retained
  security机制未删除或弱化。
- 未实施统一 tool authorization framework。
- R09-R12、Issues 142/151/175/177/178 与其它 deferred owners 保持 out-of-scope。

## 4. Independent validation

- corrected plan SHA-256：PASS
- protected 23-path diff hash before/after：PASS，仍为 `7a7ebf...1d6d`
- protected changed paths：23
- `test_fins_read_runtime.py` SHA-256：
  `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`
- guards correction-entry SHA-256：
  `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff`
- compatibility/private-helper negative scan on current guards entry：零命中
- `git diff --check`：PASS
- staged paths：空
- plan-only authored scope：corrected plan + Codex artifact；product/tests/README/control/design/
  prior artifacts未由 AgentCodex 修改

本 gate 不运行 implementation tests/pyright/Ruff；这些命令只在 corrected plan 接受并恢复
test-only continuation 后运行，不能复用旧绿色。

## 5. Next gate

AgentMiMo 与 AgentDS 必须对 SHA
`86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`
的完整 corrected plan 并发 review，并各自重算 plan/protected-tree hashes。review 必须挑战五个
candidate 是否真实穿过 public seam、能否达到 coverage、是否偷带 compatibility/fake/private
state、是否在首次过线停止，以及 correction 是否保留完整 §6.6/§6.7/security/deferred gates。

不得进入 test implementation、code re-review、aggregate deepreview、accepted implementation
commit、R09-R12、push 或 PR。
