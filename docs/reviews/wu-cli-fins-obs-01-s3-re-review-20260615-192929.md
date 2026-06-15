# WU-CLI-FINS-OBS-01 S3 Scoped Re-Review

## Scope

- Mode: scoped re-review (deepreview AgentDS)
- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S3-service-fins-direct-subscription`
- Gate: fix → re-review (post AgentCodex fix)
- Reviewed artifacts:
  - Adjudication: `docs/reviews/wu-cli-fins-obs-01-s3-code-review-adjudication-20260615-192410.md`
  - Fix report: `docs/reviews/wu-cli-fins-obs-01-s3-fix-codex.md`
  - AgentMiMo review: `docs/reviews/code-review-20260615-192103.md`
  - AgentDS review: `docs/reviews/code-review-20260615-191952.md`
- Reviewed files:
  - `dayu/service/fins_direct.py` — fix target
  - `tests/service/test_fins_direct.py` — test additions
- Excluded scope:
  - S3 design re-review (reviewed only for fix-introduced contradictions)
  - Deferred / non-actions: terminal fallback sidecar write-back, wait_for_terminal/stream mutual exclusion, CLI/Host/Engine/Fins runtime modifications
- Parallel review coverage: 无

## Verification Summary

| Check | Result |
|---|---|
| `pytest tests/service/test_fins_direct.py -q` | 17 passed |
| `pyright dayu/service/fins_direct.py tests/service/test_fins_direct.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Fix-by-Fix Verification

### S3-FIX-01: terminal event / job record inconsistency → runtime state error

**Adjudication requirement**: When terminal event arrives but `read_job` returns non-terminal record, raise an exception with runtime data inconsistency semantics (not `FinsDirectUsageError`). Normal terminal mapping unchanged. Test coverage required.

**Fix evidence**:

- `dayu/service/fins_direct.py:49-50` — New `FinsDirectRuntimeStateError(RuntimeError)` with Chinese docstring `"Fins direct runtime 持久化状态不一致。"`. Semantics clearly separate from `FinsDirectUsageError` (parameter error).
- `dayu/service/fins_direct.py:595-603` — In `_terminal_result_for_event`, non-terminal events still return `None` (line 595-596). Terminal events still call `read_job` (line 597). The new guard at lines 598-603 checks `_is_terminal_status(record.status)` **before** calling `_terminal_result`, raising `FinsDirectRuntimeStateError` with explicit `"terminal job event observed before terminal job record"` message including `job_id`, `event_sequence`, `event_type`, and `record_status`.
- `dayu/service/fins_direct.py:604` — Normal terminal path unchanged: `return _terminal_result(record)`.
- `dayu/service/fins_direct.py:661-683` — `_terminal_result` unchanged; its `FinsDirectUsageError` at line 676 now only fires for direct `wait_for_terminal` callers (correct — that path has no event involved).
- `tests/service/test_fins_direct.py:487-511` — `test_stream_job_events_reports_terminal_record_inconsistency`: terminal event (JOB_SUCCEEDED) + non-terminal record (RUNNING) → asserts `FinsDirectRuntimeStateError` with match `"terminal job event observed before terminal job record"`. Also asserts event_read_calls were made.

**Verdict**: ✅ FIXED. Exception semantics correctly changed from usage error to runtime state inconsistency. Normal terminal mapping preserved. Test coverage present.

### S3-FIX-02: negative after_sequence validation coverage

**Adjudication requirement**: Add focused test proving `stream_job_events_until_terminal(handle, after_sequence=-1)` fails fast with `FinsDirectUsageError`.

**Fix evidence**:

- `tests/service/test_fins_direct.py:470-484` — `test_stream_job_events_rejects_negative_after_sequence`:
  - Passes `after_sequence=-1` ✅
  - Asserts `FinsDirectUsageError` with `match="after_sequence"` ✅
  - Asserts `runtime.event_read_calls == []` — proves no runtime read (fail-fast) ✅
  - Uses `_unused_sleep` — proves sleep path not reached ✅

**Verdict**: ✅ FIXED. Fail-fast behavior proven with no runtime interaction.

### S3-FIX-03: terminal event read_job failure propagation coverage

**Adjudication requirement**: Add focused test proving that when `read_job_events` returns a terminal event and subsequent `read_job` fails, the failure propagates to the caller.

**Fix evidence**:

- `tests/service/test_fins_direct.py:513-533` — `test_stream_job_events_propagates_read_job_failure_after_terminal_event`:
  - Terminal event (JOB_FAILED) in event_batches with `read_job_error=LookupError("unknown job")` ✅
  - Asserts `LookupError` propagates with `match="unknown job"` ✅
  - Asserts `event_read_calls == [("job-1", 0, FINS_DIRECT_JOB_EVENT_READ_LIMIT)]` — proves terminal event was read before read_job failed ✅
  - Uses `_unused_sleep` — proves no fallback path reached ✅

**Verdict**: ✅ FIXED. Exception propagation from the terminal-event → read_job path is proven.

## AGENTS.md Compliance

- `FinsDirectRuntimeStateError` (line 49-50): Chinese docstring ✅, inherits `RuntimeError` ✅
- All three new test functions: Chinese docstrings ✅, `-> None` return type ✅, typed parameters ✅
- No `Any`, `object`, bare containers, or untyped signatures in new code ✅
- `FinsDirectRuntimeStateError` included in `__all__` (line 781) ✅

## Findings

未发现实质性问题。

All three accepted fixes (S3-FIX-01, S3-FIX-02, S3-FIX-03) are correctly implemented with no introduced regressions or contradictions with existing S3 design. No deferred / non-action boundary was crossed.

## Open Questions

无。

## Residual Risk

- `_terminal_result` at line 676 still raises `FinsDirectUsageError` for the direct non-terminal-record path. This is now only reachable via `wait_for_terminal` (no event involved), where usage-error semantics are appropriate. No action needed.
- The three new tests share the same fake runtime infrastructure as existing S3 tests; no new fake runtime capabilities were added. The existing `_FakeIngestionRuntime.read_job_error` was sufficient for S3-FIX-03 without conditional injection — this is correct because the fake's `read_job` always raises when `read_job_error` is set, and the test structure ensures `read_job` is only called once (by `_terminal_result_for_event` after the terminal event).

## Conclusion

**PASS** — 3/3 fixed.
