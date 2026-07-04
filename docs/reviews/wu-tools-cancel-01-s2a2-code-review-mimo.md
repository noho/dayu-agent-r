# Code Review - WU-TOOLS-CANCEL-01 S2A2

## Scope

- Mode: current changes (workspace diff only)
- Branch: `phase/wu-tools-cancel-01`
- Base: HEAD (workspace unstaged diff)
- Output file: `docs/reviews/wu-tools-cancel-01-s2a2-code-review-mimo.md`
- Included scope:
  - `dayu/host/tool_runtime.py` — declaration-backed factory wiring, process envelope mapping
  - `tests/host/test_toolruntime_executor.py` — new tests for factory wiring and envelope mapping
  - `dayu/host/README.md` — ToolRuntime execution capsule 段落新增
  - `docs/reviews/wu-tools-cancel-01-s2a2-implementation-codex.md` — implementation gate artifact
- Excluded scope: Engine contract, durable schema/migration, Host public cancel API, Doc/Fins/Web business tool migration
- Parallel review coverage: 无

## Findings

### 1-未修复-中-缺少 capsule 构造失败路径的 executor 级测试

- **入口/函数**: `ToolRuntimeExecutor._dispatch_tool_call_with_bounds`
- **文件(行号)**: `dayu/host/tool_runtime.py:3197-3214`
- **输入场景**: `DeclaredToolExecutionCapsuleFactory` 遇到未知 `ToolExecutionCapability` 类型（`TypeError`）或 process target factory 构造目标抛出异常
- **实际分支**: `try/except Exception` 被触发，返回 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR`
- **预期行为**: capsule 构造失败应返回受治理的 failed outcome，不传播原始异常给 Engine
- **实际行为**: 生产代码正确捕获并归一化，但无测试覆盖此路径
- **直接证据**:
  - `tool_runtime.py:3197-3214` — `try: capsule = self._execution_capsule_factory.create_capsule(...)` / `except Exception as exc:` → `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR`
  - `_is_runtime_dispatch_exception_outcome` (行 6514-6528) 已将 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR` 加入判断集合，但无测试验证此判定
  - `tests/host/test_toolruntime_executor.py` — 全文搜索 `capsule_build` 无结果
- **影响**: 若 capsule 构造失败的归一化逻辑被后续改动破坏，无测试会发现回归。当前行为正确但无守护。
- **建议改法和验证点**: 新增测试，使用一个 `create_capsule` 抛出异常的 fake factory，验证 executor 返回 `ToolFailedOutcome` 且 `error == "tool_capsule_build_failed"`，同时验证 `_is_runtime_dispatch_exception_outcome` 对此 error 的判定。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-thread_backed 未通过 declaration-backed factory 路径测试

- **入口/函数**: `_declared_capsule_for_execution` 中 `ThreadBackedToolExecutionCapability` 分支
- **文件(行号)**: `dayu/host/tool_runtime.py:1607-1614`
- **输入场景**: 工具声明 `execution=ThreadBackedToolExecutionCapability()`，生产默认 factory 路径
- **实际分支**: `isinstance(execution, ThreadBackedToolExecutionCapability)` → `ThreadBackedToolExecutionCapsule(_ThreadBackedDispatchTarget(...))`
- **预期行为**: thread_backed capsule 通过声明式 factory 正确创建，`_ThreadBackedDispatchTarget` 的 `asyncio.run(dispatcher.dispatch_tool_call(...))` 路径被覆盖
- **实际行为**: `test_thread_backed_capsule_does_not_claim_thread_termination` 直接构造 capsule，未经过 `DeclaredToolExecutionCapsuleFactory` 或 `_declared_capsule_for_execution`
- **直接证据**:
  - `tests/host/test_toolruntime_executor.py:1776-1798` — 直接 `ThreadBackedToolExecutionCapsule(target)`，不经过 `_executor(..., execution=ThreadBackedToolExecutionCapability())`
  - `test_tool_runtime_default_factory_uses_declared_process_backed_execution` 只测 `process_backed`，未测 `thread_backed`
- **影响**: thread_backed 的 `_ThreadBackedDispatchTarget` 包装路径（`asyncio.run` + dispatcher）未被集成测试覆盖。若该路径有 bug（如 event loop 嵌套问题），当前测试不会发现。
- **建议改法和验证点**: 新增测试，通过 `_executor(..., execution=ThreadBackedToolExecutionCapability())` 走生产默认 factory，验证 callable 在子线程的独立 event loop 中被调用且结果正确返回。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-process envelope fail-closed 测试绕过了 executor 级 wiring

- **入口/函数**: `ProcessBackedToolExecutionCapsule.run()` → `_tool_outcome_from_process_envelope`
- **文件(行号)**: `tests/host/test_toolruntime_executor.py:1584-1612`
- **输入场景**: 非法或 reserved status 的 process envelope
- **实际分支**: 直接构造 `ProcessBackedToolExecutionCapsule(_EnvelopeProcessTarget(envelope))` 并调用 `capsule.run()`
- **预期行为**: fail-closed 逻辑在 capsule 层正确工作
- **实际行为**: 测试只验证 capsule 层行为，未经过 `DeclaredToolExecutionCapsuleFactory` → `_declared_capsule_for_execution` → `ProcessBackedToolExecutionCapsule` 的完整链路
- **直接证据**:
  - `tests/host/test_toolruntime_executor.py:1606` — `capsule = ProcessBackedToolExecutionCapsule(_EnvelopeProcessTarget(envelope))`
  - 对比 `test_tool_runtime_default_factory_uses_declared_process_backed_execution` (行 1517) 走了完整 factory 链路
- **影响**: envelope 解析逻辑本身正确，但 capsule 构造路径（target_factory → target → capsule）未被 fail-closed 场景覆盖。风险较低，因为 envelope 解析是独立函数。
- **建议改法和验证点**: 可接受当前覆盖方式，因为 `_tool_outcome_from_process_envelope` 是纯函数，capsule 层测试已足够证明 fail-closed 行为。若要更严格，可将部分 parametrize case 改为通过 `_executor(..., execution=ProcessBackedToolExecutionCapability(...))` 走完整链路。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- `DefaultToolExecutionCapsuleFactory` 仍保留在 `tool_runtime.py` 和 `__all__` 中，但当前无任何生产代码或测试使用它。它已退化为 dead code。保留是为了向后兼容还是可以清理，取决于是否有外部消费者。
- `ToolExecutionMode` 从 `tool_runtime.py` 的本地定义改为从 `dayu.contracts.tool_execution` 导入并 re-export。`__all__` 中仍保留该符号。当前无类型错误，但属于兼容性 re-export，若后续清理应一并处理。
- `thread_backed` 的 `_ThreadBackedDispatchTarget` 使用 `asyncio.run()` 在新 event loop 中运行 dispatcher，这意味着如果目标 callable 内部依赖外部 event loop 状态（如共享的 async session），可能出现嵌套 event loop 问题。当前测试未暴露此风险，生产迁移 `thread_backed` 工具时需注意。

## Verdict

**PASS** — S2A2 的 declaration-backed Host capsule factory wiring 实现正确，核心生产路径（process-backed 通过声明式 factory）有测试覆盖。发现 1 项中等 severity test gap（capsule 构造失败路径无 executor 级测试）和 2 项低 severity test gap，均为 test coverage 加强项，不阻塞 merge。
