# WU-WAIT-03 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: Slice 1 code review
- Slice: Host Lifecycle Contract And Poller Diagnostics
- Implementation artifact: `docs/reviews/wu-wait-03-slice1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-wait-03-slice1-code-review-mimo.md`
  - `docs/reviews/wu-wait-03-slice1-code-review-ds.md`

## Controller Decision

Verdict: `fix-required`

Both reviews confirmed the Slice 1 correctness core: typed lifecycle contract, durable outcome mapping, schema CHECK / schema version alignment, CAS behavior, retry behavior, and late-result isolation are sound. Current fix is required only for small Slice 1 contract/test polish items. The Fins adapter return type finding is deferred to Slice 2 because this slice explicitly forbids `dayu/fins/**` changes and the accepted plan assigns Fins mapping to Slice 2.

## Finding Adjudication

| Finding | Source | Decision | Required action |
|---|---|---|---|
| `FinsIngestionWaitPollAdapter.abandon_wait` still returns `None` | MiMo F1 / DS F1 | deferred-with-owner | Owner: WU-WAIT-03 Slice 2. Do not fix in Slice 1 because `dayu/fins/**` is forbidden in this slice. Slice 2 must update the Fins adapter to return `WaitExternalJobLifecycleResult` and run Fins focused tests plus pyright. Current Slice 1 may record this as deferred risk only. |
| New lifecycle types missing from `dayu.host.wait_adapter.__all__` | MiMo F2 / DS F2 | accepted | Add `WaitExternalJobLifecycleAction`, `WaitExternalJobLifecycleApplied`, `WaitExternalJobLifecycleUnsupported`, `WaitExternalJobLifecycleNoop`, and `WaitExternalJobLifecycleResult` to `__all__`. |
| Cancelled wait + missing adapter branch lacks focused test | DS F3 | accepted | Add a focused test proving cancelled wait with missing poll adapter writes `MISSING_ADAPTER` backoff, does not set `poll_abandoned_at`, increments adapter error, and remains retryable. |
| `_last_outcome_for_lifecycle_result` TypeError message uses ambiguous "unsupported" wording | DS F4 | accepted | Change the defensive TypeError message to distinguish unknown result type from the normal `WaitExternalJobLifecycleUnsupported` result. |
| `_poller_with_resolver` test helper parameter type too narrow | DS F5 | accepted | Change the test helper annotation to `WaitResolvePort`. |

## Non-finding Confirmations

- Host command cancellation state machine is unchanged.
- Cancelled wait lifecycle path does not call `resolve_wait(...)`.
- New durable outcome values align with schema CHECK and schema version.
- No new public Host API, Engine contract, durable table / column, provider registry, or watchdog was introduced.
- README non-update decision is acceptable for Slice 1 because the change is internal Host adapter/poller diagnostic contract plus tests.

## Required Fix Validation

After fix, run:

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q
source .venv/bin/activate && pytest tests/host/test_wait_record_state.py tests/host/test_durable_schema.py -q
source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py -q
source .venv/bin/activate && pyright
git diff --check
```

## Residual Risks

- Fins adapter lifecycle result mapping remains deferred to Slice 2 with owner WU-WAIT-03 Slice 2.
- Existing schema version 18 compatibility remains intentionally unsupported under the project schema-change rule; current WU treats schema 19 as fresh truth.
