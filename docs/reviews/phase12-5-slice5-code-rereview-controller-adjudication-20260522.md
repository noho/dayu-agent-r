# Phase 12.5 Slice 5 Code Re-Review Controller Adjudication

## Scope

- Phase: 12.5 Conversation Memory Optimization
- Slice: 5, Memory Projection Materialization
- Base accepted slice: `e2a7332` (`gateflow: accept phase 12.5 slice 4`)
- Reviewed artifacts:
  - `docs/reviews/phase12-5-slice5-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice5-code-review-ds-20260522.md`
  - `docs/reviews/phase12-5-slice5-code-rereview-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice5-code-rereview-ds-20260522.md`

## Controller Decision

PASS. Slice 5 is accepted for local commit.

The controller rejected the initial workaround that stored `minimum_preserve_item` durable rows as `episode_summary`; the root cause was the fresh schema `host_memory_items.item_kind` CHECK missing `minimum_preserve_item`. The repair added `minimum_preserve_item` as a first-class durable item kind.

The controller also accepted the following review findings as required fixes before acceptance:

- MiMo F1: diagnostics schema CHECK must include `evidence_backed_fact_candidate_invalid` and remove stale `missing_fact_summary_fallback`.
- DS Finding 1: compact payload validation must not mask non-fact field errors behind fact-candidate diagnostics.
- DS Finding 2: memory projection must enforce shared fact/minimum-preserve bounds when materializing raw JSON.
- MiMo F3: `max_evidence_backed_facts` latest-N retention and budget diagnostic needed direct test coverage.

MiMo and DS targeted re-review returned PASS with no remaining blockers.

## Accepted Repair Outcome

- `TOOL_RESULT_ACCEPTED` alone does not materialize `EvidenceBackedFactView`.
- Accepted `CONTEXT_COMPACTED` fact candidates materialize `EvidenceBackedFactView` with `claim_text`, `evidence_refs`, `evidence_kind`, attributes, and provenance from the accepted compact event id / sequence.
- Minimum preserve candidates materialize only as `ConversationContinuityItem(item_kind=minimum_preserve_item)`.
- Durable schema stores `minimum_preserve_item` as a first-class item kind.
- Old snapshot key `verified_facts`, old durable item kind `verified_fact`, and old fact JSON shape fail closed.
- Invalid fact candidates produce diagnostics only and do not synthesize fallback facts.

## Deferred Non-Blocking Findings

- DS Finding 3: durable snapshot read path performs an extra SQL item-kind validation query. This remains an accepted residual because it is defensive, bounded, and not on the critical Engine loop.
- DS re-review LOW: validation depth currently depends on both `validate_context_compacted_payload` and typed constructors. The current tests cover the intended invalid candidate diagnostic path; future schema relaxations should keep these layers aligned.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_memory_projection.py
=> 47 passed

source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/host/durable/schema.py
=> 0 errors
```

## Next Gate

Proceed to Phase 12.5 Slice 6: RunInputBuilder Rendering And Compaction Request Wiring.
