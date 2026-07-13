# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review Re-Review — AgentMiMo

## Review Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review re-review`
- Reviewer: `AgentMiMo`
- Timestamp: 2026-07-13
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-controller-adjudication.md`

## Closure Table

| Finding | Description | Verdict | Evidence |
| --- | --- | --- | --- |
| CR-S1-01 | HTML fiscal year must not survive without fiscal period | ✅ closed | `_build_period_for_column` (line 735-741) and `_build_single_scope_period` (line 784-790) both guard `fiscal_year` on `fiscal_period is not None` first. New test `test_html_year_token_without_accepted_fiscal_period_clears_fiscal_year` (line 1133) constructs a fixture with `"Reporting year 2025"` year token but no accepted fiscal-period evidence; asserts all periods `fiscal_year=None`, `fiscal_period=None`, `data_quality="partial"`, `reason="period_semantics_unavailable"`. |
| CR-S1-02 | Remove unused `period_end` parameter from `_extract_fiscal_period_from_direct_text` | ✅ closed | Function signature (line 1579-1582) now only takes `scope_text`. Both call sites (line 730-732, line 779-781) pass only `scope_text=...`. `del period_end` removed. |
| CR-S1-03 | Document OCR income-summary units/currency assumption | ✅ closed | `_build_income_summary_result_from_title_match` docstring (line 1106-1107) now reads: "income summary 的 ``units`` 与 ``currency`` 有意同源，均表示该货币报表的报告货币；该假设不适用于非货币计量的 statement type，后者不得复用。" |
| CR-S1-04 | Align read-runtime rejection test with owner-level contract | ✅ closed | Test renamed to `test_financial_statement_owner_rejects_missing_or_non_list_rows` (line 754). Now directly calls `validate_financial_statement_result_payload` with two parametrized fixtures: missing `rows` expects `"缺少必填字段: rows"`, non-list `rows` expects `"rows 必须为数组"`. No dependency on runtime citation construction or downstream row iteration. |

## Scope Creep Check

Changed production files (17 modified + 2 new): all within S1 allowlist (`dayu/fins/processors/*`, `dayu/fins/tools/*`, `dayu/fins/domain/*`, `tests/fins/*`). No Host/Engine, R3-E, tool-security, upload/download security, 6-K dual-engine routing, or full DocumentMeta migration changes detected.

## Validation

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
→ 73 passed, 3 warnings

pytest tests/fins/test_fins_storage_provider.py -q -k "financial_statement or xbrl_query or financial_tool"
→ 4 passed, 45 deselected, 3 warnings

python -m pyright dayu/fins/domain/financial_result_contract.py dayu/fins/domain/xbrl_result_contract.py dayu/fins/tools/result_types.py dayu/fins/tools/read_runtime.py dayu/fins/tools/read_runtime_helpers.py dayu/fins/processors/html_financial_statement_common.py dayu/fins/processors/six_k_form_common.py
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ pass
```

## New Findings

None.

## Decision

**PASS.** All four controller-accepted fixes (CR-S1-01 through CR-S1-04) are verified closed with direct code evidence. Tests pass (73 + 4). Pyright clean. No scope creep. No new findings.
