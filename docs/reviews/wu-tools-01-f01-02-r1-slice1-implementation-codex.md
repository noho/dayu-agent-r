# WU-TOOLS-01-F01-02-R1 Slice 1 Implementation

## Slice

- id/name: Slice 1 Host accepted-wait activation hook
- gate: implementation
- implementer: Codex
- date: 2026-06-21

## Changed Files

- `dayu/host/wait_adapter.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_executor.py`
- `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`

## Implementation Summary

- 在 `dayu.host.wait_adapter` 增加 Host 内部 activation contract:
  - `WaitActivationRequest`
  - `WaitActivationAdapter`
  - `WaitActivationAdapterRegistration`
  - `WaitActivationRegistry`
- `WaitActivationRegistry` 复用现有 `WaitAdapterKey` 解析 activation adapter，保持 construction-time wiring，不新增 Engine / LLM-facing awaiting contract。
- 扩展 `ToolRuntimeBuildRequest` 与 `ToolRuntimeExecutor`，接收可选 `wait_activation_registry`。
- 在 `_accept_awaiting(...)` 中，仅当 `ToolAwaitingAcceptedAck` 已返回后，且 `context.cancellation_token.is_cancelled()` 为 `False` 时，按 `binding.adapter_key` 解析 activation adapter 并调用。
- activation adapter 未配置或未注册时 no-op。
- activation adapter 抛出异常时，ToolRuntime 只记录有界 diagnostic `wait_activation_failed`，diagnostic message 只包含异常类型，不包含 provider/job 原始异常消息；accepted wait 仍返回原 `ToolAwaitingOutcome`。
- 测试 harness 增加 spy activation adapter，并覆盖 accepted、rejected、timeout、retry exhausted、missing binding、missing external job ref、pre-cancelled context、duplicate awaiting fanout waiter、stale execution rejected 和 activation exception 路径。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - result: `34 passed in 0.45s`
- `tests/host/test_phase7_waiting_integration.py`
  - result: 未运行；本 slice 未修改该文件，也未需要 production-like wiring assertion。
- `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright reported only a newer-version notice: `v1.1.409 -> v1.1.410`。

## Docs Decision

- 未更新 README、design doc 或 control doc。
- 原因：本 slice 只增加 Host 内部 construction-time activation hook 与 focused Host 测试，不改变公开 Host API、Engine contract、LLM-facing tool schema、Service wiring、用户工作流或测试分层说明。
- 已按 README 触发规则阅读 `dayu/host/README.md` 与 `tests/README.md` 的更新约束；当前变更不属于必须写入这些 README 的职责范围。

## Residual Risks / Uncovered Areas

- covered by later approved slice: Fins prepare / activate two-phase runtime 尚未实现；当前 slice 只提供 Host accepted-wait 后的 activation hook。
- covered by later approved slice: Service / production Fins wiring 尚未注入 `WaitActivationRegistry`；当前 slice 保持未配置时 no-op。
- covered by later approved slice: Fins activation idempotency、activation failure 后 observation terminal state、prepared-but-unaccepted observation cleanup 行为尚未验证。
- covered by later approved slice: end-to-end Fins awaiting download / preprocess / upload submit-before-accept 验证尚未执行。

## Completion Status

- status: Slice 1 implementation complete
- stop point: 按用户要求停在 implementation artifact 完成后；未进入 code review、fix、commit、push、PR 或其它 slice。
