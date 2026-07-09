# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Re-Review (AgentMiMo)

## Metadata

- Review type: narrow re-review (controller accepted findings closure check)
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Plan fix: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-review-controller-adjudication.md`
- Initial review artifacts:
  - `docs/reviews/plan-review-20260709-p1-a-mimo.md`
  - `docs/reviews/plan-review-20260709-p1-a-ds.md`
- Review date: 2026-07-09

## Conclusion

**`pass`**

所有 7 个 controller accepted findings（P1A-PLAN-F01 至 P1A-PLAN-F07）均已闭合。Codex fix 正确地在 plan artifact 中落实了 controller 要求的修复，未引入新 blocker。

---

## Accepted Findings Closure Audit

### P1A-PLAN-F01：Tool Trace request summary 替代策略

**状态：已闭合**

Controller 要求：
- 明确选择 Tool Trace 保留 trace-specific bounded rendering helper 还是 projection 暴露完整 summary view
- 偏好窄方案
- 更新 validation grep 可测试性

Plan fix 落实：
- §4 新增："Tool Trace 分界选择窄方案：projection helper 只拥有 query/status/source/result truth；Tool Trace 可以保留 trace 专属的参数有界渲染、脱敏和展示格式 helper，但这些 helper 只能消费 projection 字段与已校验的 display-only 参数视图，不能重新拥有 accepted query/status/source/result 语义，不能直接回读 request atom 来决定 query/status/source。"
- §4 新增 helper 内部 back-query 设计决策："helper 内部负责从 envelope 指向的 `TOOL_CALL_REQUESTED` request atom 读取 query 信息并校验 request/result identity；消费者不得直接调用 request atom back-query。identity mismatch、missing request atom、digest mismatch 和 payload descriptor 缺失不抛给消费者做分支判断，而是归一为 projection 的 typed limited-signal / `diagnostic`。"
- §6 S2 更新："Tool Trace 只保留 display-only 参数有界渲染/脱敏，不再直接回读 request atom 决定 query/status/source，也不保留 `_tool_result_status()` 的 payload fallback chain。"
- §8 checklist 更新，区分 projection truth 与 trace 参数摘要
- §12 propagation audit 补充 Tool Trace 参数摘要仅为 display-only

**验证**：窄方案选择正确，与 controller 偏好一致。helper 内部 back-query 是架构正确的单一收敛点，不违反"消除消费者私有 back-query"的 owner boundary 意图。

---

### P1A-PLAN-F02：Read API PREVIEW vs CANONICAL_FACT event class 边界

**状态：已闭合**

Controller 要求：
- 明确 Read API activity 是否迁移到 canonical projection helper
- 如果迁移，指定 dispatch boundary 和 `AcceptedToolResultStatus` → `HostActivityStatus` 映射
- 如果不迁移，更新 checklist 和 non-goals

Plan fix 落实：
- §4 新增："Read API 分界选择迁移到 canonical `TOOL_RESULT_ACCEPTED` projection helper。`_activity_from_row()` 需要新增 canonical `TOOL_RESULT_ACCEPTED` 的显式分发边界：PREVIEW event class 仍按 preview payload 处理既有 activity，CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 通过 projection helper 产生 activity status / summary，二者不得在同一 row 上互相 fallback。"
- §4 新增完整映射表：`completed -> COMPLETED`；`failed`、`governed_error`、`lost`、`unknown -> FAILED`；`cancelled -> CANCELLED`
- §4 明确 `unknown` fail closed 行为："Read API 必须 fail closed 为 failed activity，而不是隐藏该 accepted result"
- §6 S2 更新 Read API 迁移项
- §8 / §12 补 checklist 和 propagation audit

**验证**：选择迁移方案，PREVIEW path 保留但不冒充 canonical projection。映射表覆盖所有 6 个 `AcceptedToolResultStatus` 值到 3 个 `HostActivityStatus` 值。`unknown` fail closed 策略正确。

---

### P1A-PLAN-F03：`_readable_source_text_from_refs()` source producer 处理

**状态：已闭合**

Controller 要求：
- 明确 `_readable_source_text_from_refs()` 是迁移到 projection helper、被 helper 输出替代、还是仅在 non-accepted-result initial material 边界保留
- 增加 `_readable_source_text_from_refs` 和 `source_note` 到 validation grep

Plan fix 落实：
- §6 S1："统一 source 投影：把 accepted-result source readable 生产逻辑迁移到 projection helper；只输出 business-readable source，internal provenance refs 不进入 `readable_source_text`。`compact_material._readable_source_text_from_refs()` 对 accepted result 的使用必须被 helper 输出替代。"
- §6 S2："CompactMaterial 构造 accepted evidence block 时使用 projection view，不再私有回读 request atom；accepted-result source 不再经 `_readable_source_text_from_refs()` 生产 `source_note`。"
- §6 S2 完成信号增加："`source_note` 生产逻辑"
- §9 validation grep 增加 `_readable_source_text_from_refs`、`source_note`、`tool_call_request_atoms`
- §9 明确允许/禁止："grep 只允许新共享 helper 内部命中 `tool_call_request_atoms`、status/query/source projection 私有函数或 non-accepted initial material 边界命中；消费者禁止命中旧私有 query/status/source helper、accepted-result `source_note` 生产、`_readable_source_text_from_refs` accepted-result 调用和 request atom back-query"

**验证**：fix 正确区分了 accepted-result path（必须迁移/替代）和 non-accepted initial material 边界（允许保留）。validation grep 覆盖了上游 producer 和下游 consumer 两个层面。fix artifact 也明确说明"`_readable_source_text_from_refs()` 可在 non-accepted initial material 边界保留"。

---

### P1A-PLAN-F04：Conversation Memory unavailable-query fallback owner

**状态：已闭合**

Controller 要求：
- 明确 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 常量是移到 projection helper 模块还是从单一 owner 导入
- 明确 Conversation Memory 消费 projection `query_text` / query state，不自行决定 fallback 条件

Plan fix 落实：
- §4 新增："`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 的 owner 迁移到 `accepted_result_projection.py`，作为 query typed limited-signal 的唯一定义；旧模块若仍需要该文案只能从 projection owner 导入。Conversation Memory 只能消费 projection `query_text` / `query_state`，不得根据 `event.evidence_query_text is None` 自行决定 fallback 条件。"
- §6 S2 更新 Conversation Memory 迁移项
- §8 补 Conversation Memory checklist

**验证**：常量 owner 明确为 `accepted_result_projection.py`。Conversation Memory 的消费约束明确：只读 projection view，不自行判断 fallback。这消除了 "durable memory 用 unavailable，compact material 用参数 JSON" 的语义 drift。

---

### P1A-PLAN-F05：`AcceptedToolResultStatus` mapping 与 `_tool_result_status()` 处理

**状态：已闭合**

Controller 要求：
- 增加 concise mapping table 或 S1 requirement 定义 ordinary/wait-resolution status 字段优先级
- 明确 `_tool_result_status()` 是删除、移到 shared helper、还是保留为 formatting adapter

Plan fix 落实：
- §4 新增完整 status 归一规则表，覆盖 6 种 durable signal → 6 种 `AcceptedToolResultStatus` 的映射
- §4 新增 status 字段优先级："先读 canonical accepted status fields（wait-resolution 的 `resolution_kind` 高于 ordinary `tool_fact_kind`），再读 raw outcome 的 kind/result.ok 作为同一 helper 内的降级依据；禁止消费者自行实现这条 fallback chain"
- §4 明确 `_tool_result_status()` 命运："Tool Trace 现有 `_tool_result_status()` 在 S2 中删除，或重构为只把 projection status 格式化为 Tool Trace 展示文本的 adapter；它不得继续读取 payload 字段推断 status"
- §6 S1 / S3 补 status mapping 测试要求

**验证**：mapping table 清晰覆盖所有状态值。优先级规则明确（canonical fields > raw outcome）。`_tool_result_status()` 被明确禁止继续拥有 status 推断逻辑。fix artifact 也指出"`governed_error` 的具体 durable 字段名需由 implementation 落实"，这是合理的 implementation-stage 依赖。

---

### P1A-PLAN-F06：`InitialEvidenceMaterial` / `_evidence_blocks()` 边界

**状态：已闭合**

Controller 要求：
- 分类 initial material path 为 in-scope migration 或 explicit non-goal
- 如果 in scope，加到 S2/S3 tests；如果 out of scope，解释为什么不是 accepted-result projection consumer

Plan fix 落实：
- §5 新增："`InitialEvidenceMaterial` / `_evidence_blocks()` 不是 accepted-result projection owner，本轮不把它们改造成 EventLog accepted result 读取路径。它们只允许承载调用方已经提供的初始材料 readable query/source/result；若 S3 测试需要用 accepted tool result 构造 initial material，测试输入必须先经 projection helper 派生，不能在 fixture 内手写另一套 accepted query/source 语义。"
- §8 补 checklist："Initial material：`InitialEvidenceMaterial` / `_evidence_blocks()` 保持非 accepted-result owner；相关测试不得手写 accepted query/source 语义"
- §6 S3 补 initial material grep / fixture 审计要求

**验证**：明确分类为 non-goal，并给出充分理由（它们承载调用方提供的初始材料，不是 EventLog accepted result 读取路径）。测试约束正确：若测试需用 accepted tool result 构造 initial material，必须经 projection helper 派生。

---

### P1A-PLAN-F07：validation scans

**状态：已闭合**

Controller 要求：
- 增加 `_readable_source_text_from_refs`、`source_note`、`tool_call_request_atoms` call-site scans 到 validation
- 说明 helper 内部仍调用 `tool_call_request_atoms` 时的 expected allowed matches

Plan fix 落实：
- §9 validation grep 更新为：
  ```
  rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host
  ```
- §9 明确允许/禁止规则

**验证**：所有 controller 要求的 grep pattern 已加入。允许/禁止规则明确区分了 helper 内部调用（允许）与消费者调用（禁止）。

---

## New Blocker Check

未发现因 fix 引入的新 blocker。fix 仅修改 plan artifact 的 contract 描述、migration checklist 和 validation 命令，未引入新的设计决策冲突或 scope 膨胀。

fix artifact 中列出的 3 个 residual risks 均为已知的 implementation-stage 关注点，不构成 plan-level blocker：
1. `governed_error` 具体字段名需 implementation 落实 — 这是 S1 实现依赖，plan 已在 §11 stop conditions 覆盖
2. Source refs 生产路径多数为空 — plan §11 已列为 residual risk
3. Tool Trace result details bounded rendering — plan §11 已列为 residual risk

---

## Summary

| Accepted Finding | 状态 | 修复方式 |
|---|---|---|
| P1A-PLAN-F01 | ✓ 闭合 | §4 窄方案选择 + helper 内部 back-query 设计 + §6/§8/§12 更新 |
| P1A-PLAN-F02 | ✓ 闭合 | §4 迁移到 canonical + dispatch boundary + mapping table |
| P1A-PLAN-F03 | ✓ 闭合 | §6 S1/S2 source producer 迁移 + §9 grep 增加 |
| P1A-PLAN-F04 | ✓ 闭合 | §4 常量 owner 迁移 + Conversation Memory 消费约束 |
| P1A-PLAN-F05 | ✓ 闭合 | §4 mapping table + 优先级规则 + `_tool_result_status()` 命运 |
| P1A-PLAN-F06 | ✓ 闭合 | §5 non-goal 分类 + §8 checklist + §6 S3 审计 |
| P1A-PLAN-F07 | ✓ 闭合 | §9 grep 增加 + 允许/禁止规则 |

**Final verdict: `pass`** — P1-A plan 可进入 implementation。
