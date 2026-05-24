# P12.6 Slice 1 Plan Fix

## Gate

P12.6 Slice 1 plan fix only. This artifact does not authorize implementation.

## Scope Guard

Only the following files were changed:

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- `docs/reviews/p12-6-slice1-plan-fix-codex-20260524.md`

No source code, tests, README, design doc, control doc, git state, or other artifacts were modified.

## Motivation Judgment

S1-PF1 is valid and materially blocking. `CompactionRequest` is a shared Host internal contract across request construction, prompt rendering, quality validation, operation wiring, event payload / artifact writing and tests. Deleting old request fields only in `dayu/host/compaction.py` cannot compile while production call sites still construct or read those fields.

The correct boundary is not a deprecated alias or temporary old-field default. The first implementation slice must own the contract deletion and every current direct production constructor / consumer in one accepted checkpoint.

## Plan Changes

Updated `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` as follows:

- Changed plan status from `HANDOFF_READY` to `PLAN_FIX_READY` and set the current gate to Slice 1 plan-fix re-review.
- Added `docs/reviews/p12-6-slice1-stop-controller-adjudication-20260524.md` / S1-PF1 as plan-fix truth.
- Added direct evidence that the old request field consumers include:
  - `dayu/host/llm_compaction.py`
  - `dayu/host/context_governance.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/compaction_evidence.py`
- Replaced Slice 1 with `Material Pack 契约删除边界与 Direct Consumers Migration`.
- Expanded Slice 1 allowed files to include the direct production consumers above, `dayu/host/compact_material.py` or `dayu/host/compaction_material.py`, `dayu/host/compaction_operation.py` for compile break cleanup, and `dayu/config/prompts/scenes/conversation_compaction_user.md` for prompt-local label wording.
- Made Slice 1 explicitly delete `CompactionRequest.input_event_refs`, `current_message_summary`, `accepted_evidence_envelopes`, `compact_raw_context_items`, and remove `CurrentMessageSummary` / `CompactRawContextItem` from the exported Host compaction contract.
- Required `dispatch.py` and `engine_ingest.py` to construct `CompactionRequest(material_pack=..., segment_selection=...)` in Slice 1.
- Required `llm_compaction.py` to render material pack sections and map prompt-local labels through provenance, without rendering old ledger / envelope blocks.
- Required `context_governance.py` to validate prompt-local labels and provenance map instead of reading old request refs.
- Required `compaction_evidence.py` to become an evidence / history material collector and stop returning old envelope + raw context request carriers.
- Added prompt asset migration from `input_event_refs` / `accepted_evidence_refs` wording to prompt-local material / evidence labels.
- Added Slice 1 tests for direct consumer construction, prompt-local governance validation, prompt asset wording, and no old request fields through aliases / defaults / derived properties.
- Expanded Slice 1 validation to include focused pytest, pyright over all Slice 1 production consumers, and an `rg` no-match check for old request carriers in production / prompt files.
- Resequenced later slices so Slice 2 refines deterministic builder, Slice 3 hardens raw evidence reading, Slice 4 hardens schema / parser / accept barrier, and Slice 5 handles governance / multi-pass without carrying old request deletion.

## Preserved Design Goals

The revised plan keeps the Phase 12.6 constraints intact:

- No EventLog ledger dump into compactor prompt.
- No `result_preview` read, generation, fallback or prompt use.
- No Host provenance keys as LLM semantic input.
- No public API drift for Host public methods, options, followup request, Engine contracts, ConfigLoader, ScenePrepare or Fins storage/tools.
- No deprecated aliases, compatibility wrappers, old-field defaults or test-only compatibility.

## Residual Risks

- Slice 1 is now intentionally larger. This is the cost of a compile-safe contract deletion boundary; the alternative would be a misleading half-migrated checkpoint.
- Slice 1 still only establishes initial material construction. Full deterministic segment selection, snapshot repair, already-represented pruning and evidence chunking remain in later slices.
- The pyright command names `dayu/host/compact_material.py`; if implementation chooses `dayu/host/compaction_material.py`, the command must use that actual owner path consistently.

## Verification

No pytest or pyright was run because this gate is documentation-only and implementation is explicitly out of scope.

Checked the plan text for the Slice 1 boundary and direct consumer references after editing.
