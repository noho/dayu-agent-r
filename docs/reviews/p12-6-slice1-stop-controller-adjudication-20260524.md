# P12.6 Slice 1 Stop Controller Adjudication

## Gate

P12.6 implementation Slice 1.

## Reviewed Artifact

- `docs/reviews/p12-6-slice1-implementation-codex-20260524.md`

## Controller Judgment

The stop is valid. Slice 1 asks the implementation agent to remove old `CompactionRequest` fields and compatibility paths, but the
current plan's Slice 1 allowed source files exclude production consumers and constructors of those fields. Continuing would require
either modifying files outside scope or adding deprecated aliases / compatibility wrappers. Both choices violate the approved plan and
project constraints.

## Direct Evidence

The following production files still directly consume or construct old `CompactionRequest` fields and types:

- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_evidence.py`

The old fields / types include `input_event_refs`, `accepted_evidence_envelopes`, `compact_raw_context_items`,
`CompactRawContextItem`, and `CurrentMessageSummary`.

## Accepted Finding

### S1-PF1: Slice 1 file ownership does not form a compile-safe migration boundary

Decision: accepted.

Reason: Under the design goal, `CompactionRequest` is an internal Host contract shared by request construction, prompt rendering,
quality validation, artifact writing and tests. A slice that changes this contract must include all direct production call sites or
must explicitly defer contract deletion. Deferring deletion through deprecated aliases is not allowed in this project.

Required plan fix:

- Revise `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` so the first implementation slice has a coherent
  compile-safe ownership boundary.
- The fix must not introduce deprecated aliases, compatibility wrappers, old-field defaults, or test-only compatibility paths.
- The plan must state exactly which production consumers are migrated in the same slice as the `CompactionRequest` contract change,
  or otherwise reshape the slice boundaries so no accepted checkpoint contains a misleading half-migrated contract.
- The plan must preserve `docs/host/design.md` §24 / §25: no EventLog ledger dump, no `result_preview`, no Host provenance keys as
  LLM semantic input, and no public API drift.

## Next Gate

Return to plan fix, then run plan re-review again before implementation resumes.
