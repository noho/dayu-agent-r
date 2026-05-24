# P12.6 Plan Review Controller Adjudication

## Gate

P12.6 handoff implementation-ready plan review.

## Reviewed Artifacts

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- `docs/reviews/p12-6-plan-review-mimo-20260524.md`
- `docs/reviews/p12-6-plan-review-ds-20260524.md`

## Controller Judgment

Both independent plan reviews conclude the plan is directionally handoff-ready, but the findings identify real plan clarity gaps that
could cause implementation agent stop conditions or slice coordination drift. Based on `docs/host/design.md` §1 / §24 / §25, the
right choice is to fix the plan artifact before entering implementation.

## Accepted Findings

### Accepted P-F1: §7 master allowlist conflicts with Slice 3 local allowlist

Reason: §7 claims to be the exhaustive modification list. If `dayu/host/evidence.py` and
`tests/host/test_toolruntime_accept_barrier.py` appear only in Slice 3, an implementation agent must either stop or violate the plan.

Required fix:

- Add `dayu/host/evidence.py` to §7 Host source list.
- Add `tests/host/test_toolruntime_accept_barrier.py` to §7 tests list.

### Accepted P-F2: Slice 1 does not explicitly cover existing tests broken by `CompactionRequest` shape change

Reason: P12.6 rejects compatibility wrappers, so existing tests referencing old fields must be migrated in the same slice that changes
the contract. Leaving this implicit would create a red baseline for later slices.

Required fix:

- Expand Slice 1 allowed tests to include all existing tests that directly construct or assert old `CompactionRequest` fields.
- State that Slice 1 must migrate those tests to the new material-pack-oriented contract instead of keeping deprecated aliases.

### Accepted P-F3: Slice dependency order should be explicit

Reason: The plan is sequential in practice, but implementation handoff should not rely on implicit ordering where later slices depend
on material pack types, builder output, evidence label mapping and parser semantics.

Required fix:

- Add an explicit dependency graph before slice details.
- Add dependency notes to slices where useful.

### Accepted P-F4: `PromptLocalEvidenceMap` is used but not defined in typed contract list

Reason: It is a cross-slice contract between material pack builder, evidence collector and LLM parser. Leaving the shape implicit
forces implementation agents to redesign.

Required fix:

- Add `PromptLocalEvidenceMap` and canonical provenance entry shape to §6.1 typed contracts.
- State the relationship to `CompactMaterialPack.provenance_map`.

### Accepted P-F5: prompt-local label generation owner and algorithm are implicit

Reason: Label generation is the protocol between Slice 2 and Slice 4. It must have one owner and shared validation helpers.

Required fix:

- Define label generation owner as `dayu/host/compact_material.py` module-level private helpers.
- Define the format `{section_prefix}{ordinal}` and `{section_prefix}{ordinal}.{chunk_ordinal}` with shared constants used by parser
  validation.

## Rejected Findings

None.

## Deferred Risks

- Large session rebuild performance remains a later hardening owner and is not a plan blocker.
- V1 relevance remains Host-neutral and bounded; business ranking belongs to later Fins / retrieval owner.
- Prompt-local label provenance mapping must remain internal artifact / diagnostic data and must not write raw prompt or provider
  payload into EventLog; this remains a review focus in Slice 1 and Slice 4.

## Fix Handoff

Route to `AgentCodex` as plan fix. Scope is restricted to
`docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` and a fix artifact under `docs/reviews/`. No source, tests,
README, design doc or control doc edits.
