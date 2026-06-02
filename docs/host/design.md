# Host 设计

本文档是 Host 唯一设计真源。稳定架构边界、公共接口、状态机、EventLog 语义、恢复语义、执行路径、工具治理、memory / context governance 与后续 public contract 决策只以本文档为准。

## 1. 设计目标

Host 的设计目标是支撑生产级买方财报分析 Agent。系统范式是“宿主强约束下的 LLM in the loop”：

- Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 的治理真源。
- Engine 只执行单次 `AgentRunRequest`，不拥有 Session / Run 生命周期，不持久化 Host 状态，不恢复旧 Agent / Runner。
- 多入口 interactive / web / GUI / CLI / WeChat 共享同一本地 Host 真源。
- 支持单机多客户端 / 多进程，并支持本地 Engine 与远程 Engine 并列执行。

Host 设计必须优先保证：

- durable facts 可恢复。
- 同一 Session 的执行并发受控。
- 远端执行环境不能拥有 Host 状态。
- 工具执行受 Host / ToolRuntime 治理，包括截断、等待、幂等与语义级重复调用治理。
- 工具事实、证据锚点和审计链可追溯。
- assistant final answer 不自动成为 `evidence_backed_fact`。

## 2. 分层边界

整体依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

边界职责：

- UI 负责展示、输入收集、流式订阅和用户动作触发。
- Service 负责业务入口、身份解析、场景装配和调用 Host。
- Host 负责 Agent 运行宿主边界、状态治理、持久化、工具运行时治理、memory / context governance 和 projection。
- Engine 负责单次 run 的模型交互、Runner 协议归一、tool loop 和 EngineEvent 流。

禁止反向依赖：

- Engine 不读取 Host durable store，不理解 Host policy，不管理 Session / Run / Attempt。
- Host 不承载财报业务语义，不直接管理财报原文仓储规则。
- Service 不能绕过 Host 直接控制 Engine。
- Projection、timeline、audit、usage、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源。

Host 内部模块边界：

- Public API layer：只负责 request / context validation、幂等查找与调用稳定服务；不得直接拼 messages、启动 Engine 或写 projection。
- Admission / Queue：唯一负责 Session active Run 判定、queued Run promotion 与 CAS-style admission。
- EventLog / State Transition：唯一负责 EventLog append、`event_sequence` 分配，以及 `canonical_fact` 对 Run / Attempt 索引的原子更新。
- Attempt Dispatch：只消费已提交的 dispatch record / attempt snapshot，负责 LocalProxy / RemoteProxy 派发与 cancel 传播；不得生成治理事实。
- EngineEvent Ingest：唯一负责把 Engine / Worker / ToolRuntime 回传事件验证、分类并转成 Host event。
- RunInputBuilder：唯一负责通过 typed input provider protocols 聚合 EventLog、memory snapshot、compact artifact、tool schema snapshot 与场景约束，构造 `AgentRunRequest.messages`。
- Conversation Memory：只消费 committed canonical EventLog facts，维护 session memory snapshot、stable layer 与 history pool；它是可重建 projection / read model，不是事实真源，不直接写 EventLog，也不由 Context Governance 直接写入。
- Context Governance：唯一负责上下文预算、compact 编排与 compact 事件收口；它是治理 orchestrator，不直接写 memory、audit、trace 或其它 projection。
- ToolRuntime / TruncationManager：唯一负责工具执行治理、截断、`fetch_more`、等待与重复调用治理；工具事实必须走 Host accept barrier。
- Observer / Sink / Projection：只消费 committed EventLog events，维护派生视图和外部投递队列。
- Recovery：唯一负责 Host startup scan、旧 Attempt `LOST` 收口和可恢复 Run 的新 Attempt 创建。

这些模块可以在实现中进一步拆分，但不能互相绕过上述 ownership。尤其是 dispatch、sink、tool runtime 和 remote stub 都不能直接写 Run / Attempt / EventLog。

## 3. dayu.runtime

`dayu.runtime` 是层中立运行期基础设施包，不属于 `UI / Service / Host / Engine` 任一业务层。它只能承载运行期通用、可被多层复用的基础能力；不得承载业务语义、财报语义、Host durable truth、Host 状态治理或 Engine 协议状态机。

`dayu.runtime` 不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。各层需要公共运行时能力时，应优先复用或扩展 `dayu.runtime`，不得在各层自行实现语义不一致的 runtime helper。

当前 Host 设计需要记录的 runtime / external assembly 基础组件：

- `lane`：层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的业务并发、LLM 并发或其它非真源资源容量治理。lane 只表达资源容量，不表达 Session / Run / Attempt owner，不替代 Host admission、SQLite transaction、CAS 状态迁移、EventLog ordering、fencing token、Attempt takeover 或 recovery proof。LLM lane acquire 是可取消的耗时操作；调用方 / supervisor 退出时必须同时触发 Host cancel 与 lane cancel，避免等待 acquire 或已持有容量的 dispatch guard 悬挂。Host 如何使用 lane 控制 LLM 并发的细节属于后续 phase design。
- `filelock`：`dayu.runtime.filelock` 对 `from filelock import FileLock` 的同步统一封装，用于多进程访问普通文件时的互斥保护。filelock 不能表达 Host durable truth、EventLog ordering、Run / Attempt owner，也不能兜底数据库事务。
- `ToolsDiscovery`：独立于 Host 的工具发现 / 注册组件，位于 `dayu.runtime`。它只加载配置中显式声明的 Python provider callable 或 package entry point；entry point 也必须解析为 provider callable。工具包通过当前项目的 `@tool` / `ToolDefinition` 契约显式暴露工具集合，`ToolsDiscovery` 聚合 provider 输出，生成业务 `ToolBundle`、来源 refs 与稳定 content digest，并作为显式参数传给 Host construction / composition root。Host 不做工具发现、模块扫描或注册生命周期管理。`ToolsDiscovery` 只能依赖标准库与 `dayu.contracts`，不得 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。
- `ScenePrepare`：独立于 Host 的场景准备组件，位于 `dayu.runtime`。scene manifest 是 Service 调用 `ScenePrepare` 的 single-run scene assembly input；`ScenePrepare` 根据 manifest、prompt fragments 与 Service 提供的 typed context values 产出 typed scene assembly result。Service 负责把该 result 显式拆分并映射到 `open_host` construction-time inputs 与 per-run request inputs。Host 不读取 scene manifest，不从 scene manifest 自行拼业务 prompt，也不把场景规则写进 Host 状态机。`ScenePrepare` 只能依赖标准库与更底层公共契约；具体财报 scene manifest、业务 prompt 文案、场景策略与业务 context values 属于 Service / 业务配置，不属于 runtime。
- `ConfigLoader`：独立于 Host 的配置加载组件，位于 `dayu.runtime`。它只负责从配置文件原样读取、覆盖合并、typed validation 并输出层中立配置视图，使 Service / composition root 能把 `ScenePrepare` 的 `model_hints` / `runtime_hints` 显式映射为现有 typed execution inputs。`ConfigLoader` 不构造 Host，不创建 provider client，不解析业务工具，不读取 Fins storage，也不得 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。

这些组件服务 Host 装配，但不提升为 Host 治理真源。Host 真源仍是 Session / Run / Attempt / EventLog 与同事务状态索引。

Phase 1 的 runtime 实施范围只包括 `lane` 与 `filelock` 的层中立基础能力，以及 Host construction input 中对外部 `ToolBundle` 的 typed 边界。`ToolsDiscovery` / `ScenePrepare` 在 Phase 1 只固定 import boundary 与责任边界，不落地具体 adapter、manifest schema、业务工具扫描、财报 prompt 组装或 provider 注册生命周期；这些能力若需要代码实现，必须作为独立后续 phase 进入 design refinement。

`ScenePrepare` 只定义单个 Run 的场景装配预设，不定义 workflow。manifest 的稳定职责是描述 scene identity、scene definition version / source digest、prompt fragment assembly、tool selection intent、model hint、可选 agent policy override、required context slots 与可供 workflow / skill 引用的 capability tags / refs。`ScenePrepare` 拥有 scene manifest 的解释权：Service 调用 `ScenePrepare` 时必须传入 manifest 所需的 typed context slot values，`ScenePrepare` 负责校验 required slots、读取 / 渲染 / 拼接 prompt fragments，并输出已装配好的 `system_messages`。Service 不应二次解释 fragments，只负责把 prepared scene result 显式映射到 `open_host` construction-time inputs 与 per-run request inputs。`fragment_refs`、source refs 与 digest 可作为诊断字段解释 system messages 来源，但不作为 Service 重拼 prompt 的入口。`model` 与 `agent_policy` 只是不拥有 Host truth 的 hints / typed override；最终如何选择 runner、model、policy 或 per-run override，由 Service / execution configuration 显式映射到 Host 已冻结的 typed inputs。

ConfigLoader 是 scene / config hints 到 typed execution inputs 的前置配置能力。配置 schema 不沿用旧 `llm_models.json` / `run.json` 的混合职责；稳定配置视图拆分为 `models.json`、`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json` 与 `tool_discovery.json`，并删除旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json`，不保留兼容读取路径。ConfigLoader 不拥有 scene 解释权，不解释 Host lifecycle，不读取 EventLog；配置中的 provider API key、环境变量引用或其它 provider 参数都按配置 schema 原样读取并进入 typed config view。Service / execution environment 负责决定如何使用、脱敏、保护或解析这些配置值。若 Service 无法把 scene hints 与 ConfigLoader 输出映射为当前环境支持的 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 或其它 typed input，必须在调用 Host 前失败。

Config catalog 的 record id 由顶层 map key 提供，record 内不重复 `runtime_id`、`model_id`、`profile_id`、`execution_profile_id` 等 id 字段；typed config view 如需 id，由 ConfigLoader 从 map key 注入。`extends` 引用同一 catalog 的 map key；ConfigLoader validation 不接受重复 id 字段，避免 key / value 不一致和新旧 schema 并存。

`models.json` 是模型目录，只表达 provider / model 能力与请求基础参数：runner kind、provider、model、endpoint、`api_key_ref`、headers、tool calling / streaming / stream usage capability、default timeout、max retries、SSE idle timeout / heartbeat、provider request extension、context window tokens 与 provider/model-specific `runtime_hints.runner_option_hints`。`runner_option_hint_id` 是 semantic call style selector，例如 `interactive`、`overview`、`audit`、`decision`、`write`、`infer` 与 `conversation_compaction`；具体 `temperature`、`top_p`、`stream` 等 RunnerCallOptions 值由 effective model 的 hint 表解释，不放入全局 execution profile。默认 config 不使用 `max_tokens` 限制模型输出；若未来需要输出 token cap，必须作为显式 per-run / provider adapter override 或 provider-specific public contract 重新设计，不能回到默认 model hint。

`execution_profiles.json` 表达 execution baseline 与治理策略选择。顶层 selector 使用 `default_execution_profile_id`，catalog 使用 `execution_profiles`；默认 profile id 可以按场景与窗口分档，例如 `standard-256k`、`standard-1m`、`wechat-256k` 与 `wechat-1m`。单个 execution profile 至少包含 `run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy` 与内嵌 `agent_policy`。`run_baseline` 保存默认 `model_id` 与 `runner_option_hint_id`；`compactor_baseline` 保存 compactor 专用 `model_id`、`scene_id`、`runner_option_hint_id`、`user_prompt_template_path` 与 artifact root，默认 compactor scene、runner hint 与 user prompt template 分别为 `conversation_compaction`、`conversation_compaction` 与 `scenes/conversation_compaction_user.md`。默认 compactor model 由 execution profile 的 `compactor_baseline.model_id` 表达；packaged 默认应选择低延迟 flash-tier 模型，因为 compact 是低温度、无工具、结构化 JSON proposal 任务，优先需要快、稳定、可重试。高规格 compact 模型只能由 profile 显式选择，不由 scene 或 Host 代码隐式切换。`conversation_compaction` scene manifest 中若保留 `model.default_model_id`，其 packaged default 必须与默认 execution profile 的 compactor model 对齐，或被明确标记为非治理 fallback；不得与 profile 默认给出互相矛盾的 compactor model truth。compactor 的 system prompt、AgentPolicy 与 user prompt template 不写在 Host 或 Service 代码中；Service / composition root 必须按 `compactor_baseline.scene_id` 装配 compactor scene asset，从 scene 读取 compactor system prompt 与完整 `agent_policy`，并按 `compactor_baseline.user_prompt_template_path` 读取 user prompt template，然后作为 typed `CompactorRunnerBaseline` 字段传入 Host。普通 `agent_policy` 一比一对齐 Engine / Host public `AgentPolicy` typed shape，使用 `max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt` 与 `max_consecutive_failed_tool_batches` 等稳定字段；`fallback_mode` 只允许 `force_answer` / `raise_error`，默认 `force_answer`，默认 `fallback_prompt` 为“请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。”。`execution_profiles.json` 不保留顶层 `agent_policy_profiles` catalog、`agent_policy_profile_id`、`runner_options_profiles`、`runner_hints` 或 `agent_hints`。

execution profile 选择是 Service / composition root 的显式业务决策，不由 helper 根据 `models.context_window_tokens` 隐式切换。Service 可以根据业务场景、响应速度和 effective model 选择合适 profile；assembly helper 只做兼容性校验和诊断，例如 1M profile 搭配 256K 模型时 fail fast 或输出明确 diagnostic，256K profile 搭配 1M 模型时可允许但提示策略较保守。若需要机器可读约束，profile 可增加 `context_window_class` 或 `min_context_window_tokens` 一类字段；这些字段只用于校验，不用于自动选择。

`context_budget_policy` 对齐 ratio-first Host public `ContextBudgetPolicy`，只表达治理策略，不表达模型能力或本次调用输出预算。Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `ContextBudgetPolicy.context_window_size` 直接传入 typed policy。`ContextBudgetPolicy` 至少包含 `context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、`max_proactive_compactions_per_run`、`max_reactive_compactions_per_run`、`max_compaction_attempts_per_operation` 与 `policy_ref`；Host 内部根据 ratio 计算 soft / hard threshold tokens。旧的 `max_context_tokens`、`reserved_response_tokens`、`reserved_output_tokens`、`minimum_protection_tokens` 与 `compaction_trigger_tokens` 不作为 config/public policy 字段暴露。

usage 是 provider capability 驱动的治理观测信号，不是 scene / Service 业务风格参数。流式 OpenAI-compatible 请求在 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时默认请求 `stream_options.include_usage=true`；非流式响应如果 provider 返回 `usage`，Engine 默认读取并上报。Config 不提供 `usage_enabled`、`collect_usage`、`include_usage` 这类 override，也不引入独立 `supports_usage` 字段。Engine 只负责如实上报 usage，不理解 Host budget；Host ingest 负责 durable 化 `usage_reported` 并保留 attempt / execution context、估算 digest、policy ref 等后续消费所需关联信息。Context Governance 可主动消费 usage，但 usage 是 post-call observation，只用于估算器校准、diagnostic 与后续 Run / 后续 compaction 治理参考；不得回头修改当前已经完成的 dispatch decision。usage 缺失、provider 不支持 usage 或 usage 字段格式异常都不得导致 Run 失败。

`memory_projection_policy` 对齐 Host public `MemoryProjectionPolicy`，采用 ratio / floor / cap 自适应预算模型。Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `MemoryProjectionPolicy.context_window_size` 直接传入 typed policy。policy 至少包含 `context_window_size`、`max_pinned_items`、`max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、stable layer ratio/floor/cap、history pool ratio/floor/cap、raw turn ratio/floor/cap、`max_lag_events_for_inline_delta` 与 `max_delta_repair_events`。policy 存在即表示装配 stateful memory projection；不再使用 `enabled` 字段表达单轮 / 多轮语义。

`tool_truncation_policy` 只配置默认治理参数，不配置 per-tool strategy / target。它至少包含 `enabled`、`default_cursor_ttl_seconds` 与 `default_limits`，其中 `default_limits` 覆盖 `text_chars.max_chars`、`text_lines.max_lines`、`list_items.max_items` 与 `binary_bytes.max_bytes`。工具声明负责提供 `ToolTruncateSpec.strategy`、`target_field` / `field_path` 与是否启用截断；如果工具声明启用截断但未提供 limit 或 ttl，Service / composition root 用 policy default 补齐成 effective truncate spec。`fetch_more` 名称由 `FrameworkToolName.FETCH_MORE` 固定，不作为配置项。

`host_runtime.json` 表达 Host opener 的部署默认值：store / artifact roots、SQLite、`host_execution_lane_name`、worker backend、dispatch poll interval 与 memory projection catch-up batch size 等。这些都是 `open_host(options)` construction-time assembly inputs，不是 per-run override。顶层 selector 使用 `default_host_runtime_id`；host runtime record 不重复内部 id。`worker_backend` 当前支持 `local`，未来可扩展 `remote`；ConfigLoader 只读取该值，Service / composition root 负责映射为 `OpenHostOptions.worker_factory`。`runtime_lanes.json` 表达层中立 runtime lane coordinator 与 lane catalog；`host_runtime.json.host_execution_lane_name` 引用该 lane catalog，Service / composition root 再映射到 `OpenHostOptions` 的 lane fields。`tool_discovery.json` 表达 ToolsDiscovery provider 配置：provider id、import path 或 entry point、source kind、source id、enabled 与 `allow_empty`；ConfigLoader 只读出 typed provider specs，ToolsDiscovery 才负责 import provider、聚合 `ToolBundle` 与计算 digest。

ConfigLoader overlay 规则必须保持可预测：包内默认配置与 workspace 覆盖配置按配置文件类型分别加载；顶层 map 按稳定 id 合并，同 id 记录由 workspace 整条替换，不做隐式 deep merge。需要复用配置时使用显式 `extends`，且只允许单继承；继承解析后必须得到完整 typed record。ConfigLoader 不解析环境变量、不替换 secret、不脱敏，只原样读取 schema 表达的值。`dayu.runtime` 提供层中立 location resolver：当 `workspace/config` 存在时输出 `config_overlay_dir=workspace/config`，否则输出 `None`；同时解析 `prompt_asset_root` 与 `scene_manifest_root` 的实际可用路径。ConfigLoader 和 ScenePrepare 都不内置 workspace fallback 策略。

多 Run 财报流程由 Service workflow 或未来 typed Skill orchestration 控制。scene manifest 不表达 step graph、next scene、产物传递、artifact store、structured parser、replay policy、retry / stop policy、failure classification 或 checkpoint / resume 语义。这些属于 Service workflow / skill orchestration 的状态机和持久化边界，不属于 `ScenePrepare`，也不得进入 Host 状态机。Scene manifest 只保留稳定 scene identity、capability tags / refs 与 source digest，作为后续 workflow / skill 可引用的 scene capability。

Scene manifest schema 包含 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments` 与 `context_slots`。`schema_version` 表达 manifest schema 版本；`version` 表达 scene definition version；`scene` 是稳定 scene id；`capability_tags` 用于 Service workflow 或未来 skill 按能力引用 scene。`model.default_model_id` 是 scene 层默认 model 建议，可被 UI / Run override 覆盖；`model.runner_option_hint_id` 是 scene 层调用语义档位建议。scene 不保存 provider-specific runner option 值，不保存 model allow-list，不保存 raw runtime patch dict。`agent_policy` 是可选 typed override block，只允许覆盖 `AgentPolicy` 白名单字段；未知字段必须 fail fast。`context_slots` 只声明 Service 必须提供的 typed context 名称，不携带值。source refs 与 content digest 由 `ScenePrepare` 基于 manifest 与 assembly 输入计算，不写死在 manifest。

`tool_selection` 第一版只支持 names 与 tags 选择，不支持 include / exclude 组合，也不支持 scene 动态替换整个 `ToolBundle`。`mode="all"` 表示使用 construction-time business `ToolBundle` 的全部业务工具，Service 映射为 `SubmitFollowupRequest.tool_names=None`；`mode="none"` 表示本 Run 禁用业务工具，Service 映射为空 `frozenset()`；`mode="select"` 只允许 `tool_names` 与 `tool_tags_any`，显式 names 与 tags 命中的工具取并集后映射为 `SubmitFollowupRequest.tool_names`。未知 `tool_names` 是配置错误；`tool_tags_any` 没有匹配默认是配置错误，只有显式 `allow_empty=true` 时才允许空选择。

Scene manifest 支持 `extends`，但只允许单继承。`extends` 为空或单元素数组；多元素数组和循环继承均为配置错误。子 scene 只能追加 fragments，不覆盖父 fragments；`fragment.id` 与 `fragment.order` 重复均为配置错误。`context_slots` 继承并去重，保持父优先顺序。`tool_selection`、`model` 与 `agent_policy` 支持子 scene 显式覆盖；未显式配置时继承父项或使用 execution profile baseline。scene manifest 不包含 `conversation` 字段；单轮 / 多轮、是否 clear session、是否保留历史由 Service session lifecycle 控制。`prompt` scene 保留为 prompt-style task config，`prompt_mt` 不作为独立 scene 语义存在。

Phase 12 的 runtime assembly 边界由 `ScenePrepare`、`ConfigLoader` 与 `ToolsDiscovery` 三个独立组件组成。`ScenePrepare` 解释 scene manifest、读取 manifest 直接引用的 prompt fragment assets、接收 Service 传入的 typed context slot values，并输出已拼接 `system_messages`、tool selection、model hints、可选 agent policy override、fragment refs、source refs 与 content digest。`ConfigLoader` 原样读取 execution config、执行 overlay 与 typed validation，并输出层中立 typed config view。`ToolsDiscovery` 加载显式 provider callable 或 package entry point，聚合 provider 返回的 `ToolDefinition` 集合，输出业务 `ToolBundle`、source refs、content digest 与 provider report。三者互不替代：`ConfigLoader` 不解释 scene manifest，`ScenePrepare` 不做工具发现，`ToolsDiscovery` 不读取 scene manifest 或配置模型。

Service / composition root 是三者输出进入 Host 的唯一映射方。Service 同时消费 `PreparedSceneInputs`、ConfigLoader 的 typed config view 与 ToolsDiscovery 的 discovered bundle，把它们显式映射为 `open_host` construction-time inputs、per-run request inputs、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`HostToolingOptions` 或其它已冻结 typed input；映射失败必须在调用 Host 前失败。Service / execution environment 负责 provider client 创建、secret 使用 / 脱敏 / 保护、多 Run workflow、artifact、parser、replay、retry 与 stop policy。

运行时 override 合并由 Service / composition root 执行，优先级固定为未来 UI 显式输入 > scene manifest hints > ConfigLoader typed config view > 代码默认值。该优先级只适用于 Host 外部装配阶段，Host 接收的仍然是最终 typed inputs，不解释 override provenance。当前 Host public contract 允许的 per-run override 仅限 `SubmitFollowupRequest` 的 `system_prompt`、`tool_names`、`runner_spec`、`runner_options` 与 `agent_policy`：`system_prompt` 承接 `ScenePrepare` 已装配的 system messages；`tool_names` 只在已发现业务 `ToolBundle` 内选择子集，`None` 表示使用全量业务工具，空集合表示禁用业务工具，非空集合表示显式白名单；`runner_spec`、`runner_options` 与 `agent_policy` 必须由 Service 映射为完整 typed value，不接受 patch dict、profile lookup、extra payload 或 raw config fragment。`SubmitFollowupRequest.user_prompt` 是调用方本次输入，不来自 scene / config；`behavior` 与 `target_run_id` 属于 Service / UI 请求控制，不属于 scene manifest 的稳定职责。

`open_host(options)` 的 construction-time inputs 也由 Service / composition root 从 ConfigLoader、ToolsDiscovery、代码默认值以及部署环境组装，但它们不是当前 per-run override。包括 durable store / artifact roots、SQLite 与 lane 参数、worker factory、ordinary run baseline、`HostToolingOptions`、context budget policy、compactor runner baseline、memory projection policy、memory catch-up batch size 与 truncation manager 开关在内的 Host opener 参数，在 Host handle 打开后不由 scene 或单个 Run 改写。Scene 可以表达 model / tool selection hints 与 typed agent policy override，ConfigLoader 可以表达 execution profile 与部署默认值，最终是否转化为 opener baseline 或 per-run override 由 Service 根据现有 Host typed contract 决定；若发现需要新增 per-run override 字段，必须回到 Host public interface design gate，不能通过 runtime assembly 旁路扩展。

Host 不知道 scene manifest、config 文件或 tool provider，不扫描业务工具，不拼 prompt，不解释 workflow，也不接收 raw `ToolBundle` 作为 per-run request。runtime assembly 可以修正 Host public policy dataclass 或 tool truncate declaration 的 typed shape，但不得改变 Host public command、Host handle method、`open_host(options)` 字段、public request / response dataclass 字段或 `dayu.host` public exports；runtime assembly 结果只能通过现有 `open_host` construction-time inputs 与 per-run typed request inputs 交给 Host。

`utils/smoke_host_public_multiturn.py` 的最终验证职责是模拟真实 Service-like assembly，而不是脚本内手写生产替身。它必须使用 dedicated ordinary scene asset（`smoke_host_public_multiturn`）作为默认 scene，通过 runtime location resolver、ConfigLoader、ToolsDiscovery、ScenePrepare 与 adapter/helper 组装 `open_host(options)` 和 per-run submit input。smoke scene 是普通 scene manifest，不得在 ScenePrepare 或 smoke 中写 special case；它只表达 system prompt fragments、context slots、tool selection、可选 `model.default_model_id`、`model.runner_option_hint_id` 与白名单内 `agent_policy` override。smoke 脚本不得用业务默认值遮住 schema 或 public contract 缺口；如果 config 到 contracts 的映射需要猜测、adapter 过厚或缺 helper，必须输出装配诊断并在调用 Host 前 fail fast。

### 3.1 `dayu.runtime.lane`

`dayu.runtime.lane` 第一版是层中立、cross-process 的 async named semaphore / capacity guard primitive。它用于单机多客户端 / 多进程下对 LLM provider 调用、外部 API 调用、CPU / IO worker 等非真源资源做容量保护。它提供同一机器、同一 runtime lane coordinator 下的跨进程容量计数；跨进程 Host admission、Run / Attempt owner、EventLog ordering、SQLite CAS、fencing token、Attempt takeover 和 positive orphan proof 仍属于 Host durable store / Host 状态机 / recovery phase。

第一版 coordinator 使用独立 runtime SQLite 文件实现，原因是：

- 单机多进程容量计数需要原子 compare-and-claim；普通内存 semaphore 不满足项目目标。
- SQLite 是 Python 3.11 标准库能力，可用短事务表达跨进程 claim / release，不引入业务层依赖。
- 该 SQLite 文件是 `dayu.runtime.lane` 的资源容量协调器，不是 Host durable store；不得复用 Host EventLog / state index 数据库，也不得被 Host recovery 当作 truth。
- `dayu.runtime.filelock` 可作为普通文件互斥 wrapper，但不能提供 capacity claim 的可查询状态、TTL cleanup 和原子计数，因此不作为 lane 第一版 coordinator。

第一版 public API shape：

```text
@dataclass(frozen=True, slots=True)
LaneConfig
  name: str
  capacity: int
  default_timeout_seconds?: float
  claim_ttl_seconds: float
  heartbeat_interval_seconds: float

@dataclass(frozen=True, slots=True)
LaneOwner
  owner_id: str
  pid: int
  process_start_token?: str

@dataclass(frozen=True, slots=True)
SQLiteLaneCoordinatorConfig
  db_path: Path
  create_parent_dirs: bool = true
  busy_timeout_seconds: float
  poll_interval_seconds: float

@dataclass(slots=True)
LaneClaimToken
  name: str
  claim_id: str
  owner: LaneOwner
  expires_at: datetime
  refresh() -> Awaitable[None]
  release() -> Awaitable[None]
  released: bool

@dataclass(frozen=True, slots=True)
LaneAcquired
  token: LaneClaimToken

@dataclass(frozen=True, slots=True)
LaneAcquireCancelled
  reason?: str

@dataclass(frozen=True, slots=True)
LaneAcquireTimedOut
  elapsed_seconds: float

LaneAcquireOutcome = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut

LaneController
  open(configs: Sequence[LaneConfig], *, coordinator: SQLiteLaneCoordinatorConfig, owner?: LaneOwner) -> LaneController
  acquire(name: str, *, token?: CancellationToken, timeout_seconds?: float) -> Awaitable[LaneAcquireOutcome]
  close(reason?: str) -> Awaitable[None]
```

`LaneConfig.name` 必须非空，`capacity` 必须为正整数。`claim_ttl_seconds` 必须大于 `heartbeat_interval_seconds`，且二者都必须为正数。重复 lane name、未知 lane name、非正 capacity、非法 TTL / heartbeat 属于配置错误，必须在 controller construction 或 acquire 前以结构化 runtime error 暴露。Phase 1 不要求全局 registry；调用方显式持有 `LaneController`，避免模块级隐式单例。

Coordinator / store / lock 选择和注入方式：

- `LaneController.open(...)` 必须显式接收 `SQLiteLaneCoordinatorConfig`；调用方传入独立 runtime lane DB 路径，例如 workspace runtime 目录下的 `runtime_lanes.sqlite3`。
- `db_path` 不得默认为 Host durable store 路径，不得从 Host package 读取配置，也不得通过模块级全局 singleton 隐式创建。
- coordinator schema 只允许保存 lane capacity coordination 所需的 rows，例如 lane name、claim id、owner id、pid、process start token、created_at、heartbeat_at、expires_at。不得保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段。
- SQLite transaction 只保护 runtime capacity claim 的原子计数和 release；它不是 Host transaction、不能兜底 Host state machine，也不能被任何层解释为 resource fencing。
- `busy_timeout_seconds` 只限制 runtime coordinator SQLite busy 等待；Host command path SQLite busy policy 属于 Host durable store，不由 runtime lane 决定。

Acquire / release 生命周期：

- `acquire()` 成功时，coordinator 在每个 SQLite transaction 开始前通过 `datetime.now(UTC)` 读取一次真实 UTC `now`，并在同一短事务内复用同一个 bound value 清理同一 lane 中 `expires_at <= now` 的 stale claims、统计 `expires_at > now` 的 active claim，再在 active claim 数量小于 capacity 时插入一条新 claim，返回 `LaneAcquired(token=LaneClaimToken(...))`。
- `claim_id` 必须是不可猜测的随机 id；`owner` 默认由 runtime 根据当前进程生成，也允许上层显式传入稳定 owner id。owner identity 只用于 runtime cleanup / diagnostics，不是 Host owner。
- 只有持有 `LaneClaimToken` 才表示当前 owner 占用了一个 lane 容量。token id 只标识 runtime capacity claim，不得传入 Host EventLog 作为 canonical identity。
- `LaneClaimToken.release()` 必须异步、幂等，并在短事务内按 `(lane_name, claim_id, owner_id)` 删除 claim；重复 release 不得影响其它 owner 的 claim。
- token 持有期间必须定期 heartbeat / refresh，延长 `expires_at`。每次 refresh 在 SQLite transaction 开始前读取一次真实 UTC `now`，并在同一事务内复用同一个 bound value 更新 `heartbeat_at`、`expires_at` 与判断旧 `expires_at > now`。第一版可以由 `LaneController` 为本进程持有的 tokens 启动 heartbeat task，也可以由 token context helper 驱动；无论实现方式，heartbeat failure 必须让 token 进入不可继续使用的 released / lost 状态，并触发调用方可观测错误或取消。
- 调用方必须用 `try/finally` 或 runtime 提供的 async context helper 持有 token，确保工作完成、失败、取消或 shutdown 时释放容量。
- 第一版以 token 模型为必须实现的 public primitive；可额外提供 async context manager helper，但它只能包裹同一 token acquire / release 语义，不能引入第二套生命周期。

Cancellation / shutdown：

- 等待 acquire 必须可取消：外层 `asyncio.Task.cancel()` 必须透传 `asyncio.CancelledError`，不得吞掉取消；如果传入 `CancellationToken` 且 token 在等待期间命中，返回 `LaneAcquireCancelled(reason=...)`，不得创建 claim。
- `timeout_seconds=None` 表示不设置 acquire timeout；`timeout_seconds=0` 表示 non-blocking acquire；正数表示最多等待对应秒数。timeout 命中返回 `LaneAcquireTimedOut`，不得占用容量。
- cancellation 与 timeout 同时命中时 cancellation 优先，返回 `LaneAcquireCancelled`。
- 等待 acquire 的轮询必须通过 SQLite 短事务重试；不得在一个长事务里等待容量释放。
- `LaneController.close(reason=...)` 用于 supervisor shutdown：它停止接受新 acquire，唤醒仍在等待的 acquire 返回 `LaneAcquireCancelled`，并尝试 release 当前 controller 持有且尚未 release 的 tokens。owner task 仍必须在 `finally` / context manager 中 release；close 的 best-effort release 不能替代 owner task cleanup。
- runtime primitive 不追踪 Host Run / Attempt，因此不能根据 Host cancel 自动释放 token。Host dispatch usage 必须在后续 phase 通过 owner task cancellation 和 durable recheck 组合完成。

Stale owner / timeout handling：

- 如果进程崩溃或 owner task 未能 release，claim 最多占用到 `expires_at`；后续 acquire 会在事务内清理 expired claims。
- stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能驱动 Host recovery，不能写 EventLog。
- heartbeat / TTL 不是 lease / fencing。即使某个 expired claim 被清理，也不授权旧 worker takeover，也不证明旧 side effect 已停止。
- lane TTL 的 `created_at`、`heartbeat_at`、`expires_at` 与 stale cleanup 判断使用每个 SQLite transaction 前读取的真实 UTC；monotonic 只用于本进程等待 timeout / deadline 等等待时长计算，不参与跨进程过期判断。跨进程 clock skew 只能影响 runtime capacity availability，不能影响 Host truth / EventLog / Attempt lifecycle。

Fairness / ordering / non-goals：

- 第一版不承诺 FIFO、公平性、优先级、权重、队列可观测性或跨 lane ordering；测试不得断言 acquire 顺序。
- 第一版不实现分布式跨机器 rate limit、provider quota accounting、resource cost weighting、fencing token、Attempt takeover、Host recovery proof 或 capacity ownership diagnostics beyond runtime claims。
- lane token 不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner、不是 dispatch record 状态。
- acquire 成功只表示当前 owner 在 runtime coordinator 中拿到资源容量；执行任何副作用前，Host 后续 dispatch phase 仍必须在短事务内 recheck durable precondition。

Multi-process tests:

- 两个及以上独立 Python 进程使用同一个 lane DB 和同一 lane name 时，总并发 successful claims 不得超过 capacity。
- 一个进程持有 claim 时，另一个进程 `timeout_seconds=0` acquire 同 lane 且 capacity 已满必须返回 timed out。
- 持有 claim 的进程正常 release 后，另一个进程可以 acquire。
- 持有 claim 的进程崩溃或不 heartbeat 后，另一个进程在 TTL 过期并清理 stale claim 后可以 acquire。
- 多进程竞争不能依赖 acquire ordering；测试只断言 capacity invariant 和 eventual acquire / timeout。

Import boundary：`dayu.runtime.lane` 只能依赖标准库（包括 `sqlite3`）、`dayu.contracts.cancellation.CancellationToken` 和同包层中立 helper；不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，不得持有财报、Host、Engine 或具体 provider 语义。

Phase 1 只实现该 runtime primitive 及其单元测试，不实现 Host dispatch 对 lane 的使用，不实现 LLM provider policy，不修改 Host durable state machine。

### 3.2 `dayu.runtime.filelock`

`dayu.runtime.filelock` 第一版是对第三方 `filelock.FileLock` 的同步 wrapper，用于普通文件访问互斥，例如单进程 / 多进程对 JSONL、临时 artifact 或其它普通文件的短临界区保护。它不能用于 SQLite transaction、EventLog ordering、Host durable truth、Run / Attempt owner、lease / fencing 或 recovery 判断。

第一版 public API shape：

```text
@dataclass(frozen=True, slots=True)
RuntimeFileLockOptions
  lock_path: Path
  timeout_seconds?: float
  create_parent_dirs: bool = true

@dataclass(slots=True)
RuntimeFileLockToken
  lock_path: Path
  release() -> None

RuntimeFileLock
  acquire(timeout_seconds?: float) -> RuntimeFileLockToken
  __enter__() -> RuntimeFileLockToken
  __exit__(exc_type, exc, tb) -> None

file_lock(lock_path: str | Path, *, timeout_seconds?: float, create_parent_dirs: bool = true) -> RuntimeFileLock
```

Sync / async 边界：

- Phase 1 只提供同步 wrapper。它不提供 async file lock context manager，也不在线程池中替调用方隐藏阻塞 acquire。
- async 调用方如需使用 file lock，必须在自己的边界显式决定是否放入 executor，或保证临界区足够短且不会阻塞事件循环关键路径。

Path handling / directory creation：

- `lock_path` 是显式 lock file 路径，不从业务文件路径隐式派生，避免调用方误判保护范围。
- wrapper 必须把 `str | Path` 归一化为 `Path`，并在 `create_parent_dirs=True` 时创建 lock file 的 parent directory。
- `create_parent_dirs=False` 且 parent directory 不存在时，必须返回 / 抛出结构化 runtime file lock error，不得静默退化。

Timeout / error semantics：

- `timeout_seconds=None` 表示等待第三方 `FileLock` 默认的无限等待语义；`timeout_seconds=0` 表示 non-blocking acquire；正数表示最多等待对应秒数。
- 第三方 `filelock.Timeout` 必须被包装为 runtime 自己的 timeout error，避免上层散落直接依赖第三方异常类型。
- lock acquire 失败、路径非法、parent directory 创建失败等必须归一为 runtime file lock error；不得吞异常后让调用方误以为已进入临界区。

Stale lock / reentrancy / release：

- 第一版不实现 stale lock 探测、锁文件删除、owner pid 解析、跨进程 owner takeover 或强制 break lock。发现疑似 stale lock 时只能 timeout / error，由调用方或运维路径处理。
- lock marker 文件只属于第三方文件锁实现细节和普通文件互斥可见痕迹，不是 Host 治理真源。Host 不得用 marker 文件存在性判断 Run / Attempt owner、worker liveness、lease / fencing、EventLog ordering、recovery 或 takeover 条件；这些事实只能来自 Host durable store、EventLog、状态索引和事务。
- wrapper 不承诺 reentrant lock 语义是设计意图，不是待补能力。调用方不得依赖同一线程 / 同一进程 / 同一 `RuntimeFileLock` 实例重复 acquire 的成功、失败、计数或 token 复用行为；测试不应断言第三方库的 reentrant 细节。
- `RuntimeFileLockToken` 只暴露 `lock_path` 与 `release()`，不暴露 release 状态；它只是把 release 调用路由到本次获取的第三方 lock，不是 Host truth、lease 证明或 wrapper lifecycle truth。
- `RuntimeFileLockToken.release()` 在第三方 release 成功后必须幂等；重复 release 不得抛出误导性错误，也不得释放其它 token。第三方 release 失败时不得把 token 标记为成功 release，后续调用必须仍能再次尝试底层 release。
- context manager 退出必须 release；异常路径也必须 release。

第三方依赖边界：

- 只有 `dayu.runtime.filelock` 可以直接 import `from filelock import FileLock` 及其 timeout 类型。业务层、Host、Service、Fins、工具模块不得各自直接封装或散落 import 第三方 `filelock`。
- 该 wrapper 是纯 infra dependency adapter，不表达 Host durable truth，也不替代数据库事务、CAS、EventLog sequence 或 projection checkpoint。

## 4. 核心对象

Host 治理核心只有四个一等对象：

```text
Session
Run
Attempt
EventLog
```

其它能力，例如 durable queue、wait record、memory snapshot、tool trace、audit、usage、outbox、projection checkpoint，是表、投影或内部机制，不提升为同级治理真源。

对象边界：

- `Session`：一条可持续会话上下文，包含多个 Run。
- `Run`：用户可见的一次 Agent 目标 / 问题 / follow-up，属于一个 Session。
- `Attempt`：Host 为完成某个 Run 派发给本地或远程 EngineWorker 的一次执行，属于一个 Run。
- `EventLog`：append-only event ledger；其中 `canonical_fact` 子集是恢复、memory、audit、outbox 等治理真源，其它 event class 只服务展示、诊断或 projection 输入。

关键不变量：

- Run 是用户可见生命周期；Attempt 是执行生命周期。
- resume、steer、recovery 等同一 Run 内继续执行路径都不复用旧 Attempt；它们在同一个 Run 下创建新 Attempt。
- `retry(run)` / `replay(run)` 不重开原终态 Run；它们创建关联的新 Run，新 Run 再创建自己的 Attempt。
- 每个 Attempt 必须有唯一 `attempt_id` 和 `execution_id`。
- `execution_id` 用于拒绝迟到 Attempt 事件，不是 lease，也不表示远端拥有治理状态。
- 远端执行环境只回传 Attempt 事件，不关闭 Attempt，不更新 Run，不 append EventLog。

### 4.1 Stream 术语约束

文档与实现不得把不同层的流式概念混称为 “stream”。固定术语如下：

- `EngineEvent stream`：EngineWorker 执行 Engine 时产出的事件流，是 Host ingest 的输入来源之一，不是 Host 事实真源。
- `Host event stream`：Host 对 UI / CLI / Web / GUI 暴露的订阅与补读事件流，只能由 EventLog `event_sequence` cursor 派生，不触发执行。
- `preview event`：面向 UI 流式体验的临时事件，可以进入 Host event stream，但不能作为恢复、投递、RunResult、memory 或 audit 的唯一事实来源。
- `preview delta`：模型 content / reasoning / tool-call 的增量片段，只服务展示体验，默认不是 canonical fact。
- `stream fanout`：把已提交 Host events 分发给多个客户端的 projection / sink。慢客户端必须通过 `event_sequence` cursor 补读，不能反压 EventLog append。

## 5. Session 生命周期

Session 状态集合：

```text
OPEN
CLOSED
```

语义：

- `OPEN`：允许创建新 Run、queue follow-up、steer active Run、读取 session timeline。
- `CLOSED`：只读；拒绝新 Run、follow-up、steer。已有 Run 不因 close 被删除或改写。

`close_session` 是归档 / 关闭语义，不删除 EventLog，不清空 memory，不重写历史。

`close_session` 只关闭 Session 的新输入入口，不取消、不终止、不删除已有 Run。`CLOSED` Session 的语义：

- `submit_followup(queue)`、`submit_followup(steer)` 返回 `invalid_state`；内部新 Run admission primitive 同样不得绕过 Session closed 前置条件。
- `ensure_session(scope, slot_key)` 可以返回当前 slot Session，snapshot 标记为 `CLOSED`。
- `create_session` 仍允许创建新 Session；UI / Service 若要继续聊天，应显式调用 `create_session(bind_slot=true, scope, slot_key)` 创建并重绑定新 Session。
- `get_session`、`get_run` 仍允许读取；Host 内部 diagnostic EventLog 补读仍可用于排查。
- `cancel_run` 仍允许取消已有 Run。
- `resolve_wait` 仍允许让已有 `WAITING` Run 继续收口。
- `retry_run` / `replay_run` 默认拒绝在 closed Session 内创建关联新 Run，除非显式 policy 把新 Run 创建到其它 Session。

已有 active Run 继续按 Host 状态机治理到终态；close 前已 durable accepted 的非终态 Run 继续按原状态机完成。`QUEUED` Run 可在 active slot 释放后 promotion；`WAITING` Run 可在 `resolve_wait` 后 resume；`RECOVERING` Run 可继续 recovery dispatch；`RUNNING` / `CANCELLING` Run 继续收口到 terminal。Host opener close 可停止当前 handle 持有的本地执行环境，但不等于用户 cancel；若调用方希望表达用户停止意图，必须显式调用 `cancel_run` 或 `cancel_session_runs`。

`clear_session` 不进入第一版普通公共接口。需要清理、遗忘或重置时，必须分别设计 close / new session / memory forget / purge 等有明确审计语义的接口。

`purge_session` 是第一版 destructive purge API，用于彻底清理一个已经结束且不再需要恢复的 Session 的 Host 本地数据。它不是 close、cancel、archive、memory forget 或 UI hide。

`purge_session` 前置条件：

- Session 必须已经 `CLOSED`。
- Session 不得有 active Run。
- Session 不得有 `QUEUED` Run。
- Session 不得有 `WAITING` / `RECOVERING` / `CANCELLING` Run。
- Session 下所有 Run 必须已经进入终态。

不满足前置条件时，Host 必须返回 `invalid_state`，不得部分删除。

`purge_session` 删除范围包括该 Session 独占的 Host 本地数据：Session / slot binding、Run、Attempt、该 Session 的 EventLog rows、payload descriptors / local payloads、memory snapshot、projection rows、outbox items、tool trace hot data。共享 cold artifact 只有在没有其它 durable ref 引用时才允许被清理。

`purge_session` 是第一版对 EventLog append-only retention 的唯一 destructive exception。它只能在严格前置条件成立后删除该 Session 的可恢复事实，并必须保留最小 purge tombstone / audit record。tombstone 至少包含 `session_id`、purge `client_request_id`、semantic request digest、actor / source / request refs、reason、purge timestamp、precondition digest、deleted counts / digest 和 tombstone id。purge tombstone 不是可恢复 Session fact，不参与 resume、retry、replay、memory 或 RunInputBuilder；它不能位于被 purge 的 Session EventLog 中，必须存入 Host durable store 中可按 `session_id` 查询的 tombstone table 或等价持久区域。

`purge_session` 不删除已经写入的 append-only audit JSONL 记录。purge audit JSONL 记录的是 destructive 操作流水，而不是 purge 完成真源。purge 应至少能表达 `purge_started` 与 `purge_completed` 两类 audit line：`purge_started` 只表示上层发起并通过前置检查、Host 准备执行 destructive purge；`purge_completed` 只能在 SQLite purge tombstone 已提交后写入，并必须引用 tombstone id / digest。若 purge 执行失败，可以写入 `purge_failed` audit line 记录失败阶段和原因。既有 audit JSONL 行可以保留对已删除 EventLog rows 的 refs，audit 查询 / analyze 工具必须以 SQLite tombstone 判断 purge 是否完成：只有 `purge_started` 但没有可验证 tombstone / completed 记录时，只能报告 purge attempt / incomplete，不得报告 purge 已完成。

purge 后该 Session 不再支持 `get_session`、`get_run`、`retry_run`、`replay_run` 或 final answer 恢复；Host 内部 EventLog 补读也不得再恢复该 Session 的可恢复事实。读取接口应返回 `not_found` / `gone` 或 tombstone snapshot；具体错误形状属于 Public API phase。

P10.5 ordinary local multi-turn public contract 只要求 `close_session(...)` public contract 可用，不要求 `purge_session(...)` destructive cleanup 可用。P10.5 必须验证 `close_session(...)` 只关闭 Session 新输入入口，不取消、不终止、不删除已有 Run；关闭后 `get_session(...)`、`get_run(...)` 与 `watch_session_events(...)` 仍可读取 / 观察既有事实，新的 `submit_followup(...)` 必须返回明确 invalid-state / typed error。P10.5 还必须验证 `close_session(...)`、Host opener close 与 cancel 的边界：`close_session(...)` 不停止本地 runtime，Host opener close 不把 Session 改成 `CLOSED`，二者都不写用户 cancel facts；只有 `cancel_run(...)` / `cancel_session_runs(...)` 表达用户停止 Run 的治理意图。`purge_session(...)` 可以保留 public envelope、closed-handle guard、unsupported / deferred 或 precondition error 边界，但 purge tombstone、删除矩阵、payload / memory / projection / outbox / tool trace 清理、audit 查询与 retention hardening 继续归 Phase 15。

Recommended Service policy：当上层产品语义是“结束会话并停止当前工作”时，Service 应显式调用 `cancel_session_runs(...)`，等待 cancel 结果通过 `watch_session_events(...)` 或 `get_run(...)` 可见后，再调用 `close_session(...)` 关闭新输入入口。Host 不在 `close_session(...)` 内自动 cancel，因为 close / cancel 是不同治理事实，必须在 EventLog 中保持可解释边界。

## 6. Session Slot

Session slot 用于让外部入口回到同一个当前 Session。取得当前会话与显式新建会话是两个不同意图，Host 公共接口必须拆成 `ensure_session` 与 `create_session`。

```text
EnsureSessionRequest:
  scope
  slot_key
  metadata

CreateSessionRequest:
  client_request_id
  bind_slot?
  scope?
  slot_key?
  metadata
```

不变量：

- `(scope, slot_key)` 唯一映射到一个当前 Session。
- `ensure_session(scope, slot_key)` 返回该 slot 当前 Session；如果 slot 尚不存在，Host 原子创建并绑定一个新 Session。
- `ensure_session(scope, slot_key)` 的幂等键是 `(scope, slot_key)`；不同 `client_request_id` 不应改变复用结果，因此该接口不需要 `client_request_id`。
- `ensure_session` 的并发安全必须由 durable store 保证：slot 表对 `(scope, slot_key)` 有唯一约束，Session 创建与 slot 绑定必须在同一事务内完成；并发重复调用必须返回同一个绑定 Session，不得留下孤儿 Session。
- `create_session(client_request_id, bind_slot=false)` 明确创建一个新 Session；同一 `client_request_id` 重试必须返回同一个新 Session，不能重复创建。
- `create_session(..., bind_slot=true, scope, slot_key)` 创建新 Session 后，把 `(scope, slot_key)` 原子重绑定到新 Session；旧 Session 不删除，不改写 EventLog。
- 对同一 `(scope, slot_key)` 使用不同 `client_request_id` 调用 `create_session(..., bind_slot=true)` 表示不同的新建动作，允许创建更新的 Session 并重绑定 slot。
- `scope` 是入口或身份命名空间；`slot_key` 是该命名空间下的会话槽位。
- Host 不把 session slot 当权限模型。认证、授权、外部身份解析属于上层。

示例：

- WeChat 同一稳定身份可调用 `ensure_session(scope="wechat", slot_key=<stable_user_key>)`，重复调用拿到同一个 Session。
- CLI `--label` 可作为 `slot_key`；同一 label 默认调用 `ensure_session` 复用同一 Session。
- UI “新建 session” 调用 `create_session(client_request_id=<click_id>, bind_slot=true, scope, slot_key)`，创建新 Session 并重绑定该 slot。

## 7. Run 生命周期

Run 状态集合：

```text
ACCEPTED
QUEUED
RUNNING
WAITING
CANCELLING
RECOVERING
SUCCEEDED
FAILED
CANCELLED
LOST
```

Run 终态：

```text
SUCCEEDED
FAILED
CANCELLED
LOST
```

状态语义：

- `ACCEPTED`：Run 已被 Host durable accepted，且当前 Session 没有更早的 active / start-blocking Run；它尚未创建 Attempt，等待 scheduler / pre-start governance 将其推进到 `RUNNING` 或 terminal failure。
- `QUEUED`：Run 已被 Host durable accepted，但尚未创建 active Attempt。
- `RUNNING`：Run 已占用 Session active slot，并已有 active Attempt lifecycle；active Attempt 可以处于 `STARTING` 或 `RUNNING`。
- `WAITING`：当前 Attempt 已因外部等待条件收口为 `SUSPENDED`，Run 等待 Host 后续 resume。
- `CANCELLING`：Host 已接受取消请求，正在等待 active Attempt 收口或超时升级。
- `RECOVERING`：Host 已确认旧 Attempt 丢失，但用户请求和必要 canonical facts 仍可恢复；Host 正在或等待创建新 Attempt 继续同一 Run。
- `SUCCEEDED`：Run 产出已确认 final answer。
- `FAILED`：Run 已确认不可恢复执行失败。
- `CANCELLED`：Run 已按用户或上层取消请求收口。
- `LOST`：Host 无法恢复该 Run 的用户请求或必要事实，或 policy 明确放弃继续。

`LOST` 不是 `FAILED`。`FAILED` 表示已确认失败；`LOST` 表示治理无法恢复或无法确认，不能伪装成普通失败。

允许且预期存在 `Run.status=RUNNING` 与 `Attempt.status=STARTING` 的组合。Host crash 导致旧 Attempt 丢失时，若用户输入和必要 canonical facts 已持久化，Run 优先进入 `RECOVERING`，而不是直接终态 `LOST`。

## 8. Attempt 生命周期

Attempt 状态集合：

```text
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

Attempt 终态：

```text
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

状态语义：

- `STARTING`：Host 已创建 Attempt，并准备派发到 LocalProxy / RemoteProxy。
- `RUNNING`：EngineWorker 已开始执行，Host 正在接收事件。
- `SUCCEEDED`：Attempt 产出 final answer，Run 可进入 `SUCCEEDED`。
- `FAILED`：Attempt 以确认失败收口，Run 可进入 `FAILED`，或由 Host policy 创建 retry Attempt。
- `CANCELLED`：Attempt 响应 Run cancel 请求收口。
- `SUSPENDED`：Attempt 因工具等待或外部条件挂起，Run 进入 `WAITING`。
- `STEERED`：Attempt 被 steer 打断，Run 保持 active，并由 Host 创建新 Attempt。
- `LOST`：Attempt 的执行结果无法确认。

映射规则：

```text
Attempt SUSPENDED -> Run WAITING
wait resolved -> new Attempt -> Run RUNNING
```

```text
Run RUNNING -> CANCELLING
Attempt RUNNING -> CANCELLED / LOST
Run -> CANCELLED / RECOVERING / LOST
```

旧 Attempt 永不 resume。任何继续执行都必须创建新 Attempt 和新 `execution_id`。

## 9. Admission 与多进程并发

同一个 Session 同时最多一个 active Run。

多客户端可以同时打开和写入同一个 Session。Host 不维护 client ownership truth，不发放 session write lock，不要求 attach token，也不把某个 watcher 视为 Session owner。多个客户端同时调用 `submit_followup(queue)` 时，写入顺序、幂等和冲突处理只由 Host durable admission transaction、`(session_id, client_request_id)` 幂等、Run 状态 precondition、全局 `event_sequence` 与 scheduler governance 决定。不同 `client_request_id` 的 prompt 按 durable accepted order 进入 `ACCEPTED` / `QUEUED` 和后续 FIFO promotion；相同 `(session_id, client_request_id)` 重放必须返回同一 accepted Run，不重复创建。客户端身份、权限、channel delivery 和本地 UI 去重属于 Service / UI 边界，不进入 Host Session ownership 语义。

active Run 状态：

```text
RUNNING
WAITING
CANCELLING
RECOVERING
```

`QUEUED` Run 是 durable accepted run，不占 active slot，但必须持久化。queued run 不是内存队列项；它必须有稳定 `run_id`、`session_id`、`client_request_id`、输入 canonical fact 和 `Run.status=QUEUED`。

新输入 admission：

- `queue`：`submit_followup(queue)` 在同一个 Host admission transaction 内检查 active / start-blocking Run；有 active / start-blocking Run 时输入进入 durable queue，成为后续 Run；无 active / start-blocking Run 时创建 `ACCEPTED` Run，后续由 scheduler / pre-start governance 启动。
- `reject`：当前 Session 有 active Run 时，拒绝创建新 Run，并返回 active run conflict。
- `attach_active`：当前 Session 有 active Run 时，返回当前 active `RunSnapshot`，不触发新执行，不新增 canonical EventLog fact。第一版只通过幂等记录、diagnostic refs 或后续 audit/read-model projection 解释 attach request；如果后续需要把 attach 作为可查询业务事实，必须先补充新的 canonical event shape，不能由 public facade 临时发明事件。
- `steer`：必须命中 active Run precondition；它在同一 Run 内切换 Attempt，不创建新 Run。

幂等不变量：

- `ensure_session` 由 `(scope, slot_key)` 幂等映射到当前 Session。
- `create_session` 由 `client_request_id` 幂等映射到一次明确的新建 Session 动作；绑定 slot 时，同一 `client_request_id` 重试不能重复创建或重复重绑定。
- 内部新 Run admission primitive 由 `(session_id, client_request_id)` 幂等映射到同一个 Run；Service-facing 普通 prompt 入口统一为 `submit_followup(queue)`。
- queued follow-up / queued run 也必须按 `(session_id, client_request_id)` 幂等。
- `cancel_run` 由 `(run_id, client_request_id)` 幂等映射到同一个 cancel 操作。
- `cancel_session_runs` 由 `(session_id, client_request_id)` 幂等映射到同一个 session-scope cancel 操作。
- `retry_run` / `replay_run` 由 `(source_run_id, client_request_id)` 幂等映射到同一个关联新 Run。
- `resolve_wait` 由 `(wait_id, idempotency_key)` 幂等映射到同一个 wait resolution。

多进程持久化方向：

- 第一版使用 SQLite durable store 表达单机多进程真源。
- 多进程一致性依赖 SQLite 事务、唯一约束、CAS-style state transition、`event_id` / `event_sequence` 去重与排序。
- SQLite 使用 WAL、明确 busy timeout 和显式重试策略；具体参数属于 Host storage policy。
- 不引入重 lease / fencing 系统。
- 不做旧 Attempt takeover；不做远端 worker 自治恢复；新执行必须创建新 Attempt 和新 `execution_id`。
- `dayu.runtime.lane` 可作为层中立 named semaphore，被 Host 或其它层用于非真源资源的容量控制；它不能替代 Session active Run admission、SQLite 事务或 CAS 状态迁移。
- `dayu.runtime.filelock` 是对 `from filelock import FileLock` 的统一封装，只用于多进程访问普通文件时的互斥保护；不得用 file lock 表达 Host durable truth、EventLog ordering 或 Run / Attempt owner。

durable queue promotion：

- 同一 Session 的 queued Run 按 accepted `event_sequence` FIFO promotion。
- promotion 只在该 Session 没有 active Run 时发生。
- promotion 与 `RUN_STARTED`、`ATTEMPT_STARTED`、Attempt row 创建、dispatch record 创建必须在同一事务中完成。
- 多进程竞争 promotion 时，只有一个事务能通过 CAS 抢占该 Session 的 active slot；其它进程必须重新读取状态。
- active Run 进入终态、`RECOVERING` 成功恢复、或 Host 启动 recovery scan 后，都必须触发一次同 Session queue promotion check。
- promotion 与 `cancel_run` 竞争时使用 CAS first-committer-wins。promotion 先提交时，Run 已变 `RUNNING`，后到 cancel 必须按 active cancel 路径处理；cancel 先提交时，Run 已变 `CANCELLED`，后到 promotion 必须 CAS 失败并放弃创建 Attempt。
- queued Run 被 cancel 时直接进入 `CANCELLED`，不得为了取消而创建 Attempt。

用户输入持久化顺序必须是：

```text
append USER_INPUT_ACCEPTED
append RUN_ACCEPTED / RUN_STARTED or RUN_QUEUED
create Attempt when admitted
commit
dispatch EngineWorker
```

Host 不允许先 dispatch EngineWorker 再补写用户输入事实。

### 9.1 状态迁移契约

状态迁移必须通过明确操作触发。不得新增隐式后台迁移来绕过 admission、EventLog 或 Attempt 语义。

Phase 3 owned transition subset：

Phase 3 只实现不需要 Engine dispatch、ToolRuntime、wait record、steer、retry / replay、context compaction 或 recovery 的状态机闭环：

- Session lifecycle：创建 Session、按 slot 幂等确保 Session、关闭 Session；关闭后的 Session 不接受新输入，但不把既有 queued Run 作为内存对象丢弃。
- start / follow-up admission：接受初始输入或 follow-up queue 输入，追加用户输入与 Run 接受事实；无 active / start-blocking Run 时创建 `ACCEPTED` Run，有 active / start-blocking Run 且 policy 为 queue 时持久化 `QUEUED` Run。
- scheduler start / queue promotion：同一 Session 无 active Run 时，优先推进 `ACCEPTED` Run，或按 queued Run 的 accepted `event_sequence` FIFO 推进一个 Run 到 `RUNNING`，创建 Attempt `STARTING` 与 dispatch record `pending`。
- cancel accepted / queued：`ACCEPTED` / `QUEUED -> CANCELLED`，不创建 Attempt。
- cancel pre-dispatch starting：`Run RUNNING + Attempt STARTING + dispatch record pending -> Run CANCELLED + Attempt CANCELLED + dispatch record cancelled`；该路径不通知 WorkerProxy，不启动 Engine。
- internal terminal closeout helper：仅作为 Phase 3 状态机测试闭环和后续 EngineEvent ingest 复用的内部 transition helper，用于追加 concrete terminal facts、关闭当前 Attempt / Run、释放 active slot；它不实现 EngineEvent ingest。
- terminal / cancel 成功释放 active slot 后，必须触发同 Session scheduler start / promotion check。promotion check 必须重新进入短事务，并通过 CAS 判定是否仍可推进 accepted / queued Run。

Engine final answer / failure ingest、Tool awaiting、`resolve_wait`、steer、retry / replay、context compaction、recovery scan / dispatch 是全局状态迁移矩阵中的 future-owner references，除非后续 phase plan 明确拥有，不属于 Phase 3 实施范围。

| 操作 / 来源 | 前置状态 | 目标状态 | 必须追加的 canonical facts | Attempt 动作 |
| --- | --- | --- | --- | --- |
| 内部新 Run admission primitive 且无 active / start-blocking Run | Session `OPEN` | Run `ACCEPTED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED` | 不创建 Attempt；commit 后 wake scheduler |
| 内部新 Run admission primitive 且有 active / start-blocking Run，policy=`queue` | Session `OPEN` | Run `QUEUED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` | 不创建 Attempt；Service-facing prompt 入口不暴露该分支，使用 `submit_followup(queue)` |
| `submit_followup(queue)` 且有 active / start-blocking Run | Session `OPEN` | 新 Run `QUEUED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` | 不创建 Attempt |
| `submit_followup(queue)` 且无 active / start-blocking Run | Session `OPEN` | 新 Run `ACCEPTED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED` | 不创建 Attempt；commit 后 wake scheduler |
| scheduler starts accepted / queued Run | Run `ACCEPTED` 或 `QUEUED` 且 Session 无 active Run | Run `RUNNING` / Attempt `STARTING` | `RUN_STARTED(start_reason=initial 或 queue_promotion)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |
| Engine final answer | Run `RUNNING` / Attempt `RUNNING` | Run `SUCCEEDED` / Attempt `SUCCEEDED` | `RUN_SUCCEEDED`、`ATTEMPT_SUCCEEDED` | 关闭当前 Attempt |
| Engine failure | Run `RUNNING` / Attempt `RUNNING` | Run `FAILED` / Attempt `FAILED`，或按 policy 进入 retry | `RUN_FAILED`、`ATTEMPT_FAILED` | 关闭当前 Attempt |
| context compaction proactive | Run accepted before Attempt creation / dispatch | Run `RUNNING` / Attempt `STARTING` after compact | `CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)`、`CONTEXT_COMPACTED`，随后 `RUN_STARTED`、`ATTEMPT_STARTED` | pre-dispatch input governance；不进入 `RECOVERING` |
| context compaction reactive | Run `RUNNING` / Attempt `RUNNING` | Run `RECOVERING`，随后新 Attempt `STARTING` | `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`、current Attempt terminal by policy、`RUN_RECOVERING`、`CONTEXT_COMPACTED`、`RUN_STARTED(start_reason=recovery)`、`ATTEMPT_STARTED` | 关闭当前 Attempt；compact 后创建新 Attempt |
| Tool awaiting accepted | Run `RUNNING` / Attempt `RUNNING` | Run `WAITING` / Attempt `SUSPENDED` | `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` | ToolRuntime Host accept transaction 关闭当前 Attempt，持久化 wait record |
| `resolve_wait` | Run `WAITING` | Run `RUNNING` | `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED(start_reason=resume)`、`ATTEMPT_STARTED` | 创建新 Attempt 并 dispatch |
| `submit_followup(steer)` on running | target Run 是当前 active Run，且状态为 `RUNNING` | 同一 Run `RUNNING` / new Attempt `STARTING` | `STEER_REQUESTED`、`ATTEMPT_STEERED`、`RUN_STARTED(start_reason=steer)`、`ATTEMPT_STARTED` | 运行中 Attempt 收口为 `STEERED`；创建新 Attempt；commit 后 dispatch |
| `submit_followup(steer)` on waiting | target Run 是当前 active Run，且状态为 `WAITING` | 同一 Run `RUNNING` / new Attempt `STARTING` | `STEER_REQUESTED`、wait record cancelled with reason `steered`、`RUN_STARTED(start_reason=steer)`、`ATTEMPT_STARTED` | 旧 Attempt 保持 `SUSPENDED`；创建新 Attempt；commit 后 dispatch |
| `cancel_run` on accepted / queued | Run `ACCEPTED` 或 `QUEUED` | Run `CANCELLED` | `CANCEL_REQUESTED`、`RUN_CANCELLED` | 无 |
| `cancel_run` on waiting | Run `WAITING` | Run `CANCELLED` | `CANCEL_REQUESTED`、wait record cancelled fact、`RUN_CANCELLED` | 旧 Attempt 保持 `SUSPENDED`；不传播 cancel |
| `cancel_run` on recovering before dispatch | Run `RECOVERING` 且无新 Attempt dispatch committed | Run `CANCELLED` | `CANCEL_REQUESTED`、`RUN_CANCELLED` | 不创建新 Attempt；不进入 `CANCELLING` |
| `cancel_run` on pre-worker starting | Run `RUNNING` / Attempt `STARTING` 且 dispatch record `pending` / `waiting_for_lane` / pre-accept `dispatching` | Run `CANCELLED` / Attempt `CANCELLED` | `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED` | 标记 dispatch record cancelled；cancel lane wait 或 wake scheduler release held lane；不通知 WorkerProxy |
| `cancel_run` on active running | Run `RUNNING` / `CANCELLING` 且 Attempt `RUNNING` | Run `CANCELLING`，后续 `CANCELLED` / `WAITING` / `LOST` | `CANCEL_REQUESTED`、`RUN_CANCELLING`，后续 terminal fact | commit 后向当前 Attempt / WorkerProxy 传播 cancel |
| `retry(run)` | Run `FAILED` 或 recoverable failure | 关联的新 Run `ACCEPTED` 或 `QUEUED` | `RETRY_REQUESTED`、新 Run 的 `RUN_ACCEPTED`，按 admission 可追加 `RUN_QUEUED` | 原 Run 终态不改；新 Run 由 scheduler 创建自己的 Attempt |
| `replay(run)` | Run `SUCCEEDED`，且 final answer 格式 / schema / 结构需修复 | 关联的新 Run `ACCEPTED` 或 `QUEUED` | `REPLAY_REQUESTED`、新 Run 的 `RUN_ACCEPTED`，按 admission 可追加 `RUN_QUEUED` | 原 Run 终态不改；新 Run 默认复用已接受工具事实，并由 scheduler 创建 Attempt |
| recovery scan | Run `RUNNING` / `CANCELLING` 且 active Attempt 不可确认 | Run `RECOVERING` 或 `LOST` | `ATTEMPT_LOST`、`RUN_RECOVERING` 或 `RUN_LOST` | 不 takeover |
| recovery dispatch | Run `RECOVERING` 且可重建 messages | Run `RUNNING` / Attempt `STARTING` | `RUN_STARTED(start_reason=recovery)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |

`RUN_STARTED` 表示 Run 进入 active Attempt lifecycle。它必须携带 `start_reason`，第一版枚举为 `initial`、`queue_promotion`、`resume`、`steer`、`recovery`。`start_reason=recovery` 覆盖 crash recovery 和 reactive context compaction recovery；具体原因通过关联的 `ATTEMPT_LOST`、`CONTEXT_COMPACTION_REQUESTED` 或 policy refs 区分。不得用新增的 `RUN_RESUMED` / `RUN_RECOVERED` event 表达同一治理事实。

`RECOVERING` 的退出必须收敛：

- `RECOVERING -> RUNNING`：Host 成功基于 canonical facts 创建新 Attempt，记录 dispatch intent，并让 Attempt 进入 `STARTING`。
- `RECOVERING -> CANCELLED`：用户在恢复期间取消，且没有新 Attempt 已提交 terminal。
- `RECOVERING -> FAILED`：可恢复路径中的新 Attempt 已确认不可恢复失败，或恢复动作本身确认失败且 policy 选择失败收口。
- `RECOVERING -> LOST`：无法重建 messages、必要 payload / anchor 缺失、重复恢复超过 policy 上限，或 policy 明确放弃恢复。

recovery、retry、replay 和 context compaction retry 都必须有 Host policy 上限。默认次数与退避参数属于 Host policy；架构不允许无限重试或无限恢复占用 Session active slot。

Attempt startup 边界：

- `ATTEMPT_STARTED` 表示 Host 已在 durable store 中创建 `STARTING` Attempt，并记录 dispatch intent / dispatch record。
- worker 明确接受 dispatch 后，Host append `ATTEMPT_RUNNING`，Attempt 才进入 `RUNNING`。
- dispatch rejected、startup timeout、dispatch failure、cancel during `STARTING` 都必须关闭 Attempt，并追加明确 Attempt terminal fact。Run 随 Host policy 进入 `FAILED`、`RECOVERING` 或 `LOST`；实现不得把“Host 准备派发”和“worker 已开始执行”混为同一状态。
- `Run RUNNING` 表达 Host 治理生命周期；Attempt `RUNNING` 表达执行环境生命周期。`Run RUNNING + Attempt STARTING` 是合法组合，表示该用户目标已进入 Host 治理执行态，但执行环境尚未确认接住。

标准启动路径：

```text
initial prompt admitted through submit_followup(queue) or internal admission primitive
  -> append USER_INPUT_ACCEPTED
  -> append RUN_ACCEPTED
  -> Run.status = ACCEPTED
  -> commit
  -> after-commit scheduler wakeup
  -> scheduler pre-start governance
  -> append RUN_STARTED(start_reason=initial)
  -> create Attempt(status=STARTING)
  -> append ATTEMPT_STARTED
  -> Run.status = RUNNING
  -> commit
  -> WorkerProxy dispatch
  -> worker accepted
  -> append ATTEMPT_RUNNING
  -> Attempt.status = RUNNING
```

cancel / resolve / promotion 竞态规则：

- `cancel_run` 命中 `WAITING` Run 时，Host 在同一事务内 append `CANCEL_REQUESTED`，标记 active wait record cancelled，append `RUN_CANCELLED`，释放 Session active slot；旧 Attempt 保持 `SUSPENDED`，不重写历史。
- cancel / suspend 竞态由 Host ingest 事务提交顺序决定。terminal fact 已提交时 terminal 胜过后续 cancel；suspend / awaiting 已提交时，后续 cancel 走 `WAITING -> CANCELLED`；cancel 已提交时，后续 suspend / awaiting candidate 不得把 Run 推入 `WAITING`。
- cancel-first 场景下，迟到 `TOOL_AWAITING` / `run_suspended` 只能进入 diagnostic / tool trace 或被拒绝为 canonical fact；Host 不创建 active wait record，并将 Attempt / Run 按取消路径收口到 `CANCELLED`。
- `cancel_run` 与 `resolve_wait` 并发时，先提交事务者赢。cancel 先到则迟到 `resolve_wait` 不得写入 canonical tool result；resolve 先到则 cancel 按最新 Run 状态继续处理。
- `cancel_run` 与 queue promotion 并发时，CAS first-committer-wins，输方必须重新读取 Run 状态并按最新状态处理。
- durable accepted 的 `CANCEL_REQUESTED` 在 terminal fact 之前胜出时，后续 recovery 不得继续用户目标。已取消的 lost Attempt 应按 policy 收口到 `CANCELLED` 或 `LOST`，不得创建新的正常执行 Attempt。

## 10. Durable Store

Host durable store 是本地治理真源。第一版使用 SQLite 承载以下 durable state：

- Session。
- Session slot。
- Run。
- Attempt。
- EventLog。
- durable queue。
- wait record。
- attempt dispatch record。
- host instance liveness record。
- durable payload table / descriptor table。
- projection checkpoint。
- optional outbox marker。

事务不变量：

- EventLog event append 必须分配全局单调 `event_sequence`；`event_sequence` 是 Host event stream cursor、projection checkpoint、outbox dispatch、audit replay 与恢复扫描的主 cursor。
- EventLog append 与必要 Run / Attempt 状态索引更新必须在同一 SQLite transaction 内完成，或具备等价原子性。
- Run terminal fact 提交与 Run 终态更新必须原子。
- Attempt terminal fact 提交与 Attempt 终态更新必须原子。
- queued Run promotion 到 `RUNNING` 与 Attempt 创建必须原子。
- 小型 / 中型可恢复 payload 可以写入 SQLite payload table，并与引用它的 EventLog `canonical_fact` append 在同一 transaction 内提交。
- projection checkpoint 不得先于对应 projection 持久化结果提交。

状态迁移必须使用 CAS-style 条件更新。实现不得以“读出状态后无条件写回”的方式更新 Run / Attempt。

durable store 语义分区：

- governance truth：Session、Run、Attempt、EventLog、wait record、dispatch record、payload descriptor。
- derived state index：active Run index、queue index、projection checkpoint、outbox work queue、memory snapshot cursor。
- diagnostic / trace：provider diagnostic refs、tool trace refs、late event diagnostic、shutdown diagnostic。

governance truth 只能由 Host transaction 写入。derived state index 可以从 governance truth 重建；diagnostic / trace 不能参与状态恢复判定。

Durable table ownership 跟随语义 owner，而不是跟随实现先后顺序。SQLite / transaction runner / EventLog / payload descriptor / idempotency / host instance liveness 是 durable foundation；Session / Run / Attempt / active index / queue index 属于状态机与 admission；wait record 属于 Tool Awaiting；projection checkpoint、audit、tool trace、outbox、memory snapshot、context artifacts、purge tombstone 等表属于各自 projection 或治理模块。实现不得创建无语义 owner 的空表，也不得让 projection 表成为 governance truth。

Phase 3 durable state / index contract：

Session / Run / Attempt state indexes 是 Host governance truth index，必须与对应 canonical EventLog facts 在同一 SQLite transaction 内更新。

- Session row 必须表达 `session_id`、status、创建时间、关闭时间等 lifecycle truth；Session 关闭是状态迁移，不删除 Session truth。
- Session slot row 必须表达 `(scope, slot_key) -> session_id` 的当前绑定，并由唯一约束保护 `(scope, slot_key)`。`ensure_session` 必须在同一事务内创建 Session 与 slot binding；遇到唯一约束竞争时，输方重新读取 winning binding，不留下可见孤儿 Session 作为调用结果。
- Run row 必须表达 `run_id`、`session_id`、status、`client_request_id`、accepted event sequence、当前 Attempt ref、source Run relation 与 terminal event ref 等 state-machine truth。active Run invariant 第一版优先用 SQLite partial unique index on `(session_id)` for active Run statuses 表达，让 active truth 跟随 `runs.status`，避免独立 active table 双写 owner；若后续 implementation 或 review 证明 partial unique index 与 SQLite 或测试约束不匹配，必须回到 design discussion 决策，不得由 implementation agent 自行改为独立 active-run table 或其它 active index 表示。
- queued Run FIFO 只能由 accepted `event_sequence` 排序；内存队列、进程本地顺序或 after-commit wakeup 顺序都不能成为 queue truth。
- Attempt row 必须表达 `attempt_id`、`run_id`、`execution_id`、status、started event ref 与 terminal event ref 等 execution lifecycle truth；旧 Attempt 不 resume，新执行必须创建新 Attempt 与新 `execution_id`。
- Minimal dispatch record row 属于 Attempt startup truth 的一部分。`ATTEMPT_STARTED` 要求 Attempt row 已进入 `STARTING`，且 dispatch record row 在同一事务内创建为 `pending`。Phase 3 只写 dispatch record `pending` 与 `cancelled`；scheduler、lane acquire、WorkerProxy、LocalProxy、RemoteProxy、Engine dispatch、`dispatching` 推进和 `ATTEMPT_RUNNING` 均属于 Phase 5 或后续 phase。
- 每个 transition service 必须把 CAS preconditions 表达为预期的 Session / Run / Attempt / dispatch record 当前状态。条件更新 `rowcount=0` 表示 CAS loser 或状态已变化；实现必须重新读取 durable snapshot，并返回结构化 conflict、invalid state 或当前结果，不得无条件覆盖最新状态。
- Operation idempotency 的 `scope_kind`、`scope_id`、`idempotency_key`、semantic digest 输入字段、result kind、result ref 与 first canonical event ref 绑定必须在进入实现前按 operation 固定。不同 operation 不能共用含义模糊的 idempotency scope，也不能把显式参数塞进无结构 extra payload。

SQLite schema convention：

- 第一版 Host durable store 使用单个 SQLite 数据库文件作为 Host 本地治理真源。`dayu.runtime.lane` 的 runtime lane DB 仍是独立 runtime coordinator，不得复用 Host durable store。
- 第一版按全新 schema 起库处理。bootstrap 只负责 fresh DB schema creation 与幂等校验，不提供旧库兼容读取、兼容迁移或旧 schema fallback。
- bootstrap 必须设置并校验 `PRAGMA user_version`，用于标识当前 Host durable schema version。schema version 不匹配时必须结构化失败，不得静默按旧 schema 运行。
- fresh bootstrap 的全量 DDL 与 `PRAGMA user_version` 写入必须有明确事务边界并同成同败。DDL 中途失败不得留下带 current `user_version` 的半初始化 durable store；下一次 open 要么从 fresh 状态完整成功，要么以结构化 schema / corruption 错误失败。
- current-version DB 的 opener validation 不得只相信 `PRAGMA user_version`，也不得把缺表 / 缺索引的 current-version DB 通过 `CREATE ... IF NOT EXISTS` 静默修好并继续运行。若 required table / index / schema invariant 缺失，普通 opener 必须结构化失败；显式 offline repair / rebuild 工具必须另行设计，不能混进正常 open path。
- durable ids 使用 TEXT 存储稳定业务标识，例如 `session_id`、`run_id`、`attempt_id`、`execution_id`、`event_id`、`host_instance_id`。`event_sequence` 是 EventLog 的全局 INTEGER cursor，不替代这些业务 id。
- durable timestamp 使用 UTC ISO-8601 TEXT 存储，必须规范化为 UTC、固定微秒精度并使用 `Z` 后缀。schema、reader 和 tests 不得混用本地时区、naive datetime、Unix timestamp integer 或多种 timestamp 表达。
- JSON payload、policy decision、reason、actor、source、diagnostic refs 等结构化字段以确定性 canonical JSON TEXT 存储；digest 计算必须基于同一 canonicalization，不能依赖 Python dict 插入顺序或数据库返回顺序。
- 外键约束必须开启。能够由 schema 表达的唯一性必须用显式 unique index 或 primary key 表达；不能只依赖 application-side check。
- 每个 foundation table 必须有明确语义 owner。不得为了后续 phase 预创建空的 Session / Run / Attempt / wait / projection / outbox / memory / purge tables。

SQLite transaction runner：

- Host mutating command 使用短 write transaction。write transaction 必须显式进入 `BEGIN IMMEDIATE`，避免在写入中途才升级锁导致不确定失败。
- Host durable connection 必须启用 WAL、`foreign_keys=ON` 和明确 busy timeout；这些属于 Host storage policy，不复用 runtime lane 的 SQLite 配置。
- WAL auto-checkpoint 可以作为 baseline，但 production hardening 必须定义 Host-owned checkpoint maintenance policy：触发点、运行时机、失败诊断、WAL size / checkpoint result 观测和测试入口必须明确。checkpoint 不得在 Host hot write transaction 内阻塞执行，也不得成为 EventLog append、state transition、recovery 或 projection correctness 的前置条件；checkpoint failure 只能进入 diagnostic / maintenance 路径。
- retry policy 只包裹短事务级 SQLite busy / locked 类失败，并必须有有限重试次数和退避。唯一约束冲突、外键错误、schema mismatch、payload digest mismatch、idempotency conflict、CAS precondition failed 不得按 busy retry 处理。
- Read transaction 使用 SQLite snapshot 语义：单个 read transaction 内允许看到 transaction 开始时的稳定旧快照。需要 fresh durable truth 的 public read、scheduler、recovery 和 governance decision 必须开启新的短 read / write transaction；不得复用长 read transaction、read model、projection lag、memory snapshot 或 watch cache 作为治理真源。
- transaction runner 必须保证 commit 成功前不会触发 after-commit wakeup。after-commit callbacks 只在 SQLite commit 成功后执行；rollback、异常或 retry 中间失败不得唤醒 projection / sink / dispatcher。
- 长耗时工作、Engine dispatch、artifact 大文件写入、projection、audit、tool trace、memory projection 不得在 Host SQLite write transaction 内执行。事务内只做状态校验、EventLog append、foundation row 写入、必要 state index 更新和可证明短小的 payload row 写入。

### 10.1 Host Handle / Composition Root

Host 公共函数接收的 `host` 是 composition root / handle，不是业务 God object。它只负责持有模块化依赖和事务入口，不把各子系统状态混成一个可变大包。

Host composition root 可以拥有两类能力：command path handle 与 background runtime supervisor。二者可以由同一个构造入口装配，但必须向调用方和子系统暴露不同 facet。

command path handle 只服务同步治理命令，例如 `submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run`。它可以持有内部新 Run admission primitive，但不把 `start_run` 作为 Service-facing public API 暴露。它可以持有：

- durable store / transaction runner。
- EventLog appender / reader。
- Run admission 与 queue promotion service。
- Attempt dispatcher / WorkerProxy factory。
- ToolRuntime factory。
- RunInputBuilder。
- state transition services。
- typed policy views / immutable policy snapshot refs。
- active worker cancel registry；默认值只能在 composition root 构造时创建 fresh registry。command handle 与 scheduler 需要共享 active cancel 传播时，必须由 production composition root 显式传入同一个 registry 对象；不得依赖模块级 mutable singleton 或 public helper 绕过 Host handle ownership。
- clock / id generator。
- after-commit wakeup port。

内部新 Run admission primitive 的实现名固定为 `_start_run`。`_start_run` 是 Host 内部 contract，不从 `dayu.host` public namespace 导出，不进入普通 Service-facing public API，不进入 P10.5 thin Service recipe。第一条 prompt 与后续普通 prompt 的 Service-facing 入口统一是 `submit_followup(queue)`。

background runtime supervisor 只服务已提交事实的追平、投影和投递。它可以持有：

- Observer / Sink runner。
- Outbox projection runner。
- stream fanout。
- projection workers。
- wait poller adapter / supervisor（P10.5 不要求实现生产后台 loop）。
- sink-local checkpoint / retry state。

每个依赖必须有清晰 ownership；Host handle 不能让 Service、UI、RemoteStub 或 Sink 绕过 Host 状态机直接写 durable truth。

command path 与 background runtime 的固定路径：

```text
Host mutating command
  -> durable transaction
  -> append EventLog / update state indexes
  -> commit
  -> after-commit wakeup port signals background supervisor
  -> supervisor catches up Sink / Outbox / projection by event_sequence checkpoint
```

command path 不直接运行慢 projection、outbox projection、tool trace 写文件或 memory projection。background runtime 不 append canonical facts，不更新 Run / Attempt governance state，也不决定 mutating command 是否成功。

运行参数约束：

- Host 运行参数可以有默认值，但默认值只能在 Host composition root 构造时应用。
- 所有影响持久化、执行、恢复、投影、工具治理或外部通信的运行参数，都必须有显式接口可由调用方传入；不得只能通过模块级全局变量、隐式单例、环境变量或硬编码路径取得。
- EventLog / durable store 所在数据库、payload / artifact 目录、projection / outbox 存储位置、worker target、policy provider、clock、id generator、truncation / context budget policy、compactor runner / storage config、compact artifact root、memory catch-up port 都属于可注入运行参数。
- 外部业务 `ToolBundle` 是 Host construction / composition root 的显式输入参数。Host handle 必须记录 tool bundle digest、schema digest 和 source refs，用于 Attempt snapshot、audit 和 diagnostic 解释。
- Host 公共操作函数不接收零散全局配置；它们接收已构造好的 Host handle。Host handle 的构造函数或工厂函数必须暴露 typed options / request，用于传入上述运行参数。
- 默认参数必须能被显式传入值完全覆盖；覆盖后的值必须进入 Host snapshot / diagnostic / audit 所需的可解释 refs，便于排查不同入口或进程使用的运行配置。

Phase 1 必须稳定 ToolBundle construction input 的最小 typed shape，但不实现 Host command path、durable store、ToolRuntime policy resolution 或 framework tool 注入逻辑。最小 Python 3.11 类型形状为：

```text
class ToolBundleSourceKind(StrEnum):
    EXPLICIT_PROVIDER = "explicit_provider"
    CONFIG_BINDING = "config_binding"
    PACKAGE_ENTRYPOINT = "package_entrypoint"
    SERVICE_COMPOSITION = "service_composition"

class FrameworkToolName(StrEnum):
    FETCH_MORE = "fetch_more"

@dataclass(frozen=True, slots=True)
HostToolingOptions
  business_tool_bundle: ToolBundle
  source_refs: tuple[ToolBundleSourceRef, ...]
  framework_tool_policy: FrameworkToolPolicyView

@dataclass(frozen=True, slots=True)
ToolBundleSourceRef
  source_kind: ToolBundleSourceKind
  source_id: str
  version_ref?: str
  content_digest?: str

@dataclass(frozen=True, slots=True)
FrameworkToolPolicyView
  reserved_framework_tool_names: frozenset[FrameworkToolName]
  enabled_framework_tools: frozenset[FrameworkToolName]
```

`HostToolingOptions` 属于 Host construction options 的一部分，只能在 composition root / host factory 接收。`business_tool_bundle` 不得出现在 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resume request 或无结构 metadata 中。`SubmitFollowupRequest` 可以携带本次 Run 的 business tool selector，但只能是 typed tool name selector，不能携带 raw `ToolBundle`、`ToolDefinition`、callable binding 或 discovery adapter。`ToolBundleSourceRef` 只记录可解释来源、版本与 digest；它不携带 callable，不反向指向具体业务工具模块，也不要求 Host 能重新执行 discovery。

P10.5 per-run business tool selection 语义：

- Host opener / construction options 接收全量业务 `ToolBundle`。
- `SubmitFollowupRequest.tool_names` 是本次 Run 的业务工具选择器。
- `tool_names is None` 或字段省略表示本次 Run 允许使用全量业务工具。
- `tool_names == ()` 或空集合表示本次 Run 禁用业务工具；framework tools 是否可用仍由 framework tool policy 决定。
- `tool_names` 为非空集合时表示只允许这些工具名。
- Host admission 必须校验每个 tool name 都存在于 construction-time `business_tool_bundle`，并把 resolved effective business tool names / digest 冻结到 Run / Attempt 可解释 snapshot 或 source refs 中。
- `tool_names` 不得使用无结构 metadata、逗号分隔字符串、自然语言工具描述或 tool schema 片段表达。
- `None=all` 与 `empty=none` 必须严格区分；空集合不得被解释成全部工具，避免调用方 bug 导致权限扩大。

`ToolBundleSourceKind` 必须使用 Python 3.11 `enum.StrEnum`，不得实现为普通 `str` 常量或 `typing.Literal`，以保证 source refs 具备稳定字符串序列化和受限取值。`FrameworkToolName` 同样必须使用 Python 3.11 `enum.StrEnum`，不得实现为普通 `str` 常量或 `typing.Literal`；当前 framework tool 名称集合至少包含 `fetch_more`。`FrameworkToolPolicyView.reserved_framework_tool_names` 用于禁止业务 `ToolBundle` 占用 Host framework tool 名称，即使某个 framework tool 当前未启用也可以被保留。`FrameworkToolPolicyView.enabled_framework_tools` 只表达 construction-time policy view，表示本 Host handle 允许后续 ToolRuntime factory 注入的 framework tool 名称集合；它不得在 Phase 1 触发 ToolRuntime 注入、tool governance policy resolution 或 per-run policy override。

Phase 1 的默认 reserved framework tool names 至少包含 `FrameworkToolName.FETCH_MORE`。enabled framework tools 必须显式来自 Host construction options 或其默认值；默认值不表达完整工具治理策略。`FrameworkToolPolicyView` 是独立的 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`。后续 ToolRuntime / Tool Governance phase 可以消费它，或将其并入更完整的 `ToolGovernancePolicyView`，但 Phase 1 不实现完整工具治理策略。

`HostPolicyProviderSet` 是一组 typed policy providers，不是插件市场、全局 registry、service locator 或 god bag。它只承载 Host 运行时需要读取的治理策略：

- admission policy。
- worker selection policy。
- retry / replay policy。
- cancel policy。
- context budget policy。
- tool governance policy。
- sink / outbox policy。

每个 policy provider 必须有明确输入、输出和 owner。互不相关的策略不得塞进一个无结构 config payload。

`HostPolicyProviderSet` 只存在于 composition root / acceptance command path。Attempt snapshot 和子系统不能持有整个 provider set；它们只能接收已经解析过的 typed policy view 或 immutable policy snapshot ref，例如：

- `AdmissionPolicyView`
- `WorkerSelectionPolicyView`
- `ToolGovernancePolicyView`
- `ContextBudgetPolicyView`
- `OutboxPolicyView`

策略使用路径固定为：

```text
HostPolicyProviderSet at composition root
  -> command path resolves policy decisions / snapshots at acceptance or dispatch boundary
  -> each subsystem receives only its typed policy view or immutable policy snapshot refs
  -> subsystem executes with that view / ref
  -> audit / trace records policy decision id / ref needed to explain behavior
```

子系统不得用字符串 key 反查全局 policy，也不得把 policy provider set 当作跨层 service locator。

## 11. Host 公共接口

Host 公共接口采用函数式风格，但不得依赖全局隐式单例。公共函数接收明确的 Host handle / context 与 request，返回稳定 snapshot 或 Host event stream。

Service-facing 第一版应表现为一个简单 Host opener / handle，而不是把 scheduler、runner、tooling、memory catch-up、wakeup 或 `HostLocalRuntime` 暴露给上层。调用方形态是打开 Host、取得 / 新建 / 读取 Session、提交 prompt 或控制命令、读取 / 订阅 Session 事件、在 terminal event 中观察 final answer、关闭 Host。内部可以使用 composition root / runtime 装配 command handle、durable store、scheduler、active registry、local execution、ToolRuntime、compactor 与 projection catch-up，但这些只是 Host 内部实现边界。

P10.5 冻结 async-only Host opener / handle。Service-facing opener 名称固定为 `open_host(options)`，并且必须是 async context manager：`async with open_host(options) as host:`。handle methods 与 event stream consumption 均以 async public contract 为准。Host public contract 不提供同步 wrapper，不冻结同步 close / cancel / timeout / stream iteration 语义。CLI 或同步上层如需使用 Host，应在 Service / CLI adapter 边界用 `asyncio.run(...)` 或等价机制包装 async Host contract，不要求 Host 层维护第二套同步 API。

Host opener close 是 Host handle lifecycle 语义，不是 Session / Run 治理事实。`host.close()` 与 `open_host(...).__aexit__` 必须幂等；重复 close 不报错。close 完成后，调用该 handle 上的 `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`get_run`、`watch_session_events`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run` 等 Host API，必须 fail-fast 抛出 typed `HostClosedError` 或等价 Host lifecycle exception。这个错误不写 EventLog，不返回 command-level `invalid_state`，也不与 `Session CLOSED`、not found、purged、retry precondition failed 等业务状态混淆。已经进入 admission / command transaction 的调用按正常事务语义完成；close gate 之后新进入的调用统一抛 closed-handle exception。

Host opener close 会终止当前 handle 持有的本地运行环境，但不得伪装成用户取消。close 流程必须停止 scheduler / promotion / background supervisor，不再启动新的 Attempt；必须向 active worker registry 传播 lifecycle cancel，使 Host 注入 Engine 的 cancellation token 可见，并通知 `LocalWorkerHandle.on_cancel(reason)` 这个 best-effort hook；随后关闭或取消当前 handle 持有的 active worker task、lane wait、stream fanout task 与本地 runtime resource，避免进程内任务泄漏。若 close 过程中 active worker 已经产出可确认 terminal event，Host 按正常 ingest / terminal closeout 追加事实。若 active worker 没有可确认 terminal，Host close 不得写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED` 或其它伪装用户意图 / 确认失败的 canonical fact；未收口 active Attempt 后续必须通过 Host lifecycle / Recovery 的 positive orphan proof 路径进入 `ATTEMPT_LOST`，再按 policy 进入 `RUN_RECOVERING` 或 `RUN_LOST`。调用方若要表达用户明确停止，应在 close 前显式调用 `cancel_run(...)` 或 `cancel_session_runs(...)`。

P10.5 的 Host opener close shutdown order 是 implementation requirement，不是新的 public API 设计点。推荐顺序是：先关闭 public gate 并拒绝新进入 API；停止 scheduler / promotion / background supervisor，避免启动新 Attempt；关闭 session live watch fanout，让 watcher 正常结束或收到 Host lifecycle termination；取消或关闭当前 handle 持有的 active worker task、lane wait、worker stream consumer task；flush / close projection catch-up 与本地 runtime resources；最后关闭 durable store。全程不得写 `RUN_CANCELLED` / `RUN_FAILED` 或其它 terminal fact 来伪装用户意图；已经在 close 过程中确认的真实 terminal event 仍按正常 ingest / terminal closeout 处理。

P10.5 冻结的是后续真实生产系统 Service 使用的普通多轮生产接线，不是 smoke 专用接线。P10.5 自身必须把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实；真实 CLI / web / GUI 在 P11-P15 实施完毕后会通过 Service 使用这里冻结的 Host public interface / contract 接入，不能等到真实入口接入时再补一条新接线。后续 phase 可以扩展 Recovery、ToolsDiscovery / ScenePrepare、Audit / Tool Trace / Outbox、RemoteProxy 与 Retention / Purge 能力，但不得要求真实入口绕过、替换或重写普通多轮会话的 Host 生产接线。

`open_host(options)` 的 options 只承载打开 Host、驱动 Host -> Engine 本地运行所需的 construction-time 参数。Host public API 保持朴素接口形式：内部运行真正需要外部提供的 durable store / payload / artifact roots、runner / worker factory、全量 business `ToolBundle`、ToolRuntime policy、compactor runner / storage config、context budget policy、memory catch-up、stream fanout / background supervisor 所需端口和运行目录等依赖，由调用方通过 typed function 参数显式传入；Host 不在 P10.5 引入 ConfigLoader、全局配置系统或 service locator。scheduler、wakeup、active worker registry、dispatch control 等 Host 内部接线由 `open_host` composition root 自行创建或连接，不作为 Service-facing 参数暴露。每次 Run 会变化的参数不得塞进 `open_host` options；它们必须进入对应 public request，例如普通 prompt / per-run tool selection / run-local instruction 进入 `SubmitFollowupRequest`，retry / replay 控制参数进入各自 request，后续若新增 per-run profile / target 也必须作为明确 request contract 讨论和冻结。

一个 `open_host(options)` 表达一个 Host runtime environment 与默认 ordinary Run execution baseline。durable store、scheduler / worker wiring、memory / artifact roots、全量 business `ToolBundle`、Host policy 基线与默认 `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy` 都属于 construction-time baseline。真实生产系统在同一个 Session 的不同 Run 中切换模型是正常需求；P10.5 不通过 `profile_id` / registry lookup 表达这件事，而是允许 `SubmitFollowupRequest` 直接携带可选 typed override 对象：`runner_spec?: RunnerSpec`、`runner_options?: RunnerCallOptions`、`agent_policy?: AgentPolicy`。字段省略时使用 `open_host(options)` 的默认 ordinary Run baseline；字段出现时使用该 Run 显式传入的 typed value。override 是按字段 partial merge，不是 all-or-nothing profile：例如只传 `runner_options` 时，`RunnerSpec` 与 `AgentPolicy` 仍取 opener baseline；只传 `runner_spec` 时，runner call options 与 agent policy 仍取 opener baseline。每个出现的 override 对象本身必须是完整 typed value，不能是 patch dict、增量字段包或 extra payload。Host 不接收 raw provider client、API key 明文、callable、无结构 dict override、extra payload 或 `policy_overrides`。`RunnerSpec.api_key_ref` 仍只是 secret 引用名，不是 secret 本体。Host admission / dispatch 必须校验并冻结每个 Run 的 effective runner spec / runner options / agent policy 到 Run / Attempt 可解释 snapshot 或 source refs，保证 retry / replay / recovery 能解释当时使用的执行配置。普通每 Run 其它可变项第一版包括显式 `system_prompt`、`user_prompt`、`tool_names` 以及必要的 `client_request_id`、actor / source refs 等 request metadata。后续若新增更细粒度 per-run override，也必须作为 typed request field 讨论并冻结。

LLM compactor 与 ordinary Run 共享同一个 Host runtime environment、durable store、memory / artifact roots、budget governance 与 canonical event / artifact 接线，但不共享每个 Run 的 execution override。Service / `open_host(options)` 只能提供 compactor runner、scene/baseline prompt、compactor AgentPolicy 与 storage 配置，例如 `compactor_runner_spec`、`compactor_runner_options`、Service 从 compactor scene 装配的 system prompt、Service 从 compactor scene 装配的完整 `AgentPolicy`、Service 从 `compactor_baseline.user_prompt_template_path` 读取的 user prompt template、context budget policy 与 compact artifact root；不能提供 `ContextCompactor` 实例、policy ref、candidate builder、quality check、artifact writer 或 repair callback。当前只有一套 Host compactor policy，因此 compactor policy id / version 是 Host 内部常量或 typed policy snapshot ref，只用于 EventLog / artifact / diagnostic 审计，不进入 Service-facing opener contract。Host 在 opener composition root 内部构造 Host-owned LLM compactor，并把它接入 Context Governance internal seam。`SubmitFollowupRequest.runner_spec` / `runner_options` / `agent_policy`、`tool_names`、`system_prompt` 不影响 compactor；compactor 不创建用户可见 Run，不产出 final answer，不使用 business ToolRuntime。后续如需多套 compactor policy，必须先作为 Host-recognized typed policy profile 重新设计 public contract，不能先暴露 raw string `policy_ref`，也不能借用 ordinary Run override、metadata 或 extra payload。

Scheduler wakeup ownership 已由本设计冻结，不是 P10.5 待讨论 public contract。`submit_followup(queue)`、`retry_run(...)`、`replay_run(...)`、`resolve_wait(...)`、terminal closeout 与 cancel 释放 active slot 等命令提交后，需要唤醒 scheduler / promotion / dispatch 的地方，都必须通过 Host 内部 after-commit wakeup port 或等价 background supervisor 接线完成。Service 不得调用 scheduler wakeup、读取 dispatch row 或控制 dispatch。P10.5 的责任是把 production `open_host(options)` 中的 command facade、after-commit wakeup port、background supervisor、scheduler 与 shared active worker registry 接到同一 composition root 上，并用 public-path smoke 证明命令 commit 后无需 Service 额外唤醒即可推进执行。

P10.5 冻结的普通本地多轮会话 contract 必须包含 memory catch-up 与 context overflow compact 的 public opener 接线。普通 Service 不得为了完成多轮闭环而直接装配或调用 memory projection、compact artifact store、scheduler pre-start governance、dispatch scheduler、RunInputBuilder 内部接口或 `ContextCompactor.compact(...)`。Host opener / handle 的 typed construction options 必须能接收或配置 compactor runner baseline、context budget policy、compact artifact root 与 memory catch-up；Host 内部负责构造 Host-owned compactor，在 accepted / queued Run dispatch 前完成必要 catch-up、compact artifact 写入、canonical compact event 追加、memory projection consumption 与 subsequent RunInputBuilder 注入。P10.5 compact smoke 必须接入真实 Host-owned compactor runner 配置；mock / test-double compactor 只能作为低层测试或显式本地辅助回归，不能作为普通本地多轮闭环的 compact success signal，也不得成为 production opener 的隐式默认值。

P10.5 的普通 Service dialing 形态固定为 async Host handle + session-level async event iterator。Service 仍必须保存 Outbox attach / reconnect 所需的 terminal watermark / seen ids，但 P10.5 不实现 Outbox read / drain API；离线 terminal 补读归 Phase 13。以下伪代码表达 P10.5 public contract 形状：

```python
async with open_host(options) as host:
    session = await host.ensure_session(...)
    session_id = session.session_id

    events = host.watch_session_events(session_id)
    event_task = asyncio.create_task(consume_session_events(events))

    await host.submit_followup(
        session_id,
        SubmitFollowupRequest(...),
    )

    # final answer is rendered by consume_session_events from terminal HostEvent.
    event_task.cancel()
```

等价地，调用方可以直接在 async iterator 上消费事件：

```python
async with open_host(options) as host:
    session = await host.get_session(session_id)

    events = host.watch_session_events(session.session_id)
    await host.submit_followup(session.session_id, request)

    async for event in events:
        render_once_by_terminal_identity(event)
```

这两个形态都以 `watch_session_events(session_id) -> AsyncIterator[HostEvent]` 为普通聊天主事件入口；`watch_session_events` 是 live watch，不接收 cursor，不负责离线补读。该 async iterator 在 session live watch 路径中产出 Host-owned typed `HostEvent`，不是 raw `EngineEvent`，也不是当前内部 EventLog 补读使用的薄 `HostEventView`。它对齐 Engine `run_agent_messages(...)` 的朴素 async generator 形态：调用方正常用 `async for` 消费；提前停止消费时，由调用方 cancel consumer task 或在返回对象支持 `aclose()` 时显式 `aclose()`，这只关闭本次 watch 订阅，不写 EventLog、不 cancel Run、不影响其它 watcher。terminal `HostEvent` 只是 iterator 中的一个事件，不让 iterator 自动结束；同一 Session 后续 queue / retry / replay / follow-up 事件仍可继续出现。Host handle 已 close 时打开 watch 必须抛 typed `HostClosedError` 或等价 lifecycle exception；session 不存在 / 已 purge 时抛 typed not-found / gone；Session `CLOSED` 仍允许 watch，因为它只拒绝新输入，不禁止读取事件。Host close 时已打开的 iterator 结束或抛 Host lifecycle termination，但不得写 EventLog 或 cancel Run。Service 拿到 `session_id` 后必须把 Outbox terminal 增量补读与 session live watch attach 视为同一个 attach / reconnect 协议：用客户端保存的 `last_seen_terminal_event_sequence` / `seen_terminal_event_ids` 读取 Outbox 中离线 terminal / final answer 增量，同时或随后打开 `watch_session_events(session_id)`，并用 `terminal_event_id` / `event_sequence` / `run_id` 去重，避免离线补读与 live watch 之间漏投或重复展示 terminal answer。一个 Run 的 terminal `HostEvent`，包括 final answer typed view，可在该 Session 的 async event iterator 中观察到。P10.5 不实现 Outbox read / drain API，不把离线 terminal 补读计入 smoke coverage；P10.5 只冻结 attach / reconnect recipe、terminal identity 与去重要求，Outbox concrete projection / read API / delivery queue 继续归 Phase 13。P10.5 不定义 `wait_final_answer(...)` public API；普通 Service 必须从 `watch_session_events(session_id)` 的 terminal HostEvent 取得在线 final answer，smoke 也不得用等待 helper 替代 live watch 主路径。

`HostEvent` 的边界：

- `HostEvent` 是 Host ingest / 校验 / governance / EventLog commit 后形成的 Service-facing typed event。它可以引用原始 EngineEvent provenance，但不得把 raw `EngineEvent` 或 Host internal envelope 原样暴露给 Service。
- 第一版 `HostEvent` 固定携带 `event_id`、`event_sequence`、`session_id`、`run_id?`、typed kind、dedupe identity 和 display payload。terminal HostEvent 必须包含 typed terminal view；`SUCCEEDED` terminal 必须 inline 可展示的 final answer view，字段固定为 `content`、`filtered`、`degraded`、`finish_reason` 与 terminal status。
- tool event、thinking delta、content delta 是否展示由 UI 决定；Host 只负责把它们作为 typed HostEvent 暴露为可选择显示的事件，不在 Host 内部决定 UI 展示策略。
- `HostEventView` 是 EventLog row 的 Host 内部薄读模型 / diagnostic DTO，可服务内部 run-scoped EventLog 补读、debug、diagnostic、drill-down 和局部断言；它不作为普通聊天主事件流的元素类型，也不从 `dayu.host` Service-facing public namespace 导出。
- Phase 13 的 Audit / Tool Trace / Outbox 与 `watch_session_events` 一样消费 committed EventLog / typed projection input view；它们不需要也不得依赖 `HostEventView`、`watch_session_events` 或 Service-facing `HostEvent` display view，也不得从 raw EngineEvent 直接派生 truth。

类型归属规则：

- `dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 边界都必须理解的层间协作契约，例如现有 `ToolBundle`、`ToolDefinition`、`ToolSchema`、`ToolExecutor`、批式工具调用 / outcome、取消观察 token 与严格 JSON 值。
- Host 公共 API 类型放在 `dayu.host` 的公共命名空间，而不是放进 `dayu.contracts`。这些类型包括 Host handle / command facet、`HostCallContext`、`OperationContext`、各 mutating request、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventStream`、Session / Run / Attempt status enum、Host API error code 与 stream cursor 类型。Service / UI 可以按向下依赖关系 import `dayu.host` 公共类型；Engine 不得 import 这些类型。
- Host 内部类型留在 `dayu.host` 内部模块，不从公共命名空间导出。这些类型包括 durable EventLog row、状态索引 row、dispatch record、idempotency record、transaction object、policy provider set、ToolRuntime snapshot、accept barrier 内部 candidate、projection checkpoint row、recovery scan record 与 background supervisor 私有状态。
- 如果某个类型同时被多层读写，必须先审视边界是否过宽；不能因为多个调用方想复用 dataclass 就把 Host 私有治理状态提前提升到 `dayu.contracts`。

第一版最小接口集合：

```text
ensure_session(host, request) -> SessionSnapshot
create_session(host, request) -> SessionSnapshot
get_session(host, session_id) -> SessionSnapshot
close_session(host, session_id, request) -> SessionSnapshot
purge_session(host, session_id, request) -> PurgeSessionResult

get_run(host, run_id) -> RunSnapshot
watch_session_events(host, session_id) -> AsyncIterator[HostEvent]
cancel_run(host, run_id, request) -> RunSnapshot
cancel_session_runs(host, session_id, request) -> SessionSnapshot
submit_followup(host, session_id, request) -> FollowupSnapshot
retry_run(host, run_id, request) -> RunSnapshot
replay_run(host, run_id, request) -> RunSnapshot
resolve_wait(host, wait_id, request) -> RunSnapshot
```

以下能力不属于普通 Service-facing public contract：

- `start_run(...)` / `_start_run(...)`：`_start_run` 是 Host 内部 admission primitive，普通 Service 不可调用。
- `create_host_command_handle(...)`：降为 Host 内部 / 低层测试 composition primitive，不作为 Service 打开 Host 的入口；Service-facing 打开入口只有 `open_host(options)`。
- `HostLocalRuntime`、`HostLocalExecutionOptions`：均为 Host 内部 contract 或 implementation type，不从普通 Service-facing public namespace 暴露。
- scheduler / wakeup / dispatch control API：Service 不得调用 scheduler wakeup、读取 dispatch row 或控制 dispatch；这些接线由 `open_host(options)` 内部完成。
- `stream_run_events(...)` / `HostEventView`：只作为 Host 内部 diagnostic / detail / debug / drill-down 补读契约保留，不进入普通 Service-facing public contract。若未来需要公开 run-scoped diagnostic read API，必须另行讨论并定义不同于内部 `HostEventView` 的 public typed DTO。
- public payload reader / `read_payload(ref)` / `get_run_result(...)`：P10.5 不定义这些 public API。final answer 只能通过 terminal HostEvent 展示；大 payload、分页或 result read-model 如未来需要，必须另行讨论 public contract，不能成为普通多轮主路径。

外部语义采用函数式操作。`retry_run(host, run_id, request)` 与 `replay_run(host, run_id, request)` 的语义分别是 `retry(run)` / `replay(run)`：输入是源 Run，输出是关联的新 RunSnapshot；它们不是在原 Run 上调用 `Run.retry` / `Run.replay` 来重开终态。

Phase 4 public function behavior matrix：

| 函数 / 路径 | Phase 4 行为 | 后续 owner / 说明 |
| --- | --- | --- |
| `ensure_session` | 完整实现 | 只依赖 Phase 1-3 durable store、slot binding 与 session lifecycle。 |
| `create_session` | 完整实现 | 只依赖 Phase 1-3 durable store、slot binding 与 session lifecycle。 |
| `get_session` | 完整实现 | 从 durable truth / minimal read path 构造 snapshot，不触发 projection worker。 |
| `close_session` | 完整实现 | 关闭新输入入口；不 cancel、不 purge。 |
| `submit_followup(queue)` | 完整实现 | 在同一 admission transaction 内吸收 active Run 竞态；结果用 `accepted_run_id` + `accepted_run_status` 表达。 |
| `get_run` | 完整实现 | 从 durable Run / Attempt truth 构造 snapshot。 |
| internal `stream_run_events` / run-scoped EventLog 补读 | 完整实现 EventLog-backed read path | 全局 EventLog cursor 是唯一 cursor truth；Phase 4 不引入 projection truth；P10.5 后该路径降为内部 diagnostic / detail contract。 |
| `cancel_run` queued / pre-dispatch `STARTING` | 完整实现 | 覆盖 Phase 1-3 已有可闭环路径：`QUEUED` 与 dispatch record 尚未进入 dispatching 的 Attempt `STARTING`。 |
| `cancel_session_runs` queued / pre-dispatch `STARTING` | 子集实现并追踪后续完善 | Phase 4 只批量覆盖上述 `cancel_run` 可闭环子集；dispatching / active worker、`WAITING`、`RECOVERING` cancel deferred。 |
| `submit_followup(steer)` | stable unsupported / deferred | Phase 4 只冻结 envelope、validation、error/detail contract；public facade 返回 `unsupported_operation`。完整 Attempt switching 由后续 steer / dispatch / wait owner 落地。 |
| `retry_run` | stable unsupported / deferred | Phase 4 冻结 request / idempotency / error envelope；执行语义由后续 retry owner 落地。 |
| `replay_run` | stable unsupported / deferred | Phase 4 冻结 request / idempotency / error envelope；执行语义由后续 replay owner 落地。 |
| `resolve_wait` | stable unsupported / deferred | Phase 7 owns wait record、tool result accept 与 resume Attempt。 |
| `purge_session` | stable unsupported / deferred | Phase 15 owns destructive cleanup 与 purge tombstone persistence。 |
| active dispatch cancel | stable unsupported / deferred | Phase 5 owns dispatching / active WorkerProxy cancel propagation。 |
| wait cancel | stable unsupported / deferred | Phase 7 owns `WAITING` closeout 与 external job best-effort cancel / abandon。 |
| recovery cancel | stable unsupported / deferred | Phase 11 owns `RECOVERING` dispatch / recovery scan cancellation。 |

所有会 append EventLog `canonical_fact` 或影响 audit 的 mutating request 都必须携带结构化 `HostCallContext` 或等价 request envelope。Host 不负责认证，但必须记录上层已经解析的 actor / principal、source / client、request id、权限声明和 operation context。required fields 不能塞进无结构 metadata。

本节 request 片段只列操作专属字段；mutating request envelope 必须统一包含 `HostCallContext`。

`HostCallContext` 语义契约：

```text
actor / principal       -> 谁代表本次操作负责
source / client         -> 操作来自哪个入口或客户端
request_id              -> 上层调用链路追踪 id
authorization_claims?   -> 上层已验证的权限声明
operation_context       -> 业务 / 操作上下文
```

`HostCallContext` 描述这次调用 Host 的来路、责任信息和业务操作上下文，回答“谁、从哪里、以什么权限、为了什么业务操作发起”。它不携带 delivery target，也不是统一幂等键。具体 request 描述状态机前置条件，并定义自己的幂等字段或幂等范围。

`OperationContext` 由 UI / Service 解析并传入，Host 不从 prompt 文本、session slot 或 metadata 猜业务对象。最小语义：

```text
operation_name          # 例如 fins.earnings_qna.ask / run.cancel / replay.repair
operation_kind          # user_prompt | control | system_recovery | tool_execution | projection
business_domain         # fins | host | service | system
business_object_type?   # company | filing | report | session | run | tool_call | other typed object
business_object_id?     # ticker / company_id / filing_id / report_id / typed ref
scenario?               # earnings_qna | annual_report_analysis | replay_repair | other typed scenario
correlation_id?         # 跨 Service / Host / tool trace / audit 的关联 id
```

`OperationContext` 不是 policy override，不决定权限，不替代 `authorization_claims`，不承载大业务 payload。EventLog、Audit、Tool Trace 和 Attempt snapshot 只能记录 operation context 的 typed identifiers / refs / digest。

Host 不从 `Session slot` 反推 actor，也不从 metadata 猜 actor、权限、业务对象或 channel 投递目标。匿名、系统动作和后台 policy 动作必须使用显式 actor 值和 operation context，例如 system actor / service actor。

mutating API 的通用路径：

```text
validate HostCallContext
  -> validate precondition and idempotency key
  -> open durable transaction
  -> append EventLog canonical facts
  -> update required governance indexes
  -> commit
  -> dispatch side effects only after commit
```

事务提交前不得启动 EngineWorker、写 outbox item、调用外部 job 或通知远端执行。提交后的 side effect 必须能从 EventLog / dispatch record / outbox checkpoint 恢复或重试。

Idempotency semantic contract：

- 每个 mutating operation 的幂等范围必须显式定义，例如 `(session_id, client_request_id)`、`(run_id, client_request_id)` 或 `(scope, slot_key)`。
- `HostCallContext` 不定义幂等范围；operation request owns idempotency key。
- 幂等记录绑定 operation name、scope / target object、semantic input digest、result object id 和 accepted event refs。
- 同一幂等键 + 同一 semantic input digest 重试时，Host 返回既有 snapshot，不重复 append canonical facts，不重复 dispatch。
- 同一幂等键 + 不同 semantic input digest 必须返回 `idempotency_conflict`，不得静默复用旧对象，也不得创建第二个对象。
- 已提交 Run / Attempt 后的重试只读取当前 truth 并返回最新 snapshot；它不能重新派发已经派发过的 Attempt。
- 幂等判断必须在 durable transaction 内完成，不能依赖进程内 cache。

`EnsureSessionRequest`：

```text
scope
slot_key
metadata
```

`CreateSessionRequest`：

```text
client_request_id
bind_slot?
scope?
slot_key?
metadata
```

`StartRunRequest`：

```text
session_id
client_request_id
input
execution_target
queue_policy
```

`CancelRunRequest`：

```text
client_request_id
reason
mode: graceful   # first version only
```

`CancelSessionRunsRequest`：

```text
client_request_id
reason
mode: graceful   # first version only
```

`CloseSessionRequest`：

```text
client_request_id
reason
```

`PurgeSessionRequest`：

```text
client_request_id
reason
```

`SubmitFollowupRequest`：

```text
session_id
client_request_id
system_prompt?
user_prompt
behavior: queue | steer
target_run_id?        # required when behavior=steer
tool_names?           # None / omitted = all business tools; empty = no business tools; non-empty = selected tool names
runner_spec?          # optional typed per-run override; omitted = open_host default
runner_options?       # optional typed per-run override; omitted = open_host default
agent_policy?         # optional typed per-run override; omitted = open_host default
```

`RetryRunRequest`：

```text
client_request_id
reason
```

`ReplayRunRequest`：

```text
client_request_id
reason
repair_instruction?
```

`ResolveWaitRequest`：

```text
idempotency_key
outcome
source: poll | callback | manual
observed_at
```

Run 接口语义：

- `submit_followup(queue)` 是 Service / UI 发送普通 prompt 的统一入口，包括同一 Session 的第一条 prompt。调用方取得 Session 后不需要判断“首轮调用 `start_run`、后续调用 `submit_followup`”；Host 在 admission transaction 内决定该输入是直接成为可启动 Run，还是排到当前 active Run 后面。
- `get_run`：读取 RunSnapshot；不触发执行、不触发 queue promotion、不改变 Run / Attempt 状态。
- `watch_session_events` / session-level Host event stream：Service / UI 观察 agent session 的主事件流。在线 / 已 attach 客户端通过 live watch 接收目标 Session 的事件，适合多客户端打开同一 Session、排队 Run、steer、retry / replay 链路和 final answer 展示。调用方可以先打开 session event stream，再并发提交 `submit_followup(...)` / `retry_run(...)` / `replay_run(...)` 等 mutation；事件观察与命令提交是两条并行通道，不要求 `submit_followup` 后才开始读某个 run stream。`watch_session_events` 不接收 cursor，不承担离线补读；Service 取得 Session 后进入 attach / reconnect 流程：先按客户端已保存的 terminal watermark / seen ids 补读 Outbox terminal 增量，再进入或保持 session live watch；实现上必须用 `terminal_event_id` / `event_sequence` / `run_id` 去重，避免 Outbox drain 与 live watch attach 之间出现漏消息窗口。断线后的在线 terminal/final answer 补读由 Outbox terminal delivery queue 承接；未 attach / 离线渠道不靠 live watch 接收中间过程。
- 普通 Service 的官方事件入口只有 `watch_session_events(session_id)`。普通多轮 recipe、thin Service proof、P10.5 no-tool / mock-tool / real-runner smoke 都必须走 session-level live watch，不能用内部 run-level EventLog 补读绕过 session live watch 来证明多轮闭环。
- 内部 `stream_run_events` / run-scoped EventLog 补读：从全局 `event_sequence` cursor 补读目标 Run 的事件。它是 Host 内部 diagnostic / detail / debug / drill-down helper，只服务内部测试、排查某次 retry / replay source run 或运维诊断；不得和 `watch_session_events` 并列成为 Service-facing 聊天入口。若未来要公开给 Run detail 页面，必须先定义 public diagnostic event DTO，不得直接暴露内部 `HostEventView`。
- `close_session`：关闭 Session 新输入入口，按 `(session_id, client_request_id)` 幂等；不取消、不终止、不删除已有 Run。
- `purge_session`：清理已关闭且全部 Run 终态的 Session，按 `(session_id, client_request_id)` 幂等；删除可恢复事实与 projection，只保留最小 purge tombstone / audit record。
- `cancel_run`：接受取消请求，按 `(run_id, client_request_id)` 幂等；queued Run 直接 `CANCELLED`，pre-worker `STARTING` Run 可直接 `CANCELLED`，包括 `pending`、`waiting_for_lane` 以及 WorkerProxy accepted 前的 `dispatching`。active worker cancel 进入 `CANCELLING` 并向当前 Attempt 传播 cancel 的完整能力由 Phase 5 落地；`WAITING` 与 `RECOVERING` cancel 分别由 Phase 7 / Phase 11 落地。
- `cancel_session_runs`：接受 session-scope cancel 请求，按 `(session_id, client_request_id)` 幂等；取消该 Session 下所有未终态 Run，不影响其它 Session。Phase 4 只实现 queued / pre-dispatch `STARTING` 子集，完整 pre-worker `dispatching` / active worker、`WAITING`、`RECOVERING` cancel 必须由 Phase 5 / 7 / 11 补齐。
- `submit_followup`：接受同一 Session 的普通 prompt 或控制输入。聊天界面的普通 prompt 入口应统一使用该接口，不应由调用方先读 active Run 再在 `start_run` / `submit_followup` 之间选择。`behavior=queue` 由 Host admission 在同一事务内决定排队或直接启动；`behavior=steer` 必须命中 `target_run_id` 所指的当前 active Run 并切换 Attempt。Phase 4 只冻结 steer envelope、validation 与 error/detail contract，public facade 对 steer 返回 `unsupported_operation`；完整 Attempt switching 后续落地。
- `retry_run`：公开 Host control API，由调用方主动发起；函数式语义为 `retry(run)`。它在 confirmed failure / recoverable failure 后创建关联的新 Run。原 Run 保持终态不可变；新 Run 可以按 retry policy 复用旧 Run 已接受工具事实，并创建自己的 Attempt。
- `replay_run`：公开 Host control API，由调用方主动发起；函数式语义为 `replay(run)`。它只用于 final answer 格式、schema、结构或输出 envelope 失败时创建关联的新 Run。原 `SUCCEEDED` Run 不重开；新 Run 默认复用旧 Run 已接受工具事实，并以 no-tool messages 调用做结构修复。事实内容脏、幻觉、业务归因错误、证据不足或证据冲突不属于 replay 场景。
- `resolve_wait`：等待结果接收与治理入口；接收 poll / callback / manual 已取得的结果，关闭 wait record，append tool terminal/result fact，并创建新 Attempt resume。它不负责等待外部长事务完成，不启动 poll loop，不阻塞等待外部结果，也不承载 callback HTTP endpoint / callback auth / replay 防护。
  Phase 7 起，`ResolveWaitRequest.outcome_ref: str` 必须被强类型 `outcome` envelope 替代；request 至少区分 completed /
  failed / cancelled / lost。外部结果引用或 payload ref 只能作为 `outcome` envelope 的受限字段，不能替代显式 outcome
  类型与 Host 状态机含义。`resolve_wait(host, wait_id, request)` 成功返回当前 `RunSnapshot`。

第一版公共 API 不暴露开放式 policy knobs。Host policy 可以有默认值，但 request 不能携带无结构 `policy_overrides`。`CancelRunRequest.mode` 第一版唯一值为 `graceful`；不支持 `force` / `immediate`。`retry_run` 是否复用 accepted tool facts、重试次数和退避由 Host retry policy 决定。`replay_run` 固定复用源 Run accepted tool facts / evidence anchors，固定 no tools，固定只做结构修复。

Run 读取与结果边界：

- Run 当前结果通过 `get_run` 的 `RunSnapshot.terminal result summary`、session-level Host event stream 的 terminal HostEvent 暴露。内部 run-scoped EventLog 补读也能按 Run 维度读取同一 terminal fact，但只作为 diagnostic / detail / debug / drill-down 内部视图。P10.5 不定义 `wait_final_answer(run_id)` public API；final answer 的普通 Service 主展示路径只能是 `watch_session_events(session_id)` 的 terminal HostEvent。
- P10.5 不定义 public payload reader、`read_payload(ref)` 或 `get_run_result(...)`；普通 Service 不得为了展示 final answer 读取内部 payload 表。若后续需要大结果分页或多版本 replay result，必须作为新的 read-model public contract 单独讨论，且不能成为事实真源。
- Session timeline 仍通过 `get_session` snapshot 或后续 read-model API 暴露；它不能替代 Host event stream 的 live watch 语义，也不能替代 Outbox 的离线 terminal 投递职责。

接口分层：

- `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`get_run`、`watch_session_events`、`cancel_run`、`cancel_session_runs`、`submit_followup` 是普通 Service-facing 稳定公共能力。
- `stream_run_events` 不进入 P10.5 普通 Service-facing public contract；现有实现若保留，只能作为 Host 内部 diagnostic / detail read path。未来若要公开 run-scoped diagnostic read API，必须另行讨论 public contract，且不能直接暴露内部 `HostEventView`。
- `cancel_session_runs` 是客户端退出 / supervisor shutdown 的便利公共能力；它只取消指定 Session 下未终态 Run，不表达客户端拥有的 Session 集合。
- `ensure_session` 表示“给我这个 slot 的当前会话，必要时创建并绑定”。
- `create_session` 表示“明确分配一个新 Session”，可选绑定 slot。
- `start_run` 不作为 Service-facing public API 暴露。内部 admission primitive 命名为 `_start_run`，用于表达“创建独立 Run”的低层语义，但普通 Service 不应依赖它；P10.5 必须把包根 public export、README 与 tests 调整到这一边界。
- `retry_run`、`replay_run` 是 Host control API；UI / Service 可以暴露，但必须保留 `retry(run)` / `replay(run)` 的函数式语义、Host 幂等与状态机。
- `resolve_wait` 是 Host 内部 / adapter API；poller、callback handler、manual admin 入口都必须走它，不能各自写 Run 状态。
- P10.5 ordinary local multi-turn public contract 只冻结并验证 `WAITING` / wait record / `resolve_wait(...)` 的 public resume path：调用方或 tool adapter 已经通过 poll、callback 或 manual 操作拿到外部结果后，调用 Host public `resolve_wait(...)`，Host 通过 after-commit wakeup 创建 resume Attempt、推进 dispatch，并在 session-level `watch_session_events(...)` 中暴露后续 terminal HostEvent。生产级 callback endpoint、callback auth / replay、poller 后台 loop、backoff / in-flight fencing 与 external job physical cancel / revoke 不属于 P10.5 阻塞项；它们是后续生产集成 / scale owner，不能改变 `resolve_wait(...)` 作为唯一等待结果治理入口的边界。
- 读取 Session timeline 通过 `get_session` 的 snapshot、session-level Host event stream 或后续 read-model API 暴露；它必须从 EventLog / projection 读取，不触发执行。离线 / 未 attach 客户端的 final answer 通知通过 Outbox terminal delivery queue 读取，不通过 session live watch 追补完整中间过程。

Snapshot 最小语义：

- `SessionSnapshot`：`session_id`、status、slot、active run、queued runs、timeline cursor。timeline cursor 使用全局 `event_sequence` cursor；session-local cursor 只能作为 read model 优化，不能替代全局 cursor。
- `RunSnapshot`：`run_id`、`session_id`、status、current attempt、terminal result summary、event_sequence cursor、source_run_id?、source_run_relation?、outbox summary。
- `FollowupSnapshot`：accepted input ref、behavior、`accepted_run_id`、`accepted_run_status`、command commit event sequence / durable read watermark。`accepted_run_status` 使用公共 `RunStatus`，表达 command commit 后该 Run 的 durable 状态；该 watermark 不得被解释为 `watch_session_events` 的 cursor，因为 session live watch 不接收 cursor。`submit_followup(queue)` 有 active / start-blocking Run 时通常为 `QUEUED`，无 active / start-blocking Run 时为 `ACCEPTED`，随后由 scheduler / pre-start governance 推进到 `RUNNING` 或 terminal。`queued_run_id` 不进入普通 Service-facing 主 contract；如内部或 diagnostic view 保留，只能作为派生可选字段表达真正处于 `QUEUED` 的 Run，不能承载 accepted / running Run id，也不能替代 `accepted_run_id`。steer 分支可携带 `target_run_id?`，但 Phase 4 steer 返回 `unsupported_operation`，不会产生 accepted steer snapshot。
- `PurgeSessionResult`：`session_id`、purged marker、purge tombstone ref、deleted counts / digest。
- `HostEvent`：session live watch 的 Service-facing typed event。它由 committed EventLog / Host ingest result 派生，不能是 raw `EngineEvent` passthrough；terminal HostEvent 必须 inline typed terminal / final answer display view。
- `HostEventView`：EventLog row 的 Host 内部薄读模型 / diagnostic DTO，主要用于内部 run-scoped EventLog 补读、diagnostic / detail / debug / drill-down、测试局部断言，字段只包含 event identity、class/type、scope 与 payload ref / digest；不从 `dayu.host` Service-facing public namespace 导出。
- session live watch：`watch_session_events(session_id) -> AsyncIterator[HostEvent]`，返回 typed `HostEvent` 异步流，必须保留全局 `event_sequence` ordering truth。只有内部 run-level EventLog 补读接收 cursor；普通 Service-facing live watch 不接收 cursor。`HostEventStream` 若在代码中保留，只能作为内部实现或类型别名表达 async event iterator，不得成为需要 Service 理解的 context manager / subscription handle。

公共错误分类至少包括：

- `not_found`
- `invalid_state`
- `conflict`
- `idempotency_conflict`
- `permission_denied`
- `unsupported_operation`
- `internal_error`

错误分类语义：

- `conflict`：当前 Host 状态与请求前置条件冲突，例如 active Run 存在且 policy 拒绝排队。
- `idempotency_conflict`：同一幂等键已绑定到不同语义输入或不同目标对象。
- `invalid_state`：目标对象存在，但该状态下不允许此操作。
- `permission_denied`：上层传入的 authorization claims 不满足 Host policy。
- `unsupported_operation`：public request / response envelope 已冻结，但完整语义由后续 phase 落地；它不表达目标对象状态错误，也不能伪装成 `invalid_state`。

`HostApiError` 必须是受限 typed contract：`code`、`message`、`retryable` 与 `detail?`。`detail` 只能是 Host 公共 API 中显式定义的 detail union 成员，禁止无结构 `extra` / `payload` / `metadata` god bag。第一版至少包含：

```text
SteerConflictDetail:
  target_run_id
  target_run_status?
  current_active_run_id?
  current_active_run_status?
```

`SteerConflictDetail` 只携带足以解释 steer precondition 失败的 Run id 与状态摘要，不嵌入完整 `RunSnapshot`，不暴露 Host durable row。后续新增错误 detail 时必须新增具体 typed detail，不得把显式参数塞进无结构 payload。

内部 run-scoped EventLog 补读从 EventLog `event_sequence` cursor 读取，不触发新执行。Phase 4 既有 cursor contract 在 P10.5 后降为内部 diagnostic / detail read path：

- 全局 EventLog `event_sequence` 是唯一 cursor truth；projection checkpoint、session-local cursor、client sequence 或内存订阅位置都不能替代它。
- internal signature 包含可选 `limit`；未传时使用 Host read 默认 limit，超过 Host read 最大 limit 时返回 `invalid_state` 或等价 validation error，不静默无上限扫描。默认值和最大值必须集中定义，不能在实现中散落魔法数字。
- 内部 run-scoped EventLog 补读只返回与目标 `run_id` 相关的 `HostEventView`；需要 Service-facing session timeline 时走 `get_session` snapshot、`watch_session_events` 或后续 read-model API，不把 session projection 当作本接口真源。
- filtering 发生在 EventLog read path 上，`next_cursor` 以本次已经扫描过的最大全局 `event_sequence` 为准；即使过滤后结果为空，只要扫描推进，`next_cursor` 也必须前进，避免重连时重复扫描同一窗口。
- 如果没有扫描到任何大于 cursor 的 EventLog row，返回空 events，`next_cursor` 等于输入 cursor。
- `HostEventView` 是 EventLog row 的内部视图映射：携带 `event_id`、`event_sequence`、event type / class、`run_id`、`session_id?`、payload ref / digest 与必要 summary；不得暴露 durable row 私有列，也不得从 projection 派生新的事实。`HostEventView` 不承担 Service-facing live watch display payload；session live watch 必须产出 typed `HostEvent`。
- Phase 4 不引入 projection truth；Phase 8 可以基于同一 cursor contract 建 projection / read model，但不能改变内部补读路径的 truth 来源。

## 12. Follow-up 与 Steer

运行中的 Session 可能收到新的用户输入。

聊天界面的普通 prompt 入口统一是 `submit_followup`。UI / Service 不应先读取 active Run 再决定调用 `start_run` 还是 `submit_followup`；调用方表达用户意图，Host 在 admission transaction 内决定该输入排队、立即启动或作为 steer 被接受。

`queue` 语义：

- `submit_followup(queue)` 必须由 Host 在同一个 admission transaction 内吸收 active Run 竞态。
- 当前 Session 有 active / start-blocking Run 时，follow-up 输入排队为后续 Run 的输入，不打断当前 active Run。
- 当前 Session 没有 active / start-blocking Run 时，follow-up 创建 `ACCEPTED` Run；execution target 通过 Host policy 归一化并持久化，随后由 scheduler / pre-start governance 启动。
- 普通多轮 follow-up 使用当前 Host handle 的 default execution baseline，除非 `SubmitFollowupRequest` 显式携带 typed `runner_spec`、`runner_options` 或 `agent_policy` override。`SubmitFollowupRequest` 不携带 per-run target / profile id；每轮可变项第一版通过 typed `system_prompt`、`user_prompt`、`tool_names` 与可选 typed execution override 对象表达。
- 排队输入使用 `(session_id, client_request_id)` 幂等。
- queue follow-up 的 public result 必须使用 `accepted_run_id` + `accepted_run_status` + command commit event sequence / durable read watermark 表达被接受的新 Run。active / start-blocking Run 存在时通常返回 `accepted_run_status=QUEUED`；无 active / start-blocking Run 时返回 `accepted_run_status=ACCEPTED`。调用方不应根据 submit 返回值推断 Engine 已开始执行；是否进入 `RUNNING` / terminal 必须通过 `watch_session_events(...)` 或 `get_run(...)` 观察。`watch_session_events` 没有 cursor；这里的 watermark 只用于解释 command commit 后的 durable 读取位置。`queued_run_id` 不作为普通 Service-facing contract 字段；若为兼容内部 diagnostic 暂留，也不能承载 accepted / running Run id。
- `submit_followup(queue)` 的 `invalid_state` / `conflict` 不应表示 active Run 竞态；它应表示 Session closed、幂等冲突、权限不满足、输入不合法等真实错误。

`steer` 语义：

Phase 4 只冻结 `submit_followup(steer)` 的 public envelope、request validation、错误码与 typed detail contract，不实现 Attempt switching。Phase 4 public facade 在 steer 路径返回 `unsupported_operation`，`retryable=false`；完整 `RUNNING` / `WAITING` steer 语义由后续 steer / dispatch / wait owner 落地。以下完整语义是后续 owner 的目标设计，不是 Phase 4 implementation scope。

- steer 是对当前 active Run 的控制输入，不创建并列新 Run。
- steer request 必须携带 `target_run_id` 或等价 expected active Run precondition。
- steer 不能像 queue 一样吸收 active Run 竞态；它必须作用于调用方指定的目标 Run。
- Host 只允许 steer 调用方指定的目标 Run；如果当前 active Run 已切换，Host 不得隐式 steer 新 active Run。
- 调用方可见语义是：把用户输入追加到当前 active Run，用于重定向正在进行的工作。
- Host 对当前 active Attempt 发起受治理的停止请求，并记录 steer input canonical fact。
- 当前 Attempt 收口后，Host 为同一个 Run 创建新 Attempt 和新 `execution_id`。
- Host 基于 EventLog canonical facts 重建完整 `AgentRunRequest.messages`，其中包含已接受工具事实、已确认输出边界和 steer 输入。
- Engine 只看到新的 `AgentRunRequest`；Engine 不理解 steer，不恢复旧 Agent / Runner。

`RUNNING` Run steer 路径：

```text
user submits follow-up with behavior=steer
  -> Host validates target_run_id is the current active Run
  -> Host appends STEER_REQUESTED
  -> Host requests current attempt stop through cancellation source
  -> current Attempt closes as STEERED or terminal race result
  -> Host appends RUN_STARTED(start_reason=steer)
  -> Host creates new Attempt for the same Run with new execution_id
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds messages from EventLog canonical facts + steer input
  -> commit
  -> Host dispatches through LocalProxy / RemoteProxy
```

`WAITING` Run steer 路径：

```text
user submits follow-up with behavior=steer
  -> Host validates target_run_id is the current WAITING active Run
  -> Host appends STEER_REQUESTED
  -> Host marks active wait record cancelled(reason=steered) in the same transaction
  -> Host appends RUN_STARTED(start_reason=steer)
  -> late wait result can only enter diagnostic / tool trace
  -> old Attempt remains SUSPENDED
  -> Host creates new Attempt(status=STARTING) for the same Run
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds messages from EventLog canonical facts + steer input
  -> commit
  -> Host dispatches through LocalProxy / RemoteProxy after commit
```

`WAITING` steer 不新增 wait record 状态。旧 Attempt 保持 `SUSPENDED`，不改写为 `STEERED`，因为它已经因 awaiting 正常 suspended。

steerable Run 状态只有 `RUNNING` 与 `WAITING`。`CANCELLING`、`RECOVERING` 和所有 terminal 状态都不可 steer。

调用方错误处理语义：

- 没有 active Run：返回 `invalid_state`；聊天 UI 可用同一条输入重新调用 `submit_followup(queue)`。
- `target_run_id` 不是当前 active Run：返回 `conflict`，错误响应应包含当前 active Run 与目标 Run 的状态摘要。
- 目标 Run 已 terminal：返回 `invalid_state`；聊天 UI 可用同一条输入重新调用 `submit_followup(queue)`，控制型 UI 可以只提示用户 steer 已失效。
- 目标 Run 是当前 active Run 但状态不可 steer：返回 `invalid_state`；调用方可选择 cancel、queue 或稍后重试。

Host 不自动把 steer 降级成 queue / replay；这些是 UI / Service 的显式策略。

terminal / steer 竞态规则：

- Run terminal fact 已提交时，steer 不能改写 terminal；该输入必须按调用方 policy 降级为 queued follow-up / new Run，或返回 `invalid_state`。
- Host 已 append `STEER_REQUESTED` 但旧 Attempt 先提交 terminal 时，terminal 优先；Host 记录 `STEER_LOST` diagnostic / projection_signal，steer input 不进入已 terminal Run 的 messages。
- `STEER_LOST` 至少包含原 `STEER_REQUESTED` event ref、目标 `run_id`、赢得竞态的 terminal event ref、reason code 和调用方可见状态提示。它不是 canonical fact，不驱动 recovery、memory、resume 或 Run 状态迁移。
- Host 已成功将旧 Attempt 收口为 `STEERED` 时，后续旧 `execution_id` 的 terminal 事件视为迟到事件，只能进入诊断 / trace。
- steer 不绕过同一 Session active Run admission；它只是同一 Run 内 Attempt 切换。

取消后编辑再发送：

- 已 accepted 的用户输入是 `USER_INPUT_ACCEPTED` canonical fact，不支持原地修改、覆盖或删除。
- 用户在 final answer 返回前取消 prompt A、编辑后发送 prompt B 时，Host 真源必须保留两条输入事实：prompt A 对应 Run A 并最终 `CANCELLED`，prompt B 对应新的 Run B。
- 聊天 UI 可以在 Session timeline projection 中折叠或弱化显示已取消的 prompt A，但这不能改变 EventLog、RunInputBuilder、audit、memory 或 recovery 事实。
- prompt B 必须通过 `submit_followup(queue)` 进入 Host；聊天界面默认使用 `submit_followup(queue)`。

## 13. EventLog

EventLog 是 Host 的 append-only event ledger。`event_class=canonical_fact` 的子集是 Host canonical fact source；preview / diagnostic / projection signal 可以为了 Host event stream 或诊断进入同一 cursor 空间，但不能成为治理真源。

EventLog 不变量：

- 除 `purge_session` 的 destructive retention 例外外，EventLog 只 append，不 update，不 delete。
- `purge_session` 是第一版唯一 destructive retention 例外。它只允许在严格前置条件成立后删除目标 Session 的可恢复事实，并必须保留 purge tombstone；该 tombstone 不参与 resume、retry、replay、memory 或 RunInputBuilder。
- 是否挂载 Observer / Sink 不能改变 EventLog 行为。
- 同一输入在同一 Host 状态下，append 成功条件、事件顺序、状态迁移、恢复语义和调用方可见结果必须一致。
- Projection / audit / memory / timeline / usage / tool trace 不得 append 或 update EventLog。
- preview / reasoning / display-only event 可以用于 Host event stream，但不能成为 memory / audit / resume 真源。
- 每条 event 必须显式标注 `event_class`；缺省不得被解释为 canonical fact。
- 只有 `canonical_fact` 可以驱动 Run / Attempt 状态迁移、recovery、resume、memory verified inputs、audit 责任主链和 outbox terminal delivery intent。
- `preview` 可以按 `event_sequence` 补读以恢复 UI 体验，但 preview 丢失、压缩或清理不得影响 Run terminal、messages rebuild 或 memory。
- `diagnostic` 可以用于排错和 trace，但不得让 late remote event、protocol error 或 projection failure 变成业务事实。
- `projection_signal` 只能由 Host ingest / Host policy 写入，用于 usage、tool trace 或其它 projection 输入；Sink 不得把自己的输出再写回 EventLog 形成反馈环。

事件形态：

```text
event_log
  event_id
  event_sequence
  event_class: canonical_fact | preview | diagnostic | projection_signal
  session_id
  run_id?
  attempt_id?
  execution_id?
  event_type
  occurred_at
  actor?
  source?
  client_request_id?
  idempotency_key?
  policy_decision?
  reason?
  payload_json
  payload_ref?
  payload_digest?
```

排序与幂等：

- `event_sequence` 是 SQLite 分配的全局单调 INTEGER 序列，是所有 Host event stream cursor、projection checkpoint、outbox dispatch、audit replay 和 recovery scan 的主 cursor。它只能由 Host durable store 在 append transaction 中分配；远端 sequence、client request order、projection checkpoint 或内存 counter 都不能替代它。
- `event_id` 是 Host ledger event identity，使用 TEXT 存储并全局唯一。所有 `event_class` 都必须有 ledger identity；`canonical_fact` 的 `event_id` 同时是 canonical event identity。重复 ingest 同一 canonical `event_id` 必须返回已接受结果，不得 append 第二条 canonical event。
- EventLog schema 必须显式约束 `event_id` 全局唯一、`event_sequence` 全局单调唯一、`event_class` 必填、`event_type` 必填。`payload_json` 为 canonical JSON TEXT；大 payload 只通过 `payload_ref` / descriptor 与 `payload_digest` 引用。
- client operation id、remote event identity、canonical event identity 必须分层。`client_request_id` 标识客户端 API 操作幂等；remote event identity 标识 Proxy / Stub / EngineWorker 回传来源事件；canonical `event_id` 标识 Host EventLog 中单条 canonical fact。
- 一个 remote event 如果映射为多个 canonical events，每个 canonical event 都必须有独立、稳定、可去重的 identity，例如由 `execution_id`、remote event identity、canonical event type 与 sub-index 派生。Host-generated state transition event 也必须有明确幂等来源，不能混用 `client_request_id` 或 remote event identity。
- `run_sequence` / `session_sequence` 可作为 read model 优化，但不得替代全局 `event_sequence`。
- 内部 run-scoped EventLog 补读使用全局 `event_sequence` cursor 过滤目标 run，保证诊断补读稳定。空结果也必须返回稳定 `next_cursor`：扫描窗口有推进时使用本次扫描过的最大全局 sequence，没有新 row 时保持输入 cursor。Phase 4 不引入 projection cursor truth；P10.5 后该路径不作为普通 Service-facing public contract。
- 远端事件携带的 sequence 只用于 remote-side ordering / diagnostics；是否作为 `canonical_fact` 进入 EventLog 由 Host 决定，并由 Host 重新分配 `event_sequence`。

idempotency record primitive：

- Host durable store 提供通用幂等记录 primitive，但具体 operation 的幂等范围由对应 request / accept path 定义，不由 `HostCallContext` 统一定义。
- 幂等记录以 `(scope_kind, scope_id, idempotency_key)` 唯一绑定一次语义输入。`scope_kind` 表达 operation 类别或 accept path 类别；`scope_id` 表达 session / run / wait / attempt / tool call 等作用域；`idempotency_key` 是调用方或 accept path 提供或确定性派生的 key。
- 每条幂等记录必须保存 `semantic_input_digest`、`result_kind`、`result_ref`，并在适用时保存 `created_event_id` / `created_event_sequence`。重复请求命中同一 scope + key 且 semantic digest 相同，必须返回既有 accepted result ref；同一 scope + key 但 semantic digest 不同，必须返回 `idempotency_conflict`。
- 幂等冲突是业务前置条件失败，不属于 SQLite busy / locked retry；不得通过重试、覆盖或追加第二个对象消解。

Event ingest semantic contract：

```text
event source
  -> validate source identity
  -> validate run_id / attempt_id / execution_id when attempt-scoped
  -> derive canonical event identity
  -> check idempotency
  -> classify as canonical / preview / projection input / diagnostic / rejected
  -> append accepted EventLog row inside Host transaction
  -> update Run / Attempt indexes in the same transaction when event_class=canonical_fact has state side effects
  -> notify projections after commit
```

canonical ingest 必须满足：

- stale `execution_id` 不得作为 `canonical_fact` 进入 EventLog。
- duplicate canonical identity 返回既有 accepted event，不追加第二条。
- out-of-order remote event 只能在不破坏 Host 状态机时被接受；否则进入 diagnostic 或 rejected。
- terminal event 一旦 accepted，同一 Run 的后续 steer / cancel / late terminal 不能改写 terminal fact。
- preview event 可以进入 Host event stream，但不能让 RunResult、memory、audit 或 recovery 依赖它。

### 13.1 Payload 存储

- EventLog row 不应内嵌大 payload；canonical event 必须记录 payload ref / descriptor 与 digest，或其它可校验 ref。
- 第一版使用 SQLite payload table 作为默认 durable payload store；小型 / 中型可恢复 payload 与引用它的 EventLog append 在同一 SQLite transaction 内提交。
- Phase 2 payload foundation 支持两类最小 descriptor：`sqlite_payload` 与本地 `artifact_ref`。`sqlite_payload` 指向 SQLite payload table 中的 canonical JSON / bytes payload；`artifact_ref` 指向 Host composition root 注入的本地 artifact root 下的 durable artifact。
- Host composition root 必须显式注入 `payload_inline_threshold_bytes` 与 artifact root。默认值只能在 construction root 应用，不能通过模块级全局变量、隐式环境变量或硬编码路径取得。
- 小于等于 `payload_inline_threshold_bytes` 的可恢复 payload 可以作为 `sqlite_payload` 写入 SQLite payload table，并与引用它的 EventLog append 在同一 SQLite transaction 内提交。
- `TOOL_RESULT_ACCEPTED` 的完整 accepted payload 是否可内联，由 ToolRuntime accept barrier 在 append transaction 内根据 durable policy 判断；超过阈值时必须写 SQLite payload descriptor，并让 EventLog hot payload 只保留 evidence envelope、status、metadata 与可校验 payload ref。工具实现、Service 或 smoke 脚本不得自行承担该冷热分离判断。
- 超过 Host policy 阈值的大工具结果、财报 chunk、binary、长网页正文、provider raw response、完整 prompt / messages、trace 明细必须外移到 artifact / blob / tool trace / 领域仓储，并在 artifact durable 且 digest verified 后才 append EventLog `canonical_fact`。
- 本地 `artifact_ref` 的最小写入顺序是：先写入 artifact root 下的临时文件，完成 flush / fsync 或等价 durable 写入，计算并校验 digest，再通过 atomic rename 发布到最终相对路径，最后在 SQLite transaction 中写 payload descriptor 与 EventLog row。EventLog 不得引用未 durable、未 digest verified 或位于 artifact root 外的临时路径。
- SQLite transaction 无法原子覆盖外部文件系统写入；因此 artifact 发布必须先于 EventLog canonical append。若 SQLite transaction 后续失败，已发布但未被 descriptor 引用的 artifact 只能作为后续 cleanup / diagnostics 处理，不能被当作 accepted fact。
- `payload_digest`、normalized args digest、result digest 和 evidence digest 必须基于确定性序列化 / canonicalization 计算；同一语义 payload 不能因 JSON key 顺序或无关默认值产生不同 digest。
- 会参与 resume、memory、audit、`fetch_more`、replay 的 payload / ref / descriptor 缺失或 digest 不匹配时，Host 不能把该 fact 当作 accepted fact 使用。
- preview / diagnostic / display-only payload 可以降级丢失；其缺失只能影响展示、深度审计或 trace 细节，不能伪装成恢复必要事实。
- 对财报证据，EventLog 记录 evidence anchor / ref / digest，不复制整份材料。

### 13.2 Canonical Event 最小集合

第一版 canonical events 至少包括：

```text
SESSION_CREATED
SESSION_CLOSED

RUN_ACCEPTED
RUN_QUEUED
RUN_STARTED
RUN_WAITING
RUN_CANCELLING
RUN_RECOVERING
RUN_SUCCEEDED
RUN_FAILED
RUN_CANCELLED
RUN_LOST

ATTEMPT_STARTED
ATTEMPT_RUNNING
ATTEMPT_SUCCEEDED
ATTEMPT_FAILED
ATTEMPT_CANCELLED
ATTEMPT_SUSPENDED
ATTEMPT_STEERED
ATTEMPT_LOST

USER_INPUT_ACCEPTED
STEER_REQUESTED
CANCEL_REQUESTED
RESUME_REQUESTED
RETRY_REQUESTED
REPLAY_REQUESTED

TOOL_CALL_REQUESTED
TOOL_CALL_GOVERNED
TOOL_RESULT_ACCEPTED
TOOL_AWAITING
GUIDANCE_INSERTED
CONTEXT_COMPACTION_REQUESTED
CONTEXT_COMPACTED
CONTEXT_COMPACTION_FAILED
PROVIDER_PROTOCOL_ERROR
```

Terminal event 使用具体终态 event，不使用模糊 `RUN_TERMINAL` / `ATTEMPT_TERMINAL` 作为唯一类型。

模糊的“attempt event accepted”不作为第一版 canonical event。EngineEvent ingest 必须落到具体业务事实、preview / diagnostic，或被拒绝；不得用模糊“已接受某事件”掩盖事实类型。

### 13.3 Canonical Event Contract Matrix

canonical event contract 必须转成 typed dataclass / enum / validation tests。架构级最小矩阵如下：

| Event class | 必需 scope | 必需 payload | 状态副作用 | Resume / memory | Audit / Host event stream |
| --- | --- | --- | --- | --- | --- |
| `SESSION_CREATED` / `SESSION_CLOSED` | `session_id` | slot / actor / reason | 更新 Session status | memory 不消费 | audit yes / timeline emit |
| `USER_INPUT_ACCEPTED` | `session_id`、`run_id`、`client_request_id` | user input ref / digest / display text | 创建或关联 Run 输入 | resume yes / memory raw turn | audit yes / Host event stream emit |
| `RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` | `session_id`、`run_id` | queue policy / execution target / `start_reason` when started | 更新 Run status / queue index | resume yes | audit yes / Host event stream emit |
| `RUN_WAITING` / `RUN_CANCELLING` / `RUN_RECOVERING` | `session_id`、`run_id` | wait_id / cancel reason / recovery reason | 更新 Run status | resume yes when semantically needed | audit yes / Host event stream emit |
| `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` | `session_id`、`run_id`、terminal attempt refs | terminal summary / error / reason / result ref | 更新 Run terminal status | resume 只消费有语义必要的终态；memory 消费 assistant conclusion 和工具事实 | audit yes / Host event stream emit / success 触发 outbox |
| `ATTEMPT_STARTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | worker target / dispatch record ref | 创建 Attempt row，status=`STARTING` | resume 不消费，除非用于诊断 | audit yes / Host event stream optional |
| `ATTEMPT_RUNNING` | `session_id`、`run_id`、`attempt_id`、`execution_id` | worker accepted / dispatch accepted info | Attempt status=`RUNNING` | resume 不消费，除非用于诊断 | audit yes / Host event stream optional |
| `ATTEMPT_SUCCEEDED` / `ATTEMPT_FAILED` / `ATTEMPT_CANCELLED` / `ATTEMPT_SUSPENDED` / `ATTEMPT_STEERED` / `ATTEMPT_LOST` | `session_id`、`run_id`、`attempt_id`、`execution_id` | terminal reason / error / wait_id | 关闭 Attempt | resume 按需消费 suspended / lost reason | audit yes / Host event stream emit |
| `STEER_REQUESTED` / `CANCEL_REQUESTED` / `RESUME_REQUESTED` / `RETRY_REQUESTED` / `REPLAY_REQUESTED` | `session_id`、`run_id`、operation idempotency key | control input / reason / policy / source_run_id when retry or replay | 触发对应状态机；retry / replay 创建关联新 Run，不重开源 Run | 改变模型语义时进入 messages | audit yes / Host event stream emit |
| `TOOL_CALL_REQUESTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | tool_call_id / tool name / normalized args digest | 记录工具调用 intent | accepted into model history 时 resume 消费 | audit 是 / tool trace 是 |
| `TOOL_CALL_GOVERNED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | policy decision / duplicate key / action | 不直接改 Run；可触发 guidance / hard stop | action 影响模型继续时进入 messages | audit 是 / tool trace 是 |
| `TOOL_RESULT_ACCEPTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | result ref / digest / evidence anchors / status；wait terminal result 通过 wait-specific fields 表达来源与状态 | 记录工具事实；P1-P7 accepted waiting terminal result 不另建 `TOOL_TERMINAL_RESULT` canonical fact | resume 是 / memory 工具事实 | audit 是 / tool trace 是 |
| `TOOL_AWAITING` | `session_id`、`run_id`、`attempt_id`、`execution_id` | wait_id / await_spec / external_job_id | 与 `RUN_WAITING`、`ATTEMPT_SUSPENDED` 同事务创建 wait record；Run -> `WAITING`；Attempt -> `SUSPENDED` | resume 是 | audit 是 / tool trace 是 |
| `GUIDANCE_INSERTED` | `session_id`、`run_id` | guidance text / source policy / reason | 不直接改 terminal；影响下一 Attempt messages | 插入 messages 时 resume 消费 | audit yes / Host event stream emit |
| `CONTEXT_COMPACTION_REQUESTED` | `session_id`、`run_id`；`trigger_source=reactive` 时必须有 `attempt_id`、`execution_id`；`trigger_source=proactive` 时可以没有 | trigger source / budget reason / provider error refs / snapshot refs | 触发 context governance；proactive path 是 pre-dispatch input governance；reactive path 可关闭当前 Attempt 并让 Run -> `RECOVERING` | resume 是；memory projection 按需消费 | audit yes / trace 是 |
| `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` | `session_id`、`run_id` | compact artifact ref / episode summary candidate / pinned state patch candidate / preserved fact refs / dropped reason / quality check / failure reason | compacted 后允许创建新 Attempt；failed 后按 policy 失败或保持 recoverable | resume 是；memory projection 按 policy 消费 accepted compact output | audit yes / trace 是 |
| `PROVIDER_PROTOCOL_ERROR` | `session_id`、`run_id`、`attempt_id`、`execution_id` | provider / error code / request ref | Attempt failure or retry input | retry 需要时 resume 消费 | audit yes / Host event stream emit |

canonical event 的 required fields 不能被塞进无结构 `metadata`；`metadata` 只能承载不参与状态机、幂等、恢复和审计主链的附加说明。

control event 的 `run_id` 绑定规则：

- `STEER_REQUESTED` 的 `run_id` 是被 steer 的目标 Run。
- `submit_followup(queue)` 不引入独立 `FOLLOWUP_QUEUED` canonical event；它的 canonical 表达是 `USER_INPUT_ACCEPTED` 加 `RUN_ACCEPTED`，并在命中 active / start-blocking Run 时追加 `RUN_QUEUED`。`RUN_STARTED` 由后续 scheduler / pre-start governance 追加，不由 submit command 直接追加。
- `RETRY_REQUESTED` 与 `REPLAY_REQUESTED` 的 `run_id` 是源 Run；关联的新 Run 必须通过后续 `RUN_ACCEPTED` 的 `source_run_id` / `source_run_relation` 或等价 typed payload 表达。
- `RESUME_REQUESTED` 的 `run_id` 是从 `WAITING` / `RECOVERING` 继续的同一 Run。
- `CANCEL_REQUESTED` 的 `run_id` 是被取消的 Run。

### 13.4 EngineEvent 映射

EngineEvent 到 Host EventLog 的映射原则：

- 参与恢复、resume、memory、audit、governance 的 EngineEvent 映射为 canonical event。
- 只服务 UI 流式体验的 delta 映射为 preview event，不进入 canonical projection。
- Host 可以把多个 EngineEvent 聚合成一个 canonical fact，但不得丢失恢复必须的信息。
- 工具事实 canonical owner 是 ToolRuntime Host accept path。EngineEvent ingest 不得为同一工具 outcome 追加第二条工具 canonical fact；描述已 accepted 工具结果的 EngineEvent 必须携带 accepted event refs / accepted tool fact ids，并只能映射为 preview、diagnostic、trace 或 idempotent no-op。

默认映射：

```text
iteration_started              -> preview
content_delta                  -> preview
reasoning_delta                -> preview
content_completed              -> preview
tool_call_delta                -> preview
tool_calls_batch_ready         -> preview or diagnostic
tool_call_requested            -> TOOL_CALL_REQUESTED
ToolRuntime policy decision     -> TOOL_CALL_GOVERNED when decision affects execution / guidance / audit / duplicate handling
tool_result_accepted           -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
tool_calls_batch_done          -> preview or diagnostic
tool_awaiting                  -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
context_compaction_requested   -> CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive); must include attempt_id + execution_id
usage_reported                 -> usage projection input; canonical only if needed for audit policy
provider_protocol_error        -> PROVIDER_PROTOCOL_ERROR
iteration_completed            -> preview or diagnostic
final_answer                   -> RUN_SUCCEEDED + ATTEMPT_SUCCEEDED
run_suspended                  -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
run_cancelled                  -> RUN_CANCELLED + ATTEMPT_CANCELLED
run_failed                     -> ATTEMPT_FAILED + (RUN_FAILED or RUN_RECOVERING by Host policy); context_compaction_required 在可恢复时进入 RUN_RECOVERING + new Attempt
```

该映射是规范性边界；实现必须转成 typed code 和 tests，不得重新发明 canonical / preview 边界。

## 14. Observer / Sink / Projection

Observer / Sink 只消费已提交 EventLog，用于派生 read model 或外部投递。

基本路径：

```text
Host event ingest
  -> validate ids / attempt identity / idempotency key
  -> durable transaction:
       append accepted EventLog row
       assign global event_sequence
       update required Host state indexes for canonical facts
       optionally record projection wakeup / outbox marker
  -> committed event notification
  -> Observer / Sink dispatch
  -> sink-specific checkpoint / retry / replay
```

Sink semantic contract：

- Sink 的输入是 committed EventLog event，不是事务中的临时状态。
- Sink 必须按 `event_sequence` checkpoint 追平，并按 canonical `event_id` 幂等消费。
- Sink 必须是幂等消费者；重复消费同一 canonical `event_id` 不得产生重复副作用或违反投递语义。
- Sink 必须声明消费哪些 `event_class` / `event_type`；默认只消费 `canonical_fact`。
- 每个 Sink 必须有自己的 typed consumer contract，明确输入 event 类型、payload view、checkpoint、幂等键、失败处理和输出 projection；不得让所有 Sink 共享一个无结构 Event payload。
- Sink 可以维护自己的 projection 表、work queue 或冷数据文件，但不能写 Host governance truth。
- Sink lag 只影响派生视图新鲜度，不影响 Run admission、cancel、resume、terminal 收口。
- Sink 失败只能更新 sink-local retry / error state，不能回滚 EventLog，也不能改变 Run / Attempt 状态。
- Audit、usage、tool trace、stream fanout、memory、outbox 等 sink 只依赖 committed EventLog 与各自 typed consumer contract；它们消费 recovery 相关 event 时不读取 Recovery 内部状态。Recovery 产生的 `ATTEMPT_LOST`、`RUN_RECOVERING`、`RUN_STARTED(start_reason=recovery)` 等只是普通 committed events，sink 不得对 Recovery 内部状态形成反向依赖。

第一批 sink：

- audit projection。
- usage projection。
- tool trace projection。
- stream fanout。
- memory projection。
- outbox projection。

### 14.1 Tool Trace Hot / Cold Storage

Tool trace 是 EventLog 派生 projection，不是 Host durable truth。它必须支持冷热数据分离，避免把调试明细、长工具参数、长结果摘要和归档流混进 EventLog 或热查询表。

存储口径：

- 热数据使用结构化 JSON projection。热数据保存近期、可查询、可展示、可关联的 tool trace summary，例如 tool_call_id、tool name、normalized args digest、result digest、evidence anchors、truncate info、await info、policy decision、error code、duration、attempt refs。
- 冷数据使用 append-only JSONL。冷数据保存可归档、可批处理、可离线审计的 trace detail，例如长参数摘要、长结果摘要、provider / tool raw diagnostic refs、截断诊断、重复治理上下文、等待 / 取消 / 超时细节。
- JSON 与 JSONL 都必须携带 `event_id` / `event_sequence`、`session_id`、`run_id`、`attempt_id`、`execution_id`、operation context refs / digest 和必要 digest / ref，保证能从 EventLog 对齐，并能回答“这是什么业务的什么操作产生的 trace”。
- 热数据可以按 retention policy 淘汰或压缩；冷 JSONL 可以按 run / 日期 / workspace 分片归档。
- EventLog 对 tool trace 只记录必要 event、ref 与 digest；不得把 JSONL 当作恢复、resume、memory 或 Run 状态迁移真源。
- tool trace projection 损坏或缺失时，应能从 EventLog 与外移 payload ref 尽力重建热数据；冷 JSONL 丢失只能影响深度诊断和离线审计。

约束：

- Sink 不拥有 Session / Run / Attempt 状态。
- Sink 失败不能回滚 EventLog。
- Sink 按 `event_sequence` checkpoint 追平，并按 `event_id` 幂等消费。
- Sink 慢只能表现为 projection lag，不能拖慢 Host append、run admission、cancel、resume、terminal 收口。
- 第一版不引入重型消息系统；SQLite EventLog + projection checkpoint + 本地后台 worker / 任务循环足够表达可靠追平语义。
- Sink notification 只是一种 wakeup；正确性来自 EventLog replay + checkpoint，不来自内存通知是否送达。

## 15. Audit

Audit 不是事实真源；audit sink 消费 committed EventLog 生成 audit projection。

第一版 Audit 默认落地为 `LogAuditSink(JSONL)`：

- `LogAuditSink` 是 projection / sink，不是 Host truth。
- `LogAuditSink` 按 `event_sequence` checkpoint 消费 committed EventLog。
- `LogAuditSink` 写本地 append-only JSONL audit log file。
- audit log file 路径由 Host composition root 的 typed options 显式传入，可有默认值。
- `LogAuditSink` 写失败只更新 sink-local error / diagnostic / lag，不回滚 EventLog，不影响 Host command path。
- `NoopAuditSink` 只作为测试 / 开发显式配置；生产默认应使用 `LogAuditSink`。
- 第一版不做复杂 AuditPolicy 规则引擎，不做外部 audit 系统投递保证，不做 UI / Service 动态 audit 配置。

Host command path 不直接写 audit log file。它只负责在 EventLog canonical facts、policy decision refs 和 `HostCallContext` 中保留审计所需最小事实。UI / Service 只负责传入 `HostCallContext`，不传 audit 策略。

canonical event 必须携带足够 audit 可追溯字段：

- actor / principal。
- source / client。
- request id / client_request_id。
- operation context refs / digest。
- session_id / run_id / attempt_id / execution_id。
- policy decision。
- reason。
- payload ref / digest。

operation context 是 audit、tool trace、timeline 与 diagnostic 关联业务操作的共同索引。Host 只记录 UI / Service 已解析的 typed identifiers / refs / digest，不从 prompt 文本或无结构 metadata 推断业务对象。

Audit 重点记录治理动作和责任链：

- session / run 创建。
- cancel、steer、resume、replay。
- 工具调用。
- 外部材料访问。
- policy 允许 / 拒绝 / 截断 / 等待。
- 语义级重复工具调用治理：allow / reuse / hint / require_justification / hard_stop。
- evidence 纳入。
- 外部副作用 idempotency key。

`LogAuditSink` 每行至少记录：

- `event_sequence`
- `event_id`
- `event_type`
- `event_class`
- `occurred_at`
- `session_id`
- `run_id`
- `attempt_id`
- `execution_id`
- actor / principal
- source / client
- operation context refs / digest
- `client_request_id`
- policy decision ref / summary
- reason
- payload ref / digest

`LogAuditSink` 不写大 payload，不复制 tool trace 冷数据。工具执行细节、证据锚点、截断、等待、provider request id 等深诊断信息属于 tool trace；audit 只记录可关联 ref / digest。audit 与 tool trace 必须都能通过 operation context 回答“这是什么业务的什么操作产生的记录”。

`purge_session` 不删除已经写入的 append-only audit JSONL 记录。purge audit JSONL 记录 destructive 操作流水，至少应区分 `purge_started` 与 `purge_completed`：`purge_started` 表示 purge attempt 已发起，不能解释为完成；`purge_completed` 必须在 SQLite tombstone commit 成功后写入，并引用 tombstone id / digest。若 purge 失败，可以写入 `purge_failed` 记录失败阶段和原因。audit 查询 / analyze 工具必须能识别 purge audit lines，并以 SQLite tombstone 作为 purge 完成真源；只有 started 而没有 completed / tombstone 时，应提示该 Session 只有 purge attempt 或 incomplete purge，不得提示源 EventLog facts 已成功 purge。

audit projection 可以为了查询重组，但不能反向成为恢复、resume 或 memory 真源。

## 16. Read Model / Host Event Stream / Outbox

EventLog 是真源；Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 都是 read model 或 projection。

公共读取语义：

```text
get_run(run_id)
  -> RunSnapshot(status, terminal summary, active attempt, cursors)

watch_session_events(session_id)
  -> live Host event stream for a Session, ordered by EventLog event_sequence

internal stream_run_events(run_id, cursor, limit?)
  -> internal run-scoped diagnostic / detail / debug stream from EventLog event_sequence cursor

get_session(session_id)
  -> SessionSnapshot(session status, active run, queued runs, timeline summary)
```

边界：

- `RunResult` 是 Run 终态投影，不是事实真源。
- `Session timeline` 是 UI / read model，不是事实真源。
- Session timeline 必须能表达“已取消的用户输入”和后续新输入是两条不同 `USER_INPUT_ACCEPTED`。聊天 UI 可以折叠或弱化 cancelled input，但不能把新输入建模为旧输入的 edit。
- `watch_session_events` 是普通 Service-facing 官方事件入口：在线 / 已 attach 客户端通过 live watch 接收 attach 之后的 Session 事件；它不接收 cursor，不承担离线补读。
- internal `stream_run_events` 不触发新执行，只提供 Host 内部 run-scoped diagnostic / detail / debug / drill-down 读取，不进入普通 Service 多轮 recipe、public contract 或 smoke 主路径。
- 投影损坏或缺失时应能从 EventLog 重建。
- resume、memory、audit 责任链必须读取 EventLog canonical facts。

Outbox：

- Run terminal fact 提交后，final answer 已成为 Host 真源中的结果。
- 在线 / 已 attach 客户端的阅读路径是 Host event stream、Session timeline、RunSnapshot 或 read model；未 attach / 离线期间错过的 terminal/final answer 通知通过 Outbox terminal watermark / seen terminal ids 补读。P10.5 只冻结这一 attach / reconnect recipe 与 terminal identity / 去重边界，不实现 Outbox concrete read / drain API；Outbox projection、delivery queue、concrete read / drain API 与离线 terminal delivery smoke 归 Phase 13。
- Outbox 不是客户端阅读 final answer 的通用接口，也不是 UI read model。
- Outbox 是离线 / 外部投递路径的 durable terminal delivery queue，表达 terminal result 可投递 / 可通知的 durable item。
- Outbox 解决的问题是：离线客户端或外部渠道不需要回放中间过程，也不能丢 final answer / terminal notification。
- Outbox 不包含完整 run timeline，不补 preview / progress / reasoning / streaming content。
- 在线阅读路径和 Outbox 离线投递路径必须指向同一个 terminal identity。UI / Service 应使用 `terminal_event_id` / `event_sequence` / `run_id` 去重，不得用 final answer 文本内容去重。
- UI 本地聊天记录应保存已展示 terminal answer 的 terminal watermark，例如 `last_seen_terminal_event_sequence` 或 `seen_terminal_event_ids`。客户端重连时，Service / channel adapter 按该 watermark 从 Outbox 读取 terminal 增量；已展示过的 terminal item 不得作为新消息重复投递。
- Service 取得或重新打开 Session 后，必须把 Outbox terminal 增量补读和 session live watch attach 视为一个 attach / reconnect 协议。业务语义上先补离线 terminal，再接入 live watch；实现上可以先建立 `watch_session_events(session_id)` 再 drain Outbox，也可以先 drain Outbox 再打开 live watch，但必须依靠 `terminal_event_id` / `event_sequence` / `run_id` 去重，并证明两步之间没有漏投 terminal 的窗口。
- Outbox 只补未 attach / 离线期间的 terminal/final answer 通知，不补完整中间过程；reasoning delta、content delta、tool progress、preview 等在线过程事件只属于 session live watch / read model。
- Host 不负责 deliver to UI，不判断哪些客户端应该收到，不记录 GUI / CLI / WeChat / Web 的 channel 投递成功状态。
- Session 不持有唯一 default delivery target；HostCallContext 不包含 delivery target / delivery hint。
- 具体投递目标、投递成功状态、channel retry、WeChat / Web / notification binding 属于 Service / UI / channel adapter。
- 投递失败不能回滚 Run terminal。
- terminal transaction 不同步写 outbox 表；把 Run 终态提交和 outbox work queue 生成强绑定违反 Observer / Sink 边界。
- OutboxSink 按 `event_sequence` checkpoint 扫描 terminal EventLog facts，并 upsert outbox item。outbox 表是 projection / work queue，可由 EventLog 重建。
- optional outbox marker / notification 只是 wakeup；它丢失不得影响最终投递意图的派生。
- Outbox 必须具备幂等 item key、terminal event ref、result ref / digest、session_id、run_id、event_sequence 和 projection state。channel delivery state 不属于 Host truth。
- Outbox 不参与 resume、memory 事实重建或 Run 状态迁移。

阅读路径：

```text
Host EventLog
  -> Host event stream / Session timeline / RunSnapshot
      -> UI read path: GUI / Web / CLI / attached clients read here
      -> UI stores seen terminal watermark / terminal ids in local or Service state
```

OutboxSink 路径：

```text
OutboxSink checkpoint at event_sequence N
  -> scan terminal EventLog facts after N
  -> derive terminal delivery intent / notification item
  -> upsert outbox item by idempotency key
  -> advance checkpoint after projection commit
  -> Service / channel adapter consumes outbox item and owns channel delivery
```

outbox item idempotency key 必须由 terminal event identity、`run_id` 和 result digest 等稳定输入派生。重复扫描同一 terminal event 不得创建重复 outbox item。具体 hash 算法属于实现策略，但不得使用 final answer 文本内容作为去重主键。

离线补投推荐语义：

```text
UI restores local chat history
  -> reads last_seen_terminal_event_sequence or seen terminal_event_ids
  -> Service / channel adapter queries Outbox terminal items after terminal watermark
  -> returns only unseen final answer / terminal notification items
  -> UI upserts by terminal_event_id / run_id before display
  -> UI / Service advances seen terminal watermark after display or delivery ack
```

OutboxSink 只读 EventLog / Run durable truth，并写 outbox projection / work queue。它不能 append EventLog、不能更新 Run / Attempt，也不能改变 terminal 结果。

## 17. WorkerProxy / EngineWorker

无治理执行路径：

```text
Host -> Proxy / Stub -> EngineWorker -> Engine
```

治理路径：

```text
Host API
  -> Session / Run admission
  -> durable transaction: create Run / Attempt / initial EventLog fact
  -> Attempt execution context: attempt_id + execution_id + cancellation source
  -> WorkerProxy / RemoteStub
  -> EngineWorker -> Engine
  -> EngineEvent stream
  -> Host event ingest: validate run_id / attempt_id / execution_id
  -> durable EventLog append
  -> terminal transaction: append terminal event + close Attempt + update Run
  -> Host event stream / projection / result read model
```

Local / Remote topology：

```text
Host -> LocalProxy -> EngineWorker -> Engine
Host -> RemoteProxy -> RemoteStub -> EngineWorker -> Engine
```

Remote boundary：

- LocalProxy 是语义基准。
- RemoteProxy 是 transport substitution，不是治理 boundary。
- design 定义 remote semantic contract，不定义 wire protocol。
- RPC、ack frame、event replay、heartbeat、version negotiation、connection keepalive 是 Remote transport 细节；它们不得改变本节 remote semantic contract。
- `tool fact accepted ack` 是 ToolRuntime / EngineWorker 执行语义的一部分，不是 wire protocol 细节。LocalProxy 与 EngineWorker 之间也必须具备等价函数调用语义；RemoteProxy 只把该语义替换为远程传输。

远程执行不变量：

- Host 创建 Run、Attempt 与 `execution_id`。
- Host dispatch Attempt。
- RemoteStub / EngineWorker 只执行并回传带 `run_id`、`attempt_id`、`execution_id`、remote event id / remote ordering hint 的事件。
- Host 校验 `attempt_id + execution_id` 后决定是否 append EventLog `canonical_fact`。
- RemoteStub / EngineWorker 不 append EventLog，不关闭 Attempt，不更新 Run，不 takeover，不 resume。
- 迟到事件、重复事件或 `execution_id` 不匹配事件不能污染 EventLog `canonical_fact` 子集；最多进入诊断 / trace。
- Host 接受远端事件后重新分配 canonical `event_sequence`；remote ordering hint 不能成为 Host event stream cursor。
- cancel 由 Host 发起，通过 Proxy / Stub 传递到 EngineWorker 的 run-local cancellation token；远端不自行决定 Run 终态。
- Host 不保证 exactly-once 远程物理执行。dispatch 后、Host 确认前发生断连时，旧远端执行可能继续运行；Host 通过 `execution_id` 拒绝迟到事件，并依赖工具级 idempotency key / best-effort cancel 降低外部副作用风险。

LocalProxy / EngineWorker identity boundary：

- Engine 公共 `EngineEvent` 契约只表达 Engine run 内部事件，不提升为 Host Attempt identity carrier；不得为了 Phase 5 让 Engine 理解 Host `Attempt`、Host durable state、dispatch record 或 recovery policy。
- Host-owned LocalProxy / EngineWorker envelope 负责把一次 Engine run 绑定到 `session_id`、`run_id`、`attempt_id`、`execution_id`、dispatch record 和 cancellation source。Host ingest 只能接受来自该 envelope 的 scoped event；`attempt_id + execution_id` 校验发生在 Host ingest 边界。
- 本地执行路径中，EngineWorker 可以把 Engine 原始事件与 Host envelope 组合成 Host ingest candidate；该 candidate 不是 Engine 公共契约，不得反向污染 `dayu.engine.contracts`。
- RemoteProxy 后续必须复用同一 envelope 语义；wire protocol 可以改变传输形态，但不能把 `attempt_id + execution_id` 校验职责转交给 Engine 或 RemoteStub。

Worker dispatch semantic contract：

```text
Host transaction commits ATTEMPT_STARTED with status STARTING
  -> dispatch record status = pending
  -> Attempt Dispatch reads dispatch record
  -> Attempt Dispatch marks dispatch record waiting_for_lane when it starts waiting for configured LLM lane
  -> after lane acquired, open short Host transaction
       -> re-read Run / Attempt / dispatch record
       -> verify Attempt STARTING, Run dispatchable, execution_id matches, dispatch record waiting_for_lane or pending, no cancel / terminal committed
       -> if valid: update dispatch record status = dispatching, record dispatcher_instance_id / lane_name diagnostic refs, commit
       -> if invalid: commit nothing, release lane, do not call WorkerProxy
  -> WorkerProxy receives dispatch request with attempt snapshot
  -> EngineWorker accepts or rejects dispatch
  -> accepted: Host appends ATTEMPT_RUNNING
  -> rejected / startup timeout: Host closes Attempt through failure / lost path
  -> EngineWorker emits EngineEvent stream scoped by run_id / attempt_id / execution_id
  -> Host ingests events and owns all state transitions
```

LLM lane 控制资源容量，不控制 Session admission。acquire 不到 lane 时，Attempt 保持 `STARTING`，dispatch record 保持 `pending` 或 `waiting_for_lane`，不 append `ATTEMPT_RUNNING`，不启动 EngineWorker。Phase 5 必须把 `waiting_for_lane` 和 `dispatching` 纳入 dispatch record fresh schema 与 typed enum；这是 Host dispatch 诊断 / 重复派发抑制状态，不是 lease / fencing。lane acquire 成功后仍必须 recheck durable state，确认 Attempt 仍为 `STARTING`、Run 仍可派发、dispatch record 仍处于 `pending` 或 `waiting_for_lane`、`execution_id` 仍匹配且 cancel / terminal 没有抢先提交。recheck 成功必须先把 dispatch record 原子推进为 `dispatching`，再调用 WorkerProxy；recheck 失败必须 release lane，不得派发。

`dispatching` 与 `dispatcher_instance_id` 只用于本机调度诊断、重复派发抑制和 recovery 判断，不是 lease，不是 fencing token，不授权旧 Attempt takeover。lane token 也不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner；它只是本地或运行时资源 guard。Attempt terminal、dispatch 失败、Host cancel 或 supervisor shutdown 都必须 release / cancel 对应 lane wait 或 held token。

EngineEvent stream 非正常终止必须由 Host 收口：

```text
EngineEvent stream EOF / error / transport close / worker crash
  AND no terminal event accepted for active Attempt
  -> Host records diagnostic
  -> Host evaluates Attempt as failed / lost / recoverable according to policy
  -> Host must not leave Run indefinitely RUNNING solely waiting for restart scan
```

该规则不是 lease / fencing 系统，也不保证 exactly-once 远程物理执行。它只是 Host 对自己执行流异常终止的本地治理；旧远端 worker 后续迟到事件仍按 `execution_id` 拒绝进入 canonical facts。

dispatch record 已进入 `dispatching` 后，如果 WorkerProxy 调用失败、worker reject 或 startup timeout：

```text
dispatch record = dispatching
  -> release lane token
  -> append dispatch diagnostic
  -> Attempt -> FAILED or LOST by failure type
  -> Run -> FAILED / RECOVERING / LOST by Host policy and recoverability
```

Phase 5 本地执行的最小 terminal closeout policy：

| 场景 | Attempt 终态 | Run 终态 | recoverable | 最小诊断 / reason |
| --- | --- | --- | --- | --- |
| WorkerProxy 调用前 final pre-call recheck 发现 Attempt 不再是 `STARTING`、dispatch record 不再是 `dispatching` 或 cancel / terminal 已提交 | 不新增终态，由已提交事实决定 | 不新增终态，由已提交事实决定 | false | `dispatch_aborted_by_durable_recheck`，包含 dispatch record ref、attempt status、run status |
| WorkerProxy 调用异常、worker reject 或 startup timeout，且 worker 未 accepted | `FAILED` | `FAILED` | false | `worker_startup_failed` / `worker_rejected` / `worker_startup_timeout`，包含 dispatch record ref、worker kind、execution target、error code |
| EngineWorker 已 accepted 后返回结构化 `run_failed` | `FAILED` | `FAILED`，除非当前 phase 已有显式 recovery owner | 取 Engine event `recoverable` 作为诊断，不在 Phase 5 自动 recovery | Engine failure code、message、provider request id、recoverable |
| EngineEvent stream clean EOF 但没有 accepted terminal event | `FAILED` | `FAILED` | false | `stream_ended_without_terminal`，包含最后 accepted / preview event refs |
| EngineEvent stream error、transport close 或本地 worker crash，且 terminal result 无法确认 | `LOST` | `LOST` | false in Phase 5 | `worker_lost_before_terminal`，包含 worker lifecycle signal、stream error refs、last observed event refs |
| Engine emits recoverable failure that requires a later phase owner, such as reactive context compaction before Phase 10 policy exists | `FAILED` | `FAILED` | diagnostic-only in Phase 5 | `unsupported_recovery_policy`，包含 original error code and later owner |

Phase 5 不创建 automatic recovery Attempt，不把 local execution abnormal closeout 直接推入 `RECOVERING`。`RECOVERING` / recovery dispatch 由 Phase 10 reactive context governance 或 Phase 11 lifecycle / recovery 在各自 design refinement 中接入；Phase 5 plan 若要处理 recoverable Engine failure，必须明确只是记录 diagnostic 并失败收口，或证明 fake local execution 不会产生该路径。

Host recovery scan 遇到 `dispatch record = dispatching` 且 Attempt 仍为 `STARTING` 时，必须具备 positive orphan proof 才能把该 Attempt 标为 `LOST`。随后 Run 按 recovery policy 进入 `RECOVERING` 或 `LOST`。`dispatching` / `dispatcher_instance_id` 不授权 takeover，也不允许旧 Attempt 继续拥有 Host 状态。

attempt snapshot 至少包含：

- `session_id`、`run_id`、`attempt_id`、`execution_id`。
- complete `AgentRunRequest`。
- cancellation source / token binding。
- ToolExecutor capability snapshot。
- policy snapshot ids / refs required to explain execution.

lane token lifecycle：

- Lane token 从 acquire 成功后开始由 dispatch supervisor 持有；如果 durable recheck 失败，必须立即 release，且不得调用 WorkerProxy。
- durable recheck 成功并提交 `dispatching` 后，lane token 继续由 dispatch supervisor / worker execution context 持有，直到 Attempt terminal closeout、dispatch abort、WorkerProxy reject、startup timeout、cancel direct closeout 或 supervisor shutdown。
- WorkerProxy accept 后，lane token 不能在 `ATTEMPT_RUNNING` 前提前释放；否则 LLM provider 容量治理会和真实执行脱钩。
- cancel path 不直接假设自己持有 lane token。它只提交 canonical cancel / terminal facts、更新 dispatch record，并 wake dispatch scheduler；实际 token release 由持有 token 的 scheduler / worker finally 路径完成。

RemoteProxy、RemoteStub 与 EngineWorker 可以缓存 attempt snapshot 服务本次执行，但该 snapshot 不是远端治理状态；Host durable store 才是治理真源。

Phase 5 ToolRuntime / wait boundary：

- Phase 5 只允许 no-tool 或最小 fake ToolExecutor 支撑本地 Engine 执行闭环；不得实现 ToolRuntime governance、effective ToolBundle、Host accept barrier、`fetch_more`、语义级重复工具调用治理或 wait record。
- Phase 5 不创建 `WAITING` Run，不实现 `resolve_wait`，不把 EngineEvent `tool_awaiting` / `run_suspended` 解释为 Tool Awaiting canonical owner。第一版若收到 awaiting / suspended 路径，只能按当前 phase 的 unsupported execution path 记录诊断并收口为结构化失败，或在 plan 中证明 fake executor 不会产生该路径。
- Phase 6 / Phase 7 分别拥有 ToolRuntime governance 与 Tool Awaiting / `resolve_wait`；Phase 5 的 implementation 和测试不得通过临时 wait table、局部 ToolRuntime wrapper 或 Engine 特化分支提前实现这些能力。

Tool fact accept ack 语义：

- ToolRuntime Host accept path 是工具事实 canonical 写入所有者。
- ToolRuntime 向 Host submit tool fact candidate 必须携带稳定 accept idempotency key。
- accept idempotency key 必须能由 attempt identity、tool call identity、tool fact kind、result digest / awaiting digest 等确定性输入派生。
- Phase 6 工具结果 accept path 的默认幂等范围是当前 Attempt 的单个 tool call：`scope_kind=tool_fact_accept`，
  `scope_id` 至少绑定 `attempt_id` 与 `tool_call_id`，`semantic_input_digest` 至少覆盖 tool identity、
  normalized arguments digest、tool fact kind、result / payload digest、policy decision digest 与 truncation metadata digest。
  同一 scope + key + digest 的重试必须返回既有 accepted ack；同一 scope + key 但 digest 不同必须返回 idempotency conflict。
- Host 已 durable accepted 但 ack 在本地回调或远程传输中丢失时，ToolRuntime 必须重试 accept；Host 通过 accept idempotency key 返回既有 accepted ack，不追加第二份 canonical fact。
- ack rejected 表示 Host 明确拒绝该 candidate；ack timeout 只表示 ToolRuntime 未确认 Host 是否 accepted，不能直接把 tool result 返回给 Engine。
- Phase 6 第一版采用有限 accept retry；重试后仍未确认时，ToolRuntime 返回 governed tool error，且不得让 LLM 消费原始工具结果。
  Phase 6 的 ack timeout 默认动作不创建 wait record，不把 Run 推入 `WAITING`，不触发 recovery，也不把 Attempt 自动升级为 recoverable。
  后续 Phase 7 / Phase 11 若引入 awaiting 或 recovery 分支，必须基于新的 phase plan 扩展本策略。

## 18. ToolRuntime

ToolRuntime 是 Host-owned tool governance module。它可以随 EngineWorker 部署在本地或远端执行环境，但治理配置和真源来自 Host attempt snapshot。

### 18.1 ToolBundle Input / Runtime Tool View

Host 不能通过修改 Host 代码来增加业务工具。工具发现和注册必须外移到独立装配组件或 composition root；Host 包本身不得 import 具体业务工具模块，也不得内置财报工具清单。

Host 的工具输入是公共契约 `ToolBundle`：

```text
tool declaration / external tool registration module
  -> ToolDefinition
  -> ToolBundle
  -> create_host(..., tool_bundle=business_tool_bundle, ...)
  -> Host receives business ToolBundle as explicit construction parameter
  -> Host derives attempt-local effective tool view
  -> ToolRuntime factory receives business ToolBundle
  -> ToolRuntime factory injects enabled framework tools
  -> effective ToolBundle
  -> ToolRuntime projects ToolSchema to Engine and governs ToolCallable execution
```

`ToolBundle` 是 `dayu.contracts` 已定义的工具声明集合，包含 `ToolDefinition` 元组，校验工具名唯一，并可投影为 Engine 可见的 `ToolSchema` 列表或 ToolRuntime 使用的 truncate specs。Host 只接收 `ToolBundle`，不参与工具发现、模块扫描或注册生命周期。

外部工具注册组件负责收集业务工具并生成业务 `ToolBundle`。它可以使用显式 provider import path、package entry point、配置绑定或 Service 装配；这些只是 discovery adapter，不改变 Host 语义契约。所有 discovery 入口都必须解析为显式 provider callable，provider 返回当前项目 `@tool` 契约产生的 `ToolDefinition` 集合；runtime 不递归扫描 package，不猜测 module 内哪些对象是工具。新增业务工具应通过新增工具包 / provider / 配置装配完成，不要求修改 Host 源码。

`ToolsDiscovery` 的 provider 结果必须能形成稳定来源解释：provider identity 非空且不重复，source refs 必须存在，`content_digest` 由 `ToolsDiscovery` 基于稳定声明内容统一计算。digest 只覆盖 tool name、LLM-facing schema、truncate spec、tags 与 display metadata 等声明内容，不 hash callable 对象本身。provider 返回空工具集合默认是配置错误；只有显式 `allow_empty=true` 的 provider 才允许空结果。业务工具不得占用 framework reserved tool name，例如 `fetch_more`。

`ToolBundleSourceKind` 与 `ToolBundleSourceRef` 是跨 Host、runtime assembly、diagnostic、audit 与后续 attempt snapshot refs 的公共契约，应位于 `dayu.contracts`。`EXPLICIT_PROVIDER` 表达 provider import path / entry point 解析后的 provider callable，`CONFIG_BINDING` 表达配置绑定来源，`PACKAGE_ENTRYPOINT` 表达 package entry point 来源。Host 只保存 / 透传 source refs 与 digest 用于解释、诊断、trace、audit 或后续 snapshot refs；它们不是权限、lease、fencing、Host truth 或 Run / Attempt owner。

非 Python tool backend 不属于 Phase 12 第一版能力。未来若工具由 JS / Go / Rust / Java 等实现，应由 Python `ToolCallable` adapter 包装外部进程、HTTP / gRPC / JSON-RPC、daemon 或 MCP-like 服务，再通过 `ToolDefinition` 暴露给 provider。Host / ToolRuntime 仍只看到普通 `ToolDefinition.callable`，不理解外部语言、进程协议或 daemon 生命周期。

Host construction input 只能接收 `HostToolingOptions` 这样的 typed options：业务 `ToolBundle`、工具来源 refs、framework tool policy view 与后续治理所需的可解释 digest/ref。Host 不接收 discovery adapter 本体，不调用 provider 列表，不扫描业务包，也不把 per-run `tool_profile_ref` 作为 Phase 1 能力。P10.5 的 per-run tool variation 不通过多个 raw bundle 或 profile registry 表达，而是通过 `SubmitFollowupRequest.tool_names` 从 construction-time 全量业务 `ToolBundle` 中选择本次 Run 的工具子集。

Host 对传入的业务 `ToolBundle` 只做治理所需的防御性校验和派生 metadata：

- schema 合法性。
- reserved framework tool name 冲突，例如 `fetch_more`。
- bundle / schema digest（用于诊断、trace 或后续恢复策略解释；不是防止普通装配 bug 的重型快照机制）。
- attempt-local effective tool view refs。
- policy binding refs 是否可解析。

attempt-local effective tool view 是 RunInputBuilder 暴露 tool schemas 与 ToolRuntime callable dispatch 的单一真源。
业务工具声明现场的 `ToolDefinition` 已经把 schema 与 `ToolCallable` 同源绑定；Phase 6 不为该普通装配 invariant 引入额外
durable snapshot 机制。实现必须保证 `AgentRunRequest.tool_schemas` 与 ToolRuntime dispatch 都从同一个
effective `ToolBundle` 对象派生，并用测试覆盖 `fetch_more` framework tool 注入后的同源行为。

`fetch_more` 不由外部业务 `ToolBundle` 提供。ToolRuntime factory 根据是否启用 TruncationManager 注入 framework tool，生成 attempt-local effective `ToolBundle`。RunInputBuilder 向 Engine 提供的 `tool_schemas` 和 ToolRuntime 执行使用的 callable binding 必须来自同一个 effective `ToolBundle`。`fetch_more` 仍走普通 tool dispatch / policy / accept barrier，不允许 Host 或 Engine 为它写特化分支。

Start / follow-up request 不得携带 raw `ToolBundle`，因为 `ToolBundle` 包含 callable binding，不是普通 UI / Service request payload。Host construction / composition root 是业务 `ToolBundle` 的输入边界。普通每 Run 工具差异通过 `SubmitFollowupRequest.tool_names` 选择 construction-time 全量业务工具的子集：`None` / 省略表示全量业务工具，空集合表示禁用业务工具，非空集合表示指定子集。若未来需要跨 bundle / 跨来源 / 动态 discovery profile 切换，Service 可以通过 typed `tool_profile_ref` 或独立 Host handle 选择工具集合；该扩展必须冻结到 Attempt snapshot，不能塞进无结构 metadata。

Retry / resume 默认复用源 Run / Attempt 已接受的 effective tool view refs，包括本次 Run 的 `tool_names` selector 解析结果；policy 若要为关联新 Run 选择新的工具视图，必须显式记录 source relation、new effective view refs 与 policy decision。Replay 即使存在 effective `ToolBundle`，也不向模型暴露 tool schemas。

### 18.2 ToolRuntime Boundary

ToolRuntime 边界：

```text
Host
  -> receives business ToolBundle
  -> builds attempt-local effective tool view refs and ToolRuntime snapshot
  -> ToolRuntime factory builds effective ToolBundle
  -> ToolRuntime implements ToolExecutor
  -> ToolRuntime wraps effective ToolBundle / dispatcher / policies
  -> optional TruncationManager
  -> optional built-in fetch_more tool
  -> EngineWorker receives ToolRuntime as ToolExecutor
  -> Engine calls ToolExecutor.execute(...)
```

ToolRuntime 内部必须拆成稳定 ports，避免把注册、执行、治理、截断、追踪和 Host accept 混成一个 god object。第一版最小 port 边界：

- ToolBundle / schema projection port。
- tool dispatcher / callable execution port。
- policy decision port。
- truncation / fetch_more port。
- awaiting / wait outcome port placeholder。
- duplicate governance port。
- Host tool fact accept port。
- `ToolTraceDiagnosticEmitter`。

第一版可以在同一模块或类中实现多个 port，但 public boundary 和测试必须保持语义分离。不得用单个 god function 混合 schema lookup、execution、truncation、policy、Host accept、tracing 和 wait handling。

`ToolTraceDiagnosticEmitter` 只提交结构化工具诊断记录 / refs，供 tool trace projection 生成 hot JSON 与 cold JSONL。它不是 EventLog appender，不拥有 canonical fact，不写 audit，不直接写 trace 文件，也不更新 Run / Attempt 状态。

语义：

- Host 持有 ToolRuntime 的治理 ownership。
- ToolRuntime 是 `ToolExecutor`。
- Engine 只看见 `ToolExecutor` protocol。
- Engine 不知道 `@tool`、`ToolDefinition`、TruncationManager、`fetch_more` 或业务工具实现。
- Host 不知道具体业务工具实现；Host 只消费外部传入的业务 `ToolBundle`、attempt-local effective tool view refs 和工具治理策略。
- 远端 ToolRuntime 可以执行和截断，但不能 append EventLog、不能关闭 Attempt、不能更新 Run。
- ToolRuntime 必须遵守 Host-mediated accept barrier：工具事实必须先交给 Host durable accepted，收到 accepted ack 后，ToolRuntime 才能把对应 tool result 返回给 Engine 继续推理。LLM 不得消费 Host 真源中尚未 durable accepted 的工具事实。EngineEvent ingest 不能替代 ToolRuntime accept path 写工具 canonical facts。

Tool fact accept barrier 路径：

```text
Engine requests tool execution through ToolExecutor
  -> ToolRuntime applies policy / truncation / duplicate governance
  -> ToolRuntime executes tool or resolves reuse / awaiting
  -> ToolRuntime submits tool fact candidate to Host accept path
  -> Host validates attempt identity and payload durability
  -> Host appends TOOL_* canonical facts or rejects / diagnoses
  -> Host returns accepted ack with canonical event refs
  -> ToolRuntime returns tool result to Engine only after accepted ack
```

该路径对 LocalProxy 与 RemoteProxy 语义一致。LocalProxy 通过函数调用表达 accepted ack；RemoteProxy 通过等价远程请求 / ack 语义表达。远端 tool execution 本质上是把 LocalProxy 下的 tool execution / Host accept 调用改成远程调用；网络延迟、序列化成本或额外 round trip 不是放松 Host accept barrier 的理由。Remote transport 可以用不同 wire protocol 表达，但不能绕过 Host accept barrier。若 ack rejected 或 Phase 6 有限重试后仍 timeout，ToolRuntime 不得把对应工具结果返回给 Engine；Phase 6 默认返回受治理的工具错误。`awaiting` / suspend 与 recovery 分支分别由 Phase 7 / Phase 11 扩展，不在 Phase 6 默认动作中夹带。

tool fact candidate 必须包含足以治理和追溯的信息：

- tool identity 与 tool call identity。
- normalized args digest 与可选 semantic duplicate key。
- payload ref / digest / evidence anchors。
- 截断发生时的 truncation metadata 与 run-scoped `fetch_more` refs。
- 外部副作用或付费工具适用的 idempotency key。
- policy decision 与 diagnostic refs。
- accept idempotency key。

ToolRuntime 负责：

- 消费 Host 传入的业务 `ToolBundle` 并生成 attempt-local effective `ToolBundle`。
- 权限 / policy。
- 并发 / timeout / orphan cleanup。
- tool awaiting placeholder；wait record、`WAITING` 与 `resolve_wait` 由 Phase 7 实现。
- truncation / fetch_more。
- 语义级重复工具调用治理。
- 通过 `ToolTraceDiagnosticEmitter` 发出 tool trace 所需诊断。
- 工具级 idempotency key 执行约束。

### 18.3 语义级重复工具调用治理

Engine 只负责同一次模型响应内的结构性工具调用协议，不理解工具语义、业务幂等性、用户意图或历史结果质量。语义级重复工具调用治理属于 Host / ToolRuntime。

治理目标不是禁止所有重复工具调用，也不是跨 Attempt 复用历史工具结果。第一版只治理同一个 Attempt 内模型复读导致的重复工具调用，目标是减少一次 LLM 调用内的无意义 token、工具执行浪费和工具循环风险。跨 Attempt 的重复工具调用默认视为新的工具请求；是否复用旧结果、刷新结果或要求工具级幂等，不由 duplicate governance 决定。

重复判定信号：

- tool identity：工具名、工具版本、schema version。
- normalized arguments：去除无关顺序和默认值后的参数 digest。
- optional tool-provided semantic key：工具声明的 attempt-local 语义重复 key。
- accepted result digest / evidence anchor：当前 Attempt 内已接受结果是否等价或覆盖当前请求。

ToolRuntime 维护 attempt-local in-memory duplicate index，不需要 session-scope 或 run-scope durable duplicate ledger。duplicate key 的 scope 必须绑定当前 Attempt，至少包含 `attempt_id`，并结合 tool identity、normalized arguments digest 与可选 semantic key。`WAITING -> resolve_wait -> resume`、steer、recovery 或 compact recovery 创建的新 Attempt 不继承旧 Attempt 的 duplicate index；模型在新 Attempt 中再次发起同 tool + 同 args 调用时，ToolRuntime 默认按新的工具请求治理。

Host 崩溃、重启、Attempt 终止或新 Attempt 创建后不要求继承该内存索引；P6 第一版不引入 durable duplicate ledger，也不从 EventLog 重建 duplicate index。RunInputBuilder 是否把旧工具结果作为上下文、历史观测或证据 ref 注入 prompt，属于 memory / prompt assembly / tool result presentation policy，不属于 duplicate governance，也不得被用作跨 Attempt 语义去重的 correctness 前提。

policy action 必须分级：

- `allow`：重复调用有新 scope、新参数、新证据需求或用户明确要求。
- `reuse`：在同一 Attempt 内直接复用已接受工具事实 / evidence anchor，不重新执行工具。
- `hint`：append `GUIDANCE_INSERTED`，提醒模型本 Attempt 已有事实或建议改查其它证据。
- `require_justification`：允许继续，但要求下一轮 messages 中保留模型为什么需要重复调用的上下文。
- `hard_stop`：判定为工具循环或违反幂等 policy，关闭当前 Attempt 为 failed / governed stop，并由 Host policy 决定 retry、replay 或失败。

duplicate governance policy 与模型可见提示必须来自 Host / ToolRuntime 的 typed 配置或 Attempt snapshot，不能把治理动作、
提示文案或 justification 参数名硬编码在执行路径里。配置边界必须保持 attempt-local：可以按默认值或工具名选择 `allow` /
`reuse` / `hint` / `require_justification` / `hard_stop`，也可以配置对应治理提示和结构化 justification 参数名；但这些配置不得
引入跨 Attempt duplicate index、durable duplicate ledger、工具 freshness 策略或跨历史结果复用策略。

EventLog 规则：

- 工具调用意图进入 `TOOL_CALL_REQUESTED`。
- policy 决策进入 `TOOL_CALL_GOVERNED`，至少包含 duplicate key、决策、scope、reason、相关 prior event refs。
- 真正执行并被接受的结果进入 `TOOL_RESULT_ACCEPTED`。P1-P7 的 accepted waiting terminal result 同样使用 `TOOL_RESULT_ACCEPTED` 作为唯一 accepted tool result canonical event，通过 payload 的 wait-specific fields 区分等待完成来源、wait id、resolution kind 与 wait record 状态，避免追加第二份 canonical tool fact。
- `reuse` 不伪造新的工具事实；它只能引用当前 Attempt 内 prior accepted result，并在 messages 中表达为 Host 复用的已接受事实。
- audit / tool trace 必须能解释为什么某次重复调用被允许、复用、提示或阻断。

边界：

- 第一版只实现 attempt-local deterministic duplicate key；跨 Attempt、跨 Run、跨 Session、跨多年历史中的相似证据召回属于 Conversation Memory / retrieval、tool result presentation 或工具自身 policy，不属于重复工具调用治理。
- 对财报读取类 read-only 工具，同一 Attempt 内重复调用默认优先 `reuse` / `hint`，除非参数或 evidence scope 明确变化；跨 Attempt 不默认复用。
- 对外部写入或付费工具，必须依赖工具 schema / policy 提供 idempotency key；Host 的 duplicate governance 不能替代工具级幂等。
- 该治理不能进入 Engine，也不能让 RemoteStub 拥有 Host 状态。

## 19. TruncationManager / fetch_more

`ToolTruncateSpec` 是截断的显式触发条件。无 spec、spec 未启用、策略未知或 limit 非法时，默认不截断。

执行路径：

```text
@tool(..., truncate=ToolTruncateSpec(...))
  -> ToolDefinition
  -> Host / ToolRuntime keeps ToolTruncateSpec
  -> Engine only receives ToolSchema
  -> Engine emits normal tool call
  -> ToolExecutor executes ToolCallable
  -> TruncationManager applies declared ToolTruncateSpec
  -> ToolExecutor returns normal tool result with truncation hint when needed
  -> truncation hint carries opaque cursor + scope_token for ordinary fetch_more
```

Truncation handle 语义：

- `cursor` 标识“从哪个被截断结果、哪个位置继续读”。
- `scope_token` 是 opaque capability / scope binding，用来证明本次 `fetch_more` 只能读取对应工具结果的后续内容。
- LLM-facing tool result 只暴露普通 `fetch_more` 所需的 opaque 参数，不暴露 Host 内部 cursor store、artifact path、payload layout 或远端 cache key。
- Phase 6 第一版 `cursor` / `scope_token` 是 Run-scoped、short-lived、ToolRuntime-local capability，只保证创建它的
  Run 内续读，允许同一 Run 内跨 iteration 使用；不承诺跨 Run、跨 Session、Host restart、Attempt `LOST` /
  recovery、replay 或长期 memory retrieval 后继续可用。
- `cursor` / `scope_token` 的生成、single-use、TTL、scope hash 校验和错误 envelope 属于 TruncationManager
  实现细节，但必须通过测试覆盖。Run 终态后 cursor 失效；过期、scope mismatch、cursor missing 或 token mismatch
  均返回普通工具错误结果，不推进 Host recovery，也不创建 wait record。

`fetch_more` 是 Host / ToolRuntime 内置 framework tool，但必须作为普通 tool 暴露和执行：

```text
Host / ToolRuntime registers built-in @tool("fetch_more", ...)
  -> effective tool schemas include business tools + fetch_more
  -> model emits normal tool_call(name="fetch_more", arguments=...)
  -> ToolExecutor dispatches as normal tool call
  -> fetch_more callable validates cursor + scope_token through TruncationManager
  -> ToolExecutor returns normal tool result
```

硬约束：

- `fetch_more` 不能有 Host / Engine 特化分支。
- `fetch_more` 不拥有专属 Engine event 或专属 WorkerProxy 协议。
- `fetch_more` callable 内部通过闭包或协议访问 TruncationManager，这是普通 tool callable dependency injection。
- EventLog 视角下，`fetch_more` 是普通 tool request / result。
- `fetch_more` 不能成为业务工具注册表 public API。
- `fetch_more` 必须校验 `cursor` 与 `scope_token` 的绑定关系；scope 不匹配、过期、被撤销或 artifact digest 不匹配时，应返回普通工具错误结果，不得旁路读取。
- Phase 6 不实现 durable cursor descriptor table，也不要求 Host 在 EventLog 中持久化足以跨 restart 续读的 raw payload /
  cursor store。EventLog 可以记录截断发生、`fetch_more` 调用、普通工具结果与诊断 refs，但这些记录不把
  `fetch_more` 升级为跨 Run 可恢复能力。
- Remote ToolRuntime 可以持有 attempt-local TruncationManager 和 short-lived cache，服务同一 Run 内的快速续读；这是优化，
  不是正确性前提。Phase 14 若要让远端支持等价 `fetch_more` 语义，必须保持 Host accept barrier，不得让远端拥有
  Host EventLog、Run / Attempt 或 wait record 状态。
- cursor 生命周期、TTL、读取 limit、重复续读、错误 envelope 和取消资源收口由 TruncationManager / ToolRuntime policy 定义。

## 20. Tool Awaiting / Wait Record

长事务或外部等待以 `ToolAwaitingOutcome` 进入 Host。

基本路径：

```text
ToolExecutor returns ToolAwaitingOutcome(await_spec, snapshot)
  -> ToolRuntime submits awaiting candidate to Host accept path
  -> Host transaction validates attempt identity and current dispatch state
  -> Host appends TOOL_AWAITING
  -> Host appends RUN_WAITING
  -> Host appends ATTEMPT_SUSPENDED
  -> Host creates active wait record
  -> Host updates Run.status = WAITING
  -> Host closes Attempt.status = SUSPENDED
  -> Host returns accepted ack / event refs
  -> Engine may emit tool_awaiting with accepted refs for diagnostic / preview
  -> Engine may emit run_suspended with accepted refs for diagnostic / preview
```

ToolRuntime Host accept path 是 awaiting canonical owner。Engine `tool_awaiting` / `run_suspended` 不能创建 wait record，不能把 Run 推入 `WAITING`，不能关闭 Attempt，也不能追加第二份 awaiting canonical facts。它们只能携带 accepted refs，作为 preview、diagnostic 或 idempotent confirmation。

如果 accepted ack 丢失，ToolRuntime 必须用同一个 accept idempotency key 重试，Host 返回既有 accepted refs。即使 Engine 后续 `tool_awaiting` / `run_suspended` 事件丢失，Host durable state 也已经完整；迟到 EngineEvent 只能 diagnostic / idempotent confirmation。

wait record 最小语义：

```text
wait_id
run_id
attempt_id
tool_call_id
tool_name
adapter_key
await_kind
resume_token
snapshot_ref?
external_job_id?
idempotency_key?
created_event_id / created_event_sequence
updated_event_id / updated_event_sequence
resume_policy: callback | poll | manual
deadline / expires_at?
status: waiting | resolved | failed | cancelled | lost
```

wait record 是 Host durable state index，不是 EventLog 的替代品，也不是 projection / timeline truth。EventLog 记录
`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、`RESUME_REQUESTED` 和 tool terminal facts；wait record 负责
active wait 查询、adapter observation 恢复、取消 CAS、resolution CAS 与 late result 拒绝。`adapter_key`、`await_kind`、
`resume_token`、`external_job_id` 与 `snapshot_ref` 必须是强类型字段或受限 typed refs，不能把 adapter 对象、callable、
无结构 metadata bag 或外部系统私有 payload 放进 durable row。

wait record 状态语义：

- `waiting`：Host 已接受等待事实，Run 保持 `WAITING`。
- `resolved`：等待结果已被 Host durable accepted，并已触发 resume Attempt 创建。
- `failed`：外部等待确认失败，Run 按 policy 进入 `FAILED`、`RECOVERING` 或关联 retry。
- `cancelled`：Host 已取消 Run 或等待，不再接受该 wait record 的结果作为 `canonical_fact` 进入 EventLog。
- `lost`：Host 无法确认外部 job 状态，且 policy 放弃继续等待。

Resume 策略分层：

```text
wait signal source
  -> poll | callback | manual
  -> common Host resolve_wait pipeline
  -> append RESUME_REQUESTED
  -> append tool terminal/result fact
  -> append RUN_STARTED(start_reason=resume)
  -> create new Attempt
  -> rebuild messages
  -> resume Run
```

`poll`、`callback`、`manual` 只是发现等待结果已经到达的 adapter。稳定核心是 Host 内部统一的等待结果接收与治理入口：

```text
resolve_wait(wait_id, request) -> RunSnapshot
```

`resolve_wait` request 必须携带 `source`、`idempotency_key`、`observed_at` 与强类型等待结果 envelope。等待结果 envelope
至少覆盖 completed / failed / cancelled / lost；Host pipeline 负责把 envelope 转成 durable payload、tool terminal canonical
fact、wait record terminal update 与 resume / closeout 状态迁移。`resolve_wait` 不等待外部长事务完成，也不死等业务结果。
结果未到时，poll adapter / callback endpoint / manual operator 不应调用它，或调用后得到结构化拒绝，例如
`outcome_not_ready`、`invalid_state`、`wait_not_found`。`resolve_wait` 本身是短事务 command，最多只因 SQLite transaction、
CAS 或 busy timeout 做短等待和重试。

resume policy 覆盖 internal / manual、poll、callback 三类入口。所有入口都必须走同一个 `resolve_wait` pipeline，不能各自更新 Run / Attempt / EventLog。

`WAITING -> resolve_wait -> resume` 会创建一次新的模型请求。模型本身是无状态调用方，Host 不能把“模型没有天然记住上一个 Attempt 已经发过某个 tool call”作为协议前提，也不能要求模型在新请求里自动避免重复 tool call。resume 的 RunInputBuilder 必须从 EventLog canonical facts 重建足够的 messages，把已 accepted 的等待结果、必要上下文和按 policy 允许注入的工具事实 / refs 放回模型输入；若模型仍发出与上一 Attempt 等价的工具调用，第一版 duplicate governance 不做跨 Attempt 复用或阻断，ToolRuntime 按新的 Attempt 内工具请求处理。工具结果是否可复用、是否需要刷新、是否需要工具级幂等，由工具 policy、freshness / side-effect 语义或后续 retrieval / prompt assembly 设计决定。

约束：

- 如果工具启动外部 job，必须返回稳定 `external_job_id` 或等价 ref。
- 外部副作用必须先有工具级 idempotency key，再启动外部 job。
- wait record 是 Host durable 状态，不是 remote worker 状态。
- job 完成后，`resolve_wait` append `RESUME_REQUESTED`、tool terminal / result canonical fact、`RUN_STARTED(start_reason=resume)`、new Attempt row、`ATTEMPT_STARTED` 与 dispatch record，再 resume。
- 如果 job 状态无法确认，应进入 structured failed / lost。
- Engine 不读取 wait record，也不恢复旧 Agent / Runner。
- Host recovery scan 遇到 `WAITING` Run 时不得创建新 Attempt；它只能恢复 wait record 的 adapter 状态。
- wait record 的 `resume_policy` / `await_spec` / `external_job_id` 必须包含足以在 Host restart 后恢复 adapter observation 的 durable refs。adapter registry / lookup 由 Host composition root 提供 typed adapter binding；wait record 只保存 adapter key / policy ref / external job refs，不保存进程内 adapter 对象。
- `poll` adapter 从 wait record 读取 `external_job_id` / `await_spec` 后继续轮询，并在完成时调用同一个 `resolve_wait`。
- `callback` source 在 Phase 7 只保留 adapter contract 与 common pipeline 入口；专属 HTTP callback 服务、认证入口、复杂
  重放防护和外部系统专属 callback adapter 不属于第一版实现。后续 callback 产品化入口必须验证认证、重放防护和 idempotency
  key，然后调用同一个 `resolve_wait`。
- `manual` resolve 只能由受控入口触发，并必须写 audit projection。
- wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果；不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。
- wait record resolution 与 `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED(start_reason=resume)`、new Attempt row、`ATTEMPT_STARTED`、dispatch record 创建必须在同一事务或等价原子流程中收口。
- `resolve_wait` 幂等范围是 `(wait_id, idempotency_key)`。
- `resolve_wait` 幂等判断只基于 committed durable state；如果事务未 commit，重试应重新执行完整 resolution chain。
- 同一幂等键 + 同一 outcome 重试时，Host 返回既有 RunSnapshot / Attempt refs，不追加第二份 canonical fact，不创建第二个 Attempt。
- 同一幂等键 + 不同 outcome 必须返回 `idempotency_conflict`。
- 已 `resolved` 的 wait record 只允许幂等重放既有结果，不允许第二次 resolution。
- 非 `waiting` 状态的 wait record 不得被新的 resolution 改写；`cancelled` / `lost` 的迟到结果只能进入 diagnostic / tool trace。
- `cancelled` / `lost` wait record 的迟到 poll / callback result 不得作为 `canonical_fact` 进入 EventLog；必须至少追加
  `event_class=diagnostic`、`event_type=WAIT_LATE_RESULT_REJECTED` 的 EventLog diagnostic event，payload 包含 `wait_id`、
  `run_id`、`source`、`idempotency_key`、`observed_at`、rejection reason 与 outcome digest / refs。完整 tool trace
  projection 可由后续 phase 消费该 diagnostic event 生成。
- adapter 观察到 wait record cancelled 后，可以 best-effort cancel / revoke / abandon 外部 job；该能力不能影响 Host Run terminal 正确性。

## 21. Suspend / Resume / Retry / Replay

`suspend`、`resume`、`retry`、`replay` 是不同语义。

Suspend / Awaiting：

```text
ToolRuntime receives ToolAwaitingOutcome
  -> ToolRuntime submits awaiting candidate to Host accept path
  -> Host validates attempt_id + execution_id
  -> Host appends TOOL_AWAITING / RUN_WAITING / ATTEMPT_SUSPENDED
  -> Host closes current Attempt as SUSPENDED
  -> Host updates Run to WAITING
  -> Host persists wait record
  -> Engine may emit tool_awaiting / run_suspended with accepted refs as diagnostic confirmation
```

Engine `tool_awaiting` / `run_suspended` 不拥有 Host waiting 状态迁移；它们不能创建 wait record、不能关闭 Attempt、不能更新 Run。

Resume：

```text
wait condition satisfied
  -> Host appends RESUME_REQUESTED
  -> Host appends tool terminal/result fact
  -> Host appends RUN_STARTED(start_reason=resume)
  -> Host creates new Attempt with new execution_id
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds complete AgentRunRequest.messages from EventLog canonical facts
  -> Host dispatches through LocalProxy / RemoteProxy
```

Resume 是同一 Run 内的新 Attempt，不是恢复旧 Attempt，也不是让旧模型进程继续执行。由于模型请求无状态，Host 必须在 rebuild messages 阶段显式提供等待结果、必要上下文，以及按 prompt / memory / tool-result policy 允许注入的已 accepted 工具事实或 refs。模型在 resume 后重复发起与上一 Attempt 等价的 tool call 时，这不是模型协议违规；第一版 duplicate governance 只在当前 Attempt 内生效，不跨 Attempt 复用旧 duplicate index。

Retry：

- Retry 是调用方主动发起的公开 Host control API，Host policy 只负责允许、拒绝、复用事实和设置重试上限。
- Retry 通过函数式 `retry(run)` 语义触发；公共 API 为 `retry_run(host, run_id, request)`，语义是输入源 Run、返回关联的新 Run。
- Retry 必须有 `client_request_id` / idempotency key。
- Retry 不重开原终态 Run；原 Run 的 `FAILED` / `LOST` 等终态事实保持不可变。
- Retry 创建关联的新 Run，新 Run 再创建自己的 Attempt 和 `execution_id`。
- Retry 不复用旧 EngineWorker / Agent / Runner。
- Retry 是否复用源 Run 已接受工具事实由 retry policy 决定；默认复用已提交且仍有效的工具事实，不复用失败中的未接受输出。

Replay：

- Replay 是调用方主动发起的公开 Host control API，Host 不自动 replay，也不把 replay 当作 terminal 输出失败后的内部隐式修复策略。
- Replay 只用于 final answer 的格式、schema、结构、输出 envelope 或引用格式违反输出 policy，并且可以在不重复昂贵工具的前提下修复。
- 事实内容脏、幻觉、业务归因错误、证据不足、证据冲突不属于 replay 场景；这些情况必须通过新分析 / follow-up / retry / evidence retrieval / 新工具事实解决。
- Replay 通过函数式 `replay(run)` 语义触发；公共 API 为 `replay_run(host, run_id, request)`，语义是输入源 Run、返回关联的新 Run。
- Replay 必须有 `client_request_id` / idempotency key 和 replay reason。
- Replay 不重开原 `SUCCEEDED` Run；旧 final answer 保留为历史 assistant conclusion / rejected candidate，不是 `evidence_backed_fact`。
- Replay 创建关联的新 Run，新 Run 再创建自己的 Attempt 和 `execution_id`。
- Replay 通过 EventLog 重建 messages，复用源 Run accepted tool facts / tool messages / evidence anchors。
- Replay 是 no-tool `AgentRunRequest.messages` 结构修复调用，不重新执行工具，不新增工具事实。主防线在 RunInputBuilder：replay Attempt 构造 `AgentRunRequest` 时不暴露 tool schemas，模型不应获得可调用工具。ToolRuntime 的 replay policy 拒绝只是 defense-in-depth。
- 源 Run 的 final answer 不作为普通 assistant conclusion 注入新 Run；它只能作为 `rejected_candidate` / repair context 与 validation errors / repair instruction 一起进入 messages。
- replay messages 必须约束模型只做结构修复，不引入新事实，不调用工具，不改变 evidence anchors。
- 如果 replay 执行期间模型仍发起 tool call，Host / ToolRuntime 必须按 replay policy 拒绝；默认治理动作是 hard stop 或 governed tool error，并记录 diagnostic / tool trace。不得把该 tool call 当作普通工具执行。
- Replay append `REPLAY_REQUESTED`，并在新 Run 上记录 `source_run_id` / `replay_of_run_id` 或等价关联。
- Session timeline 可以把 replay Run 标成“对某次回答的重放 / 修正”，并用 read model 指向最新 replay result；EventLog 保留完整 replay 链。

Retry / Replay 默认前置条件：

| 源 Run 状态 | retry_run | replay_run |
| --- | --- | --- |
| `SUCCEEDED` | 默认拒绝，除非显式 retry policy 支持重跑成功 Run | 仅在格式 / schema / 结构修复场景接受 |
| `FAILED` | retry policy 允许时接受 | 拒绝 |
| `LOST` | 仅当 policy 判断 durable facts 足够支持创建新 Run 重试时接受 | 拒绝 |
| `RECOVERING` | `invalid_state` | `invalid_state` |
| `RUNNING` / `WAITING` / `CANCELLING` | `invalid_state` | `invalid_state` |
| `QUEUED` | `invalid_state` | `invalid_state` |
| `CANCELLED` | 默认拒绝；未来 policy 可支持显式 rerun | 拒绝 |

P10.5 ordinary local multi-turn scope 不改变上表的长期语义，但只实现普通本地 `FAILED` retry 与 `SUCCEEDED` structure replay。`LOST` / `RECOVERING` retry、recovery cancel、startup recovery、positive orphan proof 与 recovery dispatch 继续归 Phase 11；P10.5 implementation 不得为了通过 retry / replay / cancel smoke 提前实现或改变 Recovery 路径。

## 22. Cancel

取消由 Host 发起和治理，Engine 只观察 run-local cancellation token。取消不是普通 error，也不是工具失败。

初始路径：

```text
client requests cancel
  -> Host appends CANCEL_REQUESTED
  -> if Run is QUEUED: Run -> CANCELLED
  -> if Run is RECOVERING before new dispatch: Run -> CANCELLED
  -> if Attempt STARTING and dispatch record pending / waiting_for_lane / dispatching before WorkerProxy accepted: Attempt -> CANCELLED and Run -> CANCELLED
  -> if active Attempt RUNNING: Host appends RUN_CANCELLING and Run -> CANCELLING
  -> commit
  -> Host sends cancel through LocalProxy / RemoteProxy after commit only when active worker exists
  -> EngineWorker maps cancel to run-local cancellation token
  -> Engine emits run_cancelled when cancellation wins execution boundary
  -> Host validates attempt_id + execution_id
  -> Host appends ATTEMPT_CANCELLED + RUN_CANCELLED
```

规则：

- `ACCEPTED` / `QUEUED` 且尚未创建 Attempt 的 Run 被取消时，直接进入 `CANCELLED`，不创建 Attempt。
- `WAITING` Run 被取消时，Host 直接收口为 `CANCELLED`：append `CANCEL_REQUESTED`，CAS 标记该 Run 下所有
  active `status=waiting` wait records 为 `cancelled`，append `RUN_CANCELLED`；不创建 resume Attempt。Phase 7 第一版应保持
  同一 Run 同时只有一个 active wait record 的 invariant，并用测试守护；复数更新是防御性状态收口。外部 job 的实际取消 /
  revoke / abandon 属于 adapter best-effort 能力，不作为第一版保证，也不能影响 Host terminal correctness。
- `RECOVERING` 且新 Attempt 尚未 dispatch committed 时直接进入 `CANCELLED`；不创建新 Attempt，不进入 `CANCELLING`。
- Attempt `STARTING` 且 dispatch record 仍为 `pending` / `waiting_for_lane` 时直接收口：append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，标记 dispatch record cancelled，cancel lane wait / wake dispatch scheduler，释放 active slot 并触发 queue promotion check；不通知 EngineWorker。
- dispatch record 已进入 `dispatching` 但 Attempt 仍为 `STARTING` 时，表示 lane 已 acquire 且 dispatching commit 已完成，但 WorkerProxy 尚未 accepted。该窗口仍按 pre-worker direct cancel 收口：append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，标记 dispatch record `cancelled`，wake dispatch scheduler，释放 active slot 并触发 queue promotion check；不得进入 `CANCELLING`，不得等待不存在的 WorkerProxy。持有 lane token 的 dispatch scheduler 必须在 WorkerProxy 调用前做 final pre-call recheck；若看到 cancel / terminal 已提交或 dispatch record 已 `cancelled`，必须 release lane token 并跳过 WorkerProxy。
- Attempt 已 `RUNNING` 时，必须 append `CANCEL_REQUESTED` + `RUN_CANCELLING` 并向 WorkerProxy 传播 cancel。`CANCEL_REQUESTED` 表达取消意图，`RUN_CANCELLING` 表达 Run 状态迁移。`dispatching` 本身不等于 active worker；只有 `ATTEMPT_RUNNING` 已 durable accepted 后才说明 WorkerProxy / EngineWorker 已接受执行。
- terminal fact 已提交后，cancel 不能改写 terminal。
- cancel 只阻止未来工作，不覆盖已接受事实。
- 已接受 tool result、awaiting outcome、final decision、canonical facts 继续保留。
- cancel 与 suspend 同时发生时，由 Host ingest 事务提交顺序决定。suspend / awaiting 已 canonical accepted 后，late cancel 不覆盖它，后续走 `WAITING -> CANCELLED`；cancel 已提交后，late suspend / awaiting candidate 不得把 Run 推入 `WAITING`，只能进入 diagnostic / tool trace 或被拒绝为 canonical fact。
- 如果外部 job 在 Run 已 `CANCELLED` 后回调或被 poll / manual 入口带回结果，Host 必须拒绝其结果作为
  `canonical_fact` 进入 EventLog，并至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event；完整 tool trace 可由
  后续 projection 消费该 diagnostic event 生成。
- cancel 控制消息最小携带 `run_id`、`attempt_id`、`execution_id`。
- 未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，旧 Attempt 进入 `LOST`；若 `CANCEL_REQUESTED` 已 durable accepted 且 terminal fact 未抢先提交，Host 不得继续用户目标，Run 应按 policy 收口到 `CANCELLED` 或 `LOST`，不得创建新的正常执行 Attempt。
- 同一 `(run_id, client_request_id)` cancel 重试必须返回既有结果，不重复 append `RUN_CANCELLING`。Run 已是 `CANCELLING` 时，新的不同 cancel 请求不能重复制造状态迁移；可按 policy 返回当前状态或记录 diagnostic。
- 强制终止执行环境、后台 job reconcile、细粒度资源收口失败事实属于 cancel governance 扩展能力，不影响基础 Host 状态收口。

`cancel_session_runs(host, session_id, request)` 是 session-scope cancel command，用于客户端退出、supervisor shutdown 或用户明确停止该 Session 下全部未完成工作。它不是 `close_session`，不关闭新输入入口；不是 `purge_session`，不删除事实；也不表达“客户端拥有的所有 Session”。

Phase 4 只实现 `cancel_session_runs` 的 Phase 1-3 可闭环子集：`QUEUED` Run 与 pre-dispatch Attempt `STARTING`。dispatch record 已进入 `dispatching`、Attempt 已 `RUNNING`、`WAITING`、`RECOVERING`、active worker propagation、wait record cancel 与 recovery dispatch cancel 都是 stable deferred 行为；Phase 5 / Phase 7 / Phase 11 必须分别补齐，不能把 Phase 4 子集解释为最终语义。

`cancel_session_runs` 语义：

- 作用范围是指定 `session_id` 下所有 non-terminal Run。
- 包含 `QUEUED`、`RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING`，以及 Attempt `STARTING` / `waiting_for_lane` 场景。
- 不影响其它 Session，不影响已终态 Run。
- 幂等范围是 `(session_id, client_request_id)`。
- accepted / queued Run 直接 `CANCELLED`，不创建 Attempt。
- Attempt `STARTING` 且尚未 dispatch / 正在 `waiting_for_lane` 时直接取消，不通知 EngineWorker。
- 已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy；Phase 5 owns 该路径。
- `WAITING` Run 取消 wait record；外部 job 物理取消由 adapter best-effort；Phase 7 owns 该路径。
- `RECOVERING` Run 的取消由 Phase 11 recovery owner 接入。
- terminal 已抢先提交时 terminal 优先，`cancel_session_runs` 返回当前终态，不改写 terminal。
- 返回 `SessionSnapshot`，包含 cancel 后的 session / run summary。

客户端同时 attach 多个 Session 时，调用方必须逐个 session 调用 `cancel_session_runs`，并同时 cancel / close 自己持有的 lane wait 或 lane token。Host 不维护客户端到多个 Session 的 ownership 真源。

Host ingest 顺序是分布式竞态排序真源。不得用物理时间重写该规则。

## 23. RunInputBuilder

RunInputBuilder 是 Host 内部组件。它是 memory / EventLog / Service 场景输入进入 Engine 的唯一运行态入口。

RunInputBuilder 通过 typed input provider protocols 聚合输入，不读取上游内部结构，也不直接查询 UI / Service 临时状态。每类输入必须有稳定 provider contract，例如：

- `CurrentRunFactProvider`
- `SessionContinuityProvider`
- `MemorySnapshotProvider`
- `CompactArtifactProvider`
- `ToolSchemaSnapshotProvider`
- `SceneParameterProvider`
- `PolicySnapshotProvider`

这些 provider 只暴露 RunInputBuilder 所需的 typed view / refs，不暴露各自内部表结构、projection 私有状态或全局 registry。

第一版物理实现可以合并共享同一 EventLog reader 的 provider，但必须保持 typed input 边界。RunInputBuilder 不得读取 UI 临时文本、Session timeline 真源、全局 policy service locator 或 untyped metadata bags。

输入：

```text
current USER_INPUT_ACCEPTED canonical fact
current run semantic canonical facts
session / prior-run EventLog canonical facts needed for continuity
session memory snapshot
compact artifact / context snapshot refs when present
source Run accepted tool facts when retry / replay policy allows reuse
caller system messages / scene parameters
tool schemas snapshot
runner / policy snapshot refs
```

`USER_INPUT_ACCEPTED` 是当前用户 prompt 进入 RunInputBuilder 的唯一事实入口。UI / Service 可以提交用户输入给 Host，
但一旦进入 RunInputBuilder，就必须读取已持久接受并绑定到 Session / Run 的 `USER_INPUT_ACCEPTED` canonical fact；
不能从 UI 临时文本、request 临时字段或 Session timeline 旁路取当前 prompt。

输出：

```text
AgentRunRequest.messages
```

Service / caller 可以提供 system messages 或场景装配参数，但不能绕过 Host 直接拼装恢复 messages。

messages 构造顺序必须稳定：

1. Host / Service 提供的 system 与场景约束。
2. session memory stable layer：pinned state、evidence-backed facts、open questions、assumptions。
3. 当前 `USER_INPUT_ACCEPTED` 与当前 Run 需要的 canonical facts，按 `event_sequence` 顺序投影为对模型有语义的 messages。
4. replay / retry / steer / resume guidance。
5. 当前 attempt 的工具 schema snapshot 与运行 policy。

同一 EventLog 在同一 policy 下必须构造出等价 messages；projection lag、preview delta 或 sink failure 不能改变 RunInputBuilder 输出。

RunInputBuilder 的输出必须能由输入 fact refs、memory snapshot cursor、compact artifact refs 与 policy snapshot 解释；不得依赖未持久化的旧 provider request、旧 EngineRunner 内存或 UI 临时状态。

应进入 messages 的典型事实：

- `USER_INPUT_ACCEPTED`、steer input、resume input、follow-up input。
- assistant final answer / assistant conclusion，作为对话连续性，不是 `evidence_backed_fact`。
- accepted tool result、tool terminal result、evidence anchor / ref / digest。
- tool awaiting resolved 后的 terminal / result fact。
- Host memory block：pinned state、evidence-backed facts、open questions、assumptions。
- `GUIDANCE_INSERTED`，如果影响后续 iteration。
- 必要的 cancel / resume / steer 说明，如果它影响当前继续目标。

不应进入 messages：

- audit-only facts。
- usage-only facts。
- stream fanout 状态。
- projection checkpoint。
- raw preview delta / reasoning delta。
- 内部 state transition 本身，除非模型需要理解其用户语义。

RunInputBuilder 不创建独立 RunInputBuildTrace 子系统；上下文构造和证据纳入的观测统一进入 tool trace / trace 体系。

## 24. Conversation Memory

Conversation Memory 从买方财报分析 Agent 的会话不变量出发：

- 目标稳定。
- 工具结果即事实。
- 追问连续性是刚需。
- 跨轮一致性优先于上下文丰富度。
- memory 克制。
- 展示态与运行态分离。

Conversation Memory 不是聊天记录压缩器，而是财报分析工作台状态投影。它回答下一轮分析所需的稳定问题：

- 现在分析谁。
- 分析什么期间。
- 按什么口径。
- 哪些事实已由工具确认。
- 哪些仍是假设或待验证线索。
- 下一步需要验证什么。

结构：

```text
Conversation Memory
  -> stable layer
      -> pinned_state
      -> evidence_backed_facts
      -> working_assumptions
      -> open_questions
  -> history pool
      -> conversation_continuity
      -> recent raw turns floor
      -> older raw turns
      -> episode summaries
```

Conversation Memory 不包含独立的 `evidence anchors / tool facts / provenance` memory layer。accepted tool result 是
`TOOL_RESULT_ACCEPTED` canonical fact；accepted evidence envelope、payload digest、artifact ref、source locator 与 EventLog
refs 是 Host 内部 provenance / audit mapping。LLM-facing memory 只能看到可读 claim、可读 continuity 与短 evidence refs，不能把
Host 内部账本字段作为主要语义输入。

`pinned_state` 至少包含：

- `current_goal`
- `confirmed_subjects`
- `user_constraints`
- `open_questions`

`evidence_backed_facts` 只来自 accepted tool evidence。它不表示 Host 证明世界事实为真，而表示一个自包含 claim 绑定到了
已接受 evidence，因此不是 assistant 幻想、episode summary 或 user claim。每条 `evidence_backed_fact` 至少包含
`claim_text`、`evidence_kind`、`evidence_refs`、producer / extraction operation ref、`event_id` / `event_sequence` 与可选
opaque attributes。`evidence_refs` 指向 accepted evidence envelope；第一版每个 accepted tool result 至少形成一个稳定
`evidence_id`，多个 facts 可以引用同一个 `evidence_id`。更细粒度 item-level evidence id 可后续扩展，但不得要求 Host
理解 URL、年报章节、chunk、span、row、cell 或其它 locator。

Accepted evidence envelope 至少记录 evidence id、producer event ref、tool name、tool query、
payload ref / digest、outcome digest 与 opaque source / locator descriptor；不记录、派生或暴露有界结果预览字段。
`evidence_id` 由 Host 在
`TOOL_RESULT_ACCEPTED` accept barrier 通过时生成；LLM 不生成 canonical evidence id，tool provider 也不承担 memory fact
生成职责。Accepted evidence envelope 是 provenance anchor，不是 evidence 内容的 lossy 容器；LLM extractor 生成
`claim_text` 时必须读取 compact input 中原本进入会话上下文的 raw tool result / raw transcript，并引用 Host 标注到该 raw
内容旁边的 `evidence_id`。Host 只校验 `evidence_refs` 指向已接受 evidence、`claim_text` 非空且
长度受限、`evidence_kind` 属于允许枚举，以及 candidate 不把 assistant final answer、episode summary、user input 或
working assumption 当作 evidence。Host 不校验 evidence 的业务形状，不解析 locator，不证明 excerpt 逐字覆盖 claim，也不理解
metric / subject / period 的业务含义。

当 compact 输入中存在 accepted evidence，但 LLM extractor 无法形成可接受的 `evidence_backed_fact` candidate 时，Host 不得合成
neutral fallback fact。正确行为是保留 accepted evidence envelope / artifact refs，记录 projection diagnostic、candidate reject
reason 或 bounded repair 结果；episode summary 与 minimum preserve 仍可保留导航和连续性，但不能以 fallback fact 形式进入 stable facts。

`working_assumptions` 承载用户说法、assistant 推断、早期弱信号和待验证候选。它们不能冒充 `evidence_backed_facts`；后续若被用于关键归因，
必须由当前 Run 召回并验证对应工具事实后，才能形成 evidence-backed claim。

`conversation_continuity` 承载最近 raw turns、assistant conclusion、minimum preserve items 与 episode summaries，只服务追问连续性。episode summary
只能做导航，不能替代 evidence anchor、source ref、chunk ref、fingerprint 或 claim status。

`minimum_preserve_items` 是 compact structured output 中的 bounded continuity item，用于保护当前或下一轮追问所需的最小指代解析上下文。
例如用户粘贴长文本并要求提炼三个因素后，下一轮追问“第二个因素”时，minimum preserve 应保留有序 extracted items 中能解析
“第二个因素”的 item，而不是保留整段长 user input。minimum preserve 不属于事实真源，不产生 `evidence_backed_fact`；它只进入
conversation continuity / navigation。

long-session retention / consolidation 是 Conversation Memory 的基本语义，不是后续性能优化：

- `pinned_state` 对 RunInputBuilder 和 compactor 可见时必须是 materialized current state，不是 patch log。
- `working_assumptions` 与 `open_questions` 是当前工作台状态，后续 compact 应合并、解决、过期或降级旧项，不能无限 append。
- `episode summaries` 进入 history pool 后仍需 bounded rendering；较旧 summaries 应 roll up 或只保留 artifact / EventLog refs。
- `evidence_backed_facts` 可以在 durable memory projection 中保存更多历史项，但 ordinary RunInputBuilder 与 compactor input 只能选择
  与当前 pinned subject、current goal、用户问题、近期引用或 policy top-K / size budget 相关的 bounded working set。
- 第一版 consolidation 由 memory projection policy 与 RunInputBuilder / compactor input bounded selection 执行，不要求 compactor 输出
  独立 `memory_retention_candidate`。后续若引入 retention intent，也只能作为 compactor candidate 由 Host accept barrier 与
  memory projection policy 消费，不能让 LLM 直接改写 memory truth。
- `minimum_preserve_items` 与 conversation continuity 是短寿命导航层；如果已被 stable layer 或 episode summary 覆盖，应从可见
  working set 中移除。

RunInputBuilder 注入 memory 的顺序必须体现财报分析优先级：

1. 用户目标与约束。
2. 已确认主体和口径。
3. evidence-backed facts。
4. open questions / working assumptions。
5. recent raw turns。
6. episode summaries。

不变量：

- `pinned_state` 与 evidence-backed stable facts 全量注入，不参与 history pool 竞争。
- `pinned_state` 与 `evidence_backed_facts` 虽不参与 history pool 竞争，但必须有结构化尺寸上限、降级诊断和 trace 记录；不得无限扩大 memory
  挤占财报材料、工具结果、章节上下文和当前问题的预算。
- `final_answer` 是 assistant role 产出的最终回答，只能作为 raw turn / assistant conclusion 参与连续性。
- `final_answer` 绝不能自动升级为 `evidence_backed_fact`。
- `evidence_backed_fact` 只接受 accepted tool evidence refs。
- 缺少可接受的 `evidence_backed_fact` candidate 时只能记录 diagnostic / repair outcome，不得生成 neutral fallback fact。
- 用户输入进入 pinned state、约束或待验证候选，不直接成为 `evidence_backed_fact`。
- memory projection 只消费 canonical facts。
- preview / reasoning / display-only facts 不进入 memory。
- LLM 产出的 pinned patch、episode summary 或 conclusion 默认只能成为 candidate / assumption / continuity view；它们不能直接写入
  Host truth，也不能直接产生 `evidence_backed_fact`。proactive compaction 编排属于 Context Governance。
- RunInputBuilder 渲染 `evidence_backed_facts` 时必须包含 `claim_text` 与 `evidence_refs`，不能只渲染 digest / ref。source /
  locator 细节通过 evidence id 回查 accepted evidence envelope，不要求进入 memory block。
- 第一版 `evidence_backed_facts` 采用 compaction-gated extraction：compact 前不阻塞普通 Run 做 extraction；短链路追问继续依赖
  recent raw turns / older raw turns / 已有 memory。`TOOL_RESULT_ACCEPTED` 后记录 accepted evidence / artifact / refs，供后续
  compact 使用，不要求同步 LLM extraction。
- memory snapshot 是 read model，可重建、可修复，不是事实真源。
- 第一版 memory snapshot 与 projection checkpoint 使用同一 SQLite durable store transaction 提交；checkpoint 不得先于 snapshot 落库。
- 跨存储 atomic commit marker 不进入第一版默认实现，只作为后续 memory storage split 能力。
- RunInputBuilder 消费 memory snapshot 时必须记录 snapshot cursor；后续 replay / audit 能解释当时看到的是哪一版 memory。
- RunInputBuilder 消费 memory snapshot 前必须校验 snapshot cursor 覆盖本次构造 messages 所需的 EventLog cursor。projection lag 不能改变同一 EventLog + policy 下的 messages。
- RunInputBuilder 的 trace / tool trace 必须记录 memory item included / excluded reason、snapshot cursor、policy digest、预算原因、
  stale / conflict / missing-evidence reason。P9 不创建独立 RunInputBuildTrace 子系统。
- recent raw turns floor 是下限保底，不是 history 上限；预算允许时可以注入更多 older raw turns。older raw turns 与 episode summaries
  共享单一 history pool，超预算时先降级 episode summaries / older raw turns，最后才降级 recent raw turns。
- `recent_raw_turns_floor` 保留现有命名，语义是最近 raw turns 的最低保留数量，用于代词指代、局部追问、刚发生的用户输入 /
  assistant conclusion / tool result 展示等交互连续性。它不是 financial fact retention 机制，不保证完整 raw tool transcript
  跨 compact 可见；compact 覆盖范围内的历史事实稳定性由 `evidence_backed_facts` 承担。
- minimum preserve items 只保留指代解析所需的最小 extracted context，不保留整段长输入。Host 只校验 item text 非空且长度受限、
  source refs 指向 compact input、item 数量受 policy 限制、preserve reason 属于允许枚举；Host 不解释 item 业务含义。
- P9 只实现 session-level memory projection 与 provider 边界；长期 retrieval index、业务 signal ledger、signal-to-outcome
  verification 与 public memory edit / reset / forget API 均不进入第一版。

memory snapshot 缺失或滞后的处理：

- snapshot cursor 滞后但 EventLog delta 在 policy 阈值内时，RunInputBuilder 可以从 EventLog canonical facts 重建所需 stable layer，并记录 diagnostic / trace。
- snapshot 缺失、损坏或 lag 超过 policy 阈值时，Host 进入结构化 context governance / projection repair path；dispatch 前的
  catch-up failure 或 lag 超阈值必须先尝试 memory projection rebuild / retry。这不是 Run crash recovery。
- memory projection lag 不得触发 Run 状态迁移，不得把 Run 推入 `RECOVERING`。
- 重建后的 snapshot checkpoint 不得先于 durable snapshot content 落库。

## 25. Context Governance

Context governance 是 Host 责任。Engine 不做 Host-side compact retry，也不理解 Host compaction attempt state machine。

Host 负责：

- provider-aware context budget policy。
- RunInputBuilder 输入层预算分配。
- compact 触发。
- LLM episode summary compaction。
- pinned_state patch。
- evidence-backed fact candidate extraction。
- compact 后保真检查。
- compaction semantic repair / retry 编排。
- failure closeout。
- context overflow retry。
- compact event。
- compact event 与 projection 输入。

Context Governance 是 orchestrator，不直接写 memory snapshot、tool trace、audit projection 或 outbox。它只能 append / request append compact-related canonical facts 或 projection_signal，并通过 typed ports 调用 compactor、budget estimator、RunInputBuilder 和 policy view。memory、trace、audit 等 projection 只从已提交 EventLog 追平。

第一版不实现 provider-specific token counting / provider tokenizer adapter。Context Governance 使用 conservative estimator、provider-aware configured limits 和 safety margin 做 proactive 判断；Engine context overflow event 只是 reactive fallback，不是主要 compaction trigger。provider-specific tokenizer adapter 是后续能力。

`context_window_size` 与 `reserved_output_tokens` 是 Host context policy 的显式 typed input，由 Service / composition root 在装配 Host policy provider 时传入。Host 不从 Engine 反查模型窗口，不从 per-run metadata 或 extra payload 中读取预算参数，也不把 provider overflow event 当作预算真源。pre-dispatch 判断必须先为输出预留 `reserved_output_tokens`，再用剩余输入预算、safety margin 与 conservative estimator 决定是否触发 proactive compact。Runner 返回的 usage 只能作为 post-call observation / diagnostics / policy calibration 输入，不能替代下一次 dispatch 前对当前 messages 的估算。

第一版 policy 默认值与阈值语义：

- `context_window_size` 与 `reserved_output_tokens` 必须为正整数，且 `reserved_output_tokens` 必须小于 `context_window_size`。
- 输入预算先按 `input_budget_tokens = context_window_size - reserved_output_tokens` 计算；输出预留不参与输入层竞争。
- 默认 safety margin 为 20%，即 proactive compact 的 soft threshold 为 `input_budget_tokens * 0.8`。超过 soft threshold 时，Host 应先尝试 compact，而不是直接 dispatch。
- hard threshold 由 policy provider 显式给出或按 `input_budget_tokens` 扣除 policy 定义的最小保护余量后计算。proactive path 在 dispatch 前使用估算输入决定是否禁止 dispatch；proactive compact operation 的 bounded repair attempts 全部耗尽后仍超过 hard threshold 时 append `CONTEXT_COMPACTION_FAILED` 并按 failure policy 收口。reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源；它接受 quality 通过的 compact 结果，随后用真实 recovery dispatch / Engine overflow 闭环判断是否还需要下一次 reactive compact。
- 每个 Run 的 proactive trigger 第一版最多启动一个 compaction operation；reactive trigger 每次 Engine overflow 最多启动一个 operation，但同一 Run 可在 `max_reactive_compactions_per_run` 上限内多次 reactive compact，默认上限为 2。一个 operation 内可以包含 Host-owned bounded semantic repair attempts，但不得启动无界 compact loop。
- `max_compaction_attempts_per_operation` 由 Host context budget policy 显式给出，含第一次 proposal attempt、reactive material
  block pass proposal 与后续 semantic repair attempts，必须为正整数。它控制一次 Host compaction operation 内所有外部 LLM proposal
  调用总数；默认 packaged policy 为 5 次。代码 fallback 默认值与 execution profile 默认值必须保持一致，避免同一 Host 在不同装配路径下出现不同 compact retry 语义。该字段不控制 Engine provider / transport retry，也不允许 Service 提供 prompt、candidate builder 或 repair callback。
- 第一版只记录 usage observation 与 estimator calibration diagnostic，不根据 usage 自动动态调整 policy threshold，避免同一配置下的预算行为不可预测。

Context Governance 与 Conversation Memory 的关系必须保持单向。Conversation Memory 是 EventLog read model，向 RunInputBuilder 提供 memory snapshot、snapshot cursor、policy digest 和 diagnostics；Context Governance 可以读取这些输入来做预算、compact 与质量检查，但不能直接写 memory snapshot，不能让 compacted summary 替代 `evidence_backed_fact` 或 evidence anchor，也不能把 memory projection lag 当作 Run recovery。`WorkingAssumptionView` 的主动填充可以由 proactive compaction 或后续 retrieval owner 通过 canonical facts / projection policy 接入；P10 不得绕过 P9 memory projection 边界直接写入。

P10 必须补齐 stable layer / history pool 的生成来源，而不是只做预算裁剪。第一版 compactor 是 Host-owned typed port，可以调用 LLM compaction scene，但 LLM 只能提出结构化候选；Host 负责校验、接受并写入 canonical compact event / artifact。compactor 输出至少包含：

- episode summary candidate：阶段标题、目标、已完成动作、confirmed fact refs / summaries、用户约束、open questions、next step、tool finding refs。
- pinned state patch candidate：`current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 的字段级 patch；每个字段必须有三态语义：未出现表示不修改，空值表示显式清空，非空值表示替换为候选值。
- evidence-backed fact candidates：基于 compact 输入中的 raw tool result / raw transcript 生成 `claim_text`、
  `evidence_kind`、`evidence_refs` 与可选 opaque attributes。Host 必须把 accepted evidence envelope 的 `evidence_id`
  标注回对应 raw tool result 内容旁边，使 LLM 只负责引用 Host 已给出的 evidence id；不得让 LLM 从 tool query 自行生成 canonical
  evidence id，也不得让 lossy preview 替代原始 evidence 内容。它们与 episode summary / pinned state patch 可由同一次 structured JSON
  proposal 产生，正常 compact 路径不得因此固定增加第二次 LLM 调用。
- minimum preserve item candidates：当前追问或下一轮短链路追问中，理解代词、序号、局部承接所需的最小 continuity items。每条至少
  包含 item id、label、text、source refs 与 preserve reason；它们可与 episode summary / pinned state patch / evidence-backed fact
  candidates 由同一次 structured JSON proposal 产生。
- preservation evidence：每条 summary / patch candidate 对应的输入 event refs、tool fact refs、memory snapshot cursor 或 compact input range。
- quality check result：是否保留 current user input、accepted tool fact refs、evidence anchors、open questions / assumptions refs，以及 dropped / summarized ranges。

Host 接受 compactor 输出后，`CONTEXT_COMPACTED` payload 必须记录 compact artifact ref、episode summary candidate、pinned state patch candidate、evidence-backed fact candidates、minimum preserve item candidates、preserved fact refs、dropped / summarized ranges、quality check result 与 budget after compact。是否将 episode summary / pinned patch / evidence-backed fact candidates / minimum preserve item candidates materialize 到 Conversation Memory，由 memory projection policy 消费已提交 canonical facts 决定；Context Governance 不得直接写 memory snapshot、memory table 或 RunInputBuilder 私有 message 缓存。

Compactor 与 retry / repair 的 owner 边界固定为：

- Runner/provider 层负责低层 transport retry：network、timeout、HTTP 429、HTTP 5xx、stream idle timeout 等由 Engine Runner 按 `RunnerSpec.max_retries`、`Retry-After` 与退避策略在一次 compactor proposal 调用内处理。该层 retry 不拥有 Host governance，不 append EventLog，不 emit HostEvent，只通过 RunnerEvent / log / attempt summary 进入 Host diagnostic。
- `LLMContextCompactor` 是 Host-owned 单次 proposal executor。它把 immutable `CompactionRequest`、Service 从 `compactor_baseline.scene_id` 指向的 scene 装配后传入的 system prompt / `AgentPolicy`、Service 从 `compactor_baseline.user_prompt_template_path` 指向的 prompt asset 读取后传入的 user prompt template，以及 Host lifecycle cancellation token 映射为一次 structured JSON LLM proposal，并返回 episode summary、pinned state patch、evidence-backed fact candidates、minimum preserve item candidates、preservation / diagnostic candidate 或 typed failure；它不决定是否重试、不更新 Run / Attempt、不写 EventLog、不写 artifact、不做 memory projection，也不得自行构造不可取消 token。Host 只把 request 渲染为 typed data block 并替换 user template 中的 compaction request 占位符，不从 config 读取 prompt asset。
- Host Context Governance 拥有 semantic repair / retry：非 final answer、空 summary、解析失败、candidate shape 非法、缺 preservation evidence、quality check reject、compact 后仍超过 hard threshold 等，都由 Host compaction operation 决定是否发起 bounded repair attempt。repair attempt 必须复用同一个 immutable compaction request、同一套 Host-owned scene、同一 durable operation id，并在每次外部 LLM call 前后 recheck Run / Attempt / Session / cursor state。
- stale / cancelled / session closed / execution replaced / cursor mismatch 不是可 repair 错误；Host 必须丢弃 stale proposal，不写 `CONTEXT_COMPACTED`。proactive compaction 在 worker 启动前没有 active worker token，必须使用 durable Run 状态观察 token；reactive compaction 必须复用 Engine envelope 中的 run-local cancellation token。
- retry budget 耗尽后只允许写一个最终 `CONTEXT_COMPACTION_FAILED`，不能让 Service replay，不能让 Engine retry Host governance，也不能无限 compact。

LLM compaction repair 耗尽或 compactor 不可用时，Host 可以进入 deterministic recent-window fallback。该 fallback 不是
compact 成功，不提交 `CONTEXT_COMPACTED`，不生成 episode summary、minimum preserve、pinned state patch 或
`evidence_backed_fact`，也不写 memory projection。它只为本次 dispatch 构造类似首次 compact 前的 bounded RunInputBuilder
输入视图：当前用户输入、最新 N 轮 raw turns、至少 M 轮 recent raw floor、已有 stable facts、answer anchors、open task
state，以及必要 evidence / artifact / tool result refs。fallback 必须写 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic，
并标明本次 dispatch 使用了 recent-window fallback；记录内容至少包含 compact failure reason、fallback policy
decision、fallback input window / digest、重新估算后的 budget result 和 diagnostic refs。fallback 后必须重新估算预算；
若该 bounded input view 仍超过 hard threshold，Host 不得 dispatch，必须按 failure policy 收口。fallback 读取已有
facts / refs，但不得把 refs 或 raw turns 提升为新的 stable facts。

Compaction operation 的 durable 语义固定为：

```text
CONTEXT_COMPACTION_REQUESTED(operation_id, trigger_source, budget snapshot, input cursor)
  -> attempt 1: LLM proposal outside write transaction
  -> Host quality / budget gate
  -> optional CONTEXT_COMPACTION_ATTEMPT_REJECTED(attempt_no, category, diagnostic refs)
  -> optional bounded repair attempt N
  -> CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
```

`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 是 Host governance diagnostic canonical fact，用于回答尝试次数、失败类别、是否 exhaust budget 和最终接受的是哪次 attempt。EventLog 不能包含 API key、headers、完整 raw prompt 或完整 provider payload；大 payload、raw candidate、provider error body 或 repair prompt 如需保留，必须写 artifact / diagnostic ref 并做敏感信息过滤。

HostEvent 暴露粒度必须比 EventLog 克制：`CONTEXT_COMPACTION_REQUESTED`、最终 `CONTEXT_COMPACTED`、最终 `CONTEXT_COMPACTION_FAILED` 应作为 Service-facing HostEvent 可观察；Host-level repair attempt rejected / retry scheduled 可以作为 typed diagnostic/progress HostEvent 暴露，但不得把每一次 Engine runner HTTP retry 变成 public HostEvent。低层 provider retry 只进入 runner log / aggregated diagnostics。

stable layer / history pool 的来源按事实等级固定：

- `pinned_state.current_goal` 与 `pinned_state.user_constraints` 可由 `USER_INPUT_ACCEPTED` 的确定性投影初始化，也可由 P10 accepted pinned state patch candidate 后续修正。
- `pinned_state.confirmed_subjects` 与 `pinned_state.open_questions` 主要来自 P10 accepted pinned state patch candidate、用户显式确认或后续 steer / goal-change owner；不得仅凭未校验 LLM 文本直接写入。`confirmed_subjects` 的 replace 值必须是 Host-neutral opaque ref 文本，例如 `subject:...`、`entity:...` 或 `topic:...`，不能接受自然语言、ticker、marker 或没有 kind 前缀的字符串。
- `evidence_backed_facts` 只来自 accepted evidence refs。compact 前不阻塞普通 Run 做 extraction；compact 时复用同一次 structured JSON proposal 生成 `evidence_backed_fact_candidates`。本次 compact 覆盖范围内的历史 evidence-backed claims 在 compact 后通过 accepted `evidence_backed_facts` 进入 stable memory，不再依赖 compact 前 raw turns 或 episode summary 复原；compact 后新产生的 user input、assistant answer、tool result 继续作为新的 raw turns / accepted evidence 进入后续 memory pipeline。
- P10 episode summary 中的 confirmed facts 只能引用或摘要已存在 facts / evidence refs，不能新建 `evidence_backed_fact`，也不能替代 `evidence_backed_fact`。
- `conversation_continuity` 的 raw turns 来自 `USER_INPUT_ACCEPTED` 与 `RUN_SUCCEEDED`；episode summaries 与 minimum preserve items 来自 accepted compact output，并继续只作为 continuity / navigation，不替代 evidence anchors 或 `evidence_backed_facts`。

Compaction request 的输入边界固定为 compact material pack，而不是从 Session 起点重放 EventLog ledger。一次 compactor run 的
messages 只能由 compactor system prompt 和一个 user material pack 组成；material pack 是 Host 对 memory / history /
evidence / current input anchor 的去重、分段、可读投影，不承载 Host 内部账本 dump。

material pack 至少包含：

- `stable_input`：bounded `pinned_state`、`evidence_backed_facts`、`working_assumptions` 与 `open_questions`。
- `history_input`：compact segment 内的 recent raw turns、older raw turns、assistant terminal continuity、compact segment 新产生的
  episode summaries，以及 policy 允许的 bounded recent episode summaries；超出 policy 上限或与本次 segment 无关的较旧 summaries
  只保留 artifact / EventLog refs。
- `evidence_input`：compact segment 内 accepted tool results 的 prompt-local evidence blocks，每个 block 包含可读 tool query、
  raw result 或必要 raw transcript、可读 source / locator 和短 label，例如 `E1`。
- `current_input_anchor`：当前输入的 ref、短文本 / 摘要 / digest 与 retention check 所需边界信息；它不能重复承载完整当前
  user payload。

compact segment 是从 ordinary run input material list 或 reactive overflow material list 中选择的可压缩 material block 集合，
不是 EventLog 全量 range。segment selection 必须满足：

- proactive path 的 segment 上界是当前待 dispatch ordinary input 中除 `current_input_anchor` 与 protected recent raw turns floor
  之外的 history / evidence material；目标是压缩旧 prefix，为当前 Run dispatch 腾出预算。
- proactive path 的 segment 下界从当前 ordinary input 中最旧、尚未被 accepted compact output 的 stable layer / episode summary
  充分代表的 material block 开始；已 compact 且仅以 summary / stable facts 进入 ordinary input 的旧 range 不应重新展开。
- reactive path 的 segment 来自被冻结的 overflow ordinary input material list，优先选择 older prefix；suffix 中的 current input
  anchor 与 protected recent raw turns 必须保留到后续 pass 或 recovery dispatch。
- segment selection 按 material block 与 token / budget 压力裁剪，不按固定轮数裁剪；一轮中包含的长 tool result 可以单独形成
  evidence block 或 evidence-block 内部分段。
- 给定 input cursor、memory snapshot cursor、policy 与 ordinary input material list，segment selection 必须确定性输出本次进入
  `history_input` / `evidence_input` / `current_input_anchor` 的 block ids，供 tests、trace 与 audit 解释。

material pack builder 的 section 映射必须是一对一分类，不允许同一 canonical content 同时进入两个 LLM-facing section：

- `stable_input` 只来自 memory snapshot 的 bounded stable layer view，以及 policy 允许的 inline delta repair view。
- `current_input_anchor` 来自当前 `USER_INPUT_ACCEPTED` 的 bounded anchor；同一 current user payload 不得再作为 `history_input`
  raw turn 渲染。
- `history_input` 渲染 user / assistant continuity 与 non-evidence raw turns；accepted tool result raw content 不在 history section
  中重复出现。
- `evidence_input` 渲染 accepted tool evidence block。raw evidence 内容来自 compact segment 内 `TOOL_RESULT_ACCEPTED` canonical fact
  所引用且 digest 校验通过的 Host payload / raw result descriptor；accepted evidence envelope 只提供 evidence id、query /
  provenance mapping 与 source locator metadata，不作为 lossy result preview 或事实内容容器。
- `accepted_evidence_envelope`、payload ref、artifact ref、digest、event id、cursor 与 policy snapshot 只能作为 Host 内部映射、
  trace、audit 或 validation 输入，不能代替 LLM-facing raw result / transcript。

material pack build 启动前必须校验 memory snapshot cursor。若 snapshot cursor 不能覆盖构造 `stable_input` 和 compact segment 所需的
EventLog cursor，Host 必须先执行 memory projection catch-up / rebuild 或在 policy 允许范围内做 inline delta repair；失败时按
compaction failure / pre-dispatch failure 收口。这不是 Run crash recovery，不得把 Run 推入 `RECOVERING`。

Host 必须同时维护 prompt-local label 到 canonical provenance 的内部映射，例如 `E1 -> TOOL_RESULT_ACCEPTED event ->
TOOL_CALL_REQUESTED event -> payload / artifact / source locator refs`。该映射用于 accept barrier、audit 与 rebuild，不作为
LLM 主要语义输入。compact material pack 不得包含 full EventLog range wrapper、裸 event id / payload ref / digest /
cursor / policy / artifact descriptor 作为模型阅读主体，也不得重复渲染同一 current input、raw turn 或 raw tool result。
当单条 accepted evidence 被 chunk 成 `E1.1`、`E1.2` 等子 label 时，Host proposal parser 可以把父 label `E1`
解析为同一 canonical evidence 的 shorthand；该 shorthand 只允许用于 evidence section，仍必须拒绝未知 label 或跨 section label。

proactive compact 的安全条件是：compactor material tokens 必须与触发 compact 的 ordinary input material 属于同一去重视图，
不得显著大于 ordinary run input material。Context Governance 必须按即将发送给 compactor 的真实 messages 估算 budget；若
proactive material pack 仍超过 hard budget，优先判定为 segment selection 或 material pack builder 错误，并通过 bounded
repair / failure policy 收口，不能盲打 provider。

reactive compact 来自 provider context overflow，不能把已经 overflow 的 ordinary messages 原样一次性交给 compactor。Host 必须冻结
overflowed ordinary input material list，优先压缩 older prefix，保留 recent raw turns 与 current input anchor；若完整 material
list 仍超过 compactor budget，应按 compact material block 分段多 pass 压缩。分段单位是 turn block、evidence block、episode summary
block、stable layer block 与 current input anchor，而不是固定轮数。若单个 evidence block 自身超过 compactor budget，必须在同一
canonical evidence provenance 下做 evidence-block 内部分段。reactive path 不依赖估算证明成功，而是通过 bounded multi-pass compact
与真实 recovery dispatch / provider overflow 闭环收敛，超过 `max_reactive_compactions_per_run` 后 fail closed。

reactive multi-pass 是同一个 compaction operation 内的 material block batch processing，不追加新的
`CONTEXT_COMPACTION_REQUESTED`，也不单独消耗 `max_reactive_compactions_per_run`。每个 pass 的外部 LLM proposal 消耗
`max_compaction_attempts_per_operation` 预算。中间 pass 的 compact 产物只能作为 operation-level transient artifact 或 diagnostic
artifact 暂存；Host 只能在所有 required passes 通过 quality / budget gate 后提交一个合并的 `CONTEXT_COMPACTED`。若中间 pass
失败且 repair budget 耗尽，整个 operation 写入一个最终 `CONTEXT_COMPACTION_FAILED`，不得提交孤立的 partial compacted event，
memory projection 也不得消费中间产物。

### 25.1 Compact Event 响应路径

context compaction 有两类触发来源：

- proactive trigger：Host / RunInputBuilder 在 dispatch Attempt 前根据 provider-aware budget、tool facts、memory snapshot、当前用户输入和场景参数判断下一次 provider call 可能超过 policy 阈值。
- reactive trigger：Engine 在 Runner 报告 context length exceeded 后 emit `context_compaction_requested` EngineEvent，并以 recoverable `run_failed(context_compaction_required)` 收口本次 Engine run。

compact 是 Host governance，不是 Engine retry。proactive 与 reactive 使用不同状态路径：

```text
proactive trigger before dispatch
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)
  -> Host ContextGovernance runs bounded compaction operation outside write transaction
  -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
  -> if compact failed and policy allows fallback: build deterministic recent-window input view and re-estimate
  -> RunInputBuilder rebuilds complete AgentRunRequest.messages
  -> append RUN_STARTED / ATTEMPT_STARTED
  -> dispatch Engine

reactive trigger from EngineEvent.context_compaction_requested
  -> validate attempt_id + execution_id
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)
  -> close current Attempt according to policy
  -> Run -> RECOVERING when policy allows recovery
  -> Host ContextGovernance runs bounded compaction operation outside write transaction
  -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
  -> if compact failed and policy allows fallback: build deterministic recent-window input view and re-estimate
  -> append RUN_STARTED(start_reason=recovery)
  -> create new Attempt with new execution_id
  -> append ATTEMPT_STARTED
  -> dispatch Engine again
```

proactive path 是 pre-dispatch input governance，不表示旧 Attempt orphan，也不要求 Run 进入 `RECOVERING`。reactive path 才复用 `RECOVERING` 与 `RUN_STARTED(start_reason=recovery)`。

reactive path 约束：

- Host 必须先按 `attempt_id + execution_id` 校验 `context_compaction_requested` 是否来自当前 active Attempt。
- Engine 后续的 recoverable `run_failed(context_compaction_required)` 只能关闭当前 Attempt；它不能让 Engine 自己重试，也不能让旧 Attempt resume。
- Host 若接受恢复，应把 Run 标为 `RECOVERING`，执行 compact 后创建新 Attempt；若 compact policy 放弃恢复，Run 才进入 `FAILED`。
- proactive compact failure 在 dispatch 前优先尝试 deterministic recent-window fallback；fallback 预算通过时允许创建 Attempt，但不得写 `CONTEXT_COMPACTED` 或 memory projection。fallback 仍超预算或 policy 不允许 fallback 时，Run 按 failure policy 收口，后续引入 `REJECTED` 后应归入 governance rejection，不得进入 `RECOVERING`。
- reactive compact failure 发生时当前 Attempt 已按 policy 关闭；Host 可按 policy 尝试 deterministic recent-window fallback，并创建新的 recovery Attempt。fallback 仍超预算或 policy 不允许 fallback 时，Run 进入 `FAILED`。`LOST` 只属于 Phase 11 recovery / positive orphan proof owner，P10 不得用 compact failure 伪造 `LOST`。
- `CONTEXT_COMPACTION_REQUESTED` payload 至少记录 operation id、trigger source、provider / runner error refs、provider request id、budget snapshot refs、input snapshot cursor、retry / repair budget snapshot 和 reason。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 至少记录 operation id、attempt number、failure category、whether repairable、runner attempt summary refs、quality / parse / budget diagnostic refs 和 next policy decision。
- `CONTEXT_COMPACTED` payload 至少记录 operation id、accepted attempt number、compact artifact ref、episode summary candidate、pinned state patch candidate、evidence-backed fact candidates、minimum preserve item candidates、preserved fact refs、dropped / summarized ranges、accepted evidence refs / prompt-local label mapping refs、quality check result、budget after compact。
- `CONTEXT_COMPACTION_FAILED` payload 至少记录 operation id、failure reason、policy decision、whether retryable、attempt count、retry / repair budget exhausted 标记和 diagnostic refs；若 policy decision 采用 deterministic recent-window fallback，还必须记录 fallback input window / digest、fallback budget result，以及 fallback 后是 dispatch 还是 fail closed。

compact 不变量：

- compact 不能改写历史 EventLog facts，也不能让 summary 替代 evidence anchor。
- compacted snapshot / summary 是 read model 或 input artifact；是否进入 memory projection 必须由 memory policy 决定。
- RunInputBuilder 必须从 `USER_INPUT_ACCEPTED`、canonical facts、memory snapshot 和 compacted artifacts 重建完整 messages；不能复用失败 Attempt 的 provider request payload。
- deterministic recent-window fallback 只能影响本次 RunInputBuilder 输入选择，不得改写 EventLog 历史事实，不得提交 `CONTEXT_COMPACTED`，不得 materialize memory snapshot；但它必须有 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 痕迹，不能静默发生。
- 新 Attempt 必须有新的 `attempt_id` / `execution_id`；旧 Attempt 不 takeover、不 resume。
- compact 必须有 policy 上限。proactive operation 内 bounded repair attempts 耗尽后，Host 必须 append `CONTEXT_COMPACTION_FAILED`；若 deterministic recent-window fallback 预算通过，可继续 dispatch，否则按 failure policy 收口。reactive path 中 compact 后若真实 recovery dispatch 再次触发 Engine overflow，可在 `max_reactive_compactions_per_run` 范围内追加下一次 reactive compact；超过上限后 append `CONTEXT_COMPACTION_FAILED`，可按 policy 尝试 deterministic recent-window fallback，仍失败则让 Run 进入 `FAILED`。不得进入 `LOST`，不得无限 compact retry。
- tool trace / audit 必须能解释哪些内容被保留、压缩、丢弃，以及为什么这样做。

参数默认值由 memory / context policy provider 定义。设计固定治理范围，policy 固定优先级和默认值。

provider tokenizer adapter 是 Host 预算治理的后续精确能力，不进入第一版。第一版 proactive path 使用保守 token estimator，阈值必须留出 safety margin；provider 返回 context length exceeded 仍是 reactive fallback，不是 proactive compact 触发机制。reactive path 不依赖估算证明 compact 后一定可 dispatch，而是通过最多两次真实 recovery dispatch 闭环收敛，超过上限后 fail closed。

## 26. Evidence / Retrieval / Long-term Memory

长期 memory 不在第一版实现。第一版只做 session memory 与当前 run 的 context governance，但设计不得封死长期记忆。

跨多年弱信号归因靠证据链和 query-time retrieval，不靠无限扩大 session memory。

边界：

- Host 提供 evidence anchor、provenance、事实候选 / 验证标记等中立骨架。
- 原始网页新闻、公告、研报摘录、财报 chunk、source metadata、业务 event type、company / product / business-line ref 由业务工具和财报领域仓储管理。
- 早期 signal 进入 assumption / candidate，不因 summary 或 memory 收录变成 verified attribution。
- 后续分析通过 query-time retrieval 召回 signal anchors / evidence chunks / prior assumptions。
- 长期 summary 只能做导航；关键归因必须追到当前 run 已召回并验证过的工具事实。
- 召回失败、证据不足、证据冲突、signal stale、预算未纳入 RunInput 时，tool trace / trace 必须能解释。

## 27. Host Lifecycle / Recovery

Host 启动时必须执行 recovery scan：

- `ACCEPTED` Run 保持 `ACCEPTED`，等待 scheduler / pre-start governance；它不是 orphan Attempt，不得进入 `RECOVERING`。
- `QUEUED` Run 保持 `QUEUED`，等待调度。
- `WAITING` Run 保持 `WAITING`，等待 wait record resolution。
- `RUNNING` / `CANCELLING` Run 的 active Attempt 只有在具备 positive orphan proof 时，才能进入 `LOST`。
- 若 Run 的用户输入和必要 canonical facts durable accepted，Run 进入 `RECOVERING`。
- 若必要 facts 缺失或 policy 放弃恢复，Run 进入 `LOST`。

Recovery scan 不得让旧 Attempt takeover。恢复必须创建新 Attempt。

Recovery 的输入只能是 Host durable truth：Run / Attempt indexes、EventLog canonical facts、dispatch record、wait record、payload descriptors 和 host instance liveness record。Projection checkpoint、Session timeline、RunResult、audit、tool trace、outbox、memory snapshot lag 或其它 read model 不能作为 recovery scan 的前置条件或事实依据；这些 projection 只能在 recovery 提交 canonical facts 后按 `event_sequence` 追平。

Recovery scan semantic path：

```text
Host startup
  -> read Run / Attempt indexes
  -> classify each non-terminal Run
  -> append ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST when needed
  -> keep QUEUED and WAITING in place
  -> for recoverable RECOVERING Run:
       -> rebuild messages from canonical facts
       -> append RUN_STARTED(start_reason=recovery)
       -> create new Attempt(status=STARTING)
       -> append ATTEMPT_STARTED
       -> dispatch after commit
  -> trigger queue promotion after terminal / recovery transitions
```

分类规则：

- `QUEUED`：不触发 Engine dispatch；只等待 admission promotion。
- `WAITING`：不创建 Attempt；只恢复 wait adapter observation。
- `RUNNING` / `CANCELLING` 且存在当前 Host 可确认控制的 dispatch record：继续观察，不接管。
- `RUNNING` / `CANCELLING` 且属于其它存活 Host instance：跳过 recovery，不 append `ATTEMPT_LOST`，不创建新 Attempt。
- `RUNNING` / `CANCELLING` 且具备 positive orphan proof：通过 CAS 将旧 Attempt -> `LOST`；Run 按 policy 与事实完整性进入 `RECOVERING` 或 `LOST`。
- `RUNNING` / `CANCELLING` 且只能判断 owner heartbeat stale，但无法证明 owner 进程已死：记录 suspect / diagnostic，跳过 recovery。
- `RECOVERING`：继续按 recovery policy 创建新 Attempt，或因超过上限进入 `LOST`。

Phase 11 第一版 startup recovery policy：

- `ACCEPTED`、`QUEUED` 与 `WAITING` 都不是 orphan Attempt，不得因 Host startup scan 被推进到 `RECOVERING`。
- `RUNNING` / `CANCELLING` 的旧 Attempt 只有在 positive orphan proof 成立后才能写入 `ATTEMPT_LOST`；随后如果用户输入、payload descriptor、tool fact reuse policy、memory / compact input refs 等必要 canonical facts 足以重建 messages，则 Run 进入 `RECOVERING`，否则进入 `LOST`。
- `RECOVERING` Run 在未被用户取消且未超过 recovery policy 上限时，创建新的 Attempt 与新的 `execution_id`，并以 `RUN_STARTED(start_reason=recovery)` 重新派发；不得恢复旧 Engine / Agent / Runner / provider request。
- 第一版每个 Run 最多允许一次 automatic startup recovery dispatch。若再次 startup scan 发现同一 Run 已消耗该上限，必须以结构化 reason 将 Run 收口为 `LOST`，不得无限创建新 Attempt，也不得伪造 `FAILED` 或 successful final answer。
- owner heartbeat stale 但 positive orphan proof 不成立时，只能追加或投递 suspect diagnostic，不得写 `ATTEMPT_LOST`、`RUN_RECOVERING`、`RUN_LOST`，也不得取消或接管旧 Attempt。

多进程 recovery 不得把“当前进程不可确认控制”当作 orphan proof。一个 Host 进程无法控制另一个 Host 进程持有的 LocalProxy / RemoteProxy channel，并不表示该 Attempt 已丢失。

positive orphan proof 第一版来自本机 Host 进程存活证据，而不是远端 lease。推荐最小机制：

```text
dispatch_record.owner_host_instance_id
  -> host_instance durable row:
       host_instance_id
       pid
       process_start_token / boot_id / create_time
       heartbeat_at
       status
```

orphan 判定必须同时证明 owner Host instance 已不可能继续治理该 Attempt，例如 pid 已不存在，或 pid 已复用但 process_start_token 不匹配，并且 heartbeat 已过期。`heartbeat_at` 单独不构成 orphan proof；进程卡顿、调试暂停或长时间阻塞不能导致其它 Host 进程误杀 active Attempt。`pid` 单独也不构成 orphan proof；pid 可能复用，必须配合 process_start_token / boot id / create time 等启动指纹。

第一版 positive orphan proof 的最小判定必须同时满足：

- dispatch record 能关联到旧 Attempt、`owner_host_instance_id` 与 durable host instance row。
- owner heartbeat 已超过 recovery policy 的 stale threshold。
- 本机进程证据能证明 owner pid 已不存在，或 pid 已复用且 `process_start_token` / `boot_id` / `created_at` 启动指纹与 durable row 不匹配。
- CAS recheck 时 Run / Attempt / dispatch record 仍与分类输入一致。

任一条件缺失都只能得到 suspect / inconclusive 结论，不得推进 recovery。

只有 positive orphan proof 成立后，才能 CAS `ATTEMPT_LOST` -> `RUN_RECOVERING` -> new Attempt。该机制不是重 lease / fencing：它不授予远端执行 ownership，不允许旧 Attempt takeover，只用于证明原 Host owner 是否已经不可能继续治理该 Attempt。

Host instance liveness foundation 的最小边界：

- host instance liveness record 是 durable foundation primitive，不是 lease、fencing token、Attempt owner 或 takeover grant。
- Phase 2 只需要提供 register current instance、heartbeat current instance、mark stopping / stopped best-effort、read instance row 的持久化 primitive。
- host instance row 最小字段包括 `host_instance_id`、`pid`、`process_start_token`、`boot_id?`、`created_at`、`heartbeat_at`、`status`。`status` 只表达本机 Host instance 的生命周期诊断，例如 `running`、`stopping`、`stopped`、`crashed_suspected`；不得被解释为远端执行 ownership。
- heartbeat 只能刷新当前 Host instance 自己的 row；不得刷新其它 instance，也不得因 heartbeat stale 自动标记其它 instance 的 Attempt 为 `LOST`。
- positive orphan proof classifier、dispatch record join、Attempt `LOST` CAS、Run `RECOVERING`、新 Attempt 创建属于后续 recovery / state machine phase。Phase 2 不实现 orphan classifier，不引入 lease / fencing，不允许旧 Attempt takeover。

### 27.1 已接受 Prompt 的恢复语义

用户可见目标：

```text
用户已经提交 prompt
  -> Host 已 durable append USER_INPUT_ACCEPTED
  -> LLM 尚未返回 final answer
  -> Host 崩溃 / 进程退出 / Host opener 正常 close 后重启
  -> Host 重启后仍应最终产出 answer
```

系统真实语义：

```text
USER_INPUT_ACCEPTED durable accepted
  -> old RUNNING / CANCELLING Attempt marked LOST only after positive orphan proof
  -> Run enters RECOVERING when recovery policy allows
  -> RunInputBuilder rebuilds complete AgentRunRequest.messages from EventLog
  -> Host creates new Attempt + new execution_id
  -> Host dispatches Engine again
  -> final_answer is accepted into EventLog / RunResult
  -> final answer is visible through Host event stream / read model
  -> Outbox terminal delivery item can be derived for offline / external delivery
```

不变量：

- 用户 prompt 只有在 `USER_INPUT_ACCEPTED` 已提交后才具备恢复语义；若崩溃发生在 durable append 之前，Host 没有事实真源，不能凭空恢复这次输入。
- Recovery 不恢复旧 Engine / Agent / Runner / provider request，也不接管旧远端 worker；旧 Attempt 只有在 positive orphan proof 成立后才能进入 `LOST`。
- Host opener 正常 close 若在 terminal 到达前停止本地 worker，只能传播 lifecycle cancel 与关闭本地 runtime，不能写用户 cancel facts；重启后由 owner `STOPPED` lifecycle proof 直接推进 recovery。若进程停在 `STOPPING` 后崩溃，startup recovery 必须等待 heartbeat stale 且 pid missing / identity mismatch 等进程证据成立后再推进 recovery，避免抢正在正常关闭的旧 Host。
- 若 terminal event 在 close lifecycle cancel 前已经到达并完成 ingest，answer 已经由正常 terminal closeout 产出，后续由 Outbox / read model 处理可见性，不再走 recovery 重放。
- 新执行必须基于 EventLog canonical facts 重建完整 messages，并创建新 Attempt / 新 `execution_id`。
- 用户不需要感知 Run / Attempt 细节；用户可见语义是“已提交 prompt 不丢，之后仍能收到 answer”。
- 如果 recovery policy 放弃恢复、必要 facts 缺失、重复恢复超过限制或后续新 Attempt 失败，Run 应进入结构化 `FAILED` / `LOST`，不能伪造成功 answer。

attempt dispatch record 最小语义：

```text
owner_host_instance_id
run_id
attempt_id
execution_id
worker_kind: local | remote
dispatch_started_at
last_event_at?
connection_state?
```

dispatch record 不是 lease，也不是 fencing token。它帮助 Host 识别本次 Attempt 的 owner Host instance、执行通道和诊断状态。当前进程不能确认控制该 dispatch record 时，只能说明当前进程不能接管；不能单独证明旧 Attempt 已丢失。

`host_instance_id` 是 Host 进程启动时生成的本进程实例标识，用于 host instance liveness record 与 dispatch record 关联。它不是 lease、不是 fencing token、不是远端 owner。相同 `host_instance_id` 本身也不能授权 takeover；positive orphan proof 只能证明原 owner 已不可能继续治理，不能允许接管旧 Attempt。

Host graceful shutdown：

- 停止接收新的 prompt admission。
- 尽力向 active Attempt 传播 cancel / shutdown signal。
- 持久化 shutdown diagnostic fact 或 projection diagnostic。
- 不得伪造成功 terminal。

shutdown grace timeout 由 shutdown policy 配置。

## 28. 第一版 Non-goals

第一版不实现：

- 长期 memory public edit / reset / forget API。
- 完整远程 wire protocol 细节。
- 强制终止远程执行环境和复杂 job reconcile。
- 重型消息系统。
- 重 lease / fencing 系统。
- 业务层财报语义抽取。
- 外部渠道投递保证高于 outbox retry 语义。

这些 non-goals 不能削弱第一版的 durable facts、admission、EventLog、cancel 最小收口、resume、新 Attempt 语义和本地多进程一致性。
