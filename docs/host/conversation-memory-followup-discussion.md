# Conversation Memory 讨论稿

本文档只记录 Conversation Memory 已确认的设计共识。未在本文确认的内容，不作为 #81 的设计依据。

## 当前共识

Conversation Memory 不应该成为新的事实真源。Host 的 durable EventLog、payload descriptor 与 artifact 才是可恢复、可审计的真源；Conversation Memory 是从这些真源投影出的、受预算约束的 read model。

因此，“全量召回”不应理解为把所有历史都塞进 prompt，也不应理解为把 memory snapshot 做成无限大。设计约束是：

- EventLog / artifact 保留全量原始痕迹和 canonical facts。
- Memory snapshot 只保留当前 Run 最常用、最稳定、最需要直接注入上下文的 bounded working set。
- 第一阶段不根据用户 prompt 做相关性召回，不引入 memory intent parser、semantic search、vector recall 或 LLM reranker。
- 第一阶段不提供全量或长尾历史召回；全量材料只保留在 EventLog、payload descriptor、artifact 和 audit 路径中。

## 配置化运行参数边界

Conversation Memory 与 Context Governance 的运行参数必须来自配置文件进入 typed policy，再由 Host construction / composition root 显式注入；不得硬编码在生产代码、prompt 模板、compactor schema 或测试 fixture 中作为唯一来源。

第一阶段仍使用两个配置归属作为唯一候选 owner：

- `context_budget_policy`：承载 context budget / governance 相关运行参数。
- `memory_projection_policy`：承载 Conversation Memory read model / projection / prompt assembly 相关运行参数。

字段级 owner、字段名、默认值来源、派生公式、测试入口与迁移顺序由 WU-CM-01 plan 裁决。讨论稿只固定原则：selected recent window、protected recent floor、per-semantic bounded working set、compact attempt / fallback budget、projection lag / repair threshold 等运行参数不得硬编码；必须从配置文件进入 typed policy，再由 Host construction / composition root 注入运行时。

同一个运行语义只能有一个 policy owner。若某个值同时影响 budget governance 与 memory projection，WU-CM-01 plan 必须明确 owner，并由 owner 的 typed policy 派生给另一侧使用；不得在 `context_budget_policy` 与 `memory_projection_policy` 中复制出会漂移的双份真源。

## LLM-facing Compact I/O 硬边界

一次 compact 是一次 LLM 调用。LLM 是无状态、会犯错、会走捷径、上下文有限、偏好模式匹配的推理器；因此 compact I/O 必须把 Host internal control/provenance 与 LLM-readable material 严格分离。

本节指北星：

- 不得暴露与当前任务无关的内部实现细节。
- 不得把系统状态伪装成业务事实。
- 不得返回会诱导模型依赖脆弱实现约定的字段或隐式规则，例如位置语义、临时缩写、magic string、仅当前版本成立的默认约定。

Host internal terms 不得作为模型阅读材料，也不得要求模型返回：

- EventLog event id、event sequence、payload / artifact ref、digest、durable evidence id。
- compact cursor、compact boundary、policy name、recent floor、budget diagnostic、fallback diagnostic、`already_represented`、stable / delta / material block 内部状态。
- `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 的 raw payload、compact artifact JSON、projection checkpoint、scheduler / Attempt / recovery 内部治理细节。
- 任何只在当前实现版本成立的默认约定、magic string、临时缩写、位置语义或隐式排序语义。

LLM-readable compact material 只能包含与当前 compact 任务有关、用户或业务可理解的材料：

- 用户输入文本、助手最终回答文本、用户可见的 Run 状态连续性。
- 可读 tool name、tool query、tool response / source text。
- Host 为本次 compact 生成的 prompt-local opaque labels。

prompt-local label 是本次 LLM 调用内的 opaque citation handle，只用于让模型把 claim / anchor / summary / intent 绑定到它刚读过的材料。第一阶段允许使用短 deterministic handle，例如 `C1` / `H1` / `E1` / `S1` / `E1.1`，以节省 token 并降低 LLM 引用成本；“opaque”约束的是语义，不要求随机长 id。label 不得携带位置、时间、重要性、优先级、durable identity 或实现状态语义；模型不得根据 `E1` / `E2` / `M1` 等顺序、前缀、chunk 后缀或名字推断事实含义。Host 内部维护 prompt-local label 到 durable provenance refs 的映射。prompt、schema、validator 和测试可以验证 label 能映射回 provenance，但不得依赖 label 名称或 ordinal 推断业务语义。

LLM compact output 只能返回业务语义字段和 prompt-local labels。Host 负责把 labels 映射回 durable refs、校验 provenance、长度、枚举、source boundary 和 quality gate。模型不得返回 durable refs、event ids、digests、artifact refs、policy decisions 或任何 Host 内部状态字段。

## Prompt-independent compact / delta 边界

第一阶段 Conversation Memory 不走 prompt-conditioned recall 路线。也就是说，Host 不在每轮根据用户 prompt 动态判断“哪些历史相关”，不做 semantic search / vector recall，不用 LLM parser 判断 memory intent，也不让用户一句话动态拉取任意历史。

设计统一采用 material boundary + policy-conditioned deterministic assembly：

```text
memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material

rendered_context =
  assemble(
    memory_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

其中：

- `latest_accepted_compacted_view`：Host 内部已接受的 compact projection，用于代表 compact 覆盖范围内的旧历史；没有 accepted compact 时为空。给 LLM 的只能是 Host 从它投影出的业务语义视图，不是 raw compact artifact JSON、EventLog payload 或内部字段全集。
- `post_compact_delta_material`：最近一次 accepted compact 之后新产生、尚未被 compact 覆盖的 canonical EventLog material；没有 accepted compact 时从 session 起点开始。它是 Host 内部材料边界，不是全部进入 prompt 的 view。
- `current_input_anchor`：当前 Run 的用户输入保护锚点。它不是 memory 语义类，而是 Host 的 compact / fallback / prompt assembly 边界字段；给模型的仍只是当前用户输入文本。当前用户说“继续刚才失败的任务”或“恢复刚才那个”属于 `current_input_anchor`，不是 Trace Memory。
- `selected_recent_window_policy`：Host 从 material 中选择 bounded recent window 的确定性策略，不得暴露给模型。
- `protected_recent_floor_policy`：Host 在 selected recent window 内执行的保底规则，用来为短链路 continuity 保留最近若干 turn / item，避免“刚才”“继续”“第二点”等局部承接因 deterministic bound 或 compact 边界消失。它不是独立 memory，也不是第三份 view，不得暴露给模型。

`before compact` 不需要作为独立阶段建模。它只是 `latest_accepted_compacted_view` 为空、`post_compact_delta_material` 从 session 起点开始时的普通情况：

```text
before_compact_memory_material =
  empty_latest_accepted_compacted_view
  + session_start_delta_material

before_compact_rendered_context =
  assemble(
    before_compact_memory_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

也就是说，Conversation Memory 不维护 before compact / after compact 两套语义。统一模型始终是：

- accepted compacted material：没有 compact 时为空；有 compact 时为 latest accepted compact projection。
- delta material：没有 compact 时从 session 起点开始；有 compact 时从 latest compact cursor 之后开始。第一阶段不会把完整 delta 全量渲染给模型，而是按 deterministic recent-window policy 选择 bounded window。
- prompt assembly policy：负责 recent-window 选择、protected recent floor、去重、排序和 deterministic bounded selection；`protected_recent_floor_policy` 不产生新 memory，只约束 material 选择。第一阶段不做 token-estimator-driven runtime trimming。

第一阶段渲染原则固定为：

```text
if no accepted compacted view:
  memory_context =
    selected_recent_window
  current_input = final user message

if compact failed and recent-window fallback is allowed:
  memory_context =
    fallback_selected_recent_window
  current_input = final user message

if accepted compacted view exists:
  memory_context =
    session_summary_memory
    evidence_fact_memory
    answer_anchor_memory
    forward_intent_memory
    trace_memory.reference_continuity_items
    selected_recent_window_after_compact_boundary
  current_input = final user message
```

其中 `selected_recent_window` 可以包含近期 user turn、assistant final answer、tool query / response 或 accepted evidence material，但这些只作为 recent context / material 被渲染；它们不会在 compact 前自动生成 Answer Anchor、Session Summary、Forward Intent 或 `evidence_backed_facts`。

Prompt Assembly 的 section 顺序是固定 contract，不根据当前 prompt 做 recall、parser、reranker 或动态重排。Session Summary 只提供会话框架，不能替代 Evidence / Fact Memory；当 summary 与 fact 同时出现时，事实 claim 以 `evidence_backed_facts` 为准。Answer Anchor Memory 与 Forward Intent Memory 在 compact 后按 bounded policy 渲染非空 section，不由当前 prompt 触发。Reference Continuity Item 归属 Trace Memory，只服务局部指代解析，并放在 selected recent window 之前；selected recent window 是最接近 current input 的历史上下文。

compact failure fallback 场景下的 `selected_recent_window` 更准确地说是 deterministic fallback selected view。fallback 的原则与 compact 前一致：只渲染 deterministic fallback selected view 与当前输入，不提交新的 `CONTEXT_COMPACTED`，不写 compact artifact，不 materialize memory snapshot，不生成新的高阶语义。失败的 compact proposal 本身绝不能进入 memory。

第一阶段不根据 token estimator 在 runtime 做逐 section 裁剪。各 section 必须在 projection / assembly 前通过配置化的 item cap、char cap、selected recent window floor-cap 等确定性上限形成 bounded working set；provider context length failure 由 Host context governance 的 reactive / fallback compact 收口。确定性上限可以迁移当前 `memory_projection_policy` 的思路，但不能继承旧 semantic field 名称或旧 `stable layer` / `history pool` / `pinned_state` / `working_assumptions` 语义。

需要 floor 的 section 只固定两类：

- `selected_recent_window_turn_floor`：必须存在，用于保障短链路连续性与刚发生的用户可见上下文。
- `evidence_fact_floor`：必须存在，用于保障已经 accepted 的关键 `evidence_backed_facts` 不被普通 recent material 挤出。

其它 section 默认只有 cap，没有 floor：`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory` 与 `trace_memory.reference_continuity_items` 都允许为空；`reference_continuity_item_floor = 0` 可以显式进入配置，避免实施时把 Reference Continuity Item 误做成必须保留的独立层。

多次 compact 采用 rolling compacted view 模型。第二次及后续 compact 必须输入上一轮 accepted compacted view，但不能重新展开上一轮 compact 已覆盖的 raw history：

```text
next_compact_input =
  previous_accepted_compacted_view
  + selected_post_compact_recent_window
  + current_input_anchor

next_compact_output =
  next_accepted_compacted_view
```

这里的 `previous_accepted_compacted_view` 是 Host 已接受并可由 memory projection / compact artifact 解释的语义视图；再次给 LLM 时必须先投影成业务可读材料，不能暴露上一次 LLM raw JSON、raw compact artifact、EventLog payload、repair 前 candidate、失败 proposal 或中间 transient artifact。已被 accepted compact output 代表的旧 raw turns / old tool results 不应在下一次 compact 中重新展开；否则会导致 context window overflow、重复抽取、事实 / anchor / summary 重复生成，以及 compact boundary 不可审计。

下一次 compact 需要做的是 roll-forward / merge：用上一轮 accepted compacted view 代表旧历史，再吸收 post-compact selected recent window。输出的新 compacted view 代表旧 compacted view 与新 delta material 的合并结果，而不是无限追加 summary-of-summary。

`current_input_anchor` 只参与本次 compact / fallback / prompt assembly。它用于标记当前用户问题，定义 compact 不能吞掉的边界；普通 Run 最终仍以最后一条 user message 渲染当前输入。当前输入只有到下一轮成为历史时，才可能作为 selected recent window 中的 previous user turn 进入 Trace Memory。

每次 accepted compact 都会 renew 当前 compacted view：

```text
compact_1 -> accepted_compacted_view_1
compact_2 input uses accepted_compacted_view_1 -> accepted_compacted_view_2
compact_3 input uses accepted_compacted_view_2 -> accepted_compacted_view_3
```

因此，第三次 compact 的 `previous_accepted_compacted_view` 是第二次生成并被 Host 接受的 `accepted_compacted_view_2`。旧的 `accepted_compacted_view_1` 保留在 EventLog / artifact / audit 中用于追溯和重建，但不作为当前 prompt 或下一次 compact 的默认输入继续叠加。默认输入始终只使用 latest accepted compacted view，避免旧 summary、facts、anchors 或 forward intent 重复出现。

在没有 accepted compact output 之前，高阶结构化语义不应被凭空生成。第一阶段 compact 前只有两类 session-scoped semantic memory 可以非空：

- Trace Memory：来自 selected recent window 中的 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED.final_answer` 等明确连续性事件。
- Evidence / Fact Memory：来自 selected recent window 中的 tool query / response / accepted evidence material；如果没有 accepted compact output 或其它非 compact producer，`evidence_backed_facts` 仍为空。

以下三类在 compact 前必须为空：

- Answer Anchor Memory：compact 前不对 final answer 做规则化、deterministic outline parser 或 LLM parser。
- Session Summary Memory：summary 是 accepted compact / rollup 的产物。
- Forward Intent Memory：compact 前不对 prompt / final answer 做 intent parser，也不生成 hidden plan。

这个公式不是：

```text
visible_memory = retrieve(prompt, all_history)
```

而是：

```text
rendered_context = assemble(policy, cursor, compact_boundary, material_delta)
```

因此，五个 session-scoped 语义模型都按 accepted compacted material / delta material / prompt assembly policy 建模：

1. **accepted compacted material**：已经进入 accepted compact output 的结构化结果。它不改写历史 EventLog，只提供可审计的 projection / rollup；没有 compact 时为空。
2. **delta material**：latest compact cursor 之后的 bounded canonical events；没有 compact 时就是 session 起点以来的 eligible events。它是未 compact 覆盖的材料集合，不等于 prompt view。
3. **prompt assembly policy**：从 accepted compacted material 与 delta material 中做 selected recent-window 选择、protected recent floor 保底、去重、排序和 deterministic bounded selection。

这个 compact / delta 边界会反过来约束 #80 的评测：empty compacted view、non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection 与 provider context length fallback 都应有可断言场景。核心目标是可测试、可复现、可审计，而不是追求第一阶段的 prompt-level 相关性最优。

## 评测约束

Conversation Memory 的设计正确性由 GitHub Issue #80 的评测标准反向约束。#81 负责决定 memory 怎么设计，#80 负责定义什么行为证明这个设计成立。

#80 从四层观察 Conversation Memory：

- Memory Truth / Store：EventLog、accepted evidence、artifact refs、profile source refs 是否完整。
- Memory Projection：session memory snapshot、answer anchors、session summary、forward intent、profile view 是否按规则生成、更新、淘汰并保留 source refs。
- Prompt Assembly：RunInputBuilder 是否只注入 policy 允许的 bounded memory，是否保留 floor，是否避免无关历史污染 prompt，是否在 compact 后仍带上关键事实、锚点和任务状态。
- Agent Outcome：最终回答是否使用正确事实、当前偏好和正确锚点，是否拒答无证据问题，是否避免不必要重复工具调用，是否引用或解释来源。

WU-CM-01 进入 plan 前必须把 #80 维度映射为 current scope satisfied、deferred-with-owner 或 explicit non-goal。该映射不是要求 WU-CM-01 直接落地完整 #80 eval benchmark，而是防止 plan 把 User Profile、deep historical recall、full eval harness 或 smoke 覆盖范围混在一起。

第一阶段映射如下：

| #80 评测维度 / 能力 | WU-CM-01 scope | Owner / 验证入口 |
| --- | --- | --- |
| Trace continuity | current scope satisfied by WU-CM-01 | WU-CM-01 unit tests + 现有 `utils/` Host public smoke 初步验收 |
| Evidence-backed fact recall | current scope satisfied by WU-CM-01 | compact / projection / RunInputBuilder tests + 现有 `utils/` Host public smoke 初步验收 |
| Session Summary Memory | current scope satisfied by WU-CM-01 | accepted `CONTEXT_COMPACTED`、snapshot projection、prompt assembly tests |
| Answer Anchor Memory | current scope satisfied by WU-CM-01 | compact candidate / accept barrier / projection / prompt assembly tests |
| Forward Intent Memory | current scope satisfied by WU-CM-01 | compact candidate / accept barrier / projection / prompt assembly tests |
| Prompt assembly bounded behavior | current scope satisfied by WU-CM-01 | RunInputBuilder、selected recent window、protected floor、deterministic bound policy tests |
| Compact boundary / fallback behavior | current scope satisfied by WU-CM-01 | compact operation、fallback、不生成高阶语义、diagnostic tests |
| Agent outcome under finance scenarios | current scope smoke-only initial acceptance | 现有 `utils/` Host public smoke 必须通过；完整 benchmark deferred to WU-CM-10 / GitHub Issue #80 |
| User Profile Memory / dynamic profile | deferred-with-owner | WU-CM-11 / GitHub Issue #115；不进入 session Conversation Memory |
| Deep historical recall / semantic search | deferred-with-owner；WU-CM-01 explicit non-goal | GitHub Issue #39；research gate 后再设计 recall / retrieval |
| Full eval benchmark harness | deferred-with-owner | WU-CM-10 / GitHub Issue #80；当前不新增 issue，若 #80 后续需要拆 implementation child，再由 WU-CM-10 裁决 |

现有 `utils/` smoke 是 WU-CM-01 的初步验收标准，不等价于完整通过 #80。#80 的完整 eval harness 在 post-#81 memory semantic contract 稳定后，由 WU-CM-10 / GitHub Issue #80 继续推进。

## 第一阶段策略

第一阶段不引入 prompt-conditioned recall，也不引入 LLM parser。Trace Memory 与 Evidence / Fact Memory 采用 policy-conditioned selected recent window 与 protected recent floor。各 section 在 projection / assembly 前已按 deterministic item cap / char cap / floor-cap bounded；第一阶段不做 token-estimator-driven runtime trimming。provider context length failure 由 Host context governance 的 reactive / fallback compact 收口。

第一阶段只解决近因连续性：

- “刚才说什么”
- “第二点展开”
- “继续”
- 最近工具结果和最近财报事实连续性

深历史语义检索、跨 session 用户画像归纳、长期偏好演化不属于 #81 第一阶段。

## Compact 失败、重试与 Fallback

Compact failure handling 采用 whole-candidate repair retry、Host accept barrier 与 deterministic recent-window fallback：

```text
CompactionRequest
-> LLMContextCompactor 生成一次 strict JSON proposal
-> JSON parse / required keys / schema-value mapping
-> Host quality check / provenance check / proactive budget gate
-> accepted: write compact artifact + append CONTEXT_COMPACTED
-> rejected: append CONTEXT_COMPACTION_ATTEMPT_REJECTED diagnostic
-> if attempt budget remains: retry whole candidate proposal
-> if attempt budget exhausted: append CONTEXT_COMPACTION_FAILED
-> if recent-window fallback passes context governance: dispatch fallback attempt
-> otherwise fail closed
```

确定约束：

- LLM compactor 是单次 proposal 生成器，不拥有 durable 写入，也不在内部做 semantic repair loop。
- runner timeout、非 final outcome、`finish_reason=length`、空文本、非 JSON、top-level 非 object、缺必填 key、字段类型 / 值非法，都会作为 proposal failure 收口。
- `proposal_failed`、`quality_check_rejected`、`hard_threshold_after_compact` 都在 Host operation 层按 attempt budget 做 whole-candidate repair retry；取消请求在下一次 attempt 前 fail closed。
- repair attempt 可以接收 Host-neutral 的失败类别 / validation issue 摘要，但每次必须重新产出完整 candidate；不得要求 LLM 返回 repair patch，不得由 Host 合并旧 proposal 的 valid fields 与新 patch。
- rejected attempt 不是 memory。Host 只记录 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 诊断；失败 candidate 的“好字段”不被部分采用。
- 不做 partial materialize。只有整体 candidate 通过 JSON/schema/value mapping、provenance、quality check 与必要预算闸门后，才允许写 compact artifact 和 `CONTEXT_COMPACTED`。
- 多 pass reactive compact 先分别通过 pass 级 proposal 与 quality gate，再由 Host deterministic merge 成单个 candidate，并对 merged candidate 再做全量 quality check。
- `CONTEXT_COMPACTION_FAILED` 是 Host governance diagnostic event，承载 attempt count、retry / repair budget 是否耗尽、diagnostic refs、fallback policy decision、fallback input window、fallback digest、fallback budget result 和 fallback action；它不是业务事实，不得进入 Evidence / Fact Memory，也不得作为 LLM-readable compact material。
- recent-window fallback 只选择 current input anchor 与 policy-bounded selected recent window，并在 selected recent window 内应用 protected recent floor；不得渲染 `stable / already represented` 等内部状态。若 fallback selected view 仍无法通过 Host context governance，则 fail closed。
- fallback dispatch 不是 compact 成功：不提交 `CONTEXT_COMPACTED`，不写 compact artifact，不 materialize memory snapshot，不生成 Session Summary / Answer Anchor / Forward Intent / `evidence_backed_facts`。
- RunInputBuilder 只消费当前 Run started 前、`fallback_action=dispatch`、且 current input ref 匹配的 active fallback view；渲染结果仍是 selected recent window 与当前输入。

## 六类语义模型

Conversation Memory 按语义用途划分为六类。#81 第一阶段只实施 session-scoped 的五类；User Profile Memory 是唯一跨 session 语义类，已拆到 GitHub Issue #115。

### vNext schema / producer / projection / prompt assembly 边界

WU-CM-01 的新设计只从六类语义模型出发定义 vNext schema、producer、projection 与 prompt assembly，不从当前旧字段反推新语义。旧字段只作为删除 / 迁移清单处理，不作为设计输入，也不得形成兼容 wrapper。

因此，第一阶段应定义新的 session-scoped snapshot / compact projection shape：

```text
ConversationMemorySnapshotVNext
  trace_memory
  evidence_fact_memory
  session_summary_memory
  answer_anchor_memory
  forward_intent_memory
  diagnostics
```

`UserProfileMemory` 不进入 session snapshot；它是 GitHub Issue #115 / WU-CM-11 的 durable cross-session profile 边界。

当前讨论稿不拍死 `ConversationMemorySnapshotVNext` 的最终字段名、JSON schema、dataclass / TypedDict / Pydantic 形态或 validator 细节，但必须明确：vNext compact I/O contract 与 snapshot typed schema 是进入 WU-CM-01 plan 前的 high blocker，不能留给 implementation 自行发挥。讨论稿升级为 Host design 真源时，必须正式定义：

- LLM-readable compact input material：每类 semantic memory 暴露给 compactor 的业务可读材料、prompt-local opaque label 规则和禁止暴露的 Host internal provenance。
- compact output JSON schema：每类 compact candidate 的 required / optional fields、allowed enum、source label 引用方式、长度上限、空值语义与多次 compact roll-forward 语义。
- Host internal provenance mapping：prompt-local labels 如何映射到 durable EventLog / accepted evidence / assistant final answer / user-visible run state refs，且该 mapping 不作为模型阅读材料。
- accept barrier：JSON parse、schema-value mapping、source boundary、provenance、quality gate、whole-candidate repair retry、fail closed 与 fallback 的判定顺序。
- accepted projection / snapshot schema：通过 accept barrier 的 compact candidate 如何物化为 `ConversationMemorySnapshotVNext` typed view，哪些字段只存在于 diagnostics，哪些字段允许进入 RunInputBuilder。
- producer mapping：compact 前、compact 成功后、post-compact delta、fallback 与后续明确非 prompt-conditioned producer 分别能生成哪些 semantic memory。
- prompt assembly view：RunInputBuilder 消费 snapshot typed fields 的 section 顺序、bounded selection、floor / cap 与 current input 边界。
- tests：invalid / missing / stale source label、schema invalid、provenance mismatch、partial candidate invalid、fallback 不生成高阶语义、post-compact delta 可见与 compact roll-forward 的可断言用例。

因此，这个 blocker 的裁决是：现在只在讨论稿固定设计责任和最低契约，不在讨论稿中提前锁死完整 schema；但该 blocker 必须在讨论稿升级为 `docs/host/design.md` 时关闭。WU-CM-01 只能消费设计真源，不能直接消费本讨论稿作为 implementation contract。

旧 `pinned_state`、`working_assumptions`、`conversation_continuity`、`stable layer`、`history pool` 与 `recent raw turns floor` 不再作为顶层 semantic model：

- `working_assumptions` 已被 WU-CM-02 裁决为 rejected / closed；旧字段删除或迁移必须由 WU-CM-01 schema / projection slice 明确覆盖。
- `pinned_state` 不能作为 god bag 保留；其中仍有价值的 session-scoped 任务状态只能按新语义进入 Forward Intent Memory 或明确删除。
- `conversation_continuity` 不能作为粗池子保留；连续性材料必须按 Trace Memory、Session Summary Memory 或 Answer Anchor Memory 边界表达。旧 Minimum Preserve 裁决为 Trace Memory 下的 `reference_continuity_items`，不是独立 memory layer。
- `stable layer`、`history pool` 与 `recent raw turns floor` 只能作为 prompt assembly / deterministic bounded selection policy 结果或配置字段讨论，不能继续充当 memory category。

每个 session-scoped 语义必须在 WU-CM-01 design / plan 中写清：

- producer：哪些 canonical EventLog event、accepted compact output 或明确非 prompt-conditioned producer 能生成它。
- projection schema：snapshot / compact artifact 中的 typed view 字段、source refs、长度 / 枚举 / 去重 / 淘汰规则。
- accept barrier：LLM candidate 需要通过哪些 Host schema、provenance、source boundary、quality 与 budget gate。
- prompt assembly：RunInputBuilder 渲染位置、deterministic bounded selection owner、排序、去重、fallback 行为，以及 compact 前 / compact 后 / compact failure fallback 的差异。
- tests：compact 前为空或 selected recent window 行为、compact 后生成、post-compact delta 可见、fallback 不生成高阶语义、invalid candidate 不物化。

### 1. Trace Memory

Trace Memory 负责对话连续性，不负责事实证明。

数据来源：

- `USER_INPUT_ACCEPTED` 中的用户输入。
- `RUN_SUCCEEDED.final_answer` 中的助手最终回答。
- 历史中用户可见的 Run 失败、取消、等待或恢复状态；当前用户说“继续 / 恢复”的文本本身属于 `current_input_anchor`，不属于 Trace Memory。

投影规则：

- compact 前，Trace Memory 只来自 selected recent window。
- compact 时，Trace material 作为连续性材料进入 compactor。
- compact 后，Trace Memory 由 accepted compacted trace projection、post-compact delta material 与 protected recent floor 共同表达。
- Trace Memory 不包含内部 Attempt retry、compact retry、projection repair、scheduler 治理细节或 fallback diagnostics；只有已经成为用户可见对话上下文的 Run 状态才可进入 Trace material。
- 第一阶段不解析 tool response，不把 accepted evidence 归入 Trace Memory。
- Reference Continuity Item 是 Trace Memory 下的受限 item type，用于保存 compact 后仍需解析代词、序号、“刚才那个”等局部承接的最小上下文。它是旧 Minimum Preserve 的新名称；不是独立语义层，不是 fact、summary、answer anchor 或 forward intent。

落地边界：

- producer：raw delta 来自 user input / assistant final answer / 用户可见 Run 状态；compacted trace projection 只能来自 accepted `CONTEXT_COMPACTED`。
- projection schema：`trace_memory` 保存 bounded continuity items，可包含 `reference_continuity_items`；不保存工具事实证明、不保存内部治理 event。`reference_continuity_items` 只能保留理解局部指代所需的最小文本、source refs 与 reason，不能保留整段长输入。
- prompt assembly：compact 前与 fallback 只渲染 selected recent window + current input；compact 后渲染 accepted trace projection + selected post-compact recent window + current input。

### 2. Evidence / Fact Memory

Evidence / Fact Memory 负责工具证据与基于证据的 claim。这里的 fact 是 Host-accepted claim，不是 Host 对现实世界 truth 的证明。

数据来源：

- `TOOL_CALL_REQUESTED` 先进入 EventLog，再交给 LLM / tool loop。
- `TOOL_RESULT_ACCEPTED` 通过 Host accept barrier 后保存 accepted evidence envelope、payload / artifact refs 与 digest。
- LLM-facing evidence material 只包含可读 tool、query、response、source text 与 prompt-local opaque label。
- event id、payload / artifact ref、digest、durable evidence id 只存在于 Host internal provenance map，不得作为模型阅读材料，也不得要求模型返回。

投影规则：

- compact 前，Evidence / Fact Memory 是 selected recent window 中的可读 tool query / response / evidence material。
- compact 时，compactor 读取 selected recent window 中的 tool query / response material，提出 `evidence_backed_fact` candidates。
- `evidence_backed_facts` 必须引用本次 compact material 中的 prompt-local opaque evidence label；该 label 必须由 Host provenance map 映射到 accepted `TOOL_RESULT_ACCEPTED` material。
- compact 后，只有通过 Host accept barrier 的 `evidence_backed_fact_candidates` 才能物化为 `evidence_backed_facts`。
- compact failure fallback 只保留 selected recent window 中仍被选中的 tool query / response material，不生成 `evidence_backed_facts`。
- accepted evidence 存在但 compactor 没有产出合法 fact candidate 时，Host 只记录 diagnostic，不合成 fallback fact。

落地边界：

- producer：accepted evidence envelope 来自 `TOOL_RESULT_ACCEPTED`；`evidence_backed_facts` 只来自 accepted `CONTEXT_COMPACTED` 中通过 Host accept barrier 的 fact candidates，或后续明确设计的非 compact producer。
- projection schema：`evidence_fact_memory` 至少区分 readable recent evidence material 与 accepted evidence-backed fact view；fact view 必须绑定 Host internal provenance map，但模型只看到业务可读 claim 与来源说明，不看到 durable refs。
- prompt assembly：compact 前 / fallback 渲染 selected recent window 中的 readable tool query / response；compact 后渲染 accepted evidence-backed facts 加 selected post-compact recent evidence material。

### 3. User Profile Memory

User Profile Memory 是唯一跨 session 语义类，不混进 session Conversation Memory。#81 只固定边界：User Profile 的 durable store、profile update、撤销、删除、导出、隐私与跨 session profile projection 均由 GitHub Issue #115 承接。

### 4. Session Summary Memory

Session Summary Memory 负责当前 session 的 compact / rollup，服务长对话连续性，不替代事实。

投影规则：

- compact 前，Session Summary Memory 为空。
- compact 成功后，accepted `CONTEXT_COMPACTED` 产生 session summary。
- summary 不能替代 `evidence_backed_facts`。
- 多次 compact 使用 rolling compacted view；latest accepted compacted view 是下一次 compact 的 previous accepted view。

落地边界：

- producer：只来自 accepted `CONTEXT_COMPACTED`。
- projection schema：`session_summary_memory` 保存当前 session 的 rolling summary view、source boundary 与必要 source labels / refs 映射；不得保存 raw compact artifact JSON 或 failed proposal。
- accept barrier：summary 不能声称未由 source material 支撑的业务事实，不能替代 evidence-backed facts，不能覆盖 current input anchor。
- prompt assembly：compact 前与 fallback 为空；compact 后作为 compacted view 的 summary section 渲染，并与 evidence-backed facts、answer anchors、forward intents 分区。

### 5. Answer Anchor Memory

Answer Anchor Memory 保存上一轮或历史回答中可被用户后续指代的结构化轮廓，例如“三个风险”的第 1 / 2 / 3 点，用于支持“第二点展开”“刚才第三个风险”等追问。

边界规则：

- compact 前，Answer Anchor Memory 为空。
- 第一阶段不对 final answer 做规则化、deterministic outline parser 或 LLM parser。
- Answer Anchor 只能来自 accepted compact output，或明确设计的非 prompt-conditioned producer。
- Answer Anchor 必须引用本次 compact material 中的 prompt-local opaque source label；Host 内部再把 label 映射到 assistant final answer / assistant conclusion 的 durable source refs。
- Answer Anchor 只服务对话指代和局部展开，不能自动升级为 `evidence_backed_fact`。
- Reference Continuity Item 只保留长输入或 compact material 中理解代词、序号、局部承接所需的最小 continuity item；它归属 Trace Memory，不承担 final-answer outline 指代职责。

落地边界：

- producer：只来自 accepted `CONTEXT_COMPACTED`，或后续明确设计的非 prompt-conditioned producer；第一阶段不在 compact 前对 final answer 做 outline parser。
- projection schema：`answer_anchor_memory` 保存 bounded anchor items、anchor label / title、children / ordinal-safe display text、source refs 映射与淘汰规则；不得依赖 prompt-local label 名字的顺序语义。
- accept barrier：anchor 必须绑定本次 compact material 中的 assistant final answer / conclusion source label；不能绑定 tool evidence 后冒充 fact。
- prompt assembly：compact 前与 fallback 为空；compact 后按 bounded policy 渲染非空 anchor section，不根据当前 prompt 动态召回或触发。

### 6. Forward Intent Memory

Forward Intent Memory 保存待澄清问题、未完成任务、下一步任务状态等前瞻意图。它不是真实世界事实，也不直接驱动工具执行，只辅助下一轮 prompt 构造或澄清问题。

边界规则：

- compact 前，Forward Intent Memory 为空。
- 第一阶段不对 prompt / final answer 做 intent parser，也不生成 hidden plan。
- Forward Intent 只能来自 accepted compact output，或明确设计的非 prompt-conditioned producer。
- Forward Intent 必须引用本次 compact material 中的 prompt-local opaque source label；Host 内部再校验 source refs、长度和允许类型。

落地边界：

- producer：只来自 accepted `CONTEXT_COMPACTED`，或后续明确设计的非 prompt-conditioned producer；第一阶段不根据当前 prompt 生成 hidden plan。
- projection schema：`forward_intent_memory` 保存 bounded intent items，例如 open question、pending clarification、pending user-visible task state、next-step note；每项必须有 allowed type、status、source refs 与过期 / supersession 规则。
- accept barrier：Forward Intent 不能被当作工具执行计划或事实证明，不能覆盖本轮用户输入，也不能自动触发工具。
- prompt assembly：compact 前与 fallback 为空；compact 后作为 bounded task-state / clarification section 渲染，帮助下一轮回答或澄清，但执行权仍属于 Host / Agent 正常 tool loop。

## 关键边界

- 原始痕迹全量存在于 EventLog、descriptor 和 artifact，不等于全量进入 prompt。
- accepted evidence 是证据，不等于已抽取的 `evidence_backed_fact`。
- assistant final answer、回答锚点、用户输入、episode summary、reference continuity item、用户画像、前瞻意图都不能自动升级成 `evidence_backed_fact`。
- 跨 session 用户画像必须有独立 durable 边界，不能伪装成 session memory 字段；该边界由 GitHub Issue #115 跟踪。
- 任何可自动学习的长期信息都必须有来源、置信度、更新时间、撤销路径和用户可见解释。
