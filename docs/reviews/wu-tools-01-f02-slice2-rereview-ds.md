# WU-TOOLS-01-F02 Slice 2 Re-Review — DeepReview

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate：re-review (Slice 2 fix verification)
- 日期：2026-06-09
- Artifact path：`docs/reviews/wu-tools-01-f02-slice2-rereview-ds.md`
- Original review artifact：`docs/reviews/wu-tools-01-f02-slice2-code-review-ds.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f02-slice2-code-review-controller-adjudication.md`
- Fix artifact：`docs/reviews/wu-tools-01-f02-slice2-fix-codex.md`
- Reviewed file：`utils/diagnose_web_access.py`

## Verdict：pass

Blocking：否。所有 accepted finding 均已修复，无 scope creep，无新增 blocking issue。

## Accepted Finding 修复验证

### DS F1 — `_classify_diagnostic_bucket` 决策树修复

| 子项 | 要求 | 修复位置 | 状态 |
|---|---|---|---|
| `requests_only_sampled` | 新增 bucket：requests 是唯一采样成功路径且其他路径未采样 | `diagnose_web_access.py:1779-1780` | 已修复 |
| 移除 `no_path_sampled` | 零采样路径回退到 `mixed`，除非是 batch child crash | `diagnose_web_access.py:1797` 返回 `"mixed"`，`no_path_sampled` 已删除 | 已修复 |
| `child_process_error` 保留 | 子进程 crash 优先分类 | `diagnose_web_access.py:1769-1770`，仍为首个判断 | 已修复 |
| `all_success` 优先于 challenge | 三路径均采样成功时返回 `all_success`，不因 challenge 降级 | `diagnose_web_access.py:1771-1772` 在 challenge 检查 (line 1773) 之前 | 已修复 |
| `fetch_outperforms_requests` 扩展 | Playwright skipped 或采样失败时均适用 | `diagnose_web_access.py:1777-1778`：条件为 `not playwright_sampled or playwright_failed` | 已修复 |
| `fetch_only_success` 收窄 | 仅当 requests 和 Playwright 均采样且失败时触发 | `diagnose_web_access.py:1775-1776`：条件包含 `requests_failed and playwright_failed`（两者均为 `sampled and not ok`） | 已修复 |

**验证方法**：逐条对照 controller adjudication 的 required action 与代码行号，确认语义一致。

**关键决策树顺序验证**：

1. `child_process_error` (line 1769) — 最先判断 ✅
2. `all_success` (line 1771) — 三路径均采样成功，先于 challenge ✅
3. `playwright_challenge_detected` (line 1773) — 仅在三路径不全成功时触发 ✅
4. `fetch_only_success` (line 1775) — playwright_failed（采样且失败），先于 `fetch_outperforms_requests` 以区分"采样失败"和"未采样" ✅
5. `fetch_outperforms_requests` (line 1777) — Playwright 未采样或采样失败 ✅
6. `requests_only_sampled` (line 1779) — fetch 和 Playwright 均未采样 ✅
7. `requests_only_success` (line 1781) — fetch 失败，Playwright 未采样或失败 ✅
8. `browser_only_success` (line 1783) — 仅 Playwright 成功 ✅
9. `requests_and_fetch_success_playwright_failed` (line 1785) — Playwright 采样且失败 ✅
10. `fetch_only_failure` (line 1787) — fetch 失败但其他路径有成功 ✅
11. `all_failed` (line 1789) — 有采样路径但全部失败 ✅
12. `partial_sample` (line 1796) — 有采样路径但未命中以上 bucket ✅
13. `mixed` (line 1797) — 零采样路径（非 child_process_error）回退 ✅

**边界组合抽样验证**：

| 场景 | requests | fetch | playwright | 期望 bucket | 代码行 | 命中 |
|---|---|---|---|---|---|---|
| playwright skipped + fetch ok + requests failed | sampled+failed | sampled+ok | not sampled | `fetch_outperforms_requests` | 1777 | ✅ |
| playwright sampled+failed + fetch ok + requests failed | sampled+failed | sampled+ok | sampled+failed | `fetch_only_success` | 1775 | ✅ |
| playwright skipped + fetch ok + requests ok | sampled+ok | sampled+ok | not sampled | `partial_sample` | 1796 | ✅ (plan 未定义此组合专用 bucket) |
| requests ok + fetch not sampled + playwright not sampled | sampled+ok | not sampled | not sampled | `requests_only_sampled` | 1779 | ✅ |
| all three ok + challenge_detected | sampled+ok | sampled+ok | sampled+ok | `all_success` | 1771 | ✅ (不因 challenge 降级) |
| zero sampled + not child_process_error | not sampled | not sampled | not sampled | `mixed` | 1797 | ✅ |

## Rejected/Deferred Finding 完整性检查

| Finding | Controller 裁决 | 代码状态 | 是否被误修 |
|---|---|---|---|
| DS F2 — `--playwright-channel ""` | rejected-with-reason | `diagnose_web_access.py:2083-2084` 未改 | 否 |
| DS F3 — 缺少 aspirational 字段 | rejected-with-reason | `diagnose_web_access.py:1276-1286` 未改 | 否 |
| DS F4 — `ToolsDiscoveryProviderSpec` import | accepted, no fix required | `diagnose_web_access.py:40-43` 未改 | 否 |

## Scope Creep 检查

| 检查项 | 状态 |
|---|---|
| 仅修改 `_classify_diagnostic_bucket` 函数 | PASS — 周围代码与原始 review 描述一致 |
| 未改 tests | PASS |
| 未改 README | PASS |
| 未改 shell wrappers | PASS |
| 未改 production Web tools | PASS |
| 未改 Host/Engine/ToolRuntime | PASS |
| 未改 plan/controller artifacts | PASS |
| 无新增 bucket（不在 plan 定义中） | PASS |
| 无新增函数/类/导入 | PASS |

## Static Validation

| 命令 | 结果 |
|---|---|
| `python -m py_compile utils/diagnose_web_access.py` | PASS |
| `python -m pyright utils/diagnose_web_access.py` | PASS (0 errors, 0 warnings) |
| `git diff --check` | PASS |

## New Findings

无。分类器逻辑与 controller adjudication 要求的决策树一致，未发现新的逻辑漏洞、边界遗漏或 regression。

## Residual Risks

1. **确定性测试覆盖**：分类器行为已在代码中修复，但 Slice 3 的 pytest 确定性覆盖尚未编写。当前 re-review 仅做静态逻辑验证，未运行测试矩阵。风险：若 Slice 3 测试矩阵设计时对 plan 决策树的理解与 fix 实现存在偏差，可能在测试阶段暴露。**缓解**：此风险为 Slice 3 的职责范围，不在 Slice 2 re-review gate 内。

2. **`partial_sample` 覆盖范围**：`requests ok + fetch ok + playwright not sampled` 组合落入 `partial_sample`，plan 未为其定义专用 bucket。当前行为正确（两个路径采样成功、一个路径跳过，属于部分采样），但若 F03 对该组合有特定消费需求，需在 Slice 3 明确。

## Recommendation

Slice 2 fix 已验证通过。可推进到 Slice 3（Deterministic Tests）。

## Finding Summary

| # | Source | Severity | Category | Status |
|---|---|---|---|---|
| 1 | DS F1 | medium | Classifier diverges from plan decision tree | 已修复 |

- **Accepted findings 总数**：1 (controller 要求修复的)
- **已修复**：1
- **未修复**：0
- **部分修复**：0
- **证据失效**：0
- **New findings**：0
- **Blocking**：0
