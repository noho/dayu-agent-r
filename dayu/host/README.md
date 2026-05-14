# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 当前提供 Host 公共 API 的类型契约和 Host construction 的业务工具输入边界，供 UI / Service 按 `UI -> Service -> Host -> Engine` 的依赖方向向下引用。

当前包根导出包含以下类型：

- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`。
- command handle 协议：`HostCommandFacet`，只暴露 `host_handle_id`。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`StartRunRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`。
- snapshots / stream：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventView`、`HostEventStream`。
- error：`HostApiError`。
- tooling construction options：`ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`、`default_framework_tool_policy_view`。

`dayu.host.api.__all__` 仍只包含 request、snapshot、status、error、context 与 stream cursor 类型。Host construction tooling 类型位于 `dayu.host.tooling`，由包根导出，但不进入 `dayu.host.api`。

## Host Tooling Options

`HostToolingOptions` 是 Host construction / composition root 接收业务工具的 typed input boundary。它包含：

- `business_tool_bundle`：外部装配好的业务 `ToolBundle`。
- `source_refs`：非空 `ToolBundleSourceRef` 元组，用于解释业务工具来源。
- `framework_tool_policy`：construction 期 framework tool 预留名与启用集合视图。

`ToolBundleSourceKind` 当前覆盖 `explicit_provider`、`config_binding`、`package_entrypoint`、`service_composition`。`ToolBundleSourceRef` 只保存来源类别、来源 id、可选版本引用和可选内容摘要；它不携带 callable、provider 对象或业务模块对象。

默认 `FrameworkToolPolicyView` 预留 `FrameworkToolName.FETCH_MORE`，但默认不启用任何 framework tool。`HostToolingOptions` 会拒绝业务 `ToolBundle` 中与预留 framework tool 名称冲突的工具，例如 `fetch_more`。

## 校验边界

所有公共 dataclass 均使用 `frozen=True, slots=True`。枚举使用 `enum.StrEnum`，字符串值为稳定的 snake_case 值。

当前构造期校验覆盖：

- id / name / reason 字段拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 拒绝负数。
- `SubmitFollowupRequest` 中 `behavior=steer` 必须携带 `target_run_id`，`behavior=queue` 不得携带 `target_run_id`。
- `CreateSessionRequest.bind_slot=True` 时必须同时提供 `scope` 与 `slot_key`。
- `CancelRunRequest` 与 `CancelSessionRunsRequest` 当前只接受 `CancelMode.GRACEFUL`。
- `ToolBundleSourceRef.source_id` 拒绝空字符串或纯空白；可选版本引用与内容摘要存在时也必须非空。
- `HostToolingOptions.source_refs` 必须非空。
- `FrameworkToolPolicyView.enabled_framework_tools` 必须是 `reserved_framework_tool_names` 子集。
- 业务 `ToolBundle` 不得占用 reserved framework tool name。

## 架构边界

`dayu.host` 不导入 `dayu.engine`、`dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

业务工具发现、provider / 配置绑定、包入口扫描和 Service composition 发生在 Host 外部。Host 只接收外部已经形成的业务 `ToolBundle`，不扫描业务工具包，也不导入具体财报工具模块。`business_tool_bundle` 不进入 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resolve wait 等 per-run request。

Host 若在后续实现中复用 `dayu.runtime.filelock`，只能把它用于普通文件短临界区互斥。lock marker 文件不是 Host 治理真源，不能用于判断 Run / Attempt owner、worker liveness、EventLog ordering、recovery 或 takeover；这些事实只能来自 Host durable store、EventLog、状态索引和事务。`RuntimeFileLock` 也不承诺 reentrant lock 语义，Host 代码不得依赖同一实例重复 acquire 的第三方行为。

当前未实现：

- Host command function。
- durable store、EventLog row、dispatch record、policy provider set。
- ToolRuntime construction、ToolRuntime policy resolution、framework tool injection。
- ToolsDiscovery / ScenePrepare provider contract、tool profile registry、Attempt tool snapshot durability。
- Engine 调用路径、Fins 业务语义、Service / UI 装配逻辑。

## 测试

Host 公共契约测试位于 `tests/host/`：

```bash
pytest tests/host -q
python -m pyright dayu/host tests/host
```

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host tooling options 校验、Host import 边界与弱类型守卫。
