# WU-CLI-FINS-OBS-01 Slice C Re-review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: re-review (post-fix)
- Reviewer: AgentMiMo
- Date: 2026-06-16

## Review Scope

Re-review of the review fix applied on top of the Slice C implementation. The fix addresses two findings:

- `DS-C01`: runtime `_run_direct_stream` should guarantee "no silent ending" without relying on Service layer fallback
- `DS-C02`: `_put_direct_queue` cancel branch needs comment explaining event discard behavior

Files changed in fix:

- `dayu/fins/ingestion_runtime.py` — missing RESULT fallback + `_put_direct_queue` comment
- `tests/fins/test_fins_ingestion_runtime.py` — new `test_direct_stream_missing_result_returns_failure_result`

## Validation

- `pytest tests/fins/test_fins_ingestion_runtime.py -q` → 60 passed, 3 warnings
- `pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py` → 0 errors
- `git diff --check` → clean

## Review Checklist

### 1. Runtime direct stream still returns AsyncIterator[FinsEvent], producer silent ending produces unique FAILURE RESULT, no silent ending

**PASS**

- `download()` / `preprocess()` / `upload()` unchanged, still return `AsyncIterator[FinsEvent]`.
- `_run_direct_stream` consumer loop unchanged for normal path (progress → RESULT → exit).
- After the `while True` loop exits (via `break` from sentinel or `break` from `result_seen`), new code: `if not result_seen: yield _direct_missing_result_event(context)`.
- This means: if producer thread finishes (sentinel received) without any RESULT having been yielded, runtime itself emits one FAILURE RESULT before exiting. No silent `StopAsyncIteration` possible.
- `_direct_missing_result_event` produces a `FinsEvent(event_type=RESULT, status=FAILURE, exit_code=1, error_kind=EXECUTION, error_message="执行失败")`.
- Test `test_direct_stream_missing_result_returns_failure_result` uses a no-op producer (`quiet_producer` that does nothing), collects events, and asserts exactly `[RESULT]` with `status=FAILURE, exit_code=1`.

### 2. Failure RESULT does not leak job id/cursor/sidecar/path/raw payload

**PASS**

- `_direct_missing_result_event` uses only: `context.direct_operation_kind`, `context.normalized_ticker`, `_direct_filing_kind(context.source_kind)`, and bounded constants (`_DIRECT_FAILURE_TITLE`, `_DIRECT_ERROR_TEXT_FALLBACK`).
- `details=()` — empty tuple, no summary fields exposed.
- `document_label=None`.
- No reference to `job_id`, `sequence`, `cursor`, absolute path, raw payload, or financial document body.
- Consistent with the existing `_emit_direct_result` leakage guard pattern.

### 3. No job/durable/sidecar dependency introduced

**PASS**

- `_direct_missing_result_event` is a pure function of `_FinsIngestionExecutionContext` — constructs a `FinsEvent` directly, no job store access.
- `_run_direct_stream` does not call `start_*`, `read_job`, `read_job_events`, or `request_cancel` in the new fallback path.
- The fix only adds a `yield` statement and a module-level helper; no new imports, no new class dependencies.

### 4. asyncio.to_thread/thread/queue bridge remains internal bounded implementation detail

**PASS**

- `_run_direct_stream` thread/queue/bridge structure unchanged.
- `_put_direct_queue` unchanged except for added comment on the cancellation branch: `# consumer 已结束时丢弃后续事件，避免同步 producer 卡在无人读取的队列上。`
- Comment correctly documents the existing behavior: when `cancellation_state.is_cancelled()` (set by consumer's `finally` block), put returns `False` to unblock the producer's retry loop. This is a clarification, not a behavior change.
- Bridge still bounded: queue maxsize=32, 50ms timeouts, cancellation check per iteration.

### 5. Tests and pyright

**PASS**

- 60 passed (was 59 before fix; +1 new test).
- pyright 0 errors on touched files and full project.
- `git diff --check` clean.
- New test `test_direct_stream_missing_result_returns_failure_result` correctly exercises the edge case: silent producer → runtime-emitted FAILURE RESULT.

## Findings

No blocking findings. No new non-blocking observations.

## Conclusion

**PASS**

The review fix correctly addresses both `DS-C01` and `DS-C02`:

1. `_run_direct_stream` now guarantees "no silent ending" by yielding `_direct_missing_result_event` when producer exits without producing a RESULT. The fallback event is a pure FAILURE RESULT with bounded, non-leaking fields.
2. `_put_direct_queue` cancel branch now has a comment explaining the event-discard behavior as intentional cooperative cancellation design.

No new dependencies, no leakage, no architectural changes. The fix is minimal, correct, and well-tested.
