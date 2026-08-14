# UF-FIX04 聚合 deepreview

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `f609a4d8`（accepted plan checkpoint）
- HEAD: `0dfc9f34`
- Output file: `docs/reviews/wu-upload-filing-calendar-year-validation-aggregate-deepreview-mimo.md`
- Included scope: S1-S3 三个 implementation slice 的全部 production/test/README diff（35 files, +3656 / -57）
- Parallel review coverage: 无

## Gateflow artifacts reviewed

- `wu-upload-filing-calendar-year-validation-plan-codex.md`（accepted plan）
- `wu-upload-filing-calendar-year-validation-s1-implementation-codex.md`
- `wu-upload-filing-calendar-year-validation-s1-review-controller-adjudication.md`
- `wu-upload-filing-calendar-year-validation-s1-rereview-controller-adjudication.md`
- `wu-upload-filing-calendar-year-validation-s2-implementation-codex.md`
- `wu-upload-filing-calendar-year-validation-s2-review-controller-adjudication.md`
- `wu-upload-filing-calendar-year-validation-s2-rereview-controller-adjudication.md`
- `wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`
- `wu-upload-filing-calendar-year-validation-s3-review-controller-adjudication.md`
- `wu-upload-filing-calendar-year-validation-s3-rereview-controller-adjudication.md`
- 各 slice 的 dual deepreview 和 re-review artifacts（MiMo / DS）

## 用户六项要求端到端检查

### 1. 唯一 calendar/year owner

**Pass。** `dayu/fins.domain.filing_semantics` 唯一拥有：

- `parse_calendar_year(value: int) -> int`：拒绝 bool、非 int、`<1000`、`>9999`
- `parse_iso_calendar_date(value: str) -> datetime.date`：strict ASCII `YYYY-MM-DD`、`datetime.date` 构造验证真实公历、`isoformat()` round-trip、公历域 `0001..9999`
- `normalize_fiscal_year` 委托同一 owner 的 `parse_calendar_year`
- 模块级私有常量 `_MIN_CALENDAR_YEAR`、`_MAX_CALENDAR_YEAR`、`_CALENDAR_YEAR_RANGE_TEXT`、`_STRICT_ISO_CALENDAR_DATE_PATTERN` 由 bounds 派生

直接证据：`filing_semantics.py:344-397`，`filing_semantics.py:400-422`。

upload/download/CLI/tool 均通过 import 共享同一 owner，无各自维护的 year/calendar 规则。

### 2. strict actual ISO date 与 1000..9999 non-bool year

**Pass。**

- `parse_calendar_year`：`isinstance(value, bool)` 前置拒绝、`int` 类型守卫、`_MIN_CALENDAR_YEAR.._MAX_CALENDAR_YEAR` 闭区间
- `parse_iso_calendar_date`：`re.fullmatch` 精确 ASCII digit `YYYY-MM-DD`、`datetime.date(year, month, day)` 构造真实日期、`parsed.isoformat() != value` round-trip 检查
- `normalize_fiscal_year`：先拒绝 bool/非 int，再委托 `parse_calendar_year`

直接证据：`filing_semantics.py:358-364`（year bounds），`filing_semantics.py:384-397`（date round-trip）。

### 3. upload_filing CLI/tool/runtime 在 operation/converter/storage mutation 前 usage 拒绝且零副作用

**Pass。**

- `_validate_fins_upload_filing_static`（ingestion_runtime.py:895-912）：year/date 校验位于 file existence probes（line 916-926）之前
- `_prevalidate_upload_filing_request`（fins.py:693-694）：CLI 传递 raw date 原值，不 strip
- `_optional_raw_nullable_text`（upload_tools.py:337-360）：tool adapter 保留 raw text，不 strip/折叠

零副作用证据（测试断言）：
- `test_filing_calendar_year_static_admission_precedes_all_side_effects`：`state_repository.calls == []`、`executor.operations == []`、`runner.requests == []`、workspace snapshot 不变
- `test_upload_tool_filing_calendar_year_invalid_input_has_zero_side_effects`：`state_repository.calls == []`、`executor.submitted_job_ids == ()`、`runtime._observations == {}`、job store 空
- `test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation`：CLI exit 2、service factory/workspace 零调用

### 4. 非法 year 不进入 meta/manifest/durable

**Pass。** 与 #3 同一链路：`_validate_fins_upload_filing_static` 在 `_filing_upload_request_identity` 之后、`read_filing_upload_state` 之前拒绝。非法 year/date 不可能到达 state read、operation 创建或 storage mutation。

read-runtime 层面：`test_parse_source_document_meta_fails_closed_for_invalid_historical_fiscal_year` 断言 `999/10000/True/False/"2025"` 在 `_parse_source_document_meta` 中抛出 `ValueError`，不会被忽略或默认化。

### 5. download 只共享 full-date/year legality 并保留 partial shape/inclusive expansion/order

**Pass。**

- `_parse_date_bound`（download_contract.py:799-813）：
  - year-only：`parse_calendar_year(int(value))` → `dt.date(year, 1, 1)` / `dt.date(year, 12, 31)`
  - year-month：`parse_calendar_year(int(year_text))` → download wrapper 自己拥有 month 合法性与 `calendar.monthrange` 月末展开
  - full-date：wrapper 补零 `f"{int(year_text):04d}-{int(month_text):02d}-{int(day_text):02d}"` → `parse_iso_calendar_date(canonical_value)`，不调用 `parse_calendar_year`，因此 `0001..0999` full-date 合法
- `_parse_optional_iso_date`（download_contract.py:858-861）：委托 `parse_iso_calendar_date`
- `_FULL_DATE_PATTERN` 继续允许 1~2 位 month/day
- `FinsDownloadDateRange` 继续唯一拥有 `start_bound <= end_bound` ordering
- `_parse_date_bound` 先 `strip()` 后处理，外围空白仍按既有 contract 接受

直接证据：download_contract.py:799-816。

### 6. 合法 download 行为无回归

**Pass。**

- `test_download_date_bounds_preserve_shape_canonicalization_and_inclusive_expansion`：覆盖 `2024`、`2024-2`、`2024-2-9`、`2024-02-09`、` 2024-02-09 ` 等 shape
- `test_download_partial_year_rejects_values_outside_shared_year_domain`：`0999/0000/0999-12/0000-1` 正确拒绝
- `test_download_full_date_rejects_nonexistent_calendar_dates`：`0000-12-31/2023-2-29/2024-13-1/2024-4-31` 正确拒绝
- `test_download_date_bound_delegates_shared_year_and_full_date_owners`：spy 证明 year/full-date owner 被调用
- `test_download_public_iso_dates_delegate_shared_full_date_owner`：public DTO 校验委托 owner
- `test_download_date_range_ordering_remains_owned_by_range_contract`：start > end 拒绝

CLI 完整文件测试：`124 passed`。

## 附加审查项

### read durable invalid year fail closed

**Pass。** `test_parse_source_document_meta_fails_closed_for_invalid_historical_fiscal_year` 覆盖 `999`、`10000`、`True`、`False`、`"2025"`，均抛出 `ValueError`，不被忽略或默认化。

### 无 adapter/storage/test fallback

**Pass。** 生产代码中无 `hasattr`/`getattr` 补救、无默认值兼容、无 loose parsing。`normalize_fiscal_year` 先显式拒绝 bool/非 int 再委托 owner；`_validate_optional_upload_iso_date` 只做 `None` gate 和 owner 调用。

### frozen registry/evidence 未改

**Pass。** `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 在 diff 中无改动。

### UF-PF04 未执行

**Pass。** 所有 implementation/review artifacts 均记录 UF-PF04 未运行，分类为 later work unit。

### 其它 findings 未扩张

**Pass。** UF-FIX01/02/03/05 等其它 upload findings 未被修改或扩展。tool 完整文件唯一预存失败 `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 精确保持为 UF-FIX01 baseline（`82 passed, 1 failed`）。

## 跨 slice integration 检查

- S1 owner APIs 被 S2 upload admission 和 S3 download wrapper 同一 import 路径消费，无重复实现
- `_validate_fins_upload_filing_static` 中 year/date 校验顺序（year → period → date → file）由测试 `test_validate_fins_upload_filing_request_preserves_validation_priority` 锁定，含 filing date 和 report date 对称 case
- download full-date `0001..0999` 合法但 year-only `0999` 非法的域差异由 `parse_iso_calendar_date`（full-date owner）和 `parse_calendar_year`（year owner）分别拥有，测试分别覆盖
- CLI `_prevalidate_upload_filing_request` 传递 raw date → `FinsUploadFilingRequest` → `_validate_fins_upload_filing_static` → shared owner，与 tool `_optional_raw_nullable_text` → `FinsUploadFilingRequest` → same static validator 路径同源

## 错误消息检查

- 三个 year/date usage code 使用唯一业务中立 message，不含 `--flag` 语法
- CLI usage exit 2 与 tool `ToolFailedOutcome(error="invalid_message")` 对同一 code 使用同一 message
- download `FinsDownloadUsageError` 保持原有用户可见 wording 分类

## 类型检查

- pyright: `0 errors, 0 warnings, 0 informations`（5 个修改生产文件）
- 所有新增函数有完整类型签名
- `parse_calendar_year` 的 `isinstance(value, bool)` 前置检查正确处理 Python `bool` 是 `int` 子类的问题

## 覆盖率

| 生产文件 | 测试集合 | Statements | Miss | Coverage |
| --- | --- | --- | --- | --- |
| `filing_semantics.py` | S1 owner + read-runtime + download pipeline | 141 | 18 | 87% |
| `ingestion_runtime.py` | S2 runtime 完整文件 | 2188 | 202 | 91% |
| `download_contract.py` | 5-file 联合集合 | 330 | 38 | 88% |
| `fins.py` (CLI) | CLI 完整文件 | — | — | 86%（S2 artifact 证据） |
| `upload_tools.py` | tool 完整文件（deselect UF-FIX01 baseline） | — | — | >=80%（S2 artifact 证据） |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `UF-PF04` 真实 CLI evidence 未执行：`assigned to later work unit`，owner=`UF-PF04`。
- 其它 upload findings（UF-FIX01/02/03/05）：`assigned to later work unit`，owner=各自 work unit。
- `upload_filings_from` raw-date parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
- download regex Unicode digit 接受集：`pre-existing baseline`，S3 未修改 regex，分类为独立后续 `download date ASCII-shape admission` work unit。
- tool 完整文件预存 UF-FIX01 baseline failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`。

没有 `unclassified residual risk`。

## Verification commands executed

```bash
# S1 owner tests
pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
# 98 passed

# S2 runtime tests
pytest tests/fins/test_fins_ingestion_runtime.py -q
# 258 passed

# S3 CLI tests
pytest tests/cli/test_fins_commands.py -q
# 124 passed

# Tool tests (UF-FIX01 baseline)
pytest tests/fins/test_fins_ingestion_tools.py -q
# 82 passed, 1 failed (pre-existing baseline)

# S1 owner coverage
coverage erase && coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_sec_pipeline_download.py -q
coverage report --include='dayu/fins/domain/filing_semantics.py' --fail-under=80
# 87%

# S2 runtime coverage
coverage erase && coverage run -m pytest tests/fins/test_fins_ingestion_runtime.py -q
coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
# 91%

# download_contract.py coverage (5-file set per S3 amendment)
coverage erase && coverage run -m pytest tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_output.py -q
coverage report --include='dayu/fins/download_contract.py' --fail-under=80
# 88%

# Full pyright
python -m pyright dayu/fins/domain/filing_semantics.py dayu/fins/ingestion_runtime.py dayu/fins/download_contract.py dayu/cli/commands/fins.py dayu/fins/tools/upload_tools.py
# 0 errors, 0 warnings, 0 informations

# git diff check
git diff --check f609a4d8..0dfc9f34
# clean
```

## Conclusion

**Pass。** UF-FIX04 三个 implementation slice 的聚合 diff 满足用户六项端到端要求：唯一 calendar/year owner 位于 `dayu.fins.domain.filing_semantics`；strict actual ISO date 与 `1000..9999` non-bool year 由同一 owner 拥有；upload filing 在所有 state/operation/converter/storage mutation 前拒绝且零副作用；非法 year/date 不进入 durable state；download 只共享合法性并保留 partial shape/inclusive expansion/order；合法 download 行为无回归。read durable invalid year fail closed、无 adapter/storage/test fallback、frozen registry/evidence 未改、UF-PF04 未执行、其它 findings 未扩张均通过。跨 slice integration、错误消息、类型、docstring、README 与测试真实性审查未发现实质性问题。
