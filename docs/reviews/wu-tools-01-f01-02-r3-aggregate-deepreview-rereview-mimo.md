# WU-TOOLS-01-F01-02-R3 Aggregate Deepreview Fix Re-Review - AgentMiMo

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: aggregate deepreview fix re-review
- Date: 2026-06-10
- Agent: AgentMiMo
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-fix-codex.md`
- Base: `main` / `caaa559e`

## Scope

只复查 Controller 裁决为 accepted 的七项 finding 的 fix，不重新扩大审查 deferred / rejected findings。

## Findings

未发现实质性问题。

## Verification Detail

### AGG-DS-F1：Doc/Web cancellation outcome message/hint 不泄露治理字符串

**代码走读：**

- `dayu/tools/doc_tools.py:1626` `_doc_cancelled()` 不再接收 `CancellationToken`，固定返回 `ToolBusinessCancelled(message="文档工具调用已被宿主取消。", hint=_DOC_CANCELLED_HINT)`。`cancel_reason()` 不再被调用。
- `dayu/tools/doc_tools.py:1607` `_raise_doc_cancelled()` 调用无参 `_doc_cancelled()`。
- `dayu/tools/doc_tools.py:728,731` 预取消路径调用 `_doc_cancelled()` 而非 `_doc_cancelled(token)`。
- `dayu/tools/web/web_tools.py:1404-1425` `_host_cancelled_from_token()` 参数从 `token: CancellationToken` 改为 `message: str`，不再调用 `token.cancel_reason()`。
- `dayu/tools/web/web_tools.py:536-552` `_raise_fetch_cancelled()` 不再接收 `CancellationToken`，固定返回 `_WEB_FETCH_CANCELLED_MESSAGE`。
- `dayu/tools/web/web_tools.py:1167,1188` search 预取消和深层 `WebSearchCancelledError` 捕获都使用 `_WEB_SEARCH_CANCELLED_MESSAGE`，不使用 `exc.message`。
- `dayu/tools/web/web_tools.py:1246,1260` fetch 预取消路径使用 `_WEB_FETCH_CANCELLED_MESSAGE`。
- `dayu/tools/web/web_tools.py:1753-1754` fetch 深层 `RuntimeError` catch 在 token 已取消时调用 `_raise_fetch_cancelled()`，不把异常文本当业务失败投影。

**测试覆盖：**

- Doc 预取消测试注入 `run_id=run-doc session_id=session-doc payload_ref=payload-{tool_name}`，断言 outcome message / hint 不含治理字符串。
- Doc line scan 深层取消测试注入 `run_id=run-doc correlation_id=correlation-doc digest=sha256:doc`，断言不含治理字符串。
- Web search 预取消测试注入 `run_id=run-web session_id=session-web payload_ref=payload-web`，断言不含治理字符串。
- Web search 深层取消测试（`test_search_web_deep_cancel_message_is_sanitized`）注入 `run_id=run-web correlation_id=correlation-web digest=sha256:web`，断言不含治理字符串。
- Web fetch 预取消测试注入 `run_id=run-web session_id=session-web cancellation_token=token-web`，断言不含治理字符串。
- Web fetch 深层 RuntimeError 取消测试（`test_fetch_web_page_deep_runtime_cancel_message_is_sanitized`）注入治理字段，断言不含治理字符串。
- Playwright fallback 入口预取消测试注入治理字段，断言不含治理字符串。

**结论：** 治理字符串注入路径全部被固定安全消息替代，预取消和深层取消路径均覆盖，无遗漏。

### AGG-MIMO-F1：Doc file_path 指向目录返回 invalid_argument

**代码走读：**

- `dayu/tools/doc_tools.py:845-850` 新增 `if parameter_name != "directory" and not candidate.is_file()` 分支，在路径已确认存在后、进入业务体前返回 `_DocPathFailure(error="invalid_argument", ...)`。该分支只对非 `directory` 参数生效，`directory` 参数的 `is_dir()` 校验在 `line 839` 独立处理，互不干扰。

**测试覆盖：**

- `test_doc_file_path_pointing_to_directory_returns_invalid_argument` 参数化覆盖 `get_file_sections`、`read_file`、`read_file_section`，创建目录传入 `file_path`，断言 `ToolFailedOutcome` 且 `error == "invalid_argument"`。

**结论：** 目录路径在路径投影层被拦截，不进入业务体，不落入 `execution_error`。

### AGG-MIMO-F2：_try_playwright_fallback 入口已取消时不启动 Playwright

**代码走读：**

- `dayu/tools/web/web_tools.py:698` 在 `_try_playwright_fallback()` 入口、`try` 块之前调用 `_raise_if_host_cancelled(cancellation_token)`。token 已取消时抛出 `WebToolCancelledError`，不执行 `_fetch_and_convert_with_playwright()`。

**测试覆盖：**

- `test_try_playwright_fallback_pre_cancel_does_not_start_playwright` 注入已取消 token，mock `_fetch_and_convert_with_playwright` 记录调用，断言 `playwright_calls == []` 且异常 message / hint 不含治理字符串。

**结论：** 已取消 token 下 Playwright worker 不会被启动。

### AGG-MIMO-F4：ToolBusinessFailure 类型和 __all__ 导出已移除

**代码走读：**

- `dayu/runtime/tool_call_projection.py` diff 显示 `ToolBusinessFailure` dataclass（原 19 行）已完整删除，`__all__` 中的 `"ToolBusinessFailure"` 条目已移除。
- 未添加兼容 alias、wrapper 或 re-export。

**验证：**

- `rg -n "ToolBusinessFailure" dayu tests` 无命中。

**结论：** 类型和导出已彻底移除，无兼容残留。

### AGG-MIMO-F14：总控中 F04/F05/F06/F07 残留引用已删除

**代码走读：**

- `docs/host/issues-implementation-control.md:900` 原文 `F04 / F05 / F06 / F07 仍负责迁移 CI pipeline 与生成 smoke` 改为 `SEC/Fins CI pipeline / smoke 与 CN/HK Docling CI pipeline / smoke 改由 GitHub Issues #121 / #122 追踪`。

**验证：**

- `rg "WU-TOOLS-01-F04|WU-TOOLS-01-F05|WU-TOOLS-01-F06|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md` 无命中。

**结论：** F04-F07 引用已全部改为 issue 追踪表达。

### AGG-MIMO-F15：总控记录了 R3 plan 与 Slice0-4 accepted commits

**代码走读：**

- `docs/host/issues-implementation-control.md:223` R3 行的备注列更新为 `accepted plan commit 7b465e19；Slice 0 / 1 / 2 / 3 / 4 accepted commits a5ab5364 / 1bbc45fe / ac0c7303 / 2a914234 / a24f6dc9`。

**结论：** R3 plan 和 Slice 0-4 的 accepted commits 已记录在控制文档中。

### AGG-MIMO-F17：dayu/tools/__init__.py docstring 不再声称 OLD adapter

**代码走读：**

- `dayu/tools/__init__.py:2-4` docstring 从 `当前 slice 只提供 OLD 风格工具声明到当前 ToolDefinition 的私有适配器` 改为 `Doc、Web 与财报 read 工具通过当前 ToolDefinition / ToolCallable 契约暴露，由 runtime discovery 和 Host ToolRuntime 显式装配与治理`。

**结论：** 包 docstring 准确反映当前 native provider 边界，不再声称 OLD adapter。

## Controller 复验确认

以下 Controller 已复验结果与本次独立验证一致：

| 验证项 | Controller 结果 | MiMo 独立验证 |
|---|---|---|
| pytest 完整集合 | 115 passed, 3 edgar deprecation warnings | 115 passed, 3 warnings |
| pyright | 0 errors | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed | passed |
| rg legacy adapter symbols | no matches | no matches |
| rg F04/F05/F06/F07 in control doc | no matches | no matches |

## Open Questions

无。

## Residual Risk

- Web live / real network smoke：tracked by GitHub Issues #121 / #122，不属于 deterministic R3 blocker。
- 已启动同步 HTTP / browser 工作的物理中断：tracked by WU-WAIT-03 / GitHub Issue #92，本轮只关闭已裁决的协作式入口和消息治理问题。
- Deferred / rejected aggregate findings：按 Controller adjudication 保持原 destination，不在本 fix gate 处理。

## Verdict

**PASS**

七项 accepted findings 全部修复到位，代码走读确认实现正确，测试覆盖充分，Controller 复验结果与独立验证一致。未发现实质性问题。
