# Design Review — WU-CM-01-F01-S7-R1-S0 Design Contract Sync

## Metadata

- **review target**: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md` (S0 implementation artifact) and associated `docs/host/design.md` unstaged changes
- **work unit**: `WU-CM-01-F01-S7-R1`
- **gate**: S7-R1-S0 review
- **review type**: adversarial design review (post-S0, pre-S1 production code)
- **plan artifact**: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- **plan review**: `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-ds.md`
- **controller adjudication**: `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-controller-adjudication.md`
- **S0 implementation artifact**: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`
- **design source**: `docs/host/design.md` (unstaged changes at lines 1446-1448, 2550-2583, 2614-2616, 3050-3052)
- **control source**: `docs/host/issues-implementation-control.md` (unstaged changes)
- **branch**: `phaseflow/wu-dur-obs-cm-closeout`
- **review timestamp**: 2026-06-05T17:33:09+08:00
- **review artifact**: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-ds.md`

## Scope

- **Mode**: design contract sync review (S7-R1-S0 gate)
- **Base**: main
- **Included scope**:
  - `docs/host/design.md` unstaged changes: one-system-message hard contract (§23), section title/order/separator table, role preservation trade-off, internal ref replacement table, boundedness sanity, manifest alignment rules, manifest verification boundary, Conversation Memory Prompt Assembly rules (§24)
  - `docs/host/issues-implementation-control.md` unstaged changes: gate status update, S0 artifact registration, inspection note update
  - `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`: S0 self-assessment of accepted finding coverage
  - Cross-reference with accepted plan and controller adjudication for finding coverage verification
- **Excluded scope**:
  - `tests/` unstaged changes (pre-existing from Slice 7 retry, not S0 scope)
  - Committed changes in `docs/host/design.md` lines 1446-1448 (from prior WU-DUR-P01 slices)
  - Production code, test logic, pyright, pytest results (S0 is design-only gate)
- **Parallel review coverage**: 无（单 reviewer 全量覆盖）

## Accepted Finding Coverage Verification

Controller adjudication (`docs/reviews/wu-cm-01-f01-s7-r1-plan-review-controller-adjudication.md`) accepted 5 mandatory findings for S7-R1-S0. Below is the evidence-based coverage verdict for each.

### F1 (high): Concrete section titles / order / separator

- **Controller requirement**: "S7-R1-S0 design sync must define concrete LLM-facing section titles, ordering, and separators before S7-R1-S1 code changes. Implementation must not invent these values ad hoc."
- **Direct evidence**: `docs/host/design.md` lines 2552-2564.
- **What the design now specifies**:
  - 9 sections with exact English titles in fixed order (1. Task Instructions, 2. Execution Guidance, 3. Conversation Summary, 4. Verified Evidence and Facts, 5. Prior Answer Anchors, 6. Open Follow-up Context, 7. Reference Continuity, 8. Recent Evidence, 9. Resume Guidance)
  - Header format: `## <title>` (Markdown H2)
  - Inter-section separator: exactly `\n\n`
  - Empty sections omitted; non-empty sections rendered in order
  - Each section has a defined content source and rendering rule
- **Verdict**: **COVERED**. Section titles, order, and separator are concrete and not left to implementation invention. See Finding 1 for a minor specification gap on header-to-content spacing.

### F2 (medium): Selected recent evidence position trade-off

- **Controller requirement**: "S7-R1-S0 must state that moving system-scoped selected recent evidence into the single system envelope changes its original interleaved position. The design must either accept that trade-off with validation coverage or choose another role strategy before implementation."
- **Direct evidence**: `docs/host/design.md` lines 2566.
- **What the design now specifies**:
  - Explicit statement: "该选择会把原本夹在历史 user / assistant turn 中间的 evidence 提前到 system envelope 内，是被接受的 trade-off"
  - Trade-off rationale: "它用稳定的 provider-independent one-system-message shape 换取 evidence 原始交错位置的弱化"
  - Validation requirement: "实现必须用 public path smoke 证明 role shape 收敛，并用 focused tests 证明 follow-up 仍能读取 evidence 中的关键业务文本"
  - Forward-compatibility note: "未来如果 Engine contract 支持 historical `tool` role，可在后续 work unit 中重新评估"
- **Verdict**: **COVERED**. Trade-off is explicitly accepted with validation coverage and forward-compatibility path.

### F3 (medium): Internal ref replacement table

- **Controller requirement**: "S7-R1-S0 must include a replacement table for `policy_snapshot_ref`, `tool_call_id`, event ids, payload/artifact refs, digests, cursors, projection metadata, and other LLM-facing internal fields. Each entry must say remove, replace with business text, or replace with Host-neutral unavailable wording."
- **Direct evidence**: `docs/host/design.md` lines 2568-2581.
- **What the design now specifies**:
  - 10-row replacement table covering: `policy_snapshot_ref`, `tool_call_id`, EventLog event id/sequence, payload/artifact refs/descriptors, digests, cursors/boundaries/checkpoints, projector metadata, Attempt/execution ledger, scheduler/lane/worker state, Python/internal type names
  - Each row has: internal field identifier, LLM-facing strategy (删除/remove), acceptable replacement text
  - Catch-all rule: "未列出的内部 ref / ledger 字段按同类最严格规则处理"
  - Boundary rule: "可进入 manifest、Tool Trace、audit、diagnostic 或 payload descriptor 的 internal refs，不得作为模型阅读材料进入 system envelope、selected recent window 或 current input"
- **Verdict**: **COVERED**. All controller-required categories are addressed with concrete strategies. See Finding 2 for a note on composite message restructuring.

### F4 (low): Manifest verification boundary

- **Controller requirement**: "S7-R1-S0 or the implementation report must distinguish public-path message assertions from focused durable manifest assertions."
- **Direct evidence**: `docs/host/design.md` lines 2616.
- **What the design now specifies**:
  - Layer 1: "public path smoke 只能通过实际 public request / scripted runner `messages_seen` 证明 ordinary runner call 至多一条 system message"
  - Layer 2: "focused durable manifest tests 可以通过 manifest recorder 或 payload resolution helper 读取 manifest，证明 manifest 与 normalized final messages 同源"
  - Negative constraint: "focused manifest tests 不得把直接读取私有 SQLite table 当作证明 public message shape 的替代路径"
- **Verdict**: **COVERED**. Two-layer boundary is explicit about what each test layer can prove and what it cannot.

### F5 (low): Boundedness enforcement / sanity

- **Controller requirement**: "S7-R1-S0/S1 must state that merging does not add new content and must add a sanity assertion for merged envelope size or section cap preservation."
- **Direct evidence**: `docs/host/design.md` lines 2583.
- **What the design now specifies**:
  - Merge-only rule: "system envelope merge 只能合并已经由各 input provider / projection policy 治理后的 bounded content，不得新增、展开或重新召回内容"
  - Cap preservation: "实现必须保留各 section 原有 item cap、char cap、selected recent window cap、floor 和 compact / fallback budget 约束"
  - Size sanity: "merge 后的总 envelope 大小 sanity 应满足：总内容只等于非空 section 的 bounded rendered text 加固定 header / separator 开销"
  - Cap failure handling: "若某 section 在 merge 前已超出其 provider cap，必须在 provider 边界 fail closed 或截断；merge helper 不得用新的全局截断掩盖上游 cap 失效"
  - Test requirement: "focused tests 必须覆盖 section cap preservation 或总大小 sanity，至少断言 merge 没有引入候选 system messages 之外的新业务文本"
- **Verdict**: **COVERED**. Merge-only rule, cap preservation, sanity check, and test requirement are all specified.

## Findings

### 1-未修复-低-Section 4 "Verified Evidence and Facts" 将 memory 已校验事实与 selected recent evidence 合并到同一 section，模型无法通过 section title 区分 provenance

- **入口/函数**: `docs/host/design.md` lines 2559 (section 4 渲染规则) 与 line 2566 (role preservation trade-off)
- **文件(行号)**: `docs/host/design.md:2559`, `docs/host/design.md:2566`
- **输入场景**: 正常 public RunInput（非 fallback），存在 Evidence/Fact Memory 中的已校验事实，同时 selected recent window 中存在无法使用 `tool` role 的 evidence material
- **实际分支**: 两类 material 都进入 section 4 "Verified Evidence and Facts"
- **预期行为**: 模型应能区分"经过 memory verification pipeline 的已校验事实"与"从 selected recent window 移入的原始 evidence"
- **实际行为**: 两类材料在同一个 "Verified Evidence and Facts" section 中呈现，section title 暗示所有内容都是 "verified"；模型仅依赖 prompt-local source label（格式未在设计中具体化）来区分 provenance
- **直接证据**:
  - line 2559: section 4 内容来源 = "Evidence / Fact Memory、accepted evidence-backed facts、selected recent evidence 中不能合法使用 `tool` role 的 evidence material"
  - line 2559: 渲染规则要求 "prompt-local source label"，但设计未指定 label 格式（如 `[Verified Fact]` vs `[Recent Evidence]` vs `Source E1`）
  - line 2566: trade-off 声明只讨论了 evidence 位置变化，未讨论 verified vs raw provenance 区分
- **影响**: 模型可能将 raw selected recent evidence 误加权为 "verified fact"，尤其在 source label 格式不够显式区分时；follow-up answer 质量可能受影响，且该变化在 mechanical smoke（只检查 role count）下不可见
- **建议改法和验证点**:
  1. 在 section 4 渲染规则中显式要求 source label 区分 "Verified Fact" 与 "Recent Evidence" 两类 provenance
  2. 或在设计中将 selected recent evidence 统一路由到 section 8 "Recent Evidence"，section 4 只保留 memory-stored verified facts
  3. focused tests 增加对 section 4 中 source label 区分 provenances 的断言
- **修复风险（低/中/高）**: 低 — 仅需澄清渲染规则或调整路由策略，不改变整体 one-system-message 方向
- **严重程度（低/中/高/严重）**: 低 — 有 prompt-local source label 作为缓解，且模型通常能从内容本身推断可信度；但在极端场景（大量 evidence + 少量 verified facts）下可能引起模型权重偏差

### 2-未修复-低-内部字段替换表覆盖了独立字段，但未指导如何将复合 Host execution context 消息整体改写为业务可读形式

- **入口/函数**: `docs/host/design.md` lines 2568-2581 (replacement table)；对照 plan §Direct Evidence `run_input.py:1707`（当前 Host execution context 以独立 SystemMessage 包含 `policy_snapshot_ref` 及多项执行状态）
- **文件(行号)**: `docs/host/design.md:2568-2581`
- **输入场景**: S7-R1-S1 实现需要把 `run_input.py:1707` 处当前包含 `policy_snapshot_ref`、执行状态等复合信息的 Host execution context SystemMessage 改写为纯业务可读的 "Execution Guidance" section
- **实际分支**: replacement table 对 `policy_snapshot_ref` 的替换策略是 "删除 ref；如模型需要知道行为约束，只保留 Host-neutral 业务规则"，示例为 "Use the available context and tools under the current run limits."
- **预期行为**: 实现需要把整段 Host execution context（不仅包含 `policy_snapshot_ref`，还包含其他执行元数据）改写为纯业务规则文本
- **实际行为**: replacement table 是 per-field 替换策略，但当前 `run_input.py:1707` 处的消息是一个复合文本块；实现需要自行判断整个消息中哪些部分属于"业务规则"、哪些属于"内部状态"、整体改写后的消息应该多长
- **直接证据**:
  - plan §Direct Evidence: `run_input.py:1707` — "Host execution context 当前以独立 `SystemMessage` 进入 RunInput，且内容包含 `policy_snapshot_ref`"
  - design.md line 2557: section 2 "Execution Guidance" 渲染规则为 "只写模型需要遵守的业务动作和限制；不得暴露 policy snapshot ref、Attempt / execution ledger 或调度状态"
  - design.md lines 2568-2581: replacement table 对 `policy_snapshot_ref` 的替换文本是一行短示例，不是对整段 Host execution context 消息的改写指导
- **影响**: implementation agent 在 S7-R1-S1 需要自行判断 Host execution context 消息的整体改写策略；选择过于激进（只保留一行示例文本）可能丢失有用运行约束，选择过于保守可能保留内部状态痕迹。这是实现自由度问题，不影响设计正确性
- **建议改法和验证点**:
  1. 在 design.md 或 S7-R1-S1 stop condition 中注明：如果 Host execution context 包含无法归约为纯业务规则的运行约束，必须停止并列出具体字段
  2. focused tests 验证 "Execution Guidance" section 不包含 policy ref、ledger 字段、调度状态
- **修复风险（低/中/高）**: 低 — S7-R1-S1 stop condition 已覆盖"无法改写则停止"的情况
- **严重程度（低/中/高/严重）**: 低 — replacement table + section 2 渲染规则 + stop condition 三层保护已足够；实现有自由度但方向明确

### 3-未修复-低-Section title 文本在 §23（RunInputBuilder table）与 §24（Conversation Memory mapping）两处重复硬编码，存在未来 drift 风险

- **入口/函数**: `docs/host/design.md` lines 2554-2564 (§23 section title table) 与 lines 3052 (§24 Conversation Memory section header mapping)
- **文件(行号)**: `docs/host/design.md:2554-2564`, `docs/host/design.md:3052`
- **输入场景**: 未来 design 维护者在 §23 的 section title table 中修改某个 title（如 "Verified Evidence and Facts" → "Evidence and Facts"），但忘记同步更新 §24 中的对应字符串
- **实际分支**: §24 line 3052 写有 "Conversation Memory section header 必须使用 23 节固定的 LLM-facing title"，随后将 5 个 title 字符串 inline 写出（"Session Summary Memory 进入 `Conversation Summary`，Evidence / Fact Memory 进入 `Verified Evidence and Facts`..."）
- **预期行为**: section title 的真源只有一处（§23 table），§24 只引用不重复
- **实际行为**: §24 同时包含规范性引用（"必须使用 23 节"）和 title 字符串 inline 重复；如果未来只改 §23 table 而漏改 §24 inline 字符串，§24 中的示例 title 会与 §23 真源不一致
- **直接证据**:
  - line 3052: "Session Summary Memory 进入 `Conversation Summary`，Evidence / Fact Memory 进入 `Verified Evidence and Facts`，Answer Anchor Memory 进入 `Prior Answer Anchors`，Forward Intent Memory 进入 `Open Follow-up Context`，reference continuity items 进入 `Reference Continuity`"
  - 这些字符串与 line 2556-2564 table 中的 section title 列完全重复
- **影响**: 低概率的文档维护 drift——不影响 production 行为（production code 应读取 §23 table 或模块级常量），但可能误导未来的 design reader
- **建议改法和验证点**:
  1. §24 line 3052 改为纯引用形式，不 inline 重复 title 字符串，例如 "Conversation Memory 各 section 的 LLM-facing header 必须使用 23 节 system envelope section table 中对应的固定 title"
  2. 或保留当前 inline 形式但在 §23 table 旁加注 "本表是 section title 的唯一真源"
- **修复风险（低/中/高）**: 低 — 仅涉及文档文本调整
- **严重程度（低/中/高/严重）**: 低 — 不影响 production 正确性，仅影响文档长期可维护性

## Open Questions

1. **prompt-local source label 的具体格式是否需要进入设计契约？** 设计在 section 4 和 replacement table 中多次提到 prompt-local label（如 `Source E1`），但未指定格式。如果不同 implementation agent 或未来维护者选择了不同的 label 格式，可能导致 LLM-facing 文本风格不一致。当前 risk 低，因为 label 格式是 rendering 细节，不影响 contract correctness。

2. **`## <title>` Markdown 格式在不同 provider 上的行为差异是否需要更早验证？** 设计选择 Markdown H2 作为 section header 格式，不同的 LLM provider 对 system message 中的 Markdown 结构可能有不同的 tokenization 和注意力分配策略。当前 plan residual risks 已记录此风险，并 defer 到 real provider smoke。是否需要在 S7-R1-S1 实现前做至少一个 provider 的 manual sniff test？

## Residual Risk

- **R1**: Evidence 位置变化对 follow-up answer 质量的影响在 mechanical smoke 下不可见 — 已在 design.md line 2566 声明为 accepted trade-off，plan residual risks 记录 defer 到 real provider smoke。**当前 gate 不要求解决**。
- **R2**: 合并后 system envelope 总大小未设硬 cap — design.md line 2583 要求 sanity check（总大小 = section bounded content + header/separator overhead），但未指定总大小告警阈值。plan 的 residual risks 已记录此风险。**当前 gate 不要求解决**。
- **R3**: Section title 字符串在两处重复 — 见 Finding 3。**低影响，可 deferred**。
- **R4**: S0 codex artifact 的 self-assessment 表（lines 54-60）声称覆盖了所有 5 个 accepted findings，但未对每个 finding 提供 design.md 中的具体行号引用。当前 review 已验证所有覆盖，但 artifact 自身的可审计性可以通过添加行号引用来加强。**不影响 gate 通过**。

## Verdict

**pass — 可以进入 S7-R1-S1 production implementation gate**

S7-R1-S0 design contract sync 实质性覆盖了 controller adjudication 的全部 5 个 accepted findings：

- Finding 1 (high): 9-section table with exact titles, order, `## <title>` format, and `\n\n` separator — **covered**
- Finding 2 (medium): Explicit trade-off acceptance with validation coverage and forward-compatibility path — **covered**
- Finding 3 (medium): 10-row internal ref replacement table with per-field strategy and acceptable replacement text — **covered**
- Finding 4 (low): Two-layer manifest verification boundary (public smoke vs focused durable tests) — **covered**
- Finding 5 (low): Merge-only rule, cap preservation, size sanity, and focused test requirement — **covered**

三个 low-severity findings 均不阻塞 S7-R1-S1 进入 implementation：
- Finding 1 (section 4 provenance conflation) 有 prompt-local source label 作为缓解
- Finding 2 (composite message restructuring) 有 S7-R1-S1 stop condition 保护
- Finding 3 (title string duplication) 仅影响文档长期维护，不影响 production 行为

设计契约的 concrete level 足以支撑 S7-R1-S1 实现：section title、顺序、分隔符、角色保留规则、内部字段替换策略、manifest 对齐规则和验证边界均已指定。实现不会需要"发明"契约，仅在 rendering 细节（prompt-local label 格式、merge 算法实现）上有合理的实现自由度。

S7-R1-S1 进入前建议确认：
1. 当前 working tree 中 tests/ 的 unstaged 修改（来自 Slice 7 retry）是否需要先 commit 或 revert，避免与 S7-R1-S2 的 focused test 变更混淆
2. `dayu/host/run_input.py` 当前代码与 S0 设计之间的 gap 是否需要先做一次 code-to-design mapping 再开始实现
