# Controller Adjudication — WU-CM-01-F01-S7-R1-S0 Design Review

## Scope

- Work unit: `WU-CM-01-F01-S7-R1`
- Gate: S7-R1-S0 design review
- Implementation artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`
- MiMo review artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-mimo.md`
- DS review artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-ds.md`

## Verdict

Fix required before S7-R1-S1 production implementation.

S0 covers the five mandatory plan-review findings at a high level, but MiMo Finding 1 is accepted as a concrete design ambiguity: `Verified Evidence and Facts` and `Recent Evidence` both mention evidence material that cannot use `tool` role. That ambiguity would force the implementation agent to invent a routing rule.

## Accepted Findings

### 1. Section 4 / Section 8 evidence routing ambiguity

- Source: MiMo Finding 1.
- Severity: medium.
- Decision: accepted.
- Required fix: design must define a unique routing rule:
  - `Verified Evidence and Facts` owns verified / accepted memory facts and evidence selected through the memory/fact pipeline.
  - `Recent Evidence` owns bounded recent-window fallback, wait-resume, or other evidence-like material that is not already accepted as memory/fact material.
  - A single evidence item must not be rendered in both sections.

### 2. `tool` role legality authority must be explicit

- Source: MiMo Finding 2.
- Severity: low.
- Decision: accepted.
- Required fix: design must state the current authority: current Engine message contract does not support historical evidence as `tool` role in ordinary RunInput, so selected recent evidence defaults to the system envelope until a later Engine contract work unit changes this.

### 3. Boundedness sanity should be measurable

- Source: MiMo Finding 3 and DS residual note.
- Severity: low.
- Decision: accepted.
- Required fix: design should require a measurable char-count sanity assertion: merged system envelope content length must not exceed candidate system message content length plus deterministic header/separator overhead.

### 4. Duplicate section titles in §23 and §24 are a maintenance risk

- Source: DS Finding 3.
- Severity: low.
- Decision: accepted.
- Required fix: design should mark §23's table as the single source of section titles and make §24 reference that table without duplicating all titles.

## Rejected / Non-Blocking Observations

- English section titles in Chinese context are accepted for this design gate. They are stable LLM-facing section identifiers and can be revisited only through a later design decision.
- Composite Host execution context rewrite remains an S7-R1-S1 implementation concern protected by the internal-ref replacement table and stop conditions.

## Next Gate

Run S7-R1-S0 design fix before production code implementation.

Allowed files:

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md`

No `dayu/host/run_input.py` changes may start until this fix is complete and reviewed.
