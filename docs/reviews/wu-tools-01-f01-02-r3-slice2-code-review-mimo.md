# WU-TOOLS-01-F01-02-R3 Slice 2 Code Review — MiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice2-code-review-mimo.md`
- Included scope: `dayu/tools/web/provider.py`, `dayu/tools/web/web_tools.py`, `dayu/tools/web/web_search_providers.py`, `tests/tools/web/test_web_tools_provider.py`, `docs/host/issues-implementation-control.md`
- Excluded scope: Doc / Fins / Host / Engine / Service / ToolRuntime / `dayu/tools/_legacy_adapter/` 目录（未删除，符合 plan Slice 4 约定）
- Parallel review coverage: 无

## 结论

**pass-with-findings**

## Findings

### 001-未修复-低-`_try_playwright_fallback` docstring 隐瞒取消异常

- **入口/函数**: `_try_playwright_fallback`
- **文件(行号)**: `dayu/tools/web/web_tools.py:660-676`
- **输入场景**: Playwright 浏览器回退期间 Host 发起取消
- **实际分支**: `_web_playwright_backend.CancelledError` 被捕获后调用 `_raise_fetch_cancelled(cancellation_token)`，抛出 `WebToolCancelledError`
- **预期行为**: docstring 应记录 cancellation exception 作为 raised 类型
- **实际行为**: docstring 写 `Raises: 无。`，但第 689-690 行明确捕获 `CancelledError` 并调用 `_raise_fetch_cancelled`，后者抛出 `WebToolCancelledError`（第 543 行）
- **直接证据**: `web_tools.py:689` — `except _web_playwright_backend.CancelledError:`; `web_tools.py:690` — `_raise_fetch_cancelled(cancellation_token)`; `web_tools.py:543` — `raise WebToolCancelledError(...)`
- **影响**: 维护者可能误认为该函数不会抛异常而遗漏上游 catch 处理。当前 `_call_fetch_web_page:1247` 有正确 catch，不影响运行时行为。
- **建议改法**: 将 docstring Raises 改为 `WebToolCancelledError: Playwright 取消时抛出。` 或改为 `无（取消信号由上游 callable 边界捕获）。` 并注明 catch 在 `_call_fetch_web_page`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-中-search_web provider 失败语义压平为 execution_error

- **入口/函数**: `_call_search_web` / `_search_web_business`
- **文件(行号)**: `dayu/tools/web/web_tools.py:1170-1175`
- **输入场景**: 所有搜索 provider 均失败（`search_public_web` 抛出 `RuntimeError`）
- **实际分支**: `except Exception as exc:` → `_unexpected_failed_outcome(error="execution_error")`
- **预期行为**: 按 plan "搜索 provider 业务失败保持现有 LLM-readable message / hint"，失败应携带可区分的错误码
- **实际行为**: `RuntimeError("All search providers failed")` 被压平为 `error="execution_error"`，丢失 provider 语义。对比 `fetch_web_page` 有专用 `except ToolBusinessError` 分支保留 `exc.code`（第 1255 行）
- **直接证据**: `web_tools.py:1170` — `except Exception as exc:` 统一捕获; `web_tools.py:951` 测试断言 `outcome.result.error == "execution_error"`; 旧 adapter 对 `RuntimeError` 投影为 `ToolFailedOutcome(error="tool_failed")`
- **影响**: LLM 无法区分"搜索 provider 不可用"和"内部执行异常"。当前 `search_web` 无 `ToolBusinessError` 路径，但 `fetch_web_page` 有，形成不对称。不影响取消行为。
- **建议改法**: 在 `_search_web_business` 中将 `RuntimeError` 映射为 `ToolBusinessFailure(error="search_failed", ...)` 并在 `_call_search_web` 增加 `except ToolBusinessFailure` 分支；或接受 `execution_error` 为当前语义并记录 decision。关键在于对称性：`fetch_web_page` 保留业务错误码，`search_web` 也应如此。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 003-未修复-低-provider.py __all__ 重导出已迁移的 WebToolsConfig

- **入口/函数**: `provider.py` module-level `__all__`
- **文件(行号)**: `dayu/tools/web/provider.py:315`
- **输入场景**: 外部模块 `from dayu.tools.web.provider import WebToolsConfig`
- **实际分支**: `__all__ = ["WebToolsConfig", "discover_tools"]`
- **预期行为**: 按 AGENTS.md "兼容性 re-export：仅为保持旧导入路径而转发符号"应避免
- **实际行为**: `WebToolsConfig` 真源已迁至 `web_tools.py`；`provider.py` 仅因 `_parse_config` 使用而 import，但 `__all__` 暴露为公共符号，构成第二导入路径
- **直接证据**: `provider.py:22` — `from .web_tools import WebToolsConfig, build_web_tool_definitions`; `provider.py:315` — `__all__ = ["WebToolsConfig", "discover_tools"]`; 全仓搜索无外部消费者从 `provider` 导入 `WebToolsConfig`
- **影响**: 极低。当前无外部消费者；但保留第二路径可能诱导未来开发者从 `provider` 导入而非 `web_tools`。
- **建议改法**: 将 `__all__` 收窄为 `["discover_tools"]`，保留 import 仅供内部 `_parse_config` 使用。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 已验证通过项

以下要求经代码走读和 diff 审查确认通过：

1. **越界约束**: Web provider / web_tools / web_search_providers / Web tests 是唯一变更的生产/测试文件；Doc / Fins / Host / Engine / Service / ToolRuntime 未被修改。
2. **legacy adapter 依赖消除**: `rg "_legacy_adapter|LegacyToolDeclarationCollector|LegacySyncToolCallable|adapt_collected_tools" dayu/tools/web tests/tools/web/test_web_tools_provider.py` 无命中。
3. **工具名 / LLM-facing schema 保持**: `search_web`、`fetch_web_page` 名称不变；参数字段、required、display name、tags 均保持。
4. **truncate spec 保持**: search `LIST_ITEMS / max_items=10 / target_field=results`，fetch `TEXT_CHARS / max_chars=config.fetch_truncate_chars / target_field=content`。
5. **返回 shape 保持**: success 返回原 `WebPayload` 字典（`url/final_url/title/content/fetch_backend`），无 `ok` envelope。
6. **provider config 投影**: 7 个配置字段全部通过 `WebToolsConfig` 闭包投影给 callable。
7. **private URL policy**: 默认拒绝，`allow_private_network_url=True` 后允许。测试覆盖。
8. **requests / docling / Playwright fallback 行为**: `_fetch_web_page_business` 保持原有 fallback 链：warmup → content probe → fetch → 各阶段 Playwright fallback → challenge detection → empty content 检查。
9. **Host cancellation token 投影 `ToolCancelledOutcome(host_cancelled)`**:
   - pre-cancel（`_call_search_web:1120`、`_call_fetch_web_page:1216`）
   - provider attempt 间 cancel（`async with provider_lock` 内第 1142/1230 行）
   - Playwright cancel（`_try_playwright_fallback:689-690` → `_raise_fetch_cancelled` → `WebToolCancelledError` → `host_cancelled_outcome`）
   - 测试覆盖：`test_search_web_cancelled_before_provider_returns_host_cancelled`、`test_search_web_cancelled_between_provider_attempts_stops_fallback`、`test_fetch_playwright_cancel_projects_to_host_cancelled`
10. **普通失败仍为 `ToolFailedOutcome`**: `ToolBusinessError` → `failed_outcome(error=exc.code)`；参数错误 → `failed_outcome(error="invalid_argument")`；未预期异常 → `failed_outcome(error="execution_error")`。
11. **共享 lock**: `build_web_tool_definitions` 创建一把 `provider_lock`，`search_web` 和 `fetch_web_page` 闭包共享。测试 `test_web_provider_serializes_search_and_fetch_business` 覆盖并发序列化。
12. **`_try_playwright_fallback` docstring**: 已在 Finding 001 记录。

## Open Questions

- 无阻塞性问题。

## Residual Risk

- Finding 002 的 `search_web` 失败语义是否需要对齐 `fetch_web_page` 的错误码保留行为，需由 controller 裁决。
- Web live smoke（真实网络搜索 provider fallback、Playwright browser 启动后取消、真实页面 fetch truncate）未在本 slice 运行；owner 为现有 Web CI diagnostics / smoke follow-up。
- Tavily / Serper provider success 路径未验证（API keys 未配置）；owner 为 provider-configured Web CI environment。
- Legacy adapter 目录删除留待 Slice 4。
