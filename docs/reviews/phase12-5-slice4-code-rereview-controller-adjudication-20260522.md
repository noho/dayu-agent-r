# Phase 12.5 Slice 4 Code Re-Review Controller Adjudication

## Scope

- Phase: 12.5 Conversation Memory Optimization
- Slice: 4, LLM Compactor Structured JSON Rewrite
- Base accepted slice: `e0cc8a1` (`gateflow: accept phase 12.5 slice 3`)
- Reviewed artifacts:
  - `docs/reviews/phase12-5-slice4-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice4-code-review-ds-20260522.md`
  - `docs/reviews/phase12-5-slice4-code-rereview-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice4-code-rereview-ds-20260522.md`

## Controller Decision

PASS. Slice 4 is accepted for local commit.

The controller accepted DS F1 as blocking because `dayu/host/compaction_budget.py` was zero-caller stale code and `pyright dayu/host/compaction_budget.py` failed on removed `CompactionRequest.tool_fact_refs` / `verified_fact_refs` fields. The fix deleted the module and confirmed no production or test imports remain.

The controller also accepted DS F2 / F3 and MiMo F1 / DS F6 as required repair items before acceptance:

- `budget_after_compact` must account for the structured proposal output, not only `episode.goal`.
- The system prompt estimate must be described as a conservative post-compact estimate, not the compactor prompt itself.
- Stale docstring wording about the old verified/tool fact budget helper must be removed.

Targeted re-review by MiMo and DS returned PASS with no new blocking findings.

## Accepted Repair Outcome

- `LLMContextCompactor` now rejects plain text, malformed JSON, schema-invalid JSON, truncated final proposals, overlong structured text, and non-accepted evidence refs.
- Structured JSON final answers map through typed compaction constructors into episode summary, pinned patch, evidence-backed fact candidates, and minimum preserve item candidates.
- `budget_after_compact` includes structured summary text, pinned patch text, fact claims, minimum preserve text / labels, current input, preserved refs, and a conservative post-compact system prompt estimate.
- `dayu/host/compaction_budget.py` was deleted because it was stale and unreferenced.
- `dayu/host/README.md` was synchronized with final proposal and structured budget terminology.

## Deferred Non-Blocking Findings

- Empty candidate list and invalid enum LLM-layer tests remain deferred. Slice 3 constructor / contract tests cover the underlying rejection or acceptance behavior, and both reviewers agreed these are low risk.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py
=> 14 passed

source .venv/bin/activate && pyright dayu/host/llm_compaction.py
=> 0 errors

rg -n "estimate_compacted_context_budget|from .*compaction_budget|import .*compaction_budget|compaction_budget\\." dayu tests
=> no matches
```

## Next Gate

Proceed to Phase 12.5 Slice 5: Memory Projection Materialization.
