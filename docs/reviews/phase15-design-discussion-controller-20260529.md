# Phase 15 Design Discussion Controller Artifact

## Scope

Work unit: Phase 15 Retention / Purge / Production Hardening.

Design source:
- `docs/host/design.md`
- `docs/host/implementation-control.md`

Controller conclusion: Phase 15 can enter plan generation without changing the Host design source. The existing design already defines the required `purge_session` semantics, tombstone minimum fields, audit JSONL retention rule, public API envelope, and non-goals.

## Motivation Check

The motivation is valid. Direct code evidence shows `dayu.host.command.purge_session(...)` still raises `UNSUPPORTED_OPERATION`, while `PurgeSessionRequest` and `PurgeSessionResult` are already stable public API types. Phase 15 is therefore not speculative hardening; it closes a documented deferred destructive cleanup capability under the existing public contract.

The severity must not be overstated. The Phase 15 tracking list contains many production hardening items; only items required to make first-version purge semantics, tombstone/audit behavior, projection cleanup/rebuild confidence, and local multiprocess/recovery confidence credible should be release-blocking. Remote-dependent smoke and broad production scale tuning remain deferred.

## Confirmed Scope Decisions

Release-blocking for the Phase 15 plan:
- Implement `purge_session(...)` inside the frozen public envelope.
- Enforce purge preconditions: Session closed, no active/queued/waiting/recovering/cancelling Run, and all Runs terminal.
- Persist a purge tombstone outside the target Session EventLog.
- Preserve append-only audit JSONL and add purge tombstone audit/query support sufficient to identify purged source facts.
- Delete only target Session-owned recoverable facts and projection/hot rows: Session/slot binding, Runs, Attempts, EventLog rows, SQLite payload descriptors/local payloads that are not shared, memory snapshot/items/diagnostics, minimal read models, outbox terminal items, tool trace hot rows, and projection checkpoints/failures only where reset is semantically owned by the purged Session or can be safely repaired.
- Keep shared cold artifacts unless durable refs prove they are unreferenced.
- Add tests for purge idempotency, precondition failures, deleted counts/digest, tombstone persistence, audit JSONL retention, projection cleanup/rebuild consistency, and closed-handle behavior.
- Update `dayu/host/README.md` and `tests/README.md` if implementation/test behavior changes make current docs stale.

Explicit non-goals:
- No public API shape change for `PurgeSessionRequest`, `PurgeSessionResult`, `Host` methods, `OpenHostOptions`, or `watch_session_events`.
- No `archive_session`, memory edit/reset/forget API, public payload reader, `wait_final_answer(...)`, or `get_run_result(...)`.
- No RemoteProxy / RemoteStub smoke or remote wire protocol work; that remains tracked by issue 73.
- No Service/UI workflow integration and no external issue creation from this gate.
- No Engine changes without explicit user confirmation.

## Plan Requirements

The implementation-ready plan must:
- Separate release-blocking purge/tombstone/audit/projection work from follow-up production scale hardening.
- Keep implementation slices small enough for independent implementation, review, validation, and accepted commits.
- Assign exact allowed files/modules per slice.
- Define storage ownership and deletion ordering from direct table ownership and foreign-key evidence, not from broad table-name matching.
- Specify how idempotent replay and conflict detection work for `(session_id, client_request_id)` after the Session facts are deleted.
- Specify how reads after purge behave using the existing public error taxonomy without changing the frozen public contract.
- Include pyright and affected test commands.

## Blocking Questions

No blocking user question is open for plan generation.

If planning discovers that the existing public result type cannot carry required tombstone/deleted-count information, or that current storage tables cannot support idempotent purge without changing public contract or schema semantics beyond Phase 15 scope, the planning agent must stop and return a blocking question to the controller.
