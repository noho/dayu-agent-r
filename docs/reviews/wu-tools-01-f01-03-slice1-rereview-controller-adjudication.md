# WU-TOOLS-01-F01-03 Slice 1 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: Slice 1 fix re-review
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice1-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice1-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-03-slice1-fix-codex.md`

## Re-Review Verdicts

- AgentMiMo: `fix-accepted`; 4/4 accepted findings fixed; 0 blocking findings.
- AgentDS: `pass`; 4/4 accepted findings fixed; 0 blocking findings.

Controller verdict: accepted findings fixed, but one controller-found follow-up fix is required before Slice 1 can be accepted.

## Accepted Finding Status

| Finding | Controller status |
|---|---|
| MIMO-S1 module docstring | fixed |
| MIMO-S2 `FinsIngestionJobRecord` docstring | fixed |
| DS-S1 `_save_cancelled` active-only atomic cancel terminal | fixed |
| DS-S2 upload request union exhaustiveness | fixed |

## Controller-Found Follow-Up

### CTRL-RR1: `_save_failed` still uses stale record overwrite instead of atomic current-state terminalization

- Source: Controller re-review after reading `docs/reviews/wu-tools-01-f01-03-slice1-rereview-ds.md`
- Severity: medium
- Controller decision: accepted
- Direct evidence:
  - `dayu/fins/ingestion_runtime.py` `_save_failed(...)` builds a failed terminal record from the caller-provided `record` and calls `self.job_store.save_job(...)`.
  - Background job paths read `latest`, check cancellation state, and then call `_save_failed(latest, ...)` for failed summaries. A concurrent caller can still call `request_cancel(job_id)` between that read/check and `_save_failed`落盘.
  - This is the same root cause as DS-S1: terminalization uses a stale active record and bypasses the job store's current-state decision under one lock.
- Why this belongs to Slice 1:
  - Slice 1 introduces upload long-transaction job foundation and new failed terminal paths: unsupported upload runner and upload runner exceptions.
  - Long transactions make cancel/fail races more likely; leaving `_save_failed` stale-record overwrite in place would carry the same cancellation correctness gap into later production upload slices.
- Required fix:
  - Add a job-store-level atomic method, or equivalent, that saves failed only when the current record is still active and otherwise returns the current terminal record or writes cancelled when cancellation has already been requested.
  - `_save_failed` must use that atomic current-state method instead of `save_job(record_with_failed_status)`.
  - Preserve existing semantics: if the current record is already terminal, return it; if current record is `CANCELLING` or `cancellation_requested=True`, write/return `CANCELLED`; otherwise write `FAILED` with the provided bounded `failure_summary` and `result_summary`.
  - Keep `save_cancelled_if_active` intact; do not collapse failed/cancelled semantics into `save_succeeded_or_cancelled`.
- Required tests:
  - Add a production-store test proving a stale active record passed to `_save_failed` cannot overwrite a current `CANCELLING` record; expected terminal result is `CANCELLED`, not `FAILED`.
  - Existing `test_save_cancelled_does_not_overwrite_current_terminal_record` must continue to pass.

## Fix Follow-Up Requirements

Allowed production files:

- `dayu/fins/ingestion_runtime.py`

Allowed test/doc files:

- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md` only if implementation changes require README sync after reading the target README update constraints
- `tests/README.md` only if test scope description changes require README sync after reading the target README update constraints
- `docs/reviews/wu-tools-01-f01-03-slice1-fix-followup-codex.md`

Required validation:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
- `source .venv/bin/activate && pyright`
- `git diff --check`
