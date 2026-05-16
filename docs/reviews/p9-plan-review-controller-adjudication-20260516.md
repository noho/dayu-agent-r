# P9 Plan Review Controller Adjudication

- Controller: AgentController
- Date: 2026-05-16
- Work unit: Phase 9 Conversation Memory / Session Memory Projection
- Plan artifact: `docs/host/phase9-conversation-memory-plan.md`
- Review artifacts:
  - `docs/reviews/p9-plan-review-mimo-20260516.md`
  - `docs/reviews/p9-plan-review-ds-20260516.md`
- Re-review artifacts:
  - `docs/reviews/p9-plan-rereview-mimo-20260516.md`
  - `docs/reviews/p9-plan-rereview-ds-20260516.md`

## Verdict

PASS. P9 handoff implementation-ready plan is accepted.

Remaining blocking findings: 0.

## Design Basis

The accepted plan is governed by:

- `docs/host/design.md` §23 RunInputBuilder.
- `docs/host/design.md` §24 Conversation Memory.
- `docs/host/design.md` §26 Evidence / Retrieval / Long-term Memory.
- `docs/host/implementation-control.md` Phase 9 entry and P9 design refinement tracking.

Controller confirms the plan follows the phase discussion ruling:

- P9 is a financial-analysis workbench state projection, not a chat transcript compressor.
- P9 implements session-level memory projection only.
- P9 preserves Host business neutrality and does not implement long-term retrieval, business signal ledger, signal-to-outcome verification, or public memory edit / reset / forget API.
- P9 reserves neutral evidence anchor, claim status, provenance, and included / excluded reason boundaries for future issue 39 work.

## Finding Adjudication

### Accepted Findings

- MiMo B-1 / DS F4: `SessionContinuityProvider` and `DurableMemorySnapshotProvider` ownership was under-specified.
  - Resolution: accepted. Plan now states P9 primary path moves historical raw turns and episode summaries into `MemorySnapshotProvider` / history pool as the single budget authority. `SessionContinuityProvider` may only carry resume-specific / non-history continuity facts or no-op raw history.
- MiMo B-2: `MemorySnapshotView` and provider/factory shape was under-specified.
  - Resolution: accepted. Plan now specifies `messages`, `memory_snapshot_cursor`, `policy_digest`, and `diagnostics`; provider protocol still returns `MemorySnapshotView`; factories accept optional `memory_snapshot_provider` with no-op default; global RunInputBuilder order remains `docs/host/design.md` §23.
- DS F1 / MiMo L-1: claim status lifecycle needed active vs reserved scope.
  - Resolution: accepted. Plan now states P9 actively produces only `TOOL_VERIFIED` and `ASSUMPTION`; `CANDIDATE`, `CONFLICTED`, `STALE`, and `SUPERSEDED` are reserved for issue 39 / future long-term memory unless a canonical fact explicitly carries neutral status.
- DS F2: `RUN_SUCCEEDED` consumption was implicit.
  - Resolution: accepted. Plan now defines `ConversationContinuityItem`; `RUN_SUCCEEDED` final answer becomes continuity / assistant conclusion, never `verified_facts`.
- DS F3: `required_event_sequence` needed a concrete boundary.
  - Resolution: accepted. Plan now ties it to `current_facts.attempt.started_event_sequence - 1`.
- DS F5 / MiMo M-3: `open_questions` placement needed clarification.
  - Resolution: accepted. Plan now keeps `open_questions` only in `PinnedStateView`; message rendering injects pinned open questions before working assumptions without duplicate storage.
- MiMo M-1: history pool budget algorithm needed implementation-level precision.
  - Resolution: accepted with modification. Plan now specifies a conservative estimator, count-based recent raw turns floor, per-turn safety cap, shared `history_pool_size_units`, and item-level diagnostics. Controller rejected arbitrary fixed 40 / 60 budget split because it would introduce magic policy coupling.
- MiMo M-2: Host-neutral reference enforcement needed clarification.
  - Resolution: accepted with modification. Plan now uses a small Host-neutral enum / `StrEnum` for `HostNeutralRefKind` and tests schema / contracts for business-specific field leakage. Controller rejected brittle business-term blocklist.
- MiMo M-4: `TOOL_RESULT_ACCEPTED` mapping needed guidance.
  - Resolution: accepted. Plan now requires inspecting existing ToolRuntime / RunInputBuilder payload helpers and mapping available tool/event/payload/digest fields with neutral fallback diagnostics.
- MiMo M-5 / L-2: diagnostics and projection failures needed separation.
  - Resolution: accepted. Plan now routes `MemoryDiagnostic` to memory diagnostics / snapshot diagnostics and runner-level projection exceptions to `host_projection_failures`.
- MiMo L-3 / DS F6: digest canonicalization needed deterministic rules.
  - Resolution: accepted. Plan now specifies canonical JSON rules, stable EventLog-derived ordering, deterministic null handling, and excludes non-deterministic timestamps from digest input.

### Rejected Findings

No reviewer finding was fully rejected. Two proposed remedies were rejected while the underlying issue was accepted:

- Fixed 40 / 60 stable/history budget split was rejected as a magic policy ratio.
- Business-term blocklist for `OpaqueMemoryRef.ref_kind` was rejected as brittle and not type-first.

### Deferred Findings

No accepted blocking finding is deferred.

The following capabilities remain explicitly deferred with owners:

- Long-term retrieval index, business signal ledger, and signal-to-outcome verification: issue 39 / future long-term memory phase.
- Full context governance orchestration for repair-required paths: Phase 10.
- Durable tool trace projection of included / excluded reasons: Phase 13.
- Public memory edit / reset / forget API: future memory governance work unit after design write-back.

## Re-review Result

- AgentMiMo re-review: PASS, 0 remaining blocking findings.
- AgentDS re-review: PASS, 0 remaining blocking findings.

Controller accepts the P9 plan as implementation-ready.
