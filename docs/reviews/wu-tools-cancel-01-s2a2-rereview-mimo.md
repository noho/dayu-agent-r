# Code Re-Review: WU-TOOLS-CANCEL-01 S2A2 Fix Gate

## Scope

- Mode: current changes (workspace diff only)
- Branch: `phase/wu-tools-cancel-01`
- Base: HEAD (workspace unstaged diff)
- Output file: `docs/reviews/wu-tools-cancel-01-s2a2-rereview-mimo.md`
- Included scope:
  - `dayu/host/tool_runtime.py` — S2A2 implementation + F02 docstring fix
  - `tests/host/test_toolruntime_executor.py` — F01/F03 test additions
  - `dayu/host/README.md` — ToolRuntime execution capsule 段落新增
  - Review artifacts: MiMo original review, DS review, Codex fix artifact
- Excluded scope: Engine contract, durable schema/migration, Host public cancel API, Doc/Fins/Web business tool migration
- Parallel review coverage: 无

## Review Inputs

- Code review artifact: `docs/reviews/wu-tools-cancel-01-s2a2-code-review-mimo.md`
- Code review artifact: `docs/reviews/wu-tools-cancel-01-s2a2-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-s2a2-fix-codex.md`
- Controller accepted findings: F01, F02, F03
- Deferred: MiMo original finding 3 (process envelope fail-closed executor-level wiring)

## Findings

未发现实质性问题。

## Closed Findings

### F01 — capsule build failure executor 链路测试 ✓ CLOSED

**Claimed fix**: 新增 `_RaisingCapsuleFactory` 和 `test_capsule_build_failure_bypasses_accept_barrier`。

**Verification**:

- `tests/host/test_toolruntime_executor.py` 新增 `_RaisingCapsuleFactory` 类（行 618-655），`create_capsule` 始终抛出传入的异常。
- `test_capsule_build_failure_bypasses_accept_barrier`（行 1096-1119）注入 `ValueError("capsule boom")`，断言：
  - `capsule_factory.create_calls == 1` — factory 被调用 ✓
  - `callable_.call_count == 0` — 业务 callable 未被调用 ✓
  - `accept_port.candidates == []` — 未进入 accept barrier ✓
  - `isinstance(record.outcome, ToolFailedOutcome)` — 返回失败 outcome ✓
  - `record.outcome.result.error == "tool_capsule_build_failed"` — error 值正确 ✓
  - `"ValueError: capsule boom" in record.outcome.result.message` — 异常信息透传 ✓
- 测试通过 `_executor(..., capsule_factory=capsule_factory)` 注入 fake factory，`capsule_factory` 直接映射到 `ToolRuntimeBuildRequest.execution_capsule_factory`。当该值非 `None` 时，`DefaultToolRuntimeFactory` 跳过 `DeclaredToolExecutionCapsuleFactory`，直接使用注入的 factory（`tool_runtime.py:3984-3987`）。这正确测试了 executor 级 capsule build failure 路径。
- 生产代码 `_dispatch_tool_call_with_bounds` 的 try/except（`tool_runtime.py:3197-3214`）捕获异常并返回 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR`。`_is_runtime_dispatch_exception_outcome`（`tool_runtime.py:6514-6528`）正确识别该 error 并 early return，不进入 accept barrier。测试完整覆盖了该链路的可观测行为。

**Verdict**: 完全满足 Controller accepted finding 要求。

### F02 — DeclaredToolExecutionCapsuleFactory.create_capsule docstring 异常类型 ✓ CLOSED

**Claimed fix**: 修正 docstring 异常类型说明。

**Verification**:

- `tool_runtime.py:1567-1570` docstring 现在写：
  - `:raises ValueError: 工具声明缺失时抛出。` — 对应 `:1574` 的 `raise ValueError(...)` ✓
  - `:raises TypeError: execution capability 类型未知时抛出。` — 对应 `_declared_capsule_for_execution` 中 `:1621-1623` 的 `raise TypeError(...)` ✓
  - `:raises Exception: process target factory 构造目标失败时透传。` — 对应 `_declared_capsule_for_execution` 中 process-backed 分支 `execution.target_factory.build_process_target(...)` 可能抛出的异常 ✓

**Verdict**: docstring 现在准确反映三种异常来源，满足 finding 要求。

### F03 — declaration-backed async_direct 与 thread_backed 默认路径集成测试 ✓ CLOSED

**Claimed fix**: 新增两个 declaration-backed 默认路径测试。

**Verification**:

- `test_declared_async_direct_default_factory_calls_tool`（行 1059-1075）：
  - 调用 `_executor(callable_, accept_port)` — 不传 `execution`，不传 `capsule_factory`。
  - `_executor` 内部 `capsule_factory=None` → `execution_capsule_factory=None`。
  - `_executor` 内部 `execution=None` → `_definition(..., execution=None)` → `AsyncDirectToolExecutionCapability()`（`_definition` 默认值，行 2714-2717）。
  - `DefaultToolRuntimeFactory` 检测到 `execution_capsule_factory is None` → 创建 `DeclaredToolExecutionCapsuleFactory(effective_bundle)`（`tool_runtime.py:3984-3987`）。
  - `create_capsule` 从 `effective_bundle.definitions_by_name` 获取 `ToolDefinition`，其 `execution` 为 `AsyncDirectToolExecutionCapability()` → `_declared_capsule_for_execution` 创建 `AsyncDirectToolExecutionCapsule`。
  - 断言 `callable_.call_count == 1`、`isinstance(record.outcome, ToolCompletedOutcome)`、`record.outcome.result.value == {"declared": "async-direct"}` ✓
  - **关键**：该测试真实经过 production default `DeclaredToolExecutionCapsuleFactory`，不是绕过 factory 直接构造 capsule。

- `test_declared_thread_backed_default_factory_calls_tool`（行 1078-1094）：
  - 调用 `_executor(callable_, accept_port, execution=ThreadBackedToolExecutionCapability())` — 不传 `capsule_factory`。
  - `execution_capsule_factory=None` → `DeclaredToolExecutionCapsuleFactory`。
  - `ToolDefinition.execution` 为 `ThreadBackedToolExecutionCapability()` → `_declared_capsule_for_execution` 创建 `ThreadBackedToolExecutionCapsule(_ThreadBackedDispatchTarget(...))`。
  - 断言 `callable_.call_count == 1`、`isinstance(record.outcome, ToolCompletedOutcome)`、`record.outcome.result.value == {"declared": "thread-backed"}` ✓
  - **关键**：同样真实经过 production default `DeclaredToolExecutionCapsuleFactory`。

- 辅助修改：`_executor` 和 `_definition` 新增 `execution` 参数（行 2585、2690），用于向 `ToolDefinition` 注入 execution capability。`_executor` 传递 `execution_capsule_factory=capsule_factory`（行 2638），当 `capsule_factory=None` 时由 `DefaultToolRuntimeFactory` 自动选择 `DeclaredToolExecutionCapsuleFactory`。

**Verdict**: 两个测试均经过 production default declaration-backed factory 路径，满足 finding 要求。

## New Findings

未发现新的实质性问题。

### 越界变更检查

fix diff 中生产代码变更仅限于 `DeclaredToolExecutionCapsuleFactory.create_capsule` docstring（F02）。其余生产代码变更（新常量、`_ThreadBackedDispatchTarget`、`DeclaredToolExecutionCapsuleFactory` 类、`_declared_capsule_for_execution`、process envelope 解析、`_is_runtime_dispatch_exception_outcome` 重命名、`ToolRuntimeBuildRequest.execution_capsule_factory` 默认值变更、`DefaultToolRuntimeFactory` factory 选择逻辑、`__all__` 新增）均为 S2A2 implementation 原有改动，非 fix 引入。

测试文件变更：
- 新增 `_EnvelopeProcessTarget`、`_RecordingProcessTargetFactory`、`_RaisingCapsuleFactory` 测试辅助类。
- `_executor` 和 `_definition` 新增 `execution` 参数。
- 移除 `DefaultToolExecutionCapsuleFactory` import（无现有测试使用）。
- 新增 3 个测试函数（F01、F03）。
- 既有测试行为未被修改。

无越界变更。

## Validation Claims

- `pytest tests/host/test_toolruntime_executor.py -q` → `55 passed in 6.09s` ✓ 已验证
- `pyright` → `0 errors, 0 warnings, 0 informations` ✓ 已验证

## Residual Risk

1. **Deferred finding 未修复**：MiMo original finding 3（process envelope fail-closed executor-level wiring）由 Controller 裁决为 deferred，fix 未新增相关测试。该 deferred 项不影响本轮 gate。

2. **`_executor` helper 的 `execution` 参数传播链**：新增的 `execution` 参数从 `_executor` → `_definition` → `ToolDefinition.execution` → `DeclaredToolExecutionCapsuleFactory` → `_declared_capsule_for_execution`。链路上每一步都有类型保证（`ToolExecutionCapability | None`），且 `None` 默认值明确映射到 `AsyncDirectToolExecutionCapability()`。风险低。

3. **既有测试对 `_executor` 签名变更的兼容性**：`_executor` 新增 `execution` 参数有默认值 `None`，不影响既有测试调用。`_definition` 新增 `execution` keyword-only 参数有默认值 `None`，同样不影响既有调用。风险低。

## Verdict

**PASS** — F01、F02、F03 三个 accepted findings 均已正确关闭。F01 测试验证了 capsule build failure 跳过 accept barrier 且不调用 business callable；F02 docstring 准确反映三种异常来源；F03 两个测试均经过 production default `DeclaredToolExecutionCapsuleFactory` 路径。fix 未误改生产行为，未新增越界变更。pyright 0 errors 和 pytest 55 passed 已验证可信。
