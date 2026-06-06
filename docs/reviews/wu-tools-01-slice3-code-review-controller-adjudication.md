# WU-TOOLS-01 Slice S3 Code Review Controller Adjudication

Gate: code review adjudication
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Controller: AgentController
Status: fix required

## Inputs

- AgentMiMo review: `docs/reviews/wu-tools-01-slice3-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-tools-01-slice3-code-review-ds.md`
- Controller validation:
  - `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents` -> 19 passed
  - `source .venv/bin/activate && pyright` -> 0 errors
  - `git diff --check` -> clean

## Accepted Findings

### A1. OLD ToolRegistry / truncation owner wording must be removed from migrated Doc tools text

Accepted from AgentMiMo and AgentDS.

`dayu/tools/doc_tools.py` still contains module and function docstrings that say path safety or truncation is handled by OLD `ToolRegistry`. This conflicts with the accepted S3 boundary: Doc tool function bodies do not own path safety; provider/adapter validates and projects paths, while current Host ToolRuntime owns truncation/fetch_more.

Required fix:

- Replace stale module docstring and function docstrings with current wording.
- Remove the OLD `ToolRegistry()` example.
- Do not add internal Host/Engine governance terms to LLM-facing schema text.
- Tool descriptions may mention that paths must be accessible/configured, but must not imply Doc functions enforce security themselves.

### A2. `register_doc_tools(... allowed_paths=...)` must not register path safety through the collector

Accepted from AgentMiMo.

The provider correctly calls `register_doc_tools(..., allowed_paths=None, allow_file_write=False, allowed_write_paths=None, timeout_budget=None)`, but the migrated registration function still calls `registry.register_allowed_paths(allowed_paths)` if a caller passes paths. That leaves an OLD safety-owner code path in the Doc tools module.

Required fix:

- Keep the `register_doc_tools` signature for migration compatibility.
- Do not call `registry.register_allowed_paths(...)`.
- Treat `allowed_paths`, `allow_file_write`, `allowed_write_paths`, and `timeout_budget` as ignored legacy registration parameters in this migrated module.
- Keep or adjust the collector test so it proves collector-recorded paths are not trusted by execution.

### A3. `list_files -> read_file/get_file_sections/read_file_section` chaining must not be broken by relative paths

Accepted from AgentDS, severity raised to fix-required for S3.

`list_files` returns `files[].path` as a relative path, and the LLM-facing descriptions instruct models to pass that value to other Doc tools. The current adapter resolves relative path input against process CWD, not against the provider allowed root or the listing directory, so the advertised workflow can fail even when all paths are under the allowed root.

This is exactly the kind of input/response projection issue the user asked the Controller to adjudicate for WU-TOOLS-01. It should be fixed in S3 instead of deferred.

Required fix:

- Prefer an adapter/provider response projection that preserves the migrated OLD business function body and projects `list_files` returned file paths into paths accepted by the current adapter.
- If a narrow OLD body change is the only simple maintainable fix, document why it is a response-projection adaptation, keep it limited to path values, and avoid rewriting business search/listing logic.
- Add an integration-style test where `list_files` output is passed directly to `read_file` or `get_file_sections` and succeeds under a provider allowed root that is not the process CWD.
- Consider `search_files` returned file references too if its LLM-facing schema asks models to reuse them.

## Deferred Findings

- OLD weak typing in migrated `doc_tools.py` (`Any`, `Dict`, `List`, `Optional`) is deferred as a migration residual. Do not rewrite OLD tool function signatures or bodies only to satisfy style in S3.
- OLD search snippet quality, encoding fallback differences, dead stores, and OSError fallback behavior are OLD behavior residuals and not S3 blockers.
- Broader edge tests such as empty directories, invalid refs, no search results, HTML fixture coverage, and provider concurrency can be deferred unless they become necessary for an accepted fix.
- A dedicated `dayu.tools` import-boundary test is useful, but S3 already includes direct no-OLD-runtime assertions. Defer unless the fix changes package dependencies.

## Rejected Or Downgraded Findings

- The absence of detailed path-safety explanation in every tool description is not itself a bug. LLM-facing text should stay task-focused and avoid internal mechanism burden. Only incorrect or workflow-breaking text must be fixed.

## Required Fix Gate

Dispatch AgentCodex for a narrow fix. After fix, run:

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Then dispatch AgentMiMo and AgentDS re-review on the accepted findings only.
