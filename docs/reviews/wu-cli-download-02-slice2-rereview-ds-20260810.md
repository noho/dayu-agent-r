# WU-CLI-DOWNLOAD-02 Slice 2 — AgentDS Independent Re-review

## Scope

- Mode: Current Changes（相对于 HEAD 的工作树 diff）
- Branch: `codex/download-oracle`
- HEAD: `401edda723750d1cb18ad6f6572cda79d948679d`
- Base: `HEAD`（未提交工作树）
- Re-review target: 验证 S2-CR-01 与 S2-CR-02 两个 accepted finding 的修复，并回扫全部 Slice 2 语义、scope 与 guards
- Input artifacts:
  - `docs/gateflow/wu-cli-download-02-slice2-code-review-adjudication-20260810.md`
  - `docs/gateflow/wu-cli-download-02-slice2-implementation-20260810.md`（含 fix gate §12）
  - `docs/reviews/wu-cli-download-02-slice2-code-review-mimo-20260810.md`
  - `docs/reviews/wu-cli-download-02-slice2-code-review-ds-20260810.md`（前轮 DS review）
- Output file: `docs/reviews/wu-cli-download-02-slice2-rereview-ds-20260810.md`
- Included scope: Slice 2 allowed files（8 production + 5 tests）
- Excluded scope: Slice 3、Slice 1、README、CLI、真实 provider evidence
- Parallel review coverage: 无

## Findings

未发现实质性问题。两个 accepted finding 均已在 fix gate 正确关闭。

### S2-CR-01 修复验证：download `filters.start_dates` 与 rebuild 同源

- **Adjudication required fix**: download 的 `filters.start_dates` 直接从既有 `period_windows` 投影 `{item.fiscal_period: item.start_date}`；补 owner test 证明未显式 start 时 FY 五年窗口与其它财期两年窗口不同。
- **当前代码证据**:
  - `dayu/fins/pipelines/cn_download_workflow.py:368`: `"start_dates": {item.fiscal_period: item.start_date for item in period_windows}`
  - `dayu/fins/pipelines/cn_download_rebuild.py:113`: `"start_dates": {item.fiscal_period: item.start_date for item in period_windows}`
  - 两路径投影表达式完全一致，同源 `period_windows`（均从 `resolve_period_windows(discovery_periods=period_policy.discovery_periods, ...)` 派生）。
  - 旧投影 `{period: window.start_date for period in ...}` 在 production/tests 中无匹配（`rg -F` exit 1）。
- **Owner test 证据**:
  - `test_cn_bare_download_projects_actual_default_period_window_start_dates`（新增于 `tests/fins/test_cn_download_workflow.py`）:
    - 使用 `form_type=None, start_date=None, end_date="2026", start_is_explicit=False`
    - 断言 `start_dates == {"FY": "2021-11-01", "H1": "2024-11-01", "Q1": "2024-11-01", "Q3": "2024-11-01"}`
    - FY 五年窗口（2021-11-01）与 H1/Q1/Q3 两年窗口（2024-11-01）不同，证明值直接来自 per-period `period_windows` 而非全局 `resolve_window`。
  - 已有 test `test_cn_hk_bare_rebuild_is_local_only_and_always_has_empty_missing` 继续断言 rebuild 的 `start_dates` key 集。
- **判定**: **已修复**。download 与 rebuild 的 `filters.start_dates` 投影现在同源（`period_windows`），key/value 语义一致。

### S2-CR-02 修复验证：`CN_FISCAL_PERIOD_ORDER` 仅加入 owner `__all__` 且无 re-export

- **Adjudication required fix**: 仅在 owner 模块 `__all__` 中加入 `"CN_FISCAL_PERIOD_ORDER"`，在 owner test 断言导出清单；不得新增 re-export 或兼容路径。
- **当前代码证据**:
  - `dayu/fins/pipelines/cn_download_models.py:266`: `"CN_FISCAL_PERIOD_ORDER"` 在 `__all__` 列表首行。
  - `dayu/fins/pipelines/cn_form_utils.py:35`: 跨模块直接 import `CN_FISCAL_PERIOD_ORDER`（正确的显式消费者模式），但 `cn_form_utils.__all__` 中不包含该名称（已验证 `assert 'CN_FISCAL_PERIOD_ORDER' not in f.__all__`）。
  - `rg` 全仓搜索 `CN_FISCAL_PERIOD_ORDER` 仅命中三处：owner 定义（`cn_download_models.py:41`）、owner `__all__`（`cn_download_models.py:266`）、合法消费者直接 import（`cn_form_utils.py:35,46,246,359`）、owner test（`test_cn_download_workflow.py:1123`）。零 re-export。
- **Owner test 证据**:
  - `test_cn_fiscal_period_order_is_declared_in_owner_module_exports`（新增于 `tests/fins/test_cn_download_workflow.py`）:
    - `assert "CN_FISCAL_PERIOD_ORDER" in _cn_download_models.__all__`
    - 直接对 owner 模块的 `__all__` 做 membership 断言。
- **判定**: **已修复**。`CN_FISCAL_PERIOD_ORDER` 仅在 owner 模块 `__all__` 中声明，零 re-export，owner test 精确断言。

### 全量 Slice 2 语义回扫

对 fix gate 修改的 3 个文件之外的所有 Slice 2 allowed files 进行了完整性回扫，确认修复未引入回归：

| 检查项 | 证据 | 结论 |
|---|---|---|
| 旧 contract 无残留 | `rg TargetPeriodResolution\|resolve_target_periods\|CnReportQuery.target_periods\|query.target_periods` → 0 matches | ✓ |
| Slice 3 边界未渗透 | `rg CnReportPeriodProjection\|covered_fiscal_periods\|period_projection\|identity_period\|t2code=-2` 在 diff 中 → 0 matches | ✓ |
| HKEX `13600` 未提前改动 | `_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` 仍在 `hkexnews_downloader.py:75`，HKEX category diff → 0 matches | ✓ |
| Python diff allowlist | 精确 8 production + 5 tests = 13 Python 文件 | ✓ |
| 全量 pyright | 0 errors, 0 warnings, 0 informations | ✓ |
| Slice 2 tests | 228 passed, 3 warnings（warnings 为既有 `edgar` 依赖） | ✓ |
| Fix owner tests | `test_cn_bare_download_projects_actual_default_period_window_start_dates` + `test_cn_fiscal_period_order_is_declared_in_owner_module_exports` → 2 passed | ✓ |
| `CN_FISCAL_PERIOD_ORDER` 无 re-export | 仅在 owner 模块 `__all__` 与合法显式 import 中出现 | ✓ |
| 旧 `start_dates` 投影无残留 | `rg -F 'period: window.start_date for period in'` → 0 matches | ✓ |
| download/rebuild `start_dates` 同源 | 两文件同一表达式 `{item.fiscal_period: item.start_date for item in period_windows}` | ✓ |

## Open Questions

无。

## Residual Risk

| 风险 | 分类 | Owner / 处置 |
|---|---|---|
| `_PERIOD_SORT_KEY` 与 `CN_FISCAL_PERIOD_ORDER` 独立定义 | 按 plan/adjudication 属于 Slice 3 | WU-CLI-DOWNLOAD-02 Slice 3 |
| `_optional_period` 硬编码六期值 | adjudication 明确拒绝处理 | 未来 domain period 扩展时自然触发 |
| HKEX `13600`、multi-period projection、真实 CLI evidence | 按 plan 属于 Slice 3 及后续 aggregate/evidence gate | WU-CLI-DOWNLOAD-02 Slice 3 |
| `cn_report_selection.py` Ruff format churn | 已有两名 reviewer 核验无 token/顺序/分类变化 | 无需额外处置 |

## Overall Verdict

**PASS** — S2-CR-01 和 S2-CR-02 均已正确修复，无新问题。

修复范围精确在 adjudication 指定的 3 个文件（`cn_download_workflow.py`、`cn_download_models.py`、`test_cn_download_workflow.py`），未扩散到其它 Slice 2 文件或 Slice 3 边界。整个 Slice 2 实现（implementation + fix gate）的语义 owner、三路 data flow、rebuild local-only、测试 owner-level 与 scope/guard 全部通过。
