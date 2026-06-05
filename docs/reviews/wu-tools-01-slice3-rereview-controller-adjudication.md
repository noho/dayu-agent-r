# WU-TOOLS-01 Slice S3 Re-Review Controller Adjudication

Gate: re-review adjudication
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Controller: AgentController
Status: accepted for slice commit

## Inputs

- Fix artifact: `docs/reviews/wu-tools-01-slice3-fix-codex.md`
- AgentMiMo re-review: `docs/reviews/wu-tools-01-slice3-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/wu-tools-01-slice3-rereview-ds.md`

## Accepted Fix Results

### A1. OLD owner terminology cleanup

Accepted as fixed.

Both re-reviews confirm `dayu/tools/doc_tools.py` no longer contains stale OLD `ToolRegistry` / `TruncationManager` owner wording. LLM-facing tool text uses current task-level wording around configured accessible paths and does not claim Doc function bodies own path safety.

### A2. Legacy registration path safety removed

Accepted as fixed.

`register_doc_tools(...)` keeps the migrated signature but ignores `allowed_paths`, `allow_file_write`, `allowed_write_paths`, and `timeout_budget`. It no longer calls `registry.register_allowed_paths(...)`. Tests prove collector-recorded paths are not trusted as execution policy.

### A3. Relative path chaining fixed through response projection

Accepted as fixed.

`list_files.files[].path` and `search_files.matches[].file` are projected to absolute paths based on the returned `directory` before current outcome construction. The follow-up tools still run normal input path validation before entering migrated functions. Tests cover `allowed_root != CWD` and direct chaining from list/search output to read/section tools.

## Non-Blocking Residual

The new response projection lives in `_legacy_adapter/definition_adapter.py` and dispatches on Doc tool names. This is acceptable for S3 because:

- It is private adapter code.
- It fixes a real current input/response projection mismatch.
- It avoids rewriting migrated Doc business function bodies.
- Only one provider currently needs this projection.

Residual tracking: if later WU-TOOLS slices add more provider-specific response projection rules, revisit a declaration-level or provider-supplied projector mechanism instead of accumulating hard-coded tool-name branches in the generic adapter.

## Validation

Controller re-ran:

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents` -> 20 passed
- `source .venv/bin/activate && pyright` -> 0 errors
- `git diff --check` -> clean

## Decision

Slice S3 is accepted for final validation and slice commit. No additional fix gate is required.
