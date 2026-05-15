# PR 55 Re-Review: PR55-DS-1 Fix (Accept Retry Exhaustion)

## Scope

- Mode: PR re-review (accepted finding fix)
- PR: 55, https://github.com/noho/dayu-agent-r/pull/55
- Branch: `feat/host-phase-6-toolruntime`
- Base: `main`
- Fix commit: `c79d6b8 fix: handle ToolRuntime accept retry exhaustion`
- Previous artifact: `docs/reviews/pr-55-deepreview-mimo-20260515.md`
- Controller adjudication: `docs/reviews/pr-55-deepreview-controller-adjudication-20260515.md`
- Fix artifact: `docs/reviews/pr-55-fix-accept-retry-exhausted-20260515.md`
- Output file: `docs/reviews/pr-55-re-review-mimo-20260515.md`
- Included scope: PR55-DS-1 fix and regressions introduced by commit `c79d6b8`
- Excluded scope: All other PR55-DS-* findings (deferred by controller), Engine code, Remote transport, business tool implementations
- Parallel review coverage: 无

## Commands And Files Inspected

- `git show c79d6b8 --stat` — 6 files changed, 670 insertions, 1 deletion
- `git diff c79d6b8~1..c79d6b8` — production diff + test + review artifacts
- Production code: `dayu/host/tool_runtime.py` (3 lines changed: 1 import, 1 except clause)
- Test code: `tests/host/test_toolruntime_executor.py` (+51 lines: `_RetryExhaustedAcceptPort` + `test_accept_retry_exhausted_returns_governed_timeout`)
- Documentation: controller adjudication, fix artifact, DS review artifact (gateflow records)
- `source .venv/bin/activate && pytest tests/host -q` — 350 passed (was 349)
- `source .venv/bin/activate && python -m pyright dayu/host tests/host` — 0 errors, 0 warnings, 0 informations
- `git diff --check` — clean

## Required Checks

### 1. `_accept_with_retry` catches `HostTransactionRetryExhaustedError`

**PASS.**

- `_accept_with_retry()` (`tool_runtime.py:2455-2498`) exception clause at line 2471: `except (HostTransactionRetryExhaustedError, TimeoutError):`.
- `HostTransactionRetryExhaustedError` imported from `dayu.host.durable.errors` (`tool_runtime.py:60`).
- On catch, `last_error_code` is set to `_TOOL_RUNTIME_ACCEPT_EXCEPTION_REASON`, and result is `ToolFactAcceptTimedOut(attempt_count=..., last_error_code=..., diagnostic_refs=...)` (lines 2472-2477).
- The retry loop continues to `attempt_count >= self._retry_policy.max_attempts` check (line 2490), then breaks and returns final `ToolFactAcceptTimedOut` with timeout diagnostic ref (lines 2494-2498).

### 2. Does NOT catch broad `HostDurableError`

**PASS.**

- Exception clause is `except (HostTransactionRetryExhaustedError, TimeoutError):` — only these two specific exception types.
- `HostDurableError` is imported (`tool_runtime.py:58`) but NOT caught here.
- Schema, payload, foreign-key, missing-event, or implementation defect durable errors will still propagate as unhandled exceptions — visible as implementation defects, not hidden as ordinary tool timeouts.

### 3. New test proves raw result does not leak and retry count follows policy

**PASS.**

- `_RetryExhaustedAcceptPort` (`test_toolruntime_executor.py:193-218`): fake accept port that always raises `HostTransactionRetryExhaustedError("busy retry exhausted in fake accept port", attempts=...)`.
- `test_accept_retry_exhausted_returns_governed_timeout` (`test_toolruntime_executor.py:300-318`):
  - Constructs executor with `_CountingCallable({"secret": "retry-exhausted-raw"})` and `_RetryExhaustedAcceptPort`.
  - `retry_policy=ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0)` — 2 attempts, no backoff.
  - Asserts `callable_.call_count == 1` — business callable was called once (line 314).
  - Asserts `len(accept_port.candidates) == 2` — exactly 2 retry attempts made (line 315).
  - Asserts `isinstance(record.outcome, ToolFailedOutcome)` — result is governed failure, not exception (line 316).
  - Asserts `record.outcome.result.error == "tool_accept_timeout"` — correct error code (line 317).
  - Asserts `"retry-exhausted-raw" not in record.outcome.result.message` — raw tool result does not leak (line 318).

### 4. No type/test/doc regressions

**PASS.**

- `source .venv/bin/activate && pytest tests/host -q`: 350 passed in 4.38s (was 349 before fix — the +1 is the new `test_accept_retry_exhausted_returns_governed_timeout`).
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.
- No changes to README or other documentation files (fix is internal to ToolRuntime executor).
- No changes to Protocol definitions, `__all__` exports, or public interfaces.

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **PR55-DS-2 deferred**: `fetch_more` single-use cursor check-and-set is not atomic under concurrent calls. Controller deferred as non-blocking; Phase 6 executes batch tool calls serially.
- **PR55-DS-3 through PR55-DS-7 deferred**: all low-severity findings deferred by controller as non-blocking for Phase 6 exit.
- **No CI checks on branch**: `gh pr checks 55` reports no checks configured. Verification done locally.

## Conclusion

**PASS.**

PR55-DS-1 fix 正确实现了 `HostTransactionRetryExhaustedError` 的治理路径。`_accept_with_retry` 在 `tool_runtime.py:2471` 精确捕获 `HostTransactionRetryExhaustedError` 和 `TimeoutError`，不捕获 broad `HostDurableError`。durable transaction retry exhausted 被转换为 bounded `ToolFactAcceptTimedOut`，耗尽重试后返回 governed `tool_accept_timeout`，不泄漏原始工具结果。新测试 `test_accept_retry_exhausted_returns_governed_timeout` 验证了重试次数遵循 `ToolAcceptRetryPolicy.max_attempts`、结果类型为 `ToolFailedOutcome`、error code 为 `tool_accept_timeout`、raw result 不出现在 message 中。无类型、测试或文档回归。
