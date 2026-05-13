# Host 开发手册

本文档只记录当前 `dayu.host` 已实现的公共类型、边界与测试约定。

## 当前公共命名空间

`dayu.host` 当前提供 Host 公共 API 的类型契约，供 UI / Service 按 `UI -> Service -> Host -> Engine` 的依赖方向向下引用。

当前包根导出与 `dayu.host.api.__all__` 保持一致，只包含以下类型：

- status / enum：`SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior`、`CancelMode`、`WaitResolutionSource`、`SourceRunRelation`、`HostApiErrorCode`。
- context / input：`OperationContext`、`AuthorizationClaim`、`HostCallContext`、`HostMetadataEntry`、`HostInput`、`SessionSlotRef`、`HostStreamCursor`。
- command handle 协议：`HostCommandFacet`，只暴露 `host_handle_id`。
- requests：`EnsureSessionRequest`、`CreateSessionRequest`、`CloseSessionRequest`、`PurgeSessionRequest`、`StartRunRequest`、`CancelRunRequest`、`CancelSessionRunsRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest`、`ResolveWaitRequest`。
- snapshots / stream：`TerminalResultSummary`、`OutboxSummary`、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventView`、`HostEventStream`。
- error：`HostApiError`。

## 校验边界

所有公共 dataclass 均使用 `frozen=True, slots=True`。枚举使用 `enum.StrEnum`，字符串值为稳定的 snake_case 值。

当前构造期校验覆盖：

- id / name / reason 字段拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 拒绝负数。
- `SubmitFollowupRequest` 中 `behavior=steer` 必须携带 `target_run_id`，`behavior=queue` 不得携带 `target_run_id`。
- `CreateSessionRequest.bind_slot=True` 时必须同时提供 `scope` 与 `slot_key`。
- `CancelRunRequest` 与 `CancelSessionRunsRequest` 当前只接受 `CancelMode.GRACEFUL`。

## 架构边界

`dayu.host` 不导入 `dayu.engine`、`dayu.fins`、`dayu.service` 或 `dayu.ui`。Host 公共类型不放入 `dayu.contracts`；`dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 等共同理解的协作契约。

当前未实现：

- Host command function。
- durable store、EventLog row、dispatch record、policy provider set。
- runtime lane、runtime filelock、Host tooling options、ToolRuntime construction。
- Engine 调用路径、Fins 业务语义、Service / UI 装配逻辑。

## 测试

Host 公共契约测试位于 `tests/host/`：

```bash
pytest tests/host -q
python -m pyright dayu/host tests/host
```

测试覆盖包根导出白名单、枚举字符串值、请求校验失败路径、Host import 边界与弱类型守卫。
