# Dayu 配置说明

本手册只说明当前 `dayu/config/` 的默认配置、`workspace/config/` 覆盖关系与 prompts 目录职责。Engine、Host、Service 和财报领域能力的内部机制不在这里展开。

## 配置层级

Dayu runtime assembly 配置分两层：

1. 包内默认配置：`dayu/config/`
2. 工作区覆盖配置：调用方显式传入的配置目录，常用位置是 `workspace/config/`

`dayu.runtime.config_loader.ConfigLoader` 默认加载包内配置；调用方可以显式传入 workspace 配置目录。ConfigLoader 不猜测 workspace 路径，不解析环境变量，不替换 secret，不脱敏，也不 import Host、Engine、Service、UI、Fins 或具体业务工具包。

覆盖规则按配置文件类型分别执行：

- 顶层 map 按稳定 id 合并。
- workspace 中与包内同 id 的记录会整条替换包内记录。
- 不做隐式 deep merge；复用配置只能用显式 `extends`。
- `extends` 只允许单继承；循环、多父项、父项缺失、缺字段和非法类型都会加载失败。

## 当前文件

```text
dayu/config/
├── README.md
├── execution_profiles.json
├── host_runtime.json
├── models.json
└── tool_discovery.json
```

旧 `llm_models.json` 和 `run.json` 已删除，不再提供兼容读取路径。

## models.json

`models.json` 是模型目录，只表达 provider / model 能力和请求基础参数。顶层字段为 `models`，每条记录的 key 必须与 `model_id` 一致。

常用字段：

| 字段 | 含义 |
|---|---|
| `model_id` | 模型配置稳定 id |
| `runner_kind` | Runner 类别，当前默认配置使用 `openai_compatible` |
| `provider` | provider 标识 |
| `model` | provider 模型名 |
| `endpoint` | provider endpoint |
| `api_key_ref` | API key 引用，按字符串原样保留 |
| `headers` | 请求 headers，按配置原样保留 |
| `supports_tool_calling` | 是否支持工具调用 |
| `supports_stream` | 是否支持流式输出 |
| `supports_stream_usage` | 是否支持流式 usage |
| `default_timeout_seconds` | 默认请求超时秒数 |
| `max_retries` | 默认最大重试次数 |
| `sse_idle_timeout_seconds` | SSE 空闲超时秒数 |
| `sse_heartbeat_seconds` | SSE 空闲诊断 heartbeat 秒数 |
| `provider_request_extension` | provider 私有请求扩展，按 JSON 原样保留 |
| `context_window_tokens` | 模型上下文窗口 token 数 |

temperature profile 不属于模型能力，不放在 `models.json`。

## execution_profiles.json

`execution_profiles.json` 表达 Service / composition root 生成完整执行输入所需的 profiles。顶层字段包括：

| 字段 | 含义 |
|---|---|
| `default_profile_id` | 默认 execution profile id |
| `profiles` | 普通 Run、compactor、context budget、memory projection、truncation 的完整基线 |
| `runner_options_profiles` | temperature、max tokens、top-p、stream 等 Runner 调用参数 profile |
| `agent_policy_profiles` | Agent loop、continuation、工具超时、fallback 等 policy profile |
| `runner_hints` | scene runtime runner hint 可覆盖字段 |
| `agent_hints` | scene runtime agent hint 可覆盖字段 |

`ordinary`、`compactor`、`context_budget`、`memory_projection` 和 `truncation` 都是完整 typed records。`runner_hints` 和 `agent_hints` 只表达允许覆盖的字段；最终仍由 Service 产出完整 `RunnerSpec`、`RunnerCallOptions` 与 `AgentPolicy`，不得把 profile id、hint id 或 raw config fragment 传给 Host。

## host_runtime.json

`host_runtime.json` 表达 Host opener 的部署默认值。顶层字段为 `default_runtime_id` 和 `runtimes`。

每条 runtime 记录覆盖：

- Host durable store 与 artifact roots。
- SQLite path 与 busy timeout。
- runtime lane DB、默认 lane 与 lane 容量。
- `worker_factory_kind`。
- `dispatch_poll_interval_seconds`。
- `memory_projection_catch_up_batch_size`。
- `truncation_manager_enabled`。
- `prompt_asset_root` 与 `scene_manifest_root`。

这些配置都是 `open_host(options)` construction-time assembly inputs 的来源，不是单个 Run 的 override。

## tool_discovery.json

`tool_discovery.json` 只表达 ToolsDiscovery provider specs。ConfigLoader 只读出 typed provider specs，不 import provider，也不做工具发现。

provider 字段：

| 字段 | 含义 |
|---|---|
| `provider_id` | provider spec 稳定 id |
| `import_path` | 显式 `module:attribute` provider callable |
| `entry_point` | package entry point provider callable |
| `source_kind` | 来源类别，使用工具来源公共契约值 |
| `source_id` | 来源标识 |
| `enabled` | 是否启用 provider |
| `allow_empty` | 是否允许 provider 返回空工具集合 |

`import_path` 与 `entry_point` 必须二选一。

## prompts 目录职责

`workspace/config/prompts/` 与包内 prompt asset 目录用于放置 prompt fragments 和 scene manifests。Scene manifest 由 `dayu.runtime.scene_prepare` 解释；ConfigLoader 不读取、拼接或渲染 scene manifest。

Scene manifest 第一版是单 Run 场景装配输入，必含 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`runtime`、`conversation`、`tool_selection`、`defaults`、`fragments` 与 `context_slots`。`model.default_name` 表达模型配置 hint，`model.temperature_profile` 表达可选 runner options profile hint；二者都只由 Service / composition root 映射为完整执行输入。调用方显式传入 manifest root、prompt asset root、typed context slot values 与可用工具目录；ScenePrepare 只读取 manifest 直接引用的 fragments，执行确定性的 `{{slot_name}}` 文本替换，并输出 system messages、工具选择结果、model / runtime / conversation hints、fragment refs、source refs 与 content digest。

Scene manifest 不表达 workflow step graph、next scene、artifact store、parser、retry / replay / stop policy、failure classification 或 checkpoint / resume。多 Run 财报流程属于 Service workflow 或后续 typed skill orchestration，不属于 prompt asset schema。

## 最小 workspace 覆盖示例

只覆盖一个模型时，workspace 文件应提供该模型的完整记录：

```json
{
  "models": {
    "deepseek-chat": {
      "model_id": "deepseek-chat",
      "runner_kind": "openai_compatible",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "endpoint": "https://api.deepseek.com/chat/completions",
      "api_key_ref": "DEEPSEEK_API_KEY",
      "headers": {
        "Authorization": "Bearer ${DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
      },
      "supports_tool_calling": true,
      "supports_stream": true,
      "supports_stream_usage": true,
      "default_timeout_seconds": 3600.0,
      "max_retries": 2,
      "sse_idle_timeout_seconds": 120.0,
      "sse_heartbeat_seconds": 10.0,
      "provider_request_extension": {
        "type": "deepseek_thinking",
        "enabled": false
      },
      "context_window_tokens": 128000
    }
  }
}
```

如果只想复用包内记录并改少量字段，应新增一个 id 并用 `extends` 显式继承；不要指望 workspace partial record 与包内同 id 记录 deep merge。
