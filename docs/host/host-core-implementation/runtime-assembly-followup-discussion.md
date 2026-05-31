# Runtime Assembly 后续修正讨论记录

## 文档职责

本文档只记录 Phase 12 runtime assembly 在 smoke 装配验证中暴露出的后续设计修正项，供全部讨论结束后统一进入 `$init-agents` / `$gateflow` 修改闭环。

本文档不是设计真源，不替代 `docs/host/design.md`；最终裁决若改变稳定设计，必须写回设计真源与总控文档。

## 已裁决修正项

### 1. catalog record id 规则

当前现象：

- 多个 config catalog 中 record id 同时出现在 map key 与 record 内部字段，例如 `runtimes.local.runtime_id = "local"`、`models.deepseek-chat.model_id = "deepseek-chat"`、`profiles.ordinary.profile_id = "ordinary"`。

问题判断：

- 如果内部 id 只是重复 map key，它不会提供额外语义，反而引入冗余和 key / value 不一致的校验成本。
- ConfigLoader 可以用 map key 作为 record id，并在 typed config dataclass 中注入 id 字段供代码使用；JSON schema 不需要重复写 id。
- `extends` 引用同一 catalog 的 map key 即可。

已裁决方向：

- catalog record id 统一由 map key 提供。
- JSON record 内删除重复 id 字段，包括但不限于 `runtime_id`、`host_runtime_id`、`model_id`、`profile_id`、`execution_profile_id`。
- typed config dataclass 如需 id 字段，由 ConfigLoader 从 map key 注入，不从 JSON 读取。
- `extends` 继续引用同 catalog 的 map key。
- ConfigLoader validation 不再接受内部重复 id 字段，避免新旧 schema 并存。

### 2. override 白名单原则

当前现象：

- P12 runtime assembly 涉及多层覆盖：UI / Run override、scene manifest、execution profile、model runtime hints、code default。
- 如果任一层允许 raw dict 或任意字段透传，容易绕过 typed contract、制造字段拼写错误、旧字段残留或状态机参数被非预期覆盖。

问题判断：

- override 是必要能力，但必须是 typed allowlist，不得成为 extra payload。
- scene 需要覆盖部分 AgentPolicy 字段是合理需求，例如 WeChat service 为了较快响应，常会把 `max_iterations` 设得比普通 Chat 更低。
- 这类需求应由 scene manifest 直接声明 typed `agent_policy` override，而不是通过 `agent_hints` 间接依赖 execution config。

已裁决方向：

- 任何一级 override 都只允许覆盖白名单字段。
- 禁止 raw dict / extra payload / 任意 key 透传进入 Host / Engine public contracts。
- ConfigLoader、ScenePrepare、adapter helper 与 smoke 都必须 fail fast 拒绝未知 override 字段。
- scene manifest 如需特殊 AgentPolicy，使用 typed `agent_policy` override，并只允许覆盖白名单字段。
- AgentPolicy scene override 白名单对齐当前 public `AgentPolicy` 字段：`max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt`、`max_consecutive_failed_tool_batches`。
- override 优先级保持：UI / Run override > scene typed override > execution profile baseline > code default。

### 3. runtime config / prompt asset location resolver

当前现象：

- `host_runtime.json` 中 `prompt_asset_root` / `scene_manifest_root` 默认指向 `workspace/config/prompts` 与 `workspace/config/prompts/manifests`。
- 仓库内可直接运行的默认 scene assets 位于 `dayu/config/prompts`。
- runtime assembly smoke 为了跑通，只能在配置路径不存在时回退到包内默认路径。

问题判断：

- 生产环境默认从 `workspace/config` 读取覆盖配置是合理的；当 `workspace/config` 不存在时，应视为没有 workspace overlay。
- `ConfigLoader` 不应知道“workspace/config 不存在则 fallback 到 dayu/config”的策略；它只应接收 `workspace_config_dir: Path | None`，其中 `None` 的含义是无 overlay、只读 package default。
- `ScenePrepare` 也不应知道默认路径策略；它只解释调用方显式传入的 `scene_manifest_root` 与 `prompt_asset_root`。
- 为避免每个 Service 重复实现路径选择，可以在 `dayu.runtime` 增加层中立 location resolver。resolver 只做路径选择，不解释 schema、不拼 Host input、不依赖 Host / Engine / Service / Fins。

已裁决方向：

- 新增 runtime location resolver，输出 `config_overlay_dir = workspace/config if exists else None`，以及 `prompt_asset_root` / `scene_manifest_root` 的实际可用路径；Service 调用 resolver 后再调用 `ConfigLoader.load(config_overlay_dir)` 与 `ScenePrepare.prepare(...)`。
- resolver 把 fallback 策略放在层中立 runtime helper，而不是塞进 `ConfigLoader` 或 `ScenePrepare`。
- resolver 对 ConfigLoader 的正确输出是 `None`，不是把 `dayu/config` 作为 `workspace_config_dir` 传入；这样不会把 package default 伪装成 workspace overlay。

### 4. runtime lane config 拆分

当前现象：

- `host_runtime.json` 的 `lane.default_lane_name`、`lane.db_path` 与 `lane.lanes` 混在 Host runtime 配置中。
- `dayu.runtime.lane` 是层中立 capacity primitive，可以用于 LLM provider 调用、SEC filings 下载、解析任务、CPU / IO worker 等多类资源容量保护，不是 Host 专属配置。
- `default_lane_name` 这个字段名容易被理解成“所有 runtime lanes 的默认 lane”，但 Host 实际只需要声明“Host 本地 Engine 执行使用哪一个 lane”。

问题判断：

- lane catalog 与 lane coordinator DB 属于 `dayu.runtime` 通用资源配置，不应放在 Host 专属 runtime 配置中。
- Host runtime 配置只应引用 Host 执行所需的 lane 名称，不应拥有整个 lane catalog。
- `default_lane_name` 命名不贴切；当存在 `llm_api`、`sec_download` 等多个 lane 时，该字段没有表达它服务于 Host local Engine execution。

已裁决方向：

- 新增独立 runtime lane 配置文件，例如 `runtime_lanes.json`。
- `runtime_lanes.json` 拥有 runtime lane coordinator 与 lane catalog，例如 runtime lane SQLite DB 路径、`llm_api` / `sec_download` 等 lane 的 `capacity`、`claim_ttl_seconds`、`heartbeat_interval_seconds`。
- `host_runtime.json` 不再内联 lane catalog，只保留 Host 执行 lane 引用字段，字段名改为 `host_execution_lane_name`。
- `host_execution_lane_name` 必须引用 `runtime_lanes.json.lanes` 中存在的 key。
- Service / composition root 负责同时读取 `host_runtime.json` 与 `runtime_lanes.json`，用 `host_execution_lane_name` 从 lane catalog 中取出具体 lane 配置，再映射到 `OpenHostOptions.lane_name`、`lane_capacity`、`lane_claim_ttl_seconds`、`lane_heartbeat_interval_seconds` 与 `lane_db_path`。
- 不修改 Host 公开接口；`OpenHostOptions` 仍接收现有 lane typed fields。

### 5. host runtime profile selector 命名

当前现象：

- `host_runtime.json` 顶层字段为 `default_runtime_id`。
- 该字段用于在 `runtimes` 中选择默认 Host runtime profile，例如当前默认选择 `runtimes.local`。
- 该字段不是 Run ID、不是 Host instance ID，也不是通用 runtime id。

问题判断：

- `default_runtime_id` 命名偏泛，容易和 execution profile、runtime lane、Host instance runtime state 混淆。
- 该字段真实语义是“默认 Host runtime profile id”。

已裁决方向：

- 将 `default_runtime_id` 改名为 `default_host_runtime_id`。
- `runtimes` 保持作为 Host runtime profiles catalog；单项中不再保留 `runtime_id` / `host_runtime_id` 这类重复 id 字段，record id 由 map key 提供。
- Service / composition root 使用 `default_host_runtime_id` 从 `runtimes` 选择 Host runtime profile，再装配 `OpenHostOptions`。

### 6. host worker backend 命名

当前现象：

- `host_runtime.json` 中使用 `worker_factory_kind` 表达 worker factory 选择，当前值为 `"local"`。
- 该字段最终由 Service / composition root 解释，并映射为 `OpenHostOptions.worker_factory`。
- `ConfigLoader` 不应根据该字段创建 worker factory，也不应 import Host / Engine。

问题判断：

- `worker_factory_kind` 是代码实现视角，暴露了 factory 这个装配细节。
- 配置层更应表达 Host 执行后端选择，而不是具体 factory 实现类型。
- 未来实现 `RemoteWorkerProxy` / `RemoteWorkerStub` 后，该字段需要自然支持 `"remote"` 这类 worker backend。

已裁决方向：

- 将 `worker_factory_kind` 改名为 `worker_backend`。
- 当前默认值为 `"local"`；未来可扩展 `"remote"`。
- `"local"` 表示 Service 装配本地 `LocalEngineWorkerFactory`，Host 在本机启动 Engine worker。
- `"remote"` 表示 Service 装配 remote worker factory / proxy，通过 RemoteWorkerProxy / RemoteWorkerStub 把 Attempt 交给远端执行。
- Host 公开接口不变，仍由 Service / composition root 把 `worker_backend` 映射为 `OpenHostOptions.worker_factory`。
- `ConfigLoader` 只读取和校验配置值，不负责创建 worker factory。

### 7. execution profile selector 命名

当前现象：

- `execution_profiles.json` 顶层字段为 `default_profile_id`。
- 该字段用于在 `profiles` 中选择默认 execution profile，例如当前默认选择 `profiles.ordinary`。
- `profiles.ordinary` 再用于装配 ordinary run baseline、compactor baseline、context budget、memory projection、truncation 等执行配置。

问题判断：

- `default_profile_id` 和 `profiles` 命名过于泛化，离开文件上下文后无法表达它们选择的是 execution profile。
- schema 中同时存在 host runtime profile、execution profile、runner options profile、agent policy profile、model catalog 等多类 profile / catalog；顶层 selector 应自解释。
- 既然 `host_runtime.json.default_runtime_id` 已裁决改为 `default_host_runtime_id`，execution profile 也应采用同类命名规则。

已裁决方向：

- 将 `default_profile_id` 改名为 `default_execution_profile_id`。
- 将顶层 `profiles` 改名为 `execution_profiles`。
- 单项中不再保留 `profile_id` / `execution_profile_id` 这类重复 id 字段，record id 由 map key 提供。
- 默认 execution profile id 从 `"ordinary"` 改为 `"standard"`，避免 profile id 与普通 Run baseline 字段同名。
- profile 内部的 `ordinary` 字段改名为 `run_baseline`，表达普通 Run 的 execution baseline。
- profile 内部的 `compactor` 字段改名为 `compactor_baseline`，表达 Host-owned compactor 的 execution baseline。
- 新 schema 形状为 `execution_profiles.standard.run_baseline` 与 `execution_profiles.standard.compactor_baseline`，不再出现 `profiles.ordinary.ordinary`。
- Service / composition root 使用 `default_execution_profile_id` 从 `execution_profiles` 选择 execution profile，再装配 ordinary / compactor execution baseline 和治理策略。

### 8. context budget policy 装配边界

当前现象：

- `execution_profiles.json` 中的 `context_budget` 当前包含 `max_context_tokens`、`reserved_response_tokens`、`compaction_trigger_tokens` 三个绝对 token 字段。
- `models.json` 中的 model record 已有 `context_window_tokens`，它才是模型上下文窗口能力事实。
- `RunnerCallOptions.max_tokens` / runner options profile 表达本次调用输出上限，可作为 Host context governance 的输出预留来源。

问题判断：

- `max_context_tokens` 是模型/provider 能力事实，不应放在 execution profile；否则切换 provider / model 时必须同步改 execution profile，能力真源会漂移。
- `reserved_response_tokens` / `reserved_output_tokens` 不应写死在 execution profile；不同 provider 未必都有稳定、同名、同语义的 `max_tokens` 参数，因此也不应把它强绑定为 config 派生来源。
- `minimum_protection_tokens` 同样不适合暴露给普通配置作者；它是 Host 内部预算模型参数，很难回答“写多少合适”。
- `compaction_trigger_tokens` 是基于 context window 与治理策略计算出的阈值结果，不应作为跨模型固定绝对值配置。
- 旧项目以 `budget_soft_limit_ratio` / `budget_hard_limit_ratio` 这类比例表达预算策略，能随模型窗口自动伸缩；该方向更适合作为公共配置和 Host public contract。
- 现有 Host typed `ContextBudgetPolicy` 暴露 `reserved_output_tokens`、`minimum_protection_tokens` 和可选 `hard_threshold_tokens`，不再是最佳公共契约；根修复应修改 Host public contract，而不是让 Service / config adapter 伪造这些内部参数。

已裁决方向：

- 将 `context_budget` 改名为 `context_budget_policy`。
- `context_budget_policy` 直接对齐新的 Host ratio-first `ContextBudgetPolicy` public contract，只表达治理策略，不直接表达模型能力或本次调用输出预算。
- 从 execution profile 中移除 `max_context_tokens`、`reserved_response_tokens`、`compaction_trigger_tokens`。
- Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `ContextBudgetPolicy.context_window_size`，并直接放入 Host public policy typed value。
- 修改 Host public `ContextBudgetPolicy`，从 `reserved_output_tokens` / `minimum_protection_tokens` / `hard_threshold_tokens` 模型改为 ratio-first 模型。
- 新 Host public `ContextBudgetPolicy` 至少包含 `context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、`max_proactive_compactions_per_run`、`max_reactive_compactions_per_run`、`max_compaction_attempts_per_operation` 与 `policy_ref`。
- Host 内部根据 `context_window_size * soft_threshold_context_ratio` 与 `context_window_size * hard_threshold_context_ratio` 计算 soft / hard threshold tokens。
- `context_window_size` 必须作为 `ContextBudgetPolicy` 的直接字段参与 typed validation、policy digest、EventLog / diagnostic / artifact metadata；不得通过 callback、provider、profile lookup 或外部 execution context 隐式提供。
- `policy_ref` 保留为治理策略稳定引用，用于 EventLog、diagnostic payload 与 compact artifact metadata 审计；它不是配置路径或 Python class 名。默认配置应显式写入，例如 `context-budget:standard:v1`。
- `OpenHostOptions.context_budget_policy` 字段保留，但其接收的 `ContextBudgetPolicy` typed shape 会随 Host public contract 一起更新。
- runtime assembly / ConfigLoader / tests / README 需要随 Host public contract 迁移；按全新 schema 处理，不保留旧 `context_budget` 兼容读取。

### 9. memory projection policy schema 补齐

当前现象：

- `execution_profiles.json.memory_projection` 目前只有 `enabled`、`stable_layer_max_items`、`history_pool_max_items`。
- Host public `MemoryProjectionPolicy` 实际需要 `max_pinned_items`、`max_verified_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`max_raw_turn_size_units`、`history_pool_size_units`、`stable_layer_size_units`、`max_lag_events_for_inline_delta`、`max_delta_repair_events`。
- 当前 `stable_layer_max_items` / `history_pool_max_items` 命名与 Host typed contract 不一致；Host 使用的是 size units 预算，不是 item count。

问题判断：

- 当前 schema 不足以完整装配 `OpenHostOptions.memory_projection_policy`，只能走代码 default 或 smoke adapter 临时补值。
- `max_items` 命名会误导配置作者，以为这是条目数量；实际 Host stable layer / history pool 的关键预算是保守 size units。
- 固定 `stable_layer_size_units` / `history_pool_size_units` 不能在 128K、256K、1M 或更小 context window 下自适应；大窗口下过度保守，小窗口下可能挤占当前任务、工具结果和财报材料。
- P12 需要系统性对照 Host public contracts 检查 config schema 是否足够装配 `open_host(options)` 与 per-run typed input，不能只靠 smoke 中发现一个补一个。

已裁决方向：

- 将 `memory_projection` 改名为 `memory_projection_policy`。
- 修改 Host public `MemoryProjectionPolicy`，从固定 `stable_layer_size_units`、`history_pool_size_units`、`max_raw_turn_size_units` 改为 ratio / floor / cap 自适应预算模型。
- Service / composition root 从 effective model config 读取 `context_window_tokens`，作为 `MemoryProjectionPolicy.context_window_size`，并直接放入 Host public policy typed value。
- 新 Host public `MemoryProjectionPolicy` 至少包含 `context_window_size`、`max_pinned_items`、`max_verified_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、stable layer ratio/floor/cap、history pool ratio/floor/cap、raw turn ratio/floor/cap、`max_lag_events_for_inline_delta`、`max_delta_repair_events`。
- Host 内部根据 `context_window_size` 与 ratio / floor / cap 计算 effective stable layer、history pool 与 raw turn size units。
- `context_window_size` 必须作为 `MemoryProjectionPolicy` 的直接字段参与 typed validation、policy digest 与 snapshot digest 相关语义；不得通过 callback、provider、profile lookup 或外部 execution context 隐式提供。
- 删除 `memory_projection_policy.enabled`；policy 存在即表示装配 stateful memory projection。
- 单轮 / 非 conversation 场景的语义由 scene manifest 表达，例如旧项目 `conversation: false` 后续迁移为 scene 层语义。本次 P12 config 补丁先不处理 scene schema。
- 新增 P12 任务：逐项对照 Host public contracts，检查 `host_runtime.json`、`runtime_lanes.json`、`models.json`、`execution_profiles.json`、scene manifest 是否足够且正确装配 `open_host(options)` 与 per-run typed input；缺失、命名错误或边界错误的配置项必须统一裁决后迁移。

### 10. tool truncation policy schema 补齐

当前现象：

- `execution_profiles.json.truncation` 目前只有 `enabled`、`default_max_chars`、`fetch_more_tool_name`。
- 公共 `ToolTruncateSpec` 支持 `text_chars` / `text_lines` / `list_items` / `binary_bytes` 四种策略，limit key 分别为 `max_chars`、`max_lines`、`max_items`、`max_bytes`。
- `ToolTruncateSpec` 还包含 `target_field` / `field_path` 与 `ttl_seconds`。
- Host 当前 `fetch_more` 是预留 framework tool 名称 `FrameworkToolName.FETCH_MORE = "fetch_more"`，不是 execution profile 应暴露的可改名配置。

问题判断：

- 当前 schema 只覆盖字符截断，缺少 `default_max_lines`、`default_max_items`、`default_max_bytes` 对应能力。
- `strategy` 与 `target_field` / `field_path` 应由工具自己声明，因为每个工具最了解自己的返回结构；配置不应替工具决定“怎么截、截哪里”。
- 配置层应该只表达默认治理参数：各 truncation strategy 的默认 limit、默认 cursor TTL、是否启用 truncation manager / `fetch_more` 注入。
- 当前 `ToolTruncateSpec` enabled 时要求 `limits` 必须包含策略对应 key，这不支持“工具声明 strategy/target，limit 由 config default 补齐”的最佳分层。

已裁决方向：

- 将 `truncation` 改名为 `tool_truncation_policy`。
- `tool_truncation_policy` 只配置默认治理参数，不配置 per-tool strategy / target。
- schema 至少包含：

```json
{
  "enabled": true,
  "default_cursor_ttl_seconds": 600,
  "default_limits": {
    "text_chars": {"max_chars": 12000},
    "text_lines": {"max_lines": 400},
    "list_items": {"max_items": 200},
    "binary_bytes": {"max_bytes": 65536}
  }
}
```

- `fetch_more_tool_name` 从 config 中删除；framework tool 名称继续由 Host public `FrameworkToolName.FETCH_MORE` 固定。
- 工具声明负责提供 `ToolTruncateSpec.strategy`、`target_field` / `field_path` 与是否启用截断。
- 如果工具声明显式提供对应 limit，则使用工具声明值；如果工具声明启用截断但未提供 limit，则由 assembly 用 `tool_truncation_policy.default_limits[strategy]` 补齐。
- 如果工具声明未提供 `ttl_seconds`，则由 assembly 用 `default_cursor_ttl_seconds` 补齐。
- 如果 `tool_truncation_policy.enabled = false`，Service / composition root 不启用 truncation manager，也不注入 `fetch_more`。
- 修改 `ToolTruncateSpec` public contract，使其支持 limit 缺省后由 assembly 生成 effective truncate spec；具体实现可保持 `limits` mapping，但允许声明态为空，并在 effective bundle 阶段补齐。

### 11. runner option hint 分层重设计

当前现象：

- `execution_profiles.json` 同时包含 `runner_options_profiles` 与 `runner_hints`。
- `runner_options_profiles` 直接保存 `temperature`、`max_tokens`、`top_p`、`stream` 等 RunnerCallOptions 值。
- `runner_hints` 又可覆盖 `model_id`、`runner_options_profile_id`、`max_tokens`、`stream`、`temperature` 等字段。
- 旧项目 `llm_models.json` 在每个模型下提供 `runtime_hints.temperature_profiles`，同一个 hint id 在不同 provider / model 下映射到不同具体参数。

问题判断：

- `temperature`、`top_p` 等值具有明显 provider / model 差异，不应作为 execution profile 的全局具体值。
- `max_tokens` 不是所有 provider 都有稳定、同名、同语义的 API 参数，也不应作为 context governance 的预算来源。
- `runner_hints` 作为独立 override bag 会和 scene、model runtime hints、UI overrides 同时修改 RunnerCallOptions，边界不清。
- Host / Service 应支持默认 model，并允许每次 Run 切换 model；切换 model 时应保留当前语义 hint 档位，由新 model 自己解释该 hint 的具体 RunnerCallOptions。

已裁决方向：

- 删除 `execution_profiles.json.runner_options_profiles`。
- 删除 `execution_profiles.json.runner_hints`。
- `models.json.models[*].runtime_hints.runner_option_hints` 成为 provider/model-specific RunnerCallOptions hint 真源。
- `runner_option_hint_id` 是 semantic call style selector，语义接近 scene/task intent，例如 `interactive`、`overview`、`audit`、`decision`、`write`、`infer`、`conversation_compaction`。
- `execution_profiles.json` 只保存默认 `runner_option_hint_id`，不保存具体 `temperature` / `top_p` / `max_tokens` / `stream` 值。
- `run_baseline` 保存默认 `model_id` 与默认 `runner_option_hint_id`，例如 `interactive`。
- `compactor_baseline` 保存 compactor 专用 `model_id` 与 `runner_option_hint_id`，固定语义为 `conversation_compaction`。
- 每次 Run 可 override `model_id`；如果不 override `runner_option_hint_id`，则保持当前 hint 档位不变，并从新 model 的 `runtime_hints.runner_option_hints[hint_id]` 读取具体 RunnerCallOptions。
- effective model / hint 选择优先级：
  - `model_id`: UI / Run override > scene default > execution baseline default > code default。
  - `runner_option_hint_id`: UI / Run override > scene default > execution baseline default > code default。
- effective RunnerCallOptions 由 `models[effective_model_id].runtime_hints.runner_option_hints[effective_runner_option_hint_id]` 生成。
- `execution_profile.run_baseline.runner_option_hint_id` 必须存在于对应 model 的 `runtime_hints.runner_option_hints`。
- `execution_profile.compactor_baseline.runner_option_hint_id` 必须存在于对应 compactor model 的 `runtime_hints.runner_option_hints`；启用 compactor 时 `conversation_compaction` 必须存在。
- scene manifest 可以选择 `runner_option_hint_id`，但不直接保存 provider-specific runner option 值。

### 12. agent policy profile schema 对齐

当前现象：

- `execution_profiles.json.agent_policy_profiles` 当前字段包括 `max_iterations`、`continuation_attempts`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt`、`consecutive_failed_tool_batches`。
- Host / Engine public `AgentPolicy` 当前字段为 `max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt`、`max_consecutive_failed_tool_batches`。

问题判断：

- `max_iterations`、`tool_execution_timeout_seconds`、`continuation_prompt` 与 Host public contract 匹配。
- `continuation_attempts` 命名不匹配，应改为 `continuation_max_attempts`。
- `consecutive_failed_tool_batches` 命名不匹配，应改为 `max_consecutive_failed_tool_batches`。
- `allow_tool_calls` 缺失，但它是当前 `AgentPolicy` 必填字段。
- `fallback_mode` 与 `fallback_prompt` 已单独裁决需要修正。
- `agent_hints` 当前也是松散 override bag，且沿用了旧字段名；它会让 scene 间接覆盖 Agent loop 状态机参数，导致 scene 与 execution config 之间依赖过多。

已裁决方向：

- `agent_policy_profiles` 必须一比一对齐当前 Host / Engine public `AgentPolicy` typed shape。
- 将 `continuation_attempts` 改名为 `continuation_max_attempts`。
- 将 `consecutive_failed_tool_batches` 改名为 `max_consecutive_failed_tool_batches`。
- 增加必填 `allow_tool_calls`，默认 agent policy profile 为 `true`。
- `fallback_mode` 使用 `force_answer` / `raise_error`，默认 `force_answer`。
- `fallback_prompt` 使用已裁决文本：`请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。`
- 默认 profile id 从 `default-agent` 改为 `standard-agent`，与 `standard` execution profile 命名一致。
- 删除 `agent_hints`。
- scene manifest 不再通过 `agent_hint_id` 依赖 execution config 中的 agent hint；scene 只保留 model / runner option hint 这类调用语义档位依赖。
- AgentPolicy baseline 由 execution profile 的 `agent_policy_profile_id` 选择。
- scene manifest 如需自定义 `max_iterations` 等 AgentPolicy 参数，直接使用 scene typed `agent_policy` override，并受全局 override 白名单约束。
- per-run AgentPolicy override 由 Service / UI override 层显式执行，并受同一白名单约束；不通过 scene hint 间接覆盖。

### 13. `fallback_mode` schema 语义

当前现象：

- `execution_profiles.json` 中 `agent_policy_profiles.default-agent.fallback_mode` 为 `"finalize"`。
- Engine typed contract `AgentFallbackMode` 的稳定值是 `"force_answer"` / `"raise_error"`。
- runtime assembly smoke 只能临时把 `"finalize"` 映射为 `AgentFallbackMode.FORCE_ANSWER`。

问题判断：

- 如果该字段目标是映射到 `AgentPolicy.fallback_mode`，使用 `"finalize"` 会产生语义错位；它不是 Engine typed input 的合法值。
- 如果该字段目标是 Service 层业务语义，则字段名不应伪装成 Engine `fallback_mode`，需要更明确的 Service policy 名称与映射规则。

已裁决方向：

- config schema 直接使用 Engine enum 值：`"force_answer"` / `"raise_error"`。
- 默认配置将 `fallback_mode` 从 `"finalize"` 改为 `"force_answer"`。
- `ConfigLoader` 的 typed validation 应拒绝 `"finalize"`，避免旧 Service 语义词继续混入 Engine typed input 字段。

### 14. `fallback_prompt` 默认文本

当前现象：

- 当前 `execution_profiles.json` 中 `fallback_prompt` 为 `"请基于已获得证据给出可审计结论。"`。
- 旧项目 `dayu-agent/dayu/config/run.json` 中对应文本为 `"Based on the information gathered, answer the question directly. Do not fabricate if information is insufficient."`

问题判断：

- force-answer 时 Engine 已禁用工具，因此 prompt 不需要再写“不要调用工具”；这是 Engine 硬约束，不应软化为自然语言请求。
- 当前文本“可审计结论”偏抽象，缺少“信息不足不得编造”的明确边界。

已裁决方向：

- 默认 `fallback_prompt` 改为旧项目语义的中文化版本：

```text
请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。
```

- 该 prompt 专注表达 force-answer 的认知任务，不重复 Engine 的工具禁用约束。

### 15. 旧项目模型目录全量迁移

当前现象：

- 旧项目 `dayu-agent/dayu/config/llm_models.json` 中包含多 provider / 多模式模型配置。
- 当前 `dayu-agent-r/dayu/config/models.json` 只迁移了最小 DeepSeek 默认模型，尚未覆盖旧项目完整模型目录。

旧项目待迁移模型集合：

- `deepseek-v4-flash`
- `deepseek-v4-flash-thinking`
- `deepseek-v4-pro`
- `deepseek-v4-pro-thinking`
- `gpt-5.4`
- `gpt-5.4-thinking`
- `claude-sonnet-4-6`
- `claude-sonnet-4-6-thinking`
- `gemini-2.5-flash`
- `gemini-2.5-flash-thinking`
- `gemini-2.5-pro`
- `gemini-2.5-pro-thinking`
- `gemini-2.5-flash-lite`
- `gemini-2.5-flash-lite-thinking`
- `gemini-3.1-pro-preview`
- `gemini-3.1-pro-preview-thinking`
- `gemini-3.1-flash-lite-preview`
- `gemini-3.1-flash-lite-preview-thinking`
- `mimo-v2.5-pro`
- `mimo-v2.5-pro-thinking`
- `mimo-v2.5-pro-plan`
- `mimo-v2.5-pro-thinking-plan`
- `mimo-v2.5-pro-plan-sg`
- `mimo-v2.5-pro-thinking-plan-sg`
- `qwen-plus`
- `qwen-plus-thinking`
- `ollama`

问题判断：

- 这不是简单 JSON 拷贝。旧 schema 字段包括 `runner_type`、`endpoint_url`、`extra_payloads`、`supports_usage`、`max_context_tokens`、`runtime_hints.temperature_profiles` 等；新 schema 字段是 `runner_kind`、`endpoint`、`provider_request_extension`、`supports_stream_usage`、`context_window_tokens` 等。
- 旧 `runtime_hints.temperature_profiles` 需要迁移或归并到新 `execution_profiles.json` 的 `runner_options_profiles` / `runner_hints`，否则 scene manifest 中的 `model.temperature_profile` 无法完整复用旧行为。
- 不同 provider 的扩展必须映射为当前 Engine 支持的 provider extension DSL，不能把旧 `extra_payloads` 作为任意 raw payload 继续透传。

已裁决方向：

- 全量迁移旧 `llm_models.json` 的模型配置到新 `models.json`。
- 同步迁移旧 temperature profiles 到 `execution_profiles.json`，使 `write`、`overview`、`audit`、`decision`、`interactive`、`prompt`、`infer`、`conversation_compaction` 等 profile id 可被 scene manifest 引用。
- 明确各 provider 的 `provider_request_extension` 映射规则；不支持或已过期的字段必须 fail closed，而不是静默保留。
- `provider_request_extension` DSL 已经存在，目标是和旧 `llm_models.json` 的 `extra_payloads` 能力一一对应，而不是继续保留旧 raw `extra_payloads` 字段。
- 旧模型迁移时应把旧 provider 扩展映射到新 DSL：
  - OpenAI reasoning effort。
  - Anthropic thinking。
  - DeepSeek thinking。
  - MiMo thinking。
  - Gemini thinking。
  - Qwen thinking。
- `ConfigLoader` 属于 `dayu.runtime`，不能 import `dayu.engine`，因此不负责把 `provider_request_extension` 转成 Engine typed union。
- `dayu.runtime` 也不能新增会 import Engine 的 helper。若需要复用转换逻辑，应放在 `dayu.engine` 下作为纯 Engine adapter/helper：输入层中立 `JsonValue`，输出 `ProviderRequestExtension | None`。
- Service / composition root 负责调用该 Engine helper，把 ConfigLoader 读出的 JSON DSL 映射为 `RunnerSpec.provider_request`。
- unknown / unsupported provider extension 必须 fail closed，不允许静默透传。
- 迁移时按“新 schema 起库”处理，不保留旧 `llm_models.json` 兼容读取。
- 对模型名称、endpoint、API key env、stream / tool / usage 能力、context window 与 provider extension 做 focused tests，避免默认配置漂移。

### 16. runtime assembly smoke 重写与 schema / contract 验证

当前现象：

- `utils/smoke_host_public_multiturn.py` 的 runtime assembly 模式是在旧 schema 基础上补出来的，包含为了跑通当前缺口而写的临时映射与脚本内默认值。
- P12 已裁决多个 config schema 与 Host public contract 变更，包括 Host runtime、runtime lanes、execution profile、context budget policy、memory projection policy、tool truncation policy、runner option hints、agent policy profile 与 model catalog。

问题判断：

- schema 变更后，现有 smoke 需要重写；否则它会继续验证旧 schema 或用脚本默认值遮住配置缺口。
- P12 最终验证不应只看 ConfigLoader 单元测试，还要看一个真实 Service-like assembly 是否能只依赖配置与 scene / tools 输出装配出 `open_host(options)` 和 per-run typed input。
- smoke 编写过程本身是 schema / public contract 匹配度测试；如果从 config 转 Host / Engine contracts 时出现别扭、缺字段、需要猜默认值或需要反向依赖，应输出为待讨论问题，而不是在 smoke 内静默兜底。

已裁决方向：

- 将 `utils/smoke_host_public_multiturn.py` 的 runtime assembly 路径按新 schema 重写。
- 新增 dedicated smoke scene assets，建议命名为 `smoke_host_public_multiturn`：
  - manifest: `dayu/config/prompts/manifests/smoke_host_public_multiturn.json`
  - prompt fragment: `dayu/config/prompts/scenes/smoke_host_public_multiturn.md`
- smoke 默认使用该 dedicated smoke scene；CLI 仍可显式切换 `scene_id`，用于验证其它 scene。
- dedicated smoke scene 必须是一份普通 scene manifest，不得在 ScenePrepare 或 smoke 脚本中为它写 special case。
- dedicated smoke scene 只表达 scene 应表达的内容：system prompt fragments、context slots、tool selection、可选 `model.default_model_id`、`model.runner_option_hint_id` 与白名单内 `agent_policy` override。
- Host runtime 相关配置仍由 config 提供；scene 不承载 lane、sqlite、artifact root、memory / context policy、truncation 或 worker backend。
- runtime assembly smoke 不写业务默认值；它只依赖 ConfigLoader、ScenePrepare、ToolsDiscovery、显式 CLI override 与代码层真正稳定 default。
- 删除脚本内为了补 schema 缺口写的临时桥接，例如旧 fallback mode 映射、硬编码 model、硬编码 context / memory / truncation 默认值等。
- smoke 只负责读取 config、读取 scene manifest / prompt assets、发现 tools、按已裁决 override 优先级合成 typed inputs，然后调用 `open_host(options)` 与 per-run submit input。
- 如果 config 缺少装配必需字段，smoke 应 fail fast，并把缺口作为 schema / public contract 问题暴露。
- smoke 必须输出一项装配诊断：从 config 转 Host / Engine public contracts 时有哪些地方别扭、需要猜、需要 adapter 过厚、需要 contract 再讨论或 config schema 再裁决。
- 装配诊断还必须列出建议新增哪些 adapter/helper 函数，以简化 Service / composition root 工作；这些 helper 必须放在正确层内，不能让 `dayu.runtime` 反向 import Host / Engine。
- runtime smoke 能在无脚本业务默认值的前提下跑通，作为 config schema 与 Host public contracts 足够匹配的验收信号之一。
- `utils/` 脚本仍无覆盖率要求，但修改后必须跑 smoke 相关命令与 pyright，README 中 runtime smoke 用法需同步当前事实。

### 17. scene model hint 命名修正

当前现象：

- scene manifest 的 `model.default_name` 实际表达 scene 建议的 model id。
- scene manifest 的 `model.temperature_profile` 实际表达 scene 建议的 runner option hint / 调用语义档位。
- 字段名 `default_name` 过于泛化，且不能表达它对应 `models.json` 的 model catalog key。
- 字段名 `temperature_profile` 过窄；P12 已裁决 hint 不只是 temperature，而是 semantic call style selector，并由 model runtime hints 映射为具体 RunnerCallOptions。

已裁决方向：

- 将 scene manifest `model.default_name` 改名为 `model.default_model_id`。
- 将 scene manifest `model.temperature_profile` 改名为 `model.runner_option_hint_id`。
- `default_model_id` 是 scene 层默认建议，不是强制绑定；可被 UI / Run override 覆盖。
- `runner_option_hint_id` 是 scene 层调用语义档位建议，例如 `prompt`、`interactive`、`overview`。
- 如果 scene 不提供 `default_model_id`，Service 使用 execution profile `run_baseline.model_id`。
- 如果 scene 不提供 `runner_option_hint_id`，Service 使用 execution profile `run_baseline.runner_option_hint_id`。

### 18. scene agent policy override

当前现象：

- 当前迁移后的 scene manifest 使用泛化 `runtime` block 表达运行时 hint，例如 `runtime.agent_hint_id`。
- 旧项目 scene manifest 中存在直接的 `agent_policy` 配置，但迁移到当前项目时未保留。
- P12 已裁决删除 `agent_hints`，scene 不再通过 hint id 间接依赖 execution config 修改 AgentPolicy。

问题判断：

- `runtime` 命名过泛，容易继续容纳 runner、agent、tool、session、workflow 等不相干 override。
- scene 如果需要自定义 `max_iterations` 等 AgentPolicy 参数，应直接声明 typed `agent_policy` override。
- WeChat、confirm 等短响应 scene 经常需要比普通 Chat 更低的 `max_iterations`，这是 scene 层合法需求。

已裁决方向：

- 删除 scene manifest 的泛化 `runtime` block。
- scene 如需覆盖 AgentPolicy，使用顶层 typed `agent_policy` block。
- `agent_policy` block 只允许覆盖全局 override 白名单中的 AgentPolicy 字段：`max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt`、`max_consecutive_failed_tool_batches`。
- 未知字段必须 fail fast；禁止 raw dict 透传。
- 常规 scene 不必声明 `agent_policy`，使用 execution profile baseline。
- 迁移旧项目 scene manifest assets 时，必须把旧 manifest 中已有的 `agent_policy` 迁移到新 schema 的顶层 `agent_policy` block。

### 19. scene conversation 字段移除

当前现象：

- 当前迁移后的 scene manifest 包含 `conversation` 字段，例如 `conversation.mode`。
- 旧项目 scene manifest 使用过 `conversation.enabled` / `conversation: false` 表达单轮或多轮语义。
- `prompt.json` 与 `prompt_mt.json` 同时存在，容易把 prompt 任务风格与 Service session lifecycle 混在一起。

问题判断：

- scene manifest 应描述任务 prompt assets、model / runner option hint、tool selection 与 scene-level typed policy override。
- 单轮 / 多轮、是否 `/clear`、是否保留历史，是 Service 的 session lifecycle 决策，不是 scene schema 职责。
- 即使是单轮 prompt，Context Governance 仍可能需要启用；因此不能用 scene 的 conversation 布尔值隐式关闭 Host governance 能力。
- prompt 与 chat / interactive 在参数上仍可不同，例如 `runner_option_hint_id`、`agent_policy.max_iterations`、未来 thinking effort hint 等；这些差异应通过 scene 的 model hint 与 typed `agent_policy` override 表达，而不是 conversation 字段。

已裁决方向：

- 从 scene manifest schema 删除 `conversation` 字段。
- 旧项目 `conversation.enabled` / `conversation: false` 不迁移为 scene 字段。
- 保留 `prompt.json`，它表达 prompt-style task config。
- 删除 `prompt_mt.json`；multi-turn / single-turn 由 Service 是否复用 session、是否 clear history 决定。
- 单轮 prompt 的实现方式是 Service 新建或清空 session 后使用 `prompt` scene submit run。
- `prompt.json` 可以继续声明自己的 `model.runner_option_hint_id`、`agent_policy.max_iterations`、tool selection、fragments 与 context slots。

## 后续执行约束

- 在全部讨论结束前，不直接修改 schema、默认配置、prompt asset 或 smoke 行为。
- 进入修改闭环时，按 `$init-agents` 路由派发 Agent；implementation / fix 交给 AgentCodex 或 AgentOpus，review / re-review 交给 AgentMiMo、AgentDS、AgentGLM 中的可用 review Agent。
- 修改闭环必须同步更新 `docs/host/design.md`、`docs/host/implementation-control.md`、相关 README、测试与 pyright 验证。
