# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Implementation - Codex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round2 Batch D2b2`.
- Gate role: implementation / fix.
- Included findings: `144330-20`, `144330-23`, `144330-24`, `144330-25`.
- Excluded scope: D2a, D2b1, Fins, Web, Engine fallback, accepted tool outcome codec.
- No commit, push, PR, or unrelated refactor.

## Changed Files

- `dayu/host/compaction.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/README.md`
- Focused tests under `tests/host/`
- `tests/host/fake_compaction.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`

`utils/smoke_host_public_conversation_memory_scenarios.py` was changed only because the required pyright command covers `utils/` and the script referenced the removed compact fact enum.

## Semantic Owner Decisions

### 144330-20 evidence-kind-hardcode

Decision: remove unsupported compact fact `evidence_kind`.

Evidence showed `FactEvidenceKindVNext` had three enum values but production only assigned `ACCEPTED_EVIDENCE_MATERIAL` in `llm_compaction.py`. No material-pack owner provided multiple evidence kinds. The owner-correct fix is to delete the misleading field/enum from the compact candidate and current persisted payload schema, not to add prompt complexity or downstream derivation.

Current contract:

- `EvidenceBackedFactCandidateVNext` owns `claim_text`, `evidence_labels`, and `source_labels`.
- `CONTEXT_COMPACTED.accepted_candidate.evidence_backed_facts[]` no longer accepts `evidence_kind`.
- LLM proposal parsing ignores an LLM-supplied `evidence_kind`; persisted payload parsing rejects it as unsupported current schema.

### 144330-23 compact-session-summary-loss

Decision: Conversation Memory preserves prior Session Summary Memory when accepted compact candidate has `session_summary is None`.

`session_summary=None` means compact owner did not provide a replacement. It is not an explicit delete command. Memory now carries forward the previous summary view and only replaces it when the compact candidate provides a valid summary.

### 144330-24 reactive-compact-no-circuit-breaker

Decision: compaction operation owner applies post-compact hard threshold acceptance to both proactive and reactive compaction.

The operation already estimates accepted candidate business text plus current input. Letting reactive over-budget output through pushed acceptance responsibility into downstream dispatch/Engine loops. The operation now rejects over-hard-threshold reactive output, retries while repair budget remains, and fail-closes when attempts are exhausted.

### 144330-25 memory-fallback-crosses-ownership

Decision: Memory no longer parses raw `RUN_SUCCEEDED` payload for assistant final answer fallback.

Durable memory projection already resolves terminal answer continuity at the EventLog/canonical projection boundary and passes typed `assistant_final_answer_text` into `MemoryProjectionEvent`. Memory now consumes only that typed field; missing typed text means no assistant selected recent item.

## Tests Updated

- Compact schema tests now assert unsupported `evidence_kind` is rejected at persisted payload boundary and not emitted by candidate JSON.
- LLM compaction parser test now asserts LLM-supplied `evidence_kind` is not retained.
- Memory projection tests cover:
  - facts-only accepted compact preserves prior session summary;
  - raw `RUN_SUCCEEDED.final_answer` payload does not materialize without typed `assistant_final_answer_text`;
  - typed terminal answer material still materializes.
- Compaction operation tests cover:
  - reactive over-hard-threshold candidate is retried;
  - reactive over-hard-threshold candidate fail-closes when no repair budget remains.
- Existing previous-view tests were updated for the current compact fact text contract.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_memory_projection.py -q`
  - Result: `185 passed in 0.74s`
- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_compaction_contract.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q`
  - Result: `260 passed in 2.64s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- Source scans:
  - Removed `FactEvidenceKindVNext` and `_HOST_DERIVED_FACT_EVIDENCE_KIND`.
  - Removed memory call to `assistant_final_answer_text_from_run_payload`.
  - Remaining `assistant_final_answer_text_from_run_payload` calls are in terminal resolver/tests, the upstream owner boundary.

## Follow-up Fix

- Controller audit found incomplete one-line docstrings on new / renamed D2b2 tests.
- Updated docstrings with `:returns` and `:raises` for:
  - `tests/host/test_memory_projection.py::test_accepted_compact_without_summary_preserves_prior_session_summary`
  - `tests/host/test_memory_projection.py::test_run_succeeded_raw_final_answer_payload_does_not_materialize_assistant_window`
  - `tests/host/test_compaction_operation.py::test_run_compaction_operation_fails_closed_for_reactive_over_budget_output`
  - `tests/host/test_context_compact_events.py::test_compacted_semantic_parser_rejects_unsupported_evidence_kind_field`
- Re-scanned D2b2 new / renamed test functions; the reactive retry and LLM parser renamed tests already had complete docstrings.
- Only comments and this artifact were changed in the follow-up; no focused tests were rerun.

## Code Review Fix

- Addressed accepted MiMo / DS minor findings:
  - Removed stale `EvidenceBackedFactCandidateVNext.__post_init__` docstring text that still mentioned enum `TypeError` after `evidence_kind` removal.
  - Updated `_parse_fact` docstring to describe unknown / unsupported fields instead of removed evidence-kind validation.
- Only docstrings and this artifact were changed; no behavior changes.

## README Decision

- Updated `dayu/host/README.md` because Host stable behavior changed:
  - proactive and reactive compaction both require post-compact hard-threshold acceptance at operation owner;
  - accepted compact with no session summary replacement preserves prior Session Summary Memory.
- Checked `tests/README.md`; no update. This change adds focused cases within existing Host test layers and does not add test layers, running modes, or maintenance rules.

## Residual Risks

- No known residual correctness risk in D2b2 scope.
- Persisted compact payload schema is treated as fresh current schema per instruction; old payload shapes containing `evidence_kind` are not compat-read.

## Stop Status

COMPLETE.
