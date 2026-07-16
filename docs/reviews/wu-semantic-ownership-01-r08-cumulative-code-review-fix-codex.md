# WU-SEMANTIC-OWNERSHIP-01 R08 累积代码审查修复 — AgentCodex

## 1. Gate 结果

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：既有 `R08`；不是新 WU
- gate：cumulative code-review fix
- finding：只处理 Controller accepted `R08-CR-CF01`
- HEAD：`d24efafc2cd508d468dc4a6644af119f3c7e49f2`
- branch：`phaseflow/host-issues-control`
- 状态：`STOPPED — exact changed-file coverage 无法在 accepted symbol/owner boundary 内关闭`
- next entry point：Controller 对 coverage gate 与共享文件 symbol boundary 的直接冲突作裁决

本轮没有修改 production、README、design、plan、control、旧 reviewer/controller artifact 或 S1/S2 implementation artifact，没有 stage、commit、push 或创建 PR。

## 2. 第一性原理与 owner 判断

`R08-CR-CF01` 成立。四个新增节点验证的是 document discovery、search navigation、table projection、section/default-XBRL 等 generic/compatibility 行为，不是 R08 本轮 changed semantic owner。

R08 在共享文件中的唯一 owner boundary 仍是：

- S1 fiscal consumer：`_extract_fiscal_from_xbrl_query`、`_FiscalXbrlProcessor` 与一个 fiscal node；
- S2 read owner：`_normalize_xbrl_query_payload` 与六个 normalize/dedup nodes；
- generic LRU 与 form matching nodes 保持不变。

因此正确修复是删除越界节点，而不是把其 assertions 搬到其它 allowlist 文件、重新包装为 integration test，或用 coverage 技巧保留无关语义。

## 3. 删除范围

从 `tests/fins/test_fins_read_runtime.py` 删除四个越界节点：

- `test_read_helper_document_discovery_rules_preserve_public_semantics`
- `test_search_next_section_owner_ranks_exact_hits_per_query`
- `test_table_data_projection_owner_emits_self_describing_shapes`
- `test_navigation_and_xbrl_default_rule_owners_fail_closed`

同时删除仅服务上述节点的 imports：

- `_build_table_data_payload`
- `_normalize_document_types`
- `_normalize_periods`
- `_normalize_section_children`
- `_normalize_taxonomy_name`
- `_resolve_default_xbrl_concepts`
- `build_search_next_section_fields`
- `resolve_document_type_for_source`
- `resolve_has_financial_data`

没有新增测试。`deepcopy`、`_extract_fiscal_from_xbrl_query`、`_normalize_xbrl_query_payload`、`_normalize_form_type_for_matching` 及 LRU imports 均为允许节点的直接机械依赖，继续保留。

## 4. Shared-file symbol boundary 证明

对 `HEAD:tests/fins/test_fins_read_runtime.py` 与当前文件执行 top-level function AST 比较：

- common functions 的 AST 变化：零；
- generic LRU node `test_generic_lru_returns_replaced_evicted_and_cleared_values`：未修改；
- form matching node `test_read_runtime_form_matching_consumes_domain_sec_aliases`：AST identical；
- 仅删除旧 fiscal/count 七节点并新增计划允许的新 fiscal/normalize-dedup 七节点；
- 当前文件恰好只保留 9 个节点：2 个未改 generic nodes、6 个 S2 normalize/dedup nodes、1 个 S1 fiscal node；
- 四个 Controller 列名越界节点及其九个专用 imports 均零命中。

没有把这些 generic/compatibility assertions 搬到其它文件。

## 5. Accepted plan §6.6 coverage 实测

删除后先按计划运行累计 coverage 集与 exact-key checker：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
python -m coverage json -o workspace/tmp/r08-cumulative-coverage.json
# 随后运行 accepted plan §6.6 的 changed-production manifest 与 exact-key checker。
```

pytest 结果：`386 passed, 3 warnings`。warnings 均为既有 edgartools deprecation。Coverage JSON 成功写入；15 文件 exact-key ledger 如下：

| changed production file | exact-key coverage | 结果 |
|---|---:|---|
| `dayu/fins/domain/financial_result_contract.py` | 88.56% | PASS |
| `dayu/fins/domain/xbrl_result_contract.py` | 89.30% | PASS |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 91.37% | PASS |
| `dayu/fins/processors/bs_report_form_common.py` | 83.73% | PASS |
| `dayu/fins/processors/bs_six_k_processor.py` | 80.17% | PASS |
| `dayu/fins/processors/financial_base.py` | 100.00% | PASS |
| `dayu/fins/processors/html_financial_statement_common.py` | 80.34% | PASS |
| `dayu/fins/processors/report_form_financial_statement_common.py` | 89.01% | PASS |
| `dayu/fins/processors/sec_processor.py` | 85.17% | PASS |
| `dayu/fins/processors/sec_xbrl_query.py` | 82.69% | PASS |
| `dayu/fins/processors/six_k_form_common.py` | 81.91% | PASS |
| `dayu/fins/tools/fins_tools.py` | 86.49% | PASS |
| `dayu/fins/tools/read_runtime.py` | 84.51% | PASS |
| `dayu/fins/tools/read_runtime_helpers.py` | 64.78% | **FAIL** |
| `dayu/fins/tools/result_types.py` | 100.00% | PASS |

唯一失败是 `read_runtime_helpers.py`：494 statements、320 covered、174 missing。80.00% exact threshold 需要至少 396 covered，即还差 76 条语句。

## 6. 边界内不可闭合证明

使用 AST 从 `_normalize_xbrl_query_payload` 出发机械计算同模块传递调用闭包，并与同一 coverage JSON 的 exact missing lines 相交。闭包包含：

- `_normalize_xbrl_query_payload`
- `_normalize_single_fact`
- `_to_optional_float`
- `_clean_fact_text_value`
- `_looks_like_html_text`
- `_deduplicate_xbrl_facts`
- `_build_fact_dedup_key`
- `_canonicalize_concept`
- `_build_segment_signature`
- `_build_fact_selection_score`
- `_parse_xbrl_decimals`
- `_parse_xbrl_decimals_value`

该完整 changed-owner call closure 尚未覆盖的 executable statements 合计只有 31。即使新增 owner-direct tests 让这 31 条全部执行，理论上限也只有：

```text
current:                 320 / 494 = 64.78%
required:                396 / 494 = 80.16%（满足 >=80.00% 的最小整数 covered 数）
additional required:      76
all missing closure:      31
theoretical maximum:     351 / 494 = 71.05%
```

因此，继续增加 R08 normalize/dedup owner tests、public projection assertions 或同一真实 Host XBRL composition，数学上仍不能达到 80%。剩余至少 45 条必须来自闭包外的 document discovery、search、table、navigation/default-rule 等 generic owners；这正是 Controller 已要求删除且禁止搬运/包装的 coverage padding。

没有新增 fake-only、private cache/method、偶然顺序、compatibility-field、skip/xfail、pragma/omit、阈值豁免或 production fallback。也没有改 production 来规避 changed-file manifest。

## 7. 后续验证状态

用户与 Controller 明确要求任何无法在边界内关闭的 gap 立即停止，不得弱化 plan。因此在 exact coverage checker 失败并完成不可闭合证明后停止，以下 §6.6/§6.7 后续命令未运行，不能声明通过：

- focused/aggregate/full Fins 后续重复矩阵；
- full pyright；
- actual-changed Python Ruff；
- `git diff --check` final gate；
- source/propagation/forbidden/no-touch/AST/README/security scans；
- AAPL、BS 6-K 与 Host truncation final smoke 重跑。

这是 stop-condition 的有意结果，不是把旧 S2 validation 当作当前 tree 的 pass。当前 Controller validation、review lock 与两路 review 均已因 tracked test diff 改变而失效。

## 8. README 与 scope 决策

- 本轮唯一 tracked 修改是删除越界 tests/imports；没有用户可见 contract 变化。
- `tests/README.md` 的既有 S1/S2 current owner-level说明未因本次删除产生新的产品语义，且用户禁止修改 README；保持不变。
- `dayu/fins/README.md`、production、design、plan、control、prior artifacts 均保持 no-touch。
- R09-R12、Issues 142/151/175/177/178、Host/Engine/Service/UI、prompts、统一 authorization 均未触及。

## 9. Tree、hash 与 staged 状态

- tracked changed paths：23（仍为 S1/S2 原 23 路径；本轮只改变其中一个 test path 的内容）。
- 新 tracked `git diff --binary` SHA-256：`7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`。
- accepted final plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- S1 artifact SHA-256：`d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`。
- S2 artifact SHA-256：`08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`。
- 当前 `tests/fins/test_fins_read_runtime.py` SHA-256：`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`。
- staged paths：空。

本 artifact 的最终 SHA-256 不能自嵌入而保持不变；写入结束后由 AgentCodex 在外部重算，并在 Controller handoff 中与上述 S1/S2 hashes 一起报告。

## 10. Residual 与 stop

| residual | 分类 | destination |
|---|---|---|
| `read_runtime_helpers.py` exact-key coverage 64.78%，低于 80.00% | requiring explicit Controller decision | Controller 必须在严格 symbol boundary 与 whole-file threshold 之间重新裁决；AgentCodex 不自行放宽任一约束 |
| §6.6/§6.7 后续验证未执行 | blocked by required immediate stop | Controller 裁决后重开完整累计验证 |

`R08-CR-CF01` 的机械删除已完成，但 cumulative code-review fix gate **未通过**。到此停止回 Controller；不得进入 re-review、aggregate deepreview、accepted commit、R09-R12 或 umbrella closeout。
