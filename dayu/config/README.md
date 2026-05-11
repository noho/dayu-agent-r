# Dayu 配置说明

本手册只说明当前 `dayu/config/` 中已经存在的默认配置，以及它们与
`workspace/config/` 的覆盖关系。Engine 与领域能力的内部机制不在这里展开。

## 配置层级

Dayu 配置分两层：

1. 包内默认配置：`dayu/config/`
2. 工作区覆盖配置：`workspace/config/`

读取规则是：优先使用 `workspace/config/*`，缺失时回退到
`dayu/config/*`。因此日常运行不应直接修改包内默认配置，项目级模型、
超时、API key 占位符和运行参数应放在 `workspace/config/`。

当前 `dayu.config` 不提供公共 Python loader，也不提供
`llm_models.json -> RunnerSpec` 的统一模型配置 adapter。模型字段、
`provider_request` 等业务 schema 由各调用入口在自身边界内解释。

## 当前文件

```text
dayu/config/
├── README.md
├── llm_models.json
└── run.json
```

`llm_models.json` 定义默认模型入口和 provider 请求扩展；`run.json`
定义运行时默认参数与工具限额。

## llm_models.json

顶层每个非 `_` 开头的键是一套模型配置。当前默认配置只声明
OpenAI-compatible runner 形态。

常用字段：

| 字段 | 含义 |
|---|---|
| `runner_type` | Runner 类型，当前默认配置使用 `openai_compatible` |
| `name` | 配置名称 |
| `endpoint_url` | Chat completions endpoint |
| `model` | Provider 模型 ID |
| `headers` | HTTP header 模板，支持 `{{ENV_VAR}}` 占位符 |
| `provider_request` | Provider 私有请求扩展，配置 schema 与 Engine contract 对齐 |
| `timeout` | 单次模型请求默认超时秒数 |
| `stream_idle_timeout` | SSE 字节流空闲 hard timeout 秒数 |
| `stream_idle_heartbeat_sec` | SSE 空闲诊断日志间隔秒数 |
| `supports_stream` | 是否支持流式输出 |
| `supports_tool_calling` | 是否支持工具调用 |
| `supports_stream_usage` | 流式请求时是否发送 `stream_options.include_usage=true` |
| `max_context_tokens` | 模型最大上下文窗口；Phase 5 context budget 使用 |
| `description` | 面向配置阅读者的模型说明 |
| `runtime_hints.temperature_profiles` | 不同 scene / 任务类别的温度建议 |

禁止在默认配置中使用开放 `extra_payloads` 弱类型配置袋。Provider 私有参数
必须放入 `provider_request`，其配置 schema 与 Engine contract 对齐。
当前 `dayu.config` 不负责构造 `RunnerSpec.provider_request`；具体解析由消费方
在自身边界内完成。`utils/` 下的人工 smoke 脚本遵循脚本内固定
`ProviderCase` 的范式，不作为配置 adapter。

### provider_request

当前支持的 `provider_request.type`：

| type | 对应 Engine contract | 字段 |
|---|---|---|
| `openai_reasoning` | `OpenAIReasoningExtension` | `reasoning_effort` |
| `anthropic_thinking` | `AnthropicThinkingExtension` | `enabled`、`budget_tokens` |
| `deepseek_thinking` | `DeepSeekThinkingExtension` | `enabled`、`reasoning_effort` |
| `mimo_thinking` | `MimoThinkingExtension` | `enabled` |
| `gemini_thinking` | `GeminiThinkingExtension` | `thinking_budget`、`include_thoughts`、`thinking_level` |
| `qwen_thinking` | `QwenThinkingExtension` | `enable_thinking`、`thinking_budget` |

字段缺省表示“不传给 provider”。只有 provider 文档明确把 `0` 定义为
显式关闭或显式预算值时，才应在配置中写 `0`。

示例：

```json
{
  "gpt-5.4-thinking": {
    "runner_type": "openai_compatible",
    "name": "gpt-5.4-thinking",
    "endpoint_url": "https://api.openai.com/v1/chat/completions",
    "model": "gpt-5.4",
    "headers": {
      "Authorization": "Bearer {{OPENAI_API_KEY}}",
      "Content-Type": "application/json"
    },
    "provider_request": {
      "type": "openai_reasoning",
      "reasoning_effort": "high"
    },
    "timeout": 3600,
    "stream_idle_timeout": 120.0,
    "stream_idle_heartbeat_sec": 10.0,
    "supports_stream": true,
    "supports_tool_calling": true,
    "supports_stream_usage": true,
    "max_context_tokens": 1050000
  }
}
```

## run.json

`run.json` 提供运行时默认值。当前主要分区：

| 分区 | 含义 |
|---|---|
| `runner_running_config` | Runner 诊断、SSE 调试和工具超时默认值 |
| `agent_running_config` | Agent 最大迭代、fallback、重复工具调用、continuation / compaction 参数 |
| `doc_tool_limits` | 文档工具默认读取和列表限制 |
| `fins_tool_limits` | 财报工具默认读取和列表限制 |
| `web_tools_config` | Web 工具 provider、超时、抓取和浏览器配置 |

这些配置属于默认值；具体项目应在 `workspace/config/run.json` 中覆盖。

## API Key

默认模型配置只写环境变量占位符，不保存密钥明文。例如：

```json
"headers": {
  "Authorization": "Bearer {{DEEPSEEK_API_KEY}}",
  "Content-Type": "application/json"
}
```

运行前在 shell 或部署环境中设置对应环境变量。
