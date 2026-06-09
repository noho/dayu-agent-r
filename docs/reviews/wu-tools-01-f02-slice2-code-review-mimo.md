# WU-TOOLS-01-F02 Slice 2 Code Review - MiMo

## Artifact Path

- `docs/reviews/wu-tools-01-f02-slice2-code-review-mimo.md`

## Review Metadata

- Reviewer: AgentMiMo
- Date: 2026-06-09
- Gate: code review
- Slice: Slice 2 Current-Contract Diagnostic Script
- Reviewed file: `utils/diagnose_web_access.py`
- Implementation artifact: `docs/reviews/wu-tools-01-f02-slice2-implementation-codex.md`
- Accepted plan: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`

## Verdict

**pass-with-findings**

## Findings

### F-01 [info] fetch failure profile 缺少 next_action / http_status / diagnostics 字段

**位置**: `_build_tool_fetch_profile`，第 1276-1286 行

**描述**: plan 的 `fetch_web_page_profile` 要求失败时包含 `error_code`、`message`、`hint`、`next_action`、`http_status`、`diagnostics`。实现只输出 `error_code`、`error`、`message`、`hint`。

**根因**: `ToolFailedOutcome.result`（`ToolResultFailure`）只暴露 `error`、`message`、`hint`、`meta`。`next_action`、`http_status`、`internal_diagnostics` 是 `ToolBusinessError` 的扩展属性，在 `definition_adapter._failed_outcome` 投影时被丢弃，无法通过 current contract 获取。

**严重性**: info — 这是 current contract 约束，不是实现 defect。实现正确消费了 `ToolResultFailure` 的所有字段。`next_action` 实际编码在 `hint` 字符串的 `[action]` 前缀中，可解析但脆弱。

**建议**: 如 F03 需要独立 `next_action` 字段，应作为后续 work unit 增强 `ToolResultFailure.meta` 或增加 web-specific failure projection，不在 F02 scope 内。

---

### F-02 [info] requests_only_sampled bucket 未被 classifier 生成

**位置**: `_classify_diagnostic_bucket`，第 1738-1789 行

**描述**: plan 定义了 `requests_only_sampled` bucket（"若 requests 是唯一被采样成功路径且其他路径未采样"）。classifier 不包含该 bucket 的条件分支。当只有 requests 被采样且成功时，会落入 `requests_only_success`。

**严重性**: info — batch summary 和 per-URL JSON 仍正确记录 `requests_sampled=true`、`playwright_sampled=false`、`fetch_sampled=false`，信息无损。bucket 粒度略粗于 plan 声明，但不影响 F03 消费。

**建议**: 若 F03 需要区分"只采样了 requests 且成功"与"三条路径均采样但只有 requests 成功"，可在 F03 plan 中要求增加 `requests_only_sampled` 条件。当前 bucket 分类仍 deterministic 且合理。

---

### F-03 [info] requests_only_success bucket 在典型诊断流程中不会触发

**位置**: `_classify_diagnostic_bucket`，第 1777 行

**描述**: 默认流程三条路径均被采样（除非显式 `--skip-playwright` / `--skip-tool-fetch`）。`requests_only_success` 条件要求 `not fetch_ok and not playwright_ok`，即 fetch 和 Playwright 均采样且失败。该场景较窄，但仍可能在 Playwright 缺失且 fetch 异常时触发。

**严重性**: info — bucket 存在且条件正确，只是触发频率低。不影响正确性。

## Validation Evidence

| 验证项 | 结果 |
|---|---|
| `py_compile utils/diagnose_web_access.py` | PASS |
| `pyright utils/diagnose_web_access.py` | 0 errors, 0 warnings |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | N/A（Slice 2 不修改 shell wrappers） |
| `git diff --check` | PASS（无 whitespace error） |
| OLD imports 检查 | PASS（无 `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools.fetch_more`、`dayu.web`、OLD `/Users/leo/workspace/dayu-agent/`） |
| `Any` / `object` / 无类型签名检查 | PASS |
| `getattr` / `hasattr` 检查 | PASS |

## Scope Compliance

| 检查项 | 结果 | 说明 |
|---|---|---|
| Slice 2 allowed files only | PASS | 只修改 `utils/diagnose_web_access.py`；git diff 确认 |
| current fetch adapter | PASS | 通过 `discover_tools(spec)` → `ToolDefinition.callable` → `ToolCallRequest` + `BatchToolExecutionContext` 调用 |
| 无 OLD ToolRegistry / truncation / fetch_more / dayu.web | PASS | import grep 确认 |
| CLI flags 完整 | PASS | 覆盖 plan 所有 flags：`--playwright-channel`、`--headed`、`--manual-wait-seconds`、`--storage-state-dir` 等 |
| raw requests 标注 diagnostic_local | PASS | `raw_requests_header_source="diagnostic_local"` + `header_source_note` |
| Playwright optional boundary skip-safe | PASS | `ImportError` 捕获返回 `ok=false` profile；Protocol 类型收窄，无 `getattr`/`hasattr` |
| batch mode / child_process_error | PASS | 子进程 crash → `status="child_process_error"` + `comparison_bucket="child_process_error"`；不混入 `all_failed` / `mixed` |
| summary / results / corpus 输出 | PASS | `corpus.normalized.jsonl` → per-url children → `results.jsonl` → `summary.json` → `summary.md` |
| LLM-facing diagnostics 业务可读 | PASS | header 脱敏；storage state 只记录路径；bucket 描述访问路径对比而非业务事实 |
| 中文 docstring | PASS | 模块、类、函数均有中文 docstring |
| 严格类型 | PASS | 无 `Any`、`object`、无类型签名 |

## Residual Risks

1. **`next_action` / `http_status` 不可通过 current contract 获取**: `ToolResultFailure` 不暴露这些字段。F03 若需独立消费，需增强 contract。
2. **Playwright Protocol 假设**: 协议基于 Playwright sync API 的当前 shape；Playwright 大版本变更可能破坏协议兼容。风险低，因 Protocol 是 structural typing。
3. **live diagnostics 未验证**: 实现未运行真实网络请求或浏览器。`detect_bot_challenge` 调用、storage state 读写、网络事件收集的端到端行为依赖 live 环境。
4. **`requests_only_sampled` bucket 缺失**: batch summary 不区分"只采样 requests 且成功"与"三条路径均采样但只有 requests 成功"。信息无损，但粒度略粗。

## Recommendation for Next Gate

accept。3 个 info findings 均为 current contract 约束或 plan 细节偏差，不阻塞 Slice 2 进入下一阶段。建议：

- Slice 3 deterministic tests 应覆盖 `_classify_diagnostic_bucket` 的完整 bucket matrix，包括 `child_process_error`、`no_path_sampled`、`playwright_challenge_detected` 分支。
- 若 F03 需要 `next_action` 作为独立字段，应在 F03 plan 中声明对 `ToolResultFailure` contract 的增强依赖。
- Controller 裁决时注意：`requests_only_sampled` bucket 未被实现，但 batch summary 的 `requests_sampled_count` 统计可补偿。
