# P12.6 Design Review — DS Independent Review

## Review Metadata

- **Reviewer**: DS (Design Reviewer)
- **Target**: Phase 12.6 Conversation Memory design refinement, as recorded in `docs/host/design.md` §24 and §25
- **Controller artifact**: `docs/reviews/p12-6-design-refinement-controller-20260524.md`
- **Gate**: Design refinement review, not implementation review
- **Timestamp**: 2026-05-24T19:37:43+08:00
- **Truth sources**: `docs/host/design.md` §1, §24, §25; `docs/host/implementation-control.md` Phase 12.6; controller artifact
- **Discussion input** (not design truth): `docs/host/conversation-memory-compact-io-first-principles-discussion.md`

## Scope

Review whether the design refinement recorded in `docs/host/design.md` §24 and §25:
1. Satisfies Phase 12.6 goals and success signals
2. Removes the compact I/O root cause (not local stopgaps)
3. Preserves Host governance boundaries (Host as truth source, Conversation Memory as projection, Context Governance as orchestrator)
4. Avoids overdesign, public API drift, Engine changes, Fins/tool-provider leakage
5. Is specific enough to enter plan gate (handoff to implementation-ready plan without forcing the planning agent to redesign architecture)

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | Conversation Memory structure in §24 correctly removes the independent `evidence anchors / tool facts / provenance` memory layer | Confirmed. §24 line 2541-2544 explicitly removes this layer. |
| A2 | Compact material pack (§25) replaces EventLog range dump as compactor input | Confirmed. §25 lines 2734-2751 define material pack and forbid EventLog dump. |
| A3 | Prompt-local evidence labels (E1, E2) decouple LLM-facing evidence from Host provenance | Confirmed. §25 lines 2742-2749 define evidence_input with labels and internal provenance mapping. |
| A4 | Proactive compact material tokens ≤ ordinary run input material tokens | Confirmed. §25 lines 2752-2755 state this as a safety condition. |
| A5 | Reactive compact uses bounded multi-pass with fail-closed policy limit | Confirmed. §25 lines 2757-2762 define the reactive path. |
| A6 | Long-session retention/consolidation is part of memory semantics, not deferred optimization | Confirmed. §24 lines 2586-2594 define consolidation as basic semantics. |
| A7 | No Engine changes required | Confirmed. Phase 12.6 scope explicitly prohibits Engine changes. |
| A8 | No Fins/tool-provider leakage | Confirmed. Tool provider only produces TOOL_RESULT_ACCEPTED; fact extraction is Host-governed. |

## Findings

### F1-BLOCKED-[中]-compact segment 边界选择规则未明确定义

- **位置**: `docs/host/design.md` §25 material pack 定义，Phase 12.6 进入条件与成功信号
- **问题类型**: 不可直接实施
- **当前写法**: §25 定义 material pack 包含 `history_input`（compact segment 内的 raw turns、episode summaries）、`evidence_input`（compact segment 内的 accepted tool results）。讨论稿给出具体场景推演（第一轮后 compact、第二轮 dispatch 前 compact、两轮都完成后 compact），但设计真源 §25 未将 "compact segment 是什么" 的判定规则冻结为稳定契约。
- **反例/失败场景**: 实现 Agent 在以下情形下将被迫自行设计 segment 选择算法：
  - 非 fresh session 且已有 10 轮对话时，第 11 轮 dispatch 前触发 proactive compact——应压缩前 10 轮全部，还是只压缩最旧的 K 轮？
  - 第 10 轮工具返回了 50 万 token 的财报全文，第 11 轮只问了简单追问——segment 是否应以 token budget 而非轮次为切分单位？
  - 已有多段历史被 compact 过，新的 ordinary run input 已包含 episode summaries + recent raw turns + stable layer——proactive compact 的 segment 是否应排除已 compact 为 episode summary 的段落？
- **为什么有问题**: Phase 12.6 进入条件要求 "必须确定 compact material pack 的输入边界"，退出条件要求 "Compactor input / output 边界不再依赖 EventLog range dump"。若 segment 选择规则未明确定义，implementation agent 可能复用类似 `start_event_sequence=1` 的保守策略，直接违背根本设计意图。
- **直接证据**: 
  - §25 写 "compact segment 内的 raw turns"、"compact segment 内的 accepted tool results"，但未定义 segment 的起止判定。
  - 讨论稿 §"第一轮结束即触发 compact" 和 §"第二轮 dispatch 前触发 proactive compact" 给出了具体场景的 segment 定义，但讨论稿不是设计真源。
- **影响**: 实施 Agent 自行设计 segment 算法 → 若选择过宽（全部历史），重新引入 EventLog range dump 问题；若选择过窄，丢失 evidence 或 continuity 导致 compact 后追问失败。
- **建议改法和验证点**:
  1. 在 §25 material pack 定义中增加 compact segment 的判定规则（至少覆盖 proactive 路径）：segment 的上界是当前普通 run input 中除 `current_input_anchor` 以外的 history 材料；下界是上次 compact 已覆盖且已被 episode summary / stable layer 物化的最旧轮次之后。
  2. 验证点：实施 plan 中 segment selection 必须可测试——给定一个 EventLog cursor range 和 memory snapshot cursor，能确定性输出哪些 turn block / evidence block 进入本次 compact segment。
- **修复风险**: 低。只增加判定规则的文字描述，不改变已定义的 material pack 结构。
- **严重程度**: 中

### F2-BLOCKED-[中]-material pack builder 数据读取路径缺少显式声明

- **位置**: `docs/host/design.md` §24 accepted evidence envelope 定义，§25 material pack evidence_input 定义
- **问题类型**: 契约缺失
- **当前写法**: §24 定义 accepted evidence envelope "不记录、派生或暴露有界结果预览字段"；§25 定义 evidence_input 的每个 evidence block 包含 "raw result 或必要 raw transcript"。两处合起来看，evidence block 的 raw result 内容只能从 EventLog 的 `TOOL_RESULT_ACCEPTED` 事件中读取。但 §25 也写 material pack builder 不得 "从 Session 起点重放 EventLog ledger"，且设计真源没有一段文字显式声明：material pack builder 读取 compact segment 内 `TOOL_RESULT_ACCEPTED` 事件的 raw result，而不是从 accepted evidence envelope 读取。
- **反例/失败场景**: 实现 Agent 看到 §24 的 accepted evidence envelope 字段（`tool name`、`tool query`、`payload ref / digest`）后，尝试从 envelope 的 payload ref 回查 artifact store 拿 raw result，导致 artifact store 成为 compact hot path 依赖，且 payload ref 可能指向已截断/已过期/已迁移的 artifact。
- **为什么有问题**: 当前设计真源在 evidence block 内容来源上有歧义。accepted evidence envelope 是 provenance anchor，不是 evidence 内容容器；但 §24 和 §25 都没有一句话把 "material pack builder 从 EventLog 读 raw tool result" 写成显式契约。计划 Agent 或实施 Agent 可能做出错误推断。
- **直接证据**:
  - §24 line 2560-2561: envelope 记录 "payload ref / digest" 但不记录 raw result。
  - §25 line 2742-2743: evidence block 需要 "raw result 或必要 raw transcript"。
  - 两个事实之间的数据流连接（EventLog → raw result → evidence block）未显式写为稳定契约。
- **影响**: 实施 Agent 可能的错误路径：envelope.payload_ref → artifact store → raw result 回查（把 artifact store 变成 compact hot path），而非从 EventLog TOOL_RESULT_ACCEPTED 事件直接读取。若 artifact store 实现为 cold storage 或异步写入，compaction 可能失败或读空。
- **建议改法和验证点**:
  1. 在 §25 material pack 定义中增加一句显式声明：evidence block 的 raw result 内容来自 compact segment 内对应 `TOOL_RESULT_ACCEPTED` 事件的原始 `tool_result` 字段，不经过 accepted evidence envelope 或 artifact store 间接读取。
  2. 验证点：unit test 证明 material pack builder 不 import artifact store，不调用 `get_artifact` 或等价方法。
- **修复风险**: 低。增加一句契约声明，不改变任何结构。
- **严重程度**: 中

### F3-BLOCKED-[低]-reactive multi-pass compact 的跨 pass 产物提交流程未定义

- **位置**: `docs/host/design.md` §25 reactive compact 分段语义
- **问题类型**: 状态机漏洞
- **当前写法**: §25 line 2757-2762 定义 reactive compact 的分段语义（冻结 overflowed material list、优先压缩 older prefix、block-based multi-pass）。line 2757 提到 "prompt-local evidence labels 可以在每个 pass 内重新分配，但 Host 必须保留 label 到 canonical provenance 的映射，并在跨 pass 产物中转化为 stable fact refs / compact artifact refs"。但未定义跨 pass 的 EventLog 提交流程：Pass 1 的 `CONTEXT_COMPACTED` 是否在 Pass 2 启动前 durable 提交，还是全部 pass 完成后再提交一个合并的 `CONTEXT_COMPACTED`。
- **反例/失败场景**: 若 Pass 1 提交了 `CONTEXT_COMPACTED` 然后 Pass 2 失败，Pass 1 的 compact 产物已持久化但 Pass 2 的整个 reactive compact operation 最终进入 `CONTEXT_COMPACTION_FAILED`——此时 Pass 1 的部分产物（episode summary、evidence-backed facts）已进入 EventLog 并被 memory projection 消费，但整个 operation 宣告失败。状态不一致。
- **为什么有问题**: 跨 pass durable 提交策略有两种选择（逐 pass 提交 vs. operation-level 原子提交），各有取舍，但设计真源未裁决。若留给实施 Agent 自行选择，可能导致 compaction operation 的 durable 语义不一致。
- **直接证据**: §25.1 定义 `CONTEXT_COMPACTED` payload 记录 "operation id"——暗示一个 operation 可能只有一个 `CONTEXT_COMPACTED`。但 multi-pass reactive compact 可能产生多个中间 compact 产物。
- **影响**: 实施 Agent 选错策略 → 部分提交通道下 compaction 状态不可回滚、memory projection 可能消费未完成的 compact 产物。
- **建议改法和验证点**:
  1. 在 §25 reactive compact 定义中增加一句裁决：reactive multi-pass compact 中，中间 pass 的 compact 产物作为 operation-level transient artifact 暂存，不提交独立的 `CONTEXT_COMPACTED`；所有 pass 完成后，Host 提交一个合并的 `CONTEXT_COMPACTED`（或所有 pass 均失败后提交 `CONTEXT_COMPACTION_FAILED`）。若中间 pass 失败且 policy 允许 repair，Host 可重试该 pass；若超过 repair budget，整个 operation fail closed。
  2. 验证点：integration test 覆盖 multi-pass reactive compact 中 pass 1 成功、pass 2 失败的场景，验证 EventLog 中没有孤立的 `CONTEXT_COMPACTED` 且 memory projection 不受中间产物影响。
- **修复风险**: 低。裁决本身是设计层面的选择，不改变已定义的数据结构。
- **严重程度**: 低

### F4-BLOCKED-[低]-`history_input` 中 episode summaries 的纳入标准模糊

- **位置**: `docs/host/design.md` §25 material pack history_input 定义
- **问题类型**: 契约缺失
- **当前写法**: §25 line 2741 写 "history_input：compact segment 内的 recent raw turns、older raw turns、episode summaries 与 assistant terminal continuity"。其中 "compact segment 内的 episode summaries" 的语义不够精确——episode summary 是之前 compact 的产物，不天然属于某个 "segment"。
- **反例/失败场景**: 非 fresh session 已有 5 个 episode summaries（来自前 5 次 compact）。第 6 次 proactive compact 触发时，"compact segment 内的 episode summaries" 指什么？全部 5 个？最近 K 个？还是只有与本次 compact segment 中的原始 turns 对应的 summaries？若全部放入，compactor prompt 可能因 summaries 累积而持续膨胀，违背 bounded rendering 原则。
- **为什么有问题**: §24 已裁决 episode summaries 需要 bounded rendering（"较旧 summaries 应 roll up 或只保留 artifact / EventLog refs"），但 §25 material pack 定义中的 "compact segment 内的 episode summaries" 表述与 bounded rendering 原则的衔接不够明确。
- **直接证据**:
  - §24 line 2590: "episode summaries 进入 history pool 后仍需 bounded rendering；较旧 summaries 应 roll up 或只保留 artifact / EventLog refs"
  - §25 line 2741: "history_input：compact segment 内的 ... episode summaries"
- **影响**: 实施 Agent 若按字面理解 "compact segment 内的" 而非应用 bounded rendering，长期运行的 session 中 episode summaries 累积会导致 compactor prompt 膨胀。
- **建议改法和验证点**:
  1. 在 §25 history_input 定义中将 "compact segment 内的 episode summaries" 改为 "compact segment 内新产生的 episode summaries，以及 policy 允许的 bounded recent episode summaries；超出 policy 上限或与 compact segment 无关的较旧 summaries 只保留 artifact refs"，与 §24 的 bounded rendering 原则对齐。
  2. 验证点：memory projection test 证明 bounded rendering 在 compactor input 侧生效，不依赖 RunInputBuilder 单方面裁剪。
- **修复风险**: 低。文字收敛，不改变整体设计。
- **严重程度**: 低

## Open Questions

| # | Question | Recommended Owner |
|---|---------|------------------|
| OQ1 | compact segment 中的 "current_input_anchor" 如何生成摘要/digest？是否需要一次额外的轻量 LLM 调用，还是可以纯规则化截断？ | Planning agent / Slice 2 |
| OQ2 | 单个 evidence block 超过 compactor budget 时的 evidence-block 内部分段机制具体如何实现？是否需要引入 "evidence chunk" 子结构？ | Planning agent / Slice 3（可标记为 edge case，不阻塞 happy path 实现） |
| OQ3 | `pinned_state` materialization 的具体策略：来自 `USER_INPUT_ACCEPTED` 的初始化、来自 compact `pinned_state_patch_candidate` 的修正、来自显式用户确认的覆盖——三者的优先级和合并策略？ | Planning agent / Slice 4 |
| OQ4 | `evidence_backed_facts` 的 working set 选择策略（按 current goal 相关性）的具体算法？纯 keyword 匹配、LLM relevance scoring、还是先按 recency + 简单策略？ | Planning agent / Slice 4 |

## Residual Risks

| # | Risk | Severity | Suggested Tracking |
|---|------|---------|-------------------|
| R1 | P12.5 的现有代码（`compaction_evidence.py`、`compaction.py`、`run_input.py`）与 P12.6 设计有结构性差异；Slice 1 "Design Truth Rewrite And Contract Pruning" 的重写范围可能比预期大，需要仔细判断哪些代码可复用、哪些必须删除。 | 中 | Phase 12.6 Slice 1 plan 必须包含现有代码审计与复用/删除判定。 |
| R2 | Material pack builder 的 token 估算与 budget enforcement 可能引入新的准确性问题——如果打包后的 material pack 仍偶尔超过 compactor hard budget，reactive path 是否足够鲁棒地兜底。 | 低 | P12.6 smoke/integration test 覆盖 proactive compact 不超窗 + reactive fail-closed。 |
| R3 | `evidence_id` 到 prompt-local label 的映射机制在跨 pass reactive compact 中需要重新分配 labels；label 重新分配逻辑若实现错误，可能导致 fact candidate 引用不存在的 evidence。 | 低 | Slice 5 integration test 覆盖 multi-pass reactive compact 的 label 一致性。 |

## Conclusion

**PASS** — the design refinement in `docs/host/design.md` §24 and §25 satisfies Phase 12.6 goals, removes the compact I/O root cause, preserves Host governance boundaries, and avoids overdesign/public API drift/Engine/Fins leakage. The design is specific enough to support handoff to an implementation-ready plan, provided the four findings (F1-F4) are acknowledged by the controller and addressed during planning or design fix.

Findings F1 and F2 are medium severity and should be resolved before plan gate handoff. Findings F3 and F4 are low severity and can be deferred to the planning phase.

All four findings require only text-level design clarification, not structural redesign. Fix risk is low for all.
