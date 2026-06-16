# WU-CLI-FINS-OBS-01 Slice C Code Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: code review
- Reviewer: AgentMiMo
- Date: 2026-06-16

## Design Sources

- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- `docs/host/issues-implementation-control.md`
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-slice-c-implementation-codex.md`

## Scope

Changed files:

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/README.md`

## Validation

- `pytest tests/fins/test_fins_ingestion_runtime.py -q` → 59 passed, 3 warnings
- `pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py` → 0 errors
- `pyright dayu/ tests/ utils/` → 0 errors
- `git diff --check` → clean

## Review Checklist

### 1. Direct download/preprocess/upload returns AsyncIterator[FinsEvent], produces progress + unique RESULT, no silent ending

**PASS**

- `download()` (line 1915), `preprocess()` (line 1952), `upload()` (line 1988) all return `AsyncIterator[FinsEvent]`.
- They delegate to `_run_direct_stream()` (line 2019) which uses bounded queue + daemon thread producer bridge.
- Each producer (`_produce_direct_download` line 2127, `_produce_direct_preprocess` line 2184, `_produce_direct_upload` line 2246) emits progress events and exactly one terminal RESULT.
- `_run_direct_stream_producer` (line 2095) wraps producer execution in try/except: any exception is converted to `RESULT(status=FAILURE)` with classified error kind and safe error message. The `finally` block always sends `_DirectStreamProducerDone()` sentinel.
- Consumer loop in `_run_direct_stream` (line 2073) has `result_seen` guard ensuring at most one RESULT is yielded. After RESULT or sentinel, loop exits.
- Tests `test_direct_download_stream_writes_storage_and_does_not_create_job_record` and `test_direct_download_unsupported_source_returns_failure_result` verify progress → unique RESULT ordering and failure RESULT for unsupported source.

### 2. Direct path does not call start_*, does not create durable job record, does not write job event sidecar, does not depend on job id/sequence/cursor

**PASS**

- `_produce_direct_download` calls `self._execute_download_request(context, ...)` directly — no `start_download` call.
- `_produce_direct_preprocess` calls `self._execute_preprocess_request(context, request)` directly — no `start_preprocess` call.
- `_produce_direct_upload` calls `self.upload_runner.run_upload(...)` directly — no `start_upload` call.
- `_emit_context_progress` (line 3679) routes by `context.job_record is not None`: legacy path writes sidecar; direct path constructs `FinsEvent` and puts into `direct_queue`.
- `_emit_direct_result` (line 3717) only operates when `context.direct_queue is not None`; it never touches job store.
- Test `test_direct_download_stream_writes_storage_and_does_not_create_job_record` explicitly asserts `executor.operations == []`, `tuple(jobs_dir.glob("*.json")) == ()`, `tuple(jobs_dir.glob("*.jsonl")) == ()`.

### 3. Old job store/read_job/read_job_events/request_cancel only retained for awaiting legacy path, not used by CLI/Service direct path

**PASS**

- `start_download` / `start_preprocess` / `start_upload` / `read_job` / `read_job_events` / `request_cancel` remain on `FinsIngestionRuntime` (lines 2329–2561). These are the legacy awaiting job path API, still needed by tools and wait adapter.
- Direct path uses `_run_direct_stream` → producer thread → `_emit_context_progress` / `_emit_direct_result` → `direct_queue`. Zero calls to `start_*`, `read_job`, `read_job_events`, or `request_cancel` in the direct stream code path.
- `_FinsIngestionExecutionContext` (line 1172) uses `job_record is None` vs `direct_queue is None` to distinguish paths; the two paths share business helpers but have separate event and cancellation truth sources.
- `_job_execution_context` (line 2811) constructs context from legacy job record with `direct_queue=None`; direct stream constructs context with `job_record=None`.
- Implementation artifact confirms: "direct path 不调用 `start_*`，不创建 durable queued job record，不写 job event sidecar".

### 4. Internal producer thread / queue / asyncio.to_thread bridge is bounded, runtime implementation detail, not exposed, does not claim strong cancellation

**PASS — with non-blocking observation**

- `_DIRECT_EVENT_QUEUE_MAX_SIZE = 32` (line 161): bounded queue.
- `_DIRECT_QUEUE_GET_TIMEOUT_SECONDS = 0.05` / `_DIRECT_QUEUE_PUT_TIMEOUT_SECONDS = 0.05` (lines 162–163): bounded timeouts.
- `_put_direct_queue` (line 3826) checks `cancellation_state.is_cancelled()` before each put attempt; returns `False` if cancelled.
- `_direct_queue_get` (line 3800) returns `_DirectStreamProducerDone()` sentinel when thread is dead and queue is empty.
- Thread is `daemon=True` (line 2068): does not prevent process exit.
- `asyncio.to_thread` (line 2076) bridges sync queue.get to async consumer; only one call site.
- Bridge is purely internal to `_run_direct_stream` and `_run_direct_stream_producer`; not in any protocol, Service boundary, tool schema, or README.
- `_DirectStreamCancellationState` (line 1083) is process-local, Lock-guarded, not exported.
- `_DirectCancellationChecker` (line 1139) is frozen dataclass, only composes external `CancellationToken` and local `_DirectStreamCancellationState`.
- Cancellation is best-effort cooperative: adapter/runner only observe at cancellation checker call sites; if a sync adapter blocks without checking, cancellation waits for the next checker or natural return.
- Implementation artifact explicitly states: "取消是 best-effort cooperative：adapter/runner 只有在调用 cancellation checker 或自然返回时才能收口".

**Observation F1 (non-blocking, informational):** `_put_direct_queue` has a `while True` retry loop on `Full` with 50ms timeout. Under extreme backpressure (consumer stalled, producer generating many events), this creates a CPU spin. The bounded queue size (32) and cancellation check limit the blast radius, but it is worth noting as a design limitation until adapters become async.

### 5. Cancellation, exception, unsupported source, upload failure, leakage guard, storage repository boundary

**PASS**

**Cancellation:**
- `_DirectCancellationChecker.__call__` (line 1146): checks local `_DirectStreamCancellationState` then external `CancellationToken`.
- `_produce_direct_download` / `_produce_direct_preprocess` / `_produce_direct_upload` all check `context.cancellation_checker()` after execution and emit `_emit_direct_cancelled_result` (line 3717) with `FinsResultStatus.CANCELLED`, `exit_code=130`, `FinsErrorKind.CANCELLED`.
- `_run_direct_stream` finally block (line 2092) always calls `cancellation_state.request_cancel()`, ensuring producer observes cancellation when consumer exits.
- Test `test_direct_download_uses_operation_scoped_cancellation_token` verifies `_CancelOnSecondCheckToken` → `RESULT(status=CANCELLED, exit_code=130)`.

**Exception handling:**
- `_run_direct_stream_producer` (line 2095) catches all `Exception` in producer, converts to `RESULT(status=FAILURE)` via `_classify_direct_error` (line 3848) and `_safe_direct_error_message` (line 3868).
- `_classify_direct_error` maps: `_UnsupportedDownloadSourceError | ValueError | FileNotFoundError` → `USER_INPUT`, `OSError` → `STORAGE`, `RuntimeError` → `EXECUTION`, default → `UNKNOWN`.

**Unsupported source:**
- `_produce_direct_download` relies on `_execute_download_request` which raises `_UnsupportedDownloadSourceError` for unknown adapters; caught by `_run_direct_stream_producer` and converted to `RESULT(status=FAILURE)`.
- Test `test_direct_download_unsupported_source_returns_failure_result` verifies `FAILURE` result with "不支持的下载来源" error message.

**Upload failure:**
- `_produce_direct_upload` (line 2274): `self.upload_runner is None` → `RESULT(status=FAILURE)` with `_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE`.
- After upload completes (line 2310): `summary.status.strip().lower() == "failed"` → `RESULT(status=FAILURE)`.
- Test `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text` verifies SUCCESS result and no path/payload leakage.

**Leakage guard:**
- `_safe_direct_error_message` (line 3868): strips path separators, job_id, cursor, raw payload references; falls back to `"{_DIRECT_ERROR_TEXT_FALLBACK}: {type(exc).__name__}"`.
- `_direct_document_label` (line 3809): uses `_bounded_text` with `reject_path_separators=False`.
- `_direct_progress_event` (line 3776): constructs `FinsEvent` with bounded fields; `document_label` uses `_direct_document_label`.
- Direct events never include `job_id`, `sequence`, `cursor`, absolute paths, raw provider payloads, or financial document body text.
- Test `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text` asserts `str(tmp_path) not in event_text`, `"finsjob_" not in event_text`, `"raw provider payload" not in event_text`.

**Storage repository boundary:**
- All storage writes go through `self.source_repository`, `self.blob_repository`, `self.filing_maintenance_repository`, `self.processed_repository` — the same `dayu.fins.storage` protocols used by legacy path.
- Direct path does not bypass or duplicate storage access; it uses the same `_execute_download_request` / `_execute_preprocess_request` helpers that go through repository protocols.

### 6. README impact and tests compliance

**PASS**

- `tests/README.md` updated: CLI Fins direct description changed from `request_cancel(job_id)` to "operation-scoped async cancellation"; Service Fins direct description updated to `AsyncIterator[FinsEvent]` pass-through; runtime description updated with direct stream coverage.
- Implementation artifact confirms `dayu/fins/README.md` was read but not edited (Slice E responsibility).
- Tests cover: direct download stream writes storage, no durable job record, unsupported source failure RESULT, operation-scoped cancellation, upload leakage guard.
- Legacy job store tests preserved as regression protection for awaiting path.

## Findings Summary

| ID | Severity | Blocking | File:Line | Description |
|---|---|---|---|---|
| F1 | informational | no | `ingestion_runtime.py:3826` | `_put_direct_queue` `while True` retry on `Full` with 50ms timeout creates CPU spin under extreme backpressure; bounded by queue size and cancellation check but worth noting as design limitation until adapters become async |

## Residual Risks

- **`dayu/fins/README.md` durable job descriptions:** Still contains durable Fins job development handbook text; Slice E is responsible for synchronization. Covered by later approved slice.
- **Tools awaiting / wait adapter:** Still depend on old `job_store` / `read_job_events` / `request_cancel`. Covered by later approved slice: Slice D lightweight observation handle migration.
- **Blocking adapter cancellation:** Best-effort cooperative only; adapter/runner must call cancellation checker or naturally return. Assigned to current design limitation until adapters are async-capable, fixed by test.

## Conclusion

**PASS**

The Slice C implementation correctly converges the Fins ingestion runtime core API:

1. Direct `download` / `preprocess` / `upload` methods return `AsyncIterator[FinsEvent]` with progress events and exactly one terminal RESULT; no silent ending.
2. Direct path does not call `start_*`, does not create durable job records, does not write job event sidecars, does not depend on job id / sequence / cursor.
3. Old job store / `read_job` / `read_job_events` / `request_cancel` are retained only for the awaiting legacy path; CLI / Service direct path does not use them.
4. Internal producer thread / queue / `asyncio.to_thread` bridge is bounded (maxsize=32, 50ms timeouts), is purely a runtime implementation detail, is not exposed externally, and does not claim strong cancellation.
5. Cancellation, exception handling, unsupported source, upload failure, leakage guard, and storage repository boundary are all correctly implemented.
6. README impact assessment and test updates are compliant.

No blocking findings. One non-blocking informational observation (F1) regarding busy-wait under extreme queue backpressure.
