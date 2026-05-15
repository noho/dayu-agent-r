# PR 55 Fix: Accept Retry Exhausted Handling

## Root Cause

`ToolRuntimeExecutor._accept_with_retry` treated accept barrier timeout as an in-band `ToolFactAcceptTimedOut` result, but its exception branch only caught built-in `TimeoutError`. The default durable accept path can fail with `HostTransactionRetryExhaustedError` when SQLite busy / locked retry is exhausted. That exception is not a `TimeoutError`, so it could escape tool execution instead of being governed as a bounded accept timeout.

## Fix

- `dayu/host/tool_runtime.py` now catches `HostTransactionRetryExhaustedError` together with `TimeoutError` in `_accept_with_retry`.
- The catch remains intentionally narrow. It does not catch broad `HostDurableError`, so durable schema, payload, foreign-key, missing-event, or implementation defects still surface instead of being hidden as ordinary tool timeouts.
- `tests/host/test_toolruntime_executor.py` adds `_RetryExhaustedAcceptPort` and `test_accept_retry_exhausted_returns_governed_timeout`, proving durable retry exhaustion is retried according to `ToolAcceptRetryPolicy`, then returned as governed `tool_accept_timeout` without leaking the raw tool result.

## Validation

- `pytest tests/host/test_toolruntime_executor.py -q`: 8 passed.
- `python -m pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.

## Residual Risks

- This fix does not implement `ToolFactRejectedAck.retryable` semantics. Current production rejected acks are non-retryable; retryable reject handling remains ToolRuntime hardening work.
- This fix does not address concurrent `fetch_more` cursor check-and-set, which remains deferred to concurrency hardening before introducing concurrent tool execution.
