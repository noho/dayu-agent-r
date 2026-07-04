# Re-review — WU-TOOLS-CANCEL-01 S2C Fix

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: phase/wu-tools-cancel-01
- Base: workspace unstaged changes against HEAD
- Output file: docs/reviews/wu-tools-cancel-01-s2c-rereview-mimo.md
- Included scope:
  - `dayu/fins/tools/fins_tools.py`
  - `dayu/fins/tools/provider.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
- Excluded scope: Host / Engine / durable / runtime contract, Web tools, Fins WAITING tools
- Parallel review coverage: 无
- Source findings:
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2c-fix-codex.md`

## Findings

未发现实质性问题。

逐项确认如下。

### DS Finding 01 收口确认：`get_financial_statement` spawned-child process-backed 测试

新增测试 `test_fins_read_financial_statement_runs_in_spawned_child`（test_fins_storage_provider.py:888-906）：

- 通过 `_build_fins_financial_html_workspace(tmp_path)` 构造真实临时 Fins workspace，使用 `FsBatchingRepository`、`FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsDocumentBlobRepository` 写入 HTML 10-K fixture——全部经 `dayu.fins.storage` 仓储协议，未绕过 storage。
- 通过 `_build_process_target(workspace_root, "get_financial_statement", {...})` 从真实 provider discovery 构造 `_FinsReadProcessTarget`。
- 通过 `ProcessBackedToolExecutionCapsule(target)` 在真实 spawned child 中执行，验证子进程内 `DefaultFinsRuntime.create()` 正确装配 `FinancialDataProcessor` 路径。
- 断言 `ToolCompletedOutcome`，value 包含 `document_id`、`statement_type`、`rows`（list），且不含 `supported`/`error` 字段。
- 未引入脆弱 fake；所有仓储对象由 storage 协议实现驱动。

结论：**收口**。DS Residual Risk 1（`FinancialDataProcessor` 子进程装配可行性未经直接验证）已消除。

### DS Finding 02 收口确认：`_cancelled_from_token` 命名/文档误导

- `_cancelled_from_token` 已重命名为 `_build_fins_read_cancelled_outcome`（fins_tools.py:1395）。
- 签名从 `(tool_name, cancellation_token, started_at)` 改为 `(tool_name, started_at)`，移除了未使用的 `cancellation_token` 参数。
- docstring 明确说明："本函数不读取 Host token reason，避免把 run_id、session_id、digest 等 Host 治理信息泄漏到 LLM-facing message 或 hint。"
- 两处调用点（fins_tools.py:1007, 1010）已同步更新。
- Host governance reason 未泄漏到 LLM-facing message/hint。

结论：**收口**。

### DS Finding 03 收口确认：process target 通用异常 failed envelope 包含恢复 hint

`_FinsReadProcessTarget.__call__` 的 `except Exception` 分支（fins_tools.py:300-307）：

```python
except Exception:
    return {
        _FINS_PROCESS_STATUS_FIELD: _FINS_PROCESS_FAILED_STATUS,
        _FINS_PROCESS_ERROR_TYPE_FIELD: "execution_error",
        _FINS_PROCESS_MESSAGE_FIELD: (
            f"Tool {self.tool_name!r} execution failed. Hint: {_UNEXPECTED_FAILURE_HINT}"
        ),
    }
```

- 恢复 hint（`_UNEXPECTED_FAILURE_HINT` = "Inspect provider diagnostics or retry with narrower arguments."）已包含在 message 中。
- 未修改 Host process envelope contract（仍为 `status`/`error_type`/`message` 三字段）。
- 与 direct callable fallback 路径（`_execute_fins_read_business_value` line 1150-1155）保持一致。

结论：**收口**。

### 新增类型/docstring/Any/object/getattr/hasattr/README/import boundary 检查

- **类型**：所有新增函数/方法签名均有完整类型标注。无 `Any`、`object` 签名。
- **docstring**：所有新增/修改的函数、类、方法均有完整中文 docstring，含 Args/Returns/Raises。
- **无 `hasattr`/`getattr`**：diff 中无新增。
- **README 触发**：`dayu/fins/README.md` 已更新 read 路径描述、process-backed 执行形态说明和扩展点约束；`tests/README.md` 已更新 Fins process-backed 覆盖记录。
- **import boundary**：新增 import 均为 `dayu.contracts`（`ProcessBackedToolContext`、`ProcessBackedToolExecutionCapability`）和 `dayu.fins.service_runtime`（`DefaultFinsRuntime`），符合分层约束。

结论：**无新增问题**。

### S2C 原始目标满足确认

| 目标 | 状态 |
|------|------|
| 九个 read tools process-backed | ✅ 九个 `_build_*_definition` 均声明 `ProcessBackedToolExecutionCapability` |
| target/factory 不捕获 runtime/repo/cache/token/Host | ✅ `_FinsReadProcessTarget` 字段为 `workspace_root_locator: str`、`tool_name: str`、`arguments: dict`、`limits: FinsToolLimits`、`timeout_seconds: float \| None`；pickle round-trip 测试验证不含 forbidden fragments |
| production default 走 `ToolDefinition.execution` | ✅ Host `_declared_capsule_for_execution` 读取 `ProcessBackedToolExecutionCapability.target_factory` |

## Open Questions

无。

## Residual Risk

1. **`query_xbrl_facts` 未在 spawned child 中执行**：fix 覆盖了 `FinancialDataProcessor` 的 `get_financial_statement` 路径，但 `query_xbrl_facts` 仍无 spawned-child 测试。两者走相同 `FinancialDataProcessor` protocol 装配路径，且 `_route_fins_read_business` 中 `query_xbrl_facts` 与其它工具走相同 cast 路径。风险低。

2. **多工具并发 process-backed 的资源竞争未测试**：当前测试每次只执行一个 process-backed 工具。多个 Fins read tools 同时以独立子进程执行时的文件系统级锁行为需要进一步确认。

## Conclusion

**PASS**

三个 DS findings 全部收口：
- Finding 01：新增 `test_fins_read_financial_statement_runs_in_spawned_child` 通过真实 storage 仓储写入 HTML fixture、真实 `ProcessBackedToolExecutionCapsule` spawned child 验证 `FinancialDataProcessor` 子进程装配。
- Finding 02：`_cancelled_from_token` 重命名为 `_build_fins_read_cancelled_outcome`，移除未使用参数，docstring 明确说明避免 Host governance 泄漏。
- Finding 03：process target 通用异常 failed envelope 已包含 `_UNEXPECTED_FAILURE_HINT` 恢复提示。

无新增类型/docstring/Any/object/getattr/hasattr/README/import boundary 问题。S2C 原始目标全部满足。测试全部通过（31/31），pyright 0 errors。

READY_FOR_CONTROLLER
