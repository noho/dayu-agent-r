# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Fix

S2 fix gate complete.

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization`
- Slice: `S2 - Fatal protocol error vs non-fatal provider diagnostic`
- Gate: fix after S2 code review
- Agent: AgentCodex
- Branch: `phaseflow/host-issues-control`
- Fixed findings: `P3-D-S2-CR-F01`, `P3-D-S2-CR-F02`
- Not fixed by instruction: `P3-D-S2-CR-F03`
- Non-goals kept: no re-review, no aggregate review, no PR, no commit, no push, no merge.

## Owner Boundary

- Fatal provider protocol error fact is first produced by Runner protocol validation and persisted by Host ingest as `PROVIDER_PROTOCOL_ERROR`.
- Non-fatal provider diagnostic fact is first produced by provider adapter / Runner diagnostic normalization and persisted by Host ingest as `PROVIDER_DIAGNOSTIC`.
- Host Read API owns UI / Service-facing `HostActivityView` semantics and must expose fatal vs non-fatal provider facts without forcing consumers to infer from a shared kind.
- Agent owns Runner HTTP error to Engine event projection; typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` remains the source of `context_compaction_requested`.

## Fixes

### P3-D-S2-CR-F01

- Added `HostActivityKind.PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`.
- Updated Read API `PROVIDER_PROTOCOL_ERROR` projection to use `HostActivityKind.PROVIDER_PROTOCOL_ERROR` and `HostActivityStatus.FAILED`.
- Kept non-fatal `PROVIDER_DIAGNOSTIC` projection on `HostActivityKind.PROVIDER_DIAGNOSTIC`.
- Changed non-fatal provider diagnostic activity status from `HostActivityStatus.COMPLETED` to existing `HostActivityStatus.INFO`.
- Updated Service entrypoint activity mapping with `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`, so the public activity kind remains intact through the direct UI adapter boundary.
- Updated Host activity tests and added Service entrypoint activity regression coverage.

### P3-D-S2-CR-F02

- Added explicit Agent regression test for `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)`.
- The test asserts the Engine event stream contains `CONTEXT_COMPACTION_REQUESTED` and does not contain `PROVIDER_DIAGNOSTIC`.

## Files Changed By This Fix Gate

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/service/entrypoint_runtime.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/engine/test_agent_phase2.py`
- `tests/service/test_entrypoint_runtime.py`
- `dayu/host/README.md`
- `docs/host/design.md`
- `docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-codex.md`

## Validation

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/host/test_host_activity_event_projection.py -q`
  - Result: `83 passed in 0.50s`
- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q`
  - Result: `131 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py -q`
  - Result: `164 passed in 1.51s`
- Additional affected Service validation:
  - `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py -q`
  - Result: `43 passed, 3 warnings in 2.06s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed a tool version update notice.
- `git diff --check`
  - Result: passed.

## README / Docs Decision

- `dayu/host/README.md` was updated because `dayu/host/` public Read API activity contract changed.
- `docs/host/design.md` was updated to keep the design source aligned with the Host diagnostic event and activity distinction.
- `dayu/engine/README.md` was checked by trigger; no update was needed for this fix because Agent behavior was not changed, only a missing regression test was added for existing behavior.
- `tests/README.md` was checked by trigger; no update was needed because the added tests stay inside existing Engine / Host / Service test layers and do not introduce a new test layer or command policy.
- Root `README.md` and `dayu/README.md` were not updated because this fix does not change user-visible commands, workspace layout, installation flow, or layer boundaries.

## Propagation Audit Delta

- Fatal path: Runner protocol validation emits fatal provider protocol error -> Agent emits `EngineEventType.PROVIDER_PROTOCOL_ERROR` with failure candidate -> Host ingest persists `PROVIDER_PROTOCOL_ERROR` diagnostic/failure payload -> Read API now projects `HostActivityKind.PROVIDER_PROTOCOL_ERROR` / `FAILED` -> Service entrypoint preserves `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR` for UI adapters.
- Non-fatal path: provider adapter / Runner emits `PROVIDER_DIAGNOSTIC` -> Agent emits `EngineEventType.PROVIDER_DIAGNOSTIC` without failure candidate -> Host ingest persists `PROVIDER_DIAGNOSTIC` as `EventClass.DIAGNOSTIC` with no terminal state or failure metadata -> Read API projects `HostActivityKind.PROVIDER_DIAGNOSTIC` / `INFO` -> Tool Trace remains diagnostic-only -> Outbox, memory, final answer, accepted evidence material, compact material and LLM-facing prompts remain non-consumers.
- Context overflow `detection=None` path: Runner typed HTTP error `CONTEXT_LENGTH_EXCEEDED` -> Agent emits only `CONTEXT_COMPACTION_REQUESTED` before terminal recoverable failure -> no provider diagnostic provenance event is produced.

## Residual Risk

- S3 typed Engine error-code contract remains out of scope.
- `P3-D-S2-CR-F03` remains rejected-with-reason and was not changed.
- Pre-existing broader workspace modifications and unrelated untracked files were left untouched.

