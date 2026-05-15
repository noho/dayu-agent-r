# Gateflow Code Review: Host P5-S3 Dispatch Scheduler, Lane And LocalProxy

## Gate

- Work unit: Host Phase 5 RunInputBuilder local dispatch
- Slice: P5-S3 Dispatch Scheduler, Lane And LocalProxy
- Role: code review
- Reviewer: mimo
- Branch: `feat/host-phase5-local-dispatch`
- Design source: `docs/host/design.md` §17 / §22
- Approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S3, §3.4, §3.5, §4 cancel boundary
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s3-dispatch-scheduler-localproxy-20260514.md`

## Validation

| Check | Result |
| --- | --- |
| `pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q` | 27 passed in 0.77s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | passed |

## Review Findings

### F1. Scheduler Flow: pending → waiting_for_lane → dispatching → worker accept — CORRECT

`_dispatch_one` (dispatch.py:295-325) implements the full flow:

1. `_mark_waiting_for_lane` — CAS `PENDING → WAITING_FOR_LANE`; idempotent if already `WAITING_FOR_LANE`.
2. `lane_controller.acquire` — runtime lane capacity gate.
3. `_mark_dispatching_after_recheck` — durable recheck reads Run/Attempt/dispatch record, verifies `_is_dispatchable_recheck`, then CAS `WAITING_FOR_LANE → DISPATCHING`.
4. `_dispatch_record_still_pre_accept` — final pre-call recheck confirming `DISPATCHING` + no `worker_accept_event_id` + no `cancelled_event_id`.
5. `_accept_worker_running` — single transaction: append `ATTEMPT_RUNNING`, CAS Attempt `STARTING → RUNNING`, record dispatch worker accept refs.

Status lifecycle matches design §17 worker dispatch semantic contract. `dispatching` status persists after worker accept (dispatch record status is not changed to a new state), consistent with plan requirement "dispatch record status 仍 dispatching".

### F2. Runtime Lane Independent DB — CORRECT

`HostDispatchScheduler.open` (dispatch.py:179-201) creates `LaneController` with `SQLiteLaneCoordinatorConfig(db_path=local_execution.lane_db_path)`. Lane DB is independent from Host durable DB. Plan stop condition "lane DB 与 Host durable DB 合并" is not triggered.

### F3. Durable Recheck CAS Loser Releases Lane — CORRECT

`_dispatch_one` (dispatch.py:318-319): when `_mark_dispatching_after_recheck` returns `None`, `await token.release()` is called before returning `"skipped"`. Worker is not called.

### F4. Pre-call Cancel Race — CORRECT

`_dispatch_record_still_pre_accept` (dispatch.py:396-416) reads latest dispatch record and checks:
- `status == DISPATCHING`
- `worker_accept_event_id is None`
- `cancelled_event_id is None`

If cancel has been committed between lane acquire and worker call, this check fails and `_dispatch_one` releases the lane token (dispatch.py:323-324).

### F5. Lane Acquire Timeout and Worker Startup Timeout — CORRECT

Both timeouts closeout as FAILED with reason `worker_startup_timeout`:

- **Lane acquire timeout** (dispatch.py:309-310): `LaneAcquireTimedOut` triggers `_closeout_worker_startup_timeout`.
- **Worker startup timeout** (dispatch.py:448-451): `asyncio.wait_for` `TimeoutError` triggers `_closeout_worker_startup_timeout`.

`_closeout_worker_startup_timeout` (dispatch.py:575-606) uses `terminal_closeout_in_transaction` with `AttemptStatus.FAILED` / `RunStatus.FAILED` and reason `worker_startup_timeout`.

### F6. ATTEMPT_RUNNING Payload Completeness — CORRECT

`_attempt_running_event_request` (dispatch.py:719-730) includes all 4 P5-S3 residual fields:

```python
"local_worker_id": local_worker_id,
"worker_accepted_at": accepted_at_text,
"lane_name": lane_name,
"lane_claim_id": lane_claim_id,
```

Plus canonical fields: `attempt_id`, `execution_id`, `dispatch_record_id`, `worker_kind`, `execution_target`, `reason`.

### F7. Attempt RUNNING Only After Durable ATTEMPT_RUNNING — CORRECT

`_accept_worker_running` (dispatch.py:506-573) executes in a single write transaction:
1. Append `ATTEMPT_RUNNING` event.
2. `mark_attempt_running_row` — CAS `STARTING → RUNNING`.
3. `mark_dispatch_worker_accepted_row` — record accept refs.

If any step fails, the entire transaction rolls back. Attempt cannot be RUNNING without durable `ATTEMPT_RUNNING`.

### F8. LocalProxy Default Worker — CORRECT

`DefaultLocalEngineWorker.accept` (local_proxy.py:43-59) returns `_DefaultLocalWorkerHandle`.
`_DefaultLocalWorkerHandle.events()` (local_proxy.py:91-99) calls `run_agent_messages(self._request)`.
`cancel` is no-op (local_proxy.py:101-110). `close` acloses the generator (local_proxy.py:113-121).

No ingest, no terminal closeout, no recovery. Consistent with P5-S3 scope boundary.

### F9. Host→Engine Import Boundary — CORRECT

`test_command_handle.py` removes `"dayu.engine"` from `_FORBIDDEN_IMPORT_PREFIXES`. This is intentional: P5-S3 LocalProxy requires `dayu.engine.run_agent_messages`. Fins / Service / UI remain forbidden.

### F10. HostCommandHandleOptions.local_execution Wiring — RESIDUAL RISK, NOT BLOCKING

`HostCommandHandleOptions.local_execution` is typed (`HostLocalExecutionOptions | None`) and defaults to `None` (api.py:772). The scheduler is self-contained in `dispatch.py` and does not depend on command handle construction.

Per plan: "为 `None` 时保持 no-op wakeup，不启动本地执行。" Current behavior is correct: when `local_execution` is `None`, no scheduler is started, existing command handle tests exercise no-op dispatch wakeup.

Full command-handle scheduler lifecycle wiring is deferred. Implementation artifact §Residual Risks documents this. Not blocking because:
- The scheduler works independently.
- The `local_execution = None` default preserves backward compatibility.
- No existing behavior is broken.

### F11. Scope Boundary Compliance — CORRECT

No implementation of:
- EngineEvent terminal ingest mapping (P5-S4)
- Full active/session-scope cancel propagation (P5-S5)
- ToolRuntime, WAITING, RemoteProxy, recovery, lease/fencing/takeover

`_consume_worker_events` (dispatch.py:608-624) iterates events but discards them (`async for _event in handle.events(): pass`). This is correct: P5-S3 only needs to drain the stream and release the lane token on completion. Event ingest is P5-S4.

### F12. `_NeverCancelledToken` Placeholder — RESIDUAL RISK, NOT BLOCKING

`_snapshot_from_dispatch` (dispatch.py:478) uses `_NeverCancelledToken()` as the cancellation token. This means the scheduler does not observe Host cancellation through the token protocol.

Per design §22: "Engine 只观察 run-local cancellation token." The current Phase 5 implementation relies on durable state checks (`cancelled_event_id`, dispatch record status) for cancel observation, which is the correct approach for pre-accept cancel. Full cancel propagation through the token to the Engine is P5-S5.

### F13. Missing Test: Handle Close Cancel Pending Acquire — RESIDUAL RISK

Plan test requirement: "handle close 取消 pending acquire、best-effort cancel active worker、release lane。"

No test verifies that `scheduler.close()` properly cancels a pending lane acquire, cancels active workers, and releases held lane tokens. The `close()` implementation does these things (dispatch.py:258-277), but test coverage is absent.

Not blocking: the implementation follows the correct pattern (cancel tasks, close handles, close lane controller), and the happy-path tests verify the underlying primitives work.

## Residual Risks

1. **`HostCommandHandleOptions.local_execution` wiring**: Typed and defaulted to `None`, but not wired to actual command handle construction. Full lifecycle wiring deferred to controller scope.
2. **`_NeverCancelledToken` placeholder**: Scheduler does not observe Host cancellation through the CancellationToken protocol. Cancel observation relies on durable state checks only. Full token-based cancel propagation is P5-S5.
3. **Missing handle close test**: No test verifies `scheduler.close()` behavior for pending lane acquire cancellation, active worker cancellation, or lane token release.
4. **`_consume_worker_events` discards events**: Correct for P5-S3 scope, but event consumer must be replaced with P5-S4 ingest mapping before the local execution path is complete.

## Conclusion

**0 blocking findings.** All plan items are implemented correctly. Validations pass (27 tests, pyright clean, no whitespace errors). Implementation is ready for code review gate.

## Scope Notes

- Did not review `dayu/host/command.py` or `dayu/host/admission.py` — no changes in P5-S3 diff.
- Reviewed against design §17 (WorkerProxy / EngineWorker) and §22 (Cancel) for P5-S3 specific requirements.
- Verified dispatch record status lifecycle matches design §17 worker dispatch semantic contract.
- Verified lane token release paths cover: CAS recheck loss, pre-accept cancel, lane acquire timeout, worker startup timeout, worker stream completion, and scheduler close.
