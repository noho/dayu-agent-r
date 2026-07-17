# Dayu Service 开发手册

`dayu.service` 是 Host 外部的组合边界。它负责把 `dayu.runtime` 的层中立配置、位置解析、工具发现结果与 scene 装配结果映射为 Host public typed inputs。

当前稳定入口：

- `dayu.service.host_assembly.assemble_effective_tool_provider_configs(...)`：把 `tool_discovery.json` typed view 与运行时参数装配为 effective provider configs。
- `dayu.service.host_assembly.discover_service_tools(effective_provider_configs)`：只接收已装配的 effective provider configs，并执行工具发现。
- `dayu.service.host_assembly.compose_open_host_options(request)`：从 runtime config、locations、prepared scene、工具发现、显式 override 与 env/secret mapping 组合 `OpenHostOptions`。
- `dayu.service.host_assembly.compose_submit_followup_request(...)`：把 prepared scene 的 `system_prompt` 与本轮用户输入组合为 `SubmitFollowupRequest`。
- `dayu.service.host_assembly.compose_submit_followup_request_with_overrides(...)`：在同一 assembly 真源内把可映射的单次 Run override 合并为完整 `runner_options` 与 `agent_policy`。
- `dayu.service.wait_callback_endpoint.handle_wait_callback_completion(...)`：framework-neutral wait callback completion transport mapper；真实 Web router 只把 path wait id、headers 与已解析 JSON body 传入该函数，mapper 负责 transport 校验、Host callback envelope 构造和 HTTP-like status/body 映射，不注册真实路由。
- `dayu.service.entrypoint_runtime`：为 product entrypoint 提供 reusable Agent runtime helper，覆盖 runtime 准备、Session ensure/create、submit 前 live watcher attach、terminal observation outbox fallback、interactive existing-session startup reconnect、cancel request 构造与 watcher failure 诊断；该模块不解析 CLI 参数，不保存 CLI cursor，不处理 stdout/stderr，也不安装 signal handler。
- `dayu.service.scene_context`：为 product entrypoint 生成 LLM-facing context slot 文本，覆盖财报分析对象、当前时间、显式 FMP key 下的公司名增强和 FMP 失败时的 ticker-only fallback；该模块不读取 CLI 参数，不向 LLM 投影 FMP 错误文本。
- `dayu.service.fins_direct`：为 product entrypoint 提供 reusable Fins direct stream helper，覆盖 download / preprocess / upload 的 typed request 构造、同一个 `ValidatedFinsEventStream` identity 透传和 operation-scoped cancellation；terminal 协议由 Fins validator 唯一拥有，该模块不解析 CLI 参数、不处理 stdout/stderr，也不读取 Fins storage。
- `dayu.service.fins_wait_adapter`：为 Host production wait poller 提供 Fins awaiting observation integration，负责把 Host `WaitAdapterSnapshot` 映射到 Fins `FinsObservationRuntime` 的 activate / poll / cancel / abandon 入口；该模块不读取 Host durable row / store / state mutator，也不读取 Fins storage。

`compose_open_host_options(request)` 会把选中的 execution profile 映射为 Host typed inputs：`tool_truncation_policy` 决定 ToolRuntime 截断默认值，`tool_duplicate_governance_policy` 决定 `HostToolingOptions.duplicate_governance_policy`，`agent_policy` 决定 ordinary run baseline 的 Agent loop policy。
Service 从模型配置构造 `RunnerSpec` 时默认启用 OpenAI-compatible client correlation policy，使 ordinary baseline 与 compactor baseline 的 Runner 调用都携带可由 Engine 映射的客户端调试关联 id；静态 `X-Client-Request-Id` header 冲突由 RunnerSpec 边界 fail fast。

工具发现 provider 不读取全局 runtime config，也不自行推断 workspace。调用方负责把 raw config 与运行时参数装配为 effective spec；例如 Fins provider 的 `workspace_root` 可以来自 overlay 显式配置，也可以由调用方通过 `assemble_effective_tool_provider_configs(...)` 使用当前 `workspace_root` 注入到 provider spec。

`discover_service_tools(...)` 返回的 `ServiceDiscoveredTools` 会携带本次 discovery 实际使用的 effective provider configs，并另行保存一次构造的 Service 私有 Fins awaiting typed metadata collection。Service 只用现有 provider identity 把 raw provider config 交给 Fins 唯一 parser；typed mode、provider/source/version、工具名与绝对 workspace root 保存在并行私有 projection 中，不写回 `ToolDiscoveryProviderConfig.config`，不放入 extra payload，也不以 Fins mode / metadata 扩展 ConfigLoader 的 generic runtime schema。后续 activation、binding、poll registry 与 composition 只复用该 typed collection，不再次读取 raw mode。

`compose_open_host_options(...)` 对全部 active awaiting metadata 构造 activation registry，并把 `poll/callback/manual` 精确映射为 Host binding；poll registry 只包含 typed mode 为 `poll` 的工具。存在 active poll 时，Service 把 `host_runtime.json` 的完整 typed policy snapshot 一对一映射为 `WaitPollerRuntimePolicy`；没有 active poll 时向 Host 传 `None`，runtime policy disabled 时仍显式传递 disabled policy。当前没有 authenticated callback transport，因此任意 active callback 都在 `open_host` 前失败，不能降级成 poll/manual 或用 marker 绕过。scene 只控制单次 Run 的工具暴露，不再决定 Host opener policy；prompt 与 interactive 经过同一 composition 路径，对相同 provider/runtime inputs 得到相同 opener 决策。

`entrypoint_runtime` 的 terminal observation 只使用 Host public API：submit 路径先 attach `watch_session_events(session_id)` 再提交 Run，并可在 Host 接受 Run 后把 `accepted_run_id` 通知调用方用于运行中取消；cancel 路径先通过 `get_run(...)` 读取 public snapshot，已终态时跳过 `cancel_run(...)` 并走 outbox terminal fallback，非终态时在 `cancel_run(...)` 前 attach watcher。Service 不读取 Host durable internals，终态来源会明确标记为 live event 或 outbox read；watcher drain 失败会进入 terminal result 或 observation error 的诊断消息。submit helper 可把 Host public activity 和 thinking view 分别投影给调用方回调，是否展示由 UI adapter 决定。

`entrypoint_runtime` 的 interactive startup reconnect helper 只编排 Host public API：先 attach `watch_session_events(session_id)` 并缓存 live events，再用调用方提供的 terminal cursor 做 session-scoped Outbox backfill，随后处理 selected Session 的 active Run 与 queued-only bounded promotion barrier；进入输入态前会在 idle snapshot 后再做 tail outbox closure 并 drain watcher，避免 startup terminal 在 idle 边界丢失。Service 不保存 CLI cursor，不按单个 Run 过滤 startup backfill，不把 queued-only 状态静默视为 idle。

`entrypoint_runtime` 的 submit / cancel wait helper 不持有内部 timeout。调用方负责通过 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。

`wait_callback_endpoint` 只做 Service/Web transport 映射：method、content-type 与 path/body wait id 错误在 Service 层拒绝；JSON body 与 outcome shape 错误在 Service 层返回 malformed payload；认证结果、wait 状态、replay、digest 与 late callback 语义来自注入的 Host callback adapter。响应体只包含 typed status、diagnostic、retryable 与可选 Run 摘要，不回显 outcome payload。

`fins_direct` 的 upload helper 只通过 `FinsIngestionRuntime.upload(...)` 提交 `FinsUploadFilingRequest` 或 `FinsUploadMaterialRequest`，不要求 runtime 存在 `upload_filing(...)` / `upload_material(...)` 方法。Service 的 protocol、public 与 private direct methods 都以 plain `def` 直接返回 runtime 提供的同一个 `ValidatedFinsEventStream`，不 `await`、迭代、包装或重建 stream；missing、duplicate、event-after-result 与 terminal availability 均由 Fins validator 判定一次。调用方通过 `async for` 消费 `PROGRESS` 与唯一 terminal `RESULT`，并在 clean exhaustion 后读取 validator 的 terminal result。用户中断仍通过关闭当前 stream / 取消当前 task和 operation-scoped cancellation 传播；Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`。

边界约束：

- Service 可以依赖 Host / Engine public contracts，但不得修改 Host truth 或绕过 Host public API。
- `dayu.runtime` 不得依赖 `dayu.service`；公共层中立能力应继续放在 `dayu.runtime`。
- 财报文档存取仍只能通过 `dayu.fins.storage` 仓储协议完成；本包只允许在 approved Fins Service boundary 中调用 `DefaultFinsRuntime` / `FinsIngestionRuntime` / `FinsObservationRuntime`，不得直接读取财报仓储。
- Service-owned Fins wait adapter 只消费 Host `WaitAdapterSnapshot`、`WaitActivationRequest` 与 wait adapter public outcome 类型；不得导入 `dayu.host.durable` 或从 Host durable row 推断 deadline / expiry / state mutator 语义。
