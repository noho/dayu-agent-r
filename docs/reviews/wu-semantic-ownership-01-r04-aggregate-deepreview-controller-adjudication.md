# WU-SEMANTIC-OWNERSHIP-01 / R04 aggregate deepreview Controller adjudication

## 1. Gate identity

- Active work unit: existing umbrella `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU: R04 `awaiting provider resolution composition`.
- Accepted product commit: `9e349ac4`.
- Control-only transition HEAD: `c2a40929`.
- Aggregate validation: `docs/reviews/wu-semantic-ownership-01-r04-aggregate-validation.md`.
- Aggregate deepreview artifacts:
  - `docs/reviews/wu-semantic-ownership-01-r04-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r04-aggregate-deepreview-ds.md`

Both reviewers independently examined the complete R04 configuration-to-public-Host chain, prior finding ledger, security/deferred boundaries, tests, README, and aggregate evidence. Reviewer conclusions do not independently authorize acceptance; this document is the final R04 aggregate adjudication.

## 2. Review summary

AgentMiMo returned `PASS / ZERO ACCEPTED CURRENT FINDINGS`, with no open question. It independently confirms that `R04-S1-CV-F01` remains closed, the R05 timeout/LOST behavior is correctly deferred rather than accepted as final, and the prior provider identity collision hypothesis remains correctly rejected.

AgentDS also returned a passing verdict with no blocking question. It reverified the same prior ledger and reported one new low-severity internal redundancy observation, `DS-AGG-F01`.

## 3. New finding adjudication

### DS-AGG-F01 — metadata spec-id index is constructed once for validation and once for binding lookup

**Decision: rejected-with-reason / no fix.**

The two calls have different owner-boundary timing and purposes:

1. `_fins_awaiting_provider_metadata_from_configs(...)` validates duplicate active spec ids immediately after producing the complete typed metadata tuple. This occurs before `_shared_fins_awaiting_runtime_from_provider_metadata(...)`, which creates the Fins runtime and initializes storage-backed resources. The early call therefore preserves fail-fast validation before runtime I/O/initialization.
2. `_tool_discovery_bindings(...)` later builds the index it actually owns for provider-config lookup while constructing discovery bindings.

The metadata tuple is the unique source of truth and the public private-boundary result. Reusing the first dictionary would require widening that owner contract to return both tuple and index, introducing two representations and coupling later binding needs into the parser/validation result. Replacing the shared helper with a set-length check would duplicate the duplicate-id validation/error semantic. The current second O(n) construction covers at most the small closed Fins awaiting provider set, has no data drift because the frozen tuple is unchanged, and has no measurable correctness, stability, security, or performance impact.

This is a deliberate minimal interface and fail-fast sequencing tradeoff, not a production defect. No code or test change is authorized.

Disposition: `REJECTED_WITH_REASON / NO_FIX`.

## 4. Prior ledger revalidation

- `R04-S1-CV-F01`: **closed**, with no aggregate drift.
- Code-review DS-F01 observation-timeout -> LOST: **deferred to mandatory R05**, not accepted as umbrella-final behavior and not a current R04 fix.
- Code-review DS-F02 identity-fragment collision: **rejected-with-reason**, unchanged; no current provider/config evidence supports a new conjunctive identity framework.
- Callback transport: existing WU-WAIT-01 / Issue 89 owner; pre-open fail-closed is the correct current behavior.
- Issue 175 and Issues 142/151/177/178: unchanged and outside R04.

## 5. Final aggregate ledger

| category | count | items |
|---|---:|---|
| accepted current R04 aggregate findings | 0 | none |
| deferred to an existing mandatory owner | 1 | code-review DS-F01 -> R05 |
| rejected-with-reason | 2 | code-review DS-F02; DS-AGG-F01 |
| blocking questions | 0 | none |

There is no accepted current aggregate finding to fix or re-review. Both complete aggregate reviewers evaluated the final accepted product commit and approved it. An empty fix/re-review cycle would add no evidence.

## 6. Validation and safety boundary

Controller aggregate validation remains authoritative:

- `509 passed, 3 warnings` at the accepted commit state;
- all nine modified production Python files at `85.54%` to `100%` coverage;
- full pyright zero;
- Ruff, whitespace, owner/source/propagation/security/deferred-scope scans pass;
- packaged public Host smoke passes `not_ready=1 -> ready=1 -> SUCCEEDED` with matching outbox terminal truth.

R04 retains existing identity, allowed paths, Web defense, filesystem containment/symlink protection, DNS/peer proof, resource budgets, atomic writes, cancellation, durable wait, and process fencing. It does not implement a unified tool authorization framework or permission schema. It does not pull R05, Issue 175, callback transport, Host public API/open_host changes, or Issues 142/151/177/178 into current code.

## 7. Verdict and next gate

**PASS / READY_FOR_R04_AGGREGATE_EVIDENCE_COMMIT.**

All current R04 code-review and aggregate-review findings are closed, deferred to an explicit mandatory owner, or rejected with direct reason. The next action is an exact-scope local commit containing the aggregate validation, both aggregate deepreviews, this adjudication, and control state. After that evidence commit, R04 still requires its completion report and Controller completion validation before the control may enter R05 plan. R04 completion does not close the umbrella WU; no push or PR is authorized.
