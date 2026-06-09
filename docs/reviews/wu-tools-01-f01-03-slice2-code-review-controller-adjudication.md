# WU-TOOLS-01-F01-03 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 2: Migrate SEC Downloader And SEC Download Runtime`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice2-code-review-ds.md`
- Controller validation before review:
  - `pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q`: 111 passed, 7 warnings
  - `pyright`: 0 errors
  - `git diff --check`: passed
  - targeted `Any` / type `object` scan: no matches
  - boundary scan for CN/HK, upload/process, Host/Engine reverse dependency: no matches

## Verdict

`fix-required`

AgentMiMo reported `pass-with-findings` with 0 blocking findings. AgentDS reported `fix-accepted` with 2 high-severity findings. Controller accepts one blocking correctness fix and several small quality fixes. Controller rejects the proposed fix direction that maps NEW `rebuild_processed` directly to OLD `SecPipeline.download(rebuild=...)`, because direct source evidence shows OLD `rebuild` means local downloaded-meta rebuild, not processed reprocess.

## Accepted Fixes

### CTRL-S2-01: SEC persisted summary must count 6-K rejected filings

- Source findings: AgentDS F2.
- Severity: high / blocking.
- Evidence:
  - `dayu/fins/pipelines/sec_pipeline.py` counts `rejected_count` only when `item.get("status") == "rejected"`.
  - `dayu/fins/pipelines/sec_download_filing_workflow.py` emits rejected 6-K artifacts as `status="skipped"` with `skip_reason="6k_filtered"` / `reason_code="6k_filtered"`.
  - `dayu/fins/ingestion_runtime.py` uses `summary.rejected_count == 0` when deciding whether an all-failed download job is failed.
- Required fix:
  - Count migrated SEC rejected filing artifacts in `_summary_from_pipeline_result`.
  - The fix must not rewrite OLD download workflow business logic.
  - Add a deterministic test proving a 6-K filtered filing produces `rejected_count > 0` in the runtime persisted summary path or adapter summary path.

### CTRL-S2-02: Fix misplaced test docstring

- Source finding: AgentMiMo S2-01.
- Severity: medium / accepted.
- Evidence: `tests/fins/test_sec_pipeline_download.py` has `StubDownloader.list_filing_files` incrementing `list_filing_files_call_count` before the triple-quoted docstring, so Python does not treat it as a function docstring.
- Required fix:
  - Move the counter increment below the docstring.

### CTRL-S2-03: Remove dead `_SpySourceRepository.download_files_stream`

- Source findings: AgentMiMo S2-02 / S2-06 and AgentDS F8.
- Severity: low to medium / accepted.
- Evidence: `tests/fins/test_sec_pipeline_download_stream.py` defines `_SpySourceRepository.download_files_stream`, but the production stream path reads `download_files_stream` from the downloader, not from `source_repository`.
- Required fix:
  - Delete the dead method and any imports that become unused.

### CTRL-S2-04: Remove or register stray `unit` marker

- Source findings: AgentMiMo S2-04 and AgentDS F5.
- Severity: low / accepted.
- Required fix:
  - Prefer removing the four `@pytest.mark.unit` decorators from `tests/fins/test_sec_downloader.py`, because the migrated file is already in the default deterministic test set and the repo currently only defines `stress` as a special marker.
  - Do not broaden `pyproject.toml` marker taxonomy unless tests actually need a selectable unit class.

### CTRL-S2-05: Remove unused `_maybe_await` from `sec_pipeline.py`

- Source finding: AgentMiMo S2-05.
- Severity: low / accepted.
- Evidence: `_maybe_await` in `dayu/fins/pipelines/sec_pipeline.py` is not called; `inspect` import exists only for that helper.
- Required fix:
  - Remove the unused helper and its dedicated import.

### CTRL-S2-06: Add `dayu/fins/pipelines/__init__.py`

- Source finding: AgentDS F9.
- Severity: low / accepted.
- Required fix:
  - Add a module-level Chinese overview docstring for the new package.

### CTRL-S2-07: Clarify persisted-summary adapter responsibility for `rebuild_processed`

- Source finding: AgentDS F1, partially accepted with corrected root cause.
- Severity: medium / accepted as clarification and test; not accepted as direct OLD rebuild mapping.
- Evidence:
  - `FinsSourceDownloadAdapterRequest.rebuild_processed` reaches `SecDownloadAdapter`.
  - `SecDownloadAdapter` uses `persisted_summary`, so runtime does not call `_store_downloaded_document`.
  - Direct source evidence shows `SecPipeline.download(rebuild=...)` means "基于本地已下载数据重建 meta", while SEC normal download success already calls `upsert_downloaded_filing_source_document(... mark_processed_reprocess_required=...)` and tests cover changed source fingerprint marking processed snapshots for reprocess.
- Required fix:
  - Do not pass `request.rebuild_processed` to `SecPipeline.download(rebuild=...)`.
  - Update docstring / artifact comments so persisted-summary adapters explicitly own their own storage side effects, including processed reprocess marking when their source update semantics require it.
  - Add or update a focused test that proves the persisted-summary path forwards `rebuild_processed` to adapters and records the request, without asserting OLD `rebuild=True`.

## Deferred Findings

### CTRL-S2-D1: Stream failure / overwrite coverage expansion

- Source findings: AgentMiMo S2-03 and AgentDS residual risk 2.
- Decision: deferred-with-owner to later Slice 2 hardening if a fix pass remains small, otherwise aggregate review.
- Reason: current non-stream migrated tests already cover core failure, overwrite, rejected artifact, and rebuild-local-meta paths; adding broader stream matrix is useful but not required to fix the current blocking correctness issue.

### CTRL-S2-D2: Broader helper de-duplication across migrated OLD modules

- Source findings: AgentDS F6 / F7.
- Decision: deferred.
- Reason: extracting all duplicated OLD helper patterns would touch multiple migrated modules without changing Slice 2 behavior. It should be handled only if review/fix proves it is needed for pyright or correctness, not as a business-logic rewrite during SEC migration.

### CTRL-S2-D3: Finer-grained SEC cancellation inside downloader wait/retry loops

- Source finding: AgentDS F3.
- Decision: deferred-with-owner to later hardening.
- Reason: Slice 2 plan required cooperative cancellation; current implementation passes cancellation to the OLD workflow boundary. File-level and rate-limit sleep interruption is a hardening improvement with possible behavioral side effects, not a blocker for this migration slice.

### CTRL-S2-D4: DefaultFinsRuntime SEC concrete dependency

- Source finding: AgentDS F4.
- Decision: rejected as a current finding.
- Reason: `DefaultFinsRuntime` is the Fins assembly root for default production runtime. Concrete adapter registration there is intended by the Slice 2 plan and avoids creating a speculative factory/profile seam.

## Rejected Findings

### CTRL-S2-R1: Map `rebuild_processed` directly to OLD `SecPipeline.download(rebuild=...)`

- Source finding: AgentDS F1 proposed fix option.
- Decision: rejected.
- Reason: OLD `rebuild` is local downloaded source meta rebuild. NEW `rebuild_processed` is processed artifact reprocess governance. Treating them as the same flag would be a semantic bug and would violate the migration-not-rewrite constraint.

## Required Validation After Fix

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_ingestion_runtime.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
- Targeted scan: no new `Any` / type `object` in touched Slice 2 production/test files.
