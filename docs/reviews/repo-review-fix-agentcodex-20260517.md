# Repo Review Fix - AgentCodex - 2026-05-17

## 范围

- gate：全仓 code review 修复 gate。
- 输入报告：
  - `docs/reviews/repo-review-20260517-1635.md`
  - `docs/reviews/repo-review-20260517-1654.md`
- 本轮未 commit、未 push、未开 PR。

## 已修复项

### SSE provider error / missing choices 成功空回答

修复：
- `dayu/engine/runners/openai/sse_parser.py`
  - SSE 顶层 `error` object 现在产出 `RunnerProtocolErrorData(error_code="sse_provider_error")` 并以 `RunnerDoneData(ERROR)` 收口。
  - 既无有效 `choices` 也无有效 `usage` 的 chunk 现在产出 `sse_missing_choices` 协议错误。
  - usage-only chunk 保持合法，不误报协议错误。
- `tests/engine/runners/openai/test_protocol_error.py`
  - 覆盖 provider error object、missing choices no usage、usage-only chunk、SSE unknown finish reason warning。

### 未知 finish_reason 诊断

修复：
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`

行为：
- 未知 `finish_reason` 保留既有 `STOP` 回落，新增 warning 诊断日志。

测试：
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_non_stream_response.py`

### Conversation Memory 接入本地 dispatch 主链路

修复：
- `dayu/host/api.py`
  - `HostLocalExecutionOptions` 增加 `memory_projection_policy` 与 `memory_projection_catchup_batch_size`。
- `dayu/host/dispatch.py`
  - worker accept 前按当前 Attempt `ATTEMPT_STARTED - 1` cursor 追平 conversation memory projection。
  - no-tool 与 tool-enabled builder 均注入同一 policy 的 `DurableMemorySnapshotProvider`。
  - `MemoryProjectionRepairRequired` 使用独立 closeout reason `memory_projection_repair_required`，不再混同 worker startup timeout。
- `dayu/host/projection.py`、`dayu/host/memory_repair.py`
  - projection runner / memory catch-up 支持 `max_event_sequence`，避免 queued follow-up 未来输入进入当前 active Attempt memory。
- `dayu/host/durable/memory.py`、`dayu/host/run_input.py`
  - durable provider 读取不超过 required cursor 的 snapshot，保留 future-leak 防线。
- `dayu/host/memory.py`
  - 增加默认 memory projection policy helper。

测试：
- `tests/host/test_dispatch_scheduler.py`
  - 覆盖 no-tool dispatch 注入 durable memory。
  - 覆盖 tool-enabled dispatch 注入 durable memory 且保留 ToolRuntime 接线。
- `tests/host/test_run_input_builder.py`
  - 覆盖同 Session future input 不泄漏到当前 Attempt。

### Contracts 构造期校验与静态类型

修复：
- `dayu/contracts/tool_call.py`
  - `ToolCallRequest` 拒绝空 `tool_call_id`、空 `name`、负 `index_in_iteration`。
- `dayu/contracts/tool_result.py`
  - `ToolResultFailure` 拒绝空 `error` / `message`。
- `dayu/contracts/tool_outcome.py`
  - `ToolCancelledOutcome.reason` 收紧为 `ToolCancelledReason` Literal。
- `dayu/contracts/__init__.py`
  - 导出 `ToolCancelledReason`。

测试：
- `tests/contracts/test_tool_call.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/contracts/test_package_exports.py`

### Host / Runtime 低风险运行时问题

修复：
- `dayu/host/api.py`
  - `OperationContext.business_object_type` 与 `scenario` 现在与其它 optional string 一致，存在时必须非空。
- `dayu/runtime/lane.py`
  - `_mark_token_lost` 现在唤醒等待中的 acquire waiter。
- `dayu/host/dispatch.py`
  - `_drain_loop` 未预期异常退出时记录 warning。
- `dayu/runtime/filelock.py`
  - 明确 `RuntimeFileLock` 同一实例不承诺多线程共享；当前生产代码无共享同一实例的证据。

测试：
- `tests/host/test_public_contracts.py`
- `tests/runtime/test_lane.py`
- `tests/host/test_dispatch_scheduler.py`

## 用户明确 deferred / no-change

### 发布入口指向不存在包

裁决：`user-deferred/no-change`。

直接原因：
- 用户补充约束明确要求本轮不修改 `pyproject.toml` 和根 `README.md` 的发布入口 / 用户命令问题。
- 本轮未修改 `pyproject.toml` 或根 `README.md`；`git diff -- pyproject.toml README.md` 为空。

状态：
- 不作为本轮 blocking。

### Engine Agent 硬编码 AsyncOpenAIRunner

裁决：`deferred/no-code-change`。

直接原因：
- 用户补充约束明确要求本轮不修改该 finding 的代码。
- 本轮未修改 `dayu/engine/agent.py`，未引入 runner factory。

追踪：
- 已在 `docs/host/implementation-control.md` 的追踪区新增 “Engine Runner Factory 解耦追踪”。

## 其它未修 / deferred 裁决

- Runner usage-only / tool_call_delta 后跨 attempt retry：不改。此前 re-review 已把“已 yield 事件后不跨 attempt retry”作为 pass 条件；本轮没有直接证据证明 usage-only 重试不会破坏调用方可见事件流与审计。
- `RECOVERING` Run：确认当前 `dayu/host/durable/run_transition.py` 无写入 `RECOVERING` 的转换；保留为 Phase 11 future-reserved 状态。本轮只在 `RunStatus` docstring 与 schema 注释标注，不围绕不可达状态堆分支。
- `cancel_active_wait_records_for_run` TOCTOU：成立为并发语义债，但安全修复需要重新定义批量 wait cancel 的部分成功 / 幂等 contract；本轮 deferred。
- session cancel 幂等重放多 active worker：当前单 active Run invariant 下影响被限制；若未来支持多 active worker，需要 schema 或 idempotency result contract 扩展，本轮 deferred。
- Gemini provider 专属合约：低严重架构债，涉及 public contract 重构，本轮 deferred。
- RuntimeFileLock 线程安全：未发现生产共享同一实例；本轮用 docstring 明确非线程安全边界，不加锁扩大语义。

## README / 文档同步

- 更新 `dayu/engine/README.md`：补充 SSE provider error、missing choices、usage-only chunk 与未知 finish reason 当前行为。
- 更新 `dayu/host/README.md`：补充本地 dispatch memory projection 接线、bounded catch-up、独立 memory repair closeout reason 与 drain loop 异常日志。
- 更新 `docs/host/implementation-control.md`：记录 Engine runner factory 解耦 deferred 追踪项。
- 未修改根 `README.md`，符合用户补充约束。

## 验证结果

- `source .venv/bin/activate && pytest tests/contracts/test_package_exports.py tests/contracts/test_tool_call.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/runtime/test_lane.py tests/host/test_public_contracts.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py -q`
  - 152 passed。
- `source .venv/bin/activate && pytest -q`
  - 979 passed。
- `source .venv/bin/activate && python -m pyright dayu tests`
  - 0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - passed。

## 残余风险

- 发布入口 public contract 仍未处理，是用户明确 deferred，不属于本轮 blocking。
- Engine runner factory 解耦仍未处理，已进入 implementation-control 追踪。
- Memory projection 目前按当前 Attempt cursor 做 bounded catch-up；如果其它 composition root 在 dispatch 前主动把同一 memory consumer catch-up 到 queued future cursor，当前 snapshot 表仍只保存 latest snapshot，后续需要配合 projection lifecycle owner 明确是否保留 snapshot history或避免越界 catch-up。
- `cancel_active_wait_records_for_run` 与 session cancel replay 的并发 / 幂等增强仍需后续独立设计，不应作为局部补丁处理。
