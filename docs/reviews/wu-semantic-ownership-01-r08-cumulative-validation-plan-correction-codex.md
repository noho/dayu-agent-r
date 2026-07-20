# WU-SEMANTIC-OWNERSHIP-01 / R08 Cumulative Validation Plan Correction — AgentCodex

## 1. Gate result

| 项 | 结果 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| gate | same-R08 cumulative validation plan correction |
| accepted plan commit | `19cbe8a054784297a593cfd6ea823bac40109b99` |
| S1 transition HEAD | `c433b21a881ff10311a3bdf8ac77a583a98184aa` |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md` |
| before plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| final plan SHA-256 | `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d` |
| decision | `CORRECTED / READY FOR CONTROLLER VALIDATION` |
| stop | 未进入 S2 implementation、plan-correction review、commit 或其它后续 gate |

本 gate 只修改 accepted plan 并新增本 artifact。当前 11 个 production、3 个 tests、S1 implementation artifact、control/controller artifact、README/design 均未由本 gate 修改；未 stage、commit、push 或创建 PR。

## 2. 第一性原理与 owner 判断

Controller 的修正动机成立。S1 producer contract 已删除 `StatementLocator`，而旧 public consumer import graph 仍由 S2 owner 持有；因此任何 `dayu.fins.tools` 测试 collection 都会在执行测试前读取已删除类型。该失败与 full-pyright 的 S2 propagation 是同一 producer→consumer contract cutover，不是测试偶发、产品 contract 冲突或可由 shim 修补的独立 S1 缺陷。

同样，S1 固定测试集与已发现相关测试并集都无法让七个实际 changed processor owner 达到 whole-file `>=80%`。降低为 changed-line/aggregate coverage、保留兼容类型、添加 lazy import/test shim、用 fake-only padding 或豁免阈值都会把错误改到非 owner boundary。正确路径是保留 producer→consumer 实现顺序，但把 S1/S2 作为同一未提交 destructive cutover，在 public import graph 恢复后统一验证和 review。

语义 owner 未改变：S1 domain contracts/actual processors 继续拥有 producer truth，S2 `result_types.py` public projection/helper 继续拥有 LLM-facing public truth；R06/R07 storage/identity/snapshot/citation、Host truncation、Topic 8-9 no-code 与 deferred Issues 仍保持各自 owner。

## 3. Before / after sections

| Plan section | Before | After |
|---|---|---|
| §0 / §2.1 | gate 仍描述旧 plan-fix；S1 review/fix/re-review 是 S2 前置 | gate 改为 same-R08 cumulative validation correction；S1→S2 保持有序 implementation steps，但只在累计 tree 全绿后 review |
| §5.1 / §5.3 | 共享 test symbol 边界附带 S1 Controller/reviewer gate；S1 exact fiscal node 独立收集 | 只保留 S1/S2 symbol 实现边界；S1 fiscal node 与全部 owner tests 在 S2 恢复 import graph 后累计收集 |
| §5.4 | S1 独立 pytest/coverage、modified/full pyright、红色 propagation ledger、immutable hash 与双路 review 是 formal pass | S1 artifact 明确是 blocked intermediate/root-cause evidence；删除全部独立 acceptance 义务，直接在同一 tree 进入 S2 |
| §5.5 / §5.6 | scans 和 immutable dual review 构成 S1 gate；review 全闭合后才可 S2 | producer scans 移入累计 tree；S1/S2 间无 validation/review/fix/re-review/stage/commit |
| §6.1 | S1 validation/review 闭合是 S2 entry condition | 受保护 14-path hash 不变、tree 未 stage/commit 即直接续作 S2 |
| §6.5 / §6.6 | S2-only focused/coverage session，coverage 静态只看四个 tools 文件 | 唯一累计 gate运行 S1+S2 focused/exact/aggregate/full-Fins tests、真实 smokes；coverage 对每个实际 changed production 文件逐文件 `>=80.00%` |
| §6.7 | source/public/count/R07 scans | 保留原 scans，并显式补齐 AST、README/LLM、retained-security、exact allowlist/no-touch 分类 |
| §6.9 | S2 cumulative review 文字存在，但未消除 S1 独立 lock/review | Controller 只在累计 validation 全绿后锁 content manifest + binary diff hash；MiMo/DS review 同一 immutable cumulative tree，fix 后完整重跑与双路 re-review |
| §7 | 复制第二份 aggregate validation matrix，可能再次漂移 | §6.6 成为唯一累计/aggregate validation 真源；§7 只定义累计 code-review 后的 aggregate deepreview |
| §8 / §9 | stop/checklist 仍要求 S1 red ledger、coverage、hash/review gate | S1 只保留 blocked artifact/no-shim/no-commit/direct-S2；全部 acceptance checklist 移到累计 S1+S2 tree |
| §10 | 旧 artifact path、旧 before hash `07268...`、旧 `R08-RR-PF-01..02` gate 自检 | 改为本 correction gate 的两路径 allowlist、before/final hash、受保护 diff hash、九项 closure、status/staged/diff checks 与 Controller stop |

## 4. Finding closure

### 4.1 Plan-drift findings

| Finding | 裁决 | Plan closure | 最终状态 |
|---|---|---|---|
| `R08-S1-VAL-PD-F01` | accepted | §5.3/§5.4 删除 S1 exact-node formal collection 与独立 acceptance；§5.6/§6.1 让 S2 直接在同一受保护 tree 续作；§6.6 累计收集完整测试 | `已修复` |
| `R08-S1-VAL-PD-F02` | accepted | §6.6 从实际 changed production manifest 逐文件读取 coverage JSON，缺失或 `<80.00%` 即失败；必要新增测试仅限既有 owner test allowlist，禁止 changed-line/aggregate/pragma/omit/fake-only/skip/xfail/豁免 | `已修复` |

历史 `R08-PF-01..07` 与 `R08-RR-PF-01..02` 仍保持闭合；本 correction 没有重开或弱化其 product contract、forced-truncation public seam、LLM-facing self-description、shared fiscal-period owner、citation/R07 no-touch 或 rejected/no-fix disposition。

### 4.2 Controller §3 九项逐条 closure

1. **保留顺序、取消 S1 独立 gate：已修复。** §2.1、§5.1、§5.3、§5.4、§5.6 明确保留 S1 producer→S2 public consumer 顺序，删除 S1 validation/immutable review/fix/re-review/S2 前置门。
2. **同一累计 destructive cutover：已修复。** §5.4、§5.6、§6.1 把 S1 artifact 定位为 blocked intermediate evidence；S2 在受保护 tree 直接续作，无兼容层或中间 commit。
3. **删除错误 formal pass 义务：已修复。** §5.4 删除 S1 exact fiscal collection、whole-file coverage、红色 full-pyright ledger、Controller lock/dual review；原证据只保留为 drift/root-cause。
4. **累计 tests/smokes/逐文件 coverage：已修复。** §6.5/§6.6 收集全部 S1/S2 focused、exact、aggregate tests、完整 Fins regression、三段 forced-truncation 以及 AAPL/HTML/no-statement smokes；每个实际 changed production 文件单独 `>=80.00%`。
5. **coverage owner tests 与 allowlist：已修复。** §6.6 要求测试集直接触达每个 changed owner；新增测试只准落在既有 S1/S2 test allowlist 且必须是对应 contract/behavior，不扩 production allowlist或添加 coverage-only fixture。
6. **full pyright/Ruff/scans：已修复。** §6.6/§6.7 保留 full pyright `0 errors`、全部实际 changed Python scoped Ruff `0`、source/AST/LLM/README/security/no-touch/allowlist scans、所有 real smokes 与 `git diff --check`。
7. **累计 immutable dual review：已修复。** §6.9 要求 Controller 只在全绿后锁 changed-path content hashes 与完整 binary diff hash；MiMo/DS 对同一 immutable cumulative tree 完整 review，任一 fix 使旧 hash/review 失效并触发完整 revalidation/re-review。
8. **无中间 commit：已修复。** §5.4、§5.6、§6.9、§9 明确 S1/S2 之间不 stage/commit，只有 aggregate deepreview 全闭合后才可能由 Controller 另行授权 exact-scope accepted local implementation commit。
9. **既有 contracts/allowlists/deferred boundaries 不变：已修复。** §4 未修改；§5.1/§6.1 production/test/README allowlists 未改；R07 no-touch、Host truncation、Topic 8-9 no-code、Issues 142/151/175/177/178、R09-R12 仍明确 out of scope。

最终 closure 计数：Controller §3 `9/9 已修复`；plan-drift findings `2/2 已修复`；新增 accepted/deferred/blocking finding `0/0/0`。

## 5. Protected 14-path proof

重算对象精确为 S1 artifact 记录的 11 个 production 与 3 个 tests：

```text
dayu/fins/domain/financial_result_contract.py
dayu/fins/domain/xbrl_result_contract.py
dayu/fins/pipelines/sec_fiscal_fields.py
dayu/fins/processors/bs_report_form_common.py
dayu/fins/processors/bs_six_k_processor.py
dayu/fins/processors/financial_base.py
dayu/fins/processors/html_financial_statement_common.py
dayu/fins/processors/report_form_financial_statement_common.py
dayu/fins/processors/sec_processor.py
dayu/fins/processors/sec_xbrl_query.py
dayu/fins/processors/six_k_form_common.py
tests/fins/test_financial_read_contracts.py
tests/fins/test_fins_read_runtime.py
tests/fins/test_sec_pipeline_download.py
```

重算命令为 `git diff --binary -- <上述14路径> | shasum -a 256`，结果：

```text
0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57  -
```

结果与 Controller §4 锁定值精确一致；本 gate 未改变受保护 implementation tree。

## 6. Scope、diff 与 staged evidence

### 6.1 本 gate changed files

```text
M  docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md
```

其余 dirty paths 均为进入本 gate 前已存在的受保护 S1 tree、S1 artifact、Controller artifact 与 Controller-owned control transition；本 gate 未修改它们。

### 6.2 Checks

- `shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`：`4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d`。
- `git diff --check`：exit `0`，无输出。
- `git diff --check -- docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`：exit `0`，无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md`：预期因存在新增 diff 返回 exit `1`，无 whitespace error 输出。
- `git diff --cached --name-only`：exit `0`，无输出；staged tree 为空。
- 未运行产品 tests/coverage/full pyright/Ruff：本 gate 是 plan/artifact-only correction，且当前 S1 tree 的测试收集/full pyright 红色证据正是已裁决的中间-tree drift；本 artifact 不把它们冒充累计 implementation acceptance。

### 6.3 Final status

最终 `git status --short --untracked-files=all`：

```text
 M dayu/fins/domain/financial_result_contract.py
 M dayu/fins/domain/xbrl_result_contract.py
 M dayu/fins/pipelines/sec_fiscal_fields.py
 M dayu/fins/processors/bs_report_form_common.py
 M dayu/fins/processors/bs_six_k_processor.py
 M dayu/fins/processors/financial_base.py
 M dayu/fins/processors/html_financial_statement_common.py
 M dayu/fins/processors/report_form_financial_statement_common.py
 M dayu/fins/processors/sec_processor.py
 M dayu/fins/processors/sec_xbrl_query.py
 M dayu/fins/processors/six_k_form_common.py
 M docs/host/issues-implementation-control.md
 M docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
 M tests/fins/test_financial_read_contracts.py
 M tests/fins/test_fins_read_runtime.py
 M tests/fins/test_sec_pipeline_download.py
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md
```

该输出与 gate 入口相比只新增 accepted plan 的 modified 状态和本 correction artifact；受保护 implementation/control/controller/S1 artifact 状态未被本 gate 改写。`git diff --cached --name-only` 最终仍为空。

## 7. README / docs / residuals

- README decision：不更新。当前 gate 未改变产品、测试行为、安装/入口或稳定文档职责；Controller §3 明确禁止 README/design 修改。
- Product/test decision：不修改。S2 未开始。
- Residual risk：累计 S1+S2 tests/smokes/coverage/full pyright/Ruff/scans 尚未执行，因为累计 tree 尚未形成；owner 为同一 R08 的 S2 cumulative implementation/validation gate，不是豁免或 later WU。
- Deferred scope：R09-R12、Issues 142/151/175/177/178、Topic 8-9、统一 authorization、push/PR 均未进入。

## 8. Completion / next entry point

Plan correction 已完成，所有 Controller §3 项均已映射到 code-generation-ready plan。下一入口严格是 `Controller validation`；之后才可按 Controller 裁决进入 MiMo/DS concurrent complete plan-correction review。AgentCodex 在此停止，不进入 S2 implementation、review、fix、commit、later sub-WU、push 或 PR。
