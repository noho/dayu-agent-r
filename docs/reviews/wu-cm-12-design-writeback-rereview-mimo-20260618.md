# WU-CM-12 Design Writeback Focused Re-Review

## Review Metadata

- **Review type**: pre-plan design truth repair focused re-review
- **Work unit**: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- **Reviewer**: MiMo
- **Date**: 2026-06-18
- **Reviewed files**:
  - `docs/host/design.md`（fix 写入点：line 3263、line 3265）
  - `docs/reviews/wu-cm-12-design-writeback-fix-codex-20260618.md`（Codex fix 自检报告）
- **参考 review artifacts**:
  - `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`（DS 原始 review）
  - `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`（MiMo 原始 review）
- **Source of truth**: `docs/host/conversation-memory-material-budget-discussion.md`（已接受设计裁决）

## Scope

本次只审查 AgentCodex 对 DS review 中已 accepted 的 3 个 findings 的修复是否充分。不审查设计写回的其余部分（已在先前 review 中通过）。不修改生产代码、测试、配置或除本 artifact 外的任何文件。

---

## Findings

### 未发现实质性问题

以下逐项验证三个 accepted findings 的修复状态。

---

## Accepted Finding 验证

### DS F1：section-aware degrade 的 section 内 item 保留 / 丢弃顺序必须明确由设计固定

**状态：已修复**

**原始问题**（DS F1）：design.md 只写 "按确定性顺序"，未声明顺序所有者是谁；实施 Agent 可能自行裁决顺序。

**讨论稿原义**（line 630）：

> section 内 item 的保留 / 丢弃顺序必须由设计固定，例如按 semantic priority、source recency、material order 或稳定 digest 排序；不得由实施代码临时判断"重要 / 不重要"。

**design.md 修复写入**（line 3263）：

> section 内 item 的保留 / 丢弃顺序必须由设计固定，不得由实施代码临时判断重要 / 不重要；本文只固定设计原则：排序依据必须业务可解释、稳定、可在同一 input cursor、material source cursor 与 policy 下确定性复现。后续 code-generation-ready plan 必须基于该原则选择稳定排序字段和排序方向，并确保 ordinary / compact / fallback 路径复用同一规则。

**验证**：

1. ✅ "必须由设计固定" — 明确了顺序所有权归设计，不归实施代码。
2. ✅ "不得由实施代码临时判断重要 / 不重要" — 与讨论稿一致，禁止实施 Agent 自创排序规则。
3. ✅ 设计原则写明："排序依据必须业务可解释、稳定、可在同一 input cursor、material source cursor 与 policy 下确定性复现" — 比讨论稿的 "例如按 semantic priority、source recency、material order 或稳定 digest 排序" 更精确，把具体字段选择留给 plan 阶段，同时确保设计原则足够约束。
4. ✅ "ordinary / compact / fallback 路径复用同一规则" — 讨论稿未显式写此要求，但这是合理的设计补强，防止不同路径使用不同排序策略。
5. ✅ 未过度设计：未提前选定具体排序字段，保留给 code-generation-ready plan。

**结论**：修复充分，语义覆盖讨论稿原义，且增加了路径复用约束，属于合理的设计补强。

---

### DS F2：fallback 状态机附近需要集中写出 fail closed 条件

**状态：已修复**

**原始问题**（DS F2）：fail closed 条件分散在 design.md 多处（line 3263、3318、3372），实施 Agent 需跨多个章节拼凑。

**讨论稿原义**（line 646-651）：

> fail closed 应收窄为真正不可恢复或继续 dispatch 会破坏治理边界的场景，例如：
> - `current_input_anchor` 本身超过 hard context budget，连当前用户输入都无法放入。
> - durable EventLog / payload / artifact 损坏，无法构造可信输入。
> - selected material provenance 不一致，继续 dispatch 会污染事实边界。
> - cancellation、session closed、run state 已不允许继续。

**design.md 修复写入**（line 3265）：

> Fallback fail closed 条件必须集中收窄为真正不可恢复，或继续 dispatch 会破坏 Host 治理 / 事实边界的场景：current input anchor 本身超过 hard context budget；durable EventLog、payload 或 artifact 损坏，导致 Host 无法构造可信 LLM-facing 输入；selected material provenance 不一致，继续 dispatch 会污染事实边界；cancellation、session closed 或当前 Run state 已不允许继续执行。其它可恢复的 compaction proposal 质量问题、schema 问题、预算问题或 provider overflow，应先按 bounded repair、tier 1-3 compact recovery fallback、tier 4/5 dispatch fallback 或 failure policy 收口，不能绕过上述 hard stop 边界静默 dispatch。

**验证**：

1. ✅ 四类 fail closed 条件全部覆盖：
   - current input anchor 超 hard context budget ✅
   - durable EventLog / payload / artifact 损坏 ✅
   - selected material provenance 不一致 ✅
   - cancellation / session closed / run state 不允许继续 ✅
2. ✅ 条件集中在 fallback 状态机描述之后（line 3265），紧接 tier 0-5 状态机（line 3196-3263），实施 Agent 可从一个位置理解所有硬停止条件。
3. ✅ 补充了 "其它可恢复场景应先按 repair / fallback / failure policy 收口" — 明确了 fail closed 与可恢复路径的边界，比讨论稿更精确。
4. ✅ 未过度设计：未引入新的状态机或 schema，只做设计原则集中化。

**结论**：修复充分，四类条件全部覆盖且集中化，同时增加了可恢复路径的边界说明。

---

### DS F3：section-aware degrade 需要显式禁止动作列表

**状态：已修复**

**原始问题**（DS F3）：design.md 只有正面允许动作，无显式禁止列表；实施 Agent 可能误解 "允许动作只有..." 不排除其他辅助操作。

**讨论稿原义**（line 622-628）：

> 禁止的动作：
> - 截断 semantic item text。
> - 重新 summary 或改写 summary。
> - 改写 fact、answer anchor、forward intent 或 reference continuity item。
> - 临时生成新的 compacted view。
> - 让 fallback 产生新的 Session Semantic Memory。

**design.md 修复写入**（line 3263）：

> degrade 禁止动作列表固定为：禁止截断 semantic item text；禁止重新 summary 或改写 summary；禁止改写 fact、answer anchor、forward intent 或 reference continuity item；禁止临时生成新的 compacted view；禁止让 fallback 产生新的 Session Semantic Memory。

**验证**：

1. ✅ 五条禁止动作全部逐字覆盖，与讨论稿完全一致。
2. ✅ 位置在 "允许动作只有..." 之后，逻辑顺序正确：先说允许，再说禁止。
3. ✅ 使用 "固定为" 措辞，明确这是设计层面的硬约束，不是建议。
4. ✅ 未过度设计：未引入额外的禁止动作，严格对应讨论稿。

**结论**：修复充分，五条禁止动作逐字对应讨论稿，位置和措辞恰当。

---

## 附加审查：fix 是否引入新问题

### 是否引入新的设计真源问题

**结论：否**。三个 fix 都是在已有设计段落中补强约束，未修改已有语义，未引入矛盾。DS F1 增加的 "ordinary / compact / fallback 路径复用同一规则" 是合理补强，不与讨论稿冲突。

### 是否过度设计

**结论：否**。DS F1 未提前选定具体排序字段；DS F2 只做条件集中化，未引入新状态机；DS F3 逐字搬运讨论稿禁止列表。三者都是最小化设计补全。

### 是否引入 implementation handoff notes

**结论：否**。fix 中未出现 current code owner、allowed files、测试命令、plan slice 参考或 Python 类型名。

### 是否引入 public API / schema / contract 变更

**结论：否**。三个 fix 都是设计文档内部的约束补强，未新增字段、枚举值、durable schema 或跨层 contract。

---

## Open Questions

无。

## Residual Risk

- 本次只验证了三个 accepted findings 的 fix 充分性，未重新审查 design.md 其余部分（已在先前 review 中通过）。
- DS F1 的具体排序字段和排序方向仍由后续 code-generation-ready plan 决定；设计原则已足够约束，但 plan 阶段必须实际选定并写入。
- DS F2 的 fail closed 条件集中化后，design.md 其余位置（如 line 3318 reactive compact fail closed、line 3372 `CONTEXT_COMPACTION_FAILED` payload）的分散 fail closed 表述仍然存在；集中化段落应作为权威来源，其余位置的表述不应与之矛盾（当前不矛盾，但后续编辑需注意）。
- DS F3 的禁止列表已写入，但后续 plan 的 test case 需包含 "degrade 后 text 未被截断" 和 "degrade 后未生成新 summary" 断言，以验证实现遵守禁止列表。
