# Dayu 配置说明

本手册只说明当前 `dayu/config/` 的默认配置、`workspace/config/` 覆盖关系与 prompts 目录职责。Engine、Host、Service 和财报领域能力的内部机制不在这里展开。

## 配置层级

Dayu runtime assembly 配置分两层：

1. 包内默认配置：`dayu/config/`
2. 工作区覆盖配置：`workspace/config/`

`dayu.runtime.location.resolve_runtime_locations` 负责把项目根目录解析为 runtime assembly 位置：`workspace/config` 存在时输出 `config_overlay_dir`，不存在时输出 `None`；prompt assets 与 scene manifests 优先使用 workspace 中已存在的对应目录，否则使用包内默认资产。`ConfigLoader` 只接收调用方显式传入的配置目录，不猜测 workspace 路径。

`dayu.runtime.config_loader.ConfigLoader` 默认加载包内配置；调用方可以显式传入 workspace 配置目录。ConfigLoader 不解析环境变量，不替换 secret，不脱敏，也不 import Host、Engine、Service、UI、Fins 或具体业务工具包。

覆盖规则按配置文件类型分别执行：

- 顶层 map 按稳定 id 合并。
- workspace 中与包内同 id 的记录会整条替换包内记录。
- 不做隐式 deep merge；复用配置只能用显式 `extends`。
- `extends` 只允许单继承；循环、自引用、多父项、父项缺失、缺字段和非法类型都会加载失败。
- catalog record id 只来自顶层 map key；record 内不得重复写 `model_id`、`provider_id`、`runtime_id`、`host_runtime_id`、`profile_id` 或 `execution_profile_id`。

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
- `compactor_baseline`：compactor 默认 `model_id`、`scene_id`、`runner_option_hint_id`、`user_prompt_template_path` 与 `artifact_root`。
- `context_budget_policy`：对齐 Host public `ContextBudgetPolicy` 的 ratio-first 配置；上下文窗口来自 effective model 的 `context_window_tokens`。
- `memory_projection_policy`：对齐 Host public `MemoryProjectionPolicy` 的 per-section cap / floor 配置，包含 selected recent window、fallback selected recent window、evidence fact、session summary、answer anchor、forward intent、reference continuity、inline delta repair limits 与 `policy_ref`；`context_window_size` 由 profile 显式配置并由 Service 一对一装配。
- `tool_truncation_policy`：只配置默认截断治理参数和默认 limits，不配置 per-tool strategy / target。
- `tool_duplicate_governance_policy`：配置 attempt-scoped 重复工具调用治理，包含默认 duplicate decision、按工具名覆盖的 decision、require-justification 参数名映射，以及治理消息文本。
- `agent_policy`：内嵌 Agent loop、continuation、工具超时、fallback 等 policy。

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

配置只接受上述内嵌 `agent_policy` 与 baseline 结构；历史 catalog、间接引用或全局 runner/agent hint 结构出现在配置中都会加载失败。

## host_runtime.json

`host_runtime.json` 表达 Host opener 的部署默认值。顶层字段为 `default_host_runtime_id` 和 `runtimes`。

每条 runtime 记录覆盖：

- Host durable store 与 artifact roots。
- SQLite path、busy timeout 与写事务 busy retry 策略。
- `host_execution_lane_name`：引用 `runtime_lanes.json` 中已存在的 lane。
- `worker_backend`，当前默认配置为 `local`。
- `dispatch_poll_interval_seconds`。
- `payload_inline_threshold_bytes`，包内默认值为 `65535` bytes。
- `worker_startup_timeout_seconds`。
- `memory_projection_catch_up_batch_size`。

这些配置都是 `open_host(options)` construction-time assembly inputs 的来源，不是单个 Run 的 override。prompt asset root 与 scene manifest root 不在 `host_runtime.json` 中配置，由 runtime location resolver 解析。

## runtime_lanes.json

`runtime_lanes.json` 表达层中立 runtime lane coordinator 与 lane catalog。顶层字段包括：

| 字段 | 含义 |
|---|---|
| `coordinator.db_path` | 独立 runtime lane SQLite DB 路径 |
| `coordinator.busy_timeout_seconds` | coordinator SQLite busy timeout |
| `coordinator.poll_interval_seconds` | acquire 轮询间隔 |
| `lanes` | 按 lane 名索引的容量配置 |

单个 lane 包含 `capacity`、`default_timeout_seconds`、`claim_ttl_seconds` 与 `heartbeat_interval_seconds`。`claim_ttl_seconds` 必须大于 `heartbeat_interval_seconds`。

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
| `allow_empty` | 是否允许 provider 返回空工具集合 |
| `config` | provider 自身的层中立 JSON 配置；ConfigLoader 原样读取，不解释 Doc / Fins / Web 语义 |

`import_path` 与 `entry_point` 必须二选一。provider id 来自 `providers` map key，不在 record 内重复配置。`config` 缺省等价空对象；需要业务含义时由调用方先把 raw config 与运行时参数装配为 effective provider spec，再交给对应 provider 解析，例如文档路径白名单、财报 workspace root、Web 请求限制等。

包内默认 Fins providers 分为四组，均为 `enabled=false`、`allow_empty=true` 且 `workspace_root=null`。Fins provider 需要显式 workspace root，默认不参与工具发现，避免在未配置财报工作区时破坏普通 scene 装配：

| provider id | import path | 能力 |
|---|---|---|
| `financial-read-tools` | `dayu.fins.tools.provider:discover_tools` | 财报 read tools |
| `financial-download-tools` | `dayu.fins.tools.download_provider:discover_tools` | 财报 download awaiting tool |
| `financial-preprocess-tools` | `dayu.fins.tools.preprocess_provider:discover_tools` | 财报 preprocess awaiting tool |
| `financial-upload-tools` | `dayu.fins.tools.upload_provider:discover_tools` | 财报 upload awaiting tool |

启用任一 Fins provider 时，传给 provider 的 effective spec 必须包含绝对 `workspace_root`；该值可以来自 workspace overlay 的 `config.workspace_root`，也可以由 Service 调用方用当前 runtime workspace 注入。provider 不从 cwd 或环境变量猜路径。`financial-read-tools` 可额外配置 `include_read_tools` 与 `config.limits`，`config.limits` 可覆盖 `processor_cache_max_entries`、`list_documents_max_items`、`get_document_sections_max_items`、`search_document_max_items`、`list_tables_max_items`、`read_section_max_chars`、`get_page_content_max_chars`、`get_table_max_items`、`get_financial_statement_max_items` 与 `query_xbrl_facts_max_items`。`financial-upload-tools` 还必须配置非空绝对路径数组 `config.allowed_upload_roots`，上传工具只接受这些根目录下的本地文件路径。Download / preprocess / upload 能力通过独立 provider 启用，不通过 read provider 的布尔开关混合启用。

包内默认 `doc-tools` provider 指向 `dayu.tools.doc_provider:discover_tools`，默认 `enabled=false` 且 `allowed_paths=[]`。启用 Doc tools 时必须在 `config.allowed_paths` 中显式配置可访问文件或目录根；白名单为空时 provider 会 fail closed，返回空工具集合，不注册可执行文档工具。Doc provider 的 `config.limits` 可覆盖 `list_files_max`、`get_sections_max`、`search_files_max_results`、`read_file_max_chars` 与 `read_file_section_max_chars`，未配置字段使用 provider 默认值。

包内默认 `web-tools` provider 指向 `dayu.tools.web:discover_tools`，默认 `enabled=true`、`allow_empty=true`，并默认拒绝 private / local network URL。Provider 只暴露 `search_web` 与 `fetch_web_page`；`config` 可设置 `provider`（`auto` / `tavily` / `serper` / `duckduckgo`）、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel` 与 `playwright_storage_state_dir`。默认 `playwright_storage_state_dir` 指向 `workspace/.dayu/web_tools_storage_states`；只有该目录下存在目标 host 对应的 storage state 文件时，Playwright fallback 才会注入登录态。只有显式设置 `allow_private_network_url=true` 时，fetch/search URL safety 才允许内网或本地 URL。

## prompts 目录职责

`workspace/config/prompts/` 与包内 `dayu/config/prompts/` 用于放置 prompt fragments 和 scene manifests。包内默认资产按目录分为：

| 路径 | 职责 |
|---|---|
| `prompts/manifests/*.json` | ScenePrepare schema v1 scene manifest |
| `prompts/base/*.md` | 多个 scene 复用的基础 prompt fragment |
| `prompts/scenes/*.md` | 单个 scene 的场景 prompt fragment |

Scene manifest 由 `dayu.runtime.scene_prepare` 解释；ConfigLoader 不读取、拼接或渲染 scene manifest。`prompts/tasks/`、contract 文件、workflow 产物和未被 scene manifest 直接引用的模板不属于当前包内默认资产范围。

Scene manifest 第一版是单 Run 场景装配输入。允许的顶层字段固定为 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments` 与 `context_slots`。调用方显式传入 manifest root、prompt asset root、typed context slot values 与可用工具目录；ScenePrepare 只读取 manifest 直接引用的 fragments，执行确定性的文本替换，并输出 system messages、已拼接的 system prompt、工具选择结果、model hints、typed agent policy override、fragment refs、source refs 与 content digest。

`conversation_compaction` 是会话压缩专用 scene。该 scene 使用一个 required fragment 作为 compactor system prompt，并在 scene 的 `agent_policy` block 中声明 compactor AgentPolicy。user prompt template 由 execution profile 的 `compactor_baseline.user_prompt_template_path` 指向 prompt asset；template 使用 `<<compaction_request>>` 作为运行期请求数据块占位符，该占位符不是 ScenePrepare context slot，不能写成 `{{...}}`。

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
