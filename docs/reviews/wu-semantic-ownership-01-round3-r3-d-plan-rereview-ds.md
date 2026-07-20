# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Re-Review — AgentDS

## Review Metadata

- Review artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-rereview-ds.md`
- Reviewer: AgentDS (adversarial plan re-review)
- Re-review target: revised plan `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md` (post plan-fix)
- Gate: `plan re-review` (只验证 PF-01 至 PF-06 关闭状态，不扩大为全量计划 review)
- Timestamp: 2026-07-13 08:18:38 CST
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Input artifacts:
  - Revised plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
  - MiMo review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-mimo.md`
  - DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-controller-adjudication.md`
  - Codex fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-fix-codex.md`

## Re-Review Scope

只验证 PF-01 至 PF-06 是否完整关闭，以及 plan-fix 是否引入新 blocker。不重新扩大为全量计划 review。

## PF Closure Table

### PF-01 — XBRL Empty-Success And Failure Matrix

**Controller requirement**: edgartools pre-check, distinguish exception/successful-zero/partial-fail/all-failed, caller mapping, resolve quality terminology tension.

**Direct code evidence (pre-fix)**:
- `sec_xbrl_query.py:434-486`: `_query_facts_rows` 对每个 concept 的 `query_obj.execute()` 做 `try: result_rows = query_obj.execute()` / `except Exception: continue`，exception 与空 list 同样落成空 rows。
- `sec_processor.py:712`: caller 把 `_query_facts_rows()` 当 list，做 `total=len(rows)`。
- `bs_report_form_common.py:317`: 同上。

**Plan-fix evidence**:
- Plan §2 Edgartools API pre-check (line 209-214)：明确 edgartools 5.30.0 `execute()` 返回 `list[dict]`，正常零命中返回 `[]`，exception 只来自 `get_facts`/filter/transform。characterization tests 锁定此边界；非 list 或 list 中含非 mapping row 视为 contract violation → failed。
- Plan §2 `XbrlConceptQuerySummary` (line 199-207)：`attempted_concepts`/`successful_concepts`/`failed_concepts` 三元组 accounting；每 concept 只执行一次、不重试；failed identity 使用 bounded concept local name。
- Plan §2 State matrix (line 216-228)：valid empty (`xbrl`, `reason=None`)、partial (`query_partially_failed`)、XBRL unavailable (`xbrl_not_available`)、all-failed → `XbrlQueryExecutionError`，四类由类型和字段唯一分辨。
- Plan §2 Caller mapping (line 227-228)：`sec_processor.py` 与 `bs_report_form_common.py` 统一解构 summary，按同一映射消费 `rows/successful_concepts/failed_concepts`；all-failed caller 不构造 payload。
- Plan §1 invariants (line 162-163)：明确定义 FinancialStatementResult `rows=[]` 不可声明完整 `xbrl/extracted`，但该规则不适用于 XBRL concept query 的零命中。
- Plan Required Assertions (line 371)：edgartools characterization/matrix 覆盖 sentinel exception、non-list/malformed row、all-failed raises、partial、successful zero rows → `xbrl/None`、XBRL absent、本地 filter 空集。
- Plan S1 Stop Condition (line 420-421)：characterization 不通过立即停止。

**Verdict**: **FIXED** — 所有 controller 要求的子项均已落地：edgartools API pre-check 有具体版本证据和 characterization 契约；exception/malformed/successful-zero/partial/all-failed 在 state matrix 中逐项可分辨；caller mapping 明确；terminology tension 通过 invariant 边界注释化解（financial empty ≠ XBRL query empty）。

### PF-02 — XBRL Dedup Count Contract

**Controller requirement**: single owner for `deduped_fact_count`, requiredness explicit, raw total protected.

**Direct code evidence (pre-fix)**:
- `result_types.py:307-316`: `XbrlQueryResult` 使用 `total=False`，`deduped_fact_count: int` 在 `NotRequired` 区域。
- `read_runtime_helpers.py:1453-1456`: 只在 `len(deduped_facts) != validated.total` 时才写入，否则 `pop("deduped_fact_count", None)` —— 该字段有条件存在，requiredness 未保证。

**Plan-fix evidence**:
- Plan §2 (line 196-197)：`deduped_fact_count` 不属于 domain `XbrlFactsResult`；domain validator 遇到 raw payload 中夹带该字段必须拒绝；domain 自身不得生成或覆盖 read-side dedup count。
- Plan §2 (line 196-197)：`deduped_fact_count: int` 属于 `XbrlQueryResult` public read projection 的 required 字段，即使未删除任何 row 也必须显式等于 `len(public facts)`；不放 extra payload、不设为 `NotRequired`；满足 `0 <= deduped_fact_count <= total`。
- Plan §2 (line 229-230)：`_normalize_xbrl_query_payload()` 始终写 required `deduped_fact_count=len(deduped public facts)`。raw `total` 原样复制 producer count，dedup count 不能覆盖它。
- Plan Required Assertions (line 373)：raw total 与 raw facts count 不一致 fail closed；raw producer payload 夹带 `deduped_fact_count` 也 fail closed；public `deduped_fact_count` 在有/无去重两种情况下都 required 并等于 public facts 长度。
- Plan Propagation Scans (line 399, 407)：domain/processor dedup count 扫描零匹配；该字段只允许出现在 read normalizer/public projection、LLM description、tests 和 README。

**Verdict**: **FIXED** — 单一 owner（read projection）明确；requiredness 从 conditional 变为 always required；raw total 保护完整（不会被 read-side 覆盖，domain 不生成 dedup count）。

### PF-03 — Source Meta Cache Freshness

**Controller requirement**: independent meta read revision comparison, rebuild race concrete (zero retry or fixed count), freshness matrix includes independent meta.

**Direct code evidence (pre-fix)**:
- `read_runtime.py:2207-2234`: `_get_source_meta_cached_by_kind` cache hit (line 2228-2230) 直接返回 `cached.meta`，不读取 storage revision。
- `read_runtime.py:2236-2260`: `_get_document_meta_cached` cache hit (line 2250-2252) 同样直接返回，无 revision 比较。
- `read_runtime.py:2468-2514`: `_get_or_create_processor` 有 creation lock 但无 revision 比较。
- `read_runtime.py:2110`: `list_documents` 调用 `_get_source_meta_cached_by_kind` 获取 meta，不触发 processor build。

**Plan-fix evidence**:
- Plan §4 (line 265-266)：`_get_source_meta_cached_by_kind()` 或实现时固定的等价 owner 必须独立完成 revision comparison，不能假设 `_get_or_create_processor()` 已运行。`list_documents`、document identity/info 和 citation 路径即使完全不构建 processor，也统一经过该 owner。
- Plan §4 (line 266-267)：`_get_document_meta_cached()` 必须先 resolve source kind 后委托同一 revision-aware owner；不得保留一条不比较 revision 的 no-kind positive cache 快路。
- Plan §4 (line 267)：processor build race (`R1→build→R2`)：`R1 != R2` 时不缓存、不返回。meta read race (`M1→read/parse→M2`)：`M1 != M2` 时不缓存、不返回。两者均**立即**抛 `source_changed_during_read` typed failure，固定零次自动重试。
- Plan §4 Freshness matrix (line 474-483)：新增 "source revision changes, meta cache accessed independently" 行：不调用 processor build 也必须比较 revision；old meta 与同文档 old processor 一并 evict。
- Plan Required Assertions (line 491-492)：independent meta tests 不调用 processor registry；修改 storage source revision 后下一次独立 meta read 必须重读 new meta 并 evict old processor；processor/meta race 各断言一次尝试、无第二次、cache 无 race 产物。

**Verdict**: **FIXED** — 所有三条 controller requirement 均已落地。independent meta read 路径显式要求 revision comparison；rebuild race 固定为零次自动重试（非"不做无界 loop"的模糊约束）；freshness matrix 完整覆盖 meta 独立访问、concurrent rebuild、source change during build。

### PF-04 — 10-Q Expansion Ref Uniqueness

**Controller requirement**: clarify whether expansion creates new refs, if yes state uniqueness rule.

**Direct code evidence (pre-fix)**:
- `ten_q_form_common.py:499-582`: `expand_ten_q_virtual_sections_content()` 只修改已有 section 的 `start/end/content/preview`（line 575-577），按 `(start, level, ref)` 排序（line 582），不调用 `append` 或 `insert`，不创建新 section 对象。
- `ten_q_processor.py:89-92`: expansion 后调用 `expand_ten_q_virtual_sections_content(full_text=full_text, virtual_sections=self._virtual_sections)`，不重建 `_virtual_section_by_ref`。

**Plan-fix evidence**:
- Plan §5 (line 280-281)：直接代码证据：expansion 只原地修改既有 section 的 `start/end/content/preview` 并按 `(start, level, ref)` 重排，不 append/insert section，也不创建 child ref。
- Plan §5 (line 280-281)：S2 不设计新 ref schema；调用前后的 section object/ref multiset 必须相同，且输入/输出 refs 均唯一。
- Plan §5 (line 281-282)：若实现时发现 expansion 已能创建 child section/ref，必须停止并回 plan/re-review 明确由 expansion owner 生成的唯一规则；禁止在 refresh helper 用后缀补救冲突。
- Plan Required Assertions (line 487)：10-Q expansion 改变 start/end/order 后，在调用 table assignment 前先断言调用前后 section object/ref multiset 相同且 ref 唯一；refresh 后 `_virtual_section_by_ref` object identity 指向最终 sections，table 双向 map 一致。
- Plan S2 Stop Condition (line 543)：expansion 创建 child section/ref 立即停止。

**Verdict**: **FIXED** — 基于当前代码直接证据明确了 expansion 不创建 child ref；ref multiset 唯一性在 refresh 前后均可验证；stop condition 覆盖了 expansion 行为变化的场景。

### PF-05 — HTML/OCR Financial Producer Semantics

**Controller requirement**: HTML/OCR scale semantics separate from XBRL decimals; extracting helper is owner; no evidence → partial + reason.

**Direct code evidence (pre-fix)**:
- `html_financial_statement_common.py:1673-1691`: `_infer_scale_from_caption()` 从 caption 读取 "in thousands"/"in millions"，是 HTML table 的 scale evidence owner。
- `six_k_form_common.py:1833-1859`: `_extract_ocr_currency_and_scale()` 从 OCR header 正则匹配 million/billion/thousands，"000" 也映射为 thousands。
- `html_financial_statement_common.py:1646-1670`: `_build_units_label()` 当 scale 非空时返回 `f"{primary_currency_raw} in {scale}"`，将 scale 拼入 units。
- `six_k_form_common.py:1862-1886`: `_build_ocr_units_label()` 同样返回 `f"{currency_raw} in {scale}"`。
- `bs_six_k_processor.py:350,933`: 对 XBRL rows 硬编码 `"scale": None`，不调用 scale inference。

**Plan-fix evidence**:
- Plan §1 HTML/OCR scale truth (line 176-179)：HTML table 路径由 `_infer_scale_from_caption()` 独占 caption/header 的 scale 提取；OCR 路径由 `_extract_ocr_currency_and_scale()` 独占 OCR heading 的 scale 提取。两者只消费直接文本证据，不借 currency/units、金额绝对值或下游日期猜 scale。
- Plan §1 (line 178-179)：存在 rows 但无直接 scale 证据时不得声明完整 `extracted` → `data_quality=partial` + `scale_unavailable`；若 fiscal semantics 也缺失则使用 `scale_and_period_semantics_unavailable`。
- Plan §1 (line 179)：删除 `_build_units_label` / `_build_ocr_units_label` 把 scale 拼入 units 的行为。scale helper 未命中时保持 `scale=None`，不从旧 units 文本反解析。
- Plan §1 (line 167-168)：`_build_shared_statement_result_from_tables()`、`extract_statement_result_from_ocr_pages()` 与 OCR income-summary fallback 必须把 scale 和 fiscal-period evidence 一并交给同一 financial quality/reason owner。
- Plan Required Assertions (line 375)：HTML caption 含 `in millions` → scale=millions 且 units 不含 scale；无 scale 证据但有 rows → partial+`scale_unavailable`；同时无 fiscal semantics → partial+`scale_and_period_semantics_unavailable`；OCR income-summary fallback 消费同一 scale owner。

**Verdict**: **FIXED** — HTML caption 与 OCR heading 各有一个明确的 direct-evidence scale owner；degradation contract（partial + 具体 reason）对无直接证据场景完整；units 不再承载 scale；三个 producer 路径（table/OCR/OCR-summary）均统一消费 quality/reason owner。

### PF-06 — LLM-Facing Tool Description And Tests

**Controller requirement**: concrete description template/examples; replace 0-selectable test filter with named test.

**Direct code evidence (pre-fix)**:
- `fins_tools.py:853`: `description="读取标准财务报表。"` — 仅 7 个中文字，无任何输出字段说明。
- `fins_tools.py:923`: `description="查询结构化 XBRL 数值 facts。"` — 同样仅标题。
- `tests/fins/test_sec_pipeline_download.py`: grep 结果无任何 test function 名同时匹配 `6k` 和 `decode`。原 `-k '6k and decode'` 命令会 0 selected / 0 passed（pytest 对此场景默认不报错）。

**Plan-fix evidence**:
- Plan §3 (line 245)：`get_financial_statement` description 模板：`读取标准财务报表。返回 periods（period_end、fiscal_year、fiscal_period）、rows、currency、units、scale、data_quality 和 reason；scale 取 units/thousands/millions/billions/null，表示数值倍率，units 表示货币或计量单位。data_quality 取 xbrl/extracted/partial；partial 时 reason 说明缺失或降级原因。`
- Plan §3 (line 246)：`query_xbrl_facts` description 模板：`查询结构化 XBRL 数值 facts。返回 query_params、facts、total、deduped_fact_count、data_quality 和 reason；total 是去重前的原始 fact 数，deduped_fact_count 是返回 facts 的去重后数量。data_quality=xbrl 表示 XBRL 查询正常执行，total=0 表示没有匹配 fact；partial 时 reason 说明 XBRL 不可用或部分概念查询失败。`
- Plan §3 (line 247)：明确只改 financial/read tool descriptions；不改 upload/download schema 或 security text。
- Plan S2 Validation (line 503)：6-K decode test 使用显式 node id：`pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q` —— 不存在该 test 时命令直接失败。
- Plan S2 Propagation Scan (line 526)：named 6-K preview decode test 必须被 pytest 按 node id 收集并执行；不存在该 test 时命令直接失败，禁止使用可能 0 selected 的 `-k` 表达式。
- Plan Required Assertions (line 377)：两个 tool description 分别与模板字段/语义一致；XBRL description 明确 `xbrl + total=0` 是正常零命中；均无内部治理/security 术语。

**Verdict**: **FIXED** — 两个 description 模板均可直接实现，自足说明字段名、类型、allowed values、scale-vs-units 区分和 partial reason 语义。6-K decode test 使用显式 pytest node id，避免了 0-selected 假阳性。

## New Findings

**无。**

逐项检查 plan-fix 是否引入新 blocker：

1. **Scope creep check**: 全 plan 搜索 `tool-security\|R3-E\|upload.*security\|download.*security\|SSRF\|allowlist\|TLS.*redirect\|byte.*budget` 无新增引用。Hard Non-Goals（line 108-118）保持完整。三个 slice 的 stop conditions 均保留 tool-security/R3-E 立即停止条款。**未引入。**

2. **6-K dual-engine routing**: Plan Scope Corrections §1（line 101）明确 "R3-D 仍覆盖 BsSixKFormProcessor 的 financial scale/period/result correctness；不新增 SixK edgartools fallback，不改 registry priority"。plan-fix 未修改此声明。**未引入。**

3. **Full DocumentMeta migration**: Plan Scope Corrections §2（line 102）明确 "S2 只增加 freshness 所需的 storage-owned typed revision；S1 关闭 LLM/durable boundary 上与 financial result 直接相关的 weak type。残余由 umbrella controller 决定后续 owner"。plan-fix 未扩大此范围。**未引入。**

4. **PF-03 zero-retry 是否过于严格**: Plan-fix 将 rebuild race 固定为"零次自动 retry，立即 typed fail closed"。这是正确的 conservative default：correction-first 策略优先正确性，不猜测合理重试次数；若业务需要 retry，caller 可发起新的显式 read。该设计不引入 correctness risk。**非 blocker。**

5. **PF-04 expansion ref multiset 断言是否可能过度约束**: Plan-fix 的 stop condition（若 expansion 已创建 child ref 则停止）是基于当前代码事实的保守策略。若未来 expansion 行为变化，stop condition 会 fail closed 并回 plan/re-review，不会静默产生不一致。**非 blocker。**

6. **PF-06 description 模板字段覆盖**: 模板包含 periods/scale/units/quality/reason（financial statement）和 query_params/facts/total/deduped_fact_count/data_quality/reason（XBRL），与 LLM-facing 文本约束要求一致。不暴露 Host/Engine 内部治理术语。**非 blocker。**

## Blocking Questions

无。

所有 PF-01 至 PF-06 均已通过直接代码证据验证关闭。plan-fix 未引入新 scope creep、未扩大 R3-D 范围、未引入 tool-security/R3-E 工作。修订后 plan 的 3 个 slice 结构保持完整，allowed files 边界清晰，stop conditions 和 required assertions 足够 code-generation-ready。

## Final Decision

**pass**

修订后 plan 可以安全交给 implementation agent 执行 S1。PF-01 至 PF-06 全部关闭，无新 finding。
