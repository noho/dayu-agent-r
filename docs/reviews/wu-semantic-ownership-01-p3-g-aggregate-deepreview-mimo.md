# Aggregate Deepreview — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts`
- Accepted commits:
  - Plan: `e5e4ad97`
  - S1 SEC form/shared domain typed values: `79629dfa`
  - S2 CN/HK report selection ownership: `92320413`
  - S3 typed SEC download rejection registry: `c0386fa2`
  - S4 XBRL processor result contract: `cbbad162`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-aggregate-deepreview-mimo.md`

## Cross-Slice Source Finding Closure

### AgentDS 7 — SEC form normalization drift

**Status**: 已关闭 ✅

- `dayu/fins/processors/form_type_utils.py` 已删除。
- Source scan `rg -n "form_type_utils"` 零匹配。
- 所有 SEC form normalization 消费方（processors、pipelines、read runtime、SC13、rebuild workflow）统一消费 `dayu.fins.domain.filing_semantics.normalize_sec_form_type_for_matching(...)` / `parse_sec_form_type(...)` / `parse_sec_form_filter_value(...)`。

### AgentDS 8 — naked strings (`fiscal_period`, `form_type`, `quality`, `data_quality`)

**Status**: 已关闭（S1 覆盖共享 parser surface）✅

- `SecFormType` / `FiscalPeriod` / `DocumentQuality` / `FinancialDataQuality` 为封闭 Literal 类型别名。
- `DocumentSummary.from_dict(...)` 在 decode 边界校验 `fiscal_period`（`normalize_fiscal_period`）和 `quality`（`normalize_document_quality`）。
- `RejectedFilingArtifact.from_meta_dict(...)` 在 decode 边界校验 `form_type`（`parse_sec_form_type`）和 `fiscal_period`（`normalize_fiscal_period`）。
- `DownloadRejectionEntry.__post_init__` / `from_dict(...)` 校验 `form_type` 为 canonical SEC form。
- `DocumentSummary.form_type` 仍为 `Optional[str]`（承载 SEC + CN/HK + material forms），plan 已记录此 tradeoff。

### AgentMiMo BI-1 — downloader-owned financial-report filtering and fiscal inference

**Status**: 已关闭 ✅

- `cninfo_downloader.py` / `hkexnews_downloader.py` 不再拥有 `_is_title_blocked`、`_infer_fiscal_year`、`_infer_fiscal_period_from_text`、`_looks_like_english_report_text`。
- Source scan `rg -n "_is_title_blocked|_infer_fiscal_period_from_text|_infer_fiscal_year|_looks_like_english_report_text" dayu/fins/downloaders` 零匹配。
- 产品级业务筛选由 `dayu.fins.pipelines.cn_report_selection` 持有。
- `CnFiscalPeriod: TypeAlias = FiscalPeriod` 消费共享 domain 类型，无第二个 Literal 定义。

### AgentMiMo SS-10 — download rejection registry hidden shape

**Status**: 已关闭 ✅

- `DownloadRejectionEntry` / `DownloadRejectionRegistry` 是唯一 contract。
- Repository protocol 签名为 `DownloadRejectionRegistry`。
- Source scan `dict[str, dict[str, str]]` 在 public contracts 中零匹配；仅 `_fs_maintenance_core.py` 局部 serialization payload。
- 坏 registry fail closed（`ValueError`），不再静默 `str(...)` coercion。

### AgentCodex 11 — XBRL facts result `total` recomputed by read runtime

**Status**: 已关闭 ✅

- `dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)` 校验 raw `total`（非 bool int、≥ 0、`== len(raw_facts)`）。
- `_normalize_xbrl_query_payload(...)` 先调 validator，再做 normalization / dedupe。
- `normalized_payload["total"] = validated.total`（保留 processor raw total，不重算）。
- `deduped_fact_count` 仅在 dedupe 后数量不同时设置。
- Source scan `"total": len(deduped_facts)` 零匹配。

## Cross-Slice Consistency

| Slice | Domain Owner | Consumer Consistency | Residual |
|---|---|---|---|
| S1 | `filing_semantics.py` | 12+ call sites统一消费 | `DocumentSummary.form_type` 仍为 `Optional[str]` |
| S2 | `cn_report_selection.py` | downloaders 委托 pipeline helper | `CnReportDiscoveryClientProtocol` 仍返回 `CnReportCandidate` |
| S3 | `DownloadRejectionEntry` | pipeline/SC13/diagnostics/ingestion runtime 统一消费 | 旧坏 registry 文件会 fail closed |
| S4 | `xbrl_result_contract.py` | read runtime + fiscal inference 统一消费 | coverage 刚好 80% |

## Propagation Audit

1. **SEC form**: 用户输入 → `parse_sec_form_filter_value` / `expand_sec_form_aliases`（fail closed）→ pipeline form expansion / collection filtering / fiscal helper → processor selection → source/processed summary decode → read runtime matching。所有路径消费 domain helper。✅

2. **CN/HK report selection**: HTTP endpoint → downloader raw DTO → `cn_report_selection.py` 业务筛选 → `CnReportCandidate` → workflow → source/blob commit。downloader 不拥有业务筛选。✅

3. **SEC rejection registry**: SEC pipeline policy decision → `DownloadRejectionEntry` → `FilingMaintenanceRepositoryProtocol` typed registry → skip/diagnostic/SC13 consumers。无 `dict[str, dict[str, str]]` public contract。✅

4. **XBRL facts result**: processor `query_xbrl_facts(...)` → `xbrl_result_contract.validate_xbrl_facts_result_payload(...)` → read runtime normalization/dedup/projection。processor-owned `total` 不被覆盖。✅

## Validation

- **Aggregate tests**: 174 passed, 3 warnings。
- **Pyright**: 0 errors。
- **`git diff --check`**: 通过。
- **Source scans**: S1 `form_type_utils` 零匹配；S2 downloaders 业务筛选函数零匹配；S3 public contracts `dict[str, dict[str, str]]` 零匹配；S4 `"total": len(deduped_facts)` 零匹配。

## Residual Risk

- S4 `xbrl_result_contract.py` 覆盖率 80%，刚好满足 gate。
- 旧 workspace 坏 `_download_rejections.json` 会 fail closed；P3-G 按新 schema 起库处理，不做兼容迁移。
- `DocumentSummary.form_type` 仍为 `Optional[str]`（SEC + CN/HK + material），plan 已记录。

## Verdict

**PASS** — P3-G 四个 slices 共同关闭了所有 source findings。SEC form normalization 收束到 `filing_semantics.py`，CN/HK report selection 从 downloader 迁入 pipeline helper，SEC rejection registry 改为 typed contract 且坏 registry fail closed，XBRL facts `total` 由 domain validator 校验且 read runtime 不再覆盖。无新 material finding。
