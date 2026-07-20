# WU-SEMANTIC-OWNERSHIP-01 / R08 Financial/XBRL Contract Plan Review — AgentMiMo

## 1. Review Target And Scope

| 项 | 值 |
|---|---|
| reviewed artifact | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| plan SHA-256 | `9ddc11b6dbfc9559561ae619f47e2d237a7e999b88798eb861eae7483b0e2385` |
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 overdesign remediation |
| sub-WU | R08 Financial/XBRL 最小 contract 与单一 projection |
| review date | 2026-07-17 |
| reviewer | AgentMiMo |
| artifact revision | 2（修正 F01 事实错误、F02 Citation 类型错误、新增 F06 source_type 示例不一致） |

Review 范围：R08 plan 全文（698 行）、controller entry validation、controller discussion Topic 6.4、umbrella remediation plan §15、`docs/fins/design.md` §5-§6，以及以下代码直接证据：

- `dayu/fins/domain/financial_result_contract.py` — 当前 FinancialStatementResult、StatementLocator、九值 reason、validator
- `dayu/fins/domain/xbrl_result_contract.py` — 当前 XbrlFactsResult、total、deduped_fact_count guard
- `dayu/fins/domain/tool_models.py` — Citation frozen dataclass、SourceType enum（`SEC_EDGAR = "SEC_EDGAR"`）
- `dayu/fins/tools/result_types.py` — 当前 public FinancialStatementResult、XbrlQueryResult、16 处 `dict[str, Any]`
- `dayu/fins/tools/read_runtime.py` — 当前 financial/XBRL projection、statement_locator 转发、total/deduped_fact_count 转发、`_FILING_SOURCE_TYPES_BY_PROVIDER` 映射
- `dayu/fins/tools/read_runtime_helpers.py` — XBRL normalize/dedup pipeline、total/deduped_fact_count 计算
- `dayu/fins/tools/fins_tools.py` — tool descriptions（total/deduped_fact_count 显式文档化）
- `dayu/fins/processors/sec_processor.py`、`bs_report_form_common.py`、`bs_six_k_processor.py`、`html_financial_statement_common.py`、`six_k_form_common.py` — statement_locator、filters_applied、total=len(facts) 产出
- `dayu/fins/processors/sec_xbrl_query.py::build_statement_locator` — locator helper
- `dayu/fins/pipelines/sec_fiscal_fields.py` — _build_financials_payload（dead code, test-only callers）、_extract_fiscal_from_xbrl_query、processor_error/invalid_statement_result reason
- `tests/fins/test_financial_read_contracts.py`、`test_sec_pipeline_download.py`、`test_fins_read_runtime.py`、`test_read_runtime_semantic_ownership_guards.py`、`test_fins_storage_provider.py`、`test_processor_read_consistency.py`、`test_processor_registry.py`、`test_fins_ingestion_tools.py`

## 2. Assumptions Tested

1. Plan 对七值 financial reason 闭集的业务可行动性判断是否成立。
2. Plan 对 `query_params` shape drift 的诊断是否与代码一致。
3. Plan 对 `statement_locator` 删除范围的 inventory 是否完整。
4. Plan 对 `_build_financials_payload` "无 production caller" 的断言是否准确。
5. Plan 对 `total`/`deduped_fact_count`/`fact_count` 的 source-of-truth 诊断是否正确。
6. Plan 对 Host truncation 组合风险的验证设计是否可执行。
7. Plan 的 S1 未提交破坏性边界与 pyright 策略是否安全。
8. Plan 的 exact allowlists 是否覆盖所有 producer/consumer/test。
9. Plan 对 R07 no-touch boundary 的保护是否充分。
10. Plan 对 R09-R12/Issues/统一 authorization 的 out-of-scope 声明是否与 control doc 一致。
11. Plan 最小示例中的 `source_type` 值是否与当前代码一致。

## 3. Findings

### R08-MIMO-F01-已撤回-`_build_financials_payload` "无 production caller" 断言实际正确

- **位置**: §3.3 Actual producer inventory, `sec_fiscal_fields.py`
- **问题类型**: 事实错误（reviewer 自身证据错误，已撤回）
- **原写法**: Reviewer 初版声称 `_resolve_processed_fiscal_fields`（`:174`）调用 `_build_financials_payload`，删除会破坏 download pipeline。
- **修正**: 全仓 `rg -n '_build_financials_payload' dayu/ tests/` 确认只有 `sec_fiscal_fields.py:95` 定义和 `tests/fins/test_sec_pipeline_download.py:2113,2120,2121` 测试调用。`_resolve_processed_fiscal_fields`（`:174`）接收 `financials_payload` 作为参数，内部调用 `_extract_fiscal_from_financials(financials_payload)`（`:203`），不调用 `_build_financials_payload`。`_resolve_download_fiscal_fields`（`:227`）调用 `_extract_download_fiscal_from_xbrl` 和 `_infer_download_fiscal_fields`，也不调用 `_build_financials_payload`。`_build_financials_payload` 和 `_resolve_processed_fiscal_fields` 均为 dead code（仅测试调用）。Plan 的"无 production caller"断言正确。
- **直接证据**:
  - `rg -n '_build_financials_payload' dayu/ tests/` — 仅 `:95` 定义 + `tests/` 三处调用
  - `rg -n '_resolve_processed_fiscal_fields' dayu/` — 仅 `:174` 定义，无 production 调用
  - `sec_fiscal_fields.py:203` — `_extract_fiscal_from_financials(financials_payload)` 不调用 `_build_financials_payload`
  - `sec_fiscal_fields.py:227-255` — `_resolve_download_fiscal_fields` 调用 `_extract_download_fiscal_from_xbrl` + `_infer_download_fiscal_fields`
- **最终状态**: 撤回。Plan 的 `_build_financials_payload` 删除动作和"只固化其发明 reason 的测试"措辞准确。

### R08-MIMO-F02-未修复-低-citation strict typing 实现路径未明确

- **位置**: §4.3 单一 public typed projection, citation 行
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 要求"不得继续新建或复制 `dict[str, Any]` 签名"、"不得用 cast、shim 或重新拼字段建立第二个 citation owner"、"不得改变 R07 字段、必填性或 identity 语义"。
- **反例/失败场景**: 当前 `result_types.py` 中 7 个 citation 字段全部是 `dict[str, Any]`。R07 的 `Citation` 是 `dayu.fins.domain.tool_models` 中的 frozen dataclass（`@dataclass(frozen=True)`），不是 TypedDict；其 `to_dict()` 方法返回 `dict[str, Any]`，且移除 `None` 值键。Plan 禁止 `dict[str, Any]` 和第二个 owner，但未明确说明实现 agent 应如何处理 citation typing。直接 import `Citation` dataclass 作为 TypedDict 字段类型不匹配（dataclass 不是 TypedDict）；使用 `Mapping[str, JsonValue]` 丢失键检查；使用 `Citation.to_dict()` 的返回类型仍是 `dict[str, Any]`。
- **为什么有问题**: Implementation agent 必须自行决定 typing 策略。三种路径都有 trade-off：
  1. Import `Citation` 并声明 `citation: Citation` — 类型安全但要求调用方构造 `Citation` 实例而非 dict
  2. 使用 `Mapping[str, JsonValue]` — 满足 plan 禁止 `dict[str, Any]` 的要求但丢失键检查
  3. 新建一个与 `Citation` 同构的 `PublicCitation(TypedDict)` — 严格 typed 但违反 plan 禁止第二个 citation owner
- **直接证据**:
  - `result_types.py:251` — `citation: dict[str, Any]`（当前 FinancialStatementResult）
  - `result_types.py:290` — `citation: dict[str, Any]`（当前 XbrlQueryResult）
  - `tool_models.py:86-125` — `@dataclass(frozen=True) class Citation`，`to_dict() -> dict[str, Any]`
  - `tool_models.py:107` — `source_type: str`（不是 SourceType enum 直接类型）
  - `result_types.py:23-28` — 已 import R07 的 `FinancialPeriod`、`FinancialScale`、`StatementLocator` 等 TypedDict 类型
- **影响**: Implementation agent 可能选择不同策略导致 review cycle 延长。
- **建议改法和验证点**: 在 plan 中明确 citation typing 策略。考虑到 plan 禁止 `dict[str, Any]` 且禁止第二个 citation owner，建议采用 `Mapping[str, JsonValue]` 作为新 financial/XBRL public result 的 citation 字段类型（与 plan §4.3 "签名使用 `Mapping[str, JsonValue]` 输入与 JsonValue-compatible strict mapping 输出"一致）。同时明确不修改其它 result 类型中已有 `dict[str, Any]` citation 字段（不在 R08 scope）。验证：pyright 零错误、新 result 的 citation 键与 R07 `Citation.to_dict()` 一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R08-MIMO-F03-未修复-低-S1 未提交破坏性边界 pyright 策略需 review agent 共识

- **位置**: §5.4 验证门, S1 pyright 策略段
- **问题类型**: 可执行性风险
- **当前写法**: "S1 modified-owner scoped pyright/类型验证必须零；同时必须执行 full pyright。Full pyright 在 S1 内部未提交破坏性边界上只允许出现预声明 S2 direct-consumer allowlist（`dayu/fins/tools/result_types.py`、`read_runtime_helpers.py`、`read_runtime.py`、`fins_tools.py`）内、且能逐条对应已删除 producer 字段/类型的传播错误"。
- **反例/失败场景**: S1 删除 `statement_locator`/`StatementLocator` 后，`result_types.py:260` 的 `statement_locator: StatementLocator` 字段和 `read_runtime.py:2096` 的 `"statement_locator": statement_payload["statement_locator"]` 会产生 pyright 错误。这些在 S2 预期修复。但 review agent 如果不了解 S1/S2 是同一次破坏性 cutover 的设计意图，可能会在 S1 review 中要求修复这些错误，导致 S1 scope 膨胀。
- **为什么有问题**: Plan 的策略是正确的——S1/S2 不做中间 commit，S1 允许精确的 S2 预期传播错误。但双路 reviewer 必须理解并接受这一策略，否则会在 S1 review 中产生 rejected findings。
- **直接证据**:
  - `result_types.py:27,260` — `StatementLocator` import 和 `statement_locator` 字段
  - `read_runtime.py:2096` — `"statement_locator": statement_payload["statement_locator"]`
  - Plan §5.6: "S1 不做中间 commit。S1 与 S2 是同一次破坏性 contract cutover"
- **影响**: Review agent 可能在 S1 review 中要求修复 S2 scope 的错误，导致 fix/re-review cycle 延长。
- **建议改法和验证点**: 在 plan §5.4 或 §5.6 中显式列出 S1 完成后 full pyright 预期出现的 S2 propagation 错误清单（文件、symbol、旧字段、S2 迁移动作），作为 review agent 的裁决依据。Controller entry validation §3 `R08-PE-F04` 已建立此规则，但 plan 本身应自足说明。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R08-MIMO-F04-未修复-低-七值 reason 闭集中 `statement_not_found` 合并语义需显式说明

- **位置**: §3.1 Financial producer contract, §4.1 Financial producer typed contract
- **问题类型**: 实施指导不足
- **当前写法**: Plan 将 `statement_method_missing`、`statement_empty` 合并为 `statement_not_found`，七值闭集为 `unsupported_statement_type`、`xbrl_not_available`、`statement_not_found`、`low_confidence_extraction`、`scale_unavailable`、`period_semantics_unavailable`、`scale_and_period_semantics_unavailable`。
- **反例/失败场景**: 当前 `sec_processor.py:629` 使用 `statement_method_missing` 表示 processor 没有对应 statement type 的方法；`sec_processor.py:639,658` 使用 `statement_empty` 表示方法存在但返回空。两者合并为 `statement_not_found` 后，implementation agent 需要理解这是"方法缺失或结果为空"的统一业务语义，而不是"文件未找到"。
- **为什么有问题**: 七值闭集本身是正确的（每个值都有独立业务恢复动作），但 `statement_not_found` 的合并语义可能被 implementation agent 误解为 storage-level file-not-found，而非 processor-level method/empty 归一。
- **直接证据**:
  - `financial_result_contract.py:31,33` — 当前 `statement_method_missing`、`statement_empty`
  - `sec_processor.py:629` — `base_result["reason"] = "statement_method_missing"`
  - `sec_processor.py:639,658` — `base_result["reason"] = "statement_empty"`
  - `bs_report_form_common.py:378,386,391` — 同上
  - Plan §4.1 失败语义表："method absent、method 返回 None、空表、空 rows → partial + `statement_not_found`"
- **影响**: Implementation agent 可能在迁移时保留 method/empty 分支而非统一归一。
- **建议改法和验证点**: Plan 已在 §4.1 失败语义表中明确四类观测统一为 `statement_not_found`。建议在 §5.2 实施顺序第 3 步补充一行："method absent/None/empty 统一为 `statement_not_found`；不保留 method/empty 分支 reason"。验证：producer tests 断言四类观测均产出 `statement_not_found`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R08-MIMO-F05-未修复-低-XBRL `query_params` flat typed shape 与当前 processor `filters_applied` 的迁移路径

- **位置**: §4.2 XBRL processor-internal typed contract
- **问题类型**: 实施指导不足
- **当前写法**: Plan 要求删除 `filters_applied` 嵌套 shape，producer 直接输出 flat typed params。
- **反例/失败场景**: 当前 `sec_processor.py:716-726` 和 `bs_report_form_common.py:303-313` 构造 `filters_applied: dict[str, JsonValue]` 嵌套在 `query_params` 中。Plan 的 target shape 是 flat `XbrlQueryParams`（`concepts`、`statement_type`、`period_end` 等）。Implementation agent 需要将 `filters_applied` 中的字段提升到 `query_params` 顶层。
- **为什么有问题**: Plan 正确识别了 shape drift，但未说明迁移路径：processor 当前将 filters 嵌套在 `filters_applied` 中，read 从 `query_params` 顶层读取同名键并补 `None`。Plan 的 flat shape 要求 processor 直接输出顶层字段，read 只复制。
- **直接证据**:
  - `sec_processor.py:716-726` — `filters_applied` 构造
  - `bs_report_form_common.py:303-313` — `filters_applied` 构造
  - `result_types.py:274-283` — 当前 `XbrlQueryParams`（flat，已有目标 shape）
  - `xbrl_result_contract.py:28` — 当前 `query_params: dict[str, JsonValue]`（untyped）
- **影响**: Implementation agent 可能保留 `filters_applied` 嵌套并在 read 侧做 flat 展开（即保留当前 shape drift）。
- **建议改法和验证点**: Plan §5.2 第 2 步已写"建立 flat typed query params；exact-key validation 统一拒绝未知字段"。建议补充："processor 输出 `query_params` 时直接使用 `XbrlQueryParams` 顶层键（`concepts`、`statement_type`、`period_end` 等）；删除 `filters_applied` 嵌套；`xbrl_result_contract.py` 的 validator 要求 exact keys"。验证：processor tests 断言 `query_params` 无 `filters_applied` 键且顶层键与 typed contract 一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R08-MIMO-F06-未修复-中-plan 最小 XBRL 示例 `source_type="sec_filing"` 与当前 SourceType 不一致

- **位置**: §4.4 Tool schema、description与LLM文本, 最小XBRL示例
- **问题类型**: 事实错误
- **当前写法**: Plan 最小示例中 citation 的 `source_type` 值为 `"sec_filing"`：
  ```json
  "citation": {
    "source_type": "sec_filing",
    "document_id": "opaque-document-id",
    "ticker": "AAPL",
    "source_provider": "SEC_EDGAR"
  }
  ```
- **反例/失败场景**: 当前代码中 `SourceType` enum（`dayu/fins/domain/tool_models.py:17-34`）定义为 `SEC_EDGAR = "SEC_EDGAR"`。`read_runtime.py:148-153` 的 `_FILING_SOURCE_TYPES_BY_PROVIDER` 映射确认 SEC filing 的 `source_type` 值为 `"SEC_EDGAR"`（通过 `SourceType.SEC_EDGAR.value`）。全仓 `rg 'sec_filing' dayu/ tests/` 零命中——`"sec_filing"` 在代码库中不存在。Implementation agent 若将此示例作为 tool description 的最小示例写入 `fins_tools.py`，LLM 会看到一个不存在的 `source_type` 值，可能在生成报告时使用错误的来源标注。
- **为什么有问题**: Plan §4.4 要求示例"自足说明字段、类型、必填性、枚举与最小示例"，且"不得暴露 processor 类名、method 状态、raw count、dedupe diagnostic、revision、snapshot key 或内部错误消息"。但示例中的 `source_type` 值本身就不正确，违反了 plan 自身的自足说明要求。
- **直接证据**:
  - `tool_models.py:20` — `SEC_EDGAR = "SEC_EDGAR"`
  - `tool_models.py:17-34` — `SourceType` enum：`SEC_EDGAR`、`CNINFO`、`HKEXNEWS`、`UPLOADED`、`SUPPLEMENTARY`
  - `read_runtime.py:148-153` — `_FILING_SOURCE_TYPES_BY_PROVIDER`：`FinsSourceProvider.SEC_EDGAR -> SourceType.SEC_EDGAR`
  - `rg -n 'sec_filing' dayu/ tests/` — 零命中
  - Plan §4.4 最小示例 — `"source_type": "sec_filing"`
- **影响**: Implementation agent 将示例写入 tool description 后，LLM 看到不存在的 `source_type` 值，可能在报告中使用 `"sec_filing"` 而非 `"SEC_EDGAR"` 标注来源。
- **建议改法和验证点**: 将 plan 最小示例中的 `"source_type": "sec_filing"` 改为 `"source_type": "SEC_EDGAR"`。验证：示例中的 `source_type` 值与 `SourceType` enum 一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## 4. Review Coverage Evidence

以下为本次 review 独立检查的维度与直接证据摘要：

### 4.1 七值 reason 动作性

| reason | 业务恢复动作 | 直接证据 |
|---|---|---|
| `unsupported_statement_type` | 不再请求此 statement type | Plan §4.1 |
| `xbrl_not_available` | 改用 HTML/OCR 抽取 | Plan §4.1 |
| `statement_not_found` | 尝试其它 document/method | Plan §4.1; 当前 method_missing/empty 合并 |
| `low_confidence_extraction` | 谨慎使用抽取结果 | Plan §4.1 |
| `scale_unavailable` | 无法确定倍率 | Plan §4.1 |
| `period_semantics_unavailable` | 无法确定财期 | Plan §4.1 |
| `scale_and_period_semantics_unavailable` | 两者均不可靠 | Plan §4.1 |

结论：每个值均有独立业务恢复动作。删除的 `statement_method_missing`、`statement_empty`（→ `statement_not_found`）、`processor_error:`、`invalid_statement_result`（→ 删除）均为 producer 内部诊断，无独立业务恢复动作。

### 4.2 Actual producer/consumer/test allowlist 完整性

**Producer inventory**：
- `sec_processor.py` — financial + XBRL ✓（allowlist）
- `bs_report_form_common.py` — financial + XBRL ✓（allowlist）
- `bs_six_k_processor.py` — financial + XBRL ✓（allowlist）
- `html_financial_statement_common.py` — financial only ✓（allowlist）
- `six_k_form_common.py` — financial only ✓（allowlist）
- `sec_xbrl_query.py::build_statement_locator` — locator helper ✓（allowlist delete target）
- `financial_base.py` — Protocol 引用 ✓（allowlist, propagation only）
- `sec_report_form_common.py` — 消费 common ✓（allowlist, propagation only）
- `report_form_financial_statement_common.py` — fallback reason ✓（allowlist）

**Consumer inventory**：
- `result_types.py` — public financial/XBRL result ✓（S2 allowlist）
- `read_runtime_helpers.py` — normalize/dedup ✓（S2 allowlist）
- `read_runtime.py` — financial/XBRL projection ✓（S2 allowlist）
- `fins_tools.py` — tool descriptions ✓（S2 allowlist）

**Alternate owner**：
- `sec_fiscal_fields.py::_build_financials_payload` — dead code（仅测试调用，plan 删除动作正确）

**Test inventory**：
- S1: `test_financial_read_contracts.py`、`test_sec_pipeline_download.py`、`test_processor_registry.py`（必跑） ✓
- S2: `test_fins_read_runtime.py`、`test_read_runtime_semantic_ownership_guards.py`、`test_processor_read_consistency.py`、`test_fins_storage_provider.py` ✓
- Aggregate: 上述全部 + `test_fins_ingestion_tools.py` ✓

### 4.3 `query_params` shape drift 直接证据

- `sec_processor.py:716-726` — `filters_applied: dict[str, JsonValue]` 嵌套
- `bs_report_form_common.py:303-313` — `filters_applied: dict[str, JsonValue]` 嵌套
- `xbrl_result_contract.py:28,100` — `query_params: dict[str, JsonValue]`（untyped，接受任何 shape）
- `result_types.py:274-283` — `XbrlQueryParams`（flat typed，已有目标 shape）
- Plan 诊断正确：producer 嵌套 + read 顶层补 None = shape drift

### 4.4 `total`/`deduped_fact_count`/`fact_count` source-of-truth

- `sec_processor.py:756` — `total = len(facts)`（processor-local 重复派生）
- `bs_report_form_common.py:343` — `total = len(facts)`（同上）
- `xbrl_result_contract.py:102-104` — validator 要求 `total == len(facts)`
- `read_runtime_helpers.py:1219-1220` — `total=validated.total`, `deduped_fact_count=len(deduped_facts)`
- `result_types.py:293-294` — `total: int`, `deduped_fact_count: int`（双 count 公开）
- `fins_tools.py:978-980` — tool description 显式文档化 total/deduped_fact_count
- Plan 诊断正确：`total` 是 processor-local `len(facts)` 重复派生，不是 provider raw validation fact；`fact_count` 将在 S2 作为唯一 public count 引入

### 4.5 Public citation strict typing 且 R07 no-touch

- `result_types.py` 当前 citation 为 `dict[str, Any]`（7 处）
- Plan §4.3 禁止 `dict[str, Any]`、cast、shim、第二个 citation owner
- R07 citation owner: `dayu.fins.domain.tool_models.Citation`（frozen dataclass，非 TypedDict）
- `result_types.py` 已从 R07 domain import `FinancialPeriod`（TypedDict）、`FinancialScale`（`Literal["units", "thousands", "millions", "billions"]` TypeAlias）、`StatementLocator`（TypedDict）
- R07 snapshot/borrow/revision/citation 在 `read_runtime.py` 中完整存在（lines 193-280）
- Plan §6.7.D 要求 R07 no-touch scan

### 4.6 Host ToolTruncateSpec cursor envelope/fetch_more 组合裁决

- Controller validation §5 已裁决：`fact_count == len(facts)` 是 Fins pre-Host 不变量；Host envelope 是独立治理层
- Plan §6.4 要求 S2 验证 under-limit + forced-truncation 两类路径
- Plan §6.4 stop rule: 若 Fins serializer 把 Host envelope 重新承诺为普通 facts list，stop 回 Controller
- 当前 `query_xbrl_facts` 声明 Host `ToolTruncateSpec`（evidence from plan）
- Plan 不修改 Host、不私造 cursor/fetch_more ✓

### 4.7 Coverage/pyright/Ruff/scans/smoke

- S1 coverage: 逐文件 `>=80%`，只列实际修改文件 ✓
- S2 coverage: 同上 ✓
- pyright: S1 modified-owner scoped 零 + full pyright 必跑 + S2 后 full pyright 零 ✓
- Ruff: S1 必改文件中已有两个 F401（`bs_report_form_common.py` 未使用 `Path`、`sec_processor.py` 未使用 `pandas`）✓
- Scans: internal positive inventory + public negative + `fact_count` unique owner + R07 no-touch ✓
- 真实 smoke: AAPL XBRL fixture + HTML financial table + no-statement path ✓

### 4.8 Review/commit 顺序

- S1: AgentCodex → Controller validation → AgentMiMo + AgentDS 并发 review → Controller adjudication → fix → 双路 re-review → Controller 关闭 ✓
- S2: 同上（S1+S2 cumulative diff）✓
- Aggregate: aggregate validation + aggregate 双路 deepreview ✓
- Commit: S1/S2 闭环后才允许一个 exact-scope local implementation commit ✓

### 4.9 Compat/fallback/shim 和 R09-R12/Issues/统一 authorization

- Plan §2.3 明确 out-of-scope ✓
- Plan §8 禁止补救表 ✓
- Issues 142、151、175、177、178 不在 R08 scope ✓
- 统一 authorization 不实现 ✓
- R09-R12 顺序继续 ✓

### 4.10 `_build_financials_payload` dead code 验证

- `rg -n '_build_financials_payload' dayu/ tests/` — 仅 `sec_fiscal_fields.py:95` 定义 + `test_sec_pipeline_download.py:2113,2120,2121` 测试调用
- `rg -n '_resolve_processed_fiscal_fields' dayu/` — 仅 `sec_fiscal_fields.py:174` 定义，零 production 调用
- `sec_fiscal_fields.py:203` — `_extract_fiscal_from_financials(financials_payload)` 不调用 `_build_financials_payload`
- `sec_fiscal_fields.py:227-255` — `_resolve_download_fiscal_fields` 调用 `_extract_download_fiscal_from_xbrl` + `_infer_download_fiscal_fields`，不调用 `_build_financials_payload` 或 `_resolve_processed_fiscal_fields`
- 结论：Plan 的"无 production caller"断言正确。F01 初版 reviewer 证据错误，已撤回。

### 4.11 Plan 最小示例 `source_type` 验证

- `tool_models.py:17-34` — `SourceType` enum values: `SEC_EDGAR`、`CNINFO`、`HKEXNEWS`、`UPLOADED`、`SUPPLEMENTARY`
- `read_runtime.py:148-153` — SEC filing → `SourceType.SEC_EDGAR.value` = `"SEC_EDGAR"`
- `rg -n 'sec_filing' dayu/ tests/` — 零命中
- Plan §4.4 最小示例 `"source_type": "sec_filing"` — 与代码不一致，见 F06

## 5. Open Questions

无。所有 finding 均有直接证据和可执行 fix。

## 6. Residual Risks And Suggested Tracking Destination

| 残留风险 | 追踪目的地 |
|---|---|
| Host `ToolTruncateSpec` 无法原子维护 `fact_count` sibling 字段 | Issue #177（TruncationManager 接通） |
| `query_xbrl_facts` tool description 中 total/deduped_fact_count 文案需同步更新 | R08-S2（fins_tools.py 在 S2 allowlist） |
| `result_types.py` 中非 financial/XBRL 的 `dict[str, Any]` citation 字段 | R07 / 后续 WU（不在 R08 scope） |
| `sec_fiscal_fields.py` 中 `_extract_fiscal_from_xbrl_query` 的 XBRL validator 消费迁移 | R08-S1（传播新 validator） |

## 7. Verdict

**pass-with-risks**

R08 plan 在 owner 边界、reason 闭集、query_params shape、fact_count 单一同源、Host truncation 组合裁决、exact allowlists、验证矩阵、review/commit 顺序和 out-of-scope 声明上均基于直接代码证据，设计合理且 code-generation-ready。

六项 finding 中一项已撤回（F01 reviewer 自身证据错误）、一项为中等严重（F06 最小示例 `source_type` 值不一致）、四项为低严重（F02-F05 实施指导细节）。F01 撤回后，plan 的 `_build_financials_payload` 删除动作正确。F06 若不修复会导致 tool description 中出现不存在的 `source_type` 值，影响 LLM 来源标注准确性。F02-F05 不会阻塞实施但会增加 review cycle。

建议 Controller 裁决 F06 为 accepted plan fix（修正示例 `source_type` 为 `"SEC_EDGAR"`），F02-F05 为 accepted 或 informational（补充实施指导细节）。无 rejected finding。Plan fix 后需双路 complete re-review。
