# Host P5 Tool Declaration Plan Review

## 当前总控决策

本文保留此前 “最小公共 tool declaration” plan review 的历史结论，但它不再单独代表当前 P5 可进入实现。
用户二次人工 review 已废弃 `double_echo` 临时方向，改为 `huge_echo`：手工 smoke 必须真实向
`mimo-v2.5-pro-plan` 发送 prompt，由模型通过 LLM tool calling 调用公共
`@tool(..., truncate=ToolTruncateSpec(...))` 声明的 `huge_echo`，并跑通真实 Host ToolRuntime
truncate / fetch_more。当前 P5 plan 正在按该目标修订，决策记录见
`docs/host/phase5-huge-echo-plan-note.md`；需重新复审后才能进入实现。

## 结论

有条件通过。

本次 P5 plan 修订的动机成立：P5 本来就要用真实 ToolRuntime 稳定制造截断、cursor 与
`fetch_more` facts；如果继续把 OLD-like `@tool(..., truncate=ToolTruncateSpec(...))` 留在
`utils` 局部 smoke registry，schema、executor binding 与 Host ToolRuntime metadata 仍会在真实工具接入时分散。
把“最小公共 tool declaration / definition”纳入 P5，属于为 P5 纵向 smoke 提供同源声明能力，不等同完整
ToolRegistry / 权限治理 / Service catalog，因此没有破坏 P5 no-full-governance scope。

通过条件是：实现与 code review 必须直接验证 `ToolDefinition` / `ToolBundle` 不会被 Engine 误消费为
LLM-facing tool schema；进入 Engine / Runner 的仍只能是 `ToolSchema`，Host ToolRuntime 只从 definition /
bundle 中提取 `ToolTruncateSpec` 和 executor binding。该条件不要求再修 plan 才能进入实现，但必须作为 P5
code review 的显式检查点。

## Findings

### P2 重要：[已修复] `ToolDefinition` 位于公共 contracts 后，必须防止 Engine 误消费 Host metadata

证据：

- `docs/host/phase5-plan.md:206-210` 计划新增 `dayu/contracts/tool_declaration.py`，并让
  `ToolDefinition` / `ToolBundle` 同时携带 name、LLM-facing `ToolSchema`、callable / executor binding、
  `ToolTruncateSpec` 与 display metadata。
- `docs/host/phase5-plan.md:373-378` 已声明公共 tool declaration 不让 Engine 理解 Host cursor、memory、
  compact 或 display metadata，ToolRuntime 只消费其中的 `ToolTruncateSpec`。
- 当前 Engine 契约仍是 `AgentRunRequest.tool_schemas: tuple[ToolSchema, ...]` 与
  `AgentRunRequest.tool_executor: ToolExecutor`；Engine / Runner 只序列化 `ToolSchema`。

影响：

计划语义是正确的，但 `dayu.contracts` 同时被 Host 与 Engine 稳定依赖。`ToolDefinition` 一旦成为公共符号，
后续实现者可能把它直接传给 `AgentRunRequest.tool_schemas`，或让 Engine 侧代码读取 display / truncate metadata。
这会把 Host runtime metadata 泄漏到 Engine 边界，形成 semantic vs implementation mismatch。

建议：

P5 实现时补充直接 guard：

- `tests/contracts/test_tool_declaration.py` 断言 definition 到 Engine 的投影只产生 `ToolSchema`。
- P5 Host 测试或 code review 明确检查 `AgentRunRequest.tool_schemas` 只接收 `definition.schema`，不接收
  `ToolDefinition` / `ToolBundle`。
- `dayu/contracts/tool_declaration.py` 模块 docstring 写清楚：definition 是装配输入，不是 Engine tool schema，
  不是 registry，不承载权限治理。

该 finding 不阻断 plan，因为 plan 已经写明边界；它是实现 gate 条件。

修复状态：

已写回 `docs/host/phase5-plan.md`。P5 plan 现在要求 `ToolDefinition` / `ToolBundle` 提供明确的
`ToolSchema` projection，例如 `to_tool_schema()` 或只读 `schema`；Engine / Runner request 只能接收
`tuple[ToolSchema, ...]`，不得接收 definition / bundle 本体。测试清单、ToolRuntime / EngineWorker / Engine
边界、Code review gate 与停止条件也已补充直接 guard，要求断言 Engine request / WorkerProxy request 不含
`ToolTruncateSpec`、display metadata、tags、callable 或 executor binding。待复审确认。

### P3 非阻断：[已修复] 既有 P5 plan review 通过结论不能单独代表本次范围变更

证据：

- `docs/host/migration-plan.md:15-18` 明确当前进入 P5 plan 修订阶段，用户人工 review 后新增
  OLD-like `@tool(..., truncate=ToolTruncateSpec(...))` 与 `huge_echo` 方向调整。
- 既有 `docs/host/phase5-plan-review.md` 与 `docs/host/phase5-old-new-review.md` 的复审结论主要覆盖
  terminal 前 `fetch_more`、真实 ToolRuntime 参与、pinned_state 与文档同步旧口径清理。
- 旧 `double_echo` code/decorator review 只覆盖已废弃的临时方向，不能作为当前 `huge_echo` + real provider
  smoke 目标的通过证据；相关临时 review 文档已从当前待提交产物中移除。

影响：

如果只看原 `phase5-plan-review.md` 的“通过”，容易误以为 P5 已经在旧 scope 下完成 plan gate，忽略本次新增的
公共契约能力。该风险是流程状态歧义，不是 plan 内容阻断。

建议：

本文件应作为 P5 tool declaration 范围变更的新增 plan review gate。实施前需要以本文件的“有条件通过”为准；
若总控要求所有 review 文档自解释，可在既有 plan review 文档或迁移状态处追加一行“tool declaration 范围变更已由
`phase5-tool-declaration-plan-review.md` 复审通过”。不需要重写旧 findings。

修复状态：

已写回 `docs/host/phase5-plan.md` 的 Review Gate，并小幅更新 `docs/host/migration-plan.md` 当前状态。本次
tool declaration scope 变更以本文档作为新增 plan review gate；旧 P5 plan review 通过结论不能单独代表当前
scope。当前状态为有条件通过，finding 已修订，待复审确认。

## 复审要点

### 1. P5 是否适合承接最小公共 tool declaration

适合。

P5 的目标是把 P1-P4 的真实路径串成可观察 smoke，其中工具截断和补读是主链路事实之一。`ToolTruncateSpec`
已是公共 contracts 层契约，且当前痛点正是 LLM schema、executor binding 与 truncate metadata 分散。P5 只新增
declaration / definition，不新增权限、发现、middleware、审计 hard-gate、Service catalog 或业务工具迁移，因此仍在
no-full-governance scope 内。

### 2. ToolSchema / ToolTruncateSpec / display metadata 是否分清

分清。

计划明确：

- `ToolSchema` 只投影给 LLM。
- `ToolTruncateSpec` 是 Host ToolRuntime metadata，不进入 LLM schema。
- `@tool(..., display_name="...")` 是可读声明入口，内部展示 metadata 为 `ToolDisplayInfo` / `tags`；
  这些信息不影响模型可见描述。
- P5 修订后会恢复最小 framework `fetch_more` schema 与 LLM-facing truncation hint；`ToolTruncateSpec`
  本体仍是 Host ToolRuntime metadata，不进入 LLM schema。

### 3. `dayu/contracts/tool_declaration.py` 落点是否合理

合理，优于放入 `dayu.runtime` 或 `dayu.host`。

`dayu.contracts` 已承载 `ToolSchema`、`ToolExecutor`、`ToolTruncateSpec` 与工具结果契约；新增 declaration helper
如果只依赖标准库和 `dayu.contracts` 内部类型，不 import Host / Engine / Service / UI / Fins，就符合分层。它不是
runtime 通用并发 / 日志 / race helper，也不应进入 `dayu.runtime`。

实现时需要保持 display metadata 为层中立数据，不引入 UI 类型、组件或展示策略。

### 4. `_get_xxx_tool_definition` / `ToolDefinition` 命名是否更准确

更准确。

计划返回值包含 schema、callable / executor binding、truncate spec 与 display metadata，不只是 LLM-facing
`ToolSchema`。因此 `_get_xxx_tool_definition(...)` 或 `_get_xxx_tool_bundle(...)` 比
`_get_xxx_tool_schema(...)` 更能避免误导。只有纯 schema factory 才应使用 `_get_xxx_tool_schema(...)`。

### 5. `huge_echo` 定位是否正确

正确。

修订后 plan 已把 `huge_echo` 表述为公共声明能力的首个 smoke/test 工具，并明确不能继续把
`utils.host_smoke_tools.py` 的局部 `SmokeToolRegistry` / 泛名 `tool` 当作最终 P5 目标。这修正了先前局部
smoke registry 继续演进的方向风险。

### 6. 是否需要重新经过 plan review gate

需要。

用户人工 review 后新增公共契约能力，属于 P5 scope 的实质变化，不能复用旧 plan review 结论直接进入实现。本文件即为
该范围变更的新增 plan review gate；结论为有条件通过。进入实现后，code review 还必须按本文件的条件核验 Engine
边界与 metadata 分离。

### 7. semantic vs implementation mismatch 风险

主要风险有两个，plan 已基本覆盖：

- 公共 `@tool` 被误解为完整 ToolRegistry / 权限治理入口。plan 已通过非目标、文件清单、停止条件与风险段落明确压住。
- `ToolDefinition` 被 Engine 误消费 Host metadata。plan 已写明 Engine 不理解 display / Host metadata，但实现阶段还需
  直接测试或 review guard，见本 review 的 P2 finding。

## 最终判定

P5 plan 可以在新增 tool declaration scope 下进入实现；无需因该修订退回 P5.5。实现必须守住三条线：

- 公共能力只做 declaration / definition，不做 registry / governance。
- Engine / Runner 只接收 `ToolSchema`，不接收 `ToolDefinition` / `ToolBundle`。
- `ToolTruncateSpec`、display metadata 与 LLM-facing schema 全程分离；framework `fetch_more` 只作为最小运行时
  tool 暴露，不滑向完整 ToolRegistry / 权限治理。

## 复审结论（2026-05-07）

通过。

上一轮两个 finding 均已真正修复，未发现 remaining findings。

### P2 复审

已修复。

直接证据：

- `docs/host/phase5-plan.md` 的 tool declaration 能力段明确要求 `ToolDefinition` / `ToolBundle` 提供
  `to_tool_schema()` 或只读 `schema` 等 Engine input projection，且进入 Engine / Runner 的必须始终是
  `tuple[ToolSchema, ...]`，不得把 definition / bundle 本体传给 `AgentRunRequest.tool_schemas` 或
  WorkerProxy request。
- 契约变化段再次固定：definition / bundle 是工具声明输出，不是 Host runtime governance API；Engine / Runner
  request 不得接收、保存或检查 `ToolDefinition` / `ToolBundle` 本体。
- ToolRuntime / EngineWorker / Engine 边界段明确：WorkerProxy request / `AgentRunRequest.tool_schemas` 中不得出现
  `ToolTruncateSpec`、display metadata、`tags`、callable 或 executor binding；ToolRuntime 可以从 definition /
  bundle 消费 `ToolTruncateSpec`，但不得把该 spec 投影给 LLM。
- 测试清单新增 `test_tool_declaration_keeps_schema_runtime_and_display_metadata_separate` 与
  `test_phase5_engine_and_worker_requests_only_receive_tool_schema_tuple`，覆盖 schema projection、metadata 分离、
  request 只含 `ToolSchema` tuple、request 不含 definition / bundle 及 Host metadata。
- Code review gate 明确要求检查 definition / bundle 降为 `ToolSchema` tuple 后再传入 Engine / Runner，并断言
  Engine request / WorkerProxy request 不含 `ToolTruncateSpec`、display metadata、tags、callable 或 executor
  binding。
- 停止条件明确：如果无法提供 definition / bundle 到 `ToolSchema` 的 projection，或必须把 definition / bundle 本体传给
  Engine / Runner，或 Engine request / WorkerProxy request 中出现 Host metadata / callable / executor binding，则必须停止。

判定：P2 的 root cause 是公共 `ToolDefinition` 位于 contracts 后可能被 Engine 误消费。当前 plan 已在设计约束、边界、
测试、review gate 与停止条件形成同源 guard，足以防止 Host metadata 泄漏到 Engine / Runner。

### P3 复审

已修复。

直接证据：

- `docs/host/phase5-plan.md` 的 Review Gate 明确新增 “tool declaration 范围变更 review”，并指定
  `docs/host/phase5-tool-declaration-plan-review.md` 为新增 plan review gate；旧 P5 plan review 的通过结论不能单独代表当前
  tool declaration scope。
- `docs/host/migration-plan.md` 当前总控状态明确记录：用户人工 review 后新增 tool declaration 方向调整；该 scope
  已新增本文档作为 plan review gate，当前结论为有条件通过，P2/P3 finding 已写回并待复审确认。

判定：P3 的流程歧义已消除。本次 tool declaration scope review 已被明确为新增 plan review gate，旧 P5 plan review
通过不再会被误读为覆盖当前新增 scope。
