# Phase 13 Plan Review Controller Adjudication

## Gate

Phase 13 plan review.

Reviewed artifacts:
- `docs/reviews/phase13-plan-review-mimo-20260529.md`
- `docs/reviews/phase13-plan-review-ds-20260529.md`

Plan target:
- `docs/host/phase13-audit-tool-trace-outbox-plan.md`

Design truth:
- `docs/host/design.md` §14 / §14.1 / §15 / §16
- `docs/host/implementation-control.md` Phase 13
- `docs/reviews/phase13-design-discussion-controller-adjudication-20260529.md`

## Controller Verdict

Plan review does not pass yet. One blocking finding is accepted and requires a plan fix before implementation handoff.

The fix should also address accepted non-blocking clarifications where they remove real implementation ambiguity without expanding Phase 13 scope.

## Finding Decisions

### DS-F1 read_outbox_terminal_items side-effect boundary

Decision: accepted, blocking.

Reason: Based on the Host design goal that command truth and projection state must stay separated, the plan must precisely state whether read can advance projection-local state. The current wording says read is side-effect free while also allowing best-effort catch-up that writes projection rows and checkpoints. That ambiguity would force the implementation agent to choose semantics.

Required plan fix: replace the side-effect-free wording with an explicit boundary: read must not write EventLog, mutate Run / Attempt, or change Outbox item state, but may run projection-local catch-up before returning; projection catch-up failure must be visible through `projection_status`.

### MiMo-F1 Outbox dedupe_key alignment

Decision: accepted, plan clarification required.

Reason: Phase 13 must preserve the P10.5 terminal identity contract. Since current `HostEvent.dedupe_key` is the event id, the plan should not allow `run_id + terminal_event_id` as an alternative.

Required plan fix: fix `OutboxTerminalItem.dedupe_key = terminal_event_id`.

### MiMo-F2 idempotency_key versus dedupe_key boundary

Decision: accepted, plan clarification required.

Reason: The two keys serve different owners. Blurring them invites UI / Service code to depend on projection upsert internals.

Required plan fix: define `idempotency_key` as the OutboxSink durable upsert / drain idempotency key, and `dedupe_key` as the UI / Service key aligned with `HostEvent.dedupe_key`.

### DS-F2 purge_session interaction

Decision: accepted as material plan clarification, not Phase 13 implementation scope expansion.

Reason: `purge_session` tombstone and retention cleanup are already assigned to Phase 15. However, the Phase 13 plan must explicitly say that current Audit / Tool Trace / Outbox sinks do not implement purge tombstone behavior, and that purge-related audit/outbox/tool-trace cleanup remains Phase 15 owner.

Required plan fix: add a non-goal / residual risk entry assigning purge tombstone audit record, outbox cleanup, tool trace cleanup, and retention matrix to Phase 15; do not add purge implementation to Phase 13.

### DS-F3 tool trace diagnostic whitelist

Decision: accepted, plan clarification required.

Reason: A typed projection consumer cannot rely on vague diagnostic categories. The plan must either enumerate the first whitelist or make whitelist discovery the first explicit Slice 2 step with stop conditions.

Required plan fix: add an initial conservative whitelist or define a concrete Slice 2 discovery step that only admits named EventLog event types / typed payload views and stops if needed refs require Engine or ToolRuntime contract changes.

### DS-F4 audit marker table naming

Decision: accepted, plan clarification required.

Reason: `host_audit_jsonl_events` sounds like an audit event store and weakens the design boundary that JSONL is the audit artifact while SQLite marker rows are sink-local idempotency support.

Required plan fix: rename the optional marker table in the plan to `host_audit_sink_markers` or `host_audit_jsonl_idempotency`, and state that it is not an audit event store.

### DS-F5 RUN_LOST outbox mapping

Decision: accepted, plan clarification required.

Reason: `HostTerminalStatus` currently lacks `LOST`. Phase 13 should not introduce a public lost terminal item without a public display contract.

Required plan fix: state that Phase 13 OutboxSink skips `RUN_LOST` with a projection detail code and does not create public terminal item; LOST notification can be reconsidered in a recovery / public terminal contract gate.

### DS-F6 tool trace query helper pagination

Decision: accepted as low plan clarification.

Reason: Query helpers should not force implementation to decide return cardinality.

Required plan fix: specify return ordering and pagination or exact single-row semantics for each helper.

### DS-F7 HostClosedError path

Decision: rejected as requiring no plan change.

Reason: Existing `_PublicHostHandle` closed-handle guard pattern is sufficient and plan already names `HostClosedError`.

### DS-F8 projection-lag anti-leak smoke

Decision: accepted as low test clarification.

Reason: The design goal is no missed offline terminal notification. A lagged Outbox projection case is a realistic overlap scenario and should be named in Slice 4 tests.

Required plan fix: add a Slice 4 test case where first drain/read returns `projection_status=LAGGED`, later catch-up plus second read returns the terminal item without duplicate display.

### DS-F9 AGENTS compliance

Decision: accepted as pass evidence; no fix required.

## Next Gate

Return to planning fix. The planning specialist must update only `docs/host/phase13-audit-tool-trace-outbox-plan.md` and report a fix summary. After the fix, run plan re-review with MiMo and DS before any implementation gate.
