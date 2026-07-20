# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S1 Code Review Controller Adjudication

## Adjudication Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S1 — Financial Result, XBRL Execution, And LLM Projection Contracts`
- Gate: `code review controller adjudication`
- Timestamp: 2026-07-13 09:24:00 CST
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-ds.md`

## Controller Decision

`fix-required`

Both AgentMiMo and AgentDS returned pass decisions, but the controller accepts the concrete review findings as fix-worthy before S1 can be accepted. This follows the user instruction to fix all discovered findings before reporting.

## Accepted Fixes

### CR-S1-01 - HTML fiscal year must not survive without fiscal period

- Source: AgentDS DS-01.
- Severity: required fix.
- Required correction:
  - In `dayu/fins/processors/html_financial_statement_common.py`, when `fiscal_period is None`, `fiscal_year` must also be `None` for S1 financial periods.
  - Add a test fixture where direct text provides a year-like token but no accepted fiscal period evidence; assert both `fiscal_year` and `fiscal_period` are `None` and quality/reason degrade correctly.

### CR-S1-02 - Remove unused `period_end` parameter from direct fiscal text helper

- Source: AgentDS DS-02.
- Severity: required fix.
- Required correction:
  - Remove the unused `period_end` parameter from `_extract_fiscal_period_from_direct_text`.
  - Update both call sites.

### CR-S1-03 - Document OCR income-summary units/currency assumption

- Source: AgentDS DS-03.
- Severity: required fix.
- Required correction:
  - Update `_build_income_summary_result_from_title_match` docstring to state that `units` and `currency` intentionally share the income-summary reporting currency, and that this assumption must not be reused for non-currency statement types.

### CR-S1-04 - Align read-runtime rejection test with owner-level contract

- Source: AgentMiMo F1.
- Severity: required test fix.
- Required correction:
  - Adjust `test_get_financial_statement_rejects_missing_or_non_list_rows` or adjacent tests so the invalid fixture fails at the domain owner contract, not incidentally during downstream row iteration.
  - The test name and assertion must match the owner-level failure being tested.

## Accepted Non-Fix Observations

- AgentDS DS-04 records a positive latent behavior correction: bool values are no longer counted as numeric OCR row values. No fix required.
- AgentMiMo residual `_is_json_value` duplication and import consolidation are not current-scope correctness findings and do not require S1 fix.

## Required Fix Gate

AgentCodex must:

1. Modify only files already in S1 scope plus `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s1-code-review-fix-codex.md`.
2. Apply CR-S1-01 through CR-S1-04.
3. Run affected focused tests, full S1 focused validation, pyright, and `git diff --check`.
4. Stop after the fix artifact; do not commit, push, review, or enter S2.

## Blocking Questions

None.
