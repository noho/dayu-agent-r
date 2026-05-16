# Code Review — Host Phase 7 P7-S2 ToolRuntime Awaiting Accept Path（修后复检）

## Scope

- Mode: current changes (uncommitted, post-fix)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: HEAD (committed P7-S1 artifact)
- Output file: docs/reviews/host-phase7-code-review-s2-ds-20260516.md
- Prior reviews:
  - 初检: `docs/reviews/host-phase7-code-review-s2-ds-20260516.md`（S2-F1: CAS_LOST error propagation gap, S2-F2: precondition test gap）
- Included scope:
  - `dayu/host/waiting.py` (new, 843 lines) — Host awaiting accept port + `_AwaitingAcceptStateConflictError`
  - `dayu/host/wait_adapter.py` (new, 124 lines) — Wait adapter binding / registry（未修改）
  - `dayu/host/tool_runtime.py` (diff) — ToolRuntime awaiting accept routing + `ToolAwaitingAcceptRejectReason` export
  - `dayu/host/_event_payload.py` (diff) — TOOL_AWAITING / RUN_WAITING / ATTEMPT_SUSPENDED payload（未修改）
  - `dayu/host/durable/state.py` (diff) — mark_run_waiting_row / mark_attempt_suspended_row（未修改）
  - `tests/host/test_wait_awaiting_accept.py` (new, 442 lines) — 新增 `test_awaiting_accept_stale_execution_rejects_without_wait_record`
  - `tests/host/test_toolruntime_executor.py` (diff) — 新增 `_SequencedAwaitingAcceptPort`、rejected/timeout/missing_external_job/batch_stop 测试
- Excluded scope:
  - P7-S1 committed changes, resolve_wait path (P7-S3+), plan/design/control docs
- Parallel review coverage: 无

## Fix Verification

### S2-F1 — 已修复 — CAS_LOST 错误传播链

- **原始 finding**: `HostDurableError` 从 CAS 失败点未被 `accept_tool_awaiting` 或 `_accept_awaiting_with_retry` 吸收，导致未处理异常崩溃
- **修复**:
  1. `waiting.py:67-68` — 新增 `_AwaitingAcceptStateConflictError(HostDurableError)` 异常子类
  2. `waiting.py:388-389` — CAS 失败从 `raise HostDurableError` 改为 `raise _AwaitingAcceptStateConflictError`
  3. `waiting.py:300-305` — `accept_tool_awaiting` 新增 `except _AwaitingAcceptStateConflictError` 并转换为 `ToolAwaitingRejectedAck(CAS_CONFLICT, retryable=False)`
  4. `waiting.py:72` — `ToolAwaitingAcceptRejectReason` 新增 `CAS_CONFLICT = "cas_conflict"`
- **验证证据**:
  - `_AwaitingAcceptStateConflictError` 是 `HostDurableError` 子类，不影响 `run_write` 内部回滚逻辑
  - `accept_tool_awaiting` 中的 catch 在 `run_write` 外部，转换发生在事务回滚后，无部分状态风险
  - `ToolAwaitingRejectedAck(CAS_CONFLICT, retryable=False)` 被 `_accept_awaiting_with_retry` 检测为 terminal result 直接返回，不重试
- **状态**: 已关闭

### S2-F2 — 部分修复 — precondition 拒绝路径测试

- **原始 finding**: `_invalid_awaiting_precondition` 拒绝路径无直接测试覆盖
- **修复**:
  1. `test_wait_awaiting_accept.py:152-175` — 新增 `test_awaiting_accept_stale_execution_rejects_without_wait_record`
  2. 构造 mismatched `execution_id="execution-stale"`，断言 `ToolAwaitingRejectedAck(STALE_EXECUTION)`、wait_record 为 None、events 为空
- **仍缺失**: `INVALID_ATTEMPT` 类型的拒绝（Run 不是 RUNNING、Attempt 不是 RUNNING、identity mismatch、`worker_accept_event_id IS NULL`）无直接测试
- **状态**: 部分关闭 — STALE_EXECUTION 已覆盖，INVALID_ATTEMPT 仍为 residual risk

## Findings

### S2-F3 — 未修复 — 低 — INVALID_ATTEMPT precondition 拒绝路径仍无直接测试

- **入口/函数**: `DefaultHostToolAwaitingAcceptPort._accept_in_transaction()` → `_invalid_awaiting_precondition()`
- **文件(行号)**: `waiting.py:439-475`
- **输入场景**: Run 非 RUNNING、Attempt 非 RUNNING、`run.session_id != candidate.session_id`、`run.current_attempt_id != candidate.attempt_id`、`attempt.run_id != candidate.run_id`、`dispatch_record.worker_accept_event_id IS None`
- **实际分支**: `waiting.py:454-474` — 6 个不同的 `INVALID_ATTEMPT` 拒绝点，均返回 `ToolAwaitingAcceptRejectReason.INVALID_ATTEMPT`
- **预期行为**: 非法请求应被结构化拒绝为 `INVALID_ATTEMPT`
- **实际行为**: 分支逻辑正确，但无测试证明该分支可达且行为正确
- **直接证据**: `test_wait_awaiting_accept.py` 中仅 `STALE_EXECUTION` 被测试（mismatched execution_id），`INVALID_ATTEMPT` 所有子分支均未触发
- **影响**: 若未来修改 Run/Attempt 状态枚举或 CAS 条件，导致非法状态被静默接受，无测试捕获。当前代码正确，但回归防护不完整
- **建议改法和验证点**: 增加 1 个 `INVALID_ATTEMPT` 测试（将 Run status 改为非 RUNNING），覆盖最具代表性的拒绝子分支
- **修复风险**: 低 — 新增测试
- **严重程度**: 低 — 当前生产代码逻辑正确，缺失的是部分回归防护

## Open Questions

1. **CAS_CONFLICT 测试可行性**：`_AwaitingAcceptStateConflictError` 在单进程 IMMEDIATE transaction 下不可触发（写锁贯穿整个事务）。是否需要像 S1-F4（CAS_LOST race test）一样 deferred to later slice？还是将 CAS_CONFLICT 的测试视作不可达代码防护（no test required）？
2. **`_accept_awaiting_with_retry` 中 `TimeoutError` catch**：`accept_tool_awaiting()` 是同步方法，`TimeoutError` 当前不可达。此 catch 是否应保留作为 future async port 实现的预留？还是应移除以减少 dead code？
3. **`ToolAwaitingAcceptRejectReason` 自身是否需要作为公共符号导出**：当前通过 `tool_runtime.__all__` 导出。该枚举描述的是 Host port 层的拒绝原因，ToolRuntime 消费它是为了构造 hint 文本。这是否属于合理的跨层使用，还是应定义单独的 ToolRuntime 层拒绝原因枚举？

## Residual Risk

- **S2-F3 INVALID_ATTEMPT 测试缺口**：6 个 `INVALID_ATTEMPT` 子分支未被直接测试。Run/Attempt/DispatchRecord 的状态组合（RUNNING/RUNNING/DISPATCHING）是 Host 核心 invariant，被多个模块依赖。建议至少覆盖 1 个 `INVALID_ATTEMPT` 子分支作为回归防护。
- **CAS_CONFLICT 不可达**：在 IMMEDIATE transaction 下不可触发，实际风险极低。修复（`_AwaitingAcceptStateConflictError` → `CAS_CONFLICT`）已将不可达的 crash 转为结构化拒绝，即使未来事务隔离降级也不会崩溃。
- **`_accepted_ack_from_existing` 重放时对缺失 EventLog/wait record 使用 `RuntimeError`**：此异常会穿透 port 层并崩溃 executor。若发生，表明 durable invariant 已破坏，hard crash 可能优于静默修复。当前设计合理但值得在运维文档中记录。
- **`_wait_snapshot_ref` 始终传 `snapshot_digest=None`**：快照完整性验证推迟到 resolve 阶段（P7-S3+），当前不阻塞。

## Test Coverage Assessment

### Port 层测试（test_wait_awaiting_accept.py — 4 项）

| 测试 | 状态 | 覆盖路径 |
|------|------|----------|
| happy path + 3 facts + WAITING/SUSPENDED | ✅ | 正常 accept |
| idempotency replay（同 digest） | ✅ | 重放，无重复事件 |
| idempotency conflict（异 digest） | ✅ | 拒绝，无副作用 |
| STALE_EXECUTION 拒绝 | ✅ (新增) | execution_id 不匹配 |

### ToolRuntime 层测试（test_toolruntime_executor.py — 7 项）

| 测试 | 状态 | 覆盖路径 |
|------|------|----------|
| awaiting outcome → awaiting accept port | ✅ | e2e 正确端口路由 |
| 无 adapter binding → governed error | ✅ | 配置缺失降级 |
| awaiting rejected ack → governed error | ✅ (新增) | 拒绝转译 |
| awaiting timeout → governed error | ✅ (新增) | 超时转译 |
| poll 无 external_job_ref → governed error | ✅ (新增) | external_job_ref 缺失 |
| batch 首个 awaiting 后停止后续调用 | ✅ | batch 挂起 |
| 普通 fake tool → fact accept port | ✅ (已有) | 回归 |

### 未覆盖路径

| 路径 | 状态 |
|------|------|
| INVALID_ATTEMPT（Run 非 RUNNING 等） | ❌ |
| CAS_CONFLICT | ❌（不可达） |
| retry loop retry-then-succeed | ❌ |
| `_accepted_ack_from_existing` port 层重建 | ❌（间接覆盖于 replay 测试） |

## Verification of Five Focus Areas

### 1. Awaiting accept 事务原子性

- 所有写入（3 events + wait_record + Run CAS + Attempt CAS + idempotency record）在单个 `run_write` transaction 内
- CAS 失败 → `_AwaitingAcceptStateConflictError` → 事务回滚 → `accept_tool_awaiting` 转换为 `ToolAwaitingRejectedAck(CAS_CONFLICT)`
- 无部分状态残留可能；事务内错误不会导致半提交
- **结论：正确，S2-F1 已修复**

### 2. Idempotency replay/conflict

- Idempotency scope: `(attempt_id, tool_call_id)` with `accept_idempotency_key`
- Same digest → replay from durable EventLog（port 层测试 `test_awaiting_accept_same_key_replays_existing_ack_without_duplicate_events` 验证）
- Different digest → `IDEMPOTENCY_CONFLICT`（port 层测试验证）
- **结论：正确，无重复事实写入风险**

### 3. Host registry 派生 adapter_key/external_job_ref

- `WaitAdapterRegistry.resolve_binding(tool_name, await_kind)` — Host 配置
- `WaitAdapterBinding.external_job_ref(await_spec)` — 从 `external_job_ref_source` 派生
- Engine 无任何输入到 adapter_key 或 external_job_ref
- **结论：正确，所有权清晰**

### 4. 普通工具路径回归

- `_execute_one` 中 `isinstance(raw_outcome, ToolAwaitingOutcome)` 是显式条件分支
- 非 awaiting outcome → `_normalize_runtime_outcome`（pass-through）→ `_accept_with_retry`（未修改）
- 既有测试 `test_fake_tool_result_returns_only_after_accepted_ack` 等未修改
- **结论：无回归**

### 5. 测试充分性（awaiting rejected/timeout/missing external job/batch stop）

- awaiting rejected → `test_awaiting_accept_rejected_returns_governed_error` ✅
- awaiting timeout → `test_awaiting_accept_timeout_returns_governed_error` ✅
- missing external job → `test_poll_awaiting_without_external_job_ref_is_governed_error` ✅
- batch stop → `test_awaiting_outcome_stops_remaining_batch_calls` ✅
- **结论：4 项关键 failure path 均已覆盖**

## Conclusion

PASS。两项初检 finding（S2-F1, S2-F2）中 S2-F1 已完全修复，S2-F2 中 STALE_EXECUTION 已覆盖。新增 1 个低级 finding（S2-F3: INVALID_ATTEMPT 子分支仍未测试）。测试覆盖从初检的 3+3 项增加到 4+7 项，failure path 覆盖显著增强。未发现中/高/严重级别缺陷。
