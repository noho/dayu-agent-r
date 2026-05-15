# PR 55 Deepreview Controller Adjudication

## Scope

- Pull Request: PR 55, `Host Phase 6 ToolRuntime governance`
- Branch: `feat/host-phase-6-toolruntime`
- Review artifacts:
  - `docs/reviews/pr-55-deepreview-mimo-20260515.md`
  - `docs/reviews/pr-55-deepreview-ds-20260515.md`

## Summary

AgentMiMo returned `PASS` with no substantive findings.

AgentDS returned `PASS` but listed two medium findings and five low-severity findings. The controller does not treat the final `PASS` label as sufficient by itself; each finding is adjudicated below.

## Findings Adjudication

### PR55-DS-1: `_accept_with_retry` does not catch durable transaction retry exhaustion

- Source reviewer: AgentDS.
- Severity: medium.
- Controller decision: accepted.
- Owner: PR 55 fix.

Rationale:

The motivation is valid. P6 explicitly turns accept ack timeout / ack lost into governed tool errors so raw tool results do not leak and tool execution does not crash. `HostTransactionRetryExhaustedError` is the concrete durable error raised when SQLite busy / locked retry is exhausted. The previous `except TimeoutError` branch did not catch it, so the exception could escape `_accept_with_retry` and bypass the governed timeout path.

Required fix:

- Catch `HostTransactionRetryExhaustedError` together with `TimeoutError` in `_accept_with_retry`.
- Do not catch broad `HostDurableError`, because schema, payload, foreign-key, or missing-event durable errors should remain visible as implementation defects.
- Add a targeted test that a fake accept port raising `HostTransactionRetryExhaustedError` is converted into `tool_accept_timeout` after bounded retry and does not leak raw tool output.

### PR55-DS-2: `fetch_more` single-use cursor check is not atomic under future concurrent calls

- Source reviewer: AgentDS.
- Severity: medium.
- Controller decision: deferred, non-blocking.
- Owner: ToolRuntime concurrency hardening before introducing concurrent tool execution.

Rationale:

The concern is structurally real under concurrent `fetch_more` calls that share one `TruncationManager`, but Phase 6 executes batch tool calls serially through `ToolRuntimeExecutor._execute_one`. The finding is not currently reachable through the Phase 6 execution model. Adding a lock here is plausible but broadens this PR beyond the accepted PR review fix. Track it as a future concurrency-hardening item.

### PR55-DS-3: already-terminal abnormal redispatch may leave empty duplicate registry state until scheduler close

- Source reviewer: AgentDS.
- Severity: low.
- Controller decision: deferred, non-blocking.
- Owner: scheduler / recovery hardening.

Rationale:

The scenario requires an already terminal Run to be dispatched again, which should already be prevented by admission and dispatchability checks. If it occurs, `scheduler.close()` still clears all registry state. This is not a Phase 6 exit blocker.

### PR55-DS-4: truncation `target_field` set to JSON null is treated like missing

- Source reviewer: AgentDS.
- Severity: low.
- Controller decision: deferred, non-blocking.
- Owner: ToolRuntime truncation hardening.

Rationale:

The behavior is a real edge case but low impact for current financial-report tool outputs. It does not affect the accepted PR review fix.

### PR55-DS-5: `TEXT_LINES` truncation normalizes CRLF / CR to LF

- Source reviewer: AgentDS.
- Severity: low.
- Controller decision: deferred, non-blocking.
- Owner: ToolRuntime truncation hardening.

Rationale:

This is byte-level formatting drift, not a correctness issue for current LLM-visible text summarization. If a future tool depends on exact line-ending preservation, it should be handled with a dedicated truncation strategy test.

### PR55-DS-6: accept reject enum values are reserved but not produced

- Source reviewer: AgentDS.
- Severity: low.
- Controller decision: deferred, already tracked.
- Owner: ToolRuntime hardening / later policy owner.

Rationale:

This matches existing residual risk around hardening accept rejection reasons. It is not a new PR blocker.

### PR55-DS-7: `ToolFactRejectedAck.retryable` is not consumed

- Source reviewer: AgentDS.
- Severity: low.
- Controller decision: deferred, non-blocking.
- Owner: ToolRuntime hardening.

Rationale:

Current production reject acks are not marked retryable, so the field is reserved shape rather than an active behavior gap. Do not introduce retry semantics in this PR without a concrete policy owner.

## Gate Decision

PR 55 deepreview is not yet fully closed because PR55-DS-1 is accepted for fix. After the PR55-DS-1 fix is committed and pushed, run PR 55 re-review focused on the accepted finding and regressions.
