# Plan Review — WU-CM-01-F01-S7-R1 One-System-Message Rescope Plan

## Metadata

- **review target**: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- **work unit**: `WU-CM-01-F01-S7-R1`
- **review type**: adversarial plan review (pre-implementation)
- **design source**: `docs/host/design.md`
- **control source**: `docs/host/issues-implementation-control.md`
- **closeout plan**: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- **blocker adjudication**: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-controller-adjudication.md`
- **DS blocker review**: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-review-ds.md`
- **review timestamp**: 2026-06-05T17:16:55+08:00
- **review artifact**: `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-ds.md`

## Reviewed Target and Scope

本 review 审查 `WU-CM-01-F01-S7-R1` 的 one-system-message rescope plan，判断该 plan 是否 code-generation-ready，能否安全交给 implementation agent。

## Assumptions Tested

| # | assumption | evidence tested against | verdict |
|---|---|---|---|
| A1 | `one-system-message` 作为 hard production contract 是正确方向 | design.md §23/§24 LLM-facing 边界；closeout plan F01 success signal；controller adjudication 裁决 | **成立** — design.md 已禁止 compact/memory 暴露内部 refs，但未约束普通 RunInput system cardinality；controller 已裁决 one-system-message 是 WU-CM-01-F01 的 hard success signal |
| A2 | root cause 唯一在 `dayu/host/run_input.py` | DS blocker review 代码定位；production `SystemMessage(...)` 构造点分布 | **成立** — 所有 system message 构造点均在 `run_input.py` 内 |
| A3 | 在 RunInputBuilder 边界做 normalization 是最佳位置 | design.md §23 RunInputBuilder 是 `AgentRunRequest.messages` 唯一构造入口；Engine 不应理解 Host memory/compact | **成立** — RunInputBuilder 是设计真源指定的唯一构造入口 |
| A4 | 合并为单条 system message 不会丢失业务语义 | plan §Goal: "selected recent window 中的 user / assistant 对话连续性保留原角色" | **部分成立** — 见 Finding 2 |
| A5 | 所有 system-scoped material 的 content 均为纯文本，可直接拼接 | plan §S7-R1-S1: "若遇到未知 message type...抛出结构化 Host 错误" | **需验证** — 见 Finding 3 |
| A6 | 禁止 `policy` / `digest` 等通用词不会阻塞 prompt 演进 | DS blocker review Finding 2；plan §S7-R1-S2 stop condition | **低风险** — plan 已正确 defer 该问题 |

## Findings

### 1-未修复-高-system envelope section 格式欠规格，implementation agent 需自行发明 section title、separator 与合并算法

- **位置**: plan §Design Source Updates Required Before Code §2 "system envelope sections"；plan §S7-R1-S1 "新增模块级私有 typed helper"
- **问题类型**: 不可直接实施
- **当前写法**:
  - §2: "system envelope 以稳定 section 顺序承载：caller system prompt、Host-neutral execution instruction、memory summary / facts / anchors / forward intents / reference continuity、accepted compacted view、fallback / wait continuity guidance"
  - §2: "section header 是 LLM-facing 业务标题，不是 projector id、Python 类型名、policy ref 或内部模块名"
  - §2: "空 section 不渲染；非空 section 之间使用稳定分隔"
  - §S7-R1-S1: "system envelope 使用模块级常量定义 section title / separator；不得散落魔法字符串"
- **反例/失败场景**:
  1. Implementation agent 需要自行决定 8+ 个 section 的具体英文标题（如 "Session Summary" vs "Conversation Summary" vs "Memory Summary"），不同选择会改变 LLM 对 system envelope 的解析行为。
  2. "稳定分隔" 未定义——是 `\n\n`、`\n---\n`、`\n===\n` 还是 Markdown heading（`## Section Name`）？不同分隔符对 tokenization 和 LLM 注意力分配有不同影响。
  3. 如果 implementation agent 选择了与 compact system prompt 中已使用的分隔符冲突的格式，会导致 compact 路径的 LLM 混淆 system envelope 边界与 compact instruction 边界。
  4. 当前代码中各 memory section 使用 `_MEMORY_SESSION_SUMMARY_HEADER` 等模块级常量（如 `run_input.py:2242`），但这些 header 被硬编码为业务英文标题。plan 要求改为 "LLM-facing 业务标题" 但没有给出具体标题列表，implementation agent 可能沿用旧标题而不审查其 LLM-facing 质量。
- **为什么有问题**: plan 正确识别了需要 section ordering 和 header，但没有给出具体值。对于 "code-generation-ready" 的 plan，section title 和 separator 是 LLM-facing contract 的一部分，不应由 implementation agent 临场决定。
- **直接证据**:
  - plan §Design Source Updates Required Before Code §2 只描述了 section 的语义类别（caller system prompt、Host-neutral execution instruction 等），没有给出具体 header 文本
  - plan §S7-R1-S1 只说 "使用模块级常量定义 section title / separator"，没有给出常量名或建议值
  - 当前 production code 中 `_MEMORY_SESSION_SUMMARY_HEADER` 等常量的定义位置和具体值在 plan 中未被引用或审查
- **影响**: implementation agent 自行发明 section title/separator → 后续 design review 可能拒绝已实现的格式 → 返工；或格式未 review 直接合入 → LLM-facing 文本质量下降
- **建议改法和验证点**:
  1. 在 plan 或 Slice S7-R1-S0 的 design.md 更新中给出至少以下 section 的具体 LLM-facing 标题候选：
     - caller system prompt section header
     - Host-neutral execution context section header
     - memory summary section header
     - evidence/fact section header
     - answer anchor section header
     - forward intent section header
     - reference continuity section header
     - accepted compacted view section header
     - fallback/wait continuity section header
  2. 指定 inter-section separator（如 `\n\n` 或更显式的分隔符）并说明选择理由（token 效率、与 compact prompt 分隔符不冲突）
  3. 在 focused tests 中增加对 section header 文本的精确断言，防止 implementation agent 使用内部术语作为 header
- **修复风险（低/中/高）**: 低 — plan 只需补充具体 section title 列表和 separator 选择
- **严重程度（低/中/高/严重）**: 高 — 缺少 LLM-facing contract 的具体值，implementation agent 会自行发明，增加返工风险

### 2-未修复-中-selected recent window 中 evidence item 从原始交错位置移至 system envelope 头部，改变了 LLM 看到的对话连续性结构

- **位置**: plan §Design Source Updates Required Before Code §3 "role preservation"；plan §S7-R1-S1 "把非 system messages 保持原序输出"
- **问题类型**: 架构边界 / 契约缺失
- **当前写法**:
  - §3: "工具结果和 evidence 若不能作为 `tool` role 合法进入当前 Engine contract，则进入 system envelope 的业务可读 evidence section，而不是散落为多条 `SystemMessage`"
  - §S7-R1-S1: "从最终候选 messages 中抽取所有 `SystemMessage` 内容，按原相对顺序合并为一个 `SystemMessage`，再把非 system messages 保持原序输出"
- **反例/失败场景**:
  1. 当前 production code `_memory_selected_recent_window_messages()` (`run_input.py:2341-2366`) 按 selected recent window 的原始事件顺序输出 messages。evidence item（role 非 USER/ASSISTANT）被渲染为 `SystemMessage` 并保持其在窗口中的原始交错位置。例如：
     ```
     user: "请分析营收数据"
     system: "[evidence chunk E1.1: 营收数据表]"
     assistant: "营收增长主要来自价格因素"
     user: "刚才说的价格因素具体是多少？"
     ```
  2. plan 的合并方案会产出：
     ```
     system: "[envelope: ...evidence section: E1.1: 营收数据表...]"
     user: "请分析营收数据"
     assistant: "营收增长主要来自价格因素"
     user: "刚才说的价格因素具体是多少？"
     ```
  3. LLM 在读取第二条 `user` message 时，不再能看到 evidence 出现在 assistant answer 之前的连续性。对于依赖 evidence 出现位置来推断 "assistant 是根据哪个 evidence 得出的答案" 的模型，这可能降低答案质量。
  4. plan 没有分析这种位置变化对 compact quality、follow-up answer consistency 或 provider behavior 的影响。
- **为什么有问题**: plan 将 "合并所有 system message 到首位" 与 "保留非 system 对话连续性" 视为两个独立目标，但没有分析移除 evidence 原始交错位置对 LLM 理解对话流的潜在影响。当前 public smoke 的 red assertions 是基于 role count 的机械断言，不验证 LLM 行为正确性——合并后 role count 变绿，但 LLM 可能因 evidence 位置变化而给出不同质量的答案。
- **直接证据**:
  - `run_input.py:2341-2366` — selected recent window 中 evidence item 当前保持原始交错位置
  - plan §Goal: "若存在任何 system-scoped material，唯一 `SystemMessage` 必须位于最终 message list 的第一条" — 这强制所有 evidence 移到首位
  - plan §Non-Goals: "不修改 Engine / Runner 的 tool loop 或 provider adapter 语义" — 但未声明 LLM 行为变化 risk
- **影响**: LLM 在 follow-up 和 compact 场景下可能因 evidence 位置变化产生不同质量的答案；该变化在 mechanical smoke（只检查 role count）下不可见
- **建议改法和验证点**:
  1. 在 plan 中显式声明 selected recent window evidence 从原始交错位置移到 system envelope 是已知的语义变化。
  2. 在 residual risks 中记录该变化对 LLM 行为的影响为 unknown，需要在后续 real provider smoke 中采样验证。
  3. 或者考虑替代方案：保留 evidence item 在 selected recent window 中的原始位置，但改用非 system 的其他 role（如当前 Engine contract 不支持则记录为 deferred risk）。
  4. public smoke 在机械角色断言通过后，增加至少一个对 follow-up answer 中关键事实引用的语义检查（如验证 answer 中仍包含 evidence 中的关键数据点）。
- **修复风险（低/中/高）**: 低 — 主要是 plan 文档补充风险声明和验证点
- **严重程度（低/中/高/严重）**: 中 — 不影响 mechanical correctness，但可能影响 LLM 行为质量；变更在 smoke role-count 断言下不可见

### 3-未修复-中-internal ref 移除后替换文本欠规格，implementation agent 需自行决定 `policy_snapshot_ref` 和 `tool_call_id` 的 LLM-facing 替代措辞

- **位置**: plan §S7-R1-S1 "当前 `policy_snapshot_ref`、memory fact 的 `event_id` / `event_sequence` / `extraction_operation_ref` / internal evidence refs、wait continuity 的 `tool_call_id` 等内部字段不得继续进入 LLM-facing content；需要改为业务可读说明或 Host-neutral unavailable wording"
- **问题类型**: 不可直接实施
- **当前写法**: plan §S7-R1-S1 要求将 internal refs 改为 "业务可读说明或 Host-neutral unavailable wording"，但没有给出具体替换文本或替换规则。
- **反例/失败场景**:
  1. `run_input.py:1702` `policy_snapshot_ref={policy_snapshot.policy_snapshot_ref}` — 当前暴露给 LLM。plan 要求移除，但替代文本是什么？是直接删除该行（减少 Host execution context 信息量），还是替换为业务可读的 policy 描述（需要新增 policy description 字段），还是替换为 "policy applied"？
  2. `run_input.py:3171` `tool_call_id={...}` — wait continuity 中当前暴露 `tool_call_id` 给 LLM。替换为 "a tool call" 还是 "tool: {tool_name}" 还是完全移除？不同选择对 LLM 理解 wait/resume 上下文有不同影响。
  3. memory fact 中的 `event_id` / `event_sequence` — 当前可能出现在 memory section 渲染中。替换为什么？
  4. Implementation agent 在这些选择上的自由度意味着不同 agent 可能产出不同的 LLM-facing 文本，而 plan 中缺少对这些选择的约束。
- **为什么有问题**: plan 的 stop condition §S7-R1-S1 说 "如果某类 internal ref 无法在不丢业务语义的前提下改写为 LLM-readable wording，停止并列出该来源、字段和需要补的 durable atom"。这假设 "能否改写" 是二元的，但实际上改写有不同程度——从 "完全移除该行" 到 "替换为详细业务描述" 之间是连续的。plan 没有给出改写的充分性标准。
- **直接证据**:
  - plan §S7-R1-S1: "需要改为业务可读说明或 Host-neutral unavailable wording" — "或" 连接了两个不同级别的替换策略
  - plan §Stop Conditions: "LLM-facing content 仍包含 EventLog id、payload / artifact ref、digest、cursor、policy ref..." — 这是禁止项列表，但没有给出可接受替换的下限
  - `run_input.py:1702` 当前暴露 `policy_snapshot_ref`；`run_input.py:3171` 当前暴露 `tool_call_id`
- **影响**: implementation agent 可能选择过于激进的移除（丢失有用 context）或过于保守的保留（用模糊措辞掩饰而非真正移除 internal refs）
- **建议改法和验证点**:
  1. 对每类需要移除的 internal ref，在 plan 中给出替换策略：完全移除、替换为业务可读描述、或替换为 Host-neutral unavailable wording。
  2. 特别对 `policy_snapshot_ref` 和 wait continuity `tool_call_id` 给出具体替换文本。
  3. 在 focused tests 中增加对替换后 system envelope 包含必要业务语义的正面断言，而不只是检查 internal ref 不存在。
- **修复风险（低/中/高）**: 低 — 只需在 plan 中补充替换策略表
- **严重程度（低/中/高/严重）**: 中 — implementation agent 有自由度但方向明确（移除 internal refs），风险主要在替换质量而非正确性

### 4-未修复-低-manifest 验证与 "不读取 private durable table" 的 tension 对 focused test 设计构成约束

- **位置**: plan §S7-R1-S2 "添加 focused cases 覆盖...manifest `message_count` / `message_entries` / role digest 与 normalized messages 同源"；plan §S7-R1-S2 stop condition "如果 focused tests 只能通过读取 private durable table 才能证明 message shape，停止"
- **问题类型**: 测试缺口 / open question 未收敛
- **当前写法**: S7-R1-S2 要求 manifest 相关测试，但 stop condition 禁止 "只能通过读取 private durable table" 证明 message shape。
- **反例/失败场景**:
  1. `RunnerCallInputAssemblyManifest` 存储在 durable store 中（通过 payload descriptor / artifact）。读取 manifest 的 `message_count`、`message_entries`、`role_sequence_digest` 必然需要访问 durable store。
  2. 如果 "private durable table" 指的是直接读取 SQLite 表而不通过 Host public API，那么通过 `RunnerCallManifestRecorder` 或 public query API 读取 manifest 是否算 "private"？plan 没有澄清。
  3. 当前 public smoke 通过 `factory.requests[index].messages`（即 `AgentRunRequest.messages`）获取 messages，这是 public path。但 manifest 本身不是 public API 的一部分——它是 Host 内部 durable record。如果 tests 需要证明 manifest 与 messages 同源，就需要读取 manifest，而 manifest 的读取路径可能被视为 "private"。
- **为什么有问题**: plan 的两个要求之间存在 tension——证明 manifest 同源必然需要读取 manifest，而 manifest 存储位置可能触发 "no private durable table" stop condition。这可能导致 implementation agent 在实现测试时触发 stop condition 而无法完成 S7-R1-S2。
- **直接证据**:
  - plan §S7-R1-S2 expected changes: "manifest `message_count` / `message_entries` / role digest 与 normalized messages 同源"
  - plan §S7-R1-S2 stop condition: "如果 focused tests 只能通过读取 private durable table 才能证明 message shape，停止"
  - closeout plan appendix: manifest 存储在 durable payload descriptor / artifact 中
- **影响**: implementation agent 可能因无法在不读取 durable store 的情况下验证 manifest 而同源而触发 stop condition → S7-R1-S2 阻塞；或 implementation agent 绕过 stop condition 直接读取 durable table → 偏离 plan 边界
- **建议改法和验证点**:
  1. 在 plan 中澄清 "private durable table" 的边界：通过 `RunnerCallManifestRecorder` 的公开查询接口或 payload resolution API 读取 manifest 是否在允许范围内。
  2. 如果 manifest 读取不被视为 public path，将 manifest 验证移到单独的 focused durable test（使用允许读取 durable store 的测试入口），S7-R1-S2 只验证 public path messages 的 one-system-message 收敛。
- **修复风险（低/中/高）**: 低 — 只需澄清测试边界
- **严重程度（低/中/高/严重）**: 低 — 不影响 production correctness，但可能导致 test implementation 阶段的 confusion

### 5-未修复-低-合并点 boundedness 约束只声明了原则，没有指定 chunk 级截断或超限处理行为

- **位置**: plan §Design Source Updates Required Before Code §6 "boundedness"；plan §S7-R1-S1
- **问题类型**: 契约缺失
- **当前写法**:
  - §6: "合并为单条 system message 不能绕过既有 memory / compact / fallback char caps"
  - §6: "system envelope 只拼接已由各 provider 预算治理后的 bounded content；不得因为合并而重新展开旧 compact artifact、完整 memory snapshot 或 raw history"
- **反例/失败场景**:
  1. 各 provider（memory projection、compact view、fallback material）各自遵守自己的 char cap。但合并后总 system envelope 可能远大于任一单独 cap。例如 5 个 section 各 2000 chars → 合并后 10000+ chars system message。部分 provider（如 Anthropic）对 system message 长度可能有不同处理。
  2. plan 正确声明 "不得重新展开"，但没有说明如果合并后的 system envelope 超过某个总阈值（如 token budget 的 X%）应该怎么办。
  3. 当前各 provider 的 char cap 是独立治理的，合并后没有一个 "总 system envelope cap"——plan 是否隐含要求增加一个？如果是，cap 是多少？由谁设定？
- **为什么有问题**: plan 的 §6 boundedness 是一个正确的约束声明，但缺少 enforcement mechanism。"不能绕过" 是结果要求，不是实现指令。
- **直接证据**:
  - plan §6: "合并为单条 system message 不能绕过既有 memory / compact / fallback char caps" — 声明了约束但没有 enforcement
  - plan §S7-R1-S1 没有提到合并后的总长度检查或截断策略
- **影响**: 合并后 system envelope 可能异常大，在某些 provider 上触发意外行为；但当前由各 provider 独立 cap 保证，合并不会引入新内容——风险低
- **建议改法和验证点**:
  1. 在 plan 中声明合并本身不增加新内容，仅做拼接，因此不绕过各 provider 的独立 cap。
  2. 在 focused tests 中增加 system envelope 总大小 sanity check（如不超过各 section cap 之和）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低 — 现有各 provider cap 已提供足够保护

## Open Questions

1. **selected recent window evidence 位置变化是否影响 compact quality？** plan 将 evidence 从原始交错位置移到 system envelope 头部。当前 public smoke 只验证 mechanical role count，不验证 LLM 输出质量。需要在 plan 中显式声明这是已知 trade-off，并在 residual risks 中记录。

2. **合并后的 system message 是否需要总 token cap？** 当前各 provider 独立 cap 已限制各 section 大小，但合并后无总 cap。如果 8 个 section 各接近 cap，总 system message 可能非常大。

3. **`tool` role 是否未来用于 selected recent window evidence？** plan §Residual Risks 提到 "如果 design review 认为 `tool` role 应用于更多 historical evidence"。如果 Engine contract 未来支持在 historical window 中使用 `tool` role，evidence 可以保留原始交错位置且不增加 system count。plan 可以标注这是 forward-compatible 方向。

## Residual Risks

- **R1**: section title/separator 选择影响 LLM 行为 — plan 未指定具体值，implementation agent 自行决定。**建议跟踪**: S7-R1-S0 design.md 更新时最终确定。
- **R2**: evidence 位置变化影响 follow-up answer quality — mechanical smoke 不可见。**建议跟踪**: 后续 real provider smoke 中采样验证。
- **R3**: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 的 `policy`/`digest` 可能在未来 prompt 变更时误触发 — plan 已正确 defer。**建议跟踪**: 现有 WU-CM-01-F01 或后续 prompt work 中精确化 forbidden terms。

## Verdict

**pass-with-risks**

plan 的动机成立，root cause 定位准确，scope boundary 清晰，stop conditions 完整。三个 findings 均为可修复的规格不足问题，不改变 plan 的核心方向：

- Finding 1 (高): 需在 S7-R1-S0 的 design.md 更新中补充 section title/separator 具体值
- Finding 2 (中): 需在 plan residual risks 中声明 evidence 位置变化的已知 trade-off
- Finding 3 (中): 需补充 internal ref 替换策略表
- Finding 4 (低): 需澄清 manifest 验证的测试边界
- Finding 5 (低): boundedness 已有各 provider cap 保护，风险低

三个 findings 可以在 design.md 更新 (S7-R1-S0) 执行期间一并解决，不需要 plan 级别重写。建议 phaseflow controller 在接受 plan 时将 Finding 1 和 Finding 2 标记为 S7-R1-S0 design review 的必检项。
