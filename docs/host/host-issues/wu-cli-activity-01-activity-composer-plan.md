# WU-CLI-ACTIVITY-01 activity / composer plan

## 1. Goal / motivation / success signal

本 Work Unit 面向 GitHub Issue #144：`dayu-cli prompt` 与
`dayu-cli interactive` 当前只在 Run 终态后输出 final answer / failure /
cancel，长时间运行期间用户缺少可理解的运行态 activity 反馈。动机成立：
这不是 debug log 缺口，而是 CLI UI 对 Host public session live watch 的消费
缺口。

Issue #144 当前仍为 open，验收信号包含：

- `prompt` 长时间运行时显示可理解的 activity 摘要，并在终态输出 final answer。
- `interactive` 多轮运行时 activity 与每轮 final answer 不乱序。
- 用户可以隐藏 / 展示 activity 区域，隐藏后 final answer 仍可正常阅读。
- 工具调用 start / finish / failure 有有界业务摘要。
- API key 仍受保护，业务诊断信息不因泛化脱敏而失去分析价值。

目标：

- `prompt`：补运行态 activity 展示、隐藏 / 展示切换、运行中 cancel 语义；不做
  composer、不做 prompt 历史、多行或编辑器。
- `interactive`：补运行态 activity，并把输入态升级为 composer，支持多行、
  历史搜索、外部编辑器和明确快捷键。
- Host session live watch 的 `HostEvent` 必须准确表达 public event identity /
  activity；CLI 只消费 Service 投影后的 public activity，不读取 Host durable
  internals。
- 事件链路保持 Runner event -> Engine event -> Host EventLog / Host event；每层
  可以新增本层 event，但不能让上层绕过下层 public contract。
- stdout 保持 final answer / machine-consumable result 清晰；activity 优先走
  stderr。

成功信号：

- `dayu-cli prompt "..."` 在 TTY 中能在 final answer 前显示运行态 activity，用户
  可用快捷键隐藏 / 展示 activity，终态 final answer 仍只写 stdout。
- `dayu-cli interactive` 每轮输入态由 composer 收集输入；运行态 activity 与本轮
  final answer 不乱序。
- Ctrl+J 换行；Ctrl+T 切换 activity 可见性；Ctrl+C / Esc 在运行态请求 cancel
  当前 run；连续 Ctrl+C 本地退出。
- interactive composer 支持历史搜索与外部编辑器，不把这两项推到后续 WU。
- 工具调用 start / finish / failure 通过 Host public activity view 展示有界业务
  摘要；不展示 hidden chain-of-thought，不把 stdlib logging、debug log、Tool
  Trace analyzer 或 Fins direct event stream 当作 activity UI。

## 2. Non-goals / scope boundary

- 不展示模型隐藏 chain-of-thought、provider reasoning 原文或 raw
  `reasoning_delta`。
- 不新增 `prompt` composer，不做 prompt 历史、多行或编辑器。
- 不读取 Host durable internals、EventLog row、Tool Trace hot/cold 表、
  projection checkpoint、payload descriptor、artifact、payload ref、digest、
  cursor 或 run-scoped internal event reader。
- 不从 outbox terminal 反推运行过程；outbox 只用于现有 terminal fallback。
- 不改变 Fins direct event stream 已完成语义；Fins direct 的 `FinsEvent` 与本 WU
  的 Host activity 是不同 stream 概念。
- 不改 durable schema、EventLog canonical fact 语义或 Host / Engine 状态机。
- 不要求 Engine 依赖 `ToolDefinition` / `ToolBundle` 或 Host public `HostEvent`
  类型；Engine 仍只产出一次 run 的 Engine event。
- 不要求 CLI 读取 payload_ref、payload_digest、tool_call_id、Tool Trace、logging
  或 Host 内部 diagnostic DTO。
- 不占用 Ctrl+O。Codex manual 已确认 Ctrl+O 是 copy latest completed output，
  不是 activity toggle。

## 3. First-principles judgment and direct code evidence

第一性原理判断：

- 用户可见 activity 的真源应来自当前 Session 的 public live watch，而不是日志或
  durable 内部表。日志是系统诊断通道，不表达 UI activity；durable internals 是
  Host 治理真源，不应被 CLI 越层读取。
- CLI 的职责是展示、输入收集和用户动作触发；Service 的职责是业务入口、场景装配
  和调用 Host；Host 的职责是生命周期、取消、EventLog / public event truth；
  Engine 只提供一次 run 的 `EngineEvent stream`。
- 当前问题根因不是 Engine event 丢失，而是 Host session live watch 的 public
  projection 裁掉了非终态事件身份和 activity payload。
- 用户已裁决允许修改 event 相关 contracts。因此 BQ-1 已 resolved；本计划不再把
  Host public progress payload 作为 blocking open question，而是把 public activity
  event contract 作为 Slice A。

直接代码证据：

- [dayu/cli/commands/prompt.py](/Users/leo/workspace/dayu-agent-r/dayu/cli/commands/prompt.py:261)
  当前 `_execute_prompt_on_existing_session(...)` submit 后只取得 terminal；
  [dayu/cli/commands/prompt.py](/Users/leo/workspace/dayu-agent-r/dayu/cli/commands/prompt.py:272)
  随后调用 `render_prompt_terminal_result(terminal)`。
- [dayu/cli/commands/interactive.py](/Users/leo/workspace/dayu-agent-r/dayu/cli/commands/interactive.py:396)
  当前 interactive 输入用 `input_reader(INTERACTIVE_INPUT_PROMPT)` 单行读取；
  [dayu/cli/commands/interactive.py](/Users/leo/workspace/dayu-agent-r/dayu/cli/commands/interactive.py:402)
  每轮 submit 后等待 terminal；
  [dayu/cli/commands/interactive.py](/Users/leo/workspace/dayu-agent-r/dayu/cli/commands/interactive.py:414)
  只渲染 terminal result。
- [dayu/service/entrypoint_runtime.py](/Users/leo/workspace/dayu-agent-r/dayu/service/entrypoint_runtime.py:401)
  `submit_entrypoint_turn_and_wait(...)` 在 submit 前 attach watcher；
  [dayu/service/entrypoint_runtime.py](/Users/leo/workspace/dayu-agent-r/dayu/service/entrypoint_runtime.py:580)
  `_wait_for_terminal(...)` 只循环寻找 live terminal 或 outbox terminal；
  [dayu/service/entrypoint_runtime.py](/Users/leo/workspace/dayu-agent-r/dayu/service/entrypoint_runtime.py:616)
  `_drain_available_watcher_items(...)` 对非 terminal progress 只消费不投影给 CLI。
- [dayu/host/api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/api.py:2515)
  `HostEventView` 已有 `event_class` / `event_type` 给 `stream_run_events`；
  [dayu/host/api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/api.py:2973)
  public `HostEvent` 只有 identity、kind、terminal/final/error/cancel 字段，没有
  `event_class`、`event_type` 或 activity view。
- [dayu/host/read_api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/read_api.py:821)
  `_host_event_from_row(...)` 把非 terminal EventLog row 全部投影为
  `HostEventKind.PROGRESS`；
  [dayu/host/read_api.py](/Users/leo/workspace/dayu-agent-r/dayu/host/read_api.py:840)
  progress event 的 `error_message=None`、`cancel_reason=None`，裁掉
  `event_class` / `event_type` / activity payload。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:987)
  `TOOL_AWAITING` 会确认并写入 Host waiting 相关 canonical events；
  [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:1010)
  `PROVIDER_PROTOCOL_ERROR` 会写入 Host diagnostic event。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4677)
  到
  [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4698)
  `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_REQUESTED`、
  `TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE` 都属于 preview event。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4728)
  到
  [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4770)
  preview payload 已为 tool events 写入安全摘要：`tool_name`、`outcome_kind`、
  `tool_call_count`、`completed_count`、`failed_count`、`cancelled_count`、参数
  digest 等；计划不需要让 CLI 读取 raw payload。
- [dayu/contracts/tool_declaration.py](/Users/leo/workspace/dayu-agent-r/dayu/contracts/tool_declaration.py:68)
  `ToolDisplayInfo.name` 是用户友好的工具展示名称；
  [dayu/contracts/tool_declaration.py](/Users/leo/workspace/dayu-agent-r/dayu/contracts/tool_declaration.py:94)
  `ToolDefinition.display` 不进入 LLM schema，适合 Host-owned display metadata
  snapshot 使用。

## 4. Design document alignment

- Host / Engine 分层：`docs/host/design.md` 固定 Service / UI 的普通事件入口是
  `watch_session_events(session_id)`；`docs/engine/design.md` 固定 `EngineEvent
  stream` 不是 Host event stream，EngineEvent 不提供 Host cursor、EventLog
  sequence 或多客户端 fanout。
- 事件链路：Runner event 由 Engine 归一成 Engine event；Host ingest 把 Engine /
  Worker / ToolRuntime 事件验证、分类并写入 Host EventLog / Host event；Host
  也会新增本层 run lifecycle、waiting、compaction、diagnostic、projection signal
  events。`watch_session_events(session_id)` 返回的 `HostEvent` 必须表达 Host
  public event identity / activity，而不是 raw Engine event passthrough。
- Service / CLI 边界：Service 可以把 Host public activity view 转成 entrypoint
  runtime activity；CLI 只消费 Service 返回的 typed activity / terminal，不构造
  Engine request，不读取 Host durable internals。
- `watch_session_events`：Service submit helper 已经 attach-before-submit，符合设计
  要求；本 WU 扩展 watcher 的 non-terminal public activity 消费方式，不新增
  run-scoped public reader。
- Tool display metadata：Engine 不应依赖 `ToolDefinition` / `ToolBundle`。工具展示名
  必须由 Host 侧 effective tool metadata snapshot 或等价 Host-owned lookup 进入
  public activity；优先 `ToolDisplayInfo.name`，缺失时 fallback stable tool name。
  不得从 LLM-facing description 猜 UI 文案。
- stdout / stderr：final answer、机器可消费结果仍写 stdout；activity、cancel 提示、
  错误和 diagnostic 继续写 stderr。TTY 中可以使用动态区域；non-TTY 中默认不输出
  live activity，避免污染脚本捕获，但 terminal error/cancel 仍按现有 stderr 规则
  输出。

## 5. Public contract / API / schema / state-machine decision

本 WU 允许且必须设计 event 相关 public contract 变更；implementation gate 才能改代码。

Public contract 变更：

- 扩展 Host public `HostEvent`，保留 `HostEventKind` 的粗粒度生命周期语义：
  `PROGRESS` / `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST` 继续表达 session live
  watch 对调用方最重要的生命周期分类。
- 为 `HostEvent` 增加：
  - `event_class: HostEventClass`
  - `event_type: str`
  - `activity: HostActivityView | None`
- `HostEventClass` 必须复用 `dayu.host.api` 已有 public enum 值：
  `canonical_fact`、`preview`、`diagnostic`、`projection_signal`。不得新增同名
  enum，不得把 `HostEventClass` 与 `HostActivityKind` 混淆：前者是 EventLog row 的
  public identity class，后者是 activity 展示语义。
- `HostEvent.event_type` 必须直接复制 EventLog row 的 `event_type`。它是 public event
  identity label，不是 UI 文案、业务事实、财报事实或 activity 分类依据。
- 新增 Host public `HostActivityView`，只包含 UI / Service 安全展示字段：
  - `kind: HostActivityKind`
  - `status: HostActivityStatus`
  - `title: str`
  - `summary: str | None`
  - `severity: HostActivitySeverity`
  - `tool_name: str | None`
  - `tool_display_name: str | None`
  - `counts: HostActivityCounts | None`
- 新增窄 enum / value objects：
  - `HostActivityKind`：至少覆盖 `RUN_LIFECYCLE`、`TOOL_CALL`、`TOOL_RESULT`、
    `TOOL_BATCH`、`TOOL_AWAITING`、`CONTEXT_COMPACTION`、`PROVIDER_DIAGNOSTIC`。
  - `HostActivityStatus`：至少覆盖 `STARTED`、`IN_PROGRESS`、`COMPLETED`、
    `FAILED`、`CANCELLED`、`WAITING`、`INFO`。
  - `HostActivitySeverity`：至少覆盖 `INFO`、`WARNING`、`ERROR`。
  - `HostActivityCounts`：第一版只定义 `total: int`、`completed: int`、
    `failed: int`、`cancelled: int` 四个必填字段，全部必须是 non-negative int；
    禁止使用 `extra` dict、`dict[str, Any]`、`object` 或泛化计数容器。未来其他
    activity 需要不同计数语义时新增独立类型，不扩成 god counts。
- `HostActivityView` 不包含 payload_ref、payload_digest、cursor、Tool Trace id、
  logging id、tool_call_id、raw reasoning、raw content delta、raw provider payload 或
  Host internal row。
- terminal `HostEvent` 也必须带 `event_class` / `event_type`；`activity` 可为
  terminal-related lifecycle view 或 `None`，但不得影响现有 terminal payload validation。

Projection 规则：

- `read_api._host_event_from_row(...)` 必须从 EventLog row 的
  `event_class` / `event_type` / payload 投影 public activity allowlist。
- Allowlist 至少包含：
  - `TOOL_CALL_REQUESTED`：`TOOL_CALL` / `STARTED`，工具名来自 payload `tool_name`，
    展示名来自 Host-owned lookup，summary 只用有界安全摘要。
  - `TOOL_RESULT_ACCEPTED`：`TOOL_RESULT`，按 `outcome_kind` 映射 completed /
    failed / cancelled。
  - `TOOL_CALLS_BATCH_DONE`：`TOOL_BATCH` / `COMPLETED`，counts 来自 payload counts。
  - `TOOL_AWAITING` 与 `RUN_WAITING`：`TOOL_AWAITING` / `WAITING`，只展示等待语义
    与必要安全摘要。
  - `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、
    `CONTEXT_COMPACTION_FAILED`、`CONTEXT_COMPACTION_ATTEMPT_REJECTED`：
    `CONTEXT_COMPACTION`，不暴露 compact artifact refs。
  - `PROVIDER_PROTOCOL_ERROR`：`PROVIDER_DIAGNOSTIC` / warning 或 error，只展示
    error code / 有界 message，不暴露 raw payload ref。
  - run lifecycle events 可映射为 `RUN_LIFECYCLE`。
- 未知非终态 event 必须保留 `event_class` / `event_type`，但 `activity=None`。
- `REASONING_DELTA` 和 `CONTENT_DELTA` 都必须保留 `event_class` / `event_type`
  identity，但 `activity=None`。raw reasoning delta、raw content delta 永不投影为
  activity；final answer 仍只通过 terminal `HostEvent.final_answer` 展示。

Tool display lookup：

- 最小实现路径：Host admission 在构造 `USER_INPUT_ACCEPTED.effective_tool_set` 时，从
  当前 selected `ToolBundle.definitions` 提取 `{tool_name, display_name}`，随
  `effective_tool_set` 冻结为 Host-owned display snapshot，例如
  `effective_tool_display_names`。
- `display_name` 来源只能是 `ToolDefinition.display.name`；definition 没有 display
  metadata 时该工具可不进入 mapping，或写入与 stable `tool_name` 相同的值，由实现按
  现有 JSON 风格二选一并保持测试自洽。
- `read_api` 在投影 tool activity 时，通过当前 run/input payload 读取这个 Host-owned
  snapshot，按 stable `tool_name` lookup；缺失、工具已移除或 snapshot 不含 metadata
  时 fallback stable `tool_name`。
- 这是 `USER_INPUT_ACCEPTED` payload shape 扩展，不是 durable schema migration，不
  要新增旧库兼容读取路径。
- 该 lookup 只能由 Host public projection 使用；不得让 Engine、Service 或 CLI import
  / 读取 `ToolBundle`、`ToolDefinition` 或 Tool Trace 来获得展示名。

不变更：

- 不改 durable schema。
- 不改 EventLog canonical fact 语义。
- 不改 Host / Engine 状态机。
- 不新增 public payload reader。
- 不把 `stream_run_events` / `HostEventView` 提升为普通 Service-facing入口。

## 6. Affected files / modules

计划会改的生产文件：

- `dayu/host/api.py`：新增 `HostActivityView` 及相关强类型 enum / value object；
  扩展 `HostEvent` 的 `event_class`、`event_type`、`activity` 字段和 validation；
  更新 public exports。
- `dayu/host/read_api.py`：把 EventLog row 投影成带 event identity / activity allowlist
  的 `HostEvent`；未知事件保留 identity 且 `activity=None`。
- `dayu/host/admission.py`：在 Host admission 构造
  `USER_INPUT_ACCEPTED.effective_tool_set` 时，随 selected business tool set 冻结
  Host-owned `effective_tool_display_names` snapshot；这是 payload shape 扩展，不是
  durable schema migration。
- `dayu/service/entrypoint_runtime.py`：Service activity callback 消费 Host public
  activity view，不再局限 generic progress。
- `dayu/cli/output.py`：新增 activity renderer 或导出 activity 相关渲染 helper；保持
  现有 terminal renderer stdout / stderr 语义。
- `dayu/cli/commands/prompt.py`：接入运行态 activity renderer、Ctrl+T visibility、
  Ctrl+C / Esc cancel 语义；不加 composer。
- `dayu/cli/commands/interactive.py`：接入运行态 activity renderer；替换输入态
  `input(...)` 为 prompt_toolkit composer。
- 可新增 `dayu/cli/activity.py`：CLI 层 activity state、renderer、TTY / non-TTY
  policy、快捷键绑定的层中立实现。
- 可新增 `dayu/cli/composer.py`：interactive composer wrapper，封装 prompt_toolkit、
  历史、Ctrl+J、Ctrl+R、外部编辑器。

计划会改的测试文件：

- `tests/host/test_public_event_api.py` 或现有等价 Host public event tests。
- `tests/host/test_read_api.py` 或现有 session live watch / read projection tests。
- Host tool activity projection 测试所在文件，由 implementation agent 根据现有测试
  分布选择。
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- 如新增 composer / activity 独立模块，新增 `tests/cli/test_activity_renderer.py`、
  `tests/cli/test_interactive_composer.py`。

只读设计 / 约束文件：

- `AGENTS.md`
- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`
- `dayu/contracts/tool_declaration.py`
- `pyproject.toml`

README 触发检查：

- 修改 `dayu/host/` 后必须先阅读 `dayu/host/README.md` 的 Agent 更新约束并按需更新。
- 修改 `tests/` 后必须先阅读 `tests/README.md` 的 Agent 更新约束并按需更新。
- 若实现改变 UI / Service / Host / Agent 边界、装配方式或 public contract，必须检查
  `dayu/README.md`。
- `dayu/service/` 与 `dayu/cli/` 修改未被 AGENTS.md 明确列为 README 触发项；但若
  实际行为改变属于某 README 职责范围，implementation agent 应说明检查结论。
- 如果 `dayu/service/README.md` 存在，implementation agent 必须只读检查
  `dayu/service/entrypoint_runtime.py` 的 entrypoint behavior 变化是否影响该 README
  职责范围，并在 completion report 记录更新 / 不更新结论。
- 本 plan artifact 修改本身不触发 README 更新。

## 7. Implementation decisions

### 7.1 Host public activity event projection

- `HostEventKind` 继续表达粗粒度生命周期；不要把 tool / compaction / provider
  diagnostic 全塞进新的 kind enum。
- `HostEvent.event_class` 必须复用已有 `HostEventClass` 值：
  `canonical_fact`、`preview`、`diagnostic`、`projection_signal`。不得新增平行 enum，
  不得把它当成 `HostActivityKind`。
- `HostEvent.event_type` 直接复制 EventLog row 的 `event_type`。
- `HostEvent.event_class` / `event_type` 是 public identity / diagnostic label，用于
  诊断、审计、去重辅助和测试断言；它们不是业务事实，也不是 UI 文案。Service / CLI
  不得根据 `event_class` 做 UI 分支，例如不得写出“preview 事件显示 spinner、
  canonical_fact 事件显示历史”的逻辑；UI 只使用 `activity.kind`、`status`、`title`、
  `summary`、`severity` 等 display semantics。
- `HostActivityView` 是 Host 对 public event 的安全展示投影；Service 可以再转成
  entrypoint activity，但不重新解析 payload。
- `read_api` 内使用模块级私有 helper，例如 `_activity_from_row(...)`、
  `_tool_call_requested_activity(...)`、`_tool_result_activity(...)`、
  `_context_compaction_activity(...)`；禁止无必要嵌套函数。
- payload 解析必须是 allowlist。字段缺失或类型非法时，Host 可按 durable corruption
  现有策略抛 `HostDurableError`，或对非关键展示字段降级为 `activity=None`；implementation
  agent 必须按现有 read_api 错误处理风格选择一致策略。
- `REASONING_DELTA` 和 `CONTENT_DELTA` 都保留 identity 但 `activity=None`；raw delta
  永不投影 activity。
- terminal HostEvent validation 需要同时允许 terminal payload 和可选 activity；progress
  event 仍不得包含 terminal payload。

### 7.2 Service activity callback

- Service 在 `submit_entrypoint_turn_and_wait(...)` 增加可选 callback，例如
  `on_activity: EntrypointActivityCallback | None`。callback 接收 Service 自己定义的
  entrypoint activity DTO，不暴露 Host durable internals。
- DTO 字段只包含当前 UI 必需信息：`kind`、`status`、`run_id | None`、
  `event_sequence | None`、`dedupe_key`、`title`、`summary | None`、`severity`、
  `tool_name | None`、`tool_display_name | None`、`counts | None`。不得包含 payload
  ref、digest、cursor、Tool Trace id 或 internal projector 标识。
- `run_id`、`event_sequence`、`dedupe_key` 只能来自 public `HostEvent` 字段；
  display semantics 只能来自 `HostEvent.activity`。Service 不解析 private payload，
  也不得用 `HostEvent.event_class` / `event_type` 决定 UI kind、title、severity。
- submit 前可 emit `preparing` / `watch_attached` 类 Service-local activity；Host 接受
  followup 后 emit `run_accepted`；收到 public `HostEvent.activity` 时转发为
  entrypoint activity。
- 对未知非终态 HostEvent，Service 可以不调用 callback，或生成通用 bounded activity；
  不能根据 `event_id` 前缀、dedupe_key、event_sequence 或隐藏内部约定猜测工具事件类型。
- 对 `_WatcherFailure` 只生成有界 diagnostic activity 到 callback，不改变 terminal
  fallback 结果。

### 7.3 Renderer and TTY / non-TTY

- Activity renderer 写 stderr；terminal final answer 继续由
  `render_prompt_terminal_result(...)` / `render_interactive_terminal_result(...)` 写 stdout。
- TTY stderr：允许动态区域，activity 可折叠 / 隐藏；隐藏时保留一行短状态，不清除
  final answer。
- non-TTY stderr：默认 suppress live activity，只输出 terminal error/cancel；如果未来
  需要机器可读 activity，必须另设显式选项，不在本 WU 偷塞。
- TTY key handling 与 non-TTY SIGINT 必须分开：interactive TTY composer 才有
  prompt_toolkit key bindings；prompt non-TTY 下没有 Ctrl+T，Ctrl+C 按 SIGINT /
  local exit 语义处理，不承诺“第一次 cancel、第二次退出”的 TTY key sequence。
- renderer 必须按 dedupe key 去重，按 event_sequence 单调忽略旧事件，避免 live watch
  和 outbox terminal fallback 造成重复终态展示。

### 7.4 Run-state key handling

快捷键裁决：

- Ctrl+T：TTY running state 下 activity 隐藏 / 展示 toggle；non-TTY 下不可用。理由：
  不占用 Ctrl+O；T 可理解为 toggle，和 Ctrl+J / Ctrl+R / Ctrl+C 常见终端习惯冲突
  较低。
- Ctrl+J：interactive composer 内插入换行；Enter 提交当前 composer 内容。
- Ctrl+C：运行态第一次请求 `cancel_run(...)`；若 cancel 已发出但 terminal 未返回，
  第二次 Ctrl+C 立即本地退出 130。
- Esc：运行态等价于请求 cancel 当前 run，但不作为“连续退出”计数；避免用户误按 Esc
  直接退出整个 REPL。
- Ctrl+R：interactive composer 历史搜索。
- Ctrl+X Ctrl+E：打开外部编辑器，优先使用 `$VISUAL`，其次 `$EDITOR`，否则使用
  prompt_toolkit 默认编辑器行为；编辑器返回空白时不 submit；用户取消编辑器时不
  submit；编辑器启动失败时保留当前 draft，并在 stderr 显示 bounded diagnostic
  message（包含 stderr / 错误消息的有界摘要，不进入 stdout）。

状态机：

- `INPUT`：interactive composer 收集输入。Ctrl+J 换行，Enter submit，Ctrl+R 历史
  搜索，Ctrl+X Ctrl+E 外部编辑器，EOF 退出 0。Ctrl+C 在空输入退出 130；非空输入
  先清空 draft，下一次 Ctrl+C 退出。
- `RUNNING_VISIBLE`：已 submit，activity visible。Ctrl+T -> `RUNNING_HIDDEN`；
  Ctrl+C / Esc -> `CANCELLING_VISIBLE` 并调用 Host public cancel。
- `RUNNING_HIDDEN`：已 submit，activity hidden。Ctrl+T -> `RUNNING_VISIBLE`；
  Ctrl+C / Esc -> `CANCELLING_HIDDEN`。
- `CANCELLING_VISIBLE` / `CANCELLING_HIDDEN`：cancel 已请求，继续等 terminal；
  收到 terminal event 立即进入 `TERMINAL_RENDERING`，terminal 优先于第二次 Ctrl+C；
  Ctrl+C 只在尚未接收 terminal 时本地退出 130；Ctrl+T 仍可切换可见性。
- `TERMINAL_RENDERING`：只渲染 terminal result；prompt 退出，interactive 回到
  `INPUT` 或 fatal 退出。

跨 slice 状态机验证：

- implementation 可新增共享状态 transition helper，或在 Slice C / D / E 通过明确的
  集成测试覆盖同一状态机；不要为了抽象而引入与 CLI 无关的 runtime 层状态机。
- 必须覆盖 terminal-before-cancel 和 cancel-before-terminal ordering：CANCELLING 中
  terminal 先到达时渲染 terminal；cancel 请求先发出且 terminal 后到达时继续等待并渲染
  terminal；第二次 Ctrl+C 不能覆盖已接收 terminal。

### 7.5 Interactive composer

- 使用现有依赖 `prompt_toolkit>=3.0.0`，不新增运行依赖。
- 封装为 CLI 层小模块，避免把 prompt_toolkit 类型扩散到 Service / Host。
- composer 返回纯 `str`，调用方仍执行 `strip()` 和空输入跳过；多行内容保留内部换行，
  最终 user prompt 是 stripped text。
- 历史只保存在当前 interactive 进程内，或使用 prompt_toolkit in-memory history；不得
  引入 durable history store。
- 外部编辑器只影响当前 draft，不写 workspace 临时脚本；若 prompt_toolkit 内部需要
  临时文件，沿用其默认安全机制。
- 外部编辑器返回空白或用户取消时不 submit；启动失败时保留 draft 并显示 stderr
  diagnostic，用户可继续编辑同一 draft。

### 7.6 Cancel semantics

- submit 已 accepted 后，cancel 必须继续走 `cancel_entrypoint_run_and_wait(...)` /
  Host public `cancel_run(...)`，不得直接 cancel worker task 伪造用户 cancel fact。
- Run accepted 前收到 Ctrl+C：保持现有语义，返回 130，不写用户 cancel fact。
- Run accepted 后收到 Ctrl+C / Esc：记录当前 accepted run id，发起 Host cancel，等待
  terminal；第二次 Ctrl+C 本地退出，不能改写 Host 后续事实。
- CANCELLING 状态下 terminal 已先到达时，立即进入 terminal rendering；cancel 快捷键或
  第二次 Ctrl+C 不得覆盖 terminal result。

## 8. Small implementation slices

### Slice A - Host public activity event contract

Objective：扩展 session live watch 的 public `HostEvent`，让它保留 EventLog row 的
public identity 并携带安全 activity view，修复非终态事件全部压成 generic
`PROGRESS` 的 root cause。

Allowed files / modules：

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/admission.py`
- `tests/host/test_public_event_api.py` 或等价 Host API contract tests。
- `tests/host/test_read_api.py` 或等价 session live watch projection tests。

Exact allowed changes：

- 新增 `HostActivityView`、`HostActivityKind`、`HostActivityStatus`、
  `HostActivitySeverity`、`HostActivityCounts`，所有 public dataclass / function 都必须
  有中文 docstring、完整类型和 validation。
- `HostActivityCounts` 第一版固定为 `total`、`completed`、`failed`、`cancelled`
  四个 non-negative int 字段；不允许 extra dict。
- 扩展 `HostEvent`：新增 `event_class`、`event_type`、`activity`；更新 validation 和
  public export。
- `event_class` 复用已有 `HostEventClass`，不新增 enum；`event_type` 从 EventLog row
  直接复制。
- Host admission 在 `USER_INPUT_ACCEPTED.effective_tool_set` 中冻结 selected tools 的
  `effective_tool_display_names` snapshot；`read_api` 只通过 run/input payload 查该
  Host-owned snapshot，按 `tool_name` lookup，缺失 fallback stable `tool_name`。
- `_host_event_from_row(...)` 对所有 rows 填充 `event_class` / `event_type`。terminal rows
  继续保留现有 terminal payload；非终态 rows 保持 `HostEventKind.PROGRESS`，但允许
  `activity`。
- 新增 activity allowlist projection：`TOOL_CALL_REQUESTED`、
  `TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`TOOL_AWAITING`、`RUN_WAITING`、
  `CONTEXT_COMPACTION_*`、`PROVIDER_PROTOCOL_ERROR`、必要 run lifecycle events。
- 未知非终态保留 identity 且 `activity=None`。
- `REASONING_DELTA` 和 `CONTENT_DELTA` 都保留 identity 且 `activity=None`；raw delta
  永不投影 activity。
- 工具展示名从 Host-owned effective tool display snapshot 取得；不得让 Engine、
  Service 或 CLI 读取 `ToolBundle`。

Call paths：

- Engine / Host ingest -> EventLog row -> `watch_session_events(session_id)` ->
  `_ReadSessionHostEventsAfterOperation` -> `_host_event_from_row(...)` ->
  public `HostEvent(event_class, event_type, activity)`.

Tests：

- 非终态 tool preview row 投影为 `HostEventKind.PROGRESS`，同时带正确
  `event_class`、`event_type` 和 `HostActivityView`。
- `TOOL_CALL_REQUESTED` activity 包含 stable `tool_name`，有 display metadata 时包含
  `tool_display_name`。
- `TOOL_RESULT_ACCEPTED` 按 outcome kind 映射 status / severity。
- `TOOL_CALLS_BATCH_DONE` counts 正确且强类型。
- `PROVIDER_PROTOCOL_ERROR` 只展示 bounded error code / message，不暴露 raw payload ref。
- `REASONING_DELTA` 与 `CONTENT_DELTA` 都不泄露 raw delta，且 `activity=None`。
- 未知非终态 event 保留 identity 且 `activity=None`。
- terminal HostEvent 仍包含 final answer / error / cancel payload，且 validation 不回退。
- terminal HostEvent `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST` 都必须携带正确
  `event_class` 和 `event_type`。

Stop condition：

- 如果实现需要 durable schema migration、Engine import Host / `ToolBundle`、Service /
  CLI 读取 `ToolBundle` 或 EventLog payload、或把 raw payload ref/digest 暴露给 Service
  / CLI，停止并回到 design gate。

### Slice B - Service activity callback consumes Host public activity

Objective：让 Service helper 把已消费的 public live events 投影成 entrypoint activity
callback，同时保持 terminal wait 与 outbox fallback 语义。

Allowed files / modules：

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

Exact allowed changes：

- 新增严格类型 `EntrypointActivityKind`、`EntrypointActivityStatus`、
  `EntrypointActivitySeverity`、`EntrypointActivityCounts`、`EntrypointActivity`、
  `EntrypointActivityCallback`。
- `submit_entrypoint_turn_and_wait(...)` 增加可选 `on_activity` 参数，默认 `None`。
- `_drain_available_watcher_items(...)` 在消费 non-terminal `HostEvent.activity` 时调用
  projection helper；projection 只消费 Host public fields。
- 对没有 `activity` 的 generic progress 默认不回调，或回调 bounded generic run activity；
  不解析 payload ref / digest。
- Service / CLI 不得根据 `HostEvent.event_class` 做 UI 分支；UI 展示只依赖 Service
  DTO 的 `kind`、`status`、`title`、`summary`、`severity`。
- 对 `_WatcherFailure` 只生成有界 diagnostic activity 到 callback，不改变 terminal
  fallback 结果。

Call paths：

- prompt / interactive -> `submit_entrypoint_turn_and_wait(..., on_activity=renderer.record)`
  -> `_wait_for_terminal(...)` -> watcher queue -> callback。

State transitions：

- attach watcher -> submit -> accepted run id -> activity 0..n -> terminal result。

Tests：

- watcher attach 仍在 submit 前。
- Host public activity event 被 callback 收到且不作为 terminal 返回。
- duplicate activity 按 dedupe key 不重复 callback。
- Host progress without activity 不导致工具级伪展示。
- watcher failure 产生 diagnostic activity，但 terminal outbox fallback 仍可返回。
- terminal live event 仍返回 `EntrypointRunTerminalResult`，不被 activity callback 吞掉。

Stop condition：

- 需要读取 EventLog payload、Tool Trace 或 Host private DTO 时停止，回到 Slice A contract。

### Slice C - CLI activity renderer and prompt integration

Objective：`prompt` 在运行态展示可隐藏 / 展示的 activity，并保持 stdout final answer
清晰。

Allowed files / modules：

- `dayu/cli/activity.py`（可新增）
- `dayu/cli/output.py`
- `dayu/cli/commands/prompt.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_activity_renderer.py`（可新增）

Exact allowed changes：

- 新增 renderer state：visible / hidden、seen dedupe keys、last sequence、TTY policy。
- renderer 只写 stderr；terminal renderer 不变。
- `_submit_prompt_turn_handling_sigint(...)` 创建 renderer 并传入 Service `on_activity`。
- Ctrl+T 切换 visible / hidden；Ctrl+C / Esc 按运行态 cancel 语义处理。
- TTY 与 non-TTY 行为分离：TTY 可接收 activity toggle / cancel key handling；non-TTY
  默认无 Ctrl+T，Ctrl+C 按 SIGINT / local exit 语义，不伪造 Host cancel fact。
- 若新增状态 transition helper，Slice C 必须先覆盖 prompt running/cancelling 的核心
  transition；若不新增 helper，则 Slice C 必须留下可被 Slice E 复用的集成测试 fixture。

Call paths：

- `run_prompt_command` -> `_execute_prompt_on_existing_session` ->
  `_submit_prompt_turn_handling_sigint` ->
  `submit_entrypoint_turn_and_wait(..., on_activity=...)` -> stderr activity ->
  terminal stdout。

State transitions：

- RUNNING_VISIBLE / RUNNING_HIDDEN / CANCELLING_VISIBLE / CANCELLING_HIDDEN /
  TERMINAL_RENDERING。

Tests：

- TTY stderr 下 activity 写 stderr，final answer 写 stdout。
- non-TTY stderr 默认不写 live activity，final answer 仍写 stdout。
- Ctrl+T 不调用 Host cancel，只影响 renderer visible。
- Ctrl+C / Esc 在 accepted run 后调用 cancel helper；第二次 Ctrl+C 返回 130。
- Run accepted 前 Ctrl+C 不发 cancel。
- CANCELLING 中 terminal 先到达时渲染 terminal，第二次 Ctrl+C 不覆盖 terminal。

Stop condition：

- 需要 CLI 读取 Host internals 或 renderer 与 terminal final answer 无法避免乱序时停止。

### Slice D - Interactive composer

Objective：把 interactive 输入态从单行 `input(...)` 替换为 prompt_toolkit composer，
支持多行、历史搜索、外部编辑器和输入态 Ctrl+C 语义。

Allowed files / modules：

- `dayu/cli/composer.py`（可新增）
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_interactive_composer.py`（可新增）

Exact allowed changes：

- 在替换 REPL wiring 前，先做 prompt_toolkit early compatibility validation：用最小
  wrapper / 单元测试验证当前依赖版本可表达 Ctrl+J、Ctrl+R、Ctrl+X Ctrl+E、输入态
  Ctrl+C 以及 async / key binding 基本组合；失败则先停止，不做大范围 REPL 改造。
- 新增 `InteractiveComposer` 窄协议 / wrapper，生产实现使用 prompt_toolkit，测试可注入
  fake。
- Ctrl+J 插入换行，Enter accept，Ctrl+R 历史搜索，Ctrl+X Ctrl+E 外部编辑器。
- `_run_interactive_repl(...)` 接收 composer / input reader 的窄接口，避免 prompt_toolkit
  类型扩散。
- 输入态 Ctrl+C：空 draft 退出 130；非空 draft 清空并继续输入。

Call paths：

- `run_interactive_command` -> `_execute_interactive_on_existing_session` ->
  `_run_interactive_repl` -> composer read -> submit path。

State transitions：

- INPUT -> RUNNING_* -> TERMINAL_RENDERING -> INPUT。

Tests：

- 多行输入保留换行并 submit。
- 空白输入不 submit。
- Ctrl+R 调用历史搜索行为的 wrapper hook。
- Ctrl+X Ctrl+E 调用外部编辑器 hook，编辑后 submit；返回空白不 submit；用户取消不
  submit；启动失败保留 draft 并输出 stderr diagnostic。
- 输入态 Ctrl+C 空 draft 退出，非空 draft 清空不 submit。
- prompt_toolkit minimal compatibility test 先于 broad REPL wiring 落地。

Stop condition：

- prompt_toolkit 无法在当前依赖版本实现必需快捷键时停止并重新裁决依赖 / 降级策略。

### Slice E - Interactive running activity and cancel integration

Objective：interactive 每轮运行态复用 activity renderer 与 cancel state machine，确保
每轮 final answer 与下一轮 composer 不乱序。

Allowed files / modules：

- `dayu/cli/activity.py`
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_activity_renderer.py`

Exact allowed changes：

- `_submit_interactive_turn_handling_sigint(...)` 传入 `on_activity`。
- 每轮 renderer 生命周期随 run 创建和终态关闭；下一轮 composer 启动前 flush / close
  activity 区域。
- Ctrl+T、Ctrl+C、Esc 运行态语义与 prompt 保持一致；连续 Ctrl+C 本地退出。
- 复用 Slice C 的 transition helper，或增加 cross-slice integration test 覆盖
  prompt / interactive 共享的 RUNNING、CANCELLING、TERMINAL_RENDERING ordering。

Call paths：

- composer -> `_submit_interactive_turn_handling_sigint` -> Service activity callback ->
  renderer -> terminal -> composer。

State transitions：

- INPUT -> RUNNING_VISIBLE / RUNNING_HIDDEN -> CANCELLING_* -> TERMINAL_RENDERING ->
  INPUT。

Tests：

- 两轮 interactive：第一轮 activity / final answer 完成后第二轮 prompt 不被覆盖。
- hidden activity 时 terminal final answer 仍可读。
- failed / cancelled 单轮在 interactive 中按现有语义继续 REPL；lost 仍 fatal。
- terminal-before-cancel 与 cancel-before-terminal ordering 均被覆盖，terminal result
  不被第二次 Ctrl+C 覆盖。

Stop condition：

- 如果 prompt_toolkit 与 async run-state key handling 无法在不重写 REPL 主循环的情况下
  可靠组合，停止并拆分方案，不做 ad hoc terminal hacks。

### Slice F - Documentation checks and validation cleanup

Objective：按 AGENTS.md 完成 README 触发检查、测试覆盖和 pyright 验证。

Allowed files / modules：

- `dayu/host/README.md`（仅当 Host public event contract 说明属于其读者范围）
- `tests/README.md`（仅当测试职责说明需要更新）
- `dayu/README.md`（仅当边界 / 装配 / public contract 说明实际变化）
- `dayu/service/README.md`（只读检查；若存在，记录 entrypoint behavior 变化是否影响
  其职责范围）

Exact allowed changes：

- 先阅读目标 README 的 Agent 更新约束，再决定是否修改。
- 更新只描述 public Host activity event、CLI activity / composer 测试边界，不机械同步
  实现细节。
- `dayu/service/README.md` 只做存在性与职责范围检查；AGENTS.md 未列为触发项时不机械
  更新，但 completion report 必须记录检查结论。

Tests：

- 见第 9 节。

Stop condition：

- README 缺少 Agent 更新约束时，按 AGENTS.md 只判断触发规则，不自行扩写文档职责。

## 9. Tests / validation commands and expected assertions

实施后必须运行受影响测试：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_public_event_api.py \
  tests/host/test_read_api.py \
  tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_activity_renderer.py \
  tests/cli/test_interactive_composer.py \
  -q
```

若实际测试文件名不同，implementation agent 必须用实际文件替换命令，并说明原因。

覆盖率验证：

```bash
source .venv/bin/activate && pytest \
  tests/cli/test_activity_renderer.py \
  tests/cli/test_interactive_composer.py \
  --cov=dayu.cli.activity \
  --cov=dayu.cli.composer \
  --cov-fail-under=80 \
  -q
```

如果 Slice A 新增 Host activity projection helper 文件，也必须对该文件单独验证 >= 80%
覆盖率，或说明它已被现有 Host read API 测试计入覆盖率。

类型检查：

```bash
source .venv/bin/activate && pyright
```

格式 / patch hygiene：

```bash
git diff --check
```

Expected assertions：

- stdout 只包含 final answer / machine-consumable result；activity 不进入 stdout。
- stderr TTY activity 可见 / 隐藏切换可测试；non-TTY 默认无 live activity。
- `watch_session_events(session_id)` 是唯一 Host event read path；测试 fake Host 不提供
  durable internals。
- `HostEvent` 对非终态事件保留 `event_class` / `event_type`；未知事件
  `activity=None`。
- `HostEvent.event_class` 复用已有 `canonical_fact` / `preview` / `diagnostic` /
  `projection_signal`；`HostEvent.event_type` 直接复制 EventLog row `event_type`。
- terminal HostEvent `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST` 都携带
  `event_class` / `event_type`。
- Tool activity 使用 Host public `HostActivityView`，工具展示名优先
  `ToolDisplayInfo.name`，缺失 fallback stable tool name；Service / CLI 不读取
  `ToolBundle`。
- `REASONING_DELTA` 与 `CONTENT_DELTA` 都保留 identity 但 `activity=None`，raw delta
  永不投影 activity。
- outbox terminal fallback 仍只用于 terminal，不能产生 activity。
- Ctrl+T 不触发 cancel；Ctrl+C / Esc 触发 cancel；连续 Ctrl+C 本地退出；CANCELLING
  中 terminal 优先于第二次 Ctrl+C。
- prompt non-TTY 下没有 Ctrl+T；Ctrl+C 按 SIGINT / local exit 语义。
- interactive composer 的 Ctrl+J、Ctrl+R、外部编辑器行为有独立单元测试。
- 外部编辑器返回空白或用户取消时不 submit；启动失败保留 draft 并显示 stderr
  diagnostic。

Plan gate 本次只修改 markdown artifact，按用户要求不运行代码测试；只运行
`git diff --check`。

## 10. Docs decision

按 AGENTS.md README 触发规则：

- `dayu/host/` 修改：必须检查 `dayu/host/README.md` 的 Agent 更新约束，若 public
  event contract 说明属于其读者范围则更新。
- `tests/` 修改：必须先检查 `tests/README.md` 的 Agent 更新约束，若新增测试分类或
  命令职责属于其读者范围则更新。
- 若 implementation 改变 `UI / Service / Host / Agent` 边界、装配方式或 public
  contract：必须检查 `dayu/README.md`。
- `dayu/service/entrypoint_runtime.py` 修改：AGENTS.md 未列出 `dayu/service/README.md`
  触发项；但如果 `dayu/service/README.md` 存在，implementation agent 必须只读确认
  Service entrypoint behavior 变化是否影响该 README，并在 completion report 记录
  更新 / 不更新结论。
- `dayu/cli/` 修改：AGENTS.md 未列出 CLI README 触发项。
- 本 plan artifact 修改本身不触发 README 更新。

## 11. Risks / open questions / residual risk classification

Blocking：

- None. BQ-1 已 resolved：用户裁决允许 WU-CLI-ACTIVITY-01 修改 event 相关 contracts。

Residual risks：

- RR-ACT-01（low）：Host-owned tool display snapshot 需要扩展
  `USER_INPUT_ACCEPTED.effective_tool_set` payload shape。缓解：只在 Host admission 从
  selected `ToolBundle.definitions` 提取 `{tool_name, display_name}`，不改 durable schema，
  不让 Engine / Service / CLI 读取 ToolBundle。
- RR-ACT-02（medium）：prompt_toolkit key binding 在不同终端下行为可能不一致。缓解：
  在 Slice D 先做 minimal compatibility validation，再把 composer 封装成窄模块，用
  单元测试覆盖 key handling，手工 smoke 在 TTY 中验证。
- RR-ACT-03（low）：dynamic stderr renderer 可能与终端宽度、换行或 final answer 发生
  视觉干扰。缓解：renderer close / flush 后再 terminal render；非 TTY suppress live
  activity。
- RR-ACT-04（low）：连续 Ctrl+C 本地退出后 Host cancel terminal 可能稍后才提交。缓解：
  本地退出不伪造 Host fact；后续 session/outbox 仍可观察真实 terminal。
- RR-ACT-05（low）：CANCELLING 与 terminal 到达存在竞态。缓解：状态机规定 terminal
  优先于第二次 Ctrl+C，并用 terminal-before-cancel / cancel-before-terminal 测试覆盖。

## 12. Stop conditions

- 需要 durable schema migration、EventLog canonical fact 语义变更或 Host / Engine 状态机
  变更时停止，回到 design gate。
- 需要 CLI / Service 读取 EventLog row、payload_ref、payload_digest、Tool Trace、logging
  或 Host private DTO 时停止。
- 需要 Engine import `dayu.host`、`ToolDefinition`、`ToolBundle` 或 Host-owned display
  metadata 时停止；需要 Service / CLI import 或读取 `ToolBundle` / `ToolDefinition`
  取得展示名时也停止。
- 需要使用 `Any`、`object`、无类型参数 / 返回值、兼容 wrapper / facade、lazy import 或
  显式参数塞进 extra payload 才能推进时停止。
- 需要保留旧 public event contract 兼容别名 / wrapper 才能通过旧测试时停止；测试必须
  跟着新 contract 迁移。
- prompt_toolkit 无法稳定实现 interactive 本轮必需的多行、历史搜索、外部编辑器时停止。

## 13. Completion report format

Implementation final report 必须包含：

- changed files
- plan status
- major decisions updated
- validation run
- residual risks / open questions

其中：

- changed files：按 Host public activity contract、Service activity callback、prompt
  activity、interactive composer、interactive activity、测试 / README 分组。
- plan status：说明本计划已进入 implementation / review / ready gate 的实际状态。
- major decisions updated：明确 BQ-1 已 resolved，activity contract 由 Host public
  `HostEvent.activity` 承载，CLI 不读取 durable internals。
- validation run：列出 pytest、coverage、pyright、`git diff --check` 的实际命令和
  结果。
- residual risks / open questions：说明剩余风险、README 决策和 stdout / stderr 策略；
  不得宣称未覆盖的 TTY 手工行为已自动验证。

## 14. Why this is not over-designed

- 不引入 curses / full-screen TUI，不引入 durable activity store，不新增 background
  projection。
- 只修正 session live watch 的 public event projection root cause，不把 CLI 变成 Host
  internals reader。
- `HostActivityView` 是 Host public display projection，不是 Tool Trace、payload reader
  或 diagnostic analyzer。
- Service activity DTO 是 Service 到 CLI 的窄投影，不把 Host private row、EventLog
  payload 或 Tool Trace schema 提升到 CLI。
- Composer 只用于 interactive 输入态，prompt 保持 one-shot 语义。
