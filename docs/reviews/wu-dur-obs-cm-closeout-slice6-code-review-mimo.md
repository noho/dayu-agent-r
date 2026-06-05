# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice6-code-review-mimo.md`
- Included scope:
  - `dayu/config/prompts/scenes/conversation_compaction.md`
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - `tests/host/test_public_compact_smoke.py`
  - `dayu/config/README.md`
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md`
- Excluded scope: production code (parser, schema, Host behavior) — not modified by this slice
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 验证摘要

**1. 内部实现术语清理** — PASS

prompt 文件不再包含以下任何术语：`Host-owned context compaction`、`ConversationCompactOutputVNext`、`ConversationCompactInputVNext`、`vNext`、`migration`、`candidate_id`、`episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence`、`stable_input`、`history_input`、`evidence_input`、`EventLog`、`payload ref`、`payload refs`、`payload_refs`、`digest`、`cursor`、`policy`。

直接证据：`rg` 搜索 0 匹配；`python` 脚本逐词验证 0 匹配。

**2. Prompt 自足性** — PASS

user prompt 自足说明：
- 输入 JSON 顶层字段（`schema_version`、`previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`）及其类型、必填性、业务含义。
- 嵌套字段（`previous_compacted_view.session_summary`、`evidence_backed_facts[*].source_label` 等）。
- 输出 JSON 字段（`schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`）及其类型、必填性、允许值。
- 最小 JSON 示例。
- label 引用规则。

直接证据：`conversation_compaction_user.md` 第 7–107 行。

**3. Label 语义边界** — PASS

- system prompt（第 10 行）："输入中的 label 只是本次请求内的引用标签，用来说明输出内容来自哪段输入；label 本身不是业务事实、财报事实或结论。"
- user prompt（第 22–26 行）：label 规则明确说明"label 只说明'输出内容来自哪段输入'，不是业务事实、财报事实、用户意图或结论"，并禁止引用 `current_input_anchor.anchor_label`。

直接证据：`conversation_compaction.md` 第 10 行；`conversation_compaction_user.md` 第 23–24 行。

**4. 输出 schema 字段名保留** — PASS

prompt 指定的输出字段名与生产 parser `parse_conversation_compact_output_vnext`（`llm_compaction.py:563–570`）期望的字段名完全一致：
- `schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`。

**5. 允许值与生产枚举一致** — PASS

| 字段 | prompt 允许值 | 生产枚举 | 一致 |
|---|---|---|---|
| `evidence_kind` | `tool_result`、`tool_source_text`、`accepted_evidence_material` | `FactEvidenceKindVNext`（`compaction.py:123–125`） | ✓ |
| `intent_type` | `next_step_note`、`open_question`、`pending_clarification`、`pending_user_visible_task` | `ForwardIntentTypeVNext`（`compaction.py:131–134`） | ✓ |
| `status` | `open`、`blocked`、`superseded` | `ForwardIntentStatusVNext`（`compaction.py:140–142`） | ✓ |
| `reason` | `local_reference`、`ordinal_reference`、`ellipsis_recovery`、`recent_state` | `ReferenceContinuityReasonVNext`（`compaction.py:148–151`） | ✓ |
| `trace_kind` | `user_input`、`assistant_final_answer`、`user_visible_run_state` | `TraceReadableKindVNext`（`compaction.py:95–97`） | ✓ |
| `schema_version` | `conversation_compact_output_v1` | 生产 parser 校验 | ✓ |

**6. 不暴露治理内部** — PASS

prompt 不包含 EventLog、payload ref、digest、cursor、policy、Python 类型名或 Host 内部治理标识。

直接证据：forbidden terms 搜索 0 匹配。

**7. 测试使用真实装配路径** — PASS

`test_default_compactor_prompt_is_llm_facing_and_self_contained`（第 119–148 行）通过 `_compactor_baseline_inputs()` 装配真实 `ConfigLoader` → `ScenePrepare` → compactor system prompt + user prompt template，不使用 test-only production bridge。

直接证据：`test_public_compact_smoke.py:933–962` 的 `_compactor_baseline_inputs` 实现。

**8. README 同步** — PASS

- `dayu/config/README.md` 第 188–190 行：补充会话压缩 prompt asset 的 LLM-facing 稳定边界说明，在 `conversation_compaction` scene 描述职责范围内。
- `tests/README.md`：补充 `test_public_compact_smoke.py` 覆盖默认 compactor prompt 不暴露内部实现术语且自足说明输入输出，在测试手册职责范围内。

**9. Control doc bookkeeping** — PASS

- gate 更新为 `review`。
- implementation status 更新为 `WU-CM-01-F02 Slice 6 implementation-ready-for-code-review`。
- next entry point 更新为 `AgentMiMo and AgentDS review Slice 6 compactor prompt semantic rewrite implementation`。
- 新增 slice 6 implementation artifact 记录。
- current inspection note 更新为 Slice 6 完成状态。

## Open Questions

无。

## Residual Risk

1. **`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 包含通用英文词**（低风险）：测试的 forbidden terms 列表包含 `digest`、`cursor`、`policy` 等通用英文词。当前 prompt 不使用这些词，测试通过。若未来 prompt 需要在业务语境中使用这些词（如"evidence digest"），测试会误报。这是 intentional design choice — 守卫内部术语泄漏 — 但需注意维护成本。

2. **User prompt 长度增加**（低风险）：user prompt 从约 60 行增加到约 107 行，增加了 compactor input token 数。这是 self-containment 的合理 trade-off，且 prompt 仍远低于 context window 限制。

3. **后续 slice 依赖**：Slice 7（public smoke closeout）将验证 compactor prompt 装配路径的端到端行为。本 slice 只验证 prompt 文本内容，不验证运行时装配的完整链路。
