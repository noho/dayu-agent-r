# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Code Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main` (workspace changes + committed S1-S2 on top of main)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-mimo.md`
- Included scope: S3 implementation diff（S3 allowed production files、S3 tests、`dayu/fins/README.md`）、implementation artifact、controller validation artifact
- Excluded scope: S1/S2 已提交 diff（除非 S3 回归触达）、R3-E/tool-security
- Parallel review coverage: 无

## Review Focus

1. **Fiscal owner**：`filing_semantics` 的 `normalize_fiscal_year` / `normalize_fiscal_period` / `fiscal_period_recency_rank` 是否成为唯一真源；`read_runtime` 是否无 date-year inference、FY fallback、第二 rank map、dead helper。
2. **Dataframe optional string owner**：`value_normalization` helper 类型/语义是否满足 None/blank/NaN/pd.NA/pd.NaT/0/False 矩阵；三个 SEC processor 是否无本地 wrapper/漂移。
3. **README 当前契约**：是否只写已落地事实，覆盖 S1-S3 current Fins developer contract，无 work-unit/future/security 文本。
4. **AGENTS.md**：中文 docstring、无 Any/object 签名逃逸、无不当 getattr/hasattr、无兼容 shim、无工具安全代码。

## Findings

未发现实质性问题。

## Evidence Summary

### 1. Fiscal owner

| 检查项 | 结果 |
| --- | --- |
| `normalize_fiscal_year` 严格只接受正整数，bool/0/负/浮点/文本 fail closed | ✓ `filing_semantics.py:289-292`，bool 先于 int 检查 |
| `normalize_fiscal_period` 只接受 FY/H1/Q1-Q4，非法非空值抛 ValueError | ✓ `filing_semantics.py:255-269` |
| `fiscal_period_recency_rank` 使用 immutable tuple `_FISCAL_PERIOD_RECENCY_ORDER`，None/未知=0，Q1=1, Q2=2, H1=3, Q3=4, Q4=5, FY=6 | ✓ `filing_semantics.py:83,296-311` |
| `_parse_source_document_meta` 调用 domain `normalize_fiscal_year` 和 `normalize_fiscal_period`，不再 inline isinstance 判断 | ✓ `read_runtime.py:360-369`（working tree diff） |
| `_source_document_recency_sort_key` 调用 domain `fiscal_period_recency_rank` | ✓ `read_runtime.py:453`（working tree diff） |
| `_FISCAL_PERIOD_SORT_ORDER` 在 read_runtime.py 已删除 | ✓ `read_runtime.py:167-176`（旧 9 行 mutable dict 已移除） |
| `_infer_fiscal_year`、`_infer_fiscal_period`、`_resolve_fiscal_year_with_fallback`、`_resolve_fiscal_period_with_fallback` 在 read_runtime_helpers.py 已删除 | ✓ 共删除约 170 行（helpers diff 行 91-108, 376-411, 814-944） |
| `_FISCAL_PERIOD_SORT_ORDER` 在 read_runtime_helpers.py 已删除 | ✓ `read_runtime_helpers.py:126-133`（旧 mutable dict 已移除） |
| `build_document_recency_sort_key`、`_build_recommended_documents` dead helpers 已删除 | ✓ 各约 40-60 行 |
| `_extract_year` dead helper 已删除 | ✓ 约 20 行 |
| read runtime `_get_source_document_summaries` 不再调用 `_infer_fiscal_period`/`_infer_fiscal_year`/`_resolve_*_with_fallback` | ✓ `read_runtime.py:2090-2110`（working tree diff）直接使用 `meta["fiscal_year"]` 和 `meta["fiscal_period"]` |
| 零残留扫描：`_FISCAL_PERIOD_SORT_ORDER\|def _infer_fiscal_year\|def _infer_fiscal_period\|_resolve_fiscal_.*fallback\|build_document_recency_sort_key\|_build_recommended_documents` | ✓ 零匹配 |

### 2. Dataframe optional string owner

| 检查项 | 结果 |
| --- | --- |
| `value_normalization.normalize_optional_dataframe_string` 使用 `StringConvertible` protocol，无 Any/object | ✓ `value_normalization.py:15-31,34-55` |
| None/pd.NA/pd.NaT → None | ✓ `value_normalization.py:50` |
| float NaN → None | ✓ `value_normalization.py:52` |
| 空白文本 → None | ✓ `value_normalization.py:54-55`（`str(value).strip()` 后 falsy 检查） |
| 0 → "0" | ✓ `str(0).strip()` = `"0"` |
| False → "False" | ✓ `str(False).strip()` = `"False"` |
| 三份 `_normalize_optional_string` 私有 wrapper 已删除 | ✓ `sec_section_build.py`、`sec_table_extraction.py`、`sec_xbrl_query.py` 各删除约 15-23 行 |
| 三份 `_normalize_optional_string_base` import 已移除 | ✓ `sec_section_build.py`、`sec_table_extraction.py` 删除 `from dayu.documents.processors.text_utils import normalize_optional_string as _normalize_optional_string_base`；`sec_xbrl_query.py` 同 |
| `import pandas as pd` 在 `sec_section_build.py` 已移除（不再直接使用 pd.isna） | ✓ |
| 三个 consumer 全部 import 并调用 `normalize_optional_dataframe_string` | ✓ 共 26 处调用，零残留旧 wrapper 调用 |
| test 矩阵覆盖全部 9 个输入值 | ✓ `test_fiscal_normalization_contracts.py:187-218` |

### 3. README 当前契约

| 检查项 | 结果 |
| --- | --- |
| financial statement result required fields、quality/reason、scale/units | ✓ README 行 111 |
| XBRL result quality/reason、valid-empty/partial/all-failed | ✓ README 行 113 |
| storage source revision cache | ✓ README 行 99 |
| typed read degradation（decode/search/XBRL/source-change） | ✓ README 行 145 |
| fiscal parser/rank owner | ✓ README 行 475 |
| dataframe optional string owner | ✓ README 行 475 |
| upload ticker alias canonical/no-write-on-invalid | ✓ README 行 761 |
| 禁止词扫描 `R3-D\|plan gate\|future\|tool-security\|SSRF\|allowlist` | ✓ 零匹配（行 23 的 `work unit` 是 README 更新约束自身描述，不是写 work-unit 状态） |
| 无测试命令、无未落地能力 | ✓ |

### 4. AGENTS.md compliance

| 检查项 | 结果 |
| --- | --- |
| 新增函数全部有完整中文 docstring（Args/Returns/Raises） | ✓ `normalize_fiscal_year`、`fiscal_period_recency_rank`、`normalize_optional_dataframe_string`、`has_current_download_version`、`_normalize_ticker_aliases`（更新） |
| `value_normalization.py` 无 Any/object | ✓ |
| `filing_semantics.py` 新增函数无 Any/object | ✓ `normalize_fiscal_year` 参数为 `JsonValue \| None`，返回 `int \| None` |
| `sec_download_state.py` 新增函数无 Any/object | ✓ `has_current_download_version` 参数为 `Mapping[str, JsonValue] \| None` |
| `upload_company_meta.py` 无 strip().upper() alias 持久化 | ✓ 改为 `try_normalize_ticker` |
| 无兼容 shim/re-export | ✓ 旧 wrapper 直接删除，不做 re-export |
| 无工具安全代码 | ✓ |

## Open Questions

无。

## Residual Risk

- SEC downloader 的 3 处 `errors="ignore"` heuristic decode 路径仍在 `sec_downloader.py`，不在 S3 scope。后续收敛应由独立 Fins downloader decode-policy owner 处理。
- broad `DocumentMeta` type migration 与 6-K BS-only routing 保持不变，按 accepted plan 由后续 owner 处理。
- edgartools deprecated import warnings 仍存在，不影响当前 contract correctness。
