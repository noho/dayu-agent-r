# Phase 12.5 Slice 1 Code Review Controller Adjudication

## Context

- Gate: Phase 12.5 Slice 1 code review.
- Slice: Contract Rename And Config Schema.
- Review artifacts:
  - `docs/reviews/phase12-5-slice1-code-review-mimo-20260522.md`.
  - `docs/reviews/phase12-5-slice1-code-review-ds-20260522.md`.
- Approved plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`.

## Verdict

Slice 1 is not accepted yet. One blocking rename finding is accepted for fix.

## Accepted Findings

### S1-F1 — `stable:verified_facts` and related RunInputBuilder naming remain

- Source: MiMo S1-02.
- Severity: Medium.
- Decision: Accepted.
- Reasoning: The accepted plan §4.1 makes the block id rename part of the contract migration. Leaving `stable:verified_facts` in `dayu/host/run_input.py` would violate the old-name cleanup invariant and final stale-term search, even if Slice 5 owns the later rendering semantics.
- Required fix:
  - Rename `stable:verified_facts` to `stable:evidence_backed_facts`.
  - Rename the local helper / docstring text from verified/tool-verified wording to evidence-backed wording where this is only naming fallout.
  - Update focused `tests/host/test_run_input_builder.py` references for the block id / diagnostic id if they fail due to the rename.
  - Do not implement Slice 5 rendering semantics yet: no `claim_text + evidence_refs` rendering change beyond current renamed data model.

## Rejected / Deferred Findings

- DS observation that `host_assembly.py` import restructuring is benign scope creep: accepted as non-blocking observation only. It does not require a fix because it resolved current import surface after the rename and introduces no behavior change.
- DS deferred items for later run input rendering and broader test references are accepted as later-slice responsibilities only where they do not conflict with S1-F1.

## Next Step

Send fix to AgentCodex. After fix, run the existing Slice 1 validation plus focused `tests/host/test_run_input_builder.py` if touched, then re-review.
