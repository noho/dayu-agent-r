# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1 Review Fix (AgentCodex)

## Scope

- Gate: review-fix
- Branch: `phaseflow/host-issues-control`
- Accepted finding: `DS-D1-01`
- Initial scope: focused test assertions for force-answer failure messages.
- Updated scope: the focused test exposed a direct Engine Agent production mismatch; per handoff, the fix minimally changed the Engine Agent force-answer owner and did not expand to other production modules.

## Finding Status

- `DS-D1-01`: fixed.

The original review classified this as a test gap: `test_force_answer_empty_and_tool_call_are_fail_closed` did not assert that force-answer failures preserve the original fallback trigger in the diagnostic message.

During the focused test run, the max-iterations force-answer tool-call branch failed directly:

- expected message metadata: `trigger=max_iterations_exceeded`
- actual message: `runner produced tool calls while tools were disabled or unavailable`

This upgraded the issue from a test-only assertion gap to a direct production mismatch in the Engine Agent force-answer failure path.

## Changes

- Updated `dayu/engine/agent.py` so `_run_force_answer()` rewrites the `RunFailedData(tool_call_not_enabled)` message through `_fallback_failure_message(trigger=...)` before emitting the terminal failure.
- Updated `tests/engine/test_agent_phase3_tool_call.py` so `test_force_answer_empty_and_tool_call_are_fail_closed` now asserts:
  - force-answer empty after `max_iterations_exceeded` retains `trigger=max_iterations_exceeded`;
  - force-answer tool-call failure after `max_iterations_exceeded` retains `trigger=max_iterations_exceeded`;
  - force-answer empty after `consecutive_failed_tool_batches` retains `trigger=consecutive_failed_tool_batches`.

## README Decision

- `dayu/engine/README.md` was checked because production Engine code changed. It already states that force-answer self-failures preserve the original fallback trigger error code, so no README update was required.
- `tests/README.md` was checked because tests changed. The test hierarchy and run commands did not change, so no README update was required.

## Validation

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py::test_force_answer_empty_and_tool_call_are_fail_closed -q`
  - Result: `1 passed`
- `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/test_runner_event_contract.py tests/engine/test_import_boundary.py tests/host/test_engine_ingest_mapping.py tests/host/test_watch_session_events.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q`
  - Result: `283 passed, 3 warnings`
  - Warnings: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.

## Residual Risk

- The original fallback trigger is still carried in the human-readable `RunFailedData.message` string rather than a structured field. This matches the accepted D1 contract and existing README wording. If future consumers need programmatic trigger handling, that should be a separate contract change owned by Engine event schema design.

## No Commit / Push

- No commit, push, PR, or merge was performed.
