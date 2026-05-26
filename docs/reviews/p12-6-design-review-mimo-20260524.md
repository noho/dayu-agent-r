# P12.6 Conversation Memory Design Review

## Reviewed Target

- **Scope**: Phase 12.6 Conversation Memory Redesign design refinement, as recorded in `docs/host/design.md` §24 and §25.
- **Controller artifact**: `docs/reviews/p12-6-design-refinement-controller-20260524.md`.
- **Discussion input** (not design truth): `docs/host/conversation-memory-compact-io-first-principles-discussion.md`.
- **Gate**: Design refinement review. Not implementation review.

## Review Posture

Constructively adversarial. Default assumption: the design refinement has at least one material gap until evidence proves otherwise.

## Assumptions Tested

1. The material pack concept removes the root cause of compactor I/O boundary violation (current input duplication, EventLog range dump, Host provenance key as LLM input).
2. The prompt-local evidence label to canonical provenance mapping preserves Host governance boundaries.
3. The proactive/reactive compaction split with bounded multi-pass is architecturally sound.
4. The long-session retention/consolidation strategy prevents structured memory bloat.
5. The design is specific enough to enter plan gate without forcing the planning agent to redesign architecture.
6. No overdesign, reverse dependency, public API drift, Engine change, Fins/tool-provider leakage or extra payload escape hatch is introduced.

## Findings

### 01-unfixed-medium-CompactionRequest-to-material-pack-schema-mapping-not-explicit

- **位置**: `docs/host/design.md` §25, material pack 边界段落；`dayu/host/compaction.py` `CompactionRequest` dataclass
- **问题类型**: 契约缺失
- **当前写法**: 设计描述了 material pack 的四个 section（`stable_input`、`history_input`、`evidence_input`、`current_input_anchor`），但没有显式说明如何从现有 `CompactionRequest` 的平铺字段映射到这四个 section。当前 `CompactionRequest` 使用 `compact_raw_context_items`（含 user input、assistant conclusion、accepted tool result）、`accepted_evidence_envelopes`、`current_message_summary`、`evidence_backed_fact_refs`、`recent_raw_turn_refs`、`older_raw_turn_refs`、`existing_episode_summary_refs` 等平铺字段。
- **反例/失败场景**: implementation agent 在构造 material pack builder 时，可能把 `compact_raw_context_items` 中的 `ACCEPTED_TOOL_RESULT` 项同时作为 `history_input` 和 `evidence_input` 渲染，导致去重失败；或者把 `current_message_summary.summary_text` 作为 `current_input_anchor` 渲染后又把同一 `USER_INPUT_ACCEPTED` event 的 raw context item 作为 `history_input` 渲染，重现当前 duplication bug。
- **为什么有问题**: 设计的核心安全条件是 "compact material pack 不得重复渲染同一 current input、raw turn 或 raw tool result"。若 schema 映射不明确，implementation agent 必须自行推断哪些 items 属于哪个 section，推断错误会直接违反该安全条件。
- **直接证据**: `CompactionRequest` 有 `compact_raw_context_items`（`CompactRawContextKind` 含 `USER_INPUT`、`ASSISTANT_CONCLUSION`、`ACCEPTED_TOOL_RESULT`），但 material pack 将 user input 归入 `current_input_anchor` 或 `history_input`，将 tool result 归入 `evidence_input` 或 `history_input`。当前设计未说明分类规则。
- **影响**: implementation agent 可能生成重复内容的 material pack，导致 compactor provider 超窗，重现 P12.5 smoke 失败。
- **建议改法和验证点**: 在 design doc 或 plan 中显式补充 material pack section 到 `CompactionRequest` 字段的映射表。例如：`current_input_anchor` ← `current_message_summary`（bounded）；`history_input.recent_raw_turns` ← `compact_raw_context_items` 中 `recent_raw_turn_refs` 对应的 items（不含 `ACCEPTED_TOOL_RESULT`）；`evidence_input` ← `compact_raw_context_items` 中 `ACCEPTED_TOOL_RESULT` items + `accepted_evidence_envelopes` 的可读 query/result；`stable_input` ← memory snapshot 的 bounded stable layer view。验证点：material pack builder unit test 断言同一 event ref 不出现在两个 section 中。
- **修复风险**: 低
- **严重程度**: 中

### 02-unfixed-medium-long-session-consolidation-trigger-mechanism-under-specified

- **位置**: `docs/host/design.md` §24, "long-session retention / consolidation 是 Conversation Memory 的基本语义" 段落
- **问题类型**: 过度设计 / 契约缺失
- **当前写法**: 设计明确了 consolidation 语义（pinned state materialized current state、assumptions merge/resolve/expire、episode summaries roll up、evidence-backed facts bounded working set、minimum preserve items 短寿命），但未指定 consolidation 触发机制。讨论稿中提到了 `memory_retention_candidate` JSON 输出结构（含 `keep_fact_refs`、`demote_fact_refs`、`merge_assumption_refs`、`resolve_open_question_refs`、`rollup_episode_summary_refs`），但设计真源（§24/§25）未将此纳入 compactor output schema。
- **反例/失败场景**: V1 implementation 只做 extraction + append，不做 consolidation。多次 compact 后 `evidence_backed_facts`、`working_assumptions`、`episode summaries` 无界增长，最终仍超出上下文窗口。设计明确说 "compact 不能只是把 raw turns 变成 structured append log"，但没有给 implementation agent 一条具体的 consolidation 路径。
- **为什么有问题**: 设计将 consolidation 定义为基本语义而非后续优化，但 V1 实现路径和触发条件不明确。implementation agent 可能选择 "先 append-only，后续加 consolidation"，但设计的意图是 consolidation 从一开始就是 memory 语义的一部分。
- **直接证据**: 讨论稿 §"输出需要表达 Retention / Consolidation" 给出了 `memory_retention_candidate` JSON 结构，但设计真源 §25 compactor output schema（`CONTEXT_COMPACTED` payload）未包含此字段。设计说 "第一版实现可以先用 policy 在 projection / RunInputBuilder 侧做 bounded selection"，但 "first version" 与 "基本语义" 之间存在张力。
- **影响**: V1 可能成为 append-only 实现，后续需要重写 memory projection 来加 consolidation，造成返工。
- **建议改法和验证点**: 在 design doc 中明确：(a) V1 consolidation 由 memory projection policy 在消费 `CONTEXT_COMPACTED` 时执行 bounded selection（top-K / size cap），而不是由 compactor 输出 retention intent；(b) compactor output 的 `memory_retention_candidate` 作为后续增强，不阻塞 V1；(c) V1 的 success signal 必须包含 "多次 compact 后 memory bounded" 的 integration test，验证 bounded selection 确实生效。验证点：多次 compact integration test 断言 `evidence_backed_facts` 和 `episode_summaries` 数量/大小受 policy 限制。
- **修复风险**: 低
- **严重程度**: 中

### 03-unfixed-low-reactive-multi-pass-termination-and-budget-allocation

- **位置**: `docs/host/design.md` §25, "reactive compact" 段落
- **问题类型**: 状态机漏洞
- **当前写法**: 设计说 "按 compact material block 分段多 pass 压缩"、"超过 `max_reactive_compactions_per_run` 后 fail closed"，但未指定每次 pass 的 budget 分配策略。当前 `max_reactive_compactions_per_run` 默认为 2，但 material block 分段可能需要 3+ pass。
- **反例/失败场景**: 一个包含 5 个 episode summary、10 个 evidence block、20 轮 raw turns 的长会话，material pack 总量远超 compactor budget。分段策略需要 4 次 pass 才能完成，但 `max_reactive_compactions_per_run=2`，导致 compact 不完整。后续 recovery dispatch 仍 overflow，Run 进入 FAILED。
- **为什么有问题**: `max_reactive_compactions_per_run` 控制的是 "每次 Engine overflow 触发的 compaction operation 数量"，不是 "单个 operation 内的 pass 数量"。设计提到 "一个 operation 内可以包含 Host-owned bounded semantic repair attempts"，但未明确 material block 分段是否属于同一 operation 内的多次 pass 还是需要多个 operation。
- **直接证据**: 设计 §25: "每个 Run 的 proactive trigger 第一版最多启动一个 compaction operation；reactive trigger 每次 Engine overflow 最多启动一个 operation，但同一 Run 可在 `max_reactive_compactions_per_run` 上限内多次 reactive compact"。分段 multi-pass 与 operation 的关系未明确。
- **影响**: implementation agent 可能把分段 multi-pass 实现为多个 operation，导致 `max_reactive_compactions_per_run` 提前耗尽；或实现为单个 operation 内的多次 pass，但超出 `max_compaction_attempts_per_operation` 的语义范围。
- **建议改法和验证点**: 明确分段 multi-pass 属于单个 compaction operation 内的 "material block batch processing"，不消耗 `max_reactive_compactions_per_run`；`max_compaction_attempts_per_operation` 控制的是同一 material block 的 proposal + repair attempts，不是跨 block 的 pass 次数。需要额外引入 `max_material_block_passes_per_operation` 或明确复用现有 budget。验证点：reactive multi-pass unit test 断言分段 compact 在单个 operation 内完成，不触发额外 `CONTEXT_COMPACTION_REQUESTED`。
- **修复风险**: 低
- **严重程度**: 低

### 04-unfixed-low-memory-projection-rebuild-during-compaction-not-specified

- **位置**: `docs/host/design.md` §24, "memory snapshot 缺失或滞后的处理" 段落；§25, compaction operation 段落
- **问题类型**: 状态机漏洞
- **当前写法**: 设计说 "snapshot cursor 滞后但 EventLog delta 在 policy 阈值内时，RunInputBuilder 可以从 EventLog canonical facts 重建所需 stable layer"。但未说明 compaction operation 启动时发现 memory snapshot 缺失或过期时的行为。
- **反例/失败场景**: compaction operation 启动时读取 memory snapshot，发现 snapshot cursor 远落后于 compact input range 的 end_event_sequence。此时 compactor 的 `stable_input` 基于过期 snapshot，可能遗漏已接受的 evidence-backed facts。compact 后生成的 `evidence_backed_fact_candidates` 与已过期 snapshot 中的 facts 重复或矛盾。
- **为什么有问题**: compaction 依赖 memory snapshot 提供 `stable_input`。若 snapshot 过期，compact 的输入不完整，输出质量无法保证。
- **直接证据**: 设计未在 compaction operation 段落提到 snapshot cursor 校验。RunInputBuilder 有 "snapshot cursor 覆盖本次构造 messages 所需的 EventLog cursor" 的要求，但 compaction operation 没有对等要求。
- **影响**: compact 可能基于过期 snapshot 生成重复或矛盾的 facts，需要额外 repair 或导致 memory 不一致。
- **建议改法和验证点**: 在 compaction operation 启动时增加 snapshot cursor 校验：若 snapshot cursor 落后于 compact input range 的 start_event_sequence，先触发 memory projection rebuild，再启动 compact。验证点：compaction operation unit test 断言 snapshot cursor >= compact input range start 时才启动 compact。
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

1. **CompactionRequest 是否需要重构为 material pack 导向的结构？** 当前 `CompactionRequest` 是平铺结构，material pack 是分层结构。plan 阶段需决定：(a) 保持 `CompactionRequest` 平铺，material pack builder 负责分组；(b) 将 `CompactionRequest` 重构为分层结构，与 material pack 对齐。选项 (a) 改动小但 builder 逻辑复杂；选项 (b) 改动大但结构更清晰。

2. **Prompt-local evidence label 的生命周期？** 设计说 "prompt-local evidence labels 可以在每个 pass 内重新分配，但 Host 必须保留 label 到 canonical provenance 的映射"。跨 pass 的 label 映射如何持久化？是在 operation 级别维护一个累计映射表，还是每个 pass 独立？

3. **`evidence_input` 中 raw tool result 的渲染边界？** 设计说 "raw result 或必要 raw transcript"。若单个 tool result 是几万字的年报章节，rendering 时是否截断？截断策略是什么？设计 §24 说 "fact extraction 基于 raw accepted evidence block"，但未指定 evidence block 本身的大小限制。

4. **Memory projection policy 的具体默认值？** 设计 §3 列出了 `MemoryProjectionPolicy` 的字段（`max_pinned_items`、`max_evidence_backed_facts`、`max_working_assumptions` 等），但 consolidation 的 bounded selection 策略（top-K vs relevance-based vs recency-based）未在设计中指定。plan 阶段需决定 V1 使用哪种 selection 策略。

## Residual Risks

| 风险 | 严重程度 | 建议追踪位置 |
|------|---------|-------------|
| Material pack builder 去重实现不正确，重现 duplication bug | 高 | P12.6 plan / Slice 2 |
| V1 consolidation 只做 append-only，未实现 bounded selection | 中 | P12.6 plan / Slice 4 |
| Reactive multi-pass 分段策略实现不正确，导致 compact 不完整或 budget 耗尽 | 中 | P12.6 plan / Slice 5 |
| Long chapter tool result 进入 evidence block 时无截断策略，compactor 超窗 | 中 | P12.6 plan / Slice 2 / Slice 3 |
| Prompt-local label 跨 pass 映射丢失，导致 evidence ref 校验失败 | 低 | P12.6 plan / Slice 3 |
| Memory snapshot 过期时 compaction 基于过期数据生成矛盾 facts | 低 | P12.6 plan / Slice 5 |

## Conclusion

**PASS-WITH-RISKS**

Design refinement 满足 Phase 12.6 核心目标：移除了 EventLog range dump 作为 compaction input 的根因，正确分离了 Host provenance 与 LLM-facing evidence，material pack 概念架构合理，proactive/reactive 分段 compact 方案可执行。设计足够具体，可以进入 plan gate。

五个 material findings 均为中低严重程度，属于 plan 阶段可解决的实现细节，不构成架构性 blocker。主要风险集中在 material pack schema 映射（Finding 01）和 long-session consolidation 触发机制（Finding 02），建议在 plan 阶段优先明确这两个问题。
