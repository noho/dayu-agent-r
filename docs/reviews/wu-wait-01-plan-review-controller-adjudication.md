# WU-WAIT-01 Plan Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 Callback Endpoint / Auth / Replay
- Gate: plan review
- Plan artifact: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260621-220834.md`
  - `docs/reviews/plan-review-20260621-221033.md`

## Decision

Plan direction is accepted, but the current plan is not ready for implementation. The controller moves the work unit to the `fix` gate. AgentCodex must update the plan artifact before re-review.

Core accepted direction:

- Callback completion remains a transport adapter into the existing `resolve_wait` pipeline.
- Host core stays framework-independent.
- Service/Web owns HTTP transport parsing and HTTP status mapping.
- No Engine awaiting model change, no durable schema migration, no new wait lifecycle, no issue-90 poller loop, and no issue-92 physical cancel.

## Finding Adjudication

### WU-WAIT-01-PLAN-F01 - accepted - Dispatch wakeup gap

- Source findings: DS-F01, related MiMo Finding 03.
- Severity: high.
- Evidence: `dayu/host/command.py:769-770` wakes dispatch after non-replay `resolve_wait`; the plan proposed direct `DefaultHostResolveWaitService` use but did not preserve this wakeup.
- Ruling: accepted.
- Required plan fix:
  - Define a callback resolve port / command-layer adapter that returns both latest `RunSnapshot` and `idempotent_replay`, and guarantees non-replay resume dispatch wakeup when a dispatch record is created.
  - The plan must not leave wakeup logic to implementation inference.
  - Add tests requiring callback accepted path wakes dispatch once and replay path does not wake dispatch again.

### WU-WAIT-01-PLAN-F02 - accepted - Callback digest formula conflicts with existing resolve_wait digest

- Source findings: MiMo Finding 01.
- Severity: high.
- Evidence: `dayu/host/waiting.py:1132-1146` computes wait resolution digest from `{wait_id, idempotency_key, outcome}` only; plan proposed callback pre-check digest over `{wait_id, idempotency_key, completed_at, outcome}`.
- Ruling: accepted.
- Required plan fix:
  - Make callback digest validation use the same semantic material as existing wait resolution digest, or remove independent pre-check and rely on the resolve pipeline for idempotency conflict.
  - If payload digest remains in callback envelope, define it as transport integrity over the canonical outcome material and explicitly state `observed_at` / `completed_at` do not affect replay conflict.
  - Add tests for same callback replay and same key different outcome.

### WU-WAIT-01-PLAN-F03 - accepted - Transport failures are mixed into Host adapter status

- Source findings: MiMo Finding 02.
- Severity: medium.
- Ruling: accepted.
- Required plan fix:
  - Separate Service transport status from Host callback adapter status.
  - `TRANSPORT_REJECTED` and `MALFORMED_PAYLOAD` belong to Service/Web mapper and must not require calling Host adapter.
  - Host adapter tests should not include HTTP method/content-type/path-body mismatch cases; Service tests should.

### WU-WAIT-01-PLAN-F04 - accepted - Error disambiguation relies on unstable INVALID_STATE interpretation

- Source findings: DS-F02.
- Severity: medium.
- Ruling: accepted.
- Required plan fix:
  - Do not parse `HostApiError.message`.
  - Define a reliable mapping strategy for `INVALID_STATE`: pre-resolve read may classify already-cancelled/lost states when stable, but concurrent changes must safely collapse to `INVALID_WAIT_STATE` unless a structured subcode is added.
  - State clearly whether cancelled/lost late callback classification is best-effort under races or requires a narrow structured result change.

### WU-WAIT-01-PLAN-F05 - accepted - JSON outcome mapping is underspecified

- Source findings: DS-F03.
- Severity: medium.
- Ruling: accepted.
- Required plan fix:
  - Provide full JSON shapes or examples for `completed`, `failed`, `cancelled`, and `lost`.
  - Add Service mapper tests for all four outcome kinds.

### WU-WAIT-01-PLAN-F06 - accepted - Wait deadline / expires semantics need current-code grounding

- Source findings: DS-F04, MiMo Finding 04, MiMo Finding 06.
- Severity: low.
- Evidence: `WaitRecordRow.deadline_at` and `expires_at` both exist, but `_wait_record_row(...)` currently writes `deadline_at` from `await_spec.deadline` and `expires_at=None`.
- Ruling: accepted.
- Required plan fix:
  - State current behavior: only `deadline_at` is currently populated; `expires_at` is schema-reserved unless a future path populates it.
  - Define UTC timestamp parsing using existing Host timestamp helpers where available.
  - Add tests for no deadline/expires not being rejected as stale, and deadline exceeded being rejected as stale.

### WU-WAIT-01-PLAN-F07 - accepted - completed_at usage is unclear

- Source findings: DS-F05.
- Severity: low.
- Ruling: accepted.
- Required plan fix:
  - State whether `completed_at` is only transport/audit input used for stale/digest checks and not persisted by `resolve_wait`, or define an explicit persistence location.
  - Current phase should avoid changing `resolve_wait` payload schema unless directly required.

### WU-WAIT-01-PLAN-F08 - accepted - Auth 401 / 403 mapping is underspecified

- Source findings: MiMo Finding 05.
- Severity: low.
- Ruling: accepted.
- Required plan fix:
  - Define deterministic HTTP mapping for auth failures in the Service mapper, for example missing/invalid credential -> 401 and authenticated-but-forbidden -> 403, or a single documented 401 policy.

### WU-WAIT-01-PLAN-F09 - accepted via F01 - RunRow / RunSnapshot mismatch

- Source findings: DS-F06.
- Severity: low.
- Ruling: accepted as covered by F01.
- Required plan fix:
  - The callback resolve port must return `RunSnapshot` or explicitly convert `RunRow` with existing conversion before producing callback adapter result.

## Rejected Findings

None.

## Deferred Findings

None.

## Residual Risks

No residual risk is accepted for implementation yet. All material review findings above must be fixed in the plan artifact and re-reviewed before the plan can be accepted.

## Next Gate

Proceed to `fix` gate. AgentCodex must update `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md` and produce a plan-fix artifact under `docs/reviews/`.
