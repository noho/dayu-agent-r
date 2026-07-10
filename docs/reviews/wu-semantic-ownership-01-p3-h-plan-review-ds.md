# WU-SEMANTIC-OWNERSHIP-01 P3-H Plan Review — AgentDS

## Review metadata

- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- **Date**: 2026-07-11 06:16:19 CST
- **Gate**: plan review (adversarial)
- **Review type**: adversarial plan review; no production code, tests, or docs edited outside this artifact
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Goal artifact**: `docs/reviews/wu-semantic-ownership-01-p3-h-goal-confirmation.md`
- **Adjudication**: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- **Source findings**: `docs/reviews/2026-07-10-semantic-ownership-drift-review.md` (BI-2..BI-6), `docs/reviews/repo-review-20260710-091608.md` (finding 12)

## Scope

Adversarial plan review only. Required lenses: architecture boundary, best practice, optimal solution, overengineering, overcoupling, test gaps, source finding disposition correctness, slice count/cost. Special attention areas: Fins direct runtime ownership claim, Web public output contract implementability, source scan brittleness, DS12 disposition proof.

## Assumptions tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | Provider/downloader/adapter modules are NOT the owner of LLM-facing prose or user-visible copy | Confirmed — see code evidence below |
| A2 | A small projection text helper per boundary is sufficient; no localization framework needed | Confirmed — plan scope is minimal |
| A3 | Three slices cover all semantic owner boundaries without coupling distinct concerns | Confirmed with one refinement (see Finding 2) |
| A4 | `SearchWebOutput` type can be moved to projection helper without breaking public tool JSON | Partially confirmed — stop condition provides safety net but migration path underspecified (Finding 3) |
| A5 | DS12 hidden hint protocol is already closed in current code | Confirmed — source scan zero hits (Finding 1 below) |
| A6 | Fins `direct_events.py` is the contract shape owner but NOT the text-content owner | Confirmed (Finding 4 below) |
| A7 | Source scans serve as definitive validation of cleanup completeness | Partially confirmed — scans are structural smell checks, not correctness proofs (Finding 5) |

## Findings

### 1-DS12-EVIDENCE-VALID-中-DS12证据无效判定成立

- **位置**: Plan §Source finding dispositions, DS12 row; Goal artifact §Non-goals
- **问题类型**: 源发现处置正确性
- **当前写法**: Plan 将 DS12 标记为 `evidence-invalid for P3-H`，理由是 "Current source scan found no `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, no `_hint_with_diagnostic_refs`, and no `hint=policy_decision.reason_code`"
- **反例/失败场景**: 无。本 finding 是确认性 finding（确认 DS12 处置正确），不是反驳性 finding。
- **为什么有问题**: 用户要求验证 DS12 evidence-invalid 判定是否充分证明。需要独立确认。
- **直接证据**:
  - 独立 source scan 结果：`rg -n "_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_hint_with_diagnostic_refs|hint=policy_decision\.reason_code" dayu tests` → **零命中**
  - P3-E 已删除这些符号：controller adjudication §P3-E 确认 "Separate governance reason and diagnostic refs from LLM-facing `hint` text if direct code inspection confirms the hidden string protocol is still present" — 但当前代码已无这些符号，说明 P3-E 已执行删除
  - Goal artifact §Non-goals: "Do not reopen DS12 Host ToolRuntime hidden hint protocol unless new direct code evidence shows it still exists" — plan 遵守此约束
- **影响**: DS12 处置正确；P3-H 无需处理 DS12
- **建议改法和验证点**: 保持当前处置。plan 中的 regression scan（`rg -n "_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|..."` dayu tests）作为 S3 验证的一部分已足够
- **修复风险（低）**: 无修复需要
- **严重程度（中）**: 确认性 finding，不影响 plan 质量

### 2-UNCLEAR-BOUNDARY-中-S2-Fins-direct-event-text-helper-owner边界模糊

- **位置**: Plan §Implementation slices S2, §Design alignment
- **问题类型**: 架构边界
- **当前写法**: Plan 声称 `direct_event_text.py` "owns: Direct result titles, Direct progress messages, Direct failure messages, Wait-resolution failed hint and cancelled message/hint"。同时说明 helper "may import `FinsErrorKind`, `FinsOperationKind`, and `FinsResultStatus` from `dayu.fins.direct_events`"。stop condition 说 "If a direct runtime string is both durable machine state and user-visible projection, first identify the consumer path."
- **反例/失败场景**: 实现 agent 可能对 helper 的角色产生两种不同理解，导致设计不一致：
  - 理解 A（纯文本常量模块）：helper 只导出 `str` 常量，`ingestion_runtime.py` 仍然自行选择哪个常量用于哪个场景。此时 runtime 仍然是事实上的 projection owner，只是文本集中存储了。
  - 理解 B（投影辅助函数模块）：helper 导出 `def download_failure_title(...) -> str` 等类型化函数，封装了状态到文本的映射逻辑。此时 helper 是真正的 projection owner。
- **为什么有问题**: Plan 的 "owns" 措辞暗示理解 B，但 helper 的允许 import 列表只包含枚举类型（`FinsErrorKind`, `FinsOperationKind`, `FinsResultStatus`），不包含 `FinsEvent`, `FinsResultSummary`, `FinsProgress`。这暗示理解 A。如果 implementation agent 选择了错误的解释，会导致：
  - 选 A 但 plan 要的是 B：projection 逻辑仍然分散在 runtime 中，语义所有权目标未达成
  - 选 B 但 plan 要的是 A：helper 过度膨胀，引入对 `FinsEvent` 的构造依赖
- **直接证据**:
  - `direct_events.py:244-247` — `FinsResultSummary` 已经定义 `title: str` 和 `error_message: str | None` 字段，且通过 `_validate_safe_text` 校验。这些字段是用户可见文本的容器。
  - `ingestion_runtime.py:181-184` — `_DIRECT_CANCELLED_MESSAGE`, `_DIRECT_FAILURE_TITLE`, `_DIRECT_SUCCESS_TITLE`, `_DIRECT_ERROR_TEXT_FALLBACK` 是模块级常量。Plan 的 S2 将其移入 `direct_event_text.py`。
  - Plan §S2 allowed changes: "Replace direct event title/message/error-message literals in direct-stream result/progress paths with calls/constants from `direct_event_text.py`" — "calls/constants" 的措辞本身就包含了两种可能性。
- **影响**: 实施 Agent 可能跑偏，需要自行判断 helper 的设计粒度
- **建议改法和验证点**: 在 plan S2 中显式声明 `direct_event_text.py` 的接口形态。推荐选择：纯文本常量模块 + 少量 key-based lookup 函数（如 `def direct_result_title(status: FinsResultStatus, operation: FinsOperationKind) -> str`），不构造完整 `FinsEvent` 对象。这样既不重复 `direct_events.py` 的契约形状所有权，又把文本映射逻辑集中管理。验证点：helper 模块不 import `FinsEvent` / `FinsResultSummary` / `FinsProgress`
- **修复风险（低）**: 在 plan 中加一句话澄清即可
- **严重程度（中）**: 可能导致实施偏差，但不阻塞 plan 推进

### 3-UNDERSPECIFIED-TYPE-MIGRATION-中-S1-SearchWebOutput-类型迁移路径欠规格

- **位置**: Plan §Implementation slices S1, §Contract/schema changes, §Risks
- **问题类型**: 不可直接实施
- **当前写法**: Plan 说 `web_search_providers.py` 中 "Replace `SearchWebOutput` with a provider-owned output type containing only `query`, `domains`, `total`, `preferred_result`, and `results`"，同时 `web_search_projection.py` "Own the current LLM-facing `SearchWebOutput` shape"。风险章节承认 "tests or downstream code may rely on `SearchWebOutput` type from `web_search_providers.py`"
- **反例/失败场景**: Implementation agent 需要自行决定以下问题：
  1. 新的 provider-owned 类型叫什么？（如 `SearchWebProviderFacts`）
  2. `web_tools.py:108` 当前 `from .web_search_providers import SearchWebOutput` — 改为从 `web_search_projection` import？
  3. `tests/tools/web/test_web_tools_provider.py` 当前 `-> web_search_providers.SearchWebOutput` 类型注解 — 改为指向 projection 模块？
  4. `_search_web_business` 函数（`web_tools.py:1492`）当前返回 `SearchWebOutput` — 改为返回什么类型？中间类型？
  5. 如果 `web_search_projection.py` 同时定义旧的 `SearchWebOutput`（LLM-facing）和新的构造逻辑，它是否需要 import provider-owned 类型？这创建了 projection → provider 的依赖方向，是合理的（projection 消费 provider facts）
- **为什么有问题**: Plan 声称是 "code-generation-ready"，但类型迁移路径的多个关键决策点留给 implementation agent。如果 agent 做错决策（如创建兼容别名），会违反 CLAUDE.md 的 "禁止兼容性代码" 约束。
- **直接证据**:
  - `web_tools.py:108` — `from .web_search_providers import ..., SearchWebOutput`
  - `tests/tools/web/test_web_tools_provider.py` — 多处 `-> web_search_providers.SearchWebOutput` 类型注解
  - Plan §Contract changes: "Provider-internal search output shape may shrink to raw facts. If type names change, update imports and tests directly; do not add compatibility re-exports or wrapper aliases."
- **影响**: 实施 Agent 可能引入不必要的中间类型或错误依赖方向
- **建议改法和验证点**: 在 plan S1 的 "Exact allowed changes" 中显式声明：
  - 新 provider 类型名称（建议 `SearchWebProviderResult` 或 `SearchWebRawFacts`）
  - `web_search_projection.py` 的 `build_search_web_output(provider_result: NewType) -> SearchWebOutput` 函数签名
  - `_search_web_business` 的新返回类型（建议直接返回 provider facts type，在调用方做 projection）
  - import 迁移路径：`web_tools.py` 从 `web_search_providers` import provider type，从 `web_search_projection` import `SearchWebOutput` + builder
- **修复风险（低）**: 在 plan 中补充类型名称和 import 路径即可
- **严重程度（中）**: 可能导致实施返工

### 4-FINS-OWNERSHIP-CONFIRMED-低-Fins-direct-runtime-所有权判定正确

- **位置**: Plan §Goal, §First-principles judgment, §Design alignment
- **问题类型**: 架构边界（确认性 finding）
- **当前写法**: Plan 将 Fins direct-stream visible text 的所有权从 `ingestion_runtime.py` 移出，归于 "Fins direct/wait projection helper"。Goal artifact 说 "Fins direct event/projection boundary owns reusable direct-stream user-visible labels, titles, and bounded messages shared by Service/CLI and direct runtime."
- **反例/失败场景**: 用户特别关注 "whether the plan wrongly treats Fins direct runtime as non-owner despite direct_events declaring user-visible text"。需要独立验证。
- **为什么有问题**: 需要独立确认 plan 是否正确区分了 `direct_events.py` 的契约形状所有权和 `ingestion_runtime.py` 的文本内容所有权。
- **直接证据**:
  - `direct_events.py:229-277` — `FinsResultSummary` 定义 `title: str`, `error_message: str | None` 字段，通过 `_validate_safe_text` 校验。这是**契约形状所有权**：`direct_events.py` 定义用户可见事件的字段名、类型、长度约束和安全规则。
  - `direct_events.py:186-226` — `FinsProgress` 定义 `stage: str`, `completed_units`, `total_units`。同样是契约形状。
  - `direct_events.py:280-299` — `FinsEvent` 定义 `message: str`, `event_type`, `operation_kind` 等。契约形状。
  - `ingestion_runtime.py:181-184` — `_DIRECT_CANCELLED_MESSAGE = "操作已取消"`, `_DIRECT_FAILURE_TITLE = "操作失败"`, 等。这是**文本内容所有权**在当前代码中的实际位置。
  - `ingestion_runtime.py:2791,2810,2849,2868,2907,2918,2932,2954` — 具体中文字符串如 `"下载准备中"`, `"下载失败"`, `"预处理准备中"` 等。
  - `direct_events.py` **不定义**这些中文字符串。它只定义字段的容器类型。
- **分析**: Plan 的判定是正确的。`direct_events.py` 拥有"用户可见事件应该有哪些字段、字段类型是什么、长度/安全约束是什么"——这是契约形状所有权。`ingestion_runtime.py` 当前拥有"具体中文字符串是什么"——这是文本内容所有权。Plan 将文本内容所有权移至 `direct_event_text.py`，但保持 `direct_events.py` 的契约形状所有权不变。Plan **没有**错误地将 `direct_events.py` 标记为 non-owner。相反，它正确识别了两个不同的所有权维度。
- **影响**: 无。Plan 判定正确。
- **建议改法和验证点**: 在 plan S2 中显式声明 helper 不替代 `direct_events.py` 的契约形状所有权，helper 只提供文本内容。验证点：helper 不重新定义 `FinsEvent`/`FinsResultSummary`/`FinsProgress` 的字段或校验逻辑
- **修复风险（低）**: 无修复需要
- **严重程度（低）**: 确认性 finding

### 5-SOURCE-SCAN-BRITTLENESS-低-源码扫描作为验证手段存在结构性脆弱

- **位置**: Plan §Implementation slices S3, required source scans
- **问题类型**: 测试缺口
- **当前写法**: Plan 的 aggregate validation 依赖 8 个 `rg` 命令扫描特定中英文字符串。例如 `rg -n "请检查 Fins ingestion|如仍需要该财报资料|Fins operation was cancelled before completion|下载准备中|预处理准备中|..." dayu/fins/ingestion_runtime.py dayu/fins/ingestion/wait_adapter.py`
- **反例/失败场景**:
  1. **假阴性**：如果有人在被扫描文件中新增了不在模式中的中英文 prose（如新的操作阶段 `"校验准备中"`），扫描不会捕获。扫描只检测已知字符串。
  2. **误判为通过**：如果实现 agent 在重构时改变了措辞（如 `"下载准备中"` → `"正在准备下载..."`），旧字符串从 runtime 消失，扫描零命中通过——但新字符串可能仍在 runtime 中而不在 helper 中。agent 可能忘记更新扫描模式。
  3. **正常重构的干扰**：如果 helper 中的文本被有意改进（如改进 LLM 可读性），扫描结果从 "零命中（旧位置）" 变为 "仅命中 helper（新位置）"，这是预期行为。但 review 时无法从扫描结果区分 "移动到 helper" 和 "helper 中的措辞是新写的而旧措辞丢失了"。
- **为什么有问题**: 扫描是结构性气味检查（smell check），不是正确性证明。Plan 将它们呈现为 definitive validation criteria（"Expected scan results: zero production/test hits"），可能让 review 产生虚假安全感。
- **直接证据**: Plan §Required source scans 和 §Expected scan results 将扫描结果作为切片完成的硬性条件
- **影响**: 扫描可能漏掉新型号的语义漂移（不在模式中的字符串），或对合法的措辞改进产生误报
- **建议改法和验证点**: 在 plan 中补充说明：扫描是结构性验证而非穷尽性证明；真正的安全网是以下三项的组合：(a) 测试验证用户可见文本来自 helper，(b) 新 helper 文件的 coverage 报告，(c) propagation audit 逐路径确认。扫描只作为快速气味检查。同时在 plan 中声明：如果新文本字符串被添加到 runtime 但与已有扫描模式不匹配，implementation agent 必须同步更新扫描模式
- **修复风险（低）**: 在 plan 中补充说明即可
- **严重程度（低）**: 不影响 plan 的正确性，但影响验证的可靠性

### 6-WEB-CONTRACT-IMPLEMENTABLE-低-Web公开输出契约保持可实施

- **位置**: Plan §Implementation slices S1, stop condition
- **问题类型**: 最佳实践偏离（确认性 finding）
- **当前写法**: Plan S1 stop condition: "If removing provider output fields would require changing a public tool success JSON consumed outside `web_tools.py`, keep public JSON unchanged and move only its construction owner to `web_search_projection.py`."
- **反例/失败场景**: 用户特别关注 "whether Web provider/public output contract remains implementable without compatibility shims"
- **为什么有问题**: 需要独立验证 plan 的 stop condition 是否提供了足够的保护。
- **直接证据**:
  - `SearchWebOutput` 当前在 `web_search_providers.py:72-83`，被 `web_tools.py:108` import
  - `web_tools.py:1492-1518` 的 `_search_web_business` 返回 `SearchWebOutput`
  - `web_tools.py:1580` 调用 `_search_web_business` 并消费返回的 `SearchWebOutput`
  - Plan S1: "`_search_web_business(...)` calls `search_public_web(...)` for provider facts, then calls projection helper before returning a completed tool value"
  - 这意味着 `_search_web_business` 的调用链变为：`search_public_web()` → provider facts → projection helper → `SearchWebOutput`
  - 最终 tool outcome 的 JSON shape 不变（因为 `SearchWebOutput` 的字段结构被 `web_search_projection.py` 原样保留）
- **分析**: Stop condition 提供充分保护。Plan 的核心策略是 "移动构造 owner，保持公开 shape"：
  - Provider 不再生产 `preferred_result_summary`, `next_action`, `next_action_args`, `hint` 字段
  - Projection helper 从 provider facts（query, domains, total, preferred_result, results）构造这些字段
  - 最终 `SearchWebOutput` 的所有字段仍然存在，只是构造位置从 provider 变为 projection
  - 不需要 compatibility shim：因为公开类型 `SearchWebOutput` 的 shape 不变，只是 import 源可能变化
- **影响**: 无。Web 公开契约保持可实施。
- **建议改法和验证点**: Plan 已包含必要的保护机制。建议 implementation agent 在 S1 完成后运行 `rg -n "SearchWebOutput" tests/` 确认所有测试的 import 已更新
- **修复风险（低）**: 无修复需要
- **严重程度（低）**: 确认性 finding

### 7-SLICE-COUNT-ADEQUATE-低-三切片数量合理

- **位置**: Plan §Implementation slices
- **问题类型**: 切片过粗 / 切片数量
- **当前写法**: "Three slices are enough because each slice is a separate semantic owner boundary with its own validation loop. Splitting further by file would add gate overhead without reducing semantic risk."
- **反例/失败场景**: 用户要求检查 slice count/cost。需要验证三切片是否足够覆盖所有 owner boundary，或是否需要拆分/合并。
- **为什么有问题**: S1 涵盖 Web search provider + Web tool projection + Web cancellation text，三个不同关注点。但如果拆分为独立切片，中间状态无法通过测试（provider output 变更需要 projection helper 就位才能通过 tool-call 测试）。
- **直接证据**:
  - S1 涉及 4 个 production files + 新的 projection helper
  - S2 涉及 2 个 production files + 新的 text helper
  - S3 涉及 1 个 production file + docs + aggregate validation
- **分析**: 三切片设计合理：
  - S1 的 provider refactoring 和 projection helper 必须同时落地——否则 `_search_web_business` 无法同时产出 provider facts 和构造 SearchWebOutput。拆分会导致中间 commit 无法通过测试。
  - S1 的 concern 内聚：所有变更服务于同一个 Web tool LLM-facing output 路径（搜索 → 投影 → tool outcome → LLM context）
  - S2 的 concern 内聚：所有变更服务于同一个 Fins direct/wait user-visible output 路径
  - S3 是收尾切片：小范围变更 + 聚合验证
  - 每个切片有独立的 focused test command 和 stop condition
- **影响**: 无。切片设计合理。
- **建议改法和验证点**: 保持当前切片设计
- **修复风险（低）**: 无修复需要
- **严重程度（低）**: 确认性 finding

## Open questions

1. **`web_cancellation_text.py` 删除时机**：Plan 说 "keep the old file only if it remains the real owner and is renamed is not needed"。当前该文件的唯一内容是 `WEB_CANCELLED_HINT` 常量。如果 S1 将其移入 `web_tool_projection_text.py`，`web_cancellation_text.py` 成为空壳。建议 S1 明确：移动到新 helper 后删除旧文件，不做兼容 re-export。

2. **Fins `direct_event_text.py` 是否需要导入 `FinsOperationKind` 来做 operation-specific 文本映射？** 当前 `ingestion_runtime.py` 中不同操作（download/preprocess/upload）有不同的失败标题。如果 helper 只提供常量和简单 key lookup，operation-specific 的文本选择逻辑仍留在 runtime 中。建议 plan 明确 helper 的接口粒度。

3. **`web_tool_projection_text.py` 和 `web_search_projection.py` 是否应合并？** 一个存储文本常量（display names, cancellation copy），一个做计算（next_action decision from provider facts）。当前分离是合理的（常量 vs 计算），但如果两个模块都很小（各 < 100 行），合并为一个 `web_projection.py` 可能更简洁。这不影响正确性，留给 implementation agent 判断。

## Residual risks

| Risk | Severity | Suggested tracking |
|------|----------|-------------------|
| S2 可能意外移动 durable job state 字符串（plan stop condition 要求 "only move user-visible projection" 但 `ingestion_runtime.py` 中两者的边界不总是清晰的） | 中 | Implementation agent 必须在 S2 closeout 中报告哪些字符串被移动、哪些保留在 runtime 中及其原因 |
| Web 测试中对 `SearchWebOutput` 类型的 import 可能分散在多个测试文件中，遗漏更新会导致 pyright 报错 | 低 | S1 focused test command 覆盖了主要测试文件；aggregate scan 会捕获剩余 |
| 如果 Fins direct/wait 文本 helper 在 S2 中被设计为构造完整 `FinsEvent` 对象（而非只提供文本常量），会与 `direct_events.py` 的契约形状所有权产生重叠 | 中 | 见 Finding 2；plan 应澄清 helper 不构造 `FinsEvent`/`FinsResultSummary`/`FinsProgress` |
| `web_tools.py:69` 当前 import `WEB_CANCELLED_HINT` from `web_cancellation_text.py` — 如果新 helper 的 import 路径不同，`web_search_providers.py:19` 的同名 import 也需要更新（但 provider 应该不再需要该常量） | 低 | Implementation agent 应在 S1 中确认 provider 移除了对 `WEB_CANCELLED_HINT` 的所有引用 |

## Conclusion

**Verdict: pass-with-risks**

Plan 在以下方面表现良好：
- 动机成立，基于直接 code evidence 验证
- Owner boundary 判定正确（特别是 Fins direct_events vs ingestion_runtime 的区分，Finding 4 确认）
- 6 个 source finding 的处置全部正确（含 DS12 evidence-invalid，Finding 1 确认）
- 三切片设计合理，每个切片有独立的 validation loop（Finding 7 确认）
- Web 公开契约保持可实施，stop condition 提供充分保护（Finding 6 确认）
- 非目标清晰，不扩大范围

需要关注的风险（不阻塞推进）：
- S2 `direct_event_text.py` 的角色需澄清：纯文本常量 vs 投影辅助函数（Finding 2）
- S1 `SearchWebOutput` 类型迁移路径需补充具体类型名称和 import 路径（Finding 3）
- Source scan 应被定位为结构性气味检查而非穷尽性正确性证明（Finding 5）

三个 open questions 均可在 implementation gate 中由 agent 做出合理判断后推进，无需阻塞 plan approval。

**Findings count**: 7（2 中、5 低）
**Blockers**: 0
**Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-ds.md`
