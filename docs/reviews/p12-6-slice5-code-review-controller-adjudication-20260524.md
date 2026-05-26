# P12.6 Slice 5 Code Review Controller Adjudication

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 5 Proactive / Reactive Context Governance Wiring
- Review base: `410a620` (`gateflow: accept P12.6 slice 4`)
- Review artifacts:
  - `docs/reviews/p12-6-slice5-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice5-code-review-ds-20260524.md`
- Implementation artifact: `docs/reviews/p12-6-slice5-implementation-codex-20260524.md`

## Verdict

Targeted fix required before Slice 5 acceptance.

Both reviewers returned PASS, but DS D1 and D2 are real maintainability / semantic merge risks. They should be corrected before the accepted slice commit because Slice 5 is the durable governance wiring slice and should not leave duplicated core helper logic or lossy multi-pass merge behavior as known debt.

## Accepted Findings

### A1 — Duplicate selected material source refs helper

- Source finding: DS D1
- Files: `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py`
- Decision: accepted for targeted fix.
- Rationale: duplicated helper logic in two governance entrypoints violates the project duplicate-logic constraint and can drift. Extract one Host-internal helper near `RunInputMaterialBlock` ownership, preferably in `dayu/host/compact_material.py`, and use it from both call sites.

### A2 — Multi-pass merge drops earlier pass episode summary / pinned patch

- Source finding: DS D2
- File: `dayu/host/compaction_operation.py`
- Decision: accepted for targeted fix.
- Rationale: final `CONTEXT_COMPACTED` should be a merged operation result. Facts / preserve items / ranges are merged, but `episode_summary_candidate` and `pinned_state_patch_candidate` currently keep only the last pass. At minimum, episode summaries must be merged deterministically so earlier selected blocks are represented. Pinned patch merge must be explicit: either deterministic last-writer-wins with a code comment and test, or a stricter merge when operations differ. Add a focused test with different pass candidates.

### A3 — Reactive pass queue single-block selection uses an indirect zero-budget trick

- Source finding: MiMo Finding 1, DS D4
- File: `dayu/host/engine_ingest.py`
- Decision: accepted as low-risk cleanup in the same fix.
- Rationale: constructing a single-block reactive pass should be direct and explicit; relying on `max_selected_size_units=0` behavior is unnecessarily brittle.

### A4 — README omits frozen material list durable semantics

- Source finding: DS D6
- File: `dayu/host/README.md`
- Decision: accepted as documentation fix.
- Rationale: reactive frozen material digest / refs are stable Host governance semantics, not an implementation detail.

## Deferred / Non-blocking

### D1 — Dead exported range collector

- Source finding: DS D5
- Decision: defer to Slice 7 cleanup / aggregate validation.
- Rationale: current Slice 5 removed production callers from dispatch / engine ingest. Deleting the old collector may touch `compaction_evidence.py`, outside current wiring owner, and should be handled with a final no-callers cleanup pass.

### D2 — Budget-after-compact min choice

- Source finding: DS D3
- Decision: non-blocking.
- Rationale: reactive path does not use hard threshold gate after compact, and proactive remains single-pass. Add a short code comment only if touched during A2.

### D3 — Proactive pre-start material view is current-input only

- Source: DS residual risk
- Decision: accepted residual, not a fix.
- Rationale: pre-start lacks `AttemptDispatchSnapshot`; full memory/history/evidence rendering depends on later Slice 6 memory projection consolidation.

## Required Validation

Run:

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py -q
source .venv/bin/activate && python -m pyright dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_budget.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py
git diff --check
```
