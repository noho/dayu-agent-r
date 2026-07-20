# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `2f2b73f8` (accepted S1 commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s2-code-review-mimo.md`
- Included scope: 22 files changed since S1 acceptance (3 new production, 2 new test, 17 modified)
- Excluded scope: `dayu/config/`, `dayu/engine/`, `dayu/fins/` (not in S2 allowed list)
- Parallel review coverage: 4 subagents — actor ownership & bridge, close order & admin separation, CLI routing & test quality, dispatch changes & source scans. All areas covered; no residual uncovered zones.

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

1. **`DurableActor.close_handle()` check-then-assign race** (`_durable_actor.py:159-163`): `_handle_close_future is None` check is not atomic with assignment. Two concurrent callers could submit `_close_command_handle` twice. Current callers (`_PublicHostHandle.close()` and `_PublicHostAdminHandle.close()`) are guarded by `_closed` flag, making the race unreachable today. If a future caller bypasses the public handle's close guard, the double-close would call `command_handle.close()` on an already-closed handle. Severity: low, latent.

2. **`_run_callback_on_event_loop` has no timeout** (`open_host.py:377`): `future.result()` blocks the actor thread indefinitely. If the event loop is blocked by a long-running synchronous callback, all subsequent actor operations stall. In practice, scheduler bridge callbacks (`wake_dispatch`, `cancel`) are fast, so this is a liveness concern, not a correctness bug. Severity: low, latent.

3. **`DurableActor.shutdown_executor()` blocks event loop** (`_durable_actor.py:182`): `executor.shutdown(wait=True)` is synchronous and runs on the event loop thread (verified by `_require_opener_loop()`). By the time this executes, the only pending work is `_close_command_handle` which has already completed, so blocking is negligible. If a spurious future were still queued, the event loop would block. Severity: low, latent.

4. **Watchdog `QueueFull` wake drop** (`dispatch.py:1131-1132`): `wake_active_cancel_watchdog()` silently drops the wake signal when the queue is full. This is the known S5 finding (watchdog wakeup drop). S2 correctly preserves this pattern; the fix is deferred to S5 which changes to `asyncio.Event`. Severity: known, deferred to S5.

5. **`_is_deferred_cancel_state` post-write read** (`command.py:1650-1684`): The deferred cancel check opens a second read transaction after the write transaction fails. This is the known S5 finding (cancel_run deferred race). S2 correctly preserves this pattern; the fix is deferred to S5. Severity: known, deferred to S5.

## Review Verification Summary

All S2 focus areas verified by direct code path inspection:

| Focus Area | Verdict | Evidence |
|---|---|---|
| HostAdmin separation | PASS | `Host`/`HostAdmin` are independent Protocols (`api.py:3500,3576`); admin opener creates no scheduler/recovery/lane/worker/secret (`open_host.py:1424-1453`); `HostAdmin` exposes no execution/cancel/watch methods |
| Durable actor ownership | PASS | `handle_factory` called inside executor thread (`_durable_actor.py:235`); `HostCommandHandle` never leaves actor thread; `_PublicHostHandle` has no `_command_handle` slot |
| Busy SQLite / event loop | PASS | `asyncio.Event`-driven ticker in tests proves event loop progresses during actor busy retry (test evidence from controller validation) |
| Caller cancellation & FIFO | PASS | `asyncio.shield` in `call()` (`_durable_actor.py:104`); cancelled caller doesn't cancel executor work; `ThreadPoolExecutor(max_workers=1)` preserves FIFO |
| Event-loop bridge | PASS | `_ThreadsafeSchedulerWakeupPort` and `_ThreadsafeActiveWorkerCancelPort` use `call_soon_threadsafe` + typed `Future` (`open_host.py:277-361`); `_is_current_event_loop` check prevents deadlock when called from event loop thread |
| Close order | PASS | Execution: gate→wait_poller→actor_drain→scheduler→projection→actor_handle→executor→scheduler_store (`open_host.py:909-1023`); Admin: actor chain only (`open_host.py:1151-1165`) |
| CLI opener routing | PASS | `session list/purge` → `open_host_admin` (`session.py:192`); `session resume` → `open_host` (`session.py:273,303`); resume label resolution uses short-lived admin handle (`session.py:424-441`) |
| Tests/docs | PASS | Stale execution purge assertions removed from `test_public_lifecycle_smoke.py`; tests assert owner-level behavior; `HostAdmin`/`open_host_admin` in package exports (`__init__.py:129,273-274`) |
| Project constraints | PASS | Chinese docstrings on all new public functions/classes; no `Any`/`object` in new signatures; no reverse dependency; no compatibility re-export/wrapper; no schema migration |
