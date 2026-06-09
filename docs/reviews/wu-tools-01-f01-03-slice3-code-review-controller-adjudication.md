# WU-TOOLS-01-F01-03 Slice 3 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 3: Migrate CN/HK Downloader And CN/HK Download Runtime`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice3-code-review-ds.md`
- Controller validation before review:
  - `pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`: 111 passed, 3 warnings
  - `pyright`: 0 errors
  - `git diff --check`: passed
  - targeted `Any` / type `object` scan: no matches
  - boundary scan for upload/process/CLI and Host/Engine reverse dependency: no matches

## Verdict

`fix-required`

Both review agents reported 0 blocking findings. Controller accepts a narrow fix set focused on boundary clarity and AGENTS compliance. Broader test-matrix expansion and downloader utility de-duplication are deferred to avoid rewriting migrated OLD business logic during this slice.

## Accepted Fixes

### CTRL-S3-01: Split CN and HK adapter factory defaults

- Source finding: AgentDS F1.
- Severity: medium / accepted.
- Evidence:
  - `dayu/fins/pipelines/cn_pipeline.py` binds combined `DEFAULT_CN_HK_SLEEP_SECONDS` / `DEFAULT_CN_HK_MAX_RETRIES` to CNInfo constants.
  - `build_hk_download_adapter(...)` therefore indirectly follows CNInfo defaults even though `hkexnews_downloader.py` owns explicit HK defaults.
- Required fix:
  - Import HKEXNews `DEFAULT_SLEEP_SECONDS` and `DEFAULT_MAX_RETRIES`.
  - Use source-specific defaults for CN and HK adapter factories.
  - Add deterministic tests proving CN and HK adapter factories pass their own downloader defaults.

### CTRL-S3-02: Remove unused `ProcessorRegistry` from CN/HK download facade

- Source findings: AgentMiMo S3-01 and AgentDS F2.
- Severity: medium / accepted.
- Evidence: `CnPipeline.__init__` accepts and stores `processor_registry`, but no CN/HK download workflow reads it.
- Required fix:
  - Remove the unused parameter/field from `CnPipeline`, `build_cn_download_adapter`, `build_hk_download_adapter`, related tests, and `DefaultFinsRuntime` calls.
  - Do not remove or alter SEC pipeline `processor_registry`; SEC Slice 2 remains accepted.

### CTRL-S3-03: Move standard-library lazy imports in CNInfo downloader to module top level

- Source finding: AgentMiMo S3-02.
- Severity: medium / accepted.
- Evidence: `_sha256_hex` and `_utc_now_isoformat` import `hashlib` / `datetime` inside functions without a documented reason.
- Required fix:
  - Move those imports to the top-level import section.

### CTRL-S3-04: Move `CnDownloadCancelledError` to a shared CN download module

- Source finding: AgentDS F4.
- Severity: low / accepted.
- Evidence: `cn_download_rebuild.py` imports a control-flow exception from `cn_download_filing_workflow.py`, creating a rebuild -> filing workflow dependency that is not semantically necessary.
- Required fix:
  - Move the exception to `cn_download_models.py` or a dedicated small CN download errors module.
  - Update imports without changing cancellation behavior.

### CTRL-S3-05: Convert English CN download module docstrings to Chinese

- Source finding: AgentDS F3.
- Severity: low / accepted.
- Evidence: `cn_download_pdf_gate.py`, `cn_download_source_upsert.py`, and `cn_download_staging.py` contain English module/function docstrings while project constraints require Chinese function docstrings.
- Required fix:
  - Convert affected module/class/function docstrings to Chinese and keep Args / Returns / Raises where functions are involved.
  - Do not alter business branches.

### CTRL-S3-06: Use absolute import in `cn_download_pdf_gate.py`

- Source finding: AgentMiMo S3-06.
- Severity: low / accepted.
- Evidence: `cn_download_pdf_gate.py` uses a relative import while the surrounding migrated CN modules use absolute imports.
- Required fix:
  - Replace the relative import with the absolute `dayu.fins.pipelines...` path.

## Deferred Findings

### CTRL-S3-D1: Broader CN/HK workflow/runtime test matrix expansion

- Source findings: AgentMiMo residuals and AgentDS F5-F10.
- Decision: deferred.
- Reason: current Slice 3 already has deterministic downloader, workflow, pipeline, runtime registration and storage-write coverage. Additional HK retry/HEAD, workflow failure/cancel/date, explicit source/auto route, and pipeline-level persisted-summary matrix are useful hardening but not required to close this migration slice.

### CTRL-S3-D2: Downloader helper de-duplication

- Source findings: AgentMiMo S3-03 / S3-04 and AgentDS F11.
- Decision: deferred.
- Reason: extracting shared downloader helpers would touch two migrated OLD downloader modules beyond the current correctness issue. Keep modules self-contained for migration review; revisit in cleanup if duplication starts causing behavioral drift.

### CTRL-S3-D3: `HkexnewsDiscoveryClient` class docstring expansion

- Source finding: AgentMiMo S3-05.
- Decision: deferred unless already touched by accepted docstring fix.
- Reason: class-level overview is short but Chinese and not misleading. Accepted docstring fix focuses on English function/module docstrings that directly violate the project language requirement.

## Rejected Findings

None.

## Required Validation After Fix

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- Targeted scan: no new `Any` / type `object` in touched Slice 3 production/test files.
