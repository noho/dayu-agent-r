# WU-TOOLS-CANCEL-01 Slice S1 Code Review Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- Slice: WU-TOOLS-CANCEL-01-S1 interrupt capsule + local worker cleanup
- Gate: code review
- Implementation artifact: `docs/reviews/wu-tools-cancel-01-slice1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-cancel-01-slice1-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-slice1-code-review-ds.md`

## Verdict

Implementation direction is accepted, but fix gate is required before accepted slice commit.

## Adjudicated Findings

| Finding | Source | Decision | Rationale | Required Fix |
|---|---|---|---|---|
| F01 outer `CancelledError` can leak capsule/capsule task | AgentDS | accepted, blocking for slice acceptance | S1 goal is cancel-triggered cleanup. The new `capsule_task` is created before `wait_for_or_cancel(...)`; if the outer `ToolExecutor.execute()` task is cancelled, current control flow can exit without interrupting or closing the capsule. This directly risks process / queue / async task leakage. | Add `CancelledError` / exit-path cleanup in `_dispatch_tool_call_with_bounds(...)`. Ensure process-backed capsule is interrupted and closed when the outer task is cancelled. Add focused test that cancels the outer executor task while a process-backed non-cooperative target is running and proves cleanup. |
| 01 terminate-then-kill executor integration test missing | AgentMiMo | accepted, non-blocking but fix in this gate | Runtime helper tests cover hard kill, but ToolRuntime executor integration currently exercises only SIGTERM-success path. S1 plan expected hard-kill path coverage. | Add ToolRuntime executor-level test with a process target that ignores SIGTERM, proving terminate -> kill escalation under ToolRuntime cancellation. |
| F02 `on_cancel` background close task exception is not logged | AgentDS | accepted, non-blocking fix | The background close task is intentionally fire-and-forget because `on_cancel` is sync, but unobserved exceptions make cancel cleanup failures hard to diagnose. | Add a done callback or equivalent that logs close task exceptions with worker identity and reason. |
| F03 `capsule.close()` exception can hide governed cancel/timeout failure | AgentDS | accepted, non-blocking fix | Cleanup failure must not prevent ToolRuntime from returning governed cancel/timeout outcome. | Wrap close in `_interrupt_capsule_after_wait(...)` so close exceptions are logged and do not replace the governed outcome. Add focused test if practical. |
| 02 `_run_process_target` catches `BaseException` | AgentMiMo | accepted as low-priority fix if safe | Catching `BaseException` may convert signal-driven exits into business failures. The safer default is to catch `Exception` and let `SystemExit` / `KeyboardInterrupt` terminate the child process naturally. | Change `_run_process_target` to catch `Exception`, or document and test a deliberate alternative. |

## Non-Findings

- `tests/host/test_local_proxy_engine_ingest.py` is accepted as a reasonable focused S1 test location. It directly verifies default local worker `on_cancel(...)` -> event stream close behavior and is not scope overrun.
- S1 did not migrate Doc / Fins / Web production tools, did not change `dayu.contracts`, Engine contract, durable schema, EventLog, or public Host cancel API.

## Next Gate

Move to fix gate. AgentCodex should fix accepted findings, update tests, rerun the S1 validation matrix and pyright, and write `docs/reviews/wu-tools-cancel-01-slice1-fix-codex.md`.
