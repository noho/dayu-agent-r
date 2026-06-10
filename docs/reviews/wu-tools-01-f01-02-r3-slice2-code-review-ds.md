# WU-TOOLS-01-F01-02-R3 Slice 2 Web Native Tools — Code Review

## 结论

**pass-with-findings** — 无 blocking defect；四条 finding 均为低/中严重度，不阻碍 Slice 2 接受。

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main` (仅检查未提交 working tree diff)
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice2-code-review-ds.md`
- Included scope:
  - `dayu/tools/web/provider.py`
  - `dayu/tools/web/web_tools.py`
  - `dayu/tools/web/web_search_providers.py`
  - `tests/tools/web/test_web_tools_provider.py`
- Excluded scope:
  - `docs/host/issues-implementation-control.md` (control doc 状态更新，非生产代码)
  - `docs/reviews/wu-tools-01-f01-02-r3-slice2-implementation-codex.md` (implementation record)
- Parallel review coverage: 无

## Findings

### F1-未修复-中-`_call_search_web` 搜索 provider 失败语义被过度压平为 `execution_error`

- **入口/函数**: `_call_search_web` — `search_web` callable 的异常投影外壳
- **文件(行号)**: `dayu/tools/web/web_tools.py:1162-1175`
- **输入场景**: `search_public_web` 内所有 provider (Tavily → Serper → DuckDuckGo) 均失败，抛出 `RuntimeError("联网检索失败：所有 provider 均不可用")`
- **实际分支**: `_search_web_business` 调用 `search_public_web` → 所有 provider fail → `RuntimeError` → `asyncio.to_thread` 重抛 → `except Exception as exc:` 命中 → `_unexpected_failed_outcome(error="execution_error")`
- **预期行为**: 按 plan Section 7 Slice 2 Error handling 约定，"搜索 provider 业务失败、fetch 失败保持现有 LLM-readable message / hint"。当前 `message` 字段确已保留原文，但 `error` 码被统一压为 `execution_error`，丢失了 provider 级失败的结构化语义
- **实际行为**: `ToolFailedOutcome(error="execution_error", message="联网检索失败：所有 provider 均不可用", hint=None)`
- **直接证据**:
  - Line 1162-1175: `except WebSearchCancelledError` → cancelled; `except Exception` → `_unexpected_failed_outcome` (hardcoded `"execution_error"`)
  - 对比同文件 `_call_fetch_web_page` (line 1247-1269): 包含独立的 `except ToolBusinessError as exc:` 分支，透传 `exc.code` / `exc.message` / `exc.hint`，保留了结构化 error code
  - `search_public_web` (web_search_providers.py:249-256): 内部循环的 `except Exception` 只捕获单个 provider 失败并 fallback；所有 provider 均失败时走 line 282 `raise RuntimeError(...)`
- **影响**: LLM 仍可读到 `message` 原文判断下一步动作，但 Host/Engine 层无法通过 error code 区分"所有 provider 不可用"与"未预期内部异常"；若未来 `search_public_web` 新增特定业务异常，也都会被压为 `execution_error`
- **建议改法和验证点**: 为搜索路径新增与 fetch 对称的业务异常 catch，或在 `_search_web_business` 中把 `RuntimeError` 映射为带明确 error code 的 typed result。至少应让 "所有 provider 不可用" 保留专用 error code（如 `"search_provider_unavailable"`），与真正的未预期 `execution_error` 区分。验证点：`test_search_failure_projects_to_current_failed_outcome` 当前断言 `error == "execution_error"`，修复后应断言保留业务语义 error code
- **修复风险（低）**: 新增异常分支不影响现有取消路径；`test_search_failure_projects_to_current_failed_outcome` 需要同步更新断言
- **严重程度（中）**

### F2-未修复-低-`_try_playwright_fallback` docstring 声明 `Raises: 无。` 与实际行为不一致

- **入口/函数**: `_try_playwright_fallback`
- **文件(行号)**: `dayu/tools/web/web_tools.py:674-675` (docstring Raises 段); `dayu/tools/web/web_tools.py:689-690` (实际 raise 路径)
- **输入场景**: Playwright backend 抛出 `CancelledError`（Host 在浏览器 fallback 期间取消）
- **实际分支**: `except _web_playwright_backend.CancelledError:` → line 690 `_raise_fetch_cancelled(cancellation_token)` → 内部 `raise WebToolCancelledError(...)` (line 543, `NoReturn`)
- **预期行为**: docstring 应声明本函数可能通过 `_raise_fetch_cancelled` 间接抛出 `WebToolCancelledError`
- **实际行为**: docstring 写 `Raises: 无。`，但 Playwright cancel 路径会 raise；调用方 `_fetch_web_page_business` 未捕获该异常，由上层 `_call_fetch_web_page` line 1247 `except WebToolCancelledError` 正确转为 `host_cancelled_outcome`，因此**运行时行为正确，仅 docstring 错误**
- **直接证据**: Line 674-675 `Raises: 无。` vs. line 689-690 `except _web_playwright_backend.CancelledError: _raise_fetch_cancelled(cancellation_token)` 且 `_raise_fetch_cancelled` 为 `NoReturn`
- **影响**: 文档错误，不影响运行时正确性；维护者可能误认为本函数不会抛异常而漏加 catch
- **建议改法和验证点**: 将 Raises 段改为 `Raises: WebToolCancelledError: Playwright 执行期间 Host 取消时抛出。`
- **修复风险（低）**: 仅改 docstring
- **严重程度（低）**

### F3-未修复-低-`provider.py.__all__` 对 `WebToolsConfig` 的可疑兼容 re-export

- **入口/函数**: `provider.py` 模块级 `__all__`
- **文件(行号)**: `dayu/tools/web/provider.py:22` (import); `dayu/tools/web/provider.py:315` (`__all__`)
- **输入场景**: 旧代码路径 `from dayu.tools.web.provider import WebToolsConfig` 仍可工作，因为 `provider.py` 持续在 `__all__` 中导出该符号
- **实际分支**: `WebToolsConfig` 的真实定义已从 `provider.py` 迁移至 `web_tools.py:157-178`；`provider.py:22` 通过 `from .web_tools import WebToolsConfig` 导入后，在 `__all__` 中再次导出
- **预期行为**: AGENTS.md 禁止"仅为保持旧导入路径而转发符号"的兼容性 re-export。Plan Section 2 Non-goals 明确"不引入兼容 re-export、兼容 facade 或仅透传旧导入路径的 wrapper"
- **实际行为**: `provider.py.__all__` 包含 `WebToolsConfig`，尽管 `provider.py` 自身只在 `_parse_config` 返回类型中使用该类型（line 62-63），并非必须对外暴露
- **直接证据**: Line 22 `from .web_tools import WebToolsConfig, build_web_tool_definitions`; line 315 `__all__ = ["WebToolsConfig", "discover_tools"]`; `WebToolsConfig` 定义位于 `web_tools.py:157`
- **影响**: 当前无外部 consumer 直接依赖此路径（测试通过包级 `dayu.tools.web` 导入），但保留 re-export 会让旧导入路径继续可用，与 plan 的"不保留旧导入兼容层"原则冲突
- **建议改法和验证点**: 从 `__all__` 中移除 `WebToolsConfig`（保留 `discover_tools`）；若确有外部 consumer 需要该类型，应从 `web_tools` 模块导入。验证：确认无 import 边界测试失败
- **修复风险（低）**: 仅影响 `__all__` 列表，不影响运行时行为
- **严重程度（低）**

### F4-未修复-低-并发串行化测试 `test_web_provider_serializes_search_and_fetch_business` 中段断言存在时序脆弱性

- **入口/函数**: `test_web_provider_serializes_search_and_fetch_business`
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:1046-1058`（`await asyncio.sleep(0.05)` → `assert max_active_count == 1` 段）
- **输入场景**: CI 运行环境负载极高，fetch task 在 50ms 内未被 event loop 调度
- **实际分支**: `await asyncio.sleep(0.05)` 后 fetch task 尚未尝试 `async with provider_lock:`，此时 `max_active_count` 仍为 1（仅有 search 在业务体内），断言通过但未验证锁的互斥效果
- **预期行为**: 中段断言 `max_active_count == 1` 应区分"fetch 被锁阻塞"与"fetch 尚未调度"
- **实际行为**: 两种情况下 `max_active_count` 均为 1，无法区分；但测试末尾的 `assert max_active_count == 1`（line 1060）在两次 `enter_business`/`leave_business` 均完成后检查，**该断言可靠**，不依赖时序
- **直接证据**:
  - Line 1046-1050: `await asyncio.sleep(0.05)` → `assert max_active_count == 1` — 依赖 event loop 在 50ms 内调度 fetch task 并使其到达 lock 获取点
  - Line 1060: `assert max_active_count == 1` — 最终断言，覆盖整个测试窗口，确定性地验证了 lock 的互斥性
- **影响**: 极端负载下中段断言可能成为"空洞通过"（未真正验证 lock 竞争），但末尾断言不受影响。整体测试的互斥性验证仍然有效
- **建议改法和验证点**: 无需修改中段断言逻辑；可在中段增加 `assert search_entered.is_set()` 作为最小前置条件，或改用 `asyncio.wait_for(fetch_task_has_attempted_lock, timeout=1.0)` 模式确保 fetch 已到达锁竞争点。若中段时序不可靠，可将中段 `max_active_count` 断言降级为注释
- **修复风险（低）**: 仅影响测试时序容忍度，不影响生产代码
- **严重程度（低）**

## Open Questions

无。

## Residual Risk

- **真实外网搜索 provider fallback 与 Tavily/Serper 成功路径未在本 Slice 验证。** 原因：Slice 2 implementation smoke 使用了 `--external-limit 0`，且 CI 环境未配置 Tavily/Serper API key。Owner: 已有 Web CI diagnostics / smoke follow-up (#120)。R3 closeout 必须记录这些未验证场景及 owner。
- **`_unexpected_failed_outcome` 将 `str(error)` 直接写入 `message` 可能导致内部 traceback 信息泄漏给 LLM。** 当前仅 `RuntimeError("联网检索失败：所有 provider 均不可用")` 等明确消息会经过此路径，且 `_call_fetch_web_page` 的 `except Exception` 同级 catch 同样不做 sanitization。此行为与旧实现一致，不是本 Slice 引入的回归。若后续需要统一异常消息消毒，应由独立 work unit 处理。
- **Doc / Fins read Slice (Slice 1/3) 与 adapter 删除 (Slice 4) 尚未实施。** 当前 Web 已完全脱离 legacy adapter，但 `dayu/tools/_legacy_adapter` 目录仍存在且被 Doc 和 Fins read provider 依赖。R3 整体完成前不可删除。
