# WU-TOOL-02 Draft PR Review — AgentDS

## Scope and Reviewed Inputs

- **Work unit**: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- **Gate**: draft PR review
- **PR**: [#108](https://github.com/noho/dayu-agent-r/pull/108), `refactor/wu-tool-02-accept-candidate-cleanup` → `main`
- **Reviewed inputs**:
  - Design source: `docs/host/design.md`
  - Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
  - Aggregate adjudication: `docs/reviews/wu-tool-02-aggregate-deepreview-controller-adjudication-20260602.md`
  - Extra full-repo adjudication: `docs/reviews/wu-tool-02-extra-full-repo-review-controller-adjudication-20260602.md`
  - PR diff: `gh pr diff 108` (5657 additions, 571 deletions across 1 production file, 5 test files, and docs artifacts)
  - Current production file state: `dayu/host/tool_runtime.py`
  - Current test state: 5 affected test files

## CI/Checks Observation

GitHub PR #108 reports `statusCheckRollup: []` — no status checks configured or reported. This is noted for the record; it does not constitute a blocking finding, as local validation (below) is comprehensive.

## Local Validation

| Check | Result |
|---|---|
| 206 affected Host tests | 206 passed, 0 failed |
| Full pyright | 0 errors, 0 warnings |
| Payload consumer regression tests | 121 passed (per Slice 4 verified) |
| `rg` residual flat-field access | 0 hits in `tool_runtime.py` |

## Review Findings

### No Blocking Findings

After reviewing the complete PR diff and the current state of the production file against the approved plan, prior adjudications, and the following correctness domains, I found **no actionable PR-blocking findings**.

#### Correctness Areas Checked

1. **EventLog durable truth**: All `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED`, and `TOOL_RESULT_ACCEPTED` payload keys, value shapes, and dictionary structure are preserved identically. Payload values are read from the new typed sub-structures — no key was added, removed, reordered, or renamed.

2. **Accepted evidence envelope**: `AcceptedEvidenceEnvelope` constructor arguments are read from `candidate.call.*`, `candidate.idempotency.semantic_input_digest`, and `_candidate_result(candidate).*`. Shape, field ordering, and value semantics are identical.

3. **Event id derivation**: `_tool_accept_event_plan()` digest input dict keys and values are preserved — identity fields read from `candidate.identity.*`, call fields from `candidate.call.*`, idempotency fields from `candidate.idempotency.*`. The resulting `tool_fact_id` is stable.

4. **Idempotency scope**: `_accept_idempotency_scope()` reads `attempt_id`, `tool_call_id`, and `accept_idempotency_key` from the new sub-structures. Scope derivation logic (`f"{attempt_id}:{tool_call_id}"`) is unchanged.

5. **Duplicate governance**: ALLOW duplicate governance records still require `duplicate_scope` and `duplicate_decision_message` — consistent with old `_validate_duplicate_fields()` behavior. Non-ALLOW decisions additionally require `duplicate_key`. The prior adjudication's ruling that this is correct current behavior stands.

6. **REUSE path**: `_append_tool_result_if_needed()` guards with `if candidate.tool_fact_kind is ToolFactKind.REUSE: return None` (line 3315-3316), ensuring `_candidate_result()` is never called for reuse candidates. The `result=None` on reuse candidates is correctly handled throughout.

7. **Validation decomposition**: Sub-structure `__post_init__` validators (`_validate_tool_accept_identity`, `_validate_tool_accept_call`, `_validate_tool_accept_result`, etc.) enforce internal invariants. Candidate-level validators (`_validate_result_fact_policy`, `_validate_governed_error_candidate`, `_validate_duplicate_governed_candidate`, `_validate_reuse_candidate`) enforce cross-structure fact-kind constraints. The decomposition is sound with no circular dependency or validation gap.

8. **Type safety**: `ToolAcceptResult.raw_tool_outcome: JsonValue` (non-optional) is a valid tightening — REUSE candidates carry `result=None`, and all result-bearing fact kinds (`COMPLETED`, `FAILED`, `CANCELLED`, `GOVERNED_ERROR`) require non-None `raw_tool_outcome` via `_require_raw_tool_outcome()`. No `Any`, `object`, or untyped signatures were introduced or spread.

9. **Layering**: `ToolFactAcceptCandidate` and all sub-structures remain Host-internal (`dayu/host/tool_runtime.py`). No public API exports, no `dayu.runtime` boundary violations, no upward dependency leakage.

10. **Memory / compaction / tool trace consumers**: `dayu/host/tool_trace.py`, `dayu/host/compaction_evidence.py`, `dayu/host/compact_material.py`, `dayu/host/memory.py` are unchanged. They consume committed EventLog payloads and `AcceptedEvidenceEnvelope`, not `ToolFactAcceptCandidate` directly. Payload consumer regression tests (121) confirm no semantic change.

### Known Non-Blocking Notes (Already Adjudicated, Not Repeated)

The following items were previously identified and adjudicated as non-blocking. I confirmed they are either correctly implemented or are deferred-with-owner:

- **`else None` indentation** at `tool_runtime.py:3521`: Purely stylistic, no Python semantic change. Controller ruled non-blocking.
- **ALLOW duplicate governance scope/message requirement**: Matches old validator behavior and is consistent with auditable governance records. Controller ruled correct current behavior.
- **`ToolFactKind.LOST` test gap**: Pre-existing, deferred to future ToolRuntime fact-kind expansion (RR-TOOL-03).
- **Sub-structure direct unit tests**: Deferred to WU-LAYER-02 test organization cleanup (RR-TOOL-04).

### Adversarial Pass

I specifically checked the following potential failure modes and found none:

- **`_candidate_result()` on REUSE candidates**: All guarded by `REUSE` fact-kind check at the `_append_tool_result_if_needed` level.
- **`duplicate.duplicate_decision.value` when `duplicate is None`**: All accesses in `_tool_result_payload` and `_append_tool_call_governed_if_needed` are guarded by `if duplicate is not None`.
- **`ToolAcceptResult.__post_init__` rejecting None `raw_tool_outcome`**: Only result-bearing fact kinds require raw outcome; REUSE correctly omits result entirely.
- **`_validate_tool_accept_duplicate_governance` rejecting ALLOW with missing scope/message**: Consistent with prior adjudication — ALLOW duplicate governance is still a governance record requiring auditable scope and message.
- **Payload key reordering in `_tool_result_payload` dict literal**: All keys and their order are identical to the old version.

## Coverage Judgment

**Sufficient for draft-PR-pass.** The 206 affected Host tests cover normal tool fact acceptance, reuse, duplicate governance (ALLOW, HINT, REQUIRE_JUSTIFICATION, HARD_STOP, DURABLE_MISSING), governed error, truncation, fetch_more, diagnostics, and accept barrier rejection paths. Payload consumer regression tests (121) cover tool trace projection, memory projection, and compaction operation. Full pyright (0 errors) validates type consistency across the entire codebase.

Residual coverage items (LOST test gap, sub-structure direct unit tests) are tracked in the control document's residual risk table with explicit owners and do not introduce new regression risk for the current work unit.

## PR Readiness Verdict

**Verdict: pass**

This PR contains no actionable blocking findings. The typed composition root migration is complete, correct, and consistent with the approved plan. EventLog durable truth, accepted evidence envelope, duplicate governance semantics, and all downstream consumer behaviors are preserved. Local validation (206 tests, full pyright 0 errors) is comprehensive. The known non-blocking notes are already adjudicated and do not require PR-blocking fixes.
