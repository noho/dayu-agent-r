# Controller Adjudication — WU-CM-01-F01-S7-R1 Plan Review

## Scope

- Work unit: `WU-CM-01-F01-S7-R1`
- Gate: plan review
- Plan artifact: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- DS review artifact: `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-ds.md`
- MiMo review status: attempted, but no artifact was persisted after timeout; controller proceeds with DS artifact and the previously captured MiMo blocker verdict to avoid stalling the phase.

## Verdict

Plan accepted with mandatory S7-R1-S0 design-sync findings.

The plan's core direction is sound:

- `one-system-message` remains a hard WU-CM-01-F01 closeout requirement until design/control truth is explicitly changed.
- The blocker root cause is in production `dayu/host/run_input.py`, not in public smoke tests.
- The correct owner is RunInputBuilder / memory projection message assembly, not Engine, Runner, Service, or smoke helpers.
- The existing red public smoke assertions must remain active as acceptance tests.

## Accepted Findings

### 1. System envelope section title / separator must be specified before production code

- Source: DS Finding 1.
- Severity: high.
- Controller decision: accepted.
- Required action: S7-R1-S0 design sync must define concrete LLM-facing section titles, ordering, and separators before S7-R1-S1 code changes. Implementation must not invent these values ad hoc.

### 2. Selected recent evidence position change must be explicit

- Source: DS Finding 2.
- Severity: medium.
- Controller decision: accepted.
- Required action: S7-R1-S0 must state that moving system-scoped selected recent evidence into the single system envelope changes its original interleaved position. The design must either accept that trade-off with validation coverage or choose another role strategy before implementation.

### 3. Internal ref replacement strategy must be concrete

- Source: DS Finding 3.
- Severity: medium.
- Controller decision: accepted.
- Required action: S7-R1-S0 must include a replacement table for `policy_snapshot_ref`, `tool_call_id`, event ids, payload/artifact refs, digests, cursors, projection metadata, and other LLM-facing internal fields. Each entry must say remove, replace with business text, or replace with Host-neutral unavailable wording.

### 4. Manifest verification boundary must be clarified

- Source: DS Finding 4.
- Severity: low.
- Controller decision: accepted.
- Required action: S7-R1-S0 or the implementation report must distinguish public-path message assertions from focused durable manifest assertions. Reading manifest artifacts through existing test helpers is allowed for manifest tests; public smoke must still prove message shape through request / runner messages.

### 5. Boundedness enforcement must be testable

- Source: DS Finding 5.
- Severity: low.
- Controller decision: accepted.
- Required action: S7-R1-S0/S1 must state that merging does not add new content and must add a sanity assertion for merged envelope size or section cap preservation.

## Next Gate

Proceed to S7-R1-S0 design contract sync.

Allowed files for the next gate:

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- review / implementation artifact under `docs/reviews/`

No production `run_input.py` changes may begin until the design sync covers the accepted findings above.
