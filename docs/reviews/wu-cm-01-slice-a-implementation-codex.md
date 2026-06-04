# WU-CM-01 Slice A Implementation Gate - AgentCodex

## Scope

- Gate: implementation
- Slice: Slice A - Compact Contract Closure
- Design: `docs/host/design.md` section 24.3
- Accepted plan: `docs/host/wu-cm-01-conversation-memory-plan.md`
- Reslice commit: `a92416ec`

## Implementation Summary

- Added typed vNext compact input/output contracts in `dayu/host/compaction.py`:
  - `ConversationCompactInputVNext`
  - `ConversationCompactOutputVNext`
  - vNext readable input item dataclasses
  - vNext candidate dataclasses
  - vNext schema/version literals and enum types
  - `CompactQualityCheckResultVNext` and `CompactQualityIssueVNext`
- Added vNext material construction in `dayu/host/compact_material.py`:
  - `conversation_compact_input_vnext_from_material_pack`
  - maps old selected material into vNext LLM-readable sections without exposing Host provenance
  - keeps `current_input_anchor` readable but outside citable labels
- Added vNext parser path in `dayu/host/llm_compaction.py`:
  - `parse_conversation_compact_output_vnext`
  - `LLMContextCompactor.compact_vnext`
  - strict design 24.3 schema parsing
  - fail-closed validation for unknown/stale/cross-section/missing labels, empty text, illegal enum, and current input anchor citation
- Added vNext accept barrier helper in `dayu/host/context_governance.py`:
  - `check_conversation_compact_output_vnext`
  - no overload or compatibility bridge for old `CompactionCandidate`
- Added deterministic vNext fake compactor in `tests/host/fake_compaction.py`.

## Old Path Boundary

- Old `CompactionCandidate`, `CompactionRequest`, `ContextCompactor.compact`, old `stable_input` / `history_input` / `evidence_input`, and production compaction operation remain in place.
- No vNext-to-old wrapper was added.
- No production operation was switched to vNext.
- No memory durable/projection, RunInputBuilder, Service/UI/Fins/Engine code was modified.

## Validation

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
```

Result: `100 passed in 0.35s`

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`

## README Decision

No README files were changed. This slice introduces a local vNext compact contract closure without changing the production Host operation, public user workflow, stable package entry, or documented extension path.

## Residual Risks

- `compact_vnext` is available as a local contract path but is not yet wired into production compaction operation; this is intentional for Slice A and remains Slice B work.
- Previous compacted view materialization is minimal and only maps already available stable evidence-backed fact material; full accepted vNext compact projection remains later-slice work.
- Parser and accept barrier use the Slice A label section allowlist fixed from design 24.3; future slices must keep event payload/projection rules aligned with the same source.

## Gate Recommendation

Implementation gate is complete and pyright-clean. The slice can enter code review.
