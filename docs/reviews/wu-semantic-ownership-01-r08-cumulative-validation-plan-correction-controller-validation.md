# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Validation Plan Correction — Controller Validation

## 1. Gate result

- umbrella / sub-WU：既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue。
- target：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` 与 AgentCodex correction artifact。
- before accepted plan SHA-256：`bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251`。
- corrected plan SHA-256：`4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d`。
- Controller verdict：`VALIDATED_FOR_COMPLETE_DUAL_PLAN_CORRECTION_REVIEW / NOT_YET_ACCEPTED`。

Controller 完整读取了 plan correction diff 与 AgentCodex artifact。九项 mandatory correction 均已进入 plan，同一 product contract、allowlist、安全 owner、deferred scope 与 no-code decision 未改变。该结论只授权两路完整 plan-correction review，不授权 S2 implementation、code review、commit 或后续 sub-WU。

## 2. 九项 correction 复核

1. S1 producer→S2 public consumer 实现顺序保留；S1 独立 validation/review/fix/re-review 门已删除。
2. S1 artifact 被明确定位为 blocked intermediate evidence；S1/S2 构成同一未提交 destructive cutover。
3. 不可收集 exact node、S1 whole-file coverage session 与红色 full-pyright ledger 只保留为 root-cause evidence，不再冒充 formal pass。
4. §6.6 成为唯一累计 validation 真源，包含 S1/S2 focused、aggregate、完整 `tests/fins`、forced-truncation public chain、AAPL/HTML/no-statement smokes。
5. Coverage 仍要求每个实际 changed production Python 文件独立 `>=80.00%`；changed-line、aggregate threshold、pragma/omit、fake-only padding、skip/xfail 与豁免均被禁止。
6. 累计 full pyright 必须 `0 errors`；全部实际 changed Python scoped Ruff 必须零；source/AST/LLM/README/security/no-touch/allowlist scans 与 `git diff --check` 保留。
7. Controller 只在累计 validation 全绿后锁定完整 path content manifest 与 binary diff hash；MiMo/DS 审查同一 immutable cumulative tree，任何 fix 触发新 hash、完整 revalidation 与双路 re-review。
8. S1/S2 无 stage/commit；只有累计 code review 和 aggregate deepreview 全闭环后才可能授权一个 exact-scope local implementation commit。
9. §4 contracts、§5.1/§6.1 allowlists、R07 no-touch、Host truncation owner、Topic 8-9 no-code、Issues 142/151/175/177/178、R09-R12 与统一 authorization 边界未改。

## 3. 受保护 implementation tree

Controller 重算 11 个 S1 production 与 3 个 S1 tests 的完整 binary diff：

```text
0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57  -
```

它与 S1 handoff、plan-drift adjudication 与 correction artifact 精确一致。Plan-correction gate 没有修改这 14 个路径；S1 artifact、Controller artifact、control、README/design 也没有被 AgentCodex 改写。暂存区为空。

## 4. Static checks 与 review challenge points

- `git diff --check`：PASS。
- corrected plan SHA-256：PASS，精确为 `4ff2c00c...`。
- protected 14-path diff SHA-256：PASS，精确为 `0d985b85...`。
- stale S1 gate / old correction artifact / old before-hash scan：零命中。
- 产品 tests/coverage/full pyright/Ruff 未在本 Markdown-only gate 重跑；累计 tree 尚未形成，plan 明确禁止把当前红色中间 tree 当 acceptance。

两路 reviewer 必须特别挑战而非默认接受：

1. §6.6 changed-production manifest 是否精确过滤 production Python，避免把 README 等非 Python path 误当 coverage target；
2. coverage JSON 的逐文件读取/阈值判定是否足够可执行、不会退化成手工或 aggregate 判定；
3. 完整 Fins regression 与 coverage session 是否同时覆盖所有 changed owner，测试 diff allowlist 与零 diff regression target 是否表达无歧义；
4. S1/S2 symbol allowlist、shared test file boundary、S1 protected tree 与 S2 entry 是否存在残留矛盾；
5. cumulative code review、aggregate deepreview 与 accepted commit 顺序是否仍满足用户指定的 review/fix/re-review 闭环；
6. forced-truncation、R07 no-touch、LLM-facing self-description、retained security 与 deferred/no-code scope 是否被计划修正意外削弱。

上述是 adversarial review questions，不是 Controller 预先接受的 findings；最终 finding 由两路 review 证据后裁决。

## 5. 下一 gate

下一 gate：AgentMiMo / AgentDS 对 corrected plan、plan-drift adjudication、S1 implementation evidence、correction artifact 与本 Controller validation 做并发完整 `$planreview` / `/planreview` 等价审查。

两路 review 前后不得修改 plan、product、tests、README/design、control/controller artifacts。Reviewer 只能新增各自 allowlisted artifact。Reviewer verdict 不自行授权 S2。
