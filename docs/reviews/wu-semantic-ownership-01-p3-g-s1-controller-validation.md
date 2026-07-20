# Controller Validation — WU-SEMANTIC-OWNERSHIP-01 P3-G S1

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Slice: S1 — SEC form and shared domain typed values.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-g-s1-implementation-codex.md`
- Accepted plan commit: `e5e4ad97`

## Controller Checks

The implementation stayed within S1:

- added `dayu/fins/domain/filing_semantics.py` as the shared domain parser/closed-value owner;
- deleted `dayu/fins/processors/form_type_utils.py`;
- moved SEC form normalization consumers in processors, SEC pipeline helpers, SC13 browse-edgar paths, fiscal helpers, and read runtime to the domain owner;
- tightened decode boundaries for rejected SEC artifact form, fiscal period, and document quality;
- did not implement CN/HK report selection migration, typed rejection registry, or XBRL `total` contract changes.

## Validation Results

- `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_read_runtime.py -q`
  - Result: `84 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && rg -n "form_type_utils|from dayu\\.fins\\.processors\\.form_type_utils|from \\.form_type_utils|normalize_form\\(|normalize_form_type\\(|_normalize_form\\(|_normalize_form_type\\(|_normalize_report_form_type\\(|_normalize_form_for_fiscal\\(" dayu/fins tests/fins`
  - Result: no matches, exit code `1`.
- `git diff --check`
  - Result: passed.
- `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_read_runtime.py --cov=dayu.fins.domain.filing_semantics --cov-report=term-missing --cov-fail-under=80 -q`
  - Result: `73 passed, 3 warnings`; `dayu/fins/domain/filing_semantics.py` coverage `80.43%`.

Warnings are existing edgartools deprecation warnings and not introduced by this slice.

## Propagation Audit

- User/CLI SEC form filter input now goes through `parse_sec_form_filter_value(...)` and `expand_sec_form_aliases(...)`, preserving fail-closed behavior for unsupported user forms and expanding the `SC 13D/G` group alias into supported single forms.
- SEC provider raw filing rows now use `normalize_sec_form_type_for_matching(...)` and then existing target windows decide whether to keep or skip the row, avoiding false user-input failures for unknown provider rows.
- Rejected SEC artifact decode now uses `parse_sec_form_type(...)`, so a stored single filing form cannot be the `SC 13D/G` group alias or an unsupported form.
- Fiscal period normalization is centralized through `normalize_fiscal_period(...)` and form-specific sanitation through `sanitize_fiscal_period_by_sec_form(...)`.
- `DocumentSummary.from_dict(...)` now rejects invalid fiscal period and document quality values at the domain decode boundary.
- Processor selection, SEC fiscal helper, SC13 browse-edgar, rebuild workflow, and read runtime form matching consume the domain helper rather than maintaining separate mappings.

## README Decision

`dayu/fins/README.md` was updated because S1 adds a stable Fins domain contract for SEC form, fiscal period, document quality, and financial data quality parsing. `tests/README.md` was not updated because no new test layer or test responsibility was introduced.

## Residual Risk

- `DocumentSummary.form_type` remains a general optional string because it represents SEC, CN/HK, and material forms. This is accepted for S1; strict SEC single-form parsing is applied where the value is known to be a SEC filing form.
- `FinancialDataQuality` parser is introduced but not yet wired into XBRL result validation; that remains S4 scope by plan.

## Gate

Ready for independent code review by AgentMiMo and AgentDS.
