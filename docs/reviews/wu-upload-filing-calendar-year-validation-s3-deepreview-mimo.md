# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `67c34c0f`
- Output file: `docs/reviews/wu-upload-filing-calendar-year-validation-s3-deepreview-mimo.md`
- Included scope:
  - `dayu/fins/download_contract.py` — download wrapper 消费 shared domain owner
  - `tests/cli/test_fins_commands.py` — delegation spy、boundary、ordering 回归
  - `README.md` — 最终用户 download/upload contract
  - `dayu/fins/README.md` — domain owner 开发者 contract
  - `dayu/fins/domain/filing_semantics.py` — shared owner（已 accepted，只读核对）
- Excluded scope: S1/S2 生产文件、frozen oracle/scenario/evidence、UF-PF04
- Parallel review coverage: 无

## Findings

### 001-未修复-低-下载 wrapper 正则 `\d` 匹配 Unicode 数字

- **入口/函数**: `dayu/fins/download_contract.py::_parse_date_bound`
- **文件(行号)**: `download_contract.py:46-48`
- **输入场景**: 用户传入全角数字 `"０００１"` 或其它 Unicode 数字字符作为日期边界
- **实际分支**: `_YEAR_PATTERN` / `_YEAR_MONTH_PATTERN` / `_FULL_DATE_PATTERN` 的 `\d` 匹配 Unicode 数字（Python `re` 默认 Unicode-aware），进入 `int()` 转换分支
- **预期行为**: download wrapper 的日期 shape regex 应只匹配 ASCII 数字 `[0-9]`，与 domain owner 的 `_STRICT_ISO_CALENDAR_DATE_PATTERN`（使用 `re.ASCII` + `[0-9]`）保持一致
- **实际行为**: year-only/year-month 路径因 `parse_calendar_year` 的 `1000..9999` 范围检查而被拒绝（正确但路径偶然）；full-date 路径经 `int()` 补零后产生合法 ASCII canonical 文本，被 `parse_iso_calendar_date` 接受（静默接受 Unicode 输入）
- **直接证据**: `download_contract.py:46` `_YEAR_PATTERN = re.compile(r"^\d{4}$")`；`filing_semantics.py:55-58` `_STRICT_ISO_CALENDAR_DATE_PATTERN` 使用 `[0-9]` + `re.ASCII`；`int("０００１")` = 1（Python `int()` 接受全角/阿拉伯-印度数字）
- **影响**: Unicode 数字输入在 full-date 路径被静默接受并规范化为正确 ASCII 日期，行为正确但绕过了 ASCII-only 的隐式合同。year-only/year-month 路径因范围检查被拒绝，行为正确但拒绝原因是范围而非格式。CLI 环境中 Unicode 数字实际出现概率极低。
- **建议改法和验证点**: 将三个正则的 `\d` 改为 `[0-9]` 并添加 `re.ASCII` 标志；或保持现状并在 docstring 中说明 `\d` 匹配范围。此为 S3 范围外的 pre-existing 问题，不影响 S3 的 owner delegation 正确性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。所有 S3 指定的验证点均已在代码路径中直接确认。

## Residual Risk

1. **UF-PF04 真实 CLI evidence**: `assigned to later work unit`，owner=`UF-PF04`；按用户明确要求未执行。
2. **其它 upload findings**: `assigned to later work unit`，owner=`UF-FIX01/02/03/05...`；S3 未处理。
3. **`upload_filings_from` raw-date parity**: `assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`；README 已限定 direct contract scope。
4. **tool 完整文件预存 failure**: `assigned to later work unit`，owner=`UF-FIX01 follow-up`；S3 未修改 tool 文件。
5. **Unicode digit regex width**: pre-existing，S3 未引入也未修复；见 finding 001。

没有 `unclassified residual risk`。

## Verification Checklist

以下逐项核对 S3 implementation artifact 与 accepted plan 的每个指定验证点：

### download partial year/year-month 只消费 parse_calendar_year

- **代码证据**: `download_contract.py:800` `year = parse_calendar_year(int(value), field_name=field_name)`（year-only）；`download_contract.py:804` `year = parse_calendar_year(int(year_text), field_name=field_name)`（year-month）
- **结论**: ✅ 两条路径都只调用 `parse_calendar_year`，不调用 `parse_iso_calendar_date`

### full-date canonicalize 后只消费 parse_iso_calendar_date 且保持 0001..9999

- **代码证据**: `download_contract.py:810-813` 构造 `f"{int(year_text):04d}-{int(month_text):02d}-{int(day_text):02d}"` 后调用 `parse_iso_calendar_date(canonical_value, field_name=field_name)`；`filing_semantics.py:388-396` 使用 `datetime.date` 构造并要求 `isoformat()` round-trip，公历年份域为 `datetime.date` 标准库的 `0001..9999`
- **结论**: ✅ full-date 不调用 `parse_calendar_year`，不继承 `1000` 下界，`0001-01-01` 和 `0999-12-31` 均合法

### wrapper 继续拥有 strip、shape、1-2 位月日、真实月末/inclusive expansion、ordering

- **代码证据**: `download_contract.py:793` `value = raw_value.strip()`；`download_contract.py:46-48` regex 允许 `\d{1,2}`；`download_contract.py:806` `calendar.monthrange(year, month)[1]`；`download_contract.py:801` `dt.date(year, 12, 31) if is_end else dt.date(year, 1, 1)`；`download_contract.py:588` `start_bound > end_bound` 检查
- **结论**: ✅ wrapper-owned 行为全部保留

### _parse_optional_iso_date 是否保持 public contract

- **代码证据**: `download_contract.py:841-861` 保留 `_validate_public_text` 前置检查、`None` gate 和 `ValueError` wrapper；`parse_iso_calendar_date` 的 `ValueError` 被包装为 `"{field_name} must be an ISO date"`
- **行为变化**: 旧代码区分 `"must be an ISO date"` 和 `"must use canonical ISO format"` 两个错误消息，新代码统一为 `"must be an ISO date"`。这是错误消息合并，不改变 ValueError 类型。
- **结论**: ✅ public contract（类型、None 处理、text validation）保持；错误消息从两种合并为一种，不影响现有测试断言

### Unicode digit（见 finding 001）

- **代码证据**: `download_contract.py:46-48` 使用 `\d`（Unicode-aware）；`filing_semantics.py:55-58` 使用 `[0-9]` + `re.ASCII`
- **结论**: ⚠️ pre-existing regex width，S3 未引入也未修复

### year 0000/0999/10000

- **测试证据**: `test_download_partial_year_rejects_values_outside_shared_year_domain` 覆盖 `0999`、`0000`、`0999-12`、`0000-1`
- **代码路径**: `parse_calendar_year(999)` 和 `parse_calendar_year(0)` 均抛 ValueError → `FinsDownloadUsageError`
- **结论**: ✅ 正确拒绝

### 闰年

- **测试证据**: `test_download_date_bounds_preserve_shape_canonicalization_and_inclusive_expansion` 覆盖 `("2024-2", "2024-2", "2024-02-01", "2024-02-29")`
- **代码路径**: `calendar.monthrange(2024, 2)[1]` = 29
- **结论**: ✅ 闰年二月正确展开为 29 日

### 非法月日

- **测试证据**: `test_download_full_date_rejects_nonexistent_calendar_dates` 覆盖 `2023-2-29`、`2024-13-1`、`2024-4-31`
- **代码路径**: `parse_iso_calendar_date` → `datetime.date(2023, 2, 29)` 等抛 ValueError
- **结论**: ✅ 正确拒绝

### 外围空白

- **测试证据**: `test_download_date_bounds_preserve_shape_canonicalization_and_inclusive_expansion` 覆盖 `(" 2024-2-9 ", " 2024-2-9 ", "2024-02-09", "2024-02-09")`
- **代码路径**: `raw_value.strip()` → regex 匹配 → `int()` 转换 → canonical 补零
- **结论**: ✅ 外围空白被 strip 后正确规范化

### start/end 竞争

- **测试证据**: `test_download_date_range_ordering_remains_owned_by_range_contract` 覆盖 `start="2025", end="2024-12"`
- **代码路径**: `_parse_date_bound` 分别处理 start/end → `FinsDownloadDateRange.__post_init__` 检查 `start_bound > end_bound`
- **结论**: ✅ ordering 由 `FinsDownloadDateRange` 唯一拥有，不与 domain owner 竞争

### README 是否准确且未外推 upload_filings_from

- **根 README 证据**: 明确说明 "该严格原始输入承诺只适用于这两个直接 filing 入口，不覆盖 `upload_filings_from` 的扫描与脚本生成元数据处理"
- **Fins README 证据**: 明确说明 "`upload_filings_from` 的扫描与脚本生成元数据处理不属于这两个直接入口的 strict raw-admission contract"
- **结论**: ✅ README 准确限定 scope，未外推

### 测试 delegation spy 是否真实

- **代码证据**: `test_download_date_bound_delegates_shared_year_and_full_date_owners` 使用 `monkeypatch.setattr` 替换为 recording wrapper，wrapper 调用真实 `parse_calendar_year` / `parse_iso_calendar_date` 并记录调用
- **断言**: `year_calls == [(1000, "--start"), (2024, "--end")]` 和 `date_calls == [("0001-01-01", "--start"), ("0999-12-31", "--end")]` 证明 partial year 走 year owner、full-date 走 date owner
- **结论**: ✅ spy 使用真实实现（非 fake），调用记录真实

### coverage 集合修正是否避免 scope drift

- **证据**: S3 implementation artifact 记录 CLI-only 集合为 63%（不足 80%），controller 裁决撤销非目标 tests，改用真实可达集合（5 个测试文件）达到 88%
- **scope 检查**: 没有为凑 coverage 新增非 calendar/year tests
- **结论**: ✅ coverage 集合修正由控制侧裁决驱动，避免 goal drift

### 核对 frozen/UF-PF04

- **证据**: `git diff --name-only 67c34c0f` 精确为四个 allowed tracked files；`git diff --cached --name-status` 无输出；`docs/cli_ci_oracles.json` 和 `docs/cli_ci_scenarios.json` 未修改
- **结论**: ✅ frozen registry 未改，UF-PF04 未执行

## Conclusion

**Pass**（含一个低严重度 pre-existing finding）。

S3 实现正确完成 accepted plan 指定的 download wrapper owner delegation：partial year/year-month 只消费 `parse_calendar_year`（`1000..9999`），full-date canonicalize 后只消费 `parse_iso_calendar_date`（`0001..9999`），wrapper-owned strip/shape/expansion/ordering 全部保留。delegation spy 使用真实实现，测试覆盖 boundary/rejection/ordering/canonicalization。README 准确限定 scope，未外推 `upload_filings_from`。coverage 集合修正由控制侧裁决驱动，避免 scope drift。frozen registry 未改。

唯一 finding（001）是 download wrapper 正则 `\d` 匹配 Unicode 数字的 pre-existing 问题，不影响 S3 的 owner delegation 正确性，建议后续统一修复。
