# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Code Review Controller Adjudication

## Review Inputs

- AgentMiMo: PASS 0.
- AgentDS: three findings, one Medium and two Low.
- Controller decision: all three accepted; fix and independent re-review required.

## Accepted Findings

### P3-C-S1-CR-F01 — Path-aware nested label validation

The finding is valid, but the root cause is broader than one fact field. Persisted nested label tuples are validated for uniqueness only inside typed constructors, so duplicate-label errors lose the item JSON path.

Required fix:

- Add or extend one parser-owner helper that validates non-empty unique text lists with a caller-provided full path.
- Use it for persisted candidate label lists whose typed contracts require uniqueness, including fact evidence/source labels and the corresponding summary/anchor/intent/reference/diagnostic source labels.
- Preserve strict rejection semantics; only diagnostics gain precise paths.
- Add tests proving at least fact and another nested category report indexed paths.

### P3-C-S1-CR-F02 — Dead Memory diagnostic enum

`MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` has no producer after invalid candidates move to the persisted parser boundary. Comments or deprecation markers would retain dead governance vocabulary.

Required fix: remove the enum member and prove a production source scan has zero matches.

### P3-C-S1-CR-F03 — Contract-only business text helper

`accepted_compact_business_texts()` has no production consumer in S1. Keeping it until S2 would make the accepted S1 commit contain a contract-only half product.

Required fix:

- Remove the helper and its S1-only test now.
- Record that S2 must implement it atomically with `context_budget.estimate_post_compact_budget()` and its integration test.
- Do not duplicate its traversal in another S1 consumer.

## Residual Scope

- Compact-material previous-view parsing and budget integration remain S2.
- Accepted-evidence rendering remains S3.
- No compatibility fallback, reserved enum, dead wrapper, or downstream special case is allowed.

## Next Gate

AgentCodex fixes `P3-C-S1-CR-F01` through `P3-C-S1-CR-F03`, reruns the full S1 validation matrix, per-file coverage and pyright, and updates the implementation/fix artifacts. AgentMiMo and AgentDS then independently re-review all accepted findings and scan for regressions.
