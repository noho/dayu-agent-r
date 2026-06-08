# WU-TOOLS-01-F01 Slice S4 Code Review Controller Adjudication

## Gate Metadata

- Gate: code review adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S4 - Download / Preprocess Awaiting Tool Providers`.
- Branch: `host-wu-tools-01-f01`.
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s4-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-s4-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s4-code-review-ds.md`
  - `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`

## Summary

Both reviewers returned `pass-with-findings`. Slice S4 meets the plan objective: read, download and preprocess providers are split; download/preprocess tool callables return `ToolAwaitingOutcome` with `EXTERNAL_JOB`; no ToolDiscovery, Host, Engine or Service contract shape changed.

Three findings are accepted for the Slice S4 fix gate. No finding is rejected.

## Accepted Findings

### F01-S4-001 - accepted

- Source: AgentMiMo and AgentDS.
- Severity: medium.
- Files:
  - `dayu/fins/tools/download_tools.py`
  - `dayu/fins/tools/preprocess_tools.py`
- Finding: the two tool modules duplicate helper logic for awaiting outcome construction, failed outcome construction and JSON argument parsing.
- Controller judgment: accepted. This violates the repository rule that repeated logic must be extracted. The fix is still within S4's tool-provider boundary because it only consolidates S4 tool adapter helpers.
- Required fix:
  - Extract the shared helper functions into a private module under `dayu/fins/tools/`.
  - Keep tool-specific request construction in each concrete tool module.
  - Preserve all current tool names, schemas and outcomes.

### F01-S4-002 - accepted

- Source: AgentMiMo.
- Severity: low.
- Files:
  - `dayu/fins/tools/download_tools.py`
  - `dayu/fins/tools/preprocess_tools.py`
  - `tests/fins/test_fins_ingestion_tools.py`
- Finding: OSError and unexpected exception paths in tool callables are not covered by tests.
- Controller judgment: accepted. These are pre-awaiting startup failures and are part of the S4 tool-adapter contract. A small focused test prevents error-code drift.
- Required fix:
  - Add focused tests for `OSError` and unexpected exception from `runtime.start_download` / `runtime.start_preprocess`.
  - Assert `ToolFailedOutcome` and the appropriate start-failed error code.

### F01-S4-003 - accepted

- Source: AgentDS.
- Severity: low.
- File: `tests/fins/test_fins_ingestion_tools.py`.
- Finding: tests that call awaiting tools do not wait for the daemon background job to reach terminal state before test teardown.
- Controller judgment: accepted. The tool itself must not block, but the test can wait after asserting awaiting behavior. This closes a flaky-test risk without changing runtime semantics.
- Required fix:
  - After asserting `ToolAwaitingOutcome`, wait for the returned job id to reach terminal state through the shared workspace runtime.
  - Keep production callable behavior non-blocking.

## Rejected Findings

None.

## Deferred Findings

None.

## Required Validation For Fix Gate

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py`
- `source .venv/bin/activate && pyright`

## Next Gate

Proceed to Slice S4 fix gate with AgentCodex. Do not commit, push, open PR, or enter re-review until the fix artifact is available.
