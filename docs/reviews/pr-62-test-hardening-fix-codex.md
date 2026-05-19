# PR-62 merge-before test hardening fix - AgentCodex

## Accepted findings

- DS F1 confirmed: dispatch effective decision used inline-only payload parsing and could drop descriptor-backed per-run overrides. Fixed `HostDispatchScheduler._effective_dispatch_decision` to use `event_payload_object(..., payload_label="USER_INPUT_ACCEPTED")`.
- Admission descriptor boundaries confirmed under-tested. Added exact positive-threshold boundary coverage, descriptor fail-closed coverage, and RunInputBuilder descriptor prompt coverage.
- Compaction retry negative paths confirmed under-tested. Added operation-level quality rejection and hard-threshold retry tests, plus proactive scheduler quality-retry integration and stale failure reason assertion.
- Multi-turn deterministic continuity confirmed as a real gap: `RUN_SUCCEEDED` persisted final content in terminal summary descriptor, but memory continuity rendered only an event ref. Fixed memory projection and RunInputBuilder inline delta to resolve terminal summary descriptor content.
- Scheduler close / wake lifecycle, public retry/replay negative paths, and steer idempotency / conflict detail were under-covered. Added focused tests and filled typed `SteerConflictDetail` on steer precondition failures.
- Re-review maintainability cleanup: de-duplicated terminal summary SQLite descriptor resolution and assistant summary extraction. Descriptor object reads now reuse `dayu/host/payload_resolution.py`; pure assistant summary extraction lives in `dayu/host/terminal_summary_payload.py` to avoid a `memory.py` -> durable schema import cycle.

## Changed files

- Production:
  - `dayu/host/dispatch.py`
  - `dayu/host/admission.py`
  - `dayu/host/payload_resolution.py`
  - `dayu/host/terminal_summary_payload.py`
  - `dayu/host/durable/memory.py`
  - `dayu/host/memory.py`
  - `dayu/host/run_input.py`
- Tests:
  - `tests/host/test_effective_execution_config.py`
  - `tests/host/test_admission_queue.py`
  - `tests/host/test_payload_store.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_public_open_host_multiturn_smoke.py`
  - `tests/host/test_public_retry_replay.py`
  - `tests/host/test_public_steer.py`
  - `tests/host/test_public_contracts.py`
- Docs:
  - `dayu/host/README.md`
  - `tests/README.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_payload_store.py tests/host/test_effective_execution_config.py -q`
  - Result: `52 passed`
- `source .venv/bin/activate && pytest tests/host/test_effective_execution_config.py tests/host/test_admission_queue.py tests/host/test_payload_store.py tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_retry_replay.py tests/host/test_public_steer.py tests/host/test_public_contracts.py tests/host/test_package_exports.py tests/runtime/test_lane.py -q`
  - Result: `208 passed`
- `source .venv/bin/activate && pyright dayu/host/payload_resolution.py dayu/host/terminal_summary_payload.py dayu/host/durable/memory.py dayu/host/run_input.py dayu/host/memory.py tests/host/test_run_input_builder.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_payload_store.py tests/host/test_effective_execution_config.py tests/host/test_public_contracts.py`
  - Result: `0 errors`
- `git diff --check`
  - Result: passed

## Deferred findings

- Multi-process admission spill remains deferred per controller scope.
- Dedicated `start_run` large payload descriptor test remains deferred; follow-up path now covers positive-threshold descriptor resolution.
- DS F2 threshold-zero coverage was rejected by the controller because `payload_inline_threshold_bytes=0` violates the design truth and existing public contract; threshold must remain positive.
- OpenHostOptions full negative matrix remains deferred.
- `run is None` stale branch and `system_prompt=None` message-layout expansion remain deferred.
- No broad coverage inventory was added.

## Residual risks

- Terminal summary descriptor continuity now resolves SQLite descriptor content for memory projection and RunInputBuilder inline delta. Artifact-backed terminal summary descriptors are still fail-closed because current Engine terminal summaries are written as SQLite payload descriptors.
- Positive-threshold descriptor coverage now exercises boundary `L` / `L-1` and large prompt descriptor resolution. Threshold zero remains invalid by public contract.
