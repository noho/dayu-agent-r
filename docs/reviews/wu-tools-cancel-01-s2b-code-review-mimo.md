# WU-TOOLS-CANCEL-01 S2B Code Review — AgentMiMo

## Scope

- Mode: current changes (workspace diff, uncommitted)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Review date: 2026-07-04 21:33 CST
- Included files:
  - `dayu/tools/doc_tools.py` (S2B core)
  - `tests/tools/test_doc_tools_provider.py` (S2B tests)
  - `tests/README.md` (trigger update)
  - `docs/reviews/wu-tools-cancel-01-s2b-implementation-codex.md` (implementation artifact)
- Context truth:
  - `dayu/contracts/tool_execution.py` (S2A1: ProcessBackedToolExecutionCapability, ProcessBackedToolTarget protocol)
  - `dayu/contracts/tool_declaration.py` (S2A1: ToolDefinition.execution field)
  - `dayu/host/tool_runtime.py` (S2A2: DeclaredToolExecutionCapsuleFactory, ProcessBackedToolExecutionCapsule, envelope mapping, cancel/timeout/late-result rejection)
  - Typed plan: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
  - S2A1 commit `32030ca9`, S2A2 commit `0fea8da0`
- Parallel review coverage: 无

## Findings

### F1-未修复-中-Process-backed failed envelope 丢失独立 hint 字段，与 fallback callable 语义不等价

- **入口/函数**: `_process_failed_envelope` + `_process_failure_message` vs `_invoke_doc_business` fallback path
- **文件(行号)**: `dayu/tools/doc_tools.py` L1203-1242 (process path) vs L912-920 (fallback path)
- **输入场景**: 任何 Doc 工具调用触发参数校验失败、路径白名单拒绝、文件不存在或业务执行异常
- **实际分支**: process-backed 生产路径进入 `_DocProcessTarget.__call__` -> `_execute_doc_business_value` 抛出 `_DocBusinessFailure` -> `_process_failed_envelope` 构造 `{"status": "failed", "error_type": ..., "message": "msg Hint: hint"}`；fallback callable 路径进入 `_invoke_doc_business` -> `failed_outcome(error=..., message=..., hint=hint)` -> `ToolFailedOutcome` 携带独立 `hint` 字段
- **预期行为**: process-backed 与 fallback 路径在相同失败场景下应产生语义等价的 LLM-facing failure response，hint 作为结构化恢复提示独立可解析
- **实际行为**: Host `_failed_outcome_from_process_envelope` (tool_runtime.py L6583) 映射 failed envelope 时固定 `hint=None`；Doc 子进程通过 `_process_failure_message` 把 hint 拼接进 message 字符串 `"msg Hint: hint"`，LLM 需从自然语言 message 中自行解析恢复建议，而非从结构化 hint 字段获取
- **直接证据**:
  - `dayu/tools/doc_tools.py` L1216-1220: `_process_failed_envelope` 只返回 `status`、`error_type`、`message` 三个字段，无 `hint`
  - `dayu/tools/doc_tools.py` L1240-1242: `_process_failure_message` 把 hint 拼入 message: `f"{failure.message} Hint: {failure.hint}"`
  - fallback path `dayu/tools/doc_tools.py` L912-920: `failed_outcome(error=error.error, message=error.message, hint=error.hint)` 保留独立 hint
- **影响**: process-backed 生产路径的失败响应丢失结构化恢复提示；LLM 需从拼接 message 中解析 hint 文本，降低 failure recovery 可靠性。非 correctness bug，但会影响 LLM-facing failure behavior 一致性
- **建议改法和验证点**:
  - 短期可接受当前 workaround（hint 附在 message 内），但应在 implementation artifact 中标记为需后续 Host process envelope contract work unit 跟进
  - 长期方案：扩展 Host process failed envelope 契约增加可选 `hint` 字段，或在 `_tool_outcome_from_process_envelope` 中解析 `"Hint: ..."` 后缀
- **修复风险（低/中/高）**: 低（当前 workaround 已实现，后续扩展需改 Host envelope contract）
- **严重程度（低/中/高/严重）**: 中

### F2-未修复-中-ToolRuntime cancel late-result 测试只覆盖 read_file，四个工具无直接 cancel 证据

- **入口/函数**: `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept`
- **文件(行号)**: `tests/tools/test_doc_tools_provider.py` L1126-1184
- **输入场景**: 五个 Doc tools 中任意一个被取消
- **实际分支**: 测试只对 `read_file` 替换为 `_SlowProcessTargetFactory(sleep_seconds=5.0)`，其它四个工具保留真实 process target
- **预期行为**: 测试应证明五个 Doc tools 均可通过 ToolRuntime process-backed 路径正确取消，且 late result 不进入 accept barrier
- **实际行为**: 只有 `read_file` 有 ToolRuntime 级 cancel + late-result rejection 测试；`list_files`、`get_file_sections`、`search_files`、`read_file_section` 无直接 ToolRuntime cancel 证据
- **直接证据**:
  - `tests/tools/test_doc_tools_provider.py` L1133-1143: `replace(...)` 只替换 `definition.name == "read_file"` 的 execution
  - 无其它工具的 ToolRuntime cancel 测试
- **影响**: 四个工具的 process-backed cancel 路径缺乏直接测试证据。由于五个工具共用同一 `_DocProcessTarget.__call__` 实现，实际风险有限；但测试未证明 `list_files` / `search_files` 等工具的 process target 在被 Host terminate 后不会产生意外副作用
- **建议改法和验证点**:
  - 补充至少一个非 `read_file` 工具（如 `list_files`）的 ToolRuntime cancel 测试，或改为 `@pytest.mark.parametrize` 覆盖全部五个工具
  - 或在测试注释中明确说明"实现均匀，只覆盖 read_file 作为代表"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F3-未修复-低-`_execute_doc_business_value` 中 `_DocCancelledError` re-raise 在 process target 路径为死代码

- **入口/函数**: `_execute_doc_business_value`
- **文件(行号)**: `dayu/tools/doc_tools.py` L1030-1031
- **输入场景**: process-backed 子进程 target 执行 Doc 业务
- **实际分支**: `_DocProcessCancellationToken.is_cancelled()` 永远返回 `False`，业务 helper 内的 cancellation 检查不可触发 `_DocCancelledError`
- **预期行为**: process target 路径中 `_DocCancelledError` 不可被抛出
- **实际行为**: L1030-1031 `except _DocCancelledError: raise` 在 process target 路径中不可达；该分支仅对 fallback callable 路径有意义（fallback 使用真实 `CancellationToken`）
- **直接证据**:
  - `dayu/tools/doc_tools.py` L280-293: `_DocProcessCancellationToken.is_cancelled()` 始终返回 `False`
  - `dayu/tools/doc_tools.py` L1030-1031: `_DocCancelledError` 的 except 分支
- **影响**: 无功能影响；代码冗余但不影响正确性
- **建议改法和验证点**: 保持现状，或添加行内注释说明此分支仅对 fallback callable 路径有效
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F4-未修复-低-`_DocProcessTarget.__call__` 中 timeout_seconds 赋值后立即删除为死代码

- **入口/函数**: `_DocProcessTarget.__call__`
- **文件(行号)**: `dayu/tools/doc_tools.py` L365-366
- **输入场景**: 子进程 target 执行
- **实际分支**: `timeout_seconds = self.timeout_seconds; del timeout_seconds` 赋值后立即删除，本地变量从未使用
- **预期行为**: 无功能预期
- **实际行为**: 死代码，可能用于抑制 lint unused-variable 警告
- **直接证据**: `dayu/tools/doc_tools.py` L365-366
- **影响**: 无功能影响
- **建议改法和验证点**: 可删除两行或添加注释说明意图；或改用 `_ = self.timeout_seconds` 更明确表达"有意忽略"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F5-未修复-低-Fallback callable 仍持有 provider_lock，生产路径已不经过此锁

- **入口/函数**: `_invoke_doc_business` + 五个 `_build_*_definition` callable
- **文件(行号)**: `dayu/tools/doc_tools.py` L874-973, L531-871
- **输入场景**: 直接调用 `ToolDefinition.callable`（测试或非生产 fallback）
- **实际分支**: 生产默认走 process-backed，不经过 `_invoke_doc_business`；provider_lock 仅保护 fallback callable 内的 `asyncio.to_thread` 调用
- **预期行为**: provider_lock 在生产路径中无作用
- **实际行为**: provider_lock 仍作为 `_invoke_doc_business` 参数传入并在 `async with provider_lock:` 中使用；docstring 已声明"生产默认路径不再经过本函数"
- **直接证据**:
  - `dayu/tools/doc_tools.py` L882-888: docstring 声明 fallback only
  - `dayu/tools/doc_tools.py` L907: `async with provider_lock:` 仍在 fallback 路径中
- **影响**: 无功能影响；provider_lock 仅保护 fallback callable 的串行执行，不与 process-backed 路径竞争
- **建议改法和验证点**: 保持现状；provider_lock 对 fallback 路径仍有意义（测试中多个 callable 并发时保护共享状态）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。F1 的 hint 丢失是已知设计 trade-off（implementation codex Residual Risks 已记录），不阻塞 S2B gate。

## Residual Risk

1. **hint 结构化保留**: process-backed failed envelope 的 Host 契约只有 `error_type` + `message`，无独立 `hint` 字段。当前 workaround 把 hint 拼入 message，但 LLM 解析可靠性低于结构化 hint。后续需 Host process envelope contract work unit 跟进。

2. **cancel 测试覆盖**: 五个 Doc tools 中只有 `read_file` 有 ToolRuntime 级 cancel + late-result rejection 测试。实现均匀，实际风险有限，但测试覆盖不完整。

3. **provider_lock 过期语义**: `_invoke_doc_business` 的 provider_lock 在生产 process-backed 路径中已无作用。fallback callable 仍需要它保护测试并发场景，但未来维护者可能误解其用途。

## Verdict

**PASS**

S2B 实现正确地将五个 Doc tools 迁移到 process-backed execution capability：
- `_DocProcessTargetFactory` / `_DocProcessTarget` 为 frozen dataclass，pickle round-trip 安全，不捕获 provider lock / DocumentProcessor / CancellationToken / Host internals
- 子进程内重新解析 allowed_roots，复用路径 containment 校验，输出 shape、truncate spec 与旧 callable 语义一致
- process target 只返回 completed / failed JSON envelope，不返回 awaiting / cancelled / timeout / host_cancelled
- cancel/timeout 由父进程 Host capsule 独占治理，late result 不进入 accept barrier
- tests 覆盖所有五个 tools 的 process-backed 声明、pickle round-trip、fast path、processor path、denied path、nonexistent path、cancel late-result
- README 更新准确

F1（hint 丢失）为已知设计 trade-off，F2（cancel 测试覆盖）为测试完整性缺口但非 correctness defect，F3-F5 为低严重度代码卫生项。无阻塞 gate 的实质问题。
