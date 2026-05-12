# Code Review: ToolExecutor Batch — Slice 1

- **Date**: 2026-05-12
- **Reviewer**: DeepSeek (Code Review Agent)
- **Review Target**: 当前 workspace 未提交 diff，Slice 1 范围
- **Accepted Plan Commit**: `aa5e621`
- **Implementation Artifact**: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
- **Review Type**: Gateflow-governed adversarial code review

## 结论

实现质量良好，无 blocking correctness 发现。340 测试全部通过，pyright 零错误。旧 `ToolExecutionRequest` / `ToolExecutionContext` / `FunctionToolExecutor` / `ToolFunctionCallable` 完全移除且无残留引用。批式双射验证、取消提交边界、cancelled-vs-failed 语义、非 flatten record 形状、`@tool` 装饰器保留与 Engine 边界隔离均符合计划要求。

**发现 5 个 MEDIUM 问题、3 个 LOW 问题**，均归因于测试覆盖缺口与实现 artifact 描述偏差，不涉及生产代码正确性回归。未见旧 per-call 契约泄漏或隐藏兼容表面。

Controller 决策状态：见各 finding 标注（详见 `docs/reviews/gateflow-fix-tool-executor-batch-slice1-20260512.md`）。

---

## Findings

### CR-01 | MEDIUM | 缺少 all-cancelled 批次的 `_all_records_failed` 语义测试

**位置**: `tests/engine/test_agent_phase3_tool_call.py`

**事实**:
- 计划 §5.9 明确要求："测试必须覆盖 all-cancelled、all-failed、mixed failed+cancelled 三种计数与 `_all_records_failed` 语义。"
- `_all_records_failed()` 实现位于 `dayu/engine/agent.py:2235`，语义正确：空 records 或存在任一 completed/cancelled 时返回 `False`。
- 现有测试 `test_mixed_outcomes_in_single_batch_count_correctly` 覆盖了 1 completed + 1 failed + 1 cancelled 的混合批次计数。
- 现有测试 `test_consecutive_failed_batches_force_answer_raise_and_reset` 覆盖了 all-failed 触发 fallback 与 success 清零。
- **没有**对 "所有 outcome 都是 `ToolCancelledOutcome` 的批次不触发 `_consecutive_failed_tool_batches` 递增" 的独立测试。all-cancelled 批次在 prod 路径中将由 `_all_records_failed` 返回 `False` 并 reset 计数器，但无测试验证。

**风险**: 若未来有人修改 `_all_records_failed` 逻辑（如添加 `ToolCancelledOutcome` 也算失败的规则），不会被现有测试捕获。all-cancelled 批次的 fallback 行为可能被错误归类。

**建议**: 新增测试：构造 all-cancelled 批次（至少 2 个调用，全部返回 `ToolCancelledOutcome`），验证 (a) `tool_calls_batch_done.cancelled_count == 2`，(b) `failed_count == 0`，(c) `_consecutive_failed_tool_batches` 被重置为 0（后续成功 Runner 调用进入 `final_answer` 而非 fallback）。

**Controller 决策状态**: resolved/fixed — 新增 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues`（tests/engine/test_agent_phase3_tool_call.py）。

---

### CR-02 | MEDIUM | 缺少 `ToolCancelledOutcome.__post_init__` 构造期校验的单元测试

**位置**: `tests/contracts/test_tool_outcome_exhaustive.py`

**事实**:
- `ToolCancelledOutcome.__post_init__` 校验两件事：`reason` 必须在 `ALLOWED_TOOL_CANCELLED_REASONS` 内，`message` 必须非空。
- `test_tool_outcome_exhaustive.py` 仅测试了 `_make_cancelled(reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED, ...)` 的分类分支，未验证非法 reason 和空 message 的 `ValueError` 抛出。
- prod 代码行为正确（手动验证确认），但缺少自动化测试。

**风险**: 若有人放宽 `__post_init__` 校验逻辑（如改为 warn-only），测试不会捕获。低概率但 contracts 层防御应可验证。

**建议**: 在 `test_tool_outcome_exhaustive.py` 增加 `test_cancelled_rejects_invalid_reason` 和 `test_cancelled_rejects_empty_message`。

**Controller 决策状态**: resolved/fixed — 新增 `test_cancelled_rejects_invalid_reason` 与 `test_cancelled_rejects_empty_message`（tests/contracts/test_tool_outcome_exhaustive.py）。

---

### CR-03 | MEDIUM | `TOOL_CALLS_BATCH_READY` 发射时机与实现 artifact 描述不一致

**位置**: `dayu/engine/agent.py:1480-1495`

**事实**:
- 实现 artifact §4.1 声明："`TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、bijection 校验完成后发射一次"。
- 实际代码在 `_execute_tool_batch` 内、**pre-validate duplicate ids**（行 1459-1471）之后、**调用 `_execute_batch(batch_request)`**（行 1539）之前发射。
- Post-executor bijection 校验（行 1547 `_validate_batch_bijection`）尚未发生时就已 emit `TOOL_CALLS_BATCH_READY`。
- 这**不是** correctness bug——`TOOL_CALLS_BATCH_READY` 是观测性事件，语义上是 "batch 已组成且已通过输入侧预校验，即将提交执行"。实现 artifact 的 "bijection 校验完成后" 表述可能指输入侧 duplicate check（plan §6.1 step 2 "预校验 tool call ids"），但 plan 中 "预校验" 与 "双射校验" 是两个不同概念。

**风险**: 调用方若误以该事件作为 "executor 已返回并通过双射校验" 的信号，可能过早假设执行结果。但这不是 Engine bug，是文档精确性问题。

**建议**: 修正实现 artifact §4.1 的表述，明确 "预校验完成后"（指 duplicate check 和已执行 id 检查）而非 "bijection 校验完成后"。或按实现 artifact 文字移动该事件的 emit 位置到 bijection 校验通过后（更严格但语义变化）。

**Controller 决策状态**: resolved (artifact wording fix) — 代码当前时机是正确语义；implementation artifact §1/§4.1 已更正表述，代码不动。

---

### CR-04 | LOW | 缺少 all-awaiting 批次挂起测试

**位置**: `tests/engine/test_agent_phase3_tool_call.py`

**事实**:
- 现有测试 `test_tool_awaiting_suspends_run_with_accepted_and_awaiting_records` 覆盖 mixed batch（1 awaiting + 1 completed）。
- 现有测试 `test_awaiting_cancellation_before_and_after_outcome_boundary` 覆盖单个 awaiting + 取消边界。
- **没有**测试覆盖 "批次中所有工具调用都返回 `ToolAwaitingOutcome`，无 accepted records，仍正确 emit `tool_awaiting` 和 `run_suspended`"。
- prod 路径中此场景由 `_execute_tool_batch` 行 1611 的 `if awaiting_records:` 分支处理，accepted_records 可以为空元组——`RunSuspendedData.__post_init__` 只校验 awaiting_records 非空。行为正确但无测试。

**风险**: 低。实现正确处理了空 accepted_records，但无回归保护。

**建议**: 新增测试：构造一个 `_RecordingToolExecutor` 返回两个 `ToolAwaitingOutcome`，验证 `accepted_records` 为空、`awaiting_records` 包含两个记录、terminal 为 `RUN_SUSPENDED`。

**Controller 决策状态**: resolved/fixed — 新增 `test_all_awaiting_batch_suspends_with_empty_accepted_records`。

---

### CR-05 | LOW | `_ToolOutcomeRecord` 命名未按计划建议重命名

**位置**: `dayu/engine/agent.py:396`

**事实**:
- 计划 §5.9 原文："实现时可以将其重命名为更准确的 `_AcceptedOutcomeRecord`"。
- 实现保持 `_ToolOutcomeRecord`。
- 这不是硬性要求（计划写 "可以"），也不影响正确性。但在计划引用追踪中应记录此偏差。

**风险**: 无。纯粹命名一致性差异。

**Controller 决策状态**: controller-rejected — 计划中为非硬性建议；Slice 1 不做命名重构。

---

### CR-06 | LOW | 缺少 cancellation 在 accepted 与 awaiting emit 之间的 race 测试

**位置**: `dayu/engine/agent.py:1585-1646`

**事实**:
- 在 `_execute_tool_batch` 中，accepted records 的 `TOOL_RESULT_ACCEPTED` 事件在行 1585-1609 emit 完成，随后在行 1612 检查取消才进入 awaiting 分支。
- 现有测试 `test_awaiting_cancellation_before_and_after_outcome_boundary` 仅覆盖两种边界：(a) executor 返回前取消；(b) 所有 `TOOL_AWAITING` 已 emit 后取消。
- **没有**覆盖 "accepted 已 emit 但在 `TOOL_AWAITING` 尚未 emit 时取消到达" 的精确时序。
- prod 行为：行 1612 的 `if self._is_cancelled()` 会 win，发出 `run_cancelled` 而不会有 `TOOL_AWAITING` 或 `RUN_SUSPENDED`。这符合取消提交边界语义——awaiting 不是已接受的终态。

**风险**: 极低。此 race 需要精确的时序编排，实际不太可能发生，且 prod 行为正确。

**Controller 决策状态**: resolved/fixed + 生产代码修复 — 新增 `test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend`；同步删除 `_execute_tool_batch` 中 accepted-events 与 tool_awaiting 之间违反 commit-edge 的 `_is_cancelled()` 短路。

---

## 开放问题与 Residual Risk

### OR-01: Host / ToolRuntime 不存在

`dayu/host` 和 `dayu/service` 目录均不存在。计划要求验证的 `rg` 命令已返回 stderr (os error 2)。这意味着 batch executor / ToolCallable 组合为 ToolExecutor 的实现尚未进入本 Slice。风险已在 implementation artifact §8 记录，无需新发现。

### OR-02: `correlation_id` per-batch 语义变更

所有 `correlation_id` 引用均使用 batch-level 格式 `f"{run_id}:{iteration_id}:tool_batch"`。仅 `dayu/engine/agent.py` 的 `_batch_correlation_id()` 和 `dayu/contracts/tool_call.py` 的 docstring 引用。测试 `test_completed_tool_call_injects_messages_and_reaches_final` 验证了正确的 batch-level 值。无残留 per-call `correlation_id` 使用。

### OR-03: 外部调用方旧导入破坏

旧 `ToolExecutionRequest` / `ToolExecutionContext` / `FunctionToolExecutor` / `ToolFunctionCallable` 在 Python 文件中零残留。旧 flat event/outcome 字段（`await_spec` / `snapshot` 在 `RunSuspendedData` 上）已全部切换到 `accepted_records` / `awaiting_records`。外部调用方需要迁移到新 shape。这是计划 §5.7 所列的有意 public break。

### OR-04: 缺少 `_all_records_failed` 单元测试

`_all_records_failed` 方法（`agent.py:2235`）没有被独立的单元测试覆盖。它通过 `test_consecutive_failed_batches_force_answer_raise_and_reset` 间接测试，但空 records、all-cancelled、mixed 等全部输入组合没有穷尽覆盖。这是 CR-01 的补充层面。

### OR-05: `ALLOWED_TOOL_CANCELLED_REASONS` 仅三值

当前允许的取消原因为 `{approval_denied, host_cancelled, timeout}`。若未来有新的工具级取消语义（如 `rate_limited`），`ALLOWED_TOOL_CANCELLED_REASONS` 需要同步扩展。这是设计而非实现问题。

---

## 验证摘要

### 自动化验证

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/contracts/test_tool_outcome_exhaustive.py tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py` | 73 passed |
| `pytest tests/contracts tests/engine` | 340 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `rg "ToolExecutionRequest\|ToolExecutionContext" --type py` | 零残留（全部为 `BatchToolExecutionRequest` / `BatchToolExecutionContext`） |
| `rg "FunctionToolExecutor\|ToolFunctionCallable" --type py` | 零残留 |
| `rg "ToolExecutor\|execute.*ToolExecutionRequest" dayu/host dayu/service` | 目录不存在（exit code 2） |

### 计划符合性检查

| 计划要点 | 验证状态 |
| --- | --- |
| `ToolExecutor.execute` 唯一 batch 签名 | 通过（`tool_executor.py:30-32`） |
| 旧 `ToolExecutionRequest`/`ToolExecutionContext` 移除 | 通过（零残留） |
| `ToolCancelledOutcome` 独立于 failed | 通过（`_count_cancelled_tool_records` 单独统计） |
| `ALLOWED_TOOL_CANCELLED_REASONS` 常量集合 | 通过（三值 frozenset + `__post_init__` 校验） |
| `BatchToolExecutionRecord` / `BatchToolExecutionOutcome` | 通过（tool_outcome.py:136-164） |
| `ToolCallable` 单工具协议 + `@tool` 装饰器 | 通过（`tool_declaration.py:37-262`） |
| Engine 不消费 `ToolDefinition`/`ToolCallable` | 通过（agent.py 无导入） |
| `FunctionToolExecutor` 移除 | 通过（零残留） |
| Event/outcome 非 flatten record shape | 通过（`record.call`, `record.batch_snapshot`） |
| `RunSuspendedData` / `EngineRunOutcomeSuspended` 用 `accepted_records` / `awaiting_records` | 通过 |
| `ToolCallsBatchDoneData.cancelled_count` 新增 | 通过（含 `__post_init__` 计数守恒校验） |
| 双射验证（missing/unknown/duplicate） | 通过（`_validate_batch_bijection`，含 set equality + duplicate 检查） |
| `_all_records_failed` 仅 all-failed 为 True | 通过（实现正确） |
| cancelled LLM projection | 通过（`_project_tool_cancelled_for_llm`） |
| cancelled 注入 tool message | 通过（`_inject_tool_messages` 不区分 cancelled） |
| `run_agent_and_wait` suspension mapping | 通过（行 2493-2503 原样映射） |
| `correlation_id` per-batch | 通过（`_batch_correlation_id` + 测试断言） |
| 包导出精确符合计划 §5.8 | 通过（contracts/engine/engine.contracts 三个 `__init__.py`） |

---

## Controller Decision Summary

| Finding | Severity | Status |
| --- | --- | --- |
| CR-01: 缺少 all-cancelled 批次测试 | MEDIUM | resolved/fixed |
| CR-02: 缺少 ToolCancelledOutcome 校验测试 | MEDIUM | resolved/fixed |
| CR-03: TOOL_CALLS_BATCH_READY 时机 vs artifact | MEDIUM | resolved (artifact wording fix) |
| CR-04: 缺少 all-awaiting 批次测试 | LOW | resolved/fixed |
| CR-05: `_ToolOutcomeRecord` 命名 | LOW | controller-rejected |
| CR-06: 缺少 accepted/awaiting 间 cancel race 测试 | LOW | resolved/fixed + 生产代码修复 |

**建议**: CR-01 和 CR-02 应在 Slice 2 开始前补齐，避免测试缺口进入后续 hardening 工作。CR-03 在实现 artifact 中修正一行表述即可，不涉及代码变更。CR-04/05/06 可按优先级排入 Slice 2。
