# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 code review Controller adjudication

## 1. Gate identity

- Active work unit: existing umbrella `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU: R04 `awaiting provider resolution composition`, unique atomic S1.
- Accepted plan commit: `983070dd1d56490d23529970960349a3df3e9787`.
- Implementation base/current HEAD: `a4ffd7641c8f114e987972d77572c2c2b4a8202f`; no implementation commit exists yet.
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-r04-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r04-s1-code-review-ds.md`
- Controller re-validation: `docs/reviews/wu-semantic-ownership-01-r04-s1-controller-revalidation.md`.

This adjudication covers the complete final R04-S1 product/config/test/README/smoke diff, the Controller finding fix, and both independent reviews. It does not authorize R05 or any other deferred work.

## 2. Review summary

AgentMiMo returned `PASS` with zero material finding and zero open question after a complete owner, configuration, composition, LLM-facing, security, test, coverage, and README pass.

AgentDS independently reviewed the complete implementation and returned a passing/non-blocking verdict. Its corrected evidence records a 419-test reviewer subset, while the Controller re-validation independently ran the accepted-plan complete 509-test matrix. DS reported two observations for Controller classification: the already-deferred R05 observation-timeout behavior and a speculative future provider identity collision.

Both reviewers independently confirm that `R04-S1-CV-F01` is closed by required construction state, the discovery owner's unique direct constructor, `dataclasses.replace(...)` at every derived consumer, a public-composition regression, and full pyright.

## 3. Finding adjudication

### DS-F01 — observation timeout currently terminalizes as LOST

**Decision: deferred to the already-planned R05 owner; not an accepted R04-S1 fix.**

The code evidence is real: the unchanged observation-timeout branch in `dayu/host/wait_adapter.py` still resolves a lost outcome. The authoritative Controller discussion Topic 5 requires the future behavior to revoke late publication, record a transient diagnostic, release the claim, and back off without terminalizing the wait/Run.

However, the accepted R04 plan §1/§4 explicitly excludes “R05 observation-timeout / retry-backoff / LOST state machine”, and the added-line scan proves this branch predates the R04 implementation base. Implementing the change in R04 would violate the accepted owner/dependency boundary and the user's explicit sub-WU sequencing. This is not forgotten or accepted as correct final behavior: R05 remains mandatory before umbrella final closeout and owns this exact code fix.

R04 disposition: `DEFERRED_TO_R05 / NO_CURRENT_FIX`.

### DS-F02 — future provider might reuse one recognized identity fragment

**Decision: rejected-with-reason; speculative future framework change without current defect evidence.**

Current Service identity ownership deliberately recognizes built-in providers through any one of the established `provider_id`, `import_path`, or `source_id` identifiers. The same existing OR identity rule already owns Fins awaiting routing, Fins workspace injection, and Web workspace configuration. Accepted plan §2/§4.2 explicitly requires reuse of this existing identity and forbids inventing a generic future-provider framework.

The reported failure requires a hypothetical future provider to reuse a built-in identity fragment while claiming to be unknown. No current packaged config, overlay, provider contract, or test fixture has such an identity collision. A provider with three unknown identifiers remains opaque, as proved by `test_unknown_third_party_provider_mode_field_remains_opaque`. Replacing the existing alternative-identifier contract with a new conjunctive three-field tuple would be a new semantic contract, could reject existing identity aliases, and is not supported by a current product requirement.

R04 disposition: `REJECTED_WITH_REASON / NO_FIX`.

## 4. MiMo residual observations

MiMo recorded two non-finding observations:

1. A possible lack of policy-specific NaN/Infinity tests is no current gap. `test_config_json_boundary_rejects_non_finite_number_literals` already exercises `NaN`, `Infinity`, `-Infinity`, and overflow at the shared ConfigLoader JSON owner, and the policy field parser independently calls the shared finite-number validator. No duplicate policy-only literal test is required for correctness.
2. Rebuilding a small private spec-id index in pure validation/registry helpers is not a semantic duplication or measurable product defect. The typed metadata tuple remains the source of truth; no raw mode/config is reparsed. A performance refactor without evidence would be overdesign.

Disposition for both: `OBSERVATION / NO_FIX`.

## 5. Final ledger

| category | count | items |
|---|---:|---|
| accepted current R04-S1 findings | 0 | none |
| deferred to an existing mandatory owner | 1 | DS-F01 -> R05 |
| rejected-with-reason | 1 | DS-F02 |
| observation / no-fix | 2 | MiMo residual notes |
| blocking questions | 0 | none |

There is no accepted current finding to send through an implementation fix/re-review cycle. Creating an empty fix or re-review gate would add no evidence. Both complete reviews already evaluated the final F01-corrected implementation and independently approved it.

## 6. Validation and boundary decision

Controller evidence remains:

- focused F01/public-composition set: `36 passed, 3 warnings`;
- accepted-plan complete affected matrix: `509 passed, 3 warnings`;
- all nine modified production Python files: `85.54%` to `100%` coverage;
- full pyright: zero errors/warnings/information;
- Ruff, `git diff --check`, source/propagation/security/deferred-scope scans: pass;
- packaged ConfigLoader -> provider discovery -> Service composition -> public Host smoke: pass, including `not_ready=1 -> ready=1 -> SUCCEEDED`;
- README trigger/ownership check: pass.

R04-S1 did not implement R05, Issue 175, callback transport, Host public API/open_host changes, unified tool authorization, permission schema, or Issue 142/151/177/178. It did not remove or weaken existing allowed-path, Web defense, containment/symlink, DNS/peer, resource-budget, atomic-write, cancellation, durable-wait, or process-fencing security behavior.

## 7. Verdict and next gate

**PASS / READY_FOR_ACCEPTED_LOCAL_COMMIT.**

All current R04-S1 findings are closed or finally classified. The next and only authorized action is an exact-scope accepted local commit containing the final R04-S1 implementation, tests, README/smoke changes, complete evidence chain, and current control state. R04 remains incomplete after that commit until aggregate validation and dual aggregate deepreview pass. R05 and all later umbrella remediation sub-WUs remain pending; no push or PR is authorized.
