# WU-TOOLS-01-F01 Slice S3 Re-Review Controller Adjudication

## Gate Metadata

- Gate: re-review adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S3 - Download Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-s3-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-s3-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s3-rereview-ds.md`

## Verdict

Pass. Slice S3 fix gate is accepted.

Both AgentMiMo and AgentDS verified that the two accepted findings are fixed. Neither reviewer reported new correctness, stability, maintainability or testing blockers.

## Accepted Finding Status

### F01-S3-001

- Status: fixed.
- Evidence: `FinsIngestionJobStore.save_succeeded_or_cancelled(...)` and `FsFinsIngestionJobStore.save_succeeded_or_cancelled(...)` now re-read the current job record under the store lock and atomically choose existing terminal, `CANCELLED`, or `SUCCEEDED`.
- Test evidence: `test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled` injects cancellation immediately before success terminalization and verifies the terminal state is `CANCELLED`.

### F01-S3-002

- Status: fixed.
- Evidence: both `_run_download_job(...)` and `_run_preprocess_job(...)` return immediately when `_mark_job_running_or_cancelled(...)` returns any status in `_TERMINAL_STATUSES`.
- Test evidence: `test_runners_return_for_preterminalized_jobs_without_executing` verifies pre-terminalized download and preprocess jobs do not execute adapter/preprocess work again.

## New Findings

None.

## Residual Risks

- Completed storage writes are not rolled back if cancellation arrives after source/blob/rejected artifacts have already been written but before success terminalization. This is the current ingestion runtime non-transactional boundary and is not a Slice S3 blocker.
- DS observed that `_save_cancelled` and `_save_failed` still use direct terminal writes rather than the new success-or-cancelled arbitration. This is outside the accepted fix scope and currently not reachable as a conflicting concurrent success path in the single-runner model. If future slices introduce multiple writers per job, terminal arbitration should be generalized.
- Real SEC/CN/HK network download adapters remain explicitly out of S3 scope.

## Required Controller Validation

Before accepted slice commit, run:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

## Next Gate

Proceed to accepted slice commit for WU-TOOLS-01-F01 Slice S3 if controller validation passes.
