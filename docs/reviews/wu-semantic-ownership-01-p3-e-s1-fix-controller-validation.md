# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S1 - ToolResult invariant and ToolRuntime LLM-facing hint cleanup`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-fix-codex.md`
- Adjudication artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-controller-adjudication.md`

## Controller Result

`ready-for-independent-rereview`

All four accepted S1 code review findings are fixed in the current workspace pending independent re-review.

## Finding Closure Check

### P3-E-S1-CR-F01 - Fixed Pending Re-review

- Verified `tests/tools/test_doc_tools_provider.py` and `tests/tools/web/test_web_tools_provider.py` no longer assert ToolRuntime synthetic cancellation `hint == "tool_runtime_cancelled"`.
- Verified those tests still assert `accept_port.candidates[0].governance.policy_decision.reason_code == "tool_runtime_cancelled"`.
- Owner boundary remains correct: ToolRuntime governance reason stays in policy diagnostics, not LLM-facing `hint`.

### P3-E-S1-CR-F02 - Fixed Pending Re-review

- Verified `_truncation_failure` now accepts only `message: str`.
- Verified `_TRUNCATION_*_REASON` constants are removed.
- Verified source scan has no `_TRUNCATION_.*REASON` hit.
- Owner boundary remains correct: ToolRuntime owns truncation failure projection; there is no discarded false source-of-truth reason code.

### P3-E-S1-CR-F03 - Fixed Pending Re-review

- Verified `tests/host/test_toolruntime_truncation_fetch_more.py` now uses `_assert_truncation_failure(...)`.
- Verified the helper asserts:
  - `outcome.result.error == "truncation_error"`
  - exact scenario-specific `outcome.result.message`
  - `outcome.result.hint is None`
- Verified coverage includes cursor missing, token mismatch, cursor already used, invalid request, TTL expiry, scope mismatch, digest mismatch, and unreplaceable target.

### P3-E-S1-CR-F04 - Fixed Pending Re-review

- Verified `test_accept_rejected_does_not_expose_raw_fake_result` now asserts `hint is None`.
- Verified it asserts `idempotency_conflict` remains in `message`.
- Verified it preserves the negative raw-result leakage assertion.

## Validation Commands

Passed:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q
```

Result: `233 passed, 1 skipped, 3 warnings in 18.98s`.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed:

```bash
rg -n "_truncation_failure|_TRUNCATION_.*REASON|_hint_with_diagnostic_refs|_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY|_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR|accept_rejected:|hidden-hint" dayu/host/tool_runtime.py tests/host tests/tools
```

Classification: only `_truncation_failure` helper/call/test-helper hits remain. `_TRUNCATION_*_REASON`, hidden hint helper/constants, `accept_rejected:`, and `hidden-hint` have no hits.

Passed:

```bash
git diff --check
```

Result: no output.

Passed coverage workaround:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py --cov=dayu.contracts.tool_result --cov=dayu.host.tool_runtime --cov-report=term-missing -q -k 'not process_backed and not process_capsule and not process_backed_capsule'
```

Result: `137 passed, 17 deselected in 1.70s`; `dayu/contracts/tool_result.py` coverage `100%`, `dayu/host/tool_runtime.py` coverage `85%`.

## README Decision

No README update is required in this fix gate.

- `dayu/host/README.md`: S1 fix does not change Host architecture, ToolRuntime ownership, accept barrier contract, or fetch-more user/developer workflow. It removes an internal dead parameter and retired hidden hint projection.
- `tests/README.md`: S1 fix strengthens existing tests and aligns existing integration assertions; it does not introduce a new test layer or testing convention.
- `dayu/fins/README.md`: the touched Fins test remains S1 alignment coverage only; no Fins storage/tool public contract changes are introduced in this fix gate.

## Propagation Audit

- Truncation:
  - Producer/validator: `TruncationManager` and `FetchMoreToolCallable`.
  - Projection owner: `_truncation_failure(message)` in ToolRuntime.
  - Durable / diagnostics: no new durable field; no discarded reason code remains.
  - LLM-facing output: `ToolResultFailure(error="truncation_error", message=<scenario>, hint=None)`.
  - Tests prove the scenario-specific message did not collapse.
- Cancellation:
  - Producer/validator: ToolRuntime cancellation policy.
  - Diagnostic owner: `ToolPolicyDecision.reason_code`.
  - LLM-facing output: governed failure `hint=None`.
  - Doc/Web integration tests prove the policy reason remains outside `hint`.
- Accept rejection:
  - Producer/validator: accept barrier `ToolFactRejectedAck`.
  - Diagnostic owner: reject ack message / Tool Trace reason.
  - LLM-facing output: `hint=None`, owner-authored message preserved.
  - Test proves `idempotency_conflict` remains visible while raw fake result remains hidden.

## Residual Risk

- Full-repository test suite was not run in this validation pass; the affected S1 and tools matrix, pyright, source scans, diff check, and coverage workaround passed.
- P3-E S2 and S3 remain unimplemented and are not closed by this S1 validation.

