# Conversation Memory 讨论稿

本文档用于记录 Conversation Memory 后续讨论，不是实施计划。任何进入实施的内容都必须回到对应 design gate 与实施总控 work unit。

## 当前共识

Conversation Memory 不应该成为新的事实真源。Host 的 durable EventLog、payload descriptor 与 artifact 才是可恢复、可审计的真源；Conversation Memory 是从这些真源投影出的、受预算约束的 read model。

因此，“全量召回”不应理解为把所有历史都塞进 prompt，也不应理解为把 memory snapshot 做成无限大。更合理的方向是：

- EventLog / artifact 保留全量原始痕迹和 canonical facts。
- Memory snapshot 只保留当前 Run 最常用、最稳定、最需要直接注入上下文的 bounded working set。
- 需要全量或长尾历史时，通过检索 / 回查能力从 EventLog、payload descriptor、artifact 或后续索引中按需召回。
- 不同用户 prompt 应只召回与当前问题相关的 memory，避免无关原文稀释模型注意力。

## 讨论边界

本文档包含若干面向目标架构的讨论判断，不等同于当前实施建议。特别是 Prompt Understanding / Memory Intent Parsing、LLM schema parser、跨 session 用户画像、回答锚点和前瞻意图等内容，都需要后续 design gate 单独裁决；本文只记录问题空间和可能方向。

## 第一阶段策略

第一阶段不默认引入 prompt-conditioned recall，也不默认引入 LLM parser。为了控制延迟、复杂度和测试成本，Trace Memory 与 Evidence / Fact Memory 先采用 recency + floor 策略：

- Trace Memory：保留最近 N 轮原始痕迹，最少保留 M 轮。
- Evidence / Fact Memory：保留最近 N 条 accepted evidence / evidence-backed facts，最少保留 M 条。

这表示第一阶段主要解决近因记忆：

- “刚才说什么”
- “第二点展开”
- “继续”
- 最近工具结果和最近财报事实连续性

预算紧张时，优先丢弃更旧的 trace / evidence / fact item，但必须保留对应 memory 类型的 minimum floor。超出 N 的历史仍可留在 EventLog / artifact / durable store 中，后续可通过 recall / retrieval 设计重新接入，但第一阶段不默认注入 prompt。

该策略的优点是低延迟、可测试、接近现有实现，且不会引入每轮 LLM parser 的额外成本和不稳定性。它的明确边界是：不能解决深历史语义检索、跨 session 用户画像归纳、长期偏好演化等问题；这些应留到后续相关性 recall / index / profile 设计中讨论。

## 核心设计原则

Conversation Memory 的默认目标不是“多带历史”，而是“少带但带对”。每一轮 prompt 应该尽量干净，只包含当前问题需要的连续性、事实证据、回答锚点、会话状态、用户画像和前瞻意图。

这意味着：

- 召回必须与当前 prompt 相关，不能按时间粗暴灌入大量历史。
- 原始历史可以全量保存，但进入模型前必须经过选择、压缩、排序和预算控制。
- 稳定事实优先于原文长片段；原文长片段只在需要引用、核验或重新推理时召回。
- 上一轮 `final_answer` / `assistant_conclusion` 是重要的对话承接材料；当用户问“第二点”“刚才那个”“继续说”时，应通过相关性召回进入 prompt。
- 如果上一轮回答有清晰结构，例如“三个主要风险”，应优先召回结构化回答锚点，而不是整段 `assistant_conclusion`。
- 用户画像和前瞻意图只能辅助理解当前问题，不能压过用户本轮明确输入。
- prompt cleanliness 是验收目标：memory 注入越多，越需要证明它确实相关。

### 语义类型与预算层分离

当前实现中的 `stable layer`、`history pool`、`recent raw turns floor` 更像是 prompt assembly 阶段的预算策略，而不是 Conversation Memory 的顶层语义模型。

第一性原理上，LLM memory 要解决的不是“保存更多历史”，而是回答这些问题：

1. 当前问题需要哪些事实。
2. 当前问题在延续哪段对话。
3. 用户是谁、偏好什么。
4. 之前已经形成了什么结构化结论。
5. 下一步任务状态是什么。
6. 每条信息从哪里来，可信度如何，能否撤销。

更好的设计应把两件事分开：

- Memory semantic types：原始痕迹、原子事实、用户画像、会话摘要、回答锚点、前瞻意图。
- Prompt budget / assembly policy：在当前 prompt 下，从这些语义类型中召回哪些 item，以什么顺序、格式和预算注入模型。

这意味着：

- `stable layer` / `history pool` 不应决定 memory 的概念边界；它们只决定 prompt 里如何取舍。
- `pinned_state` 应进一步拆分语义：`current_goal` / `open_questions` 更接近任务状态或前瞻意图，`user_constraints` 可能是 session constraint，不应都塞进同一个概念桶。
- `evidence_backed_facts` 是核心 stable fact 类型，但仍需要 accepted evidence recall / index 支撑回查和重新推理。
- `working_assumptions` 容易被误读成弱事实，后续应考虑改成 hypotheses / candidate claims，并强制带 source、status 和置信度。
- `conversation_continuity` 可以继续作为 prompt assembly 的连续性集合，但内部应允许 raw turns、assistant conclusion、minimum preserve、answer anchors 等不同语义 item 被独立召回。
- `recent_raw_turns_floor` 只应是预算保底策略，不应承担 memory 分类职责。

目标架构可以理解为：

```text
Memory Truth / Store
  -> EventLog / artifacts / accepted evidence
  -> durable user profile store
  -> session memory projection

Semantic Memory Indexes
  -> Trace Recall Index
  -> Evidence / Fact Index
  -> User Profile Memory
  -> Session Summary Memory
  -> Answer Anchor Memory
  -> Forward Intent Memory

Prompt Assembly
  -> 根据当前 prompt 做相关性召回
  -> 按预算、优先级、source refs 和结构化格式注入模型
```

换句话说，`stable layer` / `history pool` 不应该是顶层心智模型。它们应降级为 Prompt Assembly 的预算结果。

### 当前实现取舍

现有实现不是错，但抽象层次混了。短期不用推倒，应在现有 Conversation Memory 上加一层语义模型：先引入 Answer Anchor 和 recall 思路，再逐步把 `stable layer` / `history pool` 重命名或下沉为预算策略。

| 当前项 | 取舍 | 调整方向 |
| --- | --- | --- |
| `pinned_state` | 部分保留 | 拆开。`current_goal` / `open_questions` 更像任务状态或前瞻意图，`user_constraints` 可能是 session constraint，不应都塞进 `pinned_state`。 |
| `evidence_backed_facts` | 保留 | 这是核心 stable fact 类型，但还缺 accepted evidence recall / index。 |
| `working_assumptions` | 谨慎保留或改名 | 当前语义危险，容易被误读成弱事实。更好的方向是 hypotheses / candidate claims，并强制带 status / source / confidence。 |
| `open_questions` | 保留但换位置 | 更像 forward intent / task state，不是 stable fact。 |
| `conversation_continuity` | 保留 | 但它应成为 prompt assembly 的连续性集合，内部包含 raw turns、assistant conclusion、minimum preserve、answer anchors 等独立语义 item 的召回结果，而不是一个粗池子。 |
| `recent_raw_turns_floor` | 保留为策略 | 它是预算保底策略，不是 memory 分类。 |
| `episode summaries` | 保留 | 对应 Session Summary Memory。 |
| `assistant_conclusion` | 保留但降级 | 作为原始痕迹 / 连续性兜底，不如 Answer Anchor 精确。 |

### Prompt Understanding / Memory Intent Parsing

讨论判断：一个正常 Agent 面对的用户输入大多是自然表达，不能把规则解析作为主方案。规则只适合辅助和兜底，例如识别“第二点”“最新”“来源”“TSLA Q3”等明显结构。

阶段性裁决：第一阶段不默认执行本节描述的 parser 路径，避免拉长每轮对话延迟。本节仅作为后续相关性 recall / profile / forward intent 设计的讨论材料。

更合理的目标方向是：

```text
自然语言 prompt
-> typed memory-intent parser
-> deterministic validation
-> recall / write gate
-> memory retrieval / candidate update
-> prompt assembly
```

typed memory-intent parser 可以由 LLM、专门小模型或混合 pipeline 实现，但它只能提出计划，不能直接读写 memory。Host / Service 仍必须通过确定性逻辑做 schema 校验、枚举校验、置信度处理、时间歧义判断、source refs 检查和是否需要用户确认的裁决。

示例：

```json
{
  "intent": "memory_query",
  "query_kind": "profile_pattern",
  "target_memory": ["user_profile", "trace"],
  "natural_query": "我做大决策有什么习惯",
  "time_scope": "all_relevant",
  "needs_aggregation": true,
  "needs_evidence": true
}
```

```json
{
  "intent": "memory_write_candidate",
  "write_kind": "future_event",
  "target_memory": ["forward_intent"],
  "content": "8月有一场重要的面试",
  "time_expression": "8月",
  "time_resolution": "ambiguous",
  "needs_confirmation": true
}
```

这不是当前实施建议，也不表示第一版必须引入 LLM parser。当前可实施方案仍需要在 design gate 中基于复杂度、可靠性、测试成本和分层边界单独裁决。

### Compact Repair 策略

讨论判断：`CONTEXT_COMPACTED` 是一次 LLM 交互返回的结构化 JSON，但其中不同字段有不同 accept barrier。某些字段可能合法，另一些字段可能因 evidence ref 不存在、claim 过长、minimum preserve source refs 非法等原因不通过校验。

更好的方向不是直接 partial materialize，而是在写入 `CONTEXT_COMPACTED` 前先 repair：

```text
compact proposal
-> Host validation 收集所有 invalid fields
-> 一次 repair LLM 交互修复所有坏字段
-> Host 用 repair patch 替换上一次 proposal 中的坏字段
-> Host 对 merged candidate 做全量校验
-> 通过后 append CONTEXT_COMPACTED
```

关键约束：

- 多个字段坏掉时，也应合并成一次 repair LLM 交互，而不是每个字段单独交互。
- repair 只修坏字段，不应让 LLM 重写已通过校验的字段，避免 good fields 漂移。
- 合并由 Host 代码完成；LLM 只返回 repair patch，不能决定最终接受状态。
- merged candidate 必须重新做全量校验，只有整体合法才写入 EventLog。
- repair 发生在 `CONTEXT_COMPACTED` 写入前；已提交 EventLog 不做原地修改。

阶段性裁决：该策略纳入 GitHub Issue #81 的 Conversation Memory 整体优化。`WU-CM-03` 不再单独裁决 partial materialize / fail closed；后续实现应优先讨论 compact repair，只有 repair 耗尽仍失败时，再裁决是否 partial materialize 或 fail closed。

### Answer Anchor 与 Minimum Preserve 分界

讨论判断：上一轮 assistant final answer 中形成的结构化回答轮廓，优先由 Answer Anchor 解决；minimum preserve 不应承担 answer outline 的主职责。

例如：

```text
用户：分析这家公司三个主要风险。
助手 final_answer：
1. 毛利率下行压力
2. 需求放缓风险
3. 现金流压力

下一轮用户：第二个风险展开说说。
```

这个场景本质是“上一轮回答结构的指代解析”，更适合召回 Answer Anchor：

```text
anchor 2 = 需求放缓风险
source = RUN_SUCCEEDED.final_answer
```

minimum preserve 仍然有价值，但职责不同：它用于保留长用户输入、compact material 或其它非 answer-outline 内容中的最小指代上下文。例如用户粘贴长文并要求提炼因素后，下一轮问“第二个因素”，而这个有序结构不一定来自 assistant final answer。

边界规则：

- Answer Anchor：优先解决 final answer 中“第 N 点 / 那个结论 / 刚才第三个风险”等回答结构指代。
- Minimum Preserve：保留长输入或 compact material 中理解代词、序号、局部承接所需的最小 continuity item。
- Evidence / Fact Memory：负责财报事实和证据引用；Answer Anchor 与 minimum preserve 都不能自动升级为 evidence-backed fact。

阶段性裁决：`WU-CM-04` 纳入 GitHub Issue #81 的 Conversation Memory 整体优化与后续 Fins integration 边界。#81 正确实现 Answer Anchor 后，minimum preserve 不再需要承担 final-answer outline 指代职责；它只保留 continuity / navigation 边界。

## 代码核对

- `USER_INPUT_ACCEPTED` 是用户输入进入 Host 的 canonical fact；memory 当前会将其投影为 raw user turn。
- `RUN_SUCCEEDED.payload.final_answer` 会投影为 `assistant_conclusion`，用于对话连续性，但不是 `evidence_backed_fact`。
- `TOOL_RESULT_ACCEPTED` 当前只表示 accepted evidence envelope；memory 不会直接从 raw tool result 合成 stable fact。
- `CONTEXT_COMPACTED` 的 accepted candidates 才会物化 episode summary、minimum preserve、pinned state patch 和 `evidence_backed_facts`。
- 当前已有 session-level 会话摘要、minimum preserve、pinned state 的 current goal / constraints / open questions，但没有跨 session 用户画像。
- 当前没有独立的“前瞻意图”层；`current_goal` 和 `open_questions` 只能覆盖一部分短期目标与未解问题。

## Benchmark 借鉴

### LongMemEval

LongMemEval 评测长期交互记忆的五类能力：信息抽取、多 session 推理、时间推理、知识更新和拒答。它还把长期记忆系统拆成 indexing、retrieval、reading 三阶段，并强调 session / round decomposition、fact-augmented key、time-aware query expansion 和 structured reading。

对 Dayu 的启发：

- Memory 不能靠“把历史全塞进长上下文”解决；需要 EventLog / artifact 的索引、相关召回和结构化阅读。
- 原始痕迹 recall 应优先按 turn / event / evidence span 粒度切分，而不是整 session 粗召回。
- index key 不应只来自原文，还应包含 extracted facts、公司、指标、期间、source locator、event_sequence 等增强 key。
- 召回必须带时间信息，支持“最新”“之前”“修改后”“当时为什么”这类时间推理。
- retrieved memory 进入 prompt 时要结构化，避免一坨聊天记录稀释模型注意力。
- 评测必须包含无证据 / 不可回答问题，确保系统会拒答，而不是用 memory 幻觉补洞。

### PersonaMem

PersonaMem 评测个性化记忆和动态用户画像，关注模型能否识别用户当前偏好、偏好演化、变化原因，并在新场景中给出符合用户当前状态的回答。它的任务类型包括召回用户事实、识别最新偏好、追踪偏好演化、回忆偏好变化原因、给出偏好对齐建议、泛化到新场景。

对 Dayu 的启发：

- 用户画像不能是静态 key-value 表；它必须有 source refs、observed_at / valid_from、supersedes、confidence、撤销和用户可见解释。
- 最新偏好与历史偏好必须同时可解释；系统既要知道当前采用哪个，也要能解释为什么旧偏好被覆盖。
- 画像更新不能只依赖压缩后的 LLM-generated facts；相关原始交互仍应可召回，避免过早压缩丢失变化原因。
- personalization recall 应按当前 prompt 选择相关画像，不应把用户全部画像都塞进 prompt。
- 新场景泛化是高阶能力：用户画像只能辅助生成，不应压过本轮明确输入或财报证据。

### 对 DayuMemoryEval 的启发

后续可以建立项目内 memory eval，用来覆盖以下能力：

- 财报事实召回：从 accepted evidence / evidence-backed facts 找回指标、期间、来源。
- 多 session 推理：跨多个 session 合成公司、指标或用户关注点的变化。
- 时间更新：处理“最新指引”“之前说法”“后来修正”的问题。
- 拒答：当 EventLog / evidence / profile 中没有足够依据时明确拒答或要求补充。
- 动态画像：用户偏好从“先看现金流风险”改为“先看毛利率”后，下一轮按最新偏好组织回答。
- 回答锚点：用户问“第二点展开”时召回上一轮 answer anchors，而不是整段 final answer。

## 目标六类语义模型

更好的 Conversation Memory 不应以 `stable layer` / `history pool` 作为顶层分类，而应以语义用途划分为六类：

- Trace Memory：原始痕迹。EventLog / artifact 全量保存，prompt 里只按需召回。包括 user input、final answer、tool result、失败、取消、恢复轨迹。
- Evidence / Fact Memory：原子事实。分为 accepted evidence 和 evidence-backed facts 两层；事实必须绑定 evidence refs。
- User Profile Memory：用户画像。跨 session，使用独立 durable store，不混进 session Conversation Memory。
- Session Summary Memory：会话摘要。当前 session 的 compact / rollup，服务连续性，不替代事实。
- Answer Anchor Memory：回答锚点。保存上一轮或历史回答的结构化轮廓，例如“三个风险”的 1 / 2 / 3 点，解决“第二点展开”问题。
- Forward Intent Memory：前瞻意图。保存下一步任务状态、待澄清问题、可能需要召回的方向；不能自动驱动工具执行，只辅助 prompt 构造。

### 1. 原始痕迹

含义：

- 用户原始输入、助手最终回答、工具调用结果、等待恢复结果、取消 / 失败 / 修复轨迹等原始历史。
- 这些内容主要存在于 EventLog、payload descriptor 和 artifact 中。

当前现状：

- memory 只把部分原始痕迹投影进 conversation continuity。
- raw user turn 来自 `USER_INPUT_ACCEPTED`。
- assistant conclusion 来自上一轮 `RUN_SUCCEEDED.final_answer`。
- 工具 raw result 不直接作为普通 memory 文本长期注入。

待讨论问题：

- “全量召回”应该做成 EventLog / artifact 检索能力，而不是扩大 raw turn pool。
- 需要定义哪些历史可被普通 Run 检索，哪些只能供 compactor / audit / debug 使用。
- 需要定义召回结果进入 prompt 前的预算、脱敏、排序和 source refs。

初步倾向：

- 保持 EventLog 是全量真源。
- Conversation Memory 只保留 bounded continuity。
- 新增独立 retrieval / recall 入口，用于按 session、run、event type、semantic query 或 evidence ref 回查原始痕迹。
- recall 入口必须接收当前 prompt / query context，返回相关片段而不是时间线全量 dump。
- `final_answer` 不需要并入 raw user turn 类型；它应保留为 `assistant_conclusion`，但成为高优先级 recall 候选。

### 2. 原子事实

含义：

- 对财报分析真正有用的稳定事实，例如“某公司某季度收入是多少”“该事实来自哪份财报哪段证据”。
- 原子事实必须可追溯到 accepted evidence，不能来自 assistant final answer 或 episode summary 的自由文本。

当前现状：

- `TOOL_RESULT_ACCEPTED` 保存 accepted evidence envelope。
- `evidence_backed_facts` 当前只从 accepted `CONTEXT_COMPACTED.evidence_backed_fact_candidates` 物化。
- 如果 accepted evidence 存在但 compactor 没有产出合法 fact candidate，Host 只记录 diagnostic，不合成 fallback fact。

待讨论问题：

- “全量召回原子事实”应召回 accepted evidence，还是召回已经抽取过的 `evidence_backed_facts`。
- 是否需要一个 evidence index，让普通 Run 或 compactor 能按财报 subject / metric / period / source locator 找回 accepted evidence。
- 是否需要把 fact extraction 从 compaction 中拆出一条更直接的 evidence-to-fact path。

初步倾向：

- accepted evidence 是原子事实的上游证据，不等同于已验证 fact。
- `evidence_backed_facts` 仍必须绑定 evidence refs。
- 如果要“全量”，应优先建立 accepted evidence recall，再决定是否新增专门 fact extraction work unit。

### 3. 用户画像

含义：

- 跨 session 的用户偏好、角色、常用分析风格、约束、风险偏好、语言习惯、常看的公司 / 行业等。

当前现状：

- 当前 Conversation Memory 是 session-level。
- `pinned_state.current_goal`、`user_constraints`、`open_questions` 仍属于 session memory，不是跨 session 用户画像。
- 代码中没有 durable user profile / identity memory。

关于实现边界：

- 用户画像抽取 / 更新可以由 scene、专门 extractor、retrieval pipeline 或其它实现承载。
- 讨论稿不预设必须使用某个 markdown prompt、某个 scene 或某条固定 pipeline。
- 真正的用户画像数据应有 durable profile store、canonical update event、projection、隐私删除 / 重置策略和用户可见解释。

待讨论问题：

- 用户画像是按本地 workspace、账号、客户组织，还是更细粒度 subject 分区。
- 哪些画像字段允许自动学习，哪些必须用户显式确认。
- 画像如何过期、撤销、覆盖、导出和删除。

初步倾向：

- 新建跨 session User Memory / Identity Profile 设计，不混入 session Conversation Memory。
- profile extraction / update 的技术实现后置到 design gate 决策。

### 4. 会话摘要

含义：

- 对当前 session 已发生内容的压缩总结，用于跨长对话保持连续性。

当前现状：

- 已有 `CONTEXT_COMPACTED` 产生 episode summary。
- memory 会将 accepted episode summary 作为 conversation continuity 的一部分。
- summary 不能替代 `evidence_backed_facts`。

待讨论问题：

- 会话摘要是否只服务当前 session，还是能作为跨 session user profile 的候选输入。
- 摘要里如果包含事实性陈述，是否必须显式引用已有 evidence-backed fact 或 accepted evidence。
- 多次 compact 后 summary 的 roll-up、可读性与 source refs 怎么保持。

初步倾向：

- session summary 继续留在 Conversation Memory。
- 跨 session 画像只能消费经过明确 profile update gate 的摘要候选。

### 5. 回答锚点

含义：

- 上一轮或历史回答中可被用户后续指代的结构化节点。
- 例如用户问“分析这家公司三个主要风险”，模型回答了三点；这三点应形成有序锚点，支持后续“第二点展开说说”“刚才第三个风险呢”这类追问。

当前现状：

- 当前已有 `assistant_conclusion`，但它是整段 final answer 的 continuity item。
- 当前没有专门的 answer outline / answer anchor 分类。

和前瞻意图的区别：

- 前瞻意图表达“下一步可能要做什么 / 需要准备什么”。
- 回答锚点表达“刚才回答中有哪些可被再次指代的结构”。
- “三个主要风险”这个任务本身可以生成前瞻意图候选，例如后续可能追问某一项；但模型回答出的三点更适合进入回答锚点。

待讨论问题：

- 回答锚点由 deterministic parser、LLM extractor，还是 final answer 结构化输出直接产生。
- 回答锚点是否只保存 label / order / short text / source final answer ref，还是也保存 evidence refs。
- 回答锚点如何过期、覆盖，以及如何避免被误当作财报事实。

初步倾向：

- 新增 session-level answer anchors / answer outline memory 分类。
- 它只服务对话指代和局部展开，不自动成为 `evidence_backed_fact`。
- 如果某个锚点本身绑定了 accepted evidence refs，后续可用于解释和召回证据；但分析结论仍不能仅凭 final answer 升级为 stable fact。

### 6. 前瞻意图

含义：

- 系统对用户下一步可能需要什么的结构化判断，例如待跟进问题、计划中的分析路径、未完成任务、下一步建议。

当前现状：

- `pinned_state.current_goal` 和 `open_questions` 能表达部分当前目标与未解问题。
- 但它们不是完整的 forward intent，不表达“下一步应该主动准备什么 / 召回什么 / 问什么”。

待讨论问题：

- 前瞻意图是 Host memory 的一部分，还是 Service / Agent planning 的 projection。
- 前瞻意图能否由 LLM 自动写入，还是必须通过 Host accept barrier。
- 前瞻意图如何避免变成不可审计的隐形计划或 self-fulfilling prompt bias。

初步倾向：

- 前瞻意图可以作为 bounded、可解释、可撤销的 planning memory。
- 它不应成为事实真源，也不应直接驱动工具执行；只能影响下一轮上下文构造或澄清问题。

## 关键边界

- 原始痕迹全量存在于 EventLog / descriptor / artifact，不等于全量进入 prompt。
- accepted evidence 是事实证据，不等于已抽取的 stable fact。
- assistant final answer、回答锚点、用户输入、episode summary、minimum preserve、用户画像、前瞻意图都不能自动升级成 `evidence_backed_fact`。
- 跨 session 用户画像必须有独立 durable 边界，不能伪装成 session memory 字段。
- 任何可自动学习的长期信息都需要来源、置信度、更新时间、撤销路径和用户可见解释。

## 可能拆出的后续 Work Units

- EventLog / artifact recall：为原始痕迹建立可控召回入口。
- Accepted evidence recall / index：为财报证据建立可查询索引。
- Evidence-to-fact extraction：评估是否从 compaction 中拆出独立 fact extraction path。
- Answer anchors / outline memory：设计回答锚点的生产者、source refs、预算、过期和召回规则。
- Cross-session identity profile：设计 durable 用户画像、profile update event 和抽取 / 更新边界。
- Forward intent memory：设计前瞻意图的生产者、accept barrier、预算和渲染规则。
