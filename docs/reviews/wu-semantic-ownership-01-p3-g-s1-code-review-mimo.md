# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S1

## Scope

- Mode: current changes (unstaged workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `e5e4ad97` (S1 plan accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s1-code-review-mimo.md`
- Included scope: 16 files (+223/-220) — S1 SEC form and shared domain typed values
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Findings

未发现实质性问题。

逐项检查：

### 1. `filing_semantics.py` 作为单一真源

`dayu/fins/domain/filing_semantics.py` 定义：

- `SecFormType` / `FiscalPeriod` / `DocumentQuality` / `FinancialDataQuality` — 封闭 Literal 类型别名。
- `SEC_FORM_TYPES` / `FISCAL_PERIODS` / `DOCUMENT_QUALITIES` / `FINANCIAL_DATA_QUALITIES` — 封闭值 frozenset。
- `SEC_FORM_GROUP_SC13D_G` / `SEC_SC13_FORMS` — SC 13D/G 组合别名与展开常量。
- `_SEC_FORM_ALIASES` — 完整别名映射表（28 条），覆盖 `10K`、`10-K/A`、`def 14a`、`SC13D/G`、`SCHEDULE 13D` 等。
- `normalize_sec_form_type_for_matching(...)` — 匹配用标准化，未知值只做大写保留，由调用方支持集合决定。
- `parse_sec_form_type(...)` — 单一 SEC form 解析，fail closed on 组合别名/不支持 form。
- `parse_sec_form_filter_value(...)` — 下载筛选解析，允许 `SC 13D/G` 组合别名。
- `expand_sec_form_aliases(...)` — 别名展开，`SC 13D/G` → 4 个单一 form。
- `normalize_fiscal_period(...)` — 财期解析，fail closed on 非法值。
- `sanitize_fiscal_period_by_sec_form(...)` — 按 SEC form 约束财期。
- `normalize_document_quality(...)` — 文档质量解析，空值默认 `full`。
- `normalize_financial_data_quality(...)` — 财务数据质量解析，fail closed。

模块只依赖标准库和 `typing`，不 import pipeline / storage / processor / tool。✅

### 2. `form_type_utils.py` 完全删除

- `dayu/fins/processors/form_type_utils.py` 已删除（`git status` 显示 `D`）。
- `cat` 确认文件不存在。
- Source scan `rg -n "form_type_utils"` 零匹配（exit code 1）。
- Source scan `rg -n "normalize_form\(|normalize_form_type\(|_normalize_form\(|_normalize_form_type\(|_normalize_report_form_type\(|_normalize_form_for_fiscal\("` 零匹配（exit code 1）。
- `sec_form_section_common.py` 和 `sec_report_form_common.py` 的 `__all__` 已移除 `_normalize_form_type` / `_normalize_report_form_type` 导出。✅

### 3. SEC 用户输入 fail closed vs provider raw rows normalize/skip

**用户输入路径** — `parse_sec_form_type(...)` / `parse_sec_form_filter_value(...)`：
- 空输入 → `ValueError("form_type 不能为空")`
- 组合别名 `SC 13D/G` → `parse_sec_form_type` 抛 `ValueError`（单一 form 不允许组合别名）；`parse_sec_form_filter_value` 允许。
- 不支持 form → `ValueError("form_type 不支持")`

**Provider raw rows 路径** — `normalize_sec_form_type_for_matching(...)`：
- 空输入 → `None`
- 已知别名 → canonical form
- 未知非空值 → 大写保留，由调用方支持集合决定

`sec_filing_collection.py:108-110`：`normalized_form = normalize_sec_form_type_for_matching(...)` + `if normalized_form is None: continue` + `if normalized_form not in form_windows: continue`。未知 provider row 被跳过，不报错。✅

`sec_sc13_filtering.py:567-570`：同样模式。✅

### 4. 下游消费一致性

| 消费方 | 旧调用 | 新调用 | 一致性 |
|---|---|---|---|
| `sec_processor.py` | `normalize_form_type` | `normalize_sec_form_type_for_matching` | ✅ |
| `bs_report_form_common.py` | `normalize_form_type` | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_report_form_common.py` | `normalize_form_type` | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_form_section_common.py` | `normalize_form_type` | `normalize_sec_form_type_for_matching` | ✅ |
| `read_runtime_helpers.py` | `normalize_form_type` | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_form_utils.py` | `normalize_form` (local) | `parse_sec_form_filter_value` | ✅ |
| `sec_fiscal_fields.py` | `_normalize_form_for_fiscal` (local) | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_sc13_filtering.py` | `_normalize_form` (local) | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_filing_collection.py` | `normalize_form` (import) | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_rebuild_workflow.py` | `_normalize_form_for_fiscal` (import) | `normalize_sec_form_type_for_matching` | ✅ |
| `DocumentSummary.from_dict` | 无校验 | `normalize_fiscal_period` + `normalize_document_quality` | ✅ |
| `RejectedFilingArtifact.from_meta_dict` | 无校验 | `parse_sec_form_type` + `normalize_fiscal_period` | ✅ |

### 5. S2/S3/S4 scope 未被误实现

- **S2 (CN/HK report selection)**: `sec_rebuild_workflow.py` 参数从 `normalize_form` 改为 `parse_sec_form`，但这是 rename + domain helper 消费，不是 CN/HK downloader filtering 迁移。CN/HK downloader 未修改。✅
- **S3 (typed rejection registry)**: `sec_sc13_filtering.py` 只删除了本地 `_normalize_form` 函数并改为消费 domain helper，未修改 rejection registry contract（仍为 `dict[str, dict[str, str]]`）。✅
- **S4 (XBRL total contract)**: `read_runtime_helpers.py` 只修改了 `_normalize_form_type_for_matching` 的 import 来源，未修改 `_normalize_xbrl_query_payload` 中 `total` 的覆写逻辑。✅

### 6. 测试、pyright、coverage

- **Tests**: 84 passed, 3 warnings（edgartools deprecation，非本轮引入）。
- **Pyright**: 0 errors, 0 warnings。
- **Coverage**: `filing_semantics.py` 80.43%（≥80% 阈值）。未覆盖行主要是 `normalize_sec_form_type_for_matching` 的 `None` 返回路径（由下游调用方测试覆盖）和 `sanitize_fiscal_period_by_sec_form` 的部分分支。
- **Source scans**: 旧 normalizer pattern 零匹配；`form_type_utils` 零匹配。
- **`git diff --check`**: 通过。

### 7. README

`dayu/fins/README.md` 更新了两处：Fins 专属契约描述增加 "SEC form parser / alias expansion、财期、文档质量与财务数据质量"；目录树增加 "SEC form / 财期 / 质量封闭值 parser"。内容在 `dayu/fins/` Agent update constraints 范围内。✅

## Residual Risk

- **`DocumentSummary.form_type` 仍为 `Optional[str]`**: 因为 summary 同时承载 SEC、CN/HK 和 material forms。S1 只对 SEC 单一 form 和 rejected SEC artifact decode 收口。Plan 已记录此 tradeoff。
- **`FinancialDataQuality` parser 已建立但未消费**: S4 XBRL result contract 未在 S1 实现。
- **`_normalize_optional_period` 行为变更**: 旧代码对 `"Q5"` 返回 `"Q5"`（上写入）；新代码返回 `None`（fail open to absent）。这是正确语义——非法财期不应被持久化。

## Verdict

**PASS** — S1 正确实现了 plan 中的 SEC form 和 shared domain typed values。`form_type_utils.py` 完全删除，所有消费方迁移至 domain helper，SEC 用户输入 fail closed，provider raw rows normalize/skip，未误实现 S2/S3/S4 scope。
