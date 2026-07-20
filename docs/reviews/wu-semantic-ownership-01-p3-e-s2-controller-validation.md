# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S2 - Wait callback typed provider status ref and accepted status projection`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-implementation-codex.md`

## Controller Result

`ready-for-code-review`

The S2 implementation satisfies the accepted plan target pending independent code review.

## Direct Checks

### Wait Callback Provider Status Ref

- `_provider_status_ref_from_json(...)` in `dayu/service/wait_callback_endpoint.py` no longer accepts a bare string.
- Non-`None` `provider_status_ref` must be a JSON object with typed `adapter_key`, `status_ref`, and optional `status_digest`.
- `tests/service/test_wait_callback_endpoint.py` includes a negative bare-string test returning `malformed_payload` without calling the adapter.

### Accepted Result Status Projection

- `_status_from_raw_outcome(...)` is removed.
- Accepted status is now derived only from typed payload fields `resolution_kind` and `tool_fact_kind`.
- Payload unavailable diagnostics map to `AcceptedToolResultStatus.LOST`.
- Payload available but typed status missing, blank, malformed, or unknown maps to `AcceptedToolResultStatus.UNKNOWN` and appends `accepted_status_unavailable`.
- Raw outcome remains available only for result text / details extraction.

### Consumer Disposition

- `read_api`: consumes `project_accepted_tool_result(...)` status and does not reconstruct status from raw outcome.
- `run_input` / evidence material: consumes accepted result projection / evidence material; raw result fallback is for text material, not status truth.
- `memory`: no accepted status reconstruction from raw outcome was found.
- `compact_material`: consumes `projection.llm_material`; raw outcome missing remains a fail-closed material path, not status reconstruction.

## Validation Commands

Passed:

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py -q
```

Result: `311 passed in 1.66s`.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed coverage gate:

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py --cov=dayu.service.wait_callback_endpoint --cov=dayu.host.accepted_result_projection --cov-report=term-missing -q
```

Result: `62 passed in 0.50s`; `dayu/host/accepted_result_projection.py` coverage `92%`, `dayu/service/wait_callback_endpoint.py` coverage `88%`.

Passed:

```bash
rg -n "_status_from_raw_outcome" dayu tests
```

Result: no matches.

Passed:

```bash
rg -n "_result_payload|AcceptedToolResultStatus.UNKNOWN|_status_from_raw_outcome|raw_tool_outcome|result_payload_unavailable|event_payload_unavailable|accepted_status_unavailable" dayu/host/accepted_result_projection.py dayu/host/read_api.py dayu/host/run_input.py dayu/host/evidence.py dayu/host/memory.py dayu/host/compact_material.py tests/host
```

Classification:

- `_status_from_raw_outcome`: no matches.
- `raw_tool_outcome`: retained only as raw result text / evidence material input, tests, or fail-closed material checks.
- `AcceptedToolResultStatus.UNKNOWN`, `accepted_status_unavailable`, `result_payload_unavailable`, and `event_payload_unavailable`: retained in accepted-result projection and related tests.

Passed:

```bash
rg -n "provider_status_ref|WaitAdapterKey\\(\"callback\"\\)" dayu/service/wait_callback_endpoint.py tests/service/test_wait_callback_endpoint.py dayu tests
```

Classification:

- Service endpoint only parses object-shaped `provider_status_ref`.
- Tests include typed object positive coverage and bare-string malformed negative coverage.
- Wider Host hits are typed `WaitProviderStatusRef` contracts, serialization, digest material, or tests; no Service mapper string-to-`WaitAdapterKey("callback")` fallback remains.

Passed:

```bash
git diff --check
```

Result: no output.

## README Decision

- `tests/README.md` update is accepted: it is within the file's stated role of recording existing test coverage and now mentions bare-string `provider_status_ref` rejection in the Service wait callback endpoint tests.
- `dayu/host/README.md` no-op is accepted: current Host README already states accepted result projection is unified and downstream consumers must not rebuild evidence text or semantics.
- Root `README.md` and `dayu/README.md` no-op is accepted: S2 changes internal Service callback payload validation and Host projection status sourcing, not end-user workflow or project-level layer boundaries.

## Propagation Audit

- `provider_status_ref`:
  - Producer: external callback JSON payload.
  - Direct upstream validation owner: `dayu.service.wait_callback_endpoint`.
  - Typed contract: `WaitProviderStatusRef`.
  - Downstream Host callback adapter receives either a typed ref or no ref; Service no longer creates a fake callback adapter identity from a bare string.
- accepted result status:
  - Producer / durable truth: Host accept barrier and wait resolution payload typed status fields.
  - Projection owner: `dayu.host.accepted_result_projection`.
  - Diagnostics: unavailable payload maps to `LOST`; available payload with unavailable typed status maps to `UNKNOWN` plus `accepted_status_unavailable`.
  - Consumers: read model, run input, memory, and compact material consume the shared projection or evidence material; no consumer restores raw outcome fallback status.
  - LLM-facing text: raw outcome may still contribute business-readable result details, but it does not own accepted status.

## Residual Risk

- `UNKNOWN` currently displays through existing consumer policies, including Read API's non-completed severity path. Changing product display semantics would be a separate projection/display policy work unit and must not reintroduce raw outcome reconstruction.
- External callback producers still sending bare-string `provider_status_ref` will now receive `malformed_payload`, as required by the S2 fail-closed contract.

