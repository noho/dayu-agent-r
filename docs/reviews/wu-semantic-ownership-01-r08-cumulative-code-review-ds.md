# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Code Review — AgentDS

## Gate 结论

- **Verdict**: PASS with 7 findings (2 HIGH, 4 MEDIUM, 1 LOW)
- **Review scope**: R08 S1+S2 累计 immutable tree；23 tracked changed paths + 2 artifacts
- **Immutable tree lock**:
  - Tracked `git diff --binary` SHA-256: `4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b` ✓（独立重算一致）
  - S1 artifact SHA-256: `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` ✓
  - S2 artifact SHA-256: `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` ✓
- **Review basis**: accepted final plan `87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`、Controller validation `1eb89632`、AGENTS.md、`docs/fins/design.md`、controller discussion、phaseflow umbrella optimization control
- **Stop**: 所有 findings 为 accepted-candidate 与非阻塞 risk，不得自行裁决；写回 Controller 后停止

---

## 1. 总体评估

R08 S1+S2 累计实现正确履行了 accepted plan §4–§6 的核心契约：producer 删除 locator/raw total/双 count，reason 改为 optional 七值闭集，flat query params 消除 nested `filters_applied` drift，tools 层建立唯一 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` public projection，`fact_count` 仅由 `result_types.py:401` builder 一处赋值，R07 citation/snapshot 零 diff，Host truncation composition 被三段公开链路的 forced-truncation 测试证明。

以下 finding 按 severity 分类；所有 finding 均附直接代码证据、root owner 与修复方向。未发现 accepted plan 明确禁止的 compat/shim/re-export/wrapper、`hasattr/getattr` 补偿、skip/xfail、`type: ignore`/`noqa`、`pragma: no cover`、private API 读取或 R07/R06/storage/Host/prompts 越界修改。

---

## 2. Findings

### 2.1 FS-DS-01 (HIGH) — Coverage tests 锁定了 OCR fallback 与 HTML table helper 的私有实现路径

**Severity**: HIGH — 测试通过 public API 间接覆盖大量 private helper（`_collect_ocr_page_texts`、`_collect_hidden_ocr_page_texts_from_image_containers`、`_collect_page_break_page_texts`、`_extract_first_date`、`_extract_fiscal_period_year`、`_infer_scale_from_caption` 等），但测试断言的是 public contract 输出（`statement_type`、`periods`、`rows`、`data_quality`、`reason`），而非验证这些私有 helper 的内部行为。这本身是正确设计——coverage 通过 public path 达成，断言在 owner boundary。

但存在一个隐蔽风险：`bs_six_k_processor.py` (80.17%) 和 `html_financial_statement_common.py` (80.34%) 的 coverage 刚过 80% 阈值，其剩余 19%+ 未覆盖行集中于：
- `_collect_fixed_layout_page_texts` 的 `id.startswith("Page")` 分支
- `_find_adjacent_statement_data_table` 的 classified_type in `_PRIMARY_EXTRACTABLE_STATEMENT_TYPES` 短路分支
- `_has_tiny_hidden_ocr_font` 的 `font` 缩写正则匹配分支
- `build_html_statement_result_from_tables` 的 `scale_unavailable` / `period_semantics_unavailable` 路径

**直接证据**: coverage JSON 逐文件 ledger 中 `bs_six_k_processor.py` 和 `html_financial_statement_common.py` 分别为 80.17% 和 80.34%；代码审查确认这些未覆盖分支处理 real-world edge cases（非标准 HTML style 拼写、fixed-layout page containers、多 statement table 紧邻扩展）。

**Root owner**: `tests/fins/test_financial_read_contracts.py` 与 `tests/fins/test_fins_storage_provider.py` —— coverage closure 测试集。

**修复方向**: 为 `test_real_bs_six_k_processor_uses_html_and_ocr_fallbacks` 的真实 fixture 增加 coverage 验证（如果现有 fixture 未触发这些分支），或在已有 test allowlist 内为这些唯一业务规则 owner 增加定向测试。不得通过 pragma/omit、changed-line coverage 或降低阈值接受。

**分类**: accepted-candidate — 当前 coverage 满足 80% 阈值，未覆盖分支均为真实 OCR/HTML 变体处理路径；不阻塞 review pass，但 Controller 应裁决是否需要在新 fixture 上补充 coverage 后再 lock final tree。

---

### 2.2 FS-DS-02 (HIGH) — `_BaseBsReportFormProcessor.get_financial_statement` 的 `xbrl_reason is None` RuntimeError 是防御性断言但缺少 fail-closed 语义说明

**Severity**: HIGH — 触及 production 行为。`bs_report_form_common.py:247`：

```python
if xbrl_reason is None:
    raise RuntimeError("XBRL 报表失败结果缺少业务原因")
```

`_get_statement_from_xbrl` 在所有正常路径上要么返回 `(result, None)`（成功），要么返回 `(None, reason)`（失败 + reason）。`xbrl_reason is None` 仅在内部逻辑错误时触发。该 RuntimeError 对调用方是不可恢复的，会导致整个 `get_financial_statement` 调用失败，进而通过 `FinsReadRuntime._get_financial_statement_with_borrow` 的 `except Exception` 路径传播为通用 `FinsReadBusinessError`。

**直接证据**: `bs_report_form_common.py` lines 239–247；read_runtime 中 `_get_financial_statement_with_borrow` 的裸 `processor.get_financial_statement(...)` 调用未被 try/except 包裹（只有 `validate_financial_statement_result_payload` 被包裹）。

**Root owner**: `dayu/fins/processors/bs_report_form_common.py::_BaseBsReportFormProcessor._get_statement_from_xbrl`

**修复方向**: 若这确实是 invariant guard（不可达代码），应改为 `assert xbrl_reason is not None` 或直接消除分支（因为所有正常路径都返回 reason）；若存在可达但未处理的路径，应在 producer terminal 统一处理为 `"statement_not_found"` 而非 RuntimeError。

**分类**: accepted-candidate — 当前逻辑在所有正常执行路径上都能返回合法 reason，RuntimeError 仅在代码 bug 时触发；Controller 应裁决是消除分支还是改为 assertion。

---

### 2.3 FS-DS-03 (MEDIUM) — `BsSixKFormProcessor.get_financial_statement` 丢弃 XBRL failure 的原始 reason

**Severity**: MEDIUM — 不影响 product contract（terminal reason 总是由 final path 决定），但丢失 intermediate diagnostic 信息。

当前路径：
1. XBRL（`_get_financial_statement_from_xbrl`）失败 → 返回 `None`（reason 被丢弃）
2. HTML tables（`_get_statement_tables` + `_build_statement_result_from_tables`）失败 → 返回 `None`
3. OCR fallback（`_get_statement_result_from_ocr_pages`）失败 → 返回 `None`
4. Terminal reason = `"statement_not_found"` 或 `"low_confidence_extraction"`

`SecProcessor` 和 `_BaseBsReportFormProcessor` 的 behavior 类似——中间失败原因不在 terminal result 中体现。

**直接证据**: `bs_six_k_processor.py` lines 364–393；`bs_report_form_common.py` lines 239–264；`sec_processor.py` lines 612–672。

**Root owner**: `dayu/fins/processors/bs_six_k_processor.py::BsSixKFormProcessor.get_financial_statement`

**修复方向**: 当前行为符合 accepted plan §4.1——只在 terminal 产生唯一 business reason。如果生产环境需要 XBRL→HTML→OCR 的完整降级链诊断，应在 R08 之外的独立 Fins diagnostic/log contract 中实现，不改 public reason。

**分类**: non-blocking risk — 当前 terminal reason 语义正确，中间丢失是设计意图；记录为 residual，后续 aggregate deepreview 可重新评估是否需要 internal diagnostic path。

---

### 2.4 FS-DS-04 (MEDIUM) — `_deduplicate_xbrl_facts` 的去重键混合使用 `normalized_fact` 和 `raw_fact` 作为两个不同信息源

**Severity**: MEDIUM — stable dedup 逻辑正确，但 `_build_fact_dedup_key` 从 `normalized_fact["period_end"]` 和 `raw_fact.get("fiscal_period")` 混合取值。当 `normalized_fact` 的 `period_end` 存在时，`dedup_fiscal_period` 固定为空（忽略 `raw_fact["fiscal_period"]`）。这与 docstring 描述一致，但要求 `normalized_fact["period_end"]` 和 `raw_fact["period_end"]` 的语义关系未在任何地方形式化。

**直接证据**: `read_runtime_helpers.py` lines 1351, 1368–1382（`_build_fact_dedup_key`）。

**Root owner**: `dayu/fins/tools/read_runtime_helpers.py::_build_fact_dedup_key`

**修复方向**: 将 `_build_fact_dedup_key` 改为只消费 `normalized_fact`（如果 `period_end` 已在 normalize 步骤中正确设置），或显式文档化两个参数的不同语义角色。当前混合消费不会导致错误（因为没有 `period_end` 的 fact 确实需要 `raw_fact` 的 `fiscal_period`），但评审人应记录此设计微妙性。

**分类**: non-blocking risk — 当前逻辑正确，测试覆盖了去重场景（`test_xbrl_query_payload_always_projects_dedup_count_and_owner_quality` 等六个 S2 nodes）；建议在后续 aggregate deepreview 中验证 `period_end` 与 `fiscal_period` 的互斥关系是否在所有 producer 路径上成立。

---

### 2.5 FS-DS-05 (MEDIUM) — `SecProcessor.get_financial_statement` 中 `base_result` 原地变异可能与 TypedDict 语义冲突

**Severity**: MEDIUM — `sec_processor.py` lines 602–672 中 `base_result` 被声明为 `FinancialStatementResult`（TypedDict），然后被原地修改（`base_result["reason"] = "xbrl_not_available"` 等）。TypedDict 在 Python runtime 中允许这种操作，但 `NotRequired` 字段的原地赋值绕过了类型检查器的 structural 验证。运行时不产生错误，但若 future type checker 变得严格，这些赋值可能产生误报。

**直接证据**: `sec_processor.py` lines 602–672；同样的 pattern 出现在 `bs_report_form_common.py` lines 226–264 和 `bs_six_k_processor.py` lines 351–393。

**Root owner**: `dayu/fins/processors/sec_processor.py::SecProcessor.get_financial_statement`

**修复方向**: 将 base_result 的构造方式改为 conditional build：先确定 reason，再一次性构造 `FinancialStatementResult`（与 `_get_statement_from_xbrl` 的成功路径一致）。当前 pattern 不会产生运行错误，但增加了 maintenance 风险。

**分类**: non-blocking risk — 当前运行时安全（TypedDict 在 Python runtime 中不强制 NotRequired），且被所有三个 processor 的 owner tests 覆盖；建议在后续 code cleanup slice 中统一为 immutable constructor pattern。

---

### 2.6 FS-DS-06 (MEDIUM) — `_FinancialStatementReadProcessor` Protocol 接受 `financials` 参数但所有实际实现均丢弃

**Severity**: MEDIUM — `read_runtime.py` 中定义的 `_FinancialStatementReadProcessor` Protocol 包含 `financials: Mapping[str, JsonValue] | None` 参数，但 `SecProcessor.get_financial_statement`、`bs_report_form_common._BaseBsReportFormProcessor.get_financial_statement`、`bs_six_k_processor.BsSixKFormProcessor.get_financial_statement` 均使用 `del financials` 忽略该参数。这不是 R08 引入的问题（Protocol 在 R07 或更早存在），但 R08 未清理此无消费语义的参数。

**直接证据**: `read_runtime.py` lines 534–545（Protocol 定义）；`sec_processor.py` line 597（`del financials`）；`bs_report_form_common.py` line 222；`bs_six_k_processor.py` line 347。

**Root owner**: `dayu/fins/tools/read_runtime.py::_FinancialStatementReadProcessor` Protocol

**修复方向**: 若 `financials` 参数无实际语义消费者，应从 Protocol 与实际 processor signatures 中删除。此清理不属于 R08 scope（R08 不改 Protocol signature），但应在后续 umbrella slice 中处理。

**分类**: non-blocking risk — pre-existing；不阻塞 R08 review pass，但记录为 residual。

---

### 2.7 FS-DS-07 (LOW) — `result_types.py` 中 `_FINANCIAL_STATEMENT_RESULT_DESCRIPTION` 字符串的 `period_end:string` token 与 `fiscal_period:FY|H1|Q1|Q2|Q3|Q4|null` token 之间的逗号分隔可能被 LLM 误解析

**Severity**: LOW — LLM-facing description 字符串使用中文逗号分隔字段说明，格式一致且自足。没有发现缺少字段、类型或枚举。唯一 minor concern：financial description 中 `period_end:string` 标记与 `fiscal_period:FY|H1|Q1|Q2|Q3|Q4|null` 之间的逗号在视觉上类似 CSV 分隔符，但实际测试 `test_financial_tool_descriptions_explain_owner_fields` 已通过精确 token 断言证明了所有关键子串在 description 中存在。

**直接证据**: `result_types.py` lines 284–307；`test_fins_storage_provider.py` lines 3855–3897。

**Root owner**: `dayu/fins/tools/result_types.py::_FINANCIAL_STATEMENT_RESULT_DESCRIPTION`

**修复方向**: 可选；当前 description 已在测试中逐 token 验证且满足 plan §4.4 的全部七项自足要求。

**分类**: 非阻塞 — 当前 description 自足且通过 owner test；不需要修改。

---

## 3. 逐项审查结果

### 3.1 Correctness

- **Producer contract 删除**: `statement_locator`、`build_statement_locator`、`statement_method_missing`、`statement_empty`、`processor_error`、`_build_financials_payload` 全部从 production code 删除。`rg` scan exit 1 / 零命中。✓
- **Reason 闭集**: financial reason 精确为七值闭集，complete/partial matrix 由 `validate_financial_statement_result_payload` 与 `validate_xbrl_facts_result_payload` 强制。✓
- **Method absent/None/empty 归一**: 三个 processor 均在 producer terminal 归一为 `"statement_not_found"`。✓
- **XBRL zero-hit**: `data_quality=xbrl`、`facts=[]`、reason 缺席；`query_xbrl_facts` 返回合法 completed result。✓
- **All-concepts-failed**: 继续抛 `XbrlQueryExecutionError`，不降级为 partial result。✓
- **Bool rejection**: `min_value`/`max_value` 的 `_optional_number` 在 `isinstance(value, bool)` 时先抛 ValueError，再检查 `isinstance(value, (int, float))`。`fiscal_year` 同样先拒绝 bool。Owner tests 覆盖了 True/False/int/float/缺席场景。✓

### 3.2 Producer/Public exact contract

- **Exact-key validation**: 两个 domain validator 均通过 `_validate_exact_keys` 拒绝 unknown keys。✓
- **旧 tools 类型名删除**: code scan 确认 `result_types.py` 只导出 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`；旧 `FinancialStatementResult` / `XbrlQueryResult` 在 tools 层不存在。domain 层原名保留（`dayu.fins.domain.financial_result_contract.FinancialStatementResult` 和 `dayu.fins.domain.xbrl_result_contract.XbrlFactsResult`）。✓
- **无 alias/re-export/wrapper**: AST 确认。✓
- **Citation 投影**: 两个 builder 接受 `Mapping[str, JsonValue]` 并使用 `dict(citation)` 创建独立副本，不 alias 输入。✓

### 3.3 Optional reason matrix

- Complete result 省略 reason（`NotRequired` 字段不在 dict 中）；partial result 必须有 reason。两个 validator 均强制执行。✓
- `reason: null` 被两个 validator 的 `_optional_*_reason` 函数拒绝。✓
- Financial reason 七值闭集，XBRL reason 二值闭集。✓
- Test coverage: `test_financial_read_contracts.py` 覆盖 complete+reason、partial 无 reason、未知 reason 等 fail-closed 场景。✓

### 3.4 Query params

- Flat `XbrlQueryParams` 替代旧 nested `filters_applied`。✓
- Optional filters 仅在 producer 明确提供时出现，不补 `None` 键。✓
- `fiscal_period` 消费共享 `FISCAL_PERIODS`（`FY|H1|Q1|Q2|Q3|Q4`）。✓
- `min_value`/`max_value` 使用 `int | float`，先拒绝 bool。✓
- Read runtime 中 `_normalize_xbrl_query_payload` → `validated.query_params.copy()` → `project_xbrl_query_result` 纯复制，不重组。✓

### 3.5 输入深层不变

- `validate_xbrl_facts_result_payload` 的 `_required_json_object_list` 对每个 fact 做 `dict(item)` 深复制。✓
- `_normalize_xbrl_query_payload` 再做 `[dict(raw_fact) for raw_fact in validated.facts]` 深复制。✓
- `_normalize_single_fact` 创建新 dict，不写入 raw_fact。✓
- `_deduplicate_xbrl_facts` 返回新 list。✓
- Owner tests 验证 raw payload immutability（`test_financial_read_contracts.py` 的 exact-key 与 deep-equality 断言）。✓

### 3.6 Stable dedup

- `_build_fact_dedup_key` 生成确定性 7-tuple。✓
- `_build_fact_selection_score` 使用确定性 tuple 比较。✓
- Tie-breaking by `source_index`（list order）。✓
- Final sort by `first_seen_index` 保持 first-seen 稳定顺序。✓
- S2 six nodes 覆盖 two-raw-facts-one-key、zero-hit、optional reason 场景。✓

### 3.7 唯一 fact_count owner

- Code scan (`rg -n fact_count`): 仅 `result_types.py:401` `fact_count=len(returned_facts_copy)` 为 production assignment。✓
- 所有其他出现：typed field (`result_types.py:279`)、description text (`result_types.py:314`)、example text (`result_types.py:323`)、README 语句、test assertions。✓
- `read_runtime.py`、`read_runtime_helpers.py`、`fins_tools.py`、`dayu/config/prompts` 无第二赋值。✓
- AST verification: 仅一个 `fact_count` keyword 在 production assignment 中。✓

### 3.8 Host truncation envelope/fetch_more composition

- `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` 正确验证三段公开链路：
  1. Pre-Host: `tool_definitions["query_xbrl_facts"].callable(...)` → direct callable seam，asserts `fact_count == len(facts)`、exact key set
  2. Post-Host: `runtime.tool_executor.execute(...)` → 真实 ToolRuntime，asserts same key set、non-facts siblings unchanged、`fact_count` preserved
  3. Fetch-more: reads `cursor`/`scope_token` from public envelope → `FrameworkToolName.FETCH_MORE` → asserts `[*visible, *remainder] == pre_facts_copy`
- 测试不读取私有 `_cursors`、`_truncated_public_value`、`TruncationManager` 内部状态。✓
- 不冻结 fixture facts 数量（`assert len(pre_facts_value) > _FORCED_XBRL_MAX_ITEMS`）。✓
- `_tool_runtime` helper 使用公开 `FrameworkToolPolicyView` 和 `enable_truncation_manager` flag，不改 Host 内部。✓

### 3.9 R07 snapshot/citation no-touch

- `git diff HEAD -- dayu/fins/tools/read_runtime.py` 的 citation 变更仅限于将 `"citation": citation` 改为 `citation=citation`（从 dict key 改为 keyword argument）。✓
- `_build_citation` 函数 body 零 diff。✓
- 21 个 snapshot/borrow/release/revision/citation/source-changed 函数 AST 与 HEAD 相同（S2 artifact claim + 独立 code review 确认）。✓
- Storage、Host、Engine、Service、UI、prompts 路径零 diff。✓

### 3.10 LLM-facing description 自足性

- `_FINANCIAL_STATEMENT_RESULT_DESCRIPTION` 包含：
  - 全部返回字段及业务含义 ✓
  - JSON 类型 ✓
  - required/optional ✓
  - `data_quality`/`scale`/`reason` 允许值 ✓
  - reason 仅在 partial 时出现 ✓
  - 七值 reason 的业务含义与安全下一动作 ✓
  - 最小 JSON 示例（使用 `SEC_EDGAR`，不含 `sec_filing`、processor method name、Host 治理术语）✓
- `_XBRL_QUERY_RESULT_DESCRIPTION` 同样自足。✓
- `test_financial_tool_descriptions_explain_owner_fields` 通过精确 token 匹配验证。✓
- `fins_tools.py` 的 tool descriptions 消费 `result_types.py` owner helpers，不手写第二份 contract。✓
- `fiscal_period.enum` 从 `sorted(FISCAL_PERIODS)` 派生为 `FY|H1|Q1|Q2|Q3|Q4`，不在 description 中手写第二份 literal enum；`min_value`/`max_value` 保持 JSON Schema `type: number`。✓

### 3.11 Security/deferred boundaries

- R06/R07 storage identity、revision、snapshot、citation、containment、symlink、atomic publication/recovery 零语义 diff。✓
- Host truncation owner 未改（Fins 不实现 cursor/fetch_more）。✓
- 未实施 R09–R12、Issues 142/151/175/177/178、统一 tool authorization。✓
- `dayu/config/prompts/**` 零 diff。✓
- Exact allowlist scan: 无超出 plan §5.1/§6.1 production/test/README allowlist 的路径。✓

### 3.12 Compat/shim/过度设计

- 无 `FinancialStatementResult` / `XbrlQueryResult` 旧 tools 类型名的 alias/re-export/wrapper。✓
- 无 `getattr`/`hasattr` 补偿。✓
- 无 `skip`/`xfail`。✓
- 无 `type: ignore`/`noqa`。✓
- 无 `# pragma: no cover`。✓
- 无 compatibility field、lazy import、cast/ignore、默认值、临时 adapter。✓
- `result_types.py` 的 `Any` 使用仅限于 pre-existing types（`NotSupportedResult`、`DocumentSectionsResult` 等），新的 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 不使用 `Any`。✓

### 3.13 Coverage closure tests 质量

逐项 adversarial 挑战结果：

- **测试只断言 public processor contract 还是锁定 private method?**
  - `test_real_sec_processor_reads_and_projects_aapl_fixture`: 经 `SecProcessor` public API（`supports` → `list_sections` → `read_section` → `search` → `get_financial_statement` → `query_xbrl_facts` → `get_xbrl_taxonomy`）验证结构化 output；不直接调用 `_get_xbrl()`、`_collect_*`、private cache。✓
  - `test_real_bs_six_k_processor_uses_html_and_ocr_fallbacks`: 经 `BsSixKFormProcessor.get_financial_statement` public API 验证 HTML/OCR 降级；不直接调用 private collector。✓
  - Coverage of private helpers（`_extract_first_date`、`_infer_scale_from_caption` 等）通过 public API paths 实现，断言在 public output contract 上。✓
- **有无 fake-only path 测试?**
  - `_FakeXbrl`、`_FakeFactQuery`、`_FakeStatements` 仅为 SEC processor 不完整 XBRL 场景（method absent、empty result、XBRL unavailable）的测试替身。真实 XBRL 路径通过 AAPL fixture 验证。✓
  - 没有发现仅通过 fake 验证而跳过真实路径的 contract 行为。✓
- **有无测试锁定偶然调用顺序?**
  - 没有测试断言 `_tables` 的内部顺序、cache hit/miss 次数、或 `OrderedDict` 内部状态。✓
- **有无测试仅为走行?**
  - 所有新增/修改测试均断言具体的 contract 字段、枚举值、reason 组合或等式条件；没有空 assertion 或仅 `assert True` 的测试。✓
- **Coverage 数字是否掩盖缺陷?**
  - 见 FS-DS-01（HIGH）：两个文件 coverage 仅略超 80%，未覆盖分支为 real-world edge cases。✓

---

## 4. 正向确认清单

| 项 | 状态 |
|---|---|
| Producer exact keys + optional reason | ✓ |
| 七值 financial reason + 二值 XBRL reason 闭集 | ✓ |
| Complete/partial reason matrix fail-closed | ✓ |
| Flat query params（无 `filters_applied`、无 `None` 补键） | ✓ |
| `fiscal_period` 共享 `FISCAL_PERIODS` owner | ✓ |
| Bool 被显式拒绝于 number/fiscal_year 输入 | ✓ |
| Raw facts/producer payload 深层不变 | ✓ |
| Stable dedup | ✓ |
| 唯一 `fact_count` production assignment（`result_types.py:401`） | ✓ |
| Host truncation pre/post/fetch-more 三段公开链路 | ✓ |
| R07 citation/snapshot no-touch（21 functions AST identical） | ✓ |
| LLM-facing description 自足（七项要求 + reason→下一动作矩阵） | ✓ |
| Tool description 消费 owner helper，不手写第二份 | ✓ |
| 无 compat shim/re-export/wrapper/alias | ✓ |
| 无 `getattr`/`hasattr`/skip/xfail/type:ignore/noqa/pragma | ✓ |
| 旧 tools 类型名 `FinancialStatementResult` / `XbrlQueryResult` 在 tools 层不存在 | ✓ |
| `_build_financials_payload` / `build_statement_locator` 完全删除 | ✓ |
| Exact allowlist 内无越界 path | ✓ |
| Full pyright 0 errors | ✓ |
| Scoped Ruff 0 | ✓ |
| 所有 15 个 changed production 文件 coverage ≥ 80.00% | ✓ |
| Forced-truncation 不读私有 Host state | ✓ |
| 测试不锁定 fake-only 行为 | ✓ |
| `fiscal_period` schema enum 从 `sorted(FISCAL_PERIODS)` 派生 | ✓ |
| 示例使用 `SEC_EDGAR`、无 `sec_filing`、无 processor 内部术语 | ✓ |

---

## 5. 未覆盖项与 residual risk

| 风险 | 分类 | destination |
|---|---|---|
| FS-DS-01: 两个文件 coverage 仅略超 80%，未覆盖 real-world edge cases | HIGH accepted-candidate | Controller adjudication；可能需在 test allowlist 内补充 coverage |
| FS-DS-02: `xbrl_reason is None` RuntimeError | HIGH accepted-candidate | Controller adjudication |
| FS-DS-03: 6-K XBRL→HTML→OCR 中间 reason 被丢弃 | MEDIUM non-blocking | R08 后 aggregate deepreview 评估是否需要 internal diagnostic path |
| FS-DS-04: dedup key 混合消费 normalized/raw facts | MEDIUM non-blocking | 后续 aggregate deepreview 验证 `period_end`/`fiscal_period` 互斥 |
| FS-DS-05: `base_result` 原地变异 pattern | MEDIUM non-blocking | 后续 code cleanup slice |
| FS-DS-06: `financials` dead parameter in Protocol | MEDIUM non-blocking | 后续 umbrella slice 清理 |
| FS-DS-07: description comma token ambiguity | LOW | 非阻塞 |
| 未验证 `period_end` 在所有 `XbrlQueryParams` consumer 中一致处理 | LOW | 后续 aggregate deepreview |
| R09–R12 deferred；R08 后 umbrella 仍 active | INFO | umbrella control doc |

---

## 6. Artifact metadata

- **Review type**: AgentDS independent cumulative code review
- **Reviewed tree**: 23 tracked changed paths + 2 untracked artifacts
- **Basis documents**: AGENTS.md, `docs/fins/design.md`, `docs/phaseflow-umbrella-optimization-control.md`, controller discussion, accepted plan, Controller validation, S1/S2 implementation artifacts
- **Review lock recalculated**:
  - Tracked `git diff --binary` SHA-256: `4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b` ✓
  - S1 artifact SHA-256: `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` ✓
  - S2 artifact SHA-256: `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` ✓
- **Reviewer**: AgentDS
- **Stop**: 所有 findings 为 accepted-candidate / non-blocking risk，不自行裁决；停止回 Controller
