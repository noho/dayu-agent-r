# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift plan review Controller adjudication

## 1. 结论

`PLAN_FIX_REQUIRED / FIVE_ACCEPTED_CLARITY_AND_TEMPORAL_FINDINGS / ZERO_BLOCKER`。

Review target：

- final plan：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- SHA-256：`bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd`

两路 reviewer 均独立匹配 final plan、cumulative diff 与全部 current locks：

- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-mimo.md`，SHA-256 `531662c2f2d9064ee3708be1abb5d029c6b50706cf6b0046683cfe7114912864`，verdict `PASS / ZERO_MATERIAL_FINDING`；
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-ds.md`，SHA-256 `cfe34587df2e4a4c10c9008ffa57d91febc04fd7b918f53781bbed735e026e57`，verdict `CONDITIONAL PASS`。

AgentDS verdict 概要写“4 findings”，正文实际枚举 `M1..M3` 与 `L1..L2` 共 5 项；Controller
ledger 以逐项正文为准。Reviewer verdict 不独立授权 implementation。

## 2. Accepted findings

### `R08-CR-PCPR-F01`：§5.1 六个 shared-test node 名称 stale

`ACCEPTED / MEDIUM`。

Plan §5.1 当前列出的六个 `total`/`deduped_fact_count` 时代名称在 locked
`tests/fins/test_fins_read_runtime.py` 中全部不存在。当前 authoritative node names 精确为：

```text
test_xbrl_query_payload_missing_facts_fails_closed
test_xbrl_query_payload_rejects_non_flat_query_params
test_xbrl_query_payload_preserves_raw_input_during_normalization
test_xbrl_query_payload_stable_dedup_projects_unique_fact_count
test_xbrl_query_payload_preserves_owner_quality_and_optional_reason
test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason
```

这些节点直接对应当前 tightened contract，且 shared file SHA lock 为 `01db5538...6692`。计划必须用
上述 exact names 替换旧列表，不得改 tests 或恢复已删除字段/compatibility semantics。

### `R08-CR-PCPR-F02`：prefix proof 与 full acceptance coverage scope 未显式区分

`ACCEPTED / MEDIUM`。

`387/485 -> 391/485` 只证明 `read_runtime_helpers.py` 单文件以 stable-owner tests 达到 80%，不代表
candidate 6 单独关闭全部 15 changed production files 的 coverage。计划必须在 summary/§6.6 明确：
single-file prefix proof 只关闭该 helper file 的 threshold gap；15-file full acceptance 由累计
S1+S2 owner/public/real-smoke tests 共同产生，并只以 §6.6 fresh exact-key checker 为真源。

### `R08-CR-PCPR-F03`：§6.1 no-delta 与 §6.2 future implementation 时态冲突

`ACCEPTED / MEDIUM`。

当前 cumulative diff `e40de2a0...33f` 已含完整 S1+S2、dead-helper deletion 与 candidate 6；本
continuation 不授权 production/test/README delta。然而 §6.2 items 1-7 仍使用待实施语气，可能诱导重复
实现。计划必须明确：items 1-7 是当前 stopped tree 已完成且受保护的累计状态；只有 item 8、§6.6 与
§6.7 是本 continuation 的 verification actions。可通过给 items 1-7 添加“已完成于 stopped tree”状态
标记并在 §6.1/§6.2 增加唯一时序说明实现，不得改产品树。

### `R08-CR-PCPR-F04`：§7 historical baseline provenance 不够精确

`ACCEPTED / LOW`。

§7 的 focused/smoke/pyright/Ruff baseline 来自较早 S2 tree，只能作历史数量级/继承问题参考；当前
tree acceptance 不得以它作为 expected result。计划必须明确 baseline 来自 S2 artifact
`08085bde...c648` 的不同 tree state，current exact results 只由 §6.6 fresh validation 产生。

### `R08-CR-PCPR-F05`：helper content lock label 语义范围过窄

`ACCEPTED / LOW`。

`1d7b4bf1...5ea9b` 是当前 S1+S2 cumulative `read_runtime_helpers.py` content lock，既包含
dead-helper deletion，也包含已完成 public projection/normalization state。把它只标为“deletion 后内容”
会低估锁的语义范围。计划须统一改为等义的 cumulative-state content lock label；hash 不变。

## 3. Open questions 与 residual adjudication

| Reviewer item | Controller decision |
|---|---|
| Q1 当前 15-file coverage 是否已验证 | 不是 plan blocker；本 continuation 尚未运行 full §6.6，fresh exact-key checker 正是唯一 destination，任何低于 80% 都 fail closed |
| Q2 guards 其余 tests 是否依赖未完成 S2 | 已由 direct evidence 关闭：current S2 imports存在，且 stopped implementation 的同一八文件 prefix-six 已完整收集并通过 `392 passed` |
| Q3 proof JSON 是否仍存在 | Controller 直接确认两个文件存在；prefix-five SHA `43986a2d...b59fb`、prefix-six SHA `b4c10342...b4dee` 均精确匹配 |
| coverage.py/test-count portability | 保持此前裁决：locked environment 下 exact drift 是 intentional fail-closed proof，不预先兼容 |
| R09-R12/deferred regression | 由后续 sub-WU gates/umbrella aggregate deepreview owner，非当前 plan fix |

不接受新增 coverage-version compatibility、旧 test 名 alias、fallback、重复测试或产品修改。

## 4. Protected boundary

Plan fix 只允许修改最终 plan 与新增 AgentCodex plan-fix artifact。以下 locks 必须保持：

| Lock | Required value |
|---|---|
| cumulative `dayu/fins + tests` diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| helper cumulative content | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1/S2 artifacts | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` / `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged | empty |

Topic 8-9 no-code、安全机制、R07 no-touch、Issues 142/151/175/177/178、R09-R12、统一
authorization 与所有 deferred boundaries 保持不变。

## 5. Next gate

AgentCodex 执行同一 R08 plan-only fix，关闭 `F01..F05`，不得实施任何 product/test/README delta 或
运行 implementation validation。Controller validation 后，AgentMiMo 与 AgentDS 必须对完整 fixed plan
做并发、独立、完整 re-review；所有 accepted findings 关闭前不得 accepted-plan commit 或实现。
