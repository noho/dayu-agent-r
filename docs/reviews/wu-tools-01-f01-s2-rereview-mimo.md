# WU-TOOLS-01-F01 Slice S2 Re-Review - MiMo

## Gate Metadata

- Gate: Slice S2 re-review gate.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S2 - Preprocess / Process Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s2-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-s2-code-review-controller-adjudication.md`
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`

## Verdict

**pass**

## Accepted Findings Status

### F01-S2-001 — fixed

- Requirement: `_MAX_PREPROCESS_DOCUMENTS` must be checked after deleted / ingest_complete / form_types filtering on the actual work set, with a regression test covering whole-ticker over-inventory but under-limit after form filter.
- Evidence:
  - `dayu/fins/ingestion_runtime.py:1034-1048`: `_select_preprocess_documents` applies the filter loop (deleted at line 1037, ingest_complete at line 1039, form_types at line 1042) to build `filtered_ids`, then checks `len(filtered_ids) > _MAX_PREPROCESS_DOCUMENTS` at line 1047. The max-count rejection is now on the filtered work set, not the raw repository inventory.
  - `tests/fins/test_fins_ingestion_runtime.py:367-389`: `test_start_preprocess_whole_ticker_applies_limit_after_form_filter` creates `_MAX_PREPROCESS_DOCUMENTS + 1` extra `10-Q` source documents via `_add_unmatched_source_documents`, then requests `form_types=("10-K",)` with whole-ticker selection. The `10-Q` documents are excluded by the form filter before the limit check. The job succeeds and only processes the single matching `aapl-2024-10k` source document. Assertions verify `selected_count == 1`, `processed_count == 1`, and `processed_document_ids == ["aapl-2024-10k"]`.
- Assessment: The fix is correct and complete. The max-count bound now reflects the actual filtered work set as required by the controller adjudication.

### F01-S2-002 — fixed

- Requirement: `_save_failed_from_exception` must log bounded diagnostic context when secondary job-store failure occurs, remain non-throwing, with a focused test verifying log content and no propagation.
- Evidence:
  - `dayu/fins/ingestion_runtime.py:1247-1256`: The `except Exception as terminal_exc` block logs a `WARNING`-level message with event name `fins.ingestion.failed_terminalization_failed`, structured arguments `job_id`, `error_type` (secondary), and `original_error_type` (primary), plus `exc_info=True` for traceback. The method returns without re-raising, preserving non-throwing behavior.
  - `tests/fins/test_fins_ingestion_runtime.py:485-526`: `test_save_failed_from_exception_logs_secondary_job_store_failure` monkeypatches `FsFinsIngestionJobStore.save_job` to raise `OSError`, calls `_save_failed_from_exception` with a primary `RuntimeError`, and asserts: (a) no exception propagates, (b) log contains `fins.ingestion.failed_terminalization_failed`, (c) log contains `job_id=`, (d) log contains `error_type=OSError`, (e) log contains `original_error_type=RuntimeError`.
- Assessment: The fix is correct and complete. Bounded diagnostic logging is present, non-throwing behavior is preserved, and the test validates all required log fields.

## New Findings

none

## Validation Notes

- `pytest tests/fins/test_fins_ingestion_runtime.py`: **20 passed, 3 warnings** (all warnings are existing third-party `edgar` deprecation warnings, unrelated to this fix).
- `pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`: **0 errors, 0 warnings, 0 informations**.

## Blocking Open Questions

none
