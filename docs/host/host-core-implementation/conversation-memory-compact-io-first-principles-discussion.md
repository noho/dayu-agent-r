# Conversation Memory Compact I/O 第一性原理讨论稿

## 背景

本讨论稿记录一次重新从第一性原理出发的 Conversation Memory / Context Compaction 设计校准。目标不是修补当前实现，而是先回答：compact 发生时，LLM compactor 应该看到什么、输出什么，Host 又应该如何把 LLM 可读 evidence 与 canonical EventLog provenance 连接起来。

当前实现暴露出的 smoke 失败说明：仅靠 `soft_threshold_context_ratio` 不能证明 compactor prompt 安全。若 compactor 输入把当前用户长输入、raw transcript、EventLog wrapper、Host refs 或 evidence metadata 重复塞入 prompt，即使 dispatch 估算低于 hard threshold，compactor provider 仍可能真实超窗。

## 核心裁决草案

LLM compactor 的输入必须是面向模型可读的 compact material，而不是 Host 内部账本字段。

Host 内部需要 canonical provenance；LLM 需要可阅读内容和短引用标签。这两者不能混为一谈。

本讨论稿同时裁决：Conversation Memory 需要重新设计。当前设计中的 stable layer 子项 `evidence anchors / tool facts / provenance` 不应继续作为独立 memory layer 存在。它与 `evidence_backed_facts` 的 evidence refs、EventLog 中的 `TOOL_RESULT_ACCEPTED` / `TOOL_CALL_REQUESTED`、payload / artifact provenance 重复，并且会诱导实现把 Host 内部账本字段渲染进 memory prompt。

建议重塑后的结构为：

```text
Conversation Memory
  -> stable layer
      -> pinned_state
      -> evidence_backed_facts
      -> working_assumptions
      -> open_questions
  -> history pool
      -> conversation_continuity
      -> recent raw turns floor
      -> older raw turns
      -> episode summaries
```

其中：

- `accepted tool result`：EventLog canonical fact，来源是 `TOOL_RESULT_ACCEPTED`。
- `evidence block`：compact prompt 内临时渲染的 LLM 可读 query / result / source locator。
- `evidence_backed_fact`：compact accept 后进入 memory stable layer 的事实声明，携带 evidence refs。
- `provenance`：Host 内部 label / ref / digest / artifact mapping，不是 LLM-facing memory layer。

```text
LLM 可见：
  Evidence E1
  tool: read_section
  query: 读取 2024 年报 管理层讨论与分析
  result:
    ...工具返回内容...
  source / locator:
    ...工具结果可读来源信息，如有...

Host 内部：
  E1 -> TOOL_RESULT_ACCEPTED event
     -> TOOL_CALL_REQUESTED event
     -> payload digest / source refs / locator refs / artifact refs
```

`event_id`、`payload_ref`、`outcome_digest`、`query_ref` 这类 Host provenance key 不应作为 LLM 的主要语义输入。裸 id 对 LLM 不可解引用，只会增加噪音和 token 开销。

## 旧 `dayu-agent` Conversation Memory 实现对照

`/Users/leo/workspace/dayu-agent/dayu/host/conversation_memory.py` 是一个已经长期使用并通过
`/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md` 实测的可靠 baseline。它与本讨论稿的方向高度一致，应作为 P12.5 的行为参照，而不是被当前
`dayu-agent-r` 中 EventLog range dump 式实现替代。

旧实现的关键机制：

- Memory 是两层结构：`pinned_state` 永远完整渲染、不参与预算竞争；history pool 中放 recent raw turns、older raw turns 和 episode summaries。
- `recent_turns_floor` 是下限保底，不是上限。最近 N 轮 raw turn 强制保留、不消耗 memory budget；更老 raw turn 才按剩余预算从新到旧回放。
- Compaction 是独立 LLM 调用，messages 只有 compaction system prompt 与一个 user JSON payload，不是在 ordinary run messages 后继续追加。
- Compaction user payload 是可读业务材料，不是内部账本 dump。payload 包含 `pinned_state`、最近 episode summaries、待压缩 turns；turn 内是 `user_text`、`assistant_final`、`tool_uses.result_summary`、warnings/errors。
- Compaction 输出严格 JSON，并在同一轮 LLM 调用里生成 `episode_summary` 与 `pinned_state_patch`。
- Compaction candidate 是未压缩 history 的 older prefix，并保留 recent tail；持久化后的后台 compaction 不再额外传当前 `user_text`，避免当前 turn 被重复计数。
- 长会话 prompt 稳定主要靠 bounded rendering：episode summaries 可以持久追加，但普通 run 只渲染预算内的最新 summaries。

这些机制直接支持本讨论稿的几个裁决：

- Compactor prompt 应基于 compact material pack，而不是 EventLog / Host provenance dump。
- `pinned_state` 应是 materialized current state，不应把 patch log 暴露给 LLM。
- 当前输入、raw turn、tool result 不能在 compact prompt 中重复出现。
- compact trigger 估算必须尽量贴近将要发送给普通 run / compactor run 的真实渲染内容。
- Conversation Memory 应保持克制；长上下文窗口优先留给财报材料、工具结果和当前分析上下文。

但旧实现也有明确边界，不能原样照搬为 P12.5 的最终设计：

- 旧实现没有 EventLog canonical provenance；`ConversationTranscript` 是运行态真源，而 P12.5 必须以 EventLog 为 canonical truth，Conversation Memory 只是 projection / read model。
- 旧实现没有独立的 `evidence_backed_facts` stable layer。它用 `episode_summary.confirmed_facts` 与 `pinned_state` 做跨轮反幻觉。
- 旧实现中的工具信息是 `ConversationToolUseSummary.result_summary`，不是 raw accepted tool result。它默认工具结果已被压缩成摘要，因此不能单独解决“几万字管理层讨论与分析中哪些事实应进入 memory”的通用抽取问题。
- 旧实现没有 evidence refs / source refs / locator refs 的可审计映射；`confirmed_facts` 是事实文本，不携带它来自哪个 accepted tool result。
- 旧实现没有 provider overflow 后的 reactive multi-pass compact；它主要解决 proactive / background transcript compaction。
- 旧实现对结构化记忆膨胀的处理是 prompt 侧预算裁剪，而不是显式 consolidation / retention。

因此，P12.5 应继承旧实现的稳定骨架，但补上 evidence-backed 语义：

```text
旧实现：
  compaction input = pinned_state + recent_episodes + candidate_turns(tool result_summary)
  compaction output = episode_summary + pinned_state_patch

P12.5：
  compaction input = pinned_state + bounded stable layer + recent_episodes
                   + candidate_turns + accepted tool evidence blocks
  compaction output = episode_summary_candidate
                    + pinned_state_patch_candidate
                    + evidence_backed_fact_candidates
                    + working_assumption / open_question candidates
                    + minimum_preserve_item_candidates
```

旧实现的 `confirmed_facts` 可以视为 `evidence_backed_facts` 的前身，但不能直接等价。P12.5 中，事实进入 stable layer 前必须引用 prompt-local evidence labels；Host accept barrier 再把这些 labels 映射回 `TOOL_RESULT_ACCEPTED` / `TOOL_CALL_REQUESTED` 等 canonical provenance。这样既保留旧实现已验证的 prompt 克制与追问连续性，又补上通用 evidence-backed memory 的审计边界。

## 第一轮结束后有什么

第一轮结束后，Host 已经有 committed canonical facts：

```text
USER_INPUT_ACCEPTED
TOOL_CALL_REQUESTED
TOOL_RESULT_ACCEPTED
RUN_SUCCEEDED / terminal summary
```

其中：

- `TOOL_RESULT_ACCEPTED` 是 accepted tool evidence 的 canonical anchor。
- `TOOL_CALL_REQUESTED` 是 evidence 的 query / provenance，不是 evidence 本体。
- assistant final answer / terminal summary 只提供 conversation continuity，不能自动成为 evidence-backed fact。
- stable layer 不应凭空产生；`evidence_backed_facts` 必须来自 compact / extraction accept barrier。

因此第一轮结束后，真正可用于后续 extraction 的是 accepted tool result 的可读内容；真正可用于短链路连续性的是 user / assistant raw continuity。

## 第一轮结束即触发 compact

若第一轮完成后立刻触发主动 compact，compactor 输入应包含：

- 第一轮 conversation continuity：用户输入、assistant final / terminal summary 的 bounded 可读内容。
- 第一轮 accepted tool evidence blocks：工具 query、工具 result、工具结果自带 source / locator 可读信息，以及 prompt-local evidence label。
- 已有 stable layer：fresh session 通常为空；非 fresh session 则是已有 pinned state、evidence-backed facts、working assumptions、open questions 的 bounded view。

不应输入：

- full EventLog range wrapper。
- 裸 `TOOL_RESULT_ACCEPTED.event_id` / `TOOL_CALL_REQUESTED.event_id` 作为主要语义输入。
- payload ref / digest / cursor / policy 等 Host 内部账本字段。
- 同一 raw content 的重复副本。

输出应包含：

- `episode_summary_candidate`：压缩第一轮对话连续性。
- `pinned_state_patch_candidate`：当前目标、主体、用户约束、开放问题。
- `evidence_backed_fact_candidates`：从 evidence blocks 提取的 facts，引用 prompt-local labels，例如 `E1`。
- `minimum_preserve_item_candidates`：只保留后续短链路指代需要的最小 continuity。

Host accept barrier 负责把 `E1` 映射回 canonical EventLog provenance，校验 fact candidate 没有引用不存在的 evidence。

## 第二轮 dispatch 前触发 proactive compact

若第一轮已完成，第二轮用户输入已 accepted，但第二轮 Run 尚未 dispatch，此时 proactive compact 的主体是第二轮之前的历史，不是第二轮当前输入本身。

输入应包含：

- 第一轮 conversation continuity。
- 第一轮 accepted tool evidence blocks。
- 第二轮当前用户输入的 bounded anchor：说明当前待处理输入是什么，用于 continuity 和 retained current input 校验。
- 已有 stable layer 和已有 episode summaries，如果存在。

此时通常不包含第二轮 accepted tool evidence blocks，因为第二轮 Run 还没执行工具。

关键约束：

- 第二轮当前用户输入不能完整重复出现在 `current_message_summary` 与 raw context 两处。
- 如果第二轮当前输入本身就是巨大 payload，compact 不应先完整读两遍它；应把它作为 current input anchor 或按 hard threshold / 用户可见失败策略处理。
- proactive compact 的主要目标是压缩此前 history segment，为当前 Run dispatch 腾出窗口。

## 两轮对话都完成后触发 compact

若第一轮和第二轮都已经完成，然后发生 compact，输入应覆盖这次要被压缩掉的 history segment：

```text
U1 / A1 continuity
E1 = 第一轮 accepted tool evidence block
U2 / A2 continuity
E2 = 第二轮 accepted tool evidence block
已有 stable layer / episode summaries（如有）
```

此时第二轮 accepted tool evidence blocks 必须进入输入，因为第二轮工具结果已经是 committed canonical facts。

输出可以包含：

- 从 `E1` 提取的 fact candidates。
- 从 `E2` 提取的 fact candidates。
- 同时引用 `E1` 与 `E2` 的 derived fact candidates。
- 两轮 episode summary。
- 后续追问所需的 minimum preserve items。
- pinned state / working assumptions / open questions 的更新。

## Accepted Evidence 的最小语义

`accepted evidence` 不应是额外重型持久化实体。它的最小语义是：

```text
accepted evidence = Host 已接受的 TOOL_RESULT_ACCEPTED canonical fact
```

面向 LLM 时，Host 临时渲染为 evidence block，并分配 prompt-local label：

```text
E1 -> readable query + readable result + readable source/locator
```

面向 Host persistence / audit 时，Host 保存 label 到 canonical provenance 的映射：

```text
E1 -> TOOL_RESULT_ACCEPTED event id
   -> TOOL_CALL_REQUESTED event id
   -> payload digest / artifact refs / opaque source locator refs
```

如果未来保留 `AcceptedEvidenceEnvelope`，它只能是内部 computed view 或 artifact metadata，不能成为 LLM 主要阅读对象，也不能成为独立事实真源。

## Compact Request 的边界

Compaction request 应表达 compact input segment，而不是从 Session 起点无脑重建全量 EventLog。

从 LLM 调用形态看，compact 是一次独立 compactor run，而不是在 ordinary run messages 后面继续追加。该 run 的 messages 应只有：

```text
SystemMessage:
  compact / extraction 指令、边界规则、输出 JSON schema

UserMessage:
  Host 组装出的 compact material pack
```

`UserMessage` 的职责是承载 compact material，不承载 Host 内部账本 dump。它应是 ordinary run 需要依赖的 history / memory / evidence 的去重、分段、可读版本。

建议输入模型：

```text
stable_input:
  pinned_state
  evidence_backed_facts
  working_assumptions
  open_questions

history_input:
  recent raw turns / older raw turns in compact segment
  episode summaries
  assistant terminal continuity

evidence_input:
  prompt-local evidence blocks for accepted tool results in compact segment

current_input_anchor:
  current input ref
  bounded current input summary / digest / short text
```

其中 `current_input_anchor` 只用于边界与 continuity，不应成为重复 raw payload 容器。

## Proactive Compact 的预算含义

在上述 I/O 边界下，`soft_threshold_context_ratio = 0.65` 的 proactive compact 不应因为 compactor context 太长而失败。

理由是 proactive compact 触发时，ordinary run 输入约等于 context window 的 65%。compactor run 读取的 material pack 应是同一批历史 / evidence material 的去重重组，再加 compact system prompt、输出 schema、section headers 和 prompt-local labels。只要 material pack 不重复塞内容，剩余约 35% window 应足以覆盖 compact 指令、schema、labels、少量 provenance mapping 与模型输出空间。

因此 proactive compact 必须满足：

- compact material token 不应显著大于触发 compact 的 ordinary input material token。
- compact user prompt 不得重复当前输入、raw turn 或 tool result。
- compact material pack 必须基于 memory / history / evidence 的去重 view。
- compactor prompt budget 必须按即将发送给 compactor 的真实 messages 估算；若估算仍超过 compactor hard budget，说明 material pack builder 有 bug 或 input segment 选择错误，不能盲打 provider。

当前 smoke 失败正是反例：ordinary dispatch 估算约 69 万 token，但 compactor prompt provider 真实报 146 万 token，因为当前长输入被重复渲染，且 request 中混入了过多 Host wrapper / metadata。

## Reactive Compact 的分段语义

Reactive compact 来自 provider context overflow。此时真实 provider 已证明 ordinary messages 过大，Host 不应再把 overflowed messages 一次性塞给 compactor。

Reactive compact 应对 overflowed ordinary input 做分段 / 层级压缩：

```text
ordinary run input M 触发 provider overflow
Host 冻结 M 为 compact material list

if M 可一次放进 compactor:
    compact(M)
else:
    prefix = M 中较旧、可压缩、约 55%-60% compactor budget 的 material
    suffix = M 剩余 material

    C1 = compact(prefix)
    M2 = C1 + suffix

    if M2 仍然过大:
        继续 compact(M2 的旧 prefix)
    else:
        compact 或直接进入 recovery dispatch
```

这里的 55%-60% 是 material token budget 的经验目标，不是按轮数切。切分单位应是 compact material block：

- turn block：user / assistant continuity。
- evidence block：tool query + result。
- episode summary block。
- existing stable layer block。
- current input anchor。

Reactive path 的关键约束：

- 先压缩 older prefix，保留最近 raw turns 与 current input anchor。
- 按 token / material budget 切，不按轮数切；一轮可能只有两句话，也可能包含几万字工具结果。
- prompt-local evidence labels 可以在每个 pass 内重新分配，但 Host 必须保留 label 到 canonical provenance 的映射，并在跨 pass 产物中转化为 stable fact refs / compact artifact refs。
- 若单个 evidence block 本身超过 compactor budget，不能靠切 N 轮解决；需要 evidence block 内部分段，同时保持同一个 canonical evidence provenance。
- reactive compact 不依赖估算证明一次成功，而是通过 bounded multi-pass compact + recovery dispatch / provider overflow 闭环收敛，超过 policy 上限后 fail closed。

## 长会话中的结构化记忆膨胀

Compact 不能只是把 raw turns 变成 structured append log。若每次 compact 都持续追加：

```text
pinned_state patches
evidence_backed_facts
working_assumptions
open_questions
episode summaries
minimum preserve / conversation_continuity items
```

长会话最终仍会超出上下文窗口。区别只会从 raw transcript 膨胀变成 structured memory 膨胀。

因此 compact 必须同时承担 extraction 与 memory consolidation / retention 的职责。EventLog 和 artifacts 可以永久 append 以便审计和 rebuild，但 RunInputBuilder / compactor input 只能读取 bounded working set。

### Pinned State

`pinned_state` 对 LLM 可见时应是 materialized current state，不是 patch log。

- EventLog 可以保存完整 patch history。
- memory projection 负责 materialize 当前 pinned state。
- RunInputBuilder 和后续 compactor input 只看当前 pinned state。
- 多次 compact 不应让 LLM 看到一串历史 pinned patches。

### Working Assumptions 与 Open Questions

`working_assumptions` 与 `open_questions` 是当前工作台状态，不是历史流水。

后续 compact 应输出 replacement / merge / resolve candidate，而不是无限 append：

- 已解决 open question 应移除或归档。
- 重复 assumption / question 应合并。
- stale assumption 应降级到 episode summary 或丢弃。
- 当前可见 working set 必须受 policy top-K / size budget 限制。

### Episode Summaries

episode summaries 需要分层再压缩，而不是全部进入 prompt。

建议模型：

```text
recent episode summaries:
  最近 K 个，仍可进入 ordinary run / compact input

older episode summaries:
  被 roll up 成 higher-level summary

archive summaries:
  只保留 artifact / EventLog refs，不进入普通 prompt
```

### Evidence-backed Facts

`evidence_backed_facts` 必须有 stable layer budget。memory projection 可以保存更多 facts，但普通 RunInputBuilder / compactor input 只能选择 bounded relevant working set。

选择策略应至少考虑：

- 当前 pinned subject / current goal 相关性。
- 最近被引用或刚生成的 facts。
- 用户当前问题涉及的 evidence / subject。
- policy 限制的 top-K / size budget。

超出 working set 的 facts 留在 durable memory / artifact / retrieval index，不应全部塞入上下文。

### Conversation Continuity / Minimum Preserve

minimum preserve 和 conversation continuity 是短寿命层，主要服务下一轮或近几轮指代解析。

- 每次 compact 后应合并、过期或替换。
- 不应长期累积。
- 若某个 continuity item 已被 stable layer 或 episode summary 覆盖，应从 working set 移除。

### 输出需要表达 Retention / Consolidation

长期设计上，compact 输出不应只有新增候选，还应表达保留、合并、降级或归档意图。例如：

```json
{
  "pinned_state_patch_candidate": {},
  "evidence_backed_fact_candidates": [],
  "episode_summary_candidate": {},
  "memory_retention_candidate": {
    "keep_fact_refs": [],
    "demote_fact_refs": [],
    "merge_assumption_refs": [],
    "resolve_open_question_refs": [],
    "rollup_episode_summary_refs": []
  },
  "minimum_preserve_item_candidates": []
}
```

第一版实现可以先用 policy 在 projection / RunInputBuilder 侧做 bounded selection，但设计真源必须承认：compact 是 extraction + consolidation，不是无限 append。

## 输出 JSON 草案

LLM 输出应继续是严格 JSON，但 evidence refs 使用 prompt-local labels：

```json
{
  "episode_summary_candidate": {
    "summary": "bounded text",
    "source_turn_refs": ["T1", "T2"]
  },
  "pinned_state_patch_candidate": {
    "current_goal": "text or null",
    "confirmed_subjects": ["text"],
    "user_constraints": ["text"],
    "open_questions": ["text"]
  },
  "evidence_backed_fact_candidates": [
    {
      "candidate_id": "local id",
      "claim_text": "bounded text",
      "evidence_kind": "observed_value|quoted_statement|table_value|derived_from_evidence",
      "evidence_refs": ["E1"],
      "attributes": {}
    }
  ],
  "working_assumption_candidates": [],
  "open_question_candidates": [],
  "minimum_preserve_item_candidates": [
    {
      "item_id": "local id",
      "label": "short text",
      "text": "bounded text",
      "source_refs": ["T2"],
      "preserve_reason": "needed_for_local_followup"
    }
  ],
  "retained_current_input": {
    "current_input_ref": "current input ref",
    "retain": true
  }
}
```

Host 接收后必须：

- 校验 `evidence_refs` 都来自本次 prompt-local evidence label set。
- 将 labels 映射回 canonical EventLog provenance。
- 拒绝无 evidence 的 `evidence_backed_fact_candidates`。
- 拒绝 episode summary 冒充 evidence-backed fact。
- 拒绝超出 compact input segment 的 source refs。
- 写入 `CONTEXT_COMPACTED`，由 memory projection 消费后物化 stable layer 与 history pool 更新。

## 当前实现偏离

当前实现已经暴露出至少两个偏离：

- proactive compaction 从 EventLog range 临时重建 raw context，且当前实现使用 `start_event_sequence=1` 到当前输入，容易把非本次 compact segment 的历史全部塞入 request。
- 当前用户输入被放入 `current_message_summary.summary_text`，同时又作为 `USER_INPUT_ACCEPTED` raw context item 渲染，导致长输入重复进入 compactor prompt。

这两个问题解释了 smoke 中 `soft_threshold_context_ratio=0.65` 仍然出现 compactor provider 超窗：dispatch 估算对象约 69 万 token，但 compactor prompt 真实请求约 146 万 token。

## 后续实现方向

实现修复不应从“给当前 request 再加几个截断”开始，而应先重塑 compact I/O 边界：

- 明确 compact segment selection，不再从 Session 起点无脑扫描。
- 把 LLM 可见 evidence block 与 Host provenance mapping 分离。
- 当前输入只作为 bounded anchor，不重复进入 raw context。
- compactor prompt budget 必须按将要发送给 compactor 的真实 message 内容估算，而不是复用 dispatch input estimate。
- memory snapshot / history pool 应成为 compact 的主要语义输入；EventLog raw reads 只服务于 compact segment 内必要 raw evidence 和 continuity material。
