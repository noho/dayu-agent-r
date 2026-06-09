# WU-TOOLS-01-F01-03 Slice 5 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 5: Upload Awaiting Tool, Provider, Wait Adapter, And Service Assembly`
- Reviewed implementation artifact: `docs/reviews/wu-tools-01-f01-03-slice5-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-slice5-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice5-code-review-ds.md`

## Verdict

`fix-not-required`

AgentMiMo verdict is `pass`. AgentDS verdict is `pass-with-findings` with one medium non-blocking finding. Controller rejects the single DS finding after direct validation; no implementation fix is required for Slice 5.

## Findings Adjudication

### DS F1: restore terminal wait in download awaiting tool test

- DS severity: medium non-blocking
- Controller decision: rejected

Evidence:

- The Slice 5 tool test `test_download_tool_returns_external_job_awaiting_outcome` verifies the tool start boundary: `ToolAwaitingOutcome`, `EXTERNAL_JOB`, durable job creation, operation kind and normalized ticker.
- Restoring `_wait_ingestion_job_terminal(runtime, outcome.await_spec.resume_token)` makes the target suite fail:
  - Command: `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result after temporary restoration: `1 failed, 72 passed, 3 warnings`
  - Failure: `test_download_tool_returns_external_job_awaiting_outcome` timed out waiting for the production download job to become terminal within `_JOB_WAIT_TIMEOUT_SECONDS = 5.0`.
- The root cause is test-boundary mismatch, not a product defect: production download is a long transaction, and this tool/provider test should not require production download completion. Download terminal lifecycle is covered by ingestion runtime and pipeline tests with controlled adapters.

Controller action:

- Kept the terminal wait removed from the download tool start test.
- Added an inline test comment clarifying that production download is a long transaction and this test only validates the start boundary and durable job creation.

## Accepted Follow-Up

None.

## Required Fixes

None.

## Controller Validation

Before review dispatch, Controller ran:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `73 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- Targeted weak typing scan over touched files
  - Result: no matches
- Targeted reverse dependency scan for Fins upload tool/provider/helper files
  - Result: no matches
- Targeted upload schema internal-governance scan
  - Result: no matches

After adjudicating DS F1, Controller will rerun the Slice 5 target validation before accepting the slice.
