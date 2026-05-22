# Phase 12.5 Slice 6 Code Re-Review Controller Adjudication

## Scope

- Phase: 12.5 Conversation Memory Optimization
- Slice: 6, RunInputBuilder Rendering And Compaction Request Wiring
- Base accepted slice: `1f37435` (`gateflow: accept phase 12.5 slice 5`)
- Reviewed artifacts:
  - `docs/reviews/phase12-5-slice6-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice6-code-review-ds-20260522.md`
  - `docs/reviews/phase12-5-slice6-code-rereview-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice6-code-rereview-ds-20260522.md`

## Controller Decision

PASS. Slice 6 is accepted for local commit.

The controller accepted DS F1/F2/F3/F6 as required repair items:

- Extract duplicated proactive/reactive compaction evidence input logic into shared Host code.
- Stop using raw `candidate_id` as an existing fact ref; derive stable fact refs as `memory-item:evidence_backed_fact:{candidate_id}:{compact_event_id}`.
- Add adversarial tests for malformed accepted evidence envelopes, producer mismatches, malformed compacted payload refs, duplicate evidence ids, and stable derived fact refs.
- Deduplicate accepted evidence envelopes by `evidence_id` while preserving order.

The controller rejected DS F4 as a blocker because `CompactionRequest.accepted_evidence_refs` already exists as a derived property from `accepted_evidence_envelopes`, matching the design rule that refs are derived rather than independently supplied. DS F5 (`start_event_sequence=1`) remains a deferred residual for Slice 7 / aggregate review.

MiMo and DS targeted re-review returned PASS with no remaining blockers.

## Accepted Repair Outcome

- `dayu/host/compaction_evidence.py` owns bounded EventLog evidence input collection for both proactive dispatch and reactive ingest.
- `dispatch.py` and `engine_ingest.py` call the shared helper and no longer duplicate evidence parsing code.
- RunInputBuilder renders `stable:evidence_backed_facts` with `claim_text`, `evidence_refs`, `evidence_kind`, extraction operation ref, and extraction event id / sequence.
- Minimum preserve continuity renders after recent raw turns and before episode summaries, with label, text, source refs, and preserve reason.
- Compaction requests carry accepted evidence envelopes separately from existing evidence-backed fact refs.

## Deferred Non-Blocking Findings

- `start_event_sequence=1` remains a residual because the current bounded reader is session-filtered and tolerates starting before the first actual row. Slice 7 / aggregate review should decide whether to derive a session min sequence.
- End-to-end no-compaction and post-compaction follow-up smokes remain Slice 7 scope.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py
=> 48 passed

source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_evidence.py
=> 0 errors
```

## Next Gate

Proceed to Phase 12.5 Slice 7: Integration Smoke, README Sync, Aggregate Validation.
