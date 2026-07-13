# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Implementation — AgentCodex

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `implementation`
- Implementer: `AgentCodex`
- Status: `S1 implementation complete`
- Artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Next action: 由 controller 裁决并进入 S1 code review；本实现 agent 不 review、不 commit、不 push、不进入 S2/S3 或下一 gate。

## First-Principles And Owner Decision

动机成立且严重性为 `production-high`。财务 rows 没有可靠 scale 会造成数量级错误；XBRL execute 异常被改写成 `facts=[]` 会制造错误的成功事实；read runtime 删除 producer 已产生的 period/quality/reason 则使下游无法从同一真源恢复语义。

本 slice 固定以下 owner：

- `dayu.fins.domain.financial_result_contract` 拥有 financial period、scale、quality/reason matrix、statement locator shape、producer payload validator 与 decimals scale truth。
- `dayu.fins.domain.xbrl_result_contract` 拥有 XBRL producer result、concept execution summary、all-failed typed exception 与 raw total/quality/reason validator。
- SEC/BS/HTML/OCR processor 拥有直接 period/scale evidence 的产生；无法产生时返回 typed partial degradation，不从日期月份、units 或 read fallback 猜测。
- read runtime 只校验、逐字段复制、附加 document identity/citation，并产生 read-owned `deduped_fact_count`；它不重算 producer `total/data_quality/reason`。
- Fins tool schema description 拥有 LLM-facing 自解释文本；Host/Engine 不新增 Fins 分支。

edgartools implementation-start characterization 先于 producer 改动执行。当前环境 `edgartools 5.30.0` 的 `FactQuery.execute()` 对合法 `[]` 正常返回，对 facts view sentinel exception 原样传播；`2 passed`，因此未命中 stop condition。

## Changed Files

### Production

- 新增 `dayu/fins/domain/financial_result_contract.py`
- `dayu/fins/domain/xbrl_result_contract.py`
- `dayu/fins/processors/financial_base.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/bs_six_k_processor.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/processors/html_financial_statement_common.py`
- `dayu/fins/processors/six_k_form_common.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/result_types.py`
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/tools/fins_tools.py`

### Tests

- 新增 `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_fins_storage_provider.py`

### Implementation Artifact

- 新增 `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`

所有修改均位于 accepted plan S1 allowlist；未修改 `filing_semantics.py`，因为 S1 所需 `FiscalPeriod/FinancialDataQuality` 可直接复用现有 domain owner。

## Contract Changes

### Financial Statement

- 新增 required `FinancialStatementResult`：`statement_type/periods/rows/currency/units/scale/data_quality/reason/statement_locator` 全部必须存在，absence 由显式 `None` 表达。
- validator fail closed：拒绝 required 字段缺失、非法 ISO date/scale/JSON shape、空 rows 声明完整质量、partial 无 reason、完整结果携带 reason、locator statement type 漂移，以及 `units` 承载 `in millions` 等 scale 文本。
- 统一 evidence matrix：只缺 scale、只缺 fiscal semantics、二者都缺分别产生 `scale_unavailable`、`period_semantics_unavailable`、`scale_and_period_semantics_unavailable`。
- decimals scale helper 成为单一真源；processor probe 与 read fact normalization 复用。probe exception/malformed 通过 `FinancialScaleOutcome.query_failed` 显式保留，失败时 statement rows 保留但质量降级。
- SEC/BS statement period 不再用 `period_end[:4]` 写 fiscal year/FY；只消费 XBRL fact 的直接 `fiscal_year/fiscal_period`。HTML/OCR 不再根据月份/as-of date 猜 Q/FY，只使用明示 token 或无歧义 `year ended`。
- HTML caption 与 OCR heading 分别拥有 scale evidence；OCR income-summary fallback 复用同一 heading helper。HTML/OCR `units` 只保留货币/计量单位，不再拼入 scale。

### XBRL Execution And Result

- `XbrlConceptQuerySummary` 显式保存 rows、attempted/successful/failed concepts；concept identity 有界，异常对象/raw message 不进入结果。
- `_query_facts_rows` 对每个 concept 只执行一次：合法 list（包括 `[]` 和本地 filter 后空集）计 successful；exception、非 list、含非 mapping row 计 failed。
- 至少一个 successful 且存在 failed 时 caller 返回 `partial/query_partially_failed`；全部 attempted concept 失败抛 `XbrlQueryExecutionError` 并以最后异常为 cause；concepts 规范化为空直接 fail input contract。
- Sec 与 BS caller 都显式消费 `summary.rows/successful_concepts/failed_concepts`，不把 summary 当 list，不丢 failed accounting。
- producer `XbrlFactsResult` required `query_params/facts/total/data_quality/reason`；`total` 必须等于 raw normalized facts 数。producer/domain type 不声明 `deduped_fact_count`，validator 对夹带该 read-side 字段的 raw payload fail closed。

### Read / Tool Projection

- 删除 `_ProcessorFinancialStatementPayload` shadow TypedDict、statement locator fallback、optional field copy和 financial/XBRL cast bag。
- read runtime 先调用 domain validator，再逐字段复制 owner fields；financial public result required periods/scale/quality/reason。
- read normalizer 始终写 required `deduped_fact_count=len(public facts)`，保留 producer raw `total`，并逐字段复制 producer quality/reason。
- all-failed 映射为 `FinsReadBusinessError(code="xbrl_query_failed")`；direct callable 与 process-target representative path 都验证为 failed outcome，不是 successful empty value。
- 两个 financial tool description 已按 accepted template 自足说明字段、allowed values、scale-vs-units、raw-vs-dedup count、valid zero rows 与 partial reason；未修改 upload/download schema 或 security text。

## Tests And Validation

### Required Focused Tests

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
72 passed, 3 edgartools deprecation warnings
```

覆盖 characterization、financial required fields/quality matrix、Sec/BS valid-empty/partial/all-failed/unavailable、malformed execute return、local-filter empty、BS common/6-K scale probe、HTML/OCR scale/period/units、OCR income-summary fallback、read round-trip、raw/dedup count ownership和 typed failure mapping。

```text
pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
4 passed, 45 deselected, 3 edgartools deprecation warnings
```

覆盖真实 spawned-child financial statement/XBRL query、LLM-facing descriptions 和 process-target failed envelope。

额外回归：

```text
pytest tests/fins/test_fins_storage_provider.py -q
49 passed, 3 edgartools deprecation warnings
```

### Coverage

```text
coverage run -m pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py -q
58 passed, 3 edgartools deprecation warnings

coverage report --include="dayu/fins/domain/financial_result_contract.py,dayu/fins/domain/xbrl_result_contract.py" --fail-under=80
financial_result_contract.py: 84%
xbrl_result_contract.py: 85%
TOTAL: 85%
```

### Type Check And Whitespace

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
passed
```

## README Decision

- `dayu/fins/README.md`: 不在 S1 更新。已读取其 `Agent更新约束`；accepted plan 要求在 S3 aggregate docs step 统一记录最终 financial/XBRL、source revision 和 failure contract，避免中间 slice 写 future state。
- `tests/README.md`: 不更新。新增测试仍属于既有 `tests/fins` 层级，未改变测试运行方式或维护规则。
- 根 `README.md` / `dayu/README.md`: 不更新；无安装、CLI、workspace、最终用户工作流或分层关系变化。

## Propagation Scans

按 S1 plan 执行了全部六条 propagation scan，并分类如下：

1. `_ProcessorFinancialStatementPayload|data_quality: NotRequired|reason: NotRequired`：零匹配。
2. financial/XBRL type consumer：production consumers 直接 import domain owner；`financial_base.py` 仅为 protocol 内部注解直接 import，不在 `__all__` re-export。旧 `financial_base` result import/export 路径零匹配。`dayu/fins/README.md` 的旧概览命中按 S3 docs decision 保留，未作为 compatibility surface。
3. `query_obj.execute()` 后 catch-and-continue empty-success 形态：零匹配；现有 exception 分支均记录 `failed_concepts` 和 cause。
4. `_DECIMALS_SCALE_MAP`：零匹配。精确全范围 scan 的 `units.*millions/...` 命中包括一个现有 AAPL HTML fixture 长行；排除 fixture 后仅剩 domain scale enum、producer scale enum narrowing、validator negative fixture、两个 LLM description/test。没有 producer 把 scale 写入 units。
5. read/result/tool `periods|scale|data_quality|reason`：financial/XBRL public result 均 required；read runtime 逐字段复制；两个 tool description 自解释。其它 `cancel_reason` / document-filter reason 命中属于既有非 financial 语义，不是 shadow owner。
6. `deduped_fact_count` in domain/processors：无 producer type/producer result 命中；domain validator 有 2 个 deliberate negative-guard 命中，用于拒绝 raw producer payload 夹带 read-side 字段。这是当前 domain owner 的 fail-closed 校验，不是 read-side 字段反向传播；processors 零匹配。

未发现 Host/Engine、R3-E、tool-security、upload/download schema、6-K routing 或 full DocumentMeta scope 扩张。

## Residual Risks And Uncovered Areas

- `fixed in current slice`: edgartools 5.30.0 API 漂移风险由 implementation-start characterization 与 malformed-return/all-failed tests fail closed；未来依赖升级若无法区分空集与失败，测试会在 producer 修改前失败。
- `fixed in current slice`: 未识别的 HTML/OCR scale/fiscal layout 不会猜测为完整结果，而是稳定返回 typed partial degradation；已覆盖 caption/heading 命中、缺 scale、缺 fiscal、二者都缺和 OCR summary fallback。
- `covered by later approved slice`: source revision/cache freshness、decode/search failure和 section/table consistency仍属于 S2，本 slice 未触碰。
- `covered by later approved slice`: fiscal recency/parser、optional dataframe string、SEC version、ticker alias与 aggregate README属于 S3，本 slice 未触碰。
- `assigned to later work unit`: 6-K dual-engine routing与 full `DocumentMeta` migration按 accepted plan 保持后续 controller owner，本 slice 未引入兼容 shim 或局部补偿。

## Blocking Questions

无。

## Completion Status

`S1 IMPLEMENTATION COMPLETE`。当前只能交 controller 进入 S1 code review；不得由本 agent commit、push、review、进入 S2/S3 或下一 gate。
