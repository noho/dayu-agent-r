# P3 Conversation Memory 最优方案 Review

## 结论：有条件通过

`docs/host/phase3-plan.md` 与 GitHub issue #48 的方向不是“只够用”的随手版，而是一个边界意识较强的 Host 最小方案：它抓住了 `pinned_state` 独立、单总池、recent floor、memory 克制、展示态隔离、canonical facts 真源这些关键不变量。作为 P3 的最小 Host Conversation Memory / RunInputBuilder，可以通过。

但它还没有接近“最好的买方财报分析多轮会话记忆子系统”。当前方案主要解决“下一轮能看到上一轮历史且不污染 reasoning / delta”，还没有把财报分析最核心的跨轮事实治理建成一等结构：实体、期间、口径、单位、来源、已验证结论、未验证假设、纠错状态、用户投资偏好、当前任务框架。若 P3 完全按现状落地而不补结构性预留，P4+ 会在 `memory pool` 文本摘要、tool summary 和 pinned_state 之间补丁式扩展，最终很难支持审计、纠错、忘记/重置和 domain fact compaction。

条件是：P3 不需要实现完整 domain memory，但必须把“事实账本 / 证据锚点 / claim 状态 / 假设寄存器 / task frame / preference profile”的接入点在强类型结构和 RunInputBuilder 顺序中预留出来，并明确 Host 只承载层中立的记忆治理字段，不理解财报业务语义。

## First-principles model

买方财报分析 memory 的目标函数不是“最大化聊天回放量”，而是最小化跨轮分析漂移，最大化可验证事实复用，并把有限上下文留给当前财报材料、工具检索结果和局部章节。

不可变量：

- 事实必须有来源：任何进入“已验证事实”的数字、期间、口径、单位、公司实体、报告来源，都必须能追到 tool fact / source reference / event cursor，不能只来自 assistant final answer。
- 状态必须可区分：`verified claim`、`assistant conclusion`、`user preference`、`open assumption`、`display text`、`tool large result`、`reasoning` 是不同类型，不应混入一个文本池。
- 纠错必须可覆盖：用户或工具后续纠错时，新事实不能和旧事实并存成同权重历史；旧 claim 需要 `superseded` / `rejected` / `stale` 状态。
- 指代必须稳定：追问里的“它 / 上一家公司 / 同口径 / 去年同期 / 刚才那个增速”必须解析到 task frame 中的实体、期间、口径、单位和比较基准。
- Memory 必须克制：recent floor 是追问连续性的保底，不是允许历史挤占财报材料窗口的理由；大工具结果只能以 evidence anchor 和摘要进入。
- Host 必须业务无关：Host 可以治理 claim、evidence、status、scope、cursor、projection，但不能内嵌“营收 / 毛利率 / IFRS / XBRL”的财报语义；这些应由 fins/tool 侧产生结构化事实，Host 只做中立投影。
- Memory 必须可审计、可忘记、可压缩：每条长期或半长期记忆都需要来源、状态、作用域、生命周期，才能支持 future persistent projection、compaction、reset 和 audit。

## Findings

### Critical（已修复）：P3 缺少事实账本与 claim 状态，容易把 assistant 历史当成已验证事实

证据：P3 计划的最小 memory 包含 `pinned_state`、memory pool、tool facts projection 和最近轮 user / final answer 回放；`RunInputBuilder` 可消费 `FINAL_ANSWER`、tool facts、warnings/errors 的中性摘要，并把 evidence anchors/source references 作为“本阶段只允许强类型不透明引用”的可选项。OLD 代码里 `ConversationEpisodeSummary.confirmed_facts` 是 `tuple[str, ...]`，tool summary 被拼进 assistant 历史文本，`ConversationTurnRecord` 也没有 claim status / evidence anchor。

问题：`final answer` 是模型表达，不是事实真源。财报分析中，“2024H1 营收同比 +18%”如果只作为 assistant 历史回放，下一轮模型可能把未验证结论、旧口径、展示摘要或被纠错内容当成事实。P3 现在防住了 reasoning/delta 污染，但没有防住“assistant final answer 污染 verified facts”。

为什么影响财报分析：买方工作流经常连续追问同一公司、多公司对比、口径切换、期间滚动。没有 claim 状态和证据锚点，系统无法判断一个数字来自原始财报工具、模型推断、用户假设，还是已经被后续纠正。

建议：P3 必须预留 Host 中立的 `MemoryClaim` / `EvidenceAnchor` 槽位，最小字段至少包括 `claim_id`、`status`、`source_run_id`、`source_event_cursor`、`evidence_anchor_id`、`scope`、`created_at`、`supersedes`。P3 可以不抽取财报字段，但不能只留下纯文本 `confirmed_facts` 插入位。财报领域结构应由 fins/tool facts 提供，Host 只保存强类型、不透明、可追踪的证据关系。

### Medium（已修复）：`pinned_state` 过于粗粒度，task frame / 假设 / 用户偏好需要分槽

证据：OLD `ConversationPinnedState` 只有 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions` 四类；P3 计划继承该独立路径，并把 compaction 和 `ConversationPinnedStatePatch` 三态合并后移。

问题：这四个字段适合通用会话，但不足以表达买方分析的稳定 frame。`confirmed_subjects` 会混放公司、报告期、报告类型、比较对象；`user_constraints` 会混放单位、会计准则、偏好、输出风格；`open_questions` 会混放待检索问题和未验证投资假设。

为什么影响财报分析：追问“按同口径再看现金流”“那和海天比呢”“换成人民币百万元”时，系统需要知道当前 task frame 的实体、期间、口径、单位、比较基准，而不是从自然语言 pinned_state 中再猜一次。

建议：P3 必须至少预留分槽结构：`TaskFrame`、`AssumptionRegister`、`UserPreferenceProfile`。P3 不实现自动抽取也可以，但 RunInputBuilder 的 memory block 顺序应为 task frame / verified claims / assumptions / preferences / raw turns，而不是把所有稳定状态压进四个通用字符串字段。

### Medium（已修复）：evidence anchor 只是可选提法，不足以约束 tool facts 与引用追踪

证据：P3 说 `evidence anchors / source references` 本阶段只允许强类型不透明引用，若当前事件不含这些字段不得臆造；同时 tool facts projection 只列 tool name、tool_call_id、cursor fingerprint、value summary、has_more、error code。

问题：这是正确的消极约束，但缺少积极要求：哪些 canonical tool facts 必须能产生 evidence anchor，anchor 如何在后续 claim、compaction、RunInputBuilder 中被稳定引用。没有这个约束，P3 实施者可能只实现“摘要字符串 + tool_call_id”，后续再补 source references 时要重建 projection。

为什么影响财报分析：财报结论必须能回到报告、章节、表格、XBRL fact、页码或工具结果 chunk。否则多轮会话里“引用上次那个数”会变成引用 assistant 文本，而不是引用数据来源。

建议：P3 必须定义 `EvidenceAnchor` 的中立最小形状和生命周期：`anchor_id`、`origin_event_cursor`、`tool_call_id`、`source_ref`、`chunk_ref`、`fingerprint`、`summary`。如果 P2 事件暂时没有完整 source_ref，也应保留字段和测试，允许为空但不能缺类型。

### Medium（已修复）：RunInputBuilder 顺序总体正确，但 tool facts 不应混进 assistant history

证据：P3 要求输入顺序为 system prompt -> `[Conversation Memory]` -> pinned_state -> history pool -> current user message；OLD `_render_tool_summary_block` 把工具摘要拼到 assistant 历史的一部分。

问题：把工具摘要混在 assistant 历史里，会弱化“工具事实”和“模型结论”的边界。P3 已经说 tool facts projection 是独立消费事实，但测试重点仍是“tool summary 参与 memory”。这会诱导实现沿用 OLD 的拼接方式。

为什么影响财报分析：模型看到“上一轮助手说 X + 历史工具摘要 Y”时，可能把二者等权处理；最优方案应该让 verified tool facts / evidence anchors 先于 raw conversation 出现，并标明状态与来源。

建议：RunInputBuilder 顺序保持 current user 最后、静态 system 在前，但 `[Conversation Memory]` 内部应调整为：`TaskFrame / Pinned State` -> `Verified Claim Ledger` -> `Assumption Register` -> `Evidence Anchors / Tool Fact Summaries` -> `Recent Raw Turns` -> `Older Pool / Episode Summaries`。raw turns 是连续性材料，不是事实真源。

### Medium（已修复）：recent floor 是正确方向，但需要明确“语义保底不等于无限 token 保底”

证据：#48 和 P3 都把 recent N 轮从上限反转为下限，并要求不参与 token pool 竞争；OLD `DefaultWorkingMemoryPolicy` 对 forced turns 有单轮溢出阈值和 minimum preserved view。

问题：P3 plan 强调 recent floor 不是上限，但对超大 user_text / assistant_final 的兜底只写了“简单 token / 字符预算”和 memory 克制测试，没有把 OLD 的单轮溢出保护列为必须继承。财报会话里用户可能粘贴大段表格或报告摘录，recent floor 如果无条件全量保留，会直接挤掉当前检索材料。

为什么影响财报分析：当前轮工具检索和财报局部上下文通常比旧轮完整文本更重要。保留指代连续性时，应保留“可指代的结构和证据锚点”，不是保留旧轮所有正文。

建议：P3 必须明确 recent floor 的实现规则：最近 N 轮“必须有代表”，但单轮超过窗口派生阈值时降级为 user intent + assistant final 摘要 + evidence anchors，不回放完整大文本。这个要求不等于 P4 compaction，可以作为 P3 RunInputBuilder 的安全裁剪规则。

### Low（已修复）：忘记 / 重置 / 纠错生命周期没有 P3 预留入口

证据：P3 把持久化、clear history 五真源补偿、完整 lifecycle governance 后移；P3 in-memory store 只服务顺序 smoke。

问题：后移是合理的，但最优 memory 必须从第一版数据模型就支持 invalidation。否则用户说“忘掉刚才那个假设”“这家公司不是 A 是 B”“重置本会话口径”时，后续只能靠追加自然语言修正，旧记忆仍在池里竞争。

为什么影响财报分析：买方分析大量发生在纠错和口径切换中。错误事实残留比遗忘更危险。

建议：P3 只需预留 `memory_reset` / `claim_correction` / `scope_clear` 的内部事件或 patch 形状，不需要 public API。P4+ 再接入 Session clear、用户命令和持久化治理。

### Low（已修复）：用户偏好 profile 应后移，但不能混入 session pinned_state

证据：OpenClaw 和 Claude Code 都把长期偏好/规则作为独立记忆类别或持久指令；P3 当前只做同 Session memory，且 public 边界保持最小。

问题：买方用户偏好有长期价值，例如“默认看同比和毛利率桥”“金额单位用百万元”“先列数据来源再下结论”。这些不应和某个会话的公司/期间混在一起，也不应在 Headless / one-shot 任务中隐式生效。

为什么影响财报分析：偏好会影响输出口径和工具选择，但错误作用域会造成惊讶行为，尤其是不同客户、不同策略、不同组合经理之间。

建议：P3 只预留 `UserPreferenceProfileRef` 或 profile slot，不实现跨 session durable memory。P4+ 在权限、作用域、可见性、审计明确后再做。

### Info（已确认）：P3 没有迁回 OLD scene preparation / archive 是正确选择

证据：P3 明确不迁回 OLD Engine 内 context、scene preparation、file archive；design 第 12 节把 Conversation Memory 放在 Host 上下文治理边界，Engine 只消费最终 `RunInput.messages`。

判断：这符合 Host 强约束与 `UI -> Service -> Host -> Engine` 分层。OLD 的 `ConversationSessionArchive` 在运行态/展示态分离、reasoning 禁止入运行态上提供了好证据，但其文件 archive、scene preparer 强耦合不应成为 NEW Host 的结构来源。

建议：继续以 RunEventStore canonical facts 为真源，OLD 只作为语义证据，不作为模块迁移模板。

## 最优架构建议

### P3 必须补

- 强类型预留 `MemoryClaim`、`EvidenceAnchor`、`ClaimStatus`、`TaskFrame`、`AssumptionRegister` 的 Host 中立结构；字段可以少，但必须有 ID、状态、来源 cursor、作用域和 supersession 关系。
- RunInputBuilder memory block 内部顺序改成“稳定 frame / verified claims / assumptions / evidence anchors / raw turns / older pool”，避免 tool facts 混入 assistant history。
- recent floor 的安全裁剪规则：语义保底，token 不无限保底；超大轮次保留 intent、final 摘要和 evidence anchors。
- 测试增加一类“assistant final answer 不能自动升级为 verified claim”的边界；只有 tool fact / evidence-backed projection 可进入 verified claim ledger。
- projection 诊断至少能说明某条 memory item 来自哪个 run/event cursor，便于未来 audit。

### P3 只预留

- 财报领域字段，如 company identifier、period、currency、unit、accounting standard、metric taxonomy、filing section，应由 fins/tool 层产生；Host 只保留 opaque typed reference 或中立 claim text。
- `ConversationPinnedStatePatch` 三态合并、LLM compaction、episode summary 生成可后移，但 P3 的结构必须能插入 episode summaries 和 claim patch。
- `UserPreferenceProfile` 只预留 ref/slot，不跨 session 持久化，不自动注入所有运行形态。
- `memory_reset`、`claim_correction`、`scope_clear` 只预留内部 patch/event 形状，不做 public command。

### P4+ 后移

- domain fact ledger 的自动抽取、冲突检测、纠错 UI、长期持久化、审计查询。
- evidence anchor 到财报页码、XBRL fact、表格 cell、chunk span 的完整绑定。
- retrieval index、semantic recall、跨 session preference memory。
- context overflow compact / retry、episode compaction LLM、persistent projection checkpoint。
- 多进程 session admission、幂等、clear history 五真源补偿、reset/forget 的完整生命周期治理。

## 与 OpenClaw / Codex / Claude Code 的启发对照

- OpenClaw Context Engine 把 ingest、assemble、compact、after-turn 分成生命周期点，并明确 memory plugin 与 context engine 分离。这支持 Dayu 的判断：Host RunInputBuilder 是上下文装配器，memory search / domain facts 不应混在一个 store 里。
- OpenClaw Active Memory 只在符合条件的持久交互会话运行，并给模型一次有界召回机会。这提醒 Dayu：memory 注入应有 eligibility 和预算克制，不能让隐藏个性化或长期偏好进入所有 Run。
- Claude Code 把 CLAUDE.md 和 auto memory 分开，前者是用户写的持久规则，后者是系统从纠错和偏好中学到的记录；并说明 subagents 有独立 context。对 Dayu 的启发是：用户偏好、任务 frame、工具研究结果应分槽，重型检索/探索结果不应污染主会话。
- Codex AGENTS.md 采用层级发现、作用域和大小上限；Codex agent loop 也强调静态内容放在 prompt 前缀以利缓存，动态变化追加在后。这支持 P3 的 system prompt 在前、memory 后置、current user 最后的顺序；也提醒 Dayu memory block 应稳定、有序、克制，避免每轮重排造成上下文不稳定。
- Codex 的 compaction/无状态请求设计说明：长期运行不应依赖 provider conversation state；Dayu 选择由 Host 从 canonical events 构造 RunInput 是正确方向。

## Sources

- NEW `docs/host/phase3-plan.md`。
- NEW `docs/host/design.md`，尤其第 6.2 节展示 read model 隔离与第 12 节 Conversation Memory / RunInputBuilder。
- GitHub issue #48：https://github.com/noho/dayu-agent/issues/48 。
- OLD `/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py`。
- OLD `/Users/leo/workspace/dayu-agent/dayu/host/conversation_store.py`。
- OLD `/Users/leo/workspace/dayu-agent/dayu/host/conversation_session_archive.py`。
- OLD `/Users/leo/workspace/dayu-agent/dayu/host/scene_preparer.py`。
- OpenClaw Memory System：https://clawdocs.org/architecture/memory-system/ 。
- OpenClaw Active Memory：https://docs.openclaw.ai/concepts/active-memory 。
- OpenClaw Context Engine：https://docs.openclaw.ai/concepts/context-engine 。
- Claude Code memory：https://code.claude.com/docs/en/memory 。
- Claude Code subagents：https://code.claude.com/docs/en/sub-agents 。
- OpenAI Codex agent loop：https://openai.com/index/unrolling-the-codex-agent-loop/ 。
- OpenAI Codex AGENTS.md：https://developers.openai.com/codex/guides/agents-md 。

## 复审结论

复审结论：通过。

本次复审只核对 `docs/host/phase3-plan.md` 与 `docs/host/design.md` 对原 findings 的文档修复是否成立，不评价尚未落地的代码实现。基于直接证据，原先标注“已修复 / 已确认”的问题已经真实进入 P3 plan 与 Host design 第 12 节，且方向一致。

### 已通过核对项

- `MemoryClaim` / `EvidenceAnchor` / `ClaimStatus` 已足以避免 assistant final answer 污染 verified facts：`phase3-plan.md` 在目标、非目标、可消费事实、Host 中立 memory 强类型预留、Verified claim 规则、测试清单、review gate 与停止条件中反复固定“assistant final answer 只能作为 raw turn / assistant conclusion，不能自动升级为 verified claim”；并要求 verified claim ledger 只接纳 tool fact、evidence-backed projection、user-confirmed correction。`design.md` 第 12.4.3 节同样明确 assistant final answer 不是 verified fact 真源。
- `TaskFrame` / `AssumptionRegister` / `UserPreferenceProfileRef` 已预留：`phase3-plan.md` 在目标、文件级改动清单、RunInputBuilder 可消费事实、Host 中立 memory 强类型预留、review gate 中均列出这些槽位；`design.md` 第 12.4 节也把三者列为 Conversation Memory 必须区分的运行态材料。
- `EvidenceAnchor` 生命周期和必要字段已进入 plan：`phase3-plan.md` 要求 `EvidenceAnchor` 至少包含 `anchor_id`、`origin_event_cursor`、`tool_call_id`、`source_ref`、`chunk_ref`、`fingerprint`、`summary`，并要求每个 memory item 携带 `source_run_id`、`source_event_cursor`、`producer_kind`、`ingestion_policy`、`scope`；测试清单还要求 anchor 不被自然语言 summary 替代，RunInputBuilder 输出保留 anchor id 与 source cursor。
- RunInputBuilder memory block 顺序已从 assistant history 拼接改为稳定 frame / verified claims / assumptions / evidence anchors / raw turns / older pool：`phase3-plan.md` 的 issue #48 兼容结构明确给出 system prompt -> `[Conversation Memory]` -> stable task frame / pinned_state -> verified claim ledger -> assumption register -> evidence anchors / tool fact summaries -> history pool（最近 raw turn、older raw turn、episode summary 插入位）-> current user message，并把“tool facts / evidence anchors 混进 assistant history”列为必须停止修订的偏离。`design.md` 第 12.6 节顺序与此一致。
- recent floor 已明确为语义保底而非无限 token 保底：`phase3-plan.md` 明确最近 N 轮 raw turn 是语义反退化下限，不是上限，也不是超大旧轮全文无限保底；超大轮次必须降级为 user intent、assistant final 摘要与 evidence anchors。`design.md` 第 12.6 节也写明保留可指代 intent、final 摘要和 evidence anchors，而不是让旧轮全文挤占当前财报材料窗口。
- reset / correction / scope_clear 生命周期已至少内部预留：`phase3-plan.md` 在文件级改动清单、可接受临时实现、测试清单中要求 internal-only `memory_reset` / `claim_correction` / `scope_clear` patch / event 形状；`design.md` 第 12.9 与 12.10 节预留 `claim correction`、`supersession`、`forget / reset patch`。
- `design.md` 第 12 节与 plan 方向一致：两者都坚持 Host 中立、Engine 不感知 memory、canonical facts 派生、展示 read model 与运行态隔离、assistant final 不等于 verified fact、EvidenceAnchor / MemoryClaim / TaskFrame / AssumptionRegister / UserPreferenceProfileRef 分槽、RunInputBuilder 顺序、recent floor 语义保底与 build trace 诊断。

### 剩余 findings

无新的阻塞 finding。剩余风险从“文档方案缺口”转为“代码实现是否真实守住文档语义”：后续 code review 必须重点核对实际实现没有从 final answer 自动投影 verified claim、没有把 tool facts / evidence anchors 拼进 assistant history、没有把 recent floor 写成超大旧轮全文保底、没有让 preview / reasoning / display transcript 回流运行态。
