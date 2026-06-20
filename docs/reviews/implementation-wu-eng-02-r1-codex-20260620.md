# WU-ENG-02-R1 Implementation Report - AgentCodex

- **Work unit**: WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics
- **Gate**: implementation
- **Agent**: AgentCodex
- **Date**: 2026-06-20
- **Accepted plan commit**: `913875da`
- **Accepted plan artifact**: `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`

## Baseline Before Default Change

Before changing Service default assembly:

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
```

Result: `52 passed, 3 warnings in 1.92s`.

Warnings were existing `edgar` deprecation warnings from dependencies.

## Files Changed And Why

- `dayu/service/host_assembly.py`: changed Service-created `RunnerSpec.client_correlation_policy` default from `DISABLED` to `OPENAI_X_CLIENT_REQUEST_ID`.
- `dayu/engine/runners/openai/runner.py`: threaded `client_correlation_id` into the private HTTP attempt path and added it to the existing `runner.http.response` DEBUG log line.
- `dayu/host/tool_trace.py`: preserved `ENGINE_EVENT_DIAGNOSTIC` Tool Trace rows when `provider_request_id=None` but `client_correlation_id` exists.
- `dayu/host/_terminal_diagnostics.py`: added the shared private Host projection helper for bounded terminal diagnostic suffix formatting.
- `dayu/host/read_api.py`: appended the shared diagnostic suffix on failed live `HostEvent.error_message` projection only.
- `dayu/host/outbox.py`: appended the same suffix on failed outbox terminal item projection only.
- Tests updated:
  - `tests/service/test_host_assembly.py`
  - `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
  - `tests/engine/runners/openai/test_runner_diagnostics.py`
  - `tests/host/test_tool_trace_projection.py`
  - `tests/host/test_tool_trace_queries.py`
  - `tests/host/test_read_api_terminal_policy.py`
- README updates:
  - `dayu/service/README.md`
  - `dayu/engine/README.md`
  - `dayu/host/README.md`
  - `tests/README.md`

Scope note: `tests/host/test_read_api_terminal_policy.py` was used for direct Host public projection coverage because it already targets terminal text projection and can compare live `HostEvent` projection with outbox terminal projection without adding broad public API setup.

## Implementation Summary By Slice

### Slice 1: Service Default Policy Enablement

`_runner_spec_from_model(...)` now sets `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`. Tests assert ordinary baseline, compactor baseline, and local OpenAI-compatible `ollama` model specs use the enabled policy. Static `X-Client-Request-Id` headers fail fast through existing `RunnerSpec` validation.

### Slice 2: Runner Diagnostics And Header Extraction

Provider request id extraction remains limited to `x-request-id`; tests assert `x-trace-id`, `x-correlation-id`, `cf-ray`, and `traceparent` do not become `provider_request_id`. The existing `runner.http.response` DEBUG log line now includes `client_correlation_id` on the same log site, level, and line.

### Slice 3: Tool Trace Fallback Preservation

Diagnostic extraction now skips `ENGINE_EVENT_DIAGNOSTIC` only when both `provider_request_id` and `client_correlation_id` are absent. Tests assert hot row `provider_request_id is None`, `diagnostic_ref is None`, hot summary includes `client_correlation_id`, cold JSONL top-level and trace summary preserve it, and provider id lookup does not match the client id.

### Slice 4: Terminal Diagnostic Visibility

Live failed `HostEvent.error_message` and outbox failed `error_message` call the same Host projection helper. The helper appends `provider_request_id=...` and/or `client_correlation_id=...` as projection text only. Tests assert identical live/outbox suffix rendering and unchanged source terminal payload JSON/message.

### Slice 5: README / Docs Sync

README trigger rules were checked. Service, Engine, Host, and tests README files were updated with current-code facts. Root `README.md` was not updated because this work did not add user commands, flags, workspace paths, or a new user workflow; it only adds existing diagnostic ids to failed terminal projection text.

## Validation

Final validation after all code and README changes:

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
```

Result: `53 passed, 3 warnings in 1.83s`.

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_runner_diagnostics.py -q
```

Result: `38 passed in 0.56s`.

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
```

Result: `38 passed in 0.50s`.

```bash
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py -q
```

Result: `69 passed, 3 warnings in 3.11s`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`. Pyright also printed a version-available notice: `v1.1.409 -> v1.1.410`.

```bash
git diff --check
```

Result: passed with no output.

## Stop Conditions

No stop condition was hit. No provider contract evidence was found showing default configured provider rejects `X-Client-Request-Id`; implementation did not require new log lines, new event types, durable schema changes, or sensitive header value output.

## Residual Risks

None.
