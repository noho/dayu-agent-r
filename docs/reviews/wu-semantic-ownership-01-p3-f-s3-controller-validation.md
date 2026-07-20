# WU-SEMANTIC-OWNERSHIP-01 P3-F S3 Controller Validation

## Scope

- Slice: `P3-F S3 - Fins wait adapter deadline/expiry consumption`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s3-implementation-codex.md`
- Accepted S2 commit: `3b2779e4`

## Motivation Check

S3 motivation is current. The Fins wait adapter previously used its own created-at age window to convert transient observation unavailability into `WaitPollLost`. That put terminal wait timeout ownership in the adapter instead of the Host wait record. The fix correctly keeps Host wait record deadline/expiry as the boundary truth and makes the Fins adapter consume it.

## Controller Result

Ready for independent code review by AgentMiMo and AgentDS.

## Evidence Checked

- `_TRANSIENT_PENDING_MAX_SECONDS` and `_transient_pending_expired(...)` were removed.
- `_poll_error_result(...)` now calls `_wait_boundary_lost(...)` for `TRANSIENT_UNAVAILABLE`.
- `_wait_boundary_lost(...)` reads `deadline_at` first, then `expires_at`, matching `dayu/host/wait_callback.py:_stale_status_or_none`.
- Present invalid boundary text fails closed to lost.
- No Host boundary returns not-ready; old `created_at` alone no longer makes transient unavailable lost.
- Host wait creation evidence was inspected: `dayu/host/waiting.py:_wait_record_row` writes `deadline_at` from await spec and `expires_at=None`.
- README wait adapter contract was updated in `dayu/fins/README.md`.

## Commands Run

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `132 passed, 3 warnings in 4.55s`.
- `source .venv/bin/activate && rg -n '_TRANSIENT_PENDING_MAX_SECONDS|_transient_pending_expired' dayu tests`
  - Result: zero matches; `rg` exit code `1`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- Additional source scans confirmed `_timestamp_or_now(...)` remains used for observation handle timestamps, not transient timeout ownership.

## Propagation Audit

1. Host wait creation writes durable `deadline_at` and `expires_at`.
2. Fins adapter consumes those fields only when classifying transient unavailable.
3. Adapter output remains `WaitPollNotReady` or `WaitPollLost(_lost_outcome())`; no deadline/expires/id/governance text is projected to LLM-facing tool output.
4. Host wait resolution remains the terminal governance owner.

## Residual Risk

- No-boundary transient unavailable can remain not-ready until Host cancellation/close or future Host-owned boundary; this is intended by the owner boundary.
- `expires_at` is currently `None` in Host creation but supported for future Host-owned expiry truth.
