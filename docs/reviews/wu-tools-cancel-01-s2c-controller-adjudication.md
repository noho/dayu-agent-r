# WU-TOOLS-CANCEL-01 S2C Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Slice: S2C `Fins read process-backed`
- Gate: controller adjudication after implementation review / fix / re-review
- Branch: `phase/wu-tools-cancel-01`

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-cancel-01-s2c-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2c-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2c-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2c-rereview-ds.md`

## Decision

S2C is accepted.

Nine non-WAITING Fins read tools now declare `ProcessBackedToolExecutionCapability` through `ToolDefinition.execution`. The production Host ToolRuntime path uses the S2A2 declaration-backed factory to construct process-backed capsules. The Fins process target only carries serializable values: workspace root locator, tool name, JSON argument copy, `FinsToolLimits`, and timeout scalar. It does not capture `FinsReadRuntime`, repositories, processor cache, provider lock, `CancellationToken`, session/run objects, or Host internals.

The child process reconstructs `DefaultFinsRuntime.create(workspace_root=Path(...))`, obtains a read runtime through the normal Fins assembly root, and continues to access documents through `dayu.fins.storage`.

## Review Adjudication

- AgentMiMo initial review: `PASS`; no blocking finding.
- AgentDS initial review: `PASS` with three low-severity findings.
- Controller accepted all three DS findings for current-slice cleanup because they were cheap and improved S2C evidence quality:
  - add FinancialDataProcessor spawned-child process-backed coverage;
  - remove misleading cancellation helper naming / parameter;
  - preserve recovery hint on process target infrastructure failure.
- Fix completed. AgentCodex started the fix but stalled before artifact completion; controller interrupted the stuck pane, completed the missing test fixture helper, and validated the result. This is recorded in `docs/reviews/wu-tools-cancel-01-s2c-fix-codex.md`.
- AgentMiMo re-review: `PASS`.
- AgentDS re-review: `PASS`.

## Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q
source .venv/bin/activate && pyright
git diff --check
```

Observed:

- Fins provider + ingestion tests: 87 passed, 3 third-party `edgar` deprecation warnings.
- Host ToolRuntime tests: 55 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

Earlier focused fix validation also passed:

- `tests/fins/test_fins_storage_provider.py`: 31 passed, 3 third-party `edgar` deprecation warnings.
- `test_fins_read_financial_statement_runs_in_spawned_child`: 1 passed, 3 third-party `edgar` deprecation warnings.

## Residual Risk

- `query_xbrl_facts` is not independently exercised in a spawned child with a real XBRL instance fixture. Current S2C coverage exercises the distinct `FinancialDataProcessor` process-boundary route via `get_financial_statement`, and table / processor / fast paths are separately covered. This is accepted as a low residual risk and not a blocker for S2C.
- Concurrent multi-process Fins read contention is not covered by a dedicated stress test. Current S2C scope requires per-tool interrupt boundary migration and late-result rejection; broader filesystem contention stress remains outside this slice.

## Next Entry Point

Proceed to WU-TOOLS-CANCEL-01 S2D `Web sync process-backed or abort-capable async_direct`.

S2D must move Web search / fetch synchronous requests execution away from uninterruptible same-process `asyncio.to_thread(...)` into `process_backed`, or replace it with request-abort-capable `async_direct` backed by explicit response / client / stream close verification. Playwright must retain process-backed / fail-closed semantics and must not fall back to an uninterruptible same-process path.
