# WU-WAIT-03 Slice 1 Fix

## Scope

- Work unit: WU-WAIT-03 / GitHub issue-92.
- Gate executed: Slice 1 fix only.
- Source adjudication: `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md`.
- Boundary honored: did not enter re-review or later gates; did not modify Fins, Engine, Service, UI, runtime, config, prompt, tool schema, control doc, plan artifact, or review artifacts.

## Accepted Findings Fixed

- Added lifecycle result contract symbols to `dayu.host.wait_adapter.__all__`:
  - `WaitExternalJobLifecycleAction`
  - `WaitExternalJobLifecycleApplied`
  - `WaitExternalJobLifecycleUnsupported`
  - `WaitExternalJobLifecycleNoop`
  - `WaitExternalJobLifecycleResult`
- Added focused cancelled wait + missing poll adapter coverage in `tests/host/test_wait_adapter_polling.py`:
  - uses an empty `WaitPollAdapterRegistry`;
  - asserts `adapter_errors=1`;
  - asserts abandoned count remains `0`;
  - asserts `poll_last_outcome=MISSING_ADAPTER`;
  - asserts `poll_abandoned_at is None`;
  - asserts the cancelled wait remains retryable through cleared claim and retry backoff state.
- Changed `_last_outcome_for_lifecycle_result(...)` defensive `TypeError` message to use unknown-type wording, keeping it distinct from the normal `WaitExternalJobLifecycleUnsupported` lifecycle result.
- Changed `_poller_with_resolver(...)` test helper resolver annotation to `WaitResolvePort`.

## Files Changed

- `dayu/host/wait_adapter.py`
- `tests/host/test_wait_adapter_polling.py`
- `docs/reviews/wu-wait-03-slice1-fix-codex.md`

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q`
  - Passed: 35 tests.
- `source .venv/bin/activate && pytest tests/host/test_wait_record_state.py tests/host/test_durable_schema.py -q`
  - Passed: 60 tests.
- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py -q`
  - Passed: 17 tests.
- `source .venv/bin/activate && pyright`
  - Passed: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Passed.

## Deferred Finding To Slice 2

- `FinsIngestionWaitPollAdapter.abandon_wait` return type remains deferred-with-owner to WU-WAIT-03 Slice 2 per controller adjudication. This fix intentionally did not modify `dayu/fins/**` or `tests/fins/**`.

## Residual Risks / Owners

- Fins adapter lifecycle mapping remains owned by WU-WAIT-03 Slice 2.
- Existing schema version 18 compatibility remains intentionally unsupported under the project schema-change rule; current WU treats schema 19 as fresh truth.
- No additional current-slice file was required beyond the allowed files.

## Completion Status

- Slice 1 fix gate complete.
- Stopped before re-review and all later gates, as requested.
