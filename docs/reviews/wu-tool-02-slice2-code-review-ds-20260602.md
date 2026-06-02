# WU-TOOL-02 Slice 2 Code Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-06-02
- **Gate**: code review
- **Branch**: `refactor/wu-tool-02-accept-candidate-cleanup`
- **Review Target**: uncommitted workspace diff for Slice 2
- **Primary Plan**: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- **Implementation Handoff**: `docs/reviews/wu-tool-02-slice2-implementation-handoff-20260602.md`
- **Implementation Report**: `docs/reviews/wu-tool-02-slice2-implementation-report-20260602.md`
- **Design Source of Truth**: `docs/host/design.md`

## Review Scope

Per plan Slice 2 allowed files:
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`

Review of non-allowed files is advisory only; findings in those files should be deferred to their respective slice ownership.

## Review Summary

**Result: CODE REVIEW PASS — NO BLOCKING FINDINGS.**

The implementation correctly migrates `ToolFactAcceptCandidate` from an over-wide flat dataclass to a composition root of typed sub-structures, with all producer, accept barrier consumer, EventLog payload, accepted evidence envelope, accepted ack, and logging paths properly updated. No old flat field facades, properties, or re-exports remain. No `Any`, `object`, or untyped signatures were introduced. EventLog payload keys, accepted evidence envelope shape, duplicate governance attempt-local semantics, reuse semantics, idempotency scope, and awaiting accept path are all preserved.

Three non-blocking minor findings and one advisory were identified.

---

## Positive Observations

### 1. Structure Migration — Complete and Clean

`ToolFactAcceptCandidate` is now a composition root:

```text
ToolFactAcceptCandidate
  identity: ToolAcceptIdentity       (session_id, run_id, attempt_id, execution_id)
  call: ToolAcceptCall               (iteration_id, tool_call_id, tool_name, digests)
  tool_fact_kind: ToolFactKind
  result: ToolAcceptResult | None    (outcome_digest, payload_digest, payload_ref, truncation, raw_tool_outcome)
  governance: ToolAcceptGovernance   (policy_decision, tool_idempotency_key, duplicate)
  idempotency: ToolAcceptIdempotency (accept_idempotency_key, semantic_input_digest)
  diagnostics: ToolAcceptDiagnostics (diagnostic_refs)
```

All 20+ old flat top-level fields removed. No `@property` forwarding, no `__getattr__` passthrough, no compatibility re-exports. Confirmed by rg scan: zero old-flat-field access patterns on `ToolFactAcceptCandidate` instances in the allowed files.

### 2. Validation Decomposition — Correct Layering

| Layer | Validator | Scope |
|-------|-----------|-------|
| `ToolAcceptIdentity.__post_init__` | `_validate_tool_accept_identity` | Non-empty text fields |
| `ToolAcceptCall.__post_init__` | `_validate_tool_accept_call` | Non-empty text + sha256 digests |
| `ToolAcceptResult.__post_init__` | `_validate_tool_accept_result` | sha256 digest, payload_ref consistency, truncation type |
| `ToolAcceptDuplicateGovernance.__post_init__` | `_validate_tool_accept_duplicate_governance` | key/decision/scope/message/refs |
| `ToolAcceptGovernance.__post_init__` | `_validate_tool_accept_governance` | policy_decision type, idempotency_key |
| `ToolAcceptIdempotency.__post_init__` | `_validate_tool_accept_idempotency` | Non-empty key, sha256 digest |
| `ToolAcceptDiagnostics.__post_init__` | `_validate_tool_accept_diagnostics` | Ref type checks |
| `ToolFactAcceptCandidate.__post_init__` | Cross-structure fact-kind validators | Ordinary result / reuse / plain governed / duplicate governed / unsupported LOST |

Sub-structure `__post_init__` handles internal invariants. Composite root handles cross-structure constraints. The `payload_digest must match payload_ref digest` constraint was correctly moved from the old `_validate_common_candidate_fields` to `_validate_tool_accept_result`.

### 3. Producer Migration — Both Paths

- `_tool_fact_accept_candidate()`: constructs `ToolAcceptIdentity`, `ToolAcceptCall`, `ToolAcceptResult`, `ToolAcceptGovernance`, `ToolAcceptIdempotency`, `ToolAcceptDiagnostics` then composes `ToolFactAcceptCandidate`.
- `_tool_fact_reuse_accept_candidate()`: constructs same sub-structures but `result=None`, `governance.policy_decision.kind=REUSE`, `governance.duplicate.duplicate_decision=REUSE`.

Conditional `reuse_prior_event_refs` assignment for `GOVERNED_ERROR` with `duplicate_governed` correctly preserved.

### 4. Consumer Migration — All Paths Updated

Verified every accept barrier consumer path reads from the new sub-structure:

- `_accept_idempotency_scope()`: `candidate.identity.attempt_id`, `candidate.call.tool_call_id`, `candidate.idempotency.accept_idempotency_key`
- `_read_accept_context()` / `_invalid_accept_context_reason()`: `candidate.identity.*`
- `_candidate_payload_descriptor_exists()`: `candidate.result` with None guard for reuse
- `_tool_accept_event_plan()`: digest input keys unchanged, reads from sub-structures
- `_tool_call_requested_event_request()`: payload keys unchanged
- `_append_tool_call_governed_if_needed()`: payload keys unchanged, duplicate fields read from `candidate.governance.duplicate` with proper None guards
- `_tool_result_payload()`: payload keys unchanged, result/duplicate fields read from sub-structures
- `_accepted_evidence_envelope()`: shape unchanged, reads from sub-structures
- `_accepted_ack_from_rows()` / `_ack_result_digest()`: correct reuse fallback logic preserved
- `_rejected_ack()`: diagnostic_refs read from `candidate.diagnostics`
- `_should_append_governed_event()`: logic preserved, reads from `candidate.governance.*`
- `_log_tool_fact_accept_result()`: identity/call fields read from sub-structures

### 5. Test Migration — Composition Helpers, No Compatibility Branches

Test helpers properly migrated to composition pattern:

- `_completed_candidate()`: uses `_candidate_identity()`, `_candidate_call()`, `_allow_governance()`, `_candidate_idempotency()` helpers
- `_reuse_candidate()`: constructs `ToolAcceptGovernance` with `ToolAcceptDuplicateGovernance` inline
- `_fact_kind_candidate()`: uses `_candidate_identity()`, `_candidate_call()`, `_candidate_idempotency()` helpers
- `_candidate_identity()`, `_candidate_call()`, `_allow_governance()`, `_candidate_idempotency()`, `_required_result()`, `_required_duplicate()`: small focused test helpers
- `_accepted_ack_for_call()` in executor test: migrated to composition structure
- `_accepted_ack()` in both executor and truncation tests: migrated, correct None-safe `result` access for result_digest + payload_ref

No compatibility branches. No old flat fields kept for test convenience.

### 6. Type Safety

- Zero `Any` types introduced
- Zero `object` types introduced
- Zero untyped function signatures
- All sub-structures are `@dataclass(frozen=True, slots=True)` with strict type annotations
- Slice 2 scope pyright: `0 errors, 0 warnings, 0 informations`

### 7. Semantic Preservation

Confirmed via code inspection and test pass:

| Semantic | Status |
|----------|--------|
| `TOOL_CALL_REQUESTED` payload keys | Unchanged |
| `TOOL_CALL_GOVERNED` payload keys | Unchanged |
| `TOOL_RESULT_ACCEPTED` payload keys | Unchanged |
| Accepted evidence envelope shape | Unchanged |
| Duplicate governance attempt-local | Unchanged |
| Reuse (requested + governed, no result) | Unchanged |
| Idempotency scope derivation | Unchanged |
| Accepted ack result_digest fallback | Unchanged |
| Awaiting accept path | Untouched |
| `_tool_awaiting_accept_candidate()` | Untouched |
| `ToolAwaitingAcceptCandidate` | Untouched |

### 8. Validation: LOST Unsupported

`ToolFactAcceptCandidate.__post_init__` still raises `ValueError("unsupported tool_fact_kind")` for `ToolFactKind.LOST`. No new producer, payload, ack, or EventLog semantics introduced for LOST.

---

## Findings

### F-DS-01 — Non-Blocking — Minor — Unreachable nil guard in `_validate_duplicate_governed_candidate`

**Location**: `dayu/host/tool_runtime.py:4213`

```python
if duplicate is None:
    raise ValueError("duplicate governed error requires duplicate decision")
```

**Analysis**: At this point in the function, `decision` has already been confirmed to be in `(HINT, REQUIRE_JUSTIFICATION, HARD_STOP)` (line 4200-4205). Since `decision = duplicate.duplicate_decision if duplicate is not None else None`, if `decision` is not None, `duplicate` must not be None. The check is logically unreachable. It may serve as a pyright type-narrowing guard for `duplicate.duplicate_decision_message` on the next line, but pyright can narrow this transitively.

**Recommendation**: Remove the dead nil guard. If pyright complains, use `assert duplicate is not None` to document the invariant explicitly rather than raising a misleading `ValueError`.

**Severity justification**: No runtime impact — the error can never be raised. Minor code clarity issue.

### F-DS-02 — Non-Blocking — Minor — Redundant duplicate governance validation

**Location**: `dayu/host/tool_runtime.py:4120-4131` (`_validate_duplicate_fields`)

**Analysis**: `_validate_duplicate_fields` delegates to `_validate_tool_accept_duplicate_governance(duplicate)`. However, `ToolAcceptDuplicateGovernance.__post_init__` already calls `_validate_tool_accept_duplicate_governance(self)`. Since `ToolAcceptDuplicateGovernance` is a frozen slots dataclass, its `__post_init__` runs at every construction (including `replace()`). The second call from `_validate_common_candidate_fields → _validate_duplicate_fields` is redundant.

**Recommendation**: Remove `_validate_duplicate_fields` and inline its early-return guard into `_validate_common_candidate_fields`. The duplicate sub-structure's own `__post_init__` is sufficient for internal invariant validation.

**Severity justification**: No correctness impact — duplicate governance validation is idempotent. Minor maintainability issue (two call sites for same validator).

### F-DS-03 — Non-Blocking — Advisory — Slice 3/4 tests expected to fail

**Verification**: 24 tests fail in `test_toolruntime_duplicate_governance.py` and `test_toolruntime_diagnostics.py`. These files are scoped for Slice 3 migration per plan.

**Full pyright**: 77 errors, all from unmigrated test files in `test_toolruntime_duplicate_governance.py`, `test_toolruntime_diagnostics.py`, and projection consumer tests. Zero errors in Slice 2 allowed files.

**Recommendation**: Proceed with Slice 3 migration as planned. No action needed for Slice 2.

---

## Verification Evidence

### Tests — Slice 2 Scope

```
53 passed in 0.36s
```

All tests in `test_toolruntime_accept_barrier.py`, `test_toolruntime_executor.py`, `test_toolruntime_truncation_fetch_more.py`.

### Pyright — Slice 2 Scope

```
0 errors, 0 warnings, 0 informations
```

### Old Flat Field Access — Slice 2 Scope

Zero hits for old `candidate.<flat_field>` patterns on `ToolFactAcceptCandidate` in allowed files. Remaining hits are:
- `ToolAwaitingAcceptCandidate` instances (out of scope, not migrated)
- Slice 3 test files (deferred)

### Adversarial Failure Pass

- **Empty identity**: blocked by `_validate_tool_accept_identity` non-empty check
- **Empty call fields**: blocked by `_validate_tool_accept_call`
- **Missing result on COMPLETED**: blocked by `_require_raw_tool_outcome` → `_candidate_result`
- **Result on REUSE**: blocked by `_validate_reuse_candidate` (`candidate.result is not None`)
- **ALLOW policy on GOVERNED_ERROR**: blocked by `_validate_governed_error_candidate`
- **REUSE policy on COMPLETED**: blocked by `_validate_result_fact_policy`
- **LOST fact kind**: blocked by `else: raise ValueError("unsupported tool_fact_kind")`
- **Missing duplicate_decision_message**: blocked by `ToolAcceptDuplicateGovernance.__post_init__`
- **payload_digest mismatch with payload_ref**: blocked by `_validate_tool_accept_result`
- **Duplicate governed without prior refs**: blocked by `_validate_duplicate_governed_candidate`
- **Durable-missing with prior refs**: blocked by `_validate_duplicate_governed_candidate`

---

## Residual Risks

1. **Slice 3/4 regression risk**: The 24 failing tests and 77 pyright errors in unmigrated files must be resolved in subsequent slices. The Slice 2 implementation report correctly lists these as "uncovered areas."
2. **Full integration test risk**: Only focused unit tests were run. Full integration/end-to-end tests were not part of this slice's validation scope.
3. **F-DS-01 dead code**: Low risk — unreachable code that cannot cause runtime issues. Could confuse future maintainers.

---

## Stop Conditions Check

Per plan Section "Stop Conditions", verified none are triggered:
- No Host public contract changes
- No durable schema changes
- No EventLog event type/payload key changes
- No duplicate governance semantic changes
- No compatibility wrappers/facades/re-exports
- No `Any`/`object`/untyped signatures
- No production consumer changes needed in `tool_trace.py`, `compaction_evidence.py`, `compact_material.py`, `memory.py`

---

## Conclusion

Slice 2 implementation is correct, complete, and well-executed. The composition root migration is clean with proper validation decomposition. All producer and consumer paths are correctly updated. Tests are properly migrated with composition helpers. No blocking findings. Recommend proceeding to Slice 3.
