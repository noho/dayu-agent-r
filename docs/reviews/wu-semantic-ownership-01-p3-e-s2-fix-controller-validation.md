# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S2 - Wait callback typed provider status ref and accepted status projection`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-fix-codex.md`
- Accepted fix: `P3-E-S2-CR-F01`

## Controller Result

`ready-for-independent-rereview`

`P3-E-S2-CR-F01` is fixed in the current workspace pending independent re-review.

## Closure Check

- `tests/host/test_accepted_result_projection.py` now includes `test_projection_missing_event_payload_maps_lost_with_diagnostic`.
- The test writes a valid payload descriptor whose JSON is not an EventLog payload object, causing the projection read boundary to emit `event_payload_unavailable`.
- The test asserts:
  - `projection.status is AcceptedToolResultStatus.LOST`
  - `"event_payload_unavailable" in projection.diagnostic_reasons`
- Existing `result_payload_unavailable` coverage remains unchanged.
- No production code was changed in this fix gate.

## Validation Commands

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py -q
```

Result: `17 passed in 0.36s`.

Passed:

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py -q
```

Result: `312 passed in 1.77s`.

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

## README Decision

No additional README update is required. This fix only adds one diagnostic branch test to an already documented accepted-result projection test area and does not change test layering, commands, public Host contract, or user workflow.

## Propagation Audit

- Producer / durable fact: already committed `TOOL_RESULT_ACCEPTED` EventLog row.
- Projection owner: `_result_event_payload(...)` reads and validates the EventLog payload object.
- Diagnostic: invalid/unreadable EventLog payload maps to `event_payload_unavailable`.
- Status projection: `_accepted_status(...)` maps unavailable event payload diagnostics to `AcceptedToolResultStatus.LOST`.
- Consumers: no downstream consumer fix is needed; they consume the shared projection.

## Residual Risk

- No new residual risk from this fix gate.
- Existing S2 product-display residual remains: `UNKNOWN` currently uses existing consumer severity policy. Any product-level distinction from failed/error belongs to a future display policy work unit.

