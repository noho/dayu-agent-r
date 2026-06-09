# WU-TOOLS-01-F01-03 Slice 3 Fix Gate - AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 3: Migrate CN/HK Downloader And CN/HK Download Runtime`
- Fix gate source: `docs/reviews/wu-tools-01-f01-03-slice3-code-review-controller-adjudication.md`
- Scope boundary: only accepted controller findings CTRL-S3-01 through CTRL-S3-06 were addressed. No CN/HK upload, process, CLI, Host/Engine contract, or SEC processor registry behavior was changed.

## CTRL Findings

### CTRL-S3-01 - Fixed

- CN/HK adapter factory defaults are now source-specific.
- `build_cn_download_adapter(...)` uses `cninfo_downloader.DEFAULT_SLEEP_SECONDS` / `DEFAULT_MAX_RETRIES`.
- `build_hk_download_adapter(...)` uses `hkexnews_downloader.DEFAULT_SLEEP_SECONDS` / `DEFAULT_MAX_RETRIES`.
- Added deterministic coverage in `tests/fins/test_cn_download_runtime.py` by monkeypatching the two source default sets to distinct values and asserting the factory-built adapter pipeline uses the matching values.

### CTRL-S3-02 - Fixed

- Removed unused `ProcessorRegistry` from CN/HK download facade boundaries:
  - `CnPipeline.__init__`
  - `build_cn_download_adapter`
  - `build_hk_download_adapter`
  - CN/HK pipeline and runtime tests
  - `DefaultFinsRuntime` CN/HK adapter factory calls
- SEC `build_sec_download_adapter(..., processor_registry=...)` and runtime-level `FinsIngestionRuntime.create(..., processor_registry=...)` remain unchanged.

### CTRL-S3-03 - Fixed

- Moved `hashlib` and `datetime` imports in `dayu/fins/downloaders/cninfo_downloader.py` to module top level.
- `_sha256_hex` and `_utc_now_isoformat` keep their migrated OLD behavior.

### CTRL-S3-04 - Fixed

- Moved `CnDownloadCancelledError` into `dayu/fins/pipelines/cn_download_models.py`.
- Updated filing workflow, ticker workflow, and rebuild workflow imports.
- Cancellation behavior is unchanged; only the dependency direction changed.

### CTRL-S3-05 - Fixed

- Converted English docstring section labels to Chinese in:
  - `dayu/fins/pipelines/cn_download_pdf_gate.py`
  - `dayu/fins/pipelines/cn_download_source_upsert.py`
  - `dayu/fins/pipelines/cn_download_staging.py`
- No business branch or workflow rule was changed.

### CTRL-S3-06 - Fixed

- Replaced the relative import in `dayu/fins/pipelines/cn_download_pdf_gate.py` with absolute `dayu.fins.pipelines.cn_download_models` import.

## Changed Files

- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_pdf_gate.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_staging.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `112 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported only a newer version notice.
- `git diff --check`
  - Result: passed.
- Targeted scan:
  - Command scanned touched Slice 3 production/test files with `rg -n "\bAny\b|\bobject\b" ...`.
  - Result: no matches.

## README Decision

No README file was changed by this fix gate. The accepted findings are internal adapter/test/docstring cleanup and do not add or change user-facing Fins runtime capabilities beyond the existing Slice 3 implementation.

## Residual Risks / Blockers

- No blocker.
- Deferred controller findings remain deferred by adjudication: broader CN/HK matrix expansion, downloader helper extraction, and unrelated HKEXNews docstring expansion were not implemented.
