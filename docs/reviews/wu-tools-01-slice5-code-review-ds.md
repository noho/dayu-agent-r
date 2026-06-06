# WU-TOOLS-01 Slice S5 Code Review — AgentDS

**审查对象**: 当前未提交变更（dayu/tools/web/、tests/tools/web/、dayu/config/README.md、tests/README.md）
**参考**: docs/host/design.md、docs/engine/design.md、docs/host/issues-implementation-control.md、docs/reviews/wu-tools-01-slice5-implementation-codex.md
**角色**: AgentDS，只做 review，不改代码

## 结论: PASS

无 blocking findings。7 条 non-blocking findings（3 medium, 4 low），均不构成正确性、安全性或迁移合规性障碍。

---

## 审查清单逐项确认

### 1. `dayu/tools/web/` 是否只迁移 Web tools

**PASS**。AST import 分析 (`test_web_modules_do_not_import_old_registry_truncation_fetch_more_or_ui`) 与人工 review 均确认：

- 未导入 OLD `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tools.fetch_more`、`dayu.web`
- 未导入 OLD `/dayu/web` UI（FastAPI/Streamlit）
- 未导入 OLD `TruncationManager`、OLD `fetch_more`
- 包根 `__init__.py` 只暴露 `discover_tools`

### 2. OLD business function signatures/bodies 是否被不必要重写

**PASS**。与 OLD 源文件逐函数对照确认（web_tools.py、web_search_providers.py、web_challenge_detection.py、web_fetch_orchestrator.py、web_http_encoding.py、web_http_session.py、web_playwright_backend.py、web_recovery.py）：

- 业务 pipeline（search provider selection、URL safety、requests/Playwright fallback、challenge detection、content encoding/decoding、warmup、content-type probe、HTML/Docling routing、meta refresh）均保持 OLD 实现语义
- 必要变更限于：import/package 适配、current `ToolTruncateSpec` 声明、current `CancellationToken` 语义（`is_cancelled()` 替代 OLD `raise_if_cancelled()`）、current `BatchToolExecutionContext` 注入、local `Log` adapter、`ToolBusinessError` 窄适配

### 3. Provider 是否只暴露 search_web / fetch_web_page，并正确解析 spec.config

**PASS**。`discover_tools()` 在 `provider.py:67-102` 中：

- 通过 `_parse_config` 解析 `WebToolsConfig`，字段覆盖 `provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir`
- `_validate_web_declarations` 确认两个工具名集合为 `("search_web", "fetch_web_page")` 且均有 `web` tag
- 配置解析有完整的类型校验（`_positive_float`/`_positive_int`/`_bool_default`/`_parse_provider`），非法类型 early fail

### 4. Private/local URL 默认 fail-closed

**PASS**。验证路径：

- `WebToolsConfig.allow_private_network_url` 默认 `False`（`provider.py:62`）
- `fetch_web_page` 入口处（`web_tools.py:1122`）调用 `_is_safe_public_url(url, allow_private_network_url=...)`
- `_is_safe_public_url` 当 `allow_private_network_url=False` 时：拒绝 `localhost`/`127.*`/`0.0.0.0`/`::1` pattern 匹配 → DNS 解析后拒绝 private/loopback/link-local/reserved/multicast/unspecified IP → fake-IP 网段仅对 "形似公开域名" 的主机名放行
- `allow_private_network_url=True` 直接返回 `True`（完全放行），符合显式允许语义
- 测试 `test_fetch_private_url_fails_closed_by_default` 确认默认拒绝，`test_fetch_private_url_can_be_allowed_with_explicit_config` 确认显式允许后放行

### 5. Search optional 参数投影与 current outcome 投影

**PASS**。

- 参数投影：`test_search_web_projects_optional_arguments_and_success` 确认 `recency_days=7.0` → `7` (int)、`max_results=3.0` → `3` (int)、`domains` 保持 `list[str]`
- 非法 URL 类型：`test_invalid_fetch_url_type_fails_before_web_logic` 确认 `url=["..."]` → `ToolFailedOutcome(error="invalid_argument")` 且未进入 Web 逻辑体
- 成功 outcome：plain dict 直接成为 `ToolCompletedOutcome.result.value`，不含 OLD `ok/value` envelope（`test_search_web_projects_optional_arguments_and_success` 断言 `"ok" not in value`；`test_fetch_private_url_can_be_allowed_with_explicit_config` 同样断言）
- 失败 outcome：`test_search_failure_projects_to_current_failed_outcome` 确认 `RuntimeError` → `ToolFailedOutcome(error="execution_error")`
- URL safety 拒绝 → `ToolFailedOutcome(error="permission_denied")`

### 6. ToolTruncateSpec 声明是否当前 contract

**PASS**。`test_web_truncate_specs_use_current_contract` 确认：

- `search_web`: `ToolTruncateSpec(enabled=True, strategy=LIST_ITEMS, limits={"max_items": 10}, target_field="results")`
- `fetch_web_page`: `ToolTruncateSpec(enabled=True, strategy=TEXT_CHARS, limits={"max_chars": 1234}, target_field="content")`（测试覆盖动态 `fetch_truncate_chars` 投影）
- 均不使用 OLD 截断声明格式；均不暴露 `fetch_more` business tool

### 7. 测试 deterministic / no live network

**PASS**。

- 所有 7 个测试通过 monkeypatch 控制搜索 provider (`search_public_web`)、requests 主路径 (`_warmup_domain`、`_probe_content_type`、`_fetch_and_convert_content`)、Playwright fallback (`_try_playwright_fallback`)
- `test_web_modules_do_not_import_old_registry_truncation_fetch_more_or_ui` 通过 AST 解析做静态 import 边界检查
- 无 live network 依赖
- 22 passed, 0 failures

### 8. AGENTS.md typing/docstring/import boundary/README 约束

**PASS**。

- pyright: 0 errors, 0 warnings, 0 informations
- 所有公开函数均有完整中文 docstring
- `dayu/config/README.md`: 补充了 web-tools provider 说明（enabled=false、default private URL fail-closed、config 字段、显式 allow 字段）
- `tests/README.md`: 补充了 web tools provider 测试职责与 deterministic mock / no live network 约定
- 无 typing escape（`Any` 出现处有合理理由：Playwright 类型不在运行时常驻、异常参数类型收窄、JSON 中间态）

---

## Findings

### F1 (Medium) — 未使用导入 `RECOVERY_CONTRACT_VERSION`

- **文件**: `dayu/tools/web/web_tools.py`, line 77
- **描述**: `RECOVERY_CONTRACT_VERSION` 从 `.web_recovery` 导入但未在 `web_tools.py` 中任何位置引用
- **影响**: 死代码；不影响功能正确性。增加一条无意义的 import 依赖
- **修复建议**: 从 import 中移除 `RECOVERY_CONTRACT_VERSION`

### F2 (Medium) — 死代码 `_close_response_safely` 包装函数

- **文件**: `dayu/tools/web/web_tools.py`, lines 469-480
- **描述**: 函数体仅委托到 `_web_fetch_orchestrator._close_response_safely(response)`，但该函数在 `web_tools.py` 和测试中均未被调用。所有实际关闭调用通过 `web_fetch_orchestrator.py` 内部的同名函数完成
- **影响**: 死代码；不影响功能正确性
- **修复建议**: 删除该包装函数，或确认是否有预期调用方尚未接入

### F3 (Medium) — Playwright fallback 取消信号在错误恢复路径的投影不精确

- **文件**: `dayu/tools/web/web_playwright_backend.py:62,268,843,872`；`dayu/tools/web/web_tools.py:541-590`
- **描述**: `web_playwright_backend.CancelledError(RuntimeError)` 通过 `_fetch_and_convert_with_playwright` (line 872: `except CancelledError: raise`) 向上传播到 `_try_playwright_fallback`，后者无专门的 `CancelledError` 捕获。当 `_try_playwright_fallback` 在错误恢复路径（`except requests.Timeout`/`except requests.RequestException`/`except RuntimeError` handler 内部）被调用且抛出 `CancelledError` 时，该异常绕过特定异常 handler，最终落入 adapter 的通用 `except Exception` → `ToolFailedOutcome(error="execution_error")`，丢失取消语义
- **可复现逻辑**: 在 `fetch_web_page` 执行到 `except requests.Timeout:` 分支(line 1232)时若取消令牌触发，`_try_playwright_fallback` → `_fetch_and_convert_with_playwright` → `_run_playwright_worker_process` 检测到取消 → 抛出 `CancelledError` → `_fetch_and_convert_with_playwright` re-raise → `_try_playwright_fallback` 不捕获 → 穿透到 adapter 的 `except Exception` → `error="execution_error"`
- **影响**: 取消时 LLM 收到通用执行错误而非明确的取消信号；不影响系统稳定性，但降低取消场景的诊断质量。触发条件为取消恰好在 Playwright fallback 执行期间到达，概率较低
- **修复建议**: 在 `_try_playwright_fallback` 或 `fetch_web_page` 的 `except RuntimeError` handler 中增加对 `CancelledError` 的识别；或让 `_fetch_and_convert_with_playwright` 在取消时返回 `{"ok": False, "availability": "cancelled", ...}` 而非抛出异常

### F4 (Low) — URL 安全校验中的同步 DNS 解析

- **文件**: `dayu/tools/web/web_tools.py`, lines 2077-2109 (`_resolve_hostname_ips`)
- **描述**: `_is_safe_public_url` 对非字面量 IP 的主机名执行同步 DNS 解析 (`socket.getaddrinfo`)，这是 OLD 行为的直接迁移。DNS 解析发生在工具执行的安全检查路径中，会引入网络延迟并产生 DNS 侧信道
- **影响**: 延迟与隐私影响与 OLD 一致；非本 slice 引入的新问题。在 `asyncio.to_thread` 中执行（adapter 将同步 callable 在线程池运行），不阻塞 event loop
- **修复建议**: 可作为后续 slice 的 DNS cache 优化点

### F5 (Low) — 三个 Log adapter 类方法集不一致

- **文件**: `web_tools.py:129-174` (Log.debug, Log.verbose)、`web_search_providers.py:27-55` (Log.warn)、`web_playwright_backend.py:76-121` (Log.debug, Log.warning)
- **描述**: 三个模块各自定义 `Log` adapter，方法集和调用风格不一致（`warn` vs `warning`、有的有 `verbose` 有的没有）
- **影响**: 仅日志标签一致性差异；不影响业务行为。每个 Log 类都是自包含的窄适配器，对应各模块的 OLD 日志调用模式
- **修复建议**: 无需在当前 slice 修复；可在后续统一为 `dayu.runtime` 的 logging helper

### F6 (Low) — 函数别名模式不一致

- **文件**: `dayu/tools/web/web_tools.py`, lines 485-491 vs lines 721-760
- **描述**: 部分 `web_fetch_orchestrator` 函数通过模块级变量别名暴露（如 `_build_fetch_content_runtime_context = _web_fetch_orchestrator._build_fetch_content_runtime_context`），另一部分通过 `_web_fetch_orchestrator.` 前缀直接调用（如 `_web_fetch_orchestrator._warmup_domain(...)`）
- **影响**: 纯代码组织风格差异；不影响正确性
- **修复建议**: 统一为一种模式（建议全部通过模块引用调用，减少别名维护负担）

### F7 (Low) — 取消检查逻辑重复

- **文件**: `web_tools.py:533-538` (`_raise_if_tool_cancelled`)、`web_fetch_orchestrator.py:121-136` (`_raise_if_cancelled`)
- **描述**: 两个模块各自定义了功能完全相同的取消检查函数（检查 `cancellation_token.is_cancelled()` 后抛出 `RuntimeError`）
- **影响**: 维护负担（两处需要同步修改）；当前实现一致，无行为差异
- **修复建议**: 提取为 `dayu.tools.web` 包内共享 helper，或在 `web_fetch_orchestrator` 中定义并让 `web_tools` import

---

## 验证记录

| 检查项 | 结果 |
|--------|------|
| `pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py` | 22 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| OLD registry/truncation/fetch_more/UI import AST scan | 未发现违规 |
| `search_web` / `fetch_web_page` 参数投影 | 正确 |
| Private/local URL fail-closed | 默认拒绝，显式 allow 放行 |
| Current `ToolTruncateSpec` 声明 | 仅使用 current contract |
| Current outcome 投影 (no OLD ok/value) | 正确 |
| README 同步 | dayu/config/README.md, tests/README.md 已更新 |
| 迁移原则遵守 | 无 OLD business logic 重写 |

## 未覆盖风险

- **Playwright live network 行为**: S5 仅验证 deterministic mock 路径；Playwright + 真实浏览器 + 反爬站点的交互未在本 slice 验证
- **Provider 级串行并发安全**: SERIAL_PER_PROVIDER 是显式 policy，共享 requests session 与 Playwright fallback 的并发安全性未在 S5 证明
- **搜索 provider API key 真实调用**: Tavily/Serper API 调用仅在 mock 中覆盖；真实 API 响应格式变更、rate limit、认证失败场景未覆盖
