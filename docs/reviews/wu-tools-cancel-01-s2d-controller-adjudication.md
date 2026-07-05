# WU-TOOLS-CANCEL-01 S2D Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Slice: S2D `Web sync process-backed or abort-capable async_direct`
- Gate: controller adjudication after implementation review
- Branch: `phase/wu-tools-cancel-01`

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-cancel-01-s2d-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2d-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2d-code-review-20260704-224009.md`
  - `docs/reviews/wu-tools-cancel-01-s2d-code-review-ds.md`

`docs/reviews/wu-tools-cancel-01-s2d-code-review-mimo.md` is a stable-path note because AgentMiMo wrote the full artifact with a timestamped filename.

## Decision

S2D is accepted.

`search_web` and `fetch_web_page` now declare `ProcessBackedToolExecutionCapability` through `ToolDefinition.execution`, so production Host ToolRuntime dispatch uses the S2A2 declaration-backed process capsule instead of same-process `asyncio.to_thread(...)` execution. The direct callable path remains available for direct tests and non-production fallback behavior only.

The Web process target and factory only carry serializable state: tool name, arguments JSON copy, `WebToolsConfig`, and timeout scalar. They do not capture `requests.Session`, provider locks, Host cancellation tokens, Host / Run / Session objects, or Playwright runtime / browser objects. The child process rebuilds Web runtime state and passes timeout budget into HTTP / browser stages.

## Review Adjudication

- AgentMiMo review: `PASS`; no substantive finding.
- AgentDS review: `PASS`; two low-severity advisory findings:
  - `_WebProcessCancellationToken` relies on structural `CancellationToken` protocol conformance;
  - process envelope constants are locally mirrored rather than single-sourced.
- Controller accepts both advisories as non-blocking. They do not affect S2D correctness, do not require a current fix, and are better addressed in S2E aggregate validation or future contract cleanup if needed.

## Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q
source .venv/bin/activate && pyright
git diff --check
```

Observed:

- Web provider tests: 31 passed.
- Host ToolRuntime tests: 55 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Residual Risk

- Process-backed Web tools have per-call process cold-start cost. This is accepted for #87 closeout because interruptibility and late-result isolation are more important than optimizing Web call latency in S2D.
- `query` / fetch process envelopes fold hint text into `message` because the Host process envelope has no separate hint field. This follows the current process-backed envelope contract and avoids runtime / Host contract churn in S2D.
- Playwright fallback under Web process-backed can involve nested child processes. Current S2D preserves existing fail-closed worker behavior; aggregate validation should include Playwright cancellation / fail-closed recheck where feasible.

## Next Entry Point

Proceed to WU-TOOLS-CANCEL-01 S2E `aggregate validation`.

S2E must run the combined Host / Doc / Fins / Web focused matrix, confirm process-backed late-result behavior across tool families, reconcile residual risks, and update final S2 implementation status before aggregate deepreview / PR gates.
