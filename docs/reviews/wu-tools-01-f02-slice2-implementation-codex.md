# WU-TOOLS-01-F02 Slice 2 Implementation - Codex

## Artifact Path

- `docs/reviews/wu-tools-01-f02-slice2-implementation-codex.md`

## Changed Files

- `utils/diagnose_web_access.py`
- `docs/reviews/wu-tools-01-f02-slice2-implementation-codex.md`

## OLD Source Scope

- Reference source: `/Users/leo/workspace/dayu-agent/utils/diagnose_web_access.py`
- Reused behavior scope: single URL diagnostics, batch corpus normalization, per-URL JSON, `results.jsonl`, `summary.json`, `summary.md`, comparison buckets, raw requests profile, optional Playwright profile, storage state path handling, bounded network summary.
- Not reused: OLD `ToolRegistry`, OLD truncation/fetch_more path, OLD `dayu.web` UI, OLD engine/web tool imports.

## Adapter Decisions

- `fetch_web_page` is discovered through current `dayu.tools.web.provider.discover_tools(spec)`.
- The script reads `ToolsDiscoveryProviderOutput.definitions`, selects the current `ToolDefinition` named `fetch_web_page`, and invokes `ToolDefinition.callable` with `ToolCallRequest` plus `BatchToolExecutionContext`.
- `_DiagnosticCancellationToken` implements never-cancelled semantics and does not connect to Host cancellation governance.
- Raw requests uses diagnostic-local headers and records `raw_requests_header_source="diagnostic_local"` so the output does not misrepresent this path as production fetch behavior.
- Playwright integration is optional and uses narrow local Protocols around the dynamic package boundary.

## CLI Flags Implemented

- `--url`
- `--url-file`
- `--output`
- `--batch-output-dir`
- `--run-label`
- `--request-timeout`
- `--tool-timeout-budget`
- `--playwright-timeout`
- `--playwright-channel`
- `--headed`
- `--manual-wait-seconds`
- `--pause-before-snapshot`
- `--storage-state-in`
- `--storage-state-out`
- `--storage-state-dir`
- `--skip-playwright`
- `--skip-tool-fetch`
- `--max-network`
- `--fetch-truncate-chars`
- `--allow-private-network-url`

## Validation Results

- Passed: `source .venv/bin/activate && python -m py_compile utils/diagnose_web_access.py`
- Passed: `source .venv/bin/activate && python -m pyright utils/diagnose_web_access.py`
- Passed: `bash -n utils/diag_web.sh utils/diag_web_batch.sh`
- Passed: `git diff --check`
- Passed: supplemental no-index whitespace checks for the two new files, because plain `git diff --check` does not include untracked files.
- Slice 2 fix gate update: `_classify_diagnostic_bucket` now matches the accepted plan decision tree, including `requests_only_sampled`, `fetch_outperforms_requests` with Playwright skipped/failed, `fetch_only_success` only when requests and Playwright are sampled failures, `all_success` before challenge bucket, and `mixed` fallback instead of non-plan `no_path_sampled`.

## Docs Decision

- README not updated. Slice 2 only adds the diagnostic implementation script and its implementation artifact; README update is outside the allowed files for this task.

## Residual Risks / Uncovered Areas

- No live diagnostics were run by design.
- No pytest was added or run because Slice 3 tests are explicitly out of scope.
- Deterministic classifier pytest coverage remains deferred to Slice 3; the accepted classifier finding has been fixed in implementation but not locked by tests in this gate.
- Playwright browser availability, real storage state reuse, and real site behavior remain live-environment dependent.
- Raw requests path intentionally uses local diagnostic headers, not private production fetch helpers.

## Completion Status

- Slice 2 implementation complete. Review, fix, commit, push, PR, live diagnostics, and Slice 3 tests were not performed.
