# WU-TOOLS-01-F02 Slice 2 Fix - Codex

## Artifact Path

- `docs/reviews/wu-tools-01-f02-slice2-fix-codex.md`

## Scope

- Work unit: `WU-TOOLS-01-F02`
- Gate: fix
- Slice: Slice 2 Current-Contract Diagnostic Script
- Fixed finding: Controller-accepted classifier divergence in `_classify_diagnostic_bucket`.

## Changed Files

- `utils/diagnose_web_access.py`
- `docs/reviews/wu-tools-01-f02-slice2-implementation-codex.md`
- `docs/reviews/wu-tools-01-f02-slice2-fix-codex.md`

## Fix Summary

- Updated `_classify_diagnostic_bucket` to follow the accepted plan decision tree.
- Added `requests_only_sampled` for the case where requests is the only sampled successful path and fetch / Playwright were not sampled.
- Removed the non-plan ordinary bucket `no_path_sampled`; zero sampled paths now fall back to `mixed` unless the row is a batch child crash.
- Preserved `child_process_error` as the batch child crash classification.
- Made `all_success` take precedence over `playwright_challenge_detected` when all three paths were sampled and successful.
- Made `fetch_outperforms_requests` cover fetch success with requests sampled failure and Playwright skipped or sampled failure.
- Restricted `fetch_only_success` to the narrower case where fetch succeeds while requests and Playwright were both sampled and failed.

## Deferred / Not Changed

- Did not change `--playwright-channel ""` child-process propagation.
- Did not synthesize `next_action`, `http_status`, or `diagnostics` for current `ToolResultFailure`.
- Did not change runtime provider spec imports.
- Did not add or run Slice 3 tests.
- Did not review, commit, push, or open a PR.

## Validation

- Passed: `source .venv/bin/activate && python -m py_compile utils/diagnose_web_access.py`
- Passed: `source .venv/bin/activate && python -m pyright utils/diagnose_web_access.py`
- Passed: `bash -n utils/diag_web.sh utils/diag_web_batch.sh`
- Passed: `git diff --check`
- Passed: supplemental `git diff --check --no-index /dev/null docs/reviews/wu-tools-01-f02-slice2-fix-codex.md` for the new fix artifact.

## Blocking Open Questions

- None.

## Residual Risks

- Classifier behavior is fixed in code, but deterministic pytest coverage is intentionally deferred to Slice 3.
- Live site behavior, Playwright browser availability, and storage-state reuse remain environment dependent because this gate did not run live diagnostics.
