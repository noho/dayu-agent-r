# WU-WAIT-01 Plan Fix - AgentCodex

## Scope

- Work unit: WU-WAIT-01 Callback Endpoint / Auth / Replay
- Gate: fix
- Fixed plan artifact: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- Review inputs:
  - `docs/reviews/plan-review-20260621-220834.md`
  - `docs/reviews/plan-review-20260621-221033.md`
  - `docs/reviews/wu-wait-01-plan-review-controller-adjudication.md`

## Fix Summary

All accepted findings were fixed in the plan artifact. The core direction remains unchanged: callback completion is a transport adapter into the existing `resolve_wait` pipeline; Host core stays framework-independent; Service/Web owns HTTP transport parsing and status mapping; no durable schema migration, new wait lifecycle, Engine awaiting model change, issue-90 poller loop, issue-92 physical cancel, or concrete HTTP framework was introduced.

Slice count remains 2. The fix does not create a third slice because the new command-layer callback resolve port belongs to Slice 1's Host state-governance boundary, while Service transport mapping remains Slice 2.

## Findings Fixed

### F01 Dispatch wakeup gap

Fixed by replacing direct Host adapter calls to `DefaultHostResolveWaitService` with an injected `CallbackWaitResolvePort` implemented in the command layer. The plan now requires the port to return `RunSnapshot` plus `idempotent_replay`, convert any internal `RunRow` before returning, and wake dispatch exactly once when a non-replay resolve creates dispatch. Tests now require wake once on accepted and no wake on replay.

### F02 Digest formula conflict

Fixed by aligning `payload_digest` with existing wait resolution digest material: `wait_id + idempotency_key + outcome`. The plan now explicitly excludes `observed_at` and `completed_at` from digest and replay conflict semantics, and requires replay/conflict tests.

### F03 Transport failures mixed into Host adapter status

Fixed by removing `TRANSPORT_REJECTED` and `MALFORMED_PAYLOAD` from Host adapter status. The plan now defines them as Service/Web transport mapper diagnostics that happen before Host adapter invocation. Host tests exclude HTTP transport cases; Service tests cover them.

### F04 INVALID_STATE disambiguation

Fixed by prohibiting parsing `HostApiError.message`. The plan now states stable pre-resolve cancelled/lost classification is allowed, but concurrent races and resolver `INVALID_STATE` collapse safely to `INVALID_WAIT_STATE` unless a future structured subcode/result is added.

### F05 JSON outcome mapping

Fixed by adding full JSON examples for `completed`, `failed`, `cancelled`, and `lost`, and by requiring Service mapper tests for all four outcome kinds.

### F06 Deadline / expires semantics

Fixed by grounding stale behavior in current code: only `deadline_at` is currently populated; `expires_at` is schema-reserved and currently written as `None`. The plan now defines UTC ISO-8601 parsing and adds tests for no deadline/expires and deadline exceeded.

### F07 completed_at usage

Fixed by stating `completed_at` is transport/audit input used for validation and stale classification only in this WU. It is not persisted by `resolve_wait`, not added to `ResolveWaitRequest` payload, and not included in digest.

### F08 Auth 401 / 403 mapping

Fixed by defining deterministic Service mapper behavior: missing, malformed, expired, or invalid credentials return 401; authenticated-but-forbidden credentials return 403.

### F09 RunRow / RunSnapshot mismatch

Fixed through the callback resolve port contract. The plan now requires conversion to `RunSnapshot` before producing the callback adapter result.

## Findings Not Fixed

None. All accepted findings were fixed.

## Blocking Open Questions

None.

## Validation / Read Commands Performed

- `sed -n '1,260p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '261,520p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '1,260p' docs/reviews/plan-review-20260621-220834.md`
- `sed -n '1,260p' docs/reviews/plan-review-20260621-221033.md`
- `sed -n '1,260p' docs/reviews/wu-wait-01-plan-review-controller-adjudication.md`
- `git status --short`
- `rg -n "DefaultHostResolveWaitService|ResolveWaitResult|TRANSPORT_REJECTED|MALFORMED_PAYLOAD|expires_at|completed_at|RunRow|RunSnapshot|INVALID_STATE|401|403|wake" docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '50,105p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '95,290p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '290,430p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `sed -n '430,520p' docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- `git diff -- docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md docs/reviews/wu-wait-01-plan-fix-codex.md`
- `rg -n "DefaultHostResolveWaitService" docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md docs/reviews/wu-wait-01-plan-fix-codex.md`
- `rg -n "TRANSPORT_REJECTED|MALFORMED_PAYLOAD" docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md docs/reviews/wu-wait-01-plan-fix-codex.md`
- `rg -n "ResolveWaitResult|CallbackWaitResolvePort|RunRow|RunSnapshot|completed_at|observed_at|INVALID_STATE|401|403|wake" docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md docs/reviews/wu-wait-01-plan-fix-codex.md`
- `sed -n '1,220p' docs/reviews/wu-wait-01-plan-fix-codex.md`

No code tests or pyright were run because this fix gate was restricted to plan/review artifact edits and explicitly prohibited implementation changes.
