# WU-CM-01-F02 Slice 6 Implementation Artifact

## Gate

- Gate：implementation
- Work unit：WU-CM-01-F02
- Slice：Slice 6 compactor prompt semantic rewrite
- Branch：`phaseflow/wu-dur-obs-cm-closeout`
- Artifact path：`docs/reviews/wu-dur-obs-cm-closeout-slice6-implementation-codex.md`

## 第一性原理判断

本 slice 动机成立。compactor LLM 是无状态、上下文有限、偏模式匹配的推理器；投给它的 prompt 应只描述当前任务、输入、输出、引用规则和禁止事项。现有 prompt 直接暴露 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`vNext 字段` 与旧 candidate 字段名，这些词不能帮助模型完成压缩任务，反而要求模型理解内部实现身份、Python 类型名和迁移历史。

直接证据：

- `dayu/config/prompts/scenes/conversation_compaction.md` 原 system prompt 自称 `Host-owned context compaction`，并要求符合 `ConversationCompactOutputVNext`。
- `dayu/config/prompts/scenes/conversation_compaction_user.md` 原 user prompt 使用 `vNext 字段`，并列出 `candidate_id`、`episode_summary_candidate` 等旧字段清理措辞。
- `docs/host/design.md` 第 25 章要求 compactor input 是业务可读投影，不应把 EventLog、payload refs、digest、cursor、policy 等内部治理信息作为模型阅读主体。
- `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 6 明确要求只做 LLM-facing prompt semantic cleanup，保持 compact output schema 字段名不变。

判断结果：问题真实存在，严重性适中但属于 LLM-facing 稳定性风险；根因在 prompt asset 本身，不在 smoke、fixture 或 parser。无需改 compact output schema、parser 或 Host production behavior。

## 变更文件

- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_public_compact_smoke.py`
- `dayu/config/README.md`
- `tests/README.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice6-implementation-codex.md`

## Prompt 语义变更

- system prompt 从“内部组件身份”改为“把较长会话材料整理为后续对话可继续使用的简短记忆”。
- 删除面向实现者的 `ConversationCompactOutputVNext`、`vNext`、旧 candidate 字段和迁移措辞。
- 将 prompt-local label 规则改写为“本次请求内的引用标签”，并明确 label 不是业务事实、财报事实或结论。
- 明确 `current_input_anchor` 只帮助理解当前输入，不得被任何输出 label 列表引用。
- user prompt 自足说明输入 JSON 顶层字段、嵌套字段、类型、必填性、允许值和各 section 的业务含义。
- user prompt 保留现有输出 schema 字段名：`schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`。
- 明确 `session_summary` 是必填字段，但可为 object 或 null，匹配现有 parser 行为。
- 保留最小 JSON 示例，未增加任何新生产 schema 字段。

## 测试与验证

- `rg -n "Host-owned context compaction|ConversationCompactOutputVNext|ConversationCompactInputVNext|vNext|migration|candidate_id|episode_summary_candidate|pinned_state_patch_candidate|minimum_preserve_item_candidates|preservation_evidence|stable_input|history_input|evidence_input|EventLog|payload ref|payload refs|payload_refs|digest|cursor|policy" dayu/config/prompts/scenes/conversation_compaction.md dayu/config/prompts/scenes/conversation_compaction_user.md`
  - 结果：无匹配。
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - 结果：`6 passed, 1 skipped in 0.77s`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

新增 focused assertion：

- `test_default_compactor_prompt_is_llm_facing_and_self_contained` 通过默认 `CompactorRunnerBaseline` 装配真实 compactor system/user prompt。
- 断言 prompt 不包含本 slice stop condition 中的内部实现身份、Python 类型名、vNext / migration wording、旧 candidate 字段、EventLog / payload ref / digest / cursor / policy 等治理标识。
- 断言 prompt 包含输入 JSON 说明、输出 JSON 字段、最小示例、label 语义和输出 schema 必填字段。

## README 同步决策

- `dayu/config/README.md` 已更新：补充会话压缩 prompt asset 的 LLM-facing 稳定边界，说明 prompt 必须自足描述输入输出与 label 规则，且不得要求模型理解内部治理、Python 类型名、迁移术语或底层账本标识。
- `tests/README.md` 已更新：补充 `test_public_compact_smoke.py` 覆盖默认 compactor prompt 不暴露内部实现术语且自足说明输入输出。

## 非目标与边界

- 未改 compact output schema 字段名。
- 未改 compactor parser、accept barrier、Context Governance、Host durable event、memory projection 或 RunInputBuilder 行为。
- 未改 real compactor smoke gating；`DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 仍为可选。
- 未扩大到 Slice 7 的四个 utility smoke script 审计。

## 剩余风险

- fixed in current slice：默认 compactor prompt asset 的内部实现 / 迁移术语暴露风险已由 prompt rewrite 和 focused assertion 覆盖。
- covered by later approved slice：四个 Host public smoke 入口的逐一装配路径审计属于 Slice 7，不在本 slice 扩范围。
- assigned to later work unit：真实模型在复杂材料上是否稳定产出最高质量 compact 内容仍属于完整 eval / benchmark 工作，不由本 prompt 文本清理闭环。

## Completion Status

Slice 6 implementation complete。当前实现满足 stop condition：真实默认 compactor prompt dump 不再包含计划列出的内部实现身份、Python 类型名或 vNext / migration 术语；schema/parser 和 Host production behavior 未变更。
