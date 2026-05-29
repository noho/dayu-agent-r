# Phase 13 Design Discussion Controller Adjudication

## Scope

Work unit: Phase 13 Audit / Tool Trace / Outbox Projections.

Design truth:
- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §14.1 Tool Trace Hot / Cold Storage
- `docs/host/design.md` §15 Audit
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox
- `docs/host/implementation-control.md` Phase 13

## Accepted Design Discussion Decisions

### D1. Audit / Tool Trace / Outbox remain projection / sink only

Decision: accepted.

Based on the design goal that Host durable truth is Session / Run / Attempt / EventLog governance, Audit / Tool Trace / Outbox must consume committed EventLog through typed sink contracts and must not participate in Host command path success, recovery, resume, memory, or Run state transitions.

### D2. Outbox only covers offline terminal / final-answer notification

Decision: accepted.

Outbox solves the offline terminal notification gap left by P10.5. It must not become a full timeline, reasoning, progress, preview, or general read model path, and it must not change `watch_session_events(...)` live-only semantics.

### D3. Outbox read / drain API is the only Phase 13 additive public extension

Decision: accepted.

The API must be additive and must freeze item identity, terminal watermark / cursor semantics, dedupe keys, and the no-gap attach / reconnect protocol. It may not redefine existing Host handle methods, public request fields, or `watch_session_events(...)`.

### D4. LogAuditSink first version is append-only JSONL

Decision: accepted.

`LogAuditSink` records governance responsibility chain from committed EventLog and structured context refs. Sink failure may only update sink-local error / lag state and must never roll back EventLog or affect command-path outcomes.

### D5. Tool Trace first version uses hot JSON projection plus cold JSONL writer

Decision: accepted.

Tool trace must support provider / tool diagnostic lookup and cold archival detail while preserving EventLog as truth. Hot or cold trace loss can degrade diagnostics only; it must not affect recovery, resume, memory, or Run terminal facts.

## Blocking Open Questions

None after user confirmation on 2026-05-29.

## Next Gate

Generate Phase 13 handoff implementation-ready plan through a planning specialist. The plan must remain grounded in the accepted design decisions above and must be reviewed before implementation.
