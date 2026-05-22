# P12.1 后续配置讨论稿

## 文档职责

本文档只记录 P12.1 已完成后新增的 config schema、runner usage 与 token 上限讨论项。它不是设计真源；进入实现闭环前，稳定裁决必须写回 `docs/host/design.md` 与 `docs/host/implementation-control.md`。

## 已裁决待实施项

### 1. AgentPolicy 直接嵌入 execution profile

当前现象：

- `execution_profiles.json` 通过 `execution_profiles[*].agent_policy_profile_id` 引用顶层 `agent_policy_profiles`。
- 当前没有足够强的跨 execution profile 复用需求。
- 间接引用会让 execution profile baseline 不够朴素，也让 Service 装配时多一次 catalog 查找。

已裁决方向：

- 删除顶层 `agent_policy_profiles` catalog。
- 删除 execution profile 内的 `agent_policy_profile_id`。
- 每个 execution profile 直接嵌入 `agent_policy` block，作为该 execution profile 的 AgentPolicy baseline。
- `agent_policy` 必须一比一对齐当前 Host / Engine public `AgentPolicy` typed shape。
- scene manifest 如需自定义 `max_iterations` 等 AgentPolicy 参数，继续使用 scene typed `agent_policy` override，并受全局 override 白名单约束。

### 2. 彻底删除默认 `max_tokens`

当前现象：

- `models.json.runtime_hints.runner_option_hints` 中包含 `max_tokens`。
- Service assembly helper 会把该字段映射为 `RunnerCallOptions.max_tokens`，最终进入 Engine provider payload。
- 默认输出 token cap 容易导致模型回答被长度上限截断。

已裁决方向：

- 从 `models.json.runtime_hints.runner_option_hints` 中删除 `max_tokens`。
- 从 ConfigLoader 的 runner option hint schema 中删除 `max_tokens`。
- 从 Service assembly helper 的默认 RunnerCallOptions 装配路径中删除 `max_tokens` 来源。
- 进一步评估是否从 Host / Engine public contract 中删除 `RunnerCallOptions.max_tokens`；若保留，也只能作为明确的 per-run / provider adapter override，不应来自默认配置。
- OpenAI adapter 不应继续把通用字段直接等同为 Chat Completions `max_tokens`；后续如确需限制输出，应按具体 API 协议区分 `max_completion_tokens`、`max_output_tokens` 或 provider 私有字段。

### 3. usage 默认打开，Context Governance 主动使用

当前现象：

- OpenAI 兼容协议中的 usage 是 Context Governance 的重要观测输入。
- 非流式响应可直接读取 response `usage`。
- 流式响应应在支持时默认请求 usage，并把收到的 usage 交给 Context Governance 消费。
- Engine 现状已经能把 Runner usage 归一为 `usage_reported` 事件。
- Host ingest 现状已经把 `usage_reported` 写为 durable projection signal。
- Host Context Governance 现状明确把 usage 作为 post-call observation，不参与当前阈值动态调整。

已裁决方向：

- 对支持 usage 的 provider，默认开启 usage 采集。
- 流式 OpenAI 兼容请求在 `supports_stream_usage=true` 时默认发送 `stream_options.include_usage=true`。
- 非流式响应默认读取 response `usage`。
- Engine 将 usage 作为观测事件输出；usage 缺失不得导致 run 失败。
- 不把 #3 设计成 Engine / Host 大改：Engine 继续只负责如实上报 usage，不理解 Host budget。
- Host ingest 继续 durable 化 usage，并补齐后续消费所需的关联信息，例如 attempt / execution context、估算 digest 与 policy ref。
- Context Governance 主动消费 usage，但 usage 是 post-call observation，只用于估算器校准、diagnostic 与后续 Run / 后续 compaction 治理参考。
- 不用 post-call usage 回头修改当前已经完成的 dispatch decision；当前 Run 的 admission 仍由 pre-dispatch estimator、provider context overflow 与 reactive compaction 负责。
- usage 缺失、provider 不支持 usage 或 usage 字段格式异常都不得导致 Run 失败。
- config 不提供 `usage_enabled` / `collect_usage` / `include_usage` 这类 override；Service、scene 与 execution profile 也不覆盖 usage 采集行为。
- 暂不引入独立 `supports_usage` 字段；流式 usage 只由 `models.json.supports_stream_usage` 表达，非流式响应如果 provider 返回 `usage`，Engine 默认读取。

### 4. execution profile 按场景显式分档

当前现象：

- 常见财报 Agent 场景至少需要适配 256K 与 1M 两类 context window。
- 不同 Service 场景对响应速度、记忆预算、compaction 激进程度的偏好不同。
- 自动根据 `models.context_window_tokens` 隐式切换 execution profile 会隐藏 Service 的业务决策。

已裁决方向：

- `execution_profiles.json` 可以定义多份 profile，例如 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`。
- Service 根据业务场景、响应速度和 effective model 显式选择 execution profile。
- Service assembly helper 不根据 `models.context_window_tokens` 隐式切换 execution profile。
- Helper 只做兼容性校验与诊断：例如 1M profile 搭配 256K 模型时 fail fast 或输出明确 diagnostic；256K profile 搭配 1M 模型可允许但提示使用较保守策略。
- 若需要机器可读约束，可在 profile 中增加 `context_window_class` / `min_context_window_tokens` 一类字段；该字段只用于校验，不用于自动选择。

## 当前倾向

- 默认配置不使用输出 token 上限控制模型行为。
- 输出长度治理优先由 Host / Engine 的迭代、fallback、Context Governance、tool truncation 与 artifact 流程完成。
- usage 是治理观测信号，应尽量采集、尽量使用，但不能成为强一致依赖。
- execution profile 是 Service 显式选择的运行策略，不由 helper 根据模型窗口隐式切换。
