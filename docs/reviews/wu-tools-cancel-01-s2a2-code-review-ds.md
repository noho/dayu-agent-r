# Code Review: WU-TOOLS-CANCEL-01 S2A2 Host Factory Wiring

## Verdict

**NEEDS_FIX** — 发现 1 个中等严重程度 finding（capsule build failure 路径中 `policy_decision` 为 None 时仍可能被后续 unreachable 分支引用，当前因 `_is_runtime_dispatch_exception_outcome` early return 保护而不触发，但结构脆弱）；其余为测试覆盖缺口与 docstring 不一致。无 correctness 阻塞项。

## Scope

- **Mode**: current changes (workspace diff only)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-tools-cancel-01-s2a2-code-review-ds.md`
- **Included scope**:
  - `dayu/host/tool_runtime.py` (workspace diff: +325/-48 lines)
  - `tests/host/test_toolruntime_executor.py` (workspace diff: +244/-48 lines)
  - `dayu/host/README.md` (workspace diff: +2 lines)
  - `docs/reviews/wu-tools-cancel-01-s2a2-implementation-codex.md` (untracked reference)
- **Excluded scope**: committed S2A1 changes, other committed slice changes, `dayu/contracts/tool_execution.py` (S2A1), design docs (read-only context)
- **Parallel review coverage**: 无 — scope 集中在一个模块的两个文件，单人逐行走读即可覆盖

## Context Truth

- Typed plan: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md` S2A2 section
- Design docs: `docs/host/design.md`, `docs/engine/design.md`
- S2A1 commit: `32030ca9` (contract/declaration/digest)
- Implementation codex: `docs/reviews/wu-tools-cancel-01-s2a2-implementation-codex.md`

## Findings

### F01-NEEDS_FIX-中-declaration-backed-factory-未覆盖-capsule-build-failure-回归测试

- **入口/函数**: `ToolRuntimeExecutor._dispatch_tool_call_with_bounds` → `ToolRuntimeExecutor._execute_tool_call_with_governance`
- **文件(行号)**: `dayu/host/tool_runtime.py:3197-3214`（capsule build try/except）、`:2968-2973`（`_is_runtime_dispatch_exception_outcome` 分支）
- **输入场景**: `DeclaredToolExecutionCapsuleFactory.create_capsule` 因工具名不在 effective bundle 中而抛出 `ValueError`，或 `_declared_capsule_for_execution` 因未知 capability 类型抛出 `TypeError`
- **实际分支**: `_dispatch_tool_call_with_bounds:3203-3214` 捕获异常并返回 `(ToolFailedOutcome(error="tool_capsule_build_failed", ...), None)`；`:2968` 处 `_is_runtime_dispatch_exception_outcome` 命中，early return `BatchToolExecutionRecord`
- **预期行为**: capsule build failure 应 bypass accept barrier，标记为 `TOOL_EXCEPTION`，不写入 durable tool fact
- **实际行为**: **当前逻辑正确**——`_is_runtime_dispatch_exception_outcome` 正确识别 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR` 并 early return，不经过 accept barrier
- **直接证据**:
  - `:3203-3214`：try/except 捕获所有异常，统一包装为 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR`
  - `:6514-6528`：`_is_runtime_dispatch_exception_outcome` 检查集合包含 `_TOOL_RUNTIME_CAPSULE_BUILD_FAILED_ERROR`
  - `:2968-2973`：命中后 early return，不进入 `_normalize_runtime_outcome` / accept path
- **影响**: 当前行为正确，但**测试缺失**——没有测试证明 capsule build failure 走完整 `_execute_tool_call_with_governance → _dispatch_tool_call_with_bounds → _is_runtime_dispatch_exception_outcome` 链路。`_is_runtime_dispatch_exception_outcome` 自身的单元行为也未直接测试。如果后续有人重构该检测条件或移动 early return 位置，可能无声回归。
- **建议改法和验证点**:
  1. 新增测试：用 `capsule_factory` 注入一个在 `create_capsule` 中抛 `ValueError` 的 fake factory，验证 executor 返回 `ToolFailedOutcome` 且 error 为 `tool_capsule_build_failed`，且不调用 accept_port
  2. 新增测试：对 `_is_runtime_dispatch_exception_outcome` 的两个命中条件（callable exception、capsule build failure）各一条 parametrized case
- **修复风险（低）**: 仅新增测试，不改生产代码
- **严重程度（中）**: 不是 correctness bug，但关键异常路径无测试保护，属于 structural test gap

### F02-NEEDS_FIX-低-DeclaredToolExecutionCapsuleFactory.create_capsule-docstring-异常类型不准确

- **入口/函数**: `DeclaredToolExecutionCapsuleFactory.create_capsule`
- **文件(行号)**: `dayu/host/tool_runtime.py:1568`
- **输入场景**: 调用方阅读 docstring 了解可能抛出的异常类型
- **实际分支**: docstring 声称 `:raises ValueError: 工具声明缺失或 execution capability 类型未知时抛出`
- **预期行为**: docstring 应准确反映实际抛出的异常类型
- **实际行为**: 工具声明缺失时确实抛出 `ValueError`（`:1574`）；但 execution capability 类型未知时 `_declared_capsule_for_execution` 抛出 `TypeError`（`:1621-1623`），不是 `ValueError`
- **直接证据**:
  - `:1568`：docstring 写 `ValueError` 覆盖两种场景
  - `:1572-1574`：缺失工具时 `raise ValueError(...)`
  - `:1621-1623`：未知 capability 时 `raise TypeError(...)`
- **影响**: 仅文档不准确。由于异常在外层 `_dispatch_tool_call_with_bounds:3203` 由 `except Exception` 统一捕获，无功能影响
- **建议改法和验证点**: 将 docstring 改为分别列出 `ValueError`（工具缺失）和 `TypeError`（未知 capability），或改为 `:raises Exception:`
- **修复风险（低）**: 仅改 docstring
- **严重程度（低）**: 不影响行为，但违反编码硬约束"函数必须提供完整中文 docstring，至少包含参数、返回值、异常"的准确性要求

### F03-NEEDS_FIX-低-缺少-declaration-backed-async_direct-与-thread_backed-默认路径集成测试

- **入口/函数**: `DefaultToolRuntimeFactory.create_tool_runtime` → `DeclaredToolExecutionCapsuleFactory.create_capsule`
- **文件(行号)**: `dayu/host/tool_runtime.py:3983-3986`（factory 选择）、`:1544-1580`（DeclaredToolExecutionCapsuleFactory）
- **输入场景**: 生产路径下，`ToolRuntimeBuildRequest.execution_capsule_factory` 为 `None`，工具声明 `execution` 为 `AsyncDirectToolExecutionCapability()` 或 `ThreadBackedToolExecutionCapability()`
- **实际分支**: `DefaultToolRuntimeFactory` 创建 `DeclaredToolExecutionCapsuleFactory(effective_bundle)`，`create_capsule` 读取 `ToolDefinition.execution` 并创建对应 capsule
- **预期行为**: `async_direct` 和 `thread_backed` 声明应正确路由到对应 capsule
- **实际行为**: 代码路径正确——`:1601-1606` 处理 `async_direct`，`:1607-1614` 处理 `thread_backed`。但**测试只覆盖了 `process_backed` 的声明路径**（`test_tool_runtime_default_factory_uses_declared_process_backed_execution`），没有通过默认 factory（`execution_capsule_factory=None`）验证 `async_direct` 和 `thread_backed` 声明路由
- **直接证据**:
  - 新增测试 `test_tool_runtime_default_factory_uses_declared_process_backed_execution` 只覆盖 `execution=ProcessBackedToolExecutionCapability(...)`
  - 现有 `async_direct` 测试仍然通过 `_executor` helper 的默认路径（`execution=None` → `AsyncDirectToolExecutionCapability()`），行为等价但未显式验证声明→capsule 路由
  - `thread_backed` 声明路径无集成测试
- **影响**: `async_direct` 和 `thread_backed` 的声明路由未被直接测试证明。由于 `_executor` helper 现有默认路径等价于 `async_direct` 声明路由，实际回归风险低
- **建议改法和验证点**:
  1. 新增测试：`_executor(callable_, accept_port)`（不传 `execution`，不传 `capsule_factory`）验证默认 `async_direct` 路由且 callable 被实际调用
  2. 新增测试：`_executor(callable_, accept_port, execution=ThreadBackedToolExecutionCapability())` 验证 `thread_backed` 声明路由
- **修复风险（低）**: 仅新增测试
- **严重程度（低）**: 当前路径由等价路径间接覆盖，风险可控

## Open Questions

1. **`tests/README.md` 触发检查是否充分**: CLAUDE.md 规定 `tests/` 修改须检查并按需更新 `tests/README.md`。Implementation codex 称 "No update needed: existing test layering already covers Host ToolRuntime executor focused tests and no new test directory or test layer was introduced." 本次 workspace diff 在 `tests/host/test_toolruntime_executor.py` 新增 ~200 行测试（4 个新 test function + helper 重构），未新增测试目录或测试层。判断合理，无强证据要求必须更新 `tests/README.md`。

2. **`ProcessBackedToolExecutionCapsule.run()` 中 `InterruptibleProcessStillRunning` 分支可达性**: `:1796-1801` 处理 `InterruptibleProcessStillRunning` 并返回 `_PROCESS_BACKED_TOOL_UNEXPECTED_PENDING_ERROR`。由于 `run()` 调用 `self._handle.wait(timeout_seconds=None)`（无限等待），该分支在正常流程中不可达。但它作为 defensive 分支（防止未来 `wait` 实现变更引入非 None 默认 timeout）是合理的。不构成 dead code。

## Residual Risk

1. **`thread_backed` 声明路由无集成测试**: 见 F03。当前 `test_thread_backed_capsule_does_not_claim_thread_termination` 直接构造 `ThreadBackedToolExecutionCapsule` 而非通过声明路由，不覆盖 factory wiring 路径。

2. **capsule build failure 与 `durable_missing_reason` 的交互未穷尽**: 当 `_is_runtime_dispatch_exception_outcome` early return 时（`:2968-2973`），`durable_missing_reason` 设为 `TOOL_EXCEPTION`，`policy_decision` 保持为之前的 ALLOW 决策。若未来有人在 early return 之前插入使用 `policy_decision` 的代码（如额外的 policy check），可能因 `policy_decision` 语义不匹配（ALLOW 但实际 capsule build 失败）而引入 bug。当前代码路径安全，但结构性风险值得在 F01 修复测试中覆盖。

3. **`ProcessBackedToolExecutionCapsule` 不验证 target 返回值确实是 JsonValue**: `run()` 直接信任 `InterruptibleProcessCompleted.value` 为 `JsonValue` 并传给 `_tool_outcome_from_process_envelope`。类型层面由 `InterruptibleProcessTarget.__call__() -> JsonValue` 协议保证；运行时若子进程返回非 JSON 兼容对象（如包含不可序列化类型的 dict），会在 pickle/serialization 层失败（`InterruptibleProcessFailed`），不会到达 envelope 解析。但 envelope 解析层不做额外类型检查（如检查 value 是否为合法 JsonValue），依赖上游保证。风险可控——进程边界天然提供序列化隔离。

4. **`DeclaredToolExecutionCapsuleFactory` 持有 `EffectiveToolBundle.definitions_by_name` 引用**: `EffectiveToolBundle` 是 frozen dataclass，`definitions_by_name` 是 `MappingProxyType`，均为不可变。但若未来 `EffectiveToolBundle` 变为 mutable 或在 attempt 生命周期中被替换，factory 持有的旧引用可能过时。当前架构下 attempt-scoped factory 与 effective bundle 生命周期一致，无实际风险。

5. **测试只验证 pyright 0 errors 和 pytest 52 passed**: 未执行完整测试套件（`pytest tests/host/ -q`），其余 Host 测试可能受 `ToolRuntimeBuildRequest.execution_capsule_factory` 默认值变更影响。Implementation codex 报告 `tests/host/test_toolruntime_effective_bundle.py` 和 `tests/host/test_package_exports.py` 均通过（20 passed）；本 review 额外验证 `test_toolruntime_duplicate_governance.py` 和 `test_tool_runtime_schema_projection.py` 通过（45 passed）。其他 Host 测试文件仅 S2A1 做了 import 兼容性批量更新（`:2` lines changed per file），应无回归风险。
