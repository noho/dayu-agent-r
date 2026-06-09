# WU-TOOLS-01-F01-03 Slice 3 Fix Re-Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 3: Migrate CN/HK Downloader And CN/HK Download Runtime`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice3-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice3-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-03-slice3-fix-codex.md`

## Verdict

`pass`

Both re-review agents confirmed all six controller-accepted findings are fixed, with 0 blocking findings and 0 new findings. Controller accepts the Slice 3 fix and closes this review/fix loop.

## Accepted Findings Status

- `CTRL-S3-01`: fixed. CN and HK adapter factories now use source-specific downloader defaults, with deterministic coverage proving the split.
- `CTRL-S3-02`: fixed. CN/HK download facade boundaries no longer accept or store unused `ProcessorRegistry`; SEC pipeline and runtime-level registry wiring remain unchanged.
- `CTRL-S3-03`: fixed. CNInfo downloader standard-library imports are module-level.
- `CTRL-S3-04`: fixed. `CnDownloadCancelledError` lives in shared CN download models, and rebuild no longer depends on filing workflow for that control-flow exception.
- `CTRL-S3-05`: fixed. The accepted CN download modules now use Chinese docstrings / section labels without business branch changes.
- `CTRL-S3-06`: fixed. `cn_download_pdf_gate.py` uses an absolute import.

## Controller Validation

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`: 112 passed, 3 edgartools deprecation warnings
- `source .venv/bin/activate && pyright`: 0 errors
- `git diff --check`: passed
- Targeted `Any` / type `object` scan over Slice 3 production/test files: no matches
- Boundary scan for upload/process/CLI and Host/Engine reverse dependency in Slice 3 production files: no matches

## Deferred Findings

The following remain deferred exactly as decided in the Slice 3 code-review adjudication:

- `CTRL-S3-D1`: broader CN/HK workflow/runtime test matrix expansion.
- `CTRL-S3-D2`: broad downloader helper de-duplication.
- `CTRL-S3-D3`: unrelated `HkexnewsDiscoveryClient` docstring expansion.

## Next Gate

Slice 3 is ready for an accepted implementation commit. After bookkeeping, the next implementation entry is Slice 4: migrate upload service and production upload runtime, preserving OLD SEC/CN upload workflow semantics and treating upload as a long transaction.
