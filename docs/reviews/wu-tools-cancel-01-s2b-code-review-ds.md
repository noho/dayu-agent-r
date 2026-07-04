# WU-TOOLS-CANCEL-01 S2B Code Review — AgentDS

## Verdict

**NEEDS_FIX** — 两个 MEDIUM findings 需要在 merge 前处理或明确裁决。

## Scope

- **Mode**: current changes (workspace diff only)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main` (S2A2 commit `0fea8da0`)
- **Output file**: `docs/reviews/wu-tools-cancel-01-s2b-code-review-ds.md`
- **Included scope**:
  - `dayu/tools/doc_tools.py` — S2B Doc process-backed 迁移
  - `tests/tools/test_doc_tools_provider.py` — 新增/修改测试
  - `tests/README.md` — Doc provider 覆盖说明更新
  - `docs/reviews/wu-tools-cancel-01-s2b-implementation-codex.md` — Codex 实现报告
- **Excluded scope**: 已提交的 S2A1/S2A2 commits、其他未修改文件
- **Context truth documents read**: `dayu/contracts/tool_execution.py`、`dayu/host/tool_runtime.py`（execution capsule dispatch / cancel governance / process envelope mapping）、`dayu/runtime/cancellation.py`（`wait_for_or_cancel`）、`dayu/runtime/interruptible_process.py`（`InterruptibleProcessTarget` protocol）

## Execution Walkthrough Summary

以下是对生产 process-backed 主链路的完整走读确认：

1. **`build_doc_tool_definitions()`**（`doc_tools.py:488`）为五个 Doc 工具各构造一个 `_DocProcessTargetFactory`，传入 `_tool_definition()`。

2. **`_tool_definition()`**（`doc_tools.py:2126`）硬编码 `execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory)`。五个工具的 `ToolDefinition.execution` 均为 `ProcessBackedToolExecutionCapability`。✓

   - 不再有 `AsyncDirectToolExecutionCapability`；无配置开关可使 Doc 工具回退到 async direct。✓

3. **生产执行路径**：`ToolRuntimeExecutor.execute()` → `_dispatch_tool_call_with_bounds()` → `self._execution_capsule_factory.create_capsule()`。

   - 生产默认 `execution_capsule_factory` 为 `DeclaredToolExecutionCapsuleFactory`（`tool_runtime.py:3984-3987`），按 `definition.execution` dispatch。✓
   - `_declared_capsule_for_execution()`（`tool_runtime.py:1616`）匹配 `isinstance(execution, ProcessBackedToolExecutionCapability)` → 调用 `execution.target_factory.build_process_target(call, process_backed_context)` → 构造 `ProcessBackedToolExecutionCapsule(target)`。✓
   - `definition.callable` **不进入生产执行路径**；仅测试直接调用。✓

4. **取消路径**：`wait_for_or_cancel()` 检测到 token 取消 → 返回 `WaitCancelled` → `_interrupt_capsule_after_wait()` 执行 `request_interrupt` → `terminate` → `kill`（如需）→ 取消 capsule task → `close` → 返回 `_governed_failure_outcome(decision)`，`hint="tool_runtime_cancelled"`。✓

   - late result（capsule task 在 cancel 后完成）不会进入 accept barrier；其值被丢弃。✓

5. **子进程执行**：`_DocProcessTarget.__call__()` 调用 `_execute_doc_business_value()` → 参数校验 → 路径白名单校验 → `_route_doc_business()` → 对应业务 helper。成功返回 `{"status": "completed", "value": ...}`；失败返回 `{"status": "failed", "error_type": ..., "message": ...}`。✓

6. **Envelope 字段对齐**：`doc_tools.py` 的 `_DOC_PROCESS_STATUS_FIELD` / `_DOC_PROCESS_COMPLETED_STATUS` / `_DOC_PROCESS_FAILED_STATUS` / `_DOC_PROCESS_VALUE_FIELD` / `_DOC_PROCESS_ERROR_TYPE_FIELD` / `_DOC_PROCESS_MESSAGE_FIELD` 与 `tool_runtime.py` 的 `_PROCESS_ENVELOPE_*` 常量字面量一致（均为 `"status"`、`"completed"`、`"failed"`、`"value"`、`"error_type"`、`"message"`）。✓

## Findings

### 01-NEEDS_FIX-MEDIUM-process-backed-failed-envelope-hint语义丢失

- **入口/函数**: `_failed_outcome_from_process_envelope()` → `_tool_failed_outcome(error=error_type, message=message, hint=None)`
- **文件(行号)**: `dayu/host/tool_runtime.py:6583-6607`
- **输入场景**: 子进程 Doc 工具因 `file_not_found`、`permission_denied`、`invalid_argument` 等业务原因返回 `{"status": "failed", "error_type": "file_not_found", "message": "..."}` 信封
- **实际分支**: Host `_failed_outcome_from_process_envelope()` 将 `error_type` 映射为 `ToolFailedOutcome.result.error`，`message` 映射为 `ToolFailedOutcome.result.message`，但 **`hint` 硬编码为 `None`**
- **预期行为**: 与 callable fallback 路径一致，`hint` 应包含恢复提示（如 `"Verify the file path and retry."`）
- **实际行为**: `ToolFailedOutcome.result.hint` 始终为 `None`

  Doc 侧 `_process_failure_message()`（`doc_tools.py:1223`）将 hint 嵌入 message 文本：`"Hint: Verify the file path and retry."`，但下游若按结构化字段读取 `hint`（而非解析 message），会看到空值。

- **直接证据**:
  - `tool_runtime.py:6603-6607`: `_tool_failed_outcome(error=error_type, message=message, hint=None)`
  - `tool_runtime.py:254-255`: process envelope 契约只定义了 `error_type` 和 `message`，无 `hint` 字段
  - `doc_tools.py:1240-1242`: `_process_failure_message()` 把 hint 附在 message 内作为 workaround

- **影响**: process-backed 生产路径与 callable fallback 路径对 LLM 的失败输出结构不一致。如果 Engine 或上层消费者按 `ToolFailedOutcome.result.hint` 字段做分支判断或 LLM prompt 构造，process-backed 路径会静默丢失恢复提示（仅 message 中包含）。
- **建议改法和验证点**:
  1. **短期**（本轮可接受）: 在 `_process_failure_message()` 的 docstring 中已有明确说明，且所有 process target 测试验证了 `error_type` 的正确性。当前 LLM-facing 影响有限（hint 文本仍在 message 中）。若接受此 tradeoff，应在 design doc 或 control doc 中记录为 deferred work unit。
  2. **长期**: 在 Host process envelope 契约中增加可选的 `hint` 字段，修改 `_failed_outcome_from_process_envelope()` 读取并透传。
- **修复风险（低）**: 若本轮只记录不修，零风险；若本轮修改 Host 公共契约，中等风险（需同步更新 `_PROCESS_ENVELOPE_FAILED_*` 常量、envelope 解析、以及所有 process-backed tool provider）。
- **严重程度（中）**:

---

### 02-NEEDS_FIX-MEDIUM-cancel-test未覆盖真实Doc-process-target

- **入口/函数**: `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept`
- **文件(行号)**: `tests/tools/test_doc_tools_provider.py:1126-1184`
- **输入场景**: ToolRuntime cancel 路径测试
- **实际分支**: 测试将 `read_file` 的 execution 替换为 `_SlowProcessTargetFactory(sleep_seconds=5.0)`，使用 `time.sleep()` 阻塞的 fake target
- **预期行为**: 应验证真实 `_DocProcessTarget` 在 cancel 后正确被 terminate/kill，不会产生 late accept
- **实际行为**: 测试只验证了 ToolRuntime cancel → govern → accept barrier 的通用 framework 路径，未验证：
  1. 真实 `_DocProcessTarget` 在 `_DocProcessCancellationToken`（永不取消）下被 terminate 时，文件 I/O 或 Docling processor 是否能正确释放
  2. `_DocProcessTarget` 的子进程在被 kill 后是否留下僵尸进程或资源泄漏
  3. `_DocProcessTarget.__call__()` 中 `create_doc_file_processor(path)` 的 processor 创建在 terminate/kill 下的行为

- **直接证据**:
  - `test_doc_tools_provider.py:1133-1143`: `execution=ProcessBackedToolExecutionCapability(target_factory=_SlowProcessTargetFactory(sleep_seconds=5.0))` — 替换为 fake
  - `test_doc_tools_provider.py:1098-1107`: `_SlowCompletedProcessTarget.__call__()` — 仅 `time.sleep()` + 返回固定 envelope
  - 对比：其他 process target 测试（`test_doc_process_target_fast_path_matches_callable_baseline`、`test_doc_process_target_processor_path_supports_docling_sections`）使用的是真实 `_DocProcessTarget`，但均为成功路径

- **影响**: cancel 路径对 Doc 工具子进程的正确性仅有 framework 级别担保，缺少业务级别验证。如果 Docling processor 或文件 I/O 在收到 SIGTERM 时进入不可中断状态，cancel grace period 可能不足，但测试无法发现。
- **建议改法和验证点**:
  1. 新增测试：使用真实 `_DocProcessTarget`（或真实 `_DocProcessTargetFactory`）+ 大文件/慢 processor，触发 cancel，验证：
     - `elapsed < PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS + PROCESS_CAPSULE_KILL_GRACE_SECONDS + buffer`
     - accept barrier 仅 1 个 candidate，`reason_code == "tool_runtime_cancelled"`
  2. 或在已有 `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept` 中增加一个不替换 execution 的变体，使用真实的 `_DocProcessTargetFactory`
- **修复风险（低）**: 新增测试不改变生产代码
- **严重程度（中）**:

---

### 03-NEEDS_FIX-LOW-process-target参数校验失败路径缺少测试

- **入口/函数**: `_DocProcessTarget.__call__()` → `_execute_doc_business_value()` → `validate_and_project_arguments()` 失败分支
- **文件(行号)**: `dayu/tools/doc_tools.py:374-384`（`_DocProcessTarget.__call__` 中 `except _DocBusinessFailure`）、`dayu/tools/doc_tools.py:1008-1010`（validation failure → `raise _DocBusinessFailure`）
- **输入场景**: 对 process target 传入非法参数（如缺少必填字段、类型错误、路径非字符串）
- **实际分支**: `validate_and_project_arguments()` 返回 `ToolArgumentValidationFailure` → `raise _DocBusinessFailure(validation.error, validation.message, validation.hint)` → 被 `_DocProcessTarget.__call__()` 的 `except _DocBusinessFailure` 捕获 → `_process_failed_envelope(failure)`
- **预期行为**: 返回 `{"status": "failed", "error_type": "...", "message": "..."}`
- **直接证据**: 现有 process target 测试均使用合法参数，没有测试参数校验失败的 envelope 形状
- **影响**: 参数校验失败 envelope 的 `error_type` / `message` / hint-embedding 行为未被测试覆盖；未来修改 `validate_and_project_arguments` 返回格式或 `_DocBusinessFailure` 构造时可能静默破坏
- **建议改法和验证点**: 新增 `test_doc_process_target_argument_validation_failure`，传入非法参数（如缺少 `file_path`），验证 envelope `status == "failed"` 且 `error_type` 包含合法值
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**:

---

### 04-NEEDS_FIX-LOW-process-target泛化异常捕获路径缺少测试

- **入口/函数**: `_DocProcessTarget.__call__()` → 裸 `except Exception:` 分支
- **文件(行号)**: `dayu/tools/doc_tools.py:385-390`
- **输入场景**: `_execute_doc_business_value()` 或其依赖（`_parameters_for_tool`、`_resolve_allowed_root_locators`）抛出非 `_DocBusinessFailure` 的未预期异常
- **实际分支**: `except Exception:` → 返回 `{"status": "failed", "error_type": "execution_error", "message": "Tool 'read_file' execution failed."}`
- **预期行为**: 返回 generic failed envelope
- **直接证据**: 该 `except Exception:` 分支无法通过正常参数触发；现有测试未覆盖
- **影响**: 该兜底路径的正确性未验证（message 格式字符串、envelope 结构）；在 monkeypatch 下可测
- **建议改法和验证点**: 通过 monkeypatch `_resolve_allowed_root_locators` 使其抛出 `RuntimeError`，验证 envelope 形状
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**:

---

### 05-INFO-AGENT_NOTE-callable-fallback双路径语义已正确隔离

此条不是 finding，而是对 review 指令中"direct callable fallback 是否造成双真源"的确认答复：

- **确认结论**: 不造成双真源。
- **证据**:
  1. 生产 `ToolExecutor` 通过 `DeclaredToolExecutionCapsuleFactory.create_capsule()` → `_declared_capsule_for_execution(execution=definition.execution, ...)` dispatch（`tool_runtime.py:1576-1581`），不使用 `definition.callable`
  2. 五个 Doc 工具的 `definition.execution` 均为 `ProcessBackedToolExecutionCapability`（`doc_tools.py:2165-2167`），无 fallback 到 async direct 的路径
  3. `_invoke_doc_business()` docstring 明确标注为 fallback/test-only（`doc_tools.py:882-888`）
  4. 生产 `execution_capsule_factory` 在 `DefaultToolRuntimeFactory.create_tool_runtime()` 中默认为 `DeclaredToolExecutionCapsuleFactory`（`tool_runtime.py:3984-3987`），仅在测试通过 `request.execution_capsule_factory` 覆盖
- **旧 `to_thread`/`provider_lock` 路径**: 保留在 `_invoke_doc_business()` 中供测试使用；不被生产默认路径消费。不是 closeout 证据。

---

### 06-INFO-AGENT_NOTE-DocProcessCancellationToken子进程取消语义

此条不是 finding，而是对 review 指令中"子进程 cancel/timeout 由父进程 Host capsule 独占治理"的确认答复：

- **确认结论**: 正确实现。
- **证据**:
  1. `_DocProcessCancellationToken.is_cancelled()` 始终返回 `False`（`doc_tools.py:293`）
  2. 子进程内所有 `_raise_if_doc_cancelled()` 和 `_raise_if_doc_cancelled_at_interval()` 调用均使用 `_DocProcessCancellationToken`，因此永不触发协作式取消
  3. 子进程内 `_DocCancelledError` 永远不会被抛出（死代码路径 in child process，但共享的 `_execute_doc_business_value` 中 `except _DocCancelledError: raise` 在 fallback callable 路径仍有效）
  4. 真实取消由父进程 `ProcessBackedToolExecutionCapsule.terminate()` / `kill()` 执行（`tool_runtime.py:1817-1849`）

---

### 07-INFO-AGENT_NOTE-pickle安全性确认

此条不是 finding，而是对 review 指令中"是否捕获或传递不可序列化/不该跨进程对象"的确认答复：

- **确认结论**: 未捕获任何不可序列化对象。
- **证据**:
  1. `_DocProcessTargetFactory` 字段: `allowed_root_locators: tuple[str, ...]`、`limits: DocToolLimits`（frozen dataclass with int fields only）✓
  2. `_DocProcessTarget` 字段: `tool_name: str`、`arguments: dict[str, JsonValue]`、`allowed_root_locators: tuple[str, ...]`、`limits: DocToolLimits`、`timeout_seconds: float | None` ✓
  3. 测试 `test_doc_process_target_factory_is_pickle_round_trippable` 对五个工具逐一验证 pickle round-trip（`test_doc_tools_provider.py:1148-1179`）
  4. `build_process_target()` 通过 `dict(call.arguments)` 创建 JSON 副本，断开与原始 `ToolCallRequest` 的引用（`doc_tools.py:439`）
  5. 无 `provider_lock`、`DocumentProcessor`、`CancellationToken`、Host internals 在 factory 或 target 中

- **注意**: `DocToolLimits` 可 pickle（纯 int 字段的 frozen dataclass），但若未来有人往 `DocToolLimits` 添加不可序列化字段，pickle round-trip 测试会直接失败。当前安全。

---

## Open Questions

1. **Process envelope hint 契约演进时间线**: Codex review 将 hint 丢失标记为 residual risk 并建议独立 work unit 处理。本轮是否接受此 tradeoff（hint 嵌入 message）并记录为 deferred，还是需要本轮就修改 Host 公共契约？
2. **Cancel 测试是否需要覆盖真实 Docling processor**: Finding 02 建议增加真实 Doc 业务 cancel 测试。考虑到 Docling 依赖可能较大，是否接受当前 fake target 测试作为 framework-level 充分覆盖？

## Residual Risk

1. **Process envelope hint 结构化丢失**: 已在 Finding 01 详述。短期通过 message-embedded hint workaround 缓解；长期需 Host contract 演进。

2. **Docling processor SIGTERM 响应**: 当前无测试覆盖 `create_doc_file_processor()` 创建的真实 processor 在收到 SIGTERM 时的行为。`_DOC_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` + kill grace 可能不足以等待某些 I/O 操作。如果 Docling 的 C extension 不响应 Python signal handler，kill 可能留下僵尸子进程。这是 process-backed 架构的固有风险，非本轮引入。

3. **Subprocess `_DocProcessCancellationToken` 异常安全**: 子进程内所有业务 helper 的取消检查被禁用，意味着子进程在 terminate/kill 之前会一直运行。对于极大文件或极慢 processor，子进程可能在被终止前消耗大量 CPU/内存。当前 `DocToolLimits` 默认值（如 `read_file_max_chars=80000`）限制了单次调用的数据量，降低了此风险。

4. **测试未覆盖的工具**: `list_files`、`search_files`、`read_file_section` 的 process target 成功路径未直接测试（仅 `read_file` fast path 和 `get_file_sections` processor path 有测试）。这些工具的 code path 与已测工具共享 `_execute_doc_business_value()` → `_route_doc_business()`，风险较低但非零。

5. **`tests/README.md` 更新准确性**: 已移除 "provider 级串行策略" 表述，新增 "process-backed execution 声明、process target 可序列化与子进程内路径校验，以及 current ToolRuntime accept barrier / cancel 后 late result 不接受集成"。描述准确反映当前测试覆盖范围。✓
