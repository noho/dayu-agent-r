# WU-CM-01 Slice B Code Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B code review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation artifact | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-slice-b-code-review-mimo.md`; `docs/reviews/wu-cm-01-slice-b-code-review-ds.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

Slice B implementation review found **0 blocking correctness defects**. Two small findings are accepted for a Slice B fix before accepted commit.

## Accepted Findings

### A1: Remove dead old compact payload helper code from `context_events.py`

- Source: AgentMiMo NB-1.
- Decision: accepted.
- Reason: the helpers are private, uncalled, and keep old compact candidate types alive inside a module that has now migrated `CONTEXT_COMPACTED` validation to vNext. Keeping them would conflict with the no-compatibility-code constraint.
- Required fix: delete the dead old helper functions and now-unused old type imports without changing vNext reject-list behavior.

### A2: Rename or strengthen the stale preserved-refs test

- Source: AgentDS N2.
- Decision: accepted.
- Reason: the test name still describes old preserved refs merge behavior, while the implementation now tests vNext whole-candidate output. The test should describe the current vNext contract.
- Required fix: rename the test and, if useful, assert a concrete vNext semantic such as whole-candidate output replacement or evidence fact retention.

## Non-Fix Findings

### N1: `_NO_CONTEXT_BUDGET_POLICY_REF` is used in a non-closeout path

- Source: AgentDS N1.
- Decision: no fix required.
- Reason: this is a named constant replacing an existing string literal. It does not alter non-closeout behavior, signatures, state machine, projection, or RunInputBuilder logic.

## Validation Already Reproduced

Controller reproduced the implementation validation before review:

- `270 passed` for the Slice B focused pytest matrix.
- `pyright` result: `0 errors, 0 warnings, 0 informations`.

## Required Next Gate

Send AgentCodex to Slice B fix gate for A1/A2 only. Then rerun focused tests and pyright, followed by re-review.
