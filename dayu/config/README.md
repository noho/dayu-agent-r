# Dayu 配置说明

本手册只说明当前 `dayu/config/` 的默认配置、workspace root 下 `config/` 覆盖关系与 prompts 目录职责。Engine、Host、Service 和财报领域能力的内部机制不在这里展开。

## 配置层级

Dayu runtime assembly 配置分两层：

1. 包内默认配置：`dayu/config/`
2. 工作区覆盖配置：`<workspace>/config/`

`dayu-cli init --base <workspace>` 会创建目标 workspace，并把当前包内默认配置文件和 `prompts/`
资产发布到 `<workspace>/config/`。该命令会先交互选择普通/思考模型组合，只生成当前 schema 所需的 `models.json`、
`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json`、`tool_discovery.json`
和 prompts 资产；不会生成旧 `llm_models.json` / `run.json`，也不会把明文 API key 写入配置。

配置 schema 与有效值的唯一 owner 仍是 `ConfigLoader` 和本目录当前 JSON；`init` 只构造
transaction-private staging，再用真实 `ConfigLoader`、工具发现与 13 个 production scenes 校验，
通过后才发布。它不实现第二套 loose parser，也不根据旧字段补默认。

`init` 对 `<workspace>/config/` 的状态规则如下：

- FIRST：目标不存在，从本目录默认值创建。
- PRESERVE：目标已存在且无覆盖参数，完整保留用户配置、自建文件和自建 manifest；先补齐
  `models.json`、`execution_profiles.json`、`host_runtime.json`、
  `runtime_lanes.json`、`tool_discovery.json` 中缺失的文件，再补缺失的 package prompt
  普通文件；随后只把本次选择写入相应模型记录和 16 个 package-known manifest 的
  `model.default_model_id`，其它 manifest 字段保持不变。已经存在的根配置和 prompt
  文件不会被补缺步骤覆盖。
- OVERWRITE：`--overwrite` 从本目录默认值重建整个 `config/`，不合并旧树。
- RESET：`--reset` 经默认 No 的明确确认后，从本目录默认值重建 `config/`；同时由 workspace
  transaction 移除整个 `.dayu/`。RESET 优先于 `--overwrite`。

四种状态都不把 `portfolio/` 或 `assets/` 纳入配置 manifest。`init` 会拒绝 workspace、
受管树及其子树中的 symlink / Windows reparse entry，避免沿链接把配置或清理动作带出工作区。
无 destructive flag 时，普通文件占据受管根也会失败；OVERWRITE 只允许修复普通文件形态的
`config`，RESET 允许修复普通文件形态的 `config` 与 `.dayu`。symlink、reparse 与 special
file 不因 destructive mode 放宽。
所选模型需要的 secret 仍只通过 `api_key_ref` 表达；用户确认后由 POSIX shell profile 或 Windows
用户环境 owner 持久化，配置文件、异常和 CLI 输出都不保存 value。

当前 15 个 init choice 的 ordinary / thinking pair 必须解析到相同的 provider、
provider model、endpoint 与 credential ref；provider request extension、runner hint、采样和
stream 参数可以不同。选择结果投影到全部 16 个 package-known manifest，其中
`conversation_compaction` 使用 ordinary model family 与自己的
`conversation_compaction` runner hint。

动态 Ollama / OpenAI-compatible 模型的 `context_window_tokens` 必须不低于本次目标
default execution profile 的 `min_context_window_tokens`。FIRST、OVERWRITE 与 RESET
读取 package default profile；PRESERVE 读取 workspace overlay 后的 effective default
profile，workspace 文件缺失时自然使用 package layer。已存在但非法的 workspace
`execution_profiles.json` 会直接失败并提示使用 `--overwrite`，不会改用 package 值掩盖
错误。Custom 模型的默认 context window 直接取目标 minimum；Ollama 的默认值或显式输入
低于 minimum 时会在 context 输入步骤重新询问。

`dayu.runtime.location.resolve_runtime_locations` 负责把 workspace root 解析为 runtime assembly 位置：`<workspace>/config` 存在时输出 `config_overlay_dir`，不存在时输出 `None`；prompt assets 与 scene manifests 优先使用 workspace 中已存在的对应目录，否则使用包内默认资产。`ConfigLoader` 只接收调用方显式传入的配置目录，不猜测 workspace 路径。

`dayu.runtime.config_loader.ConfigLoader` 默认加载包内配置；调用方可以显式传入 workspace 配置目录。ConfigLoader 不解析环境变量，不替换 secret，不脱敏，也不 import Host、Engine、Service、UI、Fins 或具体业务工具包。

覆盖规则按配置文件类型分别执行：

- 顶层 map 按稳定 id 合并。
- workspace 中与包内同 id 的记录会整条替换包内记录。
- 顶层非 map 字段也由 workspace 值整体替换；即使该值是 object，也不会做字段级合并。
  因此 workspace 必须提供该字段的完整当前 schema，缺字段会在 typed 校验阶段直接失败。
- 不做隐式 deep merge；复用配置只能用显式 `extends`。
- `extends` 只允许单继承；循环、自引用、多父项、父项缺失、缺字段和非法类型都会加载失败。
- catalog record id 只来自顶层 map key；record 内不得重复写 `model_id`、`provider_id`、`runtime_id`、`host_runtime_id`、`profile_id` 或 `execution_profile_id`。

所有配置文件使用严格 JSON 数值边界：`NaN`、`Infinity`、`-Infinity` 以及解析后
溢出为无穷的数字都会在文件读取时失败；timeout、backoff、TTL、heartbeat 等数值字段
还会按各自 schema 校验正数或非负数。不要依赖 Python `json` 的非标准常量扩展。

## 当前文件

```text
dayu/config/
├── README.md
├── execution_profiles.json
├── host_runtime.json
├── models.json
├── runtime_lanes.json
├── prompts/
│   ├── base/
│   ├── manifests/
│   └── scenes/
└── tool_discovery.json
```

旧 `llm_models.json` 和 `run.json` 已删除，不再提供兼容读取路径。

## models.json

`models.json` 是模型目录，只表达 provider / model 能力和请求基础参数。顶层字段为 `models`，每条记录的 key 是模型配置稳定 id。

常用字段：

| 字段 | 含义 |
|---|---|
| `runner_kind` | Runner 类别，当前默认配置使用 `openai_compatible` |
| `provider` | provider 标识 |
| `model` | provider 模型名 |
| `endpoint` | provider endpoint |
| `api_key_ref` | API key 引用，按字符串原样保留；本地或免鉴权 provider 可为 `null` |
| `headers` | 请求 headers，按配置原样保留 |
| `supports_tool_calling` | 是否支持工具调用 |
| `supports_stream` | 是否支持流式输出 |
| `supports_stream_usage` | 是否支持流式 usage |
| `default_timeout_seconds` | 默认请求超时秒数 |
| `max_retries` | 默认最大重试次数；包内默认模型使用 `3` |
| `sse_idle_timeout_seconds` | SSE 空闲超时秒数 |
| `sse_heartbeat_seconds` | SSE 空闲诊断 heartbeat 秒数 |
| `provider_request_extension` | provider 私有请求扩展 JSON DSL，按原样保留 |
| `context_window_tokens` | 模型上下文窗口 token 数 |
| `runtime_hints.runner_option_hints` | 模型内 semantic RunnerCallOptions hints |

`runtime_hints.runner_option_hints` 的每个 hint 都是默认 RunnerCallOptions 配置片段，只包含 `temperature`、`top_p` 与 `stream`。默认配置不提供输出 token cap；`RunnerCallOptions.max_tokens` 只保留给显式 per-run 或 provider adapter override 使用。execution profile 只引用 `model_id` 和 semantic `runner_option_hint_id`，不保存 provider-specific 调用参数。

模型记录可以使用 `extends` 继承基础模型；子记录按顶层字段覆盖父记录。thinking 变体通常继承对应基础模型，只覆盖 `provider_request_extension`，需要 provider beta header 等差异时也可以同时覆盖完整 `headers` object。

## execution_profiles.json

`execution_profiles.json` 表达 Service / composition root 生成完整执行输入所需的 execution baseline 与治理策略选择。顶层字段包括：

| 字段 | 含义 |
|---|---|
| `default_execution_profile_id` | 默认 execution profile id，默认值为 `standard-256k` |
| `execution_profiles` | 普通 Run、compactor、context budget、memory projection、工具治理与 agent policy 的完整基线 |

单个 execution profile 包含：

- `context_window_class`：profile 面向的上下文窗口分档，当前只允许 `256k` 与 `1m`。
- `min_context_window_tokens`：profile 要求的最小模型上下文窗口 token 数，`256k` 为 `262144`，`1m` 为 `1000000`。
- `run_baseline`：普通 Run 默认 `model_id` 与 `runner_option_hint_id`。
- `compactor_baseline`：compactor 默认 `model_id`、`scene_id`、`runner_option_hint_id`、`user_prompt_template_path` 与 `artifact_root`；相对 `artifact_root` 按当前 workspace root 解析，包内默认写入 `.dayu/artifacts/compaction`。
- `context_budget_policy`：对齐 Host public `ContextBudgetPolicy` 的 ratio-first 配置；上下文窗口来自 effective model 的 `context_window_tokens`。
- `memory_projection_policy`：对齐 Host public `MemoryProjectionPolicy` 的 per-section cap / floor 配置，包含 selected recent window、fallback selected recent window、evidence fact、session summary、answer anchor、forward intent、reference continuity、inline delta repair limits 与 `policy_ref`；`context_window_size` 由 profile 显式配置并由 Service 一对一装配。
- `tool_truncation_policy`：只配置默认截断治理参数和默认 limits，不配置 per-tool strategy / target。
- `tool_duplicate_governance_policy`：配置 attempt-scoped 重复工具调用治理，包含默认 duplicate decision、按工具名覆盖的 decision、require-justification 参数名映射，以及治理消息文本。
- `agent_policy`：内嵌 Agent loop、continuation、工具超时、fallback 等 policy。

`context_budget_policy` 中，`max_reactive_compactions_per_run` 是单个 Run 可启动的
reactive operation 上限；`max_compaction_attempts_per_operation` 是每个 proactive 或
reactive operation 冻结的 semantic proposal attempt 预算。proactive 是否启动只由当前输入与
预算事实决定，不提供单独的 proactive operation 次数配置；Runner transport retry 不计入
semantic proposal attempt。

`memory_projection_policy` 当前字段为：

| 字段 | 含义 |
|---|---|
| `context_window_size` | effective model context window，由 execution profile 显式配置并装配到 Host policy。 |
| `selected_recent_window_item_cap` | selected recent window 的 item 上限。 |
| `selected_recent_window_char_cap` | selected recent window 的字符上限。 |
| `selected_recent_window_turn_floor` | selected recent window 必须保留的近轮下限。 |
| `fallback_selected_recent_window_item_cap` | fallback selected recent window 的 item 上限，必须覆盖近轮 floor 且不超过普通 selected recent window 上限。 |
| `fallback_selected_recent_window_char_cap` | fallback selected recent window 的字符上限，不得超过普通 selected recent window 字符上限。 |
| `evidence_fact_item_cap` | evidence-backed fact 的 item 上限。 |
| `evidence_fact_char_cap` | evidence-backed fact 的字符上限。 |
| `evidence_fact_floor` | evidence-backed fact 的保底数量。 |
| `session_summary_char_cap` | session summary 的字符上限。 |
| `answer_anchor_item_cap` | answer anchor 的 item 上限。 |
| `answer_anchor_char_cap` | answer anchor 的字符上限。 |
| `forward_intent_item_cap` | forward intent 的 item 上限。 |
| `forward_intent_char_cap` | forward intent 的字符上限。 |
| `reference_continuity_item_cap` | reference continuity item 上限。 |
| `reference_continuity_char_cap` | reference continuity 字符上限。 |
| `reference_continuity_item_floor` | reference continuity item 保底数量，包内默认可为 `0`。 |
| `max_lag_events_for_inline_delta` | 允许 inline delta repair 覆盖的 snapshot lag 事件数。 |
| `max_delta_repair_events` | 单次 delta repair 可读取的最大事件数。 |
| `policy_ref` | memory projection policy 的稳定配置引用。 |

`tool_duplicate_governance_policy.default_duplicate_decision` 与 `decisions_by_tool_name` 只允许 `allow`、`reuse`、`hint`、`require_justification`、`hard_stop`。`messages` 是 duplicate governance 返回给模型和诊断的文本，workspace overlay 可以按 profile 覆盖；这些文本不是 scene prompt asset，不放在 `prompts/` 目录。默认 messages 只使用模型可执行、人工可读的外部语义，不要求模型理解 Host、ToolRuntime、Attempt 等内部实现概念。

包内默认 `default_duplicate_decision` 为 `hint`：同一推理步骤内重复请求相同工具证据时，默认返回行为提示，让模型优先使用上一次工具结果，只有在主体、期间、指标或证据范围不同的情况下才重新调用工具。

`agent_policy` 使用 `continuation_max_attempts`、`allow_tool_calls`、`max_consecutive_failed_tool_batches` 等当前 AgentPolicy 字段。`fallback_mode` 只允许 `force_answer` 与 `raise_error`；默认 fallback prompt 文本为“请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。”

包内默认 profile 按场景与上下文窗口显式分档为 `standard-256k`、`standard-1m`、`wechat-256k` 与 `wechat-1m`。Service / composition root 只能通过显式 override 或 `default_execution_profile_id` 选择 profile；runtime assembly helper 只校验 profile 的 `min_context_window_tokens` 与 effective model 的 `context_window_tokens`，不会按模型窗口自动切换到其它 profile。`256k` profile 搭配 `1m` 模型允许装配，但诊断会标记为保守策略；`1m` profile 搭配低于 `1000000` token 的模型会在调用 Host 前失败。

四个 package execution profile 的 `run_baseline.model_id` 与
`compactor_baseline.model_id` 当前都指向 `mimo-v2.5-pro-plan`。这保证 scene hint
缺失时，普通 Run 与 compactor fallback 仍使用同一个 Mimo Token Plan family。

配置只接受上述内嵌 `agent_policy` 与 baseline 结构；历史 catalog、间接引用或全局 runner/agent hint 结构出现在配置中都会加载失败。

## host_runtime.json

`host_runtime.json` 表达 Host opener 的部署默认值。顶层字段为 `default_host_runtime_id` 和 `runtimes`。

每条 runtime 记录覆盖：

- Host durable store 与 artifact roots；相对路径按当前 workspace root 解析，包内默认写入 `.dayu/host` 与 `.dayu/artifacts`。
- SQLite path、busy timeout 与写事务 busy retry 策略；相对路径按当前 workspace root 解析，包内默认写入 `.dayu/host/dayu_host.sqlite3`。
- `host_execution_lane_name`：引用 `runtime_lanes.json` 中已存在的 lane。
- `worker_backend`，当前默认配置为 `local`。
- `dispatch_poll_interval_seconds`。
- `payload_inline_threshold_bytes`，包内默认值为 `65535` bytes。
- `worker_startup_timeout_seconds`。
- `memory_projection_catch_up_batch_size`。
- 必填 `session_event_delivery_policy`：完整保存 Host Session Event Delivery 的
  item-only resource policy，并由 Service 一对一装配到 `OpenHostOptions`。
- 必填 `wait_poller_policy`：完整保存 production wait poller 的部署 snapshot；
  ConfigLoader 只做层中立 typed projection，不解释 provider 或 Fins 语义。
- 可选 `process_capsule_interrupt_policy`：process-backed 工具子进程取消 / 超时后的 cleanup interrupt 策略，只包含 `terminate_grace_seconds` 与 `kill_grace_seconds`。字段缺省时由 Host typed 默认值决定；显式配置必须是有限非负数，不能使用 boolean、NaN 或正负无穷。该策略只约束 cleanup grace，不是单次工具业务执行 deadline，不能替代 execution profile 中的 `agent_policy.tool_execution_timeout_seconds`。

`wait_poller_policy` 必须同时提供 `enabled`、`poll_interval_seconds`、
`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、
`backoff_multiplier`、`backoff_max_delay_seconds`、
`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、
`adapter_call_timeout_seconds`、`close_drain_timeout_seconds` 与
`max_outstanding_adapter_calls`。除 `enabled` 外所有字段都是有限正数；两个整数位
`claim_batch_size`、`max_outstanding_adapter_calls` 显式拒绝 JSON boolean。
缺字段、多余字段、`null`、零、负数或非有限值都会加载失败。包内 snapshot 固定为
`true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`，顺序与上述字段一致。

`session_event_delivery_policy` 必须且只能提供
`transient_mailbox_max_items` 与 `max_subscriptions_per_session`。两者都是严格正整数，
显式拒绝 JSON boolean、零、负数、浮点数、字符串、缺字段和多余字段。包内 snapshot
固定为 `512` 与 `4`：前者约束单订阅 mailbox 与唯一 in-flight 合计的 retained item，
后者约束同一 opener 内单 Session 的 subscription reservation；该配置不提供 byte 或
resident-heap 上界字段。

这些配置都是 `open_host(options)` construction-time assembly inputs 的来源，不是单个 Run 的 override。prompt asset root 与 scene manifest root 不在 `host_runtime.json` 中配置，由 runtime location resolver 解析。

## runtime_lanes.json

`runtime_lanes.json` 表达层中立 runtime lane coordinator 与 lane catalog。顶层字段包括：

| 字段 | 含义 |
|---|---|
| `coordinator.db_path` | 独立 runtime lane SQLite DB 路径；相对路径按当前 workspace root 解析，包内默认写入 `.dayu/runtime/runtime_lanes.sqlite3` |
| `coordinator.busy_timeout_seconds` | coordinator SQLite busy timeout |
| `coordinator.poll_interval_seconds` | acquire 轮询间隔 |
| `lanes` | 按 lane 名索引的容量配置 |

单个 lane 包含 `capacity`、`default_timeout_seconds`、`claim_ttl_seconds` 与
`heartbeat_interval_seconds`。timeout 必须是有限非负数；busy timeout、poll interval、
TTL 与 heartbeat 必须是有限正数；`claim_ttl_seconds` 还必须大于
`heartbeat_interval_seconds`。

## tool_discovery.json

`tool_discovery.json` 只表达 ToolsDiscovery provider specs。ConfigLoader 只读出 typed provider specs，不 import provider，也不做工具发现。

provider 字段：

| 字段 | 含义 |
|---|---|
| `import_path` | 显式 `module:attribute` provider callable |
| `entry_point` | package entry point provider callable |
| `source_kind` | 来源类别，使用工具来源公共契约值 |
| `source_id` | 来源标识 |
| `enabled` | 是否启用 provider |
| `config` | provider 自身的层中立 JSON 配置；ConfigLoader 原样读取，不解释 Doc / Fins / Web 语义 |

`import_path` 与 `entry_point` 必须二选一。provider id 来自 `providers` map key，不在 record 内重复配置。`config` 缺省等价空对象；需要业务含义时由调用方先把 raw config 与运行时参数装配为 effective provider spec，再交给对应 provider 解析，例如文档路径白名单、财报 workspace root、Web 请求限制等。启用 provider 返回空工具集合是配置错误；不希望某个 provider 参与发现时使用 `enabled=false`。

包内默认 Fins providers 分为四组，均为 `enabled=true` 且 raw config 不写 `workspace_root`。Service effective config 会用当前 runtime workspace root 注入绝对 `workspace_root` 后再传给 Fins provider；workspace overlay 只有在需要改用其它财报仓储根目录时才显式配置 `config.workspace_root`。Fins provider 默认参与工具发现；scene manifest 再决定实际选择哪些 Fins tools：

| provider id | import path | 能力 |
|---|---|---|
| `financial-read-tools` | `dayu.fins.tools.provider:discover_tools` | 财报 read tools |
| `financial-download-tools` | `dayu.fins.tools.download_provider:discover_tools` | 财报 download awaiting tool |
| `financial-preprocess-tools` | `dayu.fins.tools.preprocess_provider:discover_tools` | 财报 preprocess awaiting tool |
| `financial-upload-tools` | `dayu.fins.tools.upload_provider:discover_tools` | 财报 upload awaiting tool |

三个 awaiting provider 的 `config.awaiting_resolution_mode` 都是必填 provider-owned
字段，只允许精确的 `poll`、`callback`、`manual`；包内配置均显式写为 `poll`。
ConfigLoader 仍把 `config` 当作 opaque JSON，不解析、规范化或默认该字段；唯一业务
解析由 Fins 共享 parser 完成。即使 provider 为 disabled，Service 也会先把 raw config
交给该 parser 严格校验，再做 active filtering。已识别的 Fins read / Web non-awaiting
provider 声明该字段会作为 owner misuse 失败，未知第三方 provider 不由此配置契约扩展语义。

启用任一 Fins provider 时，传给 provider 的 effective spec 必须包含绝对 `workspace_root`；该值可以来自 workspace overlay 的 `config.workspace_root`，也可以由 Service 调用方用当前 runtime workspace 注入。provider 不从 cwd 或环境变量猜路径。`financial-read-tools` 的 packaged `config.limits` 显式写入默认值：`processor_cache_max_entries=128`、`list_documents_max_items=300`、`get_document_sections_max_items=1200`、`search_document_max_items=20`、`list_tables_max_items=50`、`read_section_max_chars=80000`、`get_page_content_max_chars=80000`、`get_table_max_items=800`、`get_financial_statement_max_items=1200` 与 `query_xbrl_facts_max_items=1200`。workspace overlay 可用同名正整数字段覆盖这些 read limits。`financial-upload-tools` 启用时注册 `start_fins_upload`；上传工具只校验本地路径必须指向存在的非空普通文件，财报写入仍通过 Fins workspace repository 完成。Download / preprocess / upload 能力通过独立 provider 启用，不通过 read provider 的布尔开关混合启用。

包内默认 `doc-tools` provider 指向 `dayu.tools.doc_provider:discover_tools`，默认 `enabled=false` 且 `allowed_paths=[]`。只有在 workspace overlay 启用并在 `config.allowed_paths` 中显式配置可访问文件或目录根时才注册可执行文档工具。白名单为空时 provider 会 fail fast。Doc provider 的 packaged `config.limits` 显式写入默认值：`list_files_max=200`、`get_sections_max=200`、`search_files_max_results=50`、`read_file_max_chars=80000` 与 `read_file_section_max_chars=50000`；workspace overlay 可用同名正整数字段覆盖这些 Doc limits。

包内默认 `web-tools` provider 指向 `dayu.tools.web:discover_tools`，默认 `enabled=true`。Provider 只暴露 `search_web` 与 `fetch_web_page`；`config` 可设置 `provider`（`auto` / `tavily` / `serper` / `duckduckgo`）、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、五个独立布尔 policy 字段、`playwright_channel`、`playwright_storage_state_dir` 与 nested `resource_budget`。默认 `playwright_storage_state_dir` 是 `.dayu/web_tools_storage_states`，Service discovery 会按当前 workspace root 解析为 `<workspace>/.dayu/web_tools_storage_states`；只有该目录下存在目标 host 对应的 storage state 文件时，Playwright fallback 才会注入登录态。

`ConfigLoader` 对同 id provider record 仍执行整条替换且不 deep merge；Web provider 只解析替换后的 final `config`。这个 final record 可以合法缺少已知字段，Web parser 会逐字段或逐 budget group 补对应 typed default，并保留已提供的 sibling；任何未知顶层字段（包括拼写错误）都会在读取其它字段前按 `web provider config.<field>` 精确 fail fast。

五个布尔字段各自独立解析，缺失时使用以下 typed default，显式值只接受 JSON boolean：

| 字段 | 默认值 | 当前配置事实 |
|---|---:|---|
| `allow_private_network_url` | `true` | 是否允许 private / local URL |
| `allow_custom_port_url` | `true` | 是否允许非默认 HTTP(S) 端口；不再从 private policy 反推 |
| `dns_peer_proof_enabled` | `false` | 是否要求 HTTP numeric target / peer proof |
| `allow_environment_proxy` | `true` | 是否允许环境 proxy |
| `browser_enabled` | `true` | browser capability 开关；不从 private policy 反推 |

`dns_peer_proof_enabled`、`allow_environment_proxy` 与 `browser_enabled` 会在一次 Web tool 调用中冻结为不可变 typed snapshot，并由 search/fetch/browser 执行路径共同消费。peer proof 关闭时 HTTP 使用标准 Session；允许环境 proxy 时 `trust_env=true`，禁止时 `trust_env=false` 且发送设置中的 proxy 映射为空。peer proof 开启且当前 URL 未选择 proxy 时复用 numeric target 与实际 peer 校验；若当前 URL 实际选择了环境 proxy，则以稳定的 `proxy_peer_proof_incompatible` 失败，不会静默降级。proxy warning 只记录是否启用与稳定原因，不记录 URL、proxy 值或 credential。

`browser_enabled` 与 `allow_private_network_url` 互不授权：关闭 browser 不会因允许 private URL 而启动浏览器，关闭 private URL 也不阻止公网 browser 访问；browser 的每次 route/navigation 仍逐目标执行同一出站策略。只有真实 browser fallback 即将启动且 peer proof 已开启时，才会在导入或启动 browser process 前以 `browser_peer_proof_unavailable` 失败。禁止环境 proxy 时 browser worker 会清理标准 proxy 环境变量，允许时沿用当前运行环境。

Web 资源预算的唯一 raw 配置路径是 `providers["web-tools"].config.resource_budget`。Provider 把它解析为 `http`、`browser`、`diagnostics` 三个 owner group；group 或 field 缺失时只补对应 child owner 的 typed default，已提供 sibling 保持不变。未知 group、未知 field、错误 object 类型、布尔值、零或负数都会按完整字段路径 fail fast。当前完整默认与等价显式示例为：

```json
{
  "providers": {
    "web-tools": {
      "config": {
        "resource_budget": {
          "http": {
            "wire_body_bytes": 134217728,
            "decoded_body_bytes": 268435456
          },
          "browser": {
            "warmup_body_bytes": 1048576,
            "dom_chars": 16777216,
            "text_chars": 8388608
          },
          "diagnostics": {
            "error_chars": 8192,
            "events": 512
          }
        }
      }
    }
  }
}
```

下游只接收自己消费的 child budget：HTTP search/fetch 使用 `http`，warmup 与 browser DOM/text/Markdown 使用 `browser`，browser failure / diagnostics projection 使用 `diagnostics`；`resource_budget` aggregate 不进入执行器。

包内默认 `utils-tools` provider 指向 `dayu.tools.utils:discover_tools`，默认 `enabled=true`。Provider 当前只暴露 `get_current_time`，用于需要实时时钟的场景；工具只支持 `timezone="Asia/Shanghai"` 或省略该参数，并返回 `time`、`timezone`、`weekday` 与 `iso` 字段。该工具不提供财报、网页或文件事实。

## prompts 目录职责

`<workspace>/config/prompts/` 与包内 `dayu/config/prompts/` 用于放置 prompt fragments 和 scene manifests。包内默认资产按目录分为：

| 路径 | 职责 |
|---|---|
| `prompts/manifests/*.json` | ScenePrepare schema v1 scene manifest |
| `prompts/base/*.md` | 多个 scene 复用的基础 prompt fragment |
| `prompts/scenes/*.md` | 单个 scene 的场景 prompt fragment |

Scene manifest 由 `dayu.runtime.scene_prepare` 解释；ConfigLoader 不读取、拼接或渲染 scene manifest。`prompts/tasks/`、contract 文件、workflow 产物和未被 scene manifest 直接引用的模板不属于当前包内默认资产范围。

Scene manifest 第一版是单 Run 场景装配输入。允许的顶层字段固定为 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments` 与 `context_slots`。调用方显式传入 manifest root、prompt asset root、typed context slot values 与可用工具目录；ScenePrepare 只读取 manifest 直接引用的 fragments，执行确定性的文本替换，并输出 system messages、已拼接的 system prompt、工具选择结果、model hints、typed agent policy override、fragment refs、source refs 与 content digest。

Prompt fragment 可以使用条件块 marker 控制工具说明是否进入最终 system prompt。`<when_tag TAG>...</when_tag>` 只在当前 scene 选中对应工具 tag 时保留正文；`<when_tool NAME>...</when_tool>` 只在当前 scene 选中对应工具名时保留正文。条件块 marker 是 ScenePrepare 解释的 prompt asset 控制语法，渲染后的 LLM-facing system prompt 不应包含这些 marker。

默认非上传 scene 不使用 broad `"fins"` tag 选择 Fins 工具，也不在 packaged manifest 中列出具体工具名；它们通过窄标签 `"fins-read"`、`"fins-download"`、`"fins-preprocess"` 选择财报 read / download / preprocess 工具。除 `conversation_compaction` 这类压缩 scene 外，包内 scene manifest 都声明 required `current_time` context slot，并在 scene prompt 的主要执行契约正文之后渲染 `{{current_time}}`。`current_time` 是 LLM-facing 当前时间文本，表示对话开始时的当前时间；回答普通“现在 / 今天 / 当前时间”问题默认使用它，且该时间不会自动更新。它不等同于工具暴露。

`prompt` 与 `interactive` manifest 还声明 required `fins_default_subject` slot，并在 scene
执行契约与 `current_time` 之后渲染 `{{fins_default_subject}}`。CLI 的可选 `--ticker`
通过共享 Service scene-context builder 生成该模型可读文本；未提供 ticker 时 slot 值为空，
不会把 CLI metadata 或内部标识伪装成财报事实。

`prompt` 是单轮问答 scene，不暴露 download / preprocess / upload 这类长事务工具；需要模型在对话中触发 download / preprocess 时，使用 `interactive` 或 `wechat` scene。

只有 `interactive` 与 `wechat` manifest 通过 `"utils"` tag 选择 `get_current_time` 工具，使模型在用户明确要求获取此刻最新时间，或要求在等待、查询、下载、上传、处理等动作完成后再确认时间时可以主动调用工具。`prompt` 与其它 scene 即使需要当前时间，也只消费 `current_time` context slot，不通过 `"utils"` tag 暴露该工具。manifest 不写 `"time"` tag 或具体工具名也能通过 `"utils"` tag 获得默认实时时钟能力。这样即使 upload provider 默认注册 `start_fins_upload`，也不会被非上传 scene 通过泛化 Fins tag 意外选中。`tool_selection.allow_empty` 只控制 scene 工具选择空匹配语义，和 ToolsDiscovery provider 是否允许空输出无关。

`conversation_compaction` 是会话压缩专用 scene。该 scene 使用一个 required fragment 作为 compactor system prompt，并在 scene 的 `agent_policy` block 中声明 compactor AgentPolicy。user prompt template 由 execution profile 的 `compactor_baseline.user_prompt_template_path` 指向 prompt asset；template 使用 `<<compaction_request>>` 作为运行期请求数据块占位符，该占位符不是 ScenePrepare context slot，不能写成 `{{...}}`。

package `conversation_compaction` manifest 的 `model.default_model_id` 当前是
`mimo-v2.5-pro-plan`，与 package ordinary baseline 同 family；
`model.runner_option_hint_id` 保持 `conversation_compaction`，因此压缩调用仍可使用独立
temperature、top-p、stream 与 provider request extension。

会话压缩 prompt asset 是直接投给模型阅读的文本，必须自足说明输入 JSON、输出 JSON 字段、字段含义、类型、必填性、允许值、最小示例与 label 引用规则。prompt 中的 label 只能解释为本次请求内的引用标签，不得写成业务事实、财报事实或用户可见结论；prompt 不要求模型理解 Host 内部治理、Python 类型名、迁移术语或底层账本标识。

Service assembly 不硬编码 compactor scene 名或 user template 路径；它从当前 execution profile 的 `compactor_baseline.scene_id` 读取 scene id，通过 ScenePrepare 装配 system prompt 与 AgentPolicy，并从 `compactor_baseline.user_prompt_template_path` 读取 user prompt template。

`model` 只使用 `default_model_id` 与 `runner_option_hint_id`。`agent_policy` 是可选 typed override block，只允许覆盖 `max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt` 与 `max_consecutive_failed_tool_batches`。旧 `conversation`、泛化 `runtime`、`model.default_name`、`model.temperature_profile` 与 `prompt_mt` scene 均不属于当前 schema。

Scene manifest 不表达 workflow step graph、next scene、artifact store、parser、retry / replay / stop policy、failure classification 或 checkpoint / resume。多 Run 财报流程属于 Service workflow 或后续 typed skill orchestration，不属于 prompt asset schema。

## 最小 workspace 覆盖示例

只覆盖一个模型时，workspace 文件应提供该模型的完整记录，且 record 内不重复写 `model_id`：

```json
{
  "models": {
    "deepseek-v4-flash": {
      "runner_kind": "openai_compatible",
      "provider": "deepseek",
      "model": "deepseek-v4-flash",
      "endpoint": "https://api.deepseek.com/chat/completions",
      "api_key_ref": "DEEPSEEK_API_KEY",
      "headers": {
        "Authorization": "Bearer {{DEEPSEEK_API_KEY}}",
        "Content-Type": "application/json"
      },
      "supports_tool_calling": true,
      "supports_stream": true,
      "supports_stream_usage": true,
      "default_timeout_seconds": 3600.0,
      "max_retries": 3,
      "sse_idle_timeout_seconds": 120.0,
      "sse_heartbeat_seconds": 10.0,
      "provider_request_extension": {
        "type": "deepseek_thinking",
        "enabled": false
      },
      "context_window_tokens": 1048576,
      "runtime_hints": {
        "runner_option_hints": {
          "interactive": {
            "temperature": 1.3,
            "top_p": 1.0,
            "stream": true
          },
          "conversation_compaction": {
            "temperature": 0.4,
            "top_p": 1.0,
            "stream": false
          }
        }
      }
    }
  }
}
```

如果只想复用包内记录并改少量字段，应新增一个 id 并用 `extends` 显式继承；不要指望 workspace partial record 与包内同 id 记录 deep merge。
