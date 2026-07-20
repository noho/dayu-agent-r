# P1-B Plan Fix Narrow Re-Review — AgentDS

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-B`
- Gate: plan re-review (post plan-fix)
- Reviewer: AgentDS
- Date: 2026-07-09
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-review-controller-adjudication.md`
- Initial reviews: `docs/reviews/plan-review-20260709-p1-b-mimo.md`, `docs/reviews/plan-review-20260709-p1-b-ds.md`

## Conclusion

**pass**

All six controller-accepted findings (P1B-PLAN-F01 through F06) are properly closed in the plan fix. No new blockers introduced.

## Per-Finding Verification

### P1B-PLAN-F01: S0 design truth update concrete structure — CLOSED

Controller required: (a) specify insertion location or require S0 artifact to record it; (b) minimum three-part structure; (c) RUN_LOST contrast between Read Model/HostEvent projection and Outbox skip.

Plan fix delivers:
- S0 now specifies two concrete insertion targets: after the state-transition terminal facts table, or after the Durable Store / EventLog / Outbox ownership section. If implementation picks another location, the S0 artifact must record the final location, section title, and rationale.
- S0 Required changes lists a self-contained three-part structure: Host terminal/lifecycle event set, public outbox terminal item set, non-public terminal fact skip/diagnostic behavior.
- S0 explicitly contrasts `RUN_LOST` as `lost` terminal in Read Model / Read API / HostEvent versus Outbox explicit skip / diagnostic, with no public outbox item produced.

Evidence: plan §7 S0 Required changes, bullet points 1-3.

### P1B-PLAN-F02: Terminal helper `str` vs `HostRunEventType` decision — CLOSED

Controller required: state whether helper accepts raw `str` or typed `HostRunEventType`, with rationale.

Plan fix delivers:
- Plan §5.1 now explicitly chooses raw EventLog `str` for mapping/predicate helper parameters.
- Rationale: EventLog rows, projection filters, SQL `IN` parameters, HostEvent projection, and diagnostic input boundaries all carry durable strings; forcing each consumer to parse first would decentralize parse/classification responsibility back to consumers.
- `lifecycle_events.py` owns parse/classification internally: known Run lifecycle strings map to `HostRunEventType`; unknown or non-Run strings return `None` / `False` without throwing.
- `HostRunEventType` remains the typed source-of-truth for helper-owned sets and new production code; `event_type_values(...)` is the only allowed string tuple projection helper.

Evidence: plan §5.1 implementation constraints, paragraph beginning "mapping / predicate helper 接受 raw EventLog `str` event type".

### P1B-PLAN-F03: durable/outbox latest public terminal sequence consumes shared public set — CLOSED

Controller required: (a) explicitly require `durable/outbox.py` to use `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`; (b) prohibit second local tuple; (c) add test for "RUN_LOST does not advance latest public terminal sequence".

Plan fix delivers:
- S1 Required changes now explicitly states: `durable/outbox.py` latest public terminal sequence must use `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` string values or `event_type_values(PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES)`, must not include `RUN_LOST`, and must not retain a second local public outbox terminal tuple in `durable/outbox.py`.
- S1 Expected tests adds: when `RUN_LOST` appears after the latest EventLog sequence, latest public terminal sequence stays at the most recent public outbox terminal item event; no false "checkpoint behind but no item to deliver" lag.

Evidence: plan §7 S1 Required changes and Expected tests.

### P1B-PLAN-F04: Outbox tests + `RUN_CANCELLING` residual scan — CLOSED

Controller required: (a) add outbox/durable-outbox tests to S1 validation; (b) add `event_payload_object(...RUN_CANCELLING...)` residual scan; (c) classify allowed vs forbidden matches.

Plan fix delivers:
- S1 validation now includes `pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py`.
- §9 full implementation validation includes the same outbox test command.
- S2 Required changes adds: audit `event_payload_object(...RUN_CANCELLING...)` residual calls; allowed hits limited to one-time audit / diagnostic / historical payload readability paths; forbidden hits include active watchdog, engine ingest cooperative cancel, dispatch linked cancel, recovery accepted-cancel critical closeout paths.
- §9 validation regex now includes `event_payload_object\(.*RUN_CANCELLING`.

Evidence: plan §7 S1 Validation, §7 S2 Required changes, §9 Validation commands.

### P1B-PLAN-F05: Direct cancel typed-link stop condition — CLOSED

Controller required: add stop condition for direct cancel paths where `cancel_request_event_id` cannot be safely written.

Plan fix delivers:
- S2 stop condition now covers: "queued / accepted / waiting / pre-worker direct cancel paths where `cancel_request_event_id` cannot be safely written for some Run state and cannot be resolved by adjusting transition ordering or same-transaction row mutation."

Evidence: plan §7 S2 Stop condition.

### P1B-PLAN-F06: Non-terminal lifecycle constants residual classification — CLOSED

Controller required: (a) classify non-terminal lifecycle constants (`RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_RECOVERING`); (b) clarify whether `HostRunEventType` is current helper owner only or full migration target.

Plan fix delivers:
- §11 Residual risks now explicitly classifies `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_WAITING`, `RUN_CANCELLING`, `RUN_RECOVERING`.
- P1-B only migrates touched consumers that need the shared lifecycle helper for terminal / read-model / tool-trace / outbox semantics.
- P1-B does not promise a repo-wide migration of every non-terminal lifecycle constant consumer. If `HostRunEventType` later becomes the universal Run event string owner, deferred consumers belong to a later work unit.

Evidence: plan §11 Residual risks, paragraph beginning "Non-terminal Run lifecycle constants".

## New Blocker Scan

The plan fix artifact states: "本轮只修 plan artifact，并新增本 plan-fix artifact。未修改生产代码、未修改 tests、未提交、未 push。"

- All plan changes are precise responses to the six accepted findings. No new architectural decisions, no scope expansion, no unresolved trade-offs introduced.
- `git diff --check` passes (confirmed in plan fix artifact).
- No residual findings from the initial reviews were left unaddressed that were marked as required fixes by the controller.

**No new blockers found.**

## Validation

Per task requirements, this re-review is read-only. No code or document modifications were made. No git operations were performed.

## Reviewer

AgentDS, 2026-07-09
