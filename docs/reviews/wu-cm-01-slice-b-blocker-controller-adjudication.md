# WU-CM-01 Slice B Blocker Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B implementation blocker adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

The Slice B blocker is **accepted**.

The accepted plan under-scoped the implementation ownership boundary. Reactive accepted compaction closeout is implemented in `dayu/host/engine_ingest.py`, but that module is not in Slice B allowed files. Since Slice B requires accepted / rejected / failed compaction events to be vNext event closures, the current allowed list cannot complete the production reactive path without an unauthorized file modification.

## Motivation Check

The implementation motivation still holds:

- Production operation and compacted event payload must move from old `CompactionCandidate` / old payload fields to vNext candidate and vNext quality result.
- Whole-candidate repair must replace old field-level merge behavior.
- Fallback / failed compaction must not materialize memory or write compact success events.

The blocker is not that the goal is overestimated. The blocker is a plan ownership error: one production owner of the required behavior was omitted from allowed files.

## Accepted Evidence

### E1: Reactive accepted closeout owner is `engine_ingest.py`

AgentCodex identified direct code evidence:

- `dayu/host/engine_ingest.py` imports old artifact write request and old compaction types.
- The reactive accepted branch calls `_append_reactive_compacted_event(...)`.
- `_append_reactive_compacted_event(...)` still accepts `CompactionCandidate` and `CompactQualityCheckResult`.
- It writes compact artifacts through old `CompactArtifactWriteRequest`.
- The observed failure is `TypeError: CompactArtifactWriteRequest.accepted_candidate must be CompactionCandidate` after operation has moved to vNext candidate.

This is sufficient direct evidence that reactive accepted vNext event closure cannot be completed only through `dispatch.py`.

### E2: Proactive subsequent run input failure is not Slice B scope

The failing proactive subsequent run input test still expects projection / RunInputBuilder to consume compacted event output. The accepted Slice B explicitly forbids memory durable/projection and RunInputBuilder migration. That behavior belongs to Slice C/D, not to a compatibility field added to the vNext compact payload.

## Decision

Return to plan fix/reslice gate.

The plan fix must do both:

1. Add `dayu/host/engine_ingest.py` to the Slice B allowed files, limited to reactive accepted compaction event/artifact closeout.
2. Clarify that tests whose assertions require memory projection or RunInputBuilder consumption of vNext compacted payload must be moved to Slice C/D or adjusted in Slice B to assert only operation/event closure.

The plan fix must not introduce old payload compatibility fields, projection shims, or old candidate adapters.

## Current Workspace State

AgentCodex has partial Slice B edits in allowed files only. They are not accepted implementation output because the full Slice B validation did not pass. The next plan-fix gate must decide whether those edits remain useful after the allowed-files correction or should be reworked.

## Required Next Gate

Send AgentCodex to plan fix/reslice. The plan fix should update `docs/host/wu-cm-01-conversation-memory-plan.md` and write a plan-fix artifact. No production code should be committed before the corrected plan is reviewed and accepted.
