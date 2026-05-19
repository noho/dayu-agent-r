# Phase 11 Slice 5 Implementation - AgentCodex - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening。
- Assigned slice: Slice 5. Multi-process Recovery And Runtime Lane Hardening。
- Role constraint: implementation specialist only. No commit, no push, no PR, no review gate。
- Pre-existing dirty file not touched: `docs/host/implementation-control.md`。

## Motivation Judgment

动机成立。Slice 1-4 已提供 process proof、startup scan、recovery dispatch、RECOVERING cancel 和 public opener hook，但主要覆盖单进程或 direct durable 场景；这不能证明 live owner 在第二进程打开同库时不会被误杀，也不能证明 crash recovery 的用户可见答案仍通过 public Host event stream 输出。

严重性评估正确。Host recovery 的第一性原理是 durable EventLog / Run / Attempt / dispatch rows 加 positive orphan proof，而不是 projection、memory、read model、audit、trace、outbox、lane token 或 heartbeat stale alone。Slice 5 必须把多进程证据和 runtime lane capacity cleanup 的边界测出来。

## Changed Files

- `tests/host/recovery_support.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/runtime/test_lane.py`
- `tests/README.md`
- `docs/reviews/phase11-slice5-implementation-codex-20260519.md`

No production Host/Runtime code was changed. `dayu/runtime/lane.py`, `dayu/host/recovery.py`, and `dayu/host/dispatch.py` were inspected but did not require changes for the reproduced Slice 5 scenarios or the final Host test blocker.

## Implemented Items

- Added a focused multi-process recovery harness:
  - owner process opens public `open_host(options)`, submits a Run, reaches worker accept, and blocks final answer with a marker file.
  - probe process opens the same DB through public `open_host(options)` and closes without touching the live owner.
  - crash path terminates the owner process, waits only for runtime lane TTL cleanup, then injects stale heartbeat + missing pid evidence for Host recovery proof.
- Added multi-process recovery tests:
  - live second process does not append `ATTEMPT_LOST`, does not append `RUN_RECOVERING`, does not create a second Attempt, and the original owner process remains alive.
  - killed owner pid + stale heartbeat reopens through public `open_host(options)` and produces a succeeded final answer through `watch_session_events(session_id)`.
  - projection checkpoint lag is forced before reopen; recovery still succeeds from durable EventLog / Run / Attempt / dispatch rows.
- Added runtime lane close/acquire hardening tests:
  - close wakes a pending acquire even with a long poll interval.
  - close releases active held claims and rejects new acquire calls.
  - close racing with a slow shielded claim releases the untracked claim and preserves active claim count invariant.
- Confirmed stale runtime lane claim cleanup remains runtime capacity cleanup only. Tests wait for lane TTL before expecting dispatch capacity, but Host orphan proof still comes from durable liveness pid + heartbeat evidence.
- Fixed the final Host test blocker without weakening production identity constraints:
  - `tests/host/test_active_cancel_dispatch.py` no longer manually registers an already-open scheduler's `host_instance_id` with the old fixed `process_start_token`. The helper now reuses the durable liveness row created by `HostDispatchScheduler.open`.
  - `tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local` opens the second scheduler with a different `host_handle_id`, so the test proves registry locality without creating an invalid same-instance identity conflict.

## Blocker Evidence

The three failing tests were not evidence of a production owner-id bug. Direct failure output showed `HostDispatchScheduler.open` had already registered rows like `host_instance_id='host-active-cancel'` with a high-entropy token such as `10936b3fc10c4d67ad042bde169dfa5`; the old test helper then called `register_current_instance` for the same `host_instance_id` with `process_start_token='dispatch-host-active-cancel'`, which correctly raised `HostInstanceIdentityConflictError`.

`dayu/host/dispatch.py` writes dispatch `owner_host_instance_id` from `self._host_handle_id`, and `_new_dispatch_host_instance_identity(host_handle_id)` creates `HostInstanceIdentity(host_instance_id=host_handle_id, ...)`. Therefore the production owner id matches the registered Host instance id; the root cause was stale test identity setup, not dispatch owner id persistence.

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_waiting_for_lane_skips_later_dispatch tests/host/test_active_cancel_dispatch.py::test_cancel_run_dispatching_pre_accept_stays_cancelled tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local -q
```

Result: `3 passed in 0.30s`

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
```

Result: `39 passed in 5.17s`

```bash
source .venv/bin/activate && pytest tests/host -q
```

Result: `794 passed in 62.48s`

```bash
source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
```

Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

Result: passed.

## Docs Decision

- Updated `tests/README.md` because this slice adds new Host multiprocess recovery tests and runtime lane close/acquire race coverage.
- Did not update `tests/README.md` for the final blocker fix because the helper-only identity correction does not change test layering, run commands, conventions, or maintenance rules.
- Did not update `dayu/host/README.md` because no `dayu/host/` production behavior changed in this slice.
- Did not update root `README.md` because no user-facing CLI, install, configuration, trace/render, or workflow changed.

## Risks / Uncovered

- The multiprocess crash tests use `Process.terminate()` and explicit stale heartbeat injection to create portable missing-pid proof. They do not add platform-specific pid start-time / boot-id fingerprinting.
- Projection lag coverage forces memory projection checkpoint lag; it does not attempt to corrupt projection tables, because corrupted projection is a projection repair concern, not Host recovery truth.
- The final blocker fix intentionally did not add compatibility behavior for re-registering a live `host_instance_id` with a different `process_start_token`; that conflict remains enforced.

## Conclusion

HANDOFF_IMPLEMENTED
