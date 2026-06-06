# WU-TOOLS-01 Slice S5 Re-review — AgentDS

**审查对象**: Controller accepted findings A1-A4 的 fix，以及是否引入新 blocking regression。
**参考**:
- docs/reviews/wu-tools-01-slice5-code-review-ds.md（原 DS review，7 findings）
- docs/reviews/wu-tools-01-slice5-code-review-mimo.md（MiMo review，4 observations）
- docs/reviews/wu-tools-01-slice5-fix-codex.md（Codex fix artifact）
- docs/reviews/wu-tools-01-slice5-implementation-codex.md（原实现文档）
**角色**: AgentDS，只做 re-review，不改代码、不 commit、不 push、不 PR。

## 结论: PASS

4 项 accepted findings 均充分修复。无新 blocking regression。无 typing escape、无 live network leakage、无 README/artifact 与代码事实不一致。

---

## 逐项复核

### A1 — 生产代码 Any/object 类型签名与 import

**PASS。**

- `rg -n "\bAny\b|\bobject\b" dayu/tools/web/ --include '*.py'` 结果：仅 2 处，均为 JSON schema 字面量 `"type": "object"`：
  - `web_tools.py:1025` — `search_web` tool schema
  - `web_tools.py:1140` — `fetch_web_page` tool schema
- 零 `typing.Any` import、零 `: Any` / `-> Any` 类型签名。
- 类型收窄方法验证：
  - `Protocol`：`web_playwright_backend.py` 中 17 个 Protocol（_ResultQueueProtocol, _RouteProtocol, _PageProtocol, _BrowserProtocol, _ChromiumProtocol, _PlaywrightInstanceProtocol 等），全部用于 Playwright 可选依赖的边界隔离；属于合理的最小 Protocol。
  - `web_search_providers.py` 中 2 个 Protocol（_TimeoutBudgetResolver, _PublicUrlSafetyChecker）用于 callback 注入。
  - `JsonValue` / `Mapping[str, JsonValue]`：`provider.py` config 解析、`web_tools.py` WebPayload/WebMapping TypeAlias 使用 `dayu.contracts.json_value.JsonValue`，标准 JSON 边界。
  - `TypedDict`：`_FetchContentResult`（web_tools.py:134-149）、`_PlaywrightFallbackKwargs`（web_tools.py:152-161）用于内部窄结构。
  - `cast()`：全部在外部库边界（`json.load` → `JsonValue`、`sync_playwright()` → Protocol、`multiprocessing.Queue` → Protocol、browser type 收窄），无不合理 escape。

### A2 — 未使用 RECOVERY_CONTRACT_VERSION import

**PASS。**

- `web_tools.py` `from .web_recovery import (...)` 块（lines 78-91）已移除 `RECOVERY_CONTRACT_VERSION`。
- `RECOVERY_CONTRACT_VERSION` 仅在其定义处 `web_recovery.py:11` 存在，不再通过 import 泄漏到 `web_tools.py`。

### A3 — 死包装函数 _close_response_safely

**PASS。**

- `web_tools.py` 中已无 `_close_response_safely` 定义或引用。
- 真实 close 逻辑保留在 `web_fetch_orchestrator.py:139`（定义）和 `web_fetch_orchestrator.py:839`（调用），不影响功能。

### A4 — Playwright fallback 取消投影

**PASS。**

- 投影链路验证：
  1. `_raise_fetch_cancelled`（web_tools.py:478-499）：当 cancellation_token 触发时，抛出 `ToolBusinessError(code="tool_cancelled", message=..., hint="[continue_without_web]...", next_action=NEXT_ACTION_CONTINUE_WITHOUT_WEB)`
  2. `_raise_if_tool_cancelled`（web_tools.py:601-606）：在 fetch 各阶段的协作式检查点调用 `_raise_fetch_cancelled`。插入点：warmup 前（line 1235）、content-type probe 前（line 1253）、fetch 前（line 1271）、URL safety 后（line 1189）。
  3. `_try_playwright_fallback`（web_tools.py:649-650）：捕获 `_web_playwright_backend.CancelledError` → 调用 `_raise_fetch_cancelled`。
  4. Adapter 投影（definition_adapter.py:374-379）：`project_legacy_exception` 检查 `isinstance(error, ToolBusinessError)` → `error.code` 映射为 `ToolFailedOutcome(error=code)`。
  5. 结果：`ToolBusinessError(code="tool_cancelled")` → `ToolFailedOutcome(error="tool_cancelled")`。
- 测试 `test_fetch_playwright_cancel_projects_to_cancelled_failure`（test_web_tools_provider.py:206-268）：
  - monkeypatch `_warmup_domain` 返回 `{"ok": False}`（触发 escalation）
  - monkeypatch `_should_escalate_stage_result_to_browser` 返回 `True`（进入 Playwright fallback）
  - monkeypatch `_fetch_and_convert_with_playwright` 抛出 `web_playwright_backend.CancelledError("cancelled by host")`
  - 断言 `isinstance(outcome, ToolFailedOutcome)` — PASS
  - 断言 `outcome.result.error == "tool_cancelled"` — PASS
  - 断言 hint 包含 `"continue_without_web"` — PASS
  - **无 live network**：全部 external call 通过 monkeypatch 替换。

---

## 新增回归检查

### hasattr 使用

**PASS。** `dayu/tools/web/` 全量搜索 `hasattr` — 零使用。

### getattr 使用

**PASS。** 全部 fall into fix artifact 已声明的合理场景：

| 文件 | getattr 用途 | 判定 |
|------|-------------|------|
| `web_http_encoding.py:205-255` | response headers/content/encoding/text | 编码 helper 兼容 requests response 与测试桩 |
| `web_http_session.py:77` | session.max_redirects copy | 复制 requests Session 配置 |
| `web_fetch_orchestrator.py:152-876` | response close/status/url/headers、session warmed_hosts 标记 | OLD 抓取编排对 requests response 与 test stub 的容错 |
| `web_tools.py:427-431` | 异常链 `__cause__/__context__/reason/args` | 跨库异常结构展开 |
| `web_tools.py:1287,1319` | requests exc.response | 非所有子类携带 response，安全提取诊断上下文 |

无新增不适当地址 escape。

### cast 使用

**PASS。** 全部位于外部库边界，无不合理用途：

- `web_playwright_backend.py:505` — `multiprocessing.Queue` → Protocol
- `web_playwright_backend.py:547` — 内部 payload dict → WebPayload
- `web_playwright_backend.py:695` — `sync_playwright().start()` → Protocol
- `web_playwright_backend.py:1130` — response headers Mapping 类型收窄
- `web_tools.py:336` — `json.load()` → JsonValue
- `web_tools.py:1267` — content_type_probe StagePayload 收窄
- `web_tools.py:1560,1654,1932` — 内部组装点的类型辅助

### 业务逻辑重写检查

**PASS。** 本次 fix 仅涉及：
- 删除 dead import / dead wrapper
- 类型签名收窄（Any → Protocol/JsonValue/TypedDict）
- 取消投影路径补充（_raise_fetch_cancelled + 适配点）

未触及 search provider selection、URL safety、requests/Playwright fallback、challenge detection、content encoding/decoding 等核心业务逻辑。

### README 同步

**PASS。**
- `dayu/config/README.md:179` — web-tools provider 说明：enabled=false、默认 private URL fail-closed、config 字段、显式 allow 字段。与代码实现一致。
- `tests/README.md:137-141` — Web tools provider 测试职责与 deterministic mock / no live network 约定。与测试实现一致。

---

## 验证记录

| 检查项 | 方法 | 结果 |
|--------|------|------|
| `rg "\bAny\b|\bobject\b" dayu/tools/web/` | Grep | 仅 JSON schema `"type": "object"` x2 |
| `source .venv/bin/activate && pyright` | Bash | 0 errors, 0 warnings, 0 informations |
| `pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py -q` | Bash | 23 passed (含 1 新增取消投影测试) |
| `git diff --check` | Bash | clean |
| `rg "hasattr" dayu/tools/web/` | Grep | 0 |
| `rg "typing\.Any\|: Any\|-> Any" dayu/tools/web/` | Grep | 0 |
| `rg "RECOVERY_CONTRACT_VERSION" dayu/tools/web/web_tools.py` | Grep | 0 (已从 import 移除) |
| `rg "_close_response_safely" dayu/tools/web/web_tools.py` | Grep | 0 (已删除) |
| LIVE NETWORK in 取消测试 | 人工 review monkeypatch 覆盖 | 无 — 全部 deterministic |
| README vs 代码事实 | 人工对照 | 一致 |

---

## 残余风险（与原 DS review 一致，非本次 fix 引入）

1. **Playwright live network 行为**: S5 仅验证 mock 路径；真实浏览器 + 反爬站点交互未覆盖。
2. **Provider 级串行并发安全**: `SERIAL_PER_PROVIDER` 是显式保守 policy，共享 session 与 Playwright fallback 的并发安全未证明。
3. **搜索 provider API key 真实调用**: Tavily/Serper API 仅在 mock 中覆盖。
