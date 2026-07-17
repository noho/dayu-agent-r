# WU-SEMANTIC-OWNERSHIP-01 R08-S2 cumulative implementation evidence

## 结论

AgentCodex 已在同一未提交 R08 cumulative S1+S2 tree 完成 S2 实现与累计验证。S2 没有建立新 WU，没有修改 Host/Engine/Service/UI、storage、prompts、control/design/plan/controller/reviewer 文档，也没有 stage、commit、push 或创建 PR。

当前 tree 的 15 个实际 changed production Python 文件逐文件 exact-key coverage 全部不低于 80.00%；full pyright 为 0，actual-changed Python Ruff 为 0，focused/aggregate/full Fins tests、真实 smokes、source/AST/LLM/README/security/no-touch scans 与 `git diff --check` 全部通过。交付后应由 Controller 锁定本 tree，并在同一 immutable cumulative tree 上发起双路 code review。

## Preflight 与边界

- HEAD：`28b096c7b371afdcff271c6ab4ab971901f83798`
- accepted correction：`1eb896325d0d7d3ccaff1e5412b7da490f3a4485`，已证明是 HEAD ancestor。
- final plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`
- 修改前 staged tree：空。
- 修改前 protected S1 14-path `git diff --binary` SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`，与 accepted S1 evidence 一致。
- S1 的 11 个 production path 未回改；coverage closure 只按 Controller 澄清继续修改已授权的 S1 tests。
- S2 production diff 精确限制在 `result_types.py`、`read_runtime_helpers.py`、`read_runtime.py`、`fins_tools.py`；README 只修改两份授权文档。

## 实现结果

### Public typed owner

- 删除 tools 层旧 `FinancialStatementResult` / `XbrlQueryResult`、public locator、旧 `total` 与 `deduped_fact_count`。
- `PublicFinancialStatementResult` 与 `PublicXbrlQueryResult` 是唯一 public typed contract；旧 tools 类型名没有 alias、re-export、wrapper 或 compatibility shim。
- `project_financial_statement_result` 逐字段复制已校验 producer result，并只在 producer 实际提供时复制 actionable `reason`。
- `project_xbrl_query_result` 独立复制 citation、flat query params 与 final facts 容器；唯一 `fact_count` 赋值是 `len(returned_facts_copy)`。
- 两个 tool description 都消费同一 `result_types.py` owner helper，字段、类型、必填性、枚举、可选 reason、恢复动作与 `SEC_EDGAR` 最小示例自足。

### Read composition

- Financial 路径只执行 producer validation、同 borrowed snapshot citation 生成与 public builder 投影；不猜 reason、不补默认值、不保留 locator。
- XBRL 路径固定为 `validate → copy query params/raw facts → normalize → stable deduplicate → public builder`；不修改 producer payload、facts list 或 raw fact 深层值。
- 缺席 query filters 不补 `None`；合法 zero-hit 输出 `facts=[]`、`fact_count=0`、`data_quality=xbrl` 且 reason 缺席。
- R07 snapshot/citation owner 没有修改；AST 比较证明 21 个 snapshot/borrow/release/revision/citation/source-changed 函数与 HEAD 完全相同。

### Schema 与 Host composition

- `fiscal_period.enum` 从 `FISCAL_PERIODS` 派生，精确为 `FY|H1|Q1|Q2|Q3|Q4`。
- `min_value` / `max_value` 保持 JSON Schema `number`；真实 callable 接受 int/float，拒绝 bool。
- forced-truncation exact node 使用真实 AAPL fixture、真实 provider callable、真实 ToolRuntime、Host-injected `fetch_more`：先证明 pre-Host `fact_count == len(facts)`，再证明 Host 只把 `facts` 替换为 cursor envelope 且所有 sibling 不变，最后证明 visible prefix 与公开 fetch-more remainder 按序拼回原 pre-Host facts。测试没有读取私有 manager/cursor 状态，也没有冻结 fixture facts 数量。

## Coverage closure 质量审计

新增 coverage tests 只验证 public processor contracts 或唯一明确的模块级业务规则 owner。

Public processor 路径：

- `SecProcessor`：真实 AAPL fixture 经 `supports/list/read/search/get_financial_statement/query_xbrl_facts/get_xbrl_taxonomy` 观察结构化业务结果。
- `BsSixKFormProcessor`：只经 `supports/list/read/search/get_financial_statement` 观察结构化 HTML、低置信 terminal、隐藏 OCR 与长报告章节模式。
- 不直接调用 `_collect_*`、`_get_xbrl()`，不验证私有缓存或偶然调用顺序。

保留的模块级 private helper 均是稳定业务规则的唯一 owner，而非空执行：

- HTML：`_extract_first_date`（直接日期格式）、`_extract_fiscal_period_year`（财期 token）、`_extract_fiscal_period_from_direct_text`（直接 scope 证据）、`_normalize_period_end`（期末日期）、`_extract_currency_for_column`（列级币种证据）、`_infer_scale_from_caption`（倍率）、`_parse_optional_numeric`（报表数值）。
- 6-K：`_classify_statement_type_for_table`（6-K 表格类型与导航噪声排除）。OCR 期间、金额、货币、倍率通过公开 `extract_statement_result_from_ocr_pages` 断言。
- Read helper：`_normalize_document_types` / `_normalize_periods`（public tool filters）、`_normalize_section_children`（LLM 导航最小投影）、`_normalize_taxonomy_name` / `_resolve_default_xbrl_concepts`（默认 XBRL query 规则）、`_build_table_data_payload`（公开 table data 三种自描述形态）。
- `_normalize_xbrl_query_payload` 是 final plan 明定的 S2 normalize/dedup/public projection composition owner，六个指定 nodes 直接断言 fail-closed、输入深层不变、stable dedup、optional reason 与 zero-hit。

没有 coverage-only 空执行、fake-only padding、skip/xfail、pragma/omit、changed-line coverage、aggregate threshold 或阈值豁免。

## Validation ledger

以下结果来自包含最终 production/tests/README 内容的同一 cumulative tree；本 artifact 写入后再次机械重跑同一 gate，未再修改 tree。

### Tests 与 smokes

| Gate | 结果 |
|---|---:|
| S1 focused owner matrix | 119 passed，50 deselected |
| S1 fiscal exact node | 1 passed |
| S2 focused/public matrix | 332 passed |
| forced pre-Host → Host envelope → fetch_more exact node | 1 passed |
| AAPL XBRL / HTML financial / no-statement real smokes | 3 passed |
| R08 aggregate matrix | 390 passed |
| full `tests/fins -q` | 857 passed，1 existing skip |
| cumulative coverage test collection | 390 passed |

完整 Fins suite 中的 1 个 skip 是仓库既有状态；本实现没有新增或修改 skip/xfail。pytest 只报告 edgartools 已有 deprecation warnings。

### Exact-key per-file coverage

| Production path | Coverage |
|---|---:|
| `dayu/fins/domain/financial_result_contract.py` | 88.56% |
| `dayu/fins/domain/xbrl_result_contract.py` | 89.30% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 91.37% |
| `dayu/fins/processors/bs_report_form_common.py` | 83.73% |
| `dayu/fins/processors/bs_six_k_processor.py` | 80.17% |
| `dayu/fins/processors/financial_base.py` | 100.00% |
| `dayu/fins/processors/html_financial_statement_common.py` | 80.34% |
| `dayu/fins/processors/report_form_financial_statement_common.py` | 89.01% |
| `dayu/fins/processors/sec_processor.py` | 85.17% |
| `dayu/fins/processors/sec_xbrl_query.py` | 82.69% |
| `dayu/fins/processors/six_k_form_common.py` | 81.91% |
| `dayu/fins/tools/fins_tools.py` | 86.49% |
| `dayu/fins/tools/read_runtime.py` | 84.51% |
| `dayu/fins/tools/read_runtime_helpers.py` | 85.83% |
| `dayu/fins/tools/result_types.py` | 100.00% |

Coverage manifest 与 JSON 均从 repository root 生成，并按 repo-relative exact key 查找；manifest 非空且没有 missing key。

### Static 与 scans

- full `pyright`：`0 errors, 0 warnings, 0 informations`。
- NUL-safe actual-changed Fins Python Ruff：`All checks passed!`。
- `git diff --check`：pass。
- §6.7 A internal old-total inventory：0 命中。
- §6.7 B public/tool/schema/serializer/LLM forbidden inventory：0 命中。
- §6.7 C `fact_count` inventory：只有 typed field、owner description/example、唯一 builder `len(returned_facts_copy)`、两份 current README；read runtime/helper/callable/prompts 无第二赋值。
- AST：`fact_count` production keyword 赋值精确为 `result_types.py:401` 一处；旧 tools class 名不存在；两个 builder 参数 annotation 不含 `Any`。
- R07 no-touch：21 个相关函数 AST 与 HEAD 相同；storage/Host/Engine/Service/UI/prompts path 零 diff。
- exact allowlist/security/scope scan：pass；无 R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI 或其它额外 path。
- staged tree：空。

## README decision

修改前已读取两份 README 的 Agent 更新约束。

- `dayu/fins/README.md` 只陈述 current producer/public contract：最小字段、optional actionable reason、输入不变、稳定去重与唯一 `fact_count`。
- `tests/README.md` 只陈述 current owner-level tests、真实 AAPL/HTML/no-statement/truncation 与 R07 citation 一致性。
- 两份 README 不写 R08/slice/review/gate/未来计划；根 README 与 `dayu/README.md` 不触发。

## Final changed manifest

Production（15）：

- `dayu/fins/domain/financial_result_contract.py`
- `dayu/fins/domain/xbrl_result_contract.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/bs_six_k_processor.py`
- `dayu/fins/processors/financial_base.py`
- `dayu/fins/processors/html_financial_statement_common.py`
- `dayu/fins/processors/report_form_financial_statement_common.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/processors/six_k_form_common.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/result_types.py`

Tests（6）：

- `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_sec_pipeline_download.py`

README（2）：

- `dayu/fins/README.md`
- `tests/README.md`

Artifacts（2）：

- `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md`

总计 25 个 actual changed/untracked paths；没有其它 path。

## Content SHA-256 manifest

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
| `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `tests/fins/test_financial_read_contracts.py` | `75f6e7f6fee615eca9c1c26bc5af768ffc527677c66d9cf5b76cbaac5879c0a4` |
| `tests/fins/test_fins_read_runtime.py` | `c099c628a1f9a3e46289a6ce1d4d51a0c0472daa98c0f49f2b4e043c0bafa09a` |
| `tests/fins/test_fins_storage_provider.py` | `a2885ce6fd62909a2760d900a46181984ea83e7351037905e28581eb5f27b872` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |

本 artifact 自身属于 manifest，但文件无法在自身内容中嵌入其最终原始 content SHA-256 而仍保持该值有效；这里不伪造递归自哈希。AgentCodex 在写入完成后外部重算该文件 SHA-256，并在最终 handoff 直接提供；Controller 必须把该外部值加入 immutable manifest 后再锁树。

## Cumulative diff hash 与 handoff

- 23 个 tracked changed paths 的完整 `git diff --binary` SHA-256：`4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b`。
- 两个 implementation artifacts 均为 untracked，按 Git 定义不进入上述 `git diff --binary` stream；Controller 锁树时必须同时记录两个 artifact 的 content hash。
- staged tree 为空。
- 未 commit、push 或创建 PR。
- 实现 gate 到此停止；下一步只允许 Controller 对最终外部 manifest/hash 复核并发起 immutable cumulative tree 双路 code review。
