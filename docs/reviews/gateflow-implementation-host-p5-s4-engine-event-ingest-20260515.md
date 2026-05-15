# Gateflow Implementation Artifact: Host P5-S4 EngineEvent Ingest

- **Gate**: Host Phase 5 P5-S4 EngineEvent Ingest Mapping And Terminal Closeout implementation
- **Role**: implementation worker
- **Accepted plan**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S4, §3.1, §3.5, §3.6
- **Design source**: `docs/host/design.md` §13.4, §17, §22
- **Status**: implementation completed with controlled scope expansion requiring controller / reviewer裁决

## Controlled Scope Expansion

- `dayu/host/durable/state.py` was not in the original P5-S4 allowed files.
- It was required because active cancel terminal closeout needs durable row CAS for `Attempt RUNNING -> CANCELLED` and `Run CANCELLING -> CANCELLED`.
- The state row owner is `dayu/host/durable/state.py`; implementing those CAS statements in `run_transition.py` would bypass the established durable state boundary and would be a worse root-cause fix.
- The `state.py` diff is intentionally limited to two row helper additions:
  - `cancel_cancelling_run_row(...)`
  - `cancel_running_attempt_row(...)`
- Controller / reviewer must explicitly裁决 this scope expansion before accepting the slice.

## Changed Files

- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/state.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `docs/reviews/gateflow-implementation-host-p5-s4-engine-event-ingest-20260515.md`

## Implemented Items

- Added Host-owned typed contracts:
  - `LocalEngineEnvelope`
  - `EngineEventCandidate`
  - `EngineEventIngestor`
  - `EngineIngestResult`
  - `EngineIngestStatus`
- Implemented event id derivation using:
  - `event-engine-` + `sha256_digest_json({execution_id, worker_event_index, event_class, event_type, sub_index}).removeprefix("sha256:")`
- Kept Engine public `EngineEvent` contract unchanged; Host attempt identity stays in Host envelope / durable state only.
- Added durable validation for envelope / EngineEvent `session_id` and `run_id`, UTC-aware `observed_at`, Run / Attempt / dispatch identity, stale execution, and terminal-late rejection.
- Implemented mappings:
  - `final_answer` -> `ATTEMPT_SUCCEEDED` + `RUN_SUCCEEDED`
  - `run_failed(recoverable=False)` -> `ATTEMPT_FAILED` + `RUN_FAILED`
  - `run_failed(recoverable=True)` -> diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED`, `unsupported_later_owner=phase10`
  - `context_compaction_requested(budget_state=None)` -> diagnostic + `FAILED`, `unsupported_later_owner=phase10`
  - `run_suspended` / `tool_awaiting` -> diagnostic + `FAILED`, `unsupported_later_owner=phase7`
  - `usage_reported` -> `EventClass.PROJECTION_SIGNAL / USAGE_REPORTED`, no state mutation
  - preview events -> `EventClass.PREVIEW`, no state mutation
  - provider protocol error -> diagnostic with raw payload descriptor support
- Implemented terminal summary SQLite payload descriptors for terminal closeout payload references.
- Implemented duplicate candidate detection before late-terminal rejection so replay returns existing result without adding canonical facts.
- Implemented worker lifecycle closeout helpers:
  - clean EOF without terminal -> `FAILED`, reason `stream_ended_without_terminal`
  - stream error / worker crash / terminal unknown -> `LOST`, reason `worker_lost_before_terminal`
- Added active cancel terminal primitive:
  - `run_cancelled` after active cancel -> `ATTEMPT_CANCELLED` + `RUN_CANCELLED`
  - closes Attempt / Run to `CANCELLED`
- Added narrow EventLog reader for latest run event by type to recover the active cancel request reference.
- Terminal closeout triggers typed queue promotion wakeup through `AdmissionWakeupPort`.

## Validation Result

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q`
  - Passed: `10 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Passed: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Passed

## Stop Conditions

- Did not modify Engine public contract or Engine code.
- Did not make EngineEvent carry Host attempt identity.
- Did not create unsupported recovery Attempt or move Run into `RECOVERING`.
- Did not implement RemoteProxy, ToolRuntime, WAITING, Recovery, or active cancel propagation.
- Blocking file-ownership issue found and handled as controlled scope expansion: `dayu/host/durable/state.py` is required for correct durable state CAS ownership. This requires controller / reviewer裁决.

## Docs Decision

- README trigger was detected for `dayu/host/` and `tests/` changes.
- Current worker handoff explicitly restricts writes to the assigned allowed files, and no README file is allowed.
- No README was modified to avoid violating file ownership.

## Residual Risks

- Dispatch scheduler still needs a later slice to call `EngineEventIngestor` from its worker event consumption loop; this slice only lands the Host-owned ingest service and tests it directly.
- Active cancel propagation to LocalProxy remains out of scope for P5-S4 and is not implemented here.
- Remote worker envelopes and replay / recovery semantics remain later-phase work.
