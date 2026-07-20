# Controller Validation — WU-SEMANTIC-OWNERSHIP-01 P3-G S2

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Slice: S2 — CN/HK report candidate classification and fiscal inference ownership.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-g-s2-implementation-codex.md`
- Accepted prior slice: S1 commit `79629dfa`

## Controller Checks

The implementation stayed within S2:

- added `dayu/fins/pipelines/cn_report_selection.py` as the pipeline owner for CN/HK report selection;
- moved CNInfo/HKEXNews title filtering, language filtering, fiscal period/year inference, period/year grouping, amended preference, and `CnReportCandidate` construction into the pipeline helper;
- kept downloader responsibilities to HTTP/JSON/raw-provider field parsing, URL normalization, stock/company lookup, HEAD/GET, and PDF validation;
- did not implement S3 typed SEC rejection registry or S4 XBRL `total` contract changes.

## Validation Results

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py -q`
  - Result: `76 passed`.
- `source .venv/bin/activate && pytest tests/fins/test_cn_report_selection.py --cov=dayu.fins.pipelines.cn_report_selection --cov-fail-under=80 -q`
  - Result: `4 passed`; `dayu/fins/pipelines/cn_report_selection.py` coverage `84%`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && rg -n "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders dayu/fins/pipelines`
  - Result: matches only in `dayu/fins/pipelines/cn_report_selection.py`.
- `git diff --check`
  - Result: passed.

## Propagation Audit

- CNInfo/HKEXNews provider endpoints produce raw announcement JSON.
- Downloaders parse provider raw fields into `CninfoRawAnnouncement` / `HkexnewsRawAnnouncement` and expose HTTP HEAD through `CnReportHeadMeta`.
- `dayu.fins.pipelines.cn_report_selection` applies product-level report filtering, language filtering, fiscal period/year inference, dedupe/grouping, amended preference, and `CnReportCandidate` construction.
- Existing workflow-facing `list_report_candidates(...)` contract remains stable; concrete downloader implementations now compose raw fetch with the pipeline helper.
- `CnReportCandidate` continues into CN/HK workflow, source/blob commit, source meta, and direct stream summary.

## README Decision

`dayu/fins/README.md` was updated because S2 changes the stable Fins downloader/pipeline ownership boundary. `tests/README.md` was updated because a new `tests/fins/test_cn_report_selection.py` helper test responsibility was introduced.

## Residual Risk

- `CnReportDiscoveryClientProtocol.list_report_candidates(...)` still returns `CnReportCandidate` to preserve the existing workflow contract; the concrete downloader implementation delegates candidate selection to the pipeline helper. A future raw-discovery protocol change would be a separate breaking-contract slice.
- Provider category/request parameters remain in downloader because they are HTTP request construction facts, not product-level report selection rules.

## Gate

Ready for independent code review by AgentMiMo and AgentDS.
