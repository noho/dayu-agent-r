# WU-CLI-FINS-OBS-01 Aggregate Deepreview Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: aggregate deepreview
- Review artifacts:
  - `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260615-205916.md`
  - `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260615-205638.md`
- Decision time: 2026-06-15 21:06:18 Asia/Shanghai

## Review Conclusion

AgentMiMo returned `PASS`. AgentDS returned `PASS-WITH-FINDINGS`.

Controller accepts three bounded fix items and rejects/defer the remaining low-risk observations to avoid expanding this work unit beyond its approved architecture and test scope.

## Accepted Fix Items

### AGG-FIX-01 Corrupted event sidecar line must not permanently break event observation

- Source finding: DS finding 1
- Severity: medium-low
- Decision: accepted
- Required fix:
  - When reading a Fins job event sidecar, malformed JSONL lines or invalid event rows must not make all future `read_job_events(...)` and `append_job_event(...)` calls fail for that job forever.
  - Skip invalid sidecar rows with a bounded warning that includes job-independent file context and line number, not payload values.
  - Preserve strict monotonic validation for valid records.
  - Add Fins runtime tests proving a corrupted sidecar row is skipped and a later append can still allocate the next valid sequence.

### AGG-FIX-02 CLI synthetic terminal fallback rendering coverage

- Source finding: DS finding 2
- Severity: low
- Decision: accepted
- Required fix:
  - Add CLI-level coverage for a Service-produced synthetic terminal fallback event.
  - The test must prove CLI rendering and exit-code behavior still work when `event_label="job_terminal_fallback"` and `terminal_result` is produced from the terminal job record fallback path.

### AGG-FIX-03 `_LOGGER` constant annotation consistency

- Source finding: DS finding 4
- Severity: low
- Decision: accepted
- Required fix:
  - Change `dayu/fins/ingestion_runtime.py` module logger annotation to `Final[logging.Logger]`.
  - Run pyright on affected files.

## Deferred Or Accepted-Risk Findings

| Source finding | Decision | Rationale |
| --- | --- | --- |
| DS finding 3 `_is_summary_key_allowed` conservative substring matching | accepted-risk | Current behavior over-redacts rather than leaks sensitive content. Tightening matching can increase leakage risk and needs a separate output-redaction policy review. |
| DS finding 5 synchronous `request_cancel` in SIGINT coroutine | deferred | Real only under extreme file-lock / filesystem stalls. Moving cancel to executor changes concurrency semantics and needs a dedicated cancel responsiveness design pass. |
| DS finding 6 `claim_running_or_cancelled` repeated RUNNING claim updates `updated_at` | deferred | Normal runtime submits a single background task. Fix is low risk but outside current live event/log/UI closeout unless a direct test proves user-visible impact. |
| DS finding 7 `_last_event_sequence_locked` O(N) append scan | deferred | This was already a known S1 scalability residual; current coarse progress event volume is bounded. Fine-grained high-frequency event streaming remains future scope. |
| DS finding 8 mutable `FINS_DIRECT_SERVICE_FACTORY` test seam | accepted-risk | Existing CLI tests rely on this injection point and current CLI command path is single-process/single-thread. No production bug in current scope. |

## Required Validation

After the aggregate fix, run:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q
source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py
git diff --check
```

If implementation touches README or broader tests, expand validation accordingly.
