# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `eadee409` (HEAD)
- Output file: `docs/reviews/code-review-wu-cli-interactive-02-s4-ds-20260801.md`
- Included scope: 全部未提交 workspace changes（5 modified + 2 new files）
- Excluded scope: 无

### 变更文件

| 文件 | 状态 | 类别 |
| --- | --- | --- |
| `dayu/host/compaction_terminal.py` | new | F11 shared terminal owner |
| `dayu/host/dispatch.py` | modified | F11 writer integration + F12 sole flight |
| `dayu/host/engine_ingest.py` | modified | F11 reactive writer integration |
| `dayu/host/proactive_compaction.py` | modified | F11 projection consumer |
| `tests/host/test_compaction_terminal.py` | new | F11 shared owner unit tests |
| `tests/host/test_dispatch_scheduler.py` | modified | F11/F12 integration tests |
| `tests/host/test_engine_ingest_mapping.py` | modified | F11 reactive race tests |

### 审查方法

沿真实代码路径逐行走读了全部 production diff、新增模块和测试。对每个 shared owner call site 做了 transaction-local 线性化点验证；对每个 flight lifecycle 阶段做了 race condition / cancel / close 路径遍历。同步验证了 AGENTS.md 语义所有权约束和编码硬约束。

## Findings

### 1-未修复-中-`_promotion_pending_session_ids` stale entry 可导致 wake signal 被静默丢弃

- **入口/函数**: `HostDispatchScheduler.wake_queue_promotion` → `_signal_pre_start_governance` flight create path
- **文件(行号)**: `dayu/host/dispatch.py:1577-1583`（wake 端 pending set 检查）、`dayu/host/dispatch.py:1783-1797`（signal 端 flight 创建，未清理 pending set）
- **输入场景**:
  1. `wake_queue_promotion(S)` 将 S 加入 `_promotion_pending_session_ids` 并入队 promotion queue（行 1583-1584）
  2. `run_queue_promotion(S)` 被直接调用，`_signal_pre_start_governance` 创建 flight 并执行完成，flight 自我清理（行 1841 `del self._pre_start_flights[S]`）
  3. `wake_queue_promotion(S)` 再次被调用
  4. 检查 flight → `None`（已清理）→ 检查 `_promotion_pending_session_ids` → S 存在（stale）→ 直接 return，不投递 signal
- **实际分支**: 行 1581 `if session_id in self._promotion_pending_session_ids: return` — 此检查的意图是防止重复入队，但未感知 flight 已绕过队列直接创建并完成，导致 set 中的 stale entry 把合法 wake signal 当作重复入队而丢弃。
- **预期行为**: step 4 的 wake signal 应能触发新的 flight 或至少入队等待 drain loop 处理。
- **实际行为**: signal 被静默丢弃。只有在 drain loop 消费到 step 1 产生的原始队列条目（行 4449 `self._promotion_pending_session_ids.discard(session_id)`）之后，后续 wake 才能恢复正常入队。
- **直接证据**:
  - `wake_queue_promotion`（行 1577-1584）和 `_signal_pre_start_governance`（行 1783-1797）各自独立操作 `_pre_start_flights`，但只有 `wake_queue_promotion` / `_enqueue_requeued_promotion` 检查 `_promotion_pending_session_ids`
  - `_signal_pre_start_governance` 创建 flight 时不调用 `self._promotion_pending_session_ids.discard(session_id)`
  - `_run_pre_start_governance_flight` 的 cleanup（行 1841-1845）只删除 `_pre_start_flights` entry，不清理 `_promotion_pending_session_ids`
- **影响**: wake signal 延迟至多一个 drain loop 迭代周期（production 中由 `dispatch_poll_interval_seconds` 决定）。在 drain loop 繁忙或有大量排队 Session 时，延迟可能更长。最坏情况下 compaction 触发被推迟，但不丢失 — 下一次 periodic reconciliation 会重新评估。
- **建议改法和验证点**:
  - 在 `_signal_pre_start_governance` 创建新 flight 后（行 1794 之后），增加 `self._promotion_pending_session_ids.discard(session_id)`
  - 在 `_run_pre_start_governance_flight` cleanup finally block（行 1843-1845）中同样 discard
  - 验证：构造 `wake_queue_promotion` → `run_queue_promotion` → `wake_queue_promotion` 序列，断言第三次 `wake_queue_promotion` 能成功入队或触发 rerun
- **修复风险（低）**: discard 是幂等操作，不影响正确性；改动仅涉及 scheduler-local in-memory set，不触及 durable state
- **严重程度（中）**: wake signal 可能被延迟，但不丢失

### 2-未修复-低-缺少显式的 fresh owner crash recovery 测试

- **入口/函数**: `HostDispatchScheduler._signal_pre_start_governance` / `reconcile_owned_sessions_once`
- **文件(行号)**: `dayu/host/dispatch.py:1783-1797`、`dayu/host/dispatch.py:3990-4013`
- **输入场景**: scheduler 进程崩溃时 `_pre_start_flights` dict 随进程丢失；新 scheduler 启动后 periodic reconciliation 或 promotion drain 需要从 durable truth 恢复
- **实际分支**: 当前测试覆盖了 live compactor coalesce（`test_live_compactor_flight_coalesces_wake_and_periodic_without_recovery`）、exit boundary（`test_pre_start_flight_exit_boundary_signal_starts_fresh_flight`）、caller cancel / close（`test_pre_start_flight_is_parallel_per_session_and_close_owned`），但没有测试模拟 scheduler 崩溃后新 scheduler 从 durable state 恢复的场景
- **预期行为**: 新 scheduler 的 `_pre_start_flights` 为空，`reconcile_owned_sessions_once` 对 active RW Session 创建新 flight，flight 从 durable truth（EventLog）读取既有 operation 状态并正确恢复
- **实际行为**: 行为依赖 `_pre_start_flights` 是纯内存结构的特性 — 进程崩溃自然清零，无需显式恢复逻辑。但缺少测试意味着无法回归验证：future change 如果向 flight 加入需要显式恢复的 durable marker，不会被测试捕获。
- **直接证据**: 全部 F12 新增测试用例中无 crash-restart 场景；`_PreStartGovernanceFlight` 是纯 `slots=True` dataclass 无序列化/持久化路径
- **影响**: 当前无功能影响（in-memory state 天然支持 crash recovery）；future change 风险
- **建议改法和验证点**: 可选：增加一个测试用例，创建 scheduler、执行部分 flight、close scheduler、新建 scheduler、验证新 flight 正确从 durable truth 恢复。或至少在 F12 design doc 中显式记录"crash recovery 依赖 in-memory state 的天然丢失特性，不需要额外恢复逻辑"
- **修复风险（低）**: 仅增加测试
- **严重程度（低）**: 当前无功能缺陷，仅测试覆盖缺口

### 3-未修复-低-`_promotion_drain_loop` 收到 flight 异常时会丢失原始 session_id 的重试入队

- **入口/函数**: `HostDispatchScheduler._promotion_drain_loop`
- **文件(行号)**: `dayu/host/dispatch.py:4446-4481`
- **输入场景**: drain loop 从 `_promotion_queue` 取出 session_id，调用 `_signal_pre_start_governance(session_id)` 时 flight 抛出非 `RuntimeError`、非 `HostTransactionRetryExhaustedError` 的异常（例如 `HostDurableError` from INVALID_MULTIPLE）
- **实际分支**: 行 4451 `await self._signal_pre_start_governance(session_id)` 抛出异常后，`except RuntimeError`（行 4452）和 `except HostTransactionRetryExhaustedError`（行 4469）都不匹配，异常传播到 `_promotion_drain_loop` 的顶层 `try`（行 4446），被外层 `except asyncio.CancelledError`（行 4475-4477）或 bare `except Exception`（行 4477-4481）捕获
- **预期行为**: `HostDurableError` from INVALID_MULTIPLE 是 durable state 已损坏的明确信号，应记录并停止该 Session 的 promotion retry，不应 crash 整个 drain loop
- **实际行为**: 行 4477 `except Exception:` 捕获后仅 log warning 并 `continue`（进入下一轮 `while not self._closed` 循环）。session_id 已被 `_promotion_pending_session_ids.discard`（行 4449），但 `_requeue_promotion_after_backoff` 未被调用。这意味着该 Session 的 promotion 永久停止（直到下次 periodic reconciliation 或外部 wake）。
  - 对于 INVALID_MULTIPLE 场景，这是**正确行为**：durable state 已损坏，不应重试。
  - 但对于其他未预期的 flight 异常（比如 transient durable error 被错误包装），会意外停止 promotion。
- **直接证据**: 行 4451-4481 的异常处理链：`RuntimeError` → retry；`HostTransactionRetryExhaustedError` → retry；其他 `Exception` → log + continue（不 retry）
- **影响**: 对 INVALID_MULTIPLE 场景是正确的 fail-stop；对其他未预期异常可能导致 promotion 静默停止。该行为与修改前一致（旧 `run_queue_promotion` 的异常也会传播到 drain loop），不是 S4 引入的回归。
- **建议改法和验证点**: 可在 `_signal_pre_start_governance` 的 docstring 中显式说明哪些异常是可恢复的（transient）、哪些是 terminal（INVALID_MULTIPLE、request identity invalid）。长期建议将 terminal error 和 transient error 区分为不同异常类型。
- **修复风险（低）**: docstring 变更无风险；异常类型重构风险中等，超出本 work unit 范围
- **严重程度（低）**: 行为与修改前一致，非 S4 引入

## Open Questions

1. **`_promotion_pending_session_ids` 是否应该在 `_signal_pre_start_governance` 中也做 discard？** — Finding 1 分析了 stale entry 问题。discard 是幂等操作，从 `_signal_pre_start_governance` 创建 flight 时清理 pending set 不会引入新风险。但当前实现中 drain loop 是唯一消费者，discard 放在 drain loop 侧保证了 pending set 和 queue 的严格对应。在 `_signal_pre_start_governance` 中添加 discard 会打破这个 invariant（pending set 可能为空但 queue 中仍有条目），需要考虑是否可接受。

2. **`read_proactive_compaction_projection` 中 `terminal_state` 为 `None` 但存在 terminal rows 时的行为是否充分验证？** — 当 `operation_id` 为 `None` 时跳过 shared owner 调用，`terminal_state` 保持 `None`。如果有孤儿 terminal rows（无对应 request），`_project_state` 会在 `_required_operation_owner` 查找时因 operation_id 不在 `operation_owners` 中而抛出 `HostDurableError`。该路径在 `test_arbitrary_event_cannot_act_as_compaction_request` 中有部分覆盖（验证了非 request event 被拒绝），但没有专门测试"无 request 但有 orphan terminal"的场景。当前代码路径的最终行为是正确的（fail closed），但缺少显式测试。

## Residual Risk

1. **Test coverage of drain-replaced assertions**: 4 个已有测试从 `assert (await scheduler.drain_once()).dispatched == 1` 改为 `await _wait_for_event_count(...)` / `await _wait_for_final_request_count(...)`。新断言验证了 durable side effect（event 写入、worker accept）而不再是 drain 机制本身。由于 F12 将 dispatch 收敛到 flight 内部而非 drain loop，旧断言不再适用。新断言正确验证了最终状态，但不验证"恰好一次 drain"的中间步骤 — 这个中间步骤在 F12 架构下已无意义。

2. **Bounded page size for terminal reads**: `compaction_terminal.py` 使用 `_READ_PAGE_SIZE = 64` 分页读取 terminal events。对于 Run 内 terminal 数量远超 64 的极端场景，`_read_operation_terminal_rows` 的 while 循环会多次分页读取，但跨 page 的 `event_class is not CANONICAL_FACT` 检查只在 page 内按行执行。如果 non-canonical terminal row 的 `operation_id` 恰好不匹配目标 operation_id，它会被 `continue` 跳过而不是触发 invariant 检查 — 这是正确行为，因为 non-canonical row 本就不应参与 operation 过滤。但如果 non-canonical row 的 `operation_id` 匹配目标，会在 invariant 检查中 fail closed。现有测试 `test_non_canonical_terminal_row_fails_before_operation_filter` 通过注入 non-canonical row 覆盖了此路径。

3. **`_active_tasks` type widening**: `set[asyncio.Task[None]]` → `set[asyncio.Task[None] | asyncio.Task[bool]]`。所有现有消费者（`close()` 中的 cancel+await、`add_done_callback`）都兼容 `Task[bool]`。此变更不引入类型安全问题。

4. **已知相邻 watchdog exact token count race**: HEAD 即有 10ms race，无 S4 改动触及该路径。确认无新增 race。

## 验证摘要

### 已验证的正确性属性

| 属性 | 验证结果 | 关键证据 |
| --- | --- | --- |
| Shared owner 是唯一 terminal disposition 真源 | ✓ | `compaction_terminal.py:98-177`，所有 6 个 call site 都通过同一函数判定 |
| Permit 不跨 transaction/await | ✓ | `CompactionTerminalCommitPermit` 只在 write transaction 闭包内使用，无跨 await 保存 |
| 所有 request-backed writer 已覆盖 | ✓ | AST inventory 测试 (`test_compaction_terminal_writer_inventory_uses_only_shared_owner`) + 手动验证：dispatch 4 calls、engine_ingest 1 call、proactive_compaction 1 call（只读） |
| First truth 不被 late loser 改写 | ✓ | `test_proactive_late_accepted_result_preserves_first_failed_truth` (I0543)、`test_proactive_same_operation_terminal_contenders_preserve_first_truth`、`test_reactive_same_pending_terminal_race_preserves_first_truth` |
| Late loser 零 artifact/descriptor/rejected/terminal/fallback/start | ✓ | 上述测试均验证 cursor/descriptor count/artifact files/event count 在 loser 提交后不变 |
| INVALID_MULTIPLE 不追加第三 terminal | ✓ | `test_multiple_terminals_fail_closed_without_inventing_third_truth`、`test_proactive_invalid_multiple_terminals_fail_closed_without_third_or_start`、`test_reactive_invalid_multiple_terminals_fail_closed_without_third_or_start` |
| Projection 不产生第二 owner | ✓ | `_project_state` 接收 `terminal_state` 参数，用 shared owner 结果验证 terminal rows；`terminal_count` 已完全移除 |
| Per-Session sole flight coalesce | ✓ | `test_pre_start_flight_coalesces_wake_periodic_and_direct_signals`：多 signal → 2 passes（第一个 coalesced pass + 一个 fresh no-op） |
| Live compactor 不被误恢复 | ✓ | `test_live_compactor_flight_coalesces_wake_and_periodic_without_recovery`：provider 只调一次，attempt=1，无重复 request/terminal |
| Exit boundary 无 race | ✓ | `test_pre_start_flight_exit_boundary_signal_starts_fresh_flight`：`call_soon` 排队的 signal 正确启动新 flight |
| Caller cancel 不取消 flight | ✓ | `test_pre_start_flight_is_parallel_per_session_and_close_owned`：取消 awaiter 后 flight task 仍在运行 |
| Close 统一收口 | ✓ | 同上测试：close 后所有 flight cleanup，`_pre_start_flights` 为空 |
| 不同 Session 并行 | ✓ | 同上测试：两个 Session 同时进入 barrier |
| 非 request event 被拒绝 | ✓ | `test_arbitrary_event_cannot_act_as_compaction_request` |
| Non-canonical terminal 在 operation filter 前 fail | ✓ | `test_non_canonical_terminal_row_fails_before_operation_filter` |
| Trigger mismatch fail closed | ✓ | `test_trigger_mismatch_fails_closed` |
| 旧契约未因并发时序弱化 | ✓ | `test_pre_start_governance_compact_failure_is_attempt_free` 仍断言 `RunStatus.RUNNING`（使用 `_CloseCountingHandle`） |
| Transient retry 正确计数 | ✓ | `test_wake_queue_promotion_requeues_after_transient_exception`：`attempts == 2` |

### 未发现实质问题的区域

- **Lease lifecycle**: eligibility check 使用短暂 lease 后立即释放；每个 governance pass 取得 fresh lease 并在 finally 中释放。无 lease leak。
- **`asyncio.shield` 使用**: 正确保护 flight task 免受 caller cancel 影响；flight 异常正确传播给所有 awaiter。
- **Close 顺序**: 先 cancel 所有 background tasks 和 active tasks（同步发出），再逐个 await。flight tasks 通过 `_active_tasks` 被追踪和取消。
- **Type safety**: `_active_tasks` 类型 widening 兼容所有消费者；`_suppress_task_cancel` 签名正确更新。
- **编码规范**: 无 `Any`/`object`/`hasattr`/`getattr`/compat shim/extra payload；docstring 完整；模块依赖最小化。

## 结论

F11/F12 implementation 正确实现了 transaction-local shared terminal owner 和 per-Session scheduler-local sole flight。全部 6 个 request-backed terminal writer 已收敛到同一个 shared owner；first truth / late loser / INVALID_MULTIPLE 在所有 artifact/descriptor/rejected/terminal/fallback/start 写入前正确收口；projection 是 shared owner 的消费者而非第二 owner；flight coalesce / exit race / caller cancel / close 生命周期正确。

发现 1 个中等问题（`_promotion_pending_session_ids` stale entry 可导致 wake signal 延迟）和 2 个低等问题（缺少显式 crash recovery 测试、drain loop 异常分类不够精细）。无阻塞性 finding。

**Next gate**: 建议在 controller adjudicate 后进入 S5（fix），修复 Finding 1 的 stale pending set 问题。其余低等 findings 可 deferred 到后续 work unit 或 S6 documentation gate。

**Review verdict**: 建议有条件通过（conditional pass），条件为修复或裁决 Finding 1。
