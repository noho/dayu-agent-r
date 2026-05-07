# Host P4 Handoff Plan：Host Compact for Context Overflow

## 目标

P4 目标是在 P3 已合入 `main` 的 Host Conversation Memory / RunInputBuilder 事实层之上，迁移 context overflow
时 compact 的归属：Engine 或 Runner 在上下文超限时只暴露强类型 overflow / compaction-required 事实，
Host 负责基于 P1.5 / P3 canonical EventLog、memory snapshot 与 RunInputBuilder trace 中的可消费事实构造
compact 后的 attempt 输入，然后继续同一个 Run 的下一次 internal attempt，或在无法 compact / 超过策略上限时
明确失败收口。

本阶段必须产出：

- Host internal compact coordinator / policy：识别 Engine context overflow 事实，决定是否重建 attempt 输入。
- Host compact 输入：只来自 `USER_INPUT_ACCEPTED`、canonical terminal / tool facts、P3 memory snapshot、
  `RunInputBuildTrace` 的 included / excluded 诊断与可消费事实，不绕过 EventLog 另造 transcript 真源。
- Host compact 输出：生成可解释的 compacted memory block / attempt RunInput，并保留 pinned state、稳定事实、
  evidence anchors、source cursor、当前用户问题与必要工具事实。
- Host Memory / compact memory 顺序约束：若调用者、Agent 或 app 提供 caller system prompt，Host Memory
  system block 必须追加在 caller system prompt 之后、当前 UserMessage 之前；compacted RunInput 重建时也
  继承同一顺序，不得把 Host memory 放到 caller system prompt 前。
- Host token 估算策略：P4 compact before / after size、`RunInputBuildTrace.total_token_estimate` 与
  trigger / effectiveness 判断不得继续只依赖 P3 `_APPROX_TOKEN_CHARS=4` 粗估；必须继承 OLD
  `conversation_memory` 对中英文混合财报文本更保守的宽 / 窄字符估算思想。
- compacted RunInput 语义：它是 Host 从既有 `USER_INPUT_ACCEPTED` 与 canonical facts 派生出的治理性
  attempt 输入，不是新的用户输入事实；同一 Run 下 retry 不得再次 append `USER_INPUT_ACCEPTED`。
- Host Memory 输出不变量：RunInputBuilder 注入的 system Host Memory block 是 internal grounding context /
  verification context，不是 final answer 输出模板；其中的 `Tool Facts`、`Evidence Anchors` 或 compact 后
  等价摘要只允许模型用于定位、校验和引用来源，不得被原样渲染成用户可见“历史工具摘要”正文。
- Engine overflow 协作：补齐 OLD 多 provider context overflow 信号回归矩阵；P4 不是在 Host
  硬编码字符串，而是在 Engine / Runner 内有可测试的 classifier / adapter 边界，优先消费结构化 provider
  错误，只有在 Engine 层 classifier 内允许受控 message fallback。
- compact 成功后置条件：compacted RunInput 必须在 token / char 估算上确实变短；如果 no-op、变长，或
  当前用户问题、pinned_state、evidence anchors 不能保真，则不得再次 retry，必须以 Host-owned failed
  terminal 收口并记录可解释原因。
- attempt retry loop：context overflow 后最多按明确上限重建 attempt；成功则继续流出同一个 Run 的事件，失败则
  append Host-owned terminal `RUN_FAILED`。
- EventLog 事实：记录 context overflow 被观察、compact requested / completed / failed、attempt retry
  decision 等 Host canonical 事实，供 P5 smoke 与后续 P6 projection 读取。
- OLD / NEW 语义对照：强参考 OLD `async_agent._compact_messages` 的“保留系统 / 用户目标 / 最近尾部 /
  工具调用组不拆散 / 工具结果摘要”不变量，以及 OLD `conversation_memory` 的 pinned_state / episode
  summary / compaction scene 经验；但不把 OLD Engine 内 compact/retry、scene_preparer、后台 archive compaction
  机械迁回 NEW。
- 财报分析保真约束：compact 不得丢失 pinned_state、稳定事实、证据锚点、来源游标、当前用户问题；旧摘要 /
  recall 可以降级，但降级原因必须可解释并可在 trace 或 event data 中定位。
- P4 后补充 smoke 判断：若 P4 触及真实 provider overflow 或 attempt retry，必须新增 `utils/` 手工 smoke；
  若只通过 fake Engine overflow 验证，则计划中说明 P5 前是否补 smoke。
- P4 实施完成后写回 `docs/host/design.md` 与 `dayu/host/README.md`：只写当前已落地的 overflow compact
  执行路径与边界，不写未来完整治理。

## 非目标

P4 不实现以下能力：

- 不解决 Engine stream 无 terminal 问题。Engine stream 按设计必须有 terminal；无 terminal 的 CRITICAL log 与
  Host-owned 失败终态已经是 P3 事实，P4 不重复解决。
- 不实现完整 context governance，包括全局 token budget service、长期 memory governance、跨 session /
  project / user memory 策略、准入仲裁、生产级恢复。
- 不实现 replay / validation / OutputContract 联动；context overflow compact 后重建 attempt 输入不是输出
  校验失败后的 replay。
- 不提前做 P6 observer / persistent projection / audit hard-gate / tool trace observer。
- 不提前做 P7 lifecycle governance、`client_request_id` 幂等、同 Session active Run admission、完整取消治理。
- 不提前做 P8 lease / fencing / 多进程 recovery。
- 不提前做 P9 Reply Outbox。
- 不迁回 OLD Engine 内 `_compact_messages` 作为 Engine 稳定能力，不在 Engine 内实现 compact/retry 策略。
- 不迁回 OLD `ConversationCompactionCoordinator` 的后台 archive compaction、scene preparation、Agent builder
  或 file archive 写回路径。
- 不让 reasoning / preview / delta 进入运行态 memory、RunInput replay 或 compact 输入。
- 不新增财报业务语义抽取。Host 只保留 fins / tool facts 提供的 opaque evidence/source references，不解释公司、
  期间、口径、单位、准则或 XBRL fact。

## 前置条件

- P1、P1.5、P2、P3 已合入 `main`。
- P3 已通过 PR #19 合入 `main`，merge commit 为 `b20e792 Host P3 conversation memory (#19)`。
- 当前分支为 `codex/host-p4-context-overflow-compact`。
- 当前 `dayu.host` 已落地：
  - append-before-stream `RunEventStore`。
  - Host-owned canonical `USER_INPUT_ACCEPTED`。
  - canonical / preview 分层。
  - ToolRuntime truncate / fetch_more canonical facts。
  - `InMemoryConversationMemoryStore` 与 `DefaultRunInputBuilder`。
  - `RunInputBuildTrace` internal-only 诊断缓存。
  - Engine stream 无 terminal 时的 Host-owned `RUN_FAILED` 与 CRITICAL log。
- 当前 `dayu.engine` 已有 `EngineEventType.CONTEXT_COMPACTION_REQUESTED` 与
  `ContextCompactionRequestedData` 契约，但生产路径是否产生该事件需由 P4 实施前以代码直接确认。
- OLD 直接证据：
  - `../dayu-agent/dayu/engine/async_agent.py` 中 `_compact_messages` 处理 Engine 内 provider overflow 与软阈值
    压缩，保留连续 system、首条 user、最近尾部，并避免拆散 assistant(tool_calls) + tool 结果组。
  - `../dayu-agent/dayu/engine/async_openai_runner.py` 中 `_detect_context_overflow` 识别
    `context_length_exceeded` 与多 provider 文本信号。
  - `../dayu-agent/dayu/host/conversation_memory.py` 中 `DefaultConversationMemoryManager` / episode
    compaction 提供 pinned_state、recent episodes、tool result summary、pinned_state_patch 三态语义参考。
  - `../dayu-agent/dayu/host/conversation_memory.py` 中 `_token_units_for_char`、
    `_estimate_token_units`、`_token_units_to_estimated_tokens`、`_estimate_tokens` 提供中英文混合财报文本的
    保守 token 近似参考：半角字符 1 unit，全角 / 宽字符 2 units，再按固定 unit-per-token 转换。
- 计划 review 前必须再次用 `rg` 复核 NEW / OLD 中 `compact`、`overflow`、`context_length`、
  `ConversationMemory`、`conversation_memory`、`summar` 的当前位置，确认没有新的并行 Agent 已改动边界。

## 架构边界

分层仍固定为：

```text
UI -> Service -> Host -> Engine
```

P4 后 context overflow 协作边界：

```text
Engine / Runner
  -> EngineEvent(context_compaction_requested) 或 terminal recoverable RUN_FAILED(context_compaction_required)
  -> WorkerProxy
  -> Host RunEventStore append canonical overflow fact
  -> Host CompactCoordinator
      -> RunEventStore canonical facts
      -> ConversationMemoryStore snapshot
      -> RunInputBuildTrace / 可消费事实诊断
      -> CompactPolicy
      -> RunInputBuilder compact mode 或 CompactRunInputBuilder
  -> same Run / new internal attempt input
  -> LocalProxy -> EngineWorker -> Engine
```

边界规则：

- Host 决策 compact、attempt retry、失败收口；Engine 只负责报告无法继续的 overflow / compaction-required 事实。
- compacted RunInput 只属于同一 Run 的新 internal Engine attempt 输入；它不改变原始用户输入真源，
  也不表示用户提交了新 turn。
- Host Memory system block 与 compacted memory block 都是 Host 内部 grounding / verification context。
  RunInputBuilder 或 compact 渲染层必须明确标注这类内容不可原样输出；P4 plan 只要求实施时补保护，
  不宣称当前 P3 代码已经具备该保护。
- 若调用者 / Agent / app 提供 caller system prompt，RunInputBuilder 与 compact RunInput 重建必须保持
  caller system prompt 作为前缀，随后注入 Host Memory instructions + Host Memory / compact memory
  system context，最后才是当前 UserMessage。若 provider / payload builder 需要把多条 system message
  合并成单条文本，合并文本也必须保持 caller system prompt 在前，Host Memory instructions 与 Host
  Memory 在后。
- 该顺序同时服务语义优先级与 provider prefill cache / prompt cache 友好性：caller system prompt 通常更稳定，
  适合作为稳定前缀；Host Memory / compact memory 每轮更易变化，放在后面可减少稳定前缀失效。P4 只能把这写成
  prompt 排列优化理由，不得宣称已经接入任何具体 provider cache API。
- compact 输入不得从客户端 timeline、preview stream、reasoning delta、content delta、展示 transcript 或
  request 对象旁路构造。
- `RunInputBuildTrace` 可用于解释“哪些事实已进入 / 被裁剪”，但 trace 不是事实真源；缺事实时必须回到
  RunEventStore / memory snapshot，而不是把 trace 当 transcript。
- P4 可以新增 Host internal compact trace / data，但不得把显式参数塞进 extra payload。
- P4 不改变 ToolRuntime 的权限和 cursor 管理边界；ToolRuntime 不负责 context compact。
- P4 不改变 EngineWorker public boundary；EngineWorker / ToolExecutor 仍不是 Host public API。
- `dayu.runtime` 不承载 compact / memory / attempt policy；这些是 Host 上下文治理，不是层中立 runtime helper。

## 文件级改动清单

计划新增：

- `dayu/host/_token_estimator.py`
  - 定义 Host 内部 token estimator，供 RunInputBuilder、CompactCoordinator、compact trace / event size 字段共同使用。
  - 优先继承 OLD `conversation_memory` 的保守字符近似：半角字符按 1 unit，全角 / 宽字符按 2 units，
    再按命名常量 `TOKEN_UNITS_PER_ESTIMATED_TOKEN` 或等价私有常量向上取整转换为估算 token。
  - 所有权属于 Host context budgeting；不得放入 `dayu.runtime`，也不得 import Engine / provider tokenizer。
  - estimator 是 Host compact / RunInputBuilder 的预算与 before / after 相对比较工具，不是 provider tokenizer 真源。
    context overflow 是否真实发生的真源仍来自 Engine / Runner provider classifier 的强类型事实。
  - 必须用命名常量表达 half-width unit、full-width unit、unit-per-token 与算法标识，trace / event data 中可记录算法标识。
- `dayu/host/_context_compaction.py`
  - 定义 Host internal compact policy、compact input / output、compact trace。
  - 定义 `ContextCompactCoordinator` 或等价内部组件，负责从 overflow fact 到 compacted RunInput 的决策。
  - 定义 deterministic compact 默认实现：优先保留 pinned_state、stable frame、verified claims、assumptions、
    evidence anchors、tool facts、当前用户输入，再对 older raw turns / 旧摘要做可解释降级。
  - 不调用 LLM compaction scene；若实施 Agent 判断必须调用 LLM 才能达成目标，必须停止并修 plan。
  - compact output 必须携带 before / after token 或 char 估算、reduced 判断与失败原因；只有
    `after < before` 且必保事实保真时才允许后续 retry。
- `tests/host/test_phase4_context_compaction.py`
  - 覆盖 compact 输入来源、保真约束、降级解释、reasoning/preview 隔离、财报 evidence/source cursor 保留。
- `tests/host/test_phase4_overflow_retry.py`
  - 使用 fake WorkerProxy / fake Engine event stream 模拟 context overflow、compact 后成功、compact 后仍失败、超过上限。
- `tests/host/test_phase4_boundary.py`
  - 覆盖 Engine 不 import Host compact、Host public API 不导出 compact coordinator、ToolRuntime 不承担 compact。
- `utils/smoke_host_context_compaction.py`
  - P4 后若实现 attempt retry 或真实 overflow 事件映射，新增手工 smoke；若实施范围无法稳定触发真实 provider
    overflow，也必须提供 fake overflow smoke，清楚标注不代表 provider 覆盖。

计划修改：

- `dayu/host/contracts.py`
  - 新增 Host-owned compact / overflow canonical event data，例如 `HostContextOverflowObservedData`、
    `HostContextCompactRequestedData`、`HostContextCompactCompletedData`、
    `HostContextCompactFailedData`、`HostContextAttemptRetryData`，命名可调整但必须封闭联合。
  - 如 Engine 已能产生 `CONTEXT_COMPACTION_REQUESTED`，保留其 Engine source 映射；Host-owned 事实使用
    `source=HOST`。
  - 若需要表达 compact policy，使用强类型 dataclass / enum，不使用 `dict[str, Any]`。
- `dayu/host/_event_translation.py`
  - 将 Engine `CONTEXT_COMPACTION_REQUESTED` 分类为 canonical。
  - 将 Engine terminal recoverable `RUN_FAILED(error_code="context_compaction_required")` 或等价
    overflow 事实映射为 Host 可识别的 compact trigger；若当前 Engine 没有该生产路径，P4 只能在 Host fake
    WorkerProxy 测试中覆盖，并把 Engine 协作缺口列为停止条件或小范围契约补充。
- `dayu/host/_run_harness.py`
  - 在 `_run_to_store` 内识别 context overflow trigger 后，不把同一个 Run 立即投影为最终失败；先由
    CompactCoordinator 判断是否重建 attempt。
  - compact retry 是同一个 Run 的内部 attempt，不改变 public `run_id`。
  - retry 启动第二次或后续 internal Engine attempt 时，必须复用原始 `USER_INPUT_ACCEPTED` 事实派生输入，
    不得再次 append `USER_INPUT_ACCEPTED`。
  - 每次 retry 必须有次数上限和事件事实，不得无限循环。
  - 如果 compact 失败或上限耗尽，append Host-owned terminal `RUN_FAILED`。
- `dayu/host/_run_input_builder.py`
  - 可选择增加 compact mode 或提供 compact builder adapter；必须保留 P3 默认顺序与 preview / reasoning
    隔离。
  - 若新增 caller system prompt / app system prompt 支持，必须把 Host Memory system block 追加在 caller
    system prompt 之后、当前 UserMessage 之前；compact mode 重建 RunInput 时同样保持 caller system prompt
    前缀不变，再注入 Host compact memory block。
  - 若 provider / payload builder 需要合并多条 system message，合并后的文本顺序必须可测试地保持 caller
    system prompt 在前，Host Memory instructions + Host Memory / compact memory 在后。
  - `RunInputBuildTrace` 可扩展记录 compact 降级原因，但仍 internal-only，不进入 RunInput / memory pool。
  - 若 P4 修改 RunInputBuilder 的 token 估算，必须从 Host 内部 token estimator 取值，并同步更新
    `RunInputBuildTrace.total_token_estimate` 与每个 `RunInputTraceItem.token_estimate` 的测试。
  - 若 P4 暂不修改 RunInputBuilder，则必须在代码注释 / 文档中把现有 `_APPROX_TOKEN_CHARS=4` 明确标为
    P3 临时粗估；它不得作为 P4 compact trigger 或 effectiveness gate 的最终依据。
- `dayu/host/_conversation_memory.py`
  - 如需支持 episode summary slot 的最小写入或 compacted older pool 表达，只能作为 Host internal memory
    projection，不得引入持久 schema 或 public memory API。
  - memory projection 不得把 compacted RunInput 记成新的 raw user turn；本 Run 的用户输入 canonical 真源仍只有
    原始 `USER_INPUT_ACCEPTED`。
- `dayu/engine/runners/openai/error_classifier.py`、`dayu/engine/runners/openai/runner.py`、
  `dayu/engine/agent.py`
  - 只有当 NEW Engine 完全无法暴露 context overflow 事实时，才允许做最小契约补充：provider context overflow
    识别并以现有 `CONTEXT_COMPACTION_REQUESTED` + terminal recoverable failure 或等价已设计事件收口。
  - provider overflow 识别必须落在 Engine / Runner classifier 或 provider adapter 边界，并有纯单元测试；
    Host 只消费强类型结果，不实现 provider message 字符串匹配。
  - classifier 必须优先读取结构化错误字段，例如 OpenAI `error.code=context_length_exceeded`；message
    fallback 只覆盖已列入矩阵的 context overflow 短语，并必须有普通 400 / 普通 client error 负例防误判。
  - 禁止在 Engine 内实现 compact、retry、memory、RunInput 重建或 Host policy。
- `dayu/host/README.md`
  - P4 实施后写当前事实：context overflow compact 已落地的执行路径、事件、上限、未落地治理。
- `docs/host/design.md`
  - P4 实施后写回 Host compact ownership、Engine 协作边界、P4 后执行路径。
- `tests/README.md`
  - P4 新增 Host compact 测试分层与验证命令后再更新。

不计划修改：

- `dayu.runtime.*`。
- `dayu.fins.*`。
- `dayu.service.*`、`dayu.ui.*`。
- 持久化 schema / workspace migrations。

## 新增 / 修改契约

### Engine overflow 输入契约

P4 接受的 overflow trigger 只能来自以下事实之一：

- Engine source canonical `CONTEXT_COMPACTION_REQUESTED`，data 为 `ContextCompactionRequestedData`。
- Engine source terminal `RUN_FAILED`，错误码为明确 context overflow / compaction required，并且
  `recoverable=True`。
- Runner provider protocol error 中已被强类型识别为 context overflow 的事实；若只是普通 `client_error` 或
  非结构化文本，不得由 Host 猜测为 overflow。

若当前 Engine 无法产生上述任何事实，实施 Agent 必须先补最小 Engine 协作契约或停止修 plan；不得在 Host
用字符串搜索普通 provider 错误文本替代根因判断。

Engine / Runner 的 provider overflow 识别必须形成可测试 classifier / adapter 边界，而不是把 provider
字符串散落到 Host 或 retry loop。回归矩阵至少覆盖：

| 类别 | 输入信号 | 期望 |
| --- | --- | --- |
| 结构化 OpenAI | JSON `error.code == "context_length_exceeded"` | 识别为 context overflow，产出强类型 `CONTEXT_COMPACTION_REQUESTED` 或等价 compaction-required fact |
| OpenAI message fallback | `maximum context length is`、`context length exceeded` | 在 Engine classifier 内识别为 context overflow |
| Anthropic / 兼容网关 message fallback | `model's maximum context length`、`model requires more context` | 在 Engine classifier 内识别为 context overflow |
| 本地或未知 provider message fallback | `total message token length exceed model limit`、`range of input length should be` | 在 Engine classifier 内识别为 context overflow |
| 非 overflow 负例 | 普通 400、认证失败、参数错误、rate limit、普通 `client_error`，以及只包含 `context` 但不表达长度超限的文本 | 不触发 compact，不产出 compaction-required fact |

矩阵约束：

- 结构化错误优先；当 provider 同时给出结构化 code 与 message 时，以明确 code / typed field 为准。
- message fallback 只属于 Engine / Runner classifier 的 provider 适配责任，且必须限定在可解释信号集合内；
  Host 不得读取普通 provider message 猜测 overflow。
- 每个正例只证明“需要 Host compact”的强类型事实，不得在 Engine 内 compact、retry、构造 memory 或重建 RunInput。
- 每个负例必须保持原有错误分类语义，避免把普通 client error 误判为可 compact 的 overflow。

### Host compact event 契约

P4 应新增或等价表达以下 Host-owned canonical facts：

- `context_overflow_observed`：Host 已观察到 Engine overflow trigger，记录来源 event cursor、attempt index、
  reason、预算快照或估算摘要；若记录 token 估算，必须带 estimator 算法标识。
- `context_compact_requested`：Host 决定尝试 compact，记录 compact attempt index、policy、source run input trace id。
- `context_compact_completed`：compact 成功，记录保留项、降级项、`before_estimated_size`、
  `after_estimated_size`、`reduced=True`、estimator 算法标识或等价强类型字段、source event cursors。
- `context_compact_failed`：compact 失败，记录失败原因、是否可再尝试。
- `context_attempt_retrying`：同一个 Run 将以 compacted RunInput 启动下一次 internal attempt。

这些 facts 均为 canonical，但 P4 不要求 projection / observer；P6 后续可以读取。

compacted RunInput 本身不是 canonical 用户输入事实，也不是第二条 raw user turn。它只能作为
`context_compact_completed` / `context_attempt_retrying` 等 compact 或 attempt retry facts 的派生结果、
internal trace，或新 internal attempt 的执行输入被表达；不得伪装成 `USER_INPUT_ACCEPTED`、display
transcript user message 或 memory raw user turn。

`context_compact_completed` 是允许 retry 的硬前置事实，不是“执行过 compact”的日志。只有同时满足以下条件
才能 append `context_compact_completed` 与后续 `context_attempt_retrying`：

- compacted RunInput 的 token / char 估算严格小于 compact 前 RunInput，估算方法必须以命名常量或强类型
  policy 标识记录在 trace / event data 中。
- 当前用户问题、pinned_state、必需 stable facts、evidence anchors、source cursor 与必要 tool facts 保真。
- 降级只发生在允许降级的 older raw turns、旧摘要、recall / retrieval 历史片段或非关键 warning / error 摘要上，
  且有可解释原因。

若 compact no-op、`after_estimated_size >= before_estimated_size`、compact 变长，或必须通过牺牲当前用户问题 /
pinned_state / evidence anchors / source cursor 才能变短，则必须 append `context_compact_failed` 或
`context_compaction_exhausted` 等价事实，并以 Host-owned `RUN_FAILED` terminal 收口；不得 append
`context_attempt_retrying`，也不得消耗下一次 Engine internal attempt。

### Host token estimator 契约

P4 的 compact before / after size、`RunInputBuildTrace.total_token_estimate`、compact trigger 判断与
effectiveness gate 必须使用同一套 Host 内部 token estimator，避免 RunInputBuilder 与 CompactCoordinator
各自用不同口径得出互相矛盾的预算结论。

estimator 的 P4 默认策略应以 OLD `conversation_memory` 的保守字符近似为强参考：

- 半角 / 窄字符按 `1` token unit 计入。
- 全角 / 宽字符按 `2` token units 计入，至少覆盖 `unicodedata.east_asian_width(char)` 为 `W` / `F`
  的字符。
- token units 按固定 `TOKEN_UNITS_PER_ESTIMATED_TOKEN` 或等价命名常量向上取整为 estimated tokens。
- 空文本估算为 `0`；非空但 unit 很小的文本至少估算为 `1` token。
- 常量、算法名、trace 字段名必须显式命名；禁止把 `4`、`2` 等估算参数散落成魔法数字。

边界：

- 该 estimator 只服务 Host compact / RunInputBuilder 的预算、排序与 before / after 相对比较。
- 它不是 provider tokenizer、不是模型窗口真源，也不替代 OpenAI / Anthropic / 本地 provider 的真实 token 计数。
- context overflow 的根因真源仍是 Engine / Runner provider classifier 产出的强类型 overflow /
  compaction-required fact；Host 不得因为 estimator 超预算就伪造 provider overflow。
- P3 `_APPROX_TOKEN_CHARS=4` 只能被视为 P3 临时粗估。P4 可以先保留旧字段以降低改动面，但
  `context_compact_completed(reduced=True)`、`context_attempt_retrying` 和 compact failed /
  exhausted 判断不得依赖该粗估作为最终依据。

### Compact 输入保真契约

compact 必须优先保留：

- 当前用户问题，即本 Run 的 `USER_INPUT_ACCEPTED`。
- `ConversationPinnedState` 全量 stable block。
- task frame、verified claims、assumptions。
- evidence anchors：至少保留 anchor id、source event cursor、tool_call_id、source_ref / chunk_ref / fingerprint /
  summary 中已存在字段。
- tool facts：工具名、tool_call_id、value summary、cursor fingerprint、has_more、error code 等中性摘要。
- 最近 raw turns 的语义代表。

Host Memory / compact memory 输出约束：

- Host Memory system block 是 internal grounding context / verification context，不是 final answer 模板、
  用户可见章节结构或“历史工具摘要”模板。
- Host Memory block 开头必须先包含 internal grounding / not output template 约束，再进入 `Tool Facts` /
  `Evidence Anchors` 或 compact 后等价摘要；不能把禁止原样输出的说明放在工具事实之后。
- 若存在 caller system prompt、Agent system prompt 或 app system prompt，Host Memory system block 必须作为
  后续 system context 追加在 caller system prompt 之后、当前 UserMessage 之前。compacted RunInput 重建时，
  caller system prompt 前缀保持不变，Host compact memory block 作为后续 system context 注入，然后才是当前
  UserMessage。
- 若 provider / payload builder 将多条 system message 合并为一条 provider payload，合并文本顺序必须保持
  caller system prompt 在前，Host Memory instructions + Host Memory / compact memory 在后；不得因合并而
  让 Host Memory 获得 caller system prompt 之前的语义位置。
- 顺序设计同时是 provider prefill cache / prompt cache 友好优化：caller system prompt 通常跨轮次更稳定，
  放在前缀有利于稳定前缀复用；Host Memory / compact memory 与工具事实每轮更容易变化，放在后面可降低稳定
  前缀失效概率。本 plan 只要求消息顺序与优化理由，不把任何具体 provider cache API 写成 P4 已落地能力。
- `Tool Facts` / `Evidence Anchors` 只能用于模型定位事实、校验证据、生成面向用户的引用或出处列表；
  不得作为用户可见正文段落被原样输出。
- final answer 可以输出面向用户的“证据与出处”、引用列表、页码 / chunk / source ref 等受控来源说明；
  但不得输出 Host 内部标题、字段或治理元数据，例如 `Host Memory`、`Tool Facts`、`Evidence Anchors`、
  `历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`tool args`、
  `tool result repr`、`scope_token` 或 raw EventLog metadata。
- compacted RunInput 继承同一约束：compact 可以保留 evidence anchors、source refs、tool fact summaries
  用于 grounding，但不得把它们整理成看起来应该展示给用户的历史工具摘要、内部事实表或调试字段清单。
- 若 compact 需要重写 memory block，提示层 / 渲染层必须继续显式标注 internal context 不可原样输出；
  不能只依赖工具摘要截断来避免泄漏。

可以降级但必须可解释：

- older raw turns。
- episode summary slot / 旧摘要。
- recall / retrieval 类历史片段。
- 非关键 warning / error 摘要。

禁止进入 compact 输入：

- reasoning delta / reasoning_content。
- runner content delta / preview content completed。
- 客户端 display timeline。
- ToolRuntime `scope_token`、cursor 原文、受控 handle。
- 未 append 的 request 对象历史 transcript。

Compact 输出语义：

- compacted RunInput 是 Host 从上述输入事实派生出的治理性 attempt 输入，只用于同一 Run 的下一次
  internal Engine attempt。
- compacted RunInput 中保留的当前用户问题必须能追溯回原始 `USER_INPUT_ACCEPTED` event cursor，
  不得生成新的 `USER_INPUT_ACCEPTED` 或新 raw user turn。
- 如果实现需要记录 compacted input 的摘要、hash、估算大小或降级说明，应使用 compact / attempt retry
  canonical facts 或 Host internal trace 表达，不得写成用户输入事件。

## 状态机变化

P4 仍不落地完整 P7 Run / Attempt 状态机，但需要在当前内存 harness 中表达最小 internal attempt loop：

```text
RUNNING(attempt 0)
  -> context_overflow_observed
  -> context_compact_requested
  -> context_compact_completed
  -> context_attempt_retrying
  -> RUNNING(attempt 1)
  -> SUCCEEDED / FAILED / CANCELLED / SUSPENDED
```

失败路径：

```text
RUNNING
  -> context_overflow_observed
  -> context_compact_requested
  -> context_compact_failed
  -> RUN_FAILED(source=HOST, error_code="context_compaction_failed" 或等价)
```

compact no-op / 变长 / 保真失败路径：

```text
RUNNING
  -> context_overflow_observed
  -> context_compact_requested
  -> context_compact_failed(reason="no_effective_reduction" / "would_drop_required_fact" / 等价)
  -> RUN_FAILED(source=HOST, error_code="context_compaction_failed" 或等价)
```

上限耗尽：

```text
RUNNING
  -> context_overflow_observed
  -> RUN_FAILED(source=HOST, error_code="context_compaction_exhausted" 或等价)
```

约束：

- public `run_id` 不变；attempt id / attempt index 是 Host internal。
- context overflow compact retry 会启动同一 Run 下的新 internal Engine attempt；它只消费 compacted RunInput，
  不再次 append `USER_INPUT_ACCEPTED`。
- P4 不新增 public `RECOVERING` 状态；若内部 trace / event 需要表达 retrying，使用 Host canonical fact。
- Engine stream 无 terminal 仍沿用 P3 Host-owned failure，不进入 compact retry。
- `context_attempt_retrying` 只能出现在有效 `context_compact_completed(reduced=True)` 之后；no-op、变长或保真失败
  不能进入 retry 状态。
- compact retry 后第一个真正 terminal event 才触发 memory projection；不得把中间 recoverable overflow failure
  投影为本 Run 最终 memory turn。
- memory projection 对本 Run 仍只能看到一条原始用户输入 canonical 真源，即最初 append 的
  `USER_INPUT_ACCEPTED`；不得把 compacted RunInput 投影成新的 raw user turn。

## 数据持久化 / schema 变化

P4 默认不做持久化 schema 变更：

- `InMemoryRunEventStore` 仍是单进程内存态临时实现。
- `InMemoryConversationMemoryStore` 仍是单进程内存态 projection。
- compact trace / compacted RunInput 可以保存在 harness 内部短期缓存，必须有容量上限。
- 不新增 workspace migration。

如果实施 Agent 判断必须改 schema，必须停止并修 plan，且按全新 schema 起库处理：

- NEW 按全新 schema 起库，不做旧库兼容读取。
- 必须说明是否需要将旧库迁移动作作为 `workspace_migrations` 插件进入 `dayu-cli init` 流程。

## 多进程并发影响

P4 不声明多进程正确性：

- attempt retry loop 只在当前 `LocalRunHarness` 单进程内存态成立。
- compact retry 的次数计数、trace 缓存与 attempt 输入重建不具备跨进程 fencing。
- 不实现 owner token、lease、startup recovery、orphan attempt 接管。
- P8 落地时必须把 P4 compact facts 纳入 attempt fencing / recovery 设计，避免两个 owner 对同一 Run 同时 compact
  并重试。

P4 代码不得把单进程 lock 或内存缓存写成生产并发真源。

## ToolRuntime / EngineWorker / Engine 边界影响

- ToolRuntime 不负责 compact；只继续提供工具执行、截断、fetch_more 与 canonical facts。
- compact 可消费 ToolRuntime facts，但不得读取 `scope_token`、cursor 原文或受控 handle。
- EngineWorker 只按 Host 传入的 compacted `StartRunRequest.input` 启动 Engine；不理解 compact policy。
- Engine 不持有 memory、transcript、RunInputBuilder trace、compact trace 或 retry policy。
- Engine 只需暴露 context overflow / compaction-required 事实；如需补 Engine 协作，必须是最小强类型事件 / 错误映射。
- P4 code review 必须检查没有从 Engine import Host compact / memory，也没有从 Host public API 暴露
  `EngineWorker.run_agent_messages` 或 `ToolExecutor.execute`。

## EventLog / RunEventStore / projection 影响

- context overflow / compact / retry decision 必须先 append 为 RunEvent，再驱动后续 stream 观察；不得只写日志。
- P4 不实现 projection / observer，但新增事件必须可被 P6 幂等读取。
- compact / retry facts 可以引用 compacted RunInput 的摘要、size、source cursors 或 trace id；不得通过新增
  `USER_INPUT_ACCEPTED` 表达 compacted input。
- recoverable overflow trigger 不应被 `get_run_result` 当作最终 terminal，除非 Host 已决定失败收口。
- 如果沿用 Engine terminal `RUN_FAILED(recoverable=True)` 作为 compact trigger，实施时必须避免
  `RunEventStore` terminal-after-append 拒绝后续 retry 事件；可选方案：
  - Engine 先发非 terminal `CONTEXT_COMPACTION_REQUESTED`，Host 消费后关闭该 attempt stream；
  - 或 Host translation 将该 recoverable failure 映射为非 terminal compact trigger event；
  - 或停止修 plan，重新定义 Engine / Host 事件契约。
- P4 不把 reasoning / preview 事件改为 canonical，也不让它们进入 projection。

## 可接受临时实现 / 不可接受临时实现

可接受临时实现：

- 单进程 `LocalRunHarness` 内部 attempt index 计数。
- deterministic compact，不调用 LLM 生成 episode summary。
- fake WorkerProxy 测试 Engine overflow 与 retry。
- compact trace 仅保留最近 N 次，使用有界内存缓存。
- 使用 Host 内部宽 / 窄字符 token estimator 作为 P4 最小预算判断，并在 trace / event data 中标明算法名与估算性质。
- 暂时保留 `_APPROX_TOKEN_CHARS=4` 供 P3 未迁移路径使用，但必须标明它是 P3 临时粗估，不能进入
  P4 compact effectiveness gate。

不可接受临时实现：

- 在 Engine 内直接调用 `_compact_messages` 或任何 Host memory 逻辑。
- Host 用字符串搜索普通错误文本猜测 context overflow，而不是消费 Engine / Runner 强类型分类。
- compact 从 display timeline、preview delta、reasoning、request.input 历史消息或旁路 transcript 取事实。
- compact no-op、估算变长、或无法保真当前用户问题 / pinned_state / evidence anchors 时仍 append
  `context_compact_completed` 或启动 retry。
- 使用 `_APPROX_TOKEN_CHARS=4` 作为 P4 compact before / after、trigger、effectiveness gate 或
  `context_attempt_retrying` 的最终判定依据。
- RunInputBuilder 与 CompactCoordinator 分别使用不同 token 估算口径，导致 trace total、compact size 与
  event data 不可比较。
- context overflow retry 时再次 append `USER_INPUT_ACCEPTED`，或把 compacted RunInput 写成新的用户消息、
  raw user turn、display transcript 用户输入。
- RunInputBuilder 或 compact memory block 把 Host Memory、Tool Facts、Evidence Anchors、历史工具摘要、
  tool args、tool result repr、cursor fingerprint、source event cursor、scope token 或 raw EventLog metadata
  渲染成可被模型误认为 final answer 正文模板的内容，且没有明确 internal-only / do-not-echo 提示保护。
- 把 tool cursor 原文、scope token、handle 写入 RunInput、memory 或 EventLog。
- 无限 retry 或无上限 compact。
- recoverable overflow failure 已被 store 当 terminal 后继续 append 事件。
- 为了兼容旧接口增加 wrapper / facade / re-export。
- 使用 `Any` / `object` / 开放 `dict` 承载 compact 契约。

## runtime dependency

P4 不涉及 lane，不新增 `dayu.runtime` 依赖。

若实施中需要通用取消等待 / race helper，应优先复用或扩展 `dayu.runtime`；但 compact、memory、attempt retry
policy 不得放入 `dayu.runtime`，因为它们属于 Host 上下文治理。

## 测试清单

必须新增 / 更新：

- `tests/host/test_phase4_context_compaction.py`
  - compact 保留 current user、pinned_state、verified claims、assumptions、evidence anchors、tool facts。
  - compacted RunInput 的当前用户问题可追溯到原始 `USER_INPUT_ACCEPTED`，且不会产生新的用户输入事实。
  - compacted RunInput 重建时保持 caller system prompt 前缀不变，Host compact memory block 位于其后，
    当前 UserMessage 位于最后。
  - older raw turns / old summaries 降级时 trace 记录原因。
  - compacted RunInput 的 token / char 估算严格小于 compact 前；event / trace 记录 before、after、reduced。
  - before / after size 使用 Host 内部 token estimator；中英文混合财报文本覆盖宽字符比 ASCII 文本更保守的估算。
  - 全部关键事实都不可降级导致 compact no-op 时，返回 failed / exhausted，不产出 completed，不启动 retry。
  - compact 若需要丢弃当前用户问题、pinned_state、evidence anchor 或 source cursor 才能变短，必须失败收口。
  - source event cursor / anchor id 在 compact 后 RunInput 中可追溯。
  - reasoning / preview / delta 不进入 compact 输入。
  - scope token / cursor 原文不进入 compact 输入。
  - compacted memory block 保留 evidence anchors / source refs / tool fact summaries 用于 grounding，但不会把它们
    渲染成面向用户展示的“历史工具摘要”模板或内部字段清单。
  - Host Memory / compact memory block 开头先出现 internal grounding / not output template 约束，再出现
    `Tool Facts` / `Evidence Anchors` 或等价摘要。
- `tests/host/test_phase4_run_input_ordering.py` 或就近 RunInputBuilder / payload builder 测试：
  - caller / Agent / app system prompt 存在时，`RunInput.messages` 顺序为 caller system prompt、Host Memory
    system context、当前 UserMessage。
  - compact retry 时，compacted RunInput 继承同一顺序：caller system prompt 前缀不变，Host compact memory
    block 在后，当前 UserMessage 最后。
  - 若 provider / payload builder 合并多条 system message，测试合并文本顺序仍为 caller system prompt 在前，
    Host Memory instructions + Host Memory / compact memory 在后。
  - 测试不得把具体 provider prefill cache / prompt cache API 当作已落地能力；只断言 prompt 稳定前缀顺序。
- `tests/host/test_phase4_overflow_retry.py`
  - Engine `CONTEXT_COMPACTION_REQUESTED` 触发 Host compact 后启动第二次 internal attempt 并成功。
  - 第二次 internal attempt 不再次 append `USER_INPUT_ACCEPTED`；同一 Run 内用户输入 canonical fact 仍只有一条。
  - compact 后仍 overflow，达到上限后 Host-owned `RUN_FAILED` 收口。
  - compact 失败时 append `context_compact_failed` 与 Host-owned failure。
  - Engine stream 无 terminal 仍走 P3 `engine_stream_ended_without_terminal`，不触发 compact。
  - recoverable overflow trigger 不污染 memory projection 为最终失败轮次。
- `tests/host/test_phase4_final_answer_semantics.py` 或就近 smoke / fake model 语义测试：
  - fake model 若试图 echo Host Memory section headings，final answer 路径必须能暴露该风险并让测试失败。
  - 覆盖 final answer 不应包含 `Host Memory`、`Tool Facts`、`Evidence Anchors`、`历史工具摘要`、
    `tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`tool args`、`tool result repr`、
    `scope_token` 或 raw EventLog metadata。
  - 覆盖允许的用户可见“证据与出处”或引用列表，确认语义来源可见但 Host 内部标题 / 字段 / 治理元数据不可见。
  - 至少在 code review gate 中检查测试断言覆盖 final answer 输出回显风险，而不只是检查 memory 是否被注入。
- `tests/host/test_phase4_eventlog.py`
  - overflow / compact / retry facts append 顺序稳定。
  - compacted RunInput 只通过 compact / attempt retry facts 或 internal trace 表达，不被记录成
    `USER_INPUT_ACCEPTED`。
  - terminal 后 store 拒绝追加仍成立。
  - `get_run_result` 只从最终 terminal 推导。
- `tests/host/test_phase4_boundary.py`
  - Host public `__all__` 不导出 compact coordinator / builder。
  - Engine 模块不 import `dayu.host`。
  - ToolRuntime 不新增 compact 职责。
- `tests/host/test_phase4_token_estimator.py` 或就近测试：
  - 覆盖 ASCII / 半角字符、中文 / 全角宽字符、中英文混合财报文本、空字符串。
  - 覆盖 token units 到 estimated tokens 的向上取整与非空最小值。
  - 覆盖 RunInputBuilder trace 与 CompactCoordinator before / after 使用同一 estimator 口径；若
    `_run_input_builder.py` 暂不迁移，则测试或文档必须明确 P3 `_APPROX_TOKEN_CHARS=4` 不参与 P4 gate。
- 如补 Engine 协作：
  - `tests/engine/test_phase*_context_overflow_contract.py` 或就近测试，覆盖 provider context overflow 识别只产出强类型事实，不做 Engine 内 compact/retry。
  - OLD provider overflow 信号回归矩阵必须逐项覆盖：结构化
    `context_length_exceeded`、`maximum context length is`、`context length exceeded`、
    `total message token length exceed model limit`、`model's maximum context length`、
    `range of input length should be`、`model requires more context`。
  - 覆盖普通 400 / 普通 client error / 非 overflow message 负例，确认不触发 compact。
  - 覆盖结构化错误优先与 message fallback 边界，确认 fallback 只在 classifier / adapter 内发生。
- README/docs 测试：
  - 若已有 README 断言测试，需要更新或新增断言，确保文档不写 P6/P7/P8/P9 已落地。

覆盖率要求：

- 新增非 `utils/` 单文件测试覆盖率目标 >= 80%。
- 若修改触及已有 pyright 报错，必须一并修复，至少不能扩散。

## 验证命令

实施 Agent 完成后至少运行：

```bash
source .venv/bin/activate && pytest tests/host/test_phase4_context_compaction.py \
  tests/host/test_phase4_overflow_retry.py \
  tests/host/test_phase4_eventlog.py \
  tests/host/test_phase4_boundary.py
```

回归受影响 Host 测试：

```bash
source .venv/bin/activate && pytest tests/host/test_phase1_5_run_harness_eventlog.py \
  tests/host/test_phase2_tool_runtime.py \
  tests/host/test_phase3_conversation_memory_projection.py \
  tests/host/test_phase3_run_input_builder.py \
  tests/host/test_phase3_boundary.py
```

如修改 Engine overflow 协作：

```bash
source .venv/bin/activate && pytest tests/engine
```

类型检查：

```bash
source .venv/bin/activate && pyright
```

手工 smoke：

```bash
source .venv/bin/activate && python utils/smoke_host_context_compaction.py --case fake-overflow --log-level DEBUG
```

若没有新增 smoke，实施完成汇报必须明确说明原因，并说明 P5 前是否补。

## README / docs 触发判断

P4 实施后必须检查并按职责更新：

- `dayu/host/README.md`：`dayu/host/` 修改触发。写当前 context overflow compact 执行路径、事件、retry 上限、
  未落地生产治理。
- `docs/host/design.md`：Host compact ownership 与 Engine 协作边界变化触发。写回 P4 后执行边界 / 执行路径。
- `tests/README.md`：新增 `tests/host/test_phase4_*` 触发。写 Host compact 测试分层与命令。
- `dayu/engine/README.md`：仅当 P4 修改 `dayu/engine/` 并落地 overflow 协作生产事实时更新；不得写 Engine
  支持 compact/retry。
- 根目录 `README.md`：仅当新增用户可见 CLI / smoke 命令属于用户手册职责时更新；纯内部 `utils/` smoke
  默认不需要写入根 README。

不做机械同步；只更新与当前代码事实不一致且属于目标读者职责的内容。

## review gate

P4 至少需要以下 review：

- plan review gate：确认目标、非目标、EventLog 真源、Engine / Host 边界、P4 不偷跑 P6-P9。
- OLD / NEW plan review gate：对照 OLD `async_agent._compact_messages`、OLD provider overflow detection、
  OLD `conversation_memory` compaction，确认只继承必要不变量，不机械迁回旧职责。
- Token estimator plan review gate：对照 OLD `conversation_memory` 的宽 / 窄字符 token units 算法，确认 P4
  plan 继承其保守估算思想，并明确它不是 provider tokenizer 真源。
- code review gate：常规代码风险、类型、测试、README/docs。
- OLD / NEW code review gate：重点审 compact 保真、工具调用组不拆散或等价事实保留、pinned_state /
  evidence anchors / source cursor 不丢失、Engine 内不 compact。
- Engine overflow classifier parity gate：对照 OLD provider overflow 信号逐项测试，确认 OpenAI / Anthropic /
  本地或未知 provider 的典型 overflow 信号被 Engine classifier / adapter 识别为强类型事实，普通 client error
  负例不误触发，Host 没有 provider 字符串匹配。
- Compact effectiveness gate：每次 `context_attempt_retrying` 前必须有
  `context_compact_completed(reduced=True)` 或等价事实证明 compact 后 RunInput 估算确实变短；no-op、变长、
  或保真失败必须 Host-owned failed terminal 收口。该 gate 必须使用 Host 内部宽 / 窄字符 token estimator，
  不得使用 P3 `_APPROX_TOKEN_CHARS=4` 粗估。
- Internal memory non-echo gate：确认 Host Memory system block、Tool Facts、Evidence Anchors 与 compacted
  tool fact summaries 只作为 internal grounding / verification context；提示层 / 渲染层明确禁止原样输出。
  final answer / fake model 语义测试必须覆盖内部 section heading、tool metadata、cursor fingerprint、
  source event cursor、scope token、tool args、tool result repr 不被 echo。若测试只验证 memory 注入而不验证
  输出回显风险，该 gate 不通过。
- System ordering / cache-prefix gate：确认 caller / Agent / app system prompt 存在时，Host Memory system
  block 与 compact memory block 总是追加在 caller system prompt 之后、当前 UserMessage 之前；若 provider /
  payload builder 合并 system message，合并文本顺序也保持 caller system prompt 在前，Host Memory
  instructions + Host Memory / compact memory 在后。review 必须检查没有把 Host Memory 放到 caller system
  prompt 前，导致语义优先级反转或 provider prefill cache / prompt cache 稳定前缀失效；同时不得把具体
  provider cache API 写成已落地能力。
- User input canonical source gate：确认 compacted RunInput 是从原始 `USER_INPUT_ACCEPTED` 与 canonical facts
  派生的治理性 attempt 输入；context overflow retry 不再次 append `USER_INPUT_ACCEPTED`，memory projection
  不把它当作新 raw user turn。
- import boundary / public API gate：确认 `dayu.runtime`、Engine、ToolRuntime、Host public API 边界未被污染。
- PR diff review gate：创建 PR 后审查 diff 是否只包含 P4 范围。

review 不通过时，实施 Agent 必须在对应 review 文档 finding 标题标注修复状态，再复审。

## 停止条件

遇到以下情况必须停止并回到 plan：

- 当前 Engine 无法产生任何强类型 context overflow / compaction-required 事实，且需要新增 Engine 协作契约。
- 无法在 Engine / Runner classifier / adapter 边界覆盖 OLD 多 provider overflow 信号矩阵，或只能靠 Host
  搜索普通 provider message 才能触发 compact。
- `RunEventStore` terminal 语义与 recoverable overflow trigger 冲突，无法在不破坏 terminal-after-append 规则下重试。
- compact 只能依赖 display timeline、reasoning、preview delta 或 request transcript 旁路才能工作。
- 实现需要把 compacted RunInput 伪装成新的 `USER_INPUT_ACCEPTED`、raw user turn 或 display transcript 用户输入。
- 无法保留 pinned_state、当前用户问题、证据锚点或 source cursor。
- compacted RunInput 在 token / char 估算上无法变短，或为了变短必须牺牲当前用户问题、pinned_state、
  evidence anchors、source cursor 等必保事实。
- 实现让 internal tool fact summary、Host Memory section heading、Tool Facts / Evidence Anchors 标题、
  cursor fingerprint、source event cursor、tool args、tool result repr、scope token 或 raw EventLog metadata
  进入 final answer 用户可见正文，或把 compacted tool facts 整理成应展示给用户的历史工具摘要。
- 实现把 Host Memory / compact memory 放到 caller system prompt 之前，或 system message 合并后文本顺序
  变成 Host Memory 在前、caller system prompt 在后，导致语义优先级与稳定 cache 前缀约束失效。
- 测试只检查 Host Memory / compact memory 已注入，不检查 final answer 或 fake model 是否 echo 内部标题、
  字段和治理元数据。
- 测试缺少 RunInput message ordering 断言，或缺少 system message 合并文本顺序断言。
- 无法抽取或复用统一 Host 内部 token estimator，只能继续用 `_APPROX_TOKEN_CHARS=4` 粗估判断 P4
  compact before / after、trigger 或 effectiveness。
- 需要持久 schema、多进程 lease / fencing、OutputContract / validation 才能继续。
- 需要把 compact policy 放进 Engine 或 `dayu.runtime`。
- pyright 需要通过 `Any` / `object` / ignore 绕过才能实现。

## 风险与回滚

主要风险：

- Engine 当前只保留 context compaction 契约草案，生产路径可能未产出 trigger，导致 P4 必须补最小 Engine 协作。
- recoverable overflow 如果被当前 Host 视为 terminal，会与 retry 后继续 append 冲突。
- deterministic compact 可能压缩不足，真实 provider overflow 仍失败；必须有上限与明确失败收口。
- token estimator 仍是近似值：宽 / 窄字符算法比 P3 `_APPROX_TOKEN_CHARS=4` 更适合中英文混合财报文本，
  但仍可能与 provider tokenizer 有偏差；真实 overflow 根因与模型窗口事实必须继续由 Engine / Runner
  provider classifier 给出。
- deterministic compact 可能因为必保事实占满预算而 no-op；这不是可重试成功条件，必须以可解释
  Host-owned failure 收口。
- 财报工具事实若摘要过粗，compact 后可能丢失证据定位；测试必须覆盖 source cursor / anchor id。
- Host Memory 当前以 system role message 进入模型上下文；即使工具摘要已截断，模型仍可能回显内部
  grounding 标题、tool metadata 或 compact 后摘要形态。P4 必须把 internal-only 标注、final answer
  语义测试和 review gate 作为共同保护，而不能把“结果被截断”当作充分安全条件。
- 单进程临时实现容易被误读为生产治理；README / design 必须明确未落地 P7 / P8。

回滚策略：

- P4 不改 schema，回滚可删除 `_context_compaction.py`、phase4 测试、smoke，并撤回 `_run_harness.py`、
  `_token_estimator.py`、`contracts.py`、`_event_translation.py`、`_run_input_builder.py` 的 P4 改动。
- 若补了 Engine overflow 协作，必须单独列出可回滚文件；不得影响已落地 continuation / terminal 语义。
- 回滚后 P3 多轮 memory、ToolRuntime、EventLog 行为必须保持原样。

## 待用户确认项

无。

## 迁移 Agent 实施完成汇报格式

实施 Agent 完成后按以下格式汇报：

```text
改动文件：
- ...

关键实现：
- overflow trigger 来源：
- compact 输入来源：
- compact 输出 / retry 上限 / token estimator：
- EventLog 新增事实：
- Engine / Host / ToolRuntime 边界：

验证：
- pytest ...
- pyright
- smoke（如有）

README / docs：
- 已更新：
- 未更新及原因：

风险 / 未覆盖：
- ...
```
