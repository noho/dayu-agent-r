# WU-TOOLS-01 Slice S3 Fix

Gate: fix
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Agent: AgentCodex
Status: fix complete; stopped before re-review / commit / push / PR

## Scope

Only Controller-accepted findings from:

- `docs/reviews/wu-tools-01-slice3-code-review-controller-adjudication.md`
- `docs/reviews/wu-tools-01-slice3-code-review-mimo.md`
- `docs/reviews/wu-tools-01-slice3-code-review-ds.md`

Changed files:

- `dayu/tools/doc_tools.py`
- `dayu/tools/_legacy_adapter/definition_adapter.py`
- `tests/tools/test_doc_tools_provider.py`
- `docs/reviews/wu-tools-01-slice3-fix-codex.md`

## Fix Summary

- Cleaned migrated Doc tools wording so OLD `ToolRegistry` and OLD truncation-owner terms no longer appear in `dayu/tools/doc_tools.py`.
- Kept `register_doc_tools(...)` signature but made legacy registration parameters ignored by the migrated module.
- Added response projection for reusable Doc tool paths: `list_files.files[].path` and `search_files.matches[].file` now return absolute paths derived from the returned directory, so follow-up read tools can consume them directly under the current path policy.
- Added an integration-style test that exercises `list_files -> read_file`, `list_files -> get_file_sections`, `search_files -> read_file`, and `search_files -> read_file_section` when provider allowed root differs from process CWD.

## A1. OLD Terminology Cleanup

Status: fixed.

Changes:

- Rewrote the module docstring in `dayu/tools/doc_tools.py` to describe the current migrated Doc tool boundary.
- Rewrote `register_doc_tools(...)`, `get_file_sections(...)`, `read_file(...)`, and `read_file_section(...)` docstrings that previously named OLD `ToolRegistry` as path or truncation owner.
- Removed the OLD `ToolRegistry()` example from `register_doc_tools(...)`.
- Updated LLM-facing tool descriptions and parameter descriptions to say paths must be accessible/configuration-allowed and existing, without describing Host/Engine governance or claiming Doc function bodies enforce safety.

## A2. Legacy Registration Params

Status: fixed.

Changes:

- Removed the `registry.register_allowed_paths(...)` call from `register_doc_tools(...)`.
- Preserved the function signature.
- Explicitly ignored `allowed_paths`, `allow_file_write`, `allowed_write_paths`, and `timeout_budget` inside the migrated registration function.
- Strengthened `test_collector_allowed_paths_are_not_trusted` so it passes these legacy parameters and asserts the collector did not record an allowed-path registration; execution without an explicit path policy still fails closed.

## A3. Path Chaining Projection

Status: fixed.

Root cause:

- OLD business functions returned relative path values from `list_files.files[].path` and `search_files.matches[].file`.
- Current path input projection resolves tool-call path arguments before executing the migrated function body. A relative value copied from a prior tool result was therefore interpreted relative to process CWD, not the provider allowed root or the listed directory.
- This broke the LLM-facing workflow that tells the model to pass returned path fields into follow-up read tools.

Fix:

- Added response projection in `dayu/tools/_legacy_adapter/definition_adapter.py`.
- `list_files.files[].path` is projected from a directory-relative value to an absolute path based on the returned `directory`.
- `search_files.matches[].file` is projected the same way.
- Follow-up calls still pass through current path validation before entering migrated business functions.

Migration principle note:

- This is a response-projection adaptation, not a rewrite of OLD listing/search business logic.
- The OLD function bodies still decide which files are listed or matched.
- The fix only changes reusable path values at the adapter output boundary so they match the current input projection contract.

## Docs Decision

No README change was required by this fix beyond already-present Slice S3 test documentation. The functional contract is covered by `tests/tools/test_doc_tools_provider.py`; user-facing configuration behavior did not change.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents` -> 20 passed.
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> clean.

## Residual Risks

- OLD weak typing in migrated `dayu/tools/doc_tools.py` remains deferred with owner: later approved cleanup / migration work unit.
- OLD search snippet quality, encoding fallback differences, dead store, and OSError fallback behavior remain deferred with owner: later approved cleanup / migration work unit.
- OLD ToolRegistry / OLD TruncationManager / OLD fetch_more migration remains explicitly out of scope for this fix gate.
- Multiple allowed roots with identical relative file names are not ambiguous in this fix because response projection uses the actual returned `directory`, not root guessing.

## Completion Status

Accepted findings A1, A2, and A3 were addressed in the narrow fix scope. No re-review, commit, push, or PR action was performed.
