# WU-CLI-DOWNLOAD-02 Slice 2 — AgentDS Independent Code Review

## Scope

- Mode: Current Changes（相对于 HEAD 的工作树 diff）
- Branch: `codex/download-oracle`
- HEAD: `401edda723750d1cb18ad6f6572cda79d948679d`
- Base: `HEAD`（未提交工作树）
- Review target: DL-F14 Slice 2 — market-specific typed form policy、effective/discovery/missing 三路 data flow、rebuild local-only
- Output file: `docs/reviews/wu-cli-download-02-slice2-code-review-ds-20260810.md`
- Included scope: Slice 2 allowed files（8 production + 5 tests，精确等于 plan §6 Slice 2 allowlist）
- Excluded scope: Slice 3（DL-F13 HKEX discovery/category-first/projection/coverage）、Slice 1（DL-F12 mode invariant）、README、CLI、真实 provider evidence
- Parallel review coverage: 无（单 reviewer 直接走读全部 diff + 完整 source + 关键 test）

### Verification commands run

- `rg` old-contract guard: `TargetPeriodResolution|resolve_target_periods|CnReportQuery.target_periods|query.target_periods` — 0 matches in production + tests ✓
- `rg` Slice 3 guard: `CnReportPeriodProjection|covered_fiscal_periods|period_projection|identity_period|t2code=-2` — 0 matches in diff ✓
- `rg` provider-id guard: `0700|11793094|12056833` — 0 matches in production code (only in unrelated `ticker_normalization.py` docstring) ✓
- `rg` perl deviation guard: `resolve_discovery_periods` — 0 matches ✓
- `rg` HKEX unchanged guard: `_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` — still exists at `hkexnews_downloader.py:75` ✓
- Runtime verification: all policy contract assertions passed ✓

## Findings

### 1-NOT-FIXED-低-`filters.start_dates` 值语义在 download 与 rebuild 路径不一致

- **入口/函数**: `run_cn_download_stream_impl` → `_build_result(... filters=...)` / `rebuild_cn_download_artifacts` → result `"filters"`
- **文件(行号)**:
  - `dayu/fins/pipelines/cn_download_workflow.py:368`: `{period: window.start_date for period in period_policy.discovery_periods}`
  - `dayu/fins/pipelines/cn_download_rebuild.py:111-113`: `{item.fiscal_period: item.start_date for item in period_windows}`
- **输入场景**: `start_date` 为 `None`（用户未显式指定起始日期）时，download path 对全部 `discovery_periods` key 赋予同一个全局回退窗口起点的值，而 rebuild path 对每个 key 赋予各自 per-period lookback（FY=5yr, 其它=2yr）的不同起点。
- **实际分支**: download 走 `resolve_window(start_date, end_date)` 取得全局 `window.start_date`；rebuild 直接消费 `resolve_period_windows` 返回的逐期 `item.start_date`。
- **预期行为**: 两路径的 `filters.start_dates` 应有统一的 key/value 语义——由于该字段的关键契约是 key 集（`discovery_periods`）且无已知 consumer 依赖 value 精度，可直接统一为 per-period window dates。
- **实际行为**: 当 `start_date=None` 时，download 端 `"Q1"` key 对应的 start 值为 FY 回退日起点（约 end-5yr-60d）而非 Q1 自身 2yr 回退起点；rebuild 端 `"Q1"` 对应正确的 2yr 回退起点。两路径对同一 key 产生不同值。
- **直接证据**: download 的 `window = resolve_window(start_date, end_date)` 在缺省起点时固定用 `_ANNUAL_LOOKBACK_YEARS=5` 回归；rebuild 没有调用 `resolve_window`，直接用 per-period `resolve_period_windows` 产物。见 `cn_download_workflow.py:98-103` 与 `cn_download_rebuild.py:69-74`。
- **影响**: 下游 consumer（目前无已知依赖 `start_dates` 值的业务逻辑）若未来期望 `filters.start_dates` 统一表达"对该 period 实际使用的起始查找日期"，rebuild 路径正确而 download 路径偏差；反之若期望"统一用户请求起点"，则 download 路径正确而 rebuild 路径偏差。当前属于 contract ambiguity，非 correctness 缺陷。
- **建议改法和验证点**: 在 `filters.start_dates` 语义文档中明确定义其 key/value 契约（"key 为 discovery_periods，value 为逐期实际生效的扫描起点"），然后统一两路径均使用 `resolve_period_windows` 派生 value。低成本，可结合 Slice 3 顺便修正。
- **修复风险（低）**: 仅统一两路径的 value 取值源，不改变 key 集，不影响下游 adapter。
- **严重程度（低）**:

### 2-NOT-FIXED-低-`CN_FISCAL_PERIOD_ORDER` 未纳入模块 `__all__`

- **入口/函数**: 模块级 `__all__` 定义
- **文件(行号)**: `dayu/fins/pipelines/cn_download_models.py:265-280`
- **输入场景**: 任何使用 `from dayu.fins.pipelines.cn_download_models import *` 的调用方（虽然生产代码不应使用 wildcard import）。
- **实际分支**: N/A（静态导出清单缺失）。
- **预期行为**: plan §5.2 明确 `CN_FISCAL_PERIOD_ORDER` 是 "CN/HK 下载链路唯一的 canonical 财期顺序"，应作为公共 contract 显式导出。
- **实际行为**: `CN_FISCAL_PERIOD_ORDER` 不在 `__all__` 中，但显式 `from ... import CN_FISCAL_PERIOD_ORDER` 正常工作（`cn_form_utils.py:35` 直接 import 验证）。
- **直接证据**: `__all__` 列表（`cn_download_models.py:265-280`）包含 `CN_PIPELINE_DOWNLOAD_VERSION` 等其他顶层常量但不包含 `CN_FISCAL_PERIOD_ORDER`。
- **影响**: wildcard import 场景下不可见；显式 import 不受影响。与 plan 声明的 "唯一常量" 定位不一致。
- **建议改法和验证点**: 在 `__all__` 中追加 `"CN_FISCAL_PERIOD_ORDER"`。一字符串增加，零行为变化。
- **修复风险（低）**: 仅追加导出，不影响现有显式 import。
- **严重程度（低）**:

## Open Questions

无。

## Residual Risk

| 风险 | 分类 | Owner / 处置 |
|---|---|---|
| `_PERIOD_SORT_KEY` (cn_report_selection.py:27-34) 与 `CN_FISCAL_PERIOD_ORDER` 独立定义，尚未复用 | 按 plan 属于 Slice 3 完成时机 | WU-CLI-DOWNLOAD-02 Slice 3 |
| `_optional_period` (cn_download_rebuild.py:373-391) 硬编码六期值，新增财期需同步更新 | 低概率变更；`CnFiscalPeriod` 变更时 pyright 会在所有同类型 consumer 报错，可作为提醒 | 未来 domain period 扩展时自然触发 |
| `filters.start_dates` 值语义未在 plan/contract 中明确定义 | 文档/contract gap | 见 Finding 1；建议 Slice 3 或 closeout 阶段统一 |
| `cn_report_selection.py` 的 Ruff format churn 横跨 `_HK_PERIOD_INFERENCE_TOKENS` 四段（Q1~Q4），虽然 token 值/顺序/分类/控制流未改变，但较大的 diff 可能误导只读 diff 的后续 reviewer | 过程已记录在 implementation artifact §3.2 | 无需额外处置；本 review 已逐行逐值核验 |
| HKEX `t2code=13600` 仍在使用（Slice 2 正确未动），但 plan 要求在 Slice 3 替换为 `t2code=-2` | 按 plan 属于 Slice 3 | WU-CLI-DOWNLOAD-02 Slice 3 |

## Overall Verdict

**PASS** — 无 blocking finding。

Slice 2 正确实现了 accepted plan 的全部 DL-F14 目标：

1. **语义 owner 唯一**: `resolve_download_period_policy` 是三个期间集合的单一真源；workflow/rebuild 均从 owner 投影消费，未从 filters、rows、category 或字符串反推 policy。
2. **CN bare=FY,H1,Q1,Q3**: effective/discovery/missing 三集合均精确为此四期。
3. **HK bare effective/missing=FY,H1 且 discovery 六期**: 正确实现；test 精确断言六期 query + FY/H1 effective forms + FY/H1 missing。
4. **显式 CN Q2/Q4 行为未改变**: test 断言 query/effective/missing 三集合同为 (Q2, Q4)，无候选时 missing 正确报告 Q2/Q4。
5. **missing/summary/manifest/meta 投影同源**: `missing_periods` 从 `policy.missing_eligible_periods` + candidate `fiscal_period`（identity period）派生；summary 从真实 filing 结果计算；rebuild 不生成 missing。
6. **rebuild local-only**: test 断言 provider query/HTTP/download/converter 均为 0，PDF/Docling blob 不变，processed/reprocess marker 不变，`missing_periods` 始终空 list。
7. **`filters.forms` 与 `filters.start_dates` keys 清晰一致**: `forms` 始终 = `effective_periods`；`start_dates` keys 始终 = `discovery_periods`。values 有 minor inconsistency（Finding 1）。
8. **`cn_report_selection.py` 格式 churn 可接受**: 仅 Ruff 机械换行，token 值/顺序/分类/控制流未变。
9. **测试为 owner-level 且未由 fake 固化错误语义**: fake client 使用通用构造（无 0700/腾讯/固定 ID 硬编码），assertion 直接对账 policy contract 而非实现细节；HKEX 13600 assertion 由既有 test 保护证明 Slice 2 未提前进入 Slice 3。
10. **过程 perl 偏差未在最终 diff 留问题**: 所有 guard 通过，无残留误名。

两个 low-severity finding 均非 correctness 缺陷，且修复成本极低（Finding 2 为单行追加，Finding 1 可在 Slice 3 统一修正）。所有 Slice 3 边界清晰，无 scope creep。
