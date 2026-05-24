# P12.6 Slice 2 Code Review Controller Adjudication

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Review base: `c0a5b18` (`gateflow: accept P12.6 slice 1`)
- Review artifacts:
  - `docs/reviews/p12-6-slice2-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice2-code-review-ds-20260524.md`
- Implementation artifact: `docs/reviews/p12-6-slice2-implementation-codex-20260524.md`

## Verdict

Targeted fix required before Slice 2 can be accepted.

Both reviewers returned PASS, but DS M1 and M2 identify real implementation-quality drift that should be corrected before accepted slice commit. MiMo F2 is a low-cost semantic cleanup and should be included in the same targeted fix.

## Accepted Findings

### A1 — `_memory_material_kind` uses fragile string prefix matching

- Source findings: DS M1, MiMo F1
- File: `dayu/host/run_input.py`
- Controller decision: accepted as targeted fix.
- Rationale: the behavior is currently self-consistent, but project constraints explicitly reject brittle hard-coded business rules. The fix should share the same module-level section header constants between message rendering and material-kind classification, or otherwise make the classifier consume typed source metadata. Do not introduce a compatibility wrapper or public API change.

### A2 — snapshot cursor inline repair uses an extra undocumented hard threshold

- Source finding: DS M2
- File: `dayu/host/compact_material.py`
- Controller decision: accepted as targeted fix.
- Rationale: P12.6 plan §6.6 explicitly uses `MemoryProjectionPolicy.max_lag_events_for_inline_delta` as the inline delta threshold. `max_delta_repair_events` is a rebuild/repair budget field, not an additional inline delta gate in this slice. Remove the extra `or lag_events > policy.max_delta_repair_events` condition unless design/plan is updated first; no design update is justified for this slice.

### A3 — `excluded_reason_codes` key annotation implies prompt-local label but stores block id

- Source finding: MiMo F2
- File: `dayu/host/compaction.py`
- Controller decision: accepted as low-risk cleanup in the same fix.
- Rationale: runtime behavior is correct because both are string aliases, but the contract is misleading. Prefer a `MaterialBlockId = str` alias or `Mapping[str, str]` for this mapping.

## Deferred / Rejected Findings

### D1 — continuity / compact material blocks use `event_sequence=None`

- Source finding: DS M3
- Decision: deferred to Slice 5 wiring.
- Rationale: current Slice 2 establishes deterministic behavior via block id tie-breakers. Production event-sequence recovery for continuity / compact blocks depends on later dispatch / engine-ingest material wiring and should not be invented in this slice.

### D2 — `_snapshot_goal_text` uses `subject.ref_kind.value`

- Source finding: DS L1
- Decision: rejected.
- Evidence: `ConversationMemorySnapshot.pinned_state.confirmed_subjects` uses `OpaqueMemoryRef`, whose `ref_kind` is `HostNeutralRefKind`, not `dayu.host.evidence.OpaqueEvidenceRef.ref_kind: str`. Direct code evidence is `dayu/host/memory.py` lines defining `OpaqueMemoryRef.ref_kind: HostNeutralRefKind`.

### D3 — snapshot text escaping and stable kind ordering

- Source findings: DS L2, DS I1
- Decision: non-blocking residual.
- Rationale: these are V1 rendering / future-selection observations and do not affect Slice 2 correctness.

## Required Fix Validation

Run:

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
source .venv/bin/activate && python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
git diff --check
```
