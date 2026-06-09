# WU-TOOLS-01-F02 Slice 2 Code Review — DeepReview

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate：code review (Slice 2)
- 日期：2026-06-09
- Artifact path：`docs/reviews/wu-tools-01-f02-slice2-code-review-ds.md`
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Implementation artifact：`docs/reviews/wu-tools-01-f02-slice2-implementation-codex.md`
- Reviewed files：`utils/diagnose_web_access.py`
- Controller note：Controller 复验时误用 example.com 跑过 raw requests；不作为 implementation validation。正式验收以无网络本地阻断 CLI 和静态验证为准。

## Verdict：pass-with-findings

Blocking：否。Slice 2 可继续推进到 Slice 3，但 classifier findings 必须在 Slice 3 的 deterministic tests 前修复或以 Controller 裁决接受当前实现。

## Findings

### Finding 1 (medium) — `_classify_diagnostic_bucket` 决策树与 plan 不一致

**证据**：`utils/diagnose_web_access.py:1738-1789`

对比 plan Section 5 "comparison bucket 保持粗粒度" 的 13 步决策树与代码实现，存在以下偏差：

**1a. `fetch_outperforms_requests` 条件过窄**

Plan step 7："fetch 成功、requests 失败、Playwright 未采样或失败，返回 `fetch_outperforms_requests`"

代码 line 1781-1782：
```python
if playwright_sampled and playwright_ok and fetch_ok and not requests_ok:
    return "fetch_outperforms_requests"
```
要求 `playwright_ok=True`，但 plan 要求 Playwright 可以是"未采样或失败"。以下合法组合被误分类：
- playwright skipped + fetch ok + requests failed → 落入 `partial_sample`（line 1787），应为 `fetch_outperforms_requests`
- playwright sampled+failed + fetch ok + requests failed → 落入 `mixed`（line 1789），应为 `fetch_outperforms_requests`

**1b. `fetch_only_success` 未区分 Playwright 未采样 vs 采样失败**

代码 line 1775-1776：
```python
if fetch_ok and not requests_ok and not playwright_ok:
    return "fetch_only_success"
```
未检查 `playwright_sampled=True`。当 Playwright 被跳过时（`sampled=false`），`playwright_ok` 也为 `False`（`_bool_from_mapping` 对缺失 key 返回 `False`），导致 playwright skipped + fetch ok + requests failed → 错误分入 `fetch_only_success`。

Plan step 7 明确 `fetch_only_success` 需要 "requests / Playwright 均采样失败"（both sampled and failed），而非 "Playwright 未采样"。

**1c. 缺少 `requests_only_sampled` bucket**

Plan step 8："若 requests 是唯一被采样成功路径且其他路径未采样，返回 `requests_only_sampled`"。代码中无此 bucket。requests sampled+ok + fetch not sampled + playwright not sampled → 落入 `partial_sample`。

**1d. `no_path_sampled` 不在 plan 定义 bucket 列表中**

Plan 定义的 13 个 bucket（lines 265-277）不含 `no_path_sampled`。Plan step 13 规定未能归类的组合返回 `mixed`。代码 line 1767-1768 返回 `no_path_sampled`。

**1e. 缺少 `all_success` 例外处理**

Plan step 5："若 Playwright 采样且 challenge signals 为真，优先返回 `playwright_challenge_detected`，除非所有路径均完全成功且 challenge 只作为低置信提示"。代码 line 1769-1770 无条件返回 `playwright_challenge_detected`，未实现该例外。

**裁决建议**：accepted。应在 Slice 3 前修复分类器使其与 plan 决策树一致，或由 Controller 裁决接受当前实现作为等效替代。

---

### Finding 2 (low) — `--playwright-channel` 空字符串传递

**证据**：`utils/diagnose_web_access.py:2075-2076`

`_build_batch_child_command` 总是传递 `--playwright-channel` 和 `options.playwright_channel`。当 `playwright_channel` 为空字符串时，子进程命令行包含 `--playwright-channel ""`。`_parse_options` 会 strip 为空字符串，`_provider_config` 会将其映射为 `None`。行为正确但传递空字符串作为命令行参数不够干净。

**裁决建议**：deferred-with-owner（Slice 3 可选修复）。不影响功能正确性。

---

### Finding 3 (low) — `fetch_web_page_profile` 失败时缺少 `next_action`/`http_status`/`diagnostics` 字段

**证据**：`utils/diagnose_web_access.py:1276-1286`

Plan line 182-183 定义 `fetch_web_page_profile` 失败字段包含 `next_action`、`http_status`、`diagnostics`。代码只输出 `error_code`、`error`、`message`、`hint`。

经查 `ToolResultFailure` 契约（`dayu/contracts/tool_result.py:78-92`），其字段为 `ok`、`error`、`message`、`hint`、`meta`，无 `next_action`/`http_status`/`diagnostics`。plan 字段列表超出了 current contract 实际提供的字段。

**裁决建议**：rejected-with-reason。代码正确反映了 current contract 能力。Plan 的字段列表为 aspirational，不在 current contract 中。若未来 ToolResultFailure 扩展了这些字段，需单独 work unit 同步更新 diagnostic adapter。

---

### Finding 4 (info) — `ToolsDiscoveryProviderSpec` 从 `dayu.runtime.tools_discovery` 导入

**证据**：`utils/diagnose_web_access.py:40-43`

代码从 `dayu.runtime.tools_discovery` 导入 `PythonImportPathProvider` 和 `ToolsDiscoveryProviderSpec`。Plan line 215-216 禁止使用 `dayu.runtime.tools_discovery.discover_tools(...)` 聚合入口，但未禁止导入这两个类型。

代码使用 `discover_tools` 来自 `dayu.tools.web.provider`（line 44），符合 plan 要求。`PythonImportPathProvider` 和 `ToolsDiscoveryProviderSpec` 是构造 provider spec 所必需的类型，且 `dayu.runtime` 是层中立运行时基础设施，`utils/` 从 `dayu.runtime` 导入类型符合架构约束。

**裁决建议**：accepted。无违规。

---

## 合规性检查

### Slice 2 Allowed Files

| 检查项 | 状态 |
|---|---|
| 仅修改 `utils/diagnose_web_access.py` | PASS |
| 未改 shell wrappers | PASS |
| 未改 tests | PASS |
| 未改 README | PASS |
| 未改 production Web tools | PASS |
| 未改 Host/Engine/ToolRuntime | PASS |

### Current Fetch Adapter

| 检查项 | 状态 |
|---|---|
| 通过 `dayu.tools.web.provider.discover_tools` 发现工具 | PASS |
| 使用 current `ToolDefinition.callable` | PASS |
| 使用 `ToolCallRequest` | PASS |
| 使用 `BatchToolExecutionContext` | PASS |
| 未导入 `dayu.engine.tool_registry` | PASS |
| 未导入 `dayu.engine.truncation_manager` | PASS |
| 未导入 `dayu.engine.tools.fetch_more` | PASS |
| 未导入 `dayu.web` | PASS |
| 未导入 OLD 路径 | PASS |

### CLI Flags

| Plan 要求 flag | 代码实现 |
|---|---|
| `--playwright-channel` | line 718 ✓ |
| `--headed` | line 719 ✓ |
| `--manual-wait-seconds` | line 720 ✓ |
| `--storage-state-dir` | line 724 ✓ |
| `--request-timeout` | line 715 ✓ |
| `--fetch-truncate-chars` | line 728-733 ✓ |
| `--allow-private-network-url` | line 734 ✓ |
| `--skip-playwright` | line 725 ✓ |
| `--url` / `--url-file` | line 710-711 ✓ |

所有 plan 要求的 CLI flags 均已实现。

### Raw Requests Profile

| 检查项 | 状态 |
|---|---|
| `raw_requests_header_source="diagnostic_local"` | line 1064 ✓ |
| 业务可读说明 raw requests 是对照路径非 production fetch | line 1065-1067 ✓ |
| 敏感 header 脱敏 | `_redact_headers` line 965-987 ✓ |
| 未伪装 production fetch | PASS |

### Playwright Optional Boundary

| 检查项 | 状态 |
|---|---|
| Playwright import 仅在 `_build_playwright_profile` 内部 | line 1535 ✓ |
| `ImportError` 时返回 skip-safe profile | line 1536-1547 ✓ |
| 使用 private Protocol 收窄动态类型 | `_PlaywrightContextManagerProtocol` 等 ✓ |
| 无 `hasattr` / `getattr` 滥用 | PASS (0 occurrences) |
| `cast` 使用在窄 boundary 内 | line 1563 ✓ |

### Batch Mode / Child Process Error

| 检查项 | 状态 |
|---|---|
| `corpus.normalized.jsonl` 先于 per-URL children 写出 | line 2398 ✓ |
| `results.jsonl` 输出 | line 2435 ✓ |
| `summary.json` 输出 | line 2436-2437 ✓ |
| `summary.md` 输出 | line 2438 ✓ |
| `child_process_error` 单独统计不混入普通 bucket | `_classify_diagnostic_bucket` line 1765-1766 + `_build_batch_summary` line 2284 ✓ |
| `child_process_error` row 保留 `return_code`/`stderr_prefix`/`stdout_prefix` | `_child_error_payload` line 2204-2233 ✓ |

### LLM-Facing Diagnostics

| 检查项 | 状态 |
|---|---|
| 错误说明/hint 业务可读（中文） | PASS |
| 不泄漏敏感 header 内容 | `_redact_headers` ✓ |
| storage state 只记录路径不内联内容 | line 1618 note + 不内联 ✓ |
| 不用内部治理 id 代替必要信息 | PASS |
| bucket 只描述访问路径对比 | line 1631-1632 challenge 标记为 signals 不混淆为业务事实 ✓ |

### AGENTS.md 合规

| 检查项 | 状态 |
|---|---|
| 中文模块 docstring | line 2-8 ✓ |
| 中文类 docstring | `DiagnosticUrlEntry`, `CliOptions`, `_DiagnosticCancellationToken` ✓ |
| 中文函数 docstring（含 Args/Returns/Raises） | 所有函数 ✓ |
| 禁止 `Any` | PASS (0 occurrences) |
| 禁止 `object` | PASS (0 occurrences as type) |
| 禁止无类型签名 | PASS |
| `JsonObject` / `TypeAlias` 严格 | PASS |

## Validation Evidence

| 命令 | 结果 |
|---|---|
| `python -m py_compile utils/diagnose_web_access.py` | PASS |
| `python -m pyright utils/diagnose_web_access.py` | PASS (0 errors, 0 warnings) |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | PASS |
| `git diff --check` | PASS (no whitespace errors) |
| Forbidden imports grep | PASS (0 matches) |
| `hasattr`/`getattr` grep | PASS (0 matches) |
| `Any`/`object` type grep | PASS (0 type usages) |

注：未执行 live diagnostics，符合"不得要求 live diagnostics"约束。

## Residual Risks

1. **Classifier 与 plan 决策树不一致**（Finding 1）：当前 classifier 在特定边界组合下产出与 plan 不同的 bucket。若 F03 消费 `comparison_bucket` 做 smoke gate 决策，偏差可能导致误判。建议 Slice 3 前修复或 Controller 裁决接受。
2. **Playwright browser 可用性**：代码正确处理了 `ImportError` 和 browser 异常（skip-safe），但真实的 browser channel 兼容性（chromium/chrome/msedge）未在 CI 中验证。非 blocking，属于 live-environment 依赖。
3. **`requests` Session finally-close 竞态**：`_build_requests_profile` 在 `finally` 块中 `session.close()`。若 `session.send()` 抛出非 `RequestException` 异常（理论上可能但罕见），`session.close()` 仍会执行，但 `response` 变量可能未绑定。当前代码结构安全（`result` 在 try 块内分支），但值得在 Slice 3 用 mock 覆盖。
4. **`_prefix_text` 的 `max(max_chars, 0)` 防御**：line 1004，当 `max_chars=0` 时返回空字符串。当前所有调用点 `max_chars > 0`，但防御性写法不引入 bug。
5. **diagnostic JSON schema 稳定性**：代码实现了 plan 定义的 F03 最小稳定子集（`schema_version`, `url`, `comparison_bucket`, per-path `sampled`/`ok`/`elapsed_seconds`/`status`/`error`），但 `requests_profile.result` 内的 `ok` 字段位置与其他 profile 不一致（requests 的 `ok` 在 `result` 子对象内，fetch/playwright 的 `ok` 在顶层）。F03 消费时需注意此差异。

## Recommendation for Next Gate

Slice 2 可推进到 Slice 3（Deterministic Tests），但建议：

1. **先修复 Finding 1（classifier 决策树）**，或由 Controller 在 review artifact 中明确裁决接受当前分类器实现。
2. Slice 3 的 test matrix 应专门覆盖 classifier 在以下 scenario 的正确性：
   - playwright skipped + fetch ok + requests failed → 期望 `fetch_outperforms_requests`
   - playwright sampled+failed + fetch ok + requests failed → 期望 `fetch_outperforms_requests`
   - playwright skipped + fetch ok + requests ok → 期望 `requests_and_fetch_success_playwright_failed` 或 `partial_sample`（需 plan 明确）
   - requests ok + fetch not sampled + playwright not sampled → 期望 `requests_only_sampled`
   - all three ok + challenge_detected → 期望 `all_success`（不因 challenge 降级）
3. Slice 3 AST/import guard tests 应确认 forbidden imports 持续缺失。

## Finding Summary

| # | Severity | Category | Status |
|---|---|---|---|
| 1 | medium | Classifier diverges from plan decision tree | Accepted |
| 2 | low | Empty playwright-channel in subprocess CLI | Deferred |
| 3 | low | Missing aspirational fields in fetch failure profile | Rejected |
| 4 | info | ToolsDiscoveryProviderSpec import from runtime | Accepted |

- **Total findings**：4
- **Accepted**：2 (F1, F4)
- **Rejected**：1 (F3)
- **Deferred**：1 (F2)
- **Blocking**：0
