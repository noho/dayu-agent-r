# Phase 12.5 Slice 2 Code Review Controller Adjudication

## Context

- Gate: Phase 12.5 Slice 2 code review.
- Slice: Accepted Evidence Envelope In Tool Accept Path.
- Review artifacts:
  - `docs/reviews/phase12-5-slice2-code-review-mimo-20260522.md`.
  - `docs/reviews/phase12-5-slice2-code-review-ds-20260522.md`.
- Approved plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`.

## Verdict

PASS. Slice 2 is accepted.

Both reviewers found no blocking issue. The implementation correctly:

- Adds Host-neutral accepted evidence envelope typed contract and strict JSON codec.
- Embeds `accepted_evidence_envelope` in non-reuse `TOOL_RESULT_ACCEPTED` payloads.
- Derives `evidence_id` as `evidence:<TOOL_RESULT_ACCEPTED.event_id>`.
- Avoids business source / locator parsing.
- Ensures `TOOL_RESULT_ACCEPTED` no longer directly materializes `EvidenceBackedFactView`.

## Deferred Finding

### S2-D1 — compact summary fact-ref test coverage weakened

- Source: DS review finding.
- Decision: Deferred to Slice 5.
- Reasoning: The removed `confirmed_fact_refs=("event-tool-for-summary",)` assertion depended on pre-P12.5 direct tool-result fact projection. Slice 2 correctly disables that projection and does not yet implement compact-output fact materialization. The fact-ref coverage must be restored once Slice 5 creates `EvidenceBackedFactView` from accepted compact output.
- Owner / destination: Phase 12.5 Slice 5 `Memory Projection Materialization`.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_memory_projection.py`
  - Result: PASS, 47 passed.
- `source .venv/bin/activate && pyright dayu/host/evidence.py dayu/host/tool_runtime.py dayu/host/memory.py`
  - Result: PASS, 0 errors.

Proceed to accepted Slice 2 local commit, then Slice 3 handoff.
