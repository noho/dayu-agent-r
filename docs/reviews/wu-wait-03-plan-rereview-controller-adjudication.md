# WU-WAIT-03 Plan Re-review Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: plan re-review
- Plan artifact: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Plan-fix artifact: `docs/reviews/wu-wait-03-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-wait-03-plan-rereview-mimo.md`
  - `docs/reviews/wu-wait-03-plan-rereview-ds.md`

## Controller Decision

Verdict: `pass`

Both re-review agents verified that all controller-accepted plan review findings are closed. Blocking findings: 0. The plan is code-generation-ready and may enter accepted plan commit gate.

## Finding Final Status

| Finding group | Final status | Evidence |
|---|---|---|
| `WaitPollLastOutcome.ABANDON_UNSUPPORTED` / `ABANDON_NOOP` and enum serialization / validation handling | 已修复 | Plan now explicitly requires adding both enum values, preserving value-based `StrEnum` serialization/deserialization, row validation, and roundtrip / row validation tests. |
| unsupported/noop durable terminal marker and re-claim fencing | 已修复 | Plan now requires parameterizing `mark_wait_record_poll_abandoned(...)` with keyword-only `last_outcome`, and requires unsupported/noop to set `poll_abandoned_at`. |
| Fins corrupt token, missing observation, non-transient observation error, and transient unavailable mapping | 已修复 | Plan now maps corrupt/missing/non-transient errors to `WaitExternalJobLifecycleNoop` with explicit reasons and keeps `TRANSIENT_UNAVAILABLE` retryable by re-raising. |
| `WaitPollOnceResult.abandoned` semantics | 已修复 | Plan now states applied / unsupported / noop terminal lifecycle markers all increment `abandoned` after successful CAS write and no new counter is added. |
| unsupported/noop CAS conflict and prepared observation cancel + abandon tests | 已修复 | Plan now explicitly adds these tests to Slice 1 and Slice 2 validation. |
| `REVOKE` action selection rule | 已修复 | Plan now explains adapter returns the strongest provider-supported lifecycle action it actually took; `REVOKE` is for invalidating future delivery/result without necessarily stopping physical work; Fins returns `ABANDON`. |

## Residual Risks

No unclassified residual risk remains. Existing residual risks are deferred with owners:

- Provider-specific physical cancel support: provider-specific adapter owners under GitHub Issue #92 / #87.
- Poller disabled deployment lifecycle action: Service composition / WU-WAIT-04.
- Fins cooperative cancellation checkpoints: Fins provider/runtime owners.
- Richer lifecycle diagnostic projection: future tool trace / diagnostic projection work.

## Next Gate

Proceed to accepted plan commit. After the commit, update the control document with the accepted plan commit hash and move the next entry point to implementation.
