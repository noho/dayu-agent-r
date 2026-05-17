# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p9-conversation-memory
- Base: main
- Output file: docs/reviews/p9-s4-code-review-ds-20260517.md
- Included scope:
  - `dayu/host/memory_repair.py` (NEW) — rebuild/catch-up orchestration
  - `dayu/host/durable/memory.py` (modified) — memory projection durable primitives
  - `dayu/host/admission.py` (modified) — ProjectionCatchupPort Protocol, catch-up hooks
  - `dayu/host/dispatch.py` (modified) — scheduler catch-up hook in wake_queue_promotion
  - `tests/host/test_memory_projection.py` (modified) — rebuild/catch-up/reset tests
  - `tests/host/test_admission_queue.py` (modified) — catch-up failure survival tests
  - `tests/host/test_dispatch_scheduler.py` (modified) — scheduler catch-up failure test
- Excluded scope:
  - Previously committed S1-S3 code unless directly affected by current diff
  - `dayu/host/projection.py` (Phase 8 base, unchanged in this diff)
  - `dayu/host/memory.py` (S1-S2 contracts, unchanged in this diff)
- Pre-review checks: 114 tests passed; pyright 0 errors; git diff --check clean
- Design source of truth: docs/host/design.md
- Plan: docs/host/phase9-conversation-memory-plan.md Slice 4

## Findings

### 1-未修复-中-ProjectionCatchupPort 定义在 admission.py 形成跨关注点耦合

- **入口/函数**: `dispatch.py:23` import `ProjectionCatchupPort` from `dayu.host.admission`
- **文件(行号)**: `dayu/host/admission.py:175-189`（Protocol 定义），`dayu/host/dispatch.py:23`（跨层 import）
- **输入场景**: dispatch scheduler 需要注入 projection catch-up 端口以在 `wake_queue_promotion` 中触发 best-effort catch-up
- **实际分支**: dispatch.py 从 admission.py 导入 `ProjectionCatchupPort`
- **预期行为**: projection 层协议应定义在 projection-layer 模块（`dayu/host/projection.py`），admission 和 dispatch 都从 projection 层 import
- **实际行为**: Protocol 在 admission 层定义，dispatch 对 admission 形成 import 依赖，而 dispatch 本身不调用 admission 的任何其他符号（除 `PendingDispatchRecord` 和 `create_host_admission_service` 外）
- **直接证据**:
  - `dayu/host/admission.py:175-189`：`class ProjectionCatchupPort(Protocol)` 定义在 admission 模块
  - `dayu/host/dispatch.py:21-25`：`from dayu.host.admission import (PendingDispatchRecord, ProjectionCatchupPort, create_host_admission_service)`
  - `dayu/host/memory_repair.py:55-100`：`ConversationMemoryProjectionCatchupPort` 实现该协议，定义在 memory_repair.py
  - `dayu/host/projection.py`：定义了 `ProjectionConsumer`、`ProjectionRunner`、`ProjectionEventView` 等所有其他 projection 层核心契约，但 `ProjectionCatchupPort` 不在此
- **影响**: 架构 maintainability 降低。若 admission 模块未来移除 Protocol（例如 admission 自身不再需要 catch-up），dispatch 的 import 会断裂。projection 层契约分散在两个模块（projection.py 和 admission.py），新加入的 projection consumer 作者不易发现完整契约集合。
- **建议改法和验证点**: 将 `ProjectionCatchupPort` 与 `NoopProjectionCatchupPort` 移至 `dayu/host/projection.py`，与 `ProjectionConsumer`、`ProjectionRunner` 等 projection 层核心契约同模块。admission.py 和 dispatch.py 均从 projection.py import。验证：pyright 0 errors，现有 114 测试继续通过。
- **修复风险（低）**: 纯 import 路径变更，不改变运行时行为。仅需更新 import 语句和对应的 `__all__`。
- **严重程度（中）**: 违反 projection 层契约聚合原则，当前不造成运行时 bug 但增加后续维护风险。

### 2-未修复-中-Catch-up hook 在工作线程事件消费路径与 resolve_wait 路径缺失

- **入口/函数**: `dispatch.py:913-1016` `_consume_worker_events()`；`engine_ingest.py` `EngineEventIngestor` 构造函数
- **文件(行号)**:
  - `dispatch.py:943-946`：`EngineEventIngestor(transaction_runner=..., wakeup_port=self)` — 未传入 projection_catchup_port
  - `dispatch.py:978-1006`：`ingestor.ingest(...)` 调用后未调用 catch-up
  - `engine_ingest.py`：`EngineEventIngestor.__init__` 不接收 `projection_catchup_port` 参数
- **输入场景**: worker 在运行中产生 Engine event → `EngineEventIngestor.ingest()` 追加 `TOOL_RESULT_ACCEPTED`、`EPISODE_SUMMARY_ACCEPTED` 等 canonical fact 到 EventLog → worker 事件消费循环继续
- **实际分支**: worker 产生的 `TOOL_RESULT_ACCEPTED` 已写入 EventLog，但 memory projection 不会被 catch-up，直到下一次 admission `start_run`/`submit_followup_queue`/`closeout_attempt_terminal` 或 scheduler `wake_queue_promotion` 被触发
- **预期行为**: S4 plan 声明 catch-up 为 best-effort after-commit hook，不要求实时性
- **实际行为**: 在单 worker 长运行场景下（多轮 tool call），projection lag 可能累积直到 worker 终态 closeout 才追平
- **直接证据**:
  - `dispatch.py:943-946`：ingestor 构造未传 catchup port
  - `dispatch.py:978-1006`：ingest 循环内无 catch-up 调用
  - `dispatch.py:410`：`wake_queue_promotion` 是 dispatch 侧唯一触发 catch-up 的路径
  - `admission.py:472,506,617`：admission 侧 catch-up 仅在 `start_run`、`submit_followup_queue`、`closeout_attempt_terminal` 中触发
  - `engine_ingest.py`：`EngineEventIngestor` 不持有 `projection_catchup_port`
- **影响**: memory projection 读取可能滞后于最新 EventLog 事实，但不会产生错误状态。当 memory 读取发生在 catch-up 之前时，返回的是上次 catch-up 时刻的快照。S3 设计中 memory 读取本身接受这种最终一致性窗口。
- **建议改法和验证点**: 此 gap 属于有意设计（S4 plan 明确为 best-effort，未要求 work path 实时 catch-up）。不建议在 S4 中强行补齐——在 worker 事件热路径上添加 catch-up 会耦合 projection 延迟到 Engine 吞吐。如需降低 lag，建议在 S5 或后续 phase 中引入可配置的 periodic catch-up（如每 N 个 Engine event 或每秒触发一次 idle check），而非在 `_consume_worker_events` 内联调用。当前建议保持现状，记录为 residual risk。
- **修复风险（不适用）**: 不建议在 S4 修复。
- **严重程度（中）**: 功能 gap 明确，但属于 S4 plan 范围内的已知设计取舍。

### 3-未修复-低-Catch-up 失败信息被完全丢弃，缺乏可观测性

- **入口/函数**: `memory_repair.py:88-100` `ConversationMemoryProjectionCatchupPort.catch_up_projection()`；`admission.py:2469-2481` `_catch_up_projection_best_effort()`
- **文件(行号)**:
  - `memory_repair.py:95-100`：`catch_up_conversation_memory_projection(...)` 返回值被丢弃
  - `admission.py:2478-2481`：`try: port.catch_up_projection(); except Exception: pass`
  - `dispatch.py:1042-1046`：`try: port.catch_up_projection(); except Exception: pass`
- **输入场景**: catch-up 过程中 consumer apply_event 抛出异常 → ProjectionRunner 记录 projection failure row 并停止该批次 → `ConversationMemoryProjectionRepairResult.failures > 0`
- **实际分支**: `ConversationMemoryProjectionCatchupPort.catch_up_projection()` 调用 `catch_up_conversation_memory_projection()` 但丢弃返回的 `ConversationMemoryProjectionRepairResult`；`_catch_up_projection_best_effort` 捕获所有 Exception 但无日志
- **预期行为**: S4 plan 要求 best-effort，但 failure 应可被运维观察到（至少通过 projection_failures 表）
- **实际行为**: failure 仅存在于 projection_failures 表中（由 ProjectionRunner 写入），无运行时日志、metric 或 trace 信号
- **直接证据**:
  - `memory_repair.py:95-100`：return value discarded
  - `admission.py:2478-2481`：`except Exception: pass` — 无 logging
  - `dispatch.py:1043-1046`：`except Exception: pass` — 无 logging
- **影响**: 运维无法通过日志/告警发现 catch-up 持续失败。failure 只在主动查询 projection_failures 表时可见。在 catch-up 反复失败且无人检查 failure 表的场景下，projection 可能长期滞后而不被察觉。
- **建议改法和验证点**: 在 `_catch_up_projection_best_effort` 中添加结构化日志（warning 级别，包含 exception type 和 message）。或至少在 `ConversationMemoryProjectionCatchupPort.catch_up_projection()` 中检查返回值的 `failures` 字段，failures > 0 时 emit 日志。验证：日志输出不抛异常（best-effort 约束下日志失败也不应影响主流程）。
- **修复风险（低）**: 仅在 except 块中添加 logging，不改变控制流。
- **严重程度（低）**: 当前 failure 已持久化到 DB，只是缺运行时信号。不影响正确性。

### 4-未修复-低-`_catch_up_projection_best_effort` 在 admission.py 和 dispatch.py 中重复定义

- **入口/函数**: `admission.py:2469-2481` `_catch_up_projection_best_effort()`；`dispatch.py:1032-1046` `_catch_up_projection_best_effort()`
- **文件(行号)**:
  - `admission.py:2469-2481`
  - `dispatch.py:1032-1046`
- **输入场景**: 两个模块各自需要 best-effort 触发 projection catch-up
- **实际分支**: 两处定义了语义几乎相同的私有函数，差异仅在于 dispatch 版本处理了 `None` port（early return）
- **预期行为**: 共享 helper 应抽取到公共位置（如 `projection.py` 或 `memory_repair.py`）
- **实际行为**: 重复定义，且 admission 版本不处理 `None` port（因为 `HostAdmissionService` 始终有默认 `NoopProjectionCatchupPort`）
- **直接证据**:
  - `admission.py:2469-2471`：`def _catch_up_projection_best_effort(projection_catchup_port: ProjectionCatchupPort)`
  - `dispatch.py:1032-1034`：`def _catch_up_projection_best_effort(projection_catchup_port: ProjectionCatchupPort | None)`
  - 两个函数体 `try: port.catch_up_projection(); except Exception: pass` 完全相同
- **影响**: 若未来需要增强 best-effort 行为（如添加 logging），需要改两处。当前无运行时影响。
- **建议改法和验证点**: 将 `_catch_up_projection_best_effort` 提取到 `dayu/host/projection.py` 作为模块级公开函数 `catch_up_projection_best_effort(port: ProjectionCatchupPort | None) -> None`。admission 和 dispatch 都从 projection 导入。此修改可和 Finding 1（Protocol 迁至 projection.py）一起完成。验证：pyright + 现有测试。
- **修复风险（低）**: 纯代码组织变更。
- **严重程度（低）**: 不造成行为错误，仅增加维护成本。

## Verified Passing (8 mandatory check items)

1. **Rebuild/Catch-up 复用 ProjectionRunner**：`memory_repair.py:191-198` 创建 `ProjectionRunner(transaction_runner, (ConversationMemoryProjectionConsumer(...),))` — 确认无 memory 专用 runner 旁路。PASS。
2. **Snapshot 与 checkpoint 原子一致**：`projection.py:481-538` `_process_next_event()` 在同一个 `run_write` transaction 内依次调用 `consumer.apply_event()`（写 snapshot）然后 `advance_projection_checkpoint()`。PASS。
3. **Rebuild 不 append EventLog，不改治理状态**：`memory_repair.py:127-139` rebuild 路径仅 `reset_conversation_memory_projection()` + `_run_memory_projection_until_idle()`，均不调用 `EventLogStore.append_event()`。PASS。
4. **Reset 按 consumer 粒度安全清理**：`durable/memory.py:426-476` `reset_conversation_memory_projection()` 通过 `WHERE consumer_id = ?` 子查询删除 diagnostics/items/snapshots + projection_failures + projection_checkpoints，全部 scoped by consumer_id。PASS。
5. **Provenance 保留原始 event_id/event_sequence**：`durable/memory.py:171-193` `_memory_projection_event_from_view()` 原样传递 `event.event_sequence`、`event.event_id`、`event.payload_ref`、`event.payload_digest`。PASS。
6. **Snapshot digest 稳定**：`durable/memory.py:848-858` `_validate_snapshot_digest()` 调用 `calculate_memory_snapshot_digest(snapshot)`；digest 计算基于 canonical JSON（content only，不含 built_at/diagnostic_id/recorded_at）。测试 `test_snapshot_rebuild_preserves_provenance_and_digest_is_deterministic` 确认同事件+同 policy 产生稳定 digest。PASS。
7. **Best-effort catch-up 不影响主命令结果**：`admission.py:2478-2481` 和 `dispatch.py:1043-1046` 均 `except Exception: pass`。测试 `test_start_run_survives_after_commit_projection_catchup_failure`、`test_terminal_closeout_survives_after_commit_projection_catchup_failure`、`test_scheduler_queue_promotion_survives_projection_catchup_failure` 确认 admission/promotion 在 catch-up 抛出时返回值不受影响。PASS。
8. **无 weak typing / Any / 魔法字符串 / 反向依赖**：memory_repair.py 全量使用 typed dataclass、`ProjectionConsumerId`、模块常量，无 `Any`、无 `object`、无 `hasattr`/`getattr` 投机。PASS 已验证。

## Open Questions

- 无。

## Residual Risk

1. **Worker 事件消费路径的 projection lag**（关联 Finding 2）：worker 运行期间 `TOOL_RESULT_ACCEPTED` / `EPISODE_SUMMARY_ACCEPTED` 写入 EventLog 后不触发 catch-up。单 worker 长运行场景下 memory projection 可能滞后至 worker 终态 closeout 才追平。当前 designer intent 接受此窗口（S4 plan 声明 best-effort，无需实时）。建议在 S5 或后续 phase 评估是否需要 periodic catch-up 机制。**Owner: S5 planning**。

2. **resolve_wait 路径的 catch-up 覆盖**：`resolve_wait` 是 Phase 5+ 功能，当前未在 S4 scope 内。若 resolve_wait 也会 append `TOOL_RESULT_ACCEPTED` 等 memory-relevant canonical fact，需在对应 phase 补齐 catch-up hook。**Owner: future wait/resolve phase**。

3. **Catch-up 失败可观测性**（关联 Finding 3）：当前 catch-up 失败仅在 projection_failures 表中可见，无运行时日志/告警。若 catch-up 持续静默失败，可能长期不被发现。**Owner: S4 后续 polish 或运维监控配置**。

## Verdict

**No blocking findings.** P9-S4 实现正确满足 plan 要求：rebuild/catch-up 复用现有 ProjectionRunner，snapshot 与 checkpoint 原子一致，reset 按 consumer 粒度安全清理，provenance 保留原始引用，digest 稳定，best-effort catch-up 不影响主命令结果。两个 Medium 级 finding（ProjectionCatchupPort 耦合位置、worker 路径 catch-up 覆盖 gap）属于 maintainability 和设计取舍问题，不构成 S4 阻止合入的理由。建议在合入前或 S5 中处理 Finding 1（Protocol 迁至 projection.py）。
