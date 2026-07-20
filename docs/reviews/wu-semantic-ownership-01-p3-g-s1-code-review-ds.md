# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S1

## Scope

- Mode: current changes (unstaged)
- Branch: `phaseflow/host-issues-control`
- Slice: P3-G S1 — SEC form and shared domain typed values
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s1-code-review-ds.md`
- Included scope: 16 files (+223/-220)
- Validation: `pytest` 84 passed, `pyright` 0 errors, coverage 80.43%

## Verdict

**PASS** — 无 material finding。S1 正确将 SEC form/fiscal period/document quality/financial data quality 的解析真源收束到 `dayu/fins/domain/filing_semantics.py`，旧 `form_type_utils.py` 已完全删除且无兼容 wrapper 残留，所有下游消费者均改为消费 domain truth。

---

## Findings

未发现实质性问题。

---

## Review Focus 逐项核实

### 1. `filing_semantics.py` 作为 single source of truth

新模块（`dayu/fins/domain/filing_semantics.py`）结构验证：

| 组件 | 设计 | 核实 |
| --- | --- | --- |
| 依赖 | 只依赖 `re`, `typing`（标准库） | ✅ 无 import pipeline/storage/processor/tool |
| 类型定义 | `SecFormType`, `FiscalPeriod`, `DocumentQuality`, `FinancialDataQuality` — 四种 `Literal` TypeAlias | ✅ 行 14-39 |
| Alias 表 | `_SEC_FORM_ALIASES` 覆盖 30+ 历史变形（含 `SCHEDULE 13D` → `SC 13D` 全系列） | ✅ 行 92-125 |
| User input path | `parse_sec_form_filter_value` → fail closed；`expand_sec_form_aliases` → expand `SC 13D/G` | ✅ 行 194-240 |
| Provider raw row path | `normalize_sec_form_type_for_matching` → 未知值不抛异常，由调用方窗口/支持集合过滤 | ✅ 行 144-167 |
| Single filing path | `parse_sec_form_type` → 拒绝组合别名 + 拒绝不支持 form | ✅ 行 170-191 |
| Fiscal period | `normalize_fiscal_period` → Fail closed on invalid；`sanitize_fiscal_period_by_sec_form` → form-aware constraint | ✅ 行 243-292 |
| Document quality | `normalize_document_quality` → 空值默认 `full`；非法值 fail closed | ✅ 行 295-316 |
| Financial data quality | `normalize_financial_data_quality` → 非空必校验 | ✅ 行 319-342 |

### 2. `form_type_utils.py` 完全删除，无隐藏 wrapper

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 文件删除 | ✅ | `git diff --stat` 显示 `form_type_utils.py \| 82 ---------------------` |
| 无 import 残留 | ✅ | `rg -n "form_type_utils" dayu/fins/` → exit 1 |
| 无调用残留 | ✅ | `rg -n "normalize_form_type\(|_normalize_form_for_fiscal\(|_normalize_report_form_type\(|_normalize_form\(" dayu/fins/` → exit 1 |
| `sec_form_utils.py` 更新 | ✅ | `normalize_form` → `parse_sec_pipeline_form`（委托 `parse_sec_form_filter_value`）；旧 alias 表全删除 |
| `sec_fiscal_fields.py` 更新 | ✅ | `_normalize_form_for_fiscal` 删除；全部调用点改为 `normalize_sec_form_type_for_matching`；`_sanitize_fiscal_period_by_form` 委托 `sanitize_fiscal_period_by_sec_form` |
| 无兼容 re-export | ✅ | 无 "from old_module import new_helper" wrapper |

### 3. SEC user input fail-closed vs provider raw row skip

| 场景 | 函数 | 行为 | 核实 |
| --- | --- | --- | --- |
| 用户 CLI form filter | `parse_sec_form_filter_value` + `expand_sec_form_aliases` | 非法值抛 `ValueError` | ✅ `test_shared_domain_parsers_reject_invalid_values` 覆盖 |
| Provider submissions raw row | `normalize_sec_form_type_for_matching` | 未知 form 大写保留，调用方自己的窗口集合决定 skip/keep | ✅ 行 167: `_SEC_FORM_ALIASES.get(alias_key, stripped.upper())` |
| Rejected filing decode | `parse_sec_form_type` | 非法值抛 `ValueError`（包括组合别名） | ✅ `RejectedFilingArtifact.from_meta_dict` 行 562 |
| Processor selection | `normalize_sec_form_type_for_matching` | 未知 form 大写保留 → `SecProcessor.supports_form` 返回 `False` | ✅ `sec_processor.py:269` 用 `_parse_processor_sec_form` |

### 4. 所有下游消费者一致使用 domain truth

| 消费者 | 导入 | 核实 |
| --- | --- | --- |
| `sec_processor.py` | `normalize_sec_form_type_for_matching as _parse_processor_sec_form` | ✅ |
| `bs_report_form_common.py` | `normalize_sec_form_type_for_matching as _parse_report_sec_form` | ✅ |
| `sec_report_form_common.py` | `normalize_sec_form_type_for_matching as _parse_report_sec_form` | ✅ |
| `sec_form_section_common.py` | `normalize_sec_form_type_for_matching as _parse_section_sec_form` | ✅ |
| `sec_form_utils.py` | `parse_sec_form_filter_value`, `expand_sec_form_aliases`, `SEC_FORM_GROUP_SC13D_G` | ✅ |
| `sec_fiscal_fields.py` | `normalize_fiscal_period`, `normalize_sec_form_type_for_matching`, `sanitize_fiscal_period_by_sec_form` | ✅ |
| `sec_filing_collection.py` | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_rebuild_workflow.py` | `normalize_sec_form_type_for_matching` | ✅ |
| `sec_sc13_filtering.py` | `normalize_sec_form_type_for_matching` | ✅ |
| `read_runtime_helpers.py` | `normalize_sec_form_type_for_matching` | ✅ |
| `document_models.py` | `parse_sec_form_type`, `normalize_fiscal_period`, `normalize_document_quality` | ✅ |

**全部 11 个消费者均从 `dayu.fins.domain.filing_semantics` 导入，无绕过。**

### 5. S1 未越界到 S2/S3/S4

| Slice | 行为 | S1 状态 |
| --- | --- | --- |
| S2 CN/HK report selection | pipeline helper 迁移 downloader 过滤 | ❌ 未实现 — 正确 |
| S3 rejection registry | typed entry 替换 dict shape | ❌ 未实现 — 正确 |
| S4 XBRL total | processor contract validation | ❌ 未实现 — `normalize_financial_data_quality` parser 已添加（plan 允许），但未 wired into XBRL result validation |

`normalize_financial_data_quality` 在 S1 中的存在是合理的——它是共享 domain parser 的一部分（plan S1 scope 包含 "document quality / financial data quality parser"），S4 将消费它。

### 6. Tests, pyright, coverage, typing, docstrings

| 检查项 | 状态 |
| --- | --- |
| Tests 覆盖 SEC form parser 所有 alias + invalid | ✅ `test_sec_form_domain_parser_accepts_supported_aliases` + `test_shared_domain_parsers_reject_invalid_values` |
| Tests 覆盖 DocumentSummary decode fail-closed | ✅ `test_document_summary_decode_rejects_invalid_fiscal_period_and_quality` |
| pyright 0 errors | ✅ |
| Coverage 80.43% | ✅ 超过 80% 门槛 |
| `filing_semantics.py` 全部函数有中文 docstring | ✅ 每个 parse/normalize 函数都有完整 Args/Returns/Raises |
| `SecFormType`/`FiscalPeriod`/`DocumentQuality`/`FinancialDataQuality` 使用 `Literal` TypeAlias | ✅ |
| 无 `Any` / `object` 类型扩大 | ✅ 新代码全部使用 `Literal`、`Optional[str]`、`cast` |
| 无 `hasattr`/`getattr` 绕过 | ✅ |
| 无魔法字符串扩用 | ✅ 所有枚举值集中在 `filing_semantics.py` |

---

## Owner Boundary Assessment

| 事实 | Producer | Validator (S1) | Consumer |
| --- | --- | --- | --- |
| SEC form | User CLI / SEC submissions / source meta | `filing_semantics.py` — `parse_sec_form_filter_value` / `normalize_sec_form_type_for_matching` / `parse_sec_form_type` | Processors, fiscal helpers, SC13, collection, rebuild, read runtime |
| Fiscal period | Upload args / SEC DEI / CN/HK inference | `normalize_fiscal_period` / `sanitize_fiscal_period_by_sec_form` | Source/processed meta, read filters, document sorting |
| Document quality | Processed repository commit | `normalize_document_quality` | `DocumentSummary.from_dict`, `_resolve_processed_quality` |
| Financial data quality | Processor XBRL result | `normalize_financial_data_quality` | S4 (future XBRL result validation) |

---

## Adversarial Failure Pass

- **`parse_sec_form_type("SC13D/G")` → fail**: `normalize_sec_form_type_for_matching` 返回 `SEC_FORM_GROUP_SC13D_G` → 行 187-188 检测到组合别名 → `ValueError`。✅
- **`parse_sec_form_filter_value("SC13D/G")` → pass**: 行 213-214 显式允许组合别名返回。✅
- **`normalize_sec_form_type_for_matching(None)` → None**: 行 161-162。✅
- **`normalize_sec_form_type_for_matching("")` → None**: 行 163-165。✅
- **`normalize_sec_form_type_for_matching("F-1")` → "F-1"**: 非 alias，保留大写。调用方自己过滤。✅
- **`normalize_fiscal_period(None)` → None**: 行 257-258。✅
- **`normalize_fiscal_period("")` → None**: 行 259-261。✅
- **`normalize_document_quality(None)` → "full"**: 默认值。✅
- **`normalize_document_quality("")` → "full"**: 空字符串默认。✅
- **`normalize_financial_data_quality("")` → ValueError**: 必填字段，非空。✅
- **`_sanitize_fiscal_period_by_form` 旧 inline implementation 已删除**: 新实现委托 `sanitize_fiscal_period_by_sec_form`，form-aware constraint 不变。✅

---

## Residual Risk

- **`DocumentSummary.form_type` 仍为 `Optional[str]`**: 这是有意的——`DocumentSummary` 同时承载 SEC/CN/HK/material form 值。S1 对 form_type 只做 `_optional_str` 归一化，SEC 单一 form parser 只在 rejected artifact decode 中强制校验。plan 接受此边界。
- **`FinancialDataQuality` parser 未接入 XBRL result**: S4 将消费此 parser，当前仅定义 + 测试，无运行时消费路径。
- **`sec_form_utils.py` 保留了 `parse_sec_pipeline_form`**: 这是一个 3 行薄 wrapper（委托 `parse_sec_form_filter_value`），但保留在 pipeline 层作为 `sec_form_utils` 的公共 API 入口。非兼容 shim——它是 pipeline 自己的 API boundary。
