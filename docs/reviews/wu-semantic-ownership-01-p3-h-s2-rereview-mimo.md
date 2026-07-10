# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 code re-review

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Mode: re-review of code-review fix
- Review inputs:
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-fix-codex.md`
  - Current diff S2 related files
- Accepted findings to verify:
  - `P3-H-S2-CR-F01`
  - `P3-H-S2-CR-F02`

## Findings

未发现实质性问题。

## Finding Verification

### P3-H-S2-CR-F01: `_failure_message` fallback to `snapshot.message`

**Verdict: CLOSED**

Evidence:

1. `dayu/fins/ingestion/wait_adapter.py:556-566` — `_failure_message` now:
   - Accepts only `FinsResultSummary` (not snapshot)
   - Returns `result.error_message` only when non-empty (line 564)
   - Raises `ValueError` if failed result lacks business-readable `error_message` (line 566)
   - Does NOT read `snapshot.message` anywhere

2. Call site `wait_adapter.py:488` — `_failed_outcome` passes `_failure_message(result)` where `result` comes from `_required_result(snapshot)` which returns `snapshot.result` (typed `FinsResultSummary`).

3. Propagation audit confirms:
   - `snapshot.message` (process-local observation diagnostic) remains in `record.message` only
   - Terminal `FinsResultSummary.error_message` comes from `direct_event_text.direct_failure_message(...)`
   - Wait adapter reads only `FinsResultSummary.error_message`

### P3-H-S2-CR-F02: Test coverage for observation terminal `error_message` non-leakage

**Verdict: CLOSED**

Evidence:

All four required test scenarios exist and assert `"Observation" not in error_message`:

1. **Cancel before activation** — `test_cancel_prepared_observation_prevents_later_activation_submit` (runtime test:2444-2473)
   - Asserts `cancelled.result.error_message == direct_failure_message(error_kind=FinsErrorKind.CANCELLED, fallback_message=None)`
   - Asserts `"Observation" not in cancelled_error_message` (line 2471)

2. **Activation failed** — `test_unexpected_activation_exception_terminalizes_prepared_observation` (runtime test:2666-2693)
   - Asserts `snapshot.result.error_message == direct_failure_message(error_kind=FinsErrorKind.EXECUTION, fallback_message=None)`
   - Asserts `"Observation" not in activation_error_message` (line 2693)

3. **Producer without result** — `test_observed_producer_without_result_uses_helper_failure_message` (runtime test:2696-2743)
   - Asserts `snapshot.result.error_message == direct_failure_message(error_kind=FinsErrorKind.EXECUTION, fallback_message=None)`
   - Asserts `"Observation" not in missing_result_error_message` (line 2743)

4. **Malformed failed snapshot** — `test_fins_wait_poll_adapter_rejects_failed_result_without_message` (tools test:1626-1652)
   - Creates snapshot with `error_message=None` and internal `message="Observation activation failed."`
   - Asserts `pytest.raises(ValueError, match="must contain error_message")` — proves adapter rejects instead of falling back

## Open Questions

无

## Residual Risk

- Legacy job sidecar messages and adapter-provided progress messages remain outside S2 scope, as recorded in the plan and controller validation.
