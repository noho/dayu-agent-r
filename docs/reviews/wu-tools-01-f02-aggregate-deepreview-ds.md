# WU-TOOLS-01-F02 Aggregate Deepreview (AgentDS)

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Review type：aggregate deepreview
- Reviewer：AgentDS
- Date：2026-06-09
- Accepted commits：plan `ded9e690`, Slice 1 `8f5bb379`, Slice 2 `6984c514`, Slice 3 `89604aa0`
- Design sources：`docs/host/design.md`, `docs/engine/design.md`
- Control source：`docs/host/issues-implementation-control.md`
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Review scope：`utils/diag_web.sh`, `utils/diag_web_batch.sh`, `utils/web_ci_urls.jsonl`, `utils/diagnose_web_access.py`, `tests/tools/web/test_diagnose_web_access.py`

## Verdict

**pass-with-findings**

3 个 minor finding，无 blocking issue。所有 findings 均可由 F03 或后续维护修复，不阻止进入 draft PR gate。

---

## 1. 成功信号合规评估

### 1.1 单 URL / 批量双模式 ✓

`utils/diagnose_web_access.py` 同时支持 `--url`（单 URL）和 `--url-file`（批量）两种模式。`main()` 在 `diagnose_web_access.py:2518` 按 `options.url_file` 分流入 `_run_single_diagnose` 或 `_run_batch_diagnose`。

### 1.2 Shell wrapper 与 URL corpus ✓

- `utils/diag_web.sh`：Shell wrapper，接受 `<URL> [额外参数...]`，默认 headed chrome、30s manual wait、storage-state dir。
- `utils/diag_web_batch.sh`：批量 shell wrapper，接受 `<URL文件> [额外参数...]`，默认 headed chrome、timestamp 输出目录。
- `utils/web_ci_urls.jsonl`：60 条 URL，覆盖 foreign/china × news/finance/government 三类，逐条含 url/label/region/category/notes 字段。其中 40 条 foreign（Reuters、SEC、FRB 等），20 条 china（新华网、央行、证监会等）。

三个文件均通过 `bash -n` 语法检查。

### 1.3 单 URL 输出结构 ✓

`_build_single_diagnostic_payload`（`diagnose_web_access.py:1852`）产出的 JSON 包含：
- `schema_version`: `"web-diagnostics-v1"`
- `generated_at`: UTC ISO 时间
- `url`: 输入 URL
- `requests_profile`: raw requests 证据对象（含 `raw_requests_header_source: "diagnostic_local"`）
- `fetch_web_page_profile`: current fetch 工具证据对象
- `playwright_profile`: Playwright 浏览器证据对象（跳过时为 `skipped=true`）
- `comparison_bucket`: 访问路径对比分桶

### 1.4 requests_profile 结构 ✓

`_build_requests_profile`（`diagnose_web_access.py:1023`）包含：
- 成功时：`sampled`, `ok`, `status`, `normalized_url`, `prepared_headers`（已脱敏）, `timeout_seconds`, `result`（含 `status_code`, `final_url`, `elapsed_seconds`, `text_prefix`, `challenge_detected`）
- 失败时：`status`, `error`, `result` 含 `error_type`, `error_message`, `elapsed_seconds`
- URL 安全策略拒绝时：`sampled=false`, `status: "blocked_by_diagnostic_url_policy"`
- `raw_requests_header_source: "diagnostic_local"` 标注本地 header 来源

### 1.5 fetch_web_page_profile 结构 ✓

`_build_tool_fetch_profile`（`diagnose_web_access.py:1232`）通过 current `ToolDefinition.callable` 调用，产出：
- `ToolCompletedOutcome` → `sampled=true`, `ok=true`, `title`, `final_url`, `fetch_backend`, `content_prefix`
- `ToolFailedOutcome` → `sampled=true`, `ok=false`, `error_code`, `message`, `hint`, `next_action`, `diagnostics`
- `ToolCancelledOutcome` → `sampled=true`, `ok=false`, `status: "cancelled"`
- `ToolAwaitingOutcome` → `sampled=true`, `ok=false`, `status: "awaiting"`
- callable 异常 → `sampled=true`, `ok=false`, `status: "callable_exception"`

`next_action` 从 `hint` 的 `[action]` 前缀正则恢复（`diagnose_web_access.py:1321`）。

### 1.6 playwright_profile 结构 ✓

`_build_playwright_profile`（`diagnose_web_access.py:1557`）包含：
- Playwright package 缺失 → `sampled=true`, `ok=false`, `status: "playwright_package_missing"`
- 成功 → `ok=true`, `status: "completed"`, browser/channel/headed/timeout, navigation（response_status/final_url/title/user_agent）, page_text_prefix, html_prefix, challenge_detected/challenge_signals, network_events（有界）
- 失败 → `ok=false`, `status: "playwright_error"`, error_type/error/message
- storage_state_in/out 仅记录路径，附 `storage_state_note: "仅记录 storage state 路径，不内联 cookie、localStorage 或其它敏感状态内容。"`

### 1.7 批量输出 ✓

`_run_batch_diagnose`（`diagnose_web_access.py:2427`）产出：
- `corpus.normalized.jsonl`：规范化输入 URL entries
- `diagnostics/`：每个 URL 的单文件 JSON
- `results.jsonl`：每行含 url、diagnostic_path、comparison_bucket、per-path sampled/ok/status/error 摘要字段
- `summary.json`：schema_version、run_label、input_file、各类计数、comparison_buckets 分布、child_returncodes
- `summary.md`：业务可读 Markdown 汇总，含 per-path 成功/采样计数、comparison bucket 分布、各路径 status 计数

### 1.8 current ToolDefinition.callable 调用 ✓

`_fetch_web_page_definition`（`diagnose_web_access.py:1134`）通过 `ToolsDiscoveryProviderSpec` + `PythonImportPathProvider("dayu.tools.web.provider:discover_tools")` 获取 provider，再按 `name == "fetch_web_page"` 筛选 `ToolDefinition`。调用使用 `ToolCallRequest` + `BatchToolExecutionContext` + `_DiagnosticCancellationToken`，并通过 `asyncio.run(...)` 做同步边界转换。

未恢复 OLD `ToolRegistry`、OLD truncation manager、OLD `fetch_more` 或 OLD `dayu.web`。AST import guard test (`test_diagnose_web_access_does_not_import_old_web_or_ui_paths`) 显式确认。

### 1.9 缺失依赖的 skip-safe 输出 ✓

- Playwright package 缺失 → `playwright_package_missing` profile，不抛异常
- Playwright browser 执行失败 → `playwright_error` profile，记录 error_type/message
- `--skip-playwright` → `skipped=true` profile
- `--skip-tool-fetch` → `skipped=true` profile

### 1.10 确定性测试 ✓

`tests/tools/web/test_diagnose_web_access.py` 所有 10 个测试均通过 monkeypatch/fixture 控制，不做 live network 或 real browser 请求。

---

## 2. 非目标合规评估

### 2.1 不定义 Web smoke pass/fail/skip gate ✓

F02 只输出诊断证据和 comparison bucket。`summary.md` 和 `summary.json` 中比较路径和统计计数，不包含 pass/fail 结论或 smoke gate 判定逻辑。

### 2.2 不关闭 WU-TOOLS-01-S5-R2 ✓

Residual risk `WU-TOOLS-01-S5-R2` 在 `issues-implementation-control.md:198` 仍标记为 `deferred-with-owner`，destination 为 WU-TOOLS-01-F03 / GitHub Issue #120。

### 2.3 不把 live network/browser diagnostics 放入默认 CI ✓

Shell wrappers 和 Python 脚本均为手动 opt-in 入口，无 CI workflow 引用。默认 pytest 排除 live network/browser。

### 2.4 不恢复 OLD 路径 ✓

- `diagnose_web_access.py` 的 import 列表不含任何 `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools`、`dayu.engine.tools.fetch_more`、`dayu.web`、`dayu.ui`
- AST import guard test 通过扫描源码显式确认（`test_diagnose_web_access_does_not_import_old_web_or_ui_paths`）
- grep 全文件确认 0 匹配

### 2.5 不重写 Web production behavior ✓

`utils/diagnose_web_access.py` 只读取 `dayu.tools.web.provider.discover_tools`、`dayu.tools.web.web_challenge_detection.detect_bot_challenge` 和 contracts 层公共类型，不修改任何 `dayu/tools/web/` 下的生产代码。

### 2.6 不修改 Host/Engine/ToolRuntime contract ✓

诊断脚本是独立 utility，不引入新 Host command、Engine event、ToolRuntime policy 或 durable schema。不连接 Host 取消状态（`_DiagnosticCancellationToken` 恒返回 `False`/`None`）。

### 2.7 不把单个 live 站点偶发失败判定为 production regression ✓

F02 只输出证据和分类，不包含 regression 判定逻辑。

---

## 3. 实现正确性与安全性逐项审查

### 3.1 CLI parser

**Finding #1 (minor): `--url` 与 `--url-file` 同时传入时非清晰失败**

- 位置：`diagnose_web_access.py:2518`
- 证据：`if options.url_file:` 仅判断 url_file 是否非空字符串，不为空时直接进入批量模式，忽略同时传入的 `--url`
- Plan 要求："`--url` 与 `--url-file` 同时存在或同时缺失时清晰失败"（plan §Slice 2 - Error handling）
- 当前行为：两者同时存在时 `--url` 被静默忽略，批量模式运行；两者同时缺失时单 URL 模式因 `options.url` 为空字符串抛出 `ValueError("单 URL 模式必须提供 --url。")`
- 严重性：低。现有使用模式中用户一般不传冲突参数。若有冲突，进入批量模式是可理解的默认选择。
- 建议：在 `main()` 或 `_parse_options()` 中增加互斥检查，同时传入时输出清晰错误并返回非零退出码。可在 F03 或后续 maintenance 修复。

**CLI 选项类型安全**：`_parse_options()` 返回 `CliOptions` 强类型 dataclass（frozen, slots=True），所有字段均有明确类型。CLI 数值参数强制 `max(..., 0.001)` 下限，`max_network` 和 `fetch_truncate_chars` 强制最小 `1`。✓

### 3.2 URL 文件解析

- JSONL 解析：`_read_json_line` 支持对象（带 url/label/region/category/notes）和裸字符串两种格式 ✓
- 非法 JSON → 带行号 ValueError（`"JSONL 第 {line_number} 行不是合法 JSON"`）✓
- TXT 解析：`_read_txt_url_entries` 跳过空行和 `#` 注释行 ✓
- 去重：`_deduplicate_url_entries` 按 URL 保留首次出现的元数据 ✓
- 空文件 → `ValueError("URL 文件中没有可用样本。")` ✓

### 3.3 内网/本地 URL 安全策略

`_validate_url_safety`（`diagnose_web_access.py:917`）层层防御：
1. `_normalize_url_for_http` → 拒绝非 http/https scheme 或空 netloc
2. `_is_private_or_local_host` → 检查 localhost、`.local`、`.localhost`、IPv4/IPv6 private、loopback、link-local、reserved、multicast、unspecified
3. 除非 `allow_private_network_url=True`，否则拒绝

**潜在遗漏**：`_is_private_or_local_host` 未处理 IPv6 的 `::1` loopback 格式和 IPv4-mapped IPv6 地址。这是 minor gap，但 `ipaddress.ip_address()` 已覆盖标准 IPv6 表示。当前 `ip_address.is_loopback` 可捕获 `::1`。✓

### 3.4 批量子进程行为

`_run_batch_diagnose` 逐 URL 启动子进程：
- 子进程命令通过 `_build_batch_child_command` 构造，完整传递所有 CLI 选项 ✓
- `subprocess.run(capture_output=not interactive_mode)`：headed 或 manual-wait 模式不捕获输出，允许终端交互 ✓
- 子进程非零退出 → `_child_error_payload` 创建 `status="child_process_error"` payload，记录 `returncode`、有界 `stdout_prefix`、`stderr_prefix` ✓
- 子进程成功但 JSON 损坏 → 同样记为 `child_process_error`，附诊断信息 ✓
- `results.jsonl` 中 child_process_error 行不写入普通 comparison bucket ✓
- `summary.json` 单独统计 `child_process_error_count` 和 `child_returncodes` ✓

**Finding #2 (minor): 批量模式下无并发控制**

- 位置：`diagnose_web_access.py:2461-2493`
- 证据：`for index, entry in enumerate(entries, start=1)` 串行处理所有 URL，每个 URL 启动独立子进程并等待完成
- 影响：60 个 URL 串行处理总耗时可能较长，但作为 opt-in 诊断工具可接受
- 建议：若 F03 需要加速批量诊断，可增加 `--max-workers` 参数引入 `concurrent.futures` 并行化。当前串行行为满足 F02 目标。

### 3.5 输出路径

- 单 URL：默认 `workspace/output/web_diagnostics/{slug}-{timestamp}.json`；可通过 `--output` 覆盖 ✓
- 批量模式：默认 `workspace/output/web_diagnostics/{run_label}/`；可通过 `--batch-output-dir` 覆盖 ✓
- 所有输出 `mkdir(parents=True, exist_ok=True)` 自动创建父目录 ✓
- `storage_state_out` 写入前也自动创建父目录 ✓

### 3.6 JSON schema 稳定性

`_SCHEMA_VERSION = "web-diagnostics-v1"` 写入每个 payload 顶层。F03 最小稳定子集字段均已覆盖：
- 顶层 `schema_version`, `url`, `comparison_bucket` ✓
- `requests_profile` / `fetch_web_page_profile` / `playwright_profile` 均稳定提供 `sampled`、`ok`、`status`、`error` 字段 ✓
- `results.jsonl` 每行稳定提供 `url`、`diagnostic_path`、`comparison_bucket`、per-path `sampled`/`ok`/`status`/`error` ✓
- `summary.json` 稳定提供计数与分布统计 ✓

### 3.7 Comparison bucket 分类

`_classify_diagnostic_bucket`（`diagnose_web_access.py:1790`）按确定性 decision tree 顺序检查：
1. `child_process_error` → `"child_process_error"`
2. `all_success`（三条路径均采样且均成功）→ `"all_success"`
3. `playwright_challenge_detected`（Playwright 采样且 challenge 为真）→ `"playwright_challenge_detected"`
4. `fetch_only_success`（fetch 成功，requests + Playwright 均采样且失败）→ `"fetch_only_success"`
5. `fetch_outperforms_requests`（fetch 成功，requests 采样且失败，Playwright 未采样或失败）→ `"fetch_outperforms_requests"`
6. `requests_only_sampled`（requests 成功，fetch + Playwright 均未采样）→ `"requests_only_sampled"`
7. `requests_only_success`（requests 成功，fetch 采样且失败，Playwright 未采样或失败）→ `"requests_only_success"`
8. `browser_only_success`（Playwright 成功，fetch + requests 均采样且失败）→ `"browser_only_success"`
9. `requests_and_fetch_success_playwright_failed`（requests + fetch 成功，Playwright 采样且失败）→ `"requests_and_fetch_success_playwright_failed"`
10. `fetch_only_failure`（fetch 采样且失败，requests 或 Playwright 成功）→ `"fetch_only_failure"`
11. `all_failed`（所有采样路径均失败，至少一条被采样）→ `"all_failed"`
12. `partial_sample`（至少一条被采样，非空组合无法归入上述桶）→ `"partial_sample"`
13. Fallback → `"mixed"`

分类不依赖字典遍历顺序或错误 message 文本包含关系 ✓。

测试矩阵覆盖 13 个 synthetic case（`test_comparison_bucket_matrix`），包括 `all_success` 优先于 `playwright_challenge_detected` 的特殊例外。✓

### 3.8 Failed outcome 诊断

`_tool_failed_outcome_diagnostics` 明确声明 current `ToolFailedOutcome` 的字段边界和限制：
- `available_fields`: `["error_code", "message", "hint", "next_action_from_hint"]`
- `note`: "current ToolFailedOutcome 不暴露 Web 工具内部 http_status 或 internal_diagnostics"
- 不把缺失字段伪装成站点事实 ✓

### 3.9 Playwright optional 行为

- Playwright import 使用 lazy import（`diagnose_web_access.py:1587: from playwright.sync_api import sync_playwright`），且在 try/except ImportError 中 ✓
- `--skip-playwright` flag 支持显式跳过 ✓
- 所有 Playwright 类型通过本地 `Protocol` 定义：`_PlaywrightContextManagerProtocol`, `_PlaywrightProtocol`, `_BrowserTypeProtocol`, `_BrowserProtocol`, `_BrowserContextProtocol`, `_PageProtocol`, `_RequestProtocol`, `_ResponseProtocol` ✓
- `sync_playwright()` 返回类型通过 `cast(_PlaywrightContextManagerProtocol, sync_playwright())` 收口 ✓
- 浏览器和上下文通过 `_safe_close_context` / `_safe_close_browser` 安全关闭，忽略清理异常 ✓

### 3.10 Storage-state 路径处理

`_resolve_storage_state_paths`（`diagnose_web_access.py:1369`）：
- `--storage-state-dir` 设置时，按 `{host}.json` 自动解析输入/输出路径
- 已有 `{host}.json` 文件时才设为输入路径
- 输出路径始终设为 `{host}.json`
- `--storage-state-in` / `--storage-state-out` 显式指定时优先
- 所有路径均 `expanduser().resolve()` 规范化 ✓

### 3.11 Shell wrapper 语义

- `diag_web.sh`：`set -euo pipefail`，URL 必填参数，默认 timestamp 输出文件名，默认 headed chrome + 30s manual wait + storage-state dir
- `diag_web_batch.sh`：`set -euo pipefail`，URL 文件必填参数，默认 timestamp 输出目录，默认 headed chrome + 30s manual wait + storage-state dir
- 两个 wrapper 末尾 `"$@"` 支持额外参数透传，允许覆盖默认行为 ✓
- 输出根目录统一为 `workspace/output/web_diagnostics`，`mkdir -p` 自动创建 ✓

### 3.12 安全/隐私

**Header 脱敏**：`_redact_headers` 按 `_SENSITIVE_HEADER_FRAGMENTS`（authorization, cookie, token, secret, key）子串匹配脱敏为 `<redacted>` ✓。应用于：
- raw requests 的 prepared headers（`diagnose_web_access.py:1068`）
- raw requests 的 response headers（`diagnose_web_access.py:1097`）
- Playwright request 事件 headers（`diagnose_web_access.py:1459`）
- Playwright response 事件 headers（`diagnose_web_access.py:1482`）
- Playwright navigation 的 response headers（`diagnose_web_access.py:1652`）

**Storage-state 不内联**：`_build_playwright_profile` 中 storage state 只记录输入/输出路径字符串，附明确 note 说明不内联内容 ✓。`summary.json` 和 `summary.md` 统计中不含 storage-state 路径 ✓（summary 只计数，不列 per-url 路径细节）。

**内网/本地 URL 默认拒绝**：`_validate_url_safety` 默认拒绝 private/local URL ✓。

**Summaries 无敏感泄漏**：`summary.json` 只记录计数和分布，不包含 URL、header 或 storage-state 内容 ✓。唯一可能含 URL 的是 `results.jsonl` 和 `corpus.normalized.jsonl`，这些是诊断所需的 URL 标识，不包含访问凭据。

---

## 4. 测试质量评估

### 4.1 测试覆盖矩阵

| 测试 | 覆盖范围 | 做 live network |
|---|---|---|
| `test_jsonl_and_txt_corpus_parsing_retains_metadata_and_deduplicates` | JSONL/TXT 解析、去重、元数据保留 | N |
| `test_invalid_jsonl_reports_line_number` | 非法 JSONL 带行号错误 | N |
| `test_storage_state_dir_resolves_existing_host_input_and_default_output` | storage-state 路径按 host 解析 | N |
| `test_comparison_bucket_matrix` | 13 个 synthetic profile 的分桶矩阵 | N |
| `test_batch_rows_and_summary_counts` | synthetic rows 的批量汇总计数 | N |
| `test_current_fetch_adapter_completed_outcome_generates_ok_profile` | monkeypatch `ToolDefinition.callable` → `ToolCompletedOutcome` | N |
| `test_current_fetch_adapter_failed_outcome_generates_business_readable_profile` | monkeypatch `ToolDefinition.callable` → `ToolFailedOutcome` | N |
| `test_cli_single_mode_writes_deterministic_json` | monkeypatch 三个 profile builder 后 CLI 单 URL 模式输出 | N |
| `test_cli_batch_mode_uses_monkeypatched_child_execution` | monkeypatch `subprocess.run` 后 CLI 批量模式输出 | N |
| `test_diagnose_web_access_does_not_import_old_web_or_ui_paths` | AST 扫描确认无 OLD import | N/A |

### 4.2 测试充分性

- **Parser 与 classifier**：覆盖充分。JSONL/TXT 解析、去重、错误路径、storage-state 解析、13 个 bucket case 均被测试。
- **current adapter**：覆盖充分。成功/失败 outcome 投影均通过 monkeypatch 测试。
- **CLI integration**：覆盖充分。单 URL 和批量模式的端到端路径通过 monkeypatch 测试。
- **Import guard**：覆盖充分。AST 扫描确认无 OLD import。

测试矩阵足够支撑 F03 消费——F03 消费者可以通过这些确定性测试验证 utility 的逻辑行为，不需要 live network。

### 4.3 tests/README 决策

`tests/README.md:143` 已明确：`"tests/tools/web/` 的 Web provider 测试必须保持 deterministic：搜索 provider、requests 主路径和 Playwright fallback 都通过 monkeypatch / fixture 替身控制，不做 live network 请求。"

该约束自然覆盖 `test_diagnose_web_access.py`（位于同一目录）。未新增测试层级或运行方式，无需更新 tests/README。符合 plan：`"只有新增测试层级、运行方式或维护规则事实变化时才更新"`。

### 4.4 测试未覆盖项

- **`_build_requests_profile` 的 live requests 路径**：HTTP 连接、超时、异常分支未通过集成测试覆盖。这是 F02 的非目标（默认 deterministic），真实的 requests 行为通过手动 opt-in 验证。
- **`_build_playwright_profile` 的 live browser 路径**：Playwright 启动、导航、网络事件收集未通过集成测试覆盖。同样是 F02 的非目标。
- **`_build_batch_child_command` 的 CLI 参数完整性**：子进程命令构造未独立测试，但批量模式集成测试（`test_cli_batch_mode_uses_monkeypatched_child_execution`）间接覆盖了命令行构造路径。

---

## 5. AGENTS 合规评估

### 5.1 中文 docstring ✓

所有函数、类、模块均有中文 docstring，包含参数（Args）、返回值（Returns）、异常（Raises）。

### 5.2 强类型签名 ✓

- 无 `Any`、`object`、无类型参数、无类型返回值（grep 确认 0 匹配）
- `TypeAlias` 用于 `JsonObject`、`_PlaywrightNetworkEvent`
- Playwright 动态对象通过本地 `Protocol` 窄接口定义（8 个 Protocol 类），不扩散到公共签名
- `cast` 仅在必要时使用：requests headers（外部库返回 `MutableMapping`）、`sync_playwright()`（第三方库返回类型与 Protocol 不兼容）、`asdict()` 返回值

### 5.3 无胶水 seam / 无不当 lazy import ✓

- 唯一 lazy import：`from playwright.sync_api import sync_playwright`（在 `_build_playwright_profile` 内），有充分理由——Playwright 是可选依赖，缺失时应诊断记录而非 crash
- 无 `hasattr`、`getattr`（grep 确认 0 匹配）

### 5.4 无魔法字符串 ✓

- 常量在模块级别定义：`_SCHEMA_VERSION`, `_FETCH_TOOL_NAME`, `_DEFAULT_BATCH_OUTPUT_ROOT`, `_JSONL_SUFFIXES`, `_SENSITIVE_HEADER_FRAGMENTS`, `_REDACTED`, `_TEXT_PREFIX_CHARS`, `_STDIO_PREFIX_CHARS`, `_HTML_PREFIX_CHARS`, `_DEFAULT_FETCH_TRUNCATE_CHARS`, `_DEFAULT_USER_AGENT`, `_REQUEST_ACCEPT`, `_NEXT_ACTION_HINT_PATTERN`
- Comparison bucket 字符串是 schema/tool literal，符合豁免条件

### 5.5 无反向依赖 ✓

- `utils/diagnose_web_access.py` 只 import standard library + `requests` + `dayu.contracts.*` + `dayu.runtime.tools_discovery` + `dayu.tools.web.provider` + `dayu.tools.web.web_challenge_detection`
- 不 import `dayu.host`, `dayu.engine`, `dayu.service`, `dayu.ui`
- `dayu.runtime.tools_discovery` import 仅使用 `PythonImportPathProvider` 和 `ToolsDiscoveryProviderSpec`，不依赖 runtime aggregate discovery 的返回结构

### 5.6 LLM-facing 文本业务可读 ✓

- 错误说明使用业务可读描述：`"URL 被诊断脚本安全策略阻止；如需诊断内网或本地 URL，请显式传入 --allow-private-network-url。"`、`"不内联 cookie、localStorage 或其它敏感状态内容。"`、`"raw requests 使用诊断脚本本地 headers；它是对照路径，不代表生产 fetch_web_page 的完整抓取路径。"`
- `diagnostics` 字段明确说明 current ToolFailedOutcome 的可用字段和限制
- 未使用裸 `event_id`、`payload_ref`、digest、cursor、tool_call_id 作为用户理解失败的依据

---

## 6. 架构 / 非目标合规（汇总）

| 检查项 | 状态 | 证据 |
|---|---|---|
| 不修改 Host/Engine/ToolRuntime 公共契约 | ✓ | 诊断脚本是独立 utility |
| 不恢复 OLD ToolRegistry | ✓ | AST import guard + grep 0 matches |
| 不恢复 OLD truncation manager | ✓ | AST import guard + grep 0 matches |
| 不恢复 OLD fetch_more | ✓ | AST import guard + grep 0 matches |
| 不恢复 OLD dayu.web/UI | ✓ | AST import guard + grep 0 matches |
| 不改默认 CI | ✓ | 无 CI workflow 修改 |
| 不改 production Web tools | ✓ | 仅 import public provider 接口 |
| 不关闭 WU-TOOLS-01-S5-R2 | ✓ | Control doc 仍标记 deferred |
| 不定义 Web smoke gate | ✓ | 无 pass/fail 判定 |
| `raw_requests_header_source` 标注为 diagnostic_local | ✓ | 明确区分对照路径 vs 生产路径 |
| 不把内部治理状态伪装成业务事实 | ✓ | 错误消息业务可读 |
| comparison bucket 只描述访问路径对比 | ✓ | 分类逻辑只基于 per-path ok/sampled |

---

## 7. 验证覆盖与缺口

### 7.1 Controller 已执行验证

- `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`：23 passed ✓
- `python -m pyright dayu/ tests/ utils/`：0 errors ✓
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`：passed ✓
- `git diff --check`：passed ✓
- precise forbidden import / wide-type scan：no matches ✓

### 7.2 验证缺口

- **Live network manual validation**：未被自动化为 CI 步骤。这是 F02 的非目标——live validation 只能通过手动 opt-in 命令运行。F03 应在 plan 阶段决定是否需要定期 live diagnostics 运行。
- **Playwright browser 可用性验证**：未在任何自动化步骤中验证 Playwright 安装和 browser channel 可用性。同样是 F02 非目标。
- **batch 模式全量 URL corpus 运行**：60 条 URL 的完整 live batch 未在自动化中运行。这是手工 opt-in 操作。

---

## 8. Residual Risks

| ID | 严重性 | 描述 | Owner / Destination |
|---|---|---|---|
| F02-R1 | Low | `--url` 与 `--url-file` 同时传入时静默忽略 `--url`（Finding #1） | F03 或 maintenance fix |
| F02-R2 | Low | 批量模式无并发控制，60 URL 串行可能耗时较长（Finding #2） | F03 可选优化 |
| F02-R3 | Medium | Web smoke pass/fail 标准与 evidence 消费方式待 F03 裁决 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R4 | Medium | diagnostic JSON schema 的 F03 消费子集超出 F02 最小稳定子集时，F03 需在 plan 中声明依赖；schema mismatch skip/fail 策略由 F03 定义 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R5 | Low | `_is_private_or_local_host` 不处理 IPv4-mapped IPv6 地址（`::ffff:10.0.0.1`），但 `ipaddress.ip_address()` 可捕获此类地址 | 后续维护 |
| F02-R6 | Low | Playwright 安装与 browser channel 因环境不同而异；缺失时诊断记录为 profile failure，不影响其他路径 | Environment / operator |
| F02-R7 | Low | `fetch_web_page` 内部实现变化可能导致 current adapter 行为改变；通过 current `ToolDefinition.callable` 调用已是最小耦合边界 | WU-TOOLS-01 future changes |
| F02-R8 | Info | `utils/` 代码的覆盖率由项目策略豁免，但 test 中包含 parser/classifier/adapter 的非平凡测试 | N/A |

---

## 9. 下一 gate 建议

**推荐 gate：draft PR gate**（创建 WU-TOOLS-01-F02 的 draft pull request）。

理由：
1. 所有 blocking condition 均未触发。
2. 3 个 minor finding 均可由 F03 或后续维护修复，不阻止进入 draft PR。
3. Controller 已执行的验证链（pytest 23 passed, pyright 0 errors, bash -n passed, git diff --check passed, forbidden import scan 0 matches）覆盖了所有自动化要求。
4. Residual risks 均有明确 owner/destination。

进入 draft PR gate 前建议：
- 确认 Controller 将 Finding #1 和 Finding #2 记入 closeout 或 defer 到 F03。
- 确认 `issues-implementation-control.md` 的 WU-TOOLS-01-F02 行状态更新为 `ready-to-open-draft-PR`，next entry point 更新为 `draft PR gate`。
