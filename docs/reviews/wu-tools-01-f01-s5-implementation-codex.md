# WU-TOOLS-01-F01 Slice S5 Implementation - Codex

## Gate Metadata

- Gate: implementation only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-implementation-codex.md`.
- Scope guard: no commit, no push, no review gate, no Host / Engine public contract change.

## Objective Judgment

S5 目标成立。S4 已经提供 Fins download / preprocess awaiting tools，但 Service assembly 原先仍以 `wait_adapter_registry=None` 构造 `HostToolingOptions`。在当前 Host wait-resume contract 下，awaiting tool 若没有 adapter registry 会被 ToolRuntime 治理性拒绝，问题根因在 Service composition wiring 与 Fins-owned wait adapter 缺失，不在 Host / Engine contract。

本实现没有修改 `HostToolingOptions` 字段、`WaitAdapterBinding` shape、`ToolAwaitSpec`、`ToolAwaitingOutcome`、`ResolveWaitRequest`、`WaitRecord` schema 或 Engine contract。

## Changed Files

- `dayu/fins/ingestion/__init__.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/service/host_assembly.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_import_boundary.py`
- `dayu/fins/README.md`
- `dayu/README.md`
- `tests/README.md`

## Core Design

Fins 新增 `dayu.fins.ingestion.wait_adapter` 作为 Fins ingestion job 与 Host wait-resume contract 的薄适配边界：

- `FinsIngestionWaitPollAdapter` 实现当前 Host `WaitPollAdapter` protocol。
- `poll_wait(wait_record)` 只通过 Fins ingestion runtime 读取 job record，并按 S5 规则映射状态：
  - `queued` / `running` / `cancelling` -> `WaitPollNotReady`
  - `succeeded` -> `WaitPollReady(ResolveWaitCompletedOutcome)`
  - `failed` -> `WaitPollReady(ResolveWaitFailedOutcome)`
  - `cancelled` -> `WaitPollReady(ResolveWaitCancelledOutcome)`
  - missing / corrupt job evidence -> `WaitPollLost(ResolveWaitLostOutcome)`
- `abandon_wait(wait_record)` 只调用 Fins runtime `request_cancel(job_id)`，不删除 source docs，也不修改 Host wait records。
- `build_fins_wait_adapter_registry(workspace_root=..., tool_names=...)` 为 S4 稳定工具名构造 `WaitAdapterRegistry`，使用 `ToolAwaitKind.EXTERNAL_JOB`、`WaitResumePolicy.POLL`、`WaitExternalJobRefSource.RESUME_TOKEN` 与稳定 adapter key `poll:fins-ingestion`。
- binding 合并按工具名 deterministic sort；重复 binding fail fast。

Service assembly 在 Host 外部完成 Fins wait adapter wiring：

- `compose_open_host_options(...)` 仍通过现有 `HostToolingOptions.wait_adapter_registry` 字段传入 registry。
- 检测仅基于 `RuntimeConfig.tool_discovery.providers` 中已加载的显式 provider config：`provider_id`、`import_path`、`source_id` 和 provider `config.workspace_root`。
- 不依赖 ToolsDiscovery diagnostic strings。
- 不改变 `ToolsDiscoveryProviderOutput` shape，不把 adapter object 塞进 discovery output。
- 启用的 Fins awaiting providers 必须使用同一个 absolute `workspace_root`；不一致时在 `open_host` 前由 Service assembly fail fast。
- `dayu.runtime` 未新增 Fins import，ToolsDiscovery 保持 layer-neutral。

Service import boundary 随 S5 设计收敛为 allowlist：`dayu.service` 仍禁止导入 `dayu.config`、`dayu.ui` 和 Fins 非 assembly 边界；当前只允许 Service composition helper 导入 `dayu.fins.ingestion` 来装配 Fins wait adapter。

## Tests And Validation

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py
```

结果：`49 passed, 3 warnings`。warnings 来自第三方 `edgar` deprecation，不是本 slice 新增失败。

```bash
source .venv/bin/activate && pytest tests/service -q
```

结果：`34 passed, 3 warnings`，用于确认 S5 后 Service import boundary 与 host assembly 一起通过。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无 whitespace error。

## README Sync Decision

已按 AGENTS.md 触发规则做最小同步：

- `dayu/fins/README.md`：新增 Fins ingestion wait adapter 边界、poll 状态映射与 abandon 行为。
- `dayu/README.md`：新增 Service composition root 为 Fins awaiting provider 装配 wait adapter registry 的稳定边界说明。
- `tests/README.md`：新增 Service Fins awaiting assembly、Fins wait adapter registry / poll adapter / abandon wait 测试覆盖说明，并收敛 Service import boundary 文案。

未更新根 `README.md`：本 slice 没有改变用户手册层面的 CLI 命令、项目级运行方式、trace/render 入口或配置使用方式；S6 默认 config closeout 仍是 non-goal。

未更新 `dayu/host/README.md` / `dayu/engine/README.md`：本 slice 没有修改 Host / Engine public contract、状态机、durable schema 或执行路径。

## Residual Risk

- `assigned to later work unit`: 当前 Service assembly 只构造 `HostToolingOptions.wait_adapter_registry`，没有为生产 poller loop 提供自动启动 / backoff / fencing / retry wiring；这属于既有 WAIT hardening owner，不在 S5 范围。
- `assigned to later work unit`: 当前默认 `tool_discovery.json` closeout 和 packaged config 启用策略仍属 S6 non-goal。
- `assigned to later work unit`: 当前没有真实 SEC / CN / HK 网络下载 adapter；Fins ingestion runtime 对 unsupported source 写入明确 failed terminal，真实 source adapter breadth 不属于 S5。

## Completion Status

S5 implementation completed. No blocker.
