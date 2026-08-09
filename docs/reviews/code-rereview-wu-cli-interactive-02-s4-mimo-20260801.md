# Code Re-Review — Gateflow S4 (F11/F12) MiMo Independent Re-Review

## Scope

- Mode: current changes (`--base HEAD`)
- Branch: `codex/interactive-oracle`
- Base: `HEAD` (`eadee40932cff2113e944620dcbac1bf187ab799`)
- Output file: `docs/reviews/code-rereview-wu-cli-interactive-02-s4-mimo-20260801.md`
- Included scope: 全部 workspace unstaged/staged changes (5 tracked + 2 untracked production/test files), plan §8, implementation artifact, adjudication artifact
- Excluded scope: DS reviewer 的 re-review artifact（未读取）
- Parallel review coverage: 无

## Re-Review Method

从第一性原理独立核对以下材料，不依赖初审结论：

1. `git diff HEAD` — 全部 5 文件 1665 行 diff
2. `dayu/host/compaction_terminal.py` — 新增 292 行 production（逐行走读）
3. `dayu/host/dispatch.py` — 修改区域（F12 flight 机制逐行走读）
4. `dayu/host/engine_ingest.py` — reactive terminal outcome commit
5. `dayu/host/proactive_compaction.py` — projection 复用 shared owner
6. `tests/host/test_compaction_terminal.py` — 新增 756 行 owner tests
7. `tests/host/test_dispatch_scheduler.py` — F12 tests + crash recovery tests
8. `tests/host/test_engine_ingest_mapping.py` — reactive terminal tests
9. `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` §8
10. `docs/reviews/gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md`
11. `docs/reviews/gateflow-wu-cli-interactive-02-s4-code-review-adjudication-20260801-210745.md`

## 初审后变更确认

`git diff HEAD --stat` 与初审时完全一致：5 tracked 文件 + 2 untracked production/test 文件。
`git log --oneline -1 HEAD` 仍为 `eadee409`，无新 commit。
workspace 中新增的文件仅为 review artifacts（3 份初审 artifact + 本 re-review artifact）。
生产/测试代码在初审后保持不变。裁决未被修改。

## Adversarial 验证：D1 — `_promotion_pending_session_ids` stale entry

### 裁决：`rejected — 确认驳回正确`

### 独立逐行证据

**pending set 的全部写入点**（`dispatch.py` grep 确认仅 4 处引用）：

| 行号 | 操作 | 函数 |
| ---: | --- | --- |
| 1375 | 初始化 `set()` | `__init__` |
| 1583 | `add(session_id)` | `wake_queue_promotion` |
| 4583 | `add(session_id)` | `_enqueue_requeued_promotion` |
| 4449 | `discard(session_id)` | `_promotion_drain_loop` |

**关键事实**：`_signal_pre_start_governance`（line 1763-1797）不修改 `_promotion_pending_session_ids`。
`_run_pre_start_governance_flight`（line 1799-1845）不修改 `_promotion_pending_session_ids`。

**set/queue invariant 证明**：

1. `wake_queue_promotion(S)` (line 1558-1595)：检查 flight → 检查 pending set → 同时 `add` 到 pending set 和 `put_nowait` 到 promotion queue。两个操作之间无 `await`。
2. `_enqueue_requeued_promotion(S)` (line 4567-4584)：同一模式，`add` + `put_nowait` 之间无 `await`。
3. `_promotion_drain_loop` (line 4439-4494)：`get()` dequeue → 立即 `discard` → 调用 `_signal_pre_start_governance`。`discard` 在 `await _signal_pre_start_governance` 之前执行。

**invariant**：`S ∈ pending_set → S ∈ promotion_queue`（直到 drain 消费该 queue entry 时同时 discard）。

**D1 场景分析**："direct flight 可能在 queue entry 尚未被 drain 时先完成"

事件时序：
1. `wake_queue_promotion(S)` → S 加入 pending set + queue，drain task 启动
2. `reconcile_owned_sessions_once` → `_signal_pre_start_governance(S)` 直接调用（不经过 queue）
3. 直接调用创建 flight，返回
4. drain 最终处理 S → `discard` from pending set → `_signal_pre_start_governance(S)` → flight 已存在 → `rerun_requested = True` + `await shield(task)`

步骤 2 的直接调用不消费 queue entry，不修改 pending set。步骤 4 的 drain 正常消费 queue entry 并 discard pending set。没有 stale entry。

**如果 drain 先于直接调用处理 S**：
1. drain `discard` from pending set → `_signal_pre_start_governance(S)` → 创建 flight
2. 直接调用 `_signal_pre_start_governance(S)` → flight 已存在 → `rerun_requested = True`

同样没有 stale entry。

**为什么不应在 `_signal` 中 discard**：
如果在 `_signal_pre_start_governance` 中无条件 `discard`，当 S 同时在 pending set 和 queue 中时，直接调用会 discard pending set，但 queue entry 仍在。后续 drain dequeue 时再次 `_signal`，flight 已存在，`rerun_requested = True`。此时 S 已不在 pending set，但 queue entry 已被消费——没有功能问题，但 `wake_queue_promotion` 的 `if session_id in self._promotion_pending_session_ids: return` 检查会失效，允许同一 Session 在 drain 处理前重复入队。这破坏了 level-bit coalescing 语义。

**结论**：裁决正确。pending set 始终对应尚未消费的真实 queue level signal。direct flight 不修改 pending set，不破坏 set/queue invariant。

## Adversarial 验证：D2 — fresh scheduler crash recovery 测试

### 裁决：`rejected — 确认驳回正确`

### 独立验证

`test_proactive_manifest_crash_resumes_deterministic_next_stage`（line 7086-7232）：

**测试结构**：
- 参数化 `crash_attempt_number` 从 1 到 5，覆盖全部 stage
- `_CrashAtPreparedAttemptCompactor` 在第 N 个 prepared attempt 的 provider await 处注入 crash
- crash 后关闭旧 scheduler，创建 fresh scheduler（不同 `host_handle_id`）
- fresh scheduler 调用 `run_queue_promotion` 恢复

**断言覆盖 owner-level invariant**：

| 断言 | 行号 | 覆盖的 invariant |
| --- | ---: | --- |
| `completed.state.operation_id == operation_id` | 7192 | 同 operation |
| `CONTEXT_COMPACTION_REQUESTED count == 1` | 7194-7198 | 不创建新 request |
| `incomplete.state.prepared_attempt_numbers == prepared_attempts` | 7158 | frozen snapshot |
| `incomplete.state.max_attempt_number == 5` | 7161 | frozen budget |
| `incomplete.state.next_attempt_number == crash_attempt_number + 1` | 7160 | next attempt |
| `_assert_resumed_proactive_request_stage` | 7215 | stage material contract |
| `completed.state.phase is COMPACTED` | 7220 | 最终 terminal |

`test_proactive_exhausted_manifest_fails_same_operation_without_provider`（line 7606）：
- fresh scheduler 断言 exhausted operation 不创建新 operation、不再次调用 provider
- `operation_id` 一致、`prepared_attempt_numbers` 一致

**结论**：D2 要求的 "同 operation/snapshot/budget/next-attempt 的 owner-level 测试" 已由参数化 crash recovery test 完整覆盖。裁决正确。

## Adversarial 验证：D3 — promotion unexpected exception 不 requeue

### 裁决：`rejected — 确认驳回正确，代码事实读取错误`

### 独立逐行证据

`_promotion_drain_loop`（line 4439-4494）的异常处理分支：

```python
# line 4479-4489
except Exception as exc:
    self._requeue_promotion_after_backoff(session_id)  # ← 先 requeue
    _LOGGER.warning(
        "dispatch.queue_promotion.unexpected_exception ...",
        ...
    )
    raise  # ← 再 raise
```

**执行顺序**：
1. `_requeue_promotion_after_backoff(session_id)` (line 4480) — 调用 `loop.call_later` 延迟重新入队
2. `_LOGGER.warning` (line 4481-4488) — 记录 warning
3. `raise` (line 4489) — 重新抛出异常

`_requeue_promotion_after_backoff`（line 4551-4565）：
```python
def _requeue_promotion_after_backoff(self, session_id: str) -> None:
    if self._closed:
        return
    loop = asyncio.get_running_loop()
    loop.call_later(
        self._local_execution.dispatch_poll_interval_seconds,
        self._enqueue_requeued_promotion,
        session_id,
    )
```

`_enqueue_requeued_promotion`（line 4567-4584）：按同一 flight/pending/queue 规则重新投递。

**异常传播路径**：`raise` → `_promotion_drain_loop` task 结束 → `_start_critical_task` 的 supervisor 收到异常 → shared health 进入 unavailable。

**与 reviewer 描述的差异**：reviewer 声称代码是 "log + continue（不 retry）"。实际代码是 `requeue + warning + raise`。裁决的 "代码事实读取错误" 判定正确。

**结论**：D3 裁决正确。异常分支先 requeue 再 raise/fatal，不是 reviewer 描述的不 retry。

## F11/F12 Owner Invariant 独立确认

### F11: shared terminal transaction owner

1. **覆盖完整性**：AST inventory test 固定 dispatch=4, engine=1, proactive=1。逐行确认每个 request-backed terminal commit 点在同一 write transaction 内首先调用 `begin_compaction_terminal_commit_in_transaction`。
2. **late loser 零副作用**：每个 caller 的 `CompactionTerminalClosed` 处理分支返回 no-op，不写 artifact/descriptor/rejected/terminal/fallback/start。测试断言 `cursor_after_winner` 后零新增事件。
3. **INVALID_MULTIPLE fail closed**：所有 caller 显式 `raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)`。测试注入 2 terminal 断言异常抛出且不追加第三。
4. **projection 不产生第二 owner**：`read_proactive_compaction_projection` 调用 shared owner 后传入 `_project_state`。旧 `terminal_count` 已删除。AST inventory 固定 `terminal_count` 不在 source 中。

### F12: scheduler-local sole flight

1. **信号合并**：`wake_queue_promotion` / `_enqueue_requeued_promotion` / `reconcile_owned_sessions_once` 都收敛到 `_signal_pre_start_governance`。已有 flight → `rerun_requested = True`。已在 pending set → 不重复入队。
2. **exit race 无丢失**：flight 的 "check bit → delete entry" 区间无 `await`（line 1839-1841）。`call_soon` 边界测试验证 exit-boundary signal 启动新 flight。
3. **caller cancel shield**：`asyncio.shield(flight.task)` 阻止 cancel 传播。测试验证 caller cancel 后 `flight.task.done() is False`。
4. **scheduler close**：`close()` 取消 `_active_tasks` 含 flight tasks。测试验证 close 后 `_pre_start_flights == {}`。
5. **fresh owner crash recovery**：参数化测试覆盖 5 个 crash point，断言同 operation/snapshot/budget/next-attempt。
6. **live compactor barrier**：`_BlockingAfterManifestCompactor` 冻结 provider await。测试验证 barrier 期间 `provider_calls == 1`、`prepared_requests == 1`、`CONTEXT_COMPACTION_REQUESTED == 1`。释放后 `terminal_count == 1`、`prepared_attempt_numbers == (1,)`。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

与初审一致，无新增：

1. **terminal owner 分页扫描超长 Run**：现有 EventLog primitive 上的正确实现；plan 明确禁止本 slice 新增 index/schema/migration。非 correctness blocker。
2. **reconciliation `dispatched` 使用 flight OR 归约**：observability 语义差异，不改变 durable truth。
3. **scheduler-local flight 进程崩溃后丢失**：intended recovery boundary，fresh owner 从 durable request/manifest 恢复，已有参数化 owner test。
4. **F12 design/README 尚未同步**：按 accepted plan 留给 S6。
5. **HEAD 相邻 watchdog token exact-count 竞态**：S3 已记录，S4 未触及 cancel owner。

## Gate Decision

- D1：确认驳回正确。pending set 始终对应尚未消费的真实 queue level signal；`_signal_pre_start_governance` 不修改 pending set；direct flight 不破坏 set/queue invariant。
- D2：确认驳回正确。`test_proactive_manifest_crash_resumes_deterministic_next_stage` 参数化覆盖 5 个 crash point，断言同 operation/snapshot/budget/next-attempt。
- D3：确认驳回正确。`except Exception` 分支先 `_requeue_promotion_after_backoff` 再 `raise`，不是 reviewer 描述的 "log + continue"。
- F11/F12 owner invariant：独立确认全部覆盖。
- 初审后生产/测试代码未变，仅新增 review artifacts。
- 裁决未被修改。

结论：`S4 code review re-review pass`。裁决正确，无遗漏，无新增 finding。Next gate 为 DS re-review 后的 S4 commit。
