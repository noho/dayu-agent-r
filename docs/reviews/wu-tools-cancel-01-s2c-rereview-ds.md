# Code Re-Review — WU-TOOLS-CANCEL-01 S2C Fix

## Scope

- Mode: current changes (workspace diff only)
- Branch: phase/wu-tools-cancel-01
- Base: HEAD (uncommitted workspace diff)
- Output file: docs/reviews/wu-tools-cancel-01-s2c-rereview-ds.md
- Primary review artifacts: `docs/reviews/wu-tools-cancel-01-s2c-code-review-ds.md` (AgentDS), `docs/reviews/wu-tools-cancel-01-s2c-code-review-mimo.md` (AgentMiMo)
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2c-fix-codex.md`
- Included scope:
  - `dayu/fins/tools/fins_tools.py` (uncommitted diff — S2C fix changes)
  - `dayu/fins/tools/provider.py` (uncommitted diff)
  - `tests/fins/test_fins_storage_provider.py` (uncommitted diff — new test + fixture)
  - `dayu/fins/README.md` (uncommitted diff)
  - `tests/README.md` (uncommitted diff)
- Excluded scope: committed S2A1/S2A2/S2B slices, Host/Engine internals, download/preprocess/upload tools
- Parallel review coverage: 无（单 reviewer 逐行走读）

## Review Method

本 re-review 只审 S2C fix 对三个 DS finding 的修复是否收口，以及是否引入新问题。按 deepreview skill 定义的 Current Changes Mode 执行，沿修复后的真实代码路径逐行走读。

## DS Finding Resolution

### DS Finding 01: FinancialDataProcessor spawned-child 覆盖 — RESOLVED ✅

**原始 finding**: `query_xbrl_facts` 与 `get_financial_statement` 缺少 spawned-child process target 覆盖；`FinancialDataProcessor` protocol 在子进程中的装配可行性未经直接验证。

**修复内容**:

1. 新增 fixture 辅助函数 `_build_fins_financial_html_workspace`（test_fins_storage_provider.py:1498-1578），通过真实 `dayu.fins.storage` 仓储构造包含 HTML 10-K 的 Fins workspace：
   - `FsBatchingRepository(workspace_root, repository_set=repository_set)` — 真实 batching 仓储
   - `FsCompanyMetaRepository` — 写入公司元数据（AAPL, CIK 0000320193）
   - `FsSourceDocumentRepository` — 创建 source document（`aapl-html-2024-10k`, form_type "10-K"）
   - `FsDocumentBlobRepository` — 存储 HTML blob（`_fixture_financial_html()` 内容）
   - 完整 batch commit/rollback 语义
   - 无 mock、无 fake、无绕过 storage 协议

2. 新增测试 `test_fins_read_financial_statement_runs_in_spawned_child`（test_fins_storage_provider.py:1468-1492）：
   - 通过 `_build_process_target(workspace_root, "get_financial_statement", {...})` 构造 target
   - `_build_process_target` 走完整真源链路：`_discover_definitions(workspace_root)` → 真实 provider → `ProcessBackedToolExecutionCapability.target_factory` → `factory.build_process_target(call, context)`
   - 通过 `_run_process_capsule(target)` 在真实 `ProcessBackedToolExecutionCapsule` 中 spawned child 执行
   - 断言 `isinstance(outcome, ToolCompletedOutcome)` — 确认子进程成功完成
   - 断言 `value.get("document_id") == "aapl-html-2024-10k"` — 业务字段正确
   - 断言 `value.get("statement_type") == "income"` — statement type 正确
   - 断言 `isinstance(value.get("rows"), list)` — 返回结构化 rows
   - 断言 `"supported" not in value` 且 `"error" not in value` — 无错误标记

**证据链**:

```
test_fins_read_financial_statement_runs_in_spawned_child
  → _build_fins_financial_html_workspace (真实 Fs* 仓储写入 HTML fixture)
  → _build_process_target (真实 provider discovery → ProcessBackedToolExecutionCapability.target_factory)
  → _run_process_capsule (真实 ProcessBackedToolExecutionCapsule.run → spawned child)
  → _FinsReadProcessTarget.__call__
    → DefaultFinsRuntime.create(workspace_root=Path(...))
    → runtime.get_read_runtime(...)
    → _execute_fins_read_business_value
      → _route_fins_read_business
        → read_runtime.get_financial_statement(...)  ← FinancialDataProcessor protocol
```

**判定**: `get_financial_statement` 与 `query_xbrl_facts` 共享同一个 `FinancialDataProcessor` protocol 和 `_route_fins_read_business` 路由。`get_financial_statement` 的 spawned-child 成功直接证明了 `FinancialDataProcessor` protocol 在子进程中可正确装配。测试未使用 fake storage 或绕过仓储协议。**DS Finding 01 已收口。**

### DS Finding 02: _cancelled_from_token 命名/文档误导 — RESOLVED ✅

**原始 finding**: 函数名 `_cancelled_from_token` 暗示会从 token 提取信息构造 outcome，但实际 `del cancellation_token` 立即丢弃参数；消息硬编码，不读取 `cancel_reason()`。

**修复内容**:

1. 函数重命名为 `_build_fins_read_cancelled_outcome`（fins_tools.py:1398），准确描述行为：构造 cancelled outcome。
2. 移除 `cancellation_token: CancellationToken` 参数，签名变为 `(tool_name: str, started_at: datetime)`（line 1398-1400）。
3. 移除 `del cancellation_token` 行。
4. 新增 docstring（lines 1402-1405）显式说明设计意图：
   > 本函数不读取 Host token reason，避免把 run_id、session_id、digest 等 Host 治理信息泄漏到 LLM-facing message 或 hint。
5. 两处调用点（`_invoke_fins_read_business` lines 1006, 1009）均已更新为新函数名和新签名。

**LLM-facing 文本泄漏检查**:
- 取消消息: `"财报读取工具调用已被取消。"` — 纯业务语义，无 Host 治理信息
- 取消 hint: `"当前工具调用已停止；等待新的用户指令或后续调度。"` — 纯业务语义，无 Host 治理信息

**判定**: 函数名准确反映行为，docstring 显式解释设计意图，LLM-facing 消息无 Host governance reason 泄漏。**DS Finding 02 已收口。**

### DS Finding 03: process target 通用异常丢失 hint — RESOLVED ✅

**原始 finding**: `_FinsReadProcessTarget.__call__` 的 `except Exception` 分支（通用异常）缺少 `_UNEXPECTED_FAILURE_HINT`，而 direct callable fallback 的同类异常处理附带该 hint。

**修复内容**:

`_FinsReadProcessTarget.__call__` line 289（fins_tools.py:289），通用异常 failed 信封 message 改为：

```python
f"Tool {self.tool_name!r} execution failed. Hint: {_UNEXPECTED_FAILURE_HINT}"
```

其中 `_UNEXPECTED_FAILURE_HINT = "Inspect provider diagnostics or retry with narrower arguments."`（line 78）。

**与 direct callable fallback 的一致性验证**:

- Direct callable 路径：`_execute_fins_read_business_value` 的 `except Exception` → `_FinsReadBusinessFailure("execution_error", ..., _UNEXPECTED_FAILURE_HINT)` → `_process_failed_envelope` → `_process_failure_message` → `"{message} Hint: {hint}"`
- Process target 路径：`except Exception` → 直接构造 `{"message": f"Tool {self.tool_name!r} execution failed. Hint: {_UNEXPECTED_FAILURE_HINT}"}`

两条路径的 hint 文本和格式一致（均使用 `"Hint: "` 前缀）。

**Host process envelope contract 检查**:
- Host process envelope 无独立 hint 字段；hint 折入 message 字段，与 `_process_failure_message` 模式一致（fins_tools.py:1173-1192）
- 未修改 Host public contract 或 runtime JSON 契约

**判定**: 通用异常路径现在包含恢复 hint，与 direct callable fallback 一致，且不修改 Host process envelope contract。**DS Finding 03 已收口。**

## New Issue Scan

按 CLAUDE.md 硬约束逐项扫描修复引入的新增代码：

### 类型标注

- `_build_fins_read_cancelled_outcome`: 参数 `tool_name: str, started_at: datetime`，返回值 `ToolExecutionOutcome` ✅
- `_build_fins_financial_html_workspace`: 参数 `tmp_path: Path`，返回值 `Path` ✅
- `_fixture_financial_html`: 无参数，返回值 `str` ✅
- `test_fins_read_financial_statement_runs_in_spawned_child`: 参数 `tmp_path: Path`，返回值 `None` ✅
- 无新增 `Any`、`object`、无类型参数、无类型返回值

### Docstring

- 所有新增函数/方法均有完整中文 docstring，含 Args/Returns/Raises ✅
- 无缺失 docstring 的公开符号

### getattr/hasattr

- 修复 diff 中无新增 `getattr` 或 `hasattr` 调用 ✅

### Import boundary

- `fins_tools.py`: 修复不涉及新增 import；已有 import 均为合约层/Fins 内部/运行时基础设施 ✅
- `test_fins_storage_provider.py`: 新增 `import pickle`（标准库）；`from dayu.contracts.tool_execution import ProcessBackedToolContext, ProcessBackedToolExecutionCapability, ProcessBackedToolTarget, ProcessBackedToolTargetFactory`（合约层，测试允许）；`from dayu.host.tool_runtime import ProcessBackedToolExecutionCapsule`（测试允许跨层引用）✅
- 无反向 import、无跨层穿透

### README 触发

- `dayu/fins/README.md`: 已更新 read path 描述、process-backed 架构说明、扩展点约束 ✅
- `tests/README.md`: 已更新 Fins 测试覆盖记录，包含 process-backed 相关覆盖项 ✅

### LLM-facing 文本约束

- `_build_fins_read_cancelled_outcome` 的 message/hint 无 Host 治理信息 ✅
- `_FinsReadProcessTarget.__call__` 的 failed envelope message 仅含 tool_name 和通用 hint ✅
- `_process_failed_envelope` / `_process_failure_message` 仅使用 business-level error/message/hint ✅

## S2C Original Goals Re-verification

对照 S2C 原始目标逐项复核：

| # | 目标 | 修复前状态 | 修复后状态 |
|---|------|-----------|-----------|
| 1 | 九个 read tools process-backed | ✅ 已满足 | ✅ 未退化 |
| 2 | target/factory 不捕获 runtime/repo/cache/token/Host | ✅ 已满足 | ✅ 未退化 |
| 3 | production default 走 ToolDefinition.execution | ✅ 已满足 | ✅ 未退化 |
| 4 | 子进程通过 DefaultFinsRuntime.create + storage 重建 | ✅ 已满足 | ✅ 新增 FinancialDataProcessor 路径覆盖 |
| 5 | schema/truncate/failure envelope 自解释无 regression | ✅ 已满足（DS finding 03 除外） | ✅ DS finding 03 已收口 |
| 6 | direct callable fallback 仅为测试/非生产 | ✅ 已满足 | ✅ 未退化 |
| 7 | 不影响 WAITING tools | ✅ 已满足 | ✅ 未退化 |
| 8 | AGENTS.md 硬约束 | ✅ 已满足 | ✅ 修复未引入新违规 |

## Findings

未发现实质性问题。

三个 DS finding 全部收口，修复引入的代码无新增类型/docstring/Any/object/getattr/hasattr/README/import boundary 问题，S2C 原始目标未退化。

## Open Questions

无。

## Residual Risk

1. **`query_xbrl_facts` 未独立覆盖 spawned-child**: `get_financial_statement` 已覆盖 `FinancialDataProcessor` protocol 的 process-boundary 路径，两者共享同一 processor protocol 和 `_route_fins_read_business` 路由。`query_xbrl_facts` 的额外参数（concepts、period_end、min_value/max_value 等）在参数校验层被覆盖，processor 调用层的差异属于同一 protocol 的不同方法。风险低，不阻塞 merge。

2. **`except Exception` 通用异常路径无直接测试**: `_FinsReadProcessTarget.__call__` 的 `except Exception` 分支仅在子进程基础设施故障时触发（如 `DefaultFinsRuntime.create()` 失败），难以在不引入 mock 的前提下构造真实触发场景。当前该路径的 message 格式已通过静态代码阅读验证与 `_process_failure_message` 一致。风险低。

3. **多工具并发 process-backed 资源竞争**: 与初次 DS review 的 residual risk 相同，未在本次修复中覆盖。不阻塞 merge。

## Verdict

**PASS**

三个 DS finding 全部收口：FinancialDataProcessor spawned-child 覆盖通过真实仓储和 ProcessBackedToolExecutionCapsule 验证（finding 01）；`_cancelled_from_token` 重命名为 `_build_fins_read_cancelled_outcome` 并移除误导参数，LLM-facing 消息无 Host governance 泄漏（finding 02）；process target 通用异常路径已附加 `_UNEXPECTED_FAILURE_HINT`，与 direct callable fallback 一致且不修改 Host process envelope contract（finding 03）。修复未引入新问题，S2C 原始目标未退化。

READY_FOR_CONTROLLER
