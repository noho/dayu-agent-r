# Host Phase 1 Phase Design Refinement Review

## Work Gate

phase design refinement

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Reviewed Sources

- `docs/host/design.md` §3 `dayu.runtime`
- `docs/host/design.md` §10.1 Host Handle / Composition Root
- `docs/host/design.md` §11 Host 公共接口
- `docs/host/design.md` §18.1 ToolBundle Input / Runtime Tool View
- `docs/host/implementation-control.md` Phase 1 条目
- `dayu/README.md` 术语约定、Runtime、工具定义与执行边界
- `dayu/contracts/tool_declaration.py`
- 当前包结构：`dayu/contracts`、`dayu/engine`、`dayu/runtime` 已存在，`dayu/host` 尚未存在；`dayu/runtime` 当前文件只有 `__init__.py`、`cancellation.py`、`log.py`、`log_levels.py`

## Direct Evidence

- `docs/host/design.md:61-63` 已规定 `dayu.runtime` 层中立，且不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `docs/host/design.md:67-70` 已把 `lane` / `filelock` 与 Host durable truth 区分，并把 ToolsDiscovery / ScenePrepare 定义为 Host 外部装配组件。
- `docs/host/design.md:74` 现已明确 Phase 1 只实现 `lane`、`filelock` 与 `ToolBundle` construction input 边界；ToolsDiscovery / ScenePrepare 只固定边界，具体实现后置。
- `docs/host/design.md:519` 已要求业务 `ToolBundle` 是 Host construction / composition root 的显式输入，并记录 bundle / schema digest 与 source refs。
- `docs/host/design.md:523-538` 现已给出 `HostToolingOptions` 与 `ToolBundleSourceRef` 的最小 typed shape，并禁止 `business_tool_bundle` 出现在 per-run request 或 metadata。
- `docs/host/design.md:576-581` 现已明确 Host API 类型放在 `dayu.host` 公共命名空间；`dayu.contracts` 只放 Host 与 Engine / ToolRuntime 共同理解的层间协作契约；Host durable rows、dispatch records、policy provider set、ToolRuntime 内部状态等留在 Host 内部。
- `docs/host/design.md:1453-1457` 现已明确 Host 只接收 `ToolBundle` / `HostToolingOptions`，不接收 discovery adapter，不扫描业务包，不把 per-run `tool_profile_ref` 作为 Phase 1 能力。
- `docs/host/implementation-control.md:296-328` 现已把 Phase 1 的进入条件、范围、关键设计问题和 slice 切分收敛到 Host public typing、runtime lane/filelock、ToolBundle construction input，并把 ToolsDiscovery / ScenePrepare 作为 deferred slice。
- `dayu/README.md:34` 规定 `dayu.contracts` 承载跨层共享协作契约；`dayu/README.md:188` 规定只有跨层都需要理解的协作对象才进入 `dayu.contracts`。
- `dayu/README.md:121-124` 现已把 lane / filelock 表述为 Host 设计要求沉淀到 `dayu.runtime` 的能力，并把 ToolsDiscovery / ScenePrepare 表述为若后续放入 runtime 时必须遵守的边界。
- `dayu/README.md:136-146` 现已区分 `dayu.runtime` 当前已有能力和 Host 设计要求沉淀到 runtime 或保持为 runtime 边界约束的能力；当前已有能力只列日志装配 / 日志 level 与取消等待 / race helper。
- `dayu/README.md:194-203` 已规定工具声明、治理、执行边界：Host 接收业务 `ToolBundle`，Engine 只接收 `tool_schemas` 与 `tool_executor`。
- `dayu/contracts/tool_declaration.py:7-15` 已规定 `ToolDefinition` / `ToolBundle` 是 Host / ToolRuntime 装配输入，Engine / Runner 只能消费投影后的 `ToolSchema`。
- `dayu/contracts/tool_declaration.py:121-128` 已存在 `ToolBundle` dataclass，当前没有 `dayu.host` 包，Phase 1 可以建立 Host public typing 而无需移动现有 tool contract。
- `dayu/runtime` 当前没有 `lane.py`、`filelock.py`、ToolsDiscovery 或 ScenePrepare 实现；README 已不再把这些能力描述为当前已稳定承载的代码能力。

## Design Refinement Decision

需要细化后再进入 implementation-ready plan；已完成文档细化。

本次 refinement 的核心判断：

- Host API request / snapshot / status / error / `HostCallContext` / `OperationContext` 是 Host public API contract，应放在 `dayu.host` 公共命名空间，不应放入 `dayu.contracts`。理由是这些类型表达 Host 治理语义，Service / UI 可以向下依赖 Host，Engine 不应理解它们。
- `ToolBundle`、`ToolDefinition`、`ToolSchema`、`ToolExecutor`、批式工具调用 / outcome、取消观察 token、严格 JSON 值属于 Host 与 Engine / ToolRuntime 共同理解的协作契约，应继续放在 `dayu.contracts`。
- Host construction input 必须以 `HostToolingOptions` 这类 typed options 接收 construction-time business `ToolBundle`、source refs 与 framework tool policy view；Start / follow-up / retry / replay / resume request 不得携带 raw `ToolBundle`。
- Phase 1 原本把 ToolsDiscovery / ScenePrepare 放入 implementation slice 过大。当前设计没有足够 typed manifest / provider contract 支撑直接实现它们；把它们夹带进 Phase 1 会迫使 implementation agent 现场设计业务装配与场景输入。已将其改为边界确认与后续独立 phase。
- `dayu.runtime.lane` 与 `dayu.runtime.filelock` 的层中立边界足够明确，可以进入 Phase 1 plan；它们不得表达 Host truth、EventLog ordering、Run / Attempt owner、SQLite transaction 或 CAS 状态迁移。

## Changed Files

- `dayu/README.md`
- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`

## Blocking Questions

无。

## Non-Blocking Assumptions

- Phase 1 implementation-ready plan 可以创建 `dayu.host` 公共类型模块，但不需要实现 Host command path、SQLite store、Engine 执行路径或业务财报工具扫描。
- `FrameworkToolPolicyView` 在 Phase 1 只需要覆盖 framework tool reserved-name / enablement 的 typed policy view；完整 ToolRuntime policy 在后续 ToolRuntime phase 细化。

## Residual Risks

- 已修复 / 已消除：`dayu/README.md` Runtime 段曾把 lane、filelock、ToolsDiscovery、ScenePrepare 列在“当前稳定承载”下，与当前 `dayu/runtime` 文件事实和 Phase 1 收敛范围不一致。现已改为“当前已有能力”和“Host 设计要求沉淀到 runtime 或保持为 runtime 边界约束”的两组表述。
- `HostToolingOptions` 当前只定义最小 construction-time shape。后续多 scene tool profile、profile registry、tool snapshot durability 与 source ref digest 算法仍需在 ToolRuntime / command path 相关 phase 细化。
- Host public API 类型虽然已明确归属 `dayu.host`，但具体模块拆分、`__all__` 导出边界和测试矩阵仍需在 implementation-ready plan 中列为可审查 slice。

## Ready For Phase Design Review

是。

当前没有 material open question 阻塞进入 phase design review。ToolsDiscovery / ScenePrepare 后置已在设计文档、总控文档和 `dayu/README.md` 中保持一致。

## Artifact Path

`docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`
