# Host 设计

本文档是 Host 唯一设计真源。稳定架构边界、公共接口、状态机、EventLog 语义、恢复语义、执行路径、工具治理、memory / context governance 与后续 public contract 决策只以本文档为准。

## 1. 设计目标

Host 的设计目标是支撑生产级通用 Agent，具备买方财报分析能力。系统范式是“宿主强约束下的 LLM in the loop”：

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
- Conversation Memory：只消费 committed canonical EventLog facts 与 accepted compact projection，维护 session memory snapshot 的五类会话语义视图；它是可重建 projection / read model，不是事实真源，不直接写 EventLog，也不由 Context Governance 直接写入。
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

本地 Config 与 Host SQLite / EventLog 属于同一受信任产品域。Service / execution environment 仍是 secret 解析 owner：它从 typed config 与当前运行环境解析 provider secret，并把解析后的 headers / API key 作为完整 typed `RunnerSpec` 的执行字段交给 Host。Host 可以接收该 resolved typed input，并把一次 Run 实际采用的 effective `RunnerSpec` 原样冻结到内部 durable canonical fact，供 dispatch、retry、replay 与 recovery 使用。这个内部持久化副本不是 public contract，也不得被直接复用为 Tool Trace、audit、HostEvent、outbox、memory、compact、runner-call observation、LLM-facing 文本或日志的输出 payload；这些 projection 必须只从各自 owner 的显式安全字段派生，且不得包含 provider secret 明文。

Config catalog 的 record id 由顶层 map key 提供，record 内不重复 `runtime_id`、`model_id`、`profile_id`、`execution_profile_id` 等 id 字段；typed config view 如需 id，由 ConfigLoader 从 map key 注入。`extends` 引用同一 catalog 的 map key；ConfigLoader validation 不接受重复 id 字段，避免 key / value 不一致和新旧 schema 并存。

`models.json` 是模型目录，只表达 provider / model 能力与请求基础参数：runner kind、provider、model、endpoint、`api_key_ref`、headers、tool calling / streaming / stream usage capability、default timeout、max retries、SSE idle timeout / heartbeat、provider request extension、context window tokens 与 provider/model-specific `runtime_hints.runner_option_hints`。`runner_option_hint_id` 是 semantic call style selector，例如 `interactive`、`overview`、`audit`、`decision`、`write`、`infer` 与 `conversation_compaction`；具体 `temperature`、`top_p`、`stream` 等 RunnerCallOptions 值由 effective model 的 hint 表解释，不放入全局 execution profile。默认 config 不使用 `max_tokens` 限制模型输出；若未来需要输出 token cap，必须作为显式 per-run / provider adapter override 或 provider-specific public contract 重新设计，不能回到默认 model hint。

`execution_profiles.json` 表达 execution baseline 与治理策略选择。顶层 selector 使用 `default_execution_profile_id`，catalog 使用 `execution_profiles`；默认 profile id 可以按场景与窗口分档，例如 `standard-256k`、`standard-1m`、`wechat-256k` 与 `wechat-1m`。单个 execution profile 至少包含 `run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy` 与内嵌 `agent_policy`。`run_baseline` 保存默认 `model_id` 与 `runner_option_hint_id`；`compactor_baseline` 保存 compactor 专用 `model_id`、`scene_id`、`runner_option_hint_id`、`user_prompt_template_path` 与 artifact root，默认 compactor scene、runner hint 与 user prompt template 分别为 `conversation_compaction`、`conversation_compaction` 与 `scenes/conversation_compaction_user.md`。默认 compactor model 由 execution profile 的 `compactor_baseline.model_id` 表达；packaged 默认应选择低延迟 flash-tier 模型，因为 compact 是低温度、无工具、结构化 JSON proposal 任务，优先需要快、稳定、可重试。高规格 compact 模型只能由 profile 显式选择，不由 scene 或 Host 代码隐式切换。`conversation_compaction` scene manifest 中若保留 `model.default_model_id`，其 packaged default 必须与默认 execution profile 的 compactor model 对齐，或被明确标记为非治理 fallback；不得与 profile 默认给出互相矛盾的 compactor model truth。compactor 的 system prompt、AgentPolicy 与 user prompt template 不写在 Host 或 Service 代码中；Service / composition root 必须按 `compactor_baseline.scene_id` 装配 compactor scene asset，从 scene 读取 compactor system prompt 与完整 `agent_policy`，并按 `compactor_baseline.user_prompt_template_path` 读取 user prompt template，然后作为 typed `CompactorRunnerBaseline` 字段传入 Host。普通 `agent_policy` 一比一对齐 Engine / Host public `AgentPolicy` typed shape，使用 `max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt` 与 `max_consecutive_failed_tool_batches` 等稳定字段；`fallback_mode` 只允许 `force_answer` / `raise_error`，默认 `force_answer`，默认 `fallback_prompt` 为“请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。”。`execution_profiles.json` 不保留顶层 `agent_policy_profiles` catalog、`agent_policy_profile_id`、`runner_options_profiles`、`runner_hints` 或 `agent_hints`。

execution profile 选择是 Service / composition root 的显式业务决策，不由 helper 根据 `models.context_window_tokens` 隐式切换。Service 可以根据业务场景、响应速度和 effective model 选择合适 profile；assembly helper 只做兼容性校验和诊断，例如 1M profile 搭配 256K 模型时 fail fast 或输出明确 diagnostic，256K profile 搭配 1M 模型时可允许但提示策略较保守。若需要机器可读约束，profile 可增加 `context_window_class` 或 `min_context_window_tokens` 一类字段；这些字段只用于校验，不用于自动选择。

`context_budget_policy` 对齐 ratio-first Host public `ContextBudgetPolicy`，只表达治理策略，不表达模型能力或本次调用输出预算。Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `ContextBudgetPolicy.context_window_size` 直接传入 typed policy。`ContextBudgetPolicy` 至少包含 `context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、`max_proactive_compactions_per_run`、`max_reactive_compactions_per_run`、`max_compaction_attempts_per_operation` 与 `policy_ref`；Host 内部根据 ratio 计算 soft / hard threshold tokens。绝对 token 阈值、输出预留和触发阈值不作为 config/public policy 字段暴露。

usage 是 provider capability 驱动的治理观测信号，不是 scene / Service 业务风格参数。流式 OpenAI-compatible 请求在 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时默认请求 `stream_options.include_usage=true`；非流式响应如果 provider 返回 `usage`，Engine 默认读取并上报。Config 不提供 `usage_enabled`、`collect_usage`、`include_usage` 这类 override，也不引入独立 `supports_usage` 字段。Engine 只负责如实上报 usage，不理解 Host budget；Host ingest 负责 durable 化 `usage_reported` 并保留 attempt / execution context、估算 digest、policy ref 等后续消费所需关联信息。Context Governance 可主动消费 usage，但 usage 是 post-call observation，只用于估算器校准、diagnostic 与后续 Run / 后续 compaction 治理参考；不得回头修改当前已经完成的 dispatch decision。usage 缺失、provider 不支持 usage 或 usage 字段格式异常都不得导致 Run 失败。

`memory_projection_policy` 对齐 Host public `MemoryProjectionPolicy`，采用按语义分区的 deterministic floor / cap 预算模型。Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `MemoryProjectionPolicy.context_window_size` 直接传入 typed policy。policy 至少包含 `context_window_size`、`selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`selected_recent_window_turn_floor`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`、`session_summary_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor`、`max_lag_events_for_inline_delta`、`max_delta_repair_events` 与 `policy_ref`。fallback selected recent window caps 必须不小于 `selected_recent_window_turn_floor` 所需材料，且不得大于普通 selected recent window caps；否则 fallback 会失去“更小、更保守恢复视图”的治理含义。同一个运行语义只能有一个 policy owner；若某个值同时影响 context governance 与 memory projection，必须由唯一 owner 派生给另一侧使用，不得复制成会漂移的双份真源。policy 存在即表示装配 stateful memory projection；不再使用 `enabled` 字段表达单轮 / 多轮语义。

`tool_truncation_policy` 只配置默认治理参数，不配置 per-tool strategy / target。它至少包含 `enabled`、`default_cursor_ttl_seconds` 与 `default_limits`，其中 `default_limits` 覆盖 `text_chars.max_chars`、`text_lines.max_lines`、`list_items.max_items` 与 `binary_bytes.max_bytes`。工具声明负责提供 `ToolTruncateSpec.strategy`、`target_field` / `field_path` 与是否启用截断；如果工具声明启用截断但未提供 limit 或 ttl，Service / composition root 用 policy default 补齐成 effective truncate spec。`fetch_more` 名称由 `FrameworkToolName.FETCH_MORE` 固定，不作为配置项。

`host_runtime.json` 表达 Host opener 的部署默认值：store / artifact roots、SQLite、`host_execution_lane_name`、worker backend、dispatch poll interval 与 memory projection catch-up page size 等。这些都是 `open_host(options)` construction-time assembly inputs，不是 per-run override。`memory_projection_catchup_batch_size` 只表示 required catch-up / rebuild 的内部读取页大小和单批 transaction 粒度，不表示“本次最多追多少事件”的语义预算，也不能作为 correctness 停止条件。顶层 selector 使用 `default_host_runtime_id`；host runtime record 不重复内部 id。`worker_backend` 当前支持 `local`，未来可扩展 `remote`；ConfigLoader 只读取该值，Service / composition root 负责映射为 `OpenHostOptions.worker_factory`。`runtime_lanes.json` 表达层中立 runtime lane coordinator 与 lane catalog；`host_runtime.json.host_execution_lane_name` 引用该 lane catalog，Service / composition root 再映射到 `OpenHostOptions` 的 lane fields。`tool_discovery.json` 表达 ToolsDiscovery provider 配置：provider id、import path 或 entry point、source kind、source id、enabled 与 provider config；ConfigLoader 只读出 typed provider specs，ToolsDiscovery 才负责 import provider、聚合 `ToolBundle` 与计算 digest。

wait resolution 配置不得写入 scene manifest。具体 awaiting provider 选择 `poll`、`callback` 或 `manual` 的恢复策略属于该 provider / adapter binding 的工具级事实，写在 `tool_discovery.json` 对应 provider config，并由 provider assembly 校验所选策略确实可用；当前 product runtime 尚未装配真实 authenticated callback transport 时，选择 `callback` 必须在 Host 打开前 fail fast。wait poller 的启停、poll / idle cadence、retry / backoff、单次 adapter observation budget、close drain budget、claim 与 outstanding invocation 上限属于 Host opener runtime policy，写在 `host_runtime.json`，不得放进 per-Run `execution_profiles.json`。Service 只能在 effective Host runtime policy 已启用、当前工具集合至少包含一个选择 `poll` 的 awaiting provider、且匹配 poll adapter registry 存在时启动 poller；scene tool selection 只用于筛选本次实际暴露的工具，不拥有后台 runtime authority。

ConfigLoader overlay 规则必须保持可预测：包内默认配置与 workspace 覆盖配置按配置文件类型分别加载；顶层 map 按稳定 id 合并，同 id 记录由 workspace 整条替换，不做隐式 deep merge。需要复用配置时使用显式 `extends`，且只允许单继承；继承解析后必须得到完整 typed record。ConfigLoader 不解析环境变量、不替换 secret、不脱敏，只原样读取 schema 表达的值。`dayu.runtime` 提供层中立 location resolver：当 `workspace/config` 存在时输出 `config_overlay_dir=workspace/config`，否则输出 `None`；同时解析 `prompt_asset_root` 与 `scene_manifest_root` 的实际可用路径。ConfigLoader 和 ScenePrepare 都不内置 workspace fallback 策略。

多 Run 财报流程由 Service workflow 或未来 typed Skill orchestration 控制。scene manifest 不表达 step graph、next scene、产物传递、artifact store、structured parser、replay policy、retry / stop policy、failure classification 或 checkpoint / resume 语义。这些属于 Service workflow / skill orchestration 的状态机和持久化边界，不属于 `ScenePrepare`，也不得进入 Host 状态机。Scene manifest 只保留稳定 scene identity、capability tags / refs 与 source digest，作为后续 workflow / skill 可引用的 scene capability。

Scene manifest schema 包含 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments` 与 `context_slots`。`schema_version` 表达 manifest schema 版本；`version` 表达 scene definition version；`scene` 是稳定 scene id；`capability_tags` 用于 Service workflow 或未来 skill 按能力引用 scene。`model.default_model_id` 是 scene 层默认 model 建议，可被 UI / Run override 覆盖；`model.runner_option_hint_id` 是 scene 层调用语义档位建议。scene 不保存 provider-specific runner option 值，不保存 model allow-list，不保存 raw runtime patch dict。`agent_policy` 是可选 typed override block，只允许覆盖 `AgentPolicy` 白名单字段；未知字段必须 fail fast。`context_slots` 只声明 Service 必须提供的 typed context 名称，不携带值。source refs 与 content digest 由 `ScenePrepare` 基于 manifest 与 assembly 输入计算，不写死在 manifest。

`tool_selection` 第一版只支持 names 与 tags 选择，不支持 include / exclude 组合，也不支持 scene 动态替换整个 `ToolBundle`。`mode="all"` 表示使用 construction-time business `ToolBundle` 的全部业务工具，Service 映射为 `SubmitFollowupRequest.tool_names=None`；`mode="none"` 表示本 Run 禁用业务工具，Service 映射为空 `frozenset()`；`mode="select"` 只允许 `tool_names` 与 `tool_tags_any`，显式 names 与 tags 命中的工具取并集后映射为 `SubmitFollowupRequest.tool_names`。未知 `tool_names` 是配置错误；`tool_tags_any` 没有匹配默认是配置错误，只有显式 `allow_empty=true` 时才允许空选择。

Scene manifest 支持 `extends`，但只允许单继承。`extends` 为空或单元素数组；多元素数组和循环继承均为配置错误。子 scene 只能追加 fragments，不覆盖父 fragments；`fragment.id` 与 `fragment.order` 重复均为配置错误。`context_slots` 继承并去重，保持父优先顺序。`tool_selection`、`model` 与 `agent_policy` 支持子 scene 显式覆盖；未显式配置时继承父项或使用 execution profile baseline。scene manifest 不包含 `conversation` 字段；单轮 / 多轮、是否 clear session、是否保留历史由 Service session lifecycle 控制。`prompt` scene 保留为 prompt-style task config，`prompt_mt` 不作为独立 scene 语义存在。

Phase 12 的 runtime assembly 边界由 `ScenePrepare`、`ConfigLoader` 与 `ToolsDiscovery` 三个独立组件组成。`ScenePrepare` 解释 scene manifest、读取 manifest 直接引用的 prompt fragment assets、接收 Service 传入的 typed context slot values，并输出已拼接 `system_messages`、tool selection、model hints、可选 agent policy override、fragment refs、source refs 与 content digest。`ConfigLoader` 原样读取 execution config、执行 overlay 与 typed validation，并输出层中立 typed config view。`ToolsDiscovery` 加载显式 provider callable 或 package entry point，聚合 provider 返回的 `ToolDefinition` 集合，输出业务 `ToolBundle`、source refs、content digest 与 provider report。三者互不替代：`ConfigLoader` 不解释 scene manifest，`ScenePrepare` 不做工具发现，`ToolsDiscovery` 不读取 scene manifest 或配置模型。

Service / composition root 是三者输出进入 Host 的唯一映射方。Service 同时消费 `PreparedSceneInputs`、ConfigLoader 的 typed config view 与 ToolsDiscovery 的 discovered bundle，把它们显式映射为 `open_host` construction-time inputs、per-run request inputs、resolved `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`HostToolingOptions` 或其它已冻结 typed input；映射失败必须在调用 Host 前失败。Service / execution environment 负责 provider client 创建、secret 解析 / 使用 / 脱敏 / 保护、多 Run workflow、artifact、parser、replay、retry 与 stop policy。Host 不重新读取 Config 或运行环境来解析 secret；它只消费 Service 已构造的 typed execution input。

运行时 override 合并由 Service / composition root 执行，优先级固定为未来 UI 显式输入 > scene manifest hints > ConfigLoader typed config view > 代码默认值。该优先级只适用于 Host 外部装配阶段，Host 接收的仍然是最终 typed inputs，不解释 override provenance。当前 Host public contract 允许的 per-run override 仅限 `SubmitFollowupRequest` 的 `system_prompt`、`tool_names`、`runner_spec`、`runner_options` 与 `agent_policy`：`system_prompt` 承接 `ScenePrepare` 已装配的 system messages；`tool_names` 只在已发现业务 `ToolBundle` 内选择子集，`None` 表示使用全量业务工具，空集合表示禁用业务工具，非空集合表示显式白名单；`runner_spec`、`runner_options` 与 `agent_policy` 必须由 Service 映射为完整 typed value，不接受 patch dict、profile lookup、extra payload 或 raw config fragment。`SubmitFollowupRequest.user_prompt` 是调用方本次输入，不来自 scene / config；`behavior` 与 `target_run_id` 属于 Service / UI 请求控制，不属于 scene manifest 的稳定职责。

`open_host(options)` 的 construction-time inputs 也由 Service / composition root 从 ConfigLoader、ToolsDiscovery、代码默认值以及部署环境组装，但它们不是当前 per-run override。包括 durable store / artifact roots、SQLite 与 lane 参数、worker factory、ordinary run baseline、`HostToolingOptions`、context budget policy、compactor runner baseline、memory projection policy、memory catch-up page size 与 truncation manager 开关在内的 Host opener 参数，在 Host handle 打开后不由 scene 或单个 Run 改写。Scene 可以表达 model / tool selection hints 与 typed agent policy override，ConfigLoader 可以表达 execution profile 与部署默认值，最终是否转化为 opener baseline 或 per-run override 由 Service 根据现有 Host typed contract 决定；若发现需要新增 per-run override 字段，必须回到 Host public interface design gate，不能通过 runtime assembly 旁路扩展。

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

Host 默认不把 `content_delta` 与 `tool_call_delta` 写入 EventLog；`reasoning_delta` 只为 live thinking display 写入 `PREVIEW` row。Host 可以接受这些事件并把它们用于本次运行的即时展示路径，但 durable replay、Host event stream 补读、memory、audit 与 RunResult 不能承诺 token-level delta replay；可恢复真源仍是 terminal final answer、工具接受事实、compact canonical fact、usage / diagnostic / projection signal 等已提交 EventLog facts。若未来需要多客户端 live token fanout，必须另行设计 transient fanout 能力，不能把主 EventLog 的 durable replay 语义改成 token-level 保真。

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
- `list_sessions` 仍允许读取全部未 purge Session 的 durable 列表摘要；它不是 projection，不触发 projection catch-up，不启动执行，也不改变 Session / Run / Attempt 状态。
- `cancel_run` 仍允许取消已有 Run。
- `resolve_wait` 仍允许让已有 `WAITING` Run 继续收口。
- `retry_run` / `replay_run` 默认拒绝在 closed Session 内创建关联新 Run，除非显式 policy 把新 Run 创建到其它 Session。

已有 active Run 继续按 Host 状态机治理到终态；close 前已 durable accepted 的非终态 Run 继续按原状态机完成。`QUEUED` Run 可在 active slot 释放后 promotion；`WAITING` Run 可在 `resolve_wait` 后 resume；`RECOVERING` Run 可继续 recovery dispatch；`RUNNING` / `CANCELLING` Run 继续收口到 terminal。Host opener close 可停止当前 handle 持有的本地执行环境，但不等于用户 cancel；若调用方希望表达用户停止意图，必须显式调用 `cancel_run` 或 `cancel_session_runs`。

CLI `session resume` 与 Host wait-resume 是两个不同术语。CLI resume 只是 UI / Service adapter 选择一个已有 `OPEN` Session，再提交新的 `submit_followup(queue)` 输入；它不恢复旧 Agent、Runner、Engine generator 或 Attempt，也不解析 Host wait record。Host wait-resume 只指 `resolve_wait` 接收外部等待结果后，让同一个 `WAITING` Run 创建新的 resume Attempt 并继续收口。

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
| Tool awaiting accepted | Run `RUNNING` / Attempt `RUNNING` | Run `WAITING` / Attempt `SUSPENDED` | `TOOL_CALL_REQUESTED`、`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` | ToolRuntime Host accept transaction 持久化业务可读 request atom、关闭当前 Attempt、持久化 wait record |
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

Host terminal / lifecycle event set 是 Run 生命周期的 canonical fact 集合。`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED` 与 `RUN_LOST` 都是 Host Run terminal canonical facts；其中 `RUN_LOST` 表达 recovery、worker lifecycle 或 waiting-result positive proof 得到的 lost terminal，不是用户 cancel，也不是 failure 的展示别名。Read Model、Read API 与 public HostEvent 必须能把 `RUN_LOST` 投影为 `lost` terminal。

Public outbox terminal item set 只包含 `RUN_SUCCEEDED`、`RUN_FAILED` 与 `RUN_CANCELLED`。Outbox 是 public delivery work queue，不拥有 Run terminal truth，不得把 `RUN_LOST` 伪装成 success、failure 或 cancel 的 public terminal item。`RUN_LOST` 仍保留在 EventLog / Run row / read model 中作为 Host terminal truth，但不要求存在 public outbox item。

Non-public terminal fact skip / diagnostic behavior 必须显式且可审计。Outbox consumer 遇到 `RUN_LOST` 时只能记录 skip / diagnostic，不能创建 public terminal item；public outbox watermark、latest item cursor 与 lag 判断只能以 public outbox terminal item event set 为准，不能把 `RUN_LOST` 当成必须投递的 item 候选。

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

Host SQLite / EventLog 是受信任内部 durable store。为冻结 exact effective execution，`USER_INPUT_ACCEPTED` 或等价 canonical fact 可以持久化 Service 已解析的 typed `RunnerSpec`，包括 resolved provider headers / API key；这是 retry / replay / recovery 的执行真源，不是新增 public projection。任何读取该 fact 的消费者都必须声明自己的 typed projection contract：dispatch / retry / replay / recovery 可以恢复完整执行配置，Tool Trace、audit、HostEvent / read API、outbox、memory / compact、LLM-facing runner input / observation 与 operator log 则只能选择各自安全字段，provider secret 明文必须为零。不得用字段名黑名单、下游字符串替换或展示层 repair 代替 owner 级白名单投影。

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

admission 冻结的 effective execution snapshot 必须把 canonical execution config digest 同时写为 `policy_snapshot_digest`，并把 `policy_snapshot_ref` 规范化为由该 digest 派生的不可变 ref。恢复边界必须先重算 config digest，再校验 digest 与 ref，全部通过后才能反序列化 runner / options / agent policy；不得把 snapshot 中自报的 digest 或 ref 当作可信输入。

## 11. Host 公共接口

### 11.1 Execution / Admin capability 与 durable actor boundary

Host 对 Service 提供两个无继承关系的 public Protocol：

- execution `Host` 由 `open_host(OpenHostOptions)` 打开，承诺 Session / Run command、cancel、wait、outbox read/drain 与 live watch；它不承诺 Session list / purge 或 storage maintenance。
- `HostAdmin` 由 `open_host_admin(OpenHostAdminOptions)` 打开，只承诺 `get_session`、`list_sessions`、`purge_session`、`report_storage_usage` 与 `run_storage_maintenance`；它不暴露 ensure/create/submit/retry/replay/resolve/cancel/watch 或任何 scheduler control。

`OpenHostAdminOptions` 只包含 durable SQLite、artifact 与 payload policy。admin opener 不加载或接收 scene、tool、model、provider secret、lane、worker、wait poller 或 execution baseline，不执行 startup recovery、projection catch-up 或 scheduler/host-instance registration。CLI / Service 的 list 与 purge 必须走这条 admin assembly；resume 等执行入口仍走 `open_host`。

所有 execution / admin public durable command 与 read 都提交到 opener 私有的 single-worker durable actor。actor 是 command handle、actor durable store 与 SQLite connection 的唯一线程 owner，负责它们的创建、使用、drain 和关闭；caller cancellation 只取消等待，不取消已经提交的底层 future。execution scheduler 使用独立 durable store / connection，两条连接共享同一个 SQLite / payload policy，但任何 live connection 都不得跨线程。

actor transaction 的 after-commit scheduler wake 与 active worker cancel 必须同步桥接回 opener event loop；callback、`LocalWorkerHandle.on_cancel()` 与 asyncio primitive 只能在 opener loop thread 访问，bridge exception 必须返回原 actor caller。execution close 先停止新 call 并 drain actor command / wake，在 scheduler 仍存活时完成 bridge，然后按 `scheduler -> projection flush -> actor handle/store -> actor executor -> scheduler store` 关闭；admin close 只关闭 actor chain，重复关闭幂等。

execution Host 的 lifecycle 与 new-work admission 由同一个 `HostExecutionHealthGate` 拥有，状态单向为 `STARTING -> READY -> UNAVAILABLE -> CLOSING -> CLOSED`。`submit_followup`、`retry_run`、`replay_run` 取得 admission lease 后才可提交 actor；lease 覆盖 transaction、commit 后 scheduler wake 与 actor future 收口，caller cancellation 不提前释放。scheduler fatal transition 取得同一 lease，因此 admission-first 只能先完成 commit+wake，fatal-first 则在 actor submission 前返回 retryable `unavailable`。read、cancel 与 close 不因 `UNAVAILABLE` 被 admission gate 拒绝，但仍受 close gate 与各自业务状态约束。

heartbeat、dispatch drain、queue promotion 与 active-cancel watchdog critical task 的非预期退出通过同一 health gate 报告稳定 `component/reason_code`，public detail 不携带原始异常文本。`HostTransactionRetryExhaustedError` 是 transient，不提交 fatal、不关闭 scheduler、不取消 active worker；dispatch pending durable row 保持真源，scheduler 按 poll interval 退避后重新 reconcile。closed 或 unavailable scheduler 的 dispatch/promotion/watchdog wake 必须返回 typed internal unavailable，不能静默丢弃。

admission 幂等 replay 必须在 transaction 内从最新 Run、current Attempt 与 dispatch row 重新派生 after-commit wake：`ACCEPTED` Run 重唤醒 pre-start governance，`RUNNING + STARTING + pending dispatch` 重投递 matching dispatch identity；queued、terminal、已取消或已进入 lane/worker 的 snapshot 不误 wake。`idempotent_replay` 只描述 durable 幂等命中，不能作为跳过全部 wake 的 shortcut。

Host 公共接口采用函数式风格，但不得依赖全局隐式单例。公共函数接收明确的 Host handle / context 与 request，返回稳定 snapshot 或 Host event stream。

Service-facing 第一版应表现为一个简单 Host opener / handle，而不是把 scheduler、runner、tooling、memory catch-up、wakeup 或 `HostLocalRuntime` 暴露给上层。调用方形态是打开 Host、取得 / 新建 / 读取 Session、提交 prompt 或控制命令、读取 / 订阅 Session 事件、在 terminal event 中观察 final answer、关闭 Host。内部可以使用 composition root / runtime 装配 command handle、durable store、scheduler、active registry、local execution、ToolRuntime、compactor 与 projection catch-up，但这些只是 Host 内部实现边界。

Host Service-facing opener 固定为 capability-separated `open_host(options)` 与 `open_host_admin(options)`，两者都是 async context manager。handle methods 与 event stream consumption 均以 async public contract 为准。Host public contract 不提供同步 wrapper，不冻结同步 close / cancel / timeout / stream iteration 语义。CLI 或同步上层如需使用 Host，应在 Service / CLI adapter 边界用 `asyncio.run(...)` 或等价机制包装 async Host contract，不要求 Host 层维护第二套同步 API。

Host opener close 是 handle lifecycle 语义，不是 Session / Run 治理事实。execution `Host` 与 `HostAdmin` 的 `close()` / context exit 都必须幂等；close 完成后，调用同一 handle 能力面上的任一方法必须 fail-fast 抛出 typed `HostClosedError` 或等价 lifecycle exception。这个错误不写 EventLog，不返回 command-level `invalid_state`，也不与 `Session CLOSED`、not found、purged、retry precondition failed 等业务状态混淆。已经提交给 durable actor 的调用按正常事务与 after-commit wake 语义完成；close gate 之后的新调用统一抛 closed-handle exception。

Host opener close 会终止当前 handle 持有的本地运行环境，但不得伪装成用户取消。close 流程必须停止 scheduler / promotion / background supervisor，不再启动新的 Attempt；必须向 active worker registry 传播 lifecycle cancel，使 Host 注入 Engine 的 cancellation token 可见，并通知 `LocalWorkerHandle.on_cancel(reason)` 这个 best-effort hook；随后关闭或取消当前 handle 持有的 active worker task、lane wait、stream fanout task 与本地 runtime resource，避免进程内任务泄漏。若 close 过程中 active worker 已经产出可确认 terminal event，Host 按正常 ingest / terminal closeout 追加事实。若 active worker 没有可确认 terminal，Host close 不得写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED` 或其它伪装用户意图 / 确认失败的 canonical fact；未收口 active Attempt 后续必须通过 Host lifecycle / Recovery 的 positive orphan proof 路径进入 `ATTEMPT_LOST`，再按 policy 进入 `RUN_RECOVERING` 或 `RUN_LOST`。调用方若要表达用户明确停止，应在 close 前显式调用 `cancel_run(...)` 或 `cancel_session_runs(...)`。

P10.5 的 Host opener close shutdown order 是 implementation requirement，不是新的 public API 设计点。推荐顺序是：先关闭 public gate 并拒绝新进入 API；停止 scheduler / promotion / background supervisor，避免启动新 Attempt；关闭 session live watch fanout，让 watcher 正常结束或收到 Host lifecycle termination；取消或关闭当前 handle 持有的 active worker task、lane wait、worker stream consumer task；flush / close projection catch-up 与本地 runtime resources；最后关闭 durable store。全程不得写 `RUN_CANCELLED` / `RUN_FAILED` 或其它 terminal fact 来伪装用户意图；已经在 close 过程中确认的真实 terminal event 仍按正常 ingest / terminal closeout 处理。

P10.5 冻结的是后续真实生产系统 Service 使用的普通多轮生产接线，不是 smoke 专用接线。P10.5 自身必须把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实；真实 CLI / web / GUI 在 P11-P15 实施完毕后会通过 Service 使用这里冻结的 Host public interface / contract 接入，不能等到真实入口接入时再补一条新接线。后续 phase 可以扩展 Recovery、ToolsDiscovery / ScenePrepare、Audit / Tool Trace / Outbox、RemoteProxy 与 Retention / Purge 能力，但不得要求真实入口绕过、替换或重写普通多轮会话的 Host 生产接线。

`open_host(options)` 的 options 只承载打开 Host、驱动 Host -> Engine 本地运行所需的 construction-time 参数。Host public API 保持朴素接口形式：内部运行真正需要外部提供的 durable store / payload / artifact roots、runner / worker factory、全量 business `ToolBundle`、ToolRuntime policy、compactor runner / storage config、context budget policy、memory catch-up、stream fanout / background supervisor 所需端口和运行目录等依赖，由调用方通过 typed function 参数显式传入；Host 不在 P10.5 引入 ConfigLoader、全局配置系统或 service locator。scheduler、wakeup、active worker registry、dispatch control 等 Host 内部接线由 `open_host` composition root 自行创建或连接，不作为 Service-facing 参数暴露。每次 Run 会变化的参数不得塞进 `open_host` options；它们必须进入对应 public request，例如普通 prompt / per-run tool selection / run-local instruction 进入 `SubmitFollowupRequest`，retry / replay 控制参数进入各自 request，后续若新增 per-run profile / target 也必须作为明确 request contract 讨论和冻结。

一个 `open_host(options)` 表达一个 Host runtime environment 与默认 ordinary Run execution baseline。durable store、scheduler / worker wiring、memory / artifact roots、全量 business `ToolBundle`、Host policy 基线与默认 `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy` 都属于 construction-time baseline。真实生产系统在同一个 Session 的不同 Run 中切换模型是正常需求；P10.5 不通过 `profile_id` / registry lookup 表达这件事，而是允许 `SubmitFollowupRequest` 直接携带可选 typed override 对象：`runner_spec?: RunnerSpec`、`runner_options?: RunnerCallOptions`、`agent_policy?: AgentPolicy`。字段省略时使用 `open_host(options)` 的默认 ordinary Run baseline；字段出现时使用该 Run 显式传入的 typed value。override 是按字段 partial merge，不是 all-or-nothing profile：例如只传 `runner_options` 时，`RunnerSpec` 与 `AgentPolicy` 仍取 opener baseline；只传 `runner_spec` 时，runner call options 与 agent policy 仍取 opener baseline。每个出现的 override 对象本身必须是完整 typed value，不能是 patch dict、增量字段包或 extra payload。Host 不接收 raw provider client、callable、无结构 dict override、extra payload 或 `policy_overrides`；它可以接收 Service 已解析并封装进 typed `RunnerSpec.headers` 的 provider API key。`RunnerSpec.api_key_ref` 是 secret 来源引用名，不要求 `headers` 仍保持未解析。Host admission / dispatch 必须校验并把每个 Run 的 effective runner spec / runner options / agent policy 冻结到内部 durable canonical fact 或等价可恢复 snapshot，保证 retry / replay / recovery 使用并解释当时的准确执行配置；其中 resolved headers / API key 只属于受信任 Host internal durable state，不能进入 public / LLM-facing / log projection。普通每 Run 其它可变项第一版包括显式 `system_prompt`、`user_prompt`、`tool_names` 以及必要的 `client_request_id`、actor / source refs 等 request metadata。后续若新增更细粒度 per-run override，也必须作为 typed request field 讨论并冻结。

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
list_sessions(host) -> ListSessionsResult
close_session(host, session_id, request) -> SessionSnapshot
purge_session(host, session_id, request) -> PurgeSessionResult

get_run(host, run_id) -> RunSnapshot
watch_session_events(host, session_id) -> AsyncIterator[HostEvent]
report_storage_usage(host) -> HostStorageUsageReport
run_storage_maintenance(host, request) -> HostStorageMaintenanceResult
cancel_run(host, run_id, request) -> RunSnapshot
cancel_session_runs(host, session_id, request) -> SessionSnapshot
submit_followup(host, session_id, request) -> FollowupSnapshot
retry_run(host, run_id, request) -> RunSnapshot
replay_run(host, run_id, request) -> RunSnapshot
resolve_wait(host, wait_id, request) -> RunSnapshot
```

以下能力不属于普通 Service-facing public contract：

- `start_run(...)` / `_start_run(...)`：`_start_run` 是 Host 内部 admission primitive，普通 Service 不可调用。
- `create_host_command_handle(...)`：降为 Host 内部 / 低层测试 composition primitive，不作为 Service 打开 Host 的入口；Service-facing opener 只有 capability-separated `open_host(options)` 与 `open_host_admin(options)`。
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
| `list_sessions` | 完整实现 | 从 durable truth 读取全部未 purge Session 的列表摘要，不触发 projection worker 或执行。 |
| `close_session` | 完整实现 | 关闭新输入入口；不 cancel、不 purge。 |
| `submit_followup(queue)` | 完整实现 | 在同一 admission transaction 内吸收 active Run 竞态；结果用 `accepted_run_id` + `accepted_run_status` 表达。 |
| `get_run` | 完整实现 | 从 durable Run / Attempt truth 构造 snapshot。 |
| internal `stream_run_events` / run-scoped EventLog 补读 | 完整实现 EventLog-backed read path | 全局 EventLog cursor 是唯一 cursor truth；Phase 4 不引入 projection truth；P10.5 后该路径降为内部 diagnostic / detail contract。 |
| `cancel_run` queued / pre-dispatch `STARTING` | 完整实现 | 覆盖 Phase 1-3 已有可闭环路径：`QUEUED` 与 dispatch record 尚未进入 dispatching 的 Attempt `STARTING`。 |
| `cancel_session_runs` queued / pre-dispatch `STARTING` / `WAITING` / `RECOVERING` | 完整覆盖当前可闭环状态 | 批量取消所有当前可闭环 non-terminal Run；active worker 物理传播、外部 job physical cancel / abandon 与 recovery dispatch 中取消继续由对应后续 owner 强化。 |
| `submit_followup(steer)` | stable unsupported / deferred | Phase 4 只冻结 envelope、validation、error/detail contract；public facade 返回 `unsupported_operation`。完整 Attempt switching 由后续 steer / dispatch / wait owner 落地。 |
| `retry_run` | stable unsupported / deferred | Phase 4 冻结 request / idempotency / error envelope；执行语义由后续 retry owner 落地。 |
| `replay_run` | stable unsupported / deferred | Phase 4 冻结 request / idempotency / error envelope；执行语义由后续 replay owner 落地。 |
| `resolve_wait` | stable unsupported / deferred | Phase 7 owns wait record、tool result accept 与 resume Attempt。 |
| `purge_session` | stable unsupported / deferred | Phase 15 owns destructive cleanup 与 purge tombstone persistence。 |
| active dispatch cancel | stable unsupported / deferred | Phase 5 owns dispatching / active WorkerProxy cancel propagation。 |
| wait external job physical cancel | stable unsupported / deferred | 当前已实现 `WAITING -> CANCELLED` 逻辑收口；Phase 7 继续拥有外部 job best-effort cancel / abandon 强化。 |
| recovery dispatch cancel | stable unsupported / deferred | 当前已实现未派发 `RECOVERING -> CANCELLED`；Phase 11 继续拥有 recovery dispatch / recovery scan cancellation 强化。 |

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
- `cancel_run`：接受取消请求，按 `(run_id, client_request_id)` 幂等；queued Run 直接 `CANCELLED`，pre-worker `STARTING` Run 可直接 `CANCELLED`，包括 `pending`、`waiting_for_lane` 以及 WorkerProxy accepted 前的 `dispatching`；`WAITING` Run 通过取消 wait record 直接 `CANCELLED`；未派发的 `RECOVERING` Run 直接 `CANCELLED`。active worker cancel 进入 `CANCELLING` 并向当前 Attempt 传播 cancel 的完整能力由 Phase 5 落地；外部 job physical cancel / abandon 与 recovery dispatch cancellation 分别由 Phase 7 / Phase 11 强化。
- `cancel_session_runs`：接受 session-scope cancel 请求，按 `(session_id, client_request_id)` 幂等；取消该 Session 下所有当前可闭环未终态 Run，不影响其它 Session。queued / pre-dispatch `STARTING`、`WAITING` 与未派发 `RECOVERING` 会直接收口；active worker 物理传播、外部 job physical cancel / abandon 与 recovery dispatch cancellation 继续由 Phase 5 / 7 / 11 强化。
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
- `report_storage_usage` 是 operator-facing 只读诊断入口。它只读取 durable SQLite row count、SQLite payload logical bytes、artifact descriptor logical bytes、orphan SQLite payload 诊断计数以及 DB / WAL 文件 `stat`。它不写 EventLog，不改变 Session / Run / Attempt 状态，不扫描 artifact root，不执行 checkpoint，也不删除文件或 row。artifact descriptor logical bytes 只是 descriptor 记录的 logical sum，不代表内容寻址 artifact 的物理文件占用。
- `run_storage_maintenance` 是 operator-facing 显式 maintenance 入口。它基于 `payload_descriptors` 中的 `artifact_ref` 相对路径收集引用集合，只扫描 artifact root 下 `sha256/` 内容寻址 namespace，返回超过 grace window 的 orphan artifact 候选、`sha256/` 已发布 artifact 物理字节和、同一次 usage report、memory snapshot integrity issues，并可用独立 SQLite connection 执行 WAL checkpoint。memory snapshot integrity issues 只报告 `invalid_json`、`schema_mismatch`、`digest_mismatch`、`unsupported_item_kind` 或 `storage_read_failed` 分类、短错误摘要和 row identity，不内联 snapshot JSON、prompt、tool payload 或大内容。默认 dry-run 不删除文件；`reclaim_orphan_artifacts=True` 时，只回收候选扫描证明为 orphan、且删除前 recheck 仍未被 descriptor 引用的 `sha256/` artifact 物理文件。maintenance 不删除任何 SQLite row，不 quarantine / rebuild / overwrite memory snapshot，不处理 audit JSONL / tool-trace JSONL，不执行 `VACUUM`，也不启动 scheduler。recheck 与 unlink 之间仍有极短 TOCTOU 窗口；默认 grace、content-addressed artifact 可重写性和 containment-guarded delete 用于降低风险。SQLite orphan payload row 只报告不回收；SQLite space reclamation / VACUUM 继续归 Issue 76。

接口分层：

- execution `Host` 稳定能力包括 `ensure_session`、`create_session`、`get_session`、`close_session`、`get_run`、`watch_session_events`、outbox read/drain、`cancel_run`、`cancel_session_runs`、`submit_followup`、`retry_run`、`replay_run` 与 `resolve_wait`。
- `HostAdmin` 稳定能力包括 `get_session`、`list_sessions`、`purge_session`、`report_storage_usage` 与 `run_storage_maintenance`；两个 Protocol 不互相继承，也不通过 wrapper/facade 重新合并能力面。
- `stream_run_events` 不进入 P10.5 普通 Service-facing public contract；现有实现若保留，只能作为 Host 内部 diagnostic / detail read path。未来若要公开 run-scoped diagnostic read API，必须另行讨论 public contract，且不能直接暴露内部 `HostEventView`。
- `cancel_session_runs` 是客户端退出 / supervisor shutdown 的便利公共能力；它只取消指定 Session 下未终态 Run，不表达客户端拥有的 Session 集合。
- `ensure_session` 表示“给我这个 slot 的当前会话，必要时创建并绑定”。
- `create_session` 表示“明确分配一个新 Session”，可选绑定 slot。
- `start_run` 不作为 Service-facing public API 暴露。内部 admission primitive 命名为 `_start_run`，用于表达“创建独立 Run”的低层语义，但普通 Service 不应依赖它；P10.5 必须把包根 public export、README 与 tests 调整到这一边界。
- `retry_run`、`replay_run` 是 Host control API；UI / Service 可以暴露，但必须保留 `retry(run)` / `replay(run)` 的函数式语义、Host 幂等与状态机。
- `resolve_wait` 是 Host 内部 / adapter API；poller、callback handler、manual admin 入口都必须走它，不能各自写 Run 状态。
- P10.5 ordinary local multi-turn public contract 冻结并验证 `WAITING` / wait record / `resolve_wait(...)` 的 public resume path：调用方或 tool adapter 已经通过 poll、callback 或 manual 操作拿到外部结果后，调用 Host public `resolve_wait(...)`，Host 通过 after-commit wakeup 创建 resume Attempt、推进 dispatch，并在 session-level `watch_session_events(...)` 中暴露后续 terminal HostEvent。当前 production poller 可由 `open_host` 可选启动，并通过 durable claim / backoff 防止重复 poll 与 tight-loop；它仍只是在拿到外部结果后调用同一个 `resolve_wait(...)`。生产级 callback HTTP endpoint、callback auth / replay 与 external job physical cancel / revoke 是独立边界，不能改变 `resolve_wait(...)` 作为唯一等待结果治理入口的边界。
- 读取 Session timeline 通过 `get_session` 的 snapshot、session-level Host event stream 或后续 read-model API 暴露；它必须从 EventLog / projection 读取，不触发执行。读取 Session 列表通过 `list_sessions` 暴露，它直接来自 durable Session / slot / Run state truth，不是 projection，也不触发 projection catch-up 或执行。离线 / 未 attach 客户端的 final answer 通知通过 Outbox terminal delivery queue 读取，不通过 session live watch 追补完整中间过程。

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
- `unavailable`
- `internal_error`

错误分类语义：

- `conflict`：当前 Host 状态与请求前置条件冲突，例如 active Run 存在且 policy 拒绝排队。
- `idempotency_conflict`：同一幂等键已绑定到不同语义输入或不同目标对象。
- `invalid_state`：目标对象存在，但该状态下不允许此操作。
- `permission_denied`：上层传入的 authorization claims 不满足 Host policy。
- `unsupported_operation`：public request / response envelope 已冻结，但完整语义由后续 phase 落地；它不表达目标对象状态错误，也不能伪装成 `invalid_state`。
- `unavailable`：execution scheduler 已报告 fatal 或 Host 尚未完成 startup；固定为 retryable，detail 只包含稳定 component / reason code，不泄漏原始异常文本。

`HostApiError` 必须是受限 typed contract：`code`、`message`、`retryable` 与 `detail?`。`detail` 只能是 Host 公共 API 中显式定义的 detail union 成员，禁止无结构 `extra` / `payload` / `metadata` god bag。第一版至少包含：

```text
SteerConflictDetail:
  target_run_id
  target_run_status?
  current_active_run_id?
  current_active_run_status?

HostUnavailableDetail:
  component
  reason_code
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
- Host durable JSON resolver 是 descriptor 内容完整性的唯一读取 owner。读取 SQLite payload 时必须同时校验调用方 ref / digest、descriptor ref / digest / size、SQLite row identity / format / digest / size，以及实际 canonical bytes 的 digest / size，并拒绝非 canonical JSON 或非 object JSON；读取 artifact-backed payload 时还必须校验 artifact root containment、实际文件 digest / size 与 canonical object。任一层不一致都 fail closed，下游消费者不得只信 descriptor、row metadata 或调用方 digest 中的任意一份。
- Host composition root 必须显式注入 `payload_inline_threshold_bytes` 与 artifact root。默认值只能在 construction root 应用，不能通过模块级全局变量、隐式环境变量或硬编码路径取得。
- 小于等于 `payload_inline_threshold_bytes` 的可恢复 payload 可以作为 `sqlite_payload` 写入 SQLite payload table，并与引用它的 EventLog append 在同一 SQLite transaction 内提交。
- `TOOL_RESULT_ACCEPTED` 的完整 accepted payload 是否可内联，由 ToolRuntime accept barrier 在 append transaction 内根据 durable policy 判断；超过阈值时必须写 SQLite payload descriptor，并让 EventLog hot payload 只保留 evidence envelope、status、metadata 与可校验 payload ref。工具实现、Service 或 smoke 脚本不得自行承担该冷热分离判断。
- 超过 Host policy 阈值的大工具结果、财报 chunk、binary、长网页正文、provider raw response、完整 prompt / messages、trace 明细必须外移到 artifact / blob / tool trace / 领域仓储，并在 artifact durable 且 digest verified 后才 append EventLog `canonical_fact`。
- 本地 `artifact_ref` 的最小写入顺序是：先写入 artifact root 下的临时文件，完成 flush / fsync 或等价 durable 写入，计算并校验 digest，再通过 atomic rename 发布到最终相对路径，最后在 SQLite transaction 中写 payload descriptor 与 EventLog row。EventLog 不得引用未 durable、未 digest verified 或位于 artifact root 外的临时路径。
- SQLite transaction 无法原子覆盖外部文件系统写入；因此 artifact 发布必须先于 EventLog canonical append。若 SQLite transaction 后续失败，已发布但未被 descriptor 引用的 artifact 只能作为后续 cleanup / diagnostics 处理，不能被当作 accepted fact。
- runner-call reconstruction 使用同一冷热分离规则。`RUNNER_CALL_INPUT_ASSEMBLED` 只在 canonical event hot payload 中保存 scope、runner-call identity、manifest descriptor ref、manifest digest、manifest schema version、validation status、runner-call projection ref / digest / size 等 bounded 字段；manifest body 使用 payload descriptor kind `runner_call_input_manifest` 存储。manifest canonical JSON 字节数小于等于 `payload_inline_threshold_bytes` 时可以写 SQLite payload，超过阈值必须写 artifact root 并通过 payload descriptor 引用。
- 完整 LLM-facing rendered messages 不是 EventLog hot payload。若 debug、analyzer 或 smoke 需要保存完整 rendered messages，只能写为 derived payload/artifact kind `runner_call_input_projection`，由 runner-call manifest 中的 projection artifact ref / digest 指向；它不能成为 recovery、resume、memory projection、dispatch decision 或 Run / Attempt 状态迁移真源。
- selected tool schema full JSON snapshot 使用 payload descriptor kind `selected_tool_schema_snapshot` 保存，并由 runner-call manifest 的 `tool_schema_snapshot_refs` 记录 ref / digest / size。Tool Trace hot/cold 只能保留 bounded refs/digests/summary；analyzer 通过 resolver 按需读取 snapshot，不得把完整 schema 内联进 hot row 或 cold JSONL。
- `TOOL_CALL_REQUESTED` 接受的工具参数也使用冷热分离规则。规范化 canonical arguments JSON 字节数小于等于 `payload_inline_threshold_bytes` 时可以作为 bounded inline JSON 进入 canonical payload；超过阈值必须写 payload descriptor kind `tool_call_arguments_json`。工具运行时若能提供业务可读 semantic query，短文本可 bounded inline，长文本必须写 payload descriptor kind `tool_call_semantic_query_text`；没有 semantic query 是合法但可诊断状态。
- compactor LLM proposal 输入投影使用 payload descriptor / artifact kind `compactor_input_projection`。该投影只记录 compactor 输入 data block 的 durable ref / digest，不能替代 `CONTEXT_COMPACTED` 的 accepted compact truth。
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
RUNNER_CALL_INPUT_ASSEMBLED
RUNNER_CALL_INPUT_ITERATION_LINKED
CONTEXT_COMPACTION_REQUESTED
CONTEXT_COMPACTED
CONTEXT_COMPACTION_FAILED
PROVIDER_DIAGNOSTIC
PROVIDER_PROTOCOL_ERROR
```

Terminal event 使用具体终态 event，不使用模糊 `RUN_TERMINAL` / `ATTEMPT_TERMINAL` 作为唯一类型。

模糊的“attempt event accepted”不作为第一版 canonical event。EngineEvent ingest 必须落到具体业务事实、preview / diagnostic，或被拒绝；不得用模糊“已接受某事件”掩盖事实类型。

EngineEvent ingest 的命名 diagnostic event 至少包括：

```text
ENGINE_EVENT_REJECTED
PROVIDER_DIAGNOSTIC
```

`ENGINE_EVENT_REJECTED` 不是 Run / Attempt lifecycle fact，只记录 Host 拒绝某个 Engine event 的原因和是否要求停止当前 worker stream。它不得驱动 recovery、memory projection、dispatch decision、resume 或 Run / Attempt 状态迁移。

`PROVIDER_DIAGNOSTIC` 是非致命 provider / adapter diagnostic，EventClass 固定为 `DIAGNOSTIC`。它持久化 bounded `diagnostic_code`、`severity`、`message`、`provider_request_id`、`diagnostic_source`、`payload_ref` 与 `payload_digest`，不得更新 Run / Attempt terminal state，不得写入 failure metadata，不得进入 outbox terminal item、Conversation Memory、final answer、accepted evidence material、compact material 或 LLM-facing prompt messages。Read API 以 `provider_diagnostic` / `info` activity 展示非致命诊断，以独立 `provider_protocol_error` activity 展示 fatal provider protocol error；Tool Trace 可以把 provider diagnostic 作为诊断展示材料。

Engine typed failure code 的唯一 Host 边界是 EngineEvent ingest。Host ingest
必须调用 Engine serializer，把 `EngineRunErrorCode` 或
`RunnerSpecificErrorCode` 写成 durable JSON 文本；`RUN_FAILED`、
`PROVIDER_PROTOCOL_ERROR`、failure metadata、public HostEvent、Tool Trace 和
Outbox 之后都只读取 durable 文本，不检查 provider / runner-specific wrapper
内部字段，也不按 provider-specific code 分支。

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
| `TOOL_CALL_REQUESTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | tool_call_id / tool name / accepted arguments atom / normalized args digest / optional source-owned semantic query atom | 记录工具调用 intent | resume、memory 与 compact evidence 只消费业务可读 tool name / query / 参数文本；不得把 Host 内部字段或下游字段名过滤结果当作 LLM-facing 语义 | audit 是 / tool trace 是 |
| `TOOL_CALL_GOVERNED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | policy decision / duplicate key / action | 不直接改 Run；可触发 guidance / hard stop | action 影响模型继续时进入 messages | audit 是 / tool trace 是 |
| `TOOL_RESULT_ACCEPTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | result ref / digest / accepted evidence envelope / raw outcome / status；wait terminal result 通过 wait-specific fields 表达来源与状态 | 记录工具事实；P1-P7 accepted waiting terminal result 不另建 `TOOL_TERMINAL_RESULT` canonical fact | resume 是 / memory 工具事实 | audit 是 / tool trace 是 |
| `TOOL_AWAITING` | `session_id`、`run_id`、`attempt_id`、`execution_id` | wait_id / await_spec / external_job_id | 与 `TOOL_CALL_REQUESTED`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 同事务创建 wait record；Run -> `WAITING`；Attempt -> `SUSPENDED` | 不进入 LLM-facing memory；resume 参数不得从此治理事实推断 | audit 是 / tool trace 是 |
| `GUIDANCE_INSERTED` | `session_id`、`run_id` | guidance text / source policy / reason | 不直接改 terminal；影响下一 Attempt messages | 插入 messages 时 resume 消费 | audit yes / Host event stream emit |
| `RUNNER_CALL_INPUT_ASSEMBLED` | `session_id`、`host_run_id`；有 Attempt 时必须带 `attempt_id`、`execution_id`；compactor proposal 必须可由 manifest 关联 parent run 与 compaction operation | runner_call_index / runner_call_kind / runner_call_trigger_reason / manifest_payload_ref / manifest_digest / manifest_schema_version / validation_status | 无 Run / Attempt 状态副作用；不参与 terminal decision、recovery scan、memory projection、dispatch decision 或 lifecycle transition | resume 不消费；reconstruction consumer 只能消费 refs / digests / projector metadata | audit optional / tool trace 是 |
| `RUNNER_CALL_INPUT_ITERATION_LINKED` | `session_id`、`host_run_id`、`attempt_id`、`execution_id` | manifest_event_id / manifest_payload_ref / manifest_digest / manifest_schema_version / runner_call_index / runner_call_kind / runner_call_trigger_reason / iteration_id / iteration_index / engine_message_count / engine_role_sequence_digest / runner_input_serializer_schema_version / expected_message_count / expected_role_sequence_digest / validation_status / diagnostic | 无 Run / Attempt 状态副作用；只表达 prepared runner-call manifest 与 Engine `ITERATION_STARTED` observation 的追加式 link / validation fact | resume 不消费；reconstruction consumer 可用 refs / digests / observed-vs-expected summary 判断 Engine link 是否完成 | audit optional / tool trace optional |
| `CONTEXT_COMPACTION_REQUESTED` | `session_id`、`run_id`；`trigger_source=reactive` 时必须有 `attempt_id`、`execution_id`；`trigger_source=proactive` 时可以没有 | trigger source / budget reason / provider error refs / snapshot refs | 触发 context governance；proactive path 是 pre-dispatch input governance；reactive path 可关闭当前 Attempt 并让 Run -> `RECOVERING` | resume 是；memory projection 按需消费 | audit yes / trace 是 |
| `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` | `session_id`、`run_id` | compact artifact ref / accepted candidate digest / prompt-local label mapping refs / source boundary refs / quality check / failure reason / fallback decision | compacted 后允许创建新 Attempt；failed 后按 policy 失败或保持 recoverable | resume 是；memory projection 按 policy 消费 accepted compact output | audit yes / trace 是 |
| `PROVIDER_DIAGNOSTIC` | `session_id`、`run_id`、`attempt_id`、`execution_id` | diagnostic code / severity / message / provider request id / diagnostic source / payload ref + digest | 无 Run / Attempt 状态副作用；非 terminal；不写 failure metadata | resume 不消费；memory 不消费；LLM-facing material 不消费 | audit optional / Host activity optional / tool trace diagnostic |
| `PROVIDER_PROTOCOL_ERROR` | `session_id`、`run_id`、`attempt_id`、`execution_id` | serializer 输出的 provider / runner error code 文本 / request ref | Attempt failure or retry input | retry 需要时 resume 消费 | audit yes / Host event stream emit |
| `ENGINE_EVENT_REJECTED` | `session_id`、`host_run_id`、`attempt_id`、`execution_id`、worker_event_index、engine_event_type | reason / stop_worker_stream / optional diagnostic_refs / optional runner-call link or manifest refs | 无 Run / Attempt 状态副作用；只表达 Host ingest fail-closed 或 unsupported event diagnostic；`stop_worker_stream` 是 worker stream 控制信号，不是 lifecycle transition | resume 不消费；memory 不消费 | audit yes / tool trace optional |

canonical event 的 required fields 不能被塞进无结构 `metadata`；`metadata` 只能承载不参与状态机、幂等、恢复和审计主链的附加说明。

control event 的 `run_id` 绑定规则：

- `STEER_REQUESTED` 的 `run_id` 是被 steer 的目标 Run。
- `submit_followup(queue)` 不引入独立 `FOLLOWUP_QUEUED` canonical event；它的 canonical 表达是 `USER_INPUT_ACCEPTED` 加 `RUN_ACCEPTED`，并在命中 active / start-blocking Run 时追加 `RUN_QUEUED`。`RUN_STARTED` 由后续 scheduler / pre-start governance 追加，不由 submit command 直接追加。
- `RETRY_REQUESTED` 与 `REPLAY_REQUESTED` 的 `run_id` 是源 Run；关联的新 Run 必须通过后续 `RUN_ACCEPTED` 的 `source_run_id` / `source_run_relation` 或等价 typed payload 表达。
- `RESUME_REQUESTED` 的 `run_id` 是从 `WAITING` / `RECOVERING` 继续的同一 Run。
- `CANCEL_REQUESTED` 的 `run_id` 是被取消的 Run。

Runner-call reconstruction contract 使用以下 scalar aliases：`Digest` 表示对 contract 声明的 canonical bytes 计算出的 lowercase hex SHA-256；`HostInternalRef` 表示只供 Host / trace / smoke consumer 使用的 typed Host ref string 或 descriptor object，永远不进入 LLM-facing material；`JsonObject` 表示 JSON-compatible mapping，key 必须是 string，value 只能是 JSON scalar / list / object，不能是 provider object、binary blob、callable、Python `Any` 或无结构内部对象。

`TOOL_CALL_REQUESTED` payload contract 固定为工具调用 intent、原始 accepted 参数 atom 与可选 source-owned semantic query atom。payload required fields 至少包括 `tool_call_id`、`tool_name`、`normalized_arguments_digest`、`arguments_json_size_bytes`、`arguments_storage_kind`、`arguments_payload_digest`、`semantic_input_digest`、`semantic_query_storage_kind`。`normalized_arguments_digest` 绑定 ToolRuntime 已接受的原始 canonical arguments preimage；`arguments_inline_json` 或 `arguments_payload_ref` 保存同一份 accepted canonical arguments JSON，只服务幂等、audit、payload integrity、internal replay、tool trace 和诊断，不是 Host 新增的 LLM-safe 参数投影。`arguments_storage_kind` 只允许 `inline_json` 或 `payload_descriptor`：当 accepted canonical arguments JSON 字节数小于等于 `payload_inline_threshold_bytes` 时必须使用 `inline_json` 并提供 `arguments_inline_json`；超过阈值时必须使用 `payload_descriptor` 并提供 `arguments_payload_ref`，descriptor kind 为 `tool_call_arguments_json`。`arguments_payload_digest` 校验 accepted canonical arguments JSON，必须等于 `normalized_arguments_digest`。Host 不得创建第二份 normalized / redacted / LLM-safe arguments JSON，也不得用字段名黑名单把 raw arguments 事后改写成 LLM-facing 语义。

可选 semantic query 是业务可读输入，不等同于 `semantic_input_digest` 的 preimage。`semantic_input_digest` 只表达幂等或语义归一 digest，可以没有可读文本；若工具/runtime 提供可读 query，`semantic_query_storage_kind` 可以是 `inline_text` 或 `payload_descriptor`，并必须提供 `semantic_query_digest`。长 query 使用 payload descriptor kind `tool_call_semantic_query_text`。缺少 semantic query 时 `semantic_query_storage_kind="absent"`，compact evidence projection 只能使用源头符合 LLM-facing 文本约束的工具名、query 或参数文本，或使用业务中性“工具参数不可读”说明 / fail closed；不得把 `tool_call_id`、payload ref、digest、cursor、Host 内部账本字段或 projection 层字段名黑名单结果渲染给 LLM。WU-CM-01-F02 的真实缺口是 query_text / accepted arguments 的业务可读表达，不是 tool name 缺失。

Host LLM-facing 参数文本不做独立 normalized/safe-args 层。LLM-facing 合规必须从源头保证：prompt assets、tool schema name/description、参数说明、枚举说明、错误说明、测试中模拟真实 LLM 的 prompt，以及 Host / Engine / Tool projection renderers 都必须遵守 `AGENTS.md` 的 LLM-facing 文本约束。若某个 schema、prompt 或 renderer 暴露 Host 内部术语、治理字段、裸 ref/digest/cursor、不可自解释缩写或安全敏感实现细节，必须在该 source owner 修正；Host projection 不得用下游 fallback、字段名 blacklist、兼容别名、`hasattr/getattr`、默认值或字符串猜测来补救。

`ToolCallArgumentsAtom` 字段固定为：

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `tool_call_requested_event_ref` | `HostInternalRef` | yes | canonical `TOOL_CALL_REQUESTED` event that accepted the intent | resolves to same `tool_call_id` and `tool_name` |
| `tool_call_id` | `str` | yes | provider/Engine tool call identity | can appear in internal trace, not compact query text |
| `tool_name` | `str` | yes | business-readable tool identity | equals canonical payload tool name |
| `normalized_arguments_digest` | `Digest` | yes | digest used for idempotency/tool intent validation | equals digest of normalized canonical arguments |
| `arguments_json_size_bytes` | `int` | yes | canonical JSON byte size | non-negative |
| `arguments_storage_kind` | `"inline_json" | "payload_descriptor"` | yes | storage form for accepted arguments | inline iff size `<= payload_inline_threshold_bytes`; descriptor otherwise |
| `arguments_inline_json` | `JsonObject | null` | conditional | accepted canonical arguments when small; internal/audit/replay material, not a separate LLM-safe projection | required for `inline_json`; forbidden for descriptor path |
| `arguments_payload_ref` | `HostInternalRef | null` | conditional | descriptor ref for accepted arguments JSON | required for descriptor path; forbidden for inline path |
| `arguments_payload_digest` | `Digest` | yes | digest of canonical accepted arguments JSON | durable args digest must equal `normalized_arguments_digest` |
| `semantic_input_digest` | `Digest | null` | no | existing idempotency semantic digest | retained; not assumed to be readable query preimage |
| `semantic_query_storage_kind` | `"absent" | "inline_text" | "payload_descriptor"` | yes | optional business-readable query supplied by typed tool/runtime contract | absent is valid and diagnosable |
| `semantic_query_text` | `str | null` | conditional | bounded readable query text | required only for inline text |
| `semantic_query_payload_ref` | `HostInternalRef | null` | conditional | descriptor ref for long readable semantic query | descriptor kind `tool_call_semantic_query_text`; required only for descriptor path |
| `semantic_query_digest` | `Digest | null` | conditional | digest of semantic query text | required when semantic query exists |

### 13.4 EngineEvent 映射

EngineEvent 到 Host EventLog 的映射原则：

- 参与恢复、resume、memory、audit、governance 的 EngineEvent 映射为 canonical event。
- 只服务 UI 流式体验的 per-delta EngineEvent 默认被 Host 接受但不写入主 EventLog；它们不进入 canonical projection，也不承诺 durable replay。当前 transient delta 子集是 `content_delta` 与 `tool_call_delta`。`reasoning_delta` 因 live thinking 展示需要写入 `PREVIEW` row，但仅供运行态 Host event stream 投影，不成为 memory、audit、resume、outbox terminal 或 canonical replay 真源。
- Host 可以把多个 EngineEvent 聚合成一个 canonical fact，但不得丢失恢复必须的信息。
- 工具事实 canonical owner 是 ToolRuntime Host accept path。EngineEvent ingest 不得为同一工具 outcome 追加第二条工具 canonical fact；描述已 accepted 工具结果的 EngineEvent 必须携带 accepted event refs / accepted tool fact ids，并只能映射为 preview、diagnostic、trace 或 idempotent no-op。

默认映射：

```text
iteration_started              -> preview
content_delta                  -> accepted non-durable delta; no EventLog row by default
reasoning_delta                -> preview (live thinking display only; not canonical replay truth)
content_completed              -> preview
tool_call_delta                -> accepted non-durable delta; no EventLog row by default
tool_calls_batch_ready         -> preview or diagnostic
tool_call_requested            -> TOOL_CALL_REQUESTED
ToolRuntime policy decision     -> TOOL_CALL_GOVERNED when decision affects execution / guidance / audit / duplicate handling
tool_result_accepted           -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
tool_calls_batch_done          -> preview or diagnostic
tool_awaiting                  -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
context_compaction_requested   -> CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive); must include attempt_id + execution_id
usage_reported                 -> usage projection input; canonical only if needed for audit policy
provider_diagnostic            -> PROVIDER_DIAGNOSTIC; diagnostic only, no Run / Attempt terminal state change
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

Tool Trace 的 event filter 与 extract / render owner 必须显式白名单化；不得因为 source EventLog 内部 canonical fact 含 resolved `RunnerSpec` 就复制其 `effective_execution_config`、provider headers 或 API key。hot row、cold JSONL、readable summary 与 query 返回中的 provider secret 明文都必须为零。工具自身 source-owned request / result 文本仍按既有 Tool / LLM-facing 安全 contract 处理，不能把 configured provider secret 的排除责任退化为 header 字段名黑名单。

存储口径：

- 热数据使用结构化 JSON projection。热数据保存近期、可查询、可展示、可关联的 tool trace summary，例如 tool_call_id、tool name、normalized args digest、result digest、evidence anchors、truncate info、await info、policy decision、error code、duration、attempt refs。
- 冷数据使用 append-only JSONL。冷数据保存可归档、可批处理、可离线审计的 trace detail，例如长参数摘要、长结果摘要、provider / tool raw diagnostic refs、截断诊断、重复治理上下文、等待 / 取消 / 超时细节。
- JSON 与 JSONL 都必须携带 `event_id` / `event_sequence`、`session_id`、`run_id`、`attempt_id`、`execution_id`、operation context refs / digest 和必要 digest / ref，保证能从 EventLog 对齐，并能回答“这是什么业务的什么操作产生的 trace”。
- 热数据可以按 retention policy 淘汰或压缩；冷 JSONL 可以按 run / 日期 / workspace 分片归档。
- EventLog 对 tool trace 只记录必要 event、ref 与 digest；不得把 JSONL 当作恢复、resume、memory 或 Run 状态迁移真源。
- tool trace projection 损坏或缺失时，应能从 EventLog 与外移 payload ref 尽力重建热数据；冷 JSONL 丢失只能影响深度诊断和离线审计。

Tool Trace 的 hot `trace_summary_json` 与 cold JSONL summary 是日常排障入口，必须能直接回答“模型请求了什么工具、业务参数是什么、Host 接受了什么、工具最终返回了什么、哪些内容可进入 memory / 下一轮上下文”。`TOOL_CALL_REQUESTED` summary 必须从该 event 的 request atom 派生，包含业务可读工具名、tool call label、source-owned request / query 文本、符合 LLM-facing 文本约束的参数摘要（若有）和参数 digest / ref 校验锚点；不得只保留 digest / ref。`TOOL_RESULT_ACCEPTED` summary 必须从 accepted evidence envelope 定位同源 `TOOL_CALL_REQUESTED` request atom，并从 digest-checked `raw_tool_outcome` 生成 bounded、脱敏的结果状态、details / summary 文本和 outcome digest / ref 校验锚点。wait-resolution result 与普通 tool result 使用同一 readable summary contract；Tool Trace 不得从 `TOOL_AWAITING`、wait record、poll 记录、observation handle、runtime 状态或当前代码路径反推 request / result 语义，也不得把 wait id、observation handle、runtime 等 Host / Tool 治理术语作为模型或开发者理解业务事实的主体。

Tool Trace 对 runner-call reconstruction 的消费边界固定为 read-only signal。它只能消费 `RUNNER_CALL_INPUT_ASSEMBLED` manifest refs / digests、`TOOL_CALL_REQUESTED` arguments / semantic query atoms、Engine 可观察的 iteration/message count 以及 projection artifact refs；不得读取旧 provider request、EngineRunner 内存、当前 prompt builder 代码或重新运行 compact material selection 来猜测历史输入。Tool Trace hot projection 只能缓存固定上界 scalar / diagnostic signal；projector metadata 的五字段 summary 必须在 query 时从 digest-verified manifest descriptor 的完整六字段 metadata 重建，不能读取 hot payload 中的数组或 raw string 作为语义真源。读取 descriptor bytes 后还必须经 shared runner-call manifest owner 解析完整 typed graph，至少校验当前 schema/version、scope 与 runner-call identity、message count 与连续 indexes、message-to-metadata 引用闭合、metadata id 唯一、projector/purpose closed enum、projection descriptor pair，以及 hot/manifest identity；只有该 typed manifest 可以产生 metadata summary。以下字段只是 projection copy，不是 recovery、memory、dispatch 或 Run 状态真源：

`RUNNER_CALL_INPUT_ASSEMBLED.validation_status="complete"` 只表示 prepared manifest 完整；`RUNNER_CALL_INPUT_ITERATION_LINKED.validation_status="complete"` 才表示该 prepared input 已通过 Engine `ITERATION_STARTED` observation 校验。第一版 Tool Trace 最小实现不强制投影 `RUNNER_CALL_INPUT_ITERATION_LINKED`；若未来投影 link event，只能作为独立 read-only signal 复制 manifest ref/digest、iteration fields、expected/observed count/digest 与 typed diagnostic，不得改变现有 `RUNNER_CALL_INPUT_ASSEMBLED` reconstruction signal 的含义。

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `runner_call_index` | `int` | yes | Host call index for locating the manifest | must match manifest |
| `runner_call_kind` | `RunnerCallKind` | yes | non-overlapping logical call kind | must match manifest |
| `runner_call_trigger_reason` | `RunnerCallTriggerReason` | yes | why the call was assembled | must match manifest |
| `iteration_id` | `str | null` | no | Engine iteration id when available | if present must match Engine event |
| `manifest_ref` | `HostInternalRef | null` | no | ref to runner-call manifest descriptor/artifact | null only with diagnostic reason `missing_runner_call_manifest` |
| `manifest_digest` | `Digest | null` | no | digest of manifest body canonical JSON | required when `manifest_ref` is present |
| `message_count` | `int | null` | no | manifest/Engine message count summary | mismatch emits diagnostic |
| `role_sequence_digest` | `Digest | null` | no | digest of roles in actual message order | mismatch emits diagnostic |
| `input_projection_digest` | `Digest | null` | no | digest of manifest source summary | mismatch emits diagnostic |
| `runner_call_projection_artifact_ref` | `HostInternalRef | null` | no | ref to LLM-facing runner input projection payload/artifact | required for complete reconstruction |
| `runner_call_projection_artifact_digest` | `Digest | null` | no | digest of runner input projection body | required when projection ref is present |
| `runner_call_projection_artifact_size_bytes` | `int | null` | no | bounded size summary for projection payload/artifact | non-negative when present |
| `diagnostic` | `RunnerCallReconstructionDiagnostic` | yes | typed complete / limited / mismatch signal | always explicit；`complete` 必须携带与 validation status、message count、role digest 同源的固定 shape diagnostic，不得为 `null` |

`ProjectorMetadataSummary` 只由已验证 manifest 中的完整 metadata descriptor 重建 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest` 与 `purpose`。完整 descriptor 固定包含这五个字段和 `source_contract_refs`，不得使用旧 `metadata_id` 别名或默认 schema version。summary 不得包含 Python module path、source code text、完整 prompt、完整 messages 或 Host 私有 ledger dump。

`RunnerCallReconstructionDiagnostic` 是内部诊断 contract，状态只允许：

- `complete`：所有必需 refs / digests / counts 校验通过。
- `limited_signal`：缺少 durable atom 或 ref，导致无法完整重建，但没有发现矛盾。
- `mismatch`：observed data 与 expected data 冲突。

diagnostic 字段固定为 `status`、`reason`、`missing_atom_kind`、`missing_ref_kind`、`missing_ref`、`observed_count`、`expected_count`、`observed_digest`、`expected_digest`、`consumer_boundary`。`reason` 在非 `complete` 时必填，只允许 `missing_runner_call_manifest`、`missing_projection_artifact`、`missing_tool_call_arguments_atom`、`missing_semantic_query_atom`、`missing_compactor_manifest`、`missing_memory_snapshot_body`、`unsupported_projector_version`、`message_count_mismatch`、`role_sequence_digest_mismatch`、`input_projection_digest_mismatch`、`payload_digest_mismatch`、`unresolvable_ref`、`provider_specific_atom_deferred`。`missing_atom_kind` 只允许 `tool_call_arguments`、`semantic_query`、`runner_call_manifest`、`compactor_manifest`、`projection_artifact`、`memory_snapshot_body`。`missing_ref_kind` 只允许 `payload_ref`、`artifact_ref`、`event_ref`、`cursor_ref`。`consumer_boundary` 只允许 `tool_trace_query`、`analyzer_fixture`、`compact_evidence_projection`、`public_smoke`；compact LLM-facing text 只能得到业务中性的 unavailable wording，不能得到 refs、digests、event ids、cursors 或 diagnostic ledger details。

`RUNNER_CALL_INPUT_ITERATION_LINKED` 只复用 runner-call diagnostic 中的 `message_count_mismatch` 与 `role_sequence_digest_mismatch` 表达 Engine observed input 与 prepared manifest expected input 的差异。Engine ingest rejected reason 不属于 `RunnerCallReconstructionDiagnostic.reason` 闭集，不得写入 Tool Trace runner-call diagnostic。

Engine ingest rejected reason 的 runner-call link 子集固定为：

- `missing_runner_call_manifest`：当前 `attempt_id` / `execution_id` 的第一个 accepted `ITERATION_STARTED` 到达时，没有唯一 unlinked prepared ordinary manifest。该 reason 用于 initial runner call fail-closed，不用于 Engine-only continuation。
- `ambiguous_runner_call_manifest`：当前 `attempt_id` / `execution_id` 下存在多条 unlinked prepared ordinary manifest，Host 无法唯一确定 Engine iteration 对应哪个 prepared input。使用该 reason 时不得追加 `RUNNER_CALL_INPUT_ITERATION_LINKED`。
- `runner_call_iteration_link_conflict`：同一 `run_id` / `attempt_id` / `execution_id` / `iteration_id` 已有 accepted `RUNNER_CALL_INPUT_ITERATION_LINKED`，但当前 Engine observation 与既有 link 的 manifest identity、iteration index、message count、role digest 或 serializer schema version 不一致。使用该 reason 时不得追加第二条 link。
- `runner_call_manifest_mismatch`：存在唯一 unlinked prepared ordinary manifest，并已追加 `RUNNER_CALL_INPUT_ITERATION_LINKED` mismatch event；其 `message_count` 或 `role_sequence_digest` 与 Engine observation 不一致。具体差异写在 link event diagnostic 的 `message_count_mismatch` 或 `role_sequence_digest_mismatch` 中。

约束：

- Sink 不拥有 Session / Run / Attempt 状态。
- Sink 失败不能回滚 EventLog。
- Sink 按 `event_sequence` checkpoint 追平，并按 `event_id` 幂等消费。
- Sink 慢只能表现为 projection lag，不能拖慢 Host append、run admission、cancel、resume、terminal 收口。
- 第一版不引入重型消息系统；SQLite EventLog + projection checkpoint + 本地后台 worker / 任务循环足够表达可靠追平语义。
- Sink notification 只是一种 wakeup；正确性来自 EventLog replay + checkpoint，不来自内存通知是否送达。

## 15. Audit

Audit 不是事实真源；audit sink 消费 committed EventLog 生成 audit projection。

Audit 的输出 owner 只能投影固定审计字段、operation context refs / digest、policy / reason 摘要与 payload ref / digest；不得复制 canonical payload、`effective_execution_config`、provider headers 或 API key。即使内部 EventLog 合法持久化 resolved execution config，audit JSONL、audit query / analyze 输出与相关 operator log 中的 provider secret 明文也必须为零。

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

EventLog 是真源；Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 都是 read model 或 projection。public HostEvent / read API、outbox、memory / compact / evidence 与任何 LLM-facing material 只能输出各自 typed owner 明确选择的业务字段，不得透传内部 effective execution snapshot、provider headers 或 API key；Host / Service / Engine operator logs 同样不得记录这些 secret 明文。

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

`ToolsDiscovery` 的 provider 结果必须能形成稳定来源解释：provider identity 非空且不重复，source refs 必须存在，`content_digest` 由 `ToolsDiscovery` 基于稳定声明内容统一计算。digest 只覆盖 tool name、LLM-facing schema、truncate spec、tags 与 display metadata 等声明内容，不 hash callable 对象本身。启用 provider 返回空工具集合是配置错误；需要让 provider 不参与发现时使用 provider-level `enabled=false`。scene manifest 的 `tool_selection.allow_empty` 只控制 scene 工具选择空匹配语义，不允许 ToolsDiscovery provider 返回空输出。业务工具不得占用 framework reserved tool name，例如 `fetch_more`。

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
- 消费当前已装配的权限 / policy；统一 tool authorization 目标边界见 18.4。
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

### 18.4 Tool Authorization 与防御性安全边界

Tool 的统一 security 设计主要指 authorization：谁发起的哪次 Run / Attempt 可以调用哪个
工具，以及该调用允许读、写、执行或访问哪些资源。该授权决策的最终语义 owner 在 Host，
执行 gate 位于 ToolRuntime 或与 ToolRuntime 同级、由 Host 拥有的 tool-governance boundary。
Engine、LLM、Service adapter、CLI 和具体业务工具不得各自拥有第二套最终权限判断。

当前 `HostCallContext.authorization_claims` 只记录上层已经验证的权限声明；它尚未定义 claims
如何映射为 tool path roots、read/write operations、network targets、side-effect authority 或
process capability。当前 WU 不实现 repository-wide tool authorization framework，也不提前冻结
permission schema、角色模型、capability token、policy language、sandbox backend 或配置位置。

未来设计统一权限时必须至少明确：

- principal / actor 与 Run / Attempt / tool call 的绑定。
- tool identity、允许操作类型和资源 scope，例如 read roots、write roots、network scope 与
  destructive/paid side effects。
- authorization claims、scene/tool selection、operator config 与 tool declaration 的组合及
  deny precedence。
- attempt snapshot、retry/resume/recovery 的权限冻结或重新授权规则。
- dispatch 前决策、实际 I/O enforcement、process/remote backend 传播、audit/trace 和拒绝错误码。

Host 拥有授权语义不等于 Host 可以只检查一次字符串后取消下层防御。路径 resolve、symlink
containment、文件原子发布、socket peer/DNS/redirect 验证、资源预算和 provider protocol 校验必须
在最接近实际 I/O 的 Tool/provider/storage/process boundary 继续执行。未来 Host authority 是调用
可以做什么的上限；下层防御可以因实际环境 fail closed，但不得扩大 Host 已拒绝的权限。

在统一 authorization 设计落地前，现有 Tool config 权限机制保持现状，例如 Doc
`allowed_paths` 与 Web 网络策略。它们是当前有效执行约束，不因未来 owner 已确定而删除；未来
迁移必须在一个独立 WU 中建立同源 Host authority 并移除重复真源，不保留长期双重权限配置。

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

deadline 与 observation timeout 是两个不同的 Host 事实。Host 在 durable
`deadline_at` / `expires_at` 到期后确认 expiry 时，必须在一个 write transaction
内追加失败型 `TOOL_RESULT_ACCEPTED` 与 `RUN_FAILED`、把 wait 收为 `failed` 并释放
Session active slot；该失败固定使用 `wait_deadline_expired`，不能解释为 `lost`，也不能
接受 deadline 后到达的 provider success。poll、callback 与 direct/manual result 都委托
同一个 transaction-local expiry helper；迟到结果只在 expiry commit 后追加 diagnostic，
projection catch-up 与 queue promotion wake 必须先于向 caller 返回 late-result error。

同步 wait adapter observation 受 Host runtime policy 的 finite-positive 单次调用预算、
finite-positive close drain 预算与 positive outstanding cap 约束。每个 invocation 使用只持
adapter、immutable wait snapshot、发布 token 与单槽结果通道的 daemon thread；token 按
`ACTIVE -> INVALIDATED -> FINISHED` 迁移。timeout 或 supervisor close 必须先撤销发布权，
迟到结果只能以 `publish=false` 丢弃，不能接触 resolver 或 durable authority。poll observation
超时只证明本次状态查询没有在预算内返回，不证明外部 job 已丢失；poller 必须记录 transient
diagnostic、释放 claim 并按 policy backoff，不得调用 `resolve_wait` 或把 wait / Run 收为 `LOST`。
只有 adapter 基于 authoritative provider / external-job 状态显式返回 typed lost outcome，Host
才能通过 common resolve path 收为 `LOST`。cancelled wait 的 abandon observation timeout 只写
poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 Host policy backoff，durable
status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied、unsupported
或 noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker，且不调用 wait resolve。
supervisor close 对 poller loop 与全部 observation thread 只使用一个 shared monotonic deadline；
预算耗尽后可保持 `CLOSING` 有界返回，最后一个 tracked thread finally 结束后才进入 `STOPPED`。

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
- `poll` adapter 从 wait record 读取 `external_job_id` / `await_spec` 后继续轮询，并在完成时调用同一个 `resolve_wait`；若 provider observation 前已确认 durable deadline，则调用 common expiry helper，provider call count 必须为零。生产 poller 由 `open_host` composition root 在显式配置 poll adapter registry 与 wait poller policy 后启动；默认不启动。poller 每轮通过 durable claim / expiry / next-observe / backoff 字段判断 wait record 是否可观察，防止多个 poller 同时处理同一 wait。正常 `not_ready` 表示外部 job 仍在运行，只写入短间隔 next-observe，不增加错误 backoff attempt；observation timeout、adapter error、missing adapter、capacity、resolve error 或 shutdown-skipped 写入可重试 backoff，不把 observation failure 猜成 external-job terminal fact。没有可 claim wait record 时，supervisor 使用 idle 间隔降低空查频率；有 active wait 但未到 next-observe / claim expiry 时，supervisor 睡眠到下一次 due 或 idle 上限，并可被本地 wakeup 打断。空轮询不逐轮输出空摘要日志。claim / backoff 只约束 poll observation 资格，不是 Attempt ownership、EventLog truth 或外部 job ownership。
- `callback` source 在 Phase 7 只保留 adapter contract 与 common pipeline 入口；专属 HTTP callback 服务、认证入口、复杂
  重放防护和外部系统专属 callback adapter 不属于第一版实现。后续 callback 产品化入口必须验证认证、重放防护和 idempotency
  key，然后调用同一个 `resolve_wait`。
- `manual` resolve 只能由受控入口触发，并必须写 audit projection。
- wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果；不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。poller runtime diagnostics 只描述本地 loop / close / retry 状态，不写 EventLog，也不能被解释为业务事实。
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
  -> ToolRuntime may call an internal activation adapter after accepted ack
  -> Engine may emit tool_awaiting / run_suspended with accepted refs as diagnostic confirmation
```

Engine `tool_awaiting` / `run_suspended` 不拥有 Host waiting 状态迁移；它们不能创建 wait record、不能关闭 Attempt、不能更新 Run。
需要 submit-before-accept barrier 的长事务工具只能在 Host durable accepted ack 之后由 ToolRuntime 调用内部 activation adapter。activation adapter 是 Host construction-time wiring，不进入 Engine awaiting 公共模型，不改变 `ToolAwaitingOutcome`，也不让 Engine 拥有 activation、外部 job lifecycle 或 wait record truth。

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
- Attempt 已 `RUNNING` 时，必须 append `CANCEL_REQUESTED` + `RUN_CANCELLING` 并向 WorkerProxy 传播 cancel。`CANCEL_REQUESTED` 表达取消意图，`RUN_CANCELLING` 表达 Run 状态迁移。`dispatching` 本身不等于 active worker；只有 `ATTEMPT_RUNNING` 已 durable accepted 后才说明 WorkerProxy / EngineWorker 已接受执行。Host active cancel watchdog 是 accepted-cancel closeout supervisor，不提供 post-cancel timeout budget；cancel commit 会唤醒 watchdog，watchdog tick 可在当前 Attempt 仍为 `RUNNING`、dispatch 已 worker accepted 且 terminal first-committer-wins recheck 通过时写入 `ATTEMPT_CANCELLED` + `RUN_CANCELLED`，释放 Session active slot 并触发 queue promotion。该 closeout 只表达 Host durable cancel 收口，不证明 provider、工具线程、子进程、HTTP 请求、远端 job 或外部长事务已经物理停止；后续旧 worker / tool 事件仍按 identity、state 与 first-committer-wins 规则接受或拒绝。
- active cancel watchdog wake 是 opener-loop owned 的 level-triggered `asyncio.Event`。watchdog 必须在每轮 tick 前 clear event；tick 期间到达的新 wake 保持 set 并驱动下一轮，多个并发 wake 可合并但不能因 bounded queue/`QueueFull` 被吞。periodic scan 只负责 restart/fallback reconcile，不是丢 wake 的 correctness 补偿。watchdog loop 的非取消异常必须交给 execution health critical-task supervisor并提交稳定 typed fatal；scheduler 正常 close 对 task 的取消不报告 fatal。
- `cancel_run` 的 supported、deferred、terminal 与 conflict 分类必须由 `_CancelRunOperation` 在同一个 SQLite write transaction snapshot 中产生。command facade 不得在 write transaction 返回错误后另开 read transaction重判 Run/Attempt/dispatch；并发状态在获锁 snapshot 之后变化时，当前调用的错误码仍只对应该 snapshot。只有首次真正释放 active slot 的分类可触发 queue-promotion wake；幂等 replay、terminal loser 与 conflict/deferred 分类不得重复 wake。
- terminal fact 已提交后，cancel 不能改写 terminal。
- cancel 只阻止未来工作，不覆盖已接受事实。
- 已接受 tool result、awaiting outcome、final decision、canonical facts 继续保留。
- cancel 与 suspend 同时发生时，由 Host ingest 事务提交顺序决定。suspend / awaiting 已 canonical accepted 后，late cancel 不覆盖它，后续走 `WAITING -> CANCELLED`；cancel 已提交后，late suspend / awaiting candidate 不得把 Run 推入 `WAITING`，只能进入 diagnostic / tool trace 或被拒绝为 canonical fact。
- 如果外部 job 在 Run 已 `CANCELLED` 后回调或被 poll / manual 入口带回结果，Host 必须拒绝其结果作为
  `canonical_fact` 进入 EventLog，并至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event；完整 tool trace 可由
  后续 projection 消费该 diagnostic event 生成。
- cancel 控制消息最小携带 `run_id`、`attempt_id`、`execution_id`。
- accepted-cancel watchdog 没有 construction-time timeout opt-out。startup recovery 必须先执行 watchdog tick；带 accepted cancel facts 的 `CANCELLING` Run 不因缺少 timeout 配置而进入 `LOST`，而是由 watchdog closeout 或既有 terminal / recovery proof 处理。
- 同一 `(run_id, client_request_id)` cancel 重试必须返回既有结果，不重复 append `RUN_CANCELLING`。Run 已是 `CANCELLING` 时，新的不同 cancel 请求不能重复制造状态迁移；可按 policy 返回当前状态或记录 diagnostic。
- 强制终止执行环境、后台 job reconcile、细粒度资源收口失败事实属于 cancel governance 扩展能力，不影响基础 Host 状态收口。

`cancel_session_runs(host, session_id, request)` 是 session-scope cancel command，用于客户端退出、supervisor shutdown 或用户明确停止该 Session 下全部未完成工作。它不是 `close_session`，不关闭新输入入口；不是 `purge_session`，不删除事实；也不表达“客户端拥有的所有 Session”。

当前 `cancel_session_runs` 实现覆盖所有当前可闭环 non-terminal Run：`QUEUED`、pre-dispatch Attempt `STARTING`、`WAITING` 与未派发的 `RECOVERING`。active worker propagation、外部 job physical cancel / abandon 与 recovery dispatch cancellation 仍是后续强化行为；Phase 5 / Phase 7 / Phase 11 必须分别补齐，不能把当前逻辑收口解释为外部执行环境已经物理停止。

`cancel_session_runs` 语义：

- 作用范围是指定 `session_id` 下所有 non-terminal Run。
- 包含 `QUEUED`、`RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING`，以及 Attempt `STARTING` / `waiting_for_lane` 场景。
- 不影响其它 Session，不影响已终态 Run。
- 幂等范围是 `(session_id, client_request_id)`。
- accepted / queued Run 直接 `CANCELLED`，不创建 Attempt。
- Attempt `STARTING` 且尚未 dispatch / 正在 `waiting_for_lane` 时直接取消，不通知 EngineWorker。
- 已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy；Phase 5 owns 该路径。
- `WAITING` Run 取消 wait record；外部 job 物理取消由 adapter best-effort，Phase 7 继续拥有该强化路径。
- `RECOVERING` Run 在新 recovery dispatch 尚未提交前直接取消；已进入 recovery dispatch 的取消强化由 Phase 11 recovery owner 接入。
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
2. Session Summary Memory。
3. Evidence / Fact Memory。
4. Answer Anchor Memory。
5. Forward Intent Memory。
6. Trace Memory 中的 reference continuity items。
7. selected recent window。
8. 当前 `USER_INPUT_ACCEPTED` 对应的 current input。
9. replay / retry / steer / resume guidance。
10. 当前 attempt 的工具 schema snapshot 与运行 policy。

普通 public RunInputBuilder 输出必须满足 one-system-message hard contract。这里的普通 public RunInputBuilder 输出指由 Host public opener / follow-up / retry / replay / resume / forced-answer / length-continuation / tool-result continuation 等用户 Run 路径构造并交给 Engine / Runner 的 `AgentRunRequest.messages`；Host-owned compactor proposal call 不属于该 ordinary RunInput contract，而受 24.2 compact I/O 边界约束。ordinary RunInput 若存在任何 system-scoped material，最终 message list 至多包含一条 `system` role message，且这条 system envelope 必须是第一条；如果没有 system-scoped material，则 message list 可以没有 `system` role。selected recent window 中的用户输入继续使用 `user` role，助手最终回答继续使用 `assistant` role，当前 `USER_INPUT_ACCEPTED` 仍是最后的 current input `user` message。实现不得为了压低 system count 把普通用户 / 助手对话历史改写成 system role。

system envelope 的 LLM-facing section 顺序、标题和分隔符是设计契约，不由实现临场发明。非空 section 按下列顺序渲染，空 section 不渲染；section header 使用 Markdown 二级标题，格式固定为 `## <title>`；相邻 section 之间使用且只使用两个换行符作为分隔，即 `\n\n`。section title 是业务可读标题，不是 projector id、Python 类型名、policy ref、内部模块名或 Host 治理字段。下表是 section title、顺序和 Conversation Memory section 映射的唯一真源；其它章节只能引用本表的映射关系，不得重复硬编码完整 title 列表。

| 顺序 | section title | 内容来源 | 渲染规则 |
|---:|---|---|---|
| 1 | `Task Instructions` | caller / Service system prompt 与场景约束 | 保留调用方给模型的任务规则；不得附带 prompt fragment ref、source digest 或 scene manifest 诊断。 |
| 2 | `Execution Guidance` | Host-neutral execution instruction、当前运行约束、工具可用性或必要继续说明 | 只写模型需要遵守的业务动作和限制；不得暴露 policy snapshot ref、Attempt / execution ledger 或调度状态。 |
| 3 | `Conversation Summary` | Session Summary Memory 或 accepted compacted view 中的会话摘要 | 只写 compact / memory 已接受的业务摘要；不得内联 raw compact artifact JSON 或 compact boundary。 |
| 4 | `Verified Evidence and Facts` | Evidence / Fact Memory、accepted evidence-backed facts，以及 memory / fact pipeline 已接受的 evidence material | 写业务可读 tool name、query / 参数文本、response / source text 和 prompt-local source label；不得写 tool_call_id、event id、payload ref、digest 或 cursor。 |
| 5 | `Prior Answer Anchors` | Answer Anchor Memory | 写可被后续指代的历史回答轮廓；不得把 anchor 当作事实证明。 |
| 6 | `Open Follow-up Context` | Forward Intent Memory | 写未完成任务、待澄清点或下一步上下文；不得把 intent 当作工具执行计划或事实。 |
| 7 | `Reference Continuity` | Trace Memory reference continuity items | 写解析“刚才”“第二点”等局部指代所需的最小文本。 |
| 8 | `Recent Evidence` | 未进入 memory / fact pipeline 的 fallback bounded material、wait-resume 或其它 evidence-like bounded material | 仅在 material 不能作为合法 `user` / `assistant` role 进入 Engine contract，且尚未被 memory / fact pipeline 接受时使用；不得暴露 fallback diagnostic、wait record id 或内部恢复状态。 |
| 9 | `Resume Guidance` | replay / retry / steer / resume / wait continuity guidance | 只写当前继续目标和用户可理解的恢复说明；不得写 tool_call_id、Attempt id、execution id、runner iteration id 或内部账本字段。 |

evidence material 的 section routing 必须唯一归属：已经作为 verified / accepted memory facts 或 memory / fact pipeline accepted evidence 的材料只能进入 `Verified Evidence and Facts`；未进入 memory / fact pipeline 的 fallback bounded material、wait-resume 或其它 evidence-like bounded material 只能进入 `Recent Evidence`；同一条 evidence material 不得同时渲染到两个 section。若某条 recent material 已被 memory / fact pipeline 接受，后续只能按 accepted memory / fact material 路由，不再按 recent fallback material 路由。

selected recent window 的 role preservation 优先于原始交错位置 preservation。用户输入和助手最终回答必须保持原 role 和相对顺序；当前 Engine message contract 不支持 ordinary RunInput historical evidence 使用 `tool` role，因此 selected recent evidence 和其它不能作为 `user` / `assistant` role 保留的 historical evidence 默认进入首条 system envelope，并按上一段唯一归属规则路由到 `Verified Evidence and Facts` 或 `Recent Evidence` section。该选择会把原本夹在历史 user / assistant turn 中间的 evidence 提前到 system envelope 内，是被接受的 trade-off：它用稳定的 provider-independent one-system-message shape 换取 evidence 原始交错位置的弱化。实现必须用 public path smoke 证明 role shape 收敛，并用 focused tests 证明 follow-up 仍能读取 evidence 中的关键业务文本；未来如果 Engine contract 支持 historical evidence 使用 `tool` role，可在后续 work unit 中重新评估是否把 selected recent evidence 保留在原交错位置。

ordinary RunInput 的 LLM-facing material 不得暴露内部治理标识。下表是实现时必须采用的替换边界；未列出的内部 ref / ledger 字段按同类最严格规则处理。可进入 manifest、Tool Trace、audit、diagnostic 或 payload descriptor 的 internal refs，不得作为模型阅读材料进入 system envelope、selected recent window 或 current input。

| 内部字段 / 标识 | LLM-facing 策略 | 可接受替代文本 |
|---|---|---|
| `policy_snapshot_ref`、policy ref、policy name | 删除 ref；如模型需要知道行为约束，只保留 Host-neutral 业务规则 | “Use the available context and tools under the current run limits.” |
| `tool_call_id`、tool request id、tool result id | 删除 id；用业务 tool name、query / 参数文本、response / source text 表达 | “A previous tool call to `<tool name>` returned: ...”；若 query 不可读则写 “The original tool query is not available in readable form.” |
| EventLog event id、event sequence、durable event ref | 删除；如需顺序，只用自然语言或 prompt-local label 表达 | “Earlier in this conversation...” 或 `Source E1` 这类 prompt-local label。 |
| payload ref、artifact ref、payload descriptor、artifact descriptor | 删除；改用已校验的 bounded readable content | 直接展示业务文本摘要或 “The detailed artifact is not available in readable form.” |
| digest、content digest、semantic input digest、role sequence digest | 删除；不得把 digest 当作业务事实或 query 文本 | “The original query text is not available in readable form.” |
| cursor、compact boundary、projection checkpoint、memory snapshot cursor | 删除；不要求模型理解边界 | “Recent conversation context:” 或 “Earlier accepted summary:” |
| projector metadata、projector id、schema version、source contract refs、projection artifact ref | 删除；只保留 section title 和业务文本 | 不写替代字段；manifest 保留 provenance。 |
| Attempt ledger、execution ledger、attempt id、execution id、iteration id、runner call index | 删除；如影响当前继续目标，用用户可读恢复说明 | “Continue from the previous interrupted step.” |
| scheduler、lane、worker、dispatch、recovery 内部状态 | 删除；如用户需要知道状态，只写业务可见状态 | “The previous step was interrupted before a final answer.” |
| Python 类型名、Host / Engine 内部类名、内部 enum 名 | 删除；用当前 prompt 自足说明字段含义 | 使用业务 schema 名或普通自然语言；不得写 `ConversationCompactOutputVNext` 这类实现类型名。 |

system envelope merge 只能合并已经由各 input provider / projection policy 治理后的 bounded content，不得新增、展开或重新召回内容。实现必须保留各 section 原有 item cap、char cap、selected recent window cap、floor 和 compact / fallback budget 约束；merge 后的总 envelope 大小必须有可测断言：`len(merged_system_content) <= sum(len(candidate_system_content)) + deterministic_header_separator_overhead`，其中 `candidate_system_content` 是所有准备进入 system envelope 的 bounded rendered content，`deterministic_header_separator_overhead` 只包含非空 section 的固定 Markdown header、header 与内容之间的固定换行，以及 section 间固定 separator。若某 section 在 merge 前已超出其 provider cap，必须在 provider 边界 fail closed 或截断；merge helper 不得用新的全局截断掩盖上游 cap 失效。focused tests 必须覆盖 section cap preservation 或上述总字符数 sanity，并断言 merge 没有引入候选 system content 之外的新业务文本。

同一 EventLog 在同一 policy 下必须构造出等价 messages；projection lag、preview delta 或 sink failure 不能改变 RunInputBuilder 输出。

RunInputBuilder 的输出必须能由输入 fact refs、memory snapshot cursor、compact artifact refs 与 policy snapshot 解释；不得依赖未持久化的旧 provider request、旧 EngineRunner 内存或 UI 临时状态。

应进入 messages 的典型事实：

- `USER_INPUT_ACCEPTED`、steer input、resume input、follow-up input。
- assistant final answer / assistant conclusion，作为对话连续性，不是 `evidence_backed_fact`。
- accepted tool result、tool terminal result、evidence anchor / ref / digest。
- tool awaiting resolved 后的 terminal / result fact。
- Host memory block：session summary、evidence-backed facts、answer anchors、forward intents、reference continuity items。
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

### 23.1 Runner-call Input Assembly Manifest

RunInputBuilder 每次完成 logical runner call input assembly 后，Host 必须写入 `RUNNER_CALL_INPUT_ASSEMBLED` canonical reconstruction event，并把完整 manifest body 存为 `runner_call_input_manifest` payload descriptor / artifact。该 event 的 hot payload 只记录 `session_id`、`host_run_id`、`attempt_id`、`execution_id`、`runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`、`manifest_payload_ref`、`manifest_digest`、`manifest_schema_version`、`validation_status`、message count / role digest / input projection digest、runner-call projection ref / digest / size 与固定 shape self-describing diagnostic；hot payload 禁止逐消息内容、projector metadata 数组或其它随 message count 增长的字段。complete hot payload 的 diagnostic 必须显式写 `status="complete"`，不得用 `null` 表达 complete。`manifest_digest` 必须等于 manifest body canonical JSON digest；hot payload scope fields 必须与 manifest identity fields 一致。ordinary、Engine continuation 与 compactor producer 必须复用同一个 Host manifest / hot contract owner。该 event 没有 Run / Attempt 状态副作用，不驱动 recovery、memory、lifecycle、terminal decision 或 dispatch decision。

ordinary RunInput 的 manifest 必须记录 one-system-message normalization 之后的最终 messages，而不是 merge 前候选 messages。`message_count`、`message_entries`、`role_sequence_digest`、每条 message 的 `index` / `role` / `content_digest` / `content_size_bytes` 必须与实际交给 Engine / Runner 的 `AgentRunRequest.messages` 同源。完整 LLM-facing message 明文写入 `runner_call_input_projection` payload/artifact，并由 manifest-level `runner_call_projection_artifact_ref` / `runner_call_projection_artifact_digest` 与每条 message entry 的 projection ref / digest 指向。manifest 中的每条 projector metadata 必须完整且只含 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose`、`source_contract_refs` 六个字段；compactor 也必须显式提供 schema version 与 source refs，不得为旧字段名、缺失版本或缺失来源提供 fallback。manifest 可以保存 source refs、projection artifact refs、digests 和 cursor refs 来解释 section 来源；这些 internal fields 仍只属于 reconstruction / Tool Trace / audit / diagnostic 边界，不得泄漏到 LLM-facing envelope。

ordinary `RUNNER_CALL_INPUT_ASSEMBLED.validation_status="complete"` 只表示 Host prepared input manifest 自身完整，且与 Host-built final messages 同源；它不表示该 input 已被 Engine observation 校验。ordinary prepared manifest 的 `iteration_id` / `iteration_index` 可以为 `null`，因为它在 Engine `ITERATION_STARTED` 之前写入。RunInputBuilder 写入 ordinary prepared manifest 的 transaction 必须在 Attempt dispatch / worker start 前 durable commit；Engine ingest 若在当前 `attempt_id` / `execution_id` 的首次 accepted iteration observation 时看不到唯一 unlinked prepared ordinary manifest，必须 fail closed。

Engine ingest 接受 `ITERATION_STARTED` 后，Host 必须通过追加式 `RUNNER_CALL_INPUT_ITERATION_LINKED` canonical fact 关联 prepared manifest 与 Engine iteration，不得回写旧 `RUNNER_CALL_INPUT_ASSEMBLED` manifest body、payload descriptor、payload digest 或 hot payload。`RUNNER_CALL_INPUT_ITERATION_LINKED.validation_status="complete"` 才表示 prepared input 已由 Engine `message_count` / `role_sequence_digest` observation 校验。link event 没有 Run / Attempt 状态副作用，不驱动 recovery、memory、lifecycle、terminal decision 或 dispatch decision。

`RUNNER_CALL_INPUT_ITERATION_LINKED` resolution 规则：

- 先在当前 `run_id` / `attempt_id` / `execution_id` / `iteration_id` 查找既有 link。只有既有 link 的 `validation_status="complete"` 且 observation 完全一致时才幂等接受；若 manifest identity、iteration index、message count、role digest 或 serializer schema version 不一致，写入 `ENGINE_EVENT_REJECTED(reason="runner_call_iteration_link_conflict", stop_worker_stream=true)` 并 fail closed；若既有 link 是 `validation_status="mismatch"`，继续写入 `ENGINE_EVENT_REJECTED(reason="runner_call_manifest_mismatch", stop_worker_stream=true)`，不得追加 accepted `ITERATION_STARTED` preview。
- 查找 unlinked prepared ordinary manifest 时，只允许 `RUNNER_CALL_INPUT_ASSEMBLED.validation_status="complete"`、`iteration_id is null`、`iteration_index is null`、`compactor_identity is null`，且 `runner_call_kind` 属于 `initial_user_dispatch` / `followup_user_dispatch` / `post_compaction_dispatch`。`tool_result_continuation` 与 `compactor_proposal` 不得进入 ordinary link candidates。
- unlinked 判定必须在同一个 Host transaction 内排除已被当前 `run_id` / `attempt_id` / `execution_id` 下 accepted `RUNNER_CALL_INPUT_ITERATION_LINKED.manifest_event_id` 引用的 manifest。实现可以使用 bounded scan 或 SQLite JSON anti-join；不得依赖 `RUNNER_CALL_INPUT_ASSEMBLED` 总计数。
- 候选为 1 且 Engine `message_count` / `role_sequence_digest` 均匹配时，同一 Host transaction 内追加 `RUNNER_CALL_INPUT_ITERATION_LINKED` 与 accepted `ITERATION_STARTED` preview。
- 候选为 1 但 count 或 role digest mismatch 时，同一 Host transaction 内追加 `RUNNER_CALL_INPUT_ITERATION_LINKED(validation_status="mismatch")` 与 `ENGINE_EVENT_REJECTED(reason="runner_call_manifest_mismatch", stop_worker_stream=true)`，不得追加 accepted `ITERATION_STARTED` preview。
- 候选大于 1 时写入 `ENGINE_EVENT_REJECTED(reason="ambiguous_runner_call_manifest", stop_worker_stream=true)`，不得追加 link event。
- 候选为 0 时，只有当前 `run_id` / `attempt_id` / `execution_id` 下已有 accepted `RUNNER_CALL_INPUT_ITERATION_LINKED` 或 accepted `ITERATION_STARTED` preview，才允许作为 Engine-only continuation 写 canonical manifest；即使 continuation 的 `iteration_index == 0`，也不得匹配已 linked ordinary manifest。若 Engine `iteration_started.input_projection` 携带完整 observed messages，Host 必须保存 `runner_call_input_projection` payload/artifact 并写 `validation_status="complete"` 的 continuation manifest；若缺少完整 projection，只能写 `validation_status="limited_signal"` 且 reason 为 `missing_projection_artifact`。若没有 prior accepted iteration observation，必须写入 `ENGINE_EVENT_REJECTED(reason="missing_runner_call_manifest", stop_worker_stream=true)`，不得用 continuation manifest 掩盖 ordinary prepared manifest 缺失。

验证边界分两层：public path smoke 只能通过实际 public request / scripted runner `messages_seen` 证明 ordinary runner call 至多一条 system message；focused durable manifest tests 可以通过 manifest recorder 或 payload resolution helper 读取 manifest，证明 manifest 与 normalized final messages 同源。focused manifest tests 不得把直接读取私有 SQLite table 当作证明 public message shape 的替代路径。

`RunnerCallInputAssemblyManifest` 是 durable reconstruction contract，不是 message dump。字段固定为：

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `schema_version` | `str` | yes | manifest contract version | equals design-approved current version |
| `manifest_id` | `str` | yes | stable logical id for this manifest body | unique within payload/artifact namespace |
| `session_id` | `str` | yes | parent Session scope | equals canonical event `session_id` |
| `host_run_id` | `str` | yes | Host admitted user Run for ordinary calls; parent user Run for compactor calls | equals canonical event `host_run_id` |
| `attempt_id` | `str | null` | conditional | Host Attempt that owns this runner call when one exists | required for ordinary dispatch after Attempt creation; null allowed for pre-dispatch proactive compact |
| `execution_id` | `str | null` | conditional | Engine execution envelope id when call belongs to Engine execution | required for Engine-emitted ordinary/tool continuation calls |
| `runner_call_index` | `int` | yes | Host-owned monotonic zero-based index per `host_run_id`; compactor operations use a separate zero-based index scoped by `compaction_operation_id` | first call is 0; each later call in the same scope increments by 1 |
| `runner_call_kind` | `RunnerCallKind` | yes | non-overlapping business kind of the logical call | value must be in the closed enum below |
| `runner_call_trigger_reason` | `RunnerCallTriggerReason` | yes | why this call was assembled now | value must be compatible with `runner_call_kind` |
| `iteration_id` | `str | null` | conditional | Engine iteration id for calls observed by Engine | required when Engine emitted an iteration-started event |
| `iteration_index` | `int | null` | conditional | Engine iteration index | non-negative when present |
| `message_count` | `int` | yes | number of messages sent to runner/provider boundary | equals `message_entries` count and Engine `message_count` when present |
| `role_sequence_digest` | `Digest` | yes | digest of message roles in order | computed from canonical UTF-8 string `role0\nrole1\n...` over allowed roles |
| `input_projection_digest` | `Digest` | yes | digest of canonical manifest source summary, not full rendered messages | recompute from message entry content digests, source refs and projector metadata |
| `runner_call_projection_artifact_ref` | `HostInternalRef | null` | no | ref to LLM-facing rendered message projection | required for complete reconstruction |
| `runner_call_projection_artifact_digest` | `Digest | null` | no | digest of LLM-facing rendered message projection | required when projection ref is present |
| `runner_call_projection_artifact_size_bytes` | `int | null` | no | bounded projection payload/artifact size summary | non-negative when present |
| `message_entries` | `list[RunnerCallMessageEntry]` | yes | per-message lightweight provenance and digest | length equals `message_count`; indexes contiguous |
| `source_cursor_refs` | `list[HostInternalRef]` | yes | EventLog cursor, memory cursor, compact boundary or equivalent source boundary | every ref must resolve or produce limited-signal diagnostic |
| `tool_schema_snapshot_refs` | `list[HostInternalRef]` | no | selected tool schema snapshot ref / digest / size visible to the call | required when tools are available |
| `memory_snapshot_cursor_ref` | `HostInternalRef | null` | no | memory read model cursor used by RunInputBuilder | missing historical snapshot body leaves manifest valid and emits limited-signal for body reconstruction |
| `compact_artifact_refs` | `list[HostInternalRef]` | no | accepted compact artifacts or fallback diagnostic artifacts used in input selection | refs must point to accepted compact or explicit fallback diagnostic |
| `context_fallback_decision_ref` | `HostInternalRef | null` | no | tiered dispatch fallback decision when compaction recovery failed but dispatch continued | present only when tier 4/5 fallback affected this input |
| `projector_metadata` | `list[ProjectorMetadata]` | yes | stable producer metadata for each message/source projection | every message `projector_metadata_id` must resolve here |
| `compactor_identity` | `CompactorRunnerCallIdentity | null` | conditional | parent/self identity for Host-owned compactor calls | required when `runner_call_kind == "compactor_proposal"` |
| `diagnostic` | `RunnerCallReconstructionDiagnostic | null` | yes | manifest body 的 typed incomplete/mismatch signal | manifest body 在 `complete` 时固定为 `null`，非 `complete` 时必须携带 typed diagnostic；canonical event hot payload 无论状态都必须显式携带固定 shape diagnostic |

`RunnerCallMessageEntry` 字段固定为：

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `index` | `int` | yes | message order in actual runner call input | contiguous from 0 |
| `role` | `"system" | "user" | "assistant" | "tool"` | yes | LLM role sent to runner | must match Engine/provider role vocabulary accepted by `AgentRunRequest` |
| `content_digest` | `Digest` | yes | digest of rendered content for this message | computed from canonical text/parts serializer chosen by projector metadata |
| `content_size_bytes` | `int` | yes | bounded observability for payload size | non-negative; used to test manifest stays bounded |
| `source_refs` | `list[HostInternalRef]` | yes | canonical facts, payload descriptors, compact artifacts, memory cursors or tool result refs that explain the message | empty only for static system prompt with prompt asset digest in projector metadata |
| `projection_artifact_ref` | `HostInternalRef | null` | no | optional derived rendered-message artifact for analyzer/debug | may be null; if present digest must match `projection_artifact_digest` |
| `projection_artifact_digest` | `Digest | null` | no | digest of optional derived rendered-message artifact | required when artifact ref is present |
| `projector_metadata_id` | `str` | yes | lookup id into manifest `projector_metadata` | must resolve to one projector metadata entry |
| `provider_tool_calls_digest` | `Digest | null` | no | digest for assistant tool_calls/provider structured parts when present | absent unless provider contract exposes typed fields |
| `reasoning_content_digest` | `Digest | null` | no | digest for provider reasoning content if typed Engine contract exposes it | absent unless provider contract exposes typed field |

Provider-specific assistant `tool_calls` / `reasoning_content` 不得以 raw provider dict、untyped payload bag 或 Python object 进入 Host manifest。若 Engine provider contract 已有 typed 字段，manifest 只保存 digest；若当前 provider data 只有 raw provider state，则 runner-call reconstruction 对该 atom 输出 `provider_specific_atom_deferred` limited-signal，具体 typed provider atom 属于后续 Engine provider contract work。

`ProjectorMetadata` 字段固定为：

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `projector_metadata_id` | `str` | yes | stable id referenced by message entries | unique within manifest |
| `projector_id` | closed string enum | yes | semantic projector identity | must be one of design-approved ids |
| `projector_schema_version` | `str` | yes | output contract version for the projector | unsupported consumer emits `unsupported_projector_version` |
| `projector_digest` | `Digest` | yes | digest of prompt asset / config / projector contract that affects output shape | recompute from declared source refs where possible |
| `purpose` | closed string enum | yes | why the projector contributes to LLM input | must be one of design-approved purposes |
| `source_contract_refs` | `list[HostInternalRef]` | yes | design/prompt/tool schema/config refs that define projector input contract | every ref must resolve or produce diagnostic |

第一版 `projector_id` 至少覆盖 `run_input_system_context`、`user_input_message`、`assistant_history_message`、`tool_result_message`、`compact_memory_material`、`recent_window_material`、`guidance_message`、`tool_schema_snapshot`、`compactor_system_prompt`、`compactor_user_prompt`。第一版 `purpose` 至少覆盖 `ordinary_run_input`、`tool_continuation_input`、`post_compaction_input`、`compactor_proposal_input`、`retry_replay_resume_input`、`forced_answer_input`、`length_continuation_input`。这些枚举是 Host / trace 内部 contract；LLM-facing compact material 或 prompt 不得暴露 projector id、schema version、digest 或 source contract refs。

Closed `RunnerCallKind` enum：

| value | meaning |
| --- | --- |
| `initial_user_dispatch` | ordinary Session 中第一个被 Host admitted user input 触发的 runner call |
| `followup_user_dispatch` | 同一 Session 中后续 user input 触发的 ordinary runner call |
| `tool_result_continuation` | tool results accepted 后继续同一 logical run 的 runner call |
| `post_compaction_dispatch` | accepted compact 或 tier 4/5 dispatch fallback 后的 ordinary/recovery dispatch |
| `compactor_proposal` | Host-owned compactor proposal / repair attempt 的 runner call，不是 Host admitted user Run |

Closed `RunnerCallTriggerReason` enum：

| value | meaning |
| --- | --- |
| `initial_user_input` | initial user input dispatch |
| `followup_user_input` | follow-up user input dispatch |
| `tool_results_available` | accepted tool results make a continuation call possible |
| `force_answer_after_tool_limit` | policy forces answer after tool limit or tool loop limit |
| `finish_reason_length_continuation` | provider length finish requires continuation |
| `host_retry` | Host retry operation |
| `host_replay` | Host replay operation |
| `host_resume` | Host resume operation |
| `context_compaction_completed` | accepted compact or fallback permits next dispatch |
| `context_compaction_initial_proposal` | first compactor proposal attempt for a compaction operation |
| `context_compaction_repair_attempt` | compactor repair attempt after proposal rejection |
| `context_compaction_retry_attempt` | compactor retry attempt after proposal execution failure |

`runner_call_kind` 表达互不重叠的 logical call business kind；forced answer、length continuation、retry/replay/resume 只作为 trigger reason，不挤入 kind。该分类必须覆盖 ordinary initial / follow-up、tool result continuation、post compaction dispatch、compactor proposal、retry / replay / resume、forced answer 与 length continuation，且一个 runner call 只能有一个 kind。

Manifest size-boundary 不变量：

- manifest 不内联 full messages、完整 prompt、完整 compact material、完整 memory snapshot、provider raw request 或 provider raw response。
- manifest 只保存 source refs、cursor refs、digests、message count、role sequence digest、content size、projector metadata 与可选 projection artifact refs。
- 小体积 human-readable projection 只有在对应 contract 显式允许且不违反 LLM-facing boundary 时才可 bounded inline；默认完整 rendered messages 必须走 derived payload/artifact descriptor。
- Tool Trace、analyzer 与 public smoke 可以按 refs/digests/projector metadata 做 reconstruction 或输出 limited-signal，但不能把 missing projection artifact 解释成 EventLog fact 缺失。

## 24. Conversation Memory

Conversation Memory 的目标是为生产级通用 Agent 提供可恢复、可审计、受预算约束的会话 read model，并在该通用能力之上支撑买方财报分析的跨轮事实、证据和追问连续性。它不是新的事实真源，也不是把历史全文塞回 prompt 的召回系统。

事实真源固定为 Host durable EventLog、payload descriptor 与 artifact。Conversation Memory 只从这些真源和 accepted compact projection 中投影出当前 Session 最常用、最稳定、最需要直接注入上下文的 bounded working set。第一阶段不根据当前用户 prompt 做相关性召回，不引入 memory intent parser、semantic search、vector recall 或 LLM reranker；深历史语义检索 deferred owner 为 GitHub Issue 39。

Conversation Memory 的 session-scoped 语义模型固定为五类：

1. Trace Memory。
2. Evidence / Fact Memory。
3. Session Summary Memory。
4. Answer Anchor Memory。
5. Forward Intent Memory。

User Profile Memory 是唯一跨 session 语义类，不进入 session Conversation Memory snapshot；其 durable profile store、更新、撤销、删除、导出、隐私与跨 session projection deferred owner 为 GitHub Issue 115。

### 24.1 Compact / Delta 边界

第一阶段采用 material boundary 与 policy-conditioned deterministic assembly：

```text
memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material

rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

`latest_accepted_compacted_view` 是 Host 内部已接受的 compact projection，用于代表 compact 覆盖范围内的旧历史；没有 accepted compact 时为空。给 LLM 的只能是 Host 从它投影出的业务语义视图，不是 raw compact artifact JSON、EventLog payload 或内部字段全集。该视图必须展开为五类 Session Semantic Memory，而不是一个黑盒 material：

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

`post_compact_delta_material` 是最近一次 accepted compact 之后新产生、尚未被 compact 覆盖的 committed canonical material；没有 accepted compact 时从 session 起点开始。它是 Host 内部材料边界，不等于全部进入 prompt 的 view。该 material 至少包含历史 `USER_INPUT_ACCEPTED.display_text`、历史 `RUN_SUCCEEDED.final_answer`、readable accepted tool evidence，以及用户可见的 Run outcome material。用户可见 outcome material 只表达用户已经感知到的业务状态，例如取消、失败、等待确认 / 澄清或无 final answer 的终止；不得包含 attempt id、execution id、cursor、compact failure、fallback tier、projection diagnostic、payload ref、digest、event id 或 Host 内部治理状态。如果某个 Run 已有 `RUN_SUCCEEDED.final_answer`，通常不需要额外渲染 succeeded outcome，因为 final answer 本身就是用户可见结果。

`current_input_anchor` 是当前 Run 的用户输入保护锚点。它不是 memory 语义类，而是 compact、fallback 与 prompt assembly 的边界字段；给模型的仍只是当前用户输入文本。当前用户说“继续刚才失败的任务”或“恢复刚才那个”属于 current input，而不是 Trace Memory。

current input anchor 单独传入 `assemble(...)`，不得被当作历史 material source。当前 Run 的 prompt 只有到下一轮成为历史时，才可能成为 `post_compact_delta_material` 的一部分。reactive / recovery / continuation 这类当前 Run 已执行到一半的 assembly snapshot 中，已经 committed 且 accepted 的 current-run tool result 可以作为 current-run delta / evidence material 参与 assembly；裸 `TOOL_CALL_REQUESTED` 没有 response 时，不应直接当成 evidence memory。

`selected_recent_window_policy` 只从 `post_compact_delta_material` 中确定性选择 bounded recent context view，不从 `latest_accepted_compacted_view` 中重新选择 raw recent window。selected item 的基本单位是完整 material block；material block 必须带 `turn_group_id`、role / material kind、source refs 与稳定 block id。`protected_recent_floor_policy` 保护最近 N 个 turn group，而不是最近 N 个 raw item；当前设计中 `turn_group_id = host_run_id`，即一个 turn group 等于一个 Host admitted user Run。一个受保护 turn group 至少覆盖该 Run 的 user prompt、assistant final answer、accepted tool evidence 和用户可见 Run outcome material 中已经 committed 且 eligible 的部分。floor 与 item / char cap 冲突时，floor 优先；若 floor 本身按当前 conservative estimator 仍超过 hard threshold，进入 tier 5，必要时 fail closed。

`selected_recent_window` 不是第六类 Semantic Memory。它是 `post_compact_delta_material` 的 bounded recent context view，可以包含 user input、assistant final answer、user-visible run outcome material 与 readable evidence material；`trace_memory.reference_continuity_items` 才是 compact 后属于 Trace Memory 的 semantic item。把 selected recent window 当成独立 semantic memory 会混淆 compacted view 与 post-compact delta material，也会让 fallback 漂移成另一套 memory 系统。

`memory_projection_policy` 是 Host 内部 LLM-facing memory / material 产量的唯一 policy owner，至少覆盖 `selected_recent_window_policy`、`fallback_selected_recent_window_policy`、`protected_recent_floor_policy`、`semantic_memory_section_caps` 与 `projection_repair_policy`。JSON 配置是否保持 flat 属于实现形态，不是本设计真源要固定的要求；但 Host 内部不得用 DTO 私有 cap、renderer 私有截断值或零散常量作为另一套 LLM-facing material 产量真源。

Compact material 的真源是 Host durable EventLog、payload descriptor 与 artifact。构造 compact input 时，Host 必须从这些真源读取 latest accepted compact event、post-compact delta canonical material 与当前 input anchor；不得依赖 Conversation Memory projection checkpoint 作为 compact input 是否可构造的前置真源。Conversation Memory projection 是 accepted compact 之后的 read model 物化路径，不是 compact operation 的材料所有者。

before compact 不需要独立阶段建模。它只是 `latest_accepted_compacted_view` 为空、`post_compact_delta_material` 从 session 起点开始的普通情况：

```text
before_compact_memory_material =
  empty_latest_accepted_compacted_view
  + session_start_delta_material

before_compact_rendered_context =
  assemble(
    empty_latest_accepted_compacted_view,
    session_start_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

多次 compact 使用 rolling compacted view。第二次及后续 compact 只输入上一轮 latest accepted compacted view、selected post-compact recent window 与 current input anchor；不得重新展开已被上一轮 accepted compact 覆盖的旧 raw history。旧 compact artifact 保留在 EventLog / artifact / audit 中用于追溯和重建，但不作为当前 prompt 或下一次 compact 的默认叠加输入。

### 24.2 LLM-facing Compact I/O 硬边界

一次 compact 是一次 LLM 调用。Compact I/O 必须严格分离 Host internal control / provenance 与 LLM-readable material。

LLM-readable compact input 只能包含与当前 compact 任务有关、用户或业务可理解的材料：

- 用户输入文本、助手最终回答文本、用户可见 Run 状态连续性。
- 可读 tool name、tool query、tool response / source text。
- Host 为本次 compact 生成的 prompt-local opaque labels。
- 上一轮 accepted compacted view 的业务可读 projection。

不得作为模型阅读材料暴露，也不得要求模型返回：

- EventLog event id、event sequence、payload / artifact ref、digest、durable evidence id。
- compact cursor、compact boundary、policy name、budget diagnostic、fallback diagnostic、projection checkpoint、scheduler / Attempt / recovery 内部治理细节。
- `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` raw payload、compact artifact JSON、repair 前 candidate、失败 proposal 或中间 transient artifact。
- 任何只在当前实现版本成立的默认约定、magic string、临时缩写、位置语义或隐式排序语义。

prompt-local label 是本次 LLM 调用内的 opaque citation handle，只用于让模型把 claim、anchor、summary 或 intent 绑定到它刚读过的材料。第一阶段允许使用短 deterministic handle，例如 `C1`、`H1`、`E1`、`S1`、`E1.1`。label 不得携带位置、时间、重要性、优先级、durable identity 或实现状态语义；模型不得根据顺序、前缀、chunk 后缀或名字推断事实含义。Host 内部维护 prompt-local label 到 durable provenance refs 的映射；prompt、schema、validator 和测试可以验证 label 能映射回 provenance，但不得依赖 label 名称或 ordinal 推断业务语义。

LLM compact output 只能返回业务语义字段和 prompt-local labels。Host 负责把 labels 映射回 durable refs，校验 provenance、长度、枚举、source boundary 和 quality gate。模型不得返回 durable refs、event ids、digests、artifact refs、policy decisions 或任何 Host 内部状态字段。

compact material / prompt / query_text 的 LLM-facing 语义必须自解释。工具材料可以暴露业务可读 tool name、source-owned 业务可读 query text、符合 LLM-facing 文本约束的参数文本与工具响应/来源文本；不得暴露 `tool_call_id`、EventLog id、payload ref、artifact ref、digest、cursor、projection checkpoint、policy 名称、Attempt / execution ledger、Projector metadata 或 Host 内部账本字段。若工具只有 `semantic_input_digest` 而没有 durable semantic query text，Host 不得把 digest 当作 query 文本，也不得要求模型理解 digest；compact evidence projection 只能使用源头合规的 query / 参数文本或业务中性的 unavailable wording。若 accepted arguments atom 缺失，projection 必须产生 `missing_tool_call_arguments_atom` limited-signal，并避免向 LLM 展示内部诊断细节。

F02 的稳定问题陈述固定为：`EvidenceReadableItem.tool_name` 已有业务可读位置；真实缺口是 `query_text` 缺少 durable arguments / semantic query 的业务可读表达。实现和测试不得把该问题降级成“tool name 缺失”，也不得用 `tool_call_id=...`、payload ref、digest 或 Host 内部 id 伪装成业务 query。

LLM-facing memory / compact / RunInput material 不允许字段级 silent truncation、preview 化或 summary 化。任何给模型阅读的 `display_text`、`text`、`claim_text`、`answer_text`、`response_text`、`summary_text` 或等价业务字段，要么是完整选中 material / item / section 的可读内容，要么带明确 provenance 做 chunking，要么整体 keep / drop，要么 fail closed。上下文缩小只能通过 deterministic selection、whole-item 或 whole-section keep-drop、chunking with provenance、section-aware degrade 或 fail closed 表达；不得把超长字段静默切到固定字符数后继续让模型当作完整事实、完整证据或完整回答理解。

### 24.3 vNext Compact I/O Contract

Compact input 与 ordinary RunInput、fallback RunInput 共享同一套 material selection / rendering 语义：都从 `latest_accepted_compacted_view`、`post_compact_delta_material`、`current_input_anchor`、`selected_recent_window_policy` 与 `protected_recent_floor_policy` 推导 `rendered_context = assemble(...)`。三者差异只在 renderer、source label、accept barrier 与 tier output：compact input 使用 compactor renderer 和 prompt-local labels，并经过 compact output accept barrier；ordinary RunInput 使用普通 runner renderer；fallback RunInput 使用对应 fallback tier 的 bounded renderer。设计层不得为 compact input 另起一套 selector，也不得让 fallback selected recent window 变成独立 memory 系统。

`ConversationCompactInputVNext` 是 Host 渲染给 compactor 的唯一 user material data block，结构固定为：

```text
ConversationCompactInputVNext
  schema_version: "conversation_compact_input_v1"
  previous_compacted_view?: CompactReadableView
  trace_material: list[TraceReadableItem]
  evidence_material: list[EvidenceReadableItem]
  answer_material: list[AnswerReadableItem]
  current_input_anchor: CurrentInputAnchor
  instruction: CompactInstruction
```

compact input 子类型固定为 LLM-readable schema，不携带 Host internal refs：

```text
PromptLocalLabel = str

CompactReadableView
  session_summary?: str
  evidence_backed_facts: list[ReadableFactItem]
  answer_anchors: list[ReadableAnswerAnchor]
  forward_intents: list[ReadableForwardIntent]
  reference_continuity_items: list[ReadableReferenceContinuityItem]

ReadableFactItem
  source_label: PromptLocalLabel
  claim_text: str
  source_note?: str

ReadableAnswerAnchor
  source_label: PromptLocalLabel
  anchor_title: str
  anchor_items: list[ReadableAnswerAnchorItem]

ReadableAnswerAnchorItem
  display_text: str
  ordinal?: int

ReadableForwardIntent
  source_label: PromptLocalLabel
  intent_type: "open_question" | "pending_clarification" | "pending_user_visible_task" | "next_step_note"
  text: str
  status: "open" | "blocked" | "superseded"

ReadableReferenceContinuityItem
  source_label: PromptLocalLabel
  text: str
  reason: "local_reference" | "ordinal_reference" | "ellipsis_recovery" | "recent_state"

TraceReadableItem
  source_label: PromptLocalLabel
  trace_kind: "user_input" | "assistant_final_answer" | "user_visible_progress"
  text: str

EvidenceReadableItem
  source_label: PromptLocalLabel
  tool_name: str
  query_text?: str
  response_text: str
  source_note?: str

AnswerReadableItem
  source_label: PromptLocalLabel
  answer_text: str

CurrentInputAnchor
  anchor_label: PromptLocalLabel
  text: str

CompactInstruction
  output_schema_name: "conversation_compact_output_v1"
  compact_goal: "roll_forward_session_memory"
```

所有 readable item 的 `source_label` 都是 prompt-local opaque label，只在本次 compact 调用内有效。`display_text`、`text`、`claim_text` 与 `answer_text` 是模型可读业务内容；这些字段不得承载 durable refs、digest、event sequence、policy name 或 compact boundary。`CompactInstruction` 只表达业务任务和目标输出 schema，不承载 Host budget policy、fallback decision、repair state 或内部 provenance map。

`previous_compacted_view` 只包含上一轮 accepted compacted view 的业务可读 projection，包括 session summary、accepted evidence-backed facts、answer anchors、forward intents 与 reference continuity items；不得包含 raw compact artifact JSON。`trace_material` 只包含用户输入、助手最终回答和用户可见进展 / 结果摘要，不暴露 Host run-state 字段名。`evidence_material` 只包含可读 tool、query、response / source text 与 prompt-local evidence label。`answer_material` 只包含可读 assistant final answer / conclusion 与 prompt-local answer label。`current_input_anchor` 只包含当前用户输入文本和 prompt-local anchor label；同一 current user payload 不得再作为 trace material 重复渲染。`instruction` 只表达本次 compact 的业务任务和输出 contract 要求，`output_schema_name` 是业务可读输出 contract 标识，不是 Python 类型名；`instruction` 不承载 Host policy internals。

`current_input_anchor` 是 readable but not citable：LLM 可以读取它来理解本次 compact 的边界，Host 也用它确保当前用户输入不会被 compact / fallback 吞掉；但 `current_input_anchor.anchor_label` 不属于任何 compact candidate 的 allowed source label set。Host accept barrier 必须拒绝任何在 `source_labels`、`evidence_labels`、`answer_source_labels`、diagnostic `source_labels` 或其它 candidate source 字段中引用 `current_input_anchor.anchor_label` 的输出。当前输入只有到下一轮成为历史时，才可能作为 trace material 进入后续 compact。

`ConversationCompactOutputVNext` 是 compactor 必须返回的 strict JSON object：

```text
ConversationCompactOutputVNext
  schema_version: "conversation_compact_output_v1"
  session_summary: SessionSummaryCandidate | null
  evidence_backed_facts: list[EvidenceBackedFactCandidate]
  answer_anchors: list[AnswerAnchorCandidate]
  forward_intents: list[ForwardIntentCandidate]
  reference_continuity_items: list[ReferenceContinuityCandidate]
  diagnostics: list[CompactCandidateDiagnostic]
```

`session_summary` 为 nullable；compact 后如果没有足够材料形成 summary，Host 可以接受空 summary，但不能让空 summary 掩盖其它必需 quality gate。`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items` 必须是 list，允许为空。所有 candidate 均必须引用本次 input 中存在且允许被引用的 prompt-local source labels；未知 label、跨 section label、stale label、缺 source label 或引用 `current_input_anchor.anchor_label` 都是 candidate invalid。candidate 文本必须非空且受 policy char cap 限制；枚举字段只能使用 schema 定义值；空字符串不表达删除或清空语义。

candidate schema：

```text
SessionSummaryCandidate
  summary_text: str
  source_labels: list[str]

EvidenceBackedFactCandidate
  claim_text: str
  evidence_labels: list[str]
  source_labels?: list[str]

AnswerAnchorCandidate
  anchor_title: str
  anchor_items: list[AnswerAnchorChild]
  answer_source_labels: list[str]

AnswerAnchorChild
  display_text: str
  ordinal?: int

ForwardIntentCandidate
  intent_type: "open_question" | "pending_clarification" | "pending_user_visible_task" | "next_step_note"
  text: str
  status: "open" | "blocked" | "superseded"
  source_labels: list[str]

ReferenceContinuityCandidate
  text: str
  reason: "local_reference" | "ordinal_reference" | "ellipsis_recovery" | "recent_state"
  source_labels: list[str]

CompactCandidateDiagnostic
  code: str
  text: str
  source_labels?: list[str]
```

`EvidenceBackedFactCandidate` 只能引用 evidence material labels，不能引用 user input、assistant final answer、session summary、answer anchor 或 forward intent 后冒充工具事实。LLM-facing candidate 不输出 `evidence_kind`；Host 根据 evidence labels 所属 material section 派生内部 evidence kind，并在 accepted typed candidate / memory projection 中保留 Host-owned typed value。`AnswerAnchorCandidate` 只能引用 assistant final answer / conclusion labels。`ForwardIntentCandidate` 不能被当作工具执行计划或事实证明，也不能自动触发工具。`ReferenceContinuityCandidate` 只能保存理解局部指代所需的最小文本，不能保留整段长输入。

### 24.4 Snapshot Typed Schema

通过 Host accept barrier 的 compact output 物化为 `ConversationMemorySnapshotVNext` typed view。Snapshot 是 read model，可重建、可修复，不是事实真源。

```text
ConversationMemorySnapshotVNext
  schema_version: "conversation_memory_snapshot_v1"
  session_id: SessionId
  source_event_cursor: EventSequence
  latest_compaction_event_ref?: HostInternalRef
  trace_memory: TraceMemoryView
  evidence_fact_memory: EvidenceFactMemoryView
  session_summary_memory: SessionSummaryMemoryView
  answer_anchor_memory: AnswerAnchorMemoryView
  forward_intent_memory: ForwardIntentMemoryView
  diagnostics: MemoryProjectionDiagnostics

TraceMemoryView
  selected_recent_window: list[SelectedRecentWindowItem]
  reference_continuity_items: list[ReferenceContinuityItem]

EvidenceFactMemoryView
  evidence_backed_facts: list[EvidenceBackedFact]
  recent_evidence_items: list[RecentEvidenceReadableItem]

SessionSummaryMemoryView
  summary_text?: str
  source_refs: list[HostInternalRef]

AnswerAnchorMemoryView
  anchors: list[AnswerAnchor]

ForwardIntentMemoryView
  intents: list[ForwardIntent]
```

`HostInternalRef` 是 Host 内部 typed provenance ref，不进入 LLM-readable prompt。Snapshot item 必须保存 internal source refs、source labels mapping digest、producer compact event ref、created cursor、last updated cursor、policy ref、item digest 与 bounded diagnostic。RunInputBuilder 渲染 snapshot 时只输出业务可读文本和必要的短来源说明，不输出 durable refs、digest 或 cursor。

`latest_compaction_event_ref` 只是 provenance ref，用来说明当前 snapshot 的 compacted semantic view 来自哪个 accepted compact event；它不是 `latest_accepted_compacted_view` 本体。`TraceMemoryView.selected_recent_window` 与 `EvidenceFactMemoryView.recent_evidence_items` 如果物化在 snapshot 中，也只是对 `post_compact_delta_material` 的 bounded recent view，服务 ordinary RunInput 渲染与诊断；它们不是 compact output 生成的第六类 Semantic Memory，也不会自动生成 summary、answer anchor、forward intent 或 evidence-backed fact。

Projection 规则：

- compact 前，Session Summary Memory、Answer Anchor Memory 与 Forward Intent Memory 为空。
- compact 前，Trace Memory 与 Evidence / Fact Memory 只能从 selected recent window 中的 user / assistant / user-visible state / readable tool material 表达；它们不自动生成高阶结构化 item。
- `TOOL_AWAITING` 是 Host / ToolRuntime 之间的等待治理事实，对模型不可见。`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、wait record、poll outcome、cancel / abandon lifecycle 等 Host / ToolRuntime 等待治理事实不得成为 Conversation Memory producer，也不得投影为 LLM-facing selected recent window、recent evidence、reference continuity 或 semantic memory item。对 LLM 来说，awaiting 与非 awaiting 不改变跨轮 memory 语义；同样的 user input、ordinary tool result 与 final answer，有无中间 awaiting governance event，LLM-facing memory 必须等价。
- wait-resolution 的 `TOOL_RESULT_ACCEPTED` 必须与普通工具结果一样携带 accepted evidence envelope 和 digest-checked raw outcome。Envelope 必须指向同一工具调用的 `TOOL_CALL_REQUESTED` request atom；Conversation Memory 从 request atom 读取 source-owned 业务可读 request / query 语义，从 raw outcome 读取结果摘要，不从 `TOOL_AWAITING`、wait record、event id、payload ref 或 digest 推断模型需要理解的业务语义。
- 当前 schema 下 awaiting accept 必须同事务写入 `TOOL_CALL_REQUESTED` request atom；wait-resolution 不实现旧库兼容读取分支。历史或测试构造的旧格式 wait result 若缺少 envelope / request atom，只能在 resume input 层降级为自解释 guidance，不能进入 self-explaining Conversation Memory evidence，也不能从 `TOOL_AWAITING` 反推 request/query 语义。
- compact 成功后，accepted compact output 生成或更新五类 session memory；post-compact delta material 继续按 selected recent window 进入 prompt assembly。
- fallback tier 1-3 属于 compact recovery fallback：它们仍送 LLM compactor；accepted output 可以提交 `CONTEXT_COMPACTED`，并由 projection 生成五类 Session Semantic Memory。
- fallback tier 4-5 属于 dispatch fallback：它们不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact / memory snapshot / 五类 memory。
- accepted evidence 存在但 compactor 没有产出合法 fact candidate 时，Host 只记录 diagnostic，不合成 fallback fact。
- assistant final answer、用户输入、session summary、answer anchor、reference continuity item、User Profile、Forward Intent 都不能自动升级成 `evidence_backed_fact`。

Snapshot 与 projection checkpoint 必须在同一 durable store transaction 提交；checkpoint 不得先于 snapshot 落库。RunInputBuilder 消费 snapshot 时必须记录 snapshot cursor；若 snapshot 缺失、损坏或 lag 超过 policy 阈值，Host 进入 projection catch-up / rebuild / retry path。这不是 Run crash recovery，不得触发 Run 状态迁移，也不得把 Run 推入 `RECOVERING`。Operator-facing storage maintenance 可以只读分类 damaged snapshot row，分类结果用于诊断，不是 repair authorization；自动 overwrite、quarantine 或 rebuild 必须另行通过显式 maintenance / operator policy 设计，不能静默发生在 command path。

### 24.5 五类 Session Semantic Memory

Trace Memory 负责对话连续性，不负责事实证明。数据来源包括 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED` 的 assistant final-answer continuity 和用户可见 Run 状态。`RUN_SUCCEEDED` canonical terminal fact、payload descriptor 与 terminal artifact 是成功终态回答的真源；terminal answer continuity resolver 可以从已提交 terminal fact 的 inline `final_answer` 或 digest-checked terminal artifact `content` 读取 LLM-facing answer text。Conversation Memory projection 与 RunInputBuilder 只能消费该 resolver 产出的 typed continuity material，不能通过修改 EventLog payload mapping 让下游误以为 descriptor-backed answer 来自 canonical hot payload。TraceMemoryView 当前字段为 selected recent window 与 reference continuity items；reference continuity item 用于保存 compact 后仍需解析代词、序号、“刚才那个”等局部承接的最小上下文，不是 fact、summary、answer anchor 或 forward intent。

Evidence / Fact Memory 负责工具证据与基于证据的 claim。`TOOL_RESULT_ACCEPTED` 通过 Host accept barrier 后保存 accepted evidence envelope、payload / artifact refs 与 digest；LLM-facing evidence material 必须自解释，只包含可读 tool、必要 request / query 语义、response、source text 与 prompt-local opaque label。必要 request / query 语义用于让工具结果在下一轮可解释、可复用，例如“查询 Coinbase 的股票代码”或“读取 ticker=COIN 的财报列表”；它不是 `TOOL_CALL_REQUESTED` 原事件、原始参数或内部治理字段的原样回放，也不得暴露 `tool_call_id`、EventLog id、payload ref、artifact ref、digest、wait id、awaiting / poll / cancel 状态或 Python 类型名。wait-resolution accepted result 与普通 accepted result 使用同一 self-explaining evidence contract；若缺少 request atom、semantic query 或 raw outcome，只能降级为业务中性 unavailable 文本或 fail closed，不能投影“工具结果已接受；原始工具响应不可用”这类无业务语义占位。`evidence_backed_facts` 只来自 accepted `CONTEXT_COMPACTED` 中通过 Host accept barrier 的 fact candidates，或后续明确设计的非 compact producer。这里的 fact 表示 Host-accepted claim 绑定到 accepted evidence，不表示 Host 证明现实世界 truth。

Session Summary Memory 负责当前 session 的 compact / rollup，服务长对话连续性，不替代事实。它只来自 accepted `CONTEXT_COMPACTED`；多次 compact 使用 rolling compacted view，latest accepted compacted view 是下一次 compact 的 previous accepted view。

Answer Anchor Memory 保存历史回答中可被用户后续指代的结构化轮廓，例如“三个风险”的第 1 / 2 / 3 点，用于支持“第二点展开”“刚才第三个风险”等追问。第一阶段不对 final answer 做 deterministic outline parser 或 LLM parser；Answer Anchor 只能来自 accepted compact output，或明确设计的非 prompt-conditioned producer。

Forward Intent Memory 保存待澄清问题、未完成任务、下一步任务状态等前瞻意图。它不是真实世界事实，也不直接驱动工具执行，只辅助下一轮 prompt 构造或澄清问题。第一阶段不对 prompt / final answer 做 intent parser，也不生成 hidden plan；Forward Intent 只能来自 accepted compact output，或明确设计的非 prompt-conditioned producer。

producer mapping 汇总如下；实现不得从旧字段或旧 renderer 反推新语义：

| 语义 | compact 前 | compact 成功后 | post-compact delta | compact failure fallback |
| --- | --- | --- | --- | --- |
| Trace Memory | selected recent window 中的 user input、assistant final answer、用户可见 Run 状态只作为 recent view 表达 | accepted `reference_continuity_items` 与 trace projection | latest compact cursor 之后的 eligible user / assistant / user-visible state material 继续进入 selected recent window | tier 1-3 accepted output 可生成 `reference_continuity_items`；tier 4-5 只渲染 fallback input，不物化 Trace snapshot item |
| Evidence / Fact Memory | selected recent window 中的 readable tool query / response / source text 只作为 recent view 表达 | 通过 accept barrier 的 `evidence_backed_facts` | latest compact cursor 之后的 readable accepted evidence material 继续进入 selected recent window | tier 1-3 accepted output 可生成 fact；tier 4-5 只渲染 fallback input 中仍被选中的 tool material，不生成 fact |
| Session Summary Memory | 空 | accepted `session_summary` roll-forward view | 不由 delta 直接生成 summary | tier 1-3 accepted output 可生成 summary；tier 4-5 为空，不生成 summary |
| Answer Anchor Memory | 空 | 通过 accept barrier 的 `answer_anchors` | 不对 final answer 做 compact 前 parser | tier 1-3 accepted output 可生成 anchor；tier 4-5 为空，不生成 anchor |
| Forward Intent Memory | 空 | 通过 accept barrier 的 `forward_intents` | 不对 prompt / final answer 做 intent parser | tier 1-3 accepted output 可生成 intent；tier 4-5 为空，不生成 intent |

### 24.6 Prompt Assembly

Prompt Assembly 的 section 顺序是固定 contract，不根据当前 prompt 做 recall、parser、reranker 或动态重排：

1. Host / Service system messages 与场景约束。
2. Session Summary Memory。
3. Evidence / Fact Memory。
4. Answer Anchor Memory。
5. Forward Intent Memory。
6. Trace Memory 的 reference continuity items。
7. selected recent window。
8. current input。
9. replay / retry / steer / resume guidance。
10. tool schema snapshot 与运行 policy。

Session Summary 只提供会话框架，不能替代 Evidence / Fact Memory；当 summary 与 fact 同时出现时，事实 claim 以 `evidence_backed_facts` 为准。Answer Anchor Memory 与 Forward Intent Memory 在 compact 后按 bounded policy 渲染非空 section，不由当前 prompt 触发。Reference continuity items 只服务局部指代解析，并放在 selected recent window 之前；selected recent window 是最接近 current input 的历史上下文。

渲染原则固定为：

```text
rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

如果没有 accepted compacted view，`latest_accepted_compacted_view` 为空，assembly 只从 `post_compact_delta_material` 选择 selected recent window 并追加 current input anchor。如果存在 accepted compacted view，assembly 先渲染五类 semantic memory 的非空 section，再渲染 compact boundary 之后的 selected recent window，最后渲染 current input anchor。无论 ordinary RunInput、compact input 还是 fallback RunInput，current input anchor 都是最终用户输入保护锚点，不得被吞掉、重复渲染成历史 trace material，或作为 compact candidate source 引用。

compact accepted 后的 ordinary RunInput 不得只等价于 `latest_accepted_compacted_view + current_input_anchor`。Host 仍必须按 `protected_recent_floor_policy` 从同一套 EventLog-backed material view 中选择 protected recent raw tail，并把 eligible user input、assistant final answer、accepted readable tool evidence 等 raw turn-group material 追加到 ordinary RunInput。该 raw tail 复用 `selected_recent_window_turn_floor`，不新增 ordinal-followup 专属 floor、recent-answer cap 或 prompt-pattern rule；选择、去重与 fallback material 必须使用同一套 material block / turn group 语义。若 memory selected recent window 已经渲染了同一 source refs 或同一文本 digest，ordinary protected raw tail 必须去重，避免同一 raw turn 重复进入 LLM context。

当第 N 轮已发生 accepted compact，随后第 N+m 轮再次 compact 且 `m < selected_recent_window_turn_floor` 时，floor 只保护第 N 轮 compact boundary 之后实际存在的 eligible turn groups。Host 不得为了“补满 floor”而重新展开第 N 轮 compact 已覆盖的旧 raw history，也不得把上一轮 `latest_accepted_compacted_view` 当作 raw recent turn。第 N+m 轮 compact 成功后的 ordinary RunInput 应包含新的 latest accepted compacted view、compact boundary 之后实际存在且未被 memory 去重的 protected recent raw tail，以及当前 input anchor。换言之，floor 是 post-compact delta 的保底，不是跨 compact boundary 的 raw-history replay 机制；旧历史只能通过 rolling compacted semantic view、audit / artifact 或后续显式 retrieval 能力表达。

ordinary path 不根据 token estimator 在 runtime 做字段级或逐 section silent truncation。各 section 必须在 projection / assembly 前通过配置化 item cap、char cap、selected recent window cap、selected recent window floor 与 per-semantic bounded working set 形成确定性上限；provider context length failure 由 Context Governance 的 reactive compact / fallback 收口。需要 floor 的 section 只固定两类：`selected_recent_window_turn_floor` 与 `evidence_fact_floor`。其它 section 默认只有 cap，没有 floor；`reference_continuity_item_floor = 0` 可以显式进入配置。fallback selected recent window caps 必须不小于 selected recent window floor 所需材料，并且不大于普通 selected recent window caps。

Prompt Assembly 渲染给 ordinary RunInput 时必须遵守 23 节 one-system-message hard contract。Conversation Memory 可以在内部维护 snapshot cursor、compact event ref、source refs、source label mapping digest、producer policy ref、projection checkpoint、diagnostic 与 item digest；但投影给 LLM 的 system envelope 和 selected recent window 只能包含业务可读内容、必要短来源说明和 prompt-local opaque label。ordinary RunInput 不得暴露 EventLog id、event sequence、payload ref、artifact ref、digest、cursor、policy ref、projection checkpoint、projector metadata、Attempt / execution ledger、tool_call_id、Python 类型名或 Host 内部治理术语。terminal answer continuity 投影只能输出回答文本本身，不得输出 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、EventLog id、digest、cursor 或 Host governance label。

Conversation Memory section header 必须使用 23 节 system envelope section table 中对应内容来源的固定 LLM-facing title；23 节表格是 section title 与映射关系的唯一真源，本文不重复硬编码完整 title 列表。selected recent window 中的 user / assistant material 保留原 role；当前 Engine message contract 不支持 ordinary RunInput historical evidence 使用 `tool` role，因此 selected recent evidence 若不能保留为 `user` / `assistant` role，则进入 system envelope，并按 23 节 evidence material 唯一归属规则路由，用业务可读 tool / query / response / source text 表达。该迁移不得展开 compact 覆盖范围内的旧 raw history，也不得把 fallback diagnostic 或 compact failure payload 渲染给模型。

### 24.7 测试与评测边界

Conversation Memory 的完整评测 deferred owner 为 GitHub Issue 80。当前设计要求 WU-CM-01 至少覆盖以下可断言场景：empty compacted view、non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection、provider context length fallback、invalid / missing / stale source label、schema invalid、provenance mismatch、partial candidate invalid、fallback 不生成高阶语义、compact roll-forward。

`utils/` Host public smoke 是 WU-CM-01 的初步验收标准，不等价于完整通过 GitHub Issue 80 的 benchmark。完整 eval harness 由 GitHub Issue 80 继续推进。

## 25. Context Governance

Context governance 是 Host 责任。Engine 不做 Host-side compact retry，也不理解 Host compaction attempt state machine。

Host 负责：

- provider-aware context budget policy。
- RunInputBuilder 输入层预算观测。
- proactive / reactive compact 触发。
- `ConversationCompactInputVNext` 构造。
- `ConversationCompactOutputVNext` accept barrier。
- compaction whole-candidate repair / retry 编排。
- failure closeout、tier 1-3 compact recovery fallback 与 tier 4-5 dispatch fallback。
- context overflow recovery dispatch。
- compact-related EventLog facts。
- compact event 与 Conversation Memory projection 输入。

Context Governance 是 orchestrator，不直接写 memory snapshot、tool trace、audit projection 或 outbox。它只能 append / request append compact-related canonical facts 或 projection_signal，并通过 typed ports 调用 compactor、budget estimator、RunInputBuilder 和 policy view。memory、trace、audit 等 projection 只从已提交 EventLog 追平。

第一版不实现 provider-specific token counting / provider tokenizer adapter。Context Governance 使用 conservative estimator、provider-aware configured limits 和 safety margin 做 proactive 判断；Engine context overflow event 是 reactive 收口信号。provider-specific tokenizer adapter 是后续精确能力。

`context_window_size` 是 Host context policy 的显式 typed input，由 Service / composition root 从 effective model config 读取并传入 typed policy。Host 不从 Engine 反查模型窗口，不从 per-run metadata 或 extra payload 中读取预算参数，也不把 provider overflow event 当作预算真源。Runner 返回的 usage 只能作为 post-call observation / diagnostics / policy calibration 输入，不能替代下一次 dispatch 前对当前 messages 的估算。

第一版 policy 默认值与阈值语义：

- `context_window_size` 必须为正整数。
- `soft_threshold_context_ratio` 与 `hard_threshold_context_ratio` 必须大于 0 且小于等于 1，且 soft ratio 不得大于 hard ratio。
- Host 内部按 ratio 计算 soft / hard threshold tokens。超过 soft threshold 时，Host 应先尝试 compact，而不是直接 dispatch。
- proactive path 在 dispatch 前使用估算输入决定是否触发 compact 或禁止 dispatch；proactive compact operation 的 bounded repair attempts 全部耗尽后仍超过 hard threshold 时 append `CONTEXT_COMPACTION_FAILED` 并按 failure policy 收口。
- reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源；它接受 quality 通过的 compact 结果，随后用真实 recovery dispatch / Engine overflow 闭环判断是否还需要下一次 reactive compact。
- 每个 Run 的 proactive trigger 第一版最多启动一个 compaction operation；reactive trigger 每次 Engine overflow 最多启动一个 operation，但同一 Run 可在 `max_reactive_compactions_per_run` 上限内多次 reactive compact，默认上限为 2。一个 operation 内可以包含 Host-owned bounded semantic repair attempts，但不得启动无界 compact loop。
- `max_compaction_attempts_per_operation` 由 Host context budget policy 显式给出，含第一次 proposal attempt、reactive material
  block pass proposal 与后续 whole-candidate semantic repair attempts，必须为正整数。它控制一次 Host compaction operation 内所有外部 LLM proposal
  调用总数；默认 packaged policy 为 5 次。代码 fallback 默认值与 execution profile 默认值必须保持一致，避免同一 Host 在不同装配路径下出现不同 compact retry 语义。该字段不控制 Engine provider / transport retry，也不允许 Service 提供 prompt、candidate builder 或 repair callback。
- 第一版只记录 usage observation 与 estimator calibration diagnostic，不根据 usage 自动动态调整 policy threshold，避免同一配置下的预算行为不可预测。

Context Governance 与 Conversation Memory 的关系必须保持单向。Conversation Memory 是 EventLog read model，向 ordinary RunInputBuilder 提供 `ConversationMemorySnapshotVNext`、snapshot cursor、policy digest 和 diagnostics。Context Governance 只负责读取同源 material view、估算预算、裁决 allow dispatch / compact / fallback / fail closed，并编排 bounded compaction operation；它不拥有 material 语义，不直接写 memory snapshot，不能让 session summary 替代 `evidence_backed_fact` 或 evidence anchor，也不能把 memory projection lag 当作 Run recovery。

Proactive compact 的 material view 必须由 EventLog-backed compact material builder 生成，而不是由 Context Governance 临时拼接。该 builder 的职责是从 latest accepted `CONTEXT_COMPACTED` 构造 `previous_compacted_view`，从 latest compact cursor 之后到当前 input 之前的 committed canonical facts 构造 post-compact delta material，并把当前 `USER_INPUT_ACCEPTED` 作为 current input anchor。Context Governance 只消费 builder 输出做预算估算、segment selection 与 compact operation 编排。

第一版 compactor 是 Host-owned typed port，可以调用 LLM compaction scene，但 LLM 只能提出 `ConversationCompactOutputVNext` 结构化候选；Host 负责校验、接受并写入 canonical compact event / artifact。compactor 输出 schema、candidate 字段和 source label 规则以第 24 章的 vNext compact I/O contract 为准。

Host 接受 compactor 输出后，`CONTEXT_COMPACTED` payload 必须记录 compact artifact ref、accepted attempt number、accepted candidate digest、prompt-local label mapping refs、source boundary refs、quality check result、budget after compact 与 projection signal。是否将 session summary、evidence-backed fact candidates、answer anchors、forward intents 或 reference continuity items materialize 到 Conversation Memory，由 memory projection policy 消费已提交 canonical facts 决定；Context Governance 不得直接写 memory snapshot、memory table 或 RunInputBuilder 私有 message 缓存。

Host-owned compactor proposal call 必须写入 runner-call manifest，并在 manifest 中提供 `CompactorRunnerCallIdentity`。该 identity 只标识“哪个 parent user Run 的哪个 compaction operation 发起了哪次 compactor LLM proposal input”，不表示新的 Host admitted user Run。字段固定为：

| field | type | required | semantics | validation rule |
| --- | --- | ---: | --- | --- |
| `parent_host_run_id` | `str` | yes | Host admitted user Run that triggered or is governed by compaction | must equal manifest `host_run_id` |
| `parent_session_id` | `str` | yes | parent Session | must equal manifest `session_id` |
| `compaction_operation_id` | `str` | yes | Host context governance operation id shared across proposal/repair attempts | required for every compactor call |
| `compactor_engine_run_id` | `str` | yes | self Engine/runner id for compactor proposal call, e.g. `context-compactor:*` | must not be treated as Host admitted user Run id |
| `compaction_attempt_number` | `int` | yes | proposal/repair attempt number within operation | positive and <= Host compaction policy max attempts |
| `compaction_request_digest` | `Digest` | yes | digest of immutable compaction request | must match compactor input projection |
| `compactor_input_projection_ref` | `HostInternalRef` | yes | artifact/descriptor for rendered compactor input data block | descriptor kind `compactor_input_projection` |

`CompactorRunnerCallIdentity` 只描述 proposal runner-call input 的 owner 与 input provenance，不保存 outcome ref。proposal manifest 在 runner call 前写入，不能回写 accepted / rejected outcome 字段，也不能重算 payload digest。`CONTEXT_COMPACTED` 继续拥有 accepted compact artifact refs、accepted attempt number、candidate digest、prompt-local label mapping refs、source boundary refs、quality check 与 budget after compact；accepted compact event 必须通过 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 反向引用 accepted proposal manifest。`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 必须通过 `proposal_manifest_ref` / `proposal_manifest_digest` 反向引用该 rejected attempt 的 proposal manifest。任何 rejected proposal content、中间 transient artifact 或 compactor input projection 都不能进入 Conversation Memory，也不能成为 accepted compacted view。

Compactor 与 retry / repair 的 owner 边界固定为：

- Runner/provider 层负责低层 transport retry：network、timeout、HTTP 429、HTTP 5xx、stream idle timeout 等由 Engine Runner 按 `RunnerSpec.max_retries`、`Retry-After` 与退避策略在一次 compactor proposal 调用内处理。该层 retry 不拥有 Host governance，不 append EventLog，不 emit HostEvent，只通过 RunnerEvent / log / attempt summary 进入 Host diagnostic。
- `LLMContextCompactor` 是 Host-owned 单次 proposal executor。它把 immutable `CompactionRequest`、Service 从 `compactor_baseline.scene_id` 指向的 scene 装配后传入的 system prompt / `AgentPolicy`、Service 从 `compactor_baseline.user_prompt_template_path` 指向的 prompt asset 读取后传入的 user prompt template，以及 Host lifecycle cancellation token 映射为一次 strict JSON proposal，并返回 typed candidate 或 typed failure；它不决定是否重试、不更新 Run / Attempt、不写 EventLog、不写 artifact、不做 memory projection，也不得自行构造不可取消 token。Host 只把 request 渲染为 typed data block 并替换 user template 中的 compaction request 占位符，不从 config 读取 prompt asset。
- Host Context Governance 拥有 semantic repair / retry：runner timeout、非 final outcome、`finish_reason=length`、空文本、非 JSON、top-level 非 object、缺必填 key、字段类型 / 值非法、未知 source label、provenance mismatch、source boundary violation、quality check reject、compact 后仍超过 hard threshold 等，都由 Host compaction operation 决定是否发起 bounded repair attempt。repair attempt 是 whole-candidate re-proposal：可以向 LLM 提供 Host-neutral 的失败类别 / validation issue 摘要，但每次必须重新产出完整 candidate；Host 不要求 LLM 返回 repair patch，不合并旧 proposal 的 valid fields 与新 patch，也不 partial materialize rejected candidate。repair attempt 必须复用同一个 immutable compaction request、同一套 Host-owned scene、同一 durable operation id，并在每次外部 LLM call 前后 recheck Run / Attempt / Session / cursor state。
- 每个 semantic proposal attempt 必须创建新的 Host-private linked cancellation child。child 只拥有当前 provider attempt 的 timeout；parent 继续拥有 Run / reactive operation 生命周期，且 parent reason / requested-at 始终优先。timeout 不得写 parent，也不得把 writable cancellation 加入 Engine public `CancellationToken` 观察协议；repair / retry 必须使用新的 child。
- stale / cancelled / session closed / execution replaced / cursor mismatch 不是可 repair 错误；Host 必须丢弃 stale proposal，不写 `CONTEXT_COMPACTED`。proactive compaction 在 worker 启动前没有 active worker token，必须使用 durable Run 状态观察 token；reactive compaction 必须复用 Engine envelope 中的 run-local cancellation token。prepared proposal 在 runner-call manifest commit 后、provider call 前必须用同一个 attempt token 再检查一次；该检查可读取 durable snapshot，但不得跨 provider await 持有 Host transaction。
- retry budget 耗尽后只允许写一个最终 `CONTEXT_COMPACTION_FAILED`，不能让 Service replay，不能让 Engine retry Host governance，也不能无限 compact。

Context Governance fallback 是同一套 `assemble(...)` material 语义下的分级状态机，不是另一套 memory 逻辑：

```text
tier 0 normal:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      normal_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    ordinary RunInput or compact input according to Context Governance decision

tier 1 compact recovery with tighter recent window:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 2 compact recovery with section-aware compacted view degrade:
  rendered_context =
    assemble(
      degraded latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 3 compact recovery delta-only:
  rendered_context =
    assemble(
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 4 dispatch fallback floor-only:
  rendered_context =
    assemble(
      protected_recent_turn_floor,
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED

tier 5 dispatch fallback current-input-only:
  rendered_context =
    assemble(
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED
```

Tier 1-3 是 compact recovery fallback：它们对同一套 material 用更保守的 selected recent window、section-aware compacted view degrade 或 delta-only 视图重新构造 compact input，并继续送 LLM compactor。tier 1-3 的 accepted output 可以提交 `CONTEXT_COMPACTED`，随后由 Conversation Memory projection 生成五类 Session Semantic Memory。tier 4-5 是 compact recovery 全失败后的 dispatch fallback：它们不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact，不 materialize memory snapshot，不生成 Session Summary、Answer Anchor、Forward Intent、reference continuity item 或 `evidence_backed_fact`；它们只影响本次 RunInput rendering，并且必须有 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 痕迹，不能静默发生。

Section-aware compacted view degrade 是 deterministic keep / drop 规则，不是新的 compact、summary 或 LLM 修复。保留优先级固定为：`evidence_fact_memory.evidence_backed_facts`、`trace_memory.reference_continuity_items`、`answer_anchor_memory.anchors`、`forward_intent_memory.intents`、`session_summary_memory.summary_text`。允许动作只有保留完整 semantic section、丢弃完整 semantic section，或在 section 内按确定性顺序保留 / 丢弃完整 semantic item。section 内 item 的保留 / 丢弃顺序必须由设计固定，不得由实施代码临时判断重要 / 不重要；本文只固定设计原则：排序依据必须业务可解释、稳定、可在同一 input cursor、material source cursor 与 policy 下确定性复现。后续 code-generation-ready plan 必须基于该原则选择稳定排序字段和排序方向，并确保 ordinary / compact / fallback 路径复用同一规则。degrade 禁止动作列表固定为：禁止截断 semantic item text；禁止重新 summary 或改写 summary；禁止改写 fact、answer anchor、forward intent 或 reference continuity item；禁止临时生成新的 compacted view；禁止让 fallback 产生新的 Session Semantic Memory。tier 4 的 `protected_recent_turn_floor` 使用 `host_run_id` turn group 保护最近 N 个 Host admitted user Run；如果 floor-only 仍超过 hard threshold，进入 tier 5；如果 current-input-only 仍无法合法 dispatch，必须 fail closed。

Fallback fail closed 条件必须集中收窄为真正不可恢复，或继续 dispatch 会破坏 Host 治理 / 事实边界的场景：current input anchor 本身超过 hard context budget；durable EventLog、payload 或 artifact 损坏，导致 Host 无法构造可信 LLM-facing 输入；selected material provenance 不一致，继续 dispatch 会污染事实边界；cancellation、session closed 或当前 Run state 已不允许继续执行。其它可恢复的 compaction proposal 质量问题、schema 问题、预算问题或 provider overflow，应先按 bounded repair、tier 1-3 compact recovery fallback、tier 4/5 dispatch fallback 或 failure policy 收口，不能绕过上述 hard stop 边界静默 dispatch。

Compaction operation 的 durable 语义固定为：

```text
CONTEXT_COMPACTION_REQUESTED(operation_id, trigger_source, budget snapshot, input cursor)
  -> attempt 1: LLM proposal outside write transaction
  -> Host quality / budget gate
  -> optional CONTEXT_COMPACTION_ATTEMPT_REJECTED(attempt_no, category, diagnostic refs)
  -> optional bounded whole-candidate repair attempt N
  -> CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
```

`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 是 Host governance diagnostic canonical fact，用于回答尝试次数、失败类别、是否 exhaust budget 和最终接受的是哪次 attempt。内部 EventLog 可以在 effective execution canonical fact 中保存 resolved provider headers / API key，但 compact request、attempt rejection diagnostic、artifact、Tool Trace、audit、HostEvent、memory / evidence、LLM-facing material 与日志都不得包含这些 secret 明文。完整 raw prompt、完整 provider payload、大 raw candidate、provider error body 或 repair prompt 如需保留，必须写受控 artifact / diagnostic ref，并在进入任何 public、LLM-facing、audit、trace 或 log projection 前由其 source owner 做敏感信息过滤与有界化。

HostEvent 暴露粒度必须比 EventLog 克制：`CONTEXT_COMPACTION_REQUESTED`、最终 `CONTEXT_COMPACTED`、最终 `CONTEXT_COMPACTION_FAILED` 应作为 Service-facing HostEvent 可观察；Host-level repair attempt rejected / retry scheduled 可以作为 typed diagnostic/progress HostEvent 暴露，但不得把每一次 Engine runner HTTP retry 变成 public HostEvent。低层 provider retry 只进入 runner log / aggregated diagnostics。

Compaction request 的输入边界固定为 `ConversationCompactInputVNext`，而不是从 Session 起点重放 EventLog ledger。一次 compactor run 的 messages 只能由 compactor system prompt 和一个 user material data block 组成；data block 是 Host 对 latest accepted compacted view、post-compact delta material 与 current input anchor 的去重、分段、可读投影，不承载 Host 内部账本 dump。

compact material selection 必须满足：

- proactive path 的目标是压缩旧 prefix，为当前 Run dispatch 腾出预算；current input anchor 与 protected recent floor 必须保留。
- reactive path 来自被冻结的 overflow ordinary input material list，优先压缩 older prefix；current input anchor 与 protected recent floor 必须保留到 recovery dispatch。
- selection 的候选集合是 `post_compact_delta_material`，不从 `latest_accepted_compacted_view` 中重新选择 raw recent window；fallback 与 ordinary selected recent window 复用同一个 recent-window selection 语义，只替换 fallback caps / tier。
- selection 按完整 material block 与 budget 压力裁剪，不按 raw item、固定轮数或字段字符数裁剪；一轮中包含的长 tool result 可以单独形成 evidence material block 或 evidence-block 内部分段。
- 给定 input cursor、material source cursor、policy 与 ordinary input material list，selection 必须确定性输出本次进入 compact input 的 block ids，供 tests、trace 与 audit 解释。
- 已被 latest accepted compacted view 代表的旧 raw turns / old tool results 不应在下一次 compact 中重新展开。
- selection 输出的 block id / provenance 必须从 selection 到 rendering 全程同源；LLM-facing material 缩小时只能 whole-block keep-drop、section-aware keep-drop、chunking with provenance 或 fail closed，不能用字段级 silent truncation 或 lossy preview 冒充完整 material。

material data block 的 section 映射必须一对一，不允许同一 canonical content 同时进入两个 LLM-facing section：

- `previous_compacted_view` 只来自 latest accepted compacted view 的业务可读 projection。
- `current_input_anchor` 来自当前 `USER_INPUT_ACCEPTED` 的 bounded anchor；同一 current user payload 不得再作为 trace material 渲染，且该 anchor label 不得被 compact candidate 作为 source 引用。
- `trace_material` 渲染 user / assistant continuity 与用户可见 Run 状态；accepted tool result raw content 不在 trace section 中重复出现。
- `evidence_material` 渲染 accepted tool evidence block。raw evidence 内容来自 `TOOL_RESULT_ACCEPTED` canonical fact 所引用且 digest 校验通过的 Host payload / raw result descriptor；accepted evidence envelope 只提供 Host 内部 provenance mapping，不作为 lossy result preview 或事实内容容器。
- `answer_material` 渲染 assistant final answer / conclusion 的可读文本，用于 answer anchor candidate；它不得作为 evidence-backed fact 的 source。

`OpaqueEvidenceRef` 以及 accepted evidence envelope 的 `source_refs` / `locator_refs` 只拥有 Host 内部 provenance identity；其 `ref_kind`、`ref_id` 与 `digest` 不承诺业务可读语义。Host、Conversation Memory、RunInput、Compact 及其他 LLM-facing projection 不得用 kind 黑白名单、未知 kind 默认分支或 `kind:id` 拼接去猜测业务来源；仅当具体 Tool / Fins producer 通过显式 contract 直接提供任务所需、业务可读且自解释的来源语义时，该语义才能进入 LLM-facing source 文本，否则统一投影为来源不可用。Opaque ref 可以继续进入 EventLog、audit 与内部 provenance / diagnostic trace，但不得因此被包装成财报事实或业务来源。当前没有实际 producer 需要通用业务来源类型，因此本规则不要求预先新增 `BusinessSource` 抽象。

Compact material data block build 启动前必须校验 EventLog / payload / artifact source refs 与 digest 可读、可校验，并且 latest accepted compact boundary 与 post-compact delta boundary 一致。对 `TOOL_RESULT_ACCEPTED`，strict compact consumer 必须先通过 shared durable JSON resolver 解析 result payload，再把已校验 payload 交给 accepted-result 业务投影；不得让 read/display 用的 lenient projection 把 descriptor、SQLite row、artifact 或 canonical JSON corruption 降级为“没有 evidence”。它不得因为 Conversation Memory snapshot lag 而要求先追平 memory projection；如果 EventLog-backed material source 不完整、payload 损坏、artifact 缺失或 source boundary 不可校验，按 compaction failure / pre-dispatch failure 收口。这不是 Run crash recovery，不得把 Run 推入 `RECOVERING`。

Ordinary RunInput 的 memory section 仍依赖 Conversation Memory snapshot。若 ordinary dispatch 前 snapshot cursor 不能覆盖 required EventLog cursor，Host 必须执行 page-bounded memory projection catch-up / rebuild，直到达到 required cursor、确认当前已 idle，或遇到 projection failure；也可以在 policy 允许范围内做 inline delta repair。`memory_projection_catchup_batch_size` 与相关 page limit 只控制单批读取和单次 transaction 粒度，不是“最多追多少事件”的语义预算，不得作为 required catch-up / rebuild 的 correctness 停止条件。追到 idle 仍不能覆盖 required cursor，或 catch-up / rebuild / inline repair 失败时，必须产生结构化 diagnostic，并按 pre-dispatch failure / retry / defer 策略收口。这不是 Run crash recovery，不得把 Run 推入 `RECOVERING`。

Dispatch hot path 不得做无上限同步补账。after-commit / after-compact hook 尤其不能为了追平 required cursor 执行无界 catch-up / rebuild；它们只能不执行机会性 projection，或执行有显式页数上限、只改善后续读取延迟的 latency-only maintenance。latency-only maintenance 的页数上限不得被解释为 memory 已追平，也不得用于判定 required cursor 是否满足；ordinary dispatch 的 correctness 仍必须由 required catch-up / rebuild / inline repair 的目标 cursor、idle 或 failure 结果决定。

Host 必须同时维护 prompt-local label 到 canonical provenance 的内部映射，例如 `E1 -> TOOL_RESULT_ACCEPTED event -> TOOL_CALL_REQUESTED event -> payload / artifact / source locator refs`。compact material 接受 evidence 前必须要求 `tool_call_requested_event_ref` 存在、解析到 canonical `TOOL_CALL_REQUESTED`，并与 accepted result 的 tool call id / tool name identity 一致；ref 缺失、指向 result event、类型错误或 identity mismatch 均 fail closed，绝不能把 `TOOL_RESULT_ACCEPTED.event_id` 当作 call ref fallback。该映射用于 accept barrier、audit 与 rebuild，不作为 LLM 主要语义输入。compact material data block 不得包含 full EventLog range wrapper、裸 event id / payload ref / digest / cursor / policy / artifact descriptor 作为模型阅读主体，也不得重复渲染同一 current input、raw turn 或 raw tool result。当单条 accepted evidence 被 chunk 成 `E1.1`、`E1.2` 等子 label 时，Host proposal parser 可以把父 label `E1` 解析为同一 canonical evidence 的 shorthand；该 shorthand 只允许用于 evidence section，仍必须拒绝未知 label 或跨 section label。

proactive compact 的安全条件是：compactor material tokens 必须与触发 compact 的 ordinary input material 属于同一去重视图，
不得显著大于 ordinary run input material。Context Governance 必须按即将发送给 compactor 的真实 messages 估算 budget；若
proactive material data block 仍超过 hard budget，优先判定为 segment selection 或 material data block builder 错误，并通过 bounded
repair / failure policy 收口，不能盲打 provider。

reactive compact 来自 provider context overflow，不能把已经 overflow 的 ordinary messages 原样一次性交给 compactor。Host 必须冻结
overflowed ordinary input material list，优先压缩 older prefix，保留 selected recent window 与 current input anchor；若完整 material
list 仍超过 compactor budget，应按 compact material block 分段多 pass 压缩。分段单位是 trace block、evidence block、summary block、
answer block 与 current input anchor，而不是固定轮数。若单个 evidence block 自身超过 compactor budget，必须在同一
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
  -> if compact failed and policy allows dispatch fallback: build tier 4/5 fallback input view and re-estimate
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
  -> if compact failed and policy allows dispatch fallback: build tier 4/5 fallback input view and re-estimate
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
- proactive compact failure 在 dispatch 前先完成 tier 1-3 compact recovery fallback；若仍失败且 policy 允许 dispatch fallback，再尝试 tier 4 floor-only / tier 5 current-input-only。tier 4/5 fallback 预算通过时允许创建 Attempt，但不得写 `CONTEXT_COMPACTED` 或 memory projection。fallback 仍超预算或 policy 不允许 fallback 时，Run 按 failure policy 收口，后续引入 `REJECTED` 后应归入 governance rejection，不得进入 `RECOVERING`。
- reactive compact failure 发生时当前 Attempt 已按 policy 关闭；Host 可按 policy 完成 tier 1-3 compact recovery fallback，仍失败后再尝试 tier 4/5 dispatch fallback，并在 fallback 预算通过时创建新的 recovery Attempt。fallback 仍超预算或 policy 不允许 fallback 时，Run 进入 `FAILED`。`LOST` 只属于 Phase 11 recovery / positive orphan proof owner，P10 不得用 compact failure 伪造 `LOST`。
- `CONTEXT_COMPACTION_REQUESTED` payload 至少记录 operation id、trigger source、provider / runner error refs、provider request id、budget snapshot refs、input snapshot cursor、retry / repair budget snapshot 和 reason。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 至少记录 operation id、attempt number、failure category、whether repairable、runner attempt summary refs、quality / parse / budget diagnostic refs 和 next policy decision。
- `CONTEXT_COMPACTED` payload 至少记录 operation id、accepted attempt number、compact artifact ref、accepted candidate digest、prompt-local label mapping refs、source boundary refs、accepted evidence mapping refs、quality check result、budget after compact 与 projection signal。
- `CONTEXT_COMPACTION_FAILED` payload 至少记录 operation id、failure reason、policy decision、whether retryable、attempt count、retry / repair budget exhausted 标记和 diagnostic refs；若 policy decision 采用 tier 4/5 dispatch fallback，还必须记录 fallback tier、fallback input window / digest、fallback budget result，以及 fallback 后是 dispatch 还是 fail closed。

compact 不变量：

- compact 不能改写历史 EventLog facts，也不能让 summary 替代 evidence anchor。
- compacted snapshot / summary 是 read model 或 input artifact；是否进入 memory projection 必须由 memory policy 决定。
- RunInputBuilder 必须从 `USER_INPUT_ACCEPTED`、canonical facts、memory snapshot 和 compacted artifacts 重建完整 messages；不能复用失败 Attempt 的 provider request payload。
- tier 4/5 dispatch fallback 只能影响本次 RunInputBuilder 输入选择，不得改写 EventLog 历史事实，不得提交 `CONTEXT_COMPACTED`，不得 materialize memory snapshot；但它必须有 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 痕迹，不能静默发生。
- 新 Attempt 必须有新的 `attempt_id` / `execution_id`；旧 Attempt 不 takeover、不 resume。
- compact 必须有 policy 上限。proactive operation 内 bounded repair attempts 和 tier 1-3 compact recovery fallback 耗尽后，Host 必须 append `CONTEXT_COMPACTION_FAILED`；若 tier 4/5 dispatch fallback 预算通过，可继续 dispatch，否则按 failure policy 收口。reactive path 中 compact 后若真实 recovery dispatch 再次触发 Engine overflow，可在 `max_reactive_compactions_per_run` 范围内追加下一次 reactive compact；超过上限后 append `CONTEXT_COMPACTION_FAILED`，可按 policy 尝试 tier 4/5 dispatch fallback，仍失败则让 Run 进入 `FAILED`。不得进入 `LOST`，不得无限 compact retry。
- tool trace / audit 必须能解释哪些内容被保留、压缩、丢弃，以及为什么这样做。

参数默认值由 memory / context policy provider 定义。设计固定治理范围，policy 固定优先级和默认值。

provider tokenizer adapter 是 Host 预算治理的后续精确能力，不进入第一版。第一版 proactive path 使用保守 token estimator，阈值必须留出 safety margin；provider 返回 context length exceeded 仍是 reactive fallback，不是 proactive compact 触发机制。reactive path 不依赖估算证明 compact 后一定可 dispatch，而是通过最多两次真实 recovery dispatch 闭环收敛，超过上限后 fail closed。

## 26. Evidence / Retrieval / Long-term Memory

长期 memory 不在第一版实现。第一版只做 session memory 与当前 run 的 context governance，但设计不得封死长期记忆。

跨多年弱信号归因靠证据链和 query-time retrieval，不靠无限扩大 session memory。

边界：

- Host 提供 evidence anchor、provenance、事实候选 / 验证标记等中立骨架。
- 原始网页新闻、公告、研报摘录、财报 chunk、source metadata、业务 event type、company / product / business-line ref 由业务工具和财报领域仓储管理。
- 早期 signal 进入待验证 candidate，不因 summary 或 memory 收录变成 verified attribution。
- 后续分析通过 query-time retrieval 召回 signal anchors、evidence chunks 与待验证 candidates。
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

同一次 startup recovery scan 必须在开始时冻结 `policy.now`，并从 durable Run governance index 取得固定 upper watermark。扫描顺序固定为 `(accepted_event_sequence, run_id)` keyset 全序；同 sequence 由 `run_id` 稳定打破平局，不允许使用 offset。scanner 在 durable actor 独占连接上按有界 page 执行，每个 page 是独立 write transaction；默认 batch size 为 64。只有当前 page commit 成功后才能投递该 page 的 matching dispatch / queue-promotion wake；rollback page 不得 wake，先前已提交 page 不得因后续失败回滚。失败后的完整重跑只能依赖 durable CAS / idempotency 收敛，不得依赖内存 cursor。

opener 在 execution health 仍为 `STARTING` 时完成全部 recovery pages 与 commit 后 wake；任一 batch、cursor invariant 或 wake bridge 失败时不得进入 `READY`。固定 watermark 之后新接受、且 keyset 高于该 watermark 的 Run 留给下一轮 scan，避免启动扫描因并发 admission 无限延长。

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
- `CANCELLING` 且存在已接受 active cancel facts：defer 给 accepted-cancel watchdog，不 append `ATTEMPT_LOST` / `RUN_LOST`。
- `RUNNING` / `CANCELLING` 且具备 positive orphan proof：通过 CAS 将旧 Attempt -> `LOST`；Run 按 policy 与事实完整性进入 `RECOVERING` 或 `LOST`。带 accepted cancel facts 的 `CANCELLING` Run 先由 watchdog 处理，不走该 LOST 分支。
- `RUNNING` / `CANCELLING` 且只能判断 owner heartbeat stale，但无法证明 owner 进程已死：记录 suspect / diagnostic，跳过 recovery。
- `RECOVERING`：继续按 recovery policy 创建新 Attempt，或因超过上限进入 `LOST`。

Phase 11 第一版 startup recovery policy：

- `ACCEPTED`、`QUEUED` 与 `WAITING` 都不是 orphan Attempt，不得因 Host startup scan 被推进到 `RECOVERING`。
- `RUNNING` / `CANCELLING` 的旧 Attempt 只有在 positive orphan proof 成立后才能写入 `ATTEMPT_LOST`；随后如果用户输入、payload descriptor、tool fact reuse policy、memory / compact input refs 等必要 canonical facts 足以重建 messages，则 Run 进入 `RECOVERING`，否则进入 `LOST`。startup 先执行一次 watchdog tick，再由 scanner defer 剩余 accepted-cancel `CANCELLING` Run，避免正常 close/reopen 把用户已取消的 Run 标为 `LOST`。
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
