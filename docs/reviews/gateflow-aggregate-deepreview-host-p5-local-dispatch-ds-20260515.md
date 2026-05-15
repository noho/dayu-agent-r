# Host Phase 5 Aggregate DeepReview — 本地执行 Dispatch

- **审查人**：AgentDS
- **审查日期**：2026-05-15
- **审查范围**：Host Phase 5 P5-S1..P5-S6（RunInputBuilder / LocalProxy / dispatch scheduler / EngineEvent ingest / active cancel / session cancel / terminal closeout）
- **真源**：`docs/host/design.md`、`docs/host/implementation-control.md`、`docs/host/phase5-runinputbuilder-local-dispatch-plan.md`
- **分支**：`feat/host-phase5-local-dispatch`

---

## 1. 审查结论

**Verdict：PASS**

无 blocking 发现。Phase 5 全部 6 个 slice 均已按 plan 实施完毕，形成一致的本地 Engine 执行闭环。实现严格遵循 plan 规定的文件边界、schema 决策、状态迁移、provider set、EngineEvent 映射表、取消行为与异常收口。254 个 Host 测试全部通过，pyright 零报错，import 边界 AST 验证无一违反。无兼容代码、无旧 schema 残留、无 Phase 3/4 断言残留。

---

## 2. Findings

### 2.1 发现 1 — RunInputBuilder no-tool 与 LocalProxy/scheduler/EngineEvent ingest 闭环完整性

**Severity**：INFO（一致，无修复需求）

**Evidence**：

- `dayu/host/run_input.py`（982 行）：8 个 typed provider protocols 全部按 §3.4 实现。5 个 real providers（`CurrentRunFactProvider` → `DurableCurrentRunFactProvider`、`SessionContinuityProvider` → `DurableSessionContinuityProvider`、`SceneParameterProvider` → `DefaultSceneParameterProvider`、`PolicySnapshotProvider` → `StaticPolicySnapshotProvider`）+ 3 个 noop providers（Memory/Compact/ToolSchema/Executor）。输出 `disable_tools=True`、`tool_schemas=()`、`AgentPolicy.allow_tool_calls=False`、`NoToolExecutor` 返回 `ToolCancelledOutcome`。
- `dayu/host/dispatch.py`（1072 行）：`HostDispatchScheduler` 完整实现 pending → waiting_for_lane → lane.acquire → durable recheck → dispatching → worker accept → event consumption。`drain_once()` 同步 drain loop，`_consume_worker_events()` 消费 EngineEvent stream 并移交 ingest。lane token 在 finally 释放（§3.3 要求）。
- `dayu/host/engine_ingest.py`（1813 行）：`EngineEventIngestor.ingest()` 完整覆盖 §3.5 canonical payload 与 §3.6 terminal closeout 表。FINAL_ANSWER → ATTEMPT_SUCCEEDED + RUN_SUCCEEDED；RUN_FAILED → FAILED（含 recoverable diagnostic-only）；RUN_CANCELLED → active cancel closeout；CONTEXT_COMPACTION_REQUESTED → diagnostic + FAILED（含 `budget_state=None` 接受）；RUN_SUSPENDED/TOOL_AWAITING → diagnostic + FAILED；USAGE_REPORTED → projection_signal 无状态副作用；clean EOF without terminal → FAILED；worker crash/stream error → LOST。
- `dayu/host/local_proxy.py`（128 行）：`DefaultLocalEngineWorker.accept()` → `_DefaultLocalWorkerHandle`，调用 Engine public `run_agent_messages(request)`。cancel 为 no-op（Phase 5 只用 Host `_HostCancellationToken`），close 负责 aclose event generator。
- `dayu/host/command.py` 的 `cancel_run`/`cancel_session_runs` 在 commit 后通过 `_propagate_active_cancel_targets` 向 active registry 传播取消。
- EngineEvent 不携带 Host identity，Host `LocalEngineEnvelope` 负责任何绑定（§3.1）。

**Required fixes**：无。

**Residual risks**：真实 provider runner 的外部网络/provider API smoke 不属于 Phase 5 必测；当前以 fake local worker 和 Engine contract tests 覆盖 Host state machine。

---

### 2.2 发现 2 — 状态机/事件事实与设计一致性

**Severity**：INFO（一致，无修复需求）

**Evidence**：

- **Dispatch record 四个状态**：`dayu/host/durable/schema.py:348-349` DDL CHECK 确认为 `pending`、`waiting_for_lane`、`dispatching`、`cancelled`。Nullability CHECK（380-438 行）匹配 §3.2：
  - `pending`：全部诊断字段 NULL
  - `waiting_for_lane`：`waiting_for_lane_at`、`lane_name`、`owner_host_instance_id` NOT NULL；其余 NULL
  - `dispatching`：lane 诊断字段 NOT NULL；cancel refs NULL；worker accept refs 全 NULL 或全 NOT NULL（paired）
  - `cancelled`：cancel refs NOT NULL；worker accept refs NULL
- `dayu/host/durable/state.py:50` `DispatchRecordStatus` 枚举 4 个值匹配 DDL。
- **Run 9 个状态**（含 `CANCELLING`）：`schema.py:220-232` DDL CHECK 确认含 `cancelling`。Attempt 8 个状态（含 `STARTING`、`RUNNING`）：`schema.py:310` 行 DDL CHECK 确认。
- **Pre-worker direct cancel**：`cancel_starting_dispatch_record_row`（state.py:2241-2291）接受 `PENDING`/`WAITING_FOR_LANE`/pre-accept `DISPATCHING`（worker_accept_event_id IS NULL），拒绝 dispatching+worker accepted。§3.7 要求完全匹配。
- **Active cancel CANCELLING**：`request_active_attempt_cancel_in_transaction`（run_transition.py）追加 CANCEL_REQUESTED + RUN_CANCELLING，Run RUNNING → CANCELLING。
- **Terminal first-wins**：CAS 语义在 `_ingest_validated` 中依赖 durable run_transition CAS 原语（通过 CAS_LOST 检测 terminal 已存在）。
- **Queue promotion**：`_with_terminal_promotion_retry` 在 terminal closeout 后触发 promotion，独立新事务（不在 ingest transaction 内递归）。
- **Lane token release**：只在 scheduler/worker finally 路径；cancel path 不直接 release（§3.3 §3.7）。

**Required fixes**：无。

**Residual risks**：多进程 orphan proof 与 restart recovery 仍由 Phase 11 处理。

---

### 2.3 发现 3 — 分层/import 边界验证

**Severity**：INFO（一致，无修复需求）

**Evidence**：

- `tests/host/test_import_boundary.py` 5 项 AST 级 import 边界测试全部通过：
  - `test_host_does_not_import_upper_or_business_layers`：Host 不导入 `dayu.fins`/`dayu.service`/`dayu.ui`
  - `test_host_engine_imports_stay_on_allowed_boundary_modules`：Host 只在 `api.py`/`dispatch.py`/`engine_ingest.py`/`local_proxy.py`/`run_input.py` 这 5 个边界模块导入 Engine
  - `test_runtime_does_not_import_host_or_engine_layers`：Runtime 不导入 host/engine/service/ui/fins
  - `test_engine_does_not_import_host_layer`：Engine 不导入 host
  - `test_host_request_dataclasses_do_not_carry_tool_bundle`：per-run request 不携带 business ToolBundle
- pyright 零报错（0 errors, 0 warnings, 0 informations）确认无类型级反向依赖。
- 实际实现中 Host 只通过 `dayu.engine` 公共入口（`run_agent_messages`）和 `dayu.engine.contracts.*` 公共契约类型与 Engine 交互；Engine 不 import `dayu.host`。

**Required fixes**：无。

**Residual risks**：无。

---

### 2.4 发现 4 — Schema/测试迁移合理性

**Severity**：INFO（一致，无修复需求）

**Evidence**：

- `HOST_SCHEMA_VERSION = 3`（schema.py:14），无旧版兼容读取路径。
- Dispatch DDL 为 fresh schema（§3.2 完整实现），CHECK constraint 覆盖全部 4 个状态及其 nullability 组合。
- 无 Phase 3/4 schema 兼容性 re-export、wrapper 或旧 CHECK 残留。
- 测试迁移：新增 6 个测试文件（`test_run_input_builder.py`、`test_dispatch_scheduler.py`、`test_local_proxy_engine_ingest.py`、`test_engine_ingest_mapping.py`、`test_active_cancel_dispatch.py`、`test_phase5_local_execution_integration.py`），更新 5 个既有测试文件（`test_state_schema.py`、`test_run_attempt_transitions.py`、`test_admission_queue.py`、`test_public_cancel_session_runs.py`、`test_command_handle.py`、`test_package_exports.py`）。
- 无生产代码中的兼容逻辑或旧接口保留。

**Required fixes**：无。

**Residual risks**：后续 phase（ToolRuntime/Memory/Context Governance）引入新 schema column 时需再次 bump schema version；Phase 5 已为此建立 fresh schema 先例。

---

### 2.5 发现 5 — README/control doc 当前能力描述与 deferred owner

**Severity**：INFO（一致，无修复需求）

**Evidence**：

- `dayu/host/README.md`（166 行）准确描述 Phase 5 全部当前能力（RunInputBuilder no-tool、dispatch scheduler/LocalProxy 基线、EngineEvent ingest mapping、active cancel 子集、terminal closeout 表）与 deferred owner：
  - ToolRuntime → Phase 6
  - WAITING/resolve_wait → Phase 7
  - Memory → Phase 9
  - Context Governance → Phase 10
  - Recovery → Phase 11
  - RemoteProxy → Phase 14
  - Observer/Sink → Phase 13
- `tests/README.md`（148 行）已更新 Phase 5 test strata、运行命令、fake local worker 约定。
- README 无"未来设计"、时间敏感记录或过时术语残留。

**Required fixes**：无。

**Residual risks**：后续 phase 引入新功能时需按 CLAUDE.md 触发规则同步更新对应 README。

---

### 2.6 发现 6 — Ready-to-create-PR 与残余风险

**Severity**：INFO

**Evidence**：

- 所有 Phase 5 slice 均已 accepted 并 checkpoint（git log 显示 P5-S1 到 P5-S6 的 record+accept 提交对）。
- 254 个 Host 测试全部通过。
- pyright 零报错（`dayu/`、`tests/`、`utils/` 全量检查 0 errors, 0 warnings, 0 informations）。
- Import 边界 AST 级检查无一违反。
- 无 blocking findings。

**Required fixes**：无。

**Residual risks and subsequent owners**：

| 风险 | Owner |
|------|-------|
| ToolRuntime 治理、工具 schema snapshot、`fetch_more` 注入 | Phase 6 |
| WAITING 状态、`resolve_wait`、wait cancel | Phase 7 |
| Memory projection、stable layer | Phase 9 |
| Context Governance、proactive/reactive compaction | Phase 10 |
| Recovery classifier、自动 RECOVERING、多进程 orphan proof | Phase 11 |
| RemoteProxy、RemoteStub、wire protocol | Phase 14 |
| Observer/Sink、audit projection、stream fanout | Phase 13 |
| 真实 provider runner 外部网络 smoke | 集成环境验证 |
| Active cancel 超时后 watchdog/LOST policy | lifecycle hardening（后续 phase） |

---

## 3. Review Gate 检查清单逐项确认

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | Phase 5 没有修改 Engine public `EngineEvent` contract 来携带 Host identity | PASS |
| 2 | Dispatch record enum 含 `pending`/`waiting_for_lane`/`dispatching`/`cancelled`，nullability 已测试 | PASS |
| 3 | `dispatching` 在 WorkerProxy accept 后仍是最终非取消状态；active truth 是 `ATTEMPT_RUNNING` | PASS |
| 4 | RunInputBuilder provider set 区分 real/noop | PASS |
| 5 | 当前用户输入只来自 durable `USER_INPUT_ACCEPTED` | PASS |
| 6 | `usage_reported` 是 projection_signal，不是 canonical Run state fact | PASS |
| 7 | context compaction/unsupported recovery → diagnostic + FAILED，不进入 RECOVERING | PASS |
| 8 | clean EOF no terminal → FAILED；worker crash/stream error → LOST | PASS |
| 9 | pre-worker dispatching+STARTING cancel → CANCELLED，不进入 CANCELLING | PASS |
| 10 | active worker cancel 只有 Attempt RUNNING 后才进入 RUN_CANCELLING | PASS |
| 11 | cancel_session_runs replay 不取消新 Run，不重复 append facts；WAITING/RECOVERING 无 partial mutation | PASS |
| 12 | lane token release 只在 scheduler/worker finally；cancel path 不直接 release | PASS |
| 13 | 未实现 ToolRuntime/fetch_more/wait/Memory/Context Governance/Observer/RemoteProxy | PASS |

---

## 4. 验证记录

```text
# 测试结果
pytest tests/host -q
  → 254 passed in 3.81s

pytest tests/runtime -q
  → 80 passed

# 类型检查
python -m pyright dayu/ tests/ utils/
  → 0 errors, 0 warnings, 0 informations

# Import 边界
pytest tests/host/test_import_boundary.py -q
  → 5 passed
```
