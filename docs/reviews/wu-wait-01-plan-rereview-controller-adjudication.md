# WU-WAIT-01 Plan Re-Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 Callback Endpoint / Auth / Replay
- Gate: re-review
- Plan artifact: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- Plan fix artifact: `docs/reviews/wu-wait-01-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/plan-review-20260621-222106.md`
  - `docs/reviews/plan-review-20260621-222241.md`

## Decision

Both re-review paths pass. The controller accepts the fixed plan for implementation.

## Accepted Findings Final Status

| Finding | Final status | Evidence |
|---|---|---|
| F01 dispatch wakeup gap | 已修复 | Plan now requires `CallbackWaitResolvePort` to return `RunSnapshot` plus `idempotent_replay` and preserve non-replay dispatch wakeup. |
| F02 digest formula conflict | 已修复 | Plan aligns callback payload digest with existing wait resolution material: `wait_id + idempotency_key + outcome`. |
| F03 transport vs Host statuses | 已修复 | Plan separates Service/Web transport diagnostics from Host adapter statuses. |
| F04 INVALID_STATE mapping | 已修复 | Plan forbids parsing `HostApiError.message` and allows race cases to collapse to `INVALID_WAIT_STATE`. |
| F05 JSON outcome mapping | 已修复 | Plan defines completed / failed / cancelled / lost JSON shapes and tests. |
| F06 deadline / expires semantics | 已修复 | Plan states only `deadline_at` is currently populated and `expires_at` is schema-reserved. |
| F07 completed_at usage | 已修复 | Plan states `completed_at` is transport/audit input only for this WU and is not persisted by `resolve_wait`. |
| F08 auth 401 / 403 mapping | 已修复 | Plan defines deterministic Service mapper behavior for 401 vs 403. |
| F09 RunRow / RunSnapshot mismatch | 已修复 | Plan requires the callback resolve port to convert internal rows to `RunSnapshot`. |

## Residual Risks

No blocking residual risk remains for the plan gate. Two low implementation risks remain tracked inside the re-review artifacts:

- `CallbackWaitResolvePort` concrete implementation location must be chosen during Slice 1 while preserving import boundaries.
- Credential extraction and secret verification remain deployment-specific Service/Web responsibilities; this WU only adds typed protocol and framework-neutral mapper.

Both are within approved implementation scope and do not block the accepted plan commit.

## Next Gate

Proceed to accepted plan commit, then implementation Slice 1.
