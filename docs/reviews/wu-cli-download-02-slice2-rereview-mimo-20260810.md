# Code Review (Re-review)

## Scope

- Mode: current changes
- Branch: `codex/download-oracle`
- Base: `main` (selected base)
- Output file: `docs/reviews/wu-cli-download-02-slice2-rereview-mimo-20260810.md`
- Included scope: DL-F14 Slice 2 — market-specific typed form policy、effective/discovery/missing 三路 data flow、rebuild local-only，以及 S2-CR-01/S2-CR-02 修复
- Excluded scope: Slice 3/DL-F13、真实 CLI、README 或其它命令
- Parallel review coverage: 无

## Input artifacts

- `docs/gateflow/wu-cli-download-02-slice2-code-review-adjudication-20260810.md`
- `docs/gateflow/wu-cli-download-02-slice2-implementation-20260810.md`（已更新至 §12 fix gate）
- `docs/reviews/wu-cli-download-02-slice2-code-review-mimo-20260810.md`（原 MiMo review）
- `docs/reviews/wu-cli-download-02-slice2-code-review-ds-20260810.md`（原 DS review）
- 当前完整未提交 diff

## Findings

未发现实质性问题。

### S2-CR-01 验证：`filters.start_dates` 直接从 `period_windows` 投影 ✅

**Adjudication 要求**：download 的 `filters.start_dates` 直接从既有 `period_windows` 投影 `{item.fiscal_period: item.start_date}`；补 owner test 精确断言未显式 start 时 FY 与 Q1/H1 的值不同且等于 policy window 结果。

**直接证据**：`cn_download_workflow.py:367`（diff 行 217）

```python
# 旧代码
"start_dates": {period: window.start_date for period in period_policy.discovery_periods},

# 新代码
"start_dates": {item.fiscal_period: item.start_date for item in period_windows},
```

修复正确：download 路径现在直接从 `period_windows`（`resolve_period_windows` 返回的 `PeriodDownloadWindow` tuple）投影，与 rebuild 路径（`cn_download_rebuild.py:113`）使用相同来源。

**Owner test 验证**：`test_cn_bare_download_projects_actual_default_period_window_start_dates`（diff 行 919-961）

```python
events = asyncio.run(
    _collect_events_async(
        pipeline=pipeline,
        ticker="600519",
        form_type=None,
        start_date=None,  # 未显式指定起点
        end_date="2026",
        overwrite=False,
        start_is_explicit=False,
    )
)
result = _final_result(events)
filters = result["filters"]
start_dates = filters["start_dates"]
assert start_dates == {
    "FY": "2021-11-01",   # 五年窗口：2026-11-01 回退 5 年 - 60 天
    "H1": "2024-11-01",   # 两年窗口：2026-11-01 回退 2 年 - 60 天
    "Q1": "2024-11-01",
    "Q3": "2024-11-01",
}
```

该测试真实证明：
1. FY 与其它财期的窗口起点不同（五年 vs 两年）
2. 下载路径与重建路径使用相同的 `PeriodDownloadWindow` 投影
3. Key 集仍等于 CN bare discovery periods

**结论**：S2-CR-01 已正确修复，download/rebuild 现在同源消费 `period_windows`。

### S2-CR-02 验证：`CN_FISCAL_PERIOD_ORDER` 仅加入 owner `__all__` 且无 re-export ✅

**Adjudication 要求**：仅在现有 `__all__` 中加入 `"CN_FISCAL_PERIOD_ORDER"`，并在 owner test 断言导出清单；不得新增 re-export 或兼容路径。

**直接证据**：`cn_download_models.py:263-264`（diff 行 83-84）

```python
__all__ = [
    "CN_FISCAL_PERIOD_ORDER",  # 新增
    "CN_PIPELINE_DOWNLOAD_VERSION",
    ...
]
```

仅在 owner 模块的 `__all__` 中加入该名称，未在其它模块新增 re-export。

**Owner test 验证**：`test_cn_fiscal_period_order_is_declared_in_owner_module_exports`（diff 行 964-977）

```python
def test_cn_fiscal_period_order_is_declared_in_owner_module_exports() -> None:
    """canonical 财期顺序应由 owner 模块的显式公共清单声明。"""
    assert "CN_FISCAL_PERIOD_ORDER" in _cn_download_models.__all__
```

该测试直接断言常量存在于 owner 模块的 `__all__`。

**结论**：S2-CR-02 已正确修复，`CN_FISCAL_PERIOD_ORDER` 仅在 owner 模块 `__all__` 中声明，无 re-export。

### 全量 Slice 2 语义回扫 ✅

在验证 S2-CR-01/S2-CR-02 修复的同时，对完整 diff 进行全量回扫，确认：

#### 1. Semantic owner 唯一性 ✅

`CnDownloadPeriodPolicy` 在 `cn_form_utils.py:62-96` 是唯一的 policy owner，三集合都由此 frozen dataclass 唯一产生。

#### 2. CN bare default = FY,H1,Q1,Q3 ✅

`cn_form_utils.py:40`：`CN_BARE_DEFAULT_PERIODS = ("FY", "H1", "Q1", "Q3")`

#### 3. HK bare effective/missing=FY,H1 且 discovery 六期 ✅

`cn_form_utils.py:43-47`：
- `HK_BARE_EFFECTIVE_PERIODS = ("FY", "H1")`
- `HK_BARE_DISCOVERY_PERIODS = CN_FISCAL_PERIOD_ORDER`（六期）

#### 4. Explicit CN Q2/Q4 行为未改变 ✅

`cn_form_utils.py:246-251`：显式 forms 令三集合相等。

#### 5. Missing/summary/manifest/meta 投影同源 ✅

- `cn_download_workflow.py:367`：`filters.forms` 使用 `period_policy.effective_periods`
- `cn_download_workflow.py:568-586`：`_resolve_missing_periods` 只消费 `missing_eligible_periods`
- `cn_download_rebuild.py:99`：`form_values` 使用 `period_policy.effective_periods`
- `cn_download_rebuild.py:121`：`missing_periods` 始终为空 list

#### 6. Rebuild 无网络/转换/processed 修改 ✅

`cn_download_rebuild.py:36-124`：rebuild 只基于本地 source，不访问 provider。

#### 7. Filters.forms 与 filters.start_dates 键一致性 ✅

- `forms` 始终 = `effective_periods`
- `start_dates` 现在直接从 `period_windows` 投影（S2-CR-01 修复后）

#### 8. cn_report_selection.py 格式 churn 可接受 ✅

diff 只有两处语义变更（`query.target_periods` → `query.discovery_periods`），其余是 Ruff 格式化。

#### 9. 测试 owner-level 且未由 fake 固化错误语义 ✅

所有测试断言 owner-level contract 行为。

#### 10. 过程 perl 偏差 ✅

implementation artifact §8 已记录，最终 diff 无 allowlist 外写入。

### Scope/Guards 验证 ✅

- 旧 contract guard：`TargetPeriodResolution|resolve_target_periods|CnReportQuery.target_periods|query.target_periods|target_periods=` 无匹配
- HKEX unchanged guard：`_HKEXNEWS_T2_QUARTERLY_RESULTS = "13600"` 仍存在
- Slice 3 absence guard：`CnReportPeriodProjection|covered_fiscal_periods|period_projection|identity_period|t2code=-2` 无匹配
- allowlist guard：Python diff 精确为 8 production + 5 tests
- S2-CR-01 guard：新投影 `{item.fiscal_period: item.start_date for item in period_windows}` 存在；旧 `{period: window.start_date ...}` 无匹配
- S2-CR-02 guard：`"CN_FISCAL_PERIOD_ORDER"` 存在于 owner `__all__`

## Open Questions

无。

## Residual Risk

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| HKEX 仍使用季度 `13600`，尚未扩展为全 results group | covered by later approved slice | WU-CLI-DOWNLOAD-02 Slice 3 |
| candidate multi-period identity、coverage、category-first classification、source/public projection 尚未实现 | covered by later approved slice | WU-CLI-DOWNLOAD-02 Slice 3 |
| 真实 CN/HK provider 与 production CLI post-fix evidence 未运行 | covered by later approved slice | Slice 3 完成并通过后，按 accepted plan 进行 aggregate review 与 evidence gate |

无 unclassified residual risk，无 blocking open question。

## Conclusion

**PASS**。S2-CR-01 和 S2-CR-02 两个 accepted findings 均已正确修复：

1. **S2-CR-01**：download `filters.start_dates` 现在直接从 `period_windows` 投影，与 rebuild 同源；owner test 精确断言 FY 五年窗口与 H1/Q1/Q3 两年窗口的不同起点值。
2. **S2-CR-02**：`CN_FISCAL_PERIOD_ORDER` 仅加入 owner 模块 `__all__`，无 re-export；owner test 断言导出清单。

全量 Slice 2 语义回扫未发现新问题。所有 guards 通过。residual risk 均属于后续 Slice 3 范围。
