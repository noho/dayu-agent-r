# Gateflow Fix Artifact: Host P2 S2 EventLog / Idempotency

## Work Gate

- **work gate name**: fix
- **current gate**: Phase 2 Slice 2 code review fix
- **work-unit**: Host Phase 2 Slice 2 EventLog / Idempotency
- **branch**: `feat/host-phase2-durable-store-eventlog`
- **artifact path**: `docs/reviews/gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md`

## Source Review Artifacts

- `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`
- `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md`
- `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-controller-adjudication-20260514.md`

## Controller-Accepted Findings

- `DS-F1`: whitespace-only identifier strings pass non-empty validation.
- `DS-F2`: `EventLogStore` / `IdempotencyStore` class wrapper methods have zero test coverage.
- `DS-F3`: missing edge case tests for `read_event_by_id` returning `None` and `read_events_after` returning empty tuple.
- `DS-F4`: `_request` helper never exercises NULL optional fields in single-process EventLog tests.

## Per-Finding Fix Status

### DS-F1 - fixed

- `dayu/host/durable/event_log.py` now rejects required and optional text values that are empty or whitespace-only.
- `dayu/host/durable/idempotency.py` now rejects required and optional text values that are empty or whitespace-only.
- Follow-up controller check found `EventLogAppendRequest.actor` and `EventLogAppendRequest.source` were still missing from append validation; both are now routed through `_require_optional_non_empty_text`.
- Validation is deterministic and does not trim or normalize values before storing; it only rejects semantically empty text.
- Added EventLog and Idempotency tests covering whitespace-only required and optional/result text fields, including EventLog `actor` and `source`.

### DS-F2 - fixed

- Added `test_event_log_store_wrapper_methods_delegate_to_functions` to exercise `EventLogStore.append_event`, `read_event_by_id`, and `read_events_after`.
- Added `test_idempotency_store_wrapper_methods_delegate_to_functions` to exercise `IdempotencyStore.record_idempotent_result` and `read_idempotency_record`.
- Store classes were kept because the approved plan names them.

### DS-F3 - fixed

- Added `test_missing_event_and_cursor_beyond_end_return_empty_results`.
- The test verifies missing `event_id` returns `None`.
- The test verifies `read_events_after` with a cursor beyond the last row returns an empty tuple.

### DS-F4 - fixed

- Added `test_append_optional_none_fields_preserves_nulls_and_digest_idempotency`.
- The test appends an EventLog request with optional fields set to `None`.
- The test verifies append/read preserves `None` fields, `event_body_digest` is stored, and duplicate same request returns `inserted=False` with the same digest.

## Changed Files

- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_idempotency_store.py`
- `docs/reviews/gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md`

## Validation

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q` | passed: `19 passed in 0.13s` |
| `source .venv/bin/activate && pytest tests/host/test_event_log_multiprocess.py -q` | passed: `1 passed in 0.28s` |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | passed: `0 errors, 0 warnings, 0 informations` |

## Follow-up Fix: DS-F1 Actor / Source Gap

- Controller follow-up found one remaining DS-F1 coverage gap: `EventLogAppendRequest.actor` and `EventLogAppendRequest.source` are optional EventLog text fields but were not checked by `_require_optional_non_empty_text`.
- `dayu/host/durable/event_log.py` now rejects whitespace-only `actor` and `source` in `_validate_append_request`.
- The implementation does not trim or normalize stored values; non-empty text remains stored exactly as provided.
- `tests/host/test_event_log_store.py` now verifies whitespace-only `actor` and whitespace-only `source` each raise `HostDurableError`.

## Follow-up Validation

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q` | passed: `19 passed in 0.13s` |
| `source .venv/bin/activate && pytest tests/host/test_event_log_multiprocess.py -q` | passed: `1 passed in 0.28s` |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | passed: `0 errors, 0 warnings, 0 informations` |

## Finding Title Status Update Result

- Source review artifacts were not modified because the handoff allowed file list does not include the DS/MiMo/controller review artifact files.
- Status mapping recorded here:
  - `DS-F1`: `未修复` -> `已修复`
  - `DS-F2`: `未修复` -> `已修复`
  - `DS-F3`: `未修复` -> `已修复`
  - `DS-F4`: `未修复` -> `已修复`

## New Risks / Open Questions

- No new open questions.
- No plan deviation.
- No new runtime, Engine, Fins, Service, UI, command path, state machine, projection, ToolRuntime, Remote, payload descriptor helper, artifact helper, or liveness operation scope was introduced.

## Residual Risk Classification

- `DS-F1`: fixed in current slice; no residual accepted-finding risk.
- `DS-F2`: fixed in current slice; no residual accepted-finding risk.
- `DS-F3`: fixed in current slice; no residual accepted-finding risk.
- `DS-F4`: fixed in current slice; no residual accepted-finding risk.
- Documentation README sync was not performed because README files are outside the allowed file list for this handoff.
