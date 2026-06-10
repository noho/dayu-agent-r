# WU-TOOLS-01-F01-02-R3 Slice 2 Re-Review - MiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice2-rereview-mimo.md`
- Included scope: S2-CR-01 到 S2-CR-04 fix 复核
- Excluded scope: 外部 Tavily/Serper credentials、真实网络 smoke、legacy adapter deletion（已明确 residual/deferred）

## Conclusion

**pass**

所有 accepted findings 已完全修复，未发现新引入的 correctness/type/boundary/test 问题。

## Findings

未发现实质性问题。

## Fix Verification

### S2-CR-01: `search_web` Provider Failure Is Over-Flattened To `execution_error`

**状态**: ✅ 完全修复

**验证证据**:

1. **新异常类型**: `web_search_providers.py` 添加了 `WebSearchProviderUnavailableError(RuntimeError)`，docstring 完整，继承合理。

2. **异常映射**: `web_tools.py:_call_search_web` 中：
   - `WebSearchCancelledError` → `host_cancelled_outcome` (cancelled)
   - `WebSearchProviderUnavailableError` → `failed_outcome(error=_SEARCH_PROVIDER_UNAVAILABLE_ERROR)` (稳定业务失败)
   - 其他异常 → `_unexpected_failed_outcome(error="execution_error")` (未预期失败)

3. **错误码常量**: `_SEARCH_PROVIDER_UNAVAILABLE_ERROR = "search_provider_unavailable"` 是稳定的 `Final[str]`。

4. **Hint 内容**: `_SEARCH_PROVIDER_UNAVAILABLE_HINT` 非空，内容为：
   ```
   [retry_later_or_use_known_source] Search providers are currently unavailable; retry later, refine the query, or continue with a known source URL.
   ```
   LLM-readable，包含恢复建议。

5. **测试覆盖**: `test_search_provider_unavailable_projects_to_stable_business_failure` 验证：
   - 驱动 Tavily、Serper、DuckDuckGo 三个 provider 真实 fallback 路径
   - 断言 `error == "search_provider_unavailable"`
   - 断言 `message` 包含 "provider"
   - 断言 `hint` 非空
   - 断言三个 provider 都被尝试

6. **provider exhaustion 路径**: `web_search_providers.py:search_public_web` 在所有 provider 失败后抛出 `WebSearchProviderUnavailableError`，而非 `RuntimeError`。

### S2-CR-02: `_try_playwright_fallback` Docstring Hides Cancellation Raise

**状态**: ✅ 完全修复

**验证证据**:

`_try_playwright_fallback` docstring 已更新：
```python
Raises:
    WebToolCancelledError: Playwright 执行期间 Host 取消时抛出。
```

与实现一致：函数内部 `except CancelledError` 分支调用 `_raise_fetch_cancelled(...)`，后者抛出 `WebToolCancelledError`。

### S2-CR-03: `provider.py.__all__` Re-exports `WebToolsConfig`

**状态**: ✅ 完全修复

**验证证据**:

1. `provider.py.__all__` 现在为 `["discover_tools"]`，不包含 `WebToolsConfig`。

2. `WebToolsConfig` 定义已移至 `web_tools.py`（`WebToolsConfig.__module__ == "dayu.tools.web.web_tools"`）。

3. `provider.py` 仍从 `web_tools` 导入 `WebToolsConfig`（用于 `_parse_config`），但不在 `__all__` 中暴露，符合"本地导入仅用于内部消费"的约束。

### S2-CR-04: Web Provider Lock Test Has A Timing-Weak Mid-Assertion

**状态**: ✅ 完全修复

**验证证据**:

新测试 `test_web_provider_serializes_search_and_fetch_business` 使用确定性协调：

1. **协调机制**:
   - `first_to_thread_entered = asyncio.Event()` - 第一个任务进入信号
   - `release_first_to_thread = asyncio.Event()` - 释放第一个任务信号

2. **fake_to_thread** 拦截 `asyncio.to_thread`：
   - 第一次进入时设置 `first_to_thread_entered` 并等待 `release_first_to_thread`
   - 跟踪 `active_business` 标志检测重叠
   - 记录 `to_thread_entries` 和 `business_entries`

3. **测试流程**:
   - 启动 search_task
   - 等待 `first_to_thread_entered`（search 进入 fake_to_thread）
   - 启动 fetch_task
   - `await asyncio.sleep(0)` 让出控制权（非 arbitrary sleep，是 asyncio 标准做法）
   - 断言 `to_thread_entries == ["enter"]`（只有 search 进入）
   - 设置 `release_first_to_thread` 释放 search
   - 等待两个任务完成

4. **最终断言**:
   - `observed_overlap is False` - 无重叠
   - `to_thread_entries == ["enter", "enter"]` - 两个都进入
   - `business_entries == ["search", "fetch"]` - 顺序正确

**关键改进**: 原测试使用 `await asyncio.sleep(0.05)` 做 timing-based 断言；新测试使用 `asyncio.Event` 做确定性协调，能证明 fetch task 在 search 业务释放 provider lock 后才进入业务边界。

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py`: **17 passed**
- `source .venv/bin/activate && pyright`: **0 errors, 0 warnings**
- `git diff --check`: passed

## Open Questions

无。

## Residual Risk

- 外部 Tavily/Serper success paths 依赖外部环境配置，不在本 fix gate 范围内。
- Legacy adapter directory deletion 由后续 slice 处理。
- 真实网络 smoke 测试由 Web CI diagnostics/smoke follow-up 覆盖。
