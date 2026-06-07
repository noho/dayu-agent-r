# Dayu 开发手册总览

本文档是 `dayu/` 包的开发手册总览。

整体架构如下：

```text
UI -> Service -> Host -> Engine
```

## Agent更新约束【必须遵守】

- 本文档只写当前代码已实现的“总揽级别”的设计意图、整体架构、稳定边界、主要组件、关键执行路径、核心术语、公共契约概览、扩展入口和代码阅读顺序。
- 不写用户手册、安装运行命令、测试清单或文件级流水账。
- 不写过程状态，不写未来计划，不写路线图或时间表，不写实现细节，只保留稳定说明。

## 设计意图

Dayu 是生产级通用 Agent，具备买方财报分析能力，核心范式是“宿主强约束下的 LLM in the loop”。
- LLM 参与分析与生成，但 Session / Run / Attempt 生命周期、取消、恢复、工具治理、事件事实和投影治理由 Host 掌控。
- Engine 提供单次 run 的执行状态机、Runner 协议归一、工具调用闭环与强类型 `EngineEvent stream`。
- Agent 与 Runner 都是 run-scoped 一次性对象：一次 `AgentRunRequest` 对应一次 Agent / Runner 生命周期；run 结束、失败、取消或挂起后，Engine 不复用旧实例。
- Host 的核心设计意图是让 LLM 处于宿主强约束下运行：
  - `Session`、`Run`、`Attempt`、`EventLog` 与同事务状态索引是 Host 治理真源。
  - 同一 Session 的 active Run 由 Host admission 约束；queued Run 是 durable state，不是内存队列。
  - EngineEvent 只是 Host ingest 的输入；Run / Attempt 终态必须由 Host 校验后写入 EventLog 与状态索引。
  - 工具结果、工具等待、重复调用治理和截断治理必须经过 Host-owned ToolRuntime 与 accept barrier。
  - Memory snapshot、timeline、projection、trace、outbox 与 diagnostic 都是派生视图，不能反向驱动 Run / Attempt 状态迁移。

系统优先保证以下性质：

- durable facts 可恢复，EventLog 与同事务状态索引是 Host 治理事实真源。
- 同一 Session 内执行并发受 Host admission 约束，远端执行环境不拥有 Host 状态。
- Engine 只执行单次 `AgentRunRequest`，不持有 Session / Run 生命周期，也不恢复旧 Agent、Runner 或 EngineWorker。
- 工具事实必须经过 Host / ToolRuntime 治理与 accept barrier；assistant final answer 不自动成为 evidence-backed fact。
- 财报文档存取只通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成。


## 整体架构

Dayu 的控制权和依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

- `UI` 负责展示、输入收集、流式订阅和用户动作触发。
- `Service` 负责业务入口、身份解析、场景装配和调用 Host。
- `Host` 负责 Agent 运行宿主边界、状态治理、持久化、工具运行时治理、memory / context governance 和 projection。
- `Engine` 负责单次 run 的模型交互、Runner 协议归一、tool loop 和 EngineEvent 流。

依赖只能沿 `UI -> Service -> Host -> Engine` 向下发生。Engine 不读取 Host durable store，不管理 Session / Run / Attempt；Host 不承载财报业务语义，不直接管理财报原文仓储规则；Service 不绕过 Host 直接控制 Engine。

`dayu.runtime` 是层中立运行期基础设施包，不属于上述任一业务层。它只能承载日志、取消等待、cross-process lane、同步 filelock wrapper、diagnostic 文本脱敏与有界截断、文本 / JSON digest、工具发现装配、配置加载、scene manifest 装配、工具截断声明补齐等通用运行期能力，不持有 Host truth、业务语义或 Engine 协议状态机。

`dayu.documents` 是共享文档处理基础包，也不属于 `UI / Service / Host / Engine` 任一业务层。它承载 Markdown、HTML、Docling JSON 等文档处理器、文档来源协议和 Docling runtime 装配能力，供 Doc 工具、Fins 能力和 Web 转换路径复用；它不持有 Host 生命周期、Engine tool loop、Service 装配状态或财报仓储真源。

`dayu.tools` 是业务工具实现与 provider 适配边界，位于 Host / Engine 之外。工具通过 `dayu.runtime.tools_discovery` 显式 provider 进入 Service 装配，再作为 current `ToolDefinition` 交给 Host ToolRuntime；工具包不拥有 Host 生命周期、Engine tool loop 或财报仓储真源。当前包内的 `_legacy_adapter` 只用于把 OLD 风格同步工具声明适配为 current 工具声明，不是 OLD `ToolRegistry`。

## 稳定边界

### `dayu.contracts`

`dayu.contracts` 承载跨层共享协作契约，例如 JSON 值、取消观察 token、工具声明、工具来源引用、工具调用请求、工具执行结果、工具等待结果和 `ToolExecutor` 协议。它不得依赖 `dayu.engine` 或上层业务包。

公共契约只表达层间协作对象，不承载 UI 展示语义、Service 业务流程、Host 治理状态机、Engine 内部执行状态或财报领域存储规则。若一个类型只被某一层理解，应留在该层内部。

### `dayu.engine`

`dayu.engine` 暴露 Engine 调用方需要的结构契约和函数式执行入口，包括 `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerSpec`、`RunnerCallOptions`、`run_agent_messages` 与 `run_agent_and_wait`。

Runner 实现类不属于 `dayu.engine` 包根公共 API。Engine 只接收 `tool_schemas` 与治理后的 `ToolExecutor`，不导入具体工具实现、Host ToolRuntime、Fins 仓储或 UI / Service 逻辑。

### `dayu.host`

`dayu.host` 包根承载普通 Host public handle 与 Service / UI 可调用的稳定入口，包括 `open_host`、`OpenHostOptions`、`Host`、Session / Run request 与 snapshot 类型、状态类型、错误类型、调用上下文、事件游标、`HostToolingOptions`、`OrdinaryRunExecutionBaseline`、`CompactorRunnerBaseline` 和本地 worker typed construction boundary。

低层 command handle factory、`start_run`、Host durable store、EventLog 内部实现、dispatch scheduler、ToolRuntime factory、policy provider、projection runner 和 storage mutator 不属于 `dayu.host` 包根公共命名空间。普通聊天式输入应通过 `submit_followup` 进入 Host admission；`start_run` 是低层 command / diagnostic 接口。

Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / replay / memory / context governance / tool governance 的治理真源。Projection、timeline、audit、usage、tool trace、outbox 与 memory snapshot 都是已提交 EventLog 的派生视图，不能反向成为恢复或状态迁移真源。

Host-owned LLM compaction 通过 `OpenHostOptions` 的预算治理配置与 `CompactorRunnerBaseline` 装配。Service / composition root 按 execution profile 的 `compactor_baseline.scene_id` 装配 compactor system prompt 与 AgentPolicy，按 `compactor_baseline.user_prompt_template_path` 读取 user prompt template 后传入 Host；Host 在自己的 Context Governance 边界内构造 compaction request、替换 template 中的 request 数据块、校验 candidate，并写入 compact artifact 与 canonical event。

### `dayu.service`

`dayu.service` 承载 Host 外部的 Service composition helper。当前 `host_assembly` helper 从 runtime typed config、runtime locations、工具发现结果、prepared scene、显式 override 与 env/secret mapping 组合 `OpenHostOptions` 与 `SubmitFollowupRequest`。

Service composition root 负责把业务 provider 的显式配置映射为 Host construction-time inputs。例如启用 Fins download / preprocess awaiting providers 时，Service 基于 provider id、import path、source id 与 provider config 校验同一绝对 workspace root，并为 Host `HostToolingOptions` 装配对应 wait adapter registry；`dayu.runtime.tools_discovery` 仍只输出工具 bundle、provider report 与 source refs，不承载 Fins adapter object。

Service 可以依赖 Host / Engine public contracts，但不得让 `dayu.runtime` 反向依赖 Service，不得绕过 Host public handle 写 Host truth，也不得把 raw config fragment、profile id 或 patch dict 传入 Host。

### `dayu.runtime`

`dayu.runtime` 可被多层复用，但不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。各层需要公共运行时能力时，应优先复用或扩展 `dayu.runtime`，避免自行实现语义不一致的 helper。

已实现的层中立能力包括：

- 日志装配与 `VERBOSE` level 注册。
- 协作式取消等待 / race helper。
- `lane`：cross-process named semaphore / capacity guard，只表达 runtime capacity claim，不表达 Host admission、lease、fencing、Attempt owner、EventLog ordering 或 recovery proof。
- `filelock`：第三方 `FileLock` 的同步 wrapper，只用于普通文件访问互斥，不替代 SQLite transaction、EventLog 顺序或 Host 状态机。
- `tools_discovery`：按显式 import path 或 package entry point 解析 provider callable，聚合 provider 输出为业务 `ToolBundle`、provider report 与 source refs；没有业务工具时返回类型真实的内部空 `ToolBundle`；不扫描业务包，不持有 Host / Service 上下文。
- `config_loader`：读取包内默认配置和调用方显式传入的 workspace 覆盖目录，输出 `models`、`execution_profiles`、`host_runtime`、`runtime_lanes` 与 `tool_discovery` 五类 typed config view；不构造 Host，不创建 provider client，不解释 scene manifest，不解析 secret。
- `location`：根据项目根目录与包内配置根目录解析 `workspace/config` 覆盖目录、prompt asset root 与 scene manifest root；ConfigLoader 和 ScenePrepare 不内置 workspace fallback。
- `scene_prepare`：读取调用方显式传入的 scene manifest root 与 prompt asset root，校验 scene-only manifest、加载直接引用的 prompt fragments，用 typed context slot values 渲染 system messages，并输出已拼接的 system prompt、工具选择、model hints、typed agent policy override、fragment refs、source refs 与 content digest；不读取 ConfigLoader，不做工具发现，不表达 workflow、conversation lifecycle 或 Host runtime 部署。
- `assembly`：提供 runtime-neutral 的 catalog selection、typed allowlist override merge、Agent policy 字段来源诊断与工具截断 policy defaults 投影；不构造 Host / Engine typed object。
- `tool_truncation`：把允许缺省 limit / TTL 的 `ToolTruncateSpec` declaration 按调用方提供的 policy defaults 补齐为 effective spec；不导入 Host 或 Engine。
- `diagnostic_text`：提供层中立 diagnostic 文本敏感值检测、局部脱敏和有界截断；不承载 Host / Engine 诊断事件语义、provider payload 语义或业务字段语义。
- `_digest`：提供层中立 canonical JSON digest 与 UTF-8 文本 digest helper，输出稳定 `sha256:<hex>` 摘要；不承载业务身份、Host truth 或 Engine 协议语义。

### `dayu.documents`

`dayu.documents` 承载共享文档处理基础能力，包括文档来源协议、通用处理器注册表、Markdown 处理器、HTML 处理器、Docling JSON 处理器、HTML 清洗 / 抽取 / markdown 渲染原语和 Docling PDF runtime 装配 helper。该包不依赖 Host、Engine、Service、UI、Fins 或具体工具实现。

文档处理器只负责把调用方提供的文档来源解析为章节、表格、全文、页内容和搜索命中等业务可读结构；路径权限、工具参数校验、工具执行、截断、`fetch_more`、财报仓储访问和 Host accept barrier 都不属于本包职责。

### `dayu.tools`

`dayu.tools` 承载业务工具实现、工具 provider 和迁移期私有适配器。工具声明必须输出 current `ToolDefinition`，并经 `dayu.runtime.tools_discovery` 显式发现后交给 Service / Host 装配。

`dayu.tools._legacy_adapter` 只收集 OLD 风格 decorator metadata、执行参数投影、路径策略校验、同步 callable 到 async callable 的适配，以及 OLD 返回 / 异常到 current outcome 的投影。它不迁移 OLD `ToolRegistry`、OLD 截断 manager、OLD `fetch_more` 或 OLD 截断 / fetch-more 投影逻辑。

### `dayu.fins`

`dayu.fins` 是财报领域能力边界。财报文档、解析结果、索引和证据锚点的持久化入口必须收敛到 `dayu.fins.storage` 的仓储协议与实现；Host 和 Engine 不直接读取或写入财报原文存储。

## 核心术语

- `Session`：一条可持续的会话上下文，由 Host 管理生命周期。
- `Run`：用户可见的一次 Agent 目标 / 问题 / follow-up，属于一个 Session。
- `Attempt`：Host 为完成某个 Run 派发给本地或远程 EngineWorker 的一次执行；继续、恢复、重试或重放都不复用旧 Agent / Runner / EngineWorker。
- `EventLog`：Host append-only 事件事实源；Run / Attempt 状态、RunResult、timeline、trace、audit、outbox 和 memory 都从它或同事务状态索引派生。
- `EngineEvent stream`：EngineWorker 执行 Engine 时产出的事件流，是 Host ingest 的输入，不是 Host 事实真源。
- `RunnerEvent stream`：Runner 到 Agent 的 provider 协议归一事件流，只在 Engine 内部消费。
- `Host event stream`：Host 面向 UI / CLI / Web / GUI 暴露的订阅与补读事件流，来自 EventLog cursor。
- `ToolBundle`：外部装配好的非空业务工具声明集合，通过 `HostToolingOptions` 显式传给 Host construction。
- `ToolRuntime`：Host-owned 工具治理模块，负责工具执行、截断、等待、重复调用治理、诊断与工具事实 accept barrier。
- `Context Governance`：Host 对上下文预算、compaction、pinned state、accepted tool evidence、open questions、assumptions 和 compact 事件的治理 orchestrator。

`turn` 不用于描述 Engine / Runner 执行路径；如需表达用户视角的多轮对话，应明确其与 `Session`、`Run` 的关系。`resume` 不表示恢复旧 Agent / Runner / EngineWorker 实例，而是基于 canonical EventLog facts 构造新的 `AgentRunRequest` 并创建新的 Attempt。

## 日志与可观测性

日志用于诊断系统执行过程，不承担 UI 输出、审计真源、tool trace 热 / 冷数据、EventLog canonical fact 或 projection checkpoint 职责。需要稳定查询、审计、恢复或投递的事实必须进入对应 typed EventLog / projection / audit / tool trace 机制。

日志级别语义：

| 级别 | 用途 |
| --- | --- |
| `DEBUG` | 执行细节，例如有界策略分支、事件分类、计数、cursor、CAS 结果和 diagnostic refs。不得输出大 prompt、大 tool result、delta 全量、provider secret、完整业务 payload 或财报原文。 |
| `VERBOSE` | 执行路径骨架，例如 Engine run、iteration、Runner 调用、tool loop、Host command、dispatch、ingest、terminal closeout 和 projection catch-up。 |
| `INFO` | 重要信息，例如进程启动、Host handle / scheduler 启停和 run finished 摘要。 |
| `WARN` | 可恢复异常，例如 provider 临时失败后 retry、projection catch-up 失败但 command 已提交、worker startup / closeout 可诊断失败。 |
| `ERROR` | 本次操作失败，例如 Engine run failed、Host command 无法完成、dispatch / worker 本次执行失败。 |
| `CRITICAL` | 系统 invariant / contract 被破坏，例如 EventLog / state index 不一致或 ToolRuntime accept barrier 被绕过。 |

`dayu.runtime.log_levels` 是层中立日志 level 数值真源；`dayu.runtime.log` 负责把 `VERBOSE=15` 注册为 stdlib level name 并装配日志。Engine 只使用 stdlib logger，由上层完成日志装配。

## 扩展入口

- 新 UI / CLI / Web / GUI 入口：通过 Service 解析身份、场景和调用上下文，再调用 `dayu.host` public handle；不要直接控制 Engine。
- 新业务工具：用 `@tool(...)` 同源声明 schema、展示信息、截断声明和 callable，经 `dayu.runtime.tools_discovery` 或外部 composition root 组装为 `ToolBundle`，通过 `HostToolingOptions` 传入 Host construction。
- 新 scene manifest：通过 `dayu.runtime.scene_prepare` 在 Host 外部装配成 typed scene inputs，再由 `dayu.service.host_assembly` 或等价 Service composition root 显式映射到 Host construction-time inputs 与 per-run request inputs。
- 新 provider request extension DSL：在 `dayu.engine.provider_extensions` 中映射到 Engine `ProviderRequestExtension` 封闭联合；不要把 Engine contract 解析 helper 放进 `dayu.runtime`。
- 新财报数据能力：在 `dayu.fins.storage` 仓储协议与实现内扩展文档存取；工具或 Service 通过仓储协议访问，不旁路读取文件或数据库。
- 新本地执行能力：实现 `LocalEngineWorkerFactory` / `LocalEngineWorker`，并通过 `OpenHostOptions` 装配到 Host。
- 新上下文压缩能力：通过 Host 的预算治理配置和 `CompactorRunnerBaseline` 装配 Host-owned LLM compaction；compactor system prompt 与 AgentPolicy 由 Service 从 scene asset 装配，user prompt template 由 Service 从 compactor baseline prompt asset 读取，compaction 生命周期仍属于 Host，不放到 Service 或 UI。
- 新运行期通用能力：优先放入 `dayu.runtime`，并保持层中立 import 边界。
- 新 projection / sink / trace 能力：消费 committed EventLog 与 checkpoint，不写 Host canonical facts，不改变 Run / Attempt 治理状态。

## 代码阅读顺序

1. `dayu.contracts`：先理解跨层工具、取消和 JSON 契约。
2. `dayu.engine/README.md` 与 `dayu.engine` 包根：理解 Engine public contract、函数式入口、AgentRunRequest / EngineEvent / RunnerEvent 的关系。
3. `docs/host/design.md` 与 `dayu.host/README.md`：理解 Host 稳定设计、Session / Run / Attempt / EventLog、admission、dispatch、ToolRuntime、memory / context governance。
4. `dayu.host` 包根与 `dayu.host.open_host`：理解 public handle、`OpenHostOptions`、普通 command facade 和本地执行装配。
5. `dayu.runtime`：理解日志、取消、lane、filelock 等层中立运行期能力。
6. `dayu.documents`：理解共享文档处理器、Source 协议和 Docling runtime 的层外基础能力。
7. `dayu.tools`：理解业务工具 provider 和 legacy adapter 如何输出 current `ToolDefinition`。
8. `dayu.service/README.md` 与 `dayu.service.host_assembly`：理解 Host 外部 runtime assembly 如何生成 Host public typed inputs。
9. `tests/README.md` 与对应测试目录：用测试确认边界约束、公共入口和关键状态机行为。
