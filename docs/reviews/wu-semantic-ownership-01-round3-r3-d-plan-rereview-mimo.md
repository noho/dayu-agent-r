# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Re-Review — AgentMiMo

## Review Metadata

- Reviewer: AgentMiMo
- Review gate: `plan re-review`（PF-01 至 PF-06 关闭验证）
- Reviewed artifact: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`（plan-fix 后版本）
- Plan-fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-controller-adjudication.md`
- Original MiMo review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-mimo.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-ds.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Review timestamp: 20260713-081738

## Re-Review Scope

只验证 PF-01 到 PF-06 是否完整关闭，以及 plan-fix 是否引入新 blocker。不重新扩大为全量计划 review。

## PF Closure Table

| PF ID | 描述 | 状态 | 关闭证据 |
|-------|------|------|----------|
| PF-01 | XBRL empty-success/failure matrix、caller mapping、quality 术语 | **已关闭** | plan §2 state matrix 5 行覆盖合法空集/partial/all-failed/XBRL unavailable/concepts empty；`XbrlConceptQuerySummary` 定义 attempted/success/failed accounting；caller mapping 写明 `sec_processor` 与 `bs_report_form_common` 统一消费 `summary.rows/successful_concepts/failed_concepts`，all-failed 不构造 payload；quality 术语明确：`data_quality=xbrl` 表示查询正常执行，`total=0` 是合法零命中，不与 empty financial statement 混淆（§2 state matrix 第二行 + §3 tool description template）；characterization pre-check 与 stop condition 明确。 |
| PF-02 | deduped_fact_count owner/requiredness，无 extra/NotRequired 暗门 | **已关闭** | plan §2 明确 `deduped_fact_count` 不属于 domain `XbrlFactsResult`，raw payload 夹带须 fail closed；属于 `XbrlQueryResult` public read projection 的 required `int`，等于 public facts 长度，不放 extra、不用 `NotRequired`；raw `total` 始终复制 producer count 不可被覆盖；assertions 覆盖有/无去重、raw extra、source scan；propagation scan `rg -n 'deduped_fact_count' dayu/fins/domain dayu/fins/processors` 期望零匹配。 |
| PF-03 | independent source meta cache revision check 和零次自动 retry | **已关闭** | plan §4 要求 `_get_source_meta_cached_by_kind()` 独立比较 revision，no-kind positive read 先解析 kind 再委托同一 owner；processor/meta race 均固定零次自动 retry 并立即 `source_changed_during_read` typed fail；freshness matrix 新增 "source revision changes, meta cache accessed independently → meta rebuilt from storage"（§4 Required Freshness table 第 3 行）；required assertions 要求 independent meta tests 不调用 processor registry 并验证 list/info/citation 更新。 |
| PF-04 | 10-Q expansion ref uniqueness 基于直接证据，stop condition 足够 | **已关闭** | plan §5 引用直接代码证据：`expand_ten_q_virtual_sections_content()` 只修改已有 section 的 start/end/content/preview 并排序，不 append/insert，不创建 child ref（已由 `ten_q_form_common.py:499-574` 源码确认）；S2 不设计新 ref schema；测试须在 table assignment 前断言 ref 集合/唯一性；stop condition 明确：若实现时发现 expansion 已创建或必须创建 child ref，停止并回 plan/re-review。 |
| PF-05 | HTML/OCR scale owner 与 partial degradation 明确 | **已关闭** | plan §1 "HTML / OCR scale truth" 分别固定 HTML caption helper（`_infer_scale_from_caption`，`html_financial_statement_common.py:1673`）和 OCR heading helper（`_extract_ocr_currency_and_scale`，`six_k_form_common.py:1833`）为 direct-evidence scale owner；无直接 scale 证据时 `partial + scale_unavailable`，同时缺 fiscal semantics 时 `scale_and_period_semantics_unavailable`；units 不再承载 scale；required assertions 覆盖 HTML caption、OCR heading、missing-scale、missing-scale-and-period、OCR income-summary fallback。 |
| PF-06 | tool description 模板和具名 6-K decode test 可实施 | **已关闭** | plan §3 提供 `get_financial_statement` 和 `query_xbrl_facts` 的简洁中文 description 模板，覆盖 periods/scale/units/quality/reason、raw total vs required dedup count、XBRL 合法零命中语义；S2 固定新增 `test_sec_6k_preview_rejects_invalid_utf8`，validation 命令按 pytest node id 执行（`pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q`），不存在时命令直接失败；aggregate validation 同样使用 node id。 |

## Plan-Fix 引入新 Blocker 检查

| 检查项 | 结果 |
|-------|------|
| tool-security 范围膨胀 | 未引入。Hard Non-Goals 保持不变。 |
| R3-E 范围膨胀 | 未引入。 |
| upload/download security schema | 未引入。 |
| 6-K dual-engine routing | 未引入。§Scope Corrections 保持 "6-K 双引擎 fallback 不在本 plan"。 |
| full DocumentMeta migration | 未引入。§Scope Corrections 保持 "不做全量 DocumentMeta migration"。 |
| creation-lock lifetime | 未引入。 |
| 新增 slice 或 slice 结构变化 | 未引入。保持 3 slices。 |
| 新增 compatibility re-export/wrapper/facade | 未引入。 |

## 原始 Findings 关闭追踪

### MiMo 原始 Findings

| ID | 描述 | 状态 | 说明 |
|----|------|------|------|
| Finding 1 | XBRL zero-row quality invariant 与 state matrix 语义张力 | **已关闭** | PF-01 修复。plan 明确 `data_quality=xbrl` 在 query 场景表示"查询正常执行"，`total=0` 是合法零命中；empty-row invariant 只约束 `FinancialStatementResult`。tool description 模板与 state matrix 一致。 |
| Finding 2 | XbrlQueryResult 缺少 deduped_fact_count 显式契约 | **已关闭** | PF-02 修复。required int，属于 read projection，不属于 domain contract。 |
| Finding 3 | S2 cache revision race rebuild retry 边界未指定 | **已关闭** | PF-03 修复。明确零次自动 retry，立即 typed fail。 |
| Finding 4 | tool description 模板缺失 | **已关闭** | PF-06 修复。提供简洁中文模板。 |

### DS 原始 Findings

| ID | 描述 | 状态 | 说明 |
|----|------|------|------|
| F1 | edgartools API 能力边界未证实 | **已关闭** | PF-01 修复。增加 characterization pre-check、malformed fallback、stop condition。 |
| F2 | Meta cache 独立访问路径 revision 校验未显式说明 | **已关闭** | PF-03 修复。显式要求 `_get_source_meta_cached_by_kind()` 独立比较 revision。 |
| F3 | caller 适配未显式展开 | **已关闭** | PF-01 修复。caller mapping 明确写出消费 summary rows/successful/failed 并映射到 quality/reason。 |
| F4 | 10-Q expansion child section ref 冲突 | **已关闭** | PF-04 修复。直接代码证据确认不创建 child ref，stop condition 覆盖边界情况。 |
| F5 | HTML/OCR producer 语义未展开 | **已关闭** | PF-05 修复。HTML/OCR scale owner、degradation 逻辑、tests 均明确。 |
| F6 | 6-K decode test filter 可能 0 selected | **已关闭** | PF-06 修复。改用 node id 执行。 |

## New Findings

**none**

所有 PF-01 至 PF-06 均已完整关闭。plan-fix 未引入新 blocker，未扩大 scope，未改变 slice 结构。修订内容严格限于 controller adjudication 要求的 6 个 plan-fix 点。

## Blocking Questions

无。

## Residual Risks

以下风险已在 plan 中有 owner 和 stop condition 覆盖，不构成 blocker：

| 风险 | Owner | 缓解 |
|------|-------|------|
| edgartools 版本行为漂移 | S1 characterization tests + stop condition | producer 修改前必须 fail closed |
| revision comparison 额外 storage read 成本 | S2 storage/read cache | correctness 优先 |
| HTML/OCR 文本无 scale 直接证据 | S1 HTML/OCR producer contract | `partial + scale_unavailable` |
| full `DocumentMeta` broad type 仍存在 | umbrella controller 后续裁决 | S2 只增加 freshness 所需 typed revision |

## Final Decision

**pass**

PF-01 至 PF-06 全部关闭，每个 PF 有直接 plan 文本和代码事实支持。plan-fix 未引入新 blocker、未扩大 scope、未改变 slice 结构。plan 可安全交给 implementation agent。
