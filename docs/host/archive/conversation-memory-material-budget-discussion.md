# Conversation Memory Material Budget 讨论稿

本文档只记录本轮围绕 Conversation Memory material 产量、compact input/output 上限与 fallback selected recent window 的调查结论和设计裁决。本文不是设计真源；正式设计仍以 `docs/host/design.md` 为准。

## 背景

`utils/smoke_host_public_conversation_memory_scenarios.py` 在 `core-d2-group-pressure-no-tool` 场景暴露了两个相关问题：

- compaction proposal 连续失败，诊断为 `TraceReadableItemVNext.text exceeds maximum length`。
- compact 失败后 fallback 裁决允许 dispatch，但 worker 启动时因 `fallback selected block id is missing from material view` 失败。

进一步讨论后确认，不能只把 `TraceReadableItemVNext.text <= 1200` 当作孤立 bug。需要一起核对：

- 代码里还有哪些 LLM-facing memory / compact material 的产量没有来自 `memory_projection_policy`。
- `memory_projection_policy` 当前字段和值是否真的符合 `docs/host/design.md` 的 Conversation Memory 设计。

## 设计真源校准

本轮所有讨论必须从两个设计源头出发：

1. Conversation Memory 的输入公式：

```text
memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material
```

2. Prompt assembly 的渲染公式：

```text
rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

其中 `latest_accepted_compacted_view` 又必须展开为五类 Session Semantic Memory：

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

这两个公式与五类 memory 是所有后续设计的源头。后续任何 selector、fallback、compact input、schema、DTO 或 RunInput rendering 规则，都只能细化这两个公式，不能另起一套 memory material 产量逻辑。

核心边界：

- `latest_accepted_compacted_view` 是最新 accepted compact projection。
- `post_compact_delta_material` 是 latest compact cursor 之后的 canonical EventLog material；没有 accepted compact 时从 session 起点开始。
- `current_input_anchor` 是当前 Run 的用户输入保护锚点，不属于历史 memory material。
- `selected_recent_window_policy` 从 `post_compact_delta_material` 中确定性选择 bounded recent window。
- `protected_recent_floor_policy` 保护最近若干 turn group；本轮裁决中一个 turn group 等于一个 Host admitted user Run。

fallback 语义不是另一套 memory 逻辑。更准确地说，fallback 分为两段：tier 1-3 是 compact recovery fallback，对同一套 material 用更保守的 assembly 重新构造 compact input，并继续送 LLM compactor；tier 4-5 是 compact recovery 全失败后的 deterministic dispatch fallback，不再调用 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact，不 materialize memory snapshot，只影响本次 RunInput rendering。

```text
normal:
  latest_accepted_compacted_view
  + normal selected post_compact_delta_material
  + current_input_anchor

fallback:
  tier 1-3: compact recovery with tighter selected window / degraded compacted view / delta-only;
  tier 4-5: dispatch fallback with floor-only / current-input-only.
```

因此，fallback 的 `selected_recent_window` 与 ordinary assembly 使用的 `selected_recent_window` 是同一个语义对象，只是 fallback 使用更保守的 caps / tier。tier 1-3 仍然属于 compact operation 的恢复尝试；tier 4-5 才是不再调用 LLM compactor 的 dispatch fallback。

### 写回设计真源的验收标准

讨论稿被写回 `docs/host/design.md` 后，必须能让后续实施从 Conversation Memory 的源头无歧义进入代码实现。验收标准不是“列出足够多背景”，而是实施 Agent 能从以下源头逐层推导，不需要自行补设计：

```text
rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

以及五类 Session Semantic Memory：

```text
trace_memory.reference_continuity_items
evidence_fact_memory.evidence_backed_facts
session_summary_memory.summary_text
answer_anchor_memory.anchors
forward_intent_memory.intents
```

写回后的设计必须明确回答：

- `memory_material` 如何由 `latest_accepted_compacted_view + post_compact_delta_material` 组成。
- `latest_accepted_compacted_view` 如何映射到五类 memory。
- `post_compact_delta_material` 包含哪些 committed material，排除哪些 material。
- `current_input_anchor` 如何参与 compact input / ordinary RunInput / fallback RunInput，且不得被持久化为历史 memory source。
- `selected_recent_window_policy` 如何从 `post_compact_delta_material` 选择完整 material block。
- `protected_recent_floor_policy` 如何以 `host_run_id` 为 turn group 保护最近 N 个 user Run。
- compact input 如何消费同一个 `rendered_context = assemble(...)`：compact input 不引入新的 design-level selector；它与 ordinary / fallback RunInput 共享 `latest_accepted_compacted_view`、`post_compact_delta_material`、`current_input_anchor`、`selected_recent_window_policy` 与 `protected_recent_floor_policy`，差异只在 renderer、source label 与 accept barrier 约束。
- fallback tier 如何分为 tier 1-3 compact recovery fallback 与 tier 4-5 deterministic dispatch fallback；哪些 tier 送 LLM compactor，哪些 tier 不送 LLM compactor、不提交 `CONTEXT_COMPACTED`、不生成 memory snapshot。
- LLM-facing memory material 为什么不允许字段级 silent truncation，以及上下文缩小时只能使用 selection、chunking、section-aware degrade 或 fail closed。
- 哪些实现层 DTO / schema / summary cap 是漂移产物，不能继续作为 LLM-facing memory material 的产量真源。

凡是上述任一问题仍需实施 Agent 自行裁决，讨论稿就还不能直接写回设计真源。

## 概念到 schema 的分层工作法

当前 design 框架不需要推倒重来，代码也不应整体重写。更稳妥的工作方法是把设计公式中的概念一层一层细化，直到每个概念都能对应到代码里的 typed schema、producer、selector 与 renderer。

需要细化的概念包括：

- `latest_accepted_compacted_view`
- `post_compact_delta_material`
- `memory_material`
- `current_input_anchor`
- `selected_recent_window_policy`
- `protected_recent_floor_policy`
- 五类 Session Semantic Memory

建议后续排查代码与拆 plan 时可按以下 mapping 表推进。本 mapping 只用于定位现有实现事实和漂移点，不属于写回 `docs/host/design.md` 的设计术语：

```text
design concept
  -> internal schema / typed DTO
  -> producer
  -> selector
  -> renderer
  -> current code owner
  -> gap /设计点
```

这件事的目标不是增加新抽象，而是把已经存在的概念边界写清楚。能复用现有 `ConversationMemorySnapshotVNext`、`PreDispatchCompactMaterialView`、`RunInputMaterialBlock`、`CompactMaterialPack` 的地方应优先复用；真正要删除或改造的是漂移出来的隐式产量真源、重复 material view 和偏离 `assemble(...)` 的实现层 selector。

### 五类 Session Semantic Memory

`latest_accepted_compacted_view` 不能长期停留为黑盒概念。按 `docs/host/design.md` 的 Snapshot Typed Schema，它不是一个独立字段，而是被物化为 `ConversationMemorySnapshotVNext` 中的五类 Session Semantic Memory：

- `Trace Memory`
- `Evidence / Fact Memory`
- `Session Summary Memory`
- `Answer Anchor Memory`
- `Forward Intent Memory`

更精确的概念展开是：

```text
latest_accepted_compacted_view =
  session_summary_memory
  + evidence_fact_memory
  + answer_anchor_memory
  + forward_intent_memory
  + trace_memory.reference_continuity_items

memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material
```

对应到 Snapshot Typed Schema：

```text
ConversationMemorySnapshotVNext
  latest_compaction_event_ref?: HostInternalRef
  trace_memory:
    reference_continuity_items
    selected_recent_window
  evidence_fact_memory:
    evidence_backed_facts
    recent_evidence_items
  session_summary_memory:
    summary_text
  answer_anchor_memory:
    anchors
  forward_intent_memory:
    intents
```

其中 `latest_compaction_event_ref` 只是 provenance ref，用来说明当前 snapshot 的 compacted semantic view 来自哪个 accepted compact event；它不是 `latest_accepted_compacted_view` 本体。

### `selected_recent_window` 不是第六类 Semantic Memory

`trace_memory.selected_recent_window` 比较特殊，容易被误读为第六类 semantic memory。它更准确地说是对 `post_compact_delta_material` 执行 bounded projection 后得到的 recent context view。

因此：

- `trace_memory.reference_continuity_items` 属于 compact 后的 Trace Memory semantic item。
- `trace_memory.selected_recent_window` 是未被 latest accepted compact 覆盖的 recent delta material view。
- selected recent window 可以包含 user input、assistant final answer、user-visible run outcome material、readable evidence material。
- selected recent window 不自动生成 summary、answer anchor、forward intent 或 evidence-backed facts。

这个区分很重要：如果把 `selected_recent_window` 当作独立 semantic memory，就会混淆 `latest_accepted_compacted_view` 和 `post_compact_delta_material`，也会让 fallback selected window 变成另一套 memory 系统。

### Material Boundary 的目标定义

本轮对 `post_compact_delta_material` 的可实现定义如下：

```text
post_compact_delta_material =
  latest accepted compact boundary 之后，
  到本次 assembly material snapshot cutoff 之前，
  尚未被 latest_accepted_compacted_view 覆盖的 committed canonical material
```

material 至少包括：

- 原始 `USER_INPUT_ACCEPTED.display_text`。
- 原始 `RUN_SUCCEEDED.final_answer`。
- readable accepted tool evidence。
- user-visible run outcome material。

`current_input_anchor` 单独传入 assemble，不应被当作历史 delta material。当前输入只有到下一轮成为历史时，才可能成为 `post_compact_delta_material` 的一部分。

更具体地说：

- 之前每轮的 prompt 是 `USER_INPUT_ACCEPTED.display_text`，属于 `post_compact_delta_material`。
- 之前每轮的 final answer 是 `RUN_SUCCEEDED.final_answer`，属于 `post_compact_delta_material`。
- 之前每轮的 tool request / response 在概念上属于 readable tool evidence；当前代码主要由 `TOOL_RESULT_ACCEPTED` 生成 evidence block，tool request 通常作为 query / provenance 挂在 evidence 上，不一定单独成为一个 material block。
- 之前每轮的用户可见非正常结果属于 `user_visible_run_outcome_material`，例如用户取消、用户可见失败、等待确认 / 澄清、无 final answer 的用户可见终止。
- 当前 Run 的 prompt 不属于历史 `post_compact_delta_material`，而是 `current_input_anchor`。
- 当前 Run 已发生的 tool request / response 需要区分 assembly 阶段：如果是在 reactive compact、recovery 或 continuation 这类当前 Run 已执行到一半的 assembly snapshot 中，已 committed 且 accepted 的 tool result 可以作为 current-run delta / evidence material 进入；裸 `TOOL_CALL_REQUESTED` 没有 response 时，不应直接当成 evidence memory。
- 当前 Run 的 final answer 在当前 Run terminal 前还不存在；发生后会成为下一轮的 `post_compact_delta_material`，直到下一次 compact accepted 后被 roll into `latest_accepted_compacted_view`。

因此，`post_compact_delta_material` 的结束点不应被概念性地固定为 `current_input_event_sequence`，而应定义为“本次 assembly 的 material snapshot cutoff”。pre-dispatch assembly 是一个特例：cutoff 刚好等于 current input event sequence。reactive / recovery assembly 可以包含 current input 之后已经 committed 的 accepted tool evidence，但 `current_input_anchor` 仍然必须单独标记，不作为普通历史 prompt block。

当前代码中的 pre-dispatch compact material builder 已经实现了一个较窄的特例：

```text
latest compact event sequence + 1
  <= event_sequence
  < current input event sequence
```

并只读取三类 canonical facts：

```text
USER_INPUT_ACCEPTED
RUN_SUCCEEDED
TOOL_RESULT_ACCEPTED
```

这与“current input 单独作为 anchor”的方向一致。reactive / recovery 阶段的 current-run committed accepted evidence 统一挂到当前 `host_run_id` 的 turn group 下；它可以作为 current-run delta / evidence material 参与 assembly，但不得把 current input prompt 本身改写成历史 prompt block。

### Policy Boundary 的目标定义

`selected_recent_window_policy` 与 `protected_recent_floor_policy` 的设计边界裁决如下。

- selector 的候选集合是 `post_compact_delta_material`，不从 `latest_accepted_compacted_view` 中重新选择 raw recent window。
- selected item 的基本单位是完整 material block；material block 必须带 `turn_group_id`、role / material kind、source refs 与稳定 block id。
- `selected_recent_window_turn_floor` 保护最近 N 个 turn group；本轮裁决中 `turn_group_id = host_run_id`。
- accepted evidence 属于所属 Run 的 turn group；若该 turn 被 floor 保护，已 committed accepted evidence 应随 turn 一起保护。
- floor 与 item / char cap 冲突时，floor 优先；若 floor 本身按当前 conservative estimator 超过 hard threshold，进入 tier 5，必要时 fail closed。
- fallback 与 ordinary selected recent window 复用同一个 recent-window selection 语义，只替换 fallback caps / tier。
- selection 输出的 block id / provenance 必须从 selection 到 rendering 全程同源。

基于这些裁决，`TraceReadableItemVNext.text <= 1200`、fallback caps 不生效、fallback rendering 找不到 selected block id 等问题都归类为具体实现偏差，而不是设计待定问题。

### `user_visible_run_outcome_material` 的边界

`user_visible_run_outcome_material` 是用户已经感知到的 Run 结果状态，用于保持对话连续性。它属于 `post_compact_delta_material`，挂到所属 `turn_group_id = host_run_id`，可以进入 selected recent window，也可以作为 Trace Memory 的输入，但不得进入 Evidence / Fact Memory。

允许进入的内容只包括用户可见、业务可解释的结果状态：

- 用户取消：`本轮已由用户取消。`
- 用户可见失败：`本轮未完成，原因：<用户可见错误说明>`。
- 等待用户确认 / 澄清：`本轮等待用户确认。`
- 无 final answer 的用户可见终止：`本轮未产生最终回答。`

如果某个 Run 已经有 `RUN_SUCCEEDED.final_answer`，通常不需要额外渲染 succeeded outcome；final answer 本身就是用户可见结果。

禁止进入的内容：

- attempt id、execution id、cursor、checkpoint。
- compact failure、fallback tier、projection diagnostic。
- provider retry、runner internal state。
- payload ref、digest、event id。
- hidden policy、Host governance 细节。

### `protected_recent_floor_policy` 的语义单位

本轮裁决：`protected_recent_floor_policy` 语义上保护“最近 N 轮”，不是最近 N 个 raw event / raw block。

原因是用户说“刚才那个”“第二点”“继续上面”时，需要的是完整互动上下文，而不是孤立的最后几个 EventLog row。一个 turn group 至少应能覆盖：

```text
user prompt
+ assistant final answer, if terminal exists
+ accepted tool evidence used in that turn, if any
+ user-visible run outcome material, if any
```

因此，`selected_recent_window_turn_floor` 的设计单位是 turn group。当前代码多处按 raw user / assistant block 取最近 N 个，是实现偏差或命名漂移。

turn group 的边界固定为 Host admitted user Run：

```text
turn_group_id = host_run_id
```

accepted tool evidence 随所属 turn 一起进入 protected floor。未终态 current / in-flight Run 的未 committed evidence 不参与 historical floor；reactive / recovery / continuation 中已经 committed 的 current-run accepted evidence 挂到当前 `host_run_id`，可作为 current-run evidence material 参与 assembly。floor 保护的 turn group 超过 item / char caps 时 floor 优先；若按当前 conservative estimator 仍超过 hard threshold，进入 tier 5，必要时 fail closed。

### `context_window_size` 的定位

`memory_projection_policy.context_window_size` 的存在不应理解为 selected recent window caps 必须按 context window ratio 自动放大。它更合理的定位是：composition root 从 `models.json` 或 effective model config 读取模型上下文窗口后，作为 typed policy input 注入 Host，避免 Host memory 层反向读取 model catalog。

因此：

- Host memory 不读 `models.json`，只接受 typed `context_window_size`。
- `selected_recent_window_item_cap` / `selected_recent_window_char_cap` 仍是显式 profile cap，尽量保持模型窗口无关。
- `context_window_size` 可用于 validation、policy digest、profile 自洽校验和与 Context Governance 协同。
- 如果 256k 与 1m profile 需要不同 memory 行为，应由 profile 显式写不同 caps；Host 内部不应隐式按窗口比例推导 recent window cap。

换句话说，`context_window_size` 是 memory policy 的校验 / 校准输入，不是 `selected_recent_window_policy` 的直接比例参数。

## 五类 Session Semantic Memory 的输入 / 输出边界

在前述边界成立后，五类 Session Semantic Memory 可以按“不靠猜”的方式定义输入与输出。

统一输入模型是：

```text
compact_input_for_semantic_memory =
  previous latest_accepted_compacted_view
  + selected post_compact_delta_material
  + current_input_anchor, for boundary/context only
```

统一输出模型是：

```text
accepted compact output
  -> ConversationMemorySnapshotVNext
      trace_memory.reference_continuity_items
      evidence_fact_memory.evidence_backed_facts
      session_summary_memory.summary_text
      answer_anchor_memory.anchors
      forward_intent_memory.intents
```

`current_input_anchor` 可以帮助 compactor 理解当前任务边界，但不应被错误持久化为“已经发生的历史事实”。如果某个 output item 引用 current input anchor 作为长期 source，应由 accept barrier 拒绝。

### Trace Memory

输入：

- `post_compact_delta_material` 中的 user prompt、assistant final answer、必要 `user_visible_run_outcome_material`。
- 上一次 `trace_memory.reference_continuity_items`，作为 previous compacted view 的一部分参与 roll-forward。
- `current_input_anchor` 只用于理解本次 compact 边界，不作为可引用长期 source。

输出：

- `reference_continuity_items`：只保存后续局部指代解析需要的最小承接信息，例如“刚才那个”“第二点”“上面那组口径”。
- `selected_recent_window` 不属于 compacted semantic output；它是对 post-compact delta 的 bounded recent context view。

### Evidence / Fact Memory

输入：

- `post_compact_delta_material` 中的 readable accepted tool evidence。
- 上一次 `evidence_fact_memory.evidence_backed_facts`。
- selected recent window 中仍未被 compact 覆盖的 recent evidence。
- reactive / recovery snapshot 中当前 Run 已 committed 且 accepted 的 tool result。

输出：

- `evidence_backed_facts`：经过 compact accept barrier、带 evidence provenance 的事实。
- `recent_evidence_items` 如果保留，只应是 bounded recent evidence view，不是 compacted fact。

关键边界：

- 裸 `TOOL_CALL_REQUESTED` 没有 response 时，不应生成 fact memory。
- Session Summary 不能替代 evidence-backed facts；当 summary 与 fact 同时存在时，事实 claim 以 `evidence_backed_facts` 为准。

### Session Summary Memory

输入：

- 上一次 `session_summary_memory.summary_text`。
- selected post-compact delta 中的 user / assistant trace、answer、evidence / facts。
- 其它 semantic memory 的必要上下文，但不能把 summary 当成 fact store。

输出：

- `summary_text`：会话框架、长期主题、分析上下文的简要 roll-forward view。

关键边界：

- `summary_text` 不能承载精确财报事实的唯一依据。
- 需要精确引用的事实必须进入 Evidence / Fact Memory 或保留在 readable evidence material 中。

### Answer Anchor Memory

输入：

- `post_compact_delta_material` 中的 assistant final answer。
- 上一次 `answer_anchor_memory.anchors`。
- selected recent window 中需要后续回指的答案结构。

输出：

- `anchors`：可回指的回答锚点，例如“第二点”“刚才那张表”“上次比较结论”。

关键边界：

- Answer Anchor 不是 summary，也不是 fact store。
- Anchor 只服务后续回指和局部续写，不能替代原始 final answer 或 evidence-backed facts。

### Forward Intent Memory

输入：

- `post_compact_delta_material` 中 user prompt / assistant answer 明示或用户可见地建立的未完成意图。
- 上一次 `forward_intent_memory.intents`。
- `current_input_anchor` 只用于判断当前 Run 的边界和任务关系，不应被误持久化为已经完成的历史 intent。

输出：

- `intents`：未完成任务、后续分析方向、用户要求的延续状态。

关键边界：

- Forward Intent 不是 plan executor。
- Forward Intent 不保存 hidden chain-of-thought。
- 只保存用户可见、业务可解释的 forward context。

### fallback 边界

fallback 的目标是在 compact 输入过大、compact 失败或 compact 后仍不可 dispatch 时，尽量保留 memory 精度并让本次 RunInput 可继续。这里的 fallback 必须拆成两类：tier 1-3 是 compact recovery fallback，可以继续送 LLM compactor；tier 4-5 是 dispatch fallback，不再送 LLM compactor。

这里必须区分两个阶段：

```text
compact operation:
  可以调用 LLM compactor
  可以进行 bounded repair / retry
  成功 -> CONTEXT_COMPACTED -> 后续 projection 生成 memory snapshot
  tier 1-3 recovery 成功 -> CONTEXT_COMPACTED -> 后续 projection 生成 memory snapshot
  tier 1-3 recovery 全部失败 -> CONTEXT_COMPACTION_FAILED

fallback dispatch assembly:
  只在 tier 4-5 发生
  不调用 LLM compactor
  不提交 CONTEXT_COMPACTED
  不写 compact artifact
  不 materialize memory snapshot
  只为本次 RunInput 选择 / 降级 rendered_context
```

因此，tier 1-3 是“降低 compact input 后继续 compact”的恢复路径；只有 tier 4-5 属于 compact recovery 全失败后的 deterministic dispatch fallback。

fallback 不应一开始就丢弃 `latest_accepted_compacted_view`。本轮裁决采用分级降级：

```text
normal path:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      normal_selected_recent_window_policy,
      protected_recent_floor_policy
    )
```

如果 normal compact input 过大、compact output 不可接受，或 compact 后仍无法按当前 Context Governance budget dispatch，先尝试保留既有 compacted view，只收紧 selected recent window：

```text
fallback tier 1:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )

  action:
    send to LLM compactor
```

如果 tier 1 通过当前 conservative estimator 重新估算后仍超过 hard threshold，或无法构造合法 RunInput，先尝试对既有 `latest_accepted_compacted_view` 做 section-aware degrade，尽量保留事实和引用连续性：

```text
fallback tier 2:
  rendered_context =
    assemble(
      degraded latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )

  action:
    send to LLM compactor
```

如果 tier 2 通过当前 conservative estimator 重新估算后仍超过 hard threshold，或无法构造合法 RunInput，再进入 delta-only fallback：

```text
fallback tier 3:
  rendered_context =
    assemble(
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )

  action:
    send to LLM compactor
```

如果 tier 3 仍不可 dispatch，不应默认 fail closed。多轮会话不能因为 compact 失败就变成不可使用；compact failure 应优先表现为 memory 精度降级，而不是用户无法继续输入。

因此，fallback 定义为以下保底分层策略：

```text
tier 0 normal:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      normal_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input or ordinary RunInput according to Context Governance decision

tier 1 compact recovery with tighter recent window:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 2 compact recovery with section-aware compacted view degrade:
  rendered_context =
    assemble(
      degraded latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 3 compact recovery delta-only:
  rendered_context =
    assemble(
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 4 dispatch fallback floor-only:
  rendered_context =
    assemble(
      protected_recent_turn_floor,
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED

tier 5 dispatch fallback current-input-only:
  rendered_context =
    assemble(
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED
```

这个顺序的原因是：`latest_accepted_compacted_view` 通常是高密度 memory，不应优先丢弃；`post_compact_delta_material` 往往更大、更冗余，优先用更保守的 selected window 选择更少完整 material block，可以最大化 fallback 时的 memory 精度。若仍然过大，再对 compacted view 做 section-aware degrade，最后才退到 delta-only / floor-only / current-input-only。

section-aware degrade 的保留优先级：

```text
1. evidence_fact_memory.evidence_backed_facts
2. trace_memory.reference_continuity_items
3. answer_anchor_memory.anchors
4. forward_intent_memory.intents
5. session_summary_memory.summary_text
```

理由：

- `evidence_backed_facts` 精度最高，且是可证明事实，不应优先丢弃。
- `trace_memory.reference_continuity_items` 保护“刚才那个”“第二点”等局部承接。
- `answer_anchor_memory.anchors` 支持多轮回指。
- `forward_intent_memory.intents` 有用，但通常可从 current prompt 和 recent context 部分恢复。
- `session_summary_memory.summary_text` 语义精度最低，也最不应替代 facts，因此应最先整体降级或丢弃。

section-aware degrade 是 deterministic keep / drop 规则，不是新的 compact 或 summary。允许的动作只有：

- 保留完整 semantic section。
- 丢弃完整 semantic section。
- 在 section 内按确定性顺序保留 / 丢弃完整 semantic item。

禁止的动作：

- 截断 semantic item text。
- 重新 summary 或改写 summary。
- 改写 fact、answer anchor、forward intent 或 reference continuity item。
- 临时生成新的 compacted view。
- 让 fallback 产生新的 Session Semantic Memory。

section 内 item 的保留 / 丢弃顺序必须由设计固定，例如按 semantic priority、source recency、material order 或稳定 digest 排序；不得由实施代码临时判断“重要 / 不重要”。

保底策略的原则：

```text
current_input_anchor 必保
protected recent turn floor 尽力必保
evidence facts 优先保
summary 最先降级
compact failure 不应让长会话不可用
```

理论上，到 tier 4 后就不应再需要 compact。`protected recent turn floor + current_input_anchor` 已经是最小可用多轮上下文，不再依赖 `latest_accepted_compacted_view` 或完整 `post_compact_delta_material`。除非 `current_input_anchor` 太长、protected floor 中某个 turn 极长、evidence 随 floor 保护导致 floor 过大，或 floor 配置与当前模型窗口不自洽，否则 tier 4 应当可以 dispatch。

如果 `current_input_anchor + protected recent turn floor` 仍超预算，不应继续 compact tier 4，也不再引入额外 floor 降级分支，而应直接降级到 `current_input_anchor only`，并通过 HostEvent / diagnostic 暴露 memory degraded 状态；不得把内部 compact failure、fallback tier 或 policy diagnostic 直接投影给 LLM。

fail closed 应收窄为真正不可恢复或继续 dispatch 会破坏治理边界的场景，例如：

- `current_input_anchor` 本身超过 hard context budget，连当前用户输入都无法放入。
- durable EventLog / payload / artifact 损坏，无法构造可信输入。
- selected material provenance 不一致，继续 dispatch 会污染事实边界。
- cancellation、session closed、run state 已不允许继续。

tier 4-5 dispatch fallback 不提交 `CONTEXT_COMPACTED`，不写 compact artifact，不 materialize memory snapshot，不生成 summary、facts、anchors、intents 或 reference continuity items。tier 4-5 只影响本次 RunInput rendering。预算判断第一阶段使用现有 Context Governance conservative estimator；GitHub issue 20 的 provider/model-aware sizing adapter 完成后，只替换预算估算入口，不改变上述 memory / fallback 语义。

## Implementation Handoff Notes（仅供后续 plan 参考）

本节不是设计真源写回内容，只作为后续 Gateflow plan / implementation plan 的代码定位、scope 拆分和 slice 参考。写回 `docs/host/design.md` 时不得搬运 current code owner、current gap、allowed files、测试命令或代码类型名；只能搬运前文已经裁决的设计语义。

本节的作用是帮助后续实施前快速定位当前代码中的实现事实和漂移点，避免 plan 阶段重新摸索代码路径。

### Core Material / Policy Mapping

| Design concept | Internal schema / typed DTO | Producer | Selector / policy | Renderer | Current code owner | Current gap |
| --- | --- | --- | --- | --- | --- | --- |
| `latest_accepted_compacted_view` | ordinary path: `ConversationMemorySnapshotVNext` 的 five semantic memory sections；compact path: `PreDispatchCompactMaterialView.previous_compacted_view` / `CompactMaterialBlock` tuple；LLM compact input: `CompactReadableViewVNext` | Memory projection 消费 `CONTEXT_COMPACTED`；`build_pre_dispatch_compact_material_view(...)` 从 latest accepted compact event 构造 previous view | `semantic_memory_section_caps`；fallback tier 2 需要 section-aware degrade | ordinary RunInput: `_memory_messages(...)`；compact input: `conversation_compact_input_vnext_from_material_pack(...)`；fallback: degraded section renderer | `dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/run_input.py` | `DurableCompactArtifactProvider` 仍用 compact artifact summary 旁路 ordinary memory projection；compactor output schema cap 与 policy cap 双真源；section-aware degrade 未实现 |
| `post_compact_delta_material` | `RunInputMaterialBlock` tuple；pre-dispatch path: `PreDispatchCompactMaterialView.material_blocks`；reactive path: frozen material blocks | pre-dispatch: `_post_compact_delta_rows(...)` + `_pre_dispatch_delta_material_blocks(...)`；reactive: Engine ingest / overflow 时冻结 ordinary material | `selected_recent_window_policy` normal/fallback；`protected_recent_floor_policy` | ordinary RunInput selected recent window messages；compact input trace / answer / evidence material；fallback selected window | `dayu/host/compact_material.py`、`dayu/host/memory.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py` | pre-dispatch 只覆盖 `seq < current_input_event_sequence` 的特例；reactive / recovery current-run committed evidence 归属需要统一；tool request 不单独成 material，只通过 evidence query/provenance 进入 |
| `memory_material` | 当前没有单一 DTO；概念上是 `latest_accepted_compacted_view + post_compact_delta_material`；实现中分散为 memory snapshot、previous compacted view、delta material blocks | ordinary path 由 memory provider + compact artifact provider + continuity provider 拼接；compact path 由 compact material builder 生成；fallback path 由 context fallback selection 生成 | selected window / section-aware degrade / protected floor | ordinary RunInput、compact input、fallback RunInput | `dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py` | 缺少统一 material view 语义导致 selection / rendering 使用不同 block id 空间；`memory:*` / `compact:*` / `eventlog:*` 多套 id 漂移 |
| `current_input_anchor` | `CurrentInputAnchor`、`CurrentInputAnchorVNext`、`RunInputMaterialBlock(kind=CURRENT_INPUT_ANCHOR)`、ordinary final `UserMessage` | `_validated_current_input_event(...)`、`_current_input_anchor(...)`、`_current_input_material_block(...)`、`build_run_input_material_blocks(...)` | 必保；compact output 不得引用 current anchor 作为长期 source | ordinary RunInput 最后一条 user message；compact input current anchor；fallback current anchor | `dayu/host/compact_material.py`、`dayu/host/run_input.py`、`dayu/host/dispatch.py` | `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200` / `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS = 1200` 是 DTO 私有 cap；应改由 context governance / assembly policy 裁决 |
| `selected_recent_window_policy` | 当前散落在 `MemoryProjectionPolicy` flat fields：normal / fallback item cap 与 char cap；没有独立 typed section view | profile loader / Service assembly 注入 `MemoryProjectionPolicy` | 设计上从 `post_compact_delta_material` 中选择最近上下文；ordinary 与 fallback 复用同一 recent-window 语义，只替换 caps / tier | selected recent window messages、fallback selected material | `dayu/host/memory.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py` | fallback caps 当前没有真正成为 selector 真源；selection / rendering 不同源；context hard budget 替代了 deterministic fallback caps |
| compact input rendering | `ConversationCompactInputVNext`；当前代码中存在 `CompactSegmentSelection` / compact material block path | Context Governance 在 compact operation 内调用 EventLog-backed compact material builder 后，把同一个 `rendered_context = assemble(...)` 渲染为 compactor-readable input | 设计上不引入新的 selector；compact input 与 ordinary / fallback RunInput 共享 `selected_recent_window_policy`、`protected_recent_floor_policy` 与 material view，只改变 renderer、source label 与 accept barrier 约束 | `ConversationCompactInputVNext` 的 previous view / trace / evidence / answer / current anchor sections | `dayu/host/compact_material.py`、`dayu/host/compaction.py` | 当前实现层 `CompactSegmentSelection` 是代码事实，不是设计源头；后续实现应收敛到 `assemble(...)` 语义，不得让 compact input 另起一套 material selection 真源 |
| `protected_recent_floor_policy` | `selected_recent_window_turn_floor`，语义为 protected recent run floor；`turn_group_id = host_run_id` | profile loader / Service assembly 注入 `MemoryProjectionPolicy` | 保护最近 N 个 Host admitted user Run；Attempt / retry 不形成新 turn | selected window、fallback floor-only、compact input current/recent protection | `dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py` | 当前多处按 raw user / assistant blocks 取 floor；需要改为 run-level turn group，并定义 evidence membership |
| fallback tiers | 当前没有 typed schema；建议后续至少有 Host diagnostic / enum 表达 selected fallback tier | Context Governance 在 normal compact input 过大、compact output 不可接受或 compact 后仍不可 dispatch 时选择 tier | tier 1-3 是 compact recovery fallback：tighter window / section-aware degrade / delta-only，并送 LLM compactor；tier 4-5 是 dispatch fallback：floor-only / current-input-only，不送 LLM compactor；tier 失败用当前 conservative estimator 判断 | tier 1-3 compact input rendering；tier 4-5 fallback RunInput rendering；HostEvent / diagnostic 只暴露 degraded 状态，不暴露内部细节给 LLM | `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py` | 当前 fallback 是单级 recent-window fallback，且 selection/rendering 不同源；fail closed 过早；compact recovery tier、floor-only、current-input-only 未实现 |

### Semantic Memory Mapping

| Semantic memory | Snapshot schema | Accepted compact producer | Ordinary renderer | Compact input renderer | Current gap |
| --- | --- | --- | --- | --- | --- |
| Trace Memory | `TraceMemoryView.reference_continuity_items`；`TraceMemoryView.selected_recent_window` 仅是 delta recent view | `_reference_continuity_from_accepted_event(...)`；selected recent window 由 delta projection 维护 | `_memory_reference_continuity_message(...)`；`_memory_selected_recent_window_messages(...)` | `_trace_material_vnext(...)`；previous reference continuity blocks | `TraceReadableItemVNext.text` 误用 1200 上限；`selected_recent_window` 容易被误解为第六类 semantic memory；turn group floor 未实现 |
| Evidence / Fact Memory | `EvidenceFactMemoryView.evidence_backed_facts`；`recent_evidence_items` 是 recent evidence view | `_facts_from_accepted_event(...)`；recent evidence 来自 `TOOL_RESULT_ACCEPTED` selected window | `_memory_evidence_fact_message(...)`；recent evidence 进入 selected recent window / system envelope | `_evidence_material_vnext(...)`；previous readable facts | compactor fact item cap 与 policy cap 冲突；裸 `TOOL_CALL_REQUESTED` 不应生成 fact；recent evidence 与 fact memory 的渲染归属需保持唯一 |
| Session Summary Memory | `SessionSummaryMemoryView.summary_text` | `_session_summary_from_accepted_event(...)` | `_memory_session_summary_message(...)` | `_previous_compacted_view_vnext(...)` 的 session summary readable item | summary 不能替代 facts；`MAX_VNEXT_SESSION_SUMMARY_CHARS=2400` 与 profile `session_summary_char_cap=4096` 漂移 |
| Answer Anchor Memory | `AnswerAnchorMemoryView.anchors` | `_answer_anchors_from_accepted_event(...)` | `_memory_answer_anchor_message(...)` | `_previous_compacted_answer_anchors_vnext(...)` | anchor 只服务回指，不替代原始 final answer；schema item cap / char cap 与 policy cap 关系需明确 |
| Forward Intent Memory | `ForwardIntentMemoryView.intents` | `_forward_intents_from_accepted_event(...)` | `_memory_forward_intent_message(...)` | `_previous_compacted_forward_intents_vnext(...)` | intent 不是 plan executor，不保存 hidden chain-of-thought；current input 不应被持久化成已发生历史 intent |

### Assembly Path Matrix

| Path | Material input | Selector / fallback tier | Output renderer | Must preserve | Current implementation status |
| --- | --- | --- | --- | --- | --- |
| ordinary no compact needed | `latest_accepted_compacted_view + post_compact_delta_material + current_input_anchor` | normal selected recent window + protected turn floor | `_memory_messages(...)` + final current user message | current input、selected recent window role preservation、memory section order | 基本存在，但 compact artifact summary 旁路需要清理 |
| proactive compact input | `memory_material + current_input_anchor` | `assemble(...)` with selected recent window + protected floor；no compact-specific design selector | `conversation_compact_input_vnext_from_material_pack(...)` | current anchor not citable；selected delta provenance | 当前 pre-dispatch 特例存在；trace/current anchor DTO cap 漂移；现有 compact segment 代码应收敛到 `assemble(...)` 语义 |
| reactive compact / recovery input | overflow 时冻结 ordinary material；可能包含 current-run committed evidence | `assemble(...)` over frozen material view with selected recent window + protected floor；no compact-specific design selector | compact input / recovery RunInput | frozen material同源、current input anchor 单独标记 | 需要把 current-run evidence 归属写清，并与 proactive path 对齐 |
| compact recovery fallback tier 1 | `latest_accepted_compacted_view + post_compact_delta_material + current_input_anchor` | fallback selected window caps + protected floor | compact input to LLM compactor | 最大化 memory 精度，保留 compacted view | 当前未实现分 tier |
| compact recovery fallback tier 2 | degraded `latest_accepted_compacted_view + post_compact_delta_material + current_input_anchor` | section-aware degrade + fallback selected window | compact input to LLM compactor | facts、reference continuity 优先 | 未实现 |
| compact recovery fallback tier 3 | `post_compact_delta_material + current_input_anchor` | fallback selected window + protected floor | compact input to LLM compactor | recent delta / current input | 当前 fallback 接近但 selection/rendering 不同源 |
| fallback tier 4 | protected recent turn floor + current input | protected floor | fallback RunInput | turn group 基本 user-assistant 连续性 | 未实现 turn group floor |
| fallback tier 5 | current input only | no memory selection | current input final user message | current input | 作为保底策略未实现 |

### Plan Slice Reference（仅供 Gateflow plan 使用）

若后续已把前文设计裁决写回 `docs/host/design.md` 并进入 Gateflow，可参考以下 work slices 拆分，避免一次重写。本小节不是设计真源，不定义新增概念或契约：

1. **Design / typed policy grouping slice**：不改 JSON 结构，给 `MemoryProjectionPolicy` 增加 internal section views 或 helper，明确 selected window、protected floor、semantic caps、projection repair 分组。
2. **Rendered-context assembly slice**：定义 ordinary RunInput、compact input 与 fallback RunInput 都消费同一个 `rendered_context = assemble(...)`；compact input 不引入新的 design-level selector，只改变 renderer、source label 与 accept barrier 约束。
3. **Material view同源 slice**：让 fallback selection 与 fallback rendering 使用同一个 material view / block id 空间，消除 `selected block id is missing`。
4. **DTO cap cleanup slice**：移除或改造 `TraceReadableItemVNext` / `CurrentInputAnchorVNext` 的私有 1200 cap，使 LLM-facing material 产量回到 policy / governance。
5. **Fallback tiers slice**：实现 tier 1-3 compact recovery fallback 与 tier 4-5 dispatch fallback 的降级策略和 diagnostics，确保 compact failure 不让长会话不可用。
6. **LLM-facing no-silent-truncation slice**：移除 / 废除 compactor input/output DTO 中改变 LLM-facing memory material 产量的私有 item / char cap；保留必要 parser safety guard 时不得改变业务文本语义，也不得成为 profile 外的产量真源。

每个 slice 的测试都应至少覆盖：

- ordinary RunInput message shape；
- proactive compact input；
- compact failure fallback；
- protected turn floor；
- long delta material；
- current input anchor 不被持久化为长期 memory source；
- fallback degraded 后不会把 internal diagnostics 投影给 LLM。

## Design Update Candidate

本节是可迁回 `docs/host/design.md` 的规范草案。它不要求一次性重写代码，但应足够支撑后续 Gateflow plan：开发者可以据此判断目标、非目标、契约、状态机、实现边界、验收边界与残余风险。

### Scope

本设计只定义 Host Conversation Memory 如何从 committed EventLog material 生成 LLM-facing memory context，以及 compact 失败时如何降级 assembly。

本设计不引入：

- semantic search / vector recall / prompt-conditioned retrieval；
- UI / log / diagnostic preview 的展示截断规则；
- tool 原始输出抓取、下载、转换或 tool truncation policy；
- Host public API 变更。

如果后续实现发现必须修改 Host / Engine public API 或跨层 contracts，应在 Gateflow 的 goal confirmation 或 slice stop condition 中停下来单独裁决。

### Write-Back Order

写回 `docs/host/design.md` 时，本设计应按以下顺序展开，避免实施 Agent 从抽象概念自行补中间层：

1. 定义 normal path 与 five fallback tiers，明确每个 tier 的 `assemble(...)` 输入、是否送 LLM compactor、输出是 compact input / ordinary RunInput / fallback RunInput。
2. 定义 `assemble(...)` 的规则：从 `post_compact_delta_material` 做 selected recent window selection，按 `protected_recent_floor_policy` 保护 turn floor，必要时对 `latest_accepted_compacted_view` 做 section-aware keep / drop，不做 silent truncation。
3. 定义 compact / fallback 的输入输出：normal / tier 1-3 compact recovery 可以产出 accepted compact；tier 4-5 dispatch fallback 只产出本次 RunInput，不产出 compact artifact、`CONTEXT_COMPACTED` 或 memory snapshot。
4. 定义 accepted compact output 的五类 Session Semantic Memory，并明确 `current_input_anchor` 不得被持久化为历史 memory source。

### Normative Definitions

#### Design axioms

Conversation Memory 的全部设计从展开版 `assemble(...)` 和五类 memory 展开。`memory_material` 可以作为 shorthand 使用，但设计真源应优先展示展开版，避免实施时把它误解成独立黑盒。

```text
memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material

rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

任何 implementation-level DTO、schema、selector、fallback、compact material builder 或 RunInput renderer，都只能细化上述公式，不得另行创造 LLM-facing memory material 产量路径。`memory_material` 只是 `latest_accepted_compacted_view + post_compact_delta_material` 的简写。

#### Canonical material source

Conversation Memory 的原始事实来源必须是 committed EventLog 及其 durable payload。read model、snapshot、compact artifact、fallback selection 都不能创造新的业务事实，只能选择、压缩、排序或渲染 canonical material。

EventLog material 进入 LLM-facing memory 前必须被转换成业务可读文本。裸 `event_id`、`payload_ref`、digest、cursor、tool_call_id 不得代替模型完成任务所需的语义内容。

#### `latest_accepted_compacted_view`

`latest_accepted_compacted_view` 是最新 accepted compact 生成并被 Host 接受的五类 Session Semantic Memory：

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

`trace_memory.selected_recent_window` 和 `evidence_fact_memory.recent_evidence_items` 是 recent delta view，不是 accepted compacted semantic view 的第六类 / 第七类 memory。

#### `post_compact_delta_material`

`post_compact_delta_material` 是 latest accepted compact boundary 之后、当前 assembly snapshot cutoff 之前，尚未被 `latest_accepted_compacted_view` 覆盖的 committed material。

至少包含以下 material kind：

- historical user prompt：来自 `USER_INPUT_ACCEPTED.display_text`；
- historical final answer：来自 `RUN_SUCCEEDED.final_answer`；
- accepted tool evidence：来自业务可读的 `TOOL_RESULT_ACCEPTED`；
- user-visible run outcome material：仅限用户已感知的取消、失败、等待确认 / 澄清、无 final answer 的用户可见终止；
- current-run accepted tool evidence：仅在 reactive / recovery / continuation assembly 中，且必须已经 committed。

不包含：

- 当前 Run 的用户输入；它属于 `current_input_anchor`；
- 裸 `TOOL_CALL_REQUESTED`；它可作为 accepted evidence 的 query/provenance，但不能单独成为 evidence fact；
- 未 committed、in-flight 或 hidden governance 状态。

#### `current_input_anchor`

`current_input_anchor` 是当前 Run 用户输入的保护锚点。ordinary RunInput 中它必须作为最终 user message；compact input 中它只能用于边界和当前任务理解；accepted compact output 不得把它当成已经发生的历史事实或长期 memory source。

如果 `current_input_anchor` 本身超过模型可承载上限，才属于真正不可恢复的 fail closed 条件；不得用 DTO 私有常量静默截断。

#### `memory_material`

`memory_material` 是一个概念层集合：

```text
memory_material =
  latest_accepted_compacted_view
  + post_compact_delta_material
```

实现可以不新增同名 DTO，但 selection 与 rendering 必须基于同一 material snapshot 和同一 block id 空间。禁止 selection 使用 `eventlog:*`，rendering 又重新构造 `memory:*` / `compact:*` / `accepted-tool-evidence:*` 后再尝试匹配。

### Policy Semantics

#### `selected_recent_window_policy`

`selected_recent_window_policy` 从 `post_compact_delta_material` 中选择 bounded recent window。normal 与 fallback 必须复用同一 recent-window selection 语义，只允许使用不同 caps / tier。

选择规则：

1. 按 committed material 的 session sequence / logical order 取最近 material。
2. 必须先满足 `protected_recent_floor_policy`。
3. 在 floor 之外，再按 item / char selection cap 选择更多完整 recent material block；不得对单个 LLM-facing material text 做 silent truncation。
4. 同一 recent-window selector 必须服务 ordinary memory projection 与 fallback selected window。
5. selector 输出必须带稳定 block id、source ref、role / material kind、turn group id 与 LLM-readable text。

compact input 不引入新的 design-level selector。它消费同一个 `rendered_context = assemble(latest_accepted_compacted_view, post_compact_delta_material, current_input_anchor, selected_recent_window_policy, protected_recent_floor_policy)`，并把该 context 渲染为 compactor-readable input。compact input 与 ordinary / fallback RunInput 的差异只在 renderer、source label、current input anchor 不可作为长期 source 引用、以及 compact accept barrier 约束；不得通过实现层 `CompactSegmentSelection` / `select_compact_segment(...)` 另起一套 material selection 真源。

#### `protected_recent_floor_policy`

`protected_recent_floor_policy` 保护最近 N 个 turn group，不保护裸 item 数。

本轮裁决中，一个 turn group 等于一个 Host admitted user Run：

```text
turn_group_id = host_run_id
```

Attempt、retry、provider retry、compactor proposal call 不形成新 turn。一个 turn group 至少包含：

```text
user prompt
+ assistant final answer, if terminal answer exists
+ accepted tool evidence used by that turn, if materialized
+ user_visible_run_outcome_material, if any
```

当前正在执行的 Run 的用户输入是 `current_input_anchor`，不是 historical turn material。reactive / recovery / continuation path 中已经 committed 的 current-run accepted tool evidence 可以挂在当前 `host_run_id` 的 turn group 下，但不得把未 committed / in-flight event 当作 historical memory。

当 floor 与 item / char cap 冲突时，策略必须显式裁决：

- normal / fallback selected window 中 floor 优先；
- 如果 floor 本身超过当前模型 hard budget，进入 fallback tier 5，而不是在 selector 内隐式丢弃 turn 的一半；
- 配置装配阶段应验证 fallback item cap 至少能容纳最小 turn floor 的结构性下限。

#### Selection policy and no silent truncation

LLM-facing memory material 不做字段级静默截断。需要缩小上下文时，只能通过 deterministic selection、section-aware degrade、material block chunking 或 fail closed 表达。

`memory_projection_policy` 中的 item / char 字段应理解为 selection / section working-set 上限，而不是“把一个业务文本截短到 N 字符”的授权。profile 可以暂时保持 flat JSON 字段，但 Host 内部必须把它们解释为以下四组：

```text
selected_recent_window_policy
protected_recent_floor_policy
semantic_memory_section_caps
projection_repair_policy
```

以下实现漂移不得成为 LLM-facing memory material 产量真源，应删除、废除或迁出 LLM-facing path：

- `TraceReadableItemVNext.text <= 1200`；
- `CurrentInputAnchorVNext.text <= 1200` / `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200`；
- `_COMPACT_SUMMARY_MAX_CHARS = 1200` 作为 ordinary RunInput 的 accepted compacted view 替代品；
- 与 `memory_projection_policy` 冲突并实际限制 accepted compact output 形状的 compactor output item / char 常量。

允许保留的上限只限于非 LLM-facing 结构字段、diagnostic / UI / log preview、parser safety guard 或 evidence block chunking。即便保留 parser safety guard，也不得改变业务文本语义，不得小于 packaged policy 声称可产出的形状，不得作为 profile 外的实际产量真源。

### Rendering Semantics

ordinary RunInput 的渲染顺序应稳定：

```text
system / scene instructions
+ latest_accepted_compacted_view rendered by five semantic sections
+ selected recent window rendered from post_compact_delta_material
+ current_input_anchor as final user message
```

compact input 的渲染输入应为：

```text
previous latest_accepted_compacted_view
+ selected post_compact_delta_material
+ current_input_anchor
```

compact input 的 `selected post_compact_delta_material` 来自同一个 `selected_recent_window_policy` / `protected_recent_floor_policy` assembly 语义；不存在独立的 design-level compact selector。

tier 1-3 compact recovery fallback 会把更保守的 `rendered_context` 送 LLM compactor；只有 tier 4-5 dispatch fallback 不提交 compact、不写 memory snapshot、不生成 accepted compact artifact、不调用 LLM compactor。dispatch fallback 只改变当前 RunInput 的 context assembly。

#### Compact output contract

normal compact 与 tier 1-3 compact recovery fallback 的 compactor accepted output 只能投影为五类 Session Semantic Memory：

```text
trace_memory.reference_continuity_items
evidence_fact_memory.evidence_backed_facts
session_summary_memory.summary_text
answer_anchor_memory.anchors
forward_intent_memory.intents
```

accepted compact output 可以提交 `CONTEXT_COMPACTED`，并由后续 projection materialize memory snapshot。tier 4-5 dispatch fallback 不产生 compact output，因此不得提交 `CONTEXT_COMPACTED`，不得生成 compact artifact，不得 materialize memory snapshot，也不得产生新的五类 memory。

### Fallback State Machine

compact input 过大、compact 失败或 compact 后仍无法按 policy dispatch 时，Host 不应让多轮会话直接不可用。除 durable corruption、run/session state invalid 或 current input 单独过大外，应先按 tier 1-3 尝试 compact recovery，再按 tier 4-5 做 deterministic dispatch fallback：

```text
tier 0 normal:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      normal_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input or ordinary RunInput according to Context Governance decision

tier 1 compact recovery with tighter recent window:
  rendered_context =
    assemble(
      latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 2 compact recovery with section-aware compacted view degrade:
  rendered_context =
    assemble(
      degraded latest_accepted_compacted_view,
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 3 compact recovery delta-only:
  rendered_context =
    assemble(
      post_compact_delta_material,
      current_input_anchor,
      fallback_selected_recent_window_policy,
      protected_recent_floor_policy
    )
  output:
    compact input -> send to LLM compactor

tier 4 dispatch fallback floor-only:
  rendered_context =
    assemble(
      protected_recent_turn_floor,
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED

tier 5 dispatch fallback current-input-only:
  rendered_context =
    assemble(
      current_input_anchor
    )
  output:
    fallback RunInput; no LLM compactor; no CONTEXT_COMPACTED
```

上述 normal 与 five fallback tiers 是 `assemble(...)` 的唯一入口形态。`assemble(...)` 本身不决定是否 compact，也不生成五类 memory；它只根据传入 material、selected window policy 与 protected floor policy，输出一个稳定、可渲染、可估算的 `rendered_context`。是否把 `rendered_context` 渲染成 compact input、ordinary RunInput 或 fallback RunInput，由 tier 的 output 规则决定。

section-aware degrade 的保留优先级：

1. 保留 `evidence_fact_memory.evidence_backed_facts`；
2. 保留 `trace_memory.reference_continuity_items`；
3. 保留 `answer_anchor_memory.anchors`；
4. 保留 `forward_intent_memory.intents`；
5. 最后保留、降级或丢弃 `session_summary_memory.summary_text`。

section-aware degrade 是 deterministic keep / drop 规则，不是新的 compact 或 summary。允许的动作只有：保留完整 semantic section、丢弃完整 semantic section，或在 section 内按确定性顺序保留 / 丢弃完整 semantic item。禁止截断 semantic item text、重新 summary、改写 fact / anchor / intent / reference continuity、临时生成新的 compacted view，或让 fallback 产生新的 Session Semantic Memory。section 内 item 的保留 / 丢弃顺序必须由设计固定，不得由实施代码临时判断“重要 / 不重要”。

fallback tier 可以写入 Host diagnostic / activity event，但投影给 LLM 的内容不得要求模型理解内部 tier 名称、cursor、block id 或 compact failure 细节。

进入下一 tier 的判断第一阶段使用当前 Context Governance conservative estimator；如果某 tier 重新估算后仍超过 hard threshold，或无法构造合法 RunInput，则进入下一 tier。GitHub issue 20 的 provider/model-aware sizing adapter 完成后，只替换 estimator / sizing adapter，不改变 tier 语义。

## Implementation Plan Reference（不写回设计真源）

以下内容不属于 `Design Update Candidate`，也不应写回 `docs/host/design.md`。它只作为后续 Gateflow plan 的拆分参考；真正写回设计真源的内容以上一节的 Scope / Normative Definitions / Policy Semantics / Rendering Semantics / Fallback State Machine 为准。

后续 Gateflow 可把本设计拆成以下顺序，每个 slice 都可独立 review / commit：

1. **Policy grouping slice**
   - Objective：在不迁移 JSON 的前提下，把 `MemoryProjectionPolicy` 的 flat fields 暴露为 typed semantic section views。
   - Allowed owner：`dayu/host/memory.py`、profile loader tests、必要的 config README。
   - Success signal：normal / fallback selected window、protected floor、semantic section caps、repair policy 在代码中有单一 typed 解释入口。

2. **Selected window selector slice**
   - Objective：实现 shared recent-window selector，覆盖 normal selected recent window、fallback selected recent window、memory projection selected recent window 与 compact input 的 selected delta material。
   - Allowed owner：`dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py`。
   - Success signal：同一组 material + policy 在 ordinary / fallback / compact input 路径得到同一 selected recent ids；fallback caps 实际生效；现有 compact-segment 实现不再形成独立 design selector。

3. **Turn group floor slice**
   - Objective：把 `selected_recent_window_turn_floor` 从 raw item floor 修正为 Host admitted user Run floor，即 `turn_group_id = host_run_id`。
   - Allowed owner：material projection / selector 相关 Host 模块。
   - Success signal：最近 N 轮的 prompt / final answer / accepted evidence 不被拆散；floor 与 cap 冲突有确定降级。

4. **Material snapshot identity slice**
   - Objective：selection 与 rendering 共用同一 material snapshot / block id 空间。
   - Allowed owner：`dayu/host/compact_material.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py`。
   - Success signal：不再出现 `fallback selected block id is missing from material view`；fallback rendering 不重新猜 ids。

5. **DTO cap cleanup slice**
   - Objective：移除 / 废除 compact input DTO 私有 1200 cap；LLM-facing material 不做 silent truncation，只通过 selection / chunking / degrade / fail closed 缩小上下文。
   - Allowed owner：compact input DTO、compact builder、相关 tests。
   - Success signal：长 prompt / 长 answer 不因 `TraceReadableItemVNext` 本地校验失败；current input 不被静默截断。

6. **Fallback tier slice**
   - Objective：实现 tier 1-3 compact recovery fallback 与 tier 4-5 dispatch fallback 状态机和 diagnostics。
   - Allowed owner：dispatch、engine ingest、context fallback、run input assembly。
   - Success signal：compact failure 后仍能构造可解释 RunInput；只有 current input 单独过大、durable corruption、invalid run/session state 才 fail closed。

7. **Compactor output cap alignment slice**
   - Objective：移除 / 废除与 `memory_projection_policy` 冲突的 compactor output item / char 私有 cap，消除 profile cap 与 schema cap 双真源。
   - Allowed owner：compactor output parser / schema、policy validation、execution profile tests。
   - Success signal：packaged profile 中每个 semantic memory 产量都只由 policy / selection 决定；parser safety guard 不改变业务文本语义，也不成为 profile 外的实际产量真源。

Gateflow plan 的最小验收命令应包括：

```text
source .venv/bin/activate
pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
python utils/smoke_host_public_conversation_memory_scenarios.py
python -m pyright dayu/ tests/ utils/
```

如果某个 slice 修改了 CLI / README 触发范围，再按 `AGENTS.md` 的 README 更新触发规则补充对应文档验证。

## 已核对的实现事实

### `memory_projection_policy` 当前字段

`dayu/config/execution_profiles.json` 中每个 profile 的 `memory_projection_policy` 包含：

- `context_window_size`
- `selected_recent_window_item_cap`
- `selected_recent_window_char_cap`
- `selected_recent_window_turn_floor`
- `fallback_selected_recent_window_item_cap`
- `fallback_selected_recent_window_char_cap`
- `evidence_fact_item_cap`
- `evidence_fact_char_cap`
- `evidence_fact_floor`
- `session_summary_char_cap`
- `answer_anchor_item_cap`
- `answer_anchor_char_cap`
- `forward_intent_item_cap`
- `forward_intent_char_cap`
- `reference_continuity_item_cap`
- `reference_continuity_char_cap`
- `reference_continuity_item_floor`
- `max_lag_events_for_inline_delta`
- `max_delta_repair_events`
- `policy_ref`

这些字段在 `dayu/host/memory.py` 的 `MemoryProjectionPolicy` 中也有 typed contract。

按当前讨论，这些字段不是都属于 `selected_recent_window_policy` / `protected_recent_floor_policy`。大部分字段仍然需要，但应按语义分组：

```text
memory_projection_policy:
  context:
    context_window_size
    policy_ref

  selected_recent_window_policy:
    normal:
      selected_recent_window_item_cap
      selected_recent_window_char_cap
    fallback:
      fallback_selected_recent_window_item_cap
      fallback_selected_recent_window_char_cap

  protected_recent_floor_policy:
    selected_recent_window_turn_floor

  semantic_memory_section_caps:
    evidence_fact:
      evidence_fact_item_cap
      evidence_fact_char_cap
      evidence_fact_floor
    session_summary:
      session_summary_char_cap
    answer_anchor:
      answer_anchor_item_cap
      answer_anchor_char_cap
    forward_intent:
      forward_intent_item_cap
      forward_intent_char_cap
    reference_continuity:
      reference_continuity_item_cap
      reference_continuity_char_cap
      reference_continuity_item_floor

  projection_repair_policy:
    max_lag_events_for_inline_delta
    max_delta_repair_events
```

字段保留倾向：

- `selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap` 仍需要；fallback 字段当前实现没有真正成为 selector 真源，后续应修正。
- `selected_recent_window_turn_floor` 仍需要，但语义应澄清为 protected recent turn group floor，而不是 raw block floor；将来可考虑更名。
- 五类 semantic memory section cap 仍需要，用于控制 `latest_accepted_compacted_view` 的 read model 产量。
- `reference_continuity_item_floor` 可以保留为显式 0，表达默认不强制保留 reference continuity。
- `max_lag_events_for_inline_delta` 与 `max_delta_repair_events` 仍需要，但它们属于 projection repair / catch-up 操作参数，不属于 memory material selection。
- `context_window_size` 仍需要，作为 composition root 注入的模型窗口事实 / 校验输入；它不是 recent window caps 的隐式比例来源。
- `policy_ref` 仍需要。

后续可在不阻塞设计真源写回的前提下补充到 JSON 的策略字段：

- `floor_degrade_policy`
- `semantic_memory_degrade_order`
- `fallback_tiers`

第一步不必立刻重写 `execution_profiles.json` 为嵌套结构。更稳妥的路径是先在设计和 typed helper 中建立 semantic grouping，让现有 flat fields 有清晰归属；等实现稳定后，再评估是否迁移配置结构。

### 额外存在的 compact input 上限

以下上限没有来自 `memory_projection_policy`，但会影响 compact input 或 compact input DTO：

- `TraceReadableItemVNext.text <= MAX_VNEXT_REFERENCE_CONTINUITY_TEXT_CHARS`，当前为 `1200`。
- `CurrentInputAnchorVNext.text <= CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`，当前为 `1200`。
- `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200`。
- `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096`。
- `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS = 4096`。

其中 `TraceReadableItemVNext.text <= 1200` 是这次 smoke 中直接触发失败的上限。它把 compact input 中的原始 trace delta material 当成 reference continuity 一类短文本处理，和 `post_compact_delta_material` 的设计语义不一致。按本轮裁决，这类 DTO 私有上限是实现漂移，应移除 / 废除，不能改写 LLM-facing raw delta material 的可读文本。

`CurrentInputAnchor* <= 1200` 也属于实现漂移。`current_input_anchor` 不是 memory item，但它是 compact / fallback / prompt assembly 的边界输入；如果当前用户输入很长，使用固定 1200 截断会影响 compact 对当前任务的理解。当前输入不得被 DTO 私有常量静默截断；若 current input 本身过大，应由 Context Governance fail closed 或通过显式上游输入治理处理。

evidence chunk 4096 与 trace 1200 的性质不同：chunking 可以是 material 分块和 provenance 粒度。若保留，它只能定义可追溯 material block 分块，不得静默截断业务文本，也不得让 chunk cap 成为 profile 外的 LLM-facing 产量真源。

### 额外存在的 compactor output schema 上限

以下上限没有来自 `memory_projection_policy`，但限制了 accepted compact output 的最大形状：

- `MAX_VNEXT_SESSION_SUMMARY_CHARS = 2400`
- `MAX_VNEXT_FACT_CLAIM_TEXT_CHARS = 2000`
- `MAX_VNEXT_ANSWER_ANCHOR_TEXT_CHARS = 1600`
- `MAX_VNEXT_FORWARD_INTENT_TEXT_CHARS = 1200`
- `MAX_VNEXT_REFERENCE_CONTINUITY_TEXT_CHARS = 1200`
- `MAX_VNEXT_DIAGNOSTIC_TEXT_CHARS = 1200`
- `MAX_VNEXT_SOURCE_LABELS_PER_ITEM = 16`
- `MAX_VNEXT_FACT_ITEMS = 64`
- `MAX_VNEXT_ANSWER_ANCHOR_ITEMS = 32`
- `MAX_VNEXT_FORWARD_INTENT_ITEMS = 32`
- `MAX_VNEXT_REFERENCE_CONTINUITY_ITEMS = 32`
- `MAX_VNEXT_DIAGNOSTIC_ITEMS = 32`

这些上限来自实现层 schema / parser，不来自 `memory_projection_policy`。凡是会实际限制 accepted compact output 中五类 semantic memory item / text 形状的上限，都是当前实现漂移，不能作为 LLM-facing memory material 的产量真源。

明显例子：

- profile 中 `evidence_fact_item_cap = 256`，但 compactor parser 最多接受 `MAX_VNEXT_FACT_ITEMS = 64`，所以实际 fact 产量上限是 64。
- profile 中 `session_summary_char_cap = 4096`，但 compactor candidate 先被 `MAX_VNEXT_SESSION_SUMMARY_CHARS = 2400` 卡住，所以实际 summary 产量上限是 2400。

按本轮裁决，`memory_projection_policy` 与 `rendered_context = assemble(...)` 是 memory / prompt assembly 产量与选择真源。上述 schema 上限应移除 / 废除，或收窄为不改变业务文本语义的 parser safety guard；它们不能继续与 profile 形成双真源。

### ordinary RunInput 的 compact artifact 摘要上限

`dayu/host/run_input.py` 中存在：

- `_COMPACT_SUMMARY_MAX_CHARS = 1200`

`DurableCompactArtifactProvider` 会把 accepted compact payload 渲染成一条 system message，内容是 `_vnext_compact_candidate_summary()` 的摘要，并用 1200 截断。

本轮裁决如下：

- 如果它是 UI/log/audit 摘要，1200 可以是 UI/log 层规则。
- 如果它进入普通 LLM RunInput，且代表 `latest_accepted_compacted_view`，则必须退出 LLM-facing path；ordinary RunInput 只能通过五类 semantic memory section 渲染 accepted compacted view。

按 `docs/host/design.md`，ordinary RunInput 应通过 Conversation Memory 的高阶 section 渲染 accepted compacted view，而不是用 compact artifact 摘要替代 memory projection。

### fallback caps 定义了但未实际成为 fallback selection 真源

profile 中定义了：

- `fallback_selected_recent_window_item_cap`
- `fallback_selected_recent_window_char_cap`

但当前 fallback selection 代码主要使用：

- `selected_recent_window_turn_floor`
- context hard budget estimate

没有实际用 `fallback_selected_recent_window_item_cap` / `fallback_selected_recent_window_char_cap` 作为 deterministic selected recent window 的直接 cap。

这意味着 profile 写了 fallback 产量，但 fallback selected view 的实际产量不是由这两个字段控制。

## 当前实现与设计的主要偏差

### 偏差一：compact input DTO 改写了 raw delta material 的产量

`TraceReadableItemVNext` 是 compactor LLM-readable input item，不是 EventLog，也不是 memory policy。它不应该用 `1200` 这种字段级常量决定 `post_compact_delta_material` 是否能进入 compact。

当前失败就是直接后果：长历史 user input 进入 trace material 后超过 1200，compaction request 在本地 typed contract 校验阶段失败。后续 semantic repair 重试无效，因为根因不是 LLM candidate 输出错，而是 Host 构造 compact input 时已经违反了自己的 DTO 限制。

### 偏差二：fallback selection 与 fallback rendering 使用不同 material view

proactive compact failure 后，fallback selection 从 EventLog-backed material view 中选择 block ids，例如：

- `eventlog:user:*`
- `eventlog:answer:*`
- `current:*`

worker 真正 dispatch 时，ordinary `RunInputBuilder` 又重新构造 material blocks，例如：

- `memory:*`
- `compact:*`
- `continuity:*`
- `accepted-tool-evidence:*`
- `current:*`

两套 block id 空间不一致，所以 `_fallback_context_messages()` 找不到 selected ids，触发 `fallback selected block id is missing from material view`。

按设计，fallback selected recent window 应该由同源 material view 选择并渲染，不能 selection 用一套 view、rendering 用另一套 view。

### 偏差三：policy 中“turn floor”与“item cap”的校验语义不足

`MemoryProjectionPolicy.__post_init__` 当前只校验：

```text
fallback_selected_recent_window_item_cap >= selected_recent_window_turn_floor
```

但 `selected_recent_window_turn_floor` 是“近轮保底”，不是单个 item 数。一个 turn 在实现中至少可能包含 user / assistant 两个 raw block，还可能有 evidence-like material。因此这个校验把 turn 和 item 混用了。

以当前 profile 为例：

```text
selected_recent_window_turn_floor = 4
fallback_selected_recent_window_item_cap = 8
```

如果按 user + assistant 估算，4 轮至少需要 8 个 raw turn blocks，刚好贴边；若再考虑 evidence，则不够。更重要的是，代码没有真正证明 fallback cap 能覆盖 floor 所需材料。

### 偏差四：floor 与 char cap 的冲突当前实现未统一

memory projection 中 `_limit_selected_recent_window()` 会先保护 floor item，再继续按 char cap 选其它 item。若 protected floor 本身超过 char cap，当前逻辑会让 floor 绕过 char cap。

fallback selection 当前没有使用 fallback char cap，而是依赖 context hard budget。

因此，同一个语义在不同路径下行为不一致：

- memory projection：floor 优先，可能超过 section char cap。
- fallback：fallback char cap 未生效，最后由 hard budget 决定。

本轮裁决：floor 优先。若 floor 本身按当前 conservative estimator 超过 hard threshold，进入 fallback tier 5，而不是在 selector 内静默截断或打散 turn group。配置装配阶段应尽量验证 fallback item cap 能容纳最小 turn floor 的结构下限。

### 偏差五：compactor output schema cap 与 memory policy cap 双真源

compactor output schema 的 per-field / per-list 上限和 memory policy 的 section cap 同时存在。当前没有明确 owner，也没有派生关系。

这会导致 profile 中的值看似可配，实际被 schema 常量提前拦截。例如 `evidence_fact_item_cap = 256` 实际上不可能超过 compactor parser 的 `64`。

本轮裁决：这类 schema cap 是实现漂移，应移除 / 废除，或收窄为不改变业务文本语义的 parser safety guard；不得继续作为五类 semantic memory 的实际产量上限。

## 已裁决问题

### 1. `memory_projection_policy` 是 LLM-facing memory material selection 真源

裁决为：是，但更准确地说，LLM-facing memory material 的上下文缩小方式是 selection / section-aware degrade / material block chunking / fail closed，不是字段级 silent truncation。

含义：

- selected recent window 的 item / char / floor 由 policy 控制。
- fallback selected recent window 的 item / char / floor 由 policy 控制。
- accepted compacted view 投影进 ordinary RunInput 的产量由 policy 控制。
- compact input 的 raw delta material 不再由 DTO 字段级 magic cap 截断。

仍可保留的例外：

- diagnostic / log / UI preview 的安全上限。
- durable id / digest / wait id 等非 LLM-facing 结构字段长度上限。
- tool truncation policy 对工具结果原始输出的上限，但它属于 `tool_truncation_policy`，不是 memory policy。

### 2. compactor output schema 上限不得成为独立产量真源

裁决：

- 现有会改变五类 semantic memory item / text 形状的 schema cap 属于实现漂移，应移除 / 废除。
- 如需保留 parser safety guard，只能防止结构性失控，不能改变业务文本语义，不能小于 packaged policy 声称可产出的形状，不能作为 profile 外的实际产量真源。
- 实施时优先删除 `evidence_fact_item_cap=256` 但 parser 只接受 64、`session_summary_char_cap=4096` 但 schema 只接受 2400 这类双真源。

### 3. selected recent window 的 floor 单位应定义为 turn 还是 raw block

当前字段名是 `selected_recent_window_turn_floor`，但实现多处按 raw user / assistant block 取最近 N 个，而不是按完整 turn 分组。

裁决：

- 保留 turn floor，且一个 turn group 等于一个 Host admitted user Run：`turn_group_id = host_run_id`。
- Attempt / retry / provider retry / compactor proposal call 不形成新 turn。
- turn group 应覆盖该 Run 的 user prompt、terminal final answer、accepted tool evidence，以及设计明确进入 LLM-facing context 的用户可见 Run 状态。

### 4. fallback caps 与 normal selected recent window caps 的关系

设计文档要求 fallback caps：

- 不小于 floor 所需材料。
- 不大于普通 selected recent window caps。

当前只校验了 item cap 与 turn floor 的弱关系，且 fallback caps 未实际生效。

裁决：

- fallback selected recent window 与 normal selected recent window 复用同一 selection 语义。
- fallback 可以使用更小 caps，但必须证明 floor 可容纳。
- 如果 floor 无法容纳，不允许运行时隐式截断或绕过 cap；按 fallback tier 5 降级，必要时 fail closed。

### 5. `_COMPACT_SUMMARY_MAX_CHARS = 1200` 必须退出 ordinary LLM RunInput

裁决：

- 如果 ordinary RunInput 已有 Conversation Memory snapshot，就不应再把 compact artifact 摘要作为另一份 accepted compacted view 输入。
- compact artifact 摘要可保留为 diagnostic / UI / log，但不能作为 LLM memory material 的独立产量路径。

## 初步调整方向

1. 删除 / 废除 `TraceReadableItemVNext.text` 对 raw trace material 的 1200 校验。
2. 重新定义 compact input material 的缩小规则：只允许通过 `assemble(...)` 中的 selected recent window policy、protected floor、material block chunking、section-aware degrade 或 fail closed 缩小上下文，不允许 trace item DTO 私有上限截断单条原始文本。
3. 让 fallback selected recent window 实际使用 `fallback_selected_recent_window_item_cap` 与 `fallback_selected_recent_window_char_cap`。
4. 修复 fallback dispatch：selection 与 rendering 必须使用同源 material view / 同一 block id 空间。
5. 统一 normal selected recent window、fallback selected recent window 与 compact input selected delta material 的 selector；compact input 不再作为独立 design selector，只作为 `assemble(...)` 的不同 renderer / consumer。
6. 删除 / 废除 compactor output schema 中与 `memory_projection_policy` 冲突、且实际改变五类 semantic memory 产量的 item / char cap，消除 `evidence_fact_item_cap=256` 但 schema 只接收 64 这类漂移。
7. 明确 floor 超 cap 的行为：floor 优先，不静默截断；若 floor 按当前 conservative estimator 仍超过 hard threshold，进入 fallback tier 5，必要时 fail closed。
8. 审视 `_COMPACT_SUMMARY_MAX_CHARS = 1200`，避免它作为 ordinary LLM RunInput 的隐式 accepted compacted view。

## 非目标

本文不裁决以下问题：

- 是否引入 semantic search / vector recall / prompt-conditioned memory retrieval。
- 是否调整 tool truncation policy。
- 是否调整 UI / log / diagnostic preview 的展示上限。
- 是否变更 Host public API / contracts。
- 是否修改 `docs/host/design.md` 真源。

## 推荐下一步

写回 `docs/host/design.md` 前，建议按上面的分层工作法把本轮裁决整理成 design-ready 章节，并确保以下设计点都以肯定句进入设计真源：

1. 把 `memory_material`、`rendered_context = assemble(...)` 与五类 memory 作为 `docs/host/design.md` Conversation Memory 的源头公式。
2. 明确 LLM-facing memory material 不允许 silent truncation；上下文缩小只能通过 selection、chunking、section-aware degrade 或 fail closed。
3. 明确 selected recent window floor 的单位是 Host admitted user Run：`turn_group_id = host_run_id`。
4. 明确 fallback 分为 tier 1-3 compact recovery fallback 与 tier 4-5 deterministic dispatch fallback；tier 1-3 可送 LLM compactor，tier 4-5 不调用 LLM、不提交 `CONTEXT_COMPACTED`、不 materialize memory snapshot。
5. 明确 fallback tier 的预算判断第一阶段使用现有 Context Governance conservative estimator；GitHub issue 20 后替换 sizing adapter。
6. 明确 compact artifact summary 不得作为 ordinary LLM RunInput 的 accepted compacted view 替代品。
