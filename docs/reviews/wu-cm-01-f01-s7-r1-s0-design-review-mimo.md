# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-mimo.md`
- Included scope: `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`, accepted plan `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`, controller adjudication `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-controller-adjudication.md`
- Excluded scope: production code, tests, README
- Parallel review coverage: 无

## Accepted Finding Coverage Verification

| Controller Accepted Finding | Coverage Status | Evidence Location |
|---|---|---|
| 1. Concrete section titles / order / separator | **Covered** | `design.md:2552-2564` — nine-section fixed order, `## <title>` Markdown header format, `\n\n` separator, section title is business-readable. |
| 2. Selected recent evidence position trade-off | **Covered** | `design.md:2566` — explicit role-preservation-over-interleaving rule, accepted trade-off statement, future `tool` role strategy deferred to later work unit. |
| 3. Internal ref replacement table | **Covered** | `design.md:2568-2581` — replacement table for `policy_snapshot_ref`, `tool_call_id`, event ids, payload/artifact refs, digests, cursors, projector metadata, Attempt/execution ledger, scheduler state, Python/internal type names. Each entry specifies delete/replace strategy with acceptable alternative text. |
| 4. Manifest verification boundary | **Covered** | `design.md:2614-2616` — two-layer verification: public path smoke via `AgentRunRequest.messages` / `messages_seen`; focused durable manifest tests via manifest recorder or payload resolution helper. Explicit prohibition on using private SQLite table reads as public message shape proof. |
| 5. Boundedness enforcement / sanity | **Covered** | `design.md:2583` — merge-only rule, section cap preservation, header/separator overhead sanity, focused test requirement that merge adds no new business text. |

## Findings

### 1-未修复-中-System envelope section 4 与 section 8 的证据内容边界重叠

- **入口/函数**: S7-R1-S1 implementation（RunInput system envelope merge helper）
- **文件(行号)**: `docs/host/design.md:2559` (section 4), `docs/host/design.md:2563` (section 8)
- **输入场景**: 当 selected recent evidence 既属于 Evidence/Fact Memory 来源，又来自 deterministic recent-window fallback 时
- **实际分支**: section 4 描述为 "selected recent evidence 中不能合法使用 `tool` role 的 evidence material"；section 8 描述为 "deterministic recent-window fallback 中无法保留原 role 的 bounded tool / evidence material"
- **预期行为**: 每条 evidence material 应有唯一明确的 section 归属规则，实现者无需临场判断
- **实际行为**: 两条描述都涉及 "tool role 不兼容的 evidence material"，但来源描述不同（"selected recent evidence" vs "deterministic recent-window fallback"）。当 evidence 既通过 selected recent window 又通过 memory/fact pipeline 进入时，归属哪个 section 需要实现者额外推断
- **直接证据**: `design.md:2559` section 4 content source 包含 "Evidence / Fact Memory、accepted evidence-backed facts、selected recent evidence 中不能合法使用 `tool` role 的 evidence material"；`design.md:2563` section 8 content source 包含 "deterministic recent-window fallback 中无法保留原 role 的 bounded tool / evidence material"
- **影响**: 实现者可能对同一条 evidence 判定不同 section，导致 envelope section 归属不一致；测试难以覆盖所有组合
- **建议改法和验证点**: 在设计中明确 section 4 处理 memory/fact 来源的 evidence（包括已选入 memory 的 recent evidence），section 8 处理 deterministic recent-window fallback 中尚未进入 memory 的 evidence 以及 wait-resume 材料。或者明确 "selected recent evidence" 与 "recent-window fallback material" 是互斥来源
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-"cannot legally use tool role" 判断权威来源未指定

- **入口/函数**: RunInputBuilder system envelope merge helper
- **文件(行号)**: `docs/host/design.md:2550`, `docs/host/design.md:2566`
- **输入场景**: selected recent evidence 需要决定保留为 `tool` role message 还是移入 system envelope
- **实际分支**: 设计说 "若不能合法作为 `tool` role 进入当前 Engine contract，必须移入首条 system envelope"
- **预期行为**: 判断 "能否合法使用 tool role" 的权威来源应在设计中明确——是 RunInputBuilder 查询 Engine message contract、tool schema、RunnerSpec 还是静态 policy
- **实际行为**: 设计未指定谁做此判断、依据什么 contract。实现者需要自行决定：是否检查 Engine `AgentRunRequest` 的 role vocabulary、是否查询当前 provider adapter、或是否用静态规则（如 "historical evidence always goes to system envelope"）
- **直接证据**: `design.md:2550` 和 `design.md:2566` 使用 "不能合法" 但未定义 "合法" 的判断入口
- **影响**: 实现可能采用不同策略（保守全部进 system envelope vs 查询 Engine contract），导致行为在不同 provider 间不一致
- **建议改法和验证点**: S7-R1-S1 实现前在设计中明确：当前 Engine contract 不支持 historical `tool` role，因此所有 selected recent evidence 默认进入 system envelope；未来 Engine contract 变更时再重新评估。这与 `design.md:2566` 末尾的 "未来如果 Engine contract 支持 historical `tool` role" 一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-Boundedness sanity 缺少可测量边界

- **入口/函数**: S7-R1-S2 focused tests
- **文件(行号)**: `docs/host/design.md:2583`
- **输入场景**: focused tests 验证 system envelope merge 不引入新内容
- **实际分支**: 设计说 "总内容只等于非空 section 的 bounded rendered text 加固定 header / separator 开销"，使用 "sanity" 一词
- **预期行为**: boundedness 应有可测试的断言，例如 "merge 后总字符数 <= 各 section char cap 之和 + header/separator 开销"
- **实际行为**: "sanity" 是刻意模糊用词；设计只说 "至少断言 merge 没有引入候选 system messages 之外的新业务文本"，未要求量化总大小
- **直接证据**: `design.md:2583` "merge 后的总 envelope 大小 sanity 应满足：总内容只等于非空 section 的 bounded rendered text 加固定 header / separator 开销"
- **影响**: 测试可能只验证 "没有新内容" 但不验证 "总大小合理"，导致 merge 后 envelope 超出 provider token 限制时被 provider 层拒绝而非 Host 层拦截
- **建议改法和验证点**: 计划的成功信号已包含 "merge adds no new business text"，这足以证明 boundedness 本质。建议 S7-R1-S2 增加一条 sanity assertion：merge 后 message content 总字符数不超过 merge 前所有候选 system message content 总字符数加上固定 header/separator 开销。不需精确 token 计数
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 4-未修复-低-English section titles 在中文 LLM 上下文中的混合语言

- **入口/函数**: LLM 消费 system envelope
- **文件(行号)**: `docs/host/design.md:2554-2564`
- **输入场景**: 中文财报分析 agent 的 ordinary RunInput system envelope
- **实际分支**: 九个 section title 使用 English（`Task Instructions`, `Execution Guidance`, `Conversation Summary` 等）
- **预期行为**: section title 是 LLM-facing 业务可读标题；agent 上下文和财报内容均为中文
- **实际行为**: English section titles 在中文 prompt 中创建混合语言 envelope。LLM 是多语言的，English titles 更稳定且无歧义，但与 "业务可读" 约束的 "业务" 语义存在轻微张力
- **直接证据**: `design.md:2554-2564` section title 列表全部为 English
- **影响**: 低。LLM 能正确理解 English section headers in Chinese context。但若未来需要更严格的中文 LLM-facing 语义，需要重新评估
- **建议改法和验证点**: 当前 English titles 是可接受的设计选择，稳定性优于中文翻译歧义风险。若需要中文，应在 design gate 决策而非 implementation 中变更。无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。上述 finding 均可在 S7-R1-S1 implementation 前通过设计澄清或实现时直接解决，不阻塞 implementation 启动。

## Residual Risk

- S0 变更包含大量超出五个 accepted finding 的增量设计内容（runner-call manifest full contract、tool call arguments atom、tool trace consumption boundary、compactor runner-call identity）。这些内容来自 closeout chain 已接受的 design contract slices，是增量补充而非 S0 特有 scope creep。codex artifact 已确认这些来自已接受的 closeout chain work units。
- 设计未覆盖 system envelope 的 provider-specific 格式偏好差异（如 OpenAI vs Anthropic 对 system message 长度/格式的隐式偏好）。计划 residual risks 已记录此项，由后续 provider matrix smoke 覆盖。
- `issues-implementation-control.md` 的 `active work unit` 字段同时列出四个 work unit（`WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01`），但表格结构设计为单值。这是控制文档的展示问题，不影响 implementation。

## Verdict

S0 design sync 覆盖了全部五个 controller accepted findings，实现可以启动。上述四个 findings 中，finding 1（section 4/8 边界）应在 S7-R1-S1 实现前通过设计澄清解决；finding 2-4 为低严重度，可在实现时直接处理。
