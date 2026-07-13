# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review Fix

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review fix`
- Fix owner: `AgentCodex`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-controller-adjudication.md`
- Status: `pass`
- Commit authorization: none；本 gate 未 commit、未 push、未进入 S2。

## Scope

本 fix 只处理 controller accepted 的 `CR-S1-01` 至 `CR-S1-04`，未处理 S2/S3、tool-security、R3-E、upload/download security、6-K dual-engine routing 或 full `DocumentMeta` migration。按用户约束未处理 DS-04、`_is_json_value` duplication 或 import consolidation，未做泛清理、review、commit 或 push。

## Changed Files

- `dayu/fins/processors/html_financial_statement_common.py`
- `dayu/fins/processors/six_k_form_common.py`
- `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-fix-codex.md`

## Finding Status

### CR-S1-01 — 已修复

- `_build_period_for_column` 与 `_build_single_scope_period` 现在都只在 `fiscal_period` 已有 accepted direct evidence 时产生 `fiscal_year`；`fiscal_period is None` 时 `fiscal_year` 强制保持 `None`。
- 新增 HTML 公共 producer 测试，构造含普通 `2025` 年份 token、但无 accepted fiscal-period evidence 的直接文本，断言全部 period 的 `fiscal_year` / `fiscal_period` 均为 `None`，并断言 `data_quality=partial`、`reason=period_semantics_unavailable`。
- 直接代码核对显示当前 `_extract_fiscal_period_label()` 复用 `_extract_fiscal_period_year()`，因此 review 所述两个 helper pattern 不重叠的具体路径当前不可达；本修复仍在 period producer owner 处显式锁定裁决要求的 invariant，避免未来解析路径演进后产生孤立财年。

### CR-S1-02 — 已修复

- 从 `_extract_fiscal_period_from_direct_text` 移除未使用的 `period_end` 参数、对应 docstring 文本与 `del period_end`。
- 两个 call site 均只传入实际参与解析的 `scope_text`。

### CR-S1-03 — 已修复

- `_build_income_summary_result_from_title_match` docstring 现在明确：income summary 的 `units` 与 `currency` 有意同源，均表达货币报表的报告货币；该假设不得复用于非货币计量的 statement type。

### CR-S1-04 — 已修复

- 将原 read-runtime rejection 测试改名为 `test_financial_statement_owner_rejects_missing_or_non_list_rows`。
- 测试直接调用 `validate_financial_statement_result_payload`，分别断言缺失 `rows` 在 domain owner boundary 报告 `缺少必填字段: rows`、非数组 `rows` 报告 `rows 必须为数组`。
- 测试不再依赖 runtime citation 构造或后续 row iteration 的偶然失败。

## Validation

### S1 Focused Tests

```bash
source .venv/bin/activate
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
```

结果：`73 passed, 3 warnings`。warnings 均来自既有 edgartools deprecated modules。

### Storage Provider Financial Tests

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
```

结果：`4 passed, 45 deselected, 3 warnings`。warnings 均来自既有 edgartools deprecated modules。

### Pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Diff Check

```bash
git diff --check
```

结果：pass，无输出。

## README Decision

不更新 README。Accepted plan 明确要求 S1 不单独修改 README，并在 S3 aggregate docs step 统一同步 Fins financial/XBRL 当前 contract；本 fix 未改变该裁决。

## Residual Risks

- S2 的 source revision/cache freshness、decode/search failure 与 section/table consistency 仍未实施，按约束留在 S2，不是本 fix gate 的未完成项。
- S3 的 fiscal normalization/sort、optional dataframe string、SEC download version 与 ticker alias owner 仍未实施，按约束留在 S3。
- DS-04、`_is_json_value` duplication 与 import consolidation 按 controller/user 裁决不属于本 fix；未新增兼容分支或下游补偿。
- 当前指定测试和 pyright 均通过；除既有 edgartools deprecation warnings 外，无新增已知 current-scope residual risk。

## Blocking Questions

None。

## Fix Gate Decision

- status: `pass`
- `CR-S1-01`: `已修复`
- `CR-S1-02`: `已修复`
- `CR-S1-03`: `已修复`
- `CR-S1-04`: `已修复`
- remaining accepted findings: `0`
- blocking questions: `0`
- artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-fix-codex.md`
- 本 artifact 不授权 commit、push、review 或进入 S2；按用户要求停在 S1 code-review fix gate。
