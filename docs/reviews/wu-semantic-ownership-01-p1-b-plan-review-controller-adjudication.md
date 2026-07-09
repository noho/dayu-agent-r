# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-B`
- Gate: plan review
- P1-A accepted commit: `2a841134`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-codex.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260709-p1-b-mimo.md`
  - `docs/reviews/plan-review-20260709-p1-b-ds.md`
- Decision date: 2026-07-09

## Decision

`fix-required`

Both reviewers concluded `pass-with-risks` and accepted the main architecture: design truth must be updated first, terminal/public-outbox semantics need a Host-owned helper, and cancel linkage should move from `RUN_CANCELLING` payload parsing into typed durable Run state unless implementation discovers a real multi-cancel history requirement. Controller accepts the following plan precision findings before implementation.

## Accepted Plan Findings

### P1B-PLAN-F01: S0 design truth update is not concrete enough

- Source: AgentMiMo F1 and AgentDS Finding 1.
- Severity: medium.
- Decision: accepted.
- Required fix:
  - Specify where in `docs/host/design.md` the design update should land, or require S0 artifact to record the final insertion location.
  - Specify the minimum structure: Host terminal/lifecycle event set, public outbox terminal item set, and non-public terminal fact skip/diagnostic behavior.
  - Explicitly contrast `RUN_LOST` read model / Read API / HostEvent projection as `lost` terminal with Outbox skip behavior.

### P1B-PLAN-F02: Terminal helper API needs explicit `str` vs `HostRunEventType` decision

- Source: AgentMiMo F2.
- Severity: medium.
- Decision: accepted.
- Required fix:
  - State whether helper functions accept raw EventLog `str` event types or typed `HostRunEventType`.
  - If accepting `str`, document that this is because EventLog rows expose strings and helper performs parse/classification internally.
  - If requiring `HostRunEventType`, require callers to parse first and include parse behavior in the plan.

### P1B-PLAN-F03: `durable/outbox.py` latest public terminal sequence must consume the shared public set

- Source: AgentMiMo F3 and AgentDS Finding 2.
- Severity: medium.
- Decision: accepted.
- Required fix:
  - Explicitly require `durable/outbox.py` to use `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` or `event_type_values(...)`.
  - Prohibit a second local public outbox terminal tuple in `durable/outbox.py`.
  - Add tests/validation for "latest public terminal sequence is not advanced by `RUN_LOST`".

### P1B-PLAN-F04: Validation must include outbox / durable-outbox tests and `RUN_CANCELLING` payload object residual scan

- Source: AgentMiMo F3 and AgentDS Finding 4.
- Severity: medium.
- Decision: accepted.
- Required fix:
  - Add outbox/durable-outbox focused tests to S1 validation.
  - Add `event_payload_object(...RUN_CANCELLING...)` residual scan or an equivalent `rg` pattern.
  - State allowed matches if any remain only for audit/diagnostic paths, not critical cancel closeout.

### P1B-PLAN-F05: Direct cancel typed-link stop condition is missing

- Source: AgentMiMo F5.
- Severity: low.
- Decision: accepted.
- Required fix:
  - Add stop condition for direct cancel paths where `cancel_request_event_id` cannot be safely written for some Run state and cannot be fixed by transition ordering.

### P1B-PLAN-F06: Non-terminal lifecycle constants need explicit residual classification

- Source: AgentDS Finding 3.
- Severity: low.
- Decision: accepted.
- Required fix:
  - Add residual classification for non-terminal lifecycle constants such as `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, and `RUN_RECOVERING`.
  - Clarify whether P1-B's proposed `HostRunEventType` is only a current helper owner for touched Run lifecycle/terminal consumers or a full migration target with deferred consumers.

## Rejected / Non-blocking Observations

| Observation | Decision | Rationale |
|---|---|---|
| Success-only consumers using `RUN_SUCCEEDED` | rejected-with-reason | The plan correctly excludes final-answer / memory success-only consumers from generic terminal set migration unless they consume terminal-set semantics. |
| RunRow nullable column over relation | accepted-as-current-plan | The single accepted cancel request model is currently supported by code evidence. The plan already includes a stop condition for multi-cancel history. |
| Indexing for `cancel_request_event_id` | deferred-with-owner | Not required for P1-B correctness. Add only if implementation evidence shows query pressure. |

## Next Gate

Proceed to P1-B plan fix by AgentCodex. After fix, send both reviewers through narrow plan re-review before P1-B can enter accepted plan commit.
