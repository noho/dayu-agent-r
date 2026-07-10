# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S2

## Scope

- Mode: current changes (unstaged)
- Branch: `phaseflow/host-issues-control`
- Slice: P3-G S2 — CN/HK report candidate classification and fiscal inference ownership
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s2-code-review-ds.md`
- Included scope: 5 modified + 2 new files (total 713 lines changed: +122/-591 + 2 new modules)
- Validation: `pytest` 80 passed, `pyright` 0 errors, coverage 84%

## Verdict

**PASS** — 无 material finding。S2 正确将 CN/HK 产品级财报筛选、语言过滤、财期/财年推断、分组去重和 `CnReportCandidate` 构造从 HTTP downloader adapter 移到 pipeline helper `cn_report_selection.py`。下载器不再拥有业务过滤真源。

---

## Findings

未发现实质性问题。

---

## Review Focus 逐项核实

### 1. `cn_report_selection.py` 作为 product-level report selection 的真源

新模块（`dayu/fins/pipelines/cn_report_selection.py`，569 行）职责清单：

| 职责 | 函数 | 归属 |
| --- | --- | --- |
| CNINFO title blocklist 过滤 | `_is_title_blocked` | pipeline helper |
| CNINFO 英文语言标记检测 | `_has_cninfo_report_language_marker` | pipeline helper |
| CNINFO fiscal year 推断 | `_infer_cninfo_fiscal_year` | pipeline helper |
| CNINFO amended 优先选择 | `_pick_best_cninfo_announcement` | pipeline helper |
| CNINFO candidate 构造 | `_build_cninfo_candidate` | pipeline helper |
| HKEXNEWS 英文副本过滤 | `_is_english_hk_announcement` | pipeline helper |
| HKEXNEWS 英文财报标题检测 | `_looks_like_english_report_text` | pipeline helper |
| HKEXNEWS CJK 字符检测 | `_contains_cjk` | pipeline helper |
| HKEXNEWS fiscal period 推断 | `_infer_fiscal_period_from_text` | pipeline helper |
| HKEXNEWS fiscal year 推断 | `_infer_hk_fiscal_year` + `_parse_chinese_digit_year` | pipeline helper |
| HKEXNEWS amended 优先选择 | `_pick_best_hk_announcement` + `_is_hk_amended_title` | pipeline helper |
| HKEXNEWS candidate 构造 | `_build_hk_candidate` | pipeline helper |

两个 public entry point：
- `select_cninfo_report_candidates(query, announcements_by_period, read_head_meta)` → `tuple[CnReportCandidate, ...]`
- `select_hkexnews_report_candidates(query, announcements, read_head_meta)` → `tuple[CnReportCandidate, ...]`

模块依赖：只 import `cn_download_models`（dataclass/字面量类型）和标准库 — 无反向依赖。✅

### 2. Downloader 不再拥有业务过滤/推断

**CNINFO downloader**（`cninfo_downloader.py`）:
- `list_report_candidates` 现在只做：market/provider validation → fetch `_query_announcements` per period → raw JSON → `_parse_raw_announcement` → raw DTO → 委托 `select_cninfo_report_candidates(...)`
- `_http_head_meta` 仍保留为 downloader 方法（HTTP HEAD owner）— 通过 `read_head_meta` callback 传给 pipeline helper
- 删除的函数：`_is_title_blocked`、`_infer_fiscal_year`（业务推断版）、CNINFO candidate 构造逻辑

**HKEXNEWS downloader**（`hkexnews_downloader.py`）:
- `list_report_candidates` 现在只做：market/provider validation → fetch `_query_period_announcements` per category spec → raw JSON → `_parse_raw_announcement` → raw DTO → 委托 `select_hkexnews_report_candidates(...)`
- `_http_head_meta` 仍保留为 downloader 方法
- 删除的函数：`_infer_fiscal_year`、`_infer_fiscal_period_from_text`、`_looks_like_english_report_text`、`_contains_cjk`、`_is_hk_amended_title`、`_is_english_hk_announcement`、`_build_hk_candidate`、`_pick_best_hk_announcement`

**source scan 确认**: `rg "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders/` → **零命中**。✅

### 3. `list_report_candidates(...)` 作为 stable contract 的有效性

`CnReportDiscoveryClientProtocol.list_report_candidates` 仍返回 `tuple[CnReportCandidate, ...]`：
- 具体 downloader 实现变为 raw fetch + pipeline helper delegation
- 既存 workflow 消费 `CnReportCandidate` 不变
- Pipeline helper 通过 `ReadHeadMeta = Callable[[str], CnReportHeadMeta]` callback 接收 HEAD 元数据，保留了 HTTP 边界归属 downloader 的窄契约

**非 compatibility shim**: downloader 的 `list_report_candidates` 是既有 protocol contract，保留它不会隐藏语义漂移——因为候选选择真源已从 downloader 内部移到了 pipeline helper，downloader 只是 coordinator。Plan 允许保留 stable contract（实现报告已将 protocol 改写列为未来单独 breaking-contract slice）。✅

### 4. Raw DTO 定义与类型正确性

新增 raw DTO 均在 `dayu/fins/pipelines/cn_download_models.py`：

| DTO | 类型 | 用途 |
| --- | --- | --- |
| `CninfoRawAnnouncement` | frozen dataclass | 巨潮 raw 公告（announcement_id, title, source_url, announcement_date, file_extension） |
| `HkexnewsRawAnnouncement` | frozen dataclass | 披露易 raw 公告（document_id, title, category_text, source_url, filing_date, language） |
| `CnReportHeadMeta` | frozen dataclass | PDF HEAD 元数据（content_length, etag, last_modified — 均为 Optional） |
| `ReadHeadMeta` | TypeAlias = `Callable[[str], CnReportHeadMeta]` | pipeline helper 中定义，窄化 HTTP 边界 |

所有 DTO 均为 `frozen=True`，无可变状态。类型字段全部为 `str | None`、`int | None`，无 `Any`。✅

### 5. 测试迁移

| 测试类别 | 文件 | 覆盖 | 断言 |
| --- | --- | --- | --- |
| Pipeline helper（纯 domain 测试，无 HTTP mock） | `tests/fins/test_cn_report_selection.py` | 4 tests | CNINFO title blocklist + candidate 构造；CNINFO amended 优先 + 不同 year 保留；HKEXNEWS 英文过滤 + FY/Q2 推断；HKEXNEWS 同 period/year amended 优先 |
| Downloader 集成（HTTP mock + raw fetch） | `test_cninfo_downloader.py` / `test_hkexnews_downloader.py` | 保留既有 | 证明 raw adapter + pipeline helper 组合后用户可见行为不变 |
| Workflow 集成 | `test_cn_download_workflow.py` / `test_cn_pipeline.py` | 保留既有 | end-to-end download → source commit |

**迁移规则核实**: 每条被移除的 downloader 业务断言都在新 helper 测试中有对应断言。例如：
- 旧 CNINFO downloader title blocklist 断言 → `test_cninfo_selection_filters_blocklisted_titles_and_builds_candidate`
- 旧 HKEXNEWS downloader 英文过滤 + FY/Q2 推断 → `test_hkexnews_selection_filters_english_and_infers_periods`

### 6. S2 未越界到 S1/S3/S4

| Slice | 行为 | S2 状态 |
| --- | --- | --- |
| S1 SEC form parser | `filing_semantics.py` | ❌ 未修改 — 正确 |
| S3 rejection registry | typed entry | ❌ 未实现 — 正确 |
| S4 XBRL total | contract validation | ❌ 未实现 — 正确 |

S2 的 `CnFiscalPeriod` 是 `Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`，与 S1 的 `FiscalPeriod` TypeAlias 字面量集合完全一致。S2 未迁移 `CnFiscalPeriod` 消费 S1 的 `FiscalPeriod`——这是计划的设计决策：CN/HK `CnFiscalPeriod` 迁移为消费共享 domain 类型属于 S1 scope 的后续 step。当前两个 TypeAlias 的 Literal 值集合相同，运行时兼容。✅

### 7. Tests, pyright, coverage, typing, docstrings

| 检查项 | 状态 |
| --- | --- |
| 80 tests 全部通过 | ✅ (76 downloader/workflow + 4 new helper) |
| pyright 0 errors | ✅ |
| `cn_report_selection.py` coverage 84% | ✅ 超过 80% |
| 全部 public/private 函数有中文 docstring | ✅ 569 行中每个函数都有完整 Args/Returns/Raises |
| 无 `Any` / `object` 类型 | ✅ 全部 frozen dataclass + `Optional[str|int]` + `Literal` |
| 无 `hasattr`/`getattr` | ✅ |
| 无魔法字符串扩散 | ✅ 常量全部为模块级 `Final` tuple/dict |

---

## Owner Boundary Assessment

| 事实 | Producer | Validator (S2) | Consumer |
| --- | --- | --- | --- |
| CN raw announcements | CNINFO HTTP endpoint → `_query_announcements` + `_parse_raw_announcement` | Downloader（HTTP/JSON/raw fields） | `select_cninfo_report_candidates` |
| HK raw announcements | HKEXNEWS HTTP endpoint → `_query_period_announcements` + `_parse_raw_announcement` | Downloader（HTTP/JSON/raw fields） | `select_hkexnews_report_candidates` |
| CN/HK title blocklist / language filter | — | `cn_report_selection.py`（`_is_title_blocked`, `_is_english_hk_announcement`） | `select_cninfo_report_candidates` / `select_hkexnews_report_candidates` |
| Fiscal period/year inference | — | `cn_report_selection.py`（`_infer_cninfo_fiscal_year`, `_infer_hk_fiscal_year`, `_infer_fiscal_period_from_text`） | Candidate 构造 |
| Amended priority selection | — | `cn_report_selection.py`（`_pick_best_cninfo_announcement`, `_pick_best_hk_announcement`） | Candidate 构造 |
| `CnReportCandidate` 构造 | Pipeline helper | `_build_cninfo_candidate` / `_build_hk_candidate` | Workflow → source commit → source meta → direct stream |
| PDF HEAD meta | Downloader HTTP | `_http_head_meta` → `ReadHeadMeta` callback | Pipeline helper 用于 candidate `content_length`/`etag`/`last_modified` |

---

## Adversarial Failure Pass

- **Downloader HTTP 失败**: downloader 仍抛 `RuntimeError` → workflow 处理 → ✅
- **Pipeline helper 输入空 raw announcements**: `select_cninfo_report_candidates` 和 `select_hkexnews_report_candidates` 的循环在空 iterable 上正常执行，返回空 tuple → ✅
- **`read_head_meta` callback 失败**: 异常在 pipeline helper 内传播（未捕获）→ 调用方（downloader）处理 → ✅
- **Fiscal year 推断失败（所有规则未命中）**: `_infer_cninfo_fiscal_year` / `_infer_hk_fiscal_year` 返回 `None` → 该公告被跳过 → ✅
- **中文数字年份非法**: `_parse_chinese_digit_year` 对格式异常返回 `None` → fiscal year 推断失败 → 公告跳过 → ✅
- **旧 downloader 内业务函数残留**: `rg` 扫描确认零命中 → ✅
- **S1 SEC domain 文件未触碰**: `filing_semantics.py` 不在 diff 中 → ✅

---

## Residual Risk

- **`CnFiscalPeriod` 尚未迁移为消费 S1 共享 domain type**: S2 的 `CnFiscalPeriod` 和 S1 的 `FiscalPeriod` 是相同的 Literal 值集合但不同的 TypeAlias。plan Design Decision 3 要求迁移，但 S2 未完成此迁移。当前运行时兼容（值相同），但 mypy/pyright 将它们视为不同类型。建议在 S1 或 S2 的后续 step 中将 `CnFiscalPeriod` 改为 `from dayu.fins.domain.filing_semantics import FiscalPeriod as CnFiscalPeriod` 的 re-export。
- **`list_report_candidates(...)` protocol 仍返回 `CnReportCandidate`**: 计划将此列为未来 breaking-contract slice 的安全项。当前 downloader 实现为 coordinator role，非 candidate 构造 owner。
- **Provider category 参数仍在 downloader**: `_PERIOD_TO_CATEGORY` 和 `_PERIOD_TO_CATEGORY_SPEC` 在 downloader 内定义。这些映射是 provider-specific 的请求参数（HTTP adapter 范畴），不是产品级筛选规则，归属正确。
