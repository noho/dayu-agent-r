# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: plan review
- P0-A accepted commit: `6731b451`
- P0-B accepted commit: `750af328`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- AgentCodex plan delivery: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-codex.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260709-p1-a-mimo.md`
  - `docs/reviews/plan-review-20260709-p1-a-ds.md`
- Decision date: 2026-07-09

## Decision

`fix-required`

Both reviewers accept the main P1-A direction: the stale part of the umbrella finding is correctly narrowed, the selected sibling projection helper approach is sound, and the owner boundary belongs in Host accepted-result projection rather than individual consumers. However, AgentDS identified high-severity plan gaps that must be resolved before implementation. Controller accepts those as plan-review blockers and also accepts related medium/low precision fixes where they reduce implementation ambiguity without expanding scope.

## Accepted Plan Findings

### P1A-PLAN-F01: Tool Trace request summary replacement strategy is under-specified

- Source: AgentDS F01, AgentMiMo F02.
- Severity: high.
- Decision: accepted.
- Rationale: Tool Trace currently reconstructs request arguments, redacted arguments, arguments summary, query text and identity checks. P1-A must not accidentally move Tool Trace-specific bounded rendering/redaction into a generic projection truth, nor leave consumers doing private request back-query.
- Required fix:
  - In the plan, explicitly choose whether Tool Trace keeps a trace-specific bounded rendering helper fed by projection fields, or whether projection exposes complete Tool Trace summary typed views.
  - Prefer the narrower option unless direct evidence requires otherwise: projection owns query/status/source/result truth; Tool Trace may keep display-only argument rendering without re-owning accepted query/status/source semantics.
  - Update validation grep expectations so the selected strategy is testable.

### P1A-PLAN-F02: Read API PREVIEW vs CANONICAL_FACT event class boundary is missing

- Source: AgentDS F02.
- Severity: high.
- Decision: accepted.
- Rationale: Current Read API activity path reads `outcome_kind` from PREVIEW payloads, while the planned projection helper is described around canonical accepted result payload fields such as `tool_fact_kind` / `resolution_kind`. Implementation would otherwise discover an event-class contract mismatch late.
- Required fix:
  - Plan must explicitly decide whether Read API activity migrates to canonical `TOOL_RESULT_ACCEPTED` projection helper input or remains PREVIEW-only in P1-A.
  - If migrating to canonical events, specify the dispatch boundary and mapping from `AcceptedToolResultStatus` to `HostActivityStatus`.
  - If not migrating, update the checklist and non-goals so P1-A does not falsely claim Read API status is produced by the helper.

### P1A-PLAN-F03: Source projection producer `_readable_source_text_from_refs()` is not covered

- Source: AgentDS F03, AgentMiMo F01.
- Severity: high.
- Decision: accepted.
- Rationale: Source projection drift starts before the duplicated blacklist filters: `compact_material._readable_source_text_from_refs()` currently creates source note text from opaque refs. A plan that only removes downstream blacklist helpers may leave the source text producer outside the owner boundary.
- Required fix:
  - Add explicit handling for `_readable_source_text_from_refs()` in S2 or S1.
  - Decide whether its logic migrates into the projection helper, is replaced by helper output, or is retained only for non-accepted-result initial material with a documented boundary.
  - Add `_readable_source_text_from_refs` and `source_note` to validation grep.

### P1A-PLAN-F04: Conversation Memory unavailable-query fallback ownership is unclear

- Source: AgentDS F04.
- Severity: medium.
- Decision: accepted.
- Rationale: `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` may remain as a limited-signal text, but consumers must not independently decide when to emit it.
- Required fix:
  - Specify whether the constant moves to the projection helper module or remains imported from a single owner.
  - Specify that Conversation Memory consumes projection `query_text` / query state and does not decide fallback conditions itself.

### P1A-PLAN-F05: Status enum mapping rules are incomplete

- Source: AgentMiMo F03, AgentDS F06.
- Severity: medium.
- Decision: accepted.
- Rationale: `completed` / `failed` / `cancelled` / `governed_error` / `lost` / `unknown` must have plan-level mapping rules or an explicit S1 precondition before tests are written.
- Required fix:
  - Add a concise mapping table or S1 requirement defining ordinary/wait-resolution status field precedence.
  - Clarify whether Tool Trace `_tool_result_status()` is deleted, moved to the shared helper, or retained only as a formatting adapter over projection status.

### P1A-PLAN-F06: Initial compact material path needs explicit boundary

- Source: AgentDS F07.
- Severity: low.
- Decision: accepted.
- Rationale: `InitialEvidenceMaterial` and `_evidence_blocks()` can become a parallel query/source construction path if not classified.
- Required fix:
  - Classify the initial material path as in-scope migration or explicit non-goal.
  - If in scope, add it to S2/S3 tests; if out of scope, explain why it is not an accepted-result projection consumer.

### P1A-PLAN-F07: Validation grep should include upstream and payload-resolution call sites

- Source: AgentDS F05/R03.
- Severity: medium.
- Decision: accepted.
- Rationale: Validation must catch remaining source-note producers and request-atom back-query helpers, not only the already named consumer helpers.
- Required fix:
  - Add `_readable_source_text_from_refs`, `source_note`, and relevant `tool_call_request_atoms` call-site scans to validation commands.
  - State expected allowed matches if helper internals still call `tool_call_request_atoms`.

## Rejected / Deferred Observations

| Observation | Decision | Rationale |
|---|---|---|
| Control doc modified but plan does not mention it | rejected-with-reason | Controller owns gate-state updates in `docs/host/issues-implementation-control.md`; AgentCodex correctly did not touch the existing controller modification. |
| P1-C should consume P1-A helper API | deferred-with-owner | This is a P1-C handoff requirement. P1-A plan should name the helper API enough for implementation and handoff, but P1-C text cleanup remains a later sub WU. |
| Source refs production paths mostly empty | deferred-with-owner | P1-A can close no-leak / projection ownership now. Business source enrichment belongs to a later source producer WU if needed. |
| Tool Trace bounded rendering details | accepted as boundary clarification only | Tool Trace display truncation may remain consumer-level rendering, but query/status/source truth must come from the projection helper. |

## Next Gate

Proceed to P1-A plan fix by AgentCodex. After the fix, send both reviewers through P1-A plan re-review. P1-A cannot enter implementation until all accepted plan findings P1A-PLAN-F01 through P1A-PLAN-F07 are closed.
