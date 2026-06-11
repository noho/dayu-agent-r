# WU-TOOLS-01-F01-02-R3 Aggregate Deepreview Fix - AgentCodex

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Gate: aggregate deepreview fix
- Date: 2026-06-10
- Agent: AgentCodex
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-controller-adjudication.md`
- Allowed scope: accepted findings only; no stage, no commit, no push.

## Goal / Scope

本 fix gate 只处理 Controller 裁决为 accepted 的七项 finding：

- `AGG-DS-F1`
- `AGG-MIMO-F1`
- `AGG-MIMO-F2`
- `AGG-MIMO-F4`
- `AGG-MIMO-F14`
- `AGG-MIMO-F15`
- `AGG-MIMO-F17`

不处理 deferred / rejected findings，不修改 Engine / Host 状态机，不恢复 legacy adapter，不新增兼容 alias。

## First-principles Judgment

动机成立。直接代码证据显示：

- Doc 取消路径原先在 `_doc_cancelled(...)` 中读取 `CancellationToken.cancel_reason()` 并拼入 `ToolCancelledOutcome.message`，会把 Host 治理字符串投影给 LLM。
- Web 预取消路径原先在 `_host_cancelled_from_token(...)` 中读取 `token.cancel_reason()`，`search_web` 深层取消原先直接使用 `WebSearchCancelledError.message`，`fetch_web_page` 的 Playwright / RuntimeError 取消路径也可能沿异常消息泄漏治理字符串。
- Doc `_project_doc_paths(...)` 只对 `directory` 参数做 `is_dir()` 校验，没有对 `file_path` 做 `is_file()` 校验，导致目录路径进入业务体后落到通用执行错误。
- `_try_playwright_fallback(...)` 是浏览器回退统一入口，入口缺少取消检查会在已取消 token 下启动 fallback。
- `ToolBusinessFailure` 在 `dayu.runtime.tool_call_projection` 中无消费者，继续导出会扩大 runtime 公共表面。
- `dayu/tools/__init__.py` 包说明仍描述 OLD adapter，与当前 native provider 状态不一致。
- 控制文档仍有 F04/F05/F06/F07 残留表述，且 R3 accepted commit 信息缺失。

这些修复均在允许文件内闭合，不需要新增抽象或扩大契约。

## Changes

### AGG-DS-F1

状态：已修复。

改动：

- `dayu/tools/doc_tools.py`
  - `_doc_cancelled()` 不再接收或读取 `CancellationToken`，固定返回安全取消说明。
  - Doc 预取消和深层 `_DocCancelledError` 路径都使用固定安全 message / hint。
- `dayu/tools/web/web_tools.py`
  - 新增 Web 搜索 / 抓取固定安全取消 message。
  - `_host_cancelled_from_token(...)` 改为接收固定 message，不读取 token reason。
  - `search_web` 捕获 `WebSearchCancelledError` 时忽略异常 message，只投影固定安全取消说明。
  - `_raise_fetch_cancelled()` 不再读取 token reason。
  - `fetch_web_page` 的深层 `RuntimeError` catch 在 token 已取消时转为固定安全取消，不把异常文本当业务失败投影。
  - Playwright backend cancellation message 被 `_raise_fetch_cancelled()` 统一消毒。

测试：

- Doc 预取消测试注入 `run_id/session_id/payload_ref`，断言 outcome message / hint 不含治理字符串。
- Doc line scan 深层取消测试注入 `run_id/correlation_id/digest`，断言 outcome message / hint 不含治理字符串。
- Web search 预取消、search provider 深层取消、fetch 预取消、fetch RuntimeError 深层取消、Playwright fallback 入口预取消均断言不含 `run_id/session_id/payload_ref/digest/correlation_id/cancellation_token`。

### AGG-MIMO-F1

状态：已修复。

改动：

- `dayu/tools/doc_tools.py::_project_doc_paths(...)` 对非 `directory` 路径参数增加 `candidate.is_file()` 校验。
- `file_path` 指向目录时返回 `ToolFailedOutcome(error="invalid_argument")`，不进入业务体，不落入 `execution_error`。

测试：

- `tests/tools/test_doc_tools_provider.py::test_doc_file_path_pointing_to_directory_returns_invalid_argument` 覆盖 `get_file_sections`、`read_file`、`read_file_section`。

### AGG-MIMO-F2

状态：已修复。

改动：

- `dayu/tools/web/web_tools.py::_try_playwright_fallback(...)` 入口先调用 `_raise_if_host_cancelled(cancellation_token)`。
- 已取消时抛出模块内取消信号，不调用 `_fetch_and_convert_with_playwright(...)`。

测试：

- `tests/tools/web/test_web_tools_provider.py::test_try_playwright_fallback_pre_cancel_does_not_start_playwright` 断言已取消 token 下 Playwright worker 未启动。

### AGG-MIMO-F4

状态：已修复。

改动：

- 移除 `dayu/runtime/tool_call_projection.py::ToolBusinessFailure`。
- 从 `__all__` 移除 `ToolBusinessFailure`，未添加兼容 alias / wrapper / re-export。

验证：

- `rg -n "ToolBusinessFailure" dayu tests` 无生产或测试消费者。

### AGG-MIMO-F14

状态：已修复。

改动：

- `docs/host/issues-implementation-control.md` 中 F01-03 非目标段不再引用 F04/F05/F06/F07。
- 改为由 GitHub Issues #121 / #122 追踪 SEC/Fins CI pipeline / smoke 与 CN/HK Docling CI pipeline / smoke。

### AGG-MIMO-F15

状态：已修复。

改动：

- `docs/host/issues-implementation-control.md` 的 R3 当前 work unit 记录补充：
  - plan: `7b465e19`
  - Slice 0: `a5ab5364`
  - Slice 1: `1bbc45fe`
  - Slice 2: `ac0c7303`
  - Slice 3: `2a914234`
  - Slice 4: `a24f6dc9`

### AGG-MIMO-F17

状态：已修复。

改动：

- `dayu/tools/__init__.py` 包 docstring 更新为当前 native `ToolDefinition` / `ToolCallable` provider 边界，不再声称 OLD adapter。

## README Decision

- 修改了 `tests/`：已阅读 `tests/README.md` 更新约束。本轮只在既有 Doc/Web provider 测试层补充具体 regression cases，未新增测试层级、运行方式或维护约定，因此不更新 `tests/README.md`。
- 修改了 `dayu/runtime` 与 `dayu/tools`：未改变跨包关系、装配方式或 Host / Engine / Service 边界；`dayu/README.md` 只记录总揽级稳定边界，因此不更新。
- 未修改 `dayu/engine/`、`dayu/host/`、`dayu/fins/`、`dayu/config/`，不触发对应 README。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py -q
```

结果：`71 passed`。

指定完整验证：

```bash
source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py
```

结果：`115 passed, 3 warnings`。warnings 均来自 `edgar` 依赖的 deprecation warning。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 提示存在新版本 `v1.1.410`，不影响类型检查结果。

```bash
git diff --check
```

结果：通过，无输出。

```bash
rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests
```

结果：无命中。

```bash
rg "WU-TOOLS-01-F04|WU-TOOLS-01-F05|WU-TOOLS-01-F06|WU-TOOLS-01-F07" docs/host/issues-implementation-control.md
```

结果：无命中。

补充核对：

```bash
rg -n "ToolBusinessFailure" dayu tests
```

结果：无命中。

## Residual Risks

- Web live / real network smoke：tracked by existing issue，GitHub Issues #121 / #122；不属于 deterministic R3 blocker。
- 已启动同步 HTTP / browser 工作的物理中断：tracked by existing issue，WU-WAIT-03 / GitHub Issue #92；本轮只关闭已裁决的协作式入口和消息治理问题。
- Deferred / rejected aggregate findings：按 Controller adjudication 保持原 destination，不在本 fix gate 处理。

## Completion Status

当前状态：accepted findings 已修复，指定验证已通过；等待 re-review gate。

Artifact path: `docs/reviews/wu-tools-01-f01-02-r3-aggregate-deepreview-fix-codex.md`
