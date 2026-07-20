# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review — AgentDS

## Review Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review (AgentDS)`
- Reviewer: `AgentDS`
- Timestamp: 2026-07-13
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-controller-validation.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`

## Scope / Validation Check

### Scope Confirmation

Diff 限定于 S1 allowed production files (15 files) 与 S1 allowed test files (4 files)。未修改 Host/Engine、R3-E、upload/download security schema、6-K routing 或 full `DocumentMeta` 迁移。无新增 compat re-export/wrapper/facade。

### Test And Pyright Baseline

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
→ 72 passed, 3 edgartools deprecation warnings

pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
→ 4 passed, 45 deselected, 3 edgartools deprecation warnings

python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations

coverage report --include="dayu/fins/domain/financial_result_contract.py,dayu/fins/domain/xbrl_result_contract.py" --fail-under=80
→ financial_result_contract.py: 84%, xbrl_result_contract.py: 85%, TOTAL: 85%
```

### Propagation Scan Results

所有 6 条 S1 propagation scan 均按预期：

1. `_ProcessorFinancialStatementPayload|data_quality: NotRequired|reason: NotRequired` → **零匹配**。
2. Financial/XBRL type consumer scan → 全部直接 import domain owner；旧 `financial_base` re-export 零匹配。
3. `query_obj.execute()` catch-and-continue empty-success 形态 → **零匹配**。
4. `_DECIMALS_SCALE_MAP` → **零匹配**。`units.*millions|...` 排除 fixture 后仅剩 domain enum、producer enum narrowing、validator negative fixture 和 LLM description/test text。
5. read/result/tool `periods|scale|data_quality|reason` → financial/XBRL public result 均 required。
6. `deduped_fact_count` in domain/processors → 仅 domain fail-closed guard 命中（拒绝 producer payload 夹带 read-side 字段）；processors **零匹配**。

---

## Findings

### Finding DS-01 (Medium): `_build_period_for_column` / `_build_single_scope_period` 可能在 fiscal_period 缺失时仍写入 fiscal_year

- **File:line**: `dayu/fins/processors/html_financial_statement_common.py:901-906`, `:926-929`
- **Direct evidence**:
  ```python
  fiscal_pair = _extract_fiscal_period_year(column_header_text)
  direct_date = _extract_first_date(column_header_text)
  fiscal_year = fiscal_pair[1] if fiscal_pair is not None else (
      direct_date.year if fiscal_period is not None and direct_date is not None else None
  )
  ```
  当 `_extract_fiscal_period_year` 返回 `("Q1", 2025)` 但 `_extract_fiscal_period_label` 和 `_extract_fiscal_period_from_direct_text` 均未识别任何 fiscal period 时，`fiscal_year=2025` 但 `fiscal_period=None`。
- **Failure mode**: 一个期间同时拥有 `fiscal_year` 和缺失 `fiscal_period`，虽然 `determine_financial_statement_quality` 会正确判定为 `period_semantics_unavailable`，但 `fiscal_year` 的来源不是 issuer fiscal calendar 的直接证据——它来自列头文本的年份 token，与 `fiscal_period` 的判断路径不同源。
- **Root cause**: `_extract_fiscal_period_year` 可能仅从 "Q1 2025" 等 token 中提取 year 部分，但 `_extract_fiscal_period_label` 可能因 pattern 不匹配而错过 "Q1"。此时 year 有值，period 无值。
- **Required fix**: 当 `fiscal_period is None` 时，`fiscal_year` 也必须为 `None`，不保留从 `_extract_fiscal_period_year` 或 `direct_date.year` 中提取的 year。改法：`fiscal_year = fiscal_pair[1] if fiscal_pair is not None and fiscal_period is not None else (...)`。
- **Test impact**: 当前 test `test_html_missing_fiscal_evidence_uses_quality_owner` 已验证 `fiscal_year is None` 的路径（`fiscal_semantics=False` 时列头不含 `FY2025` token）；需要新增一个 fixture：列头含 `Q1 2025` 或 `1Q25` 但 scope text 不含任何 `_extract_fiscal_period_label` 可识别 token，验证 `fiscal_year` 同为 `None`。

### Finding DS-02 (Low): `_extract_fiscal_period_from_direct_text` 接收但不使用 `period_end` 参数

- **File:line**: `dayu/fins/processors/html_financial_statement_common.py:1573-1599`
- **Direct evidence**: 函数签名包含 `period_end: str`，函数体内 `del period_end` 显式丢弃。
- **Failure mode**: 无运行时失败；仅签名误导调用者以为 `period_end` 参与推断。
- **Required fix**: 移除 `period_end` 参数，更新两个 call site (`_build_period_for_column` line 731, `_build_single_scope_period` line 776) 移除 `period_end=period_end` 实参。函数重命名为仅反映其实际行为：从直接文本提取 FY（不涉及 date-based inference）。
- **Test impact**: 现有 test 不会受影响；只需确认 call site signature 更新后仍通过。

### Finding DS-03 (Low): OCR income summary fallback 将 `units` 和 `currency` 设为同一值

- **File:line**: `dayu/fins/processors/six_k_form_common.py:1145-1146`
- **Direct evidence**:
  ```python
  "currency": currency,
  "units": currency,
  ```
- **Failure mode**: 对 income statement (P&L)，计量单位就是报告货币，目前语义正确。若未来此 pattern 被复制到 balance sheet 或其他 non-currency measurement 提取，可能出现 `units="USD"` 但实际应该是 `"shares"` 等情景。
- **Required fix**: 当前无需修改；在 `_build_income_summary_result_from_title_match` 的 docstring 中注明 `units` 与 `currency` 对 income summary 同源，其他 statement type 不能复用此假设。
- **Test impact**: 当前 test `test_ocr_income_summary_fallback_consumes_heading_scale_owner` 已验证 `units == "USD"` 且 `currency == "USD"`。无需新增测试。

### Finding DS-04 (Observation): `_sum_absolute_numeric_row_values` 新增 `bool` guard 改变 OCR 候选排序行为

- **File:line**: `dayu/fins/processors/six_k_form_common.py:1048-1068`
- **Direct evidence**: 新增 `not isinstance(value, bool)` guard，原 inline comprehension 无此 guard。`bool` 是 `int` 子类，旧代码会把 `True/False` 当数值计入候选得分。
- **Failure mode**: 行为变化是正向修复（旧代码有 bug），但不在 accepted plan 的 explicit scope 内。若 OCR candidate 原先依赖此行为排序，排序可能变化。
- **Required fix**: 无需修改。此为 latent bug fix，且 S1 OCR test 已验证新行为正确。
- **Test impact**: 当前 test 间接覆盖（OCR income summary 和 OCR statement 路径均通过）。

---

## Adversarial Verification Results

### 1. edgartools execute 边界 (Pass)

| 场景 | 测试覆盖 | 结果 |
|------|----------|------|
| `execute()` 返回 `[]` | `test_edgartools_execute_treats_empty_list_as_successful_zero_rows` | ✅ 合法空集 = successful |
| `execute()` 抛 sentinel 异常 | `test_edgartools_execute_propagates_facts_view_exception` | ✅ 异常传播可区分 |
| 非 list 返回 (str) | `test_xbrl_execution_summary_treats_malformed_return_as_failure["malformed"]` | ✅ 计 failed |
| 含非 mapping row 返回 | `test_xbrl_execution_summary_treats_malformed_return_as_failure[["malformed"]]` | ✅ 计 failed |
| 本地 filter 清空 rows | `test_xbrl_execution_summary_local_filter_zero_is_successful` | ✅ successful zero rows |
| 部分 concept 失败 | `test_xbrl_execution_summary_distinguishes_empty_success_and_failure` | ✅ failed/successful 分别计数 |
| 全部 concept 失败 | `test_xbrl_execution_summary_all_failed_raises_with_cause` | ✅ `XbrlQueryExecutionError` + `__cause__` |
| concepts 规范化为空 | S1 code: `if not attempted_concepts: raise ValueError` | ✅ `ValueError` (input contract fail) |

### 2. XBRL scale probe failure (Pass)

- `_infer_scale_from_xbrl_query` 返回 `FinancialScaleOutcome(scale=None, query_failed=True)` 当全部 candidate 失败时。
- `test_bs_scale_probe_failure_keeps_rows_and_degrades_quality` 验证：即使全部 probe candidate 抛 sentinel 异常，statement rows 仍保留，质量降级为 `partial` + `scale_and_period_semantics_unavailable`。
- Caller (`_get_statement_from_xbrl` in BS common / sec_processor) 在 `query_failed=True` 时设 `scale=None`，不保留错误 scale。

### 3. HTML/OCR missing scale, missing fiscal semantics (Pass)

- HTML caption scale: `_infer_scale_from_caption` 拥有唯一 scale 提取逻辑。`test_html_caption_owns_scale_and_units_remain_measurement_only` 验证 `in millions` → `scale="millions"`, `units="USD"`（不含 scale）。
- HTML missing fiscal: `test_html_missing_fiscal_evidence_uses_quality_owner` 验证无 FY/Q1 token 时 `fiscal_year=None, fiscal_period=None`，质量正确降级。
- OCR heading scale: `_extract_ocr_currency_and_scale` 拥有唯一 scale 提取。`test_ocr_heading_owns_scale_and_units_remain_measurement_only` 验证分离。
- OCR missing fiscal: `test_ocr_missing_fiscal_evidence_uses_quality_owner` 验证无 "year ended" 时不补 FY。
- OCR income-summary fallback: `test_ocr_income_summary_fallback_consumes_heading_scale_owner` 验证复用同一 heading scale owner。
- `_build_units_label` 和 `_build_ocr_units_label` 已删除；`units` 不再承载 scale。

### 4. All-failed → failed outcome (Pass)

- Direct callable path: `test_query_xbrl_facts_maps_all_failed_to_typed_business_failure` 验证 `FinsReadBusinessError(code="xbrl_query_failed")` + correct cause chaining + "零命中" message。
- Process-backed target path: `test_financial_tool_process_target_preserves_xbrl_failed_outcome` 验证 `envelope["status"] == "failed"`, `envelope["error_type"] == "xbrl_query_failed"`, `"value" not in envelope`。

### 5. Validator fail-closed (Pass)

- Required fields: `test_financial_validator_rejects_missing_required_fields` 逐字段验证 `periods/scale/data_quality/reason/statement_locator` 缺失均 fail。
- Empty rows: `test_financial_validator_rejects_invalid_quality_and_scale_contracts` 包含 `rows=[]` 不可声明完整质量。
- Quality/reason matrix: `test_financial_quality_reason_matrix_uses_direct_evidence` 参数化覆盖三种 partial reason。
- ISO date: `_required_periods` 校验 `YYYY-MM-DD` pattern + `date.fromisoformat`。
- Scale enum: `_required_financial_scale` 拒绝非 `units/thousands/millions/billions/None` 值。
- Raw dedup field: `test_xbrl_query_payload_rejects_producer_dedup_count` 验证 producer payload 夹带 `deduped_fact_count` 被拒。
- Units/scale split: validator 拒绝 `units="USD in millions"` 等含 scale 文本。

### 6. Propagation scans (Pass)

全部 6 条 S1 scan 结果与 expected scan decision 一致；无 unexpected match 需要分类。

---

## Non-Blocking Residuals

1. **`_extract_fiscal_period_year` 与 `_extract_fiscal_period_label` 的 pattern 覆盖不重叠**：前者可能识别 "Q1 2025"，后者可能不识别。当前由 `determine_financial_statement_quality` 在 period 级别检测 `fiscal_period=None` 并降级，不会产生错误完整结果。详见 DS-01。

2. **HTML `_build_single_scope_period` 与 `_build_period_for_column` 有重复的 fiscal evidence 组装逻辑**：两段代码几乎相同（fiscal_period → fiscal_pair → direct_date → fiscal_year），但 S1 未要求提取公共 helper。S3 的 `value_normalization` 不涵盖此 case。建议后续 WU 处理。

3. **`FinancialStatementResult` domain type 与 `result_types.py` 的 public projection type 同名但不同语义**：
   - Domain: `dayu.fins.domain.financial_result_contract.FinancialStatementResult`（producer-owned，不含 ticker/document/citation）
   - Public: `dayu.fins.tools.result_types.FinancialStatementResult`（read projection，含 ticker/document/citation + 全部 domain fields）
   - Read runtime import 使用别名 `ProcessorFinancialStatementResult` 区分。不会造成运行时混淆，但代码阅读时需注意 import 来源。非 S1 scope。

4. **OCR `_extract_ocr_fiscal_period_from_heading` 只能返回 `"FY"` 或 `None`**：Q1/Q2/H1/H2/Q3/Q4 的提取由调用路径的 explicit_fiscal_period token 覆盖，heading 只承担默认值。当前 6-K 测试 fixture 均通过 heading 无法提供非 FY 默认值的路径。S1 已满足 plan 要求的 "不根据月份/日期猜测 issuer fiscal calendar"。

5. **S2 依赖**：source revision/cache freshness、decode/search failure、section/table consistency 仍为 S2 scope，本 slice 未触碰。`ErrorCode.XBRL_QUERY_FAILED` 已新增，供 S2 复用。

---

## Final Decision

**PASS**

所有 7 项重点 adversarial check 均通过。76 个 focused/semantic-ownership/storage-provider 测试全部通过。pyright 零错误。6 条 propagation scan 均返回预期结果。2 个 medium findings (DS-01, DS-02) 建议 fix 但不 block S1 acceptance——DS-01 的 `fiscal_year` 不一致已被 `determine_financial_statement_quality` 的 `period_semantics_missing` 检测降级，不会产生错误完整结果；DS-02 仅为签名清洁度问题。

**Finding count**: 2 medium, 2 low, 4 observation/residual
