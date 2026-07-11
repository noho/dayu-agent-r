# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-K - Test harness semantic coupling cleanup`
- Gate: plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-p3-k-goal-confirmation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-ds.md`

## Review Summary

- AgentMiMo conclusion: `pass-with-risks`, four findings.
- AgentDS conclusion: `PASS-WITH-FINDINGS`, seven findings.
- Both reviewers accept the plan's core stance: preserve legitimate public-contract locks and remove ownerless test parallel truth.
- Both reviewers agree the plan must be tightened before implementation.

## Controller Findings

### P3-K-PF-01 - Clarify S1 resume-guidance assertion ownership

- Source findings: MiMo 01, DS P3K-F07, MiMo OQ-1.
- Decision: `accepted`.
- Reason: The plan currently groups owner-derived dynamic assertions and hardcoded production guidance text under one "semantic helper" idea. That can either weaken coverage or leave implementation ambiguity.
- Required plan fix:
  - Distinguish dynamic owner-derived content assertions from production-owned guidance constants.
  - Specify whether the helper should assert production constants directly or assert named production-owned guidance semantics.
  - State that the helper must not use vague substring checks.
  - Clarify that any optional shared helper file is only needed if reuse justifies it; otherwise file-local private helpers are preferred.

### P3-K-PF-02 - Make S2 raw SQL decisions code-generation-ready

- Source findings: MiMo 02, DS P3K-F01, DS P3K-F02, DS P3K-F05, DS open questions 1 and 2.
- Decision: `accepted`.
- Reason: The plan overstates replaceability of raw SQL helpers and references at least one non-existent production method. This can send implementation into API invention or wrong helper usage.
- Required plan fix:
  - Enumerate each TF-2 raw SQL helper with one final disposition: replace via exact existing owner helper, keep as diagnostic-only raw SQL, or keep as fault-injection-only raw SQL.
  - Correct `HostInstanceLivenessStore.read_by_host_instance_id(...)` to the actual `read_host_instance(...)` API or state that all-instance diagnostics have no exact production helper.
  - Verify projection checkpoint helper names/signatures or explicitly classify the helper as raw SQL fault injection / diagnostic retention.
  - Update S2 completion signal so success is not measured by reducing raw SQL count broadly, but by eliminating only exact-replaceable raw SQL and documenting the rest.

### P3-K-PF-03 - Tighten S3 cancellation-helper contract and validation

- Source findings: MiMo 03, DS P3K-F03, DS P3K-F04, DS P3K-F06.
- Decision: `accepted`.
- Reason: The plan's "where feasible" and optional coverage language leaves room to keep the duplicated fake semantics that TF-4 is meant to close.
- Required plan fix:
  - Define `ControllableCancellationToken()` as open by default.
  - Require explicit `request_cancel(reason)` to transition to cancelled; do not preserve constructor-as-cancelled semantics.
  - Require external call sites to migrate away from `.trigger(...)`; any alias may exist only inside the helper as a temporary internal alias if it has identical semantics and no external call sites.
  - Decide `tests/service/test_fins_direct.py` handling explicitly: use the canonical open token or keep a clearly named non-mutable open observation stub with no cancellation semantics.
  - Require a focused helper contract test for open state, UTC-aware `requested_at`, reason, and idempotent cancellation.

### P3-K-PF-04 - Record README no-update branch explicitly

- Source finding: MiMo 04.
- Decision: `accepted`.
- Reason: AGENTS.md requires README trigger decisions after tests changes. The plan must tell implementation to record a no-update decision when no README trigger actually applies.
- Required plan fix:
  - Add an explicit "if none of the README trigger conditions apply, record `tests/README.md: no update needed` in the implementation artifact" branch.

## Rejected / Deferred Items

- DS open question about adding `test_dispatch_scheduler.py` to S3 validation is `rejected-with-reason`: `test_dispatch_scheduler.py` uses its own scheduler cancellation tokens and already has baseline compaction previous-view failures unrelated to TF-4. It should not be added as a required S3 validation target unless implementation actually changes that file or same-path evidence appears.

## Residual Risk

- P3-K remains a test-only cleanup. If implementation discovers a production API is needed solely for tests, it must stop and return to controller.
- Some raw SQL will likely remain. That is acceptable only when explicitly marked diagnostic-only or fault-injection-only.

## Next Gate

Dispatch AgentCodex for plan fix. Do not enter implementation until MiMo and DS re-review the fixed plan.
