# Host P3 Handoff Plan：Conversation Memory / RunInputBuilder

## 目标

P3 目标是在 P1.5 `RunEventStore` 与 P2 Host-owned `ToolRuntime` facts 之上，强参考 GitHub issue
[#48 conversation_memory 多轮会话记忆子系统优化](https://github.com/noho/dayu-agent/issues/48) 与 OLD
`dayu/host/conversation_memory.py`，落地 Host 最小
Conversation Memory / RunInputBuilder，使同一 `Session` 内的下一轮 Run 可以从 canonical 事实构造
运行态输入，同时严格隔离客户端展示 read model。

本阶段必须产出：

- Host 内部最小 `RunInputBuilder`：只消费可进入运行态的 canonical RunEvent 与受控 memory projection。
- Host 内部最小 Conversation Memory：包含 `pinned_state`、memory pool、结构化 tool facts projection 与最近轮
  user / final answer 回放。
- Host-owned canonical 用户输入真源：新增 `USER_INPUT_ACCEPTED` RunEvent，append-before-engine / run stream；
  memory projection、display timeline、RunInputBuilder、replay 均只能从 EventLog 读取该事件里的用户输入。
- Host 中立强类型 memory 预留：P3 至少定义并承载 / 投影 / 透传 `EvidenceAnchor`、`MemoryClaim`、
  `ClaimStatus`、`TaskFrame`、`AssumptionRegister`、`UserPreferenceProfileRef` 或等价 slot；不得把财报业务语义
  抽取逻辑塞进 Host。
- 已验证事实账本与 assistant history 分离：assistant final answer 只能作为 raw turn / assistant conclusion
  回放，不能自动升级为 verified claim；只有 tool fact、evidence-backed projection、user-confirmed correction
  可进入 verified claim ledger。
- 最小 Session memory store / projection：服务 P5 单进程顺序多轮 smoke，不宣称持久化、多进程恢复或完整
  lifecycle governance。
- 明确 public / internal 边界：public 只暴露 Run 级或 Session 级必要契约；projection / store / builder 均为
  Host internal。
- preview / reasoning / delta 隔离测试：它们只能进入展示 read model，不得进入 `RunInput` replay、memory pool
  或 RunInputBuilder 运行态输入。
- issue #48 结构兼容性：P3 可以不实现完整 #48 参数、compaction、episode summary，但最小内存结构与
  RunInputBuilder 输入顺序必须与 #48 不变量兼容，后续 P4+ 不应为接入 #48 方案推倒重来。
- OLD / NEW 语义差异测试：证明 P3 继承 OLD 的运行态 / 展示态分离、pinned_state 独立路径、tool summary
  作为独立结构化事实参与 memory 的可靠语义，但不迁回 OLD Engine 内 context / transcript / compaction 做法。
- internal-only `RunInputBuildTrace`：记录 included / excluded facts、裁剪原因、source id、估算 char / token
  size；它不得进入 RunInput，也不得进入 memory pool。

## 非目标

P3 不实现以下能力：

- P4 context overflow compact / retry，不实现 compaction scene、episode 压缩 LLM、context overflow 后 attempt
  重建。
- P6 持久 EventLog、persistent projection、observer checkpoint、timeline projection、tool trace observer、
  audit observer。
- P7 `client_request_id` 幂等、同 Session active Run admission、完整 Session / Run lifecycle governance。
- P8 attempt lease / fencing / 多进程 recovery。
- P9 Reply Outbox。
- P10 RemoteProxy / RemoteStub。
- P11 wait / suspend / resume 协作。
- 业务工具迁移、ToolRegistry、财报文档语义或 `dayu.fins.storage` 以外的财报存取路径。
- Host 内自动抽取完整财报语义，例如公司、期间、口径、单位、准则、XBRL fact 的业务解释；这些由
  fins / tool facts 产生，Host 只承载中立 claim / evidence / scope / provenance。
- LLM-facing `fetch_more` schema 或 `fetch_more_args` projection。
- 把 assistant final answer 自动写入 verified claim ledger。
- public memory edit / forget / reset API、持久治理、审计 UI；P3 只预留内部 patch / event 形状。
- 把 OLD `ConversationCompactionCoordinator`、`ConversationRuntimeProtocol`、scene preparation、Agent builder、
  trace recorder 或 file archive 机械搬回 NEW。

## 前置条件

- P1、P1.5、P2 已合入 `main`。
- 当前分支为 `codex/host-p3-conversation-memory`。
- 当前 `dayu.host` 已落地：
  - `RunEventStore` append-before-stream、per-run cursor、canonical / preview 分层。
  - `RunEventType` 中 Engine lifecycle / tool / final answer / reasoning delta / content delta 以及 P2 ToolRuntime facts。
  - `ToolRuntime` 截断与 `fetch_more` facts 写入 canonical RunEvent，`scope_token` 不进入 EventLog / Engine projection。
  - `RunInput` 当前只承载 Engine 可直接消费的 messages，不包含 memory / timeline / run input builder 语义。
- OLD 直接证据：
  - GitHub issue #48 是 P3 Conversation Memory 的强参考来源，不是泛泛 OLD 背景材料。P3 plan review
    与后续 code review 必须逐条对照 #48 的设计不变量。
  - `dayu/host/conversation_session_archive.py` 已把 `runtime_transcript` 与 `history_archive` 分离，`assistant_reasoning`
    仅展示，禁止参与运行态。
  - `dayu/host/conversation_memory.py` 已证明 `pinned_state` 独立渲染、episode / raw turn / tool summary 可构造
    conversation memory。
  - `ConversationPinnedStatePatch` 的 `None` / 空值 / 非空值三态语义用于避免 LLM 漏字段污染 pinned state。
  - `_render_tool_summary_block` 将工具摘要作为 assistant 历史的一部分参与 working memory，但不回放完整大结果。
- OLD 强参考代码：
  - `dayu/host/conversation_memory.py`、`dayu/host/conversation_store.py`、
    `dayu/host/conversation_session_archive.py`、`dayu/host/scene_preparer.py` 是 P3 plan review 与后续
    code review 的强参考。review 不能只看命名相似，必须审“语义声称”和“实际实现逻辑”是否错开。

## 架构边界

分层仍固定为：

```text
UI -> Service -> Host -> Engine
```

P3 后的运行态输入构造边界：

```text
Session id + new user input
  -> Host RunInputBuilder
      -> RunEventStore canonical events
      -> ToolRuntime canonical facts
      -> Host internal memory projection
      -> Host-owned canonical USER_INPUT_ACCEPTED event
  -> RunInput(messages=...)
  -> LocalRunHarness / LocalProxy / EngineWorker
  -> Engine
```

展示读取边界：

```text
RunEventStore canonical + preview events
  -> Host internal display read model
  -> future list_session_timeline / tests
```

边界规则：

- RunInputBuilder / MemoryManager 属于 Host，Engine 只消费最终 `RunInput.messages`，不理解 session memory、
  pinned_state、tool facts projection 或 timeline。
- Host 不得绕过 P1.5 `RunEventStore` 直接制造独立 transcript 真源；memory projection 只能从已 append 的
  `RunEvent` 推导，或从本阶段明确定义的 Host memory store 读取。
- 用户输入的 canonical 真源必须是 Host-owned `USER_INPUT_ACCEPTED` RunEvent。该事件必须在 Engine run
  stream 开始前 append，且 display timeline、memory projection、RunInputBuilder、replay 读取用户输入时必须同源
  读取 EventLog；不得从 preview stream、客户端展示 transcript 或旁路 request 对象二次拼装。
- `list_session_timeline` 若本阶段新增，只能返回展示 read model；它不是 RunInputBuilder 输入，也不是 memory pool
  真源。
- `reasoning` / preview `delta` / content completed preview 只能进入展示 read model；不得进入
  `RunInput` replay、Memory pool、RunInputBuilder 运行态输入或 RunResult 推导。
- `pinned_state` 是 Host internal memory projection 的稳定输入，不作为 Engine state，不由 Engine 更新。
- `ToolRuntime` 的 `scope_token`、cursor 原文与受控 `ToolFetchMoreHandle` 不进入 memory pool；RunInputBuilder
  只能消费 canonical facts 中可观察的中性摘要，例如 tool name、tool_call_id、cursor fingerprint、value summary、
  completed chunk summary。
- Tool facts / evidence anchors 必须作为独立 memory 槽位进入 RunInputBuilder memory block，不得混进 assistant
  history 文本；assistant history 只承载用户与助手可回放 raw turn。
- Memory item 必须带 source / provenance / trust 元数据：至少包含 `source_run_id`、`source_event_cursor`、
  `producer_kind`、`ingestion_policy`、`scope`。P3 默认只接纳主 session canonical facts；subagent / compaction /
  background run 的 facts 即使未来出现，也必须通过显式 ingestion policy 降级或转换后才能进入 memory。
- P3 只实现 `session` scope，但类型上必须预留 `direct_user`、`group`、`project`、`user` 等后续扩展；不同
  `session_id` 的 memory 必须测试证明不串读。
- `dayu.runtime` 不承载 Conversation Memory / RunInputBuilder；这是 Host 运行事实与上下文治理，不是层中立
  runtime helper。

## 文件级改动清单

计划新增：

- `dayu/host/_conversation_memory.py`
  - 定义 Host internal memory projection 数据类：`ConversationPinnedState`、`ConversationMemoryTurn`、
    `ConversationToolFact`、`ConversationMemorySnapshot`、`ConversationMemoryPatch` 等。
  - 定义 Host 中立强类型槽位：`EvidenceAnchor`、`MemoryClaim`、`ClaimStatus`、`TaskFrame`、
    `AssumptionRegister`、`UserPreferenceProfileRef` 或等价 slot。P3 可以只承载、投影、透传这些结构，不做
    Host 内财报语义自动抽取。
  - 所有可进入 memory 的 item 必须携带 provenance / trust / scope 元数据：`source_run_id`、
    `source_event_cursor`、`producer_kind`、`ingestion_policy`、`scope`。
  - 预留 internal-only lifecycle patch / event 形状：`memory_reset`、`claim_correction`、`scope_clear` 或等价
    结构；P3 不实现 public API、持久治理或 UI。
  - 定义 `ConversationMemoryStore` protocol 与 `InMemoryConversationMemoryStore`。
  - 定义从 canonical RunEvent 投影 memory snapshot 的最小逻辑。
- `dayu/host/_run_input_builder.py`
  - 定义内部 `RunInputBuilder` protocol 与默认实现。
  - 将 `ConversationMemorySnapshot`、当前 run 的 `USER_INPUT_ACCEPTED` event 和原始 `RunOptions` 构造成新的
    `RunInput.messages`。
  - 明确过滤 preview / reasoning / delta / display-only 字段。
  - 定义 internal-only `RunInputBuildTrace` 或等价诊断对象，记录 included / excluded facts、裁剪原因、
    `source_run_id`、`source_event_cursor`、估算 char / token size；诊断对象不得进入 RunInput 或 memory pool。
  - 实现 recent floor 安全裁剪：最近轮必须有语义代表，但超大旧轮不得全文无限保底，应降级为 user intent、
    assistant final 摘要和 evidence anchors。
- `tests/host/test_phase3_conversation_memory_projection.py`
  - 验证 `USER_INPUT_ACCEPTED`、canonical final answer、ToolRuntime facts 可进入 memory projection。
  - 验证 preview / reasoning / delta 不进入 memory projection。
  - 验证 assistant final answer 不会自动升级为 verified claim；只有 tool fact、evidence-backed projection、
    user-confirmed correction 可进入 verified claim ledger。
  - 验证 memory item 记录 `source_run_id`、`source_event_cursor`、`producer_kind`、`ingestion_policy`、`scope`，
    且默认只接纳主 session canonical facts。
  - 验证不同 `session_id` 的 memory 不串读。
- `tests/host/test_phase3_run_input_builder.py`
  - 验证 stable frame / pinned_state 独立进入 system memory block，最近轮 user / final answer 按顺序进入 messages。
  - 验证 tool facts 只以摘要进入，不含 `scope_token`、cursor 原文或完整大结果。
  - 验证 memory block 内部顺序为 stable frame / verified claims / assumptions / evidence anchors /
    recent raw turns / older pool / episode summary 插入位。
  - 验证 tool facts / evidence anchors 不混入 assistant history。
  - 验证 `RunInputBuildTrace` 记录 included / excluded facts、裁剪原因、source id、估算 char / token size，且不进入
    RunInput 或 memory pool。
  - 验证超大 recent raw turn 被语义降级，不挤占当前财报材料 / 工具结果窗口。
- `tests/host/test_phase3_multiturn_smoke.py`
  - 最小单进程、单调用方、顺序多轮 smoke：第一轮 terminal 后，第二轮 RunInputBuilder 可看见第一轮
    canonical final answer 与 tool summary。
- `tests/host/test_phase3_boundary.py`
  - 验证 Host public API 不导出 internal store / builder，Engine 不 import Host memory。
  - 验证 `RunInput` replay 不包含展示 reasoning。

计划修改：

- `dayu/host/contracts.py`
  - 增加最小 Session / memory public 请求与结果类型；若不需要新增 public API，则只增加内部 data union 所需强类型。
  - 增加表达用户输入被接纳为 Run 初始事实的 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent data；该
    event 是用户输入唯一 canonical 真源，必须 append-before-engine / run stream。
  - 增加 Host 中立 memory 强类型、scope 枚举、producer / ingestion policy 枚举、build trace 所需类型时，必须保持
    封闭联合，禁止 `dict[str, Any]`。
- `dayu/host/_run_harness.py`
  - 注入 `ConversationMemoryStore` 与 `RunInputBuilder`。
  - 在 `start_run` 前为同 Session 的新 Run 构造 `RunInput`，或新增内部 `start_session_run` 测试入口承接
    Session + user_text 到 RunInput 的转换。
  - 在 Run terminal 后，把 canonical 事件投影到 memory store；投影必须以 RunEventStore 为事实来源。
- `dayu/host/_event_translation.py`
  - 新增 `USER_INPUT_ACCEPTED` Host-owned event 的 canonical 分类，并补充 memory projection 相关分类。
- `dayu/host/__init__.py`
  - 只导出必要 public 契约；不得导出 `_conversation_memory`、`_run_input_builder`、store 或 builder 实现。
- `dayu/host/README.md`
  - P3 代码落地后更新当前事实：Conversation Memory / RunInputBuilder 已落地的最小能力与未落地能力。
- `docs/host/design.md`
  - P3 代码落地后写回 RunInputBuilder 可消费事实、display read model 隔离、preview / reasoning 禁止流回运行态。
- `tests/README.md`
  - P3 代码落地后补 Host Conversation Memory 测试分层与验证命令。

不计划修改：

- `dayu.engine.*` 生产代码。
- `dayu.runtime.*`。
- `dayu.fins.*`。
- `dayu.service.*`、`dayu.ui.*`。

## 新增 / 修改契约

### RunInputBuilder 可消费事实

RunInputBuilder 只可消费以下 facts：

- 已 append 的 canonical RunEvent：
  - 用户输入接纳事实：必须是 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent。该事件必须 append-before-engine /
    run stream，携带 `session_id`、`run_id`、`turn_id`、normalized user text 与 scope metadata。若实施中发现无法
    新增该 event，必须停止修 plan，不得退回 `StartRunRequest.input` 旁路投影。
  - `FINAL_ANSWER`：只消费终态 final answer，不从 `RUNNER_CONTENT_DELTA` 或 `RUNNER_CONTENT_COMPLETED` 拼接回答。
    `FINAL_ANSWER` 只能进入 recent raw turn / assistant conclusion，不得自动进入 verified claim ledger。
  - `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`：只消费 Engine 已接纳的结构化工具调用 / 工具结果摘要。
  - P2 ToolRuntime facts：`tool_result_truncated`、`tool_cursor_issued`、`tool_fetch_more_completed`、
    `tool_fetch_more_failed`、`tool_cursor_expired`、`tool_cursor_denied` 等中性摘要。
  - warnings / errors / provider protocol error：只以中性摘要进入 memory，且不得替代终态结果。
- Host internal memory projection：
  - stable frame / `pinned_state`：当前主任务、task frame、已确认对象、用户约束、未决问题。
  - verified claim ledger：只接纳 tool fact、evidence-backed projection、user-confirmed correction；不接纳
    assistant final answer 自动升级。
  - assumption register：承载未验证假设、用户临时假设、后续纠错状态。
  - memory pool：最近若干轮 user / final answer raw turn，以及更老历史 pool；raw turn 只提供会话连续性，不是
    verified fact 真源。
  - tool facts projection：工具名、tool_call_id、摘要、value size、cursor fingerprint、has_more、error code 等。
  - evidence anchors / source references：必须有强类型 `EvidenceAnchor` 或等价中立结构，包含 `anchor_id`、
    `origin_event_cursor`、`tool_call_id`、`source_ref`、`chunk_ref`、`fingerprint`、`summary` 等字段；字段可以
    为空或不完整，但类型不能缺失，且不得由 Host 臆造财报语义。
  - user preference profile ref / slot：P3 只预留引用或槽位，不实现跨 session durable preference memory。

### Host 中立 memory 强类型预留

P3 必须预留以下 Host 中立结构，字段名可随实现调整，但语义不可缺失：

- `EvidenceAnchor`：证据锚点，至少承载 `anchor_id`、`origin_event_cursor`、`tool_call_id`、`source_ref`、
  `chunk_ref`、`fingerprint`、`summary`。Host 不解释公司、期间、口径、单位、页码、XBRL fact 等财报语义；这些
  可以由 fins / tool facts 作为 opaque typed reference 放入 anchor。
- `MemoryClaim`：事实或结论条目，至少承载 `claim_id`、`status`、`source_run_id`、`source_event_cursor`、
  `evidence_anchor_id`、`scope`、`created_at`、`supersedes`。P3 不要求自动生成财报 claim，但 verified claim
  ledger 必须有这个接入点。
- `ClaimStatus`：封闭状态枚举，至少预留 `verified`、`assumption`、`assistant_conclusion`、`superseded`、
  `rejected`、`stale`。只有 `verified` 可作为已验证事实注入对应 ledger。
- `TaskFrame`：当前任务框架槽位，承载实体、期间、比较基准、口径、单位等 opaque references；P3 可为空或由测试
  seed，不在 Host 内做财报规则抽取。
- `AssumptionRegister`：未验证假设与用户临时假设槽位，支持后续纠错 / supersession。
- `UserPreferenceProfileRef`：用户偏好 profile 引用或 slot；P3 不跨 session 自动召回，不隐式作用于 headless /
  one-shot Run。

所有 memory item 都必须带 `source_run_id`、`source_event_cursor`、`producer_kind`、`ingestion_policy`、`scope`。
P3 默认 ingestion policy 只接受主 session canonical facts；内部 helper、subagent、future compaction、background run
不得默认进入主 session memory。

### Scope / privacy 预留

P3 只实现 `session` scope，store key 必须至少包含 `session_id`。类型上必须预留 `direct_user`、`group`、
`project`、`user` 等后续扩展，以及 `owner_ref`、`project_ref`、`visibility` 等可空强类型字段。

P3 不实现 group / direct / project 策略，不实现 UI 查看、删除或权限检查；但测试必须证明不同 `session_id` 不会
互相读写 memory。

### Verified claim 规则

- assistant final answer 不是事实真源，不能自动升级为 verified claim。
- tool fact 可在 evidence anchor 完整或策略允许时进入 verified claim ledger。
- evidence-backed projection 可进入 verified claim ledger，但必须保留 anchor id 与 source event cursor。
- user-confirmed correction 可进入 verified claim ledger，并应通过 `supersedes` 或等价字段覆盖旧 claim。
- warnings / errors / provider protocol error 不得替代 verified claim。

### RunInputBuildTrace

RunInputBuilder 必须产出 internal-only build trace 或等价诊断，至少记录：

- included facts / excluded facts。
- exclusion reason，例如 budget、scope mismatch、producer policy、missing evidence、oversized raw turn。
- `source_run_id`、`source_event_cursor`、anchor / claim id。
- pinned_state、verified claims、assumptions、tool facts、raw turns、older pool、episode summary 插入位的估算
  char / token size。
- budget limit 与裁剪后总估算 size。

该 trace 只用于测试和 future audit observer；不得序列化进 RunInput，不得写入 memory pool，不得作为下一轮
projection 真源。

### 只进入展示 read model 的事实

以下事实只允许进入展示 read model：

- `RUNNER_CONTENT_DELTA`。
- `RUNNER_REASONING_DELTA`。
- `RUNNER_CONTENT_COMPLETED`。
- 可展示 reasoning 文本。
- 面向客户端的 tool 展示摘要、warnings / errors 展示字段。
- timeline 排版、流式状态、debug sampling、trace-only payload。

展示 read model 不得作为 RunInputBuilder 输入；测试必须覆盖“展示可见但运行态不可见”的差异。

### 禁止进入运行态的字段

以下字段必须被显式禁止进入 `RunInput` replay、Memory pool 与 RunInputBuilder 运行态输入：

- reasoning / 思考过程。
- preview delta / content delta / reasoning delta。
- `scope_token`。
- ToolRuntime cursor 原文。
- `ToolFetchMoreHandle`。
- 完整大工具结果 payload。
- trace-only / audit-only / debug payload。

### Conversation Memory 最小 Host 边界

public：

- 如果需要新增 public，优先只新增 Session 级只读 snapshot / timeline 读取契约，且返回展示 read model。
- `start_run` 仍是 Run 入口；P3 不把 `RunInputBuilder.build`、`MemoryStore.append`、`Projection.apply` 暴露为 public API。

internal：

- `ConversationMemoryStore` / `InMemoryConversationMemoryStore`。
- `RunInputBuilder` / 默认实现。
- `ConversationMemoryProjection`。
- `ConversationMemorySnapshot` 与 patch / apply 逻辑。
- display read model store / projector，若本阶段为测试新增，也必须 internal。

### issue #48 兼容内存结构

P3 不一定实现完整 issue #48 参数面、compaction 触发、episode summary 生成或 `conversation_compaction`
scene，但最小内存结构和 RunInputBuilder 输入顺序必须与 #48 兼容，不能设计成 P4+ 接入 #48 时需要推倒重来。

必须保留的 #48 关键设计不变量：

- `pinned_state` 永远全量进入 RunInputBuilder 的 `[Conversation Memory]` system block，不参与 token pool
  竞争，不因 memory pool 裁剪而丢失。
- 历史 memory 是单总池：除 `pinned_state` 与最近 N 轮 raw turn 保底外，更老 raw turn、tool summary /
  tool facts 摘要、后续 episode summary 都应共享同一历史 pool 语义；P3 可以先用最小 pool，但不能设计成
  working / episodic 双独立预算池。
- 最近 N 轮 raw turn 是语义反退化下限保底，不是上限，也不是超大旧轮全文无限保底；P3 可以固定一个很小的
  默认 floor，但不得引入“最多 N 轮”的天花板语义。单轮超过安全阈值时必须降级为 user intent、assistant final
  摘要与 evidence anchors，不能挤占当前财报材料 / 工具结果窗口。
- memory 要克制：RunInputBuilder 不应为了多轮历史挤占财报材料、检索结果和工具结果窗口；P3 的默认
  裁剪策略应倾向保留最小可用历史，而不是扩大 memory 直到占满上下文。
- compaction、token budget、episode summary、`confirmed_facts`、`ConversationPinnedStatePatch` 三态合并可后移
  P4 或后续 phase，但 P3 的数据结构必须预留它们的接入点，例如 pinned_state 独立区、历史单总池顺序和
  episode summary 插入位置。

RunInputBuilder 的最小输入顺序必须兼容 #48：

```text
system prompt
-> [Conversation Memory]
   -> stable task frame / pinned_state（全量，独立）
   -> verified claim ledger（tool fact / evidence-backed / user-confirmed only）
   -> assumption register
   -> evidence anchors / tool fact summaries
   -> history pool（单总池语义）
      -> 最近 N 轮 raw turn 语义保底
      -> 更老 raw turn 按预算从新到旧
      -> 后续 episode summaries 插入位
-> current user message
```

如果实施 Agent 认为 P3 需要偏离该顺序、把 tool facts / evidence anchors 混进 assistant history、把 assistant
final answer 自动升级为 verified claim，或把最近 N 轮实现成上限 / 无限 token 保底，必须停止并提交 plan 修订。

### OLD 行为继承 / 后移 / 禁止迁回

P3 必须继承：

- `runtime_transcript` 与 `history_archive` 分离的设计：运行态输入与展示历史不是同一真源。
- reasoning 只进入展示历史，不进入运行态 transcript / messages / memory。
- `pinned_state` 独立路径：进入 RunInputBuilder system memory block，不参与 memory pool 竞争。
- tool summary 参与 memory，但只能作为独立 tool facts / evidence anchors 槽位的摘要和结构化 facts，不是完整工具
  大结果，也不得沿用 OLD 方式混进 assistant history。
- 最近轮 raw turn 作为语义反退化下限保底进入上下文，保证追问连续性；不得把它误实现为最大回放轮数或超大旧轮
  全文无限保底。
- issue #48 的单总池方向：P3 即使只实现最小 pool，也必须避免 working / episodic 双独立池语义回潮。

P3 后移：

- episode summary / compaction LLM / token budget 参数 / `ConversationPinnedStatePatch` 三态合并落地到 P4
  或后续明确 phase；P3 结构必须为它们留出兼容位置。
- context overflow compact 与 retry。
- persistent archive、file lock、workspace migration。
- conversation label、CLI session registry、clear history 五真源补偿。
- retrieval index / durable memory。

P3 禁止迁回：

- 不把 RunInputBuilder、memory projection、compaction 或 pinned_state 更新迁回 `dayu.engine`。
- 不恢复 OLD Engine 内 `TruncationManager` 或 LLM-facing `fetch_more` 半协议。
- 不恢复 OLD scene preparation / Agent builder 对 Host memory 的强耦合。
- 不把 `assistant_reasoning` 放回运行态 transcript。

## 状态机变化

P3 不引入完整 P7 Session / Run 状态机。

当前最小 Run 状态仍为：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

P3 只增加 memory projection 的派生时机：

```text
StartRunRequest accepted
  -> append canonical USER_INPUT_ACCEPTED
  -> build RunInput from EventLog + current session memory snapshot
  -> start Engine run stream
Run terminal canonical event appended
  -> project canonical facts into Session memory snapshot
  -> next sequential Run may build context from snapshot
```

约束：

- projection 失败不得伪造 Run terminal 状态；应返回 typed failure 或让测试 harness 明确失败。
- P3 smoke 只允许“上一轮 terminal 后启动下一轮”的顺序路径。
- 不实现同 Session active Run admission；如果调用方并发启动同 Session 多个 Run，P3 不承诺正确仲裁。
- `USER_INPUT_ACCEPTED` append 失败时不得启动 Engine；否则用户输入、display timeline、memory projection 与 replay
  会产生不同真源。

## 数据持久化 / schema 变化

P3 不引入持久化 schema，不修改 workspace schema，不新增 migration。

原因：

- 本阶段只服务 P5 单进程顺序多轮 smoke，最小 store 可以是 in-memory。
- P6 才落地 persistent EventLog / projection / observer。
- P7 / P8 才处理 lifecycle governance 与多进程 recovery。

如果实施 Agent 认为必须新增 schema，必须先停止并提交 plan 修订。若后续 schema 变更被批准，必须按全新
schema 起库处理，不做旧库兼容读取；是否进入 `workspace_migrations` 的 `dayu-cli init` 流程由修订计划明确。

## 多进程并发影响

P3 不提供多进程正确性。

允许的临时语义：

- `InMemoryConversationMemoryStore` 仅在单进程、单调用方、同一事件循环内提供一致性。
- P3 测试只验证顺序多轮，不验证并发 Run admission。
- projection 可使用单进程锁保护同一 store 的内存更新。

必须明确的限制：

- 不能把 in-memory store 描述为生产级 Session memory。
- 不能依赖单进程锁宣称解决跨进程 Session 顺序。
- 不能加入隐藏队列模拟 P7 admission policy。
- 如果同 Session 多个非终态 Run 并发，P3 可以拒绝或标记 unsupported，但不能静默合并 memory。

## ToolRuntime / EngineWorker / Engine 边界影响

- EngineWorker 不新增 public API；`EngineWorker.run_agent_messages` 仍不可被 UI / Service 直接调用。
- Engine 不 import `dayu.host`，不感知 Conversation Memory / RunInputBuilder / ToolRuntime。
- ToolRuntime facts 进入 RunInputBuilder 的路径只能是 canonical RunEvent 或其 projection；不能由
  RunInputBuilder 直接读取 ToolRuntime cursor store。
- RunInputBuilder 不持有 `ToolFetchMoreHandle`，不读取 `scope_token`，不触发 `fetch_more`。
- `fetch_more` 后续是否影响下一轮 memory，只能通过已 append 的 canonical `tool_fetch_more_completed` 等事实体现。

## EventLog / RunEventStore / projection 影响

P3 必须复用 P1.5 / P2 的事实层：

- memory projection 从 `RunEventStore.list_events(run_id, after=None)` 或等价已 append 事件读取。
- projection 应记录已处理到的 run / cursor，但 P3 可在 in-memory store 中保存；P6 再持久化 checkpoint。
- preview events 可以进入 display read model，但不得进入 memory projection。
- terminal 后 `RunEventStore` 拒绝继续 append 的约束不变；memory projection 不能通过追加 post-terminal 事件补事实。
- P3 必须新增 user input canonical `USER_INPUT_ACCEPTED` event，保证 append-before-engine / run stream，并在
  `_event_translation.py` 或等价分类逻辑中标为 canonical。
- `USER_INPUT_ACCEPTED` 是 memory projection、display timeline、RunInputBuilder、replay 的用户输入同源真源；
  测试必须覆盖这些路径读取同一 event cursor。

## 可接受临时实现 / 不可接受临时实现

可接受：

- in-memory ConversationMemoryStore / display read model store。
- 单进程顺序 projection，P5 smoke 专用。
- 简单 token / 字符预算，仅用于最小 memory pool 裁剪；不实现 P4 overflow compact。
- 最小 pinned_state 手工 patch / request 字段，前提是强类型且由 Host public / internal 契约显式表达。
- 最小 `session` scope 与 in-memory store key；类型预留 direct / group / project / user scope 但不启用策略。
- internal-only build trace，用于测试 included / excluded facts、裁剪原因与估算 size。
- internal-only memory reset / claim correction / scope clear patch 形状，作为后续生命周期治理接入点。
- 测试 harness 内部装配 fake events / fake tool executor。

不可接受：

- 绕过 RunEventStore 写旁路 transcript 真源。
- 从 preview delta 拼 final answer。
- 从 `StartRunRequest.input`、display transcript 或 preview stream 旁路投影用户输入，绕过 `USER_INPUT_ACCEPTED`。
- reasoning 进入 RunInput、memory pool 或 RunInputBuilder。
- assistant final answer 自动升级为 verified claim。
- tool facts / evidence anchors 拼进 assistant history，而不是独立槽位注入 memory block。
- `scope_token`、cursor 原文、完整大工具结果进入 memory。
- 使用 `Any`、`object`、开放 dict payload 作为契约逃生口。
- 为 OLD 导入路径创建兼容 wrapper / re-export。
- 在 `dayu.runtime` 放 Host memory / projection / RunInputBuilder。
- 在 `dayu.engine` 实现或引用 Conversation Memory。
- 提前实现 P4 / P6 / P7 / P9 能力并混入 P3。

## runtime dependency

P3 不涉及 lane，不新增 `dayu.runtime` 依赖。

若实施中需要等待 / race helper，应先检查 `dayu.runtime` 是否已有层中立 helper；只有纯运行期、无 Host 语义的
helper 才可复用或扩展 `dayu.runtime`。Conversation Memory、RunInputBuilder、projection checkpoint 均不得放入
`dayu.runtime`。

## 测试清单

新增 / 修改测试必须覆盖：

- `USER_INPUT_ACCEPTED` 是用户输入 canonical 真源：append-before-engine / run stream；memory projection、
  display timeline、RunInputBuilder、replay 都从 EventLog 读取同一个 event cursor。若不能新增该事件，停止修
  plan，不写替代实现。
- RunInputBuilder 消费 canonical final answer，不消费 content delta / content completed preview。
- assistant final answer 不自动升级为 verified claim；只有 tool fact、evidence-backed projection、
  user-confirmed correction 可进入 verified claim ledger。
- reasoning delta 进入 display read model，但不进入 memory snapshot / RunInput messages。
- ToolRuntime facts 进入 memory projection时只保留中性摘要，不含 `scope_token`、cursor 原文和完整大结果。
- ToolRuntime facts / evidence anchors 进入独立 memory 槽位，不混进 assistant history。
- evidence anchors 不被自然语言 summary 替代；同一 turn 同时有 tool summary 和 `EvidenceAnchor` 时，
  RunInputBuilder 输出必须保留 anchor id 与 source cursor。
- `fetch_more_completed` facts 可作为下一轮 tool summary 依据；`fetch_more_requested` / denied / failed 只以中性事件摘要进入。
- pinned_state 独立渲染在 memory block 开头，不参与 pool 竞争。
- memory block 内部顺序为 stable frame / verified claims / assumptions / evidence anchors / recent raw turns /
  older pool / episode summary 插入位。
- 历史 memory 按 issue #48 单总池语义组织；测试必须能区分“单总池”与“working / episodic 双独立池”。
- 最近 N 轮 raw turn 是下限保底，不是上限；测试必须证明预算充足时不会被固定 N 轮天花板截断。
- 最近 N 轮 raw turn 是语义保底，不是超大旧轮全文无限 token 保底；测试必须证明超大旧轮会降级为 user intent、
  assistant final 摘要 / evidence anchors，且不挤占当前财报材料 / 工具结果窗口。
- P3 可以不生成 episode summary，但 RunInputBuilder / memory snapshot 必须保留后续 episode summary 插入位，
  且该位置不破坏 pinned_state 独立路径与单总池顺序。
- memory 裁剪保持克制，不把 memory pool 设计成优先占满上下文；测试或实现注释必须说明财报材料 /
  工具结果窗口优先于扩张历史 memory。
- 每个 memory item 都记录 source / provenance / trust 元数据：`source_run_id`、`source_event_cursor`、
  `producer_kind`、`ingestion_policy`、`scope`。
- P3 只实现 `session` scope，但类型预留 direct / group / project / user；测试必须证明不同 `session_id`
  不串 memory。
- `RunInputBuildTrace` 记录 included / excluded facts、裁剪原因、source id、估算 char / token size；测试必须证明
  trace 与生产 RunInputBuilder 路径同源，且 trace 不进入 RunInput 或 memory pool。
- internal-only `memory_reset` / `claim_correction` / `scope_clear` patch / event 形状存在，但不暴露 public API、
  不做持久治理或 UI。
- 最近轮 user / assistant final 按 session 顺序进入 RunInputBuilder。
- projection 只读取已 append RunEvent，不能直接读取 EngineEvent 或 ToolRuntime store。
- Host public boundary：`RunInputBuilder`、`ConversationMemoryStore`、projection 实现不在 `dayu.host.__all__`。
- Engine import boundary：`dayu.engine` 不 import `dayu.host`。
- 最小多轮 Session smoke：同一 session 第一轮 terminal 后，第二轮问题可在 RunInput 中看见第一轮 final answer /
  tool summary；测试必须明确它不覆盖 P7 active Run admission、幂等、取消和完整 lifecycle。
- issue #48 + OLD / NEW 差异：#48 的 pinned_state 全量、单总池、recent_turns_floor 下限、memory 克制等
  不变量必须有测试或实现路径守住；OLD `assistant_reasoning` 可展示但不运行态；OLD pinned_state /
  tool summary 行为被继承；OLD compaction / persistent archive / Engine 内实现未迁回。

覆盖率：

- 新增生产文件单文件覆盖率目标 >= 80%。
- 只改测试 helper / smoke 时不降低既有覆盖。

## 验证命令

代码实施完成后运行：

```bash
source .venv/bin/activate
pytest tests/host/test_phase3_conversation_memory_projection.py \
  tests/host/test_phase3_run_input_builder.py \
  tests/host/test_phase3_multiturn_smoke.py \
  tests/host/test_phase3_boundary.py
pyright
```

如果修改了 README / docs 示例，还需运行相关文档检查命令或至少用 `rg` 校验旧术语清理：

```bash
rg -n "assistant_reasoning.*运行态|fetch_more_args|RunInputBuilder.*Engine|scope_token.*RunEvent" dayu docs tests
```

本 plan 编写阶段只需文档检查，无需 pytest / pyright：

```bash
test -f docs/host/phase3-plan.md
rg -n "^## (目标|非目标|前置条件|架构边界|文件级改动清单|新增 / 修改契约|状态机变化|数据持久化 / schema 变化|多进程并发影响|ToolRuntime / EngineWorker / Engine 边界影响|EventLog / RunEventStore / projection 影响|可接受临时实现 / 不可接受临时实现|runtime dependency|测试清单|验证命令|README / docs 触发判断|review gate|停止条件|风险与回滚|待用户确认项|迁移 Agent 实施完成汇报格式)" docs/host/phase3-plan.md
rg -n "reasoning|preview|RunInput|Memory pool|RunInputBuilder|RunEventStore|ToolRuntime|OLD|P4|P6|P7|P9" docs/host/phase3-plan.md
rg -n "#48|pinned_state|单总池|recent_turns_floor|反退化|克制|episode summary" docs/host/phase3-plan.md
```

## README / docs 触发判断

本 plan 文档新增本身不触发 README 更新，因为它是迁移 handoff plan，不描述已落地当前事实。

P3 代码实施后触发：

- 修改 `dayu/host/` -> 必须检查并按职责更新 `dayu/host/README.md`。
- 修改 `tests/` -> 必须检查并按职责更新 `tests/README.md`。
- 涉及分层关系、RunInputBuilder 装配方式、Host / Engine 边界 -> 必须检查并按职责更新 `dayu/README.md`。
- 修改 `docs/host/design.md` 只写 P3 已落地事实，不写 P4+ 未来设计为已落地能力。
- 根目录 `README.md` 只有在项目级使用方式、CLI 命令或配置入口变化时才更新；P3 最小 Host internal
  memory 不应机械修改根 README。

## review gate

P3 至少需要以下 review gate：

- plan review gate：确认本计划栏目完整、边界清晰、未提前实现 P4 / P6 / P7 / P9。
- canonical user input gate：确认 `USER_INPUT_ACCEPTED` 是 Host-owned canonical event，append-before-engine /
  run stream，且 memory projection、display timeline、RunInputBuilder、replay 都从 EventLog 读取同一 cursor。
- issue #48 + OLD / NEW plan review gate：对照 GitHub issue #48、OLD `conversation_memory.py`、
  `conversation_store.py`、`conversation_session_archive.py`、`scene_preparer.py` 与相关测试，确认 P3
  继承 / 后移 / 禁止迁回判断正确，且最小结构与 #48 不变量兼容。
- domain-neutral memory structure gate：确认 `EvidenceAnchor`、`MemoryClaim`、`ClaimStatus`、`TaskFrame`、
  `AssumptionRegister`、`UserPreferenceProfileRef` / slot、scope、producer / ingestion policy 均为 Host 中立
  强类型结构；Host 没有内嵌财报业务抽取规则。
- verified claim gate：确认 assistant final answer 不会自动升级为 verified claim，verified claim ledger 只接纳
  tool fact、evidence-backed projection、user-confirmed correction。
- build trace gate：确认 `RunInputBuildTrace` 与生产 RunInputBuilder 同源，记录 included / excluded facts、裁剪原因、
  source id、估算 size，且不进入 RunInput 或 memory pool。
- code review gate：常规代码 review，重点看类型、docstring、测试和 public boundary。
- issue #48 + OLD / NEW code review gate：必须对照 issue #48 与 OLD conversation memory 实现做专项 review，
  确认 `pinned_state` 全量独立、历史单总池、最近 N 轮 raw turn 下限保底、memory 克制、episode summary
  后续接入位等不变量不是只写在文档里，而是被 P3 实现路径和测试守住；同时确认 NEW 没有旁路 transcript、
  没有 reasoning 回流运行态、没有把 compaction / persistent archive / Engine 内 memory 迁回。
- import boundary gate：确认 `dayu.runtime`、`dayu.engine`、`dayu.fins` 依赖边界没有被破坏。
- scope / privacy gate：确认 P3 只实现 `session` scope，不跨 `session_id` 串 memory；direct / group / project /
  user 只作为强类型预留，不实现策略或 UI。
- semantic vs implementation gate：review 必须专门检查“文档声称的语义”和“实际实现逻辑”是否一致，例如：
  - 文档称 preview 不进 memory，代码是否真的过滤了所有 preview event。
  - 文档称用户输入 canonical 真源是 `USER_INPUT_ACCEPTED`，代码是否所有生产与测试路径都读取 EventLog 同一
    cursor。
  - 文档称 final answer 只来自 terminal event，代码是否从 delta 拼接。
  - 文档称 assistant final 不等于 verified claim，代码是否存在从 final answer 到 verified ledger 的自动投影。
  - 文档称 anchor 不被 summary 替代，代码是否在 RunInputBuilder 输出中保留 anchor id / source cursor。
  - 文档称 scope token 不进 memory，测试是否覆盖序列化输出。
  - 文档称遵守 #48 单总池和 recent_turns_floor 下限，代码是否实际实现成双池或上限。
  - 文档称 recent floor 是语义保底，代码是否对超大旧轮做降级而非全文保留。
  - 文档称 build trace 与生产路径同源，测试是否没有使用单独 mock builder 绕过真实裁剪逻辑。
  - 文档称不做 P7 admission，代码是否偷偷实现了隐式队列或幂等。

## 停止条件

实施 Agent 遇到以下情况必须停止并请求 plan 修订：

- 需要新增持久化 schema 或 workspace migration。
- 无法新增 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent，或无法保证 append-before-engine / run stream。
- 需要修改 `dayu.engine` 才能完成 RunInputBuilder。
- 需要从 `StartRunRequest.input`、display transcript、preview stream 旁路投影用户输入。
- 需要从 ToolRuntime cursor store / scope token 构造 memory。
- 需要把 reasoning / preview delta 放入运行态才能通过测试。
- 需要把 assistant final answer 自动升级为 verified claim 才能通过 smoke。
- 需要把 tool facts / evidence anchors 混入 assistant history 才能复用 OLD 行为。
- 需要实现 active Run admission、`client_request_id` 幂等或完整 Session 状态机。
- 需要实现 context overflow compact / retry。
- 需要新增 `dayu.runtime` Host 语义 helper。
- 需要偏离 issue #48 的 pinned_state 独立全量、历史单总池、recent_turns_floor 下限保底或 memory 克制不变量。
- 需要把 recent floor 实现为超大旧轮全文无限保底。
- 无法在 Host 中立强类型结构中预留 claim / evidence / task frame / assumption / preference / scope / provenance。
- OLD 行为与本计划继承 / 后移 / 禁止迁回判断冲突。

## 风险与回滚

主要风险：

- memory projection 与展示 read model 混淆，导致 reasoning 或 delta 污染下一轮输入。
- P3 为了 smoke 方便绕过 RunEventStore，形成第二套 transcript 真源。
- P3 未把用户输入写入 `USER_INPUT_ACCEPTED`，导致 memory projection、display timeline、RunInputBuilder、replay
  用户输入真源分裂。
- assistant final answer 被误当成 verified claim，导致模型表达污染财报事实账本。
- tool facts / evidence anchors 被拼进 assistant history，导致工具事实与模型结论边界消失。
- ToolRuntime facts 过度投影，泄漏 cursor 原文、scope token 或完整大结果。
- Memory item 缺少 source / provenance / trust / scope 元数据，导致未来 subagent、compaction、group/direct/project
  场景难以防污染。
- recent floor 被误解为超大旧轮全文无限保底，挤占当前财报材料 / 工具结果窗口。
- RunInputBuildTrace 与生产路径不同源，测试只验证 mock trace，无法解释真实裁剪和召回。
- 最小多轮 smoke 被误写成 P7 lifecycle，提前引入不完整 admission / 幂等。
- P3 只做表面过滤，实际 RunInputBuilder 与测试使用不同路径，造成语义与实现漂移。
- P3 最小结构没有对齐 issue #48，导致 P4 引入 compaction / episode summary / token budget 时需要重写
  memory store 或 RunInputBuilder 输入顺序。

回滚策略：

- P3 不改 schema，回滚可删除 `_conversation_memory.py`、`_run_input_builder.py` 及相关 harness 注入。
- 保留 P1.5 / P2 `RunEventStore` 与 ToolRuntime facts 不变。
- 如果发现 memory projection 边界错误，优先禁用 RunInputBuilder 注入，退回显式 `RunInput.messages` 路径。
- 不为错误契约加兼容 wrapper；按全新设计修正契约和测试。

## 待用户确认项

- P3 是否需要新增最小 Session 级 public `start_session_run(session_id, user_text, options)` 测试入口，还是只在
  `LocalRunHarness` 内部提供 RunInputBuilder 装配供 P5 smoke 使用。
- P3 的 `pinned_state` 是否只支持显式测试 patch / seed，还是要从用户输入和 final answer 做最小规则化更新。
  默认建议只支持显式 seed / patch，LLM compaction 后移 P4。
- P3 的最近轮 raw turn 保底数量是否先固定为内部常量，还是引入强类型配置字段；无论哪种，都必须保持
  issue #48 的“下限保底，不是上限”语义。
- P3 是否新增 `list_session_timeline` 的最小 display read model，还是仅用 internal display projection 测试隔离。
- ToolRuntime facts 进入 memory 的摘要粒度：默认只保留 tool name、tool_call_id、value summary、cursor fingerprint、
  has_more、error code；是否需要保留 `scope_hash` 作为中性 provenance 字段。

已决策，不再作为待确认项：

- P3 必须新增 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent；若实现中不能新增，实施 Agent 必须停止并提交
  plan 修订。
- assistant final answer 不自动升级为 verified claim。
- P3 只实现 `session` scope，但类型预留 direct / group / project / user。

## 迁移 Agent 实施完成汇报格式

迁移 Agent 完成 P3 代码后，最终汇报必须包含：

```text
修改文件：
- ...

关键决策：
- RunInputBuilder 实际消费了哪些 canonical RunEvent / ToolRuntime facts。
- P3 最小 memory 结构如何兼容 issue #48：pinned_state 全量、历史单总池、最近 N 轮下限保底、
  memory 克制、episode summary 后续接入位。
- 哪些事实只进入 display read model。
- preview / reasoning / delta 的隔离实现位置。
- OLD 行为中继承、后移、禁止迁回的实际落点。

验证：
- pytest ...
- pyright
- README / docs 同步情况

未覆盖 / 风险：
- ...

待用户确认：
- ...
```
