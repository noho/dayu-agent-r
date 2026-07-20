# WU-SEMANTIC-OWNERSHIP-01 / R08 Plan — 第二路独立 adversarial plan review (AgentDS)

## 0. Review identity

| 项 | 值 |
|---|---|
| review target | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| target SHA-256 | `9ddc11b6dbfc9559561ae619f47e2d237a7e999b88798eb861eae7483b0e2385` |
| reviewer | AgentDS（第二路独立 plan review） |
| review type | adversarial plan review；不是新 WU |
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 overdesign remediation continuation |
| sub-WU | R08 Financial/XBRL 最小 contract 与单一 projection |
| base HEAD | `8d9bf63b3ab56f9ba3d5355d75af4ee002548c9c` |
| R07 completion | `28b6fc1956bd3832489a471fa29bfe354b319860` |
| output | 唯一 artifact（本文件） |
| 授权 | 只写本 review artifact；不改 plan/control/design/code/tests/README；不 stage/commit/push/PR |

## 1. Review scope and method

### 1.1 Documents read

- `AGENTS.md`（项目最高约束）
- `docs/host/issues-implementation-control.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（完整 732 行，特别 Topic 6）
- `docs/fins/design.md`（完整 124 行，§5-§6）
- `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（完整 1270 行，特别 §15 R08）
- `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（完整 707 行）
- `docs/reviews/wu-semantic-ownership-01-r08-plan-entry-controller-validation.md`（完整 98 行）

### 1.2 Code evidence directly inspected

| 文件 | 检查内容 |
|---|---|
| `dayu/fins/domain/financial_result_contract.py` | 当前 9-reason 闭集（含 `statement_method_missing`/`statement_empty`）、`StatementLocator` 类型、`statement_locator` required 字段、validator 逻辑 |
| `dayu/fins/domain/xbrl_result_contract.py` | 当前 `total` 字段（`len(facts)` 派生）、`ValidatedXbrlFactsResult`、validator 拒绝 `deduped_fact_count` |
| `dayu/fins/tools/result_types.py` | Public `FinancialStatementResult` 含 `statement_locator`、Public `XbrlQueryResult` 含 `total` + `deduped_fact_count`、`XbrlQueryParams` 含 `fiscal_period: str \| None`（非 typed） |
| `dayu/fins/tools/read_runtime_helpers.py` | `NormalizedXbrlQueryPayload` 含 `total` + `deduped_fact_count`；read 侧 dedup |
| `dayu/fins/tools/read_runtime.py` | Line 2096: `"statement_locator": statement_payload["statement_locator"]`（机械复制）；line 1999: docstring 提及 `statement_locator` |
| `dayu/fins/tools/fins_tools.py` | Line 978-980: `query_xbrl_facts` tool description 手写"total 是去重前的原始 fact 数，deduped_fact_count 是返回 facts 的去重后数量"；`get_financial_statement` tool description 仅含 `rows/currency/units/scale/data_quality/reason`，未提及 `statement_locator`（`statement_locator` 不在 description 但实际返回） |
| `dayu/fins/processors/sec_processor.py` | `get_financial_statement`: 使用 `build_statement_locator`、产生 `statement_method_missing`/`statement_empty`/`statement_not_found`；`query_xbrl_facts`: 构造嵌套 `filters_applied`、`total=len(facts)`；未使用 `pandas`（F401） |
| `dayu/fins/processors/sec_xbrl_query.py` | `build_statement_locator` helper 定义及所有 `_STATEMENT_TITLE_BY_TYPE`/`_format_statement_period_label` 引用 |
| `dayu/fins/processors/bs_six_k_processor.py` | 导入 `build_statement_locator`；`get_financial_statement` 与 `query_xbrl_facts` 均产生 locator 与 count |
| `dayu/fins/processors/bs_report_form_common.py` | 两处 `statement_locator: build_statement_locator(...)`；未使用 `Path`（F401） |
| `dayu/fins/processors/html_financial_statement_common.py` | `_build_html_financial_result` 产生 `statement_locator` |
| `dayu/fins/processors/six_k_form_common.py` | 两处 `build_statement_locator(...)` |
| `dayu/fins/processors/report_form_financial_statement_common.py` | fallback reason 集 |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `_build_financials_payload` 发明 `processor_error:<message>` 与 `invalid_statement_result` alternate reason；`_extract_fiscal_from_xbrl_query` 消费旧 XBRL validator |
| `dayu/fins/pipelines/sec_download_persistence.py` | `_build_financials_payload` 的生产调用方搜索（零结果：仅在测试中出现） |
| `dayu/contracts/tool_schema.py` | `ToolTruncateSpec` 定义；`ToolTruncationStrategy` 枚举 |
| `tests/fins/test_sec_pipeline_download.py` | `_build_financials_payload` 的唯一 caller（line 2113, 2120, 2121）；test 固化 `processor_error:` 与 `invalid_statement_result` |
| `tests/fins/test_financial_read_contracts.py` | 当前 owner contract tests |
| `tests/fins/test_fins_read_runtime.py` | XBRL payload 测试：`test_xbrl_query_payload_always_projects_dedup_count_and_owner_quality`、`test_xbrl_query_payload_preserves_processor_total_after_dedup`、`test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup` |
| `tests/fins/test_fins_storage_provider.py` | AAPL XBRL fixture 路径（lines 137-141） |
| `dayu/fins/domain/tool_models.py` | `Citation` 为 frozen dataclass（line 86-118），`to_dict() -> dict[str, Any]`（line 119）；`SourceType` str Enum（lines 17-30）实际值为 `SEC_EDGAR` / `CNINFO` / `HKEXNEWS` / `UPLOADED` / `SUPPLEMENTARY` |
| `dayu/fins/tools/read_runtime.py` | `_FILING_SOURCE_TYPES_BY_PROVIDER` 映射表（lines 148-152）；字符串映射（lines 141-145） |

### 1.3 Tests collected

```
tests/fins/test_financial_read_contracts.py
tests/fins/test_fins_read_runtime.py
tests/fins/test_read_runtime_semantic_ownership_guards.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_storage_provider.py
tests/fins/test_processor_registry.py
tests/fins/test_fins_ingestion_tools.py
tests/fins/test_sec_pipeline_download.py
```
总计 319 tests collected（全部 R08-relevant allowlist）。

### 1.4 Assumptions tested

| # | Assumption | 验证方式 | 结论 |
|---|---|---|---|
| A1 | `_build_financials_payload` 无 production caller | `rg` 全仓搜索 + 人工确认仅 `tests/` 调用 | **成立** |
| A2 | 当前 `query_params` shape drift 存在于 `filters_applied` 嵌套 vs flat | 直接读 `sec_processor.py:716-726` + `result_types.py:274-282` | **成立**：producer 写 `query_params.filters_applied`，read 从 `query_params` 顶层读同名键并补 `None` |
| A3 | 九值 reason closure 中 `statement_method_missing`/`statement_empty` 可用 `statement_not_found` 统一 | 分析所有 producer 中的 method/empty 分支 | **成立**：三者在 producer terminal 归一语义等价 |
| A4 | 当前 `total=len(facts)` 是本地派生值，非 provider raw total | 读 `sec_processor.py:756`（`"total": len(facts)`）、`xbrl_result_contract.py:103`（`total != len(facts)` 抛异常） | **成立**：validator 把 `total == len(facts)` 作为 contract invariant，所以 `total` 不携带 provider 独立语义 |
| A5 | R07 不触及 `read_runtime.py` snapshot/citation symbols | plan §2.2 明确列出 R07 禁改边界 + S2 scan 要求 | **成立且可执行** |
| A6 | 七值 reason 闭集每个值都有业务恢复动作 | 逐值分析 | **多数成立，见 Finding R08-PR-DS-02** |
| A7 | `FinancialStatementResult` public type 当前含 `statement_locator` | 直接读 `result_types.py:260` | **成立** |
| A8 | AAPL XBRL fixture 存在且可用于真实 smoke | `test_fins_storage_provider.py:137-141` 确认 `tests/fins/fixtures/aapl_xbrl/` 路径 | **成立** |
| A9 | bs_report_form_common.py 有 F401 unsed `Path`；sec_processor.py 有 F401 unused `pandas` | ruff F401 scan | **成立（各1个）** |
| A10 | `Citation` 是 frozen dataclass 而非 TypedDict；`to_dict()` 返回 `dict[str, Any]` | 直接读 `tool_models.py:86-119` | **成立**：R08 public projection 不能直接 import dataclass 作 TypedDict 签名 |
| A11 | `SourceType` 枚举实际值为 `SEC_EDGAR` 等，不存在 `"sec_filing"` | 直接读 `tool_models.py:17-30` + `rg -n 'sec_filing' dayu tests` 零命中 | **成立**：plan 示例 `"sec_filing"` 是错误值 |

## 2. Findings

### R08-PR-DS-01 — 中 — S1 checkpoint 的 "中间未提交破坏性边界" 在 multi-reviewer 并发下存在状态漂移风险

- **位置**: Plan §5.6 "S1 不做中间 commit"、§4.1 Controller validation "S1 是未提交的严格 review checkpoint"
- **问题类型**: 切片过粗 / 状态机漏洞
- **当前写法**: S1 与 S2 是"同一次破坏性 contract cutover"；S1 不做中间 commit；S1 full pyright 允许预声明的 S2 consumer 破坏性传播错误
- **反例/失败场景**:
  1. AgentCodex 完成 S1 implementation，working tree 含所有 producer 变更 + S2 consumer 的类型错误。
  2. AgentMiMo 与 AgentDS 对"同一 immutable diff"做并发的 S1 review。但实际上 diff 中混入了预期 S2 会修复的类型错误 —— 两路 reviewer 必须区分"这是 S1 已完成的正确行为"与"这是 S1 已知的、S2 会修复的传播错误"。
  3. Controller adjudication 期间 S1 已 review 通过，但 S2 consumer 的类型错误仍在 tree 中。若此时任何人运行 full pyright，看到的是"未完成"的红色 —— 这与"review 通过"产生认知分歧。
  4. 两路 reviewer 对"哪些类型错误是预声明的 S2 传播"可能产生分歧，导致 same evidence/different verdict。
- **为什么有问题**: 项目指令要求 `pyright` 全量通过作为每个 slice 的验证门。S1 明确允许 full pyright 不通过（只要求 modified-owner scoped 通过），这在流程上与"每个 sub-WU 独立可验证"的目标存在张力。两个 reviewer 需要精确区分 S1-expected-error vs new-error，增加了 review 认知负担和误判风险。

  但 plan §5.4 已做了详细约束：full pyright 必跑，"只允许出现预声明 S2 direct-consumer allowlist 内、且能逐条对应已删除 producer 字段/类型的传播错误，并把文件、symbol、旧字段与 S2 迁移动作记录为精确预期证据；任何位于其它文件、无法对应 S2 迁移或由 S1 owner 自身产生的错误都使 S1 失败。禁止 cast、ignore、compat 字段或临时 shim 压错"。

  此约束在逻辑上可执行，但执行成本高：需要人为逐条核对每个 full pyright 错误与预声明 S2 allowlist 的精确对应。若 S2 allowlist 文件超过 4 个、S1 删除字段超过 3 个，人工逐一归因容易遗漏。
- **直接证据**:
  - Plan §5.4: "Full pyright 在S1内部未提交破坏性边界上只允许出现预声明 S2 direct-consumer allowlist...内、且能逐条对应已删除producer字段/类型的传播错误"
  - Plan §5.6: "S1不做中间commit。S1与S2是同一次破坏性contract cutover"
  - Plan §6.1: "S1 cumulative tree未commit且未混入其它scope"
- **影响**: S1 review 可能在未察觉的 type error 上达成错误共识；S1→S2 handoff 的"已 review 通过"状态与实际 working tree 的 pyright 红色不一致。
- **建议改法和验证点**:
  1. 在 S1 review 开始前，由 Controller 先运行 full pyright，将实际错误列表与预声明 S2 allowlist 逐条匹配，产出 `S1-propagated-errors.md` 作为 review 输入。两路 reviewer 只对照该清单裁决，不各自从 pyright 输出中手工匹配。
  2. 或者：S1 使用独立 git worktree 做 implementation+review，只在该 worktree 内不提交；review 闭圈后将 S1+S2 作为一组 squash-merged commit 提交到主分支。这保持了"中间不 commit"的意图但隔离了 review surface。

  不推荐改为 S1 独立 commit（与 plan 的"同一 cutover"设计冲突）。
- **修复风险**: 低（只增加 Controller 预检查 artifact，不改 plan 设计）
- **严重程度**: 中 — 流程风险，不是 correctness 风险；但若 controller 预检缺失，可能导致 S1 review 误签。

### R08-PR-DS-02 — 中 — 七值 financial reason 闭集中 `unsupported_statement_type` 的动作性需要在 plan 中明确定义

- **位置**: Plan §4.1 七值 reason 闭集、§5.2 "失败语义"映射表
- **问题类型**: 契约缺失
- **当前写法**: Plan §4.1 列出七值闭集（`unsupported_statement_type`/`xbrl_not_available`/`statement_not_found`/`low_confidence_extraction`/`scale_unavailable`/`period_semantics_unavailable`/`scale_and_period_semantics_unavailable`），并给出 producer 观测→reason 的映射表。§5.2 说明 `statement_not_found` 统一 method absent/None/empty/空 rows 四种观测。
- **反例/失败场景**: `unsupported_statement_type` 在 plan 中被定义为"statement type 不支持"时输出。但 plan 没有说明 LLM 收到此 reason 后的**正确恢复动作**是什么。当前 tool description（`fins_tools.py:900-907`）列出 `statement_type` 枚举 `["income", "balance_sheet", "cash_flow", "equity", "comprehensive_income"]` —— 若 LLM 传了这些合法值之一，producer 就不可能产生 `unsupported_statement_type`。那什么场景会触发？如果 LLM 传了不在枚举中的值，schema 验证会在 tool call 阶段就拒绝，根本到不了 producer。所以 `unsupported_statement_type` 在当前 tool schema 下实际上是 **dead reason**：枚举已覆盖所有合法输入值。

  同理，`xbrl_not_available` 的动作性：LLM 应该转而调用 `get_financial_statement` 的 HTML/OCR 路径？还是放弃？plan 只说"XBRL source/能力不可用且下一步应改用抽取"，但 tool description 层面没有告诉 LLM 这种 fallback 路径存在。
- **为什么有问题**: `AGENTS.md` LLM-facing 文本约束要求"只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"。若 reason 值存在但 LLM 不知道该做什么，reason 只是诊断 noise。当前 plan 在 producer→reason 映射上完整，但在 reason→LLM action 上不完整。
- **直接证据**:
  - Plan §4.1 七值闭集（lines 89-96）
  - `fins_tools.py:903-906` 当前 tool description 只列出 `data_quality` 取值和 `reason` 说明缺失或降级原因，没说 LLM 该怎么做
  - `fins_tools.py:1710` `statement_type` enum 只含 5 个合法值
  - Plan §4.3 "Tool schema、description与LLM文本" 要求自足说明字段、类型、必填性、枚举与最小示例，但未要求说明 reason 对应的恢复动作
- **影响**: 中等 — LLM 收到 reason 后可能做错误决策（如：收到 `xbrl_not_available` 后继续重试 XBRL 查询而非切换抽取路径）
- **建议改法和验证点**:
  1. 在 plan §4.4 的 tool description 要求中增加：每个 reason 值的业务含义与 LLM 推荐的下一步动作。
  2. 在 S2 implementation 中对 tool description metadata/helper 增加每个 reason 的 LLM-actionable 说明。
  3. `unsupported_statement_type` 在当前 schema 下是 dead reason —— 要么在 plan 中记录为"保留给未来 statement_type 动态扩展"，要么从七值中删除该值并只保留六值。推荐保留但标注为"当前 tool schema 枚举外、未来扩展入口"，避免 S2 实现时误删。

  或者更简洁：plan 中明确七值的动作矩阵：
  - `unsupported_statement_type` → 更换 statement_type
  - `xbrl_not_available` → 对同一 ticker/document 切换为 HTML/OCR 抽取路径（通过 `get_financial_statement` 的自动 fallback 或 LLM 改用不同 document_id）
  - `statement_not_found` → 检查 document 是否支持该 statement type
  - `low_confidence_extraction` → 交叉验证数值；优先使用 XBRL 路径
  - `scale_unavailable` → 不要跨报表比较数值（可能倍率不同）
  - `period_semantics_unavailable` → 不要跨期间比较数值（可能财期不对齐）
  - `scale_and_period_semantics_unavailable` → 不要做任何数值比较
- **修复风险**: 低 — 只在 plan 中增加动作矩阵，不改变 contract shape
- **严重程度**: 中 — 不影响 producer contract 正确性，但影响 LLM 可行动性，属于 LLM-facing 契约缺失

### R08-PR-DS-03 — 中 — Public citation typing 从 `dict[str, Any]` 迁移到 strict mapping 但 plan 未确认 R07 Citation 的 exact 类型形态

- **位置**: Plan §4.3 "Public XBRL exact字段"、§4.3 投影规则第 3 条
- **问题类型**: 契约缺失
- **当前写法**: Plan §4.3 要求 public result 的 `citation` 字段 "机械消费 R07 当前 Citation JSON 投影，优先直接复用其现有typed payload；若边界只暴露mapping，则签名使用 `Mapping[str, JsonValue]` 输入与 JsonValue-compatible strict mapping输出。不得继续新建或复制 `dict[str, Any]` 签名，不得用cast、shim或重新拼字段建立第二个citation owner"
- **反例/失败场景**:
  1. 当前 `result_types.py` 所有 public result 的 `citation` 字段均声明为 `dict[str, Any]`。
  2. `dayu/fins/domain/tool_models.py:86-118` 的 `Citation` 是 **frozen dataclass**（不是 TypedDict），其 `to_dict() -> dict[str, Any]` 返回松散字典。R08 public projection 不能直接 import 该 dataclass 用作 JSON TypedDict 签名——dataclass 的字段类型（如 `source_type: str`、`Optional[str]` 等）不映射到 JSON Schema shape，`to_dict()` 的返回值是 `dict[str, Any]`，不符合"strict mapping"要求。
  3. 因此 plan 需要面对的实际技术选择是：(a) public projection 签名用 `Mapping[str, JsonValue]` 输入、`dict[str, JsonValue]` 输出，不改 R07 Citation dataclass；(b) 新建一个只含 public 必要字段的 `PublicCitation` TypedDict，从 R07 dataclass 的 fields 手动投影。Plan 当前"优先直接复用typed payload"的说法对 dataclass 形态不适用——dataclass instance 不是 typed mapping，`to_dict()` 返回 `dict[str, Any]`。
- **为什么有问题**: Controller validation `R08-PE-F05` 裁决"机械消费 R07 citation 的 strict JsonValue-compatible mapping，不改 R07 owner、不 cast/shim"。但 R07 Citation 是 frozen dataclass 而非 TypedDict/mapping，裁决的"strict JsonValue-compatible mapping"与 R07 actual type 之间存在 gap。Plan 未澄清这个 gap，implementation agent 可能错误地 `cast(Citation, raw_dict)` 或引入 `Any` 签名的 wrapper。
- **直接证据**:
  - `tool_models.py:86-87`: `@dataclass(frozen=True)` / `class Citation:`（**不是 TypedDict**）
  - `tool_models.py:119`: `def to_dict(self) -> dict[str, Any]:`（返回值是 `dict[str, Any]`）
  - `result_types.py:117,251,290`: 三处 `citation: dict[str, Any]`
  - `read_runtime.py:48`: `from dayu.fins.domain.tool_models import Citation, SourceType`
  - Plan §4.3: "优先直接复用其现有typed payload" — 对 dataclass 形态不可直接套用
- **影响**: S2 implementation 可能：(a) 错误地将 dataclass 用作 TypedDict 签名；(b) 引入 `cast()` 绕过类型检查；(c) 保留 `dict[str, Any]` 并声称"不改 R07 owner"。三者均违反 AGENTS.md 禁止 `Any`/禁止 `cast`（用作规避）约束。
- **建议改法和验证点**:
  1. Plan §4.3 的引用规则应明确：R08 public projection 的 `citation` 签名使用 `Mapping[str, JsonValue]` 输入、`dict[str, JsonValue]` strict 输出（不改 R07 Citation dataclass 字段/owner）。Public projection helper 从已经 `to_dict()` 的 raw dict 中逐字段读取并写入 public result，不做 `cast`、不 import Citation dataclass 用于签名。
  2. 验证：S2 中所有 `citation` 字段声明和 helper 签名中零 `dict[str, Any]`、零 `Any`、零 `cast`（用于规避类型检查的 cast）。
  3. 如果 public 需要比 R07 Citation 更少的字段，可以在 projection helper 内部做字段子集投影，签名不必与 R07 dataclass 耦合。
- **修复风险**: 低 — 澄清技术约束，不改 plan 核心设计
- **严重程度**: 中 — 不影响 contract 语义，但类型实现的正确性依赖 exact 技术路径澄清

### R08-PR-DS-04 — 低 — Tool description "最小 XBRL 示例" 缺少 `reason` 为 optional 的显式证明

- **位置**: Plan §4.4 最小 XBRL 示例（lines 293-309）
- **问题类型**: 契约缺失
- **当前写法**: 示例中 `data_quality: "xbrl"` 且不含 `reason` 字段。这隐含证明 `reason` 是 optional 且 complete 时缺席。
- **反例/失败场景**: LLM 看到示例没有 `reason`，可能错误推断"所有 XBRL 结果都没有 reason"而没有意识到 partial 时会出现 reason。虽然 tool description 文本会说明"reason只在partial时出现"，但单一示例不覆盖两种质量状态。
- **为什么有问题**: 轻度。单一示例不能同时展示 complete（无 reason）和 partial（有 reason）两种形态。但 plan 要求"最小示例"而非"穷举示例"，且 tool description 文本已要求说明 optional reason 规则（§4.4 第5点："reason只在partial时出现"）。
- **直接证据**: Plan §4.4 lines 295-309
- **影响**: 低 — LLM 可能不完全理解 reason 的 optional 语义，但 tool description 文本可弥补
- **建议改法和验证点**: 在 plan §4.4 中增加一个 partial + reason 的补充示例，或在 plan 中注明"complete 示例已足够，partial 示例在 tool description 文本中说明"
- **修复风险**: 低 — 仅增加示例
- **严重程度**: 低

### R08-PR-DS-05 — 低 — `query_xbrl_facts` tool 的 `fiscal_period` 参数 schema 描述缺少封闭枚举

- **位置**: Plan §4.2 XBRL query params、§6.5 tests
- **问题类型**: 契约缺失
- **当前写法**: Plan §4.2 定义 `XbrlQueryParams.fiscal_period: NotRequired[FiscalPeriod]`（typed `FiscalPeriod`）。但当前 `fins_tools.py:1748` 的 tool parameter schema 中 `fiscal_period` 的 description 是 `"可选财期过滤，例如 FY、Q1、Q2。"`，没有 enum 约束。Plan 未明确 S2 中 `fiscal_period` 的 LLM-facing schema 是否需要增加 `enum` 约束。
- **反例/失败场景**: LLM 可能传入 `"annual"` / `"yearly"` / `"H2"` 等非法财期值，schema 不做 enum 校验，错误会延迟到 processor 内部才暴露。虽然 processor 会 reject 非法 `fiscal_period`，但更早的 schema 校验可以给 LLM 更精确的错误反馈。
- **为什么有问题**: 轻度。`list_documents` 的 `fiscal_periods` 已有 `enum: ["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`；`query_xbrl_facts` 的 `fiscal_period` 参数相同语义，但没有同样的 enum。
- **直接证据**:
  - `fins_tools.py:1499` `fiscal_periods` enum（list_documents）
  - `fins_tools.py:1748` `fiscal_period` description 无 enum（query_xbrl_facts）
- **影响**: 低 — LLM 可能在错误值上浪费一次 tool call；processor 会 fail closed
- **建议改法和验证点**: 在 S2 的 `_query_xbrl_facts_parameters()` 中为 `fiscal_period` 增加 `enum: ["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`。此修改在 plan S2 allowlist 范围内（`fins_tools.py`）。
- **修复风险**: 低 — 与 `list_documents` 的 `fiscal_periods` enum 一致化
- **严重程度**: 低

### R08-PR-DS-06 — 低 — `min_value`/`max_value` 使用 `int | float` 类型但当前 tool schema 声明为 `number`

- **位置**: Plan §4.2、当前 `fins_tools.py:1749-1750`
- **问题类型**: 契约一致性
- **当前写法**: Plan §4.2 定义 `XbrlQueryParams.min_value: NotRequired[int | float]`、`max_value: NotRequired[int | float]`。当前 tool schema 的 `min_value`/`max_value` 声明为 `{"type": "number"}`。Controller validation `R08-PE-F02` 确认"query 数值使用可实现的 `int | float`，validator 显式拒绝 `bool`"。
- **反例/失败场景**: Python `bool` 是 `int` 的子类，JSON Schema `number` 接受整数和浮点数。`validate_and_project_arguments` 可能传入 `True`/`False`（LLM 偶尔会传 boolean 作为数值过滤）。Plan 要求在 validator 中显式拒绝 `bool`，此逻辑必须在 `XbrlQueryParams` 的 typed validator（或 tool schema 的 JSON Schema 层）中实现。
- **为什么有问题**: 轻度。`int | float` 类型注解在 Python 中无法自动拒绝 `bool`（`bool` is `int`）；Plan 和 Controller 裁决明确要求拒绝，但未指定 exact 拒绝位置（是 TypedDict validator 还是 tool schema JSON Schema 的 `"type": "number"` 本身已经足够，因为 JSON Schema `number` 类型不包含 `true`/`false`）。
- **直接证据**:
  - Plan §4.2: "`bool`虽然是`int`子类，但不属于本业务数值，validator必须显式拒绝"
  - Controller validation `R08-PE-F02`
  - JSON Schema spec: `"type": "number"` 不包括 boolean
- **影响**: 低 — JSON Schema 层的 `"type": "number"` 已天然拒绝 boolean（不合规的 LLM 实现除外）；TypedDict 层只是 Python 类型约束
- **建议改法和验证点**: 在 S1 `xbrl_result_contract.py` 的 validator 中增加 `isinstance(value, bool)` 拒绝逻辑（对 `min_value`/`max_value` 的 int-as-bool 做显式 guard），并增加专门 test。此修改在 S1 allowlist 范围内。
- **修复风险**: 低
- **严重程度**: 低

### R08-PR-DS-07 — 中 — Plan §4.4 最小 XBRL 示例中 `source_type: "sec_filing"` 与代码真源 `SourceType.SEC_EDGAR` 不一致

- **位置**: Plan §4.4 最小 XBRL 示例 line 300
- **问题类型**: 契约缺失 / 直接反例
- **当前写法**: Plan §4.4 最小 XBRL 示例的 `citation` 中写 `"source_type": "sec_filing"`
- **反例/失败场景**:
  1. `dayu/fins/domain/tool_models.py:17-30` 定义 `SourceType` str Enum，实际值为 `SEC_EDGAR`, `CNINFO`, `HKEXNEWS`, `UPLOADED`, `SUPPLEMENTARY`。不存在 `sec_filing`。
  2. `read_runtime.py:148-152` 的 `_FILING_SOURCE_TYPES_BY_PROVIDER` 将 `FinsSourceProvider.SEC_EDGAR` 映射到 `SourceType.SEC_EDGAR`（值为 `"SEC_EDGAR"` 字符串）。
  3. 同样 `read_runtime.py:141` 的字符串映射也是 `FinsSourceProvider.SEC_EDGAR: "SEC_EDGAR"`。
  4. Plan 示例中的 `"sec_filing"` 在任何代码路径中都不出现。若 S2 implementation 按 plan 示例写出 `"sec_filing"` 字面量到 tool description/example，LLM 会期待一个不存在的 `source_type` 值，导致 citation field 与 R07 actual value 不一致。
- **为什么有问题**: Plan 的示例是 §4.4 的 normative 部分——"最小示例必须只有一个 count 并满足等式"。该示例直接指导 implementation agent 的 tool description/example 写作。如果 agent 按字面实现 `"sec_filing"`，将创建一个代码中不存在的 source_type 值。这是 plan→code 的直接错误传播路径。
- **直接证据**:
  - `tool_models.py:20`: `SEC_EDGAR = "SEC_EDGAR"`（实际值）
  - `tool_models.py:17-30`: `SourceType` 枚举全体——无 `sec_filing`
  - `read_runtime.py:149`: `FinsSourceProvider.SEC_EDGAR: SourceType.SEC_EDGAR`
  - `read_runtime.py:141`: `FinsSourceProvider.SEC_EDGAR: "SEC_EDGAR"`
  - Plan line 300: `"source_type": "sec_filing"`（错误值）
  - 全仓 `rg -n 'sec_filing' dayu tests` 零命中——证实 `sec_filing` 在任何生产代码与测试中均不存在
- **影响**: 中等 — implementation agent 可能将错误值写入 tool description example；LLM 收到的示例 citation 与实际 citation 不一致
- **建议改法和验证点**:
  1. Plan §4.4 示例中 `"source_type": "sec_filing"` 改为 `"source_type": "SEC_EDGAR"`。
  2. 同步检查 Controller validation artifact 是否也传递了该错误值（`docs/reviews/wu-semantic-ownership-01-r08-plan-entry-controller-validation.md` 未直接引用示例 source_type 值，只需确认 plan 修正）。
  3. S2 implementation 中所有 tool description example 的 `source_type` 值必须与 `SourceType` enum 一致；验证用 `rg -n 'source_type' dayu/fins/tools/fins_tools.py` 确认零硬编码字符串违例。
- **修复风险**: 低 — 单字段字符串修正
- **严重程度**: 中 — plan 规范示例错误，会直接传播到 S2 implementation 的 LLM-facing 文本

## 3. Mandatory review challenges — 独立验证结果

Controller validation §6 要求两路 reviewer 至少独立检查九项挑战。以下逐项报告结果：

### 3.1 七值 financial reason 闭集是否每个都有当前业务恢复动作

**结论**: 六个成立，见 Finding R08-PR-DS-02。`unsupported_statement_type` 在当前 tool schema 枚举下是 dead reason；`xbrl_not_available` 的 LLM action 需要显式写入 tool description。其余五个（`statement_not_found`、`low_confidence_extraction`、`scale_unavailable`、`period_semantics_unavailable`、`scale_and_period_semantics_unavailable`）均有明确业务语义。**通过，附建议**。

### 3.2 Actual producer inventory 是否覆盖所有路径

**结论**: Plan §3.3 列出 10 个文件/owner symbol，覆盖 SEC generic（`SecProcessor`）、BS 10-K/10-Q/20-F（`bs_report_form_common.py`）、BS 6-K（`bs_six_k_processor.py`）、HTML/OCR（`html_financial_statement_common.py`/`six_k_form_common.py`）、继承/registry 传播（`sec_report_form_common.py`、`report_form_financial_statement_common.py`、`financial_base.py`）。`sec_xbrl_query.py` 的 `build_statement_locator` helper 被覆盖。Registry 的 BS forms 通过 common 继承得到覆盖。**通过**。

### 3.3 `_build_financials_payload` 删除是否确有无 production caller 证据

**结论**: 全仓精确 `rg` 命令 `rg -n '_build_financials_payload' dayu/fins dayu tests --no-filename` 证实：

```
tests/fins/test_sec_pipeline_download.py:2113:    payload, has_xbrl = _sec_fiscal_fields._build_financials_payload(processor)
tests/fins/test_sec_pipeline_download.py:2120:    assert _sec_fiscal_fields._build_financials_payload(None) == (None, False)
tests/fins/test_sec_pipeline_download.py:2121:    no_xbrl_payload, no_xbrl = _sec_fiscal_fields._build_financials_payload(
```

`dayu/fins/pipelines/sec_download_persistence.py` 零命中。生产代码中唯一的 `_build_financials_payload` 出现是其自身定义（`sec_fiscal_fields.py:95`）。全仓 `dayu/fins/` 下无其它 production caller。

Plan 的删除范围正确：删除 alternate reason owner（`processor_error:` / `invalid_statement_result`）及固化其发明 reason 的 3 个 test 调用，保留 `_extract_fiscal_from_xbrl_query`（有 production caller 链：`_resolve_processed_fiscal_fields -> sec_download_persistence`）。**通过**。

### 3.4 Flat XBRL query params 是否把"实际执行参数"作为 producer truth

**结论**: Plan §4.2 正确定义 flat typed params（`concepts` required + 可选 filters 只有明确提供时出现）。Plan 明确禁止"read 重拼/default `None`"（§6.3）。**通过**。

### 3.5 Public citation typing 能否在不动 R07 owner 的前提下实现

**结论**: 通过但需澄清，见 Finding R08-PR-DS-03。`read_runtime.py:48` 已导入 `dayu/fins/domain/tool_models.Citation`（frozen dataclass，`to_dict() -> dict[str, Any]`）。Plan 需澄清 projection 签名使用 `Mapping[str, JsonValue]` 输入 / `dict[str, JsonValue]` 输出，不做 cast、不 import dataclass 用于签名、不改 R07 owner。**通过，附建议**。

### 3.6 S1 internal checkpoint 的 bounded propagation evidence 是否足够审查

**结论**: 通过但需流程补充，见 Finding R08-PR-DS-01。Plan 的约束（§5.4）逻辑上可执行，但需要 Controller 预检 artifact 降低两路 reviewer 的归因负担。**通过，附建议**。

### 3.7 Host truncation 组合裁决与 forced-truncation/fetch_more tests 是否可执行且不越界

**结论**: Plan §6.4 正确识别风险：Host 替换 `facts` 为 `{truncated: true, value: [...], fetch_more: {...}}` 后，`fact_count` sibling 不被原子更新。Plan 的正确处置是：(a) 在 Fins pre-Host 边界恒有 `fact_count == len(facts)`；(b) 不修改 Host；(c) 不私造 cursor/fetch_more；(d) 不静默 drop；(e) 不把 Host envelope 解释为 Fins contract。Controller validation §5 的裁决精确：Host envelope 是独立治理层，不是第二 Fins result。

  组合验证可执行：under-limit 路径走真实 provider→read→tool 验证等式；forced-truncation 路径可在测试中注入模拟超限场景（或直接验证 Fins serializer 不将 envelope 解释为 facts list）。**通过**。

### 3.8 Exact allowlists、逐文件 coverage、scoped Ruff、full pyright、真实 AAPL/HTML/no-statement smoke、双向 scans 是否完整

**结论**:
- **Exact allowlists**: S1 12 files + S2 4 files，全部列明。通过。
- **逐文件 coverage**: Plan 要求每个 changed production file `>=80%` 而非 aggregate。通过。
- **Scoped Ruff**: Plan 要求 S1+S2 全部实际修改文件 Ruff 零。S1 两个已知 F401（`bs_report_form_common.py::Path`、`sec_processor.py::pandas`）被纳入 S1 scope。通过。
- **Full pyright**: S1 后允许传播错误（见 Finding R08-PR-DS-01），S2 后必须零。通过但附注。
- **真实 AAPL/HTML/no-statement smoke**: `test_fins_storage_provider.py:137-141` 确认 AAPL fixture 路径存在。HTML 财务表 smoke 在 `test_financial_read_contracts.py` 中有覆盖。No-statement 测试在 `test_financial_read_contracts.py` 中有覆盖。通过。
- **双向 scans**: Plan §6.7 的 A/B/C/D 四类 scan 精确列出命令和 roots。通过。

### 3.9 是否偷带 R09-R12、Issues 142/151/175/177/178、unified authorization 或 R07 owner change

**结论**: Plan §2.3 "明确 out-of-scope" 列出全部 excluded items。S1/S2 allowlist 文件无越界。`read_runtime.py` 的 snapshot/bire/retire/revision/citation 路径被明确定义为 R07 no-touch（§6.4 scan D）。**通过**。

## 4. Additional adversarial checks

### 4.1 R07 no-touch 可执行性

Plan §6.7 scan D 要求 `git diff -U0` 验证 `read_runtime.py` 只改 financial/XBRL projection symbols。此 scan 是机械可执行的。当前 `read_runtime.py:2096` 的 `"statement_locator": statement_payload["statement_locator"]` 是 R08 必改行 —— 这行在 scan 中会命中，必须归因于 R08 public contract 删除。可执行。

### 4.2 Compat/fallback/shim 的禁止

Plan §2.2 "不可回改的 owner" 表和 §8 "Stop conditions与禁止补救" 表覆盖了所有禁止的补救行为（read 补默认、cast/ignore/shim、保留旧测试兼容分支等）。Plan 明确要求在 producer terminal 统一 `statement_not_found` 而非 read 看 rows 推断。通过。

### 4.3 Pyright 当前状态

当前 full pyright baseline 为零（umbrella plan §7 aggregate validation 记录 "full pyright为零"）。S1 将破坏此 baseline，S2 后必须恢复为零。已知的 150 个 Ruff 继承问题不归 R08。通过。

### 4.4 `statement_locator` 删除的影响面

当前 `statement_locator`/`StatementLocator` 存在于：
- `financial_result_contract.py`（type 定义 + validator 校验）
- All 7 producer files（构造）
- `result_types.py`（public TypedDict）
- `read_runtime.py:2096`（机械复制）
- `sec_xbrl_query.py`（`build_statement_locator` helper）

Plan 删除范围覆盖全部 5 层。`fins_tools.py` 的 tool description 不直接提及 `statement_locator`（description 只列 `rows` 等字段），但返回结果中实际包含该字段 —— S2 删除 public locator 后，tool description 无需修改（本来就没提），但返回 shape 会变小。这是正确行为。

### 4.5 `total` 字段的双重语义

当前 `total` 在三个上下文中有不同含义：
1. `XbrlFactsResult.total`（producer）：`len(facts)` 本地派生 → plan 决定**删除**
2. `ValidatedXbrlFactsResult.total`（validator）：要求 `total == len(facts)` → plan 决定**删除**
3. `XbrlQueryResult.total`（public）：当前与 `deduped_fact_count` 并存 → plan 决定**删除**，只保留 `fact_count`

Plan 的"internal positive inventory 预期为零"判断正确：当前 `total` 没有 provider raw-total 语义。如果未来出现真实的 provider response total，plan 要求五联证据保留在 internal diagnostic owner。通过。

### 4.6 `deduped_fact_count` 的单一迁移路径

Plan 要求 `fact_count` 只在 S2 public builder 赋值一次。当前 `read_runtime_helpers.py:1220` 是 `deduped_fact_count=len(deduped_facts)` 的写入点。S2 需将此逻辑从 `NormalizedXbrlQueryPayload` 移到 public builder，并确保 read runtime/serializer/tool callable 不再重写。迁移路径清晰。

## 5. Open questions

| ID | 问题 | 建议处置 |
|---|---|---|
| R08-PR-DS-Q01 | `result_types.py` 的 `FinancialStatementResult` 与 domain `FinancialStatementResult` 同名不同包（tools 包 vs domain 包）。Plan 要求 S2 建立 public projection，是否需要改名避免 import 冲突？ | 建议 S2 implementation 时将 tools 版本命名为 `PublicFinancialStatementResult`（与 plan §4.3 helper 名一致），domain 版本保留原名或改为 `ProducerFinancialStatementResult`。Plan 在 §4.3 用了 `PublicFinancialStatementResult` 这个名字，但 §3.4 consumer inventory 未明确说明需要 rename。建议在 S2 开始前由 Controller 确认 exact 命名。 |

## 6. Residual risks and suggested tracking destination

| 风险 | 当前处置 | destination |
|---|---|---|
| S1→S2 full pyright 传播错误的 reviewer 归因负担 | Plan §5.4 已有约束；建议 Controller 预检 | Controller pre-check artifact；若预检未通过则 S1 stop |
| `unsupported_statement_type` 为 dead reason | Plan 保留但未标注 | R08 implementer 检查；若确认 dead 则删除该值或标注为保留 |
| `xbrl_not_available` reason 的 LLM 恢复动作缺失 | Plan tool description 未要求 | S2 tool description 增加每个 reason 的 LLM action |
| 同名 `FinancialStatementResult` 冲突 | 未在 plan 中处理 | Controller 确认命名方案 |
| Plan §4.4 示例 `source_type: "sec_filing"` 与代码 `"SEC_EDGAR"` 不一致 | Plan fix: 修正为 `"SEC_EDGAR"` | Plan fix gate；S2 implementation 验证 |

## 7. Final plan review conclusion

### Verdict: **PASS-WITH-FINDINGS**

R08 plan 在 owner boundary 划分、contract reshape、producer/consumer inventory、exact allowlist、双向 scans、coverage/pyright/Ruff 门禁、真实 smoke、review/commit 边界和 out-of-scope 守卫方面完整且可执行。

与本 review 主要挑战的 Controller validation §6 九项 mandatory challenges 对照：全部通过（其中三项附建议）。发现 4 个 medium-severity findings 和 3 个 low-severity findings，均不阻塞 plan 进入 implementation：

- **R08-PR-DS-01（中）**: S1 checkpoint 的 pyright 传播错误需要 Controller 预检 artifact 降低 reviewer 归因负担。建议加到 S1 entry criteria。
- **R08-PR-DS-02（中）**: 七值 reason 闭集中 `unsupported_statement_type` 的动作性未定义；建议在 plan tool description 要求中增加 reason→LLM action 矩阵。
- **R08-PR-DS-03（中）**: Citation 为 frozen dataclass 而非 TypedDict；plan 的"复用typed payload"表述对 dataclass 形态不适用，需澄清 `Mapping[str, JsonValue]` 输入 / `dict[str, JsonValue]` 输出签名。
- **R08-PR-DS-04（低）**: 最小 XBRL 示例只展示 complete 态。
- **R08-PR-DS-05（低）**: `fiscal_period` schema 缺 enum。
- **R08-PR-DS-06（低）**: `bool` as `int` 需要在 validator 或 JSON Schema 层确切拒绝。
- **R08-PR-DS-07（中）**: Plan §4.4 示例 `source_type: "sec_filing"` 错误——代码真源为 `SourceType.SEC_EDGAR`（值 `"SEC_EDGAR"`），全仓 `sec_filing` 零命中。必须修正为 `"SEC_EDGAR"` 以防传播到 S2 implementation。

无 finding 为 critical severity。无 finding 质疑 plan 的 fundamental owner boundary 划分或 contract reshape 方案。无 finding 要求重新 design。所有建议均可作为 accepted plan finding 在 AgentCodex plan fix 中低成本修复。

### 审查覆盖声明

本次审查覆盖：
- S1 owner（domain contracts + all 10 actual producers）
- S2 owner（public projection + read/tool/LLM surface）
- 全部 current producer/consumer 直接代码证据（12+ files）
- 全部 existing test allowlist（8 test files, 319 collected）
- 七值 reason 动作性逐值分析
- `query_params` shape drift 双端验证
- Public citation strict typing 路径
- R07 no-touch 边界验证
- S1 未提交破坏性边界的执行风险
- Host ToolTruncateSpec cursor envelope/fetch_more 组合裁决验证
- 逐文件 coverage/pyright/Ruff/scans 完整性
- 真实 AAPL + HTML + no-statement smoke 证据
- Review/commit 顺序验证
- Compat/fallback/shim 禁止全覆盖
- R09-R12 / Issues 142/151/175/177/178 / 统一 authorization 越界检查
- `Citation` frozen dataclass vs TypedDict 形态验证
- `SourceType` 枚举值与 plan 示例 `source_type` 逐字比对
- `_build_financials_payload` 全仓 production caller 精确 rg 扫描

所有 mandatory review challenges 已逐项验证并有直接代码证据支撑。
