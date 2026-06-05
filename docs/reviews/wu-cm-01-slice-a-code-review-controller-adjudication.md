# WU-CM-01 Slice A Code Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | code review adjudication |
| slice | Slice A - Compact Contract Closure |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation report | `docs/reviews/wu-cm-01-slice-a-implementation-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-slice-a-code-review-mimo.md`; `docs/reviews/wu-cm-01-slice-a-code-review-ds.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

Slice A implementation review verdict is **fix-required before accepted commit**.

Both reviewers found 0 blocking correctness defects in the vNext compact contract closure. However, three non-blocking findings are accepted as Slice A fix scope because they are small, same-boundary issues and align with AGENTS constraints on maintainability and tests following implementation boundaries.

## Accepted Findings

### A1: Export vNext accept barrier in `context_governance.__all__`

- Source findings: AgentMiMo NF-02; AgentDS F1.
- Decision: accepted.
- Reason: `check_conversation_compact_output_vnext` is the typed vNext accept barrier that later operation code will consume. Keeping it outside `__all__` is not a runtime bug today, but it leaves the module public contract incomplete.
- Required fix: add `check_conversation_compact_output_vnext` to `dayu/host/context_governance.py` `__all__`.

### A2: Deduplicate vNext stale label rule and section allowlists

- Source findings: AgentMiMo NF-01; AgentDS F2.
- Decision: accepted.
- Reason: parser and accept barrier currently encode the same vNext label contract in two modules. The behavior is identical today, but the rule is one contract and should have one source of truth before Slice B depends on it.
- Required fix: move the shared vNext label-section allowlists and stale-label helper to the contract owner module, `dayu/host/compaction.py`, then import them from `llm_compaction.py` and `context_governance.py`.
- Constraint: this must be a direct contract helper, not a compatibility wrapper, re-export, lazy import, or old/new bridge.

### A3: Add direct tests for vNext material mapping boundaries

- Source finding: AgentMiMo NF-03.
- Decision: accepted.
- Reason: `conversation_compact_input_vnext_from_material_pack` is the Slice A material mapping closure. Existing tests call it indirectly, but AGENTS requires tests to follow the implementation boundary. The mapping should be directly protected before operation wiring depends on it.
- Required fix: add focused tests in `tests/host/test_compact_material.py` for user-turn trace mapping, assistant-turn answer mapping, evidence material mapping, previous compacted fact-only mapping, and current input anchor non-citability.

## Deferred Findings

### D1: `previous_compacted_view` only maps evidence-backed facts

- Source finding: AgentDS F3.
- Decision: deferred, not a Slice A defect.
- Reason: Slice A is contract closure and deliberately does not introduce durable memory projection or operation-level roll-forward. Full previous view materialization requires the typed memory projection introduced in later slices.
- Owner: Slice B/C, depending on where operation event payload and memory projection are closed.

## Required Next Gate

Return to AgentCodex for Slice A fix. The fix must update implementation/tests, re-run focused tests and pyright, and write a fix artifact before controller re-review.
