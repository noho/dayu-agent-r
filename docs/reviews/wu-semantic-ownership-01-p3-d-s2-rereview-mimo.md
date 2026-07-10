# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Re-Review

## Scope

- Mode: re-review of S2 fix gate
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization`
- Slice: `S2 - Fatal protocol error vs non-fatal provider diagnostic`
- Branch: `phaseflow/host-issues-control`
- Re-review date: 2026-07-10 23:47:24
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-rereview-mimo.md`
- Included scope: S2 fix artifact validation, accepted findings F01 and F02 closure verification
- Excluded scope: P3-D-S2-CR-F03 (rejected finding, not fix target)
- Parallel review coverage: 无

## Re-Review Checklist

### 1. F01: fatal PROVIDER_PROTOCOL_ERROR activity is no longer projected as HostActivityKind.PROVIDER_DIAGNOSTIC

**Status: FIXED**

Direct evidence:

1. **HostActivityKind enum** (`dayu/host/api.py:2537`):
   - `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"` 已添加
   - `PROVIDER_DIAGNOSTIC = "provider_diagnostic"` 保留

2. **Read API projection** (`dayu/host/read_api.py`):
   - Fatal path (line 1434-1435): `kind=HostActivityKind.PROVIDER_PROTOCOL_ERROR`, `status=HostActivityStatus.FAILED`
   - Non-fatal path (line 1462-1463): `kind=HostActivityKind.PROVIDER_DIAGNOSTIC`, `status=HostActivityStatus.INFO`

3. **Service entrypoint mapping** (`dayu/service/entrypoint_runtime.py:1289-1292`):
   - `HostActivityKind.PROVIDER_DIAGNOSTIC` → `EntrypointActivityKind.PROVIDER_DIAGNOSTIC`
   - `HostActivityKind.PROVIDER_PROTOCOL_ERROR` → `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`

4. **EntrypointActivityKind enum** (`dayu/service/entrypoint_runtime.py:103-104`):
   - `PROVIDER_DIAGNOSTIC = "provider_diagnostic"`
   - `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`

5. **HostActivityStatus.INFO** (`dayu/host/api.py:2552`):
   - `INFO = "info"` 已添加用于非致命诊断

6. **Test coverage**:
   - `test_provider_protocol_error_activity_is_bounded` (`tests/host/test_host_activity_event_projection.py:582-609`):
     - Asserts `activity.kind is HostActivityKind.PROVIDER_PROTOCOL_ERROR` (line 603)
     - Asserts `activity.status is HostActivityStatus.FAILED` (line 604)
   - `test_provider_diagnostic_activity_is_nonfatal` (`tests/host/test_host_activity_event_projection.py:612-641`):
     - Asserts `activity.kind is HostActivityKind.PROVIDER_DIAGNOSTIC` (line 634)
     - Asserts `activity.status is HostActivityStatus.INFO` (line 635)
   - `test_submit_entrypoint_turn_preserves_provider_protocol_error_activity` (`tests/service/test_entrypoint_runtime.py:833-865`):
     - Asserts `activity.kind is EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR` (line 863)
     - Asserts `activity.status is EntrypointActivityStatus.FAILED` (line 864)

**Conclusion**: Fatal `PROVIDER_PROTOCOL_ERROR` is now projected with its own `HostActivityKind.PROVIDER_PROTOCOL_ERROR` and `HostActivityStatus.FAILED`. Non-fatal `PROVIDER_DIAGNOSTIC` remains on `HostActivityKind.PROVIDER_DIAGNOSTIC` with `HostActivityStatus.INFO`. Service entrypoint preserves the distinction. All assertions pass.

### 2. F02: context overflow CONTEXT_LENGTH_EXCEEDED with context_overflow_detection=None has explicit regression coverage

**Status: FIXED**

Direct evidence:

1. **Test implementation** (`tests/engine/test_agent_phase2.py:871-912`):
   - Test name: `test_context_overflow_without_detection_emits_only_compaction_request`
   - Input: `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)` (line 879-886)
   - Assertion: event stream contains `CONTEXT_COMPACTION_REQUESTED` (line 901-906)
   - Assertion: `EngineEventType.PROVIDER_DIAGNOSTIC not in {event.type for event in events}` (line 907-909)
   - Assertion: compact event data is `ContextCompactionRequestedData` with correct `provider_request_id` (line 910-912)

2. **Agent implementation** (`dayu/engine/agent.py:1617-1622`):
   - `if detection is None or detection.kind is not ContextOverflowDetectionKind.MESSAGE_MARKER_FALLBACK:` short-circuits to return `(compaction_event,)` only
   - No diagnostic event produced when `detection=None`

**Conclusion**: Explicit regression test exists and passes. `CONTEXT_LENGTH_EXCEEDED` with `context_overflow_detection=None` produces only `CONTEXT_COMPACTION_REQUESTED` and no `PROVIDER_DIAGNOSTIC`.

### 3. No new semantic ownership drift, public contract mismatch, reverse dependency, LLM-facing leakage, or test weakening introduced by fix

**Status: VERIFIED**

Direct evidence:

1. **Semantic ownership**:
   - Runner protocol validation produces fatal `PROVIDER_PROTOCOL_ERROR` → Agent emits `EngineEventType.PROVIDER_PROTOCOL_ERROR` with failure candidate → Host ingest persists `PROVIDER_PROTOCOL_ERROR` → Read API projects `HostActivityKind.PROVIDER_PROTOCOL_ERROR` / `FAILED` → Service entrypoint preserves `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`
   - Provider adapter / Runner produces non-fatal `PROVIDER_DIAGNOSTIC` → Agent emits `EngineEventType.PROVIDER_DIAGNOSTIC` without failure candidate → Host ingest persists `PROVIDER_DIAGNOSTIC` as `EventClass.DIAGNOSTIC` → Read API projects `HostActivityKind.PROVIDER_DIAGNOSTIC` / `INFO`
   - No downstream semantic reconstruction or fallback patterns introduced

2. **Public contract**:
   - `HostActivityKind` enum extended with `PROVIDER_PROTOCOL_ERROR` (backward compatible addition)
   - `HostActivityStatus` enum extended with `INFO` (backward compatible addition)
   - `EntrypointActivityKind` enum extended with `PROVIDER_PROTOCOL_ERROR` (backward compatible addition)
   - No breaking changes to existing public interfaces

3. **Reverse dependencies**:
   - `grep -n "from dayu.host" dayu/engine/` returns empty
   - `grep -n "from dayu.service" dayu/host/` returns empty
   - No reverse import violations introduced

4. **LLM-facing leakage**:
   - `grep -r "PROVIDER_PROTOCOL_ERROR" dayu/config/` returns empty
   - `grep -r "PROVIDER_DIAGNOSTIC" dayu/config/` returns empty
   - No internal diagnostic terms exposed to LLM prompts

5. **Test weakening**:
   - No assertions removed or weakened
   - No test fixtures modified to accommodate implementation
   - All existing tests pass without modification
   - New tests added for regression coverage

6. **Type safety**:
   - pyright: `0 errors, 0 warnings, 0 informations`
   - `git diff --check`: passed

**Conclusion**: No new semantic ownership drift, public contract mismatch, reverse dependency, LLM-facing leakage, or test weakening introduced.

### 4. Validate docs/README changes are necessary and accurate

**Status: VERIFIED**

Direct evidence:

1. **`dayu/host/README.md`**:
   - Added paragraph explaining `PROVIDER_DIAGNOSTIC` as non-fatal diagnostic with `provider_diagnostic` / `info` activity (line 411-412)
   - Added paragraph explaining fatal `PROVIDER_PROTOCOL_ERROR` uses independent `provider_protocol_error` activity kind (line 411-412)
   - Necessary: Host public Read API activity contract changed, README must document the distinction
   - Accurate: matches implementation (`HostActivityKind.PROVIDER_PROTOCOL_ERROR` vs `HostActivityKind.PROVIDER_DIAGNOSTIC`)

2. **`docs/host/design.md`**:
   - Added `PROVIDER_DIAGNOSTIC` to EngineEvent list (line 1515-1518)
   - Added `PROVIDER_DIAGNOSTIC` to diagnostic event list (line 1527-1533)
   - Added canonical event contract matrix row for `PROVIDER_DIAGNOSTIC` (line 1558-1560)
   - Added event type mapping `provider_diagnostic -> PROVIDER_DIAGNOSTIC` (line 1622-1624)
   - Necessary: design source must align with Host diagnostic event distinction
   - Accurate: matches implementation behavior (diagnostic only, no Run/Attempt terminal state change, no failure metadata)

3. **`dayu/engine/README.md`**:
   - Checked by trigger; no update needed because Agent behavior was not changed, only a missing regression test was added for existing behavior

4. **`tests/README.md`**:
   - Checked by trigger; no update needed because added tests stay inside existing Engine/Host/Service test layers

5. **Root `README.md` and `dayu/README.md`**:
   - Not updated because fix does not change user-visible commands, workspace layout, installation flow, or layer boundaries

**Conclusion**: Docs/README changes are necessary and accurate. No over-documentation or missing documentation.

## Open Questions

- 无

## Residual Risk

- S3 typed Engine error-code contract remains out of S2 scope (pre-existing, not introduced by this fix).
- `P3-D-S2-CR-F03` remains rejected-with-reason and was not changed (by instruction).

## Validation Summary

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/host/test_host_activity_event_projection.py tests/service/test_entrypoint_runtime.py -q` → `126 passed, 3 warnings in 1.58s`
- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q` → `131 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py -q` → `164 passed in 1.55s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`
- `git diff --check` → passed

## Conclusion

### P3-D-S2-CR-F01: FIXED

Fatal `PROVIDER_PROTOCOL_ERROR` activity is no longer projected as `HostActivityKind.PROVIDER_DIAGNOSTIC`. It now uses its own `HostActivityKind.PROVIDER_PROTOCOL_ERROR` with `HostActivityStatus.FAILED`. Non-fatal `PROVIDER_DIAGNOSTIC` remains on `HostActivityKind.PROVIDER_DIAGNOSTIC` with `HostActivityStatus.INFO`. Service entrypoint preserves the distinction through `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`. All tests pass with direct assertions on the new kind and status.

### P3-D-S2-CR-F02: FIXED

Context overflow `CONTEXT_LENGTH_EXCEEDED` with `context_overflow_detection=None` has explicit regression coverage in `test_context_overflow_without_detection_emits_only_compaction_request`. The test asserts the Engine event stream contains `CONTEXT_COMPACTION_REQUESTED` and does not contain `PROVIDER_DIAGNOSTIC`. All assertions pass.

### New Material Findings

未发现实质性问题。

---

S2 re-review complete.
