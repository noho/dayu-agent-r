# WU-ENG-02 Slice 1 Implementation - AgentCodex

## Gate / Work Unit / Slice

- gate: implementation
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 - Engine Contract And Agent Identity
- agent: AgentCodex

## Changed Files

Slice 1 allowed files changed:

- `dayu/engine/contracts/runner_identity.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/agent.py`
- `tests/engine/contracts/test_runner_identity.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_metadata_boundary.py`
- `docs/reviews/wu-eng-02-slice1-implementation-codex.md`

Additional files changed for compile/type compatibility:

- `dayu/engine/runners/openai/runner.py`: required because `AsyncRunner.call` public protocol changed. Without a minimal keyword-only `request_identity` parameter, `build_default_runner()` no longer returned an `AsyncRunner` by pyright and the default production Agent path would be runtime-incompatible. This change only accepts and ignores the identity; it does not implement RunnerSpec policy or OpenAI header mapping.
- `tests/host/public_smoke_support.py`: existing fake runners were assigned to `_AsyncAgent(..., runner=...)`; pyright required their signatures to match the new `AsyncRunner` protocol.
- `tests/host/test_phase6_toolruntime_integration.py`: existing fake runner was assigned to `_AsyncAgent(..., runner=...)`; pyright required its signature to match the new `AsyncRunner` protocol.

Pre-existing worktree change not touched:

- `docs/host/issues-implementation-control.md` was already modified before this implementation and was intentionally not edited.

## Implementation Summary

- Added `RunnerRequestIdentity` and `build_runner_request_identity`.
- Added validation for non-empty identity text fields, `iteration_index >= 0`, `runner_call_index >= 1`, and paired `attempt_id` / `execution_id`.
- Derived `client_correlation_id` as `dayu-` plus full 64-character lowercase SHA-256 hex over the canonical tuple: `run_id`, `attempt_id`, `execution_id`, `iteration_id`, `iteration_index`, `runner_call_index`.
- Added `attempt_id` and `execution_id` to `AgentRunRequest` with paired validation and default `None` for direct Engine / compactor paths not handled in this slice.
- Changed `AsyncRunner.call` to accept keyword-only `request_identity`.
- Added `_AsyncAgent._runner_call_index`; every `_run_runner_iteration()` call now increments it, builds a non-`None` `RunnerRequestIdentity`, and passes it to Runner.
- Added `client_correlation_id` to provider-related EngineEvent data and failed outcome contracts.
- Stored request identity in `_IterationState` and used one module-level helper to read `client_correlation_id` at emit/classification points.

## Public Contract Changes

- New public Engine contract module: `dayu.engine.contracts.runner_identity`.
- New public exports from `dayu.engine.contracts`: `RunnerRequestIdentity`, `build_runner_request_identity`.
- `AsyncRunner.call(messages, options, tools, *, request_identity)` now includes typed per-call identity.
- `AgentRunRequest` now includes optional `attempt_id` and `execution_id`; they must both be `None` or both non-`None`.
- `ContextCompactionRequestedData`, `ProviderProtocolErrorData`, `IterationCompletedData`, `RunFailedData`, and `EngineRunOutcomeFailed` now carry optional `client_correlation_id`.

## Tests / Validation

Command:

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/test_metadata_boundary.py
```

Result:

- Passed: 127 tests.

Command:

```bash
source .venv/bin/activate && pyright
```

Result:

- Passed: 0 errors, 0 warnings, 0 informations.

## Docs Decision

README sync is deferred to the approved Slice 4. This slice did not modify README files.

## Residual Risks / Uncovered Areas

- Owner Slice 2: `dayu/engine/runners/openai/runner.py` currently only accepts `request_identity`; it does not map `client_correlation_id` to `X-Client-Request-Id`.
- Owner Slice 2: no `RunnerSpec` client correlation policy exists yet.
- Owner Slice 3: Host `RunInputBuilder` still does not project `AttemptDispatchSnapshot.attempt_id/execution_id` into `AgentRunRequest`.
- Owner Slice 3/4: Host ingest, Tool Trace, and README synchronization are intentionally not implemented here.
- Owner test suite: direct OpenAI runner tests still exercise calls without request identity, which remains allowed for direct Runner paths.

## Stop Conditions Encountered

- Initial pyright failed because the new `AsyncRunner` protocol made the default OpenAI runner and several existing fake runners signature-incompatible. This was resolved by minimal signature synchronization only; no policy/header behavior was added.
- No blocking open questions remained after the minimal signature sync.

## Completion Status

Complete for Slice 1 implementation.
