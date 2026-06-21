# Code Review — Fix Re-Review

## Scope

- Mode: fix re-review (verify accepted fix items only)
- Branch: `phase/wu-tools-01-f03-r4`
- Base: current working tree after Codex fix
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-mimo.md`
- Included scope: `tests/fins/test_fins_storage_provider.py`, `tests/tools/test_doc_tools_provider.py`, `docs/reviews/wu-tools-01-f03-r4-slice5-fix-codex.md`
- Excluded scope: Slice 6 docs/design, production code changes outside fix scope
- Prior review artifacts: `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-mimo.md`, `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-ds.md`

## Verification Checklist

### F1: `processor_cache_max_entries` negative assertion — CLOSED

**要求**: `test_fins_provider_explicit_limits_shape_truncate_specs` 必须断言 `processor_cache_max_entries` 不出现在任何 ToolDefinition 的 `truncate.limits` 中，同时保留全部可见 limit 正向断言。

**验证**:

- `tests/fins/test_fins_storage_provider.py:1151-1159` — 9 个正向 limit 断言全部保留（`list_documents.max_items=21`, `get_document_sections.max_items=122`, `search_document.max_items=23`, `list_tables.max_items=54`, `read_section.max_chars=8100`, `get_page_content.max_chars=8200`, `get_table.max_items=830`, `get_financial_statement.max_items=1240`, `query_xbrl_facts.max_items=1250`）。✓
- `tests/fins/test_fins_storage_provider.py:1160-1163` — 新增遍历全部 definitions 的负向断言：`for definition in definitions.values(): assert "processor_cache_max_entries" not in truncate.limits`。覆盖全部 9 个 Fins 工具。✓
- 测试配置中 `processor_cache_max_entries=16` 仍然存在于 config 中（`tests/fins/test_fins_storage_provider.py:1135`），确认该值进入 provider 但不投影到 ToolDefinition。✓
- 辅助函数 `_truncate_limit` 同步新增（`tests/fins/test_fins_storage_provider.py:1420-1438`），与 Doc 测试文件中同名函数语义一致。✓

**结论**: F1 已关闭。负向断言覆盖全部 9 个工具，正向断言无遗漏。

### F2: Partial limits fallback — CLOSED

**要求**: 必须存在 partial limits 测试，证明显式单项 limit 覆盖默认值，缺失字段回退到 `DocToolLimits` dataclass 默认值。

**验证**:

- `tests/tools/test_doc_tools_provider.py:1008-1040` — 新增 `test_doc_provider_partial_limits_fall_back_to_defaults`。✓
- 测试只传 `list_files_max=99`，`defaults = doc_tools.DocToolLimits()` 获取默认值。✓
- 正向断言：`_parameter_maximum(definitions["list_files"], "limit") == 99`（显式覆盖）。✓
- 回退断言：
  - `get_file_sections.limit.maximum == defaults.get_sections_max` ✓
  - `search_files.limit.maximum == defaults.search_files_max_results` ✓
  - `read_file.truncate.limits["max_chars"] == defaults.read_file_max_chars` ✓
  - `read_file_section.truncate.limits["max_chars"] == defaults.read_file_section_max_chars` ✓
- 辅助函数 `_parameter_maximum` 和 `_truncate_limit` 同步新增（`tests/tools/test_doc_tools_provider.py:1144-1175`）。✓

**结论**: F2 已关闭。测试覆盖显式覆盖和缺失回退两条路径，5 个 limit 字段全部断言。

### Check 3: No production code changed by fix — CONFIRMED

**验证**:

- `dayu/tools/doc_provider.py` 的 diff 属于 Slice 5 实现变更（fail-closed 语义、`_EMPTY_ALLOWED_PATHS_ERROR` 常量、`_parse_limits()` 抽取），不是 fix 产物。fix artifact 明确声明"未修改生产代码"。✓
- fix 只修改了 `tests/fins/test_fins_storage_provider.py` 和 `tests/tools/test_doc_tools_provider.py`。✓
- `tests/README.md` 未被 fix 修改（fix artifact 也声明"未修改"）。✓

**结论**: 无生产代码回归。

### Check 4: Validation sufficient — CONFIRMED

**验证**:

- pytest: `57 passed, 3 warnings`（warnings 来自 edgar 依赖，非测试本身）。✓
- pyright: `0 errors, 0 warnings, 0 informations`。✓
- 本轮独立验证结果与 fix artifact 报告一致。✓

## Findings

未发现实质性问题。

## Open Questions

- 无

## Residual Risk

- `processor_cache_max_entries` 的 runtime cache 行为（LRU 容量）需要更重的集成测试才能直接验证，超出 Slice 5 范围。当前测试只验证该值不投影到 ToolDefinition，不验证 cache 容量是否生效。此风险已在原 review 中记录，非本轮 fix 引入。

## Verdict

**Accept** — F1 和 F2 均已关闭，无回归，无新增 findings。

- F1: `processor_cache_max_entries` 负向断言覆盖全部 9 个 Fins 工具的 `truncate.limits`，正向断言无遗漏。
- F2: partial limits fallback 测试证明显式 `list_files_max=99` 覆盖默认值，其余 4 个 limit 字段正确回退到 `DocToolLimits()` 默认值。
- 无生产代码被 fix 修改。
- 测试 57 passed，pyright 0 errors。
