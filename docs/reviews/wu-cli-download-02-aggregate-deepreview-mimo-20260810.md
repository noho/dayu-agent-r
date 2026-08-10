# WU-CLI-DOWNLOAD-02 Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `codex/download-oracle`
- Base: `3811f95c82fbf0daf15740a5d217eed4d8b49df5`
- Target: `a24671793c0d69f2a3e0f2d39e1b611d945b6044` (HEAD)
- Output file: `docs/reviews/wu-cli-download-02-aggregate-deepreview-mimo-20260810.md`
- Review date: 2026-08-10

## Inputs Read

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 项目约束 |
| `docs/gateflow/wu-cli-download-02-goal-confirmation-20260810.md` | 目标确认 |
| `docs/gateflow/wu-cli-download-02-plan-20260810.md` | Accepted plan (§1–§12) |
| `docs/gateflow/wu-cli-download-02-plan-fix-20260810.md` | Plan fix round 1 |
| `docs/gateflow/wu-cli-download-02-plan-fix-2-20260810.md` | Plan fix round 2 |
| `docs/gateflow/wu-cli-download-02-plan-review-adjudication-20260810.md` | Plan review 裁决 |
| `docs/gateflow/wu-cli-download-02-slice1-implementation-20260810.md` | Slice 1 implementation |
| `docs/gateflow/wu-cli-download-02-slice1-code-review-adjudication-20260810.md` | Slice 1 裁决 |
| `docs/gateflow/wu-cli-download-02-slice1-review-fix-20260810.md` | Slice 1 fix |
| `docs/gateflow/wu-cli-download-02-slice1-validation-fix-20260810.md` | Slice 1 validation fix |
| `docs/gateflow/wu-cli-download-02-slice2-implementation-20260810.md` | Slice 2 implementation + fix |
| `docs/gateflow/wu-cli-download-02-slice2-code-review-adjudication-20260810.md` | Slice 2 裁决 |
| `docs/gateflow/wu-cli-download-02-slice3-implementation-20260810.md` | Slice 3 implementation |
| `docs/gateflow/wu-cli-download-02-slice3-code-review-adjudication-20260810.md` | Slice 3 裁决 |
| `docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md` | 前序 Oracle 裁决 |
| `docs/cli_ci.md` | CLI CI 设计 |
| `docs/host/design.md`, `docs/engine/design.md` | Design docs (确认不修改) |
| 13 份 slice review artifacts | 双路 review 结论 |
| `git diff 3811f95c..HEAD` 全部 Python diff | 产品/测试改动 |
| 3 份 README diff | 文档更新 |

## Cross-Slice Adversarial Verification

### 1. F12 typed invariant 是否在所有构造路径早于副作用且不破坏 standalone modes

**验证结论：PASS**

- `_validate_download_mutation_mode(...)` 是唯一 conjunction owner，定义于 `download_contract.py:62–79`。
- `FinsDownloadRequest.__post_init__` 调用该 helper → `build_fins_download_request(...)` 构造 request 时立即触发 → `_prevalidate_download_request` 在 `_resolve_workspace_root`、`FINS_DIRECT_SERVICE_FACTORY`、stream、provider 和 storage 之前调用。
- `FinsDownloadEffectiveFilters.__post_init__` 复用同一 helper，拒绝独立构造的非法双 true。
- CLI parser 无第二套 validator；两个 flag help 文案各自声明互斥。
- 单独 `overwrite=True`、单独 `rebuild=True`、`False/False` 三组合法组合均可构造且行为不变。
- 生产代码 `rg` guard 确认唯一 `and` 判断仅存在于 `_validate_download_mutation_mode`。

### 2. F14 policy effective/discovery/missing 与 F13 identity/coverage 组合在 CN/HK bare、explicit forms、rebuild、missing、summary/meta/manifest/public JSON/CLI 全链同源

**验证结论：PASS**

**CN bare default (`FY,H1,Q1,Q3`)**：
- `resolve_download_period_policy(None, "CN")` → `effective=discovery=missing=(FY,H1,Q1,Q3)`。
- workflow `filters.forms` = `(FY,H1,Q1,Q3)`。
- `_resolve_missing_periods(missing_eligible=(FY,H1,Q1,Q3), selected)` → 只按 identity period 判断。
- 测试断言 summary 不出现 Q2/Q4 missing。

**HK bare default (effective/missing=`FY,H1`, discovery=六期)**：
- `resolve_download_period_policy(None, "HK")` → `effective=missing=(FY,H1)`, `discovery=(FY,H1,Q1,Q2,Q3,Q4)`。
- workflow `filters.forms` = `(FY,H1)` → public summary effective forms 仅 FY/H1。
- provider query 使用六个 discovery periods → optional quarter 可被发现。
- `_resolve_missing_periods(missing_eligible=(FY,H1), selected)` → 只有 FY/H1 baseline missing。
- Q2 result 的 `covered=(H1,Q2)` 不满足 H1 report baseline → H1 仍 missing。
- Q4 result 的 `covered=(FY,Q4)` 不满足 FY annual report baseline → FY 仍 missing。
- 测试断言只有 optional quarter 时 missing 仍为 FY/H1。

**Explicit forms**：
- 显式 `Q2,Q4` → `effective=discovery=missing=(Q2,Q4)`，CN/HK 行为不变。
- canonical order 由 `CN_FISCAL_PERIOD_ORDER` 唯一持有。

**Rebuild**：
- `rebuild_cn_download_artifacts` 使用 `discovery_periods` 扫描本地 source，`effective_periods` 作为 `filters.forms`。
- missing 由 rebuild producer 直接输出空 list，不计算。
- 测试断言 provider/HTTP 零调用、不覆盖 PDF/Docling。

**数据流同源验证**：
```
raw forms + market
  -> resolve_download_period_policy
     -> effective_periods -> filters.forms -> FinsDownloadEffectiveFilters.form_types
     -> discovery_periods -> period windows -> CnReportQuery.discovery_periods -> provider/selection
     -> missing_eligible_periods + selected identity_periods -> missing_periods
```
全链无反推、无 fallback、无默认补偿。

### 3. HK category query/classifier 对官方 Q2/Q4 根因是否一般化

**验证结论：PASS**

- Q1–Q4 共用 `t1code=10000, t2_group_code=3, t2code=-2` 全 results group。
- 旧 `13600` production 语义已删除；`rg` guard 无 `_HKEXNEWS_T2_QUARTERLY_RESULTS` 残留。
- category spec 去重保证四个 quarter 只触发一次全 results query。
- 分类器 `_classify_hk_period_projection` 先只由 provider `category_text` 判定 report/results family，再在 family 内共同解释 category + title 期间事实。
- `_HK_CATEGORY_RESULTS_MARKERS` 包含 `業績`/`业绩`/`RESULTS` → `中期業績`/`末期業績` 正确归入 results family。
- `_HK_CATEGORY_REPORT_MARKERS` 包含 `年報`/`REPORT`/`中期報告` 等 → 年报/中期报告正确归入 report family。
- report 与 results 对共享 half/full-year token 分别解释为 H1/FY report 或 Q2/Q4 result。
- 不使用 0700、腾讯、固定 document id、固定日期或完整标题特例。

### 4. 同 source 一 identity、coverage 不满足 baseline

**验证结论：PASS**

- `build_cn_filing_ids(...)` 只从 `period_projection.identity_period` 调用一次，不遍历 `covered_periods`。
- source meta `fiscal_period` = identity period；manifest 只有一个 entry。
- Q2 result `covered=(H1,Q2)` → 不满足 H1 report baseline。
- Q4 result `covered=(FY,Q4)` → 不满足 FY annual report baseline。
- source meta `covered_fiscal_periods` 保留完整 coverage 事实。

### 5. Fresh schema / skip / rebuild / overwrite 交互

**验证结论：PASS**

- fresh schema：rebuild 对 source meta `covered_fiscal_periods` 做 required list/成员/非空/去重/canonical order/identity inclusion 严格校验；缺字段或畸形 fail closed。
- skip：skipped result 携带 required coverage。
- rebuild：不访问 provider、不下载 PDF、不运行 Docling、不覆盖 blob、不触发 processed/reprocess、missing 为空。
- overwrite：与 rebuild 互斥，由 typed invariant 拒绝。

### 6. SEC / generic mandatory field 迁移

**验证结论：PASS**

- `FinsDownloadDocumentResult` 新增无默认必填 `covered_fiscal_periods: tuple[str, ...]`。
- SEC `sec_pipeline.py` 四个构造点显式传 `()`。
- `ingestion_runtime.py` 两个 non-persisted 构造点显式传 `()`。
- public JSON `"covered_fiscal_periods": []` 正确输出。
- 测试断言 SEC public JSON 包含空 array。

### 7. 取消 / 失败 / 空候选

**验证结论：PASS**

- 取消：不影响 F12 invariant（在 operation 前拦截）；F14/F13 取消路径正常。
- 失败：`_build_candidate_failed_result` 携带 required `covered_fiscal_periods`。
- 空候选：`_resolve_missing_periods` 对空 selected 正确返回全部 missing_eligible_periods。
- rebuild 空结果：`warnings.append("未匹配到可重建的已下载 CN/HK filings")`。

## Production Code Verification

### 静态验证

| 检查项 | 结果 |
|---|---|
| `pyright` | 0 errors, 0 warnings, 0 informations |
| focused owner union (12 test files) | 609 passed |
| old contract guard (`TargetPeriodResolution\|resolve_target_periods\|CnReportQuery.target_periods`) | 无匹配（正确；`target_periods` in `html_financial_statement_common.py` 属于不同业务模型） |
| HKEX `13600` / `_HKEXNEWS_T2_QUARTERLY_RESULTS` guard | 无匹配 |
| ticker/title/date 特例 guard | production 分类逻辑不含特例；`0700` 仅在 ticker normalization/docstring 示例中 |
| identity guard | 两个 candidate download ID call site 均只传 `identity_period` |
| required-field guard | 公共 coverage 无默认；SEC/generic 显式空 tuple |
| `test_arg_parsing.py` revert guard | 相对 accepted-plan base 零 diff |

### 逐文件 Coverage（来自 Slice 3 implementation artifact）

| Production file | Line coverage |
|---|---:|
| `dayu/cli/output.py` | 81% |
| `dayu/fins/direct_events.py` | 87% |
| `dayu/fins/download_contract.py` | 88% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 85% |
| `dayu/fins/ingestion_runtime.py` | 90% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 86% |
| `dayu/fins/pipelines/cn_download_models.py` | 97% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 86% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 86% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 93% |
| `dayu/fins/pipelines/cn_pipeline.py` | 90% |
| `dayu/fins/pipelines/cn_report_selection.py` | 91% |
| `dayu/fins/pipelines/sec_pipeline.py` | 82% |

全部实际修改 production 文件均 ≥ 80%。

## Cross-Slice Semantic Ownership Drift Audit

### Audit matrix

| 语义事实 | 正确 owner | 实现中的实际 owner | 是否 drift |
|---|---|---|---|
| overwrite/rebuild 互斥 | `FinsDownloadRequest.__post_init__` via `_validate_download_mutation_mode` | 同左 | 否 |
| CN/HK effective forms | `CnDownloadPeriodPolicy.effective_periods` | 同左 → `filters.forms` | 否 |
| CN/HK discovery scope | `CnDownloadPeriodPolicy.discovery_periods` | 同左 → `CnReportQuery.discovery_periods` → period windows | 否 |
| CN/HK missing eligibility | `CnDownloadPeriodPolicy.missing_eligible_periods` | 同左 → `_resolve_missing_periods` | 否 |
| document identity period | `CnReportPeriodProjection.identity_period` | 同左 → ID/窗口/missing/form/report kind | 否 |
| document covered periods | `CnReportPeriodProjection.covered_periods` | 同左 → source meta/workflow result/public JSON/CLI | 否 |
| HKEX material family | `_classify_hk_period_projection` (category-first) | 同左 | 否 |
| HKEX category query | `_PERIOD_TO_CATEGORY_SPEC` (全 results group) | 同左 | 否 |
| source meta coverage | `_build_base_meta` from `candidate.period_projection.covered_periods` | 同左 | 否 |
| public JSON coverage | `FinsDownloadPublicDocument.to_json_value()` | 同左 | 否 |
| CLI coverage display | `_download_document_line` from `FinsDownloadPublicDocument` | 同左 | 否 |

**结论：未发现 semantic ownership drift。** 所有业务事实均有唯一清晰 owner，全链从 owner 同源投影，无 fallback/重算/loose parsing/compat shim。

## Test Fixture Audit

- 测试不使用冻结完整标题作为唯一匹配条件；参数化 fixture 覆盖英文/繁中/简中 token。
- `test_download_command_maps_args_to_service` 从非法双 true 组合改为合法单 mode sentinel。
- Service pass-through fixture 从双 true 改为合法 overwrite-only。
- HKEX tests 断言精确 category 参数 `t1code=10000,t2Gcode=3,t2code=-2`。
- owner test 不固化实现内部结构（已删除 AST owner test per adjudication）。

## README Verification

| README | 更新内容 | 与实现事实一致性 |
|---|---|---|
| 根 `README.md` | mode 互斥、CN/HK bare policy、baseline missing、coverage 行 | 一致 |
| `dayu/fins/README.md` | 全 results discovery、category-first、identity/coverage owner、public contract | 一致 |
| `tests/README.md` | download owner matrix、coverage 测试事实 | 一致 |

README 未写 plan/review/WU 历史、future capability 或内部 evidence ID。Host/Engine/`dayu/README.md`/design docs 未修改（分层边界不变）。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

| 风险 | 分类 | Owner |
|---|---|---|
| 真实 HKEX 全 results 数据规模与边缘 category 文本尚未验证 | covered by evidence gate | accepted plan §9 |
| 通用 substring token 在未知 provider 文本上可能保守丢弃歧义材料 | acceptable fail-closed residual | 不在当前 scope 加 issuer 特例 |
| 旧 workspace 无 coverage 的 source meta 无兼容读取 | accepted fresh-schema boundary | 非本 work unit |
| `_HKEXNEWS_T2_ALL_RESULTS` 与 `_HKEXNEWS_T2_GROUP_ALL` 值相同 (`-2`) 但语义不同（t2code vs t2Gcode） | cosmetic naming | 无行为影响 |

## Verification Summary

| 维度 | 状态 |
|---|---|
| F12 typed invariant 时序 | PASS — 所有构造路径在副作用前 |
| F14 三集合 policy 全链同源 | PASS — CN/HK bare/explicit/rebuild/missing |
| F13 category-first 一般化 | PASS — 不含发行人特例 |
| 同 source 一 identity | PASS — ID 只从 identity_period 调用一次 |
| Coverage 不满足 baseline | PASS — Q2→H1, Q4→FY 不满足 |
| Fresh schema / rebuild / overwrite | PASS — fail closed，无 fallback |
| SEC/generic mandatory migration | PASS — 显式空 tuple |
| 取消/失败/空候选 | PASS |
| Semantic ownership drift | PASS — 未发现 |
| Test fixtures | PASS — 不固化实现偶然性 |
| README 语义 | PASS — 与实现事实一致 |
| Pyright | PASS — 0 errors |
| Focused owner union | PASS — 609 passed |
| 逐文件 coverage | PASS — 13 文件均 ≥ 80% |
| Scope drift / 过度设计 | PASS — 无 scope expansion |

**总体结论：未发现实质性问题。DL-F12/F13/F14 实现正确、全链同源、测试充分。**
