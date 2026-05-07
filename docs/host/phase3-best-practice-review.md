# P3 Conversation Memory 最佳实践 Review

## 结论

有条件通过。

P3 plan + issue #48 的主方向成立：Conversation Memory 属于 Host，RunInputBuilder 只消费 canonical facts，展示 transcript 与运行态输入隔离，`pinned_state` 独立、历史单总池、recent raw turn 下限保底、memory 克制，这些都符合成熟 Agent 的 context engineering 方向。

但它还不是完整适配“买方财报分析 Agent”的最佳形态。P3 至少需要补强两类结构性设计：一是财报 stable facts / evidence anchors 的强类型承载方式，二是 scope / privacy / audit / forget 的最小边界元数据。否则 P3 虽可跑通通用多轮 smoke，但会把最关键的财报精度、可追溯性和跨会话权限问题留成后续结构债。

## Executive Summary

- 运行态输入与展示 transcript 隔离：通过。P3 与 NEW design 明确禁止 reasoning / delta / preview 回流 RunInputBuilder，且继承 OLD `runtime_transcript` / `history_archive` 分离。
- durable canonical facts 与 memory projection 分离：基本通过。P3 以 `RunEventStore` canonical events 为真源，memory store 只是 projection；但 P3 不持久化可以接受，不能宣称生产级。
- memory 召回克制：通过。#48 明确 1M 档不扩张 memory cap，P3 也要求把窗口留给财报材料、检索结果、工具结果。
- 财报特有事实承载：有缺口。P3 仅把 evidence anchors 写成“不透明引用”，没有定义公司、期间、口径、单位、币种、准则、页码、XBRL fact id 等 stable pinned facts / evidence anchors 的最小强类型形状。
- scope / permission / privacy：有缺口。P3 只限定同 Session memory，不定义 direct / group / project / user scope，不定义 memory 是否可查看、暂停、删除、遗忘。
- subagent / tool / compaction 污染防护：方向正确但元数据不足。P3 禁止 reasoning / cursor / scope token 进入 memory，但没有为 future compaction、subagent、internal helper run 预留 producer/source/trust 边界。

## Findings

### Critical（已修复）: 财报 stable facts / evidence anchors 只写成占位，承载力不足

证据：
- NEW design 第 12 节要求“工具结果即事实”，结构化 tool facts、evidence anchors、source references 不能被 LLM 二次摘要丢失精度。
- P3 plan 的 RunInputBuilder 可消费 facts 只说 evidence anchors / source references “本阶段只允许强类型不透明引用；若当前事件不含这些字段，不得臆造”。
- issue #48 的 `pinned_state` 仅覆盖 current_goal、confirmed_subjects、user_constraints、open_questions；OLD `ConversationPinnedState` 也是这四类字段。

问题：
P3 的 `pinned_state` 和 generic tool summary 能维持通用追问，但不足以承载买方财报分析里的稳定事实：公司主体、报告期间、报告类型、会计准则、币种、单位、口径、页码、表格/章节位置、XBRL fact id、用户投资假设、是否为用户确认结论。把这些仅作为自然语言 summary 或不透明引用，会削弱后续 P4 compaction / recall 的精度。

为什么影响财报分析：
财报分析最怕“数字对、口径错”或“结论对、来源丢”。例如上一轮确认的是“2024H1，人民币百万元，合并口径，IFRS/中国准则差异已调整”，下一轮追问“同比呢？”时，memory 必须稳定携带这些锚点，而不是让模型从摘要里猜。

建议：
纳入 P3 plan：在 `_conversation_memory.py` 里预留强类型结构，不要求 P3 自动抽取完整财报语义，但要让后续工具 facts 能无重构进入。例如：
- `FinancialSubjectRef(company_id, company_name, ticker, market)`
- `FinancialPeriodRef(fiscal_year, fiscal_period, report_type)`
- `FinancialMeasureContext(unit, currency, accounting_standard, consolidation_scope, restatement_flag)`
- `EvidenceAnchor(source_kind, document_id, page, table_id, xbrl_fact_id, quote_hash)`
- `StablePinnedFact(kind, text, anchors, confidence, confirmed_by_user)`

### Medium（已修复）: scope / privacy / permission 边界不足，容易在 group/direct/project 场景里补晚

证据：
- OpenClaw Active Memory 默认只在 direct session 启用，并明确用 `allowedChatTypes` 控制 direct / group / channel。
- Claude Code 把记忆按 managed policy、project、user、working tree 等 scope 区分；Codex AGENTS.md 也按 global -> project -> path 合并，越近的规则越具体。
- P3 plan 当前只说同一 `Session` 内下一轮 Run 可见 memory，未定义 user / project / direct / group / channel scope，也未定义谁能查看或清除 memory。

问题：
P3 不实现持久 memory 可以接受，但 memory snapshot 的 key 与元数据如果只有 `session_id`，后续扩展 direct/group/project 时容易出现跨用户、跨群、跨项目污染，尤其是买方研究里可能有组合持仓、投资假设、未公开结论、客户偏好等敏感上下文。

为什么影响财报分析：
同一公司、同一报告期的财报事实可复用，但用户投资假设、关注指标、组合约束、风险偏好不一定能跨 direct / group / project 复用。群聊中提到的假设也未必能进入某个用户的私有 direct memory。

建议：
纳入 P3 plan：为 `ConversationMemorySnapshot` / store key 增加最小 scope 元数据，哪怕 P3 只支持 `session`：
- `memory_scope: Literal["session"]` 或封闭枚举，P4+ 可扩展到 `direct_user`、`group`、`project`。
- `owner_ref` / `project_ref` / `visibility` 使用强类型可空字段。
- 测试证明 P3 不跨 `session_id` 读写 memory。

后移 P4+：真正的 group/direct/project 策略、UI 管理入口、跨项目共享和权限检查。

### Medium（已修复）: memory 的可审计、可编辑、可遗忘机制没有最小锚点

证据：
- OpenClaw memory 是本地 Markdown，可查看、编辑、reset，并提醒用户定期 review。
- Claude Code auto memory 可通过 `/memory` 浏览、编辑、删除，并会显示正在写入/召回 memory。
- P3 plan 有 display read model 隔离测试，但没有要求 RunInputBuilder 产出“本轮为何召回这些 memory”的可审计诊断；P3 也把 persistent projection / audit observer 后移 P6。

问题：
P3 可以不做完整 UI 和持久 audit，但如果内部没有 inclusion/exclusion trace，后续很难解释“为什么这一轮模型看到了某个历史事实”。对财报 Agent，memory 中的错误假设必须能定位来源并删除或覆盖。

为什么影响财报分析：
投资分析需要可追溯。用户发现“上一轮假设 WACC=9% 已过期”时，系统应能定位它来自哪轮、哪个工具事实或用户确认，而不是只能清空整段 session。

建议：
纳入 P3 plan：新增 internal-only `RunInputBuildTrace` 或等价诊断对象，记录 included / excluded facts、裁剪原因、source run/event id、anchor id。它不进入 RunInput，不进入 memory pool，只给测试和未来 audit observer 使用。

后移 P4+：用户可编辑 memory、forget API、审计 UI、持久 projection reconcile。

### Medium（已修复）: subagent / compaction / internal helper 的污染防护需要 producer 元数据

证据：
- OpenClaw Active Memory 明确不在 sub-agent/internal helper execution 中运行。
- Claude Code subagents 的探索、工具调用和 transcript 与主会话隔离，fork 模式也强调只有最终结果回主上下文。
- P3 plan 禁止迁回 OLD compaction、禁止 reasoning / preview / scope token 进入 memory，但 `ConversationMemoryTurn` / `ConversationToolFact` 未要求记录 producer kind 或 source run kind。

问题：
P3 当前只靠 event 类型过滤。等 P4 compaction、subagent、tool trace observer、background run 加入后，单靠 `FINAL_ANSWER` / `TOOL_RESULT_ACCEPTED` 很难判断该事实是否来自主用户会话、内部压缩、子 agent 探索、后台任务或测试 harness。

为什么影响财报分析：
子 agent 搜索可以产出候选材料，但候选材料不等于用户确认事实；compaction 也可能把假设写成事实。没有 producer/trust 边界，会把“研究过程发现”污染成“长期可用结论”。

建议：
纳入 P3 plan：memory projection 强类型里预留 `producer_kind`、`source_run_id`、`source_event_id`、`ingestion_policy`，P3 默认只接受主 session terminal run 的 canonical user/final/tool summary。P4+ compaction 与 subagent 进入 memory 时必须显式降级或转换。

### Medium（已修复）: 用户输入 canonical 真源仍是待确认项，实施前必须收敛

证据：
- P3 plan 在 RunInputBuilder 可消费 facts 中说用户输入事实要么新增 Host-owned canonical event，要么从 `StartRunRequest.input` 稳定用户消息投影。
- 待确认项仍保留“是否允许新增 Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent”。
- Codex agent loop 中新一轮会把用户消息作为 prompt 的最终输入项；上下文历史随轮次增长被纳入下一轮 prompt。

问题：
用户输入是每个 turn 的一半真源。如果 P3 不明确它如何进入 canonical timeline，就会在 memory projection、display timeline、resume/replay、RunInputBuilder 测试之间产生两条来源。

为什么影响财报分析：
财报追问常以省略方式出现，例如“那扣非后呢？”、“换成美元口径”。如果 user turn 不是 canonical、可排序、可审计的事实，后续无法可靠还原指代链。

建议：
纳入 P3 plan：P3 必须选定一种路径。最佳实践倾向新增 Host-owned canonical `USER_INPUT_ACCEPTED`，append-before-stream，并携带 `session_id`、`run_id`、`turn_id`、normalized user text、可选 scope metadata。若不新增 event，则必须把 `StartRunRequest.input` 到 memory projection 的稳定规则写成不可变契约并测试覆盖。

### Low（已修复）: P3 的 prompt budget 策略方向正确，但缺少最小可观测指标

证据：
- #48 主张 memory 克制，1M 档 cap 主动下调到 32K，避免挤占财报材料。
- P3 plan 要求测试或注释说明财报材料 / 工具结果窗口优先于扩张历史 memory。
- Codex 明确 context window management 是 agent harness 职责，超阈值后 compact。

问题：
P3 允许简单 token / 字符预算，但没有要求记录本轮 memory tokens、tool facts tokens、current user tokens 的估算结果。没有这些指标，后续调参只能靠主观感知。

为什么影响财报分析：
财报工具结果可能非常大。memory 预算过大时模型看不到关键页；memory 预算过小时追问断链。需要最小指标支持后续生产调优。

建议：
纳入 P3 plan：RunInputBuilder 诊断里记录估算 token / char：`pinned_state_size`、`history_pool_size`、`tool_fact_size`、`excluded_fact_count`、`budget_limit`。

### Info（已确认）: 运行态输入与展示 transcript 隔离符合最佳实践

证据：
- NEW design 明确 `list_session_timeline` 是展示 read model，不是 RunInputBuilder 输入；reasoning 只能作为展示字段，不能回流运行态。
- P3 plan 明确 preview / reasoning / delta 只能进入展示 read model，不得进入 RunInput replay、memory pool 或 RunInputBuilder。
- OLD archive 已把 `runtime_transcript` 与 `history_archive` 分离，`assistant_reasoning` 仅展示。
- Codex agent loop 也区分 UI streaming delta 与要追加进下一次模型输入的结构化 item。

问题：
无阻断问题。这是 P3 plan 最强的一部分。

为什么影响财报分析：
展示 reasoning 或流式 delta 回流会把未稳定、未确认、可能自相矛盾的中间文本污染成下一轮事实。P3 的隔离能降低财报结论漂移。

建议：
保持现有 plan，并在 code review 中重点检查测试路径与生产路径是否同源。

### Info（已确认）: Host-owned RunInputBuilder 边界符合“宿主强约束下 LLM in the loop”

证据：
- P3 plan 明确 RunInputBuilder / MemoryManager 属于 Host，Engine 只消费 `RunInput.messages`。
- P3 plan 禁止在 `dayu.runtime` 或 `dayu.engine` 放 Host memory。
- OpenClaw Context Engine 把 ingest / assemble / compact / after-turn 视为运行时上下文构造生命周期，而不是模型本身的职责。

问题：
无阻断问题。

为什么影响财报分析：
Host 统一治理 memory，才能统一做权限、证据、预算和审计；Engine 不应理解财报 memory 语义。

建议：
保持 internal API，不导出 store / builder / projection 实现。

## Best-practice 对照表

| 维度 | OpenClaw | Codex | Claude Code | #48 | P3 plan | 结论 |
|---|---|---|---|---|---|---|
| 运行态输入 vs 展示 transcript | Active Memory 注入 hidden system context，调试摘要与原始 prompt 分离；Context Engine assemble 独立于展示 | streaming delta 用于 UI，结构化 output item 才进入后续 input | subagent transcript 与主对话分离 | 未作为重点，但基于 OLD 分层 | 明确 preview/reasoning/delta 只展示，不进 RunInput | 通过 |
| canonical facts vs projection | memory 文件是可查看的持久知识库，active memory 是召回投影 | history/input 与 compacted input 分离 | CLAUDE.md / auto memory 作为持久上下文，topic 文件按需读 | pinned_state + episode summary + raw turn | RunEventStore canonical，memory store/projection internal | 基本通过 |
| memory 克制 | `maxSummaryChars`、queryMode、timeout、recent caps | 超阈值 compact，避免耗尽 context window | MEMORY.md 首 200 行或 25KB，详细文件按需读 | 32K cap，recent floor 是下限 | 要求不挤占财报材料/工具结果 | 通过 |
| scope / permission / privacy | `allowedChatTypes` 控制 direct/group/channel；local files 可 review | AGENTS.md global/project/path 分层 | managed/project/user/working-tree scope；`/memory` 可查看 | 主要是 session 内 memory | 未定义 group/direct/project/user scope | 需补 P3 最小元数据 |
| subagent 污染防护 | Active Memory 不跑在 sub-agent/internal helper | agent loop/harness 负责上下文管理 | named subagent 默认 fresh context；fork 明确隔离工具调用回流 | 未覆盖 | 过滤 reasoning/preview，但缺 producer 元数据 | 需补 P3 producer/source 字段 |
| 财报证据 anchor | 通用 memory，不覆盖财报证据 | 通用 coding agent，不覆盖财报证据 | 通用 coding memory，不覆盖财报证据 | 强调工具结果即事实、confirmed_facts | 只写 opaque evidence refs | 需补强类型 anchor |
| 可审计 / 可编辑 / 可遗忘 | Markdown 可编辑、reset；隐私说明 | AGENTS.md 文件可审阅；compaction opaque | `/memory` 可浏览、编辑、删除 | 配置/结构为主 | P6 audit 后移，P3 无 build trace | P3 应加 internal trace |

## 建议纳入 P3 plan 的改动

1. 定义最小强类型财报 evidence anchor / stable pinned fact 结构，P3 可只承载和透传，不做复杂抽取。
2. 明确用户输入 canonical 真源，优先新增 `USER_INPUT_ACCEPTED` RunEvent；否则写死 `StartRunRequest.input` 投影规则。
3. 给 memory snapshot/store key 增加最小 scope 元数据，P3 只实现 `session`，但类型上预留 direct/group/project。
4. 给 memory facts 增加 `source_run_id`、`source_event_id`、`producer_kind`、`ingestion_policy`，默认只接纳主 session terminal run 的 canonical facts。
5. 增加 internal-only RunInputBuilder build trace，记录 included/excluded facts、裁剪原因、source id、估算 token/char。
6. 测试覆盖财报 anchor 不被 summary 替代：同一 turn 同时有自然语言 tool summary 和 `EvidenceAnchor` 时，RunInputBuilder 输出必须保留 anchor id。

## 建议后移 P4+ 的改动

1. LLM compaction / episode summary 生成与 `ConversationPinnedStatePatch` 三态合并。
2. 持久 EventLog projection、audit observer、workspace schema / migration。
3. 用户可编辑 memory、forget API、`/memory` 类管理 UI、group/direct/project 完整权限策略。
4. durable retrieval index、跨 session / 跨 project memory recall。
5. subagent / compaction / background run 的完整 memory ingestion policy。
6. 基于真实生产数据的 memory cap / ratio 调参与 token accounting dashboard。

## Sources

本地文件：
- `docs/host/phase3-plan.md`
- `docs/host/design.md`
- `/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py`
- `/Users/leo/workspace/dayu-agent/dayu/host/conversation_store.py`
- `/Users/leo/workspace/dayu-agent/dayu/host/conversation_session_archive.py`
- `/Users/leo/workspace/dayu-agent/dayu/host/scene_preparer.py`

GitHub：
- GitHub issue #48: https://github.com/noho/dayu-agent/issues/48

业界参考：
- OpenClaw Memory System: https://clawdocs.org/architecture/memory-system/
- OpenClaw Active Memory: https://docs.openclaw.ai/concepts/active-memory
- OpenClaw Context Engine: https://docs.openclaw.ai/concepts/context-engine
- Claude Code Memory: https://code.claude.com/docs/en/memory
- Claude Code Subagents: https://code.claude.com/docs/en/sub-agents
- OpenAI, Unrolling the Codex agent loop: https://openai.com/index/unrolling-the-codex-agent-loop/
- Codex AGENTS.md guide: https://developers.openai.com/codex/guides/agents-md

## 复审结论

复审结论：通过。

本次仅复审已标注“已修复 / 已确认”的 findings 是否在 `docs/host/phase3-plan.md` 与
`docs/host/design.md` 中形成真实设计约束。结论是：原 review 提出的 P3 最佳实践缺口已被 plan
收束为明确实施要求、测试 gate 和停止条件；design.md 第 12 节也已同步为同一方向，没有发现仍需阻断
P3 handoff 的剩余 finding。

证据：

- 财报 stable facts / evidence anchors 已从占位升级为 Host 中立强类型预留。`phase3-plan.md` 明确要求
  定义并承载 / 投影 / 透传 `EvidenceAnchor`、`MemoryClaim`、`ClaimStatus`、`TaskFrame`、
  `AssumptionRegister`、`UserPreferenceProfileRef`，并要求 evidence anchors 至少保留 `anchor_id`、
  `origin_event_cursor`、`tool_call_id`、`source_ref`、`chunk_ref`、`fingerprint`、`summary`。
  `design.md` 第 12.4 节同步说明公司、期间、指标、XBRL fact、页码、单位、币种、准则等由 fins / tool
  侧以 typed 或 opaque reference 进入 Host。
- scope / privacy / permission 已具备 P3 最小边界。`phase3-plan.md` 要求 P3 只实现 `session` scope，
  store key 至少包含 `session_id`，类型预留 `direct_user`、`group`、`project`、`user`，并预留
  `owner_ref`、`project_ref`、`visibility`；测试必须证明不同 `session_id` 不串 memory。`design.md`
  第 12.8 与 12.10 节也要求 scope 元数据并后移 group/direct 隐私治理。
- audit / edit / forget 已具备内部锚点。`phase3-plan.md` 要求 internal-only `RunInputBuildTrace` 记录
  included / excluded facts、裁剪原因、source id、估算 char / token size，并预留 `memory_reset`、
  `claim_correction`、`scope_clear` patch / event 形状；public edit / forget / reset API、持久治理和 UI
  明确后移。`design.md` 第 12.4、12.7、12.9 与 12.10 节一致。
- producer / source / trust 元数据已进入 plan。`phase3-plan.md` 多处要求所有 memory item 至少携带
  `source_run_id`、`source_event_cursor`、`producer_kind`、`ingestion_policy`、`scope`，且 P3 默认只接纳
  主 session canonical facts，future subagent / compaction / background run 必须显式降级或转换。
- `USER_INPUT_ACCEPTED` 已从待确认项变成 P3 canonical 真源决策。`phase3-plan.md` 明确新增
  Host-owned canonical `USER_INPUT_ACCEPTED` RunEvent，append-before-engine / run stream；memory projection、
  display timeline、RunInputBuilder、replay 都只能从 EventLog 读取该事件。plan 还把无法新增该事件列为
  停止条件，不再保留 `StartRunRequest.input` 旁路投影作为 P3 可选路线。`design.md` 第 12.4.1 节方向一致，
  但仍保留“某阶段暂不新增”的通用设计说明；以 P3 plan 的强约束为本阶段执行真源。
- prompt budget / trace 指标已进入 plan。`phase3-plan.md` 要求 memory 克制，不挤占财报材料 / 工具结果窗口，
  并要求 `RunInputBuildTrace` 记录 pinned_state、verified claims、assumptions、tool facts、raw turns、
  older pool、episode summary 插入位的估算 char / token size、budget limit 与裁剪后总估算 size。
- `design.md` 第 12 节与 P3 plan 方向一致：都坚持 Host-owned Conversation Memory、canonical facts 真源、
  display transcript 隔离、强类型 evidence / claim / task frame、assistant final answer 不自动升级 verified claim、
  scope / provenance / build trace、以及 P4+ 后移 compaction、persistent projection、audit UI、跨 scope 治理。

剩余 findings：无阻断项。需在后续代码 review 中继续核对实现是否与 plan 同源，尤其是
`USER_INPUT_ACCEPTED` append-before-engine、anchor id/source cursor 保留、build trace 与生产
RunInputBuilder 同路径、以及 `scope_token` / cursor 原文 / reasoning 不进入 memory。
