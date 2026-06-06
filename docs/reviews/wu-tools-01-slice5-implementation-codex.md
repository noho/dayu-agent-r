# WU-TOOLS-01 Slice S5 Implementation

Gate: implementation
Work unit: WU-TOOLS-01
Slice: S5 - Web Tools Provider
Agent: AgentCodex
Status: implementation complete; stopped before review / re-review / commit / push / PR

## 实现摘要

- 新增 `dayu/tools/web/`，从 OLD `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_*.py` 迁移 Web tools 业务实现。
- 新增 `dayu.tools.web:discover_tools` provider，通过当前 `ToolsDiscoveryProviderSpec.config` 解析 `WebToolsConfig`，并只暴露 `search_web` 与 `fetch_web_page`。
- 默认 `allow_private_network_url=false`，private / local URL fail closed；显式配置 `true` 时才放行。
- Web tools 声明使用当前 `dayu.contracts.tool_schema.ToolTruncateSpec`，实际 truncation 与 `fetch_more` 仍由当前 Host ToolRuntime 负责。
- Web provider 对两个工具采用 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`；OLD 共享 requests session 与 Playwright fallback 的并发安全未在本 slice 证明，因此 provider 级串行是当前 policy。
- 新增 deterministic 测试 `tests/tools/web/test_web_tools_provider.py`，mock 搜索 provider、requests 主路径与 Playwright fallback，不做 live network。

## Import Closure Inventory

源文件：

- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_tools.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_fetch_orchestrator.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_search_providers.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_challenge_detection.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_http_encoding.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_http_session.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_playwright_backend.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_recovery.py`

直接 import 分类：

| OLD import | 分类 | 处理 |
|---|---|---|
| 标准库：`json` / `ipaddress` / `os` / `re` / `socket` / `ssl` / `time` / `dataclasses` / `typing` / `urllib.parse` / `threading` / `multiprocessing` / `queue` / `pickle` / `atexit` / `math` / `codecs` / `importlib.util` | included | 保留；另补 `logging` 作为本地日志适配器。 |
| 第三方：`requests` / `urllib3` / `bs4` | included | 保留 OLD Web HTTP / HTML 行为；测试中 monkeypatch，不触发 live network。 |
| 可选第三方：`playwright` / `playwright_stealth` | included-as-optional | 保留 OLD lazy import 和缺失降级路径；测试 monkeypatch fallback，不要求安装或启动浏览器。 |
| `dayu.contracts.cancellation.CancellationToken` | included-with-adaptation | 当前 token 只有 `is_cancelled/cancel_reason/requested_at`，无 OLD `raise_if_cancelled()`；迁移处改为当前 token 观察语义。 |
| `dayu.contracts.protocols.ToolExecutionContext` | included-with-adaptation | 当前工具执行上下文为 `BatchToolExecutionContext`，仅为 `fetch_web_page.execution_context` 注入取消 token。 |
| `dayu.contracts.env_keys.*` | included-as-local-constant | 当前仓库无 `env_keys` 模块；保留 `SEC_USER_AGENT`、`TAVILY_API_KEY`、`SERPER_API_KEY` 字符串常量，不新增兼容 facade。 |
| `dayu.docling_runtime.*` | included | 改到当前 `dayu.documents.docling_runtime.*`。 |
| `dayu.engine.processors.html_pipeline` / `text_utils` | included | 改到当前 `dayu.documents.processors.*`。 |
| `dayu.engine.tools.web_*` | included | 改为 `dayu.tools.web.web_*` 相对 import。 |
| `dayu.log.Log` | excluded-with-local-adapter | 不迁移 OLD logging facade；Web 文件内提供极窄 `Log` 本地适配到 stdlib logger。 |
| `dayu.engine.tool_contracts.ToolSchema` / `ToolTruncateSpec` | excluded-with-current-contract | 改为当前 `dayu.contracts.tool_schema.ToolSchema`、`ToolTruncateSpec` 与 `ToolTruncationStrategy`。 |
| `dayu.engine.tool_errors.ToolBusinessError` | included-with-adaptation | 使用 `_legacy_adapter.tool_errors.ToolBusinessError`；因 OLD Web 传入 `url/next_action/http_status/internal_diagnostics` 扩展参数，`web_tools.py` 定义子类吸收并写入 `extra`。 |
| `dayu.engine.tool_registry.ToolRegistry` | excluded-with-reason | 不迁移 OLD ToolRegistry；注册参数改为 `LegacyToolDeclarationCollector`。 |
| `dayu.engine.tools.base.tool` | included | 改为 `_legacy_adapter.tool_decorator.tool`，只收集声明 metadata。 |
| OLD `/Users/leo/workspace/dayu-agent/dayu/web` | excluded-with-reason | 属 UI / FastAPI / Streamlit，不属于 Web tools provider。 |
| OLD `TruncationManager` / OLD `fetch_more` / OLD truncate-fetch_more projection | excluded-with-reason | 当前 Host ToolRuntime owner；Web provider 不暴露 `fetch_more` business tool。 |

Blocker: none. import closure 不需要 UI 模块、live network 测试、OLD registry、OLD truncation/fetch_more/projection 或未分类 helper。

## 迁移原则遵守说明

- `search_web` 与 `fetch_web_page` 的业务 pipeline、URL safety、search provider selection、challenge detection、requests/Playwright fallback 和 diagnostic payload 逻辑按 OLD 实现迁移。
- 必要变更只限当前仓库 import/package 适配、当前 `ToolTruncateSpec` 声明、current execution context 注入、current cancellation token 差异，以及 OLD `ToolBusinessError` 扩展参数的窄适配。
- 未迁移 OLD `ToolRegistry`、OLD `TruncationManager`、OLD `fetch_more`、OLD `/dayu/web` UI。

## Config / URL Safety 边界

- Provider 从 `spec.config` 解析 `WebToolsConfig`，字段包括 `provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel` 与 `playwright_storage_state_dir`。
- `allow_private_network_url` 默认 `False`。默认情况下 `fetch_web_page("http://127.0.0.1/...")` 返回 current `ToolFailedOutcome(error="permission_denied")`。
- 显式配置 `allow_private_network_url=True` 时，provider 把该策略传给迁移 Web 函数闭包，URL safety 才放行 private/local URL。

## 输入 / 响应投影说明

- 输入：provider 通过 `_legacy_adapter` 按 current schema 校验/转换 `domains`、`recency_days`、`max_results` 与 `url`。`recency_days=7.0`、`max_results=3.0` 会被转换为整数；`url=["..."]` 会在进入 Web 抓取逻辑前返回 `ToolFailedOutcome(error="invalid_argument")`。
- 成功响应：`search_web` 与 `fetch_web_page` 的 plain dict 返回直接成为 current `ToolCompletedOutcome.result.value`，不含 OLD `ok/value` envelope。
- 失败响应：`ToolBusinessError`、URL safety rejection、timeout-like / requests / conversion 类失败、adapter validation failure 均投影为 current `ToolFailedOutcome`；unexpected exception 走 adapter 的 `execution_error`。

## TruncateSpec 映射说明

- `search_web` 声明 `ToolTruncateSpec(enabled=True, strategy=ToolTruncationStrategy.LIST_ITEMS, limits={"max_items": 10}, target_field="results", field_path=None, ttl_seconds=None)`。
- `fetch_web_page` 声明 `ToolTruncateSpec(enabled=True, strategy=ToolTruncationStrategy.TEXT_CHARS, limits={"max_chars": fetch_truncate_chars}, target_field="content", field_path=None, ttl_seconds=None)`。
- 当前 Host ToolRuntime 负责执行时截断与 framework `fetch_more`，Web provider 不提供 OLD `fetch_more`。

## 测试 / Pyright / Diff Check 结果

- `source .venv/bin/activate && pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py -q`
  - 当前结果：22 passed。
- `source .venv/bin/activate && pyright`
  - 当前结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 当前结果：通过，无 whitespace error。

## README 同步说明

- `dayu/config/README.md`：补充 `web-tools` provider config、默认 disabled、默认 private/local URL fail-closed、显式放行字段。
- `tests/README.md`：补充 Web provider 测试职责与 deterministic mock / no live network 约定。

## 残余风险

- Provider 级串行执行是当前显式 policy；共享 requests session 与 Playwright fallback 并发安全未在 S5 中证明。后续如需要并发执行，应先补并发安全证据或独立 hardening。
- Web live network 行为未在本 slice 验证；按验证要求，S5 仅覆盖 deterministic mocked requests/search/Playwright paths。

## 完成状态

Implementation complete for Slice S5. 本轮按用户要求停在 implementation；未进入 review / re-review / commit / push / PR gate。
