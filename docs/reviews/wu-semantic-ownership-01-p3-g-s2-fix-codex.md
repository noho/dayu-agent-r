# Code Review Fix — WU-SEMANTIC-OWNERSHIP-01 P3-G S2

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Slice: S2 — CN/HK report candidate classification and fiscal inference ownership.
- Accepted fix: `P3-G-S2-CR-F01`
- Input adjudication: `docs/reviews/wu-semantic-ownership-01-p3-g-s2-code-review-controller-adjudication.md`

## Fix

`P3-G-S2-CR-F01` is fixed.

- `dayu/fins/pipelines/cn_download_models.py` no longer defines a second `Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]` for `CnFiscalPeriod`.
- `CnFiscalPeriod` now consumes the shared domain type: `CnFiscalPeriod: TypeAlias = FiscalPeriod`.
- The CN/HK model docstring keeps CN/HK business semantics such as Q2/Q4 not folding into H1/FY, while the closed value set is owned by `dayu.fins.domain.filing_semantics`.
- No S3 rejection registry or S4 XBRL `total` contract code was changed.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_report_selection.py -q`
  - Result: `80 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && rg -n "CnFiscalPeriod = Literal\\[\\\"FY\\\"" dayu/fins tests/fins`
  - Result: no matches, exit code `1`.
- `git diff --check`
  - Result: passed.

## Blocking Questions

None. Ready for independent re-review.
