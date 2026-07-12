# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Goal Confirmation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Theme: Fins financial semantics, XBRL projection, processor freshness, and read contracts
- Type: production-high semantic ownership fix
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`
- Source finding truth: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`

## Motivation Check

R3-D is valid and should enter plan gate.

The accepted findings identify current Fins owner-boundary failures: financial scale, fiscal period, data quality, failure reason, source freshness, XBRL query failure, text decode failure, 10-Q virtual-section repair, upload ticker normalization, duplicated optional string normalization, and read/search error semantics are not consistently produced once by the correct Fins owner and preserved through read-runtime / LLM-facing projection.

This is not a style cleanup. These failures can produce apparently successful but incomplete financial answers, stale processor output, empty XBRL results after exceptions, or LLM-facing output that hides quality / reason / period semantics.

## Correct Owner

- Financial result/domain semantics: Fins processor / financial-domain result contracts.
- XBRL query and degradation semantics: Fins XBRL query owner plus read-runtime projection owner.
- Read/search user-facing contracts: Fins read runtime and tool result types.
- Source freshness / reprocess invalidation: Fins storage/processed repository and pipeline owners.
- SEC fiscal period/version/ticker normalization: Fins domain/pipeline owner helpers.

## Non-Goals

- Do not implement Web/Documents egress, resource caps, diagnostics, or oracle fixes; those are R3-E.
- Do not implement tool-security policy. Upload allowlist/file authority, URL/TLS/redirect/SSRF provenance, remote byte-budget, and LLM-facing upload/download security schema/prompt changes remain deferred to a later dedicated owner.
- Do not rewrite the entire Fins processor architecture or split broad god-file governance unless directly required to close accepted R3-D findings.
- Do not preserve compatibility shims for old tests or old accidental empty-success behavior.

## Success Signals

- Financial result projection preserves owner-level period, scale, quality, and reason semantics instead of recomputing or dropping them downstream.
- XBRL/query failures become typed degradation or failure signals, not successful empty sets.
- Missing scale/year semantics are either produced by the processor owner or explicitly rejected/degraded at that owner boundary.
- Fiscal period and optional string normalization use one owner source of truth.
- 10-Q virtual sections rebuild refs/table assignments after expansion.
- Processor cache is invalidated after reprocess or freshness is validated before reuse.
- Non-UTF-8 decode and read/search failures do not silently disappear.
- Existing ticker normalization owner is used for upload alias handling.

## Validation Expectations

Use production-high validation. At minimum the plan must include focused tests for result projection, XBRL exception/degradation, BS scale, 10-Q virtual sections/tables, processor cache invalidation or freshness validation, read-runtime degradation, SEC skip/version, ticker normalization, pyright, `git diff --check`, README decision, and propagation/source scans.

## Decision

Goal confirmation accepted by controller based on the user's instruction to continue fixing all accepted findings and not stop at individual sub WUs. Proceed to R3-D plan gate via AgentCodex.
