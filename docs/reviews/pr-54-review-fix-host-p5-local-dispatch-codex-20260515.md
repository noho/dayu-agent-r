# PR 54 Review Fix: Host P5 Local Dispatch

## Scope

本轮按 PR #54 review fix gate 处理 accepted blocking/current items，只修改本地工作区代码与测试；未改写历史 gateflow review artifacts。

## Finding Disposition

- fixed: dispatch / lane / worker lifecycle correctness。
  - `HostDispatchScheduler` 现在对 lane acquire timeout / cancelled、worker factory / accept 非 timeout 异常做 startup failed closeout，并把 pre-accept dispatch record 置为 `CANCELLED`。
  - lane token release 改为 best-effort helper，覆盖 durable recheck skip、pre-accept cancel race、worker startup failure、scheduler task cancellation 与 worker consume finally。
  - startup closeout 与 lane release 改为 `try/finally`，即使 durable closeout 抛错也会释放已获取 lane token；补充回归测试覆盖 closeout exception 后同 lane 可立即重新 acquire。
  - fixed F5: durable lane recheck 支持 `PENDING -> DISPATCHING` direct jump，`mark_dispatching_after_lane_row` 会同时填充 `waiting_for_lane_at`、`lane_name`、`owner_host_instance_id`、lane claim / owner / acquired / dispatching 时间字段，满足 dispatch record schema nullability；`WAITING_FOR_LANE -> DISPATCHING` 旧路径保持不变。
  - fixed F5: scheduler `_is_dispatchable_recheck` 接受 `PENDING` 或 `WAITING_FOR_LANE`，补充 scheduler pending direct recheck 与 durable primitive CAS 测试。
  - active handle cancel / close 异常不再打断 scheduler close 或 consume cleanup。
  - worker event stream clean EOF 继续映射为 `FAILED`；stream 异常和 ingest 异常映射为 `LOST`；consume finally 仍是 lane release owner。
  - scheduler 端到端测试覆盖 accept exception、clean EOF -> failed、stream crash -> lost、close/cancel exception。

- fixed: durable CAS / idempotency。
  - `cancel_starting_dispatch_record_row` 对已 `CANCELLED` dispatch row 返回 `CAS_LOST`，吸收重复取消。
  - active Run CAS 分类把 `CANCELLING` / `RECOVERING` 纳入 `CAS_LOST`，避免误报 invalid_state。
  - worker lost lifecycle duplicate ids 改为 `ATTEMPT_LOST` / `RUN_LOST`，terminal payload `engine_event_ref` 不再伪装为 `run_failed`。

- fixed: Engine ingest mapping / idempotency coverage。
  - 新增 `RUN_SUSPENDED`、`TOOL_AWAITING` duplicate terminal id 识别，重复 ingest 返回 `DUPLICATE`。
  - 补齐 `PROVIDER_PROTOCOL_ERROR`、preview、late terminal、`run_cancelled_without_active_cancel`、unsupported type/data shape 测试。
  - `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 在 Phase 5 no-tool boundary 下只作为 `PREVIEW` 写入结构化 payload，不创建 canonical tool facts、wait record 或 WAITING 状态。依据：设计真源规定 ToolRuntime accept barrier 才拥有 canonical tool facts；Engine 工具事件在当前 Phase 只能作为 preview / diagnostic / idempotent confirmation。

- fixed: RunInputBuilder continuity。
  - continuity 现在只投影已成功收口且同时具备 user / assistant 两端的历史 Run；failed / cancelled / lost Run 不再留下孤立 `UserMessage`。
  - system scene message 移除 `attempt_id` / `execution_id`，避免把 Host Attempt / execution identity 泄漏给 Engine message 内容。

- fixed: test gaps。
  - dispatch record nullability 增加 pending / waiting_for_lane / dispatching / cancelled 四状态非法组合覆盖。
  - `cancel_session_runs` 集成测试已存在 queued / pre-dispatch / active worker / replay / unsupported non-terminal 覆盖，本轮验证通过，未追加重复用例。
  - close / exception 路径已在 scheduler 测试补充。

- fixed: `HostLocalExecutionOptions` typed field 校验。
  - `runner_spec`、`runner_options`、`agent_policy` 构造期分别用 `isinstance` 校验为 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`。
  - `worker_factory` 是结构协议，运行时不使用 `hasattr` / `getattr` 探测协议形状；当前构造期拒绝 `None`，结构完整性由 pyright 与显式 scheduler 装配点保障。
  - 补充 public contract 测试覆盖 valid shape、三类 typed field 错误和 `worker_factory=None`。

- fixed-with-fail-fast: `HostCommandHandleOptions.local_execution` 未被 public sync factory 消费。
  - root cause: 当前 public `create_host_command_handle` 是同步 command facade，而 `HostDispatchScheduler.open` 需要 async lane controller 与 worker lifecycle owner；直接在 sync factory 内消费 `local_execution` 会引入隐藏 event loop / background task 生命周期，不符合 Host 强约束生命周期真源。
  - fix: `create_host_command_handle` 对非空 `local_execution` fail fast，避免 silent accept；README 说明本地 scheduler 需显式 `await HostDispatchScheduler.open(...)` 装配和关闭。
  - remaining owner: Host public API / controller 后续设计切片可新增显式 async host runtime/scheduler 装配 API；不要在同步 command handle 构造中隐式启动 async worker runtime。

- rejected-with-reason: schema v2 -> v3 旧库迁移。
  - 项目 schema 约束为 fresh schema 起库；本轮未添加兼容读取或迁移测试。

- deferred-with-owner: active cancel watchdog、default worker hard cancel、retry / replay failure-context projection。
  - owner: 后续 Phase 对应 controller-owned slice；本轮只处理 PR #54 accepted blocking/current items。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_state_schema.py -q`
  - passed: 79 tests
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_state_schema.py -q`
  - passed: 24 tests
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py -q`
  - passed: 23 tests
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_phase5_local_execution_integration.py tests/host/test_public_cancel_session_runs.py tests/host/test_state_schema.py -q`
  - passed: 58 tests
- `source .venv/bin/activate && pytest tests/host tests/runtime -q`
  - passed: 356 tests
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - passed: 0 errors
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - passed: 0 errors

## Residual Risks

- Worker lost closeout remains best-effort if durable storage itself is unavailable during both ingest failure and lost closeout; recovery/takeover is still outside Phase 5.
- `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` preview payload intentionally avoids canonical tool result persistence; ToolRuntime canonicalization remains future owner.
- Public command handle still does not own scheduler lifecycle and now rejects `local_execution`; callers must use explicit scheduler/local runtime assembly until the deferred async public runtime API design lands.
