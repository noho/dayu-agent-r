# WU-TOOLS-01-F01-02-R3 Slice 1 Fix

## Scope

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 1, Doc Native Tools
- Gate: fix after code review adjudication
- Implemented only accepted findings `S1-CR-01` through `S1-CR-04`.
- Did not modify Web, Fins, Host, Engine, Service, ToolRuntime, or legacy adapter deletion scope.

## Fixes

### S1-CR-01 Path Validation Order

- `_project_doc_paths` now checks allowed-root containment before filesystem existence.
- A path outside `allowed_roots` returns `permission_denied` even when it does not exist.
- Added regression coverage for a nonexistent path under a blocked root returning `permission_denied`, not `file_not_found`.

### S1-CR-02 Provider Lock Serialization Test

- Added a direct concurrent test using two different Doc callables from the same provider: `list_files` and `read_file`.
- The test replaces `asyncio.to_thread` with a deterministic async probe and verifies the second callable does not enter the synchronous business body while the first remains inside it.
- No sleep-based timing assertion is used; the only event-loop yield is used to let the second coroutine attempt progress while the first holds the provider lock.

### S1-CR-03 Line Scan Cancellation

- `_search_via_line_scan` now requires a non-optional `CancellationToken`.
- The line scan loop now observes bounded cooperative cancellation checkpoints.
- Added tests that:
  - verify `_search_via_line_scan` raises the Doc-local cancellation signal from inside the loop checkpoint path;
  - verify the public `search_files` callable projects that cancellation to `ToolCancelledOutcome(reason="host_cancelled")`.

### S1-CR-04 Markdown Section / Line Count Cancellation

- Added bounded cooperative cancellation checkpoints to:
  - `_extract_markdown_sections`;
  - `_count_file_lines`;
  - fallback paths that call `_count_file_lines`;
  - processor section paths that call `_count_file_lines`.
- No timeout policy, physical cancellation, Host, Engine, or ToolRuntime behavior was introduced.
- Added narrow helper tests for Markdown section extraction and line count cancellation.

## README Decision

- `tests/README.md` was checked because `tests/tools/test_doc_tools_provider.py` changed.
- No README update was made: this fix adds coverage inside the existing `tests/tools` Doc provider layer and does not add a new test layer, command, fixture class, or maintenance rule.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
  - Passed: 28 tests.
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -k doc`
  - Passed: 1 selected, 7 deselected.
  - Notes: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && pyright`
  - Passed: 0 errors, 0 warnings.
  - Notes: pyright reported an available version update only.
- `git diff --check`
  - Passed.

## Residual Risk

- Doc helper cancellation remains cooperative by design; already-running file reads are not physically interrupted.
- Web and Fins native migration, legacy adapter deletion, and long-running processor timeout policy remain out of this Slice 1 fix scope.
