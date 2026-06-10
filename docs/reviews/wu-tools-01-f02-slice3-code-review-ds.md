# WU-TOOLS-01-F02 Slice 3 Code Review — AgentDS

## 元数据

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate: Slice 3 code review
- 日期: 2026-06-09
- 审查人: AgentDS
- artifact path: `docs/reviews/wu-tools-01-f02-slice3-code-review-ds.md`
- 审查范围:
  - `tests/tools/web/test_diagnose_web_access.py`
  - `utils/diagnose_web_access.py` Slice 3 diff
  - `docs/reviews/wu-tools-01-f02-slice3-implementation-codex.md`

## Verdict: pass-with-findings

无阻塞性问题。发现两个低风险 findings，均已标注为 non-blocking。

---

## Findings

### Finding 1 — [LOW] comparison_bucket 测试矩阵未穷尽全部决策树分支

**文件**: `tests/tools/web/test_diagnose_web_access.py:112-186`

**证据**: `test_comparison_bucket_matrix` 覆盖了 6 个 bucket:

| 测试用例 | bucket |
|---|---|
| `requests_only_sampled` | `requests_only_sampled` |
| `mixed_zero_sample` | `mixed` |
| `all_success_before_challenge` | `all_success` |
| `fetch_outperforms_requests_playwright_skipped` | `fetch_outperforms_requests` |
| `fetch_only_success_narrowed_to_sampled_failures` | `fetch_only_success` |
| `child_process_error` | `child_process_error` |

`_classify_diagnostic_bucket` 决策树定义了 13 个分支（含 `child_process_error`），以下 6 个 bucket 未出现在矩阵测试中:

- `playwright_challenge_detected`（计划 step 5，all_success 例外已通过 `all_success_before_challenge` 间接覆盖挑战信号不覆盖完全成功路径的逻辑）
- `browser_only_success`（计划 step 9）
- `requests_and_fetch_success_playwright_failed`（计划 step 10）
- `fetch_only_failure`（计划 step 11）
- `all_failed`（计划 step 12）
- `partial_sample`（计划 step 13，在 `test_cli_batch_mode` 中通过集成路径间接覆盖）

**评估**: 不阻塞通过。计划 Slice 3 exact tests 只要求 "synthetic profile payload 的 comparison bucket matrix"，未要求穷尽。决策树实现是确定性的（条件顺序固定，不依赖 dict 遍历顺序或 message 文本），未覆盖分支不会引入非确定性行为。`playwright_challenge_detected` 遗漏值得注意——虽然 `all_success_before_challenge` 覆盖了 "挑战不覆盖完全成功" 例外，但没有测试 "挑战信号触发 playwright_challenge_detected 且非完全成功" 的路径。

**建议**: 在后续 Slice 或 F03 中补齐剩余 bucket 的覆盖。

### Finding 2 — [LOW] `requests_only_success` 的 `fetch_failed` 条件比计划文本更严格

**文件**: `utils/diagnose_web_access.py:1834`

**计划文本**（step 8）:
> requests 成功、fetch 失败、Playwright 未采样或失败，返回 requests_only_success

**实现**:
```python
if requests_sampled and requests_ok and fetch_failed and (not playwright_sampled or playwright_failed):
    return "requests_only_success"
```
其中 `fetch_failed = fetch_sampled and not fetch_ok`。

**分歧**: 计划写 "fetch 失败"，但实现要求 fetch **被采样且失败**。当用户传入 `--skip-tool-fetch`（fetch 未采样），且 requests 成功、playwright 失败时，fetch_failed=False，该条件不匹配，最终落到 `partial_sample`。

**评估**: 不阻塞通过，且实现语义更精确——"未采样"不应等同于"失败"。此处的 `partial_sample` 落点合理。

**建议**: 若计划意图确实包含 "fetch 未采样" 场景，应在后续调整条件为 `(not fetch_sampled or fetch_failed)`；否则计划文本应修正为 "fetch 采样且失败"。

---

## Accepted-Plan Alignment Assessment

### Slice 3 exact tests 对照

| 计划要求的测试 | 实现 | 状态 |
|---|---|---|
| JSONL/TXT corpus 解析、metadata 保留、去重 | `test_jsonl_and_txt_corpus_parsing_retains_metadata_and_deduplicates` (L40-81) | 符合 |
| 非法 JSONL 错误 | `test_invalid_jsonl_reports_line_number` (L84-91) | 符合 |
| storage-state path 按 host 解析 | `test_storage_state_dir_resolves_existing_host_input_and_default_output` (L94-109) | 符合 |
| synthetic profile payload 的 comparison bucket matrix | `test_comparison_bucket_matrix` (L112-185) | 符合（覆盖 6/13，见 Finding 1） |
| synthetic rows 的 batch summary count | `test_batch_rows_and_summary_counts` (L188-234) | 符合 |
| `ToolDefinition.callable` 返回 `ToolCompletedOutcome` → `ok=true` profile | `test_current_fetch_adapter_completed_outcome_generates_ok_profile` (L237-280) | 符合 |
| `ToolDefinition.callable` 返回 `ToolFailedOutcome` → `ok=false` profile + error/hint/diagnostic 字段 | `test_current_fetch_adapter_failed_outcome_generates_business_readable_profile` (L283-327) | 符合 |
| CLI single mode monkeypatch 后写出 deterministic JSON | `test_cli_single_mode_writes_deterministic_json` (L329-354) | 符合 |
| CLI batch mode monkeypatch child execution | `test_cli_batch_mode_uses_monkeypatched_child_execution` (L357-433) | 符合 |
| AST/import guard | `test_diagnose_web_access_does_not_import_old_web_or_ui_paths` (L436-448) | 符合 |

### `diagnose_web_access.py` Slice 3 修改对照

| 计划要求 | 实现 | 状态 |
|---|---|---|
| 失败的 `fetch_web_page_profile` 包含 `next_action` | L1288: `"next_action": _next_action_from_hint(hint)` | 符合 |
| 失败的 `fetch_web_page_profile` 包含 `http_status` | L1289: `"http_status": None` | 符合 |
| 失败的 `fetch_web_page_profile` 包含 `diagnostics` | L1290: `"diagnostics": _tool_failed_outcome_diagnostics(outcome.result.error)` | 符合 |
| `next_action` 从 hint `[action]` 前缀恢复 | L1322-1338: `_next_action_from_hint` 使用 `^\[([a-z_]+)\]\s*(.*)$` | 符合 |
| `diagnostics` 显式说明 current outcome 可见字段边界 | L1341-1367: `_tool_failed_outcome_diagnostics` 说明 adapter 不暴露 http_status/internal_diagnostics | 符合 |

### `next_action` 提取正确性验证

计划要求从 `ToolBusinessError` 的 hint 中恢复 `next_action`。Web 工具 `_raise_web_tool_error`（`web_tools.py:872`）将 `next_action` 嵌入 hint: `f"[{normalized_action}] {message}"`。

测试 `test_current_fetch_adapter_failed_outcome` 使用 hint `"[change_source] Use another source."` → `next_action == "change_source"`，验证提取正确。

### `http_status` 与 `diagnostics` 正确性验证

- `ToolFailedOutcome.result` 是 `ToolResultFailure`，只包含 `error/message/hint/meta` 四个字段。
- current adapter 投影 `ToolBusinessError` 时只保留 `code/message/hint`，`extra` 中的 `http_status` 与 `internal_diagnostics` 不进入 outcome。
- 诊断脚本将 `http_status` 设为 `None`，并在 `diagnostics.note` 中说明这一 contract 边界。
- 这符合计划的 diagnostic 字段定义: `http_status` 是 `fetch_web_page_profile` 失败字段，当前值为 `None` 是正确的——不是站点事实缺失，而是 contract 不暴露。

---

## README / Doc Decision Assessment

**决策**: 不更新 `tests/README.md`。**判定: 正确。**

依据:
- `tests/README.md` 更新边界: "如果之后新增测试层级、测试运行方式或测试维护规则发生变化，应在对应变更中同步更新本文件"
- 新增的 `test_diagnose_web_access.py` 位于既有 `tests/tools/web/` 层级下
- 既有规则 "`tests/tools/web/` 的 Web provider 测试必须保持 deterministic" 已覆盖新测试
- 未新增测试层级、运行方式或维护规则

不更新 `docs/host/design.md`、`docs/engine/design.md`、各层 README 的决策同样正确——Slice 3 未修改 Host/Engine/Service/UI 代码。

---

## Validation Gaps

1. **comparison_bucket 矩阵不穷尽**: 见 Finding 1，6/13 分支覆盖。非阻塞，决策树实现是确定性的。
2. **未验证 live network 下的 diagnostic artifact**: 按计划，不是本 Slice 责任。live network 验证留给 F03 或 manual opt-in。
3. **`browser_only_success` 分支无测试**: 计划 step 9 明确列出此 bucket，但不在 exact tests 列表中。逻辑正确性由确定性条件链保证。

---

## Residual Risks

| 风险 | 状态 | 缓解 |
|---|---|---|
| live network 结果天然不稳定 | 已知 | F02 通过 explicit opt-in 和 evidence-only 输出降低风险 |
| Playwright 安装/浏览器 channel 差异 | 已知 | 缺失记录为 diagnostic profile failure |
| current adapter 不暴露 http_status/internal_diagnostics | 已记录 | 诊断 artifact 显式声明边界（`diagnostics.note`），不把缺失误解为站点事实 |
| comparison bucket 矩阵覆盖不穷尽 | 已知（Finding 1） | 决策树是确定性的；F03 可补齐覆盖 |
| `requests_only_success` 的 fetch_failed 条件比计划文本严格 | 已知（Finding 2） | 语义更精确，不构成功能缺陷 |

---

## 约束合规检查

| 约束 | 状态 |
|---|---|
| 中文 docstring（AGENTS） | 通过 — 所有函数和类使用中文 docstring |
| 无 `Any`/`object` 类型签名 | 通过 — 使用 `JsonValue`、`Mapping`、`Sequence` 等强类型 |
| 无 lazy/glue compatibility | 通过 — 无兼容性 re-export、wrapper 或 facade |
| 无 OLD `ToolRegistry`/`truncation`/`fetch_more`/`dayu.web`/UI imports | 通过 — AST import guard 测试确认 |
| 无反向依赖 | 通过 — `utils/diagnose_web_access.py` 只导入 `dayu.contracts`、`dayu.runtime.tools_discovery`、`dayu.tools.web.provider` |
| 不改 Host/Engine/ToolRuntime contract | 通过 |
| 不改 production Web behavior | 通过 |
| 不改默认 CI workflow | 通过 |
| 不定义 Web smoke | 通过 |
| 不做 live network/Playwright 的默认测试 | 通过 — 全部使用 monkeypatch/tmp_path/synthetic payload |
