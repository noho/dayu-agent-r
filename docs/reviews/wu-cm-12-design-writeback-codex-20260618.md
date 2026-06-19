# WU-CM-12 Design Writeback

## Gate

- gate: pre-plan design truth repair
- work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- design input: `docs/host/conversation-memory-material-budget-discussion.md`
- design truth updated: `docs/host/design.md`

## Scope

本次只把讨论稿中已接受、且可作为稳定设计真源的 Conversation Memory material / assemble / compact / fallback / five semantic memories 语义写回 `docs/host/design.md`。

本次不是 plan gate、implementation gate 或 review gate；未生成 code-generation-ready plan，未修改生产代码、测试、配置或 README，未新增 Host / Engine public API、durable schema、EventLog canonical semantics 或跨层 contract。

## 写回内容

- 将 `rendered_context` 从黑盒 `assemble(memory_material, ...)` 展开为 `assemble(latest_accepted_compacted_view, post_compact_delta_material, current_input_anchor, selected_recent_window_policy, protected_recent_floor_policy)`。
- 明确 `latest_accepted_compacted_view` 映射到五类 Session Semantic Memory：`trace_memory.reference_continuity_items`、`evidence_fact_memory.evidence_backed_facts`、`session_summary_memory.summary_text`、`answer_anchor_memory.anchors`、`forward_intent_memory.intents`。
- 明确 `post_compact_delta_material` 的 committed canonical material 边界，包括历史 `USER_INPUT_ACCEPTED.display_text`、历史 `RUN_SUCCEEDED.final_answer`、readable accepted tool evidence 与 user-visible run outcome material；`current_input_anchor` 单独参与 assembly，不作为历史 material source。
- 明确 `selected_recent_window_policy` 只从 `post_compact_delta_material` 选择完整 material block；`protected_recent_floor_policy` 以 `host_run_id` turn group 保护最近 N 个 Host admitted user Run。
- 明确 selected recent window 不是第六类 Semantic Memory，而是 `post_compact_delta_material` 的 bounded recent context view；`trace_memory.reference_continuity_items` 才是 compact 后 Trace Memory semantic item。
- 明确 compact input、ordinary RunInput 与 fallback RunInput 共享同一套 material selection / rendering 语义，差异只在 renderer、source label、accept barrier 与 tier output。
- 写回 tier 0 normal、tier 1 compact recovery with tighter recent window、tier 2 compact recovery with section-aware compacted view degrade、tier 3 compact recovery delta-only、tier 4 dispatch fallback floor-only、tier 5 dispatch fallback current-input-only 状态机。
- 明确 tier 1-3 送 LLM compactor，accepted output 可以提交 `CONTEXT_COMPACTED` 并投影为五类 Session Semantic Memory；tier 4-5 不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact / memory snapshot / 五类 memory。
- 明确 LLM-facing memory / compact / RunInput material 不允许字段级 silent truncation、preview 化或 summary 化；上下文缩小只能通过 deterministic selection、whole-item 或 whole-section keep-drop、chunking with provenance、section-aware degrade 或 fail closed 表达。
- 明确 `memory_projection_policy` 是 Host 内部 LLM-facing memory / material 产量的唯一 policy owner，覆盖 recent window、fallback recent window、protected floor、semantic section caps、projection repair / parser safety guard policy；不强行裁决 JSON 是否保持 flat。

## 未写入内容及原因

- 未写入 implementation handoff notes、current code owner、allowed files、测试命令或 plan slice 参考：这些属于后续计划 / 实施材料，不属于设计真源。
- 未引入 semantic search、vector recall、prompt-conditioned retrieval、User Profile Memory 或 Conversation Memory eval benchmark：均为本任务非目标。
- 未新增 Host / Engine public API、durable schema、EventLog canonical semantics 或跨层 contract：本次只修复设计真源语义漂移。
- 未修改 `docs/host/issues-implementation-control.md`：用户允许修改文件不包含该控制文档。

## 验证命令

- `git diff --check -- docs/host/design.md`：通过，无输出。
- `git diff --check`：通过，无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-cm-12-design-writeback-codex-20260618.md`：无 whitespace 输出；`--no-index` 因存在文件差异返回非零属于预期。
- `rg -n 'tier 0 normal|tier 1 compact recovery|tier 2 compact recovery|tier 3 compact recovery|tier 4 dispatch fallback|tier 5 dispatch fallback|rendered_context =|assemble\(|silent truncation|host_run_id|selected_recent_window.*第六类|memory_projection_policy.*唯一 policy owner|no LLM compactor|CONTEXT_COMPACTED' docs/host/design.md`：通过，确认核心 tier、expanded assemble、no silent truncation、host_run_id turn group、policy owner 与 compactor / `CONTEXT_COMPACTED` 边界已存在。
- `rg -n 'deterministic recent-window fallback|字段级 silent|preview 化|summary 化|post_compact_delta_material|current_input_anchor|protected_recent_floor_policy|fallback_selected_recent_window_policy' docs/host/design.md`：通过，确认旧 deterministic fallback 表述已收敛，并保留关键 material / anchor / floor / fallback policy 语义。
- `rg -n 'deterministic recent-window fallback' docs/host/design.md`：无输出；命令返回 1 表示旧术语不存在。

## Residual Risks

- 本次只完成 pre-plan design truth repair，尚未验证现有实现是否已经符合更新后的设计真源。
- 第 23 章 runner-call manifest 与 section routing 已做必要术语同步，但后续 code-generation-ready plan 仍需逐项核对实现层 DTO / renderer / selector 是否存在私有 cap 或重复 material 产量真源。
- 文档中仍保留第一版 conservative estimator / provider tokenizer adapter 后续能力边界；这不是本次漂移修复范围。
