# WU-TOOLS-01-F01-02-R3 Aggregate Deepreview Fix Focused Re-Review — AgentDS

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: aggregate deepreview fix focused re-review
- Date: 2026-06-10
- Agent: AgentDS
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-controller-adjudication.md`
- Codex fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-fix-codex.md`
- Re-review artifact: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-rereview-ds.md`

## Scope

只复查 Controller adjudication 中 accepted findings 的 fix。不重新扩大审查 deferred/rejected findings。

Accepted findings:
- AGG-DS-F1：Doc/Web cancellation outcome message/hint 不泄露 cancel_reason 中的治理字符串
- AGG-MIMO-F1：Doc file_path 指向目录返回 invalid_argument
- AGG-MIMO-F2：_try_playwright_fallback 入口已取消时不启动 Playwright fallback
- AGG-MIMO-F4：ToolBusinessFailure 类型和 __all__ 导出已移除
- AGG-MIMO-F14：总控中 WU-TOOLS-01-F04/F05/F06/F07 残留引用已删除
- AGG-MIMO-F15：总控记录了 R3 plan 与 Slice0-4 accepted commits
- AGG-MIMO-F17：dayu/tools/__init__.py docstring 不再声称 OLD adapter

## Re-review Method

对每项 accepted finding，沿真实代码路径逐行走读：
1. 确认 fix 已按 adjudication 要求实施；
2. 确认没有引入新的治理泄漏、边界错误或类型问题；
3. 确认对应测试覆盖了入参、触发条件与实际行为的证据链；
4. 确认没有对 deferred/rejected finding 做越权修改。

## Re-review by Finding

### AGG-DS-F1：Doc/Web cancellation message/hint 治理

**证据链**：

- `dayu/tools/doc_tools.py::_doc_cancelled()`（行 1626-1639）：不接收或读取 `CancellationToken`，固定返回 `ToolBusinessCancelled(message="文档工具调用已被宿主取消。", hint=_DOC_CANCELLED_HINT)`。`_DOC_CANCELLED_HINT`（行 66）为固定安全字符串。
- `_invoke_doc_business()` 预取消检查（行 727-731）：使用 `_cancelled_outcome(tool_name, started_at, _doc_cancelled())`，不读取 token reason。
- `_invoke_doc_business()` 深层取消（行 734-735）：catch `_DocCancelledError` 后使用 `error.cancellation`，该值来自 `_doc_cancelled()` -> `_raise_doc_cancelled()` 链，不读取 token reason。
- `dayu/tools/web/web_tools.py::_host_cancelled_from_token()`（行 1404-1427）：不再读取 `token.cancel_reason()`，接收显式 `message`/`hint` 参数。
- `_raise_fetch_cancelled()`（行 539-558）：使用固定 `_WEB_FETCH_CANCELLED_MESSAGE` 和安全 hint，不读取 token reason。
- `_call_search_web()` 预取消（行 1141-1150, 1163-1172）：使用固定 `_WEB_SEARCH_CANCELLED_MESSAGE`。
- `_call_search_web()` 深层取消（行 1183-1190）：message 使用固定 `_WEB_SEARCH_CANCELLED_MESSAGE`；hint 来自 `WebSearchCancelledError.hint`（搜索 provider 层异常，非 Host token `cancel_reason()` 泄漏源）。
- `_call_fetch_web_page()` 预取消（行 1246-1255, 1261-1269）：使用固定 `_WEB_FETCH_CANCELLED_MESSAGE`。
- `_call_fetch_web_page()` 深层取消（行 1277-1284）：catch `WebToolCancelledError`，其 message/hint 来自 `_raise_fetch_cancelled()`，均为固定安全值。
- `_fetch_web_page_business()` RuntimeError 深层取消（行 1753）：`cancellation_token.is_cancelled()` 时调用 `_raise_fetch_cancelled()`，不把异常文本当业务失败投影。

**测试覆盖**：
- `test_doc_tools_cancelled_before_work_return_host_cancelled`（test_doc_tools_provider.py:227）：五个 Doc tools 预取消，cancel reason 注入 `run_id/session_id/payload_ref`，断言 `_assert_no_governance_text`。
- `test_search_files_line_scan_cancellation_returns_host_cancelled`（test_doc_tools_provider.py:718）：line scan 深层取消时 `_assert_no_governance_text`。
- `test_search_web_cancelled_before_provider_returns_host_cancelled`（test_web_tools_provider.py:379）：Web search 预取消，cancel reason 注入治理字段，断言无泄漏。
- `test_search_web_deep_cancel_message_is_sanitized`（test_web_tools_provider.py:473）：search provider 深层取消异常 message 含治理字段，断言 outcome 无泄漏。
- `test_fetch_web_page_cancelled_before_work_returns_safe_host_cancelled`（test_web_tools_provider.py:658）：fetch 预取消，cancel reason 注入治理字段，断言无泄漏。
- `test_fetch_web_page_deep_runtime_cancel_message_is_sanitized`（test_web_tools_provider.py:679）：fetch 深层 RuntimeError 携带治理字段，断言 outcome 无泄漏。
- `test_try_playwright_fallback_pre_cancel_does_not_start_playwright`（test_web_tools_provider.py:853）：Playwright fallback 入口预取消，断言异常 message/hint 无治理泄漏。

**裁决**：已修复。所有 Doc/Web 取消路径的 LLM-facing message/hint 均不读取 `CancellationToken.cancel_reason()`，改为固定安全字符串。测试沿预取消和深层取消两条路径验证。

### AGG-MIMO-F1：Doc file_path 指向目录返回 invalid_argument

**证据链**：

- `dayu/tools/doc_tools.py::_project_doc_paths()`（行 845-850）：对非 `"directory"` 的路径参数增加 `candidate.is_file()` 校验。`file_path` 指向目录时返回 `_DocPathFailure(error="invalid_argument", ...)`。
- 分支语义：`parameter_name == "directory"` 走 `candidate.is_dir()` 校验（行 839-844），`parameter_name != "directory"`（即 `"file_path"`）走 `candidate.is_file()` 校验（行 845-850）。不存在重叠或覆盖问题。
- 下游：`_path_failed_outcome()` 将 `_DocPathFailure` 投影为 `ToolFailedOutcome(error=error_code)`，不进入 `_invoke_doc_business()` 业务体，不会落入 `execution_error`。

**测试覆盖**：
- `test_doc_file_path_pointing_to_directory_returns_invalid_argument`（test_doc_tools_provider.py:307）：参数化 `get_file_sections`、`read_file`、`read_file_section`，传入目录路径，断言 `outcome.result.error == "invalid_argument"`。

**裁决**：已修复。路径投影层对 `file_path` 参数增补了 `is_file()` 校验，目录路径提前返回 `invalid_argument`，不进入业务体。

### AGG-MIMO-F2：_try_playwright_fallback 入口已取消时不启动 Playwright

**证据链**：

- `dayu/tools/web/web_tools.py::_try_playwright_fallback()`（行 698）：入口第一条语句 `_raise_if_host_cancelled(cancellation_token)`。
- `_raise_if_host_cancelled()`（行 650-665）：`cancellation_token is not None and cancellation_token.is_cancelled()` 时调用 `_raise_fetch_cancelled()` 抛出 `WebToolCancelledError`。
- 取消时控制流不触及行 700 的 `_fetch_and_convert_with_playwright()`。

**测试覆盖**：
- `test_try_playwright_fallback_pre_cancel_does_not_start_playwright`（test_web_tools_provider.py:853）：已取消 token 下直接调用 `_try_playwright_fallback`，mock 的 `_fetch_and_convert_with_playwright` 记录调用副作用，断言 `playwright_calls == []`，断言异常 message/hint 无治理泄漏。

**裁决**：已修复。`_try_playwright_fallback` 入口执行取消检查，取消时不启动 Playwright worker。

### AGG-MIMO-F4：ToolBusinessFailure 类型和 __all__ 导出已移除

**证据链**：

- `dayu/runtime/tool_call_projection.py`：`__all__`（行 837-847）不包含 `ToolBusinessFailure`。
- 模块内无 `ToolBusinessFailure` 类定义。
- `rg -n "ToolBusinessFailure" dayu tests`：无命中。
- 无兼容 alias、wrapper 或 re-export。

**裁决**：已修复。`ToolBusinessFailure` 已从 `dayu.runtime.tool_call_projection` 完全移除，无残留引用。

### AGG-MIMO-F14：总控中 F04/F05/F06/F07 残留引用已删除

**证据链**：

- `rg "WU-TOOLS-01-F04|WU-TOOLS-01-F05|WU-TOOLS-01-F06|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md`：无命中。
- 控制文档 `WU-TOOLS-01-S1-R1`（行 198）已改为由 GitHub Issues #121/#122 追踪 SEC/Fins 与 CN/HK Docling CI pipeline/smoke。

**裁决**：已修复。F04/F05/F06/F07 残留引用已从控制文档删除，改为 issue-121/issue-122 追踪表达。

### AGG-MIMO-F15：总控记录了 R3 plan 与 Slice0-4 accepted commits

**证据链**：

- `docs/host/issues-implementation-control.md` 行 223：`WU-TOOLS-01-F01-02-R3` 行 `当前定位` 列明确记录 plan commit `7b465e19` 与 Slice 0/1/2/3/4 accepted commits `a5ab5364` / `1bbc45fe` / `ac0c7303` / `2a914234` / `a24f6dc9`。

**裁决**：已修复。R3 的 plan 与 Slice0-4 accepted commits 已在控制文档记录。

### AGG-MIMO-F17：dayu/tools/__init__.py docstring 不再声称 OLD adapter

**证据链**：

- `dayu/tools/__init__.py`（行 1-8）docstring 描述当前 `ToolDefinition` / `ToolCallable` 契约和 runtime discovery / Host ToolRuntime 装配边界，不提及 OLD adapter。
- 无 `_legacy_adapter`、`LegacyToolDeclarationCollector`、`adapt_collected_tools` 等旧符号在 `dayu\tools` 下的引用（`rg` 验证：无命中）。

**裁决**：已修复。包 docstring 已更新为当前 native provider/tools 边界说明。

## Adversarial Failure Pass

对已修复区域执行 adversarial pass：

- 预取消路径：所有 Doc/Web callable 的 `cancellation_token.is_cancelled()` 检查在 provider lock 外和 lock 内各执行一次（双检查），已覆盖。
- 深层取消路径：Doc 的 `_raise_if_doc_cancelled()` / `_raise_if_doc_cancelled_at_interval()` 在循环和 I/O 边界均有调用；Web 的 `_raise_if_host_cancelled()` 在 fetch 各阶段入口均有调用。
- `_project_doc_paths()` 中对 `file_path` 的 `is_file()` 校验同时检查了文件存在性和类型；`exists()` 检查在先（行 833-838），`is_file()` 在后（行 845-850），分支语义正确：不存在的文件返回 `file_not_found`，存在的目录返回 `invalid_argument`。
- `_try_playwright_fallback()` 入口取消检查在参数解包后、Playwright 调用前（行 698），覆盖所有 call site（warmup、probe、fetch、SSL、timeout-like、bot challenge、pipeline failure、conversion failure、post-fetch bot check 等）。
- 未发现 fix 引入的新类型问题、新治理泄漏或新边界错误。

## Verification

独立复验：

- `pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py`：71 passed。
- `pyright`：0 errors, 0 warnings, 0 informations。
- `rg -n "ToolBusinessFailure" dayu tests`：无命中。
- `rg "WU-TOOLS-01-F04|WU-TOOLS-01-F05|WU-TOOLS-01-F06|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md`：无命中。
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`：无命中。

与 Controller 预验证结论一致。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `WebSearchCancelledError.hint` 直通：`_call_search_web()`（web_tools.py:1189）中 `hint=exc.hint` 将搜索 provider 层异常 hint 直接投影到 outcome。当前 provider 层 `WebSearchCancelledError.hint` 不含 Host 治理字符串（异常来自 provider 自身取消逻辑，非 token `cancel_reason()` 泄漏），但若未来 search provider 实现变化并开始在 hint 中携带敏感字段，该路径无二次消毒。此项不属于本轮 accepted finding 范围，且当前代码路径无实际泄漏证据；记录为低风险 residual note。
- Deferred/rejected aggregate findings：按 Controller adjudication 保持原 destination，不在本 re-review 处理。

## Verdict

**PASS**。7 项 accepted findings 全部已修复，代码、测试与验证结果一致，未发现新增实质性缺陷。0 findings。

Artifact path: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-rereview-ds.md`
