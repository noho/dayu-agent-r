# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 code-review fix

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Code-review adjudication: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-controller-adjudication.md`
- Fixed findings:
  - `P3-H-S2-CR-F01`
  - `P3-H-S2-CR-F02`

## Fix Summary

- `dayu/fins/ingestion/wait_adapter.py`
  - `_failure_message(...)` now accepts only `FinsResultSummary`.
  - It returns `result.error_message` only when non-empty.
  - It raises `ValueError` if a failed observation result lacks business-readable `error_message`.
  - It no longer reads `snapshot.message`, so process-local observation diagnostics cannot become LLM-visible failed wait messages.

- `tests/fins/test_fins_ingestion_runtime.py`
  - Added explicit assertions that cancellation-before-activation, activation failure, and producer-without-result terminal summaries use helper-derived error messages and do not contain `"Observation"`.

- `tests/fins/test_fins_ingestion_tools.py`
  - Added a malformed failed snapshot regression test proving wait adapter rejects missing `error_message` instead of falling back to `snapshot.message`.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py::test_cancel_prepared_observation_prevents_later_activation_submit tests/fins/test_fins_ingestion_runtime.py::test_unexpected_activation_exception_terminalizes_prepared_observation tests/fins/test_fins_ingestion_runtime.py::test_observed_producer_without_result_uses_helper_failure_message tests/fins/test_fins_ingestion_tools.py::test_fins_wait_poll_adapter_rejects_failed_result_without_message -q`
  - Result: `4 passed, 3 warnings`

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - Result: `215 passed, 3 warnings`

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py --cov=dayu.fins.direct_event_text --cov-report=term-missing -q`
  - Result: `136 passed, 3 warnings`
  - `dayu/fins/direct_event_text.py`: `86%` coverage

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

- `git diff --check`
  - Result: passed

- `rg -n "snapshot\\.message\\.strip|Fins operation failed|did not complete successfully|error_message=.*Observation|fallback_message=.*Observation|hint=\\\"|message=\\\"Fins operation was cancelled before completion|请检查 Fins ingestion" dayu/fins/ingestion_runtime.py dayu/fins/ingestion/wait_adapter.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py`
  - Result: no matches.

## Propagation Audit

- Observation diagnostics remain in `record.message` for process-local diagnosis.
- Terminal `FinsResultSummary.error_message` now comes from `direct_event_text.direct_failure_message(...)`.
- Wait adapter failed outcome reads only `FinsResultSummary.error_message`.
- Missing `error_message` is now a contract violation instead of a downstream fallback.

## Residual Risk

- Legacy job sidecar messages and adapter-provided progress messages remain outside S2 scope, as recorded in the plan and controller validation.
