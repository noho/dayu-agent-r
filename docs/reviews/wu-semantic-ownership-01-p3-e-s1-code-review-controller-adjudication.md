# WU-SEMANTIC-OWNERSHIP-01 P3-E S1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S1 - ToolResult invariant and ToolRuntime LLM-facing hint cleanup`
- Reviewed implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s1-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s1-code-review-ds.md`

## Controller Decision

The S1 implementation satisfies the core accepted plan target: `ToolResultSuccess` and `ToolResultFailure` now enforce their runtime `ok` discriminants, and ToolRuntime synthetic governance failures no longer project internal governance reason codes through LLM-facing `hint`.

The two review passes found current-scope issues caused by that semantic migration. They are accepted as fix-gate items because they either break full-repository tests or weaken the proof that moved diagnostics still remain observable at the proper owner boundary.

## Merged Findings

### P3-E-S1-CR-F01 - Accepted - Update stale `tests/tools/` cancellation hint assertions

- Source findings: AgentDS `S1-F1`
- Severity: Medium
- Owner boundary: ToolRuntime owns synthetic cancellation policy decisions and failure projection; `tests/tools/` are downstream integration tests and must assert the new public contract rather than the retired LLM-facing governance hint.
- Required fix:
  - Update stale `tool_runtime_cancelled` hint assertions in:
    - `tests/tools/test_doc_tools_provider.py`
    - `tests/tools/web/test_web_tools_provider.py`
  - Keep assertions that the Tool Trace / policy diagnostic reason remains `tool_runtime_cancelled`.
- Acceptance signal:
  - `pytest tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q` passes.

### P3-E-S1-CR-F02 - Accepted - Remove dead truncation `reason_code` contract

- Source findings: AgentMiMo finding 1, AgentDS `S1-F2`
- Severity: Medium
- Owner boundary: ToolRuntime is the owner of fetch-more truncation failure projection. S1 intentionally removed truncation subtype leakage from LLM-facing `hint`; keeping a discarded `reason_code` parameter and reason constants creates a false source of truth.
- Required fix:
  - Remove the unused `reason_code` parameter from `_truncation_failure`.
  - Update all `_truncation_failure` call sites.
  - Delete truncation reason constants that become unused.
  - Keep the existing structured `error == "truncation_error"` contract unless current code proves a downstream owner requires a more specific structured code.
- Acceptance signal:
  - Source scan shows no dead `_TRUNCATION_*_REASON` constants used only as discarded arguments.
  - Existing truncation behavior remains distinguishable through human-readable `message` at the failure projection boundary.

### P3-E-S1-CR-F03 - Accepted - Strengthen truncation failure tests after hint removal

- Source findings: AgentMiMo finding 2, AgentDS `S1-F3`
- Severity: Low
- Owner boundary: ToolRuntime owns truncation failure message/error projection; tests must prove that removing `hint` did not erase failure semantics.
- Required fix:
  - In `tests/host/test_toolruntime_truncation_fetch_more.py`, keep `hint is None`.
  - Add assertions for `error == "truncation_error"`.
  - Add scenario-specific `message` assertions for cursor missing, token mismatch, cursor already used, invalid request, TTL expiry, scope mismatch, digest mismatch, and unsupported target paths covered by the file.
- Acceptance signal:
  - Truncation tests fail if all truncation messages are collapsed or emptied.

### P3-E-S1-CR-F04 - Accepted - Prove accept rejection reason remains outside `hint`

- Source findings: AgentMiMo finding 3
- Severity: Low
- Owner boundary: the accept barrier owns rejection diagnostics. S1 removed the retired `accept_rejected:` hint protocol, but the rejection reason must remain visible through owner-authored message or diagnostics.
- Required fix:
  - Strengthen `test_accept_rejected_does_not_expose_raw_fake_result` or an adjacent accept rejection test to prove the idempotency conflict reason remains visible in `message` or Tool Trace diagnostics.
  - Keep `hint is None` and keep the negative assertion against raw fake result leakage.
- Acceptance signal:
  - The test fails if accept rejection drops both message reason and diagnostics reason.

## Required Validation

Run from the repository root after activating `.venv`:

```bash
pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Also run source scans proving the removed hidden hint protocol and truncation dead constants do not remain in production paths.

## Residual Risk

- This adjudication does not close P3-E S1. The accepted fixes require implementation, controller validation, and independent re-review.
- P3-E S2 and S3 remain untouched and must proceed after S1 is closed.

