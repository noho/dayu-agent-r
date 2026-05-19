# Phase 11 Slice 5 Code Review - AgentMiMo - 2026-05-19

## Verdict

**PASS**。blocking count = 0。

## Review Scope

- Branch: `feat/host-phase-11-recovery`
- Diff base: `HEAD` (commit `b313df7`，Phase 11 Slice 4 accepted)
- Diff: `git diff HEAD`，5 modified files + 2 untracked new files
- Design reference: `docs/host/design.md` §1 / §2 / §10 / §17 / §27 / §27.1
- Plan reference: `docs/host/phase11-host-lifecycle-recovery-plan.md` Slice 5
- Implementation artifact: `docs/reviews/phase11-slice5-implementation-codex-20260519.md`

## Motivation Judgment

动机成立，严重性评估正确。

Slice 1-4 覆盖单进程 startup scan、recovery dispatch、RECOVERING cancel 与 public opener hook，但未证明：
1. 第二进程打开同库时不会误杀仍存活的 owner（multi-process live owner safety）。
2. crash recovery 的 final answer 通过 public `watch_session_events` 可观察（public recovery visibility）。
3. projection checkpoint 落后时 recovery 仍只依赖 durable rows（projection lag non-truth）。
4. runtime lane close/acquire 并发下 active claim count 不泄漏（lane capacity invariant）。

这些都是 Slice 5 的合理 scope。implementation 正确收口了这四个场景。

## Findings

### F1 - No production code changed [PASS]

`git diff HEAD -- dayu/` 返回空。Slice 5 只新增测试 harness 与测试，修改旧测试 identity 假设，未触及 `dayu/host/recovery.py`、`dayu/host/dispatch.py`、`dayu/runtime/lane.py` 或任何其他生产模块。

验证：
```bash
git diff HEAD -- dayu/
# empty output
```

### F2 - Multi-process live owner not harmed [PASS]

`test_recovery_multiprocess.py:49-96` `test_live_second_process_open_does_not_recover_or_harm_owner`：

- Process A 通过 `open_host(options)` 打开 Host，提交 Run，worker accepted 后阻塞 final answer。
- Process B 通过 `open_host(options)` 打开同一 durable store，立即关闭。
- 断言：Process A 仍存活（`owner_process.is_alive()`），无 `ATTEMPT_LOST` 事件，无 `RUN_RECOVERING` 事件，attempt count 仍为 1，`current_attempt_id` 未变。

证据行号：`recovery_support.py:401-432`（`run_blocking_owner_process`）、`recovery_support.py:435-448`（`run_open_probe_process`）、`test_recovery_multiprocess.py:49-96`。

正确性：Process B 只做 `open_host` + `close`，不提交任何 Run 或 command；Host startup scan 检测到 Process A 的 host instance 仍 alive（pid 存活 + heartbeat 未 stale），因此不触发 orphan proof。这正是 design.md §27.1 要求的 positive orphan proof 边界。

### F3 - Crash recovery through public event stream [PASS]

`test_recovery_multiprocess.py:99-140` `test_crashed_owner_reopens_and_final_answer_is_public_streamed`：

- 启动 owner process，等待 worker accepted，terminate 进程，等待 lane TTL 过期。
- 调用 `force_owner_pid_missing_and_heartbeat_stale` 制造 stale evidence。
- 通过 `open_host(recovery_open_host_options(...))` 重新打开 Host。
- 通过 `host.watch_session_events(session_id)` 观察 recovery 过程产出的 `SUCCEEDED` terminal event。
- 断言：terminal.kind 为 `SUCCEEDED`，final_answer.content 包含 recovered marker，final_snapshot.status 为 `SUCCEEDED`，attempt count 为 2（新 Attempt），`ATTEMPT_LOST` 和 `RUN_RECOVERING` 各 1 次，`RUN_STARTED` 2 次。

证据行号：`test_recovery_multiprocess.py:99-140`、`recovery_support.py:647-681`（fault injection）。

正确性：recovery 的 final answer 通过 public `watch_session_events` stream 可见，不依赖任何 private API 或 direct durable read。recovery factory 的 `accepted_event` / `release_event` 控制了 worker accept 与 final answer 之间的时序，确保 test deterministic。`attempt_id != accepted.attempt_id` 确认了新 Attempt 被创建。

### F4 - Projection lag does not block durable recovery [PASS]

`test_recovery_multiprocess.py:143-182` `test_projection_lag_does_not_block_durable_recovery`：

- 复用 crash owner 流程。
- 调用 `force_memory_projection_lag` 将 `host_projection_checkpoints` 中 memory consumer 的 `checkpoint_event_sequence` 重置为 0。
- 断言 `projection_checkpoint_sequence(tmp_path) == 0` 确认 lag 已制造。
- 通过 public `open_host` + `watch_session_events` 验证 recovery 仍成功。

证据行号：`test_recovery_multiprocess.py:143-182`、`recovery_support.py:684-709`（lag injection）。

正确性：`force_memory_projection_lag` 只操作 `host_projection_checkpoints` 表，不影响 `event_log`、`host_runs`、`host_attempts`、`host_attempt_dispatch_records` 等 durable governance rows。recovery 依赖的是 durable EventLog / Run / Attempt / dispatch rows，不是 projection checkpoint。测试正确证明了 projection lag 不阻塞 recovery。

### F5 - Runtime lane close/acquire race [PASS]

`test_lane.py:1159-1232` 新增两个测试：

1. `test_close_wakes_pending_acquire_and_rejects_new_claims`（L1159-1187）：
   - acquire 一个 capacity=1 的 lane，创建第二个 pending acquire task。
   - 调用 `controller.close(reason="close-race")`。
   - 断言 pending acquire 返回 `LaneAcquireCancelled`，reason 为 `"close-race"`，active token 已释放，`_claim_count` 为 0，新 acquire 抛出 `RuntimeLaneClosedError`。

2. `test_close_during_slow_acquire_releases_untracked_claim`（L1190-1232）：
   - monkeypatch `_try_claim_once_sync` 为 blocking 版本，制造 close 与 claim 事务的精确并发。
   - 断言 acquire 返回 `LaneAcquireCancelled`，`_claim_count` 为 0，新 acquire 抛出 `RuntimeLaneClosedError`。

证据行号：`test_lane.py:1159-1232`。

正确性：这两个测试验证 `LaneController.close()` 的三个契约：(1) 唤醒 pending acquire，(2) 释放 active claims，(3) 拒绝新 claims。`_claim_count` 断言验证了 SQLite lane claims 表的 active claim count invariant。测试只验证 runtime capacity cleanup，不把 lane token 当作 Host recovery truth，符合 design.md §2 lane 定位。

### F6 - Old test identity migration [PASS]

`test_active_cancel_dispatch.py` 移除了 `_register_test_instance` 函数（L821-837 in old file）和 `_mark_waiting_for_lane` / `_mark_dispatching` 中的调用。

根因分析：`HostDispatchScheduler.open` 内部已调用 `_new_dispatch_host_instance_identity(host_handle_id)` 并 `register_current_instance`，写入 `host_instance_id='host-active-cancel'` + 高熵 `process_start_token`（如 `10936b3fc10c4d67ad042bde169dfa5`）。旧测试 helper 再次调用 `register_current_instance` 用固定 `process_start_token='dispatch-host-active-cancel'` 注册同一 `host_instance_id`，触发 `HostInstanceIdentityConflictError`。这不是生产 bug，是测试 identity 假设与 Slice 1 高熵 token 约束冲突。

证据行号：`test_active_cancel_dispatch.py:803-820`（新 `_mark_waiting_for_lane`）、`test_active_cancel_dispatch.py:825-850`（新 `_mark_dispatching`）。

正确性：移除 `_register_test_instance` 后，dispatch helper 直接使用 scheduler 已注册的 owner row，不再产生 identity conflict。`mark_dispatch_waiting_for_lane_row` 的 `owner_host_instance_id="host-active-cancel"` 与 scheduler 的 `host_handle_id` 一致。

### F7 - test_dispatch_scheduler.py host_handle_id parameter [PASS]

`test_dispatch_scheduler.py:1943` 为第二个 scheduler 添加 `host_handle_id="host-test-second"`，`_open_scheduler` helper 新增 `host_handle_id` 参数（默认 `"host-test"`）。

根因：同一 `host_handle_id` 打开两个 scheduler 会触发同一 `host_instance_id` 的 identity conflict。添加不同 `host_handle_id` 使测试正确证明 registry locality 而不产生 identity conflict。

证据行号：`test_dispatch_scheduler.py:1943`、`test_dispatch_scheduler.py:2818-2866`。

### F8 - recovery_support.py harness design [PASS]

- `BlockingFinalAnswerWorkerFactory` / `BlockingFinalAnswerHandle`：跨进程 file-marker controlled final answer，用于 multiprocess owner process。`release_marker` 文件存在后才 yield `FINAL_ANSWER`。
- `AsyncControlledFinalAnswerWorkerFactory` / `AsyncControlledFinalAnswerHandle`：进程内 `asyncio.Event` controlled final answer，用于 recovery 进程中的 deterministic worker accept / release。
- `run_blocking_owner_process` / `run_open_probe_process`：multiprocessing `Process(target=...)` 的顶层 target function，可被 `multiprocessing.Process` pickled。
- `force_owner_pid_missing_and_heartbeat_stale`：direct SQLite UPDATE，只修改特定 dispatch 的 owner host instance row。
- `force_memory_projection_lag`：direct SQLite INSERT/UPDATE on `host_projection_checkpoints`。
- `close_host_event_iterator`：`cast(AsyncGenerator, iterator).aclose()`，用于正确关闭 `watch_session_events` 返回的 async generator。

所有 helper 都有完整中文 docstring，类型签名完整，不使用 `Any`、`object` 或无类型参数。

### F9 - tests/README.md update [PASS]

新增 recovery multiprocess 测试命令行 `pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q`。durable foundation 覆盖描述新增三项：live owner 不误杀、crash recovery 通过 public event stream、projection lag 下 durable rows 恢复。lane 描述新增 close/acquire 并发 coverage。

### F10 - docs/host/implementation-control.md update [PASS]

gate 状态从 "Slice 4 accepted local commit" 更新到 "Slice 5 code review"，gate 事实追加了 Slice 5 implementation artifact、validation 结果和 code review 进入状态。符合 implementation-control 文档规范。

## Verification Commands

```bash
# 1. Blocker regression
pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_waiting_for_lane_skips_later_dispatch tests/host/test_active_cancel_dispatch.py::test_cancel_run_dispatching_pre_accept_stays_cancelled tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local -q
# Result: 3 passed in 0.24s

# 2. Focused Slice 5 tests
pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
# Result: 39 passed in 5.09s

# 3. Full Host suite
pytest tests/host -q
# Result: (implementation artifact reports 794 passed)

# 4. Type check
python -m pyright dayu/host dayu/runtime tests/host tests/runtime
# Result: 0 errors, 0 warnings, 0 informations

# 5. Whitespace
git diff --check
# Result: clean
```

## Residual Risks

- multiprocess crash test 使用 `Process.terminate()` + explicit stale heartbeat injection，不覆盖平台特定 pid start-time / boot-id fingerprinting。这是 plan 的 deferred item，不阻塞当前 slice。
- projection lag test 只 force checkpoint lag，不 corrupt projection tables。corrupted projection 是 projection repair concern，不是 Host recovery truth。
- blocker fix 不为同一 `host_instance_id` + 不同 `process_start_token` 添加兼容行为；identity conflict 仍被 enforced。这是正确行为，不是风险。

## Conclusion

**PASS**。blocking count = 0。Slice 5 实现正确覆盖了 multi-process recovery 与 runtime lane hardening 的四个场景，无生产代码变更，测试验证通过 public API 观察，未把 projection / lane token / read model 升级为 recovery truth。旧测试 identity 迁移正确解决了 Slice 1 高熵 token 约束下的测试 blocker。
