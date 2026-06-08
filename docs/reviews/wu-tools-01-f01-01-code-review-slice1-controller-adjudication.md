# WU-TOOLS-01-F01-01 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: code review
- Slice: Slice 1 - ingestion job store convergence
- Implementation artifact: `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice1-mimo.md`
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice1-ds.md`

## Verdict

Slice 1 code review passed with accepted fixes. No blocking functional issue was found, and both reviewers confirmed the implementation stayed inside Slice 1.

Next gate: `fix`.

## Finding Adjudication

### A1. `RuntimeFileLockError` missing from job store public method docstrings

- Source findings: MiMo F1; DS F1.
- Decision: accepted.
- Reason: Slice 1 changed lock acquire failure from private `_StoreFileLock` / `OSError` to `dayu.runtime.filelock.RuntimeFileLockError`. The six `FsFinsIngestionJobStore` public methods still document only filesystem `OSError` / `FileNotFoundError` / `ValueError` paths. AGENTS requires complete Chinese docstrings, and this is a current-slice contract readability issue.
- Required fix: import or otherwise reference `RuntimeFileLockError` as needed, and update `create_job`, `save_job`, `save_succeeded_or_cancelled`, `claim_running_or_cancelled`, `read_job`, and `request_cancel` docstrings to include file-lock acquire failure.

### A2. Coverage validation missing from implementation artifact

- Source finding: MiMo F2.
- Decision: accepted.
- Reason: The plan recommended coverage validation for modified production files, and the project coverage target is at least 80 percent per touched file. Controller ran the command and confirmed coverage is sufficient, but the implementation artifact should record it for durable gate evidence.
- Required fix: update `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md` with the coverage command and result.
- Controller evidence: `pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q` passed with `26 passed`, 3 existing edgar deprecation warnings, and `dayu/fins/ingestion_runtime.py` coverage `92%`.

## Rejected / Deferred Notes

- DS residual note about a dedicated lock-acquisition-failure test is not accepted as a current fix. Slice 1 removed the Fins-owned file descriptor lifecycle; runtime filelock owns acquire/release failure behavior and is already covered in runtime tests. Current Fins behavior tests and coverage are sufficient for this slice.
- Storage batch convergence and `dayu/fins/_file_lock.py` deletion remain deferred to Slice 2 and Slice 3 by plan.

## Residual Risks

- Storage batch runtime token lifecycle remains future Slice 2 work.
- Private Fins `_file_lock.py` deletion remains future Slice 3 work.
- No unclassified residual risk remains for Slice 1 code review.

## Validation

- Read both code review artifacts.
- Re-ran coverage command for `dayu.fins.ingestion_runtime`; result was 92 percent.
- Confirmed both reviewers reported 0 blocking findings and Slice 1 scope conformance.
