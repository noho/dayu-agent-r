# WU-WAIT-03 Slice 1 Code Re-review Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: Slice 1 code re-review
- Slice: Host Lifecycle Contract And Poller Diagnostics
- Fix artifact: `docs/reviews/wu-wait-03-slice1-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-wait-03-slice1-code-rereview-mimo.md`
  - `docs/reviews/wu-wait-03-slice1-code-rereview-ds.md`

## Controller Decision

Verdict: `pass`

Both re-review agents verified that all current-slice accepted findings are fixed. Blocking findings: 0. The Fins adapter return type finding remains `deferred-with-owner` to WU-WAIT-03 Slice 2 and is not a Slice 1 blocker.

## Finding Final Status

| Finding | Final status | Evidence |
|---|---|---|
| Add lifecycle result symbols to `dayu.host.wait_adapter.__all__` | 已修复 | `WaitExternalJobLifecycleAction`, `WaitExternalJobLifecycleApplied`, `WaitExternalJobLifecycleNoop`, `WaitExternalJobLifecycleResult`, and `WaitExternalJobLifecycleUnsupported` are exported. |
| Add cancelled wait + missing adapter focused test | 已修复 | New test verifies empty poll adapter registry on a cancelled wait records `MISSING_ADAPTER`, does not mark abandoned, leaves `poll_abandoned_at` unset, and remains retryable. |
| Clarify `_last_outcome_for_lifecycle_result` TypeError wording | 已修复 | Defensive error message now uses unknown-type wording, separate from normal unsupported lifecycle result semantics. |
| Relax `_poller_with_resolver` helper annotation to `WaitResolvePort` | 已修复 | Test helper now uses the protocol type. |
| `FinsIngestionWaitPollAdapter.abandon_wait` return type | deferred-with-owner | Owner: WU-WAIT-03 Slice 2. Slice 1 intentionally did not modify `dayu/fins/**`. |

## Validation

Controller reran the fix validation before re-review:

- `pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q`: 35 passed.
- `pytest tests/host/test_wait_record_state.py tests/host/test_durable_schema.py -q`: 60 passed.
- `pytest tests/host/test_open_host_runtime.py tests/host/test_package_exports.py -q`: 31 passed.
- `pyright`: 0 errors.
- `git diff --check`: passed.

## Residual Risks

- Fins adapter lifecycle result mapping remains owned by WU-WAIT-03 Slice 2.
- Existing schema version 18 compatibility remains intentionally unsupported under the project schema-change rule; schema version 19 is the fresh truth for this branch.

## Next Gate

Proceed to accepted slice commit for WU-WAIT-03 Slice 1.
