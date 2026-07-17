# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift implementation continuation — Codex

## 1. Gate、范围与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：`R08`；本轮是同一 implementation continuation，不是新 WU 或新 slice
- gate：prefix-six exact-drift validation-only implementation continuation
- authority：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-controller-authorization.md`
- accepted plan commit：`c723de5907b834f05b2701d23c1067cb3eb960ce`
- fixed plan SHA-256：`0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521`
- branch / HEAD：`phaseflow/host-issues-control` / `3eacce9af55140e2e3a1a028c047aacd077ae40a`
- Python / pyright：`Python 3.11.15` / `pyright 1.1.409`
- 最终状态：**STOP / PYRIGHT_FAILED / NOT ACCEPTED**

第一性原理判断：当前待证事实是受保护 candidate 6 cumulative tree 是否精确跨过
`read_runtime_helpers.py` 的 80% 阈值，并在同一 immutable tree 上满足完整 acceptance matrix；它不授权继续修改
任何语义 owner。Entry locks、source/AST proof、prefix-six exact proof、focused/smoke/regression 与 15-file coverage
均通过，但 full `pyright` 返回 12 errors。Controller authorization §5 明确要求任一 pyright failure fail closed，
因此本轮未修改 production/tests/README，未运行失败点之后的 Ruff、其余 §6.7 scans 或 `git diff --check`，并在此停止。

## 2. Entry locks

| Lock | Required | Entry result |
|---|---|---|
| `git diff --binary -- dayu/fins tests` SHA-256 | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | exact PASS |
| `read_runtime_helpers.py` content | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | exact PASS |
| actual-owner `read_runtime.py` content | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | exact PASS |
| candidate 6 guards content | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | exact PASS |
| shared runtime test content | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | exact PASS |
| S1 artifact content | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | exact PASS |
| S2 artifact content | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | exact PASS |
| prefix-five predecessor JSON | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` | exact PASS；保留且未重跑 prefix-five |
| stopped prefix-six JSON | `b4c103423956543069ef89434cb7190d3e32b2847cff9f6320dc0a6c6f7b4dee` | entry exact PASS；随后按授权 fresh 重写 |
| staged tree | empty | PASS |

Entry tracked changed-path manifest 精确为 23 paths，顺序与 §9 content manifest 一致；NUL manifest SHA-256 为
`d04a659725063c42ea549e49b46f371b99d766f3a02a308e60efd24be78c092f`。

Entry AST inventory 结果：原五个 stable-owner exact nodes 与 candidate 6 node 均精确出现一次；
`resolve_document_type_for_source` production import 精确出现一次；candidate 6 有完整 docstring、无 skip/xfail marker，
并精确保留以下三条 owner assertions：

```text
UNLISTED_MATERIAL + material -> material
None + filing -> other
FY + filing -> annual_report
```

辅助 AST inventory 的第一次本地 evaluator 错把 `ast.unparse(ast.Assert)` 产生的 `assert ` 前缀与仅表达式预期比较，
因此 evaluator 自身非零；其 stdout 已显示三条断言完全一致。修正 evaluator 只读取 `ast.Assert.test` 后立即重跑并 PASS。
该 evaluator 问题未修改 tree，也不是 entry lock drift；authoritative content hash 与修正后的 AST proof 均精确通过。

## 3. §6.7.G pre-prefix source/AST proof

按 plan §6.7.G 原 source scan 与 AST proof 执行，exit `0`：

```text
PASS old helper source matches=0
PASS old helper definition/caller/import=0; actual typed/sorted owner definition/caller=1
```

证明内容：

- `_collect_available_document_types` definition/caller/import 全部为 `0`；
- `_collect_available_document_types_for_source_documents` top-level definition/caller 均为 `1`；
- actual owner typing 保持 `list[_SourceDocumentSummary] -> list[str]`；
- actual owner 仍调用 `resolve_document_type_for_source`，且精确存在一个 `sorted(...)` return。

## 4. Prefix-five predecessor 与 fresh prefix-six exact proof

Prefix-five predecessor 没有回退 candidate 6、没有重跑、没有 deselect 或重写：

| Evidence | Result |
|---|---|
| test count | `391 passed`（既有 mutation-before evidence） |
| single-file result | `387/485 = 79.79381443% < 80.00%` |
| JSON | `workspace/tmp/r08-prefix-five-proof-coverage.json` |
| JSON SHA-256 before / after | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` / unchanged |

Fresh prefix-six 按 plan 相同八文件、零 deselect 运行：

```bash
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
python -m coverage json -o workspace/tmp/r08-prefix-six-proof-coverage.json
```

Exact result：exit `0`，`392 passed, 3 warnings in 21.70s`，
`391/485 = 80.61855670% >= 80.00%`。Fresh JSON SHA-256 为
`e011ba3d423e96de661c481cce399332cda8765bdacdaf567ea3592e43ffe2ae`。

同源 `executed_lines` direct comparison：

```text
PREFIX_FIVE_PROOF 387/485 = 79.79381443%
PREFIX_SIX_PROOF 391/485 = 80.61855670%
NEWLY_COVERED_LINES [344, 346, 348, 442]
PASS prefix-five/prefix-six direct comparison
```

因此 candidate 6 对该单文件阈值仍是 first/shortest threshold-crossing prefix；达到阈值后没有增加第七项测试。

## 5. §6.6 已执行 validation matrix

所有命令均从 repository root、激活 `.venv` 后执行。

| Command | Exit | Exact result |
|---|---:|---|
| `pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_processor_registry.py -k 'financial or statement or xbrl or quality or reason or fiscal'` | `0` | `119 passed, 50 deselected, 3 warnings in 3.62s` |
| `pytest tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract` | `0` | `1 passed, 3 warnings in 0.60s` |
| S2 focused/public six-file command | `0` | `334 passed, 3 warnings in 16.53s` |
| `pytest tests/fins/test_fins_storage_provider.py::test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` | `0` | `1 passed, 3 warnings in 2.84s` |
| AAPL XBRL / HTML financial / no-statement 三节点 smoke command | `0` | `3 passed, 3 warnings in 3.60s` |
| R08 aggregate eight-file command | `0` | `392 passed, 3 warnings in 17.35s` |
| `pytest tests/fins -q` | `0` | `859 passed, 1 skipped, 3 warnings in 39.02s` |
| fresh cumulative eight-file coverage run | `0` | `392 passed, 3 warnings in 21.64s` |
| exact-key 15-file checker | `0` | 15/15 `PASS`，见 §6 |
| `pyright` | `1` | `12 errors, 0 warnings, 0 informations`；fail-closed stop |

S2 focused/public six-file命令的 exact roots：

```text
tests/fins/test_financial_read_contracts.py
tests/fins/test_fins_read_runtime.py
tests/fins/test_read_runtime_semantic_ownership_guards.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_ingestion_tools.py
tests/fins/test_fins_storage_provider.py
```

真实 smoke evidence：

- AAPL XBRL fixture：`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123`；nodes
  `test_fins_read_aapl_xbrl_query_runs_in_spawned_child` 与
  `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation`；
- HTML financial fixture：`tests/fins/test_fins_storage_provider.py::_fixture_financial_html` 在真实 filesystem repository
  工作区发布为 `aapl-html-2024-10k.html`；node
  `test_fins_read_financial_statement_runs_in_spawned_child`；
- no-statement fixture：同一 AAPL XBRL fixture 去除 `aapl-20240928_pre.xml` 并以无表格主 HTML 发布；node
  `test_fins_read_financial_statement_projects_statement_not_found`。

完整 Fins regression 的唯一 skip 位于未修改文件
`tests/fins/test_docling_upload_service_integration.py:43`，要求设置
`DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 才运行真实 Docling upload integration；本 continuation 没有新增或修改
skip/xfail。三条 warnings 均为已安装 `edgar` 包的 deprecated-module warning，不影响 exit status。

## 6. 15-file exact-key coverage ledger

Fresh cumulative JSON：`workspace/tmp/r08-cumulative-coverage.json`，SHA-256
`a180e9bb67c78bca262e918c15d32fe70ea1259f23564c5df07a6776f1dfc98e`。
Production NUL manifest：`workspace/tmp/r08-changed-production-python.nul`，SHA-256
`1c74512a4b60eed7b7aa79d9fe77d1658f5be90f9c8f59328276fc2a13f87748`。

| Exact repo-relative JSON key | Covered/statements | Percent | Result |
|---|---:|---:|---|
| `dayu/fins/domain/financial_result_contract.py` | `178/201` | `88.55721393%` | PASS |
| `dayu/fins/domain/xbrl_result_contract.py` | `167/187` | `89.30481283%` | PASS |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `254/278` | `91.36690647%` | PASS |
| `dayu/fins/processors/bs_report_form_common.py` | `139/166` | `83.73493976%` | PASS |
| `dayu/fins/processors/bs_six_k_processor.py` | `279/348` | `80.17241379%` | PASS |
| `dayu/fins/processors/financial_base.py` | `14/14` | `100.00000000%` | PASS |
| `dayu/fins/processors/html_financial_statement_common.py` | `572/712` | `80.33707865%` | PASS |
| `dayu/fins/processors/report_form_financial_statement_common.py` | `81/91` | `89.01098901%` | PASS |
| `dayu/fins/processors/sec_processor.py` | `247/290` | `85.17241379%` | PASS |
| `dayu/fins/processors/sec_xbrl_query.py` | `234/283` | `82.68551237%` | PASS |
| `dayu/fins/processors/six_k_form_common.py` | `421/514` | `81.90661479%` | PASS |
| `dayu/fins/tools/fins_tools.py` | `301/348` | `86.49425287%` | PASS |
| `dayu/fins/tools/read_runtime.py` | `840/975` | `86.15384615%` | PASS |
| `dayu/fins/tools/read_runtime_helpers.py` | `391/485` | `80.61855670%` | PASS |
| `dayu/fins/tools/result_types.py` | `138/138` | `100.00000000%` | PASS |

## 7. Fail-closed evidence

Full `pyright` 在受保护 guards 文件返回 12 个 error：

| Location | Direct diagnostic |
|---|---|
| `tests/fins/test_read_runtime_semantic_ownership_guards.py:1555` | optional `ListDocumentsResult["suggestion"]` access，`reportTypedDictNotRequiredAccess` |
| `:1685`, `:1686` | optional `TableDetailResult["caption"]` / `["page_no"]` access，`reportTypedDictNotRequiredAccess` |
| `:1754`, `:1782`, `:1804` | `_DefaultConceptsXbrlProcessor` constructor requires extra keyword-only `taxonomy`，不满足 `DocumentProcessor` protocol constructor |
| `:1769`, `:1772`, `:1773` | `NotSupportedResult` 上访问未定义 `query_params` / `facts` / `fact_count` |
| `:1790`, `:1793`, `:1794` | `NotSupportedResult` 上访问未定义 `query_params` / `facts` / `fact_count` |

Exact terminal line：`12 errors, 0 warnings, 0 informations`。该文件 entry/exit content SHA-256 均为
`cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274`，所以本 continuation 没有通过修改
test 产生或修复这些 diagnostics。当前授权禁止修 tree；本 artifact 不裁决此前何时/为何未被发现，交由 Controller
在相同 immutable tree 与工具版本上复核。

失败点之后按 fail-closed 未执行：

- changed Python scoped Ruff；
- §6.7 A/B/C/D/E/F 与 post-validation §6.7.G；
- source/AST/LLM/README/security/no-touch/no-deferred 完整 acceptance scans；
- `git diff --check`。

这些项目均记为 **NOT RUN DUE TO PYRIGHT STOP**，不能被本轮之前的历史绿色替代。

## 8. Exit locks 与 no-touch boundary

在写入本 artifact 前立即重算的 exit evidence：

| Lock | Exit result |
|---|---|
| 23-path tracked changed manifest count / SHA-256 | `23` / `d04a659725063c42ea549e49b46f371b99d766f3a02a308e60efd24be78c092f` |
| cumulative binary diff SHA-256 | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f`，与 entry 相同 |
| helper / actual owner | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` / `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards / shared | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` / `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 / S2 artifacts | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` / `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| prefix-five predecessor | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb`，与 entry 相同 |
| staged tree | empty |

Continuation 没有修改 candidate 6、原五个 stable-owner tests、dead-helper deletion、actual owner、shared test、
production、tests、README、design、control、plan、prior artifacts 或 S1/S2 artifacts。没有新增第七测试，
没有加入 compatibility/fallback/skip/xfail/pragma/omit。R09-R12、Issues 142/151/175/177/178、统一 authorization
均未实施；Topic 8 保持 no-code，Topic 9 的既有安全机制未被本 continuation 改动。由于 pyright stop，完整
security/no-deferred acceptance scan 未运行，不能把 binary/content no-touch lock 表述成完整 scan pass。

## 9. Immutable 23-path content manifest

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
| `dayu/fins/tools/read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `dayu/fins/tools/result_types.py` | `f7ee9d1c31e2e9e62c87bb717da229d0f3182e91af15ea9ac45121da76bd1d83` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `tests/fins/test_financial_read_contracts.py` | `75f6e7f6fee615eca9c1c26bc5af768ffc527677c66d9cf5b76cbaac5879c0a4` |
| `tests/fins/test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| `tests/fins/test_fins_storage_provider.py` | `a2885ce6fd62909a2760d900a46181984ea83e7351037905e28581eb5f27b872` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |

## 10. Changed files、residual risks 与 handoff

本 continuation 的 durable authored delta 只有：

```text
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-continuation-codex.md
```

Authorized temporary evidence：

```text
workspace/tmp/r08-prefix-six-proof-coverage.json
workspace/tmp/r08-cumulative-coverage.json
workspace/tmp/r08-changed-production-python.nul
```

Residual risks / uncovered areas：

1. **Requires Controller decision:** full pyright 的 12 errors 阻塞本 continuation acceptance；受保护 tree 不允许
   AgentCodex 在本授权下修复。
2. **Uncovered due to fail-closed stop:** scoped Ruff、完整 §6.7 A-G acceptance scans 与 `git diff --check` 未运行；
   必须在 Controller 裁决后的授权路径上从 fail-closed 要求指定的起点重新执行，不能复用为绿色。
3. **Environment-gated existing coverage:** full Fins regression 的真实 Docling upload integration 仍因未设置
   `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 被既有 skip 排除；该文件不在 R08 diff。

Completion decision：**未完成 acceptance；STOP 回 Controller。** 未 stage、commit、push、创建 PR、执行 code review、
aggregate deepreview 或进入下一 gate。
