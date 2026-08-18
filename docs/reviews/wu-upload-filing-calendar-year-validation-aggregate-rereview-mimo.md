# UF-FIX04 aggregate re-review（AgentMiMo）

- 审查类型：aggregate re-review（验证 AgentCodex aggregate fix artifact 对 F1/F2 的修复）
- 审查时间：2026-08-14T16:26:58+0800
- Work unit：`UF-FIX04 shared-calendar-year-validation`
- Branch：`codex/upload-filing-oracle`
- Base：`0dfc9f34`（S3 accepted 提交）
- 审查输入：DS aggregate deepreview、MiMo aggregate deepreview、controller adjudication、AgentCodex aggregate fix artifact、当前未提交 diff（`tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py`）
- 审查动作：只读。未修改代码或测试，未 stage、未 commit。

## Scope

- Mode: current changes（aggregate fix artifact 验证）
- Branch: `codex/upload-filing-oracle`
- Base: `0dfc9f34`
- Included scope：两个测试文件的未提交 diff、四个 review artifacts
- Excluded scope：production 代码、README、frozen registry/evidence（仅核对未改）

## 验证结论

**Pass。** F1/F2 修复均正确达成 controller adjudication 要求，scope 完整性通过。

---

## F1 验证：`20240229` baseline 可解析 / strict owner 拒绝 / exact 统一 message

### 验证项

| 条件 | 证据 | 结果 |
| --- | --- | --- |
| `20240229` 在 Python 3.11 baseline 可被 `date.fromisoformat` 解析 | Python 3.11 接受 basic format `YYYYMMDD`，`2024-02-29` 为合法闰日 | ✅ |
| strict owner 拒绝 | `_STRICT_ISO_CALENDAR_DATE_PATTERN` 为 `^\d{4}-\d{2}-\d{2}$`，`20240229` 不匹配；`download_contract.py:856-861` 委托 `parse_iso_calendar_date` 后抛 `ValueError` | ✅ |
| exact 统一 message | `test_fins_commands.py:1273-1281` 断言 `str(exc.value) == "start_date must be an ISO date"` | ✅ |

### 代码走读

`tests/cli/test_fins_commands.py:1273-1281`：

```python
with pytest.raises(ValueError) as basic_format_exc:
    FinsDownloadEffectiveFilters(
        form_types=(),
        start_date="20240229",
        end_date=None,
        overwrite_existing=False,
        rebuild_local_artifacts=False,
    )
assert str(basic_format_exc.value) == "start_date must be an ISO date"
```

该测试精确覆盖 controller adjudication 指定的真实 wording 漂移类别：baseline `fromisoformat` 可解析的 basic format，strict owner 拒绝后统一投影为 `"{field_name} must be an ISO date"`。message 文本与 `download_contract.py:859` 生产代码一致。

### scope 检查

- 仅新增该断言块，未修改同函数内其它断言
- production `download_contract.py` 未改
- `_parse_optional_iso_date` 的 unified wording 已在 aggregate deepreview 中确认为委托 shared owner 的预期 contract 变更

---

## F2 验证：delegation test 用两个不同日期 / 证明正确值委托 / 不锁定次数 / 保留 identity/action/request

### 验证项

| 条件 | 证据 | 结果 |
| --- | --- | --- |
| 两个不同日期 | `filing_date="2024-02-29"`、`report_date="2024-03-01"`（`test_fins_ingestion_runtime.py:1753-1754`） | ✅ |
| 证明正确值委托 | `set(year_calls) == {fiscal_year}`（1771）；`set(date_calls) == {"2024-02-29", "2024-03-01"}`（1773）——两值均至少出现一次 | ✅ |
| 不锁定次数 | `year_calls`/`date_calls` 仅断言非空 + 值集合，无 `len`/`== [x]*n`/`== [x] * 8` 约束 | ✅ |
| 保留 identity | `first.document_id == second.document_id`（1766）、`first.internal_document_id == second.internal_document_id`（1767） | ✅ |
| 保留 action | `first.resolved_action == "delete"`（1768） | ✅ |
| 保留 request identity | `first.request is request`（1769） | ✅ |

### 代码走读

`tests/fins/test_fins_ingestion_runtime.py:1770-1773`（新断言）：

```python
assert year_calls
assert set(year_calls) == {fiscal_year}
assert date_calls
assert set(date_calls) == {"2024-02-29", "2024-03-01"}
```

对照 baseline 旧断言（`year_calls == [fiscal_year] * 4`、`date_calls == ["2024-02-29"] * 8`），新断言只锁定值内容与"每个字段至少委托一次"，不约束调用次数。使用两个不同日期（`2024-02-29` 与 `2024-03-01`）证明 filing_date 和 report_date 均独立委托 owner，且值未被改写。

旧断言中 `report_date="2024-02-29"` 与 `filing_date="2024-02-29"` 相同，无法区分两个字段是否都委托；新断言用不同日期消除了该歧义。

---

## scope 完整性检查

| 检查项 | 结果 |
| --- | --- |
| `git diff --name-only` 仅含两个测试文件 | ✅ `tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py` |
| production 代码零改动 | ✅ `git diff HEAD -- dayu/` 无输出 |
| 其它测试文件零改动 | ✅ |
| README 零改动 | ✅ |
| frozen registry/evidence 零改动 | ✅ |
| 两修改测试全绿 | ✅ `3 passed, 3 warnings` |

## Fix artifact 可信度

AgentCodex aggregate fix artifact 声明：

- 仅修改两个测试文件：与 `git diff --name-only` 一致 ✅
- 未修改 production/README/frozen：与实际 diff 一致 ✅
- 验证命令覆盖 focused、runtime 完整、CLI 完整、pyright、diff check：fix artifact 已记录 ✅
- 不执行 UF-PF04、不处理其它 residual：scope 正确 ✅

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无新增。aggregate deepreview 中列出的 residual 项均未被本次 fix 扩展或遗漏。

## Conclusion

**Pass。** F1 正确覆盖 baseline `fromisoformat` 可解析但 strict owner 拒绝的 basic format `20240229`，exact message 为统一后 contract `"start_date must be an ISO date"`。F2 使用两个不同日期（`2024-02-29` / `2024-03-01`）证明 filing_date 和 report_date 均独立委托 owner、值不被改写，同时保留 deterministic identity、resolved action 与 request identity 断言，不再锁定调用次数。scope 完整性通过：仅两个测试文件改动，production/README/frozen 零改动。
