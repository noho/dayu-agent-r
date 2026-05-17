# P9 All-Repository Review Controller Adjudication

## Scope

- Review gate: P9 all-repository follow-up after draft PR review.
- Initial review artifacts:
  - `docs/reviews/repo-review-20260517-1402.md`（AgentMiMo）
  - `docs/reviews/repo-review-20260517-1411.md`（AgentDS）
- Re-review artifacts after first controller fix pass:
  - `docs/reviews/repo-review-20260517-1435.md`（AgentMiMo）
  - `docs/reviews/repo-review-20260517-1434.md`（AgentDS）
- Latest re-review artifacts:
  - `docs/reviews/repo-review-20260517-1503.md`（AgentMiMo，PASS）
  - `docs/reviews/repo-review-20260517-1507.md`（AgentDS）
- Follow-up DS review artifact after the non-stream read retry fix:
  - `docs/reviews/repo-review-ds-20260517-1521.md`（AgentDS，non-PASS before final fix pass）
- Final re-review artifacts after the stream retry / SSE finish / file lock fix pass:
  - `docs/reviews/repo-review-final-mimo-20260517.md`（AgentMiMo，PASS）
  - `docs/reviews/repo-review-final-ds-20260517.md`（AgentDS，PASS）
- Controller principle: accept low-risk correctness / observability hardening that is directly evidenced and does not change P9 design truth; defer broad architecture work to owned later phases.

## Accepted Fixes

The controller accepted and fixed the following findings in this gate:

- Projection checkpoint CAS hardening:
  - `advance_projection_checkpoint` now updates with the previous checkpoint sequence as CAS guard and checks rowcount.
- Non-stream / SSE tool call parity:
  - non-stream responses with emitted tool calls now close with `FinishReason.TOOL_CALLS`.
  - tool call position fallback ignores non-dict tool call array elements in SSE and non-stream parsers.
- Tool call assistant content fallback:
  - empty `tool_calls_content` no longer masks completed content.
- Timeout metric precision:
  - timeout elapsed seconds are captured before cancellation cleanup waits.
- Observability for swallowed exceptions:
  - active worker cancel failures log warning.
  - scheduler close safe cancel logs warning.
  - wait poll adapter abandon / poll failures log warning.
  - missing wait poll adapter registration logs warning.
  - pending `readany` cancellation cleanup logs non-cancel exceptions.
  - worker startup failure closeout failures are logged without masking the original startup path.
- Memory diagnostic precision:
  - unsupported memory event type has independent `unsupported_event_type` diagnostic reason.
- Durable schema / query hardening:
  - schema bumped to v7.
  - EventLog adds `(run_id, event_type, event_sequence)` partial index.
- Runtime and contract guardrails:
  - runtime weak typing guard test added.
  - `RunnerSpec` validates positive default timeout and non-negative max retries.
  - `BatchToolExecutionOutcome` validates non-empty, unique record tool call ids while leaving full request/outcome bijection to Engine.
- SSE usage resilience:
  - malformed usage is a warning and does not terminate otherwise valid content / tool-call streams.
- Dispatch transient retry classification:
  - `HostTransactionRetryExhaustedError` during dispatch no longer closes the Run as worker startup timeout.
  - The scheduler releases the lane token, logs a warning, and requeues the pending dispatch for a later drain.
- Stream retry safety:
  - SSE attempts that have already yielded any `RunnerEvent` no longer retry after a retriable read / idle failure.
  - The runner now emits the failure as HTTP error plus `Done(ERROR)` for that attempt, preventing cross-attempt content or tool-call concatenation.
- SSE final finish parity:
  - SSE streams that emitted tool calls now always close `RunnerDoneData.finish_reason` as `FinishReason.TOOL_CALLS`, even if the provider sends `stop`.
- Runtime file lock release failure cleanup:
  - `RuntimeFileLock.__exit__` clears the active token in a `finally` block, so release failures do not leave the same lock instance permanently stuck as active.

## Deferred Findings

The controller accepted these as real but out of this P9 follow-up scope:

- `agent.py` hard-coded `AsyncOpenAIRunner`:
  - Valid architecture debt.
  - Not a P9 regression and not a local memory correctness issue.
  - Correct fix requires Engine runner factory / registry / Host composition design and public entrypoint contract review.
  - Owner: future Engine runner abstraction / provider composition work.
- `reset_minimal_read_model_projection` clears global minimal read model tables:
  - Current minimal read model tables are global single-consumer read views and do not carry `consumer_id`.
  - Adding consumer-scoped reset requires schema design, not a local patch.
  - Owner: future read model multi-consumer schema work.
- RECOVERING transition coverage:
  - Recovery is a later-phase capability; current P9 must not invent recovery flows.
  - Owner: Phase 11 recovery state machine tests.
- `terminal_attempt_row` does not accept `SUSPENDED` as a generic source state:
  - Existing WAITING/SUSPENDED cancellation path uses dedicated waiting cancel transition and the `ATTEMPT_SUSPENDED` terminal event recorded when the Attempt was suspended.
  - Extending the generic terminal helper would change state-machine semantics and must be handled with the recovery / waiting transition owner, not this P9 memory follow-up.
- `session_lifecycle.py` durable/API layering:
  - Valid layering debt but requires error taxonomy and caller mapping refactor.
  - Owner: Host durable/API boundary cleanup.
- Command service instance caching, LocalProxy close/events race, read API enum mapping, ToolRuntime module size, memory module size, lane heartbeat/shield hardening, message/tool result size limits:
  - Valid hardening or maintainability items.
  - Not blockers for P9 memory gate because they are not introduced by P9 and need separate design/test scope.
- `_run_after_commit` subsequent callback exception logging, duplicate governance concurrent reserve semantics, shared test cancellation token fixture, WaitPoller concurrency guard, TruncationManager cursor cleanup ordering, and `_is_sse_response` content-type strictness:
  - Accepted as non-blocking hardening from MiMo PASS review.
  - Owners: Host durable observability, ToolRuntime duplicate governance, test utility cleanup, wait poller scheduler design, ToolRuntime cleanup, and Engine runner diagnostics respectively.

## Validation

- `pytest -q`: 966 passed.
- `pyright dayu tests`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Verdict

Controller accepts the implemented all-repository follow-up fixes as P9-scoped hardening. AgentMiMo and AgentDS final re-review both returned PASS. Remaining findings are tracked as residual risks with explicit owners and do not block P9 PASS.
