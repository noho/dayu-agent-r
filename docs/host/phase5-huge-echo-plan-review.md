# Host P5 huge_echo Plan Review

## 结论

有条件通过。

本次 P5 plan 修订的动机成立：用户新目标不是继续验证旧的 `double_echo` 临时方向，而是用真实
`mimo-v2.5-pro-plan` provider 触发 LLM tool calling，调用公共
`@tool(..., truncate=ToolTruncateSpec(...))` 声明的 `huge_echo`，并在同一 Host 事实链路中跑通
ToolRuntime truncate / cursor / `fetch_more`。当前 plan 已基本准确反映该目标，也没有把 fake provider 或
`utils/host_smoke_tools.py` 当作当前主证明。

通过条件是：实现与 code review 必须直接证明 real-provider smoke 的 gating / stream control 的确把成功
`fetch_more` 放在 owner run terminal 前，而且不绕过 Engine / Agent tool loop；同时必须固定
`mimo-v2.5-pro-plan` provider 配置真源，避免 smoke helper 与 `dayu/config/llm_models.json` 之间的配置漂移变成
语义错位。

## Findings

### P2 重要：[已修订] real-provider gating 是可行方向，但实现必须证明暂停点在 terminal 前且不绕过 Engine tool loop

状态：非阻断，实现 gate。

修订状态：已写回 `docs/host/phase5-plan.md` 的文件级改动清单、ToolRuntime / EngineWorker / Engine 边界、
手工 smoke 要求、Code review gate 与停止条件。P5 plan 已要求 smoke 输出和测试 / 人工检查能直接观察
cursor facts、pre-terminal `fetch_more completed`、terminal cursor 的先后关系，并证明 `via_engine_tool_loop` /
`executor_execute_called` 等字段来自实际观测而非脚本常量。

直接证据：

- `docs/host/phase5-plan.md:132-154` 已把主路径改成：模型调用 `huge_echo` 后，ToolRuntime 先 append
  truncation / cursor facts，然后在 final terminal 前暂停，Host public `get_tool_fetch_more_handle` /
  `fetch_more_tool_result` 成功补读，最后再释放 final terminal。
- `docs/host/phase5-plan.md:562-567` 明确 fake provider / fake LLM 在 final terminal 前暂停，手工 smoke 用
  gating / stream control 达到同等时序。
- `docs/host/phase5-plan.md:585-587` 与 `docs/host/phase5-plan.md:697-698` 要求真实模型若太快 final，harness 必须
  先补读再允许 terminal；直接 final、未调用 `huge_echo` 或调用其它工具都要失败。
- 当前 Engine 实现中，工具执行完成后会立即 yield `TOOL_RESULT_ACCEPTED`，随后把 tool message 注入下一轮
  Runner 输入：`dayu/engine/agent.py:497-525`、`dayu/engine/agent.py:1002-1093`。如果实现只在 smoke 侧“观察到
  cursor 后再抢 fetch_more”，真实 provider 很可能已经进入下一轮 Runner 并 append terminal。

影响：

plan 的时序方向正确，且已经把无法 terminal 前成功补读列为停止条件。但 real-provider 路径不是 fake provider，
不能只依赖 prompt 或事件消费速度。若 gating 实现落在 terminal 之后，P5 会退化成只证明 `run_terminal` typed
failure；若 gating 通过手写 tool facts、替换 scripted WorkerProxy 或跳过 `ToolExecutor.execute` 实现，又会破坏 P5
要证明的真实链路。

实现 gate：

- code review 必须看到明确暂停点，例如 Host 内部测试装配在 `ToolRuntimeToolExecutor -> InMemoryToolRuntime`
  产生 cursor facts 后、Engine 注入 tool result 并进入下一轮 provider final 前暂停。
- 暂停机制只能服务 smoke/test orchestration，不得新增 Host public governance API，不得把 gating 放进 Engine 协议状态机。
- smoke 输出中的 `via_engine_tool_loop=True` / `executor_execute_called=True` 必须来自实际观测，而不是脚本常量。
- 如果只能在 terminal 后补读，或只能用 fake provider / scripted WorkerProxy 冒充 real-provider 成功，应按
  `docs/host/phase5-plan.md:811-814` 停止。

### P3 中：[已修订] `mimo-v2.5-pro-plan` 配置真源需要在实现中固定，避免 helper 配置和模型配置漂移

状态：非阻断，实现 gate。

修订状态：已写回 `docs/host/phase5-plan.md` 的文件级改动清单、实现步骤、手工 smoke 要求、Code review gate
与停止条件。P5 plan 已固定 `dayu/config/llm_models.json` 的 `mimo-v2.5-pro-plan` 为配置真源，要求复用项目当前
模型配置入口 / 解析逻辑；若与 `utils/smoke_async_agent_providers.py` 既有同名 case 的 provider_request 存在差异，
必须以配置真源为准或在 smoke 输出与 review 中显式说明。

直接证据：

- `dayu/config/llm_models.json:1012-1026` 的 `mimo-v2.5-pro-plan` 配置包含 endpoint、model、
  `MIMO_PLAN_API_KEY` header、`supports_stream=true`、`supports_tool_calling=true`、`supports_stream_usage=false`。
- 同一配置中 provider request 为 `mimo_thinking enabled=false`：`dayu/config/llm_models.json:1057-1060`。
- 既有 `utils/smoke_async_agent_tool_call.py:214-223` 的同名 case 使用相同 env / endpoint / model，但
  `MimoThinkingExtension(enabled=True)`。
- `docs/host/phase5-plan.md:249-255` 要求从现有 provider case 读取 endpoint/model/key 配置；
  `docs/host/phase5-plan.md:691-695` 又要求复用现有 smoke 脚本中的 Mimo provider 配置口径。

影响：

这不阻断 plan，因为 endpoint、model、env 和 tool calling capability 的关键目标是一致的。但用户明确要求读取
`dayu/config/llm_models.json` 中的 `mimo-v2.5-pro-plan` 配置；如果实现实际复用旧 smoke helper 的
provider_request 开关，就可能出现“文档声称使用模型配置，实际请求 payload 使用 helper 硬编码”的 semantic vs
implementation mismatch。该差异也会让后续失败诊断变模糊：到底是模型 tool calling、thinking 开关，还是 smoke
装配本身出了问题。

实现 gate：

- P5 smoke 应明确选一个真源。更稳妥的是以 `dayu/config/llm_models.json` 的 `mimo-v2.5-pro-plan` 为真源，旧 smoke
  helper 只可作为 env / endpoint / model 口径参考。
- 输出摘要应包含 provider case、model、endpoint 摘要、`supports_tool_calling` 与 provider request 开关摘要，但不得输出
  key、headers 或完整 payload。
- 若实现故意沿用 helper 中的 `MimoThinkingExtension(enabled=True)`，必须在 review 中说明这是有意差异，并证明没有背离
  “真实 `mimo-v2.5-pro-plan` provider 配置”这个用户目标。

## 复核要点

### 1. 是否准确反映用户新目标

是。

`docs/host/phase5-plan.md:24-36` 已把手工 smoke 主目标写成真实调用 `mimo-v2.5-pro-plan`，由模型通过 LLM
tool calling 调用 `huge_echo`，并且工具调用必须经过 Engine tool loop、`ToolExecutor.execute`、
`ToolRuntimeToolExecutor`、`InMemoryToolRuntime` 与 `huge_echo` executor。

`docs/host/phase5-plan.md:196-224` 已把 `huge_echo` 绑定到公共
`@tool(..., truncate=ToolTruncateSpec(...))` declaration 能力，而不是局部 utils registry。

### 2. double_echo / `utils/host_smoke_tools.py` 是否仍是当前目标

未发现当前目标残留。

`docs/host/phase5-huge-echo-plan-note.md` 与 `docs/host/migration-plan.md` 都明确旧 `double_echo` 临时方向废弃。
`docs/host/phase5-plan.md:284-286` 要求不新增或保留 `utils/host_smoke_tools.py`；当前文件扫描也确认
`utils/host_smoke_tools.py` 不存在。旧 review 文档中的 `double_echo` 只作为历史说明出现，且已标明不能作为当前通过证据。

### 3. fetch_more 时序是否可执行

计划层可执行，但实现必须按 P2 finding 验证。

当前 Host 契约仍是 terminal 后不追加补读事实；plan 已把成功 `fetch_more` 放到 terminal 前，并把 terminal 后补读限定为
`run_terminal` typed failure、`denied=False`、`event_cursor=None`、EventLog count unchanged。这个口径和
`InMemoryToolRuntime` / `RunEventStore` 的现有契约一致。

### 4. fake provider 边界是否清楚

清楚。

`docs/host/phase5-plan.md:169-178`、`docs/host/phase5-plan.md:426-430`、`docs/host/phase5-plan.md:582-587` 已区分：
CI / integration 可以 fake provider 输出，但手工 smoke 主路径不能 fake 成功；缺 `MIMO_PLAN_API_KEY`、缺 model 或
endpoint 必须 clear failure 且非零退出。

### 5. ToolDefinition 是否泄漏给 Engine

计划已守住边界。

`docs/host/phase5-plan.md:204-217` 与 `docs/host/phase5-plan.md:421-425` 明确 `ToolDefinition` /
`ToolBundle` 是 Host 装配输入，Engine / Runner 只能接收 `ToolSchema` tuple，不能接收 `ToolTruncateSpec`、
display metadata、tags、callable 或 executor binding。当前 EngineWorker 也只把
`request.options.tool_schemas` 传入 `AgentRunRequest.tool_schemas`，见 `dayu/host/_worker.py:41-52`；Engine
effective tools 只返回 `ToolSchema` tuple，见 `dayu/engine/agent.py:1461-1467`。

### 6. real provider 要求是否和 no-full-governance P5 冲突

不冲突。

P5 仍只验证单进程、单调用方、顺序多轮 smoke，不引入 active Run admission、幂等、多进程恢复、Outbox 或
audit hard-gate。真实 provider 只作为手工 smoke 主路径；CI / 必跑 integration 仍可用 fake provider 覆盖不可联网路径。
这个拆分正好符合 no-full-governance 范围。

### 7. semantic vs implementation mismatch 风险

主要风险已被 plan 覆盖，剩余两个实现期风险见 findings：

- real-provider gating 不能只停留在文档措辞，必须证明 terminal 前成功补读。
- `mimo-v2.5-pro-plan` 的请求配置需要固定真源，避免 helper 硬编码和 `llm_models.json` 配置漂移。

## 最终判定

P5 huge_echo plan 可以进入实现，但实现完成后必须按本文两个 gate 做 code review。若 real-provider smoke 不能真实调用
`mimo-v2.5-pro-plan` 并由模型调用 `huge_echo`，或无法在 terminal 前通过 Host public path 成功 `fetch_more`，则应视为
P5 阻断，不能用 fake provider 成功替代。

## 复审结论：两个非阻断实现 gate 已写回并通过

结论：通过。

本次复审只确认两个非阻断实现 gate 是否已经写回 P5 plan 且足够清晰，不重新展开完整 P5 plan review。复审读取
`docs/host/phase5-plan.md`、`docs/host/migration-plan.md` 与本文档后确认：两个 gate 均已写回，并且已经从
“建议注意”提升为 implementation / code review / stop condition 级约束，足以指导迁移 Agent 与后续 code review。

### 1. real-provider gating gate

通过。

P5 plan 已明确要求 real-provider 主路径必须证明成功 `fetch_more completed` 发生在 final terminal 前，且证据来自真实
Engine / Agent tool loop 与 Host ToolRuntime 路径，而不是手写 facts、scripted WorkerProxy 或直接调用
`InMemoryToolRuntime.execute_tool_call()`。

直接证据：

- `docs/host/phase5-plan.md:132-154` 的主路径已经把 `pause before final terminal`、owner run 未 terminal 时
  `get_tool_fetch_more_handle` / `fetch_more_tool_result` 成功补读、释放 final terminal、terminal 后
  `run_terminal` typed failure 写进纵向链路。
- `docs/host/phase5-plan.md:437-443` 在 ToolRuntime / EngineWorker / Engine 边界处明确要求 gating /
  stream control 的暂停点在 owner run terminal 前，且证据必须来自实际事件 / wrapper 观测，不能来自脚本常量、
  手写 facts、直接调用 ToolRuntime 或 scripted WorkerProxy。
- `docs/host/phase5-plan.md:577-583` 与 `docs/host/phase5-plan.md:604-606` 在实现步骤中要求 cursor issued 后先走
  Host public fetch_more，再允许 final terminal；若真实模型直接 final、未调用工具或只能由 scripted WorkerProxy
  补造成功，smoke 必须失败。
- `docs/host/phase5-plan.md:808-814` 已把该项写入 code review gate，要求检查真实 provider tool calling、
  terminal 前 Host public fetch_more、`ToolRuntimeToolExecutor -> InMemoryToolRuntime` cursor facts、
  `fetch_more completed` cursor 早于 terminal cursor，以及 `via_engine_tool_loop=True` /
  `executor_execute_called=True` 来自实际观测。
- `docs/host/phase5-plan.md:842-847` 已把无法真实调用 provider、无法 terminal 前补读、无法证明证据来自真实
  Engine / Agent tool loop 与 ToolRuntime 路径列为停止条件。

清晰度判断：

该 gate 已足够清晰。它不仅描述目标时序，还明确了可接受证据来源、禁止的旁路、code review 检查点与停止条件。
后续实现仍需在 code review 中核验证据字段是否真由 wrapper / 事件观测产生，而不是 smoke 输出硬编码；但这是实现期
审查，不再是 plan 阻断。

### 2. `mimo-v2.5-pro-plan` 配置真源 gate

通过。

P5 plan 已明确要求 `mimo-v2.5-pro-plan` 的配置真源必须是 `dayu/config/llm_models.json` 中的同名配置，并复用项目
当前配置入口 / 解析逻辑；旧 smoke helper 只能作为差异检查或历史参考，不能静默覆盖配置真源。

直接证据：

- `docs/host/phase5-plan.md:249-255` 在文件级改动清单中固定配置真源为
  `dayu/config/llm_models.json:mimo-v2.5-pro-plan`，并要求读取 endpoint、model、headers/env、
  `supports_stream`、`supports_tool_calling`、`supports_stream_usage` 与 `provider_request`。
- `docs/host/phase5-plan.md:262-267` 要求 smoke 输出 provider case、model、endpoint 摘要、capability 与
  `provider_request` 摘要、`config_source=dayu/config/llm_models.json:mimo-v2.5-pro-plan`，并在 helper 差异存在时输出
  `helper_config_diff` 或显式说明差异理由。
- `docs/host/phase5-plan.md:597-604` 在实现步骤中要求 `--case real-provider` / `--case all` 通过项目当前模型配置入口
  读取配置，缺 key / model / endpoint / capability 时 clear failure；若旧 helper 的
  `MimoThinkingExtension(enabled=True)` 与配置真源的 `mimo_thinking enabled=false` 不一致，必须以配置真源为准或显式说明
  有意差异。
- `docs/host/phase5-plan.md:712-719` 在手工 smoke 章节具体锁定 env、case 名、endpoint、model、
  `supports_tool_calling=true`、`supports_stream_usage=false` 与 `provider_request=mimo_thinking enabled=false`，
  并禁止 helper 覆盖配置真源。
- `docs/host/phase5-plan.md:815-816` 已把配置真源与 helper 差异处理写入 code review gate。
- `docs/host/phase5-plan.md:848-849` 已把无法以 `llm_models.json` 作为配置真源、或只能静默沿用旧 helper 中不一致
  `provider_request` 列为停止条件。

清晰度判断：

该 gate 已足够清晰。计划已经同时约束配置来源、读取方式、输出摘要、helper 差异处理、code review 检查与停止条件；
后续 code review 只需核对实现是否真的复用项目配置入口 / 解析逻辑，并且没有用旧 smoke helper 的硬编码 payload
覆盖 `llm_models.json`。

### 复审后的 remaining findings

无阻断或剩余 plan finding。

两个 gate 均已写回并具备可审查性。P5 可以进入实现；实现完成后仍必须按上述 code review gate 核验真实运行证据，
不能用 fake provider、scripted WorkerProxy、手写 facts 或旧 helper 硬编码配置替代。
