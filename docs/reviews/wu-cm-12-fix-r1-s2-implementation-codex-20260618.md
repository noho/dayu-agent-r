# WU-CM-12-FIX-R1 Slice 2 Implementation Report

## Scope

- Work unit: `WU-CM-12-FIX-R1`
- Gate: implementation
- Slice: 2, accepted tool evidence provider limit removal
- Agent: AgentCodex
- Date: 2026-06-18

## Changed Files

- `dayu/host/run_input.py`
- `tests/host/test_run_input_builder.py`
- `docs/reviews/wu-cm-12-fix-r1-s2-implementation-codex-20260618.md`

## Key Decisions

- Deleted `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`.
- Removed `DurableAcceptedToolEvidenceMaterialProvider.__init__(..., max_evidence_blocks=...)`; no compatibility parameter was kept.
- Removed `build_accepted_tool_evidence_material_blocks(...)` and its `__all__` export because the helper was only a direct-SQL material builder after the provider moved to EventLog material view semantics.
- Removed `_recent_accepted_tool_result_rows(..., limit)` and the `LIMIT ?` accepted evidence retrieval path.
- `DurableAcceptedToolEvidenceMaterialProvider` now calls `build_pre_dispatch_compact_material_view(transaction, event_log_store, run=current_facts.run, current_display_text=current_facts.user_prompt)`, selects only `CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE`, then applies `_represented_evidence_refs(memory, compact)` as a second whole-block filter.
- The provider now relies on `compact_material.py` for raw outcome, readable query, digest, payload, artifact and provenance semantics. `run_input.py` no longer reinterprets accepted tool result structure for ordinary accepted evidence material.
- No public API, durable schema, EventLog canonical semantics, Engine contract, WU-CM-13 reactive recovery behavior, or Slice 1 compact DTO/default chunking changes were reworked.

## Tests Added

- Provider entry can include 10 accepted evidence blocks, proving the old cap of 8 no longer controls ordinary material retrieval.
- Memory and compact represented evidence refs exclude already represented accepted evidence as whole blocks.
- Provider material text comes from canonical raw tool outcome and readable query atoms, not event ids, payload refs, digests, or preview-style substitutes.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q`
  - Result: `118 passed in 0.79s`
- `source .venv/bin/activate && pyright dayu/host/run_input.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- `rg -n "_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT|max_evidence_blocks|build_accepted_tool_evidence_material_blocks|_recent_accepted_tool_result_rows" dayu tests`
  - Result: no matches

## README / Docs Decision

- Read `dayu/host/README.md` Agent update constraints before deciding.
- Read `tests/README.md` Agent update constraints before deciding.
- No README update was made. The production change is an internal Host material provider implementation correction and does not change Host public developer interfaces, stable package boundaries, user-visible workflows, installation, CLI/Web entrypoints, or test layer/run-command structure.
- This implementation report is the only docs artifact for this slice.

## Residual Risks

- Very large accepted evidence histories may increase EventLog-backed material view construction cost. This slice intentionally does not add a private row cap or correctness-changing page size; future performance hardening needs a separate owner and design decision.
- Context size pressure from more complete accepted evidence material remains governed by existing selection, budget, fallback, compaction failure, and fail-closed paths, not by provider row-count truncation.
