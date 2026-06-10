# WU-TOOLS-01-F01-02-R3 Slice 2 Re-Review (DS)

## Scope

- Mode: current changes re-review
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: original Slice 2 code review adjudication + Codex fix
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice2-rereview-ds.md`
- Review target: accepted findings `S2-CR-01` through `S2-CR-04` only
- Explicitly excluded: Tavily/Serper credentials, real network smoke, legacy adapter deletion

## Pre-Verification

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py`: 17 passed
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings
- `git diff --check`: passed

## Findings Review

### S2-CR-01: `search_web` Provider Failure Is Over-Flattened To `execution_error`

**Verdict: ✅ 已修复，无残留问题。**

入口/证据链：

1. `WebSearchProviderUnavailableError` 定义于 `dayu/tools/web/web_search_providers.py:107-124`，继承 `RuntimeError`，携带 `message` 属性。

2. `search_public_web()` 在 `web_search_providers.py:232-303` 的 provider 候选循环中，每个 candidate 失败时通过 `except Exception` 分支（line 270）记录日志后 `continue`。取消异常（`WebSearchCancelledError`）通过 `_is_search_cancelled_error` 判断后 `raise` 正确传播。当全部 provider 耗尽时，line 303 抛出 `WebSearchProviderUnavailableError(_ALL_PROVIDERS_UNAVAILABLE_MESSAGE)`，消息为 `"联网检索失败：所有 provider 均不可用"`。

3. `_call_search_web()` 在 `web_tools.py:1099-1201` 中按以下优先级捕获异常：
   - `WebSearchCancelledError`（line 1172）→ `host_cancelled_outcome` ✓
   - `WebSearchProviderUnavailableError`（line 1180）→ `failed_outcome(error="search_provider_unavailable")` ✓
   - `Exception`（line 1189）→ `_unexpected_failed_outcome` → `failed_outcome(error="execution_error")` ✓

4. 业务错误码常量 `_SEARCH_PROVIDER_UNAVAILABLE_ERROR = "search_provider_unavailable"` 定义于 `web_tools.py:153`。

5. 恢复提示 `_SEARCH_PROVIDER_UNAVAILABLE_HINT`（`web_tools.py:154-157`）为非空、LLM-readable 文本：`"[retry_later_or_use_known_source] Search providers are currently unavailable; retry later, refine the query, or continue with a known source URL."`。该 hint 通过 `failed_outcome(hint=...)` 传入 outcome（line 1185），不是空字符串也不是 `None`。

6. `_unexpected_failed_outcome`（`web_tools.py:1367-1390`）对所有未知异常仍投影为 `execution_error`，hint 为 `None`。provider 耗尽路径不会误走此分支。

7. 测试 `test_search_provider_unavailable_projects_to_stable_business_failure`（`test_web_tools_provider.py:930-989`）：
   - 通过 monkeypatch 使 Tavily、Serper、DuckDuckGo 三个 provider 全部失败
   - 注入 fake API key 以确保 `auto` 候选顺序包含全部三个
   - 断言 `outcome.result.error == "search_provider_unavailable"`
   - 断言 `outcome.result.hint is not None` 且非空
   - 断言 `attempted_providers == ["tavily", "serper", "duckduckgo"]`，确认走完真实 provider fallback 路径

**结论**：`search_provider_unavailable` 仅用于 provider 全部耗尽场景；未知异常仍走 `execution_error`；hint 非空且 LLM-readable；测试覆盖完整。无残留问题。

---

### S2-CR-02: `_try_playwright_fallback` Docstring Hides Cancellation Raise

**Verdict: ✅ 已修复，无残留问题。**

入口/证据：

`_try_playwright_fallback` 函数定义于 `web_tools.py:659-709`。docstring 中 Raises 段（lines 684-685）现在正确声明：

```
Raises:
    WebToolCancelledError: Playwright 执行期间 Host 取消时抛出。
```

实际行为在 `web_tools.py:699-700`：catch `_web_playwright_backend.CancelledError` 后调用 `_raise_fetch_cancelled(cancellation_token)`，该方法（`web_tools.py:537-559`）始终抛出 `WebToolCancelledError`。docstring 与行为一致。

**结论**：docstring 已更新，无残留问题。

---

### S2-CR-03: `provider.py.__all__` Re-exports `WebToolsConfig`

**Verdict: ✅ 已修复，无残留问题。**

入口/证据：

1. `WebToolsConfig` 的正确定义位置在 `dayu/tools/web/web_tools.py:167-188`（`@dataclass(frozen=True, slots=True)`）。

2. `provider.py:22` 通过局部 import `from .web_tools import WebToolsConfig, build_web_tool_definitions` 引用该类型，仅用于 `_parse_config` 内部构造（`provider.py:74-108`）。

3. `provider.py:315` 的 `__all__` 为 `["discover_tools"]`，不再包含 `WebToolsConfig`。

4. 外部调用方如需 `WebToolsConfig` 类型，应直接 `from dayu.tools.web.web_tools import WebToolsConfig`，不再有第二条 public export 路径。

**结论**：兼容性 re-export 已移除，符合 AGENTS.md 编码硬约束。无残留问题。

---

### S2-CR-04: Web Provider Lock Test Has A Timing-Weak Mid-Assertion

**Verdict: ✅ 已修复，无残留问题。**

入口/证据：

测试 `test_web_provider_serializes_search_and_fetch_business`（`test_web_tools_provider.py:1009-1141`）。

修复后的测试使用两层确定性协调：

1. **事件协调替代任意 sleep**：
   - `first_to_thread_entered`（`asyncio.Event`）：第一个 `fake_to_thread` 调用进入时 set
   - `release_first_to_thread`（`asyncio.Event`）：主测试控制释放时机
   - 搜索 task 的 `fake_to_thread` 在进入后等待 `release_first_to_thread`，确保 fetch task 只能在搜索 task 被显式释放后才可能进入

2. **业务体重叠检测**：
   - `observed_overlap` 标志：在 `fake_to_thread` 入口检查 `active_business`，若已有活跃业务体则记录重叠
   - 退出时重置 `active_business = False`

3. **mid-assertion 证明**（line 1128-1129）：
   - `await asyncio.sleep(0)` 仅是一次 event loop yield（零秒），不是 arbitrary sleep
   - 此时 `asyncio.Lock` 仍被搜索 task 持有（`fake_to_thread` 尚未释放），fetch task 的 `async with provider_lock` 无法进入
   - 断言 `to_thread_entries == ["enter"]` 证明：fetch 的 `asyncio.to_thread` 在 lock 释放前未被调用
   - 这个断言是**确定性的**——它依赖 `asyncio.Lock` 的 FIFO 语义，不依赖 wall-clock timing

4. **最终断言**（lines 1138-1141）：
   - `observed_overlap is False`：无业务体重叠
   - `to_thread_entries == ["enter", "enter"]`：两个 task 最终都调用了 `to_thread`
   - `business_entries == ["search", "fetch"]`：两个业务体都被执行

**结论**：测试不再依赖 arbitrary sleep（原 `asyncio.sleep(0.05)` 已移除）；通过 `asyncio.Event` 和 `asyncio.Lock` 实现确定性同步；能证明同 provider search/fetch 不重叠。无残留问题。

---

## New Issues Check

对 fix diff 做 adversarial pass，检查是否新引入 correctness/type/boundary/test 问题：

1. **`WebSearchProviderUnavailableError` 继承 `RuntimeError`**（`web_search_providers.py:107`）：语义正确。它表示运行时 provider 全部不可用，与 `WebSearchCancelledError`（继承 `Exception`）区分，不会在 `except Exception` catch-all 中与取消混淆。

2. **`_call_search_web` 异常捕获顺序**（`web_tools.py:1172-1194`）：`WebSearchCancelledError` → `WebSearchProviderUnavailableError` → `Exception`。顺序正确，`WebSearchProviderUnavailableError` 是 `RuntimeError` 子类，不会在 `WebSearchCancelledError` 之前被捕获。

3. **`_ALL_PROVIDERS_UNAVAILABLE_MESSAGE` 为中文**（`web_search_providers.py:27`）：`"联网检索失败：所有 provider 均不可用"` — 与模块内其他面向 LLM 的消息风格一致（如 `_raise_if_search_cancelled` 中的消息）。hint 为英文（`_SEARCH_PROVIDER_UNAVAILABLE_HINT`），符合 tool outcome hint 惯例。

4. **`provider.py` import 精简**：移除了 `dataclass` import、`_legacy_adapter.definition_adapter` import、`_legacy_adapter.registry_collector` import 以及 `register_web_tools` import。这些符号在 Slice 2 中已无消费，移除不会造成 import 错误。验证：`rg "_legacy_adapter|LegacyToolDeclarationCollector|LegacySyncToolCallable|adapt_collected_tools|tool_cancelled" dayu/tools/web tests/tools/web/test_web_tools_provider.py` 已在 controller adjudication 中确认为空。

5. **`_FORBIDDEN_IMPORTS` 测试覆盖**：`test_web_modules_do_not_import_legacy_registry_truncation_fetch_more_or_ui`（line 1144-1160）仍然覆盖 `_FORBIDDEN_IMPORTS`，包括 `dayu.tools._legacy_adapter`。AST 扫描确认所有 Web 模块无 forbidden import。

6. **`asyncio.sleep(0)` 在测试中的使用**：这不是 arbitrary sleep，是标准的 event loop yield。它不依赖 wall-clock time，只确保 event loop 处理一轮已排队的回调。行为是确定性的。

7. **测试 `test_search_provider_unavailable_projects_to_stable_business_failure` 的 API key 环境变量**：通过 `monkeypatch.setenv` 注入 fake key，确保 `auto` 候选顺序包含 Tavily 和 Serper（否则 `_has_configured_search_provider_api_key` 会跳过未配置 key 的 provider）。`monkeypatch` 在测试结束后自动清理，不会污染其他测试。

8. **`provider.py` 模块 docstring**（lines 1-7）：已更新为描述当前模块职责（"本模块只负责解析 Web provider 配置，并通过原生 ToolDefinition 暴露 search_web 与 fetch_web_page"），不再提及 legacy adapter。

**结论**：未发现新引入的 correctness/type/boundary/test 问题。

---

## Overall Conclusion

**pass**

四个 accepted findings（S2-CR-01 至 S2-CR-04）全部完全修复，无残留问题。未发现 fix 引入新的 correctness/type/boundary/test 问题。测试 17/17 通过，pyright 0 错误。

## Open Questions

无。

## Residual Risk

- Real Tavily / Serper success path smoke 仍依赖外部 credentials，不在本次 fix gate 范围内（已由 controller adjudication 明确 deferred）。
- Legacy adapter 目录删除仍为 Slice 4 范围（已由 controller adjudication 明确 deferred）。
- `search_public_web` 的 `except Exception` catch-all（line 270）在真实网络环境中可能捕获到 provider SDK 内部异常类型，但这些异常类型未在单元测试中精确断言——当前测试通过 monkeypatch 注入已知异常类型，覆盖了预期路径。若未来 provider SDK 抛出非 `Exception` 子类（如 `BaseException` 子类），可能绕过 catch-all。此风险属于 provider SDK 兼容性范畴，不是本次 fix 引入。
