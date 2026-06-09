# WU-TOOLS-01-F02 Slice 3 Code Review - AgentMiMo

## 元数据

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Review type: Slice 3 code review
- 日期: 2026-06-09
- Reviewer: AgentMiMo
- 审查范围:
  - `tests/tools/web/test_diagnose_web_access.py`
  - `utils/diagnose_web_access.py` Slice 3 diff
  - `docs/reviews/wu-tools-01-f02-slice3-implementation-codex.md`

## Verdict

**pass-with-findings**

无 blocking issue。发现 1 个中等 severity finding 和 2 个低 severity findings。

## Findings

### F1 [Medium] `socket` 模块导入未使用

- 文件: `utils/diagnose_web_access.py:17`
- 证据: `import socket` 存在，但全文搜索 `socket.` 返回 0 匹配。
- 影响: 违反编码硬约束中"禁止无必要的 import"精神；pyright 当前未报错是因为 `socket` 是标准库，但未使用导入增加认知负担。
- 建议: 删除 `import socket`。

### F2 [Medium] Slice 3 计划要求的 AST/import guard 测试缺失

- 文件: `tests/tools/web/test_diagnose_web_access.py`
- 计划要求: Slice 3 exact tests 明确要求 "AST/import guard 确认 `utils/diagnose_web_access.py` 不导入 OLD registry / truncation / fetch_more / UI"。
- 证据: 测试文件已定义 `_FORBIDDEN_IMPORTS` 常量（line 30-37）和 `_DIAGNOSE_SCRIPT`（line 29），但没有对应的测试函数使用它们。全文搜索 `test_diagnose_web_access_does_not_import` 返回 0 匹配。
- 影响: 该测试是 Slice 3 的明确验收条件之一；虽然 `test_web_tools_provider.py` 已有类似 guard 覆盖 provider 侧，但诊断脚本自身的 import 边界缺少独立验证。
- 建议: 新增 `test_diagnose_web_access_does_not_import_old_web_or_ui_paths()` 函数，复用已有的 `_FORBIDDEN_IMPORTS` 和 `_DIAGNOSE_SCRIPT`。

### F3 [Low] Bucket matrix 测试覆盖不完整

- 文件: `tests/tools/web/test_diagnose_web_access.py:112-185`
- 证据: `test_comparison_bucket_matrix` 只覆盖 6 种 bucket：`requests_only_sampled`、`mixed`、`all_success`、`fetch_outperforms_requests`、`fetch_only_success`、`child_process_error`。
- 计划定义了 12+ 种 bucket。未覆盖的 bucket 包括：`partial_sample`、`requests_only_success`、`browser_only_success`、`requests_and_fetch_success_playwright_failed`、`fetch_only_failure`、`all_failed`、`playwright_challenge_detected`（独立 case）。
- 影响: 低。已覆盖的 6 种包含了 classifier 的主要分支路径（child_process_error guard、three-path all success、challenge before all_success、two-path fetch success、one-path fetch success、zero sample fallback）。未覆盖的 bucket 可通过已有分支推导。但完整 matrix 测试可作为回归防线。
- 建议: 可在后续迭代补齐；不阻塞本 Slice。

## Accepted-Plan 对齐评估

### 测试覆盖

| 计划要求 | 状态 | 备注 |
|---|---|---|
| JSONL/TXT corpus 解析 | 已覆盖 | `test_jsonl_and_txt_corpus_parsing_retains_metadata_and_deduplicates` |
| 元数据保留 | 已覆盖 | 同上，验证 label/region/category/notes |
| 去重 | 已覆盖 | 同上，验证 duplicate URL 被过滤 |
| 非法 JSONL 报错 | 已覆盖 | `test_invalid_jsonl_reports_line_number` |
| storage-state host 路径解析 | 已覆盖 | `test_storage_state_dir_resolves_existing_host_input_and_default_output` |
| comparison bucket matrix | 部分覆盖 | 6/12+ bucket；见 F3 |
| batch row/summary 统计 | 已覆盖 | `test_batch_rows_and_summary_counts` |
| ToolCompletedOutcome 成功投影 | 已覆盖 | `test_current_fetch_adapter_completed_outcome_generates_ok_profile` |
| ToolFailedOutcome 失败投影 | 已覆盖 | `test_current_fetch_adapter_failed_outcome_generates_business_readable_profile`，含 next_action/http_status/diagnostics |
| CLI single deterministic JSON | 已覆盖 | `test_cli_single_mode_writes_deterministic_json` |
| CLI batch monkeypatch child | 已覆盖 | `test_cli_batch_mode_uses_monkeypatched_child_execution` |
| OLD import guard | 未覆盖 | 见 F2 |

### diagnose_web_access.py 修改评估

- `next_action` 从 hint 前缀恢复：实现正确，`_NEXT_ACTION_HINT_PATTERN` 只捕获 `[action]` 中的 action 部分。
- `http_status` 显式为 `None`：正确，说明 current outcome 不暴露该字段。
- `diagnostics` 字段：正确说明 current adapter 边界，包含 `diagnostic_source`、`error_code`、`available_fields` 和业务可读 `note`。
- root cause 证据成立：`ToolBusinessError.extra` 确实不经过 current adapter 进入 `ToolFailedOutcome`。
- 最小修正原则遵守：不改 Host/Engine/ToolRuntime/Web production contract，只在 opt-in diagnostics artifact 中补充说明。

## AGENTS 约束检查

| 约束 | 状态 | 备注 |
|---|---|---|
| 中文 docstring | 通过 | 所有函数和类均有完整中文 docstring |
| 禁止 `Any`/`object` 类型签名 | 通过 | AST 扫描无命中 |
| 禁止 OLD registry/truncation/fetch_more/UI imports | 通过 | import 列表只包含 current contracts、runtime、web provider |
| 禁止反向依赖 | 通过 | `utils/` 只依赖 `dayu.contracts`、`dayu.runtime`、`dayu.tools.web` |
| 禁止兼容性代码 | 通过 | 无 compatibility re-export/wrapper |
| Protocol 代替动态边界 | 通过 | Playwright 使用 `_PlaywrightProtocol` 等窄 Protocol |
| `runtime_checkable` 使用有理由 | 通过 | `_ResponseProtocol` 的 `isinstance` 检查在 `_network_event_summary` 中使用 |
| `cast` 使用有理由 | 通过 | 用于 `prepared.headers`、`response.headers`、`json.loads` 等已知类型边界 |

## tests/README.md 决策

未更新 `tests/README.md`。

原因：Slice 3 只在既有 `tests/tools/web/` 层级下新增 focused deterministic test。`tests/README.md` 已明确 "Web provider tests 必须保持 deterministic：搜索 provider、requests 主路径和 Playwright fallback 都通过 monkeypatch / fixture 替身控制，不做 live network 请求"（line 143）。新增测试文件遵循该约定，没有新增测试层级或运行方式。

## 验证缺口

- Controller 已报告的验证命令全部通过：pytest 23 passed、pyright 0 errors、bash -n 通过、git diff --check 通过。
- 无额外验证缺口。AST/import guard 测试缺失（F2）不影响生产安全性，因为 `test_web_tools_provider.py` 已有 provider 侧 guard。

## 残余风险

- Deterministic tests 不覆盖 live network、real browser、real storage-state cookies、anti-bot challenge、provider/API availability。这是 F02 设计决策，不是遗漏。
- `ToolFailedOutcome` 仍不能暴露 Web `ToolBusinessError.extra` 字段。本 Slice 只使 diagnostics artifact 显式说明该边界。
- Bucket matrix 测试不完整（F3），但已覆盖 classifier 主要分支路径。

## 结论

Slice 3 实现正确，diagnose_web_access.py 的修改有 root-cause 证据支撑且保持在 opt-in diagnostics 边界内。发现 1 个未使用 import（F1）和 1 个计划要求的测试缺失（F2），均为中等 severity，不阻塞 gate 但应在后续 Slice 或 fix 中处理。Bucket matrix 测试覆盖不完整（F3）为低 severity，可后续补齐。
