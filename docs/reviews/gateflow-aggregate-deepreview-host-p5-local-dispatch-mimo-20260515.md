# Host Phase 5 Aggregate Deep Review

- **Reviewer**: AgentMiMo
- **Date**: 2026-05-15
- **Branch**: `feat/host-phase5-local-dispatch`
- **Scope**: Phase 5 全部 6 slices (P5-S1..P5-S6) 聚合审查
- **Status**: PASS

## 审查范围

Phase 5 实现 RunInputBuilder + LocalProxy + dispatch scheduler + EngineEvent ingest + terminal closeout + active cancel + session cancel + EOF/crash closeout。审查覆盖以下 6 个维度：

1. RunInputBuilder no-tool provider + LocalProxy/scheduler + EngineEvent ingest + active cancel + session cancel + EOF/crash closeout 一致性
2. 状态机/事件事实与 design.md 合规
3. 分层/import 边界
4. Schema/测试迁移
5. README/总控文档准确性
6. 验证完备性与残余风险

## 真源文档

- `docs/host/design.md` — 架构与状态机真源
- `docs/host/implementation-control.md` — 实施总控
- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` — Phase 5 plan (877 行)

## 验证基线

| 项目 | 结果 |
| --- | --- |
| pyright | 0 errors |
| pytest | 254 passed |

## Findings

### Severity: PASS (无 blocking finding)

Phase 5 实现与 plan 完全对齐，无 blocking issue。以下为各维度详细审查结论。

---

## 1. 端到端一致性

### 1.1 RunInputBuilder no-tool provider

**PASS** — `run_input.py` 实现正确。

- `create_no_tool_run_input_builder` 工厂返回 `RunInputBuilder`，注入 `NoopToolSchemaSnapshotProvider`（返回 `disable_tools=True, tool_schemas=()`）、`NoToolExecutorProvider`（返回 `ToolCancelledOutcome`）。
- `PolicySnapshot` 校验 `allow_tool_calls=False` 且 `policy_snapshot_ref` 非空。
- `_validate_no_tool_snapshot` 在 `build()` 中强制校验 no-tool 约束。
- Messages 顺序：scene → memory → compact → continuity → current user input，与 plan 一致。
- Durable providers: `DurableCurrentRunFactProvider` 读取 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED`；`DurableSessionContinuityProvider` 读取历史 canonical events 按 `event_sequence` 排序。

**Evidence**: `dayu/host/run_input.py` L1-L982，完整实现。

### 1.2 LocalProxy / Scheduler

**PASS** — `local_proxy.py` + `dispatch.py` 实现正确。

- `DefaultLocalEngineWorkerFactory.create_worker()` 返回 `DefaultLocalEngineWorker`。
- `DefaultLocalEngineWorker.accept()` 返回 `_DefaultLocalWorkerHandle`，基于 uuid 生成 `local_worker_id`。
- `_DefaultLocalWorkerHandle.events()` 惰性调用 `run_agent_messages(request)`。
- `_DefaultLocalWorkerHandle.cancel()` 为 no-op（Host cancellation token 观察取消）。
- `HostDispatchScheduler` 流程：`wake_dispatch` → `drain_once` → `_dispatch_one` → mark_waiting_for_lane → lane acquire → mark_dispatching_after_recheck → pre-call recheck → start_worker → accept_worker_running → consume_worker_events。
- Lane token 在 `_consume_worker_events` 的 `finally` 块中释放（非 cancel 路径），确保 capacity 归还。

**Evidence**: `dayu/host/local_proxy.py` L1-L128；`dayu/host/dispatch.py` L615-L878。

### 1.3 EngineEvent ingest

**PASS** — `engine_ingest.py` 实现正确。

- `EngineEventIngestor.ingest()` 验证 envelope shape → 检查 durable context → 处理 duplicate → late rejection → 路由到具体 handler。
- Event 路由：
  - `FINAL_ANSWER` → `_close_terminal(succeeded)`
  - `RUN_FAILED` → `_close_terminal(failed)` with recoverable diagnostic
  - `RUN_CANCELLED` → `_close_active_cancel`
  - `CONTEXT_COMPACTION_REQUESTED` → diagnostic + FAILED
  - `RUN_SUSPENDED` / `TOOL_AWAITING` → diagnostic + FAILED
  - `USAGE_REPORTED` → projection_signal
  - preview events → PREVIEW
  - `PROVIDER_PROTOCOL_ERROR` → diagnostic
- Event ID 公式：`event-engine-` + sha256({execution_id, worker_event_index, event_class, event_type, sub_index})，与 plan 完全一致。
- `_validate_candidate_shape` 校验 worker_event_index > 0、observed_at 为 UTC aware、envelope 匹配 engine_event session_id/run_id。
- `_late_rejection_reason` 在 Run 或 Attempt 已有 terminal_event_id 时拒绝 late event。

**Evidence**: `dayu/host/engine_ingest.py` L1-L1813。

### 1.4 Active cancel

**PASS** — 活跃取消路径正确。

- Attempt `RUNNING` → `cancel_run` 追加 `CANCEL_REQUESTED` + `RUN_CANCELLING` → 通过 `ActiveWorkerRegistry` 传播 → Engine emit `run_cancelled` → Host `_close_active_cancel` 追加 `ATTEMPT_CANCELLED` + `RUN_CANCELLED`。
- `_close_active_cancel` 先校验 EventLog 中存在 `RUN_CANCELLING` event，提取 `cancel_request_event_id`，再调用 `active_cancel_closeout_in_transaction` 完成 CAS 终态收口。
- `_HostCancellationToken` 实现 Host-writable、Engine-observable 取消，含 `request_cancel`/`is_cancelled`/`cancel_reason`/`requested_at`。

**Evidence**: `dayu/host/engine_ingest.py` L610-L689；`dayu/host/dispatch.py` `_HostCancellationToken` 类。

### 1.5 Pre-worker cancel

**PASS** — `cancel_predispatch_starting_in_transaction` 正确处理。

- `_dispatch_record_is_direct_cancelable`：status ∈ (PENDING, WAITING_FOR_LANE) 或 (DISPATCHING + worker_accepted_at IS NULL)。
- 直接收口为 `CANCELLED`，不经过 `CANCELLING`。
- 与 plan 中"pre-worker → immediate CANCELLED, NOT CANCELLING"一致。

**Evidence**: `dayu/host/durable/run_transition.py` `cancel_predispatch_starting_in_transaction`。

### 1.6 Session cancel

**PASS** — `cancel_session_runs` 实现正确。

- queued/pre-worker → immediate CANCELLED。
- active RUNNING → CANCELLING。
- WAITING/RECOVERING → UNSUPPORTED_OPERATION（无 partial mutation）。
- 在一个 write transaction 内批量处理，commit 后通过 registry best-effort 传播 active cancel。

**Evidence**: `dayu/host/command.py` 中 `cancel_session_runs` 实现。

### 1.7 Terminal closeout

**PASS** — closeout 表与 plan 一致。

| 场景 | Run 终态 | Attempt 终态 |
| --- | --- | --- |
| startup failure | FAILED | FAILED |
| clean EOF without terminal | FAILED | FAILED |
| worker crash / stream error | LOST | LOST |
| unsupported recovery | FAILED | FAILED |

- `close_clean_eof` 和 `close_worker_lost` 合成 EngineEvent 并通过正常 terminal closeout 路径处理。
- `_with_terminal_promotion_retry` 对成功或重复 terminal closeout 触发 queue promotion wakeup。

**Evidence**: `dayu/host/engine_ingest.py` `close_clean_eof`、`close_worker_lost`、`_with_terminal_promotion_retry`。

### 1.8 EOF/crash closeout

**PASS** — `_consume_worker_events` 正确处理。

- `StopAsyncIteration` → `close_clean_eof`（terminal_seen=False 时）。
- 其它 Exception → `close_worker_lost`（含 last_accepted_event_id）。
- `asyncio.CancelledError` → 直接 re-raise。
- `finally` 块：discard handle → unregister active registry → close handle → release lane token。

**Evidence**: `dayu/host/dispatch.py` L829-L878。

---

## 2. 状态机/事件事实合规

**PASS** — 所有状态迁移与 design.md 一致。

| 概念 | 设计定义 | 实现状态 |
| --- | --- | --- |
| Run 状态集 | QUEUED/RUNNING/WAITING/CANCELLING/RECOVERING/SUCCEEDED/FAILED/CANCELLED/LOST | 一致 |
| Attempt 状态集 | STARTING/RUNNING/SUCCEEDED/FAILED/CANCELLED/SUSPENDED/STEERED/LOST | 一致 |
| Dispatch record 状态 | PENDING/WAITING_FOR_LANE/DISPATCHING/CANCELLED | 一致 |
| First-wins terminal | CAS + late reject | 一致 |
| Lane token 语义 | runtime capacity only | 一致 |
| EngineEvent 身份 | Engine 公共不携带 attempt_id/execution_id | 一致 |
| Event ID 派生 | sha256({execution_id, worker_event_index, event_class, event_type, sub_index}) | 一致 |

**Evidence**: `dayu/host/durable/state.py` 枚举定义；`dayu/host/durable/run_transition.py` transition primitives；`dayu/host/engine_ingest.py` event ID 与 late rejection。

---

## 3. 分层 / Import 边界

**PASS** — 边界合规。

### 3.1 Host → Engine

允许方向。Host 导入 `dayu.engine.contracts.*`（公共契约）和 `dayu.engine.run_agent_messages`（LocalProxy 边界调用 Engine 公共 entry）。与 design.md "dayu.host 可以在 LocalProxy 边界沿依赖方向调用 Engine public entry" 一致。

验证：`dayu/host/` 下无 `from dayu.fins`、`from dayu.service`、`from dayu.ui` 导入。

### 3.2 Runtime 边界

`dayu/runtime/` 无任何 `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins` 导入。仅有 docstring 中的约束声明。

### 3.3 Host 内部模块可见性

`dayu.host.durable` 不从 `dayu.host` 包根导出，不进入 `dayu.host.api`。`dayu.host.api.__all__` 只包含 request、snapshot、status、error、context、stream cursor 与本地执行配置契约类型。

**Evidence**: Grep 验证；`tests/host/test_import_boundary.py`；`dayu/host/README.md` 架构边界节。

---

## 4. Schema / 测试迁移

**PASS** — 迁移正确。

### 4.1 Schema

- `HOST_SCHEMA_VERSION = 3`，Phase 5 bump。
- Dispatch record DDL 有完整 CHECK 约束覆盖 4 种状态的 nullability 规则：
  - pending: 所有 dispatch 字段 NULL
  - waiting_for_lane: waiting_for_lane_at/lane_name/owner_host_instance_id NOT NULL，其余 NULL
  - dispatching: lane 字段 NOT NULL, cancel refs NULL, worker accept refs 全 NULL 或全 NOT NULL
  - cancelled: cancel refs NOT NULL, worker accept refs NULL

### 4.2 测试

Phase 5 专用测试文件：

| 测试文件 | 覆盖范围 |
| --- | --- |
| `test_run_input_builder.py` | durable prompt、canonical continuity、no-tool request |
| `test_dispatch_scheduler.py` | pending/waiting/dispatching/worker accept、pre-accept cancel race、lane acquire timeout、worker startup timeout |
| `test_local_proxy_engine_ingest.py` | LocalProxy Engine entry boundary、final answer/failed/cancelled/usage/unsupported recovery mapping、clean EOF/worker lost closeout |
| `test_engine_ingest_mapping.py` | EngineEvent ingest mapping 细粒度 |
| `test_active_cancel_dispatch.py` | active cancel durable primitive |
| `test_public_cancel_session_runs.py` | session-scope cancel 子集 |
| `test_phase5_local_execution_integration.py` | no-tool Engine 闭环集成（public start_run + real scheduler + runtime lane + fake local worker） |
| `test_import_boundary.py` | Host import 边界 |

**Evidence**: `tests/host/` 目录；pyright 0 errors；254 pytest passed。

---

## 5. README / 总控文档准确性

**PASS** — 文档与实现一致。

### 5.1 `dayu/host/README.md`

完整覆盖 Phase 5 所有新增能力：
- RunInputBuilder no-tool boundary ✓
- dispatch scheduler / LocalProxy baseline ✓
- EngineEvent ingest mapping ✓
- Durable Foundation 节详述 dispatch record 四状态、worker accept refs、active cancel durable primitive ✓
- Internal Admission 节覆盖 session-scope cancel 子集 ✓

### 5.2 `dayu/README.md`

术语约定节准确反映 Phase 5 相关概念：
- RunInputBuilder 定义 ✓
- EngineEvent stream / canonical event identity / execution_id 术语 ✓
- dispatching 语义（非 lease/fencing）✓
- WorkerProxy / EngineWorker 边界 ✓

### 5.3 `tests/README.md`

Phase 5 测试文件全部列出：
- test_dispatch_scheduler ✓
- test_local_proxy_engine_ingest ✓
- test_phase5_local_execution_integration ✓
- 测试覆盖描述准确 ✓

### 5.4 `docs/host/implementation-control.md`

Phase 5 slice 定义与实现对齐。

**Evidence**: 各 README 文件内容与代码实现交叉比对。

---

## 6. 验证完备性与残余风险

### 6.1 验证完备性

| 维度 | 状态 |
| --- | --- |
| pyright 类型检查 | 0 errors ✓ |
| pytest 单元/集成测试 | 254 passed ✓ |
| 状态机全路径覆盖 | ✓ |
| Import 边界测试 | ✓ |
| Schema CHECK 约束 | ✓ |
| 多进程 durable invariant | ✓（admission 测试覆盖） |
| Terminal closeout 全场景 | ✓ |
| Cancel 全路径 | ✓（active + pre-worker + session） |

### 6.2 残余风险

| 风险 | 严重性 | 说明 |
| --- | --- | --- |
| Engine 协议违规 `run_cancelled` 无 prior `RUN_CANCELLING` | LOW | `_close_active_cancel` 记录 diagnostic 但不强制 terminal closeout；Run 保持 RUNNING 直到 EOF/crash closeout 安全网触发。属于防御性设计，非 bug。 |
| `_DefaultLocalWorkerHandle.cancel()` 为 no-op | LOW | 当前依赖 Host cancellation token 观察取消。Engine 需要主动 poll `is_cancelled()`。若 Engine 未及时响应取消，Run 会在 `cancel_active_worker` 传播后等待 Engine 自然终止。 |
| no-tool Phase 5 不覆盖 ToolRuntime | NONE | Phase 5 scope 明确为 no-tool baseline；ToolRuntime 属于后续 phase。 |
| RemoteProxy 未实现 | NONE | Phase 5 scope 为 local dispatch；RemoteProxy 属于后续 phase。 |
| policy provider 未集成 | NONE | Phase 5 使用 facade 内部默认 execution target；完整 policy 属于后续 phase。 |

---

## Verdict

**PASS** — Phase 5 全部 6 slices 实现与 plan、design.md 完全对齐，无 blocking finding。状态机、事件事实、分层边界、schema 迁移、测试覆盖和文档同步均通过审查。残余风险均为 LOW 或 NONE，不阻塞当前 phase 完成。
