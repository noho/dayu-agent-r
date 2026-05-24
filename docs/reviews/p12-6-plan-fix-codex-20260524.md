# P12.6 Plan Fix — Codex

## Gate

Role-scoped plan fix only. No implementation workflow was started.

## Scope

Modified only:

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- `docs/reviews/p12-6-plan-fix-codex-20260524.md`

Did not modify source code, tests, README, `docs/host/design.md`, `docs/host/implementation-control.md`, or git state.

## Motivation Check

Accepted findings P-F1 through P-F5 are valid plan defects, not implementation defects. They affect handoff clarity because the plan already declares §7 as the exhaustive allowlist, deletes the old `CompactionRequest` shape without compatibility, and uses prompt-local evidence labels as a cross-slice protocol. Fixing the plan before implementation is the right gate action.

## Fixes

### P-F1 — §7 master allowlist conflict

Fixed. Added the Slice 3 files that were missing from §7 master lists:

- `dayu/host/evidence.py`
- `tests/host/test_toolruntime_accept_barrier.py`

### P-F2 — Slice 1 old `CompactionRequest` test migration scope

Fixed. Expanded Slice 1 allowed tests to cover the known existing old-field reference boundaries:

- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/fake_compaction.py`

Also made Slice 1 explicitly require migration to the new material-pack-oriented contract with no deprecated aliases, compatibility wrappers, old-field defaults, or test-only compatibility path.

### P-F3 — Slice dependency graph

Fixed. Added §8.0 with an explicit acyclic dependency graph and per-slice dependency notes.

### P-F4 — `PromptLocalEvidenceMap` typed contract

Fixed. Added typed contract definitions for:

- `PromptLocalProvenanceEntry`
- `PromptLocalEvidenceMap`

The plan now states that `CompactMaterialPack.provenance_map` is the complete single source of truth for prompt-local provenance, and `PromptLocalEvidenceMap` is the evidence-only typed view or same-value subset.

### P-F5 — Prompt-local label generation owner and algorithm

Fixed. Added label generation ownership and algorithm to §6.2:

- owner is module-level private helpers in `dayu/host/compact_material.py` or the alternate chosen file `dayu/host/compaction_material.py`;
- labels use `{section_prefix}{ordinal}` and `{section_prefix}{ordinal}.{chunk_ordinal}`;
- prefixes are shared constants for `C` / `H` / `E` / `S`;
- parser validation must reuse the same constants and private parse / validate helpers.

## Verification

Performed text-level verification by re-reading the modified sections of the plan. No tests or pyright were run because this gate is documentation-only and the user explicitly restricted scope to plan fix, not implementation.

## Residual Risks

- The plan still allows either `dayu/host/compact_material.py` or `dayu/host/compaction_material.py`; implementation must pick one and keep label helper ownership in that module.
- Slice 1 now has a wider test migration blast radius by design. This is necessary to avoid deprecated aliases, but implementation should run the expanded Slice 1 verification before proceeding.
- `PromptLocalProvenanceEntry` is specified as a plan-level typed shape; implementation review must verify the concrete dataclass does not use untyped bags or optional-field ambiguity to bypass strict typing.
