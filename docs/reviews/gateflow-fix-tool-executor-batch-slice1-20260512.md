# Gateflow Fix Gate: Tool Executor Batch — Slice 1

- **Date**: 2026-05-12
- **Branch**: `host/phase_0_design`
- **Agent**: AgentOpus (gateflow fix gate)
- **Plan**: `docs/reviews/gateflow-plan-tool-executor-batch-20260512.md`
- **Implementation artifact**: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
- **Reviews input**:
  - `docs/reviews/code-review-tool-executor-batch-slice1-20260512-mimo.md`
  - `docs/reviews/code-review-tool-executor-batch-slice1-20260512-ds.md`

## 1. Controller 决策概览

按 Controller 修复决策处理 review 全量 finding：

| 决策 | 类别 | 内容 |
| --- | --- | --- |
| ACCEPT-1 | 文档同步 | 修复 `docs/host/design.md` 中 `ToolExecutionContext` / `ToolExecutionRequest` 残留命名 |
| ACCEPT-2 | artifact 表述纠偏 | 修正 implementation artifact 中"bijection 校验完成后发射"为"输入侧预校验后、execute 前"，*不动代码* |
| ACCEPT-3 | 生产代码修复 | 删除 `_execute_tool_batch` 中 accepted-events 与 tool_awaiting 之间的 late-cancel 检查，保证 commit-edge 语义 |
| ACCEPT-4 | 测试补齐 | 新增 4 组测试：cancelled outcome 构造期校验（reason / message）、all-cancelled 批次不触发 fallback、all-awaiting 批次挂起、accepted→awaiting race late-cancel 不吞挂起 |
| REJECT | 不做 | CancelledError 归因 / all-cancelled 视为失败 / cancelled LLM `ok:false` 信封 / `_ToolOutcomeRecord` 重命名 |

## 2. 文件变更清单

### 2.1 生产代码

- `dayu/engine/agent.py`
  - 删除 `_execute_tool_batch` 中位于 accepted records emit 之后、TOOL_AWAITING emit 之前的 `if self._is_cancelled(): yield … cancelled_terminal` 短路。
  - 保留 awaiting 全部发射完毕后、进入下一轮 Runner 调用前的 `_is_cancelled()` 检查；保留 pre-execute 取消 race 走 run_cancelled 的路径。
  - 语义：executor 返回的 records 已是「已接受事实」，late cancellation 不能吞掉 tool_awaiting / run_suspended；只能阻止下一轮 Runner。

### 2.2 文档

- `docs/host/design.md`
  - L657: `ToolExecutionContext` → `BatchToolExecutionContext`
  - L667: `ToolExecutionContext` → `BatchToolExecutionContext`
  - L1151: `ToolExecutionRequest` 描述行更新为 `ToolCallRequest`
  - L1159: `ToolExecutionRequest(name="fetch_more", ...)` → `ToolCallRequest(name="fetch_more", ...)`
  - L1198: `ToolExecutor.execute(ToolExecutionRequest{...})` →
    `ToolExecutor.execute(BatchToolExecutionRequest{calls=[ToolCallRequest{...}], context=...})`

- `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
  - §1 与 §4.1：将 `TOOL_CALLS_BATCH_READY` 发射时机表述由"bijection 校验完成后"更正为"输入侧预校验（duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前"；补充说明该事件不承诺 bijection 通过，bijection 失败时本批以 `RUN_FAILED` 终结、无 `BATCH_DONE`。

### 2.3 测试

- `tests/contracts/test_tool_outcome_exhaustive.py`
  - 顶部新增 `import pytest`。
  - 新增 `test_cancelled_rejects_invalid_reason`：非白名单 reason 在 `__post_init__` 抛 `ValueError`。
  - 新增 `test_cancelled_rejects_empty_message`：空 message 在 `__post_init__` 抛 `ValueError`。

- `tests/engine/test_agent_phase3_tool_call.py`
  - 新增 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues`：
    全部 cancelled 批次 → `cancelled_count == 2` / `failed_count == 0` / 不触发 fallback，
    runner 进入下一轮并以 `FINAL_ANSWER` 收口。
  - 新增 `test_all_awaiting_batch_suspends_with_empty_accepted_records`：
    全部 awaiting → 两次 `TOOL_AWAITING`、零次 `TOOL_RESULT_ACCEPTED`，
    `RunSuspendedData.accepted_records == ()`，`awaiting_records` 含两条。
  - 新增 `test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend`：
    在 `TOOL_RESULT_ACCEPTED` emit 之后、`TOOL_AWAITING` emit 之前触发 cancel，
    final terminal 仍为 `RUN_SUSPENDED`，不出现 `RUN_CANCELLED`。

## 3. Findings 处置详情

### 3.1 mimo review

| ID | 处置 | 备注 |
| --- | --- | --- |
| F1 (`docs/host/design.md` stale `ToolExecutionContext`) | resolved/fixed | 见 §2.2，5 处全部更新 |
| F2 (CancelledError 归因歧义) | controller-rejected/deferred | 当前 commit-edge 取舍是有意设计，已在 docstring 中记录；不在 Slice 1 范围内扩展 outcome variant |
| F3 (`TOOL_CALLS_BATCH_READY` 在 bijection 校验前发射) | resolved (artifact wording fix) | 代码当前时机是正确语义；修正 implementation artifact 表述，不移动代码 |
| F4 (all-cancelled 是否计入失败) | controller-rejected (semantics retained) | "cancelled 不计入失败"是有意设计；在测试 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues` 中固化该语义 |
| F5 (cancelled LLM 投影 `ok:false` 信封) | controller-rejected | cancelled 与 completed/failed 是不同语义层，自定义投影格式是有意区分 |

### 3.2 ds review

| ID | 处置 | 备注 |
| --- | --- | --- |
| CR-01 (缺 all-cancelled 测试) | resolved/fixed | 新增 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues` |
| CR-02 (缺 `ToolCancelledOutcome.__post_init__` 测试) | resolved/fixed | 新增 `test_cancelled_rejects_invalid_reason` / `test_cancelled_rejects_empty_message` |
| CR-03 (`TOOL_CALLS_BATCH_READY` 时机 vs artifact) | resolved (artifact wording fix) | 同 mimo F3；修正 implementation artifact 文字 |
| CR-04 (缺 all-awaiting 测试) | resolved/fixed | 新增 `test_all_awaiting_batch_suspends_with_empty_accepted_records` |
| CR-05 (`_ToolOutcomeRecord` 重命名建议) | controller-rejected | 计划中为非硬性建议；不在 Slice 1 范围内做命名重构 |
| CR-06 (accepted→awaiting 间 cancel race 测试) | resolved/fixed + 生产代码修复 | 新增 `test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend`，同步修复 `_execute_tool_batch` 中违反 commit-edge 的 late-cancel 短路（见 §2.1） |

## 4. 验证

```text
$ source .venv/bin/activate && pytest tests/contracts/test_tool_outcome_exhaustive.py tests/engine/test_agent_phase3_tool_call.py
44 passed

$ source .venv/bin/activate && pytest tests/contracts tests/engine
345 passed

$ source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

## 5. 未变更项 / 已知 residual

- Host / ToolRuntime 把 `ToolCallable` 装配为受治理批式 `ToolExecutor` 的实现仍未进入 Slice 1（设计文档与 implementation artifact §8 已记录）。
- `ALLOWED_TOOL_CANCELLED_REASONS` 仍为 `{timeout, approval_denied, host_cancelled}`；若未来需要新的工具级取消语义需要单独设计决策。
- 本 slice 不 commit；交由 Controller 后续 gate。
