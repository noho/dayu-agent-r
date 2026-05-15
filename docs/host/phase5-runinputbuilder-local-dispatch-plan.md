# Host Phase 5 RunInputBuilder 与本地执行 Dispatch Plan

- **current gate**: Phase 5 handoff implementation-ready plan
- **work unit**: RunInputBuilder / LocalProxy / EngineEvent ingest / local dispatch
- **plan status**: implementation-ready
- **blocking question count**: 0
- **artifact path**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`

本文档是 handoff-ready 且 code-generation-ready 的实施计划。implementation agent 只能按本文档指定的文件边界、schema、状态迁移、provider set、payload 字段、取消行为、terminal policy 和测试范围实施；不得重新设计 Engine contract、dispatch record 语义、ToolRuntime、WAITING、RECOVERING、RemoteProxy、Memory、Context Governance 或 Observer / Sink。

## 1. 动机 / 直接证据 / 非目标

### 1.1 动机判断

动机成立，严重性评估没有被高估。

Phase 4 已提供 public command path，但它只把 Run 推进到 `RUNNING + Attempt STARTING + dispatch record pending`，并明确不启动 Engine。当前 Host 仍缺少从已提交 dispatch intent 到本地 Engine 执行、EngineEvent ingest、terminal closeout、active cancel 传播的闭环。如果此阶段不固定 schema、状态边界和异常收口，implementation agent 会被迫自行选择 `dispatching` 是否等同 active worker、EngineEvent canonical payload、RunInputBuilder provider 集合、`cancel_session_runs` 部分完成语义和 unsupported recovery 行为，这些都属于 Host 状态机真源，不应在代码实现时临场发明。

### 1.2 直接证据

- `docs/host/implementation-control.md` Phase 5 目标明确为连接 RunInputBuilder、Attempt dispatch record、LLM lane、LocalProxy / EngineWorker、EngineEvent ingest 与 terminal 收口，形成本地 Engine 执行闭环。
- `docs/host/implementation-control.md` 当前 gate 记录 Phase 5 design fix re-review 已通过，且 DS F3-F6 与 MiMo observations 必须作为 plan-gate 检查项覆盖。
- `docs/host/design.md` §17 明确 Engine 公共 `EngineEvent` 不携带 Host `attempt_id` / `execution_id`；Host-owned LocalProxy / EngineWorker envelope 负责身份绑定与 Host ingest 校验。
- `docs/host/design.md` §17 明确 dispatch record Phase 5 fresh schema 至少包含 `pending`、`waiting_for_lane`、`dispatching`、`cancelled`；这些状态只用于诊断、重复派发抑制和 recovery 判断，不是 lease / fencing / owner truth。
- `docs/host/design.md` §17 的本地 terminal closeout 表已经固定：startup failure => `FAILED`，clean EOF without terminal => `FAILED`，worker crash / stream error with unknown terminal => `LOST`，unsupported recovery signal => `FAILED` diagnostic-only；Phase 5 不自动进入 `RECOVERING`。
- `docs/host/design.md` §22 明确 `dispatching + Attempt STARTING` 且 WorkerProxy 未 accepted 时仍是 pre-worker direct cancel：`ATTEMPT_CANCELLED` / `RUN_CANCELLED`，不得进入 `CANCELLING`。
- 当前代码事实：`dayu/host/durable/schema.py` 的 dispatch record 只允许 `pending` / `cancelled`，`dayu/host/durable/state.py.DispatchRecordStatus` 也只有两个枚举值。
- 当前代码事实：`dayu/host/admission.py` 的 `AdmissionWakeupPort` 只唤醒 no-op / 测试端口；没有 scheduler、lane acquire、LocalProxy、WorkerProxy、Engine dispatch 或 EngineEvent ingest。
- 当前代码事实：`dayu/host/command.py.cancel_run` 遇到 dispatching / active worker 状态仍转为 deferred unsupported；`cancel_session_runs` Phase 4 子集遇到 unsupported non-terminal 不做 partial mutation。
- 当前代码事实：`dayu/engine/contracts/engine_events.py` 的 `EngineEvent` 包含 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`，没有 Host Attempt identity；这与设计要求一致，Phase 5 不得修改。

### 1.3 非目标

Phase 5 不做以下事项：

- 不修改 Engine public contract，不让 `EngineEvent` 携带 Host `attempt_id` / `execution_id`。
- 不实现 RemoteProxy、RemoteStub、wire protocol、远程 ack / replay / heartbeat。
- 不实现 ToolRuntime governance、ToolBundle snapshot、Host accept barrier、`fetch_more`、truncation、语义级重复工具调用治理或业务工具发现。
- 不实现 wait record、`resolve_wait`、`WAITING` canonical truth、WAITING cancel、迟到 wait result 接收。
- 不实现 Memory projection、Context Governance、proactive / reactive compaction policy、automatic `RECOVERING` 或 recovery dispatch。
- 不实现 Observer / Sink、audit projection、usage projection worker、outbox、stream fanout。
- 不实现 retry / replay / steer Attempt switching。
- 不把 lane token、`dispatching`、`owner_host_instance_id` 或 `dispatcher_instance_id` 当作 lease、fencing token、Attempt owner 或 takeover proof。
- 不为旧 schema / 旧接口写兼容读取、兼容 wrapper、兼容 re-export 或旧测试保留逻辑；本项目按 fresh schema 起库处理。

## 2. 受影响文件 / 模块所有权

### 2.1 允许修改的生产文件

- `dayu/host/durable/schema.py`
  - 拥有 Host durable schema version bump、dispatch record DDL fresh schema、状态 check、诊断字段 nullability。
- `dayu/host/durable/state.py`
  - 拥有 dispatch record row dataclass / enum / codec / CAS row mutation；新增 Attempt `RUNNING` CAS helper 与 dispatch diagnostic mutation。
- `dayu/host/durable/run_transition.py`
  - 拥有 `ATTEMPT_RUNNING` append、Engine terminal closeout payload、pre-worker dispatch cancel 泛化、active cancel transition primitive。
- `dayu/host/admission.py`
  - 拥有 admission wakeup port 扩展、`cancel_run` active worker 子集、`cancel_session_runs` Phase 5 supported subset 和 post-commit cancel target 返回。
- `dayu/host/command.py`
  - 拥有 Host composition root 装配本地 dispatch runtime、handle close 时关闭 scheduler / lane / worker registry、public cancel facade 的 Phase 5 行为。
- `dayu/host/api.py`
  - 只允许新增强类型本地执行 options / policy snapshot / runtime handle 类型；不得加入 Engine Attempt identity 到 Engine contract。
- `dayu/host/read_api.py`
  - 只在新增 EventLog view 类型或 read helper 必要时修改。
- `dayu/host/run_input.py`（新增）
  - 拥有 RunInputBuilder、typed provider protocols、Phase 5 real / noop provider 实现和 no-tool `AgentRunRequest` construction。
- `dayu/host/dispatch.py`（新增）
  - 拥有 dispatch scheduler、lane acquire/recheck、dispatch record 推进、worker accept transaction、lane token finally release。
- `dayu/host/local_proxy.py`（新增）
  - 拥有 LocalProxy / EngineWorker typed protocols、Host-owned envelope、local event identity、active worker registry 与 cancel handle。
- `dayu/host/engine_ingest.py`（新增）
  - 拥有 EngineEvent candidate validation、canonical / preview / projection_signal / diagnostic classification、terminal closeout、late / stale / duplicate event handling。
- `dayu/host/__init__.py`
  - 只导出 Phase 5 新增 public options / factory surface；不得导出内部 durable helper。

### 2.2 允许修改的测试文件

- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_run_input_builder.py`（新增）
- `tests/host/test_dispatch_scheduler.py`（新增）
- `tests/host/test_local_proxy_engine_ingest.py`（新增）
- `tests/host/test_engine_ingest_mapping.py`（新增）
- `tests/host/test_active_cancel_dispatch.py`（新增）
- `tests/host/test_phase5_local_execution_integration.py`（新增）

### 2.3 禁止修改的范围

- `dayu/engine/contracts/engine_events.py`、`dayu/engine/contracts/agent_run.py`、Engine public contract 文件。
- `dayu/runtime/lane.py`，除非现有 API 有明确 bug 且独立 root cause 证据成立；Phase 5 默认只复用。
- `dayu/fins/`、`dayu/service/`、`dayu/ui/`。
- ToolRuntime、Memory、Context Governance、RemoteProxy、Observer / Sink 相关未来模块。

## 3. 公共 / 内部契约与 schema 决策

### 3.1 Engine contract 边界

Phase 5 不修改 `EngineEvent`。Host 新增内部 envelope：

```text
LocalEngineEnvelope
  session_id: str
  run_id: str
  attempt_id: str
  execution_id: str
  dispatch_record_id: str
  worker_kind: WorkerKind
  execution_target: str
  local_worker_id: str
  cancellation_token: CancellationToken
```

Engine 原始事件进入 Host 前必须被 LocalProxy 包装为 `EngineEventCandidate`：

```text
EngineEventCandidate
  envelope: LocalEngineEnvelope
  worker_event_index: int
  engine_event: EngineEvent
  observed_at: datetime
```

`worker_event_index` 由 Host-owned LocalProxy 对单个 `execution_id` 从 1 单调分配。canonical event id 必须由 `execution_id`、`worker_event_index`、canonical event type、sub-index 派生；preview / diagnostic event id 也必须稳定可去重。Engine `metadata` 不参与 Host identity、状态机前置或幂等。

`observed_at` 必须是 `timezone.utc` aware `datetime`。写入 EventLog 时必须沿用 Phase 2 durable timestamp convention：UTC ISO-8601 TEXT、微秒精度、`Z` 后缀；naive `datetime` 属于构造错误。

Host event id 派生公式固定为：

```text
event_id = "event-engine-" + sha256_digest_json({
  "execution_id": execution_id,
  "worker_event_index": worker_event_index,
  "event_class": event_class,
  "event_type": event_type,
  "sub_index": sub_index
}).removeprefix("sha256:")
```

`sub_index` 从 0 开始，用于一个 EngineEvent 映射出多条 Host events 的场景，例如 `final_answer -> ATTEMPT_SUCCEEDED + RUN_SUCCEEDED`。同一输入必须生成同一 event id；不同 event class / event type / sub-index 必须生成不同 event id。

Host ingest 必须校验：

- candidate envelope 的 `session_id` / `run_id` 与 `engine_event.session_id` / `engine_event.run_id` 一致。
- durable Attempt 存在且 `attempt_id + execution_id` 匹配当前 Attempt。
- stale `execution_id`、terminal 后迟到事件、重复 canonical identity 不得污染 canonical EventLog。

### 3.2 Dispatch record fresh schema

`DispatchRecordStatus` 扩展为：

```text
PENDING = "pending"
WAITING_FOR_LANE = "waiting_for_lane"
DISPATCHING = "dispatching"
CANCELLED = "cancelled"
```

`dispatching` 在 WorkerProxy accept 后仍保留为 dispatch record 的最终非取消状态。Phase 5 不新增 `accepted` / `running` / `completed` dispatch record 状态；active worker truth 是 `ATTEMPT_RUNNING` 与 Attempt row `status=RUNNING`，terminal truth 是 Attempt / Run terminal facts。dispatch record 只表达 dispatch 诊断与重复派发抑制。

新增 dispatch diagnostic columns：

```text
waiting_for_lane_at TEXT NULL
lane_name TEXT NULL
lane_claim_id TEXT NULL
lane_owner_id TEXT NULL
lane_acquired_at TEXT NULL
dispatching_at TEXT NULL
worker_accepted_at TEXT NULL
worker_accept_event_id TEXT NULL
worker_accept_event_sequence INTEGER NULL
```

`worker_accept_event_id` 是 Host append 的 `ATTEMPT_RUNNING` EventLog `event_id`；`worker_accept_event_sequence` 是同一 `ATTEMPT_RUNNING` EventLog row 的全局 `event_sequence`。它们不是 worker-local sequence，也不是 Engine event id。

既有列保留：

```text
owner_host_instance_id TEXT NULL
cancelled_event_id TEXT NULL
cancelled_event_sequence INTEGER NULL
cancelled_at TEXT NULL
```

Nullability / check 规则：

- `pending`：`waiting_for_lane_at`、lane fields、`dispatching_at`、worker accept refs、cancel refs 全部为 `NULL`；`owner_host_instance_id` 可以为 `NULL`。
- `waiting_for_lane`：`waiting_for_lane_at`、`lane_name`、`owner_host_instance_id` 必须非空；`lane_claim_id`、`lane_owner_id`、`lane_acquired_at`、`dispatching_at`、worker accept refs、cancel refs 必须为 `NULL`。
- `dispatching`：`waiting_for_lane_at`、`lane_name`、`owner_host_instance_id`、`lane_claim_id`、`lane_owner_id`、`lane_acquired_at`、`dispatching_at` 必须非空；cancel refs 必须为 `NULL`；worker accept refs 要么全部 `NULL`，要么 `worker_accepted_at`、`worker_accept_event_id`、`worker_accept_event_sequence` 全部非空。
- `cancelled`：`cancelled_event_id`、`cancelled_event_sequence`、`cancelled_at` 必须非空；允许保留此前 waiting / lane / dispatching 诊断字段；worker accept refs 必须为 `NULL`，因为 WorkerProxy accepted 后 Attempt 应已进入 `RUNNING`，不再走 pre-worker direct cancel。

Schema version 必须 bump。测试必须更新为 fresh schema；禁止兼容旧 `pending/cancelled` check。

### 3.3 Dispatch / lane / WorkerProxy 状态迁移

固定路径：

```text
dispatch record pending
  -> scheduler CAS pending -> waiting_for_lane
  -> await LaneController.acquire
  -> acquire cancelled because durable cancel won: no terminal write, release nothing held
  -> acquire timed out before worker accepted: close Attempt FAILED / Run FAILED
  -> acquire success: scheduler holds lane token
  -> short transaction durable recheck
       requires Run RUNNING, Attempt STARTING, dispatch record waiting_for_lane or pending,
       execution_id match, no terminal / cancel accepted
  -> CAS dispatch record -> dispatching with lane diagnostics
  -> final pre-call recheck immediately before WorkerProxy call
  -> WorkerProxy accepted
  -> append ATTEMPT_RUNNING and Attempt STARTING -> RUNNING in one transaction
  -> record worker accept refs on dispatch record, status remains dispatching
  -> ingest EngineEvent stream
  -> terminal closeout or cancel closeout
  -> scheduler / worker finally releases lane token
```

`pending -> dispatching` 直达只允许在 acquire 前已经持有 lane 的测试 helper 中使用；生产 scheduler 必须先写 `waiting_for_lane`。如果 implementation 发现当前 test fixture 需要直达，必须把它限定在测试构造 helper，不能让生产路径跳过 `waiting_for_lane`。

Lane token release owner 是 scheduler / worker finally path，不是 cancel path。cancel path 只提交 durable cancel / terminal facts、更新 dispatch record、wake scheduler 或 active registry。

### 3.4 RunInputBuilder Phase 5 provider set

Phase 5 real providers：

- `CurrentRunFactProvider`
  - 从 EventLog / Run row 读取当前 Run 的 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED` 和当前 Attempt refs。
  - 当前 prompt 只能来自 durable `USER_INPUT_ACCEPTED.payload_json.display_text` / `payload_ref` / `payload_digest`，不能读取 UI 临时文本或 request 临时字段。
- `SessionContinuityProvider`
  - 从 EventLog 读取同 Session 中早于当前 Attempt 的 canonical `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` 摘要，按全局 `event_sequence` 稳定排序。
  - Phase 5 只把用户输入和已成功 final answer 摘要投影为 messages；失败 / 取消 / lost 只在影响当前语义时作为简短 system diagnostic，不加入 usage / preview / audit-only 事实。
- `SceneParameterProvider`
  - 从已持久化的 `USER_INPUT_ACCEPTED.payload_json.operation_kind`、`RUN_ACCEPTED.payload_json.execution_target`、`queue_policy` 和 Host policy snapshot 构造 system message。
- `PolicySnapshotProvider`
  - 提供 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 和 policy snapshot ref。Phase 5 必须使用显式 typed dataclass 注入，不得从全局配置或环境变量隐式读取。

`AgentRunRequest`、`RunnerSpec`、`RunnerCallOptions` 和 `AgentPolicy` 均使用现有 Engine public contract 类型：

- `dayu.engine.contracts.agent_run.AgentRunRequest`
- `dayu.engine.contracts.runner_spec.RunnerSpec`
- `dayu.engine.contracts.runner_spec.RunnerCallOptions`
- `dayu.engine.contracts.agent_policy.AgentPolicy`

Host RunInputBuilder 只构造这些既有 Engine request / policy objects，不在 Host 内重新定义同名 dataclass，不扩展 Engine contract，也不要求 Engine import Host 类型。

Phase 5 noop providers：

- `MemorySnapshotProvider`
  - 返回空 stable layer 与 `memory_snapshot_cursor=None`；不得读取或创建 memory projection。
- `CompactArtifactProvider`
  - 返回无 compact artifact；不得触发 proactive compaction。
- `ToolSchemaSnapshotProvider`
  - 返回空 tool schema tuple，`disable_tools=True`，`AgentPolicy.allow_tool_calls=False`。
- `ToolExecutorProvider`
  - 返回 `NoToolExecutor`。若 Engine 仍发出工具调用，`NoToolExecutor` 为每个 call 返回 `ToolCancelledOutcome(reason=host_cancelled, message="tools are disabled for this attempt")`；Host ingest 收到任何 tool awaiting / run suspended 仍按 unsupported path 失败收口，不创建 WAITING。

RunInputBuilder 输出：

```text
AgentRunRequest
  run_id / session_id from durable Attempt snapshot
  messages: tuple[AgentMessage, ...]
  disable_tools=True
  tool_schemas=()
  tool_executor=NoToolExecutor
  cancellation_token from LocalProxy envelope
  runner_spec / runner_options / agent_policy from PolicySnapshotProvider
```

Messages 稳定顺序：

1. system scene / execution target / policy constraints。
2. noop memory stable layer（Phase 5 为空，不产生日志事实）。
3. 同 Session canonical continuity messages，按 `event_sequence`。
4. 当前 `USER_INPUT_ACCEPTED` user message。

同一 EventLog + 同一 policy snapshot 必须构造出字节等价的 message 内容与顺序。

### 3.5 EngineEvent canonical payload 最小字段

Phase 5 canonical / projection_signal 映射只覆盖本地 no-tool 闭环需要的最小集合。

`ATTEMPT_RUNNING` payload 必须包含：

```text
attempt_id
execution_id
dispatch_record_id
worker_kind
execution_target
local_worker_id
worker_accepted_at
lane_name
lane_claim_id
```

`ATTEMPT_SUCCEEDED` payload 必须包含：

```text
attempt_id
execution_id
dispatch_record_id
reason = "final_answer"
engine_event_ref
finish_reason
filtered
degraded
terminal_summary_ref
terminal_summary_digest
```

`RUN_SUCCEEDED` payload 必须包含：

```text
run_id
terminal_attempt_id
attempt_terminal_event_id
reason = "final_answer"
finish_reason
filtered
degraded
terminal_summary_ref
terminal_summary_digest
```

`ATTEMPT_FAILED` / `RUN_FAILED` payload 必须包含：

```text
attempt_id / terminal_attempt_id
execution_id where attempt-scoped
dispatch_record_id
reason
error_code
message
provider_request_id
recoverable
unsupported_later_owner?  # only for unsupported recovery / compaction / waiting paths
terminal_summary_ref
terminal_summary_digest
```

`ATTEMPT_CANCELLED` / `RUN_CANCELLED` from active worker payload 必须包含：

```text
attempt_id / terminal_attempt_id
execution_id where attempt-scoped
dispatch_record_id
cancel_request_event_id
reason
engine_event_ref
requested_at
accepted_at
finished_at
```

`ATTEMPT_LOST` / `RUN_LOST` payload 必须包含：

```text
attempt_id / terminal_attempt_id
execution_id where attempt-scoped
dispatch_record_id
reason = "worker_lost_before_terminal"
worker_lifecycle_signal
stream_error_code
last_observed_worker_event_index
last_accepted_event_id?
```

`PROVIDER_PROTOCOL_ERROR` payload 必须包含：

```text
attempt_id
execution_id
iteration_id
error_code
message
provider_request_id
raw_payload_ref?
raw_payload_digest?
partial_tool_call_count
```

`partial_tool_call_count` 必须由 `len(engine_event.data.partial_tool_calls)` 派生。`raw_payload_ref` / `raw_payload_digest` 通过 Phase 2 payload descriptor 机制保存 `engine_event.data.raw_payload`；当 `raw_payload is None` 时二者均为 `None`。

`usage_reported` Phase 5 决策：

- 不映射为 canonical fact。
- append `EventClass.PROJECTION_SIGNAL` event_type `USAGE_REPORTED`，payload 包含 `attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`。
- 不更新 Run / Attempt 状态，不进入 RunInputBuilder messages，不要求 usage projection worker 存在。

Preview events：

- `iteration_started`、`content_delta`、`reasoning_delta`、`content_completed`、`tool_call_delta`、`tool_calls_batch_ready`、`tool_calls_batch_done`、`iteration_completed` 可 append `EventClass.PREVIEW`，payload 必须只含对应 Engine data 的 typed summary，不得带状态副作用。

Unsupported Phase 5 events：

- `tool_awaiting` / `run_suspended`：append diagnostic，随后以 `ATTEMPT_FAILED` / `RUN_FAILED` 收口，reason=`unsupported_waiting_path`，`unsupported_later_owner="phase7"`。
- `context_compaction_requested`：允许 `budget_state=None`，不得视为协议错误；append diagnostic，随后以 `ATTEMPT_FAILED` / `RUN_FAILED` 收口，reason=`unsupported_recovery_policy`，`unsupported_later_owner="phase10"`。
- `run_failed(recoverable=True)` 或 error_code 表达 context compaction / recovery：仍收口为 `FAILED`，把 `recoverable=True` 作为诊断字段，不进入 `RECOVERING`。

### 3.6 本地异常 terminal closeout

必须实现并测试以下表，不得偏离：

| 场景 | Attempt 终态 | Run 终态 | reason |
| --- | --- | --- | --- |
| WorkerProxy 调用前 final pre-call recheck 发现 durable 状态已变化 | 不新增终态 | 不新增终态 | `dispatch_aborted_by_durable_recheck` diagnostic only |
| WorkerProxy 调用异常，worker 未 accepted | `FAILED` | `FAILED` | `worker_startup_failed` |
| worker reject，worker 未 accepted | `FAILED` | `FAILED` | `worker_rejected` |
| startup timeout，worker 未 accepted | `FAILED` | `FAILED` | `worker_startup_timeout` |
| accepted 后结构化 `run_failed` | `FAILED` | `FAILED` | Engine error_code |
| clean EOF without terminal | `FAILED` | `FAILED` | `stream_ended_without_terminal` |
| stream error / local worker crash / terminal unknown | `LOST` | `LOST` | `worker_lost_before_terminal` |
| unsupported recovery / context compaction signal | `FAILED` | `FAILED` | `unsupported_recovery_policy` |

Terminal closeout 成功后必须触发同 Session queue promotion check；promotion 仍通过独立短事务 CAS，不在 Engine ingest transaction 内递归执行慢工作。

### 3.7 Cancel 决策

Per-run cancel：

- `Attempt STARTING + dispatch record pending / waiting_for_lane / dispatching 且 worker_accept_event_id IS NULL`：direct cancel，append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，dispatch record -> `cancelled`，不通知 WorkerProxy，不进入 `CANCELLING`。
- `Attempt RUNNING`：append `CANCEL_REQUESTED`；若 Run 为 `RUNNING`，同时 append `RUN_CANCELLING` 并 Run -> `CANCELLING`；commit 后通过 active registry 向 LocalProxy cancel handle 传播。若 Run 已 `CANCELLING`，不重复 append `RUN_CANCELLING`。
- terminal 已提交时，cancel 返回当前 Run snapshot，不改写 terminal。

`cancel_session_runs` Phase 5 supported subset：

- 支持 queued、pre-worker `STARTING`（含 pending / waiting_for_lane / pre-accept dispatching）和 active worker `RUNNING` / `CANCELLING`。
- 若同 Session 存在 `WAITING` 或 `RECOVERING` non-terminal Run，必须在追加任何 cancel fact 前返回 `UNSUPPORTED_OPERATION`，保持无 partial mutation；这些状态仍由 Phase 7 / 11 负责。
- 幂等 scope 仍是 `(operation=cancel_session_runs, scope_id=session_id, idempotency_key=request.client_request_id)`。
- semantic digest 不包含当前 Run 列表；同 key replay 返回当前 `SessionSnapshot`，不取消首次操作后新接受的 Run，不重复 append cancel facts。
- 首次执行可产生部分“完成形态”：queued / pre-worker Run 立即 `CANCELLED`，active worker Run 进入 `CANCELLING` 并等待 Engine `run_cancelled` 或 terminal race。该 partial completion 是状态机语义，不是事务 partial mutation。
- post-commit cancel propagation 是幂等 side effect；replay 不追加 facts，但可以 best-effort 再次调用 active registry 取消仍处于 `CANCELLING` 且 execution_id 匹配的 worker。

## 4. 数据流

### 4.1 成功路径

```text
start_run / submit_followup(queue)
  -> Phase 4 admission commits Run RUNNING + Attempt STARTING + dispatch pending
  -> wake dispatch scheduler after commit
  -> scheduler marks waiting_for_lane
  -> acquire runtime lane
  -> durable recheck and mark dispatching
  -> RunInputBuilder builds AgentRunRequest from durable facts
  -> LocalProxy starts EngineWorker with Host envelope
  -> WorkerProxy accepted
  -> Host appends ATTEMPT_RUNNING, Attempt -> RUNNING
  -> EngineEvent preview / usage projection_signal ingest
  -> final_answer candidate
  -> Host appends ATTEMPT_SUCCEEDED + RUN_SUCCEEDED
  -> release lane token in worker finally
  -> trigger queue promotion check
```

### 4.2 Active cancel 路径

```text
cancel_run / cancel_session_runs
  -> durable transaction appends CANCEL_REQUESTED
  -> if Attempt RUNNING and Run RUNNING: append RUN_CANCELLING
  -> commit
  -> active registry sends cancel to LocalProxy handle
  -> Engine emits run_cancelled
  -> Host validates attempt_id + execution_id
  -> Host appends ATTEMPT_CANCELLED + RUN_CANCELLED
  -> release lane token in worker finally
  -> trigger queue promotion check
```

### 4.3 Pre-worker cancel race

```text
scheduler has committed dispatching but WorkerProxy not accepted
  || cancel_run wins durable transaction
  -> Host appends CANCEL_REQUESTED + ATTEMPT_CANCELLED + RUN_CANCELLED
  -> dispatch record -> cancelled
  -> wake scheduler
  -> scheduler final pre-call recheck sees cancelled / terminal
  -> release lane token
  -> skip WorkerProxy
```

## 5. Implementation slices

### P5-S1 Dispatch Schema And Transition Primitives

Objective:

- 扩展 dispatch record fresh schema、row codec、CAS mutation 与 `ATTEMPT_RUNNING` / active cancel transition primitives。

Allowed files:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_weak_typing_guard.py`

Exact changes:

- Bump `HOST_SCHEMA_VERSION`。
- 扩展 dispatch DDL 和 `DispatchRecordStatus`。
- 扩展 `DispatchRecordRow` 字段与 row codec。
- 新增 state helpers:
  - `mark_dispatch_waiting_for_lane_row(...) -> DispatchRecordMutationResult`
  - `mark_dispatching_after_lane_row(...) -> DispatchRecordMutationResult`
  - `mark_dispatch_worker_accepted_row(...) -> DispatchRecordMutationResult`
  - `cancel_starting_dispatch_record_row(...) -> DispatchRecordMutationResult`，允许 `pending` / `waiting_for_lane` / pre-accept `dispatching`。
  - `mark_attempt_running_row(...) -> AttemptMutationResult`
  - `mark_run_cancelling_row(...) -> RunMutationResult`
- 新增 run_transition helpers:
  - `accept_worker_running_in_transaction(...)`
  - `request_active_attempt_cancel_in_transaction(...)`
  - 泛化 `cancel_predispatch_starting_in_transaction` 支持 waiting / pre-accept dispatching。
- `cancel_predispatch_starting_in_transaction` 必须拒绝 `dispatching` 且 `worker_accept_event_id` 非空的记录。

Tests:

- schema check 接受四个 dispatch 状态，验证每个状态的 nullability。
- pending -> waiting_for_lane -> dispatching -> worker accepted refs，status 保持 dispatching。
- pending / waiting_for_lane / pre-accept dispatching direct cancel 都写 `cancelled`。
- dispatching + worker accepted refs 不允许 direct cancel。
- `ATTEMPT_RUNNING` CAS 只允许 STARTING -> RUNNING。
- active cancel 只追加一次 `RUN_CANCELLING`。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Stop conditions:

- 如果 fresh schema 需要旧库兼容读取，停止并回到 controller；本计划不允许兼容路径。
- 如果 CAS helper 需要把 dispatch record 当 owner truth，停止。

Residual risks:

- 多进程 orphan proof 与 restart recovery 仍由 Phase 11 处理。

### P5-S2 RunInputBuilder And No-tool Provider Boundary

Objective:

- 建立 RunInputBuilder typed providers，基于 durable facts 构造 deterministic no-tool `AgentRunRequest`。

Allowed files:

- `dayu/host/run_input.py`
- `dayu/host/api.py`
- `dayu/host/durable/event_log.py`（仅新增窄 reader）
- `dayu/host/durable/state.py`（仅新增读取 helper）
- `dayu/host/__init__.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_package_exports.py`

Exact changes:

- 新增 provider protocols 与 view dataclasses，所有字段强类型，禁止 `Any` / `object`。
- 新增 `RunInputBuilder.build(attempt_snapshot: AttemptDispatchSnapshot) -> AgentRunRequest`。
- 新增 `AttemptDispatchSnapshot`，至少包含 `session_id`、`run_id`、`attempt_id`、`execution_id`、`dispatch_record_id`、`execution_target`、policy snapshot、cancellation token。
- `AttemptDispatchSnapshot` 只携带 durable identity refs、dispatch refs、policy snapshot refs 和 cancellation token；`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 由对应 providers 在 `build()` 时注入，不在 snapshot 中重复保存。
- 实现 Phase 5 real providers 和 noop providers，按 §3.4 固定。
- 实现 `NoToolExecutor`，只作为 no-tool防线；不得注册业务工具或 `fetch_more`。
- `ToolSchemaSnapshotProvider` 必须返回空 tuple；`AgentPolicy.allow_tool_calls=False`。

Tests:

- 当前用户消息只来自 `USER_INPUT_ACCEPTED` canonical fact；修改原 request 对象不影响 builder 输出。
- 同一 EventLog + policy snapshot 多次 build 输出 messages 顺序与内容一致。
- continuity provider 按 `event_sequence` 排序，不消费 preview / usage / audit-only events。
- noop memory / compact / tool schema provider 不创建 durable rows。
- no-tool request：`disable_tools=True`、`tool_schemas=()`、`allow_tool_calls=False`。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_package_exports.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Stop conditions:

- 如果无法从 durable `USER_INPUT_ACCEPTED` 重建当前 prompt，停止；不得从 UI/request 临时字段补读。
- 如果需要 Memory / Context / ToolRuntime 才能构造第一版 messages，停止并拆 scope。

Residual risks:

- Memory snapshot、compact artifact、ToolRuntime schema provider 会在 Phase 9 / 10 / 6 替换 noop provider。

### P5-S3 Dispatch Scheduler, Lane And LocalProxy

Objective:

- 将 pending dispatch record 接入 runtime lane、durable recheck、LocalProxy / EngineWorker accepted path。

Allowed files:

- `dayu/host/dispatch.py`
- `dayu/host/local_proxy.py`
- `dayu/host/command.py`
- `dayu/host/admission.py`
- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_command_handle.py`

Exact changes:

- 新增 `HostLocalExecutionOptions`，字段至少包含：
  - `lane_db_path: pathlib.Path`
  - `lane_name: str`
  - `lane_capacity: int`
  - `lane_default_timeout_seconds: float | None`
  - `lane_claim_ttl_seconds: float`
  - `lane_heartbeat_interval_seconds: float`
  - `worker_startup_timeout_seconds: float`
  - `dispatch_poll_interval_seconds: float`
  - `runner_spec`
  - `runner_options`
  - `agent_policy`
  - `worker_factory: LocalEngineWorkerFactory`
- 扩展 `HostCommandHandleOptions` 增加 `local_execution: HostLocalExecutionOptions | None = None`；为 `None` 时保持 no-op wakeup，不启动本地执行。
- 新增 `HostDispatchScheduler`：
  - `wake_dispatch(PendingDispatchRecord) -> None`
  - `drain_once() -> DispatchDrainResult`
  - `close() -> None`
  - 内部 async task 必须可取消，close 必须关闭 lane controller 并 best-effort cancel active workers。
- 新增 `LocalEngineWorkerFactory`、`LocalEngineWorker`、`LocalWorkerHandle` protocols：
  - factory 接收 `AttemptDispatchSnapshot`，返回 worker。
  - worker accept 后返回 `LocalWorkerHandle`。
  - handle 提供 `events() -> AsyncIterator[EngineEventCandidate]`、`cancel(reason: str) -> None`、`close() -> None`。
- LocalProxy default worker 使用 `dayu.engine.run_agent_messages(request)`；测试可注入 fake worker factory。
- WorkerProxy accept 后必须先 append `ATTEMPT_RUNNING`，再开始把 queued Engine events 交给 ingest。
- lane token 必须在 scheduler / worker finally release；cancel path 不直接 release。

Tests:

- scheduler pending -> waiting -> dispatching，Worker accepted 后 Attempt RUNNING，dispatch record status 仍 dispatching。
- lane acquire timeout 在 worker accepted 前 closeout FAILED，reason=`worker_startup_timeout`。
- durable recheck CAS loser release lane，不调用 worker。
- dispatching pre-call cancel race：cancel 先提交后 scheduler release lane 并跳过 worker。
- handle close 取消 pending acquire、best-effort cancel active worker、release lane。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Stop conditions:

- 如果需要把 lane DB 与 Host durable DB 合并，停止；runtime lane 必须保持层中立独立 DB。
- 如果 WorkerProxy accepted 前必须把 Attempt 视为 RUNNING，停止；active truth 只能是 durable `ATTEMPT_RUNNING`。

Residual risks:

- 进程崩溃后 dispatching STARTING 的 recovery classification 由 Phase 11 处理。

### P5-S4 EngineEvent Ingest Mapping And Terminal Closeout

Objective:

- 实现 Host-owned EngineEvent ingest、Phase 5 canonical payload、preview / projection_signal / diagnostic 分类和 terminal closeout。

Allowed files:

- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/payload.py`
- `dayu/host/admission.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_phase5_local_execution_integration.py`

Exact changes:

- 新增 `EngineEventIngestor.ingest(candidate: EngineEventCandidate) -> EngineIngestResult`。
- 实现 event identity derivation，重复 candidate 返回 existing result。
- final answer terminal summary 写入 payload descriptor；EventLog terminal payload 只保存 ref / digest 与必要 typed summary。
- 实现 §3.5 所列 canonical payload 字段。
- `usage_reported` append `projection_signal`，不改状态。
- `context_compaction_requested` 接受 `budget_state=None`，append diagnostic 后 FAILED closeout。
- `run_suspended` / `tool_awaiting` append diagnostic 后 FAILED closeout，不创建 WAITING。
- clean EOF without terminal 调用 FAILED closeout；stream error / worker crash 调用 LOST closeout。
- terminal closeout 后触发 queue promotion check。

Tests:

- final_answer -> `ATTEMPT_SUCCEEDED` + `RUN_SUCCEEDED`，payload fields 完整，Run snapshot terminal summary 可读。
- run_failed recoverable false -> FAILED；recoverable true -> FAILED with diagnostic-only unsupported recovery，不进入 RECOVERING。
- run_cancelled after active cancel -> CANCELLED。
- context_compaction_requested with `budget_state=None` -> diagnostic + FAILED，不是 protocol error。
- usage_reported -> projection_signal，无状态副作用。
- clean EOF no terminal -> FAILED；stream error / worker crash -> LOST。
- duplicate EngineEvent candidate 不追加第二条 canonical event。
- stale execution_id candidate rejected / diagnostic，不污染 canonical facts。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Stop conditions:

- 如果需要让 EngineEvent 携带 Host attempt identity，停止。
- 如果 unsupported recovery 需要创建新 Attempt 或 Run RECOVERING，停止；这属于 Phase 10 / 11。

Residual risks:

- Usage projection worker、audit sink 和 stream fanout 不在 Phase 5；本阶段只持久化 usage projection_signal。

### P5-S5 Active Cancel And Session-scope Cancel

Objective:

- 补齐 Phase 5 per-run active worker cancel 与 `cancel_session_runs` dispatching / active worker 子集。

Allowed files:

- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/local_proxy.py`
- `dayu/host/dispatch.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_run_api.py`

Exact changes:

- `cancel_run`：
  - pre-worker STARTING 支持 pending / waiting_for_lane / pre-accept dispatching direct cancel。
  - active Attempt RUNNING 进入 CANCELLING 并返回 post-commit `ActiveCancelTarget`。
  - command facade commit 后调用 active registry cancel。
- `cancel_session_runs`：
  - 在同一 write transaction 内先分类全部 non-terminal Run。
  - 遇到 WAITING / RECOVERING 立即 `UNSUPPORTED_OPERATION`，无 partial mutation。
  - queued / pre-worker 直接 CANCELLED；active RUNNING -> CANCELLING；already CANCELLING 不重复 RUN_CANCELLING。
  - idempotency replay 不取消新 Run，不重复 append facts，可 best-effort 重新传播仍 active 的 cancel。
- active registry：
  - 以 `(attempt_id, execution_id)` 注册 worker handle。
  - cancel message 最小携带 `run_id`、`attempt_id`、`execution_id`、reason。
  - terminal closeout finally unregister。

Tests:

- cancel_run on waiting_for_lane direct cancel，scheduler wake 后不 dispatch。
- cancel_run on dispatching pre-accept direct cancel，不进入 CANCELLING。
- cancel_run on Attempt RUNNING -> RUN_CANCELLING，worker 收到 cancel，Engine `run_cancelled` 后 Run CANCELLED。
- final_answer 与 cancel 并发时 first committed terminal wins，late cancel 不改写 terminal。
- `cancel_session_runs` 同时取消 queued、pre-worker 和 active worker；返回 snapshot 中 active 为 CANCELLING 或 terminal。
- `cancel_session_runs` replay 不取消首次后新创建 Run。
- `cancel_session_runs` replay 不追加 facts；若仍存在同 execution_id 的 active `CANCELLING` worker，best-effort re-propagation 不影响返回值与幂等记录。
- 存在 WAITING / RECOVERING 时 no partial mutation。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Stop conditions:

- 如果实现需要取消 wait record 或 recovery dispatch，停止；转交 Phase 7 / 11。
- 如果 cancel path 直接释放 lane token，停止；release owner 必须是 scheduler / worker finally。

Residual risks:

- active cancel 超时后 watchdog / LOST policy 不在 Phase 5；后续 lifecycle hardening 处理。

### P5-S6 Integration, Docs And Validation Closeout

Objective:

- 端到端验证本地 no-tool Engine 执行闭环，更新触发范围内 README。

Allowed files:

- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_import_boundary.py`
- `tests/README.md`
- `dayu/host/README.md`
- `dayu/README.md`（仅当现有总览仍宣称 Host 不支持本地 dispatch / RunInputBuilder 时更新）
- 根目录 `README.md`（仅当 CLI、项目级使用方式或配置入口发生变化时更新；本计划默认不触发）

Exact changes:

- Integration tests 覆盖：
  - start_run -> local fake worker final_answer -> Run SUCCEEDED。
  - start_run -> fake worker run_failed -> Run FAILED。
  - start_run -> fake worker clean EOF -> Run FAILED。
  - start_run -> fake worker crash -> Run LOST。
  - cancel active local fake worker -> Run CANCELLED。
  - queue promotion after terminal / cancel 继续唤醒 dispatch。
- Import boundary tests：
  - `dayu.runtime` 仍不得 import `dayu.host` / `dayu.engine`。
  - `dayu.engine` 不 import `dayu.host`。
  - `dayu.host.run_input` / `dispatch` / `local_proxy` 可以依赖 Engine contracts，但不得让 Engine 依赖 Host。

Docs decision:

- `dayu/host/README.md` 必须更新：Host 当前支持 RunInputBuilder no-tool provider、本地 LocalProxy / fake worker semantic baseline、dispatch record statuses、active cancel 子集；仍不支持 ToolRuntime / WAITING / RemoteProxy / Recovery。
- `tests/README.md` 必须更新：新增 Phase 5 test strata、运行命令、fake local worker 约定。
- `dayu/README.md` 需要先检查；若其中 Host glossary / current status 仍把 RunInputBuilder / LocalProxy 全部描述为未来能力，则更新为当前边界与剩余 deferred owner。
- 根目录 `README.md` 默认不更新；除非 implementation 实际新增用户命令、CLI、配置入口或运行方式。

Validation:

```bash
source .venv/bin/activate && pytest tests/host tests/runtime -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

Stop conditions:

- 如果 docs 需要描述未来能力才能解释当前实现，停止并改为只写当前能力 / deferred owner。
- 如果 pyright 出现新增或扩散错误，不得进入 review gate。

Residual risks:

- 真实 provider runner 的外部网络 / provider API smoke 不属于 Phase 5 必测；本阶段以 fake local worker 和 Engine contract tests 覆盖 Host state machine。

## 6. Review gate 检查清单

Plan review / code review 必须逐项确认：

- Phase 5 没有修改 Engine public `EngineEvent` contract 来携带 Host identity。
- Dispatch record enum 至少包含 `pending`、`waiting_for_lane`、`dispatching`、`cancelled`，且所有新增字段 nullability 已测试。
- `dispatching` 在 WorkerProxy accept 后仍是 dispatch record 最终非取消状态；active truth 是 `ATTEMPT_RUNNING`。
- RunInputBuilder provider set 已明确区分 real provider 与 noop provider。
- 当前用户输入只来自 durable `USER_INPUT_ACCEPTED` canonical fact。
- `usage_reported` 是 projection_signal / usage input，不是 canonical Run state fact。
- context compaction / unsupported recovery signal 在 Phase 5 只 diagnostic + FAILED，不进入 `RECOVERING`。
- clean EOF no terminal => FAILED；worker crash / stream error terminal unknown => LOST。
- pre-worker `dispatching + Attempt STARTING` cancel => `ATTEMPT_CANCELLED` / `RUN_CANCELLED`，不进入 `CANCELLING`。
- active worker cancel 只有 Attempt RUNNING 后才进入 `RUN_CANCELLING` 并传播 WorkerProxy cancel。
- `cancel_session_runs` replay 不取消新 Run，不重复 append facts；WAITING / RECOVERING 存在时无 partial mutation。
- lane token release 只在 scheduler / worker finally path；cancel path 不直接 release。
- 未实现 ToolRuntime、fetch_more、wait record、resolve_wait、Memory、Context Governance、Observer / Sink、RemoteProxy。

## 7. 最终交付报告格式

Implementation agent 完成每个 slice 后必须报告：

- slice id；
- changed files；
- implemented plan items；
- validation commands and results；
- README decision；
- residual risks / uncovered areas；
- stop status。

Phase 5 全部完成后的 closeout 必须明确：

- 改了什么；
- 验证了什么；
- 是否存在未覆盖风险；
- deferred owner：Phase 6 ToolRuntime / fetch_more，Phase 7 WAITING / resolve_wait，Phase 9 Memory，Phase 10 Context Governance，Phase 11 Recovery，Phase 14 RemoteProxy，Phase 13 Observer / Sink。

## 8. Blocking Questions

无 blocking open question。
