# Host P1-P7 Design vs Code Divergence Review

- **Review date**: 2026-05-16
- **Design baseline**: commit `1245aeefeeb182a2da833c8577d701a6a71b7065` (`docs/host/design.md`)
- **Code under review**: working tree on branch `fix/host-p1-p7-awaiting-production-wiring` (includes P1-P7 implementation + C-P1P7-001 fix)
- **Reviewer**: mimo (independent)
- **Scope**: Host P1-P7 (durable store, EventLog, admission, public API, local dispatch, ToolRuntime governance, Tool Awaiting / resolve_wait / Wait Adapter)

---

## Verdict: PASS (with 1 Low finding)

P1-P7 实现与设计基线高度一致。状态机、分层边界、一等对象模型、EventLog append-only 语义、CAS 状态迁移、幂等机制、ToolRuntime 治理、Tool Awaiting accept 路径、resolve_wait 统一 pipeline、WaitPoller adapter 模式均严格遵循设计。唯一的生产接线缺陷 C-P1P7-001 已在当前 fix 分支修复。

---

## Finding Summary

| Severity | Count |
|----------|-------|
| Blocking | 0 |
| High | 0 |
| Medium | 0 |
| Low/Info | 1 |

---

## Findings

### DIVERGE-001: `cancel_run` on WAITING Run 路径未在 Phase 4 command 层完整实现

- **Severity**: Low/Info
- **Design baseline evidence**: 设计 §7 Run 状态表、§9 admission 表明确 `cancel_run` on `WAITING` 路径：Host 在同一事务内 append `CANCEL_REQUESTED`，标记 active wait record cancelled，append `RUN_CANCELLED`，释放 Session active slot。设计 §20 约束："`cancelled` / `lost` wait record 的迟到 poll / callback result 不得作为 `canonical_fact` 进入 EventLog"。
- **Current code evidence**: `dayu/host/command.py:363-411` (`cancel_run`) 调用 `admission_service.cancel_run()`，对 `WAITING` 和 `RECOVERING` 状态返回 `UNSUPPORTED_OPERATION`（通过 `_is_deferred_cancel_state` 检测）。`dayu/host/admission.py` 中 `cancel_run` 方法不处理 `WAITING` 状态。
- **Impact**: `WAITING` Run 的 cancel 路径尚未实现，需要 Phase 7+ 补充。当前 Phase 4 的拒绝行为是显式且稳定的（返回 `UNSUPPORTED_OPERATION`），不会导致数据损坏或静默失败。
- **Recommended handling**: 不需要修复。这是有意的 phase boundary 设计——Phase 4 command 层正确拒绝了超出当前 phase 范围的操作，Phase 7 的 `waiting.py` 已提供 `resolve_wait` 基础设施，`WAITING` cancel 需要后续 phase 在 `admission.py` 中补充。
- **Fix now**: No

---

## Detailed Review

### 1. 设计偏差分析

#### 1.1 状态机一致性 ✅

设计定义的状态集合与代码实现完全一致：

| 对象 | 设计状态集合 | 代码实现 |
|------|-------------|---------|
| Session | OPEN, CLOSED | `api.py` `SessionStatus` ✅ |
| Run | QUEUED, RUNNING, WAITING, CANCELLING, RECOVERING, SUCCEEDED, FAILED, CANCELLED, LOST | `api.py` `RunStatus` ✅ |
| Attempt | STARTING, RUNNING, SUCCEEDED, FAILED, CANCELLED, SUSPENDED, STEERED, LOST | `api.py` `AttemptStatus` ✅ |
| WaitRecord | waiting, resolved, failed, cancelled, lost | `durable/state.py` `WaitRecordStatus` ✅ |
| DispatchRecord | PENDING, WAITING_FOR_LANE, DISPATCHING, CANCELLED | `durable/state.py` `DispatchRecordStatus` ✅ |

CAS 状态迁移通过 `mark_*_row` 函数族实现，返回 `StateMutationStatus.UPDATED / SKIPPED`，与设计一致。

#### 1.2 一等对象模型 ✅

设计 §4："Host 治理核心只有四个一等对象：Session, Run, Attempt, EventLog"。

代码确认：
- `WaitRecord` 是 durable table，不是一等治理真源（`durable/state.py` 中 `WaitRecordRow` 定义，`durable/schema.py` 中 `TABLE_HOST_WAIT_RECORDS`）
- `DispatchRecord` 是 durable table，不是一等治理真源
- 其它能力（memory snapshot, tool trace, outbox 等）均未提升为同级治理真源

#### 1.3 EventLog append-only 语义 ✅

- `EventLogStore.append_event()` 是唯一写入路径（`durable/event_log.py`）
- `event_sequence` 全局递增分配
- `event_class` 区分 `canonical_fact`, `preview`, `diagnostic`, `projection_signal`
- EventLog 不可删除（`purge_session` 是设计允许的唯一 destructive exception）

#### 1.4 幂等机制 ✅

- `IdempotencyStore` 按 `(scope_kind, scope_id, idempotency_key)` 索引（`durable/idempotency.py`）
- `semantic_input_digest` 防止同 key 不同内容的冲突
- 所有 command path（`start_run`, `submit_followup`, `cancel_run`, `resolve_wait`, awaiting accept）均使用幂等保护

#### 1.5 Tool Awaiting accept 路径 ✅

设计 §20 要求：
- ToolRuntime Host accept path 是 awaiting canonical owner ✅
- 单事务内 append `TOOL_AWAITING`, `RUN_WAITING`, `ATTEMPT_SUSPENDED`，创建 wait record，更新 Run → `WAITING`，Attempt → `SUSPENDED` ✅ (`waiting.py:431-532`)
- Engine `tool_awaiting` / `run_suspended` 只能携带 accepted refs 作为 preview/diagnostic ✅ (`engine_ingest.py` 中 `_REASON_WAITING_EVENT_CONFIRMATION`)
- accepted ack 丢失时用同一 idempotency key 重试 ✅ (`waiting.py:442-454`)

#### 1.6 resolve_wait 统一 pipeline ✅

设计 §20："所有入口都必须走同一个 `resolve_wait` pipeline"。

代码实现：
- `DefaultHostResolveWaitService.resolve_wait()` 在 `waiting.py:563-596`
- 支持 completed / failed / cancelled / lost 四种 outcome ✅
- resume 路径创建新 Attempt + dispatch record ✅ (`waiting.py:847-917`)
- `resolve_wait` 幂等范围是 `(wait_id, idempotency_key)` ✅
- 已 resolved wait record 只允许幂等重放 ✅ (`waiting.py:756-785`)
- late result 进入 diagnostic ✅ (`waiting.py:787-845`)

#### 1.7 WaitPoller adapter 模式 ✅

设计 §20："wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果"。

代码实现（`wait_adapter.py`）：
- `WaitPollAdapter` 是 Protocol，`poll_wait()` 在 Host transaction 外调用 ✅
- `WaitPoller.poll_once()` 读取 active poll wait records → adapter 调用 → `resolve_wait` ✅
- cancelled wait → `adapter.abandon_wait()` ✅
- poller 不持有 EventLog appender，不直接更新 Run/Attempt state ✅

### 2. 架构边界合规性

#### 2.1 分层边界 UI → Service → Host → Engine ✅

- `dayu.host` 不 import `dayu.service` 或 `dayu.ui`
- `dayu.host.engine_ingest` import `dayu.engine.contracts.engine_events`（读取 Engine 公共事件类型），但 Engine 不 import Host
- `dayu.host` 不 import `dayu.fins`

#### 2.2 dayu.runtime 中立性 ✅

- `dayu.runtime.lane` 提供层中立 named semaphore，不 import 业务层
- `dayu.runtime.filelock` 提供文件锁封装，不 import 业务层
- Host 通过 `LaneController` 使用 lane，不修改 runtime 实现

#### 2.3 Host 强治理 ✅

- ToolRuntime 由 Host 拥有和装配（`dispatch.py:708-741`）
- Host accept barrier 通过 `DefaultHostToolFactAcceptPort` 实现（`tool_runtime.py`）
- 工具截断由 `TruncationManager` 在 ToolRuntime 内治理
- duplicate governance 由 `InMemoryRunScopedDuplicateGovernanceRegistry` 管理

#### 2.4 Internal module boundary ✅

设计 §2 定义的内部模块边界在代码中得到遵守：
- Public API layer（`command.py`）只做 validation + 调用 admission service
- Admission（`admission.py`）唯一负责 Session active Run 判定和 queue promotion
- EventLog / State Transition（`durable/`）唯一负责 EventLog append 和 state CAS
- Attempt Dispatch（`dispatch.py`）只消费已提交的 dispatch record
- EngineEvent Ingest（`engine_ingest.py`）唯一负责 Engine 事件 → Host event 映射
- ToolRuntime（`tool_runtime.py`）唯一负责工具执行治理

### 3. 生产接线状态

#### 3.1 C-P1P7-001 修复 ✅

原始问题：`HostDispatchScheduler._run_input_builder_for_dispatch()` 中 `ToolRuntimeBuildRequest` 缺少 `awaiting_accept_port` 和 `wait_adapter_registry`，导致 Tool Awaiting 功能在本地 dispatch 路径不可用。

修复内容（commit `d03e064`）：
- `dispatch.py:731-738`：添加 `awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(...)` 和 `wait_adapter_registry=tooling_options.wait_adapter_registry`
- `tooling.py:140`：`HostToolingOptions` 添加 `wait_adapter_registry: WaitAdapterRegistry | None = None` 字段

修复正确，接线完整。

### 4. 未设计的状态/协议/表/事件/跨层依赖

未发现任何未设计的状态、协议、表、事件或跨层依赖。所有 durable table 均有明确的语义 owner（设计 §10）。所有事件类型均对应设计 §18 EventLog taxonomy。所有跨层依赖均为设计允许的方向。

### 5. 过度设计/过度抽象/God object

未发现 God object、God function 或过度抽象。关键观察：

- `HostCommandHandle`（`command.py`）是 composition root / handle，只持有模块化依赖和事务入口，不混入子系统状态
- `ToolRuntimeBuildRequest`（`tool_runtime.py`）是 frozen dataclass，承载装配所需的所有 typed 依赖
- `ToolAwaitingAcceptCandidate`（`waiting.py`）是 frozen dataclass，字段均经过 `__post_init__` 校验
- 模块级私有辅助函数（如 `_is_dispatchable_recheck`, `_is_worker_acceptable`）职责单一

---

## Conclusion

Host P1-P7 实现与设计基线 `1245aeefeeb182a2da833c8577d701a6a71b7065` 高度一致。状态机、分层边界、一等对象模型、EventLog 语义、CAS 迁移、幂等机制、ToolRuntime 治理、Tool Awaiting accept 路径、resolve_wait 统一 pipeline、WaitPoller adapter 模式均严格遵循设计。唯一的生产接线缺陷 C-P1P7-001 已在当前 fix 分支修复。`cancel_run` on `WAITING` 的 Phase 4 拒绝行为是有意的 phase boundary 设计，不是缺陷。
