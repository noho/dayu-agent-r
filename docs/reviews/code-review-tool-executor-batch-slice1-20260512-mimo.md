# Code Review

## Scope

- Mode: current changes (Gateflow Slice 1 review)
- Branch: `host/phase_0_design`
- Base: `main`
- Output file: `docs/reviews/code-review-tool-executor-batch-slice1-20260512-mimo.md`
- Included scope: Slice 1 实现范围 —— `dayu/contracts/`、`dayu/engine/agent.py`、`dayu/engine/contracts/`、相关测试、README 与 design doc
- Excluded scope: `dayu/engine/runners/openai/` 内部 Runner 实现（非 Slice 1 核心）、`dayu/runtime/`、`dayu/host/`、`dayu/fins/`
- Parallel review coverage: 无（子 agent 模型不可用，主 reviewer 直接全量走读）
- Implementation artifact: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
- Approved plan: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- Controller decision status: 见各 finding 标注

## Findings

### 1-未修复-低-stale `ToolExecutionContext` 在 `docs/host/design.md`

**Controller decision**: resolved/fixed —— `docs/host/design.md` L657/L667 已改为 `BatchToolExecutionContext`；L1151/L1159/L1198 同步更新到新公共契约名（见 `docs/reviews/gateflow-fix-tool-executor-batch-slice1-20260512.md` §2.2）。

- **入口/函数**: N/A（文档）
- **文件(行号)**: `docs/host/design.md:657`、`docs/host/design.md:667`
- **输入场景**: 读者查阅 Host 设计文档时会看到已移除的旧契约名。
- **实际分支/行为**: 文档仍引用 `ToolExecutionContext`，该类已在公共契约层完全移除。
- **预期行为**: 应改为 `BatchToolExecutionContext`。
- **直接证据**:
  - 行 657: `普通日志、RunEvent payload、ToolExecutionContext、public stream 和 README 示例都不能泄露明文 token。`
  - 行 667: `ToolRuntime 不获得 owner token，也不把 owner token 放入 ToolExecutionContext。Host 通过内部...`
- **影响**: 仅文档不一致，不影响运行时行为；但会误导新加入的开发者以为 `ToolExecutionContext` 仍然存在。
- **建议改法和验证点**: 将两处 `ToolExecutionContext` 替换为 `BatchToolExecutionContext`；`grep -r "ToolExecutionContext" docs/` 确认无残留。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未通过-中-`_call_tool_executor` CancelledError 归因歧义

**Controller decision**: controller-rejected/deferred —— commit-edge 取舍是有意设计，docstring 已记录；不在 Slice 1 范围扩展 outcome variant 以区分 executor 内部 CancelledError 与 run-level cancel。

- **入口/函数**: `_AsyncAgent._call_tool_executor`
- **文件(行号)**: `dayu/engine/agent.py:1763-1772`
- **输入场景**: `ToolExecutor.execute` 内部自行抛出 `CancelledError`（非 run-level 取消），同时 `cancellation_token.is_cancelled()` 为 `True`。
- **实际分支/行为**: `CancelledError` 被 re-raise，外层 `_execute_batch` 中 `await_or_cancel_or_timeout` 将其归因为 `WaitCancelled`，最终产出 `RUN_CANCELLED` 终态。
- **预期行为**: 若 executor 内部 `CancelledError` 是 executor 自身超时或内部取消策略触发（而非 Host 主动取消），归因为 `RUN_CANCELLED` 可能掩盖真实原因。设计文档明确说"当前批式握手边界的有意归因取舍"，但该取舍在 docstring 中仅部分说明。
- **直接证据**:
  - `agent.py:1765-1767`: `if self._request.cancellation_token.is_cancelled(): raise`
  - docstring 行 1754-1758: "Engine 将 CancelledError 加上已取消 token 归因为 run-level cancellation；若 executor 自行抛出 CancelledError 且 token 同时被取消，也会按 run cancellation 处理。这是当前批式握手边界的有意归因取舍"
- **影响**: 在 Host 主动取消与 executor 内部取消同时发生的边界，取消原因可能被错误归因。当前设计文档已记录此取舍，但调用方可能无法区分两种取消来源。
- **建议改法和验证点**: 当前设计已接受此取舍。建议在 `RunCancelledData.reason` 中保留当前默认值 `"cancelled"`；未来若需要区分，可考虑在 `BatchToolExecutionOutcome` 中增加 executor 级取消语义。当前无需修改，仅记录为已知限制。
- **修复风险（低/中/高）**: 低（记录性质）
- **严重程度（低/中/高/严重）**: 中

### 3-未通过-中-`ToolCallsBatchReadyData` 在 bijection 校验前发射

**Controller decision**: resolved (artifact wording fix) —— 代码当前时机（输入侧预校验通过后、`ToolExecutor.execute` 调用前）是正确语义；implementation artifact §1/§4.1 已更正"bijection 校验完成后发射"为"输入侧预校验后、execute 前"；代码不动。

- **入口/函数**: `_AsyncAgent._execute_tool_batch`
- **文件(行号)**: `dayu/engine/agent.py:1480-1508`
- **输入场景**: 批式 outcome 的 bijection 校验失败（`tool_batch_outcome_mismatch`）。
- **实际分支/行为**: `TOOL_CALLS_BATCH_READY` 和 `TOOL_CALL_REQUESTED` 事件在 executor 调用前发射（行 1480-1508）；bijection 校验在行 1547-1552 执行。若 bijection 失败，调用方已收到 `READY` / `REQUESTED` 事件但不会收到 `BATCH_DONE` / `tool_result_accepted`。
- **预期行为**: 设计文档 §4.1 明确说 "`TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、bijection 校验完成后发射一次"。当前实现在 bijection 校验前发射。
- **直接证据**:
  - `agent.py:1480`: `yield self._make_event(event_type=EngineEventType.TOOL_CALLS_BATCH_READY, ...)`
  - `agent.py:1547-1552`: `bijection_failure = self._validate_batch_bijection(...)` 在 `READY` 事件之后
  - 实现 artifact §4.1: "`TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、bijection 校验完成后发射一次"
- **影响**: Host observer 可能观察到 `READY` / `REQUESTED` 事件后等待 `BATCH_DONE`，但 bijection 失败导致 batch 以 `RUN_FAILED` 终结，`BATCH_DONE` 永不出现。这在 Host 端可能造成事件序列不完整。
- **建议改法和验证点**: 将 `TOOL_CALLS_BATCH_READY` 和 `TOOL_CALL_REQUESTED` 的发射移到 bijection 校验通过之后、实际 executor 调用之前。或者更新设计文档以匹配当前实现（当前实现中 `READY` 表示"batch 已构建，即将提交给 executor"，而非"bijection 已验证"）。需与 Controller 确认哪种语义是正确的。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未通过-低-`_all_records_failed` 不区分 cancelled 与 completed 的计数语义

**Controller decision**: controller-rejected (semantics retained) —— "cancelled 不计入失败"是有意设计；新增 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues` 固化该语义。

- **入口/函数**: `_AsyncAgent._all_records_failed`
- **文件(行号)**: `dayu/engine/agent.py:2235-2251`
- **输入场景**: 批内所有 outcome 均为 `ToolCancelledOutcome`（无 completed、无 failed）。
- **实际分支/行为**: `_all_records_failed` 返回 `False`（因为 cancelled 不是 failed），`_consecutive_failed_tool_batches` 被清零。
- **预期行为**: 设计文档 §5.3 说 "cancelled 不计入失败"。当批内全部 cancelled 时，`_consecutive_failed_tool_batches` 被清零，后续迭代正常继续。这是有意设计：cancelled 不是失败，不应触发 fallback。
- **直接证据**:
  - `agent.py:2248-2251`: `return all(isinstance(record.outcome, ToolFailedOutcome) for record in records)`
  - `agent.py:807-810`: `if self._all_records_failed(batch_result.records): ... else: self._consecutive_failed_tool_batches = 0`
- **影响**: 若 Host 工具治理策略对所有工具都返回 `cancelled`（如全部审批被拒），Engine 不会触发 `consecutive_failed_tool_batches` fallback，而是继续迭代直到 `max_iterations` 耗尽后才收口。这可能不是预期行为——全部 cancelled 的批次实际上没有产出有效信息。
- **建议改法和验证点**: 当前设计明确 "cancelled 不计入失败"，这是合理的设计选择。但建议在 `_all_records_failed` docstring 中补充说明：全部 cancelled 的批次不会触发 consecutive failed batches fallback，会继续迭代。若需要"全部 cancelled 视为无效批次"的语义，应由 Controller 发起新的设计决策。
- **修复风险（低/中/高）**: 低（记录性质）
- **严重程度（低/中/高/严重）**: 低

### 5-未通过-低-`ToolCancelledOutcome` LLM 投影缺少 `ok: false` 信封一致性

**Controller decision**: controller-rejected —— cancelled 与 completed/failed 是不同语义层；cancelled 投影格式是有意区分，不沿用 `ok:false` 信封。

- **入口/函数**: `_project_tool_cancelled_for_llm`
- **文件(行号)**: `dayu/engine/agent.py:311-328`
- **输入场景**: 工具级取消 outcome 注入 LLM context。
- **实际分支/行为**: 投影为 `{"cancelled": true, "reason": "...", "message": "...", "hint": "..."}`。
- **预期行为**: `completed` 投影使用 `ToolResultSuccess` 信封（含 `ok: true`），`failed` 投影使用 `ToolResultFailure` 信封（含 `ok: false`、`error`、`message`）。`cancelled` 投影使用自定义结构 `{"cancelled": true, ...}`，与其他两种 outcome 的信封风格不一致。
- **直接证据**:
  - `agent.py:321-328`: `projected: dict[str, _PlainJsonValue] = {"cancelled": True, "reason": ..., "message": ...}`
  - `agent.py:283-289`: completed 投影使用 `_project_tool_success_for_llm`
  - `agent.py:302-308`: failed 投影使用 `_project_tool_failure_for_llm`
- **影响**: LLM 看到的 cancelled 结果格式与 completed/failed 不一致。这可能是有意设计（cancelled 是新语义，不需要沿用旧信封），但可能影响 LLM 对工具结果的理解。
- **建议改法和验证点**: 当前投影格式清晰表达了 cancelled 语义，LLM 应能理解。建议保持当前实现，仅在设计文档中记录 cancelled 投影格式与 completed/failed 的差异。
- **修复风险（低/中/高）**: 低（记录性质）
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **`TOOL_CALLS_BATCH_READY` 发射时机**（Finding 3）：设计文档说"bijection 校验完成后发射"，当前实现在校验前发射。需 Controller 确认哪种语义正确。若选择更新文档，需同步修改实现 artifact。

2. **全部 cancelled 批次的 fallback 语义**（Finding 4）：当前全部 cancelled 不触发 consecutive failed batches fallback。若 Host 工具治理策略频繁返回 cancelled（如审批系统），Engine 会持续迭代直到 `max_iterations` 耗尽。是否需要"全部 cancelled 视为无效批次"的新设计决策？

## Residual Risk

- **Host / ToolRuntime 批式 `ToolExecutor` 实现**：Slice 1 仅锁定公共契约形状与 Engine 内部一致性；Host 侧把一组 `ToolCallable` 包装为受治理批式 `ToolExecutor` 的实现尚未进入本 slice。这是已知且有意的未覆盖项。
- **`docs/host/design.md` stale references**：两处 `ToolExecutionContext` 引用需要更新（Finding 1）。不影响运行时，但影响文档一致性。
- **测试覆盖**：Phase 3 测试覆盖了主要 batch handshake 路径（completed/failed/cancelled/awaiting/mixed/duplicate/exception/timeout/bijection）。未覆盖的边界包括：executor 返回空 records、executor 返回 records 中含未知 outcome variant（由 pyright `assert_never` 守护）、多个 awaiting 同时出现。
- **pyright**: `dayu/contracts/` 和 `dayu/engine/` 0 errors, 0 warnings, 0 informations。
- **焦点测试**: 78 passed，0 failed。
