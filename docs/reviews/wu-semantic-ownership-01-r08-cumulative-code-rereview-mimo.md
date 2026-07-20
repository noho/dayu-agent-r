# WU-SEMANTIC-OWNERSHIP-01 / R08 Cumulative Code Re-Review (MiMo)

## 1. Scope

- **Mode**: Current Changes (cumulative, immutable tree)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `b1a0631f397967e7530b676a90ef7467d83a1817^`（umbrella scope start）
- **Review scope**: 23-path cumulative diff（working tree vs HEAD，含未暂存修改），覆盖 `dayu/fins + tests`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-mimo.md`
- **Parallel review coverage**: 无（单 reviewer 独立完成）

## 2. SHA / Lock 验证

| Item | Controller value | Independent recompute | Status |
|---|---|---|---|
| cumulative `git diff --binary -- dayu/fins tests` SHA-256 | `01c2a1d5...3092d` | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` | MATCH |
| guards content SHA-256 | `44d9eaad...471a` | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` | MATCH |
| fix artifact SHA-256 | `29596e30...2edc` | `29596e309d194bb898b80803e9cc0f7faa9f76285e9af2e8ba98b00c07ed2edc` | MATCH |
| S1 artifact | `d97eed50...5748` | `d97eed5065bb4a6449122581447419fd11e984b8440320cc5147f15a369c5748` | MATCH |
| S2 artifact | `08085bde...648` | `08085bdeff711c010346a71f680411a559e742559ce8370f59b51e8651bf0648` | MATCH |
| changed paths | 23 | 23（16 product + 7 test） | MATCH |
| staged | empty | `git diff --cached --name-only` 无输出 | MATCH |

**结论**: 所有 locks 匹配，cumulative tree 未被篡改。无 drift，不触发 STOP。

**重要说明**: SHA `01c2a1d5...3092d` 对应 working tree vs HEAD（含未暂存修改），不是 committed `b1a0631f^..HEAD` diff（SHA `a7ce0bd0...afd`）。未暂存修改是 R08 最终状态的一部分，已纳入 review scope。

## 3. Corrected Finding Closure Ledger

### R08-CR-CF01: generic/compat nodes 与 imports 删除

**状态: CLOSED**

- **正确范围**: `tests/fins/test_fins_read_runtime.py` 四个 generic/compat test nodes 删除与九 imports 删除
- **复核**: 当前 test 文件只从 `dayu.contracts`、`dayu.fins.pipelines`、`dayu.fins.tools.cache` 和 `dayu.fins.tools.read_runtime_helpers` 导入四个模块级符号。无 generic/compat import 残留。LRU、form matching、XBRL payload validation 和 fiscal inference 四类 focused tests 替代了旧 generic/compat nodes。

### R08-CR-PCF02: dead helper deletion 与 actual typed/sorted owner

**状态: CLOSED**

- **正确范围**: `read_runtime_helpers.py` dead `_collect_available_document_types` definition/caller/import 全零；`read_runtime.py` actual `_collect_available_document_types_for_source_documents` typed/sorted owner 保留
- **复核**: `grep -rn "_collect_available_document_types" dayu/fins/tools/read_runtime_helpers.py` 返回空。`read_runtime.py:705` 有 `_collect_available_document_types_for_source_documents` 定义，`read_runtime.py:925` 有调用。dead helper 已完全删除。

### R08-CR-PCF03: guard test 与唯一 import/三断言

**状态: CLOSED**

- **正确范围**: guards 中 `test_document_type_resolver_projects_material_other_and_cn_categories` 与唯一 `resolve_document_type_for_source` import/三断言
- **复核**: `test_read_runtime_semantic_ownership_guards.py:57` 导入 `resolve_document_type_for_source`。测试在行 1974、1981、1988 有三个断言：`material`（form_type=UNLISTED_MATERIAL, source_kind=MATERIAL）、`other`（form_type=None, source_kind=FILING）、`annual_report`（form_type=FY, source_kind=FILING）。唯一 import，三断言，无 bypass。

### R08-CR-PCF04: exact 391/485 与 [344,346,348,442]

**状态: CLOSED**

Controller validation 证实 prefix-five `387/485 = 79.79%`，fresh prefix-six `391/485 = 80.62%`，new executed lines `[344,346,348,442]`。

### R08-VAL-PY-F01: suggestion/caption/page_no presence asserts

**状态: CLOSED**

- **正确范围**: suggestion/caption/page_no presence asserts
- **复核**: `test_list_documents_projects_stable_document_type_and_filter_contract` 断言 `"suggestion" not in filtered_result`（行 1545）和 `"suggestion" in no_match_result`（行 1555）。`test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref` 断言 `"caption" in records_result`（行 1686）和 `"page_no" in records_result`（行 1688）。presence asserts 正确。

### R08-VAL-PY-F02: protocol-compatible fixture

**状态: CLOSED**

test-only taxonomy 使用 optional keyword default `taxonomy: str = "US-GAAP"`。processor 对全部 protocol-valid calls 可调用。

### R08-VAL-PY-F03: XBRL TypeGuard

**状态: CLOSED**

`_is_xbrl_query_result` 使用 test-local `TypeGuard[PublicXbrlQueryResult]`，只以 `"facts" in result` 收窄。

## 4. Topic 6 产品裁决重新挑战

### 4.1 Financial producer contract / reason / quality / scale / terminal validator

**裁决: PASS**

当前 `FinancialStatementResult` TypedDict 包含 `statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`、`reason`（NotRequired）。与 README 行 117 和 design.md 行 60-63 一致。

`validate_financial_statement_result_payload()` 实现完整质量/原因矩阵：
- `partial` 必须有 `reason`，完整结果不得有 `reason`；
- `units` 不得承载 scale；
- rows + direct evidence 必须与 `determine_financial_statement_quality()` 一致。

`statement_locator`、raw labels、`statement_method_missing`、`statement_empty` 按 design.md 行 67-68 和 controller discussion 行 514 裁决，保持内部或删除。当前代码正确实现裁决后的最小契约。

### 4.2 XBRL flat params / typed validation / raw immutability / dedup / fact_count 单一同源

**裁决: PASS**

当前 `XbrlFactsResult` TypedDict 包含 `query_params`、`facts`、`data_quality`。与 README 行 119 和 design.md 行 70-78 一致。

- `XbrlQueryParams` 是 frozen dataclass，flat params 正确；
- `validate_xbrl_facts_result_payload()` 校验 required keys（`query_params`、`facts`、`data_quality`）；
- dedup 在 `_normalize_xbrl_query_payload()` 中完成；
- `fact_count` 唯一赋值 owner 在 `project_xbrl_query_result()` 中 `len(returned_facts_copy)`；
- `total` 和 `deduped_fact_count` 按 design.md 行 75-78 和 controller discussion 行 514 裁决，不在公共契约中。当前代码正确实现。

### 4.3 Public types / LLM-facing description

**裁决: PASS**

- `PublicFinancialStatementResult` 和 `PublicXbrlQueryResult` 是唯一公共 TypedDict；
- `project_financial_statement_result()` 和 `project_xbrl_query_result()` 复制所有引用容器；
- LLM-facing descriptions 自足说明字段、枚举、reason 安全动作和最小示例。

### 4.4 list_documents suggestion

**裁决: PASS**

- `list_documents` 只组合 filing/material typed list 与 meta 投影，不构造 per-document snapshot；
- `match_status == "no_match"` 时生成 `suggestion`，包含 `action: "broaden_filter"` 和 `available_document_types`。

### 4.5 Service / CLI 不得重复 terminal 判定

**裁决: PASS**

- `FinsDirectStreamProtocolError` 在 producer 未产出 `RESULT` 或产出重复 `RESULT` 时抛出；
- Service/CLI 只消费 `FinsEvent(PROGRESS | RESULT)`，不自行判定终态。

### 4.6 HKEX / R09-R10 deferred 边界

**裁决: PASS**

- HKEX downloader 逻辑未在 R08 中修改；
- R09-R12、Issues 142/151/175/177/178 未偷带进 R08 diff。

## 5. Findings

**未发现实质性问题。**

当前 working tree 实现与 README、design.md 和 controller discussion 裁决一致。所有 R08 cumulative findings 已正确关闭。

## 6. Semantic Owner Drift 检查

**结论: 无 semantic owner drift**

- financial result contract 由 `dayu.fins.domain.financial_result_contract` 唯一持有；
- XBRL result contract 由 `dayu.fins.domain.xbrl_result_contract` 唯一持有；
- SEC form / 财期 / 质量 parser 由 `dayu.fins.domain.filing_semantics` 唯一持有；
- `fact_count` 唯一赋值 owner 在 `project_xbrl_query_result()`；
- citation 由 read runtime `_build_citation()` 从 snapshot provenance 派生；
- read runtime 不补写 period、scale、quality 或 reason。

## 7. Compat / Fallback / Shim / Any / Cast / Ignore 检查

**结论: 无问题**

- `cast()` 使用均为窄化 cast（验证后的 Literal 收窄）；
- 无 `hasattr` / `getattr` 用于逃避类型设计；
- 无 `type: ignore` / `pyright: ignore`；
- 无兼容性 re-export、wrapper 或 facade。

## 8. Overcoupling / LLM-facing / README / 测试 Owner / Coverage 检查

**结论: 均无问题**

- 无跨层耦合；
- LLM-facing 文本自足、不暴露内部标识；
- README 与代码一致；
- 测试断言 owner 级 contract 行为；
- 15/15 production files coverage >= 80%。

## 9. R07 / Security / No-Code / Deferred 边界检查

**结论: PASS**

- R07 snapshot/citation 未修改；
- Topic 8 no-code、Topic 9 未实现统一 authorization；
- 安全机制保留；
- R09-R12、Issues 142/151/175/177/178 未偷带。

## 10. Validation Evidence 核验

| Evidence | Status |
|---|---|
| 392 prefix/aggregate | PASS |
| 391/485 coverage | PASS（prefix-six 80.62%） |
| 859/1 existing skip | PASS |
| 15/15 >= 80% | PASS |
| pyright zero | PASS（independent recompute） |
| Ruff | PASS |
| tests 33/33 pass | PASS（independent recompute） |
| smokes/scans/diff check | PASS |

## 11. Verdict

**PASS — 未发现实质性问题。**

R08 cumulative tree 正确实现裁决后的最小契约。所有 locks 匹配无 drift。所有 original cumulative findings 已关闭。Topic 6 产品裁决全部通过。无 semantic owner drift、无 compat/fallback、无 overcoupling、无 LLM-facing 问题。

## 12. Open Questions

- 无。

## 13. Residual Risk

- 无 unclassified residual risk。
- Docling real upload integration 仍由 Issue 175 控制。
- 三条 `edgar` dependency deprecation warnings 不影响 exit。
