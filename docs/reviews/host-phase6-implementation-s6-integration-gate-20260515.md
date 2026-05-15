# Host Phase 6 P6-S6 Implementation: Integration, Scheduler Wiring, And Gate Validation

## 裁决

P6-S6 原计划偏向文档与验证收尾，但 Phase 6 既定目标要求真实 Host 本地 dispatch 路径使用 Host-governed ToolExecutor。P6-S1 至 P6-S5 已完成 ToolRuntime 组件闭环；若 `HostDispatchScheduler` 仍固定调用 no-tool RunInputBuilder，Phase 6 只能算组件完成，不能满足退出目标。

因此本 slice 按 controller 裁决扩展 P6-S6 scope：允许修改 `dayu/host/api.py` 与 `dayu/host/dispatch.py`，关闭真实 scheduler no-tool wiring 缺口。

## 修改

- `dayu/host/api.py`
  - `HostLocalExecutionOptions` 增加可选 `tooling_options` 与 `enable_truncation_manager`。
  - `tooling_options` 使用私有别名引用 `HostToolingOptions`，保持 `dayu.host.api` 不导出 tooling 类型的公共边界。
- `dayu/host/dispatch.py`
  - `HostDispatchScheduler` 在 `tooling_options` 非空且 `AgentPolicy.allow_tool_calls=True` 时，为当前 Attempt 构造 ToolRuntime handle。
  - ToolRuntime 使用当前 dispatch snapshot 的 `session_id`、`run_id`、`attempt_id`、`execution_id` 作为 execution scope。
  - ToolRuntime accept port 使用同一个 transaction runner 与 EventLog store。
  - scheduler 通过 tool-enabled RunInputBuilder 把同源 `tool_schemas` 与 `tool_executor` 交给 worker。
  - tooling 缺失或 policy 禁用工具时保持 no-tool builder 行为。
- `tests/host/test_dispatch_scheduler.py`
  - 新增真实 scheduler tool-enabled wiring 测试：worker 接收到非禁用工具 request，工具 schema 来自业务 ToolBundle，captured `tool_executor` 执行业务工具后通过 Host accept barrier 写入 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`。
- `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
  - 同步 P6-S6 扩 scope 裁决和 allowed files。
- `dayu/host/README.md`
  - 同步 P6-S6 当前事实：真实 `HostDispatchScheduler` 已按 construction tooling + policy 接入 ToolRuntime。
- `dayu/README.md`
  - 修正 `TruncationManager` / `truncation cursor` / `scope_token` 术语为 Phase 6 当前 run-scoped、short-lived、ToolRuntime-local 事实。
- `tests/README.md`
  - 同步 dispatch scheduler tool-enabled ToolRuntime wiring 测试覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/host -q`
  - 348 passed
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Non-goals

- 不实现 durable tool snapshot table。
- 不实现 policy provider resolution。
- 不实现 Remote transport。
- 不实现 P7 wait record / `resolve_wait`。
- 不实现 P13 durable tool trace projection。
- 不实现 business tool discovery；Host 仍只接收外部 composition root 传入的业务 `ToolBundle`。

## 残余风险

- tool-enabled scheduler 当前使用 `HostLocalExecutionOptions.tooling_options` 作为 construction-time 单 bundle 输入；多 profile / per-scene tool profile 仍归后续 ToolsDiscovery / policy provider owner。
- `policy_snapshot_digest` 当前是本地 policy snapshot 的诊断 digest，不是 durable attempt tool snapshot。
- Phase 6 尚需 aggregate review 确认所有 P6 退出条件：Engine 只消费 accepted 工具事实、`fetch_more` 仍是普通工具路径、无 WAITING / recovery / remote / durable cursor 越界。
