# WU-SEMANTIC-OWNERSHIP-01 P3-E Aggregate Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Accepted commits:
  - Plan: `035611c8`
  - S1: `7c8bc0a8`
  - S2: `be4ed91c`
  - S3: `0b92a838`

## Controller Result

`ready-for-aggregate-deepreview`

All three P3-E implementation slices are committed and the aggregate validation matrix passed.

## Validation Commands

Passed:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
```

Result: `588 passed, 3 warnings in 17.38s`. Warnings are existing `edgar` deprecation warnings.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed:

```bash
git diff --check
```

Result: no output.

Passed aggregate source scan:

```bash
rg -n "_status_from_raw_outcome|_direct_missing_result_event|_missing_result_event|diagnostic_refs=.*hint|accept_rejected:|_hint_with_diagnostic_refs|FinsDirectStreamContractViolation|provider_status_ref\"\\s*:|last_error_code|_DirectStreamProducerDone|AcceptedToolResultStatus.UNKNOWN" dayu tests
```

Classification:

- No matches for stale helpers / protocols:
  - `_status_from_raw_outcome`
  - `_direct_missing_result_event`
  - `_missing_result_event`
  - `diagnostic_refs=.*hint`
  - `accept_rejected:`
  - `_hint_with_diagnostic_refs`
  - `FinsDirectStreamContractViolation`
- Expected matches:
  - `provider_status_ref"`: typed object serialization / tests.
  - `last_error_code`: wait poll diagnostics, projection failures, accept timeout owner diagnostics, and tests.
  - `_DirectStreamProducerDone`: Fins runtime sentinel type, producer finally, consumer drain, and queue fallback.
  - `AcceptedToolResultStatus.UNKNOWN`: accepted-result projection and tests.

## Propagation Audit

- Tool result runtime discriminator:
  - Owner: `dayu.contracts.tool_result`.
  - Enforcement: `ToolResultSuccess.ok is True`, `ToolResultFailure.ok is False`.
  - Consumers: ToolRuntime / Engine / Host now receive runtime-enforced envelopes.
- ToolRuntime synthetic failure hint:
  - Owner: ToolRuntime failure projection.
  - LLM-facing `hint`: no longer carries governance reason, accept rejection reason, diagnostic refs, or truncation reason codes.
  - Diagnostics: retained through Tool Trace, messages, failure metadata, and accept owner fields.
- Wait callback provider status ref:
  - Owner boundary: Service callback JSON-to-typed mapper.
  - Bare strings fail closed as malformed payload; typed object refs continue into Host callback adapter.
- Accepted result status:
  - Owner: Host accepted result projection over typed durable status fields.
  - Payload unavailable maps to `LOST`; typed status unavailable maps to `UNKNOWN`.
  - Raw outcome remains only result/details material, not status truth.
  - Read API, run input / evidence, memory, and compact material consume the shared projection.
- Fins direct stream terminal result:
  - Owner: Fins runtime direct stream and shared `dayu.fins.direct_events` protocol error contract.
  - Runtime / Service detect missing or duplicate `RESULT` as typed protocol errors.
  - CLI renders the shared typed protocol error; it does not fabricate a business failure result.
  - Business failure `RESULT` remains a valid business terminal event.

## Residual Risk

- P3-E aggregate deepreview has not yet run.
- S3 intentionally delays terminal `RESULT` until producer done sentinel. Existing no-hang tests pass for current producers; future producer lifecycle bugs should surface at the runtime owner.
- P3-E does not close the umbrella WU. Further full-repository deepreview rounds remain required before umbrella closeout.

