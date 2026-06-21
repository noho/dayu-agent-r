# WU-TOOLS-01-F01-02-R1 Slice 1 Code Review Fix

## 范围

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 1 `Host accepted-wait activation hook`
- fix owner: AgentCodex
- 输入依据：
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`

## 改动

- `dayu/host/tool_runtime.py`
  - 收紧 accepted wait activation failure warning：移除该路径的 `exc_info=True`，warning 只保留 session / run / attempt / tool / adapter key / exception class 等有界 metadata。
- `tests/host/test_toolruntime_executor.py`
  - 在现有 Host ToolRuntime executor harness 内新增可翻转 cancellation token、accepted ack 后取消的 awaiting accept fake port，以及 activation adapter spy。
  - 增加 accepted ack 后、activation 前 cancellation 变为 true 时不调用 activation 的 focused regression。
  - 扩展 activation failure 测试，断言 diagnostic 与 warning log 均不包含 raw provider-like exception message。
  - 增加 `WaitActivationRequest` defensive validation 测试，覆盖空 `tool_name` 与非法 `await_spec`。

## CR-F 处理

- CR-F01：已修复。
  - 新增 `test_cancel_after_awaiting_accept_skips_activation`。
  - 测试通过 `_CancellingAwaitingAcceptPort` 在返回 `ToolAwaitingAcceptedAck` 后立即翻转同一个 `CancellationToken`，直接覆盖 awaiting accept accepted 后、activation 前的取消 interleaving。
  - 断言返回仍是 accepted awaiting outcome，且 activation adapter 未收到请求。
- CR-F02：已修复。
  - 移除 `_activate_accepted_wait_best_effort` 中 activation failure warning 的 traceback/raw exception logging。
  - warning 仍记录 bounded metadata：`session_id`、`run_id`、`attempt_id`、`tool_name`、`adapter_key`、`error_type`。
  - `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` 使用 `caplog` 断言 raw provider-like message `raw-provider-job-secret` 不进入 warning log，也不进入 diagnostic message。
- CR-F03：已修复。
  - 新增 `test_wait_activation_request_rejects_empty_tool_name`。
  - 新增 `test_wait_activation_request_rejects_invalid_await_spec`。
  - 仅覆盖既有 defensive validation，不扩展 runtime contract，不增加兼容逻辑。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - 结果：`37 passed in 0.33s`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README 判断

- 已按 AGENTS.md 读取 `dayu/host/README.md` 的 Agent 更新约束。
  - 本次只收紧内部 warning 行为并补足 executor harness 测试，不改变 Host public API、稳定开发契约、状态机、事件流或扩展点说明；无需更新。
- 已按 AGENTS.md 读取 `tests/README.md`。
  - 本次只在既有 `tests/host/test_toolruntime_executor.py` 内补 focused regression，不新增测试层级、运行方式或维护约定；无需更新。

## 剩余风险

- 未覆盖真实 provider activation adapter 的集成路径；本 Slice 1 fix 按 controller 要求限制在 Host ToolRuntime executor harness 内。
- activation diagnostic emitter 自身失败时仍沿既有 best-effort diagnostic failure warning 使用 `exc_info=True`；本次 CR-F02 只要求收紧 accepted wait activation failure path，未扩大修改范围。
