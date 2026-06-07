# WU-TOOLS-01-F01 Slice S3 Code Review Controller Adjudication

## Gate Metadata

- Gate: code review adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S3 - Download Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s3-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-s3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s3-code-review-ds.md`
  - `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`

## Summary

Both reviewers returned `pass-with-findings`. Slice S3 meets the plan objective: download now has a Fins-owned typed adapter boundary, deterministic no-network test path, source/blob/rejected-artifact storage writes through `dayu.fins.storage`, explicit unsupported-source failure, and no real SEC/CN/HK network adapter scope expansion.

Two DS state-machine findings are accepted for fix. MiMo's low-severity private-test-import finding is rejected for this slice because it is a pre-existing S1 boundary test, not introduced by the S3 download runtime change.

## Accepted Findings

### F01-S3-001 - accepted

- Source: AgentDS.
- Severity: medium.
- File: `dayu/fins/ingestion_runtime.py:1058` and `dayu/fins/ingestion_runtime.py:1106`.
- Finding: `_run_preprocess_job` and `_run_download_job` read the latest job record to check cancellation, then later call `_save_succeeded`. A concurrent cancellation request between the read and success save can be overwritten by `SUCCEEDED`.
- Controller judgment: accepted. This is a real job state-machine race. The F01 design relies on Host wait/cancel governance mapping into durable Fins job terminal state. A cancellation request must not be silently overwritten by success.
- Required fix:
  - Make success terminalization re-check the current job state at the point of terminal write and convert to `CANCELLED` if cancellation has been requested.
  - Keep behavior shared by download and preprocess.
  - Add a focused race/ordering test proving a cancellation request immediately before success terminalization results in `CANCELLED`, not `SUCCEEDED`.

### F01-S3-002 - accepted

- Source: AgentDS.
- Severity: medium.
- File: `dayu/fins/ingestion_runtime.py:1054` and `dayu/fins/ingestion_runtime.py:1102`.
- Finding: `_mark_job_running_or_cancelled` returns existing terminal records unchanged, but callers only return early for `CANCELLED`. If a terminal `SUCCEEDED` or `FAILED` record is returned, the job can be executed again.
- Controller judgment: accepted. Even if the current public path makes this hard to reach, `_mark_job_running_or_cancelled` explicitly models terminal records. Callers must respect the full terminal set to keep the state machine closed and future-proof.
- Required fix:
  - In both download and preprocess runners, return immediately for any `_TERMINAL_STATUSES` record returned by `_mark_job_running_or_cancelled`.
  - Add focused coverage proving a pre-terminalized job is not executed again.

## Rejected Findings

### F01-S3-003 - rejected-with-reason

- Source: AgentMiMo.
- Severity: low.
- File: `tests/fins/test_fins_ingestion_runtime.py:40`.
- Finding: The test imports private `_StoreFileLock`.
- Controller judgment: rejected for S3 fix scope. This private import was introduced and accepted in the earlier S1 slice to verify file-lock failure resource cleanup. S3 did not introduce or expand that dependency. Reworking it now would be unrelated to the download runtime pipeline and would risk churn in already accepted job-store tests without improving S3 correctness.

## Deferred Findings

None.

## Required Validation For Fix Gate

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`

## Next Gate

Proceed to Slice S3 fix gate with AgentCodex. Do not commit, push, open PR, or enter re-review until the fix artifact is available.
