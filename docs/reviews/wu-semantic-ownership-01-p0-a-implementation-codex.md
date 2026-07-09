# WU-SEMANTIC-OWNERSHIP-01 P0-A Implementation Artifact

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P0-A`
- Agent: AgentCodex
- Date: 2026-07-09
- Scope: finish reason authority cleanup; usage `provider_request_id` propagation
- Commit/push: not performed

## S0 Root-Cause Confirmation

Consumer scan commands:

- `rg -n "RunnerContentCompletedData|ContentCompleteData|finish_reason" dayu/engine dayu/host tests`
- `rg -n "RunnerContentCompletedData\\(|ContentCompleteData\\(|content_completed|RUNNER_CONTENT_COMPLETED|CONTENT_COMPLETED|state\\.finish_reason|runner_content_completed|data\\.finish_reason" dayu/engine dayu/host tests/engine tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace*.py`
- Final verification scan: `source .venv/bin/activate && rg -n "ContentCompleteData\\(.+finish_reason|RunnerContentCompletedData\\(.+finish_reason|\\.finish_reason" dayu/engine dayu/host tests`

Scan summary:

- Construction points before fix:
  - `RunnerContentCompletedData.finish_reason`: `dayu/engine/contracts/runner_events.py`, `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/non_stream_parser.py`, Agent/test fixtures.
  - `ContentCompleteData.finish_reason`: `dayu/engine/contracts/engine_events.py`, `dayu/engine/agent.py`, Host ingest tests.
- Production consumers before fix:
  - `dayu/engine/agent.py`: copied content-completed finish reason into iteration state, projected it to `ContentCompleteData`, and preferred it over `RunnerDoneData.finish_reason` on mismatch.
  - `dayu/host/engine_ingest.py`: projected content-completed finish reason into preview/audit payload.
- Expected tests:
  - Engine/Runner contract tests, OpenAI parser parity tests, Agent tests, Host ingest fixture tests.
- Stop-condition check:
  - No unexpected production consumer beyond the already adjudicated `dayu/host/engine_ingest.py` preview/audit consumer was found.
  - Final scan has no `ContentCompleteData(... finish_reason=...)` or `RunnerContentCompletedData(... finish_reason=...)` constructor hits. Remaining `.finish_reason` hits are RunnerDone / IterationCompleted / final answer / terminal facts or their tests.

## Owner Boundary

- Fact producer: OpenAI-compatible Runner parser extracts provider finish reason and provider response request id.
- Finish reason authority: `RunnerDoneData.finish_reason`; Engine projection authority is `IterationCompletedData.finish_reason`.
- Content-completed boundary: `RunnerContentCompletedData` / `ContentCompleteData` only carry completed content and reasoning material.
- Usage identity authority: `RunnerUsageRecordedData.provider_request_id` carries the provider response request id with usage; Agent maps it to `UsageReportedData.provider_request_id`.
- Durable owner: Host ingest writes usage `provider_request_id` into `USAGE_REPORTED` projection payload and usage observation diagnostic.
- Projection: Host content-completed preview/audit no longer exposes finish reason; finish reason remains available from iteration completed and terminal/final-answer facts.

## Changes

- Removed `finish_reason` from `RunnerContentCompletedData` and `ContentCompleteData`.
- Removed Agent content-completed finish reason state write, projection, mismatch warning, and earlier-state override.
- Kept Agent iteration classification reading finish reason only from `RunnerDoneData`.
- Added `provider_request_id: str | None` to `RunnerUsageRecordedData` and `UsageReportedData`.
- Propagated usage provider request id in SSE and non-stream OpenAI parser, Agent event projection, Host usage payload, usage diagnostic, and invalid-observation digest.
- Removed Host content-completed preview/audit `finish_reason`.
- Updated affected Engine/Host tests and README files:
  - `dayu/engine/README.md`
  - `dayu/host/README.md`
  - `tests/README.md`

## Propagation Audit

Finish reason path:

- Provider response `choices[].finish_reason` -> OpenAI parser internal mapped finish reason.
- Parser emits `RunnerDoneData.finish_reason`.
- Agent accepts `RunnerDoneData.finish_reason`, writes `_IterationState.finish_reason`, and emits `IterationCompletedData.finish_reason`.
- Agent final-answer / tool-call / error classification uses `_IterationState.finish_reason`.
- Host terminal/final-answer and iteration-completed preview paths preserve finish reason.
- Content-completed Runner/Engine events and Host content preview no longer carry finish reason.

Usage identity path:

- Provider response header -> OpenAI Runner `provider_request_id`.
- SSE parser emits `RunnerUsageRecordedData(..., provider_request_id=...)` for stream usage chunks.
- Non-stream parser emits `RunnerUsageRecordedData(..., provider_request_id=...)` for response usage.
- Agent emits `UsageReportedData(..., provider_request_id=...)`.
- Host ingest writes `provider_request_id` to `USAGE_REPORTED` payload.
- Host usage observation diagnostic and invalid digest are built from the same `data.provider_request_id`.

## Validation

- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_agent_phase3_tool_call.py`
  - Result: failed with 301 passed / 1 failed.
  - Failure: `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes` expected `stream_idle.heartbeat` debug log; rerun of that single test failed the same way. The event stream completed successfully and no HTTP error occurred. This is outside P0-A finish reason / usage identity paths.
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace*.py`
  - Result: failed with 113 passed / 5 failed.
  - Failures are waiting-confirmation canonical tool event count assertions; actual count is expected + 1. These failures are outside P0-A usage/content-completed paths.
- Additional focused validation:
  - `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -k usage_reported`
  - Result: 5 passed.
  - `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace*.py`
  - Result: failed with 196 passed / 6 failed; one pre-existing EngineEvent contract field-lock failure for `IterationStartedData.input_projection`, plus the same five Host waiting-confirmation count failures.
- `source .venv/bin/activate && rg -n "ContentCompleteData\\(.+finish_reason|RunnerContentCompletedData\\(.+finish_reason|\\.finish_reason" dayu/engine dayu/host tests`
  - Result: passed for P0-A invariant: no content-completed finish reason constructor hits; remaining `.finish_reason` hits are legitimate RunnerDone / IterationCompleted / final / terminal paths.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.
- `python -m compileall -q dayu/engine dayu/host tests/engine tests/host/test_engine_ingest_mapping.py`
  - Result: passed.

## README Decision

- `dayu/engine/README.md`: updated because Engine event/Runner contract changed. It now states usage provider request id propagation and that finish reason belongs to `runner_done` / `iteration_completed`, not content-completed events.
- `dayu/host/README.md`: updated because Host usage durable payload / diagnostic behavior changed. It now states Host writes Engine usage provider id and does not substitute client correlation id.
- `tests/README.md`: updated because tests now lock content-completed finish reason exclusion and usage provider request id fields.

## Residual Risk

- The two requested broad pytest commands are not fully green due to failures outside P0-A:
  - OpenAI stream idle heartbeat log assertion.
  - Host waiting-confirmation canonical tool event count assertions.
- These failures should be triaged by their current owner before declaring the full requested validation matrix green. They do not indicate a P0-A propagation failure; focused usage propagation tests, pyright, compileall, grep invariant, and diff check passed.
- `docs/engine/design.md` and `docs/host/design.md` were read as required but not modified because P0-A allowed files only included README sync, not design-doc edits.

## Completion Status

P0-A code implementation is complete within the allowed production modules. Full validation is partially blocked by unrelated existing test failures listed above.
