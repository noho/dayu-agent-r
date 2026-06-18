# WU-CM-12 Design Writeback Review

## Scope

- Mode: current changes
- Branch: `wu-cm-12-conversation-memory-drift`
- Base: `main`
- Output file: `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`
- Reviewed files: `docs/host/design.md`（diff 相对 main）、`docs/reviews/wu-cm-12-design-writeback-codex-20260618.md`（Codex 自检报告）
- Source of truth: `docs/host/conversation-memory-material-budget-discussion.md`（已接受设计裁决）
- Parallel review coverage: 无

## Review Target

判断 AgentCodex 是否正确把 `docs/host/conversation-memory-material-budget-discussion.md` 中已接受语义写回 `docs/host/design.md`，使后续能只基于 `docs/host/design.md` 写 code-generation-ready plan。

## Findings

未发现实质性问题。

以下逐项验证八个审查重点，全部通过。

---

### 审查点 1：expanded assemble(...) 是否完整写入

**讨论稿原义**（line 33-39）：

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

**design.md 写入**（line 2786-2793、line 3103-3110）：完整写入五个参数，与讨论稿一致。同时在 before_compact 路径（line 2828-2835）也正确展开为 `assemble(empty_latest_accepted_compacted_view, session_start_delta_material, ...)`。

**结论**：✅ 通过。

---

### 审查点 2：latest_accepted_compacted_view 到五类 Session Semantic Memory 的映射

**讨论稿原义**（line 44-51）：

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

**design.md 写入**（line 2798-2805）：逐字段完整写入。同时在 Snapshot Typed Schema 段（line 3047）补充了 `latest_compaction_event_ref` 只是 provenance ref、不是 `latest_accepted_compacted_view` 本体的边界说明；以及 `TraceMemoryView.selected_recent_window` / `EvidenceFactMemoryView.recent_evidence_items` 只是 recent delta view 的澄清。

**结论**：✅ 通过。

---

### 审查点 3：post_compact_delta_material / current_input_anchor / selected_recent_window_policy / protected_recent_floor_policy 自洽性

**post_compact_delta_material**（line 2807）：正确定义为"最近一次 accepted compact 之后新产生、尚未被 compact 覆盖的 committed canonical material"。包含项（历史 `USER_INPUT_ACCEPTED.display_text`、历史 `RUN_SUCCEEDED.final_answer`、readable accepted tool evidence、用户可见 Run outcome material）与排除项（attempt id、execution id、cursor、compact failure、fallback tier、projection diagnostic、payload ref、digest、event id、Host 内部治理状态）均与讨论稿 line 207-235 一致。

**current_input_anchor**（line 2809-2811）：正确写入"单独传入 `assemble(...)`，不得被当作历史 material source"。reactive / recovery / continuation 中已 committed 且 accepted 的 current-run tool result 可参与 assembly 的规则也与讨论稿 line 232 一致。

**selected_recent_window_policy**（line 2813）：正确写入"只从 `post_compact_delta_material` 中确定性选择 bounded recent context view，不从 `latest_accepted_compacted_view` 中重新选择 raw recent window"。material block 必须带 `turn_group_id`、role / material kind、source refs 与稳定 block id 的要求也完整。

**protected_recent_floor_policy**（line 2813）：正确写入 `turn_group_id = host_run_id`，即一个 turn group 等于一个 Host admitted user Run。floor 与 cap 冲突时 floor 优先、超过 hard threshold 进入 tier 5 的规则也与讨论稿 line 263 一致。

**结论**：✅ 通过。四个参数自洽，互相之间的边界（current input 不进历史、selected window 只从 delta 选、floor 以 turn group 为单位）清晰无矛盾。

---

### 审查点 4：tier 0-5 fallback 状态机

**状态机定义**（line 3196-3258）：完整写入 tier 0 normal、tier 1 tighter recent window、tier 2 section-aware degrade、tier 3 delta-only、tier 4 floor-only、tier 5 current-input-only。每个 tier 的 `assemble(...)` 输入、output 类型（compact input / fallback RunInput）和是否送 LLM compactor 均与讨论稿 line 530-593 一致。

**tier 1-3 与 tier 4-5 的 LLM compactor / CONTEXT_COMPACTED / compact artifact / memory snapshot / 五类 memory 输出边界**（line 3261）：

> tier 1-3 的 accepted output 可以提交 `CONTEXT_COMPACTED`，随后由 Conversation Memory projection 生成五类 Session Semantic Memory。tier 4-5 不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact，不 materialize memory snapshot，不生成 Session Summary、Answer Anchor、Forward Intent、reference continuity item 或 `evidence_backed_fact`。

与讨论稿 line 448-458、643-653 完全一致。

**Producer mapping 表**（line 3077-3081）：compact failure fallback 列正确区分 tier 1-3 accepted output 可生成各类 memory、tier 4-5 只渲染 fallback input 不生成 memory。

**Section-aware degrade 保留优先级**（line 3263）：`evidence_backed_facts` > `reference_continuity_items` > `anchors` > `intents` > `summary_text`，与讨论稿 line 601-606 一致。

**结论**：✅ 通过。

---

### 审查点 5：no silent truncation / preview / summary 化约束

**design.md 写入**（line 2866）：

> LLM-facing memory / compact / RunInput material 不允许字段级 silent truncation、preview 化或 summary 化。任何给模型阅读的 `display_text`、`text`、`claim_text`、`answer_text`、`response_text`、`summary_text` 或等价业务字段，要么是完整选中 material / item / section 的可读内容，要么带明确 provenance 做 chunking，要么整体 keep / drop，要么 fail closed。

该约束明确限定于"给模型阅读的"字段，没有过度扩大到 UI / log / diagnostic 展示。讨论稿 line 896 允许的"diagnostic / UI / log preview、parser safety guard 或 evidence block chunking"例外未被此约束覆盖，属于设计层正确分界。

**结论**：✅ 通过。

---

### 审查点 6：memory_projection_policy owner 边界

**design.md 写入**（line 2817）：

> `memory_projection_policy` 是 Host 内部 LLM-facing memory / material 产量的唯一 policy owner，至少覆盖 `selected_recent_window_policy`、`fallback_selected_recent_window_policy`、`protected_recent_floor_policy`、`semantic_memory_section_caps`、`projection_repair_policy` / parser safety guard policy。JSON 配置是否保持 flat 属于实现形态，不是本设计真源要固定的要求；但 Host 内部不得用 DTO 私有 cap、renderer 私有截断值或零散常量作为另一套 LLM-facing material 产量真源。

该段正确表达了 policy owner 边界，没有把 JSON 结构或实现 slice 细节写进设计真源。"JSON 配置是否保持 flat 属于实现形态"的裁决也与讨论稿 line 1160 一致。

**结论**：✅ 通过。

---

### 审查点 7：是否错误新增 Host / Engine public API、durable schema、EventLog canonical semantics 或跨层 contract

本次改动范围：

1. 第 23 章 runner-call manifest：`context_fallback_decision_ref` description 措辞从 "recent-window fallback decision" 改为 "tiered dispatch fallback decision"、`post_compaction_dispatch` description 措辞更新。`RunnerCallKind` 和 `RunnerCallTriggerReason` 枚举值未变。
2. 第 24 章 Conversation Memory 设计：语义细化和 fallback 状态机写入。
3. section routing 表（line 2596）："recent-window fallback" → "fallback bounded material"。仅措辞对齐。

以上全部是设计文档内部的语义对齐，未新增任何 public API、durable schema、EventLog canonical semantics 或跨层 contract。

**结论**：✅ 通过。

---

### 审查点 8：是否引入过度设计、实现 handoff notes、测试命令、current code owner 或 plan slice

- 讨论稿中的 "Implementation Handoff Notes"（含 current code owner、allowed files、current gap 列）未写入 design.md。✅
- 讨论稿中的 "Plan Slice Reference"（含 work slices、测试命令）未写入 design.md。✅
- 讨论稿中的 "Implementation Plan Reference"（含 allowed owner、success signal）未写入 design.md。✅
- 讨论稿中的概念到 schema mapping 表（含 internal schema / typed DTO、producer、selector、renderer、current code owner 列）未写入 design.md。✅
- 旧术语 "deterministic recent-window fallback" 已全部替换为 tiered fallback 术语。✅

**结论**：✅ 通过。

---

## Codex Self-Report Review

`docs/reviews/wu-cm-12-design-writeback-codex-20260618.md` 的写回内容清单、未写入内容说明和验证命令与本次独立 review 结论一致。Codex 自检报告中列出的 residual risks（尚未验证实现是否符合更新后的设计真源、DTO / renderer / selector 仍需逐项核对）是合理的事后注意点，不影响设计真源写回的正确性。

## Open Questions

无。

## Residual Risk

- 本次只验证了设计真源写回的语义正确性，未验证现有实现是否已符合更新后的设计。后续 code-generation-ready plan 需逐项核对 `dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py`、`dayu/host/run_input.py` 中的 DTO 私有 cap、selector 同源性、fallback tier 实现和 material block id 空间一致性。
- 第 23 章 runner-call manifest 中 `context_fallback_decision_ref` description 改为 "tier 4/5 fallback"，但未显式说明为何 tier 1-3 不需要此 ref（因为 tier 1-3 结果已通过 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 记录）。后续 plan 实现时如对 ref scope 有歧义，应回溯到此 review 说明。
- 讨论稿中提到的 `TraceReadableItemVNext.text <= 1200`、`CurrentInputAnchorVNext.text <= 1200`、compactor output schema cap 双真源等实现偏差，在 design.md 中通过 no-silent-truncation 约束和 policy owner 声明覆盖了设计层语义，但具体删除哪些 DTO 常量属于 implementation scope。
