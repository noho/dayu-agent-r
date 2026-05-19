# Controller Fix Artifact

## Scope

- Gate: PR review fix + smoke failure fix
- Date: 2026-05-19
- Owner: AgentCodex
- Allowed implementation scope: `dayu/host/llm_compaction.py`, `dayu/host/wait_adapter.py`, `dayu/host/admission.py`, `dayu/engine/agent.py`, `utils/smoke_host_public_multiturn.py`, related tests and README files
- Explicitly excluded: console script entry points, broad architecture debt, unrelated review findings

## Accepted Fixed

- LLM compactor rejects `finish_reason=length` final answers as truncated dirty proposals, so compact operation can enter retry or failure handling instead of accepting partial summaries.
- LLM compactor wraps Engine runner calls in a timeout derived from `RunnerSpec.default_timeout_seconds`.
- LLM compactor sanitizes failed non-final `error_code` before including it in exception text, and continues redacting sensitive message content.
- Smoke script separates ordinary runner options from compactor runner options: ordinary answers use higher `max_tokens` plus continuation attempts, while compactor output stays separately bounded.
- WaitPoller cancelled wait abandon memory is bounded to currently observed successfully abandoned cancelled waits; failed abandon is not remembered and is retried.
- Engine `_AsyncAgent` no longer uses `threading.Lock` in the async run guard.
- Engine runner close cleanup releases the private run slot even when `close()` is interrupted by `asyncio.CancelledError`.
- Engine performs inline message size guard before force-answer runner calls.
- Engine checks cancellation before registering a tool batch's `tool_call_id` values as executed.
- Host tests use `dayu.host.api.HostInput` instead of relying on a package-root compatibility re-export.
- Admission queue promotion wakeup `RuntimeError` now records a warning instead of being silently swallowed.
- README files were synchronized for the stable behaviors above.

## Deferred With Reason

- Broader Engine Agent and Host scheduler object decomposition is deferred because this gate is scoped to correctness/stability fixes, not architectural refactoring.
- Host watch polling backoff, memory rebuild consistency, durable schema migration ergonomics, terminal timestamp API cleanup, and other larger repository review findings are deferred because they are outside the allowed modification range for this gate.
- ToolRuntime reuse inline governance is deferred because `dayu/host/tool_runtime.py` is outside this gate's allowed write scope.
- Fake compactor budget estimation parity is deferred because this gate only allowed the LLM compactor path; fake compactor was not part of the smoke failure or accepted fix set.

## Not Fixed By User Decision

- Published console scripts pointing at currently absent CLI/Web/GUI modules were not fixed. The user explicitly decided these are out of scope because CLI/Web/GUI work has not started.

## Verification

- `source .venv/bin/activate && pytest -q tests/host/test_llm_compaction.py tests/host/test_wait_adapter_polling.py tests/host/test_admission_queue.py::test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure tests/engine/test_agent_phase2.py::test_close_cancelled_error_releases_run_slot tests/engine/test_agent_phase2.py::test_outer_asyncio_cancelled_error_propagates_and_closes tests/engine/test_agent_phase3_tool_call.py::test_oversized_tool_message_fails_before_next_runner_call tests/engine/test_agent_phase3_tool_call.py::test_oversized_tool_message_fails_before_force_answer_runner_call tests/engine/test_agent_phase3_tool_call.py::test_cancel_before_tool_batch_does_not_register_tool_call_id tests/engine/test_agent_phase3_tool_call.py::test_late_cancellation_after_tool_outcome_preserves_accepted_facts` passed.
- `source .venv/bin/activate && pytest -q tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_llm_compaction.py tests/host/test_wait_adapter_polling.py tests/host/test_admission_queue.py tests/host/test_package_exports.py` passed.
- `source .venv/bin/activate && pytest -q tests/host/test_active_cancel_dispatch.py tests/host/test_command_handle.py tests/host/test_logging.py tests/host/test_open_host_runtime.py tests/host/test_phase5_local_execution_integration.py tests/host/test_phase7_waiting_integration.py tests/host/test_projection_read_model.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py` passed.
- `source .venv/bin/activate && pyright dayu tests utils/smoke_host_public_multiturn.py` passed with 0 errors.
- `source .venv/bin/activate && python -m py_compile utils/smoke_host_public_multiturn.py` passed.
- `git diff --check` passed.
