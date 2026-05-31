# Phase 12 ToolsDiscovery / ScenePrepare 讨论稿

## 文档职责

本文档是 Phase 12 design discussion 的临时讨论稿，用于防止讨论结论遗忘。

本文档不是 Host 设计真源，不替代 `docs/host/design.md`；只有经用户确认并写回
`docs/host/design.md` 的内容才成为 Phase 12 设计依据。

## 当前已确认

- Phase 12 的目标仍是实现 Host 外部的工具发现 / 注册与场景准备 runtime assembly 边界。
- `ToolsDiscovery` 与 `ScenePrepare` 落入 `dayu.runtime`。
- `dayu.runtime` 仍必须保持层中立：不得 import `dayu.host`、`dayu.engine`、`dayu.service`、
  `dayu.ui`、`dayu.fins` 或具体业务工具包。
- 当前项目 `dayu-agent-r` 已定义的 `@tool`、`ToolDefinition` 与 `ToolBundle` 是工具声明契约真源；
  旧项目只作为 scene manifest 形式与经验参考。
- Phase 12 不应新增 Host public command、Host handle method、Host opener option 或 Host request field。
- 若为了最佳实践必须调整跨层公共契约，可以小范围修改 `dayu.contracts`；不应为了避免改 contracts
  而让 `dayu.runtime` 反向依赖 Host 或复制 Host 私有类型。
- Phase 12 增加旧项目 `dayu-agent` scene manifest 与其引用的 prompt fragment assets 迁移任务：按新
  ScenePrepare schema 迁移到当前项目配置资产目录。该迁移覆盖 scene manifest 以及 manifest 直接引用的
  prompt fragment assets，例如旧项目 `base/*.md` 与 `scenes/*.md`；不迁移 `tasks/*`、contract files、
  workflow 产物或其它未被 scene manifest 直接引用的业务模板。这些配置资产不得进入 `dayu.runtime`。
- Phase 12 增加 ConfigLoader 任务：Service 需要通过 ConfigLoader 从配置文件加载模型与运行参数，才能把
  `ScenePrepare` 输出的 `model_hints` / `runtime_hints` 映射成 `RunnerSpec`、`RunnerCallOptions`、
  `AgentPolicy` 或其它现有 typed input。ConfigLoader 位于 `dayu.runtime`，与 `ScenePrepare` 一样对 Host、
  Engine、Service、Fins、UI 与具体业务工具一无所知；它只输出层中立 typed config view。

## 设计目标复述

Phase 12 应让外部装配方在 Host construction / Service request envelope 前完成以下事情：

- 通过 typed provider / manifest assembly 得到业务 `ToolBundle` 与 source refs。
- 通过 scene manifest / fragments 得到 typed scene inputs。
- 让 Host 只接收显式 typed inputs，不 import 业务工具、不扫描业务包、不拼财报场景 prompt。
- 让 `ScenePrepare` 只表达 scene 的 prompt / tool selection / runtime hint，不拥有 Session / Run /
  Attempt / EventLog truth。
- 让 `ToolsDiscovery` 只表达工具声明聚合，不参与 ToolRuntime accept barrier、Run lifecycle 或 EventLog。

## ToolsDiscovery 建议方案

### 当前已接受的方向

已接受的 ToolsDiscovery 方向：

- 工具包显式暴露 provider 入口，由 provider 返回该工具包愿意公开的工具定义集合。
- 配置文件只声明启用哪些 provider 入口；第一版一步到位支持显式 provider 函数 import path 与
  Python package entry point 两类入口，但都必须解析到显式 provider callable。
- `ToolsDiscovery` 只加载配置中明确声明的 provider，不递归扫描 package，不猜测 module 内哪些对象是工具。
- 工具包新增工具时，只修改工具包自己的 provider；Host 与 `dayu.runtime` 不需要了解业务包内部结构。
- provider 可返回结构化结果，至少包含 provider identity、version 与 `ToolDefinition` 集合。
- 配置中的 provider identity / version 与 provider 返回值必须有明确真源关系；倾向于 provider 自己声明
  identity / version，配置只负责启用 import path，`ToolsDiscovery` 负责校验不一致并报错。

示意配置：

```json
{
  "tool_providers": [
    {
      "provider_id": "fins.core",
      "import_path": "dayu_fins_tools.provider.get_tool_definitions"
    }
  ]
}
```

示意 entry point 配置：

```json
{
  "tool_provider_entry_points": [
    {
      "group": "dayu.tool_providers",
      "name": "fins.core"
    }
  ]
}
```

示意工具包 provider：

```python
@tool(...)
async def read_financial_statement(...):
    ...


@tool(...)
async def search_annual_report(...):
    ...


def get_tool_definitions() -> tuple[ToolDefinition, ...]:
    return (
        read_financial_statement,
        search_annual_report,
    )
```

上例中 `@tool(...)` 使用当前项目 `dayu-agent-r` 的契约，会把被装饰函数凝聚为
`ToolDefinition`；provider 返回的是显式列出的 definitions。

### 不建议的方案

不建议把隐式命名约定作为主入口，例如 `_get_xxx_tool_defination` 或 `_get_xxx_tool_definition`
自动扫描：

- 命名约定脆弱，拼写错误难以类型检查。
- 难以稳定表达 provider identity、version、digest 与 source refs。
- 容易滑向 runtime 主动扫描业务包，破坏 `dayu.runtime` 层中立边界。
- 难以清晰处理 duplicate tool name、reserved framework tool name conflict 与 provider 级错误归因。

### 建议的主入口

采用显式 provider 协议。工具模块可以用当前项目的 `@tool(...)` 声明单个 `ToolDefinition`，再由显式
provider 函数返回这些 definition。

建议 provider 最小语义：

- `provider_id`：稳定 provider 标识。
- `version_ref`：可选版本引用。
- `definitions`：`tuple[ToolDefinition, ...]`。
- `source_refs` 或足以生成 source refs 的 typed 元数据。
- `content_digest`：由 runtime aggregator 基于 provider output 稳定计算，或由 provider 显式提供后再校验。

建议 runtime 输出：

- `ToolBundle`：合并后的业务工具 bundle。
- source refs：可用于 Host construction 的来源引用。
- digest：用于诊断、trace、audit 或后续 attempt snapshot refs。
- provider report：用于解释哪些 provider 被启用、哪些 provider 被拒绝。

### Source refs 与 content digest 当前裁决

已接受 source refs / content digest 的语义：

- `source_refs` 是来源标签，用来解释业务 `ToolBundle` 从哪里来。
- `content_digest` 是内容指纹，用来判断同一 provider 的工具声明内容是否发生变化。
- `source_refs` 必须存在，至少说明 provider 来源。
- `version_ref` 可选。
- `content_digest` 由 `ToolsDiscovery` 基于 provider 输出统一计算，不由 provider 随意填写。
- digest 只基于稳定声明内容计算，例如 tool name、LLM-facing schema、truncate spec、tags 与 display metadata。
- digest 不 hash callable 对象本身。
- Host 只保存 / 透传 source refs 与 digest 用于解释、诊断、trace、audit 或未来 attempt snapshot refs；
  不把它们当权限、lease、fencing、Host truth 或 Run / Attempt owner。

示意 source ref：

```python
ToolBundleSourceRef(
    source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
    source_id="dayu_fins_tools.provider.get_tool_definitions",
    version_ref="v1",
    content_digest="sha256:abc123...",
)
```

### 非 Python tool backend 当前裁决

当前版本不直接支持其它语言实现的 tool backend，不引入 `ExternalToolDefinition`，也不让
`ToolsDiscovery` 直接加载 JS / Go / Rust / Java 等非 Python 工具代码。

保留后续扩展空间的边界：

- `ToolsDiscovery` 只要求 provider 返回当前项目的 `ToolDefinition`。
- 若未来工具由其它语言实现，应由 Python `ToolCallable` adapter 包装外部进程、HTTP / gRPC /
  JSON-RPC、daemon 或 MCP-like 服务，再通过 `@tool` / `ToolDefinition` 暴露给 provider。
- Host / ToolRuntime 仍只看到普通 `ToolDefinition.callable`，不理解外部语言、进程协议或 daemon 生命周期。
- source refs / digest 可以记录 provider import path、外部 backend 标识或 backend digest，但这些只用于解释、
  诊断和追踪，不进入 Host truth。

Phase 12 不实现非 Python backend adapter、外部进程生命周期、MCP / gRPC 协议适配或 daemon hardening。

### 关键校验

`ToolsDiscovery` aggregator 至少应校验：

- provider identity 非空且不重复。
- `ToolDefinition.name == ToolDefinition.schema.function.name` 由当前 contracts 保证。
- 合并后工具名唯一。
- 业务工具不得占用 framework reserved names，例如 `fetch_more`。
- source refs / digest 生成稳定。
- provider 返回空工具集合默认是 error；只有配置显式 `allow_empty=true` 时才允许。

## Source Ref / Contracts 建议

当前 `ToolBundleSourceKind` 与 `ToolBundleSourceRef` 位于 `dayu.host.tooling`。

若 Phase 12 的 `dayu.runtime` 需要产出 source refs，最佳实践是把通用 source ref 类型迁入
`dayu.contracts`，例如 `dayu.contracts.tool_source`：

- `ToolBundleSourceKind`
- `ToolBundleSourceRef`

原因：

- `dayu.runtime` 不能 import `dayu.host`。
- 复制一份 runtime source ref 会制造语义重复。
- source ref 是 Host、runtime assembly、audit / diagnostic 都可能解释的跨层契约，放入 contracts 更合适。

待讨论点：

- 已裁决：Phase 12 应迁移这两个类型到 `dayu.contracts`。
- 已裁决：不为旧 Host 导入路径保留兼容 re-export；按项目规则做全新设计迁移。
- 已裁决：`ToolBundleSourceKind` 不做过度扩展；第一版保持现有语义，确认
  `EXPLICIT_PROVIDER` 覆盖 provider import path / entry point 解析后的 provider callable，
  `CONFIG_BINDING` 覆盖配置绑定来源，`PACKAGE_ENTRYPOINT` 可用于记录 package entry point 来源。

## ScenePrepare 建议方案

旧项目 `dayu/config/prompts` 的 scene manifest 形式值得借鉴，尤其是：

- `schema_version`
- `scene`
- `version`
- `description`
- `capability_tags`
- `extends`
- `model.default_name`
- `model.allowed_names`
- `model.temperature_profile`
- `runtime.agent.max_iterations`
- `runtime.runner.tool_timeout_seconds`
- `conversation.enabled`
- `tool_selection.mode`
- `tool_selection.tool_names`
- `tool_selection.tool_tags_any`
- `defaults.missing_fragment_policy`
- `fragments`
- `context_slots`

但 Phase 12 不应照搬旧项目中 Host 侧 `scene_preparer` 的职责混合方式。当前项目应把 scene
解析与 Host runtime 治理拆开。

Phase 12 应把旧项目 `dayu-agent` 中已验证可用的 scene manifest 与其直接引用的 prompt fragment assets
按新 schema 迁移到当前项目配置资产目录，作为 ScenePrepare parser / assembly 的真实资产验证集。迁移不改变
runtime 边界：`dayu.runtime` 只提供通用 schema、parser 与 assembly helper，不承载具体 prompt asset 内容、
task prompts、contract files、workflow 产物或 Fins storage 访问逻辑。

### Scene manifest 第一版 schema 当前裁决

第一版 scene manifest 字段：

- `schema_version`：manifest schema 版本，用于 parser schema 演进。
- `scene`：稳定 scene id，供 Service、workflow 或未来 skill 引用。
- `version`：scene definition version；不等同于 `schema_version`。
- `description`：人读说明，只用于配置检查、诊断或文档。
- `capability_tags`：scene 能力标签，供未来 workflow / skill 按能力选择 scene。
- `extends`：scene 继承声明。
- `model`：模型选择 hints，包括 `default_name`、`allowed_names` 与 `temperature_profile`。
- `runtime`：运行预算 hints，例如 `agent.max_iterations`、`agent.max_consecutive_failed_tool_batches`
  与 `runner.tool_timeout_seconds`。
- `conversation`：会话模式 hint；不表达 Host Session truth。
- `tool_selection`：工具选择意图，只筛选 ToolsDiscovery 已发现工具，不做 discovery。
- `defaults`：manifest parser / assembly 默认策略，例如 `missing_fragment_policy`。
- `fragments`：prompt fragment refs；Phase 12 迁移 scene manifest 以及它们直接引用的 prompt fragment assets。
- `context_slots`：scene 需要 Service 提供的 typed context slot 名称，不携带值。

`source_refs` 与 digest 不写死在 manifest；由 `ScenePrepare` 基于 manifest 文件、fragment refs 与 assembly
输入统一计算并输出。

### Scene manifest 继承当前裁决

- 第一版支持 `extends`，但只允许单继承。
- `extends` 为空或单元素数组；多元素数组直接报错。
- 循环继承直接报错。
- 子 scene 追加 fragments，不覆盖父 fragments。
- `fragment.id` 与 `fragment.order` 重复直接报错。
- `context_slots` 继承并去重，保持父优先顺序。
- `tool_selection`、`conversation` 与 `runtime` 支持子 scene 显式覆盖；未显式配置时继承父项。
- `model` 必须由 concrete scene 显式声明，不通过继承隐式取得。

### 建议输出边界

`ScenePrepare` 建议输出 typed scene inputs，例如：

- `scene_id`
- `scene_version`
- 已组装的 `system_messages`
- `scene_constraints`
- `tool_selection`
- `runtime_hints`
- `model_hints`
- `required_context_slots`
- `source_refs`
- `content_digest`

这些 output 只进入 Service / Host request envelope 或 Host 外部 composition root；它们不能成为 Host
状态机语义，也不能成为 EventLog truth。

### ScenePrepare 解释权当前裁决

- `ScenePrepare` 拥有 scene manifest 的解释权。
- `context_slots` 在 manifest 中只声明 scene 需要哪些 typed context values。
- Service 调用 `ScenePrepare` 时必须传入对应 context slot values。
- `ScenePrepare` 负责校验 required slots 是否齐全。
- `ScenePrepare` 负责读取、渲染并按 manifest 规则拼接 prompt fragments。
- `ScenePrepare` 输出已装配好的 `system_messages`，而不是把 fragment 结构交给 Service 二次解释。
- Service 只负责把 `PreparedSceneInputs` 显式映射到 `open_host` construction-time inputs 与 per-run
  request inputs。
- `fragment_refs`、`source_refs` 与 digest 可作为诊断字段输出，用于解释 system messages 的来源；它们不表示
  Service 可以重新解释或重拼 fragments。

理想接口形状：

```python
prepared = scene_prepare.prepare_scene(
    scene_id="interactive",
    context_values={
        "fins_default_subject": "...",
        "base_user": "...",
    },
)
```

输出包含：

```python
PreparedSceneInputs(
    scene_id="interactive",
    system_messages=(...),
    tool_selection=...,
    model_hints=...,
    runtime_hints=...,
    source_refs=...,
    content_digest="...",
)
```

### Model / Runtime hints 当前裁决

- `ScenePrepare` 输出 `model_hints` 与 `runtime_hints`。
- `model_hints` 与 `runtime_hints` 只表达 scene 的执行建议，不是 Host truth。
- `ScenePrepare` 不直接启动 runner，不创建 provider client，不修改 Host policy。
- Service / execution config 负责把 hints 解析并显式映射到 `open_host` construction-time baseline 或
  per-run request overrides。
- Service 若无法把 hints 映射为当前环境支持的 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`
  或其它 typed input，必须在调用 Host 前失败。
- ConfigLoader 是该映射链路的前置能力：P12 重塑配置 schema 为 `models.json`、
  `execution_profiles.json`、`host_runtime.json` 与 `tool_discovery.json` 四类配置视图。

### ConfigLoader 职责边界当前裁决

- `ConfigLoader` 落入 `dayu.runtime`。
- `ConfigLoader` 与 `ScenePrepare` 一样保持层中立，对 Host、Engine、Service、UI、Fins 与具体业务工具一无所知。
- `ConfigLoader` 只负责配置文件原样读取、包内默认配置与工作区覆盖配置的 overlay、typed validation 和 typed config view 输出。
- `ConfigLoader` 不构造 Host。
- `ConfigLoader` 不创建 provider client。
- `ConfigLoader` 不解释、不脱敏、不保护 provider secret；配置中的 provider API key、环境变量引用或其它 provider 参数按 schema 原样进入 typed config view。
- `ConfigLoader` 不解析业务工具，不读取 Fins storage，不解释 scene manifest，不拼 prompt。
- Service / composition root 使用 ConfigLoader 输出，把 `ScenePrepare` 的 `model_hints` / `runtime_hints`
  显式映射为 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 或其它现有 typed input。
- 映射失败必须在调用 Host 前失败。
- ConfigLoader 第一版覆盖 `models.json`、`execution_profiles.json`、`host_runtime.json` 与
  `tool_discovery.json`；旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json` 在新 schema
  落地后删除，不保留兼容读取。

### 明确不做

- 不读取 `dayu.fins.storage`。
- 不内置具体财报 prompt 文案。
- 不导入具体业务工具包。
- 不创建 Host Session / Run / Attempt。
- 不写 EventLog。
- 不构造 ToolRuntime。
- 不把 raw `ToolBundle` 放入 per-run request。

## ToolsDiscovery 与 ScenePrepare 的关系

建议分工：

- `ScenePrepare` 决定 scene 希望启用哪些 tool tags / tool names / runtime hints。
- `ToolsDiscovery` 决定当前装配环境实际有哪些 tools，并产出 `ToolBundle`。
- composition root / Service 把两者输出合并，形成 Host construction 的 `HostToolingOptions`
  以及 per-run 显式工具选择参数。
- Host 只消费已有公共边界，不知道 provider、manifest 文件、fragment 文件或业务工具模块。

## 待逐项讨论

当前讨论稿没有剩余 blocking open。后续若 implementation 或 plan review 发现 schema 字段遗漏，必须回到
`docs/host/design.md` 更新设计真源。

## 已收口的讨论点

- `ToolsDiscovery` 落入 `dayu.runtime`。
- `ToolsDiscovery` 不扫描 package / module；它加载配置中明确声明的 provider import path 或 package entry point，
  且 entry point 也必须解析为显式 provider callable。
- 工具包通过显式 provider 暴露当前项目 `@tool` 产生的 `ToolDefinition` 集合。
- `source_refs` 必须存在；`content_digest` 由 `ToolsDiscovery` 基于稳定声明内容统一计算。
- 当前版本不直接支持非 Python tool backend，但保留通过 Python `ToolCallable` adapter 包装外部 backend 的后续扩展边界。
- provider 返回空工具集合默认 error；只有配置显式 `allow_empty=true` 时才允许。
- `ToolBundleSourceRef` / `ToolBundleSourceKind` 迁入 `dayu.contracts`，不保留 Host 旧导入路径兼容 re-export。
- `ToolBundleSourceKind` 第一版不做过度扩展，复用并确认现有 source kind 语义。
- Phase 12 增加旧项目 scene manifest 与 referenced prompt fragment assets 迁移任务；迁移目标是当前项目
  配置资产，不是 `dayu.runtime`；迁移范围不包含 `tasks/*`、contract files、workflow 产物或未被 scene
  manifest 直接引用的业务模板。
- `ScenePrepare` 拥有 scene manifest 解释权；Service 传入 context slot values，`ScenePrepare` 校验并输出
  已装配的 `system_messages`，Service 不二次解释 fragments。
- `ScenePrepare` 输出 `model_hints` 与 `runtime_hints`；Service / execution config 通过 ConfigLoader
  显式映射为现有 typed input，映射失败时在调用 Host 前失败。
- `ConfigLoader` 位于 `dayu.runtime`，只做配置原样读取 / overlay / typed validation / typed config view 输出；
  不 import 或构造 Host、Engine、Service、UI、Fins、provider client 或业务工具，也不解释 provider secret。
- runtime assembly override 由 Service / composition root 执行，优先级为未来 UI 显式输入 > scene manifest hints >
  ConfigLoader typed config view > 代码默认值。
- 当前 Host public contract 允许的 per-run override 仅为 `SubmitFollowupRequest.system_prompt`、`tool_names`、
  `runner_spec`、`runner_options` 与 `agent_policy`；`open_host(options)` 的 construction-time inputs 不作为
  per-run override。
- ConfigLoader 配置 schema 重塑为 `models.json`、`execution_profiles.json`、`host_runtime.json` 与
  `tool_discovery.json` 四类配置视图，不沿用旧 `llm_models.json` / `run.json` 的混合职责。
- 新 schema 落地后删除旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json`，不保留兼容读取路径。
- ConfigLoader overlay 采用顶层 map 按 id 合并、同 id workspace 整条替换；需要复用时使用单继承
  `extends`，不做隐式 deep merge。
- `tool_selection` 第一版只支持 `mode=all|none|select`；`select` 只支持 explicit `tool_names` 与
  `tool_tags_any` 并集选择，未知 name 报错，tag 无匹配默认报错，只有显式 `allow_empty=true` 时允许空选择。
