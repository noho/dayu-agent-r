# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Review Controller Adjudication

## Scope

- Plan: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- Reviews: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-mimo.md` and `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-ds.md`
- Design sources: `docs/host/design.md` and `docs/engine/design.md`
- Gate decision: `plan-fix-required`

Both reviewers independently confirmed that the motivation, accepted 7 / rejected 2 source-finding dispositions, owner boundaries, dependency direction, and three-slice structure are sound against current code. The seven raw review findings merge into six required plan fixes. None is deferred or rejected.

## Adjudicated Findings

| ID | Sources | Decision | Required plan fix |
|---|---|---|---|
| P3-C-PF-01 | DS F1 | accepted | Specify the exact `CompactMaterialPack` blocks/readable-view invariant, validation point and failure taxonomy. Define one pair-transforming tier2/tier3 helper so filtering cannot produce independently evolved projections. |
| P3-C-PF-02 | DS F2 + MiMo 002 | accepted and merged | Specify exact event-id equality semantics for `MemorySnapshotView.latest_compaction_event_ref` versus `CompactArtifactView.compaction_event_ref`, all `None`/mismatch cases, and reuse of `MemoryProjectionRepairRequired`. Explicitly remove message construction from `DurableCompactArtifactProvider._load_compact_artifact_tx()` and `*compact.messages` assembly from `RunInputBuilder.build()`; no empty-message compatibility field is allowed. |
| P3-C-PF-03 | DS F3 | accepted | Give the complete `RunInputMaterialBlock` evidence-field contract and same-slice migration order. Remove the three loose readable fields; define evidence/non-evidence invariants and require the block text to equal the shared renderer output. No new/old dual-field intermediate contract may survive the slice. |
| P3-C-PF-04 | DS F4 | accepted | Explain that the fixed count of two is derived from the one-system-envelope contract plus the current-input user message. Keep it an owner constant rather than a caller override; an override would weaken the single contract. Add a drift-oriented test/comment tied to this derivation. |
| P3-C-PF-05 | DS F5 | accepted | Map explicit `None`, mismatched-ref and no-compact cases to named tests in `tests/host/test_run_input_builder.py`, and include them in both focused and aggregate validation. |
| P3-C-PF-06 | MiMo 001 | accepted | Explicitly delete `compact_material.py`'s direct `accepted_evidence_envelope_from_payload()` call and string-comparison catch. Evidence block construction must consume `AcceptedToolResultProjection` and its typed LLM material only. Retain the zero-match source scan as a hard acceptance criterion. |

## Residual Observation Dispositions

- MiMo's duplicate `_POST_COMPACT_BASE_MESSAGE_COUNT` observation is not a separate P3-C finding: only the operation-owned estimator moves in this sub WU; the `llm_compaction` constant belongs to its own proposal budget semantics. The plan must state this scope distinction so similar names are not treated as one fact without evidence.
- `_snapshot_forward_intent_texts()` and related string-wire helpers must be removed when their last consumer disappears in S2. This is part of P3-C-PF-01's single typed projection closure, not a deferred dead-code cleanup.
- Candidate field constants and parsers in `compact_material.py` and `run_input.py` must be deleted in S2. Existing completion signals and source scans already require this; the plan fix should make the exact change explicit.
- The stable business-text order is already specified in plan section 6.1 and is not a finding.
- No design-document change, schema migration, compatibility path, Tool Trace refactor, or new cross-layer dependency is authorized.

## Gate Decision

- Accepted plan-review findings: 6 merged / 7 raw.
- Rejected: 0.
- Deferred: 0.
- Blocking questions: 0.
- Slice count remains 3.
- Next gate: AgentCodex plan fix for `P3-C-PF-01` through `P3-C-PF-06`, followed by parallel AgentMiMo and AgentDS plan re-review.
