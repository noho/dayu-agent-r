# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Review Controller Adjudication

## Adjudication Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Gate: `plan review controller adjudication`
- Timestamp: 2026-07-13 08:07:00 CST
- Controller: AgentController
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-ds.md`
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control truth:
  - `docs/host/issues-implementation-control.md`
  - `docs/phaseflow-umbrella-optimization-control.md`

## Controller Decision

`changes_requested`

The plan motive and owner boundary are accepted: R3-D is a production-high Fins semantic ownership fix, not style cleanup. The three-slice split is also accepted as the minimum stable closure for financial/XBRL contracts, processor/read consistency, and fiscal/pipeline normalization.

The plan must be revised before implementation. AgentDS identified two medium-severity blocking plan gaps, and AgentMiMo identified non-blocking clarifications that should be absorbed in the same plan-fix pass to reduce implementation rework.

## Accepted Review Findings

### PF-01 - XBRL Empty-Success And Failure Matrix Must Be Implementable

- Source reviews: MiMo finding 1; DS finding F1 and F3.
- Controller severity: blocking plan-fix.
- Accepted correction:
  - Add an explicit S1 pre-check task for the current edgartools query behavior or a bounded fallback strategy.
  - Clarify how `_query_facts_rows` distinguishes execute exception, successful zero rows, partial failure, and all-failed concepts.
  - Clarify caller mapping for `sec_processor.py` and `bs_report_form_common.py`: callers consume `XbrlConceptQuerySummary.rows`, preserve failed concept accounting, and produce `data_quality/reason` from the state matrix.
  - Resolve the quality terminology tension for legitimate empty XBRL query results. The plan must define whether `data_quality="xbrl"` can mean "XBRL query executed successfully even with zero facts" or whether another value is used, and the LLM-facing description/tests must match.

### PF-02 - XBRL Dedup Count Contract Must Have A Single Owner

- Source review: MiMo finding 2.
- Controller severity: required plan-fix.
- Accepted correction:
  - State whether `deduped_fact_count` belongs to the domain XBRL result contract or to the read projection contract.
  - Make requiredness explicit; do not leave it as an implicit `NotRequired` or extra payload.
  - Add a verification point that raw `total` remains the producer count and dedup count cannot overwrite it.

### PF-03 - Source Meta Cache Freshness Must Cover Independent Meta Reads

- Source reviews: DS finding F2; MiMo finding 3 partially.
- Controller severity: blocking plan-fix.
- Accepted correction:
  - S2 must explicitly require revision comparison in `_get_source_meta_cached_by_kind` or its renamed owner equivalent, including independent list/info/citation call paths that do not build a processor.
  - S2 freshness matrix must include `source revision changes, meta cache accessed independently -> meta rebuilt from storage`.
  - Rebuild race behavior must be concrete: either immediate fail with no retry, or a fixed retry count. The plan must not leave "no unbounded loop" to implementation interpretation.

### PF-04 - 10-Q Expansion Ref Uniqueness Must Be Verified At The Owner

- Source review: DS finding F4.
- Controller severity: required plan-fix.
- Accepted correction:
  - Clarify whether `expand_ten_q_virtual_sections_content` creates new refs or only modifies content/order.
  - If it can create child refs, S2 must state the ref uniqueness rule and add a test that expansion output has unique refs before table assignment.

### PF-05 - HTML/OCR Financial Producer Semantics Must Be Explicit

- Source review: DS finding F5.
- Controller severity: required plan-fix.
- Accepted correction:
  - S1 must define HTML/OCR scale semantics separately from XBRL decimals.
  - If scale can be extracted from table heading or OCR text, the extracting helper is the owner. If no direct evidence exists, producer returns `partial` with the appropriate scale reason.
  - Add tests for HTML/OCR producer quality/reason behavior.

### PF-06 - LLM-Facing Tool Description And Tests Need Concrete Guardrails

- Source reviews: MiMo finding 4; DS finding F6.
- Controller severity: required plan-fix.
- Accepted correction:
  - Add concise example or template text for `get_financial_statement` and `query_xbrl_facts` descriptions, covering periods, scale, units, data quality, reason, total, and dedup count without Host/Engine/security governance terms.
  - Replace the ambiguous `-k '6k and decode'` validation with a named new test or a command that cannot pass with zero selected tests.

## Rejected Or Narrowed Review Points

- No review finding authorizes R3-E, tool-security, upload/download security policy, SSRF/TLS/redirect policy, remote byte budget, or LLM-facing upload/download security schema work.
- The controller preserves the plan's narrowed decision not to fold 6-K dual-engine routing, creation-lock lifetime cleanup, or full `DocumentMeta` migration into R3-D.
- PF-03 does not authorize TTL, mtime, processed-meta freshness, or ingestion callback coupling; source freshness remains storage revision owned.

## Required Plan-Fix Gate

AgentCodex must update only the plan artifact unless it discovers an explicit controller blocker. The fix gate must:

1. Edit `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`.
2. Preserve the accepted three-slice structure unless a direct review finding proves it cannot hold.
3. Address PF-01 through PF-06 with concrete plan text, validation points, scans, or stop conditions.
4. Avoid production/test code edits.
5. Run `git diff --check`.
6. Produce a plan-fix artifact at `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-fix-codex.md`.

After the plan fix, AgentMiMo and AgentDS must run re-review. Implementation may start only after both re-reviews pass or the controller adjudicates all remaining findings as non-blocking.

## Blocking Questions

None for the controller. The plan-fix gate has enough evidence and bounded instructions to proceed.
