# WU-SEMANTIC-OWNERSHIP-01 P2-E plan review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-E`
- Gate: plan review
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-ds.md`

## Decision

P2-E plan is accepted for fix. Implementation must not start until the accepted
plan findings below are patched and re-reviewed.

## Accepted Findings

### P2E-PLAN-F01: stream heartbeat test must preserve DEBUG gating

- Sources: AgentMiMo `F-1`.
- Severity: LOW.
- Decision: accepted.
- Required plan fix: make the ordinary `DEBUG` negative assertion a required
  test change, not only optional evidence. The fixed test must prove
  `STREAM_DEBUG_LOG_LEVEL` captures heartbeat and ordinary `DEBUG` does not.

### P2E-PLAN-F02: wait-resume fixture diagnosis and tool-call identity closure are mandatory

- Sources: AgentMiMo `F-2`, AgentDS `Finding 1`.
- Severity: MEDIUM.
- Decision: accepted.
- Required plan fix: Slice E2 implementation must first inspect actual
  `resume_request.messages`. If normal replay is present, assertions must check
  `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`, including
  `AssistantToolCall.id == original awaiting tool_call_id` and
  `ToolMessage.tool_call_id == AssistantToolCall.id`. If only fallback guidance
  appears, fixture/request-atom setup must be fixed before assertion migration;
  if old English guidance appears, stop and escalate to production owner.

### P2E-PLAN-F03: purge fixture must use a dedicated cancel request event and check cancelled coverage

- Sources: AgentMiMo `F-3`, AgentDS `Finding 2`.
- Severity: LOW.
- Decision: accepted.
- Required plan fix: fixture repair must use a dedicated cancel request EventLog
  event id, not an arbitrary existing event. Implementation must check whether
  `cancelled` is also in the relevant parametrize set and apply the same durable
  invariant fix where applicable.

### P2E-PLAN-F04: E2 stop-condition split policy must be explicit

- Source: AgentDS `Finding 3`.
- Severity: LOW.
- Decision: accepted.
- Required plan fix: if wait-resume diagnosis requires production work, Slice E2
  must split: complete independent Host export / purge fixture alignment
  separately, then handle wait-resume as a production-owner follow-up slice.

### P2E-PLAN-F05: closeout must record export snapshot propagation

- Source: AgentDS `Finding 4`.
- Severity: INFO.
- Decision: accepted as closeout requirement.
- Required plan fix: implementation closeout must explicitly record that Engine
  and Host export snapshot changes are test-only alignment against existing
  design/README public contract and require no production/README changes.

## Next Gate

AgentCodex must patch the plan artifact only, produce a plan-fix artifact, run
`git diff --check`, and then the fixed plan must pass AgentMiMo / AgentDS
re-review before implementation.
