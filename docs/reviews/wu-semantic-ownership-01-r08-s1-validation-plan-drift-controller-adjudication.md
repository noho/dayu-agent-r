# WU-SEMANTIC-OWNERSHIP-01 R08-S1 Validation Plan Drift — Controller Adjudication

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，也不是重新打开独立旧 sub-WU。
- 当前内部 remediation sub-WU：`R08`。
- accepted plan commit：`19cbe8a054784297a593cfd6ea823bac40109b99`。
- S1 implementation transition：`c433b21a881ff10311a3bdf8ac77a583a98184aa`。
- implementation evidence：`docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`。
- Controller verdict：`REQUIRES_SAME_R08_CUMULATIVE_VALIDATION_PLAN_CORRECTION`。

S1 producer contract 与 actual processor 实现落在 accepted owner / allowlist 内，focused owner matrix、modified-owner pyright、scoped Ruff、source scans 与 diff check 已绿；但 accepted plan 把 producer cutover 与旧 public consumer 共存的中间 tree 错当成可独立收集、逐文件 coverage 并完成双路 code review 的边界。直接证据证明该边界既无法导入 S2-owned `dayu.fins.tools`，也没有足够的可收集 owner tests 达成每个实际修改 production 文件 `>=80%`。

这不是产品合同冲突，也不能用兼容 type、lazy import、测试 shim、changed-line coverage 或阈值豁免补救。正确动作是保留 producer→consumer 的实现依赖顺序，但把 S1/S2 改为同一累计 destructive cutover，在 S2 恢复 public import graph 后统一执行 full validation、immutable cumulative-tree 双路 code review、fix/re-review 与 aggregate deepreview。

## 2. 已接受的 plan drift findings

### R08-S1-VAL-PD-F01：S1 exact-node collection 不可执行

accepted plan 要求只收集：

```text
tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract
```

但收集任何 `dayu.fins.tools.*` 子模块都会执行：

```text
dayu.fins.tools.__init__
  -> provider
  -> fins_tools
  -> read_runtime
  -> search_engine
  -> read_runtime_helpers
  -> result_types
  -> financial_result_contract.StatementLocator
```

S1 已按目标 contract 删除 `StatementLocator`，而 S2-owned `result_types.py` 尚未迁移，因此 collection 在执行测试前以 `ImportError` 终止。Controller 还独立复现 `tests/fins/test_processor_read_consistency.py` 的同一失败；AgentCodex 对 `tests/fins/test_fins_storage_provider.py` 也取得相同 import-chain 证据。

在 S1 内只有三类表面补救：提前修改 S2 production、给共享测试加 conditional/lazy import、保留兼容 producer type。后两类直接违反 no-shim / no-compat；第一类说明 accepted S1 并非独立 gate，而不是产品实现越界。

裁决：接受。S1 不再作为独立 validation/review gate；S2 consumer cutover 必须紧接现有 S1 tree 实施，之后在累计 tree 上收集完整测试。

### R08-S1-VAL-PD-F02：S1 固定测试集不能满足逐文件 coverage

排除上述不可收集 exact node 后，S1 两份完整 owner tests 为 `147 passed`；实际修改 production 文件 coverage 中七个 processor owner 仅为：

| 文件 | coverage |
|---|---:|
| `bs_report_form_common.py` | 65% |
| `bs_six_k_processor.py` | 48% |
| `html_financial_statement_common.py` | 59% |
| `report_form_financial_statement_common.py` | 41% |
| `sec_processor.py` | 42% |
| `sec_xbrl_query.py` | 67% |
| `six_k_form_common.py` | 66% |

AgentCodex 进一步对全部已发现且当前可收集、会直接或经 registry 触达这些 owner 的既有测试取并集，结果 `176 passed`，上述七个文件仍分别为同样的 `41%–67%`。当前环境没有 `diff-cover`，仓库也没有 changed-line coverage helper；但即使存在，umbrella 既有 Controller 裁决与 AGENTS.md 都不允许用 changed-line / aggregate 覆盖率替代每个 changed production file 的 `>=80%` 目标。

裁决：接受 plan 的 fixed test set 与 gate placement 错误；拒绝降低 coverage 规则。累计 S1+S2 validation 必须对每个实际修改 production 文件逐一达到 `>=80.00%`。若现有累计测试仍不足，AgentCodex 必须在已授权 R08 owner test allowlist 内补直接 behavior/contract tests；不得使用 pragma、omit、aggregate 掩盖、fake-only padding、skip/xfail 或无关测试豁免。

## 3. 唯一允许的计划修正

AgentCodex 必须在不改变当前 product/test implementation diff 的 plan-correction gate 中修订既有 R08 plan，并新增 correction artifact。修正必须同时满足：

1. 保留 S1 producer contracts + actual processors、S2 public read/tool/LLM projection 两个有序 implementation steps；删除 S1 作为独立 validation、immutable review、fix/re-review 与进入 S2 前置门的要求。
2. 明确两步构成同一累计 destructive contract cutover：S1 implementation artifact 保留为 blocked intermediate evidence，不代表可接受 product state；S2 直接在受保护 S1 tree 上继续，不增加兼容层或中间 commit。
3. 删除 S1 exact fiscal node 独立 collection、S1 whole-file coverage session、红色 full-pyright propagation ledger 的 formal pass 义务；这些证据保留为 drift/root-cause 记录，不再冒充 acceptance。
4. 在 S2 后的累计 validation 中运行 S1+S2 全部 focused/real-smoke/aggregate tests，并对 S1+S2 每个实际修改 production 文件逐文件 `>=80.00%`；不得降低为 changed-line、aggregate 或仅四个 tool 文件 coverage。
5. 累计 coverage 测试集必须包含所有 R08 changed owner 的直接 contract/behavior tests。需要新增测试时，只能修改既有 S1/S2 test allowlist 中与该 owner 直接对应的文件；不得扩大 production allowlist、改无关功能或用 coverage-only fixture 固化偶然实现。
6. full pyright 必须在累计 tree 上为 `0 errors`；全部实际修改 Python 文件 scoped Ruff 必须为零；完整 source/AST/LLM/README/security/no-touch scans、三段 forced truncation smoke、AAPL/HTML/no-statement smoke与 `git diff --check` 均保留。
7. Controller 只在累计 S1+S2 tree 全绿后锁定 changed-path content hashes 与完整 `git diff --binary` hash；AgentMiMo / AgentDS 对同一 immutable cumulative tree 并发完整 code review。所有 accepted findings 仍由 AgentCodex 修复并双路 re-review。
8. S1/S2 不做中间 commit；R08 仍只有 aggregate deepreview 全闭合后的 exact-scope accepted local implementation commit。
9. 不改变 §4 product contracts、S1/S2 production/test/README allowlists、R07 no-touch、Host truncation owner、Topic 8-9 no-code、Issues 142/151/175/177/178 与 R09-R12 deferred boundaries。

## 4. 受保护 implementation tree

计划修正期间不得修改当前 11 个 production、3 个 tests 或既有 S1 implementation artifact。AgentCodex handoff 记录的 14 个 tracked path binary diff SHA-256 为：

```text
0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57
```

Controller 在 correction validation 时必须重算；任何 drift 使 correction gate 失败。当前暂存区为空，`git diff --check` 通过。

## 5. 下一 gate

下一 gate 是同一 R08 内的 `R08 cumulative validation plan correction`：

```text
AgentCodex 修订 accepted plan + correction artifact
  -> Controller validation
  -> AgentMiMo / AgentDS 并发完整 plan-correction review
  -> AgentCodex fix 全部 accepted findings
  -> 并发完整 re-review
  -> Controller adjudication
  -> exact-scope accepted plan-correction commit
  -> AgentCodex 在当前 S1 tree 上继续 S2 cumulative implementation
```

R08 code review、implementation commit、aggregate deepreview、R09-R12、umbrella closeout、deferred Issues、统一 authorization、push 与 PR 均未授权。
