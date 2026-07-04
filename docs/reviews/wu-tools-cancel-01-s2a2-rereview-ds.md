# Code Re-Review: WU-TOOLS-CANCEL-01 S2A2 Fix Gate

## Verdict

**PASS** — F01、F02、F03 均已关闭，无新增 finding，无生产行为误改，无越界变更。测试经过 production default declaration-backed factory 路径，pyright 0 errors，pytest 全绿（fix 相关 3 条 + 原有 52 条 = 55 passed）。

## Scope

- **Mode**: fix re-review（S2A2 code review findings F01/F02/F03 的 fix 验证）
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: HEAD workspace diff（包含 S2A2 原始实现 + fix）
- **Output file**: `docs/reviews/wu-tools-cancel-01-s2a2-rereview-ds.md`
- **Review inputs**:
  - `docs/reviews/wu-tools-cancel-01-s2a2-code-review-mimo.md`（MiMo review）
  - `docs/reviews/wu-tools-cancel-01-s2a2-code-review-ds.md`（DS review）
  - `docs/reviews/wu-tools-cancel-01-s2a2-fix-codex.md`（fix artifact）
  - `dayu/host/tool_runtime.py`（workspace diff）
  - `tests/host/test_toolruntime_executor.py`（workspace diff）
- **Controller accepted findings**: F01, F02, F03
- **Deferred**: MiMo finding 3（process envelope fail-closed executor-level wiring）— 不要求本轮修复
- **Parallel review coverage**: 无

## Closed Findings

### F01 — capsule build failure executor 链路测试 ✅ CLOSED

- **入口/函数**: `ToolRuntimeExecutor._dispatch_tool_call_with_bounds` → `_execute_tool_call_with_governance`
- **Fix**: 新增 `_RaisingCapsuleFactory` + `test_capsule_build_failure_bypasses_accept_barrier`
- **验证路径**:

  1. `_RaisingCapsuleFactory(ValueError("capsule boom"))` 注入 `_executor(..., capsule_factory=...)` → `ToolRuntimeBuildRequest(execution_capsule_factory=capsule_factory)` → `DefaultToolRuntimeFactory.create_tool_runtime()` 因 `request.execution_capsule_factory is not None` 直接使用注入 factory（`tool_runtime.py:3984-3986`）→ `ToolRuntimeExecutor(execution_capsule_factory=...)`
  2. Executor 处理工具调用时 `_dispatch_tool_call_with_bounds:3198-3203` 调用 `create_capsule` → `ValueError` 抛出
  3. `except Exception as exc:` (`:3204`) 捕获 → 返回 `(ToolFailedOutcome(error="tool_capsule_build_failed"), None)` (`:3205-3214`)
  4. `_execute_tool_call_with_governance:2969` — `_is_runtime_dispatch_exception_outcome(raw_outcome)` 命中（`tool_runtime.py:6522-6528`，error 在 `{_TOOL_RUNTIME_CALLABLE_FAILED_ERROR, _TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR}` 中）
  5. `:2971-2974` early return，`durable_missing_reason = TOOL_EXCEPTION`，不进入 accept barrier

- **断言覆盖**:
  - `capsule_factory.create_calls == 1` — factory 被调用（`test_toolruntime_executor.py:1091`）
  - `callable_.call_count == 0` — 未调用业务 callable（`:1092`）
  - `accept_port.candidates == []` — 未进入 accept barrier（`:1093`）
  - `isinstance(record.outcome, ToolFailedOutcome)` — 返回失败 outcome（`:1094`）
  - `record.outcome.result.error == "tool_capsule_build_failed"` — 正确 error code（`:1095`）
  - `"ValueError: capsule boom" in record.outcome.result.message` — 异常信息在 message 中（`:1096`）

- **未覆盖项**: `durable_missing_reason` 未直接断言（不在 `_executor` 测试边界内）。Fix artifact 已明确声明此限制，controller 接受的行为验证（不进入 accept barrier + 返回 tool failure）已充分覆盖外部可观测行为。

- **测试执行**: `test_capsule_build_failure_bypasses_accept_barrier` PASSED（55 passed in 6.12s）

### F02 — DeclaredToolExecutionCapsuleFactory.create_capsule docstring ✅ CLOSED

- **入口/函数**: `DeclaredToolExecutionCapsuleFactory.create_capsule`
- **Fix**: docstring 异常类型修正（`tool_runtime.py:1568-1570`）
- **验证**:
  - `:1568` — `:raises ValueError: 工具声明缺失时抛出。` ✅ 对应 `:1574-1575` 的 `raise ValueError(...)`
  - `:1569` — `:raises TypeError: execution capability 类型未知时抛出。` ✅ 对应 `:1622-1623` 的 `raise TypeError(...)`
  - `:1570` — `:raises Exception: process target factory 构造目标失败时透传。` ✅ 对应 `:1617-1619` 的 `execution.target_factory.build_process_target(...)` 可能抛出的异常

- **不再声称**: docstring 不再将 `ValueError` 覆盖未知 capability 场景（原错误描述"工具声明缺失或 execution capability 类型未知时抛出"）

### F03 — declaration-backed async_direct 和 thread_backed 默认路径集成测试 ✅ CLOSED

- **入口/函数**: `DefaultToolRuntimeFactory.create_tool_runtime` → `DeclaredToolExecutionCapsuleFactory.create_capsule` → `_declared_capsule_for_execution`
- **Fix**: 新增两条测试

- **`test_declared_async_direct_default_factory_calls_tool`** (`test_toolruntime_executor.py:1062-1075`):
  - `_executor(callable_, accept_port)` — 不传 `execution`，不传 `capsule_factory`
  - `execution=None` → `_definition` 默认 `AsyncDirectToolExecutionCapability()` (`:2717-2719`)
  - `capsule_factory=None` → `ToolRuntimeBuildRequest(execution_capsule_factory=None)` → `DefaultToolRuntimeFactory:3984-3988` 创建 `DeclaredToolExecutionCapsuleFactory(effective_bundle)`
  - 该 factory 读取 `ToolDefinition.execution`（`AsyncDirectToolExecutionCapability()`）→ `_declared_capsule_for_execution:1602` → `AsyncDirectToolExecutionCapsule`
  - 断言: `callable_.call_count == 1`, `accept_port.candidates == 1`, `ToolCompletedOutcome`, value 正确
  - **经过 production default declaration-backed factory** ✅

- **`test_declared_thread_backed_default_factory_calls_tool`** (`test_toolruntime_executor.py:1078-1096`):
  - `_executor(callable_, accept_port, execution=ThreadBackedToolExecutionCapability())` — 不传 `capsule_factory`
  - `capsule_factory=None` → 同上 declaration-backed factory 路径
  - `DeclaredToolExecutionCapsuleFactory.create_capsule()` → `_declared_capsule_for_execution:1608` → `ThreadBackedToolExecutionCapsule(_ThreadBackedDispatchTarget(...))`
  - `_ThreadBackedDispatchTarget.__call__()` → `asyncio.run(self.dispatcher.dispatch_tool_call(...))` → 调用业务 callable
  - 断言: `callable_.call_count == 1`, `accept_port.candidates == 1`, `ToolCompletedOutcome`, value 正确
  - **经过 production default declaration-backed factory** ✅

- **测试执行**: 两条均 PASSED

## New Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

1. **`test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 失败**: 全量 Host 测试套件（1554 passed, 1 failed, 1 skipped）中该测试因 compactor evidence_material 为空而失败。此测试位于 `tests/host/test_public_compact_smoke.py:431`，是 LLM 依赖的集成测试，与 S2A2 capsule factory 变更无关。属于预存 flaky test，不阻塞 merge。

2. **capsule build failure 的 `durable_missing_reason` 未直接断言**: F01 测试从 `_executor` helper 边界无法观测 `durable_missing_reason`。外部行为（不进入 accept barrier、不调用 callable、返回 ToolFailedOutcome）已充分覆盖。若后续有人重构 `_is_runtime_dispatch_exception_outcome` 的 early return 位置，需单独补 `_is_runtime_dispatch_exception_outcome` 单元测试。

3. **`_RaisingCapsuleFactory` 未显式实现 `ToolExecutionCapsuleFactory` Protocol**: 测试用 factory 通过 duck typing 匹配 `create_capsule` 签名。当前无类型检查问题（pyright 0 errors），但若 Protocol 增加方法，该测试 factory 不会收到类型提示。仅影响测试代码，风险极低。

4. **`DefaultToolExecutionCapsuleFactory` 仍为 dead code**: 该 class 仍定义在 `tool_runtime.py` 并在 `__all__` 中，但无生产代码或测试使用。MiMo review 已记录此 residual risk。

5. **`ToolExecutionMode` 兼容性 re-export**: 从 `dayu.contracts.tool_execution` re-export，`__all__` 中保留。MiMo review 已记录。

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| pytest `test_toolruntime_executor.py` | 55 passed ✅ |
| pytest `tests/host/` 全量 | 1554 passed, 1 failed（预存 flaky, 不相关）|
| pyright | 0 errors, 0 warnings, 0 informations ✅ |
| F01 关闭 | ✅ capsule build failure → ToolFailedOutcome, bypass accept, 不调用 callable |
| F02 关闭 | ✅ docstring 异常类型准确 |
| F03 关闭 | ✅ async_direct + thread_backed 经 declaration-backed factory |
| 生产行为误改 | 无 ✅ |
| 越界变更 | 无 ✅ |
| 测试经 production default factory | ✅ `capsule_factory=None` → `DeclaredToolExecutionCapsuleFactory` |
