# WU-TOOLS-01-F02 Slice 2 Re-Review - MiMo

## Artifact Path

- `docs/reviews/wu-tools-01-f02-slice2-rereview-mimo.md`

## Review Metadata

- Reviewer: AgentMiMo
- Date: 2026-06-09
- Gate: re-review (post-fix)
- Slice: Slice 2 Current-Contract Diagnostic Script
- Reviewed file: `utils/diagnose_web_access.py`
- Fix artifact: `docs/reviews/wu-tools-01-f02-slice2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f02-slice2-code-review-controller-adjudication.md`
- Original review: `docs/reviews/wu-tools-01-f02-slice2-code-review-mimo.md`

## Verdict

**pass**

## Accepted Finding Status

| Finding | Controller Decision | Status | Evidence |
|---|---|---|---|
| DS F1 / MiMo F-02: `_classify_diagnostic_bucket` diverges from plan decision tree | accepted — fix required | **已修复** | 见下方 Decision Tree 逐条比对 |
| MiMo F-03: `requests_only_success` narrow trigger | accepted — no direct fix beyond classifier fix | **已修复（间接）** | 修复后 `fetch_sampled and fetch_ok` 条件使 bucket 语义更精确 |

### Decision Tree 逐条比对

Plan constraint 5 steps 5-13 vs 实现 `_classify_diagnostic_bucket`（第 1738-1797 行）：

| Plan Step | Bucket | 实现行 | 条件匹配 | 结论 |
|---|---|---|---|---|
| 1 | `child_process_error` | 1769-1770 | `status == "child_process_error"` → 首先返回 | PASS |
| 5 | `playwright_challenge_detected`（all_success 例外优先） | 1771-1774 | `all_success` 先于 `challenge_detected` 检查 | PASS |
| 6 | `all_success` | 1771-1772 | 三路径 sampled 且均 ok | PASS |
| 7a | `fetch_outperforms_requests` | 1777-1778 | `fetch_ok and requests_failed and (not playwright_sampled or playwright_failed)` | PASS |
| 7b | `fetch_only_success` | 1775-1776 | `fetch_ok and requests_failed and playwright_failed`（均 sampled 且 failed） | PASS |
| 8a | `requests_only_sampled` | 1779-1780 | `requests_ok and not fetch_sampled and not playwright_sampled` | PASS（**新增**） |
| 8b | `requests_only_success` | 1781-1782 | `requests_ok and fetch_failed and (not playwright_sampled or playwright_failed)` | PASS |
| 9 | `browser_only_success` | 1783-1784 | `playwright_ok and fetch_failed and requests_failed` | PASS |
| 10 | `requests_and_fetch_success_playwright_failed` | 1785-1786 | `requests_ok and fetch_ok and playwright_failed` | PASS |
| 11 | `fetch_only_failure` | 1787-1788 | `fetch_failed and (requests_ok or playwright_ok)` | PASS |
| 12 | `all_failed` | 1789-1794 | 所有 sampled path 均 failed，至少一条 sampled | PASS |
| 13 | `partial_sample` / `mixed` | 1795-1797 | `sampled_path_count > 0` → partial_sample；否则 → mixed | PASS |

**关键验证点：**

- `requests_only_sampled`（plan step 8a）：已实现。当 requests 是唯一被采样且成功的路径、fetch 和 Playwright 均未采样时返回该 bucket。
- `mixed` fallback 替代 `no_path_sampled`：已实现。无 `no_path_sampled` 分支；零采样路径返回 `mixed`（第 1797 行）。
- `all_success` 先于 `playwright_challenge_detected`：已实现（第 1771 行 vs 第 1773 行）。
- `fetch_outperforms_requests` 覆盖 Playwright skipped 或 failed：已实现（第 1777 行 `not playwright_sampled or playwright_failed`）。
- `fetch_only_success` 仅当 requests 和 Playwright 均 sampled 且 failed：已实现（第 1775 行 `requests_failed and playwright_failed`，两者均要求 `sampled and not ok`）。
- `child_process_error` 保留：已实现（第 1769 行，首检）。

## Rejected/Deferred Findings — 误修检查

| Finding | Controller Decision | 误修? | 证据 |
|---|---|---|---|
| DS F2: `--playwright-channel ""` child-process propagation | rejected-with-reason | 否 | 第 2084 行 `command` 仍包含 `options.playwright_channel`；第 1126-1128 行 `playwright_channel` 为空时设 `None` 逻辑不变 |
| DS F3 / MiMo F-01: `next_action`/`http_status`/`diagnostics` 缺失 | rejected-with-reason | 否 | 第 1276-1286 行 `_build_tool_fetch_profile` 仍只消费 `ToolResultFailure` 的 `error`/`message`/`hint`，未合成额外字段 |
| DS F4: `ToolsDiscoveryProviderSpec` import | accepted — no fix | 否 | 第 40-43 行 import 不变 |

## New Findings

无新 findings。fix 范围严格限于 `_classify_diagnostic_bucket` 函数和 fix artifact 文档，未引入新逻辑、新依赖或新边界。

## Validation Evidence

| 验证项 | 结果 |
|---|---|
| `py_compile utils/diagnose_web_access.py` | PASS |
| `pyright utils/diagnose_web_access.py` | 0 errors, 0 warnings |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | N/A（Slice 2 不修改 shell wrappers） |
| `git diff --check` | PASS（无 whitespace error） |
| `Any` / `object` / 无类型签名检查 | PASS |
| `getattr` / `hasattr` 检查 | PASS |
| OLD imports 检查 | PASS（无 `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools.fetch_more`、`dayu.web`） |
| `no_path_sampled` 残留检查 | PASS（grep 确认无该字符串） |

## Residual Risks

1. **Classifier 行为未被 deterministic test 锁定**: pytest 覆盖有意推迟到 Slice 3。当前 classifier 逻辑正确，但回归保护缺失直到 Slice 3 合入。
2. **Live site / Playwright 环境依赖**: 此 gate 未运行真实网络请求或浏览器。`detect_bot_challenge`、storage state 读写、网络事件收集的端到端行为依赖 live 环境。
3. **`ToolResultFailure` contract 上限**: `next_action`/`http_status`/`diagnostics` 仍不可通过 current contract 获取。F03 若需独立消费需增强 contract。

## Recommendation

accept。所有 accepted findings 已修复，rejected/deferred findings 未被误修，无新 blocking issues。建议 Slice 3 优先覆盖 `_classify_diagnostic_bucket` 完整 bucket matrix 的 deterministic tests。
