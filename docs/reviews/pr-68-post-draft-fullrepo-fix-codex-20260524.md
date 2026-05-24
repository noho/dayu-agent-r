# PR 68 Post-Draft Full-Repo Fix Codex 20260524

## Gate

- Gate: P12.6 post-draft full-repo fix gate for PR 68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Assigned findings: A1-A9 from `docs/reviews/pr-68-post-draft-fullrepo-review-controller-adjudication-20260524.md`
- Stop condition: write fix artifact and stop; no commit, push, PR state change, merge, reviewer request, or later-gate transition.

## Changed Files

- Production:
  - `dayu/host/__init__.py`
  - `dayu/host/tooling.py`
  - `dayu/host/tool_runtime.py`
  - `dayu/host/context_policy.py`
  - `dayu/host/context_governance.py`
  - `dayu/host/compaction_operation.py`
  - `dayu/host/durable/transaction.py`
- Tests:
  - `tests/host/test_memory_repair.py`
  - `tests/host/test_compaction_contract.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_tool_runtime_schema_projection.py`
  - `tests/runtime/test_tool_truncation.py`
  - `tests/host/test_durable_transaction.py`
  - Host source-ref import cleanup in affected Host tests and `tests/host/public_smoke_support.py`
- README:
  - `dayu/host/README.md`
  - `tests/README.md`
- Artifact:
  - `docs/reviews/pr-68-post-draft-fullrepo-fix-codex-20260524.md`

## Per-Finding Resolution

### A1-已修复-memory_repair.py has no direct tests

- Added `tests/host/test_memory_repair.py`.
- Covered rebuild reset plus empty batch termination, catch-up cursor/batch accumulation and short-batch termination, failure counting and stop-on-failure, and `ConversationMemoryProjectionCatchupPort` delegation.

### A2-已修复-Remove ToolBundleSourceKind / ToolBundleSourceRef Host compatibility re-export

- Removed source ref re-export from `dayu.host.tooling.__all__` and `dayu.host.__all__`.
- Updated Host internals and tests to import `ToolBundleSourceKind` / `ToolBundleSourceRef` from `dayu.contracts.tool_source`.
- Updated Host package export test so source ref ownership stays in contracts.

### A3-已修复-Compaction semantic repair disabled by default

- Changed `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` from `1` to `2`, so the default allows the first proposal plus one semantic repair attempt.
- Existing context policy tests assert the default through the constant.

### A4-已修复-Open-question quality check rejects legitimate empty / clear outcomes

- Changed quality check to distinguish whether the original compact request contained open questions / working assumptions.
- If none existed, empty/CLEAR outcome is accepted.
- If originals existed, summary retention, non-empty REPLACE, or evidence-supported CLEAR is accepted; MISSING remains rejected.
- Added focused tests for no-original CLEAR, original MISSING rejection, and original evidence-supported CLEAR.

### A5-已修复-Multi-pass compaction merge overstates preserved refs

- Changed multi-pass merge to union `preserved_canonical_evidence_refs` and `preserved_evidence_backed_fact_refs` from accepted pass candidates instead of copying all refs from the root request.
- Added a reactive multi-pass test proving `preserved_evidence_backed_fact_refs` is not overstated when pass candidates do not preserve them.

### A6-已修复-Add preserved-ref subset rejection test

- Added direct quality-check coverage that rejects candidate `preserved_evidence_backed_fact_refs` outside the request subset via `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT`.

### A7-已修复-Add tool_runtime_schema_projection functional tests

- Added direct tests for valid projection/index/digests, duplicate effective tool names, and reserved framework tool-name conflicts.

### A8-已修复-Add runtime/tool_truncation boundary tests

- Added `tests/runtime/test_tool_truncation.py`.
- Covered disabled/no-truncation effective behavior, explicit threshold preservation, missing-limit defaulting, empty policy default rejection, multibyte path preservation, and strict default integer validation.

### A9-已修复-Log after-commit callback secondary errors

- Added logging for secondary after-commit callback failures while preserving the first failure as the raised `HostAfterCommitError.__cause__`.
- Updated durable transaction test to assert later callbacks still run and secondary failure diagnostics are logged.

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_tool_runtime_schema_projection.py tests/runtime/test_tool_truncation.py tests/host/test_durable_transaction.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q`
  - Result: `103 passed in 1.40s`
- `source .venv/bin/activate && python -m pytest tests/host/test_tool_runtime_schema_projection.py -q`
  - Result: `3 passed in 0.70s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && python -m pytest tests/ -x -q`
  - Result: `1653 passed, 1 skipped in 80.71s`
- `git diff --check`
  - Result: passed

## README Updates

- Updated `dayu/host/README.md` because Host public exports changed: source ref types are no longer Host package-root/tooling exports; their truth is `dayu.contracts.tool_source`.
- Updated `tests/README.md` because Host tooling option test responsibility changed accordingly.

## Residual Risks

- No known blocking residual risk for A1-A9.
- Existing controller-owned dirty files were preserved and not reverted: `docs/host/implementation-control.md` and the three post-draft full-repo review/adjudication artifacts.
- This fix gate did not commit or push by instruction.
