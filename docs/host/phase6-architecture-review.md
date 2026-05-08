# P6 架构 Review

## 1. 文档状态

本文档是 Host P6（Durable EventLog）实施后的架构 review 报告。Review 范围覆盖
`docs/host/design.md` 9.0 节、`docs/host/phase6-plan.md`、`docs/host/migration-plan.md`
P6 边界，以及 `dayu/host/` 下全部 P6 新增与修改的生产代码。

Review 类型：READ-ONLY 架构 review，不修改代码。

Review 日期：2026-05-08。

## 2. 总体判定

**有条件通过**。

P6 durable 基础设施的架构设计正确、模块实现质量合格、事务边界与序列化策略符合
设计文档要求。但存在一个关键集成缺口：主执行路径（`LocalRunHarness`）未接入
ProjectionCoordinator 与 AttemptStateStore，导致 P6 新增的 durable 投影与
attempt 状态追踪在实际 run 执行中完全被绕过。

修复该集成缺口后，P6 可达到"通过"状态。

## 3. Review 逐项回答

### Q1: Durable facts 路径是否正确升级？

**是。** `DurableRunEventStore` 正确实现了 `RunEventStore` 协议，append
在单一事务内完成：validate provenance → check terminal guard → allocate per-run
cursor → allocate global event position → serialize payload → insert event row
→ upsert run state → commit → notify subscriber。

关键证据：

- `_durable_event_store.py` 的 `append` 方法在 `HostStorage.transaction()`
  上下文内完成全部写入，事务边界正确。
- `_host_storage_transaction.py` 使用 `BEGIN IMMEDIATE` + WAL 模式，保证
  写锁获取与提交原子性。
- `_run_event_serializer.py` 实现了封闭 serializer registry，覆盖全部
  `RunEventData` 变体，unknown type / schema version fail-fast。

### Q2: UoW 事务边界是否符合 phase6-plan 4.7？

**是。** `HostStorage` 是唯一的事务 owner。`HostStorageTransaction` 作为
事务上下文对象，所有 store 写入（event append、run state upsert、projection
checkpoint advance）通过同一 connection / transaction 完成。

关键证据：

- `_host_storage_transaction.py:164` — `transaction()` 是 async context
  manager，在协程内串行获取写锁。
- `_durable_event_store.py` 的 `append` 使用 `async with self._storage.transaction()`
  作为事务边界。
- `_event_observer.py` 的 `run_once` 在 `storage.transaction()` 内完成
  observer.process + checkpoint advance，保证 at-least-once 语义。
- `_projection_store.py` 的 `advance_success` 有 compare-and-set 防止
  checkpoint 倒退。

### Q3: Run / Attempt 状态是否接入主路径？

**部分接入。** Run 状态通过 `DurableRunEventStore._upsert_run_state` 在
event append 事务内自动维护（创建 run 行、terminal 时更新 state），这是正确的。
但存在两个缺口：

1. `AttemptStateStore` 从未被主路径调用（见 Finding 2）。
2. `RunStateStore.write_terminal_result` 从未被主路径调用（见 Finding 3）。

### Q4: ProjectionCoordinator 架构是否正确？

**架构正确，但未接入主路径。** `ProjectionCoordinator` 的 batch drain +
checkpoint 协议实现正确：

- 按 observer 逐个 run_once，每个 run_once 内 fetch batch by position →
  observer.process(tx, batch) → advance checkpoint in same tx。
- Required vs best-effort 通过 `ObserverDescriptor.required` 区分。
- `MemoryProjectionObserver` 标记为 required=True。
- Failure handling 区分 `RetryableProjectionError`（RETRYABLE_FAILED）与
  其他异常（BLOCKED_FAILED）。

但 `ProjectionCoordinator` 在实际 run 执行中从未被触发（见 Finding 1）。

### Q5: LocalRunHarness 是否膨胀为 God Object？

**未膨胀，但保留了应迁出的职责。** `LocalRunHarness` 当前保留了
`_project_run_events`（line 937-955），该方法直接调用
`memory_store.project_run_events` 绕过 ProjectionCoordinator。
`phase6-plan.md` 5.2 明确要求"删除或收窄 `_project_run_events` 的职责"。

除此之外，harness 的职责边界符合 phase6-plan 第 8 节：只做 start_run
ingress 编排、RunInputBuilder 构造、WorkerProxy 消费、EventStore append。

### Q6: 公共接口是否保持向后兼容？

**是。** `LocalRunHarness.start_run` 签名未变。`RunEventStore` 协议未变。
`ConversationMemoryStore` 协议未变。`dayu/host/__init__.py` 未新增 P6
internal 类型到 public surface。

### Q7: Smoke / 测试覆盖是否充分？

**模块级测试覆盖合格，集成路径覆盖不足。** 各 P6 模块有独立单元测试：
`test_phase6_durable_event_store.py`、`test_phase6_host_storage_transaction.py`、
`test_phase6_run_state_store.py`、`test_phase6_projection_checkpoint.py`、
`test_phase6_run_event_serializer.py`、`test_phase6_memory_rebuild.py`、
`test_phase6_timeline_audit_projection.py`。

但 smoke 只测试手动 append + 手动 drain 路径，未覆盖真实的
`LocalRunHarness.start_run → Engine → durable append → ProjectionCoordinator.drain`
端到端路径（见 Finding 4）。

### Q8: 整体判定与后续建议

见第 2 节总体判定。修复 Finding 1（ProjectionCoordinator 接入）后，P6
durable 基础设施即可在实际 run 中生效。Finding 2-4 为次要改进项。

## 4. 发现清单

### Finding 1 [严重]: LocalRunHarness 未接入 ProjectionCoordinator

**状态**: [已修复] —— `LocalRunHarness` 增加 `coordinator: ProjectionCoordinator | None`、`storage`、`attempt_state_store` 三个可选字段;`_run_to_store.finally` 调用新增的 `_project_terminal_run`,durable 路径走 `coordinator.drain()`,legacy 路径退化为 `_project_run_events` fallback;`build_durable_harness` 已显式注入 coordinator 与 storage。

**问题：** `LocalRunHarness._run_to_store` 在 run 终态后直接调用
`_project_run_events`，该方法从 `event_store.list_events` 读取事件后
直接调用 `memory_store.project_run_events`，完全绕过
`ProjectionCoordinator`。P6 新建的 observer checkpoint、timeline /
audit projection、retry / lag 机制在实际 run 中不生效。

**证据：**

- `_run_harness.py:513` — `finally` 块中调用
  `await self._project_run_events(request.run_id)`。
- `_run_harness.py:937-955` — `_project_run_events` 直接调用
  `self.memory_store.project_run_events(events)`。
- `_durable_harness.py:113-119` — `build_durable_harness` 创建
  `LocalRunHarness` 时未传入 `ProjectionCoordinator`；harness 构造
  参数中无 coordinator 字段。
- `_durable_harness.py:99-104` — coordinator 被创建并放入 bundle，
  但仅作为外部可调用的 `bundle.coordinator` 暴露，harness 内部不引用。

**影响：**

- memory projection 仍走旧路径，不经过 checkpoint。
- timeline / audit projection 在 run 结束后不会自动触发。
- observer checkpoint 永远不推进，lag 永远为 0 或全量。
- phase6-plan.md 5.2 要求的"注入 projection coordinator"未完成。
- design.md 9.0 目标路径中
  `ProjectionCoordinator drains durable EventLog` 这一步在实际 run 中不存在。

**建议：**

1. `LocalRunHarness` 新增 `coordinator: ProjectionCoordinator | None`
   构造参数。
2. `_run_to_store` 的 `finally` 块中，若 coordinator 存在，调用
   `await self.coordinator.drain()` 替代 `_project_run_events`。
3. `build_durable_harness` 将 coordinator 传入 harness。
4. 保留 `_project_run_events` 作为 coordinator=None 时的 fallback
   （兼容 InMemoryRunEventStore 测试路径），或在 durable 路径下强制
   coordinator 存在并删除 fallback。

### Finding 2 [严重]: AttemptStateStore 未接入主路径

**状态**: [已修复] —— `_run_to_store` 在 attempt 起点调用 `_begin_attempt_if_durable`(create + RUNNING),terminal 调用 `_finish_attempt_if_durable` 写入终态,context overflow compact retry 把旧 attempt 标记为 `STALE_DIAGNOSTIC` 后开新 attempt,finally 路径兜底关闭未推进 attempt;attempt_id 形如 `attempt-<run_id>-<index>-<short_uuid>`;P8 owner lease/fencing 不在本范围。

**问题：** `AttemptStateStore.create` 和 `update_state` 从未在
`_run_to_store` 或任何 run 执行路径中被调用。`host_attempts` 表在
生产路径中永远为空。

**证据：**

- `_run_harness.py` 全文无 `AttemptStateStore` import 或引用。
- `_durable_harness.py` 未创建 `AttemptStateStore` 实例。
- `_durable_event_store.py` 的 `append` 方法内 `_upsert_run_state`
  只操作 `host_runs` 表，不操作 `host_attempts`。

**影响：**

- `host_attempts` 表始终为空，无法追踪 attempt 级状态。
- P8（attempt owner lease / fencing）无法在此基础上构建。
- phase6-plan.md 6.2 定义的 Attempt 状态机（CREATED → SUCCEEDED /
  FAILED / CANCELLED / SUSPENDED / STALE_DIAGNOSTIC）未生效。

**建议：**

1. `_run_to_store` 的 attempt 循环开始时调用
   `attempt_state_store.create(attempt_id=..., run_id=...,
   attempt_index=...)`。
2. terminal 事件 append 后调用 `attempt_state_store.update_state`。
3. `build_durable_harness` 创建 `AttemptStateStore` 并注入 harness。
4. 注意：attempt_id 在当前实现中未显式生成；需要在 `_run_to_store`
   中为每个 attempt 生成唯一 id。

### Finding 3 [中等]: RunStateStore.write_terminal_result 未接入

**状态**: [已修复] —— `DurableRunEventStore._append_in_transaction` 在 terminal 事件入库时同步调用 `_write_terminal_result_snapshot`,通过共享 `HostStorageTransaction` 与事件 append + Run state 推进同事务持久化;`tests/host/test_phase6_review_fixes.py` 覆盖四种终态。

**问题：** `_run_to_store` 终态后未调用
`RunStateStore.write_terminal_result`，导致 `host_runs.result_payload`
始终为 NULL。`RunStateStore.get_terminal_result` 永远返回 None。

**证据：**

- `_run_harness.py` 全文无 `RunStateStore` import。
- `_durable_event_store.py` 的 `_upsert_run_state` 只更新 `state`
  和 `updated_at`，不写 `result_payload`。

**影响：**

- 终态 result 需要从 terminal event 重新推导，无法直接读取 snapshot。
- `RunStateStore.get_terminal_result` 成为死代码。

**建议：**

1. 在 terminal event append 事务内，由 `_durable_event_store.py` 的
   `append` 方法调用 `RunStateStore.write_terminal_result`（同事务）。
2. 或在 `_run_to_store` 终态后、projection drain 前调用。

### Finding 4 [中等]: Smoke 测试未覆盖真实执行路径

**状态**: [已修复] —— smoke 改为 `harness.start_run` + stub `WorkerProxy`,完整覆盖 USER_INPUT_ACCEPTED → proxy → translate → append → terminal → coordinator.drain → memory/timeline/audit 投影 + RunResult 持久化;`tests/host/test_phase6_durable_harness_integration.py` 在测试套件层面持续守护。

**问题：** `utils/smoke_host_p6_durable_eventlog.py` 只测试手动
`event_store.append` + 手动 `coordinator.drain()`，未覆盖真实的
`LocalRunHarness.start_run → Engine → durable append → drain`
端到端路径。

**证据：**

- smoke 脚本 line 80-113：直接构造 `RunEventDraft` 并调用
  `bundle.event_store.append`。
- smoke 脚本 line 115：手动调用 `bundle.coordinator.drain()`。
- 未调用 `bundle.harness.start_run`。

**影响：**

- 无法验证 durable 路径在真实 Engine 交互中的正确性。
- phase6-plan.md 10 节要求的"故障注入 observer retry"场景未实现。

**建议：**

1. 新增一个 smoke 变体或扩展现有 smoke，通过 `harness.start_run`
   启动一个 run（可使用 mock Engine worker），验证端到端 drain。
2. 可选：新增故障注入 observer，验证 retry_count / last_error /
   checkpoint 未前进。

### Finding 5 [低]: _project_run_events 应删除或收窄

**状态**: [已修复] —— `_project_terminal_run` 现在统一负责终态投影:有 coordinator 时调用 `coordinator.drain()`,否则降级到 `_project_run_events`(legacy `InMemoryRunEventStore` 路径);保留 fallback 以维持非 durable 装配的最小行为,并在 docstring 中明确职责边界。

**问题：** `phase6-plan.md` 5.2 要求"删除或收窄 `_project_run_events`
的职责"。当前该方法仍完整存在于 `_run_harness.py:937-955`。

**证据：**

- `_run_harness.py:937-955` — `_project_run_events` 完整实现。

**影响：**

- 代码冗余；在 Finding 1 修复后该方法成为死代码。

**建议：**

- Finding 1 修复后删除此方法，或将其降级为 coordinator=None 时的
  fallback 并加注释说明。

## 5. 正确实现的确认项

以下设计要点已正确实现，无需修改：

| 项目 | 证据 |
|------|------|
| HostStorage UoW 事务边界 | `_host_storage_transaction.py` BEGIN IMMEDIATE + WAL + asyncio.Lock |
| DurableRunEventStore 原子 append | `_durable_event_store.py` 单一事务内完成 cursor + position + event + run state |
| ProjectionCoordinator batch drain | `_event_observer.py` run_once 内 fetch → process → advance in same tx |
| Checkpoint 防倒退 | `_projection_store.py` advance_success compare-and-set |
| Required vs best-effort projection | `ObserverDescriptor.required` 标记，memory=True |
| RunEventData 封闭序列化 | `_run_event_serializer.py` closed registry + schema_version + fail-fast |
| Terminal guard | `_durable_event_store.py` append 前检查已有 terminal event |
| Append-before-stream 语义 | `start_run` 先 append USER_INPUT_ACCEPTED，再创建 RunStream |
| Engine 不感知 Host durable / projection | 无 Engine 模块 import Host internal 类型 |
| Public 接口向后兼容 | `LocalRunHarness.start_run` 签名不变，`__init__.py` 未暴露 P6 internal |
| Memory rebuild from durable EventLog | `_memory_projection.py` rebuild_from_events 按 run_id 分组投影 |

## 6. 与 phase6-plan 的边界对照

| phase6-plan 条目 | 状态 | 备注 |
|------------------|------|------|
| 4.1 Durable EventLog 是 P1.5 契约的生产实现 | 已完成 | RunEventStore 协议不变 |
| 4.2 Internal global event position | 已完成 | _durable_event_store.py |
| 4.3 Run / Attempt 最小持久状态 | 部分完成 | Run state 已接入，Attempt 未接入 |
| 4.4 Observer / sink protocol | 已完成 | _event_observer.py |
| 4.5 Required vs best-effort projection | 已完成 | ObserverDescriptor |
| 4.6 Storage backend (SQLite) | 已完成 | _host_storage_transaction.py |
| 4.7 UoW 事务 owner | 已完成 | HostStorage 事务边界正确 |
| 4.8 Durable RunEventData 序列化 | 已完成 | _run_event_serializer.py |
| 5.2 _run_harness.py 修改 | 未完成 | 未注入 coordinator / run state store |
| 8. LocalRunHarness 防 God Object | 部分完成 | 保留了应迁出的 _project_run_events |
| 9. 测试清单 | 部分完成 | 模块测试有，集成路径测试缺 |
| 10. 手工 smoke | 部分完成 | 仅手动 append + drain 路径 |

## 7. 后续行动建议

1. **首要**：修复 Finding 1，将 ProjectionCoordinator 接入
   `LocalRunHarness`，使 durable 投影在实际 run 中生效。
2. **次要**：修复 Finding 2，将 AttemptStateStore 接入主路径。
3. **次要**：修复 Finding 3，在 terminal 事件事务内写入 result snapshot。
4. **改进**：扩展 smoke 覆盖端到端路径（Finding 4）。
5. **清理**：Finding 1 修复后删除 `_project_run_events`（Finding 5）。
