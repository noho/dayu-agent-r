# P5 Design Conformance Review

## Scope

- Mode: all repository (P5 slice conformance)
- Branch: feat/host-phase5-local-dispatch
- Base: main
- Reviewer: AgentMiMo
- Output file: docs/reviews/p5-design-conformance-review-mimo-20260515.md
- Included scope: Host P5 production code, durable layer, runtime lane usage, Engine contract boundary, import boundary tests, P5 integration tests
- Excluded scope: Service / UI / Fins layers, Engine internal implementation, config module
- Parallel review coverage: 无

## Verdict: PASS

P5 实现与 `docs/host/design.md`、`docs/host/implementation-control.md`、`docs/host/phase5-runinputbuilder-local-dispatch-plan.md` 高度一致。8 个审查 lens 均未发现 blocking design deviation。可进入 controller adjudication。

## Findings

未发现实质性问题。

## Non-blocking Design Drift

无。

## Production Wiring Risks

无。P5 的 8 条生产接线均按 design 正确连接：

| 接线项 | 文件 | 验证 |
| --- | --- | --- |
| command facade | `command.py` | `create_host_command_handle` 组装 `HostAdmissionService` + `HostDispatchScheduler` |
| admission wakeup | `admission.py:2272` + `dispatch.py` | `AdmissionWakeupPort.wake_dispatch` / `wake_queue_promotion` 正确注入 |
| scheduler open/close | `dispatch.py:228-265` | `HostDispatchScheduler.open()` / `close()` 生命周期与 command handle 一致 |
| lane acquire/release | `dispatch.py:375-460` | `LaneController.acquire` + finally 释放，cancel 不直接释放 lane |
| active cancel registry | `dispatch.py:535-595` | `ActiveWorkerRegistry` 注册/注销，cancel 传播通过 `cancel_active_worker` |
| LocalProxy factory | `local_proxy.py:21-27` | `DefaultLocalEngineWorkerFactory` 创建 `DefaultLocalEngineWorker` |
| EngineEventIngestor wakeup | `dispatch.py:430-445` | worker accept 后调用 `accept_worker_running` 唤醒 ingest |
| queue promotion | `admission.py:595-618` | terminal closeout 后调用 `_promote_after_release`，通过 `wake_queue_promotion` 唤醒 |

## Deferred Phase Readiness

P5 正确推迟了后续 phase 的所有功能，并在正确路径上使用 stub/no-op/fail-fast：

| 后续 Phase | 推迟项 | 当前处理 | owner 线索 |
| --- | --- | --- | --- |
| P6 | ToolRuntime / fetch_more | `NoToolExecutor` 返回 `ToolCancelledOutcome` | `run_input.py:155-167` |
| P7 | WAITING / resolve_wait | `command.py:464` + `admission.py:2209` raise `UNSUPPORTED_OPERATION` | 注释明确标注 Phase 7 |
| P8 | Memory snapshot | `NoopMemorySnapshotProvider` 返回空 | `run_input.py:89-97` |
| P9 | Context Governance | 未实现；RunInputBuilder 构造 no-tool request | design.md §49 |
| P10 | Compact artifact | `NoopCompactArtifactProvider` 返回空 | `run_input.py:100-108` |
| P11 | Recovery / takeover | `command.py:517` raise `UNSUPPORTED_OPERATION` | 注释明确标注 Phase 11 |
| P12 | Observer / Sink / Projection | 未实现 | 不在 P5 scope |
| P13 | RemoteProxy | `WorkerKind` 枚举含 `REMOTE`，但 P5 只使用 `LOCAL` | `state.py:64-68` |

所有 noop provider 均为 frozen dataclass，返回类型安全的空值，不引入运行时副作用。`UNSUPPORTED_OPERATION` 的错误消息明确标注了后续 phase owner。

## Evidence by File / Line

### Lens 1: Host 强治理真源，Engine 不理解 Host Attempt / dispatch / recovery

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `EngineEvent` 只含 `session_id`、`run_id`、`type`、`data`、`metadata`，无 `attempt_id` / `execution_id` / `dispatch_record_id` | `engine_events.py` | 429-448 |
| `LocalEngineEnvelope` 承载 Host identity（attempt_id, execution_id, dispatch_record_id），不泄漏到 EngineEvent | `engine_ingest.py` | 50-85 |
| Engine `run_agent_messages` 签名只接收 `AgentRunRequest`，不接收 Host 治理参数 | `engine/agent.py` | contract boundary |
| `EngineEventCandidate = LocalEngineEnvelope + worker_event_index + engine_event`，Host identity 在 envelope 层隔离 | `engine_ingest.py` | 87-107 |

### Lens 2: LocalProxy / EngineWorker envelope 正确承载 Host identity；EngineEvent 保持公共

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `DefaultLocalEngineWorker.accept()` 返回 `_DefaultLocalWorkerHandle`，不修改 EngineEvent 结构 | `local_proxy.py` | 43-100 |
| `EngineEventIngestor` 从 `EngineEventCandidate.envelope` 读取 Host identity，从 `engine_event` 读取 Engine 语义 | `engine_ingest.py` | 200-260 |
| terminal 映射从 `EngineEventType` 到 Host event type，不注入 Host 字段到 EngineEvent | `engine_ingest.py` | 460-570 |

### Lens 3: Dispatch record 仅为诊断 / duplicate dispatch suppression / recovery 判断

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `DispatchRecordRow` docstring 明确："active worker truth 只能由 ATTEMPT_RUNNING 与 Attempt row RUNNING 表达" | `state.py` | 174-180 |
| `DispatchRecordStatus` docstring："不是 lease / fencing / owner truth" | `state.py` | 50-62 |
| dispatch.py 使用 `Attempt.status == RUNNING` 作为 active worker 真源，而非 dispatch record status | `dispatch.py` | 535-595 |
| `_dispatch_record_is_direct_cancelable` 只检查 pre-accept 窗口，不作为 owner 判定 | `run_transition.py` | 2281-2300 |
| schema CHECK 约束 dispatch record status 只有 `pending/waiting_for_lane/dispatching/cancelled` | `schema.py` | 348-349 |

### Lens 4: UI -> Service -> Host -> Engine 依赖方向；dayu.runtime 层中立

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `HOST_FORBIDDEN_PREFIXES` 禁止 Host import config/fins/service/ui | `test_import_boundary.py` | 24-29 |
| `RUNTIME_FORBIDDEN_PREFIXES` 禁止 runtime import host/engine/service/ui/fins | `test_import_boundary.py` | 30-36 |
| `HOST_ENGINE_CONTRACT_ALLOWED_MODULES` 限定 Host 可 import Engine contracts 的模块 | `test_import_boundary.py` | 38-44 |
| `lane.py` docstring："不表达 Host durable truth / lease / fencing / Attempt owner" | `lane.py` | 1-7 |
| `LaneController` 不读取 Host 默认路径，不保存 Host / Fins / Engine 字段 | `lane.py` | 343-348 |
| Host `__init__.py` 不导出内部模块（dispatch, engine_ingest, local_proxy, run_input, admission, durable/*） | `__init__.py` | 1-153 |

### Lens 5: RunInputBuilder 只通过 typed providers 从 durable facts 构造

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `RunInputBuilder` 接收 8 个 typed provider protocol，不接收 untyped bag | `run_input.py` | 50-130 |
| `DurableCurrentRunFactProvider` 从 `HostTransactionRunner` 读取 durable facts | `run_input.py` | 200-240 |
| `DurableSessionContinuityProvider` 调用 `read_run_input_continuity_events` 读取 EventLog canonical facts | `run_input.py` | 245-310 |
| `DefaultSceneParameterProvider` 返回 typed `SceneParameterSnapshot`，不读取全局配置 | `run_input.py` | 315-360 |
| `StaticPolicySnapshot` 强制 `allow_tool_calls=False` | `run_input.py` | 408-430 |
| message 顺序：scene -> memory(empty) -> compact(empty) -> continuity -> user_input | `run_input.py` | 160-180 |
| `create_no_tool_run_input_builder` 工厂函数正确装配所有 P5 providers | `run_input.py` | 960-1010 |

### Lens 6: Production wiring 正确性

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `cancel_run` pre-dispatch 路径：pending/waiting_for_lane/pre-accept dispatching -> direct cancel | `admission.py` | 2080-2100 |
| `cancel_run` active 路径：RUNNING -> CANCELLING -> propagate to worker | `admission.py` | 2240-2250 |
| `cancel_session_runs`：WAITING/RECOVERING -> UNSUPPORTED_OPERATION | `admission.py` | 2209-2210 |
| `cancel_session_runs`：queued -> CANCELLED, pre-dispatch -> CANCELLED, active -> CANCELLING | `admission.py` | 1362-1366 |
| queue promotion 后 wake dispatch scheduler | `admission.py` | 613-617 |
| terminal closeout 后 trigger promotion | `admission.py` | 584-593 |
| dispatch scheduler finally 块释放 lane | `dispatch.py` | 460-475 |
| worker accept -> append ATTEMPT_RUNNING + mark Attempt RUNNING | `run_transition.py` | 833-899 |

### Lens 7: P5 不提前实现后续 phase

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `retry_run` raise UNSUPPORTED_OPERATION | `command.py` | 464 |
| `replay_run` raise UNSUPPORTED_OPERATION | `command.py` | 481 |
| `resolve_wait` raise UNSUPPORTED_OPERATION | `command.py` | 498 |
| `purge_session` raise UNSUPPORTED_OPERATION | `command.py` | 517 |
| `cancel_session_runs` 对 WAITING/RECOVERING raise UNSUPPORTED_OPERATION | `admission.py` | 1339-1347 |
| Run status enum 包含 `waiting`/`recovering` 但 P5 不产生这些状态 | `schema.py` | 226-232 |
| Attempt status enum 包含 `suspended`/`steered` 但 P5 不产生这些状态 | `schema.py` | 302-310 |
| `NoToolExecutor` 对任何 tool call 返回 `ToolCancelledOutcome` | `run_input.py` | 155-167 |

### Lens 8: 后续 phase 接线点按 design 预留

| 证据 | 文件 | 行号 |
| --- | --- | --- |
| `RunInputBuilder` 接口预留 `ToolSchemaSnapshotProvider` / `ToolExecutor` provider slots | `run_input.py` | 70-85 |
| `NoopToolSchemaSnapshotProvider` / `NoToolExecutorProvider` 作为正确 noop 占位 | `run_input.py` | 120-167 |
| `WorkerKind` 枚举含 `REMOTE` 为 RemoteProxy 预留 | `state.py` | 64-68 |
| `RunStatus` 含 `WAITING` / `RECOVERING` 为 P7/P11 预留 | `api.py` | RunStatus enum |
| `AttemptStatus` 含 `SUSPENDED` / `STEERED` 为 P7/P10 预留 | `api.py` | AttemptStatus enum |
| `AdmissionWakeupPort` protocol 可扩展，当前 noop 实现不阻碍后续接入 | `admission.py` | 60-80 |

## Residual Risks

| 风险 | owner | 说明 |
| --- | --- | --- |
| P5 集成测试覆盖 | Host team | `test_phase5_local_execution_integration.py` 覆盖了 happy path 和 terminal closeout，但 cancel during dispatching 和 lane timeout 路径的端到端覆盖需确认 |
| dispatch scheduler worker_startup_timeout 路径 | Host team | `dispatch.py` 使用 `terminal_closeout_in_transaction` 处理超时，但多进程竞态下的 timeout + cancel 并发场景需要更多测试 |
| `cancel_session_runs` 幂等重放 | Host team | 幂等重放路径已有实现，但重放时 idempotent_replay=True 不返回 active_cancel_targets 的行为需在集成测试中验证 |

## Open Questions

无。
