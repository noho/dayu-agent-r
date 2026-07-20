# WU-SEMANTIC-OWNERSHIP-01 / R08 Test-Only Cumulative Code-Review Fix — AgentCodex

## 1. Gate 结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation：既有 `R08`，不是新 WU、feature、issue 或独立 sub-WU
- gate：test-only cumulative code-review fix continuation
- branch：`phaseflow/host-issues-control`
- HEAD：`16d6baad4aa62d5c684c564081d78fc605d9b903`
- accepted corrected-plan commit：`0dc85654bb29612a547e7976f3eeb4801171f786`
- 状态：`STOPPED — 五个授权 candidate 全部耗尽，read_runtime_helpers.py 仍低于 80.00%`
- next entry point：Controller 重新裁决 whole-file coverage closure；不得直接进入 code re-review

本轮严格形成 candidate 1→5 的完整连续前缀。五个 exact node 及其 typed fixture 全部只写入
`tests/fins/test_read_runtime_semantic_ownership_guards.py`；没有修改 production、README、
`test_fins_read_runtime.py`、prior artifacts、control 或 design。第五步累计 coverage 为
`388/494 = 78.54%`，低于 80.00%。依 final plan §6.6/§8 的明确 stop condition，本轮没有增加
第六节点、扩大路径、修改 production、恢复原四节点/九 imports、放宽阈值或继续执行最终
acceptance validation。

## 2. Re-entry lock

开始测试修改前独立执行并精确匹配：

| 项 | 独立结果 |
|---|---|
| branch | `phaseflow/host-issues-control` |
| HEAD | `16d6baad4aa62d5c684c564081d78fc605d9b903` |
| accepted plan commit | `0dc85654bb29612a547e7976f3eeb4801171f786`；是 HEAD ancestor；commit subject 为 `docs: accept R08 corrected coverage plan` |
| final plan SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| protected `git diff --binary -- dayu/fins tests` SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` |
| `test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| guards correction-entry SHA-256 | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` |
| staged paths | empty |

所有 lock 均通过，因此没有触发 entry drift stop。

## 3. 第一性原理与 owner 边界

原 blocked artifact 已直接证明：四个越界 shared-file nodes 删除后，R08 normalize/dedup
changed-owner closure 的理论上限低于 whole-file 80%。问题不是 production contract 错误，也
不是应恢复 compatibility/omnibus tests；缺口来自同一 changed module 中其它稳定 public
projection owner 缺少证据。

本轮严格使用 final corrected plan 的 owner 顺序：

1. document type/filter：`FinsReadRuntime.list_documents`；
2. section payload：`FinsReadRuntime.read_section`；
3. table payload：`FinsReadRuntime.get_table`；
4. taxonomy/default concepts：`FinsReadRuntime.query_xbrl_facts`；
5. search next-step：唯一 module-helper 例外 `build_search_next_section_fields`。

前四项均组合真实 filesystem repositories、typed processor fixture 与 public runtime。Candidate
2/3 的 unknown ref 均由 fixture 产生 `KeyError`，测试只观察 public runtime 投影后的
`FinsReadArgumentError`。Candidate 5 之外没有新增 `read_runtime_helpers.py` production helper
import。

## 4. 连续最短前缀与逐步 ledger

最终新增节点的连续前缀精确为 `[1, 2, 3, 4, 5]`：

1. `test_list_documents_projects_stable_document_type_and_filter_contract`
2. `test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref`
3. `test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref`
4. `test_query_xbrl_facts_selects_default_concepts_from_typed_taxonomy`
5. `test_search_next_section_projection_ranks_business_evidence_per_query`

未实现候选：无。五个候选全部耗尽后仍未达到 80.00%，因此 effective decision 是
`STOP_RETURN_TO_CONTROLLER`，而不是越界寻找下一 owner family。

| step | exact node | seam | covered | statements | percent | checker / effective decision |
|---:|---|---|---:|---:|---:|---|
| 0 | correction-entry baseline | existing cumulative set | 320 | 494 | 64.78% | `CONTINUE_NEXT_OWNER_FAMILY` |
| 1 | `test_list_documents_projects_stable_document_type_and_filter_contract` | `FinsReadRuntime.list_documents` | 340 | 494 | 68.83% | `CONTINUE_NEXT_OWNER_FAMILY` |
| 2 | `test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref` | `FinsReadRuntime.read_section` | 352 | 494 | 71.26% | `CONTINUE_NEXT_OWNER_FAMILY` |
| 3 | `test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref` | `FinsReadRuntime.get_table` | 371 | 494 | 75.10% | `CONTINUE_NEXT_OWNER_FAMILY` |
| 4 | `test_query_xbrl_facts_selects_default_concepts_from_typed_taxonomy` | `FinsReadRuntime.query_xbrl_facts` | 382 | 494 | 77.33% | `CONTINUE_NEXT_OWNER_FAMILY` |
| 5 | `test_search_next_section_projection_ranks_business_evidence_per_query` | sole helper exception | 388 | 494 | 78.54% | checker 为 `CONTINUE_NEXT_OWNER_FAMILY`；候选耗尽，effective `STOP_RETURN_TO_CONTROLLER` |

每步新增单一 exact node 后，都从 repository root 立即执行同一个完整增量 coverage set：

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
python -m coverage json -o workspace/tmp/r08-code-review-fix-incremental-coverage.json
python - workspace/tmp/r08-code-review-fix-incremental-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
decision = "STOP_ADDING_TESTS" if percent >= 80.0 else "CONTINUE_NEXT_OWNER_FAMILY"
print(f"{decision} {target}: {covered}/{statements} = {percent:.2f}%")
PY
```

完整 pytest 结果依次为：

- step 1：`387 passed, 3 warnings in 21.53s`；
- step 2：`388 passed, 3 warnings in 21.32s`；
- step 3：`389 passed, 3 warnings in 21.43s`；
- step 4：`390 passed, 3 warnings in 21.49s`；
- step 5：`391 passed, 3 warnings in 21.52s`。

三条 warning 均来自既有 edgartools deprecated modules。本轮没有新增 warning category。

## 5. Candidate contract evidence

### 5.1 Candidate 1

- 真实仓储同时写入 filing 与 material source facts；
- 以 `document_id` 键控断言 canonical `annual_report` / `earnings_call`，不依赖 repository 顺序；
- 断言去空、去重、丢弃 unknown document type 后的 normalized filters；
- 断言 filtered documents 与无匹配时 exact `broaden_filter` suggestion；
- 空 ticker 仍由 public seam 抛 `FinsReadArgumentError`。

### 5.2 Candidate 2

- typed fixture 提供合法/空 ref children、page range、content/title；
- public payload 只保留有效 `ref/title`，identity/citation 由 runtime 产生；
- unknown ref 由 fixture `read_section` 抛 `KeyError`，测试只观察 public
  `FinsReadArgumentError`。

### 5.3 Candidate 3

- typed fixture 分别提供 records、合法 Markdown 与普通文本；
- public payload 精确断言 `records|markdown|raw_text` 的 exact keys/values；
- 断言 table identity/citation，不读取 processor private state；
- unknown table ref 由 fixture `read_table` 抛 `KeyError`，测试只观察 public
  `FinsReadArgumentError`。

### 5.4 Candidate 4

- 真实 document meta 的 `10-K` 与 typed `US-GAAP 2024` 选择年度 US-GAAP concept pack；
- unknown taxonomy 走 global defaults；
- processor 把实际收到的 concepts 原样写入 producer `query_params`，public result 与其同源；
- typed `XbrlQueryExecutionError` 继续由 runtime 投影为 `xbrl_query_failed`；
- 没有直接调用 `_normalize_taxonomy_name` 或 `_resolve_default_xbrl_concepts`。

### 5.5 Candidate 5

- 只使用 final plan 允许的唯一 module helper；
- 单/多 query、hit count、exact fact、malformed/no-section 与无候选 query 均被覆盖；
- 只保留 `section` 与 `evidence_hit_count` 业务字段；
- 业务 scores 明确非平手，反转输入后输出不变，未断言 `_first_index` 偶然顺序。

## 6. Stop 后未执行的 acceptance validation

Final plan 要求只有首次达到 `>=80.00%` 后才 `coverage erase` 并从零执行完整 §6.6/§6.7。
本轮五候选耗尽仍只有 78.54%，所以以下命令/扫描**未执行且不得声明通过**：

- S1 focused、S2 focused、aggregate、full `tests/fins -q` 的最终重跑；
- AAPL/HTML/no-statement 与 Host forced-truncation chain 的最终重跑；
- 最终 15-file exact-key coverage checker；
- full pyright；
- changed Python scoped Ruff；
- final `git diff --check`；
- README trigger/source/propagation/LLM/security/no-touch/correction scans。

五次 incremental coverage collection 全部通过，但它们不能替代上述 acceptance gate。

## 7. Final cumulative tracked manifest 与 SHA-256

最终 tracked `dayu/fins + tests` changed paths 仍为 23 条。除 guards test 外，其余路径均为
entry 时已存在的受保护 cumulative tree；本 continuation 没有修改它们。

| Path | SHA-256 |
|---|---|
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` |
| `dayu/fins/domain/financial_result_contract.py` | `55a87fadce62b1c8d58ac206038d3f5144eaaaf30d4ef9ec82323c5240d7a34b` |
| `dayu/fins/domain/xbrl_result_contract.py` | `81844c4b08cae67f185e862ec69eafcb14ef848eec247bdbf127511a625fc2db` |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `f99725e34f3ccbf52a2b8f152d403e3bddfc62f811597130e0df1d19752e0191` |
| `dayu/fins/processors/bs_report_form_common.py` | `78a6503405196022ed9a20936ea17707b36d5bb8940371388319f58fd0266506` |
| `dayu/fins/processors/bs_six_k_processor.py` | `745727883a2a35af717295506b9b57c6d8c130d976db5be2ee309602b177ede5` |
| `dayu/fins/processors/financial_base.py` | `c591e7538f68dc9cf25f50dbea0a061d7e658a4348bc30b5f4e0fd9769c9a374` |
| `dayu/fins/processors/html_financial_statement_common.py` | `c9a4795fedb7db0454e0ade0513289c68053ef78f535b1483df8dac433379628` |
| `dayu/fins/processors/report_form_financial_statement_common.py` | `c5cbe60cf34a2b623658656c925d4afe81874793822c2fe978f6c77467948fcd` |
| `dayu/fins/processors/sec_processor.py` | `f56fd3a35164eefc99d9e2d0f732f09f5823ad53287b96cd6107e107194e4f7b` |
| `dayu/fins/processors/sec_xbrl_query.py` | `3e787b8a08a5486474b1f72e71c8f4fd93c1bf01aafbc11bf32d9512a1a223f8` |
| `dayu/fins/processors/six_k_form_common.py` | `6fb5758cdc26dae6811f64e5ca0df8008c2030698bcb8fa1187aa368edc9c139` |
| `dayu/fins/tools/fins_tools.py` | `ab096833a249868b50dc25dde23a6a9c512bfe5fe757c7520df791dc077f7a4e` |
| `dayu/fins/tools/read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| `dayu/fins/tools/read_runtime_helpers.py` | `46e87c63a6a7baac20996139203064da95e261c4ef08b04f80821215f1a50b93` |
| `dayu/fins/tools/result_types.py` | `f7ee9d1c31e2e9e62c87bb717da229d0f3182e91af15ea9ac45121da76bd1d83` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `tests/fins/test_financial_read_contracts.py` | `75f6e7f6fee615eca9c1c26bc5af768ffc527677c66d9cf5b76cbaac5879c0a4` |
| `tests/fins/test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| `tests/fins/test_fins_storage_provider.py` | `a2885ce6fd62909a2760d900a46181984ea83e7351037905e28581eb5f27b872` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |

Prior cumulative artifacts 保持 no-touch：

| Path | SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| `docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |

本 artifact 自身无法在自身原始内容中嵌入最终 SHA-256 而保持该值不变；写入完成后由外部命令
重算，并在 Controller handoff 中报告。

## 8. Final diff、staged、scope/security/deferred no-drift

- 最终 23-path cumulative `git diff --binary -- dayu/fins tests` SHA-256：
  `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`。
- guards final SHA-256：
  `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`。
- `test_fins_read_runtime.py` 仍为 entry SHA
  `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`；原四 shared-file
  nodes 与九 imports 未恢复或搬运到该文件。
- 当前 guards 顶层 test 数为 20；相对 correction entry 新增 tests 精确为 candidate 1→5 的
  完整连续前缀。
- 当前 guards 新增 `read_runtime_helpers.py` production imports 精确为
  `{FinsReadArgumentError, build_search_next_section_fields}`；前者是 public typed failure，后者
  仅服务 candidate 5 sole-helper exception。既有 `FinsReadBusinessError` 与
  `_resolve_processor_taxonomy` 保持原样。
- staged paths：empty。
- 未 commit、push、创建 PR 或修改 control。
- production、两份 README、R06/R07 storage/identity/revision/snapshot/citation、Host
  truncation、filesystem containment/symlink/atomic publication 与其它 retained security owner
  均无本 continuation delta。
- R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI 与 prompts
  均保持 deferred/out-of-scope；没有实现、弱化或重分类。
- README：本轮没有用户可见 contract 变化；且授权明确禁止修改其它 path，因此未改 README。
  最终 README trigger/source scan 因 coverage stop 未执行，不能把旧 scan 复用为本轮 pass。

## 9. Residual risk 与停止原因

| residual | 分类 | destination |
|---|---|---|
| 五个授权 owner families 完成后 `read_runtime_helpers.py` 仍为 `388/494 = 78.54%` | requiring explicit Controller decision | Controller 重新裁决 test authorization、whole-file threshold 或 changed-module scope；AgentCodex 不自行扩张 |
| 最终 §6.6/§6.7 acceptance matrix 未执行 | blocked by mandatory five-candidate exhaustion stop | Controller 裁决后必须在新授权树上从零完整重跑，不得复用 incremental sessions |
| 新 cumulative tree 尚无 immutable lock/code re-review | blocked by validation gate | 只有 coverage/完整 validation 关闭后才可锁树并派发双路 code re-review |

到此停止回 Controller。当前不得进入 code re-review、aggregate deepreview、accepted
implementation commit、R09-R12、push 或 PR。
