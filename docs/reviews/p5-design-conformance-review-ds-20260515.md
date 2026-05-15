# P5 Design Conformance Review

## Scope

- Mode: Design conformance review (P5 vs design docs)
- Branch: feat/host-phase5-local-dispatch
- Review date: 2026-05-15 14:50
- Output file: docs/reviews/p5-design-conformance-review-ds-20260515.md
- Included scope: dayu/host/api.py, command.py, admission.py, dispatch.py, local_proxy.py, run_input.py, engine_ingest.py, read_api.py, tooling.py; dayu/host/durable/ (schema/state/run_transition/event_log/idempotency/transaction); dayu/runtime/lane.py, cancellation.py; dayu/engine/contracts/engine_events.py, agent.py; tests/host, tests/runtime, tests/contracts, tests/engine (P5-relevant)
- Excluded scope: dayu/fins/, dayu/service/, dayu/ui/ (not in P5 scope)
- Parallel review coverage:
  - Agent a0c6ff6b63e476957: architecture boundaries, imports, EngineEvent contract
  - Agent a609ea880d4916923: durable schema/state/run_transition/event_log
  - Agent a2462c726418c6feb: dispatch/local_proxy/engine_ingest (partial)
  - Agent a54809ce0829307a5: run_input/admission/command cancel paths
  - Agent a8234d5de4aa83851: all P5 test files
  - Direct review: cross-cutting verification, schema DDL, key CAS helpers, wiring, cancel flows

## Verdict

**PASS** — 无阻塞性设计偏离。实现与 docs/host/design.md、docs/host/implementation-control.md 和 docs/host/phase5-runinputbuilder-local-dispatch-plan.md 一致。可进入 controller adjudication。

## Findings

### 1-NONBLOCKING-中-ATTEMPT_RUNNING_payload缺少§3.5要求的字段

- **入口/函数**: `_attempt_running_event_request` (私有辅助)
- **文件(行号)**: dayu/host/durable/run_transition.py:1465-1506
- **输入场景**: WorkerProxy accepted 后 Host append ATTEMPT_RUNNING canonical fact
- **实际分支**: 当前 payload 包含 attempt_id, execution_id, dispatch_record_id, worker_kind, execution_target, reason
- **预期行为**: 按 plan §3.5，ATTEMPT_RUNNING payload 必须包含: attempt_id, execution_id, dispatch_record_id, worker_kind, execution_target, local_worker_id, worker_accepted_at, lane_name, lane_claim_id
- **实际行为**: 缺少 local_worker_id, worker_accepted_at, lane_name, lane_claim_id；多出未在 §3.5 中指定的 reason 字段
- **直接证据**: AcceptWorkerRunningInput dataclass (run_transition.py:269-289) 未包含 local_worker_id 字段；函数签名未接收 lane_name/lane_claim_id（但这些值存在于调用方可用的 dispatch_record 中）
- **影响**: 诊断不完整 — ATTEMPT_RUNNING EventLog row 无法回溯是哪个本地 worker、哪个 lane 受理了此次 dispatch。不影响状态机正确性
- **建议改法和验证点**: 在 AcceptWorkerRunningInput 中增加 local_worker_id 字段；在 _attempt_running_event_request 中从 dispatch_record 补充 lane_name, lane_claim_id，从 request.occurred_at 补充 worker_accepted_at；更新相关测试断言
- **修复风险（低）**: 仅影响 EventLog payload 字段，不改变状态迁移
- **严重程度（中）**: 非阻塞 — active worker truth 由 Attempt RUNNING 状态表达，payload 缺失不破坏治理语义

### 2-NONBLOCKING-低-compact_artifact_messages排序未列入plan

- **入口/函数**: `RunInputBuilder.build()`
- **文件(行号)**: dayu/host/run_input.py:688-699
- **输入场景**: 构造 AgentRunRequest.messages
- **实际分支**: messages 顺序为: system → memory → compact artifact → continuity → user input
- **预期行为**: plan §3.4 列出的顺序为: system → memory → continuity → user input（未列出 compact artifact slot）
- **实际行为**: compact artifact 消息插在 memory 与 continuity 之间
- **直接证据**: run_input.py:695 `*compact.messages` 位于 memory messages 之后、continuity messages 之前
- **影响**: Phase 5 无实际影响（compact 始终为空 noop），但 Phase 9/10 替换 noop provider 后消息顺序可能与 plan 预期不一致
- **建议改法和验证点**: 方案A — 在 plan §3.4 中补充 compact artifact 位置；方案B — 调整代码顺序使 compact 排在 continuity 之后
- **修复风险（低）**
- **严重程度（低）**: 非阻塞 — Phase 5 行为正确，未来 phase 可修正

## Architecture Boundary Verification

以下 8 项架构审查全部通过（基于 Agent a0c6ff6b63e476957 并行审查 + 直接验证）：

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | EngineEvent 不含 Host identity | PASS | engine_events.py:430-448 — EngineEvent 字段为 occurred_at, session_id, run_id, type, data, metadata；无 attempt_id/execution_id/dispatch_record_id |
| 2 | UI→Service→Host→Engine 依赖方向 | PASS | 无反向 import；Engine 不 import dayu.host；Host 不 import dayu.fins/service/ui |
| 3 | dayu.runtime 层中立 | PASS | runtime/lane.py, runtime/cancellation.py 不 import dayu.engine/host/service/ui/fins |
| 4 | Host __init__.py 导出清洁 | PASS | 仅导出公共类型与 facade 函数，无内部 durable helper |
| 5 | Dispatch record 非 lease/fencing | PASS | state.py:52-55 文档明确声明；所有 CAS helper 只做状态迁移，不授权 takeover |
| 6 | LocalProxy envelope 正确承载 Host identity | PASS | engine_ingest.py:123-146 LocalEngineEnvelope 包含 session_id/run_id/attempt_id/execution_id/dispatch_record_id；EngineEvent 保持清洁 |
| 7 | RunInputBuilder 只读 durable facts | PASS | 所有 provider 从 EventLog/Run/Attempt 行读取，不访问 UI/Service 临时状态或全局配置 |
| 8 | Host 不 import fins/service/ui | PASS | 全量 import 检查无违规 |

## Production Wiring Verification

| # | 接线项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | Command facade 正确 | PASS | command.py — create_host_command_handle 拒绝 local_execution（需显式 open scheduler）；ensure_session/create_session/start_run/cancel_run 等 facade 完整 |
| 2 | Admission wakeup port | PASS | admission.py:145-162 AdmissionWakeupPort Protocol 定义 wake_dispatch + wake_queue_promotion；admission.py:2272-2288 _wake_dispatch_if_needed 在 commit 后调用 |
| 3 | Scheduler open/close | PASS | dispatch.py:318-370 HostDispatchScheduler.open() 创建 LaneController 并注册 host instance；close() 取消 active workers 并 close lane controller |
| 4 | Lane acquire/release | PASS | dispatch.py:475-508 — acquire 成功持有 token，_dispatch_one 中所有异常/取消路径均 release；_consume_worker_events finally (827-923) release lane token |
| 5 | Active cancel registry | PASS | dispatch.py:137 ActiveWorkerRegistry 按 (attempt_id, execution_id) 注册/取消；command.py:397-408 _propagate_active_cancel_targets post-commit 传播 |
| 6 | LocalProxy factory | PASS | local_proxy.py:26-59 — DefaultLocalEngineWorkerFactory/DefaultLocalEngineWorker 调用 run_agent_messages |
| 7 | EngineEventIngestor wakeup port | PASS | engine_ingest.py:220-247 — 接收 AdmissionWakeupPort；terminal closeout 后触发 queue promotion |
| 8 | Queue promotion | PASS | dispatch.py:386-398 wake_queue_promotion 创建 admission service 并 promote；admission.py:2306 terminal closeout 后触发 |

## Deferred Phase Readiness

按 plan §1.3 非目标与 §8 deferred owner 逐项检查：

| # | 后续 phase 能力 | P5 状态 | 接线点 | Owner |
|---|-----------------|---------|--------|-------|
| 1 | ToolRuntime/fetch_more | 未实现 | NoToolExecutor (run_input.py:506-531) 作为 noop 防线；Engine 若发工具调用返回 ToolCancelledOutcome；ingest 收到 tool_awaiting → FAILED | Phase 6 |
| 2 | WAITING/resolve_wait | 未实现 | tool_awaiting/run_suspended → diagnostic + FAILED (engine_ingest.py)，reason=unsupported_waiting_path, owner=phase7 | Phase 7 |
| 3 | Memory | 未实现 | NoopMemorySnapshotProvider (run_input.py:451-465) 返回空 stable layer | Phase 9 |
| 4 | Context Governance | 未实现 | context_compaction_requested 接受 budget_state=None → diagnostic + FAILED (engine_ingest.py)，reason=unsupported_recovery_policy, owner=phase10 | Phase 10 |
| 5 | Recovery/takeover | 未实现 | clean EOF → FAILED；worker crash → LOST；不创建 RECOVERING；dispatch record dispatching 仅作诊断 | Phase 11 |
| 6 | RemoteProxy | 未实现 | 仅 LocalProxy；dispatch record worker_kind 可取值 REMOTE 但生产路径未使用 | Phase 14 |
| 7 | Observer/Sink | 未实现 | usage_reported → projection_signal (engine_ingest.py)，无 projection worker | Phase 13 |
| 8 | retry/replay/steer | stable unsupported | command.py:453-520 返回 UNSUPPORTED_OPERATION | 后续 phase |

**结论**: P5 未提前硬编码任何后续 phase 能力。所有 deferred 项均有明确 owner（phase6-14），stub/noop/fail-fast 行为与 plan 一致。

## Review Gate Checklist (plan §6)

逐项确认 13 条 gate 检查：

1. **Phase 5 没有修改 EngineEvent contract** — PASS (engine_events.py 无 attempt_id/execution_id/dispatch_record_id)
2. **Dispatch record enum 包含 4 状态** — PASS (state.py:50-61: PENDING/WAITING_FOR_LANE/DISPATCHING/CANCELLED)
3. **dispatching 是 WorkerProxy accept 后最终非取消状态** — PASS (schema.py:410-429 CHECK 约束；state.py:2174-2228 mark_dispatch_worker_accepted_row 保持 dispatching)
4. **RunInputBuilder provider set 区分 real/noop** — PASS (4 real + 4 noop providers)
5. **当前用户输入只来自 durable USER_INPUT_ACCEPTED** — PASS (run_input.py:300-392 DurableCurrentRunFactProvider)
6. **usage_reported 是 projection_signal** — PASS (engine_ingest.py 映射为 EventClass.PROJECTION_SIGNAL)
7. **context compaction → diagnostic + FAILED，不进入 RECOVERING** — PASS
8. **clean EOF → FAILED；worker crash → LOST** — PASS (engine_ingest.py terminal closeout)
9. **pre-worker dispatching cancel → CANCELLED，不进入 CANCELLING** — PASS (run_transition.py:2281-2300 _dispatch_record_is_direct_cancelable)
10. **active worker cancel 只有 Attempt RUNNING 后才进入 CANCELLING** — PASS (run_transition.py:1077-1153 request_active_attempt_cancel_in_transaction)
11. **cancel_session_runs replay 不取消新 Run，WAITING/RECOVERING 无 partial mutation** — PASS (admission.py:2209-2210)
12. **lane token release 只在 scheduler/worker finally** — PASS (dispatch.py:827-923 _consume_worker_events finally)
13. **未实现 ToolRuntime/Waiting/Memory/Context Governance/Observer/RemoteProxy** — PASS

**13/13 通过。**

## Evidence by File/Line

| 文件 | 关键行号 | 审查结论 |
|------|---------|---------|
| dayu/engine/contracts/engine_events.py | 430-448 | EngineEvent 清洁，无 Host identity |
| dayu/host/durable/schema.py | 14, 348-349, 356-439 | HOST_SCHEMA_VERSION=3；4 状态 CHECK；9 诊断列；nullability 规则正确 |
| dayu/host/durable/state.py | 50-61, 174-205, 1970-2013, 2016-2074, 2077-2171, 2174-2228, 2231-2316 | DispatchRecordStatus 枚举；DispatchRecordRow；CAS helpers 全部正确 |
| dayu/host/durable/run_transition.py | 833-899, 964-1074, 1077-1153, 2227-2278, 2281-2300 | accept_worker_running；cancel_predispatch；active_cancel；precondition checks |
| dayu/host/run_input.py | 300-392, 395-448, 451-465, 468-486, 489-503, 506-531, 534-556, 661-713 | 8 providers；RunInputBuilder.build()；NoToolExecutor |
| dayu/host/dispatch.py | 275-370, 465-508, 827-923 | HostDispatchScheduler；dispatch flow；lane lifecycle |
| dayu/host/engine_ingest.py | 123-146, 149-162, 217-283 | LocalEngineEnvelope；EngineEventCandidate；ingest flow |
| dayu/host/local_proxy.py | 26-59, 62-100 | DefaultLocalEngineWorkerFactory；worker handle |
| dayu/host/command.py | 195-226, 361-450 | HostCommandHandle；cancel_run；cancel_session_runs |
| dayu/host/admission.py | 145-162, 2206-2210, 2272-2288 | AdmissionWakeupPort；WAITING/RECOVERING check；wakeup |
| dayu/host/__init__.py | 1-152 | 公共导出清洁，无内部类型泄露 |
| dayu/runtime/lane.py | full | 层中立，import boundary 合规 |
| dayu/runtime/cancellation.py | full | 层中立，import boundary 合规 |

## Residual Risks

| # | 风险 | Owner | 说明 |
|---|------|-------|------|
| 1 | ATTEMPT_RUNNING payload 字段不完整 | P5 自身 | local_worker_id/lane_name/lane_claim_id 缺失；建议 Phase 5 内修复（低风险） |
| 2 | 多进程 orphan proof 未实现 | Phase 11 | 进程崩溃后 dispatching STARTING 的 recovery classification 未处理 |
| 3 | active cancel 超时 watchdog 未实现 | Phase 11 | cancel 后 worker 无响应时，LOST closeout 依赖后续 lifecycle hardening |
| 4 | 真实 provider/network smoke 未测试 | 集成环境 | P5 以 fake local worker 覆盖 Host state machine，外部 provider 路径未验证 |
| 5 | cancel_session_runs RECOVERING 测试缺口 | P5 自身 | test_active_cancel_dispatch.py 缺少 RECOVERING no-partial-mutation 测试用例 |
| 6 | durable recheck CAS loser 测试缺口 | P5 自身 | test_dispatch_scheduler.py 缺少并发 CAS 竞争失败场景测试 |
| 7 | Usage projection worker/audit sink 未实现 | Phase 13 | P5 只持久化 usage projection_signal，无消费端 |

## Open Questions

无 — 所有审查项均有明确证据或 deferred owner。

## Conclusion

P5 实现与 docs/host/design.md、docs/host/implementation-control.md、docs/host/phase5-runinputbuilder-local-dispatch-plan.md 一致。13/13 review gate 检查通过。0 blocking design deviations。2 non-blocking deviations 已记录。7 residual risks 均有 owner。

**可进入 controller adjudication。**
