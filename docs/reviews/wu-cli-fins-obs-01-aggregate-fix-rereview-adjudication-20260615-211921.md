# WU-CLI-FINS-OBS-01 Aggregate Fix Re-Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: aggregate deepreview fix re-review
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260615-211431.md`
  - `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260615-211431.md`
- Decision time: 2026-06-15 21:19:21 Asia/Shanghai

## Decision

Aggregate fix is accepted.

Both reviewers returned `PASS`. `AGG-FIX-01`, `AGG-FIX-02`, and `AGG-FIX-03` are closed. Deferred / accepted-risk aggregate findings remain classified by `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md` and were not expanded during the fix pass.

## Closure Evidence

| Finding | Decision | Evidence |
| --- | --- | --- |
| `AGG-FIX-01` corrupted event sidecar row recovery | closed | `FsFinsIngestionJobStore._iter_event_records_locked(...)` skips malformed JSON rows, non-object JSON rows, and invalid event rows with bounded warnings; valid record sequence monotonicity remains strict; tests prove later append continues. |
| `AGG-FIX-02` CLI synthetic terminal fallback coverage | closed | CLI test now uses a Service-produced `event_label="job_terminal_fallback"` terminal event and verifies UI rendering, stream path, and exit code. |
| `AGG-FIX-03` `_LOGGER` Final annotation | closed | `dayu/fins/ingestion_runtime.py` now declares `_LOGGER: Final[logging.Logger]`; pyright is clean. |

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q`
  - Result: `83 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## Residual Risk

- `_last_event_sequence_locked` remains O(N) over valid sidecar rows; this is deferred as a future high-frequency event scalability concern, not a correctness blocker for coarse progress events.
- `_is_summary_key_allowed` remains conservative and may over-redact some business keys; this is accepted-risk because relaxing it can leak sensitive path/raw/content fields and needs a separate redaction-policy review.
- Synchronous cancel request in the CLI SIGINT coroutine remains deferred; fixing it would change cancel concurrency semantics and belongs in a dedicated cancel responsiveness work unit if needed.

## Next Entry Point

Proceed to work-unit closeout and draft PR gate preparation.
