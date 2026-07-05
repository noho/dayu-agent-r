# WU-TOOLS-CANCEL-01 S2A2 Controller Adjudication

## Verdict

ACCEPTED.

S2A2 `Host factory wiring` 已通过 implementation、code review、fix 与 re-review gate。当前 controller 裁决 S2A2 进入 accepted slice commit，下一步为 S2B `Doc process-backed` implementation gate。

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: S2A2 `Host factory wiring`
- Implementation artifact: `docs/reviews/wu-tools-cancel-01-s2a2-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2a2-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2a2-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2a2-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-s2a2-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2a2-rereview-ds.md`

## Accepted Findings

### F01 capsule build failure executor path

Decision: accepted and closed.

AgentCodex added `test_capsule_build_failure_bypasses_accept_barrier`, which injects a capsule factory that raises during `create_capsule`. The test verifies the executor returns `ToolFailedOutcome` with `tool_capsule_build_failed`, does not call the business callable, and does not enter the accept barrier.

### F02 inaccurate docstring exception type

Decision: accepted and closed.

`DeclaredToolExecutionCapsuleFactory.create_capsule` now documents `ValueError` for missing tool declarations, `TypeError` for unknown execution capability, and pass-through exceptions from process target factory construction.

### F03 async_direct / thread_backed declaration-backed integration tests

Decision: accepted and closed.

AgentCodex added default factory path tests for `async_direct` and `thread_backed`. Both tests run with `execution_capsule_factory=None`, so `DefaultToolRuntimeFactory` must create `DeclaredToolExecutionCapsuleFactory` from the effective bundle.

## Deferred / Non-Blocking Items

- MiMo original finding 3, process envelope fail-closed executor-level wiring test, is deferred as non-blocking. Capsule-level fail-closed behavior is covered, and the process-backed success path is covered through declaration-backed factory wiring. It remains a future test-hardening opportunity, not a current S2A2 correctness blocker.
- `DefaultToolExecutionCapsuleFactory` remains exported but no longer production default. This is a residual cleanup consideration after typed capability rollout; it is not a blocker for S2A2.
- `thread_backed` remains explicitly non-proof for non-cooperative production closeout. S2B/S2C/S2D must not use it as issue-87 closeout evidence for blocking I/O.

## Controller Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_package_exports.py -q`
  - `75 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed with no output

## Boundary Check

- No Engine public request, event, runner, or tool schema contract change.
- No durable schema or migration change.
- No Host public cancel API change.
- No `dayu.runtime.interruptible_process` return type change.
- No Host branch by concrete business tool name.
- No Doc / Fins / Web process-backed migration in this slice.

## Next Gate

Proceed to S2B `Doc process-backed` implementation gate. The next slice must migrate Doc production blocking tool execution to `process_backed` through typed `ToolDefinition.execution`, using serializable process targets and preserving path containment, output shape, truncation, and Host-governed cancel / timeout ownership.
