# WU-TOOLS-01-F02 Slice 3 Re-Review - AgentMiMo

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Current gate: Slice 3 re-review after fix
- Fix artifact: `docs/reviews/wu-tools-01-f02-slice3-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f02-slice3-code-review-controller-adjudication.md`
- Review date: 2026-06-09

## Verdict

**pass-with-findings**

两个 accepted findings 均已正确修复。Rejected findings 未被修改。发现 fix 范围包含 Controller 裁决未授权的额外增强代码，但位于 `utils/` 且不影响 Host / Engine / 生产工具行为，属 non-blocking。

## Accepted Finding Status

| Finding | 状态 | 验证 |
|---|---|---|
| MiMo F1: `utils/diagnose_web_access.py` 未使用的 `socket` import | ✅ 已修复 | `git diff` 确认 `import socket` 已删除；`rg "socket\."` 无残留引用。 |
| MiMo F3 / DS F1: comparison bucket matrix 覆盖不足 | ✅ 已修复 | `test_comparison_bucket_matrix` 新增 7 个显式 bucket case：`playwright_challenge_detected`(L154)、`requests_only_success`(L192)、`browser_only_success`(L202)、`requests_and_fetch_success_playwright_failed`(L212)、`fetch_only_failure`(L224)、`all_failed`(L237)、`partial_sample`(L250)。全部 deterministic、无网络依赖。 |

## Rejected Finding Mis-Fix Check

| Finding | 状态 | 验证 |
|---|---|---|
| MiMo F2: AST/import guard test 缺失 | ✅ 未修改 | `test_diagnose_web_access_does_not_import_old_web_or_ui_paths()` 仍存在于 L521。 |
| DS F2: `requests_only_success` 分类器条件 | ✅ 未修改 | L1833 条件 `requests_sampled and requests_ok and fetch_failed and (not playwright_sampled or playwright_failed)` 保持原实现语义，`fetch_failed = fetch_sampled and not fetch_ok`。未采样 fetch 不被错误视为失败。 |

## Scope Excess Finding

**Non-blocking。** Codex fix 在执行两个 accepted findings 的同时，额外引入了以下未被 Controller 裁决授权的代码：

| 新增内容 | 位置 | 性质 |
|---|---|---|
| `_NEXT_ACTION_HINT_PATTERN` 常量 | L73 | `re.Pattern` 常量 |
| `_next_action_from_hint()` 函数 | L1321-L1337 | hint `[action]` 前缀提取 |
| `_tool_failed_outcome_diagnostics()` 函数 | L1340-L1367 | failed outcome 诊断来源说明 |
| `_build_tool_fetch_profile` 增强字段 | L1277-L1291 | `next_action`、`http_status`、`diagnostics` |

这些增强均位于 `utils/` 脚本，不触及 `dayu/` Host / Engine / ToolRuntime / 生产 Web tool 路径，不影响 CI 默认 workflow。功能上改善了 failed outcome 的诊断可读性。但严格来说超出了 Controller scope guard 的授权边界。

**建议**：Controller 可选择 (a) 接受这些增强作为 fix 的附带改进，或 (b) 要求在后续 slice/plan 中正式纳入。本次 re-review 不因此阻塞 gate。

## Validation Gaps and Residual Risks

1. **Controller 报告的验证已通过**：23 tests passed、pyright 0 errors、shell syntax passed、git diff --check passed、forbidden import/type scan 无命中。
2. **Fix 新增的 `_next_action_from_hint` 和 `_tool_failed_outcome_diagnostics`**：已有对应 deterministic 测试覆盖（`test_current_fetch_adapter_failed_outcome_generates_business_readable_profile` L368-L411），验证了 `next_action`、`diagnostics` 字段的投影正确性。
3. **comparison bucket matrix 仍为 synthetic payload**：不证明真实网络、真实浏览器安装、真实 storage state 或反爬挑战场景。此为 Slice 3 设计边界，非 fix 引入。
4. **`_tool_failed_outcome_diagnostics` 的 `available_fields` 列表是手动维护的枚举**：若 `ToolFailedOutcome` 投影字段变更，该列表需同步更新。当前不构成风险，后续演进需注意。
