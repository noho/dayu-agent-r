# WU-TOOLS-01-F01-03 Slice 2 Fix Gate

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: Slice 2 fix gate
- Agent: AgentCodex
- Controller source: `docs/reviews/wu-tools-01-f01-03-slice2-code-review-controller-adjudication.md`
- Scope boundary: only accepted CTRL-S2-01 through CTRL-S2-07 findings were addressed. No CN/HK download, upload, process, CLI, DS deferred findings, or MiMo deferred findings were implemented.

## Findings Status

### CTRL-S2-01

- Status: fixed.
- Files:
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `tests/fins/test_sec_pipeline_download.py`
- Change:
  - `_summary_from_pipeline_result` now counts OLD SEC 6-K rejected artifacts represented as `status="skipped"` with `skip_reason` or `reason_code` equal to `6k_filtered`.
  - OLD workflow result semantics were not rewritten; 6-K filtered filings still remain skipped filing results.
  - Added deterministic SEC adapter test proving the persisted summary path reports `rejected_count == 1` for a 6-K filtered rejected artifact.

### CTRL-S2-02

- Status: fixed.
- Files:
  - `tests/fins/test_sec_pipeline_download.py`
- Change:
  - Moved `StubDownloader.list_filing_files` counter increment below the function docstring so Python treats the triple-quoted string as the real docstring.

### CTRL-S2-03

- Status: fixed.
- Files:
  - `tests/fins/test_sec_pipeline_download_stream.py`
- Change:
  - Removed dead `_SpySourceRepository.download_files_stream`; production stream path reads `download_files_stream` from the downloader, not the source repository.
  - No replacement behavior added.

### CTRL-S2-04

- Status: fixed.
- Files:
  - `tests/fins/test_sec_downloader.py`
- Change:
  - Removed the four stray `@pytest.mark.unit` decorators.
  - No marker taxonomy was added.

### CTRL-S2-05

- Status: fixed.
- Files:
  - `dayu/fins/pipelines/sec_pipeline.py`
- Change:
  - Removed unused `_maybe_await` and the now-unused `inspect`, `Awaitable`, and `TypeVar` imports.

### CTRL-S2-06

- Status: fixed.
- Files:
  - `dayu/fins/pipelines/__init__.py`
- Change:
  - Added only a Chinese module overview docstring for the new package.

### CTRL-S2-07

- Status: fixed.
- Files:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
- Change:
  - Clarified that persisted-summary adapters own their storage side effects and that NEW `rebuild_processed` is a processed reprocess governance flag, not a source workflow rebuild flag.
  - Kept `SecDownloadAdapter.download(...)` passing `rebuild=False` to OLD `SecPipeline.download(...)`.
  - Added focused runtime test proving a persisted-summary adapter receives and records `rebuild_processed=True`.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `113 passed, 3 warnings`
  - Warnings: edgartools deprecation warnings from dependency imports.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output.
- Targeted scan:
  - Command: `rg -n "\bAny\b|\bobject\b" dayu/fins/pipelines/sec_pipeline.py dayu/fins/pipelines/__init__.py dayu/fins/ingestion_runtime.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: no matches.

## Residual Risks

- No blocker.
- Live SEC network behavior remains outside deterministic tests.
- Deferred controller findings remain deferred and were not addressed in this fix gate.
