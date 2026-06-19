# WU-CM-12-FIX-R1 Plan Review Adjudication

## Scope

- Work unit: `WU-CM-12-FIX-R1`
- Gate: plan review / fix / focused re-review
- Plan artifact: `docs/host/host-issues/wu-cm-12-fix-r1-material-guard-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260618-182749.md` (AgentDS)
  - `docs/reviews/plan-review-20260618-182916.md` (AgentMiMo)
- Focused re-review artifacts:
  - `docs/reviews/plan-review-20260618-183710.md` (AgentDS)
  - `docs/reviews/plan-review-20260618-183827.md` (AgentMiMo)

## Controller Decision

Plan gate is accepted. The plan is code-generation-ready after review fixes. It remains scoped to removing over-designed EventLog-derived LLM-facing input material guards and does not introduce public API, durable schema, EventLog canonical semantic, Engine contract, or WU-CM-13 reactive recovery changes.

## Finding Adjudication

| Finding | Source | Decision | Rationale |
| --- | --- | --- | --- |
| Slice 2 `build_pre_dispatch_compact_material_view` mapping underspecified | AgentDS FS-1; AgentMiMo F1 | accepted | Implementation needed exact parameter, block filtering, represented-ref filtering, and authoritative-path guidance to avoid re-designing provider semantics. |
| Chunk helper retention ambiguity | AgentDS FS-2; AgentMiMo F2 | accepted | Keeping dead chunk helper code would preserve an unapproved material production path. The plan now requires deletion when no production caller remains. |
| Former chunking test migration assertions underspecified | AgentDS FS-3 | accepted | Tests must prove whole evidence material remains intact, not merely that chunk labels disappeared. |
| Long-session evidence scan performance residual owner unclear | AgentMiMo F3 | accepted with scoped deferral | The residual is real but not a blocker. Owner is a future Host material source performance hardening WU if real scan cost is observed, not WU-CM-13. |

## Fix Summary

The plan was amended to require:

- `DurableAcceptedToolEvidenceMaterialProvider` maps through `build_pre_dispatch_compact_material_view(...)` with `current_display_text=current_facts.user_prompt`.
- Provider output selects only `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE` whole blocks and applies `_represented_evidence_refs(memory, compact)` as a second whole-block filter.
- The EventLog-backed material view is the authoritative accepted evidence material path; the plan does not preserve the old direct-SQL builder for comparison after deletion.
- `_evidence_chunks`, `_EvidenceChunk`, `evidence_chunk_label`, and `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` are deleted when no production caller remains; this WU does not retain dead explicit budget chunk helper code.
- The former large-evidence chunking test migrates to no-default-chunk assertions: single `E1`, full text / response, full-text digest, preserved provenance / payload refs, no `E1.1` / `E1.2`, and no `chunk_parent_label` / `chunk_ordinal` semantics.
- Performance risk from larger EventLog delta scans is deferred to a future Host material source performance hardening WU if observed; it must not reintroduce a private row limit or page correctness cap.

## Focused Re-review Result

- AgentDS focused re-review: PASS; all four accepted findings closed.
- AgentMiMo focused re-review: PASS; all four accepted findings closed.

## Validation

- `git diff --check`: PASS.

## Residual Risks

- Non-blocking deferred residual: long-session accepted evidence scan cost may need a future Host material source performance hardening WU if real production evidence shows dispatch latency pressure. This is not owned by WU-CM-13 and does not justify reintroducing private LLM-facing material row limits in `WU-CM-12-FIX-R1`.
