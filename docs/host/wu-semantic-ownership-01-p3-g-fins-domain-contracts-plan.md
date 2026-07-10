# WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts Plan

## Gate / Scope

- Gate: plan
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts`
- Accepted upstream: P3-F deepreview commit `1f00491b`
- Output state: ready-for-plan-review

本计划只覆盖 P3-G。P3-G 完成后不关闭 umbrella `WU-SEMANTIC-OWNERSHIP-01`；后续 P3-H/P3-I/P3-J/P3-K 与 full-repo deepreview 仍由 controller 继续推进。

## First-Principles Motivation

P3-G 的共同问题是 Fins 财报业务事实还没有稳定的 domain/pipeline contract：SEC form、财期、质量标签、financial-report 过滤、rejection registry 和 processor result validity 被下游或 HTTP adapter 各自解释。买方财报 Agent 的 read / download / preprocess / upload 多入口会消费同一批事实；如果每个入口用字符串或隐式 dict shape 自行猜测，就会出现“仓储接受了非法值、read runtime 看起来能纠正、processor contract 违约被投影层掩盖”的语义漂移。

修复动机成立，但不能一次性重写全部 Fins 类型系统。本计划按语义 owner 闭环拆分：先统一 domain parser / typed values，再把 producer 边界改为校验和持久化 typed 值，最后移除下游 recompute / hidden dict shape。

## Source Finding Dispositions

| Source finding | Disposition | 当前判断 |
| --- | --- | --- |
| AgentCodex 11: XBRL facts result `total` is recomputed by read runtime, masking processor contract violations | current | `read_runtime_helpers._normalize_xbrl_query_payload(...)` 在消费 processor payload 后设置 `normalized_payload["total"] = len(deduped_facts)`，会覆盖 processor 返回的 `total`。processor contract 本身在 `sec_processor.py` 与 `bs_report_form_common.py` 返回 `total=len(facts)`。应让 processor/result normalization owner 校验一致性，而不是让 read runtime 静默重算必填字段。 |
| AgentDS 7: SEC form type normalization exists in three inconsistent places | current | 当前至少有 `processors/form_type_utils.py:normalize_form_type(...)`、`pipelines/sec_form_utils.py:normalize_form(...)`、`pipelines/sec_fiscal_fields.py:_normalize_form_for_fiscal(...)` 三套映射，且 alias 覆盖不一致，例如 `SC 13D/G` 只在 pipeline helper 支持。 |
| AgentDS 8: `fiscal_period`, `form_type`, and `quality` are naked strings across Fins domain | current-partial | CN/HK 下载模型已有 `CnFiscalPeriod` literal，但通用 domain/storage/read contract 仍大量使用 `Optional[str]` / `str`：`DocumentSummary.form_type/fiscal_period/quality`、`ProcessedUpsertRequest.form_type`、`financial_base.XbrlFactsResult.data_quality`、source/processed meta decode 均未 fail closed。 |
| AgentMiMo BI-1: financial-report filtering and fiscal inference live in downloader HTTP adapters | current with scope correction | SEC 6-K 已有 `pipelines/sec_6k_rules.py` pipeline-owned helper，不能回退；但 CNInfo/HKEXNews adapter 的 `list_report_candidates(...)` 当前执行 title block、language filter、period/year inference 和 per-period/year grouping。HTTP adapter 不应拥有产品级“哪份公告是财报”的业务过滤和 fiscal inference 真源。 |
| AgentMiMo SS-10: download rejection registry is `dict[str, dict[str, str]]` hidden shape protocol | current | `FilingMaintenanceRepositoryProtocol`、`_fs_maintenance_core`、`sec_download_state` 和 `sec_pipeline` 都以 `dict[str, dict[str, str]]` 传递 registry；字段 `reason/category/form_type/filing_date/download_version` 只由 `_record_rejection(...)` 隐式写入，读取方用字符串 key 解释。 |

## Direct Code Evidence

- XBRL total masking:
  - `dayu/fins/tools/read_runtime_helpers.py:1374` defines `_normalize_xbrl_query_payload(...)`.
  - `dayu/fins/tools/read_runtime_helpers.py:1413` sets `normalized_payload["total"] = len(deduped_facts)`.
  - `dayu/fins/processors/financial_base.py:32` defines `XbrlFactsResult.total`.
  - `dayu/fins/processors/sec_processor.py:725` and `dayu/fins/processors/bs_report_form_common.py:330` return `total=len(facts)`.
- SEC form normalization drift:
  - `dayu/fins/processors/form_type_utils.py:50` normalizes SEC forms for processors.
  - `dayu/fins/pipelines/sec_form_utils.py:38` defines another `normalize_form(...)`.
  - `dayu/fins/pipelines/sec_fiscal_fields.py:546` defines `_normalize_form_for_fiscal(...)`.
  - `dayu/fins/tools/read_runtime_helpers.py:494` wraps form matching through processor helper.
- Naked strings:
  - `dayu/fins/domain/document_models.py:647` has `ProcessedUpsertRequest.form_type: Optional[str]`.
  - `dayu/fins/domain/document_models.py:678` has `DocumentQuery.fiscal_periods: Optional[list[str]]`.
  - `dayu/fins/domain/document_models.py:690` has `DocumentSummary.form_type: Optional[str]`; `:693` has `fiscal_period: Optional[str]`; `:699` has `quality: str = "full"`.
  - `dayu/fins/processors/financial_base.py:26` uses `data_quality: str`; `:37` uses `data_quality: NotRequired[str]`.
  - `dayu/fins/storage/_fs_processed_core.py:338` reads `quality=str(merged_meta.get("quality", "full"))`.
- Downloader-owned filtering / inference:
  - `dayu/fins/downloaders/cninfo_downloader.py:274` `list_report_candidates(...)` queries HTTP and performs title blocking / fiscal year inference / grouping.
  - `dayu/fins/downloaders/cninfo_downloader.py:341` calls `_infer_fiscal_year(...)`; `:872` has `_is_title_blocked(...)`; `:1030` defines `_infer_fiscal_year(...)`.
  - `dayu/fins/downloaders/hkexnews_downloader.py:303` `list_report_candidates(...)` groups and filters candidates.
  - `dayu/fins/downloaders/hkexnews_downloader.py:356` calls `_infer_fiscal_period_from_text(...)`; `:363` calls `_infer_fiscal_year(...)`; `:1050` defines period inference.
- Rejection registry hidden shape:
  - `dayu/fins/storage/repository_protocols.py:283` exposes `load_download_rejection_registry(...) -> dict[str, dict[str, str]]`.
  - `dayu/fins/storage/_fs_maintenance_core.py:33` decodes arbitrary nested dict and coerces every value to `str`.
  - `dayu/fins/pipelines/sec_download_state.py:89` `_is_rejected(...)` reads `entry.get("download_version")`.
  - `dayu/fins/pipelines/sec_download_state.py:120` `_record_rejection(...)` writes implicit keys.
  - `dayu/fins/pipelines/sec_sc13_filtering.py:187` and related call paths accept `rejection_registry: Optional[dict[str, dict[str, str]]]` and therefore must be updated with the typed registry contract.

## Owner Boundaries

### SEC Form Type

- First producer: user/provider form input in SEC download/upload request, SEC filing records from submissions/browse-edgar, and source meta restore paths.
- Validator: new domain SEC form parser/helper in `dayu.fins.domain`, consumed by SEC pipeline, processor registry, source upsert, and read matching.
- Persistence boundary: source meta `form_type`, rejected artifact meta `form_type`, processed meta `form_type`.
- Projection/consumer boundary: read runtime document filtering, processor selection, download diagnostics, LLM-facing citation/document metadata.

### Fiscal Period

- First producer: upload args, SEC fiscal extraction helper, CN/HK report candidate inference, source meta restore.
- Validator: shared domain fiscal-period parser for `FY/H1/Q1/Q2/Q3/Q4` plus form-aware SEC constraints where needed.
- Persistence boundary: source meta `fiscal_period`, processed meta, rejected artifact meta, source query filters.
- Projection/consumer boundary: list/search/read filters, document recency sorting, fiscal display in read tool output.

### Document / Processor Quality

- First producer: source/processed repository commit and financial processor methods.
- Validator: domain typed quality parsers for document quality and financial data quality.
- Persistence boundary: processed meta `quality`, financial result payload `data_quality`.
- Projection/consumer boundary: read tool result summaries and LLM-facing financial statement / XBRL facts output.

### Financial-Report Filtering / Fiscal Inference

- First producer: raw CNInfo/HKEXNews announcements returned by HTTP client.
- Validator: pipeline/domain report-candidate classifier and fiscal inference helper.
- Persistence boundary: selected `CnReportCandidate`, source meta, download skipped/failed result payloads.
- Projection/consumer boundary: download stream result, read runtime document list, source provenance.

### SEC Download Rejection Registry

- First producer: SEC pipeline policy decision that rejects a candidate, especially 6-K filtering.
- Validator: typed registry entry constructor/parser.
- Persistence boundary: filing maintenance repository registry JSON plus rejected filing artifact meta.
- Projection/consumer boundary: skip/diagnostic logic, insufficient-filing warnings, download summary.

### XBRL Facts Result Validity

- First producer: processor `query_xbrl_facts(...)`.
- Validator: processor result contract helper; read runtime may normalize fact shape and deduplicate only after validating required contract fields.
- Persistence boundary: none durable for query result; runtime result is transient but LLM-facing.
- Projection/consumer boundary: `query_xbrl_facts` read tool result.

## Non-Goals

- 不做旧 schema 兼容读取；发现非法旧值时按当前新 schema fail closed 或由明确 rebuild/migration 后续 work unit 处理。
- 不把 SEC/CN/HK 的所有 report selection 算法重写成单一 mega classifier；只移动 owner 边界，保留现有算法行为和测试期望。
- 不修改 P3-F source provenance、blob staging、wait adapter、company freshness 语义。
- 不更改 Host/Engine 架构、tool governance 或 LLM wait contract。
- 不为旧 import path 增加兼容 re-export/wrapper；实现时应更新调用方 import 到真源。
- 不把 read runtime 变成 source meta 修复器；read runtime 只消费 typed repository/processor truth。

## Design Decisions

1. 新 domain surface 应放在 `dayu/fins/domain/`，例如 `filing_semantics.py` 或同等窄模块。该模块只依赖标准库和 `typing`，不得 import pipeline、storage、processor 或 tool。
2. SEC form 采用 enum-backed parser 或 closed Literal + parser；必须支持当前业务别名，包括 `SC 13D/G` expansion，但 persisted single form 只能是具体表单，不保存 group alias。
3. Fiscal period 采用共享 closed set `FY/H1/Q1/Q2/Q3/Q4`。CN/HK 现有 `CnFiscalPeriod` 应迁移为消费共享 domain 类型，而不是继续定义第二套同义字面量。
4. Document quality 与 financial data quality 分离：`DocumentQuality` 不等同于 `FinancialDataQuality`，不能把 `xbrl/extracted/partial` 混进 processed document quality。
5. Downloader adapter 返回 raw announcements 或 provider-neutral raw announcement DTO；pipeline/domain helper 负责 title/language filtering、report-kind classification、fiscal inference、dedupe/grouping 和 `CnReportCandidate` 构造。Downloader 可保留 provider 原始字段解析、HTTP JSON 结构归一、URL/日期/语言原始字段读取、provider-specific ID 提取；不得保留基于财报业务语义的 title block、语言副本过滤、report-kind 判断、fiscal period/year 推断或候选去重。
6. Rejection registry 使用 typed entry collection，例如 `DownloadRejectionRegistry` / `DownloadRejectionEntry`，repository protocol 返回和保存 typed registry，不再暴露 nested dict shape。
7. XBRL total 校验分两层：processor raw contract validation 必须在 read-runtime dedup/projection 之前执行，校验 raw payload 中 `total` 存在、类型为 int、且等于 raw `facts` list 的长度；read runtime 后续可规范化和 dedupe facts，但 post-dedup count 可能小于 processor raw `total`，不得因此判定 processor result invalid，也不得覆盖 processor-owned `total`。若 LLM-facing 输出需要展示 dedup 后数量，必须使用 `deduped_fact_count` 或等价的明确派生字段/summary term。

## Implementation Slices

### S1 - SEC Form and Shared Domain Typed Values

Objective:
- 建立 P3-G 后续切片共同消费的 domain truth：SEC form parser/expander、fiscal period parser、document quality / financial data quality parser。

Allowed files/modules:
- `dayu/fins/domain/document_models.py`
- 新增 `dayu/fins/domain/filing_semantics.py` 或同等窄模块
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/fins/pipelines/sec_form_utils.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- focused tests under `tests/fins/`

Exact allowed changes:
- Add closed SEC form parser and alias expansion in domain.
- Explicit disposition: delete `dayu/fins/processors/form_type_utils.py` in S1 and update every import/call site to the domain helper. A compatibility wrapper, compatibility re-export, or "same file delegates to domain" path is not allowed because it would preserve the old public import path without adding semantics.
- Update current import/call sites including at least:
  - `dayu/fins/processors/sec_processor.py` import of `normalize_form_type as _normalize_form_type`;
  - `dayu/fins/processors/bs_report_form_common.py` import of `normalize_form_type as _normalize_report_form_type`;
  - `dayu/fins/processors/sec_report_form_common.py` import of `normalize_form_type as _normalize_report_form_type`;
  - `dayu/fins/processors/sec_form_section_common.py` import of `normalize_form_type as _normalize_form_type`;
  - `dayu/fins/tools/read_runtime_helpers.py` import/use of `normalize_form_type`;
  - any direct `normalize_form_type(...)`, `_normalize_form_type(...)`, `_normalize_report_form_type(...)`, `normalize_form(...)`, `_normalize_form(...)`, or `_normalize_form_for_fiscal(...)` call site under `dayu/fins`.
- Remove duplicate mappings in `sec_form_utils.py` / `sec_fiscal_fields.py`; callers should invoke the shared domain parser/expander rather than local mapping tables.
- Validate domain model decode paths for `form_type`, `fiscal_period`, and `quality` where values enter typed objects.
- Keep source meta JSON field names unchanged; this is semantic validation, not storage schema expansion.

Tests:
- SEC form parser covers `10K`, `10-K/A`, `def 14a`, `SC13D/G`, invalid empty input, unsupported single form.
- Existing SEC processor selection and section matching tests continue to pass.
- Source/processed summary decode rejects invalid `quality` and invalid fiscal period at domain boundary.

Validation:
- `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_read_runtime.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `source .venv/bin/activate && rg -n "form_type_utils|def normalize_form\\(|def normalize_form_type\\(|def _normalize_form_for_fiscal\\(" dayu/fins tests/fins`
- `source .venv/bin/activate && rg -n "normalize_form\\(|normalize_form_type\\(|_normalize_form\\(|_normalize_form_type\\(|_normalize_report_form_type\\(|_normalize_form_for_fiscal\\(" dayu/fins tests/fins`
- `source .venv/bin/activate && rg -n "from .*form_type_utils|import .*form_type_utils|from dayu\\.fins\\.processors\\.form_type_utils|from \\.form_type_utils" dayu/fins tests/fins`
- `git diff --check`

Completion signal:
- `dayu/fins/processors/form_type_utils.py` is deleted, no production import references it, and every remaining form normalization call is either the domain owner helper itself, a direct call into that helper, a test assertion, or an unrelated same-name concept.

### S2 - CN/HK Report Candidate Classification and Fiscal Inference Ownership

Objective:
- Move product-level financial-report filtering, language filtering, fiscal period/year inference, and per-period/year grouping out of HTTP downloader adapters into pipeline/domain-owned helpers.

Allowed files/modules:
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_form_utils.py`
- new `dayu/fins/pipelines/cn_report_selection.py` or similar
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- CN/HK downloader and workflow tests under `tests/fins/`

Exact allowed changes:
- Downloader adapters keep HTTP fetch/JSON decode/provider raw field normalization only.
- Introduce raw announcement DTOs if needed, with provider-specific raw source fields but no product-level filtering.
- Pipeline helper converts raw announcements + `CnReportQuery` into `CnReportCandidate` through typed fiscal period/year inference.
- Responsibility classification:
  - remains in downloader: HTTP request construction, response status handling, JSON shape validation, provider field extraction, provider source id/url/date/language raw normalization, stock/company id provider lookup, and provider-specific URL construction;
  - moves to pipeline/domain helper: `_is_title_blocked(...)`-style product title blocking, language duplicate filtering, report-kind / annual / interim / quarter classification, `_infer_fiscal_year(...)`, `_infer_fiscal_period_from_text(...)`, same-period/year amended/latest selection, grouping/dedupe, and final `CnReportCandidate` construction.
- Preserve current user-visible selection behavior unless tests reveal an existing defect directly tied to ownership.

Tests:
- Raw adapter tests: preserve/adjust existing downloader HTTP mock assertions so they cover request parameters, HTTP/JSON errors, provider raw field parsing, source id/url/date/language extraction, and raw DTO ordering, but no longer assert title blocking, fiscal inference, grouping, or `CnReportCandidate` business selection.
- Pipeline helper tests: move existing business assertions for CNInfo title blocking, language/report-kind filtering, fiscal year inference, HK fiscal period inference, amended/latest selection, dedupe/grouping, and `CnReportCandidate` construction into pure helper tests that do not use HTTP mocks.
- Workflow integration tests: keep CN/HK download workflow tests to prove downloader raw output flows through pipeline helper into source/blob commits and skipped/failed summaries.
- Migration rule: every downloader test assertion removed because it was business filtering/inference must have an equivalent pipeline helper assertion in the same slice.

Validation:
- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `source .venv/bin/activate && rg -n "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders dayu/fins/pipelines`
- `git diff --check`

Completion signal:
- Product-level report filtering and fiscal inference live under pipeline/domain helper; downloader matches from the source scan are absent or classified as raw provider parsing only. The implementation report must list migrated downloader assertions and their new pipeline helper test names.

### S3 - Typed SEC Download Rejection Registry

Objective:
- Replace hidden `dict[str, dict[str, str]]` rejection registry protocol with typed registry entries owned by domain/pipeline/storage contract.

Allowed files/modules:
- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_download_diagnostics.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- focused storage / SEC download tests

Exact allowed changes:
- Add frozen typed entry for download rejection registry with required fields: `document_id`, `reason`, `category`, `form_type`, `filing_date`, `download_version`.
- Repository load must parse JSON into typed registry and fail closed on malformed entries rather than coercing arbitrary values to `str`.
- Repository save must accept typed registry and serialize through entry `to_dict()`.
- Pipeline `_is_rejected`, `_record_rejection`, diagnostics, and wrappers consume typed registry, not nested dict.
- SC13 filtering call paths in `sec_sc13_filtering.py` consume the typed registry directly; no typed-registry-to-dict compatibility shim is allowed.

Tests:
- Repository load/save round-trips typed registry.
- Malformed registry entries are rejected/fail closed according to chosen contract.
- `_is_rejected` respects overwrite and `download_version`.
- 6-K filtered rejection writes typed entry and insufficient filing warning consumes typed entry.

Validation:
- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `source .venv/bin/activate && rg -n "dict\\[str, dict\\[str, str\\]\\]|rejection_registry: Optional\\[dict\\[str, dict\\[str, str\\]\\]\\]|load_download_rejection_registry|save_download_rejection_registry" dayu/fins tests/fins`
- `source .venv/bin/activate && rg -n "rejection_registry|DownloadRejection" dayu/fins/pipelines/sec_sc13_filtering.py dayu/fins/pipelines/sec_download_state.py dayu/fins/pipelines/sec_download_diagnostics.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/storage tests/fins`
- `git diff --check`

Completion signal:
- No production protocol signature exposes `dict[str, dict[str, str]]` for rejection registry; `sec_sc13_filtering.py` consumes typed registry without adapter shim; remaining matches are tests or artifact text.

### S4 - XBRL Processor Result Contract and Read Runtime Consumption

Objective:
- Make XBRL facts result validity processor-owned and prevent read runtime from masking contract violations by recomputing required `total`.

Allowed files/modules:
- `dayu/fins/processors/financial_base.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/bs_six_k_processor.py` if it exposes XBRL facts
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/result_types.py`
- focused processor/read runtime tests

Exact allowed changes:
- Add a typed validation helper for `XbrlFactsResult` that checks `query_params`, `facts`, `total`, `data_quality`, and `reason` before LLM-facing projection.
- Validation helper must receive the processor raw payload before `_normalize_single_fact(...)` filtering and `_deduplicate_xbrl_facts(...)`; it must fail closed when raw `total` is missing, raw `total` is not an `int`, raw `facts` is not a list, or raw `total != len(raw_facts)`.
- Read runtime may normalize fact rows and dedupe for display, but must preserve processor-owned `total` after validation.
- If deduped count differs from processor raw total, expose a clearly named derived count such as `deduped_fact_count` only if needed by existing output contract; otherwise keep `total` as processor truth and do not add a derived field.
- Post-dedup shrink is valid and must not fail processor contract validation.
- Remove `dict[str, Any]` expansion in new helper signatures; use existing broad payload only at legacy boundary and narrow immediately.

Tests:
- Processor result missing `total` fails closed in read runtime.
- Processor result with non-int `total` fails closed.
- Processor raw result with `total != len(raw_facts)` fails closed before dedup/projection.
- Valid raw result with `total == len(raw_facts)` preserves processor `total`.
- Valid raw result whose facts shrink after read-runtime dedup remains valid, preserves processor `total`, and uses only a distinct derived count if implementation decides a deduped count is required.
- Deduplication no longer hides invalid processor `total` and no longer overwrites valid processor `total`.

Validation:
- `source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_sec_processor_xbrl.py tests/fins/test_fins_tools_provider.py -q`
- If `test_sec_processor_xbrl.py` does not currently exist, add focused cases to the nearest existing SEC processor/read runtime test file and run that file instead.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `source .venv/bin/activate && rg -n "normalized_payload\\[\\\"total\\\"\\]|\\\"total\\\": len\\(deduped_facts\\)|deduped_fact_count|query_xbrl_facts" dayu/fins tests/fins`
- `git diff --check`

Completion signal:
- Read runtime no longer writes processor-owned `total`; validation tests prove malformed processor results fail closed.

## Aggregate Validation Plan

After all slices:

- `source .venv/bin/activate && pytest tests/fins -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`
- Source scans:
  - `source .venv/bin/activate && rg -n "form_type_utils|def normalize_form\\(|def normalize_form_type\\(|def _normalize_form_for_fiscal\\(" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "normalize_form\\(|normalize_form_type\\(|_normalize_form\\(|_normalize_form_type\\(|_normalize_report_form_type\\(|_normalize_form_for_fiscal\\(" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "from .*form_type_utils|import .*form_type_utils|from dayu\\.fins\\.processors\\.form_type_utils|from \\.form_type_utils" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "fiscal_period: Optional\\[str\\]|fiscal_period: str|quality: str|data_quality: str" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "dict\\[str, dict\\[str, str\\]\\]|rejection_registry: Optional\\[dict\\[str, dict\\[str, str\\]\\]\\]|load_download_rejection_registry|save_download_rejection_registry" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "rejection_registry|DownloadRejection" dayu/fins/pipelines/sec_sc13_filtering.py dayu/fins/pipelines/sec_download_state.py dayu/fins/pipelines/sec_download_diagnostics.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/storage tests/fins`
  - `source .venv/bin/activate && rg -n "normalized_payload\\[\\\"total\\\"\\]|\\\"total\\\": len\\(deduped_facts\\)|deduped_fact_count|query_xbrl_facts" dayu/fins tests/fins`
  - `source .venv/bin/activate && rg -n "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders dayu/fins/pipelines`

All source-scan matches must be classified as:
- active owner truth;
- direct consumer of owner truth;
- test fixture/assertion;
- unrelated same-name concept;
- removed/dead code slated for deletion in the same slice.

## Propagation Audit Criteria

Implementation artifacts must prove these paths:

1. SEC form input / filing record -> domain parser -> source/rejected/processed meta -> processor selection -> read filtering / LLM-facing output.
2. Upload/download fiscal period -> domain parser or pipeline inference helper -> source/processed meta -> list/search/read recency and filters.
3. Processor financial/XBRL quality -> raw `XbrlFactsResult` validator before dedup/projection -> read runtime projection; raw processor `total` equals raw facts length, post-dedup count may differ, and read runtime does not recompute/overwrite processor-owned fields.
4. Raw CN/HK HTTP announcement -> pipeline report selection helper -> `CnReportCandidate` -> source meta and download summary.
5. SEC rejection decision -> typed registry entry -> maintenance repository JSON -> skip/diagnostic consumers, including SC13 filtering and retry/browse-edgar supplemental paths in `sec_sc13_filtering.py`.

## README Decision

Implementation will touch `dayu/fins/` and `tests/`; each slice must read `dayu/fins/README.md` and `tests/README.md` update constraints before deciding. Expected docs impact:

- Update `dayu/fins/README.md` after S1/S2/S3/S4 because public Fins domain/storage/pipeline ownership changes.
- Update `tests/README.md` only if test organization, durable test responsibilities, or validation commands change; adding focused tests alone should not force mechanical README edits.
- No root README expected unless user-visible CLI/tool arguments or workflow behavior changes.

## Risks / Open Questions

- Risk: S1 may touch many imports. Mitigation: keep domain helper narrow, update call sites mechanically, and use source scans.
- Risk: S2 may expose tight coupling between CN/HK downloader tests and selection behavior. Mitigation: first add raw adapter tests, then move existing assertions to pipeline helper tests.
- Risk: S3 changes repository protocol and may require broad type updates. Mitigation: typed entry with direct dict serialization at storage boundary only.
- Risk: S4 may reveal existing tests assuming deduped `total`. Mitigation: decide explicitly whether output needs a derived deduped count; do not overwrite processor `total`.

Blocking questions: none for plan review. The only implementation-time decision expected is the exact module name for the new domain helper; `dayu/fins/domain/filing_semantics.py` is the proposed default.

## Completion Report Format

Each slice implementation report must include:

- files changed;
- source finding coverage;
- owner boundary and propagation audit;
- validation commands and results;
- README decision;
- source-scan classifications;
- residual risks;
- completion state: `ready-for-code-review` or `blocked`.
