# WU-TOOLS-01 Slice S5 Re-Review — AgentMiMo

**审查对象**: Controller accepted findings A1-A4 的 fix
**参考**: docs/reviews/wu-tools-01-slice5-fix-codex.md、docs/reviews/wu-tools-01-slice5-code-review-mimo.md、docs/reviews/wu-tools-01-slice5-code-review-ds.md、docs/reviews/wu-tools-01-slice5-implementation-codex.md
**角色**: AgentMiMo，只做 re-review，不改代码、不 commit、不 push、不 PR

## 结论: PASS

A1-A4 fix 充分，未引入新 blocking regression。

---

## 逐项验证

### A1 BLOCKING: dayu/tools/web 生产代码不得有 Any/object 类型签名或 import；只允许 JSON schema 字面量 "object"

**PASS。**

验证手段：`rg -n "\bAny\b|\bobject\b" dayu/tools/web`

结果仅 2 处命中：
- `dayu/tools/web/web_tools.py:1025` — `"type": "object"` (search_web JSON schema)
- `dayu/tools/web/web_tools.py:1140` — `"type": "object"` (fetch_web_page JSON schema)

均为 JSON schema 字面量字符串，不是 Python 类型注解。

类型收窄策略合理：
- `JsonValue`（`dayu/contracts/json_value.py`）作为 JSON 边界联合类型，覆盖 `None | bool | int | float | str | list[JsonValue] | Mapping[str, JsonValue]`。
- `WebPayload: TypeAlias = dict[str, JsonValue]`、`WebMapping: TypeAlias = Mapping[str, JsonValue]` 收窄 JSON object。
- `_FetchContentResult(TypedDict, total=False)` 表达 requests 抓取内部结果的窄结构。
- `StagePayload`、`ContentProbePayload` 使用具体字面量联合 `str | bool | int | float | None`。
- Playwright 对象通过 18 个 `Protocol` 类（`_PageProtocol`、`_BrowserProtocol`、`_PlaywrightResponseProtocol` 等）在 `TYPE_CHECKING` guard 下表达。
- `typing` import 仅使用 `NoReturn`、`Optional`、`TypeAlias`、`TypedDict`、`cast`，无 `Any`、无 `object` 类型注解。

`getattr` 使用均为合理边界收窄，非 typing escape：
- `web_tools.py:427-431`：异常链遍历 `__cause__`/`__context__`/`reason`/`args`，跨库异常结构的显式边界。
- `web_tools.py:1287,1319`：`getattr(exc, "response", None)` — requests 异常子类非全部携带 response。
- `web_http_encoding.py`：response 属性读取兼容 requests response 与测试桩。
- `web_http_session.py:77`：`getattr(source_session, "max_redirects", ...)` — 复制 session 配置。
- `web_fetch_orchestrator.py`：response/session 属性读取保留 OLD 抓取编排对 requests response 与 deterministic test stub 的容错。

无 `hasattr` 使用（`dayu/tools/web` 范围内已清零）。

### A2: 删除未用 RECOVERY_CONTRACT_VERSION import

**PASS。**

验证手段：`grep RECOVERY_CONTRACT_VERSION dayu/tools/web/`

结果仅 `dayu/tools/web/web_recovery.py:11`（定义处）。`web_tools.py` 已不再 import 该符号。

### A3: 删除 _close_response_safely 死包装

**PASS。**

验证手段：`grep _close_response_safely dayu/tools/web/`

结果仅 `dayu/tools/web/web_fetch_orchestrator.py:139`（定义）和 `web_fetch_orchestrator.py:839`（内部调用）。`web_tools.py` 中已无该包装函数。真实 close 逻辑不受影响。

### A4: Playwright fallback 取消投影

**PASS。**

Fix 实现路径：
1. `_try_playwright_fallback`（`web_tools.py:638-650`）catch `_web_playwright_backend.CancelledError`，调用 `_raise_fetch_cancelled(cancellation_token)`。
2. `_raise_fetch_cancelled`（`web_tools.py:478-499`）抛出 `ToolBusinessError(code="tool_cancelled", ...)`，含 `hint="[continue_without_web] ..."`。
3. Legacy adapter 的 `project_legacy_exception` 将 `ToolBusinessError` 投影为 `ToolFailedOutcome(error="tool_cancelled")`。

测试验证（`test_fetch_playwright_cancel_projects_to_cancelled_failure`，`test_web_tools_provider.py:206-268`）：
- monkeypatch `_warmup_domain` → `{"ok": False}` 触发 Playwright escalation。
- monkeypatch `_should_escalate_stage_result_to_browser` → `True`。
- monkeypatch `_fetch_and_convert_with_playwright` → raise `web_playwright_backend.CancelledError("cancelled by host")`。
- 断言：`ToolFailedOutcome(error="tool_cancelled")`，且 `hint` 包含 `"continue_without_web"`。
- 全部 mock，无 live network，无 DNS，无 Playwright 浏览器启动。**Deterministic。**

---

## 新 blocking regression 检查

### pyright / tests / diff check

| 检查项 | 结果 |
|--------|------|
| `pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py` | 23 passed (0.58s) |
| `pyright dayu/tools/web/` | 0 errors, 0 warnings, 0 informations |
| `rg -n "\bAny\b|\bobject\b" dayu/tools/web` | 仅 2 处 JSON schema `"type": "object"` |
| `git diff --check` | 通过，无 whitespace error |

### 测试覆盖增量

fix 新增 1 个测试（从 22 → 23 passed）：
- `test_fetch_playwright_cancel_projects_to_cancelled_failure`：覆盖 A4 取消投影路径。

### README / artifact 一致性

- `dayu/config/README.md:179`：web-tools provider 说明与代码一致（`enabled=false`、default private URL fail-closed、config 字段、显式 allow 字段）。
- `tests/README.md:137-141`：Web provider 测试职责与 deterministic mock / no live network 约定与实际测试一致。
- `docs/reviews/wu-tools-01-slice5-fix-codex.md`：验证记录（23 tests passed、pyright 0、rg 只剩 JSON schema 字面量、git diff --check 通过）与本次独立验证结果完全一致。

---

## 残余风险（与原 review 一致，无新增）

1. **Provider 级串行执行**：共享 requests session 与 Playwright fallback 并发安全未在 S5 证明。后续如需并发，应先补并发安全证据。
2. **Web live network 行为**：S5 仅覆盖 deterministic mocked 路径。live network 行为需在后续集成测试中验证。
