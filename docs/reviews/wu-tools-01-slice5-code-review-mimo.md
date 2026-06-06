# WU-TOOLS-01 Slice S5 Code Review

Gate: code-review
Work unit: WU-TOOLS-01
Slice: S5 - Web Tools Provider
Agent: AgentMiMo
Status: PASS

## 审查范围

- `dayu/tools/web/` 全部 10 个 Python 文件
- `tests/tools/web/test_web_tools_provider.py` 测试文件
- 上下文：`docs/reviews/wu-tools-01-slice5-implementation-codex.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`

## 审查结论

**PASS。** 无 blocking finding。实现忠实迁移 OLD Web 工具，provider 只暴露 `search_web` 与 `fetch_web_page`，URL safety 默认 fail-closed，参数/响应投影正确，测试 deterministic 且覆盖关键路径。

---

## Findings（按严重性排序）

### 无 Blocking Finding

### 观察项（非阻塞，不影响 PASS 裁决）

#### O-1: `web_search_providers.py` DuckDuckGo User-Agent 与 `web_tools.py` 默认值不一致

- **文件**: `dayu/tools/web/web_search_providers.py:628`
- **现象**: `_search_with_duckduckgo` 使用 `headers={"User-Agent": "Mozilla/5.0"}`，而 `web_tools.py` 的 `_DEFAULT_BROWSER_USER_AGENT` 是完整 Chrome UA 字符串。
- **判定**: 这是 OLD 实现的原始行为——DuckDuckGo HTML 搜索路径使用简短 UA，与 SEC/通用抓取路径的完整 Chrome UA 是两条独立策略。迁移未修改此行为，符合迁移原则。
- **风险**: 无。

#### O-2: `Log` 类在三个模块中各有一份窄适配器

- **文件**: `web_tools.py:129`、`web_search_providers.py:27`、`web_playwright_backend.py:76`
- **现象**: 每个模块各自定义 `Log` 类，方法集不同（`debug/verbose`、`warn`、`debug/warning`）。
- **判定**: 按迁移原则，OLD 各模块原有独立日志适配；当前各自窄适配到 stdlib logger 是最小化迁移，不引入共享 facade。符合编码硬约束"禁止兼容性 wrapper"。
- **风险**: 无。后续如需统一日志策略，应在 `dayu.runtime` 层中立解决，不在本 slice 范围。

#### O-3: Provider 级串行执行策略

- **文件**: `dayu/tools/web/provider.py:354`
- **现象**: 两个工具均声明 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`。
- **判定**: 实现文档已说明原因——共享 requests session 与 Playwright fallback 的并发安全未在 S5 证明，因此保守串行。符合残余风险 R1 声明。
- **风险**: 已在实现文档中明确追踪。后续如需并发，应先补并发安全证据。

#### O-4: `_search_with_duckduckgo` 中 `except Exception` 的 `# pragma: no cover`

- **文件**: `dayu/tools/web/web_search_providers.py:218`
- **现象**: 搜索 provider fallback 的异常捕获标注 `# pragma: no cover`。
- **判定**: 测试通过 monkeypatch `search_public_web` 覆盖主路径；单 provider 失败后 fallback 到 duckduckgo 的路径由集成测试（非本 slice）覆盖。pragma 标注合理。
- **风险**: 无。

---

## 逐项审查

### 1. `dayu/tools/web/` 是否只迁移 Web tools，不包含 OLD UI / 旧 registry / truncation / fetch_more

**PASS。**

- `__init__.py` 只暴露 `discover_tools`。
- AST 解析测试 `test_web_modules_do_not_import_old_registry_truncation_fetch_more_or_ui` 验证全部 `.py` 文件不得 import `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools.fetch_more`、`dayu.web`。
- 实际 import 审计：
  - 标准库：`json`、`ipaddress`、`logging`、`os`、`re`、`socket`、`ssl`、`time`、`dataclasses`、`typing`、`urllib.parse`、`threading`、`multiprocessing`、`queue`、`pickle`、`atexit`、`math`、`codecs`、`importlib.util`
  - 第三方：`requests`、`urllib3`、`bs4`
  - 可选第三方：`playwright`（TYPE_CHECKING guard）、`playwright_stealth`（lazy import）
  - 当前仓库：`dayu.contracts.*`、`dayu.runtime.*`、`dayu.tools._legacy_adapter.*`、`dayu.documents.*`
  - 内部相对 import：`dayu.tools.web.web_*`
- 无 OLD `ToolRegistry`、`TruncationManager`、`fetch_more`、`/dayu/web` UI 导入。

### 2. OLD business function signatures/bodies 是否被不必要重写

**PASS。**

- `search_public_web` 签名与 OLD 一致，保留 `query`、`domains`、`recency_days`、`max_results`、`max_search_results`、`provider`、`request_timeout_seconds`、`timeout_budget`、`deadline_monotonic`、`allow_private_network_url`、`is_safe_public_url`、`normalize_whitespace`、`resolve_timeout_budget`。
- `register_web_tools` 签名与 OLD 一致，保留 `registry`、`provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir`、`timeout_budget`。
- `_is_safe_public_url`、`_normalize_url_for_http`、`_build_fetch_headers`、`_build_referer`、`_warmup_domain`、`_probe_content_type`、`_fetch_and_convert_content` 等核心业务函数签名和实现与 OLD 一致。
- 必要变更仅限：
  - import 路径适配（`dayu.engine.tools.web_*` → `dayu.tools.web.web_*`）
  - `ToolTruncateSpec` 从 OLD contract 改为当前 `dayu.contracts.tool_schema`
  - `ToolBusinessError` 从 OLD 直接使用改为子类吸收扩展参数
  - `CancellationToken` 从 OLD `raise_if_cancelled()` 改为当前 `is_cancelled()` 观察语义
  - `Log` 类从 OLD `dayu.log.Log` 改为本地窄适配器

### 3. Provider 是否只暴露 search_web / fetch_web_page，并正确解析 spec.config

**PASS。**

- `discover_tools` 接收 `ToolsDiscoveryProviderSpec`，返回 `ToolsDiscoveryProviderOutput`。
- `_parse_config` 从 `spec.config` 解析 `WebToolsConfig`，字段类型校验严格：
  - `provider`: 字符串，枚举 `{auto, tavily, serper, duckduckgo}`
  - `request_timeout_seconds`: 正浮点数
  - `max_search_results`: 正整数
  - `fetch_truncate_chars`: 正整数
  - `allow_private_network_url`: 布尔值，默认 `False`
  - `playwright_channel`: 可选字符串
  - `playwright_storage_state_dir`: 字符串
- `_validate_web_declarations` 校验声明集合恰好为 `("search_web", "fetch_web_page")`，且均声明 `web` tag。
- 测试 `test_web_provider_discovers_search_and_fetch` 验证发现结果。

### 4. Private/local URL 默认 fail-closed，非法 URL 类型在进入 Web 逻辑前失败

**PASS。**

- `WebToolsConfig.allow_private_network_url` 默认 `False`。
- `fetch_web_page` 在进入任何网络逻辑前调用 `_is_safe_public_url(url, allow_private_network_url=...)`。
- `_is_safe_public_url` 检查链：
  1. scheme 必须在 `{http, https}`
  2. hostname 非空
  3. `allow_private_network_url=True` 时直接放行（显式授权）
  4. 否则：拒绝 `_PRIVATE_HOST_PATTERNS`（localhost、127.*、0.0.0.0、::1）
  5. IP 地址：拒绝 private/loopback/link_local/reserved/multicast/unspecified
  6. 域名：DNS 解析后检查全部 IP；支持 fake-ip（198.18.0.0/15）对公开域名的放行
- 测试覆盖：
  - `test_fetch_private_url_fails_closed_by_default`：默认拒绝 `http://127.0.0.1/internal` → `ToolFailedOutcome(error="permission_denied")`
  - `test_fetch_private_url_can_be_allowed_with_explicit_config`：显式 `allow_private_network_url=True` 后放行
  - `test_invalid_fetch_url_type_fails_before_web_logic`：`url=["..."]` 列表类型 → `ToolFailedOutcome(error="invalid_argument")`，不进入抓取逻辑
- `search_web` 也通过 `_filter_visible_results` 过滤私网 URL 结果。

### 5. search optional 参数投影是否正确；返回 current outcome 且无 OLD ok/value nesting

**PASS。**

- `search_web` schema 声明 `domains`（array of string）、`recency_days`（integer, minimum 0）、`max_results`（integer, minimum 1）。
- 测试 `test_search_web_projects_optional_arguments_and_success` 验证：
  - `recency_days=7.0` → 投影为 `7`（int）
  - `max_results=3.0` → 投影为 `3`（int）
  - `domains=["sec.gov"]` → 保留
- 成功响应：`search_public_web` 返回 plain dict → adapter 包装为 `ToolCompletedOutcome(result=ToolResultSuccess(value=plain_dict))`。
  - 测试断言 `"ok" not in value`（无 OLD ok/value envelope）。
- 失败响应：
  - `ToolBusinessError` → `ToolFailedOutcome(error=code)`（由 `project_legacy_exception` 处理）
  - `RuntimeError("provider unavailable")` → `ToolFailedOutcome(error="execution_error")`（测试 `test_search_failure_projects_to_current_failed_outcome` 验证）
  - URL safety rejection → `ToolFailedOutcome(error="permission_denied")`
  - adapter validation failure → `ToolFailedOutcome(error="invalid_argument")`

### 6. ToolTruncateSpec 声明是否当前 contract

**PASS。**

- `search_web`：`ToolTruncateSpec(enabled=True, strategy=ToolTruncationStrategy.LIST_ITEMS, limits={"max_items": 10}, target_field="results", field_path=None, ttl_seconds=None)`
- `fetch_web_page`：`ToolTruncateSpec(enabled=True, strategy=ToolTruncationStrategy.TEXT_CHARS, limits={"max_chars": fetch_truncate_chars}, target_field="content", field_path=None, ttl_seconds=None)`
- 测试 `test_web_truncate_specs_use_current_contract` 验证 strategy、limits、target_field。
- `fetch_truncate_chars` 从 provider config 传入，测试用 `{"fetch_truncate_chars": 1234}` 验证 limits 为 `{"max_chars": 1234}`。
- 未迁移 OLD `TruncationManager`、OLD `fetch_more`、OLD truncate/fetch_more projection。

### 7. 测试是否 deterministic，无 live network；是否覆盖关键 failure/safety/import boundary

**PASS。**

- 测试文件 `tests/tools/web/test_web_tools_provider.py`：
  - 所有网络调用通过 `monkeypatch.setattr` mock
  - `search_public_web`、`_fetch_and_convert_content`、`_warmup_domain`、`_probe_content_type`、`_try_playwright_fallback` 均被 mock
  - 无 live HTTP 请求、无 DNS 解析、无 Playwright 浏览器启动
- 关键路径覆盖：
  - Provider 发现（`test_web_provider_discovers_search_and_fetch`）
  - 参数投影与成功响应（`test_search_web_projects_optional_arguments_and_success`）
  - 默认 fail-closed（`test_fetch_private_url_fails_closed_by_default`）
  - 显式放行（`test_fetch_private_url_can_be_allowed_with_explicit_config`）
  - 非法 URL 类型（`test_invalid_fetch_url_type_fails_before_web_logic`）
  - 搜索失败投影（`test_search_failure_projects_to_current_failed_outcome`）
  - TruncateSpec 声明（`test_web_truncate_specs_use_current_contract`）
  - Import 边界（`test_web_modules_do_not_import_old_registry_truncation_fetch_more_or_ui`）

### 8. AGENTS.md typing/docstring/import boundary/README 约束

**PASS。**

- **类型标注**: 全部函数签名有完整类型标注，无 `object`、`Any`（TYPE_CHECKING guard 下的 Playwright 类型除外）、无类型参数/返回值。
- **Docstring**: 全部函数/类有中文 docstring，含 Args/Returns/Raises。
- **Import 边界**: AST 测试验证无 forbidden import；`dayu.runtime` 不 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`。
- **README 同步**: 实现文档声明已更新 `dayu/config/README.md`（web-tools provider config）和 `tests/README.md`（Web provider 测试职责）。

---

## 残余风险

与实现文档一致：

1. **Provider 级串行执行**：共享 requests session 与 Playwright fallback 并发安全未在 S5 证明。后续如需并发，应先补并发安全证据。
2. **Web live network 行为**：S5 仅覆盖 deterministic mocked 路径。live network 行为需在后续集成测试中验证。
