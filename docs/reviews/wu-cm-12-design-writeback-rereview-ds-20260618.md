# WU-CM-12 Design Writeback Re-review

## Review Metadata

- **Review type**: focused re-review of AgentCodex fix against accepted DS findings
- **Work unit**: WU-CM-12 Conversation Memory design truth repair
- **Reviewer**: DeepSeek (ds)
- **Date**: 2026-06-18
- **Input artifacts**:
  - `docs/host/design.md`（当前状态，fix 已写入）
  - `docs/reviews/wu-cm-12-design-writeback-fix-codex-20260618.md`（Codex fix 自述）
  - `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`（原始 DS review，含 3 个 accepted findings）
  - `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`（MiMo review，零 finding 通过）
- **Output**: `docs/reviews/wu-cm-12-design-writeback-rereview-ds-20260618.md`

## Scope

本次是 focused re-review，仅判断 AgentCodex 对 3 个 accepted DS findings 的修复是否充分。非 plan review、非 code implementation review。附带检查 fix 是否引入新的设计真源问题、过度设计、implementation handoff notes、public API/schema/contract 变更。

审查面：
1. DS F1 — section-aware degrade 的 section 内 item 保留/丢弃顺序
2. DS F2 — fallback fail closed 条件集中化
3. DS F3 — section-aware degrade 禁止动作列表

## Findings

未发现实质性问题。三个 accepted findings 均已修复，fix 未引入新的设计真源问题。

---

## 逐 Finding 裁决

### DS F1 — section-aware degrade item 保留/丢弃顺序

**状态：已修复**

**原 finding**（DS review F1）：design.md line 3263 只写"按确定性顺序"，未声明该顺序的所有者是谁；实施 Agent 可能自行裁决顺序，导致 ordinary / compact / fallback 路径 degrade 行为不可预测。讨论稿 line 627-629 明确要求"section 内 item 的保留 / 丢弃顺序必须由设计固定……不得由实施代码临时判断'重要 / 不重要'"。

**Fix 内容**（design.md line 3263，已确认命中）：

> section 内 item 的保留 / 丢弃顺序必须由设计固定，不得由实施代码临时判断重要 / 不重要；本文只固定设计原则：排序依据必须业务可解释、稳定、可在同一 input cursor、material source cursor 与 policy 下确定性复现。后续 code-generation-ready plan 必须基于该原则选择稳定排序字段和排序方向，并确保 ordinary / compact / fallback 路径复用同一规则。

**裁决理由**：

1. "必须由设计固定，不得由实施代码临时判断重要 / 不重要"直接回应了 F1 的核心诉求——剥夺实施层对 item 重要性的自由裁量权。✅
2. "本文只固定设计原则"将具体排序字段选择推迟到 code-generation-ready plan，这是正确的设计→plan 分层：设计固定原则和约束，plan 选定具体字段。讨论稿 line 629-630 对排序字段的表述也是"例如按 semantic priority、source recency、material order 或稳定 digest 排序"，使用的是"例如"（举例）而非"必须"，说明讨论稿本身也未在设计层硬编码具体字段。✅
3. "排序依据必须业务可解释、稳定、可在同一 input cursor、material source cursor 与 policy 下确定性复现"给出了三个具体约束：业务可解释性、稳定性、确定性复现。plan 在选定字段时必须同时满足三者。✅
4. "确保 ordinary / compact / fallback 路径复用同一规则"防止了不同路径使用不同排序策略的漂移风险。✅

**边界注意**：当前 fix 未选定具体排序字段和排序方向（如 source recency、material order、digest 等）。这是设计层的有意保留，但后续 plan 必须落实。若 plan 遗漏此项，F1 的风险会重新出现。

---

### DS F2 — fallback fail closed 条件集中化

**状态：已修复**

**原 finding**（DS review F2）：fail closed 条件分散在 line 3263（current-input-only 一种）、line 3318（max_reactive_compactions_per_run）、line 2657（manifest mismatch）、line 3190（stale/cancelled 不写 CONTEXT_COMPACTED）等多处；实施 Agent 需要跨章节拼凑，可能遗漏 durable corruption 或 provenance inconsistency 场景。讨论稿 line 647-652 给出了集中的 4 类 fail closed 条件。

**Fix 内容**（design.md line 3265，已确认命中）：

> Fallback fail closed 条件必须集中收窄为真正不可恢复，或继续 dispatch 会破坏 Host 治理 / 事实边界的场景：current input anchor 本身超过 hard context budget；durable EventLog、payload 或 artifact 损坏，导致 Host 无法构造可信 LLM-facing 输入；selected material provenance 不一致，继续 dispatch 会污染事实边界；cancellation、session closed 或当前 Run state 已不允许继续执行。其它可恢复的 compaction proposal 质量问题、schema 问题、预算问题或 provider overflow，应先按 bounded repair、tier 1-3 compact recovery fallback、tier 4/5 dispatch fallback 或 failure policy 收口，不能绕过上述 hard stop 边界静默 dispatch。

**裁决理由**：

1. 讨论稿要求的 4 类 fail closed 条件全部覆盖，且措辞更精确：
   - "连当前用户输入都无法放入" → "current input anchor 本身超过 hard context budget" ✅
   - "durable EventLog / payload / artifact 损坏，无法构造可信输入" → "durable EventLog、payload 或 artifact 损坏，导致 Host 无法构造可信 LLM-facing 输入"（加上"LLM-facing"限定，避免过度扩大到 diagnostic/audit 材料） ✅
   - "selected material provenance 不一致，继续 dispatch 会污染事实边界" — 原文保留 ✅
   - "cancellation、session closed、run state 已不允许继续" → "cancellation、session closed 或当前 Run state 已不允许继续执行"（加上"当前"限定和"执行"动作） ✅
2. 补充了正向排除句："其它可恢复的…不能绕过上述 hard stop 边界静默 dispatch"，明确区分了"真正不可恢复"与"应走 repair/tier/fallback/failure policy 收口"的边界，避免实施层把可恢复问题误判为 fail closed。✅
3. 集中化位置在 fallback 状态机末尾（line 3265，紧接 tier 5 之后），符合 DS F2 要求的"在 fallback 状态机附近集中写出"。✅

**与其它 fail closed 提及的一致性检查**：

- Line 3263 末尾"如果 current-input-only 仍无法合法 dispatch，必须 fail closed"是 tier 5 内部触发条件，与集中化列表第 1 条"current input anchor 本身超过 hard context budget"对应，无矛盾。
- Line 3320"超过 `max_reactive_compactions_per_run` 后 fail closed"是 reactive multi-pass 的操作预算耗尽触发，本质上属于"预算问题→按 failure policy 收口"的路径，不构成与集中化列表的冲突。
- Line 3190"stale / cancelled / session closed…不写 `CONTEXT_COMPACTED`"是 compaction repair 拒绝规则，不属于 dispatch fail closed 范畴。
- 集中化列表是 fail closed 的语义真源；其他位置的提及是具体路径上的操作触发，两者是"定义"与"引用"的关系，不矛盾。

---

### DS F3 — section-aware degrade 禁止动作列表

**状态：已修复**

**原 finding**（DS review F3）：design.md 通过正面"允许动作只有…"隐含禁止语义，未显式写出禁止动作列表。讨论稿 line 623-629 显式列出 5 条禁止动作。实施 Agent 可能误解"允许动作只有…"只是对 keep/drop 操作的描述，不排除其他辅助操作。

**Fix 内容**（design.md line 3263，已确认命中）：

> degrade 禁止动作列表固定为：禁止截断 semantic item text；禁止重新 summary 或改写 summary；禁止改写 fact、answer anchor、forward intent 或 reference continuity item；禁止临时生成新的 compacted view；禁止让 fallback 产生新的 Session Semantic Memory。

**裁决理由**：

1. 讨论稿 5 条禁止动作全部显式列出：
   - 禁止截断 semantic item text ✅
   - 禁止重新 summary 或改写 summary ✅
   - 禁止改写 fact、answer anchor、forward intent 或 reference continuity item ✅
   - 禁止临时生成新的 compacted view ✅
   - 禁止让 fallback 产生新的 Session Semantic Memory ✅
2. 使用"禁止动作列表固定为"的措辞，与前面的"允许动作只有…"形成完整的允许/禁止双边约束。实施 Agent 不再需要从正面允许推导反面禁止。✅
3. 禁止列表与允许列表在同一个段落中（line 3263），实施 Agent 可以在同一位置看到完整约束。✅

---

## Fix 副作用检查

### 是否引入新的设计真源问题

- **Line 3263 段落长度**：当前 line 3263 承载了 degrade 定义、优先级、允许动作、item 排序原则（F1 fix）、禁止动作列表（F3 fix）、tier 4 floor 描述和 tier 5 fail closed 触发，信息密度较高。但此段落结构在 fix 前已存在（原来就承载了 degrade 定义、优先级、允许动作、floor 和 fail closed），fix 只增加了排序原则和禁止列表。**不属于 fix 引入的新问题**，但后续 plan 引用此段落时需注意各子句的边界。
- **集中化列表与 `max_reactive_compactions_per_run` 的关系**：集中化列表（line 3265）将 fail closed 收窄为 4 类"真正不可恢复"场景，并说"预算问题…应按 failure policy 收口"。`max_reactive_compactions_per_run` 耗尽（line 3320）本质上是预算耗尽，其 fail closed 应理解为"通过 CONTEXT_COMPACTION_FAILED 的 failure policy 路径"，与集中化列表的"不能绕过 hard stop 边界静默 dispatch"一致。**无矛盾**。

### 是否引入过度设计

未发现。F1 fix 只固定了排序原则的三条约束（业务可解释、稳定、确定性复现），未过早选定具体字段。F2 fix 只列出了 4 类 hard stop 条件。F3 fix 只列出了 5 条禁止动作。均为最小化补全，无新增概念、类型、状态机或契约。

### 是否引入 implementation handoff notes

未发现。F1 fix 中的"后续 code-generation-ready plan 必须基于该原则选择稳定排序字段和排序方向"是设计→plan 的正常 handoff 约束，不是 implementation handoff。全文未出现 current code owner、allowed files、测试命令、代码类型名或 plan slice reference。

### 是否引入 public API / schema / contract 变更

未发现。fix 仅修改 `docs/host/design.md`，未触及任何 public API、durable schema、EventLog canonical semantics 或跨层 contract。

---

## 裁决汇总

| Finding | 状态 | 裁决要点 |
|---|---|---|
| DS F1 — item 保留/丢弃顺序所有权 | **已修复** | 设计原则已固定（业务可解释、稳定、确定性复现）；具体字段留给 plan |
| DS F2 — fail closed 条件集中化 | **已修复** | 4 类 hard stop 条件集中于 line 3265；与其它 fail closed 提及无矛盾 |
| DS F3 — 禁止动作列表 | **已修复** | 5 条禁止动作全部显式列出 |

---

## Open Questions

无。

## Residual Risk

1. **F1 排序字段未选定**：设计层有意将具体排序字段和方向留给 code-generation-ready plan。若后续 plan 遗漏此项，或选定的字段不满足"业务可解释、稳定、确定性复现"三条约束，F1 的风险会重新出现。plan review 应将此项作为必检项。

2. **Line 3263 段落信息密度**：当前 line 3263 承载了 7 个语义子句（degrade 定义、优先级、允许动作、item 排序原则、禁止动作、tier 4 floor、tier 5 fail closed）。后续 plan 引用时需注意各子句边界，避免平面化理解。这不是 fix 引入的问题，但 fix 增加了子句数量，放大了已有密度。

3. **现有实现漂移验证仍未做**：fix 只修复了设计真源，未验证 `dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/context_fallback.py` 中的现有实现是否符合更新后的 degrade、fail closed 和 no-silent-truncation 边界。这是后续 plan 和 implementation 的责任。
