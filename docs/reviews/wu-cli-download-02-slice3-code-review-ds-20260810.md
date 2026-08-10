# Code Review — WU-CLI-DOWNLOAD-02 Slice 3（DL-F13）

## Scope

- **Mode**: current changes（uncommitted workspace diff）
- **Branch**: `codex/download-oracle`
- **Base**: `main`（HEAD `3811f95c`，Slice 1+2 已 committed）
- **Output file**: `docs/reviews/wu-cli-download-02-slice3-code-review-ds-20260810.md`
- **Review target**: 当前未提交 Slice 3 diff，覆盖 26 个文件、+1194/-132 行
- **Included scope**:
  - 所有 Slice 3 allowed production files（13 个 `.py` 文件，见 plan §6 Slice 3）
  - 所有 Slice 3 allowed test files（10 个测试文件）
  - 3 份 README 更新
  - 完整 adversarial checklist（见 plan §5.3/§7/§8 及 goal confirmation）
- **Excluded scope**:
  - 已 committed 的 Slice 1（DL-F12）和 Slice 2（DL-F14）实现
  - 未进入 diff 的 Host/Engine/storage schema/protocol 文件
  - 真实 provider CLI 运行、post-fix evidence（按 gate 约束不得执行）
  - 不在 Slice 3 allowlist 的 production/test 文件
- **Evidence basis**: 本 review 只基于静态代码阅读、diff 分析与 plan/implementation artifact 对账；不使用真实 provider 数据、CLI 运行或外部 evidence 替代静态检查结论

## 审查方法

沿 plan §5.3（DL-F13）逐 invariant 走读，覆盖：

1. HKEX provider category discovery（`t1code=10000,t2Gcode=3,t2code=-2` 只发一次，无 `13600`）
2. category-first 分类矩阵（family 只由 category 判定，family 内 category+title 共同决定期间事实）
3. `CnReportPeriodProjection` 不变量（非空、canonical order、无重复、identity in coverage）
4. CNInfo singleton / HK multi-period coverage
5. 同 source ID 去重与核心事实冲突 fail closed
6. identity 只用于 ID/window/missing/form/report_kind；coverage 不满足 baseline missing
7. source meta `covered_fiscal_periods` required field、rebuild fresh-schema fail closed
8. ordinary/skip/failed/rebuild 四种 workflow result 全部携带 coverage
9. `FinsDownloadDocumentResult` / `FinsDownloadPublicDocument` 必填字段无默认值，SEC/generic 构造点显式传 `()`
10. CN adapter → runtime → public JSON → wait adapter → CLI row 全链原样投影
11. CLI 输出有界可读
12. README 按职责更新
13. 测试与 static guard 完整性

## Findings

未发现 blocking 或实质性缺陷。以下按 adversarial checklist 逐项说明验证结论。

### 1. HKEX provider category discovery（PASS）

- **入口**: `dayu/fins/downloaders/hkexnews_downloader.py:_PERIOD_TO_CATEGORY_SPEC`（行 145–176）
- **证据**: Q1/Q2/Q3/Q4 四个 key 均映射到同一 `_HkCategorySpec(t1code="10000", t2_group_code="3", t2code="-2")`；旧 `_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` 已删除（行 174 原常量移除）；常量 `_HKEXNEWS_T2_ALL_RESULTS = "-2"` 新增（行 175）
- **去重验证**: 现有 category spec 去重逻辑在 `list_report_candidates` 内按 `(t1code, t2_group_code, t2code)` 去重（未在本次 diff 中修改），四个 quarter 共享同一 spec，因此只触发一次全 results group query
- **测试证据**: `tests/fins/test_hkexnews_downloader.py` 行 1187 `assert category_params == [("40000", "-2", "40100"), ("40000", "-2", "40200"), ("10000", "3", "-2")]`，行 2385 `assert seen_t2codes == ["-2"]`
- **rg guard**: 生产代码中 `13600` 已无引用（implementation artifact §5.3 确认）

### 2. Category-first 分类矩阵（PASS）

- **入口**: `dayu/fins/pipelines/cn_report_selection.py:_classify_hk_period_projection`（行 506–557）
- **Family 判定**: 仅从 `normalized_category`（行 524–530）判定 `is_results`/`is_report`；`is_results == is_report`（双真或双假）返回 `None`
- **Report family**: 先用 `_HK_REPORT_H1_TOKENS` 匹配 H1（行 533），移除 H1 token 后再用 `_HK_REPORT_FY_TOKENS` 匹配 FY（行 534–535），避免 "半年" 子串干扰 "全年" 判定；禁止 result token（`_HK_REPORT_FORBIDDEN_RESULT_TOKENS`，行 536–539）；`has_fy == has_h1` 返回 `None`
- **Results family**: 在 `category_text + title` 合并大写文本中匹配 `_HK_RESULTS_PERIOD_TOKENS`（行 545–549），再由 `_resolve_hk_results_identity` 收敛（行 597–618）
- **Token 覆盖**: 英文（"INTERIM RESULTS", "FINAL RESULTS", "ANNUAL RESULTS", "SIX MONTHS" 等）、繁中（"中期業績", "末期業績", "六個月" 等）、简中（"中期业绩", "末期业绩", "六个月" 等）均有覆盖
- **Q2 three+six 优先**: `_resolve_hk_results_identity` 中 Q2 命中直接返回 Q2（行 614–615），Q1 仅在 `matched == {"Q1"}` 时返回（行 616–617），因此同时命中 three-month 和 six-month token 时 Q2 优先——与 plan "标题即使同时含 three-month 也不得降为 Q1" 一致
- **Q4/Q3 冲突**: Q4+Q2→None（行 611）、Q4+Q3→None（行 611）、Q3+Q2→None（行 613）
- **Generic RESULTS 歧义**: `matched` 为空时 `_resolve_hk_results_identity` 返回 `None`（行 618）——不靠枚举顺序猜测
- **无标题/日期/ticker/URL 特例**: 分类逻辑只使用 token matching（`_contains_any_token`），无完整标题精确匹配、无 issuer 分支、无固定日期/URL 硬编码。`hkexnews_downloader.py` 中保留的 `0700/00700/700.HK` 仅出现在 docstring 输入格式示例中（implementation artifact §5.3 确认已恢复既有示例）
- **测试证据**:
  - `test_hkexnews_selection_uses_category_first_then_category_and_title_period_facts` — 6 组参数化正例覆盖英文/繁中 category+通用 title（行 2029–2075）
  - `test_hkexnews_selection_rejects_ambiguous_family_or_period_facts` — 5 组参数化反例：空 category、双 marker、report+quarter title、generic RESULTS、Final Results+Six Months 冲突（行 2078–2111）
  - `test_hkexnews_selection_projects_four_generic_materials_to_distinct_identities` — 同批 Q2 result/H1 report/Q4 result/FY report 四个独立 identity/coverage/ID（行 2147–2199）

### 3. CnReportPeriodProjection invariants（PASS）

- **入口**: `dayu/fins/pipelines/cn_download_models.py:CnReportPeriodProjection.__post_init__`（行 155–183）
- **校验链**: identity 类型+membership → covered_periods 类型 → 非空 → 成员合法性 → 无重复 → canonical order（复用 `CN_FISCAL_PERIOD_ORDER`）→ identity in coverage
- **CNInfo singleton**: `cn_report_selection.py:_build_cninfo_candidate` 行 444 `CnReportPeriodProjection(identity_period=period, covered_periods=(period,))`
- **HK report singleton**: `_classify_hk_period_projection` report 分支行 543 `CnReportPeriodProjection(identity_period=identity, covered_periods=(identity,))`
- **HK result Q2**: 行 554 `(identity_period="Q2", covered_periods=("H1", "Q2"))`
- **HK result Q4**: 行 556 `(identity_period="Q4", covered_periods=("FY", "Q4"))`
- **HK result Q1/Q3**: 行 557 singleton
- **测试证据**: `test_cn_report_period_projection_rejects_invalid_coverage` — 4 组非法 coverage（空、重复、乱序、缺 identity）全部 `pytest.raises(ValueError)`（行 2114–2144）

### 4. 同 source ID 去重与冲突 fail closed（PASS）

- **入口**: `cn_report_selection.py:_deduplicate_hk_announcements`（行 621–644）
- **核心事实**: `_hk_announcement_core_facts` 返回 `(source_url, category_text, title, filing_date, language)`（行 647–668）
- **冲突处理**: 同一 `document_id` 的核心事实不一致时 `raise ValueError`（行 643）
- **`stock_code_payload`**: 不在核心事实 tuple 中，与 plan §5.3 明确列出的"source URL、category、title、filing date 或语言"一致。plan 未将其纳入 core facts——若后续发现 provider 确实对同一 document_id 返回不同 stock_code_payload，应先在 plan 层确认是否需要扩展 core facts，而非在下游 silent drop
- **测试证据**: `test_hkexnews_selection_fails_closed_on_same_source_id_fact_conflict` — 同 document_id 不同 title/category 触发 `ValueError`（行 2202–2223）

### 5. Identity 只用于 ID/window/missing/form/report_kind；coverage 不满足 baseline missing（PASS）

- **ID call site**: `cn_download_workflow.py:_candidate_document_id` 行 839 `form_type=candidate.period_projection.identity_period`；`cn_download_filing_workflow.py` 行 157–159 同
- **Window matching**: `cn_download_workflow.py:_select_candidates_for_a4` 行 712 `windows.get(candidate.period_projection.identity_period)`
- **Business limit**: `_apply_default_business_limits` 行 722 `candidate.period_projection.identity_period == "FY"`
- **Missing**: `_resolve_missing_periods` 行 586 `found = {item.period_projection.identity_period for item in selected}` — 仅 identity 参与 missing 计算
- **Form/report_kind**: source meta 中 `form_type`/`fiscal_period`/`report_kind` 三者均等于 `identity_period`（`cn_download_source_upsert.py` 行 250–256）
- **Coverage 不满足 baseline**: Q2 result `covered=(H1,Q2)` 不能消除 H1 missing（因 missing 只看 identity）；Q4 result `covered=(FY,Q4)` 同理。测试证据：`test_cn_download_workflow.py` 行 1134–1149，Q2+Q4 result 存在时 missing 仍为 `["FY", "H1"]`

### 6. Source meta / workflow result / rebuild coverage 全量覆盖（PASS）

- **Source meta 写入**: `cn_download_source_upsert.py:_build_base_meta` 行 253 `"covered_fiscal_periods": list(candidate.period_projection.covered_periods)` — 每次 commit 均写入
- **Ordinary workflow**: `cn_download_workflow.py` 行 270 `"covered_fiscal_periods": list(candidate.period_projection.covered_periods)`
- **Filing completed**: `cn_download_filing_workflow.py:_build_filing_result` 行 811 `"covered_fiscal_periods": list(candidate.period_projection.covered_periods)`
- **Failed workflow**: `cn_download_workflow.py:_build_candidate_failed_result` 行 750 同上
- **Rebuild success**: `cn_download_rebuild.py:_rebuild_single_cn_download_document` 行 282 `"covered_fiscal_periods": list(covered_fiscal_periods)`
- **Rebuild failed**: `_failed_rebuild_result` 行 405 同上
- **Rebuild fresh-schema fail closed**: `_resolve_rebuild_period_projection` 调用 `_required_covered_fiscal_periods`（行 156），后者对缺字段、非 list、空、重复、乱序、缺 identity 均 `raise ValueError`（行 451–488）。无 `.get(default)`、空 tuple 默认或旧 schema fallback
- **测试证据**: `test_cn_rebuild_fails_closed_on_invalid_fresh_schema_coverage` — 7 组非法 coverage（None/非 list/空/重复/乱序/缺 identity/非法值）全部触发 `ValueError`（行 1819–1863）

### 7. Public mandatory 字段所有构造点（PASS）

- **`FinsDownloadDocumentResult.covered_fiscal_periods`**: 无默认值（`tuple[str, ...]` 类型注解无 `= ()`）
- **CN pipeline 3 构造点**: `cn_pipeline.py:_project_cn_document_row` 行 1498/1511/1523 — 均从 `_required_cn_covered_fiscal_periods` 严格解析
- **SEC pipeline 4 构造点**: `sec_pipeline.py` 行 1986/2002/2015/2028 — 均显式传 `covered_fiscal_periods=()`
- **Generic runtime 2 构造点**: `ingestion_runtime.py` 行 3846/3867 — 均显式传 `covered_fiscal_periods=()`
- **`FinsDownloadPublicDocument.covered_fiscal_periods`**: 无默认值，`__post_init__` 校验 tuple 类型、FISCAL_PERIODS membership、无重复（`direct_events.py` 行 305–313）
- **Runtime public projection**: `ingestion_runtime.py:_public_download_summary` 行 5099 `covered_fiscal_periods=row.covered_fiscal_periods` — 原样复制
- **测试证据**: `test_sec_download_adapter_summary_classifies_skipped_and_rejected_exclusively` 行 3769 `assert all(row.covered_fiscal_periods == () for row in summary.document_rows)`

### 8. 全链 JSON 投影一致性（PASS）

- **链路**: CN/HK workflow row → `cn_pipeline._required_cn_covered_fiscal_periods` strict parse → `FinsDownloadDocumentResult` → `_public_download_summary` copy → `FinsDownloadPublicDocument` → `to_json_value()` 显式 `list(self.covered_fiscal_periods)` → `FinsDownloadPublicSummary.to_json_value()` 的 `documents[]` → wait adapter `to_json_value()` → CLI row
- **无重算**: 全链无 `form_or_period`/标题/字符串反推 coverage 的逻辑
- **测试证据**: `test_public_download_json_preserves_cn_coverage_and_sec_empty_array` — CN `["FY", "Q4"]` 与 SEC `[]` 均经 `json.dumps`/`json.loads` strict round-trip 验证（行 2297–2344）；`test_fins_wait_adapter_projects_same_typed_download_object` — wait adapter 原样投影 coverage 空数组（行 2338–2347）

### 9. CLI 输出（PASS）

- **入口**: `dayu/cli/output.py:_download_document_line` 行 462
- **格式**: `covered_fiscal_periods=json.dumps(list(row.covered_fiscal_periods), ensure_ascii=False, separators=(',', ':'))` — 有界 JSON array，`ensure_ascii=False` 保持可读性
- **测试证据**: `test_fins_download_cli_mechanically_projects_typed_public_summary` 行 1386 `assert "covered_fiscal_periods=[]" in output`

### 10. README 更新（PASS）

- **根 `README.md`**: 新增 mode 互斥说明、CN/HK bare default policy、baseline missing 规则、CLI coverage 行说明（diff 行 9–19）
- **`dayu/fins/README.md`**: 新增全 results discovery、category-first、identity/coverage owner、public contract 说明（diff 行 44–52、行 62）
- **`tests/README.md`**: 新增 download owner matrix 与 coverage 测试事实（diff 行 1293）
- **未更新**: `dayu/README.md`、Host/Engine README、design doc（分层边界未变）
- **内容检查**: 三份 README 均只写当前实现事实，不写 plan/review 历史、future capability 或内部 evidence ID

### 11. 无 Host/Engine/storage schema/scope drift（PASS）

- Host/Engine 未修改；`dayu.runtime` 未修改
- Storage protocol（`repository_protocols.py`）未修改；`FilingManifestItem` schema 未扩大
- 一个 manifest item 继续代表一个 source identity；coverage 真值仅保存在 source meta
- 无 cross-layer import、无反向依赖

### 12. 测试覆盖与 static guard（PASS）

- **Focused union**: 13-file test union 全量通过（implementation artifact §5.1 报告 1065 passed）
- **整文件 line coverage**: 全部 13 个修改 production 文件均 ≥80%（implementation artifact §5.2 逐文件表，最低 `dayu/cli/output.py` 81%、`dayu/fins/pipelines/sec_pipeline.py` 82%）
- **Pyright**: 全量 `0 errors, 0 warnings, 0 informations`（implementation artifact §5.3）
- **Ruff/format**: changed-files 通过
- **Compileall**: 13 个 production module 通过
- **Contract guards**: 无 `TargetPeriodResolution`/`resolve_target_periods`/`CnReportQuery.target_periods`/candidate `.fiscal_period`；无 `13600` production 语义；ID call site 只传 `identity_period`；公共 coverage 无默认值；rebuild/CN adapter 无 `.get(default)`
- **特例 guard**: 新增分类/分支无 ticker/title/date/URL 特例

## Open Questions

1. **`stock_code_payload` 不在 core facts 中**（`cn_report_selection.py:_hk_announcement_core_facts` 行 662–668）。当前 core facts tuple 为 `(source_url, category_text, title, filing_date, language)`，与 plan §5.3 明确列出的五项一致。若真实 provider 数据中同一 `document_id` 出现不同 `stock_code_payload`（例如多代码发行人），当前实现会将第二条视为无害重复并 silent drop 第一条之后的所有行。这不违反 accepted plan，但若后续发现此类 case，需先在 plan 层确认 `stock_code_payload` 是否应纳入 core facts——不应在下游用 fallback 补偿。

2. **`_resolve_hk_results_identity` 对 Q4+Q1 组合返回 Q4 而非 None**（`cn_report_selection.py` 行 610–611）。当前实现仅在 Q4 与 Q2/Q3 同时命中时返回 None；Q4+Q1 返回 Q4。plan §5.3 results 矩阵的冲突规则明确列出了 Q4/Q2、Q4/Q3、Q3/Q2 三组冲突，未将 Q4/Q1 列为冲突（Q4 的 full-year 语义确实包含 Q1 的 single-quarter）。当前行为与 plan 一致，但若未来需要更严格的"任何多 quarter 命中即 ambiguous"策略，需更新 plan 矩阵。

## Residual Risk

| 风险 | 分类 | 缓解 |
|---|---|---|
| `_remove_tokens` 的 token 替换顺序依赖 tuple 字面量顺序——当前 `_HK_REPORT_H1_TOKENS` 中 "半年" 位于最后，若重排使更短 token 先于更长 token，可能导致 H1 token 移除不彻底 | 低 | 当前 FY token 集合（"全年"/"FULL YEAR" 等）与 H1 token 集合无子串关系；即使移除不彻底，最坏情况是 `has_fy` 多算导致误返回 None（ambiguous），不会错误分类 |
| 旧 schema source meta（无 `covered_fiscal_periods` 字段）在 rebuild 时会导致 `ValueError` 而非 skip——按 plan 此为预期 fail closed 行为，但可能使已有大量历史下载的 workspace 在 rebuild 时全部失败 | 设计决策 | plan 明确"schema 任务按 fresh schema 起库；不做旧库 fallback"；需在 post-fix evidence 中记录此行为，由用户裁决是否需要 migration |
| 真实 HKEX provider 的全 results group 可能返回远超当前 fixture 的 raw row 数量（例如大型发行人多年的全部业绩公告），selection 的 category/text 分类矩阵依赖通用 token 匹配，未在超大规模或边缘 category 文本上验证 | 中 | 已通过参数化 fixture 覆盖英文/繁中/简中 token；`_classify_hk_period_projection` 对任何 family/period 歧义返回 None（fail closed）；实际 robustness 需由 post-fix production evidence 验证 |
| `_HK_CATEGORY_REPORT_MARKERS` 中 `"REPORT"` 是宽泛英文 token——若 HKEX 未来新增包含 "REPORT" 的非财报 category（如 "DIRECTORS' REPORT" 作为独立 category），会被误判为 report family | 低 | 当前 HKEX category 分类体系稳定；即使误入 report family，后续 FY/H1 token 匹配失败会返回 None（因 `has_fy == has_h1 == False` 时返回 None） |

## 结论

**PASS** — 无 blocking finding。

Slice 3 实现完整落实了 plan §5.3（DL-F13）的全部 invariant：HKEX 全 results discovery 无 `13600` 残留、category-first 分类矩阵、`CnReportPeriodProjection` 严格不变量、CNInfo singleton 与 HK multi-period coverage、同 source ID 去重 fail closed、identity/coverage 语义分离、source meta 全量 coverage 写入与 fresh-schema fail closed rebuild、public mandatory 字段全构造点无默认值、全链 JSON 投影一致、CLI 输出有界可读、README 按职责更新、无 Host/Engine/storage schema drift。13-file focused test union 通过、全部 production 文件整文件 coverage ≥80%、pyright 零错误。

4 项 residual risks 均为已知设计决策边界或需 post-fix evidence 验证的范围，不构成当前实现的 blocking issue。
