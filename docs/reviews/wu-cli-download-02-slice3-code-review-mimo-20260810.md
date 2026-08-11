# Code Review — WU-CLI-DOWNLOAD-02 Slice 3 (DL-F13)

## Scope

- Mode: current changes（未提交 workspace changes）
- Branch: `codex/download-oracle`
- Base: `main`（`bad90963`）
- Output file: `docs/reviews/wu-cli-download-02-slice3-code-review-mimo-20260810.md`
- Included scope: Slice 3 allowed production files（13 个）+ allowed test files（10 个）+ 3 份 README
- Excluded scope: Host / Engine / storage protocol / non-Slice-3 files
- Parallel review coverage: 无（scope 在单 reviewer 可完整走读范围内）

## Findings

**未发现 blocking 或 high severity 实质性问题。**

以下为逐项 adversarial 验证结论：

### 1. HKEX Q1–Q4 全 results category query

**验证**: `_PERIOD_TO_CATEGORY_SPEC` 中 Q1/Q2/Q3/Q4 均映射到 `t1code=10000, t2_group_code=3, t2code=-2`。旧 `_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` 已删除，新增 `_HKEXNEWS_T2_ALL_RESULTS = "-2"`。`hkexnews_downloader.py:72` 定义新常量，`:156–168` 四个 quarter 共用同一 spec。category spec 去重逻辑不变，bare HK 四个 optional quarter 只触发一次全 results query。

**结论**: PASS。无 13600 残留，无重复 query。

### 2. Category-first classification matrix

**验证**: `cn_report_selection.py:506–557` 实现 `_classify_hk_period_projection`。逻辑严格为：
1. `normalized_category` 为空 → `None`
2. `is_results` 由 `_HK_CATEGORY_RESULTS_MARKERS`（`業績/业绩/RESULTS`）判定
3. `is_report` 由 `_HK_CATEGORY_REPORT_MARKERS`（`年報/年报/REPORT/中期報告/半年報` 等）判定
4. `is_results == is_report`（both True 或 both False）→ `None`（ambiguous）
5. report family：先检测 H1 tokens，再在移除 H1 短语后的残余中检测 FY tokens；`has_results_period`（`QUARTER/RESULTS/季度/季業績`）或 `has_fy == has_h1` → `None`
6. results family：收集 `_HK_RESULTS_PERIOD_TOKENS` 命中集合 → `_resolve_hk_results_identity` 按 Q4 > Q3 > Q2 > Q1-only 收敛

**关键正例验证**:
- `中期業績` + six-month → Q2, `(H1,Q2)` ✓
- `末期業績` + annual → Q4, `(FY,Q4)` ✓
- `中期報告` + half-year → H1 singleton ✓
- `年報` + full-year → FY singleton ✓

**关键负例验证**:
- 空 category → `None` ✓
- `INTERIM RESULTS / INTERIM REPORT`（both markers）→ `None` ✓
- `RESULTS` only 无 quarter → `None` ✓
- `FINAL RESULTS` + `SIX MONTHS`（Q4 category + H1 title）→ Q4 tokens 命中但 `_resolve_hk_results_identity` 返回 Q4，然而 title 有 `SIX MONTHS`。需确认：`SIX MONTHS` 同时是 Q2 token，所以 `matched = {Q2, Q4}`，`_resolve_hk_results_identity` 返回 `None`。✓ 正确拒绝。
- report + quarter token → `has_results_period` True → `None` ✓

**Q2 three+six 优先**: `_resolve_hk_results_identity` 中 Q2 无条件返回（line 614），`matched == {Q1}` 才返回 Q1。若 title 同时含 three-month 和 six-month，`matched = {Q1, Q2}`，Q2 优先返回。✓

**Q4/Q3 冲突**: `Q4 in matched` 时若 `{Q2, Q3} & matched` 非空则 `None`。✓

**generic RESULTS 歧义**: bare `RESULTS` category 不含 quarter token → `matched` 为空 → `None`。✓

**结论**: PASS。分类矩阵正确实现 plan §5.3 全部正负例规则。

### 3. 同 source ID 去重

**验证**: `cn_report_selection.py:621–668` 实现 `_deduplicate_hk_announcements` 与 `_hk_announcement_core_facts`。核心事实 tuple 为 `(source_url, category_text, title, filing_date, language)`。`stock_code_payload` 不在核心事实中（正确：同一 document 可关联多个 stock code）。

**测试**: `test_hkexnews_selection_fails_closed_on_same_source_id_fact_conflict` 验证同 ID 不同 title/category 抛 `ValueError("核心事实冲突")`。✓

**结论**: PASS。去重完整且冲突 fail closed。

### 4. CnReportPeriodProjection invariants

**验证**: `cn_download_models.py:138–183`。校验链：
1. `identity_period` 必须是 `CN_FISCAL_PERIOD_ORDER` 成员（TypeError）
2. `covered_periods` 必须是 tuple（TypeError）
3. 非空（ValueError）
4. 每个 period 必须是 canonical（TypeError）
5. 无重复（ValueError）
6. canonical order（ValueError）
7. 包含 identity_period（ValueError）

**CNInfo singleton**: `_build_cninfo_candidate` 构造 `CnReportPeriodProjection(identity_period=period, covered_periods=(period,))`。✓

**结论**: PASS。invariants 完整且在唯一构造点正确实施。

### 5. Identity 仅由 identity_period 驱动

**验证**:
- `build_cn_filing_ids` 两个 download call site（`cn_download_workflow.py:836–840`、`cn_download_filing_workflow.py:188–196`）均只传 `candidate.period_projection.identity_period`。✓
- `_resolve_missing_periods`（`cn_download_workflow.py:583`）只收集 `identity_period`。✓
- window matching（`cn_download_workflow.py:525`）只用 `identity_period`。✓
- business limit（`cn_download_workflow.py:546`）只用 `identity_period`。✓
- source meta 的 `form_type`/`fiscal_period`/`report_kind` 均从 `identity_period` 派生。✓

**结论**: PASS。无遍历 covered_periods 生成 ID 的路径。

### 6. Coverage 不满足 FY/H1 baseline

**验证**: `test_cn_download_workflow.py` 中 `test_cn_rebuild_scope_filter_contract` 的参数化用例验证 Q2 result（covered=H1,Q2）不满足 H1 report baseline、Q4 result（covered=FY,Q4）不满足 FY report baseline。missing 只看 `identity_period`，coverage 不参与。✓

**结论**: PASS。

### 7. Source meta required coverage 与 download_version/skip 语义

**验证**:
- `cn_download_source_upsert.py:247–248`：`_build_base_meta` 写入 `covered_fiscal_periods: list(candidate.period_projection.covered_periods)`。✓
- `cn_download_rebuild.py:451–567`：`_required_covered_fiscal_periods` 做严格 required list、成员（via `_optional_period` 只接受 6 个 canonical 值）、非空、去重、canonical order、identity inclusion 校验。无 `.get(default)` 或 fallback。✓
- `cn_download_models.py` 中 `CN_PIPELINE_DOWNLOAD_VERSION` 未在本次修改中改变，不影响 coverage 语义。

**结论**: PASS。fresh schema 无 fallback，缺字段/畸形 fail closed。

### 8. Ordinary/skip/failed/rebuild 严格 coverage

**验证**:
- ordinary result：`cn_download_workflow.py:260–269` 写入 `covered_fiscal_periods`。✓
- failed result：`cn_download_workflow.py:612–620` 写入 `covered_fiscal_periods`。✓
- filing workflow result：`cn_download_filing_workflow.py:803–811` 写入 `covered_fiscal_periods`。✓
- rebuild result：`cn_download_rebuild.py:279` 写入 `covered_fiscal_periods`。✓
- rebuild failed result：`cn_download_rebuild.py:402` 写入 `covered_fiscal_periods`。✓

**结论**: PASS。四类结果均携带 coverage。

### 9. Public mandatory 字段所有构造点

**验证**:
- CN adapter 3 个构造点（`cn_pipeline.py:1495,1508,1520`）均从 `_required_cn_covered_fiscal_periods` 读取必填 array。✓
- SEC 4 个构造点（`sec_pipeline.py:1981,1999,2012,2025`）均显式传 `()`。✓
- Generic runtime 2 个构造点（`ingestion_runtime.py:3843,3864`）均显式传 `()`。✓
- `FinsDownloadDocumentResult` 与 `FinsDownloadPublicDocument` 的 `covered_fiscal_periods` 均无默认值。✓
- `to_json_value()` 显式写入 `list(self.covered_fiscal_periods)`。✓
- CLI `_download_document_line` 用 `json.dumps` 投影。✓

**结论**: PASS。全链原样投影，无重算、无默认。

### 10. CLI 输出有界可读

**验证**: `output.py:462` 新增 `covered_fiscal_periods={json.dumps(list(...), ensure_ascii=False, separators=(',', ':'))}`。输出格式如 `covered_fiscal_periods=["FY","Q4"]` 或 `covered_fiscal_periods=[]`。bounded by `_bounded_json_text` context，不暴露内部路径。✓

**结论**: PASS。

### 11. README 按职责更新

**验证**:
- 根 `README.md`：新增 mode 互斥、CN/HK bare policy、baseline missing、CLI coverage 行说明。未写 plan/review 历史。✓
- `dayu/fins/README.md`：新增全 results discovery、category-first、identity/coverage owner、public contract 说明。✓
- `tests/README.md`：新增 download owner matrix 覆盖说明。✓
- 未修改 `dayu/README.md`、Host/Engine README。✓

**结论**: PASS。按 README 内部约束更新。

### 12. test_output 跨功能测试

**验证**: 新增 2 个测试：
- `test_prompt_and_interactive_render_non_cancelled_terminal_matrix`：覆盖 success/missing_answer/failed/lost 四种终态 × prompt/interactive 两种渲染。✓
- `test_fins_renderer_covers_progress_failure_cancel_and_error_helpers`：覆盖 progress/failed/cancelled/error 四种事件渲染。✓

这两个测试填补了 `output.py` 中 `render_prompt_terminal_result`、`render_interactive_terminal_result`、`render_fins_direct_event`、`render_fins_direct_cancel_requested`、`render_cli_error` 的覆盖空白，对达到 80% 整文件覆盖率是必要的。测试稳定：不依赖网络、时间或外部状态。✓

**结论**: PASS。必要且稳定。

### 13. Host/Engine/storage schema/scope drift

**验证**:
- 未修改 `dayu/host/`、`dayu/engine/`。✓
- 未修改 `dayu/fins/storage/` protocol 或 implementation。✓
- `FilingManifestItem` schema 未变。✓
- `covered_fiscal_periods` 只存在于 source meta，不进入 manifest item。✓
- 分层依赖方向不变：`UI -> Service -> Fins`。✓

**结论**: PASS。无 drift。

## Open Questions

无。

## Residual Risk

1. **Bare "業績" category 无 quarter 指示**: 若 HKEX 返回仅含 `業績` 的 category 且标题也不含任何 quarter/duration token，当前实现正确返回 `None`（丢弃）。此行为符合 plan 但无显式测试覆盖。风险低：production HKEX 的 results category 通常附带 `中期/末期/季度` 前缀。

2. **`_contains_any_token` 子串匹配**: 当前使用 `token.upper() in text` 做子串匹配。对中文 token（如 `半年`）可能在非常规标题中产生伪命中。风险低：plan 明确接受子串匹配作为通用规则，且 `_remove_tokens` 已处理已知的 H1/FY 冲突场景。

3. **未执行真实 provider / CLI evidence**: 按 gate 约束，未运行 production CLI 或真实 HKEX 查询。category query 行为仅由 HTTP fixture 验证。风险需在 post-fix evidence 阶段消除。

## Conclusion

**PASS**。Slice 3 实现完整覆盖 plan §5.3 全部 DL-F13 目标：HKEX 全 results discovery、category-first classification matrix、CnReportPeriodProjection identity/coverage 分离、同 source ID 去重 fail closed、source meta/workflow/public JSON 全链 required coverage 原样投影、missing 只由 identity 满足、SEC/generic 显式空 coverage、CLI 有界可读输出、README 按职责更新。无 blocking finding。residual risks 均为低风险且在后续 evidence gate 可验证。
