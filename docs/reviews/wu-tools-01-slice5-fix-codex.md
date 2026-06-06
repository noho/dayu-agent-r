# WU-TOOLS-01 Slice S5 Fix Artifact - Codex

## 范围

- 本轮只处理 Controller accepted findings A1-A4。
- 未迁移 OLD UI、OLD ToolRegistry、OLD TruncationManager、OLD fetch_more、OLD truncate/fetch_more projection。
- 未重写 Web business logic；改动集中在类型边界、adapter 取消投影、测试与本文档。

## Fix 结果

### A1 - dayu/tools/web 生产代码 Any/object

- 已移除 `dayu/tools/web` 生产代码中的 `typing.Any` import 与类型签名使用。
- JSON payload 边界改为 `JsonValue`、`Mapping[str, JsonValue]`、`dict[str, JsonValue]`、`TypedDict` 与 `TypeAlias`。
- Playwright、队列、浏览器对象、页面对象、Route、Response、HTML converter、challenge detector 改为最小 `Protocol`。
- `_fetch_and_convert_content` 内部结果包含 `requests.Response`，已用专门 `_FetchContentResult` 表达；对外成功/失败投影仍只返回 JSON 兼容字段。
- 当前 `rg -n "\bAny\b|\bobject\b" dayu/tools/web` 只剩两个 JSON schema 字面量 `"object"`。

### A2 - 未使用 RECOVERY_CONTRACT_VERSION

- 已从 `dayu/tools/web/web_tools.py` 删除未使用的 `RECOVERY_CONTRACT_VERSION` import。

### A3 - 死包装函数

- 已删除 `dayu/tools/web/web_tools.py` 中未调用的 `_close_response_safely` 死包装函数。
- `dayu/tools/web/web_fetch_orchestrator.py` 内部真实 close 逻辑保持不变。

### A4 - Playwright fallback 取消投影

- 已在 `web_tools.py` 增加 `_raise_fetch_cancelled`，将工具取消投影为 `ToolBusinessError(code="tool_cancelled")`。
- `_raise_if_tool_cancelled` 与 `_try_playwright_fallback` 现在把取消交给现有 legacy adapter 投影为 current `ToolFailedOutcome`，不再落入通用 `execution_error`。
- 已新增 deterministic 测试：mock warmup escalation 与 Playwright fallback，模拟 `_web_playwright_backend.CancelledError`，断言 outcome 为 `ToolFailedOutcome(error="tool_cancelled")`。
- Residual: 未发现需要更大 ToolRuntime/adapter contract 设计的取消投影残留。

## getattr/hasattr 分类

- `hasattr`: `dayu/tools/web` 已无剩余使用。
- `web_tools.py` 异常链 `getattr(__cause__/__context__/reason/args)`: 用于展开 requests/urllib3 嵌套异常链；这是异常对象跨库结构的显式边界收窄。
- `web_tools.py` requests exception `getattr(exc, "response", None)`: requests 异常并非所有子类都携带 response；用于在错误投影前安全提取诊断上下文。
- `web_http_encoding.py` response `getattr(headers/content/apparent_encoding/encoding/text)`: 编码 helper 需要兼容 requests response 与测试桩；读取后立即按 bytes/string/header 语义归一化。
- `web_http_session.py` `getattr(source_session, "max_redirects", ...)`: 复制 requests Session 配置；测试桩或定制 session 可能缺少该属性。
- `web_fetch_orchestrator.py` response/session `getattr`: 保留 OLD 抓取编排对 requests response 与 deterministic test stub 的容错；涉及 close/status/url/headers/content encoding/meta refresh Referer 与 session warmed-host 私有标记。

## 验证

- `source .venv/bin/activate && pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py`
- `source .venv/bin/activate && pyright`
- `rg -n "\bAny\b|\bobject\b" dayu/tools/web`
- `git diff --check`

当前结果：23 tests passed；pyright 0 errors, 0 warnings, 0 informations；`rg` 只剩 JSON schema 字面量 `"object"`；`git diff --check` 通过。
