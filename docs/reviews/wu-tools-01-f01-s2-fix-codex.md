# WU-TOOLS-01-F01 Slice S2 Fix - Codex

## Scope

- Gate: Slice S2 fix gate.
- Branch: `host-wu-tools-01-f01`.
- Fixed only the two controller-accepted findings:
  - `F01-S2-001`
  - `F01-S2-002`
- No Host, Engine, Service, tool provider, download pipeline, CLI, control document, commit, push, PR, or re-review work was performed.

## Fixes

### F01-S2-001

`dayu/fins/ingestion_runtime.py` now applies `_MAX_PREPROCESS_DOCUMENTS` after `_select_preprocess_documents` has applied the real request selection filters:

- source document existence still validates against the repository inventory.
- deleted documents are skipped before counting.
- incomplete-ingest documents are skipped before counting.
- `form_types` filtering is applied before counting.
- the max-count rejection now reflects the actual filtered work set.

Regression coverage was added in `tests/fins/test_fins_ingestion_runtime.py`:

- `test_start_preprocess_whole_ticker_applies_limit_after_form_filter`
- The fixture creates more source documents than `_MAX_PREPROCESS_DOCUMENTS`.
- The request uses whole-ticker selection with `form_types=("10-K",)`.
- The nonmatching `10-Q` documents are excluded before the limit check.
- The job succeeds and only processes the matching `aapl-2024-10k` source document.

### F01-S2-002

`dayu/fins/ingestion_runtime.py` now logs bounded diagnostics when `_save_failed_from_exception` itself cannot persist the failed terminal record:

- the method remains best-effort and non-throwing.
- the diagnostic includes `job_id`.
- the diagnostic includes secondary exception type.
- the diagnostic includes original exception type.
- traceback context is emitted through logger exception info rather than broadening job record payloads.

Focused coverage was added in `tests/fins/test_fins_ingestion_runtime.py`:

- `test_save_failed_from_exception_logs_secondary_job_store_failure`
- The test forces `FsFinsIngestionJobStore.save_job` to raise while `_save_failed_from_exception` is handling a primary exception.
- It verifies the secondary exception does not propagate.
- It verifies the diagnostic log contains the event name, `job_id`, secondary error type, and original error type.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py
```

Result: `31 passed, 3 warnings`.

Passed:

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

The pytest warnings are existing third-party `edgar` deprecation warnings and are unrelated to this fix.

## README Sync

README updates were not needed.

Reason: both fixes preserve the stable runtime interface and documented Fins responsibilities. They change internal selection correctness and internal diagnostic observability only; no user-facing command, configuration, public contract, storage path, package boundary, or documented workflow changed.

## Residual Risk

- The whole-ticker regression test covers form filtering after an over-limit source inventory. It does not separately enumerate deleted and incomplete-ingest combinations, because the root finding was the max-count check location and the same filtered work-set count path now covers those filters.
- `_save_failed_from_exception` remains intentionally best-effort. If both reading and saving the job record fail, the diagnostic is logged but no terminal record can be written by design.
