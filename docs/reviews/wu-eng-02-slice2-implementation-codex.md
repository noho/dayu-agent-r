# WU-ENG-02 Slice 2 Implementation - AgentCodex

## Gate / Work Unit / Slice

- gate: implementation
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 2 - RunnerSpec Policy And OpenAI-Compatible Header Mapping
- agent: AgentCodex

## Changed Files

Slice 2 allowed files changed:

- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/host/_execution_config_projection.py`
- `tests/engine/contracts/test_runner_spec.py`
- `tests/engine/runners/openai/test_request_identity.py`
- `tests/engine/runners/openai/_factories.py`
- `tests/host/test_effective_execution_config.py`
- `docs/reviews/wu-eng-02-slice2-implementation-codex.md`

Additional direct `RunnerSpec` constructor / factory sync required by pyright:

- `dayu/service/host_assembly.py`: production assembly constructs `RunnerSpec`; added explicit `ClientCorrelationPolicy.DISABLED` so the new required contract remains explicit and does not enable outbound mapping by default.
- `utils/smoke_async_agent_providers.py`: smoke script constructs `RunnerSpec`; added explicit disabled policy only.
- `tests/engine/contracts/test_agent_run.py`: direct request factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/engine/test_agent_phase2.py`: direct Agent test request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/engine/test_agent_phase3_tool_call.py`: direct Agent test request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/engine/test_metadata_boundary.py`: direct Agent test request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/public_smoke_support.py`: host smoke support factories construct `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_active_cancel_dispatch.py`: direct host test factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_admission_multiprocess.py`: direct admission request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_admission_queue.py`: direct admission request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_command_handle.py`: direct command request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_dispatch_scheduler.py`: direct scheduler factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_llm_compaction.py`: direct compaction test factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_local_proxy_engine_ingest.py`: direct local proxy request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_logging.py`: direct logging test request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_open_host_runtime.py`: direct host runtime factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_per_run_tool_selection.py`: direct per-run selection factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_phase5_local_execution_integration.py`: direct integration factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_phase6_toolruntime_integration.py`: direct integration request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_phase7_waiting_integration.py`: direct integration factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_projection_read_model.py`: direct projection request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_public_contracts.py`: direct public contract factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_public_lifecycle_smoke.py`: direct lifecycle smoke factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_public_open_host_options.py`: direct open-host options factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_public_retry_replay.py`: direct retry replay factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_resolve_wait_command.py`: direct resolve-wait request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_run_input_builder.py`: direct run-input request constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_submit_followup_public_contract.py`: direct followup factory constructs `RunnerSpec`; added explicit disabled policy.
- `tests/host/test_watch_session_events.py`: direct watch-events factory constructs `RunnerSpec`; added explicit disabled policy.

Pre-existing worktree change not touched:

- `docs/host/issues-implementation-control.md` was already modified before this implementation and was intentionally not edited.

## Implementation Summary

- Added `ClientCorrelationPolicy` with `DISABLED` and `OPENAI_X_CLIENT_REQUEST_ID`.
- Added required `RunnerSpec.client_correlation_policy`.
- Exported `ClientCorrelationPolicy` from `dayu.engine.contracts`.
- Added Host effective execution config freeze / restore for `client_correlation_policy`.
- Added OpenAI-compatible request header helper that builds `Content-Type`, static `RunnerSpec.headers`, and conditional `X-Client-Request-Id`.
- OpenAI-compatible runner now sends `X-Client-Request-Id` only when policy is `OPENAI_X_CLIENT_REQUEST_ID` and `request_identity` is non-`None`.
- Policy disabled and missing identity paths do not send the client header.
- Policy enabled rejects static case-insensitive `x-client-request-id` in `RunnerSpec.headers` with `ValueError` before HTTP post.
- The header mapping is computed once per logical Runner call and reused across transport retries.
- Response `x-request-id` collection was not changed.
- No provider string branch, `safety_identifier`, `user_id`, or `metadata.user_id` behavior was added.
- No Host ingest, Tool Trace, native Anthropic runner, or Slice 3 behavior was implemented.

## Public Contract / Config Projection Changes

- Public Engine contract change: `RunnerSpec` now requires `client_correlation_policy: ClientCorrelationPolicy`.
- Public enum values are provider-protocol-specific outbound mapping policies, not provider-name branches.
- Host effective execution config JSON now includes `"client_correlation_policy"` under `"runner_spec"` and restores it through `ClientCorrelationPolicy(...)`.
- Fresh-schema behavior is preserved: restored JSON must contain the new field; no compatibility reader or wrapper was added.

## Tests / Validation

Command:

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_effective_execution_config.py
```

Result:

- Passed: 61 tests.

Command:

```bash
source .venv/bin/activate && pyright
```

Result:

- Passed: 0 errors, 0 warnings, 0 informations.

## Docs Decision

README sync is deferred to the approved Slice 4. This slice did not modify README files.

## Residual Risks / Uncovered Areas

- Owner Slice 3: Host `AgentRunRequest` projection from `AttemptDispatchSnapshot.attempt_id/execution_id` remains out of scope.
- Owner Slice 3: Host ingest and Tool Trace payload projection for `client_correlation_id` remains out of scope.
- Owner future adapter slice: native Anthropic runner policy and response request-id handling remain unimplemented because this slice only covers OpenAI-compatible mapping.
- Owner config/product decision: production assembly currently sets `ClientCorrelationPolicy.DISABLED`; enabling OpenAI-compatible correlation requires an explicit future config/profile decision.
- Owner test suite: direct constructor sync uses disabled policy to preserve existing tests; it does not exercise enabled policy outside the new OpenAI-compatible request identity tests.

## Stop Conditions Encountered

- Initial pyright exposed direct `RunnerSpec` constructors outside the original allowed file list. Each was minimally synchronized with explicit `ClientCorrelationPolicy.DISABLED` only, per task allowance.
- No blocking open questions remain.

## Completion Status

Complete for Slice 2 implementation.
