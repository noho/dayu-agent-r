# WU-LAYER-02 Aggregate Review Controller Adjudication

## Scope

- Work unit: WU-LAYER-02 Shared Runtime Helper Consolidation.
- Aggregate review artifacts:
  - `docs/reviews/wu-layer-02-aggregate-review-mimo-20260602.md`
  - `docs/reviews/wu-layer-02-aggregate-review-ds-20260602.md`
- Design source: `docs/host/design.md`.
- Control source: `docs/host/host-core-followup-implementation-control.md`.

## Review Summary

- MiMo: PASS, no findings.
- DS: PASS overall, but reported F-01 [MEDIUM] that `dayu/host/llm_compaction.py` still owns private secret regex and hand-written redaction/truncation in `_safe_outcome_text`.

## Finding Decisions

### F-01: `llm_compaction.py` private secret regex remains

Decision: accepted as a current WU fix requirement, not deferred.

基于 `docs/host/design.md` 的 runtime 分层目标和第一性原理，`llm_compaction.py._safe_outcome_text` is the same layer-neutral diagnostic text redaction/truncation problem already consolidated in Slice 1-3. Leaving it in Host would keep a known duplicate runtime helper after WU-LAYER-02, which weakens the work unit success signal. The plan missed this file, but aggregate review is the correct gate to catch cross-slice scope gaps before ready-to-open-draft-PR.

## Required Aggregate Fix

Implementation agent must migrate `dayu/host/llm_compaction.py._safe_outcome_text` to `dayu.runtime.diagnostic_text` without changing Host-owned compactor outcome semantics:

- Delete private `_BEARER_SECRET_PATTERN` and `_ASSIGNMENT_SECRET_PATTERN` from `dayu/host/llm_compaction.py`.
- Import and use `redact_sensitive_diagnostic_values`.
- Use `truncate_diagnostic_text` only if the implementation first resolves the old `_safe_outcome_text` truncation behavior difference. The old code returns `text[:_MAX_SAFE_OUTCOME_MESSAGE_CHARS] + _TRUNCATED_SUFFIX` on overflow, so the returned string may exceed `_MAX_SAFE_OUTCOME_MESSAGE_CHARS`; runtime truncation returns a string with total length bounded by `max_chars`. If preserving old visible text is required, the agent must report instead of silently changing it.
- Preserve `_SAFE_ERROR_CODE_PATTERN`, `_safe_error_code`, `_non_final_outcome_message`, `LLMCompactionProposalError`, Engine outcome mapping, timeout behavior and Host compactor state semantics.
- Do not migrate OpenAI provider diagnostic payload, runtime digest, Host durable, tool trace, EventLog or audit semantics.

## Allowed Files For Aggregate Fix

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md`
- README files only if stable documentation is actually triggered under `AGENTS.md`; current expectation is no README update.

## Required Validation

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

## Fix Re-Review Summary

Aggregate fix report:

- `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md`

Aggregate fix re-review artifacts:

- `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-rereview-mimo-20260602.md`
- `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-rereview-ds-20260602.md`

Both re-reviews PASS with zero findings. F-01 is closed:

- `dayu/host/llm_compaction.py` no longer owns private `_BEARER_SECRET_PATTERN` or `_ASSIGNMENT_SECRET_PATTERN`.
- `_safe_outcome_text` now uses `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values` for secret value redaction.
- Host-specific `_safe_outcome_text` truncation shape remains intentionally local and is locked by test: overflow returns the first 240 characters plus `"..."`, preserving existing visible proposal error text.
- `_SAFE_ERROR_CODE_PATTERN`, `_safe_error_code`, `_non_final_outcome_message`, `LLMCompactionProposalError`, Engine outcome mapping and timeout behavior remain Host-owned and unchanged.

## Aggregate Acceptance Decision

After the aggregate fix and re-review, WU-LAYER-02 has no accepted blocking findings. The work unit is ready for controller final validation and accepted aggregate commit.

## Final Controller Validation

Final validation passed:

```bash
source .venv/bin/activate && pytest -q tests/runtime tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py
# 469 passed

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations
```

WU-LAYER-02 is accepted locally after final validation.
