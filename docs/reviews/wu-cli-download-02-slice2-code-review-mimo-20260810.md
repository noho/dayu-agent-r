# Code Review

## Scope

- Mode: current changes
- Branch: `codex/download-oracle`
- Base: `main` (selected base)
- Output file: `docs/reviews/wu-cli-download-02-slice2-code-review-mimo-20260810.md`
- Included scope: DL-F14 Slice 2 — market-specific typed form policy、effective/discovery/missing 三路 data flow、rebuild local-only
- Excluded scope: Slice 3/DL-F13、真实 CLI、README 或其它命令
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 验证结论

经过对完整 diff 的逐文件走读和 adversarial 检查，确认 Slice 2 实现符合 accepted plan 的所有要求：

#### 1. Semantic owner 唯一性 ✅

**证据**：`cn_form_utils.py:62-96`

`CnDownloadPeriodPolicy` 是唯一的 policy owner，三集合（effective_periods/discovery_periods/missing_eligible_periods）都由此 frozen dataclass 唯一产生。`__post_init__` 校验确保：
- 三个 tuple 非空、无重复、canonical 顺序
- `missing_eligible_periods ⊆ effective_periods ⊆ discovery_periods`

无第二个 policy owner、fallback 或 downstream 反推。

#### 2. CN bare default = FY,H1,Q1,Q3 ✅

**证据**：`cn_form_utils.py:40`

```python
CN_BARE_DEFAULT_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = ("FY", "H1", "Q1", "Q3")
```

`resolve_download_period_policy(None, "CN")` 返回三集合均为 `CN_BARE_DEFAULT_PERIODS`。测试 `test_cn_bare_download_consumes_policy_for_query_filters_and_missing` 验证 query/discovery/missing 均为 `FY,H1,Q1,Q3`。

#### 3. HK bare effective/missing=FY,H1 且 discovery 六期 ✅

**证据**：`cn_form_utils.py:43-47`

```python
HK_BARE_EFFECTIVE_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = ("FY", "H1")
HK_BARE_DISCOVERY_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = CN_FISCAL_PERIOD_ORDER
```

`resolve_download_period_policy(None, "HK")` 返回：
- `effective_periods = ("FY", "H1")`
- `discovery_periods = ("FY", "H1", "Q1", "Q2", "Q3", "Q4")`
- `missing_eligible_periods = ("FY", "H1")`

测试 `test_hk_bare_download_discovers_six_periods_but_only_fy_h1_are_missing_eligible` 验证：
- query.discovery_periods 为六期
- filters.forms 为 `["FY", "H1"]`
- missing 只按 FY/H1 identity 计算

#### 4. Explicit CN Q2/Q4 行为未改变 ✅

**证据**：`cn_form_utils.py:246-251`

```python
explicit_periods: tuple[CnFiscalPeriod, ...] = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in seen)
return CnDownloadPeriodPolicy(
    effective_periods=explicit_periods,
    discovery_periods=explicit_periods,
    missing_eligible_periods=explicit_periods,
)
```

显式 forms 令三集合相等，保持原有"可请求、无候选时报告 missing"行为。测试 `test_cn_explicit_q2_q4_remains_effective_discovery_and_missing_policy` 验证。

#### 5. Missing/summary/manifest/meta 投影同源 ✅

**证据**：
- `cn_download_workflow.py:367`：`filters.forms` 使用 `period_policy.effective_periods`
- `cn_download_workflow.py:568-586`：`_resolve_missing_periods` 只消费 `missing_eligible_periods` 与 candidate identity `fiscal_period`
- `cn_download_rebuild.py:99`：`form_values` 使用 `period_policy.effective_periods`
- `cn_download_rebuild.py:121`：`missing_periods` 始终为空 list

所有投影都从 `CnDownloadPeriodPolicy` 同源派生，无 downstream 反推或 fallback。

#### 6. Rebuild 无网络/转换/processed 修改 ✅

**证据**：`cn_download_rebuild.py:36-124`

rebuild 实现：
- 基于本地 source meta 和文件条目重建
- 不访问 provider（无 `discovery.resolve_company` 或 `discovery.list_report_candidates` 调用）
- 不下载 PDF（无 `discovery.download_report_pdf` 调用）
- 不运行 Docling（无 `converter.run_docling_conversion` 调用）
- 不覆盖 PDF/Docling blob（只读取 existing files）
- 不触发 processed/reprocess（无 `processed_repository` 写入）

测试 `test_cn_hk_bare_rebuild_is_local_only_and_always_has_empty_missing` 验证 provider/HTTP/converter 零调用。

#### 7. Filters.forms 与 filters.start_dates 键一致性 ✅

**证据**：`cn_download_workflow.py:366-370`

```python
filters={
    "forms": list(period_policy.effective_periods),
    "start_dates": {period: window.start_date for period in period_policy.discovery_periods},
    ...
}
```

这是有意的设计：
- `forms` 表示向用户承诺并投影到 effective filters 的财期（effective_periods）
- `start_dates` 表示 discovery 范围的窗口（discovery_periods）

两者语义不同但都从同一 policy owner 派生，是清晰一致的 public contract。

#### 8. cn_report_selection.py 格式 churn 可接受 ✅

**证据**：diff 只有两处语义变更（`query.target_periods` → `query.discovery_periods`），其余是 Ruff 格式化要求的非语义换行。implementation artifact §8 已记录此偏差。

#### 9. 测试 owner-level 且未由 fake 固化错误语义 ✅

**证据**：
- `test_download_period_policy_owns_market_defaults_and_explicit_forms`：断言 policy owner 的三集合
- `test_download_period_policy_rejects_noncanonical_direct_construction`：断言 policy owner 拒绝非法构造
- `test_cn_bare_download_consumes_policy_for_query_filters_and_missing`：断言 workflow 从 policy owner 投影
- `test_hk_bare_download_discovers_six_periods_but_only_fy_h1_are_missing_eligible`：断言 HK bare 的三路分离
- `test_cn_explicit_q2_q4_remains_effective_discovery_and_missing_policy`：断言显式 forms 行为不变
- `test_hk_bare_rebuild_includes_local_optional_quarter_without_provider_io`：断言 rebuild local-only
- `test_cn_hk_bare_rebuild_is_local_only_and_always_has_empty_missing`：断言 rebuild empty missing

所有测试都断言 owner-level contract 行为，fake 只用于隔离 I/O 边界，不固化错误语义。

#### 10. 过程 perl 偏差 ✅

**证据**：implementation artifact §8 已记录实现早期使用 `perl -pi` 的合规性偏差，但最终 diff 已通过 `apply_patch` 修正，无 allowlist 外写入。old-contract guard 无匹配。

## Open Questions

无。

## Residual Risk

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| HKEX 仍使用季度 `13600`，尚未扩展为全 results group | covered by later approved slice | WU-CLI-DOWNLOAD-02 Slice 3 |
| candidate multi-period identity、coverage、category-first classification、source/public projection 尚未实现 | covered by later approved slice | WU-CLI-DOWNLOAD-02 Slice 3 |
| 真实 CN/HK provider 与 production CLI post-fix evidence 未运行 | covered by later approved slice | Slice 3 完成并通过后，按 accepted plan 进入 aggregate review 与 evidence gate |

无 unclassified residual risk，无 blocking open question。

## Conclusion

**PASS**。Slice 2 实现完全符合 accepted plan 的所有要求，semantic owner 唯一、三路 data flow 正确、rebuild local-only、测试 owner-level。无 blocking finding，无需要修复的问题。residual risk 均属于后续 Slice 3 范围。
