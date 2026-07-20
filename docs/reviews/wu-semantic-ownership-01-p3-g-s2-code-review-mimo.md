# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S2

## Scope

- Mode: current changes (unstaged workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `79629dfa` (S1 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s2-code-review-mimo.md`
- Included scope: 7 files (+122/-591) + 2 new files — S2 CN/HK report candidate classification and fiscal inference ownership
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Findings

未发现实质性问题。

逐项检查：

### 1. `cn_report_selection.py` 是产品级 CN/HK report selection 真源

`dayu/fins/pipelines/cn_report_selection.py`（568 行）包含：

- `select_cninfo_report_candidates(...)` — CNInfo 候选选择主入口：title blocklist → fiscal year 推断 → 同 period/year 分组 → amended 优先 → candidate 构造 → 排序。
- `select_hkexnews_report_candidates(...)` — HKEXNews 候选选择主入口：英文副本过滤 → fiscal period/year 推断 → 同 period/year 分组 → amended 优先 → candidate 构造 → 排序。
- `_is_title_blocked(...)` — CNInfo 标题黑名单（20+ 关键词）。
- `_infer_cninfo_fiscal_year(...)` — CNInfo 财年推断（标题正则 → 日期回退）。
- `_infer_fiscal_period_from_text(...)` — HKEXNews 财期推断（标题+分类文本 token 匹配）。
- `_infer_hk_fiscal_year(...)` — HKEXNews 财年推断（阿拉伯数字 → 中文数字 → 日期回退）。
- `_pick_best_cninfo_announcement(...)` / `_pick_best_hk_announcement(...)` — 同组 amended 优先选择。
- `_is_english_hk_announcement(...)` / `_looks_like_english_report_text(...)` / `_contains_cjk(...)` — 英文副本过滤。
- `_build_cninfo_candidate(...)` / `_build_hk_candidate(...)` — `CnReportCandidate` 构造。

模块只依赖 `cn_download_models.py` 中的 typed DTO，不 import downloader、storage 或 processor。✅

### 2. Downloader 不再拥有业务筛选

**CNInfo downloader**：
- 已删除：`_TITLE_BLOCKLIST`、`_REPORT_NOTICE_TITLE_TOKENS`、`_REPORT_TITLE_TOKENS`、`_TITLE_AMENDED_TOKENS`、`_PERIOD_SORT_KEY`、`_is_title_blocked`、`_infer_fiscal_year`、`_pick_best_announcement`、`_build_candidate_from_announcement`。
- `list_report_candidates(...)` 现在收集 `raw_by_period` 后委托 `select_cninfo_report_candidates(query, announcements_by_period, read_head_meta)`。

**HKEXNews downloader**：
- 已删除：`_PERIOD_SORT_KEY`、`_TITLE_AMENDED_TOKENS`、`_ENGLISH_REPORT_TITLE_TOKENS`、`_PERIOD_INFERENCE_TOKENS`、`_TITLE_YEAR_PATTERN`、`_TITLE_CHINESE_YEAR_PATTERN`、`_CHINESE_DIGIT_TO_INT`、`_RawHkAnnouncement`、`_HeadMeta`、`_infer_fiscal_period_from_text`、`_infer_fiscal_year`、`_pick_best_announcement`、`_is_amended_title`、`_is_english_announcement`、`_looks_like_english_report_text`、`_contains_cjk`、`_build_candidate`。
- `list_report_candidates(...)` 现在收集 `raw_announcements` 后委托 `select_hkexnews_report_candidates(query, announcements, read_head_meta)`。

Source scan `rg -n "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders dayu/fins/pipelines` 仅命中 `cn_report_selection.py`。✅

### 3. `list_report_candidates(...)` 作为 raw-fetch + pipeline-helper 委托

Downloader 的 `list_report_candidates(...)` 保留为 `CnReportDiscoveryClientProtocol` 的实现，内部变为：
1. HTTP 请求 + JSON decode → raw announcements。
2. 委托 pipeline helper 做业务选择。

这不是隐藏的兼容 seam，而是 plan 定义的 S2 contract boundary：protocol 稳定，concrete 实现内部委托。✅

### 4. Raw DTO 和 `CnReportHeadMeta` 正确放置

`cn_download_models.py` 新增：
- `CnReportHeadMeta` — frozen dataclass，`content_length` / `etag` / `last_modified`。HTTP HEAD 边界事实。
- `CninfoRawAnnouncement` — frozen dataclass，`sec_code` / `announcement_id` / `title` / `announcement_date` / `adjunct_url` / `source_url`。Provider raw 字段。
- `HkexnewsRawAnnouncement` — frozen dataclass，`document_id` / `title` / `source_url` / `stock_code_payload` / `category_text` / `filing_date` / `language`。Provider raw 字段。

三个 DTO 都在 `__all__` 中导出。✅

### 5. 测试迁移

- `test_cn_report_selection.py`（285 行）：4 个纯 helper 测试，无 HTTP mock。
  - `test_cninfo_selection_filters_blocklisted_titles_and_builds_candidate`
  - `test_cninfo_selection_keeps_years_and_prefers_amended_per_year`
  - `test_hkexnews_selection_filters_english_and_infers_periods`
  - `test_hkexnews_selection_groups_by_year_and_prefers_amended`
- 既有 downloader tests 保留为 concrete `list_report_candidates(...)` integration coverage。
- Coverage: `cn_report_selection.py` 84%（≥80%）。✅

### 6. S1/S3/S4 语义未改变

- S1 SEC form parser：未修改。
- S3 rejection registry：未修改。
- S4 XBRL total contract：未修改。✅

### 7. Tests、pyright、coverage、README

- **Tests**: 76 passed。
- **Pyright**: 0 errors。
- **Coverage**: `cn_report_selection.py` 84%。
- **Source scan**: 业务筛选函数仅在 `cn_report_selection.py`。
- **README**: `dayu/fins/README.md` 新增 "Downloaders 与 CN/HK report selection" 章节。`tests/README.md` 更新 Fins 测试覆盖描述。✅

## Residual Risk

- `CnReportDiscoveryClientProtocol.list_report_candidates(...)` 仍返回 `CnReportCandidate`；后续若要改为 raw discovery contract，需单独 breaking-contract slice。
- Provider category/request 参数仍在 downloader 内（HTTP 请求构造事实）。
- HEAD meta 通过 callback 读取，保留 HTTP owner 窄边界。

## Verdict

**PASS** — S2 正确实现了 plan 中的 CN/HK report candidate classification and fiscal inference ownership。产品级业务筛选从 downloader 迁入 pipeline helper，downloader 只保留 HTTP/raw provider 边界，测试迁移完整，未改变 S1/S3/S4 语义。
