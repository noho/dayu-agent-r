# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift plan-review fix（AgentCodex）

## 0. Verdict

`READY_FOR_CONTROLLER_VALIDATION / NOT_IMPLEMENTATION`

- 时间：`2026-07-17 10:47:46 +0800`
- umbrella / remediation：既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、sub-WU 或 slice。
- gate：同一 prefix-six exact-drift plan-review fix gate；本 artifact 完成后停回 Controller。
- HEAD：`e9c68cdc1d6079374149df2b8d0ff0ca3b63a02e`
- entry plan SHA-256：`bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd`
- final plan SHA-256：`0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521`

## 1. 第一性原理与 owner 裁决

Controller accepted findings 指向的是 final plan 与 locked stopped tree 之间的精确文本漂移，不是 production、test 或 product contract 缺陷。正确语义 owner 是
`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`；因此本 gate 只修 final plan，并用本 artifact 固化证据。通过修改 tests、恢复旧字段、补兼容分支或重跑 implementation validation 来修正计划文本，都会越过 owner boundary。

已完整读取并核对：

- `AGENTS.md`
- `docs/host/issues-implementation-control.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- `docs/fins/design.md`
- final plan
- MiMo / DS 两路 plan review
- Controller plan-review adjudication

## 2. Accepted findings closure

| Finding | Closure | 结果 |
|---|---|---|
| `R08-CR-PCPR-F01` | §5.1 已将六个 stale、locked tree 中不存在的 node 名精确替换为 shared file 当前六名；未改 tests，未恢复 `total` / `deduped_fact_count` 或任何 compatibility semantics。 | `CLOSED` |
| `R08-CR-PCPR-F02` | §1 与 §6.6 已明确 `387/485 -> 391/485` 只关闭 `dayu/fins/tools/read_runtime_helpers.py` 单文件 80% gap；15 个 changed production files 由累计 S1+S2 owner tests、public projection tests 与 real smokes 共同覆盖，唯一验收真源为 §6.6 fresh exact-key checker。`first/shortest` 与 `>=80.00%` 均未弱化。 | `CLOSED` |
| `R08-CR-PCPR-F03` | §6.1 已明确 current stopped tree diff `e40de2a0...33f` 包含完整 S1+S2、dead-helper deletion 与 candidate 6；§6.2 items 1–7 均标记为“已完成于 stopped tree”并作为受保护累计状态，只有 item 8 与 §6.6/§6.7 是 current verification actions。 | `CLOSED` |
| `R08-CR-PCPR-F04` | §7 已将 S2 artifact `08085bde...c648` 的结果标为较早且不同 tree state 的历史数量级/继承问题参考，不是 current expected result；current exact results 只由 §6.6 fresh validation 产生。 | `CLOSED` |
| `R08-CR-PCPR-F05` | 所有引用 helper hash `1d7b4bf1...5ea9b` 的 lock 标签已统一为“S1+S2 cumulative `read_runtime_helpers.py` content state（含 dead-helper deletion 与 public projection/normalization）”；hash 不变。历史 root-cause/stop-condition 中对 deletion 事件本身的准确叙述保留。 | `CLOSED` |

F01 使用的 authoritative exact names：

```text
test_xbrl_query_payload_missing_facts_fails_closed
test_xbrl_query_payload_rejects_non_flat_query_params
test_xbrl_query_payload_preserves_raw_input_during_normalization
test_xbrl_query_payload_stable_dedup_projects_unique_fact_count
test_xbrl_query_payload_preserves_owner_quality_and_optional_reason
test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason
```

## 3. 保持不变的 proof 与边界

- Prefix-five predecessor 仍为 `391 passed`、`387/485 = 79.79381443% < 80.00%`，JSON SHA-256 仍为 `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb`。
- Prefix-six expected result 仍为 `392 passed`、`391/485 = 80.61855670% >= 80.00%`。
- Candidate 6 相对 prefix-five 新覆盖行仍精确为 `[344, 346, 348, 442]`；candidate 6 已存在且 no-touch，不回退、不重跑 prefix-five、不新增第七项。
- Current locks、full §6.6/§6.7 validation、exact-key 15-file checker、fail-closed、security/no-code boundaries、R07/Host owner、Topic 8–9、Issues 142/151/175/177/178、统一 authorization 与 R09–R12 deferred boundaries均未改变。
- Product contract、S1/S2 path allowlists、README decision、full validation 与 aggregate handoff 均未弱化。

## 4. Current locks

| Lock | Before / final verification |
|---|---|
| HEAD | `e9c68cdc1d6079374149df2b8d0ff0ca3b63a02e` / unchanged |
| `dayu/fins + tests` tracked binary diff SHA-256 | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` / unchanged |
| S1+S2 cumulative `read_runtime_helpers.py` content state（含 dead-helper deletion 与 public projection/normalization） | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` / unchanged |
| actual-owner `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` / unchanged |
| candidate 6 guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` / unchanged |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` / unchanged |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` / unchanged |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` / unchanged |
| staged tree | empty / empty |

## 5. Exact scope 与 no-touch

本 gate authored paths 精确为：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md
```

未修改 control、product、production、tests、README、design、prior reviews、plan-correction artifacts、S1/S2 artifacts。未运行 implementation、pytest、coverage、pyright、Ruff 或 smoke；未 stage、commit、push 或创建 PR。

Final `git status --short --untracked-files=all`：

```text
 M dayu/fins/README.md
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
 M dayu/fins/tools/fins_tools.py
 M dayu/fins/tools/read_runtime.py
 M dayu/fins/tools/read_runtime_helpers.py
 M dayu/fins/tools/result_types.py
 M docs/host/issues-implementation-control.md
 M docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
 M tests/README.md
 M tests/fins/test_financial_read_contracts.py
 M tests/fins/test_fins_read_runtime.py
 M tests/fins/test_fins_storage_provider.py
 M tests/fins/test_processor_read_consistency.py
 M tests/fins/test_read_runtime_semantic_ownership_guards.py
 M tests/fins/test_sec_pipeline_download.py
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-mimo.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
```

上述除两个 authored paths 外均为 gate entry 已存在的 stopped-tree 状态，保持 no-touch。

## 6. 文本验证

- Entry plan SHA 精确匹配：`PASS`。
- Final plan 的 F01 六名 exact-name scan：`PASS`；六个 stale 名称零命中。
- F02 single-file/full-acceptance owner boundary：`PASS`。
- F03 stopped-tree/current-verification 时序：`PASS`。
- F04 historical baseline 标签：`PASS`。
- F05 cumulative helper content-state 标签：`PASS`。
- `git diff --check`：`PASS`。
- `git diff --check -- docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md`：`PASS`。
- Protected locks final recheck：`PASS`。
- Staged empty final recheck：`PASS`。

## 7. Handoff

`READY_FOR_CONTROLLER_VALIDATION / NOT_IMPLEMENTATION`

停止回 Controller。下一步只能由 Controller 验证 fixed plan 与本 artifact，并在通过后派发两路完整 fixed-plan re-review；不得进入 implementation、tests、code review、aggregate deepreview、commit 或其它后续 gate。
