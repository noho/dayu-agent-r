# Phase 11 Slice 5 Code Review — AgentDS — 2026-05-20

## Verdict: PASS

Blocking count = 0。所有验证通过，无新增 risk，无 production code / schema / public API 变更。

---

## 1. 动机判定（第一性原理）

**动机成立**。Slice 1-4 已覆盖 process proof、startup scan、recovery dispatch、RECOVERING cancel 和 public opener hook，但证据主要在单进程或 direct durable 场景。以下问题未被 Slice 1-4 证明：

- 第二个 live 进程打开同库时，是否会被误判为 orphan 并写入 `ATTEMPT_LOST` / `RUN_RECOVERING` / 新 Attempt？
- crash recovery 的 final answer 是否真正通过 public `open_host(options)` + `watch_session_events(session_id)` 可见？
- projection checkpoint 落后时，recovery 是否仍只依赖 durable EventLog / Run / Attempt / dispatch rows？

Host recovery 第一性原理是 durable EventLog / Run / Attempt / dispatch rows + positive orphan proof（pid + heartbeat），不是 projection、read model、lane token 或 memory snapshot。Slice 5 的多进程证据和 runtime lane capacity cleanup 边界测试是必要的。

**严重性评估正确**。若误杀 live owner，会导致重复派发、重复 side effect；若 crash recovery 不通过 public stream 产出 answer，则上层 Service 无法观测恢复结果。

---

## 2. 变更范围审查

### 2.1 Production Code 变更：零

```
$ git diff HEAD -- dayu/
(no output)
```

确认：`dayu/host/`、`dayu/runtime/`、`dayu/engine/` 的生产代码零变更。未修改 `dayu/host/recovery.py`、`dayu/host/dispatch.py`、`dayu/runtime/lane.py`。

### 2.2 变更文件清单

| 文件 | 变更类型 | 评估 |
|------|---------|------|
| `tests/host/recovery_support.py` | 新增 | 测试支撑模块，不进入生产 |
| `tests/host/test_recovery_multiprocess.py` | 新增 | 多进程 recovery 行为测试 |
| `tests/runtime/test_lane.py` | 新增 2 个测试 | lane close/acquire race 测试 |
| `tests/host/test_active_cancel_dispatch.py` | 修改 | 移除过时的 `_register_test_instance` helper |
| `tests/host/test_dispatch_scheduler.py` | 修改 | `_open_scheduler` 增加 `host_handle_id` 参数 |
| `tests/README.md` | 修改 | 新增 recovery multiprocess 运行命令 + lane race 描述 |
| `docs/host/implementation-control.md` | 修改 | gate 状态更新 |

### 2.3 无 Schema 变更

未新增/删除/修改任何 DDL、table、column、index 或 CHECK 约束。`git diff HEAD -- dayu/` 为空确认。

### 2.4 无 Engine 变更

Engine 生产代码零 diff。

### 2.5 无 Public API 变更

`dayu/host/__init__.py` 和 `dayu/host/api/` 零 diff。不新增 public recovery command、policy option 或 alternate startup API。

---

## 3. 逐项审查

### 3.1 Multi-process live owner not harmed

**测试**: `test_live_second_process_open_does_not_recover_or_harm_owner`
**文件**: `tests/host/test_recovery_multiprocess.py:49-96`

**证据链**:

1. Owner 进程通过 `open_host(options)` 打开 Host，提交 follow-up Run，worker accept 后被 `BlockingFinalAnswerHandle` 阻塞在 release marker 等待中（行 58-74）。此时 owner 进程**存活**且持有 active Attempt。
2. Probe 进程通过 `run_open_probe_process` 打开同一 `host.sqlite3`（行 77-82），内部调用 `open_host(options)` 后立即 `__aexit__` 关闭。Probe 进程正常退出（exitcode=0）。
3. 验证 owner 进程仍存活（行 84: `assert owner_process.is_alive()`）。
4. 验证 EventLog 中无 `ATTEMPT_LOST`（行 85: `event_type_count(tmp_path, "ATTEMPT_LOST") == 0`）。
5. 验证 EventLog 中无 `RUN_RECOVERING`（行 86: `event_type_count(tmp_path, "RUN_RECOVERING") == 0`）。
6. 验证 Attempt 数仍为 1（行 87: `attempt_count_for_run(tmp_path, accepted.run_id) == 1`）。
7. 验证 current_attempt_id 未被替换（行 88-89: `current_attempt_id_for_run(tmp_path, accepted.run_id) == accepted.attempt_id`）。
8. 释放 final answer 后 owner 进程正常退出（行 92-94）。

**判定**:
- `event_type_count` 读自 `event_log` 表（canonical durable EventLog），行号 `recovery_support.py:722` 确认。
- `attempt_count_for_run` 读自 `host_attempts` 表（durable Attempt），行号 `recovery_support.py:743` 确认。
- `current_attempt_id_for_run` 读自 `host_runs` 表（durable Run），行号 `recovery_support.py:765` 确认。
- 三个函数均读自 durable 真源表，非 projection / read model。
- **真正证明了 live second process 不会触发 ATTEMPT_LOST / RUN_RECOVERING / 新 Attempt，且 owner 进程不受影响。**

### 3.2 Crash recovery final answer 通过 public stream 可见

**测试**: `test_crashed_owner_reopens_and_final_answer_is_public_streamed`
**文件**: `tests/host/test_recovery_multiprocess.py:99-140`

**证据链**:

1. `_start_and_crash_owner`（行 185-224）：启动 owner 子进程 → 等待 worker accepted → `terminate_process` → `wait_for_runtime_lane_claim_ttl_to_expire()`（runtime capacity cleanup）→ `force_owner_pid_missing_and_heartbeat_stale`（durable Host recovery proof）。
2. Recovery 通过 public `open_host(recovery_open_host_options(...))` 打开（行 112）。
3. 通过 public `host.watch_session_events(accepted.session_id)` 订阅事件流（行 114）。
4. 从 watcher 获得 terminal HostEvent（行 123-124: `next_terminal_for_run(watcher, ...)`）。
5. 断言 `terminal.kind is HostEventKind.SUCCEEDED`（行 130）——public HostEvent 类型。
6. 断言 `terminal.final_answer.content == f"recovered-final:{accepted.run_id}"`（行 131-132）——public typed final answer view。
7. 断言 `final_snapshot.status is RunStatus.SUCCEEDED`（行 133）——public Run snapshot。
8. 新 Attempt id 不同于旧 Attempt id（行 136: `recovery_factory.snapshots[0].attempt_id != accepted.attempt_id`）。
9. EventLog 中有 1 个 `ATTEMPT_LOST`、1 个 `RUN_RECOVERING`、2 个 `RUN_STARTED`（第二个为 start_reason=recovery）（行 137-139）。
10. Attempt 数为 2（行 140）。

**关键时序分离**: `wait_for_runtime_lane_claim_ttl_to_expire()`（行 221）明确注释 "该等待只服务 runtime capacity cleanup，不参与 Host recovery proof"（`recovery_support.py:638-641`）。Host recovery proof 来自 `force_owner_pid_missing_and_heartbeat_stale`（行 222），它直接修改 `host_instances` 表的 pid 和 heartbeat_at。两者职责清晰分离。

**判定**: **真正通过 public `open_host` + `watch_session_events` 路径验证了 crash recovery 的 final answer 可见性。**

### 3.3 Projection lag 不阻断 durable recovery

**测试**: `test_projection_lag_does_not_block_durable_recovery`
**文件**: `tests/host/test_recovery_multiprocess.py:143-182`

**证据链**:

1. 同 crash owner 流程：启动 → accept → crash → lane TTL → stale heartbeat（行 149-154）。
2. `force_memory_projection_lag(tmp_path)`（行 155）：将 `host_projection_checkpoints` 的 `checkpoint_event_sequence` 设为 0（初始值）。
3. 断言 `projection_checkpoint_sequence(tmp_path) == 0`（行 156）——确认 lag 已注入。
4. Recovery 通过 public `open_host` + `watch_session_events`（行 159-160）。
5. Recovery 成功：`terminal.kind is HostEventKind.SUCCEEDED`（行 176）、final answer 正确（行 177-178）。
6. EventLog 中 `ATTEMPT_LOST=1`、`RUN_RECOVERING=1`（行 180-181）——从 durable EventLog 读，非 projection。
7. Attempt 数 = 2（行 182）。

**关键**: `force_memory_projection_lag` 操纵的是 `host_projection_checkpoints` 表（`recovery_support.py:684-709`），这是 projection checkpoint 表，不是 EventLog / Run / Attempt / dispatch 真源。测试断言 projection lag 被注入后 recovery 仍成功，证明 recovery 不依赖 projection 当前状态。

**判定**: **没有把 projection/read-model 当作 recovery truth。** Projection checkpoint 仅用于证明 lag 已注入；recovery 结果断言全部来自 durable EventLog + Run + Attempt。

### 3.4 Lane close/acquire 测试仅验证 runtime capacity cleanup

**新增测试**:
- `test_close_wakes_pending_acquire_and_rejects_new_claims`（`tests/runtime/test_lane.py:1158-1191`）
- `test_close_during_slow_acquire_releases_untracked_claim`（`tests/runtime/test_lane.py:1194-1237`）

**证据**:

1. `test_close_wakes_pending_acquire_and_rejects_new_claims`:
   - 使用长 poll interval (10.0s) 确保 pending acquire 在等待中（行 1170-1175）。
   - `close(reason="close-race")` 后 pending acquire 返回 `LaneAcquireCancelled`（行 1185-1186）。
   - held token 被 best-effort release（行 1187: `first.token.released is True`）。
   - claim count = 0（行 1188）。
   - 新 acquire 抛出 `RuntimeLaneClosedError`（行 1189-1190）。
   - 所有断言为 runtime lane 原语：`LaneAcquireCancelled`、`_claim_count`、`RuntimeLaneClosedError`。

2. `test_close_during_slow_acquire_releases_untracked_claim`:
   - monkeypatch `_try_claim_once_sync` 制造 slow claim（行 1209-1223）。
   - close 与 claim 并发（行 1228）。
   - 结果 `LaneAcquireCancelled(reason="close-during-claim")`（行 1232-1233）。
   - claim count = 0，不泄漏（行 1234）。
   - 新 acquire 被拒（行 1235-1236）。

**判定**: 两个测试仅验证 runtime lane controller 的 close 语义（唤醒 pending、释放 held、拒绝新 claim、不泄漏 claim count）。断言全部基于 `LaneAcquireCancelled`、`LaneAcquired`、`_claim_count`、`RuntimeLaneClosedError`、`RuntimeLaneError` 等 runtime lane 原语。**未将 lane token 升级为 Host truth，未引入 Host EventLog / Run / Attempt / Session 概念。**

### 3.5 旧测试 identity 迁移

#### 3.5.1 `tests/host/test_active_cancel_dispatch.py`

**变更**: 删除 `_register_test_instance` 函数并移除其在 `_mark_waiting_for_lane` 和 `_mark_dispatching` 中的调用。

**Root cause 分析**: Slice 1 引入高熵 `process_start_token` 后，`HostDispatchScheduler.open()` 在打开时为 `host_instance_id="host-active-cancel"` 注册了高熵 token（如 `10936b3fc10c4d67ad042bde169dfa5`）。旧 helper `_register_test_instance` 尝试用固定 `process_start_token="dispatch-host-active-cancel"` 重新注册同一 `host_instance_id`，正确触发了 `HostInstanceIdentityConflictError`。

**生产代码证据**: `dayu/host/dispatch.py` 中 `HostDispatchScheduler.open()` 调用 `_new_dispatch_host_instance_identity(host_handle_id)` 创建 `HostInstanceIdentity`，其中 `owner_host_instance_id` 从 `self._host_handle_id` 写入。因此 production owner id 与注册的 Host instance id 一致。

**Fix 正确性**: 移除手动 `register_current_instance` 调用后，`_mark_waiting_for_lane` 和 `_mark_dispatching` 直接使用 `owner_host_instance_id="host-active-cancel"`（与 `_command_options` 中 `host_handle_id` 一致）。scheduler 已注册的 owner row 被复用。**不掩盖生产 bug**——`HostInstanceIdentityConflictError` 在生产中仍然正确强制 (host_instance_id, pid, process_start_token) 唯一性。

#### 3.5.2 `tests/host/test_dispatch_scheduler.py`

**变更**: `test_default_active_registry_is_scheduler_local` 第二个 scheduler 使用 `host_handle_id="host-test-second"`（区别于默认 `"host-test"`）。

**分析**: 原本两个 scheduler 使用相同 host_handle_id 在同一进程内打开，导致第二个 scheduler 尝试注册同一 (host_instance_id, pid) 的 identity 冲突。生产路径 `open_host` 只打开一个 scheduler，不存在同一 host_handle_id 的两个 scheduler 实例。fix 保持了测试原始意图（不同 scheduler 不共享默认 active registry）同时避开了人工 identity 冲突。

**判定**: **旧测试 identity 迁移正确，未掩盖生产 bug。**

### 3.6 类型与 docstring 约束

**`tests/host/recovery_support.py`**:
- 所有 public 函数有完整中文 docstring（参数、返回值、异常）。
- 所有类有中文概览 docstring。
- 模块级 docstring 声明本模块 "不进入生产代码，不作为 Host recovery truth"。
- 无 `Any`、`object` 使用。类型签名完整。
- `from __future__ import annotations` 已声明。

**`tests/host/test_recovery_multiprocess.py`**:
- 模块级 docstring 声明 recovery truth 边界：`event_type_count` 等 durable 读取 "不把 projection、read model、memory、trace、outbox 或 lane token 当作 recovery truth"。
- 所有函数有 docstring。
- 无 `Any`、`object`、裸容器注解。

**`tests/runtime/test_lane.py`** 新增测试:
- 两个新测试函数均有完整 docstring。
- 无新增类型问题。

**`tests/host/test_active_cancel_dispatch.py`**:
- 移除了 `import os`（清理无用的 import）。
- 移除了 `HostInstanceIdentity`、`register_current_instance` 的无用 import。
- `_mark_waiting_for_lane` 和 `_mark_dispatching` docstring 更新为 "复用 scheduler 注册的 owner row"。

**`tests/host/test_dispatch_scheduler.py`**:
- `_open_scheduler` 新增 `host_handle_id` 参数，有完整 docstring。
- `test_default_active_registry_is_scheduler_local` docstring 更新。

### 3.7 AGENTS.md 约束

- **禁止反向依赖**: 新代码不引入 Engine → Host 或 Host → Engine 反向依赖。
- **禁止 magic 数字**: `_MISSING_OWNER_PID = 999_999`、`_STALE_HEARTBEAT_AT` 定义为模块级具名常量（`recovery_support.py:56-57`），语义明确。作为测试 fault-injection marker 值，不是业务常量。
- **禁止 `Any` / `object`**: 零使用。
- **禁止兼容性代码**: 移除 `_register_test_instance` 是删除过时 helper，不是新增兼容层。
- **分层约束**: `recovery_support.py` 的 durable 读取直接使用 `sqlite3` —— 这是测试 helper，不走 Host durable store 协议。文档明确声明 "不作为 Host recovery truth"。不违反分层边界。

---

## 4. 验证结果

### 4.1 回归测试（3 个 blocker 测试）

```bash
pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_waiting_for_lane_skips_later_dispatch \
      tests/host/test_active_cancel_dispatch.py::test_cancel_run_dispatching_pre_accept_stays_cancelled \
      tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local -q
```
**结果**: `3 passed in 0.24s`

### 4.2 Recovery + Lane 测试

```bash
pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
```
**结果**: `39 passed in 5.25s`

### 4.3 全量 Host 测试

```bash
pytest tests/host -q
```
**结果**: `793 passed, 1 skipped in 43.77s`（实现 artifact 报告 794 passed，差异 1 个 skip 为 real runner 测试因缺 credentials 正常跳过）

### 4.4 类型检查

```bash
python -m pyright dayu/host dayu/runtime tests/host tests/runtime
```
**结果**: `0 errors, 0 warnings, 0 informations`

### 4.5 Diff 检查

```bash
git diff --check
```
**结果**: clean（无空白问题）

### 4.6 Production Code 变更确认

```bash
git diff HEAD -- dayu/
```
**结果**: 空输出，零 production code 变更。

---

## 5. Risk 评估

| Risk | 等级 | 说明 |
|------|------|------|
| 多进程 crash 测试使用 `Process.terminate()` | Low | 跨平台可移植；不使用 `SIGKILL` 或平台特定信号 |
| 显式 stale heartbeat 注入 (`_STALE_HEARTBEAT_AT = "2000-01-01..."`) | Low | 测试 marker，非生产路径 |
| Projection lag 只测试 checkpoint sequence=0 | Low | Plan 明确 "不尝试损坏 projection 表"，corrupted projection 是 projection repair 的 concern |
| 未测试 pid 重用 fingerprinting（boot-id 等） | Info | Plan 明确 deferred：classifier 返回 inconclusive。不属于 Slice 5 scope |
| `wait_for_runtime_lane_claim_ttl_to_expire()` 等待 0.45s | Low | 测试环境确定性强；CI 慢机可能需调参，但 39 passed 证实在当前环境稳定 |

---

## 6. 未覆盖项

- 平台特定 pid start-time / boot-id fingerprinting（plan 明确 deferred）
- 跨机器 / 分布式 recovery（不属于 Phase 11 scope）
- `LaneController.close()` 在 heartbeat task 运行中的并发行为（当前测试已覆盖 close vs acquire 并发，heartbeat vs close 为既有测试覆盖）

---

## 7. 结论

**PASS**。Slice 5 变更范围限于测试层，无 production code / schema / public API / Engine 变更。三项核心验证均以直接证据通过：

1. Multi-process live owner not harmed — 通过 durable EventLog + host_attempts + host_runs 证明无 ATTEMPT_LOST / RUN_RECOVERING / 新 Attempt。
2. Crash recovery final answer — 通过 public `open_host(options)` + `watch_session_events(session_id)` 观察 `HostEventKind.SUCCEEDED` + typed final answer。
3. Projection lag — 注入 checkpoint lag 后 recovery 仍从 durable EventLog / Run / Attempt / dispatch 恢复成功。
4. Lane close/acquire — 仅验证 runtime capacity cleanup，未将 lane token 升级为 Host truth。
5. 旧测试 identity 迁移 — root cause 是测试 helper 使用了过时的固定 process_start_token，非生产 bug。Fix 未掩盖生产 identity 约束。
6. 类型/docstring/AGENTS 约束 — 全部满足。

**Review artifact 路径**: `docs/reviews/phase11-slice5-code-review-ds-20260519.md`
