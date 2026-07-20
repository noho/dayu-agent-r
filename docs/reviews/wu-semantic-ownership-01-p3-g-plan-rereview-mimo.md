# Plan Re-review — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Reviewed target: `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-controller-adjudication.md`
- Original review: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-mimo.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-rereview-mimo.md`

## Accepted Finding Status

### P3-G-PF-01 — S4 XBRL `total` Contract Boundary — 已关闭 ✅

**Fix 验证**:

- Design decision 7 明确两层校验："processor raw contract validation 必须在 read-runtime dedup/projection 之前执行，校验 raw payload 中 `total` 存在、类型为 int、且等于 raw `facts` list 的长度"（line 119）。
- S4 Exact allowed changes: "Validation helper must receive the processor raw payload before `_normalize_single_fact(...)` filtering and `_deduplicate_xbrl_facts(...)`; it must fail closed when raw `total` is missing, raw `total` is not an `int`, raw `facts` is not a list, or raw `total != len(raw_facts)`"（line 263）。
- Post-dedup shrink 明确合法："Post-dedup shrink is valid and must not fail processor contract validation"（line 266）。
- `total` 语义明确：read runtime 不得覆盖 processor-owned `total`；dedup count 需要时使用 `deduped_fact_count` 派生字段（line 265）。
- 测试覆盖：missing `total`、non-int `total`、raw mismatch、valid raw result、valid post-dedup shrink（lines 270-275）。
- Propagation audit 明确："raw processor `total` equals raw facts length, post-dedup count may differ"（line 317）。

原始 finding 的核心问题（read runtime dedup 后校验 `total != len(facts)` 会误判合法 processor 输出）已通过明确校验层级（raw before dedup）和 post-dedup shrink 合法性完全解决。

### P3-G-PF-02 — S1 Form Normalizer Disposition And Source Scans — 已关闭 ✅

**Fix 验证**:

- S1 Exact allowed changes 明确删除："Explicit disposition: delete `dayu/fins/processors/form_type_utils.py` in S1 and update every import/call site to the domain helper. A compatibility wrapper, compatibility re-export, or 'same file delegates to domain' path is not allowed"（line 142）。
- 列出所有需要更新的 import/call sites（lines 143-149）：`sec_processor.py`、`bs_report_form_common.py`、`sec_report_form_common.py`、`sec_form_section_common.py`、`read_runtime_helpers.py`，以及所有 `normalize_form(...)` / `_normalize_form_type(...)` / `_normalize_report_form_type(...)` / `_normalize_form_for_fiscal(...)` call sites。
- Source scans 增强为三条独立 rg 命令（lines 162-164）：定义/别名、调用/import、import source。
- Completion signal 明确："`dayu/fins/processors/form_type_utils.py` is deleted, no production import references it"（line 168）。

### P3-G-PF-03 — S2 CN/HK Adapter Versus Pipeline Boundary — 已关闭 ✅

**Fix 验证**:

- S2 Exact allowed changes 包含逐项 responsibility classification（lines 189-190）：
  - 留在 downloader：HTTP request construction、response status handling、JSON shape validation、provider field extraction、provider source id/url/date/language raw normalization、stock/company id provider lookup、provider-specific URL construction。
  - 移到 pipeline/domain：`_is_title_blocked(...)`-style product title blocking、language duplicate filtering、report-kind classification、`_infer_fiscal_year(...)`、`_infer_fiscal_period_from_text(...)`、same-period/year amended/latest selection、grouping/dedupe、`CnReportCandidate` construction。
- 测试迁移规则明确（lines 194-197）：raw adapter tests 保留 HTTP mock assertions；pipeline helper tests 接收 business filtering/inference assertions；workflow tests 保持 integration coverage。"Migration rule: every downloader test assertion removed because it was business filtering/inference must have an equivalent pipeline helper assertion in the same slice."
- Completion signal 要求 implementation report 列出迁移的 assertions（line 206）。

### P3-G-PF-04 — S3 Rejection Registry Consumer Scope — 已关闭 ✅

**Fix 验证**:

- S3 Allowed files 包含 `dayu/fins/pipelines/sec_sc13_filtering.py`（line 220）。
- S3 Exact allowed changes: "SC13 filtering call paths in `sec_sc13_filtering.py` consume the typed registry directly; no typed-registry-to-dict compatibility shim is allowed"（line 229）。
- Validation source scan 包含 `sec_sc13_filtering.py`（line 241）。
- Completion signal: "`sec_sc13_filtering.py` consumes typed registry without adapter shim"（line 245）。
- Propagation audit: "including SC13 filtering and retry/browse-edgar supplemental paths in `sec_sc13_filtering.py`"（line 319）。

## New Material Findings

未发现新 material findings。

Plan 更新后的四个 fix 均正确闭合，未引入新的架构风险、边界模糊或过度耦合。

## Residual Risks

与原 review 一致，无新增：

- S1 import 范围大但有 source scans 兜底。
- S2 测试迁移规则明确，implementation agent 有清晰执行路径。
- S3 `sec_sc13_filtering.py` 7 处 `dict[str, dict[str, str]]` 需要更新为 typed registry，已在 allowed files 中。
- S4 校验层级明确（raw before dedup），post-dedup shrink 合法。

## Verdict

**PASS** — 四个 accepted findings 均已正确关闭。Plan 可进入 implementation。
