# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S2 Fix

## Scope

- Mode: current changes (unstaged) — S2 fix re-review
- Branch: `phaseflow/host-issues-control`
- Slice: P3-G S2 fix (`P3-G-S2-CR-F01`)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s2-rereview-ds.md`
- Validation: `pytest` 80 passed, `pyright` 0 errors

## Verdict

**PASS** — `P3-G-S2-CR-F01` 已正确修复。`CnFiscalPeriod` 现在消费共享 domain `FiscalPeriod` type，无第二套 Literal 定义，无兼容 wrapper。

---

## Fix Verification

### P3-G-S2-CR-F01 — `CnFiscalPeriod` Consumes Shared Domain `FiscalPeriod` ✅ FIXED

| Controller 要求 | 状态 | 直接证据 |
| --- | --- | --- |
| `CnFiscalPeriod` 消费共享 domain type | ✅ | `cn_download_models.py:24`: `from dayu.fins.domain.filing_semantics import FiscalPeriod`；行 30: `CnFiscalPeriod: TypeAlias = FiscalPeriod` |
| 无第二套 `Literal["FY", "H1", ...]` 定义 | ✅ | `rg -n "CnFiscalPeriod = Literal" dayu/fins tests/fins/` → 零命中 |
| 无兼容 wrapper/re-export 模块 | ✅ | `CnFiscalPeriod` 直接在 `cn_download_models.py` 中定义为 TypeAlias，CN/HK 语义 docstring 保留但值集合来自 domain 真源 |
| All 下游消费者类型兼容 | ✅ | `cn_report_selection.py`、`cninfo_downloader.py`、`hkexnews_downloader.py` 的 `CnFiscalPeriod` import 不变，pyright 零报错 |
| S2 original PASS findings 仍有效 | ✅ | 80 tests passed；下载器零业务函数残留（同 original review source scan） |

---

## Original S2 PASS Conditions Re-verified

| 条件 | Original S2 状态 | Fix 后状态 |
| --- | --- | --- |
| `cn_report_selection.py` 为 report selection 真源 | ✅ | ✅ 不变 |
| 下载器不再拥有业务过滤/推断函数 | ✅ | ✅ `rg` 确认零命中 |
| Raw DTO 类型正确 | ✅ | ✅ 不变 |
| 测试迁移完成 | ✅ | ✅ 80 passed |
| S1/S3/S4 未越界 | ✅ | ✅ 不变 |

---

## New Defect Scan

Fix 仅修改 `cn_download_models.py` 中的 `CnFiscalPeriod` 定义。对该文件的完整变更走读：

- `from dayu.fins.domain.filing_semantics import FiscalPeriod` — 新增导入，方向正确（domain → pipeline models）
- `CnFiscalPeriod: TypeAlias = FiscalPeriod` — 替换了原来的 `CnFiscalPeriod = Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]`
- 模块 docstring 对应更新，提及「共享 domain 财期真源」
- `CnReportCandidate` 的 `fiscal_period: CnFiscalPeriod` 类型不变 — pyright 兼容
- `__all__` 中的 `"CnFiscalPeriod"` export 不变
- 无其他文件修改

无新增 material defect。

## Open Questions

无。

## Residual Risk

- Fix 前 S2 residual risk（`CnReportDiscoveryClientProtocol` stable contract、provider category 仍在 downloader）不变。
