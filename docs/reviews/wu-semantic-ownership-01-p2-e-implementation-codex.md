# WU-SEMANTIC-OWNERSHIP-01 / P2-E Implementation - AgentCodex

## Gate / Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-E`
- Gate: implementation
- Scope: align 7 broad-suite failures found after P2-D to accepted production contracts.
- Decision: test-only implementation. No production code changed. No commit created per user instruction.

## Motivation And Owner-Boundary Assessment

First-principles judgment: the failures were real broad-suite failures, but direct evidence did not show production contract drift. The failing assertions and fixtures were stale relative to accepted Engine / Host contracts and durable schema invariants.

Owner boundaries:

- Stream heartbeat: production fact is produced by OpenAI Runner idle-byte loop; diagnostic level truth is `STREAM_DEBUG_LOG_LEVEL`. Test owner is `tests/engine/runners/openai/test_stream_idle.py`.
- Engine runner input signal: production contract owner is `dayu.engine` / `EngineEvent.iteration_started`; docs/engine/design.md states `input_projection` is part of the event. Snapshot owner is `tests/engine/test_engine_event_contract.py`.
- Engine package exports: production export owner is `dayu.engine.__all__`; docs/engine/design.md lists `RunnerInputMessageProjection` and `RunnerInputToolCallProjection` as public package-root exports. Snapshot owner is `tests/engine/test_package_exports.py`.
- Host package/API exports: production export owner is `dayu.host` / `dayu.host.api`; dayu/host/README.md lists `HostThinkingView` as a public typed event view. Snapshot owner is `tests/host/test_package_exports.py`.
- Wait-resume LLM-facing replay: durable facts are owned by Host ToolRuntime awaiting accept, wait resolution, and RunInputBuilder projection. The stale assertion owner is `tests/host/test_phase7_waiting_integration.py`.
- Purge cancelling fixture: durable invariant owner is Host schema / cancel lifecycle. Fixture owner is `tests/host/test_purge_session.py`.

## Actual Files Changed

- `tests/engine/runners/openai/test_stream_idle.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/wu-semantic-ownership-01-p2-e-implementation-codex.md`

## Implementation Notes

- Stream heartbeat positive capture now uses `STREAM_DEBUG_LOG_LEVEL` and keeps the no-byte-drop / no HTTP error assertions.
- Added an ordinary `logging.DEBUG` negative heartbeat assertion using equivalent idle conditions through the same `_heartbeat_runner()` helper, so heartbeat would have been produced under stream-debug capture.
- Updated Engine field/export snapshots for `input_projection`, `RunnerInputMessageProjection`, and `RunnerInputToolCallProjection`.
- Updated Host package/API export snapshots for `HostThinkingView`.
- Replaced stale wait-resume English fallback assertion with the normal protocol replay assertion: `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`.
- Fixed purge cancelling fixture by creating a dedicated `CANCEL_REQUESTED` EventLog row only when a Run row is `cancelling` or `cancelled`, then storing that dedicated event id in `cancel_request_event_id`. The helper does not change ordinary succeeded matrix event counts.

## Wait-Resume Diagnostic Result

The local integration path was diagnosed before changing the assertion. Actual `resume_request.messages`:

1. `SystemMessage`
2. `UserMessage(content="hello")`
3. `AssistantMessage(tool_calls=[id="tool-call-phase7-awaiting", name="awaiting_tool", arguments={"ticker": "DAYU"}])`
4. `ToolMessage(tool_call_id="tool-call-phase7-awaiting", content='{"answer": 42}')`

No old English guidance appeared. The path already had the accepted request atom / evidence envelope needed for normal protocol replay, so production code and fixture repair were not required.

## Purge Parametrize Check Result

`_NON_TERMINAL_RUN_STATUSES` covers:

- `accepted`
- `queued`
- `running`
- `waiting`
- `cancelling`
- `recovering`

It does not include `cancelled`. The fixture helper still applies the same dedicated `cancel_request_event_id` invariant to `cancelled` if that helper is used with a cancelled Run in the future.

## Wait-Resume Propagation Audit

1. Awaiting request fact is first produced by ToolRuntime from the original `ToolCallRequest`, including `tool_call_id`, tool name, and arguments.
2. Host awaiting accept persists the request atom / awaiting wait record as canonical durable facts.
3. Manual `resolve_wait` persists the completed tool result as accepted wait resolution / tool result truth.
4. RunInputBuilder reads the durable request/result facts for the resumed Attempt and projects them into LLM-facing messages.
5. The resumed request contains a coherent protocol chain: user request, assistant tool call with the original tool call id, and tool message linked to the same id.
6. The test now asserts the projected protocol facts and the business-readable result JSON (`answer == 42`) instead of stale fallback guidance text.
7. No production LLM-facing text, memory, compact, trace, audit, or read-model projection was changed.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked tests/engine/test_package_exports.py::test_engine_all_matches_expected_set tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run 'tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs[cancelling]' -q
# 7 passed in 0.51s
```

Passed:

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_idle.py tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/host/test_phase7_waiting_integration.py tests/host/test_purge_session.py -q
# 65 passed in 1.76s
```

Passed:

```bash
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host -q
# 2596 passed, 1 skipped, 5 deselected, 3 warnings in 72.69s
```

Warnings were existing edgar dependency deprecation warnings.

Passed:

```bash
source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

Passed:

```bash
git diff --check
```

## README / Doc Trigger Decision

Production code did not change. The modified tests align to existing documented production contracts:

- `docs/engine/design.md` already documents `input_projection` and the runner input projection exports.
- `dayu/host/README.md` already documents `HostThinkingView`.
- `tests/README.md` was checked; no new test layer, command category, or maintenance convention was introduced.

README updates are not needed.

## Residual Risks

- Real-provider wait-resume behavior was not separately exercised in this implementation; current coverage is the local integration path required by P2-E. Classification: assigned to existing broader smoke / real-environment validation owners.
- Broad matrix still reports edgar dependency deprecation warnings. Classification: tracked outside this work unit; unrelated to P2-E.
- No unclassified current-slice residual risk remains.

## Completion Status

Implementation complete for P2-E. Next gate would normally be code review, but no commit/PR action was taken because the user explicitly requested not to commit.
