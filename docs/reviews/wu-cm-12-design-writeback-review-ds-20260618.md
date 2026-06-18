# WU-CM-12 Design Writeback Review

## Review Metadata

- **Review type**: pre-plan design truth repair review
- **Work unit**: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- **Reviewer**: DeepSeek (ds)
- **Date**: 2026-06-18
- **Reviewed files**:
  - `docs/host/design.md` (diff: 319 lines, +295 / -24)
  - `docs/reviews/wu-cm-12-design-writeback-codex-20260618.md` (Codex writeback self-report)
- **Design input (truth source)**: `docs/host/conversation-memory-material-budget-discussion.md`
- **Output**: `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`

## Scope

本次 review 仅判断 AgentCodex 是否正确将 `docs/host/conversation-memory-material-budget-discussion.md` 中已接受语义写回 `docs/host/design.md`，使后续能只基于 `docs/host/design.md` 写 code-generation-ready plan。

审查面：
1. `assemble(...)` 展开完整性
2. `latest_accepted_compacted_view` 到五类 Session Semantic Memory 映射
3. `post_compact_delta_material`、`current_input_anchor`、`selected_recent_window_policy`、`protected_recent_floor_policy` 自洽性
4. tier 0-5 fallback 状态机、compactor 与 `CONTEXT_COMPACTED` 边界
5. no silent truncation 约束范围
6. `memory_projection_policy` owner 边界
7. 是否错误新增 public API / schema / contract
8. 是否引入过度设计或实现 handoff notes

非目标：plan review、code implementation review、修改生产代码。

## Verdict

**PASS** — 无阻塞问题。3 个 findings（1 Medium, 2 Low），均不影响写回正确性；后续 plan 可基于当前 `docs/host/design.md` 推进，但建议在 plan 阶段处理 Medium finding 中的设计缺口。

---

## Findings

### F1 — 未修复 — 中 — section-aware degrade 的 section 内 item 保留/丢弃顺序未明确所有权

- **文件(行号)**: `docs/host/design.md:3263`；对比 `docs/host/conversation-memory-material-budget-discussion.md:627-629`
- **输入场景**: 实施 Agent 在实现 tier 2 section-aware degrade 时，需要决定 section 内哪些 item 保留、哪些丢弃
- **实际分支**: design.md 写 "在 section 内按确定性顺序保留 / 丢弃完整 semantic item"，但未声明该顺序的所有者是谁
- **预期行为**: 讨论稿明确要求 "section 内 item 的保留 / 丢弃顺序必须由设计固定，例如按 semantic priority、source recency、material order 或稳定 digest 排序；不得由实施代码临时判断'重要 / 不重要'"
- **实际行为**: design.md 只说 "按确定性顺序"，实施 Agent 可能自行裁决顺序（如按创建时间、按 block id 字典序、按 item 文本长度），导致不同实现路径的 degrade 行为不可预测
- **直接证据**:
  - 讨论稿 line 627-629: "section 内 item 的保留 / 丢弃顺序必须由设计固定...不得由实施代码临时判断'重要 / 不重要'"
  - design.md line 3263: "在 section 内按确定性顺序保留 / 丢弃完整 semantic item" — 有 "确定性"，无 "由设计固定"
- **影响**: 后续 plan 如不补上 item 排序规则，实现层可能出现多个 selector 使用不同排序策略，导致 degrade 行为在 ordinary / compact / fallback 路径间不一致
- **建议改法和验证点**: 在 design.md line 3263 或 section-aware degrade 段落中补一句："section 内 item 的保留 / 丢弃顺序必须由设计固定（例如按 source recency、material order 或稳定 digest），不得由实施代码临时判断重要 / 不重要。" plan 阶段需明确排序字段和排序方向
- **修复风险**: 低 — 纯设计补全，不涉及代码
- **严重程度**: 中

### F2 — 未修复 — 低 — fail closed 条件在 fallback 状态机附近不够集中

- **文件(行号)**: `docs/host/design.md:3263`（fallback 状态机末尾）、`docs/host/design.md:3318`（reactive compact 上限）、`docs/host/design.md:3372`（`CONTEXT_COMPACTION_FAILED` payload）；对比 `docs/host/conversation-memory-material-budget-discussion.md:647-652`
- **输入场景**: 实施 Agent 写 fallback 状态机时，需要知道哪些条件应 fail closed（直接拒绝 dispatch），哪些应继续尝试下一 tier
- **实际分支**: design.md 中 fail closed 条件分散在多处：line 3263 只有 "如果 current-input-only 仍无法合法 dispatch，必须 fail closed"；line 3318 有 "超过 max_reactive_compactions_per_run 后 fail closed"；line 2657 有 manifest mismatch 的 fail closed；line 3190 有 stale/cancelled 不写 `CONTEXT_COMPACTED`
- **预期行为**: 讨论稿 line 647-652 给出 fail closed 的集中化列表（current input 单独超预算、durable 损坏、provenance 不一致、cancellation/session closed/run state 不允许），使 plan 可从一个位置理解所有硬停止条件
- **实际行为**: 实施 Agent 需要跨多个章节拼凑 fail closed 条件，可能遗漏某些场景
- **直接证据**:
  - 讨论稿 line 647-652: 显式列出 4 类 fail closed 条件
  - design.md line 3263: 仅覆盖 current-input-only 一种
  - design.md line 3190: stale/cancelled 不写 `CONTEXT_COMPACTED` 但未说 "fail closed"
  - design.md line 2657: manifest mismatch fail closed 但属于 runner-call manifest 语义，不在 Conversation Memory 范围内
- **影响**: 后续 plan 可能漏掉 durable corruption 或 provenance inconsistency 导致的 fail closed 场景，在实现中表现为 "静默产生破损上下文" 或 "错误继续 dispatch"
- **建议改法和验证点**: 在 fallback 状态机末尾（line 3263 附近）补一段 fail closed 收窄条件汇总："fail closed 应收窄为以下真正不可恢复或继续 dispatch 会破坏治理边界的场景：（1）current input anchor 本身超过 hard context budget；（2）durable EventLog / payload / artifact 损坏，无法构造可信输入；（3）selected material provenance 不一致，继续 dispatch 会污染事实边界；（4）cancellation、session closed、run state 已不允许继续。" plan 阶段按此列表逐项覆盖
- **修复风险**: 低 — 纯设计补全
- **严重程度**: 低

### F3 — 未修复 — 低 — section-aware degrade 禁止动作列表未显式写出

- **文件(行号)**: `docs/host/design.md:3263`；对比 `docs/host/conversation-memory-material-budget-discussion.md:623-629`
- **输入场景**: 实施 Agent 实现 tier 2 degrade 时，需要知道除了 keep/drop 之外还有什么动作是禁止的
- **实际分支**: design.md 通过正面声明 "允许动作只有保留完整 semantic section、丢弃完整 semantic section，或在 section 内按确定性顺序保留 / 丢弃完整 semantic item" 隐含了禁止语义
- **预期行为**: 讨论稿 line 623-629 显式列出禁止动作："禁止截断 semantic item text、重新 summary 或改写 summary、改写 fact/answer anchor/forward intent/reference continuity item、临时生成新的 compacted view、让 fallback 产生新的 Session Semantic Memory"
- **实际行为**: 实施 Agent 可能从 "允许动作只有..." 推导出禁止动作，但不如显式禁止列表安全。例如，Agent 可能认为 "临时生成新的 compacted view" 不在 "允许动作" 中所以禁止，但也可能误解 "允许动作只有..." 只是对 keep/drop 操作的描述，不排除其他辅助操作
- **直接证据**:
  - 讨论稿 line 623-629: 显式 5 条禁止动作
  - design.md line 3263: 只有正面允许动作，无负面影响列表
- **影响**: 低概率但高影响 — 若实施 Agent 在 degrade 中做了截断 text 或临时 summary，会直接违反 no-silent-truncation 约束，且该违规可能被后续测试漏掉
- **建议改法和验证点**: 在 design.md line 3263 的 "允许动作只有..." 之后补一句："禁止截断 semantic item text、重新 summary 或改写 summary、改写 fact/answer anchor/forward intent/reference continuity item、临时生成新的 compacted view，或让 fallback 产生新的 Session Semantic Memory。" plan 阶段的 test case 应包含 "degrade 后 text 未被截断" 和 "degrade 后未生成新 summary" 断言
- **修复风险**: 低
- **严重程度**: 低

---

## 逐条审查结论

### 1. `assemble(...)` 展开完整性 — PASS

展开版 `assemble(latest_accepted_compacted_view, post_compact_delta_material, current_input_anchor, selected_recent_window_policy, protected_recent_floor_policy)` 已完整写入 design.md line 2786-2793。旧版 `memory_material` 仍然保留为简写，但设计真源优先展示展开版（line 2781-2793）。`before compact` 边界情况也使用同一展开公式（line 2828-2835）。

### 2. `latest_accepted_compacted_view` 到五类 Session Semantic Memory 映射 — PASS

映射已显式写入 design.md line 2798-2805：

```text
latest_accepted_compacted_view =
  trace_memory.reference_continuity_items
  + evidence_fact_memory.evidence_backed_facts
  + session_summary_memory.summary_text
  + answer_anchor_memory.anchors
  + forward_intent_memory.intents
```

并在 line 2815 明确 `selected_recent_window` 不是第六类 Semantic Memory，line 3047 补充 `TraceMemoryView.selected_recent_window` 和 `EvidenceFactMemoryView.recent_evidence_items` 只是 bounded recent view，不会自动生成 summary/answer anchor/forward intent/evidence-backed fact。

### 3. post_compact_delta_material、current_input_anchor、selected_recent_window_policy、protected_recent_floor_policy 自洽性 — PASS

- `post_compact_delta_material`: 边界定义为 latest accepted compact boundary 之后的 committed canonical material（line 2807），至少包含 USER_INPUT_ACCEPTED.display_text、RUN_SUCCEEDED.final_answer、readable accepted tool evidence、user-visible run outcome material。不包含 current input（属于 anchor）、裸 TOOL_CALL_REQUESTED、未 committed/in-flight 状态。
- `current_input_anchor`: 单独传入 assemble，不得作为历史 material source（line 2811）。reactive/recovery 中 committed accepted current-run evidence 可参与 assembly 但不改写 current input prompt 成历史 block。
- `selected_recent_window_policy`: 只从 post_compact_delta_material 选择（line 2813），不从 latest_accepted_compacted_view 重新选择。基本单位是完整 material block，带 turn_group_id、role/material kind、source refs、稳定 block id。
- `protected_recent_floor_policy`: 以 `turn_group_id = host_run_id` 为单位保护最近 N 个 Host admitted user Run（line 2813）。floor 与 cap 冲突时 floor 优先，超 hard threshold 进 tier 5。
- selected recent window 在 ordinary 与 fallback 复用同一 selection 语义，只替换 caps/tier（line 3289）。

### 4. tier 0-5 fallback 状态机 — PASS

完整 tier 0-5 状态机已写入 design.md line 3193-3261：

- tier 0: normal，送 LLM compactor 或 ordinary RunInput per Context Governance
- tier 1: tighter recent window，送 LLM compactor
- tier 2: section-aware degraded compacted view + tighter recent window，送 LLM compactor
- tier 3: delta-only (无 compacted view)，送 LLM compactor
- tier 4: floor-only (protected_recent_turn_floor + current_input_anchor)，不送 LLM compactor
- tier 5: current-input-only，不送 LLM compactor

边界明确：
- tier 1-3 accepted output 可提交 `CONTEXT_COMPACTED` 并投影五类 memory（line 3054, 3261）
- tier 4-5 不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact / memory snapshot / 五类 memory（line 3055, 3261）
- section-aware degrade 优先级：evidence_backed_facts > reference_continuity_items > answer_anchors > forward_intents > summary_text（line 3263）
- 进入下一 tier 的判断第一阶段使用当前 Context Governance conservative estimator（line 3261 末尾确认）

Tier 1-3 与 tier 4-5 的 LLM compactor、CONTEXT_COMPACTED、compact artifact、memory snapshot、五类 memory 输出边界正确。

### 5. no silent truncation 约束 — PASS

约束已写入 line 2866：

> LLM-facing memory / compact / RunInput material 不允许字段级 silent truncation、preview 化或 summary 化。

范围限定为 "LLM-facing"，明确不扩大到 UI/log/diagnostic 展示。缩小方式只允许 deterministic selection、whole-item/whole-section keep-drop、chunking with provenance、section-aware degrade 或 fail closed。

Line 3115 补充 ordinary path 不在 runtime 做字段级或逐 section silent truncation。

Line 3290 从 compact material selection 角度再次确认 whole-block keep-drop 不得用字段级 silent truncation 或 lossy preview 冒充完整 material。

约束边界清楚：LLM-facing 材料严格受限；UI/log/diagnostic/audit 不在此约束范围内。

### 6. memory_projection_policy owner 边界 — PASS

Owner 声明在 line 2817：

> `memory_projection_policy` 是 Host 内部 LLM-facing memory / material 产量的唯一 policy owner，至少覆盖 `selected_recent_window_policy`、`fallback_selected_recent_window_policy`、`protected_recent_floor_policy`、`semantic_memory_section_caps`、`projection_repair_policy` / parser safety guard policy。

明确：
- JSON 是否保持 flat 属于实现形态（line 2817），不作为设计真源要求
- Host 内部不得用 DTO 私有 cap、renderer 私有截断值或零散常量作为另一套 LLM-facing material 产量真源
- 四大语义分组（selected_recent_window / protected_recent_floor / semantic_memory_section_caps / projection_repair）已在 line 2817 列出，不包含 JSON nesting 细节

### 7. 是否错误新增 Host/Engine public API、durable schema、EventLog canonical semantics 或跨层 contract — PASS

审查的改动范围：
- `RunnerCallKind` enum `post_compaction_dispatch` 描述: "deterministic recent-window fallback" → "tier 4/5 dispatch fallback"（仅术语更新）
- `context_fallback_decision_ref` 描述: "recent-window fallback decision" → "tiered dispatch fallback decision when compaction recovery failed"（仅术语更新 + 语义精确化）
- Section 8 `Recent Evidence` 内容来源描述：术语更新

均为现有 schema 字段的描述更新，未新增字段、枚举值、durable schema、EventLog canonical event type 或跨层 contract。Codex writeback 文档声称 "未新增 Host / Engine public API、durable schema、EventLog canonical semantics 或跨层 contract" 成立。

### 8. 是否引入过度设计、实现 handoff notes 等 — PASS

design.md diff 中未出现：
- Implementation handoff notes、current code owner、allowed files
- 测试命令、plan slice 参考
- Python 类型名作为设计真源
- `dayu/host/memory.py`、`dayu/host/compact_material.py` 等实现模块名
- "Implementation Plan Reference" 或 "Plan Slice Reference" 内容

Codex writeback 正确过滤了讨论稿中的 Implementation Handoff Notes（line 658-717）、Implementation Plan Reference（line 1022-1071）、已核对的实现事实（line 1074-1302）等非设计真源内容。

---

## 审查面汇总

| # | 审查面 | 结论 | 关联 Finding |
|---|---|---|---|
| 1 | `assemble(...)` 展开完整性 | PASS | — |
| 2 | `latest_accepted_compacted_view` 到五类 memory 映射 | PASS | — |
| 3 | material/anchor/policy/floor 自洽性 | PASS | — |
| 4 | tier 0-5 fallback 状态机 + compactor 边界 | PASS | F1, F2, F3 |
| 5 | no silent truncation 约束范围 | PASS | — |
| 6 | `memory_projection_policy` owner 边界 | PASS | — |
| 7 | 错误新增 API/schema/contract | PASS | — |
| 8 | 过度设计 / handoff notes | PASS | — |

---

## Findings 汇总表

| # | Severity | 标题 | design.md 行号 | 讨论稿行号 | 影响后续 plan |
|---|---|---|---|---|---|
| F1 | 中 | section-aware degrade item 保留/丢弃顺序所有权未明确 | 3263 | 627-629 | 实施 Agent 可能自创排序规则，degrade 行为不可预测 |
| F2 | 低 | fail closed 条件在 fallback 状态机附近不够集中 | 3263 | 647-652 | 实施 Agent 可能遗漏 durable corruption / provenance inconsistency 等场景 |
| F3 | 低 | section-aware degrade 禁止动作列表未显式写出 | 3263 | 623-629 | 实施 Agent 可能在 degrade 中做截断 text 或临时 summary |

---

## Residual Risks / Uncovered Areas

1. **现有实现漂移验证未做**：本次只审查设计真源写回正确性。设计文档中明确指出的实现漂移（`TraceReadableItemVNext.text <= 1200`、`CurrentInputAnchorVNext.text <= 1200`、compactor output schema cap 与 policy cap 双真源、fallback selection/rendering 不同源等）尚未验证现有代码是否已修正。后续 code-generation-ready plan 必须以设计真源为基准逐项核对。

2. **第 23 章 system envelope section table 与 Conversation Memory 的交叉引用**：design.md line 3119 说 "23 节表格是 section title 与映射关系的唯一真源，本文不重复硬编码完整 title 列表"，但第 23 章 section 8 `Recent Evidence` 的描述已更新（"recent-window fallback" → "fallback bounded material"）。两端术语已对齐，但后续 plan 需要确保 section table、Conversation Memory、Context Governance fallback 三处对 "fallback bounded material" / "Recent Evidence" 路由的解释一致。

3. **`protected_recent_turn_floor` vs `protected_recent_floor_policy` 命名差异**：tier 4 的 assemble 中使用 `protected_recent_turn_floor`（指 policy 选出的实际 material），而 policy 对象名称是 `protected_recent_floor_policy`。两者语义清楚（policy vs material），但 plan 阶段需要为 "policy 输出的 floor material" 选定一个稳定术语，避免实现中混用。

4. **`context_window_size` 的定位**：设计文档中 `context_window_size` 在第 25 章描述为 "composition root 从 effective model config 读取并传入 typed policy"（line 3148），但不显式声明它不作为 selected recent window caps 的比例参数。讨论稿 line 324 明确说 "不是 selected_recent_window_policy 的直接比例参数"，但 design.md 未显式写出此否定句。实施 Agent 可能从 "typed input for validation/calibration" 推导出正确行为，但显式否定更安全。

5. **`ConversationCompactInputVNext` 的 DTO 字段 cap**：设计文档中 `ConversationCompactInputVNext` 的 schema 定义了 `TraceReadableItem.text`、`CurrentInputAnchor.text` 等字段（line 2922-2940），但无 char cap 约束。设计真源（line 2866）已声明不允许 silent truncation。后续实现如果保留 schema 层的 pydantic `max_length` 校验，会与设计真源冲突。plan 需明确：schema 字段的 `max_length` 应移除或改为远超业务合理上限的 parser safety guard。

---

## Open Questions

无。

---

## 附录：验证命令输出

```text
# 旧术语已清除
rg -n 'deterministic recent-window fallback' docs/host/design.md → exit 1 (无匹配)

# 核心 tier 全部存在
rg -n 'tier 0 normal|tier 1 compact recovery|...' docs/host/design.md
  → 3196/3208/3220/3232/3243/3252 全部命中

# no silent truncation 三处确认（LLM-facing 材料 + ordinary path + material selection）
rg -n 'silent truncation' docs/host/design.md → 2866, 3115, 3290

# memory_projection_policy owner 双重确认（typed contract + semantic grouping）
rg -n 'memory_projection_policy.*唯一 policy owner' docs/host/design.md → 2817

# turn group = host_run_id 两处确认
rg -n 'host_run_id.*turn group|turn_group_id.*host_run_id' docs/host/design.md → 2813, 3263

# CONTEXT_COMPACTED 在 tier 1-3 / tier 4-5 的边界明确
rg -n 'CONTEXT_COMPACTED' docs/host/design.md → 3054 (tier 1-3 可提交), 3055 (tier 4-5 不提交), 3261 (同上)
```
