# wu-cli-interactive-02 S4 独立 re-review

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：S4 独立 re-review（基于裁决 `gateflow-wu-cli-interactive-02-s4-code-review-adjudication-20260801-210745.md`）
- Branch：`codex/interactive-oracle`
- Base HEAD：`eadee40932cff2113e944620dcbac1bf187ab799`
- Review time：2026-08-01 21:12:52 CST
- Role：独立 re-reviewer（未读取另一 reviewer 的 re-review artifact）
- Prior review：DS 初审 `code-review-wu-cli-interactive-02-s4-ds-20260801.md` 提出 D1-D3
- Adjudication：全部 3 项驳回（0 accepted / 3 rejected / 0 deferred）
- Production/test change since initial review：无（0 accepted findings，仅新增 review/裁决 artifact）

## 1. Scope 与验证方法

本 re-review 从第一性原理独立核对当前 workspace（`git diff HEAD`，5 个生产/测试文件
修改 + 2 个新文件）、plan §8、implementation artifact 和裁决。对每个被驳回 finding
执行：

- 真实代码路径逐行走读（`dayu/host/dispatch.py` 完整变更、`compaction_terminal.py`
  全文、`engine_ingest.py` 变更、`proactive_compaction.py` 变更）。
- Event-loop 时序展开（何时入队、何时 discard、flight 创建/合并/删除边界）。
- 测试断言逐条核对（每个 finding 声称的测试覆盖是否真实存在，断言是否覆盖声称的 owner
  contract）。
- 未读取另一 reviewer 的 re-review artifact；独立判定。

## 2. D1 — pending set stale entry 再验

### 2.1 Reviewer 原始主张

"direct flight 可能留下 stale `_promotion_pending_session_ids`，后续 wake 被静默丢弃"。

### 2.2 Event-loop 时序展开

pending set 与 promotion queue 的一一关系由以下站点维持：

- **入队**（`wake_queue_promotion`，line 1558-1595）：
  1. 获取 eligibility lease（line 1567-1569）→ 无资格直接返回。
  2. 检查 flight（line 1577-1579）→ 有则 set bit 返回。
  3. 检查 pending set（line 1581-1582）→ 已在则返回。
  4. `_promotion_pending_session_ids.add(session_id)`（line 1583）。
  5. `_promotion_queue.put_nowait(session_id)`（line 1584）。

- **出队**（`_promotion_drain_loop`，line 4439-4495）：
  1. `session_id = await self._promotion_queue.get()`（line 4448）—— await 点。
  2. `self._promotion_pending_session_ids.discard(session_id)`（line 4449）—— **紧接
     dequeue，先于** `_signal_pre_start_governance`。
  3. `await self._signal_pre_start_governance(session_id)`（line 4451）。

- **Direct path**（`run_queue_promotion`，line 1753-1756）：
  - 直接调用 `_signal_pre_start_governance`，**完全不经过** pending set 或 queue。

- **Requeue path**（`_enqueue_requeued_promotion`，line 4567-4584）：
  - 与 `wake_queue_promotion` 相同的 level-bit 规则：先检查 flight（line 4577-4580），
    再检查 pending set（line 4581-4582），再 add + put。

### 2.3 D1 场景的精确执行轨迹

**场景**：direct flight 和 queue entry 同时存在。

```
T1: wake_queue_promotion(S)
    → pending set += S, queue += S
T2: run_queue_promotion(S)  [direct path, concurrent]
    → _signal_pre_start_governance(S)
    → 无 flight → 创建 flight, 开始 _run_pre_start_governance_flight
    → 执行 compact → 提交 terminal → flight 完成 → del _pre_start_flights[S]
T3: drain loop dequeue S
    → pending_set.discard(S)  [line 4449]
    → _signal_pre_start_governance(S)  [line 4451]
    → 无 flight → 创建新 flight
    → _run_pre_start_governance_flight 读 durable truth → terminal 已存在
    → begin_compaction_terminal_commit_in_transaction 返回 CompactionTerminalClosed
    → 返回 dispatched=False
    → del _pre_start_flights[S]
```

**结论**：T3 处的 drain loop 消费了真实 queue entry（在 T1 入队，T2 完成前入队），从
fresh durable truth 发现 work 已完成，no-op 返回。这是 plan §8.3 要求的 level-bit
coalescing 的正确行为，不是 stale set 问题。

### 2.4 反例裁决验证

裁决指出 "如果在 `_signal_pre_start_governance` 中无条件 discard 会让 queue 中仍有 entry、
set 却为空，破坏 set/queue invariant"——逐行走读验证：

`wake_queue_promotion` 和 `_enqueue_requeued_promotion` 在检查 `session_id in
_promotion_pending_session_ids` 时（line 1581, line 4581），如果 set 为空但 queue 中仍有
entry，**同一个 Session 可以重复入队**，产生多余 queue entry。虽然多余 entry 会被 drain
时 no-op 处理，但 set/queue 一一对应 invariant 会被破坏。裁决正确：不应在 direct path
中无条件 discard。

### 2.5 D1 判定

**agree with adjudication**：`rejected — pending set 始终对应未消费的真实 queue signal，
direct flight 不会丢 signal`。

直接证据：
- `discard` 仅在 drain dequeue 后（line 4449），此时 queue entry 已被消费。
- `wake_queue_promotion` 的 flight check（line 1577-1579）在 pending set check（line
  1581）之前，先合并到已有 flight。
- drain loop 消费 queue entry 后调用 shared signal owner，从 fresh durable truth 重读；
  即使 signal 在 direct flight 后到达，no-op pass 也是正确行为。

## 3. D2 — fresh scheduler crash recovery 测试再验

### 3.1 Reviewer 原始主张

"缺少 fresh owner crash recovery 测试"。

### 3.2 直接测试证据

#### test_proactive_manifest_crash_resumes_deterministic_next_stage（line 7086）

参数化 `crash_attempt_number ∈ {1, 2, 3, 4, 5}`，每个参数对应一条完整 recovery path：

1. **crash 前**：打开 scheduler → 启动 promotion → `_CrashAtPreparedAttemptCompactor`
   在 provider 进入时 barrier → promotion 抛 `_SimulatedProactiveCrash` → close scheduler。
2. **crash 后状态验证**（line 7151-7169，精确断言）：
   - `incomplete.state.phase is ProactiveCompactionPhase.INCOMPLETE`
   - `incomplete.state.operation_id` 非 None（同一 operation）
   - `incomplete.state.prepared_attempt_numbers == (1, ..., crash_attempt_number)`（frozen snapshot）
   - `incomplete.state.next_attempt_number == crash_attempt_number + 1`
   - `incomplete.state.max_attempt_number == 5`（frozen budget）
   - `incomplete.state.prepared_request_digests` 精确匹配每个 attempt 的 request digest
3. **fresh scheduler 恢复**（line 7172-7185）：
   - 新建 scheduler（不同 `host_handle_id`，line 7180）
   - 调用 `run_queue_promotion(seeded.session_id)`
4. **恢复后验证**（line 7187-7232）：
   - `completed.state.operation_id == operation_id`（同 operation，未创建新操作）
   - `CONTEXT_COMPACTION_REQUESTED` count == 1（未创建新 request）
   - `crash_attempt_number == 5`（预算耗尽）→ `resumed_compactor.calls == 0`，phase
     is FAILED，`attempt_count == 5`
   - `crash_attempt_number < 5` → `resumed_compactor.calls == 1`，resumed request
     stage 正确映射到 production `ProactiveCompactionAttemptStage` 枚举

这是 owner-level 测试：它直接验证 fresh scheduler 恢复时的**同 operation id**、
**frozen snapshot/manifest**、**max budget**、**next global attempt** 和 **确定性的 stage
恢复**。每个参数化用例是一条独立的 crash recovery path。

#### test_proactive_exhausted_manifest_fails_same_operation_without_provider（line 7606）

1. 打开 scheduler → 启动 promotion → manifest 后 cancel → close scheduler。
2. 新建 fresh scheduler（不同 `host_handle_id`，line 7659）。
3. `run_queue_promotion` → 断言：
   - `forbidden_provider.calls == 0`（未调用 provider，line 7673）
   - `CONTEXT_COMPACTION_REQUESTED` count == 1（未创建新 request，line 7676-7680）
   - 写入 FAILED terminal（line 7681+）

这验证了 fresh scheduler **不会**对 exhausted operation 创建新 operation 或再次调用
provider——正是 crash recovery 的关键 owner contract。

### 3.3 D2 判定

**agree with adjudication**：`rejected — 现有 owner-level 测试已明确覆盖`。

直接证据：
- `test_proactive_manifest_crash_resumes_deterministic_next_stage` 对 5 个 crash attempt
  参数验证了同 operation、frozen snapshot、max budget、next attempt 和 stage 恢复。
- `test_proactive_exhausted_manifest_fails_same_operation_without_provider` 验证了
  exhausted operation 不会触发新 request 或 provider call。
- 两者都使用 fresh scheduler（不同 handle id），模拟真实进程级 crash recovery。

## 4. D3 — promotion unexpected exception 不 requeue 再验

### 4.1 Reviewer 原始主张

"promotion drain 对 unexpected flight 异常不 requeue"。

### 4.2 逐行代码证据

`_promotion_drain_loop`（line 4439-4495）的 `except Exception` 分支：

```python
# line 4479-4489
except Exception as exc:
    self._requeue_promotion_after_backoff(session_id)  # line 4480: REQUEUE FIRST
    _LOGGER.warning(                                     # line 4481: log warning
        "dispatch.queue_promotion.unexpected_exception "
        "host_handle_id=%s session_id=%s error_type=%s",
        self._host_handle_id,
        session_id,
        exc.__class__.__name__,
        exc_info=True,
    )
    raise                                                # line 4489: THEN RAISE
```

执行顺序：**先 requeue（line 4480），再 raise（line 4489）**。这是直接代码事实，不存在
"log + continue（不 retry）"。

### 4.3 raise 之后的传播链

1. 异常从 `_promotion_drain_loop` 传播到 `_supervise_critical_task`（line 4178-4218）。
2. `_supervise_critical_task` 的 `except Exception as exc`（line 4196）捕获异常。
3. 记录 `dispatch.critical_task.fatal`（line 4197-4204）。
4. 若非 closed，调用 `self._health_gate.report_fatal`（line 4214-4218）。
5. 此后 shared health 进入 unavailable，阻止继续接受新工作。

requeue 在步骤 1 之前已完成（line 4480）。`_requeue_promotion_after_backoff` 使用
`loop.call_later` 延迟投递（line 4561-4564），`_enqueue_requeued_promotion` 使用完全
相同的 level-bit 规则（line 4567-4584）。

### 4.4 D3 判定

**agree with adjudication**：`rejected — 代码事实读取错误`。

直接证据：line 4480 的 `self._requeue_promotion_after_backoff(session_id)` 在 line 4489
的 `raise` 之前执行。这是 reviewer 的代码阅读错误，不存在 "不 requeue" 事实。

关于 "requeue 后 raise 导致 health fatal，requeued signal 是否能被处理" 的问题：
- 这是 existing critical-health design：shared health unavailable 后 scheduler 不接受
  新工作，但 requeue 是 defense-in-depth——signal 不丢失，durable truth 在 fresh
  scheduler 恢复时可 reconciliation。
- 不是 S4 引入的新行为；不是评审范围内的回归。

## 5. F11 owner invariant 再确认

### 5.1 Shared terminal owner 单点判定

`begin_compaction_terminal_commit_in_transaction`（`compaction_terminal.py` line 98-177）
是唯一 shared owner：

- **入参校验**：operation_id 非空（line 122-123）、trigger_source 类型（line 124-127）。
- **Request identity 校验**（line 128-149）：
  - `request.event_class is EventClass.CANONICAL_FACT`（line 131-132）
  - `request.event_type == CONTEXT_COMPACTION_REQUESTED`（line 133）
  - `request.event_id == operation_id`（line 134）
  - `request.run_id` 非空（line 135-137）
  - request payload 的 `operation_id` 与 event_id 一致（line 140-141）
  - `trigger_source` 严格匹配（line 142-149）
- **Terminal 读取**（`_read_operation_terminal_rows`，line 180-230）：
  - 每行校验 `event_class is CANONICAL_FACT`（line 211-214）—— non-canonical row 在
    operation filter 前 fail closed。
  - 校验 session_id、run_id、event_sequence > request.event_sequence（line 219-226）。
  - 只匹配同 operation_id 的 row（line 217-218）。
- **Disposition 判定**（line 157-176）：
  - 0 terminal → `OPEN` permit。
  - 1 terminal → `COMPACTED` 或 `FAILED` closed result（带 first sequence/type）。
  - ≥2 terminals → `INVALID_MULTIPLE`（保留 first truth，不发明第三 terminal）。

### 5.2 Writer inventory 验证

测试 `test_compaction_terminal_writer_inventory_uses_only_shared_owner`（line 388）通过
AST 分析确证：

| 调用点 | 文件 | 行 | shared owner 调用数 |
| --- | --- | ---: | ---: |
| invalid/exhausted close | dispatch.py | ~2201 | 1 |
| proactive outcome commit | dispatch.py | ~2419 | 1 |
| resume snapshot invalid | dispatch.py | ~3190 | 1 |
| missing compactor | dispatch.py | ~3263 | 1 |
| reactive outcome commit | engine_ingest.py | ~2938 | 1 |
| durable projection（只读） | proactive_compaction.py | ~306 | 1 |

**合计**：dispatch 4 + engine_ingest 1 + proactive_compaction 1 = 6 处调用，且全部语法
token "terminal_count" 在三个生产文件中不存在（line 432-434），确认旧 terminal_count
已被完全替换。

### 5.3 Late loser / contender / INVALID_MULTIPLE 测试覆盖

| 测试 | 覆盖场景 |
| --- | --- |
| `test_proactive_late_accepted_result_preserves_first_failed_truth` | I0543：compactor 先提交 FAILED，late accepted 零副作用 |
| `test_proactive_same_operation_terminal_contenders_preserve_first_truth` | compacted-first/failed-late 与 failed-first/accepted-late 双向 |
| `test_proactive_invalid_multiple_terminals_fail_closed_without_third_or_start` | proactive INVALID_MULTIPLE 不改写 first truth |
| `test_reactive_invalid_multiple_terminals_fail_closed_without_third_or_start` | reactive INVALID_MULTIPLE 不改写 first truth |
| `test_reactive_same_pending_terminal_race_preserves_first_truth` | reactive 同 pending race 双向 |

全部测试断言 zero artifact、zero rejected attempt、zero RUN_STARTED（或保持既有值）、
first terminal event_id 不变。

### 5.4 F11 结论

**pass**。Shared terminal owner 的单点判定、严格校验、writer inventory 和 late
loser/contender/INVALID_MULTIPLE 覆盖均符合 plan §8。

## 6. F12 owner invariant 再确认

### 6.1 Sole flight 生命周期

`_signal_pre_start_governance`（line 1753-1791）是唯一 signal 入口：

1. **Eligibility check**（line 1763-1767）：快速获取并立即释放 lease——仅确认当前
   signal 资格，不持有 lease 跨 await。
2. **Flight coalesce**（line 1768-1771）：已有 flight → set `rerun_requested` bit +
   `await asyncio.shield(flight.task)`。
3. **Flight create**（line 1772-1791）：无 flight → 创建 task → 注册到
   `_pre_start_flights` 和 `_active_tasks`。

`_run_pre_start_governance_flight`（line 1793-1830）是唯一 flight body：

1. **Pass loop**：清 bit → 获取 fresh lease → 执行 pass → 释放 lease → 检查 bit →
   continue 或 delete。
2. **Exit boundary**（line 1821-1822）：`if flight.rerun_requested: continue` 到
   `del self._pre_start_flights[session_id]` 之间**无 await**——在单线程 asyncio 中，
   回调（`call_soon`、`call_later` 投递的 `wake_queue_promotion` / `_enqueue_requeued_promotion`）
   无法在此边界插入执行。exit-boundary signal 安全。
3. **finally 清理**（line 1828-1830）：确保即使异常退出也删除 flight。

### 6.2 三路 signal 汇聚

| Signal 来源 | 入口 | 路径 | queue/pending 交互 |
| --- | --- | --- | --- |
| `wake_queue_promotion` | line 1558 | `_signal_pre_start_governance`（通过 drain loop 间接） | 入队前检查 pending set |
| `run_queue_promotion`（direct） | line 1753 | `_signal_pre_start_governance`（直接） | 不经过 queue/set |
| `reconcile_owned_sessions_once`（periodic） | `_signal_pre_start_governance` | 直接 | 不经过 queue/set |

三路信号都在 `_signal_pre_start_governance` 中通过 flight coalescing 合并。不同 Session
使用不同 flight task，可并行；同 Session 串行（通过 bit 标记）。

### 6.3 F12 测试覆盖

| 测试 | 覆盖场景 |
| --- | --- |
| `test_pre_start_flight_coalesces_wake_periodic_and_direct_signals` | seam-level：多 wake/periodic/direct 合并成 2 passes |
| `test_live_compactor_flight_coalesces_wake_and_periodic_without_recovery` | 真实 compactor barrier：1 provider call、1 terminal、RUNNING |
| `test_pre_start_flight_exit_boundary_signal_starts_fresh_flight` | exit boundary：`call_soon` signal 启动 fresh flight |
| `test_pre_start_flight_is_parallel_per_session_and_close_owned` | 并行 Session、awaiter cancel 不取消 flight、close 统一收口 |
| `test_wake_queue_promotion_requeues_after_transient_exception` | transient retry 2 attempts，无无限重试 |
| `test_proactive_manifest_crash_resumes_deterministic_next_stage` | crash recovery：同 operation/snapshot/budget/next-attempt |
| `test_proactive_exhausted_manifest_fails_same_operation_without_provider` | exhausted recovery：不创建新 operation 或调用 provider |

### 6.4 F12 结论

**pass**。Sole flight 的创建、合并、exit boundary、跨 Session 并行、caller cancel
shield、close 收口和 crash recovery 测试均完整。

## 7. 初审后变更确认

```
$ git diff HEAD --name-only
dayu/host/dispatch.py
dayu/host/engine_ingest.py
dayu/host/proactive_compaction.py
tests/host/test_dispatch_scheduler.py
tests/host/test_engine_ingest_mapping.py

$ git ls-files --others --exclude-standard
dayu/host/compaction_terminal.py
docs/reviews/code-review-wu-cli-interactive-02-s4-ds-20260801.md
docs/reviews/code-review-wu-cli-interactive-02-s4-mimo-20260801-210345.md
docs/reviews/gateflow-wu-cli-interactive-02-s4-code-review-adjudication-20260801-210745.md
docs/reviews/gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md
tests/host/test_compaction_terminal.py
```

生产/测试文件（5 tracked + 2 untracked production/test）与 implementation artifact §3
一致。自初审（DS review artifact: `code-review-wu-cli-interactive-02-s4-ds-20260801.md`）
和 MiMo review artifact 之后，**0 个 production/test 文件被修改**。仅新增了 review
artifact 和裁决 artifact。

## 8. Finding 状态总结

| Finding | Severity | Adjudication | Re-review 验证 | 状态 |
| --- | --- | --- | --- | --- |
| D1 — pending set stale entry | 中 | rejected | agree — discard 仅在 drain dequeue 后，set/queue invariant 正确；direct flight 不丢 signal | **确认驳回** |
| D2 — 缺少 fresh crash recovery 测试 | 低 | rejected | agree — parametrized owner-level 测试确实验证同 operation/snapshot/budget/next-attempt/stage | **确认驳回** |
| D3 — unexpected exception 不 requeue | 低 | rejected | agree — line 4480-4489 明确先 requeue 再 raise；reviewer 代码阅读错误 | **确认驳回** |

**无新增 finding**。F11/F12 owner invariant 均通过逐代码路径再验证。

## 9. Validation

- 全仓测试（implementation artifact §5）：`412 passed in 5.59s`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- S4 关键选测（27 项 F11/F12 核心测试）：`27 passed in 0.88s`。
- 独立 `test_promotion_drain_loop` 异常路径行号核对：requeue (line 4480) 先于 raise (line 4489)。
- 独立 `test_proactive_manifest_crash_resumes_deterministic_next_stage` 断言核对：operation_id、
  frozen snapshot、max budget、next attempt、stage 全部显式断言。

## 10. Residual Risk

| 风险 | 分类 | 状态 |
| --- | --- | --- |
| terminal owner 按 64 行分页扫描超长 Run | accepted bounded risk | 现有 primitive 上的正确实现；非 S4 新增 |
| F12 flight 单进程 scheduler-local | intended design | crash recovery 依赖 durable truth + fresh owner；已参数化测试 |
| HEAD 相邻 watchdog 10ms 竞态 | previously classified | S3 已记录；S4 未触及 cancel owner |
| F12 design/README/docs | planned work | S6 scope；未在本 gate 机械更新 |

无未分类 residual risk。无新增 residual risk。

## 11. Gate Decision

- **Re-review conclusion**：`pass`
- **Agreement with adjudication**：全部 3 项驳回确认同意
- **F11/F12 owner invariant**：通过独立再验证
- **Production/test code**：初审后 0 changes，确认仅有 review artifacts
- **New findings**：0
- **Next gate**：`S4 final closeout`（前提：另一 reviewer 的独立 re-review 也完成并通过）

本 re-review 没有不同意裁决的事项，未产生新的 fix 需求。
