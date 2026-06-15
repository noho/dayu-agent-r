# Dayu Service 开发手册

`dayu.service` 是 Host 外部的组合边界。它负责把 `dayu.runtime` 的层中立配置、位置解析、工具发现结果与 scene 装配结果映射为 Host public typed inputs。

当前稳定入口：

- `dayu.service.host_assembly.assemble_effective_tool_provider_configs(...)`：把 `tool_discovery.json` typed view 与运行时参数装配为 effective provider configs。
- `dayu.service.host_assembly.discover_service_tools(effective_provider_configs)`：只接收已装配的 effective provider configs，并执行工具发现。
- `dayu.service.host_assembly.compose_open_host_options(request)`：从 runtime config、locations、prepared scene、工具发现、显式 override 与 env/secret mapping 组合 `OpenHostOptions`。
- `dayu.service.host_assembly.compose_submit_followup_request(...)`：把 prepared scene 的 `system_prompt` 与本轮用户输入组合为 `SubmitFollowupRequest`。
- `dayu.service.host_assembly.compose_submit_followup_request_with_overrides(...)`：在同一 assembly 真源内把可映射的单次 Run override 合并为完整 `runner_options` 与 `agent_policy`。
- `dayu.service.entrypoint_runtime`：为 product entrypoint 提供 reusable Agent runtime helper，覆盖 runtime 准备、Session ensure/create、submit 前 live watcher attach、terminal observation outbox fallback、cancel request 构造与 watcher failure 诊断；该模块不解析 CLI 参数，不处理 stdout/stderr，也不安装 signal handler。
- `dayu.service.fins_direct`：为 product entrypoint 提供 reusable Fins direct job helper，覆盖 download / preprocess / upload 的 typed request 构造、job start、job event observation、poll terminal fallback、durable cancel request 与 terminal exit mapping；该模块不解析 CLI 参数，不处理 stdout/stderr，也不读取 Fins storage。

`compose_open_host_options(request)` 会把选中的 execution profile 映射为 Host typed inputs：`tool_truncation_policy` 决定 ToolRuntime 截断默认值，`tool_duplicate_governance_policy` 决定 `HostToolingOptions.duplicate_governance_policy`，`agent_policy` 决定 ordinary run baseline 的 Agent loop policy。

工具发现 provider 不读取全局 runtime config，也不自行推断 workspace。调用方负责把 raw config 与运行时参数装配为 effective spec；例如 Fins provider 的 `workspace_root` 可以来自 overlay 显式配置，也可以由调用方通过 `assemble_effective_tool_provider_configs(...)` 使用当前 `workspace_root` 注入到 provider spec。

`discover_service_tools(...)` 返回的 `ServiceDiscoveredTools` 会携带本次 discovery 实际使用的 effective provider configs。`compose_open_host_options(...)` 复用这份结果绑定 Host tooling / wait adapter，避免工具闭包和等待适配器从两份 raw config 各自推断运行时参数。

`entrypoint_runtime` 的 terminal observation 只使用 Host public API：submit 路径先 attach `watch_session_events(session_id)` 再提交 Run，并可在 Host 接受 Run 后把 `accepted_run_id` 通知调用方用于运行中取消；cancel 路径先通过 `get_run(...)` 读取 public snapshot，已终态时跳过 `cancel_run(...)` 并走 outbox terminal fallback，非终态时在 `cancel_run(...)` 前 attach watcher。Service 不读取 Host durable internals，终态来源会明确标记为 live event 或 outbox read；watcher drain 失败会进入 terminal result 或 observation error 的诊断消息。

`entrypoint_runtime` 的 submit / cancel wait helper 不持有内部 timeout。调用方负责通过 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。

`fins_direct` 的 upload helper 只通过 `FinsIngestionRuntime.start_upload(...)` 提交 `FinsUploadFilingRequest` 或 `FinsUploadMaterialRequest`，不要求 runtime 存在 `start_upload_filing(...)` / `start_upload_material(...)` 方法。调用方拿到 job handle 后可以通过 `stream_job_events_until_terminal(...)` 消费 Fins job event；若 terminal event sidecar 缺失但 job record 已终态，Service 会记录 bounded WARN 并合成 terminal event，避免 UI 悬挂。调用方收到用户中断时应调用 `request_cancel(job_id)` 并继续观察终态；第二次中断可以选择本地退出但必须保留 job id 供用户追踪。

边界约束：

- Service 可以依赖 Host / Engine public contracts，但不得修改 Host truth 或绕过 Host public API。
- `dayu.runtime` 不得依赖 `dayu.service`；公共层中立能力应继续放在 `dayu.runtime`。
- 财报文档存取仍只能通过 `dayu.fins.storage` 仓储协议完成；本包只允许在 approved Fins Service boundary 中调用 `DefaultFinsRuntime` / `FinsIngestionRuntime`，不得直接读取财报仓储。
