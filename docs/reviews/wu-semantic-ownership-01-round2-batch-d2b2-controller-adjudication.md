# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b2 Controller Adjudication

## Scope

- Batch: Round2 Batch D2b2
- Accepted findings: `144330-20`, `144330-23`, `144330-24`, `144330-25`
- Owner boundary: Host compaction schema / compaction operation / conversation memory projection / terminal answer typed projection
- Baseline: D2b1 accepted commit `1d46c137`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-code-review-ds.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b2-rereview-ds.md`

## Accepted Findings Closed

### 144330-20

- Decision: closed.
- Fix: removed unsupported compact fact `evidence_kind` and `FactEvidenceKindVNext` from current compact candidate/persisted payload schema. Persisted payload parsing rejects the removed field as unsupported; LLM proposal parsing does not retain it.
- Rationale: no material source owner existed for multiple evidence kinds. Removing the misleading field is the minimum owner-correct fix.

### 144330-23

- Decision: closed.
- Fix: `CONTEXT_COMPACTED` memory projection preserves previous Session Summary Memory when accepted compact candidate has `session_summary is None`. Replacement occurs only when compact owner provides a new summary.

### 144330-24

- Decision: closed.
- Fix: compaction operation owner now applies post-compact hard-threshold acceptance to both proactive and reactive compact outputs. Over-budget reactive candidates retry while repair budget remains and fail closed when exhausted.

### 144330-25

- Decision: closed.
- Fix: Conversation Memory no longer parses raw `RUN_SUCCEEDED` payload for assistant final answer fallback. It only consumes typed `assistant_final_answer_text` provided by the upstream terminal answer continuity projection boundary.

## Code Review Findings

### D2b2-F1

- Source: AgentMiMo and AgentDS.
- Decision: accepted.
- Issue: `EvidenceBackedFactCandidateVNext.__post_init__` docstring still mentioned enum `TypeError` after `evidence_kind` removal.
- Fix: docstring now declares only the current `ValueError` path for invalid text/labels.
- Re-review: AgentMiMo and AgentDS both passed.

### D2b2-F2

- Source: AgentMiMo and AgentDS.
- Decision: accepted.
- Issue: `_parse_fact` docstring still mentioned `evidence kind` validation after the field was removed.
- Fix: docstring now describes unknown/unsupported fields, text, or labels.
- Re-review: AgentMiMo and AgentDS both passed.

## Controller Validation

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_memory_projection.py -q`
  - Result: `185 passed`.
- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_compaction_contract.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q`
  - Result: `260 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.
- Source scans:
  - no `FactEvidenceKindVNext` or `_HOST_DERIVED_FACT_EVIDENCE_KIND` residuals;
  - memory no longer imports or calls `assistant_final_answer_text_from_run_payload`;
  - remaining terminal payload resolver calls are in the upstream terminal answer owner boundary or tests.

## README Decision

- `dayu/host/README.md` updated because Host stable behavior changed for compact hard-threshold acceptance and Session Summary Memory preservation.
- `tests/README.md` not updated because no test layer, command, or maintenance policy changed.

## Residual Risk

- Full pytest was not run; affected compaction/memory/dispatch matrices, pyright, diff check, and source scans passed.
- Current persisted compact payload schema rejects removed `evidence_kind` as unsupported. This intentionally follows the project rule to treat schema changes as fresh schema unless compatibility is explicitly requested.
- D2b2 closes all accepted compaction/memory findings in Batch D. Later aggregate review may still find new issues.

## Stop Status

D2b2 is accepted after implementation, code review, docstring fix, re-review, controller validation, and controller adjudication.
