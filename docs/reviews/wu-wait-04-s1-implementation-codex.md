# WU-WAIT-04 S1 Implementation Report - AgentCodex

## Scope

本报告对应 WU-WAIT-04 implementation gate Slice S1：Service production poller assembly gap。未启动完整 Gateflow，未执行 code review、deepreview、commit、push 或 PR。

## Changed Files

- `dayu/service/host_assembly.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `tests/service/test_host_assembly.py`
- `dayu/fins/README.md`
- `tests/README.md`

未修改 `docs/host/issues-implementation-control.md`；该文件在本 slice 开始前已有 controller dirty update。

## Behavior Implemented

- `ServiceAssemblyOverrides` 新增 `wait_poller_policy: WaitPollerRuntimePolicy | None = None`，作为 Service assembly 显式 typed opt-in。默认 `None` 继续表示不启动 production wait poller。
- `compose_open_host_options` / `_compose_options` 将显式 override 传入 `OpenHostOptions.wait_poller_policy`。
- `dayu.fins.ingestion.wait_adapter` 新增 `build_fins_wait_poll_adapter_registry(runtime=..., tool_names=...) -> WaitPollAdapterRegistry`：
  - 复用 `FinsIngestionWaitPollAdapter(runtime=runtime)`。
  - 使用稳定 `FINS_INGESTION_WAIT_ADAPTER_KEY`。
  - `tool_names` 只用于复用 Fins awaiting 工具名的非空、重复与 supported-name 校验，不新增 poller 逻辑。
- `dayu.service.host_assembly` 新增 `_fins_wait_poll_adapter_registry_from_provider_configs(...)`：
  - 与 wait adapter / activation registry 同源调用 `_fins_awaiting_registry_inputs_from_provider_configs(...)`。
  - 无启用且已进入 ToolBundle 的 Fins awaiting binding 时返回 `None`。
  - 有 binding 时要求 `fins_awaiting_runtime` 存在且为 `FinsIngestionRuntime`，否则 fail fast。
  - 使用同一个 `fins_awaiting_runtime` 构造 poll adapter registry。
- `_tooling_options_from_discovery` 现在显式传入 `HostToolingOptions(wait_poll_adapter_registry=...)`。该字段只有在 Fins awaiting runtime 与 awaiting tool binding 同时存在时非 `None`。
- 测试覆盖：
  - 默认 `OpenHostOptions.wait_poller_policy is None`。
  - 显式 `WaitPollerRuntimePolicy` override 到达 `OpenHostOptions.wait_poller_policy`。
  - 启用 Fins awaiting providers 且 discovered tools 包含对应 awaiting tools 时，`wait_adapter_registry`、`wait_activation_registry`、`wait_poll_adapter_registry` 同时存在，并共享同一个 ingestion runtime。
  - 无 awaiting provider、provider disabled、discovered tools 缺少 awaiting binding 时，`wait_poll_adapter_registry is None`。

## Validation

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
  - Result: passed, `54 passed, 3 warnings`.
  - Warnings: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.

## README Decision

- 已读取 `dayu/fins/README.md` 的 Agent 更新约束。新增 `build_fins_wait_poll_adapter_registry(...)` 是 `dayu.fins.ingestion.wait_adapter` 当前已实现的 developer-facing public assembly 能力，属于该 README 的接口与 wait adapter 边界职责，因此已更新。
- 已读取 `tests/README.md` 的更新约束。`tests/service/test_host_assembly.py` 的覆盖范围新增 production poller typed override 与 wait poll adapter registry assembly，属于测试分层说明职责，因此已更新。
- 未更新根 README、`dayu/README.md`、Host / Engine design docs 或 control doc。本 slice 未改变用户可见 CLI/Web/WeChat workflow、Host public API、Engine awaiting model、分层关系或 durable schema。

## Residual Risks / Uncovered Areas

- S1 只补齐 Service/Fins production poller assembly path，不实现 S2 public-only awaiting E2E smoke。
- 未新增 runtime config schema for poller enablement；当前只支持显式 typed override。
- 未覆盖真实 background poller E2E resolution；该验证属于 S2。
- 未新增 UI-facing wait record query，未读取 durable wait rows，未引入 manual resolve 作为生产级验证。

## Stop Condition

未发现 public-contract-only blocker。无需暴露 wait record query、无需把 wait id 投影给 ordinary UI、无需测试读取 durable wait rows。
