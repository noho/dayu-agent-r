# WU-WAIT-03 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: Slice 2 code review
- Slice: Fins Adapter/Runtime Mapping And Provider-focused Tests
- Implementation artifact: `docs/reviews/wu-wait-03-slice2-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-wait-03-slice2-code-review-mimo.md`
  - `docs/reviews/wu-wait-03-slice2-code-review-ds.md`

## Controller Decision

Verdict: `fix-required`

Both reviews confirm that the Slice 2 production behavior is correct: `FinsIngestionWaitPollAdapter.abandon_wait(...)` now returns typed lifecycle results, valid handles request cancel then release local tracking, corrupt / missing / LOST / non-transient / transient paths map to the accepted plan semantics, lifecycle messages do not leak internal identifiers, and runtime tests cover prepared and submitted observation abandon behavior.

One current-slice test fix is required. The accepted plan explicitly requires non-transient observation errors during cancel or abandon to return `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`. Current tests cover the abandon-side non-transient error path but not the cancel-side path. The production implementation already appears correct, so the required fix is a narrow regression test only.

## Finding Adjudication

| Finding | Source | Decision | Required action |
|---|---|---|---|
| `cancel_observation(...)` non-transient error branch lacks direct test coverage | AgentDS Finding 1 | accepted | Add a focused Fins adapter test using `cancel_errors` with `FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE`; assert `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`, `cancelled_handles == (handle_id,)`, and `abandoned_handles == ()`. |
| `abandon_observation(...)` `PERMANENT_NOT_FOUND` path lacks direct test coverage | AgentMiMo residual risk | rejected-with-reason | The existing missing-observation and LOST tests already cover the missing semantic outcome, and the accepted plan does not require separate direct coverage for both runtime throw sites. This remains low residual risk, not a current fix. |
| `_BlockingArtifactUploadRunner` timing flakiness risk | AgentMiMo residual risk | informational | No failing evidence. Existing timeout and event synchronization are sufficient for the current focused test. Revisit only if CI proves flakiness. |
| cancel succeeds but abandon fails leaves process-local handle until restart | AgentDS residual risk | informational | This is the accepted best-effort cleanup tradeoff from the plan. Host cancellation correctness does not depend on provider cleanup completing. |
| cancel + abandon double cancellation request | AgentDS residual risk | informational | Runtime cancellation request is idempotent. This is redundant but not a correctness issue. |

## Required Fix Validation

After fix, run:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q
source .venv/bin/activate && pyright
git diff --check
```

## Residual Risks

- Provider lifecycle cleanup remains best-effort. If provider abandon cleanup fails after a successful cancel, Host records a governed no-op and does not make terminal cancellation depend on local registry cleanup.
- Poller-disabled deployments still rely on durable Host cancellation truth and will not execute external lifecycle adapter actions until production polling is configured.
